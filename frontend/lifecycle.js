// 2026-11-07 立项（申报）通过以后的运行过程：档案视图、记一笔、申请变更、年度确认、停用与恢复。
// 菜单不变（培训项目 / 培训课程 / 培训基地 / 培训师资）；入口是详情里的三个主按钮。名称按验收人定的：项目立项、项目运行、项目结项。
import {materialUploadForm} from './approval-flow.js?v=20261021-form-merged1';
import {quickApply} from './apply-quick.js?v=20261109-life2';

const TYPE_LABEL={project:'培训项目',course:'培训课程',base:'培训基地',trainer:'培训师资'};
// 三个主按钮：[动作, 名称, 小字]
const ACTS={
 project:[['info','项目立项','立项信息 · 申请变更'],['note','项目运行','传材料、记过程'],['close','项目结项','结项核算']],
 course:[['info','课程申报','申报信息 · 申请变更'],['note','课程运行','开课、加课时记一笔'],['stop','课程停用','不再开设时停用']],
 base:[['info','基地申报','申报信息 · 申请变更'],['note','基地运行','使用、检查记一笔'],['annual','年度确认','今年是否还在运行']],
 trainer:[['info','师资申报','认定信息 · 申请变更'],['note','师资运行','授课、培训记一笔'],['annual','年度确认','今年是否还在授课']]
};
const STEPS={project:['项目立项','学院审批','学校备案','项目运行','项目结项'],course:['课程申报','审批入库','课程运行','停用'],base:['基地申报','审批生效','基地运行','年度确认'],trainer:['师资申报','认定备案','师资运行','年度确认']};
const SOURCE={self:'本人',college:'学院',school:'学校',auto:'系统自动'};
const split=id=>{const [type,...rest]=String(id).split('|');return [type,rest.join('|')]};
let current=null;

export function lifeEntry(c,type,id,label='查看运行档案',kind='primary'){return c.act(label,'life-open',type+'|'+id,kind)}

function stepIndex(d){
 const s=d.state;
 if(d.type==='project')return s==='CLOSED'?5:['CLOSE_COLLEGE','CLOSE_REVIEW'].includes(s)?4:s==='FILED'?3:s==='SUBMITTED'?2:s==='COLLEGE'?1:0;
 if(s==='STOPPED')return d.type==='course'?3:3;
 return d.running?2:['COLLEGE','SCHOOL','HR','JWC','DEPT'].includes(s)?1:0;
}

// 2026-11-09 按设计稿改成整页：列表里的“X运行”卡片 → 点开是整页档案（不是弹窗）。
const RUN_TAB={project:'项目运行',course:'课程运行',base:'基地运行',trainer:'师资运行'};
const PAGES={project:['apply_project','projects'],course:['apply_course','courses'],base:['apply_base','bases'],trainer:['apply_trainer','trainers']};
const BOARD_SUB={project:'正在运行的项目：开了几期、多少人、改过什么，点开一眼看清；记一笔、申请变更、结项都在项目里办。',
 course:'已入库的课程：被哪些项目用过、学时改过没有；变更和停用在课程里办。',base:'已认定的基地：使用情况自动汇总，每年确认一次是否还在用。',trainer:'已入库的培训师：授课记录自动汇总，每年确认一次是否继续授课。'};
const END_ACT={project:['close','项目结项'],course:['stop','课程停用'],base:['annual','年度确认'],trainer:['annual','年度确认']};
export const lifePageType=page=>Object.keys(PAGES).find(t=>PAGES[t].includes(page))||'';
function targetPage(c,type){
 const now=c.currentPage?.();
 if(PAGES[type].includes(now))return now;
 return c.me?.role?.kind==='teacher'?PAGES[type][0]:PAGES[type][1];
}
function go(c,type,id){
 const hash='#'+targetPage(c,type)+'?life='+encodeURIComponent(type+'|'+id);
 c.closeModal?.();
 if(typeof location==='undefined')return;
 if(location.hash===hash)return c.render?.();
 location.hash=hash;
}
const refresh=async c=>{c.closeModal?.();await c.render?.()};
function remindAct(c,d,text){
 const id=d.type+'|'+d.id;
 if(/项目结项/.test(text)&&d.can.close)return ['life-close',id];
 if(/参训明细/.test(text)&&d.running&&c.can?.('records.write'))return ['life-units',d.id];
 if(/上报信息/.test(text)&&d.running)return ['life-report',d.id];
 if(/年度/.test(text)&&d.can.annual)return ['life-annual',id];
 if(/申请变更/.test(text)&&d.can.change)return ['life-change',id];
 if(/恢复运行/.test(text)&&d.can.resume)return ['life-resume',id];
 return null;
}

function archiveHtml(c,d,page=''){
 const e=c.esc,id=d.type+'|'+d.id,steps=STEPS[d.type],now=stepIndex(d),ended=['CLOSED'].includes(d.state);
 const stepper=`<ol class="life-stepper" aria-label="办理进度">${steps.map((l,i)=>`<li class="${i<now||ended?'on':i===now?'now':''}">${e(l)}</li>`).join('')}</ol>`;
 const remind=(d.reminders||[]).map((x,i)=>{const a=remindAct(c,d,x);return `<div class="life-remind" role="status"><span>⚠ ${e(x)}</span>${a?`<button type="button" class="btn sm" data-action="${a[0]}" data-id="${e(a[1])}">现在处理</button>`:''}</div>`}).join('');
 const pending=d.pending_change?`<div class="life-pending" role="status"><span><strong>有一份变更在审批：</strong>${e(d.pending_change.summary)}（${e(d.pending_change.state_label)}，${e(d.pending_change.level_label||'')}）。审批期间仍按原内容运行，培训明细照常登记。</span>${c.act('查看变更','life-change-view',d.pending_change.id,'text')}</div>`:'';
 const [endKey,endLabel]=END_ACT[d.type],stopped=d.state==='STOPPED';
 const endOn=endKey==='close'?d.can.close:endKey==='annual'?d.can.annual:(d.can.stop||d.can.resume);
 const endBtn=stopped&&d.can.resume?`<button type="button" class="btn primary" data-action="life-resume" data-id="${e(id)}">恢复运行</button>`
  :`<button type="button" class="btn" data-action="life-${endKey}" data-id="${e(id)}"${endOn?'':' disabled'}${endOn?'':` title="${e(endKey==='close'&&['CLOSE_COLLEGE','CLOSE_REVIEW','CLOSED'].includes(d.state)?'已提交结项':!d.running?(stopped?'已停用':'通过后才能办理'):'你没有办理权限')}"`}>${e(endLabel)}</button>`;
 const main=`<button type="button" class="btn primary life-main" data-action="life-note" data-id="${e(id)}"${d.can.note?'':' disabled'}>📷 记一笔</button>`
  +`<button type="button" class="btn" data-action="life-change" data-id="${e(id)}"${d.can.change?'':' disabled'}${d.pending_change?' title="已有一份变更在审批，办完或撤回后再提"':''}>✎ 申请变更</button>`+endBtn;
 const minor=[c.act(ACTS[d.type][0][1]+'信息','life-info',id,'text'),
  d.can.upload?c.act('上传材料','life-upload',id,'text'):'',
  d.type==='project'&&d.running&&c.can?.('records.write')?c.act('导入参训明细','life-units',d.id,'text'):'',
  d.type==='project'&&d.running&&(d.reminders||[]).some(x=>x.includes('上报信息'))?c.act('补填上报信息','life-report',d.id,'text'):'',
  d.can.stop&&d.type!=='course'?c.act('停用','life-stop',id,'text'):'',
  d.can.resume&&d.type!=='course'&&!stopped?c.act('恢复运行','life-resume',id,'text'):''].filter(Boolean).join('');
 const tl=(d.timeline||[]).length?`<ol class="life-timeline">${d.timeline.map(t=>`<li class="k-${e(t.kind)}"><div class="t">${e(String(t.on||t.at||'').slice(0,10))}<span class="src ${t.source==='auto'?'auto':''}">${e(SOURCE[t.source]||'')}</span>${t.who&&t.source!=='auto'?`<span class="who">${e(t.who)}</span>`:''}</div><div class="w">${e(t.what)}</div>${t.reason&&t.reason!==t.what&&t.kind!=='auto'?`<div class="r">${e(t.reason)}</div>`:''}</li>`).join('')}</ol>`:'<p class="muted small">还没有记录。</p>';
 const stats=`<div class="life-stats">${(d.stats||[]).map(([k,v])=>`<div><b>${e(v)}</b><small>${e(k)}</small></div>`).join('')}</div><p class="life-hint">${d.type==='project'?'从培训明细、办理记录自动汇总，不用填。':'使用次数、人次从培训明细自动汇总，不用填。'}</p>`;
 const versions=(d.versions||[]).length?`<ul class="life-versions">${d.versions.map(v=>`<li><span class="v">v${e(v.v)}</span>${e(v.summary||'')}<small>${e(String(v.at||'').slice(0,10))} · ${e(v.who||'')}${v.how?' · '+e(v.how):''}</small></li>`).join('')}</ul>`:'<p class="muted small">通过后生成第 1 版。</p>';
 const sumTitle={project:'运行汇总',course:'使用汇总',base:'运行汇总',trainer:'授课汇总'}[d.type];
 const crumb=`<nav class="life-crumb" aria-label="位置">培训业务 / ${e(TYPE_LABEL[d.type])} / ${e(RUN_TAB[d.type])} / ${e(d.name)}</nav>`;
 const back=page?`<button type="button" class="life-back" data-action="nav" data-id="${e(page)}">‹ 返回${e(TYPE_LABEL[d.type])}</button>`:'';
 return `<div class="life-archive life-page">${crumb}${back}<section class="life-head"><div class="life-title"><h2>${e(d.name)}</h2><span class="tw-status ${d.running?'is-ok':stopped?'is-wait':''}">${e(d.pending_change?'变更审批中':d.state_label)}</span><span class="life-ver">当前第 ${e(d.biz_version)} 版</span></div>
<dl class="life-facts">${(d.facts||[]).map(([k,v])=>`<div><dt>${e(k)}：</dt><dd>${e(v)}</dd></div>`).join('')}</dl>${stepper}${remind}${pending}${ended?'':`<div class="life-actions">${main}</div>`}${minor?`<div class="life-minor">${minor}</div>`:''}</section>
<div class="life-two"><section class="life-panel"><h3>运行过程</h3>${tl}</section><aside><section class="life-panel"><h3>${e(sumTitle)}</h3>${stats}</section><section class="life-panel"><h3>历次版本</h3>${versions}</section></aside></div></div>`;
}

export async function lifePageHtml(c,page,life){
 const [type,id]=split(life);
 if(!PAGES[type]||!PAGES[type].includes(page))throw Error('运行档案地址不正确，请从列表重新打开。');
 const d=await c.api('/social/lifecycle/'+type+'/'+encodeURIComponent(id));current=d;
 return archiveHtml(c,d,page);
}

function cardHtml(c,x){
 const e=c.esc,pill=x.pending?'is-wait':x.running?'is-ok':x.state==='STOPPED'?'is-stop':'';
 const alert=x.remind?`<div class="life-card-alert">${e(x.remind.split(/[（。]/)[0])}</div>`:x.pending?`<div class="life-card-alert is-blue">${e(x.pending)}</div>`:'';
 return `<button type="button" class="life-card" data-action="life-open" data-id="${e(x.type+'|'+x.id)}"><span class="life-card-top"><strong>${e(x.name)}</strong><span class="tw-status ${pill}">${e(x.state_label)}</span></span>${x.sub?`<span class="life-card-meta">${e(x.sub)}</span>`:''}<span class="life-card-nums">${(x.stats||[]).map(([k,v])=>`<span><b>${e(v)}</b>${e(k)}</span>`).join('')}</span>${alert}</button>`;
}
function changesHtml(c,list){
 const e=c.esc;
 return `<section class="life-panel life-board-changes"><h3>待我审批的变更 <span class="life-count">${list.length}</span></h3>${list.map(x=>`<div class="life-chg-review"><div><strong>${e(x.name)}</strong> <span class="life-card-meta">${e(x.who)} · ${e(x.on)} 提交 · ${e(x.level_label)}${x.reason?' · 原因：'+e(x.reason):''}</span></div>
<table class="life-cmp"><thead><tr><th>变更项</th><th>现在</th><th>改成</th></tr></thead><tbody>${(x.rows||[]).map(r=>`<tr><td>${e(r.label)}</td><td>${e(r.from_text)}</td><td class="life-new">${e(r.to_text)}</td></tr>`).join('')}</tbody></table>
<div class="life-chg-btns">${c.act('同意','life-change-act','approve|'+x.id,'primary')}${c.act('退回','life-change-act','return|'+x.id,'')}${c.act('查看详情','life-change-view',x.id,'text')}<span class="life-hint">只看改动的这几项；同意后自动生成新版本，旧版本随时可查。</span></div></div>`).join('')}</section>`;
}
// 列表页上方的“X运行”卡片：老师在“我的申报”页看到本人负责的，学院、学校在业务列表页看到本院的，加上待我审批的变更。
export async function lifeBoardHtml(c,page){
 const type=lifePageType(page),teacher=c.me?.role?.kind==='teacher';
 if(!type||(teacher?page!==PAGES[type][0]:page!==PAGES[type][1]))return '';
 let b;try{b=await c.api('/social/lifecycle/board/'+type)}catch{return ''}
 if(!b.cards?.length&&!b.changes?.length)return '';
 const more=b.total>b.cards.length?`<p class="life-hint">还有 ${b.total-b.cards.length} 个，在下方列表里查找。</p>`:'';
 return `<div class="life-board">${b.changes?.length?changesHtml(c,b.changes):''}${b.cards?.length?`<section class="life-board-run"><div class="life-board-head"><h2>${e2(c,RUN_TAB[type])} <span class="life-count">${b.total}</span></h2><p>${e2(c,BOARD_SUB[type])}</p></div><div class="life-cards">${b.cards.map(x=>cardHtml(c,x)).join('')}</div>${more}</section>`:''}</div>`;
}
const e2=(c,v)=>c.esc(v);
// 卡片放在页面标题和页签下面（和页签的摆放方式一样，渲染后再挪位置）。
export function placeLifeBoard(root){
 const board=root?.querySelector?.('.life-board');if(!board)return;
 const anchor=root.querySelector('.page-group-tabs')||root.querySelector('.pagehead');
 if(anchor&&anchor.parentNode)anchor.parentNode.insertBefore(board,anchor.nextSibling);
}

async function openArchive(c,type,id){return go(c,type,id)}

async function openInfo(c,d){
 // 立项（申报）信息就是原来的详情；项目在那里也能“申请变更”。
 if(d.type==='project')return c.runAction('social-detail','social_project|'+d.id);
 if(d.application)return c.runAction('app-detail',d.id);
 if(d.type==='course'&&d.course_code)return c.runAction('social-course-view',d.course_code);
 return c.runAction('social-detail','social_resource|'+d.id);
}

function noteForm(c,d){
 const tags=Object.entries(d.note_tags||{}).filter(([k])=>d.type==='project'?k!=='use':k!=='start');
 const quick={project:['今天开班，到训 人','增加一次实训课','学院来检查，提出整改意见','学员反馈良好'],course:['本期开课 次','增加 学时实操','更新了课件'],base:['本月接待培训 期','完成安全检查','设备更新'],trainer:['本期主讲 学时','参加师资培训','学员评价良好']}[d.type];
 const body=c.field('tag','记什么','select',tags[0]?.[0]||'other',{chips:true,options:tags})
  +c.field('text','发生了什么（一两句话就行）','textarea','',{full:true,rows:3,textLimit:1000,placeholder:'例：'+quick[0]})
  +`<div class="form-field full life-quick">${quick.map(q=>`<button type="button" class="btn sm light" data-fill="${c.esc(q)}">${c.esc(q)}</button>`).join('')}</div>`
  +c.field('happened_on','发生日期（不填就是今天）','date','',{required:false});
 c.formModal(ACTS[d.type][1][1]+'：记一笔',body,async v=>{
  if(!String(v.text||'').trim())throw Error('请写一句发生了什么');
  await c.api('/social/lifecycle/'+d.type+'/'+d.id+'/notes',{method:'POST',body:{tag:v.tag,text:v.text.trim(),happened_on:v.happened_on||null}});
  c.toast('已记下');await refresh(c);
 },{submit:'记下来',stepper:false,contextLabel:TYPE_LABEL[d.type]+' / 运行记录',hint:'只记录，不审批。材料（照片、签到表）请回到档案点“上传材料”。'});
 if(typeof document!=='undefined')document.querySelectorAll('#modal-root [data-fill]').forEach(b=>b.addEventListener('click',()=>{const t=document.getElementById('f-text');if(t){t.value=b.dataset.fill;t.focus();t.dispatchEvent(new Event('input',{bubbles:true}))}}));
}

function valueText(f,v,c){
 if(v==null||v===''||(Array.isArray(v)&&!v.length))return '（空）';
 if(f.type==='user'){const t=(c?.teachers||[]).find(x=>x.id===v);return t?t.name+(t.staff_no?'（'+t.staff_no+'）':''):(v===c?.me?.user?.id?c.me.user.name:String(v))}
 if(f.type==='venue')return ({base:'校内基地',campus:'其他校内场所',offsite:'校外（一事一议）'}[v.type]||'')+'：'+(v.place||'');
 if(f.type==='multi')return v.map(x=>f.options?.[x]||x).join('、');
 if(f.type==='choice')return f.options?.[v]||v;
 return String(v);
}
function inputFor(c,f){
 const e=c.esc,n='v-'+f.key,v=f.value;
 if(f.type==='textarea')return `<textarea id="${n}" name="${n}" rows="2" maxlength="2000">${e(v||'')}</textarea>`;
 if(f.type==='number'||f.type==='money')return `<input id="${n}" name="${n}" type="number" min="0" step="${f.type==='money'?'0.01':f.key==='expected_participants'?'1':'0.5'}" value="${e(v??'')}">`;
 if(f.type==='date')return `<input id="${n}" name="${n}" type="date" value="${e(v||'')}">`;
 if(f.type==='choice')return `<select id="${n}" name="${n}">${Object.entries(f.options||{}).map(([k,l])=>`<option value="${e(k)}"${k===v?' selected':''}>${e(l)}</option>`).join('')}</select>`;
 if(f.type==='multi')return `<div class="choice-row">${Object.entries(f.options||{}).map(([k,l])=>`<label class="choice"><input type="checkbox" data-multi="${e(f.key)}" value="${e(k)}"${(v||[]).includes(k)?' checked':''}><span>${e(l)}</span></label>`).join('')}</div>`;
 if(f.type==='user')return `<select id="${n}" name="${n}">${(c.teachers||[]).map(t=>`<option value="${e(t.id)}"${t.id===v?' selected':''}>${e(t.name+(t.staff_no?'（'+t.staff_no+'）':''))}</option>`).join('')}</select>`;
 if(f.type==='venue'){const g=v||{};return `<div class="life-venue"><select name="${n}-type">${[['base','校内基地'],['campus','其他校内场所'],['offsite','校外（一事一议）']].map(([k,l])=>`<option value="${k}"${g.type===k?' selected':''}>${l}</option>`).join('')}</select><input name="${n}-place" maxlength="200" placeholder="具体地点" value="${e(g.place||'')}"><input name="${n}-reason" maxlength="1000" placeholder="校外：外出理由" value="${e(g.offsite_reason||'')}"><input name="${n}-ref" maxlength="200" placeholder="校外：议定文号或会议日期" value="${e(g.offsite_ref||'')}"></div>`}
 return `<input id="${n}" name="${n}" maxlength="500" value="${e(v||'')}">`;
}
function readValue(f,form){
 const q=s=>form.querySelector(s),n='v-'+f.key;
 if(f.type==='multi')return [...form.querySelectorAll(`[data-multi="${f.key}"]:checked`)].map(x=>x.value);
 if(f.type==='venue')return {type:q(`[name="${n}-type"]`).value,place:q(`[name="${n}-place"]`).value.trim(),offsite_reason:q(`[name="${n}-reason"]`).value.trim(),offsite_ref:q(`[name="${n}-ref"]`).value.trim()};
 const raw=q(`[name="${n}"]`)?.value??'';
 return f.type==='number'||f.type==='money'?(raw===''?null:raw):raw;
}
const LEVEL_HINT={project:'人次、收入变动不超过 30% 直接生效；换负责人、改类别、延期超过三个月、改到校外、人次或收入变动超过 30% 要学院审批后学校备案；其他学院审批。',
 course:'学时变动超过一半要学院审批后学校备案；面向对象、简介直接更新；其他学院审批。',base:'地点、级别要学院审批后学校备案；负责人直接更新；其他学院审批。',trainer:'业务类别要重新认定（校内：学院审批后组织人事部认定；外聘：教务处备案）；职称、单位、特长直接更新。'};
const REASONS={project:['学员人数增加','学员时间调整','场地调整','负责人工作变动'],course:['内容增加','学员要求','主讲老师调整'],base:['场地调整','合作变化','负责人变动'],trainer:['职称晋升','单位变动','业务方向调整']};
function changeForm(c,d){
 const e=c.esc;
 const rows=d.fields.map(f=>`<div class="life-chg" data-key="${e(f.key)}"><label class="life-chg-top"><input type="checkbox" name="pick-${e(f.key)}"><strong>${e(f.label)}</strong><span class="cur">现在：${e(valueText(f,f.value,c))}</span></label><div class="life-chg-new" hidden><span class="muted small">改为</span>${inputFor(c,f)}</div></div>`).join('');
 c.formModal('申请变更',`<div class="form-field full">${`<p class="life-chg-intro">先勾选要改哪几项，勾上的才填新内容；没勾的保持不变。审批期间按原内容照常运行，通过后生成新版本，旧版本随时可查。</p>`}${rows}<p class="hint">${e(LEVEL_HINT[d.type])}</p></div>`+c.field('reason','为什么改（一句话即可，审批人会看到）','textarea','',{full:true,rows:2,textLimit:2000})+`<div class="form-field full life-quick">${(REASONS[d.type]||[]).map(q=>`<button type="button" class="btn sm light" data-reason="${e(q)}">${e(q)}</button>`).join('')}</div>`,async(v,form)=>{
  const values={};
  for(const f of d.fields)if(form.querySelector(`[name="pick-${f.key}"]`)?.checked)values[f.key]=readValue(f,form);
  if(!Object.keys(values).length)throw Error('请至少勾选一项要改的内容');
  const r=await c.api('/social/lifecycle/'+d.type+'/'+d.id+'/changes',{method:'POST',body:{values,reason:v.reason}});
  c.toast(r.applied?'已更新，档案升到第 '+r.archive.biz_version+' 版':'已提交：'+({college:'学院审批',school:'学院审批 → 学校备案',hr:'学院审批 → 组织人事部认定',jwc:'教务处备案审核'}[r.level]||'审批')+'。审批期间照常运行。');
  await refresh(c);
 },{submit:'提交变更',stepper:false,wide:true,contextLabel:TYPE_LABEL[d.type]+' / 申请变更'});
 if(typeof document!=='undefined'){document.querySelectorAll('#modal-root .life-chg').forEach(box=>{const cb=box.querySelector('[name^="pick-"]'),nv=box.querySelector('.life-chg-new');cb?.addEventListener('change',()=>{if(nv){nv.hidden=!cb.checked;if(cb.checked)nv.querySelector('input,select,textarea')?.focus()}})});
  document.querySelectorAll('#modal-root [data-reason]').forEach(b=>b.addEventListener('click',()=>{const t=document.getElementById('f-reason');if(t){t.value=b.dataset.reason;t.dispatchEvent(new Event('input',{bubbles:true}))}}))}
}

function annualForm(c,d){
 const y=new Date().getFullYear(),years=(d.annual_years&&d.annual_years.length?d.annual_years:[y,y-1]).map(String),done=d.annual||{};
 const word=v=>v.running?'在运行':'暂未运行',first=years[0],prior=done[first];
 const doneNote=years.filter(k=>done[k]).map(k=>k+' 年度已确认为“'+word(done[k])+'”').join('；');
 c.formModal('年度运行确认',c.field('year','确认年度','select',first,{chips:true,options:years.map(k=>[k,k+' 年度'+(done[k]?'（已确认，再确认即更正）':'')])})
  +c.field('running','今年的情况','select',prior&&!prior.running?'no':'yes',{chips:true,options:[['yes',d.type==='base'?'在运行，有培训在用':'在授课，资格继续有效'],['no','今年暂未运行']]})
  +c.field('text','补充一句（选填）','textarea','',{full:true,required:false,rows:2,textLimit:1000,placeholder:d.type==='base'?'例：今年接待 3 期培训，共 120 人次':'例：今年主讲 2 个项目，共 32 学时'}),async v=>{
  await c.api('/social/lifecycle/'+d.type+'/'+d.id+'/annual',{method:'POST',body:{year:Number(v.year),running:v.running!=='no',text:v.text||''}});
  c.toast('已确认');await refresh(c);
 },{submit:'确认',stepper:false,contextLabel:TYPE_LABEL[d.type]+' / 年度确认',hint:(doneNote?doneNote+'。同一年度再确认会记为更正，前后结论都留在运行过程里。':'每年一次，点选即可，不用审批。')+'今年不再运行的，可以回到档案点“停用”。'});
}

function stopForm(c,d,resume=false){
 c.formModal(resume?'恢复运行':'停用'+TYPE_LABEL[d.type],c.field('reason',resume?'恢复原因':'停用原因','textarea','',{full:true,rows:2,textLimit:2000,placeholder:resume?'例：本学期重新开设':'例：课程不再开设 / 协议到期 / 本人调离'}),async v=>{
  await c.api('/social/lifecycle/'+d.type+'/'+d.id+'/'+(resume?'resume':'stop'),{method:'POST',body:{reason:v.reason,expected_version:d.version}});
  c.toast(resume?'已恢复运行':'已停用，历史记录都保留');await refresh(c);
 },{submit:resume?'恢复运行':'确认停用',stepper:false,hint:resume?'':'停用不是作废：以前的记录、明细和积分都不动；停用后不能再登记新的使用'+(d.type==='course'?'（导入参训明细会拦下这门课）':'')+'，需要时可以恢复。'});
}

async function changeView(c,id){
 const d=await c.api('/social/lifecycle/changes/'+encodeURIComponent(id)),x=d.item,e=c.esc;
 const table=c.table(['变更项','现在','改为'],(x.data.rows||[]).map(r=>[e(r.label),e(r.from_text),`<strong class="life-new">${e(r.to_text)}</strong>`]));
 const body=`<div class="life-archive">${c.note(e(d.target.name)+' · 现行第 '+d.target.version+' 版 · '+e(d.level_label)+' · '+e(d.state_label))}${table}<p><strong>申请理由：</strong>${e(x.data.reason||'')}</p><p class="muted small">${e(d.progress?.headline||d.progress?.text||'')}</p><details class="detail-fold"><summary>办理记录</summary>${c.eventsHtml?c.eventsHtml(d.events):''}</details></div>`;
 const foot=[c.act('打开档案','life-open',d.target.type+'|'+d.target.id),d.can.withdraw?c.act('撤回变更','life-change-act','withdraw|'+id,'danger'):'',d.can.return?c.act('退回','life-change-act','return|'+id,'danger'):'',d.can.approve?c.act('同意变更','life-change-act','approve|'+id,'primary'):'',c.act('关闭','close')].join('');
 current={change:d};
 return c.modal('变更申请：'+d.target.name,body,foot,true,TYPE_LABEL[d.target.type]+' / 变更审批');
}

async function changeActForm(c,op,id){
 // 从变更详情或列表上方的“待我审批的变更”都能直接同意、退回。
 const d=current?.change?.item?.id===id?current.change:await c.api('/social/lifecycle/changes/'+encodeURIComponent(id));
 current={change:d};
 const level=d?.item?.state,needBasis=op==='approve'&&['HR','JWC'].includes(level);
 const label={approve:'同意变更',return:'退回变更',withdraw:'撤回变更'}[op];
 c.formModal(label,c.field('reason',op==='approve'?'办理意见':op==='return'?'退回原因（告诉对方要补什么）':'撤回原因','textarea',op==='approve'?'同意变更':'',{full:true,rows:2,textLimit:2000})+(needBasis?c.field('basis',level==='HR'?'资格认定文号和日期':'备案依据','text','',{full:true}):''),async v=>{
  await c.api('/social/lifecycle/changes/'+id+'/actions',{method:'POST',body:{action:op,reason:v.reason,basis:v.basis||'',expected_version:d.item.version}});
  c.toast(op==='approve'?'已办理':'已'+label.slice(0,2));await refresh(c);
 },{submit:label,stepper:false,contextLabel:TYPE_LABEL[d.target?.type]?TYPE_LABEL[d.target.type]+' / 变更审批':''});
}

export async function lifecycleAction(action,id,c){
 if(action==='quick-apply')return quickApply(c,id);
 if(action==='life-open'){const [t,i]=split(id);return openArchive(c,t,i)}
 if(action==='life-change-view')return changeView(c,id);
 if(action==='life-change-act'){const [op,i]=split(id);return changeActForm(c,op,i)}
 if(action==='life-units'||action==='life-report'){
  // 导入明细、补填上报信息沿用原来的办理窗口（它们从项目详情里取当前项目）。
  await c.runAction('social-detail','social_project|'+id);
  return c.runAction(action==='life-units'?'social-unit-import':'social-report-info','');
 }
 const [type,ident]=split(id);
 const d=current&&current.id===ident&&current.type===type?current:await c.api('/social/lifecycle/'+type+'/'+encodeURIComponent(ident));current=d;
 if(action==='life-info')return openInfo(c,d);
 if(action==='life-note')return noteForm(c,d);
 if(action==='life-change')return changeForm(c,d);
 if(action==='life-annual')return annualForm(c,d);
 if(action==='life-stop')return stopForm(c,d);
 if(action==='life-resume')return stopForm(c,d,true);
 if(action==='life-close'){await c.runAction('social-detail','social_project|'+ident);return c.runAction('social-close','')}
 if(action==='life-upload'){
  const kind=type==='project'?'social_project':'social_resource';
  const latest=async()=>{const x=await c.api('/social/objects/'+kind+'/'+ident);return {version:x.item.version,attachments:x.attachments||[]}};
  return materialUploadForm(c,{kind,id:ident,title:'上传运行材料',intro:c.note('签到表、开班照片、检查记录、协议都可以；上传后自动记进运行过程。'),contextLabel:TYPE_LABEL[type]+' / 上传材料',latest,after:()=>refresh(c)});
 }
 throw Error('此操作入口暂不可用');
}
export const LIFE_ACTIONS=['life-open','life-info','life-note','life-change','life-annual','life-stop','life-resume','life-close','life-upload','life-units','life-report','life-change-view','life-change-act','quick-apply'];
