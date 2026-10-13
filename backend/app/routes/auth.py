"""R2 real local Cookie+CSRF authentication; not an SSO simulation."""
from datetime import timedelta
from hashlib import sha256
import secrets
from fastapi import APIRouter,Request,HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError
from ..core import *
from ..schemas import Login,Password
from ..passwords import hash_password,verify_password,DUMMY_HASH
from ..demo_identity import options as demo_options, target_actor, signed_selection
from ..schemas import Input
from pydantic import Field
router=APIRouter(prefix='/api/auth',tags=['本地认证'])

@router.post('/login')
def login(data:Login,request:Request):
    check_origin(request)
    if request.headers.get('content-type','').split(';')[0]!='application/json': raise HTTPException(415,'登录只接收JSON请求')
    cfg=request.app.state.settings;now=utcnow();failure=None;token=None
    username=data.username.strip()
    # No untrusted X-Forwarded-For; proxy deployment must configure trusted hops.
    ip=request.client.host if request.client else 'unknown'
    throttle_key=sha256(('login:'+ip).encode()).hexdigest()
    with request.app.state.sessions.begin() as db:
        throttle=db.scalar(select(Throttle).where(Throttle.key==throttle_key).with_for_update())
        if throttle is None:
            try:
                with db.begin_nested():
                    db.add(Throttle(key=throttle_key,attempts=0,window_start=now));db.flush()
            except IntegrityError: pass
            throttle=db.scalar(select(Throttle).where(Throttle.key==throttle_key).with_for_update())
        if (now-throttle.window_start).total_seconds()>cfg.login_window_seconds:
            throttle.window_start=now;throttle.attempts=0
        if throttle.attempts>=cfg.login_attempts*10:
            failure=(429,'尝试过于频繁，请稍后重试')
        else:
            user=db.scalar(select(User).where(User.username==username).with_for_update())
            valid=verify_password(user.password_hash if user else DUMMY_HASH,data.password)
            if user and user.locked_until and user.locked_until>now:
                failure=(429,'尝试过于频繁，请稍后重试')
            elif not user or not valid or not user.active:
                failure=(401,'账号或密码不正确，或账号不可用')
                if user:
                    user.failures+=1
                    if user.failures>=cfg.login_attempts: user.locked_until=now+timedelta(seconds=cfg.login_window_seconds)
            else:
                role,org=db.get(Role,user.role_id),db.get(Org,user.org_id)
                try:
                    if not role or not org: raise HTTPException(403,'身份配置未完成')
                    actor=Actor(db,user,role,org,request)
                except HTTPException:
                    failure=(403,'账号组织或角色配置不可用，请联系学校管理员')
                else:
                    old=request.cookies.get(cfg.cookie_name,'')
                    if old: db.execute(delete(AuthSession).where(AuthSession.token_hash==sha256(old.encode()).hexdigest()))
                    token=secrets.token_urlsafe(32)
                    session=AuthSession(token_hash=sha256(token.encode()).hexdigest(),csrf=secrets.token_urlsafe(32),user_id=user.id,
                         auth_version=user.auth_version,auth_method='local',expires_at=now+timedelta(hours=cfg.session_hours),last_seen=now)
                    db.add(session);user.failures=0;user.locked_until=None
                    request.state.actor_id,request.state.actor_name,request.state.org_id=user.id,user.name,user.org_id
                    audit(db,actor,'auth',user.id,'本地登录',after={'must_change_password':user.must_change_password},reason='本人密码登录')
        if failure:
            throttle.attempts+=1
            db.add(Audit(actor_id=None,actor_name='未登录',org_id=None,module='auth',object_id='login',action='登录拒绝',
                before={},after={'status':failure[0]},reason='身份校验未通过',result='DENIED',request_id=getattr(request.state,'request_id','')))
        db.flush()
    if failure: return JSONResponse({'detail':failure[1],'request_id':getattr(request.state,'request_id','')},failure[0])
    response=JSONResponse({'authenticated':True})
    response.set_cookie(cfg.cookie_name,token,httponly=True,secure=cfg.secure_cookie,samesite='strict',path='/',max_age=cfg.session_hours*3600)
    response.delete_cookie('nd_sso_session',path='/',secure=cfg.secure_cookie,httponly=True,samesite='strict')
    response.delete_cookie(cfg.demo_cookie_name,path='/',secure=cfg.secure_cookie,httponly=True,samesite='strict')
    response.delete_cookie(cfg.identity_cookie_name,path='/',secure=cfg.secure_cookie,httponly=True,samesite='strict')
    return response

@router.get('/me')
def me(request:Request):
    def result(db,a,s):
        branding=db.get(Setting,'branding')
        sso=sso_session(s)
        return {'user':{**serial(a.user),**({'must_change_password':False} if sso else {})},'role':serial(a.role),'org':serial(a.org),'permissions':sorted(a.permissions),
                'csrf':s.csrf,'school_name':(branding.value if branding else {}).get('school_name',''),
                'environment':request.app.state.settings.env,'demo_switch':demo_options(a),
                'sso_session':sso,'identities':identity_choices(db,a,request),
                'primary_role':serial(a.primary_role),'primary_org':serial(a.primary_org)}
    # csrf deliberately returned only here; generic business serial redacts it.
    with request.app.state.sessions.begin() as db:
        a,s=current_actor(db,request,allow_password=True)
        return result(db,a,s)

@router.post('/password')
def change_password(data:Password,request:Request):
    def apply(db,a,s):
        if getattr(a,'demo_controller',None) and a.demo_controller.id!=a.id:
            raise HTTPException(403,'请使用该账号独立登录后修改密码')
        if not verify_password(a.user.password_hash,data.old_password): raise HTTPException(403,'当前密码不正确')
        if data.old_password==data.new_password: raise HTTPException(422,'新密码不能与当前密码相同')
        a.user.password_hash=hash_password(data.new_password);a.user.must_change_password=False
        a.user.auth_version+=1;a.user.version+=1
        db.execute(delete(AuthSession).where(AuthSession.user_id==a.id))
        audit(db,a,'auth',a.id,'本人修改密码',after={'sessions_revoked':True},reason='本人修改登录密码')
        return {'changed':True,'login_required':True}
    result=command(request,data.model_dump(),None,apply,allow_password=True)
    response=JSONResponse(result);response.delete_cookie(request.app.state.settings.cookie_name,path='/',secure=request.app.state.settings.secure_cookie,httponly=True,samesite='strict')
    response.delete_cookie(request.app.state.settings.demo_cookie_name,path='/',secure=request.app.state.settings.secure_cookie,httponly=True,samesite='strict')
    response.delete_cookie(request.app.state.settings.identity_cookie_name,path='/',secure=request.app.state.settings.secure_cookie,httponly=True,samesite='strict')
    return response

@router.post('/logout')
def logout(request:Request):
    from .sso import _cancel_pending_state,_state_cookie
    def apply(db,a,s):
        cancelled=_cancel_pending_state(db,request)
        db.delete(s);audit(db,a,'auth',a.id,'退出登录',after={'pending_sso_cancelled':cancelled},reason='本人退出登录')
        return {'logged_out':True}
    result=command(request,{},None,apply,allow_password=True)
    response=JSONResponse(result);response.delete_cookie(request.app.state.settings.cookie_name,path='/',secure=request.app.state.settings.secure_cookie,httponly=True,samesite='strict')
    response.delete_cookie(request.app.state.settings.demo_cookie_name,path='/',secure=request.app.state.settings.secure_cookie,httponly=True,samesite='strict')
    response.delete_cookie(request.app.state.settings.identity_cookie_name,path='/',secure=request.app.state.settings.secure_cookie,httponly=True,samesite='strict')
    response.delete_cookie(_state_cookie(request.app.state.settings),path='/',secure=request.app.state.settings.secure_cookie,httponly=True,samesite='lax')
    response.delete_cookie('nd_sso_session',path='/',secure=request.app.state.settings.secure_cookie,httponly=True,samesite='strict')
    return response


class DemoSwitch(Input):
    username: str = Field(min_length=1,max_length=64)


@router.post('/demo-switch')
def switch_demo_identity(data:DemoSwitch,request:Request):
    cookie_value=None
    def apply(db,a,s):
        nonlocal cookie_value
        controller=getattr(a,'demo_controller',None)
        if controller is None:
            raise HTTPException(403,'仅授权演示管理员可以切换身份')
        target=target_actor(db,controller,data.username,request,write=True)
        audit(db,controller,'auth',target.id,'切换演示身份',
              before={'username':a.user.username},after={'username':target.user.username,'role':target.role.kind},
              reason='学校现场演示：切换到已授权账号的真实权限范围')
        # Invalidates old-page writes and any previous signed selection.
        s.csrf=secrets.token_urlsafe(32)
        cookie_value=signed_selection(s,target) if target.id!=controller.id else ''
        return {'switched':True,'username':target.user.username,'reload_required':True}
    result=command(request,data.model_dump(),None,apply)
    if cookie_value is None:
        raise HTTPException(409,'该切换已处理，请刷新页面核对当前身份')
    cfg=request.app.state.settings
    response=JSONResponse(result)
    if cookie_value:
        response.set_cookie(cfg.demo_cookie_name,cookie_value,httponly=True,secure=cfg.secure_cookie,
                            samesite='strict',path='/',max_age=cfg.session_hours*3600)
    else:
        response.delete_cookie(cfg.demo_cookie_name,path='/',secure=cfg.secure_cookie,httponly=True,samesite='strict')
    return response


def identity_choices(db,a,request):
    """一人多身份：可切换的身份和各身份待办数，只有一个身份时为空列表。"""
    from ..identities import options,identity_actor
    from .business import _todo_items
    if getattr(a,'demo_controller',None) and a.demo_controller.id!=a.id:return []
    items=options(db,a)
    for x in items:
        try:x['todo_count']=len(_todo_items(db,a if x['current'] else identity_actor(db,a.user,x['id'],request)))
        except HTTPException:x['todo_count']=None;x['unavailable']=True
    return items


class IdentitySwitch(Input):
    identity_id: str = Field(default='',max_length=64)


@router.post('/identity')
def switch_identity(data:IdentitySwitch,request:Request):
    """切换当前身份：同一个人的主身份和兼任身份之间切换，权限按切换后的身份判断。"""
    from ..identities import identity_actor,signed_selection as identity_selection
    cookie_value=None
    def apply(db,a,s):
        nonlocal cookie_value
        if getattr(a,'demo_controller',None) and a.demo_controller.id!=a.id:
            raise HTTPException(403,'演示身份下不能切换兼任身份，请先切回管理员')
        target=identity_actor(db,a.user,data.identity_id,request)
        audit(db,a,'auth',a.id,'切换身份',before={'role':a.role.name,'org':a.org.name},
              after={'role':target.role.name,'role_kind':target.role.kind,'org':target.org.name},reason='本人切换当前办理身份')
        # Invalidates old-page writes made under the previous identity.
        s.csrf=secrets.token_urlsafe(32)
        cookie_value=identity_selection(s,a.user,target.identity_id) if target.identity_id else ''
        return {'switched':True,'role':target.role.name,'org':target.org.name,'reload_required':True}
    result=command(request,data.model_dump(),None,apply)
    if cookie_value is None:
        raise HTTPException(409,'该切换已处理，请刷新页面核对当前身份')
    cfg=request.app.state.settings
    response=JSONResponse(result)
    if cookie_value:
        response.set_cookie(cfg.identity_cookie_name,cookie_value,httponly=True,secure=cfg.secure_cookie,
                            samesite='strict',path='/',max_age=cfg.session_hours*3600)
    else:
        response.delete_cookie(cfg.identity_cookie_name,path='/',secure=cfg.secure_cookie,httponly=True,samesite='strict')
    return response
