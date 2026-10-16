import test from 'node:test';
import assert from 'node:assert/strict';
import {parseTrainingRows,socialPage,socialAction} from '../../frontend/social-training.js';
const header='单元编号\t课程编号\t班级编号\t模块名称\t培训日期\t学员编号\t本校全日制生\t准毕业生例外\t实名签到\t学时达标\t全程参训\t结业通过\t重点群体\t剔除原因\t教师工号\t岗位\t人员类型\t佐证说明';
const row=(teacher='J001',learner='L001')=>['U1','C1','CL1','技能一','2026-09-01',learner,'否','否','是','是','是','是','是','',teacher,'主讲','校内','已核验签到'].join('\t');
const teachers=[{id:'t1',staff_no:'J001'},{id:'t2',staff_no:'J002'}];
test('co-teachers share one attendance unit without multiplying learners',()=>{
 const units=parseTrainingRows([header,row(),row('J002')].join('\n'),'module',teachers);
 assert.equal(units.length,1);assert.equal(units[0].learners.length,1);assert.equal(units[0].teachers.length,2);
});
test('conflicting learner evidence and unknown teachers are rejected before preview',()=>{
 assert.throws(()=>parseTrainingRows([header,row(),row().replace('\t否\t否','\t是\t否')].join('\n'),'module',teachers),/依据不一致/);
 assert.throws(()=>parseTrainingRows([header,row('UNKNOWN')].join('\n'),'module',teachers),/工号不在授权列表/);
});
test('invalid boolean and missing columns are never coerced to valid attendance',()=>{
 assert.throws(()=>parseTrainingRows([header,row().replace('\t是\t是','\t1\t是')].join('\n'),'module',teachers),/判断项/);
 assert.throws(()=>parseTrainingRows([header,'short'].join('\n'),'module',teachers),/18列/);
});
test('external instructors can be recorded with a stable school reference',()=>{
 const units=parseTrainingRows([header,row('EXT-001').replace('\t校内\t','\t外聘\t')].join('\n'),'module',teachers);
 assert.equal(units[0].teachers[0].staff_type,'external');assert.equal(units[0].teachers[0].teacher_id,'EXT-001');
});

const escapeHtml=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
function renderContext(data={},permissions=[]){
 const workspace={projects:[],courses:[],resources:[],claims:[],annuals:[],policies:[],my_duties:[],course_stats:{},decisions:{},states:{ACTIVE:'已启用',DRAFT:'草稿'},pagination:{total:0,page:1,size:20},resource_pagination:{total:0,page:1,size:200},...data};
 const requests=[];
 return {
  requests,esc:escapeHtml,can:permission=>permissions.includes(permission),me:{user:{},role:{kind:'school'}},
  api:async url=>{requests.push(url);return url==='/social/ledger-summary'?{items:[],note:''}:workspace},
  icon:()=>'<svg class="icon"></svg>',
  act:(label,action,id='')=>'<button data-action="'+escapeHtml(action)+'" data-id="'+escapeHtml(id)+'">'+escapeHtml(label)+'</button>',
  table:(headers,rows)=>'<table><thead><tr>'+headers.map(h=>'<th>'+escapeHtml(h)+'</th>').join('')+'</tr></thead><tbody>'+rows.map(row=>'<tr>'+row.map(cell=>'<td>'+cell+'</td>').join('')+'</tr>').join('')+'</tbody></table>',
  note:escapeHtml,pageHead:(description,buttons)=>'<header>'+escapeHtml(description)+buttons+'</header>',
  orgName:id=>id,teacherName:id=>id,periodName:id=>id,render:async()=>{},closeModal:()=>{},field:()=>'',teacherField:()=>''
 };
}
async function renderSocial(section,context){
 await socialAction('social-list-reset','',context);
 return socialPage(section,context);
}
function summaryValues(html){
 return Object.fromEntries([...html.matchAll(/<article class="social-stat">[\s\S]*?<span>([^<]+)<\/span><strong>([^<]+)<\/strong>/g)].map(match=>[match[1],match[2]]));
}

test('现有项目跟踪按财务职责提供核验选项，非财务不显示认定字段',async()=>{
 for(const duties of [['finance'],['coordinator']]){
  const c=renderContext({my_duties:duties,policies:[{id:'p',state:'ACTIVE',name:'学校校历'}]},['assessment.review']);
  c.me={user:{id:'reviewer'},role:{kind:'school'}};
  await renderSocial('projects',c);
  let form,posted,buttons;c.modal=(_title,_body,footer)=>{buttons=footer};c.downloads=()=>'';c.eventsHtml=()=>'';
  c.field=(name,label,type,value,options={})=>'<label>'+escapeHtml(label)+'<input name="'+name+'">'+(options.options||[]).map(x=>escapeHtml(x[1])).join('')+'</label>';
  c.formModal=(title,body,save)=>{form={title,body,save}};
  const item={id:'project',owner_id:'teacher',org_id:'college',state:'CLOSED',version:4,data:{name:'隔离项目',mode:'module',category:'other'},closeout:{}};
  c.api=async(url,options)=>{if(options){posted=options.body;return {}}return {item,kind:'social_project',state_label:'已结项',facts:{effective:0,excluded:0,units:[],followups:[]},attachments:[],events:[]}};
  await socialAction('social-detail','social_project|project',c);
  assert.match(buttons,/登记投诉与跟踪/);
  await socialAction('social-note','',c);
  if(duties[0]==='finance'){
   assert.match(form.body,/name="settlement_result"/);assert.match(form.body,/已有正式批准的例外/);
   await form.save({kind:'settlement',settlement_result:'exempt',basis:'财务例外批准文号',reason:'正式核验'});
   assert.equal(posted.settlement_result,'exempt');assert.equal(posted.expected_version,4);
  }else assert.doesNotMatch(form.body,/name="settlement_result"/);
 }
});
const base=(id,onsite,data={})=>({id,kind:'base',name:'培训基地'+id,code:'BASE-'+id,org_id:'承办学院',state:'ACTIVE',data:{onsite,recognition:'学校认定文件',location:'培训中心',...data}});

test('没有开放周期时明确阻止新建申报，有未来周期时提示手动确认',async()=>{
 const c=await pickerContext('social-claim-new',[{id:'p1',code:'P1',name:'隔离项目',cohort:'第一期'}]);c.periods=[];
 await assert.rejects(()=>socialAction('social-claim-new','',c),/没有开放的考核周期/);
 c.periods=[{id:'future',name:'未来周期',state:'OPEN',start_date:'2099-01-01',end_date:'2099-12-31'}];
 await socialAction('social-claim-new','',c);
 assert.match(c.modals.at(-1).body,/当前适用周期不能唯一确定/);
});

test('学校可在口径草稿补校历，生效口径提供显式停用入口',async()=>{
 const c=renderContext({my_duties:['coordinator']},['rules.manage']);c.me={user:{id:'calendar-editor'},role:{kind:'school'}};
 await renderSocial('policy',c);let footer,form,posted;
 const item={id:'calendar-policy',version:3,state:'DRAFT',name:'学校口径',data:{calendar_start:null,calendar_end:null,holidays:[],workdays:[]}};
 c.modal=(_title,_body,buttons)=>{footer=buttons};c.downloads=()=>'';c.eventsHtml=()=>'';
 c.field=(name,label,_type,value)=>label+':'+String(value??'')+';';
 c.formModal=(title,body,save)=>{form={title,body,save}};
 c.api=async(_url,options)=>{if(options){posted=options.body;return {item}}return {item,attachments:[],events:[],state_label:'草稿'}};
 await socialAction('social-detail','social_policy|'+item.id,c);
 assert.match(footer,/补充学校工作日历/);
 await socialAction('social-policy-calendar','',c);
 assert.match(form.body,/校历开始日期/);assert.doesNotMatch(form.body,/2026-01-01/);
 await form.save({calendar_start:'2026-01-01',calendar_end:'2026-12-31',calendar_reference:'学校校历',holidays:'2026-10-01\n2026-10-02',workdays:'',reason:'核对校历'});
 assert.deepEqual(posted.holidays,['2026-10-01','2026-10-02']);assert.equal(posted.expected_version,3);
 item.state='ACTIVE';await socialAction('social-detail','social_policy|'+item.id,c);
 assert.match(footer,/停用此口径/);assert.doesNotMatch(footer,/补充学校工作日历/);
});

test('只读账号在有记录和空列表时均不出现登记入口，有权限账号仍可登记',async()=>{
 const registrations={projects:'social-project-new',courses:'social-course-new',bases:'social-resource-new',outcomes:'social-resource-new',annual:'social-annual-new',policy:'social-policy-new'};
 for(const [section,action] of Object.entries(registrations)){
  const html=await renderSocial(section,renderContext());
  assert.ok(!html.includes('data-action="'+action+'"'),section+'不应出现登记入口');
 }
 const data={resources:[base('1',true)],pagination:{total:1,page:1,size:20}};
 const readonly=await renderSocial('bases',renderContext(data));
 assert.ok(!readonly.includes('data-action="social-resource-new"'));
 assert.match(readonly,/data-action="social-detail"/);
 const writable=await renderSocial('bases',renderContext(data,['records.write']));
 assert.match(writable,/data-action="social-resource-new"/);
 assert.match(await renderSocial('courses',renderContext({},['records.write'])),/data-action="social-course-new"/);
});

test('基地名称、编号、认定依据和地点始终作为文本显示',async()=>{
 const name='<img src=x onerror="alert(1)">',recognition='<script>alert("认定")</script>',location='地点" autofocus onfocus="alert(2)',code='编号<svg onload=alert(3)>';
 const resource={...base('1',true,{recognition,location}),name,code,org_id:'学院<script>alert(4)</script>'};
 const html=await renderSocial('bases',renderContext({resources:[resource],pagination:{total:1,page:1,size:20}}));
 for(const value of [name,recognition,location,code,resource.org_id]){
  assert.ok(html.includes(escapeHtml(value)),'动态内容应保留并转义');
  assert.ok(!html.includes(value),'动态内容不应成为页面标签或属性');
 }
});

test('基地校内、校外及未知类型分别展示，未知类型不计入校内或校外',async()=>{
 const resources=[base('inside',true),base('outside',false),base('unknown',undefined),base('null',null),base('text','false')];
 const html=await renderSocial('bases',renderContext({resources,pagination:{total:45,page:1,size:20}}));
 assert.deepEqual(summaryValues(html),{'基地总数':'45','思政实践教学基地':'0','本年新设':'0'});
 const labels=[...html.matchAll(/<span class="social-badge"[^>]*>(校内基地|校外基地|类型待补充)<\/span>/g)].map(match=>match[1]);
 assert.deepEqual(labels,['校内基地','校外基地','类型待补充','类型待补充','类型待补充']);
});

test('基地卡片显示用途、设立日期、共建单位，统计思政基地和本年新设，审批中的申请不计入',async()=>{
 const year=String(new Date().getFullYear());
 const resources=[base('a',false,{usages:['practice','ideology'],established_on:year+'-03-01',partner:'湘茶集团'}),base('b',true,{usages:['practice'],established_on:'2020-01-01'}),
  {...base('c',true,{usages:['ideology'],established_on:year+'-09-01',application:true}),state:'COLLEGE'}];
 const html=await renderSocial('bases',renderContext({resources,pagination:{total:3,page:1,size:200}}));
 assert.deepEqual(summaryValues(html),{'基地总数':'3','思政实践教学基地':'1','本年新设':'1'});
 assert.match(html,/用途：实践教学基地、思政实践教学基地/);assert.match(html,/共建单位：湘茶集团/);assert.match(html,/设立日期：2020-01-01/);
 assert.match(html,/data-action="app-detail" data-id="c">看进度/);
});

test('分页统计区分授权总数、本页记录和本页已结项',async()=>{
 const projects=[{id:'p1',cohort:'第一期',state:'CLOSED',state_label:'已结项',data:{name:'项目一',code:'P1',mode:'module'}},{id:'p2',cohort:'第二期',state:'DRAFT',data:{name:'项目二',code:'P2',mode:'module'}}];
 const html=await renderSocial('projects',renderContext({projects,pagination:{total:82,page:3,size:20}}));
 assert.deepEqual(summaryValues(html),{'培训项目总数':'82','本页记录':'2','本页已结项':'1'});
 assert.match(html,/“本页”数量随分页与检索变化/);
 assert.match(html,/共 82 项 · 第 3 页/);
});

test('检索值经转义且按原值请求，空结果可清空检索返回第一页',async()=>{
 const context=renderContext(),query='"><img src=x onerror="alert(1)">&关键词';
 await renderSocial('bases',context);
 const documentDescriptor=Object.getOwnPropertyDescriptor(globalThis,'document');
 Object.defineProperty(globalThis,'document',{configurable:true,value:{getElementById:id=>{assert.equal(id,'social-query');return {value:'  '+query+'  '}}}});
 try{await socialAction('social-list-apply','',context)}finally{
  if(documentDescriptor)Object.defineProperty(globalThis,'document',documentDescriptor);else delete globalThis.document;
 }
 const html=await socialPage('bases',context);
 assert.ok(html.includes('value="'+escapeHtml(query)+'"'));
 assert.match(html,/id="social-query"/);
 assert.ok(!html.includes(query));
 assert.equal(new URL(context.requests.at(-1),'http://localhost').searchParams.get('q'),query);
 assert.match(html,/没有找到匹配的记录/);
 assert.match(html,/<button data-action="social-list-reset"[^>]*>查看全部<\/button>/);
 assert.deepEqual(summaryValues(html),{});
 await socialAction('social-list-page','3',context);
 await socialAction('social-resource-page','2',context);
 await socialAction('social-list-reset','',context);
 const reset=await socialPage('bases',context),url=new URL(context.requests.at(-1),'http://localhost');
 assert.equal(url.searchParams.get('q'),'');
 assert.equal(url.searchParams.get('page'),'1');
 assert.equal(url.searchParams.get('resource_page'),'1');
 assert.match(reset,/还没有培训基地/);
 assert.ok(!reset.includes('data-action="social-list-reset"'));
});

test('课程资源统计只汇总所列课程，未列课程和资源明细不会混入数量',async()=>{
 const courses=[{code:'C1',name:'课程一'},{code:'C2',name:'课程二'},{code:'C3',name:'暂无统计的课程'}];
 const course_stats={C1:{resources:7,videos:2,minutes:0},C2:{resources:0,videos:0,minutes:0},OTHER:{resources:500,videos:400,minutes:9999}};
 const resources=[{id:'r1',kind:'course_resource',name:'其他课程资源',data:{course_code:'OTHER',resource_type:'video',duration_minutes:99}}];
 const html=await renderSocial('courses',renderContext({courses,course_stats,resources,pagination:{total:61,page:1,size:20}}));
 assert.deepEqual(summaryValues(html),{'培训课程总数':'61','本页课程资源':'7','本页视频资源':'2'});
 assert.match(html,/本页课程资源/);
 assert.match(html,/本页视频资源/);
 assert.match(html,/暂无统计的课程/);
});

async function pickerContext(action,items){
 const context=renderContext({projects:[{id:'old-project',data:{code:'OLD',name:'工作台中的旧项目'}}],policies:[{id:'policy-1',name:'隔离口径',state:'ACTIVE'}]});
 await renderSocial('courses',context);
 context.requests.length=0;
 context.modals=[];context.posts=[];context.renders=0;context.periods=[{id:'period2026',name:'隔离年度',state:'OPEN',start_date:'2026-01-01',end_date:'2026-12-31'}];
 context.reasonFields=()=>'';
 context.render=async()=>{context.renders++};
 context.field=(name,_label,type='text',value='',options={})=>type==='select'
  ?'<select id="f-'+name+'" name="'+name+'">'+options.options.map(([key,label])=>'<option value="'+escapeHtml(key)+'"'+(key===value?' selected':'')+'>'+escapeHtml(label)+'</option>').join('')+'</select>'
  :'<input name="'+name+'" value="'+escapeHtml(value)+'">';
 context.formModal=(title,body,save,options)=>{context.modals.push({title,body,save,options})};
 context.lookup=async url=>({items:[],q:new URL(url,'http://localhost').searchParams.get('q')||'',page:Number(new URL(url,'http://localhost').searchParams.get('page')||1),size:20,total:0});
 context.api=async(url,options)=>{
  context.requests.push(url);
  if(options){context.posts.push({url,...options});return {}}
  if(['/social/project-options','/social/project-options?mine=true'].includes(url))return {items,q:'',page:1,size:20,total:450};
  return context.lookup(url);
 };
 await socialAction(action,'',context);
 return context;
}
function pickerDocument(t,name,value,label){
 const original=Object.getOwnPropertyDescriptor(globalThis,'document');
 const target={innerHTML:''},query={value:'',focused:0,focus(){this.focused++}},select={value,selectedOptions:[{textContent:label}]};
 const fields={'social-project-picker':target,'social-project-query':query,['f-'+name]:select,'f-code':{value:'已填写课程编号'},'f-name':{value:'已填写课程名称'}};
 Object.defineProperty(globalThis,'document',{configurable:true,value:{getElementById:id=>fields[id]}});
 t.after(()=>{if(original)Object.defineProperty(globalThis,'document',original);else delete globalThis.document});
 return {target,query,select,fields};
}

test('课程和个人积分从项目候选接口取值，分别提交项目编号和项目标识',async()=>{
 const project={id:'project-450',code:'PROJECT-450',name:'候选<img src=x onerror="alert(1)">',cohort:'第三期'};
 for(const [action,name,key,url] of [['social-course-new','project_code','code','/social/courses'],['social-claim-new','project_id','id','/social/claims']]){
  const context=await pickerContext(action,[project]),modal=context.modals[0];
  assert.deepEqual(context.requests,[action==='social-claim-new'?'/social/project-options?mine=true':'/social/project-options']);
  assert.ok(modal.body.includes('<select id="f-'+name+'" name="'+name+'">'));
  assert.ok(modal.body.includes('<option value="'+project[key]+'">'));
  assert.ok(modal.body.includes(escapeHtml(project.name)));
  assert.ok(!modal.body.includes(project.name));
  assert.ok(!modal.body.includes('工作台中的旧项目'));
  const values=name==='project_code'?{code:'COURSE-1',name:'新课程',project_code:project.code}:{project_id:project.id,period_id:'period-1',policy_id:'policy-1',auxiliary_rows:''};
  // 个人积分申报一步提交：表单里直接带认定表照片，认定表说明默认用文件名。
  const fileForm=file=>({querySelector:sel=>sel==='#f-file'?{files:[file]}:null,querySelectorAll:()=>[]});
  if(name==='project_id'){
   // 文件不合格时在建申报之前就拦下，不留一条没有认定表的草稿。
   await assert.rejects(modal.save(values,fileForm({name:'认定表.heic',size:1000})),/\.jpg、\.png 或 \.pdf/);
   await assert.rejects(modal.save(values,fileForm({name:'认定表.pdf',size:11*1024*1024})),/超过 10 兆字节/);
   assert.equal(context.posts.length,0);
  }
  const form=name==='project_id'?fileForm({name:'认定表.jpg',size:2000}):undefined;
  await modal.save(values,form);
  assert.equal(context.posts[0].url,url);
  if(name==='project_id')assert.equal(context.posts[0].body.recognition_form_reference,'认定表.jpg');
  assert.equal(context.posts[0].method,'POST');
  assert.equal(context.posts[0].body[name],project[key]);
  assert.ok(!((name==='project_code'?'project_id':'project_code') in context.posts[0].body));
 }
});

test('项目检索及翻页保留已选项目和其他表单值，检索文字转义并恢复焦点',async t=>{
 const selected={id:'selected-id',code:'SELECTED',name:'原已选项目',cohort:'一期'},other={id:'other-id',code:'OTHER',name:'另一项目',cohort:'二期'};
 const context=await pickerContext('social-course-new',[selected]),label='原已选项目 <保留> · SELECTED · 一期';
 const dom=pickerDocument(t,'project_code',selected.code,label),query='新项目"><img src=x>&';
 dom.query.value=' '+query+' ';
 context.lookup=async url=>{const params=new URL(url,'http://localhost').searchParams;return {items:[other],q:params.get('q'),page:Number(params.get('page')),size:20,total:60}};
 await socialAction('social-project-lookup','3',context);
 let request=new URL(context.requests.at(-1),'http://localhost');
 assert.equal(request.searchParams.get('q'),query);
 assert.equal(request.searchParams.get('page'),'1');
 assert.ok(dom.target.innerHTML.includes('<option value="SELECTED" selected>'+escapeHtml(label)+'</option>'));
 assert.ok(dom.target.innerHTML.includes('value="'+escapeHtml(query)+'"'));
 assert.ok(!dom.target.innerHTML.includes(query));
 await socialAction('social-project-lookup','2',context);
 request=new URL(context.requests.at(-1),'http://localhost');
 assert.equal(request.searchParams.get('page'),'2');
 assert.ok(dom.target.innerHTML.includes('<option value="SELECTED" selected>'));
 assert.match(dom.target.innerHTML,/共 60 项 · 第 2 页/);
 assert.equal(dom.fields['f-code'].value,'已填写课程编号');
 assert.equal(dom.fields['f-name'].value,'已填写课程名称');
 assert.equal(context.modals.length,1,'检索不能重新打开整张表单');
 assert.equal(context.renders,0,'检索不能刷新整个页面');
 assert.equal(dom.query.focused,2);
 context.lookup=async()=>({items:[selected],q:query,page:1,size:20,total:1});
 await socialAction('social-project-lookup','1',context);
 assert.equal((dom.target.innerHTML.match(/<option value="SELECTED"/g)||[]).length,1,'已选项目出现在结果中时不重复加入');
});

test('较晚返回的旧项目候选响应不能覆盖新检索结果或夺取焦点',async t=>{
 const context=await pickerContext('social-course-new',[]),dom=pickerDocument(t,'project_code','','请选择一个项目'),pending=[];
 context.lookup=url=>new Promise(resolve=>pending.push({url,resolve}));
 dom.query.value='较早检索';
 const first=socialAction('social-project-lookup','1',context);
 dom.query.value='最新检索';
 const second=socialAction('social-project-lookup','1',context);
 assert.equal(pending.length,2);
 pending[1].resolve({items:[{id:'new',code:'NEW',name:'最新候选项目',cohort:'一期'}],q:'最新检索',page:1,size:20,total:1});
 await second;
 const latest=dom.target.innerHTML;
 assert.match(latest,/最新候选项目/);
 pending[0].resolve({items:[{id:'old',code:'OLD',name:'过期候选项目',cohort:'一期'}],q:'较早检索',page:1,size:20,total:1});
 await first;
 assert.equal(dom.target.innerHTML,latest);
 assert.equal(dom.query.focused,1);
});

test('候选请求返回时表单已关闭，不再写入旧选择器或恢复焦点',async t=>{
 const context=await pickerContext('social-claim-new',[]),dom=pickerDocument(t,'project_id','','请选择一个项目');
 let resolve;
 context.lookup=()=>new Promise(done=>{resolve=done});
 const pending=socialAction('social-project-lookup','1',context);
 delete dom.fields['social-project-picker'];
 resolve({items:[],q:'',page:1,size:20,total:0});
 await pending;
 assert.equal(dom.target.innerHTML,'');
 assert.equal(dom.query.focused,0);
});

test('超星学习通导出表按表头别名识别课程、视频数和多种时长写法',async()=>{
 const {parseChaoxingCourses,chaoxingMinutes}=await import('../../frontend/social-training.js');
 const text=['课程列表','课程名称\t课程ID\t主讲教师\t视频个数\t视频总时长（分钟）\t章节数\t选课人数','数控加工\t1001\t张老师\t12\t01:30:30\t6\t1,200','电工基础\t1002\t李老师\t3\t45分钟\t\t80','安全教育\t1003\t\t\t\t\t'].join('\r\n');
 const rows=parseChaoxingCourses(text,'P1');
 assert.deepEqual(rows[0],{code:'1001',name:'数控加工',project_code:'P1',source:'chaoxing',teacher:'张老师',video_count:12,video_minutes:90.5,chapters:6,learners:1200});
 assert.equal(rows[1].video_minutes,45);assert.equal(rows[1].chapters,null);
 assert.equal(rows[2].video_count,null);assert.equal(rows[2].video_minutes,null);
 const csv='﻿课程名,课程编号,教师,视频数量,总时长,学习人数\n"焊接,进阶",C9,王老师,2,1小时20分钟,30';
 assert.deepEqual(parseChaoxingCourses(csv,'P2').map(r=>[r.name,r.code,r.video_minutes,r.learners]),[['焊接,进阶','C9',80,30]]);
 assert.equal(chaoxingMinutes('12:30'),12.5);assert.equal(chaoxingMinutes('90'),90);assert.equal(chaoxingMinutes('--'),null);
 assert.throws(()=>chaoxingMinutes('一小时'),/无法识别/);
 assert.throws(()=>parseChaoxingCourses('名称\t编号\nA\tB','P1'),/表头/);
 assert.throws(()=>parseChaoxingCourses('课程名称\t课程编号\t视频数\nA\tB\t3','P1'),/缺少视频时长/);
 assert.throws(()=>parseChaoxingCourses('课程名称\t课程编号\nA\tB\nC\tB','P1'),/重复/);
 assert.throws(()=>parseChaoxingCourses('课程名称\t课程编号\nA\tB',''),/关联项目/);
});

test('有权限账号可见超星导入和一键生成推荐口径草稿入口',async()=>{
 assert.match(await renderSocial('courses',renderContext({},['records.write'])),/data-action="social-course-chaoxing"[^>]*>超星学习通导出表导入</);
 assert.match(await renderSocial('policy',renderContext({},['rules.manage'])),/data-action="social-policy-recommended"[^>]*>一键生成推荐口径草稿</);
 assert.doesNotMatch(await renderSocial('policy',renderContext()),/social-policy-recommended/);
});


test('course and resource registration use compact editor without changing save payloads',async()=>{
 const context=await pickerContext('social-course-new',[]);
 assert.equal(context.modals[0].options.compact,true);
 assert.match(context.modals[0].body,/name="reason"/);assert.match(context.modals[0].body,/name="basis"/);
 context.orgs=[{id:'college1',kind:'college',name:'合成学院'}];context.teachers=[];
 for(const kind of ['base','achievement','course_resource']){
  await socialAction('social-resource-new',kind,context);
  const modal=context.modals.at(-1);assert.equal(modal.options.compact,true);
  await modal.save({code:'synthetic',name:'合成登记',reason:'验证',confirmed_on:'',teacher_id:'',resource_url:''});
  const request=context.posts.at(-1);assert.equal(request.url,'/social/resources');assert.equal(request.body.kind,kind);assert.equal(request.body.confirmed_on,null);assert.equal(request.body.teacher_id,null);
 }
});

test('无佐证时直接给出上传入口，有佐证才打开提交表单',async()=>{
 const c=renderContext({},['records.write','file.write']);c.me={user:{id:'owner'},role:{kind:'college'}};
 await renderSocial('projects',c);let modal,form,writes=0;
 c.modal=(title,body,foot)=>modal={title,body,foot};c.formModal=(title,body)=>form={title,body};c.downloads=()=>'';c.eventsHtml=()=>'';
 const detail={item:{id:'p',owner_id:'owner',org_id:'college',state:'DRAFT',data:{name:'<隔离项目>',mode:'module'},closeout:{}},facts:{units:[],followups:[],effective:0,excluded:0},attachments:[],events:[],state_label:'草稿'};
 c.api=async(url,options)=>{if(options)writes++;return detail};
 await socialAction('social-detail','social_project|p',c);
 assert.match(modal.body,/detail-facts/);assert.match(modal.body,/&lt;隔离项目&gt;/);assert.doesNotMatch(modal.body,/<隔离项目>/);
 await socialAction('social-transition','submit',c);
 assert.equal(modal.title,'先补充佐证材料');assert.match(modal.foot,/social-upload/);assert.match(modal.foot,/social_project\|p/);assert.equal(form,undefined);assert.equal(writes,0);
 detail.attachments=[{id:'a'}];await socialAction('social-detail','social_project|p',c);await socialAction('social-transition','submit',c);assert.ok(form);assert.equal(writes,0);
});

test('资源补正保留不在当前分页中的课程和教师关联',async()=>{
 const c=await pickerContext('social-course-new',[]);c.orgs=[];c.teachers=[];c.downloads=()=>'';c.eventsHtml=()=>'';c.modal=()=>{};
 const item={id:'r',kind:'course_resource',org_id:'college1',code:'VIDEO-OLD',name:'原视频',state:'DRAFT',version:2,data:{course_code:'OFF-PAGE',teacher_id:'off-page-teacher',resource_type:'video',duration_minutes:'12',recognition:'原依据'}};
 c.api=async()=>({item,attachments:[],events:[],state_label:'已登记'});
 await socialAction('social-detail','social_resource|r',c);await socialAction('social-resource-edit','',c);
 const body=c.modals.at(-1).body;assert.match(body,/value="OFF-PAGE" selected/);assert.match(body,/value="off-page-teacher" selected/);assert.match(body,/原关联教师（保留）/);
});

test('course import template has eight columns and maps labels to codes',async()=>{
 const {parseCourseRows}=await import('../../frontend/social-training.js');
 const head='课程编号\t课程名称\t关联项目编号\t学时\t教学方式\t思政属性\t主讲教师\t课件审查';
 const rows=parseCourseRows([head,'C1\t茶艺\tP1\t16\t实训实操\t课程思政\t王老师 J002\t已审查 学院审查组 2026-09-01','C2\t焊接\tP1'].join('\n'),teachers);
 assert.deepEqual(rows[0],{code:'C1',name:'茶艺',project_code:'P1',hours:'16',teaching_mode:'practice',ideology:'course_ideology',teacher:'王老师',teacher_id:'t2',courseware:{checked:true,reviewer:'学院审查组',reviewed_on:'2026-09-01'}});
 assert.deepEqual(rows[1],{code:'C2',name:'焊接',project_code:'P1'});
 assert.deepEqual(parseCourseRows('课程编号\t课程名称\t项目编号\nC3\t旧模板\tP1',teachers),[{code:'C3',name:'旧模板',project_code:'P1'}]);
 assert.throws(()=>parseCourseRows([head,'C1\t茶艺\tP1\t16\t上课'].join('\n'),teachers),/教学方式/);
 assert.throws(()=>parseCourseRows([head,'C1\t茶艺\tP1\t\t\t\t\t审了'].join('\n'),teachers),/课件审查/);
 assert.throws(()=>parseCourseRows('课程编号\t课程名称\nC1\tA',teachers),/表头/);
});
