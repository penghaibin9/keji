"""工作总览/统一待办变慢的修复：不逐个老师查库、安全提示只做必要查询、授课认定汇总按数据指纹缓存、审计索引迁移可重复执行。"""
import importlib.util
from pathlib import Path
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import event
from sqlalchemy.orm import Session
from app.models import Assessment, Rule, User
import app.reference_data as rd
from conftest import auth


def _migration():
    path=Path(__file__).resolve().parents[2]/'backend/alembic/versions/20261013_0005_audit_result_index.py'
    spec=importlib.util.spec_from_file_location('audit_index_migration',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def _run_upgrade(engine,module):
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()


def _audit_table(engine,extra_index=None):
    meta=sa.MetaData()
    table=sa.Table('audit_events',meta,sa.Column('id',sa.String(36),primary_key=True),sa.Column('result',sa.String(30)),sa.Column('created_at',sa.DateTime))
    meta.create_all(engine)
    if extra_index:
        sa.Index(extra_index,table.c.result,table.c.created_at).create(engine)


def test_audit_index_migration_is_repeatable_and_accepts_a_hand_built_index():
    module=_migration()
    fresh=sa.create_engine('sqlite://');_audit_table(fresh)
    _run_upgrade(fresh,module);_run_upgrade(fresh,module)
    names=[x['name'] for x in sa.inspect(fresh).get_indexes('audit_events')]
    assert names==['ix_audit_result_time']
    # 服务器上已经按别的名字手工建过同样的索引：不再重复建。
    manual=sa.create_engine('sqlite://');_audit_table(manual,'ix_manual_result_created')
    _run_upgrade(manual,module)
    assert [x['name'] for x in sa.inspect(manual).get_indexes('audit_events')]==['ix_manual_result_created']


def test_todo_queries_do_not_grow_with_the_number_of_teachers(client2,app2):
    with app2.state.sessions.begin() as db:
        db.add(Rule(id='speed-rule',kind='assessment',name='速度测试规则',version_no=1,period_id='period2026',config={'components':[]},
                    fingerprint='e'*64,state='ACTIVE',created_by='schooladmin',reason='测试'))
        db.flush()
        template=db.get(User,'otherteacher')
        for i in range(40):
            db.add(User(id=f'sp{i}',username=f'sp{i}',name=f'速度教师{i}',staff_no=f'SP{i:03d}',org_id='dept2' if i%2 else 'dept1',
                        role_id=template.role_id,password_hash=template.password_hash,active=True))
            db.flush()
            db.add(Assessment(id=f'sp-a{i}',teacher_id=f'sp{i}',period_id='period2026',rule_id='speed-rule',score=80,detail=[],source_snapshot={},
                              state=['DEPARTMENT','COLLEGE','SCHOOL'][i%3],version=1))
    auth(client2,'schooladmin')
    count=[0]
    def tick(*args,**kwargs):count[0]+=1
    event.listen(app2.state.engine,'before_cursor_execute',tick)
    try:
        response=client2.get('/api/todos?size=100')
    finally:
        event.remove(app2.state.engine,'before_cursor_execute',tick)
    assert response.status_code==200,response.text
    assert sum(1 for x in response.json()['items'] if x['type']=='assessment')>=13
    assert count[0]<60,count[0]   # 以前每位教师至少查两次库


def test_credit_groups_are_cached_until_the_data_changes(app2):
    rd._CREDIT_CACHE.update(key=None,at=0.0,groups=[])
    with Session(app2.state.engine) as db:
        db.add(rd.TeacherHrProfile(staff_no='CACHE1',user_id='teacher',name='测试教师一',org_code='dept1'))
        db.add(rd.TeacherCourseTerm(external_key='JW|CACHE1|C1|2024-2025-1',origin='JW',staff_no='CACHE1',user_id='teacher',teacher_name='测试教师一',
                                    course_code='C1',course_name='课程一',term_name='2024-2025-1',credit=2,hours=32))
        db.commit()
        first=rd.all_credit_groups(db)
        assert rd.all_credit_groups(db) is first          # 数据没变：直接用缓存
        db.add(rd.TeacherCourseTerm(external_key='JW|CACHE1|C2|2024-2025-1',origin='JW',staff_no='CACHE1',user_id='teacher',teacher_name='测试教师一',
                                    course_code='C2',course_name='课程二',term_name='2024-2025-1',credit=3,hours=48))
        db.commit()
        second=rd.all_credit_groups(db)
        assert second is not first
        assert [g['courses'] for g in second if g['staff_no']=='CACHE1']==[2]


def test_batch_status_reads_three_receipt_values_without_loading_the_receipt(app2):
    from sqlalchemy import select
    with Session(app2.state.engine) as db:
        from app.models import Connection
        cid=db.scalar(select(Connection.id).limit(1))
        db.add(rd.InboundBatch(id='fat-batch',connection_id=cid,data_type='teacher_hr',owner_id='schooladmin',total=3,errors=0,state='COMMITTED',
            receipt={'written':3,'pull_task_id':'t-1','committed_at':'2026-10-13T08:00:00','rows':['x'*1000]*50}))
        db.commit()
        facts=rd.batch_facts(db,'fat-batch')
        assert (facts.state,facts.total,facts.errors,facts.connection_id)==('COMMITTED',3,0,cid)
        assert facts.receipt=={'written':3,'pull_task_id':'t-1','committed_at':'2026-10-13T08:00:00'}
        assert rd.batch_facts(db,'missing') is None
        assert 'fat-batch' not in [getattr(x,'id',None) for x in db.identity_map.values()]   # 没有把整行读进会话
