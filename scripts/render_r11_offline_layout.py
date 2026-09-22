#!/usr/bin/env python3
"""Render captured real UI output with synthetic API data, WITHOUT navigation/network.
This is static layout QA, not browser business E2E or evidence of school connections.
"""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]

def main():
    source=ROOT/'evidence/r11/portal_control/rendered';out=ROOT/'evidence/r11/layout';out.mkdir(parents=True,exist_ok=True)
    results=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True)
        try:
            page=browser.new_page(viewport={'width':1440,'height':1050},device_scale_factor=1)
            requests=[];page.on('request',lambda request:requests.append(request.url))
            for name in ['schooladmin_home','schooladmin_sync','schooladmin_hub','schooladmin_guide','schooladmin_assessment','schooladmin_records','teacher_home','depthead_home','collegehead_home','schooladmin_hub_batches','schooladmin_hub_proof']:
                page.set_content((source/(name+'.html')).read_text(),wait_until='load')
                page.screenshot(path=str(out/(name+'.png')),full_page=True)
                metrics=page.evaluate('''() => ({title:document.querySelector('h1')?.textContent,viewport:innerWidth,width:document.documentElement.scrollWidth,mainWidth:document.querySelector('main')?.getBoundingClientRect().width,bodyText:document.body.textContent.includes('SAMPLE-001')})''')
                results.append({'page':name,'width':1440,'horizontal_overflow':metrics['width']>1442,'placeholder_present':metrics['bodyText'],'title':metrics['title']})
            for width in [1280,900,390]:
                page.set_viewport_size({'width':width,'height':900})
                page.set_content((source/'schooladmin_home.html').read_text(),wait_until='load')
                measure=page.evaluate('({width:document.documentElement.scrollWidth,viewport:innerWidth})')
                page.screenshot(path=str(out/f'home_{width}.png'),full_page=True)
                results.append({'page':'schooladmin_home','width':width,'horizontal_overflow':measure['width']>width+2})
            report={'status':'PASS' if not any(x['horizontal_overflow'] or x.get('placeholder_present') for x in results) else 'NEEDS_FIX','scope':'offline set_content of actual renderer output captured from real HTTP + synthetic SQLite control','native_business_navigation_tested':False,'external_requests':requests,'checks':results}
            (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False,indent=2))
        finally:browser.close()
if __name__=='__main__':main()
