"""Record real browser page/form walkthroughs and local Mandarin narration.

Requires the owned synthetic lab. These are page/filling tutorials, not evidence that
unconnected school integrations or every approval workflow have been accepted.
"""
from pathlib import Path
import argparse,json,subprocess,time,wave,re,msvcrt
from playwright.sync_api import sync_playwright
from check_help_browser import ROOT,ORIGIN,login,nav,load_topics,FORM_ACTIONS

VERSION=re.search(r"HELP_VERSION='(\d{8})'",(ROOT/'frontend/help-content.js').read_text(encoding='utf-8'))[1]
def save_manifest(lab,path,ident,item):
    # Recording batches share only this small index; serialize and atomically replace it.
    with (lab/'media-index.lock').open('a+b') as lock:
        lock.write(b'0');lock.flush();lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_LOCK,1)
        try:
            data=json.loads(path.read_text(encoding='utf-8').split('export const HELP_MEDIA=',1)[1].strip().removesuffix(';'))
            data[ident]={**data.get(ident,{}),**item}
            temporary=path.with_suffix('.tmp')
            temporary.write_text('// 本地实际浏览器录屏及中文配音；不含账号凭据。\nexport const HELP_MEDIA='+json.dumps(data,ensure_ascii=False,indent=2)+';\n',encoding='utf-8')
            temporary.replace(path)
        finally:
            lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)
def stamp(seconds):
    ms=round(seconds*1000);h,ms=divmod(ms,3600000);m,ms=divmod(ms,60000);s,ms=divmod(ms,1000)
    return f'{h:02}:{m:02}:{s:02}.{ms:03}'

def audio(segments,directory):
    directory.mkdir(parents=True,exist_ok=True)
    source=directory/'speech.json';source.write_text(json.dumps(segments,ensure_ascii=False),encoding='utf-8')
    subprocess.run(['powershell','-NoProfile','-File',str(ROOT/'scripts/render_help_speech.ps1'),'-InputFile',str(source),'-OutputDirectory',str(directory)],check=True,stdout=subprocess.DEVNULL)
    params=None;frames=[]
    for i,segment in enumerate(segments):
        with wave.open(str(directory/f'{i}.wav'),'rb') as f:
            params=params or f.getparams();frame=f.readframes(f.getnframes());silence=b'\0'*(round(f.getframerate()*.6)*f.getnchannels()*f.getsampwidth())
            frames.append(frame+silence);segment['duration']=f.getnframes()/f.getframerate()+.6
    with wave.open(str(directory/'narration.wav'),'wb') as f:
        f.setparams(params)
        for frame in frames:f.writeframes(frame)

def run(args):
    lab=Path(args.lab).resolve()
    if lab.name!='integrated-help-20261022' or not (lab/'synthetic.sqlite').is_file():raise ValueError('Owned synthetic lab required')
    password=json.loads((lab/'private-login.json').read_text(encoding='utf-8'))['password']
    available=json.loads((lab/'browser/available.json').read_text(encoding='utf-8'))
    output=ROOT/'frontend/assets/help'/VERSION;output.mkdir(parents=True,exist_ok=True)
    manifest_file=ROOT/'frontend/help-media.js'
    manifest=json.loads(manifest_file.read_text(encoding='utf-8').split('export const HELP_MEDIA=',1)[1].strip().removesuffix(';'))
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        for index,topic in enumerate(load_topics()):
            if index%args.parts!=args.part:continue
            ident=topic['id']
            if args.topic and ident!=args.topic:continue
            if ident not in available or (not args.redo and ident in manifest):continue
            user=available[ident]['user'];workspace=lab/'recordings'/ident;workspace.mkdir(parents=True,exist_ok=True)
            if ident=='account':state=None
            else:
                ctx,p=login(browser,user,password);state=ctx.storage_state();ctx.close()
            rec=browser.new_context(storage_state=state,viewport={'width':1360,'height':900},record_video_dir=str(workspace),record_video_size={'width':1360,'height':900})
            p=rec.new_page();p.set_default_timeout(12000)
            if ident=='account':p.goto(ORIGIN);p.locator('#login-heading').wait_for()
            else:nav(p,ident)
            page_help='#app [data-open-help]' if ident=='account' else '#content [data-open-help]'
            selector=None
            for action,value in FORM_ACTIONS.get(ident,[]):
                candidate=f'#content [data-action="{action}"][data-id="{value}"]'
                if p.locator(candidate).count():selector=candidate;break
            # Only clearly distinguishable page/form actions are recorded; no hidden mutations.
            segments=[{'title':'入口与用途','text':f'本段介绍{topic["title"]}。画面是独立演示环境，人员和业务资料都是虚构的。'+topic['purpose'],'scene':'page'},
                      {'title':'操作顺序','text':'操作顺序如下。'+''.join(topic['steps']),'scene':'steps'},
                      {'title':'填写或查看说明','text':('点击业务填写入口，按分区核对必填项。这里打开填写说明，查看每项含义、示例和限制。本段只演示页面及填写方法，没有提交业务。' if selector else '打开本页使用帮助，可以查看数据含义和相关说明。查询时先核对当前身份、周期和组织范围。'),'scene':'form'},
                      {'title':'完成标志与常见问题','text':topic['done']+'。遇到问题可以查看帮助中的常见问题。关闭帮助后可继续原来的操作。','scene':'done'}]
            audio(segments,workspace)
            p.screenshot(path=str(output/f'{ident}.jpg'),type='jpeg',quality=78)
            # Video existed while narration was prepared; trim to this exact start point.
            start=time.monotonic();recording_start=p.video
            marks=[];subtitle=['WEBVTT',''];elapsed=0.0
            for i,segment in enumerate(segments):
                before=time.monotonic()
                if segment['scene']=='steps':
                    p.locator(page_help).click()
                elif segment['scene']=='form':
                    if p.locator('.help-panel').count():p.locator('[data-help-close]').click()
                    if selector:
                        button=p.locator(selector).first
                        if not button.is_visible():button.locator('xpath=ancestor::details[1]').locator('summary').first.click()
                        button.click();p.wait_for_timeout(500)
                        if p.locator('#modal-root #edit-form').count():
                            # Show examples using the existing hints, without inserting invented policy values.
                            p.locator('#modal-root [data-open-help]').click()
                        else:p.locator('#content [data-open-help]').click()
                    else:
                        if ident=='account':p.locator('#login-local-tab').click()
                        p.locator(page_help).click()
                    p.locator('[data-help-tab=fields]').click()
                elif segment['scene']=='done':
                    if p.locator('.help-panel').count():p.locator('[data-help-tab=steps]').click()
                marks.append({'title':segment['title'],'time':round(elapsed,2)})
                # Caption lines are short chunks, with timing proportional to their spoken text.
                chunks=re.findall(r'.{1,30}(?:[。；，]|$)|.{1,30}',segment['text'])
                total=sum(map(len,chunks)) or 1;offset=elapsed
                for chunk in chunks:
                    length=segment['duration']*len(chunk)/total
                    subtitle.extend([f'{stamp(offset)} --> {stamp(offset+length)}',chunk,'']);offset+=length
                remaining=segment['duration']-(time.monotonic()-before)
                if remaining>0:p.wait_for_timeout(remaining*1000)
                elapsed+=segment['duration']
            if p.locator('.help-panel').count():p.locator('[data-help-close]').click()
            end=time.monotonic();rec.close();raw=Path(recording_start.path())
            # Probe the captured stream, then take its tail matching the narrated walkthrough.
            probe=json.loads(subprocess.check_output([args.ffprobe,'-v','error','-show_format','-of','json',str(raw)]))
            trim=max(0,float(probe['format']['duration'])-(end-start))
            subprocess.run([args.ffmpeg,'-hide_banner','-loglevel','error','-y','-ss',str(trim),'-threads','1','-i',str(raw),'-i',str(workspace/'narration.wav'),'-t',str(elapsed),'-map','0:v:0','-map','1:a:0','-c:v','libx264','-preset','veryfast','-crf','28','-threads','1','-pix_fmt','yuv420p','-c:a','aac','-b:a','80k','-movflags','+faststart',str(output/f'{ident}.mp4')],check=True)
            (output/f'{ident}.vtt').write_text('\n'.join(subtitle),encoding='utf-8')
            manifest[ident]={'src':f'/assets/assets/help/{VERSION}/{ident}.mp4','poster':f'/assets/assets/help/{VERSION}/{ident}.jpg','captions':f'/assets/assets/help/{VERSION}/{ident}.vtt','chapters':marks,'duration':round(elapsed,2),'version':VERSION,'description':'真实页面与填写说明演示（虚构资料）；本段未提交业务，不作为完整审批验收。'}
            save_manifest(lab,manifest_file,ident,manifest[ident])
            print('视频已生成：'+topic['title']+f'，{elapsed:.0f}秒',flush=True)
        browser.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--lab',required=True);parser.add_argument('--ffmpeg',required=True);parser.add_argument('--ffprobe',required=True);parser.add_argument('--redo',action='store_true');parser.add_argument('--topic');parser.add_argument('--parts',type=int,default=1);parser.add_argument('--part',type=int,default=0);run(parser.parse_args())
