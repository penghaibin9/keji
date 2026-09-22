#!/usr/bin/env python3
"""Populate a specifically approved new R11 MySQL installation through its real APIs.
No database inserts, seed mode, fake login or permission bypass. Secrets stay on host.
"""
from __future__ import annotations
import datetime as dt, fcntl, hashlib, json, os, secrets, sys, uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from delivery.common import Blocked,secure_json,load_private
from delivery.data_spec import *
from school_http_acceptance import Client

class Journal:
    def __init__(self,root,installation_id):
        self.root=Path(root);self.path=self.root/'seed-journal.json'
        if self.path.exists():
            self.data=load_private(self.path)
            if self.data['installation_id']!=installation_id:raise Blocked('SEED_INSTALLATION_ID_MISMATCH')
            if self.data['status']!='COMPLETE' and dt.datetime.now(dt.timezone.utc)>dt.datetime.fromisoformat(self.data['expires_at']):
                raise Blocked('SEED_RESUME_EXPIRED_MANUAL_RECONCILIATION_REQUIRED')
        else:
            now=dt.datetime.now(dt.timezone.utc)
            self.data={'version':1,'run_id':str(uuid.uuid4()),'installation_id':installation_id,'created_at':now.isoformat(),
              'expires_at':(now+dt.timedelta(hours=12)).isoformat(),'status':'STARTED','steps':{},'credentials':{}}
            secure_json(self.path,self.data,exclusive=True)
    def flush(self):secure_json(self.path,self.data)
    def once(self,name,fn):
        if name not in self.data['steps']:
            self.data['steps'][name]=fn(str(uuid.uuid5(uuid.UUID(self.data['run_id']),name)));self.flush()
        return self.data['steps'][name]
    def credential(self,role,username,initial=None):
        if role not in self.data['credentials']:
            self.data['credentials'][role]={'username':username,'initial_password':initial or secrets.token_urlsafe(27)+'A1',
              'password':secrets.token_urlsafe(30)+'A1'};self.flush()
        return self.data['credentials'][role]


def login_ready(client,journal,role,username,initial=None):
    cr=journal.credential(role,username,initial)
    # Save final secret BEFORE changing the password. Interruption after commit can log in again.
    done='password-'+role in journal.data['steps']
    try:
        client.call('POST','/api/auth/login',{'username':username,'password':cr['password']})
    except Exception:
        if done:raise Blocked('ACCOUNT_PASSWORD_CHANGED_REVIEW_REQUIRED')
        client.call('POST','/api/auth/login',{'username':username,'password':cr['initial_password']})
        me=client.call('GET','/api/auth/me');client.csrf=me['csrf']
        if not me['user']['must_change_password']:raise Blocked('UNEXPECTED_NON_TEMPORARY_ACCOUNT')
        client.call('POST','/api/auth/password',{'old_password':cr['initial_password'],'new_password':cr['password']},
                    key=str(uuid.uuid5(uuid.UUID(journal.data['run_id']),'password-'+role)))
        client.call('POST','/api/auth/login',{'username':username,'password':cr['password']})
    me=client.call('GET','/api/auth/me');client.csrf=me['csrf']
    if me['user']['must_change_password']:raise Blocked('MANDATORY_PASSWORD_CHANGE_UNRESOLVED')
    journal.data['steps']['password-'+role]={'user_id':me['user']['id']};journal.flush()
    return me


def populate(factory,private_dir,initial_password,installation_id,*,asset_dir=None):
    """Internal callable for real TestClient controls; CLI has no alternative database/mode."""
    private_dir=Path(private_dir);assets=Path(asset_dir or ROOT/'delivery/assets')
    j=Journal(private_dir,installation_id)
    if j.data['status']=='COMPLETE':return j.data['summary']|{'repeated_run':'READ_ONLY_NO_RESEED'}
    clients={'school':factory('school')};admin=clients['school'];login_ready(admin,j,'school','admin',initial_password)
    def post(name,path,payload,role='school'):
        return j.once(name,lambda key:clients[role].call('POST',path,{**REASON,**payload},key=key))
    def action(name,kind,obj_id,act,role='school'):
        def fn(key):
            if kind=='rules':
                obj=next(x for x in clients[role].call('GET','/api/rules')['items'] if x['id']==obj_id)
            else:
                raw=clients[role].call('GET',f'/api/{kind}/{obj_id}')
                obj=raw.get('qualification',raw.get('assessment',raw.get('rule',raw)))
            return clients[role].call('POST',f'/api/{kind}/{obj_id}/actions',{'action':act,'expected_version':obj['version'],**REASON},key=key)
        return j.once(name,fn)
    if 'empty-authorized' not in j.data['steps']:
        if len(admin.call('GET','/api/organizations')['items'])!=1 or admin.call('GET','/api/users')['total']!=1:
            raise Blocked('SEED_ONLY_NEW_EMPTY_SCHOOL')
        for path in ('records','participations','qualifications','points','assessments','notices'):
            if admin.call('GET','/api/'+path)['total']!=0:raise Blocked('SEED_EXISTING_BUSINESS_DATA_REFUSED')
        for path in ('periods','rules'):
            if admin.call('GET','/api/'+path)['items']:raise Blocked('SEED_EXISTING_CONFIGURATION_REFUSED')
        connections=admin.call('GET','/api/connections')['items']
        if len(connections)!=3 or any(c['state']!='NOT_CONNECTED' or c['config'].get('endpoint') for c in connections):
            raise Blocked('EXTERNAL_CONNECTION_MUST_REMAIN_UNCONFIGURED')
        j.data['steps']['empty-authorized']={'confirmed':True};j.flush()
    orgs={'school':{'id':'school'}}
    for key,code,name,kind,parent in ORG_SPEC:
        orgs[key]=post('org-'+key,'/api/organizations',{'code':code,'name':name,'kind':kind,'parent_id':orgs[parent]['id']})
    users={}
    for role,username,name,staff,org,role_id in ACCOUNTS:
        cr=j.credential(role,username)
        users[role]=post('user-'+role,'/api/users',{'username':username,'name':name,'staff_no':staff,'org_id':orgs[org]['id'],'role_id':role_id,'password':cr['initial_password']})
        clients[role]=factory(role);login_ready(clients[role],j,role,username)
    periods={}
    for year in (YEAR,YEAR-1):
        periods[year]=post('period-'+str(year),'/api/periods',{'name':f'{year}年度演示考核（合成）','start_date':f'{year}-01-01','end_date':f'{year}-12-31'})
    records=[]
    for item in record_spec():
        body={k:v for k,v in item.items() if k not in ('key','role')};body['teacher_id']=users[item['role']]['id']
        records.append(post(item['key'],'/api/records',body))
    for i in range(25):
        role='teacher' if i<23 else 'teacher2';p,pn,c,cn,_,_=CATALOG[i%4]
        post(f'participation-{i}','/api/participations',{'teacher_id':users[role]['id'],'external_key':f'YS-PART-{i+1:03}',
            'event_date':f'2026-05-{i+1:02}','project_code':p,'project':pn,'course_code':c,'course':cn,'hours':'2','source':'经核对人工录入'})
    qualifiers=[('teacher','待提交职业技能材料（合成）','DRAFT'),('teacher','退回待补正材料（合成）','RETURNED'),
      ('teacher','近期到期提醒材料（合成）','APPROVED'),('teacher2','待负责人审核材料（合成）','SUBMITTED'),
      ('teacher3','待补附件材料（合成）','DRAFT'),('other','异学院资质材料（合成）','APPROVED')]
    qualifications=[]
    for i,(role,name,target_state) in enumerate(qualifiers):
        expires=(dt.date.today()+dt.timedelta(days=14 if i==2 else 365)).isoformat()
        obj=post(f'qual-{i}','/api/qualifications',{'teacher_id':users[role]['id'],'category':'职业资格','name':name,
          'certificate_no':f'YS-NOT-A-CERT-{i+1:03}','issuer':'合成材料提供方（非发证机构）','obtained':'2026-01-01','expires':expires},role)
        def attach(key,i=i,role=role,obj=obj):
            q=clients[role].call('GET','/api/qualifications/'+obj['id'])['qualification']
            # Upload API also has an idempotency key; fixed per journal step.
            return clients[role].upload('/api/attachments/qualification/'+obj['id'],(assets/'合成佐证_不是有效证书.pdf').read_bytes(),
                '合成佐证_不是有效证书.pdf','application/pdf',{'expected_version':q['version'],'reason':REASON['reason']},key=key)
        j.once(f'qual-attachment-{i}',attach)
        if target_state!='DRAFT':
            action(f'qual-submit-{i}','qualifications',obj['id'],'submit',role)
        if target_state in ('APPROVED','RETURNED'):
            action(f'qual-review-{i}','qualifications',obj['id'],'approve' if target_state=='APPROVED' else 'return','school')
        qualifications.append({'id':obj['id'],'state':target_state,'role':role,'name':name})
    teacher_ids=[users[r]['id'] for r,*_ in ACCOUNTS if r not in ('dept','college')]
    assessment_ids={};point_results={}
    for year in (YEAR,YEAR-1):
        tids=teacher_ids if year==YEAR else [users['teacher']['id']]
        pid=periods[year]['id']
        for kind in ('points','assessment'):
            components=([{'key':'hours','label':'授课学时积分（演示）','source':'hours','factor':'2','weight':'0','target':'1','cap':None},
                          {'key':'participants','label':'课程人次积分（演示）','source':'participants','factor':'0.1','weight':'0','target':'1','cap':None}]
              if kind=='points' else [{'key':'hours','label':'授课学时（演示）','source':'hours','factor':'1','weight':'60','target':'80','cap':None},
                         {'key':'participants','label':'课程人次（演示）','source':'participants','factor':'1','weight':'40','target':'500','cap':None}])
            rule=post(f'rule-{year}-{kind}','/api/rules',{'kind':kind,'name':f'{year}合成{kind}规则（非学校口径）','period_id':pid,'config':{'components':components}})
            j.once(f'trial-{year}-{kind}',lambda key,rule=rule,tids=tids:admin.call('POST','/api/rules/'+rule['id']+'/trial',{'teacher_ids':tids},key=key))
            action(f'activate-{year}-{kind}','rules',rule['id'],'activate')
            result=post(f'calculate-{year}-{kind}','/api/'+('points' if kind=='points' else 'assessments')+'/calculate',{'period_id':pid,'teacher_ids':tids})
            if kind=='assessment':assessment_ids[year]={x['teacher_id']:x['id'] for x in result['items']}
            else:point_results[year]=result
    # Keep main teacher and teacher2 at TEACHER. Browser checks use teacher2, leaving the main demo available.
    old=assessment_ids[YEAR-1][users['teacher']['id']]
    for role in ('teacher','dept','college','school'):action('old-confirm-'+role,'assessments',old,'confirm',role)
    action('old-archive','assessments',old,'archive','school')
    organization_results=[]
    for kind,key in (('dept','d1'),('college','c1')):
        rule=post('org-rule-'+kind,'/api/organization-assessment-rules',{'target_kind':kind,'name':'合成'+kind+'考核规则','period_id':periods[YEAR]['id'],
          'config':{'components':[{'key':'hours','label':'合成授课学时','source':'hours','weight':'100','target':'150'}]}})
        j.once('org-trial-'+kind,lambda idem,rule=rule,key=key:admin.call('POST','/api/organization-assessment-rules/'+rule['id']+'/trial',{'target_ids':[orgs[key]['id']]},key=idem))
        post('org-activate-'+kind,'/api/organization-assessment-rules/'+rule['id']+'/actions',{'action':'activate','expected_version':rule['version']})
        result=post('org-calc-'+kind,'/api/organization-assessments/calculate',{'target_kind':kind,'period_id':periods[YEAR]['id'],'target_ids':[orgs[key]['id']]})
        organization_results.append(result)
    # An OPEN record dispute deliberately blocks main teacher confirmation. The walkthrough resolves it first.
    dispute=post('record-dispute','/api/disputes',{'object_type':'record','object_id':records[0]['id'],
         'reason':'合成核对：请解释此条人次来源','basis':'演示申请人与复核人分离'},'teacher')
    for i,title in enumerate(['【合成演示数据】本环境不含学校真实业务','演示顺序：教师→教研室→学院→学校','三类接口待对接：不得对外宣称已接通']):
        post(f'notice-{i}','/api/notices',{'title':title,'category':'业务通知','org_id':'school','published':True,
          'body':'这是R11独立受限演示环境。教师、金额、证书与规则均为合成样本。真实接口未接通；演示数据不得用于学校验收或正式考核。'})
    # Confirm actual stored data, not just POST responses; do not read passwords into evidence.
    totals={k:admin.call('GET','/api/'+k)['total'] for k in ('users','records','participations','qualifications','assessments','notices')}
    expected={'users':9,'records':33,'participations':25,'qualifications':6,'assessments':7,'notices':3}
    if totals!=expected:raise Blocked('SYNTHETIC_DATA_TOTALS_MISMATCH')
    conn=admin.call('GET','/api/connections')['items']
    if any(x['state']!='NOT_CONNECTED' or x['config'].get('endpoint') for x in conn):raise Blocked('EXTERNAL_CONNECTION_STATE_CHANGED')
    summary={'status':'SYNTHETIC_DATA_READY_NOT_BROWSER_ACCEPTED','counts':totals,'organizations':6,'periods':2,'organization_assessments':2,
       'primary_teacher':users['teacher']['id'],'primary_assessment':assessment_ids[YEAR][users['teacher']['id']],
       'browser_assessment':assessment_ids[YEAR][users['teacher2']['id']],'browser_teacher_id':users['teacher2']['id'],
       'historical_assessment':old,'qualification_returned':qualifications[1]['id'],'period_id':periods[YEAR]['id'],
       'other_teacher_id':users['other']['id'],'other_qualification_id':qualifications[-1]['id'],'dispute_id':dispute['id'],
       'installation_id':installation_id,'synthetic':True,'external_connections':'NOT_CONNECTED','browser_verified':False,'school_acceptance':False}
    creds={role:{'username':v['username'],'password':v['password']} for role,v in j.data['credentials'].items()}
    secure_json(private_dir/'accounts.private.json',creds)
    fd=os.open(private_dir/'账号密码_仅管理员保管.txt',os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as f:
        f.write('仅本实例合成演示账号，禁止公开。部署时随机生成；不是学校真实账号。\n')
        for role,v in creds.items():f.write(f'{role}\t{v["username"]}\t{v["password"]}\n')
    secure_json(private_dir/'data-summary.json',summary)
    j.data.update(status='COMPLETE',summary=summary);j.flush()
    return summary

class ResumableClient(Client):
    def upload(self,path,data,filename,content_type,fields=None,*,key=None):
        boundary='nd'+uuid.uuid4().hex;parts=[]
        for k,v in (fields or {}).items():parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\nContent-Type: {content_type}\r\n\r\n'.encode()+data+b'\r\n')
        parts.append(f'--{boundary}--\r\n'.encode())
        return self.call('POST',path,data=b''.join(parts),content_type='multipart/form-data; boundary='+boundary,key=key)

def seed_target(target):
    from delivery.manage import selected,pipeline
    target,s,c=selected(target)
    if s['state'] not in ('INSTALLED','SEEDED'):raise Blocked('CANONICAL_MYSQL_INSTALL_REQUIRED_FIRST')
    if (target/'runtime/maintenance/active').exists():raise Blocked('MAINTENANCE_ACTIVE')
    pp=pipeline(target);pp.preflight('verify');proof=pp.installation_receipt()
    if proof['installation_id']!=s.get('installation_id'):raise Blocked('WRONG_INSTALLATION')
    log=[];secret=(target/'deploy/secrets/admin_password').read_text().strip()
    fd=os.open(target/'delivery-state/seed.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise Blocked('ANOTHER_SEED_RUNNING')
        result=populate(lambda role:ResumableClient(s['origin'],target/'delivery-state/tls/ca.crt',log,role),
            target/'delivery-state',secret,s['installation_id'],asset_dir=target/'delivery/assets')
        secure_json(target/'delivery-state/seed-http-events.json',{'requests':log,'contains_passwords':False,'status':result['status']})
        s['state']='SEEDED';secure_json(target/'delivery-state/state.json',s)
        return result|{'private_credentials':'delivery-state/accounts.private.json','ready_for_browser_check':True}
    finally:os.close(fd)
