"""老师认领超星课：超星建课人登录名不是工号时，老师登录本系统后自己认领。

不收超星密码。认领人的工号来自本系统登录身份；认领的登录名下所有课的超星姓名都和
认领人教职工表姓名一致时直接生效，否则等学校系统管理员确认。生效的认领和
“dict:cx_login_alias”对照一样，下一次同步按工号入库；生效当时就把已入库的课改挂过来。
"""
from __future__ import annotations
from fastapi import HTTPException
from sqlalchemy import select
from .models import Setting,User,utcnow
from .core import audit,serial

CLAIMS_KEY='cx_login_claims'
LIVE={'PENDING','APPROVED'}

def _claims(db,lock=False):
    q=select(Setting).where(Setting.key==CLAIMS_KEY)
    obj=db.scalar(q.with_for_update() if lock else q)
    if obj is None and lock:
        obj=Setting(key=CLAIMS_KEY,value={'items':[]},version=1);db.add(obj);db.flush()
    items=list(((obj.value or {}).get('items') or [])) if obj else []
    return obj,[dict(x) for x in items if isinstance(x,dict)]

def _save(obj,items):
    obj.value={'items':items};obj.version=(obj.version or 0)+1

def approved_claims(db):
    _,items=_claims(db)
    return {x['login']:x['staff_no'] for x in items if x.get('state')=='APPROVED' and x.get('login') and x.get('staff_no')}

def _hr(db):
    from .reference_data import TeacherHrProfile
    return {p.staff_no:p.name for p in db.scalars(select(TeacherHrProfile).where(TeacherHrProfile.active.is_(True)))}

def _rows(db,login,lock=False):
    from .reference_data import TeacherCourseTerm
    q=select(TeacherCourseTerm).where(TeacherCourseTerm.origin=='CX',TeacherCourseTerm.active.is_(True),TeacherCourseTerm.staff_no==login)
    return db.scalars((q.with_for_update() if lock else q).order_by(TeacherCourseTerm.term_name.desc(),TeacherCourseTerm.course_code)).all()

def _taken(db,items):
    from .reference_data import cx_login_aliases
    dict_logins=set(cx_login_aliases(db,include_claims=False))
    return dict_logins|{x['login'] for x in items if x.get('state') in LIVE}

def _courses(rows):
    return [{'course_code':r.course_code,'course_name':r.course_name,'term_name':r.term_name,'teacher_name':r.teacher_name,'credit':r.credit} for r in rows]

def _me(db,actor):
    staff=(actor.user.staff_no or '').strip()
    if not staff:raise HTTPException(422,'当前账号没有工号，不能认领超星课程')
    name=_hr(db).get(staff) or actor.user.name or ''
    return staff,name

def my_claims(db,actor):
    """本人认领记录 + 可能是本人的超星登录名（超星姓名与本人一致、还没对上工号）。"""
    from .reference_data import TeacherCourseTerm
    staff,name=_me(db,actor);_,items=_claims(db);hr=_hr(db);taken=_taken(db,items)
    mine=[x for x in items if x.get('staff_no')==staff]
    logins=sorted(set(db.scalars(select(TeacherCourseTerm.staff_no).where(TeacherCourseTerm.origin=='CX',TeacherCourseTerm.active.is_(True),
        TeacherCourseTerm.teacher_name==name)))) if name else []
    candidates=[{'login':l,'courses':_courses(_rows(db,l))} for l in logins if l not in hr and l not in taken]
    return {'staff_no':staff,'name':name,'claims':mine,'candidates':candidates}

def _apply(db,actor,login,staff,user_id,reason):
    """把已入库、挂在登录名下的超星课改挂到工号；同一门课工号下已有就停用登录名那条。"""
    from .reference_data import TeacherCourseTerm
    moved=0
    for r in _rows(db,login,lock=True):
        key='|'.join(('CX',staff,r.course_code,r.term_name));before=serial(r)
        if db.scalar(select(TeacherCourseTerm.id).where(TeacherCourseTerm.external_key==key)):
            r.active=False
        else:
            r.staff_no=staff;r.external_key=key;r.user_id=user_id;r.extra={**(r.extra or {}),'cx_login':login}
        r.version+=1;moved+=1
        audit(db,actor,'teacher_course',r.id,'超星课程按认领改挂工号',before=before,after=serial(r),reason=reason)
    return moved

def _unapply(db,actor,login,staff,reason):
    from .reference_data import TeacherCourseTerm
    rows=db.scalars(select(TeacherCourseTerm).where(TeacherCourseTerm.origin=='CX',TeacherCourseTerm.active.is_(True),TeacherCourseTerm.staff_no==staff).with_for_update()).all()
    moved=0
    for r in rows:
        if (r.extra or {}).get('cx_login')!=login:continue
        key='|'.join(('CX',login,r.course_code,r.term_name));before=serial(r)
        r.staff_no=login;r.external_key=key;r.user_id=None;r.extra={k:v for k,v in (r.extra or {}).items() if k!='cx_login'};r.version+=1;moved+=1
        audit(db,actor,'teacher_course',r.id,'撤销认领，超星课程退回登录名',before=before,after=serial(r),reason=reason)
    return moved

def submit_claim(db,actor,login,note=''):
    login=(login or '').strip()
    if not login or len(login)>64:raise HTTPException(422,'请填写超星登录名')
    staff,name=_me(db,actor);hr=_hr(db)
    if login in hr:raise HTTPException(422,'这个登录名本身就是在职工号，系统会自动按工号算，不需要认领')
    obj,items=_claims(db,lock=True)
    if any(x.get('login')==login and x.get('staff_no')==staff and x.get('state') in LIVE for x in items):
        raise HTTPException(409,'你已经认领过这个登录名，请看“我的认领”里的状态')
    if login in _taken(db,items):raise HTTPException(409,'这个超星登录名已有人认领或已由管理员登记，如有疑问请联系学校系统管理员')
    rows=_rows(db,login)
    if not rows:raise HTTPException(404,'系统里没有这个超星登录名建的课，请核对登录名（要和超星里完全一致），或等下一次同步后再试')
    names=sorted({r.teacher_name for r in rows if r.teacher_name})
    auto=bool(name) and names==[name]
    item={'login':login,'staff_no':staff,'user_id':actor.user.id,'claimant':name,'cx_names':names,'courses':len(rows),
          'state':'APPROVED' if auto else 'PENDING','note':(note or '')[:200],'created_at':utcnow().isoformat(),
          'decided_by':'系统自动（姓名一致）' if auto else '','decided_at':utcnow().isoformat() if auto else ''}
    items=[x for x in items if not (x.get('login')==login and x.get('staff_no')==staff)]+[item];_save(obj,items)
    moved=_apply(db,actor,login,staff,actor.user.id,'老师认领超星课程（姓名一致自动生效）') if auto else 0
    audit(db,actor,'teacher_course','cx-claim:'+login[:40],'老师认领超星登录名',after=item,reason=item['note'] or '老师认领')
    return {**item,'moved':moved}

def list_claims(db,actor,state=None):
    _require_admin(actor);_,items=_claims(db)
    if state:items=[x for x in items if x.get('state')==state]
    return {'items':sorted(items,key=lambda x:(x.get('state')!='PENDING',x.get('created_at') or ''),reverse=False)}

def decide_claim(db,actor,login,staff,decision,reason):
    _require_admin(actor)
    obj,items=_claims(db,lock=True)
    item=next((x for x in items if x.get('login')==login and x.get('staff_no')==staff),None)
    if item is None:raise HTTPException(404,'认领记录不存在')
    want={'approve':'PENDING','reject':'PENDING','revoke':'APPROVED'}[decision]
    if item.get('state')!=want:raise HTTPException(409,'这条认领已处理，请刷新')
    before=dict(item);moved=0
    if decision=='approve':
        user=db.scalar(select(User).where(User.staff_no==staff))
        item['state']='APPROVED';moved=_apply(db,actor,login,staff,user.id if user else None,reason)
    elif decision=='reject':item['state']='REJECTED'
    else:item['state']='REVOKED';moved=_unapply(db,actor,login,staff,reason)
    item['decided_by']=actor.user.name or actor.user.id;item['decided_at']=utcnow().isoformat();item['decision_reason']=reason[:200]
    _save(obj,items)
    audit(db,actor,'teacher_course','cx-claim:'+login[:40],{'approve':'确认老师认领超星登录名','reject':'驳回老师认领超星登录名','revoke':'撤销老师认领超星登录名'}[decision],before=before,after=item,reason=reason)
    return {**item,'moved':moved}

def _require_admin(actor):
    if actor.role.kind!='school' or not actor.user.is_admin:raise HTTPException(403,'仅学校系统管理员处理超星认领')
