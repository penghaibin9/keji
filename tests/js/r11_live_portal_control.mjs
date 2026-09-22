// Executed explicitly by run_r11_portal_control.py, not part of node --test *.test.mjs.
import fs from 'node:fs';import path from 'node:path';import vm from 'node:vm';import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import * as ui from '../../frontend/portal-ui.js';import * as scope from '../../frontend/scope.js';import {icons} from '../../frontend/icons.js';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const [origin,output]=process.argv.slice(2);if(!/^http:\/\/127\.0\.0\.1:\d+$/.test(origin||''))throw Error('Only explicitly isolated loopback service is allowed');
fs.mkdirSync(output,{recursive:true});const snapshots=path.join(output,'rendered');fs.mkdirSync(snapshots,{recursive:true});
const original=fs.readFileSync(path.join(root,'frontend/app.js'),'utf8');
const log=[],checks=[],pagesTested=[],jars=new Map();let activeJar='schooladmin';
const nodes=new Map();function node(id){if(!nodes.has(id))nodes.set(id,{innerHTML:'',textContent:'',value:'',disabled:false,isConnected:true,classList:{add(){},remove(){},toggle(){}},addEventListener(){},append(){},querySelector(){return null},querySelectorAll(){return []},focus(){}});return nodes.get(id)}
const c=vm.createContext({console,...ui,...scope,icons,URL,URLSearchParams,Blob,FormData,crypto:globalThis.crypto,setTimeout:()=>0,clearTimeout(){},document:{querySelector:node,querySelectorAll:()=>[],createElement:()=>({click(){},remove(){}}),addEventListener(){},body:node('body')},window:{addEventListener(){}},location:{hash:'',pathname:'/',search:''},history:{replaceState(){}},
 fetch:async(url,opts)=>{
   if(!url.startsWith('/api/'))throw Error('Unexpected external request');
   let jar=jars.get(activeJar);if(!jar){jar=new Map();jars.set(activeJar,jar)}
   const headers={...opts.headers,Origin:origin};if(jar.size)headers.Cookie=[...jar].map(([k,v])=>k+'='+v).join('; ');
   const response=await fetch(origin+url,{...opts,headers,redirect:'error'});
   for(const cookie of response.headers.getSetCookie()){const pair=cookie.split(';')[0],i=pair.indexOf('=');jar.set(pair.slice(0,i),pair.slice(i+1));}
   log.push({method:opts.method,url,status:response.status});return response;
 }});
vm.runInContext(original.replace(/^import .*?;\n/gm,'').replace(/\(async\(\)=>\{try\{await boot\(\)\}[\s\S]*$/,'')+`
globalThis.T={api,pages,handlers,shell,loginView,pageAllowed,connectionForm,mappingEditor,showInbound,showTask,showSyncItem,
 setUser(user){me=user;csrf=user.csrf},setPage(p,f={},n=1){page=p;filter=f;tablePage=n;participationPage=1;periodId=''},
 setData(p,t,o,d){periods=p;teachers=t;orgs=o;businessConfig=d},captureForm(){formModal=(title,body,callback,options)=>{globalThis.F={title,body,callback,options}}},getForm(){return globalThis.F}, getView(){return view}};`,c);
const t=c.T;const password='FixtureOnly_2026_Local'; // Isolated fixture only, never production init credentials.
async function login(username){activeJar=username;await t.api('/auth/login',{method:'POST',body:{username,password}});const user=await t.api('/auth/me');t.setUser(user);const [p,u,o,d]=await Promise.all([t.api('/periods'),t.api('/teachers?size=200'),t.api('/organizations'),t.api('/dictionaries')]);t.setData(p.items,u.items,o.items,d);return user}
function saveSnapshot(key,html){t.shell();let shell=node('#app').innerHTML;shell=shell.replace('<main id="content" class="content"></main>','<main id="content" class="content">'+html+'</main>');const css=['styles.css','integration.css','portal.css'].map(f=>fs.readFileSync(path.join(root,'frontend',f),'utf8')).join('\n');fs.writeFileSync(path.join(snapshots,key+'.html'),'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>R11真实渲染 · 合成数据</title><style>'+css+'</style></head><body>'+shell+'</body></html>');}
try{
 for(const user of ['schooladmin','teacher','depthead','collegehead']){
  await login(user);
  for(const page of Object.keys(t.pages)){
   if(!t.pageAllowed(page))continue;
   t.setPage(page);const start=log.length;
   const html=await t.pages[page]();assert.equal(typeof html,'string');assert.ok(!html.includes('SAMPLE-001'));assert.ok(!html.includes('教师 undefined'));
   pagesTested.push({user,page,requests:log.slice(start).length,status:'PASS'});
   if((user==='schooladmin'&&['home','sync','sso','hub','province','guide','assessment','qualifications','records'].includes(page))||(page==='home'&&user!=='schooladmin'))saveSnapshot(user+'_'+page,html);
  }
 }
 checks.push({id:'four-role-live-pages',status:'PASS',pages:pagesTested.length});
 await login('schooladmin');
 for(const [page,tabs] of [['sso',['mappings','proof']],['hub',['mappings','batches','tasks','schedules','proof']],['province',['mappings','tasks','items','proof']]]){
  for(const tab of tabs){t.setPage(page,{tab},2);const html=await t.pages[page]();assert.ok(html.includes('第 2 页')||['mappings','proof'].includes(tab));pagesTested.push({user:'schooladmin',page,tab,status:'PASS'});}
 }
 checks.push({id:'all-integration-tabs-live',status:'PASS'});
 const connections=(await t.api('/connections/catalog')).items;const middle=connections.find(x=>x.connection.code==='middle').connection;
 // Actual parameter form callback retains version, reason, CSRF and the current connection ID.
 t.setPage('hub');t.captureForm();await t.connectionForm(middle.id);
 const form=t.getForm();assert.ok(form.body.includes('[]'));assert.ok(!form.body.includes('teacher_no'));
 await form.callback({endpoint:'',owner:'R11隔离联调负责人',auth_mode:'',retry_count:3,secret_env:'',frequency_minutes:30,mappings:'[]',reason:'仅隔离控制登记',basis:'合成样本'});
 const after=(await t.api('/connections/catalog')).items.find(x=>x.connection.id===middle.id).connection;
 assert.equal(after.config.owner,'R11隔离联调负责人');assert.equal(after.state,'NOT_CONNECTED');assert.equal(after.version,middle.version+1);
 checks.push({id:'actual-connection-form-save-readback',status:'PASS'});
 const probe=await t.api('/connections/'+middle.id+'/probe',{method:'POST',body:{expected_version:after.version,reason:'验证缺少真实适配器',basis:'合成控制'}});
 assert.equal(probe.check.passed,false);assert.equal(probe.connection.state,'NOT_CONNECTED');
 t.setPage('hub',{tab:'proof'});const proofHtml=await t.pages.hub();assert.ok(proofHtml.includes(probe.check.reason_code));saveSnapshot('schooladmin_hub_proof',proofHtml);
 checks.push({id:'missing-adapter-is-not-success',status:'PASS',reason_code:probe.check.reason_code});
 // Actual inbound preview UI fetch, configure official fields then confirm through the existing handler.
 const current=(await t.api('/connections/catalog')).items.find(x=>x.connection.id===middle.id).connection;
 const mappings=[{data_type:'training_project',source:'code',target:'code',transform:'text',required:true,default:null},{data_type:'training_project',source:'name',target:'name',transform:'text',required:true,default:null}];
 await t.api('/connections/'+middle.id,{method:'PUT',body:{expected_version:current.version,config:current.config,mappings,reason:'合成项目字段对应',basis:'不代表学校协议'}});
 const batch=await t.api('/connections/'+middle.id+'/inbound/preview',{method:'POST',body:{data_type:'training_project',source_label:'R11合成控制项目',records:[{code:'R11-TEST-P',name:'R11隔离联调项目'}],reason:'预览控制',basis:'合成数据'}});
 assert.equal(batch.errors,0);await t.showInbound(batch.id);assert.ok(node('#modal-root').innerHTML.includes('确认写入主数据'));
 await t.handlers['inbound-confirm'](batch.id);await t.getForm().callback({reason:'明确确认合成项目入库',basis:'R11控制'});
 const committed=await t.api('/inbound-batches/'+batch.id);assert.equal(committed.batch.state,'COMMITTED');
 t.setPage('hub',{tab:'batches'});const list=await t.pages.hub();assert.ok(list.includes('已入库'));saveSnapshot('schooladmin_hub_batches',list);
 checks.push({id:'actual-inbound-confirm-handler-and-readback',status:'PASS'});
 await login('teacher');const before=log.length;await assert.rejects(()=>t.api('/inbound-batches'),/无权|权限|管理员/);assert.equal(log.at(-1).status,403);
 await assert.rejects(()=>t.api('/tasks?kind=integration'),/无权|权限/);assert.equal(log.at(-1).status,403);
 checks.push({id:'teacher-direct-access-denied',status:'PASS'});
 const report={status:'PASS',boundary:'Actual UI module renderers + existing API/form callbacks over real loopback HTTP; isolated SQLite synthetic fixtures; not native browser, MySQL, TLS or school acceptance.',checks,pages:pagesTested,requests:log};
 fs.writeFileSync(path.join(output,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({status:report.status,checks:checks.length,pages:pagesTested.length,requests:log.length},null,2));
}catch(e){fs.writeFileSync(path.join(output,'report.json'),JSON.stringify({status:'FAILED',error:e.stack,checks,pages:pagesTested,requests:log},null,2));console.error(e.stack);process.exitCode=1;}
