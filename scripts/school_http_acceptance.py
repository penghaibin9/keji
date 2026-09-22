"""Synthetic business checks against a NEW loopback-only school; no fixture SQL.

Used by the independent Docker/MySQL drill and by the explicitly labelled
SQLite HTTPS control. Responses/credentials are not printed on failure.
"""
from __future__ import annotations
import base64, http.cookiejar, io, json, secrets, ssl, time, uuid, zipfile
from pathlib import Path
from urllib.request import Request, build_opener, ProxyHandler, HTTPCookieProcessor, HTTPSHandler, HTTPRedirectHandler
from urllib.error import HTTPError
from urllib.parse import urlsplit
from xml.sax.saxutils import escape

REASON={'reason':'R7独立验收合成样本','basis':'非学校真实数据，不得作为学校签认结果'}
HEADERS=['来源唯一编号','教师工号','业务日期','项目编码','项目名称','课程编码','课程名称','班级编码','班级名称','授课学时','课程人次','归属培训收入','数据来源']
PNG=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFklEQVR4nGP8//8/AwMDEwMDAwMDAwAkBgMB/DXemwAAAABJRU5ErkJggg==')

class AcceptanceFailure(RuntimeError):pass
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*a,**k):return None

class Client:
    def __init__(self,origin,ca_file,events,role):
        parsed=urlsplit(origin)
        if parsed.scheme!='https' or parsed.hostname!='127.0.0.1' or parsed.path not in ('','/') or parsed.query or parsed.fragment or parsed.username:
            raise AcceptanceFailure('ACCEPTANCE_ONLY_NEW_LOOPBACK_HTTPS')
        self.origin=origin.rstrip('/');self.events=events;self.role=role;self.csrf='';self.jar=http.cookiejar.CookieJar()
        self.opener=build_opener(ProxyHandler({}),HTTPCookieProcessor(self.jar),HTTPSHandler(context=ssl.create_default_context(cafile=str(ca_file))),NoRedirect())
    def raw(self,method,path,body=None,*,expected=200,key=None,data=None,content_type=None):
        if not path.startswith('/api/') and path!='/':raise AcceptanceFailure('UNEXPECTED_ACCEPTANCE_PATH')
        headers={'Origin':self.origin,'Cache-Control':'no-cache'}
        if method not in ('GET','HEAD'):
            headers['Idempotency-Key']=key or str(uuid.uuid4())
            if self.csrf:headers['X-CSRF-Token']=self.csrf
        if body is not None:data=json.dumps(body,ensure_ascii=False).encode();content_type='application/json'
        if content_type:headers['Content-Type']=content_type
        try:r=self.opener.open(Request(self.origin+path,data=data,headers=headers,method=method),timeout=20)
        except HTTPError as exc:r=exc
        with r:
            payload=r.read(25*1024*1024+1);status=r.code;response_headers=dict(r.headers)
        self.events.append({'role':self.role,'method':method,'path':path,'status':status,'expected':expected})
        if status!=expected or len(payload)>25*1024*1024:raise AcceptanceFailure(f'HTTP_CHECK_FAILED {self.role} {method} {path} {status}')
        return payload,response_headers
    def call(self,method,path,body=None,**kwargs):
        data,_=self.raw(method,path,body,**kwargs)
        return json.loads(data) if data else None
    def first_login(self,username,password):
        self.call('POST','/api/auth/login',{'username':username,'password':password})
        me=self.call('GET','/api/auth/me');self.csrf=me['csrf']
        if not me['user']['must_change_password']:raise AcceptanceFailure('FIRST_CHANGE_NOT_REQUIRED')
        self.call('GET','/api/records',expected=403)
        new=secrets.token_urlsafe(28)
        self.call('POST','/api/auth/password',{'old_password':password,'new_password':new})
        self.call('GET','/api/auth/me',expected=401)
        self.call('POST','/api/auth/login',{'username':username,'password':new})
        me=self.call('GET','/api/auth/me');self.csrf=me['csrf']
        if me['user']['must_change_password']:raise AcceptanceFailure('FIRST_CHANGE_NOT_SAVED')
        return me['user']
    def upload(self,path,data,filename,content_type,fields=None):
        boundary='nd'+uuid.uuid4().hex;parts=[]
        for k,v in (fields or {}).items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\nContent-Type: {content_type}\r\n\r\n'.encode()+data+b'\r\n')
        parts.append(f'--{boundary}--\r\n'.encode())
        return self.call('POST',path,data=b''.join(parts),content_type='multipart/form-data; boundary='+boundary)


def workbook(rows):
    """Small standard OOXML file: no optional host Excel dependency for the drill."""
    def col(n):
        out=''
        while n:n,r=divmod(n-1,26);out=chr(65+r)+out
        return out
    body=''.join('<row r="%s">'%r+''.join('<c r="%s%s" t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>'%(col(c),r,escape(str(v))) for c,v in enumerate(row,1))+'</row>' for r,row in enumerate(rows,1))
    files={'[Content_Types].xml':'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
        '_rels/.rels':'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        'xl/workbook.xml':'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="培训业务" sheetId="1" r:id="rId1"/></sheets></workbook>',
        'xl/_rels/workbook.xml.rels':'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
        'xl/worksheets/sheet1.xml':'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'+body+'</sheetData></worksheet>'}
    data=io.BytesIO()
    with zipfile.ZipFile(data,'w',zipfile.ZIP_DEFLATED) as z:
        for name,text in files.items():z.writestr(name,text)
    return data.getvalue()


def run_fresh_school(origin,ca_file,password_file,out,*,process_tasks=None):
    """Must only be called after canonical init into an independent empty lab."""
    out=Path(out);out.mkdir(parents=True,exist_ok=True);events=[];checks=[]
    def check(name):checks.append({'check':name,'status':'PASS'})
    admin=Client(origin,ca_file,events,'school');admin.first_login('admin',Path(password_file).read_text().strip())
    # Refuse an existing school BEFORE creating synthetic organizations or users.
    if admin.call('GET','/api/organizations')['items'].__len__()!=1 or admin.call('GET','/api/users')['total']!=1 or admin.call('GET','/api/records')['total']!=0:
        raise AcceptanceFailure('EXISTING_SCHOOL_REFUSED')
    check('new school canonical initialization and mandatory password change')
    users={};clients={'school':admin};orgs={}
    for letter in ('a','b'):
        college=admin.call('POST','/api/organizations',{'code':'r7c'+letter,'name':'合成学院'+letter,'kind':'college','parent_id':'school',**REASON})
        dept=admin.call('POST','/api/organizations',{'code':'r7d'+letter,'name':'合成教研室'+letter,'kind':'dept','parent_id':college['id'],**REASON})
        orgs[letter]=(college,dept)
    for role,org_id,role_id in [('teacher',orgs['a'][1]['id'],'role-teacher'),('outsider',orgs['b'][1]['id'],'role-teacher'),('dept',orgs['a'][1]['id'],'role-dept'),('college',orgs['a'][0]['id'],'role-college')]:
        pwd=secrets.token_urlsafe(28)
        user=admin.call('POST','/api/users',{'username':'r7'+role,'staff_no':'r7'+role if role in ('teacher','outsider') else None,'name':'合成'+role,'org_id':org_id,'role_id':role_id,'password':pwd,**REASON})
        users[role]=user;clients[role]=Client(origin,ca_file,events,role);clients[role].first_login('r7'+role,pwd)
    period=admin.call('POST','/api/periods',{'name':'R7合成验收周期','start_date':'2026-01-01','end_date':'2026-12-31',**REASON})
    check('four levels created through real authorized HTTP; no fixture SQL')
    row=['r7-excel-one','r7teacher','2026-06-01','R7P','合成项目','R7C','合成课程','R7B','合成班级','10','5','100.00','Excel导入']
    bad=list(row);bad[1]='not-an-existing-teacher'
    for is_bad,values in [(True,bad),(False,row)]:
        content=workbook([HEADERS,values]);(out/('invalid_import.xlsx' if is_bad else 'valid_import.xlsx')).write_bytes(content)
        job=admin.upload('/api/imports/records/preview',content,'acceptance.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        if admin.call('GET','/api/records')['total']!=0:raise AcceptanceFailure('PREVIEW_WROTE_BUSINESS_ROWS')
        payload={'expected_version':job['version'],**REASON}
        if is_bad:
            if job['errors']!=1:raise AcceptanceFailure('IMPORT_ERROR_NOT_LOCATED')
            admin.call('POST','/api/imports/'+job['id']+'/confirm',payload,expected=409)
            errors,_=admin.raw('GET','/api/imports/'+job['id']+'/errors');(out/'import_errors.xlsx').write_bytes(errors)
        else:
            if job['errors']:raise AcceptanceFailure('VALID_IMPORT_REJECTED')
            key=str(uuid.uuid4());receipt=admin.call('POST','/api/imports/'+job['id']+'/confirm',payload,key=key)
            if admin.call('POST','/api/imports/'+job['id']+'/confirm',payload,key=key)!=receipt:raise AcceptanceFailure('IDEMPOTENCY_RECEIPT_CHANGED')
            admin.call('POST','/api/imports/'+job['id']+'/confirm',payload,expected=409)
    records=admin.call('GET','/api/records')
    if records['total']!=1:raise AcceptanceFailure('EXCEL_CONFIRMED_ROW_COUNT')
    record=records['items'][0];tid=users['teacher']['id'];pid=period['id'];teacher=clients['teacher']
    if clients['outsider'].call('GET','/api/records')['total']!=0:raise AcceptanceFailure('OTHER_ORGANIZATION_DATA_LEAK')
    check('XLSX error rows, preview no-write, confirmed write and duplicate receipt')
    q=teacher.call('POST','/api/qualifications',{'teacher_id':tid,'category':'职业资格','name':'R7合成资质','certificate_no':'R7-CERT','issuer':'合成机构','obtained':'2026-01-01','expires':'2026-12-31',**REASON})
    attachment=teacher.upload('/api/attachments/qualification/'+q['id'],PNG,'synthetic.png','image/png',{'expected_version':q['version'],'reason':REASON['reason']})
    for role,action in [('teacher','submit'),('dept','approve')]:
        q=clients[role].call('GET','/api/qualifications/'+q['id'])['qualification']
        clients[role].call('POST','/api/qualifications/'+q['id']+'/actions',{'action':action,'expected_version':q['version'],**REASON})
    clients['outsider'].call('GET','/api/attachments/'+attachment['id']+'/download',expected=403)
    for kind in ('points','assessment'):
        rule=admin.call('POST','/api/rules',{'kind':kind,'name':'R7合成'+kind,'period_id':pid,'config':{'components':[{'key':'hours','label':'学时','source':'hours','factor':'2','weight':'100','target':'10','cap':None}]},**REASON})
        trial=admin.call('POST','/api/rules/'+rule['id']+'/trial',{'teacher_ids':[tid]})
        if trial['items'][0]['total']!=('20.00' if kind=='points' else '100.00'):raise AcceptanceFailure('RULE_TRIAL_MISMATCH')
        admin.call('POST','/api/rules/'+rule['id']+'/actions',{'action':'activate','expected_version':rule['version'],**REASON})
        computed=admin.call('POST','/api/'+('points' if kind=='points' else 'assessments')+'/calculate',{'period_id':pid,'teacher_ids':[tid],**REASON})
        if kind=='assessment':aid=computed['items'][0]['id']
    assessment=admin.call('GET','/api/assessments/'+aid)['assessment']
    for role,state in [('teacher','DEPARTMENT'),('dept','COLLEGE'),('college','SCHOOL'),('school','READY')]:
        assessment=clients[role].call('POST','/api/assessments/'+aid+'/actions',{'action':'confirm','expected_version':assessment['version'],**REASON})
        if assessment['state']!=state:raise AcceptanceFailure('ASSESSMENT_TRANSITION_MISMATCH')
    assessment=admin.call('POST','/api/assessments/'+aid+'/actions',{'action':'archive','expected_version':assessment['version'],**REASON})
    raw,_=teacher.raw('GET','/api/assessments/'+aid+'/attachments/'+attachment['id']+'/download')
    if raw!=PNG:raise AcceptanceFailure('ARCHIVED_ATTACHMENT_CHANGED')
    (out/'archived_attachment.png').write_bytes(raw)
    proof,_=admin.raw('GET','/api/assessments/'+aid+'/evidence');(out/'archived_evidence.json').write_bytes(proof)
    check('real API four-level assessment archive and original attachment authorization')
    task=admin.call('POST','/api/exports',{'kind':'assessments','filters':{'period_id':pid}})
    for _ in range(50):
        if process_tasks:process_tasks()
        status=admin.call('GET','/api/tasks/'+task['id'])['task']
        if status['state']=='DONE':break
        if status['state'] in ('FAILED','BLOCKED'):raise AcceptanceFailure('EXPORT_TASK_FAILED')
        time.sleep(.2)
    else:raise AcceptanceFailure('EXPORT_TASK_NOT_FINISHED')
    xlsx,_=admin.raw('GET','/api/tasks/'+task['id']+'/download')
    if not zipfile.is_zipfile(io.BytesIO(xlsx)):raise AcceptanceFailure('EXPORT_NOT_XLSX')
    (out/'archived_assessments.xlsx').write_bytes(xlsx);check('real worker and actual downloadable XLSX')
    # Revoke a still-live other-school account and test its old session directly.
    other=next(x for x in admin.call('GET','/api/users')['items'] if x['id']==users['outsider']['id'])
    admin.call('PUT','/api/users/'+other['id'],{k:other[k] for k in ('name','title','org_id','role_id','is_admin')}|{'active':False,'expected_version':other['version'],**REASON})
    clients['outsider'].call('GET','/api/auth/me',expected=401);check('disabled user session is immediately rejected')
    result={'status':'PASS','transport':'HTTPS_VERIFIED_LOCAL_TEST_CERT','synthetic_school_sample':True,
            'school_acceptance':False,'browser_tested':False,'checks':checks,'requests':events,
            'restore_expectations':{'assessment_id':aid,'archive_sha256':assessment['archive_sha256'],'record_id':record['id'],'record_income':'100.00','attachment_id':attachment['id']}}
    (out/'business_http.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    return result,admin
