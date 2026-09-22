"""Native Chromium DOM clicks -> same-origin fetch -> complete app -> SQLite.
No page.route, request mocking, API bridge, or artificial response injection.
Fixtures and HTTP transport are clearly distinguished from school acceptance.
"""
from pathlib import Path
import io,json,time,re,sys
from PIL import Image
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'evidence/r2/browser-native';OUT.mkdir(parents=True,exist_ok=True)
BASE='http://127.0.0.1:8768'
OLD='FixtureOnly_2026_Local';NEW='BrowserChanged_2026_Local'
result={'mode':'NATIVE_CHROMIUM_HTTP_COOKIE_SQLITE_SYNTHETIC','mock_routes':False,'tls_tested':False,'mysql_tested':False,
  'school_acceptance':False,'steps':[],'requests':[],'page_errors':[],'cookie_security':[]}
seq=0

def save(): (OUT/'browser-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
def snap(page,name):
    global seq
    seq+=1;path=OUT/f'{seq:02d}-{name}.png';page.screenshot(path=str(path),full_page=True)
    result['steps'].append({'step':name,'status':'PASS','screenshot':path.name});save()
def submit(page):page.locator('button[type=submit][form=edit-form]').click()
def reason(page,text='浏览器合成样本核验'):
    page.locator('#f-reason').fill(text)
    if page.locator('#f-basis').count():page.locator('#f-basis').fill('隔离测试材料，不是学校正式样本')
def close(page):
    if page.locator('#modal-root:not(.hidden)').count():page.locator('#modal-root [data-action=close]').first.click()
def nav(page,dest):
    close(page);page.locator(f'#sidebar [data-action=nav][data-id="{dest}"]').click()
    expect(page.locator('#content .busy-panel')).to_have_count(0)
    expect(page.locator('#content h1')).to_be_visible()
def row_open(page,title,action):
    row=page.locator('#content table tbody tr').filter(has_text=title).first
    expect(row).to_be_visible();row.locator(f'[data-action="{action}"]').click()
    expect(page.locator('#modal-root:not(.hidden)')).to_be_visible()
def workflow(page,selector):
    page.locator(selector).click();reason(page);submit(page)
    expect(page.locator('#edit-form')).to_have_count(0)

with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
    pages={}
    try:
        for name in ('teacher','depthead','collegehead','schooladmin'):
            context=browser.new_context(viewport={'width':1440,'height':1000},locale='zh-CN',timezone_id='Asia/Shanghai')
            page=context.new_page();pages[name]=page;page.set_default_timeout(12000)
            page.on('pageerror',lambda exc:result['page_errors'].append(str(exc)))
            def response(resp,role=name):
                if '/api/' in resp.url:
                    result['requests'].append({'role':role,'method':resp.request.method,'path':resp.url.split(BASE)[-1],'status':resp.status})
            page.on('response',response)
            page.goto(BASE);expect(page.locator('#login-form')).to_be_visible()
            page.locator('#username').fill(name);page.locator('#password').fill(OLD)
            page.locator('#login-form button[type=submit]').click()
            # A rerun on the same isolated lab can use the changed fixture password.
            page.wait_for_timeout(300)
            if page.locator('#login-error .error-text').count():
                page.locator('#password').fill(NEW);page.locator('#login-form button[type=submit]').click()
            page.wait_for_selector('#sidebar')
            if page.locator('#f-old_password').count():
                page.locator('#f-old_password').fill(OLD);page.locator('#f-new_password').fill(NEW);page.locator('#f-repeat').fill(NEW);submit(page)
                expect(page.locator('#login-form')).to_be_visible()
                page.locator('#username').fill(name);page.locator('#password').fill(NEW);page.locator('#login-form button[type=submit]').click()
            expect(page.locator('#content h1')).to_have_text('工作总览')
            expect(page.locator('#content .kpis')).to_be_visible()
            cookies=[{k:v for k,v in cookie.items() if k in {'name','secure','httpOnly','sameSite','path'}} for cookie in context.cookies()]
            result['cookie_security'].append({'role':name,'cookies':cookies})
            assert all(c['httpOnly'] and c['sameSite']=='Strict' for c in cookies)
            snap(page,name+'-login-and-home')
        teacher,dept,college,school=(pages[k] for k in ('teacher','depthead','collegehead','schooladmin'))
        nav(teacher,'qualifications');teacher.locator('#content [data-action=qualification-form]').click()
        teacher.locator('#f-category').select_option('职业资格');teacher.locator('#f-name').fill('浏览器真实材料证书')
        teacher.locator('#f-certificate_no').fill('BROWSER-'+str(int(time.time())))
        teacher.locator('#f-issuer').fill('隔离样本发证单位');teacher.locator('#f-obtained').fill('2026-01-01');teacher.locator('#f-expires').fill('2026-12-31')
        reason(teacher);submit(teacher)
        expect(teacher.locator('#modal-root [data-action=upload]')).to_be_visible()
        ident=teacher.locator('#modal-root [data-action=upload]').get_attribute('data-id').split('|')[1]
        teacher.locator('#modal-root [data-action=upload]').click()
        image=io.BytesIO();Image.new('RGB',(120,70)).save(image,format='PNG')
        teacher.locator('#f-file').set_input_files({'name':'浏览器实传佐证.png','mimeType':'image/png','buffer':image.getvalue()})
        reason(teacher,'浏览器真实上传佐证');submit(teacher)
        expect(teacher.locator('#modal-root .upload-meta')).to_be_visible();snap(teacher,'qualification-uploaded-bytes')
        workflow(teacher,'#modal-root [data-action=qual-action][data-id^="submit|"]');snap(teacher,'qualification-submitted')
        nav(dept,'qualifications');row_open(dept,'浏览器真实材料证书','qualification')
        workflow(dept,'#modal-root [data-action=qual-action][data-id^="return|"]');snap(dept,'department-returned')
        nav(teacher,'qualifications');row_open(teacher,'浏览器真实材料证书','qualification')
        teacher.locator('#modal-root [data-action=qualification-form]').click();teacher.locator('#f-name').fill('浏览器补充后材料证书');reason(teacher,'退回后补充说明');submit(teacher)
        workflow(teacher,'#modal-root [data-action=qual-action][data-id^="submit|"]');snap(teacher,'teacher-resubmitted')
        nav(dept,'qualifications');row_open(dept,'浏览器补充后材料证书','qualification')
        workflow(dept,'#modal-root [data-action=qual-action][data-id^="approve|"]');snap(dept,'qualification-approved-with-history')
        # Create both rules using the existing UI, not by inserting rule fixtures.
        for kind,title in [('points','浏览器积分规则'),('assessment','浏览器考核规则')]:
            nav(school,'rules');school.locator('#content [data-action=rule-form][data-id=""]').click()
            school.locator('#f-kind').select_option(kind);school.locator('#f-name').fill(title)
            school.locator('#f-period_id').select_option('period2026')
            school.locator('#rule-rows [data-r=weight]').fill('100');school.locator('#rule-rows [data-r=target]').fill('10')
            reason(school);submit(school);expect(school.locator('#edit-form')).to_have_count(0)
            row_open(school,title,'rule');school.locator('#modal-root [data-action=trial]').click()
            school.locator('#calc-people input[value=teacher]').check();submit(school)
            expect(school.locator('#trial-result')).to_contain_text('试算结果');snap(school,kind+'-rule-trial')
            workflow(school,'#modal-root [data-action=rule-action][data-id^="activate|"]')
            snap(school,kind+'-rule-activated')
            nav(school,'points' if kind=='points' else 'assessment')
            school.locator('#content [data-action=calculate]').click();school.locator('#f-period_id').select_option('period2026')
            school.locator('#calc-people input[value=teacher]').check();reason(school);submit(school)
            expect(school.locator('#modal-root')).to_contain_text('计算批次已完成');snap(school,kind+'-calculated-database')
            if kind=='points':
                nav(teacher,'points');workflow(teacher,'#content [data-action=balance-action]');snap(teacher,'points-owner-confirmed')
        # Real successive identities, no reviewer-role switch in one session.
        for who,state in [('teacher','教研室确认'),('depthead','学院确认'),('collegehead','学校审核'),('schooladmin','待归档')]:
            page=pages[who];nav(page,'assessment');row_open(page,'测试教师一','assessment')
            workflow(page,'#modal-root [data-action=assess-action][data-id^="confirm|"]')
            expect(page.locator('#modal-root .flow-step.active')).to_contain_text(state)
            snap(page,who+'-assessment-confirmed')
        assessment_id=school.locator('#modal-root [data-action=assess-action][data-id^="archive|"]').get_attribute('data-id').split('|')[1]
        workflow(school,'#modal-root [data-action=assess-action][data-id^="archive|"]')
        expect(school.locator('#modal-root .state-lock')).to_contain_text('已归档');snap(school,'assessment-archived-sha256')
        before=school.request.get(BASE+'/api/assessments/'+assessment_id).json()['assessment']
        school.locator('#modal-root [data-action=print]').click()
        expect(school.locator('.print-sheet')).to_have_count(1)
        school.pdf(path=str(OUT/'实际考核打印_合成样本.pdf'),format='A4',print_background=True)
        result['steps'].append({'step':'native-browser-assessment-print','status':'PASS','pdf':'实际考核打印_合成样本.pdf'})
        nav(school,'cockpit');school.locator('#filters input[name=project_code]').fill('P1');school.locator('#filters button[type=submit]').click()
        expect(school.locator('#content .kpis')).to_be_visible()
        school.locator('#content .kpis [data-action=scope-nav][data-id=records]').first.click()
        expect(school.locator('#content h1')).to_have_text('培训数据台账')
        assert 'project_code=P1' in school.url
        expect(school.locator('#filters input[name=project_code]')).to_have_value('P1');snap(school,'filtered-cockpit-drill-preserved')
        school.go_back();expect(school.locator('#content h1')).to_have_text('学校管理驾驶舱')
        expect(school.locator('#filters input[name=project_code]')).to_have_value('P1')
        snap(school,'browser-back-preserved-filter')
        # Editing the current certificate must not alter archived evidence.
        nav(teacher,'qualifications');row_open(teacher,'浏览器补充后材料证书','qualification')
        teacher.locator('#modal-root [data-action=qualification-form]').click();teacher.locator('#f-name').fill('归档后新版本证书');reason(teacher,'归档后修订只影响新版本');submit(teacher)
        after=school.request.get(BASE+'/api/assessments/'+assessment_id).json()['assessment']
        assert before['archive']==after['archive'] and before['archive_sha256']==after['archive_sha256']
        snap(teacher,'certificate-revised-archive-unchanged')
        # Verify native authenticated download reaches bytes, not an API bridge.
        q=teacher.request.get(BASE+'/api/qualifications/'+ident).json();attachment=q['attachments'][0]
        response=teacher.request.get(BASE+'/api/attachments/'+attachment['id']+'/download')
        assert response.status==200 and response.body()==image.getvalue()
        result['readback']={'qualification_id':ident,'assessment_id':assessment_id,'archive_sha256':after['archive_sha256'],
            'archive_unchanged_after_qualification_revision':True,'attachment_bytes_equal':True}
        assert not result['page_errors'],result['page_errors']
        result['status']='PASS';save()
    except Exception as ex:
        result['status']='FAIL';result['failure']=str(ex)
        for name,page in pages.items():
            try:page.screenshot(path=str(OUT/f'failure-{name}.png'),full_page=True)
            except Exception:pass
        save();raise
    finally:browser.close()
print(json.dumps({'status':result['status'],'steps':len(result['steps']),'api_responses':len(result['requests']),'page_errors':len(result['page_errors'])}))
