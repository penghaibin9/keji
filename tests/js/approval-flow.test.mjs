// 审批流程精简第一、二期：逐份上传、补正一次办完、连续办理与批量办理只编排原单条接口。
import test from 'node:test';
import assert from 'node:assert/strict';
import {checkUploadFiles,uploadEntries,uploadSequential,runBatch,batchStage,batchMode,batchPerformer,nextCode,MAX_ATTACHMENTS} from '../../frontend/approval-flow.js';
import {socialAction} from '../../frontend/social-training.js';

const file=(name,body=name)=>new File([body],name,{type:name.endsWith('.pdf')?'application/pdf':'image/png'});
const sha=async f=>[...new Uint8Array(await crypto.subtle.digest('SHA-256',await f.arrayBuffer()))].map(b=>b.toString(16).padStart(2,'0')).join('');

// 模拟后端附件接口：每成功一份 version+1，版本不符或指定文件失败时拒绝；记录并发数。
function attachmentServer({version=3,fail=new Set(),landButFail=new Set()}={}){
 const state={version,attachments:[],posts:[],inFlight:0,maxInFlight:0};
 const api=async(url,options)=>{
  if(!options)return {item:{version:state.version},attachments:state.attachments};
  state.inFlight++;state.maxInFlight=Math.max(state.maxInFlight,state.inFlight);
  await new Promise(r=>setTimeout(r,1));
  try{
   const f=options.body.get('file'),expected=Number(options.body.get('expected_version'));state.posts.push({name:f.name,expected});
   if(expected!==state.version)throw Error('数据版本已变化，请刷新后重试');
   if(fail.has(f.name))throw Error('附件格式校验未通过');
   state.version++;state.attachments.push({id:'a'+state.attachments.length,name:f.name,sha256:await sha(f)});
   if(landButFail.has(f.name)){landButFail.delete(f.name);throw Error('网络连接中断。请检查学校网络后刷新；不要重复确认未知结果。')}
   return {id:'ok'};
  }finally{state.inFlight--}
 };
 return {state,api,latest:async()=>({version:state.version,attachments:state.attachments})};
}

test('多份材料严格顺序上传，版本逐份加一；一份失败其余照常，补传只重试失败那份',async()=>{
 const fail=new Set(['c.png']),server=attachmentServer({version:5,fail});
 const entries=uploadEntries([file('a.pdf'),file('b.png'),file('c.png'),file('d.pdf')]);
 const first=await uploadSequential({api:server.api,kind:'social_claim',id:'c1',version:5,entries,reason:'补充',latest:server.latest});
 assert.equal(server.state.maxInFlight,1,'不得并发上传');
 assert.deepEqual(server.state.posts.map(p=>[p.name,p.expected]),[['a.pdf',5],['b.png',6],['c.png',7],['d.pdf',7]]);
 assert.deepEqual(entries.map(e=>e.status),['done','done','failed','done']);
 assert.equal(first.failed.length,1);assert.match(first.failed[0].error,/格式校验/);assert.equal(first.version,8);
 server.state.posts.length=0;fail.delete('c.png');
 const again=await uploadSequential({api:server.api,kind:'social_claim',id:'c1',version:first.version,entries,reason:'补充',latest:server.latest});
 assert.deepEqual(server.state.posts.map(p=>[p.name,p.expected]),[['c.png',8]],'补传只发失败那一份');
 assert.equal(again.failed.length,0);assert.deepEqual(entries.map(e=>e.status),['done','done','done','done']);assert.equal(server.state.attachments.length,4);
});

test('补传成功后全部完成，已上传的不会重复上传',async()=>{
 const server=attachmentServer({version:1,fail:new Set(['b.png'])});
 const entries=uploadEntries([file('a.pdf'),file('b.png')]);
 await uploadSequential({api:server.api,kind:'social_claim',id:'c1',version:1,entries,reason:'r',latest:server.latest});
 server.state.posts.length=0;
 const fixed=attachmentServer({version:server.state.version});fixed.state.attachments=server.state.attachments;
 const result=await uploadSequential({api:fixed.api,kind:'social_claim',id:'c1',version:server.state.version,entries,reason:'r',latest:fixed.latest});
 assert.deepEqual(fixed.state.posts.map(p=>p.name),['b.png']);assert.equal(result.failed.length,0);assert.deepEqual(entries.map(e=>e.status),['done','done']);
});

test('响应丢失但材料已入库时按校验值确认，版本同步，不重复上传',async()=>{
 const server=attachmentServer({version:2,landButFail:new Set(['a.pdf'])});
 const entries=uploadEntries([file('a.pdf'),file('b.pdf')]);
 const result=await uploadSequential({api:server.api,kind:'social_claim',id:'c1',version:2,entries,reason:'r',latest:server.latest});
 assert.deepEqual(entries.map(e=>e.status),['done','done']);assert.equal(result.failed.length,0);
 assert.deepEqual(server.state.posts.map(p=>[p.name,p.expected]),[['a.pdf',2],['b.pdf',3]]);assert.equal(server.state.attachments.length,2);
});

test('选择材料先整体检查类型、大小和单个对象 50 份上限',()=>{
 assert.throws(()=>checkUploadFiles([file('a.heic')]),/\.jpg、\.png 或 \.pdf/);
 assert.throws(()=>checkUploadFiles([{name:'big.pdf',size:11*1024*1024}]),/超过 10 兆字节/);
 assert.throws(()=>checkUploadFiles([file('a.pdf'),file('b.pdf')],MAX_ATTACHMENTS-1),/最多 50 份附件，已有 49 份，本次最多还能选 1 份/);
 assert.equal(checkUploadFiles([file('a.pdf')],MAX_ATTACHMENTS-1).length,1);
});

test('批量中一条失败其余照常，失败条目带原因且不混入成功',async()=>{
 const calls=[];
 const result=await runBatch(['x','y','z'],async item=>{calls.push(item);if(item==='y')throw Error('审批依据已变化，请退回后重新试算提交\n请求编号：1');return item});
 assert.deepEqual(calls,['x','y','z']);assert.deepEqual(result.ok.map(x=>x.item),['x','z']);
 assert.deepEqual(result.failed,[{item:'y',error:'审批依据已变化，请退回后重新试算提交'}]);
});

test('只能同一业务、同一环节一起办理；本人事项和非审批环节不可勾选',()=>{
 const claim=(state,teacher='t1')=>({type:'social_claim',id:state+teacher,title:'社会培训积分认定',state,teacher_id:teacher});
 assert.equal(batchMode(claim('待院长初审'),'me'),'approve');assert.equal(batchMode(claim('待教学秘书归档'),'me'),'archive');
 assert.equal(batchMode(claim('待院长初审','me'),'me'),'');
 assert.equal(batchMode({type:'social_claim',title:'正式处理后待追加积分更正',state:'已归档',teacher_id:'t1'},'me'),'');
 assert.equal(batchMode({type:'assessment',title:'本级考核确认',state:'COLLEGE',teacher_id:'t1'},'me'),'confirm');
 assert.equal(batchMode({type:'assessment',title:'本人考核确认',state:'TEACHER',teacher_id:'me'},'me'),'');
 const stage=x=>batchMode(x,'me')?x.state:'';
 assert.equal(batchStage([claim('待院长初审'),claim('待院长初审','t2')],stage),'待院长初审');
 assert.throws(()=>batchStage([claim('待院长初审'),claim('待归口复审')],stage),/同一业务、同一审批环节/);
 assert.throws(()=>batchStage([claim('待院长初审'),{type:'assessment',title:'本级考核确认',state:'待院长初审',teacher_id:'t2'}],stage),/同一业务/);
 assert.throws(()=>batchStage([],stage),/请先勾选/);
});

test('批量逐条重新读取最新版本：本人事项、环节变化、未解决核对和来源变化单独拦下，其余各自调用原接口',async()=>{
 const details={
  ok1:{item:{id:'ok1',teacher_id:'t1',version:4},state_label:'待院长初审'},
  mine:{item:{id:'mine',teacher_id:'me',version:2},state_label:'待院长初审'},
  moved:{item:{id:'moved',teacher_id:'t2',version:9},state_label:'待归口复审'},
  ok2:{item:{id:'ok2',teacher_id:'t3',version:7},state_label:'待院长初审'},
  stale:{item:{id:'stale',teacher_id:'t4',version:3},state_label:'待院长初审'}
 },posts=[];
 const api=async(url,options)=>{if(options){posts.push({url,body:options.body});if(url.includes('/stale/'))throw Error('审批依据已变化，请退回后重新试算提交');return {}}return details[url.split('/').at(-1)]};
 const items=['ok1','mine','moved','ok2','stale'].map(id=>({type:'social_claim',id,title:'社会培训积分认定',state:'待院长初审',teacher_id:details[id].item.teacher_id}));
 const result=await runBatch(items,batchPerformer({api,meId:'me',mode:'approve',reason:'核对无误，审核通过',basis:'',total:items.length}));
 assert.deepEqual(result.ok.map(x=>x.item.id),['ok1','ok2']);
 assert.deepEqual(result.failed.map(x=>[x.item.id,x.error]),[['mine','本人申报按回避规定须由其他人员办理'],['moved','办理环节已变化（当前：待归口复审），请单独打开核对'],['stale','审批依据已变化，请退回后重新试算提交']]);
 // 本人事项和环节已变化的不发办理请求；其余各自带最新版本、各自留痕说明
 assert.deepEqual(posts.map(p=>[p.url,p.body.expected_version,p.body.action,p.body.basis]),[['/social/claims/ok1/actions',4,'approve','批量办理第1/5条'],['/social/claims/ok2/actions',7,'approve','批量办理第4/5条'],['/social/claims/stale/actions',3,'approve','批量办理第5/5条']]);
});

test('考核批量确认遇到未解决核对、积分核对或来源变化时不发确认请求',async()=>{
 const rows={a:{assessment:{teacher_id:'t1',state:'COLLEGE',version:2}},b:{assessment:{teacher_id:'t2',state:'COLLEGE',version:5},confirmation_blockers:{count:1}},c:{assessment:{teacher_id:'t3',state:'COLLEGE',version:5},source_changes:{changed:true}},d:{assessment:{teacher_id:'t4',state:'COLLEGE',version:5},open_point_reviews:1}},posts=[];
 const api=async(url,options)=>{if(options){posts.push(url);return {}}return rows[url.split('/').at(-1)]};
 const items=['a','b','c','d'].map(id=>({type:'assessment',id,title:'本级考核确认',state:'COLLEGE',teacher_id:rows[id].assessment.teacher_id}));
 const result=await runBatch(items,batchPerformer({api,meId:'me',mode:'confirm',reason:'核对无误',total:4}));
 assert.deepEqual(posts,['/assessments/a/actions']);assert.deepEqual(result.failed.map(x=>x.item.id),['b','c','d']);
 assert.match(result.failed[0].error,/数据核对尚未完成/);assert.match(result.failed[1].error,/计算依据已变化/);assert.match(result.failed[2].error,/积分核对尚未办结/);
});

test('连续办理只给出下一条位置',()=>{
 const queue={codes:['social_claim|a','social_claim|b','assessment|c']};
 assert.equal(nextCode(queue,'social_claim|a'),'social_claim|b');assert.equal(nextCode(queue,'assessment|c'),'');assert.equal(nextCode(queue,'x|y'),'');assert.equal(nextCode(null,'a'),'');
});

// ---- 社会培训页面：补正一次办完、办理区与查看下一条 ----
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function socialContext({me='teacher',duties=[],claim,handler,next=''}){
 const state={posts:[],toasts:[],modal:null,form:null,opened:[],renders:0};
 const workspace={projects:[{id:'p1',data:{name:'合成项目'}}],courses:[],resources:[],claims:[],annuals:[],policies:[{id:'pol',name:'口径',state:'ACTIVE',period_id:'y2026'}],my_duties:duties,course_stats:{},decisions:{},states:{},pagination:{total:0,page:1,size:20},resource_pagination:{total:0}};
 const c={esc,me:{user:{id:me,staff_no:'J1'},role:{kind:me==='teacher'?'teacher':'college'}},can:p=>['file.write','points.read','records.read'].includes(p),periods:[{id:'y2026',name:'2026年度',state:'OPEN',start_date:'2026-01-01',end_date:'2026-12-31'}],teachers:[],orgs:[],
  icon:()=>'',note:(t,w)=>'<p class="note'+(w?' warn':'')+'">'+esc(t)+'</p>',table:()=>'<table></table>',act:(label,action,id='')=>'<button data-action="'+action+'" data-id="'+esc(id)+'">'+esc(label)+'</button>',
  teacherName:id=>'教师'+id,periodName:id=>id,orgName:id=>id,downloads:list=>'<ul>'+(list||[]).map(a=>'<li>'+esc(a.name)+'</li>').join('')+'</ul>',eventsHtml:()=>'',
  field:(name,label,type,value,o={})=>'<label>'+esc(label)+(type==='select'?'<select name="'+name+'">'+(o.options||[]).map(([key,text])=>'<option value="'+esc(key)+'" '+(String(key)===String(value)?'selected':'')+'>'+esc(text)+'</option>').join('')+'</select>':'<input name="'+name+'" value="'+esc(value)+'">')+(o.checkLabel?esc(o.checkLabel):'')+'</label>',
  modal:(title,body,foot)=>{state.modal={title,body,foot}},formModal:(title,body,save,options)=>{state.form={title,body,save,options}},closeModal:()=>{},render:async()=>{state.renders++},
  toast:(m,e)=>state.toasts.push([m,!!e]),queueNext:code=>next&&code!==next?next:'',openNext:async code=>{state.opened.push(code)},
  api:async(url,options)=>{if(url.startsWith('/social/workspace'))return workspace;if(options){state.posts.push({url,options});return handler(url,options,state)}return {item:claim(),state_label:'退回补正',attachments:state.attachments||[{id:'old',name:'原认定表.pdf'}],events:[{action:'积分认定：退回补正',reason:'辅助积分日期写错'}],trial:{teaching:'6',auxiliary:'1',total:'7',blockers:[]}}}};
 return {c,state,workspace};
}
const returned=(extra={})=>({id:'c1',teacher_id:'teacher',project_id:'p1',period_id:'y2026',policy_id:'pol',state:'RETURNED',version:3,data:{recognition_form_reference:'原认定表',auxiliary:[]},...extra});
const formOf=files=>({querySelector:sel=>sel==='#f-file'?{files}:null,querySelectorAll:()=>[]});
const values={policy_id:'pol',period_id:'y2026',recognition_form_reference:'原认定表',reason:'按退回意见补正',basis:'',submit_now:true};

test('补正一次办完：集中显示退回原因和已有材料，保存补正→逐份上传→重新提交，版本逐步跟上',async()=>{
 let version=3;const {c,state}=socialContext({claim:()=>returned({version}),handler:(url,o)=>{if(o.method==='PUT'){version=4;return {item:returned({version:4})}}if(url.startsWith('/attachments/')){version++;return {}}return {}}});
 await socialAction('social-detail','social_claim|c1',c);await socialAction('social-claim-edit','',c);
 assert.match(state.form.body,/退回意见：辅助积分日期写错/);assert.match(state.form.body,/原认定表\.pdf/);assert.match(state.form.body,/multiple/);
 assert.equal(state.form.options.submit,'保存补正并重新提交');assert.match(state.form.body,/2026年度/);assert.match(state.form.body,/<select name="period_id">/);assert.match(state.form.body,/value="y2026" selected/);
 await state.form.save(values,formOf([file('补正1.pdf'),file('补正2.png')]));
 assert.deepEqual(state.posts.map(p=>[p.options.method,p.url,p.options.body?.expected_version??Number(p.options.body.get?.('expected_version'))]),[['PUT','/social/claims/c1',3],['POST','/attachments/social_claim/c1',4],['POST','/attachments/social_claim/c1',5],['POST','/social/claims/c1/actions',6]]);
 assert.equal(state.posts.at(-1).options.body.action,'submit');assert.deepEqual(state.toasts,[['补正已保存并重新提交审批',false]]);
});

test('退回补正期限口径未配置时提交被拦，提示已保存、未提交，不报成功',async()=>{
 const {c,state}=socialContext({claim:()=>returned(),handler:(url,o)=>{if(o.method==='PUT')return {item:returned({version:4})};if(url.endsWith('/actions'))throw Error('退回补正的期限口径尚待学校确认\n请求编号：x');return {}}});
 await socialAction('social-detail','social_claim|c1',c);await socialAction('social-claim-edit','',c);
 await state.form.save(values,formOf([]));
 assert.equal(state.toasts.length,1);const [msg,isError]=state.toasts[0];
 assert.equal(isError,true);assert.match(msg,/^补正已保存，但尚未提交：学校尚未确认退回补正的期限口径/);assert.doesNotMatch(msg,/已提交审批|重新提交审批/);
 // 保存后自动回到详情，详情顶部继续显示“已保存、未提交”
 assert.match(state.modal.body,/补正已保存，但尚未提交/);assert.match(state.modal.foot,/提交本人积分申报/);
});

test('补正时一份材料没传上去：不提交，详情只补传失败那份，补齐后接着提交',async()=>{
 let version=4,failing=true;const uploaded=[];
 const {c,state}=socialContext({claim:()=>returned({version}),handler:(url,o)=>{if(o.method==='PUT'){version=4;return {item:returned({version:4})}}if(url.startsWith('/attachments/')){const f=o.body.get('file');if(f.name==='坏.png'&&failing)throw Error('附件格式校验未通过');uploaded.push([f.name,Number(o.body.get('expected_version'))]);version++;return {}}return {}}});
 await socialAction('social-detail','social_claim|c1',c);await socialAction('social-claim-edit','',c);
 await state.form.save(values,formOf([file('好1.pdf'),file('坏.png'),file('好2.pdf')]));
 assert.deepEqual(uploaded,[['好1.pdf',4],['好2.pdf',5]]);assert.ok(!state.posts.some(p=>p.url.endsWith('/actions')),'有材料失败时不得提交');
 assert.match(state.toasts[0][0],/2 份材料已上传，1 份没有传上去，尚未提交/);assert.equal(state.toasts[0][1],true);
 await socialAction('social-detail','social_claim|c1',c);
 assert.match(state.modal.foot,/只补传失败的 1 份并提交/);assert.match(state.modal.body,/坏\.png/);
 failing=false;await socialAction('social-upload-retry','',c);
 assert.deepEqual(uploaded.at(-1),['坏.png',6]);assert.equal(uploaded.length,3,'已上传的两份不重传');
 const submit=state.posts.at(-1);assert.equal(submit.url,'/social/claims/c1/actions');assert.equal(submit.options.body.expected_version,7);
});

test('审核意见保留在资料后，底部确认只办理当前条，下一条只导航',async()=>{
 const claim=()=>returned({teacher_id:'t9',state:'SUBMITTED',version:8});
 const {c,state}=socialContext({me:'dean',duties:['dean'],claim,next:'social_claim|c2',handler:()=>({})});
 await socialAction('social-detail','social_claim|c1',c);
 assert.match(state.modal.body,/本环节办理/);assert.match(state.modal.body,/核对无误，审核通过/);assert.doesNotMatch(state.modal.body,/通过并查看下一条/);assert.match(state.modal.foot,/data-action="social-handle"/);assert.ok(state.modal.body.indexOf('id="social-materials"')<state.modal.body.indexOf('id="approval-opinion"'));
 assert.match(state.modal.body,/教师t9/);assert.match(state.modal.body,/合计 7/);assert.match(state.modal.foot,/退回补正/);assert.match(state.modal.foot,/查看下一条/);
 assert.equal(state.posts.length,0,'打开详情不办理');
 globalThis.document={getElementById:id=>({'handle-reason':{value:'核对无误，审核通过'},'handle-basis':{value:''}})[id]||null,querySelectorAll:()=>[]};
 try{await socialAction('social-handle','approve',c)}finally{delete globalThis.document}
 assert.equal(state.posts.length,1);assert.deepEqual([state.posts[0].url,state.posts[0].options.body.action,state.posts[0].options.body.expected_version],['/social/claims/c1/actions','approve',8]);
 assert.deepEqual(state.opened,[]);await socialAction('social-next','',c);assert.equal(state.posts.length,1);assert.deepEqual(state.opened,['social_claim|c2']);
});

test('本人申报不出现办理区；退回、作废等意见不预填，须具体填写',async()=>{
 const own=socialContext({me:'dean',duties:['dean'],claim:()=>returned({teacher_id:'dean',state:'SUBMITTED'}),handler:()=>({})});
 await socialAction('social-detail','social_claim|c1',own.c);
 assert.doesNotMatch(own.state.modal.body,/本环节办理/);assert.match(own.state.modal.body,/回避规定/);
 const other=socialContext({me:'dean',duties:['dean'],claim:()=>returned({teacher_id:'t9',state:'SUBMITTED'}),handler:()=>({})});
 await socialAction('social-detail','social_claim|c1',other.c);await socialAction('social-transition','return',other.c);
 assert.equal(other.state.form.options.reasonDefault,'');assert.match(other.state.form.options.reasonLabel,/退回原因/);
});

test('制度草稿继续填写和复制都保留零、否以及原校历，复制不覆盖旧版本',async()=>{
 const policy={id:'policy-preserve',name:'学校已填口径',period_id:'y2026',state:'DRAFT',version:9,data:{title_precision:0,satisfaction_inclusive:false,total_cap:0,grade_mode:'four',excellent_from:90,holidays:['2026-10-01'],workdays:[],calendar_reference:'校历通知'}};
 const {c,state}=socialContext({me:'policy-preserve',claim:()=>policy,handler:()=>({})});
 await socialAction('social-detail','social_policy|policy-preserve',c);
 for(const action of ['social-policy-edit','social-policy-copy']){
  await socialAction(action,'',c);
  assert.match(state.form.body,/value="0" selected/);
  assert.match(state.form.body,/value="false" selected/);
  assert.match(state.form.body,/value="2026-10-01"/);
  assert.equal(state.form.options.partialDraft,true);
  await state.form.save({name:'保存口径',period_id:'y2026',title_precision:'0',satisfaction_inclusive:'false',total_cap:0,excellent_from:90,holidays:'2026-10-01',workdays:'',reason:'保留原值',basis:''});
  const {url,options}=state.posts.at(-1);
  assert.equal(url,action.endsWith('edit')?'/social/policies/policy-preserve':'/social/policies');
  assert.equal(options.method,action.endsWith('edit')?'PUT':'POST');
  assert.equal(options.body.data.title_precision,0);assert.equal(options.body.data.satisfaction_inclusive,false);
  assert.equal(options.body.data.total_cap,0);assert.equal(options.body.data.excellent_from,90);
  assert.deepEqual(options.body.data.holidays,['2026-10-01']);
  assert.equal(options.body.expected_version,action.endsWith('edit')?9:undefined);
 }
});

test('打开表单刷新周期，空周期明确拦截，重叠周期不擅自选择',async()=>{
 const {c,state}=socialContext({me:'period-refresh',claim:()=>returned(),handler:()=>({})});
 let calls=0;c.refreshPeriods=async()=>{calls++;return []};
 await assert.rejects(socialAction('social-policy-new','',c),/没有开放的考核周期/);
 assert.equal(calls,1);assert.equal(state.form,null);
 c.refreshPeriods=async()=>{calls++;return ['a','b'].map(id=>({id,name:'周期'+id,state:'OPEN',start_date:'2000-01-01',end_date:'2200-12-31'}))};
 await socialAction('social-policy-new','',c);
 assert.match(state.form.body,/<option value="" selected>请选择适用年度或学年/);
 await socialAction('social-annual-new','',c);
 assert.match(state.form.body,/当前适用周期不能唯一确定/);
 assert.match(state.form.body,/<option value="" selected>请选择认定周期/);
 assert.equal(calls,3);
});

test('年度新建和补正不把前端成果分页当作完整成果清单回传',async()=>{
 const annual={id:'annual-preserve',org_id:'college',period_id:'y2026',policy_id:'pol',state:'RETURNED',version:7,data:{self_report:'原自评',achievements:['old-hidden-item']}};
 const {c,state,workspace}=socialContext({me:'annual-preserve',claim:()=>annual,handler:()=>({})});
 workspace.resources=Array.from({length:200},(_,i)=>({id:'partial-'+i,kind:'achievement',org_id:'college',state:'APPROVED',data:{}}));
 await socialAction('social-annual-new','',c);
 await state.form.save({org_id:'college',period_id:'y2026',policy_id:'pol',self_report:'新自评',reason:'登记',basis:''});
 assert.equal(Object.hasOwn(state.posts.at(-1).options.body.data,'achievements'),false);
 await socialAction('social-detail','social_annual|annual-preserve',c);
 await socialAction('social-annual-edit','',c);
 await state.form.save({period_id:'y2026',policy_id:'pol',self_report:'只改文字',reason:'补正',basis:''});
 const payload=state.posts.at(-1).options.body;
 assert.equal(Object.hasOwn(payload.data,'achievements'),false);assert.equal(payload.expected_version,7);
});

test('职责配置保存完整原办理人，不依赖人员列表第一页',async()=>{
 const {c,state}=socialContext({me:'duties-preserve',claim:()=>returned(),handler:()=>({})}),api=c.api;
 const assignments={dean:['first','beyond-200'],finance:['other-college']};
 c.api=async(url,options)=>url==='/social/duties'&&!options?{version:11,labels:{dean:'院长审核',finance:'财务审核'},assignments,people:[{id:'beyond-200',name:'后页办理人'}]}:api(url,options);
 await socialAction('social-duties','',c);
 assert.ok(state.form,'应打开职责配置表单');
 await state.form.save({reason:'核对原配置',basis:''});
 assert.deepEqual(state.posts.at(-1).options.body.assignments,assignments);
 assert.equal(state.posts.at(-1).options.body.expected_version,11);
});

test('结项整改条件放在结项情况内，不创建隐藏后的空整改步骤',async()=>{
 const project={id:'close-steps',state:'FILED',version:3,closeout:{},data:{name:'结项验证项目',category:'other',code:'TEST-CLOSE'}};
 const {c,state}=socialContext({me:'close-steps',claim:()=>project,handler:()=>({})}),api=c.api;
 c.api=async(url,options)=>url==='/social/objects/social_project/close-steps'&&!options?{item:project,facts:{units:[],followups:[],effective:0,excluded:0},attachments:[],events:[]}:api(url,options);
 await socialAction('social-detail','social_project|close-steps',c);
 await socialAction('social-close','',c);
 const first=state.form.body.match(/<fieldset class="social-fieldset">([\s\S]*?)<\/fieldset>/)?.[1];
 assert.ok(first,'应存在结项情况分组');
 assert.match(first,/<legend>一、结项情况<\/legend>/);
 assert.match(first,/id="cond-rect"/);
 assert.match(first,/name="rectification"/);assert.match(first,/name="rectification_due"/);
 assert.doesNotMatch(state.form.body,/<legend>整改/);
 assert.equal((state.form.body.match(/class="social-fieldset"/g)||[]).length,4,'普通结项为三个业务分组加办理说明');
});
