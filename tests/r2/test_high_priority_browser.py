"""真实浏览器只连接临时合成库，验证认领待确认、刷新及管理员批准后的回读。"""
from pathlib import Path
import socket
import threading
import time
import uvicorn
from playwright.sync_api import sync_playwright, expect
from app.main import create_app
from conftest import auth, post
from support import FIXTURE_PASSWORD
from test_cx_unmatched import seed_unmatched, cx_rows


def test_claim_waits_for_confirmation_in_real_browser(app2,client2,tmp_path):
    auth(client2,'schooladmin');seed_unmatched(client2,app2)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    origin=f'http://127.0.0.1:{port}'
    cfg=app2.state.settings.model_copy(update={'public_origin':origin,'allowed_hosts':'127.0.0.1'})
    app=create_app(cfg)
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error'))
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    try:
        for _ in range(100):
            if server.started:break
            time.sleep(.05)
        assert server.started
        with sync_playwright() as pw:
            launch={} if Path(pw.chromium.executable_path).exists() else {'channel':'msedge'}
            browser=pw.chromium.launch(headless=True,**launch)
            try:
                page=browser.new_page(viewport={'width':1440,'height':1000})
                page.set_default_timeout(15000);errors=[]
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(origin)
                page.get_by_role('tab',name='本地账号登录').click()
                page.locator('#username').fill('teacher');page.locator('#password').fill(FIXTURE_PASSWORD)
                page.get_by_role('button',name='登录工作台').click()
                page.locator('[data-action="nav"][data-id="credits"]').first.click()
                page.locator('[data-action="credits-tab"][data-id="cx"]').click()
                page.locator('[data-action="cx-claim"]').first.click()
                modal=page.locator('#modal-root')
                expect(modal).to_contain_text('确认后课程才归到本人名下')
                modal.get_by_role('button',name='是我的，认领',exact=True).first.click()
                modal.get_by_text('等管理员确认',exact=True).wait_for()
                assert cx_rows(app2)[('phone138','X1')]==(True,None)
                page.reload();page.locator('[data-action="cx-claim"]').first.click()
                modal.get_by_text('等管理员确认',exact=True).wait_for()
                assert page.evaluate("getComputedStyle(document.querySelector('.sidebar')).position")=='fixed'
                assert page.evaluate("Array.from(document.images).filter(x=>x.getBoundingClientRect().width>0).every(x=>x.complete&&x.naturalWidth>0)")
                page.screenshot(path=str(tmp_path/'claim-pending.png'))
                r=post(client2,'/api/reference/cx-claims/decide',{'login':'phone138','staff_no':'J001','decision':'approve'})
                assert r.status_code==200,r.text
                page.reload();page.get_by_text('线上课X1',exact=True).first.wait_for()
                claims=client2.get('/api/reference/cx-claims').json()['items']
                assert next(x for x in claims if x['login']=='phone138')['state']=='APPROVED'
                assert cx_rows(app2)[('J001','X1')]==(True,'teacher')
                assert not errors,errors
            finally:browser.close()
    finally:
        server.should_exit=True;thread.join(timeout=10)
        assert not thread.is_alive()
