"""Real browser against the actual app with isolated fixture accounts; not school acceptance."""
import socket
import os
import threading
import time
from datetime import date
from pathlib import Path
import uvicorn
from playwright.sync_api import sync_playwright
from app.main import create_app
from app.config import Settings
from app.models import Setting
from app import social_training as st
from PIL import Image
from support import populate, FIXTURE_PASSWORD


def test_social_menu_form_resources_and_refresh_in_browser(tmp_path,monkeypatch):
    monkeypatch.setattr(st,'today',lambda:date(2026,10,8))
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    origin=f'http://127.0.0.1:{port}'
    cfg=Settings(env='test',database_url='sqlite:///'+str(tmp_path/'browser.sqlite'),secure_cookie=False,public_origin=origin,allowed_hosts='127.0.0.1',storage_dir=tmp_path/'files')
    app=create_app(cfg);populate(app.state.engine)
    with app.state.sessions.begin() as db:db.add(Setting(key='social_training_duties',value={'coordinator':['schooladmin']}))
    proof=tmp_path/'fixture-evidence.png';Image.new('RGB',(10,10),'white').save(proof)
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error'))
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    try:
        for _ in range(100):
            if server.started:break
            time.sleep(.05)
        assert server.started
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(origin);page.locator('#username').fill('schooladmin');page.locator('#password').fill(FIXTURE_PASSWORD);page.get_by_role('button',name='登录工作台').click()
            page.locator('[data-action="nav"][data-id="projects"]').first.click()
            page.locator('.pagehead').get_by_role('button',name='申报培训项目',exact=True).click()
            for key,value in {'code':'BROWSER-P1','name':'隔离演示 技能培训项目','cohort':'第一期','expected_income':'0','expected_participants':'30','expected_outcomes':'掌握基础技能','start_date':'2026-10-01','end_date':'2026-10-08'}.items():page.locator('#f-'+key).fill(value)
            page.locator('#owner_id-search').fill('J001');page.locator('#f-category input[value="community"]').check(force=True)
            # 学校账号申报须选承办学院（夹具有两个学院，不会自动选中）
            page.locator('input[name="org_id"]').nth(1).check(force=True)
            # 项目层级、授课场景没有默认值，须由申报人选择（与后端必填一致）
            page.locator('#f-level input[value="school"]').check(force=True);page.locator('#f-scene input[value="ordinary"]').check(force=True)
            page.locator('#f-venue_type input[value="campus"]').check(force=True);page.locator('#f-venue_place').fill('隔离楼101教室')
            page.locator('#f-reason').fill('隔离浏览器验证项目申报')
            page.locator('button[form="edit-form"]').first.click()
            # 保存草稿后直接打开项目详情，提示下一步上传材料并提交备案
            page.locator('#modal-root h2',has_text='隔离演示 技能培训项目').wait_for()
            assert page.locator('#modal-root').get_by_role('button',name='提交审核备案').count()==1
            page.reload();page.get_by_text('隔离演示 技能培训项目',exact=True).wait_for()
            output=Path(os.environ.get('SOCIAL_BROWSER_EVIDENCE_DIR',Path(__file__).resolve().parents[2]/'evidence/social-20261008'));output.mkdir(parents=True,exist_ok=True)
            page.screenshot(path=str(output/'01-projects-desktop.png'),full_page=True)
            page.locator('[data-action="nav"][data-id="courses"]').first.click()
            page.locator('.pagehead').get_by_role('button',name='登记培训课程',exact=True).click()
            page.locator('#f-code').fill('BROWSER-C1');page.locator('#f-name').fill('隔离演示 实操课程');page.locator('#f-reason').fill('登记课程验证')
            page.locator('#f-project_code').select_option('BROWSER-P1')
            page.locator('button[form="edit-form"]').first.click();page.get_by_text('隔离演示 实操课程',exact=True).wait_for()
            page.locator('.pagehead').get_by_role('button',name='登记课程资源',exact=True).click()
            for key,value in {'code':'VIDEO-1','name':'隔离演示 视频资源','recognition':'学校确认的演示资源','duration_minutes':'12.5','reason':'登记视频时长验证'}.items():page.locator('#f-'+key).fill(value)
            page.locator('input[name="org_id"]').nth(1).check(force=True)
            # 保存后直接打开该资源详情（列表里也有同名一行）
            page.locator('button[form="edit-form"]').first.click();page.locator('#modal-root h2',has_text='隔离演示 视频资源').wait_for()
            page.screenshot(path=str(output/'02-courses-resources.png'),full_page=True)
            page.set_viewport_size({'width':390,'height':844});page.reload();page.get_by_text('隔离演示 视频资源',exact=True).wait_for()
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth+1')
            page.screenshot(path=str(output/'03-courses-mobile.png'),full_page=True)
            page.set_viewport_size({'width':1440,'height':1000})
            page.get_by_role('button',name='查看资源',exact=True).click();page.get_by_role('button',name='查看详情',exact=True).click()
            page.get_by_text('学校确认的演示资源',exact=True).wait_for();page.get_by_role('button',name='关闭窗口').first.click()
            page.locator('[data-action="nav"][data-id="projects"]').first.click()
            def open_project():
                # 保存后异步回到最新详情；等待保存完成，避免提前关闭表单后详情又遮住列表。
                if not page.locator('#modal-root .modal').count():
                    page.get_by_role('button',name='查看与办理',exact=True).first.click()
                page.get_by_role('dialog',name='隔离演示 技能培训项目',exact=True).wait_for()
            def confirm(label):
                page.get_by_role('button',name=label,exact=True).click();page.locator('#f-reason').fill('隔离正常账号浏览器验证');page.locator('#f-basis').fill('隔离审核依据');page.locator('button[form="edit-form"]').first.click()
            open_project();page.get_by_role('button',name='上传佐证',exact=True).click();page.locator('input[type=file]').set_input_files(str(proof));page.locator('#f-reason').fill('隔离材料上传');page.locator('button[form="edit-form"]').first.click()
            open_project();confirm('提交审核备案');page.get_by_text('待审核备案',exact=True).first.wait_for()
            open_project();confirm('完成审核备案');page.get_by_text('已备案',exact=True).first.wait_for()
            open_project();page.get_by_role('button',name='导入参训明细',exact=True).click()
            header=page.locator('#f-rows').input_value();line='\t'.join(['UNIT-1','BROWSER-C1','CLASS-1','实操模块','2026-10-08','LEARNER-1','否','否','是','是','是','是','是','','J001','主讲','校内','隔离完整参训依据'])
            page.locator('#f-rows').fill(header+'\n'+line);page.locator('#f-reason').fill('隔离参训明细预检');page.locator('button[form="edit-form"]').first.click()
            page.get_by_role('button',name='确认整批入库',exact=True).click();open_project();page.get_by_role('button',name='提交结项',exact=True).click()
            for key,value in {'closed_on':'2026-10-08','outcome_report':'隔离完整结项报告','satisfaction':'96','finance_reference':'公益零收入确认','settlement_on':'2026-10-08','reason':'隔离结项核验'}.items():page.locator('#f-'+key).fill(value)
            for key in ['plan','filing_form','roster','attendance','hours','process','assessment','outcomes']:page.locator('#f-checked_'+key).check()
            page.locator('button[form="edit-form"]').first.click();page.get_by_text('待结项核验',exact=True).first.wait_for()
            open_project();confirm('核验通过结项');page.get_by_text('已结项',exact=True).first.wait_for()
            page.reload();page.get_by_text('已结项',exact=True).first.wait_for();open_project()
            page.screenshot(path=str(output/'04-project-closed.png'),full_page=True,animations='disabled')
            with page.expect_download() as download:page.get_by_role('button',name='导出办理材料',exact=True).click()
            assert download.value.suggested_filename.endswith('.xlsx')
            page.get_by_role('button',name='打印当前材料',exact=True).click();assert page.locator('.print-sheet').count()==1
            page.emulate_media(media='print');page.evaluate("document.body.classList.add('print-mode')")
            page.pdf(path=str(output/'项目办理打印样张.pdf'),format='A4',print_background=True)
            page.screenshot(path=str(output/'05-print-layout.png'),full_page=True)
            page.evaluate("document.body.classList.remove('print-mode')");page.emulate_media(media='screen')
            assert page.locator('img').evaluate_all('(images)=>images.every(x=>x.complete&&x.naturalWidth>0)')
            assert not errors,errors
            browser.close()
    finally:
        server.should_exit=True;thread.join(timeout=10)
