import test from 'node:test';
import assert from 'node:assert/strict';
import {homeIndicators,minePage,ledgerAction,ledgerPage,resourceStatsPage} from '../../frontend/social-ledgers.js';
import {socialAction} from '../../frontend/social-training.js';
const esc=v=>String(v??'').replace(/[&<>"']/g,x=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));
const workspace={projects:[],courses:[],resources:[],claims:[],annuals:[],policies:[],my_duties:[],states:{},decisions:{}};
function context(answers,permissions=['records.read','points.read','qualification.read','records.write','export']){
 const c={esc,ts:v=>v||'—',me:{role:{kind:'teacher'},user:{id:'t1',staff_no:'J001'}},teachers:[],orgs:[],periods:[],requests:[],
  can:p=>permissions.includes(p),pageAllowed:()=>true,number:v=>Number(v??0).toString(),icon:()=>'',
  act:(l,a,id='')=>`<button data-action="${a}" data-id="${esc(id)}">${esc(l)}</button>`,link:(l,a,id='')=>`<a data-action="${a}" data-id="${esc(id)}">${esc(l)}</a>`,
  field:(n,l,t='text',v='',o={})=>`<label>${esc(l)}<input name="${n}" value="${esc(v)}">${(o.options||[]).map(x=>esc(x[1])).join('')}</label>`,
  note:esc,pageHead:esc,table:(h,r)=>h.join(' ')+' '+r.map(x=>x.join(' ')).join(' '),orgName:esc,teacherName:esc,downloads:()=>'',eventsHtml:()=>'',reasonFields:()=>'',
  modal:(title,body,buttons,wide,contextLabel)=>{c.modalData={title,body,buttons,wide,contextLabel}},formModal:(title,body,save,options)=>{c.formData={title,body,save,options}},
  closeModal(){},toast(){},render:async()=>{},
  api:async(url,options)=>{c.requests.push({url,options});if(url==='/social/workspace')return workspace;for(const[k,v]of Object.entries(answers))if(url.startsWith(k))return v;throw Error('无匹配测试响应：'+url)}};
 return c;
}

test('被替代公示只读保留旧快照并可跳转，新公示说明重新计满期限',async()=>{
 const d={item:{id:'old-report',kind:'point_report',state:'VOID',data:{superseded_by:'new-report',rows:[]}},state_label:'已被新公示替代',attachments:[],events:[]};
 const c=context({'/social/objects':d},['points.read','records.write','file.write','export']);c.me.role.kind='school';
 await socialAction('social-detail','social_resource|old-report',c);
 assert.match(c.modalData.body,/保留原公示快照|不再作为当前公示或归档依据/);
 assert.match(c.modalData.buttons,/查看后续公示|social_resource\|new-report/);
 assert.doesNotMatch(c.modalData.buttons,/social-upload|social-transition/);
 d.item={id:'new-report',kind:'point_report',state:'PUBLIC',data:{replaces:['old-report'],rows:[]}};d.state_label='公示中';
 await socialAction('social-detail','social_resource|new-report',c);
 assert.match(c.modalData.body,/公示期限从本次发布日重新计算|不能沿用旧公示期限/);
});

test('积分与年度考核归档详情使用认定标签，审批中保留候选标签',async()=>{
 for(const kind of ['social_claim','social_annual'])for(const state of ['SUBMITTED','ARCHIVED']){
  const d={item:{id:'label-case',state,data:{},teacher_id:'t1'},state_label:'合成状态',trial:{teaching:'1.00',auxiliary:'0.00',total:'1.00',grade:'合格',details:[{unit:'U1',participants:30,formula:'合成公式',score:'1.00'}]},attachments:[],events:[]};
  const c=context({'/social/objects':d});c.periodName=esc;
  await socialAction('social-detail',kind+'|label-case',c);
  assert.match(c.modalData.body,state==='ARCHIVED'?/认定积分/:/候选积分/);
  if(state==='ARCHIVED')assert.doesNotMatch(c.modalData.body,/候选积分|候选等级/);
  if(kind==='social_annual'){assert.match(c.modalData.body,state==='ARCHIVED'?/认定等级/:/候选等级/);assert.match(c.modalData.body,/所有单项加分共用上限/);assert.doesNotMatch(c.modalData.body,/仍须确认叠加口径/)}
 }
});

test('追加更正新建与补正保存后直接进入保存的更正详情继续办理',async()=>{
 for(const edit of [false,true]){
  const claim={id:'claim-save',state:'ARCHIVED',teacher_id:'t1',version:3,data:{}},fix={id:'fix-save',kind:'correction',state:edit?'RETURNED':'DRAFT',version:4,data:{claim_id:claim.id,teacher_id:'t1',created_by:'t1',period_id:'p1',teaching:'0.10',auxiliary:'0',decision_reference:'合成依据'}};
  const saved={item:{...fix,state:'DRAFT',version:5},state_label:'草稿',attachments:[],events:[]};
  const c=context({'/social/objects/social_claim/claim-save':{item:claim,state_label:'已归档',attachments:[],events:[]},'/social/objects/social_resource/fix-save':saved,'/social/corrections':saved},['points.read','file.write','export']);c.periodName=esc;
  await socialAction('social-detail',(edit?'social_resource|fix-save':'social_claim|claim-save'),c);
  await socialAction(edit?'social-correction-edit':'social-correction-new','',c);
  await c.formData.save({period_id:'p1',teaching:'0.10',auxiliary:'0',decision_reference:'合成依据',reason:'保存更正'});
  assert.match(c.modalData.buttons,/social-upload/);assert.match(c.modalData.buttons,/data-id="submit"/);
  const req=c.requests.findLast(r=>r.options?.method===(edit?'PUT':'POST'));
  assert.equal(req.options.body.claim_id,claim.id);if(edit)assert.equal(req.options.body.expected_version,5);
  assert.equal(c.requests.at(-1).url,'/social/objects/social_resource/fix-save');
 }
});

test('年度核验展示已完成职责并隐藏重复核验，公示摘要不泄露核验意见',async()=>{
 const prior=workspace.my_duties;workspace.my_duties=['finance','academic'];
 const d={item:{id:'annual-checks',state:'REVIEW',owner_id:'college-owner',data:{},snapshot:{checks:{finance:{reason:'财务已核验<合成说明>'}}}},state_label:'待职能部门核验',attachments:[],events:[]};
 const c=context({'/social/objects':d},['assessment.read','assessment.review','records.read','export']);c.periodName=esc;c.me.role.kind='school';c.me.user.id='finance-actor';
 try{
  await socialAction('social-detail','social_annual|annual-checks',c);
  assert.match(c.modalData.body,/职能部门核验进度|已核验|待核验/);assert.match(c.modalData.body,/财务已核验&lt;合成说明&gt;/);
  assert.doesNotMatch(c.modalData.buttons,/data-id="finance"/);assert.match(c.modalData.buttons,/data-id="academic"/);
  d.item.state='PUBLIC';d.public_summary=true;d.state_label='公示中';workspace.my_duties=[];c.me.role.kind='teacher';
  await socialAction('social-detail','social_annual|annual-checks',c);
  assert.doesNotMatch(c.modalData.body,/职能部门核验进度|财务已核验/);
 }finally{workspace.my_duties=prior}
});
test('撤销一个业务分区仅隐藏对应卡片，授权卡片仍可用',async()=>{
 const o={scope:'本人',sections:{records:true,points:true,qualifications:false},participants:{mine:{value:30,projects:1}},dual:null,achievements:{total:0,levels:{}},points:{year:0}};
 const html=await homeIndicators(context({'/social/overview':o},['records.read','points.read']),{});
 assert.match(html,/我的培训人次/);assert.match(html,/学院统计表里分给你的人次/);assert.match(html,/仅供参考，以项目核定为准/);assert.match(html,/我的社会培训积分/);assert.doesNotMatch(html,/我的双师型/);
});
test('无资质和积分读取权限的个人页不展示对应分区或操作',async()=>{
 const m={name:'合成教师',org_name:'合成学院',sections:{records:true,points:false,qualifications:false},projects:[],claims:[],allocations:[{year:2026,org_name:'合成学院',row_no:4,name:'核减项目',value:100,original_value:100,approved_value:null,project_approved:0,review_status:'项目核定 0 人次，原分配不作为认定数'}],qualifications:[],courses:{courses:0,videos:0,minutes:0},achievements:[],reminders:[]};
 const html=await minePage(context({'/social/mine':m,'/social/overview':{sections:m.sections,participants:{},achievements:{total:0,levels:{}}}},['records.read']),{});
 assert.doesNotMatch(html,/我的资质|我的积分申报|申报本人积分/);assert.match(html,/原表参考数/);assert.match(html,/项目核定人次 0/);assert.doesNotMatch(html,/个人核定 0/);
});
test('非负责人只读详情只显示参与摘要，无写操作或名册字段',async()=>{
 const d={readonly:true,readonly_reason:'仅本人摘要',state_label:'已备案',item:{id:'p1',state:'FILED',cohort:'一期',data:{name:'合成培训',start_date:'2026-09-01',end_date:'2026-09-02',mode:'module'}},facts:{units:[{external_key:'U1',data:{event_date:'2026-09-01',module:'本人模块',teachers:[{role:'lecturer'}]}}]}};
 const c=context({'/social/objects':d});await socialAction('social-detail','social_project|p1',c);
 assert.match(c.modalData.body,/本人模块|主讲/);assert.doesNotMatch(c.modalData.body,/参训记录数|实际到账收入|佐证材料/);
 assert.doesNotMatch(c.modalData.buttons,/social-upload|social-close|social-unit-import|social-transition/);
});
test('教师年度公示仅展示评分摘要，无原始材料及个人积分总量',async()=>{
 const d={public_summary:true,state_label:'公示中',item:{id:'a1',state:'PUBLIC',data:{},snapshot:{}},trial:{total:'90',base:'85',bonus_awarded:'5',metrics:[],cost_base:'10',outcome_details:[]},attachments:[],events:[]};
 const c=context({'/social/objects':d},['records.read','assessment.read','file.write','export']);c.periodName=esc;
 await socialAction('social-detail','social_annual|a1',c);
 assert.match(c.modalData.body,/公示开放评分摘要/);assert.doesNotMatch(c.modalData.body,/佐证材料|办理记录|学院个人积分合计|平均积分|正式处理依据|undefined/);assert.doesNotMatch(c.modalData.buttons,/social-upload/);
});
test('待确认草稿编辑表单覆盖日期、核算方式、层级和场景',async()=>{
 const c=context({'/social/objects':{item:{id:'p1',state:'DRAFT',cohort:'一期',data:{name:'合成草稿',source:{ledger_id:'l1',dates_pending:true,mode_pending:true,policy_pending:['level','scene']}},closeout:{}},facts:{effective:0,excluded:0,units:[],followups:[]},attachments:[],events:[]}});
 c.teacherField=()=>'';await socialAction('social-detail','social_project|p1',c);assert.match(c.modalData.body,/台账草稿待核实/);assert.match(c.modalData.body,/不能直接正式备案/);await socialAction('social-project-edit','',c);
 for(const name of ['dates_confirmed','mode_confirmed','level_confirmed','scene_confirmed'])assert.ok(c.formData.body.includes(`name="${name}"`));
});
test('结项表单要求明确资金分类，零收入空来源按空值提交',async()=>{
 const c=context({'/social/projects':{}});await socialAction('social-close','',c);
 assert.match(c.formData.body,/name="funding_source"/);assert.match(c.formData.body,/name="funding_basis"/);assert.match(c.formData.body,/政府专项按主管部门规定/);
 await c.formData.save({reason:'合成结项',basis:'合成依据',funding_source:'',actual_income:0,retained:'',personnel:'',rectification_due:'',settlement_on:''});
 assert.equal(c.requests.findLast(r=>r.options?.body?.closeout).options.body.closeout.funding_source,null);
});
test('台账人员关联使用明确账号与最新版本，拒绝只凭姓名',async()=>{
 const d={id:'l1',version:7,can_draft:true,data:{rows:[{row_no:4,name:'合成项目',allocations:[{name:'同名教师'}]}]},teacher_options:[{id:'t1',name:'同名教师',employee_no:'J001'},{id:'t2',name:'同名教师',employee_no:'J002'}]};
 const c=context({'/social/ledgers/l1':d});globalThis.document={querySelectorAll:()=>[]};
 try{await ledgerAction('tz-bind-person','l1|4|0',c);assert.match(c.formData.body,/J001/);assert.match(c.formData.body,/J002/);await c.formData.save({teacher_id:'t2',reason:'核对工号'});assert.equal(c.requests.at(-1).options.body.teacher_id,'t2');assert.equal(c.requests.at(-1).options.body.expected_version,7)}finally{delete globalThis.document}
});
test('学院只读台账逐行显示核定零值及理由，不提供核定输入框',async()=>{
 const d={id:'l1',org_name:'合成学院',version:1,can_review:false,can_draft:false,versions:[],data:{year:2026,version_no:1,template_label:'合成台账',file:{name:'合成.xlsx'},summary:{serious:0},rows:[{row_no:4,name:'已核减项目',approved:'0',approved_reason:'合成核减依据',recommended:'100',claimed:'100',issues:[]}]},totals:{claimed_total:'100',recommended_total:'100',final_total:'0',pending_rows:0}};
 const c=context({'/social/ledgers/l1':d});await ledgerAction('tz-detail','l1',c);
 try{const html=await ledgerPage(c);assert.match(html,/项目核定值 \/ 理由/);assert.match(html,/<strong>0 人次<\/strong>/);assert.match(html,/合成核减依据/);assert.doesNotMatch(html,/class="ledger-approved"/)}finally{await ledgerAction('tz-back','',c)}
});
test('资源统计显示实际视频数与小数分钟，不把汇总记录当一个视频',async()=>{
 const c=context({'/social/resource-stats':{items:[{org_name:'合成学院',courses:1,resources:1,videos:12,minutes:'95.5'}],note:'合成资源汇总'}});
 const html=await resourceStatsPage(c);assert.match(html,/12/);assert.match(html,/95\.5/);assert.doesNotMatch(html,/>96</);
});

test('核对发送前显示缺少替代审批人的原因并隐藏发送入口',async()=>{
 const d={item:{id:'r1',kind:'point_review',state:'DRAFT',version:1,data:{created_by:'t1',teacher_id:'t2'}},state_label:'待发送教师',attachments:[],events:[],workflow_blockers:['二级学院院长环节没有无需回避的办理人，请配置替代人员']};
 const c=context({'/social/objects/social_resource/r1':d});c.periodName=esc;c.me.role.kind='college';
 await socialAction('social-detail','social_resource|r1',c);
 assert.match(c.modalData.body,/配置替代人员/);assert.doesNotMatch(c.modalData.buttons,/data-id="send"/);assert.match(c.modalData.buttons,/data-id="withdraw"/);
});

test('未入账更正允许发起人作废，已作废可返回原认定且不再审核',async()=>{
 const d={item:{id:'c1',kind:'correction',state:'RETURNED',version:1,data:{created_by:'t1',teacher_id:'t2',claim_id:'claim1',review_id:'r1'}},state_label:'退回补正',attachments:[],events:[]};
 const c=context({'/social/objects/social_resource/c1':d});c.periodName=esc;
 await socialAction('social-detail','social_resource|c1',c);
 assert.match(c.modalData.buttons,/data-id="void"/);assert.doesNotMatch(c.modalData.buttons,/social-correction-edit/);
 d.item.state='VOID';d.item.data.void_reason='差额填错';d.state_label='已作废';
 await socialAction('social-detail','social_resource|c1',c);
 assert.match(c.modalData.buttons,/social_claim\|claim1/);assert.match(c.modalData.body,/差额填错/);assert.doesNotMatch(c.modalData.buttons,/social-transition|social-upload/);
 d.item.state='ARCHIVED';d.state_label='已归档';await socialAction('social-detail','social_resource|c1',c);
 assert.doesNotMatch(c.modalData.buttons,/data-id="void"/);
});

test('教研室摘要使用本室名称及教师岗位，保留导出且没有写入口',async()=>{
 const d={readonly:true,readonly_reason:'仅本教研室摘要',item:{id:'p1',data:{name:'合成项目'},state:'FILED'},state_label:'已备案',facts:{units:[{external_key:'U1',data:{teachers:[{teacher_id:'t2',role:'lecturer'}]}}]}};
 const c=context({'/social/objects/social_project/p1':d});c.me.role.kind='dept';
 await socialAction('social-detail','social_project|p1',c);
 assert.match(c.modalData.body,/本教研室核算单元/);assert.match(c.modalData.body,/t2 · 主讲/);assert.match(c.modalData.buttons,/导出本教研室参与摘要/);assert.doesNotMatch(c.modalData.buttons,/social-upload|social-transition/);
});


test('教研室只读参与摘要保留关闭入口，导出仍取决于权限且没有业务写入',async()=>{
 const d={readonly:true,readonly_reason:'仅本教研室摘要',item:{id:'p-close',data:{name:'合成<项目>'},state:'FILED'},state_label:'已备案',facts:{units:[{external_key:'unit-close',data:{module:'本室课程',teachers:[{teacher_id:'t2',role:'instructor'}]}}]}};
 for(const exported of [true,false]){
  const c=context({'/social/objects':d},exported?['records.read','export']:['records.read']);c.me.role.kind='dept';
  await socialAction('social-detail','social_project|p-close',c);
  assert.match(c.modalData.body,/本教研室核算单元/);assert.match(c.modalData.body,/t2 · 实训指导/);assert.match(c.modalData.buttons,/data-action="close"/);
  assert.equal(c.modalData.buttons.includes('social-export'),exported);assert.equal(c.modalData.buttons.includes('detail-more-actions'),exported);
  assert.doesNotMatch(c.modalData.buttons,/social-upload|social-transition|social-project-edit/);assert.equal(c.modalData.contextLabel,'培训项目 / 本教研室参与摘要');
  assert.ok(c.requests.every(r=>!r.options));
 }
});

test('教研室只读资源详情按资料材料记录分区，返回课程仍保留原分页',async()=>{
 const d={view_only:true,view_only_reason:'本室可查阅资源',item:{id:'resource-readonly',kind:'course_resource',code:'R1',name:'资源<一>',state:'ACTIVE',data:{recognition:'核验依据'}},state_label:'已生效',attachments:[],events:[]};
 const c=context({'/social/objects':d});c.me.role.kind='dept';
 await socialAction('social-detail','social_resource|resource-readonly|C1|2',c);
 for(const id of ['social-info','social-materials','social-history']){assert.ok(c.modalData.body.includes('data-detail-section="'+id+'"'));assert.ok(c.modalData.body.includes('id="'+id+'"'))}
 assert.match(c.modalData.buttons,/social-course-resources" data-id="C1\|2"/);assert.match(c.modalData.buttons,/data-action="close"/);assert.match(c.modalData.buttons,/detail-more-actions/);
 assert.doesNotMatch(c.modalData.buttons,/social-upload|social-transition|social-resource-edit/);assert.equal(c.modalData.contextLabel,'课程资源 / 业务详情');assert.ok(c.requests.every(r=>!r.options));
});

test('教研室积分核对详情和三级确认表单显示办理对象，保存保留原版本和动作',async()=>{
 const d={item:{id:'review-context',kind:'point_review',name:'积分核对<一>',state:'DRAFT',version:7,data:{created_by:'t1',teacher_id:'t2',teaching:'-0.5',auxiliary:'0',period_id:'p1'}},state_label:'待发送教师',review_context:{teacher_name:'被核对教师',project:'合成项目'},workflow_blockers:[],attachments:[{id:'material'}],events:[]};
 const c=context({'/social/objects':d,'/social/point-reviews':d});c.me.role.kind='dept';c.periodName=esc;
 await socialAction('social-detail','social_resource|review-context',c);
 assert.match(c.modalData.body,/data-detail-section="social-info"/);assert.match(c.modalData.buttons,/detail-more-actions/);assert.equal(c.modalData.contextLabel,'积分核对 / 业务详情');
 await socialAction('social-transition','send',c);
 assert.match(c.formData.body,/本次办理对象/);assert.match(c.formData.body,/积分核对&lt;一&gt;/);assert.match(c.formData.body,/待发送教师/);assert.equal(c.formData.options.contextLabel,'积分核对 / 发给教师回应');
 assert.ok(c.requests.every(r=>!r.options));
 await c.formData.save({reason:'请核对授课积分',basis:'签到表'});
 const write=c.requests.find(r=>r.options?.method==='POST');assert.equal(write.url,'/social/point-reviews/review-context/actions');assert.equal(write.options.body.expected_version,7);assert.equal(write.options.body.action,'send');
});


test('教研室从无名称的积分认定发起核对时显示被核对教师，不沿用空业务名称',async()=>{
 const d={item:{id:'claim-context',teacher_id:'teacher-context',state:'ARCHIVED',data:{}},state_label:'已入账',attachments:[],events:[]};
 const c=context({'/social/objects':d});c.me.role.kind='dept';c.periodName=esc;c.teacherName=()=>'<被核对教师>';
 await socialAction('social-detail','social_claim|claim-context',c);await socialAction('social-review-new','',c);
 assert.match(c.formData.body,/&lt;被核对教师&gt;的积分认定/);assert.doesNotMatch(c.formData.body,/<被核对教师>/);assert.equal(c.formData.options.contextLabel,'积分认定 / 发起积分核对');assert.ok(c.requests.every(r=>!r.options));
});


test('学院年度自评三级办理条使用原学院和周期，名称安全转义且不写业务',async()=>{
 const d={item:{id:'annual-subject',org_id:'college1',period_id:'period1',owner_id:'t1',state:'DRAFT',version:3,data:{},snapshot:{}},state_label:'待提交学院自评',attachments:[{id:'annual-file'}],events:[]};
 const c=context({'/social/objects':d},['records.read','assessment.read','assessment.review','file.write']);c.me.role.kind='college';c.orgName=()=>'<所属学院>';c.periodName=()=>'<年度周期>';
 await socialAction('social-detail','social_annual|annual-subject',c);await socialAction('social-transition','submit',c);
 assert.match(c.formData.body,/本次办理对象/);assert.match(c.formData.body,/&lt;所属学院&gt; · &lt;年度周期&gt;/);assert.doesNotMatch(c.formData.body,/<所属学院>|<年度周期>|当前业务/);assert.equal(c.formData.options.contextLabel,'学院年度考核 / 提交学院自评');assert.ok(c.requests.every(r=>!r.options));
});
