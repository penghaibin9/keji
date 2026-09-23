"""Isolated real-browser UI smoke with synthetic accounts and a temporary SQLite DB."""
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'backend'), str(ROOT/'tests/r2')]
from app.main import create_app
from app.config import Settings
from support import populate, FIXTURE_PASSWORD
from test_integration_intake import prepare_school_workbook
import uvicorn
from playwright.sync_api import sync_playwright


def main():
    out = ROOT/'evidence/integration-closeout/browser'
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='keji-browser-') as temporary:
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        origin = 'http://127.0.0.1:'+str(port)
        cfg = Settings(env='test', database_url='sqlite:///'+str(Path(temporary)/'browser.sqlite'),
            storage_dir=Path(temporary)/'files', secure_cookie=False, public_origin=origin, allowed_hosts='127.0.0.1')
        app = create_app(cfg)
        populate(app.state.engine)
        server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, log_level='warning'))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        for _ in range(100):
            if server.started:
                break
            time.sleep(.1)
        checks, errors, requests = [], [], []
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(channel='msedge', headless=True)
                context = browser.new_context(viewport={'width': 1440, 'height': 1000}, accept_downloads=True)
                page = context.new_page()
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.on('response', lambda response: requests.append({'path': response.url.split(origin)[-1].split('?')[0], 'status': response.status}) if response.url.startswith(origin+'/api/') else None)
                page.goto(origin)
                page.locator('#username').fill('schooladmin')
                page.locator('#password').fill(FIXTURE_PASSWORD)
                page.locator('#login-form button[type=submit]').click()
                page.locator('#content').wait_for()
                page.locator('[data-action=nav][data-id=sync]').first.click()
                page.get_by_role('heading', name='统一认证与接口适配中心', exact=True).first.wait_for()
                assert page.locator('#content').inner_text().count('待学校签认') == 3
                checks.append('实际登录与三个接口六项独立状态')
                page.screenshot(path=str(out/'01-center.png'), full_page=True)
                with page.expect_download() as intake_download:
                    page.locator('[data-action=integration-intake-download]').click()
                intake_path = Path(temporary)/'school-intake.xlsx'
                intake_download.value.save_as(str(intake_path))
                filled_path = Path(temporary)/'school-intake-filled.xlsx'
                filled_path.write_bytes(prepare_school_workbook(intake_path.read_bytes()))
                with page.expect_file_chooser() as chooser:
                    page.locator('[data-action=integration-intake-import]').click()
                chooser.value.set_files(str(filled_path))
                page.get_by_text('学校接口资料预检', exact=True).wait_for()
                assert '不会自动联网、发布或验收' in page.locator('#modal-root').inner_text()
                page.locator('#modal-root [data-action=integration-intake-confirm]').click()
                form = page.locator('#edit-form')
                form.locator('[name=reason]').fill('浏览器验证学校资料只写实施草稿')
                page.locator('button[form=edit-form][type=submit]').click()
                page.locator('#modal-root').wait_for(state='hidden')
                page.get_by_role('heading', name='统一认证与接口适配中心', exact=True).first.wait_for()
                checks.append('学校资料采集表下载、预检、确认导入只写草稿')
                page.locator('#content [data-action=nav][data-id=sso]').click()
                page.locator('[data-action=impl-step][data-id=credentials]').click()
                page.get_by_text('正式登录回调', exact=True).wait_for()
                assert origin+'/api/auth/sso/callback' in page.locator('#content').inner_text()
                checks.append('服务器只读正式回调与试登录回调')
                page.screenshot(path=str(out/'02-callbacks.png'), full_page=True)
                page.locator('[data-action=impl-step][data-id=protocol]').click()
                page.locator('#content [data-action=connection]').click()
                form = page.locator('#edit-form')
                form.locator('[name=endpoint]').fill('https://synthetic.invalid')
                form.locator('[name=owner]').fill('合成信息处 / 测试责任人')
                form.locator('[name=sso_protocol]').select_option('cas')
                form.get_by_text('实施人员使用：认证地址与协议参数', exact=True).click()
                form.locator('[name=login_path]').fill('/login')
                form.locator('[name=validate_path]').fill('/serviceValidate')
                for key, value in {'stable_id':'id', 'account':'account', 'name':'name', 'org_code':'org', 'active':'active'}.items():
                    form.locator('[name=identity_'+key+']').fill(value)
                form.locator('[name=reason]').fill('浏览器合成草稿保存验证')
                page.locator('button[form=edit-form][type=submit]').click()
                page.locator('#modal-root').wait_for(state='hidden')
                page.reload()
                page.locator('.implementation-status').wait_for()
                assert '配置校验通过' in page.locator('#content').inner_text()
                checks.append('原一页表单保存草稿、刷新真实回读且运行配置未发布')
                page.locator('[data-action=impl-step][data-id=credentials]').click()
                page.locator('[data-action=impl-credential-meta]').click()
                form = page.locator('#edit-form')
                form.locator('[name=credential_type]').select_option('token')
                form.locator('[name=managed_by]').select_option('server_env')
                form.locator('[name=owner]').fill('合成服务器管理员')
                form.locator('[name=reason]').fill('登记合成安全资产元数据')
                page.locator('button[form=edit-form][type=submit]').click()
                page.locator('#modal-root').wait_for(state='hidden')
                page.get_by_text('安全资产有效', exact=True).wait_for()
                checks.append('证书与凭据页面只登记安全元数据并显示轮换状态')
                page.locator('[data-action=impl-step][data-id=identity]').click()
                page.locator('[data-action=mapping-trial]').click()
                form = page.locator('#edit-form')
                form.get_by_text('实施人员使用：直接粘贴 JSON（数据文本）', exact=True).click()
                sample = [{'id':'synthetic-1', 'account':'teacher', 'name':'合成教师', 'org':'dept1', 'active':'ACTIVE'}]
                form.locator('[name=records]').fill(json.dumps(sample, ensure_ascii=False))
                form.locator('[name=reason]').fill('验证预览与实际身份解析相同')
                page.locator('button[form=edit-form][type=submit]').click()
                page.get_by_text('字段校验结果', exact=True).wait_for()
                assert '仅本人' in page.locator('#modal-root').inner_text()
                checks.append('实际HTTP身份预览显示本地账号组织角色范围')
                page.screenshot(path=str(out/'03-identity-preview.png'), full_page=True)
                page.locator('#modal-root [data-action=close]').first.click()
                page.locator('[data-action=impl-step][data-id=publish]').click()
                page.locator('[data-action=impl-publish]').click()
                form = page.locator('#edit-form')
                form.locator('[name=confirm_schedule_pause]').check()
                form.locator('[name=reason]').fill('验证缺少真实证明不能发布')
                page.locator('button[form=edit-form][type=submit]').click()
                page.get_by_text('缺少当前草稿的有效真实验证', exact=False).first.wait_for()
                checks.append('没有真实验证时发布被服务端拒绝')
                page.locator('#modal-root [data-action=close]').first.click()
                page.locator('[data-action=impl-step][data-id=diagnostics]').click()
                page.get_by_text('学校验收台账', exact=True).wait_for()
                page.locator('[data-action=impl-acceptance]').click()
                form = page.locator('#edit-form')
                form.locator('[name=reason]').fill('登记合成验收待确认台账')
                page.locator('button[form=edit-form][type=submit]').click()
                page.locator('#modal-root').wait_for(state='hidden')
                page.locator('#content').get_by_text('待学校签认', exact=True).first.wait_for()
                checks.append('学校验收台账可留痕且不会自动变成验收通过')
                with page.expect_download() as pending_download:
                    page.locator('[data-action=impl-handover]').click()
                pending_download.value.save_as(str(out/'synthetic-handover.zip'))
                checks.append('实际浏览器下载受权限保护的实施交接ZIP')
                for step in ('materials','protocol','credentials','identity','tests','publish','diagnostics'):
                    page.locator('[data-action=impl-step][data-id='+step+']').click()
                    page.locator('.implementation-status').wait_for()
                page.set_viewport_size({'width':1152,'height':800})
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 2')
                page.screenshot(path=str(out/'04-narrow-diagnostics.png'), full_page=True)
                checks.append('七步均可访问及1152px窄屏无页面级横向溢出')
                assert not errors, errors
                result = {'status':'PASS','browser':browser.version,'checks':checks,'page_errors':errors,
                          'requests':requests,'real_school_contacted':False,'database':'isolated SQLite',
                          'school_acceptance':False,'synthetic_accounts':True}
                (out/'browser.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
                context.close()
                browser.close()
                print(json.dumps({'status':'PASS','checks':checks},ensure_ascii=False))
        except Exception:
            (out/'failure.json').write_text(json.dumps({'checks':checks,'page_errors':errors,'requests':requests},ensure_ascii=False,indent=2),encoding='utf-8')
            raise
        finally:
            server.should_exit = True
            thread.join(timeout=10)


if __name__ == '__main__':
    main()
