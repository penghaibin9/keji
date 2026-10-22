"""Exercise context help in an explicitly isolated, synthetic loopback lab.

Normal login and real DOM only. Never accepts a production origin or writes a real-school database.
"""
from pathlib import Path
import argparse, json, re, sys, subprocess
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
ORIGIN='http://127.0.0.1:8794'
FORM_ACTIONS={
 'apply_course':[('teacher-apply','courses|app-course-new')],
 'apply_project':[('teacher-apply','projects|social-project-new')],
 'apply_base':[('teacher-apply','bases|app-base-new')],
 'apply_trainer':[('teacher-apply','trainer|')],
 'qualifications':[('qualification-form','')],
 'notices':[('notice-form','')],
 'records':[('record-form',''),('participation-form','')],
 'outcomes':[('social-resource-new','achievement')],
 'courses':[('social-course-new','')],
 'trainers':[('social-resource-new','trainer')],
 'permissions':[('org-form',''),('user-form','')],
 'rules':[('period-form',''),('org-rule-form',''),('rule-form','')],
 'imports':[('import-form','')],
 'policy':[('social-policy-new',''),('social-duties','')],
 'annual':[('social-annual-new','')],
}

def load_topics():
    data=subprocess.check_output(['node','--input-type=module','-e',"import {HELP_TOPICS} from './frontend/help-content.js'; console.log(JSON.stringify(HELP_TOPICS));"],cwd=ROOT)
    return json.loads(data)

def login(browser,username,password):
    ctx=browser.new_context(viewport={'width':1440,'height':1000})
    p=ctx.new_page();p.set_default_timeout(10000)
    p.goto(ORIGIN);p.locator('#login-local-tab').click()
    p.locator('#username').fill(username)
    try:p.locator('#password').fill(password)
    except Exception:
        ctx.close();raise RuntimeError('演示密码框无法使用，已停止；不输出凭据。') from None
    p.locator('#login-form button[type=submit]').click();p.locator('#content h1').wait_for()
    identity=p.request.get(ORIGIN+'/api/auth/me').json()
    if identity.get('environment')!='test' or identity.get('school_name')!='操作教学演示学校（虚构资料）':
        ctx.close();raise ValueError('Refusing a service other than the owned synthetic teaching lab')
    return ctx,p

def nav(p,topic):
    p.goto(ORIGIN+'/#'+topic)
    p.locator('#content h1').wait_for();p.locator('.busy-panel').wait_for(state='detached')
    p.wait_for_timeout(150)

def click_action(p,selector):
    visible=p.locator(selector+':visible')
    if not visible.count():
        ancestors=p.locator(selector).first.locator('xpath=ancestor::details')
        for i in range(ancestors.count()):
            parent=ancestors.nth(i)
            if parent.get_attribute('open') is None and parent.locator('summary').first.is_visible():parent.locator('summary').first.click()
    p.locator(selector+':visible').first.click()

def extract_fields(p):
    return p.evaluate("async()=>{const m=await import('/assets/help-system.js?v=20261022');return m.fieldsIn(document.querySelector('#modal-root'))}")

def capture_form(p,topic,out,forms,index,metadata):
    root=p.locator('#modal-root');root.locator('#edit-form').wait_for()
    title=root.locator('.modal-head h2').inner_text()
    fields=extract_fields(p)
    entry={'title':title,'fields':fields,**metadata}
    if not any(f['title']==title and f['fields']==fields for f in forms.setdefault(topic,[])):forms[topic].append(entry)
    root.screenshot(path=str(out/f'{topic}-form-{index}.png'))
    return fields

def run(args):
    lab=Path(args.lab).resolve()
    if lab.name!='integrated-help-20261022' or not (lab/'synthetic.sqlite').is_file():raise ValueError('Requires the owned synthetic help lab')
    password=json.loads((lab/'private-login.json').read_text(encoding='utf-8'))['password']
    out=lab/'browser';out.mkdir(exist_ok=True)
    report={'environment':'独立虚构演示库','real_browser':True,'production_acceptance':False,'checks':[],'pages':[],'errors':[]}
    forms={};topics=load_topics();available={}
    with sync_playwright() as pw:
        b=pw.chromium.launch(headless=True)
        for user,role in [('teacher','teacher'),('depthead','dept'),('collegehead','college'),('schooladmin','school')]:
            ctx,p=login(b,user,password);p.on('pageerror',lambda e:report['errors'].append(str(e)))
            # Read current menu links, including grouped navigation, without granting permissions.
            nav(p,'help')
            allowed=p.locator('[data-help-library] [data-action=nav]').evaluate_all("es=>es.map(e=>e.dataset.id)")+['help']
            for t in topics:
                ident=t['id']
                if ident not in allowed or (ident in available and ident not in FORM_ACTIONS):continue
                nav(p,ident)
                if not p.locator('#content [data-open-help]').count():
                    report['errors'].append(ident+':缺少帮助入口');continue
                p.locator('#content [data-open-help]').click();p.locator('.help-panel').wait_for()
                assert p.locator('#context-help-title').inner_text()
                p.keyboard.press('Escape');assert not p.locator('.help-panel').count()
                p.screenshot(path=str(out/f'{ident}.png'))
                available.setdefault(ident,{'user':user,'role':role})
                buttons=p.locator('#content [data-action]').evaluate_all("es=>es.map(e=>({action:e.dataset.action,id:e.dataset.id||'',label:e.textContent.trim()}))")
                report['pages'].append({'page':ident,'role':role,'buttons':buttons})
                for index,(action,value) in enumerate(FORM_ACTIONS.get(ident,[])):
                    candidates=p.locator(f'#content [data-action="{action}"][data-id="{value}"]')
                    if not candidates.count():continue
                    hidden_parent=candidates.first.locator('xpath=ancestor::details[1]')
                    if hidden_parent.count() and not candidates.first.is_visible():hidden_parent.locator('summary').first.click()
                    candidates.first.click();p.wait_for_timeout(700)
                    if not p.locator('#edit-form').count():continue
                    capture_form(p,ident,out,forms,index,{'user':user,'role':role,'action':action,'action_id':value})
                    p.locator('#modal-root [data-open-help]').click();p.locator('[data-help-tab=fields]').click()
                    assert p.locator('.help-panel .help-field').count()>0
                    p.keyboard.press('Escape')
                    p.locator('#modal-root [data-action=close]:visible').last.click()
                    if p.locator('.unsaved-overlay').count():p.get_by_role('button',name='放弃修改',exact=True).click()
                (out/'available.json').write_text(json.dumps(available,ensure_ascii=False,indent=2),encoding='utf-8')
                (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
                (ROOT/'frontend/help-forms.js').write_text('// 真实隔离浏览器采集，不含输入值。\nexport const HELP_FORMS='+json.dumps(forms,ensure_ascii=False,indent=2)+';\n',encoding='utf-8')
                print('页面核验：'+role+' / '+ident,flush=True)
            ctx.close()
        # Changing help must preserve the exact existing controls, selected files and dirty text.
        ctx,p=login(b,'teacher',password);nav(p,'apply_course')
        p.locator('[data-action=teacher-apply][data-id="courses|app-course-new"]').click()
        p.locator('#edit-form').wait_for()
        inputs=p.locator('#edit-form input[type=text]');inputs.first.fill('帮助保留检查（虚构资料）')
        upload=p.locator('#edit-form input[type=file]')
        if upload.count():upload.first.set_input_files({'name':'演示封面.png','mimeType':'image/png','buffer':(out/'apply_course.png').read_bytes()})
        before=p.locator('#edit-form').evaluate("f=>[...f.elements].map(e=>[e.name,e.value,e.checked,e.files?[...e.files].map(x=>[x.name,x.size]):null])")
        for width in [1440,900,390]:
            p.set_viewport_size({'width':width,'height':900})
            entry=p.locator('#modal-root [data-open-help]');entry.click();p.locator('[data-help-tab=fields]').click()
            p.screenshot(path=str(out/f'preserve-{width}.png'))
            p.keyboard.press('Escape')
            after=p.locator('#edit-form').evaluate("f=>[...f.elements].map(e=>[e.name,e.value,e.checked,e.files?[...e.files].map(x=>[x.name,x.size]):null])")
            assert before==after,'Help changed form content'
            assert entry.evaluate('(e)=>document.activeElement===e'),'Focus not restored'
            assert not p.locator('#app').evaluate('(e)=>e.inert')
            report['checks'].append(f'{width}像素：文字、已选附件、焦点保留')
        ctx.close();b.close()
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'available.json').write_text(json.dumps(available,ensure_ascii=False,indent=2),encoding='utf-8')
    (ROOT/'frontend/help-forms.js').write_text('// 真实隔离浏览器采集，不含输入值。\nexport const HELP_FORMS='+json.dumps(forms,ensure_ascii=False,indent=2)+';\n',encoding='utf-8')
    print(json.dumps({'pages':len(available),'forms':sum(map(len,forms.values())),'errors':report['errors']},ensure_ascii=False),flush=True)
    if report['errors']:raise SystemExit(1)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--lab',required=True);run(parser.parse_args())
