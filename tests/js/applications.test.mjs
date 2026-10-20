// 申请进度组件：详情、我的申请、首页三处共用同一份后端进度数据。
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {progressHtml, myCoursesHtml, myApplicationsHtml, homeApplicationsHtml, homeCoursesHtml, applyPageHtml, applicationAction, teachingCourseForm, bindApplicationConditions, trainersHtml, courseAction} from '../../frontend/applications.js';

const esc = s => String(s ?? '').replace(/[&<>"]/g, ch => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'})[ch]);
const p = {label: '培训课程申报', text: '学院审批中 · 第 3 步 / 共 4 步', headline: '测试学院一负责人正在审批。无需你操作。', tone: 'blue',
  nodes: [{label: '提交', state: 'done', who: '测试教师一', at: '2026-10-01T09:00:00'}, {label: '教研室审核', state: 'done', who: '<b>主任</b>', acting_for: '缺负责人由学院代办'},
    {label: '学院审批', state: 'current', who: '院长', waiting_days: 3}, {label: '进入培训课程库', state: 'todo'}]};

test('full progress shows who, waiting days and handling tags, escaped', () => {
  const html = progressHtml(p, esc);
  assert.match(html, /<li class="current"><i>3<\/i><span>学院审批<\/span><small>院长 · 已等 3 天<\/small>/);
  assert.match(html, /缺负责人由学院代办/);
  assert.match(html, /&lt;b&gt;主任/);
  assert.match(html, /无需你操作/);
  assert.match(html, /测试教师一 · 2026-10-01 17:00/);  // UTC 显示成北京时间
});

test('compact progress keeps the nodes and one line only', () => {
  const html = progressHtml(p, esc, {compact: true});
  assert.match(html, /apply-progress compact/);
  assert.doesNotMatch(html, /已等|无需你操作|缺负责人/);
  assert.equal([...html.matchAll(/<li /g)].length, 4);
});

test('returned node shows the reason', () => {
  const html = progressHtml({...p, tone: 'red', nodes: [p.nodes[0], {label: '教研室审核', state: 'returned', reason: '补课件审查'}]}, esc);
  assert.match(html, /<li class="returned"><i>!<\/i>/);
  assert.match(html, /退回原因：补课件审查/);
});

const ctx = data => ({esc, number:(v,d=0)=>Number(v).toFixed(d),link:(label,action,id)=>`<button data-action="${action}" data-id="${esc(id)}">${esc(label)}</button>`, icon:()=>'<svg></svg>', api: async () => data, note: t => `<div class="note">${esc(t)}</div>`, table: (h, rows, empty) => rows.length ? rows.map(r => r.join('|')).join('\n') : empty,
  act: (label, action, id = '') => `<button data-action="${action}" data-id="${esc(id)}">${esc(label)}</button>`});

test('师资分类点击与列表共享状态，校内外筛选和重置正确且不扩大资料权限',async()=>{
 const app=readFileSync(new URL('../../frontend/app.js',import.meta.url),'utf8');
 const specifier=app.match(/import \{renderTrainingWorkspace,trainingChange\} from '([^']+)'/)[1];
 const {trainingChange}=await import(new URL('../../frontend/'+specifier,import.meta.url));
 const c=ctx({total:2,items:[{id:'internal',name:'校内合成教师',source:'internal',can_view_detail:true},{id:'external',name:'校外合成教师',source:'external',can_view_detail:false}]});
 c.me={user:{id:'trainer-category-regression'},role:{kind:'college'}};
 let html=await trainersHtml(c);assert.match(html,/校内合成教师/);assert.match(html,/校外合成教师/);
 trainingChange('trainers',c,'tab','internal');html=await trainersHtml(c);
 assert.match(html,/data-action="training-tab" data-id="internal" aria-pressed="true"/);assert.match(html,/校内合成教师/);assert.doesNotMatch(html,/校外合成教师/);
 trainingChange('trainers',c,'tab','external');html=await trainersHtml(c);
 assert.match(html,/data-action="training-tab" data-id="external" aria-pressed="true"/);assert.match(html,/校外合成教师/);assert.doesNotMatch(html,/校内合成教师|data-action="app-detail"/);
 trainingChange('trainers',c,'reset');html=await trainersHtml(c);assert.match(html,/data-id="" aria-pressed="true"/);assert.match(html,/校内合成教师/);assert.match(html,/校外合成教师/);
});

test('入库师资复用申请详情入口，仅按服务端读权限提供，省级推荐权限不扩展',async()=>{
 for(const kind of ['dept','college','school']){
  const c=ctx({total:2,items:[{id:'readable',name:'已授权师资',source:'internal',directions:['社会化培训'],org_name:'学院',can_view_detail:true},{id:'basic',name:'仅公开基础师资',source:'external',directions:[],org_name:'学院',can_view_detail:false}]});c.me={role:{kind}};
  const html=await trainersHtml(c);assert.match(html,/data-action="app-detail" data-id="readable"/);assert.doesNotMatch(html,/data-action="app-detail" data-id="basic"/);assert.match(html,/仅基础信息/);assert.equal(html.includes('trainer-recommend'),kind==='school');
 }
});

test('首页与我的申请使用简明当前进度，保留办理人和草稿数量',async()=>{
 const c=ctx({counts:{draft:1,pending:1,returned:0,done:0},items:[{id:'a1',name:'<课程>',type:'application',label:'课程申报',state:'COLLEGE',state_label:'学院审批中',progress:p}]});
 c.me={role:{kind:'teacher'}};
 for(const render of [myApplicationsHtml,homeApplicationsHtml]){
  const html=await render(c);assert.match(html,/学院审批中/);assert.match(html,/负责人正在审批/);assert.match(html,/&lt;课程&gt;/);assert.match(html,/app-detail/);assert.doesNotMatch(html,/apply-steps|<课程>/);
 }
 assert.match(await myApplicationsHtml(c),/草稿 <b>1<\/b>/);
});
const card = (over = {}) => ({identity: 'CX|二维绘图软件应用', origin: 'CX', id: 't1', course_code: 'X1', course_name: '二维绘图软件应用', credit: 2, hours: 32, chapters: 12,
  terms: [{term_name: '2025-2', school_year: '2025-2026'}, {term_name: '2024-2', school_year: '2024-2025'}, {term_name: '2023-2', school_year: '2023-2024'}],
  years: ['2025-2026', '2024-2025', '2023-2024'], problems: [], application: null, cover_url: 'https://evil.example/a.png', ...over});

test('首页超星已认定学分复用本学年汇总，不累加重复待认定或不计分课程，保留明确零值',async()=>{
 const year='2026-2027',source=(id,credit,counted,review)=>card({id,credit,years:[year],terms:[{term_name:year+'-1',school_year:year,credit,counted,review}]});
 const courses=[source('linked','3.50',false,null),source('approved','2.00',true,'approved'),source('pending','4.00',true,'pending'),source('excluded','5.00',true,'excluded')];
 for(const credit of ['2.00','0.00',0]){
  const html=await homeCoursesHtml(ctx({school_year_now:year,courses,years:[{school_year:'2025-2026',cx_credit:'99.00'},{school_year:year,cx_credit:credit}]}));
  assert.match(html,new RegExp('<b>'+Number(credit).toFixed(1).replace('.','\\.')+'</b>已认定学分'));
  assert.match(html,/<b>4<\/b>本学年在用/);assert.doesNotMatch(html,/可计学分/);
 }
});

test('超星课程列表按课程归集，保留学期数、申报及课程详情入口', async () => {
  const html = await myCoursesHtml(ctx({courses: [card(), card({identity: 'CX|机械制图', course_name: '机械制图', credit: null, problems: ['超星没填学分'], terms: [{term_name: '2025-1', school_year: '2025-2026'}], years: ['2025-2026'],
    application: {id: 'a1', state: 'RETURNED', state_label: '退回补正'}})]}), 'cx', '');
  assert.equal([...html.matchAll(/class="my-course-name"/g)].length, 2);
  assert.match(html, /3 个学期/);
  assert.match(html, /data-action="mc-apply" data-id="0">申报课程/);
  assert.match(html, /退回补正.*去补正/s);
  assert.match(html, /学分未填写/);
  assert.doesNotMatch(html, /<img/);
});

test('课程详情按服务端认定状态显示中文，重复课程保留不重复计算',async()=>{
 for(const [review,counted,label] of [['pending',true,'待认定'],['approved',true,'已认定'],['excluded',true,'不计分'],[null,false,'不重复计算']]){
  const c=ctx({courses:[card({terms:[{term_name:'2026-1',school_year:'2026-2027',credit:'0.00',hours:'0.00',review,counted}]})]});let body;c.modal=(_title,html)=>{body=html};
  await myCoursesHtml(c,'cx','');await courseAction('mc-detail','0',c);assert.match(body,new RegExp('2026-1\\|2026-2027\\|0\\|0\\|'+label));
 }
});

test('课程列表学年和学期分行，未知学期转义保留且零学分学时不丢失',async()=>{
 const terms=['2026-1','2026-2027-2','2026-2027 学年第一学期','2026—2027学年第2学期','<未知学期>'];
 const html=await myCoursesHtml(ctx({courses:[card({credit:0,hours:0,chapters:0,terms:terms.map(term_name=>({term_name,school_year:'2026-2027'}))})]}),'all','');
 assert.equal([...html.matchAll(/<span>2026—2027 学年<\/span>/g)].length,4);
 assert.equal([...html.matchAll(/<span>第1学期<\/span>/g)].length,2);
 assert.equal([...html.matchAll(/<span>第2学期<\/span>/g)].length,2);
 assert.match(html,/&lt;未知学期&gt;/);assert.doesNotMatch(html,/<未知学期>/);
 assert.match(html,/<strong>0\.00<\/strong> 学分<p class="cell-sub">0 学时 · 0 章/);
 assert.match(html,/5 个学期/);assert.match(html,/申报后审核/);
});

test('按学年筛选：只列这个学年开过的课；教务课在教务课页签', async () => {
  const data = {courses: [card(), card({identity: 'JW|K1', origin: 'JW', course_name: '高等数学', years: ['2025-2026'], terms: [{term_name: '2025-2026-1', school_year: '2025-2026'}]})]};
  assert.equal([...(await myCoursesHtml(ctx(data), 'cx', '2023-2024')).matchAll(/class="my-course-name"/g)].length, 1);
  const jw = await myCoursesHtml(ctx(data), 'jw', '');
  assert.match(jw, /高等数学/);
  assert.doesNotMatch(jw, /二维绘图/);
});

test('课程来源页统一学年筛选，空状态可认领超星并保留当前筛选学年',async()=>{
 const c=ctx({courses:[]});c.me={user:{staff_no:'T1'}};
 for(const tab of ['jw','cx']){
  const html=await myCoursesHtml(c,tab,'2024-2025');assert.match(html,/id="filters"/);assert.match(html,/<option value="2024-2025" selected/);assert.match(html,/course-empty/);assert.match(html,/查看全部学年/);assert.doesNotMatch(html,/pagination|todo-chips/);
  assert.equal(html.includes('data-action="cx-claim"'),tab==='cx');
 }
 c.me.user={};assert.doesNotMatch(await myCoursesHtml(c,'cx',''),/data-action="cx-claim"/);
});

test('申报期限：截止的课不出申报按钮，补报中改成补报，到期前提醒', async () => {
  const data = {courses: [card({window: {state: 'closed', deadline: '2025-09-30'}}),
    card({identity: 'CX|茶艺', course_name: '茶艺', window: {state: 'reopened', deadline: '2025-09-30', reopen_until: '2025-10-20'}}),
    card({identity: 'CX|焊接', course_name: '焊接', window: {state: 'open', deadline: '2026-09-30'}})],
    deadline_reminders: [{school_year: '2025-2026', state: 'open', deadline: '2026-09-30', days_left: 5}]};
  const html = await myCoursesHtml(ctx(data), 'cx', '');
  assert.match(html, /已于 2025-09-30 截止/);
  assert.doesNotMatch(html, /data-id="0">申报课程/);
  assert.match(html, /data-id="1">补报为培训课程/);
  assert.match(html, /data-id="2">申报课程/);
  assert.match(html, /2025-2026 学年的课程申报将于 2026-09-30 截止，还剩 5 天/);
});


function formContext(qualifications = []) {
 const requests=[], c={...ctx({items:[],counts:{}}),me:{user:{id:'teacher',name:'测试教师'},role:{kind:'teacher'}},can:()=>true,
  field:(name,label,type='text',value='',o={})=>`<div class="form-field"><label>${esc(label)}</label><input name="${name}" value="${esc(value)}" ${o.readonly?'readonly':''} ${o.required===false?'':'required'}>${esc(o.hint||'')}</div>`,
  projectField:async(_c,value)=>`<select name="project_code"><option value="${esc(value)}" selected>原项目</option></select>`,
  formModal:(title,body,save,options)=>{c.form={title,body,save,options}},closeModal:()=>{},toast:()=>{},renderKeep:async()=>{},modal:()=>{},eventsHtml:()=>'',requests};
 c.api=async(url,options)=>{
  requests.push({url,options});if(options)return {item:{id:'saved'}};
  if(url.startsWith('/qualifications'))return {items:qualifications};
  if(url==='/applications/saved')return {item:{id:'saved',name:'合成申请',data:{}},permissions:{},fields:[],attachments:[],events:[],progress:p};
  return {items:[],counts:{}};
 };
 return c;
}

test('学院与学校审批复用课件字段补录审查，未勾选不覆盖原记录，教研室和退回不出现补录',async()=>{
 for(const [kind,level,action,recordable] of [['college','学院审批','app-approve',true],['school','学校审批','app-approve',true],['dept','教研室审核','app-approve',false],['college','学院审批','app-return',false]]){
  const c=formContext();c.me={user:{id:'reviewer'},role:{kind}};c.reasonFields=()=>'<textarea name="reason"></textarea>';
  const d={item:{id:'review-course',name:'待审课程',version:7,data:{courseware:{checked:false}}},flow:'course',label:'培训课程申报',state_label:'待审批',permissions:{approve:true,return:true},fields:[],attachments:[],events:[],progress:{...p,nodes:[{label:level,state:'current'}]}};
  c.api=async(url,options)=>{c.requests.push({url,options});return d};
  await applicationAction('app-detail','review-course',c);await applicationAction(action,'review-course',c);
  assert.equal(c.form.body.includes('补充课件审查记录'),recordable);
  if(recordable){
   await assert.rejects(()=>c.form.save({cw_checked:true,cw_reviewer:'',cw_on:'2026-10-18'}),/审查人/);
   await c.form.save({reason:'审查通过',cw_checked:true,cw_reviewer:'学院审查组',cw_on:'2026-10-18',cw_ref:'KJ-001'});
   const written=c.requests.find(x=>x.options).options.body;assert.equal(written.expected_version,7);assert.deepEqual(written.courseware,{checked:true,reviewer:'学院审查组',reviewed_on:'2026-10-18',reference:'KJ-001'});
   c.requests.length=0;await c.form.save({reason:'按已有材料办理',cw_checked:false});assert.equal('courseware' in c.requests.find(x=>x.options).options.body,false);
  }
 }
});

test('手填课程补正保留项目、零学时、审查资料和版本，不自动重新提交',async()=>{
 const c=formContext();await applyPageHtml(c,'apply_course');
 const existing={item:{id:'course-old',name:'原课程',version:7,data:{source:'manual',code:'C-OLD',project_code:'OFF-PAGE',hours:0,one_skill:true,target_groups:'原重点群体',courseware:{checked:true,reviewer:'原审查组',reviewed_on:'2026-10-01'}}},flow:'course'};
 c.api=async(url,options)=>{c.requests.push({url,options});if(url==='/applications/course-old'&&!options)return {...existing,permissions:{edit:true},fields:[],attachments:[],events:[],progress:p};if(options)return {item:{id:'saved'}};return {item:{id:'saved',name:'原课程',data:{}},permissions:{},fields:[],attachments:[],events:[],progress:p}};
 await applicationAction('app-edit','course-old',c);
 assert.match(c.form.body,/一、课程基本资料|二、课程内容与关联项目|四、已有课件审查记录/);
 assert.match(c.form.body,/name="code" value="C-OLD" readonly/);assert.match(c.form.body,/OFF-PAGE/);assert.equal(c.form.options.page,true);assert.equal(c.form.options.submit,'保存补正');
 await c.form.save({code:'C-OLD',name:'原课程',project_code:'OFF-PAGE',hours:0,teaching_mode:'practice',ideology:'none',one_skill:true,target_groups:'原重点群体',cw_checked:true,cw_reviewer:'原审查组',cw_on:'2026-10-01',cw_ref:'R1'});
 const req=c.requests.find(x=>x.options);assert.equal(req.options.method,'PUT');assert.equal(req.options.body.expected_version,7);assert.equal(req.options.body.data.hours,0);assert.equal(req.options.body.data.project_code,'OFF-PAGE');assert.deepEqual(req.options.body.data.courseware,{checked:true,reviewer:'原审查组',reviewed_on:'2026-10-01',reference:'R1'});assert.equal(c.requests.filter(x=>x.options).length,1);
});

test('已有学历课程转申报保留课程来源、面向对象和零学时',async()=>{
 const c=formContext();await applyPageHtml(c,'apply_course');teachingCourseForm({id:'term1',origin:'JW',course_name:'原课',course_code:'JW1',hours:0});
 assert.equal(c.form.options.page,true);assert.match(c.form.body,/二、培训内容与面向对象/);
 await c.form.save({hours:0,teaching_mode:'lecture',ideology:'course_ideology',aud_0:true,intro:'社会培训介绍',package:true});
 const data=c.requests.find(x=>x.options).options.body.data;assert.equal(data.source,'teaching');assert.equal(data.course_term_id,'term1');assert.equal(data.hours,0);assert.equal(data.audience,'企业职工');assert.equal(data.package,true);
});

test('基地申报仍提交原用途与校外共建信息，申请说明不混作认定依据',async()=>{
 const c=formContext();await applicationAction('app-base-new','',c);assert.equal(c.form.options.page,true);assert.match(c.form.body,/二、地点与共建信息|三、认定依据与申请说明/);
 await c.form.save({code:'BASE1',name:'合成基地',usage_practice:true,usage_ideology:true,onsite:'no',partner:'合成共建单位',level:'province',established_on:'2026-10-01',location:'合成地址',recognition:'正式共建依据',reason:'本次申请说明'});
 const data=c.requests.find(x=>x.options).options.body;assert.deepEqual(data.data.usages,['practice','ideology']);assert.equal(data.data.onsite,false);assert.equal(data.data.partner,'合成共建单位');assert.equal(data.data.recognition,'正式共建依据');assert.equal(data.reason,'本次申请说明');
});

test('培训师展示资质机构与有效期，补正保留未出现在当前列表的原引用',async()=>{
 const c=formContext([{id:'new',name:'新<证书>',issuer:'发证<单位>',expires:'2027-01-01'}]);
 const existing={item:{id:'trainer-old',version:3,data:{source:'internal',qualification_ids:['old'],qualifications:[{id:'old',name:'原资质',issuer:'原机构',expires:null}],directions:['community'],qualification_basis:'原资格依据'}},flow:'trainer'};
 const original=c.api;c.api=async(url,options)=>url==='/applications/trainer-old'&&!options?existing:original(url,options);
 await applicationAction('app-edit','trainer-old',c);
 for(const text of ['新&lt;证书&gt;','发证&lt;单位&gt;','2027-01-01','原机构','长期有效','name="qual_old" checked','当前状态请核实'])assert.ok(c.form.body.includes(text),text);
 await c.form.save({dir_community:true,qualification_basis:'原资格依据',experience:'授课经历'},{querySelectorAll:()=>[{name:'qual_old'},{name:'qual_new'}]});
 const body=c.requests.find(x=>x.options).options.body;assert.deepEqual(body.data.qualification_ids,['old','new']);assert.equal(body.expected_version,3);assert.equal(c.requests.filter(x=>x.options).length,1);
});

test('资质读取失败时阻止打开不完整的培训师表单，原申请不会被覆盖',async()=>{
 const c=formContext();c.api=async()=>{throw Error('离线')};await assert.rejects(()=>applicationAction('app-trainer-new','internal',c),/资质暂未读取/);assert.equal(c.form,undefined);
});

test('四类申报页不重复标题或展开大空卡片，培训师已有单据只沿原单办理',async()=>{
 for(const key of ['apply_course','apply_project','apply_base','apply_trainer']){
  const c=formContext(),html=await applyPageHtml(c,key);assert.match(html,/申报记录/);assert.doesNotMatch(html,/<h2>申报培训|<h2>申请培训|apply-steps|empty-art/);
  if(key==='apply_course'){assert.match(html,/从我的课程导入/);assert.match(html,/手动填写课程/);assert.match(html,/<details class="card apply-approved">/)}
 }
 for(const state of ['DEPT','ACTIVE','RETURNED','WITHDRAWN']){
  const c=formContext();c.api=async()=>({items:[{id:'t1',name:'本人培训师',flow:'trainer',state,state_label:'合成状态',progress:{text:'合成进度',tone:state==='ACTIVE'?'green':'blue'},info:{}}]});
  const html=await applyPageHtml(c,'apply_trainer');assert.match(html,/一人一单/);assert.doesNotMatch(html,/data-id="trainer\|"|新申报培训师/);assert.match(html,['RETURNED','WITHDRAWN'].includes(state)?/补正原申请/:/查看原申请/);
 }
});

test('条件必填跟随选择且不清空已填写内容',t=>{
 const original=globalThis.document,fields=Object.fromEntries(['partner','target_groups','cw_reviewer','cw_on'].map(n=>[n,{value:'原来已填内容',required:false,closest:()=>({querySelector:()=>({querySelector:()=>null,insertAdjacentHTML(){}})})}]));
 const chosen={onsite:'no',one_skill:true,cw_checked:true};let changed;
 const form={querySelector:selector=>selector.startsWith('[name=')?fields[selector.match(/name="([^"]+)/)[1]]:selector.includes('name="onsite"')?{value:chosen.onsite}:chosen[selector.match(/name="([^"]+)/)?.[1]]?{}:null,addEventListener:(_event,handler)=>{changed=handler}};
 globalThis.document={getElementById:()=>form};t.after(()=>{if(original===undefined)delete globalThis.document;else globalThis.document=original});
 bindApplicationConditions();assert.ok(Object.values(fields).every(f=>f.required));chosen.onsite='yes';chosen.one_skill=false;chosen.cw_checked=false;changed();assert.ok(Object.values(fields).every(f=>!f.required&&f.value==='原来已填内容'));
});


test('等待项目候选时切换页面，旧请求不再打开课程表单',async()=>{
 const c=formContext();let page='apply_course',resolve;c.currentPage=()=>page;c.projectField=()=>new Promise(done=>{resolve=done});
 const pending=applicationAction('app-course-new','',c);page='apply_base';resolve('<select name="project_code"></select>');await pending;assert.equal(c.form,undefined);assert.equal(c.requests.length,0);
});


test('课程候选或培训师资质晚返回时，退出或切换账号不会打开旧身份表单',async()=>{
 for(const action of ['app-course-new','app-trainer-new'])for(const nextUser of [null,'teacher-other']){
  const c=formContext();let user='teacher',resolve;c.currentPage=()=> 'apply_course';c.currentUser=()=>user;
  if(action==='app-course-new')c.projectField=()=>new Promise(done=>{resolve=()=>done('<select name="project_code"></select>')});
  else c.api=()=>new Promise(done=>{resolve=()=>done({items:[{id:'old-q',name:'旧老师资质'}]})});
  const pending=applicationAction(action,'',c);user=nextUser;resolve();await pending;assert.equal(c.form,undefined);
 }
});


test('我的申请状态筛选真实区分草稿与办理中，可恢复全部记录',async()=>{
 for(const kind of ['teacher','dept','college']){
 const c=ctx({counts:{draft:1,pending:1,returned:0,done:0},items:[{id:'draft',name:'草稿课程',state:'DRAFT',progress:{...p,tone:'gray'}},{id:'review',name:'审核课程',state:'COLLEGE',progress:p}]});
 c.me={role:{kind}};c.render=async()=>{};
 await applicationAction('app-mine-filter','draft',c);
 let html=await myApplicationsHtml(c);assert.match(html,/草稿课程/);assert.doesNotMatch(html,/审核课程/);
 await applicationAction('app-mine-filter','pending',c);
 html=await myApplicationsHtml(c);assert.match(html,/审核课程/);assert.doesNotMatch(html,/草稿课程/);
 await applicationAction('app-mine-filter','',c);
 html=await myApplicationsHtml(c);assert.match(html,/草稿课程/);assert.match(html,/审核课程/);assert.match(html,/application-status-filter/);assert.match(html,/apply-progress-copy/);assert.doesNotMatch(html,/apply-steps/);
 }
});


test('我的申请筛选与统计一致，识别已生效基地、结项退回、已备案和撤回草稿',async()=>{
 const items=[['base','已生效基地','DRAFT','green'],['returned','结项待补正','FILED','red'],['filed','已备案项目','FILED','green'],['withdrawn','已撤回申请','WITHDRAWN','gray'],['draft','未提交申请','DRAFT','gray'],['review','待学院审批','COLLEGE','blue']].map(([id,name,state,tone])=>({id,name,state,progress:{...p,tone}}));
 const c=ctx({counts:{draft:2,pending:1,returned:1,done:2},items});c.me={role:{kind:'teacher'}};c.render=async()=>{};
 try{
  for(const [filter,expected] of [['draft',['withdrawn','draft']],['pending',['review']],['returned',['returned']],['done',['base','filed']],['',items.map(x=>x.id)]]){
   await applicationAction('app-mine-filter',filter,c);
   const html=await myApplicationsHtml(c);
   for(const item of items)assert.equal(html.includes(`<strong>${item.name}</strong>`),expected.includes(item.id),`${filter}: ${item.name}`);
  }
 }finally{await applicationAction('app-mine-filter','',c)}
});

test('课程按来源与学年筛选后，名称查看仍指向原始课程索引',async()=>{
 const data={courses:[card({origin:'CX',years:['2025-2026']}),card({origin:'JW',identity:'JW|k2',course_name:'<教务课>',credit:0,hours:0,years:['2025-2026']})]};
 const html=await myCoursesHtml(ctx(data),'jw','2025-2026');
 assert.match(html,/data-action="mc-detail" data-id="1"/);assert.match(html,/&lt;教务课&gt;/);assert.doesNotMatch(html,/data-action="mc-detail" data-id="0"/);
});

test('课程详情衔接列表中的同一课程，保留原始缺值和申报前置条件',async()=>{
 const data={courses:[card({origin:'JW',course_name:'其他课程'}),card({course_name:'机械制图',course_code:'265641882',credit:2,source_credit:null,source_hours:0,source_term_name:'2026-1',years:['2026-2027'],team_names:'皮杰',team_staff_nos:'2084',created_at_source:'2026-08-05 09:35:53',edited_at_source:'2026-10-06 07:50:20',terms:[{term_name:'2026-1',school_year:'2026-2027',credit:2,hours:0,review:'approved',counted:false}]})]};
 const c=ctx(data);let rendered;c.modal=(title,body,foot)=>{rendered={title,body,foot}};
 const html=await myCoursesHtml(c,'all','2026-2027','265641882');assert.match(html,/data-action="mc-detail" data-id="1">课程详情/);assert.doesNotMatch(html,/其他课程/);assert.match(html,/学分未填写/);
 await courseAction('mc-detail','1',c);assert.equal(rendered.title,'我的课程 · 课程详情');assert.match(rendered.body,/mc-course-workspace/);assert.match(rendered.body,/皮杰（2084）/);assert.match(rendered.body,/2026-08-05 09:35:53/);assert.match(rendered.body,/超星未填写学分/);assert.match(rendered.body,/核算学分已按学校课程记录补齐/);assert.match(rendered.body,/2026-1\|2026-2027\|2\|0\|不重复计算/);assert.match(rendered.foot,/data-action="mc-apply" data-id="1">申报这门课程/);assert.match(rendered.foot,/返回课程列表/);assert.doesNotMatch(rendered.body,/其他课程|已认定积分|暂不计入授课学分/);
 const previous=rendered;await courseAction('mc-detail','99',c);assert.equal(rendered,previous);
});

test('已入库只显示真实申报结果，不伪造积分到账或重复申报',async()=>{
 const data={courses:[card({application:{id:'approved',state:'ACTIVE',state_label:'已生效'}})]};
 const c=ctx(data);let foot;c.modal=(_title,_body,value)=>{foot=value};
 const html=await myCoursesHtml(c,'cx','');assert.match(html,/已入库/);assert.match(html,/积分另行认定/);assert.match(html,/积分以实际培训业务认定结果为准/);assert.doesNotMatch(html,/已认定积分|待认定积分|data-action="mc-apply"/);
 await courseAction('mc-detail','0',c);assert.match(foot,/data-action="app-detail" data-id="approved"/);assert.doesNotMatch(foot,/data-action="mc-apply"/);
});

test('申报进度晚返回时，已离开课程页面不会重新弹出旧课程',async()=>{
 const c=ctx({courses:[card({application:{id:'pending',state:'DEPT',state_label:'待教研室审核'}})]});
 let page='credits',resolve,opened=0;c.currentPage=()=>page;c.currentUser=()=> 'teacher';c.modal=()=>opened++;
 await myCoursesHtml(c,'cx','');c.api=()=>new Promise(done=>{resolve=done});
 const loading=courseAction('mc-detail','0',c);page='home';resolve({progress:p});await loading;assert.equal(opened,0);
});


test('教师申请详情分区保留安全转义及权限，材料下载不向无权人员展示',async()=>{
 for(const allowed of [false,true]){
  const detail={item:{id:'a1',name:'课程<一>'},permissions:{upload:false},progress:p,fields:[['名称','<课程>'],['说明','完整说明']],attachments:[{name:'材料.pdf'}],events:[],applicant:{id:'teacher',name:'教师'},label:'课程申报',state_label:'审核中',org_name:'学院'};
  const c=ctx(detail);c.me={user:{id:'teacher'},role:{kind:'teacher'}};c.can=()=>allowed;c.downloads=()=>'<button>下载材料</button>';c.eventsHtml=()=>'<p>原办理记录</p>';let result;c.modal=(title,body,foot,wide,context)=>{result={body,foot,context}};
  await applicationAction('app-detail','a1',c);
  assert.match(result.body,/data-detail-section="application-materials"/);assert.match(result.body,/&lt;课程&gt;/);assert.match(result.body,/原办理记录/);assert.equal(result.body.includes('下载材料'),allowed);assert.doesNotMatch(result.foot,/app-upload|app-withdraw/);assert.equal(result.context,'课程申报 / 申请详情');
 }
});

test('教研室和学院复用教师申请详情分区，审核按钮仍只依服务端权限显示',async()=>{
 for(const kind of ['dept','college'])for(const allowed of [false,true])for(const review of [false,true]){
  const detail={item:{id:'dept-application',name:'课程<一>',version:6},permissions:{approve:review,return:review},progress:p,fields:[['名称','<课程>'],['依据说明','原认定依据']],attachments:[{name:'材料.pdf'}],events:[],applicant:{id:'teacher',name:'教师<一>'},label:'课程申报',state_label:'教研室审核中',org_name:'教研室<一>'};
  const c=formContext();c.me={user:{id:kind+'head'},role:{kind}};c.api=async()=>detail;c.can=()=>allowed;c.downloads=()=>'<button>下载材料</button>';c.eventsHtml=()=>'<p>原办理记录</p>';let result;c.modal=(title,body,foot,wide,context)=>{result={body,foot,context}};
  await applicationAction('app-detail','dept-application',c);
  for(const section of ['application-info','application-materials','application-history'])assert.match(result.body,new RegExp('data-detail-section="'+section+'"'));
  assert.match(result.body,/&lt;课程&gt;|教师&lt;一&gt;|教研室&lt;一&gt;/);assert.match(result.body,/原办理记录/);assert.equal(result.body.includes('下载材料'),allowed);
  assert.equal(result.foot.includes('app-approve'),review);assert.equal(result.foot.includes('app-return'),review);assert.doesNotMatch(result.foot,/app-edit|app-submit|app-upload|app-withdraw/);assert.equal(result.context,'课程申报 / 申请详情');
 }
});

test('教研室学院审核退回表返回只读取原申请，确认仍传原版本和办理意见',async()=>{
 for(const kind of ['dept','college'])for(const action of ['approve','return']){
 const detail={item:{id:'dept-review',name:'待审核课程',version:9},permissions:{approve:true,return:true},progress:p,fields:[],attachments:[],events:[],applicant:{id:'teacher'},label:'课程申报',state_label:'教研室审核中'};
 const c=formContext();c.me={user:{id:kind+'head'},role:{kind}};c.reasonFields=()=>'<textarea name="reason"></textarea>';c.api=async(url,options)=>{c.requests.push({url,options});return detail};
 await applicationAction('app-detail','dept-review',c);await applicationAction('app-'+action,'dept-review',c);
 assert.equal(c.form.options.contextLabel,'课程申报 / '+(action==='approve'?'通过':'退回'));await c.form.options.returnTo();assert.equal(c.requests.filter(x=>x.options).length,0);
 const reason=action==='approve'?'核对材料后通过':'请补全正式依据';await c.form.save({reason,basis:'隔离审核依据'});
 const writes=c.requests.filter(x=>x.options);assert.equal(writes.length,1);assert.equal(writes[0].url,'/applications/dept-review/actions');assert.deepEqual(writes[0].options.body,{action,expected_version:9,reason,basis:'隔离审核依据'});
 }
});

test('教研室与学院查看他人退回申请提示待申请人补正，本人申请保持待你补正',async()=>{
 for(const [kind,user,applicant] of [['dept','depthead','teacher'],['dept','depthead','depthead'],['college','collegehead','teacher'],['college','collegehead','collegehead'],['teacher','teacher','teacher']]){
  const progress={...p,text:'教研室退回，待你补正',headline:'教研室退回：请补<协议>。请补正后重新提交，会从教研室这一级接着审。',tone:'red',nodes:[p.nodes[0],{label:'教研室审核',state:'returned',reason:'请补<协议>'}]};
  const detail={item:{id:'returned',name:'退回课程',state:'RETURNED'},permissions:{edit:user===applicant,submit:user===applicant},progress,fields:[],attachments:[],events:[],applicant:{id:applicant},label:'课程申报',state_label:'退回补正'};
  const c=formContext();c.me={user:{id:user},role:{kind}};c.api=async()=>detail;let result;c.modal=(_title,body,foot)=>{result={body,foot}};await applicationAction('app-detail','returned',c);
  if(user!==applicant){assert.match(result.body,/待申请人补正/);assert.match(result.body,/请由原申请人补正后重新提交，会从教研室这一级接着审/);assert.doesNotMatch(result.body,/待你补正/)}else assert.match(result.body,/待你补正/);
  assert.match(result.body,/退回原因：请补&lt;协议&gt;/);assert.match(result.body,/查看完整审批流程/);assert.equal(result.foot.includes('app-edit'),user===applicant);assert.equal(result.foot.includes('app-submit'),user===applicant);assert.equal(detail.progress.text,'教研室退回，待你补正');
 }
});

test('学校保留原申请详情布局，教研室学院空态指向本角色已有业务菜单',async()=>{
 for(const kind of ['school']){
  const detail={item:{id:'manager-review',name:'课程'},permissions:{},progress:p,fields:[['名称','原课程']],attachments:[],events:[],applicant:{id:'teacher'},label:'课程申报'};
  const c=formContext();c.me={user:{id:'manager'},role:{kind}};c.api=async()=>detail;let body;c.modal=(_title,value)=>{body=value};await applicationAction('app-detail','manager-review',c);
  assert.match(body,/<dl class="kv mt16">/);assert.doesNotMatch(body,/detail-section-nav|detail-facts-grid/);
 }
 for(const kind of ['teacher','dept','college']){
  const c=ctx({items:[],counts:{draft:0,pending:0,returned:0,done:0}});c.me={role:{kind}};c.render=async()=>{};c.table=(_head,_rows,empty,hint)=>empty+' '+hint;await applicationAction('app-mine-filter','',c);
  const html=await myApplicationsHtml(c);if(['dept','college'].includes(kind)){assert.match(html,/培训课程管理.*培训基地管理/);assert.doesNotMatch(html,/我要申报/);if(kind==='college')assert.match(html,/培训师资库/)}else assert.match(html,/我要申报/);
 }
});

test('学校我的申请记录保留原紧凑流程布局，不显示教师状态筛选',async()=>{
 const c=ctx({counts:{draft:0,pending:1,returned:0,done:0},items:[{id:'school-application',name:'学校可见申请',state:'COLLEGE',progress:p,nodes:p.nodes}]});c.me={role:{kind:'school'}};c.render=async()=>{};await applicationAction('app-mine-filter','',c);
 const html=await myApplicationsHtml(c);assert.match(html,/学校可见申请/);assert.match(html,/apply-progress compact/);assert.match(html,/apply-steps/);assert.doesNotMatch(html,/teacher-applications|application-status-filter|apply-progress-copy/);
});

test('代登记退回申请依服务端补正提交权限或登记人识别本人，申请归属教师不变',async()=>{
 for(const kind of ['dept','college'])for(const permissions of [{edit:true},{submit:true},{}]){
  const current=kind+'head',detail={item:{id:'delegated',state:'RETURNED',data:{created_by:Object.keys(permissions).length?'other':current}},applicant:{id:'teacher',name:'原归属教师'},permissions,progress:{...p,text:'学院退回，待你补正',headline:'学院退回。请补正后重新提交，会从学院这一级接着审。'},fields:[],attachments:[],events:[]};
  const c=formContext();c.me={user:{id:current},role:{kind}};c.api=async()=>detail;let body,foot;c.modal=(_title,value,actions)=>{body=value;foot=actions};await applicationAction('app-detail','delegated',c);
  assert.match(body,/待你补正/);assert.doesNotMatch(body,/待申请人补正/);assert.match(body,/原归属教师/);assert.equal(foot.includes('app-edit'),!!permissions.edit);assert.equal(foot.includes('app-submit'),!!permissions.submit);assert.equal(detail.applicant.id,'teacher');
 }
});

test('学院课程基地外聘师表单复用现有整页表单，来源与实际审批去向一致',async()=>{
 const cases=[['app-course-new','','培训课程 / 填写资料','/applications/courses',{code:'C1',name:'课程',teacher_id:'teacher',hours:0},'已提交，等待学校审批'],['app-base-new','','培训基地 / 填写资料','/applications/bases',{code:'B1',name:'基地',teacher_id:'teacher',usage_practice:true,onsite:'yes',established_on:'2026-10-01',recognition:'正式依据'},'已提交，等待学校审批'],['app-trainer-new','external','培训师资库 / 填写资料','/applications/trainers',{name:'外聘培训师',unit:'工作单位',dir_community:true,qualification_basis:'资格依据'},'已提交，等待教务处备案审核']];
 for(const [action,id,location,url,values,message] of cases){
  const c=formContext();c.me={user:{id:'collegehead'},role:{kind:'college'}};c.teacherField=(value,name,label)=>c.field(name,label,'text',value);let toast;c.toast=value=>{toast=value};await applicationAction(action,id,c);
  assert.equal(c.form.options.page,true);assert.equal(c.form.options.contextLabel,location);assert.match(c.form.body,/class="application-form"/);assert.doesNotMatch(c.form.body,/college-form|college-detail/);await c.form.save(values,{querySelectorAll:()=>[]});
  const writes=c.requests.filter(x=>x.options);assert.equal(writes.length,1);assert.equal(writes[0].url,url);assert.equal(toast,message);if(action==='app-course-new'){assert.equal(writes[0].options.body.data.hours,0);assert.equal(writes[0].options.body.data.teacher_id,'teacher')}if(action==='app-trainer-new')assert.equal(writes[0].options.body.data.source,'external');
 }
});


test('补正表保留原审核意见并安全显示，基地提交提示与学院办理环节一致',async()=>{
 const c=formContext(),old=c.api;c.api=async(url,options)=>url==='/applications/original'?{item:{id:'original',name:'基地',state:'RETURNED',version:3,data:{usages:['practice']}},events:[{action:'退回培训基地申请',reason:'请补充<共建协议>'}]}:old(url,options);
 await applicationAction('app-edit','original',c);assert.match(c.form.body,/请补充&lt;共建协议&gt;/);assert.match(c.form.body,/保存补正不会自动提交/);
 let toast;c.toast=value=>{toast=value};await applicationAction('app-base-new','',c);
 await c.form.save({usage_practice:true,code:'BASE',name:'基地',onsite:'yes',established_on:'2026-10-01',recognition:'隔离依据'});assert.equal(toast,'已提交，等待学院审批');
});

test('基地、课程、培训师申请表都有选填封面，保存成功后才上传，上传失败不重复建单',async()=>{
 for(const [open,id,label] of [['app-base-new','','基地封面'],['app-course-new','','课程封面'],['app-trainer-new','internal','培训师头像']]){
  const c=formContext();await applicationAction(open,id,c);assert.match(c.form.body,new RegExp('name="cover_file"'));assert.match(c.form.body,new RegExp(label));
 }
 const toasts=[],c=formContext();c.toast=(m,bad)=>toasts.push([m,bad]);
 const file={name:'封面.png',size:1024};
 let uploads=0;const api=c.api;c.api=async(url,options)=>{if(url.startsWith('/social/images/')){uploads++;throw Error('服务暂不可用')}return api(url,options)};
 await applicationAction('app-base-new','',c);
 await c.form.save({code:'B2',name:'带封面基地',usage_practice:true,onsite:'yes',established_on:'2026-10-01',recognition:'依据',cover_file:file});
 assert.equal(uploads,1);assert.ok(toasts.some(([m,bad])=>/图片上传失败/.test(m)&&bad));
 assert.equal(c.requests.filter(r=>r.url==='/applications/bases'&&r.options).length,1);
 const bad=formContext();await applicationAction('app-base-new','',bad);
 await assert.rejects(()=>bad.form.save({code:'B3',name:'坏图',usage_practice:true,onsite:'yes',established_on:'2026-10-01',recognition:'依据',cover_file:{name:'a.gif',size:10}}),/PNG、JPG/);
 assert.equal(bad.requests.filter(r=>r.options).length,0);
});
