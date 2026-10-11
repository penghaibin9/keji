"""12.6 sensitive identifiers are masked for non-owner, non-reviewer viewers (API and export)."""
import io
from openpyxl import load_workbook
from sqlalchemy import select
from app.models import Role,User,Org
from app.permissions import TEACHER
from app.core import Actor
from app.sensitive import MaskPolicy,mask_text
from app.worker import run_once
from conftest import auth,post
from support import HASH

REASON={'reason':'脱敏验证','basis':'合成隔离数据'}
CERT='ZG-2026-88776655'


def add_viewer(app):
    """A department account whose role can read business data but holds no review/manage permission."""
    with app.state.sessions.begin() as db:
        db.add(Role(id='role-dept-viewer',code='dept-viewer',name='教研室查询员',kind='dept',permissions=sorted(TEACHER)))
        db.flush()
        db.add(User(id='deptviewer',username='deptviewer',name='教研室查询员',staff_no=None,org_id='dept1',role_id='role-dept-viewer',password_hash=HASH,must_change_password=False))


def make_qualification(c):
    auth(c,'teacher')
    r=post(c,'/api/qualifications',{'teacher_id':'teacher','category':'职业资格','name':'高级培训师','certificate_no':CERT,'issuer':'合成发证机构','obtained':'2025-01-01',**REASON})
    assert r.status_code==200,r.text
    assert r.json()['certificate_no']==CERT  # owner's own command response is full
    return r.json()


def export(c,app,kind):
    r=post(c,'/api/exports',{'kind':kind,'filters':{},'confirmed':False});assert r.status_code==200,r.text
    task=r.json();assert run_once(app.state.settings)['status']=='DONE'
    detail=c.get('/api/tasks/'+task['id']).json()['task']
    r=c.get('/api/tasks/'+task['id']+'/download');assert r.status_code==200,r.text
    wb=load_workbook(io.BytesIO(r.content),read_only=True);rows=list(wb.active.values);wb.close()
    return rows,detail['result']


def test_mask_text_keeps_only_edges():
    assert mask_text('J001')=='J**1'
    assert mask_text(CERT).startswith('ZG-2') and mask_text(CERT).endswith('6655') and CERT not in mask_text(CERT)
    assert mask_text('')=='' and mask_text(None) is None and mask_text('A')=='A'


def test_owner_reviewer_full_viewer_masked_in_api(client2,app2):
    c=client2;add_viewer(app2);q=make_qualification(c)
    # Teacher self sees full values.
    rows=c.get('/api/qualifications').json()['items'];assert rows[0]['certificate_no']==CERT
    assert c.get('/api/teachers').json()['items'][0]['staff_no']=='J001'
    assert c.get('/api/qualifications/'+q['id']).json()['qualification']['certificate_no']==CERT
    # Authorised reviewer in scope sees full values.
    auth(c,'depthead')
    assert c.get('/api/qualifications').json()['items'][0]['certificate_no']==CERT
    detail=c.get('/api/qualifications/'+q['id']).json()
    assert detail['qualification']['certificate_no']==CERT and detail['revisions'][0]['data']['certificate_no']==CERT
    assert {x['staff_no'] for x in c.get('/api/teachers').json()['items']}=={'J001'}
    # Same scope but no review/manage permission: masked everywhere, including nested revisions/events.
    auth(c,'deptviewer')
    item=c.get('/api/qualifications').json()['items'][0]
    assert item['certificate_no']!=CERT and '*' in item['certificate_no']
    detail=c.get('/api/qualifications/'+q['id'])
    assert detail.status_code==200 and CERT not in detail.text
    teachers=c.get('/api/teachers').json()['items']
    assert teachers and all(t['staff_no']!='J001' and '*' in t['staff_no'] for t in teachers)
    search=c.get('/api/portal/search',params={'q':'高级'});assert search.status_code==200 and CERT not in search.text


def test_unrelated_scope_reviewer_and_teacher_get_masked_by_policy(app2):
    # Out-of-scope rows are never listed; the policy still masks if one leaks into a response.
    with app2.state.sessions() as db:
        def actor(uid):
            u=db.get(User,uid);return Actor(db,u,db.get(Role,u.role_id),db.get(Org,u.org_id))
        assert MaskPolicy(db,actor('otherdept')).apply({'teacher_id':'teacher','certificate_no':CERT})['certificate_no']!=CERT
        assert MaskPolicy(db,actor('otherteacher')).apply({'id':'teacher','username':'teacher','staff_no':'J001'})['staff_no']=='J**1'
        assert MaskPolicy(db,actor('depthead')).apply({'teacher_id':'teacher','certificate_no':CERT})['certificate_no']==CERT
        assert MaskPolicy(db,actor('teacher')).apply({'teacher_id':'teacher','certificate_no':CERT})['certificate_no']==CERT


def test_export_follows_same_masking_rule(client2,app2):
    c=client2;add_viewer(app2);make_qualification(c)
    auth(c,'depthead');rows,result=export(c,app2,'qualifications')
    assert rows[1][0]=='J001' and rows[1][4]==CERT and result['sensitive_masked']==0
    auth(c,'deptviewer');rows,result=export(c,app2,'qualifications')
    assert rows[1][0]!='J001' and rows[1][4]!=CERT and '*' in rows[1][4] and result['sensitive_masked']==2
    rows,_=export(c,app2,'records')
    assert all(r[2] is None or '*' in r[2] for r in rows[1:])
    auth(c,'teacher');rows,_=export(c,app2,'qualifications')
    assert rows[1][0]=='J001' and rows[1][4]==CERT
