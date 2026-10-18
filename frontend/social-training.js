// School business pages reuse the portal's forms, permissions, navigation and attachments.
import {checkUploadFiles,uploadEntries,uploadSequential,uploadStatusHtml,failedEntries,MAX_ATTACHMENTS} from './approval-flow.js?v=20261017-multi-materials2';
import {renderTrainingWorkspace,trainingChange} from './training-workspace.js?v=20261018-claude3';
import {progressHtml,AUDIENCE,TEACHING_MODES,IDEOLOGY} from './applications.js?v=20261018-design6&materials=20261017-preview2&approvalfix=20261018-1';
const names={module:'模块式',person_day:'人天式',technical:'技术类',lecture:'讲座类',province:'省级',city:'市级或企业定制',school:'校级',dispatched:'统一委派异地送教',full_day:'全天实操或脱产',ordinary:'常规',subsidy:'补贴性培训',enterprise:'企业定制培训',community:'社区公益培训',rural:'乡村帮扶培训',other:'其他非学历培训',national:'国家级'};
let workspace,context,opened,workspaceUser;
let listSection='',listPage=1,listSearch='',resourcePage=1;
let projectChoice;
// 上传未完成的材料按业务对象暂存在本页，详情里只补传失败的那几份；办理结果提示只显示一次。
const pendingUploads=new Map(),outcomeNotes=new Map();
const path=(kind,id)=>'/social/objects/'+kind+'/'+id;
const REVIEW_STATES={DRAFT:'待发送教师',TEACHER:'待教师回应',COLLEGE:'待学院裁定',CLOSED:'已办结'};
const BASE_USAGE_OPTIONS=[['practice','实践教学基地'],['ideology','思政实践教学基地']],BASE_LEVEL_OPTIONS=[['school','校级'],['city','市级'],['province','省级及以上']];
// 基地修改表单带全用途、级别、设立日期和共建单位；其他类型不提交这几项，后端只合并提交的字段。
export function resourceFormValue(kind,raw){const v={...raw};for(const [k] of BASE_USAGE_OPTIONS)delete v['usage_'+k];if(kind==='base'){v.usages=BASE_USAGE_OPTIONS.map(([k])=>k).filter(k=>raw['usage_'+k]);v.established_on=raw.established_on||null;v.partner=raw.partner||''}return v}
const selectable=(values,blank=false)=>[...(blank?[['','待学校确认']]:[]),...values.map(v=>[v,names[v]||v])];
const blankNull=v=>Object.fromEntries(Object.entries(v).map(([k,x])=>[k,x===''?null:x]));
const tone=state=>['ARCHIVED','CLOSED','ACTIVE'].includes(state)?'green':['RETURNED','DRAFT'].includes(state)?'amber':'blue';
const statusBadge=(label,state)=>'<span class="social-badge" data-tone="'+(label==='已登记'?'blue':tone(state))+'">'+context.esc(label)+'</span>';
const identity=(name,code,icon)=>'<div class="social-identity"><span class="social-list-icon">'+context.icon(icon)+'</span><div><strong>'+context.esc(name)+'</strong><small>'+context.esc(code)+'</small></div></div>';

export function parseTrainingRows(text,mode,teachers){
 const raw=String(text??'').replace(/^\ufeff/,'').split(/\r?\n/).filter(line=>line.replace(/[\t,\s]/g,'')),sep=raw[0]?.includes('\t')?'\t':',';
 const lines=raw.map(line=>{const v=splitCells(line,sep);while(v.length>18&&v[v.length-1]==='')v.pop();return v.join('\t')});
 if(lines.length<2)throw Error('请上传模板文件或粘贴包含表头和明细的表格内容');
 const expected=['单元编号','课程编号','班级编号','模块名称','培训日期','学员编号','本校全日制生','准毕业生例外','实名签到','学时达标','全程参训','结业通过','重点群体','剔除原因','教师工号','岗位','人员类型','佐证说明'];
 if(lines[0].split('\t').join('|')!==expected.join('|'))throw Error('表头不符，请点“下载导入模板”，按模板18列填写');
 const yes=(v,row)=>{if(!['是','否'].includes(v))throw Error('第'+row+'行的判断项须填“是”或“否”');return v==='是'};
 const groups=new Map();
 for(let i=1;i<lines.length;i++){
  const v=lines[i].split('\t');if(v.length!==18)throw Error('第'+(i+1)+'行必须有18列');
  const t=teachers.find(t=>t.staff_no===v[14]);if(!t&&v[16]!=='外聘')throw Error('第'+(i+1)+'行教师工号不在授权列表，请先检索该教师');
  if(!t&&!/^[A-Za-z0-9_-]{1,64}$/.test(v[14]))throw Error('外聘人员请使用学校唯一编号，限字母、数字、下划线或短横线');
  const role={'主讲':'lecturer','实训指导':'instructor','管理辅助':'manager'}[v[15]],staff_type={'校内':'internal','外聘':'external'}[v[16]];
  if(!role||!staff_type)throw Error('岗位须为主讲、实训指导或管理辅助；人员类型须为校内或外聘');
  const day=String(v[4]).trim().match(/^(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})日?$/);if(!day)throw Error('第'+(i+1)+'行培训日期“'+v[4]+'”无法识别，请写成 2026-09-10 或 2026/9/10');const meta={external_key:v[0],course_code:v[1],class_code:v[2],module:v[3],event_date:day[1]+'-'+day[2].padStart(2,'0')+'-'+day[3].padStart(2,'0'),mode,evidence_note:v[17]};
  let group=groups.get(v[0]);if(!group){group={...meta,learners:[],teachers:[]};groups.set(v[0],group)}
  if(Object.keys(meta).some(k=>group[k]!==meta[k]))throw Error('同一单元编号的课程、日期等信息不一致');
  const learner={reference:v[5],full_time_student:yes(v[6],i+1),graduate_exception:yes(v[7],i+1),signed:yes(v[8],i+1),hours_met:yes(v[9],i+1),full_attendance:yes(v[10],i+1),passed:yes(v[11],i+1),priority_group:yes(v[12],i+1),exclusion_reason:v[13]};
  const previous=group.learners.find(x=>x.reference===learner.reference);
  if(previous&&JSON.stringify(previous)!==JSON.stringify(learner))throw Error('同一学员在同一单元的参训依据不一致');
  if(!previous)group.learners.push(learner);
  const work={teacher_id:t?.id||v[14],role,staff_type},old=group.teachers.find(x=>x.teacher_id===work.teacher_id);
  if(old&&JSON.stringify(old)!==JSON.stringify(work))throw Error('同一教师在同一单元的岗位不一致');
  if(!old)group.teachers.push(work);
 }
 return [...groups.values()];
}

const CHAOXING_COLUMNS={name:['课程名称','课程名'],code:['课程编号','课程ID','课程代码'],project_code:['项目编号'],teacher:['授课教师','教师','主讲教师','教师姓名'],video_count:['视频数','视频数量','视频个数'],video_minutes:['视频时长','视频总时长','总时长'],chapters:['章节数','章节数量'],learners:['学习人数','选课人数']};
const headerKey=v=>String(v??'').replace(/^﻿/,'').replace(/\s+/g,'').replace(/（/g,'(').replace(/）/g,')').replace(/\((分钟|分|min)\)$/i,'').toLowerCase();
const splitCells=(line,sep)=>{const cells=[];let cell='',quoted=false;for(let i=0;i<line.length;i++){const ch=line[i];if(quoted){if(ch==='"'&&line[i+1]==='"'){cell+='"';i++}else if(ch==='"')quoted=false;else cell+=ch}else if(ch==='"'&&!cell)quoted=true;else if(ch===sep){cells.push(cell);cell=''}else cell+=ch}cells.push(cell);return cells.map(x=>x.trim())};
// 超星导出的时长可能是分钟数、“hh:mm:ss”、“mm:ss”或“1小时20分钟”等写法，统一折算为分钟（保留两位小数）。
export function chaoxingMinutes(value){
 const v=String(value??'').trim().replace(/\s+/g,'');if(!v||/^-+$/.test(v))return null;
 const round=x=>Math.round(x*100)/100;let m;
 if(/^\d+(\.\d+)?$/.test(v))return round(Number(v));
 if((m=v.match(/^(\d+):(\d{1,2}):(\d{1,2})$/)))return round(Number(m[1])*60+Number(m[2])+Number(m[3])/60);
 if((m=v.match(/^(\d+):(\d{1,2})$/)))return round(Number(m[1])+Number(m[2])/60);
 if((m=v.match(/^(?:(\d+(?:\.\d+)?)(?:小时|时|h))?(?:(\d+(?:\.\d+)?)(?:分钟|分|min))?(?:(\d+(?:\.\d+)?)(?:秒|s))?$/i))&&(m[1]||m[2]||m[3]))return round(Number(m[1]||0)*60+Number(m[2]||0)+Number(m[3]||0)/60);
 throw Error('视频时长“'+value+'”无法识别，请填写分钟数、hh:mm:ss 或“xx分钟”');
}
export function parseChaoxingCourses(text,projectCode=''){
 const lines=String(text??'').replace(/^﻿/,'').split(/\r?\n/).filter(line=>line.trim()),aliases=Object.entries(CHAOXING_COLUMNS).map(([k,v])=>[k,v.map(headerKey)]);
 const at=lines.findIndex(line=>{const keys=splitCells(line,line.includes('\t')?'\t':',').map(headerKey);return ['name','code'].every(k=>CHAOXING_COLUMNS[k].map(headerKey).some(a=>keys.includes(a)))});
 if(at<0)throw Error('未找到超星导出表表头，须包含“课程名称”和“课程编号（或课程ID）”两列');
 const sep=lines[at].includes('\t')?'\t':',',header=splitCells(lines[at],sep).map(headerKey),column={};
 for(const [k,list] of aliases){const i=header.findIndex(h=>list.includes(h));if(i>=0)column[k]=i}
 if(!lines.slice(at+1).length)throw Error('导出表中没有课程明细');
 const count=(v,row,label)=>{const x=String(v??'').replace(/,/g,'').trim();if(!x||/^-+$/.test(x))return null;if(!/^\d+$/.test(x))throw Error('第'+row+'行的'+label+'须为整数');return Number(x)};
 const seen=new Set();
 return lines.slice(at+1).map((line,i)=>{
  const v=splitCells(line,sep),row=at+i+2,get=k=>column[k]===undefined?'':(v[column[k]]??'').trim();
  const code=get('code'),name=get('name'),project_code=get('project_code')||projectCode;
  if(!code||!name)throw Error('第'+row+'行缺少课程编号或课程名称');
  if(!project_code)throw Error('请先选择关联项目');
  if(seen.has(code))throw Error('第'+row+'行课程编号重复：'+code);seen.add(code);
  let video_minutes;try{video_minutes=chaoxingMinutes(get('video_minutes'))}catch(err){throw Error('第'+row+'行'+err.message)}
  const video_count=count(get('video_count'),row,'视频数');
  if(video_count&&video_minutes==null)throw Error('第'+row+'行有视频数但缺少视频时长');
  return {code,name,project_code,source:'chaoxing',teacher:get('teacher'),video_count,video_minutes,chapters:count(get('chapters'),row,'章节数'),learners:count(get('learners'),row,'学习人数')};
 });
}
async function readImportFile(file){
 if(/\.xlsx?$/i.test(file.name))throw Error('请在 Excel 中将超星导出表另存为 CSV 后上传，或直接复制表格内容粘贴');
 const bytes=await file.arrayBuffer();try{return new TextDecoder('utf-8',{fatal:true}).decode(bytes)}catch{return new TextDecoder('gbk').decode(bytes)}
}
async function importCourses(rows,v,returnTo){
 const c=context,body={rows:rows.map(r=>({...r,reason:v.reason,basis:v.basis})),reason:v.reason,basis:v.basis};
 const preview=await c.api('/social/courses/import/preview',{method:'POST',body});setTimeout(()=>c.formModal('确认课程整批入库',c.note('预检通过，共'+preview.count+'门课程'+(preview.videos?'，其中'+preview.videos+'门同时登记视频数量与总时长':'')+'。'),async()=>{await c.api('/social/courses/import/confirm',{method:'POST',body:{...body,preview_hash:preview.preview_hash}});c.closeModal();await c.render()},{submit:'确认入库',returnTo,returnLabel:'返回修改'}),0);
}

const APPLYING=['DEPT','COLLEGE','SCHOOL','RETURNED','WITHDRAWN'],BASE_USAGE={practice:'实践教学基地',ideology:'思政实践教学基地'};
const MODE_LABEL=Object.fromEntries(TEACHING_MODES),IDEOLOGY_LABEL=Object.fromEntries(IDEOLOGY);
const pending=()=>'<span class="muted small">待补充</span>';
function courseModes(info){const e=context.esc;return info.teaching_mode||info.ideology?e(MODE_LABEL[info.teaching_mode]||'待补充')+'<br><span class="muted small">'+e(IDEOLOGY_LABEL[info.ideology]||'思政属性待补充')+'</span>':pending()}
function coursewareText(w){return w?.checked?'已审查（'+[w.reviewer,w.reviewed_on].filter(Boolean).join(' ')+'）':'未审查'}
function courseTeacher(info){const e=context.esc;return info.teacher_name||info.courseware?e(info.teacher_name||'待补充')+'<br><span class="muted small">课件'+e(coursewareText(info.courseware))+'</span>':pending()}
function resourceCell(stats){return stats.resources?context.esc(stats.resources+' 项资源 · '+stats.videos+' 个视频 · '+stats.minutes+' 分钟'):'<span class="muted small">暂无资源</span>'}
// 走申请流程的基地看申请详情（带进度）；其他照旧。
function resourceOpen(x){const c=context;if(x.data?.application)return c.act(APPLYING.includes(x.state)?'看进度':'查看','app-detail',x.id,'text');return c.act(['teacher','dept'].includes(c.me?.role?.kind)?'查看':'查看与办理','social-detail','social_resource|'+x.id,'text')}
const COURSE_COLUMNS=['课程编号','课程名称','关联项目编号','学时','教学方式','思政属性','主讲教师','课件审查'];
function courseInfoFields(){const c=context;return c.field('hours','学时','number','',{required:false,min:0,step:'0.5'})+c.field('teaching_mode','教学方式','select','lecture',{options:TEACHING_MODES,chips:true})+c.field('ideology','思政属性','select','course_ideology',{options:IDEOLOGY,chips:true})
 +c.field('package','培训包','checkbox',false,{required:false,checkLabel:'按培训包开发（成套的教学包）'})+c.field('one_skill','“一人一技”专项','checkbox',false,{required:false,checkLabel:'面向“一人一技”专项培训行动'})+c.field('target_groups','重点群体与行动对接','textarea','',{required:false,full:true,hint:'勾选“一人一技”专项时必填。'})
 +c.teacherField('','teacher_id','主讲教师（输入工号或姓名检索）')+c.field('cw_checked','课件审查','checkbox',false,{required:false,checkLabel:'课件已由学院审查（政治方向、知识产权、内容质量）'})+c.field('cw_reviewer','审查人','text','',{required:false})+c.field('cw_reviewed_on','审查日期','date','',{required:false})}
function courseInfoValue(v){const{cw_checked,cw_reviewer,cw_reviewed_on,hours,teacher_id,teacher_id_search,...rest}=v;return {...rest,hours:hours===''||hours==null?null:hours,teacher_id:teacher_id||null,courseware:cw_checked?{checked:true,reviewer:cw_reviewer||'',reviewed_on:cw_reviewed_on||null}:null}}
function pick(pairs,text,label,line){const t=String(text||'').trim();if(!t)return null;const hit=pairs.find(([k,l])=>l===t||k===t);if(!hit)throw Error('第'+line+'行'+label+'“'+t+'”无法识别，可填：'+pairs.map(x=>x[1]).join('、'));return hit[0]}
export function parseCourseRows(text,teachers=context?.teachers||[]){
 const lines=String(text||'').trim().split(/\r?\n/),head=(lines.shift()||'').split('\t').map(x=>x.trim());
 const old=head.join('|')==='课程编号|课程名称|项目编号';
 if(!old&&head.join('|')!==COURSE_COLUMNS.join('|'))throw Error('请保留表头：'+COURSE_COLUMNS.join('、'));
 return lines.filter(l=>l.trim()).map((line,i)=>{const n=i+2,v=line.split('\t').map(x=>x.trim());if(v.length>(old?3:8))throw Error('第'+n+'行列数多于表头');
  const[code,name,project_code,hours,mode,ideology,teacher,review]=v;if(!code||!name||!project_code)throw Error('第'+n+'行须填写课程编号、课程名称和关联项目编号');
  const row={code,name,project_code};if(old)return row;
  if(hours){if(!/^\d+(\.\d+)?$/.test(hours))throw Error('第'+n+'行学时“'+hours+'”不是数字');row.hours=hours}
  const m=pick(TEACHING_MODES,mode,'教学方式',n),g=pick(IDEOLOGY,ideology,'思政属性',n);if(m)row.teaching_mode=m;if(g)row.ideology=g;
  if(teacher){const[tn,staff]=teacher.split(/\s+/),t=staff&&teachers.find(x=>x.staff_no===staff);row.teacher=tn;if(t)row.teacher_id=t.id}
  if(review&&review!=='未审查'){const parts=review.split(/\s+/);if(parts[0]!=='已审查')throw Error('第'+n+'行课件审查请填“未审查”或“已审查 审查人 日期”');const day=parts.find(x=>/^\d{4}-\d{2}-\d{2}$/.test(x));
   row.courseware={checked:true,reviewer:parts.slice(1).filter(x=>x!==day).join(' '),reviewed_on:day||null}}
  return row});
}
function courseView(code){
 const c=context,e=c.esc,x=workspace.courses.find(r=>r.code===code);if(!x)throw Error('课程不在当前列表里，请刷新');
 const info=workspace.course_info?.[code]||{},stats=workspace.course_stats[code]||{resources:0,videos:0,minutes:0};
 const rows=[['课程名称',e(x.name)],['课程编号',e(x.code)],['关联项目',e(workspace.projects.find(p=>p.data.code===x.project_code)?.data.name||(x.project_code?'项目名称待核对':'未关联项目'))],['来源',e(x.source||'')],['学时',info.hours!=null?e(info.hours):'待补充'],['教学方式',e(MODE_LABEL[info.teaching_mode]||'待补充')],
  ['思政属性',e(IDEOLOGY_LABEL[info.ideology]||'待补充')],['主讲教师',e(info.teacher_name||'待补充')],['培训包',info.package?'是':'否'],['“一人一技”专项',info.one_skill?e('是 · '+(info.target_groups||'')):'否'],['课件审查',e(coursewareText(info.courseware))],...(info.audience?[['面向对象',e(info.audience)]]:[]),...(info.intro?[['课程简介',e(info.intro)]]:[]),
  ['资源与视频',e(stats.resources+' 项资源，'+stats.videos+' 个视频，视频总时长 '+stats.minutes+' 分钟')]];
 const foot=[c.act('查看资源','social-course-resources',code),...(info.application_id?[c.act('查看申请记录','app-detail',info.application_id)]:[]),c.act('关闭','close','','primary')].join('');
 return c.modal(x.name,detailFacts('课程资料',rows)+(Object.keys(info).length?'':c.note('历史课程资料待完善，请由课程登记方核对补齐；无维护权限的教师当前无需操作。',true)),foot);
}

// 导出上报表：选区间 → 预检缺项（点项目名去补）→ 下载“项目清单”和“绩效数据”两张表。
let reportRange={start:'2023-07-01',end:'2026-06-30',year:''},reportResult=null;
function schoolYears(){const now=new Date(),last=now.getMonth()>=8?now.getFullYear():now.getFullYear()-1,out=[];for(let y=last;y>=2020;y--)out.push(y+'-'+(y+1));return out}
function reportModal(){
 const c=context,e=c.esc,r=reportResult;
 const form='<form id="report-range-form" class="report-range" onsubmit="return false"><label>开始日期<input type="date" id="report-start" value="'+e(reportRange.start)+'"></label><label>结束日期<input type="date" id="report-end" value="'+e(reportRange.end)+'"></label>'
  +'<label>或按学年<select id="report-year"><option value="">用左边的起止日期</option>'+schoolYears().map(y=>'<option value="'+y+'"'+(reportRange.year===y?' selected':'')+'>'+y+' 学年</option>').join('')+'</select></label></form>';
 let body=c.note('默认是上级给的统计区间（2023-07-01 至 2026-06-30），也可以选学年。只统计已备案及以后的项目；'+(c.me?.role?.kind==='school'?'学校导出全校。':'学院导出本院，用于自查。'))+form;
 if(r){
  body+='<div class="report-result">'+(r.count?'<p><strong>'+e(r.start+' 至 '+r.end)+'</strong>：'+e(r.scope)+'共 '+r.count+' 个项目，'+(r.blocked?'<span class="badge orange-b">'+r.blocked+' 个缺上报信息</span>，点项目名打开后用“补填上报信息”补齐。':'<span class="badge green-b">全部齐全</span>，可以下载。')+'</p>':'<p>这个区间里没有已备案的项目。</p>')
   +(r.items.length?c.table(['项目','承办学院','状态','缺项'],r.items.map(x=>[c.act(x.name+(x.cohort?'（'+x.cohort+'）':''),'social-detail','social_project|'+x.id,'text'),e(x.org_name),e(x.state_label),x.issues.length?'<span class="report-issues">'+x.issues.map(e).join('<br>')+'</span>':'<span class="badge green-b">齐全</span>'])):'')
   +'<p class="muted small">'+e(r.note)+'</p></div>';
 }
 const foot=[c.act(r?'重新预检':'预检','social-report-check','',r?.ready?'':'primary'),...(r?.ready?[c.act('下载上报表','social-report-download','','primary')]:[]),c.act('关闭','close')].join('');
 return c.modal('导出上报表',body,foot,true);
}
function readReportRange(){
 const val=id=>typeof document==='undefined'?'':document.getElementById(id)?.value||'',year=val('report-year');
 if(year){const y=Number(year.slice(0,4));reportRange={start:y+'-09-01',end:(y+1)+'-08-31',year}}
 else reportRange={start:val('report-start')||reportRange.start,end:val('report-end')||reportRange.end,year:''};
 if(!reportRange.start||!reportRange.end)throw Error('请填写开始和结束日期');
 return 'start='+encodeURIComponent(reportRange.start)+'&end='+encodeURIComponent(reportRange.end);
}

// 培训课程申报期限（从“我的课程”申报的学历课）：学校改各学年截止日，学院在截止后为本院开放补报（最多 90 天）。
let deadlines=null;
async function deadlinesModal(){
 const c=context,e=c.esc,d=deadlines=await c.api('/applications/deadlines');
 const STATE={open:'申报中',reopened:'补报中',closed:'已截止'},tone={open:'green-b',reopened:'blue-b',closed:'gray-b'};
 const ops=x=>d.can_set?c.act('改截止日','social-deadline-edit',x.school_year,'text'):d.can_reopen?(x.state==='closed'?c.act('开放补报','social-deadline-reopen',x.school_year,'text'):x.state==='reopened'?c.act('改补报日期','social-deadline-reopen',x.school_year,'text')+c.act('关闭补报','social-deadline-close',x.school_year,'text'):''):'';
 const rows=d.items.map(x=>[e(x.school_year+' 学年'),e(x.deadline)+(x.custom?' <span class="muted small">（已调整，默认 '+e(x.default_deadline)+'）</span>':''),'<span class="badge '+tone[x.state]+'">'+STATE[x.state]+'</span>'+(x.days_left!=null?' <span class="muted small">还剩 '+x.days_left+' 天</span>':''),e(x.reopen_until||'—'),ops(x)]);
 const tip=c.note('从“我的课程”申报的课，每学年的课在学年结束后的 9 月 30 日前申报，到期前 '+d.remind_days+' 天在老师的“我的课程”和工作总览里提醒。'+(d.can_set?'学校可以调整截止日；':'')+'截止后由学院负责人为本院开放补报，最长 '+d.reopen_max_days+' 天。退回补正的申报不受截止日限制。'+(d.college?'当前学院：'+d.college+'。':''));
 return c.modal('培训课程申报期限',tip+c.table(['学年','申报截止日','状态','本院补报截止','操作'],rows),c.act('关闭','close'),true);
}

export async function socialPage(section,c){
 context=c;if(listSection!==section){listPage=1;listSearch='';resourcePage=1;listSection=section}workspace=await c.api('/social/workspace?section='+section+'&page='+listPage+'&q='+encodeURIComponent(listSearch)+'&resource_page='+resourcePage);workspaceUser=c.me?.user?.id;const {esc,act,table,note,pageHead}=c;
 // 教研室查看项目和资源，不直接登记；课程、基地仍可走本人申请流程。
 const can=p=>c.can(p)&&!(p==='records.write'&&c.me?.role?.kind==='dept'&&['projects','courses','bases','outcomes'].includes(section));
 const buttons=[];
 if(section==='annual'&&c.me?.role?.kind==='teacher')buttons.push(act('返回政策通知','nav','notices'));
 // 老师可以申报本人负责的培训项目（先到学院审批，再到学校备案）。
 if(section==='projects'&&(can('records.write')||c.me?.role?.kind==='teacher'))buttons.push(act('申报培训项目','social-project-new','','primary'));
 // 培训课程、培训基地：学校直接登记入库；老师、教研室、学院走申请（学院登记的视为学院已确认，直接到学校审批）。
 const school=c.me?.role?.kind==='school',dept=c.me?.role?.kind==='dept',college=c.me?.role?.kind==='college',applicant=['teacher','dept','college'].includes(c.me?.role?.kind);
 if(section==='courses'&&school&&can('records.write'))buttons.push(act('登记培训课程','social-course-new','','primary'),act('批量导入课程','social-course-import'),act('超星学习通导出表导入','social-course-chaoxing'));
 if(section==='courses'&&applicant)buttons.push(c.me?.role?.kind==='teacher'?act('申报培训课程','teacher-apply','course|','primary'):act('申报培训课程','app-course-new','','primary'));
 if(section==='courses'&&can('records.write'))buttons.push(act('登记课程资源','social-resource-new','course_resource'));
 if(section==='courses'&&['school','college'].includes(c.me?.role?.kind))buttons.push(act('培训课程申报期限','social-deadlines'));
 if(section==='bases'&&school&&can('records.write'))buttons.push(act('登记培训基地','social-resource-new','base','primary'));
 if(section==='bases'&&applicant)buttons.push(act('申请培训基地','app-base-new','','primary'));
 if(section==='outcomes'&&can('records.write'))buttons.push(act('登记培训成果','social-resource-new','achievement','primary'));
 if(section==='recognition'&&c.me.user.staff_no)buttons.push(act('申报本人积分','social-claim-new','','primary'));
 if(section==='recognition'&&workspace.my_duties.includes('secretary'))buttons.push(act('生成双月汇总或年度公示','social-report-new'));
 if(section==='annual'&&can('assessment.review')&&['school','college'].includes(c.me?.role?.kind))buttons.push(act('建立学院年度自评','social-annual-new','','primary'));
 if(section==='projects'&&['school','college'].includes(c.me?.role?.kind)&&c.can('export'))buttons.push(act('导出上报表','social-report-export'));
 if(['projects','recognition','annual'].includes(section)&&can('assessment.review')&&(workspace.my_duties.length||c.me.role.kind==='school'))buttons.push(act('利益冲突申报与回避','tz-conflicts'));
 if(section==='policy'&&can('rules.manage'))buttons.push(act('新建制度口径版本','social-policy-new','','primary'),act('一键生成推荐口径草稿','social-policy-recommended'));
 if(section==='policy'&&can('roles.manage')&&c.me.user.is_admin)buttons.push(act('配置审批职责','social-duties'));
 let rows=[],headers=[],description='';
 const detail=(kind,id)=>act(['teacher','dept'].includes(c.me?.role?.kind)&&['projects','courses','bases','outcomes'].includes(section)?'查看':c.me?.role?.kind==='teacher'&&section==='annual'?'查看公示':'查看与办理','social-detail',kind+'|'+id,'text');
 if(section==='projects'){description='从项目申报到备案结项，让每一次培训有据可查。';headers=['序号','项目名称 / 编号','服务面向类型','总学时','视频资源总时长（分钟）','实践教学基地数（个）','教学实施方式','办理状态','操作'];rows=workspace.projects.map((x,i)=>[String(((workspace.pagination?.page||1)-1)*(workspace.pagination?.size||20)+i+1),identity(x.data.name,x.data.code,'book'),esc((x.data.service_types||[]).map(k=>svcLabel[k]||k).join('，'))||'—',x.data.total_hours!=null&&x.data.total_hours!==''?esc(x.data.total_hours):'—',esc(x.data.video_minutes??x.video_minutes??0),x.data.base_count!=null?esc(x.data.base_count):'—',esc((x.data.teaching_methods||[]).map(k=>tmLabel[k]||k).join('，'))||'—',statusBadge(x.state_label||workspace.states[x.state],x.state)+(x.report_issues?.length&&['FILED','CLOSE_COLLEGE','CLOSE_REVIEW','CLOSED'].includes(x.state)?' <span class="badge orange-b" title="'+esc(x.report_issues.join('；'))+'">缺上报信息</span>':''),detail('social_project',x.id)])}
 if(section==='courses'){description='集中管理培训课程、视频与教学资源，清楚掌握资源数量和视频时长。';headers=['课程名称 / 编号','关联项目','学时','教学方式 / 思政属性','主讲教师 / 课件审查','资源与视频','操作'];rows=workspace.courses.map(x=>{const stats=workspace.course_stats[x.code]||{resources:0,videos:0,minutes:0},info=workspace.course_info?.[x.code]||{};return [identity(x.name,x.code,'book')+(info.one_skill?' <span class="badge green-b">一人一技</span>':'')+(info.package?' <span class="badge blue-b">培训包</span>':''),esc(x.project_code||'待关联'),info.hours!=null?esc(info.hours):pending(),courseModes(info),courseTeacher(info),resourceCell(stats),'<div class="course-actions">'+act('查看课程','social-course-view',x.code,'text')+act('查看资源','social-course-resources',x.code,'text')+'</div>']})}
 if(['bases','outcomes'].includes(section)){description=section==='bases'?'登记基地及认定依据，校外培训保留审批材料。':'按认定文件登记成果；正式计分还须完成年度考核核验。';headers=['名称','编号','认定依据','操作'];rows=workspace.resources.filter(x=>x.kind===(section==='bases'?'base':'achievement')).map(x=>[esc(x.name),esc(x.code),esc(x.data.recognition),resourceOpen(x)])}
 if(section==='recognition'){description='授课与辅助积分分别申报，按院长、归口学院、分管副校长、教学秘书职责办理。';headers=['申报人','项目','周期','状态','操作'];rows=workspace.claims.map(x=>[identity(c.teacherName(x.teacher_id),'个人积分认定','users'),esc(workspace.projects.find(p=>p.id===x.project_id)?.data.name||'关联项目'),esc(c.periodName(x.period_id)),statusBadge(x.state_label||workspace.states[x.state],x.state),detail('social_claim',x.id)]);workspace.ledger=await c.api('/social/ledger-summary')}
 if(section==='annual'){description=c.me?.role?.kind==='teacher'?'仅显示本学院已公示的评分摘要，公示期间可提出异议。':'按收入、人次、成果和资金管理分别评分；口径未确认时不发布正式结果。';headers=['学院','周期','状态','操作'];rows=workspace.annuals.map(x=>[identity(x.org_name||c.orgName(x.org_id),c.me?.role?.kind==='teacher'?'学院考核公示':'学院年度考核','school'),esc(c.periodName(x.period_id)),statusBadge(x.state_label||workspace.states[x.state],x.state),detail('social_annual',x.id)])}
 if(section==='policy'){description='学校制度已经定稿。本页登记交叉执行口径的书面解释及依据；缺失参数保持待确认，已启用版本不可直接修改。';headers=['名称','周期','状态','待确认项','操作'];rows=workspace.policies.map(x=>[identity(x.name,'制度执行口径','file'),esc(c.periodName(x.period_id)),statusBadge(x.state_label||workspace.states[x.state],x.state),Object.keys(workspace.decisions).filter(k=>x.data[k]==null).length,detail('social_policy',x.id)])}
 const resourceTable=section==='courses'&&c.me?.role?.kind!=='teacher'?'<details class="business-guide data-details mt20"'+(!dept&&!college&&workspace.resources.some(r=>r.kind==='course_resource')?' open':'')+'><summary>课程资源明细（视频、文档、链接）</summary>'+table(['资源名称','关联课程','类型','时长（分钟）','操作'],workspace.resources.filter(r=>r.kind==='course_resource').map(r=>[esc(r.name),esc(r.data.course_code),esc({video:'视频',document:'文档',link:'其他链接'}[r.data.resource_type]),r.data.duration_minutes??'不适用',detail('social_resource',r.id)]))+'</details>':'';
 const ledger=section==='recognition'&&workspace.ledger.items.some(t=>Object.keys(t.years).length)?'<section class="card mt20"><div class="card-head"><h2>个人历年积分与折算</h2></div>'+table(['教师','年度','授课积分及对应课时','辅助积分','职称社会服务分','近五年累计'],workspace.ledger.items.flatMap(t=>Object.entries(t.years).map(([year,y])=>[esc(c.teacherName(t.teacher_id)),esc(year),esc(y.teaching),esc(y.auxiliary),y.title_pending?'待学校确认':esc(y.title_score),esc(t.five_year_total)])))+'</section>'+note(workspace.ledger.note,false,'积分折算说明'):'';
 const followups=section==='recognition'&&workspace.resources.some(r=>['correction','point_report','point_review'].includes(r.kind))?'<section class="card mt20"><div class="card-head"><h2>积分核对、更正与汇总公示</h2></div>'+table(['事项','状态','操作'],workspace.resources.filter(r=>['correction','point_report','point_review'].includes(r.kind)).map(r=>[esc(r.name)+(r.kind==='point_report'?' · '+esc(r.org_name||c.orgName(r.org_id)):''),esc(r.kind==='point_review'?REVIEW_STATES[r.state]||r.state_label:r.state_label||workspace.states[r.state]),detail('social_resource',r.id)]))+'</section>':'';
 const config={
  projects:{label:'培训项目',icon:'book',steps:[['申报与备案','登记项目资料、培训安排及核算方式，提交审核备案。'],['实施与留证','导入核验后的参训明细，上传考勤、学时及结业材料。'],['结项与核算','核验有效人次与结项材料，再办理个人积分和学院统计。']]},
  courses:{label:'培训课程',icon:'book',steps:[['申请或登记课程','老师、学院申请培训课程，学院审批后由学校审批入库；学校可直接登记。填写学时、教学方式、思政属性、主讲教师和课件审查。'],['归集资源','登记视频、文档或链接，保留来源与认定依据。'],['核对时长','视频分钟数表示资源总时长，不代表学员已学习时长。']]},
  bases:{label:'培训基地',icon:'school',steps:[['申请基地','老师、学院申请培训基地，填写用途、设立日期和共建单位，学院审批后由学校审批生效；项目设立的基地随项目备案生效。'],['补充认定依据','登记学校认定文件，按需上传佐证材料。'],['保留办理记录','校外培训保留审批材料，资料与办理过程可追溯。']]},
  outcomes:{label:'培训成果',icon:'award',steps:[['登记成果','按认定文件填写成果名称与唯一编号。'],['提供佐证','保留成果认定材料，确保来源可核查。'],['年度核验','正式计分须完成年度考核中的成果核验。']]},
  recognition:{label:'积分申报',icon:'award'},annual:{label:c.me?.role?.kind==='teacher'?'学院考核公示':'学院自评',icon:'assess'},policy:{label:'执行口径',icon:'file'}
 }[section];
 const p=workspace.pagination,items=section==='recognition'?workspace.claims:section==='annual'?workspace.annuals:section==='policy'?workspace.policies:section==='courses'?workspace.courses:section==='projects'?workspace.projects:workspace.resources;
 let stats=[[listSearch?'当前检索总数':config.label+'总数',p.total,'授权范围内的记录',config.icon]];
 if(section==='bases'){const since=new Date(Date.now()-365*864e5).toLocaleDateString('sv-SE'),today=new Date().toLocaleDateString('sv-SE'),live=items.filter(x=>x.kind==='base'&&!APPLYING.includes(x.state));stats[0]=['基地总数',p.total,'授权范围内的基地，含你提交的审批中申请','school'];stats.push(['思政实践教学基地',live.filter(x=>(x.data.usages||[]).includes('ideology')).length,'本页已生效、用途含思政实践教学的基地','award'],['近一年新增',live.filter(x=>{const d=String(x.data.established_on||'');return d>since&&d<=today}).length,'本页已生效、设立日期在近 365 天内的基地','clock'])}
 else if(section==='courses')stats.push(['本页课程资源',items.reduce((sum,x)=>sum+(workspace.course_stats[x.code]?.resources||0),0),'所列课程的资源数量','file'],['本页视频资源',items.reduce((sum,x)=>sum+(workspace.course_stats[x.code]?.videos||0),0),'所列课程的视频数量','clock']);
 else if(section==='outcomes')stats.push(['本页记录',items.length,'当前分页内的记录',config.icon],['本页已填认定日期',items.filter(x=>x.data.confirmed_on).length,'已填写认定日期的成果','check']);
 else stats.push(['本页记录',items.length,'当前分页内的记录',config.icon],['本页已'+(section==='projects'?'结项':section==='policy'?'启用':'归档'),items.filter(x=>['CLOSED','ARCHIVED','ACTIVE'].includes(x.state)).length,'依照当前办理状态','check']);
 if(c.me?.role?.kind==='teacher'&&section==='courses')stats[0]=['当前可见课程',p.total,'当前账号授权范围内的课程','book'];
 const summary=p.total?'<div class="social-summary">'+stats.map(([label,value,hint,ico])=>'<article class="social-stat"><div class="social-stat-icon">'+c.icon(ico)+'</div><div><span>'+esc(label)+'</span><strong>'+esc(value)+'</strong></div></article>').join('')+'</div>':'';
 const pager=(c.me?.role?.kind==='teacher'&&p.total<=p.size||(dept||college)&&p.page===1&&p.total<=p.size)?'':'<div class="social-pager"><span>共 '+p.total+' 项 · 第 '+p.page+' 页</span>'+(p.page>1?act('上一页','social-list-page',String(p.page-1)):'')+(p.page*p.size<p.total?act('下一页','social-list-page',String(p.page+1)):'')+'</div>';
 const tools='<form id="social-search-form" class="social-tools" role="search" aria-label="检索'+config.label+'"><input id="social-query" type="search" aria-label="检索关键词" placeholder="输入关键词检索" value="'+esc(listSearch)+'" maxlength="100"><button class="btn" type="submit">'+c.icon('search')+'查询</button>'+(listSearch?act('清空检索','social-list-reset'):'')+'</form>';
 const scopeNote={teacher:{projects:'这里只显示你负责或参与授课的项目。项目由二级学院申报、学校备案；你在“个人培训”申报本人积分。',courses:'这里只显示你参与项目关联的课程，以及登记在你名下的课程资源。',bases:'这里显示所属学院的培训基地，供申报和授课时查阅。',outcomes:'这里显示所属学院已登记的培训成果。'},dept:{projects:'这里显示本教研室教师负责或参与的项目，只能查看和导出；申报、备案、结项由学院和学校办理。',courses:'这里显示本教研室项目关联的课程和学院课程资源；可查看课程资料，也可通过“申报培训课程”提交申请。',bases:'这里显示所属学院的培训基地；可查阅已有基地，也可通过“申请培训基地”提交申请。',outcomes:'这里显示所属学院的培训成果，只能查看。'}}[c.me?.role?.kind]?.[section];
 const empty='<div class="social-empty"><div class="social-empty-art">'+c.icon(listSearch?'search':config.icon)+'</div><h3>'+(listSearch?'没有找到匹配的记录':'还没有'+config.label)+'</h3><p>'+(listSearch?'换个关键词试试。':'')+'</p><div class="social-empty-action">'+(listSearch?act('查看全部','social-list-reset'):['teacher','dept','college'].includes(c.me?.role?.kind)?'':buttons[0]||'')+'</div></div>';
 let content=rows.length?table(headers,rows):empty;
 if(section==='projects'&&c.me?.role?.kind==='teacher'){
  const projectRows=workspace.projects.map(x=>[identity(x.data.name,x.data.code,'book'),esc(x.cohort||'—'),'<span class="teacher-project-dates">'+esc(x.data.start_date||'日期待确认')+'<br>'+esc(x.data.end_date||'')+'</span>',x.owner_id===c.me.user.id?'项目负责人':'参与教师','<div class="teacher-project-state">'+statusBadge(x.state_label||workspace.states[x.state],x.state)+(x.report_issues?.length&&['FILED','CLOSE_COLLEGE','CLOSE_REVIEW','CLOSED'].includes(x.state)?'<p class="cell-sub">上报资料待学院完善</p>':'')+'</div>',detail('social_project',x.id)]);
  content=projectRows.length?table(['项目名称 / 编号','期次','培训时间','我的角色','项目状态','操作'],projectRows).replace('<table class="table">','<table class="table teacher-project-table">'):empty;
 }else if(section==='projects'&&(dept||college)){
  const projectRows=workspace.projects.map(x=>[identity(x.data.name,x.data.code,'book'),esc(x.cohort||'—'),'<span class="teacher-project-dates">'+esc(x.data.start_date||'日期待确认')+'<br>'+esc(x.data.end_date||'')+'</span>',statusBadge(x.state_label||workspace.states[x.state],x.state),detail('social_project',x.id)]);
  content=projectRows.length?table(['项目名称 / 编号','期次','培训期间','当前状态',college?'办理':'查看'],projectRows).replace('<table class="table">','<table class="table dept-project-table">'):empty;
 }else if(section==='projects')content=content.replace('<table class="table">','<table class="table projects-table">');
 if(section==='bases'&&items.length)content='<div class="social-resource-grid">'+items.map(x=>'<article class="social-resource-card"><div class="social-resource-top"><div class="social-resource-icon">'+c.icon(x.data.onsite===true?'school':'map')+'</div><span class="social-badge" data-tone="'+(x.data.onsite===true?'blue':'slate')+'">'+(x.data.onsite===true?'校内基地':x.data.onsite===false?'校外基地':'类型待补充')+({city:' · 市级',province:' · 省级及以上'}[x.data.level]||'')+'</span></div><h3>'+esc(x.name)+'</h3><p class="social-code">'+esc(x.code)+'</p><div class="social-resource-meta"><div class="social-meta-line">'+c.icon('org')+'<span>'+esc(x.org_name||c.orgName(x.org_id))+'</span></div><div class="social-meta-line">'+c.icon('map')+'<span>'+esc(x.data.location||'地点待补充')+'</span></div><div class="social-meta-line">'+c.icon('award')+'<span>用途：'+esc((x.data.usages||[]).map(k=>BASE_USAGE[k]||k).join('、')||'待补充')+'</span></div><div class="social-meta-line">'+c.icon('clock')+'<span>设立日期：'+esc(x.data.established_on||'待补充')+'</span></div>'+(x.data.onsite===false||x.data.partner?'<div class="social-meta-line">'+c.icon('users')+'<span>共建单位：'+esc(x.data.partner||'待补充')+'</span></div>':'')+'</div><div class="social-resource-evidence">认定依据：'+esc(x.data.recognition||'待补充')+'</div><div class="social-resource-foot">'+statusBadge(x.state_label||workspace.states[x.state],x.state)+resourceOpen(x)+'</div></article>').join('')+'</div>';
 const guide=config.steps?'<details class="social-guide business-guide" aria-label="'+config.label+'办理指引"><summary>'+config.label+'办理指引</summary><ol>'+config.steps.map(([title,copy])=>'<li><strong>'+title+'</strong><span>'+copy+'</span></li>').join('')+'</ol><div class="social-guide-note">材料完整性与正式认定，以学校审核结论为准。</div></details>':'';
 if(['teacher','dept','college'].includes(c.me?.role?.kind)&&section==='courses')content=rows.length?table(dept||college?['课程名称','关联项目名称','学时','资源摘要','查看资源']:['课程名称','关联项目','学时','资源摘要','操作'],workspace.courses.map(x=>[act(x.name,'social-course-view',x.code,'text'),esc(workspace.projects.find(p=>p.data.code===x.project_code)?.data.name||(x.project_code?'项目名称待核对':'未关联项目')),workspace.course_info?.[x.code]?.hours??'待完善',resourceCell(workspace.course_stats[x.code]||{resources:0,videos:0,minutes:0}),act('查看资源','social-course-resources',x.code,'text')])):empty;
 if(['teacher','dept','college'].includes(c.me?.role?.kind)&&section==='outcomes')content=rows.length?table(['成果名称','归属范围','认定级别','认定日期',dept||college?'查看':'操作'],items.filter(x=>x.kind==='achievement').map(x=>[esc(x.name),(dept||college)&&x.data.teacher_id?esc(c.teachers?.find(t=>t.id===x.data.teacher_id)?.name||'教师姓名待核对')+' · 教师贡献':esc(x.org_name||c.orgName(x.org_id))+' · 学院参考',esc(names[x.data.level]||'待确认'),esc(x.data.confirmed_on||'待补充'),resourceOpen(x)])):empty;
 if(c.me?.role?.kind==='teacher'&&section==='recognition')content=rows.length?table(['项目 / 周期','当前节点','下一步','操作'],workspace.claims.map(x=>[identity(workspace.projects.find(p=>p.id===x.project_id)?.data.name||'关联项目',c.periodName(x.period_id),'book'),statusBadge(x.state_label||workspace.states[x.state],x.state),esc({DRAFT:'核对材料及提交条件',RETURNED:'查看退回意见与待补内容',SUBMITTED:'等待院长初审',DEAN:'等待归口复审',COORDINATOR:'等待分管副校长审批',APPROVED:'等待教学秘书归档',ARCHIVED:'已归档，可查看认定依据'}[x.state]||'查看详情'),detail('social_claim',x.id)])):empty;
 const main='<div class="social-main"><section class="card social-panel"><div class="social-panel-head"><div><h2>'+config.label+'清单</h2></div></div>'+(['teacher','dept','college'].includes(c.me?.role?.kind)&&!p.total&&!listSearch?'':tools)+content+pager+'</section>'+resourceTable+ledger+followups+((['courses','recognition'].includes(section)&&workspace.resource_pagination.total>200)?'<p>资源与更正汇总第'+resourcePage+'页 '+(resourcePage>1?act('前一页明细','social-resource-page',String(resourcePage-1)):'')+(resourcePage*200<workspace.resource_pagination.total?act('后一页明细','social-resource-page',String(resourcePage+1)):'')+'</p>':'')+'</div>';
 // 图文工作台按学校管理端原型设计，只给学校身份；教师、教研室、学院保留各自已优化的清单。
 if(school&&['projects','courses','bases','outcomes'].includes(section)){
  const resourceAction=section==='courses'?buttons.find(b=>b.includes('data-id="course_resource"')):null,ordered=resourceAction?[buttons[0],resourceAction,...buttons.filter(b=>b!==buttons[0]&&b!==resourceAction)]:buttons;
  const actions=ordered.slice(0,2).join('')+(ordered.length>2?'<details class="tw-more"><summary>更多操作</summary><div>'+ordered.slice(2).join('')+'</div></details>':'');
  const supplementary='<details class="tw-supplement"><summary>完整清单与统计口径</summary>'+((c.me?.role?.kind==='teacher'&&['projects','outcomes'].includes(section))?'':summary)+content+resourceTable+(scopeNote?note(scopeNote,false,'查看范围'):'')+note('统计仅包含当前账号有权查看的记录；“本页”数量随分页与检索变化。',false,'统计口径')+'</details>';
  return renderTrainingWorkspace(section,workspace,c,{actions,serverSearch:listSearch,socialPager:pager,after:supplementary});
 }
 return '<div class="social-workspace">'+pageHead(description,buttons.join(''))+(c.me?.role?.kind==='teacher'?(['projects','outcomes'].includes(section)?'':section==='recognition'?'<p class="teacher-list-summary">本页 '+items.filter(x=>x.state==='RETURNED').length+' 项退回待补 · '+items.filter(x=>['SUBMITTED','DEAN','COORDINATOR','APPROVED'].includes(x.state)).length+' 项审核中 · '+items.filter(x=>x.state==='ARCHIVED').length+' 项已归档'+(items.some(x=>x.state==='DRAFT')?' · '+items.filter(x=>x.state==='DRAFT').length+' 项草稿':'')+'</p>':summary):summary)+main+'<div class="page-guides">'+guide+(scopeNote?note(scopeNote,false,'查看范围'):'')+note('统计仅包含当前账号有权查看的记录；“本页”数量随分页与检索变化。'+stats.map(([label,,hint])=>label+'：'+hint).join('；')+'。未完成审核的记录及候选试算不代表学校正式认定。',false,'统计与认定说明')+'</div></div>';
}

export function claimBlockersHtml(blockers,esc){
 if(!blockers.length)return '';
 const personal=blockers.filter(x=>x==='学校制式积分认定表及其附件对应说明尚未提供'||x==='管理岗位与辅助工作积分不能重复申报'||x==='辅助工作日期超出项目期间'||x==='辅助积分超过个人每日限额');
 const external=blockers.filter(x=>!personal.includes(x));
 return '<section class="claim-blockers" aria-label="积分提交条件"><h3>当前暂不能提交</h3><p>先看哪些需要本人补充；其余条件由学校或项目负责人核实。</p>'+[[external,'待学校或项目负责人确认'],[personal,'待本人补充或核对']].filter(([items])=>items.length).map(([items,label])=>'<details'+(personal===items?' open':'')+'><summary>'+label+' · '+items.length+' 项</summary><ul>'+items.map(x=>'<li>'+esc(x)+'</li>').join('')+'</ul></details>').join('')+'</section>';
}
function detailFacts(title,rows){return '<section class="social-detail-section"><h3>'+context.esc(title)+'</h3><dl class="detail-facts">'+rows.map(([label,value])=>'<div><dt>'+context.esc(label)+'</dt><dd>'+value+'</dd></div>').join('')+'</dl></section>'}
function formSection(title,body,description=''){return '<fieldset class="social-fieldset"><legend>'+context.esc(title)+'</legend>'+(description?'<p class="social-fieldset-note">'+context.esc(description)+'</p>':'')+'<div class="social-form-fields">'+body+'</div></fieldset>'}
function detailArea(kind,item){return kind==='social_resource'?({base:'培训基地',achievement:'培训成果',course_resource:'课程资源',correction:'积分更正',point_review:'积分核对',point_report:'积分汇总公示'}[item?.kind]||'社会培训业务'):({social_project:'培训项目',social_claim:'积分认定',social_annual:'学院年度考核',social_policy:'制度执行口径'}[kind]||'社会培训业务')}
function commonForm(title,body,save,options={}){const c=context,manager=['dept','college'].includes(c.me?.role?.kind),subject=options.reopen&&!options.page&&['teacher','dept','college','school'].includes(c.me?.role?.kind)?'<div class="detail-action-context"><span>本次办理对象</span><strong>'+c.esc(opened?.item?.kind==='point_report'?(opened.org_name||c.orgName(opened.item.org_id))+' · '+opened.item.name:opened?.item?.data?.name||opened?.item?.name||(opened?.kind==='social_annual'?(opened.org_name||c.orgName(opened.item.org_id))+' · '+c.periodName(opened.item.period_id):opened?.kind==='social_claim'?c.teacherName(opened.item.teacher_id)+' · '+(opened?.trial?.basis?.facts?.project?.data?.name||opened?.trial?.basis?.facts?.project?.name||'个人积分认定'):'当前业务'))+'</strong><p>'+c.esc(opened?.state_label||'')+'</p></div>':'';c.formModal(title,'<div class="social-form">'+subject+(body.includes('class="social-fieldset"')?body:formSection('办理内容',body))+formSection('办理说明',(options.hideReason?'':c.field('reason',options.reasonLabel||'办理说明','textarea',options.reasonDefault??title,{rows:2,full:true,hint:''}))+c.field('basis',options.basisLabel||'依据说明或材料编号（选填）','textarea','',{rows:2,required:!!options.basisRequired,full:true,placeholder:options.basisPlaceholder||'例：学院会议纪要〔2026〕3号、协议编号、材料编号'}),options.compact?'':'')+'</div>',async(v,f,button)=>{const back=options.reopen&&opened?{kind:opened.kind,id:opened.id,courseList:opened.courseList}:null,result=await save(v,f,button);c.closeModal();await c.render();if(options.after)await options.after(result);else if(back)await showDetail(back.kind,back.id,back.courseList).catch(()=>{})},{wide:true,stepper:true,contextLabel:c.me?.role?.kind==='teacher'?'个人培训 / '+title:manager?(options.reopen&&opened?detailArea(opened.kind,opened.item):c.me?.role?.kind==='college'?'学院业务':'教研室业务')+' / '+title:'',...options});
 if(typeof document!=='undefined'){const period=document.getElementById('f-period_id'),policy=document.getElementById('f-policy_id');if(period&&policy){const choices=[...policy.options].map(o=>({value:o.value,label:o.textContent})),sync=()=>{const selected=policy.value,matching=choices.filter(o=>workspace.policies.some(p=>p.id===o.value&&p.period_id===period.value));policy.innerHTML='<option value="">'+(matching.length?'请选择制度口径':'该周期暂无制度口径')+'</option>'+matching.map(o=>'<option value="'+c.esc(o.value)+'">'+c.esc(o.label)+'</option>').join('');policy.value=matching.some(o=>o.value===selected)?selected:matching.length===1?matching[0].value:''};period.addEventListener('change',sync);sync()}}
 if(options.reopen&&opened&&typeof document!=='undefined'){const back={kind:opened.kind,id:opened.id,courseList:opened.courseList};document.querySelectorAll('#modal-root button[data-action="close"]').forEach(b=>{if(!b.textContent.trim())return;b.textContent='返回详情';b.addEventListener('click',e=>{e.preventDefault();e.stopImmediatePropagation();showDetail(back.kind,back.id,back.courseList).catch(err=>{context.closeModal();context.toast?.(err.message,true)})},true)})}
}
function projectOptionsHtml(result,selected){
 const c=context,key=projectChoice.key,options=result.items.map(p=>[p[key],p.name+' · '+p.code+' · '+p.cohort]);
 if(selected?.value&&!options.some(([value])=>value===selected.value))options.unshift([selected.value,selected.label]);
 const empty=projectChoice.mine&&!result.total&&!result.q?context.note('还没有可申报的项目：项目须已正常结项，且“参训明细”里登记了你的工号（授课或辅助）。项目还在办理中的，等学院结项后再来申报；如有遗漏，请联系学院补录参训明细。',true):'';
 return empty+'<div class="form-field full"><label for="social-project-query">检索关联项目</label><div class="social-picker-tools"><input id="social-project-query" type="search" maxlength="100" placeholder="输入项目名称、编号或期次" value="'+c.esc(result.q)+'">'+c.act('查找项目','social-project-lookup','1')+'</div></div>'+c.field(projectChoice.name,'选择关联项目','select',selected?.value||'',{full:true,required:!projectChoice.optional,options:[['',projectChoice.optional?'不关联项目':'请选择一个项目'],...options],hint:projectChoice.optional?'可不关联项目；选择后自动使用该项目编号，无需手填。':''})+'<div class="social-picker-pager"><span>共 '+result.total+' 项 · 第 '+result.page+' 页</span>'+(result.page>1?c.act('上一页项目','social-project-lookup',String(result.page-1)):'')+(result.page*result.size<result.total?c.act('下一页项目','social-project-lookup',String(result.page+1)):'')+'</div>';
}
async function projectPicker(name,key,mine=false,optional=false,value=''){projectChoice={name,key,q:'',sequence:0,mine,optional};const result=await context.api('/social/project-options'+(mine?'?mine=true':''));projectChoice.total=result.total;return '<div id="social-project-picker" class="social-project-picker">'+projectOptionsHtml(result,value?{value,label:'原关联项目：'+value}:null)+'</div>'}
export async function applicationProjectPicker(ctx,value=''){context=ctx;return projectPicker('project_code','code',false,true,value)}
function collegeField(value=''){const c=context,choices=c.orgs.filter(x=>x.kind==='college');return c.field('org_id','承办学院','select',value||(choices.length===1?choices[0].id:''),{chips:choices.length<=6,options:[['','请选择承办学院'],...choices.map(x=>[x.id,x.name])]})}
async function bindCourseResourceFields(c,old){
 if(typeof document==='undefined')return;
 const form=document.getElementById('edit-form'),org=document.getElementById('f-org_id'),course=document.getElementById('f-course_code'),teacher=document.getElementById('f-teacher_id'),status=document.getElementById('course-resource-status');
 if(!form||!org||!course||!teacher||!status)return;
 const user=c.currentUser?.(),page=c.currentPage?.(),orgValue=()=>org.querySelector('input:checked')?.value||org.value||'',options=(rows,value)=>rows.map(([key,label])=>'<option value="'+c.esc(key)+'"'+(key===value?' selected':'')+'>'+c.esc(label)+'</option>').join('');
 let sequence=0;
 const sync=async(keep=false)=>{
  const current=++sequence,orgId=orgValue(),originalCourse=keep?old.course_code||'':'',originalTeacher=keep?old.teacher_id||'':'';
  const live=()=>current===sequence&&form.isConnected&&document.getElementById('edit-form')===form&&orgValue()===orgId&&(!c.currentUser||c.currentUser()===user)&&(!c.currentPage||c.currentPage()===page);
  course.innerHTML=options([['',orgId?'正在读取课程…':'请先选择承办学院'],...(originalCourse?[[originalCourse,'原关联课程 · '+originalCourse]]:[])],originalCourse);course.value=originalCourse;
  const orgIds=new Set(orgId?[orgId]:[]),pending=[...orgIds];
  while(pending.length){const parent=pending.pop();for(const o of c.orgs)if(o.active!==false&&o.parent_id===parent&&!orgIds.has(o.id)){orgIds.add(o.id);pending.push(o.id)}}
  const people=(c.teachers||[]).filter(t=>t.active!==false&&!t.authorization_pending&&t.staff_no&&orgIds.has(t.org_id)).map(t=>[t.id,t.name+' · '+t.staff_no]);
  if(originalTeacher&&!people.some(([id])=>id===originalTeacher))people.unshift([originalTeacher,'原关联教师（保留）']);
  teacher.innerHTML=options([['','尚未确认人员'],...people],originalTeacher);teacher.value=originalTeacher;
  status.textContent=orgId?'正在读取所选学院项目关联的有效课程。':'请先选择承办学院，再选择关联课程和归属教师。';
  if(!orgId)return;
  try{
   const courses=[];
   for(let page=1;;page++){
    const result=await c.api('/reference/courses?'+new URLSearchParams({resource_org_id:orgId,active:'true',page:String(page),size:'200'}));
    if(!live())return;
    courses.push(...result.items);
    if(courses.length>=result.total)break;
    if(!result.items.length)throw Error('课程候选读取不完整，请重新选择学院或刷新后重试。');
   }
   const selected=course.value,rows=[['','请选择关联课程'],...courses.map(x=>[x.code,x.name+' · '+x.code])];
   if(originalCourse&&!courses.some(x=>x.code===originalCourse))rows.push([originalCourse,'原关联课程 · '+originalCourse]);
   course.innerHTML=options(rows,selected);course.value=rows.some(([code])=>code===selected)?selected:'';
   status.textContent=courses.length?'已读取 '+courses.length+' 门有效课程；保存时会重新校验课程和人员归属。':'所选学院暂无项目关联的有效课程；请先完成项目课程登记。';
  }catch(err){if(live()){course.innerHTML=options([['','课程读取失败，请重新选择学院'],...(originalCourse?[[originalCourse,'原关联课程 · '+originalCourse]]:[])],originalCourse);course.value=originalCourse;status.textContent='课程候选暂未读取成功，请重新选择学院或刷新后重试；原关联资料保留。'}}
 };
 org.addEventListener('change',()=>sync());return sync(true);
}
// 默认选今天所在的开放周期，没有则留空让人选，避免跳到未来年度（如 2027）
function currentOpenPeriod(periods){const today=new Date(Date.now()+28800000).toISOString().slice(0,10);const hits=periods.filter(x=>x.state==='OPEN'&&x.start_date&&x.end_date&&x.start_date<=today&&today<=x.end_date);return hits.length===1?hits[0].id:''}
function fieldSummary(name,label,value,text){return '<div class="form-field"><label>'+context.esc(label)+'</label><p class="field-summary">'+context.esc(text)+'</p><input type="hidden" name="'+name+'" value="'+context.esc(value)+'"></div>'}
// 周期、口径唯一确定时只显示摘要；有多个可选才让人选，不替人猜。
function policyFields(x,changePeriod=false){const c=context,open=c.periods.filter(p=>p.state==='OPEN');if(!open.length)throw Error('当前没有开放的考核周期，请联系学校管理员确认后再办理');const today=currentOpenPeriod(c.periods),fixed=x?.period_id&&!changePeriod?c.periods.find(p=>p.id===x.period_id):!changePeriod&&open.length===1&&today?open[0]:null,periodHint=!fixed&&!x?.period_id&&!today?c.note('当前适用周期不能唯一确定，请根据业务归属明确选择认定周期；不要默认选未来年度。',true):'',list=workspace.policies.filter(p=>p.state!=='VOID'||p.id===x?.policy_id),matching=fixed?list.filter(p=>!p.period_id||p.period_id===fixed.id):list,policyLabel=p=>p.name+' · '+(p.state_label||workspace.states[p.state]);
 const period=fixed?fieldSummary('period_id','认定周期',fixed.id,fixed.name||c.periodName(fixed.id)):c.field('period_id','认定周期','select',x?.period_id||today,{options:[['','请选择认定周期'],...open.map(x=>[x.id,x.name])]});
 const policy=fixed&&matching.length===1?fieldSummary('policy_id','制度执行口径',matching[0].id,policyLabel(matching[0])):c.field('policy_id','制度执行口径','select',x?.policy_id||'',{options:(fixed?matching:list).map(x=>[x.id,policyLabel(x)])});
 return periodHint+period+policy}
const cleanReason=v=>{const{reason,basis,...data}=v;return{reason,basis,data}};
const routeOf=(kind,item)=>kind==='social_resource'?({correction:'corrections',point_review:'point-reviews'}[item.kind]||'reports'):{social_project:'projects',social_claim:'claims',social_annual:'annuals',social_policy:'policies'}[kind];
async function latestOf(kind,id){const d=await context.api(path(kind,id));return {version:d.item.version,attachments:d.attachments||[],detail:d}}
// 提交被拦时只说“已保存、未提交”及原因；退回补正期限口径未确认是常见情形，给出明确去向。
function notSubmitted(saved,err){const msg=String(err?.message||'提交没有完成').split(/\r?\n/)[0];return saved+'，但尚未提交：'+(/退回补正的期限口径/.test(msg)?'学校尚未确认退回补正的期限口径，暂不能重新提交，请联系学校社会培训管理员确认后再提交':msg)}

// 审核办理区：固定显示当前环节、申报人、项目、积分、异常和材料入口；常规意见预填，仍须本人点击确认。
function handlePanel(kind,x,d){
 const c=context,esc=c.esc,claim=kind==='social_claim',t=d.trial||{},r=d.review_context||{},label=opened.labels.approve||'审核通过',archive=claim?x.state==='APPROVED':x.state==='APPROVED',files=(d.attachments||[]).length,next=c.queueNext?.(kind+'|'+x.id);
 const project=claim?(t.basis?.facts?.project?.data?.name||t.basis?.facts?.project?.name||workspace.projects?.find(p=>p.id===x.project_id)?.data?.name||''):r.project;
 const owner=claim?c.teacherName(x.teacher_id):(r.teacher_name||c.teacherName(x.data?.teacher_id));
 const points=claim?'授课 '+(t.teaching??'—')+'，辅助 '+(t.auxiliary??'—')+'，合计 '+(t.total??'待确认'):'授课 '+(x.data?.teaching??0)+'，辅助 '+(x.data?.auxiliary??0)+'（追加差额）';
 const facts=[['当前环节',esc(d.state_label)],[claim?'申报人':'被更正教师',esc(owner||'—')],['项目',esc(project||'—')],[claim?'候选积分':'更正积分',esc(points)],['佐证材料',files+' 份 '+c.act('查看材料','social-materials','','text')]];
 const warn=[...(t.blockers||[]).map(v=>c.note('系统检查发现：'+v+'。通过会被拦下，请先退回补正。',true)),...(!files?[c.note('当前没有佐证材料，请核实材料来源；材料不全的请退回补正。',true)]:[])].join('');
 return {summary:'<section class="approval-object-summary" aria-label="当前审批对象"><dl class="detail-facts">'+facts.map(([k,v])=>'<div><dt>'+esc(k)+'</dt><dd>'+v+'</dd></div>').join('')+'</dl><button type="button" class="btn text" data-detail-section="approval-opinion">填写办理意见</button></section>',
  form:'<section id="approval-opinion" class="social-detail-section social-handle" aria-label="本环节办理"><h3>本环节办理</h3>'+warn
  +'<div class="form-field full"><label for="handle-reason">办理意见（须本人点击确认才会办理）</label><textarea id="handle-reason" rows="2" maxlength="2000">'+esc(archive?'审核材料齐全，归档入账':'核对无误，审核通过')+'</textarea></div>'
  +'<div class="form-field full"><label for="handle-basis">依据说明或材料编号（选填）</label><textarea id="handle-basis" rows="2" maxlength="2000"></textarea></div><div id="handle-error" role="alert" tabindex="-1"></div>'
  +'<p class="hint">退回须具体说明补什么材料；“查看下一条”仅打开下一条，不会自动审批。</p></section>'};
}
const domValue=id=>typeof document!=='undefined'?(document.getElementById(id)?.value||'').trim():'';

async function showDetail(kind,id,courseList=null){
 const c=context,d=await c.api(path(kind,id)),x=d.item,dept=c.me?.role?.kind==='dept',manager=['dept','college','school'].includes(c.me?.role?.kind),sectioned=['teacher','dept','college','school'].includes(c.me?.role?.kind)&&!d.public_summary;opened={kind,id,...d,courseList};
 if(d.readonly){
  const data=x.data,e=c.esc,scope=dept?'本教研室':c.me?.role?.kind==='college'?'本学院':'本人';
  const body='<div class="social-detail">'+c.note(d.readonly_reason||'仅显示本人参与摘要')+c.table(['项目资料','内容'],[['项目',e(data.name)],['期次',e(x.cohort)],['办理状态',e(d.state_label)],['培训期间',e(data.start_date+' 至 '+data.end_date)],['核算方式',e(names[data.mode])]])+c.table([scope+'核算单元','日期','模块',scope+'教师及岗位'],(d.facts?.units||[]).map((u,i)=>[e(u.data.module||'第'+(i+1)+'核算单元')+'<details class="implementation-details"><summary>实施人员使用：单元编号</summary>'+e(u.external_key)+'</details>',e(u.data.event_date),e(u.data.module),(u.data.teachers||[]).map(t=>e(c.teacherName(t.teacher_id)+' · '+({lecturer:'主讲',instructor:'实训指导',manager:'管理辅助'}[t.role]||'待确认'))).join('、')]))+'</div>';
  opened.printBody=body;
  const exports=c.can('export')?c.act('导出'+scope+'参与摘要','social-export',kind+'|'+id)+c.act('打印'+scope+'参与摘要','social-print'):'';
  return c.modal(data.name||scope+'培训参与摘要',body,manager?(exports?'<details class="detail-more-actions"><summary>更多操作</summary><div>'+exports+'</div></details>':'')+c.act('关闭详情','close'):exports,true,manager?'培训项目 / '+scope+'参与摘要':'');
 }
 const {esc,act,table,note}=c,exportActions=c.can('export')?act('导出办理材料','social-export',kind+'|'+id)+act('打印当前材料','social-print'):'',moreActions=manager&&exportActions?[exportActions]:[],buttons=[...(courseList?[act('返回课程资源','social-course-resources',courseList)]:[]),...(exportActions&&!manager?[c.me.role.kind==='teacher'?'<details class="detail-more-actions"><summary>更多操作</summary><div>'+exportActions+'</div></details>':exportActions]:[])];
 if(d.view_only){
  let body='<div class="social-detail">'+note(d.view_only_reason)+'<div class="social-detail-status"><strong>当前办理状态</strong>'+statusBadge(d.state_label,x.state)+'</div>'+(manager?'<nav class="detail-section-nav" aria-label="业务详情分区"><button type="button" data-detail-section="social-info">业务资料</button><button type="button" data-detail-section="social-materials">佐证材料</button><button type="button" data-detail-section="social-history">办理记录</button></nav><div id="social-info" class="detail-section">':'');
  const data=x.data;
  if(kind==='social_project')body+=detailFacts('项目资料',[['名称',esc(data.name)],['期次',esc(x.cohort)],['承办学院',esc(d.org_name||c.orgName(x.org_id))],['负责人',esc(c.teacherName(x.owner_id))],['培训期间',esc(data.start_date+' 至 '+data.end_date)],['核算方式',esc(names[data.mode])],['备案登记日期',esc(data.filed_on||'未备案')],['预期成果',esc(data.expected_outcomes||'')]])+table(['单元编号','培训日期','课程编号','参训记录数'],(d.facts?.units||[]).map(u=>[esc(u.external_key),esc(u.data.event_date),esc(u.data.course_code),u.data.learners.length]));
  else body+='<dl class="kv">'+[['名称',x.name],['来源编号',x.code],...(x.kind==='achievement'?[['成果等级',names[data.level]||'待确认'],['认定日期',data.confirmed_on||'待补充']]:[]),['认定依据',data.recognition],['地点或说明',data.location||'待补充']].map(([k,v])=>'<dt>'+esc(k)+'</dt><dd>'+esc(v||'')+'</dd>').join('')+'</dl>';
  body+=(manager?'</div>':'')+'<section class="social-detail-section" id="social-materials"><h3>佐证材料</h3>'+c.downloads(d.attachments)+'</section><details id="social-history" class="detail-fold mt20"><summary>办理记录</summary>'+c.eventsHtml(d.events)+'</details></div>';
  if(manager){if(moreActions.length)buttons.unshift('<details class="detail-more-actions"><summary>更多操作</summary><div>'+moreActions.join('')+'</div></details>');buttons.push(act('关闭详情','close'))}opened.printBody=body;return c.modal(data.name||x.name||'社会培训办理',body,buttons.join(''),true,manager?detailArea(kind,x)+' / 业务详情':'');
 }
 if(kind==='social_resource'&&['base','achievement','course_resource'].includes(x.kind)&&!x.data.auto&&!x.data.application&&c.can('records.write')&&['school','college'].includes(c.me?.role?.kind))buttons.push(act('修改资料','social-resource-edit','','primary'));
 const ownTeacher=kind==='social_project'&&c.me?.role?.kind==='teacher'&&x.owner_id===c.me?.user?.id;
 const me=c.me?.user?.id,uploadable=kind==='social_claim'?x.teacher_id===me&&['DRAFT','RETURNED'].includes(x.state):kind==='social_resource'&&x.kind==='correction'?x.data?.created_by===me&&['DRAFT','RETURNED'].includes(x.state):kind==='social_resource'&&x.kind==='point_review'?(x.data?.created_by===me&&x.state==='DRAFT')||(x.data?.teacher_id===me&&x.state==='TEACHER'):(kind==='social_policy'?c.can('rules.manage'):c.can('records.write')||ownTeacher);
 if(!d.public_summary&&!['ARCHIVED','ACTIVE','CLOSED','VOID'].includes(x.state)&&c.can('file.write')&&uploadable)buttons.push(act('上传佐证','social-upload','',(d.attachments||[]).length?'':'light','file'));
 opened.labels={};opened.archiveStep=false;opened.inlineApprove=false;const owner=kind==='social_claim'?x.teacher_id:kind==='social_policy'?x.created_by:kind==='social_resource'?(x.data?.teacher_id||x.data?.created_by):x.owner_id,selfOwned=(owner&&owner===c.me?.user?.id)||(kind==='social_resource'&&x.kind==='correction'&&x.data?.created_by&&x.data.created_by===c.me?.user?.id),reviewActions=['file','close','approve','activate','publish','archive','resolve','finance','academic','discipline','coordinator','return'];let avoided=false;
 const add=(label,action)=>{if(selfOwned&&reviewActions.includes(action)&&!(x.kind==='point_report'&&action==='archive')){avoided=true;return}opened.labels[action]=label;if(action==='approve'&&(kind==='social_claim'||(kind==='social_resource'&&x.kind==='correction'))){opened.inlineApprove=true;return}(manager&&action==='refile'?moreActions:buttons).push(act(label,'social-transition',action,action==='return'?'danger':['submit','approve','file','close','activate','publish','archive'].includes(action)?'primary':''))};
 // 学院这一级：老师、教研室提交的项目先由学院审批，结项先由学院核验（后端 college_handle 已判断回避和代办）。
 if(kind==='social_project'&&d.college_handle){add(x.state==='COLLEGE'?'学院审批通过':'学院结项核验通过','approve');add('退回补正','college_return')}
 if(kind==='social_project'&&x.state!=='CLOSED'&&((c.me?.role?.kind==='teacher'&&x.owner_id===c.me.user.id)||(c.can('records.write')&&['college','school'].includes(c.me?.role?.kind))))(manager?moreActions:buttons).push(act('更新开班准备','social-prep'));
 if(kind==='social_project'&&c.can('records.write')&&['college','school'].includes(c.me?.role?.kind)&&['FILED','CLOSE_COLLEGE','CLOSE_REVIEW','CLOSED'].includes(x.state))(manager?moreActions:buttons).push(act(d.report_issues?.length?'补填上报信息':'修改上报信息','social-report-info','',d.report_issues?.length?'primary':''));
 if(kind==='social_project'&&(c.can('records.write')||ownTeacher)){
  if(['DRAFT','RETURNED'].includes(x.state)){const resume=x.state==='RETURNED'?{college:'补正后提交学院审批',school:'补正后提交学校备案'}[x.data.returned_level]:'';add(resume||(c.me?.role?.kind==='teacher'||c.me?.role?.kind==='dept'?'提交学院审批':'提交审核备案'),'submit');buttons.push(act('修改项目资料','social-project-edit'))}
  if(x.state==='SUBMITTED'&&workspace.my_duties.includes('coordinator')){add('完成审核备案','file');add('退回补正','return')}
  if(x.state==='FILED'){if(c.can('records.write')){buttons.push(c.me?.role?.kind==='school'?act('关联已入库课程','social-course-link')+act('登记本项目课程','social-course-for-project'):act('申请本项目课程','app-course-new',x.data.code));buttons.push(act('导入参训明细','social-unit-import'))}buttons.push(act('提交结项','social-close'));add('申请重新备案','refile')}
  if(x.state==='CLOSE_REVIEW'&&workspace.my_duties.includes('coordinator')){add('核验通过结项','close');add('退回补充材料','return')}
 }
 if(kind==='social_project'&&c.can('assessment.review')&&workspace.my_duties.some(v=>['coordinator','discipline','finance'].includes(v)))buttons.push(act('登记投诉与跟踪','social-note'));
 if(kind==='social_claim'){
  if(x.state==='ARCHIVED'&&(x.teacher_id===c.me.user.id||workspace.my_duties.includes('secretary'))){if(d.busy_reason)opened.busyNote=d.busy_reason+'。';else buttons.push(act('申请追加更正','social-correction-new'))}
  if(x.state==='ARCHIVED'&&x.teacher_id!==c.me.user.id&&['dept','college'].includes(c.me?.role?.kind)){if(d.busy_reason)opened.busyNote=d.busy_reason+'。如还发现积分有误，请在那件办结后再发起核对。';else buttons.push(act('发现积分有误，发起核对','social-review-new','','light','help'))}
  if(x.teacher_id===c.me.user.id&&['DRAFT','RETURNED'].includes(x.state)){if(d.trial?.blockers?.length)buttons.push('<button type="button" class="btn primary" disabled title="请先处理上方列出的提交条件">暂不能提交积分申报</button>');else add('提交本人积分申报','submit');buttons.push(act('补正及辅助积分','social-claim-edit'))}
  const duty={SUBMITTED:'dean',DEAN:'coordinator',COORDINATOR:'vice_president',APPROVED:'secretary'}[x.state];
  if(workspace.my_duties.includes(duty)){add(x.state==='APPROVED'?'归档并计入个人台账':'审核通过','approve');if(x.state==='APPROVED')opened.archiveStep=true;add('退回补正','return')}
 }
 if(kind==='social_resource'&&x.kind==='point_review'){
  if(x.data.correction_id)buttons.push(act('查看更正单','social-detail','social_resource|'+x.data.correction_id,'primary'));
  const me=c.me.user.id,dd=x.data;
  if(dd.created_by===me&&x.state==='DRAFT'){if(d.workflow_blockers?.length)opened.busyNote=d.workflow_blockers.join('；');else add('发给教师回应','send')}
  if(dd.created_by===me&&['DRAFT','TEACHER'].includes(x.state))add('撤回核对','withdraw');
  if(dd.teacher_id===me&&x.state==='TEACHER'){add('同意更正','agree');add('不同意，说明情况','explain')}
  if(x.state==='COLLEGE'&&workspace.my_duties.includes('dean')&&dd.created_by!==me){add('裁定更正','uphold');add('维持原认定','dismiss')}
 }
 if(kind==='social_resource'&&x.kind==='correction'){
  buttons.push(act('查看原认定','social-detail','social_claim|'+x.data.claim_id));
  if(x.data.created_by===c.me.user.id&&!['ARCHIVED','VOID'].includes(x.state))add('作废未入账更正','void');
  if(x.state==='VOID')buttons.push(act('返回原认定，重新核对','social-detail','social_claim|'+x.data.claim_id));
  if(x.data.created_by===c.me.user.id&&['DRAFT','RETURNED'].includes(x.state)){add('提交更正审核','submit');if(!x.data.review_id)buttons.push(act('补正更正内容','social-correction-edit'))}
  const duty={SUBMITTED:'dean',DEAN:'coordinator',COORDINATOR:'vice_president',APPROVED:'secretary'}[x.state];if(workspace.my_duties.includes(duty)){add(x.state==='APPROVED'?'归档追加更正差额':'审核通过','approve');add('退回补正','return')}
 }
 if(kind==='social_resource'&&x.kind==='point_report'){
  if(x.state==='VOID'&&x.data.superseded_by)buttons.push(act('查看后续公示','social-detail','social_resource|'+x.data.superseded_by,'primary'));
  if(['DRAFT','SUBMITTED'].includes(x.state)&&x.data.created_by===me&&workspace.my_duties.includes('secretary')&&c.can('assessment.review'))add('重新取数并保存草稿','refresh');
  if(x.state==='DRAFT'&&x.data.created_by===c.me.user.id)add('提交归口复核','submit');
  if(x.state==='SUBMITTED'&&workspace.my_duties.includes('coordinator'))add(x.data.start_month===1&&x.data.end_month===12?'启动年度公示':'复核报送','approve');
  if(x.state==='PUBLIC'){add('提出公示异议','dispute');if(workspace.my_duties.includes('coordinator'))add('记录异议处理','resolve');if(workspace.my_duties.includes('secretary'))add('公示完成并归档','archive')}
 }
 if(kind==='social_policy'&&c.me.role.kind==='school'&&c.can('rules.manage'))buttons.push(act(x.state==='DRAFT'?'继续填写草稿':'复制为新版本',x.state==='DRAFT'?'social-policy-edit':'social-policy-copy'));
 if(kind==='social_policy'&&x.state==='DRAFT'&&c.me.role.kind==='school'&&c.can('rules.manage'))buttons.push(act('补充学校工作日历','social-policy-calendar'));if(kind==='social_policy'&&x.state==='ACTIVE'&&c.can('rules.manage')&&workspace.my_duties.includes('coordinator'))add('停用此口径（保留历史）','deactivate');if(kind==='social_policy'&&x.state==='DRAFT'&&c.me.role.kind==='school'&&c.can('rules.manage'))add(x.data.interpretation_reference?'更新学校书面依据':'登记学校书面依据（依据栏填文号）','record_basis');if(kind==='social_policy'&&x.state==='DRAFT'&&workspace.my_duties.includes('coordinator'))add('确认学校口径并启用','activate');
 if(kind==='social_annual'){
  if(['DRAFT','RETURNED'].includes(x.state)){add('提交学院自评','submit');buttons.push(act('补正年度自评','social-annual-edit'))}
  if(x.state==='REVIEW')for(const [key,label] of Object.entries({finance:'财务核验',academic:'成果核验',discipline:'纪检核验',coordinator:'归口初核'}))if(workspace.my_duties.includes(key)&&!x.snapshot?.checks?.[key])add(label,key);
  if(x.state==='COMMITTEE'&&workspace.my_duties.includes('committee'))add('委员会评分并公示','publish');
  if(x.state==='PUBLIC'){add('登记公示异议','dispute');if(workspace.my_duties.includes('coordinator'))add('记录异议处理','resolve');if(workspace.my_duties.includes('secretary'))add('公示完成并归档','archive')}
  if(['REVIEW','COMMITTEE','PUBLIC'].includes(x.state)&&workspace.my_duties.includes('coordinator'))add('退回重新核算','return');
 }
 const pkey=kind+'|'+id,pending=pendingUploads.get(pkey),outcome=outcomeNotes.get(pkey),stillFailed=pending&&uploadable&&!['ARCHIVED','ACTIVE','CLOSED','VOID'].includes(x.state)?failedEntries(pending.entries):[];if(outcome)outcomeNotes.delete(pkey);if(pending&&!stillFailed.length)pendingUploads.delete(pkey);
 if(stillFailed.length&&c.can('file.write'))buttons.unshift(act('只补传失败的 '+stillFailed.length+' 份'+(pending.then==='submit'?'并提交':''),'social-upload-retry','','primary','file'));
 let body='<div class="social-detail">'+(outcome?note(outcome,true):'')+(stillFailed.length?'<section class="social-detail-section upload-retry"><h3>材料上传结果</h3>'+uploadStatusHtml(pending.entries,esc)+'</section>':'')+'<div class="social-detail-status"><strong>当前办理状态</strong>'+statusBadge(d.state_label,x.state)+'</div>'+(avoided?note('这是你本人登记、申报或发起的事项，按回避规定须由其他有审核职责的人员办理。',true):'')+(opened.busyNote?note(opened.busyNote):'')+(kind==='social_claim'?claimBlockersHtml(d.trial?.blockers||[],esc):(d.trial?.blockers||[]).map(v=>note(v,true)).join(''));
 if(sectioned)body+='<nav class="detail-section-nav" aria-label="业务详情分区"><button type="button" data-detail-section="social-info">业务资料</button><button type="button" data-detail-section="social-materials">佐证材料</button><button type="button" data-detail-section="social-history">办理记录</button></nav><div id="social-info" class="detail-section">';
 if(kind==='social_resource'&&x.kind==='point_report'){
  if(x.state==='VOID')body+=note('原公示期间积分来源已变化，已由新公示替代。下方保留原公示快照，不再作为当前公示或归档依据。',true);
  else if(x.data.replaces?.length)body+=note('这是按最新归档积分重新生成的公示，公示期限从本次发布日重新计算，不能沿用旧公示期限。');
 }
 const steps=kind==='social_project'?[['DRAFT','项目申报'],['SUBMITTED','审核备案'],['FILED','培训实施'],['CLOSE_REVIEW','结项核验'],['CLOSED','正常结项']]:kind==='social_claim'?[['DRAFT','本人填写'],['SUBMITTED','院长初审'],['DEAN','归口复审'],['COORDINATOR','分管副校长审批'],['APPROVED','教学秘书归档'],['ARCHIVED','已入账']]:kind==='social_annual'?[['DRAFT','学院自评'],['REVIEW','职能核验'],['COMMITTEE','委员会评分'],['PUBLIC','公示'],['ARCHIVED','已归档']]:[];
 const handling=opened.inlineApprove?handlePanel(kind,x,d):null;if(handling)body+=handling.summary;
 if(!selfOwned&&c.queueNext?.(kind+'|'+id))buttons.push(act('查看下一条','social-next','','light'));
 const progress=kind==='social_project'&&d.progress?progressHtml(d.progress,esc):steps.length?'<nav class="social-progress" aria-label="办理流程"><ol>'+steps.map(([state,label])=>'<li data-current="'+(x.state===state)+'"'+(x.state===state?' aria-current="step"':'')+'>'+label+'</li>').join('')+'</ol></nav>':'';
 if(progress)body+=sectioned?'<details class="detail-fold application-flow"><summary>查看完整办理流程</summary>'+progress+'</details>':progress;
 if(kind==='social_project'&&d.progress?.tone==='red')body+=note(d.progress.headline,true);
 else if(x.state==='RETURNED'){const last=[...(d.events||[])].reverse().find(e=>/退回/.test(e.action));body+=note('退回意见：'+(last?.reason||'请核对办理记录，补充后重新提交。'),true)}
 if(kind==='social_annual'&&x.snapshot?.public_end)body+=note('公示期间：'+x.snapshot.public_start+' 至 '+x.snapshot.public_end+'。公示期满且异议处理完毕后归档。');
 if(kind==='social_annual'&&!d.public_summary&&['REVIEW','COMMITTEE','PUBLIC','ARCHIVED'].includes(x.state))body+='<section class="social-detail-section"><h3>职能部门核验进度</h3>'+table(['核验环节','核验状态','核验意见'],Object.entries({finance:'财务核验',academic:'成果核验',discipline:'纪检核验',coordinator:'归口初核'}).map(([key,label])=>{const check=x.snapshot?.checks?.[key];return [label,check?'已核验':'待核验',esc(check?.reason||check?.basis||(check?'已留痕核验':'等待对应职责人员办理'))]}))+'</section>';
 const data=x.data;
 if(kind==='social_annual'&&d.public_summary)body+=detailFacts('公示对象',[['公示学院',esc(d.org_name||c.orgName(x.org_id))],['认定周期',esc(c.periodName(x.period_id))]]);
 if(kind==='social_annual'&&!d.public_summary)body+=detailFacts('学院自评资料',[['自评学院',esc(d.org_name||c.orgName(x.org_id))],['认定周期',esc(c.periodName(x.period_id))],['年度任务下达依据',esc(data.target_reference||'尚未填写')],['组织人数基准',esc(data.staff_denominator??'尚未填写')],['组织人数依据',esc(data.staff_basis||'尚未填写')],['单位自评报告',esc(data.self_report||'尚未填写')],['其他加分',esc(data.other_bonus??0)],['其他加分依据',esc(data.other_bonus_basis||'无')],['其他已确认不合规次数（不含项目结算核验）',esc(data.compliance_failures??0)],['正式处理或处分依据',esc(data.discipline_reference||'无')]]);
 if(kind==='social_project'){
  if(d.facts.blockers?.length)body+=d.facts.blockers.map(v=>note(v,true)).join('');
  if(x.closeout_pending?.length)body+=x.closeout_pending.map(v=>note(v,true)).join('');
  const pending=data.source||{},needs=[pending.dates_pending||pending.date_pending?'实际培训日期':'',pending.mode_pending?'备案核算方式':'',...(pending.policy_pending||(pending.ledger_id?['level','scene'].filter(k=>!data[k+'_confirmed']):[])).map(k=>({level:'项目层级',scene:'授课场景'}[k]))].filter(Boolean);
  if(needs.length)body+=note('台账草稿待核实：'+needs.join('、')+'。当前显示的自动生成值仅供整理，不能直接正式备案。',true);
  body+=detailFacts('项目资料',[['名称',esc(data.name)],['期次',esc(x.cohort)],['培训期间',esc(data.start_date+' 至 '+data.end_date)],['核算方式',esc(names[data.mode])],['备案登记日期',esc(data.filed_on||'未备案')],['前置审核日期',esc(data.prior_review_on||'不适用')],['备案依据',esc(data.filing_basis||'待补充')],['培训类别',esc(names[data.category])],['预计收入',esc(data.expected_income)+' 元'],['预期成果',esc(data.expected_outcomes)],['有效人次',d.facts.effective],['剔除人次',d.facts.excluded]]);
  body+=venueBlock(data)+prepBlock(data);
  body+=reportBlock(data,d.report_issues,d.video_minutes);
  if(d.facts.units.length)body+='<h3>参训明细</h3>'+table(['单元编号','培训日期','课程编号','参训记录数'],d.facts.units.map(u=>[esc(u.external_key),esc(u.data.event_date),esc(u.data.course_code),u.data.learners.length]));
  body+=detailFacts('备案核算条件',[['承办学院',esc(d.org_name||c.orgName(x.org_id))],['负责人',esc(c.teacherName(x.owner_id))],['标准班类型',esc(names[data.class_type])],['项目层级',esc(names[data.level])],['专项层级依据',esc(data.level_basis||'按类别通常口径')],['授课场景',esc(names[data.scene])],['辅助积分细则',esc(data.auxiliary_standard||'未备案')],['个人辅助积分每日上限',data.auxiliary_daily_cap??'未确认']]);
  if(x.closeout.closed_on){const z=x.closeout,zeroIncome=z.actual_income!=null&&String(z.actual_income).trim()!==''&&Number(z.actual_income)===0;body+='<h3 class="mt20">结项核验</h3>'+table(['核验项目','登记内容'],[['结项日期',esc(z.closed_on)],['成果报告',esc(z.outcome_report)],['满意度',esc(z.satisfaction)+'%'],['实际到账收入',esc(z.actual_income)+' 元'],['财务确认依据',esc(z.finance_reference)],['结算日期',esc(z.settlement_on||'待结算')],['隐性成本',esc(z.implicit_cost)+' 元'],['资金来源',esc({other_training:'其他培训收入',government_special:'政府专项培训资金'}[z.funding_source]||(zeroIncome?'零收入，不涉及':'历史记录待补确认'))],['专项适用依据',esc(z.funding_basis||'不适用或待补')],['收入分配',z.retained!=null?'学校留存 '+esc(z.retained)+' 元 · 项目公用 '+esc((Number(z.actual_income)-Number(z.retained)-Number(z.personnel)).toFixed(2))+' 元 · 校内人员支出 '+esc(z.personnel)+' 元':Number(z.actual_income)>0?(z.funding_source==='government_special'?'按主管部门规定核验，见专项依据':'历史分配资料待补确认'):zeroIncome?'零收入，不涉及':'收入资料待补确认'],['省平台报送凭证',esc(z.province_receipt||'不适用或待补充')],['专项佐证',esc(z.special_evidence||'不适用或待补充')],['整改报告',esc(z.rectification||'无')],['整改期限',esc(z.rectification_due||'不适用')],['已核验材料',esc((z.materials_checked||[]).map(k=>({plan:'培训方案',filing_form:'备案登记表',roster:'学员名册',attendance:'签到表',hours:'学时记录',process:'过程影像',assessment:'结业考核',outcomes:'成果材料'}[k])).join('、'))],['档案保管',z.retention_years?z.retention_years+'年':'结项审核后确定']]);}
  if(d.facts.followups.length)body+='<h3>投诉、整改及结算跟踪</h3>'+table(['事项编号','类型','办理期限','办结日期','财务结论','回复'],d.facts.followups.map(r=>[esc(r.case_reference),esc({complaint:'投诉',rectification:'整改',settlement:'结算',violation:'正式处理'}[r.kind]),esc(Object.entries(r.deadlines||{}).map(([k,v])=>k+'：'+v).join('；')),esc(r.completed_on||'待办结'),esc(r.kind==='settlement'?({noncompliant:'已确认不合规',exempt:'已批准例外'}[r.settlement_result]||'待财务核验'):'不适用'),esc(r.reply||'待回复')]));
 }
 if(kind==='social_policy'){
  const values={ratio_cap:'人次÷标准人数，最高2',over_standard_two:'超过标准人数按2',daily:'按培训日',whole_project:'按整个期次',half_up:'四舍五入',proportional:'按比例',full_steps:'完整步长',four_indicators:'四项年度指标',all_bonus_shared_ten:'单项加分合计最高10分',three:'三个等次',four:'四个等级',highest_per_reference:'同一成果取最高等级',exclusive:'同一工作不重复计分',teaching:'仅授课积分',all:'授课与辅助积分',project_units:'按项目核算单元',closeout:'按结项日期',original_submission:'按首次申报日期',resubmission_date:'按补正提交日期'};
  body+=table(['执行口径','已登记内容'],Object.entries(workspace.decisions).map(([key,label])=>[esc(label),data[key]==null?'待学校书面确认':esc(typeof data[key]==='boolean'?(data[key]?'可以认定':'不予认定'):values[data[key]]||data[key])]))+note('学校书面解释依据：'+(data.interpretation_reference||'尚未提供'));
  body+=detailFacts('学校工作日历',[['开始日期',esc(data.calendar_start||'尚未登记')],['结束日期',esc(data.calendar_end||'尚未登记')],['校历依据',esc(data.calendar_reference||'尚未登记')]]);
  if(!data.calendar_start||!data.calendar_end||!data.calendar_reference)body+=note('学校工作日历尚未确认，启用前请补充校历。',true);
 }
 if(kind==='social_resource'&&!['correction','point_report','point_review'].includes(x.kind)){
  body+='<section class="social-detail-section"><h3>基本资料</h3><dl class="kv">'+[['名称',x.name],['来源编号',x.code],['承办学院',d.org_name||x.org_name||workspace.resources.find(r=>r.id===x.id)?.org_name||c.orgName(x.org_id)],...(x.kind==='base'?[['基地类型',data.onsite===true?'校内基地':data.onsite===false?'校外基地':'待补充']]:[]),...(x.kind==='achievement'?[['成果等级',names[data.level]||'待确认'],['认定日期',data.confirmed_on||'待补充']]:[]),['认定依据',data.recognition],['地点或说明',data.location||'待补充'],...(x.kind==='course_resource'?[['关联课程',data.course_code],['资源类型',{video:'视频',document:'文档',link:'其他链接'}[data.resource_type]||'待确认'],['归属教师',data.teacher_id?c.teacherName(data.teacher_id):'待确认'],['视频总时长',data.duration_minutes==null?'不适用':data.duration_minutes+' 分钟']]:[])].map(([label,value])=>'<dt>'+label+'</dt><dd>'+esc(value)+'</dd>').join('')+'</dl></section>';
  if(data.resource_url&&/^https?:\/\//.test(data.resource_url))body+='<p><a href="'+esc(data.resource_url)+'" target="_blank" rel="noopener noreferrer">打开课程资源</a></p>';
 }
 if(kind==='social_resource'&&x.kind==='point_review'){const r=d.review_context||{},out={corrected:r.correction_state==='VOID'?'该更正已作废，未追加积分；如仍需调整，请重新发起核对':data.ruling?'学院已裁定更正，已生成更正单，进入归口、分管副校长审批及教学秘书归档':'已生成更正单，进入院长、归口、分管副校长审批及教学秘书归档',kept:'学院裁定维持原认定',withdrawn:'发起人已撤回'}[data.outcome];body+=note({DRAFT:d.workflow_blockers?.length?'下一步：请学校管理员配置无需回避的替代办理人，完成后刷新详情再发送。':'下一步：上传核对材料（如签到表、认定表），再点“发给教师回应”。',TEACHER:'等待教师回应：同意就自动生成更正单；不同意由学院院长裁定。未办结前不能确认该教师的考核。',COLLEGE:'教师不同意，等待学院院长裁定。',CLOSED:'已办结：'+(out||'')}[x.state]||'')+table(['核对内容','说明'],[['被核对教师',esc(r.teacher_name)],['所属项目',esc(r.project)],['原认定积分','授课 '+esc(r.teaching??'—')+'，辅助 '+esc(r.auxiliary??'—')],['建议更正','授课 '+esc(data.teaching)+'，辅助 '+esc(data.auxiliary)+'（正数增加、负数扣减）'],['入账周期',esc(c.periodName(data.period_id))],['发起人',esc(r.creator_name)],['哪里不对',esc(data.reason)],['教师回应',esc(data.teacher_reply||'尚未回应')],['学院裁定',esc(data.ruling||(x.state==='COLLEGE'?'待裁定':'—'))]])}
 if(kind==='social_resource'&&x.kind==='correction')body+=table(['更正项目','内容'],[['授课积分变动',esc(data.teaching)],['辅助积分变动',esc(data.auxiliary)],['正式处理或更正依据',esc(data.decision_reference)],['入账周期',esc(c.periodName(data.period_id))]])+note(x.state==='VOID'?'本更正已作废，未追加积分。作废原因：'+(data.void_reason||'')+'。如需更正，请返回原认定重新办理。':'经逐级审核后追加差额，原认定快照保持不变。');
 if(kind==='social_resource'&&x.kind==='point_report')body+=detailFacts('汇总范围',[['汇总组织',esc(d.org_name||c.orgName(x.org_id))],['汇总期间',esc(data.year)+'年 '+esc(data.start_month)+'—'+esc(data.end_month)+'月']])+table(['教师','学院','项目','授课积分','辅助积分','合计'],data.rows.map(r=>[esc(r.teacher_name),esc(r.org_name),esc(r.project),esc(r.teaching),esc(r.auxiliary),esc(r.total)]))+note('汇总截至本次生成时已归档的认定及更正。'+(data.public_end?'公示截止：'+data.public_end+'；满5个工作日且异议处理完毕后归档。':''));
 const disputes=kind==='social_annual'?x.snapshot?.disputes:data.disputes;
 if(disputes?.length)body+='<section class="social-disputes" aria-label="公示异议与反馈">'+table(['异议内容','办理情况'],disputes.map(r=>[esc(r.reason),esc(r.resolved?r.resolution:'待核实')]))+'</section>';
 if(kind==='social_claim'){
  body+=detailFacts('积分认定资料',[['申报人',esc(c.teacherName(x.teacher_id))],['项目',esc(d.trial?.basis?.facts?.project?.data?.name||d.trial?.basis?.facts?.project?.name||'关联项目')],['认定周期',esc(c.periodName(x.period_id))],['认定表及附件对应说明',esc(data.recognition_form_reference||'尚未填写')]]);
  const auxiliary=(x.state==='ARCHIVED'?d.trial?.basis?.claim_data?.auxiliary:undefined)??data.auxiliary;
  if(Array.isArray(auxiliary)&&auxiliary.length)body+='<section class="social-detail-section"><h3>辅助工作明细</h3>'+table(['日期','工作说明','申报积分'],auxiliary.map(row=>[esc(row.work_date),esc(row.description),esc(row.amount)]))+'</section>';
 }
 if(d.trial){const t=d.trial,archived=x.state==='ARCHIVED',gradeLabel=archived?'认定等级':'候选等级';body+=note(archived?'以下为归档时的核算快照':'以下为候选试算，尚非正式认定');body+=table(['指标','分值'],[['授课积分',t.teaching??'不适用'],['辅助积分',t.auxiliary??'不适用'],['基础分',t.base??'不适用'],['认定加分',t.bonus_awarded??'不适用'],['合计',t.total??'待学校确认'],[gradeLabel,esc(t.grade||'待核定')],['申报期限',esc(t.deadline||'不适用或待校历确认')]].filter(([label,value])=>value!=='不适用'&&(label!==gradeLabel||kind==='social_annual')&&(label!=='申报期限'||!!t.deadline)));if(t.details)body+=table(['核算单元','人次','计算依据',archived?'认定积分':'候选积分'],t.details.map((r,i)=>[esc('第'+(i+1)+'核算单元')+'<details class="implementation-details"><summary>实施人员使用：单元编号</summary>'+esc(r.unit)+'</details>',r.participants,esc(r.formula)+(r.standard&&/^基数 \d+\.\d+ ×/.test(r.formula)?'<p class="cell-sub">基数显示值已取小数；原始人次比例为'+esc(r.participants)+'÷'+esc(r.standard)+'，按本单封顶口径计算。</p>':''),r.score??'待封顶口径确认']));if(t.metrics)body+=table(['指标','实际值','任务目标','基础分','加分'],t.metrics.map(r=>[esc(r.label),r.actual,r.target??'待下达',r.base??'待核定',r.bonus??'待核定']))}
 if(kind==='social_annual'&&d.trial){const t=d.trial;body+=table(['成果、资金及总分处理','内容'],[['综合成果基础分',t.achievement_base],['资金管理基础分',t.cost_base??'待财务核验'],['封顶前各项加分合计',t.bonus_raw],['全校总加分上限','10 分（所有单项加分共用上限）'],['封顶前总分',t.total_before_cap??'待核定'],['已确认总分上限',t.total_cap??'待核定'],['一票否决',t.veto?'已触发':'未触发'],...(!d.public_summary?[['正式处理依据',esc(t.veto_basis||data.discipline_reference||'无')],['学院个人积分合计',t.points_total],['按已确认人数的平均积分',t.points_average??'人数基准待确认']]:[])]);if(t.cost_details)body+=table(['资金管理扣分项','扣分或说明'],t.cost_details.map(r=>[esc(r.label),esc(r.value)]));if(t.outcome_details)body+=table(['成果认定依据','得分依据'],t.outcome_details.map(r=>[esc(r.label),esc(r.value)]));}
 if(sectioned)body+='</div>';
 body+=(d.public_summary?note('公示开放评分摘要；原始核验材料由授权人员查看。'):'<section class="social-detail-section" id="social-materials"><h3>佐证材料</h3>'+c.downloads(d.attachments)+'</section>'+(handling?handling.form:'')+'<details id="social-history" class="detail-fold mt20"><summary>办理记录</summary>'+c.eventsHtml(d.events)+'</details>')+'</div>';
 const pname=d.trial?.basis?.facts?.project?.data?.name||d.trial?.basis?.facts?.project?.name||'',title=data.name||x.name||({social_claim:'个人积分申报',social_annual:d.public_summary?'学院考核公示':'学院年度自评',social_resource:'积分更正与汇总'}[kind]||'社会培训办理')+(pname?' · '+pname:'');
 if(manager&&moreActions.length)buttons.unshift('<details class="detail-more-actions"><summary>更多操作</summary><div>'+moreActions.join('')+'</div></details>');if(handling)buttons.push('<div class="social-handle-actions">'+act('确认'+opened.labels.approve,'social-handle','approve','primary')+'</div>');if(['teacher','dept','college','school'].includes(c.me.role.kind))buttons.push(act('关闭','close'));opened.printBody=body;c.modal(title,body,buttons.join(''),true,c.me.role.kind==='teacher'?'个人培训 / 业务详情':manager?detailArea(kind,x)+' / 业务详情':'');
}

// ---- 立德树人与质量（上级 1.2 立德树人表要的数）：申报向导第 4 步、详情块、学院补填共用 ----
const IDEOLOGY_MODES=[['ideology_course','开设思政专题课'],['course_ideology','课程思政融入专业教学'],['practice','思政实践教学（参观、基地实践）'],['lecture','专题讲座、报告'],['none','未开展']];
function audienceFields(v){
 const c=context,e=c.esc,picked=new Set(v.audiences||[]);
 return '<fieldset class="form-field full apply-tags"><legend>受众群体 <b>*</b></legend><div class="apply-tag-row">'+AUDIENCE.map((t,i)=>'<label><input type="checkbox" name="aud_'+i+'" '+(picked.has(t)?'checked':'')+'>'+e(t)+'</label>').join('')+'</div><input name="audience_other" aria-label="其他受众群体" placeholder="其他（选填）" maxlength="200" value="'+e(v.audience_other||'')+'"></fieldset>';
}
const SERVICE_TYPES=[['national','国家战略'],['regional','区域发展'],['industry','行业发展'],['other','其他']];
const TEACHING_METHODS=[['classroom','课堂教学'],['case','案例教学'],['onsite','现场教学'],['field','实地考察'],['seminar','交流研讨'],['lab','实验实训'],['internship','岗位实习'],['peer','学习者互助'],['other','其他']];
const svcLabel=Object.fromEntries(SERVICE_TYPES),tmLabel=Object.fromEntries(TEACHING_METHODS);
function multiChips(prefix,label,options,picked,required=true){
 const e=context.esc,set=new Set(picked||[]);
 return '<fieldset class="form-field full apply-tags"><legend>'+e(label)+(required?' <b>*</b>':'')+'</legend><div class="apply-tag-row">'+options.map(([k,l])=>'<label><input type="checkbox" name="'+prefix+'_'+k+'" '+(set.has(k)?'checked':'')+'>'+e(l)+'</label>').join('')+'</div></fieldset>';
}
function serviceFields(v){return multiChips('svc','服务面向类型',SERVICE_TYPES,v.service_types)}
function methodFields(v){return multiChips('tm','教学实施方式',TEACHING_METHODS,v.teaching_methods)}
function videoField(v){return context.field('video_minutes','视频资源总时长（分钟）','number',v.video_minutes??'',{required:false,min:0,step:1,placeholder:'例：199',hint:'项目建设的视频资源合计时长；没有填 0。'})}
function baseCountField(v){return context.field('base_count','实践教学基地数量（个）','number',v.base_count??'',{required:false,min:0,step:1,placeholder:'例：2',hint:'没有填 0。'})}
const VENUE_TYPES=[['base','校内培训基地'],['campus','其他校内场所'],['offsite','校外']];
function venueFields(g={}){
 const c=context;
 return c.field('venue_type','培训场地','select',g.type||'',{chips:true,options:VENUE_TYPES})
  +c.field('venue_place','具体地点（基地名称、楼宇教室或外出地点）','text',g.place||'',{placeholder:'例：湘茶思政实践基地 / 实训楼101教室 / 湘茶集团茶园'})
  +c.field('venue_reason','校外培训的外出理由（一事一议）','textarea',g.offsite_reason||'',{required:false,hint:'选“校外”时必填：说明为什么不能在校内开展。',placeholder:'例：茶叶采摘与制作必须在茶园现场教学，校内没有条件'})
  +c.field('venue_ref','议定文号或会议日期','text',g.offsite_ref||'',{required:false,hint:'选“校外”时必填：学校一事一议的会议日期或文号。',placeholder:'例：校长办公会 2026-08-20 或 校办〔2026〕15号'});
}
function takeVenue(v){
 const t=v.venue_type,venue={type:t,place:(v.venue_place||'').trim(),offsite_reason:(v.venue_reason||'').trim(),offsite_ref:(v.venue_ref||'').trim()};
 for(const k of ['venue_type','venue_place','venue_reason','venue_ref'])delete v[k];
 if(t==='offsite'&&!(venue.offsite_reason&&venue.offsite_ref))throw Error('校外培训须登记一事一议：外出理由、议定文号或会议日期');
 return venue;
}
function takeQuality(v){
 const audiences=AUDIENCE.filter((t,i)=>v['aud_'+i]);AUDIENCE.forEach((t,i)=>delete v['aud_'+i]);
 const service_types=SERVICE_TYPES.map(([k])=>k).filter(k=>v['svc_'+k]);SERVICE_TYPES.forEach(([k])=>delete v['svc_'+k]);
 const teaching_methods=TEACHING_METHODS.map(([k])=>k).filter(k=>v['tm_'+k]);TEACHING_METHODS.forEach(([k])=>delete v['tm_'+k]);
 const video_minutes=v.video_minutes===''||v.video_minutes==null?null:Number(v.video_minutes);delete v.video_minutes;
 const base_count=v.base_count===''||v.base_count==null?null:Number(v.base_count);delete v.base_count;
 return {audiences,audience_other:v.audience_other||'',service_types,teaching_methods,base_count,video_minutes,total_hours:v.total_hours===''||v.total_hours==null?null:v.total_hours};
}
const PREP_ITEMS=[['plan','教学计划'],['lecturers','师资安排'],['venue','场地'],['equipment','设备'],['materials','教材教具'],['notice','培训告知书或邀请函']];
function venueBlock(data){
 const e=context.esc,g=data.venue,label=Object.fromEntries(VENUE_TYPES);
 if(!g)return '<section class="social-detail-section"><h3>培训场地</h3><p class="muted small">未登记（已备案的项目不强制补填，重新备案时须填写）</p></section>';
 const rows=[['场地类型',e(label[g.type]||g.type)],['具体地点',e(g.place)]];
 if(g.type==='offsite')rows.push(['一事一议：外出理由',e(g.offsite_reason)],['议定文号或会议日期',e(g.offsite_ref)]);
 return '<section class="social-detail-section"><h3>培训场地</h3><dl class="kv">'+rows.map(([k,v])=>'<dt>'+k+'</dt><dd>'+v+'</dd>').join('')+'</dl></section>';
}
function prepBlock(data){
 const e=context.esc,prep=data.prep||{},left=PREP_ITEMS.filter(([k])=>!prep[k]);
 return '<section class="social-detail-section"><h3>开班前准备</h3><ul class="prep-list">'+PREP_ITEMS.map(([k,l])=>'<li data-done="'+!!prep[k]+'">'+(prep[k]?'✓ ':'○ ')+e(l)+'</li>').join('')+'</ul>'+(left.length?'<p class="muted small">还有 '+left.length+' 项未确认：'+e(left.map(x=>x[1]).join('、'))+'。仅作提醒，不影响办理。</p>':'<p class="muted small">六项准备均已确认。</p>')+'</section>';
}
function prepForm(){
 const c=context,x=opened.item,prep=x.data.prep||{};
 commonForm('开班前准备：'+x.data.name,formSection('准备事项',PREP_ITEMS.map(([k,l])=>c.field('prep_'+k,l+'已准备','checkbox',!!prep[k])).join(''),'勾选已落实的事项；仅作提醒，不影响审批和备案。'),async raw=>{const {reason,basis,...rest}=raw;const items={};for(const [k] of PREP_ITEMS)items[k]=!!rest['prep_'+k];return c.api('/social/projects/'+x.id+'/prep',{method:'PUT',body:{reason:reason||'更新开班前准备清单',expected_version:x.version,items}})},{reopen:true,submit:'保存',hideReason:true,reasonDefault:'更新开班前准备清单'});
}
function reportBlock(data,issues,video){
 const c=context,e=c.esc,red='<span class="red">待补充</span>';
 const rows=[['服务面向类型',e((data.service_types||[]).map(k=>svcLabel[k]||k).join('、'))||red],['总学时',data.total_hours!=null&&data.total_hours!==''?e(data.total_hours):red],
  ['视频资源总时长（分钟）',data.video_minutes!=null?e(data.video_minutes):video?e(video)+'（按课程视频统计）':'—'],['实践教学基地数量（个）',data.base_count!=null?e(data.base_count):'—'],
  ['教学实施方式',e((data.teaching_methods||[]).map(k=>tmLabel[k]||k).join('、'))||red],
  ['受众群体',e([...(data.audiences||[]),...(data.audience_other?['其他：'+data.audience_other]:[])].join('、'))||red]];
 return '<section class="social-detail-section"><h3>上报信息</h3>'+(issues?.length?c.note('上报信息还缺：'+issues.join('；'),true):'')+'<dl class="kv">'+rows.map(([k,v])=>'<dt>'+e(k)+'</dt><dd>'+v+'</dd>').join('')+'</dl>'+(data.report_info_on?'<p class="small muted">学院 '+e(data.report_info_on)+' 补填</p>':'')+'</section>';
}
function reportInfoForm(){
 const c=context,x=opened.item,v=x.data;
 const body=formSection('上报信息',serviceFields(v)+context.field('total_hours','总学时','number',v.total_hours??'',{min:0,step:0.5})+videoField(v)+baseCountField(v)+methodFields(v)+audienceFields(v),'已备案、已结项的项目由学院补填，不重新走审批，修改留痕。');
 commonForm('补填上报信息：'+v.name,body,async raw=>{const {reason,basis,...rest}=raw;const info=takeQuality(rest);return c.api('/social/projects/'+x.id+'/report-info',{method:'PUT',body:{reason,basis,expected_version:x.version,...info}})},{reopen:true,submit:'保存上报信息',reasonLabel:'补填说明',reasonDefault:'补填历史项目上报信息'});
}

function projectForm(edit=false){
 const c=context,x=edit?opened.item:null,v=x?.data||{mode:'module',class_type:'technical'},f=(key,label,type='text',options={})=>c.field(key,label+(options.chips?'（单选）':''),type,v[key]??'',options);
 const pending=v.source||{},confirmations=[],teacher=c.me?.role?.kind==='teacher',myCollege=c.me?.org?.kind==='college'?c.me.org.id:c.me?.org?.parent_id;
 if(pending.dates_pending||pending.date_pending)confirmations.push(f('dates_confirmed','确认实际培训期间','checkbox',{checkLabel:'已核对开始、结束日期，占位日期已更正'}));
 if(pending.mode_pending)confirmations.push(f('mode_confirmed','确认备案核算方式','checkbox',{checkLabel:'已核对模块或培训工作日明细'}));
 for(const [key,label] of [['level','项目层级'],['scene','授课场景']])if((pending.policy_pending||[]).includes(key)||(pending.ledger_id&&!v[key+'_confirmed']))confirmations.push(f(key+'_confirmed','确认'+label,'checkbox',{checkLabel:'已依据项目材料核实'+label}));
 const body=formSection('一、项目基本资料',f('code','项目编号','text',{placeholder:'例：SOC-2026-01',hint:'填写项目材料上的编号；不清楚时请先向学院核实。'})+f('name','项目名称','text',{placeholder:'例：2026年社区茶艺公益培训'})+f('cohort','项目期次','text',{placeholder:'例：第一期'})+(teacher?'<input type="hidden" name="org_id" value="'+c.esc(v.org_id||myCollege)+'"><input type="hidden" name="owner_id" value="'+c.esc(c.me.user.id)+'">'+c.field('owner_view','项目负责人','text',c.me.user.name,{readonly:true,required:false,hint:'老师申报的项目，负责人是本人，承办学院是本人所在学院。'}):collegeField(v.org_id)+c.teacherField(v.owner_id||'', 'owner_id','项目负责人（输入工号或姓名检索）'))+f('category','培训类别','select',{chips:true,options:selectable(['subsidy','enterprise','community','rural','other'])})+audienceFields(v)+serviceFields(v)+f('high_risk','高风险项目','checkbox',{required:false,checkLabel:'属于其他高风险项目（须前置审核，备案时登记审核日期及依据）'}),'')+formSection('二、培训安排',f('start_date','开始日期','date')+f('end_date','结束日期','date')+f('expected_income','预计收入（元，公益类填0）','number',{min:0,step:0.01,placeholder:'例：0 或 30000'})+f('expected_participants','预计人次','number',{min:0,step:1,placeholder:'例：120'})+f('expected_outcomes','预期成果','textarea',{placeholder:'例：学员掌握基础茶艺，80%以上取得结业证书'})+f('target_groups','重点群体与行动对接','textarea',{required:false,hint:'补贴性培训必填：写明面向哪些重点群体、对接哪项行动；其他类别可不填。',placeholder:'例：脱贫人口、退役军人；对接“一人一技”行动'})+f('total_hours','总学时','number',{required:false,min:0,step:0.5,placeholder:'例：32',hint:'草稿可暂留空；提交学院审批前必须填写。'})+videoField(v)+baseCountField(v)+methodFields(v)+venueFields(v.venue||{}))+formSection('三、积分核算依据',f('mode','核算方式','select',{chips:true,options:selectable(['module','person_day'])})+'<div class="mode-guide form-field full" role="note" aria-label="核算方式说明"><span><strong>模块式：按课程模块统计。</strong>适合短期专题培训。例：同一教师讲 2 个模块，每个模块均有 30 名有效学员完整参加，计 <strong>60 人次</strong>。</span><span><strong>人天式：按完整培训工作日统计。</strong>适合脱产集中培训。例：30 名有效学员完整培训 1 天，计 <strong>30 人次</strong>；同一天多个模块不重复计。</span><span class="mode-guide-note">示例说明的是培训人次，不是积分。最终积分按学校规则核算。</span></div>'+f('class_type','标准班类型','select',{chips:true,options:selectable(['technical','lecture'])})+f('level','项目层级','select',{chips:true,options:selectable(['province','city','school'])})+f('scene','授课场景','select',{chips:true,options:selectable(['dispatched','full_day','ordinary'])})+f('level_basis','专项层级认定依据','textarea',{required:false,hint:'企业定制通常选市级；社区、免费帮扶通常选校级。属于更高层级专项时，填写正式认定依据并提交归口核验。',placeholder:'例：省人社厅专项培训认定文件〔2026〕8号'})+f('auxiliary_standard','随项目备案的辅助积分细则','textarea',{required:false,placeholder:'例：班主任每天0.5分，每人每天不超过1分'})+f('auxiliary_daily_cap','个人辅助积分每日上限','number',{required:false,min:0,step:0.01,placeholder:'例：1'}),'同期项目只采用一种核算方式；尚未确认的辅助积分标准请留空。')+(confirmations.length?formSection('四、台账草稿待核实事项',confirmations.join(''),'核实并保存后才能提交正式备案；自动生成的值不能代替材料核验。'):'');
 commonForm(edit?'修改项目申报':'申报培训项目',body,async v=>{delete v.owner_id_search;delete v.owner_view;const venue=takeVenue(v);const info=takeQuality(v);const data=cleanReason(v);Object.assign(data.data,info,{venue});return c.api('/social/projects'+(edit?'/'+x.id:''),{method:edit?'PUT':'POST',body:{...data,...(edit?{expected_version:x.version}:{})}})},
  edit?{reopen:true,page:true}:{page:true,submit:'保存草稿',reasonLabel:'申报说明',reasonDefault:teacher?'申报本人负责的培训项目':'学院申报培训项目',hint:teacher?'保存草稿后上传材料，再提交学院审批；学院通过后到学校备案。':'保存草稿后上传材料，再提交审核备案。',after:r=>r?.item?.id?showDetail('social_project',r.item.id):null});
 bindProjectCategory();bindVenue();
}
function bindCloseForm(){
 if(typeof document==='undefined')return;const $=id=>document.getElementById(id),show=(id,on)=>{const el=$('cond-'+id);if(el)el.style.display=on?'contents':'none'};
 const income=$('f-actual_income'),source=$('f-funding_source'),sat=$('f-satisfaction'),loc=$('f-location'),ret=$('f-retained'),per=$('f-personnel'),hint=$('close-split-hint'),all=$('close-check-all');if(!income||!source)return;
 const sync=()=>{const money=Number(income.value||0),special=source.value==='government_special';show('special',special);show('split',!special);show('rect',sat.value!==''&&Number(sat.value)<85);
  if(hint){const r=Number(ret.value||0),p=Number(per.value||0),off=loc.value==='offsite',minR=off?10:20,maxP=off?70:60;hint.textContent=money>0&&!special?'按到账收入 '+money+' 元：学校留存至少 '+(money*minR/100).toFixed(2)+' 元，人员支出至多 '+(money*maxP/100).toFixed(2)+' 元'+(r||p?'；当前留存 '+(r/money*100).toFixed(1)+'%、人员支出 '+(p/money*100).toFixed(1)+'%'+(r<money*minR/100||p>money*maxP/100?'，不符合比例要求':'，符合比例要求'):''):'';hint.style.color=/不符合/.test(hint.textContent)?'#c0392b':/符合/.test(hint.textContent)?'#218b74':''}};
 for(const el of [income,source,sat,loc,ret,per])el?.addEventListener('input',sync),el?.addEventListener('change',sync);sync();
 const boxes=[...document.querySelectorAll('#edit-form input[type=checkbox][name^="checked_"]')];
 all?.addEventListener('change',()=>boxes.forEach(b=>b.checked=all.checked));boxes.forEach(b=>b.addEventListener('change',()=>{all.checked=boxes.every(x=>x.checked)}));
}
const VENUE_PLACE={base:'例：湘茶思政实践基地',campus:'例：实训楼101教室',offsite:'例：湘茶集团茶园'};
// 选“校外”才出现一事一议两栏，其他场地不用看到。
function bindVenue(){
 if(typeof document==='undefined')return;const type=document.getElementById('f-venue_type'),place=document.getElementById('f-venue_place');if(!type)return;
 const wrap=id=>document.getElementById(id)?.closest('.form-field'),sync=()=>{const off=type.querySelector('input:checked')?.value==='offsite';for(const id of ['f-venue_reason','f-venue_ref']){const w=wrap(id);if(w)w.style.display=off?'':'none';const el=document.getElementById(id);if(el)el.required=off}if(place)place.placeholder=VENUE_PLACE[type.querySelector('input:checked')?.value]||'先选择培训场地类型'};
 type.addEventListener('change',sync);sync();
}
function bindProjectCategory(){
 if(typeof document==='undefined')return;
 const cat=document.getElementById('f-category'),pick=id=>document.querySelector('#f-'+id+' input:checked')?.value||'',tg=document.getElementById('f-target_groups'),lab=document.querySelector('label[for="f-target_groups"]');if(!cat||!tg||!lab)return;
 const sync=()=>{const need=pick('category')==='subsidy';tg.required=need;lab.querySelector('b')?.remove();if(need)lab.insertAdjacentHTML('beforeend',' <b>*</b>')};
 cat.addEventListener('change',()=>{sync();const value={enterprise:'city',community:'school',rural:'school'}[pick('category')],radio=value&&document.querySelector('#f-level input[value="'+value+'"]');if(radio)radio.checked=true});sync();
}

function policyForm(x=null,copy=false){
 const c=context,values={...(x?.data||{}),name:x?(x.name+(copy?'（新版本）':'')):'',period_id:x?.period_id||currentOpenPeriod(c.periods)},edit=x&&!copy;
 if(!c.periods.some(p=>p.state==='OPEN'))throw Error('没有开放的考核周期，请先在“规则与配置 → 考核周期与规则”新增周期');
 const policyField=(key,label,type='text',value='',opts={})=>c.field(key,label,type,Array.isArray(values[key])?values[key].join('\n'):(values[key]??value),opts);
 const choice=(key,label,options)=>policyField(key,label,'select','',{options:[['','待学校确认'],...options],required:false});
 let body=`<div class="social-recommend"><button type="button" class="btn light" id="policy-recommend">按系统推荐口径一键填写（待学校书面确认）</button><p class="cell-sub">只补空白项，不覆盖已填内容；书面依据须由学校确认后填写。</p></div>`+policyField('name','规则版本名称')+policyField('period_id','适用周期','select','',{options:[['','请选择适用年度或学年'],...c.periods.filter(x=>x.state==='OPEN').map(x=>[x.id,x.name])]});
 const groups={personal:'',annual:'',scope:''};let calendar='';
 for(const [k,label,opts] of [
  ['cap_mode','单次积分封顶',[['ratio_cap','人次÷标准人数，最高2'],['over_standard_two','超过标准人数直接按2']]],['person_day_unit','人天式单次范围',[['daily','每个培训日'],['whole_project','整个项目期次']]],
  ['precision','单元积分及汇总精度',[[2,'逐单元及汇总均保留两位（须学校确认）']]],['rounding','舍入方式',[['half_up','四舍五入']]],['step_mode','不足计分步长',[['proportional','按比例计算'],['full_steps','只计算完整步长']]],
  ['annual_model','学院考核模型',[['four_indicators','收入、人次、成果、资金管理四项']]],['bonus_pool','总加分规则',[['all_bonus_shared_ten','所有单项加分共用10分上限']]],['grade_mode','考核等次',[['three','优秀、合格、不合格'],['four','优秀、良好、合格、不合格']]],
  ['satisfaction_inclusive','恰好95%满意度',[['true','可以认定成果'],['false','不认定，须超过95%']]],['achievement_dedup','成果去重',[['highest_per_reference','同一成果依据仅取最高等级']]],['auxiliary_overlap','辅助工作重叠',[['exclusive','同一工作不得重复计分']]],['title_scope','职称折算范围',[['teaching','仅授课积分'],['all','授课及辅助积分']]],['organization_basis','学院人次口径',[['project_units','按项目核算单元汇总，不重复累计教师']]],['date_basis','年度归属',[['closeout','按结项日期归属']]]])groups[['cap_mode','person_day_unit','precision','rounding','auxiliary_overlap'].includes(k)?'personal':['step_mode','annual_model','bonus_pool','grade_mode','satisfaction_inclusive','achievement_dedup'].includes(k)?'annual':'scope']+=choice(k,label,opts);
 groups.scope+=choice('title_precision','职称折算小数位',[[0,'整数'],[1,'一位'],[2,'两位'],[3,'三位'],[4,'四位']])+choice('title_rounding','职称折算舍入',[['half_up','四舍五入']])+choice('resubmission_mode','退回补正期限依据',[['original_submission','按首次申报日期'],['resubmission_date','按补正再次提交日期']]);
 for(const [k,l] of [['total_cap','年度总分上限'],['excellent_from','三等制优秀门槛'],['qualified_from','三等制合格门槛']])groups.annual+=policyField(k,l,'number','',{required:false,min:0,step:0.01});
 for(const [k,l] of [['effective_date','本口径适用开始日期'],['calendar_start','校历开始日期'],['calendar_end','校历结束日期']])calendar+=policyField(k,l,'date','',{required:false});
 for(const [k,l] of [['holidays','放假日期（每行一个）'],['workdays','周末补班日期（每行一个）'],['calendar_reference','学校工作日历依据'],['interpretation_reference','学校书面解释依据']])calendar+=policyField(k,l,'textarea','',{required:false});
 body=formSection('一、版本与周期',body)+formSection('二、个人积分',groups.personal)+formSection('三、学院年度考核',groups.annual)+formSection('四、归属与折算',groups.scope)+formSection('五、校历与书面依据',calendar);
 commonForm(edit?'补齐学校制度草稿':copy?'复制制度口径为新草稿':'登记学校制度执行口径',body,async v=>{const {name,period_id,reason,basis,...raw}=v;const data=blankNull(raw);for(const [k,l] of [['holidays','放假日期'],['workdays','周末补班日期']])data[k]=(raw[k]||'').split(/[\s,，、；;]+/).filter(Boolean).map((d,i)=>{const m=d.match(/^(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})日?$/);if(!m)throw Error(l+'第'+(i+1)+'个“'+d+'”不是日期，请写成 2026-10-01，每行一个');return m[1]+'-'+m[2].padStart(2,'0')+'-'+m[3].padStart(2,'0')});for(const k of ['calendar_reference','interpretation_reference'])data[k]=raw[k]||'';for(const k of ['precision','title_precision'])if(data[k]!=null)data[k]=Number(data[k]);if(data.satisfaction_inclusive!=null)data.satisfaction_inclusive=data.satisfaction_inclusive==='true';return c.api('/social/policies'+(edit?'/'+x.id:''),{method:edit?'PUT':'POST',body:{name,period_id,reason,basis,data,...(edit?{expected_version:x.version}:{})}})},{partialDraft:true,submit:'保存草稿',after:r=>r?.item?.id?showDetail('social_policy',r.item.id):null,hint:'只登记学校书面确认的选项；尚未确认的保持空白。如学校解释不在当前支持范围内，先保留待确认，由实施人员补充实现。'});
 if(typeof document!=='undefined'){
  const grade=document.getElementById('f-grade_mode'),thresholds=['excellent_from','qualified_from'].map(k=>document.getElementById('f-'+k));
  const sync=()=>thresholds.forEach(el=>{if(el)el.closest('.form-field').hidden=grade.value!=='three'&&el.value===''});
  grade?.addEventListener('change',sync);sync();
 }
 if(typeof document==='undefined')return;document.getElementById('policy-recommend')?.addEventListener('click',()=>{for(const [k,v] of Object.entries(RECOMMENDED_POLICY)){const el=document.getElementById('f-'+k);if(el&&el.value===''){el.value=String(v);el.dispatchEvent(new Event('change',{bubbles:true}))}}});
}
// 推荐口径：与《社会培训模块重新规划》第八节确认清单一致；学校书面确认前不得启用。
const RECOMMENDED_POLICY={cap_mode:'ratio_cap',person_day_unit:'daily',precision:2,rounding:'half_up',step_mode:'full_steps',annual_model:'four_indicators',bonus_pool:'all_bonus_shared_ten',grade_mode:'four',satisfaction_inclusive:'true',achievement_dedup:'highest_per_reference',auxiliary_overlap:'exclusive',title_scope:'all',organization_basis:'project_units',date_basis:'closeout',title_precision:2,title_rounding:'half_up',resubmission_mode:'original_submission',total_cap:110,effective_date:'2026-08-01'};

async function dutiesForm(){
 const c=context,d=await c.api('/social/duties'),selected=Object.fromEntries(Object.keys(d.labels).map(k=>[k,new Set(d.assignments[k]||[])])),people=new Map((d.people||[]).map(p=>[p.id,p]));let sequence=0;
 const name=id=>{const p=people.get(id);return p?p.name+' · '+(p.org_name||'组织待核对'):'原办理人（资料待核对）'};
 commonForm('学校社会培训审批职责',c.field('duty','选择要调整的职责','select',Object.keys(d.labels)[0],{options:Object.entries(d.labels),required:false,full:true})+'<div class="full"><div id="duty-selected"></div><label for="duty-query">搜索姓名、工号或账号</label><div class="flex"><input id="duty-query" type="search" placeholder="输入姓名或工号"><button type="button" class="btn" data-duty-search>查询</button></div><div id="duty-options" aria-live="polite"></div><div id="duty-summary"></div></div>',v=>c.api('/social/duties',{method:'PUT',body:{expected_version:d.version,assignments:Object.fromEntries(Object.entries(selected).map(([k,ids])=>[k,[...ids]])),reason:v.reason,basis:v.basis}}),{submit:'保存职责配置',hint:'原办理人完整保留；搜索或翻页不会取消已选人员。保存时再次核对有效身份与审核范围。'});
 if(typeof document==='undefined')return;
 const form=document.getElementById('edit-form'),kind=document.getElementById('f-duty'),box=document.getElementById('duty-options'),query=document.getElementById('duty-query');
 const refresh=()=>{document.getElementById('duty-selected').innerHTML='<h3>当前已选办理人</h3>'+([...selected[kind.value]].map(id=>'<div class="between">'+c.esc(name(id))+'<button type="button" class="btn text" data-duty-remove="'+c.esc(id)+'">移除</button></div>').join('')||'<p class="hint">尚未选择办理人</p>');document.getElementById('duty-summary').innerHTML='<h3 class="mt20">保存前核对全部职责</h3>'+c.table(['职责','配置后的办理人'],Object.entries(selected).map(([key,ids])=>[c.esc(d.labels[key]),[...ids].map(id=>c.esc(name(id))).join('、')||'尚未配置']));};
 const load=async(page=1)=>{const n=++sequence,key=kind.value;box.textContent='正在查找人员…';try{const r=await c.api('/social/duty-options?'+new URLSearchParams({duty:key,q:query.value.trim(),page}));if(!box.isConnected||n!==sequence)return;for(const p of r.items)people.set(p.id,p);box.innerHTML=r.items.map(p=>'<label class="duty-person"><input type="checkbox" data-duty-person="'+c.esc(p.id)+'" '+(selected[key].has(p.id)?'checked ':'')+(p.eligible?'':'disabled')+'><span>'+c.esc(name(p.id))+'<small>'+c.esc(p.staff_no||p.username)+(p.eligible?'':' · 无有效审核身份或范围不符')+'</small></span></label>').join('')||'<p class="hint">没有匹配人员，请换姓名或工号检索。</p>';box.innerHTML+='<div class="flex mt12">'+(r.page>1?'<button type="button" class="btn" data-duty-page="'+(r.page-1)+'">上一页</button>':'')+'<span>共 '+r.total+' 人 · 第 '+r.page+' 页</span>'+(r.page*r.size<r.total?'<button type="button" class="btn" data-duty-page="'+(r.page+1)+'">下一页</button>':'')+'</div>';refresh();}catch(err){if(box.isConnected&&n===sequence)box.textContent='人员读取失败：'+err.message+'；原选择仍保留。'}};
 kind.addEventListener('change',()=>{query.value='';refresh();load()});query.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();load()}});
 form.addEventListener('change',e=>{const id=e.target.dataset.dutyPerson;if(id){if(e.target.checked)selected[kind.value].add(id);else selected[kind.value].delete(id);refresh()}});
 form.addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;if(b.hasAttribute('data-duty-search'))load();if(b.dataset.dutyPage)load(Number(b.dataset.dutyPage));if(b.dataset.dutyRemove){selected[kind.value].delete(b.dataset.dutyRemove);refresh();load()}});
 refresh();await load();
}

export async function socialAction(action,id,c){
 context=c;if(['social-policy-new','social-policy-edit','social-policy-copy','social-policy-recommended','social-claim-new','social-claim-edit','social-annual-new','social-annual-edit','social-correction-new','social-review-new'].includes(action)&&c.refreshPeriods)c.periods=await c.refreshPeriods();if(!workspace||workspaceUser!==c.me?.user?.id){workspace=await c.api('/social/workspace');workspaceUser=c.me?.user?.id}
 if(action==='social-policy-calendar'){const x=opened.item,d=x.data;return commonForm('补充学校工作日历',c.field('calendar_start','校历开始日期','date',d.calendar_start||'')+c.field('calendar_end','校历结束日期','date',d.calendar_end||'')+c.field('calendar_reference','学校工作日历依据','textarea',d.calendar_reference||'')+c.field('holidays','放假日期（每行一个）','textarea',(d.holidays||[]).join('\n'),{required:false})+c.field('workdays','周末补班日期（每行一个）','textarea',(d.workdays||[]).join('\n'),{required:false}),v=>c.api('/social/policies/'+x.id+'/calendar',{method:'PUT',body:{...v,expected_version:x.version,holidays:(v.holidays||'').split(/[\s,，、；;]+/).filter(Boolean),workdays:(v.workdays||'').split(/[\s,，、；;]+/).filter(Boolean)}}),{reopen:true,hint:'依据学校正式校历填写，不自动推算或补默认日期。'})}
 if(action==='social-resource-page'){resourcePage=Number(id);return c.render()}
 if(action==='social-list-page'){listPage=Number(id);return c.render()}
 if(action==='social-list-apply'){listSearch=document.getElementById('social-query').value.trim();listPage=1;resourcePage=1;return c.render()}
 if(action==='social-list-reset'){listSearch='';listPage=1;resourcePage=1;trainingChange(listSection,c,'reset');return c.render()}
 if(action==='social-project-lookup'){
  const choice=projectChoice,sequence=++choice.sequence,target=document.getElementById('social-project-picker'),select=document.getElementById('f-'+projectChoice.name),q=document.getElementById('social-project-query').value.trim(),selected={value:select.value,label:select.selectedOptions[0]?.textContent||''};
  const result=await c.api('/social/project-options?page='+(q===projectChoice.q?id:1)+'&q='+encodeURIComponent(q)+(choice.mine?'&mine=true':''));
  if(choice===projectChoice&&sequence===choice.sequence&&target===document.getElementById('social-project-picker')){projectChoice.q=q;target.innerHTML=projectOptionsHtml(result,selected);document.getElementById('social-project-query').focus()}return;
 }
 if(action==='social-list-search')return c.formModal('检索当前业务列表',c.field('q','名称、编号或状态','text',listSearch,{required:false}),async v=>{listSearch=v.q;listPage=1;c.closeModal();await c.render()},{submit:'查询'});
 if(action==='social-detail'){const[k,i,course,p]=id.split('|');return showDetail(k,i,course?decodeURIComponent(course)+'|'+(p||'1'):null)}
 if(action==='social-print'){
  document.querySelector('.print-sheet')?.remove();const sheet=document.createElement('section');sheet.className='print-sheet';sheet.innerHTML='<h1>社会培训办理材料</h1>'+opened.printBody;document.body.append(sheet);document.body.classList.add('print-mode');try{window.print()}finally{document.body.classList.remove('print-mode')}return;
 }
 if(action==='social-course-import')return commonForm('批量导入培训课程',c.note('从表格复制八列（含表头）：'+COURSE_COLUMNS.join('、')+'。教学方式填'+TEACHING_MODES.map(x=>x[1]).join('/')+'；思政属性填'+IDEOLOGY.map(x=>x[1]).join('/')+'；主讲教师填姓名，重名时写“姓名 工号”；课件审查填“未审查”或“已审查 审查人 2026-09-01”。后五列可留空。先预检，再整批确认。')+c.field('rows','课程清单','textarea',COURSE_COLUMNS.join('\t'),{rows:10,full:true}),async v=>{
  const rows=parseCourseRows(v.rows);
  await importCourses(rows,v,async()=>{await socialAction('social-course-import','',c);for(const key of ['rows','reason','basis'])document.getElementById('f-'+key).value=v[key]||''});
 },{submit:'预检课程清单'});
 if(action==='social-course-chaoxing')return commonForm('超星学习通导出表导入',c.note('在超星学习通课程管理中导出课程列表，选择关联项目后上传 CSV 文件或直接粘贴表格内容。可识别课程名称、课程编号（课程ID）、授课教师、视频数、视频时长、章节数和学习人数；视频时长可为分钟数、时:分:秒，或带“分钟”的数值。',false,'导出表填写说明')+await projectPicker('project_code','code')+c.field('file','上传逗号分隔表格（可不选）','file','',{required:false,accept:'.csv,.txt,.tsv'})+c.field('rows','或粘贴导出表内容（含表头）','textarea','',{rows:10,full:true,required:false}),async(v,f)=>{
  const file=f?.querySelector('input[type=file]')?.files?.[0],text=file?await readImportFile(file):v.rows;
  if(!String(text||'').trim())throw Error('请上传导出文件或粘贴导出表内容');
  const projectLabel=f?.querySelector('#f-project_code')?.selectedOptions[0]?.textContent||v.project_code;
  await importCourses(parseChaoxingCourses(text,v.project_code),v,async()=>{await socialAction('social-course-chaoxing','',c);const select=document.getElementById('f-project_code');if(![...select.options].some(o=>o.value===v.project_code))select.insertAdjacentHTML('beforeend','<option value="'+c.esc(v.project_code)+'">'+c.esc(projectLabel)+'</option>');select.value=v.project_code;for(const [key,value]of Object.entries({rows:text,reason:v.reason,basis:v.basis}))document.getElementById('f-'+key).value=value||''});
 },{submit:'预检课程清单'});
 if(action==='social-policy-recommended'&&!c.periods.some(p=>p.state==='OPEN'))throw Error('没有开放的考核周期，请先由学校管理员新增周期');
 if(action==='social-policy-recommended')return commonForm('一键生成推荐口径草稿',c.note('按系统推荐口径生成名为“推荐口径（待学校书面确认）”的草稿，供试算参考，不会启用。学校书面确认后，在这份草稿上点“登记学校书面依据”填写文号，再办理启用。')+c.field('period_id','适用周期','select','',{options:c.periods.filter(x=>x.state==='OPEN').map(x=>[x.id,x.name])}),v=>c.api('/social/policies/recommended',{method:'POST',body:{period_id:v.period_id,reason:v.reason,basis:v.basis}}),{submit:'生成草稿',after:r=>r?.item?.id?showDetail('social_policy',r.item.id):null});
 if(action==='social-review-new'){
  const x=opened.item,t=opened.trial||{};
  const body=c.note('适用于已归档入账的积分。保存后上传核对材料，再发给教师：教师同意就自动生成更正单走原审批；不同意由学院院长裁定。原认定记录不会被改动。')+c.note('原认定：授课 '+(t.teaching??'—')+' 分，辅助 '+(t.auxiliary??'—')+' 分。')
   +c.field('reason','哪里不对（教师和审批人都会看到）','textarea','',{full:true,hint:'写清哪一项、按什么依据应是多少。'})+c.field('teaching','建议更正：授课积分差额','number',0,{step:0.01,hint:'正数增加、负数扣减；不变填 0'})+c.field('auxiliary','建议更正：辅助积分差额','number',0,{step:0.01})+c.field('period_id','入账周期','select','',{options:c.periods.filter(p=>p.state==='OPEN').map(p=>[p.id,p.name])});
  return commonForm('发起积分核对',body,v=>{if(!Number(v.teaching)&&!Number(v.auxiliary))throw Error('建议更正的授课、辅助积分差额不能都为 0');return c.api('/social/point-reviews',{method:'POST',body:{...v,claim_id:x.id}})},{submit:'保存核对单',reopen:true,after:r=>r?.item?.id?showDetail('social_resource',r.item.id):null,hideReason:true});
 }
 if(['social-correction-new','social-correction-edit'].includes(action)){
  const x=opened.item,edit=action==='social-correction-edit',old=edit?x.data:{};
  const body=c.note('正数增加、负数扣减。须上传正式处理或更正依据，并经过院长、归口、分管副校长审批及教学秘书归档。')+c.field('period_id','入账或更正周期','select',old.period_id||'',{options:c.periods.filter(p=>p.state==='OPEN').map(p=>[p.id,p.name])})+c.field('teaching','授课积分变动','number',old.teaching||0,{step:0.01})+c.field('auxiliary','辅助积分变动','number',old.auxiliary||0,{step:0.01})+c.field('decision_reference','正式处理或更正依据','textarea',old.decision_reference||'');
  return commonForm('追加积分更正',body,v=>c.api('/social/corrections'+(edit?'/'+x.id:''),{method:edit?'PUT':'POST',body:{...v,claim_id:edit?old.claim_id:x.id,...(edit?{expected_version:x.version}:{})}}),{after:r=>r?.item?.id?showDetail('social_resource',r.item.id):null});
 }
 if(action==='social-report-new'){
  const orgs=c.orgs.filter(o=>['school','college'].includes(o.kind));
  const now=new Date(),endMonth=Math.ceil((now.getMonth()+1)/2)*2;
  if(!orgs.length)return c.modal('暂不能生成积分汇总',c.note('当前身份可见范围内没有可汇总的学院或学校，暂不能生成双月汇总或年度公示。请联系学校管理员核对教学秘书职责对应的身份与组织范围；如已配置学院或学校身份，请切换后办理。',true),c.act('返回','close','','primary'),false,'积分汇总公示 / 生成前检查');
  return commonForm('双月汇总与年度公示',c.field('org_id','汇总组织（年度公示选择学校）','select',(orgs.find(o=>o.id===c.me?.user?.org_id)||orgs[0]).id,{options:orgs.map(o=>[o.id,o.name])})+c.field('year','年度','number',now.getFullYear(),{min:2000,max:2200,step:1})+c.field('window','汇总范围','select',`${endMonth-1}-${endMonth}`,{options:[['1-2','1—2月'],['3-4','3—4月'],['5-6','5—6月'],['7-8','7—8月'],['9-10','9—10月'],['11-12','11—12月'],['1-12','年度全校公示']]})+c.field('policy_id','已确认制度与校历','select','',{options:workspace.policies.filter(p=>p.state==='ACTIVE').map(p=>[p.id,p.name])}),v=>{const{window,...data}=v;const[start_month,end_month]=window.split('-').map(Number);return c.api('/social/reports',{method:'POST',body:{...data,start_month,end_month}})},{submit:'生成汇总',after:r=>r?.item?.id?showDetail('social_resource',r.item.id):null});
 }
 if(action==='social-report-info')return reportInfoForm();if(action==='social-prep')return prepForm();
 if(action==='social-report-export'){reportResult=null;return reportModal()}
 if(action==='social-report-check'){const q=readReportRange();reportResult=await c.api('/social/report-export/check?'+q);return reportModal()}
 if(action==='social-report-download'){const q=readReportRange();return c.download('/social/report-export?'+q,'上报表_'+reportRange.start+'_'+reportRange.end+'.xlsx')}
 if(action==='social-project-new')return projectForm();if(action==='social-project-edit')return projectForm(true);if(action==='social-policy-new')return policyForm();if(action==='social-policy-edit')return policyForm(opened.item);if(action==='social-policy-copy')return policyForm(opened.item,true);
 if(action==='social-export'){const[k,i]=id.split('|');return c.download(path(k,i)+'/export','社会培训办理材料.xlsx')}
 if(action==='social-course-resources'){const[code,p='1']=id.split('|'),result=await c.api('/social/courses/'+encodeURIComponent(code)+'/resources?page='+p);return c.modal('课程资源',c.table(['名称','类型','视频时长（分钟）','操作'],result.items.map(r=>[c.esc(r.name),c.esc({video:'视频',document:'文档',link:'其他链接'}[r.data.resource_type]),r.data.duration_minutes??'不适用',c.act('查看详情','social-detail','social_resource|'+r.id+'|'+encodeURIComponent(code)+'|'+p)])),(workspace.courses?.some(x=>x.code===code)?c.act('返回课程资料','social-course-view',code):'')+(result.page>1?c.act('上一页','social-course-resources',code+'|'+(result.page-1)):'')+(result.page*result.size<result.total?c.act('下一页','social-course-resources',code+'|'+(result.page+1)):''))}
 if(action==='social-course-for-project'){const code=opened.item.data.code;return commonForm('登记本项目课程',c.note('课程将关联到本项目（'+code+'）。登记后，参训明细里的“课程编号”填这里的编号。')+c.field('code','课程编号')+c.field('name','课程名称')+courseInfoFields(),v=>c.api('/social/courses',{method:'POST',body:courseInfoValue({...v,project_code:code})}),{submit:'保存课程',reasonLabel:'办理说明',reasonDefault:'登记项目课程',reopen:true})}
 if(action==='social-course-link'){const x=opened.item;return commonForm('关联已入库课程',c.note('复用已经审批入库的课程，保留原申请和审批记录。只可选择承办学院尚未关联项目的课程；已有项目归属的课程不能改挂。')+c.field('course_code','已入库课程编号','text','',{hint:'从培训课程库复制课程编号，确认与本项目教学安排一致。'}),v=>c.api('/social/projects/'+x.id+'/courses/link',{method:'POST',body:{course_code:v.course_code,expected_version:x.version,reason:v.reason,basis:v.basis}}),{submit:'确认关联课程',reasonLabel:'关联说明',reasonDefault:'复用已审批入库课程',reopen:true})}
 if(action==='social-course-view')return courseView(id);
 if(action==='social-deadlines')return deadlinesModal();
 if(action==='social-deadline-edit'){const x=deadlines.items.find(r=>r.school_year===id);return commonForm('调整 '+id+' 学年申报截止日',c.field('deadline','申报截止日','date',x.deadline,{hint:'默认 '+x.default_deadline+'；改回默认日期即恢复默认。'}),v=>c.api('/applications/deadlines',{method:'PUT',body:{school_year:id,deadline:v.deadline,reason:v.reason,basis:v.basis||'',expected_version:deadlines.version}}),{compact:true,submit:'保存截止日',reasonDefault:'按学校通知调整截止日',after:()=>deadlinesModal()})}
 if(action==='social-deadline-reopen'){const x=deadlines.items.find(r=>r.school_year===id),max=new Date(Date.now()+deadlines.reopen_max_days*864e5).toLocaleDateString('sv-SE');return commonForm('开放 '+id+' 学年补报',c.note('只对本院老师开放，补报截止后自动关闭。')+c.field('until','补报截止日','date',x.reopen_until||'',{max,hint:'最晚 '+max+'。'}),v=>c.api('/applications/deadlines/reopen',{method:'PUT',body:{school_year:id,until:v.until,reason:v.reason,basis:v.basis||'',expected_version:deadlines.version}}),{compact:true,submit:'开放补报',reasonDefault:'本院老师补报',after:()=>deadlinesModal()})}
 if(action==='social-deadline-close')return commonForm('关闭 '+id+' 学年补报',c.note('关闭后本院老师不能再申报这个学年的课；已提交的申报照常审批。'),v=>c.api('/applications/deadlines/reopen',{method:'PUT',body:{school_year:id,until:null,reason:v.reason,basis:v.basis||'',expected_version:deadlines.version}}),{compact:true,submit:'关闭补报',reasonDefault:'补报结束',after:()=>deadlinesModal()});
 if(action==='social-course-new')return commonForm('登记培训课程',c.note('学校直接登记的课程不走审批，保存即入库。')+c.field('code','课程编号')+c.field('name','课程名称')+await projectPicker('project_code','code')+courseInfoFields(),v=>c.api('/social/courses',{method:'POST',body:courseInfoValue(v)}),{compact:true,submit:'保存课程'});
 if(['social-resource-new','social-resource-edit'].includes(action)){
  const edit=action==='social-resource-edit',x=edit?opened.item:null,old=x?{...x.data,name:x.name,code:x.code}:{},courseList=edit?opened.courseList:null;id=x?.kind||id;
  const f=(key,label,type='text',options={})=>c.field(key,label,type,old[key]??'',options);
  let body=(x?c.field('org_id','承办学院','select',x.org_id,{options:[[x.org_id,c.orgName(x.org_id)]]}):collegeField())+f('code','来源唯一编号','text',{readonly:edit})+f('name','名称')+f('location','地点或资源说明','textarea',{required:false})+f('recognition','认定或登记依据','textarea');
  if(id==='base'){const used=new Set(old.usages||[]);body+=c.field('onsite','基地类型','checkbox',old.onsite??true,{checkLabel:'校内基地（不勾选表示校外）'})+'<fieldset class="form-field full apply-tags"><legend>基地用途（可多选）</legend><div class="apply-tag-row">'+BASE_USAGE_OPTIONS.map(([k,l])=>'<label><input type="checkbox" name="usage_'+k+'"'+(used.has(k)?' checked':'')+'>'+c.esc(l)+'</label>').join('')+'</div></fieldset>'+c.field('level','基地级别','select',old.level||'school',{options:BASE_LEVEL_OPTIONS})+f('established_on','设立日期','date',{required:false})+f('partner','共建单位','text',{required:false,hint:'校外基地必填。'});}
  if(id==='achievement')body+=c.field('level','成果等级','select',old.level||'school',{options:selectable(['national','province','school'])})+f('confirmed_on','成果正式认定日期','date',{required:false,hint:'日期待补时，不计年度分数'});
  if(id==='course_resource')body+=c.field('course_code','关联课程','select',old.course_code||'',{options:[['','请选择关联课程'],...(old.course_code?[[old.course_code,'原关联课程 · '+old.course_code]]:[])]})+c.field('resource_type','资源类型','select',old.resource_type||'video',{options:[['video','视频'],['document','文档'],['link','其他链接']]})+f('resource_url','资源地址','url',{required:false})+f('duration_minutes','视频总时长（分钟）','number',{required:false,min:0,step:0.01})+c.field('teacher_id','归属教师及工号','select',old.teacher_id||'',{required:false,options:[['','尚未确认人员'],...(old.teacher_id?[[old.teacher_id,'原关联教师（保留）']]:[])]})+'<p id="course-resource-status" class="hint full" role="status"></p>';
  commonForm((edit?'修改':'登记')+{base:'培训基地',achievement:'培训成果',course_resource:'课程资源'}[id],body,raw=>{const v=resourceFormValue(id,raw);return c.api('/social/resources'+(x?'/'+x.id:''),{method:x?'PUT':'POST',body:{...v,kind:id,...(x?{expected_version:x.version}:{}),resource_url:v.resource_url||null,confirmed_on:v.confirmed_on||null,teacher_id:v.teacher_id||null}})},{compact:!edit,reopen:edit,submit:edit?'保存修改':'保存登记',after:r=>r?.item?.id?showDetail('social_resource',r.item.id,courseList):null});
  if(id==='course_resource')return bindCourseResourceFields(c,old);return;
 }
 if(['social-claim-new','social-claim-edit'].includes(action)){
  const x=action==='social-claim-edit'?opened.item:null,existing=x?(opened.attachments||[]):[];
  const policies=workspace.policies||[],auxRow=(r={})=>'<div class="aux-row"><input type="date" class="aux-date" aria-label="工作日期" value="'+c.esc(r.work_date||'')+'"><input type="number" class="aux-amount" aria-label="辅助积分" min="0" step="0.01" placeholder="积分" value="'+c.esc(r.amount??'')+'"><input class="aux-desc" aria-label="工作说明" maxlength="200" placeholder="做了什么辅助工作" value="'+c.esc(r.description||'')+'"><button type="button" class="btn text aux-del" aria-label="删除这一行">删除</button></div>';
  const picker=x?'':await projectPicker('project_id','id',true);
  // 没有可申报项目或学校还没登记口径时，只说明原因，不再弹出一整张填不了的表。
  if(!x&&(!projectChoice.total||!policies.length))return c.modal('本人积分申报','<div class="social-detail">'+c.note(!policies.length?'学校还没有登记积分认定口径，暂时不能申报。请联系学校社会培训管理员。':'你还没有可申报的项目。项目须由学院办完结项，且“参训明细”里登记了你的工号（授课或辅助）。项目还在办理中的，等学院结项后再来申报；如有遗漏，请联系学院补录参训明细。',true)+'</div>',c.act('知道了','close','','primary'));
  // 补正一次办完：退回原因、原填写内容和已有材料集中显示，只改需要补正的地方。
  const lastReturn=x?[...(opened.events||[])].reverse().find(e=>/退回/.test(e.action)):null;
  const recap=x?formSection('退回意见与已有材料',(x.state==='RETURNED'?c.note('退回意见：'+(lastReturn?.reason||'请核对办理记录后补正。'),true):'')+'<div class="form-field full"><label>已有材料（保留，不用重传）</label>'+(existing.length&&c.downloads?c.downloads(existing):'<p class="hint">尚未上传材料</p>')+'</div>','原来正确的内容和材料都会保留，只改需要补正的地方。'):'';
  const files='<div class="form-field full"><label for="f-file">'+(x?'补充材料（可一次选多份，没有可不选）':'学校制式积分认定表及其他材料（可一次选多份） <b>*</b>')+'</label><input type="file" id="f-file" name="file" multiple accept=".pdf,.png,.jpg,.jpeg"'+(x?'':' required')+'><p class="hint">支持 .jpg、.png、.pdf，单个文件最大 10 兆字节；每份单独上传并显示结果，失败的只需补传那一份。单个申报最多 '+MAX_ATTACHMENTS+' 份。</p><div id="upload-progress"></div></div>';
  const teacher=c.me.role.kind==='teacher';
  let body=recap+formSection('项目与认定周期',(x?'':picker)+policyFields(x,true)) +formSection('积分认定材料',(x?c.field('recognition_form_reference','学校制式积分认定表及附件对应说明','textarea',x?.data.recognition_form_reference||'',{hint:'写明认定表编号或附件名称。'}):'')+files)+formSection('辅助工作积分',
   '<div class="form-field full"><label>辅助工作积分（没有可不填）</label><div id="aux-rows" class="aux-rows">'+(x?.data.auxiliary||[]).map(auxRow).join('')+'</div><button type="button" class="btn light sm" id="aux-add">＋ 添加一行辅助工作</button><p class="hint">每行一项：日期、积分、工作说明。授课积分按参训明细自动核算，不用在这里填。</p></div>');
  setTimeout(()=>{const box=typeof document!=='undefined'&&document.getElementById('aux-rows');if(!box)return;document.getElementById('aux-add')?.addEventListener('click',()=>{box.insertAdjacentHTML('beforeend',auxRow());box.lastElementChild.querySelector('input')?.focus()});box.addEventListener('click',e=>{if(e.target.closest('.aux-del'))e.target.closest('.aux-row').remove()});for(const id of ['f-period_id','f-policy_id']){const el=document.getElementById(id);if(el&&el.options.length===1)el.value=el.options[0].value}},0);
  if(!teacher)body+=c.field('submit_now','提交方式','checkbox',true,{required:false,checkLabel:x?'保存补正后直接重新提交（不勾选则只保存，不提交）':'保存后直接提交审批（不勾选则先存为草稿）',full:true});
  return commonForm(x?'补正本人积分':'本人积分申报',body,async(v,f,button)=>{const{auxiliary_rows='',file:_file,submit_now:legacySubmit,...data}=v;const submit_now=teacher&&button?button.value==='submit':legacySubmit;const chosen=[...(f?.querySelector('#f-file')?.files||[])];if(!x&&!chosen.length)throw Error('请选择积分认定表的照片或扫描件');checkUploadFiles(chosen,existing.length);if(!x&&!data.recognition_form_reference)data.recognition_form_reference=chosen.map(file=>file.name).join('、').slice(0,500);const domRows=f?[...f.querySelectorAll('.aux-row')].map((r,i)=>({work_date:r.querySelector('.aux-date').value,amount:r.querySelector('.aux-amount').value,description:r.querySelector('.aux-desc').value.trim(),row:i+1})).filter(r=>r.work_date||r.amount||r.description):null;const auxiliary=domRows?domRows.map(({row,...r})=>{if(!r.work_date||r.amount===''||!r.description)throw Error('辅助工作第'+row+'行的日期、积分、说明都要填写；不需要的行请删除');return r}):auxiliary_rows.trim()?auxiliary_rows.trim().split(/\r?\n/).map(line=>{const[work_date,amount,description,...extra]=line.split('\t');if(!description||extra.length)throw Error('辅助工作每行须为日期、积分、说明三列');return {work_date,amount,description}}):[];const r=await c.api('/social/claims'+(x?'/'+x.id:''),{method:x?'PUT':'POST',body:{...data,...(x?{project_id:x.project_id,expected_version:x.version}:{}),auxiliary}});if(!r?.item?.id)return r;
   // 一次办完：保存（或补正）→ 逐份上传材料 → 提交。任何一步没完成都如实说明“已保存、未提交”，绝不报成功。
   const id=r.item.id,pkey='social_claim|'+id,saved=x?'补正已保存':'申报已存为草稿',box=f?.querySelector?.('#upload-progress'),show=list=>{if(box)box.innerHTML=uploadStatusHtml(list,c.esc)},submitReason=data.reason||(x?'补正后重新提交':'提交本人积分申报');let version=r.item.version;
   if(chosen.length){const entries=uploadEntries(chosen),reason=x?'补正时补充材料':'本人上传积分认定表',result=await uploadSequential({api:c.api,kind:'social_claim',id,version,entries,reason,latest:()=>latestOf('social_claim',id),onProgress:show});version=result.version;
    if(result.failed.length){pendingUploads.set(pkey,{entries,reason,then:submit_now?'submit':'',submitReason,basis:data.basis||''});const msg=saved+'，'+(entries.length-result.failed.length)+' 份材料已上传，'+result.failed.length+' 份没有传上去'+(submit_now?'，尚未提交':'')+'。请在详情里只补传失败的材料。';outcomeNotes.set(pkey,msg);c.toast(msg,true);return r}}
   if(!submit_now){c.toast(x?'补正已保存，尚未提交；确认无误后在详情里提交':'已保存草稿，可在详情里提交');return r}
   try{await c.api('/social/claims/'+id+'/actions',{method:'POST',body:{action:'submit',expected_version:version,reason:submitReason,basis:data.basis||''}});c.toast(x?'补正已保存并重新提交审批':'已提交审批，院长初审后会继续往下走')}
   catch(err){const msg=notSubmitted(saved,err);outcomeNotes.set(pkey,msg);c.toast(msg,true)}
   return r},{...(x?{reopen:true,submit:'保存补正并重新提交',reasonLabel:'补正说明',reasonDefault:'按退回意见补正'}:{submit:'申报',reasonLabel:'申报说明',reasonDefault:'申报本人社会培训积分',compact:true,hint:'选项目、拍认定表、点“申报”就办完了；说明已预填，可不改。',after:r=>r?.item?.id?showDetail('social_claim',r.item.id):null}),...(teacher?{page:true,compact:false,draft:x?'仅保存补正':'保存草稿',submit:x?'保存补正并重新提交':'提交审核',contextLabel:'个人培训 / 本人积分 / '+(x?'补正资料':'新增申报'),hint:x?'已有材料会保留。仅保存补正不会提交审核；核对无误后再重新提交。':'新申报须先选择认定表材料。保存草稿会保存内容和材料，提交审核才进入办理流程。'}:{})});
 }
 if(['social-annual-new','social-annual-edit'].includes(action)){
  const x=action==='social-annual-edit'?opened.item:null,old=x?.data||{};
  const n=(key,label)=>c.field(key,label,'number',old[key]??'',{required:false,min:0,step:key==='other_bonus'?0.01:1}),t=(key,label,required=false)=>c.field(key,label,'textarea',old[key]||'',{required,full:true});
  let body=formSection('一、学院与认定周期',(x?c.note('保留当前学院和周期，补正后重新提交。'):collegeField())+policyFields(x))
   +formSection('二、年度任务与自评',n('income_target','到账收入目标')+n('participants_target','有效人次目标')+n('priority_target','重点群体人次目标')+n('staff_denominator','组织人数基准')+t('target_reference','年度任务下达依据',true)+t('staff_basis','组织人数依据')+t('self_report','单位自评报告',true))
   +formSection('三、加分与合规事项',n('other_bonus','其他加分')+t('other_bonus_basis','其他加分依据')+n('compliance_failures','其他已确认不合规次数（不含项目结算核验）')+t('discipline_reference','正式处理或处分依据')+c.field('confirmed_veto','一票否决','checkbox',old.confirmed_veto||false,{checkLabel:'已取得正式处理依据，确认一票否决'}),'没有加分或其他不合规事项可留空；项目结算问题不在这里重复登记。');
  return commonForm('学院年度自评',body,v=>{let{org_id,period_id,policy_id,reason,basis,...data}=v;if(x){org_id=x.org_id;period_id=x.period_id}data={...data,compliance_scope:'other_only',compliance_failures:data.compliance_failures??0,other_bonus:data.other_bonus??0};return c.api('/social/annuals'+(x?'/'+x.id:''),{method:x?'PUT':'POST',body:{org_id,period_id,policy_id,reason,basis,...(x?{expected_version:x.version}:{}),data}})},x?{reopen:true,page:c.me?.role?.kind==='college'}:{page:c.me?.role?.kind==='college',submit:'保存自评',hint:'保存后会打开自评，上传自评材料后点“提交学院自评”。',after:r=>r?.item?.id?showDetail('social_annual',r.item.id):null});
 }
 if(action==='social-transition'){
  if(id==='refresh'&&opened.kind==='social_resource'&&opened.item.kind==='point_report'){
   const x=opened.item;
   return commonForm('重新取数并保存草稿',c.note('按原组织、年度和月份重新读取最新已归档积分。原汇总快照留在办理记录中，本次仅保存草稿；核对后须再次明确提交并由独立归口复核，不会自动报送或公示。'),v=>c.api('/social/reports/'+x.id+'/actions',{method:'POST',body:{...v,expected_version:x.version,action:'refresh'}}),{submit:'确认重新取数并保存草稿',reasonLabel:'重新取数原因',reasonDefault:'',reopen:true});
  }
  if(id==='submit'&&opened.kind==='social_project'&&(opened.report_issues||[]).length)return c.modal('提交前请先补齐项目资料',c.note(opened.report_issues.join('；'),true),c.act('返回详情','social-detail',opened.kind+'|'+opened.id)+c.act('去补齐项目资料','social-project-edit','','primary'));

  if(id==='submit'&&opened.item.kind!=='point_report'&&!(opened.attachments||[]).length&&c.can('file.write'))return c.modal('先补充佐证材料',c.note('上传项目或申报材料后，再提交审核。',true),c.act('返回详情','social-detail',opened.kind+'|'+opened.id)+c.act('上传佐证','social-upload','','primary'));
  const x=opened.item,label=opened.labels?.[id]||'办理确认',back=['return','college_return','refile','dispute','explain','dismiss','withdraw','void'].includes(id),reasons={college_return:'',submit:'材料已备齐，提交审核',approve:'审核通过',file:'材料齐全，同意备案',close:'结项材料核验通过',archive:'公示期满，予以归档',activate:'按学校书面确认启用',record_basis:'登记学校书面确认依据',send:'核对材料已上传，请老师核对回应',agree:'同意按核对意见更正',uphold:'经核实确有错误，按核对意见更正',publish:'委员会评分完成',finance:'财务核验通过',academic:'成果核验通过',discipline:'纪检核验无异议',coordinator:'归口初核通过'};return commonForm(label,(id==='submit'&&(opened.trial?.blockers||[]).length?c.note('系统检查发现以下问题，提交会被拦下，请先处理：'+opened.trial.blockers.join('；'),true):'')+(['submit','activate','send'].includes(id)&&x.kind!=='point_report'&&!(opened.attachments||[]).length?c.note('还没有上传佐证材料，这一步会被系统拦下。请点“返回详情”，先“上传佐证”，再来办理。',true):'')+(id==='archive'&&(x.snapshot?.public_end||x.data?.public_end)?c.note('公示截止：'+(x.snapshot?.public_end||x.data.public_end)+'。满5个完整工作日且异议处理完毕后才能归档。',true):'')+c.note('当前状态：'+opened.state_label+(back?'。请写清原因，对方会看到这段说明。':''))+(id==='file'&&(x.data.category==='subsidy'||x.data.high_risk)?c.field('prior_review_on','正式前置审核日期','date'):''),async v=>{const route=routeOf(opened.kind,x);await c.api('/social/'+route+'/'+x.id+'/actions',{method:'POST',body:{...v,expected_version:x.version,action:id}})},{submit:(/^确认/.test(label)?'':'确认')+label.replace(/（.*$/,''),reasonLabel:back?({return:'退回原因（告诉对方要补什么）',explain:'说明情况（学院院长会看到）',dismiss:'维持原认定的理由（双方都会看到）',withdraw:'撤回原因',void:'作废原因（原认定保留，重新核对须再次取得确认）'}[id]||'说明'):'办理意见',reasonDefault:(id==='archive'&&(x.snapshot?.public_end||x.data?.public_end)?'核对公示期限及异议处理结果，申请归档':id==='approve'&&opened.archiveStep?'审核材料齐全，归档入账':reasons[id])||'',reopen:true,...(id==='record_basis'?{basisLabel:'学校书面依据文号',basisRequired:true}:id==='resolve'?{basisLabel:'异议核实结论与依据',basisRequired:true}:id==='file'&&(x.data.category==='subsidy'||x.data.high_risk)?{basisLabel:'前置审核依据',basisRequired:true}:{})});
 }
 if(action==='social-upload'){
  const x=opened.item,k=opened.kind,existing=(opened.attachments||[]).length;
  return commonForm('上传社会培训佐证','<div class="form-field full"><label for="f-file">选择佐证文件（可一次选多份） <b>*</b></label><input type="file" id="f-file" name="file" multiple required accept=".pdf,.png,.jpg,.jpeg"><p class="hint">支持 .jpg、.png、.pdf，单个文件最大 10 兆字节。每份单独上传并显示结果，失败的只需补传那一份。已有 '+existing+' 份，单个业务最多 '+MAX_ATTACHMENTS+' 份。</p><div id="upload-progress"></div></div>',async(v,f)=>{
   const chosen=checkUploadFiles([...(f?.querySelector('#f-file')?.files||[])],existing);if(!chosen.length)throw Error('请选择要上传的佐证文件');
   const box=f?.querySelector?.('#upload-progress'),entries=uploadEntries(chosen),result=await uploadSequential({api:c.api,kind:k,id:x.id,version:x.version,entries,reason:v.reason,latest:()=>latestOf(k,x.id),onProgress:list=>{if(box)box.innerHTML=uploadStatusHtml(list,c.esc)}});
   if(result.failed.length){const pkey=k+'|'+x.id,msg=(entries.length-result.failed.length)+' 份材料已上传，'+result.failed.length+' 份没有传上去。请在详情里只补传失败的材料。';pendingUploads.set(pkey,{entries,reason:v.reason,then:''});outcomeNotes.set(pkey,msg);c.toast(msg,true)}
   else c.toast('已上传 '+entries.length+' 份材料');
  },{submit:'上传',reasonLabel:'材料说明',reasonDefault:'补充佐证材料',reopen:true});
 }
 // 只补传上次失败的那几份，已上传的不重复上传；原本选择“保存并提交”的，补传齐后接着提交。
 if(action==='social-materials'){if(typeof document!=='undefined')document.getElementById('social-materials')?.scrollIntoView({behavior:'smooth',block:'start'});return}
 if(action==='social-next'){const next=c.queueNext?.(opened.kind+'|'+opened.id);if(!next){c.toast('已经是当前列表的最后一条');return}return c.openNext(next)}
 // 在办理区直接办理：用本人确认的意见调用原单条接口；后端照常校验职责、回避、版本和来源变化。
 if(action==='social-handle'){
  const x=opened.item,k=opened.kind,label=opened.labels?.approve||'审核通过',reason=domValue('handle-reason'),basis=domValue('handle-basis'),next=id==='approve-next'?c.queueNext?.(k+'|'+x.id):'';
  const box=typeof document!=='undefined'?document.getElementById('handle-error'):null,controls=typeof document!=='undefined'?[...document.querySelectorAll('.social-handle-actions button')]:[];
  try{if(reason.length<2)throw Error('请填写办理意见');controls.forEach(b=>b.disabled=true);await c.api('/social/'+routeOf(k,x)+'/'+x.id+'/actions',{method:'POST',body:{action:'approve',expected_version:x.version,reason,basis}})}
  catch(err){controls.forEach(b=>b.disabled=false);if(box){box.innerHTML='<div class="error-text">'+c.esc(err.message)+'</div>';box.focus?.();return}throw err}
  await (c.renderKeep||c.render)();
  if(next){c.toast(label+'已办理，已打开下一条，请核对后再办理');return c.openNext(next)}
  c.toast(label+'已办理');return showDetail(k,x.id);
 }
 if(action==='social-upload-retry'){
  const k=opened.kind,x=opened.item,pkey=k+'|'+x.id,pending=pendingUploads.get(pkey);if(!pending)return showDetail(k,x.id);
  const fresh=await latestOf(k,x.id);checkUploadFiles(failedEntries(pending.entries).map(e=>e.file),fresh.attachments.length);
  const result=await uploadSequential({api:c.api,kind:k,id:x.id,version:fresh.version,entries:pending.entries,reason:pending.reason,latest:()=>latestOf(k,x.id)});
  if(result.failed.length){const msg='仍有 '+result.failed.length+' 份没有传上去，已上传的不会重复上传；请检查文件或网络后再补传'+(pending.then==='submit'?'，申报尚未提交':'')+'。';outcomeNotes.set(pkey,msg);c.toast(msg,true);return showDetail(k,x.id)}
  pendingUploads.delete(pkey);
  if(pending.then==='submit'){try{await c.api('/social/'+routeOf(k,x)+'/'+x.id+'/actions',{method:'POST',body:{action:'submit',expected_version:result.version,reason:pending.submitReason||'提交审核',basis:pending.basis||''}});c.toast('材料已补齐并提交审批')}catch(err){const msg=notSubmitted('材料已补齐',err);outcomeNotes.set(pkey,msg);c.toast(msg,true)}}
  else c.toast('失败的材料已补传完成');
  await c.render();return showDetail(k,x.id);
 }
 if(action==='social-close'){
  const old=opened.item.closeout||{},f=(key,label,type='text',value='',opts={})=>c.field(key,label,type,old[key]??value,opts);
  const subsidy=opened.item.data.category==='subsidy',wrap=(id,html)=>'<div class="social-cond" id="cond-'+id+'" style="display:contents">'+html+'</div>';
  let body=(!(opened.attachments||[]).length?c.note('还没有上传结项佐证材料，提交会被系统拦下。请点“返回详情”，先“上传佐证”（签到表、成果报告、财务凭证等）。',true):'')+formSection('一、结项情况',f('closed_on','结项日期','date')+f('satisfaction','满意度（百分比）','number','',{min:0,max:100,step:0.01})+f('location','培训地点类型','select','onsite',{options:[['onsite','校内'],['offsite','校外']]})+f('outcome_report','成果报告','textarea','',{full:true})+wrap('rect','<p class="full hint">满意度低于85%时，请填写整改信息。</p>'+f('rectification','整改报告与期限','textarea','',{required:false})+f('rectification_due','整改办理期限','date','',{required:false})))
   +formSection('二、经费与财务核验',f('actual_income','财务确认到账收入（元）','number',0,{min:0,step:0.01})+f('funding_source','财务确认的资金来源','select','',{required:false,options:[['','请确认资金来源（非零收入必填）'],['other_training','其他培训收入'],['government_special','政府专项培训资金']]})+f('finance_reference','财务核验凭据')+f('implicit_cost','隐性成本（元）','number',0,{min:0,step:0.01})+f('settlement_on','经费结算日期','date','',{required:false})
    +wrap('split',f('retained','学校留存（元）','number','',{min:0,step:0.01,required:false})+f('personnel','校内人员支出（元）','number','',{min:0,step:0.01,required:false})+'<p class="hint full" id="close-split-hint"></p>')
    +wrap('special',f('funding_basis','政府专项主管部门规定及财务核验依据','textarea','',{required:false,full:true,hint:'专项资金有收入时必填；按主管部门规定专款专用，不套用其他收入比例'})),'其他培训收入分配：校内留存不低于20%、人员支出不高于60%；校外留存不低于10%、人员支出不高于70%；项目公用20%。非零其他收入两项金额必填，零收入可留空。政府专项按主管部门规定核验。')
   +(subsidy?formSection('三、补贴项目专项材料',f('province_receipt','省平台报送凭证','textarea','',{required:false})+f('special_evidence','专项参训与成果材料','textarea','',{required:false}),'补贴性培训须登记省平台报送凭证和专项材料，否则结项核验不能通过。'):'')

   +formSection('结项材料核对','<div class="form-field full"><label class="flex" style="gap:8px;font-weight:600"><input type="checkbox" id="close-check-all">以下材料全部已核对</label></div>'+Object.entries({plan:'培训方案',filing_form:'学校制式备案登记表',roster:'学员名册',attendance:'实名签到',hours:'学时记录',process:'培训过程影像',assessment:'结业考核',outcomes:'培训成果',...(opened.item.data.quality?{teacher_review:'主讲教师资格审查表',courseware_review:'课件内容审查记录'}:{})}).map(([k,l])=>f('checked_'+k,l,'checkbox',(old.materials_checked||[]).includes(k),{checkLabel:'已核对'})).join(''),'逐项对照纸质或电子材料核对后勾选。');
  setTimeout(()=>bindCloseForm(),0);
  return commonForm('提交项目结项',body,v=>{const{reason,basis,...raw}=v;const materials_checked=Object.keys(raw).filter(k=>k.startsWith('checked_')&&raw[k]).map(k=>k.slice(8));for(const k of Object.keys(raw))if(k.startsWith('checked_'))delete raw[k];raw.materials_checked=materials_checked;raw.funding_source=raw.funding_source||null;raw.rectification_due=raw.rectification_due||null;for(const k of ['retained','personnel'])if(raw[k]===''||raw[k]==null)delete raw[k];return c.api('/social/projects/'+opened.id+'/actions',{method:'POST',body:{reason,basis,expected_version:opened.item.version,action:'close_submit',closeout:{...raw,settlement_on:raw.settlement_on||null}}})},{reopen:true,page:c.me?.role?.kind==='college',submit:'提交结项核验',reasonLabel:'办理说明',reasonDefault:'项目已完成，提交结项核验'});
 }

 if(action==='social-unit-import'){
  const header='单元编号\t课程编号\t班级编号\t模块名称\t培训日期\t学员编号\t本校全日制生\t准毕业生例外\t实名签到\t学时达标\t全程参训\t结业通过\t重点群体\t剔除原因\t教师工号\t岗位\t人员类型\t佐证说明';
  const code=opened.item.data.code,list=await c.api('/social/workspace?section=courses&q='+encodeURIComponent(code)).then(w=>(w.courses?.items||w.courses||[]).filter(x=>x.project_code===code)).catch(()=>[]);
  setTimeout(()=>typeof document!=='undefined'&&document.getElementById('unit-template')?.addEventListener('click',()=>{const sample=['U001','C001','B01','模块一','2026-09-10','S0001','否','否','是','是','是','是','否','','J001','主讲','校内','签到表第1页'];const blob=new Blob(['\ufeff'+header.split('\t').join(',')+'\r\n'+sample.join(',')+'\r\n'],{type:'text/csv;charset=utf-8'}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='参训明细导入模板.csv';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),5000)}),0);
  const courseNote=list.length?c.note('本项目已登记课程（“课程编号”列填这些编号）：'+list.map(x=>x.code+' '+x.name).join('；')):c.note('本项目还没有登记课程，参训明细里的课程编号无处关联。请先点下面“返回详情”，再点“登记本项目课程”（学院点“申请本项目课程”，学校审批后入库）。',true);
  return commonForm('导入参训明细',courseNote+c.note('三步完成：①下载模板，用 Excel 打开，删掉示例行后按行填写（每位学员每个单元一行）；②另存为 CSV 后在下面选择文件，或直接从 Excel 复制整表粘贴；③先预检，确认人数无误后再入库。判断项填“是/否”，学员编号用学校内部编号，不填身份证号；同一项目同一学员跨班仍须用同一编号，人天式同一天只计一次。',false,'填写与计数说明')+'<div class="form-field full"><button type="button" class="btn light" id="unit-template">下载导入模板</button><p class="hint">岗位填：主讲 / 实训指导 / 管理辅助；人员类型填：校内 / 外聘。多人同堂使用相同单元编号。</p></div>'+c.field('file','选择填好的逗号分隔表格','file','',{required:false,accept:'.csv,.txt,.tsv'})+c.field('rows','或粘贴电子表格内容（含表头）','textarea',header,{rows:8,full:true,required:false}),async(v,f)=>{
   const file=f?.querySelector('input[type=file]')?.files?.[0],text=file?await readImportFile(file):v.rows;
   const projectId=opened.id,project=opened.item,rows=parseTrainingRows(text,project.data.mode,c.teachers),body={rows,expected_version:project.version,reason:v.reason,basis:v.basis};const preview=await c.api('/social/projects/'+projectId+'/units/preview',{method:'POST',body});
   setTimeout(()=>c.formModal('确认参训明细入库','<div class="detail-action-context"><span>本次导入项目</span><strong>'+c.esc(project.data.name)+'</strong><p>'+c.esc(project.data.code)+' · '+c.esc(project.cohort||'')+'</p></div>'+c.note('预检通过：'+preview.rows+'个核算单元，有效'+preview.effective+'人次，剔除'+preview.excluded+'人次。'),async()=>{await c.api('/social/projects/'+projectId+'/units/confirm',{method:'POST',body:{...body,preview_hash:preview.preview_hash}});c.closeModal();await c.render();await showDetail('social_project',projectId).catch(()=>{})},{submit:'确认整批入库',returnLabel:'返回修改',returnTo:async()=>{await socialAction('social-unit-import','',c);for(const [key,value]of Object.entries({rows:text,reason:v.reason,basis:v.basis})){const el=document.getElementById('f-'+key);if(el)el.value=value||''}}}),0);
  },{submit:'先预检',reasonLabel:'办理说明',reasonDefault:'导入参训明细',reopen:true,after:()=>{}});
 }
 if(action==='social-duties'){
  return dutiesForm();
 }
 if(action==='social-note'){
  const finance=workspace.my_duties.includes('finance'),coordinator=workspace.my_duties.includes('coordinator'),discipline=workspace.my_duties.includes('discipline');
  const kinds=[...(coordinator?[['complaint','投诉'],['rectification','整改'],['settlement','结算']]:finance?[['settlement','结算']]:[]),...(discipline?[['violation','登记正式处理决定']]:[])];
  return commonForm('投诉与项目跟踪',c.field('case_reference','跟踪事项编号（再次办理使用相同编号）')+c.field('due_on','整改或结算办理期限','date','',{required:false})+c.field('kind','跟踪类型','select',kinds[0]?.[0]||'',{options:kinds})+(finance?c.field('settlement_result','结算财务核验结论（仅结算事项填写）','select','',{required:false,options:[['','待核验／不适用'],['noncompliant','确认不合规，计入结算扣分'],['exempt','已有正式批准的例外，本次不扣分']],hint:'认定须在下方填写财务核验或例外批准依据；同一项目结算不要重复填入年度其他不合规次数。'}):'')+(workspace.my_duties.includes('discipline')?c.field('invalidate_cohort','正式决定作废本期人次','checkbox',false)+c.field('annual_veto','正式决定触发学院年度否决','checkbox',false):'')+c.field('received_on','受理日期','date')+c.field('investigation_on','开始调查日期','date','',{required:false})+c.field('completed_on','办结日期','date','',{required:false})+c.field('major','重大投诉','checkbox',false)+c.field('reply','书面回复','textarea','',{required:false})+c.field('policy_id','已确认工作日历','select','',{options:workspace.policies.filter(p=>p.state==='ACTIVE').map(p=>[p.id,p.name])}),v=>c.api('/social/projects/'+opened.id+'/notes',{method:'POST',body:{...v,settlement_result:v.settlement_result||null,due_on:v.due_on||null,investigation_on:v.investigation_on||null,completed_on:v.completed_on||null,expected_version:opened.item.version}}),{reopen:true});
 }
}

