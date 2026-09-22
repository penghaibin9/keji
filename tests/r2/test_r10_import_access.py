"""Current-scope authorization of import previews/receipts; synthetic SQLite only."""
import copy
import pytest
from sqlalchemy import select
from app.models import User, Role, ImportJob, TrainingRecord
from app.passwords import hash_password
from conftest import auth, post
from support import FIXTURE_PASSWORD
from test_r3_excel import fill_template, upload_preview, REASON


def preview(client, *, error=False):
    auth(client, 'depthead')
    values=['R10-IMPORT','J001','2026-09-10','R10P','测试项目','R10C','测试课程','R10CL','测试班',2,3,45,'Excel导入' if not error else '无效来源']
    response=upload_preview(client,'records',fill_template(client,'records',values))
    assert response.status_code==200,response.text
    return response.json()


def move(app, mode):
    with app.state.sessions.begin() as db:
        if mode=='subject': db.get(User,'teacher').org_id='dept2'
        elif mode=='owner': db.get(User,'depthead').org_id='dept2'
        elif mode=='permission':
            r=db.get(Role,'role-dept');r.permissions=[p for p in r.permissions if p!='records.read']
        elif mode=='admin': db.get(User,'schooladmin').is_admin=False
        else: raise AssertionError(mode)


@pytest.mark.parametrize('mode',['subject','owner','permission'])
def test_import_detail_rechecks_current_authorization(client2,app2,mode):
    job=preview(client2);move(app2,mode)
    r=client2.get('/api/imports/'+job['id'])
    assert r.status_code in {403,409},r.text
    assert '测试项目' not in r.text and 'J001' not in r.text


@pytest.mark.parametrize('mode',['subject','owner','permission'])
def test_error_workbook_cannot_outlive_original_data_scope(client2,app2,mode):
    job=preview(client2,error=True);assert job['errors']==1
    move(app2,mode)
    r=client2.get('/api/imports/'+job['id']+'/errors')
    assert r.status_code in {403,409},r.text
    assert not r.content.startswith(b'PK')


def test_import_index_redacts_receipt_and_filename_after_scope_change(client2,app2):
    job=preview(client2);r=post(client2,'/api/imports/'+job['id']+'/confirm',{'expected_version':job['version'],**REASON})
    assert r.status_code==200,r.text
    move(app2,'subject')
    response=client2.get('/api/imports');assert response.status_code==200
    item=next(x for x in response.json()['items'] if x['id']==job['id'])
    assert item['access_revoked'] is True
    assert not item.get('receipt') and not item.get('sha256')
    assert item.get('filename')!=job['filename']


def test_new_unrelated_teacher_does_not_invalidate_original_preview(client2,app2):
    job=preview(client2)
    with app2.state.sessions.begin() as db:
        db.add(User(id='r10-newteacher',username='r10-newteacher',staff_no='R10-NEW',name='无关新增教师',org_id='dept1',role_id='role-teacher',password_hash='NOT_LOGIN',must_change_password=True))
    assert client2.get('/api/imports/'+job['id']).status_code==200
    r=post(client2,'/api/imports/'+job['id']+'/confirm',{'expected_version':job['version'],**REASON});assert r.status_code==200,r.text
    assert r.json()['receipt']['written']==1
    assert client2.get('/api/imports/'+job['id']).status_code==200


def test_teacher_import_committed_receipt_stays_readable_with_new_accounts(client2):
    auth(client2,'schooladmin')
    data=fill_template(client2,'teachers',['R10NEW','新教师','R10STAFF','dept1','讲师'])
    r=upload_preview(client2,'teachers',data);assert r.status_code==200,r.text
    job=r.json();assert job['errors']==0,r.text
    r=post(client2,'/api/imports/'+job['id']+'/confirm',{'expected_version':job['version'],**REASON});assert r.status_code==200,r.text
    assert r.json()['receipt']['written']==1
    r=client2.get('/api/imports/'+job['id']);assert r.status_code==200,r.text
    assert 'access_proof' not in r.text


def test_teacher_import_history_requires_current_administrator(client2,app2):
    auth(client2,'schooladmin')
    data=fill_template(client2,'teachers',['R10NEW','新教师','R10STAFF','dept1','讲师'])
    job=upload_preview(client2,'teachers',data).json()
    move(app2,'admin')
    r=client2.get('/api/imports/'+job['id']);assert r.status_code==403,r.text


@pytest.mark.parametrize('mode',['missing','principal','subjects'])
def test_import_proof_missing_or_changed_is_not_silently_reissued(client2,app2,mode):
    job=preview(client2)
    with app2.state.sessions.begin() as db:
        obj=db.get(ImportJob,job['id']);value=copy.deepcopy(obj.receipt)
        if mode=='missing':value.pop('access_proof',None)
        elif mode=='principal':value['access_proof']={'schema_version':1,'principal':'wrong','teacher_ids':['teacher'],'org_ids':[]}
        else:value['access_proof']={'schema_version':1,'principal':'wrong','teacher_ids':'teacher','org_ids':[]}
        obj.receipt=value
    response=client2.get('/api/imports/'+job['id']);assert response.status_code==409,response.text
    response=post(client2,'/api/imports/'+job['id']+'/confirm',{'expected_version':job['version'],**REASON})
    assert response.status_code==409,response.text
    with app2.state.sessions() as db:
        assert db.scalar(select(TrainingRecord).where(TrainingRecord.external_key=='R10-IMPORT')) is None
        assert db.get(ImportJob,job['id']).receipt==value


def test_current_import_access_retains_original_owner_isolation(client2):
    job=preview(client2);auth(client2,'otherdept')
    assert client2.get('/api/imports/'+job['id']).status_code==404


def test_preview_cannot_use_import_permission_to_bypass_records_read(client2,app2):
    auth(client2,'depthead');data=fill_template(client2,'records',['R10X','J001','2026-09-10','R10P','测试项目','R10C','测试课程','R10CL','测试班',2,3,45,'Excel导入'])
    move(app2,'permission')
    r=upload_preview(client2,'records',data);assert r.status_code==403,r.text
