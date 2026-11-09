// 2026-11-07 运行档案：三个主按钮名称、停用后的按钮、申请变更只提交勾选的项。
import test from 'node:test';
import assert from 'node:assert/strict';
import {lifecycleAction,LIFE_ACTIONS,lifePageHtml,lifeBoardHtml,lifePageType} from '../../frontend/lifecycle.js';

const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function ctx(archive){
 const calls=[],c={esc,calls,me:{role:{kind:'teacher'},user:{id:'t1'}},teachers:[],
  act:(l,a,id='',k='')=>`<button class="btn ${k}" data-action="${a}" data-id="${esc(id)}">${esc(l)}</button>`,
  icon:()=>'<svg></svg>',note:t=>'<p class="note">'+t+'</p>',table:(h,rows)=>'<table>'+rows.map(r=>'<tr>'+r.join('')+'</tr>').join('')+'</table>',
  field:(n,l)=>`<label>${esc(l)}<input name="${n}"></label>`,can:()=>true,toast:()=>{},render:async()=>{},closeModal:()=>{},
  modal:(title,body,foot,wide,label)=>{c.last={title,body,foot,label}},
  formModal:(title,body,save,options)=>{c.form={title,body,save,options}},
  currentPage:()=>'apply_project',
  api:async(url,opt)=>{calls.push([url,opt]);return opt?{applied:false,level:'school',archive}:archive},
  runAction:async(a,id)=>calls.push(['run',a,id])};
 return c;
}
const base={type:'project',id:'p1',name:'茶艺培训',state:'FILED',state_label:'已备案',running:true,version:3,biz_version:2,facts:[['负责人','张老师']],
 timeline:[{at:'2026-11-07',who:'张老师',what:'开班',kind:'note',source:'self'}],versions:[{v:2,at:'2026-11-07',who:'张老师',summary:'人次 30 → 36'},{v:1,at:'2026-10-01',who:'学校',summary:'立项通过'}],
 stats:[['参训明细','0 条']],reminders:['培训已结束'],pending_change:null,note_tags:{start:'开班',other:'其他'},
 fields:[{key:'end_date',label:'结束日期（延期）',type:'date',value:'2026-12-20'},{key:'expected_participants',label:'预估培训人次',type:'number',value:30}],
 can:{note:true,change:true,annual:false,stop:false,resume:false,close:true,upload:true}};

// 2026-11-09 按设计稿：运行档案是整页（不是弹窗），卡片列表在“项目运行”下。
test('项目运行档案是整页：进度条、提醒、三个按钮、时间线、汇总、版本',async()=>{
 const c=ctx(base);const html=await lifePageHtml(c,'apply_project','project|p1');
 for(const name of ['记一笔','申请变更','项目结项','项目立项信息','运行过程','运行汇总','历次版本'])assert.match(html,new RegExp(name),name);
 assert.match(html,/当前第 2 版/);assert.match(html,/v2/);assert.match(html,/life-stepper/);assert.match(html,/培训业务 \/ 培训项目 \/ 项目运行 \/ 茶艺培训/);
 assert.match(html,/data-action="life-change"/);assert.ok(LIFE_ACTIONS.includes('life-change-act')&&LIFE_ACTIONS.includes('quick-apply'));
 await assert.rejects(()=>lifePageHtml(c,'courses','project|p1'));
});

test('课程停用后第三个按钮变成恢复运行，记一笔不可点',async()=>{
 const c=ctx({...base,type:'course',state:'STOPPED',state_label:'已停用',running:false,can:{...base.can,note:false,change:false,close:false,resume:true}});
 const html=await lifePageHtml(c,'apply_course','course|r1');
 assert.match(html,/data-action="life-resume"/);assert.match(html,/课程申报信息/);
 assert.match(html,/data-action="life-note"[^>]*disabled/);
});

test('提醒带“现在处理”按钮，已有变更在审批时申请变更不可点',async()=>{
 const c=ctx({...base,reminders:['培训已于 2026-11-01 结束，材料齐了就可以点“项目结项”。'],pending_change:{id:'c1',summary:'结束日期 → 2027-04-30',state_label:'待学院审批',level_label:'学院审批'},can:{...base.can,change:false}});
 const html=await lifePageHtml(c,'apply_project','project|p1');
 assert.match(html,/现在处理/);assert.match(html,/data-action="life-close"/);assert.match(html,/变更审批中/);
 assert.match(html,/data-action="life-change"[^>]*disabled/);
});

test('运行卡片：老师在我的申报页、学院在列表页看到，点开进整页',async()=>{
 const board={cards:[{type:'project',id:'p1',name:'茶艺培训',state:'FILED',running:true,state_label:'运行中',sub:'社区公益培训 · 2026-10-08 至 2026-12-20',stats:[['参训明细','0 条']],remind:'培训已经开始（人次从明细核算）',pending:''}],total:1,
  changes:[{id:'ch1',name:'茶艺培训',who:'张老师',on:'2026-11-08',level_label:'学院审批',reason:'延期',rows:[{label:'结束日期',from_text:'2026-12-20',to_text:'2027-04-30'}]}]};
 const c=ctx(base);c.api=async()=>board;
 const html=await lifeBoardHtml(c,'apply_project');
 assert.match(html,/项目运行/);assert.match(html,/data-action="life-open" data-id="project\|p1"/);assert.match(html,/待我审批的变更/);assert.match(html,/data-id="approve\|ch1"/);assert.match(html,/2027-04-30/);
 assert.equal(await lifeBoardHtml(c,'projects'),'');           // 老师在“我负责或参与的”页不重复出现
 c.me.role.kind='college';assert.match(await lifeBoardHtml(c,'projects'),/life-card/);
 assert.equal(await lifeBoardHtml(c,'apply_project'),'');
 assert.equal(lifePageType('trainers'),'trainer');assert.equal(lifePageType('home'),'');
});

test('申请变更只提交勾选的项，没勾的项不展开',async()=>{
 const c=ctx(base);await lifecycleAction('life-change','project|p1',c);
 assert.equal(c.form.title,'申请变更');assert.match(c.form.body,/现在：2026-12-20/);
 assert.equal((c.form.body.match(/class="life-chg-new" hidden/g)||[]).length,2);
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
  const html=await lifePageHtml(c,type==='base'?'apply_base':'apply_trainer',type+'|r1');
  assert.match(html,/data-action="life-resume"[^>]*>恢复运行/,type);
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

// 2026-11-09 老师新申报：普通弹窗、点选为主，不走全屏的完整表单。
import {quickApply} from '../../frontend/apply-quick.js';
test('四类新申报都用普通弹窗（不带 page），表单点选为主',async()=>{
 for(const [type,title] of [['project','新申报培训项目'],['course','新申报培训课程'],['base','新申报培训基地'],['trainer','申报培训师']]){
  const c=ctx(base);c.field=(n,l)=>`<label>${esc(l)}<input name="${n}"></label>`;c.me={...c.me,user:{id:'t1',name:'张老师',org_id:'o1'},org:{kind:'college',id:'o1'}};
  await quickApply(c,type);
  assert.equal(c.form.title,title);assert.ok(!c.form.options.page,'不应全屏：'+type);assert.ok(!c.form.options.wide,type);
  assert.match(c.form.body,/type="(radio|checkbox)"/,type);
 }
 await assert.rejects(()=>quickApply(ctx(base),'x'));
});
test('新申报项目：必填点选缺项会拦下，补齐后以老师本人为负责人提交并转学院',async()=>{
 const c=ctx(base);c.field=(n,l)=>`<label>${esc(l)}<input name="${n}"></label>`;c.me={...c.me,user:{id:'t1',name:'张老师',org_id:'o1'},org:{kind:'college',id:'o1'}};
 await quickApply(c,'project');
 const vals={name:'茶艺',start_date:'2026-11-20',end_date:'2026-12-19',venue_place:'实训楼101',expected_participants:'40',cohort:'第一期',code:'',venue_reason:'',venue_ref:'',outcome_other:'',groups_note:''},radios={category:'community',venue_type:'campus'},checks={'outcome__结业证书':true};
 const form={querySelector:s=>{const m=s.match(/name="([^"]+)"/);if(!m)return null;const n=m[1];if(s.includes(':checked'))return radios[n]?{value:radios[n]}:null;if(n in checks)return {checked:true};if(n==='qa_files')return {files:[{name:'a.pdf',size:10}]};return n in vals?{value:vals[n]}:{value:'',checked:false}},querySelectorAll:()=>[]};
 const calls=[];c.api=async(url,opt)=>{calls.push([url,opt]);return {item:{id:'n1',version:1}}};
 globalThis.FormData=class{set(){}};
 await assert.rejects(()=>c.form.save({expected_participants:40,expected_income:0},{...form,querySelector:s=>s.includes('category')?null:form.querySelector(s)}),/培训类别/);
 assert.equal(calls.length,0);
});
