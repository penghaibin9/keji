// 学院经办人的页头角色名：运行 app.js 里实际的 roleName，不是浏览器端到端测试。
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const source=fs.readFileSync(new URL('../../frontend/app.js',import.meta.url),'utf8');
function roleName(me){
  const line=source.split('\n').find(x=>x.startsWith('const roleName='));
  assert.ok(line,'roleName exists');
  const ctx=vm.createContext({me});
  vm.runInContext(line.replace('const roleName=','globalThis.roleName='),ctx);
  return ctx.roleName();
}
test('学院经办人身份显示“学院经办人”，不显示成学院负责人',()=>{
  assert.equal(roleName({role:{name:'学院负责人'},college_agent:{on_behalf_of:'某院长'}}),'学院经办人');
});
test('院长本人和其他身份仍显示角色名',()=>{
  assert.equal(roleName({role:{name:'学院负责人'},college_agent:null}),'学院负责人');
  assert.equal(roleName({role:{name:'教师'}}),'教师');
});
test('页头、工作台范围、审批中心和账号信息都用 roleName',()=>{
  assert.equal(source.split('me.role.name').length-1,1,'只剩 roleName 自己读 me.role.name');
  assert.ok(source.includes('<small>${esc(roleName())}</small>'));
});
