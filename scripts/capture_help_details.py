"""Capture conditional business forms after synthetic fixture workflows are prepared."""
from pathlib import Path
import argparse,json,subprocess
from playwright.sync_api import sync_playwright
from check_help_browser import ROOT,login,nav,capture_form,click_action

def run(args):
    lab=Path(args.lab).resolve()
    if lab.name!='integrated-help-20261022' or not (lab/'synthetic.sqlite').exists():raise ValueError('Owned synthetic lab required')
    password=json.loads((lab/'private-login.json').read_text(encoding='utf-8'))['password']
    scenes=json.loads((lab/'teaching-workflows.json').read_text(encoding='utf-8'))
    forms=json.loads(subprocess.check_output(['node','--input-type=module','-e',"import {HELP_FORMS} from './frontend/help-forms.js';console.log(JSON.stringify(HELP_FORMS))"],cwd=ROOT))
    targets=[('projects','collegehead','college','social-close','',[{'action':'social-detail','id':'social_project|'+scenes['open']}]),('recognition','teacher','teacher','social-claim-new','',[]),('trainers','collegehead','college','app-trainer-new','external',[]),('rules','schooladmin','school','org-rule-form','',[]),('rules','schooladmin','school','rule-form','',[])]
    with sync_playwright() as pw:
        browser=pw.chromium.launch()
        for topic,user,role,action,value,setup in targets:
            ctx,p=login(browser,user,password);nav(p,topic)
            for step in setup:
                click_action(p,f'#content [data-action="{step["action"]}"][data-id="{step["id"]}"]')
                p.locator('#modal-root:not(.hidden) .modal-head h2').wait_for()
            scope='#modal-root' if setup else '#content'
            target=p.locator(f'{scope} [data-action="{action}"][data-id="{value}"]').first
            if not target.is_visible():target.locator('xpath=ancestor::details[1]').locator('summary').first.click()
            target.click();p.locator('#edit-form').wait_for()
            title=p.locator('#modal-root .modal-head h2').inner_text()
            forms[topic]=[f for f in forms.get(topic,[]) if f['title']!=title]
            capture_form(p,topic,lab/'browser',forms,0,{'user':user,'role':role,'action':action,'action_id':value,'scope':scope,'setup':setup})
            print('补充采集：'+topic,flush=True);ctx.close()
        browser.close()
    (ROOT/'frontend/help-forms.js').write_text('// 真实隔离浏览器采集，不含输入值。\nexport const HELP_FORMS='+json.dumps(forms,ensure_ascii=False,indent=2)+';\n',encoding='utf-8')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--lab',required=True);run(parser.parse_args())
