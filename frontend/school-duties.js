// 用户与权限 › 学校审批职责：10 个学校级审批职责每行一条，显示管哪些流程哪一级、当前人员和缺人后果，可直接添加、移除办理人。
// 读写复用 /social/duties、/social/duty-options（带版本号整份保存）；给人加“学校业务审核”兼任身份复用账号保存接口 PUT /users/{id}。
// 权限、回避和留痕仍由后端把关：这里只是配置入口。
'use strict';

// 每个职责管哪些流程的哪一级、没人时会卡住什么（只放前端说明文字）。
export const DUTY_INFO={
 dean:{flows:['社会培训积分认定：第 1 级（院长初审）','积分更正：第 1 级','积分核对：学院裁定'],stuck:'老师的积分申报提交不了（系统会提示审批职责尚未就绪）。'},
 coordinator:{flows:['培训项目申请：学校审核备案','培训项目结项：学校结项核验（含材料核对）','培训课程申报：学校审批','培训基地申请：学校审批','积分认定、积分更正：第 2 级（归口复审）','学院年度考核：归口初核、异议处理、退回'],stuck:'项目、结项、课程、基地走到学校这一级会停住，积分申报也提交不了。'},
 vice_president:{flows:['社会培训积分认定：第 3 级（分管副校长）','积分更正：第 3 级'],stuck:'老师的积分申报提交不了。'},
 secretary:{flows:['社会培训积分认定：第 4 级（归档入账）','积分更正：归档入账','积分双月汇总与年度公示','学院年度考核：公示期满归档'],stuck:'积分申报提交不了；积分汇总和年度考核归档没人办。'},
 finance:{flows:['学院年度考核：财务核验'],stuck:'学院年度考核停在职能部门初核。'},
 academic:{flows:['学院年度考核：成果核验'],stuck:'学院年度考核停在职能部门初核。'},
 discipline:{flows:['学院年度考核：纪检核验'],stuck:'学院年度考核停在职能部门初核。'},
 committee:{flows:['学院年度考核：委员会评分并发布公示'],stuck:'学院年度考核停在委员会评审。'},
 trainer_hr:{flows:['校内培训师申报：组织人事部认定（学院审核后，须填认定文号）'],stuck:'校内培训师申报停在组织人事部认定。'},
 trainer_filing:{flows:['外聘培训师备案：教务处备案审核'],stuck:'外聘培训师备案停在教务处。'},
};
const DUTY_ORDER=['coordinator','dean','vice_president','secretary','trainer_hr','trainer_filing','finance','academic','discipline','committee'];

let state=null;

export function dutyRows(d){
 const people=new Map((d.people||[]).map(p=>[p.id,p]));
 const codes=[...DUTY_ORDER.filter(k=>d.labels?.[k]),...Object.keys(d.labels||{}).filter(k=>!DUTY_ORDER.includes(k))];
 return codes.map(code=>{const ids=d.assignments?.[code]||[],list=ids.map(id=>people.get(id)||{id,name:'原账号已不存在',org_name:'',usable:false}),usable=list.filter(p=>p.usable).length;
  return {code,label:d.labels[code],info:DUTY_INFO[code]||{flows:[],stuck:''},people:list,usable,missing:usable===0,single:usable===1}});
}

export async function dutiesTabHtml(c){
 const d=await c.api('/social/duties');state=d;
 const e=c.esc,rows=dutyRows(d),missing=rows.filter(r=>r.missing),single=rows.filter(r=>r.single);
 const alert=missing.length||single.length?`<section class="duty-gap-notice" role="status"><div><h3>${missing.length?'有 '+missing.length+' 个学校审批职责还没有可办理的人':'有职责只配了 1 人'}</h3><ul>${missing.map(r=>`<li><strong>${e(r.label)}</strong>：还没有人担任。${e(r.info.stuck)}</li>`).join('')}${single.map(r=>`<li><strong>${e(r.label)}</strong>：只有 1 人，本人申请回避时就没人办，建议再加一位。</li>`).join('')}</ul><p>在下面对应那一行点“添加”，按姓名或工号找人。等待中的申请会自动进入新办理人的待办，不用重新提交。</p></div></section>`:'';
 const body=rows.map(r=>[
  `<strong>${e(r.label)}</strong>${r.missing?'<div class="cell-sub red">缺人</div>':r.single?'<div class="cell-sub">只有 1 人</div>':''}`,
  `<ul class="duty-flows">${r.info.flows.map(f=>`<li>${e(f)}</li>`).join('')}</ul>`,
  (r.people.length?r.people.map(p=>`<span class="org-head${p.usable?'':' is-unusable'}">${e(p.name)}${p.org_name?' · '+e(p.org_name):''}${p.usable?'':' · 账号不可用'}<button type="button" class="org-head-remove" data-action="duty-remove" data-id="${e(r.code+'|'+p.id)}" aria-label="移除 ${e(p.name)} 的${e(r.label)}职责">移除</button></span>`).join(' '):`<span class="red">尚未配置</span>`)+(r.missing?`<p class="cell-sub red">${e(r.info.stuck)}</p>`:''),
  c.act('添加','duty-add',r.code,r.missing?'primary':'light','plus')]);
 return alert+`<section class="card"><div class="card-head"><div><h2>学校审批职责</h2><p>流程走到学校这一级（以及积分认定、年度考核各环节）时，交给担任对应职责的人办理。同一职责任何一位办理即可；本人的申请自动回避，每个职责建议至少两人。被选的人要有学校类型、带审核权限的身份（如“学校业务审核”），没有时添加时可以一步加上。</p></div></div>${c.table(['职责','管哪些流程、哪一级','当前人员（姓名 · 组织）','操作'],body)}</section>`;
}

// 用最新的职责配置（带版本号）只改这一个职责的人员，避免覆盖别人刚保存的其他职责。
async function saveDuty(c,code,change,reason,basis=''){
 const d=await c.api('/social/duties'),assignments=Object.fromEntries(Object.entries(d.assignments||{}).map(([k,v])=>[k,[...v]]));
 const ids=new Set(assignments[code]||[]);change(ids);assignments[code]=[...ids];
 return c.api('/social/duties',{method:'PUT',body:{expected_version:d.version,assignments,reason,basis}});
}

export function schoolReviewRole(roles){
 const ok=r=>r&&r.active!==false&&r.kind==='school'&&(r.permissions||[]).includes('assessment.review')&&!(r.permissions||[]).some(p=>['users.manage','roles.manage','settings.manage'].includes(p));
 return roles.find(r=>r.code==='school_review'&&ok(r))||roles.find(ok)||null;
}

// 给账号加“学校业务审核”兼任身份（组织选学校），沿用原账号字段，经 PUT /users/{id} 保存。
export function accountWithSchoolReview(account,role,schoolOrgId){
 const extras=(account.extra_identities||[]).map(x=>({role_id:x.role_id,org_id:x.org_id,valid_until:x.valid_until||null}));
 if(!(account.role_id===role.id&&account.org_id===schoolOrgId)&&!extras.some(x=>x.role_id===role.id&&x.org_id===schoolOrgId))extras.push({role_id:role.id,org_id:schoolOrgId,valid_until:null});
 return {name:account.name,title:account.title||'',org_id:account.org_id,role_id:account.role_id,active:account.active,is_admin:!!account.is_admin,expected_version:account.version,extra_identities:extras};
}

async function addForm(code,c){
 const label=state?.labels?.[code]||code,e=c.esc;let picked=null,seq=0;
 c.formModal('添加办理人 · '+label,`<div class="full"><p class="muted small">${e((DUTY_INFO[code]?.flows||[]).join('；'))}</p><label for="duty-q">按姓名、工号或账号搜索</label><input id="duty-q" type="search" autocomplete="off" placeholder="输入姓名或工号"><div id="duty-results" class="head-results mt12" role="radiogroup" aria-label="候选人员"></div><p id="duty-picked" class="hint" aria-live="polite">还没有选人。</p></div>`+c.reasonFields('学校指定'+label+'办理人','办理说明'),async v=>{
  if(!picked)throw Error('请先从搜索结果里选一个人');
  if(!picked.eligible){
   const roles=(await c.api('/roles')).items,role=schoolReviewRole(roles),school=c.orgs.find(o=>o.kind==='school'&&!o.parent_id);
   if(!role)throw Error('系统里还没有“学校业务审核”这类学校审核角色，请先在“角色与授权”里建立，或由管理员执行 approver_setup ensure-role');
   if(!school)throw Error('没有找到学校这一级组织');
   await c.api('/users/'+picked.id,{method:'PUT',body:{...accountWithSchoolReview(picked.account,role,school.id),reason:'为担任“'+label+'”添加学校业务审核兼任身份：'+v.reason,basis:v.basis||''}});
  }
  await saveDuty(c,code,ids=>ids.add(picked.id),v.reason,v.basis||'');
  c.closeModal();c.toast('已把 '+picked.name+' 加为“'+label+'”办理人'+(picked.eligible?'':'（已同时添加学校业务审核兼任身份，对方需重新登录）'));await c.render();
 },{wide:true,submit:'确认添加',hint:'保存时后端再次核对身份和组织范围；本人申请仍自动回避。'});
 if(typeof document==='undefined')return;
 const input=document.getElementById('duty-q'),box=document.getElementById('duty-results'),note=document.getElementById('duty-picked');let items=[];
 const current=new Set(state?.assignments?.[code]||[]);
 const load=async()=>{const n=++seq;box.innerHTML='<p class="muted small">正在查找…</p>';try{const r=await c.api('/social/duty-options?'+new URLSearchParams({duty:code,q:input.value.trim(),page:1}));if(n!==seq||!box.isConnected)return;items=r.items;
  box.innerHTML=items.map(p=>`<label class="head-candidate"><input type="radio" name="duty_person" value="${e(p.id)}" ${current.has(p.id)?'disabled':''}><span>${e(p.name)} · ${e(p.org_name||'')}<small>${e(p.staff_no||p.username||'')}${current.has(p.id)?' · 已担任':p.eligible?'':' · 还没有学校审核身份，添加时会一并加上“学校业务审核”'}</small></span></label>`).join('')||'<p class="hint">没有匹配人员，请换姓名或工号。</p>'}catch(err){if(n===seq&&box.isConnected)box.textContent='人员读取失败：'+err.message}};
 input.addEventListener('keydown',ev=>{if(ev.key==='Enter'){ev.preventDefault();load()}});input.addEventListener('input',()=>{clearTimeout(input._t);input._t=setTimeout(load,300)});
 box.addEventListener('change',ev=>{const id=ev.target?.value;picked=items.find(p=>p.id===id)||null;if(note)note.textContent=picked?('已选：'+picked.name+(picked.eligible?'':'。此人还没有学校审核身份，确认后会先给他添加“学校业务审核”兼任身份（组织：学校），再加入本职责；对方需要重新登录。')):'还没有选人。'});
 load();
}

function removeForm(id,c){
 const [code,userId]=id.split('|'),label=state?.labels?.[code]||code,p=(state?.people||[]).find(x=>x.id===userId),name=p?.name||'该人员';
 const left=(state?.assignments?.[code]||[]).filter(x=>x!==userId).length;
 c.formModal('移除办理人 · '+label,`<p class="full">把 <strong>${c.esc(name)}</strong> 从“${c.esc(label)}”中移除。他的账号和其他身份不变。</p>`+(left?'':c.note('移除后这个职责就没有人了：'+(DUTY_INFO[code]?.stuck||'相关申请会停在这一步。'),true))+c.reasonFields('','移除原因'),async v=>{
  await saveDuty(c,code,ids=>ids.delete(userId),v.reason,v.basis||'');c.closeModal();c.toast('已移除');await c.render();
 },{submit:'确认移除'});
}

export async function dutiesAction(action,id,c){
 if(!state)state=await c.api('/social/duties');
 if(action==='duty-add')return addForm(id,c);
 if(action==='duty-remove')return removeForm(id,c);
}
