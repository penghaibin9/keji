// 2026-11-07 立项（申报）通过以后的运行过程：档案视图、申请变更、年度确认、停用与恢复。
// 2026-11-09 按设计图 v2：老师“我的X”三步列表、详情只留三个按钮、上传自动分组、结项查缺、学院学校“待我审批”。
// 菜单不变（培训项目 / 培训课程 / 培训基地 / 培训师资）；入口是详情里的三个主按钮。名称按验收人定的：项目立项、项目运行、项目结项。
import {quickApply} from './apply-quick.js?v=20261110-doc1';

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
 if(/参训明细/.test(text)&&d.type==='project'&&(d.lead!==false||c.can?.('records.write')))return ['life-units',d.id];
 if(/上报信息/.test(text)&&d.running)return ['life-report',d.id];
 if(/年度/.test(text)&&d.can.annual)return ['life-annual',id];
 if(/申请变更/.test(text)&&d.can.change)return ['life-change',id];
 if(/恢复运行/.test(text)&&d.can.resume)return ['life-resume',id];
 return null;
}

// 6 个状态：草稿、审批中、运行中、变更中、结项中（停用中）、已结项（已停用）。
export function status6(d){
 const s=d.state,proj=d.type==='project';
 if(['DRAFT','RETURNED','WITHDRAWN'].includes(s)&&!(d.type==='base'&&d.running))return ['draft','草稿'];
 if(['COLLEGE','SUBMITTED','DEPT','SCHOOL','HR','JWC'].includes(s))return ['review','审批中'];
 if(['CLOSE_COLLEGE','CLOSE_REVIEW'].includes(s))return ['closing','结项中'];
 if(s==='CLOSED')return ['done','已结项'];
 if(s==='STOPPED')return ['done',proj?'已结项':'已停用'];
 return d.pending_change?['change','变更中']:['run','运行中'];
}
// 同时只给一条最急的：没明细 > 上报信息 > 已结束去结项 > 年度确认 > 快到期；没有提醒时显示在审变更。
const URGENT=[/参训明细/,/上报信息/,/项目结项/,/年度/,/天培训结束/];
function topRemind(list){for(const re of URGENT){const x=(list||[]).find(t=>re.test(t));if(x)return x}return (list||[])[0]||''}
function archiveHtml(c,d,page=''){
 const e=c.esc,id=d.type+'|'+d.id,steps=STEPS[d.type],now=stepIndex(d),ended=['CLOSED'].includes(d.state),[code,label]=status6(d);
 const stepper=`<ol class="life-stepper" aria-label="办理进度">${steps.map((l,i)=>`<li class="${i<now||ended?'on':i===now?'now':''}">${e(l)}</li>`).join('')}</ol>`;
 const top=topRemind(d.reminders),act=top?remindAct(c,d,top):null;
 const remind=top?`<div class="life-remind" role="status"><span>⚠ ${e(top.split(/（/)[0].replace(/。$/,''))}</span>${act?`<button type="button" class="btn sm" data-action="${act[0]}" data-id="${e(act[1])}">现在处理</button>`:''}</div>`
  :d.pending_change?`<div class="life-pending" role="status"><span>变更待审批：${e(d.pending_change.summary)}（${e(d.pending_change.state_label)}）</span>${c.act('查看','life-change-view',d.pending_change.id,'text')}</div>`:'';
 const stopped=d.state==='STOPPED',lead=d.lead!==false;
 const btn=(action,text,on,primary)=>`<button type="button" class="btn${primary?' primary':''}" data-action="${action}" data-id="${e(id)}"${on?'':' disabled'}>${e(text)}</button>`;
 const end=d.type==='project'?btn('life-close','结项',d.can.close):d.type==='course'?(stopped?btn('life-resume','恢复运行',d.can.resume,true):btn('life-stop','停用',d.can.stop)):(stopped?btn('life-resume','恢复运行',d.can.resume,true):btn('life-annual','年度确认',d.can.annual));
 // 2026-11-10 参训明细由项目负责人上传一张 Excel（结项前后都能传，再传覆盖）。
 const sheet=d.type==='project'&&lead&&['FILED','CLOSE_COLLEGE','CLOSE_REVIEW'].includes(d.state)?`<button type="button" class="btn" data-action="life-units" data-id="${e(d.id)}">上传参训明细表</button>`:'';
 const main=(d.can.upload?btn('life-upload','上传材料',true,true):'')+sheet+(lead?btn('life-change','申请变更',d.can.change)+end:'');
 const minor=lead&&c.me?.role?.kind!=='teacher'&&d.type==='project'&&d.running&&c.can?.('records.write')?`<div class="life-minor">${c.act('导入参训明细','life-units',d.id,'text')}</div>`:'';
 const tl=(d.timeline||[]).length?`<ol class="life-timeline">${d.timeline.map(t=>`<li class="k-${e(t.kind)}"><div class="t">${e(String(t.on||t.at||'').slice(0,10))}<span class="src ${t.source==='auto'?'auto':''}">${e(SOURCE[t.source]||'')}</span>${t.who&&t.source!=='auto'?`<span class="who">${e(t.who)}</span>`:''}</div><div class="w">${e(t.what)}</div>${t.reason&&t.reason!==t.what&&t.kind!=='auto'?`<div class="r">${e(t.reason)}</div>`:''}</li>`).join('')}</ol>`:'';
 const pts=d.points?[[d.points.label,d.points.value]]:[];
 const stats=`<div class="life-stats">${[...(d.stats||[]),...pts].map(([k,v])=>`<div class="${/积分/.test(k)?'is-pt':''}"><b>${e(v)}</b><small>${e(k)}</small></div>`).join('')}</div>${d.points?.line?`<p class="lv-points">${e(d.points.label==='已记积分'?'已记积分：':'将记积分：')+e(d.points.line)}</p>`:''}`;
 const versions=(d.versions||[]).length?`<section class="life-panel"><h3>历次版本</h3><ul class="life-versions">${d.versions.map(v=>`<li><span class="v">v${e(v.v)}</span>${e(v.summary||'')}<small>${e(String(v.at||'').slice(0,10))} · ${e(v.who||'')}</small></li>`).join('')}</ul></section>`:'';
 const sumTitle={project:'运行汇总',course:'使用汇总',base:'运行汇总',trainer:'授课汇总'}[d.type];
 const crumb=`<nav class="life-crumb" aria-label="位置">培训业务 / ${e(TYPE_LABEL[d.type])} / ${e(d.name)}</nav>`;
 const back=page?`<button type="button" class="life-back" data-action="nav" data-id="${e(page)}">‹ 返回</button>`:'';
 return `<div class="life-archive life-page">${crumb}${back}<section class="life-head"><div class="life-title"><h2>${e(d.name)}</h2><span class="lv-pill lv-${code}">${e(label)}</span><span class="life-ver">第 ${e(d.biz_version)} 版</span></div>
<dl class="life-facts">${(d.facts||[]).map(([k,v])=>`<div><dt>${e(k)}：</dt><dd>${e(v)}</dd></div>`).join('')}</dl>${stepper}${remind}${ended||!main?'':`<div class="life-actions">${main}</div>`}${minor}</section>
<div class="life-two"><section class="life-panel"><h3>运行过程</h3>${tl}</section><aside><section class="life-panel"><h3>${e(sumTitle)}</h3>${stats}</section>${versions}</aside></div></div>`;
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
 if(!type||teacher||page!==PAGES[type][1])return '';
 const html=await lifeQueueHtml(c,type);
 return html?`<div class="life-board">${html}</div>`:'';
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
 c.formModal('申请变更',`<div class="form-field full">${rows}</div>`+c.field('reason','变更原因','textarea','',{full:true,rows:2,textLimit:2000})+`<div class="form-field full life-quick">${(REASONS[d.type]||[]).map(q=>`<button type="button" class="btn sm light" data-reason="${e(q)}">${e(q)}</button>`).join('')}</div>`,async(v,form)=>{
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
 },{submit:'确认',stepper:false,contextLabel:TYPE_LABEL[d.type]+' / 年度确认',hint:doneNote});
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
 if(QUEUE_ACTIONS.includes(action))return queueAction(action,id,c);
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
 if(action==='life-close')return closeWithCheck(c,d);
 if(action==='life-upload')return uploadGrouped(c,d,()=>refresh(c));
 throw Error('此操作入口暂不可用');
}

// ---- 2026-11-09 设计图 v2：老师“我的X”三步列表、上传材料自动分组、结项查缺、学院学校“待我审批” ----
const STAGES={project:[['apply','项目立项'],['run','项目运行'],['close','项目结项']],course:[['apply','课程申报'],['run','课程运行'],['close','课程停用']],
 base:[['apply','基地申报'],['run','基地运行'],['close','暂停 / 停用']],trainer:[['apply','师资申报'],['run','授课运行'],['close','暂停 / 退出']]};
const NEW_LABEL={project:'＋ 新建培训项目',course:'＋ 申报培训课程',base:'＋ 申报培训基地',trainer:'＋ 申请成为培训师'};
const view2={tab:{},rf:'all',q:{},sel:new Set()};
export const APPLY_TYPE={apply_project:'project',apply_course:'course',apply_base:'base',apply_trainer:'trainer'};
const pill6=(c,code,label)=>`<span class="lv-pill lv-${c.esc(code)}">${c.esc(label)}</span>`;

function lvCard(c,x){
 const e=c.esc,t=x.todo,open=['run','change','closing','done'].includes(x.status)?['life-open',x.type+'|'+x.id]:x.type==='project'?['social-detail','social_project|'+x.id]:['app-detail',x.id];
 const btn=t&&t.act&&t.tone==='warn'?`<button type="button" class="btn sm primary" data-action="${e(t.act)}" data-id="${e(t.id)}">${e(t.btn)}</button>`:'';
 const again=x.again?`<button type="button" class="btn sm" data-action="lv-again" data-id="${e(x.id)}">再办一期</button>`:'';
 return `<div class="lv-card" role="button" tabindex="0" data-action="${open[0]}" data-id="${e(open[1])}"><div class="lv-top"><strong>${e(x.name)}</strong>${pill6(c,x.status,x.status_label)}</div><div class="lv-meta">${e(x.dates)}</div>${t?`<div class="lv-todo ${t.tone==='info'?'is-info':''}">${e(t.text)}</div>`:''}${btn||again?`<div class="lv-btns">${btn}${again}</div>`:''}</div>`;
}

export async function lifeListHtml(c,page){
 const type=APPLY_TYPE[page];if(!type)return '';
 const e=c.esc;
 let m;try{m=await c.api('/social/lifecycle/mine/'+type)}catch(err){return c.note('读取失败：'+err.message,true)}
 const tab=view2.tab[type]||'run',rf=view2.rf;
 const rows=(m.items||[]).filter(x=>x.stage===tab&&(type!=='project'||rf==='all'||(rf==='lead'?x.lead:!x.lead)));
 const bar=`<div class="lv-stages">${STAGES[type].map(([k,l],i)=>`${i?'<span class="lv-arrow">›</span>':''}<button type="button" class="lv-step${k===tab?' on':''}" data-action="lv-tab" data-id="${type}|${k}">${e(l)}</button>`).join('')}</div>`;
 const seg=type==='project'&&tab!=='apply'?`<div class="lv-seg">${[['all','全部'],['lead','我负责的'],['member','我参与的']].map(([k,l])=>`<button type="button" class="${rf===k?'on':''}" data-action="lv-rf" data-id="${k}">${l}</button>`).join('')}</div>`:'';
 const hasTrainer=type==='trainer'&&(m.items||[]).some(x=>x.status!=='done');
 const extra=type==='course'?`<button type="button" class="lv-card lv-new is-sub" data-action="teacher-apply" data-id="credits|">从我的课程导入</button>`:'';
 const add=tab==='apply'&&!hasTrainer?`<button type="button" class="lv-card lv-new" data-action="quick-apply" data-id="${type}">${e(NEW_LABEL[type])}</button>${extra}`:'';
 return `<div class="lv-page"><div class="lv-bar">${bar}${seg}</div><div class="lv-grid">${rows.map(x=>lvCard(c,x)).join('')}${add}${!rows.length&&!add?'<p class="lv-empty">暂无</p>':''}</div></div>`;
}

// 上传材料：一次拖多个，按文件名自动分组（签到表、照片、课件、其他），不填说明。
const GROUPS=['签到表','照片','课件','其他'];
export const groupOf=name=>/签到|名单|名册|花名册/.test(name)?'签到表':/课件|教案|讲义/.test(name)?'课件':/\.(jpe?g|png|heic|webp)$/i.test(name)?'照片':'其他';
function groupedHtml(c,files){
 const e=c.esc;if(!files.length)return '';
 return `<div class="lv-groups">${GROUPS.map(g=>{const fs=files.filter(f=>groupOf(f.name)===g);return `<div class="lv-group"><div class="lv-ghead"><strong>${g}</strong><span>${fs.length}</span></div>${fs.map(f=>`<div class="lv-file">${e(f.name)}</div>`).join('')||'<div class="lv-file is-empty">—</div>'}</div>`}).join('')}</div>`;
}
async function uploadGrouped(c,d,refresh){
 const kind=d.type==='project'?'social_project':'social_resource',ident=d.id;
 const latest=async()=>{const x=await c.api('/social/objects/'+kind+'/'+ident);return {version:x.item.version,attachments:x.attachments||[]}};
 const {checkUploadFiles,uploadEntries,uploadSequential}=await import('./approval-flow.js?v=20261110-doc1');
 const body=`<label class="lv-drop form-field full" id="lv-drop"><input type="file" id="lv-files" data-plain-file="1" data-assist-control="true" multiple accept=".pdf,.png,.jpg,.jpeg,.docx,.xlsx,.pptx" hidden><strong>拖入文件，或点击选择</strong><span>可一次选多个</span></label><div id="lv-grouped" class="form-field full"></div>`;
 let picked=[];
 c.formModal('上传材料 · '+d.name,body,async()=>{
  if(!picked.length)throw Error('请选择文件');
  const files=checkUploadFiles(picked),fresh=await latest();
  const r=await uploadSequential({api:c.api,kind,id:ident,version:fresh.version,entries:uploadEntries(files),reason:'上传运行材料（'+GROUPS.map(g=>[g,files.filter(f=>groupOf(f.name)===g).length]).filter(x=>x[1]).map(x=>x[0]+' '+x[1]).join('、')+'）',latest});
  if(r.failed?.length)throw Error('有 '+r.failed.length+' 个文件没传上：'+r.failed.map(x=>x.name||x.file?.name||'').join('、'));
  c.closeModal();c.toast('已上传 '+files.length+' 个文件');await refresh();
 },{submit:'保存',stepper:false,wide:true,contextLabel:TYPE_LABEL[d.type]+' / 上传材料'});
 if(typeof document==='undefined')return;
 const drop=document.getElementById('lv-drop'),input=document.getElementById('lv-files'),box=document.getElementById('lv-grouped');
 const add=list=>{picked=[...picked,...Array.from(list||[])];box.innerHTML=groupedHtml(c,picked)};
 input?.addEventListener('change',()=>{add(input.files);input.value=''});
 drop?.addEventListener('dragover',ev=>{ev.preventDefault();drop.classList.add('over')});
 drop?.addEventListener('dragleave',()=>drop.classList.remove('over'));
 drop?.addEventListener('drop',ev=>{ev.preventDefault();drop.classList.remove('over');add(ev.dataTransfer?.files)});
}

// 结项前查缺：缺什么列出来，传齐才进结项表。
async function closeWithCheck(c,d){
 const r=await c.api('/social/lifecycle/close-check/'+encodeURIComponent(d.id));
 if(r.gaps?.length){
  const e=c.esc;
  const report=r.gaps.some(x=>x.includes('上报信息')),files=r.gaps.some(x=>/签到|照片|凭证/.test(x));
  return c.modal('结项 · '+d.name,`<div class="lv-gaps"><strong>还不能结项</strong><ul>${r.gaps.map(x=>`<li>${e(x)}</li>`).join('')}</ul></div>${r.points?`<div class="lv-points">本项目将记积分：${e(r.points)}</div>`:''}`,
   `${report?c.act('补填上报信息','life-report',d.id,'primary'):''}${files&&d.can.upload?c.act('去上传','life-upload',d.type+'|'+d.id,report?'':'primary'):''}${c.act('关闭','close')}`,false,'培训项目 / 结项');
 }
 if(r.notes?.length)c.toast(r.notes.join('；'));
 await c.runAction('social-detail','social_project|'+d.id);return c.runAction('social-close','');
}

// 学院、学校“待我审批”：立项（备案）、变更、结项；可勾选批量同意，退回必须写原因。
const Q_TABS=[['all','全部'],['apply','立项'],['change','变更'],['close','结项']];
async function queueData(c,type){return (await c.api('/social/lifecycle/queue/'+type)).items||[]}
const qid=x=>x.kind+'|'+x.type+'|'+x.id;
export async function lifeQueueHtml(c,type){
 let items;try{items=await queueData(c,type)}catch{return ''}
 view2.items=items;
 const e=c.esc,tab=view2.q[type]||'all',rows=items.filter(x=>tab==='all'||x.kind===tab);
 for(const k of [...view2.sel])if(!items.some(x=>qid(x)===k))view2.sel.delete(k);
 const n=k=>items.filter(x=>k==='all'||x.kind===k).length,sel=rows.filter(x=>view2.sel.has(qid(x)));
 const all=rows.filter(x=>x.batch).length>0&&rows.filter(x=>x.batch).every(x=>view2.sel.has(qid(x)));
 return `<section class="lv-queue"><div class="lv-bar"><div class="lv-stages">${Q_TABS.map(([k,l])=>`<button type="button" class="lv-step${k===tab?' on':''}" data-action="q-tab" data-id="${type}|${k}">${l} ${n(k)}</button>`).join('')}</div><button type="button" class="btn primary" data-action="q-bulk" data-id="${type}"${sel.length?'':' disabled'}>批量同意${sel.length?'（'+sel.length+'）':''}</button></div>
${rows.length?`<div class="lv-table"><table class="table"><thead><tr><th><input type="checkbox" data-action="q-all" data-id="${type}" aria-label="全选"${all?' checked':''}></th><th>事项</th><th>名称</th><th>提交人</th><th>日期</th><th>内容</th><th></th></tr></thead><tbody>${rows.map(x=>`<tr><td>${x.batch?`<input type="checkbox" data-action="q-pick" data-id="${e(qid(x))}" aria-label="选择"${view2.sel.has(qid(x))?' checked':''}>`:'<span class="lv-single" title="需单独办理">单</span>'}</td><td><span class="lv-kind k-${e(x.kind)}">${e(x.label)}</span></td><td><strong>${e(x.name)}</strong></td><td>${e(x.who)}</td><td>${e(x.on)}</td><td class="lv-sum">${e(x.summary)}</td><td class="lv-ops">${c.act('查看','q-view',qid(x),'sm')}${x.batch||(x.kind!=='close')?c.act('同意','q-ok',qid(x),'sm primary'):''}${c.act('退回','q-ret',qid(x),'sm')}</td></tr>`).join('')}</tbody></table></div>`:'<p class="lv-empty">没有待审批事项</p>'}</section>`;
}
const findQ=id=>(view2.items||[]).find(x=>qid(x)===id);
async function approveQ(c,x,extra={}){
 const reason=extra.reason||'同意';
 if(x.kind==='change')return c.api('/social/lifecycle/changes/'+x.id+'/actions',{method:'POST',body:{action:'approve',reason,basis:extra.basis||'',expected_version:x.version}});
 if(x.type==='project'){
  const body={action:x.action,reason,basis:extra.basis||'',expected_version:x.version};
  if(x.action==='close')body.materials_checked=['plan','filing_form','roster','attendance','hours','process','assessment','outcomes'];
  if(extra.review)body.review=extra.review;
  if(extra.prior_review_on)body.prior_review_on=extra.prior_review_on;
  return c.api('/social/projects/'+x.id+'/actions',{method:'POST',body});
 }
 return c.api('/applications/'+x.id+'/actions',{method:'POST',body:{action:'approve',reason,basis:extra.basis||'',expected_version:x.version}});
}
async function returnQ(c,x,reason){
 if(x.kind==='change')return c.api('/social/lifecycle/changes/'+x.id+'/actions',{method:'POST',body:{action:'return',reason,basis:'',expected_version:x.version}});
 if(x.type==='project'){
  const action=['COLLEGE','CLOSE_COLLEGE'].includes(x.state)||x.action==='approve'?'college_return':'return';
  return c.api('/social/projects/'+x.id+'/actions',{method:'POST',body:{action,reason,basis:'',expected_version:x.version}});
 }
 return c.api('/applications/'+x.id+'/actions',{method:'POST',body:{action:'return',reason,basis:'',expected_version:x.version}});
}
function returnForm(c,x){
 c.formModal('退回 · '+x.name,c.field('reason','退回原因','textarea','',{full:true,rows:3,textLimit:2000}),async v=>{
  if(String(v.reason||'').trim().length<2)throw Error('请写退回原因');
  await returnQ(c,x,v.reason.trim());c.closeModal();c.toast('已退回');await c.render?.();
 },{submit:'退回',stepper:false});
}
function okForm(c,x){
 // 需要依据（补贴性/高风险备案、人事认定、教务备案）的不进批量，这里单独补依据。
 const needPrior=x.type==='project'&&x.action==='file'&&!x.batch,needBasis=needPrior||x.needs_basis||(!x.batch&&x.kind!=='close');
 if(!needBasis)return approveQ(c,x).then(async()=>{c.toast('已同意');await c.render?.()});
 c.formModal('同意 · '+x.name,c.field('basis',needPrior?'前置审核依据':x.needs_basis?'认定依据（协议、发文或会议纪要）':'依据（文号、日期）','text','',{full:true,required:!!x.needs_basis})+(needPrior?c.field('prior_review_on','前置审核日期','date','',{required:false}):''),async v=>{
  await approveQ(c,x,{basis:v.basis||'',prior_review_on:v.prior_review_on||''});c.closeModal();c.toast('已同意');await c.render?.();
 },{submit:'同意',stepper:false});
}
async function closeReviewModal(c,x){
 const r=await c.api('/social/lifecycle/close-review/'+encodeURIComponent(x.id)),e=c.esc,d=r.archive;
 const files=r.files||[];
 const grid=`<div class="lv-mat">${GROUPS.map(g=>{const fs=files.filter(f=>groupOf(f.name)===g);return `<div class="lv-group"><div class="lv-ghead"><strong>${g}</strong><span>${fs.length}</span></div>${fs.map(f=>`<a class="lv-file is-link" href="/api/attachments/${e(f.id)}/download" target="_blank" rel="noopener">${e(f.name)}</a>`).join('')||'<div class="lv-file is-empty">—</div>'}</div>`}).join('')}</div>`;
 const stats=`<div class="life-stats">${(d.stats||[]).map(([k,v])=>`<div><b>${e(v)}</b><small>${e(k)}</small></div>`).join('')}${r.closeout?.satisfaction!=null?`<div><b>${e(r.closeout.satisfaction)}%</b><small>满意度</small></div>`:''}</div>`;
 const noUnits=!r.units,college=x.action==='approve';
 const unitsNote=noUnits?`<div class="lv-gaps"><strong>老师还没上传参训明细表</strong></div>`:'';
 const body=`<div class="life-archive">${unitsNote}<dl class="life-facts">${(d.facts||[]).map(([k,v])=>`<div><dt>${e(k)}：</dt><dd>${e(v)}</dd></div>`).join('')}</dl>${stats}${r.points?`<div class="lv-points">本项目将记积分：${e(r.points)}</div>`:''}<div class="lv-mat-head"><h3>运行材料 <span class="life-count">${files.length}</span></h3>${files.length?c.act('一键下载（'+files.length+' 个文件）','q-dl',x.id,'primary'):''}</div>${grid}</div>`;
 view2.files=files;view2.review=r;
 const ok=noUnits?'':college?c.act('同意','q-ok-close',qid(x),'primary'):c.act('同意','q-close-review',qid(x),'primary');
 return c.modal((x.label||'结项')+' · '+x.name,body,`${c.act('退回','q-ret',qid(x),'')}${ok}${c.act('关闭','close')}`,true,'培训项目 / 结项审批');
}
// 学校结项核验：登记满意度（管理办法第十四条）和财务确认的到账收入、分配（第二十一条），填完才能同意。
function schoolCloseForm(c,x){
 const r=view2.review||{},co=r.closeout||{},income=Number(co.actual_income??r.expected_income??0)||0;
 // 2026-11-10 用户定：学校核验时填实际满意度分数（0–100，必填，无默认值）；其余仍一键：收入自动带出，零收入不用填。
 const body=c.field('satisfaction','满意度分数（%）','number',co.satisfaction??'',{min:0,max:100,step:'0.1'})
  +c.field('rectification_due','整改期限','date','',{required:false})
  +c.field('actual_income','到账收入（元）','number',String(income),{min:0,step:'0.01'})
  +(income>0?c.field('funding_source','资金来源','select','other_training',{options:[['other_training','其他培训收入'],['government_special','政府专项资金']]})+c.field('retained','学校留存（元）','number','',{required:false,min:0,step:'0.01'})+c.field('personnel','人员支出（元）','number','',{required:false,min:0,step:'0.01'})+c.field('finance_reference','财务到账依据','text','',{required:false}):'');
 c.formModal('结项核验 · '+x.name,body,async(v,form)=>{
  const raw=String(v.satisfaction??'').trim(),satNum=Number(raw);
  if(raw===''||!Number.isFinite(satNum)||satNum<0||satNum>100)throw Error('请填写满意度分数（0–100）');
  const sat=String(satNum);
  if(satNum<85&&!v.rectification_due)throw Error('满意度低于 85%，请定整改期限');
  const got=Number(v.actual_income||0);
  const review={satisfaction:sat,actual_income:String(got),finance_reference:String(v.finance_reference||'').trim()||(got===0?'零收入项目，无到账收入':'')};
  if(got>0){
   review.funding_source=v.funding_source||'other_training';
   if(v.retained!==''&&v.retained!=null)review.retained=String(v.retained);
   if(v.personnel!==''&&v.personnel!=null)review.personnel=String(v.personnel);
  }
  if(v.rectification_due)review.rectification_due=v.rectification_due;
  await approveQ(c,x,{review});c.closeModal();c.toast('已结项');await c.render?.();
 },{submit:'同意',stepper:false,contextLabel:'培训项目 / 结项核验'});
}
export async function queueAction(action,id,c){
 if(action==='lv-tab'){const [t,k]=id.split('|');view2.tab[t]=k;return c.render?.()}
 if(action==='lv-rf'){view2.rf=id;return c.render?.()}
 if(action==='lv-again')return againForm(c,id);
 if(action==='q-tab'){const [t,k]=id.split('|');view2.q[t]=k;return c.render?.()}
 if(action==='q-pick'){view2.sel.has(id)?view2.sel.delete(id):view2.sel.add(id);return c.render?.()}
 if(action==='q-all'){const [t]=[id];const tab=view2.q[t]||'all',rows=(view2.items||[]).filter(x=>x.batch&&(tab==='all'||x.kind===tab));const on=rows.every(x=>view2.sel.has(qid(x)));rows.forEach(x=>on?view2.sel.delete(qid(x)):view2.sel.add(qid(x)));return c.render?.()}
 if(action==='q-bulk'){
  const list=[...view2.sel].map(findQ).filter(Boolean);let ok=0;const failed=[];
  for(const x of list){try{await approveQ(c,x);ok++}catch(err){failed.push(x.name+'：'+String(err.message||'').split('\n')[0])}}
  view2.sel.clear();c.toast('已同意 '+ok+' 项'+(failed.length?'；没办成 '+failed.length+' 项：'+failed.join('；'):''),!!failed.length);return c.render?.();
 }
 const x=findQ(id);
 if(action==='q-dl'){for(const f of view2.files||[]){const a=document.createElement('a');a.href='/api/attachments/'+f.id+'/download';a.download=f.name;document.body.appendChild(a);a.click();a.remove();await new Promise(r=>setTimeout(r,300))}return}
 if(!x)throw Error('这条已经办理过了，请刷新');
 if(action==='q-ok')return okForm(c,x);
 if(action==='q-ok-close'){c.closeModal();return okForm(c,x)}
 if(action==='q-close-review'){c.closeModal();return schoolCloseForm(c,x)}
 if(action==='q-ret'){c.closeModal?.();return returnForm(c,x)}
 if(action==='q-view'){
  if(x.kind==='change')return c.runAction('life-change-view',x.id);
  if(x.kind==='close')return closeReviewModal(c,x);
  return x.type==='project'?c.runAction('social-detail','social_project|'+x.id):c.runAction('app-detail',x.id);
 }
 throw Error('此操作入口暂不可用');
}

// 再办一期：复制已结项项目的类别、场地、口径和人员，只改名称、日期、人次。
async function againForm(c,id){
 const x=await c.api('/social/objects/social_project/'+encodeURIComponent(id)),p=x.item.data,e=c.esc;
 const copied=[['类别',({subsidy:'补贴性培训',enterprise:'企业定制培训',community:'社区公益培训',rural:'乡村帮扶培训',other:'其他非学历培训'})[p.category]||''],['场地',(p.venue&&p.venue.place)||'']].filter(z=>z[1]);
 c.formModal('再办一期 · '+p.name,c.field('name','项目名称','text',p.name,{full:true})+c.field('start_date','开始日期','date','')+c.field('end_date','结束日期','date','')+c.field('expected_participants','预估人次','number','',{min:1,step:'1'})
  +`<div class="form-field full lv-copied">${copied.map(([k,v])=>`<span>${e(k)}：<b>${e(v)}</b></span>`).join('')}</div>`+c.field('lv_files','方案材料','file','',{multiple:true,accept:'.pdf,.png,.jpg,.jpeg,.docx,.xlsx,.pptx',full:true}),async(v,form)=>{
  if(!v.start_date||!v.end_date||!v.expected_participants)throw Error('请填写起止日期和预估人次');
  if(v.end_date<v.start_date)throw Error('结束日期不能早于开始日期');
  const {checkUploadFiles,uploadEntries,uploadSequential}=await import('./approval-flow.js?v=20261110-doc1');
  const files=checkUploadFiles(form.querySelector('#f-lv_files')?.files||[]);
  if(!files.length)throw Error('请附上方案材料（立项需要正式依据）');
  const keep=['category','high_risk','expected_income','expected_outcomes','mode','class_type','level','scene','target_groups','one_skill','venue','total_hours','audience','service_type','teaching_mode'];
  const data={...Object.fromEntries(keep.filter(k=>p[k]!==undefined).map(k=>[k,p[k]])),code:'XM-'+String(v.start_date).replace(/-/g,'')+'-'+Math.random().toString(36).slice(2,6).toUpperCase(),name:String(v.name).trim(),cohort:'第一期',org_id:x.item.org_id,owner_id:c.me.user.id,
   expected_participants:Number(v.expected_participants),start_date:v.start_date,end_date:v.end_date,dates_confirmed:true,level_confirmed:true,scene_confirmed:true,mode_confirmed:true};
  const r=await c.api('/social/projects',{method:'POST',body:{reason:'再办一期（复制自 '+p.name+'）',data}});
  const up=await uploadSequential({api:c.api,kind:'social_project',id:r.item.id,version:r.item.version,entries:uploadEntries(files),reason:'立项方案材料'});
  if(up.failed?.length){c.closeModal();c.toast('已保存为草稿，材料没传完，请在详情里补传后提交',true);await c.render?.();return}
  try{await c.api('/social/projects/'+r.item.id+'/actions',{method:'POST',body:{action:'submit',expected_version:up.version,reason:'提交学院审批'}})}
  catch(err){c.closeModal();c.toast('已保存为草稿，暂未提交：'+err.message,true);await c.render?.();return}
  view2.tab.project='apply';c.closeModal();c.toast('已提交学院审批');await c.render?.();
 },{submit:'提交学院审批',stepper:false,contextLabel:'培训项目 / 再办一期'});
}
export const QUEUE_ACTIONS=['lv-tab','lv-rf','lv-again','q-tab','q-pick','q-all','q-bulk','q-dl','q-ok','q-ok-close','q-close-review','q-ret','q-view'];

export const LIFE_ACTIONS=[...QUEUE_ACTIONS,'life-open','life-info','life-note','life-change','life-annual','life-stop','life-resume','life-close','life-upload','life-units','life-report','life-change-view','life-change-act','quick-apply'];
