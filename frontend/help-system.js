import {HELP_VERSION,HELP_TOPICS,HELP_FAQS,HELP_ALIASES,GENERAL_TOPICS,FIELD_HELP,FIELD_LABEL_HELP,ROLE_NAMES,helpTopic} from './help-content.js?v=20261108-fix1';
import {HELP_MEDIA} from './help-media.js?v=20261022';
import {HELP_FORMS} from './help-forms.js?v=20261109-v2l';
const escape=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const button=(text,attr)=>`<button type="button" class="btn" ${attr}>${escape(text)}</button>`;
let panel=null,returnFocus=null,current=null,context=null,background=[],panelTab='steps',underlyingDialog=null,videoKind='overview';
if(typeof document!=='undefined')document.addEventListener('keydown',e=>{if(!panel)return;if(e.key==='Escape'){e.preventDefault();e.stopImmediatePropagation();closeHelp()}else if(panel.contains(e.target)&&['Tab','/'].includes(e.key)&&panel.getAttribute('aria-modal')!=='true')e.stopPropagation()},true);
if(typeof window!=='undefined')window.addEventListener('resize',()=>{if(panel)syncHelpModality()});
function syncHelpModality(){
 for(const [element,old] of background)element.inert=old;background=[];
 if(underlyingDialog){underlyingDialog.setAttribute('aria-modal','true');underlyingDialog=null}
 if(window.matchMedia('(max-width: 1100px)').matches){panel.setAttribute('aria-modal','true');for(const element of document.querySelectorAll('#app,#modal-root')){background.push([element,element.inert]);element.inert=true}if(!panel.contains(document.activeElement))panel.querySelector('[data-help-close]')?.focus({preventScroll:true})}
 else{panel.removeAttribute('aria-modal');underlyingDialog=document.querySelector('#modal-root:not(.hidden) .modal[aria-modal="true"]');underlyingDialog?.setAttribute('aria-modal','false')}
}
export function inferHelpPage(page,title=''){
 if(/密码|账号信息/.test(title))return 'account';
 if(/规则|考核周期/.test(title)&&page==='rules')return 'rules';
 if(/制度执行口径|审批职责/.test(title))return 'policy';
 if(/^设置.*(负责人|认定人)/.test(title))return 'permissions';
 if(/新填.*培训课程/.test(title))return 'apply_course';
 if(/数据核对/.test(title))return 'disputes';
 const matches=[[/结项/,'projects'],[/外聘/,'trainers'],[/课程申报|申请培训课程|申报培训课程/,'apply_course'],[/基地申请|申请培训基地|申报培训基地/,'apply_base'],[/校内.*培训师|申报培训师/,'apply_trainer'],[/申报培训项目|项目申请/,'apply_project'],[/积分.*申报|积分.*认定|积分.*更正/,'recognition'],[/授课认定/,'creditreview'],[/资质/,'qualifications'],[/年度.*考核/,'annual'],[/考核/,'assessment']];
 return matches.find(([re])=>re.test(title))?.[1]||page;
}
// 一组同类勾选项（受众、教学方式、材料核对等）合成一项说明；候选人名单、组织名单是实时数据，只说明怎么选，不逐个列出。
const FIELD_GROUPS=[
 [i=>/^aud_\d+$/.test(i.name),'aud','面向对象',false],
 [i=>/^svc_/.test(i.name),'svc','服务面向类型',false],
 [i=>/^tm_/.test(i.name),'tm','教学实施方式',false],
 [i=>/^dir_/.test(i.name),'dir','培训业务类别',false],
 [i=>/^checked_/.test(i.name)||i.id==='close-check-all','checked','结项材料核对',false],
 [i=>i.name==='org_ids'||i.id==='notice-all','org_ids','发布范围',true],
 [i=>!!i.closest('#duty-options'),'duty_people','选择办理人（可多选）',true],
 [i=>i.name==='head_pick'||!!i.closest('#head-results'),'head_pick','选择负责人（可多选）',true],
];
const LIVE_OPTIONS=['project_code','project_id','policy_id','period_id','teacher_id','owner_id','org_id','parent_id','course_code','class_code','role_id','target_id','user_id','reviewer_id'];
const clean=t=>String(t||'').replace(/\s*\*\s*/g,' ').replace(/\s+/g,' ').trim();
function fieldGroup(input){
 if(!['checkbox','radio'].includes(input.type))return null;
 const rule=FIELD_GROUPS.find(([test])=>test(input));if(!rule)return null;
 const [test,key,fallback,dynamic]=rule,holder=input.closest('[role=group],[role=radiogroup]'),fieldset=input.closest('fieldset');
 const named=holder?.getAttribute('aria-labelledby')?document.getElementById(holder.getAttribute('aria-labelledby')):null;
 const raw=(dynamic?holder?.getAttribute('aria-label')||named?.textContent:named?.textContent||fieldset?.querySelector('legend')?.textContent)||'';
 const root=input.form||input.closest('form,#modal-root')||document;
 const members=[...root.querySelectorAll('input')].filter(i=>['checkbox','radio'].includes(i.type)&&test(i));
 const options=dynamic?[]:members.filter(i=>i.id!=='close-check-all').map(i=>clean(i.labels?.[0]?.textContent||i.closest('label')?.textContent)).filter(Boolean);
 return {key,label:clean(raw)||fallback,required:/\*/.test(raw)||members.some(i=>i.required),options,dynamic,wrap:holder||fieldset||input.parentElement};
}
// 去掉和主说明意思重复的页面提示，避免“同一句话写两遍”。
const core=t=>String(t||'').replace(/[\s，。；、：:,.;！？“”"'（）()《》]/g,'');
function similar(a,b){
 const x=core(a),y=core(b);if(!x||!y)return false;if(x.includes(y)||y.includes(x))return true;
 const pairs=t=>new Set([...t].slice(1).map((c,i)=>t[i]+c)),p=pairs(x),q=pairs(y);let same=0;for(const v of p)if(q.has(v))same++;
 return same/Math.max(1,Math.min(p.size,q.size))>=0.6;
}
const FILE_NAMES=[[/pdf/,'PDF'],[/png/,'PNG'],[/jpe?g/,'JPG'],[/xlsx/,'Excel 表格（.xlsx）']];
// 把最小值、步长、文件类型等技术限制写成老师看得懂的话。
function plainLimits(input,label,hints){
 const attr=k=>{const v=input.getAttribute(k);return v===null||v===''?null:v},out=[];
 if(input.type==='number'){
  const min=attr('min'),max=attr('max'),step=attr('step');
  if(min!==null)out.push(Number(min)===0?'不能填负数':'不能小于 '+min);
  if(max!==null)out.push('不能大于 '+max);
  if(step==='0.5')out.push(/学时/.test(label)?'可以填 0.5 学时这样的半学时':'最小可以填到 0.5');
  else if(step==='1')out.push('只能填整数');
  else if(step&&step.includes('.')){const d=step.split('.')[1].length;out.push('最多保留'+('一两三四'[d-1]||d)+'位小数')}
 }else if(input.type==='file'){
  const accept=(attr('accept')||'').toLowerCase(),kinds=FILE_NAMES.filter(([re])=>re.test(accept)).map(([,n])=>n);
  const size=hints.join(' ').match(/(\d+)\s*(?:MB|兆字节)/i);
  if(kinds.length)out.push('支持 '+kinds.join('、')+(size?'，单个不超过 '+size[1]+'MB':''));else if(size)out.push('单个文件不超过 '+size[1]+'MB');
  if(input.multiple)out.push('可以一次选多个文件');
  if(input.dataset.uploadMax)out.push(Number(input.dataset.uploadMax)===1?'只能上传 1 份':'最多 '+input.dataset.uploadMax+' 份（含已上传的）');
 }else{
  const max=input.dataset.textLimit||attr('maxlength');if(max)out.push('最多 '+max+' 字');
  if(input.multiple)out.push('可以多选');
 }
 return out;
}
function plainExample(input){
 if(['date','password','search'].includes(input.type))return '';
 const m=String(input.placeholder||'').match(/(?:^|\s)(?:例如|例|如)[：:\s]*(.+)$/),value=m?m[1].trim():'';
 return /^\d{4}-\d{2}-\d{2}$/.test(value)?'':value;  // 日期占位“例：2026-10-20”只是格式提示
}
export function describeField(input){
 if(input.type==='hidden'||['submit','button','reset'].includes(input.type)||input.dataset.assistControl)return null;
 const group=fieldGroup(input);
 const wrap=group?.wrap||input.closest('.rule-control,.form-field')||input.parentElement;
 const radio=input.type==='radio'?wrap?.querySelector(':scope > label,legend'):null;
 const label=group?group.label:clean(radio?.textContent||input.getAttribute('aria-label')||input.labels?.[0]?.textContent||wrap?.querySelector('label,legend')?.textContent||input.placeholder||'');
 if(!label)return null;
 // 实时名单旁的提示（如“尚未选择办理人”）是当前状态，不是填写说明。
 const hints=group?.dynamic?[]:cleanHelpHints([...(wrap?.querySelectorAll('.hint')||[])].map(x=>x.textContent.trim()).filter(Boolean));
 const key=group?group.key:(input.name||input.dataset.r||input.dataset.or||({'duty-query':'duty_query','head-q':'head_query'}[input.id])||'').replace(/_search$/,'');
 const special=key==='password'&&input.closest('#login-form')?'输入本人账号的密码；忘记密码请联系学校管理员重置，不要把密码告诉别人。':'';
 const own=special||FIELD_LABEL_HELP[key+'|'+label]||FIELD_LABEL_HELP[label]||'',general=FIELD_HELP[key]||'';
 const fallback={date:'按原始材料填写实际日期，注意开始和结束的先后。',number:'按真实依据填写数值，注意页面上的单位；没有数据时不要随意填 0。',file:'上传清晰、完整、与填写内容一致的材料，并查看每一份的上传结果。',password:'按账号安全要求输入，不要告诉别人。',checkbox:'按实际情况勾选，勾选后注意是否出现新的必填项。',radio:'选择与实际情况一致的一项，并核对后面相关的填写项。'}[input.type]||'按实际材料填写“'+label+'”，不要照抄示例；不清楚学校口径时先问业务负责部门。';
 const explanation=own||general||hints[0]||fallback;
 // 有按名称写好的说明时，它已包含页面提示的意思；只有通用说明时，补上不重复的页面提示。
 const extra=own?[]:hints.filter(h=>h!==explanation&&!similar(h,explanation)).filter((h,i,a)=>a.findIndex(x=>similar(x,h))===i);
 const required=group?group.required:input.required;
 const requirement=input.disabled&&!group?'当前不可填写':input.readOnly?'自动带出／只读':required?'当前必填':'当前选填';
 // 项目、周期、组织、人员等下拉框的选项是实时业务数据，不写进说明。
 const options=group?group.options:input.tagName==='SELECT'&&!LIVE_OPTIONS.includes(key)?[...input.options].filter(o=>!o.disabled&&o.value).map(o=>o.textContent.trim()):[];
 return {key,label,explanation,requirement,hints:extra,limits:group?[]:plainLimits(input,label,hints),options,example:group?'':plainExample(input),documented:!!(own||general||hints.length)};
}
export function cleanHelpHints(hints){return hints.filter(h=>!/^已填\s*\d+\s*\/|^常用语\s*[·・]/.test(h)).map(h=>h.replace(/(\d+)\s*兆字节/g,'$1MB').replace(/(\d+)\s+MB\b/g,'$1MB'))}
// 一个字段的完整说明，按句子排好、句号结尾，不用“。；”拼接；手册、打印版、帮助面板和视频配音共用。
export function fieldSentences(f,{options=true,limits=true}={}){
 const end=s=>{s=String(s||'').trim().replace(/[；;，,、\s]+$/,'');return !s||/[。！？]$/.test(s)?s:s+'。'};
 const parts=[f.explanation,...(f.hints||[]),f.example&&!core(f.explanation).includes(core(f.example))?'示例：'+f.example:'',limits&&f.limits?.length?f.limits.join('，'):'',options&&f.options?.length?'可选：'+f.options.join(f.options.some(o=>o.includes('、'))?'；':'、'):''];
 return parts.filter(Boolean).map(end).filter((s,i,a)=>a.findIndex(x=>similar(x,s))===i).map(s=>s.replace(/。{2,}/g,'。'));
}
export function requirementText(f){return /选填/.test(f.label)&&f.requirement==='当前选填'?'':f.requirement==='当前不可填写'?'按前面的选择才需要填':f.requirement}
export function fieldsIn(root){
 const seen=new Set();return [...(root?.querySelectorAll('input,select,textarea')||[])].filter(i=>!i.closest('[data-help-library],.help-panel,.field-how')&&i.getAttribute('aria-hidden')!=='true').map(describeField).filter(f=>f&&!seen.has(f.key+'|'+f.label)&&seen.add(f.key+'|'+f.label));
}
export function fieldError(input){
 const v=input.validity;
 if(v.valueMissing)return '请先填写或选择。';
 if(v.rangeUnderflow)return '不能小于 '+input.min+'。';
 if(v.rangeOverflow)return '不能大于 '+input.max+'。';
 if(v.stepMismatch)return '请按允许的步长 '+input.step+' 填写。';
 if(v.tooLong)return '内容过长，请按字数限制精简。';
 if(v.badInput)return '请填写有效数值。';
 if(v.customError&&/[\u4e00-\u9fff]/.test(input.validationMessage))return input.validationMessage;
 return '填写格式不符合要求，请核对本项说明。';
}
function fieldHTML(f){return `<section class="help-field"><h3>${escape(f.label)} <small>${escape(requirementText(f))}</small></h3>${fieldSentences(f,{options:false}).map(s=>`<p>${escape(s)}</p>`).join('')}${f.options.length?`<details><summary>可选内容</summary><p>${escape(f.options.join('、'))}</p></details>`:''}</section>`}
function storedFieldGuide(page){return (HELP_FORMS[page]||[]).map(form=>`<details class="help-faq"><summary>${escape(form.title)}（${escape(ROLE_NAMES[form.role]||'对应办理人员')}）：填写指南</summary><p>此处为教学采集时的条件；当前实际必填项会随选项变化，请以正在填写的表单提示为准。</p>${form.fields.map(fieldHTML).join('')}</details>`).join('')}
export function helpSearch(query,aliases={}){
 const q=query.trim().toLowerCase();if(!q)return HELP_TOPICS;
 return HELP_TOPICS.filter(t=>[t.title,t.purpose,t.done,...t.steps,...(HELP_ALIASES[t.id]||[]),...(aliases[t.id]||[]),...(HELP_FORMS[t.id]||[]).flatMap(f=>[f.title,...f.fields.map(x=>x.label+' '+x.explanation)])].join(' ').toLowerCase().includes(q)||(t.id==='help'&&HELP_FAQS.some(([a,b])=>(a+b).toLowerCase().includes(q))));
}
const audienceTopics={teacher:['home','todos','apply_course','apply_project','apply_base','apply_trainer','mine','recognition','qualifications','credits','points','assessment','disputes','records','outcomes','exports','notices','help'],dept:['home','todos','projects','courses','bases','trainers','credits','creditreview','qualifications','assessment','disputes','records','organization','imports','exports','notices','help'],college:['home','todos','projects','courses','bases','trainers','annual','recognition','assessment','ledgers','resources','organization','records','outcomes','imports','exports','notices','help']};
const general=id=>GENERAL_TOPICS.includes(id);
const usable=(c,id)=>general(id)||c.allowed(id);
export function helpLibraryHTML(c){const items=HELP_TOPICS.filter(t=>general(t.id)||c.allowed(t.id)&&(!audienceTopics[c.role]||audienceTopics[c.role].includes(t.id)));return `<section class="card help-library" data-help-library><div class="card-head"><div><h2>操作手册与视频</h2><p>默认推荐当前身份可办理的事项；填写时也可随时打开页面旁的帮助。</p></div><div class="help-downloads"><a class="btn" href="/assets/assets/help/${HELP_VERSION}/manual.html" target="_blank" rel="noopener">阅读图文手册</a><a class="btn" href="/assets/assets/help/${HELP_VERSION}/manual.pdf" download="系统操作手册_${HELP_VERSION}.pdf">下载打印版</a></div></div><div class="card-pad"><label for="help-audience">按使用身份查找</label><select id="help-audience"><option value="current">我的当前身份</option><option value="teacher">教师</option><option value="dept">教研室负责人</option><option value="college">学院负责人</option><option value="school">学校办理人员</option><option value="all">全部教程</option></select><label for="help-query">按业务、页面、字段或问题查找</label><input id="help-query" type="search" placeholder="例如：课程申报、共建单位、材料上传失败"><div class="help-search-results" aria-live="polite">${items.map(t=>topicCard(t,c)).join('')}</div></div></section>`}
function topicCard(t,c){return `<article class="help-topic-card"><h3>${escape(t.title)}</h3><p>${escape(t.purpose)}</p><div>${button('图文与视频',`data-help-topic="${t.id}"`)}${c.allowed(t.id)&&t.id!=='help'?button('进入办理',`data-action="nav" data-id="${t.id}"`):general(t.id)?'<span class="muted">适用于所有使用人员</span>':'<span class="muted">由相应授权人员办理</span>'}</div></article>`}
function bindLibrary(root,c){
 const library=root.querySelector('[data-help-library]');if(!library)return;
 const input=library.querySelector('input'),audience=library.querySelector('#help-audience'),results=library.querySelector('.help-search-results');
 const update=()=>{const q=input.value.trim(),topics=helpSearch(q,c.aliases).filter(t=>audience.value==='current'?(general(t.id)||c.allowed(t.id)&&(!audienceTopics[c.role]||audienceTopics[c.role].includes(t.id))):general(t.id)||!audienceTopics[audience.value]||audienceTopics[audience.value].includes(t.id));topics.sort((a,b)=>Number(general(b.id))-Number(general(a.id))||Number(usable(c,b.id))-Number(usable(c,a.id)));results.innerHTML=(topics.length?topics.map(t=>topicCard(t,c)).join(''):'<p>没有匹配的页面，请尝试业务名称或旧菜单名称。</p>')+HELP_FAQS.filter(([a,b])=>!q||(a+b).includes(q)).map(([a,b])=>`<details class="help-faq"><summary>${escape(a)}</summary><p>${escape(b)}</p></details>`).join('');};input.addEventListener('input',update);audience.addEventListener('change',update);update();
 library.addEventListener('click',e=>{const b=e.target.closest('[data-help-topic]');if(b)openHelp({...c,page:b.dataset.helpTopic,root:null},b)});
}
function existingNotes(root){return [...root.querySelectorAll('.page-help p,.page-help-part,.business-guide,.social-guide,.workflow-context')].map(e=>e.textContent.trim()).filter(Boolean).slice(0,12)}
function localContext(root,c){const title=root.querySelector('.modal-head h2')?.textContent||'';return {...c,page:root.dataset.helpPage||inferHelpPage(c.page,title),root,title,notes:existingNotes(root)}}
function decorateHelpFields(root){
 return;  // 2026-11-09 用户定：字段下不再放“怎么填”说明（全站帮助入口仍保留）
 const fields=[...(root.matches?.('.form-field,.rule-control')?[root]:[]),...root.querySelectorAll('.form-field,.rule-control')];
 for(const wrap of fields){
  if(wrap.querySelector(':scope > .field-how'))continue;const input=wrap.querySelector('input:not([type=hidden]),select,textarea');if(!input||input.closest('.rule-control,.form-field')!==wrap)continue;
  const field=describeField(input);if(!field)continue;const detail=document.createElement('details');detail.className='field-how';detail.innerHTML='<summary>怎么填</summary><div></div>';detail.addEventListener('toggle',()=>{if(detail.open)detail.querySelector('div').innerHTML=fieldHTML(describeField(input))});wrap.append(detail);
 }
}
export function mountHelp(root,c){
 // The portal's renderer-only unit harness has no real DOM; browser checks exercise this path.
 if(!root?.ownerDocument)return;
 context=c;
 const head=root.querySelector('.pagehead .page-title,.tw-heading h1,.modal-head > div,.login-access h2')||root.querySelector('h1');
 // 2026-11-09 用户定：去掉各页和弹窗里的“使用帮助 / 填写说明”按钮，帮助内容只从左下角“帮助中心”菜单进。
 if(false&&head&&!head.querySelector('[data-open-help]')){
  const b=document.createElement('button');b.type='button';b.className='btn help-entry';b.dataset.openHelp='true';b.textContent=root.querySelector('form#edit-form')?'填写说明':'使用帮助';head.append(b);
  b.addEventListener('click',()=>openHelp(localContext(root,c),b));
 }
 root.querySelectorAll('.page-help').forEach(e=>{e.hidden=true});
 decorateHelpFields(root);
 if(root.id==='modal-root'&&!root.dataset.helpObserved){root.dataset.helpObserved='true';new MutationObserver(changes=>{for(const change of changes)for(const node of change.addedNodes)if(node.nodeType===1&&node.querySelector('input,select,textarea'))decorateHelpFields(node)}).observe(root,{childList:true,subtree:true})}
 bindLibrary(root,c);
 // Native invalid events keep focus on the original control; help never submits or rebuilds forms.
 if(!root.dataset.helpBound){root.dataset.helpBound='true';root.addEventListener('invalid',e=>{const i=e.target,w=i.closest('.form-field');if(!w)return;let err=w.querySelector('.field-help-error');if(!err){err=document.createElement('p');err.className='field-help-error';err.setAttribute('role','alert');w.append(err)}err.textContent=(describeField(i)?.label||'此项')+'：'+fieldError(i);i.setAttribute('aria-invalid','true');},true);root.addEventListener('input',e=>{e.target.closest('.form-field')?.querySelector('.field-help-error')?.remove();e.target.removeAttribute('aria-invalid')});}
}
function stopVideo(){panel?.querySelectorAll('video').forEach(v=>{v.pause();v.removeAttribute('src');v.load()})}
function keepSourceScroll(root){const x=window.scrollX,y=window.scrollY,items=[...(root?.querySelectorAll('.modal,.modal-body')||[])].map(node=>[node,node.scrollLeft,node.scrollTop]);return ()=>{for(const [node,left,top] of items){node.scrollLeft=left;node.scrollTop=top}window.scrollTo(x,y)}}
export function closeHelp(restore=true){
 if(!panel)return;
 const restoreScroll=restore?keepSourceScroll(current?.root):null;
 stopVideo();panel?.remove();panel=null;document.body?.classList?.remove('help-is-open');for(const [e,old] of background)e.inert=old;background=[];if(underlyingDialog){underlyingDialog.setAttribute('aria-modal','true');underlyingDialog=null}if(restore&&returnFocus?.isConnected)returnFocus.focus({preventScroll:true});returnFocus=null;current=null;
 restoreScroll?.();
}
function taskState(c){
 if(!c.root?.querySelector('.modal-head'))return '';
 // Read only the visible status/flow labels, not the whole form or historical opinions.
 const text=[...c.root.querySelectorAll('.badge,.status,.flow-current,.approval-current,.detail-status-summary strong')].map(x=>x.textContent).join(' ');
 if(/退回|补正/.test(text))return '当前需要补正：先看退回意见，保留正确内容与材料，补齐后重新提交。';
 if(/已归档|已结项/.test(text))return '当前已完成归档或结项：核对最终结果，需要更正时使用本业务允许的更正入口。';
 if(c.root.querySelector('#edit-form'))return '正在填写或办理：先核对当前窗口标题和按钮。保存草稿、提交、审核与归档的结果不同。';
 if(/审核中|审批中|复审中|待审核|待归档/.test(text))return c.role==='teacher'?'当前等待办理：查看进度中的实际办理方，除非收到补正要求，不要重复新建或提交。':'当前处于办理环节：先核对资料与本人职责，通过或退回后回看最新进度；不能审核本人的事项。';
 return '查看详情中的实际进度和当前办理方；教程中的示例人员不是本事项的审批人员。';
}
function drawPanel(){
 const t=helpTopic(current.page);if(!t)return;stopVideo();const fields=fieldsIn(current.root),baseMedia=HELP_MEDIA[t.id],media=videoKind==='filling'&&baseMedia?.filling?baseMedia.filling:baseMedia;
 panel.innerHTML=`<header class="help-panel-head"><div><span>${escape(ROLE_NAMES[current.role]||'使用说明')} · ${HELP_VERSION.slice(0,4)}年${HELP_VERSION.slice(4,6)}月${HELP_VERSION.slice(6)}日版</span><h2 id="context-help-title">${escape(current.title||t.title)}</h2></div>${button('关闭帮助','data-help-close aria-label="关闭帮助并返回操作"')}</header><nav class="help-panel-tabs" aria-label="帮助内容">${[['steps','这页怎么用'],['fields',(fields.length||HELP_FORMS[t.id]?.length)?'每项怎么填':'数据怎么看'],['video','看操作视频']].map(([key,label])=>`<button type="button" data-help-tab="${key}" aria-pressed="${key===panelTab}">${label}</button>`).join('')}</nav><div class="help-panel-body" tabindex="0">${panelTab==='steps'?`<p class="help-purpose">${escape(t.purpose)}</p>${taskState(current)?`<p class="help-context">${escape(taskState(current))}</p>`:''}<h3>操作步骤</h3><ol>${t.steps.map(s=>`<li>${escape(s)}</li>`).join('')}</ol><h3>怎样知道办好了</h3><p>${escape(t.done)}</p>${media?.poster?`<figure><img src="${escape(media.poster)}" alt="${escape(t.title)}演示页面" loading="lazy"><figcaption>虚构演示资料，实际人员和数据以当前业务为准。</figcaption></figure>`:''}${current.notes?.length?`<details><summary>当前页面的口径与说明</summary>${current.notes.map(n=>`<p>${escape(n)}</p>`).join('')}</details>`:''}<h3>遇到问题</h3>${HELP_FAQS.map(([a,b])=>`<details class="help-faq"><summary>${escape(a)}</summary><p>${escape(b)}</p></details>`).join('')}`:panelTab==='fields'?`${fields.length?'<p>以下必填性、可选项与限制读取自当前页面；修改选项后重新打开本栏即可核对最新要求。示例不会自动填入。</p>'+fields.map(fieldHTML).join(''):`<p>${escape(t.purpose)}</p><ol>${t.steps.map(s=>`<li>${escape(s)}</li>`).join('')}</ol><p>先核对身份、周期、组织及筛选条件；空值、缺少来源和待认定不等于正常零值。</p><p>具体填写字段会在打开业务表单后显示。${escape(t.done)}</p>`}`:media?`<p>${escape(media.description||'实际页面操作演示，使用虚构资料。')}</p><video controls preload="none" playsinline poster="${escape(media.poster)}" src="${escape(media.src)}"><track kind="subtitles" label="中文字幕" srclang="zh" src="${escape(media.captions)}" default></video><p class="help-media-error" role="alert" hidden>视频暂时无法加载，图文说明仍可使用。${button('重新加载','data-help-retry')}</p><label>播放速度 <select data-help-speed aria-label="播放速度"><option value="0.75">较慢</option><option value="1" selected>正常</option><option value="1.25">稍快</option><option value="1.5">较快</option></select></label><h3>视频章节</h3><div class="help-chapters" data-video-chapters>${(media.chapters||[]).map(ch=>button(ch.title,`data-help-seek="${ch.time}"`)).join('')}</div><p>视频为版本化演示，实际状态与审批人员请看业务详情。</p>`:'<p>本页视频尚未交付。请先查看完整图文说明；不会用空链接代替视频。</p>'}</div><footer class="help-panel-foot"><a href="/assets/assets/help/${HELP_VERSION}/manual.html#${t.id}" target="_blank" rel="noopener">阅读／打印这一章</a><span>帮助不会保存或提交业务</span></footer>`;
 panel.querySelector('[data-help-close]').onclick=()=>closeHelp();
 if(panelTab==='video'&&media?.chapters?.length>8){const chapters=panel.querySelector('[data-video-chapters]');chapters.insertAdjacentHTML('beforebegin','<label class="help-chapter-filter">查找视频章节<input type="search" placeholder="输入字段或步骤名称" aria-label="查找视频章节"></label>');panel.querySelector('.help-chapter-filter input').addEventListener('input',event=>{for(const b of chapters.querySelectorAll('button'))b.hidden=!b.textContent.includes(event.target.value.trim())})}
 if(panelTab==='video'&&media){const video=panel.querySelector('video');video.insertAdjacentHTML('afterend',`${button('全屏观看','data-help-fullscreen')}<p class="help-fullscreen-status" role="status" hidden></p>`);panel.querySelector('[data-help-fullscreen]').onclick=async()=>{try{await video.requestFullscreen()}catch{if(!video.isConnected)return;const status=panel.querySelector('.help-fullscreen-status');status.hidden=false;status.textContent='当前浏览器暂不支持全屏，请放大浏览器窗口观看。'}}}
 if(panelTab==='video'&&baseMedia?.filling){const body=panel.querySelector('.help-panel-body');body.insertAdjacentHTML('afterbegin',`<div class="help-chapters">${button('操作流程',`data-help-video-kind="overview" aria-pressed="${videoKind==='overview'}"`)}${button('逐项填写讲解',`data-help-video-kind="filling" aria-pressed="${videoKind==='filling'}"`)}</div>`);body.querySelectorAll('[data-help-video-kind]').forEach(b=>b.onclick=()=>{videoKind=b.dataset.helpVideoKind;drawPanel();panel.querySelector(`[data-help-video-kind="${videoKind}"]`).focus()})}
 if(panelTab==='fields')panel.querySelector('.help-panel-body').insertAdjacentHTML('beforeend',storedFieldGuide(t.id));
 panel.querySelectorAll('[data-help-tab]').forEach(b=>b.onclick=()=>{panelTab=b.dataset.helpTab;drawPanel();panel.querySelector(`[data-help-tab="${panelTab}"]`).focus()});
 const video=panel.querySelector('video');if(video){const errorBox=panel.querySelector('.help-media-error'),failed=()=>{if(video.isConnected)errorBox.hidden=false};video.addEventListener('error',failed);panel.querySelector('[data-help-retry]').onclick=()=>{panel.querySelector('.help-media-error').hidden=true;video.load()};panel.querySelector('[data-help-speed]').onchange=e=>{video.playbackRate=Number(e.target.value)};panel.querySelectorAll('[data-help-seek]').forEach(b=>b.onclick=()=>{const seek=()=>{if(!video.isConnected)return;video.currentTime=Number(b.dataset.helpSeek);video.play().catch(failed);video.scrollIntoView({block:'nearest'});video.focus({preventScroll:true})};if(video.readyState>=1)seek();else{video.addEventListener('loadedmetadata',seek,{once:true});video.load()}})}
}
export function openHelp(c,trigger){
 closeHelp(false);if(!helpTopic(c.page))return;current=c;returnFocus=trigger||document.activeElement;panelTab='steps';videoKind='overview';
 const restoreScroll=keepSourceScroll(c.root);
 panel=document.createElement('aside');panel.className='help-panel';panel.setAttribute('role','dialog');panel.setAttribute('aria-label','当前页面使用帮助');panel.setAttribute('aria-labelledby','context-help-title');document.body.append(panel);document.body.classList.add('help-is-open');
 // Keep the original controls mounted; the help layer only reads metadata, never values.
 syncHelpModality();
 panel.addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();e.stopImmediatePropagation();closeHelp()}if(e.key==='Tab'&&panel.getAttribute('aria-modal')==='true'){const items=[...panel.querySelectorAll('button,a,input,select,[tabindex="0"],video')].filter(x=>!x.disabled&&x.getClientRects().length);const first=items[0],last=items.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus()}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus()}}},true);
 drawPanel();panel.querySelector('[data-help-close]').focus({preventScroll:true});restoreScroll();
}
