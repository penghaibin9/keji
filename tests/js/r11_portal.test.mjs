import {renderTrainingWorkspace,trainingChange} from '../../frontend/training-workspace.js';
// Real renderer/control tests with explicit synthetic API fixtures, not browser E2E.

test('组织考核导出保持当前层级周期状态和进度，与清单查询一致',async()=>{
 for(const kind of ['dept','college','school']){
  const e=engine();e.t.setState('assessment',{state:'ARCHIVED',progress:'done',org_id:'教师页遗留筛选'},1,1,'period2026');vm.runInContext(`assessmentTab='${kind}'`,e.ctx);
  await vm.runInContext("exportRows('organization_assessments')",e.ctx);
  const request=e.requests.find(x=>x.url==='/api/exports'),body=JSON.parse(request.options.body);
  assert.equal(body.kind,'organization_assessments');assert.deepEqual(body.filters,{target_kind:kind,period_id:'period2026',state:'ARCHIVED',progress:'done'});
 }
});

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

test('办理轨迹不展示文件校验值，业务原因和普通依据继续安全显示',()=>{
 const e=engine(),render=vm.runInContext('eventsHtml',e.ctx),hash='a'.repeat(64);
 for(const prefix of ['附件SHA256:','附件校验值:','附件校验值：']){
 const html=render([{action:'上传<材料>',actor_name:'<教师>',created_at:'2026-10-18T01:00:00Z',reason:'已上传<合成附件>',basis:prefix+hash}]);
 assert.doesNotMatch(html,/实施人员使用|文件校验/);assert.ok(!html.includes(hash));
 assert.doesNotMatch(customerVisible(html),/SHA256|a{64}/);assert.match(customerVisible(html),/已上传&lt;合成附件&gt;/);assert.doesNotMatch(html,/<材料>|<教师>/);
 }
 const business=render([{action:'审核',actor_name:'教师',created_at:'2026-10-18T01:00:00Z',reason:'核对完成',basis:'学院会议纪要<第3号>'}]);
 assert.match(customerVisible(business),/核对完成 · 学院会议纪要&lt;第3号&gt;/);assert.doesNotMatch(business,/implementation-details/);
});

test('考核冻结资质附件移除技术校验，保留原版本专用下载入口',()=>{
 const e=engine();e.t.setUser({user:{id:'u'},role:{kind:'school'},permissions:['file.read']});const render=vm.runInContext('frozenAssessmentFiles',e.ctx),hash='b'.repeat(64);
 const html=render({immutable:true,assessment:{archive:{source_snapshot:{qualifications:[{attachments:[{id:'file',name:'原证书<一>',sha256:hash}]}]}}}},'assessment');
 assert.match(html,/原证书&lt;一&gt;/);assert.doesNotMatch(html,/实施人员使用|文件校验|b{64}/);assert.match(html,/data-action="assessment-file" data-id="assessment\|file"/);assert.doesNotMatch(customerVisible(html),/b{16}/);assert.doesNotMatch(html,/<details[^>]* open/);
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
import * as socialTraining from '../../frontend/social-training.js';
import {icons} from '../../frontend/icons.js';
import {renderSchoolCockpit,bindSchoolCockpit} from '../../frontend/school-cockpit.js';
import * as workspace from '../../frontend/integration-workspace.js';
import * as drafts from '../../frontend/integration-drafts.js';
import {renderBusinessHistory} from '../../frontend/business-history.js';import * as ledgers from '../../frontend/social-ledgers.js';import * as schoolData from '../../frontend/school-data.js';import * as approvalFlow from '../../frontend/approval-flow.js';import * as applications from '../../frontend/applications.js';
const source=fs.readFileSync(new URL('../../frontend/app.js',import.meta.url),'utf8');
const customerVisible=html=>String(html??'').replace(/<details\b[\s\S]*?<\/details>/g,'');
const implementationDetailTags=html=>[...String(html??'').matchAll(/<details\b[^>]*class="[^"]*implementation-details[^"]*"[^>]*>/g)].map(x=>x[0]);
function engine(responder=async()=>({items:[],total:0,page:1,size:20}), role='school'){
 const requests=[], nodes=new Map();
 function node(id){if(!nodes.has(id)){const classes=new Set(),attrs=new Map();nodes.set(id,{innerHTML:'',textContent:'',value:'',classList:{add(v){classes.add(v)},remove(v){classes.delete(v)},contains(v){return classes.has(v)},toggle(v,force){const on=force??!classes.has(v);if(on)classes.add(v);else classes.delete(v);return on}},setAttribute(k,v){attrs.set(k,v)},getAttribute(k){return attrs.get(k)??null},removeAttribute(k){attrs.delete(k)},focus(){},addEventListener(){},append(){},querySelector(){return node(id+'-child')},querySelectorAll(){return []}})}return nodes.get(id)}
 const ctx=vm.createContext({renderTrainingWorkspace,trainingChange,renderSchoolCockpit,bindSchoolCockpit,console,URLSearchParams,URL,Blob,FormData,Number,String,Object,Array,Date,Math,Set,Map,JSON,RegExp,Error,Promise,crypto:globalThis.crypto,setTimeout:()=>0,clearTimeout(){},
  ...scope,...socialTraining,...workspace,...drafts,...ledgers,...schoolData,...approvalFlow,...applications,renderBusinessHistory,connectorInfo,connectorCards,connectorStatus,incomeChart,guideCards,scopedDateFilters,incomeParticipantsChart,barChart,syncStatusChart,rankRows,percentChange,RANK_METRICS,icons,
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
test('登录页默认选中第一个统一认证标签，开通后跳转原认证入口',async()=>{
 const e=engine(async()=>({available:true})),button=e.node('#sso-login'),note=e.node('#local-login-note');
 let click,target;button.disabled=true;button.addEventListener=(event,handler)=>{if(event==='click')click=handler};e.ctx.location.assign=url=>{target=url};
 vm.runInContext("loginView('<提示>')",e.ctx);await new Promise(resolve=>setImmediate(resolve));
 const html=e.node('#app').innerHTML;
 assert.ok(html.indexOf('id="login-sso-tab"')<html.indexOf('id="login-local-tab"'));
 assert.match(html,/id="sso-login" disabled/);assert.match(html,/本地账号登录/);assert.match(html,/&lt;提示&gt;/);
 assert.match(html,/autocomplete="username"/);assert.match(html,/autocomplete="current-password" type="password" required/);
 assert.match(html,/role="tablist" aria-label="登录方式"/);
 assert.equal(e.node('#login-sso-tab').getAttribute('aria-selected'),'true');assert.equal(e.node('#sso-entry').hidden,false);assert.equal(e.node('#login-form').hidden,true);
 assert.equal(button.disabled,false);assert.equal(note.hidden,true);click();assert.equal(target,'/api/auth/sso/start');
 assert.deepEqual(e.requests.map(x=>x.url),['/api/auth/sso/status']);
});
test('当前环境未连接统一认证时保留说明和本地登录，不产生认证跳转',async()=>{
 const e=engine(async()=>({available:false})),button=e.node('#sso-login');let bound=false;button.disabled=true;button.addEventListener=()=>{bound=true};
 vm.runInContext('loginView()',e.ctx);await new Promise(resolve=>setImmediate(resolve));
 assert.equal(button.disabled,true);assert.equal(bound,false);assert.match(e.node('#local-login-note').textContent,/当前环境未连接/);
 assert.match(e.node('#app').innerHTML,/class="btn primary login-local-submit" type="submit"/);
});
test('身份菜单保留账号密码入口，真实待办只提示其他可切换角色并转义名称',()=>{
 const e=engine();e.t.setUser({user:{name:'测试教师'},role:{name:'普通教师'},demo_switch:{current:'teacher',options:[{username:'teacher',label:'教师本人',todo_count:5},{username:'depthead',label:'教研室<负责人>',todo_count:3},{username:'collegehead',label:'学院负责人',todo_count:0}]}});
 const html=vm.runInContext('accountMenuHtml()',e.ctx);
 assert.match(html,/账号信息/);assert.match(html,/修改密码/);assert.match(html,/教研室&lt;负责人&gt;/);assert.doesNotMatch(html,/<负责人>/);
 assert.equal(vm.runInContext('accountOtherTodos()',e.ctx),3);assert.match(html,/data-id="demo:teacher"[^>]*aria-current="true"/);
 e.t.setUser({user:{name:'测试教师'},role:{name:'普通教师'},demo_switch:null,identities:[{id:'',role_name:'教师',current:true,todo_count:2},{id:'extra',role_name:'学院负责人',org_name:'授权学院',todo_count:4}]});
 assert.equal(vm.runInContext('accountOtherTodos()',e.ctx),4);assert.match(vm.runInContext('accountMenuHtml()',e.ctx),/data-id="identity:extra"/);
});

test('切换身份保留当前业务和页签，清除关键词与组织条件',async()=>{
 const e=engine(async()=>({ok:true}));let target;e.ctx.history.replaceState=(_s,_t,url)=>{target=url};e.ctx.location.reload=()=>{};e.ctx.location.search='';
 e.t.setUser({demo_switch:{current:'teacher',options:[{username:'teacher',label:'教师本人',todo_count:0},{username:'collegehead',label:'学院负责人',todo_count:2}]}});
 vm.runInContext("page='projects';filter={q:'关键词',org_id:'o1',teacher_id:'t1',tab:'x',project_view:'business'}",e.ctx);
 await e.t.handlers['account-switch']('demo:collegehead');
 assert.equal(target,'/#projects?project_view=business');
});
test('身份菜单安全切换，留在当前业务页而不跳待办，失败保留当前页面',async()=>{
 for(const failed of [false,true]){
  const e=engine(async()=>{if(failed)throw Error('连接中断');return {ok:true}});let target,reloaded=false;e.ctx.history.replaceState=(_state,_title,url)=>{target=url};e.ctx.location.reload=()=>{reloaded=true};e.ctx.location.search='?mode=review';
  e.t.setUser({demo_switch:{current:'teacher',options:[{username:'teacher',label:'教师本人',todo_count:0},{username:'collegehead',label:'学院负责人',todo_count:2}]}});
  await e.t.handlers['account-switch']('demo:teacher');assert.equal(e.requests.length,0);
  if(failed)await assert.rejects(e.t.handlers['account-switch']('demo:collegehead'),/连接中断/);else await e.t.handlers['account-switch']('demo:collegehead');
  const request=e.requests[0];assert.equal(request.url,'/api/auth/demo-switch');assert.equal(request.options.headers['X-CSRF-Token'],'test-csrf');assert.deepEqual(JSON.parse(request.options.body),{username:'collegehead'});
  assert.equal(target,failed?undefined:'/?mode=review#home');assert.equal(reloaded,!failed);
 }
 const e=engine();await assert.rejects(e.t.handlers['account-switch']('demo:unauthorized'),/不可用/);assert.equal(e.requests.length,0);
});

test('其他窗口切换身份后，待办响应不覆盖当前页面的角色',async()=>{
 const e=engine(async()=>({demo_switch:{current:'schooladmin',options:[]},identities:[],current_todo_count:99}));
 e.t.setUser({user:{name:'教师'},role:{name:'教师'},demo_switch:{current:'teacher',options:[]}});
 await vm.runInContext('refreshAccountSummary()',e.ctx);
 assert.equal(vm.runInContext('me.demo_switch.current',e.ctx),'teacher');assert.match(e.node('#account-count-status').textContent,/身份已变化/);
});

test('统一认证状态请求失败时如实提示未知且不启用入口',async()=>{
 for(const fail of [async()=>{throw Error('网络中断')},async()=>({ok:false})]){
  const e=engine(),button=e.node('#sso-login');e.ctx.fetch=fail;button.disabled=true;
  vm.runInContext('loginView()',e.ctx);await new Promise(resolve=>setImmediate(resolve));
  assert.equal(button.disabled,true);assert.match(e.node('#local-login-note').textContent,/暂时无法确认/);
  assert.match(e.node('#app').innerHTML,/id="login-error" role="alert"/);
 }
});
test('登录方式点击和方向键切换只显示对应内容，并保留已填写账号',()=>{
 const e=engine(),events={};
 for(const method of ['sso','local']){events[method]={};e.node('#login-'+method+'-tab').addEventListener=(name,fn)=>{events[method][name]=fn}}
 vm.runInContext('loginView()',e.ctx);e.node('#username').value='teacher';
 events.local.click();assert.equal(e.node('#login-form').hidden,false);assert.equal(e.node('#sso-entry').hidden,true);
 assert.equal(e.node('#login-local-tab').getAttribute('aria-selected'),'true');assert.equal(e.node('#login-local-tab').tabIndex,0);assert.equal(e.node('#login-sso-tab').tabIndex,-1);
 let prevented=false;events.local.keydown({key:'Home',preventDefault(){prevented=true}});
 assert.equal(prevented,true);assert.equal(e.node('#sso-entry').hidden,false);assert.equal(e.node('#login-form').hidden,true);
 events.sso.keydown({key:'ArrowRight',preventDefault(){}});assert.equal(e.node('#login-form').hidden,false);assert.equal(e.node('#username').value,'teacher');
 events.local.keydown({key:'ArrowLeft',preventDefault(){}});assert.equal(e.node('#sso-entry').hidden,false);
 events.sso.keydown({key:'End',preventDefault(){}});assert.equal(e.node('#login-form').hidden,false);
});
test('密码显示按钮能切换回遮蔽状态，并同步无障碍说明',()=>{
 const e=engine(),password=e.node('#password'),button=e.node('#login-password-toggle');let click;
 password.type='password';button.addEventListener=(name,fn)=>{if(name==='click')click=fn};vm.runInContext('loginView()',e.ctx);
 click();assert.equal(password.type,'text');assert.equal(button.getAttribute('aria-label'),'隐藏密码');assert.equal(button.getAttribute('aria-pressed'),'true');
 click();assert.equal(password.type,'password');assert.equal(button.getAttribute('aria-label'),'显示密码');assert.equal(button.getAttribute('aria-pressed'),'false');
});
const types=[{data_type:'teacher_hr',name:'教师人事信息',local_status:'AVAILABLE',mapping_count:0},{data_type:'training_income',name:'培训收入',local_status:'AVAILABLE',mapping_count:0}];

test('接口保存保留学校专用认证和未显示的凭据绑定',()=>{
 const e=engine(),build=vm.runInContext('buildRestAuth',e.ctx),options=vm.runInContext('restAuthOptions()',e.ctx);
 assert.ok(options.some(([v])=>v==='datahub_access_token'));
 for(const current of [{mode:'datahub_access_token',token_in:'body',token_path:'/school/token',token_field:'accessToken'},
  {mode:'basic',username_key:'school_user',password_key:'school_pass'},
  {mode:'bearer',header:'X-School-Token',prefix:'Token ',credential_key:'school_token'}]){
  assert.deepEqual(JSON.parse(JSON.stringify(build({probe_auth_mode:current.mode},'probe',current))),current);
 }
 const h=build({rule_auth_mode:'signature',rule_scope:''},'rule',{mode:'signature',secret_key:'school_secret',app_id_key:'school_app',separator:'',extra:'kept'});
 assert.equal(h.separator,'');assert.equal(h.secret_key,'school_secret');assert.equal(h.extra,'kept');
 assert.deepEqual(JSON.parse(JSON.stringify(build({probe_auth_mode:'none'},'probe',{mode:'basic',username_key:'old'}))),{mode:'none'});
});

test('允许值明确清空与未修改分开处理，保留零及布尔类型',()=>{
 const parse=vm.runInContext('parseBusinessValues',engine().ctx);
 assert.deepEqual(JSON.parse(JSON.stringify(parse('',[1]))),[]);
 assert.deepEqual(JSON.parse(JSON.stringify(parse(undefined,[0]))),[0]);
 assert.deepEqual(JSON.parse(JSON.stringify(parse('0，false'))),[0,'0',false,'false']);
});

test('表单只更新实际变更，未知参数和原分页位置原样保留',()=>{
 const merge=vm.runInContext('mergeFormChanges',engine().ctx);
 const original={owner:'原负责人',adapter:{request:{auth:{mode:'datahub_access_token',token_in:'body'},body:{size:'${limit}'},headers:{'X-School':'fixed'}}},optional:0};
 const before={owner:'原负责人',adapter:{request:{auth:{mode:'none'},query:{limit:'${limit}'},body:{},headers:{'X-School':'fixed'}}},optional:0};
 const after={...before,owner:'新负责人'};
 assert.deepEqual(JSON.parse(JSON.stringify(merge(original,before,after))),{...original,owner:'新负责人'});
 assert.deepEqual(JSON.parse(JSON.stringify(merge({values:[0]}, {values:[0,'0']},{values:[]}))),{values:[]});
});

test('首次保存保留部署凭据引用，未修改已有引用时不重置',async()=>{
 const own={items:catalog.items.map(item=>({...item,connection:{...item.connection,config:{},mappings:[]}}))};
 const e=engine(url=>url.startsWith('/api/connections/catalog')?own:responder(url));e.t.captureForm();vm.runInContext('saved=async()=>{}',e.ctx);
 await e.t.connectionForm('c-middle');const initial={owner:'',endpoint:'',adapter:'{}',mappings:'[]',reason:'维护资料',basis:''};
 await e.t.getForm().callback({...initial,owner:'学校负责人'},{_initialValues:initial});
 const write=e.requests.find(r=>r.url==='/api/connections/c-middle/draft'&&r.options.method==='PUT');
 assert.equal(JSON.parse(write.options.body).config.secret_env,'ND_MIDDLE_SECRET');
});

test('同步摘要读取失败明确显示未知，不伪装成从未同步',async()=>{
 const e=engine(url=>{if(url.startsWith('/api/connections/summary')||url.startsWith('/api/reference/source-status'))throw Error('offline');return integrationResponder(url)});
 e.t.setState('sync');const html=await e.t.pages.sync();
 assert.match(html,/读取失败，请刷新重试/);assert.match(html,/未将未知数量当作零/);assert.doesNotMatch(html,/还没同步过/);
});

test('分步表单阻止缺项、定位错误并允许返回保留字段',()=>{
 const e=engine(),inputs=[true,false,true].map((valid,i)=>({willValidate:true,valid,labels:[{textContent:'字段'+i}],checkValidity(){return this.valid},reportValidity(){this.reported=true}}));
 const groups=inputs.map((input,i)=>({hidden:false,querySelector:()=>({textContent:'分组'+i}),querySelectorAll:()=>[input],contains:el=>el===input}));
 const form={querySelectorAll:s=>s.includes('.social-fieldset')?groups:inputs,prepend(){}};
 const buttons=groups.map(()=>({classList:{toggle(){}},setAttribute(){}}));
 e.ctx.document.createElement=()=>({dataset:{},setAttribute(){},addEventListener(){},querySelectorAll:()=>buttons});
 const submit={};e.ctx.document.querySelectorAll=()=>[submit];e.node('#modal-root .modal-foot').prepend=()=>{};
 const flow=vm.runInContext('bindFormSteps',e.ctx)(form,'保存',false);
 assert.deepEqual(groups.map(g=>g.hidden),[false,true,true]);
 assert.equal(flow.submit(),false);assert.deepEqual(groups.map(g=>g.hidden),[true,false,true]);
 assert.equal(flow.submit(),false);assert.ok(inputs[1].reported);assert.match(e.node('#form-error').innerHTML,/字段1/);
 inputs[1].valid=true;assert.equal(flow.submit(),false);assert.equal(flow.submit(),true);
 flow.reveal(inputs[0]);assert.equal(groups[0].hidden,false);assert.equal(inputs[1].valid,true);
});
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
 const e=engine();e.t.setState('records',{tab:'participation'});const html=await e.t.pages.records();assert.match(html,/record-teaching" hidden/);assert.doesNotMatch(html,/record-participation mt20" hidden/);assert.equal((html.match(/id="filters"/g)||[]).length,1);assert.match(html,/participation-next/);assert.ok(e.requests.every(r=>!r.url.includes('tab=')));
});

test('参训类型写入地址，刷新式读取和重置保留类型且不进入业务接口参数',async()=>{
 const e=engine();e.t.setState('records',{q:'合成查询',start:'2026-10-01'},2,3,'period2026');
 await e.t.handlers['record-section']('participation');
 assert.equal(new URLSearchParams(e.ctx.location.hash.split('?')[1]).get('tab'),'participation');assert.equal(e.t.getState().filter.q,'合成查询');
 const restored=scope.restoreNavigation(e.ctx.location.hash,{records:'培训数据'}),fresh=engine();fresh.t.setState(restored.page,restored.filter,1,1,restored.periodId);
 const html=await fresh.t.pages.records();assert.match(html,/record-teaching" hidden/);assert.doesNotMatch(html,/record-participation mt20" hidden/);
 assert.ok([...e.requests,...fresh.requests].every(x=>!x.url.includes('tab=')));
 await e.t.handlers['reset-filters']();assert.deepEqual(JSON.parse(JSON.stringify(e.t.getState().filter)),{tab:'participation'});assert.equal(e.t.getState().periodId,'');assert.match(e.node('#content').innerHTML,/record-teaching" hidden/);
});

test('考核层级写入地址并保持周期进度，切换组织清掉不适用的教师条件',async()=>{
 const e=engine();e.t.setState('assessment',{q:'教师关键词',org_id:'dept1',teacher_id:'teacher',state:'COLLEGE',returned:'true',progress:'done'},1,1,'period2026');
 await e.t.handlers['assessment-tab']('college');
 assert.deepEqual(JSON.parse(JSON.stringify(e.t.getState().filter)),{progress:'done',tab:'college'});
 const restored=scope.restoreNavigation(e.ctx.location.hash,{assessment:'考核'});assert.equal(restored.filter.tab,'college');assert.equal(restored.periodId,'period2026');
 assert.ok(e.requests.some(x=>x.url.includes('/organization-assessments?')&&x.url.includes('target_kind=college')&&x.url.includes('progress=done')));assert.ok(e.requests.every(x=>!x.url.includes('tab=')));
 const fresh=engine();fresh.t.setState(restored.page,restored.filter,1,1,restored.periodId);await fresh.t.pages.assessment();assert.ok(fresh.requests.some(x=>x.url.includes('target_kind=college')));
 await e.t.handlers['reset-filters']();assert.equal(e.t.getState().filter.tab,'college');assert.equal(e.t.getState().periodId,'');
 const teacher=engine(undefined,'teacher');teacher.t.setState('assessment',{tab:'school'});await teacher.t.pages.assessment();assert.ok(teacher.requests.every(x=>!x.url.includes('organization-assessments')&&!x.url.includes('tab=')));
});

test('教师考核导出不把地址栏界面类型当成业务筛选',async()=>{
 const e=engine();e.t.setState('assessment',{tab:'teacher',progress:'done'},1,1,'period2026');await vm.runInContext("exportRows('assessments')",e.ctx);
 const body=JSON.parse(e.requests.find(x=>x.url==='/api/exports').options.body);assert.deepEqual(body.filters,{progress:'done',period_id:'period2026'});
});

test('本双月待办直接打开原汇总表单但不自动提交业务',async()=>{
 const e=engine(),events=[];e.ctx.todoEvents=events;vm.runInContext("nav=async page=>todoEvents.push('nav:'+page);socialAction=async action=>todoEvents.push('form:'+action)",e.ctx);
 await e.t.handlers.todo('social_report|bimonth');assert.deepEqual(events,['nav:recognition','form:social-report-new']);assert.equal(e.requests.filter(x=>x.options.method==='POST').length,0);
});

test('管理员实施页能进入既有参数迁移，普通学校账号不显示该入口',async()=>{
 const admin=engine(()=>({items:[]}));admin.t.setState('implementation');const html=await admin.t.pages.implementation();
 assert.match(html,/<details class="implementation-details mt20"><summary>实施人员使用：整包参数迁移/);assert.match(html,/data-action="integration-profile-download"/);assert.match(html,/data-action="integration-profile-import"/);assert.match(html,/恢复为待对接并暂停原同步计划/);assert.match(html,/真实验证和启用流程/);
 const regular=engine(()=>({items:[]}));regular.t.setUser({user:{id:'normal',is_admin:false},role:{kind:'school'},permissions:['portal.read','sync.manage']});regular.t.setState('implementation');
 const restricted=await regular.t.pages.implementation();assert.doesNotMatch(restricted,/integration-profile-download|integration-profile-import|实施人员使用：整包参数迁移/);
});

test('入站最终确认明确业务类型样本说明总行数及零错误，返回保持当前页',async()=>{
 const batch={id:'preview',data_type:'teacher_hr',source_label:'本地<合成批次>',state:'PREVIEW',total:61,errors:0,version:4};
 const items=Array.from({length:30},(_,i)=>({row_no:i+31,business_key:'J'+(i+31),mapped:{staff_no:'J'+(i+31),name:'合成教师'+(i+31),org_code:'dept1',active:true},raw:{},errors:[]}));
 const e=engine(()=>({batch,rows:{items,page:2,size:30,total:61}}));await e.t.showInbound('preview',2);e.t.captureForm();await e.t.handlers['inbound-confirm']('preview');const form=e.t.getForm();
 assert.match(form.body,/本次确认入站/);assert.match(form.body,/教师人事信息/);assert.match(form.body,/本地&lt;合成批次&gt;/);assert.match(form.body,/共 61 行 · 校验错误 0 行/);assert.doesNotMatch(form.body,/teacher_hr|本地<合成批次>/);assert.equal(form.options.contextLabel,'入站数据 / 明确确认');
 await form.options.returnTo();assert.ok(e.requests.filter(x=>x.url.includes('/inbound-batches/preview?page=2')).length>=2);assert.equal(e.requests.filter(x=>x.options.method==='POST').length,0);
});
test('入站预览复用三列业务布局，组合编号保留在默认折叠技术内容',async()=>{
 const batch={id:'preview',data_type:'teacher_course',source_label:'合成授课',state:'PREVIEW',total:1,errors:0,version:1};
 const row={row_no:1,business_key:'JW|J001|COURSE-1|第一学期',mapped:{staff_no:'J001',teacher_name:'合成教师',course_name:'合成课程',credit:0},raw:{},errors:[]};
 const e=engine(()=>({batch,rows:{items:[row],page:1,size:30,total:1}}));await e.t.showInbound('preview');const html=e.node('#modal-root').innerHTML;
 assert.doesNotMatch(html,/<th[^>]*>业务唯一编号/);assert.match(html,/<div class="import-row-preview"><dl/);assert.match(html,/合成课程/);
 assert.match(html,/<details class="implementation-details compact-details"><summary>实施人员使用：本行技术内容<\/summary>[\s\S]*JW\|J001\|COURSE-1\|第一学期/);assert.doesNotMatch(html,/<details[^>]* open/);
});

test('两个授课认定入口共用教师学年和所选课程提示，保留零学分并转义文字',async()=>{
 for(const [action,id] of [['creditreview-do','exclude'],['credit-review','approve|T1|2026-2027']]){
  const e=engine();e.ctx.document.querySelectorAll=()=>[{value:'chosen'}];
  vm.runInContext("modalContext={teacher_name:'<老师>',staff_no:'T1',school_year:'2026-2027',details:[{id:'chosen',course_name:'<零值课>',term_name:'第一学期',credit:0},{id:'other',course_name:'未选课程',credit:5}]}",e.ctx);
  e.t.captureForm();await e.t.handlers[action](id);const body=e.t.getForm().body;
  assert.match(body,/本次认定对象/);assert.match(body,/&lt;老师&gt; · 2026-2027 学年/);assert.match(body,/T1 · 已选 1 门课/);assert.match(body,/&lt;零值课&gt; · 第一学期 · 0.00 学分/);assert.doesNotMatch(body,/未选课程|<老师>|<零值课>/);assert.equal(e.requests.length,0);
 }
});

test('公示通知按当前授权直达既有公示页，普通通知不增加办理入口',async()=>{
 for(const [category,permission,destination,label] of [['社会培训积分公示','points.read','recognition','查看积分公示'],['年度考核公示','assessment.read','annual','查看学院考核公示']]){
  for(const allowed of [true,false]){
   const e=engine(()=>({title:'合成<公示>',category,body:'合成<内容>',created_at:'2026-10-18T01:00:00Z'}),'teacher');e.t.setUser({user:{id:'teacher'},role:{kind:'teacher'},permissions:allowed?[permission,'notice.read']:['notice.read']});
   await e.t.handlers.notice('notice');const html=e.node('#modal-root').innerHTML;assert.match(html,/合成&lt;内容&gt;/);
   assert.equal(html.includes('data-action="search-nav" data-id="'+destination+'"'),allowed);assert.equal(html.includes(label),allowed);assert.equal(e.requests.length,1);
  }
 }
 const e=engine(()=>({title:'普通通知',category:'业务通知',body:'内容'}),'teacher');await e.t.handlers.notice('notice');assert.doesNotMatch(e.node('#modal-root').innerHTML,/查看积分公示|查看学院考核公示/);
});

test('培训记录核对复用原业务摘要，明确零值且不混淆为参训',async()=>{
 const e=engine(()=>({record:{project:'合成<历史项目>',event_date:'2025-09-10',hours:2,participants:0,income:0}}),'teacher');e.t.setState('records');e.t.captureForm();
 await e.t.handlers['new-dispute']('record|history');const form=e.t.getForm();assert.equal(form.options.contextLabel,'培训记录 / 提出核对申请');assert.match(form.body,/本次核对原业务/);assert.match(form.body,/合成&lt;历史项目&gt;/);assert.match(form.body,/2025-09-10 · 2.00 学时 · 0 人次 · 归属培训收入 0.00 元/);assert.doesNotMatch(form.body,/合成<历史项目>/);assert.equal(e.requests.length,1);
});

test('读取核对原业务时切页不会弹出过期核对表单',async()=>{
 let finish;const e=engine(()=>new Promise(resolve=>{finish=resolve}),'teacher');e.t.setState('records');e.t.captureForm();const pending=e.t.handlers['new-dispute']('record|history');
 e.t.setState('points');finish({record:{project:'旧项目',event_date:'2025-09-10',hours:2,participants:0,income:0}});await pending;assert.equal(e.t.getForm(),undefined);
});

test('培训记录详情按原写入权限提供留痕更正，跨页台账入口会先关弹窗',async()=>{
 for(const writable of [true,false])for(const current of ['records','disputes']){
  const record={id:'history',teacher_id:'teacher',project:'合成记录',course:'课程',event_date:'2025-09-10',class_name:'班级',version:1,hours:2,income:0,participants:0};
  const e=engine(()=>({record,history:[]}));e.t.setUser({user:{id:writable?'manager':'teacher'},role:{kind:writable?'college':'teacher'},permissions:['records.read',...(writable?['records.write']:[])]});e.t.setState(current);
  await e.t.handlers.record('history');const html=e.node('#modal-root').innerHTML;assert.equal(html.includes('data-action="record-form" data-id="history"'),writable);
  assert.equal(html.includes('data-action="search-nav" data-id="records"'),current!=='records');if(current==='records')assert.match(html,/data-action="close"[^>]*>返回台账/);assert.equal(e.requests.length,1);
 }
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
 const e=engine();const html=vm.runInContext('settingWorkspace',e.ctx)({items:[{key:'branding',version:1,value:{school_name:'学校'}}]},{key:'branding',version:1,value:{school_name:'学校'}},{items:[]});assert.match(html,/id="settings-mobile-select"/);assert.match(html,/value="branding" selected/);assert.doesNotMatch(html,/实施人员使用|settings-raw|原始配置/);
});
test('audit access detail does not label reads as business changes',()=>{
 const e=engine();vm.runInContext("view={items:[{id:'a',module:'access',action:'GET',actor_name:'合成账号',result:'SUCCESS',after:{http_status:200},request_id:'trace'}]}",e.ctx);e.t.handlers['audit-detail']('a');const html=e.node('#modal-root').innerHTML;assert.match(html,/业务访问概况/);assert.match(html,/没有修改业务数据/);assert.doesNotMatch(html,/<h3>变更前|<h3>调整前/);assert.doesNotMatch(html,/实施人员使用|追踪编号/);
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
 const e=engine(responder);e.t.setState('assessment',{tab:'dept'},2);await e.t.pages.assessment();
 const url=e.requests.find(x=>x.url.startsWith('/api/organization-assessments')).url;assert.match(url,/page=2/);assert.match(url,/size=20/);
});
test('teaching one row and participation 21 rows have independent pagination',async()=>{
 const e=engine(url=>({items:[],page:url.includes('participations')?1:1,size:20,total:url.includes('participations')?21:1}));e.t.setState('records');e.t.setData([]);const html=await e.t.pages.records();
 assert.match(html,/data-action="next" disabled/);e.t.setState('records',{tab:'participation'});const participantHtml=await e.t.pages.records();assert.match(participantHtml,/data-action="participation-next" >下一页/);
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
test('入站批次只有校验通过且未入库时提示确认，已处理和错误批次只查看',async()=>{
 const states=[['PREVIEW',0,'待确认'],['PREVIEW',1,'错误'],['COMMITTED',0,'已入库'],['VOID',0,'已撤销']];
 const e=engine(url=>url.startsWith('/api/inbound-batches?')?{items:states.map(([state,errors,id])=>({id,state,errors,total:1,data_type:'teacher_hr'})),total:4,page:1,size:20}:responder(url));e.t.setState('hub',{tab:'batches'});const html=await e.t.pages.hub();
 assert.match(html,/data-action="inbound" data-id="待确认"[^>]*>查看 \/ 确认/);
 for(const id of ['错误','已入库','已撤销'])assert.match(html,new RegExp('data-action="inbound" data-id="'+id+'"[^>]*>查看<'));
});

test('未另设认定人时说明学校正常审核账号仍可认定',()=>{
 const e=engine();const html=vm.runInContext("orgReviewersLine({kind:'school',credit_reviewers:[]})",e.ctx);
 assert.match(html,/学校层面有考核审核权限的账号仍可认定/);assert.doesNotMatch(html,/只有系统管理员/);
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
 for(const label of ['学校基本资料','学校公开标识','连接检查','服务器安全交接','正式接口总地址','服务器凭据固定引用','等待学校确认'])assert.match(visible,new RegExp(label));
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
 assert.equal(t.pointLabel({kind:'SOCIAL',item_key:'social_teaching',source_snapshot:{correction_id:'correction'}}),'社会培训授课积分更正');
 assert.equal(t.pointLabel({kind:'SOCIAL',item_key:'social_auxiliary',source_snapshot:{correction_id:'correction'}}),'社会培训辅助积分更正');
 assert.equal(t.pointLabel({item_key:'x',source_snapshot:{rule:{config:{components:[{key:'x',label:'学校指标'}]}}}}),'学校指标');
});

test('export task lists show Chinese type and business status instead of internal codes',async()=>{
 const e=engine(()=>({items:[{id:'t',kind:'export',state:'DONE',payload:{kind:'assessments'},result:{filename:'internal-code.xlsx'},attempts:1}],page:1,size:20,total:1}));
 const html=await e.t.pages.exports();assert.match(html,/教师考核/);assert.match(html,/文件已生成/);assert.doesNotMatch(html,/internal-code.xlsx|>assessments</);
});

test('教师参训导出任务准确标识业务类型，不显示成课程人次',async()=>{
 const e=engine(()=>({items:[{id:'part-export',kind:'export',state:'DONE',payload:{kind:'participations'},attempts:1}],page:1,size:20,total:1}), 'teacher');
 const html=await e.t.pages.exports();
 assert.match(customerVisible(html),/教师参训记录/);assert.doesNotMatch(customerVisible(html),/课程人次|>participations</);
});

test('审计导出保留操作类型和其他筛选，默认与页面一致只导出改动',async()=>{
 for(const kind of [undefined,'change','access','all']){
  const e=engine();e.t.setState('audit',{...(kind?{kind}:{}),actor:'合成管理员',start:'2026-10-19'});
  await vm.runInContext("exportRows('audit')",e.ctx);
  const request=e.requests.find(x=>x.url==='/api/exports');
  assert.deepEqual(JSON.parse(request.options.body).filters,{...(kind?{kind}:{}),actor:'合成管理员',start:'2026-10-19',kind:kind||'change'});
 }
});

test('审计操作类型经过查询白名单、地址刷新和导出后保持一致',async()=>{
 for(const kind of ['change','access','all']){
  const filters=scope.pageFilters('audit',{kind,start:'2026-10-19',end:'2026-10-19'});
  const restored=scope.restoreNavigation(scope.navigationHash('audit',filters),{audit:'操作审计'});
  assert.equal(restored.filter.kind,kind);
  const e=engine();e.t.setState(restored.page,restored.filter);await e.t.pages.audit();
  const query=new URL(e.requests[0].url,'http://testserver').searchParams;
  assert.equal(query.get('kind'),kind==='all'?null:kind);
  await vm.runInContext("exportRows('audit')",e.ctx);
  assert.equal(JSON.parse(e.requests.find(x=>x.url==='/api/exports').options.body).filters.kind,kind);
 }
});

test('历史导出只加说明，保留原下载入口和任务数据，新格式明确生成时间与口径',async()=>{
 const task={id:'old-report',kind:'export',state:'DONE',historical_report:true,payload:{kind:'points',filters:{period_id:'period',q:'<检索>'}},result:{size:2048}};
 const before=JSON.stringify(task),e=engine(()=>({items:[task],total:1,page:1,size:20,task,attempts:[]}));
 e.t.setData([{id:'period',name:'合成周期'}]);
 const html=await e.t.pages.exports();assert.match(html,/历史版本/);assert.match(html,/data-action="task-download" data-id="old-report"/);
 await e.t.handlers.task(task.id);const detail=e.node('#modal-root').innerHTML;
 assert.match(detail,/历史文件未记录/);assert.match(detail,/合成周期/);assert.match(detail,/&lt;检索&gt;/);assert.doesNotMatch(detail,/<检索>|<pre/);assert.equal(JSON.stringify(task),before);
 const render=vm.runInContext('exportResultSummary',e.ctx),current=render({report_version:2,generated_at:'2026-10-19T12:00:00',rows:0,size:1024},{payload:{kind:'points'},historical_report:false});
 assert.match(current,/当前格式/);assert.match(current,/生成时间（北京时间）/);assert.match(current,/0 条/);assert.match(current,/正负分值的代数和/);assert.doesNotMatch(current,/历史版本：/);
});

test('报表指南说明各类口径与业务页直出入口，按当前权限显示',()=>{
 const admin=engine();admin.t.setUser({user:{id:'admin',is_admin:true},role:{kind:'school'},permissions:['records.read','qualification.read','points.read','assessment.read','audit.read','data.export']});
 const html=vm.runInContext('exportReportGuide()',admin.ctx);
 for(const label of ['培训授课数据','教师参训记录','教师资质','教师积分','教师考核','组织考核','操作审计','结构化业务移交包','项目上报表','社会培训办理材料','已认定积分汇总'])assert.ok(html.includes(label),label);
 assert.match(html,/审核通过.*不等于当前有效/);assert.match(html,/历史区间2023-07-01至2026-06-30/);assert.match(html,/按教师当前组织归属/);
 const teacher=engine(undefined,'teacher'),own=vm.runInContext('exportReportGuide()',teacher.ctx);
 assert.doesNotMatch(own,/操作审计|结构化业务移交包|项目上报表|>组织考核</);assert.match(own,/跨周期更正/);
});

test('实际台账页面上下文包含统一时间格式，历次报送可完整渲染',async()=>{
 const stamp='2026-10-11T21:57:00',totals={claimed_total:'30',recommended_total:'30',final_total:'30',pending_rows:0};
 const detail={id:'context-time',version:1,org_name:'合成学院',can_review:false,can_draft:false,note:'',versions:[{id:'old',version_no:1,created_at:stamp,totals},{id:'context-time',version_no:2,created_at:stamp,totals}],totals,data:{year:2026,version_no:2,template_label:'合成台账',file:{name:'合成.xlsx'},summary:{serious:0},rows:[]}};
 const e=engine(async()=>detail),c=vm.runInContext('ledgerContext()',e.ctx);c.render=async()=>{};c.nav=async(_page,next)=>{c.filter=next};
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
test('教师首页迟到不能清掉已渲染积分台账，本人确认仍打开原教师周期表单',async()=>{
 let releaseHome;
 const balance={id:'balance-j002',teacher_id:'otherteacher',period_id:'period2025',version:7,confirmed:false,locked:false};
 const e=engine(url=>{
  if(url.startsWith('/api/statistics?'))return new Promise(resolve=>{releaseHome=resolve});
  if(url.startsWith('/api/point-balances?'))return {items:[balance]};
  if(url.startsWith('/api/points?'))return {items:[{id:'teaching',teacher_id:'otherteacher',kind:'SOCIAL',item_key:'social_teaching',amount:'0.07',source_snapshot:{social_claim:'claim'}},{id:'auxiliary',teacher_id:'otherteacher',kind:'SOCIAL',item_key:'social_auxiliary',amount:'0.50',source_snapshot:{social_claim:'claim'}}],sum:'0.57',total:2,page:1,size:20};
  if(url.startsWith('/api/social/overview'))return {points:{year:'0.57',five_years:'0.57'}};
  if(url.startsWith('/api/social/mine'))return {projects:[],claims:[]};
  if(url.startsWith('/api/applications/mine'))return {items:[],counts:{}};
  if(url.startsWith('/api/applications/teaching-courses'))return {courses:[]};
  return homeResponse(url);
 },'teacher');
 e.t.setUser({user:{id:'otherteacher',name:'测试教师二',staff_no:'J002'},role:{kind:'teacher'},permissions:['portal.read','records.read','points.read','assessment.read','notice.read']});
 e.t.setData([{id:'period2025',name:'2025合成核对周期'}],[{id:'otherteacher',name:'测试教师二'}]);
 const home=e.t.nav('home');assert.equal(typeof releaseHome,'function');
 await e.t.nav('points');const pointsHtml=e.node('#content').innerHTML;
 assert.match(pointsHtml,/0.57/);assert.match(pointsHtml,/data-action="balance-action" data-id="balance-j002"/);
 releaseHome({income:0,participants:0});await home;
 assert.equal(e.node('#content').innerHTML,pointsHtml,'迟到首页不能覆盖当前积分页面');
 e.t.captureForm();assert.doesNotThrow(()=>e.t.handlers['balance-action']('balance-j002'));
 const form=e.t.getForm();assert.equal(form.title,'确认本人积分');assert.equal(form.options.contextLabel,'教师积分激励 / 本人确认');
 assert.match(form.body,/2025合成核对周期 · 测试教师二/);assert.equal(e.t.getView().balances[0].version,7);
 assert.ok(!e.requests.some(r=>r.options.method==='POST'),'打开表单不提前确认或改写台账');
});
// 老师的工作总览单独设计（易用性第 6 条），见下方 teacher home 用例。
// 管理角色首页只留待办、概况、快捷入口、政策通知四块；统计分析在驾驶舱或本组织管理页，接口状态在对接与同步。
for(const role of ['dept','college','school'])test('task-first home preserves role entry points: '+role,async()=>{
 const e=engine(homeResponse,role);e.t.setState('home');
 const html=await e.t.pages.home();
 const order=(['dept','college'].includes(role)?['workbench-pending','workbench-shortcuts','home-indicators']:['workbench-pending','home-indicators','workbench-shortcuts']).map(x=>html.indexOf(x));
 assert.ok(order.every(i=>i>0));assert.deepEqual([...order].sort((a,b)=>a-b),order);
 assert.doesNotMatch(html,/portal-hero|NOT_CONNECTED|NaN|workbench-statistics|业务概况与统计分析|学校接口状态|资质有效期提醒 · 0/);
 assert.match(html,/待办理与资质提醒包含全部周期/);
 assert.equal(e.requests.some(x=>x.url.startsWith('/api/connections/summary')),false);
 if(role==='dept'||role==='college'){assert.match(html,role==='dept'?/本教研室管理/:/本学院与教研室管理/);assert.doesNotMatch(html,/data-id="cockpit"/);assert.match(html,/看趋势与考核进度/);}
 if(role==='school')assert.match(html,/data-action="nav" data-id="cockpit">驾驶舱看趋势与排行/);
 assert.ok(e.requests.every(x=>x.options.method==='GET'));
});
test('home shows at most five tasks and folds per-capita credit into the overview row',async()=>{
 const items=Array.from({length:8},(_,i)=>({id:'t'+i,type:'qualification',title:'待办'+i,owner_name:'教师',state:'SUBMITTED'}));
 const e=engine(url=>url.startsWith('/api/portal/workbench')?{...homeSummary,tasks:{total:15,returned:0,items}}:url.startsWith('/api/reference/credit-summary')?{school_year:'2026-2027',staff:733,teaching_staff:0,avg_credit:'0.00',avg_teaching:null}:homeResponse(url),'school');
 const html=await e.t.pages.home();
 assert.match(html,/待办4/);assert.doesNotMatch(html,/待办5/);assert.match(html,/workbench-count">15/);
 const row=html.slice(html.indexOf('class="kpis kpis-5"'),html.indexOf('</section>',html.indexOf('class="kpis kpis-5"')));
 assert.match(row,/全校人均授课学分/);assert.match(row,/2026-2027 学年还没有已认定的课/);assert.doesNotMatch(html,/credit-kpi/);
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
test('home statistics period never filters task summary',async()=>{
 const e=engine(homeResponse);e.t.setState('home',{project_code:'P1'},1,1,'period-1');
 await e.t.pages.home();
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
 const groups=[...html.matchAll(/<span class="nav-group-label">.*?<span>([^<]+)<\/span>/g)].map(m=>m[1]);
 assert.deepEqual(groups,['工作台','教师发展','培训业务','统计分析','系统管理']);
 for(const title of ['首页','待办中心','教师资质','授课学分','教师积分','三级考核','培训项目','培训课程','培训基地','培训师资','培训数据','课程资源统计','院系概况','学院台账','管理驾驶舱','用户与权限','导入导出','系统对接','规则配置','日志与运维'])assert.ok(html.includes('title="'+title+'"'),title);
 for(const route of ['home','todos','records','qualifications','points','assessment','rules','permissions','audit','sync','imports','organization','cockpit','ledgers','resources'])assert.ok(html.includes('data-id="'+route+'"'),route);
 // 字典参数、运行备份、导出下载并入合并页的标签，不再单独占菜单。
 for(const route of ['settings','operations','exports'])assert.ok(!html.includes('data-id="'+route+'"'));
 assert.equal((html.match(/aria-expanded="true"/g)||[]).length,5);
 const business=html.slice(html.indexOf('>培训业务<'),html.indexOf('>统计分析<'));
 assert.deepEqual([...business.matchAll(/data-id="(\w+)"/g)].map(m=>m[1]),['projects','courses','bases','trainers']);
 const stats=html.slice(html.indexOf('>统计分析<'),html.indexOf('>系统管理<'));
 assert.deepEqual([...stats.matchAll(/data-id="(\w+)"/g)].map(m=>m[1]),['records','outcomes','resources','organization','ledgers','cockpit']);
});
test('教师与管理角色共用一棵菜单树，教师培训业务暂指向本人申报页',()=>{
 const e=engine(undefined,'teacher');e.t.setUser({user:{id:'u',name:'教师'},role:{kind:'teacher'},permissions:['portal.read','records.read','qualification.read','qualification.write','points.read','assessment.read','dispute.write','notice.read','export']});
 const html=e.t.sidebarNavigation(),ids=[...html.matchAll(/data-action="nav" data-id="(\w+)"/g)].map(m=>m[1]);
 assert.deepEqual(ids,['home','todos','notices','qualifications','credits','points','assessment','disputes','apply_project','apply_course','apply_base','apply_trainer','records','outcomes']);
 assert.equal((html.match(/class="nav-section"/g)||[]).length,4);assert.doesNotMatch(html,/>系统管理<|data-id="exports"|data-id="mine"/);
 for(const title of ['培训项目','培训课程','培训基地','培训师资','教师资质','教师积分','三级考核'])assert.ok(html.includes('title="'+title+'"'),title);
 for(const p of ['projects','courses','disputes','exports','records','mine'])assert.ok(e.t.pageAllowed(p),p+' still reachable from links');
});
test('navigation does not expose unauthorized items or empty groups',()=>{
 const e=engine();e.t.setUser({user:{id:'u',name:'教师'},role:{kind:'teacher'},permissions:['portal.read']});
 const html=e.t.sidebarNavigation();assert.match(html,/>工作台</);assert.doesNotMatch(html,/系统管理|统计分析|教师发展|data-id="settings"|data-id="organization"/);
});
test('学校审核账号不是系统管理员时不显示账号与权限，系统管理员仍显示',()=>{
 for(const [admin,shown] of [[false,false],[true,true]]){
  const e=engine();e.t.setUser({user:{id:'u',name:'学校',is_admin:admin},role:{kind:'school'},permissions:['portal.read','users.manage','records.read']});
  assert.equal(e.t.sidebarNavigation().includes('data-id="permissions"'),shown);
 }
});
test('教师从看板进入项目等业务页时侧栏选中对应申报入口，其他角色不变',()=>{
 const e=engine();e.t.setUser({user:{id:'u',name:'教师'},role:{kind:'teacher'},permissions:['portal.read']});
 for(const [page,key] of [['projects','apply_project'],['courses','apply_course'],['bases','apply_base'],['trainers','apply_trainer']])assert.equal(vm.runInContext(`navKey('${page}')`,e.ctx),key);
 e.t.setUser({user:{id:'u',name:'学院'},role:{kind:'college'},permissions:['records.read']});
 assert.equal(vm.runInContext("navKey('projects')",e.ctx),'projects');assert.equal(vm.runInContext("navKey('resources')",e.ctx),'resources');
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
 assert.match(html,/进入审批中心/);assert.doesNotMatch(html,/设计预览|合成示例/);
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
test('学校原表驾驶舱使用独立筛选，原授课统计与真实同步状态仍可展开',async()=>{
 const period={year:2026,label:'2026年1—8月',start:'2026-01-01',end:'2026-08-31'};
 const report={available:true,school_name:'湖南科技职业学院',period,periods:[period],college:'合成学院',project:'p4',
  read_at:'2026-10-19T00:00:00Z',version:'hash',totals:{person_times:'204',person_days:null,records:1,colleges:1,person_times_colleges:1},
  colleges:['合成学院'],projects:[{id:'p4',name:'原表项目',college:'合成学院'}],rank:[{name:'合成学院',value:'204'}],composition:[{name:'合成学院',value:1}],
  comparison:[{...period,records:5,colleges:1}],table:[{college:'合成学院',records:{2026:5},selected_records:1,quantities:[{unit:'人次',value:'204'}],status:'待核定'}],details:[],warnings:[],excluded:[],note:'原表报送值',comparison_note:'不同口径分别统计'};
 const e=engine(url=>url.startsWith('/api/social/cockpit?')?report:cockpitResponder(url));
 vm.runInContext("me.environment='test'",e.ctx);
 e.t.setState('cockpit',{report_college:'合成学院',report_year:'2026',report_project:'p4',org_id:'o'});
 const html=await e.t.pages.cockpit();
 assert.match(html,/sc-main-value">204<small>人次/);assert.match(html,/sc-legacy/);assert.match(html,/实际同步状态/);
 assert.match(html,/外部接口未真实连接/);
 assert.match(html,/本地验证/);assert.match(html,/本区为隔离样本授课数据/);
 const reportRequest=e.requests.find(x=>x.url.startsWith('/api/social/cockpit?'));
 assert.equal(new URL(reportRequest.url,'http://test').searchParams.get('project'),'p4');
 for(const x of e.requests.filter(x=>x.url.startsWith('/api/statistics')))assert.doesNotMatch(x.url,/report_college|report_year|report_project/);
});

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

test('教师考核顶部摘要跟随所选周期，不能混入其他周期结果',async()=>{
 const e=engine(url=>{
  if(url.startsWith('/api/assessment-summary/latest'))return url.includes('period_id=new-period')?{assessment:{id:'new',teacher_id:'u',state:'ARCHIVED',score:'100'},period:{name:'本轮新周期'}}:{assessment:{id:'old',teacher_id:'u',state:'ARCHIVED',score:'67'},period:{name:'旧周期'}};
  return {items:[],total:0,page:1,size:20};
 },'teacher');
 e.t.setUser({user:{id:'u',staff_no:'J001'},role:{kind:'teacher'},permissions:['assessment.read']});
 e.t.setState('assessment',{},1,1,'new-period');
 const html=await e.t.pages.assessment();
 assert.match(html,/本轮新周期/);assert.doesNotMatch(html,/旧周期|67\.00/);
 assert.ok(e.requests.some(r=>r.url==='/api/assessment-summary/latest?period_id=new-period'));
});
test('教师首页复用统一待办，核心数据靠前并明确积分待启用条件',async()=>{
 const e=engine(url=>{
  if(url.startsWith('/api/todos?'))return {items:[{type:'social_resource',id:'r1',title:'<img src=x>教研室请你核对积分',state:'待教师确认'}],total:2,attention_counts:{handle:2,waiting:3}};
  if(url.startsWith('/api/social/mine'))return {reminders:[{text:'不能被当作本人待办的旧提醒'}]};
  if(url.startsWith('/api/social/overview'))return {participants:{mine:{value:100}},points:{year:'12.5',five_years:'85',five_year_target:340,title_points:'0.13',trial:'2'}};
  if(url.startsWith('/api/statistics'))return {income:'123.45'};
  if(url.startsWith('/api/assessment-summary/latest'))return {assessment:{id:'a1',teacher_id:'u',state:'TEACHER',score:'88.5',returned:false},period:{name:'2026年度'}};
  if(url.startsWith('/api/notices'))return {items:[{id:'n1',title:'积分办法通知',created_at:'2026-09-01T00:00:00'}]};
  return homeResponse(url)},'teacher');
 e.t.setState('home');const html=await e.t.pages.home();
 for(const t of ['有 <b>2</b> 件事需要你处理','3 项等待核对或学校确认','&lt;img src=x&gt;','todo" data-id="social_resource|r1"','123.45','原表分配人次','12.50','近五年累计 <b>85.00</b> 分','340分条件待学校正式启用','另有 2.00 分还在审批中','88.50','查看并确认','积分办法通知'])assert.ok(html.includes(t),t);
 assert.ok(html.indexOf('teacher-overview-metrics')<html.indexOf('teacher-apply-grid'));
 assert.ok(html.indexOf('teacher-todo')<html.indexOf('teacher-apply-grid'));
 assert.doesNotMatch(html,/<img src=x>|不能被当作本人待办|teacher-points-bar|NaN/);
 assert.ok(e.requests.some(x=>x.url==='/api/todos?attention=handle&size=4'));
 assert.match(e.requests.find(x=>x.url.startsWith('/api/statistics')).url,/start=\d{4}-01-01&end=\d{4}-12-31/);
 assert.ok(e.requests.every(x=>x.options.method==='GET'));
});

test('教师首页无待办时保留等待进度入口，不把等待事项算进待办',async()=>{
 const e=engine(url=>{
  if(url.startsWith('/api/todos?'))return {items:[],total:0,attention_counts:{handle:0,waiting:2}};
  if(url.startsWith('/api/assessment-summary/latest'))return {assessment:{id:'a1',teacher_id:'u',state:'ARCHIVED',score:'90',returned:false},period:{name:'2025年度'}};
  return homeResponse(url)},'teacher');
 e.t.setState('home');const html=await e.t.pages.home();
 for(const t of ['当前没有需要你处理的事项','2 项等待核对或学校确认','查看等待事项','已归档，结果已正式生效','查看明细'])assert.ok(html.includes(t),t);
 assert.doesNotMatch(html,/查看并确认|有 <b>2<\/b> 件事|NaN/);
});

test('老师待办在分页前请求分类，等待事项只放在我的申请且无重复类别下拉',async()=>{
 const e=engine(url=>url.startsWith('/api/applications/mine')?{items:[],counts:{draft:0,pending:0,returned:0,done:0}}:{items:[{type:'dispute',id:'d1',title:'待核对<收入>',state:'OPEN',action_required:false,action_hint:'等待授权人员核对'}],total:23,page:2,size:20,counts:{dispute:23},attention_counts:{handle:0,waiting:23}},'teacher');
 e.t.setState('todos',{q:'资质',type:'qualification'},2);
 let html=await e.t.pages.todos();assert.match(e.requests[0].url,/attention=handle/);assert.match(e.requests[0].url,/page=2/);assert.match(e.requests[0].url,/q=/);assert.doesNotMatch(html,/<select name="type"/);
 vm.runInContext("todoTab='mine'",e.ctx);html=await e.t.pages.todos();
 assert.match(e.requests.at(-2).url,/attention=waiting/);assert.doesNotMatch(e.requests.at(-2).url,/q=|type=/);
 assert.match(html,/等待核对与学校确认/);assert.match(html,/查看进度/);assert.match(html,/待核对&lt;收入&gt;/);assert.doesNotMatch(html,/去办理|<收入>/);
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


test('课程资源统计归入统计分析，培训课程和基地入口保留',()=>{
 const e=engine();const menus=vm.runInContext('navItems()',e.ctx).flatMap(group=>group[1]).map(item=>item[0]);
 assert.ok(menus.includes('courses'));assert.ok(menus.includes('bases'));assert.ok(menus.includes('resources'));
});

test('simplified sync overview shows three connectors, four hub tables and hides implementation tools behind a link',async()=>{
 const e=engine(integrationResponder);e.t.setState('sync');const html=await e.t.pages.sync();
 for(const title of ['学校统一认证','学校数据中台','湘培直通车','立即同步','定时计划','高级设置'])assert.ok(html.includes(title));
 assert.match(html,/data-action="nav" data-id="implementation"/);
 assert.doesNotMatch(html,/下载学校资料采集表|旧版沟通清单/);
});

test('teacher home does not claim there is nothing to do when to-dos fail to load, and explains a returned review',async()=>{
 const e=engine(url=>{
  if(url.startsWith('/api/todos?'))throw new Error('offline');
  if(url.startsWith('/api/assessment-summary/latest'))return {assessment:{id:'a1',teacher_id:'u',state:'TEACHER',score:'70',returned:true},period:{name:'2026年度'}};
  return homeResponse(url)},'teacher');
 e.t.setState('home');const html=await e.t.pages.home();
 for(const t of ['待办暂时没有加载出来','考核被退回，请先在详情里看退回原因','查看并确认'])assert.ok(html.includes(t),t);
 assert.doesNotMatch(html,/当前没有需要你处理的事项|都处理完了|NaN/);
});

test('编辑历史资质保留当前类别，不静默改成首个新类别',async()=>{
 const e=engine(async url=>url.endsWith('/qualification-categories')?{categories:['职业资格','教学资质']}:{qualification:{id:'q',teacher_id:'u',category:'双师型中级',name:'合成资质',version:1}},'teacher');
 e.t.captureForm();await vm.runInContext('qualificationForm',e.ctx)('q');
 const form=e.t.getForm();assert.match(form.body,/<option value="双师型中级" selected/);assert.equal(typeof form.options.returnTo,'function');
 await form.options.returnTo();assert.ok(e.requests.filter(r=>r.url.endsWith('/qualifications/q')).length===2);
});

test('资质表单明确草稿与审核，附件失败保留同一条草稿，提交使用上传后的版本',async()=>{
 for(const mode of ['draft','submit','upload-error','submit-error']){
  const e=engine(async(url,options)=>{
   if(url.endsWith('/qualification-categories'))return {categories:['教学资质']};
   if(url.endsWith('/qualifications')&&options.method==='POST')return {id:'q-new',version:1};
   if(url.includes('/attachments/qualification/')){if(mode==='upload-error')throw Error('附件上传失败');return {id:'att'};}
   if(url.endsWith('/q-new/actions')&&mode==='submit-error')throw Error('审核提交失败');
   if(url.endsWith('/qualifications/q-new'))return {qualification:{id:'q-new',teacher_id:'u',state:'DRAFT',category:'教学资质',name:'合成证书',version:2},attachments:[],events:[],revisions:[]};
   return {items:[],total:0,page:1,size:20};
  },'teacher');
  e.t.setState('qualifications');e.t.captureForm();await vm.runInContext('qualificationForm',e.ctx)('');const f=e.t.getForm();
  assert.equal(f.options.page,true);assert.equal(f.options.draft,'保存草稿');assert.equal(f.options.submit,'提交审核');assert.doesNotMatch(f.body,/submit_now/);
  const file=new Blob(['synthetic certificate'],{type:'image/png'});file.name='证书.png';e.node('#f-file').files=mode==='draft'?[]:[file];
  await f.callback({category:'教学资质',name:'合成证书',certificate_no:'Q1',issuer:'合成机构',obtained:'2026-01-01',expires:'',reason:'合成验证'},{querySelector:sel=>e.node(sel)},{value:mode==='draft'?'draft':'submit'});
  const created=e.requests.filter(r=>r.url.endsWith('/qualifications')&&r.options.method==='POST');assert.equal(created.length,1);assert.equal(JSON.parse(created[0].options.body).expires,null);
  const uploads=e.requests.filter(r=>r.url.includes('/attachments/qualification/')),submits=e.requests.filter(r=>r.url.endsWith('/q-new/actions'));
  assert.equal(uploads.length,mode==='draft'?0:1);assert.equal(submits.length,['submit','submit-error'].includes(mode)?1:0);
  if(mode==='submit'){assert.equal(uploads[0].options.body.get('expected_version'),'1');assert.equal(JSON.parse(submits[0].options.body).expected_version,2);const paths=e.requests.map(r=>r.url);assert.ok(paths.indexOf('/api/qualifications/q-new')>paths.indexOf('/api/attachments/qualification/q-new'));}
  assert.match(e.node('#modal-root').innerHTML,/合成证书/);
 }
});

test('资质一次选择三张证书逐份上传，任一失败保留草稿且不提交审核',async()=>{
 for(const failSecond of [false,true]){
  let version=1;const attachments=[];
  const e=engine(async(url,options)=>{
   if(url.endsWith('/qualification-categories'))return {categories:['教学资质']};
   if(url.endsWith('/qualifications')&&options.method==='POST')return {id:'q-multi',version};
   if(url.includes('/attachments/qualification/q-multi')){const name=options.body.get('file').name;assert.equal(Number(options.body.get('expected_version')),version);if(failSecond&&name==='第2张.png')throw Error('测试第二张失败');attachments.push({id:'att'+attachments.length,name,size:10});version++;return {id:'att'};}
   if(url.endsWith('/qualifications/q-multi'))return {qualification:{id:'q-multi',teacher_id:'u',state:'DRAFT',category:'教学资质',name:'多张合成证书',version},attachments,events:[],revisions:[]};
   return {items:[],total:0,page:1,size:20};
  },'teacher');
  e.t.setState('qualifications');e.t.captureForm();await vm.runInContext('qualificationForm',e.ctx)('');const form=e.t.getForm();assert.match(form.body,/type="file"[^>]*multiple/);
  e.node('#f-file').files=[1,2,3].map(i=>new File(['synthetic'],'第'+i+'张.png',{type:'image/png'}));
  await form.callback({category:'教学资质',name:'多张合成证书',reason:'合成测试'},{querySelector:sel=>e.node(sel)},{value:'submit'});
  const uploads=e.requests.filter(r=>r.url.includes('/attachments/qualification/')),submits=e.requests.filter(r=>r.url.endsWith('/q-multi/actions'));
  assert.equal(uploads.length,3);assert.equal(submits.length,failSecond?0:1);assert.equal(attachments.length,failSecond?2:3);assert.equal(e.requests.filter(r=>r.url.endsWith('/qualifications')&&r.options.method==='POST').length,1);
  if(!failSecond)assert.equal(JSON.parse(submits[0].options.body).expected_version,4);
 }
});

test('图片材料提供分组预览和下载，文档保留下载，文件名必须转义',()=>{
 const e=engine(),html=vm.runInContext('downloads',e.ctx)([{id:'a1',name:'正面<证书>.png',size:2048},{id:'a2',name:'背面.jpg',size:1024},{id:'a3',name:'说明.pdf',size:4096}]);
 assert.equal((html.match(/data-action="attachment-preview"/g)||[]).length,2);assert.equal((html.match(/data-action="attachment-download"/g)||[]).length,3);assert.match(html,/class="material-list"/);assert.match(html,/正面&lt;证书&gt;.png/);assert.doesNotMatch(html,/<证书>/);
});

test('资质提交缺附件或格式大小不合格时不创建记录',async()=>{
 for(const file of [null,{name:'错误.txt',size:2},{name:'太大.pdf',size:10*1024*1024+1}]){
  const e=engine(async()=>({categories:['教学资质']}),'teacher');e.t.captureForm();await vm.runInContext('qualificationForm',e.ctx)('');e.node('#f-file').files=file?[file]:[];
  await assert.rejects(e.t.getForm().callback({},{querySelector:sel=>e.node(sel)},{value:'submit'}),/请选择|不能上传/);assert.equal(e.requests.filter(r=>r.options.method==='POST').length,0);
 }
});

test('资质临期采用学校提醒天数，草稿不标临期，学校当天和零天窗口有效',()=>{
 const e=engine(),expiry=vm.runInContext('qualificationExpiry',e.ctx);e.ctx.Date=class extends Date{static now(){return Date.parse('2026-10-16T20:00:00Z')}};
 assert.doesNotMatch(expiry('2026-10-23',5),/即将到期/);assert.match(expiry('2026-10-23',30),/即将到期 · 剩余 6 天/);assert.doesNotMatch(expiry('2026-10-23',30,'DRAFT'),/即将到期/);assert.match(expiry('2026-10-17',0),/今天到期/);assert.match(expiry('2026-10-16',30),/已过期 1 天/);assert.match(expiry(null,30),/长期有效/);
});

test('教师资质列表按状态提供入口，去掉本人姓名与版本列，单页不显示翻页',async()=>{
 const items=['DRAFT','RETURNED','APPROVED'].map((state,i)=>({id:'q'+i,name:'证书<'+i+'>',category:'教学资质',state,certificate_no:'Q'+i,issuer:'合成机构',expires:null}));
 const e=engine(async url=>url.includes('/qualification-summary')?{items:[{key:'VALID',count:1}],expiry_days:5,note:'学校提前5天提醒'}:{items,total:3,page:1,size:20},'teacher');
 e.t.setUser({user:{id:'u',staff_no:'T1'},role:{kind:'teacher'},permissions:['qualification.read','qualification.write','portal.read']});
 const html=await e.t.pages.qualifications();for(const label of ['继续填写','补充材料','查看详情','合成机构','学校提前5天提醒'])assert.ok(html.includes(label),label);assert.match(html,/证书&lt;0&gt;/);assert.doesNotMatch(html,/<th[^>]*>教师<|<th[^>]*>版本<|pagination/);
 const manager=engine(async()=>({items,total:3,page:1,size:20}));const all=await manager.t.pages.qualifications();assert.match(all,/<th[^>]*>教师<|<th[^>]*>版本</);assert.doesNotMatch(all,/teacher-qualification-list/);
});

test('我的资质列表在原证书列展示图片入口，无附件记录说明缺图，管理角色保留原表格',async()=>{
 const items=[{id:'q-image',name:'证书<正本>',category:'职业资格',attachment_ids:['a1','a2'],state:'APPROVED'},{id:'q-empty',name:'历史资质',category:'教学资质',attachment_ids:[],state:'APPROVED'}];
 const e=engine(async url=>url.includes('/qualification-summary')?{items:[],total:2}:{items,total:2,page:1,size:20},'teacher');
 e.t.setUser({user:{id:'u',staff_no:'T1'},role:{kind:'teacher'},permissions:['qualification.read','file.read','portal.read']});
 const html=await e.t.pages.qualifications();assert.match(html,/data-action="qualification-images" data-id="q-image"/);assert.match(html,/data-qualification-preview="q-image"/);assert.match(html,/证书&lt;正本&gt;/);assert.match(html,/暂无图片/);assert.match(html,/当前版本暂无材料/);assert.equal((html.match(/<th[ >]/g)||[]).length,5);
 e.t.setUser({user:{id:'u'},role:{kind:'teacher'},permissions:['qualification.read','portal.read']});assert.doesNotMatch(await e.t.pages.qualifications(),/data-qualification-preview/);
});

test('证书详情将图片和文档分开，图片同组可切换，空材料保留历史查阅说明',()=>{
 const e=engine(),render=vm.runInContext('qualificationMaterials',e.ctx);
 const html=render([{id:'a1',name:'正面.png',size:100},{id:'a2',name:'背面.jpg',size:200},{id:'a3',name:'说明.pdf',size:300}],'历史材料请查看审核记录');
 assert.match(html,/qualification-image-gallery/);assert.match(html,/2 张/);assert.match(html,/其他文档材料 · 1 份/);assert.equal((html.match(/data-action="attachment-preview"/g)||[]).length,2);assert.equal((html.match(/data-action="attachment-download"/g)||[]).length,3);
 const empty=render([],'历史材料请查看审核记录');assert.match(empty,/当前版本暂无证书图片/);assert.match(empty,/历史材料请查看审核记录/);assert.doesNotMatch(empty,/<img/);
 const documents=render([{id:'pdf',name:'扫描件.pdf',size:123}],'');assert.match(documents,/已上传的是文档材料/);assert.doesNotMatch(documents,/data-action="attachment-preview"/);
});

test('资质列表缩略图复用授权详情，仅取真实图片，读取失败可重试且不伪造缺图',async()=>{
 for(const mode of ['images','documents','error','detached']){
  const count={textContent:''},label={textContent:'预览图片'},image={dataset:{}},attrs={};
  const button={dataset:{id:'q'},isConnected:mode!=='detached',closest:()=>({querySelector:()=>count}),querySelector:selector=>selector==='img'?image:label,setAttribute:(key,value)=>attrs[key]=value,classList:{add(){}}};
  const e=engine(async()=>{if(mode==='error')throw Error('读取失败');return {qualification:{name:'真实证书'},attachments:mode==='images'?[{id:'a1',name:'正面.png'},{id:'a2',name:'背面.jpg'},{id:'a3',name:'附件.pdf'}]:[{id:'a3',name:'附件.pdf'}]}});
  e.ctx.previewRoot={querySelectorAll:()=>[button]};vm.runInContext('bindAttachmentPreviews=async()=>{globalThis.thumbnailBound=true}',e.ctx);
  await vm.runInContext('bindQualificationPreviews(previewRoot)',e.ctx);
  if(mode==='images'){assert.equal(image.dataset.materialId,'a1');assert.equal(count.textContent,'2 张图片 · 3 份材料');assert.equal(e.ctx.thumbnailBound,true);assert.match(attrs['aria-label'],/共 2 张/)}
  if(mode==='documents'){assert.equal(label.textContent,'暂无图片');assert.equal(button.dataset.action,'qualification');assert.equal(count.textContent,'另有 1 份文档材料')}
  if(mode==='error'){assert.match(count.textContent,/点击可重试/);assert.equal(label.textContent,'预览图片');assert.equal(image.dataset.materialId,undefined)}
  assert.equal(e.requests.length,mode==='detached'?0:1);assert.equal(e.requests.filter(r=>r.options.method!=='GET').length,0);
 }
});

test('从资质列表直接预览只打开当前版本图片，无图片时回到原详情',async()=>{
 for(const hasImages of [true,false]){
  const e=engine(async()=>({qualification:{id:'q',name:'测试资质'},attachments:hasImages?[{id:'a1',name:'正面.png'},{id:'pdf',name:'扫描.pdf'},{id:'a2',name:'背面.jpg'}]:[]}));
  vm.runInContext('openMaterialPreview=(items,start)=>{globalThis.previewed={items,start}};showQualification=async id=>{globalThis.detailReopened=id}',e.ctx);
  await vm.runInContext("qualificationImages('q')",e.ctx);
  if(hasImages){assert.deepEqual(Array.from(e.ctx.previewed.items,item=>item.id),['a1','a2']);assert.equal(e.ctx.previewed.start,0);assert.equal(e.ctx.detailReopened,undefined)}else assert.equal(e.ctx.detailReopened,'q');
  assert.equal(e.requests.length,1);assert.equal(e.requests[0].url,'/api/qualifications/q');
 }
});

test('资质图片返回时已切换页面，不弹出旧页面的图片',async()=>{
 let resolve;const e=engine(()=>new Promise(done=>{resolve=done}),'teacher');e.t.setState('qualifications');
 vm.runInContext('openMaterialPreview=()=>{globalThis.unwantedPreview=true}',e.ctx);
 const pending=vm.runInContext("qualificationImages('q')",e.ctx);e.t.setState('home');resolve({qualification:{id:'q'},attachments:[{id:'a',name:'证书.png'}]});await pending;assert.equal(e.ctx.unwantedPreview,undefined);
});

test('教师学分汇总保留每学年认定与待认定口径，空记录不出现无效分页',async()=>{
 const item={staff_no:'T1',school_year:'2025-2026',jw_credit:'2',cx_credit:'0',total_credit:'2',hours:'32',pending_credit:'1',pending_courses:1,courses:2,missing_credit:[],in_staff_table:true,user_id:'u'};
 for(const items of [[],[item]]){
  const e=engine(async()=>({items,years:['2025-2026'],total:items.length,page:1,size:20}),'teacher');e.t.setState('credits',{tab:'summary'});const html=await e.t.pages.credits();assert.doesNotMatch(html,/pagination/);assert.match(html,/社会培训项目积分在“教师积分激励”查看/);
  if(items.length){assert.match(html,/已认定学分/);assert.match(html,/待认定学分/);assert.match(html,/1 门待认定/);assert.match(html,/credit-detail/);}else assert.match(html,/暂无授课学分记录/);
 }
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

test('参训详情复用中文历史，显示一点二五改为零的原因依据且转义',async()=>{
 for(const legacy of [false,true]){
  const before={version:1,project:'合成<参训>',course:'合成课程',event_date:'2026-10-18',hours:'1.25',source:'学校登记',state:'VALID',teacher_id:'hidden-teacher'};
  const after={...before,version:2,hours:'0.00'};
  const events=[...(!legacy?[{action:'新增教师参训记录',before:{},after:before,reason:'初始登记',basis:'初始签到依据',created_at:'2026-10-18T01:00:00Z'}]:[]),
   {action:'更正教师参训记录',before,after,reason:'核对<签到>后更正为零',basis:'合成依据<script>第2号',created_at:'2026-10-18T02:00:00Z'}];
  const x={...after,id:'p',teacher_id:'teacher',events},e=engine(()=>x,'teacher'),original=JSON.stringify(events);
  e.t.setUser({user:{id:'teacher'},role:{kind:'teacher'},permissions:['records.read']});
  vm.runInContext('modal=(title,body,foot)=>{globalThis.partModal={title,body,foot}}',e.ctx);
  await e.t.handlers.participation('p');const html=e.ctx.partModal.body;
  for(const text of ['参训学时','1.25 学时','0 学时','第 1 版','第 2 版','核对&lt;签到&gt;后更正为零','合成依据&lt;script&gt;第2号'])assert.ok(html.includes(text),text);
  assert.doesNotMatch(html,/<签到>|<script>|teacher_id|hidden-teacher|授课学时|归属培训收入|data-json/);
  assert.doesNotMatch(e.ctx.partModal.foot,/更正参训记录/);assert.equal(JSON.stringify(events),original);
 }
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

test('组织规则入口按系统管理员权限分流，普通规则管理人仍可复制草稿',async()=>{
 const rule={id:'org',name:'组织规则',period_id:'p',target_kind:'dept',version:1,version_no:1,state:'DRAFT',config:{components:[]}};
 for(const admin of [false,true]){
  const e=engine(url=>({items:url.includes('organization-assessment-rules')?[rule]:[]}));e.t.setUser({user:{id:'u',is_admin:admin},role:{kind:'school'},permissions:['rules.manage']});e.t.setData([{id:'p',name:'周期',state:'OPEN'}]);
  const html=await e.t.pages.rules();assert.equal(html.includes('data-action="org-rule-form"'),admin);assert.match(html,/data-action="org-rule-copy"/);
  await e.t.handlers['org-rule']('org');const detail=e.node('#modal-root').innerHTML;
  assert.match(detail,/data-action="org-rule-copy"/);assert.equal(detail.includes('data-action="org-rule-trial"'),admin);assert.equal(detail.includes('data-action="org-rule-action"'),admin);
  if(!admin){
   assert.match(detail,/学校系统管理员办理/);
   for(const [action,id] of [['org-rule-form',''],['org-rule-trial','org'],['org-rule-action','activate|org']])await assert.rejects(e.t.handlers[action](id),/学校系统管理员/);
   assert.ok(e.requests.every(r=>r.options.method==='GET'));
   e.t.captureForm();await e.t.handlers['org-rule-copy']('org');assert.match(e.t.getForm().title,/复制/);
  }
 }
});

test('复制组织规则和新增指标复用评分方式显隐，切换分档保留原值',async()=>{
 const rule={id:'r',name:'合成规则',period_id:'p',target_kind:'dept',version:1,config:{components:[{key:'points',label:'积分',source:'points',weight:100,target:1}]}};
 const e=engine(()=>({items:[rule]}));e.t.setData([{id:'p',name:'周期',state:'OPEN'}]);e.t.captureForm();
 const makeRow=()=>{const fields=Object.fromEntries(['key','label','source','weight','target','method','tiers','tier_mode','base','unit','per_unit','floor','cap'].map(or=>[or,{dataset:{or},value:or==='method'?'':or==='tiers'?'0:20,10:100':'1',hidden:false,disabled:false}]));return {fields,querySelector:()=>fields.method,querySelectorAll:()=>Object.values(fields)}};
 const rows=[makeRow()];let change;const container=e.node('#org-rule-rows');container.querySelectorAll=()=>rows;container.addEventListener=(_event,handler)=>{change=handler};container.insertAdjacentHTML=()=>rows.push(makeRow());
 await e.t.handlers['org-rule-copy']('r');
 assert.equal(rows[0].fields.tiers.hidden,true);assert.equal(rows[0].fields.target.hidden,false);assert.equal(rows[0].fields.unit.disabled,true);
 rows[0].fields.method.value='tier';change();assert.equal(rows[0].fields.tiers.hidden,false);assert.equal(rows[0].fields.target.hidden,true);assert.equal(rows[0].fields.tiers.value,'0:20,10:100');
 e.t.handlers['org-rule-add']();assert.equal(rows.length,2);assert.equal(rows[1].fields.tiers.hidden,true);assert.equal(rows[1].fields.target.hidden,false);assert.equal(rows[1].fields.base.disabled,true);
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
test('导入须知与模板用途按权限显示，行数上限随当前配置同步更新',async()=>{
 for(const role of ['dept','college','school']){
  const e=engine(undefined,role);
  for(const limit of [1200,7500]){
   vm.runInContext(`businessConfig.import_max_rows=${limit}`,e.ctx);
   const html=await e.t.pages.imports(),cards=[...html.matchAll(/<button data-action="template" data-id="([^"]+)">([\s\S]*?)<\/button>/g)];
   assert.match(html,/导入填写须知：请使用当前下载的标准模板/);assert.match(html,/任一行校验未通过时，整批不入库/);
   assert.ok(html.includes(`当前页面单批上限为 ${limit} 行`));assert.doesNotMatch(html,/5000 行/);
   assert.deepEqual(cards.map(x=>x[1]),role==='school'?['records','participations','qualifications','teachers']:['records','participations','qualifications']);
   for(const card of cards)assert.ok(card[2].includes(`最多 ${limit} 行`));
   assert.match(cards.find(x=>x[1]==='records')[2],/项目备案、结项和积分认定仍需按流程办理/);
   assert.match(cards.find(x=>x[1]==='participations')[2],/作为学员参加培训的记录，不计入授课收入和授课人次/);
   assert.match(cards.find(x=>x[1]==='qualifications')[2],/由教师本人补充证明材料并提交审核/);
   if(role==='school')assert.match(cards.find(x=>x[1]==='teachers')[2],/停用待配置账号，管理员重置临时密码并启用后才能登录/);
  }
 }
});

test('三个模板下载沿用服务端文件名，与页面显示名称一致',async()=>{
 const e=engine(undefined,'dept'),downloads=[];
 e.ctx.captureTemplateDownload=(...args)=>downloads.push(args);
 vm.runInContext('download=captureTemplateDownload',e.ctx);
 for(const kind of ['records','participations','qualifications'])await e.t.handlers.template(kind);
 assert.deepEqual(downloads,[['/imports/templates/records'],['/imports/templates/participations'],['/imports/templates/qualifications']]);
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

test('teacher list loads every page so schools with more than 200 staff are all selectable',async()=>{
 const all=Array.from({length:450},(_,i)=>({id:'t'+i,name:'教师'+i,staff_no:String(1000+i)}));
 const e=engine(async url=>{const q=new URL(url,'http://x').searchParams,page=Number(q.get('page')||1),size=Number(q.get('size'));return {items:all.slice((page-1)*size,page*size),total:all.length,page,size}});
 const out=await vm.runInContext('loadAllTeachers',e.ctx)();
 assert.equal(out.items.length,450);assert.equal(out.items.at(-1).name,'教师449');assert.equal(e.requests.length,3);
 assert.ok(e.requests.every(r=>/size=200/.test(r.url)));
});
test('audit page shows data-changing operations by default and can switch to query logs',async()=>{
 const e=engine(async()=>({items:[],total:0,page:1,size:20}));e.t.setState('audit',{});
 let html=await e.t.pages.audit();assert.match(e.requests[0].url,/kind=change/);assert.match(html,/<option value="change" selected>改动数据的操作/);
 const f=engine(async()=>({items:[],total:0,page:1,size:20}));f.t.setState('audit',{kind:'all'});
 html=await f.t.pages.audit();assert.doesNotMatch(f.requests[0].url,/kind=/);assert.match(html,/<option value="all" selected>/);
});
test('browser technical errors are shown in plain Chinese while server messages pass through',()=>{
 const e=engine(),friendly=vm.runInContext('friendlyError',e.ctx);
 assert.equal(friendly(Error('版本冲突，请刷新')),'版本冲突，请刷新');
 const text=friendly(Object.assign(new TypeError("Cannot read properties of undefined (reading 'items')"),{requestId:'req-1'}));
 assert.match(text,/暂时没加载出来/);assert.match(text,/req-1/);assert.doesNotMatch(text,/Cannot read/);
});


test('教师考核保留本人流程并可从通知查看学院公示，管理角色仍可办学院考核',async()=>{
 const e=engine(async()=>({items:[],total:0,page:1,size:20}), 'teacher');
 e.t.setState('assessment');
 assert.equal(e.t.pageAllowed('annual'),true);
 assert.equal(e.t.pageAllowed('assessment'),true);
 const tabs=vm.runInContext("pageGroupTabs('assessment')",e.ctx);assert.match(tabs,/教师与组织考核/);assert.match(tabs,/学院年度考核/);
 const html=await e.t.pages.assessment();
 assert.doesNotMatch(html,/data-action="ranking-print"/);
 assert.match(html,/等待学校生成考核结果/);
 const admin=engine(undefined,'college');assert.equal(admin.t.pageAllowed('annual'),true);
 assert.match(vm.runInContext("pageGroupTabs('assessment')",admin.ctx),/学院年度考核/);
});

test('教师公示入口仍要求考核读取权限，通知日期使用统一北京时间',async()=>{
 const e=engine(async()=>({items:[{id:'notice',title:'合成公示',category:'年度考核公示',org_id:'college',body:'合成通知',created_at:'2026-10-17T22:10:00'}],total:1,page:1,size:20}),'teacher');e.t.setState('notices');
 let html=await e.t.pages.notices();assert.match(html,/学院考核公示/);assert.match(html,/data-action="nav" data-id="annual"/);assert.match(html,/2026\/10\/18 06:10:00/);assert.match(html,/datetime="2026-10-17T22:10:00"/);
 e.t.setUser({user:{id:'restricted'},role:{kind:'teacher'},permissions:['portal.read','notice.read']});assert.equal(e.t.pageAllowed('annual'),false);html=await e.t.pages.notices();assert.doesNotMatch(html,/data-id="annual"/);
});

test('教师积分零记录保留已认定口径，待审入口明确且不显示空分页',async()=>{
 const e=engine(async url=>url.includes('point-balances')?{items:[]}:{items:[],sum:0,total:0,page:1,size:20},'teacher');
 e.t.setState('points');const html=await e.t.pages.points();
 assert.match(html,/已认定积分/);assert.match(html,/尚无已认定流水/);assert.match(html,/data-id="recognition"/);
 assert.doesNotMatch(html,/class="pagination"|我的积分合计/);
});

test('本人授课表省去重复教师列，行内展开仍对应正确列数并保留零值',()=>{
 const e=engine(undefined,'teacher');
 const html=vm.runInContext('recordTable',e.ctx)([{id:'r',teacher_id:'u',event_date:'2026-10-17',project:'<项目>',hours:0,participants:0,income:0}]);
 assert.doesNotMatch(html,/>所属教师</);assert.match(html,/colspan="6"/);assert.match(html,/&lt;项目&gt;/);assert.match(html,/record-detail-0/);assert.match(html,/0.00/);
});


test('本人核对清单保留提交时间而省去重复姓名，单页只显示记录数',async()=>{
 const e=engine(async()=>({items:[{id:'d',created_at:'2026-10-17T00:00:00Z',teacher_id:'u',object_type:'record',reason:'待核对人次',state:'OPEN'}],total:1,page:1,size:20}),'teacher');
 e.t.setState('disputes');const html=await e.t.pages.disputes();
 assert.match(html,/>提交时间</);assert.doesNotMatch(html,/>教师</);assert.match(html,/2026/);assert.match(html,/等待授权人员核对/);assert.doesNotMatch(html,/class="pagination"/);
});

test('教师导出空页面只显示一个空状态并提供有权限的业务返回入口',async()=>{
 const e=engine(undefined,'teacher');e.t.setState('exports');const html=await e.t.pages.exports();
 assert.match(html,/还没有导出任务/);assert.doesNotMatch(html,/暂无记录|class="pagination"/);assert.match(html,/data-id="records"/);assert.match(html,/data-id="points"/);
});

test('学院复用教师待办与导出布局，保留学院教师身份且不误导本人确认',async()=>{
 const e=engine(undefined,'college');e.t.setData([],[{id:'t',name:'本院<教师>'}]);
 const rows=vm.runInContext('teacherTaskRows',e.ctx)([{id:'a',type:'assessment',title:'年度考核',teacher_id:'t',state:'COLLEGE'}]);
 assert.match(rows,/teacher-task-row|本院&lt;教师&gt;/);assert.match(rows,/按本级职责确认/);assert.doesNotMatch(rows,/请查看本人考核/);assert.match(rows,/assessment\|a/);
 e.t.setState('exports');const html=await e.t.pages.exports();assert.match(html,/本院培训数据/);assert.doesNotMatch(html,/我的培训数据|处理尝试|class="pagination"/);
 e.t.setState('points');const points=await e.t.pages.points();assert.match(points,/本院积分核对/);assert.match(points,/完整周期台账由教师本人确认/);assert.doesNotMatch(points,/再确认本人积分/);
 assert.match(e.t.pager({page:2,size:20,total:20}),/上一页/);
});


test('核对摘要复用原业务授权接口，同一记录只读一次，失败或无权限不伪造原值',async()=>{
 const e=engine(async()=>({record:{project:'<原项目>',event_date:'2026-10-17',hours:0,participants:0,income:0}}),'teacher');
 const load=vm.runInContext('disputeSourceSummaries',e.ctx),rows=[{object_type:'record',object_id:'r'},{object_type:'record',object_id:'r'}];
 const out=await load(rows);assert.equal(e.requests.length,1);assert.equal(out.get('record|r').title,'<原项目>');assert.match(out.get('record|r').summary,/0.00 学时 · 0 人次/);
 e.t.setUser({role:{kind:'teacher'},user:{id:'u'},permissions:['dispute.write']});assert.equal((await load(rows)).size,0);assert.equal(e.requests.length,1);
 const failed=engine(async()=>{throw Error('记录不可读')},'teacher');assert.equal((await vm.runInContext('disputeSourceSummaries',failed.ctx)(rows)).size,0);
});


test('只有一种待办类别时显示分类说明，有多个类别时才提供切换',()=>{
 const e=engine(undefined,'teacher'),chips=vm.runInContext('todoTeacherChips',e.ctx);
 assert.equal(chips({counts:{}}),'');
 const single=chips({counts:{social_resource:2}});assert.match(single,/积分核对与更正/);assert.doesNotMatch(single,/<button/);
 const multiple=chips({counts:{social_resource:2,assessment:1}});assert.match(multiple,/<button/);assert.match(multiple,/我的年度考核/);
});


test('资质状态切换保留关键词并回到第一页，查询表单保留当前状态',async()=>{
 const e=engine(async url=>url.includes('qualification-summary')?{items:[{key:'RETURNED',count:1}],total:1,expiry_days:30,note:'学校提醒口径'}:{items:[],total:0,page:1,size:20},'teacher');
 e.t.setState('qualifications',{q:'证书'},3);vm.runInContext('render=async()=>{}',e.ctx);
 await e.t.handlers['qualification-filter']('RETURNED');
 assert.equal(e.t.getState().filter.q,'证书');assert.equal(e.t.getState().filter.state,'RETURNED');assert.equal(e.t.getState().tablePage,1);
 const html=await e.t.pages.qualifications();assert.match(html,/name="state" value="RETURNED"/);assert.match(html,/data-id="RETURNED" aria-pressed="true"/);assert.doesNotMatch(html,/<select name="state"/);
 await e.t.handlers['qualification-filter']('EXPIRED');assert.equal(e.t.getState().filter.state,'RETURNED');
 assert.ok(e.requests.every(x=>x.options.method==='GET'));
});

test('本人待确认台账先于流水出现，确认仍绑定原台账，零分和负分不被格式改写',async()=>{
 const items=[{id:'p0',teacher_id:'u',kind:'MANUAL',item_key:'hours',amount:0},{id:'p1',teacher_id:'u',kind:'MANUAL',item_key:'hours',amount:-2}];
 const e=engine(async url=>url.includes('point-balances')?{items:[{id:'balance',teacher_id:'u',period_id:'period',confirmed:false}]}:{items,total:2,sum:-2,page:1,size:20},'teacher');
 e.t.setState('points');const html=await e.t.pages.points();
 assert.ok(html.indexOf('data-action="balance-action" data-id="balance"')<html.indexOf('积分流水与依据'));
 assert.match(html,/1 份待本人确认/);assert.match(html,/0.00<\/strong>/);assert.match(html,/-2.00/);assert.match(html,/确认范围/);
});

test('社会培训零分辅助流水保留可查，明细行与统计笔数一致',async()=>{
 const items=[{id:'teaching',teacher_id:'u',kind:'SOCIAL',item_key:'social_teaching',amount:'0.07'},{id:'auxiliary-zero',teacher_id:'u',kind:'SOCIAL',item_key:'social_auxiliary',amount:'0.00'}];
 const e=engine(async url=>url.includes('point-balances')?{items:[]}:{items,total:2,sum:'0.07',page:1,size:20},'teacher');
 e.t.setState('points');const html=await e.t.pages.points();
 assert.match(html,/社会培训授课积分/);assert.match(html,/社会培训辅助积分/);assert.match(html,/0.00<\/strong>/);assert.match(html,/data-id="auxiliary-zero"/);assert.match(html,/2 笔流水/);
});

test('教师通知使用阅读列表并转义标题与摘要，管理角色保留表格',async()=>{
 const answer={items:[{id:'n',title:'<学校通知>',body:'<script>alert(1)</script>',category:'业务通知',org_name:'<学院>',created_at:'2026-10-17T01:00:00Z'}],total:1,page:1,size:20};
 const e=engine(async()=>answer,'teacher');e.t.setState('notices');const html=await e.t.pages.notices();
 assert.match(html,/teacher-notice-item/);assert.match(html,/&lt;学校通知&gt;/);assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>|<table/);assert.match(html,/阅读通知/);
 const manager=engine(async()=>answer,'school');manager.t.setState('notices');assert.match(await manager.t.pages.notices(),/<table/);
});

test('教师证书详情仅保留一个业务标题，材料和历史记录仍完整可读',async()=>{
 const e=engine(async()=>({qualification:{id:'q',teacher_id:'u',name:'<证书>',category:'教学资质',state:'APPROVED',certificate_no:'Q1',issuer:'<机构>',obtained:'2026-01-01',expires:null,version:2},attachments:[],events:[],revisions:[]}), 'teacher');
 await e.t.handlers.qualification('q');const html=e.node('#modal-root').innerHTML;
 assert.equal((html.match(/<h2>/g)||[]).length,1);assert.match(html,/qualification-facts/);assert.match(html,/&lt;机构&gt;/);assert.match(html,/长期有效/);assert.match(html,/记录版本 2/);assert.match(html,/审核记录与历史版本/);
});


test('切换页面在最新渲染完成后回到顶部，旧请求和当前页筛选不打断滚动',async()=>{
 const e=engine(undefined,'teacher'),scrolls=[];e.ctx.window.scrollTo=(...args)=>scrolls.push(args);e.ctx.pendingRenders=[];
 vm.runInContext('render=()=>{renderSequence++;return new Promise(resolve=>pendingRenders.push(resolve))}',e.ctx);
 e.t.setState('mine');const old=e.t.nav('records'),latest=e.t.nav('points');
 e.ctx.pendingRenders.shift()();await old;assert.equal(scrolls.length,0);
 e.ctx.pendingRenders.shift()();await latest;assert.deepEqual(scrolls,[[0,0]]);
 const same=e.t.nav('points',{q:'核对'});e.ctx.pendingRenders.shift()();await same;assert.equal(scrolls.length,1);
});


test('教师按周期查询考核后保留展开的记录区，筛选名称对应本人环节',async()=>{
 const e=engine(async()=>({items:[],total:0,page:1,size:20}),'teacher');e.t.setState('assessment',{},1,1,'period');
 const html=await e.t.pages.assessment();assert.match(html,/<details class="teacher-assess-list" open>/);assert.match(html,/待我确认/);assert.match(html,/已过本人环节/);assert.doesNotMatch(html,/本级 =/);
});


test('选择材料只更新可读文件反馈，保留原帮助说明且不发送上传请求',async()=>{
 const e=engine(),created=[];e.ctx.document.createElement=()=>{const n={textContent:'',innerHTML:'',children:[],setAttribute(){},append(...items){this.children.push(...items)},replaceChildren(){this.children=[]},addEventListener(){}};created.push(n);return n};
 const input=e.node('file');input.id='f-file';input.files=[];input.isConnected=true;input.setAttribute('aria-describedby','file-help');let changed,status;
 input.addEventListener=(event,fn)=>{if(event==='change')changed=fn};input.insertAdjacentElement=(_where,node)=>{if(node.className==='file-selection-status')status=node};
 vm.runInContext('bindFileFeedback',e.ctx)({querySelectorAll:()=>[input]});
 assert.match(status.textContent,/尚未选择文件/);assert.equal(input.getAttribute('aria-describedby'),'file-help f-file-selection');
 input.files=[{name:'<认定表>.pdf',size:2048},{name:'说明.pdf',size:1024}];await changed();
 assert.match(status.textContent,/已选择 2 份文件/);assert.ok(created.some(x=>x.textContent==='<认定表>.pdf'));assert.ok(created.some(x=>x.textContent==='2.0 千字节'));assert.ok(created.every(x=>x.innerHTML===''));assert.equal(e.requests.length,0);
});

test('详情导航展开对应办理记录并转移焦点，不影响其他区域',()=>{
 const e=engine(),section={tagName:'DETAILS',open:false,focus(){this.focused=true},scrollIntoView(){this.scrolled=true}},button={dataset:{detailSection:'history'},addEventListener(_event,fn){this.click=fn}};
 e.ctx.document.getElementById=()=>section;
 vm.runInContext('bindDetailSections',e.ctx)({querySelectorAll:()=>[button],contains:s=>s===section});button.click();
 assert.equal(section.open,true);assert.equal(section.tabIndex,-1);assert.equal(section.focused,true);assert.equal(section.scrolled,true);
});


test('教师考核详情分区保留零分、核对阻塞和原始依据',async()=>{
 const detail={assessment:{id:'a1',teacher_id:'u',state:'TEACHER',score:0,detail:[{label:'指标<一>',raw:0,formula:'0 × 1',score:0}],source_snapshot:{}},teacher:{name:'合成教师'},period:{name:'合成周期'},rule:{name:'合成规则',version_no:1},events:[],confirmation_blockers:{count:1,can_view:true,can_resolve:false,items:[{id:'d1',object_type:'points',reason:'核对积分',created_at:'2026-10-01'}]}};
 const e=engine(async url=>url==='/api/assessments/a1'?detail:{items:[]},'teacher');e.t.setUser({user:{id:'u'},role:{kind:'teacher'},permissions:['assessment.read','assessment.confirm']});
 e.node('#modal-root .modal-body').insertAdjacentHTML=()=>{};await e.t.handlers.assessment('a1');const html=e.node('#modal-root').innerHTML;
 assert.match(html,/三级考核管理 \/ 考核详情/);assert.match(html,/data-detail-section="assessment-scores"/);assert.match(html,/id="assessment-history"/);assert.match(html,/&lt;一&gt;/);assert.match(html,/0.00/);assert.match(html,/查看核对进度/);assert.doesNotMatch(html,/data-action="assess-action"/);
});


test('普通计算积分不冒充社会培训申报归档，课程入库也不能由项目存在推断',async()=>{
 const e=engine(url=>url==='/api/applications/mine'?{items:[{type:'social_project',state:'DRAFT'}]}:url.startsWith('/api/social/mine')?{projects:[{state:'DRAFT'}],claims:[]}:{items:[],sum:20},'teacher');
 const html=await vm.runInContext('teacherFlow',e.ctx)(20);assert.equal((html.match(/暂无完成记录/g)||[]).length,4);assert.doesNotMatch(html,/class="done"/);
 const ready=engine(url=>url==='/api/applications/mine'?{items:[{flow:'teaching_course',state:'ACTIVE'}]}:{projects:[{state:'CLOSED'}],claims:[{state:'ARCHIVED',total:'0'}]},'teacher');
 const done=await vm.runInContext('teacherFlow',ready.ctx)();assert.equal((done.match(/已有完成记录/g)||[]).length,4);
});

test('教师导出详情按状态提供下一步，完成前不出现下载按钮',async()=>{
 for(const state of ['QUEUED','DONE','FAILED']){
  const e=engine(()=>({task:{id:'export',kind:'export',state,result:{count:0,size:10}},attempts:[]}),'teacher');
  await e.t.handlers.task('export');const html=e.node('#modal-root').innerHTML;assert.match(html,/导出下载 \/ 文件详情/);assert.match(html,/查看处理记录/);assert.equal(html.includes('data-action="task-download"'),state==='DONE');
  if(state==='QUEUED')assert.match(html,/正在排队/);if(state==='FAILED')assert.match(html,/重新生成/);
 }
});


test('教师已归档周期积分显示只读，不能误导进入本人确认',async()=>{
 const e=engine(url=>url.includes('point-balances')?{items:[{id:'b',teacher_id:'u',period_id:'p',confirmed:false,locked:true,lock_reason:'考核已归档，该周期积分只读'}]}:{items:[],total:0,sum:0},'teacher');e.t.setUser({user:{id:'u'},role:{kind:'teacher'},permissions:['points.read']});e.t.setState('points');
 const html=await e.t.pages.points();assert.match(html,/只读冻结/);assert.match(html,/考核已归档，该周期积分只读/);assert.doesNotMatch(html,/data-action="balance-action"/);assert.throws(()=>e.t.handlers['balance-action']('b'),/只读/);
});


test('整页表单键盘进入其他分区时，导航跟随焦点且不改填写值',()=>{
 const e=engine(),buttons=[],listeners={};let nav;
 const group=title=>({querySelector:()=>({textContent:title}),focus(){},scrollIntoView(){}}),groups=[group('基本资料'),group('申报说明')];
 e.ctx.document.createElement=tag=>tag==='nav'?(nav={setAttribute(){},append(b){buttons.push(b)},querySelectorAll(){return buttons}}):{classList:{toggle(key,value){this[key]=value}},setAttribute(key,value){this[key]=value},addEventListener(){}};
 const form={querySelectorAll:()=>groups,prepend(){},addEventListener:(type,fn)=>{listeners[type]=fn}};
 vm.runInContext('bindPageFormSections',e.ctx)(form);const input={value:'原内容',closest:()=>groups[1]};listeners.focusin({target:input});
 assert.equal(buttons[1]['aria-current'],'step');assert.equal(buttons[0]['aria-current'],'false');assert.equal(input.value,'原内容');
});


test('详情更多操作按退出键只收起菜单并返回焦点',()=>{
 const e=engine(),menu=e.node('#modal-root .detail-more-actions');let handler,stopped=false,focused=false;menu.open=true;menu.addEventListener=(_event,fn)=>{handler=fn};menu.querySelector=()=>({focus(){focused=true}});
 vm.runInContext('modal',e.ctx)('详情','正文','操作');handler({key:'Escape',stopPropagation(){stopped=true}});assert.equal(menu.open,false);assert.equal(focused,true);assert.equal(stopped,true);assert.equal(e.node('#modal-root').classList.contains('hidden'),false);
});


test('教研室资质详情突出证书与审核，保留教师归属和当前权限',async()=>{
 const d={qualification:{id:'q',teacher_id:'t',category:'职业资格',name:'证书<一>',certificate_no:'CERT',issuer:'隔离机构',obtained:'2026-01-01',expires:null,state:'SUBMITTED',version:2},attachments:[],events:[],revisions:[]};
 const e=engine(()=>d,'dept');e.t.setUser({user:{id:'u'},role:{kind:'dept'},permissions:['qualification.read','qualification.review']});e.t.setData([],[{id:'t',name:'本室教师'}]);await e.t.handlers.qualification('q');const html=e.node('#modal-root').innerHTML;
 assert.match(html,/qualification-detail-content/);assert.match(html,/本室教师 · 职业资格/);assert.match(html,/请核验证书/);assert.match(html,/审核通过/);assert.match(html,/退回补充/);assert.doesNotMatch(html,/data-action="qualification-form"/);
});

test('教研室查看他人参训不会写成本人，积分指引说明教师本人确认',async()=>{
 const e=engine(url=>url.includes('/participations/')?{teacher_id:'t',project:'参训项目',course:'参训课程',hours:0,event_date:'2026-10-01',source:'学校登记',version:1,external_key:'internal'}:url.includes('point-balances')?{items:[]}:{items:[],sum:0,total:0,page:1,size:20},'dept');e.t.setData([],[{id:'t',name:'本室教师'}]);await e.t.handlers.participation('part');const detail=e.node('#modal-root').innerHTML;assert.match(detail,/本室教师作为学员/);assert.doesNotMatch(detail,/本人作为学员/);
 e.t.setState('points');const html=await e.t.pages.points();assert.match(html,/本室积分核对/);assert.match(html,/完整周期台账由教师本人确认/);
});

test('教研室组织考核可按分区核对，主操作仍限定本组织且非生成人',async()=>{
 const d={assessment:{id:'oa',target_id:'d1',target_kind:'dept',state:'GENERATED',generated_by:'school',score:0,version:1,source_snapshot:{}},target:{name:'本教研室'},period:{name:'测试周期'},rule:{name:'测试规则',version_no:1},evidence:[],events:[]};
 const e=engine(url=>url.includes('/attachments?')?{items:[]}:d,'dept');e.t.setUser({user:{id:'u',org_id:'d1'},role:{kind:'dept'},permissions:['assessment.read','assessment.review']});e.node('#modal-root .modal-body').insertAdjacentHTML=()=>{};
 await e.t.handlers['org-assessment']('oa');let html=e.node('#modal-root').innerHTML;assert.match(html,/org-assessment-scores/);assert.match(html,/org-assessment-history/);assert.match(html,/组织复核/);
 d.assessment.generated_by='u';await e.t.handlers['org-assessment']('oa');html=e.node('#modal-root').innerHTML;assert.doesNotMatch(html,/data-action="org-assessment-action"/);
});


test('教研室待办不显示全空批量列，仍可筛选实际事项及保留可批量的操作',async()=>{
 for(const supported of [false,true]){
  const item=supported?{type:'assessment',id:'a',title:'本级考核确认',state:'DEPARTMENT',teacher_id:'t'}:{type:'qualification',id:'q',title:'资质审核',state:'SUBMITTED',teacher_id:'t'};
  const e=engine(()=>({items:[item],counts:{qualification:supported?0:1,assessment:supported?1:0,sync:0},total:1,page:1,size:20}),'dept');e.t.setState('todos');const html=await e.t.pages.todos();
  assert.equal(html.includes('batch-pick'),supported);assert.equal(/<th[^>]*>选择<\/th>/.test(html),supported);assert.doesNotMatch(html,/<option value="sync">/);assert.doesNotMatch(html,/上一页/);
 }
});


test('教研室在后页办理后总数缩小时仍能返回上一页',()=>{
 const e=engine(undefined,'dept'),html=e.t.pager({page:2,size:20,total:20});assert.match(html,/上一页/);assert.match(html,/data-action="prev"/);
});


test('教研室导入预览按业务名称显示并保留零值，未知内部字段不直出',()=>{
 const e=engine(undefined,'dept'),html=vm.runInContext('importRowPreview',e.ctx)({'项目名称':'隔离<项目>','教师工号':'J001','授课学时':2,'归属培训收入':0,'数据来源':'Excel导入',internal_secret:'do-not-show'});
 assert.match(html,/隔离&lt;项目&gt;/);assert.match(html,/归属培训收入：0/);assert.match(html,/查看本行完整字段/);assert.match(html,/表格导入/);assert.doesNotMatch(html,/internal_secret|do-not-show|<项目>/);
});


test('学校学院教研室共用中文导入预览与明确的文件行数确认',async()=>{
 for(const role of ['school','college','dept']){
  const raw=role==='school'?{'姓名':'合成<教师>','登录账号':'r4_import_test','教师工号':'J900','组织编码':'dept1',internal_secret:'do-not-show'}:{'项目名称':'合成<项目>','教师工号':'J001','授课学时':0,internal_secret:'do-not-show'};
  const job={id:'shared-import',filename:'合成<导入>.xlsx',kind:role==='school'?'teachers':'records',state:'PREVIEW',total:1,errors:0,sha256:'a'.repeat(64),version:7};
  const e=engine(()=>({job,rows:{items:[{row_no:2,payload:{raw},errors:[]}],page:1,size:30,total:1}}),role);
  await e.t.handlers.import('shared-import');const html=e.node('#modal-root').innerHTML,visible=customerVisible(html);
  assert.match(html,/导入内容/);assert.match(html,/查看本行完整字段/);assert.doesNotMatch(html,/实施人员使用|文件校验|a{64}/);assert.doesNotMatch(visible,/a{16}|原始字段/);assert.doesNotMatch(html,/internal_secret|do-not-show/);
  if(role==='school'){assert.match(visible,/登录账号：r4_import_test/);assert.match(visible,/组织编码：dept1/)}else assert.match(visible,/授课学时：0/);
  e.t.captureForm();await e.t.handlers['import-confirm']('shared-import');const form=e.t.getForm();
  assert.match(form.body,/本次导入文件/);assert.match(form.body,/合成&lt;导入&gt;.xlsx/);assert.match(form.body,/共 1 行/);assert.equal(form.options.contextLabel,'表格导入 / 确认入库');assert.equal(typeof form.options.returnTo,'function');
  assert.equal(e.requests.filter(x=>x.options.method==='POST').length,0);
 }
});


test('教研室考核办理表单显示教师和周期，积分核对未完成时只提供进度入口',async()=>{
 const d={assessment:{id:'a',teacher_id:'t',period_id:'p',state:'DEPARTMENT',score:0,version:4,detail:[],source_snapshot:{}},teacher:{name:'教师<一>'},period:{name:'周期<一>'},rule:{name:'规则',version_no:1},events:[]};
 const e=engine(url=>url.includes('/attachments?')?{items:[]}:d,'dept');e.t.setUser({user:{id:'u'},role:{kind:'dept'},permissions:['assessment.read','assessment.review','points.read']});e.node('#modal-root .modal-body').insertAdjacentHTML=()=>{};
 e.t.captureForm();await e.t.handlers['assess-action']('confirm|a');const form=e.t.getForm();assert.match(form.body,/教师&lt;一&gt; · 周期&lt;一&gt;/);assert.match(form.body,/0.00 分/);assert.equal(form.options.contextLabel,'教师考核 / 本级办理');
 d.open_point_reviews=1;await e.t.handlers.assessment('a');const html=e.node('#modal-root').innerHTML;assert.match(html,/查看积分核对/);assert.match(html,/data-action="search-nav" data-id="recognition"/);assert.doesNotMatch(html,/data-id="confirm\|a"/);
});

test('教师本人和学校考核确认共用明确的对象周期得分提示',async()=>{
 for(const [role,state] of [['teacher','TEACHER'],['school','SCHOOL']]){
  const d={assessment:{id:'a',teacher_id:'t',period_id:'p',state,score:0,version:4,detail:[],source_snapshot:{}},teacher:{name:'教师<一>'},period:{name:'周期<一>'},rule:{name:'规则',version_no:1},events:[]};
  const e=engine(()=>d,role);e.t.captureForm();await e.t.handlers['assess-action']('confirm|a');const form=e.t.getForm();
  assert.match(form.body,/本次办理考核/);assert.match(form.body,/教师&lt;一&gt; · 周期&lt;一&gt;/);assert.match(form.body,/0.00 分/);assert.doesNotMatch(form.body,/<一>/);
 }
});

test('组织考核详情各阶段明确当前环节，学校归档复用对象周期得分提示',async()=>{
 for(const [state,name] of [['GENERATED','待组织复核'],['REVIEWED','待学校审核'],['SCHOOL_APPROVED','待归档'],['ARCHIVED','已归档']]){
  const d={assessment:{id:'org',target_id:'college',target_kind:'college',state,score:0,version:3,source_snapshot:{}},target:{name:'学院<一>'},period:{name:'周期<一>'},rule:{name:'合成规则',version_no:1},evidence:[],events:[]};
  const e=engine(url=>url.includes('/attachments?')?{items:[]}:d);e.node('#modal-root .modal-body').insertAdjacentHTML=()=>{};await vm.runInContext("showOrgAssessment('org')",e.ctx);assert.ok(e.node('#modal-root').innerHTML.includes('当前环节：'+name),state);
  if(state==='SCHOOL_APPROVED'){
   e.t.captureForm();await e.t.handlers['org-assessment-action']('archive|org');const form=e.t.getForm();
   assert.match(form.body,/学院&lt;一&gt; · 周期&lt;一&gt;/);assert.match(form.body,/0.00 分/);assert.match(form.body,/归档后结果及依据将冻结/);assert.equal(form.options.contextLabel,'组织考核 / 本级办理');
  }
 }
});

test('组织考核快捷筛选说明使用组织复核，跨角色切换先校正当前分区',async()=>{
 for(const [role,tab] of [['dept','dept'],['college','college'],['school','school']]){
  const e=engine(()=>({items:[],total:0,page:1,size:20}),role);e.t.setState('assessment',{tab});
  const html=await e.t.pages.assessment();assert.match(html,role==='school'?/本级 = 学校组织复核、审核与归档环节/:/本级 = 本组织复核环节/);
 }
 const e=engine(()=>({items:[],total:0,page:1,size:20}),'dept');e.t.setState('assessment',{tab:'school'});
 const html=await e.t.pages.assessment();assert.match(html,/本级 = 教研室确认环节/);assert.doesNotMatch(html,/本级 = 本组织复核环节/);
});

test('组织考核补材料后仍直接显示学校退回复核原因',async()=>{
 const d={assessment:{id:'org',target_id:'dept',target_kind:'dept',state:'GENERATED',score:8,version:3,source_snapshot:{}},target:{name:'教研室'},period:{name:'周期'},rule:{name:'规则',version_no:1},returned:true,evidence:[],events:[{action:'退回组织考核复核',reason:'请补说明<核对>'},{action:'上传组织考核佐证材料',reason:'材料已补'}]};
 const e=engine(url=>url.includes('/attachments?')?{items:[]}:d,'dept');e.node('#modal-root .modal-body').insertAdjacentHTML=()=>{};
 await vm.runInContext("showOrgAssessment('org')",e.ctx);const html=e.node('#modal-root').innerHTML;
 assert.match(html,/退回意见：请补说明&lt;核对&gt;/);assert.doesNotMatch(html,/退回意见：材料已补/);assert.doesNotMatch(html,/<核对>/);
});


test('教研室导出详情突出下载状态并折叠处理记录',async()=>{
 const e=engine(()=>({task:{id:'export',kind:'export',state:'DONE',result:{size:10}},attempts:[]}),'dept');await e.t.handlers.task('export');const html=e.node('#modal-root').innerHTML;assert.match(html,/导出文件详情/);assert.match(html,/查看处理记录/);assert.match(html,/下载结果/);
});


test('审批中心三分区复用原单并显示具体事项与周期，教师仍读本人待办',async()=>{
 const item={type:'qualification',id:'q',title:'资质审核',business_name:'证书<甲>',business_type_label:'教师资质',owner_name:'张<老师>',staff_no:'J001',org_name:'本室',period_name:'2026周期',state:'SUBMITTED',state_label:'待审核',entered_at:'2026-10-18T01:00:00',action_label:'查看并办理'};
 const e=engine(()=>({items:[item],total:1,page:1,size:20,counts:{qualification:1},stages:['SUBMITTED'],can_archive:false}),'college');e.t.setState('todos');const html=await e.t.pages.todos();
 assert.match(e.requests[0].url,/approval-center/);for(const text of ['待我办理','我已办理','我发起的','证书&lt;甲&gt;','张&lt;老师&gt;','J001','2026周期','进入本环节'])assert.ok(html.includes(text),text);
 assert.doesNotMatch(html,/待归档清单|batch-pick|所选审批操作|<甲>|张<老师>/);assert.match(html,/name="state"/);assert.match(html,/name="period_id"/);
 const t=engine(()=>({items:[],total:0,page:1,size:20,counts:{},attention_counts:{}}),'teacher');await t.t.pages.todos();assert.match(t.requests[0].url,/todos.*attention=handle/);assert.doesNotMatch(t.requests[0].url,/approval-center/);
});

test('已办分区可从地址恢复，保留我的动作并不出现审批勾选',async()=>{
 const e=engine(()=>({items:[{type:'assessment',id:'a',business_name:'本人已办<原单>',title:'教师考核',teacher_id:'t',state:'待学校审核',my_action:'学院<确认>',handled_at:'2026-10-18T02:00:00'}],total:1,page:2,size:20,counts:{assessment:1},stages:['待学校审核']}),'college');e.t.setState('todos',{tab:'handled',q:'J001'},2);
 const html=await e.t.pages.todos();assert.match(e.requests[0].url,/tab=handled/);assert.match(e.requests[0].url,/page=2/);assert.match(html,/学院&lt;确认&gt;/);assert.match(html,/本级完成不等于整单办结/);assert.doesNotMatch(html,/batch-pick|data-action="todo-batch"/);
});

test('审批批量条默认收起，等待公示期限单独展示且不冒称可办理',async()=>{
 const item={type:'social_claim',id:'claim',title:'社会培训积分认定',teacher_id:'t',state:'待院长初审'};
 const e=engine(()=>({items:[item],total:1,page:1,size:20,counts:{social_claim:1},stages:[],waiting:1,waiting_items:[{type:'social_resource',id:'report',business_name:'年度公示',action_hint:'公示截止2026-10-23，完整期满后才能归档'}]}),'college');e.t.setState('todos');const html=await e.t.pages.todos();
 assert.match(html,/batch-bar" hidden/);assert.match(html,/等待条件的事项/);assert.match(html,/2026-10-23/);assert.match(html,/data-id="social_resource\|report"/);assert.match(html,/不计入当前可办理数量/);
});


test('直接进入审批中心默认待我办理，不继承前一账号已办分区',async()=>{
 const e=engine(()=>({items:[],total:0,page:1,size:20,counts:{},stages:[]}),'college');vm.runInContext("todoTab='handled'",e.ctx);e.t.setState('todos');await e.t.pages.todos();assert.match(e.requests[0].url,/tab=handle(?:&|$)/);assert.doesNotMatch(e.requests[0].url,/tab=handled/);
});


test('业务依据的时间用统一本地格式，业务日期、名称和零值保持原样',()=>{
 const html=engine().t.evidenceHtml({period:{name:'2026-10-18T15:37:42Z',created_at:'2026-10-18T15:37:42.926330',start_date:'2026-01-01'},hours:0,id:'hidden-id'});
 assert.match(html,/2026\/10\/18 23:37:42/);assert.match(html,/2026-01-01/);assert.match(html,/2026-10-18T15:37:42Z/);assert.match(html,/>0</);assert.doesNotMatch(html,/926330|hidden-id/);assert.match(engine().t.evidenceHtml({created_at:'2026-99-18T15:37:42'}),/2026-99-18T15:37:42/);
});


test('积分流水显示同项目原认定和更正的中文来源，来源文字安全转义',async()=>{
 const items=[{id:'original',teacher_id:'u',kind:'SOCIAL',item_key:'social_teaching',amount:'1.00',project_name:'<合成项目>',project_code:'QA-SAFE'},
 {id:'fix',teacher_id:'u',kind:'SOCIAL',item_key:'social_fix_teaching',source_snapshot:{correction_id:'fix'},amount:'0.10',project_name:'<合成项目>',project_code:'QA-SAFE'}];
 const e=engine(async url=>url.includes('point-balances')?{items:[]}:{items,total:2,sum:'1.10',page:1,size:20},'teacher');
 e.t.setState('points');const html=await e.t.pages.points();
 assert.equal((html.match(/&lt;合成项目&gt; · QA-SAFE/g)||[]).length,2);
 assert.match(html,/1.10/);assert.match(html,/社会培训授课积分更正/);assert.doesNotMatch(html,/<合成项目>/);
});
