import test from 'node:test';
import assert from 'node:assert/strict';
import {ledgerPage,homeIndicators,ledgerAction,minePage,mineReminders,resourceStatsPage,resetLedgerView} from '../../frontend/social-ledgers.js';
import {historyDateSummary} from '../../frontend/history-projects.js';
const esc=v=>String(v??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
function context(answers,role='school'){
 const requests=[];
 return {requests,esc,ts:v=>v||'—',icon:()=>'',act:(l,a,id='')=>`<button data-action="${a}" data-id="${esc(id)}">${esc(l)}</button>`,link:(l,a,id='')=>`<a data-action="${a}" data-id="${esc(id)}">${esc(l)}</a>`,
  table:(h,rows,empty='')=>rows.length?`<table>${rows.map(r=>`<tr>${r.map(x=>`<td>${x}</td>`).join('')}</tr>`).join('')}</table>`:`<p>${esc(empty)}</p>`,
  note:(t,warn)=>t?`<p class="note${warn?' warn':''}">${esc(t)}</p>`:'',field:(n,l)=>`<label>${esc(l)}<input id="f-${n}"></label>`,pageHead:(t,a='')=>`<header>${esc(t)}${a}</header>`,
  number:(v,d=0)=>Number(v||0).toFixed(d),modal(){},closeModal(){},render:async()=>{},toast(){},me:{role:{kind:role}},can:()=>true,pageAllowed:p=>p!=='qualifications'||role!=='dept',
  api:async path=>{requests.push(path);for(const [k,v] of Object.entries(answers))if(path.startsWith(k))return v;throw Error('unexpected '+path)}};
}
const overview={year:2026,scope:'全校',note:'推荐口径待学校确认',participants:{claimed:'4320',final:'2508',reported:3,colleges:12,pending_rows:4,pending_ledgers:2,mine:null},can_review:true,points:null,achievements:{total:3,levels:{national:0,province:1,school:2}},dual:{total:7,levels:{'初级':2,'中级':3,'高级':1,'未分级':1}}};

test('台账显示同源历史日期预填和项目详情入口，不改报送量与核定状态',async()=>{
 resetLedgerView(true);
 const history={date_prefill:{kind:'source',start_date:'2025-09-02',end_date:'2025-09-11',text:'服务证明所载期间',evidence:'合成服务证明第2页'},confirmed_start:null,confirmed_end:null};
 const detail={id:'prefill-ledger',version:2,org_name:'合成学院',can_review:false,can_draft:false,versions:[],note:'原值保留',
  totals:{claimed_total:'0',recommended_total:'0',final_total:'0',pending_rows:1},reported_quantities:[{unit:'人次',value:'0'}],
  data:{year:2025,version_no:1,template_label:'合成原表',file:{name:'原件.xlsx'},summary:{serious:0},rows:[{row_no:4,name:'合成历史项目',claimed:'0',people:'0',hours:'8',recommended:'0',approved:null,issues:[],history}]}};
 const c=context({'/social/ledgers/prefill-ledger':detail});c.filter={year:'2025',source:'school',ledger_id:'prefill-ledger'};
 try{
  const html=await ledgerPage(c);
  assert.ok(html.includes(historyDateSummary(c,history)));assert.match(html,/查看历史项目资料与依据/);
  assert.match(html,/history_ledger=prefill-ledger&amp;history_row=4/);
  assert.match(html,/历史预填 · 待学校复核/);assert.match(html,/待学校核定/);
  assert.doesNotMatch(html,/学校已核定|已结项|已认定积分/);
  detail.totals.pending_rows=0;
  const quantityApproved=await ledgerPage(c);
  assert.match(quantityApproved,/报送量已核定 · 历史预填日期仍待学校复核/);
  assert.doesNotMatch(quantityApproved,/学校已核定 · 全部项目行已核定/);
 }finally{resetLedgerView(true)}
});

test('原表报送量按单位展示，驾驶舱台账链接可按年度和编号打开及返回',async()=>{
 const totals={claimed_total:'11410',recommended_total:'999',final_total:'999',pending_rows:1};
 const quantities=[{unit:'人次',value:'8902'},{unit:'人天',value:'2508'},{unit:'原表折算量',value:null}];
 const item={id:'linked-ledger',org_name:'合成学院',can_review:false,can_draft:false,version:1,versions:[],totals,reported_quantities:quantities,
  data:{year:2025,version_no:1,template_label:'合成台账',file:{name:'原件.xlsx'},summary:{serious:0},rows:[]}};
 const c=context({'/social/ledgers/linked-ledger':item,'/social/ledgers?year=':{items:[item],missing:[],can_submit:false,can_review:false,note:'',reported_quantities:quantities}});
 await ledgerAction('tz-year','2025',c);
 let html=await ledgerPage(c);
 assert.match(html,/原表报送 · 人次/);assert.match(html,/8,902/);assert.match(html,/2,508/);assert.match(html,/未提供.*原表折算量/);
 assert.doesNotMatch(html,/11,410|学院填报人次|系统建议核减/);
 assert.ok(c.requests.at(-1).endsWith('&source=school'));
 c.filter={year:'2025',ledger_id:'linked-ledger'};
 html=await ledgerPage(c);
 assert.match(html,/当前查看台账/);assert.match(html,/合成学院 · 2025 年/);
 assert.match(html,/原表报送 · 人天/);assert.doesNotMatch(html,/11,410/);
 const navigations=[];c.nav=async(page,filter)=>{navigations.push({page,filter});c.filter=filter};
 await ledgerAction('tz-back','',c);
 assert.deepEqual(navigations,[{page:'ledgers',filter:{year:'2025',source:'school'}}]);
 html=await ledgerPage(c);assert.doesNotMatch(html,/当前查看台账/);assert.equal(c.requests.at(-1),'/social/ledgers?year=2025&source=school');
 await ledgerAction('tz-back','',context({}));
});

test('2508人天台账保留原报送量与逐行公式，试算及人工核对不冒充人次',async()=>{
 const rows=[160,384,1160,96,448,240,20].map((value,i)=>({row_no:4+i,name:'合成人天项目'+(i+1),claimed:String(value),claimed_raw:value+'人天',people:value,hours:'8',recommended:String(value),approved:null,mode:'人天式',basis:'人天式：人数×课时÷8',issues:[]}));
 const detail={id:'days-ledger',version:1,org_name:'软件学院',can_review:true,can_draft:false,versions:[],note:'推荐值待学校确认',reported_quantities:[{unit:'人天',value:'2508'}],
  totals:{claimed_total:'2508',recommended_total:'2508',final_total:'2508',pending_rows:7},school_figure:{value:'2508',diff:'100',reason:'逐行核对依据'},
  data:{year:2026,version_no:1,template_label:'2026版（模块式／人天式）',file:{name:'合成原件.xls'},summary:{serious:0},rows}};
 const c=context({'/social/ledgers/days-ledger':detail});
 await ledgerAction('tz-detail','days-ledger',c);
 try{
  let html=await ledgerPage(c);
  assert.match(html,/原表报送 · 人天/);assert.match(html,/2,508<small>人天/);
  assert.match(html,/推荐试算量/);assert.match(html,/当前核对量/);assert.match(html,/学校人工核对数/);
  assert.match(html,/不作为原表人次统计/);assert.match(html,/不计算跨单位差额/);assert.match(html,/人数×课时÷8/);
  assert.doesNotMatch(html,/2,508<small>人次|2,508 人次|认可的人次|学校人工核定人次|相差 100/);
  detail.reported_quantities=[{unit:'原表折算量',value:'2508'}];html=await ledgerPage(c);
  assert.match(html,/推荐试算量/);assert.match(html,/原表报送 · 原表折算量/);
  detail.reported_quantities=[{unit:'人次',value:'2508'}];html=await ledgerPage(c);
  assert.match(html,/按推荐口径/);assert.match(html,/学校人工核定人次/);assert.match(html,/2,508<small>人次/);assert.match(html,/相差 100/);
 }finally{await ledgerAction('tz-back','',c)}
});

test('学校来源默认最新原表年度，其他来源单列且切换刷新保留范围',async()=>{
 resetLedgerView(true);
 const periods=[{year:2025,label:'2025年全年'},{year:2026,label:'2026年1—8月'}];
 const c=context({});c.filter={};
 c.api=async path=>{c.requests.push(path);const q=new URLSearchParams(path.split('?')[1]),source=q.get('source');return {year:Number(q.get('year')||2026),source,source_periods:periods,source_catalog_available:true,source_note:source==='school'?'学校原表同源':'其他资料和测试数据单列',items:[],missing:[],reported_quantities:[],can_submit:false,can_review:false,note:''}};
 let html=await ledgerPage(c);
 assert.equal(c.requests.at(-1),'/social/ledgers?source=school');
 assert.match(html,/2026年1—8月各学院台账/);assert.match(html,/学校原始台账/);assert.match(html,/其他台账（含测试）/);
 assert.match(html,/href="#ledgers\?year=2026&amp;source=other"/);assert.match(html,/href="#cockpit\?report_year=2026"/);
 c.filter={year:"2025",source:"school"};assert.match(await ledgerPage(c),/href="#cockpit\?report_year=2025"/);
 c.filter={year:'2027',source:'other'};html=await ledgerPage(c);
 assert.equal(c.requests.at(-1),'/social/ledgers?year=2027&source=other');
 assert.match(html,/href="#ledgers\?year=2026&amp;source=school"/);
 const navigations=[];c.nav=async(page,filter)=>{navigations.push({page,filter});c.filter=filter};
 await ledgerAction('tz-year','2026',c);assert.deepEqual(navigations.at(-1),{page:'ledgers',filter:{year:'2026',source:'other'}});
 await ledgerAction('tz-detail','other-ledger',c);assert.equal(navigations.at(-1).filter.source,'other');
 await ledgerAction('tz-back','',c);assert.deepEqual(navigations.at(-1).filter,{year:'2026',source:'other'});
 c.filter={source:'invalid',year:'2027'};await ledgerPage(c);assert.equal(c.requests.at(-1),'/social/ledgers?source=school');
 resetLedgerView(true);
});

test('多单位列表总卡不显示人次与人天相加的试算和当前混合数',async()=>{
 resetLedgerView(true);
 const items=[['合成人次学院','人次','120'],['合成人天学院','人天','20']].map(([org_name,unit,value],i)=>({id:'mixed-'+i,org_name,reported_quantities:[{unit,value}],data:{version_no:1,template_label:'2026版',summary:{serious:0}},totals:{claimed_total:value,recommended_total:value,final_total:value,pending_rows:1,state:'待核定'}}));
 const c=context({'/social/ledgers':{year:2026,items,missing:[],reported_quantities:[{unit:'人次',value:'120'},{unit:'人天',value:'20'}],can_submit:false,can_review:false,note:''}});
 const html=await ledgerPage(c),cards=html.match(/<section class="summary-row ledger-stats mt16">[\s\S]*?<\/section>/)[0];
 assert.match(cards,/按行查看/);assert.match(cards,/分单位核对/);assert.match(cards,/人次、人天及折算量不合并/);
 assert.doesNotMatch(cards,/>140</);assert.match(html,/120 人次/);assert.match(html,/20 人天/);
 resetLedgerView(true);
});

test('学院与学校台账详情在折叠说明外始终显示学院年度版本和核定进度',async()=>{
 for(const role of ['college','school']){
  const totals={claimed_total:'2',recommended_total:'2',final_total:'2',pending_rows:1};
  const detail={id:'context-ledger',version:3,org_name:'合成<学院>',can_review:false,can_draft:false,note:'',versions:[],totals,data:{year:2026,version_no:2,template_label:'2026版',file:{name:'合成.xlsx'},summary:{serious:0},rows:[]}};
  const c=context({'/social/ledgers/context-ledger':detail},role);c.pageHead=(description,actions)=>`<header><h1>学院台账与口径检查</h1><details><summary>页面说明</summary>${esc(description)}</details>${actions}</header>`;
  await ledgerAction('tz-detail','context-ledger',c);
  try{
   let html=(await ledgerPage(c)).replace(/<details\b[\s\S]*?<\/details>/g,'');
   assert.match(html,/当前查看台账<\/span><strong>合成&lt;学院&gt; · 2026 年 · 第 2 版/);assert.match(html,/待学校核定 · 1 行未核定，当前汇总含推荐值/);assert.doesNotMatch(html,/学校已核定/);
   totals.pending_rows=0;html=(await ledgerPage(c)).replace(/<details\b[\s\S]*?<\/details>/g,'');
   assert.match(html,/学校已核定 · 全部项目行已核定/);assert.doesNotMatch(html,/待学校核定|合成<学院>/);
  }finally{await ledgerAction('tz-back','',c)}
 }
});

test('历次台账报送时间交给系统统一时间格式，不能截取原始协调时',async()=>{
 const totals={claimed_total:'30',recommended_total:'30',final_total:'30',pending_rows:0},stamp='2026-10-11T21:57:00';
 const d={id:'time-ledger',version:1,org_name:'合成学院',can_review:false,can_draft:false,note:'',versions:[{id:'old',version_no:1,created_at:stamp,totals},{id:'time-ledger',version_no:2,created_at:stamp,totals}],totals,data:{year:2026,version_no:2,template_label:'合成台账',file:{name:'合成.xlsx'},summary:{serious:0},rows:[]}};
 const c=context({'/social/ledgers/time-ledger':d}),seen=[];c.ts=v=>{seen.push(v);return '2026/10/12 05:57:00'};
 await ledgerAction('tz-detail','time-ledger',c);
 try{const html=await ledgerPage(c);assert.deepEqual(seen,[stamp,stamp]);assert.match(html,/2026\/10\/12 05:57:00/);assert.doesNotMatch(html,/2026-10-11 21:57/)}finally{await ledgerAction('tz-back','',c)}
});
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
test('首页指标：人次用核定后口径，双师型一格内分初中高级，且转义业务文字',async()=>{
 const html=await homeIndicators(context({'/social/overview':{...overview,scope:'<全校>'}}),{income:'12345.6'},'<button class="kpi">人均学分</button>','<a>更多统计</a>');
 assert.equal((html.match(/class="kpi"/g)||[]).length,5);assert.match(html,/人均学分<\/button><\/div>/);assert.match(html,/<a>更多统计<\/a>/);
 assert.match(html,/培训人次/);assert.match(html,/2,508<small>/);assert.match(html,/2 个学院的 2026 年台账待核定/);assert.match(html,/3\/12 个学院已报/);
 assert.match(html,/12345.60/);assert.match(html,/初级 2 · 中级 3 · 高级 1 · 未分级 1/);assert.match(html,/另有 1 人未写级别/);
 assert.match(html,/3\/12 个学院已报台账/);assert.match(html,/国家级 0 · 省级 1 · 校级 2/);
 assert.match(html,/&lt;全校&gt;/);assert.doesNotMatch(html,/<全校>/);
});
test('教师首页显示我的培训人次，读取失败不冒充 0',async()=>{
 const html=await homeIndicators(context({'/social/overview':{...overview,scope:'本人',participants:{...overview.participants,mine:{value:'432',projects:2}},dual:{total:1,levels:{'初级':0,'中级':1,'高级':0,'未分级':0},mine:'中级'},points:{year:'12.5',five_years:'80',five_year_target:'340',title_points:'0.13'},can_review:false}},'teacher'),{income:0});
 assert.match(html,/我的培训人次/);assert.match(html,/432<small>/);assert.match(html,/2 个项目/);assert.match(html,/中级/);assert.match(html,/我的社会培训积分/);assert.match(html,/近五年累计 80 分（目标 340 分）/);assert.doesNotMatch(html,/待核定/);
 const failed=await homeIndicators({...context({}),api:async()=>{throw Error('网络断开')}},{});
 assert.match(failed,/读取失败：网络断开/);assert.doesNotMatch(failed,/class="kpi"/);
});
test('台账页列出各学院填报、推荐、核定后与未报学院，切换年度重新读取',async()=>{
 const item={id:'r1',org_name:'软件<学院>',reported_quantities:[{unit:'人次',value:'200'}],data:{version_no:2,template_label:'2026 版',summary:{serious:1}},totals:{claimed_total:'200',recommended_total:'150',final_total:'150',state:'待核定',pending_rows:3}};
 const c=context({'/social/ledgers':{items:[item],missing:[{org_id:'c2',org_name:'商学院'}],can_submit:true,can_review:true,note:'说明'}});
 const html=await ledgerPage(c);
 assert.match(html,/软件&lt;学院&gt;/);assert.match(html,/第 2 版/);assert.match(html,/1 行严重/);assert.match(html,/还没报送：商学院/);assert.match(html,/去核定/);assert.match(html,/200 人次/);assert.doesNotMatch(html,/−50/);
 assert.match(html,/data-action="tz-upload"/);assert.match(html,/data-action="tz-detail" data-id="r1"/);
 await ledgerAction('tz-year','2025',c);await ledgerPage(c);
 assert.equal(c.requests.at(-1),'/social/ledgers?year=2025&source=school');
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
test('个人培训按统一待办计数，保留本人项目、当前审批节点和原表人次，资质回到原页面查看',async()=>{
 const mine={year:2026,name:'任欣',org_name:'素质教育学院',note:'只显示本人',reminders:[{level:'warn',text:'“公益课”已结项，请在 2026-09-23 前申报积分',action:'social-claim-new',id:''}],
  projects:[{id:'p1',code:'TZ2026-c1-004',name:'公益<课>',cohort:'第1期',state:'CLOSED',state_label:'已结项',start_date:'2026-03-14',end_date:'2026-03-14',roles:['项目负责人','主讲（1 次）'],claim:null,deadline:{date:'2026-09-23',days_left:3,estimated:true}}],
  claims:[{id:'k1',project:'公益<课>',state:'SUBMITTED',state_label:'待院长初审',total:'1.56',blockers:1,steps:[{label:'本人填报',done:true},{label:'院长初审',current:true},{label:'继教复审'}]}],
  allocations:[{year:2026,org_name:'素质教育学院',row_no:4,name:'公益课',value:'40',original_value:'40',project_approved:'0',approved_value:null,reviewed:false,project_code:'TZ2026-c1-004'}],
  qualifications:[{id:'q1',category:'双师型教师（中级）',name:'双师型',state:'APPROVED',expires:'2026-11-01',days_left:24}],courses:{courses:1,videos:12,minutes:'95.5',resources:1},achievements:[{name:'满意度成果',level:'school',auto:true}]};
 const c=context({'/social/mine':mine,'/todos?':{total:2,attention_counts:{handle:2,waiting:3}}},'teacher');
 c.me={role:{kind:'teacher'},user:{staff_no:'T1'}};
 const html=await minePage(c,{income:0});
 assert.match(html,/素质教育学院/);assert.match(html,/待我处理 <span class="workbench-count">2/);assert.match(html,/3 项等待核对或学校确认/);assert.match(html,/data-action="social-claim-new"/);
 assert.match(html,/公益&lt;课&gt;/);assert.doesNotMatch(html,/公益<课>/);assert.match(html,/预计截止 2026-09-23（待学校确认）/);assert.doesNotMatch(html,/已过申报期限/);
 assert.match(html,/<td>院长初审<\/td>/);assert.match(html,/1 项待确认/);assert.doesNotMatch(html,/mine-steps|home-indicators|24 天后到期|我的培训人次/);
 assert.match(html,/第 4 行 · 项目 TZ2026-c1-004/);assert.match(html,/项目核定人次 0/);assert.match(html,/待个人核定/);assert.match(html,/满意度自动生成/);assert.match(html,/教师资质管理 · 1 项/);assert.ok(c.requests.includes('/todos?attention=handle&page=1&size=1'));
 const api=c.api;c.api=p=>p.startsWith('/todos?')?Promise.reject(Error('待办断网')):api(p);const unknown=await minePage(c);assert.match(unknown,/workbench-count">—/);assert.match(unknown,/待办暂未读取成功/);assert.doesNotMatch(unknown,/待我处理 <span class="workbench-count">0/);
 const failed=await minePage({...context({}),api:async()=>{throw Error('断网')}},{});assert.match(failed,/个人数据看板读取失败：断网/);
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


test('教研室平均积分说明年度与分母，零分保留，缺数据不冒充零',async()=>{
 const c=context({'/social/departments':{year:2026,note:'全体在岗教师计入人数；折算办法待学校确认。',items:[
  {name:'本室<合成>',college:'合成学院',teachers:4,with_points:0,total:'0',average:'0',rank:1},
  {name:'待计算',college:'合成学院',teachers:2,with_points:0,total:null,average:null},
  {name:'空教研室',college:'合成学院',teachers:0,with_points:0,total:'0',average:null}
 ]}},'dept');
 const original=c.table;c.table=(headers,...args)=>'<thead>'+headers.join('|')+'</thead>'+original(headers,...args);
 await ledgerAction('tz-year','2026',c);
 const html=await ledgerPage(c);
 assert.equal(c.requests.at(-1),'/social/departments?year=2026');
 assert.match(html,/2026 年教研室平均积分/);assert.match(html,/在岗人数（分母）/);assert.match(html,/没有积分的教师也计入分母/);
 assert.match(html,/其中 0 人有已归档积分/);assert.match(html,/本室&lt;合成&gt;[\s\S]*?<td>0<\/td><td><strong>0<\/strong>/);
 assert.match(html,/暂无已归档数据/);assert.match(html,/暂未计算/);assert.match(html,/没有在岗老师，暂不计算/);
 assert.match(html,/未归档申报不计入/);assert.match(html,/<details class="detail-fold mt16"><summary>统计口径与考核说明/);
 assert.doesNotMatch(html,/data-action="tz-upload"|data-action="tz-review-save"|data-action="tz-tab"/);
});

test('教研室切换到旧台账入口也只读取本室平均积分，不读取学院原件',async()=>{
 const c=context({'/social/departments':{year:2026,note:'',items:[]}},'dept');
 await ledgerAction('tz-detail','private-college-ledger',c);
 await ledgerAction('tz-tab','targets',c);
 const html=await ledgerPage(c);
 assert.deepEqual(c.requests,['/social/departments?year=2026']);
 assert.match(html,/当前年度没有可查看的教研室/);
 assert.doesNotMatch(html,/tz-detail|attachment-download|tz-upload|核定人次/);
 await ledgerAction('tz-back','',c);await ledgerAction('tz-tab','ledgers',c);
});

test('教研室资源统计只有查看入口，并受课程页面权限限制',async()=>{
 const answer={'/social/resource-stats':{note:'登记视频总分钟',items:[{org_name:'软件<教研室>',courses:2,resources:3,videos:1,minutes:'0'}]}};
 const c=context(answer,'dept');const original=c.table;c.table=(headers,...args)=>'<thead>'+headers.join('|')+'</thead>'+original(headers,...args);
 let html=await resourceStatsPage(c);
 assert.match(html,/查看课程资源/);assert.match(html,/data-action="nav" data-id="courses"/);
 assert.match(html,/仅供查阅/);assert.match(html,/教研室\|课程\|资源/);assert.match(html,/软件&lt;教研室&gt;/);assert.match(html,/<strong>0<\/strong>/);
 assert.doesNotMatch(html,/去登记课程资源|data-action="social-resource-new"/);
 c.pageAllowed=()=>false;html=await resourceStatsPage(c);assert.doesNotMatch(html,/data-action="nav"/);
 c.pageAllowed=()=>true;c.can=()=>false;html=await resourceStatsPage(c);assert.doesNotMatch(html,/data-action="nav"/);
 const school=await resourceStatsPage(context(answer));assert.match(school,/去登记课程资源/);assert.match(school,/各学院课程资源/);
});


test('空学院台账显示尚未报送，不把零汇总说成全部核定',async()=>{
 const c=context({'/social/ledgers':{items:[],missing:[{org_name:'测试学院一'}],can_submit:true,can_review:false,note:''}},'college');
 await ledgerAction('tz-tab','ledgers',c);const html=await ledgerPage(c);
 assert.match(html,/本院本年度尚未报送统计表/);assert.match(html,/当前汇总人次/);assert.match(html,/尚未报送，暂无核定结果/);
 assert.doesNotMatch(html,/全部核定|<label>核定人次<\/label>/);assert.match(html,/data-action="tz-upload"/);
 c.can=()=>false;
 const readonly=await ledgerPage({...c,api:async()=>({items:[],missing:[],can_submit:false,can_review:false,note:''})});
 assert.doesNotMatch(readonly,/data-action="tz-upload"|应报学院都已报送/);
});

test('学院台账原填人数和人次保留数字零，详情折叠报送资料并保留返回及原件权限',async()=>{
 const totals={claimed_total:'0',recommended_total:'0',final_total:'0',pending_rows:2};
 const detail={id:'zero-ledger',version:2,org_name:'测试学院一',can_review:false,can_draft:false,note:'推荐值不是正式认定结果',submitted_by_name:'合成人员',versions:[{id:'zero-ledger'}],totals,data:{year:2026,version_no:1,template_label:'2026版',file:{id:'file1',name:'合成<统计表>.xlsx'},summary:{serious:0},rows:[
  {row_no:4,name:'原文零',claimed_raw:0,claimed:999,people_raw:0,people:999,hours:0,recommended:'0',issues:[]},
  {row_no:5,name:'回落零',claimed_raw:'',claimed:0,people_raw:'',people:0,hours:0,recommended:'0',issues:[]}
 ]}};
 const c=context({'/social/ledgers/zero-ledger':detail},'college');await ledgerAction('tz-detail','zero-ledger',c);
 try{
  let html=await ledgerPage(c);
  assert.equal((html.match(/<strong>0<\/strong><div class="cell-sub">0 人 · 0 课时<\/div>/g)||[]).length,2);
  assert.match(html,/<details class="detail-fold"><summary>报送资料与版本说明/);assert.match(html,/合成&lt;统计表&gt;.xlsx/);
  assert.match(html,/返回本院台账/);assert.match(html,/attachment-download/);assert.doesNotMatch(html,/ledger-approved|保存核定/);
  c.can=()=>false;html=await ledgerPage(c);assert.doesNotMatch(html,/attachment-download/);
 }finally{await ledgerAction('tz-back','',c)}
});

test('年度速算使用接口独立的待补成果数量，明确零值不显示待补提示',async()=>{
 for(const role of ['college','school'])for(const pending of [1,0]){
  const row={org_id:'college1',org_name:'合成学院',targets:{},actual:{income:'0',participants:'0',priority:null},achievements:{national:0,province:0,school:1},achievements_pending:pending,estimate:{results:'2',cost:'10',total:null,grade:null,missing:['目标待下达'],metrics:[]}};
  const c=context({'/social/targets':{year:2026,can_edit:false,note:'',items:[row]}},role);await ledgerAction('tz-tab','targets',c);
  try{const html=await ledgerPage(c);assert.equal(html.includes('另有 1 项待确认认定年度'),pending===1);assert.match(html,/国家 0 · 省 0 · 校 1/)}finally{await ledgerAction('tz-tab','ledgers',c)}
 }
});

test('学院年度目标把含推荐值的人次标为当前汇总，并说明核定口径',async()=>{
 const c=context({'/social/targets':{year:2026,can_edit:false,note:'推荐口径',items:[{org_id:'college1',org_name:'测试学院一',targets:{},actual:{income:'0',participants:'3',priority:null},achievements:{national:0,province:0,school:0},estimate:{results:'0',cost:'10',total:null,grade:null,missing:['目标待下达'],metrics:[]}}]}},'college');
 await ledgerAction('tz-tab','targets',c);
 try{const html=await ledgerPage(c);assert.match(html,/<small>当前汇总人次<\/small><strong>3<\/strong>/);assert.match(html,/未核定行暂用推荐值/);assert.doesNotMatch(html,/<small>核定培训人次<\/small>|ledger-target"|tz-targets-save/)}finally{await ledgerAction('tz-tab','ledgers',c)}
});

function uploadContext(){
 const elements={
  'f-ledger_file':{files:[],events:{},addEventListener(name,fn){this.events[name]=fn}},
  'ledger-submit-btn':{disabled:true},'ledger-preview-result':{innerHTML:''},
  'ledger-submit-form':{values:{org_id:'college1',year:'2026',reason:'合成学院报送复验'}}
 };
 const requests=[],c=context({},'college');
 const preview={summary:{rows:1,claimed_total:'3',recommended_total:'3',serious:0},meta:{college:'测试学院一',year:2026},template_label:'2026版',suggested_org_id:'college1',colleges:[{id:'college1',name:'测试学院一'}],notes:[],note:'仅供核对',rows:[]};
 let respond=async path=>path.endsWith('/preview')?preview:{id:'new-ledger',data:{year:2026}};
 c.api=async(path,options)=>{requests.push({path,options});return respond(path,options)};
 const previousDocument=globalThis.document,previousFormData=globalThis.FormData;
 globalThis.document={getElementById:id=>elements[id]||null};
 globalThis.FormData=class {constructor(form){this.values=new Map(Object.entries(form?.values||{}))}set(key,value){this.values.set(key,value)}get(key){return this.values.get(key)}[Symbol.iterator](){return this.values[Symbol.iterator]()}};
 return {c,elements,requests,preview,setResponse:fn=>{respond=fn},restore:()=>{globalThis.document=previousDocument;globalThis.FormData=previousFormData}};
}

test('更换统计表及失败重检使旧预览失效，不能误报送上一份文件',async()=>{
 const t=uploadContext();
 try{
  await ledgerAction('tz-upload','',t.c);const input=t.elements['f-ledger_file'],button=t.elements['ledger-submit-btn'];
  input.files=[{name:'统计表A.xlsx'}];await ledgerAction('tz-preview','',t.c);assert.equal(button.disabled,false);
  input.files=[{name:'统计表B.xlsx'}];input.events.change();assert.equal(button.disabled,true);assert.match(t.elements['ledger-preview-result'].innerHTML,/文件已更换/);
  await assert.rejects(ledgerAction('tz-submit','',t.c),/请先检查/);
  t.setResponse(async()=>{throw Error('新文件损坏')});await assert.rejects(ledgerAction('tz-preview','',t.c),/新文件损坏/);
  assert.equal(button.disabled,true);await assert.rejects(ledgerAction('tz-submit','',t.c),/请先检查/);
  assert.equal(t.requests.filter(r=>r.path==='/social/ledgers').length,0);
 }finally{t.restore()}
});

test('迟到的检查结果不会覆盖新文件，确认只报送当前已检查文件',async()=>{
 const t=uploadContext();
 try{
  await ledgerAction('tz-upload','',t.c);const input=t.elements['f-ledger_file'],button=t.elements['ledger-submit-btn'];let finishOld;
  t.setResponse(()=>new Promise(resolve=>{finishOld=resolve}));input.files=[{name:'旧文件.xlsx'}];const oldRequest=ledgerAction('tz-preview','',t.c);
  const current={name:'当前文件.xlsx'};input.files=[current];input.events.change();t.setResponse(async path=>path.endsWith('/preview')?t.preview:{id:'new-ledger',data:{year:2026}});
  await ledgerAction('tz-preview','',t.c);finishOld(t.preview);await oldRequest;
  assert.equal(button.disabled,false);assert.match(t.elements['ledger-preview-result'].innerHTML,/当前文件.xlsx/);assert.doesNotMatch(t.elements['ledger-preview-result'].innerHTML,/旧文件.xlsx/);
  await ledgerAction('tz-submit','',t.c);const sent=t.requests.find(r=>r.path==='/social/ledgers');assert.equal(sent.options.body.get('file'),current);assert.equal(sent.options.body.get('org_id'),'college1');
  await ledgerAction('tz-back','',t.c);
 }finally{t.restore()}
});


test('确认报送再次核对所选文件，未触发更换事件也不能沿用旧预览',async()=>{
 const t=uploadContext();
 try{
  await ledgerAction('tz-upload','',t.c);const input=t.elements['f-ledger_file'];
  input.files=[{name:'已检查.xlsx'}];await ledgerAction('tz-preview','',t.c);
  input.files=[{name:'未检查.xlsx'}];await assert.rejects(ledgerAction('tz-submit','',t.c),/统计表已更换，请重新检查/);
  assert.equal(t.elements['ledger-submit-btn'].disabled,true);assert.equal(t.requests.filter(r=>r.path==='/social/ledgers').length,0);
 }finally{t.restore()}
});


test('台账人员和项目关联表单返回时先关闭表单，再读取原台账详情，不提交变更',async()=>{
 const detail={id:'return-ledger',version:2,org_name:'测试学院一',can_review:false,can_draft:true,note:'',versions:[{id:'return-ledger'}],totals:{claimed_total:'0',recommended_total:'0',final_total:'0',pending_rows:1},data:{year:2026,version_no:1,template_label:'2026版',file:{name:'合成.xlsx'},summary:{serious:0},rows:[{row_no:4,name:'待确认合成项目',claimed:'0',people:'0',hours:0,recommended:'0',issues:[],allocations:[{name:'合成教师'}]}]}};
 const previousDocument=globalThis.document;globalThis.document={querySelectorAll:()=>[]};
 const c=context({'/social/ledgers/return-ledger':detail},'college');let options,html;const order=[];
 c.formModal=(title,body,save,config)=>{options=config};c.closeModal=()=>order.push('close');c.render=async()=>{order.push('render');html=await ledgerPage(c)};
 try{
  for(const [action,code] of [['tz-bind-owner','return-ledger|4'],['tz-bind-person','return-ledger|4|0'],['tz-bind-project','return-ledger|4']]){
   await ledgerAction(action,code,c);order.length=0;const before=c.requests.length;
   await options.returnTo();
   assert.deepEqual(order,['close','render']);assert.deepEqual(c.requests.slice(before),['/social/ledgers/return-ledger']);
   assert.match(html,/待确认合成项目/);assert.match(html,/返回本院台账/);assert.equal(options.returnLabel,'返回学院台账');
  }
 }finally{await ledgerAction('tz-back','',{...c,render:async()=>{}});globalThis.document=previousDocument}
});


test('年度切换经过通用导航重置后仍恢复原业务标签',async()=>{
 const {resetLedgerView}=await import('../../frontend/social-ledgers.js');
 const {navigationHash,restoreNavigation}=await import('../../frontend/scope.js');
 for(const ledger_tab of ['targets','depts']){
  const c={filter:{},render:async()=>{},nav:async(page,filter)=>{resetLedgerView(true);c.filter=restoreNavigation(navigationHash(page,filter),{ledgers:'台账'}).filter}};
  await ledgerAction('tz-tab',ledger_tab,c);
  await ledgerAction('tz-year','2025',c);
  assert.equal(c.filter.ledger_tab,ledger_tab);assert.equal(c.filter.year,'2025');
 }
 resetLedgerView(true);
});


test('浏览器返回无标签地址时恢复台账列表，不沿用年度目标标签',async()=>{
 resetLedgerView(true);
 const c=context({'/social/targets':{year:2025,items:[],can_edit:false,note:''},'/social/ledgers?':{year:2026,items:[],source:'school',missing:[],source_periods:[]}});
 c.filter={year:'2025',ledger_tab:'targets'};await ledgerPage(c);
 c.filter={source:'school'};await ledgerPage(c);
 assert.equal(c.requests.at(-1),'/social/ledgers?source=school');
 resetLedgerView(true);
});

test('问题行筛选写入地址并在刷新后恢复，不能沿用上一个详情的筛选',async()=>{
 resetLedgerView(true);
 const detail={id:'refresh-ledger',version:1,org_name:'合成学院',can_review:false,can_draft:false,versions:[],note:'',totals:{pending_rows:2},data:{year:2025,version_no:1,file:{name:'原件.xlsx'},summary:{serious:0},rows:[{row_no:4,name:'正常合成项目',issues:[]},{row_no:5,name:'待核合成项目',issues:[{level:'注意',text:'材料待补'}]}]}};
 const c=context({'/social/ledgers/refresh-ledger':detail});c.filter={year:'2025',ledger_id:'refresh-ledger'};let synced=false;c.syncLocation=()=>{synced=true};
 globalThis.document={querySelectorAll:()=>[]};
 await ledgerPage(c);await ledgerAction('tz-filter','issues',c);delete globalThis.document;assert.ok(synced);assert.equal(c.filter.ledger_filter,'issues');
 resetLedgerView(true);const html=await ledgerPage(c);assert.match(html,/待核合成项目/);assert.doesNotMatch(html,/正常合成项目/);
 delete c.filter.ledger_filter;assert.match(await ledgerPage(c),/正常合成项目/);resetLedgerView(true);
});
