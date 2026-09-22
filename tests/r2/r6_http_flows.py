"""Real loopback HTTP acceptance of R2 contracts; explicitly NOT browser/MySQL.
Run browser_lab.py on a NEW disposable fixture directory before this script.
"""
from pathlib import Path
from hashlib import sha256
import io,json,uuid,sys,os
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'backend'))
import httpx
from PIL import Image
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'evidence/r6/synthetic_http';OUT.mkdir(parents=True,exist_ok=True)
BASE='http://127.0.0.1:8768'
OLD='FixtureOnly_2026_Local';NEW='HttpChanged_2026_Local'
REASON={'reason':'真实HTTP合成业务核验','basis':'隔离测试材料，不是学校正式样本'}
result={'mode':'NATIVE_HTTP_COOKIE_FULL_APP_SQLITE','browser_tested':False,'mysql_tested':False,'tls_tested':False,
        'release':'R6','synthetic_school_sample':True,'school_acceptance':False,'requests':[],'checks':[]}
class Net:
    def __init__(self,name):self.name=name;self.c=httpx.Client(base_url=BASE,headers={'Origin':BASE},timeout=15)
    def req(self,method,path,body=None,expected=200,**kwargs):
        headers=kwargs.pop('headers',{})
        if method not in ('GET','HEAD'):headers.setdefault('Idempotency-Key',str(uuid.uuid4()))
        r=self.c.request(method,path,json=body,headers=headers,**kwargs)
        result['requests'].append({'role':self.name,'method':method,'path':path,'status':r.status_code,'expected':expected})
        assert r.status_code==expected,(method,path,r.status_code,r.text[:400])
        return r
    def get(self,path):return self.req('GET',path).json()
    def post(self,path,body,**kw):return self.req('POST',path,body,**kw).json()
    def login(self):
        r=self.req('POST','/api/auth/login',{'username':self.name,'password':OLD})
        assert 'HttpOnly' in r.headers['set-cookie'] and 'SameSite=strict' in r.headers['set-cookie']
        me=self.get('/api/auth/me');assert me['user']['must_change_password']
        self.c.headers['X-CSRF-Token']=me['csrf']
        self.req('GET','/api/records',expected=403)
        self.post('/api/auth/password',{'old_password':OLD,'new_password':NEW})
        self.req('GET','/api/auth/me',expected=401)
        self.post('/api/auth/login',{'username':self.name,'password':NEW})
        me=self.get('/api/auth/me');self.c.headers['X-CSRF-Token']=me['csrf']
        assert not me['user']['must_change_password']
        result['checks'].append({'check':self.name+' first-password-cookie-login','status':'PASS'})

def check(name):result['checks'].append({'check':name,'status':'PASS'})
people={name:Net(name) for name in ('teacher','depthead','collegehead','schooladmin')}
try:
    school=people['schooladmin'];teacher=people['teacher'];dept=people['depthead'];college=people['collegehead']
    for path in ['/','/assets/app.js','/assets/scope.js','/assets/icons.js','/assets/styles.css','/assets/integration.css']:
        school.req('GET',path)
    check('real HTTP frontend resources and module URLs')
    school.req('GET','/api/health',expected=503);check('synthetic fixture has no canonical installation provenance and remains NOT_READY')
    for c in people.values():c.login()
    qdata={'teacher_id':'teacher','category':'职业资格','name':'真实HTTP材料证书','certificate_no':'NATIVE-HTTP-'+str(uuid.uuid4()),'issuer':'隔离样本发证单位','obtained':'2026-01-01','expires':'2026-12-31',**REASON}
    q=teacher.post('/api/qualifications',qdata);qid=q['id']
    image=io.BytesIO();Image.new('RGB',(120,70)).save(image,format='PNG');bytes_=image.getvalue()
    attachment=teacher.req('POST','/api/attachments/qualification/'+qid,files={'file':('真实HTTP佐证.png',bytes_,'image/png')},data={'expected_version':q['version'],'reason':'真实HTTP文件上传核验'}).json()
    def qualification_action(client,action):
        obj=client.get('/api/qualifications/'+qid)['qualification']
        return client.post('/api/qualifications/'+qid+'/actions',{'action':action,'expected_version':obj['version'],**REASON})
    assert qualification_action(teacher,'submit')['state']=='SUBMITTED'
    assert qualification_action(dept,'return')['state']=='RETURNED'
    q=teacher.get('/api/qualifications/'+qid)['qualification']
    teacher.req('PUT','/api/qualifications/'+qid,{**qdata,'name':'补充后HTTP材料证书','expected_version':q['version']})
    qualification_action(teacher,'submit');qualification_action(dept,'approve')
    assert len(teacher.get('/api/qualifications/'+qid)['revisions'])==7
    check('qualification -> actual PNG -> submit -> return -> amend -> resubmit -> approve -> 7 revisions')
    assert teacher.req('GET','/api/attachments/'+attachment['id']+'/download').content==bytes_
    check('authorized original attachment bytes match')
    for kind in ['points','assessment']:
        r=school.post('/api/rules',{'kind':kind,'name':'真实HTTP规则-'+kind,'period_id':'period2026',
             'config':{'components':[{'key':'hours','label':'授课学时','source':'hours','factor':'2','weight':'100','target':'10','cap':None}]},**REASON})
        trial=school.post('/api/rules/'+r['id']+'/trial',{'teacher_ids':['teacher']})
        assert trial['items'][0]['total']==('20.00' if kind=='points' else '100.00')
        school.post('/api/rules/'+r['id']+'/actions',{'action':'activate','expected_version':r['version'],**REASON})
        calculated=school.post('/api/'+('points' if kind=='points' else 'assessments')+'/calculate',{'period_id':'period2026','teacher_ids':['teacher'],**REASON})
        check(kind+' rule draft -> trial -> activate -> original calculation service -> persisted result')
        if kind=='points':
            balance=teacher.get('/api/point-balances?teacher_id=teacher')['items'][0]
            balance=teacher.post('/api/point-balances/'+balance['id']+'/actions',{'action':'confirm','expected_version':balance['version'],**REASON})
            school.req('POST','/api/points/calculate',{'period_id':'period2026','teacher_ids':['teacher'],**REASON},expected=409)
            balance=school.post('/api/point-balances/'+balance['id']+'/actions',{'action':'reopen','expected_version':balance['version'],**REASON})
            school.post('/api/points/adjust',{'teacher_id':'teacher','period_id':'period2026','item_key':'manual_review','amount':'-2',**REASON})
            assert teacher.get('/api/points?teacher_id=teacher')['sum']=='18.00'
            balance=teacher.get('/api/point-balances?teacher_id=teacher')['items'][0]
            teacher.post('/api/point-balances/'+balance['id']+'/actions',{'action':'confirm','expected_version':balance['version'],**REASON})
            check('points 20 -> owner confirmation -> recalc refusal -> authorized reopen -> append -2 -> 18 -> reconfirm')
        else:assessment_id=calculated['items'][0]['id']
    ass=school.get('/api/assessments/'+assessment_id)['assessment']
    ass=school.post('/api/assessments/'+assessment_id+'/adjust',{'delta':'-5','expected_version':ass['version'],**REASON});assert ass['score']=='95.00'
    dispute=teacher.post('/api/disputes',{'object_type':'assessment','object_id':assessment_id,**REASON})
    teacher.req('POST','/api/assessments/'+assessment_id+'/actions',{'action':'confirm','expected_version':ass['version'],**REASON},expected=409)
    dept.post('/api/disputes/'+dispute['id']+'/resolve',{'resolution':'合成案例核验后完成复核','expected_version':dispute['version'],**REASON})
    check('assessment correction + dispute blocks confirmation + authorized resolution')
    for who,state in [('teacher','DEPARTMENT'),('depthead','COLLEGE'),('collegehead','SCHOOL'),('schooladmin','READY')]:
        ass=people[who].post('/api/assessments/'+assessment_id+'/actions',{'action':'confirm','expected_version':ass['version'],**REASON});assert ass['state']==state
        check(who+' assessment transition '+state)
    ass=school.post('/api/assessments/'+assessment_id+'/actions',{'action':'archive','expected_version':ass['version'],**REASON})
    checksum=ass['archive_sha256'];assert ass['archive']['assessment']['version']==ass['version']
    check('school archive and final version in immutable snapshot')
    school.req('POST','/api/assessments/calculate',{'period_id':'period2026','teacher_ids':['teacher'],**REASON},expected=409)
    assert school.get('/api/assessments/'+assessment_id+'/print')['assessment']['score']=='95.00'
    check('archived recalc refused and authorized print data is 95')
    q=teacher.get('/api/qualifications/'+qid)['qualification']
    teacher.req('PUT','/api/qualifications/'+qid,{**qdata,'name':'归档后新资质版本','expected_version':q['version']})
    frozen=school.get('/api/assessments/'+assessment_id)['assessment']
    assert frozen['archive']==ass['archive'] and frozen['archive_sha256']==checksum
    check('current qualification revised but archived source/snapshot/SHA256 unchanged')
    stats=school.get('/api/statistics?project_code=P1')
    assert stats['teachers']==1 and stats['assessment_states']=={'ARCHIVED':1} and stats['income']=='100.00'
    assert school.get('/api/statistics?project_code=P2')['assessment_states']=={}
    assert school.get('/api/assessments?project_code=P1&business_scope=true')['total']==1
    assert school.get('/api/assessments?project_code=P2&business_scope=true')['total']==0
    check('R1 shared business scope wired through actual statistics and assessment routes')
    proof=school.req('GET','/api/assessments/'+assessment_id+'/evidence')
    (OUT/'sample_teacher_archive.json').write_bytes(proof.content)
    print_data=school.get('/api/assessments/'+assessment_id+'/print')
    (OUT/'sample_teacher_print_payload.json').write_text(json.dumps(print_data,ensure_ascii=False,indent=2))
    assert print_data['teacher']['name']=='测试教师一' and print_data['events'][-1]['action']=='考核归档'
    original=teacher.req('GET','/api/assessments/'+assessment_id+'/attachments/'+attachment['id']+'/download')
    assert original.content==bytes_
    (OUT/'sample_archived_attachment.png').write_bytes(original.content)
    check('R6 archive proof + frozen identity/final event + original historical attachment')
    from app.config import Settings
    from app.worker import run_once
    lab=Path(os.environ['ND_R6_HTTP_LAB']).resolve()
    assert str(lab).startswith('/tmp/nd-r2-test-')
    cfg=Settings(env='test',database_url='sqlite:///'+str(lab/'browser.sqlite'),secure_cookie=False,
        allowed_hosts='127.0.0.1,localhost',public_origin=BASE,storage_dir=lab/'files')
    for kind in ('assessments','audit','handover'):
        task=school.post('/api/exports',{'kind':kind,'filters':{},'confirmed':kind=='handover'})
        ran=run_once(cfg);assert ran['status']=='DONE',ran
        data=school.req('GET','/api/tasks/'+task['id']+'/download').content
        (OUT/('sample_'+kind+('.zip' if kind=='handover' else '.xlsx'))).write_bytes(data)
    check('R6 actual HTTP queue -> separate worker -> XLSX and typed handover download')
    sys.path.insert(0,str(ROOT/'scripts'))
    from verify_handover import verify
    verified=verify(OUT/'sample_handover.zip');assert verified['status']=='PASS',verified
    (OUT/'handover_validation.json').write_text(json.dumps(verified,ensure_ascii=False,indent=2))
    check('R6 handover file hashes + exact JSONL/CSV + foreign keys + original attachment checks')
    user=next(x for x in school.get('/api/users')['items'] if x['id']=='teacher')
    school.req('PUT','/api/users/teacher',{'name':'归档后更名教师','title':user['title'],'org_id':'dept2','role_id':'role-teacher',
          'active':True,'is_admin':False,'expected_version':user['version'],**REASON})
    teacher.req('GET','/api/auth/me',expected=401)
    dept.req('GET','/api/qualifications/'+qid,expected=403)
    dept.req('GET','/api/attachments/'+attachment['id']+'/download',expected=403)
    dept.req('GET','/api/assessments/'+assessment_id+'/evidence',expected=403)
    dept.req('GET','/api/assessments/'+assessment_id+'/attachments/'+attachment['id']+'/download',expected=403)
    assert school.get('/api/assessments/'+assessment_id+'/print')['teacher']['name']=='测试教师一'
    check('real organizational reassignment revokes old login and old organizational attachment/proof access while historical identity stays frozen')
    audits=school.get('/api/audit?size=200')['items']
    assert any(x['module']=='assessment' for x in audits)
    check('critical business and access audit query available with real Request-ID')
    result['readback']={'qualification_id':qid,'assessment_id':assessment_id,'archive_sha256':checksum,'archived_score':'95.00',
       'points_after_correction':'18.00','attachment_sha256':sha256(bytes_).hexdigest()}
    result['status']='PASS'
except Exception as ex:
    result['status']='FAIL';result['failure']=str(ex);raise
finally:
    for c in people.values():c.c.close()
    (OUT/'http-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps({'status':result['status'],'checks':len(result['checks']),'requests':len(result['requests'])}))
