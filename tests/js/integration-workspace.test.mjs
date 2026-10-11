import test from 'node:test';
import assert from 'node:assert/strict';
import {renderImplementationWorkspace} from '../../frontend/integration-workspace.js';

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
