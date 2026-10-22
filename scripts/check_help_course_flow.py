"""Real UI submit/return/amend/approve regression in the owned synthetic help lab."""
from pathlib import Path
import argparse,json,time,wave,subprocess,re
from playwright.sync_api import sync_playwright
from check_help_browser import ROOT,login,nav,ORIGIN
from record_help import audio,stamp,save_manifest,VERSION

def run(args):
    lab=Path(args.lab).resolve()
    if lab.name!='integrated-help-20261022' or not (lab/'synthetic.sqlite').exists():raise ValueError('Owned synthetic lab required')
    password=json.loads((lab/'private-login.json').read_text(encoding='utf-8'))['password']
    out=lab/'course-flow';out.mkdir(exist_ok=True);proof=[];movies=[];active={}
    with sync_playwright() as pw:
        browser=pw.chromium.launch()
        def session(user):
            ctx,p=login(browser,user,password)
            if args.record:
                state=ctx.storage_state();ctx.close()
                folder=out/f'clip-{len(movies)}';folder.mkdir(exist_ok=True)
                ctx=browser.new_context(storage_state=state,viewport={'width':1360,'height':900},record_video_dir=str(folder),record_video_size={'width':1360,'height':900})
                started=time.monotonic();p=ctx.new_page();p.set_default_timeout(12000)
                entry={'ctx':ctx,'p':p,'start':started,'events':[],'folder':folder};movies.append(entry);active[id(ctx)]=entry
            return ctx,p
        def finish(ctx):
            if not args.record:ctx.close();return
            entry=active[id(ctx)];video=entry['p'].video;ctx.close();entry['raw']=Path(video.path())
        def screenshot(p,label):
            p.screenshot(path=str(out/f'{len(proof)+1:02}.png'));proof.append({'step':label,'screen':f'{len(proof)+1:02}.png'})
            if args.record:
                entry=active[id(p.context)]
                spoken=label.replace('：depthead','，教研室负责人').replace('：collegehead','，学院负责人').replace('：reviewer','，学校归口复审人员')
                detail={'教师填写时查看帮助':'填写课程编号、名称、学时及课程简介，选择实际教学方式和思政属性。打开填写说明可核对每一项，关闭后已填内容仍在。','教师提交后进入教研室审核':'提交后显示实际办理方。此时申请人等待审核，不要重复新建。','教研室退回补正：depthead':'审核人写清缺少的内容，这次要求补充学员完成培训后掌握的技能。','教师补正保存，仍需重新提交':'原来正确的信息保留。补充课程简介并保存后，仍要点击重新提交。','教师重新提交':'重新提交后从退回环节继续办理。','审批通过：depthead':'教研室核对补正资料后通过，进入学院审批。','审批通过：collegehead':'学院负责人核对资料后通过，进入学校归口复审。','审批通过：reviewer':'学校归口核对后通过，课程进入培训课程库。','教师回看最终入库结果':'详情显示已入培训课程库，办理记录保留退回、补正和各级通过的过程。课程入库不直接产生培训积分。'}[label]
                segments=[{'text':spoken+'。'+detail}];folder=entry['folder']/f'voice-{len(entry["events"])}';audio(segments,folder)
                start=time.monotonic()-entry['start'];entry['events'].append({'title':spoken,'start':start,'duration':segments[0]['duration'],'text':segments[0]['text'],'wav':folder/'narration.wav'})
                p.wait_for_timeout(segments[0]['duration']*1000)
            (out/'progress.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
            print(label,flush=True)
        def approve(user,ident,action,reason):
            ctx,p=session(user);nav(p,'todos')
            p.locator(f'[data-action=todo][data-id="application|{ident}"]').click()
            p.locator(f'[data-action="app-{action}"]').click()
            p.locator('#edit-form [name=reason]').fill(reason)
            p.locator('button[form=edit-form][value=submit]').click()
            p.locator('#edit-form').wait_for(state='detached');p.locator('#modal-root:not(.hidden) .badge').wait_for()
            screenshot(p,{'return':'教研室退回补正','approve':'审批通过'}[action]+'：'+user)
            finish(ctx)
        ctx,p=session('teacher');nav(p,'apply_course')
        p.locator('[data-action=teacher-apply][data-id="courses|app-course-new"]').click();p.locator('#edit-form').wait_for()
        code='HELP-FLOW-'+str(int(time.time()))
        for name,value in {'code':code,'name':'社区茶艺操作教学（虚构）','hours':'8','intro':'面向社区居民，学习基本泡茶方法。','reason':'本地操作教学验证，非学校真实业务'}.items():p.locator(f'#edit-form [name="{name}"]').fill(value)
        p.locator('[name=teaching_mode][value=practice]').check();p.locator('[name=ideology][value=course_ideology]').check()
        # Filling help must not remove any typed value or submit on its own.
        before=p.locator('#edit-form').evaluate('f=>new FormData(f).get("name")')
        p.locator('#modal-root [data-open-help]').click();p.locator('[data-help-tab=fields]').click();screenshot(p,'教师填写时查看帮助');p.locator('[data-help-close]').click()
        assert p.locator('#edit-form [name=name]').input_value()==before
        p.locator('button[form=edit-form][value=submit]').click();p.locator('[data-action=app-withdraw]').wait_for()
        ident=p.locator('[data-action=app-withdraw]').get_attribute('data-id');screenshot(p,'教师提交后进入教研室审核');finish(ctx)
        approve('depthead',ident,'return','请补充培训完成后学员能够掌握的技能。')
        ctx,p=session('teacher');nav(p,'apply_course');p.locator(f'[data-action=app-detail][data-id="{ident}"]').first.click();p.locator('[data-action=app-edit]').click()
        assert p.locator('#edit-form [name=name]').input_value()==before
        p.locator('#edit-form [name=intro]').fill('面向社区居民，学习泡茶步骤、茶席布置和基本礼仪；完成后能独立布置茶席并冲泡一款茶。')
        p.locator('#edit-form [name=reason]').fill('已按退回意见补充预期技能，其他正确资料保留。')
        p.locator('button[form=edit-form][value=submit]').click();p.locator('[data-action=app-submit]').wait_for();screenshot(p,'教师补正保存，仍需重新提交')
        p.locator('[data-action=app-submit]').click();p.locator('button[form=edit-form][value=submit]').click();p.locator('#edit-form').wait_for(state='detached');p.locator('#modal-root:not(.hidden) .badge').wait_for();screenshot(p,'教师重新提交');finish(ctx)
        approve('depthead',ident,'approve','已核对补正内容，同意进入学院审批。')
        approve('collegehead',ident,'approve','学院已核对课程资料，同意进入学校复审。')
        approve('reviewer',ident,'approve','归口已核对，同意进入培训课程库。')
        ctx,p=session('teacher');nav(p,'apply_course');p.locator(f'[data-action=app-detail][data-id="{ident}"]').first.click()
        p.locator('#modal-root .application-detail').wait_for();text=p.locator('#modal-root').inner_text();assert '已入培训课程库' in text and '学校通过培训课程申报' in text,text
        screenshot(p,'教师回看最终入库结果');finish(ctx);browser.close()
    (out/'report.json').write_text(json.dumps({'synthetic_only':True,'application_id':ident,'course_code':code,'checks':proof,'school_acceptance':False},ensure_ascii=False,indent=2),encoding='utf-8')
    if args.record:
        captions=['WEBVTT',''];chapters=[];offset=0;clips=[]
        for entry in movies:
            duration=float(json.loads(subprocess.check_output([args.ffprobe,'-v','error','-show_format','-of','json',str(entry['raw'])]))['format']['duration'])
            with wave.open(str(entry['events'][0]['wav']),'rb') as w:params=w.getparams()
            frame_size=params.nchannels*params.sampwidth;rate=params.framerate
            pcm=bytearray(round((duration+1)*rate)*frame_size)
            for e in entry['events']:
                with wave.open(str(e['wav']),'rb') as w:data=w.readframes(w.getnframes())
                start=round(e['start']*rate)*frame_size;pcm[start:start+len(data)]=data
                chapters.append({'title':e['title'],'time':round(offset+e['start'],2)})
                chunks=re.findall(r'.{1,28}',e['text']);at=offset+e['start'];total=sum(map(len,chunks))
                for chunk in chunks:
                    span=e['duration']*len(chunk)/total;captions.extend([f'{stamp(at)} --> {stamp(at+span)}',chunk,'']);at+=span
            wav=entry['folder']/'mixed.wav'
            with wave.open(str(wav),'wb') as w:w.setparams(params);w.writeframes(bytes(pcm))
            clip=entry['folder']/'final.mp4';subprocess.run([args.ffmpeg,'-hide_banner','-loglevel','error','-y','-threads','1','-i',str(entry['raw']),'-i',str(wav),'-t',str(duration),'-map','0:v:0','-map','1:a:0','-c:v','libx264','-preset','veryfast','-crf','26','-threads','1','-pix_fmt','yuv420p','-c:a','aac','-movflags','+faststart',str(clip)],check=True)
            clips.append(clip);offset+=duration
        files=out/'concat.txt';files.write_text(''.join("file '"+c.as_posix()+"'\n" for c in clips),encoding='utf-8')
        target=ROOT/'frontend/assets/help'/VERSION
        subprocess.run([args.ffmpeg,'-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',str(files),'-c','copy','-movflags','+faststart',str(target/'course-flow.mp4')],check=True)
        (target/'course-flow.vtt').write_text('\n'.join(captions),encoding='utf-8')
        save_manifest(lab,ROOT/'frontend/help-media.js','apply_course',{'src':f'/assets/assets/help/{VERSION}/course-flow.mp4','poster':f'/assets/assets/help/{VERSION}/apply_course.jpg','captions':f'/assets/assets/help/{VERSION}/course-flow.vtt','chapters':chapters,'duration':round(offset,2),'version':VERSION,'description':'真实录屏：教师填写提交、教研室退回、教师补正重提、教研室与学院通过、学校归口复审及最终入库。使用独立虚构资料。'})
        print('完整课程流程视频已生成',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--lab',required=True);parser.add_argument('--record',action='store_true');parser.add_argument('--ffmpeg');parser.add_argument('--ffprobe');run(parser.parse_args())
