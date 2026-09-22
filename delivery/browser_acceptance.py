#!/usr/bin/env python3
"""Normal browser/real UI checks. Does not substitute HTTP clients for business actions.
Run only after MySQL installation and seed. Trust the instance CA explicitly first.
Uses teacher2 for writes; preserves main teacher's pending demonstration workflow.
"""
from __future__ import annotations
import argparse, datetime as dt, hashlib, json, os, re, sys, time, uuid, zipfile
from pathlib import Path
from urllib.parse import urlsplit
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from delivery.common import Blocked,secure_json

def validated_inputs(origin,credentials,data,mysql_proof):
    u=urlsplit(origin)
    if u.scheme!='https' or u.hostname!='127.0.0.1' or u.username or u.password or u.path not in ('','/') or u.query or u.fragment:
        raise Blocked('ONLY_EXPLICIT_LOOPBACK_HTTPS_ALLOWED')
    if not u.port or not 1024<=u.port<=65535:raise Blocked('HIGH_LOCAL_PORT_REQUIRED')
    proof=json.loads(Path(mysql_proof).read_text())
    if not proof.get('real_mysql_installation') or not re.match(r'^8\.4\.',proof.get('version','')):
        raise Blocked('REAL_MYSQL_8_4_INSTALLATION_RECEIPT_REQUIRED')
    provenance=proof.get('provenance',{})
    if provenance.get('baseline_revision')!='20260918_0001' or provenance.get('source_kind')!='canonical_empty_school':
        raise Blocked('CANONICAL_PROVENANCE_REQUIRED')
    cr=json.loads(Path(credentials).read_text());summary=json.loads(Path(data).read_text())
    if summary.get('installation_id')!=provenance.get('installation_id'):raise Blocked('SAMPLE_AND_MYSQL_IDENTITY_MISMATCH')
    for role in ('school','teacher','teacher2','dept','college'):
        if not cr.get(role,{}).get('username') or len(cr[role].get('password',''))<12:raise Blocked('PRIVATE_CREDENTIAL_BUNDLE_INCOMPLETE')
    return cr,summary,proof

def run(args):
    cr,data,proof=validated_inputs(args.origin,args.credentials,args.data_summary,args.mysql_proof)
    if not args.confirm_synthetic_writes:raise Blocked('EXPLICIT_CONFIRMATION_REQUIRED_FOR_UI_WRITES')
    out=Path(args.output);out.mkdir(parents=True,exist_ok=False);out.chmod(0o700)
    report={'status':'RUNNING','method':'NORMAL_BROWSER_REAL_UI','mocked_api_responses':False,'ignore_https_errors':False,
      'mysql_installation_id':proof['provenance']['installation_id'],'mysql_version_from_target_receipt':proof['version'],
      'real_mysql_receipt_supplied':True,'mysql_database_queried_by_browser_runner':False,'production_acceptance':False,
      'checks':[],'requests':[],'ui_writes_role':'teacher2','primary_demo_preserved':False,'printer_hardware_tested':False}
    secure_json(out/'report.json',report)
    from playwright.sync_api import sync_playwright,expect
    screens=[0];contexts=[]
    def check(name,page=None):
        report['checks'].append({'name':name,'status':'PASS'})
        if page:
            screens[0]+=1;page.screenshot(path=str(out/f'{screens[0]:02d}.png'),full_page=True)
        secure_json(out/'report.json',report)
    def ready(page):
        page.locator('#content h1').wait_for(timeout=20000)
        expect(page.locator('.busy-panel')).to_have_count(0,timeout=20000)
    def nav(page,dest):
        if page.locator('#modal-root:not(.hidden)').count():page.locator('#modal-root [data-action=close]').last.click()
        page.locator(f'#sidebar [data-action=nav][data-id="{dest}"]').click();ready(page)
    def confirm_form(page,path_part):
        page.locator('#edit-form').wait_for()
        page.locator('#f-reason').fill('R11浏览器实测：合成数据正常办理，非学校签认')
        if page.locator('#f-basis').count():page.locator('#f-basis').fill('浏览器现场验收留痕')
        with page.expect_response(lambda r:path_part in r.url and r.request.method=='POST') as r:
            page.locator('button[form="edit-form"]').click()
        assert r.value.status==200,f'UI mutation response {r.value.status}'
        expect(page.locator('#edit-form')).to_have_count(0,timeout=15000)
    def download(page,selector,name):
        with page.expect_download() as pending:page.locator(selector).first.click()
        obj=pending.value;obj.save_as(str(out/name))
        assert (out/name).stat().st_size>0
        return out/name
    try:
        with sync_playwright() as pw:
            opts={'headless':not args.headed}
            if args.executable:opts['executable_path']=args.executable
            elif args.channel:opts['channel']=args.channel
            browser=pw.chromium.launch(**opts)
            try:
                def login(role):
                    ctx=browser.new_context(viewport={'width':1440,'height':1000},accept_downloads=True)
                    contexts.append(ctx);page=ctx.new_page()
                    page.on('response',lambda r:report['requests'].append({'method':r.request.method,'path':urlsplit(r.url).path,'status':r.status}) if '/api/' in r.url else None)
                    page.goto(args.origin,wait_until='domcontentloaded',timeout=20000)
                    page.locator('#username').fill(cr[role]['username']);page.locator('#password').fill(cr[role]['password'])
                    page.locator('#login-form button[type=submit]').click();ready(page)
                    assert page.locator('.current-identity').is_visible()
                    check('真实浏览器登录与首页：'+role,page);return page
                teacher=login('teacher');qa=login('teacher2');dept=login('dept');college=login('college');school=login('school')
                nav(teacher,'records')
                assert teacher.locator('[data-action=participation-next]').is_enabled()
                teacher.locator('[data-action=participation-next]').click()
                expect(teacher.locator('[data-action=participation-prev]')).to_be_enabled()
                check('教师参训独立第二页',teacher)
                teacher.locator('[data-action=next]').click();expect(teacher.locator('[data-action=prev]')).to_be_enabled()
                check('教师授课第二页独立可见',teacher)
                # This is a negative authorization probe in the real authenticated browser session,
                # not a replacement for the UI business operations below.
                denied=teacher.evaluate("async () => (await fetch('/api/users',{credentials:'same-origin'})).status")
                assert denied==403;check('教师浏览器会话直请求管理接口被403拒绝')
                nav(qa,'qualifications');qa.locator('[data-action=qualification-form][data-id=""]').click()
                token=uuid.uuid4().hex[:10];name='浏览器合成佐证-'+token
                qa.locator('#f-name').fill(name);qa.locator('#f-certificate_no').fill('UI-SYNTHETIC-'+token)
                qa.locator('#f-issuer').fill('合成提供方（非发证机构）');qa.locator('#f-obtained').fill('2026-01-01')
                qa.locator('#f-expires').fill('2027-12-31');qa.locator('#f-reason').fill('浏览器合成验证')
                with qa.expect_response(lambda r:urlsplit(r.url).path=='/api/qualifications' and r.request.method=='POST') as response:
                    qa.locator('button[form="edit-form"]').click()
                assert response.value.status==200;qid=response.value.json()['id']
                qa.locator('[data-action=upload]').wait_for()
                qa.reload();ready(qa);qa.locator(f'[data-action=qualification][data-id="{qid}"]').click()
                expect(qa.get_by_role('dialog')).to_contain_text(name);check('资质正常保存、刷新回读',qa)
                qa.locator('[data-action=upload]').click();qa.locator('#f-file').set_input_files(str(ROOT/'delivery/assets/合成佐证_不是有效证书.pdf'))
                qa.locator('#f-reason').fill('合成文件，非真实证书')
                with qa.expect_response(lambda r:'/api/attachments/qualification/' in r.url and r.request.method=='POST') as upload_response:
                    qa.locator('button[form="edit-form"]').click()
                assert upload_response.value.status==200
                qa.locator(f'[data-action=qual-action][data-id="submit|{qid}"]').click();confirm_form(qa,'/qualifications/'+qid+'/actions')
                nav(dept,'qualifications');dept.locator(f'[data-action=qualification][data-id="{qid}"]').click()
                dept.locator(f'[data-action=qual-action][data-id="approve|{qid}"]').click();confirm_form(dept,'/qualifications/'+qid+'/actions')
                expect(dept.get_by_role('dialog')).to_contain_text('审核通过');check('教师提交→负责人审批',dept)
                nav(qa,'qualifications');qa.locator(f'[data-action=qualification][data-id="{qid}"]').click()
                f=download(qa,'[data-action=attachment-download]','uploaded-proof.pdf')
                expected=hashlib.sha256((ROOT/'delivery/assets/合成佐证_不是有效证书.pdf').read_bytes()).hexdigest()
                assert hashlib.sha256(f.read_bytes()).hexdigest()==expected;check('原附件真实下载与字节核对',qa)
                aid=data['browser_assessment']
                for role,page in [('teacher2',qa),('dept',dept),('college',college),('school',school)]:
                    nav(page,'assessment');page.locator(f'[data-action=assessment][data-id="{aid}"]').click()
                    page.locator(f'[data-action=assess-action][data-id="confirm|{aid}"]').click()
                    confirm_form(page,'/assessments/'+aid+'/actions');check('考核当前角色确认：'+role,page)
                school.locator(f'[data-action=assess-action][data-id="archive|{aid}"]').click()
                confirm_form(school,'/assessments/'+aid+'/actions');expect(school.get_by_role('dialog')).to_contain_text('已归档')
                download(school,'[data-action=assessment-proof]','archived-evidence.json');check('学校归档与证据下载',school)
                for bad,filename in [(True,'05_浏览器验收_教师二_错误.xlsx'),(False,'04_浏览器验收_教师二_正确.xlsx')]:
                    nav(school,'imports');school.locator('[data-action=import-form]').click()
                    school.locator('#f-kind').select_option('records');school.locator('#f-file').set_input_files(str(ROOT/'delivery/assets'/filename))
                    school.locator('button[form="edit-form"]').click()
                    school.get_by_role('dialog',name='Excel 导入预览').wait_for()
                    if bad:
                        assert school.locator('[data-action=import-confirm]').count()==0
                        e=download(school,'[data-action=import-errors]','import-error-rows.xlsx');assert zipfile.is_zipfile(e)
                        check('错误Excel定位、下载、禁止确认',school)
                    else:
                        school.locator('[data-action=import-confirm]').click();confirm_form(school,'/confirm')
                        expect(school.get_by_role('dialog')).to_contain_text('已经真实入库');check('正确Excel预览后明确确认',school)
                nav(school,'records');school.locator('[data-action=export][data-id=records]').click();ready(school)
                for _ in range(45):
                    if school.locator('[data-action=task-download]').count():break
                    time.sleep(2);school.locator('[data-action=refresh]').click();ready(school)
                else:raise AssertionError('Real worker export not completed')
                result=download(school,'[data-action=task-download]','records-export.xlsx');assert zipfile.is_zipfile(result)
                check('真实后台任务与Excel下载',school)
                nav(teacher,'assessment');teacher.locator(f'[data-action=assessment][data-id="{data["primary_assessment"]}"]').click()
                assert teacher.locator(f'[data-action=assess-action][data-id="confirm|{data["primary_assessment"]}"]').count()==1
                report['primary_demo_preserved']=True;check('主教师的现场演示仍待本人确认',teacher)
                if any(r['status']>=500 for r in report['requests']):raise AssertionError('Server errors observed')
                report['status']='PASS';report['normal_browser_business_verified']=True
            finally:
                for ctx in contexts:ctx.close()
                browser.close()
    except Exception as exc:
        report['status']='BLOCKED' if 'ERR_BLOCKED_BY_ADMINISTRATOR' in str(exc) or 'CERT_' in str(exc) else 'FAILED'
        report['error']=str(exc)[:1800];report['normal_browser_business_verified']=False
    report['finished_at']=dt.datetime.now(dt.timezone.utc).isoformat();secure_json(out/'report.json',report)
    print(json.dumps({'status':report['status'],'passed_checks':len(report['checks']),'report':str(out/'report.json'),
      'primary_demo_preserved':report['primary_demo_preserved'],'production_acceptance':False},ensure_ascii=False));return 0 if report['status']=='PASS' else 2

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for n in ('origin','credentials','data-summary','mysql-proof','output'):ap.add_argument('--'+n,required=True)
    ap.add_argument('--confirm-synthetic-writes',action='store_true');ap.add_argument('--headed',action='store_true')
    ap.add_argument('--channel',default='');ap.add_argument('--executable',default='')
    a=ap.parse_args()
    try:return run(a)
    except (Blocked,OSError,ValueError,ImportError) as exc:
        print(json.dumps({'status':'BLOCKED','reason':str(exc),'browser_verified':False},ensure_ascii=False));return 2
if __name__=='__main__':raise SystemExit(main())
