// 2026-11-07 运行档案：三个主按钮名称、停用后的按钮、申请变更只提交勾选的项。
import test from 'node:test';
import assert from 'node:assert/strict';
import {lifecycleAction,LIFE_ACTIONS} from '../../frontend/lifecycle.js';

const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function ctx(archive){
 const calls=[],c={esc,calls,me:{role:{kind:'teacher'},user:{id:'t1'}},teachers:[],
  act:(l,a,id='',k='')=>`<button class="btn ${k}" data-action="${a}" data-id="${esc(id)}">${esc(l)}</button>`,
  icon:()=>'<svg></svg>',note:t=>'<p class="note">'+t+'</p>',table:(h,rows)=>'<table>'+rows.map(r=>'<tr>'+r.join('')+'</tr>').join('')+'</table>',
  field:(n,l)=>`<label>${esc(l)}<input name="${n}"></label>`,can:()=>true,toast:()=>{},render:async()=>{},closeModal:()=>{},
  modal:(title,body,foot,wide,label)=>{c.last={title,body,foot,label}},
  formModal:(title,body,save,options)=>{c.form={title,body,save,options}},
  api:async(url,opt)=>{calls.push([url,opt]);return opt?{applied:false,level:'school',archive}:archive},
  runAction:async(a,id)=>calls.push(['run',a,id])};
 return c;
}
const base={type:'project',id:'p1',name:'茶艺培训',state:'FILED',state_label:'已备案',running:true,version:3,biz_version:2,facts:[['负责人','张老师']],
 timeline:[{at:'2026-11-07',who:'张老师',what:'开班',kind:'note',source:'self'}],versions:[{v:2,at:'2026-11-07',who:'张老师',summary:'人次 30 → 36'},{v:1,at:'2026-10-01',who:'学校',summary:'立项通过'}],
 stats:[['参训明细','0 条']],reminders:['培训已结束'],pending_change:null,note_tags:{start:'开班',other:'其他'},
 fields:[{key:'end_date',label:'结束日期（延期）',type:'date',value:'2026-12-20'},{key:'expected_participants',label:'预估培训人次',type:'number',value:30}],
 can:{note:true,change:true,annual:false,stop:false,resume:false,close:true,upload:true}};

test('项目档案用验收人定的三个名字，版本和时间线都显示',async()=>{
 const c=ctx(base);await lifecycleAction('life-open','project|p1',c);
 for(const name of ['项目立项','项目运行','项目结项'])assert.match(c.last.body,new RegExp(name));
 assert.match(c.last.body,/第 2 版/);assert.match(c.last.body,/第2版/);assert.match(c.last.body,/data-action="life-change"/);
 assert.equal(c.last.label,'培训项目 / 运行档案');assert.ok(LIFE_ACTIONS.includes('life-change-act'));
});

test('课程停用后第三个按钮变成恢复运行，记一笔不可点',async()=>{
 const c=ctx({...base,type:'course',state:'STOPPED',state_label:'已停用',running:false,can:{...base.can,note:false,change:false,close:false,resume:true}});
 await lifecycleAction('life-open','course|r1',c);
 assert.match(c.last.body,/data-action="life-resume"/);assert.match(c.last.body,/课程申报/);
 assert.match(c.last.body,/data-action="life-note"[^>]*disabled/);
});

test('申请变更只提交勾选的项',async()=>{
 const c=ctx(base);await lifecycleAction('life-change','project|p1',c);
 assert.equal(c.form.title,'申请变更');assert.match(c.form.body,/现在：2026-12-20/);
 const picked={'pick-end_date':true},values={'v-end_date':'2027-04-30','v-expected_participants':'31'};
 const form={querySelector:s=>{const m=s.match(/name="([^"]+)"/);if(!m)return null;const n=m[1];if(n.startsWith('pick-'))return {checked:!!picked[n]};return n in values?{value:values[n]}:null},querySelectorAll:()=>[]};
 await c.form.save({reason:'延期'},form);
 const sent=c.calls.find(([u,o])=>o&&u.endsWith('/changes'));
 assert.deepEqual(sent[1].body.values,{end_date:'2027-04-30'});assert.equal(sent[1].body.reason,'延期');
});

// 2026-11-08 走查修复：基地、师资停用后也有“恢复运行”；年度确认只给可确认的年份；变更表单负责人显示姓名。
test('基地、师资停用后档案里有恢复运行按钮',async()=>{
 for(const type of ['base','trainer']){
  const c=ctx({...base,type,state:'STOPPED',state_label:'已停用',running:false,annual:{},annual_years:[2026],can:{...base.can,note:false,change:false,close:false,annual:false,upload:false,resume:true}});
  await lifecycleAction('life-open',type+'|r1',c);
  assert.match(c.last.body,/data-action="life-resume"[^>]*>恢复运行/,type);
 }
});

test('年度确认只列后端给的年份，已确认的年份标明再确认即更正',async()=>{
 const c=ctx({...base,type:'base',annual:{'2026':{running:true,on:'2026-11-08'}},annual_years:[2026],can:{...base.can,annual:true}});
 c.field=(n,l,t,v,o)=>`<label>${esc(l)}<input name="${n}" value="${esc(v)}">${(o?.options||[]).map(x=>esc(x[1])).join('|')}</label>`;
 await lifecycleAction('life-annual','base|b1',c);
 assert.match(c.form.body,/2026 年度（已确认，再确认即更正）/);assert.doesNotMatch(c.form.body,/2025 年度/);
 assert.match(c.form.options.hint,/2026 年度已确认为“在运行”/);
});

test('变更表单的负责人显示姓名和工号，不显示账号',async()=>{
 const c=ctx({...base,fields:[{key:'owner_id',label:'项目负责人',type:'user',value:'t1'}]});c.teachers=[{id:'t1',name:'张老师',staff_no:'J001'}];
 await lifecycleAction('life-change','project|p1',c);
 assert.match(c.form.body,/现在：张老师（J001）/);
});
