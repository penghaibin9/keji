"""采购修复的真实浏览器回归，复用隔离样本及正常账号。"""
import os
import socket
import threading
import time
from pathlib import Path
import uvicorn
from playwright.sync_api import sync_playwright
from conftest import auth
from support import FIXTURE_PASSWORD
from test_social_training import setup_social, recognized, action, detail, proof
from test_point_review import sent_review, review
from app.main import create_app
from app.models import Setting
from app.social_models import SocialClaim


def test_dept_summary_void_and_preflight_in_browser(recognized,app2,client2,tmp_path):
    claim_id,_=recognized
    with app2.state.sessions() as db:pid=db.get(SocialClaim,claim_id).project_id
    ident=sent_review(client2,claim_id);auth(client2,'teacher')
    fix=action(client2,'point-reviews','social_resource',ident,'agree').json()['item']['data']['correction_id']
    auth(client2,'collegehead');assert action(client2,'corrections','social_resource',fix,'return').status_code==200
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    origin=f'http://127.0.0.1:{port}'
    cfg=app2.state.settings.model_copy(update={'public_origin':origin,'allowed_hosts':'127.0.0.1'})
    app=create_app(cfg);server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error'))
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    output=Path(os.environ.get('ND_BROWSER_EVIDENCE_DIR',str(tmp_path/'screenshots')));output.mkdir(parents=True,exist_ok=True)
    try:
        for _ in range(100):
            if server.started:break
            time.sleep(.05)
        assert server.started
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(origin);page.get_by_role('tab',name='本地账号登录').click();page.locator('#username').fill('depthead');page.locator('#password').fill(FIXTURE_PASSWORD);page.get_by_role('button',name='登录工作台').click()
            page.locator('[data-action="nav"][data-id="projects"]').first.click()
            page.locator('[data-action="social-detail"][data-id="social_project|'+pid+'"]').filter(has_text='查看完整资料').click()
            modal=page.locator('#modal-root')
            modal.get_by_text('本教研室核算单元',exact=True).wait_for()
            modal.locator('details.detail-more-actions > summary').click()
            assert modal.get_by_role('button',name='导出本教研室参与摘要',exact=True).count()==1
            assert not modal.get_by_role('button',name='上传佐证',exact=True).count()
            page.screenshot(path=str(output/'01-教研室项目摘要.png'),animations='disabled')
            page.get_by_role('button',name='关闭窗口').first.click()
            page.goto(origin+'/#recognition');page.reload()
            page.locator('[data-action="social-detail"][data-id="social_resource|'+fix+'"]').click()
            modal.get_by_role('button',name='作废未入账更正',exact=True).click()
            page.locator('#f-reason').fill('浏览器验证：差额填错，作废后重新核对')
            page.locator('button[form="edit-form"]').first.click()
            modal.get_by_role('button',name='返回原认定，重新核对',exact=True).wait_for()
            assert not modal.get_by_role('button',name='提交更正审核',exact=True).count()
            page.screenshot(path=str(output/'02-更正作废留痕.png'),animations='disabled')
            modal.get_by_role('button',name='返回原认定，重新核对',exact=True).click()
            modal.get_by_role('button',name='发现积分有误，发起核对',exact=True).wait_for()
            page.get_by_role('button',name='关闭窗口').first.click()
            auth(client2,'depthead');draft=review(client2,claim_id).json()['item'];proof(client2,'social_resource',draft['id'],draft['version'])
            with app2.state.sessions.begin() as db:
                setting=db.get(Setting,'social_training_duties');setting.value={**setting.value,'secretary':['depthead']}
            page.reload();page.locator('[data-action="social-detail"][data-id="social_resource|'+draft['id']+'"]').click()
            modal.get_by_text('教学秘书环节没有具备权限且无需回避的办理人，请学校管理员在社会培训职责设置中配置替代人员',exact=True).wait_for()
            assert not modal.get_by_role('button',name='发给教师回应',exact=True).count()
            page.screenshot(path=str(output/'03-核对发送前职责检查.png'),animations='disabled')
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
            assert not errors,errors
            browser.close()
    finally:
        server.should_exit=True;thread.join(timeout=10)
    auth(client2,'depthead');assert detail(client2,'social_resource',fix)['item']['state']=='VOID'
