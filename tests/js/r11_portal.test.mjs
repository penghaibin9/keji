// Real renderer/control tests with explicit synthetic API fixtures, not browser E2E.

test('brand reflects configured identity without applying another school emblem',()=>{
 const e=engine(),brand=vm.runInContext('schoolBrand',e.ctx);
 e.t.setUser({school_name:'湖南科技职业学院'});assert.match(brand(),/school-brand-image/);
 e.t.setUser({school_name:'测试<学校>'});assert.match(brand(),/测试&lt;学校&gt;/);assert.doesNotMatch(brand(),/school-brand-image|湖南科技职业学院/);
});
test('public header uses the official school mark, live identity and the original action hooks',()=>{
 const e=engine(),head=vm.runInContext('headerBrand',e.ctx),shell=vm.runInContext('shell',e.ctx);
 e.t.setUser({school_name:'湖南科技职业学院',environment:'production',user:{name:'<张>老师'},role:{name:'学院<负责人>'}});
 assert.match(head(),/school-brand-header\.png/);shell();const html=e.node('#app').innerHTML;
 assert.match(html,/class="nd-header"/);assert.doesNotMatch(html,/school-masthead|class="topbar"/);
 assert.match(html,/&lt;张&gt;老师/);assert.match(html,/学院&lt;负责人&gt;/);assert.match(html,/nd-header__avatar" aria-hidden="true">&lt;/);assert.match(html,/学校本地部署/);
 for(const hook of ['id="breadcrumb"','current-identity','data-action="search"','data-action="nav" data-id="todos"','data-action="profile"','data-action="logout"','mobile-nav" data-action="toggle-menu"','aria-controls="sidebar"','id="sidebar"','class="main-shell"'])assert.ok(html.includes(hook),hook);
 assert.ok(html.indexOf('nd-header')>html.indexOf('class="main-shell"'),'header stays inside .main-shell so the mobile menu can make it inert');
 e.t.setUser({school_name:'测试<学校>',environment:'test',user:{name:'甲'},role:{name:'乙'}});
 assert.match(head(),/测试&lt;学校&gt;/);assert.doesNotMatch(head(),/school-brand-header|湖南科技职业学院/);shell();assert.match(e.node('#app').innerHTML,/隔离合成数据/);
});
test('changed calculation evidence is escaped and explains the blocked next step',()=>{
 const e=engine(),notice=vm.runInContext('sourceChangesNotice',e.ctx);
 assert.equal(notice({source_changes:{changed:false,items:[]}}),'');
 const html=notice({source_changes:{changed:true,items:[{label:'学时',before:'10',after:'2',details:[{name:'<课程>',before:'10',after:'2'}],detail_count:1}]}});
 assert.match(html,/暂不能向前确认或归档/);assert.match(html,/&lt;课程&gt;/);assert.doesNotMatch(html,/<课程>/);
});
test('manual form cannot offer protected import or interface origins',async()=>{
 const e=engine();e.t.captureForm();vm.runInContext("businessConfig.record_sources=['学校登记','Excel导入','学校数据中台']",e.ctx);
 await e.t.handlers['record-form']('');
 const body=e.t.getForm().body;assert.match(body,/<option value="学校登记"/);assert.doesNotMatch(body,/<option value="学校数据中台"|<option value="Excel导入"/);assert.match(body,/本入口按人工录入留痕/);
});
test('changing a project immediately clears previous names and dependent course and class',()=>{
 const e=engine();
 for(const key of ['project_code','course_code','class_code']){const input=e.node('#f-'+key);input.value='old';input.addEventListener=(type,handler)=>{input[type]=handler};}
 for(const key of ['project','course','class_name']){e.node('#f-'+key).value='旧名称';e.node('#f-'+key).readOnly=true;}
 vm.runInContext('bindRecordReferences()',e.ctx);
 const project=e.node('#f-project_code');project.value='new';project.input();
 assert.equal(e.node('#f-project').value,'');assert.equal(e.node('#f-project').readOnly,false);
 for(const key of ['course_code','class_code','course','class_name'])assert.equal(e.node('#f-'+key).value,'');
});
test('rule type disables unrelated fields and prevents a circular points input',()=>{
 const e=engine(),form=e.node('#edit-form');form.dataset={};
 const controls=['factor','weight','target','cap'].map(r=>({dataset:{r}})),headers=Array.from({length:6},()=>({})),circular={disabled:false},select={value:'points',querySelector:()=>circular};
 form.querySelectorAll=s=>s.includes('[data-r]')?controls:s.includes('rule-labels')?headers:s.includes('select')?[select]:[];
 const sync=vm.runInContext('syncRuleType',e.ctx);
 e.node('#f-kind').value='points';sync();assert.deepEqual(controls.map(x=>x.disabled),[false,true,true,false]);assert.equal(select.value,'hours');assert.equal(circular.disabled,true);
 e.node('#f-kind').value='assessment';sync();assert.deepEqual(controls.map(x=>x.disabled),[true,false,false,true]);assert.equal(circular.disabled,false);
});

import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';
import {connectorInfo,connectorCards,connectorStatus,incomeChart,guideCards,scopedDateFilters,incomeParticipantsChart,barChart,syncStatusChart,rankRows,percentChange,RANK_METRICS} from '../../frontend/portal-ui.js';
import * as scope from '../../frontend/scope.js';
import {icons} from '../../frontend/icons.js';
import * as workspace from '../../frontend/integration-workspace.js';
import * as drafts from '../../frontend/integration-drafts.js';
import {renderBusinessHistory} from '../../frontend/business-history.js';import * as ledgers from '../../frontend/social-ledgers.js';import * as schoolData from '../../frontend/school-data.js';import * as approvalFlow from '../../frontend/approval-flow.js';
const source=fs.readFileSync(new URL('../../frontend/app.js',import.meta.url),'utf8');
const customerVisible=html=>String(html??'').replace(/<details\b[\s\S]*?<\/details>/g,'');
const implementationDetailTags=html=>[...String(html??'').matchAll(/<details\b[^>]*class="[^"]*implementation-details[^"]*"[^>]*>/g)].map(x=>x[0]);
function engine(responder=async()=>({items:[],total:0,page:1,size:20}), role='school'){
 const requests=[], nodes=new Map();
 function node(id){if(!nodes.has(id)){const classes=new Set(),attrs=new Map();nodes.set(id,{innerHTML:'',textContent:'',value:'',classList:{add(v){classes.add(v)},remove(v){classes.delete(v)},contains(v){return classes.has(v)},toggle(v,force){const on=force??!classes.has(v);if(on)classes.add(v);else classes.delete(v);return on}},setAttribute(k,v){attrs.set(k,v)},getAttribute(k){return attrs.get(k)??null},removeAttribute(k){attrs.delete(k)},focus(){},addEventListener(){},append(){},querySelector(){return node(id+'-child')},querySelectorAll(){return []}})}return nodes.get(id)}
 const ctx=vm.createContext({console,URLSearchParams,URL,Blob,FormData,Number,String,Object,Array,Date,Math,Set,Map,JSON,RegExp,Error,Promise,crypto:globalThis.crypto,setTimeout:()=>0,clearTimeout(){},
  ...scope,...workspace,...drafts,...ledgers,...schoolData,...approvalFlow,renderBusinessHistory,connectorInfo,connectorCards,connectorStatus,incomeChart,guideCards,scopedDateFilters,incomeParticipantsChart,barChart,syncStatusChart,rankRows,percentChange,RANK_METRICS,icons,
  document:{querySelector:node,querySelectorAll:()=>[],addEventListener(){},createElement:()=>node('created'),body:node('body')},window:{addEventListener(){}},location:{hash:'',pathname:'/',search:''},history:{replaceState(){}},
  fetch:async(url,options)=>{requests.push({url,options});let answer=await responder(url,options);if(url.endsWith('/draft')&&options.method==='GET'&&!answer.connection){const cat=await responder('/api/connections/catalog',options),ident=url.split('/').at(-2),entry=cat.items.find(x=>x.connection.id===ident);answer={connection:entry.connection,draft_version:0,active_version:entry.connection.version||1}}if(url.endsWith('/implementation')&&!answer.statuses){const cat=await responder('/api/connections/catalog',options),ident=url.split('/').at(-2),entry=cat.items.find(x=>x.connection.id===ident);answer={connection_id:ident,code:entry.connection.code,name:entry.connection.name,statuses:{materials:'资料待登记',configuration:'配置待完善',tests:'待真实测试',published:'未发布或授权失效',health:'未检查',acceptance:'待学校签认'}}}return {ok:true,status:200,json:async()=>answer}},
 });
 let program=source.replace(/^import .*?;\r?\n/gm,'').replace(/\(async\(\)=>\{try\{await boot\(\)\}[\s\S]*$/,'');
 program+=`\nglobalThis.T={pages,handlers,api,nav,render,pageAllowed,sidebarNavigation,syncMenuAccessibility,connectionOverview,integrationPage,sourceAvailability,bindPortalControls,pager,query,connectionForm,mappingEditor,showInbound,ts,evidenceHtml,pointLabel,calculationSummary,
 setUser(user){me=user;csrf=user.csrf||'test-csrf'},setState(p,f={},n=1,pa=1,per=''){page=p;filter=f;tablePage=n;participationPage=pa;periodId=per},setData(p,t=[],o=[]){periods=p;teachers=t;orgs=o},getState(){return {page,filter,tablePage,participationPage,periodId}},getView(){return view},captureForm(){formModal=(title,body,callback,options)=>{globalThis.F={title,body,callback,options}}},getForm(){return globalThis.F}};`;
 vm.runInContext(program,ctx);
 ctx.T.setUser({user:{id:'u',name:'合成用户',is_admin:role==='school'},role:{kind:role,name:role},permissions:['portal.read','records.read','qualification.read','points.read','assessment.read','sync.manage','organization.read','notice.read','import','export','settings.manage','users.manage','audit.read','operations.read','rules.manage','dispute.write'],csrf:'test-csrf'});
 return {t:ctx.T,ctx,requests,node};
}
const types=[{data_type:'teacher_hr',name:'教师人事信息',local_status:'AVAILABLE',mapping_count:0},{data_type:'training_income',name:'培训收入',local_status:'AVAILABLE',mapping_count:0}];
test('页面和辅助说明按需展开，阻断提醒始终直接显示且转义内容',()=>{
 const e=engine();e.t.setState('records');
 const header=vm.runInContext('pageHead',e.ctx)('业务<说明>','<button>新增</button>');
 assert.match(header,/<h1>培训数据<\/h1>/);assert.match(header,/<details class="page-help"><summary>页面说明<\/summary>/);
 assert.match(header,/业务&lt;说明&gt;/);assert.doesNotMatch(header,/page-help" open/);assert.match(header,/<button>新增<\/button>/);
 const note=vm.runInContext('note',e.ctx);
 assert.match(note('统计依据',false,'统计说明'),/<details class="ui-note"><summary>统计说明<\/summary>/);
 const blocked=note('材料缺失，暂不能提交',true,'查看说明');
 assert.doesNotMatch(blocked,/<details/);assert.match(blocked,/info-banner warn/);assert.match(blocked,/暂不能提交/);
});
test('四类角色快捷入口按本级工作排序、去重并服从现有权限',()=>{
 const expected={teacher:['mine','qualifications','points','assessment'],dept:['qualifications','assessment','ledgers','organization'],college:['projects','courses','ledgers','assessment'],school:['ledgers','recognition','assessment','cockpit']};
 for(const [role,first] of Object.entries(expected)){
  const e=engine(undefined,role),html=vm.runInContext('homeQuickHTML()',e.ctx);
  const ids=[...html.matchAll(/class="workbench-quick" data-action="nav" data-id="([^"]+)"/g)].map(x=>x[1]);
  assert.deepEqual(ids.slice(0,4),first);assert.equal(new Set(ids).size,ids.length);
  if(role==='dept'){assert.match(html,/教研室平均积分/);assert.doesNotMatch(html,/学院台账报送|学校管理驾驶舱/);}
 }
 const e=engine();e.t.setUser({user:{id:'u'},role:{kind:'school'},permissions:['portal.read']});
 const html=vm.runInContext('homeQuickHTML()',e.ctx);
 assert.doesNotMatch(html,/data-id="ledgers"|data-id="permissions"|data-id="sync"|data-id="recognition"/);
});
test('permission sections translate levels without changing role or user contracts',async()=>{
 const e=engine(url=>url.startsWith('/api/users')?{items:[],total:0,page:1,size:20}:url==='/api/roles'?{items:[{id:'r',name:'学院角色',kind:'college',active:true,permissions:['records.read']}]}:{items:[{id:'s',name:'学校',kind:'school',active:true,code:'S'}]});e.t.setState('permissions');
 let html=await e.t.pages.permissions();assert.match(html,/账号管理/);assert.match(html,/仅本人业务/);assert.doesNotMatch(html,/角色与批量授权/);
 vm.runInContext("permissionsSection='roles'",e.ctx);html=await e.t.pages.permissions();assert.match(html,/二级学院/);assert.match(html,/所属学院及下属教研室/);assert.doesNotMatch(html,/>college</);assert.ok(e.requests.every(r=>r.options.method==='GET'));
});
test('人事调岗待确认优先于已启用状态展示',async()=>{
 const e=engine(url=>url.startsWith('/api/users')?{items:[{id:'u',username:'fixture',name:'合成教师',staff_no:'T1',active:true,authorization_pending:true,role_id:'r',org_id:'s'}],total:1,page:1,size:20}:url==='/api/roles'?{items:[{id:'r',name:'教师',kind:'teacher',active:true,permissions:['records.read']}]}:{items:[{id:'s',name:'学校',kind:'school',active:true,code:'S'}]});
 e.t.setState('permissions');const html=await e.t.pages.permissions();
 assert.match(html,/人事调岗 · 授权待确认/);assert.doesNotMatch(html,/>已启用</);
});
test('待确认账号编辑明确说明重新授权的影响',async()=>{
 const e=engine(()=>({items:[]}));e.t.captureForm();
 e.t.setUser({user:{id:'admin',is_admin:true},role:{kind:'school'},permissions:[]});
 vm.runInContext("view={items:[{id:'u',name:'合成教师',active:true,authorization_pending:true}]};bindAccountImpact=()=>{}",e.ctx);
 await e.t.handlers['user-form']('u');
 assert.equal(e.t.getForm().options.submit,'确认授权并保存');
 assert.match(e.t.getForm().options.hint,/保存将确认当前所选组织和角色/);
});
test('教师首页保留冻结折算精度，待核定不显示零，并按北京时间选择年份',async()=>{
 for(const score of ['1',null]){
  const e=engine(url=>url.startsWith('/api/social/overview')?{points:{year:'200',five_years:'200',five_year_target:'340',title_points:score}}:url.startsWith('/api/social/mine')?{reminders:[],claim_ready:{reason:'合成待配置'}}:{items:[]});
  e.t.setUser({user:{id:'teacher',name:'合成教师',staff_no:'T1'},role:{kind:'teacher'},permissions:['portal.read','points.read']});
  vm.runInContext("Date.now=()=>Date.parse('2026-12-31T16:05:00Z')",e.ctx);
  const html=await vm.runInContext('teacherHome()',e.ctx);
  assert.ok(e.requests.some(r=>r.url==='/api/social/overview?year=2027'));
  if(score===null){assert.match(html,/职称折算 待核定/);assert.doesNotMatch(html,/职称折算 0/);}
  else{assert.match(html,/职称折算 1 分（按归档口径试算）/);assert.doesNotMatch(html,/职称折算 1\.00/);}
 }
});
test('organization tree handles cycles and escapes business labels',()=>{
 const e=engine();const tree=vm.runInContext('organizationTree',e.ctx)([{id:'a',parent_id:'b',name:'<img>',kind:'college',code:'C',active:true},{id:'b',parent_id:'a',name:'教研室',kind:'dept',code:'D',active:true}]);assert.match(tree,/&lt;img&gt;/);assert.doesNotMatch(tree,/<img>/);assert.equal((tree.match(/class="org-tree-row"/g)||[]).length,2);
});
test('advanced filters keep applied conditions visible and preserve exact values',()=>{
 const e=engine();e.t.setState('records',{start:'2026-09-01',course_code:'A<&',teacher_id:'t'},1,1,'p');e.t.setData([{id:'p',name:'测试周期'}],[{id:'t',staff_no:'J01',name:'测试教师'}]);const html=vm.runInContext('filtersBar',e.ctx)({dates:true,project:true,teacher:true,period:true});assert.match(html,/advanced-filters" open/);assert.match(html,/课程编码：A&lt;&amp;/);assert.match(html,/教师：测试教师/);assert.equal((html.match(/id="filters"/g)||[]).length,1);assert.match(html,/value="2026-09-01"/);
});
test('inactive advanced filters default closed without discarding controls',()=>{
 const e=engine();e.t.setState('records');const html=vm.runInContext('filtersBar',e.ctx)({dates:true,project:true});assert.doesNotMatch(html,/advanced-filters" open/);assert.match(html,/name="start"/);assert.match(html,/name="course_code"/);
});
test('record tabs preserve both pagers and exactly one shared filter form',async()=>{
 const e=engine();e.t.setState('records');vm.runInContext("recordSection='participation'",e.ctx);const html=await e.t.pages.records();assert.match(html,/record-teaching" hidden/);assert.doesNotMatch(html,/record-participation mt20" hidden/);assert.equal((html.match(/id="filters"/g)||[]).length,1);assert.match(html,/participation-next/);assert.ok(e.requests.every(r=>!r.url.includes('tab=')));
});
test('mobile table labels are escaped and comparative tables stay tables',()=>{
 const e=engine();const render=vm.runInContext('table',e.ctx);assert.match(render(['日期','教师','项目','状态','操作'],[['1','2','3','4','5']]),/responsive-table/);assert.match(render(['资质','状态','有效期','操作'],[['证书','已通过','2026-12-31','查看']]),/responsive-table/);assert.doesNotMatch(render(['环节','教师数量'],[['教师确认','2']]),/responsive-table/);assert.match(render(['<name>'],[['ok']]),/data-label="&lt;name&gt;"/);
});
test('table empty states distinguish no records from no filtered results',()=>{
 const e=engine();e.t.setState('qualifications');assert.match(vm.runInContext('table([],[])',e.ctx),/暂无记录/);e.t.setState('qualifications',{q:'不存在'});assert.match(vm.runInContext('table([],[])',e.ctx),/没有符合条件的记录|未找到匹配记录/);
});

test('没有积分台账时只显示一次空状态，有待确认记录时保留确认按钮',async()=>{
 let balances=[];
 const e=engine(url=>url.startsWith('/api/point-balances')?{items:balances}:{items:[],sum:0,total:0,page:1,size:20},'teacher');e.t.setState('points');
 let html=await e.t.pages.points();assert.doesNotMatch(html,/<h2>教师积分确认<\/h2>/);
 balances=[{id:'b1',teacher_id:'u',period_id:'p1',confirmed:false}];
 html=await e.t.pages.points();assert.match(html,/<h2>教师积分确认<\/h2>/);assert.match(html,/data-action="balance-action" data-id="b1"/);
});

test('零份考核不展示空分档表，有考核时保留真实分值和分布',()=>{
 const e=engine(),render=vm.runInContext('scoreBandsHTML',e.ctx);
 const empty=render({assessment_score_summary:{count:0},assessment_score_bands:[{label:'90—100分',count:0}]});
 assert.match(empty,/暂无考核数据/);assert.doesNotMatch(empty,/90—100分|平均分/);
 const populated=render({assessment_score_summary:{count:2,average:85,minimum:80,maximum:90},assessment_score_bands:[{label:'80—90分',count:2}]});
 assert.match(populated,/85\.00/);assert.match(populated,/80—90分/);assert.match(populated,/分档说明/);
});
test('mobile configuration selector retains current selection and technical content closed',()=>{
 const e=engine();const html=vm.runInContext('settingWorkspace',e.ctx)({items:[{key:'branding',version:1,value:{school_name:'学校'}}]},{key:'branding',version:1,value:{school_name:'学校'}},{items:[]});assert.match(html,/id="settings-mobile-select"/);assert.match(html,/value="branding" selected/);assert.match(html,/实施人员使用：查看原始配置/);assert.doesNotMatch(html,/settings-raw" open/);
});
test('audit access detail does not label reads as business changes',()=>{
 const e=engine();vm.runInContext("view={items:[{id:'a',module:'access',action:'GET',actor_name:'合成账号',result:'SUCCESS',after:{http_status:200},request_id:'trace'}]}",e.ctx);e.t.handlers['audit-detail']('a');const html=e.node('#modal-root').innerHTML;assert.match(html,/业务访问概况/);assert.match(html,/没有修改业务数据/);assert.doesNotMatch(html,/<h3>变更前|<h3>调整前/);assert.match(html,/<details class="mt20"><summary>实施人员使用/);
});
test('audit changes still expose both before and after business evidence',()=>{
 const e=engine();vm.runInContext("view={items:[{id:'a',module:'settings',action:'PUT',actor_name:'合成账号',result:'SUCCESS',before:{name:'原名称'},after:{name:'新名称'}}]}",e.ctx);e.t.handlers['audit-detail']('a');const html=e.node('#modal-root').innerHTML;assert.match(html,/变更前/);assert.match(html,/原名称/);assert.match(html,/新名称/);
});
test('help role selection never grants the current user additional navigation',async()=>{
 const e=engine(undefined,'teacher');e.t.setUser({user:{id:'u'},role:{kind:'teacher'},permissions:['portal.read','records.read']});e.t.setState('help');vm.runInContext("helpAudience='school'",e.ctx);const html=await e.t.pages.help();assert.match(html,/维护组织、账号与角色/);assert.match(html,/当前账号没有此办理入口/);assert.doesNotMatch(html,/data-action="nav" data-id="permissions"/);
});
test('delivery checklist cannot manufacture acceptance from healthy process values',()=>{
 const e=engine();const html=vm.runInContext('deliveryReadiness()',e.ctx);assert.match(html,/待提供学校验收证据/);assert.match(html,/不从运行心跳推断验收通过/);assert.doesNotMatch(html,/green-b/);
});
test('calculation-only permission does not newly require rule management',async()=>{
 const e=engine();e.t.setUser({user:{id:'u'},role:{kind:'school'},permissions:['assessment.calculate']});e.t.captureForm();e.t.setData([{id:'p',name:'周期',state:'OPEN'}]);e.node('#calculation-impact').dataset={};e.node('#f-period_id').value='p';await e.t.handlers.calculate('assessment');assert.equal(e.node('#calculation-impact').dataset.ready,'true');assert.match(e.node('#calculation-impact').innerHTML,/没有规则维护权限/);assert.ok(!e.requests.some(r=>r.url==='/api/rules'));
});
test('no enabled rule blocks calculation before write and explains why',async()=>{
 const e=engine();e.t.captureForm();e.t.setData([{id:'p',name:'周期',state:'OPEN'}]);e.node('#calculation-impact').dataset={};e.node('#f-period_id').value='p';await e.t.handlers.calculate('assessment');assert.match(e.node('#calculation-impact').innerHTML,/尚无已启用规则/);const form={querySelectorAll:()=>[{value:'t'}]};await assert.rejects(e.t.getForm().callback({period_id:'p'},form),/核对生效规则/);assert.ok(e.requests.every(r=>r.options.method==='GET'));
});
const connection={id:'c-middle',code:'middle',name:'学校数据中台',state:'NOT_CONNECTED',version:1,config:{},mappings:[]};
const catalog={items:[{connection,data_types:types}]};
function responder(url){
 if(url.startsWith('/api/connections/catalog'))return catalog;
 if(url.startsWith('/api/connections/summary'))return {items:[{code:'middle',name:'中台',connection_state:'NOT_CONNECTED',latest_task:null}]};
 if(url.includes('/checks'))return {items:[{id:'proof',mode:'REAL',passed:false,reason_code:'ADAPTER_NOT_INSTALLED',receipt:{_connection_revision:8},created_at:'2026-09-19T10:00:00'}]};
 return {items:[],total:23,page:Number(new URL('http://fixture'+url).searchParams.get('page')||1),size:20};
}
const middleTypes=[
 {data_type:'teacher_hr',name:'教师人事信息',local_status:'AVAILABLE',mapping_count:0},
 {data_type:'training_income',name:'培训收入',local_status:'AVAILABLE',mapping_count:0},
 {data_type:'course_participants',name:'课程人次',local_status:'AVAILABLE',mapping_count:0},
 {data_type:'training_project',name:'培训项目基础信息',local_status:'AVAILABLE',mapping_count:0},
 {data_type:'course',name:'课程基础信息',local_status:'AVAILABLE',mapping_count:0},
];
const provinceTypes=[
 ['training_project','培训项目','AVAILABLE'],['course','课程','AVAILABLE'],['plan','培训计划','WAITING_SOURCE'],['class','班级','AVAILABLE'],
 ['teaching','教师授课','AVAILABLE'],['participants','人次','AVAILABLE'],['learning_process','学习过程','WAITING_SOURCE'],['training_record','培训记录','AVAILABLE'],
 ['assessment_result','考核结果','AVAILABLE'],['completion_result','结业结果','WAITING_SOURCE'],['certificate','证书信息','WAITING_SOURCE'],
].map(([data_type,name,local_status])=>({data_type,name,local_status,mapping_count:0}));
const integrationCatalog={items:[
 {connection:{id:'c-sso',code:'sso',name:'学校统一认证',state:'NOT_CONNECTED',version:1,config:{},mappings:[]},data_types:[{data_type:'identity',name:'统一认证身份字段与角色/组织映射',local_status:'WAITING_PROTOCOL',mapping_count:0}]},
 {connection:{id:'c-middle',code:'middle',name:'学校数据中台',state:'NOT_CONNECTED',version:1,config:{},mappings:[]},data_types:middleTypes},
 {connection:{id:'c-province',code:'province',name:'湘培直通车',state:'NOT_CONNECTED',version:1,config:{},mappings:[]},data_types:provinceTypes},
]};
function integrationResponder(url){
 if(url.startsWith('/api/connections/catalog'))return integrationCatalog;
 if(url.startsWith('/api/connections/summary'))return {items:integrationCatalog.items.map(({connection})=>({code:connection.code,name:connection.name,connection_state:connection.state,latest_task:null}))};
 if(url.includes('/checks'))return {items:[{id:'proof',mode:'REAL',passed:false,reason_code:'ADAPTER_NOT_INSTALLED',receipt:{_connection_revision:8},created_at:'2026-09-19T10:00:00'}]};
 return {items:[],total:0,page:1,size:20};
}

test('connector unknown is not falsely green or falsely confirmed disconnected',()=>{
 assert.equal(connectorStatus(undefined).text,'状态未获取');assert.equal(connectorStatus('CONNECTED').kind,'good');assert.equal(connectorStatus('NOT_CONNECTED').text,'待对接');
 assert.match(connectorCards([]),/状态未获取/);assert.doesNotMatch(connectorCards([]),/连接证明有效/);
});
test('teacher home connector descriptions do not reveal operational statuses or manager actions',()=>{
 const html=connectorCards([],{restricted:true,compact:true});assert.match(html,/学校统一管理/);assert.doesNotMatch(html,/data-action=|状态未获取|连接证明有效/);
});
test('connector labels and latest counts are escaped',()=>{
 const html=connectorCards([{code:'middle',latest_task:{success_count:'<img>',failed_count:0,pending_confirmation_count:0}}]);assert.match(html,/&lt;img&gt;/);assert.doesNotMatch(html,/<img>/);
});
test('income chart keeps negative corrections and exact values, no invented months',()=>{
 const html=incomeChart([{month:'2026-08',income:'100.25'},{month:'2026-09',income:'-80.50'}]);assert.match(html,/-80\.50/);assert.match(html,/100\.25/);assert.match(html,/zero-line/);assert.doesNotMatch(html,/2026-07/);
});
test('income chart handles empty, single and zero rows without NaN',()=>{
 assert.match(incomeChart([]),/暂无收入趋势/);for(const rows of [[{month:'2026-09',income:0}],[{month:'2026-09',income:10}]])assert.doesNotMatch(incomeChart(rows),/NaN|Infinity/);
});
for(const invalid of [null,undefined,'',true,'NaN','Infinity'])test(`invalid chart value ${String(invalid)} is an error, not zero`,()=>{assert.match(incomeChart([{month:'m',income:invalid}]),/数据格式异常/)});
test('chart escapes markup in returned month labels',()=>{assert.doesNotMatch(incomeChart([{month:'<script>x</script>',income:1}]),/<script>/)});
test('participation date range intersects selected period rather than broadening',()=>{
 assert.deepEqual(scopedDateFilters({start:'2026-05-01',end:'2027-02-01',q:'hello'},{start_date:'2026-01-01',end_date:'2026-12-31'}),{start:'2026-05-01',end:'2026-12-31',q:'hello'});
 assert.deepEqual(scopedDateFilters({q:'hello'},null),{q:'hello'});
});
test('organization assessment page two sends page/size',async()=>{
 const e=engine(responder);e.t.setState('assessment',{},2);vm.runInContext("assessmentTab='dept'",e.ctx);await e.t.pages.assessment();
 const url=e.requests.find(x=>x.url.startsWith('/api/organization-assessments')).url;assert.match(url,/page=2/);assert.match(url,/size=20/);
});
test('teaching one row and participation 21 rows have independent pagination',async()=>{
 const e=engine(url=>({items:[],page:url.includes('participations')?1:1,size:20,total:url.includes('participations')?21:1}));e.t.setState('records');e.t.setData([]);const html=await e.t.pages.records();
 assert.match(html,/data-action="participation-next" >下一页/);assert.match(html,/data-action="next" disabled/);
});
test('participation second page does not turn teaching page and carries selected period dates',async()=>{
 const e=engine(responder);e.t.setState('records',{},1,2,'period');e.t.setData([{id:'period',start_date:'2026-01-01',end_date:'2026-12-31'}]);await e.t.pages.records();
 assert.match(e.requests[0].url,/records\?.*page=1/);assert.match(e.requests[1].url,/participations\?.*page=2/);assert.match(e.requests[1].url,/start=2026-01-01/);assert.match(e.requests[1].url,/end=2026-12-31/);
});
for(const [tab,endpoint] of [['tasks','/tasks'],['batches','/inbound-batches'],['schedules','/integration-schedules']])test(`data hub ${tab} uses authenticated server page/filter`,async()=>{
 const e=engine(responder);e.t.setState('hub',{tab,data_type:'teacher_hr'},2);await e.t.pages.hub();
 const r=e.requests.find(x=>x.url.startsWith('/api'+endpoint+'?'));assert.ok(r);assert.match(r.url,/connection_id=c-middle/);assert.match(r.url,/page=2/);assert.match(r.url,/data_type=teacher_hr/);
 if(tab==='tasks')assert.match(r.url,/kind=integration/);
});
test('SSO page does not create fake login or mutate connection',async()=>{
 const e=engine(url=>url.includes('/catalog')?{items:[{connection:{...connection,id:'sso',code:'sso',name:'统一认证'},data_types:[{data_type:'identity',name:'身份',local_status:'WAITING_PROTOCOL'}]}]}:{items:[]});e.t.setState('sso',{tab:'overview'});const html=await e.t.pages.sso();
 assert.match(html,/学校统一认证尚未真实联调/);assert.match(html,/本地账号仍可继续演示现有业务/);assert.ok(e.requests.every(x=>x.options.method==='GET'));
 assert.doesNotMatch(customerVisible(html),/\b(?:NOT_CONNECTED|CONNECTED|REAL|TEST)\b/);
});
test('failed proof renders a Chinese reason while internal evidence stays folded',async()=>{
 const e=engine(responder);e.t.setState('hub',{tab:'proof'});const html=await e.t.pages.hub(),visible=customerVisible(html);
 assert.match(visible,/真实接口适配程序尚未安装/);assert.match(visible,/真实联调/);assert.doesNotMatch(visible,/ADAPTER_NOT_INSTALLED|logic_revision|\bREAL\b|>8</);assert.doesNotMatch(visible,/badge green-b/);
 assert.match(html,/实施人员使用：验证追踪信息/);assert.match(html,/ADAPTER_NOT_INSTALLED/);assert.match(html,/&quot;logic_revision&quot;: 8/);
});
test('nonadmin never requests admin-only checks, schedules or inbound batches',async()=>{
 const e=engine(responder);e.t.setUser({user:{id:'x',name:'操作员',is_admin:false},role:{kind:'school'},permissions:['portal.read','sync.manage']});
 for(const tab of ['proof','schedules','batches']){e.t.setState('hub',{tab});const html=await e.t.pages.hub();assert.match(html,/管理员/)}
 assert.ok(!e.requests.some(x=>/\/checks|\/inbound-batches|\/integration-schedules/.test(x.url)));
});
test('integration hash retains tab/type/status without business-ID pollution',()=>{
 const filter={tab:'tasks',data_type:'teacher_hr',state:'FAILED',teacher_id:'forbidden'};
 assert.deepEqual(scope.restoreNavigation(scope.navigationHash('hub',filter),{hub:'中台'}),{page:'hub',filter:{tab:'tasks',data_type:'teacher_hr',state:'FAILED'},periodId:''});
});
test('forbidden direct hash does not fetch API data or expose design controls',async()=>{
 const e=engine(responder,'teacher');e.t.setUser({user:{id:'u',name:'教师',is_admin:false},role:{kind:'teacher'},permissions:['portal.read']});e.t.setState('hub');await e.t.render();
 assert.equal(e.requests.length,0);assert.match(e.node('#content').innerHTML,/未授权访问/);
});
test('real API writes retain CSRF and idempotency and never report non-2xx as success',async()=>{
 const e=engine(async()=>({ok:true}));await e.t.api('/connections/c/probe',{method:'POST',body:{expected_version:1,reason:'test'}});
 const o=e.requests[0].options;assert.equal(o.headers['X-CSRF-Token'],'test-csrf');assert.ok(o.headers['Idempotency-Key']);assert.equal(o.credentials,'same-origin');assert.equal(o.cache,'no-store');
 e.ctx.fetch=async()=>({ok:false,status:409,json:async()=>({detail:'版本冲突',request_id:'req'})});await assert.rejects(()=>e.t.api('/x',{method:'POST',body:{}}),/版本冲突/);
});
test('network failure has no fixture fallback',async()=>{
 const e=engine();e.ctx.fetch=async()=>{throw Error('offline')};await assert.rejects(()=>e.t.api('/statistics'),/网络连接中断/);
});
test('live connection form does not invent mappings or force a default auth protocol',async()=>{
 const e=engine(responder);e.t.captureForm();await e.t.connectionForm('c-middle');const form=e.t.getForm(),visible=customerVisible(form.body);
 for(const label of ['学校基本资料','学校公开标识','连接检查','服务器交接','正式接口总地址','服务器凭据固定引用','等待学校确认'])assert.match(visible,new RegExp(label));
 assert.doesNotMatch(visible,/\[\]|teacher_no|SAMPLE-001|external_subject|X-Api-Key|X-Timestamp|X-Nonce|X-Signature/);
 assert.match(form.body,/name="secret_env"[^>]*readonly/);
});
test('coordination download uses protected genuine xlsx rather than prototype fixture bytes',()=>{
 assert.ok(source.includes("download('/connections/coordination.xlsx'"));assert.doesNotMatch(source,/sample\.b64|data:application\/vnd|localStorage|sessionStorage/);
});
test('inbound row pagination is reachable by actual handler',async()=>{
 const e=engine(()=>({batch:{id:'b',data_type:'teacher_hr',state:'PREVIEW',total:61,errors:0},rows:{items:[],page:2,size:30,total:61}}));await e.t.handlers['inbound-page']('b|2');assert.match(e.requests[0].url,/page=2/);assert.match(e.node('#modal-root').innerHTML,/inbound-page/);
});
test('timestamp keeps an existing timezone instead of appending invalid Z',()=>{
 const e=engine();assert.doesNotMatch(e.t.ts('2026-09-19T18:00:00+08:00'),/Invalid/);assert.doesNotMatch(e.t.ts('2026-09-19T10:00:00Z'),/Invalid/);
});
test('all approved core local operations keep their original handler bindings',()=>{
 const e=engine();for(const h of ['record-form','qualification-form','point-adjust','assessment','org-assessment','import-confirm','task-download','connection-probe','connection-activate','sync-item-retry','schedule-form','inbound-confirm','role-permissions'])assert.equal(typeof e.t.handlers[h],'function',h);
});

test('historical TEST proof never looks like current real connection success',async()=>{
 const e=engine(url=>url.includes('/checks')?{items:[{mode:'TEST',passed:true,created_at:'2026-09-19T00:00:00Z',expires_at:'2026-09-19T01:00:00Z',receipt:{_connection_revision:8}}]}:responder(url));
 e.t.setState('hub',{tab:'proof'});const html=await e.t.pages.hub(),visible=customerVisible(html);assert.match(visible,/本地或测试通过 · 不可启用/);assert.match(visible,/证明到期/);assert.doesNotMatch(visible,/\bTEST\b|logic_revision|badge green-b/);assert.match(html,/实施人员使用：验证追踪信息/);
});
test('transport task status label does not claim business rows are committed',async()=>{
 const e=engine(url=>url.startsWith('/api/tasks?')?{items:[{id:'t',kind:'inbound_pull',state:'DONE',payload:{data_type:'teacher_hr'},attempts:1}],total:1,page:1,size:20}:responder(url));e.t.setState('hub',{tab:'tasks'});const html=await e.t.pages.hub();assert.match(html,/任务状态（非入库结果）/);
});

test('SSO logout invokes the dedicated route and follows only the server result',async()=>{
 const e=engine(()=>({logged_out:true,sso_logout_url:'https://idp.example/logout'}));
 let destination='';e.ctx.location.assign=url=>{destination=url};
 e.t.setUser({user:{id:'teacher'},role:{kind:'teacher'},permissions:[],sso_session:true,csrf:'test-csrf'});
 await e.t.handlers.logout();assert.equal(e.requests[0].url,'/api/auth/sso/logout');assert.equal(destination,'https://idp.example/logout');
});
test('adapter code configuration stays collapsed for customer-facing settings',()=>{
 const e=engine(()=>catalog);e.t.captureForm();
 return e.t.connectionForm('c-middle').then(()=>{const html=e.t.getForm().body,tags=implementationDetailTags(html),visible=customerVisible(html);assert.ok(tags.length>=2);assert.ok(tags.every(tag=>!/[\s>]open(?:[\s=>]|$)/.test(tag)));assert.match(html,/实施人员使用：高级参数与原始配置/);assert.doesNotMatch(visible,/高级协议参数 JSON|字段对应 JSON|X-Api-Key|X-Timestamp|X-Nonce|X-Signature/);});
});
test('data hub exposes five real Chinese configuration entries and the confirmation chain',async()=>{
 const e=engine(integrationResponder);e.t.setState('hub',{tab:'overview'});const html=await e.t.pages.hub();
 for(const name of middleTypes.map(x=>x.name))assert.match(html,new RegExp(name));
 assert.equal((html.match(/data-action="data-type-adapter"/g)||[]).length,5);assert.equal(typeof e.t.handlers['data-type-adapter'],'function');assert.equal(typeof e.t.handlers['inbound-confirm'],'function');
});
test('province connector exposes all eleven Chinese configuration entries',async()=>{
 const e=engine(integrationResponder);e.t.setState('province',{tab:'overview'});const html=await e.t.pages.province();
 for(const name of provinceTypes.map(x=>x.name))assert.match(html,new RegExp(name));
 assert.equal((html.match(/data-action="data-type-adapter"/g)||[]).length,11);assert.equal(typeof e.t.handlers['data-type-adapter'],'function');
});
test('each of the three connectors renders its six-item school material checklist truthfully',async()=>{
 const cases=[
  ['sso',['正式认证规范','登录与退出地址','回调登记规则','身份与组织字段字典','测试账号与异常规则','凭据交付方式']],
  ['hub',['五类接口清单','正式字段字典','分页与增量规则','成功与错误规则','脱敏正常与异常样本','凭据交付方式']],
  ['province',['省平台正式规范','机构与应用登记','签名与防重复规则','十一类数据字段字典','回执与错误码','脱敏正常与异常样本']],
 ];
 for(const[route,names]of cases){const e=engine(integrationResponder);e.t.setState(route,{tab:'overview'});const html=await e.t.pages[route](),visible=customerVisible(html);assert.match(visible,/学校资料清单/);assert.match(visible,/已登记 0 \/ 6/);assert.equal((html.match(/class="material-row"/g)||[]).length,6);assert.equal((html.match(/data-material-state="pending"/g)||[]).length,6);for(const name of names)assert.match(visible,new RegExp(name));assert.doesNotMatch(visible,/\b(?:NOT_CONNECTED|CONNECTED|WAITING_SOURCE|WAITING_PROTOCOL|ADAPTER_NOT_INSTALLED|REAL|TEST)\b/);assert.ok(e.requests.every(x=>x.options.method==='GET'));}
});
test('one-stop integration center totals the material checklist without English implementation states',async()=>{
 const e=engine(integrationResponder);e.t.setState('implementation');const html=await e.t.pages.implementation(),visible=customerVisible(html);
 for(const label of ['资料齐备','配置有效','测试结果','配置发布','运行健康','学校验收'])assert.match(visible,new RegExp(label));assert.match(visible,/统一认证与接口适配中心/);assert.equal((html.match(/data-action="nav"/g)||[]).length,4);// 3 个接口入口 + “返回对接与同步”assert.doesNotMatch(visible,/0 \/ 18|当前完成度|\b(?:NOT_CONNECTED|CONNECTED|WAITING_SOURCE|WAITING_PROTOCOL)\b/);
});
test('middle data-type form covers request, pagination and response rules with technical details folded',async()=>{
 const e=engine(integrationResponder);e.t.captureForm();assert.equal(typeof e.t.handlers['data-type-adapter'],'function');await e.t.handlers['data-type-adapter']('c-middle|teacher_hr');
 const form=e.t.getForm(),html=form.body,visible=customerVisible(html);assert.match(form.title,/一页填写采集规则 · 教师人事信息/);
 for(const label of ['接口位置','返回数据','翻页方式','游标翻页','页码翻页','每次读取数量','成功标志字段路径','数据列表字段路径'])assert.match(visible,new RegExp(label));
 const tags=implementationDetailTags(html);assert.equal(tags.length,3);assert.ok(tags.every(tag=>!/[\s>]open(?:[\s=>]|$)/.test(tag)));assert.match(html,/下一游标字段路径/);assert.doesNotMatch(visible,/完整规则 JSON|X-Api-Key|X-Timestamp|X-Nonce|X-Signature/);
});
test('province data-type form covers payload, receipt and failure rules with technical details folded',async()=>{
 const e=engine(integrationResponder);e.t.captureForm();assert.equal(typeof e.t.handlers['data-type-adapter'],'function');await e.t.handlers['data-type-adapter']('c-province|training_project');
 const form=e.t.getForm(),html=form.body,visible=customerVisible(html);assert.match(form.title,/一页填写报送规则 · 培训项目/);
 for(const label of ['接口位置','接收回执','业务数据放入的字段名','接收成功标志字段路径','回执编号字段路径'])assert.match(visible,new RegExp(label));
 const tags=implementationDetailTags(html);assert.equal(tags.length,3);assert.ok(tags.every(tag=>!/[\s>]open(?:[\s=>]|$)/.test(tag)));assert.match(html,/返回代码字段路径/);assert.match(html,/学校确认的失败代码/);assert.doesNotMatch(visible,/完整规则 JSON|X-Api-Key|X-Timestamp|X-Nonce|X-Signature/);
});

test('calculation result is a Chinese business summary without internal IDs',()=>{
 const html=engine().t.calculationSummary({batch_id:'hidden-id',summary:{teachers:1,entry_count:2}},'points');
 assert.match(html,/教师积分/);assert.match(html,/新增积分流水/);assert.doesNotMatch(html,/batch_id|hidden-id|<pre/);
});
test('business evidence hides technical keys and escapes visible values',()=>{
 const html=engine().t.evidenceHtml({hours:10,id:'hidden-id',teacher_id:'secret-id',name:'<script>'});
 assert.match(html,/授课学时/);assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/hidden-id|secret-id|teacher_id|<script>/);
});
test('point items use rule labels or Chinese fallbacks',()=>{
 const t=engine().t;assert.equal(t.pointLabel({item_key:'hours'}),'授课贡献');assert.equal(t.pointLabel({item_key:'unknown'}),'积分调整项');
 assert.equal(t.pointLabel({item_key:'x',source_snapshot:{rule:{config:{components:[{key:'x',label:'学校指标'}]}}}}),'学校指标');
});

test('export task lists show Chinese type and business status instead of internal codes',async()=>{
 const e=engine(()=>({items:[{id:'t',kind:'export',state:'DONE',payload:{kind:'assessments'},result:{filename:'internal-code.xlsx'},attempts:1}],page:1,size:20,total:1}));
 const html=await e.t.pages.exports();assert.match(html,/教师考核/);assert.match(html,/文件已生成/);assert.doesNotMatch(html,/internal-code.xlsx|>assessments</);
});

test('教师参训导出任务准确标识业务类型，不显示成课程人次',async()=>{
 const e=engine(()=>({items:[{id:'part-export',kind:'export',state:'DONE',payload:{kind:'participations'},attempts:1}],page:1,size:20,total:1}), 'teacher');
 const html=await e.t.pages.exports();
 assert.match(html,/教师参训记录/);assert.doesNotMatch(html,/课程人次|>participations</);
});

test('实际台账页面上下文包含统一时间格式，历次报送可完整渲染',async()=>{
 const stamp='2026-10-11T21:57:00',totals={claimed_total:'30',recommended_total:'30',final_total:'30',pending_rows:0};
 const detail={id:'context-time',version:1,org_name:'合成学院',can_review:false,can_draft:false,note:'',versions:[{id:'old',version_no:1,created_at:stamp,totals},{id:'context-time',version_no:2,created_at:stamp,totals}],totals,data:{year:2026,version_no:2,template_label:'合成台账',file:{name:'合成.xlsx'},summary:{serious:0},rows:[]}};
 const e=engine(async()=>detail),c=vm.runInContext('ledgerContext()',e.ctx);c.render=async()=>{};
 await ledgers.ledgerAction('tz-detail','context-time',c);
 try{const html=await ledgers.ledgerPage(c);assert.ok(html.includes(e.t.ts(stamp)));assert.match(html,/历次报送/)}finally{await ledgers.ledgerAction('tz-back','',c)}
});
test('local configuration history renders Chinese fields and escapes values',()=>{
 const e=engine();const render=vm.runInContext('settingSnapshot',e.ctx);
 const html=render('branding',{value:{school_name:'<学校>',password:'never-show'}});
 assert.match(html,/学校名称/);assert.match(html,/&lt;学校&gt;/);assert.doesNotMatch(html,/school_name|never-show|<pre/);
 const audit=vm.runInContext('auditBusinessSnapshot',e.ctx)({state:'APPROVED',permissions:['export'],password:'private',unknown_field:'internal'});
 assert.match(audit,/审核通过/);assert.match(audit,/授权表格导出/);assert.doesNotMatch(audit,/APPROVED|private|internal|unknown_field/);
});
test('export summaries never invent zero rows when the server has no row count',()=>{
 const render=vm.runInContext('exportResultSummary',engine().ctx);
 assert.match(render({size:2048,filename:'internal.xlsx'}),/以下载文件为准/);
 assert.doesNotMatch(render({size:2048}),/0 条|<pre/);
 assert.match(render({count:0,size:1024}),/0 条/);
});
test('notice read always uses the authorized detail endpoint',async()=>{
 const e=engine(()=>({title:'学校通知',category:'业务通知',body:'<script>',created_at:'2026-09-20T00:00:00'}));
 await e.t.handlers.notice('notice-id');
 assert.equal(e.requests[0].url,'/api/notices/notice-id');
 assert.match(e.node('#modal-root').innerHTML,/&lt;script&gt;/);
});
test('通知发布范围使用授权接口名称，不依赖教师组织目录包含上级',async()=>{
 const e=engine(()=>({items:[{id:'n',title:'年度公示',category:'公示',org_id:'school-outside-catalog',org_name:'合成<学校>',created_at:'2026-10-12'}],total:1,page:1,size:20}),'teacher');
 const html=await e.t.pages.notices();
 assert.match(html,/合成&lt;学校&gt;/);assert.doesNotMatch(html,/<学校>|school-outside-catalog/);
});
test('todo page sends filters and page and exposes subsequent pages',async()=>{
 const e=engine(()=>({items:[{id:'q',type:'qualification',title:'资质核对',state:'DRAFT',teacher_id:'u'}],total:24,page:2,size:20}));
 e.t.setState('todos',{q:'资质',type:'qualification'},2);
 const html=await e.t.pages.todos();
 const params=new URL('https://test.invalid'+e.requests[0].url).searchParams;
 assert.equal(params.get('page'),'2');assert.equal(params.get('type'),'qualification');
 assert.equal(params.get('q'),'资质');assert.match(html,/上一页/);
});
test('rule editors generate hidden stable keys with Chinese business inputs',()=>{
 const e=engine(),row=vm.runInContext('ruleRow',e.ctx),org=vm.runInContext('orgRuleRow',e.ctx);
 const html=row();assert.match(html,/type="hidden" data-r="key"/);
 assert.doesNotMatch(html,/placeholder="hours"|积分项编码/);
 const a=org(),b=org();assert.notEqual(a.match(/value="(item_[^"]+)"/)[1],b.match(/value="(item_[^"]+)"/)[1]);
 assert.match(row({key:'existing',label:'既有指标'}),/value="existing"/);
});
test('Chinese dictionary editor serializes all statuses through the real save callback',async()=>{
 const e=engine(async url=>url.startsWith('/api/settings/')?{}:({items:[]}));
 e.t.captureForm();
 vm.runInContext("view={items:[{key:'business_dictionary',version:1,value:{notice_categories:['通知'],record_sources:['人工'],status_labels:{DRAFT:'草稿',APPROVED:'通过'}}}]};boot=async()=>{}",e.ctx);
 await vm.runInContext("settingForm('business_dictionary')",e.ctx);
 const rows=[{dataset:{statusKey:'DRAFT'},value:'待完善'},{dataset:{statusKey:'APPROVED'},value:'审核通过'}];
 const form={querySelectorAll:selector=>selector==='[data-status-key]'?rows:[]};
 await e.t.getForm().callback({notice_categories:'通知',record_sources:'人工',reason:'调整显示',basis:''},form);
 const body=JSON.parse(e.requests.find(r=>r.options.method==='PUT').options.body);
 assert.deepEqual(body.value.status_labels,{DRAFT:'待完善',APPROVED:'审核通过'});
 assert.equal(body.expected_version,1);
});

test('validation failures translate fields and English messages without dumping data',async()=>{
 const e=engine();e.ctx.fetch=async()=>({ok:false,status:422,json:async()=>({detail:'输入校验未通过',errors:[{field:'body.reason',message:'String should have at least 2 characters'},{field:'body.teacher_id',message:'Field required'},{field:'body.internal_field',message:'Input should be a valid integer'}],request_id:'r1'})});
 await assert.rejects(()=>e.t.api('/records'),error=>{assert.match(error.message,/办理意见：至少需要2个字符/);assert.match(error.message,/教师：请填写此项/);assert.doesNotMatch(error.message,/body\.|internal_field|String|integer/);return true});
});

test('configuration history retains system meaning after school renames a status',()=>{
 const e=engine();vm.runInContext("labels.DRAFT='待完善'",e.ctx);
 const html=vm.runInContext('settingSnapshot',e.ctx)('business_dictionary',{status_labels:{DRAFT:'旧显示名称'}});
 assert.match(html,/草稿/);assert.match(html,/旧显示名称/);assert.doesNotMatch(html,/待完善/);
});

test('points calculation submits checked Chinese item choices through actual callback',async()=>{
 const e=engine(url=>url.includes('/calculation-items')?{items:[{key:'hours',label:'授课贡献'}]}:url==='/api/rules'?{items:[{name:'学校测试规则',kind:'points',period_id:'p',state:'ACTIVE',version_no:2}]}:{summary:{teachers:1,entry_count:1}});
 e.t.setData([{id:'p',name:'隔离周期',state:'OPEN'}],[{id:'t',name:'教师',active:true}]);e.t.captureForm();
 e.node('#calculation-items').dataset={};e.node('#calculation-impact').dataset={};e.node('#f-period_id').value='p';
 vm.runInContext('render=async()=>{}',e.ctx);
 await e.t.handlers.calculate('points');assert.match(e.node('#calculation-items').innerHTML,/授课贡献/);
 const f={querySelectorAll:s=>s==='input[name=person]:checked'?[{value:'t'}]:s==='input[name=calculation_item]:checked'?[{value:'hours'}]:[],querySelector:s=>e.node(s)};
 await e.t.getForm().callback({period_id:'p',reason:'隔离验收',basis:''},f);
 const body=JSON.parse(e.requests.find(r=>r.url==='/api/points/calculate').options.body);
 assert.deepEqual(body.teacher_ids,['t']);assert.deepEqual(body.item_keys,['hours']);
});

test('organization copy submits adjusted indicators and retains source version check',async()=>{
 const original={id:'r',name:'学校规则',version:3,period_id:'p',config:{components:[{key:'income',label:'收入贡献',source:'income',weight:100,target:1000}]}};
 const e=engine(url=>url.endsWith('/copy')?{id:'new'}:{items:[original]});e.t.captureForm();e.t.setData([{id:'p',name:'开放周期',state:'OPEN'}]);
 vm.runInContext('render=async()=>{};showOrgRule=async()=>{}',e.ctx);
 await e.t.handlers['org-rule-copy']('r');assert.match(e.t.getForm().body,/收入贡献/);
 const row={querySelectorAll:()=>Object.entries({key:'income',label:'新收入目标',source:'income',weight:'100',target:'2000'}).map(([or,value])=>({dataset:{or},value}))};
 e.node('#org-rule-rows').querySelectorAll=()=>[row];
 await e.t.getForm().callback({name:'新草稿',period_id:'p',reason:'学校确认新目标'});
 const body=JSON.parse(e.requests.find(r=>r.url.endsWith('/copy')).options.body);
 assert.equal(body.expected_version,3);assert.equal(body.config.components[0].target,'2000');assert.equal(body.config.components[0].key,'income');assert.equal(original.config.components[0].target,1000);
});

test('audit filter context survives refresh and remains limited to audit fields',()=>{
 const f={module:'settings',result:'SUCCESS',start:'2026-09-01',end:'2026-09-20',q:'字典',teacher_id:'must-not-leak'};
 const state=scope.restoreNavigation(scope.navigationHash('audit',f),{audit:'审计'});
 assert.deepEqual(state.filter,{module:'settings',result:'SUCCESS',start:'2026-09-01',end:'2026-09-20',q:'字典'});
});

test('calculation evidence uses Chinese limit descriptions without changing arithmetic',()=>{
 const e=engine();const html=e.t.evidenceHtml({formula:'max(0, min(100.00 ÷ 2000, 1)) × 100'});
 assert.match(html,/取较大值\(0, 取较小值\(100.00 ÷ 2000, 1\)\) × 100/);assert.doesNotMatch(html,/max|min/);
});
const homeSummary={scope_label:'测试学院',as_of:'2026-09-20',scope_note:'待办理与资质提醒包含全部周期，不受下方统计筛选影响。',tasks:{items:[],total:0,returned:0},reminders:{items:[],total:0,expired:0}};
function homeResponse(url){
 if(url.startsWith('/api/portal/workbench'))return structuredClone(homeSummary);
 if(url.startsWith('/api/statistics'))return {income:300,participants:10,teachers:2,projects:2,trend:[],assessment_states:{},metric_notes:{}};
 if(url.startsWith('/api/teacher-activity-summary'))return {teaching:{records:1,hours:10},participation:{records:0,hours:0}};
 if(url.startsWith('/api/assessment-summary/latest'))return {assessment:null};
 if(url.startsWith('/api/connections/summary'))return {items:['sso','middle','province'].map(code=>({code,connection_state:'NOT_CONNECTED'}))};
 return {items:[],total:0,sum:0};
}
// 老师的工作总览单独设计（易用性第 6 条），见下方 teacher home 用例。
for(const role of ['dept','college','school'])test('task-first home preserves role entry points: '+role,async()=>{
 const e=engine(homeResponse,role);e.t.setState('home');
 const html=await e.t.pages.home();
 assert.ok(html.indexOf('workbench-pending')<html.indexOf('workbench-statistics'));
 assert.ok(html.indexOf('workbench-shortcuts')<html.indexOf('workbench-statistics'));
 assert.doesNotMatch(html,/portal-hero|NOT_CONNECTED|NaN/);
 assert.match(html,/待办理与资质提醒包含全部周期/);
 assert.equal(e.requests.some(x=>x.url.startsWith('/api/connections/summary')),role==='school');
 if(role==='teacher'){assert.match(html,/我的培训/);assert.doesNotMatch(html,/本组织工作台|学校概况|学校接口状态/);}
 if(role==='dept'||role==='college'){assert.match(html,role==='dept'?/本教研室管理/:/本学院与教研室管理/);assert.doesNotMatch(html,/data-id="cockpit"|学校接口状态/);}
 if(role==='school'){assert.match(html,/学校接口状态/);assert.ok(html.indexOf('学校接口状态')>html.indexOf('业务概况'));}
 assert.ok(e.requests.every(x=>x.options.method==='GET'));
});
test('home task and expiry summaries escape business content and retain actual dates',async()=>{
 const e=engine(url=>url.startsWith('/api/portal/workbench')?{...homeSummary,
 tasks:{total:1,returned:1,items:[{id:'q',type:'qualification',title:'<img src=x>',owner_name:'<script>x</script>',state:'RETURNED'}]},
 reminders:{total:1,expired:1,items:[{id:'r',type:'qualification',title:'测试证书',owner_name:'本人',state:'EXPIRING',expires:'2026-09-19',days_remaining:-1}]}}:homeResponse(url),'dept');
 const html=await e.t.pages.home();assert.match(html,/&lt;img src=x&gt;/);assert.doesNotMatch(html,/<script>|<img src=x>/);
 assert.match(html,/已过期 1 天/);assert.match(html,/有效期至 2026-09-19/);assert.match(html,/qualification\|q/);
});
test('home permissions remove unauthorized shortcuts even for named school role',async()=>{
 const e=engine(homeResponse);e.t.setUser({user:{id:'u',name:'受限管理员'},role:{kind:'school',name:'学校管理'},permissions:['portal.read']});
 const html=await e.t.pages.home();
 const start=html.indexOf('workbench-shortcuts');
 const shortcuts=html.slice(start,html.indexOf('</section>',start));
 assert.doesNotMatch(shortcuts,/data-id="(?:projects|courses|bases|records|qualifications|points|assessment|organization)"/);
});
test('home active statistics conditions are visible and never filter task summary',async()=>{
 const e=engine(homeResponse);e.t.setState('home',{project_code:'P1'},1,1,'period-1');
 const html=await e.t.pages.home();assert.match(html,/更多统计筛选 · 已启用 1 项/);
 assert.match(html,/portal-filters" open/);
 assert.match(html,/workbench-statistics business-guide" open/);
 assert.equal(e.requests.find(x=>x.url.includes('/portal/workbench')).url,'/api/portal/workbench');
 assert.match(e.requests.find(x=>x.url.includes('/statistics')).url,/period_id=period-1/);
});
test('failed home task source is not represented by a false zero',async()=>{
 const e=engine(url=>{if(url.includes('/portal/workbench'))throw Error('service unavailable');return homeResponse(url)});
 await assert.rejects(()=>e.t.pages.home(),/网络连接中断/);
});
test('home reminder view-all uses existing authorized todo filter',async()=>{
 const e=engine(homeResponse);await e.t.handlers['home-todos']('qualification');
 assert.equal(e.t.getState().page,'todos');assert.equal(e.t.getState().filter.type,'qualification');
 assert.match(e.requests.at(-1).url,/type=qualification/);
});
test('global search is explicitly named when its visual text is hidden on mobile',()=>{
 assert.match(source,/data-action="search" aria-label="搜索菜单与业务"/);
 const css=fs.readFileSync(new URL('../../frontend/portal.css',import.meta.url),'utf8');
 assert.match(css,/@media\(max-width:620px\)\{\.topbar \.search-trigger\{display:flex/);
});

test('selected design keeps all authorized navigation and Chinese group headings',()=>{
 const e=engine();const html=e.t.sidebarNavigation();
 for(const title of ['工作总览','考核（数据与分析）','业务办理','系统管理','表格导入导出','对接与同步','规则与配置','日志与运行','账号与权限'])assert.ok(html.includes(title));
 for(const route of ['home','todos','records','qualifications','points','assessment','rules','permissions','audit','sync','imports'])assert.ok(html.includes('data-id="'+route+'"'));
 // 系统管理简化：字典参数、运行备份、导出下载并入合并页的标签，不再单独占菜单。
 for(const route of ['settings','operations','exports'])assert.ok(!html.includes('data-id="'+route+'"'));
 assert.equal((html.match(/aria-expanded="true"/g)||[]).length,4);
 assert.match(html,/aria-controls="nav-group-0"/);assert.match(html,/title="工作总览" aria-label="工作总览"/);
 const business=html.slice(html.indexOf('>业务办理<'),html.indexOf('>考核（数据与分析）<'));
 for(const title of ['培训项目管理','教师资质管理','培训课程管理','培训基地管理','表格导入导出'])assert.ok(business.includes(title));
 assert.doesNotMatch(business,/data-id="points"|data-id="assessment"/);
});
test('navigation does not expose unauthorized items or empty groups',()=>{
 const e=engine();e.t.setUser({user:{id:'u',name:'教师'},role:{kind:'teacher'},permissions:['portal.read']});
 const html=e.t.sidebarNavigation();assert.match(html,/工作总览/);assert.doesNotMatch(html,/系统管理|数据与分析|业务办理|data-id="settings"|data-id="organization"/);
});
test('desktop rail toggle updates accessible name and expanded state without network',()=>{
 const e=engine();e.t.handlers['collapse-sidebar']();assert.equal(e.node('#sidebar').classList.contains('collapsed'),true);
 assert.equal(e.node('.sidebar-collapse').getAttribute('aria-label'),'展开侧边栏');
 assert.equal(e.node('.sidebar-collapse').getAttribute('aria-expanded'),'false');
 e.t.handlers['collapse-sidebar']();assert.equal(e.node('.sidebar-collapse').getAttribute('aria-expanded'),'true');assert.equal(e.requests.length,0);
});
test('group toggle updates visibility state and accessible expansion',()=>{
 const e=engine(),section=e.node('group'),button=e.node('group-button');button.closest=()=>section;button.setAttribute('aria-expanded','true');
 e.t.handlers['toggle-nav-group']('',button);assert.equal(section.classList.contains('is-closed'),true);assert.equal(button.getAttribute('aria-expanded'),'false');
 e.t.handlers['toggle-nav-group']('',button);assert.equal(section.classList.contains('is-closed'),false);
});
test('mobile drawer hides background from keyboard and restores it on close and desktop resize',()=>{
 const e=engine();e.ctx.window.matchMedia=()=>({matches:true});e.t.syncMenuAccessibility();
 assert.equal(e.node('#sidebar').inert,true);assert.equal(e.node('.main-shell').inert,false);
 e.t.handlers['toggle-menu']();assert.equal(e.node('#sidebar').inert,false);assert.equal(e.node('.main-shell').inert,true);
 assert.equal(e.node('.mobile-nav').getAttribute('aria-expanded'),'true');
 e.t.handlers['close-menu']();assert.equal(e.node('#sidebar').inert,true);assert.equal(e.node('.main-shell').inert,false);
 e.ctx.window.matchMedia=()=>({matches:false});e.t.syncMenuAccessibility();assert.equal(e.node('#sidebar').inert,false);
});
test('secondary shortcuts are preserved in a native disclosure, not removed',async()=>{
 const e=engine(homeResponse);const html=await e.t.pages.home();
 assert.match(html,/<details class="workbench-more"><summary>更多常用操作/);
 assert.match(html,/data-id="points"/);assert.match(html,/data-id="cockpit"/);
 assert.match(html,/查看全部待办/);assert.doesNotMatch(html,/设计预览|合成示例/);
});

test('驾驶舱未运行同步时不显示空图，有零条结果的真实任务仍保留图表',async()=>{
 let ran=false;
 const e=engine((url,options)=>url.startsWith('/api/connections/summary')?{items:[{name:'学校数据中台',code:'middle',connection_state:'NOT_CONNECTED',latest_task:ran?{display_state:'DONE',success_count:0,failed_count:0,pending_confirmation_count:0}:null}]}:homeResponse(url,options));
 e.ctx.syncStatusChart=()=>'<div data-test="sync-plot"></div>';
 let html=await e.t.pages.cockpit();assert.doesNotMatch(html,/data-test="sync-plot"/);assert.match(html,/尚无任务/);
 ran=true;html=await e.t.pages.cockpit();assert.match(html,/data-test="sync-plot"/);
});

function closeoutWorkspaceFixture(){
 return {connection_id:'c-sso',code:'sso',name:'学校统一认证',connection_version:2,draft_version:1,has_draft:true,issues:[],
  statuses:{materials:'资料待登记',configuration:'配置校验通过',tests:'待真实测试',published:'已发布',health:'最近检查通过',acceptance:'待学校签认'},
  callbacks:{login:'https://school.example/api/auth/sso/callback',test_login:'https://school.example/api/auth/sso/implementation-callback',logout_return:'https://school.example/',readonly:true},
  credential:{reference:'ND_SSO_SECRET',configured:true,values_returned:false,version:1,
   metadata:{credential_type:'certificate',managed_by:'file_mount',owner:'信息中心',certificate_fingerprint_sha256:'a'.repeat(64),valid_from:'2026-09-01',valid_until:'2027-09-01',next_rotation_on:'2027-08-01'},
   asset_status:{state:'安全资产有效',issues:[],credential_type_name:'服务证书',managed_by_name:'受控文件挂载'}},
  materials:{version:0,required:[],items:[]},health:{},check:null,data_types:[],source_gaps:[],
  acceptance:{version:0,record:{items:[]},summary:{state:'待学校签认',passed:0,total:1,signed:false,stale:false,source_gaps:[],requirements:[{code:'real_login',label:'真实单点登录与状态校验'}]}}};
}

test('credential step exposes certificate lifecycle metadata and safe edit entry',async()=>{
 const e=engine(url=>url.includes('/implementation')?closeoutWorkspaceFixture():integrationResponder(url));
 e.t.setState('sso',{tab:'implementation',impl_step:'credentials'});
 const html=await e.t.pages.sso(),visible=customerVisible(html);
 for(const label of ['安全资产状态','凭据类型','安全保管方式','轮换责任人','证书校验指纹'])assert.match(visible,new RegExp(label));
 assert.match(html,/data-action="impl-credential-meta"/);assert.equal(typeof e.t.handlers['impl-credential-meta'],'function');
});

test('diagnostics step keeps school acceptance evidence separate from release',async()=>{
 const fixture=closeoutWorkspaceFixture();
 fixture.acceptance.record.items=[{code:'real_login',status:'PENDING',evidence_ref:'',school_contact:'',checked_on:null}];
 const e=engine(url=>url.includes('/implementation')?fixture:integrationResponder(url));
 e.t.setState('sso',{tab:'implementation',impl_step:'diagnostics'});
 const html=await e.t.pages.sso(),visible=customerVisible(html);
 assert.match(visible,/学校验收台账/);assert.match(visible,/真实单点登录与状态校验/);assert.match(visible,/待学校签认/);
 assert.match(html,/data-action="impl-acceptance"/);assert.equal(typeof e.t.handlers['impl-acceptance'],'function');
 assert.doesNotMatch(visible,/自动验收通过/);
});

test('implementation step survives URL roundtrip',()=>{
 const hash=scope.navigationHash('sso',{tab:'implementation',impl_step:'credentials'});
 const restored=scope.restoreNavigation(hash,{sso:'学校统一认证'});
 assert.equal(restored.filter.tab,'implementation');assert.equal(restored.filter.impl_step,'credentials');
});

test('one-stop integration center exposes school intake download and draft-only import entries',async()=>{
 const e=engine(integrationResponder);e.t.setState('implementation');const html=await e.t.pages.implementation();
 assert.match(html,/下载学校资料采集表/);assert.match(html,/导入学校填写表/);
 assert.match(html,/data-action="integration-intake-download"/);
 assert.match(html,/data-action="integration-intake-import"/);
 assert.equal(typeof e.t.handlers['integration-intake-download'],'function');
 assert.equal(typeof e.t.handlers['integration-intake-import'],'function');
 assert.equal(typeof e.t.handlers['integration-intake-confirm'],'function');
});

test('confirmed province source becomes visible without claiming interface readiness',()=>{
 const e=engine();
 const confirmed={data_type:'plan',name:'培训计划',local_status:'WAITING_SOURCE',mapping_count:0,
  source_confirmed:true,source_system:'学校教务系统'};
 const html=e.t.sourceAvailability('province',confirmed);
 assert.match(html,/权威来源已确认/);assert.match(html,/学校教务系统/);
 assert.doesNotMatch(html,/待确认权威来源/);
});

test('inline record detail escapes data, collapses, and discards results after navigation',async()=>{
 let finish;
 const e=engine(()=>new Promise(resolve=>{finish=resolve}));
 const panel={isConnected:true,innerHTML:''},detail={hidden:true,querySelector:()=>panel};
 const row={nextElementSibling:detail,classList:{add(){},remove(){}}};
 const attrs=new Map(),button={innerHTML:'',closest:()=>row,setAttribute:(k,v)=>attrs.set(k,v)};
 const payload={record:{id:'rec1',teacher_id:'someone',course:'课程<script>',class_name:'样本',source:'人工录入',event_date:'2026-09-01',income:100,version:1,external_key:'PRIVATE-KEY'},history:[]};
 const opening=e.t.handlers['record-expand']('rec1',button);
 assert.equal(detail.hidden,false);assert.equal(attrs.get('aria-expanded'),'true');
 finish(payload);await opening;
 assert.match(panel.innerHTML,/课程&lt;script&gt;/);assert.doesNotMatch(panel.innerHTML,/<script>/);
 assert.doesNotMatch(customerVisible(panel.innerHTML),/PRIVATE-KEY|更正记录/);
 assert.match(panel.innerHTML,/100\.00/);
 await e.t.handlers['record-expand']('rec1',button);
 assert.equal(detail.hidden,true);assert.equal(attrs.get('aria-expanded'),'false');assert.equal(e.requests.length,1);
 const stale=e.t.handlers['record-expand']('rec1',button);panel.isConnected=false;finish(payload);await stale;
 assert.match(panel.innerHTML,/正在读取/,'detached panel must not receive the response');
});

test('inline record failure is visible and remains collapsible for retry',async()=>{
 const e=engine(()=>{throw Error('读取失败')});
 const panel={isConnected:true,innerHTML:''},detail={hidden:true,querySelector:()=>panel};
 const button={innerHTML:'',closest:()=>({nextElementSibling:detail,classList:{add(){},remove(){}}}),setAttribute(){}};
 await assert.rejects(e.t.handlers['record-expand']('rec1',button),/网络连接中断/);
 assert.match(panel.innerHTML,/role="alert"/);
 await e.t.handlers['record-expand']('rec1',button);assert.equal(detail.hidden,true);
});

// ---- Procurement batch 2: 4.9 / 5.2 / 6.3 / 7.3-7.6 / 10.1 / 10.7 / 10.9 / 11.3 ----
test('dashboard chart helpers: metric ranking keeps missing values last, dual trend and bars are escaped',()=>{
 assert.deepEqual(rankRows([{name:'甲',assessment_average:null},{name:'乙',assessment_average:'80.5'},{name:'丙',assessment_average:'90'}],'assessment_average').map(x=>x.name),['丙','乙','甲']);
 assert.equal(percentChange('12.5'),'+12.50%');assert.equal(percentChange(null),'—');assert.equal(percentChange('-3'),'-3.00%');
 const dual=incomeParticipantsChart([{month:'2026-08',income:'100',participants:5},{month:'2026-09',income:'-20',participants:0}]);
 assert.match(dual,/课程人次（右轴）/);assert.match(dual,/participants-bar/);assert.match(dual,/trend-line/);assert.doesNotMatch(dual,/NaN|Infinity/);
 assert.doesNotMatch(incomeParticipantsChart([{month:'2026-08',income:'100'}]),/participants-bar/);
 assert.match(incomeParticipantsChart([{month:'m',income:null,participants:1}]),/数据格式异常/);
 const bars=barChart([{name:'<b>学院</b>',value:3},{name:'空',value:null}],{label:'参与教师',unit:'人'});assert.match(bars,/&lt;b&gt;/);assert.doesNotMatch(bars,/<b>|NaN/);
 const sync=syncStatusChart([{name:'湘培直通车',latest_task:{success_count:2,failed_count:1,pending_confirmation_count:0}},{name:'中台',latest_task:null}]);assert.match(sync,/bar-fail/);assert.match(sync,/尚无任务/);
});
function cockpitResponder(url){
 if(url.startsWith('/api/statistics/comparison'))return {available:true,windows:{current:{start:'2026-01-01',end:'2026-12-31',days:365},previous:{start:'2025-01-01',end:'2025-12-31',days:365},year_ago:{start:'2025-01-01',end:'2025-12-31'}},current:{income:'300',participants:10,teachers:2,records:2,hours:'20',projects:2},previous:{income:'100',participants:10,teachers:1,records:1,hours:'10',projects:1},year_ago:{income:'0',participants:0,teachers:0,records:0,hours:'0',projects:0},mom:{income:'200.00',participants:'0.00',teachers:'100.00',records:'100.00',hours:'100.00',projects:'100.00'},yoy:{income:null,participants:null,teachers:null,records:null,hours:null,projects:null},note:'同源'};
 if(url.startsWith('/api/statistics'))return {income:'300',participants:10,teachers:2,projects:2,courses:1,classes:2,hours:'20',records:2,trend:[{month:'2026-09',income:'300',participants:10}],assessment_states:{TEACHER:1},
  colleges:[{id:'c1',name:'学院一',income:'100',participants:5,teachers:1,assessment_average:'92.00',assessment_count:1},{id:'c2',name:'学院二',income:'200',participants:5,teachers:1,assessment_average:null,assessment_count:0}],
  assessment_score_summary:{count:1,average:'92',minimum:'92',maximum:'92'},assessment_score_bands:[{label:'90–100分',count:1}],metric_notes:{},master_data_counts:{}};
 if(url.startsWith('/api/connections/summary'))return {items:[{code:'province',name:'湘培直通车',connection_state:'NOT_CONNECTED',latest_task:{id:'t',state:'BLOCKED',display_state:'BLOCKED',success_count:0,failed_count:2,pending_confirmation_count:0,last_activity_at:'2026-09-20T00:00:00',failure_reason:'外部接口未真实连接'}}]};
 return {items:[],total:0,page:1,size:20};
}
test('school cockpit shows comparison, multi-metric colleges, charts and sync failure reason from one stats source',async()=>{
 const e=engine(cockpitResponder);e.t.setState('cockpit',{},1,1,'p');const html=await e.t.pages.cockpit();
 for(const text of ['环比 / 同比','+200.00%','上期为0，不计算','学院多指标对比','教师参与情况','培训收入与课程人次趋势','最近失败原因','外部接口未真实连接','学院排行 · 收入','bar-fail'])assert.ok(html.includes(text),text);
 assert.ok(html.indexOf('学院二')<html.indexOf('学院一'));
 assert.ok(e.requests.some(r=>r.url.startsWith('/api/statistics/comparison?')&&r.url.includes('period_id=p')));
 await e.t.handlers['rank-metric']('assessment_average');const again=await e.t.pages.cockpit();assert.match(again,/学院排行 · 考核均分/);assert.ok(again.indexOf('学院一')<again.indexOf('学院二'));
 assert.ok(e.requests.every(r=>r.options.method==='GET'));
});
test('organization page renders assessment score summary and score bands for the scope',async()=>{
 const e=engine(url=>url.startsWith('/api/organization-workbench')?{statistics:{...cockpitResponder('/api/statistics'),ranking:[],state_filter_note:''},todos:{items:[],total:0},assessment_states:{}}:{items:[]},'college');
 e.t.setState('organization');const html=await e.t.pages.organization();assert.match(html,/本范围教师考核分值汇总与分档/);assert.match(html,/90–100分/);assert.match(html,/平均分/);
});
test('integration detail renders latest sync per data type with failure reason and province ledger explanation',async()=>{
 const e=engine(url=>{
  if(url.startsWith('/api/connections/summary'))return {items:[{code:'province',name:'湘培直通车',connection_state:'NOT_CONNECTED',latest_task:{id:'t9',data_type:'training_record',state:'BLOCKED',display_state:'BLOCKED',success_count:0,failed_count:1,pending_confirmation_count:0,last_activity_at:'2026-09-20T00:00:00',failure_reason:'外部接口未真实连接',failure_items:[{business_key:'record:<x>',state:'BLOCKED',error:'NOT_CONNECTED'}]}}]};
  if(url.includes('/ledger-sync/catalog'))return {note:'内部标准字段',items:[{data_type:'training_record',name:'培训记录',buildable:true,source_note:'有效台账',fields:[{key:'record_key',label:'台账来源编号'}]},{data_type:'certificate',name:'证书信息',buildable:false,waiting_reason:'学员培训证书由发证系统签发'}]};
  return integrationResponder(url)});
 e.t.setState('province',{tab:'overview',data_type:'training_record'});const html=await e.t.pages.province(),visible=customerVisible(html);
 assert.match(visible,/最近同步/);assert.match(visible,/外部接口未真实连接/);assert.match(visible,/record:&lt;x&gt;/);assert.match(visible,/学员培训证书由发证系统签发/);assert.match(html,/data-action="ledger-sync"/);
 assert.ok(e.requests.some(r=>r.url.startsWith('/api/connections/summary?')&&r.url.includes('data_type=training_record')));
 assert.equal((html.match(/data-action="data-type-adapter"/g)||[]).length,11);
});
test('ledger sync form previews before enqueue and submits the confirmed count',async()=>{
 const e=engine(url=>url.includes('/ledger-sync/catalog')?{items:[{data_type:'teaching',name:'教师授课',buildable:true,fields:[]}]}:url.includes('/ledger-sync/preview')?{count:3,task_count:1,sample:[{business_key:'teaching:a'}],fields:[{key:'business_key',label:'业务唯一键'}],mapping_ready:true,connection_live:false}:url.endsWith('/ledger-sync')?{records:3,tasks:[{id:'t',rows:3,state:'BLOCKED',reused:0}]}:{items:[]});
 e.t.captureForm();vm.runInContext('render=async()=>{}',e.ctx);await e.t.handlers['ledger-sync']('c-province');
 const box=e.node('#ledger-preview');box.dataset={};e.node('#f-data_type').value='teaching';e.node('#f-period_id').value='p';
 await assert.rejects(e.t.getForm().callback({data_type:'teaching',reason:'生成'}),/先预览/);
 await e.t.handlers['ledger-preview']('c-province');assert.equal(box.dataset.count,'3');assert.match(box.innerHTML,/本次将组装 3 条/);assert.match(box.innerHTML,/teaching:a/);
 await e.t.getForm().callback({data_type:'teaching',period_id:'p',reason:'生成'});
 const body=JSON.parse(e.requests.find(r=>r.url.endsWith('/ledger-sync')).options.body);assert.equal(body.expected_count,3);assert.equal(body.period_id,'p');
});
test('extended scoring rule rows build tier/deduct components and keep legacy shape unchanged',()=>{
 const e=engine(),build=vm.runInContext('ruleComponent',e.ctx);
 const row=values=>({querySelectorAll:()=>Object.entries(values).map(([r,value])=>({dataset:{r},value}))});
 assert.deepEqual(JSON.parse(JSON.stringify(build(row({key:'a',label:'A',source:'hours',factor:'2',weight:'0',target:'1',cap:'',method:''}),'points'))),{key:'a',label:'A',source:'hours',factor:'2',weight:'0',target:'1',cap:null});
 const tier=build(row({key:'a',label:'A',source:'hours',factor:'1',weight:'40',target:'1',cap:'',method:'tier',tiers:'0:10, 8：30',tier_mode:'score',floor:''}),'assessment');
 assert.equal(tier.method,'tier');assert.deepEqual(JSON.parse(JSON.stringify(tier.tiers)),[{min:'0',value:'10'},{min:'8',value:'30'}]);assert.equal(tier.weight,'40');
 const ded=build(row({key:'b',label:'B',source:'participants',weight:'0',target:'1',method:'deduct',per_unit:'2',unit:'',base:'20',floor:'5'}),'points');assert.equal(ded.per_unit,'2');assert.equal(ded.base,'20');assert.equal(ded.floor,'5');assert.equal('unit' in ded,false);
 assert.throws(()=>build(row({key:'a',label:'A',source:'hours',method:'tier',tiers:'abc'}),'points'),/分档格式/);
 const relevant=vm.runInContext('ruleFieldRelevant',e.ctx);assert.equal(relevant('tiers',false,'tier'),true);assert.equal(relevant('per_unit',false,'tier'),false);assert.equal(relevant('target',false,'tier'),false);assert.equal(relevant('weight',false,'deduct'),true);assert.equal(relevant('tiers',true,''),false);
 assert.match(vm.runInContext('methodSummary',e.ctx)({method:'tier',tier_mode:'score',tiers:[{min:'0',value:'10'}],floor:'2'}),/分档；得分 0:10；保底 2/);
});
test('assessment list offers role-mapped progress quick filters, tied rank and a ranking print entry',async()=>{
 const e=engine(url=>url.startsWith('/api/assessments')?{items:[{id:'a',teacher_id:'t',period_id:'p',score:'90',state:'DEPARTMENT',returned:false,rank:1,scope_rank:1},{id:'b',teacher_id:'u',period_id:'p',score:'90',state:'DEPARTMENT',returned:false,rank:1,scope_rank:2}],total:2,page:1,size:20,rank_note:'同分并列'}:{items:[]},'dept');
 e.t.setState('assessment',{progress:'pending'});const html=await e.t.pages.assessment();
 assert.match(html,/本级待处理/);assert.match(html,/本级 = 教研室确认环节/);assert.match(html,/名次（同分并列）/);assert.match(html,/data-action="ranking-print"/);
 assert.match(e.requests.find(r=>r.url.startsWith('/api/assessments?')).url,/progress=pending/);
 await e.t.handlers['progress-filter']('returned');assert.equal(e.t.getState().filter.progress,'returned');
 await e.t.handlers['progress-filter']('all');assert.equal(e.t.getState().filter.progress,undefined);
});
test('teacher home leads with to-dos, points progress and the yearly review, without admin statistics',async()=>{
 const e=engine(url=>{
  if(url.startsWith('/api/social/mine'))return {reminders:[{level:'warn',text:'<img src=x>教研室请你核对一条积分',action:'todo',id:'social_resource|r1'},{level:'info',text:'项目已结项，请申报积分',action:'social-claim-new',id:''}]};
  if(url.startsWith('/api/social/overview'))return {points:{year:'12.5',five_years:'85',five_year_target:340,title_points:'0.13',trial:'2'}};
  if(url.startsWith('/api/assessment-summary/latest'))return {assessment:{id:'a1',teacher_id:'u',state:'TEACHER',score:'88.5',returned:false},period:{name:'2026年度'}};
  if(url.startsWith('/api/notices'))return {items:[{id:'n1',title:'积分办法通知',created_at:'2026-09-01T00:00:00'}]};
  return homeResponse(url)},'teacher');
 e.t.setState('home');const html=await e.t.pages.home();
 for(const t of ['teacher-hero','今天有 <b>2</b> 件事要你处理','需要我处理','&lt;img src=x&gt;','todo" data-id="social_resource|r1"','去申报','12.50','近五年累计 <b>85.00</b> / 340 分','另有 2.00 分还在审批中','2026年度 · 我的年度考核','88.50','轮到你确认了','查看并确认','积分办法通知'])assert.ok(html.includes(t),t);
 assert.ok(html.indexOf('需要我处理')<html.indexOf('我的社会培训积分'));
 assert.doesNotMatch(html,/<img src=x>|workbench-statistics|学校接口状态|NaN/);
 assert.equal(e.requests.some(x=>x.url.startsWith('/api/statistics')),false);
 assert.ok(e.requests.every(x=>x.options.method==='GET'));
});
test('teacher home with nothing to do says so and shows an archived review as done',async()=>{
 const e=engine(url=>{
  if(url.startsWith('/api/social/mine'))return {reminders:[]};
  if(url.startsWith('/api/assessment-summary/latest'))return {assessment:{id:'a1',teacher_id:'u',state:'ARCHIVED',score:'90',returned:false},period:{name:'2025年度'}};
  return homeResponse(url)},'teacher');
 e.t.setState('home');const html=await e.t.pages.home();
 for(const t of ['今天没有要你处理的事','都处理完了','已归档，结果已正式生效','查看明细'])assert.ok(html.includes(t),t);
 assert.doesNotMatch(html,/查看并确认|NaN/);
});
test('administrator task tab also shows the latest sync failure reason and the ledger entry',async()=>{
 const e=engine(url=>url.startsWith('/api/connections/summary')?{items:[{code:'province',name:'湘培直通车',connection_state:'NOT_CONNECTED',latest_task:{id:'t1',data_type:'teaching',state:'FAILED',display_state:'FAILED',success_count:1,failed_count:1,pending_confirmation_count:0,last_activity_at:'2026-09-20T00:00:00',failure_reason:'存在失败或缺失同步项',failure_items:[]}}]}:integrationResponder(url));
 e.t.setState('province',{tab:'tasks',data_type:'teaching'});const html=await e.t.pages.province();
 assert.match(html,/最近同步/);assert.match(html,/存在失败或缺失同步项/);assert.match(html,/data-action="ledger-sync"/);assert.equal((html.match(/id="integration-filters"/g)||[]).length,1);
});


test('compact record editor retains required fields, optional evidence and zero values on correction',async()=>{
 const e=engine(async url=>url==='/api/records/r1'?{record:{teacher_id:'teacher',external_key:'key',source:'学校数据中台',hours:0,participants:0,income:0,version:7}}:{items:[],total:0});
 e.t.captureForm();vm.runInContext("businessConfig.record_sources=['经核对人工录入'];saved=async()=>{}",e.ctx);
 await e.t.handlers['record-form']('r1');const form=e.t.getForm();
 assert.equal(form.options.compact,true);
 for(const name of ['teacher_id','external_key','event_date','source','project_code','project','course_code','course','class_code','class_name','hours','participants','income','reason','basis'])assert.match(form.body,new RegExp('name="'+name+'"'));
 assert.match(form.body,/name="external_key" required readonly/);
 const origin=form.body.match(/<select[^>]*name="source"[^>]*>([\s\S]*?)<\/select>/)[1];assert.equal((origin.match(/<option /g)||[]).length,1);assert.match(origin,/<option value="学校数据中台" selected>学校数据中台<\/option>/);
 assert.doesNotMatch(form.body.match(/<textarea[^>]*name="basis"[^>]*>/)[0],/required/);
 for(const name of ['hours','participants','income'])assert.match(form.body,new RegExp('name="'+name+'"[^>]*value="0"'));
 await form.callback({teacher_id:'teacher',teacher_id_search:'T001',hours:0,participants:0,income:0,reason:'合成验证'});
 const req=e.requests.find(x=>x.options.method==='PUT');const body=JSON.parse(req.options.body);
 assert.equal(body.expected_version,7);assert.equal(body.hours,0);assert.equal(body.income,0);assert.equal(body.teacher_id_search,undefined);
});

test('header and footer save share a pending guard and recover after a rejected save',async()=>{
 const e=engine();let submit,resolve,calls=0;const buttons=[{isConnected:true},{isConnected:true}];
 e.node('#edit-form').addEventListener=(type,fn)=>{if(type==='submit')submit=fn};
 e.ctx.document.querySelectorAll=selector=>selector==='button[form=edit-form]'?buttons:[];
 vm.runInContext('formValues=()=>({})',e.ctx);
 const open=vm.runInContext('formModal',e.ctx);
 open('合成表单','',()=>{calls++;return new Promise(r=>{resolve=r})},{compact:true});
 const first=submit({preventDefault(){}});assert.ok(buttons.every(x=>x.disabled));
 await submit({preventDefault(){}});assert.equal(calls,1);
 resolve();await first;assert.ok(buttons.every(x=>!x.disabled));
 open('合成错误','',async()=>{throw Error('合成保存失败')});
 await submit({preventDefault(){}});assert.match(e.node('#form-error').innerHTML,/合成保存失败/);assert.ok(buttons.every(x=>!x.disabled));
});


test('course navigation consolidates resources without removing course or base entry',()=>{
 const e=engine();const menus=vm.runInContext('navItems()',e.ctx).flatMap(group=>group[1]).map(item=>item[0]);
 assert.ok(menus.includes('courses'));assert.ok(menus.includes('bases'));assert.ok(!menus.includes('resources'));
});

test('simplified sync overview shows three connectors, four hub tables and hides implementation tools behind a link',async()=>{
 const e=engine(integrationResponder);e.t.setState('sync');const html=await e.t.pages.sync();
 for(const title of ['学校统一认证','学校数据中台','湘培直通车','立即同步','定时计划','高级设置'])assert.ok(html.includes(title));
 assert.match(html,/data-action="nav" data-id="implementation"/);
 assert.doesNotMatch(html,/下载学校资料采集表|旧版沟通清单/);
});

test('teacher home does not claim there is nothing to do when to-dos fail to load, and explains a returned review',async()=>{
 const e=engine(url=>{
  if(url.startsWith('/api/social/mine'))throw new Error('offline');
  if(url.startsWith('/api/assessment-summary/latest'))return {assessment:{id:'a1',teacher_id:'u',state:'TEACHER',score:'70',returned:true},period:{name:'2026年度'}};
  return homeResponse(url)},'teacher');
 e.t.setState('home');const html=await e.t.pages.home();
 for(const t of ['待办暂时没有加载出来','考核被退回，请先在详情里看退回原因','查看并确认'])assert.ok(html.includes(t),t);
 assert.doesNotMatch(html,/今天没有要你处理的事|都处理完了|NaN/);
});

test('编辑历史资质保留当前类别，不静默改成首个新类别',async()=>{
 const e=engine(async url=>url.endsWith('/qualification-categories')?{categories:['职业资格','教学资质']}:{qualification:{id:'q',teacher_id:'u',category:'双师型中级',name:'合成资质',version:1}},'teacher');
 e.t.captureForm();await vm.runInContext('qualificationForm',e.ctx)('q');
 const form=e.t.getForm();assert.match(form.body,/<option value="双师型中级" selected/);assert.equal(typeof form.options.returnTo,'function');
 await form.options.returnTo();assert.ok(e.requests.filter(r=>r.url.endsWith('/qualifications/q')).length===2);
});

test('深层表单返回详情只读重开，不提交填写内容',async()=>{
 const e=engine();let returned=0,saved=0,listener;
 e.node('#modal-root .modal-foot button[data-action=close]').addEventListener=(type,fn)=>listener=fn;
 vm.runInContext('formModal',e.ctx)('编辑资料','',()=>saved++,{returnTo:async()=>returned++});
 const events=[];await listener({preventDefault(){events.push('prevent')},stopImmediatePropagation(){events.push('stop')}});
 assert.equal(returned,1);assert.equal(saved,0);assert.deepEqual(events,['prevent','stop']);
 assert.equal(e.node('#modal-root .modal-foot button[data-action=close]').textContent,'返回详情');
});

test('不选择积分项目时按全部计算，不发送无效空数组',async()=>{
 const e=engine(url=>url.includes('/calculation-items')?{items:[{key:'hours',label:'授课贡献'}]}:url==='/api/rules'?{items:[{name:'学校测试规则',kind:'points',period_id:'p',state:'ACTIVE',version_no:2}]}:{summary:{teachers:1,entry_count:1}});
 e.t.setData([{id:'p',name:'隔离周期',state:'OPEN'}],[{id:'t',name:'教师',active:true}]);e.t.captureForm();
 e.node('#calculation-items').dataset={};e.node('#calculation-impact').dataset={};e.node('#f-period_id').value='p';
 vm.runInContext('render=async()=>{}',e.ctx);
 await e.t.handlers.calculate('points');assert.match(e.node('#calculation-items').innerHTML,/授课贡献/);
 const f={querySelectorAll:s=>s==='input[name=person]:checked'?[{value:'t'}]:s==='input[name=calculation_item]:checked'?[]:[],querySelector:s=>e.node(s)};
 await e.t.getForm().callback({period_id:'p',reason:'隔离验收',basis:''},f);
 const body=JSON.parse(e.requests.find(r=>r.url==='/api/points/calculate').options.body);
 assert.deepEqual(body.teacher_ids,['t']);assert.equal(Object.hasOwn(body,'item_keys'),false);
});


test('退回意见直接可见且转义，其他状态不展示旧退回意见',()=>{const e=engine(),notice=vm.runInContext('returnedNotice',e.ctx);const events=[{action:'资质退回补充',reason:'补充<材料>'},{action:'重新提交',reason:'已补充'}];assert.match(notice('RETURNED',events),/补充&lt;材料&gt;/);assert.equal(notice('APPROVED',events),'');});


test('组织考核隐藏本人不得执行的复核审核入口并翻译数据来源',async()=>{
 for(const [state,generated,reviewed,blocked] of [['GENERATED','u',null,'组织复核'],['REVIEWED','other','u','学校审核']]){
  const d={assessment:{id:'a',state,target_kind:'school',target_id:'school',generated_by:generated,reviewed_by:reviewed,score:10,source_snapshot:{}},target:{name:'隔离学校'},period:{name:'周期'},rule:{name:'规则',version_no:1},events:[],evidence:[{metric_name:'收入',data_source:'income',raw_value:10,target_value:100,weight:100,formula:'10',calculated_score:10}]};
  const e=engine(async()=>d);e.t.setUser({user:{id:'u',org_id:'school'},role:{kind:'school'},permissions:['assessment.read','assessment.review']});vm.runInContext('appendBoundEvidence=async()=>{}',e.ctx);
  await vm.runInContext('showOrgAssessment',e.ctx)('a');const html=e.node('#modal-root').innerHTML;
  assert.doesNotMatch(html,new RegExp('>'+blocked+'<'));assert.match(html,/其他/);assert.match(html,/归属培训收入/);assert.doesNotMatch(html,/>income</);
 }
});

test('教师跨检索保留已选，去重，并丢弃已停用人员',async()=>{
 const e=engine(()=>({items:[{id:'second',name:'第二人',staff_no:'2',active:true},{id:'inactive',name:'停用人',active:false}]}));
 e.t.setData([],[{id:'first',name:'第一人',staff_no:'1',active:true},{id:'inactive',name:'停用人',active:true}]);
 e.ctx.Event=class{constructor(type){this.type=type}};
 const box=e.node('#calc-people');box.querySelectorAll=()=>[{value:'first'},{value:'inactive'}];let events=0;box.dispatchEvent=()=>events++;
 e.node('#calc-search').value='第二';await e.t.handlers['calc-search']();
 assert.match(box.innerHTML,/value="first" checked/);assert.match(box.innerHTML,/value="second"/);assert.doesNotMatch(box.innerHTML,/inactive/);assert.equal(events,1);
 const inputs=[{checked:false},{checked:false}];box.querySelectorAll=()=>inputs;e.t.handlers['calc-all']();assert.ok(inputs.every(x=>x.checked));assert.equal(events,2);
});

test('选人检索返回时不覆盖已经关闭或新开的表单',async()=>{
 let done;const e=engine(()=>new Promise(resolve=>done=resolve));e.ctx.Event=class{};
 const old=e.node('#calc-people');let current=old;e.ctx.document.querySelector=s=>s==='#calc-people'?current:e.node(s);
 const task=e.t.handlers['calc-search']();current={innerHTML:'新表单'};done({items:[]});await task;assert.equal(current.innerHTML,'新表单');
});

test('参训专用表单不含授课收入和人次，并提交参训接口',async()=>{
 const e=engine(()=>({}));e.t.captureForm();vm.runInContext('bindRecordReferences=()=>{};saved=async()=>{}',e.ctx);
 await e.t.handlers['participation-form']('');const f=e.t.getForm();assert.equal(f.title,'新增教师参训记录');assert.match(f.body,/参训学时/);assert.doesNotMatch(f.body,/name="income"|name="participants"|name="class_code"/);
 await f.callback({teacher_id:'teacher',teacher_id_search:'教师',hours:'8',source:'经核对人工录入'});
 const request=e.requests.find(x=>x.options.method==='POST');assert.equal(request.url,'/api/participations');assert.equal(JSON.parse(request.options.body).hours,'8');assert.equal(JSON.parse(request.options.body).teacher_id_search,undefined);
});

test('参训详情按写权限展示更正且更正保留版本与原来源',async()=>{
 const x={id:'p',teacher_id:'teacher',project:'<参训>',course:'课程',source:'Excel导入',external_key:'OLD',event_date:'2026-10-11',hours:8,version:3};
 const e=engine(()=>x);e.t.setData([],[{id:'teacher',name:'本人'}]);vm.runInContext('modal=(title,body,foot)=>{globalThis.partModal={title,body,foot}};bindRecordReferences=()=>{};saved=async()=>{}',e.ctx);
 e.t.setUser({user:{id:'teacher'},role:{kind:'teacher'},permissions:['records.read']});await e.t.handlers.participation('p');assert.doesNotMatch(e.ctx.partModal.foot,/更正参训记录/);assert.match(e.ctx.partModal.body,/&lt;参训&gt;/);
 e.t.setUser({user:{id:'school'},role:{kind:'school'},permissions:['records.read','records.write']});await e.t.handlers.participation('p');assert.match(e.ctx.partModal.foot,/更正参训记录/);
 e.t.captureForm();await e.t.handlers['participation-form']('p');const f=e.t.getForm();assert.match(f.body,/value="Excel导入"/);await f.callback({...x,hours:'9'});const req=e.requests.find(x=>x.options.method==='PUT');assert.equal(req.url,'/api/participations/p');assert.equal(JSON.parse(req.options.body).expected_version,3);
});

test('积分解锁明确要求依据，普通确认不额外要求',()=>{
 const e=engine();e.t.captureForm();const action=vm.runInContext('actionForm',e.ctx);
 action('留痕解锁积分','/point-balances/b/actions',{version:1},'reopen');assert.match(e.t.getForm().body,/name="basis"[^>]*required/);
 action('确认本人积分','/point-balances/b/actions',{version:1},'confirm');assert.doesNotMatch(e.t.getForm().body,/name="basis"[^>]*required/);
});
test('组织规则新建目标值必须由学校填写，不预填1',()=>{
 assert.equal(typeof engine().t.handlers['social-policy-calendar'],'function');
 const e=engine(),html=vm.runInContext('orgRuleRow()',e.ctx);
 assert.match(html,/data-or="target"[^>]*value=""[^>]*required/);
 assert.match(html,/请按学校考核细则填写/);
});
test('组织规则新建和复制均在提交前拒绝空目标，旧目标不被覆盖',async()=>{
 const original={id:'r',name:'合成组织规则',period_id:'p',target_kind:'dept',version:2,config:{components:[{key:'income',label:'收入',source:'income',weight:100,target:1}]}};
 for(const handler of ['org-rule-form','org-rule-copy']){
  const e=engine(()=>({items:[original]}));e.t.setData([{id:'p',name:'周期',state:'OPEN'}]);e.t.captureForm();
  await e.t.handlers[handler](handler==='org-rule-copy'?'r':undefined);
  const values={key:'income',label:'收入',source:'income',weight:'100',target:'',method:''};
  e.node('#org-rule-rows').querySelectorAll=()=>[{querySelectorAll:()=>Object.entries(values).map(([or,value])=>({dataset:{or},value}))}];
  await assert.rejects(e.t.getForm().callback({name:'合成草稿',period_id:'p'}),/目标值必填，请按学校考核细则填写/);
  assert.equal(e.requests.filter(r=>r.options.method==='POST').length,0);assert.equal(original.config.components[0].target,1);
 }
});
test('收入目标1的来源待核对提示在规则详情和启用表单醒目显示',async()=>{
 const warning='归属培训收入目标值为1，来源未记录，请按学校考核细则核对。';
 const rule={id:'r',name:'合成规则',target_kind:'dept',period_id:'p',state:'DRAFT',version:1,version_no:1,fingerprint:'fixture',warnings:[warning],config:{components:[{label:'收入',source:'income',weight:100,target:1}]}};
 const e=engine(()=>({items:[rule]}));await e.t.handlers['org-rule']('r');
 assert.match(e.node('#modal-root').innerHTML,/info-banner warn/);assert.match(e.node('#modal-root').innerHTML,/来源未记录/);
 e.t.captureForm();await e.t.handlers['org-rule-action']('activate|r');
 assert.match(e.t.getForm().body,/info-banner warn/);assert.match(e.t.getForm().body,/请按学校考核细则核对/);assert.doesNotMatch(e.t.getForm().body,/系统默认/);
});
test('组织试算和正式计算保留结果并展示后端目标核对提示',async()=>{
 const warning='归属培训收入目标值为1，来源未记录，请按学校考核细则核对。';
 const rule={id:'r',name:'合成规则',target_kind:'dept',period_id:'p',state:'DRAFT',version:1,version_no:1,warnings:[warning],config:{components:[]}};
 const e=engine(url=>url==='/api/organization-assessment-rules'?{items:[rule]}:{items:[{target_id:'d',total:100,detail:[]}],count:1,warnings:[warning]});
 e.t.setData([{id:'p',name:'周期',state:'OPEN'}],[],[{id:'d',name:'合成教研室',kind:'dept',active:true}]);e.t.captureForm();
 const selected={querySelectorAll:()=>[{value:'d'}]};
 await e.t.handlers['org-rule-trial']('r');await e.t.getForm().callback({},selected);
 assert.match(e.node('#modal-root').innerHTML,/组织规则试算结果/);assert.match(e.node('#modal-root').innerHTML,/info-banner warn/);assert.match(e.node('#modal-root').innerHTML,/来源未记录/);
 vm.runInContext('render=async()=>{}',e.ctx);await vm.runInContext("calculateOrgAssessment('dept')",e.ctx);
 await e.t.getForm().callback({period_id:'p',reason:'合成计算',basis:'合成细则'},selected);
 assert.match(e.node('#modal-root').innerHTML,/组织考核已生成，请核对目标/);assert.match(e.node('#modal-root').innerHTML,/info-banner warn/);assert.match(e.node('#modal-root').innerHTML,/来源未记录/);
 assert.equal(e.requests.filter(r=>r.url==='/api/organization-assessments/calculate'&&r.options.method==='POST').length,1);
});
test('有错误行的导入预览显示校验未通过',async()=>{
 const e=engine(async()=>({items:[{id:'bad-import',filename:'测试.xlsx',kind:'records',state:'PREVIEW',total:1,errors:1}],total:1,page:1,size:20}));
 const html=await e.t.pages.imports();
 assert.match(html,/导入有误/);assert.match(html,/查看 \/ 放弃/);assert.doesNotMatch(html,/>待确认导入</);
});
test('导入错误批次可下载和放弃，已放弃批次保留说明且不再办理',async()=>{
 for(const state of ['PREVIEW','INVALID','VOID']){
  const job={id:'bad',filename:'合成.xlsx',kind:'records',state,total:1,errors:1,sha256:'a'.repeat(64),version:3};
  const e=engine(url=>url.startsWith('/api/imports/bad?')?{job,rows:{items:[],page:1,size:30,total:1}}:{items:[job],total:1,page:1,size:20});
  const list=await e.t.pages.imports();await e.t.handlers.import('bad');const html=e.node('#modal-root').innerHTML;
  assert.match(html,/下载错误明细/);assert.doesNotMatch(html,/data-action="import-confirm"/);
  if(state==='VOID'){
   assert.match(list,/已放弃/);assert.match(html,/本批已放弃，未写入业务数据/);assert.match(html,/审计记录保留/);assert.doesNotMatch(html,/data-action="import-discard"|可放弃本批/);
  }else{
   assert.match(list,/导入有误/);assert.match(html,/data-action="import-discard"/);assert.match(html,/整批未入库/);
  }
 }
});
test('放弃导入沿用版本和理由提交，成功后重新读取批次',async()=>{
 let state='INVALID';const job=()=>({id:'bad',filename:'合成.xlsx',kind:'records',state,total:1,errors:1,sha256:'b'.repeat(64),version:7});
 const e=engine((url,options)=>{if(url==='/api/imports/bad/discard'&&options.method==='POST'){state='VOID';return {...job(),version:8}}return {job:job(),rows:{items:[],page:2,size:30,total:31}}});
 vm.runInContext('render=async()=>{}',e.ctx);await vm.runInContext("showImport('bad',2)",e.ctx);e.t.captureForm();await e.t.handlers['import-discard']('bad');
 const form=e.t.getForm();assert.match(form.body,/name="reason"[^>]*required/);await form.options.returnTo();assert.ok(e.requests.some(r=>r.url.includes('/imports/bad?page=2')));
 await form.callback({reason:'原表有误，放弃本批',basis:'合成纠正依据'});
 const request=e.requests.find(r=>r.url==='/api/imports/bad/discard');assert.equal(request.options.method,'POST');assert.deepEqual(JSON.parse(request.options.body),{reason:'原表有误，放弃本批',basis:'合成纠正依据',expected_version:7});
 assert.match(e.node('#modal-root').innerHTML,/已放弃/);assert.doesNotMatch(e.node('#modal-root').innerHTML,/data-action="import-discard"/);
});
test('无错待确认导入继续显示确认入库',async()=>{
 const e=engine(()=>({job:{id:'ok',filename:'合成.xlsx',state:'PREVIEW',total:1,errors:0,sha256:'c'.repeat(64),version:1},rows:{items:[],page:1,size:30,total:1}}));
 await e.t.handlers.import('ok');const html=e.node('#modal-root').innerHTML;
 assert.match(html,/data-action="import-confirm"/);assert.doesNotMatch(html,/data-action="import-discard"|导入有误/);
});
test('过期资质详情提示有效期并解释记录版本',async()=>{
 const e=engine(async()=>({qualification:{id:'q',teacher_id:'u',name:'隔离证书',category:'职业资格',version:3,state:'DRAFT',certificate_no:'TEST',issuer:'测试机构',obtained:'1999-01-01',expires:'2000-01-01'},attachments:[],events:[],revisions:[]}));
 await vm.runInContext("showQualification('q')",e.ctx);
 const html=e.node('#modal-root').innerHTML;
 assert.match(html,/已超过有效期/);assert.match(html,/记录版本 3（含上传与办理）/);
});

test('秘书双月报送待办有独立分类、计数与办理入口',async()=>{
 const e=engine(async()=>({items:[{type:'social_report',id:'bimonth',title:'本双月积分汇总与报送',state:'待汇总',target_id:'school'}],counts:{social_report:1,social_resource:0},total:1,page:1,size:20}));
 e.t.setUser({user:{id:'secretary'},role:{kind:'school'},permissions:['portal.read','points.read']});
 const html=await e.t.pages.todos();
 assert.match(html,/<option value="social_report"[^>]*>双月积分汇总与报送（1）<\/option>/);
 assert.match(html,/data-id="social_report\|bimonth"/);
});

test('教师待办分类同时覆盖积分核对与本人更正，不误称全部为教研室核对',async()=>{
 const e=engine(async()=>({items:[{type:'social_resource',id:'fix1',title:'补充积分更正依据',state:'退回补正',teacher_id:'u'}],counts:{social_resource:1},total:1,page:1,size:20}),'teacher');
 const html=await e.t.pages.todos();
 assert.match(html,/积分核对与更正/);assert.match(html,/补充积分更正依据/);assert.doesNotMatch(html,/教研室请我核对积分/);
});
test('待办批量办理只给本人可办、同环节事项勾选框，结果分开列出成功与未办理',async()=>{
 const items=[{type:'assessment',id:'a1',title:'本级考核确认',state:'COLLEGE',teacher_id:'t1'},{type:'assessment',id:'a2',title:'本人考核确认',state:'TEACHER',teacher_id:'u'},{type:'social_claim',id:'c1',title:'社会培训积分认定',state:'待教学秘书归档',teacher_id:'t2'},{type:'qualification',id:'q1',title:'资质审核',state:'SUBMITTED',teacher_id:'t3'}];
 const e=engine(async()=>({items,total:4,page:1,size:20,counts:{}}),'college');e.t.setState('todos',{stage:'archive'},1);
 const html=await e.t.pages.todos();
 assert.equal(new URL('https://test.invalid'+e.requests[0].url).searchParams.get('stage'),'archive');
 assert.match(html,/value="assessment\|a1"/);assert.match(html,/value="social_claim\|c1"/);
 assert.doesNotMatch(html,/value="assessment\|a2"/);assert.doesNotMatch(html,/value="qualification\|q1"/);
 assert.match(html,/data-action="todo-batch" data-id="confirm"/);assert.match(html,/data-action="todo-batch" data-id="archive"/);assert.doesNotMatch(html,/data-id="approve"/);
 assert.ok(html.indexOf('data-id="confirm"')<html.indexOf('data-id="archive"'),'先确认、归档最后');
 assert.match(html,/返回全部待办/);assert.match(html,/name="stage" value="archive"/);
 vm.runInContext('showBatchResult',e.ctx)('批量确认',{ok:[{item:items[0]}],failed:[{item:items[2],error:'<b>审批依据已变化</b>'}]});
 const modal=e.node('#modal-root').innerHTML;
 assert.match(modal,/成功 1 条；未办理 1 条/);assert.doesNotMatch(modal,/均已办理/);assert.match(modal,/&lt;b&gt;审批依据已变化/);assert.match(modal,/data-id="social_claim\|c1"/);
});
