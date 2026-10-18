// Shared master/detail surface; all mutations still use the existing business handlers.
const state = new Map();
const labels = {projects:'培训项目管理',courses:'培训课程管理',bases:'培训基地管理',trainers:'培训师资库',records:'培训数据',outcomes:'培训成果'};
const descriptions = {projects:'从项目申报到备案结项，进度与材料一目了然',courses:'课程资料与教学资源集中管理',bases:'场地信息、认定材料与使用范围集中管理',trainers:'师资资格、专业方向与认定材料集中查阅',records:'授课明细与取数依据，逐条核对有据可查',outcomes:'成果认定、归属与证明材料集中管理'};
const states={DRAFT:'草稿',RETURNED:'退回补正',COLLEGE:'待学院审批',SUBMITTED:'待审核备案',FILED:'已备案',CLOSE_COLLEGE:'待学院结项核验',CLOSE_REVIEW:'待结项核验',CLOSED:'已结项',ACTIVE:'已认定',ARCHIVED:'已归档'};
const modes={lecture:'讲授',practice:'实训实操',case:'案例研讨',onsite:'现场教学',online:'线上自学'};
const categoryLabels={subsidy:'补贴性培训',enterprise:'企业定制培训',community:'社区公益培训',rural:'乡村帮扶培训',other:'其他非学历培训'};
const levels={national:'国家级',province:'省级',school:'校级'};
const key=(section,c)=>`${c.me?.user?.id}|${c.me?.role?.kind}|${section}`;
export function trainingState(section,c){const k=key(section,c);if(!state.has(k))state.set(k,{selected:'',tab:'',q:'',org:'',package:false,oneSkill:false});return state.get(k)}
export function trainingChange(section,c,action,value){const s=trainingState(section,c);if(action==='pick')s.selected=value;else if(action==='tab'){s.tab=value;s.selected=''}else if(action==='reset')Object.assign(s,{q:'',org:'',tab:'',package:false,oneSkill:false,selected:''});else if(action==='filter')Object.assign(s,value,{selected:''});}
const text=v=>v===0?'0':v==null||v===''?'待补充':String(v);
const safeImage=v=>typeof v==='string'&&(/^(https?:\/\/|\/assets\/|\/api\/)/.test(v))?v:'';
function collegeName(id,c){let o=c.orgs?.find(x=>x.id===id);const seen=new Set();while(o&&o.kind!=='college'&&!seen.has(o.id)){seen.add(o.id);o=c.orgs.find(x=>x.id===o.parent_id)}return o?.name||''}
function cover(row,section,c,large=false){
 const e=c.esc,source=safeImage(row.image),fallback={projects:/茶/.test(row.name)?'training-tea.png':'training-base.png',courses:'training-course.png',bases:'training-base.png',outcomes:/茶/.test(row.name)?'training-tea.png':'training-base.png'}[section];
 if(section==='trainers')return source?`<img class="tw-avatar${large?' large':''}" src="${e(source)}" alt="${e(row.name)}的照片">`:`<div class="tw-avatar${large?' large':''}" aria-label="尚未上传照片">${c.icon('users')}</div>`;
 return `<figure class="tw-cover${large?' large':''}"><img src="${e(source||'/assets/assets/'+fallback)}" alt="${e(source?row.name:'培训主题示意图')}" loading="lazy">${source?'':'<figcaption>示意图</figcaption>'}</figure>`;
}
export function trainingModels(section,w,c){
 const org=x=>x.org_name||collegeName(x.org_id,c)||c.orgName?.(x.org_id)||'所属学院待补充';
 if(section==='projects')return (w.projects||[]).map(x=>({id:x.id,name:x.data.name,code:x.data.code,org:org(x),orgId:x.org_id,status:x.state_label||states[x.state]||'待核对',state:x.state,category:x.data.category,date:[x.data.start_date,x.data.end_date].filter(Boolean).join(' — '),image:x.data.cover_url,detailAction:'social-detail',detailId:'social_project|'+x.id,raw:x}));
 if(section==='courses')return (w.courses||[]).map(x=>{const info=w.course_info?.[x.code]||{},project=(w.projects||[]).find(p=>p.data.code===x.project_code);return {id:x.code,name:x.name,code:x.code,org:info.org_name||project?.org_name||collegeName(project?.org_id,c)||'所属学院待补充',orgId:project?.org_id||info.org_id,subtitle:project?.data.name||(x.project_code?'项目名称待核对':'未关联项目'),image:info.cover_url||x.cover_url,info,stats:w.course_stats?.[x.code]||{},category:info.category||'',detailAction:'social-course-view',detailId:x.code,raw:x}});
 if(section==='bases'||section==='outcomes')return (w.resources||[]).filter(x=>x.kind===(section==='bases'?'base':'achievement')).map(x=>({id:x.id,name:x.name,code:x.code,org:org(x),orgId:x.org_id,status:x.state_label||states[x.state]||'已登记',state:x.state,category:section==='bases'?(x.data.onsite===false?'external':x.data.onsite===true?'internal':'unknown'):x.data.level,image:x.data.cover_url||x.data.photo_url,detailAction:'social-detail',detailId:'social_resource|'+x.id,raw:x}));
 if(section==='trainers')return (w.items||[]).map(x=>({id:x.id,name:x.name,code:x.staff_no||'',org:x.org_name||x.unit||'所属单位待补充',orgId:x.org_id,category:x.source,status:x.source==='external'?'备案有效':'已认定',subtitle:x.title||'',image:x.photo_url,detailAction:x.can_view_detail?'app-detail':'',detailId:x.id,raw:x}));
 return (w.items||[]).map(x=>({id:x.id,name:x.project||'培训项目待核对',code:x.project_code,org:x.org_name||collegeName(c.teachers?.find(t=>t.id===x.teacher_id)?.org_id,c)||'所属学院待补充',orgId:x.org_id,subtitle:x.course||'',date:x.event_date,detailAction:'record',detailId:x.id,raw:x}));
}
function tabs(section){return {projects:[['','全部项目'],['pending','待审批'],['FILED','已备案'],['closing','待结项'],['CLOSED','已结项']],courses:[['','全部资源'],['video','视频课程'],['package','培训包'],['oneSkill','一人一技']],bases:[['','全部基地'],['internal','校内基地'],['external','校外共建']],trainers:[['','全部师资'],['internal','校内教师'],['external','外聘培训师']],outcomes:[['','全部成果'],['national','国家级'],['province','省级'],['school','校级']],records:[]}[section]}
export function filterTrainingRows(rows,s,section){return rows.filter(r=>{
 if(s.q&&!`${r.name} ${r.code||''} ${r.org} ${r.subtitle||''}`.toLowerCase().includes(s.q.toLowerCase()))return false;
 if(s.org&&r.org!==s.org)return false;
 if(s.package&&!r.info?.package||s.oneSkill&&!r.info?.one_skill)return false;
 if(!s.tab)return true;
 if(section==='projects')return s.tab==='pending'?['DRAFT','RETURNED','COLLEGE','SUBMITTED'].includes(r.state):s.tab==='closing'?['CLOSE_COLLEGE','CLOSE_REVIEW'].includes(r.state):r.state===s.tab;
 if(section==='courses')return s.tab==='video'?Number(r.stats?.videos)>0:s.tab==='package'?r.info?.package:r.info?.one_skill;
 return r.category===s.tab;
})}
const meta=(icon,value,c)=>`<p class="tw-meta">${c.icon(icon)}<span>${c.esc(text(value))}</span></p>`;
const facts=(rows,c)=>`<dl class="tw-facts">${rows.map(([k,v])=>`<div><dt>${c.esc(k)}</dt><dd>${c.esc(text(v))}</dd></div>`).join('')}</dl>`;
const badge=(r,c)=>r.status?`<span class="tw-status ${['ACTIVE','CLOSED','ARCHIVED'].includes(r.state)?'is-ok':['RETURNED','DRAFT','CLOSE_REVIEW'].includes(r.state)?'is-wait':''}">${c.esc(r.status)}</span>`:'';
function preview(row,section,c){
 if(!row)return `<aside class="tw-detail"><h2>${{projects:'项目详情',courses:'课程详情',bases:'基地详情',trainers:'师资详情',records:'数据详情',outcomes:'成果详情'}[section]}</h2><div class="tw-empty">${c.icon('file')}<h3>选择一条记录</h3><p>详情与办理入口将在这里显示</p></div></aside>`;
 const e=c.esc,x=row.raw,d=x.data||{},title={projects:'项目详情',courses:'课程详情',bases:'基地详情',trainers:'师资详情',records:'数据详情',outcomes:'成果详情'}[section];
 let body=section==='records'?'':cover(row,section,c,true);
 body+=`<div class="tw-detail-name"><h3>${e(row.name)}</h3>${badge(row,c)}</div>`;
 if(section==='projects'){
  body+=facts([['项目编号',row.code],['承办学院',row.org],['负责人',c.teacherName(x.owner_id)],['培训类别',categoryLabels[d.category]],['培训时间',row.date]],c);
  const stage=['DRAFT','RETURNED'].includes(x.state)?0:x.state==='COLLEGE'?1:x.state==='SUBMITTED'?2:3;
  body+=`<ol class="tw-progress">${['申报','学院审批','学校备案',x.state==='CLOSED'?'已结项':'培训与结项'].map((l,i)=>`<li class="${i<stage?'done':i===stage?'current':''}"><span>${i+1}</span>${l}</li>`).join('')}</ol>`;
  body+=`<div class="tw-fact-grid">${[['clock','总学时',d.total_hours==null?'待补充':d.total_hours+' 学时'],['users','预计人次',d.expected_participants==null?'待补充':d.expected_participants+' 人次'],['chart','预计收入',d.expected_income==null?'待补充':d.expected_income+' 元'],['book','项目期次',x.cohort]].map(([i,k,v])=>`<div>${c.icon(i)}<span>${k}<strong>${e(text(v))}</strong></span></div>`).join('')}</div>`;
 }else if(section==='courses'){
  const i=row.info,st=row.stats;
  body+=facts([['所属学院',row.org],['关联项目',row.subtitle]],c);
  body+=`<div class="tw-fact-grid">${[['clock','学时',i.hours==null?'待补充':i.hours+' 学时'],['book','教学方式',modes[i.teaching_mode]||'待补充'],['users','主讲教师',i.teacher_name||'待补充'],['file','课件审查',i.courseware?.checked?'已审查':'待审查']].map(([ico,k,v])=>`<div>${c.icon(ico)}<span>${k}<strong>${e(v)}</strong></span></div>`).join('')}</div><h4>课程资源</h4>`;
  body+=[['video','视频',st.videos||0],['file','全部课程资源',st.resources||0]].map(([i,k,n])=>`<div class="tw-resource">${c.icon(i)}${c.act(k+' · '+n,'social-course-resources',row.id,'text')}</div>`).join('');
 }else if(section==='bases')body+=facts([['所属学院',row.org],['基地编号',row.code],['场地类型',d.onsite===false?'校外共建':d.onsite===true?'校内基地':'类型待补充'],['具体地点',d.location],['建立日期',d.established_on],['共建单位',d.partner||'—'],['认定依据',d.recognition]],c);
 else if(section==='outcomes')body+=facts([['所属学院',row.org],...(c.me?.role?.kind==='school'&&!/^(SAT-|AUTO-)/.test(row.code||'')?[['成果编号',row.code]]:[]),['认定级别',levels[d.level]],['认定日期',d.confirmed_on],['认定依据',d.recognition]],c)+`<p class="tw-note">登记成果不直接计分，以年度考核核验结果为准。</p>`;
 else if(section==='trainers')body+=facts([['职称或岗位',x.title],['所属学院或单位',row.org],['专业方向',(x.directions||[]).join('、')],['来源',x.source==='external'?'外聘培训师':'校内教师'],['认定或备案依据',x.filing_basis],['省级推荐',x.recommended_province_on||'尚未推荐']],c);
 else body+=facts([['课程',x.course],['教师',c.teacherName(x.teacher_id)],['培训日期',x.event_date],['授课学时',text(x.hours)+' 学时'],['课程人次',text(x.participants)+' 人次'],['归属培训收入',text(x.income)+' 元'],['数据来源',x.source==='Excel导入'?'表格导入':x.source]],c)+`<p class="tw-note">课程人次用于数据核对，个人积分以审核归档为准。</p>`;
 const action=row.detailAction?c.act(section==='records'?'查看完整明细':section==='projects'?'查看 / 办理':section==='trainers'?'查看认定资料':'查看完整资料',row.detailAction,row.detailId,'primary'):'<p class="tw-note">当前身份仅可查看基础信息</p>';
 const extra=section==='courses'?c.act('查看资源','social-course-resources',row.id,''):section==='trainers'&&c.me.role.kind==='school'&&!x.recommended_province_on?c.act('推荐省级','trainer-recommend',row.id):'';
 return `<aside class="tw-detail" aria-label="${title}" tabindex="-1"><h2>${title}</h2>${body}<div class="tw-detail-actions">${action}${extra}</div></aside>`;
}
export function renderTrainingWorkspace(section,w,c,options={}){
 const e=c.esc,rows=trainingModels(section,w,c),s=trainingState(section,c);
 if(options.serverSearch!==undefined)s.q=options.serverSearch;
 const filtered=section==='records'?rows:filterTrainingRows(rows,s,section);
 const selected=filtered.find(r=>r.id===s.selected)||filtered[0];s.selected=selected?.id||'';
 const pick=(r,label='查看详情')=>c.act(label,'training-pick',r.id,'text');
 const orgs=[...new Set([...rows.map(r=>r.org),s.org].filter(Boolean))];
 const filter=section==='records'?(options.filters||''):(!rows.length&&!s.q&&['teacher','dept','college'].includes(c.me?.role?.kind))?'':`<form id="social-search-form" class="tw-filters"><label class="tw-search">${c.icon('search')}<input id="social-query" name="q" maxlength="100" value="${e(s.q)}" aria-label="检索关键词" placeholder="${section==='trainers'?'搜索教师姓名或专业':'搜索'+labels[section].replace('管理','')+'名称或编号'}"></label><label class="tw-org">所属学院<select name="org" aria-label="所属学院"><option value="">全部学院</option>${orgs.map(o=>`<option value="${e(o)}"${o===s.org?' selected':''}>${e(o)}</option>`).join('')}</select></label><button type="submit" class="btn primary">查询</button>${c.act('重置','training-reset')}${options.serverSearch?c.act('清空检索','social-list-reset'):''} ${section==='courses'?`<div class="tw-filter-extra"><span>课程标记：</span><label><input type="checkbox" name="package"${s.package?' checked':''}> 培训包</label><label><input type="checkbox" name="oneSkill"${s.oneSkill?' checked':''}> 一人一技</label></div>`:''}</form>`;
 const categories=tabs(section),tabbar=categories.length?`<nav class="tw-tabs" aria-label="${labels[section]}分类">${categories.map(([v,l])=>`<button type="button" data-action="training-tab" data-id="${v}" aria-pressed="${s.tab===v}" class="${s.tab===v?'active':''}">${l}</button>`).join('')}</nav>`:'';
 let list='';
 if(section==='trainers'||section==='records'){
  const headers=section==='trainers'?['教师','所属学院或单位','专业方向','资格状态','操作']:['培训日期','项目 / 课程','教师','学时','课程人次','归属收入','来源','操作'];
  list=`<div class="tw-table-wrap"><table class="tw-table"><thead><tr>${headers.map(h=>`<th>${h}</th>`).join('')}</tr></thead><tbody>${filtered.map(r=>{const x=r.raw;const cells=section==='trainers'?[`<div class="tw-person">${cover(r,section,c)}<span><strong>${e(r.name)}</strong><small>${e(x.title||'')}</small></span></div>`,e(r.org),e((x.directions||[]).join('、')),badge(r,c),pick(r)+(x.can_view_detail?'':'<small>仅基础信息</small>')]:[e(x.event_date),`<strong>${e(r.name)}</strong><small>${e(r.subtitle)}</small>`,e(c.teacherName(x.teacher_id)),e(text(x.hours)),e(text(x.participants)),e(text(x.income))+'元',e(x.source==='Excel导入'?'表格导入':x.source),pick(r,'查看')];return `<tr class="${r.id===s.selected?'selected':''}">${cells.map((v,i)=>`<td data-label="${headers[i]}">${v}</td>`).join('')}</tr>`}).join('')}</tbody></table></div>`;
 }else list=`<div class="tw-list tw-${section}">${filtered.map(r=>{const d=r.raw.data||{};return `<article class="tw-item${r.id===s.selected?' selected':''}">${cover(r,section,c)}<div class="tw-item-copy"><h3>${c.act(r.name,'training-pick',r.id,'text')}</h3>${meta('org',r.org,c)}${section==='courses'?meta('file',r.subtitle,c):section==='projects'?meta('clock',r.date,c):section==='bases'?meta('map',d.location,c)+meta('clock','认定日期：'+text(d.established_on),c):`<p class="tw-meta">${e(levels[d.level]||'级别待确认')} · ${e(d.confirmed_on||'日期待补充')}</p><p class="tw-description">${e(d.recognition||'认定依据待补充')}</p>`}<div class="tw-item-actions">${badge(r,c)}${pick(r,section==='courses'?'查看课程':'查看详情')}${section==='courses'?c.act('查看资源','social-course-resources',r.id,''):''}</div></div></article>`}).join('')}</div>`;
 if(!filtered.length)list=`<div class="tw-empty">${c.icon(section==='trainers'?'users':'file')}<h3>${s.q?'没有找到匹配的记录':rows.length?'没有符合条件的记录':'暂无'+labels[section].replace('管理','')+'记录'}</h3><p>${rows.length?'调整筛选条件后再试':'新增或审核通过后，资料将显示在这里。'}</p>${s.q?c.act('查看全部','social-list-reset'):rows.length?c.act('清除筛选','training-reset'):''}</div>`;
 const total=options.total??w.pagination?.total??w.total??rows.length;
 const footer=options.pager||((s.q||s.tab||s.org)?'':options.socialPager)||`<div class="tw-list-footer"><span>${s.q||s.tab||s.org?'筛选结果 '+filtered.length+' 条 · ':''}共 ${total} 条${total>rows.length?' · 筛选仅作用于当前页':''}</span>${options.socialPager||''}</div>`;
 return `<section class="training-workspace tw-section-${section}"><div class="tw-heading"><div><h1>${labels[section]}</h1><p>${descriptions[section]}</p></div><div class="tw-heading-actions">${options.actions||''}</div></div>${options.before||''}<div class="tw-layout"><div class="tw-main">${filter}${tabbar}${section==='records'?`<p class="tw-data-summary">本页 ${rows.length} 条记录 · ${rows.reduce((n,r)=>n+Number(r.raw.hours||0),0)} 学时 · ${rows.reduce((n,r)=>n+Number(r.raw.participants||0),0)} 课程人次</p>`:''}${list}${footer}${options.after||''}</div>${preview(selected,section,c)}</div></section>`;
}
