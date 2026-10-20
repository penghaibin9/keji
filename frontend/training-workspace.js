// Shared master/detail surface; all mutations still use the existing business handlers.
const state = new Map();
const labels = {projects:'培训项目',courses:'培训课程',bases:'培训基地',trainers:'培训师资',records:'培训数据',outcomes:'培训成果'};
const descriptions = {projects:'从项目申报到备案结项，进度与材料一目了然',courses:'课程资料与教学资源集中管理',bases:'场地信息、认定材料与使用范围集中管理',trainers:'师资资格、专业方向与认定材料集中查阅',records:'授课明细与取数依据，逐条核对有据可查',outcomes:'成果认定、归属与证明材料集中管理'};
const states={DRAFT:'草稿',RETURNED:'退回补正',COLLEGE:'待学院审批',SUBMITTED:'待审核备案',FILED:'已备案',CLOSE_COLLEGE:'待学院结项核验',CLOSE_REVIEW:'待结项核验',CLOSED:'已结项',ACTIVE:'已认定',ARCHIVED:'已归档'};
const modes={lecture:'讲授',practice:'实训实操',case:'案例研讨',onsite:'现场教学',online:'线上自学'};
const categoryLabels={subsidy:'补贴性培训',enterprise:'企业定制培训',community:'社区公益培训',rural:'乡村帮扶培训',other:'其他非学历培训'};
const levels={national:'国家级',province:'省级',school:'校级'};
const ideology={ideology_course:'思政课程',course_ideology:'课程思政',none:'无'};
const baseLevels={school:'校级',city:'市级',province:'省级及以上'};
const usages={practice:'实践教学基地',ideology:'思政实践教学基地'};
const CLOSING=['CLOSE_COLLEGE','CLOSE_REVIEW','CLOSED'];
const key=(section,c)=>`${c.me?.user?.id}|${c.me?.role?.kind}|${section}`;
export function trainingState(section,c){const k=key(section,c);if(!state.has(k))state.set(k,{selected:'',tab:'',q:'',org:'',package:false,oneSkill:false});const s=state.get(k);if(section==='projects'&&c.setProjectViewState)Object.assign(s,{q:c.filter?.q||'',org:c.filter?.org_id||'',tab:c.filter?.project_status||'',selected:c.filter?.project_pick||''});return s}
export function trainingChange(section,c,action,value){const s=trainingState(section,c);if(action==='pick')s.selected=value;else if(action==='tab'){s.tab=value;s.selected=''}else if(action==='reset')Object.assign(s,{q:'',org:'',tab:'',package:false,oneSkill:false,selected:''});else if(action==='filter')Object.assign(s,value,{selected:''});if(section==='projects')c.setProjectViewState?.(s);}
const text=v=>v===0?'0':v==null||v===''?'待补充':String(v);
const imageUrl=id=>typeof id==='string'&&/^[A-Za-z0-9-]{8,36}$/.test(id)?'/api/social/images/'+id:'';
const typeIcon={projects:'book',courses:'book',bases:'school',outcomes:'award',trainers:'users'};
function collegeName(id,c){let o=c.orgs?.find(x=>x.id===id);const seen=new Set();while(o&&o.kind!=='college'&&!seen.has(o.id)){seen.add(o.id);o=c.orgs.find(x=>x.id===o.parent_id)}return o?.name||''}
// 没有上传图片时显示业务类型图标，不用示意照片冒充真实场景。
function cover(row,section,c,large=false){
 const e=c.esc,source=imageUrl(row.image);
 if(section==='trainers')return source?`<img class="tw-avatar${large?' large':''}" src="${e(source)}" alt="${e(row.name)}的照片" loading="lazy">`:`<div class="tw-avatar${large?' large':''}" aria-label="尚未上传照片">${c.icon('users')}</div>`;
 return source?`<figure class="tw-cover${large?' large':''}"><img src="${e(source)}" alt="${e(row.name)}" loading="lazy"></figure>`:`<figure class="tw-cover tw-cover-empty${large?' large':''}" aria-label="暂无封面">${c.icon(typeIcon[section]||'file')}<figcaption>暂无封面</figcaption></figure>`;
}
export function trainingModels(section,w,c){
 const org=x=>x.org_name||collegeName(x.org_id,c)||c.orgName?.(x.org_id)||'所属学院待补充';
 if(section==='projects')return (w.projects||[]).map(x=>({id:x.id,name:x.data.name,code:x.data.code,org:org(x),orgId:x.org_id,status:x.state_label||states[x.state]||'待核对',state:x.state,category:x.data.category,date:[x.data.start_date,x.data.end_date].filter(Boolean).join(' — '),image:x.data.cover_id,imageTarget:['project',x.id,x.version],detailAction:'social-detail',detailId:'social_project|'+x.id,raw:x}));
 if(section==='courses')return (w.courses||[]).map(x=>{const info=w.course_info?.[x.code]||{},project=(w.projects||[]).find(p=>p.data.code===x.project_code);return {id:x.code,name:x.name,code:x.code,org:info.org_name||project?.org_name||collegeName(project?.org_id,c)||'所属学院待补充',orgId:project?.org_id||info.org_id,subtitle:project?.data.name||(x.project_code?'项目名称待核对':'未关联项目'),image:info.cover_id,imageTarget:info.info_id?['resource',info.info_id,info.version]:null,info,stats:w.course_stats?.[x.code]||{},category:info.category||'',detailAction:'social-course-view',detailId:x.code,raw:x}});
 if(section==='bases'||section==='outcomes')return (w.resources||[]).filter(x=>x.kind===(section==='bases'?'base':'achievement')).map(x=>({id:x.id,name:x.name,code:x.code,org:org(x),orgId:x.org_id,status:x.state_label||states[x.state]||'已登记',state:x.state,category:section==='bases'?(x.data.onsite===false?'external':x.data.onsite===true?'internal':'unknown'):x.data.level,image:x.data.cover_id,photos:x.data.photo_ids||[],imageTarget:['resource',x.id,x.version],detailAction:'social-detail',detailId:'social_resource|'+x.id,raw:x}));
 if(section==='trainers')return (w.items||[]).map(x=>({id:x.id,name:x.name,code:x.staff_no||x.code||'',org:(x.source==='external'?x.unit:x.org_name)||x.org_name||x.unit||'所属单位待补充',orgId:x.source==='external'?'':x.org_id,category:x.source,status:x.source==='external'?'外聘已备案':'校内已认定',subtitle:x.title||'',image:x.photo_id,imageTarget:x.version?['resource',x.id,x.version]:null,detailAction:x.can_view_detail?'app-detail':'',detailId:x.id,raw:x}));
 return (w.items||[]).map(x=>({id:x.id,name:x.project||'培训项目待核对',code:x.project_code,org:x.org_name||collegeName(c.teachers?.find(t=>t.id===x.teacher_id)?.org_id,c)||'所属学院待补充',orgId:x.org_id,subtitle:x.course||'',date:x.event_date,detailAction:'record',detailId:x.id,raw:x}));
}
function tabs(section){return {projects:[['','全部项目'],['pending','待审批'],['FILED','已备案'],['closing','待结项'],['CLOSED','已结项']],courses:[],bases:[['','全部基地'],['internal','校内基地'],['external','校外共建']],trainers:[['','全部师资'],['internal','校内教师'],['external','外聘培训师']],outcomes:[['','全部成果'],['national','国家级'],['province','省级'],['school','校级']],records:[]}[section]}
const orgKey=r=>r.orgId||r.org;
export function filterTrainingRows(rows,s,section){return rows.filter(r=>{
 if(s.q&&!`${r.name} ${r.code||''} ${r.org} ${r.subtitle||''}`.toLowerCase().includes(s.q.toLowerCase()))return false;
 if(s.org&&orgKey(r)!==s.org&&r.org!==s.org)return false;
 if(s.package&&!r.info?.package||s.oneSkill&&!r.info?.one_skill)return false;
 if(!s.tab)return true;
 // 待审批只算已提交、等待学院或学校办理的项目；草稿和退回补正不在其中。
 if(section==='projects')return s.tab==='pending'?['COLLEGE','SUBMITTED'].includes(r.state):s.tab==='closing'?['CLOSE_COLLEGE','CLOSE_REVIEW'].includes(r.state):r.state===s.tab;
 return r.category===s.tab;
})}
const meta=(icon,value,c)=>`<p class="tw-meta">${c.icon(icon)}<span>${c.esc(text(value))}</span></p>`;
const facts=(rows,c)=>`<dl class="tw-facts">${rows.map(([k,v])=>`<div><dt>${c.esc(k)}</dt><dd>${c.esc(text(v))}</dd></div>`).join('')}</dl>`;
const badge=(r,c)=>r.status?`<span class="tw-status ${['ACTIVE','CLOSED','ARCHIVED'].includes(r.state)?'is-ok':['RETURNED','CLOSE_REVIEW'].includes(r.state)||r.state==='DRAFT'&&r.status==='草稿'||r.status==='结项退回补正'?'is-wait':''}">${c.esc(r.status)}</span>`:'';
// 展示图片维护：记录负责人、申请人，或所属学院、学校有登记权限的账号；后端再次校验。
function canMaintainImage(row,c){
 if(!row.imageTarget)return false;
 const me=c.me||{},x=row.raw||{},d=x.data||{};
 if(row.imageTarget[0]==='project'&&x.owner_id===me.user?.id)return true;
 if(row.imageTarget[0]==='resource'&&[d.teacher_id,d.created_by,x.teacher_id].includes(me.user?.id))return true;
 return ['school','college'].includes(me.role?.kind)&&(!c.can||c.can('records.write'));
}
function imageTools(row,section,c){
 if(!canMaintainImage(row,c))return '';
 const [target,id,version]=row.imageTarget,label=section==='trainers'?'头像':'封面';
 let html=`<div class="tw-image-tools">${c.act((row.image?'更换':'上传')+label,'training-image',[target,id,'cover',version].join('|'),'')}${row.image?c.act('移除'+label,'training-image-remove',[target,id,'cover',row.image,version].join('|'),'text'):''}`;
 if(section==='bases')html+=(row.photos.length<6?c.act('添加场地照片','training-image',[target,id,'photo',version].join('|'),''):'');
 return html+`<p class="tw-note">图片选填，仅用于展示，不能代替认定或证明材料。</p></div>`;
}
function photoStrip(row,c){
 if(!row.photos?.length)return '';
 const remove=canMaintainImage(row,c);
 return `<h4>场地照片 · ${row.photos.length}</h4><div class="tw-photos">${row.photos.map(id=>`<figure><img src="${c.esc(imageUrl(id))}" alt="${c.esc(row.name)}场地照片" loading="lazy">${remove?c.act('移除','training-image-remove',['resource',row.id,'photo',id,row.imageTarget[2]].join('|'),'text'):''}</figure>`).join('')}</div>`;
}
function projectStage(x){
 // 申报 → 学院审批 → 学校备案 → 培训与结项；已结项时四步都完成。
 if(x.state==='CLOSED')return 4;
 return ['DRAFT','RETURNED'].includes(x.state)?0:x.state==='COLLEGE'?1:x.state==='SUBMITTED'?2:3;
}
function projectPrimary(row,c){
 const x=row.raw,school=c.me?.role?.kind==='school',college=c.me?.role?.kind==='college';
 const label=school&&x.state==='SUBMITTED'?'办理备案':school&&x.state==='CLOSE_REVIEW'?'办理结项核验':college&&['COLLEGE','CLOSE_COLLEGE'].includes(x.state)?'学院审批':x.state==='FILED'&&row.status!=='结项退回补正'&&(school||college||x.owner_id===c.me?.user?.id)?'查看与结项':'查看完整资料';
 return c.act(label,row.detailAction,row.detailId,'primary');
}
function preview(row,section,c){
 if(!row)return `<aside class="tw-detail"><h2>${{projects:'项目详情',courses:'课程详情',bases:'基地详情',trainers:'师资详情',records:'数据详情',outcomes:'成果详情'}[section]}</h2><div class="tw-empty">${c.icon('file')}<h3>选择一条记录</h3><p>详情与办理入口将在这里显示</p></div></aside>`;
 const e=c.esc,x=row.raw,d=x.data||{},title={projects:'项目详情',courses:'课程详情',bases:'基地详情',trainers:'师资详情',records:'数据详情',outcomes:'成果详情'}[section];
 let body=section==='records'?'':cover(row,section,c,true)+imageTools(row,section,c);
 body+=`<div class="tw-detail-name"><h3>${e(row.name)}</h3>${badge(row,c)}</div>`;
 if(section==='projects'){
  body+=facts([['项目编号',row.code],['承办学院',row.org],['负责人',c.teacherName(x.owner_id)],...(c.me?.role?.kind==='teacher'?[['我的角色',x.owner_id===c.me.user.id?'项目负责人':'参与教师']]:[]),['培训类别',categoryLabels[d.category]],['培训时间',row.date],['项目期次',x.cohort],['一人一技',d.one_skill?'是':'否'],['需要报省',d.province_report?'是':'否']],c);
  const stage=projectStage(x);
  body+=`<ol class="tw-progress">${['申报','学院审批','学校备案',x.state==='CLOSED'?'已结项':CLOSING.includes(x.state)?'结项核验':'培训与结项'].map((l,i)=>`<li class="${i<stage?'done':i===stage?'current':''}"><span>${i<stage?'✓':i+1}</span>${l}</li>`).join('')}</ol>`;
  // 结项前显示申报时的预计值，进入结项后显示核算出的有效人次和到账收入，并标明口径。
  const m=x.metrics||{},actual=CLOSING.includes(x.state);
  const people=actual?['有效人次',m.effective==null?'待核算':m.effective+' 人次']:['预计人次',d.expected_participants==null?'待补充':d.expected_participants+' 人次'];
  const income=actual?['到账收入',m.actual_income==null?(c.me?.role?.kind==='school'||c.me?.role?.kind==='college'?'待结项填报':'仅负责人可见'):m.actual_income+' 元']:['预计收入',d.expected_income==null?'待补充':d.expected_income+' 元'];
  body+=`<div class="tw-fact-grid">${[['clock','总学时',d.total_hours==null?'待补充':d.total_hours+' 学时'],['users',...people],['chart',...income],['book','课程',(m.courses??0)+' 门']].map(([i,k,v])=>`<div>${c.icon(i)}<span>${k}<strong>${e(text(v))}</strong></span></div>`).join('')}</div>`;
  body+=`<h4>项目材料</h4><div class="tw-resource">${c.icon('file')}${c.act('项目材料 · '+(m.materials??0)+' 份（方案、参训与结业材料）',row.detailAction,row.detailId,'text')}</div>`;
 }else if(section==='courses'){
  const i=row.info,st=row.stats;
  body+=facts([['所属学院',row.org],['课程编号',row.code],['关联项目',row.subtitle],['面向对象',i.audience],['思政属性',ideology[i.ideology]],['专项属性',[i.package?'培训包':'',i.one_skill?'“一人一技”':''].filter(Boolean).join('、')||'无'],...(i.one_skill?[['重点群体与行动对接',i.target_groups]]:[]),['课程简介',i.intro]],c);
  body+=`<div class="tw-fact-grid">${[['clock','学时',i.hours==null?'待补充':i.hours+' 学时'],['book','教学方式',modes[i.teaching_mode]||'待补充'],['users','主讲教师',i.teacher_name||'待补充'],['file','课件审查',i.courseware?.checked?'已审查':'待审查']].map(([ico,k,v])=>`<div>${c.icon(ico)}<span>${k}<strong>${e(v)}</strong></span></div>`).join('')}</div><h4>课程资源</h4>`;
  body+=[['video','视频',st.videos||0],['file','全部课程资源',st.resources||0]].map(([i,k,n])=>`<div class="tw-resource">${c.icon(i)}${c.act(k+' · '+n,'social-course-resources',row.id,'text')}</div>`).join('');
  if(!i.info_id&&canMaintainImage({...row,imageTarget:['resource','x',1]},c))body+=`<p class="tw-note">课程资料尚未补充，补充后可上传封面。</p>`;
 }else if(section==='bases'){body+=facts([['所属学院',row.org],['基地编号',row.code],['场地类型',d.onsite===false?'校外共建':d.onsite===true?'校内基地':'类型待补充'],['基地用途',(d.usages||[]).map(u=>usages[u]||u).join('、')||'待补充'],['基地级别',baseLevels[d.level]||'未标注'],['具体地点',d.location],['基地负责人',d.manager_name||d.teacher_name],['设立日期',d.established_on],['认定日期',d.recognized_on],['审批生效日期',d.effective_on||'尚未生效'],['共建单位',d.partner||(d.onsite===false?'待补充':'—')],['认定依据',d.recognition]],c);body+=photoStrip(row,c)}
 else if(section==='outcomes')body+=facts([['所属学院',row.org],...(c.me?.role?.kind==='school'&&!/^(SAT-|AUTO-)/.test(row.code||'')?[['成果编号',row.code]]:[]),['认定级别',levels[d.level]],['认定日期',d.confirmed_on],['认定依据',d.recognition]],c)+`<p class="tw-note">登记成果不直接计分，以年度考核核验结果为准。</p>`;
 else if(section==='trainers')body+=facts([['职称或岗位',x.title],[x.source==='external'?'工作单位':'所属学院',row.org],...(x.source==='external'?[['登记学院',x.org_name]]:[]),['专业特长',x.specialty],['培训业务类别',(x.directions||[]).join('、')],['授课课程',(x.courses||[]).join('、')||(x.source==='external'?'外聘培训师暂无关联课程':'暂无已入库的授课课程')],['来源',x.source==='external'?'外聘培训师':'校内教师'],['认定或备案日期',x.effective_on],['认定或备案依据',x.filing_basis],['省级推荐',x.recommended_province_on||'尚未推荐']],c);
 else body+=facts([['课程',x.course],['教师',c.teacherName(x.teacher_id)],['培训日期',x.event_date],['授课学时',text(x.hours)+' 学时'],['课程人次',text(x.participants)+' 人次'],['归属培训收入',text(x.income)+' 元'],['数据来源',x.source==='Excel导入'?'表格导入':x.source]],c)+`<p class="tw-note">课程人次用于数据核对，个人积分以审核归档为准。</p>`;
 const action=section==='projects'?projectPrimary(row,c):row.detailAction?c.act(section==='records'?'查看完整明细':section==='trainers'?'查看认定资料':'查看完整资料',row.detailAction,row.detailId,'primary'):'<p class="tw-note">当前身份仅可查看基础信息</p>';
 const extra=section==='courses'?c.act('查看资源','social-course-resources',row.id,'')+(row.info.application_id&&c.can?.('points.read')?c.act('积分办理','course-points',row.info.application_id):''):section==='trainers'&&c.me.role.kind==='school'&&!x.recommended_province_on?c.act('推荐省级','trainer-recommend',row.id):'';
 return `<aside id="training-detail" class="tw-detail" aria-label="${title}" tabindex="-1"><h2>${title}</h2>${body}<div class="tw-detail-actions">${action}${extra}</div></aside>`;
}
export function renderTrainingWorkspace(section,w,c,options={}){
 const e=c.esc,rows=trainingModels(section,w,c),s=trainingState(section,c);
 if(options.serverSearch!==undefined)s.q=options.serverSearch;
 const filtered=section==='records'?rows:filterTrainingRows(rows,s,section);
 const selected=filtered.find(r=>r.id===s.selected)||filtered[0];s.selected=selected?.id||'';
 const pick=(r,label='查看详情')=>['records','trainers'].includes(section)?`<button type="button" class="btn text tw-row-select" data-action="training-pick" data-id="${e(r.id)}" aria-pressed="${r.id===s.selected}" aria-controls="training-detail" aria-label="${e(label+'：'+r.name+(r.date?' · '+r.date:''))}">${e(label)}</button>`:c.act(label,'training-pick',r.id,'text');
 const orgs=[...new Map(rows.map(r=>[orgKey(r),r.org])).entries()].filter(([k])=>k);
 const filter=section==='records'?(options.filters||''):(!rows.length&&!s.q&&['teacher','dept','college'].includes(c.me?.role?.kind))?'':`<form id="social-search-form" class="tw-filters"><label class="tw-search">${c.icon('search')}<input id="social-query" name="q" maxlength="100" value="${e(s.q)}" aria-label="检索关键词" placeholder="${section==='trainers'?'搜索教师姓名或专业':'搜索'+labels[section].replace('管理','')+'名称或编号'}"></label><label class="tw-org">所属学院<select name="org" aria-label="所属学院"><option value="">全部学院</option>${orgs.map(([k,name])=>`<option value="${e(k)}"${k===s.org?' selected':''}>${e(name)}</option>`).join('')}</select></label><button type="submit" class="btn primary">查询</button>${c.act('重置','training-reset')}${options.serverSearch?c.act('清空检索','social-list-reset'):''} ${section==='courses'?`<div class="tw-filter-extra"><span>课程标记：</span><label><input type="checkbox" name="package"${s.package?' checked':''}> 培训包</label><label><input type="checkbox" name="oneSkill"${s.oneSkill?' checked':''}> 一人一技</label></div>`:''}</form>`;
 const categories=tabs(section),tabbar=categories.length?`<nav class="tw-tabs" aria-label="${labels[section]}分类">${categories.map(([v,l])=>`<button type="button" data-action="training-tab" data-id="${v}" aria-pressed="${s.tab===v}" class="${s.tab===v?'active':''}">${l}</button>`).join('')}</nav>`:'';
 let list='';
 if(section==='trainers'||section==='records'){
  const headers=section==='trainers'?['教师','所属学院或单位','培训业务类别','资格状态','操作']:['培训日期','项目 / 课程','教师','学时','课程人次','归属收入','来源','操作'];
  list=`<div class="tw-table-wrap"><table class="tw-table"><thead><tr>${headers.map(h=>`<th>${h}</th>`).join('')}</tr></thead><tbody>${filtered.map(r=>{const x=r.raw;const cells=section==='trainers'?[`<div class="tw-person">${cover(r,section,c)}<span><strong>${e(r.name)}</strong><small>${e(x.title||'')}</small></span></div>`,e(r.org),e((x.directions||[]).join('、')),badge(r,c),pick(r)+(x.can_view_detail?'':'<small>仅基础信息</small>')]:[e(x.event_date),`<strong>${e(r.name)}</strong><small>${e(r.subtitle)}</small>`,e(c.teacherName(x.teacher_id)),e(text(x.hours)),e(text(x.participants)),e(text(x.income))+'元',e(x.source==='Excel导入'?'表格导入':x.source),pick(r,'查看')];return `<tr class="${r.id===s.selected?'selected':''}">${cells.map((v,i)=>`<td data-label="${headers[i]}">${v}</td>`).join('')}</tr>`}).join('')}</tbody></table></div>`;
 }else list=`<div class="tw-list tw-${section}">${filtered.map(r=>{const d=r.raw.data||{};return `<article class="tw-item${r.id===s.selected?' selected':''}">${cover(r,section,c)}<div class="tw-item-copy"><div class="tw-item-head"><h3><button type="button" class="btn text tw-card-select" data-action="training-pick" data-id="${e(r.id)}" aria-pressed="${r.id===s.selected}" aria-controls="training-detail">${e(r.name)}</button></h3>${badge(r,c)}</div>${meta('org',r.org,c)}${section==='courses'?meta('file',r.subtitle,c):section==='projects'?meta('clock',r.date,c)+(r.code?`<p class="tw-code">编号：${e(r.code)}</p>`:''):section==='bases'?meta('map',d.location,c)+meta('clock','设立日期：'+text(d.established_on),c):`<p class="tw-meta">${e(levels[d.level]||'级别待确认')} · ${e(d.confirmed_on||'日期待补充')}</p><p class="tw-description">${e(d.recognition||'认定依据待补充')}</p>`}<div class="tw-item-actions">${pick(r,section==='courses'?'查看课程':'查看详情')}${section==='courses'?c.act('查看资源','social-course-resources',r.id,''):''}</div></div></article>`}).join('')}</div>`;
 if(!filtered.length)list=`<div class="tw-empty">${c.icon(section==='trainers'?'users':'file')}<h3>${s.q?'没有找到匹配的记录':rows.length?'没有符合条件的记录':'暂无'+labels[section].replace('管理','')+'记录'}</h3><p>${rows.length?'调整筛选条件后再试':'新增或审核通过后，资料将显示在这里。'}</p>${s.q?c.act('查看全部','social-list-reset'):rows.length?c.act('清除筛选','training-reset'):''}</div>`;
 const total=options.total??w.pagination?.total??w.total??rows.length,narrowed=Boolean(s.tab||s.org||s.package||s.oneSkill);
 // 学院、状态等筛选作用于当前已读取的记录；总数超过一页时如实提示，并保留翻页。
 const footer=options.pager||(!narrowed&&options.socialPager)||`<div class="tw-list-footer"><span>${narrowed?'筛选结果 '+filtered.length+' 条 · ':''}共 ${total} 条${narrowed&&total>rows.length?' · 学院和状态筛选仅作用于当前页 '+rows.length+' 条':''}</span>${options.socialPager||''}</div>`;
 return `<section class="training-workspace tw-section-${section}"><div class="tw-heading"><div><h1>${labels[section]}</h1><p>${descriptions[section]}</p></div><div class="tw-heading-actions">${options.actions||''}</div></div>${options.before||''}<div class="tw-layout"><div class="tw-main">${filter}${tabbar}${section==='records'?`<p class="tw-data-summary">本页 ${rows.length} 条记录 · ${rows.reduce((n,r)=>n+Number(r.raw.hours||0),0)} 学时 · ${rows.reduce((n,r)=>n+Number(r.raw.participants||0),0)} 课程人次</p>`:''}${list}${footer}${options.after||''}</div>${preview(selected,section,c)}</div></section>`;
}
