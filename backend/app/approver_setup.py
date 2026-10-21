"""按学校返回的《审批人员选定表》一次配好学校级审批职责、学院负责人、教研室负责人。

    python -m app.approver_setup ensure-role [--apply]
    python -m app.approver_setup plan  选定表.xlsx
    python -m app.approver_setup apply 选定表.xlsx --confirm

只增不减：已有的负责人、职责人员、兼任身份都保留，重复执行不会重复添加。
plan 只读，列出将要做的事和发现的问题；apply 在一个事务里全部写入并逐项留审计记录，
有任何错误时整张表都不写。不改审批规则、积分公式和人员主身份。
"""
from __future__ import annotations
import argparse
import json
import re
import uuid
from pathlib import Path
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from .config import Settings
from .core import make_engine, audit
from .models import Org, Role, Setting, User, utcnow
from .permissions import SCHOOL_REVIEW, validate_permissions
from . import identities as idt
from . import social_training as st

ROLE_ID, ROLE_CODE, ROLE_NAME = 'role-school-review', 'school_review', '学校业务审核'
REASON = '按学校返回的审批人员选定表配置'
SCHOOL_SHEET, COLLEGE_SHEET, DEPT_SHEET = '1学校级审批人员', '2学院负责人选定', '3教研室负责人选定'
# 选定表里的职责名称 → 系统职责代码（DUTIES 里的名称可能带部门括注，按开头匹配）
DUTY_BY_LABEL = {label.split('（')[0]: code for code, label in st.DUTIES.items()}
STAFF_NO = re.compile(r'[（(]\s*([0-9A-Za-z]+)\s*[)）]\s*$')


def review_role(db):
    return db.get(Role, ROLE_ID) or db.scalar(select(Role).where(Role.code == ROLE_CODE))


def ensure_role(db, actor, plan):
    """建好“学校业务审核”角色；已存在时只补齐，不收回已有权限。"""
    role = review_role(db)
    wanted = sorted(SCHOOL_REVIEW)
    if role is None:
        plan['actions'].append('新建角色“学校业务审核”（学校类型，%d 项业务权限，不含系统管理）' % len(wanted))
        role = Role(id=ROLE_ID, code=ROLE_CODE, name=ROLE_NAME, kind='school', permissions=wanted, active=True)
        db.add(role)
        db.flush()
        audit(db, actor, 'roles', role.id, '新建学校业务审核角色', after={'name': ROLE_NAME, 'permissions': wanted}, reason=REASON)
        return role
    if role.kind != 'school' or not validate_permissions(role.kind, role.permissions):
        raise RuntimeError('已有的“学校业务审核”角色配置无效，请在角色与授权里核对')
    if set(role.permissions) & {'users.manage', 'roles.manage', 'settings.manage'}:
        raise RuntimeError('已有的“学校业务审核”角色带系统管理权限，不能作为兼任身份，请先在角色与授权里去掉')
    if not role.active:
        raise RuntimeError('“学校业务审核”角色已停用，请先启用')
    return role


def staff_no_of(value):
    text = str(value or '').strip()
    if not text:
        return None
    m = STAFF_NO.search(text)
    if m:
        return m.group(1)
    m = re.search(r'([0-9]{4,})', text)
    return m.group(1) if m else ''


def read_table(path):
    from openpyxl import load_workbook
    wb = load_workbook(path, read_only=True, data_only=True)
    for name in (SCHOOL_SHEET, COLLEGE_SHEET, DEPT_SHEET):
        if name not in wb.sheetnames:
            raise RuntimeError('选定表缺少工作表：' + name)
    def rows(name):
        return [list(r) for r in wb[name].iter_rows(min_row=2, values_only=True) if r and r[1]]
    return rows(SCHOOL_SHEET), rows(COLLEGE_SHEET), rows(DEPT_SHEET)


def people(row, plan, where):
    out = []
    for cell in row[4:7]:
        no = staff_no_of(cell)
        if no is None:
            continue
        if not no:
            plan['errors'].append(f'{where}：“{cell}”里没有工号，请写成“姓名（工号）”')
            continue
        out.append((no, str(cell).strip()))
    if row[7] not in (None, ''):
        plan['notes'].append(f'{where} 备注：{row[7]}')
    return out


def find_user(db, no, text, plan, where):
    users = db.scalars(select(User).where(User.staff_no == no)).all()
    if len(users) != 1:
        plan['errors'].append(f'{where}：工号 {no}（{text}）在平台里{"找不到" if not users else "有重名"}')
        return None
    u = users[0]
    if not u.active or u.authorization_pending:
        plan['errors'].append(f'{where}：{u.name}（{no}）账号停用或授权待确认')
        return None
    return u


def build(db, actor, school_rows, college_rows, dept_rows, plan):
    from .routes.admin import head_role, org_members
    role = ensure_role(db, actor, plan)
    orgs = {o.name: o for o in db.scalars(select(Org).where(Org.active.is_(True)))}
    school = db.scalar(select(Org).where(Org.kind == 'school', Org.parent_id.is_(None)))
    extras = idt.all_extras(db, lock=True)
    assignments = {k: list(v) for k, v in st.assignments(db).items()}
    heads = idt.org_heads(db)
    changed_users = set()

    def add_extra(user, role_obj, org, label, where):
        mine = [x for x in extras if x['user_id'] == user.id]
        if (user.role_id, user.org_id) == (role_obj.id, org.id) or any((x['role_id'], x['org_id']) == (role_obj.id, org.id) and not idt.expired(x) for x in mine):
            return False
        # 同一职务以前的临时兼任已到期：换成这次新设的，不留重复（与“设置负责人”一致）
        for x in [x for x in mine if (x['role_id'], x['org_id']) == (role_obj.id, org.id)]:
            extras.remove(x)
        if len([x for x in extras if x['user_id'] == user.id]) >= idt.MAX_EXTRA_PER_USER:
            plan['errors'].append(f'{where}：{user.name} 的兼任身份已达 {idt.MAX_EXTRA_PER_USER} 个上限')
            return False
        idt.validate_extra(db, user, role_obj.id, org.id, user.staff_no)
        extras.append({'id': str(uuid.uuid4()), 'user_id': user.id, 'role_id': role_obj.id, 'org_id': org.id,
                       'granted_by': actor.id, 'granted_at': utcnow().isoformat(timespec='seconds'), 'reason': REASON})
        changed_users.add(user.id)
        plan['actions'].append(f'{label}：{user.name}（{user.staff_no}）')
        return True

    def has_school_review(user):
        if user.is_admin:
            return True
        primary = db.get(Role, user.role_id)
        if primary and primary.kind == 'school' and 'assessment.review' in primary.permissions:
            return True
        return any(x['user_id'] == user.id and x['role_id'] == role.id and not idt.expired(x) for x in extras)

    def assign(code, user, where):
        ids = assignments.setdefault(code, [])
        if user.id in ids:
            return
        ids.append(user.id)
        plan['actions'].append(f'审批职责“{st.DUTIES[code]}”加入：{user.name}（{user.staff_no}）')

    # 学校级审批职责
    for row in school_rows:
        label = str(row[1]).strip()
        code = DUTY_BY_LABEL.get(label)
        if not code:
            plan['errors'].append(f'学校级审批人员：不认识的职责“{label}”')
            continue
        found = people(row, plan, '学校级·' + label)
        if found and len(found) < 2:
            plan['warnings'].append(f'学校级·{label} 只有 1 人，此人回避时这一环节无人可办')
        for no, text in found:
            user = find_user(db, no, text, plan, '学校级·' + label)
            if user is None:
                continue
            if not has_school_review(user):
                add_extra(user, role, school, '增加“学校业务审核”兼任身份（老师身份保留）', '学校级·' + label)
            assign(code, user, '学校级·' + label)

    # 学院、教研室负责人
    for rows, kind, sheet in ((college_rows, 'college', '学院负责人'), (dept_rows, 'dept', '教研室负责人')):
        for row in rows:
            name = str(row[1]).strip()
            org = orgs.get(name)
            where = f'{sheet}·{name}'
            if org is None or org.kind != kind:
                plan['errors'].append(f'{where}：平台里没有这个{"学院" if kind == "college" else "教研室"}')
                continue
            found = people(row, plan, where)
            if not found:
                continue
            head = head_role(db, org)
            members = set(db.scalars(org_members(db, org).with_only_columns(User.id)))
            current = {h['user_id'] for h in heads.get(org.id, [])}
            for no, text in found:
                user = find_user(db, no, text, plan, where)
                if user is None:
                    continue
                if user.id not in members:
                    plan['errors'].append(f'{where}：{user.name}（{no}）不是本单位在职人员，负责人只能从本单位选')
                    continue
                if user.id in current:
                    plan['skipped'].append(f'{where}：{user.name} 已经是负责人')
                elif add_extra(user, head, org, f'设为{name}{"负责人" if kind == "college" else "负责人（教研室）"}', where):
                    audit(db, actor, 'organization', org.id, '设置负责人', after={'user_id': user.id, 'name': user.name,
                          'staff_no': user.staff_no, 'role': head.name, 'org': org.name}, reason=REASON)
                if kind == 'college' and str(row[8] if len(row) > 8 else '').strip() == '是':
                    assign('dean', user, where)

    before = st.assignments(db)
    if assignments != before:
        setting = db.get(Setting, 'social_training_duties')
        if setting is None:
            setting = Setting(key='social_training_duties', value=assignments, version=1)
            db.add(setting)
        else:
            setting.value = assignments
            setting.version += 1
        db.flush()
    idt.save_extras(db, extras)
    for uid in changed_users:
        u = db.get(User, uid)
        u.version += 1
        audit(db, actor, 'users', uid, '调整兼任身份', after={'identities': [x for x in extras if x['user_id'] == uid]}, reason=REASON)
    # 职责人员须能真正办理：写入后按系统原规则逐一复核（与“配置审批职责”页面一致）
    db.flush()
    for code, ids in assignments.items():
        for uid in ids:
            u = db.get(User, uid)
            if not st.duty_eligible(db, u, actor, code):
                plan['errors'].append(f'审批职责“{st.DUTIES[code]}”：{u.name if u else uid} 没有能办理的审核身份')
    if assignments != before:
        audit(db, actor, 'social_duties', 'social_training_duties', '配置社会培训职责', {'value': before}, {'value': assignments}, REASON)
    plan['duties'] = {st.DUTIES[k]: len(v) for k, v in assignments.items()}


def admin_actor(db):
    admin = db.scalar(select(User).where(User.is_admin.is_(True), User.active.is_(True)).order_by(User.created_at))
    if admin is None:
        raise RuntimeError('没有可用的系统管理员账号')
    return idt.identity_actor(db, admin, None)


def run(cfg, cmd, path=None, apply=False):
    plan = {'actions': [], 'skipped': [], 'warnings': [], 'errors': [], 'notes': []}
    engine = make_engine(cfg.database_url)
    try:
        with Session(engine) as db:
            try:
                actor = admin_actor(db)
                if cmd == 'ensure-role':
                    ensure_role(db, actor, plan)
                else:
                    school_rows, college_rows, dept_rows = read_table(path)
                    build(db, actor, school_rows, college_rows, dept_rows, plan)
            except HTTPException as exc:
                plan['errors'].append(str(exc.detail))
            if apply and not plan['errors']:
                db.commit()
                plan['status'] = 'APPLIED'
            else:
                db.rollback()
                plan['status'] = 'BLOCKED' if plan['errors'] else 'PLAN_ONLY'
    finally:
        engine.dispose()
    return plan


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='cmd', required=True)
    e = sub.add_parser('ensure-role')
    e.add_argument('--apply', action='store_true')
    sub.add_parser('plan').add_argument('table')
    a = sub.add_parser('apply')
    a.add_argument('table')
    a.add_argument('--confirm', action='store_true', required=True)
    args = p.parse_args()
    table = getattr(args, 'table', None)
    if table and not Path(table).is_file():
        raise SystemExit('找不到选定表：' + table)
    try:
        plan = run(Settings(), args.cmd, table, apply=args.cmd == 'apply' or getattr(args, 'apply', False))
    except RuntimeError as exc:
        plan = {'status': 'BLOCKED', 'errors': [str(exc)]}
    print(json.dumps(plan, ensure_ascii=False, indent=1))
    raise SystemExit(0 if plan['status'] != 'BLOCKED' else 2)


if __name__ == '__main__':
    main()
