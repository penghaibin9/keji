import {bindFormAssists,rememberForm,formSnapshot,dirtyForms,confirmFormReplacement} from './form-assist.js?v=20261021-form-merged1';

export const draftOwnerKey=owner=>[owner?.user_id,owner?.role_id,owner?.org_id].join('|');
export function draftPayload(form){
 const values={},files={};
 for(const e of Array.from(form.elements||[])){
  if(e.dataset?.longTermControl){values._long_term=!!e.checked;continue}
  if(!e.name||e.readOnly||['password','hidden','button','submit','reset'].includes(e.type))continue;
  if(e.type==='file'){files[e.name]=Array.from(e.files||[]).map(f=>f.name);continue}
  if(e.type==='radio'){if(e.checked)values[e.name]=e.value;continue}
  values[e.name]=e.type==='checkbox'?!!e.checked:e.value;
 }
 const auxiliary=Array.from(form.querySelectorAll?.('.aux-row')||[]).map(row=>({
  work_date:row.querySelector('.aux-date').value,amount:row.querySelector('.aux-amount').value,
  description:row.querySelector('.aux-desc').value
 }));
 return {values,files,auxiliary};
}
export function restorableDraft(draft,sourceVersion){
 return (draft?.source_version??null)===(sourceVersion??null);
}
export function draftSavedSnapshot(form,snapshot=formSnapshot(form)){
 const files=new Set(Array.from(form.elements||[]).filter(e=>e.type==='file').map(e=>e.name));
 return JSON.stringify(JSON.parse(snapshot).map(([name,value])=>[name,files.has(name)?[]:value]));
}
function makeButton(text,run){
 const b=document.createElement('button');b.type='button';b.className='btn sm';b.textContent=text;
 b.addEventListener('click',run);return b;
}
export function restoreDraftValues(form,payload){
 const problems=[];
 const longTerm=form.querySelector('[data-long-term-control]');
 if(longTerm&&typeof payload.values._long_term==='boolean'){longTerm.checked=payload.values._long_term;longTerm.dispatchEvent(new Event('change',{bubbles:true}))}
 for(const e of Array.from(form.elements)){
  if(e.type==='file'){e.value='';e.dispatchEvent(new Event('change',{bubbles:true}));continue}
  if(!e.name||e.readOnly||['password','hidden','button','submit','reset'].includes(e.type)||!(e.name in payload.values))continue;
  const value=payload.values[e.name];
  if(e.type==='checkbox')e.checked=value===true;
  else if(e.type==='radio')e.checked=e.value===value;
  else if(e.tagName==='SELECT'&&!Array.from(e.options).some(o=>o.value===value)){
   e.selectedIndex=-1;problems.push((e.labels?.[0]?.textContent||'选项').replace(/\*/g,'').trim()+'需重新检索确认');
  }else e.value=value;
  e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));
 }
 const rows=form.querySelector('#aux-rows');
 if(rows){rows.replaceChildren();for(const row of payload.auxiliary||[]){
  form.querySelector('#aux-add')?.click();bindFormAssists(form);
  const target=rows.lastElementChild;if(!target){problems.push('辅助工作行尚未准备好，请重新恢复');break}
  for(const [key,selector] of [['work_date','.aux-date'],['amount','.aux-amount'],['description','.aux-desc']]){
   const e=target.querySelector(selector);e.value=row[key]||'';e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));
  }
 }}
 return problems;
}
export function bindFormDraft(form,profile,{api,owner,currentOwner,title,toast}){
 if(!form?.ownerDocument||!profile)return null;
 const root=form.closest('#modal-root'),initialOwner=draftOwnerKey(owner),fixed=profile.sourceVersion!=null;
 const prefix=(profile.contextKey||'new')+':',freshKey=()=>prefix+crypto.randomUUID();
 let contextKey=fixed?profile.contextKey:freshKey(),version=0,active=false,claimed=false,ready=false,conflicted=false,loaded=null,page=1;
 const box=document.createElement('section');box.className='form-draft-panel';
 const heading=document.createElement('strong');heading.textContent='填写暂存 · 仅本人当前身份可见';
 const message=document.createElement('p');message.setAttribute('role','status');message.textContent='正在查找已保存的填写草稿…';
 const controls=document.createElement('div');controls.className='draft-controls';
 const picker=document.createElement('select');picker.setAttribute('aria-label','选择本人填写草稿');picker.dataset.assistControl='true';
 const preview=document.createElement('details');preview.className='draft-preview';preview.hidden=true;
 const summary=document.createElement('summary');summary.textContent='查看暂存内容';const content=document.createElement('div');preview.append(summary,content);
 box.append(heading,message,controls,preview);form.prepend(box);
 const save=makeButton('暂存填写（可未填完）',saveCurrent);save.classList.add('light');save.disabled=true;
 root.querySelector('.modal-foot').prepend(save);
 const live=()=>form.isConnected&&draftOwnerKey(currentOwner())===initialOwner;
 const check=response=>{if(!live())throw Error('当前表单已关闭或身份已变化');if(draftOwnerKey(response.owner)!==initialOwner)throw Error('登录身份已变化，暂存没有恢复到此表单，请刷新确认身份');return response};
 const url=key=>'/form-drafts/'+profile.kind+'?'+new URLSearchParams({context_key:key});
 const fail=error=>{if(form.isConnected){message.textContent=error.message||'暂存操作未完成，当前文字仍保留';if(error.status===409){conflicted=true;save.disabled=true}}};
 const run=fn=>async()=>{try{await fn()}catch(error){fail(error)}};
 const view=record=>{
  content.replaceChildren();preview.hidden=!record;if(!record)return;
  const fields=Array.from(form.elements);
  for(const [name,value] of Object.entries(record.payload.values)){
   if(name==='user_id')continue;
   const field=fields.find(e=>e.name===name)||(name==='_long_term'?form.querySelector('[data-long-term-control]'):null);
   const line=document.createElement('p'),label=(name==='_long_term'?'长期有效':field?.labels?.[0]?.textContent||'原表单填写项').replace(/\*/g,'').trim();
   let text=typeof value==='boolean'?(value?'是':'否'):value;
   if(field?.tagName==='SELECT')text=Array.from(field.options).find(o=>o.value===value)?.textContent||'原选项当前不可选';
   if(field?.type==='radio')text=fields.find(e=>e.name===name&&e.value===value)?.labels?.[0]?.textContent||'原选项当前不可选';
   line.textContent=label+'：'+(text||'未填写');content.append(line);
  }
  for(const row of record.payload.auxiliary||[]){const line=document.createElement('p');line.textContent='辅助工作：'+[row.work_date,row.amount,row.description].join(' / ');content.append(line)}
  const files=Object.values(record.payload.files||{}).flat();if(files.length){const line=document.createElement('p');line.textContent='需要重新选择的材料：'+files.join('、');content.append(line)}
 };
 async function fetchCurrent(key){return check(await api(url(key)))}
 async function refresh(){
  ready=false;save.disabled=true;
  try{
   if(fixed){const response=await fetchCurrent(contextKey);version=response.version;loaded=response.draft;active=!!loaded;view(loaded);message.textContent=loaded?'有一份已暂存的填写内容，可查看后恢复。':'可先暂存未填完的内容，再继续正式办理。'}
   else{
    const response=check(await api('/form-drafts?'+new URLSearchParams({kind:profile.kind,prefix,page:String(page)})));
    picker.replaceChildren(new Option('选择一份本人暂存继续填写',''));
    for(const item of response.items)picker.append(new Option(item.title+' · '+new Date(item.updated_at).toLocaleString('zh-CN'),item.context_key));
    previous.disabled=page<=1;next.disabled=page*response.size>=response.total;previous.hidden=next.hidden=response.total<=response.size;
    message.textContent=response.total?'找到 '+response.total+' 份本人暂存，选择后可查看或恢复；当前填写会另存，不覆盖它们。':'可先暂存未填完的内容；不会提前创建或提交业务。';
   }
   ready=true;save.disabled=conflicted;restoreButton.disabled=fixed?!loaded:!picker.value;
  }catch(error){fail(error)}
 }
 async function selectedRecord(){
  const key=fixed?contextKey:picker.value;if(!key)throw Error('请先选择一份填写草稿');
  const response=await fetchCurrent(key);if(!response.draft)throw Error('这份草稿已处理，请重新读取列表');
  return {key,response};
 }
 async function restore(){
  const {key,response}=await selectedRecord();view(response.draft);
  if(!restorableDraft(response.draft,profile.sourceVersion)){preview.open=true;throw Error('原业务已更新，不能直接覆盖。旧草稿仍保留，可展开查看后人工核对。')}
  if(dirtyForms(root).includes(form)&&!await confirmFormReplacement(root,'恢复暂存会替换当前未保存文字，并清空当前选择的文件。',{stayLabel:'保留当前填写',discardLabel:'恢复暂存'}))return;
  const problems=restoreDraftValues(form,response.draft.payload);contextKey=key;version=response.version;active=true;claimed=true;loaded=response.draft;conflicted=false;save.disabled=false;rememberForm(form);
  const files=Object.values(loaded.payload.files||{}).flat();
  message.textContent='已恢复填写内容，尚未提交。'+(files.length?'原选的 '+files.length+' 份材料需要重新选择。':'')+problems.join('；');
 }
 async function discard(){
  const {key,response}=await selectedRecord();
  if(!await confirmFormReplacement(root,'只放弃这份服务器暂存，不清空当前输入，也不改正式申请。',{stayLabel:'取消',discardLabel:'放弃暂存'}))return;
  const result=check(await api('/form-drafts/'+profile.kind+'/finish?'+new URLSearchParams({context_key:key}),{method:'POST',body:{owner,expected_version:response.version,action:'discard'}}));
  if(key===contextKey){version=result.version;active=false;claimed=false;loaded=null}
  await refresh();
 }
 async function saveCurrent(){
  if(!ready||!live()||conflicted)return;
  if(form.dataset.saving==='true'){message.textContent='正在保存或提交业务，请等待办理结果。';return}
  save.disabled=true;form.dataset.draftSaving='true';controls.inert=true;
  const submitButtons=Array.from(root.querySelectorAll('button[form=edit-form]')).map(b=>[b,b.disabled]);submitButtons.forEach(([b])=>b.disabled=true);
  const snapshot=formSnapshot(form);
  try{
   const payload=draftPayload(form),name=payload.values.name||title;
   const response=check(await api(url(contextKey),{method:'PUT',body:{owner,expected_version:version,source_version:profile.sourceVersion??null,title:String(name).slice(0,200),...payload}}));
   version=response.version;loaded=response.draft;active=true;claimed=true;restoreButton.disabled=false;rememberForm(form,draftSavedSnapshot(form,snapshot));view(loaded);
   if(!fixed){let option=Array.from(picker.options).find(o=>o.value===contextKey);if(!option){option=new Option('',contextKey);picker.append(option)}option.textContent=loaded.title+' · '+new Date(loaded.updated_at).toLocaleString('zh-CN');picker.value=contextKey;restoreButton.disabled=false}
   message.textContent='已暂存填写内容，未创建或提交业务。刷新或重新登录后，可从同一填写入口恢复；文件需要重新选择。';
  }catch(error){fail(error)}finally{delete form.dataset.draftSaving;controls.inert=false;submitButtons.forEach(([b,wasDisabled])=>{if(b.isConnected)b.disabled=wasDisabled});if(live())save.disabled=conflicted}
 }
 const reload=makeButton('重新读取草稿',run(refresh)),restoreButton=makeButton('恢复暂存',run(restore));
 const viewButton=makeButton('查看暂存',run(async()=>{const {response}=await selectedRecord();view(response.draft);preview.open=true}));
 const discardButton=makeButton('放弃暂存',run(discard));
 const previous=makeButton('上一页草稿',run(async()=>{page--;await refresh()})),next=makeButton('下一页草稿',run(async()=>{page++;await refresh()}));
 const more=document.createElement('details');more.className='draft-more';const moreTitle=document.createElement('summary');moreTitle.textContent='更多暂存操作';more.append(moreTitle,viewButton,discardButton,reload);
 picker.addEventListener('change',()=>{restoreButton.disabled=!picker.value});
 if(!fixed)controls.append(picker);controls.append(restoreButton,more);
 if(!fixed){controls.append(previous,next);more.append(makeButton('当前文字另存一份',()=>{contextKey=freshKey();version=0;active=false;claimed=false;conflicted=false;save.disabled=!ready;picker.value='';restoreButton.disabled=true;message.textContent='已选择另存。当前文字保留，点击“暂存填写”保存为另一份，不覆盖旧草稿。'}))}
 refresh();
 return {async complete(){
  if(!active||!claimed)return;
  try{await api('/form-drafts/'+profile.kind+'/finish?'+new URLSearchParams({context_key:contextKey}),{method:'POST',body:{owner,expected_version:version,action:'complete'}})}
  catch{toast?.('业务已保存，但填写暂存未能清理；请核对暂存列表，勿重复提交业务。',true)}
 }};
}
