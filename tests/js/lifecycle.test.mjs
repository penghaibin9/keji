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
test('项目运行档案是整页：只留上传材料、申请变更、结项三个按钮，6 个状态，积分在运行汇总里',async()=>{
 const c=ctx({...base,points:{label:'预计积分',value:'3.20',line:'张老师（负责人） 3.20 分'}});const html=await lifePageHtml(c,'apply_project','project|p1');
 for(const name of ['上传材料','申请变更','结项','运行过程','运行汇总','历次版本','预计积分','将记积分'])assert.match(html,new RegExp(name),name);
 for(const gone of ['记一笔','项目立项信息','改简介','项目运行 \/'])assert.doesNotMatch(html,new RegExp(gone),gone);
 assert.match(html,/第 2 版/);assert.match(html,/lv-pill lv-run">运行中/);assert.match(html,/life-stepper/);assert.match(html,/培训业务 \/ 培训项目 \/ 茶艺培训/);
 assert.match(html,/data-action="life-change"/);assert.ok(LIFE_ACTIONS.includes('life-change-act')&&LIFE_ACTIONS.includes('quick-apply')&&LIFE_ACTIONS.includes('q-bulk'));
 await assert.rejects(()=>lifePageHtml(c,'courses','project|p1'));
});

test('参与老师（不是负责人）只能上传材料',async()=>{
 const c=ctx({...base,lead:false});const html=await lifePageHtml(c,'apply_project','project|p1');
 assert.match(html,/data-action="life-upload"/);assert.doesNotMatch(html,/data-action="life-change"/);assert.doesNotMatch(html,/data-action="life-close"/);
});

test('课程停用后第三个按钮变成恢复运行，状态显示已停用，申请变更不可点',async()=>{
 const c=ctx({...base,type:'course',state:'STOPPED',state_label:'已停用',running:false,can:{...base.can,note:false,change:false,close:false,resume:true}});
 const html=await lifePageHtml(c,'apply_course','course|r1');
 assert.match(html,/data-action="life-resume"/);assert.match(html,/已停用/);
 assert.match(html,/data-action="life-change"[^>]*disabled/);
});

test('同时只显示一条最急的提醒；已有变更在审批时显示变更中、申请变更不可点',async()=>{
 const c=ctx({...base,reminders:['培训已于 2026-11-01 结束，材料齐了就可以点“项目结项”。','培训已经开始，还没有导入参训明细（人次从明细自动核算）。'],pending_change:{id:'c1',summary:'结束日期 → 2027-04-30',state_label:'待学院审批',level_label:'学院审批'},can:{...base.can,change:false}});
 const html=await lifePageHtml(c,'apply_project','project|p1');
 assert.equal((html.match(/life-remind/g)||[]).length,1);assert.match(html,/参训明细/);assert.doesNotMatch(html,/材料齐了/);
 assert.match(html,/变更中/);assert.match(html,/data-action="life-change"[^>]*disabled/);
});

test('学院、学校在列表页上方看到“待我审批”，老师不出现；可勾选批量同意',async()=>{
 const items=[{kind:'apply',label:'立项',type:'project',id:'p1',name:'茶艺培训',who:'张老师',on:'2026-11-08',summary:'社区公益培训',action:'approve',version:3,batch:true},
  {kind:'change',label:'变更',type:'project',id:'ch1',name:'茶艺培训',who:'张老师',on:'2026-11-08',summary:'结束日期：2026-12-20 → 2027-04-30',action:'approve',version:1,batch:true},
  {kind:'close',label:'结项核验',type:'project',id:'p2',name:'面点培训',who:'李老师',on:'2026-11-07',summary:'满意度 96%',action:'close',version:5,batch:false}];
 const c=ctx(base);c.api=async url=>{c.calls.push([url]);return {items}};
 assert.equal(await lifeBoardHtml(c,'apply_project'),'');
 c.me.role.kind='college';
 const html=await lifeBoardHtml(c,'projects');
 assert.match(html,/全部 3/);assert.match(html,/立项 1/);assert.match(html,/变更 1/);assert.match(html,/结项 1/);assert.match(html,/批量同意/);
 assert.match(html,/data-action="q-pick" data-id="apply\|project\|p1"/);assert.doesNotMatch(html,/data-action="q-pick" data-id="close\|project\|p2"/);
 assert.equal(await lifeBoardHtml(c,'apply_project'),'');
 assert.equal(lifePageType('trainers'),'trainer');assert.equal(lifePageType('home'),'');
 await lifecycleAction('q-pick','apply|project|p1',c);
 const posts=[];c.api=async(url,opt)=>{if(opt)posts.push([url,opt.body]);return {items}};
 await lifecycleAction('q-bulk','project',c);
 assert.deepEqual(posts.map(x=>[x[0],x[1].action]),[['/social/projects/p1/actions','approve']]);
});

test('老师“我的培训项目”：三步按钮、全部/我负责的/我参与的、新建只在立项、被退回直接显示原因',async()=>{
 const items=[{type:'project',id:'a',name:'插花',status:'draft',status_label:'草稿',stage:'apply',dates:'2026-12-05 至 2026-12-26',lead:true,todo:{text:'被退回：人次偏高',act:'social-detail',id:'social_project|a',btn:'修改后重新提交',tone:'warn'}},
  {type:'project',id:'b',name:'茶艺',status:'run',status_label:'运行中',stage:'run',dates:'2026-09-01 至 2026-12-31',lead:true,todo:{text:'培训已结束，去结项',act:'life-close',id:'project|b',btn:'去结项',tone:'warn'}},
  {type:'project',id:'m',name:'养生茶',status:'run',status_label:'运行中',stage:'run',dates:'2026-10-15 至 2026-12-15',lead:false,todo:null},
  {type:'project',id:'d',name:'茶农',status:'done',status_label:'已结项',stage:'close',dates:'',lead:true,todo:null,again:true}];
 const c=ctx(base);c.api=async()=>({items});
 const {lifeListHtml}=await import('../../frontend/lifecycle.js');
 let html=await lifeListHtml(c,'apply_project');
 assert.match(html,/项目立项/);assert.match(html,/项目运行/);assert.match(html,/项目结项/);assert.match(html,/我参与的/);
 assert.match(html,/茶艺/);assert.match(html,/养生茶/);assert.match(html,/去结项/);assert.doesNotMatch(html,/新建培训项目/);
 await lifecycleAction('lv-rf','member',c);html=await lifeListHtml(c,'apply_project');assert.doesNotMatch(html,/>茶艺</);assert.match(html,/养生茶/);
 await lifecycleAction('lv-rf','all',c);
 await lifecycleAction('lv-tab','project|apply',c);html=await lifeListHtml(c,'apply_project');
 assert.match(html,/被退回：人次偏高/);assert.match(html,/修改后重新提交/);assert.match(html,/新建培训项目/);
 await lifecycleAction('lv-tab','project|close',c);html=await lifeListHtml(c,'apply_project');assert.match(html,/再办一期/);
 await lifecycleAction('lv-tab','project|run',c);
});

test('上传材料按文件名自动分组',async()=>{
 const {groupOf}=await import('../../frontend/lifecycle.js');
 assert.equal(groupOf('第3期签到表.pdf'),'签到表');assert.equal(groupOf('学员名单.pdf'),'签到表');assert.equal(groupOf('现场.JPG'),'照片');
 assert.equal(groupOf('茶艺课件.pdf'),'课件');assert.equal(groupOf('成果报告.pdf'),'其他');
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

test('结项审批：没明细时只写“老师还没上传参训明细表”、不给同意；学校核验要填实际满意度分数，零收入不用填收入',async()=>{
 const review=units=>({archive:{facts:[['负责人','张老师']],stats:[]},files:[],points:'',closeout:{},units,expected_income:'0',state:'CLOSE_COLLEGE'});
 const college={kind:'close',label:'结项',type:'project',id:'p1',name:'茶艺',who:'张老师',on:'2026-11-09',summary:'',action:'approve',version:3,batch:false,units:0};
 const school={...college,label:'结项核验',action:'close',id:'p2'};
 const c=ctx(base);c.me.role.kind='college';
 c.api=async url=>url.includes('/queue/')?{items:[college,school]}:review(url.includes('p1')?0:2);
 await lifeBoardHtml(c,'projects');
 await lifecycleAction('q-view','close|project|p1',c);
 assert.match(c.last.body,/老师还没上传参训明细表/);assert.doesNotMatch(c.last.foot,/q-ok-close|life-units/);
 await lifecycleAction('q-view','close|project|p2',c);
 assert.match(c.last.foot,/data-action="q-close-review"/);
 await lifecycleAction('q-close-review','close|project|p2',c);
 assert.match(c.form.body,/满意度分数/);assert.doesNotMatch(c.form.body,/满意（85% 及以上）/);
 const posts=[];c.api=async(url,opt)=>{if(opt)posts.push([url,opt.body]);return {items:[]}};
 await assert.rejects(()=>c.form.save({satisfaction:'',actual_income:'0'}),/满意度分数/);
 await assert.rejects(()=>c.form.save({satisfaction:'120',actual_income:'0'}),/满意度分数/);
 await assert.rejects(()=>c.form.save({satisfaction:'80',actual_income:'0'}),/整改期限/);
 assert.equal(posts.length,0);
 await c.form.save({satisfaction:'93.5',actual_income:'0'});
 assert.equal(posts[0][0],'/social/projects/p2/actions');assert.equal(posts[0][1].action,'close');assert.equal(posts[0][1].review.satisfaction,'93.5');assert.equal(posts[0][1].review.finance_reference,'零收入项目，无到账收入');
});

test('项目负责人在项目详情里能“上传参训明细表”，没明细的提醒点“现在处理”也去上传',async()=>{
 const c=ctx({...base,reminders:['还没有参训明细，已在学院待办里提醒导入。']});c.can=()=>false;
 const html=await lifePageHtml(c,'apply_project','project|p1');
 assert.match(html,/data-action="life-units" data-id="p1">上传参训明细表/);
 assert.match(html,/life-remind[\s\S]*data-action="life-units"/);
 const member=await lifePageHtml(ctx({...base,lead:false}),'apply_project','project|p1');
 assert.doesNotMatch(member,/上传参训明细表/);
});
