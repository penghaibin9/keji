// Execute actual page renderers in a minimal VM. This is not Chromium E2E.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const source=fs.readFileSync(new URL('../../frontend/app.js',import.meta.url),'utf8');
const esc=x=>String(x??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
async function render(method,items){
  const line=source.split('\n').find(x=>x.trimStart().startsWith('async '+method+'(){'));
  assert.ok(line,'actual page renderer exists');
  const body=line.trim().replace('async '+method+'(){','async function render(){').replace(/,$/,'');
  const state={rows:null,links:[]};
  const ctx=vm.createContext({view:null,assessmentTab:'dept',periodId:'p1',filter:{tab:'dept'},tablePage:1,me:{role:{kind:'dept'}},businessConfig:{import_max_rows:500},
    api:async()=>({items,total:items.length,page:1,size:20}),listQuery:()=>'',query:()=>'',can:()=>false,
    pageHead:()=>'',act:()=>'',note:()=>'',icon:()=>'',filtersBar:()=>'',pager:()=>'',esc,number:Number,badge:esc,workflowContext:()=>'',teacherName:()=>'测试教师',
    table:(_head,rows)=>{state.rows=rows;return rows.flat().join('|')},link:(label,type,id)=>{state.links.push(id);return label},
    orgName:()=>{throw Error('live organization fallback forbidden for archived row')},
    periodName:()=>{throw Error('live period fallback forbidden for archived row')}});
  vm.runInContext(source.split('\n').find(x=>x.startsWith('function importKindOptions()')),ctx);
  vm.runInContext(body,ctx);state.html=await ctx.render();return state;
}
test('restricted import row has no view/confirm link and no misleading zero counts',async()=>{
  const r=await render('imports',[{id:'old',filename:'已受限',kind:'records',total:null,errors:null,state:'PREVIEW',access_revoked:true,access_note:'权限已变化 <script>'}]);
  assert.equal(r.links.length,0);assert.equal(r.rows[0][2],'—');assert.equal(r.rows[0][3],'—');
  assert.ok(r.html.includes('权限已变化 &lt;script&gt;'));assert.ok(!r.html.includes('<script>'));
});
test('authorized import row keeps its original workflow and zero errors',async()=>{
  const r=await render('imports',[{id:'allowed',filename:'合格.xlsx',kind:'records',total:1,errors:0,state:'PREVIEW',access_revoked:false}]);
  assert.deepEqual(r.links,['allowed']);assert.equal(r.rows[0][3],0);
});
test('actual organization list uses frozen labels without live organization fallback',async()=>{
  const r=await render('assessment',[{id:'org1',target_id:'dept1',period_id:'p1',target_display_name:'历史教研室 <x>',period_display_name:'历史周期',score:'100.00',state:'ARCHIVED',version:4}]);
  assert.ok(r.html.includes('历史教研室 &lt;x&gt;'));assert.ok(r.html.includes('历史周期'));
});
test('organization history explicitly renders the server-provided legacy notice escaped',()=>{
  const start=source.indexOf('async function showOrgAssessment('),end=source.indexOf('async function calculateOrgAssessment(',start);
  const body=source.slice(start,end);
  assert.ok(body.includes('d.history_note'));assert.ok(body.includes('esc(d.history_note)'));assert.ok(body.includes('eventsHtml(d.events)'));
});

for (const [label,permissions,admin,expected] of [
  ['only import does not grant raw business access',['import'],false,[]],
  ['record operator gets only records and participation',['import','records.read'],false,['records','participations']],
  ['qualification operator does not get personnel import',['import','qualification.read'],false,['qualifications']],
  ['users.manage without administrator is insufficient',['import','users.manage'],false,[]],
  ['school administrator with explicit permission can import teachers',['import','users.manage'],true,['teachers']],
]) test(label,()=>{
  const ctx=vm.createContext({me:{role:{kind:'school'},user:{is_admin:admin}},can:p=>permissions.includes(p)});
  vm.runInContext(source.split('\n').find(x=>x.startsWith('function importKindOptions()')),ctx);
  assert.deepEqual(Array.from(ctx.importKindOptions(),x=>x[0]),expected);
});
