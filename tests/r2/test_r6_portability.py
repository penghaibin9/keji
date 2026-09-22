"""PDF 12.2,14.6: whole evidence graph and precise portable values."""
import csv,io,json,zipfile,hashlib
from datetime import datetime
from pathlib import Path
import pytest
from sqlalchemy import select
from openpyxl import load_workbook
from app.models import Audit,User,TrainingRecord,Attachment,Assessment,Task
from app.excel_io import _safe_excel_value
from app.worker import run_once
from conftest import auth,post
from test_r6_evidence_chain import export,archive,approved_qualification
from test_r3_handover_validator import mod


def put_audit(db,ident,at):
    db.add(Audit(id=ident,created_at=at,actor_id='schooladmin',actor_name='测试管理员',org_id='school',
      module='r6_boundary',object_id=ident,action='精确时间核对',before={},after={},reason='合成验收',result='SUCCESS',request_id=ident))


def test_audit_page_and_export_use_identical_inclusive_days_and_keep_time(client2,app2):
    c=client2;auth(c,'schooladmin')
    with app2.state.sessions.begin() as db:
        for ident,at in [('before',datetime(2026,9,17,23,59,59)),('start',datetime(2026,9,18)),('end',datetime(2026,9,18,23,59,59,999999)),('after',datetime(2026,9,19))]:put_audit(db,ident,at)
    f={'module':'r6_boundary','start':'2026-09-18','end':'2026-09-18'}
    r=c.get('/api/audit',params=f);assert r.status_code==200
    assert [x['id'] for x in r.json()['items']]==['end','start']
    wb=load_workbook(io.BytesIO(export(c,app2,'audit',f)),read_only=True)
    rows=list(wb.active.values);wb.close()
    assert len(rows)==3 and [x[4] for x in rows[1:]]==['end','start']
    assert rows[1][0]=='2026-09-18T23:59:59.999999'


@pytest.mark.parametrize('f',[{'start':'2026-09-19','end':'2026-09-18'},{'start':'20260918'},{'end':'not-date'},{'end':'2026-02-30'}])
def test_invalid_audit_bounds_rejected_consistently(client2,f):
    auth(client2,'schooladmin')
    assert client2.get('/api/audit',params=f).status_code==422
    assert post(client2,'/api/exports',{'kind':'audit','filters':f,'confirmed':False}).status_code==422


def test_audit_date_max_has_no_overflow(client2):
    auth(client2,'schooladmin');assert client2.get('/api/audit?end=9999-12-31').status_code==200


@pytest.mark.parametrize('value',['=1+1','  =SUM(1,2)','\t+cmd','\r@payload','-12.34'])
def test_spreadsheet_display_escapes_control_prefix_without_losing_raw_value(value):
    assert _safe_excel_value(value)=="'"+value


def save_zip(path,items):
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
        for name,data in items.items():z.writestr(name,data)


def rehash(items):
    m=json.loads(items['manifest.json'])
    m['files']=[{'path':n,'size':len(d),'sha256':hashlib.sha256(d).hexdigest()} for n,d in items.items() if n!='manifest.json']
    items['manifest.json']=json.dumps(m,ensure_ascii=False).encode()


def test_handover_contains_complete_evidence_and_lossless_jsonl(client2,app2,tmp_path):
    c=client2;q,att=approved_qualification(c);x=archive(c)
    with app2.state.sessions.begin() as db:
        db.get(User,'teacher').name='  =不能被Excel执行'
        db.get(TrainingRecord,'rec1').income='-12.30'
    data=export(c,app2,'handover');path=tmp_path/'all-evidence.zip';path.write_bytes(data)
    result=mod.verify(path);assert result['status']=='PASS',result
    assert result['details']['typed_tables']==40 and result['details']['foreign_key_checks']>40
    assert result['details']['typed_roundtrip_verified'] and not result['disaster_restore_proven']
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        m=json.loads(z.read('manifest.json'));assert m['format'].endswith('v2')
        assert m['consistency']=='single_read_only_database_snapshot'
        users=[json.loads(l) for l in z.read('typed/users.jsonl').decode().splitlines()]
        assert next(u for u in users if u['id']=='teacher')['name']=='  =不能被Excel执行'
        values=list(csv.DictReader(io.StringIO(z.read('data/users.csv').decode('utf-8-sig'))))
        assert next(u for u in values if u['id']=='teacher')['name']=="'  =不能被Excel执行"
        records=[json.loads(l) for l in z.read('typed/training_records.jsonl').decode().splitlines()]
        assert next(r for r in records if r['id']=='rec1')['income']=='-12.30'
        archived=json.loads(z.read('typed/assessments.jsonl').decode().splitlines()[0]);assert archived['archive']['teacher']['name']=='测试教师一'
        assert z.read(json.loads(z.read('attachments_manifest.json'))[0]['archive_path'])
        for n in ('typed/users.jsonl','typed/tasks.jsonl','typed/connection_checks.jsonl'):
            text=z.read(n).decode();assert 'password_hash' not in text and 'storage_key' not in text and 'lease_token' not in text and 'FixtureOnly' not in text


@pytest.mark.parametrize('mutation',['typed_value','foreign_key','row_count','missing_table','attachment_owner'])
def test_validator_rejects_structural_damage_even_if_member_hashes_recomputed(client2,app2,tmp_path,mutation):
    c=client2;approved_qualification(c);archive(c);data=export(c,app2,'handover')
    with zipfile.ZipFile(io.BytesIO(data)) as z:items={n:z.read(n) for n in z.namelist()}
    if mutation=='typed_value':
        rows=[json.loads(l) for l in items['typed/users.jsonl'].decode().splitlines()];rows[0]['name']='CSV没有同步的改名'
        items['typed/users.jsonl']=(''.join(json.dumps(r,ensure_ascii=False,separators=(',',':'))+'\n' for r in rows)).encode()
    elif mutation=='foreign_key':
        key='typed/users.jsonl';rows=[json.loads(l) for l in items[key].decode().splitlines()];rows[0]['org_id']='missing-org'
        items[key]=(''.join(json.dumps(r,ensure_ascii=False,separators=(',',':'))+'\n' for r in rows)).encode()
        m=json.loads(items['manifest.json']);t=next(t for t in m['tables'] if t['name']=='users')
        out=io.StringIO(newline='');w=csv.writer(out);w.writerow(t['columns']);w.writerows([[mod._csv_cell(row[k]) for k in t['columns']] for row in rows]);items['data/users.csv']=('\ufeff'+out.getvalue()).encode()
    elif mutation=='row_count':
        m=json.loads(items['manifest.json']);m['tables'][0]['rows']+=1;items['manifest.json']=json.dumps(m).encode()
    elif mutation=='missing_table':
        items.pop('typed/disputes.jsonl');items.pop('data/disputes.csv')
        m=json.loads(items['manifest.json']);m['tables']=[t for t in m['tables'] if t['name']!='disputes'];items['manifest.json']=json.dumps(m).encode()
    else:
        a=json.loads(items['attachments_manifest.json']);a[0]['teacher_id']='otherteacher';items['attachments_manifest.json']=json.dumps(a).encode()
    rehash(items);p=tmp_path/'broken.zip';save_zip(p,items)
    result=mod.verify(p);assert result['status']=='FAIL' and result['errors'],result


def test_handover_failed_attachment_cleans_temporary_sensitive_archive(client2,app2):
    c=client2;q,a=approved_qualification(c);auth(c,'schooladmin')
    with app2.state.sessions() as db:key=db.get(Attachment,a['id']).storage_key
    (app2.state.settings.storage_dir/key).unlink()
    task=post(c,'/api/exports',{'kind':'handover','filters':{},'confirmed':True}).json()
    assert run_once(app2.state.settings)['status']=='FAILED'
    root=app2.state.settings.storage_dir/'.exports'
    assert not list(root.glob('*.zip')) and not list(root.glob('.*.tmp.zip'))
    with app2.state.sessions() as db:assert not db.get(Task,task['id']).result

@pytest.mark.parametrize('kind,permission',[('records','records.read'),('participations','records.read'),('qualifications','qualification.read'),('points','points.read'),('assessments','assessment.read')])
def test_export_alone_does_not_grant_hidden_module_data(client2,app2,kind,permission):
    from app.models import Role
    auth(client2,'schooladmin')
    with app2.state.sessions.begin() as db:
        role=db.get(Role,'role-school');role.permissions=[p for p in role.permissions if p!=permission]
    r=post(client2,'/api/exports',{'kind':kind,'filters':{},'confirmed':False})
    assert r.status_code==403,r.text
