import test from 'node:test';
import assert from 'node:assert/strict';
import {ledgerPage,homeIndicators,ledgerAction,minePage,mineReminders} from '../../frontend/social-ledgers.js';
const esc=v=>String(v??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
function context(answers,role='school'){
 const requests=[];
 return {requests,esc,icon:()=>'',act:(l,a,id='')=>`<button data-action="${a}" data-id="${esc(id)}">${esc(l)}</button>`,link:(l,a,id='')=>`<a data-action="${a}" data-id="${esc(id)}">${esc(l)}</a>`,
  table:(h,rows,empty='')=>rows.length?`<table>${rows.map(r=>`<tr>${r.map(x=>`<td>${x}</td>`).join('')}</tr>`).join('')}</table>`:`<p>${esc(empty)}</p>`,
  note:(t,warn)=>t?`<p class="note${warn?' warn':''}">${esc(t)}</p>`:'',field:(n,l)=>`<label>${esc(l)}<input id="f-${n}"></label>`,pageHead:(t,a='')=>`<header>${esc(t)}${a}</header>`,
  number:(v,d=0)=>Number(v||0).toFixed(d),modal(){},closeModal(){},render:async()=>{},toast(){},me:{role:{kind:role}},can:()=>true,pageAllowed:p=>p!=='qualifications'||role!=='dept',
  api:async path=>{requests.push(path);for(const [k,v] of Object.entries(answers))if(path.startsWith(k))return v;throw Error('unexpected '+path)}};
}
const overview={year:2026,scope:'全校',note:'推荐口径待学校确认',participants:{claimed:'4320',final:'2508',reported:3,colleges:12,pending_rows:4,pending_ledgers:2,mine:null},can_review:true,points:null,achievements:{total:3,levels:{national:0,province:1,school:2}},dual:{total:7,levels:{'初级':2,'中级':3,'高级':1,'未分级':1}}};
test('个人提醒默认显示短状态，完整原因可展开，原办理目标不变',()=>{
 const c=context({}),m={projects:[{id:'p1',name:'项目<一>',deadline:{estimated:true,days_left:-5}}],reminders:[{action:'social-detail',id:'social_project|p1',action_label:'查看项目',text:'学校校历尚未确认 <保留原文>',level:'warn'},{action:'social-claim-new',id:'',text:'缺少条件'}],claim_ready:{reason:'口径待配置'}};
 const html=mineReminders(c,m),visible=html.replace(/<details\b[\s\S]*?<\/details>/g,'');
 assert.match(visible,/项目&lt;一&gt; · 申报日期待学校确认/);assert.doesNotMatch(visible,/已过申报期限|保留原文/);
 assert.match(html,/<details class="inline-note"><summary>查看说明<\/summary>/);assert.match(html,/学校校历尚未确认 &lt;保留原文&gt;/);
 assert.match(html,/data-action="social-detail" data-id="social_project\|p1"/);assert.doesNotMatch(html,/data-action="social-claim-new"/);
});
test('学院和学校都标明待核定人次，查看进度与核定入口按权限区分',async()=>{
 for(const role of ['college','school']){
  const html=await homeIndicators(context({'/social/overview':{...overview,can_review:role==='school'}},role),{});
  assert.match(html,/培训人次（待核定）/);assert.match(html,/待核定（含推荐值）/);
  assert.match(html,role==='school'?/去核定/:/查看核定进度/);
 }
 const cleared={...overview,participants:{...overview.participants,pending_rows:0,pending_ledgers:0}};
 const html=await homeIndicators(context({'/social/overview':cleared}),{});
 assert.doesNotMatch(html,/培训人次（待核定）|home-ledger-todo/);
});
test('缺少申报条件时说明原因并隐藏无效入口，估算期限不显示已过期',async()=>{
 const mine={name:'合成教师',org_name:'合成教研室',claim_ready:{reason:'学校还未登记口径'},reminders:[{text:'请核实期限',action:'social-claim-new',id:''}],
  projects:[{id:'p',name:'合成项目',roles:[],deadline:{date:'2026-09-23',days_left:-18,estimated:true}}],claims:[],allocations:[],qualifications:[],achievements:[]};
 const c=context({'/social/mine':mine,'/social/overview':{...overview,scope:'本人',can_review:false}},'teacher');
 c.me.user={staff_no:'T1'};
 const html=await minePage(c,{});
 assert.match(html,/积分申报暂未开放[\s\S]*学校还未登记口径/);assert.doesNotMatch(html,/查看积分申报条件|去申报/);
 assert.doesNotMatch(html,/data-action="social-claim-new"|已过申报期限/);
 assert.match(html,/预计截止 2026-09-23（待学校确认）/);
});
test('首页五项指标：人次用核定后口径，双师型分初中高级，且转义业务文字',async()=>{
 const html=await homeIndicators(context({'/social/overview':{...overview,scope:'<全校>'}}),{income:'12345.6'});
 assert.equal((html.match(/class="kpi"/g)||[]).length,5);
 assert.match(html,/培训人次/);assert.match(html,/2,508<small>/);assert.match(html,/2 个学院的 2026 年台账待核定/);assert.match(html,/3\/12 个学院已报/);
 assert.match(html,/12345.60/);assert.match(html,/2\/3\/1/);assert.match(html,/另有 1 人未写级别/);
 assert.match(html,/&lt;全校&gt;/);assert.doesNotMatch(html,/<全校>/);
});
test('教师首页显示我的培训人次，读取失败不冒充 0',async()=>{
 const html=await homeIndicators(context({'/social/overview':{...overview,scope:'本人',participants:{...overview.participants,mine:{value:'432',projects:2}},dual:{total:1,levels:{'初级':0,'中级':1,'高级':0,'未分级':0},mine:'中级'},points:{year:'12.5',five_years:'80',five_year_target:'340',title_points:'0.13'},can_review:false}},'teacher'),{income:0});
 assert.match(html,/我的培训人次/);assert.match(html,/432<small>/);assert.match(html,/2 个项目/);assert.match(html,/中级/);assert.match(html,/我的社会培训积分/);assert.match(html,/近五年累计 80 分（目标 340 分）/);assert.doesNotMatch(html,/待核定/);
 const failed=await homeIndicators({...context({}),api:async()=>{throw Error('网络断开')}},{});
 assert.match(failed,/读取失败：网络断开/);assert.doesNotMatch(failed,/class="kpi"/);
});
test('台账页列出各学院填报、推荐、核定后与未报学院，切换年度重新读取',async()=>{
 const item={id:'r1',org_name:'软件<学院>',data:{version_no:2,template_label:'2026 版',summary:{serious:1}},totals:{claimed_total:'200',recommended_total:'150',final_total:'150',state:'待核定',pending_rows:3}};
 const c=context({'/social/ledgers':{items:[item],missing:[{org_id:'c2',org_name:'商学院'}],can_submit:true,can_review:true,note:'说明'}});
 const html=await ledgerPage(c);
 assert.match(html,/软件&lt;学院&gt;/);assert.match(html,/第 2 版/);assert.match(html,/1 行严重/);assert.match(html,/还没报送：商学院/);assert.match(html,/去核定/);assert.match(html,/−50/);
 assert.match(html,/data-action="tz-upload"/);assert.match(html,/data-action="tz-detail" data-id="r1"/);
 await ledgerAction('tz-year','2025',c);await ledgerPage(c);
 assert.equal(c.requests.at(-1),'/social/ledgers?year=2025');
});
test('核定页整页显示、可筛选问题行，筛选时保留已填的核定值',async()=>{
 const rows=[{row_no:4,name:'公益课',recommended:'100',claimed:'200',issues:[{level:'严重',text:'浏览量当人数'}]},{row_no:5,name:'脱产班',recommended:'32',claimed:'32',issues:[]}];
 const detail={id:'r1',version:3,org_name:'软件学院',can_review:true,note:'',submitted_by_name:'甲',versions:[{id:'r1'}],totals:{claimed_total:'232',recommended_total:'132',final_total:'132',pending_rows:2},data:{year:2026,version_no:1,template_label:'2026 版',file:{name:'a.xls'},summary:{serious:1},rows}};
 const c=context({'/social/ledgers/r1':detail});
 await ledgerAction('tz-detail','r1',c);let html=await ledgerPage(c);
 assert.match(html,/软件学院 · 2026 年 · 第 1 版/);assert.match(html,/有问题的行（1）/);assert.match(html,/保存核定/);assert.match(html,/空着的行填入推荐值/);assert.equal((html.match(/class="ledger-approved"/g)||[]).length,2);
 const inputs=[{dataset:{row:'4',recommended:'100'},value:'90'},{dataset:{row:'5',recommended:'32'},value:''}],reasons=[{dataset:{row:'4'},value:'到场 90 人'},{dataset:{row:'5'},value:''}];
 globalThis.document={querySelectorAll:sel=>sel==='.ledger-approved'?inputs:sel==='.ledger-reason'?reasons:[]};
 await ledgerAction('tz-filter','serious',c);html=await ledgerPage(c);
 assert.equal((html.match(/class="ledger-approved"/g)||[]).length,1);assert.match(html,/value="90"/);assert.match(html,/value="到场 90 人"/);
 await ledgerAction('tz-back','',c);delete globalThis.document;
});
test('年度目标与考核速算：学校可编辑目标，缺数据时说明还缺什么，有总分时显示等级',async()=>{
 const items=[{org_id:'c1',org_name:'软件学院',targets:{income:'100',participants:'72'},actual:{income:'100',participants:'72',priority:null},achievements:{national:0,province:1,school:0},estimate:{results:'5',cost:'10',total:null,grade:null,missing:['重点群体目标','重点群体实际数'],metrics:[]}},
  {org_id:'c2',org_name:'商学院',targets:{income:'100',participants:'50',priority:'10',priority_actual:'10'},actual:{income:'120',participants:'60',priority:'10'},achievements:{national:0,province:0,school:0},estimate:{results:'0',cost:'10',bonus:'4',total:'94',grade:'优秀',missing:[],metrics:[{label:'收入',score:'40'},{label:'培训人次',score:'20'},{label:'重点群体',score:'10'}]}},
  {org_id:'c3',org_name:'艺术学院',targets:{students:'1000'},suggest:{participants:'2000',priority:'500'},actual:{income:'0',participants:null,priority:null},achievements:{national:0,province:0,school:0},estimate:{results:'0',cost:'0',cost_details:['公益课：结项六个月内未完成结算，扣 5 分'],veto:'纪检处分 1 号',grade:'不合格（一票否决）',total:null,missing:['收入目标'],metrics:[]}}];
 const c=context({'/social/targets':{year:2026,items,can_edit:true,note:'速算说明'}});
 await ledgerAction('tz-tab','targets',c);const html=await ledgerPage(c);
 assert.match(html,/年度目标与考核速算/);assert.match(html,/还缺：重点群体目标、重点群体实际数/);assert.match(html,/>94</);assert.match(html,/优秀/);
 assert.equal((html.match(/class="ledger-target"/g)||[]).length,21);assert.match(html,/data-action="tz-targets-save"/);assert.match(html,/data-action="tz-suggest"/);
 assert.equal((html.match(/<details class="target-college"[^>]*>/g)||[]).length,3);
 assert.match(html,/aria-label="软件学院 · 收入目标（元）"/);assert.doesNotMatch(html,/aria-label="income"/);
 for(const org of ['c1','c2','c3'])for(const key of ['students','income','participants','priority','priority_actual','compliance_failures','veto_reason'])assert.equal((html.match(new RegExp(`data-org="${org}" data-key="${key}"`,'g'))||[]).length,1);
 const view=context({'/social/targets':{year:2026,items,can_edit:false,note:''}});const read=await ledgerPage(view);
 assert.doesNotMatch(read,/ledger-target"/);assert.match(read,/完成 120%/);assert.match(read,/建议：人次 2,000 · 重点群体 500/);assert.match(read,/一票否决：纪检处分 1 号/);assert.match(read,/结项六个月内未完成结算/);assert.match(read,/red-b">不合格（一票否决）/);
 await ledgerAction('tz-tab','ledgers',c);
});
test('折叠学院表单保留零值和空值，建议值不覆盖已有目标，统一保存全部学院',async()=>{
 const inputs=[{dataset:{org:'c1',key:'students'},value:'100'},{dataset:{org:'c1',key:'participants'},value:'0'},{dataset:{org:'c1',key:'priority'},value:''},{dataset:{org:'c2',key:'income'},value:''},{dataset:{org:'c2',key:'compliance_failures'},value:'0'},{dataset:{org:'c2',key:'veto_reason'},value:' 文件号 1 '}];
 const c=context({});let saved;
 c.api=async(path,opts)=>{assert.equal(path,'/social/targets');saved=opts.body;return {}};
 globalThis.document={querySelectorAll:sel=>sel==='.ledger-target'?inputs:sel==='.ledger-target[data-key="students"]'?inputs.filter(x=>x.dataset.key==='students'):[]};
 try{
  await ledgerAction('tz-suggest','',c);assert.equal(inputs[1].value,'0');assert.equal(inputs[2].value,'50');
  await ledgerAction('tz-targets-save','',c);
  assert.deepEqual(saved.items,[{org_id:'c1',students:'100',participants:'0',priority:'50',compliance_scope:'other_only'},{org_id:'c2',income:null,compliance_failures:0,veto_reason:'文件号 1',compliance_scope:'other_only'}]);
 }finally{delete globalThis.document}
});

test('未核验的逾期结算显示待财务核验，不能把空资金分显示成零或满分',async()=>{
 const items=[{org_id:'c1',org_name:'学院一',targets:{},actual:{income:'100',participants:'30',priority:'30'},achievements:{national:0,province:0,school:0},estimate:{results:'0',cost:null,total:null,grade:null,missing:['项目逾期结算待财务核验'],cost_details:['须确认不合规或正式例外'],metrics:[]}}];
 const c=context({'/social/targets':{year:2026,items,can_edit:false,note:''}});
 await ledgerAction('tz-tab','targets',c);const html=await ledgerPage(c);
 assert.match(html,/<small>资金管理<\/small><strong>待财务核验<\/strong>/);
 assert.doesNotMatch(html,/<small>资金管理<\/small><strong>(?:0|10) 分<\/strong>/);
 assert.match(html,/须确认不合规或正式例外/);
 await ledgerAction('tz-tab','ledgers',c);
});
test('核定页可生成项目草稿、登记学校人工核定数，已生成的行标出项目编号',async()=>{
 const rows=[{row_no:4,name:'公益课',recommended:'100',claimed:'100',issues:[],project_id:'p1',project_code:'TZ2026-c1-004'},{row_no:5,name:'脱产班',recommended:'32',claimed:'32',issues:[]}];
 const detail={id:'r9',version:2,org_name:'软件学院',can_review:true,can_draft:true,drafts:1,note:'',submitted_by_name:'甲',versions:[{id:'r9'}],school_figure:{value:'120',diff:'12',reason:'文件夹核定数'},totals:{claimed_total:'132',recommended_total:'132',final_total:'132',pending_rows:2},data:{year:2026,version_no:1,template_label:'2026 版',file:{name:'a.xls'},summary:{serious:0},rows}};
 const c=context({'/social/ledgers/r9':detail});
 await ledgerAction('tz-detail','r9',c);const html=await ledgerPage(c);
 assert.match(html,/已关联 TZ2026-c1-004/);assert.match(html,/data-action="social-detail" data-id="social_project\|p1"/);assert.match(html,/生成项目草稿（1 行）/);assert.match(html,/data-action="tz-drafts" data-id="r9\|2"/);
 assert.match(html,/相差 12/);assert.match(html,/data-action="tz-figure"/);
 await ledgerAction('tz-back','',c);
});
test('个人培训页：先列要我处理的事，再列本人项目、积分审批进度、台账人次和资质',async()=>{
 const mine={year:2026,name:'样例教师甲',org_name:'素质教育学院',note:'只显示本人',reminders:[{level:'warn',text:'“公益课”已结项，请在 2026-09-23 前申报积分',action:'social-claim-new',id:''}],
  projects:[{id:'p1',code:'TZ2026-c1-004',name:'公益<课>',cohort:'第1期',state:'CLOSED',state_label:'已结项',start_date:'2026-03-14',end_date:'2026-03-14',roles:['项目负责人','主讲（1 次）'],claim:null,deadline:{date:'2026-09-23',days_left:3,estimated:true}}],
  claims:[{id:'k1',project:'公益<课>',state:'SUBMITTED',state_label:'待院长初审',total:'1.56',blockers:1,steps:[{label:'本人填报',done:true},{label:'院长初审',current:true},{label:'继教复审'}]}],
  allocations:[{year:2026,org_name:'素质教育学院',row_no:4,name:'公益课',value:'40',reviewed:false,project_code:'TZ2026-c1-004'}],
  qualifications:[{id:'q1',category:'双师型教师（中级）',name:'双师型',state:'APPROVED',expires:'2026-11-01',days_left:24}],courses:{courses:1,videos:12,minutes:'95.5',resources:1},achievements:[{name:'满意度成果',level:'school',auto:true}]};
 const c=context({'/social/mine':mine,'/social/overview':{...overview,scope:'本人',participants:{...overview.participants,mine:{value:'40',projects:1}},dual:{...overview.dual,mine:'中级'},points:{year:'0',five_years:'0',five_year_target:'340',title_points:'0'}}},'teacher');
 c.me={role:{kind:'teacher'},user:{staff_no:'T1'}};
 const html=await minePage(c,{income:0});
 assert.match(html,/素质教育学院/);assert.match(html,/需要我处理 <span class="workbench-count">1/);assert.match(html,/data-action="social-claim-new"/);
 assert.match(html,/公益&lt;课&gt;/);assert.doesNotMatch(html,/公益<课>/);assert.match(html,/预计截止 2026-09-23（待学校确认）/);assert.doesNotMatch(html,/已过申报期限/);
 assert.match(html,/<span class="done">本人填报<\/span><span class="current">院长初审<\/span>/);assert.match(html,/1 项待确认/);
 assert.match(html,/第 4 行 · 项目 TZ2026-c1-004/);assert.match(html,/24 天后到期/);assert.match(html,/满意度自动生成/);assert.match(html,/我的培训人次/);
 const failed=await minePage({...context({}),api:async()=>{throw Error('断网')}},{});assert.match(failed,/个人培训读取失败：断网/);
});
test('教研室平均积分按名次列出；利益冲突弹窗可申报、只能撤回本人的',async()=>{
 const c=context({'/social/departments':{year:2026,note:'说明',items:[{org_id:'d1',name:'软件<教研室>',college:'软件学院',teachers:4,with_points:2,total:'30',average:'7.5',rank:1},{org_id:'d2',name:'空教研室',college:'软件学院',teachers:0,with_points:0,total:'0',average:null}]},
  '/social/conflicts':{items:[{id:'x1',user_id:'u1',user_name:'甲',target_name:'商学院',reason:'配偶任教',declared_on:'2026-10-08',active:true},{id:'x2',user_id:'u2',user_name:'乙',target_name:'丙',reason:'亲属',declared_on:'2026-10-01',active:true}],can_declare:true,all:true,teachers:[{id:'t1',name:'丙'}],orgs:[{id:'c2',name:'商学院'}],note:'须回避'}});
 c.me={role:{kind:'school'},user:{id:'u1'}};
 await ledgerAction('tz-tab','depts',c);const html=await ledgerPage(c);
 assert.match(html,/教研室平均积分/);assert.match(html,/软件&lt;教研室&gt;/);assert.match(html,/<strong>7.5<\/strong>/);assert.match(html,/没有在岗老师/);
 let shown='';c.modal=(t,b,f)=>{shown=t+b+f};await ledgerAction('tz-conflicts','',c);
 assert.match(shown,/全校申报记录/);assert.match(shown,/data-action="tz-conflict-withdraw" data-id="x1"/);assert.doesNotMatch(shown,/data-id="x2"/);assert.match(shown,/回避中/);assert.match(shown,/data-action="tz-conflict-save"/);
 await ledgerAction('tz-tab','ledgers',c);
});
