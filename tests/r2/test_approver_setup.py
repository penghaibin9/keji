"""按选定表一次配好学校级审批职责与学院、教研室负责人（隔离合成数据）。"""
import pytest
from fastapi import HTTPException
from openpyxl import Workbook
from app import approver_setup as setup, identities as idt, social_training as st
from app.models import User, Role
from conftest import auth

HDR = ['序号', '名称', '业务', '单位或现任', '人员一', '人员二', '人员三', '备注', '院长初审']


def table(path, school=(), college=(), dept=()):
    wb = Workbook()
    wb.active.title = '填写说明'
    for name, rows in ((setup.SCHOOL_SHEET, school), (setup.COLLEGE_SHEET, college), (setup.DEPT_SHEET, dept)):
        w = wb.create_sheet(name)
        w.append(HDR)
        for i, row in enumerate(rows, 1):
            w.append([i, *row])
    wb.save(path)
    return path


def plan_and_apply(app2, path, apply=True):
    school, college, dept = setup.read_table(path)
    plan = {'actions': [], 'skipped': [], 'warnings': [], 'errors': [], 'notes': []}
    with app2.state.sessions() as db:
        setup.build(db, setup.admin_actor(db), school, college, dept, plan)
        (db.commit if apply and not plan['errors'] else db.rollback)()
    return plan


def add_teacher(app2, ident, staff, org):
    with app2.state.sessions.begin() as db:
        hashed = db.get(User, 'teacher').password_hash
        db.add(User(id=ident, username=ident, name='合成教师' + staff, staff_no=staff, org_id=org, role_id='role-teacher',
                    password_hash=hashed, active=True, must_change_password=False))


def test_table_sets_school_duties_heads_and_dean_keeping_teacher_identity(app2, client2, tmp_path):
    add_teacher(app2, 'teacher3', 'J003', 'dept1')
    path = table(tmp_path / 't.xlsx',
                 school=[('归口学院复审', '复审', '单位', '学校｜测试教师一（J001）', '学校｜测试教师二（J002）', '', '', '')],
                 college=[('测试学院一', '学院审批', '（无）', '测试学院一｜合成教师J003（J003）', '', '', '', '是')],
                 dept=[('测试教研室一', '教研室审核', '（无）', '测试教研室一｜测试教师一（J001）', '', '', '有两个教研室', '')])
    plan = plan_and_apply(app2, path, apply=False)
    assert plan['errors'] == [] and any('学校业务审核' in x for x in plan['actions'])
    with app2.state.sessions() as db:  # 预览不写入
        assert setup.review_role(db) is None and st.assignments(db) == {}
    plan = plan_and_apply(app2, path)
    assert plan['errors'] == [] and plan['notes'] == ['教研室负责人·测试教研室一 备注：有两个教研室']
    with app2.state.sessions() as db:
        role = setup.review_role(db)
        assert role.kind == 'school' and not set(role.permissions) & {'users.manage', 'roles.manage', 'settings.manage', 'audit.read'}
        teacher = db.get(User, 'teacher')
        assert teacher.role_id == 'role-teacher'  # 主身份仍是老师
        kinds = {(db.get(Role, x['role_id']).kind, x['org_id']) for x in idt.extras_for(db, 'teacher')}
        assert kinds == {('school', 'school'), ('dept', 'dept1')}
        duties = st.assignments(db)
        assert set(duties['coordinator']) == {'teacher', 'otherteacher'} and duties['dean'] == ['teacher3']
        admin = setup.admin_actor(db)
        assert st.duty_eligible(db, teacher, admin, 'coordinator') and st.duty_eligible(db, db.get(User, 'teacher3'), admin, 'dean')
        assert {h['user_id'] for h in idt.org_heads(db).get('college1', [])} >= {'teacher3'}
    # 再跑一遍不重复添加
    again = plan_and_apply(app2, path)
    assert again['errors'] == [] and again['actions'] == []
    # 新增的身份登录后能切换使用
    me = auth(client2, 'teacher')
    assert me['role']['kind'] == 'teacher'


def test_table_blocks_wrong_unit_unknown_staff_and_writes_nothing(app2, tmp_path):
    path = table(tmp_path / 'bad.xlsx',
                 school=[('不存在的职责', '', '', '某人（J001）', '', '', '', '')],
                 college=[('测试学院一', '', '', '测试学院二｜测试教师二（J002）', '查无此人（Z999）', '没写工号', '', '')])
    plan = plan_and_apply(app2, path)
    assert len(plan['errors']) == 4
    assert any('不认识的职责' in x for x in plan['errors']) and any('不是本单位在职人员' in x for x in plan['errors'])
    assert any('Z999' in x for x in plan['errors']) and any('没有工号' in x for x in plan['errors'])
    with app2.state.sessions() as db:
        assert setup.review_role(db) is None and idt.all_extras(db) == [] and st.assignments(db) == {}


def test_only_school_roles_without_system_permissions_can_be_extra(app2):
    with app2.state.sessions() as db:
        teacher = db.get(User, 'teacher')
        with pytest.raises(HTTPException):
            idt.validate_extra(db, teacher, 'role-school', 'school', teacher.staff_no)
        role = setup.ensure_role(db, setup.admin_actor(db), {'actions': []})
        org, got = idt.validate_extra(db, teacher, role.id, 'school', teacher.staff_no)
        assert got.id == setup.ROLE_ID and org.id == 'school'
        db.rollback()
