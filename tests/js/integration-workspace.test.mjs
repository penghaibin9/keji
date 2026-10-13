import test from 'node:test';
import assert from 'node:assert/strict';
import {renderImplementationWorkspace,renderSsoMaintenance,handleImplementationAction} from '../../frontend/integration-workspace.js';

test('统一登录日常维护按服务端证明显示动作，测试记录不显示开通按钮',async()=>{
 const w={connection_version:2,draft_version:1,code:'sso',available:false,can_publish:false,has_draft:true,issues:[],callbacks:{login:'https://school.invalid/callback'},check:{mode:'TEST_ONLY',passed:true}};
 const c={api:async()=>w,esc:x=>String(x??''),note:String,table:()=>'',act:(label,action)=>`<button data-action="${action}">${label}</button>`};
 let html=await renderSsoMaintenance('sso',c);assert.match(html,/本地测试记录/);assert.doesNotMatch(html,/data-action="impl-quick-publish"/);
 w.can_publish=true;w.check.mode='REAL';html=await renderSsoMaintenance('sso',c);assert.match(html,/data-action="impl-quick-publish"/);
 w.can_publish=false;w.available=true;html=await renderSsoMaintenance('sso',c);assert.match(html,/已开通/);assert.match(html,/impl-quick-disable/);
 assert.doesNotMatch(html,/confirm_schedule_pause|办理意见/);
});

test('试登录自动准备候选但不跳过版本校验或自动发布',async()=>{
 const requests=[];const c={api:async(url,options)=>{requests.push({url,options});if(url.endsWith('/implementation'))return {connection_version:4,issues:[]};if(url.endsWith('/prepare'))return {connection_version:4,draft_version:3};return {}}};
 await handleImplementationAction('impl-quick-trial','sso',c);
 assert.deepEqual(requests.map(r=>r.url),['/connections/sso/implementation','/connections/sso/draft/prepare','/connections/sso/draft/login-test']);
 assert.equal(requests[2].options.body.draft_version,3);assert.equal(requests[2].options.body.expected_version,4);
});

test('版本冲突只刷新状态，不重放试登录或覆盖草稿',async()=>{
 let reads=0,writes=0,renders=0,notice='';const c={api:async(_url,options)=>{if(!options){reads++;return {connection_version:1,issues:[]}}writes++;throw Object.assign(Error('原草稿待核对'),{status:409})},render:async()=>{renders++},toast:message=>{notice=message}};
 await handleImplementationAction('impl-quick-trial','sso',c);
 assert.equal(reads,1);assert.equal(writes,1);assert.equal(renders,1);assert.match(notice,/未被覆盖/);
});

test('只有统一认证显示登录回调，业务接口说明按用途区分',async()=>{
 for(const code of ['sso','middle','province']){
  const w={code,statuses:{},source_gaps:[],credential:{},callbacks:{login:'LOGIN_CALLBACK',test_login:'TEST_CALLBACK',logout_return:'LOGOUT_RETURN'}};
  const c={api:async()=>w,esc:x=>String(x??''),note:x=>x,table:(h,r)=>JSON.stringify([h,r]),act:(label)=>label};
  const credential=await renderImplementationWorkspace('fixture','credentials',c);
  if(code==='sso')assert.match(credential,/LOGIN_CALLBACK/);
  else {assert.doesNotMatch(credential,/LOGIN_CALLBACK|正式登录回调/);assert.match(credential,/凭据与证书/);}
  const identity=await renderImplementationWorkspace('fixture','identity',c);
  const check=await renderImplementationWorkspace('fixture','tests',c);
  if(code!=='sso'){assert.doesNotMatch(identity,/创建会话/);assert.doesNotMatch(check,/浏览器登录|退出登录/);}
 }
});
