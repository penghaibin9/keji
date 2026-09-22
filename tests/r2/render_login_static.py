"""Offline appearance check of the real loginView only; NOT a network/login E2E.

No API bridge, mocked response, role fixture, or network-policy modification.
The normal automatic authentication call is omitted solely for this offline render.
"""
from pathlib import Path
from hashlib import sha256
import json,re,sys
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]
out=ROOT/'evidence/r2/static-login';out.mkdir(parents=True,exist_ok=True)
front=ROOT/'frontend'
source=(front/'app.js').read_text()
bootstrap="(async()=>{try{await boot()}catch{if(!me)loginView()}})();"
assert source.count(bootstrap)==1
script=re.sub(r'^import .*?;\n','',source,flags=re.M).replace(bootstrap,'')
icons=(front/'icons.js').read_text().replace('export const ','const ')
scope=(front/'scope.js').read_text().replace('export const ','const ').replace('export function ','function ')
css=(front/'styles.css').read_text()+'\n'+(front/'integration.css').read_text()
result={'mode':'OFFLINE_REAL_LOGINVIEW_APPEARANCE_ONLY','native_browser_login_passed':False,'network_requests':[],
 'app_js_sha256':sha256(source.encode()).hexdigest(),'checks':[]}
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
    for width in (1440,390):
        page=browser.new_page(viewport={'width':width,'height':960},device_scale_factor=1)
        page.on('request',lambda request:result['network_requests'].append(request.url))
        page.route('**/*',lambda route:route.abort())
        page.set_content('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><style>'+css+'</style></head><body><div id="app"></div><div id="modal-root" class="modal-overlay hidden"></div><div id="toasts" class="toast-stack"></div></body></html>')
        page.evaluate(icons+'\n'+scope+'\n'+script+'\nloginView();')
        page.locator('#login-form').wait_for(state='visible')
        info=page.evaluate('({width:innerWidth,scroll:document.documentElement.scrollWidth,form:!!document.querySelector("#login-form"),passwordType:document.querySelector("#password").type})')
        page.screenshot(path=str(out/f'login-{width}.png'),full_page=True)
        if info['scroll']>width:
            info['overflow']=page.evaluate('Array.from(document.querySelectorAll("*")).map(e=>({tag:e.tagName,cls:e.className,width:e.getBoundingClientRect().width,right:e.getBoundingClientRect().right})).filter(x=>x.right>innerWidth)')
            (out/'failure-layout.json').write_text(json.dumps(info,ensure_ascii=False,indent=2))
        assert info['form'] and info['passwordType']=='password' and info['scroll']<=width,info
        result['checks'].append({'width':width,'result':'PASS','dom':info});page.close()
    browser.close()
assert not result['network_requests'],result['network_requests']
(out/'appearance-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps(result,ensure_ascii=False))
