"""Narrated field-by-field walkthroughs of real synthetic-lab forms; never submits."""
from pathlib import Path
import argparse,json,subprocess,time,re,wave,math
from playwright.sync_api import sync_playwright
from check_help_browser import ROOT,ORIGIN,login,nav,click_action
from record_help import VERSION,audio,stamp,save_manifest

def timeline(segments,title,offset,chapters,captions):
    elapsed=0
    for segment in segments:
        chapters.append({'title':title+' / '+segment['title'],'time':round(offset+elapsed,2)})
        chunks=re.findall(r'.{1,28}',segment['text']);total=sum(map(len,chunks));at=offset+elapsed
        for chunk in chunks:
            span=segment['duration']*len(chunk)/total;captions.extend([f'{stamp(at)} --> {stamp(at+span)}',chunk,'']);at+=span
        elapsed+=segment['duration']
    return elapsed

def paced_audio(segments,folder):
    # Hold real recorded frames while the narration explains them; keep cuts on exact video frames.
    with wave.open(str(folder/'0.wav'),'rb') as source:params=source.getparams()
    with wave.open(str(folder/'narration.wav'),'wb') as output:
        output.setparams(params)
        for i,segment in enumerate(segments):
            segment['duration']=math.ceil(segment['duration']*25)/25
            with wave.open(str(folder/f'{i}.wav'),'rb') as source:
                output.writeframes(source.readframes(source.getnframes()))
                silence=round(segment['duration']*params.framerate)-source.getnframes()
                output.writeframes(b'\0'*(silence*params.nchannels*params.sampwidth))
    (folder/'timings.json').write_text(json.dumps([s['duration'] for s in segments]),encoding='utf-8')

def run(args):
    lab=Path(args.lab).resolve()
    if lab.name!='integrated-help-20261022' or not (lab/'synthetic.sqlite').is_file():raise ValueError('Owned synthetic lab required')
    password=json.loads((lab/'private-login.json').read_text(encoding='utf-8'))['password']
    forms=json.loads(subprocess.check_output(['node','--input-type=module','-e',"import {HELP_FORMS} from './frontend/help-forms.js';console.log(JSON.stringify(HELP_FORMS))"],cwd=ROOT))
    output=ROOT/'frontend/assets/help'/VERSION
    with sync_playwright() as pw:
        browser=None
        for index,(topic,variants) in enumerate(forms.items()):
            if index%args.parts!=args.part:continue
            if args.topics and topic not in args.topics.split(','):continue
            existing=json.loads((ROOT/'frontend/help-media.js').read_text(encoding='utf-8').split('export const HELP_MEDIA=',1)[1].strip().removesuffix(';'))
            if existing.get(topic,{}).get('filling') and not args.redo:continue
            clips=[];captions=['WEBVTT',''];chapters=[];offset=0;seen=set()
            for variant_index,form in enumerate(variants):
                display_title=form['title']+'（'+{'teacher':'教师','dept':'教研室负责人','college':'学院负责人','school':'学校办理人员'}[form['role']]+'）'
                folder=lab/'form-recordings'/topic/str(variant_index);folder.mkdir(parents=True,exist_ok=True)
                segments=[{'title':form['title'],'text':form['title']+'。下面逐项说明怎么填写。所有画面使用虚构资料，本段不提交业务。政策和计分参数必须按学校正式确认的依据填写。','key':None}]
                for field in form['fields']:
                    # Individual candidate names are not useful teaching topics; explain the selection once.
                    if not field['key'] and field['label']!='搜索姓名、工号或账号':continue
                    signature=json.dumps(field,ensure_ascii=False,sort_keys=True)
                    if signature in seen:continue
                    seen.add(signature)
                    text=field['label']+'。'+field['explanation']
                    if field['example'] and len(field['example'])<70:text+='。示例提示：'+field['example']
                    segments.append({'title':field['label'],'text':text.replace('。。','。'),'key':field['key']})
                if len(segments)==1:continue
                if variant_index:segments[0]['text']=form['title']+'。本段只补充不同身份或表单的差异项，相同字段沿用前面的讲解。请按实际职责和学校确认的依据填写，本段不提交业务。'
                clip=folder/'final.mp4';source=folder/'speech.json'
                if clip.is_file() and clip.stat().st_size and source.is_file() and json.loads(source.read_text(encoding='utf-8'))==segments:
                    timing_file=folder/'timings.json'
                    timings=json.loads(timing_file.read_text()) if timing_file.is_file() and timing_file.stat().st_mtime>=source.stat().st_mtime else None
                    for i,segment in enumerate(segments):
                        with wave.open(str(folder/f'{i}.wav'),'rb') as wav:segment['duration']=timings[i] if timings else wav.getnframes()/wav.getframerate()+.6
                    expected=sum(s['duration'] for s in segments);actual=0
                    try:actual=float(json.loads(subprocess.check_output([args.ffprobe,'-v','error','-show_format','-of','json',str(clip)],stderr=subprocess.DEVNULL))['format']['duration'])
                    except (subprocess.CalledProcessError,KeyError,ValueError):pass
                    if abs(actual-expected)>=1.5:
                        for raw in sorted(folder.glob('*.webm'),key=lambda f:f.stat().st_mtime,reverse=True):
                            if raw.stat().st_mtime<source.stat().st_mtime:continue
                            try:raw_duration=float(json.loads(subprocess.check_output([args.ffprobe,'-v','error','-show_format','-of','json',str(raw)],stderr=subprocess.DEVNULL))['format']['duration'])
                            except (subprocess.CalledProcessError,KeyError,ValueError):continue
                            if raw_duration<expected:continue
                            subprocess.run([args.ffmpeg,'-hide_banner','-loglevel','error','-y','-ss',str(raw_duration-expected),'-threads','1','-i',str(raw),'-i',str(folder/'narration.wav'),'-t',str(expected),'-map','0:v:0','-map','1:a:0','-c:v','libx264','-preset','veryfast','-crf','26','-threads','1','-pix_fmt','yuv420p','-c:a','aac','-movflags','+faststart',str(clip)],check=True)
                            actual=expected;break
                    if abs(actual-expected)<1.5:
                        offset+=timeline(segments,display_title,offset,chapters,captions);clips.append(clip);print('复用已录制片段：'+form['title'],flush=True);continue
                for segment in segments:segment.pop('duration',None)
                audio(segments,folder)
                if args.paced:paced_audio(segments,folder)
                browser=pw.chromium.launch(args=['--renderer-process-limit=1'])
                ctx,p=login(browser,form['user'],password);state=ctx.storage_state();ctx.close();browser.close()
                browser=pw.chromium.launch(args=['--renderer-process-limit=1'])
                rec=browser.new_context(storage_state=state,viewport={'width':1360,'height':900},record_video_dir=str(folder),record_video_size={'width':1360,'height':900})
                p=rec.new_page();p.set_default_timeout(12000);nav(p,topic)
                for setup in form.get('setup',[]):
                    click_action(p,f'#content [data-action="{setup["action"]}"][data-id="{setup["id"]}"]');p.locator('#modal-root:not(.hidden) .modal-head h2').wait_for()
                target=p.locator(f'{form.get("scope","#content")} [data-action="{form["action"]}"][data-id="{form["action_id"]}"]').first
                if not target.is_visible():target.locator('xpath=ancestor::details[1]').locator('summary').first.click()
                target.click();p.locator('#edit-form').wait_for()
                start=time.monotonic();elapsed=0;video=p.video;scenes=[]
                for segment in segments:
                    began=time.monotonic();key=segment['key']
                    if key:
                        field=p.locator(','.join('#edit-form ['+attr+'='+json.dumps(key)+']' for attr in ['name','data-r','data-or'])).first
                        if field.count() and field.is_visible():
                            field.scroll_into_view_if_needed();field.focus()
                            help_box=field.locator('xpath=ancestor::*[contains(concat(" ",normalize-space(@class)," ")," form-field ") or contains(concat(" ",normalize-space(@class)," ")," rule-control ")][1]').locator('.field-how')
                            if help_box.count():
                                if help_box.first.get_attribute('open') is None:help_box.first.locator('summary').click()
                        else:
                            # Inactive conditional fields stay inactive; show their conditional instructions.
                            if not p.locator('.help-panel').count():p.locator('#modal-root [data-open-help]').click();p.locator('[data-help-tab=fields]').click()
                            explanation=p.locator('.help-panel-body > .help-field').filter(has_text=segment['title']).first
                            if explanation.count():explanation.scroll_into_view_if_needed()
                    remaining=segment['duration']-(time.monotonic()-began)
                    if args.paced:p.wait_for_timeout(650)
                    elif remaining>0:p.wait_for_timeout(remaining*1000)
                    scenes.append((began-start,time.monotonic()-start,segment['duration']))
                    elapsed+=segment['duration']
                    if p.locator('.help-panel').count():p.locator('[data-help-close]').click()
                end=time.monotonic();rec.close();raw=Path(video.path());browser.close();browser=None
                duration=float(json.loads(subprocess.check_output([args.ffprobe,'-v','error','-show_format','-of','json',str(raw)]))['format']['duration'])
                trim=max(0,duration-(end-start));clip=folder/'final.mp4'
                if args.paced:
                    parts=[]
                    for i,(begin,finish,spoken_duration) in enumerate(scenes):
                        part=folder/f'scene-{i}.mp4';parts.append(part)
                        subprocess.run([args.ffmpeg,'-hide_banner','-loglevel','error','-y','-ss',str(trim+begin),'-t',str(finish-begin),'-threads','1','-i',str(raw),'-an','-vf','tpad=stop_mode=clone:stop_duration='+str(spoken_duration),'-t',str(spoken_duration),'-r','25','-c:v','libx264','-preset','veryfast','-crf','26','-threads','1','-pix_fmt','yuv420p',str(part)],check=True)
                    scene_list=folder/'scenes.txt';scene_list.write_text(''.join("file '"+part.as_posix()+"'\n" for part in parts),encoding='utf-8')
                    subprocess.run([args.ffmpeg,'-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',str(scene_list),'-i',str(folder/'narration.wav'),'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-t',str(elapsed),'-movflags','+faststart',str(clip)],check=True)
                else:
                    subprocess.run([args.ffmpeg,'-hide_banner','-loglevel','error','-y','-ss',str(trim),'-threads','1','-i',str(raw),'-i',str(folder/'narration.wav'),'-t',str(elapsed),'-map','0:v:0','-map','1:a:0','-c:v','libx264','-preset','veryfast','-crf','26','-threads','1','-pix_fmt','yuv420p','-c:a','aac','-movflags','+faststart',str(clip)],check=True)
                clips.append(clip);offset+=timeline(segments,display_title,offset,chapters,captions)
                print('逐项填写录制完成：'+form['title'],flush=True)
            listing=lab/'form-recordings'/topic/'concat.txt';listing.write_text(''.join("file '"+c.as_posix()+"'\n" for c in clips),encoding='utf-8')
            subprocess.run([args.ffmpeg,'-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',str(listing),'-c','copy','-movflags','+faststart',str(output/f'{topic}-filling.mp4')],check=True)
            (output/f'{topic}-filling.vtt').write_text('\n'.join(captions),encoding='utf-8')
            item={'src':f'/assets/assets/help/{VERSION}/{topic}-filling.mp4','captions':f'/assets/assets/help/{VERSION}/{topic}-filling.vtt','poster':f'/assets/assets/help/{VERSION}/{topic}.jpg','version':VERSION,'duration':round(offset,2),'chapters':chapters,'covered_forms':[f['title'] for f in variants],'description':'真实表单逐项讲解，说明字段含义、示例和条件；使用虚构资料，不提交业务。可通过章节直接跳到某一栏。'}
            save_manifest(lab,ROOT/'frontend/help-media.js',topic,{'filling':item})
            print('填写视频已生成：'+topic,flush=True)
        if browser:browser.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--lab',required=True);parser.add_argument('--ffmpeg',required=True);parser.add_argument('--ffprobe',required=True);parser.add_argument('--parts',type=int,default=1);parser.add_argument('--part',type=int,default=0);parser.add_argument('--redo',action='store_true');parser.add_argument('--topics');parser.add_argument('--paced',action='store_true');run(parser.parse_args())
