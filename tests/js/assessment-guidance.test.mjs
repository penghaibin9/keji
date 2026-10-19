import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const source=fs.readFileSync(new URL('../../frontend/app.js',import.meta.url),'utf8');
const body=source.slice(source.indexOf('async function assessmentAction(code){'),source.indexOf('async function showOrgAssessment(id){'));
function harness({blocked=false,race=false}={}){
 const state={writes:0,blocked:0,shown:0,form:null};
 const context=vm.createContext({esc:x=>String(x??''),number:x=>String(x??0),teacherName:()=>'测试教师',periodName:()=>'测试周期',orgName:()=>'测试组织',me:{role:{kind:'teacher'}},labels:{TEACHER:'教师确认'},note:x=>x,reasonFields:()=>'',closeModal(){},render:async()=>{},showAssessment:async()=>state.shown++,showAssessmentBlockers:async()=>state.blocked++,formModal:(title,body,callback)=>state.form={title,body,callback},api:async(path,options)=>{
  if(options){state.writes++;if(race)throw Error('存在未解决数据核对，请先处理');return {}}
  return {assessment:{id:'a1',version:7,state:'TEACHER'},confirmation_blockers:{count:blocked||(race&&state.writes)?1:0}};
 }});
 vm.runInContext(body,context);return {state,run:context.assessmentAction};
}
test('blocked confirmation opens resolution guidance before asking for opinion or writing',async()=>{
 const h=harness({blocked:true});await h.run('confirm|a1');assert.equal(h.state.blocked,1);assert.equal(h.state.form,null);assert.equal(h.state.writes,0);
});
test('ready confirmation names the next stage and returns to refreshed assessment',async()=>{
 const h=harness();await h.run('confirm|a1');assert.equal(h.state.form.title,'本人确认并提交教研室');await h.state.form.callback({reason:'核实无误'});assert.equal(h.state.writes,1);assert.equal(h.state.shown,1);
});
test('a newly filed dispute between precheck and submit opens fresh guidance without claiming success',async()=>{
 const h=harness({race:true});await h.run('confirm|a1');await h.state.form.callback({reason:'核实无误'});assert.equal(h.state.blocked,1);assert.equal(h.state.shown,0);
});
test('return remains available while disputes block forward confirmation',async()=>{
 const h=harness({blocked:true});await h.run('return|a1');assert.equal(h.state.form.title,'退回教师重新核对');assert.equal(h.state.blocked,0);
});
