"""Record real browser page walkthroughs with local Mandarin narration.

Requires the owned synthetic lab. These are page tutorials, not evidence that
unconnected school integrations or every approval workflow have been accepted.
Each narrated scene is a screenshot of the real browser taken after its action has
settled, shown for exactly the length of its narration, so picture and speech stay in step.
(Browser screen recordings start a variable moment late on this machine; screenshots do not drift.)
"""
from pathlib import Path
import argparse,json,subprocess,time,wave,re,msvcrt
from playwright.sync_api import sync_playwright
from check_help_browser import ROOT,ORIGIN,login,nav,load_topics,FORM_ACTIONS

VERSION=re.search(r"HELP_VERSION='(\d{8})'",(ROOT/'frontend/help-content.js').read_text(encoding='utf-8'))[1]
SCENE_SETTLE_MS=900
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

def tidy(text):
    """Normal Chinese punctuation for speech and captions: no doubled full stops or stray separators."""
    text=re.sub(r'\s+',' ',str(text)).strip()
    text=re.sub(r'[；;，,、]+(?=[。！？])','',text)
    text=re.sub(r'。[；;]','。',text)
    return re.sub(r'([。！？])\1+',r'\1',text)

def unique_sentences(text,seen=None):
    """Drop sentences already spoken in this video, so the narration never repeats itself."""
    seen=set() if seen is None else seen;out=[]
    for sentence in re.findall(r'[^。！？]+[。！？]?',tidy(text)):
        key=re.sub(r'[\s，。；、：！？“”]','',sentence)
        if key and key not in seen:seen.add(key);out.append(sentence.strip())
    return ''.join(out)

BREAK_AFTER=set('的了和与或并及后时再在把将对按向从由给是要可就也都还')
TOKEN=re.compile(r'[A-Za-z0-9_\-./:％%]')
def _cut(text,limit):
    def safe(i):
        if i<=0 or i>=len(text):return False
        if TOKEN.match(text[i-1]) and TOKEN.match(text[i]):return False  # never split a code such as SOC-2026-001
        if text[i-1] in '“（《「' or text[i] in '”）》」':return False
        return len(text.rstrip('，、：；。！？'))-i>=4  # no orphan word such as “登录” on its own line
    def quoted(i):return text[:i].count('“')>text[:i].count('”')
    for i in range(min(limit,len(text)-1),limit//2,-1):
        if safe(i) and text[i-1] in BREAK_AFTER and not quoted(i):return i
    for i in range(min(limit,len(text)-1),3,-1):
        if safe(i) and text[i-1] in BREAK_AFTER and not quoted(i):return i
    for i in range(min(limit,len(text)-1),3,-1):
        if safe(i) and not quoted(i):return i
    for i in range(min(limit,len(text)-1),0,-1):
        if safe(i):return i
    return limit
def caption_chunks(text,limit=20):
    """Caption lines of at most ~20 characters, split at sentence and clause punctuation first."""
    lines=[]
    for sentence in re.findall(r'[^。！？；]+[。！？；]?',tidy(text)):
        current=''
        for clause in re.findall(r'[^，、：]+[，、：]?',sentence):
            clause=clause.strip()
            if not clause:continue
            if len(current)+len(clause)<=limit:current+=clause;continue
            if current:lines.append(current);current=''
            while len(clause.rstrip('，、：；。！？'))>limit+2:
                cut=_cut(clause,limit);lines.append(clause[:cut]);clause=clause[cut:]
            current=clause
        if current:lines.append(current)
    return [l for l in (line.strip().rstrip('，、；：;,') for line in lines) if l and l not in '。！？']

def caption_cues(text,start,duration,captions):
    chunks=caption_chunks(text);total=sum(map(len,chunks)) or 1;at=start
    for chunk in chunks:
        span=duration*len(chunk)/total;captions.extend([f'{stamp(at)} --> {stamp(at+span)}',chunk,'']);at+=span

def audio(segments,directory):
    directory.mkdir(parents=True,exist_ok=True)
    for segment in segments:segment['text']=tidy(segment['text'])
    source=directory/'speech.json';spoken=[{k:v for k,v in s.items() if k!='duration'} for s in segments]
    # Unchanged narration keeps its existing speech files; only new or edited text is synthesized again.
    cached=source.is_file() and json.loads(source.read_text(encoding='utf-8'))==spoken and all((directory/f'{i}.wav').is_file() for i in range(len(segments)))
    source.write_text(json.dumps(spoken,ensure_ascii=False),encoding='utf-8')
    if not cached:subprocess.run(['powershell','-NoProfile','-File',str(ROOT/'scripts/render_help_speech.ps1'),'-InputFile',str(source),'-OutputDirectory',str(directory)],check=True,stdout=subprocess.DEVNULL)
    params=None;frames=[]
    for i,segment in enumerate(segments):
        with wave.open(str(directory/f'{i}.wav'),'rb') as f:
            params=params or f.getparams();frame=f.readframes(f.getnframes())
            # Whole video frames (25 fps) keep cuts, captions and chapters on the same timeline.
            total=-(-round((f.getnframes()/f.getframerate()+.6)*25)//1)/25
            silence=round(total*f.getframerate())-f.getnframes()
            frames.append(frame+b'\0'*(silence*f.getnchannels()*f.getsampwidth()));segment['duration']=total
    with wave.open(str(directory/'narration.wav'),'wb') as f:
        f.setparams(params)
        for frame in frames:f.writeframes(frame)

def probe_duration(ffprobe,path):
    return float(json.loads(subprocess.check_output([ffprobe,'-v','error','-show_format','-of','json',str(path)]))['format']['duration'])

def assemble(ffmpeg,stills,narration,folder,target,total):
    """Show each scene's screenshot for exactly as long as its narration, then add the narration track."""
    parts=[]
    for i,(image,spoken) in enumerate(stills):
        part=folder/f'scene-{i}.mp4';parts.append(part)
        subprocess.run([ffmpeg,'-hide_banner','-loglevel','error','-y','-loop','1','-framerate','25','-t',str(spoken),'-i',str(image),'-vf','scale=1360:900,format=yuv420p','-r','25','-c:v','libx264','-preset','veryfast','-tune','stillimage','-crf','27','-threads','1',str(part)],check=True)
    listing=folder/'scenes.txt';listing.write_text(''.join("file '"+p.as_posix()+"'\n" for p in parts),encoding='utf-8')
    subprocess.run([ffmpeg,'-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',str(listing),'-i',str(narration),'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','80k','-t',str(total),'-movflags','+faststart',str(target)],check=True)
    for part in parts:part.unlink(missing_ok=True)

def still(p,folder,index):
    image=folder/f'scene-{index}.png';p.screenshot(path=str(image));return image

def demo_branding(lab):
    """Fictional school mark and plain background used in place of the real school's logo and campus photo."""
    from PIL import Image,ImageDraw,ImageFont
    folder=lab/'demo-branding';folder.mkdir(exist_ok=True)
    logo,background=folder/'school-brand.png',folder/'login-campus-blue.jpg'
    if not logo.is_file():
        image=Image.new('RGBA',(422,118),(0,0,0,0));draw=ImageDraw.Draw(image)
        big=ImageFont.truetype('C:/Windows/Fonts/msyhbd.ttc',30)
        draw.ellipse((6,24,76,94),outline=(255,255,255,235),width=4);draw.text((41,59),'演',font=big,fill=(255,255,255,240),anchor='mm')
        draw.text((92,59),'演示学校（虚构资料）',font=big,fill=(255,255,255,245),anchor='lm')
        image.save(logo)
    if not background.is_file():
        image=Image.new('RGB',(1600,1000));draw=ImageDraw.Draw(image)
        for y in range(1000):draw.line([(0,y),(1600,y)],fill=(11,52+y//40,86+y//25))
        image.save(background,quality=88)
    return {'**/assets/assets/school-brand.png':logo,'**/assets/assets/school-brand-header.png':logo,'**/assets/assets/login-campus-blue.jpg':background,'**/assets/assets/login-campus-blue.png':background}

def use_demo_branding(context,lab):
    def serve(path):return lambda route:route.fulfill(path=str(path))  # Playwright passes (route, request) to two-argument handlers
    for pattern,path in demo_branding(lab).items():context.route(pattern,serve(path))

def open_help(p,selector):
    if not p.locator('.help-panel').count():p.locator(selector).first.click()
    p.locator('.help-panel').wait_for()

def close_help(p):
    if p.locator('.help-panel').count():p.locator('[data-help-close]').click()

def page_segments(topic,has_form):
    seen=set();say=lambda text:unique_sentences(text,seen)
    steps=''.join(s if s.endswith('。') else s+'。' for s in topic['steps'])
    return [{'title':'这页做什么','text':say(f'这一段介绍{topic["title"]}。画面里的人员和数据都是虚构的演示资料。'+topic['purpose']),'scene':'page'},
            {'title':'操作步骤','text':say('具体步骤是：'+steps),'scene':'steps'},
            {'title':'填写说明' if has_form else '数据怎么看','text':say('点开填写入口后，再点“填写说明”，可以逐项看每一栏怎么填、有什么限制。演示只打开表单，没有提交。' if has_form else '页面标题旁的“使用帮助”可以随时打开。查询前先确认当前身份、统计周期和组织范围。'),'scene':'form'},
            {'title':'怎样算办好','text':say('怎样算办好了：'+topic['done']+'遇到问题可以看帮助里的常见问题。关闭帮助后，可以接着刚才的操作。'),'scene':'done'}]

def quickstart_segments(topic):
    seen=set();titles=['登录','切换身份','申报课程','看退回意见','重新提交','找待办']
    first={'title':'开始','text':unique_sentences(topic['title']+'。'+topic['purpose']+'画面里的人员和数据都是虚构的演示资料。',seen),'scene':'login'}
    rest=[{'title':title,'text':unique_sentences(step.split('：',1)[-1],seen),'scene':scene} for title,step,scene in zip(titles,topic['steps'],['login','identity','apply','returned','resubmit','todos'])]
    rest[0]['scene']='login-local'
    return [first,*rest,{'title':'小结','text':unique_sentences('记住两件事：办自己的申请用教师身份，交上去以后到“我的申请”看进度。'+topic['done'],seen),'scene':'todos-mine'}]

def quickstart_action(p,scene,state):
    try:
        if scene=='login-local':p.locator('#login-local-tab').click()
        elif scene=='identity':
            # Same-URL hash changes do not reload; reload so the app starts with the signed-in session.
            p.context.add_cookies(state['cookies']);p.goto(ORIGIN+'/#home');p.reload();p.locator('#content h1').wait_for();p.locator('.busy-panel').wait_for(state='detached')
            menu=p.locator('#account-menu summary')
            if menu.count():menu.first.click()
        elif scene=='apply':
            if p.locator('#account-menu[open] summary').count():p.locator('#account-menu summary').first.click()
            nav(p,'apply_course')  # 停在“我的申报”页，画面上能看到“新申报一门培训课程”按钮和申请列表
        elif scene=='returned':
            # “我的申请”在待办中心；筛选“待补正”就是被退回、等你补正的申请。
            nav(p,'todos');p.locator('#content [data-action="todos-tab"][data-id="mine"]').first.click();p.wait_for_timeout(400)
            p.locator('#content [data-action="app-mine-filter"][data-id="returned"]').first.click()
        elif scene=='resubmit':
            p.locator('#content [data-action="app-mine-filter"][data-id=""]').first.click();p.wait_for_timeout(400)
            detail=p.locator('#content [data-action=app-detail]')
            if detail.count():detail.first.click()
        elif scene=='todos':
            if p.locator('#modal-root:not(.hidden) [data-action=close]').count():p.locator('#modal-root [data-action=close]:visible').last.click()
            p.locator('#content [data-action="todos-tab"][data-id="handle"]').first.click()
        elif scene=='todos-mine':p.locator('#content [data-action="todos-tab"][data-id="mine"]').first.click()
    except Exception as error:
        print('  画面动作未完成（不影响配音）：',scene,type(error).__name__,flush=True)

def page_action(p,scene,ident,page_help,selector):
    if scene=='steps':open_help(p,page_help)
    elif scene=='form':
        close_help(p)
        if selector:
            button=p.locator(selector).first
            if not button.is_visible():button.locator('xpath=ancestor::details[1]').locator('summary').first.click()
            button.click();p.wait_for_timeout(500)
            if p.locator('#modal-root #edit-form').count():open_help(p,'#modal-root [data-open-help]')
            else:open_help(p,'#content [data-open-help]')
        else:
            if ident=='account':p.locator('#login-local-tab').click()
            open_help(p,page_help)
        p.locator('[data-help-tab=fields]').click()
    elif scene=='done':
        if p.locator('.help-panel').count():p.locator('[data-help-tab=steps]').click()

def run(args):
    lab=Path(args.lab).resolve()
    if lab.name!='integrated-help-20261022' or not (lab/'synthetic.sqlite').is_file():raise ValueError('Owned synthetic lab required')
    password=json.loads((lab/'private-login.json').read_text(encoding='utf-8'))['password']
    available=json.loads((lab/'browser/available.json').read_text(encoding='utf-8'))
    available.setdefault('quickstart',{'user':'teacher','role':'teacher'});available.setdefault('account',{'user':'teacher','role':'teacher'})
    output=ROOT/'frontend/assets/help'/VERSION;output.mkdir(parents=True,exist_ok=True)
    manifest_file=ROOT/'frontend/help-media.js'
    manifest=json.loads(manifest_file.read_text(encoding='utf-8').split('export const HELP_MEDIA=',1)[1].strip().removesuffix(';'))
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True,args=['--renderer-process-limit=1'])
        for index,topic in enumerate(load_topics()):
            if index%args.parts!=args.part:continue
            ident=topic['id']
            if args.topic and ident not in args.topic.split(','):continue
            if ident=='apply_course' and not args.topic:continue  # 课程申报使用完整流程录屏（check_help_course_flow.py）
            if ident not in available or (not args.redo and ident in manifest and manifest[ident].get('version')==VERSION and manifest[ident].get('paced')):continue
            user=available[ident]['user'];workspace=lab/'recordings'/ident;workspace.mkdir(parents=True,exist_ok=True)
            for old in [*workspace.glob('*.webm'),*workspace.glob('scene-*.png')]:old.unlink()
            state=None
            if ident!='account':
                ctx,p=login(browser,user,password);state=ctx.storage_state();ctx.close()
            rec=browser.new_context(storage_state=None if ident in ('account','quickstart') else state,viewport={'width':1360,'height':900})
            use_demo_branding(rec,lab)
            p=rec.new_page();p.set_default_timeout(12000)
            if ident in ('account','quickstart'):p.goto(ORIGIN);p.locator('#login-heading').wait_for();p.wait_for_timeout(300)
            else:nav(p,ident)
            page_help='#app [data-open-help]' if ident=='account' else '#content [data-open-help]'
            selector=None
            for action,value in FORM_ACTIONS.get(ident,[]):
                candidate=f'#content [data-action="{action}"][data-id="{value}"]'
                if p.locator(candidate).count():selector=candidate;break
            segments=quickstart_segments(topic) if ident=='quickstart' else page_segments(topic,bool(selector))
            audio(segments,workspace)
            if ident!='quickstart':p.screenshot(path=str(output/f'{ident}.jpg'),type='jpeg',quality=78)
            stills=[];marks=[];captions=['WEBVTT',''];elapsed=0.0
            for index,segment in enumerate(segments):
                if ident=='quickstart':quickstart_action(p,segment['scene'],state)
                else:page_action(p,segment['scene'],ident,page_help,selector)
                p.wait_for_timeout(SCENE_SETTLE_MS)
                if ident=='quickstart' and segment['scene']=='identity':p.screenshot(path=str(output/'quickstart.jpg'),type='jpeg',quality=78)
                stills.append((still(p,workspace,index),segment['duration']))
                marks.append({'title':segment['title'],'time':round(elapsed,2)})
                caption_cues(segment['text'],elapsed,segment['duration'],captions)
                elapsed+=segment['duration']
            rec.close()
            assemble(args.ffmpeg,stills,workspace/'narration.wav',workspace,output/f'{ident}.mp4',elapsed)
            (output/f'{ident}.vtt').write_text('\n'.join(captions),encoding='utf-8')
            manifest[ident]={'src':f'/assets/assets/help/{VERSION}/{ident}.mp4','poster':f'/assets/assets/help/{VERSION}/{ident}.jpg','captions':f'/assets/assets/help/{VERSION}/{ident}.vtt','chapters':marks,'duration':round(elapsed,2),'version':VERSION,'paced':True,'description':'新手上手演示：登录、切换身份、申报课程、看退回意见、重新提交、找待办（虚构资料，未提交业务）。' if ident=='quickstart' else '真实页面与填写说明演示（虚构资料）；本段未提交业务，不作为完整审批验收。'}
            save_manifest(lab,manifest_file,ident,manifest[ident])
            print('视频已生成：'+topic['title']+f'，{elapsed:.0f}秒',flush=True)
        browser.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--lab',required=True);parser.add_argument('--ffmpeg',required=True);parser.add_argument('--ffprobe',required=True);parser.add_argument('--redo',action='store_true');parser.add_argument('--topic');parser.add_argument('--parts',type=int,default=1);parser.add_argument('--part',type=int,default=0);run(parser.parse_args())
