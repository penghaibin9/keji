// School business pages reuse the portal's forms, permissions, navigation and attachments.
const names={module:'模块式',person_day:'人天式',technical:'技术类',lecture:'讲座类',province:'省级',city:'市级或企业定制',school:'校级',dispatched:'统一委派异地送教',full_day:'全天实操或脱产',ordinary:'常规',subsidy:'补贴性培训',enterprise:'企业定制培训',community:'社区公益培训',rural:'乡村帮扶培训',other:'其他非学历培训',national:'国家级'};
let workspace,context,opened,workspaceUser;
let listSection='',listPage=1,listSearch='',resourcePage=1;
let projectChoice;
const path=(kind,id)=>'/social/objects/'+kind+'/'+id;
const REVIEW_STATES={DRAFT:'待发送教师',TEACHER:'待教师回应',COLLEGE:'待学院裁定',CLOSED:'已办结'};
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

export async function socialPage(section,c){
 context=c;if(listSection!==section){listPage=1;listSearch='';resourcePage=1;listSection=section}workspace=await c.api('/social/workspace?section='+section+'&page='+listPage+'&q='+encodeURIComponent(listSearch)+'&resource_page='+resourcePage);workspaceUser=c.me?.user?.id;const {esc,act,table,note,pageHead}=c;
 // 教研室负责人在业务办理里只读：项目由学院申报、学校备案，课程和基地由学院登记（后端同样拒绝写入）。
 const can=p=>c.can(p)&&!(p==='records.write'&&c.me?.role?.kind==='dept'&&['projects','courses','bases','outcomes'].includes(section));
 const buttons=[];
 if(section==='projects'&&can('records.write'))buttons.push(act('申报培训项目','social-project-new','','primary'));
 if(section==='courses'&&can('records.write'))buttons.push(act('登记培训课程','social-course-new','','primary'),act('批量导入课程','social-course-import'),act('超星学习通导出表导入','social-course-chaoxing'),act('登记课程资源','social-resource-new','course_resource'));
 if(['bases','outcomes'].includes(section)&&can('records.write'))buttons.push(act(section==='bases'?'登记培训基地':'登记培训成果','social-resource-new',section==='bases'?'base':'achievement','primary'));
 if(section==='recognition'&&c.me.user.staff_no)buttons.push(act('申报本人积分','social-claim-new','','primary'));
 if(section==='recognition'&&workspace.my_duties.includes('secretary'))buttons.push(act('生成双月汇总或年度公示','social-report-new'));
 if(section==='annual'&&can('assessment.review')&&['school','college'].includes(c.me?.role?.kind))buttons.push(act('建立学院年度自评','social-annual-new','','primary'));
 if(['projects','recognition','annual'].includes(section)&&can('assessment.review')&&(workspace.my_duties.length||c.me.role.kind==='school'))buttons.push(act('利益冲突申报与回避','tz-conflicts'));
 if(section==='policy'&&can('rules.manage'))buttons.push(act('新建制度口径版本','social-policy-new','','primary'),act('一键生成推荐口径草稿','social-policy-recommended'));
 if(section==='policy'&&can('roles.manage')&&c.me.user.is_admin)buttons.push(act('配置审批职责','social-duties'));
 let rows=[],headers=[],description='';
 const detail=(kind,id)=>act(['teacher','dept'].includes(c.me?.role?.kind)&&['projects','courses','bases','outcomes'].includes(section)?'查看':'查看与办理','social-detail',kind+'|'+id,'text');
 if(section==='projects'){description='从项目申报到备案结项，让每一次培训有据可查。';headers=['项目名称 / 编号','期次','核算方式','办理状态','操作'];rows=workspace.projects.map(x=>[identity(x.data.name,x.data.code,'book'),esc(x.cohort),esc(names[x.data.mode])+(x.data.source?.mode_pending?'（待核实）':''),statusBadge(x.state_label||workspace.states[x.state],x.state),detail('social_project',x.id)])}
 if(section==='courses'){description='集中管理培训课程、视频与教学资源，清楚掌握资源数量和视频时长。';headers=['课程名称 / 编号','关联项目','资源数','视频数','视频时长（分钟）','操作'];rows=workspace.courses.map(x=>{const stats=workspace.course_stats[x.code]||{resources:0,videos:0,minutes:0};return [identity(x.name,x.code,'book'),esc(x.project_code||'待关联'),stats.resources,stats.videos,esc(stats.minutes),act('查看资源','social-course-resources',x.code,'text')]})}
 if(['bases','outcomes'].includes(section)){description=section==='bases'?'登记基地及认定依据，校外培训保留审批材料。':'按认定文件登记成果；正式计分还须完成年度考核核验。';headers=['名称','编号','认定依据','操作'];rows=workspace.resources.filter(x=>x.kind===(section==='bases'?'base':'achievement')).map(x=>[esc(x.name),esc(x.code),esc(x.data.recognition),detail('social_resource',x.id)])}
 if(section==='recognition'){description='授课与辅助积分分别申报，按院长、归口学院、分管副校长、教学秘书职责办理。';headers=['申报人','项目','周期','状态','操作'];rows=workspace.claims.map(x=>[identity(c.teacherName(x.teacher_id),'个人积分认定','users'),esc(workspace.projects.find(p=>p.id===x.project_id)?.data.name||'关联项目'),esc(c.periodName(x.period_id)),statusBadge(x.state_label||workspace.states[x.state],x.state),detail('social_claim',x.id)]);workspace.ledger=await c.api('/social/ledger-summary')}
 if(section==='annual'){description='按收入、人次、成果和资金管理分别评分；口径未确认时不发布正式结果。';headers=['学院','周期','状态','操作'];rows=workspace.annuals.map(x=>[identity(x.org_name||c.orgName(x.org_id),'学院年度考核','school'),esc(c.periodName(x.period_id)),statusBadge(x.state_label||workspace.states[x.state],x.state),detail('social_annual',x.id)])}
 if(section==='policy'){description='学校制度已经定稿。本页登记交叉执行口径的书面解释及依据；缺失参数保持待确认，已启用版本不可直接修改。';headers=['名称','周期','状态','待确认项','操作'];rows=workspace.policies.map(x=>[identity(x.name,'制度执行口径','file'),esc(c.periodName(x.period_id)),statusBadge(x.state_label||workspace.states[x.state],x.state),Object.keys(workspace.decisions).filter(k=>x.data[k]==null).length,detail('social_policy',x.id)])}
 const resourceTable=section==='courses'?'<details class="business-guide mt20"'+(workspace.resources.some(r=>r.kind==='course_resource')?' open':'')+'><summary>课程资源明细（视频、文档、链接）</summary>'+table(['资源名称','关联课程','类型','时长（分钟）','操作'],workspace.resources.filter(r=>r.kind==='course_resource').map(r=>[esc(r.name),esc(r.data.course_code),esc({video:'视频',document:'文档',link:'其他链接'}[r.data.resource_type]),r.data.duration_minutes??'不适用',detail('social_resource',r.id)]))+'</details>':'';
 const ledger=section==='recognition'&&workspace.ledger.items.some(t=>Object.keys(t.years).length)?'<section class="card mt20"><div class="card-head"><h2>个人历年积分与折算</h2></div>'+table(['教师','年度','授课积分及对应课时','辅助积分','职称社会服务分','近五年累计'],workspace.ledger.items.flatMap(t=>Object.entries(t.years).map(([year,y])=>[esc(c.teacherName(t.teacher_id)),esc(year),esc(y.teaching),esc(y.auxiliary),y.title_pending?'待学校确认':esc(y.title_score),esc(t.five_year_total)])))+'</section>'+note(workspace.ledger.note,false,'积分折算说明'):'';
 const followups=section==='recognition'&&workspace.resources.some(r=>['correction','point_report','point_review'].includes(r.kind))?'<section class="card mt20"><div class="card-head"><h2>积分核对、更正与汇总公示</h2></div>'+table(['事项','状态','操作'],workspace.resources.filter(r=>['correction','point_report','point_review'].includes(r.kind)).map(r=>[esc(r.name),esc(r.kind==='point_review'?REVIEW_STATES[r.state]||r.state_label:r.state_label||workspace.states[r.state]),detail('social_resource',r.id)]))+'</section>':'';
 const config={
  projects:{label:'培训项目',icon:'book',steps:[['申报与备案','登记项目资料、培训安排及核算方式，提交审核备案。'],['实施与留证','导入核验后的参训明细，上传考勤、学时及结业材料。'],['结项与核算','核验有效人次与结项材料，再办理个人积分和学院统计。']]},
  courses:{label:'培训课程',icon:'book',steps:[['登记课程','填写课程编号、名称，并关联培训项目。'],['归集资源','登记视频、文档或链接，保留来源与认定依据。'],['核对时长','视频分钟数表示资源总时长，不代表学员已学习时长。']]},
  bases:{label:'培训基地',icon:'school',steps:[['登记基本资料','填写基地名称、承办学院和实际地点。'],['补充认定依据','登记学校认定文件，按需上传佐证材料。'],['保留办理记录','校外培训保留审批材料，资料与办理过程可追溯。']]},
  outcomes:{label:'培训成果',icon:'award',steps:[['登记成果','按认定文件填写成果名称与唯一编号。'],['提供佐证','保留成果认定材料，确保来源可核查。'],['年度核验','正式计分须完成年度考核中的成果核验。']]},
  recognition:{label:'积分申报',icon:'award'},annual:{label:'学院自评',icon:'assess'},policy:{label:'执行口径',icon:'file'}
 }[section];
 const p=workspace.pagination,items=section==='recognition'?workspace.claims:section==='annual'?workspace.annuals:section==='policy'?workspace.policies:section==='courses'?workspace.courses:section==='projects'?workspace.projects:workspace.resources;
 let stats=[[listSearch?'当前检索总数':config.label+'总数',p.total,'授权范围内的记录',config.icon]];
 if(section==='bases')stats.push(['本页校内基地',items.filter(x=>x.data.onsite===true).length,'按登记类型统计','school'],['本页校外基地',items.filter(x=>x.data.onsite===false).length,'按登记类型统计','map']);
 else if(section==='courses')stats.push(['本页课程资源',items.reduce((sum,x)=>sum+(workspace.course_stats[x.code]?.resources||0),0),'所列课程的资源数量','file'],['本页视频资源',items.reduce((sum,x)=>sum+(workspace.course_stats[x.code]?.videos||0),0),'所列课程的视频数量','clock']);
 else if(section==='outcomes')stats.push(['本页记录',items.length,'当前分页内的记录',config.icon],['本页已填认定日期',items.filter(x=>x.data.confirmed_on).length,'已填写认定日期的成果','check']);
 else stats.push(['本页记录',items.length,'当前分页内的记录',config.icon],['本页已'+(section==='projects'?'结项':section==='policy'?'启用':'归档'),items.filter(x=>['CLOSED','ARCHIVED','ACTIVE'].includes(x.state)).length,'依照当前办理状态','check']);
 const summary=p.total?'<div class="social-summary">'+stats.map(([label,value,hint,ico])=>'<article class="social-stat"><div class="social-stat-icon">'+c.icon(ico)+'</div><div><span>'+esc(label)+'</span><strong>'+esc(value)+'</strong></div></article>').join('')+'</div>':'';
 const pager='<div class="social-pager"><span>共 '+p.total+' 项 · 第 '+p.page+' 页</span>'+(p.page>1?act('上一页','social-list-page',String(p.page-1)):'')+(p.page*p.size<p.total?act('下一页','social-list-page',String(p.page+1)):'')+'</div>';
 const tools='<form id="social-search-form" class="social-tools" role="search" aria-label="检索'+config.label+'"><input id="social-query" type="search" aria-label="检索关键词" placeholder="输入关键词检索" value="'+esc(listSearch)+'" maxlength="100"><button class="btn" type="submit">'+c.icon('search')+'查询</button>'+(listSearch?act('清空检索','social-list-reset'):'')+'</form>';
 const scopeNote={teacher:{projects:'这里只显示你负责或参与授课的项目。项目由二级学院申报、学校备案；你在“个人培训”申报本人积分。',courses:'这里只显示你参与项目关联的课程，以及登记在你名下的课程资源。',bases:'这里显示所属学院的培训基地，供申报和授课时查阅。',outcomes:'这里显示所属学院已登记的培训成果。'},dept:{projects:'这里显示本教研室教师负责或参与的项目，只能查看和导出；申报、备案、结项由学院和学校办理。',courses:'这里显示本教研室项目关联的课程和学院课程资源，只能查看。',bases:'这里显示所属学院的培训基地，只能查看。',outcomes:'这里显示所属学院的培训成果，只能查看。'}}[c.me?.role?.kind]?.[section];
 const empty='<div class="social-empty"><div class="social-empty-art">'+c.icon(listSearch?'search':config.icon)+'</div><h3>'+(listSearch?'没有找到匹配的记录':'还没有'+config.label)+'</h3><p>'+(listSearch?'换个关键词试试。':'')+'</p><div class="social-empty-action">'+(listSearch?act('查看全部','social-list-reset'):buttons[0]||'')+'</div></div>';
 let content=rows.length?table(headers,rows):empty;
 if(section==='bases'&&items.length)content='<div class="social-resource-grid">'+items.map(x=>'<article class="social-resource-card"><div class="social-resource-top"><div class="social-resource-icon">'+c.icon(x.data.onsite===true?'school':'map')+'</div><span class="social-badge" data-tone="'+(x.data.onsite===true?'blue':'slate')+'">'+(x.data.onsite===true?'校内基地':x.data.onsite===false?'校外基地':'类型待补充')+'</span></div><h3>'+esc(x.name)+'</h3><p class="social-code">'+esc(x.code)+'</p><div class="social-resource-meta"><div class="social-meta-line">'+c.icon('org')+'<span>'+esc(x.org_name||c.orgName(x.org_id))+'</span></div><div class="social-meta-line">'+c.icon('map')+'<span>'+esc(x.data.location||'地点待补充')+'</span></div></div><div class="social-resource-evidence">认定依据：'+esc(x.data.recognition||'待补充')+'</div><div class="social-resource-foot">'+statusBadge(x.state_label||workspace.states[x.state],x.state)+detail('social_resource',x.id)+'</div></article>').join('')+'</div>';
 const guide=config.steps?'<details class="social-guide business-guide" aria-label="'+config.label+'办理指引"><summary>'+config.label+'办理指引</summary><ol>'+config.steps.map(([title,copy])=>'<li><strong>'+title+'</strong><span>'+copy+'</span></li>').join('')+'</ol><div class="social-guide-note">材料完整性与正式认定，以学校审核结论为准。</div></details>':'';
 const main='<div class="social-main"><section class="card social-panel"><div class="social-panel-head"><div><h2>'+config.label+'清单</h2></div></div>'+tools+content+pager+'</section>'+resourceTable+ledger+followups+((['courses','recognition'].includes(section)&&workspace.resource_pagination.total>200)?'<p>资源与更正汇总第'+resourcePage+'页 '+(resourcePage>1?act('前一页明细','social-resource-page',String(resourcePage-1)):'')+(resourcePage*200<workspace.resource_pagination.total?act('后一页明细','social-resource-page',String(resourcePage+1)):'')+'</p>':'')+'</div>';
 return '<div class="social-workspace">'+pageHead(description,buttons.join(''))+summary+main+'<div class="page-guides">'+guide+(scopeNote?note(scopeNote,false,'查看范围'):'')+note('统计仅包含当前账号有权查看的记录；“本页”数量随分页与检索变化。'+stats.map(([label,,hint])=>label+'：'+hint).join('；')+'。未完成审核的记录及候选试算不代表学校正式认定。',false,'统计与认定说明')+'</div></div>';
}

function detailFacts(title,rows){return '<section class="social-detail-section"><h3>'+context.esc(title)+'</h3><dl class="detail-facts">'+rows.map(([label,value])=>'<div><dt>'+context.esc(label)+'</dt><dd>'+value+'</dd></div>').join('')+'</dl></section>'}
function formSection(title,body,description=''){return '<fieldset class="social-fieldset"><legend>'+context.esc(title)+'</legend>'+(description?'<p class="social-fieldset-note">'+context.esc(description)+'</p>':'')+'<div class="social-form-fields">'+body+'</div></fieldset>'}
function commonForm(title,body,save,options={}){const c=context;c.formModal(title,'<div class="social-form">'+(body.includes('class="social-fieldset"')?body:formSection('办理内容',body))+formSection('办理说明',(options.hideReason?'':c.field('reason',options.reasonLabel||'办理说明','textarea',options.reasonDefault??title,{rows:2,full:true,hint:''}))+c.field('basis',options.basisLabel||'依据说明或材料编号（选填）','textarea','',{rows:2,required:!!options.basisRequired,full:true}),options.compact?'':'')+'</div>',async(v,f)=>{const back=options.reopen&&opened?{kind:opened.kind,id:opened.id,courseList:opened.courseList}:null,result=await save(v,f);c.closeModal();await c.render();if(options.after)await options.after(result);else if(back)await showDetail(back.kind,back.id,back.courseList).catch(()=>{})},{wide:true,...options});
 if(typeof document!=='undefined'){const period=document.getElementById('f-period_id'),policy=document.getElementById('f-policy_id');if(period&&policy){const choices=[...policy.options].map(o=>({value:o.value,label:o.textContent})),sync=()=>{const selected=policy.value,matching=choices.filter(o=>workspace.policies.some(p=>p.id===o.value&&p.period_id===period.value));policy.innerHTML='<option value="">'+(matching.length?'请选择制度口径':'该周期暂无制度口径')+'</option>'+matching.map(o=>'<option value="'+c.esc(o.value)+'">'+c.esc(o.label)+'</option>').join('');policy.value=matching.some(o=>o.value===selected)?selected:matching.length===1?matching[0].value:''};period.addEventListener('change',sync);sync()}}
 if(options.reopen&&opened&&typeof document!=='undefined'){const back={kind:opened.kind,id:opened.id,courseList:opened.courseList};document.querySelectorAll('#modal-root button[data-action="close"]').forEach(b=>{if(!b.textContent.trim())return;b.textContent='返回详情';b.addEventListener('click',e=>{e.preventDefault();e.stopImmediatePropagation();showDetail(back.kind,back.id,back.courseList).catch(err=>{context.closeModal();context.toast?.(err.message,true)})},true)})}
}
function projectOptionsHtml(result,selected){
 const c=context,key=projectChoice.key,options=result.items.map(p=>[p[key],p.name+' · '+p.code+' · '+p.cohort]);
 if(selected?.value&&!options.some(([value])=>value===selected.value))options.unshift([selected.value,selected.label]);
 const empty=projectChoice.mine&&!result.total&&!result.q?context.note('还没有可申报的项目：项目须已正常结项，且“参训明细”里登记了你的工号（授课或辅助）。项目还在办理中的，等学院结项后再来申报；如有遗漏，请联系学院补录参训明细。',true):'';
 return empty+'<div class="form-field full"><label for="social-project-query">检索关联项目</label><div class="social-picker-tools"><input id="social-project-query" type="search" maxlength="100" placeholder="输入项目名称、编号或期次" value="'+c.esc(result.q)+'">'+c.act('查找项目','social-project-lookup','1')+'</div></div>'+c.field(projectChoice.name,'选择关联项目','select',selected?.value||'',{full:true,options:[['','请选择一个项目'],...options]})+'<div class="social-picker-pager"><span>共 '+result.total+' 项 · 第 '+result.page+' 页</span>'+(result.page>1?c.act('上一页项目','social-project-lookup',String(result.page-1)):'')+(result.page*result.size<result.total?c.act('下一页项目','social-project-lookup',String(result.page+1)):'')+'</div>';
}
async function projectPicker(name,key,mine=false){projectChoice={name,key,q:'',sequence:0,mine};const result=await context.api('/social/project-options'+(mine?'?mine=true':''));projectChoice.total=result.total;return '<div id="social-project-picker" class="social-project-picker">'+projectOptionsHtml(result)+'</div>'}
function collegeField(value=''){const c=context,choices=c.orgs.filter(x=>x.kind==='college');return c.field('org_id','承办学院','select',value||(choices.length===1?choices[0].id:''),{options:[['','请选择承办学院'],...choices.map(x=>[x.id,x.name])]})}
function policyFields(x){const c=context,active=workspace.policies.filter(p=>p.state==='ACTIVE'),list=active.length?[...active,...workspace.policies.filter(p=>p.id===x?.policy_id&&p.state!=='ACTIVE')]:workspace.policies;return c.field('period_id','认定周期','select',x?.period_id||'',{options:c.periods.filter(x=>x.state==='OPEN').map(x=>[x.id,x.name])})+c.field('policy_id','制度执行口径','select',x?.policy_id||'',{options:list.map(x=>[x.id,x.name+' · '+(x.state_label||workspace.states[x.state])])})}
const cleanReason=v=>{const{reason,basis,...data}=v;return{reason,basis,data}};

async function showDetail(kind,id,courseList=null){
 const c=context,d=await c.api(path(kind,id)),x=d.item;opened={kind,id,...d,courseList};
 if(d.readonly){
  const data=x.data,e=c.esc,scope=c.me?.role?.kind==='dept'?'本教研室':'本人';
  const body='<div class="social-detail">'+c.note(d.readonly_reason||'仅显示本人参与摘要')+c.table(['项目资料','内容'],[['项目',e(data.name)],['期次',e(x.cohort)],['办理状态',e(d.state_label)],['培训期间',e(data.start_date+' 至 '+data.end_date)],['核算方式',e(names[data.mode])]])+c.table([scope+'核算单元','日期','模块',scope+'教师及岗位'],(d.facts?.units||[]).map(u=>[e(u.external_key),e(u.data.event_date),e(u.data.module),(u.data.teachers||[]).map(t=>e(c.teacherName(t.teacher_id)+' · '+({lecturer:'主讲',instructor:'实训指导',manager:'管理辅助'}[t.role]||'待确认'))).join('、')]))+'</div>';
  opened.printBody=body;
  return c.modal(data.name||scope+'培训参与摘要',body,c.can('export')?c.act('导出'+scope+'参与摘要','social-export',kind+'|'+id)+c.act('打印'+scope+'参与摘要','social-print'):'',true);
 }
 const {esc,act,table,note}=c,buttons=[...(courseList?[act('返回课程资源','social-course-resources',courseList)]:[]),...(c.can('export')?[act('导出办理材料','social-export',kind+'|'+id),act('打印当前材料','social-print')]:[])];
 if(d.view_only){
  let body='<div class="social-detail">'+note(d.view_only_reason)+'<div class="social-detail-status"><strong>当前办理状态</strong>'+statusBadge(d.state_label,x.state)+'</div>';
  const data=x.data;
  if(kind==='social_project')body+=detailFacts('项目资料',[['名称',esc(data.name)],['期次',esc(x.cohort)],['承办学院',esc(d.org_name||c.orgName(x.org_id))],['负责人',esc(c.teacherName(x.owner_id))],['培训期间',esc(data.start_date+' 至 '+data.end_date)],['核算方式',esc(names[data.mode])],['备案登记日期',esc(data.filed_on||'未备案')],['预期成果',esc(data.expected_outcomes||'')]])+table(['单元编号','培训日期','课程编号','参训记录数'],(d.facts?.units||[]).map(u=>[esc(u.external_key),esc(u.data.event_date),esc(u.data.course_code),u.data.learners.length]));
  else body+='<dl class="kv">'+[['名称',x.name],['来源编号',x.code],...(x.kind==='achievement'?[['成果等级',names[data.level]||'待确认'],['认定日期',data.confirmed_on||'待补充']]:[]),['认定依据',data.recognition],['地点或说明',data.location||'待补充']].map(([k,v])=>'<dt>'+esc(k)+'</dt><dd>'+esc(v||'')+'</dd>').join('')+'</dl>';
  body+='<section class="social-detail-section"><h3>佐证材料</h3>'+c.downloads(d.attachments)+'</section><details class="detail-fold mt20"><summary>办理记录</summary>'+c.eventsHtml(d.events)+'</details></div>';
  opened.printBody=body;return c.modal(data.name||x.name||'社会培训办理',body,buttons.join(''),true);
 }
 if(kind==='social_resource'&&['base','achievement','course_resource'].includes(x.kind)&&!x.data.auto&&c.can('records.write')&&['school','college'].includes(c.me?.role?.kind))buttons.push(act('修改资料','social-resource-edit','','primary'));
 const me=c.me?.user?.id,uploadable=kind==='social_claim'?x.teacher_id===me&&['DRAFT','RETURNED'].includes(x.state):kind==='social_resource'&&x.kind==='correction'?x.data?.created_by===me&&['DRAFT','RETURNED'].includes(x.state):kind==='social_resource'&&x.kind==='point_review'?(x.data?.created_by===me&&x.state==='DRAFT')||(x.data?.teacher_id===me&&x.state==='TEACHER'):(kind==='social_policy'?c.can('rules.manage'):c.can('records.write'));
 if(!d.public_summary&&!['ARCHIVED','ACTIVE','CLOSED'].includes(x.state)&&c.can('file.write')&&uploadable)buttons.push(act('上传佐证','social-upload','',(d.attachments||[]).length?'':'light','file'));
 opened.labels={};opened.archiveStep=false;const owner=kind==='social_claim'?x.teacher_id:kind==='social_policy'?x.created_by:kind==='social_resource'?(x.data?.teacher_id||x.data?.created_by):x.owner_id,selfOwned=(owner&&owner===c.me?.user?.id)||(kind==='social_resource'&&x.kind==='correction'&&x.data?.created_by&&x.data.created_by===c.me?.user?.id),reviewActions=['file','close','approve','activate','publish','archive','resolve','finance','academic','discipline','coordinator','return'];let avoided=false;
 const add=(label,action)=>{if(selfOwned&&reviewActions.includes(action)&&!(x.kind==='point_report'&&action==='archive')){avoided=true;return}opened.labels[action]=label;buttons.push(act(label,'social-transition',action,action==='return'?'danger':['submit','approve','file','close','activate','publish','archive'].includes(action)?'primary':''))};
 if(kind==='social_project'&&c.can('records.write')){
  if(['DRAFT','RETURNED'].includes(x.state)){add('提交审核备案','submit');buttons.push(act('修改项目资料','social-project-edit'))}
  if(x.state==='SUBMITTED'&&workspace.my_duties.includes('coordinator')){add('完成审核备案','file');add('退回补正','return')}
  if(x.state==='FILED'){buttons.push(act('登记本项目课程','social-course-for-project'));buttons.push(act('导入参训明细','social-unit-import'));buttons.push(act('提交结项','social-close'));add('申请重新备案','refile')}
  if(x.state==='CLOSE_REVIEW'&&workspace.my_duties.includes('coordinator')){add('核验通过结项','close');add('退回补充材料','return')}
 }
 if(kind==='social_project'&&c.can('assessment.review')&&workspace.my_duties.some(v=>['coordinator','discipline','finance'].includes(v)))buttons.push(act('登记投诉与跟踪','social-note'));
 if(kind==='social_claim'){
  if(x.state==='ARCHIVED'&&(x.teacher_id===c.me.user.id||workspace.my_duties.includes('secretary'))){if(d.busy_reason)opened.busyNote=d.busy_reason+'。';else buttons.push(act('申请追加更正','social-correction-new'))}
  if(x.state==='ARCHIVED'&&x.teacher_id!==c.me.user.id&&['dept','college'].includes(c.me?.role?.kind)){if(d.busy_reason)opened.busyNote=d.busy_reason+'。如还发现积分有误，请在那件办结后再发起核对。';else buttons.push(act('发现积分有误，发起核对','social-review-new','','light','help'))}
  if(x.teacher_id===c.me.user.id&&['DRAFT','RETURNED'].includes(x.state)){add('提交本人积分申报','submit');buttons.push(act('补正及辅助积分','social-claim-edit'))}
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
  if(x.state==='DRAFT'&&x.data.created_by===c.me.user.id)add('提交归口复核','submit');
  if(x.state==='SUBMITTED'&&workspace.my_duties.includes('coordinator'))add('复核报送或启动公示','approve');
  if(x.state==='PUBLIC'){add('提出公示异议','dispute');if(workspace.my_duties.includes('coordinator'))add('记录异议处理','resolve');if(workspace.my_duties.includes('secretary'))add('公示完成并归档','archive')}
 }
 if(kind==='social_policy'&&x.state==='DRAFT'&&c.me.role.kind==='school'&&c.can('rules.manage'))add(x.data.interpretation_reference?'更新学校书面依据':'登记学校书面依据（依据栏填文号）','record_basis');if(kind==='social_policy'&&x.state==='DRAFT'&&workspace.my_duties.includes('coordinator'))add('确认学校口径并启用','activate');
 if(kind==='social_annual'){
  if(['DRAFT','RETURNED'].includes(x.state)){add('提交学院自评','submit');buttons.push(act('补正年度自评','social-annual-edit'))}
  if(x.state==='REVIEW')for(const [key,label] of Object.entries({finance:'财务核验',academic:'成果核验',discipline:'纪检核验',coordinator:'归口初核'}))if(workspace.my_duties.includes(key))add(label,key);
  if(x.state==='COMMITTEE'&&workspace.my_duties.includes('committee'))add('委员会评分并公示','publish');
  if(x.state==='PUBLIC'){add('登记公示异议','dispute');if(workspace.my_duties.includes('coordinator'))add('记录异议处理','resolve');if(workspace.my_duties.includes('secretary'))add('公示完成并归档','archive')}
  if(['REVIEW','COMMITTEE','PUBLIC'].includes(x.state)&&workspace.my_duties.includes('coordinator'))add('退回重新核算','return');
 }
 let body='<div class="social-detail"><div class="social-detail-status"><strong>当前办理状态</strong>'+statusBadge(d.state_label,x.state)+'</div>'+(avoided?note('这是你本人登记、申报或发起的事项，按回避规定须由其他有审核职责的人员办理。',true):'')+(opened.busyNote?note(opened.busyNote):'')+(d.trial?.blockers||[]).map(v=>note(v,true)).join('');
 const steps=kind==='social_project'?[['DRAFT','项目申报'],['SUBMITTED','审核备案'],['FILED','培训实施'],['CLOSE_REVIEW','结项核验'],['CLOSED','正常结项']]:kind==='social_claim'?[['DRAFT','本人填写'],['SUBMITTED','院长初审'],['DEAN','归口复审'],['COORDINATOR','分管审批'],['APPROVED','秘书归档'],['ARCHIVED','已入账']]:kind==='social_annual'?[['DRAFT','学院自评'],['REVIEW','职能核验'],['COMMITTEE','委员会评分'],['PUBLIC','公示'],['ARCHIVED','已归档']]:[];
 if(steps.length)body+='<nav class="social-progress" aria-label="办理流程"><ol>'+steps.map(([state,label])=>'<li data-current="'+(x.state===state)+'"'+(x.state===state?' aria-current="step"':'')+'>'+label+'</li>').join('')+'</ol></nav>';
 if(x.state==='RETURNED'){const last=[...(d.events||[])].reverse().find(e=>/退回/.test(e.action));body+=note('退回意见：'+(last?.reason||'请核对办理记录，补充后重新提交。'),true)}
 if(kind==='social_annual'&&x.snapshot?.public_end)body+=note('公示期间：'+x.snapshot.public_start+' 至 '+x.snapshot.public_end+'。公示期满且异议处理完毕后归档。');
 const data=x.data;
 if(kind==='social_project'){
  if(d.facts.blockers?.length)body+=d.facts.blockers.map(v=>note(v,true)).join('');
  if(x.closeout_pending?.length)body+=x.closeout_pending.map(v=>note(v,true)).join('');
  const pending=data.source||{},needs=[pending.dates_pending||pending.date_pending?'实际培训日期':'',pending.mode_pending?'备案核算方式':'',...(pending.policy_pending||(pending.ledger_id?['level','scene'].filter(k=>!data[k+'_confirmed']):[])).map(k=>({level:'项目层级',scene:'授课场景'}[k]))].filter(Boolean);
  if(needs.length)body+=note('台账草稿待核实：'+needs.join('、')+'。当前显示的自动生成值仅供整理，不能直接正式备案。',true);
  body+=detailFacts('项目资料',[['名称',esc(data.name)],['期次',esc(x.cohort)],['培训期间',esc(data.start_date+' 至 '+data.end_date)],['核算方式',esc(names[data.mode])],['备案登记日期',esc(data.filed_on||'未备案')],['前置审核日期',esc(data.prior_review_on||'不适用')],['备案依据',esc(data.filing_basis||'待补充')],['培训类别',esc(names[data.category])],['预计收入',esc(data.expected_income)+' 元'],['预期成果',esc(data.expected_outcomes)],['有效人次',d.facts.effective],['剔除人次',d.facts.excluded]]);
  if(d.facts.units.length)body+='<h3>参训明细</h3>'+table(['单元编号','培训日期','课程编号','参训记录数'],d.facts.units.map(u=>[esc(u.external_key),esc(u.data.event_date),esc(u.data.course_code),u.data.learners.length]));
  body+=detailFacts('备案核算条件',[['承办学院',esc(d.org_name||c.orgName(x.org_id))],['负责人',esc(c.teacherName(x.owner_id))],['标准班类型',esc(names[data.class_type])],['项目层级',esc(names[data.level])],['专项层级依据',esc(data.level_basis||'按类别通常口径')],['授课场景',esc(names[data.scene])],['辅助积分细则',esc(data.auxiliary_standard||'未备案')],['个人辅助积分每日上限',data.auxiliary_daily_cap??'未确认']]);
  if(x.closeout.closed_on){const z=x.closeout;body+='<h3 class="mt20">结项核验</h3>'+table(['核验项目','登记内容'],[['结项日期',esc(z.closed_on)],['成果报告',esc(z.outcome_report)],['满意度',esc(z.satisfaction)+'%'],['实际到账收入',esc(z.actual_income)+' 元'],['财务确认依据',esc(z.finance_reference)],['结算日期',esc(z.settlement_on||'待结算')],['隐性成本',esc(z.implicit_cost)+' 元'],['资金来源',esc({other_training:'其他培训收入',government_special:'政府专项培训资金'}[z.funding_source]||'历史记录待补确认')],['专项适用依据',esc(z.funding_basis||'不适用或待补')],['收入分配',z.retained!=null?'学校留存 '+esc(z.retained)+' 元 · 项目公用 '+esc((Number(z.actual_income)-Number(z.retained)-Number(z.personnel)).toFixed(2))+' 元 · 校内人员支出 '+esc(z.personnel)+' 元':Number(z.actual_income)>0?(z.funding_source==='government_special'?'按主管部门规定核验，见专项依据':'历史分配资料待补确认'):'零收入，不涉及'],['省平台报送凭证',esc(z.province_receipt||'不适用或待补充')],['专项佐证',esc(z.special_evidence||'不适用或待补充')],['整改报告',esc(z.rectification||'无')],['整改期限',esc(z.rectification_due||'不适用')],['已核验材料',esc((z.materials_checked||[]).map(k=>({plan:'培训方案',filing_form:'备案登记表',roster:'学员名册',attendance:'签到表',hours:'学时记录',process:'过程影像',assessment:'结业考核',outcomes:'成果材料'}[k])).join('、'))],['档案保管',z.retention_years?z.retention_years+'年':'结项审核后确定']]);}
  if(d.facts.followups.length)body+='<h3>投诉、整改及结算跟踪</h3>'+table(['事项编号','类型','办理期限','办结日期','财务结论','回复'],d.facts.followups.map(r=>[esc(r.case_reference),esc({complaint:'投诉',rectification:'整改',settlement:'结算',violation:'正式处理'}[r.kind]),esc(Object.entries(r.deadlines||{}).map(([k,v])=>k+'：'+v).join('；')),esc(r.completed_on||'待办结'),esc(r.kind==='settlement'?({noncompliant:'已确认不合规',exempt:'已批准例外'}[r.settlement_result]||'待财务核验'):'不适用'),esc(r.reply||'待回复')]));
 }
 if(kind==='social_policy'){
  const values={ratio_cap:'人次÷标准人数，最高2',over_standard_two:'超过标准人数按2',daily:'按培训日',whole_project:'按整个期次',half_up:'四舍五入',proportional:'按比例',full_steps:'完整步长',four_indicators:'四项年度指标',all_bonus_shared_ten:'单项加分合计最高10分',three:'三个等次',four:'四个等级',highest_per_reference:'同一成果取最高等级',exclusive:'同一工作不重复计分',teaching:'仅授课积分',all:'授课与辅助积分',project_units:'按项目核算单元',closeout:'按结项日期',original_submission:'按首次申报日期',resubmission_date:'按补正提交日期'};
  body+=table(['执行口径','已登记内容'],Object.entries(workspace.decisions).map(([key,label])=>[esc(label),data[key]==null?'待学校书面确认':esc(typeof data[key]==='boolean'?(data[key]?'可以认定':'不予认定'):values[data[key]]||data[key])]))+note('学校书面解释依据：'+(data.interpretation_reference||'尚未提供'));
 }
 if(kind==='social_resource'&&!['correction','point_report','point_review'].includes(x.kind)){
  body+='<section class="social-detail-section"><h3>基本资料</h3><dl class="kv">'+[['名称',x.name],['来源编号',x.code],['承办学院',d.org_name||x.org_name||workspace.resources.find(r=>r.id===x.id)?.org_name||c.orgName(x.org_id)],...(x.kind==='base'?[['基地类型',data.onsite===true?'校内基地':data.onsite===false?'校外基地':'待补充']]:[]),...(x.kind==='achievement'?[['成果等级',names[data.level]||'待确认'],['认定日期',data.confirmed_on||'待补充']]:[]),['认定依据',data.recognition],['地点或说明',data.location||'待补充'],...(x.kind==='course_resource'?[['关联课程',data.course_code],['资源类型',{video:'视频',document:'文档',link:'其他链接'}[data.resource_type]||'待确认'],['归属教师',data.teacher_id?c.teacherName(data.teacher_id):'待确认'],['视频总时长',data.duration_minutes==null?'不适用':data.duration_minutes+' 分钟']]:[])].map(([label,value])=>'<dt>'+label+'</dt><dd>'+esc(value)+'</dd>').join('')+'</dl></section>';
  if(data.resource_url&&/^https?:\/\//.test(data.resource_url))body+='<p><a href="'+esc(data.resource_url)+'" target="_blank" rel="noopener noreferrer">打开课程资源</a></p>';
 }
 if(kind==='social_resource'&&x.kind==='point_review'){const r=d.review_context||{},out={corrected:r.correction_state==='VOID'?'该更正已作废，未追加积分；如仍需调整，请重新发起核对':data.ruling?'学院已裁定更正，已生成更正单，进入归口、分管副校长审批及教学秘书归档':'已生成更正单，进入院长、归口、分管副校长审批及教学秘书归档',kept:'学院裁定维持原认定',withdrawn:'发起人已撤回'}[data.outcome];body+=note({DRAFT:d.workflow_blockers?.length?'下一步：请学校管理员配置无需回避的替代办理人，完成后刷新详情再发送。':'下一步：上传核对材料（如签到表、认定表），再点“发给教师回应”。',TEACHER:'等待教师回应：同意就自动生成更正单；不同意由学院院长裁定。未办结前不能确认该教师的考核。',COLLEGE:'教师不同意，等待学院院长裁定。',CLOSED:'已办结：'+(out||'')}[x.state]||'')+table(['核对内容','说明'],[['被核对教师',esc(r.teacher_name)],['所属项目',esc(r.project)],['原认定积分','授课 '+esc(r.teaching??'—')+'，辅助 '+esc(r.auxiliary??'—')],['建议更正','授课 '+esc(data.teaching)+'，辅助 '+esc(data.auxiliary)+'（正数增加、负数扣减）'],['入账周期',esc(c.periodName(data.period_id))],['发起人',esc(r.creator_name)],['哪里不对',esc(data.reason)],['教师回应',esc(data.teacher_reply||'尚未回应')],['学院裁定',esc(data.ruling||(x.state==='COLLEGE'?'待裁定':'—'))]])}
 if(kind==='social_resource'&&x.kind==='correction')body+=table(['更正项目','内容'],[['授课积分变动',esc(data.teaching)],['辅助积分变动',esc(data.auxiliary)],['正式处理或更正依据',esc(data.decision_reference)],['入账周期',esc(c.periodName(data.period_id))]])+note(x.state==='VOID'?'本更正已作废，未追加积分。作废原因：'+(data.void_reason||'')+'。如需更正，请返回原认定重新办理。':'经逐级审核后追加差额，原认定快照保持不变。');
 if(kind==='social_resource'&&x.kind==='point_report')body+=table(['教师','学院','项目','授课积分','辅助积分','合计'],data.rows.map(r=>[esc(r.teacher_name),esc(r.org_name),esc(r.project),esc(r.teaching),esc(r.auxiliary),esc(r.total)]))+note('汇总截至本次生成时已归档的认定及更正。'+(data.public_end?'公示截止：'+data.public_end+'；满5个工作日且异议处理完毕后归档。':''));
 const disputes=kind==='social_annual'?x.snapshot?.disputes:data.disputes;
 if(disputes?.length)body+=table(['异议内容','办理情况'],disputes.map(r=>[esc(r.reason),esc(r.resolved?r.resolution:'待核实')]));
 if(d.trial){const t=d.trial;body+=note(x.state==='ARCHIVED'?'以下为归档时的核算快照':'以下为候选试算，尚非正式认定');body+=table(['指标','分值'],[['授课积分',t.teaching??'不适用'],['辅助积分',t.auxiliary??'不适用'],['基础分',t.base??'不适用'],['认定加分',t.bonus_awarded??'不适用'],['合计',t.total??'待学校确认'],['候选等级',esc(t.grade||'待核定')],['申报期限',esc(t.deadline||'不适用或待校历确认')]].filter(([label,value])=>value!=='不适用'&&(label!=='候选等级'||kind==='social_annual')&&(label!=='申报期限'||!!t.deadline)));if(t.details)body+=table(['核算单元','人次','计算依据','候选积分'],t.details.map(r=>[esc(r.unit),r.participants,esc(r.formula),r.score??'待封顶口径确认']));if(t.metrics)body+=table(['指标','实际值','任务目标','基础分','加分'],t.metrics.map(r=>[esc(r.label),r.actual,r.target??'待下达',r.base??'待核定',r.bonus??'待核定']))}
 if(kind==='social_annual'&&d.trial){const t=d.trial;body+=table(['成果、资金及总分处理','内容'],[['综合成果基础分',t.achievement_base],['资金管理基础分',t.cost_base??'待财务核验'],['封顶前各项加分合计',t.bonus_raw],['全校总加分上限','10 分（仍须确认叠加口径）'],['封顶前总分',t.total_before_cap??'待核定'],['已确认总分上限',t.total_cap??'待核定'],['一票否决',t.veto?'已触发':'未触发'],...(!d.public_summary?[['正式处理依据',esc(t.veto_basis||data.discipline_reference||'无')],['学院个人积分合计',t.points_total],['按已确认人数的平均积分',t.points_average??'人数基准待确认']]:[])]);if(t.cost_details)body+=table(['资金管理扣分项','扣分或说明'],t.cost_details.map(r=>[esc(r.label),esc(r.value)]));if(t.outcome_details)body+=table(['成果认定依据','得分依据'],t.outcome_details.map(r=>[esc(r.label),esc(r.value)]));}
 body+=(d.public_summary?note('公示开放评分摘要；原始核验材料由授权人员查看。'):'<section class="social-detail-section"><h3>佐证材料</h3>'+c.downloads(d.attachments)+'</section><details class="detail-fold mt20"><summary>办理记录</summary>'+c.eventsHtml(d.events)+'</details>')+'</div>';
 const pname=d.trial?.basis?.facts?.project?.data?.name||d.trial?.basis?.facts?.project?.name||'',title=data.name||x.name||({social_claim:'个人积分申报',social_annual:'学院年度自评',social_resource:'积分更正与汇总'}[kind]||'社会培训办理')+(pname?' · '+pname:'');
 opened.printBody=body;c.modal(title,body,buttons.join(''),true);
}

function projectForm(edit=false){
 const c=context,x=edit?opened.item:null,v=x?.data||{},f=(key,label,type='text',options={})=>c.field(key,label,type,v[key]??'',options);
 const pending=v.source||{},confirmations=[];
 if(pending.dates_pending||pending.date_pending)confirmations.push(f('dates_confirmed','确认实际培训期间','checkbox',{checkLabel:'已核对开始、结束日期，占位日期已更正'}));
 if(pending.mode_pending)confirmations.push(f('mode_confirmed','确认备案核算方式','checkbox',{checkLabel:'已核对模块或培训工作日明细'}));
 for(const [key,label] of [['level','项目层级'],['scene','授课场景']])if((pending.policy_pending||[]).includes(key)||(pending.ledger_id&&!v[key+'_confirmed']))confirmations.push(f(key+'_confirmed','确认'+label,'checkbox',{checkLabel:'已依据项目材料核实'+label}));
 const body=formSection('一、项目基本资料',f('code','项目编号')+f('name','项目名称')+f('cohort','项目期次')+collegeField(v.org_id)+c.teacherField(v.owner_id||'', 'owner_id','项目负责人（输入工号或姓名检索）')+f('category','培训类别','select',{options:[...(edit?[]:[['','请选择培训类别']]),...selectable(['subsidy','enterprise','community','rural','other'])]})+f('high_risk','高风险项目','checkbox',{required:false,checkLabel:'属于其他高风险项目（须前置审核，备案时登记审核日期及依据）'}),'')+formSection('二、培训安排',f('start_date','开始日期','date')+f('end_date','结束日期','date')+f('expected_income','预计收入（公益类填0）','number',{min:0,step:0.01})+f('expected_participants','预计人次','number',{min:0,step:1})+f('expected_outcomes','预期成果','textarea')+f('target_groups','重点群体与行动对接','textarea',{required:false,hint:'补贴性培训必填：写明面向哪些重点群体、对接哪项行动；其他类别可不填。'}))+formSection('三、积分核算依据',f('mode','核算方式','select',{options:selectable(['module','person_day'])})+f('class_type','标准班类型','select',{options:selectable(['technical','lecture'])})+f('level','项目层级','select',{options:selectable(['province','city','school'])})+f('scene','授课场景','select',{options:selectable(['dispatched','full_day','ordinary'])})+f('level_basis','专项层级认定依据','textarea',{required:false,hint:'企业定制通常选市级；社区、免费帮扶通常选校级。属于更高层级专项时，填写正式认定依据并提交归口核验。'})+f('auxiliary_standard','随项目备案的辅助积分细则','textarea',{required:false})+f('auxiliary_daily_cap','个人辅助积分每日上限','number',{required:false,min:0,step:0.01}),'同期项目只采用一种核算方式；尚未确认的辅助积分标准请留空。')+(confirmations.length?formSection('四、台账草稿待核实事项',confirmations.join(''),'核实并保存后才能提交正式备案；自动生成的值不能代替材料核验。'):'');
 commonForm(edit?'修改项目申报':'申报培训项目',body,async v=>{delete v.owner_id_search;const data=cleanReason(v);return c.api('/social/projects'+(edit?'/'+x.id:''),{method:edit?'PUT':'POST',body:{...data,...(edit?{expected_version:x.version}:{})}})},
  edit?{reopen:true}:{submit:'保存草稿',reasonLabel:'申报说明',reasonDefault:'学院申报培训项目',hint:'保存草稿后上传材料，再提交审核备案。',after:r=>r?.item?.id?showDetail('social_project',r.item.id):null});
 bindProjectCategory();
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
function bindProjectCategory(){
 if(typeof document==='undefined')return;
 const cat=document.getElementById('f-category'),tg=document.getElementById('f-target_groups'),lab=document.querySelector('label[for="f-target_groups"]');if(!cat||!tg||!lab)return;
 const sync=()=>{const need=cat.value==='subsidy';tg.required=need;lab.querySelector('b')?.remove();if(need)lab.insertAdjacentHTML('beforeend',' <b>*</b>')};
 cat.addEventListener('change',()=>{sync();const level=document.getElementById('f-level'),value={enterprise:'city',community:'school',rural:'school'}[cat.value];if(level&&value)level.value=value});sync();
}

function policyForm(){
 const c=context,choice=(key,label,options)=>c.field(key,label,'select','',{options:[['','待学校确认'],...options],required:false});
 let body=`<div class="social-recommend"><button type="button" class="btn light" id="policy-recommend">按系统推荐口径一键填写（待学校书面确认）</button><p class="cell-sub">只预填下拉和日期；学校书面答复不同的，逐项改掉再保存。</p></div>`+c.field('name','规则版本名称')+c.field('period_id','适用周期','select','',{options:c.periods.filter(x=>x.state==='OPEN').map(x=>[x.id,x.name])});
 const groups={personal:'',annual:'',scope:''};let calendar='';
 for(const [k,label,opts] of [
  ['cap_mode','单次积分封顶',[['ratio_cap','人次÷标准人数，最高2'],['over_standard_two','超过标准人数直接按2']]],['person_day_unit','人天式单次范围',[['daily','每个培训日'],['whole_project','整个项目期次']]],
  ['precision','单元积分及汇总精度',[[2,'逐单元及汇总均保留两位（须学校确认）']]],['rounding','舍入方式',[['half_up','四舍五入']]],['step_mode','不足计分步长',[['proportional','按比例计算'],['full_steps','只计算完整步长']]],
  ['annual_model','学院考核模型',[['four_indicators','收入、人次、成果、资金管理四项']]],['bonus_pool','总加分规则',[['all_bonus_shared_ten','所有单项加分共用10分上限']]],['grade_mode','考核等次',[['three','优秀、合格、不合格'],['four','优秀、良好、合格、不合格']]],
  ['satisfaction_inclusive','恰好95%满意度',[['true','可以认定成果'],['false','不认定，须超过95%']]],['achievement_dedup','成果去重',[['highest_per_reference','同一成果依据仅取最高等级']]],['auxiliary_overlap','辅助工作重叠',[['exclusive','同一工作不得重复计分']]],['title_scope','职称折算范围',[['teaching','仅授课积分'],['all','授课及辅助积分']]],['organization_basis','学院人次口径',[['project_units','按项目核算单元汇总，不重复累计教师']]],['date_basis','年度归属',[['closeout','按结项日期归属']]]])groups[['cap_mode','person_day_unit','precision','rounding','auxiliary_overlap'].includes(k)?'personal':['step_mode','annual_model','bonus_pool','grade_mode','satisfaction_inclusive','achievement_dedup'].includes(k)?'annual':'scope']+=choice(k,label,opts);
 groups.scope+=choice('title_precision','职称折算小数位',[[0,'整数'],[1,'一位'],[2,'两位'],[3,'三位'],[4,'四位']])+choice('title_rounding','职称折算舍入',[['half_up','四舍五入']])+choice('resubmission_mode','退回补正期限依据',[['original_submission','按首次申报日期'],['resubmission_date','按补正再次提交日期']]);
 for(const [k,l] of [['total_cap','年度总分上限'],['excellent_from','三等制优秀门槛'],['qualified_from','三等制合格门槛']])groups.annual+=c.field(k,l,'number','',{required:false,min:0,step:0.01});
 for(const [k,l] of [['effective_date','本口径适用开始日期'],['calendar_start','校历开始日期'],['calendar_end','校历结束日期']])calendar+=c.field(k,l,'date','',{required:false});
 for(const [k,l] of [['holidays','放假日期（每行一个）'],['workdays','周末补班日期（每行一个）'],['calendar_reference','学校工作日历依据'],['interpretation_reference','学校书面解释依据']])calendar+=c.field(k,l,'textarea','',{required:false});
 body=formSection('一、版本与周期',body)+formSection('二、个人积分',groups.personal)+formSection('三、学院年度考核',groups.annual)+formSection('四、归属与折算',groups.scope)+formSection('五、校历与书面依据',calendar);
 commonForm('登记学校制度执行口径',body,async v=>{const {name,period_id,reason,basis,...raw}=v;const data=blankNull(raw);for(const [k,l] of [['holidays','放假日期'],['workdays','周末补班日期']])data[k]=(raw[k]||'').split(/[\s,，、；;]+/).filter(Boolean).map((d,i)=>{const m=d.match(/^(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})日?$/);if(!m)throw Error(l+'第'+(i+1)+'个“'+d+'”不是日期，请写成 2026-10-01，每行一个');return m[1]+'-'+m[2].padStart(2,'0')+'-'+m[3].padStart(2,'0')});for(const k of ['calendar_reference','interpretation_reference'])data[k]=raw[k]||'';if((raw.calendar_start||raw.calendar_end)&&!(raw.calendar_start&&raw.calendar_end&&(raw.calendar_reference||'').trim()))throw Error('校历要三项一起填：校历开始日期、校历结束日期、学校工作日历依据（如校历文件名称或文号）。缺一项时，积分申报会提示“学校工作日历尚未确认”。');for(const k of ['precision','title_precision'])if(data[k]!=null)data[k]=Number(data[k]);if(data.satisfaction_inclusive!=null)data.satisfaction_inclusive=data.satisfaction_inclusive==='true';return c.api('/social/policies',{method:'POST',body:{name,period_id,reason,basis,data}})},{after:r=>r?.item?.id?showDetail('social_policy',r.item.id):null,hint:'只登记学校书面确认的选项；尚未确认的保持空白。如学校解释不在当前支持范围内，先保留待确认，由实施人员补充实现。'});
 document.getElementById('policy-recommend')?.addEventListener('click',()=>{for(const [k,v] of Object.entries(RECOMMENDED_POLICY)){const el=document.getElementById('f-'+k);if(el){el.value=String(v);el.dispatchEvent(new Event('change',{bubbles:true}))}}const ref=document.getElementById('f-interpretation_reference');if(ref&&!ref.value)ref.value='系统推荐口径（见《社会培训模块重新规划》第八节），待学校书面确认';});
}
// 推荐口径：与《社会培训模块重新规划》第八节确认清单一致；学校书面确认前不得启用。
const RECOMMENDED_POLICY={cap_mode:'ratio_cap',person_day_unit:'daily',precision:2,rounding:'half_up',step_mode:'full_steps',annual_model:'four_indicators',bonus_pool:'all_bonus_shared_ten',grade_mode:'four',satisfaction_inclusive:'false',achievement_dedup:'highest_per_reference',auxiliary_overlap:'exclusive',title_scope:'all',organization_basis:'project_units',date_basis:'closeout',title_precision:2,title_rounding:'half_up',resubmission_mode:'original_submission',total_cap:110,effective_date:'2026-08-01'};

export async function socialAction(action,id,c){
 context=c;if(!workspace||workspaceUser!==c.me?.user?.id){workspace=await c.api('/social/workspace');workspaceUser=c.me?.user?.id}
 if(action==='social-resource-page'){resourcePage=Number(id);return c.render()}
 if(action==='social-list-page'){listPage=Number(id);return c.render()}
 if(action==='social-list-apply'){listSearch=document.getElementById('social-query').value.trim();listPage=1;resourcePage=1;return c.render()}
 if(action==='social-list-reset'){listSearch='';listPage=1;resourcePage=1;return c.render()}
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
 if(action==='social-course-import')return commonForm('批量导入培训课程',c.note('复制表格的三列：课程编号、课程名称、项目编号。先预检，再整批确认。')+c.field('rows','课程清单','textarea','课程编号\t课程名称\t项目编号',{rows:10,full:true}),async v=>{
  const lines=v.rows.trim().split(/\r?\n/);if(lines.shift()!=='课程编号\t课程名称\t项目编号')throw Error('请保留三列表头');
  const rows=lines.map(line=>{const[code,name,project_code,...extra]=line.split('\t');if(!code||!name||!project_code||extra.length)throw Error('每行须为课程编号、课程名称、项目编号三列');return {code,name,project_code}});
  await importCourses(rows,v,async()=>{await socialAction('social-course-import','',c);for(const key of ['rows','reason','basis'])document.getElementById('f-'+key).value=v[key]||''});
 },{submit:'预检课程清单'});
 if(action==='social-course-chaoxing')return commonForm('超星学习通导出表导入',c.note('在超星学习通课程管理中导出课程列表，选择关联项目后上传 CSV 文件或直接粘贴表格内容。可识别课程名称、课程编号（课程ID）、授课教师、视频数、视频时长、章节数和学习人数；视频时长可为分钟数、时:分:秒，或带“分钟”的数值。',false,'导出表填写说明')+await projectPicker('project_code','code')+c.field('file','上传逗号分隔表格（可不选）','file','',{required:false,accept:'.csv,.txt,.tsv'})+c.field('rows','或粘贴导出表内容（含表头）','textarea','',{rows:10,full:true,required:false}),async(v,f)=>{
  const file=f?.querySelector('input[type=file]')?.files?.[0],text=file?await readImportFile(file):v.rows;
  if(!String(text||'').trim())throw Error('请上传导出文件或粘贴导出表内容');
  const projectLabel=f?.querySelector('#f-project_code')?.selectedOptions[0]?.textContent||v.project_code;
  await importCourses(parseChaoxingCourses(text,v.project_code),v,async()=>{await socialAction('social-course-chaoxing','',c);const select=document.getElementById('f-project_code');if(![...select.options].some(o=>o.value===v.project_code))select.insertAdjacentHTML('beforeend','<option value="'+c.esc(v.project_code)+'">'+c.esc(projectLabel)+'</option>');select.value=v.project_code;for(const [key,value]of Object.entries({rows:text,reason:v.reason,basis:v.basis}))document.getElementById('f-'+key).value=value||''});
 },{submit:'预检课程清单'});
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
  return commonForm('追加积分更正',body,v=>c.api('/social/corrections'+(edit?'/'+x.id:''),{method:edit?'PUT':'POST',body:{...v,claim_id:edit?old.claim_id:x.id,...(edit?{expected_version:x.version}:{})}}));
 }
 if(action==='social-report-new')return commonForm('双月汇总与年度公示',c.field('org_id','汇总组织（年度公示选择学校）','select','',{options:c.orgs.filter(o=>['school','college'].includes(o.kind)).map(o=>[o.id,o.name])})+c.field('year','年度','number',new Date().getFullYear(),{min:2000,max:2200,step:1})+c.field('window','汇总范围','select','1-2',{options:[['1-2','1—2月'],['3-4','3—4月'],['5-6','5—6月'],['7-8','7—8月'],['9-10','9—10月'],['11-12','11—12月'],['1-12','年度全校公示']]})+c.field('policy_id','已确认制度与校历','select','',{options:workspace.policies.filter(p=>p.state==='ACTIVE').map(p=>[p.id,p.name])}),v=>{const{window,...data}=v;const[start_month,end_month]=window.split('-').map(Number);return c.api('/social/reports',{method:'POST',body:{...data,start_month,end_month}})},{submit:'生成汇总',after:r=>r?.item?.id?showDetail('social_resource',r.item.id):null});
 if(action==='social-project-new')return projectForm();if(action==='social-project-edit')return projectForm(true);if(action==='social-policy-new')return policyForm();
 if(action==='social-export'){const[k,i]=id.split('|');return c.download(path(k,i)+'/export','社会培训办理材料.xlsx')}
 if(action==='social-course-resources'){const[code,p='1']=id.split('|'),result=await c.api('/social/courses/'+encodeURIComponent(code)+'/resources?page='+p);return c.modal('课程资源',c.table(['名称','类型','视频时长（分钟）','操作'],result.items.map(r=>[c.esc(r.name),c.esc({video:'视频',document:'文档',link:'其他链接'}[r.data.resource_type]),r.data.duration_minutes??'不适用',c.act('查看详情','social-detail','social_resource|'+r.id+'|'+encodeURIComponent(code)+'|'+p)])),(result.page>1?c.act('上一页','social-course-resources',code+'|'+(result.page-1)):'')+(result.page*result.size<result.total?c.act('下一页','social-course-resources',code+'|'+(result.page+1)):''))}
 if(action==='social-course-for-project'){const code=opened.item.data.code;return commonForm('登记本项目课程',c.note('课程将关联到本项目（'+code+'）。登记后，参训明细里的“课程编号”填这里的编号。')+c.field('code','课程编号')+c.field('name','课程名称'),v=>c.api('/social/courses',{method:'POST',body:{...v,project_code:code}}),{submit:'保存课程',reasonLabel:'办理说明',reasonDefault:'登记项目课程',reopen:true})}
 if(action==='social-course-new')return commonForm('登记培训课程',c.field('code','课程编号')+c.field('name','课程名称')+await projectPicker('project_code','code'),v=>c.api('/social/courses',{method:'POST',body:v}),{compact:true,submit:'保存课程'});
 if(['social-resource-new','social-resource-edit'].includes(action)){
  const edit=action==='social-resource-edit',x=edit?opened.item:null,old=x?{...x.data,name:x.name,code:x.code}:{},courseList=edit?opened.courseList:null;id=x?.kind||id;
  const f=(key,label,type='text',options={})=>c.field(key,label,type,old[key]??'',options);
  let body=(x?c.field('org_id','承办学院','select',x.org_id,{options:[[x.org_id,c.orgName(x.org_id)]]}):collegeField())+f('code','来源唯一编号','text',{readonly:edit})+f('name','名称')+f('location','地点或资源说明','textarea',{required:false})+f('recognition','认定或登记依据','textarea');
  if(id==='base')body+=c.field('onsite','基地类型','checkbox',old.onsite??true,{checkLabel:'校内基地（不勾选表示校外）'});
  if(id==='achievement')body+=c.field('level','成果等级','select',old.level||'school',{options:selectable(['national','province','school'])})+f('confirmed_on','成果正式认定日期','date',{required:false,hint:'日期待补时，不计年度分数'});
  if(id==='course_resource')body+=c.field('course_code','关联课程','select',old.course_code||'',{options:[...(old.course_code&&!workspace.courses.some(x=>x.code===old.course_code)?[[old.course_code,'原关联课程 · '+old.course_code]]:[]),...workspace.courses.map(x=>[x.code,x.name])]})+c.field('resource_type','资源类型','select',old.resource_type||'video',{options:[['video','视频'],['document','文档'],['link','其他链接']]})+f('resource_url','资源地址','url',{required:false})+f('duration_minutes','视频总时长（分钟）','number',{required:false,min:0,step:0.01})+c.field('teacher_id','归属教师及工号','select',old.teacher_id||'',{required:false,options:[['','尚未确认人员'],...(old.teacher_id&&!c.teachers.some(t=>t.id===old.teacher_id)?[[old.teacher_id,'原关联教师（保留）']]:[]),...c.teachers.map(t=>[t.id,t.name+' · '+t.staff_no])]});
  return commonForm((edit?'修改':'登记')+{base:'培训基地',achievement:'培训成果',course_resource:'课程资源'}[id],body,v=>c.api('/social/resources'+(x?'/'+x.id:''),{method:x?'PUT':'POST',body:{...v,kind:id,...(x?{expected_version:x.version}:{}),resource_url:v.resource_url||null,confirmed_on:v.confirmed_on||null,teacher_id:v.teacher_id||null}}),{compact:!edit,reopen:edit,submit:edit?'保存修改':'保存登记',after:r=>r?.item?.id?showDetail('social_resource',r.item.id,courseList):null});
 }
 if(['social-claim-new','social-claim-edit'].includes(action)){
  const x=action==='social-claim-edit'?opened.item:null;
  const policies=workspace.policies||[],auxRow=(r={})=>'<div class="aux-row"><input type="date" class="aux-date" aria-label="工作日期" value="'+c.esc(r.work_date||'')+'"><input type="number" class="aux-amount" aria-label="辅助积分" min="0" step="0.01" placeholder="积分" value="'+c.esc(r.amount??'')+'"><input class="aux-desc" aria-label="工作说明" maxlength="200" placeholder="做了什么辅助工作" value="'+c.esc(r.description||'')+'"><button type="button" class="btn text aux-del" aria-label="删除这一行">删除</button></div>';
  const picker=x?'':await projectPicker('project_id','id',true);
  // 没有可申报项目或学校还没登记口径时，只说明原因，不再弹出一整张填不了的表。
  if(!x&&(!projectChoice.total||!policies.length))return c.modal('本人积分申报','<div class="social-detail">'+c.note(!policies.length?'学校还没有登记积分认定口径，暂时不能申报。请联系学校社会培训管理员。':'你还没有可申报的项目。项目须由学院办完结项，且“参训明细”里登记了你的工号（授课或辅助）。项目还在办理中的，等学院结项后再来申报；如有遗漏，请联系学院补录参训明细。',true)+'</div>',c.act('知道了','close','','primary'));
  let body=(x?c.note('项目与周期保留原申报；修改后重新审核。'):picker)+policyFields(x)+(x?c.field('recognition_form_reference','学校制式积分认定表及附件对应说明','textarea',x?.data.recognition_form_reference||'',{hint:'写明认定表编号或附件名称；认定表扫描件在详情里“上传佐证”。'}):c.field('file','学校制式积分认定表（拍照或扫描）','file','',{accept:'.pdf,.png,.jpg,.jpeg',full:true,hint:'支持 .jpg、.png、.pdf，单个文件最大 10 兆字节。有多页或其他附件，提交后可在详情里继续“上传佐证”。'}))
   +'<div class="form-field full"><label>辅助工作积分（没有可不填）</label><div id="aux-rows" class="aux-rows">'+(x?.data.auxiliary||[]).map(auxRow).join('')+'</div><button type="button" class="btn light sm" id="aux-add">＋ 添加一行辅助工作</button><p class="hint">每行一项：日期、积分、工作说明。授课积分按参训明细自动核算，不用在这里填。</p></div>';
  setTimeout(()=>{const box=typeof document!=='undefined'&&document.getElementById('aux-rows');if(!box)return;document.getElementById('aux-add')?.addEventListener('click',()=>{box.insertAdjacentHTML('beforeend',auxRow());box.lastElementChild.querySelector('input')?.focus()});box.addEventListener('click',e=>{if(e.target.closest('.aux-del'))e.target.closest('.aux-row').remove()});for(const id of ['f-period_id','f-policy_id']){const el=document.getElementById(id);if(el&&el.options.length===1)el.value=el.options[0].value}},0);
  if(!x)body+=c.field('submit_now','提交方式','checkbox',true,{required:false,checkLabel:'保存后直接提交审批（不勾选则先存为草稿）',full:true});
  return commonForm(x?'补正本人积分':'本人积分申报',body,async(v,f)=>{const{auxiliary_rows='',file:_file,submit_now,...data}=v;const file=!x&&f?.querySelector('#f-file')?.files?.[0];if(!x&&!file)throw Error('请选择积分认定表的照片或扫描件');if(file&&!/\.(pdf|png|jpe?g)$/i.test(file.name))throw Error('认定表只能是 .jpg、.png 或 .pdf 文件');if(file&&file.size>10*1024*1024)throw Error('认定表文件超过 10 兆字节，请压缩或分页后再传');if(file&&!data.recognition_form_reference)data.recognition_form_reference=file.name;const domRows=f?[...f.querySelectorAll('.aux-row')].map((r,i)=>({work_date:r.querySelector('.aux-date').value,amount:r.querySelector('.aux-amount').value,description:r.querySelector('.aux-desc').value.trim(),row:i+1})).filter(r=>r.work_date||r.amount||r.description):null;const auxiliary=domRows?domRows.map(({row,...r})=>{if(!r.work_date||r.amount===''||!r.description)throw Error('辅助工作第'+row+'行的日期、积分、说明都要填写；不需要的行请删除');return r}):auxiliary_rows.trim()?auxiliary_rows.trim().split(/\r?\n/).map(line=>{const[work_date,amount,description,...extra]=line.split('\t');if(!description||extra.length)throw Error('辅助工作每行须为日期、积分、说明三列');return {work_date,amount,description}}):[];const r=await c.api('/social/claims'+(x?'/'+x.id:''),{method:x?'PUT':'POST',body:{...data,...(x?{project_id:x.project_id,period_id:x.period_id,expected_version:x.version}:{}),auxiliary}});if(x||!r?.item?.id)return r;
   // 老师一步办完：建申报 → 传认定表 → 直接提交审批；中途失败就留成草稿，告诉老师在详情里接着办。
   try{const fd=new FormData();fd.set('file',file);fd.set('reason','本人上传积分认定表');fd.set('expected_version',String(r.item.version));await c.api('/attachments/social_claim/'+r.item.id,{method:'POST',body:fd});
    if(submit_now){await c.api('/social/claims/'+r.item.id+'/actions',{method:'POST',body:{action:'submit',expected_version:r.item.version+1,reason:data.reason||'提交本人积分申报',basis:data.basis||''}});c.toast('已提交审批，院长初审后会继续往下走')}else c.toast('已保存草稿，可在详情里提交')}
   catch(err){c.toast('申报已存为草稿，但'+(err.message||'认定表或提交没有完成')+'；请在打开的详情里接着办',true)}
   return r},x?{reopen:true,reasonLabel:'补正说明',reasonDefault:'按退回意见补正'}:{submit:'申报',reasonLabel:'申报说明',reasonDefault:'申报本人社会培训积分',compact:true,hint:'选项目、拍认定表、点“申报”就办完了；说明已预填，可不改。',after:r=>r?.item?.id?showDetail('social_claim',r.item.id):null});
 }
 if(['social-annual-new','social-annual-edit'].includes(action)){
  const x=action==='social-annual-edit'?opened.item:null,old=x?.data||{};
  const n=(key,label)=>c.field(key,label,'number',old[key]??'',{required:false,min:0,step:key==='other_bonus'?0.01:1}),t=(key,label,required=false)=>c.field(key,label,'textarea',old[key]||'',{required,full:true});
  let body=formSection('一、学院与认定周期',(x?c.note('保留当前学院和周期，补正后重新提交。'):collegeField())+policyFields(x))
   +formSection('二、年度任务与自评',n('income_target','到账收入目标')+n('participants_target','有效人次目标')+n('priority_target','重点群体人次目标')+n('staff_denominator','组织人数基准')+t('target_reference','年度任务下达依据')+t('staff_basis','组织人数依据')+t('self_report','单位自评报告',true))
   +formSection('三、加分与合规事项',n('other_bonus','其他加分')+t('other_bonus_basis','其他加分依据')+n('compliance_failures','其他已确认不合规次数（不含项目结算核验）')+t('discipline_reference','正式处理或处分依据')+c.field('confirmed_veto','一票否决','checkbox',old.confirmed_veto||false,{checkLabel:'已取得正式处理依据，确认一票否决'}),'没有加分或其他不合规事项可留空；项目结算问题不在这里重复登记。');
  return commonForm('学院年度自评',body,v=>{let{org_id,period_id,policy_id,reason,basis,...data}=v;if(x){org_id=x.org_id;period_id=x.period_id}data={...data,compliance_scope:'other_only',compliance_failures:data.compliance_failures??0,other_bonus:data.other_bonus??0};return c.api('/social/annuals'+(x?'/'+x.id:''),{method:x?'PUT':'POST',body:{org_id,period_id,policy_id,reason,basis,...(x?{expected_version:x.version}:{}),data:{...data,achievements:workspace.resources.filter(r=>{const period=c.periods.find(p=>p.id===period_id),date=r.data.confirmed_on;return r.kind==='achievement'&&r.org_id===org_id&&r.data.source!=='satisfaction'&&date&&period&&date>=period.start_date&&date<=period.end_date}).map(r=>({reference:r.code,name:r.name,level:r.data.level,confirmed_on:r.data.confirmed_on,recognition_reference:r.data.recognition}))}}})},x?{reopen:true}:{submit:'保存自评',hint:'保存后会打开自评，上传自评材料后点“提交学院自评”。',after:r=>r?.item?.id?showDetail('social_annual',r.item.id):null});
 }
 if(action==='social-transition'){
  if(id==='submit'&&opened.item.kind!=='point_report'&&!(opened.attachments||[]).length&&c.can('file.write'))return c.modal('先补充佐证材料',c.note('上传项目或申报材料后，再提交审核。',true),c.act('返回详情','social-detail',opened.kind+'|'+opened.id)+c.act('上传佐证','social-upload','','primary'));
  const x=opened.item,label=opened.labels?.[id]||'办理确认',back=['return','refile','dispute','explain','dismiss','withdraw','void'].includes(id),reasons={submit:'材料已备齐，提交审核',approve:'审核通过',file:'材料齐全，同意备案',close:'结项材料核验通过',archive:'公示期满，予以归档',activate:'按学校书面确认启用',record_basis:'登记学校书面确认依据',send:'核对材料已上传，请老师核对回应',agree:'同意按核对意见更正',uphold:'经核实确有错误，按核对意见更正',publish:'委员会评分完成',finance:'财务核验通过',academic:'成果核验通过',discipline:'纪检核验无异议',coordinator:'归口初核通过'};return commonForm(label,(id==='submit'&&(opened.trial?.blockers||[]).length?c.note('系统检查发现以下问题，提交会被拦下，请先处理：'+opened.trial.blockers.join('；'),true):'')+(['submit','activate','send'].includes(id)&&x.kind!=='point_report'&&!(opened.attachments||[]).length?c.note('还没有上传佐证材料，这一步会被系统拦下。请点“返回详情”，先“上传佐证”，再来办理。',true):'')+c.note('当前状态：'+opened.state_label+(back?'。请写清原因，对方会看到这段说明。':''))+(id==='file'&&(x.data.category==='subsidy'||x.data.high_risk)?c.field('prior_review_on','正式前置审核日期','date'):''),async v=>{const route=opened.kind==='social_resource'?({correction:'corrections',point_review:'point-reviews'}[x.kind]||'reports'):{social_project:'projects',social_claim:'claims',social_annual:'annuals',social_policy:'policies'}[opened.kind];await c.api('/social/'+route+'/'+x.id+'/actions',{method:'POST',body:{...v,expected_version:x.version,action:id}})},{submit:(/^确认/.test(label)?'':'确认')+label.replace(/（.*$/,''),reasonLabel:back?({return:'退回原因（告诉对方要补什么）',explain:'说明情况（学院院长会看到）',dismiss:'维持原认定的理由（双方都会看到）',withdraw:'撤回原因',void:'作废原因（原认定保留，重新核对须再次取得确认）'}[id]||'说明'):'办理意见',reasonDefault:(id==='approve'&&opened.archiveStep?'审核材料齐全，归档入账':reasons[id])||'',reopen:true,...(id==='record_basis'?{basisLabel:'学校书面依据文号',basisRequired:true}:id==='resolve'?{basisLabel:'异议核实结论与依据',basisRequired:true}:id==='file'&&(x.data.category==='subsidy'||x.data.high_risk)?{basisLabel:'前置审核依据',basisRequired:true}:{})});
 }
 if(action==='social-upload'){
  const x=opened.item,k=opened.kind;return commonForm('上传社会培训佐证',c.field('file','选择佐证文件','file','',{accept:'.pdf,.png,.jpg,.jpeg'}),async(v,f)=>{const data=new FormData(f);data.set('expected_version',String(x.version));await c.api('/attachments/'+k+'/'+x.id,{method:'POST',body:data})},{submit:'上传',reasonLabel:'材料说明',reasonDefault:'补充佐证材料',reopen:true});
 }
 if(action==='social-close'){
  const subsidy=opened.item.data.category==='subsidy',wrap=(id,html)=>'<div class="social-cond" id="cond-'+id+'" style="display:contents">'+html+'</div>';
  let body=(!(opened.attachments||[]).length?c.note('还没有上传结项佐证材料，提交会被系统拦下。请点“返回详情”，先“上传佐证”（签到表、成果报告、财务凭证等）。',true):'')+formSection('一、结项情况',c.field('closed_on','结项日期','date')+c.field('satisfaction','满意度（百分比）','number','',{min:0,max:100,step:0.01})+c.field('location','培训地点类型','select','onsite',{options:[['onsite','校内'],['offsite','校外']]})+c.field('outcome_report','成果报告','textarea','',{full:true}))
   +formSection('二、经费与财务核验',c.field('actual_income','财务确认到账收入（元）','number',0,{min:0,step:0.01})+c.field('funding_source','财务确认的资金来源','select','',{required:false,options:[['','请确认资金来源（非零收入必填）'],['other_training','其他培训收入'],['government_special','政府专项培训资金']]})+c.field('finance_reference','财务核验凭据')+c.field('implicit_cost','隐性成本（元）','number',0,{min:0,step:0.01})+c.field('settlement_on','经费结算日期','date','',{required:false})
    +wrap('split',c.field('retained','学校留存（元）','number','',{min:0,step:0.01,required:false})+c.field('personnel','校内人员支出（元）','number','',{min:0,step:0.01,required:false})+'<p class="hint full" id="close-split-hint"></p>')
    +wrap('special',c.field('funding_basis','政府专项主管部门规定及财务核验依据','textarea','',{required:false,full:true,hint:'专项资金有收入时必填；按主管部门规定专款专用，不套用其他收入比例'})),'其他培训收入分配：校内留存不低于20%、人员支出不高于60%；校外留存不低于10%、人员支出不高于70%；项目公用20%。非零其他收入两项金额必填，零收入可留空。政府专项按主管部门规定核验。')
   +(subsidy?formSection('三、补贴项目专项材料',c.field('province_receipt','省平台报送凭证','textarea','',{required:false})+c.field('special_evidence','专项参训与成果材料','textarea','',{required:false}),'补贴性培训须登记省平台报送凭证和专项材料，否则结项核验不能通过。'):'')
   +wrap('rect',formSection('整改（满意度低于85%时填写）',c.field('rectification','整改报告与期限','textarea','',{required:false})+c.field('rectification_due','整改办理期限','date','',{required:false})))
   +formSection('结项材料核对','<div class="form-field full"><label class="flex" style="gap:8px;font-weight:600"><input type="checkbox" id="close-check-all">以下材料全部已核对</label></div>'+Object.entries({plan:'培训方案',filing_form:'学校制式备案登记表',roster:'学员名册',attendance:'实名签到',hours:'学时记录',process:'培训过程影像',assessment:'结业考核',outcomes:'培训成果'}).map(([k,l])=>c.field('checked_'+k,l+'已核对','checkbox',false)).join(''),'逐项对照纸质或电子材料核对后勾选。');
  setTimeout(()=>bindCloseForm(),0);
  return commonForm('提交项目结项',body,v=>{const{reason,basis,...raw}=v;const materials_checked=Object.keys(raw).filter(k=>k.startsWith('checked_')&&raw[k]).map(k=>k.slice(8));for(const k of Object.keys(raw))if(k.startsWith('checked_'))delete raw[k];raw.materials_checked=materials_checked;raw.funding_source=raw.funding_source||null;raw.rectification_due=raw.rectification_due||null;for(const k of ['retained','personnel'])if(raw[k]===''||raw[k]==null)delete raw[k];return c.api('/social/projects/'+opened.id+'/actions',{method:'POST',body:{reason,basis,expected_version:opened.item.version,action:'close_submit',closeout:{...raw,settlement_on:raw.settlement_on||null}}})},{reopen:true,submit:'提交结项核验',reasonLabel:'办理说明',reasonDefault:'项目已完成，提交结项核验'});
 }

 if(action==='social-unit-import'){
  const header='单元编号\t课程编号\t班级编号\t模块名称\t培训日期\t学员编号\t本校全日制生\t准毕业生例外\t实名签到\t学时达标\t全程参训\t结业通过\t重点群体\t剔除原因\t教师工号\t岗位\t人员类型\t佐证说明';
  const code=opened.item.data.code,list=await c.api('/social/workspace?section=courses&q='+encodeURIComponent(code)).then(w=>(w.courses?.items||w.courses||[]).filter(x=>x.project_code===code)).catch(()=>[]);
  setTimeout(()=>typeof document!=='undefined'&&document.getElementById('unit-template')?.addEventListener('click',()=>{const sample=['U001','C001','B01','模块一','2026-09-10','S0001','否','否','是','是','是','是','否','','J001','主讲','校内','签到表第1页'];const blob=new Blob(['\ufeff'+header.split('\t').join(',')+'\r\n'+sample.join(',')+'\r\n'],{type:'text/csv;charset=utf-8'}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='参训明细导入模板.csv';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),5000)}),0);
  const courseNote=list.length?c.note('本项目已登记课程（“课程编号”列填这些编号）：'+list.map(x=>x.code+' '+x.name).join('；')):c.note('本项目还没有登记课程，参训明细里的课程编号无处关联。请先点下面“返回详情”，再点“登记本项目课程”。',true);
  return commonForm('导入参训明细',courseNote+c.note('三步完成：①下载模板，用 Excel 打开，删掉示例行后按行填写（每位学员每个单元一行）；②另存为 CSV 后在下面选择文件，或直接从 Excel 复制整表粘贴；③先预检，确认人数无误后再入库。判断项填“是/否”，学员编号用学校内部编号，不填身份证号；同一项目同一学员跨班仍须用同一编号，人天式同一天只计一次。',false,'填写与计数说明')+'<div class="form-field full"><button type="button" class="btn light" id="unit-template">下载导入模板</button><p class="hint">岗位填：主讲 / 实训指导 / 管理辅助；人员类型填：校内 / 外聘。多人同堂使用相同单元编号。</p></div>'+c.field('file','选择填好的逗号分隔表格','file','',{required:false,accept:'.csv,.txt,.tsv'})+c.field('rows','或粘贴电子表格内容（含表头）','textarea',header,{rows:8,full:true,required:false}),async(v,f)=>{
   const file=f?.querySelector('input[type=file]')?.files?.[0],text=file?await readImportFile(file):v.rows;
   const rows=parseTrainingRows(text,opened.item.data.mode,c.teachers),body={rows,expected_version:opened.item.version,reason:v.reason,basis:v.basis};const preview=await c.api('/social/projects/'+opened.id+'/units/preview',{method:'POST',body});
   const projectId=opened.id;setTimeout(()=>c.formModal('确认参训明细入库',c.note('预检通过：'+preview.rows+'个核算单元，有效'+preview.effective+'人次，剔除'+preview.excluded+'人次。'),async()=>{await c.api('/social/projects/'+projectId+'/units/confirm',{method:'POST',body:{...body,preview_hash:preview.preview_hash}});c.closeModal();await c.render();await showDetail('social_project',projectId).catch(()=>{})},{submit:'确认整批入库',returnLabel:'返回修改',returnTo:async()=>{await socialAction('social-unit-import','',c);for(const [key,value]of Object.entries({rows:text,reason:v.reason,basis:v.basis})){const el=document.getElementById('f-'+key);if(el)el.value=value||''}}}),0);
  },{submit:'先预检',reasonLabel:'办理说明',reasonDefault:'导入参训明细',reopen:true,after:()=>{}});
 }
 if(action==='social-duties'){
  const [duties,users]=await Promise.all([c.api('/social/duties'),c.api('/users?size=200')]);
  const fields=Object.entries(duties.labels).map(([k,l])=>c.field(k,l+'（每行一个账号）','textarea',(duties.assignments[k]||[]).map(id=>users.items.find(u=>u.id===id)?.username||'').join('\n'),{required:false})).join('');
  return commonForm('学校社会培训审批职责',fields,v=>{const{reason,basis,...raw}=v,assignments={};for(const[k,value]of Object.entries(raw)){assignments[k]=value.split(/\s+/).filter(Boolean).map(name=>{const user=users.items.find(u=>u.username===name);if(!user)throw Error('未找到授权账号：'+name);return user.id})}return c.api('/social/duties',{method:'PUT',body:{reason,basis,expected_version:duties.version,assignments}})});
 }
 if(action==='social-note'){
  const finance=workspace.my_duties.includes('finance'),coordinator=workspace.my_duties.includes('coordinator'),discipline=workspace.my_duties.includes('discipline');
  const kinds=[...(coordinator?[['complaint','投诉'],['rectification','整改'],['settlement','结算']]:finance?[['settlement','结算']]:[]),...(discipline?[['violation','登记正式处理决定']]:[])];
  return commonForm('投诉与项目跟踪',c.field('case_reference','跟踪事项编号（再次办理使用相同编号）')+c.field('due_on','整改或结算办理期限','date','',{required:false})+c.field('kind','跟踪类型','select',kinds[0]?.[0]||'',{options:kinds})+(finance?c.field('settlement_result','结算财务核验结论（仅结算事项填写）','select','',{required:false,options:[['','待核验／不适用'],['noncompliant','确认不合规，计入结算扣分'],['exempt','已有正式批准的例外，本次不扣分']],hint:'认定须在下方填写财务核验或例外批准依据；同一项目结算不要重复填入年度其他不合规次数。'}):'')+(workspace.my_duties.includes('discipline')?c.field('invalidate_cohort','正式决定作废本期人次','checkbox',false)+c.field('annual_veto','正式决定触发学院年度否决','checkbox',false):'')+c.field('received_on','受理日期','date')+c.field('investigation_on','开始调查日期','date','',{required:false})+c.field('completed_on','办结日期','date','',{required:false})+c.field('major','重大投诉','checkbox',false)+c.field('reply','书面回复','textarea','',{required:false})+c.field('policy_id','已确认工作日历','select','',{options:workspace.policies.filter(p=>p.state==='ACTIVE').map(p=>[p.id,p.name])}),v=>c.api('/social/projects/'+opened.id+'/notes',{method:'POST',body:{...v,settlement_result:v.settlement_result||null,due_on:v.due_on||null,investigation_on:v.investigation_on||null,completed_on:v.completed_on||null,expected_version:opened.item.version}}),{reopen:true});
 }
}
