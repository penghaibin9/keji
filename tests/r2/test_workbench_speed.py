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


def _tables(engine,extra_index=None):
    meta=sa.MetaData()
    audit=sa.Table('audit_events',meta,sa.Column('id',sa.String(36),primary_key=True),sa.Column('result',sa.String(30)),sa.Column('created_at',sa.DateTime))
    sa.Table('inbound_batches',meta,sa.Column('id',sa.String(36),primary_key=True),sa.Column('created_at',sa.DateTime))
    meta.create_all(engine)
    if extra_index:
        sa.Index(extra_index,audit.c.result,audit.c.created_at).create(engine)


def _names(engine,table):
    return sorted(x['name'] for x in sa.inspect(engine).get_indexes(table))


def test_index_migration_is_repeatable_and_accepts_hand_built_indexes():
    module=_migration()
    fresh=sa.create_engine('sqlite://');_tables(fresh)
    _run_upgrade(fresh,module);_run_upgrade(fresh,module)
    assert _names(fresh,'audit_events')==['ix_audit_created_desc_id','ix_audit_result_time']
    assert _names(fresh,'inbound_batches')==['ix_inbound_batches_created_desc_id']
    # 服务器上已经按别的名字手工建过同样的索引：改成契约规定的名字，不能跳过（校验按名字比对）。
    manual=sa.create_engine('sqlite://');_tables(manual,'ix_audit_events_result_created')
    _run_upgrade(manual,module)
    assert _names(manual,'audit_events')==['ix_audit_created_desc_id','ix_audit_result_time']


def test_mysql_hand_built_index_is_renamed_not_skipped(monkeypatch):
    module=_migration()
    statements=[]
    class Bind:
        class dialect:name='mysql'
    class Inspector:
        def get_indexes(self,table):
            return [{'name':'ix_audit_events_result_created','column_names':['result','created_at'],'unique':0}] if table=='audit_events' else []
    monkeypatch.setattr(module.sa,'inspect',lambda bind:Inspector())
    monkeypatch.setattr(module.op,'execute',lambda statement:statements.append(str(statement)),raising=False)
    monkeypatch.setattr(module.op,'create_index',lambda *args,**kwargs:statements.append('CREATE '+args[0]),raising=False)
    monkeypatch.setattr(module.op,'get_bind',lambda:Bind(),raising=False)
    module.upgrade()
    assert statements[0]=='ALTER TABLE `audit_events` RENAME INDEX `ix_audit_events_result_created` TO `ix_audit_result_time`'
    assert statements[1:]==['CREATE ix_audit_created_desc_id','CREATE ix_inbound_batches_created_desc_id']


def test_contract_lists_all_three_new_indexes():
    from app.installation import CONTRACT_PATH
    import json
    tables=json.loads(CONTRACT_PATH.with_name('audit_index_schema.json').read_text(encoding='utf-8'))['tables']
    names={x[0] for t in tables.values() for x in t['indexes']}
    assert {'ix_audit_result_time','ix_audit_created_desc_id','ix_inbound_batches_created_desc_id'}<=names


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


def test_staff_roster_looks_up_each_hr_unit_once(app2):
    from sqlalchemy import select
    with Session(app2.state.engine) as db:
        for i in range(30):
            db.add(rd.TeacherHrProfile(staff_no=f'RS{i:03d}',name=f'教职工{i}',org_code='dept1',active=True))
        db.commit()
        count=[0]
        def tick(*a,**k):count[0]+=1
        event.listen(app2.state.engine,'before_cursor_execute',tick)
        try:
            roster=rd.staff_roster(db,db.scalars(select(rd.TeacherHrProfile)).all(),school_year='2025-2026',private=False)
        finally:
            event.remove(app2.state.engine,'before_cursor_execute',tick)
    assert len(roster)>=30
    assert count[0]<15,count[0]     # 以前每位教职工至少查一次单位


def test_latest_task_ids_scans_tasks_once_for_all_connections(app2):
    from app.integration_status import latest_task_ids
    from app.models import Connection,Task
    from datetime import timedelta
    from app.core import utcnow
    with app2.state.sessions.begin() as db:
        ids=[c.id for c in db.scalars(sa.select(Connection).order_by(Connection.code))]
        assert len(ids)>=2
        for n,cid in enumerate(ids):
            for k in range(2):
                db.add(Task(id=f'lt-{n}-{k}',key=f'lt-{n}-{k}',kind='sync' if k else 'inbound_pull',state='DONE',owner_id='schooladmin',
                            payload={'connection_id':cid,'data_type':'course' if k else 'teacher_hr'},result={},
                            created_at=utcnow()-timedelta(minutes=10-k-n)))
        db.flush()
        count=[0]
        def tick(*args,**kwargs):count[0]+=1
        event.listen(db.get_bind(),'before_cursor_execute',tick)
        try:
            latest=latest_task_ids(db,ids)
            only=latest_task_ids(db,ids,'teacher_hr')
        finally:
            event.remove(db.get_bind(),'before_cursor_execute',tick)
    assert count[0]==2
    assert {latest[c] for c in ids}=={f'lt-{n}-1' for n in range(len(ids))}
    assert {only[c] for c in ids}=={f'lt-{n}-0' for n in range(len(ids))}


def test_inbound_retention_compacts_old_settled_batches_only(app2):
    from datetime import timedelta
    from app.core import utcnow
    from app.inbound_retention import compact
    from app.models import Connection
    from app.reference_data import InboundBatch,InboundRow
    with app2.state.sessions.begin() as db:
        cid=db.scalar(sa.select(Connection.id).order_by(Connection.code))
        def batch(name,state,days):
            db.add(InboundBatch(id=name,connection_id=cid,owner_id='schooladmin',data_type='course',state=state,total=2,errors=0,
                                created_at=utcnow()-timedelta(days=days)))
            db.flush()
            for n in range(2):
                db.add(InboundRow(batch_id=name,row_no=n,business_key=f'{name}-{n}',raw={'a':1},mapped={'b':2},errors=[]))
        batch('ret-old1','COMMITTED',200);batch('ret-old2','COMMITTED',150);batch('ret-old3','VOID',120)
        batch('ret-new','COMMITTED',5);batch('ret-prev','PREVIEW',300)
        db.flush()
        dry=compact(db,90,keep_latest=1)
        assert dry=={'batches':3,'rows':6,'applied':False}  # the newest settled batch (ret-new) is kept; PREVIEW is never touched
        assert db.scalar(sa.select(InboundRow.raw).where(InboundRow.batch_id=='ret-old1',InboundRow.row_no==0))=={'a':1}
        done=compact(db,90,keep_latest=1,apply=True)
        assert done['rows']==6
        db.flush()
        row=db.scalars(sa.select(InboundRow).where(InboundRow.batch_id=='ret-old1').order_by(InboundRow.row_no)).first()
        db.refresh(row)
        assert row.raw=={'_compacted':True} and row.mapped=={} and row.business_key=='ret-old1-0'
        assert db.scalar(sa.select(InboundRow.raw).where(InboundRow.batch_id=='ret-new',InboundRow.row_no==0))=={'a':1}
        assert db.scalar(sa.select(InboundRow.raw).where(InboundRow.batch_id=='ret-prev',InboundRow.row_no==0))=={'a':1}
        assert compact(db,90,keep_latest=1,apply=True)['rows']==0


def test_keep_latest_pull_compacts_everything_older_whatever_its_age(app2):
    import pytest
    from datetime import timedelta
    from app.core import utcnow
    from app.inbound_retention import compact,main
    from app.models import Connection
    from app.reference_data import InboundBatch,InboundRow
    with app2.state.sessions.begin() as db:
        cid=db.scalar(sa.select(Connection.id).order_by(Connection.code))
        def batch(name,state,hours,pull,data_type='course'):
            db.add(InboundBatch(id=name,connection_id=cid,owner_id='schooladmin',data_type=data_type,state=state,total=1,errors=0,
                                receipt={'pull_task_id':pull} if pull else {},created_at=utcnow()-timedelta(hours=hours)))
            db.flush()
            db.add(InboundRow(batch_id=name,row_no=0,business_key=name,raw={'a':1},mapped={'b':2},errors=[]))
        # 最新一次全量拉取分成两页（两个批次），更早一次拉取也只有几小时前
        batch('lp-new-a','COMMITTED',1,'pull-2');batch('lp-new-b','COMMITTED',1.5,'pull-2')
        batch('lp-old-a','COMMITTED',20,'pull-1');batch('lp-old-void','VOID',30,'pull-0');batch('lp-nopull','COMMITTED',40,None)
        batch('lp-pending','PREVIEW',50,'pull-9')  # 待确认的不动
        batch('lp-other','COMMITTED',60,'pull-7','teacher_hr')  # 另一种数据只有一次，保留
        db.flush()
        dry=compact(db,0,latest_pull_only=True)
        assert dry=={'batches':3,'rows':3,'applied':False}
        assert compact(db,0,latest_pull_only=True,apply=True)['rows']==3
        db.flush()
        raw=lambda name:db.scalar(sa.select(InboundRow.raw).where(InboundRow.batch_id==name))
        assert raw('lp-old-a')=={'_compacted':True} and raw('lp-old-void')=={'_compacted':True} and raw('lp-nopull')=={'_compacted':True}
        assert raw('lp-new-a')=={'a':1} and raw('lp-new-b')=={'a':1} and raw('lp-pending')=={'a':1} and raw('lp-other')=={'a':1}
    with pytest.raises(SystemExit):main(['--keep-latest-pull','--older-than-days','40'])
    with pytest.raises(SystemExit):main(['--older-than-days','0'])
