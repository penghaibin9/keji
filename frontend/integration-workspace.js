const statusNames={materials:'资料齐备',configuration:'配置有效',tests:'测试结果',published:'配置发布',health:'运行健康',acceptance:'学校验收'};
const steps=[['materials','接入资料'],['protocol','协议与环境'],['credentials','回调及凭据'],['identity','字段与身份范围'],['tests','测试与样本预览'],['publish','发布与同步计划'],['diagnostics','日志诊断及交付']];

export function renderCenterStatus(items,c){
 const rows=items.map(w=>[c.esc(w.name),...Object.keys(statusNames).map(k=>c.esc(w.statuses[k])),c.act('进入实施流程','nav',w.code==='middle'?'hub':w.code,'primary')]);
 return `<section class="card"><div class="card-head"><div><h2>统一认证与接口适配中心</h2><p>资料、配置、测试、发布、健康、验收分别记录；不以一个连接状态代替全部结果。</p></div></div>${c.table(['对接项目',...Object.values(statusNames),'操作'],rows)}</section>`;
}

function statusStrip(w,c){
 return `<div class="implementation-status">${Object.entries(statusNames).map(([key,label])=>`<section><span>${label}</span><strong>${c.esc(w.statuses[key])}</strong></section>`).join('')}</div>`;
}

export async function renderImplementationWorkspace(id,step,c){
 const w=await c.api('/connections/'+id+'/implementation');
 if(!steps.some(([key])=>key===step))step='materials';
 const buttons=(...items)=>`<div class="action-row">${items.join('')}</div>`;
 const edit=c.act('编辑协议与基础参数','connection',id,'primary');
 let body='';
 if(step==='materials'){
  const rows=w.materials.required.map(name=>{const x=w.materials.items.find(x=>x.name===name)||{};return [c.esc(name),c.esc(x.owner||'待登记'),c.esc(x.reference||'待提供'),c.esc(x.confirmed_on||'待确认')];});
  body=c.note('按学校真实资料登记责任人、文档编号和确认日期。连接成功不会自动把资料标成齐全。')+c.table(['资料项目','责任人','文档 / 证据编号','确认日期'],rows)+buttons(c.act('登记学校资料','impl-materials',id,'primary'));
 }else if(step==='protocol'){
  body=c.note('当前支持 CAS、OIDC、OAuth2 和 JSON-ticket。请按学校正式规范选择协议，不把未实现的协议标成已支持。')+buttons(edit)+`<h3 class="mt20">草稿配置校验</h3>${w.issues.length?c.note(w.issues.join('；'),true):c.note('配置结构检查通过，仍需真实连接和身份验证。')}`;
  if(w.code!=='sso')body+=c.table(['业务类型','权威来源','采集或报送规则'],(w.data_types||[]).map(x=>[c.esc(x.name),x.source_status==='WAITING_SOURCE'?'待确认权威来源':'本地处理能力已有',c.act('编辑这类规则','data-type-adapter',id+'|'+x.code)]));
 }else if(step==='credentials'){
  const callbackRows=[['login','正式登录回调'],['test_login','实施试登录回调'],['logout_return','退出后返回地址']].map(([key,label])=>[label,`<code>${c.esc(w.callbacks[key])}</code>`,c.act('复制','impl-copy',id+'|'+key)]);
  body=c.note('下列地址由服务器网站来源生成，只读。请将正式回调和实施试登录回调分别交给学校登记，网页填写探测地址不会改变正式回调。')+c.table(['用途','学校需登记的地址','操作'],callbackRows)+`<p class="mt16">凭据引用：<code>${c.esc(w.credential.reference||'待配置')}</code> · ${w.credential.configured?'服务器已配置凭据':'服务器尚未配置凭据'}</p>`+c.note('真实密钥、私钥和学校私有 CA 由服务器管理员通过安全渠道管理；页面不接收或回显这些内容。');
 }else if(step==='identity'){
  body=c.note('编辑的是草稿。统一认证样本使用真实登录的同一身份解析器，并预览本地账号、组织和权限范围；不会创建会话或自动授权。')+buttons(c.act(w.code==='sso'?'编辑身份映射':'编辑字段映射',w.code==='sso'?'connection':'mapping-editor',id,'primary'),c.act('预览脱敏样本','mapping-trial',id));
 }else if(step==='tests'){
  const check=w.check,preview=check?.receipt?.preview;
  body=c.note('配置检查、真实鉴权、浏览器身份核对是不同测试。测试替身和本地样本不能发布正式连接；退出登录仍需学校真实环境验证。')+buttons(c.act('测试草稿连通与鉴权','impl-probe',id,'primary'),...(w.code==='sso'?[c.act('浏览器试登录（不切换本地账号）','impl-login-test',id)]:[]),c.act('预览脱敏样本','mapping-trial',id));
  if(check)body+=`<h3 class="mt20">最近一次草稿验证</h3>${c.table(['验证方式','结果','记录时间','发布证明有效至'],[[(check.mode==='REAL'?'真实联调':'本地测试（不可发布）'),check.passed?'本次通过':'本次未通过',c.ts(check.created_at),c.ts(check.expires_at)]])}`+c.note(check.receipt?.diagnostic?.message||check.reason_code,!check.passed);
  if(preview?.binding)body+=c.table(['本地账号','组织','角色','最终数据范围'],[[c.esc(preview.binding.account),c.esc(preview.binding.organization),c.esc(preview.binding.role),c.esc(preview.binding.scope)]]);
  if(preview?.errors?.length)body+=c.note(preview.errors.join('；'),true);
 }else if(step==='publish'){
  body=`<p>当前生效版本：<strong>${w.connection_version}</strong>；草稿版本：<strong>${w.has_draft?w.draft_version:'尚未建立'}</strong>。</p>`+c.note('保存草稿不会断开当前连接。发布前服务端再次核对配置、证明、凭据和版本；发布后同步计划需重新批准。旧的已确认业务数据不会自动改写。')+buttons(c.act('确认发布已验证草稿','impl-publish',id,'primary'),...(w.has_draft?[c.act('放弃草稿并回读生效版','impl-reset',id)]:[]),...(w.code==='middle'?[c.act('配置同步计划','integration-tab','schedules')]:[]));
 }else{
  const d=w.health?.diagnostic;
  body=c.note('健康检查只记录运行情况，不因 24 小时证明到期或一次健康检查而撤销发布授权。实际调用仍严格校验地址、配置、适配器和凭据。')+buttons(c.act('检查当前连接健康','impl-health',id,'primary'),...(w.code!=='sso'?[c.act('查看同步任务','integration-tab','tasks')]:[]),c.act('下载实施交接包','impl-handover',id));
  if(d)body+=c.table(['失败阶段 / 结果','处理建议','追踪编号','检查时间'],[[c.esc(d.message),c.esc(d.remedy),c.esc(d.trace_id),c.ts(d.checked_at)]]);
 }
 return statusStrip(w,c)+`<nav class="implementation-steps" aria-label="接口实施七步">${steps.map(([key,label],index)=>c.act((index+1)+' · '+label,'impl-step',key,key===step?'primary':'')).join('')}</nav><section class="card"><div class="card-head"><h2>${steps.find(([key])=>key===step)[1]}</h2><span>当前操作：${w.has_draft?'配置草稿':'生效配置只读查看'}</span></div><div class="card-pad">${body}</div></section>`+(w.source_gaps.length?c.note('尚待确认权威来源：'+w.source_gaps.join('、')+'。这些业务类型不能计作采购验收完成。',true):'');
}

export async function handleImplementationAction(action,id,c){
 if(action==='impl-step'){await c.setStep(id);return;}
 const [connectionId,key]=String(id).split('|');
 if(action==='impl-handover'){await c.download('/connections/'+connectionId+'/handover.zip');return;}
 const w=await c.api('/connections/'+connectionId+'/implementation');
 if(action==='impl-copy'){
  const value=w.callbacks[key];if(typeof value!=='string')throw Error('回调用途无效');
  if(navigator.clipboard){await navigator.clipboard.writeText(value);c.toast('已复制服务器生成的地址');}
  else c.modal('复制学校登记地址',`<input aria-label="学校登记地址" readonly value="${c.esc(value)}">`,c.act('关闭','close'));
  return;
 }
 if(action==='impl-materials'){
  const fields=w.materials.required.map((name,index)=>{const x=w.materials.items.find(x=>x.name===name)||{};return `<section class="full"><h3>${c.esc(name)}</h3><div class="form-grid">${c.field('owner_'+index,'责任人','text',x.owner||'',{required:false})}${c.field('reference_'+index,'文档或证据编号','text',x.reference||'',{required:false})}${c.field('date_'+index,'双方确认日期','date',x.confirmed_on||'',{required:false})}</div></section>`;}).join('');
  c.formModal('登记学校实施资料',fields+c.reasonFields(),async v=>{
   const items=w.materials.required.map((name,index)=>({name,owner:v['owner_'+index]||'',reference:v['reference_'+index]||'',confirmed_on:v['date_'+index]||null}));
   await c.api('/connections/'+connectionId+'/materials',{method:'PUT',body:{expected_version:w.materials.version,items,reason:v.reason,basis:v.basis}});
   c.closeModal();await c.render();c.toast('资料登记已保存；学校验收状态未改变');
  },{wide:true,submit:'保存资料登记'});return;
 }
 const names={'impl-probe':'测试草稿连接','impl-publish':'发布已验证草稿','impl-health':'检查当前运行健康','impl-reset':'放弃当前草稿','impl-login-test':'发起认证浏览器试登录'};
 if(!names[action])throw Error('未知实施操作');
 if(action!=='impl-health'&&!w.has_draft)throw Error('请先在协议与环境中编辑并保存一份草稿');
 let fields=c.reasonFields();
 if(action==='impl-publish')fields=c.note('只有当前版本的真实验证可发布。发布会暂停旧同步计划；业务历史和学校验收状态不会改变。',true)+c.field('confirm_schedule_pause','发布影响确认','checkbox',false,{required:false,full:true,checkLabel:'我已核对草稿，并确认发布后重新批准同步计划'})+fields;
 c.formModal(names[action],fields,async v=>{
  const body={expected_version:w.connection_version,reason:v.reason,basis:v.basis};
  const part={'impl-probe':'probe','impl-publish':'publish','impl-reset':'reset','impl-login-test':'login-test'}[action];
  if(action!=='impl-health')body.draft_version=w.draft_version;
  if(action==='impl-publish')body.confirm_schedule_pause=v.confirm_schedule_pause===true;
  const result=await c.api('/connections/'+connectionId+(action==='impl-health'?'/health':'/draft/'+part),{method:'POST',body});
  c.closeModal();
  if(result.redirect_url){location.assign(result.redirect_url);return;}
  await c.render();
  if(action==='impl-publish')c.toast('已发布；请重新批准同步计划，学校验收仍待签认');
  else c.toast(result.check?.passed===false?'本次检查未通过，请查看验证结果':'操作结果已记录，当前状态以页面分项结果为准',result.check?.passed===false);
 },{wide:true,submit:names[action]});
}
