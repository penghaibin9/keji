import test from 'node:test';
import assert from 'node:assert/strict';
import {coursePointsAction} from '../../frontend/course-points.js';
import {socialAction} from '../../frontend/social-training.js';
const esc=x=>String(x??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
const base={application_id:'a',course:{name:'自建<课程>',code:'C1'},applicant:{id:'teacher',name:'本人'},project:null,claim:null,can_link:true,can_create_project:true,can_claim:false,can_open_claim:false,projects:[],period_id:'',policy_id:'',stage:'link',label:'待关联培训项目',message:'请选择实际培训项目',responsible:'项目负责人',steps:[{label:'课程入库',done:true},{label:'项目备案',done:false}]};
function ctx(data){const c={me:{user:{id:'teacher'}},currentUser:()=> 'teacher',currentPage:()=> 'apply_course',esc,icon:()=>'',act:(l,a,id)=>`<button data-action="${a}" data-id="${esc(id)}">${esc(l)}</button>`,note:esc,field:()=>'',api:async()=>data,closeModal(){},toast(){},modal(...args){c.modalArgs=args},runAction(...args){c.action=args},projectField:async()=>'<select name="project_id"></select>',formModal(...args){c.form=args}};return c}
test('已入库课程显示关联与新建项目入口，不把入库当作可申报积分',async()=>{
 const c=ctx(base);await coursePointsAction('open','a',c);assert.match(c.modalArgs[1],/自建&lt;课程>/);assert.match(c.modalArgs[2],/course-points-link/);assert.match(c.modalArgs[2],/course-points-new-project/);assert.doesNotMatch(c.modalArgs[2],/course-points-claim/);
});
test('可申报时带入原项目周期口径，已有申请则复用原申请',async()=>{
 const ready={...base,stage:'ready',project:{id:'p',name:'项目',cohort:'一期'},can_link:false,can_claim:true,period_id:'year',policy_id:'policy'};
 const c=ctx(ready);await coursePointsAction('claim','a',c);assert.deepEqual(c.action,['social-claim-new','p|year|policy']);
 c.api=async()=>({...ready,can_claim:false,can_open_claim:true,claim:{id:'claim',state:'DRAFT'}});await coursePointsAction('claim','a',c);assert.deepEqual(c.action,['social-detail','social_claim|claim']);
 c.api=async()=>({...ready,can_claim:false});await assert.rejects(coursePointsAction('claim','a',c),/本人身份办理/);
});
test('关联项目沿原接口读取最新版本并重新展示后续状态',async()=>{
 const c=ctx(base),calls=[];c.api=async(url,options)=>{calls.push([url,options]);return url.includes('/objects/')?{item:{id:'p',version:7}}:base};
 await coursePointsAction('link','a',c);await c.form[2]({project_id:'p',reason:'实际培训使用'});
 const write=calls.find(x=>x[1]?.method==='POST');assert.equal(write[0],'/social/projects/p/courses/link');assert.deepEqual(write[1].body,{course_code:'C1',expected_version:7,reason:'实际培训使用'});assert.match(calls.at(-1)[0],/course-points\?project_id=p/);
});
test('身份变化后不展示上一身份的积分办理响应',async()=>{
 const c=ctx(base);c.currentUser=()=> 'other';await coursePointsAction('open','a',c);assert.equal(c.modalArgs,undefined);
});

test('共用课程只显示本人办理，不显示无权访问的原课程审批',async()=>{
 const c=ctx({...base,can_read_application:false});await coursePointsAction('open','a',c);assert.doesNotMatch(c.modalArgs[2],/app-detail/);
 c.api=async()=>({...base,can_read_application:true});await coursePointsAction('open','a',c);assert.match(c.modalArgs[2],/app-detail/);
});

test('学校启用新口径后从课程入口申报会刷新口径并带入最新选择',async()=>{
 let active=false,loads=0;const fields=[];
 const c=ctx(base);c.me={user:{id:'policy-refresh-teacher',staff_no:'J001'},role:{kind:'teacher'}};c.currentUser=()=>c.me.user.id;
 c.periods=[{id:'year',name:'认定年度',state:'OPEN',start_date:'2026-01-01',end_date:'2026-12-31'}];
 c.field=(name,label,type,value)=>{fields.push({name,value});return ''};
 c.api=async url=>{
  if(url==='/social/workspace'){loads++;return {states:{ACTIVE:'已启用'},policies:active?[{id:'policy',name:'新认定口径',state:'ACTIVE',period_id:'year'}]:[]}}
  if(url.startsWith('/social/project-options'))return {items:[{id:'p',code:'P',name:'实际项目',cohort:'一期'}],q:'',total:1,page:1,size:25};
  if(url.includes('/course-points'))return {...base,can_claim:true,project:{id:'p'},period_id:'year',policy_id:'policy'};
  if(url==='/social/objects/social_project/p')return {item:{id:'p',data:{name:'实际项目'},cohort:'一期'}};
  throw Error(url);
 };
 c.runAction=(action,id)=>socialAction(action,id,c);
 await socialAction('social-claim-new','',c);assert.match(c.modalArgs[1],/学校还没有登记积分认定口径/);
 active=true;await coursePointsAction('claim','a',c);
 assert.equal(loads,2);assert.equal(c.form[0],'本人积分申报');
 assert.ok(fields.some(x=>x.name==='policy_id'&&x.value==='policy'));
 assert.ok(fields.some(x=>x.name==='period_id'&&x.value==='year'));
});
