"""Narrated field-by-field walkthroughs of real synthetic-lab forms; never submits."""
from pathlib import Path
import argparse,json,subprocess,time,wave
from playwright.sync_api import sync_playwright
from check_help_browser import ROOT,login,nav,click_action
from record_help import VERSION,audio,save_manifest,caption_cues,unique_sentences,assemble,probe_duration,use_demo_branding,SCENE_SETTLE_MS

ROLE_TITLES={'teacher':'教师','dept':'教研室负责人','college':'学院负责人','school':'学校办理人员'}
# 合成的分组字段在页面上没有同名控件，按下面的位置定位。
FIELD_TARGETS={'aud':'[name^="aud_"]','svc':'[name^="svc_"]','tm':'[name^="tm_"]','dir':'[name^="dir_"]','checked':'#close-check-all','org_ids':'.notice-scope-list','duty_people':'#duty-options','duty_query':'#duty-query','head_pick':'#head-results','head_query':'#head-q'}
POLICY_TOPICS={'policy','rules','annual'}
# 每个字段的配音与手册用同一句说明（fieldSentences），只是不念出长长的可选项清单。
FORMS_SCRIPT="import {HELP_FORMS} from './frontend/help-forms.js';import {fieldSentences} from './frontend/help-system.js';for(const forms of Object.values(HELP_FORMS))for(const f of forms)for(const x of f.fields)x.speech=fieldSentences(x,{options:false}).join('');console.log(JSON.stringify(HELP_FORMS))"

def opening(topic,form,variant_index,variants):
    earlier=[v for v in variants[:variant_index] if v['title']==form['title']]
    if earlier:return f'下面是{ROLE_TITLES[form["role"]]}版本，只讲和前面不同的地方。'
    if variant_index:return f'接下来讲“{form["title"]}”，前面讲过的相同栏目不再重复。'
    text=f'{form["title"]}。下面逐项说明每一栏怎么填。画面里都是虚构资料，演示不会提交。'
    if topic in POLICY_TOPICS:text+='制度和计分参数要按学校正式确认的依据填写，不要照抄示例。'
    return text

def segments_for(topic,form,variant_index,variants,spoken):
    seen=set();segments=[{'title':form['title'] if not variant_index else ROLE_TITLES[form['role']]+'版本','text':unique_sentences(opening(topic,form,variant_index,variants),seen),'key':None}]
    for field in form['fields']:
        if not field['key']:continue
        signature=(field['key'],field['label'],field['speech'])
        if signature in spoken:continue
        spoken.add(signature)
        text=unique_sentences(field['label']+'。'+field['speech'],seen)
        if text:segments.append({'title':field['label'],'text':text,'key':field['key']})
    return segments

def show_field(p,key,title):
    selector=FIELD_TARGETS.get(key)
    candidates=[selector] if selector else ['#edit-form ['+attr+'='+json.dumps(key)+']' for attr in ['name','data-r','data-or']]
    field=p.locator(','.join(candidates)).first
    if field.count() and field.is_visible():
        field.scroll_into_view_if_needed()
        try:field.focus()
        except Exception:pass
        help_box=field.locator('xpath=ancestor::*[contains(concat(" ",normalize-space(@class)," ")," form-field ") or contains(concat(" ",normalize-space(@class)," ")," rule-control ")][1]').locator('.field-how')
        if help_box.count() and help_box.first.get_attribute('open') is None:help_box.first.locator('summary').click()
        return
    # Inactive conditional fields stay inactive; show their conditional instructions instead.
    if not p.locator('.help-panel').count():p.locator('#modal-root [data-open-help]').click();p.locator('[data-help-tab=fields]').click()
    explanation=p.locator('.help-panel-body .help-field').filter(has_text=title).first
    if explanation.count():explanation.scroll_into_view_if_needed()

def reusable(folder,segments):
    source,clip,timing=folder/'speech.json',folder/'final.mp4',folder/'timings.json'
    if not (clip.is_file() and source.is_file() and timing.is_file()):return False
    if [{k:s[k] for k in ('title','text','key')} for s in json.loads(source.read_text(encoding='utf-8'))]!=segments:return False
    for segment,duration in zip(segments,json.loads(timing.read_text(encoding='utf-8'))):segment['duration']=duration
    return True

def run(args):
    lab=Path(args.lab).resolve()
    if lab.name!='integrated-help-20261022' or not (lab/'synthetic.sqlite').is_file():raise ValueError('Owned synthetic lab required')
    password=json.loads((lab/'private-login.json').read_text(encoding='utf-8'))['password']
    forms=json.loads(subprocess.check_output(['node','--input-type=module','-e',FORMS_SCRIPT],cwd=ROOT))
    output=ROOT/'frontend/assets/help'/VERSION
    with sync_playwright() as pw:
        for index,(topic,variants) in enumerate(forms.items()):
            if index%args.parts!=args.part:continue
            if args.topics and topic not in args.topics.split(','):continue
            existing=json.loads((ROOT/'frontend/help-media.js').read_text(encoding='utf-8').split('export const HELP_MEDIA=',1)[1].strip().removesuffix(';'))
            if existing.get(topic,{}).get('filling',{}).get('paced') and not args.redo:continue
            clips=[];captions=['WEBVTT',''];chapters=[];offset=0;spoken=set()
            for variant_index,form in enumerate(variants):
                display_title=form['title']+'（'+ROLE_TITLES[form['role']]+'）'
                folder=lab/'form-recordings'/topic/str(variant_index);folder.mkdir(parents=True,exist_ok=True)
                segments=segments_for(topic,form,variant_index,variants,spoken)
                if len(segments)==1:continue
                if reusable(folder,segments):print('复用已录制片段：'+display_title,flush=True)
                else:
                    for old in folder.glob('*.webm'):old.unlink()
                    audio(segments,folder)
                    (folder/'timings.json').write_text(json.dumps([s['duration'] for s in segments]),encoding='utf-8')
                    browser=pw.chromium.launch(args=['--renderer-process-limit=1'])
                    ctx,p=login(browser,form['user'],password);state=ctx.storage_state();ctx.close()
                    rec=browser.new_context(storage_state=state,viewport={'width':1360,'height':900},record_video_dir=str(folder),record_video_size={'width':1360,'height':900})
                    use_demo_branding(rec,lab)
                    p=rec.new_page();p.set_default_timeout(12000);nav(p,topic)
                    for setup in form.get('setup',[]):
                        click_action(p,f'#content [data-action="{setup["action"]}"][data-id="{setup["id"]}"]');p.locator('#modal-root:not(.hidden) .modal-head h2').wait_for()
                    target=p.locator(f'{form.get("scope","#content")} [data-action="{form["action"]}"][data-id="{form["action_id"]}"]').first
                    if not target.is_visible():target.locator('xpath=ancestor::details[1]').locator('summary').first.click()
                    target.click();p.locator('#edit-form').wait_for();p.wait_for_timeout(400)
                    start=time.monotonic();video=p.video;scenes=[]
                    for segment in segments:
                        began=time.monotonic()
                        if segment['key']:
                            try:show_field(p,segment['key'],segment['title'])
                            except Exception as error:print('  画面定位未完成（不影响配音）：',segment['title'],type(error).__name__,flush=True)
                        p.wait_for_timeout(SCENE_SETTLE_MS)
                        scenes.append((began-start,time.monotonic()-start,segment['duration']))
                        if p.locator('.help-panel').count():p.locator('[data-help-close]').click()
                    end=time.monotonic();rec.close();raw=Path(video.path());browser.close()
                    trim=max(0,probe_duration(args.ffprobe,raw)-(end-start))
                    assemble(args.ffmpeg,raw,trim,scenes,folder/'narration.wav',folder,folder/'final.mp4',sum(s['duration'] for s in segments))
                    print('逐项填写录制完成：'+display_title,flush=True)
                at=offset
                for segment in segments:
                    chapters.append({'title':display_title+' / '+segment['title'],'time':round(at,2)})
                    caption_cues(segment['text'],at,segment['duration'],captions);at+=segment['duration']
                clips.append(folder/'final.mp4');offset=at
            listing=lab/'form-recordings'/topic/'concat.txt';listing.write_text(''.join("file '"+c.as_posix()+"'\n" for c in clips),encoding='utf-8')
            subprocess.run([args.ffmpeg,'-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',str(listing),'-c','copy','-movflags','+faststart',str(output/f'{topic}-filling.mp4')],check=True)
            (output/f'{topic}-filling.vtt').write_text('\n'.join(captions),encoding='utf-8')
            item={'src':f'/assets/assets/help/{VERSION}/{topic}-filling.mp4','captions':f'/assets/assets/help/{VERSION}/{topic}-filling.vtt','poster':f'/assets/assets/help/{VERSION}/{topic}.jpg','version':VERSION,'paced':True,'duration':round(offset,2),'chapters':chapters,'covered_forms':[f['title'] for f in variants],'description':'真实表单逐项讲解，说明字段含义、示例和条件；使用虚构资料，不提交业务。可通过章节直接跳到某一栏。'}
            save_manifest(lab,ROOT/'frontend/help-media.js',topic,{'filling':item})
            print('填写视频已生成：'+topic,flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--lab',required=True);parser.add_argument('--ffmpeg',required=True);parser.add_argument('--ffprobe',required=True);parser.add_argument('--parts',type=int,default=1);parser.add_argument('--part',type=int,default=0);parser.add_argument('--redo',action='store_true');parser.add_argument('--topics');parser.add_argument('--paced',action='store_true',help='兼容旧参数；现在总是按场景定格录制');run(parser.parse_args())
