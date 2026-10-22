"""Real-browser media/accessibility/search checks; only video failure is deliberately injected."""
from pathlib import Path
import argparse,json
from playwright.sync_api import sync_playwright
from check_help_browser import login,nav,ORIGIN

def until(p,expression,arg=None):
    for _ in range(100):
        if p.evaluate(expression,arg):return
        p.wait_for_timeout(100)
    raise AssertionError('Browser condition not reached: '+expression)

def run(args):
    lab=Path(args.lab).resolve()
    if lab.name!='integrated-help-20261022' or not (lab/'synthetic.sqlite').is_file():raise ValueError('Owned synthetic lab required')
    password=json.loads((lab/'private-login.json').read_text(encoding='utf-8'))['password']
    checks=[];media_requests=[];errors=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch()
        ctx,p=login(browser,'teacher',password)
        p.on('pageerror',lambda error:errors.append(str(error)))
        p.on('response',lambda response:media_requests.append({'status':response.status,'range':response.request.headers.get('range','')}) if '.mp4' in response.url else None)
        nav(p,'apply_course');assert not media_requests
        p.locator('#content [data-open-help]').click();assert not media_requests
        p.locator('[data-help-tab=video]').click();video=p.locator('.help-panel video');video.wait_for()
        assert video.get_attribute('preload')=='none';assert not media_requests
        checks.append('页面和图文帮助不预载完整视频')
        video.evaluate('async v=>{window.helpPlaybackProbe=v;v.muted=true;await v.play()}')
        until(p,'()=>window.helpPlaybackProbe.currentTime>0.2')
        until(p,'()=>window.helpPlaybackProbe.textTracks[0]?.cues?.length>0')
        checks.append('视频和中文配音音轨可解码、中文字幕已加载')
        p.locator('[data-help-speed]').select_option('1.5');assert video.evaluate('(v)=>v.playbackRate')==1.5
        chapter=p.locator('[data-help-seek]').nth(1);seek=float(chapter.get_attribute('data-help-seek'));chapter.click()
        until(p,'(t)=>window.helpPlaybackProbe.currentTime>=t',seek)
        checks.append('倍速和章节跳转正常')
        p.locator('[data-help-fullscreen]').click()
        until(p,'()=>!!document.fullscreenElement');checks.append('原生播放器全屏正常')
        p.evaluate('document.exitFullscreen()')
        p.screenshot(path=str(lab/'browser/playback.png'))
        p.locator('[data-help-close]').click()
        assert p.evaluate('window.helpPlaybackProbe.paused&&!window.helpPlaybackProbe.getAttribute("src")')
        checks.append('关闭帮助立即停止播放并卸载媒体')
        assert any(r['status']==206 and r['range'] for r in media_requests),'Expected range response for local seeking'
        checks.append('本地服务支持分段视频读取')
        # Deliberately fail only the video file, never a business API.
        p.route('**/course-flow.mp4',lambda route:route.abort())
        p.locator('#content [data-open-help]').click();p.locator('[data-help-tab=video]').click()
        p.locator('video').evaluate('v=>{v.muted=true;v.play().catch(()=>{})}')
        p.locator('.help-media-error').wait_for(state='visible')
        p.locator('[data-help-tab=steps]').click();assert p.locator('.help-panel-body').inner_text().find('操作步骤')>=0
        p.locator('[data-help-close]').click();p.unroute('**/course-flow.mp4');checks.append('视频失败时图文仍可使用')
        p.locator('#content [data-open-help]').click();p.locator('[data-help-tab=video]').click();p.locator('[data-help-video-kind=filling]').click()
        assert '-filling.mp4' in p.locator('.help-panel video').get_attribute('src')
        p.locator('.help-chapter-filter input').fill('课程名称')
        assert p.locator('[data-help-seek]:visible').count()>0
        p.locator('.help-panel video').evaluate('v=>{v.muted=true}')
        target=p.locator('[data-help-seek]:visible').first;at=float(target.get_attribute('data-help-seek'));target.click()
        until(p,'t=>document.querySelector(".help-panel video").currentTime>=t',at)
        p.locator('[data-help-close]').click();checks.append('逐项填写视频切换与字段章节搜索正常')
        nav(p,'help')
        with p.expect_download() as pending:p.locator('a[download]').click()
        downloaded=lab/'browser/downloaded-manual.pdf';pending.value.save_as(str(downloaded))
        assert downloaded.read_bytes().startswith(b'%PDF-')
        checks.append('可打印手册可从系统内正常下载')
        p.locator('#help-audience').select_option('school')
        assert p.locator('[data-help-library] [data-action=nav][data-id=permissions]').count()==0
        p.locator('#help-query').fill('共建单位');assert p.locator('.help-topic-card').count()>0
        checks.append('按字段搜索；选择其他教程身份不会增加办理权限')
        p.locator('[data-action=search]').first.click();p.locator('#menu-search').fill('我的课程')
        p.locator('#help-search-matches [data-action=open-help-topic][data-id=credits]').click();assert '授课学分' in p.locator('#context-help-title').inner_text()
        p.locator('[data-help-close]').click();p.locator('#modal-root [data-action=close]:visible').last.click()
        checks.append('全局搜索保留旧菜单名称并可直接打开帮助')
        nav(p,'apply_course');p.locator('[data-action=teacher-apply][data-id="courses|app-course-new"]').click()
        p.locator('#edit-form [name=name]').fill('保留的虚构课程名称')
        p.locator('#modal-root [data-open-help]').click()
        p.locator('#edit-form [name=name]').focus();p.keyboard.press('Escape')
        assert p.locator('#edit-form').is_visible() and p.locator('#edit-form [name=name]').input_value()=='保留的虚构课程名称'
        checks.append('宽屏在原表单按退出键只关闭帮助')
        p.locator('#modal-root [data-open-help]').click();p.set_viewport_size({'width':390,'height':844});until(p,'()=>document.querySelector(".help-panel").getAttribute("aria-modal")==="true"')
        assert p.locator('.help-panel').get_attribute('aria-modal')=='true';assert p.locator('#modal-root').evaluate('e=>e.inert')
        p.keyboard.press('Escape');assert not p.locator('#modal-root').evaluate('e=>e.inert')
        checks.append('窗口缩窄时切换覆盖模式，关闭后原表单可继续操作')
        ctx.close();browser.close()
    report={'checks':checks,'errors':errors,'range_response_seen':True,'environment':'独立虚构演示库','production_verified':False}
    (lab/'browser/playback-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    assert not errors
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--lab',required=True);run(parser.parse_args())
