import {HELP_VERSION,HELP_TOPICS,HELP_FAQS,FIELD_HELP,FIELD_LABEL_HELP,ROLE_NAMES,helpTopic} from './help-content.js?v=20261022';
import {HELP_MEDIA} from './help-media.js?v=20261022';
import {HELP_FORMS} from './help-forms.js?v=20261022';
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
export function describeField(input){
 const wrap=input.closest('.rule-control,.form-field')||input.parentElement;
 const group=input.type==='radio'?wrap?.querySelector(':scope > label,legend'):null;
 const label=(group?.textContent||input.getAttribute('aria-label')||input.labels?.[0]?.textContent||wrap?.querySelector('label,legend')?.textContent||input.placeholder||'').replace(/\s*\*\s*/g,' ').trim();
 if(!label||input.type==='hidden'||['submit','button','reset'].includes(input.type)||input.dataset.assistControl)return null;
 const hints=cleanHelpHints([...(wrap?.querySelectorAll('.hint')||[])].map(x=>x.textContent.trim()).filter(Boolean));
 const key=(input.name||input.dataset.r||input.dataset.or||'').replace(/_search$/,'');
 const grouped=/^checked_/.test(key)?'逐项核对对应材料，确认清晰完整且内容一致后再勾选；缺少材料时先补齐，不用勾选代替真实核验。':/^aud_/.test(key)?'按本次培训实际面向的人群勾选，可以选择多类对象。':/^tm_/.test(key)?'按实际采用的教学方式勾选，可多选，与培训方案一致。':/^svc_/.test(key)?'按项目实际服务方向勾选，相关依据在方案中说明。':/^dir_/.test(key)?'按本人实际能够承担的培训业务类别勾选，可多选；类别与专业特长分别填写。':!key&&input.type==='checkbox'?'选择具备本职责有效身份的办理人；本人的业务须由其他有权人员办理。':!key&&input.type==='search'?'输入姓名、工号或账号查找人员，再核对组织和有效身份。':'';
 const explanation=(key==='password'&&input.closest('#login-form')?'输入本人本地账号的密码；忘记密码请联系学校管理员，不向他人提供密码。':'')||FIELD_LABEL_HELP[label]||FIELD_HELP[key]||hints.join(' ')||grouped||({date:'按原始材料填写实际日期，核对起止顺序。',number:'按真实业务依据填写数值，注意页面单位；没有数据时不要随意填零。',file:'按该事项要求选择清晰、完整的佐证材料，查看逐份上传结果。',password:'按账号安全要求输入，不向他人提供或写入业务材料。',checkbox:'根据真实情况勾选，勾选后注意是否出现额外必填项。',radio:'选择与实际业务一致的选项，核对后续关联字段。'}[input.type])||'按实际业务材料填写“'+label+'”，不要照抄演示值；不清楚学校口径时先向业务负责部门核实。';
 const requirement=input.disabled?'当前不可填写':input.readOnly?'自动带出／只读':input.required?'当前必填':'当前选填';
 const limits=[];for(const [attr,name] of [['min','最小值'],['max','最大值'],['step','步长'],['maxlength','最多字数'],['accept','允许文件类型']]){const v=input.getAttribute(attr);if(v!==null&&v!=='')limits.push(name+'：'+v)}
 const max=input.dataset.textLimit;if(max)limits.push('最多 '+max+' 字');
 if(input.multiple)limits.push('可多选');
 if(input.dataset.uploadMax)limits.push('最多 '+input.dataset.uploadMax+' 份（含已上传）');
 const options=input.tagName==='SELECT'?[...input.options].filter(o=>!o.disabled&&o.value).map(o=>o.textContent.trim()):[];
 return {key,label,explanation,requirement,hints,limits,options,example:input.type==='password'?'':input.placeholder||'',documented:!!FIELD_LABEL_HELP[label]||!!FIELD_HELP[key]||hints.length>0||!!grouped};
}
export function cleanHelpHints(hints){return hints.filter(h=>!/^已填\s*\d+\s*\/|^常用语\s*[·・]/.test(h)).map(h=>h.replace(/\bPNG\b(?!（)/g,'PNG（图片）').replace(/\bJPG\b(?!（)/g,'JPG（照片）').replace(/\bPDF\b(?!（)/g,'PDF（便携文档）').replace(/(\d+)\s*MB\b(?!（)/g,'$1 MB（兆字节）'))}
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
function fieldHTML(f){return `<section class="help-field"><h3>${escape(f.label)} <small>${escape(f.requirement)}</small></h3><p>${escape(f.explanation)}</p>${f.hints.filter(h=>h!==f.explanation).map(h=>`<p>${escape(h)}</p>`).join('')}${f.example?`<p class="help-example">填写提示／示例：${escape(f.example)}</p>`:''}${f.limits.length?`<p>${escape(f.limits.join('；'))}</p>`:''}${f.options.length?`<details><summary>可选内容</summary><p>${escape(f.options.join('、'))}</p></details>`:''}</section>`}
function storedFieldGuide(page){return (HELP_FORMS[page]||[]).map(form=>`<details class="help-faq"><summary>${escape(form.title)}（${escape(ROLE_NAMES[form.role]||'对应办理人员')}）：填写指南</summary><p>此处为教学采集时的条件；当前实际必填项会随选项变化，请以正在填写的表单提示为准。</p>${form.fields.map(fieldHTML).join('')}</details>`).join('')}
export function helpSearch(query,aliases={}){
 const q=query.trim().toLowerCase();if(!q)return HELP_TOPICS;
 return HELP_TOPICS.filter(t=>[t.title,t.purpose,t.done,...t.steps,...(aliases[t.id]||[]),...(HELP_FORMS[t.id]||[]).flatMap(f=>[f.title,...f.fields.map(x=>x.label+' '+x.explanation)])].join(' ').toLowerCase().includes(q)||(t.id==='help'&&HELP_FAQS.some(([a,b])=>(a+b).toLowerCase().includes(q))));
}
const audienceTopics={teacher:['home','todos','apply_course','apply_project','apply_base','apply_trainer','mine','recognition','qualifications','credits','points','assessment','disputes','records','outcomes','exports','notices','help'],dept:['home','todos','projects','courses','bases','trainers','credits','creditreview','qualifications','assessment','disputes','records','organization','imports','exports','notices','help'],college:['home','todos','projects','courses','bases','trainers','annual','recognition','assessment','ledgers','resources','organization','records','outcomes','imports','exports','notices','help']};
export function helpLibraryHTML(c){const items=HELP_TOPICS.filter(t=>t.id==='account'||c.allowed(t.id)&&(!audienceTopics[c.role]||audienceTopics[c.role].includes(t.id)));return `<section class="card help-library" data-help-library><div class="card-head"><div><h2>操作手册与视频</h2><p>默认推荐当前身份可办理的事项；填写时也可随时打开页面旁的帮助。</p></div><div class="help-downloads"><a class="btn" href="/assets/assets/help/${HELP_VERSION}/manual.html" target="_blank" rel="noopener">阅读图文手册</a><a class="btn" href="/assets/assets/help/${HELP_VERSION}/manual.pdf" download="系统操作手册_${HELP_VERSION}.pdf">下载打印版</a></div></div><div class="card-pad"><label for="help-audience">按使用身份查找</label><select id="help-audience"><option value="current">我的当前身份</option><option value="teacher">教师</option><option value="dept">教研室负责人</option><option value="college">学院负责人</option><option value="school">学校办理人员</option><option value="all">全部教程</option></select><label for="help-query">按业务、页面、字段或问题查找</label><input id="help-query" type="search" placeholder="例如：课程申报、共建单位、材料上传失败"><div class="help-search-results" aria-live="polite">${items.map(t=>topicCard(t,c)).join('')}</div></div></section>`}
function topicCard(t,c){return `<article class="help-topic-card"><h3>${escape(t.title)}</h3><p>${escape(t.purpose)}</p><div>${button('图文与视频',`data-help-topic="${t.id}"`)}${c.allowed(t.id)&&t.id!=='help'?button('进入办理',`data-action="nav" data-id="${t.id}"`):t.id==='account'?'<span class="muted">适用于所有使用人员</span>':'<span class="muted">由相应授权人员办理</span>'}</div></article>`}
function bindLibrary(root,c){
 const library=root.querySelector('[data-help-library]');if(!library)return;
 const input=library.querySelector('input'),audience=library.querySelector('#help-audience'),results=library.querySelector('.help-search-results');
 const update=()=>{const q=input.value.trim(),topics=helpSearch(q,c.aliases).filter(t=>audience.value==='current'?(t.id==='account'||c.allowed(t.id)&&(!audienceTopics[c.role]||audienceTopics[c.role].includes(t.id))):!audienceTopics[audience.value]||audienceTopics[audience.value].includes(t.id));topics.sort((a,b)=>Number(c.allowed(b.id))-Number(c.allowed(a.id)));results.innerHTML=(topics.length?topics.map(t=>topicCard(t,c)).join(''):'<p>没有匹配的页面，请尝试业务名称或旧菜单名称。</p>')+HELP_FAQS.filter(([a,b])=>!q||(a+b).includes(q)).map(([a,b])=>`<details class="help-faq"><summary>${escape(a)}</summary><p>${escape(b)}</p></details>`).join('');};input.addEventListener('input',update);audience.addEventListener('change',update);update();
 library.addEventListener('click',e=>{const b=e.target.closest('[data-help-topic]');if(b)openHelp({...c,page:b.dataset.helpTopic,root:null},b)});
}
function existingNotes(root){return [...root.querySelectorAll('.page-help p,.page-help-part,.business-guide,.social-guide,.workflow-context')].map(e=>e.textContent.trim()).filter(Boolean).slice(0,12)}
function localContext(root,c){const title=root.querySelector('.modal-head h2')?.textContent||'';return {...c,page:root.dataset.helpPage||inferHelpPage(c.page,title),root,title,notes:existingNotes(root)}}
function decorateHelpFields(root){
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
 if(head&&!head.querySelector('[data-open-help]')){
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
