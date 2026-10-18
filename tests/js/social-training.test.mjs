import test from 'node:test';
import assert from 'node:assert/strict';
import {parseTrainingRows,socialPage,socialAction,applicationProjectPicker} from '../../frontend/social-training.js';
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

test('项目补正提交按钮与确认页按退回层级续办，不误导重走学院',async()=>{
 for(const [state,returned_level,label] of [['RETURNED','school','补正后提交学校备案'],['RETURNED','college','补正后提交学院审批'],['DRAFT',undefined,'提交学院审批']]){
  const c=renderContext({},['records.read']);c.me={user:{id:'teacher'},role:{kind:'teacher'}};await renderSocial('projects',c);
  let footer,form;c.modal=(_t,_b,f)=>{footer=f};c.formModal=(title,body,save,options)=>{form={title,body,save,options}};c.downloads=()=>'';c.eventsHtml=()=>'';
  c.api=async()=>({item:{id:'returned-project',owner_id:'teacher',state,version:3,data:{name:'补正项目',code:'RET-P1',returned_level},closeout:{}},state_label:'退回补正',facts:{units:[],followups:[],effective:0,excluded:0},attachments:[{id:'proof'}],events:[]});
  await socialAction('social-detail','social_project|returned-project',c);
  assert.ok(footer.includes('data-id="submit">'+label+'</button>'));
  if(returned_level==='school')assert.doesNotMatch(footer,/提交学院审批/);
  await socialAction('social-transition','submit',c);assert.equal(form.title,label);assert.equal(form.options.submit,'确认'+label);
 }
});

test('积分原单向四角色展示认定表对应说明，教师确认表单带具体项目和申报人',async()=>{
 for(const role of ['teacher','dept','college','school']){
  const c=renderContext({},['file.write']);c.me={user:{id:'teacher'},role:{kind:role}};await renderSocial('recognition',c);
  let body,form;c.modal=(_title,html)=>{body=html};c.downloads=()=>'';c.eventsHtml=()=>'';c.formModal=(_title,html)=>{form=html};
  c.api=async()=>({item:{id:'claim',teacher_id:'teacher',project_id:'project',period_id:'period',state:'DRAFT',version:2,data:{recognition_form_reference:'认定表<第1号>与原附件对应'}},trial:{teaching:'0.07',auxiliary:'0.00',total:'0.07',basis:{facts:{project:{data:{name:'合成<项目>'}}}}},attachments:[{id:'file'}],events:[],state_label:'草稿'});
  await socialAction('social-detail','social_claim|claim',c);
  for(const value of ['积分认定资料','认定表及附件对应说明','认定表&lt;第1号&gt;与原附件对应','合成&lt;项目&gt;','period'])assert.ok(body.includes(value),value);
  assert.doesNotMatch(body,/认定表<第1号>/);
  if(role==='teacher'){
   await socialAction('social-transition','submit',c);
   assert.match(form,/teacher · 合成&lt;项目&gt;/);assert.doesNotMatch(form,/<strong>当前业务<\/strong>/);
  }
 }
});

test('积分申报四角色共用辅助明细，保留零值转义且归档读取原快照，无明细不空列',async()=>{
 const rows=[{work_date:'2025-09-01',description:'合成<辅助签到>',amount:'0.50'},{work_date:'2025-09-02',description:'合成<script>零值留痕',amount:0}];
 for(const role of ['teacher','dept','college','school']){
  const c=renderContext();c.me={user:{id:'viewer'},role:{kind:role}};await renderSocial('recognition',c);
  let body;c.modal=(_title,html)=>{body=html};c.downloads=()=>'';c.eventsHtml=()=>'';
  for(const state of ['DRAFT','ARCHIVED']){
   const detail={item:{id:'claim',teacher_id:'teacher',period_id:'period',state,data:{auxiliary:state==='ARCHIVED'?[{work_date:'2099-01-01',description:'不能替换冻结明细',amount:'99'}]:rows}},
    trial:{teaching:'0.07',auxiliary:'0.50',total:'0.57',basis:{claim_data:{auxiliary:rows}}},attachments:[],events:[],state_label:state==='ARCHIVED'?'已归档':'草稿'};
   const original=JSON.stringify(detail);c.api=async()=>detail;
   await socialAction('social-detail','social_claim|claim',c);
   for(const value of ['辅助工作明细','日期','工作说明','申报积分','2025-09-01','合成&lt;辅助签到&gt;','0.50','合成&lt;script&gt;零值留痕','<td>0</td>'])assert.ok(body.includes(value),role+' '+state+' '+value);
   assert.doesNotMatch(body,/<辅助签到>|<script>|不能替换冻结明细|work_date|description|data-json/);assert.equal(JSON.stringify(detail),original);
  }
  for(const auxiliary of [undefined,[]]){
   c.api=async()=>({item:{id:'empty',teacher_id:'teacher',state:'DRAFT',data:{auxiliary}},attachments:[],events:[]});
   await socialAction('social-detail','social_claim|empty',c);assert.doesNotMatch(body,/辅助工作明细|<th>工作说明<\/th>/);
  }
  c.api=async()=>({item:{id:'frozen-empty',teacher_id:'teacher',state:'ARCHIVED',data:{auxiliary:rows}},trial:{basis:{claim_data:{auxiliary:[]}}},attachments:[],events:[]});
  await socialAction('social-detail','social_claim|frozen-empty',c);assert.doesNotMatch(body,/辅助工作明细/);
  c.api=async()=>({item:{id:'correction',kind:'correction',state:'ARCHIVED',data:{auxiliary:rows,teaching:'0.01',period_id:'period'}},attachments:[],events:[]});
  await socialAction('social-detail','social_resource|correction',c);assert.doesNotMatch(body,/辅助工作明细/);
 }
});

test('学院自评详情显示报告任务和人数依据，保留零值且公示摘要不披露原资料',async()=>{
 for(const role of ['college','school']){
  const c=renderContext();c.me={user:{id:'annual-viewer-'+role},role:{kind:role}};await renderSocial('annual',c);
  let body,form;c.modal=(_title,html)=>{body=html};c.formModal=(_title,html)=>{form=html};c.downloads=()=>'';c.eventsHtml=()=>'';
  const detail={item:{id:'annual',org_id:'college',period_id:'period',state:'REVIEW',version:2,snapshot:{},data:{target_reference:'合成<任务依据>',staff_denominator:0,staff_basis:'合成人数原件',self_report:'合成<自评报告>',other_bonus:0,compliance_failures:0,discipline_reference:'合成处理依据'}},org_name:'合成<学院>',attachments:[{id:'file'}],events:[],state_label:'职能核验'};
  c.api=async()=>detail;await socialAction('social-detail','social_annual|annual',c);
  for(const value of ['学院自评资料','合成&lt;学院&gt;','合成&lt;任务依据&gt;','合成人数原件','合成&lt;自评报告&gt;','<dt>组织人数基准</dt><dd>0</dd>','<dt>其他加分</dt><dd>0</dd>','合成处理依据'])assert.ok(body.includes(value),value);
  assert.doesNotMatch(body,/合成<自评报告>|合成<任务依据>/);
  if(role==='school'){await socialAction('social-transition','finance',c);assert.match(form,/本次办理对象/);assert.match(form,/合成&lt;学院&gt; · period/)}
  detail.public_summary=true;await socialAction('social-detail','social_annual|annual',c);
  assert.doesNotMatch(body,/学院自评资料|合成&lt;自评报告&gt;|合成&lt;任务依据&gt;|合成人数原件|合成处理依据/);
 }
});

test('教师复用年度公示清单及摘要详情，仅提供异议且不显示自评管理和原材料',async()=>{
 const item={id:'public-annual',org_id:'college',period_id:'period',state:'PUBLIC',state_label:'公示中',data:{},snapshot:{public_end:'2026-10-23',disputes:[{reason:'本人合成异议',resolved:true,resolution:'本人核实结论'}]}};
 const c=renderContext({annuals:[item],pagination:{total:1,page:1,size:20}},['assessment.read','assessment.review','file.write','records.write']);c.me={user:{id:'teacher'},role:{kind:'teacher'}};
 const html=await renderSocial('annual',c);assert.match(html,/学院考核公示/);assert.match(html,/返回政策通知/);assert.match(html,/查看公示/);assert.doesNotMatch(html,/建立学院年度自评|social-annual-new/);
 let modal,form;c.modal=(title,body,buttons)=>{modal={title,body,buttons}};c.formModal=(_title,html)=>{form=html};c.downloads=()=>'<p>原附件不能出现</p>';c.eventsHtml=()=>'<p>原核验记录不能出现</p>';
 c.api=async()=>({item,org_name:'公示<学院>',state_label:'公示中',public_summary:true,trial:{base:'82.00',bonus_awarded:'5.00',total:'87.00',grade:'良好'},attachments:[],events:[]});await socialAction('social-detail','social_annual|public-annual',c);
 assert.equal(modal.title,'学院考核公示');assert.match(modal.body,/87.00/);assert.match(modal.buttons,/登记公示异议/);assert.doesNotMatch(modal.body,/原附件不能出现|原核验记录不能出现|学院自评资料|职能部门核验进度/);assert.doesNotMatch(modal.buttons,/上传佐证|补正年度自评|财务核验|归口初核|公示完成并归档/);
 assert.match(modal.body,/公示对象/);assert.match(modal.body,/公示&lt;学院&gt;/);assert.match(modal.body,/本人合成异议/);assert.match(modal.body,/本人核实结论/);await socialAction('social-transition','dispute',c);assert.match(form,/公示&lt;学院&gt; · period/);
});

test('年度考核与积分汇总归档确认显示公示截止日，不预填已经期满的事实',async()=>{
 for(const kind of ['social_annual','social_resource']){
  const c=renderContext();c.me={user:{id:'secretary'},role:{kind:'school'}};await renderSocial('annual',c);
  let form;c.modal=()=>{};c.formModal=(_title,html,_save,options)=>{form={html,options}};c.downloads=()=>'';c.eventsHtml=()=>'';
  const item={id:'public-item',kind:'point_report',org_id:'college',period_id:'period',state:'PUBLIC',version:2,snapshot:kind==='social_annual'?{public_end:'2026-10-23'}:{},data:kind==='social_resource'?{rows:[],public_end:'2026-10-23'}:{}};
  c.api=async()=>({item,attachments:[],events:[],state_label:'公示中'});await socialAction('social-detail',kind+'|public-item',c);await socialAction('social-transition','archive',c);
  assert.match(form.html,/公示截止：2026-10-23/);assert.match(form.html,/满5个完整工作日且异议处理完毕后才能归档/);assert.equal(form.options.reasonDefault,'核对公示期限及异议处理结果，申请归档');
 }
});

test('汇总重新取数仅限原创建秘书的草稿待归口，沿原单确认原因且不自动提交',async()=>{
 for(const state of ['DRAFT','SUBMITTED','PUBLIC','ARCHIVED','VOID'])for(const own of [false,true])for(const duty of [false,true])for(const allowed of [false,true]){
  const c=renderContext({my_duties:duty?['secretary']:[]},allowed?['assessment.review']:[]);c.me={user:{id:own?'creator':'other'},role:{kind:'school'}};await renderSocial('recognition',c);
  const item={id:'original-report',kind:'point_report',org_id:'school',state,version:7,data:{created_by:'creator',year:2026,start_month:9,end_month:10,rows:[]}},detail={item,attachments:[],events:[],state_label:'合成原状态'};let buttons,form,posted;
  c.modal=(_title,_body,footer)=>{buttons=footer};c.formModal=(title,body,save,options)=>{form={title,body,save,options}};c.downloads=()=>'';c.eventsHtml=()=>'';
  c.api=async(url,options)=>{if(options)posted={url,...options};return detail};await socialAction('social-detail','social_resource|original-report',c);
  const visible=['DRAFT','SUBMITTED'].includes(state)&&own&&duty&&allowed;assert.equal(buttons.includes('data-id="refresh"'),visible);
  if(!visible)continue;
  await socialAction('social-transition','refresh',c);assert.equal(posted,undefined);assert.match(form.body,/原汇总快照留在办理记录/);assert.match(form.body,/本次仅保存草稿/);assert.match(form.body,/再次明确提交并由独立归口复核/);assert.equal(form.options.reasonLabel,'重新取数原因');assert.equal(form.options.reasonDefault,'');
  await form.save({reason:'新归档积分纳入原汇总',basis:'合成原单依据'});assert.equal(posted.url,'/social/reports/original-report/actions');assert.equal(posted.method,'POST');assert.deepEqual(posted.body,{reason:'新归档积分纳入原汇总',basis:'合成原单依据',expected_version:7,action:'refresh'});
 }
});

test('旧归档公式显示原始比例说明，保留原公式快照不改写',async()=>{
 const c=renderContext();await renderSocial('recognition',c);let body;c.modal=(_title,html)=>{body=html};c.downloads=()=>'';c.eventsHtml=()=>'';
 const old={formula:'基数 0.07 × 层级 1.1 × 场景 1 × 岗位 1',participants:2,standard:'30',score:'0.07',unit:'U1'};
 c.api=async()=>({item:{id:'claim',teacher_id:'teacher',period_id:'period',state:'ARCHIVED',data:{}},state_label:'已归档',trial:{teaching:'0.07',auxiliary:'0.00',total:'0.07',details:[old]},attachments:[],events:[]});
 await socialAction('social-detail','social_claim|claim',c);
 assert.match(body,/原始人次比例为2÷30/);assert.ok(body.includes(old.formula));assert.match(body,/以下为归档时的核算快照/);assert.equal(old.formula,'基数 0.07 × 层级 1.1 × 场景 1 × 岗位 1');
});

test('结项补正回填原成果金额日期和核对项，明确零值不被默认值覆盖',async()=>{
 const c=renderContext({},['records.write']);await renderSocial('projects',c);
 let fields=[],saved,detailBody;c.modal=(_title,body)=>{detailBody=body};c.downloads=()=>'';c.eventsHtml=()=>'';c.formModal=()=>{};
 const old={closed_on:'2026-10-18',satisfaction:0,location:'offsite',outcome_report:'原成果',actual_income:3000,funding_source:'other_training',finance_reference:'原财务凭据',implicit_cost:0,settlement_on:'2026-10-18',retained:600,personnel:1800,rectification:'整改内容',rectification_due:'2026-10-20',materials_checked:['plan','attendance']};
 c.api=async()=>({item:{id:'project',owner_id:'teacher',state:'FILED',version:7,data:{name:'退回结项项目',category:'enterprise'},closeout:old},state_label:'结项退回补正',progress:{flow:'project_close',label:'培训项目结项',text:'学院退回，待你补正',headline:'请补齐<核对材料>',tone:'red',nodes:[],step:2,total:4},facts:{units:[],followups:[],effective:0,excluded:0},attachments:[{id:'file'}],events:[]});
 await socialAction('social-detail','social_project|project',c);
 assert.match(detailBody,/请补齐&lt;核对材料&gt;/);assert.doesNotMatch(detailBody,/<核对材料>/);
 c.field=(key,_label,_type,value)=>{fields.push([key,value]);return ''};
 c.formModal=(_title,_body,callback)=>{saved=callback};
 await socialAction('social-close','',c);
 const values=Object.fromEntries(fields);
 for(const [key,value] of Object.entries(old))if(key!=='materials_checked')assert.equal(values[key],value,key);
 assert.equal(values.checked_plan,true);assert.equal(values.checked_attendance,true);assert.equal(values.checked_roster,false);assert.equal(typeof saved,'function');
});

test('学校直接登记和项目内课程登记都只提交教师标识，去掉检索框辅助值并保留零学时',async()=>{
 for(const action of ['social-course-new','social-course-for-project']){
  const c=renderContext({my_duties:['coordinator']},['records.write']);
  await renderSocial('projects',c);
  let form,posted;c.modal=()=>{};c.downloads=()=>'';c.eventsHtml=()=>'';c.formModal=(_title,_body,save)=>{form={save}};
  const detail={item:{id:'project',owner_id:'teacher',org_id:'college',state:'FILED',version:3,data:{code:'P1',name:'合成项目',mode:'module',category:'enterprise'},closeout:{}},kind:'social_project',state_label:'已备案',facts:{effective:0,excluded:0,units:[],followups:[]},attachments:[],events:[]};
  c.api=async(url,options)=>{if(options){posted=options.body;return {}}return url.startsWith('/social/project-options')?{items:[],total:0,page:1,size:20}:detail};
  await socialAction('social-detail','social_project|project',c);
  await socialAction(action,'',c);
  await form.save({code:'C1',name:'合成课程',project_code:'P1',teacher_id:'t1',teacher_id_search:'J001',hours:0,teaching_mode:'practice',ideology:'course_ideology',reason:'浏览器登记',basis:'合成依据',cw_checked:true,cw_reviewer:'审核员',cw_reviewed_on:'2026-10-18'});
  assert.equal(posted.teacher_id,'t1');assert.equal(posted.hours,0);assert.equal(posted.project_code,'P1');assert.equal(posted.reason,'浏览器登记');assert.equal(posted.courseware.reviewer,'审核员');
  for(const field of ['teacher_id_search','cw_checked','cw_reviewer','cw_reviewed_on'])assert.equal(Object.hasOwn(posted,field),false,field);
 }
});

test('学校可为已备案项目关联已有入库课程，保留项目版本并回读原详情',async()=>{
 const c=renderContext({},['records.write']);c.me={user:{id:'school'},role:{kind:'school'}};await renderSocial('projects',c);
 let footer,form,posted;
 c.modal=(_title,_body,foot)=>{footer=foot};c.downloads=()=>'';c.eventsHtml=()=>'';c.formModal=(_title,body,save)=>{form={body,save}};
 const detail={item:{id:'project',owner_id:'teacher',org_id:'college',state:'FILED',version:7,data:{code:'P1',name:'本轮<项目>',mode:'module',category:'community'},closeout:{}},kind:'social_project',state_label:'已备案',facts:{effective:0,excluded:0,units:[],followups:[]},attachments:[],events:[]};
 c.api=async(url,options)=>{if(options)posted={url,...options};return detail};
 await socialAction('social-detail','social_project|project',c);
 assert.match(footer,/social-course-link/);
 await socialAction('social-course-link','',c);
 assert.match(form.body,/本轮&lt;项目&gt;/);assert.match(form.body,/已有项目归属的课程不能改挂/);
 await form.save({course_code:'C1',reason:'复用已审批课程',basis:'测试依据'});
 assert.equal(posted.url,'/social/projects/project/courses/link');assert.equal(posted.method,'POST');
 assert.deepEqual(posted.body,{course_code:'C1',expected_version:7,reason:'复用已审批课程',basis:'测试依据'});
 for(const role of ['teacher','dept','college']){
  c.me={user:{id:'teacher'},role:{kind:role}};await socialAction('social-detail','social_project|project',c);assert.doesNotMatch(footer,/social-course-link/);
 }
});

test('参训入库确认显示预检项目和期次，确认请求保留原项目及预检版本',async()=>{
 const c=renderContext({courses:[{code:'C1',name:'合成课程',project_code:'P1'}]},['records.write']);c.me={user:{id:'school'},role:{kind:'school'}};c.teachers=teachers;await renderSocial('projects',c);
 let form,posted;c.modal=()=>{};c.downloads=()=>'';c.eventsHtml=()=>'';c.formModal=(title,body,save)=>{form={title,body,save}};
 const detail={item:{id:'project',cohort:'第<一期>',owner_id:'teacher',org_id:'college',state:'FILED',version:9,data:{code:'P1',name:'合成<项目>',mode:'module'},closeout:{}},kind:'social_project',state_label:'已备案',facts:{effective:0,excluded:0,units:[],followups:[]},attachments:[],events:[]};
 c.api=async(url,options)=>{if(url.endsWith('/units/preview'))return {rows:1,effective:1,excluded:0,preview_hash:'checked-hash'};if(options)posted={url,body:options.body};return detail};
 await socialAction('social-detail','social_project|project',c);await socialAction('social-unit-import','',c);
 await form.save({rows:[header,row()].join('\n'),reason:'合成预检',basis:'合成依据'},{querySelector:()=>null});
 await new Promise(resolve=>setTimeout(resolve,0));
 assert.equal(form.title,'确认参训明细入库');assert.match(form.body,/合成&lt;项目&gt;/);assert.match(form.body,/P1 · 第&lt;一期&gt;/);assert.match(form.body,/有效1人次/);
 await form.save();assert.equal(posted.url,'/social/projects/project/units/confirm');assert.equal(posted.body.expected_version,9);assert.equal(posted.body.preview_hash,'checked-hash');assert.equal(posted.body.rows.length,1);
});

test('零收入结项不催补资金来源，缺失收入不能被显示为零收入',async()=>{
 const c=renderContext();c.me={user:{id:'teacher'},role:{kind:'teacher'}};await renderSocial('projects',c);
 let body;c.modal=(_title,html)=>{body=html};c.downloads=()=>'';c.eventsHtml=()=>'';
 for(const amount of [0,'0.00',null,undefined,'',' ']){
  c.api=async()=>({item:{id:'project',owner_id:'teacher',state:'CLOSE_COLLEGE',data:{name:'合成公益项目',mode:'module'},closeout:{closed_on:'2026-10-16',actual_income:amount,funding_source:null}},facts:{effective:20,excluded:2,units:[],followups:[]},attachments:[],events:[]});
  await socialAction('social-detail','social_project|project',c);
  if(amount===0||amount==='0.00'){assert.match(body,/<td>资金来源<\/td><td>零收入，不涉及<\/td>/);assert.match(body,/<td>收入分配<\/td><td>零收入，不涉及<\/td>/)}
  else{assert.match(body,/<td>资金来源<\/td><td>历史记录待补确认<\/td>/);assert.match(body,/<td>收入分配<\/td><td>收入资料待补确认<\/td>/)}
 }
});

test('老师项目清单保留名称、期次、日期、本人角色和状态，完整资料仍走原详情',async()=>{
 const c=renderContext({projects:[{id:'own',owner_id:'teacher',cohort:'第一期',state:'DRAFT',data:{name:'<本人项目>',code:'P1',start_date:'2026-09-01',end_date:'2026-09-02'}},{id:'joined',owner_id:'other',cohort:'第二期',state:'CLOSED',state_label:'已结项',report_issues:['缺材料'],data:{name:'参与项目',code:'P2'}}],pagination:{total:2,page:1,size:20}});
 c.me={user:{id:'teacher'},role:{kind:'teacher'}};
 const html=await renderSocial('projects',c);
 for(const text of ['我的角色','项目负责人','参与教师','第一期','2026-09-01','上报资料待学院完善','social_project|own','&lt;本人项目&gt;'])assert.ok(html.includes(text),text);
 assert.doesNotMatch(html,/视频资源总时长（分钟）|实践教学基地数（个）|<本人项目>|class="social-summary"/);
});

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
 assert.deepEqual(summaryValues(html),{'基地总数':'45','思政实践教学基地':'0','近一年新增':'0'});
 const labels=[...html.matchAll(/<span class="social-badge"[^>]*>(校内基地|校外基地|类型待补充)<\/span>/g)].map(match=>match[1]);
 assert.deepEqual(labels,['校内基地','校外基地','类型待补充','类型待补充','类型待补充']);
});

test('基地卡片显示用途、设立日期、共建单位，统计思政基地和近一年新增，审批中的申请不计入',async()=>{
 const recent=new Date(Date.now()-30*864e5).toLocaleDateString('sv-SE');
 const resources=[base('a',false,{usages:['practice','ideology'],established_on:recent,partner:'湘茶集团'}),base('b',true,{usages:['practice'],established_on:'2020-01-01'}),
  {...base('c',true,{usages:['ideology'],established_on:recent,application:true}),state:'COLLEGE'}];
 const html=await renderSocial('bases',renderContext({resources,pagination:{total:3,page:1,size:200}}));
 assert.deepEqual(summaryValues(html),{'基地总数':'3','思政实践教学基地':'1','近一年新增':'1'});
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

function resourceDocument(t,c,{orgId='college1',courseCode='',teacherId='',chips=false}={}){
 const original=Object.getOwnPropertyDescriptor(globalThis,'document'),listeners={};
 const org={value:orgId,querySelector:()=>chips&&org.value?{value:org.value}:null,addEventListener:(event,handler)=>{listeners[event]=handler},change(value){this.value=value;return listeners.change()}};
 const fields={'edit-form':{isConnected:true},'f-org_id':org,'f-course_code':{value:courseCode,innerHTML:''},'f-teacher_id':{value:teacherId,innerHTML:''},'course-resource-status':{textContent:''}};
 Object.defineProperty(globalThis,'document',{configurable:true,value:{getElementById:id=>fields[id],querySelectorAll:()=>[]}});
 t.after(()=>{if(original)Object.defineProperty(globalThis,'document',original);else delete globalThis.document});
 return {org,course:fields['f-course_code'],teacher:fields['f-teacher_id'],status:fields['course-resource-status'],form:fields['edit-form']};
}

test('课程资源候选读取所选学院全部分页，明确选择且新建不显示停用暂停授权或其他学院人员',async t=>{
 const c=await pickerContext('social-course-new',[]);c.orgs=[{id:'college1',kind:'college'},{id:'college2',kind:'college'},{id:'dept1',parent_id:'college1',active:true},{id:'dept2',parent_id:'college2',active:true},{id:'dead-dept',parent_id:'college1',active:false}];
 c.teachers=[{id:'valid',name:'有效<教师>',staff_no:'J001',org_id:'dept1',active:true},{id:'inactive',name:'停用教师',staff_no:'J002',org_id:'dept1',active:false},{id:'pending',name:'待授权教师',staff_no:'J003',org_id:'dept1',active:true,authorization_pending:true},{id:'other',name:'其他学院教师',staff_no:'J004',org_id:'dept2',active:true},{id:'dead-org',name:'停用组织教师',staff_no:'J005',org_id:'dead-dept',active:true}];
 const dom=resourceDocument(t,c),courses=Array.from({length:206},(_,i)=>({code:'C'+String(i).padStart(3,'0'),name:'学院<课程>'+i}));
 c.requests.length=0;c.lookup=async url=>{const p=new URL(url,'http://localhost').searchParams;assert.equal(p.get('resource_org_id'),'college1');assert.equal(p.get('active'),'true');assert.equal(p.get('size'),'200');const page=Number(p.get('page'));return {items:courses.slice((page-1)*200,page*200),total:courses.length,page,size:200}};
 await socialAction('social-resource-new','course_resource',c);
 assert.deepEqual(c.requests.map(url=>new URL(url,'http://localhost').searchParams.get('page')),['1','2']);
 assert.equal(dom.course.value,'');assert.match(dom.course.innerHTML,/value="" selected>请选择关联课程/);assert.match(dom.course.innerHTML,/C205/);assert.match(dom.course.innerHTML,/学院&lt;课程&gt;/);assert.doesNotMatch(dom.course.innerHTML,/<课程>/);
 assert.match(dom.teacher.innerHTML,/有效&lt;教师&gt; · J001/);assert.doesNotMatch(dom.teacher.innerHTML,/停用教师|待授权教师|其他学院教师|停用组织教师/);assert.equal(dom.teacher.value,'');assert.match(dom.status.textContent,/206 门/);assert.equal(c.posts.length,0);
 await dom.org.change('');assert.equal(c.requests.length,2);assert.match(dom.course.innerHTML,/请先选择承办学院/);assert.doesNotMatch(dom.teacher.innerHTML,/有效&lt;教师&gt;/);
});

test('学校切学院同步清空课程人员，旧响应与关闭后的响应不改写新表单',async t=>{
 const c=await pickerContext('social-course-new',[]);c.orgs=[{id:'college1',kind:'college'},{id:'college2',kind:'college'},{id:'dept1',parent_id:'college1'},{id:'dept2',parent_id:'college2'}];c.teachers=[{id:'t1',name:'学院一教师',staff_no:'J1',org_id:'dept1',active:true},{id:'t2',name:'学院二教师',staff_no:'J2',org_id:'dept2',active:true}];
 const dom=resourceDocument(t,c,{chips:true});c.lookup=async()=>({items:[{code:'C1',name:'学院一课程'}],total:1});await socialAction('social-resource-new','course_resource',c);
 dom.course.value='C1';dom.teacher.value='t1';const pending=[];c.lookup=url=>new Promise(resolve=>pending.push({url,resolve}));
 const older=dom.org.change('college2');assert.equal(dom.course.value,'');assert.equal(dom.teacher.value,'');assert.match(dom.teacher.innerHTML,/学院二教师/);assert.doesNotMatch(dom.teacher.innerHTML,/学院一教师/);
 const latest=dom.org.change('college1');pending[1].resolve({items:[{code:'LATEST',name:'最新学院一课程'}],total:1});await latest;const html=dom.course.innerHTML;
 pending[0].resolve({items:[{code:'OLD',name:'过期学院二课程'}],total:1});await older;assert.equal(dom.course.innerHTML,html);
 const closed=dom.org.change('college2'),beforeClose=dom.course.innerHTML;dom.form.isConnected=false;pending[2].resolve({items:[{code:'CLOSED',name:'关闭后课程'}],total:1});await closed;assert.equal(dom.course.innerHTML,beforeClose);assert.doesNotMatch(dom.course.innerHTML,/CLOSED/);
});

test('资源编辑加载候选后仍保留原课程和停用教师，读取失败不替换原关联',async t=>{
 const c=await pickerContext('social-course-new',[]);c.orgs=[{id:'college1',kind:'college'},{id:'dept1',parent_id:'college1'}];c.teachers=[{id:'old-inactive',name:'原停用教师',staff_no:'J0',org_id:'dept1',active:false},{id:'other-inactive',name:'其他停用教师',staff_no:'J9',org_id:'dept1',active:false}];c.downloads=()=>'';c.eventsHtml=()=>'';c.modal=()=>{};
 const item={id:'r',kind:'course_resource',org_id:'college1',code:'OLD-R',name:'原资源',state:'DRAFT',version:7,data:{course_code:'OLD-C',teacher_id:'old-inactive',resource_type:'video',duration_minutes:'0',recognition:'原依据'}};
 const request=c.api;c.api=async(url,options)=>url==='/social/objects/social_resource/r'?{item,attachments:[],events:[],state_label:'已登记'}:request(url,options);
 await socialAction('social-detail','social_resource|r',c);const dom=resourceDocument(t,c,{courseCode:'OLD-C',teacherId:'old-inactive'});c.lookup=async()=>({items:[{code:'NEW-C',name:'另一可选课程'}],total:1});await socialAction('social-resource-edit','',c);
 assert.equal(dom.course.value,'OLD-C');assert.match(dom.course.innerHTML,/value="OLD-C" selected>原关联课程/);assert.equal(dom.teacher.value,'old-inactive');assert.match(dom.teacher.innerHTML,/value="old-inactive" selected>原关联教师（保留）/);assert.doesNotMatch(dom.teacher.innerHTML,/other-inactive/);
 c.lookup=async()=>{throw Error('隔离读取失败')};await socialAction('social-resource-edit','',c);assert.equal(dom.course.value,'OLD-C');assert.equal(dom.teacher.value,'old-inactive');assert.match(dom.status.textContent,/原关联资料保留/);assert.equal(c.posts.length,0);
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

test('导出上报表只给学校、学院，预检有缺项时不出下载按钮，点项目名去补',async()=>{
 const c=renderContext({},['export','records.read']);
 const html=await renderSocial('projects',c);assert.match(html,/data-action="social-report-export"/);
 c.me={user:{},role:{kind:'teacher'}};assert.doesNotMatch(await renderSocial('projects',c),/social-report-export/);
 c.me={user:{},role:{kind:'college'}};
 let modal;c.modal=(title,body,foot)=>{modal={title,body,foot}};c.table=(h,rows)=>rows.map(r=>r.join('|')).join('\n');c.note=x=>x;
 await socialAction('social-report-export','',c);assert.match(modal.body,/2023-07-01/);assert.doesNotMatch(modal.foot,/social-report-download/);
 const result={start:'2023-07-01',end:'2026-06-30',count:1,blocked:1,ready:false,scope:'本院',note:'说明',items:[{id:'p1',name:'茶艺',cohort:'一期',org_name:'学院一',state_label:'已结项',issues:['请填写总学时']}]};
 c.api=async url=>{c.last=url;return result};
 await socialAction('social-report-check','',c);
 assert.match(c.last,/start=2023-07-01&end=2026-06-30/);assert.match(modal.body,/data-action="social-detail" data-id="social_project\|p1"/);assert.match(modal.body,/请填写总学时/);assert.doesNotMatch(modal.foot,/social-report-download/);
 Object.assign(result,{blocked:0,ready:true,items:[{...result.items[0],issues:[]}]});
 await socialAction('social-report-check','',c);assert.match(modal.foot,/social-report-download/);
});


test('课程申报复用项目候选并允许不关联，补正时保留第一页之外的原项目',async t=>{
 const c=await pickerContext('social-course-new',[{id:'new',code:'NEW',name:'新项目',cohort:'一期'}]);
 let required;const field=c.field;c.field=(name,label,type,value,options)=>{if(name==='project_code')required=options.required;return field(name,label,type,value,options)};
 const html=await applicationProjectPicker(c,'OFF-PAGE');assert.equal(required,false);assert.match(html,/value="OFF-PAGE" selected/);assert.match(html,/不关联项目/);assert.match(html,/下一页项目/);
 const dom=pickerDocument(t,'project_code','','不关联项目');dom.query.value='新项目';c.lookup=async()=>({items:[{id:'new',code:'NEW',name:'新项目',cohort:'一期'}],q:'新项目',page:1,size:20,total:1});
 await socialAction('social-project-lookup','1',c);assert.equal(required,false);assert.match(dom.target.innerHTML,/value="" selected>不关联项目/);
});


test('本人积分有阻塞条件时禁用提交，允许补正且保留全部安全转义的原因',async()=>{
 const c=renderContext();c.me={user:{id:'teacher'},role:{kind:'teacher'}};
 await renderSocial('recognition',c);
 let body,foot;c.modal=(_title,b,f)=>{body=b;foot=f};c.downloads=()=>'';c.eventsHtml=()=>'';
 c.api=async()=>({item:{id:'claim',teacher_id:'teacher',state:'DRAFT',data:{}},state_label:'草稿',attachments:[],events:[],trial:{blockers:['制度执行口径尚未正式启用','学校制式积分认定表及其附件对应说明尚未提供','<未知原因>'],details:[{unit:'INTERNAL-SECRET',participants:0,formula:'0',score:0}]}});
 await socialAction('social-detail','social_claim|claim',c);
 assert.match(foot,/disabled[^>]*>暂不能提交积分申报/);assert.doesNotMatch(foot,/data-id="submit"/);assert.match(foot,/social-claim-edit/);
 assert.match(body,/待学校或项目负责人确认/);assert.match(body,/待本人补充或核对/);assert.match(body,/&lt;未知原因&gt;/);assert.doesNotMatch(body.replace(/<details class="implementation-details">[\s\S]*?<\/details>/g,''),/INTERNAL-SECRET|<未知原因>/);assert.match(body,/第1核算单元/);
 c.api=async()=>({item:{id:'claim',teacher_id:'teacher',state:'DRAFT',data:{}},state_label:'草稿',attachments:[],events:[],trial:{blockers:[]}});
 await socialAction('social-detail','social_claim|claim',c);
 assert.match(foot,/data-id="submit"/);assert.doesNotMatch(foot,/disabled/);
});


test('教师积分保存与提交按钮分开，保存不调用提交接口且保留版本和零值',async()=>{
 for(const mode of ['draft','submit']){
  const c=await pickerContext('social-course-new',[]);c.me={user:{id:'teacher'},role:{kind:'teacher'}};c.downloads=()=>'';c.eventsHtml=()=>'';c.modal=()=>{};c.toast=()=>{};
  const detail={item:{id:'claim',teacher_id:'teacher',project_id:'project',period_id:'period2026',policy_id:'policy-1',version:7,state:'RETURNED',data:{recognition_form_reference:'原认定表',auxiliary:[]}},state_label:'退回补正',attachments:[],events:[],trial:{blockers:[],details:[]}};
  const writes=[];c.api=async(url,options)=>{if(url==='/social/workspace')return {my_duties:[],policies:[{id:'policy-1',name:'口径',state:'ACTIVE'}],states:{},resources:[]};if(options){writes.push({url,...options});return {item:{id:'claim',version:8}}}return detail};
  await socialAction('social-detail','social_claim|claim',c);await socialAction('social-claim-edit','',c);
  const form=c.modals.at(-1);assert.equal(form.options.page,true);assert.equal(form.options.draft,'仅保存补正');assert.equal(form.options.submit,'保存补正并重新提交');assert.doesNotMatch(form.body,/name="submit_now"/);assert.match(form.body,/项目与认定周期/);assert.match(form.body,/name="recognition_form_reference"/);assert.doesNotMatch(form.body,/NaN/);
  await form.save({auxiliary_rows:'2026-10-01\t0\t核对材料',recognition_form_reference:'原认定表',reason:'补正'},null,{value:mode});
  assert.equal(writes[0].body.expected_version,7);assert.equal(writes[0].body.project_id,'project');assert.equal(writes[0].body.auxiliary[0].amount,'0');
  assert.equal(writes.filter(x=>x.url.endsWith('/actions')).length,mode==='submit'?1:0);
  if(mode==='submit')assert.equal(writes[1].body.expected_version,8);
 }
});


test('课程资源返回原课程，只在当前课程可读取时展示返回按钮',async()=>{
 for(const listed of [true,false]){
  const c=renderContext({courses:listed?[{code:'C1',name:'合成课程'}]:[]});await renderSocial('courses',c);let footer;c.modal=(_t,_b,f)=>{footer=f};c.api=async()=>({items:[],page:1,size:20,total:0});
  await socialAction('social-course-resources','C1',c);assert.equal(footer.includes('返回课程资料'),listed);if(listed)assert.match(footer,/data-id="C1"/);
 }
});


test('项目提交缺项直接引导回原单补齐，不打开明知无法提交的确认表单',async()=>{
 const c=renderContext();c.me={user:{id:'teacher'},role:{kind:'teacher'}};await renderSocial('projects',c);let modal,form;c.modal=(title,body,foot)=>{modal={title,body,foot}};c.formModal=()=>{form=true};c.downloads=()=>'';c.eventsHtml=()=>'';
 c.api=async()=>({item:{id:'project',owner_id:'teacher',state:'DRAFT',data:{name:'隔离<项目>',venue:{type:'campus',place:'教室'}},closeout:{}},state_label:'草稿',report_issues:['请填写总学时'],attachments:[{id:'file'}],events:[],facts:{units:[],followups:[],effective:0,excluded:0}});
 await socialAction('social-detail','social_project|project',c);await socialAction('social-transition','submit',c);
 assert.equal(modal.title,'提交前请先补齐项目资料');assert.match(modal.body,/请填写总学时/);assert.match(modal.foot,/social-project-edit/);assert.equal(form,undefined);
});


test('教师基地与积分申报空列表保留一个主要入口',async()=>{
 for(const [section,action] of [['bases','app-base-new'],['recognition','social-claim-new']]){
  const c=renderContext({},['records.read','points.read']);c.me={user:{id:'teacher',staff_no:'J001'},role:{kind:'teacher'}};
  const html=await renderSocial(section,c);assert.equal((html.match(new RegExp('data-action="'+action+'"','g'))||[]).length,1);
 }
});


test('教研室课程和基地范围说明保留申请入口，不暗示可以直接登记资源',async()=>{
 for(const [section,action] of [['courses','app-course-new'],['bases','app-base-new']]){
  const c=renderContext({},['records.read','records.write']);c.me={user:{id:'dept-scope-copy'},role:{kind:'dept'}};
  const html=await renderSocial(section,c);assert.match(html,new RegExp('data-action="'+action+'"'));
  assert.match(html,/提交申请/);assert.doesNotMatch(html,/只能查看。|data-action="social-course-new"|data-action="social-resource-new"/);
 }
});


test('积分汇总默认当前双月而非固定一二月，跨年首尾月份保持范围正确',async()=>{
 const c=renderContext({my_duties:['secretary']});c.me={user:{id:'secretary-window'},role:{kind:'school'}};c.orgs=[{id:'school',name:'合成学校',kind:'school'}];await renderSocial('recognition',c);c.formModal=()=>{};
 const RealDate=globalThis.Date,fields={};c.field=(name,_label,_type,value)=>{fields[name]=value;return ''};
 try{for(const [month,window] of [[0,'1-2'],[9,'9-10'],[11,'11-12']]){globalThis.Date=class extends RealDate{getMonth(){return month}getFullYear(){return 2026}};await socialAction('social-report-new','',c);assert.equal(fields.year,2026);assert.equal(fields.window,window)}}finally{globalThis.Date=RealDate}
});

test('双月汇总默认当前办理组织，不随可选组织的排序误选其他学院',async()=>{
 const orgs=[{id:'college1',name:'其他学院',kind:'college'},{id:'school',name:'当前学校',kind:'school'},{id:'college2',name:'当前学院',kind:'college'}];
 for(const [role,org_id] of [['school','school'],['college','college2']]){
  const c=renderContext({my_duties:['secretary']});c.me={user:{id:'reporter-'+role,org_id},role:{kind:role}};c.orgs=orgs;await renderSocial('recognition',c);
  const fields={};c.field=(key,_label,_type,value)=>{fields[key]=value;return ''};c.formModal=()=>{};await socialAction('social-report-new','',c);assert.equal(fields.org_id,org_id);
 }
});

test('年度和双月汇总的详情及确认表使用本次真实办理名称',async()=>{
 for(const [start_month,end_month,label] of [[1,12,'启动年度公示'],[9,10,'复核报送']]){
  const c=renderContext({my_duties:['coordinator']});c.me={user:{id:'reviewer'},role:{kind:'school'}};await renderSocial('recognition',c);
  let buttons,form;c.modal=(_title,_body,foot)=>{buttons=foot};c.formModal=(title,_body,_save,options)=>{form={title,options}};c.downloads=()=>'';c.eventsHtml=()=>'';
  c.api=async()=>({item:{id:'report',kind:'point_report',name:'合成汇总',org_id:'school',state:'SUBMITTED',version:1,data:{created_by:'secretary',year:2025,start_month,end_month,rows:[]}},attachments:[],events:[],state_label:'待归口复核'});
  await socialAction('social-detail','social_resource|report',c);assert.match(buttons,new RegExp('data-action="social-transition" data-id="approve">'+label));assert.doesNotMatch(buttons,/复核报送或启动公示/);
  await socialAction('social-transition','approve',c);assert.equal(form.title,label);assert.equal(form.options.submit,'确认'+label);
 }
});

test('汇总清单详情和办理表明确组织及期间，避免同名汇总混淆',async()=>{
 const item={id:'report',kind:'point_report',name:'2026年9—10月积分汇总',org_id:'school',org_name:'合成<学校>',state:'DRAFT',version:1,data:{created_by:'secretary',year:2026,start_month:9,end_month:10,rows:[]}};
 const c=renderContext({my_duties:['secretary'],resources:[item]});c.me={user:{id:'secretary',org_id:'school'},role:{kind:'school'}};
 const html=await renderSocial('recognition',c);assert.match(html,/2026年9—10月积分汇总 · 合成&lt;学校&gt;/);
 let detail,form;c.modal=(_title,body)=>{detail=body};c.formModal=(_title,body)=>{form=body};c.downloads=()=>'';c.eventsHtml=()=>'';c.api=async()=>({item,org_name:'合成<学校>',state_label:'草稿',attachments:[],events:[]});
 await socialAction('social-detail','social_resource|report',c);assert.match(detail,/汇总范围/);assert.match(detail,/汇总组织/);assert.match(detail,/合成&lt;学校&gt;/);assert.match(detail,/2026年 9—10月/);
 await socialAction('social-transition','submit',c);assert.match(form,/合成&lt;学校&gt; · 2026年9—10月积分汇总/);assert.doesNotMatch(form,/合成<学校>/);
});

test('秘书身份没有学院或学校范围时直接说明配置缺项，有有效组织仍按原合约生成汇总',async()=>{
 for(const orgs of [[],[{id:'dept',name:'本教研室',kind:'dept'}],[{id:'college',name:'本学院',kind:'college'}],[{id:'school',name:'本学校',kind:'school'}]]){
  const c=renderContext({my_duties:['secretary']},['records.read']);c.me={user:{id:'report-scope-'+(orgs[0]?.id||'none')},role:{kind:orgs[0]?.kind==='school'?'school':orgs[0]?.kind==='college'?'college':'dept'}};c.orgs=orgs;
  await renderSocial('recognition',c);
  let modal,form,posted;c.modal=(title,body,buttons)=>{modal={title,body,buttons}};c.formModal=(title,body,save)=>{form={title,body,save}};
  c.field=(name,label,type,value,options={})=>escapeHtml(label)+(options.options||[]).map(x=>escapeHtml(x[0])+':'+escapeHtml(x[1])).join(';');
  c.api=async(url,options)=>{posted={url,options};return {}};
  await socialAction('social-report-new','',c);
  if(!orgs.some(o=>['college','school'].includes(o.kind))){assert.equal(form,undefined);assert.match(modal.body,/没有可汇总的学院或学校/);assert.match(modal.body,/教学秘书职责对应的身份与组织范围/);assert.match(modal.buttons,/data-action="close"/);assert.equal(posted,undefined)}
  else{assert.equal(modal,undefined);assert.match(form.body,/汇总组织/);assert.ok(form.body.includes(orgs[0].id+':'+orgs[0].name));await form.save({org_id:orgs[0].id,year:2026,window:'3-4',policy_id:'policy',reason:'隔离验证'});assert.equal(posted.url,'/social/reports');assert.equal(posted.options.method,'POST');assert.equal(posted.options.body.org_id,orgs[0].id);assert.equal(posted.options.body.start_month,3);assert.equal(posted.options.body.end_month,4)}
 }
});


test('教研室学院共用项目简表和原详情，学校保留上报宽表',async()=>{
 const project={id:'dept-compact-project',owner_id:'t1',cohort:'第一期',state:'CLOSED',state_label:'已结项',data:{name:'<合成项目>',code:'P-COMPACT',start_date:'2026-10-15',end_date:'2026-10-16',service_types:['regional'],total_hours:8,video_minutes:12,base_count:1,teaching_methods:['classroom']}};
 for(const role of ['dept','teacher','college','school']){
  const c=renderContext({projects:[project],pagination:{total:1,page:1,size:20}},['records.read','records.write']);c.me={user:{id:'project-'+role},role:{kind:role}};
  const html=await renderSocial('projects',c),head=html.match(/<thead>[\s\S]*?<\/thead>/)[0];
  assert.match(html,/&lt;合成项目&gt;/);assert.match(html,/social_project\|dept-compact-project/);
  if(['dept','college'].includes(role)){assert.equal((head.match(/<th>/g)||[]).length,5);assert.match(head,/培训期间/);assert.match(head,/当前状态/);assert.doesNotMatch(head,/服务面向类型|视频资源总时长|实践教学基地数|我的角色/);if(role==='dept')assert.doesNotMatch(html,/social-project-new|social-unit-import/);else{assert.match(head,/办理/);assert.match(html,/data-action="social-project-new"/)}}
  else if(role==='teacher'){assert.equal((head.match(/<th>/g)||[]).length,6);assert.match(head,/我的角色/)}
  else{assert.equal((head.match(/<th>/g)||[]).length,9);assert.match(head,/服务面向类型/);assert.match(head,/实践教学基地数/)}
 }
});

test('教研室学院课程复用简表与资料资源入口，学校资源汇总仍展开',async()=>{
 const data={projects:[{data:{code:'PROJECT-NAME',name:'关联<项目>'}}],courses:[{code:'COURSE-COMPACT',name:'合成<课程>',project_code:'PROJECT-NAME'}],course_info:{'COURSE-COMPACT':{hours:0,teaching_mode:'lecture',ideology:'course_ideology'}},course_stats:{'COURSE-COMPACT':{resources:1,videos:1,minutes:12.5}},resources:[{id:'compact-video',kind:'course_resource',name:'合成视频',state:'ACTIVE',data:{course_code:'COURSE-COMPACT',resource_type:'video',duration_minutes:12.5}}],pagination:{total:1,page:1,size:20}};
 for(const role of ['dept','teacher','college','school']){
  const c=renderContext(data,['records.read','records.write']);c.me={user:{id:'course-'+role},role:{kind:role}};
  const html=await renderSocial('courses',c),head=html.match(/<thead>[\s\S]*?<\/thead>/)[0],resourceDetails=html.match(/<details class="business-guide data-details mt20"([^>]*)>/);
  assert.match(html,/data-action="social-course-view" data-id="COURSE-COMPACT"/);assert.match(html,/data-action="social-course-resources" data-id="COURSE-COMPACT"/);
  if(['teacher','dept','college'].includes(role)){assert.equal((head.match(/<th>/g)||[]).length,5);assert.match(head,/资源摘要/);assert.match(html,/关联&lt;项目&gt;/);assert.match(html,/<td>0<\/td>/);assert.doesNotMatch(head,/主讲教师 \/ 课件审查/)}
  else{assert.equal((head.match(/<th>/g)||[]).length,7);assert.match(head,/主讲教师 \/ 课件审查/)}
  if(['dept','college'].includes(role)){assert.ok(resourceDetails);assert.doesNotMatch(resourceDetails[1],/open/);if(role==='dept')assert.doesNotMatch(html,/data-action="social-resource-new"/);else assert.match(html,/data-action="social-resource-new"/)}
  else if(role==='teacher')assert.equal(resourceDetails,null);
  else assert.match(resourceDetails[1],/open/);
 }
});

test('教研室空态仅保留顶部申请且无无效检索分页，越界页仍能返回上一页',async()=>{
 for(const [section,action] of [['bases','app-base-new'],['courses','app-course-new']]){
  for(const page of [1,2]){
   const c=renderContext({pagination:{total:0,page,size:20}},['records.read','records.write']);c.me={user:{id:'empty-'+section+'-'+page},role:{kind:'dept'}};
   const html=await renderSocial(section,c);assert.equal((html.match(new RegExp('data-action="'+action+'"','g'))||[]).length,1);assert.doesNotMatch(html,/id="social-search-form"/);
   if(page===1)assert.doesNotMatch(html,/class="social-pager"/);else{assert.match(html,/class="social-pager"/);assert.match(html,/data-action="social-list-page" data-id="1"/)}
  }
 }
 const c=renderContext({},['records.read']);c.me={user:{id:'dept-active-search'},role:{kind:'dept'}};await renderSocial('bases',c);
 const prior=Object.getOwnPropertyDescriptor(globalThis,'document');Object.defineProperty(globalThis,'document',{configurable:true,value:{getElementById:()=>({value:'不存在的基地'})}});
 try{await socialAction('social-list-apply','',c);const html=await socialPage('bases',c);assert.match(html,/id="social-search-form"/);assert.match(html,/清空检索/);assert.match(html,/查看全部/)}finally{if(prior)Object.defineProperty(globalThis,'document',prior);else delete globalThis.document;await socialAction('social-list-reset','',c)}
});

test('教研室学院成果共用简表显示教师贡献或学院参考，学校保留原编号依据',async()=>{
 const resources=[{id:'outcome-teacher',kind:'achievement',name:'教师成果',code:'AUTO-UUID-TEACHER',org_id:'college1',state:'ACTIVE',data:{teacher_id:'t1',level:'province',confirmed_on:'2026-10-16',recognition:'原认定依据'}},{id:'outcome-college',kind:'achievement',name:'学院成果',code:'AUTO-UUID-COLLEGE',org_id:'college1',state:'ACTIVE',data:{level:'school',confirmed_on:'2026-10-15',recognition:'原认定依据'}},{id:'outcome-unknown',kind:'achievement',name:'待核对教师成果',code:'AUTO-UUID-UNKNOWN',org_id:'college1',state:'ACTIVE',data:{teacher_id:'not-in-scope',level:'city',confirmed_on:null,recognition:'原认定依据'}}];
 for(const role of ['dept','teacher','college','school']){
  const c=renderContext({resources,pagination:{total:3,page:1,size:20}},['records.read','records.write']);c.me={user:{id:'outcomes-'+role},role:{kind:role}};c.teachers=[{id:'t1',name:'张<老师>'}];c.orgName=()=> '所属学院';
  const html=await renderSocial('outcomes',c),head=html.match(/<thead>[\s\S]*?<\/thead>/)[0];
  if(['dept','teacher','college'].includes(role)){assert.equal((head.match(/<th>/g)||[]).length,5);assert.match(head,/认定级别/);assert.match(head,/认定日期/);assert.doesNotMatch(html,/>AUTO-UUID-/);assert.match(html,/省级/);assert.match(html,/2026-10-16/)}
  else{assert.equal((head.match(/<th>/g)||[]).length,4);assert.match(head,/编号/);assert.match(html,/>AUTO-UUID-TEACHER</);assert.match(html,/原认定依据/)}
  if(['dept','college'].includes(role)){assert.match(html,/张&lt;老师&gt; · 教师贡献/);assert.match(html,/所属学院 · 学院参考/);assert.match(html,/教师姓名待核对 · 教师贡献/);assert.doesNotMatch(html,/>not-in-scope</);assert.doesNotMatch(html,/我的贡献|本人贡献/);if(role==='dept')assert.doesNotMatch(html,/social-resource-new/);else assert.match(html,/data-action="social-resource-new"/)}
  if(role==='teacher')assert.doesNotMatch(html,/教师贡献/);
  assert.match(html,/data-action="social-detail" data-id="social_resource\|outcome-teacher"/);
 }
});


test('学院空态复用单个申请入口与有效分页，审批入口不受简化影响',async()=>{
 for(const [section,action] of [['projects','social-project-new'],['courses','app-course-new'],['bases','app-base-new'],['outcomes','social-resource-new'],['annual','social-annual-new']]){
  for(const page of [1,2]){
   const c=renderContext({pagination:{total:0,page,size:20}},['records.read','records.write','assessment.review']);c.me={user:{id:'college-empty-'+section+'-'+page},role:{kind:'college'}};
   const html=await renderSocial(section,c);assert.equal((html.match(new RegExp('data-action="'+action+'"','g'))||[]).length,1);assert.doesNotMatch(html,/id="social-search-form"/);
   if(page===1)assert.doesNotMatch(html,/class="social-pager"/);else assert.match(html,/data-action="social-list-page" data-id="1"/);
  }
 }
});

test('学院项目详情复用分区折叠流程和更多操作，开班准备只显示一次且三级表单带对象',async()=>{
 const c=renderContext({},['records.read','records.write','file.write','export']);c.me={user:{id:'college-detail'},role:{kind:'college'}};await renderSocial('projects',c);
 let modal,form;c.modal=(title,body,buttons,_wide,contextLabel)=>{modal={title,body,buttons,contextLabel}};c.formModal=(title,body,save,options)=>{form={title,body,save,options}};c.downloads=()=>'';c.eventsHtml=()=>'';
 c.field=(name,label)=>'<label>'+escapeHtml(label)+'<input name="'+name+'"></label>';
 c.api=async()=>({item:{id:'college-project',owner_id:'teacher',state:'FILED',version:4,data:{name:'学院<项目>',code:'COLLEGE-P1',category:'community'},closeout:{}},state_label:'已备案',facts:{units:[],followups:[],effective:0,excluded:0},attachments:[{id:'material'}],events:[]});
 await socialAction('social-detail','social_project|college-project',c);
 assert.match(modal.body,/data-detail-section="social-info"/);assert.match(modal.body,/<details class="detail-fold application-flow"><summary>查看完整办理流程/);assert.match(modal.buttons,/<details class="detail-more-actions">/);assert.match(modal.buttons,/social-export/);assert.equal((modal.buttons.match(/data-action="social-prep"/g)||[]).length,1);assert.equal(modal.contextLabel,'培训项目 / 业务详情');assert.match(modal.buttons,/data-action="social-unit-import"/);
 await socialAction('social-transition','refile',c);assert.match(form.body,/本次办理对象/);assert.match(form.body,/学院&lt;项目&gt;/);assert.equal(form.options.contextLabel,'培训项目 / 申请重新备案');
 await socialAction('social-close','',c);assert.equal(form.options.page,true);assert.match(form.body,/结项情况/);assert.match(form.body,/结项材料核对/);
});

test('学院年度自评复用整页分区，补正保持原组织周期与版本并保留零值',async()=>{
 const c=renderContext({policies:[{id:'annual-policy',name:'隔离口径',period_id:'annual-period',state:'ACTIVE'}]},['assessment.read','assessment.review','records.read']);c.me={user:{id:'college-annual-owner'},role:{kind:'college'}};c.orgs=[{id:'college1',name:'所属学院',kind:'college'}];c.periods=[{id:'annual-period',name:'当前周期',state:'OPEN',start_date:'2000-01-01',end_date:'2099-12-31'}];
 await renderSocial('annual',c);let form,posted;c.field=(name,label)=>'<label>'+escapeHtml(label)+'<input name="'+name+'"></label>';c.formModal=(title,body,save,options)=>{form={title,body,save,options}};c.modal=()=>{};c.downloads=()=>'';c.eventsHtml=()=>'';
 await socialAction('social-annual-new','',c);assert.equal(form.options.page,true);assert.match(form.body,/学院与认定周期/);assert.match(form.body,/年度任务与自评/);assert.match(form.body,/加分与合规事项/);
 const detail={item:{id:'college-annual',org_id:'college1',period_id:'annual-period',policy_id:'annual-policy',owner_id:'college-annual-owner',state:'RETURNED',version:7,data:{self_report:'原自评报告',compliance_failures:0,other_bonus:0},snapshot:{}},state_label:'退回补正',attachments:[],events:[]};
 c.api=async(url,options)=>{if(options){posted={url,...options};return {}}return detail};await socialAction('social-detail','social_annual|college-annual',c);await socialAction('social-annual-edit','',c);assert.equal(form.options.page,true);assert.equal(form.options.contextLabel,'学院年度考核 / 学院年度自评');
 await form.save({org_id:'cannot-change',period_id:'cannot-change',policy_id:'annual-policy',self_report:'补正自评报告',compliance_failures:0,other_bonus:0,reason:'隔离补正'});
 assert.equal(posted.url,'/social/annuals/college-annual');assert.equal(posted.method,'PUT');assert.equal(posted.body.org_id,'college1');assert.equal(posted.body.period_id,'annual-period');assert.equal(posted.body.expected_version,7);assert.equal(posted.body.data.other_bonus,0);assert.equal(posted.body.data.compliance_failures,0);
});


test('学院学校共用项目次要动作折叠，教师原动作不变且无导出权限也不丢动作',async()=>{
 for(const [role,exported] of [['college',true],['college',false],['teacher',true],['school',true]]){
  const c=renderContext({},['records.read','records.write','file.write',...(exported?['export']:[])]);c.me={user:{id:role==='teacher'?'teacher':'footer-'+role+'-'+exported},role:{kind:role}};await renderSocial('projects',c);
  let footer;c.modal=(_t,_b,f)=>{footer=f};c.downloads=()=>'';c.eventsHtml=()=>'';c.api=async()=>({item:{id:'footer-project',owner_id:'teacher',state:'FILED',data:{name:'页脚合成项目',code:'FOOTER-P1',category:'community'},closeout:{}},state_label:'已备案',facts:{units:[],followups:[],effective:0,excluded:0},attachments:[{id:'file'}],events:[]});
  await socialAction('social-detail','social_project|footer-project',c);
  const more=footer.match(/<details class="detail-more-actions">[\s\S]*?<\/details>/)?.[0]||'',main=footer.replace(more,'');
  if(['college','school'].includes(role)){
   assert.equal((footer.match(/class="detail-more-actions"/g)||[]).length,1);
   for(const action of ['social-prep','social-report-info']){assert.ok(more.includes('data-action="'+action+'"'));assert.ok(!main.includes('data-action="'+action+'"'))}
   assert.match(more,/data-action="social-transition" data-id="refile"/);assert.doesNotMatch(main,/data-id="refile"/);assert.equal(more.includes('social-export'),exported);
   for(const action of ['social-upload','social-unit-import','social-close'])assert.ok(main.includes('data-action="'+action+'"'));
  }else{assert.match(main,/data-action="social-prep"/);assert.match(main,/data-id="refile"/);if(role==='school')assert.match(main,/data-action="social-report-info"/)}
 }
});
