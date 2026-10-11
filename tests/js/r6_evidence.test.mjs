// Executes the actual print function using a minimal DOM harness. Not Chromium E2E.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const source=fs.readFileSync(new URL('../../frontend/app.js',import.meta.url),'utf8');
const start=source.indexOf('async function printAssessment(id){');
const end=source.indexOf('async function newDispute(',start);
const body=source.slice(start,end);
const esc=x=>String(x??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const frozen=()=>({immutable:true,teacher:{name:'旧教师 <script>',staff_no:'J001'},period:{name:'旧周期'},rule:{name:'旧规则',version_no:2},
    organization_chain:[{kind:'school',name:'旧学校'}],assessment:{id:'a1',state:'ARCHIVED',score:'99',detail:[{label:'学时',raw:'10',formula:'10 × 2',score:20}],archive_sha256:'ab'.repeat(32)}});
async function render(data,fail=false){
 const state={html:'',classes:new Set(),printed:0,paths:[]};
 const context=vm.createContext({api:async path=>{state.paths.push(path);return data},$:()=>null,esc,number:Number,
   labels:{ARCHIVED:'已归档',TEACHER:'教师确认'},me:{school_name:'当前学校不能替代归档',user:{name:'当前打印操作者'}},
   teacherName:()=>{throw Error('must not read live identity')},periodName:()=>{throw Error('must not read live period')},
   document:{createElement:()=>({innerHTML:'',className:''}),body:{append:el=>{state.html=el.innerHTML},classList:{add:x=>state.classes.add(x),remove:x=>state.classes.delete(x)}}},
   window:{print:()=>{state.printed++;if(fail)throw Error('print unavailable')}}});
 vm.runInContext(source.match(/^function businessFormula.*$/m)[0],context);
 vm.runInContext(body,context);try{await context.printAssessment('a1')}catch(error){state.error=error.message}return state;
}
test('actual print function uses frozen identity, rule and school; escapes text',async()=>{
 const r=await render(frozen());assert.deepEqual(r.paths,['/assessments/a1/print']);assert.equal(r.printed,1);
 for(const x of ['旧教师 &lt;script&gt;','旧学校','旧周期','旧规则 版本 2','归档件','当前打印操作者'])assert.ok(r.html.includes(x));
 assert.ok(!r.html.includes('当前学校不能替代归档'));assert.ok(!r.classes.has('print-mode'));
});
test('legacy missing identity is explicitly labelled, no live school fallback',async()=>{
 const d=frozen();d.organization_chain=[];d.teacher.name='归档时未冻结姓名';d.identity_note='旧归档未保存人员组织快照';
 const r=await render(d);assert.ok(r.html.includes('归档时未冻结学校名称'));assert.ok(r.html.includes(d.identity_note));
});
test('unarchived print says process copy, not final result',async()=>{
 const d=frozen();d.immutable=false;d.school_name='正式配置学校';d.assessment.state='TEACHER';d.assessment.archive_sha256=null;
 const r=await render(d);assert.ok(r.html.includes('过程稿（非最终结果）'));assert.ok(r.html.includes('尚未归档'));assert.ok(r.html.includes('正式配置学校'));assert.ok(!r.html.includes('旧学校'));
});
test('print failure still restores page layout',async()=>{
 const r=await render(frozen(),true);assert.equal(r.error,'print unavailable');assert.ok(!r.classes.has('print-mode'));
});
test('archive evidence and original attachment actions are wired',()=>{
 for(const x of ["'assessment-proof':id=>download", "'assessment-file':code=>",'frozenAssessmentFiles(d,id)','x.teacher_display_name||teacherName'])assert.ok(source.includes(x));
});
