"""权限清单：每个账号的每个身份（主身份、长期兼任、临时兼任）一行，供学校做权限复核留档。"""
from __future__ import annotations
from sqlalchemy import select
from .models import User, Role, Org
from .identities import all_extras, expired
from .excel_io import rows_to_xlsx

HEADERS = ['登录账号', '姓名', '工号', '账号状态', '系统管理员', '授权待确认', '身份类型', '角色', '组织', '组织层级', '到期日', '权限点', '授权人', '授权时间']
KIND = {'school': '学校', 'college': '二级学院', 'dept': '教研室'}


def rows(db):
    roles = {r.id: r for r in db.scalars(select(Role))}
    orgs = {o.id: o for o in db.scalars(select(Org))}
    users = list(db.scalars(select(User).order_by(User.username)))
    names = {u.id: u.name for u in users}
    by_user = {}
    for x in all_extras(db, include_expired=True):
        by_user.setdefault(x['user_id'], []).append(x)

    def line(u, kind, role, org, until='', by='', at=''):
        return [u.username, u.name, u.staff_no or '', '启用' if u.active else '停用', '是' if u.is_admin else '', '是' if u.authorization_pending else '',
                kind, role.name if role else '（角色已删除）', org.name if org else '（组织已删除）', KIND.get(org.kind, org.kind) if org else '',
                until, '、'.join(sorted(role.permissions or [])) if role else '', by, at]

    out = []
    for u in users:
        out.append(line(u, '主身份', roles.get(u.role_id), orgs.get(u.org_id)))
        for x in sorted(by_user.get(u.id, []), key=lambda e: e.get('granted_at', '')):
            until = x.get('valid_until') or ''
            kind = ('临时兼任（已到期）' if expired(x) else '临时兼任') if until else '长期兼任'
            out.append(line(u, kind, roles.get(x['role_id']), orgs.get(x['org_id']), until, names.get(x.get('granted_by'), x.get('granted_by') or ''), x.get('granted_at', '')))
    return out


def workbook(db):
    return rows_to_xlsx(HEADERS, rows(db), '权限清单')
