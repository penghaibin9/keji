// Real renderer/control tests with explicit synthetic API fixtures, not browser E2E.
import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';
import {connectorInfo,connectorCards,connectorStatus,incomeChart,guideCards,scopedDateFilters} from '../../frontend/portal-ui.js';
import * as scope from '../../frontend/scope.js';
import {icons} from '../../frontend/icons.js';
const source=fs.readFileSync(new URL('../../frontend/app.js',import.meta.url),'utf8');
const customerVisible=html=>String(html??'').replace(/<details\b[\s\S]*?<\/details>/g,'');
const implementationDetailTags=html=>[...String(html??'').matchAll(/<details\b[^>]*class="[^"]*implementation-details[^"]*"[^>]*>/g)].map(x=>x[0]);
function engine(responder=async()=>({items:[],total:0,page:1,size:20}), role='school'){
 const requests=[], nodes=new Map();
 function node(id){if(!nodes.has(id)){const classes=new Set(),attrs=new Map();nodes.set(id,{innerHTML:'',textContent:'',value:'',classList:{add(v){classes.add(v)},remove(v){classes.delete(v)},contains(v){return classes.has(v)},toggle(v,force){const on=force??!classes.has(v);if(on)classes.add(v);else classes.delete(v);return on}},setAttribute(k,v){attrs.set(k,v)},getAttribute(k){return attrs.get(k)??null},removeAttribute(k){attrs.delete(k)},focus(){},addEventListener(){},append(){},querySelector(){return node(id+'-child')},querySelectorAll(){return []}})}return nodes.get(id)}
 const ctx=vm.createContext({console,URLSearchParams,URL,Blob,FormData,Number,String,Object,Array,Date,Math,Set,Map,JSON,RegExp,Error,Promise,crypto:globalThis.crypto,setTimeout:()=>0,clearTimeout(){},
  ...scope,connectorInfo,connectorCards,connectorStatus,incomeChart,guideCards,scopedDateFilters,icons,
  document:{querySelector:node,querySelectorAll:()=>[],addEventListener(){},createElement:()=>node('created'),body:node('body')},window:{addEventListener(){}},location:{hash:'',pathname:'/',search:''},history:{replaceState(){}},
  fetch:async(url,options)=>{requests.push({url,options});const answer=await responder(url,options);return {ok:true,status:200,json:async()=>answer}},
 });
 let program=source.replace(/^import .*?;\n/gm,'').replace(/\(async\(\)=>\{try\{await boot\(\)\}[\s\S]*$/,'');
 program+=`\nglobalThis.T={pages,handlers,api,nav,render,pageAllowed,sidebarNavigation,syncMenuAccessibility,connectionOverview,integrationPage,sourceAvailability,bindPortalControls,pager,query,connectionForm,mappingEditor,showInbound,ts,evidenceHtml,pointLabel,calculationSummary,
 setUser(user){me=user;csrf=user.csrf||'test-csrf'},setState(p,f={},n=1,pa=1,per=''){page=p;filter=f;tablePage=n;participationPage=pa;periodId=per},setData(p,t=[],o=[]){periods=p;teachers=t;orgs=o},getState(){return {page,filter,tablePage,participationPage,periodId}},getView(){return view},captureForm(){formModal=(title,body,callback,options)=>{globalThis.F={title,body,callback,options}}},getForm(){return globalThis.F}};`;
 vm.runInContext(program,ctx);
 ctx.T.setUser({user:{id:'u',name:'合成用户',is_admin:role==='school'},role:{kind:role,name:role},permissions:['portal.read','records.read','qualification.read','points.read','assessment.read','sync.manage','organization.read','notice.read','import','export','settings.manage','users.manage','audit.read','operations.read','rules.manage','dispute.write'],csrf:'test-csrf'});
 return {t:ctx.T,ctx,requests,node};
}
const types=[{data_type:'teacher_hr',name:'教师人事信息',local_status:'AVAILABLE',mapping_count:0},{data_type:'training_income',name:'培训收入',local_status:'AVAILABLE',mapping_count:0}];
test('permission sections translate levels without changing role or user contracts',async()=>{
 const e=engine(url=>url.startsWith('/api/users')?{items:[],total:0,page:1,size:20}:url==='/api/roles'?{items:[{id:'r',name:'学院角色',kind:'college',active:true,permissions:['records.read']}]}:{items:[{id:'s',name:'学校',kind:'school',active:true,code:'S'}]});e.t.setState('permissions');
 let html=await e.t.pages.permissions();assert.match(html,/账号管理/);assert.match(html,/仅本人业务/);assert.doesNotMatch(html,/角色与批量授权/);
 vm.runInContext("permissionsSection='roles'",e.ctx);html=await e.t.pages.permissions();assert.match(html,/二级学院/);assert.match(html,/所属学院及下属教研室/);assert.doesNotMatch(html,/>college</);assert.ok(e.requests.every(r=>r.options.method==='GET'));
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
 const e=engine();const render=vm.runInContext('table',e.ctx);assert.match(render(['日期','教师','项目','状态','操作'],[['1','2','3','4','5']]),/responsive-table/);assert.doesNotMatch(render(['环节','教师数量'],[['教师确认','2']]),/responsive-table/);assert.match(render(['<name>'],[['ok']]),/data-label="&lt;name&gt;"/);
});
test('table empty states distinguish no records from no filtered results',()=>{
 const e=engine();e.t.setState('qualifications');assert.match(vm.runInContext('table([],[])',e.ctx),/当前尚无业务记录/);e.t.setState('qualifications',{q:'不存在'});assert.match(vm.runInContext('table([],[])',e.ctx),/没有符合条件的记录/);
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
 const e=engine(url=>url.includes('/catalog')?{items:[{connection:{...connection,id:'sso',code:'sso',name:'统一认证'},data_types:[{data_type:'identity',name:'身份',local_status:'WAITING_PROTOCOL'}]}]}:{items:[]});e.t.setState('sso');const html=await e.t.pages.sso();
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
 const e=engine(integrationResponder);e.t.setState('hub');const html=await e.t.pages.hub();
 for(const name of middleTypes.map(x=>x.name))assert.match(html,new RegExp(name));
 assert.equal((html.match(/data-action="data-type-adapter"/g)||[]).length,5);assert.equal(typeof e.t.handlers['data-type-adapter'],'function');assert.equal(typeof e.t.handlers['inbound-confirm'],'function');
});
test('province connector exposes all eleven Chinese configuration entries',async()=>{
 const e=engine(integrationResponder);e.t.setState('province');const html=await e.t.pages.province();
 for(const name of provinceTypes.map(x=>x.name))assert.match(html,new RegExp(name));
 assert.equal((html.match(/data-action="data-type-adapter"/g)||[]).length,11);assert.equal(typeof e.t.handlers['data-type-adapter'],'function');
});
test('each of the three connectors renders its six-item school material checklist truthfully',async()=>{
 const cases=[
  ['sso',['正式认证规范','登录与退出地址','回调登记规则','身份与组织字段字典','测试账号与异常规则','凭据交付方式']],
  ['hub',['五类接口清单','正式字段字典','分页与增量规则','成功与错误规则','脱敏正常与异常样本','凭据交付方式']],
  ['province',['省平台正式规范','机构与应用登记','签名与防重复规则','十一类数据字段字典','回执与错误码','脱敏正常与异常样本']],
 ];
 for(const[route,names]of cases){const e=engine(integrationResponder);e.t.setState(route);const html=await e.t.pages[route](),visible=customerVisible(html);assert.match(visible,/学校资料清单/);assert.match(visible,/已登记 0 \/ 6/);assert.equal((html.match(/class="material-row"/g)||[]).length,6);assert.equal((html.match(/data-material-state="pending"/g)||[]).length,6);for(const name of names)assert.match(visible,new RegExp(name));assert.doesNotMatch(visible,/\b(?:NOT_CONNECTED|CONNECTED|WAITING_SOURCE|WAITING_PROTOCOL|ADAPTER_NOT_INSTALLED|REAL|TEST)\b/);assert.ok(e.requests.every(x=>x.options.method==='GET'));}
});
test('one-stop integration center totals the material checklist without English implementation states',async()=>{
 const e=engine(integrationResponder);e.t.setState('sync');const html=await e.t.pages.sync(),visible=customerVisible(html);
 assert.match(visible,/资料登记进度/);assert.match(visible,/0 \/ 18/);assert.match(visible,/一站式系统协同/);assert.match(visible,/三大接口配置一览/);assert.match(visible,/对接项目[\s\S]*学校需提供[\s\S]*当前完成度[\s\S]*真实状态/);assert.equal((html.match(/data-action="connection"/g)||[]).length,3);assert.doesNotMatch(visible,/INTEGRATION CENTER|\b(?:NOT_CONNECTED|CONNECTED|WAITING_SOURCE|WAITING_PROTOCOL)\b/);
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
for(const role of ['teacher','dept','college','school'])test('task-first home preserves role entry points: '+role,async()=>{
 const e=engine(homeResponse,role);e.t.setState('home');
 const html=await e.t.pages.home();
 assert.ok(html.indexOf('workbench-pending')<html.indexOf('workbench-statistics'));
 assert.ok(html.indexOf('workbench-shortcuts')<html.indexOf('workbench-statistics'));
 assert.doesNotMatch(html,/portal-hero|NOT_CONNECTED|NaN/);
 assert.match(html,/待办理与资质提醒包含全部周期/);
 assert.equal(e.requests.some(x=>x.url.startsWith('/api/connections/summary')),role==='school');
 if(role==='teacher'){assert.match(html,/我的培训/);assert.doesNotMatch(html,/本组织工作台|学校概况|学校接口状态/);}
 if(role==='dept'||role==='college'){assert.match(html,/本组织工作台/);assert.doesNotMatch(html,/data-id="cockpit"|学校接口状态/);}
 if(role==='school'){assert.match(html,/学校接口状态/);assert.ok(html.indexOf('学校接口状态')>html.indexOf('业务概况'));}
 assert.ok(e.requests.every(x=>x.options.method==='GET'));
});
test('home task and expiry summaries escape business content and retain actual dates',async()=>{
 const e=engine(url=>url.startsWith('/api/portal/workbench')?{...homeSummary,
 tasks:{total:1,returned:1,items:[{id:'q',type:'qualification',title:'<img src=x>',owner_name:'<script>x</script>',state:'RETURNED'}]},
 reminders:{total:1,expired:1,items:[{id:'r',type:'qualification',title:'测试证书',owner_name:'本人',state:'EXPIRING',expires:'2026-09-19',days_remaining:-1}]}}:homeResponse(url),'teacher');
 const html=await e.t.pages.home();assert.match(html,/&lt;img src=x&gt;/);assert.doesNotMatch(html,/<script>|<img src=x>/);
 assert.match(html,/已过期 1 天/);assert.match(html,/有效期至 2026-09-19/);assert.match(html,/qualification\|q/);
});
test('home permissions remove unauthorized shortcuts even for named school role',async()=>{
 const e=engine(homeResponse);e.t.setUser({user:{id:'u',name:'受限管理员'},role:{kind:'school',name:'学校管理'},permissions:['portal.read']});
 const html=await e.t.pages.home();
 const shortcuts=html.slice(html.indexOf('workbench-shortcuts'),html.indexOf('workbench-reminders'));
 assert.doesNotMatch(shortcuts,/data-id="(?:records|qualifications|points|assessment|organization)"/);
});
test('home active statistics conditions are visible and never filter task summary',async()=>{
 const e=engine(homeResponse);e.t.setState('home',{project_code:'P1'},1,1,'period-1');
 const html=await e.t.pages.home();assert.match(html,/更多统计筛选 · 已启用 1 项/);
 assert.match(html,/portal-filters" open/);
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
 for(const title of ['工作空间','数据与分析','业务办理','系统管理','表格导入中心'])assert.ok(html.includes(title));
 for(const route of ['home','todos','records','qualifications','points','assessment','settings','permissions','audit','operations'])assert.ok(html.includes('data-id="'+route+'"'));
 assert.equal((html.match(/aria-expanded="true"/g)||[]).length,4);
 assert.match(html,/aria-controls="nav-group-0"/);assert.match(html,/title="工作总览" aria-label="工作总览"/);
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
