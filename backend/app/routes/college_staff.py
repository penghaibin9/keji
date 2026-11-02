"""本院人员授权：院长（学院负责人）自己指定本院学院经办人和各教研室负责人。

只有当前身份是该学院在任院长的人能用（经办人、教研室负责人不能再往下指定）；学校管理员在组织页仍可兜底调整。
经办人代院长办理学院一级的全部审批，记录写明“经办人代 某院长 办理”，见 identities.py。
"""
from fastapi import APIRouter, Request, HTTPException
from sqlalchemy import select
from ..core import *
from ..schemas import CollegeStaffIn
from ..identities import org_heads, agent_item, MAX_AGENTS_PER_COLLEGE
from .admin import add_head, remove_head, org_members, filters_from

router = APIRouter(prefix='/api/college', tags=['本院人员授权'])


def require_dean(db, a):
    """当前身份须是本学院在任院长（不是经办人）。返回学院。"""
    org = a.org
    if a.role.kind != 'college' or org is None or org.kind != 'college' or agent_item(db, a) is not None:
        raise HTTPException(403, '只有学院院长（学院负责人）本人可以指定本院经办人和教研室负责人')
    if not any(h['user_id'] == a.id and h['usable'] and not h['agent'] for h in org_heads(db).get(org.id, [])):
        raise HTTPException(403, '你不是本学院在任的院长（学院负责人），请联系学校管理员')
    return org


def _dept(db, college, org_id):
    dept = db.get(Org, org_id) if org_id else None
    if dept is None or dept.kind != 'dept' or dept.parent_id != college.id or not dept.active:
        raise HTTPException(404, '只能设置本学院下属教研室的负责人')
    return dept


def _row(h):
    return {k: h.get(k) for k in ('user_id', 'name', 'staff_no', 'primary', 'usable', 'valid_until', 'granted_at', 'delegated_by')}


@router.get('/staff')
def staff(request: Request):
    def load(db, a, s):
        college = require_dean(db, a)
        heads = org_heads(db)
        mine = heads.get(college.id, [])
        names = {h['user_id']: h['name'] for h in mine}
        depts = db.scalars(select(Org).where(Org.parent_id == college.id, Org.kind == 'dept', Org.active.is_(True)).order_by(Org.code)).all()
        return {'college': {'id': college.id, 'name': college.name}, 'max_agents': MAX_AGENTS_PER_COLLEGE,
                'deans': [_row(h) for h in mine if not h['agent']],
                'agents': [{**_row(h), 'delegated_by_name': names.get(h['delegated_by'], '')} for h in mine if h['agent']],
                'depts': [{'id': d.id, 'name': d.name, 'heads': [_row(h) for h in heads.get(d.id, [])]} for d in depts]}
    return read_operation(request, 'assessment.review', load)


@router.get('/staff/candidates')
def candidates(request: Request):
    f, _, _ = filters_from(request, {'q', 'org_id'})
    def load(db, a, s):
        college = require_dean(db, a)
        org = _dept(db, college, f['org_id']) if f.get('org_id') and f['org_id'] != college.id else college
        q = org_members(db, org)
        if f.get('q'):
            q = q.where(User.name.contains(f['q'], autoescape=True) | User.staff_no.contains(f['q'], autoescape=True))
        names = {o.id: o.name for o in db.scalars(select(Org))}
        return {'items': [{'id': u.id, 'name': u.name, 'staff_no': u.staff_no, 'title': u.title, 'org_name': names.get(u.org_id, ''),
                           'authorization_pending': u.authorization_pending} for u in db.scalars(q.order_by(User.staff_no).limit(30))]}
    return read_operation(request, 'assessment.review', load)


@router.post('/agents')
def add_agent(data: CollegeStaffIn, request: Request):
    def apply(db, a, s):
        college = require_dean(db, a)
        return add_head(db, a, college, data.user_id, data.valid_until, data.reason, agent_of=a.id)
    return command(request, data.model_dump(), 'assessment.review', apply)


@router.post('/agents/remove')
def remove_agent(data: CollegeStaffIn, request: Request):
    def apply(db, a, s):
        college = require_dean(db, a)
        return remove_head(db, a, college, data.user_id, data.reason, agent=True)
    return command(request, data.model_dump(), 'assessment.review', apply)


@router.post('/dept-heads')
def add_dept_head(data: CollegeStaffIn, request: Request):
    def apply(db, a, s):
        college = require_dean(db, a)
        return add_head(db, a, _dept(db, college, data.org_id), data.user_id, data.valid_until, data.reason)
    return command(request, data.model_dump(), 'assessment.review', apply)


@router.post('/dept-heads/remove')
def remove_dept_head(data: CollegeStaffIn, request: Request):
    def apply(db, a, s):
        college = require_dean(db, a)
        return remove_head(db, a, _dept(db, college, data.org_id), data.user_id, data.reason, agent=False)
    return command(request, data.model_dump(), 'assessment.review', apply)
