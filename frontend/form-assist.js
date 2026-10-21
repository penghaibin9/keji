import {checkUploadFiles} from './approval-flow.js?v=20261021-form-merged1';
import {takeImage} from './display-image.js?v=20261021-form-merged1';
// 只帮助填写，所有保存、权限、版本与业务校验仍走原有流程。
export function validateFileSelection(files,{kind,max=50,existing=0}={}){
 if(!files.length)return '';
 try{
  if(kind==='cover'){if(files.length>1)throw Error('展示图片一次只能选择一张');for(const file of files)takeImage({file},'file')}
  else if(kind==='proof')checkUploadFiles(files,Math.max(0,existing),{max});
  return '';
 }catch(error){return error.message}
}
export async function fileSignatureError(files){
 for(const file of files){
  try{
   const bytes=new Uint8Array(await file.slice(0,8).arrayBuffer()),ext=file.name.split('.').at(-1).toLowerCase();
   const matches=ext==='png'?[137,80,78,71,13,10,26,10].every((n,i)=>bytes[i]===n):
    ['jpg','jpeg'].includes(ext)?bytes[0]===255&&bytes[1]===216&&bytes[2]===255:
    ext==='pdf'?[37,80,68,70,45].every((n,i)=>bytes[i]===n):false;
   if(!matches)return file.name+'：文件内容与扩展名不符或文件已损坏，请重新选择。';
  }catch{return file.name+'：暂时无法读取，请重新选择。'}
 }
 return '';
}
export const PHRASES = {
 apply:['现提交本次申报，请予审核。','本次申请用于【请补充】，具体安排详见申报材料。','本次提交材料包括：【请补充】。'],
 amend:['本次根据审核意见补充了：【请补充】。','已核对并修正【请补充】，对应材料为【请补充】。'],
 approve:['经核对，同意本次申请。','经审核，同意进入下一办理环节。','本次审核依据及说明：【请补充】。'],
 confirm:['已核对本次结果及依据，确认无误。','本次确认依据及说明：【请补充】。'],
 archive:['已核对归档材料及办理记录，同意归档。','本次归档依据及说明：【请补充】。'],
 return:['请补充以下材料后重新提交：【请补充】。','申报信息与附件中的【请补充】不一致，请核对并修正。','附件中的【请补充】无法清晰辨认，请重新上传。'],
 withdraw:['因【请补充】，申请撤回本次申报。','需要补充或调整【请补充】，申请撤回后修改。'],
 material:['补充本次申请的佐证材料。','本次补传材料包括：【请补充】。','重新提供清晰的【请补充】材料。'],
 outcome:['本次培训面向【请补充】，重点提升学员的【请补充】能力。','培训结束后，学员预期能够独立完成【请补充】。','拟通过【请补充】评价学习效果。'],
 intro:['本课程面向【请补充】，主要讲授【请补充】。','课程采用【请补充】方式，帮助学员掌握【请补充】。'],
 audience:['本项目面向【请补充】群体，对接【请补充】行动。','针对【请补充】需求，安排【请补充】培训内容。'],
 venue:['本次培训需要使用【请补充】现场设备，校内暂不具备对应条件。','为开展【请补充】实践教学，拟在【请补充】进行现场培训。'],
 basis:['依据【请补充文件名称及编号】，办理【请补充事项】。','相关依据见【请补充材料名称及页码】。'],
 qualification:['本人申报教师资质，请予审核。','本次补充或更新的资质材料为：【请补充】。'],
 experience:['在【请补充项目或课程】中承担【请补充授课工作】，授课时间为【请补充】。','主要培训方向为【请补充】，相关经历及佐证见【请补充】。'],
 work:['承担培训签到组织工作，具体内容为【请补充】。','整理培训资料，具体内容为【请补充】。','协助现场教学，具体内容为【请补充】。','核对参训记录，具体内容为【请补充】。'],
 attachment:['本项认定对应附件【请补充】，相关记录位于【请补充】。','认定表与佐证材料的对应关系为：【请补充】。'],
 dispute:['需要核对【请补充事项】，目前记录为【请补充】，认为应为【请补充】，依据为【请补充】。','对【请补充】的计算依据存在疑问，请核对【请补充】。'],
 resolution:['已核对【请补充事项】，依据【请补充材料】，确认【请补充结论】。','已将【请补充】更正为【请补充】，更正依据为【请补充】。'],
 completion:['已完成【请补充培训内容】，实际成果为【请补充】，佐证材料为【请补充】。','本项目完成情况、存在问题及后续安排为：【请补充】。'],
 rectify:['针对【请补充问题】，拟采取【请补充措施】，由【请补充】负责，于【请补充】前完成。'],
 reply:['已核实【请补充事项】，处理情况为【请补充】，后续安排为【请补充】。'],
 selfReport:['本年度完成【请补充任务】，依据及成果为【请补充】。','存在的主要问题为【请补充】，下一步拟【请补充】。'],
 report:['现报送本次统计材料，请予核定。','本次报送的范围、口径及特殊情况为：【请补充】。'],
 review:['本次核定依据为【请补充】，核定结果及调整情况为【请补充】。'],
 refresh:['因补录【请补充】，申请重新取数并核对。','因【请补充】口径更正，申请重新取数。'],
 link:['将已审批课程用于本项目培训。','本课程与项目培训安排的对应关系为：【请补充】。']
};
export function actionPhrases(action){
 if(['return','college_return','reject'].includes(action))return 'return';
 if(action==='withdraw')return 'withdraw';
 if(['approve','file','close','review','school_audit'].includes(action))return 'approve';
 if(action==='confirm')return 'confirm';
 if(action==='archive')return 'archive';
 if(action==='submit')return 'apply';
 return '';
}
export function appendPhrase(value,text,max=Infinity){
 if(value.split('\n').includes(text))return {value,message:'这条常用语已填入，可以直接修改。'};
 const next=value+(value&&!value.endsWith('\n')?'\n':'')+text;
 if([...next].length>max)return {value,message:'填入后会超过字数上限，请先精简内容；原文已保留。'};
 return {value:next,message:'已填入，请按实际情况修改；原有内容已保留。'};
}
export function normalizeDate(value){
 if(!value.trim())return '';
 const m=/^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$/.exec(value.trim());
 if(!m)return null;
 const [y,month,d]=m.slice(1).map(Number),date=new Date(0);
 date.setFullYear(y,month-1,d);date.setHours(0,0,0,0);
 return y>=100&&y<=9999&&date.getFullYear()===y&&date.getMonth()===month-1&&date.getDate()===d?`${String(y).padStart(4,'0')}-${String(month).padStart(2,'0')}-${String(d).padStart(2,'0')}`:null;
}
export function dateError(value,min='',max=''){
 const normal=normalizeDate(value);
 if(normal===null)return '请填写有效日期，例如 2026-10-20。';
 if(normal&&min&&normal<min)return '日期不能早于 '+min+'。';
 if(normal&&max&&normal>max)return '日期不能晚于 '+max+'。';
 return '';
}
const localDay=date=>`${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
export function quickDateRange(kind,now=new Date()){
 const y=now.getFullYear(),m=now.getMonth();
 if(kind==='month')return [localDay(new Date(y,m,1)),localDay(new Date(y,m+1,0))];
 if(kind==='previous-month')return [localDay(new Date(y,m-1,1)),localDay(new Date(y,m,0))];
 if(kind==='year')return [`${y}-01-01`,`${y}-12-31`];
 throw Error('不支持的日期区间');
}
export function parseCalendarDates(value){
 const dates=[];
 for(const token of value.trim().split(/[\s,，、；;]+/).filter(Boolean)){
  const date=normalizeDate(token);
  if(!date)return {dates:[],error:'日期无效：'+token+'，请按年-月-日填写。'};
  dates.push(date);
 }
 const unique=[...new Set(dates)].sort();
 return {dates:unique,error:unique.length>400?'每类校历日期最多选择400天。':''};
}
export function calendarDateError(value,other,lower='',upper=''){
 const parsed=parseCalendarDates(value);if(parsed.error)return parsed.error;
 const otherDates=new Set(parseCalendarDates(other).dates);
 if(parsed.dates.some(d=>otherDates.has(d)))return '同一天不能同时标为放假和补班，请核对两边已选日期。';
 if(parsed.dates.some(d=>lower&&d<lower||upper&&d>upper))return '所选日期必须位于校历开始与结束日期之间。';
 return '';
}
const originals=new WeakMap();
export function formSnapshot(form){
 return JSON.stringify(Array.from(form?.elements||[]).filter(e=>!['button','submit','reset'].includes(e.type)&&!e.dataset?.assistControl&&(e.name||e.dataset?.longTermControl||e.matches?.('input,textarea,select'))).map((e,i)=>[e.name||(e.dataset?.longTermControl?'long-term':'@'+i+':'+(e.id||e.getAttribute?.('aria-label')||e.type)),e.type==='file'?Array.from(e.files||[]).map(f=>[f.name,f.size,f.lastModified]):['checkbox','radio'].includes(e.type)?e.checked:e.value]));
}
export function rememberForm(form,snapshot=formSnapshot(form)){if(form?.elements&&!form.dataset?.queryForm)originals.set(form,snapshot)}
export function dirtyForms(root){
 return Array.from(root?.querySelectorAll?.('form')||[]).filter(f=>originals.has(f)&&formSnapshot(f)!==originals.get(f));
}
let leavePrompt=null;
export function confirmFormReplacement(root,message,{stayLabel='继续填写',discardLabel='放弃修改'}={}){
 if(leavePrompt)return leavePrompt;
 leavePrompt=new Promise(resolve=>{
  const previous=document.activeElement,overlay=document.createElement('div');overlay.className='unsaved-overlay';
  const dialog=document.createElement('section');dialog.className='unsaved-dialog';dialog.setAttribute('role','alertdialog');dialog.setAttribute('aria-modal','true');dialog.setAttribute('aria-label','尚未保存的修改');
  const title=document.createElement('h3');title.textContent='内容还没有保存';
  const text=document.createElement('p');text.textContent=message;
  const finish=answer=>{overlay.remove();leavePrompt=null;previous?.focus();resolve(answer)};
  const stay=button(stayLabel,()=>finish(false),'btn primary'),discard=button(discardLabel,()=>finish(true),'btn');
  dialog.append(title,text,stay,discard);overlay.append(dialog);root.append(overlay);
  dialog.addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();e.stopPropagation();finish(false)}if(e.key==='Tab'){e.preventDefault();e.stopPropagation();(document.activeElement===stay?discard:stay).focus()}});
  stay.focus();
 });
 return leavePrompt;
}
export function allowFormLeave(root,confirm=message=>confirmFormReplacement(root,message)){
 if(root?.querySelector?.('form[data-saving="true"]')?.dataset?.saving==='true')return false;
 return !dirtyForms(root).length||confirm('离开会丢失尚未保存的文字和已选文件。可以继续填写，或放弃本次修改。');
}
export function phraseValidation(value,max,{draft=false}={}){
 if(max&&[...value].length>max)return `内容不能超过 ${max} 字，请精简后再保存。`;
 if(!draft&&/【请补充[^】]*】/.test(value))return '请先补齐“【请补充】”中的具体内容。';
 return '';
}
function emitValue(input,value){
 input.value=value;input.dispatchEvent(new Event('input',{bubbles:true}));input.dispatchEvent(new Event('change',{bubbles:true}));
}
function button(label,callback,className='btn sm'){
 const b=document.createElement('button');b.type='button';b.className=className;b.textContent=label;b.addEventListener('click',callback);return b;
}
const conditionalFields=new WeakMap();
export function setFieldCondition(input,active){
 if(!input?.ownerDocument)return;
 let wrap=conditionalFields.get(input);
 if(!wrap){
  const field=input.closest('.form-field');if(!field)return;
  wrap=document.createElement('details');wrap.className=field.className+' conditional-field';
  const summary=document.createElement('summary');summary.textContent='已填写的'+(input.labels?.[0]?.textContent||'补充信息').replace(/\*/g,'').trim()+'（当前不适用，点击查看）';
  field.before(wrap);wrap.append(summary,field);conditionalFields.set(input,wrap);
 }
 const hasValue=['checkbox','radio'].includes(input.type)?input.checked:String(input.value||'').trim()!=='';
 wrap.hidden=!active&&!hasValue;wrap.open=active;wrap.querySelector('summary').hidden=active;
 if(active)delete wrap.dataset.conditionInactive;else{wrap.dataset.conditionInactive='true';input.setCustomValidity('')}
}
function bindPhrases(input){
 if(input.dataset.phraseBound||input.readOnly||input.disabled)return;
 const phrases=PHRASES[input.dataset.phrases];if(!phrases)return;
 input.dataset.phraseBound='true';
 const box=document.createElement('div');box.className='phrase-assist';
 const hint=document.createElement('p');hint.className='hint';hint.textContent='常用语 · 点击填入，可继续修改；已有内容另起一行追加';
 const row=document.createElement('div');row.className='phrase-choices';
 const status=document.createElement('p');status.className='phrase-status';status.setAttribute('role','status');
 phrases.forEach(text=>{const label=text.includes('【')?text.split('【')[0].replace(/[：，]$/,'')+'…':text;
  const b=button(label,()=>{const result=appendPhrase(input.value,text,Number(input.dataset.textLimit)||Infinity);emitValue(input,result.value);status.textContent=result.message;input.focus();const at=input.value.indexOf('【请补充');if(at>=0)input.setSelectionRange(at,input.value.indexOf('】',at)+1);else input.setSelectionRange(input.value.length,input.value.length)},'phrase-choice');b.title=text;b.setAttribute('aria-label',text);row.append(b);
 });
 box.append(hint,row,status);input.insertAdjacentElement('afterend',box);
}
function bindTextLimit(input){
 if(input.dataset.limitBound||!input.dataset.textLimit)return;input.dataset.limitBound='true';
 const counter=document.createElement('p');counter.className='hint text-count';const limit=Number(input.dataset.textLimit);
 const update=()=>{const count=[...input.value].length;counter.textContent=`已填 ${count} / 最多 ${limit} 字`;counter.classList.toggle('over-limit',count>limit);input.setCustomValidity(count>limit?`内容不能超过 ${limit} 字。`:'')};
 input.insertAdjacentElement('afterend',counter);input.addEventListener('input',update);update();
}
const DATE_PAIRS=[['start_date','end_date'],['obtained','expires'],['calendar_start','calendar_end'],['start','end'],['received_on','investigation_on'],['received_on','completed_on'],['investigation_on','completed_on']];
function boundsFor(input,root){
 let min=input.getAttribute('min')||'',max=input.getAttribute('max')||'';
 for(const [start,end] of DATE_PAIRS){
  const lower=normalizeDate(root.querySelector(`[name="${start}"]`)?.value||''),upper=normalizeDate(root.querySelector(`[name="${end}"]`)?.value||'');
  if(input.name===end&&lower)min=min&&min>lower?min:lower;
  if(input.name===start&&upper)max=max&&max<upper?max:upper;
 }
 return {min,max};
}
function layBound(value,fallback){
 const [year,month,date]=(value||fallback).split('-').map(Number);return {year,month:month-1,date,hours:0,minutes:0,seconds:0};
}
let calendarOwner=null;
export function closeDateCalendar(){
 if(typeof document==='undefined')return false;
 const calendars=document.querySelectorAll?.('.layui-laydate:not(.layui-laydate-static)')||[];if(!calendars.length)return false;
 calendars.forEach(e=>e.remove());calendarOwner?.focus();calendarOwner=null;return true;
}
function calendarKeyboard(calendar,owner,persistent=false){
 calendar.setAttribute('role',persistent?'group':'dialog');calendar.setAttribute('aria-label',persistent?'多选校历日期':'选择日期');
 const update=()=>calendar.querySelectorAll('td[lay-ymd]:not(.laydate-disabled),li:not(.laydate-disabled),.laydate-set-ym span,.layui-laydate-header i,.layui-laydate-footer span[lay-type]').forEach(e=>{
  e.tabIndex=0;e.setAttribute('role','button');
  const labels={'laydate-prev-y':'上一年','laydate-next-y':'下一年','laydate-prev-m':'上个月','laydate-next-m':'下个月'};
  e.setAttribute('aria-label',Object.keys(labels).find(k=>e.classList.contains(k))?labels[Object.keys(labels).find(k=>e.classList.contains(k))]:e.getAttribute('lay-ymd')||e.textContent.trim());
 });
 update();calendar.addEventListener('click',()=>queueMicrotask(update));
 calendar.addEventListener('keydown',event=>{
  if(event.key==='Escape'){event.preventDefault();event.stopPropagation();if(persistent)owner.focus();else closeDateCalendar();return}
  if(['Enter',' '].includes(event.key)&&event.target.matches('[role="button"]')){event.preventDefault();event.stopPropagation();event.target.click();return}
  const nodes=[...calendar.querySelectorAll('[tabindex="0"]')].filter(e=>e.getClientRects().length),at=nodes.indexOf(document.activeElement);
  if(event.key==='Tab'&&!persistent){event.preventDefault();event.stopPropagation();nodes[(at+(event.shiftKey?-1:1)+nodes.length)%nodes.length]?.focus()}
 });
 if(!persistent)(calendar.querySelector('td.layui-this')||calendar.querySelector('td[lay-ymd]:not(.laydate-disabled)'))?.focus({preventScroll:true});
}
function bindRangeShortcuts(form){
 if(form.dataset.rangeBound)return;
 const start=form.querySelector('[name="start"]'),end=form.querySelector('[name="end"]');if(!start||!end)return;
 form.dataset.rangeBound='true';
 const bar=document.createElement('div');bar.className='range-shortcuts form-field full';bar.setAttribute('aria-label','快捷日期范围');
 const year=form.querySelector('#report-year');let selectingYear=false;
 if(year){
  year.addEventListener('change',()=>{const match=/^(\d{4})-(\d{4})$/.exec(year.value);if(!match)return;
   selectingYear=true;start.value=match[1]+'-09-01';end.value=match[2]+'-08-31';emitValue(start,start.value);emitValue(end,end.value);selectingYear=false;
  });
  for(const input of [start,end])input.addEventListener('change',()=>{if(!selectingYear)year.value=''});
 }
 for(const [key,label] of [['month','本月'],['previous-month','上月'],['year','本年']]){
  bar.append(button(label,()=>{const [from,to]=quickDateRange(key);if(year)year.value='';start.value=from;end.value=to;emitValue(start,from);emitValue(end,to)},'btn light sm'));
 }
 form.append(bar);
}
function bindCalendarMulti(input,root){
 if(input.dataset.multiBound||!window.laydate)return;input.dataset.multiBound='true';
 const box=document.createElement('div');box.className='calendar-multi';
 const hint=document.createElement('p');hint.className='hint';hint.textContent='可在日历中连续点选不相邻日期，再点已选日期取消；也可在上方批量粘贴。只按学校正式校历选择。';
 const canvas=document.createElement('div'),list=document.createElement('div'),message=document.createElement('p');
 list.className='calendar-selected';list.setAttribute('aria-label','已选校历日期');message.className='date-message';message.setAttribute('role','status');
 box.append(hint,canvas,list,message);input.after(box);
 const other=()=>root.querySelector(`[name="${input.name==='holidays'?'workdays':'holidays'}"]`)?.value||'';
 const bounds=()=>({lower:normalizeDate(root.querySelector('[name=calendar_start]')?.value||'')||'',upper:normalizeDate(root.querySelector('[name=calendar_end]')?.value||'')||''});
 const paint=()=>{
  const parsed=parseCalendarDates(input.value),selected=new Set(parsed.dates);
  canvas.querySelectorAll('td[lay-ymd]').forEach(cell=>{const chosen=selected.has(normalizeDate(cell.getAttribute('lay-ymd')));cell.classList.toggle('calendar-picked',chosen);cell.classList.toggle('layui-this',chosen);cell.setAttribute('aria-pressed',String(chosen))});
 };
 const refresh=()=>{
  const {lower,upper}=bounds(),parsed=parseCalendarDates(input.value),error=calendarDateError(input.value,other(),lower,upper);
  input.setCustomValidity(error);message.textContent=error;list.replaceChildren();
  const count=document.createElement('span');count.textContent='已选 '+parsed.dates.length+' 天';list.append(count);
  for(const day of parsed.dates)list.append(button(day+' ×',()=>emitValue(input,parsed.dates.filter(d=>d!==day).join('\n')),'btn sm'));
  paint();
 };
 const initial=bounds();
 const calendar=window.laydate.render({elem:canvas,type:'date',position:'static',showBottom:false,lang:'cn',theme:'#265fd3',calendar:false,min:initial.lower||'0100-01-01',max:initial.upper||'9999-12-31',value:parseCalendarDates(input.value).dates[0]||initial.lower||'',
  ready(){const node=canvas.querySelector('.layui-laydate');if(node)calendarKeyboard(node,input,true);paint()},
  done(value){const parsed=parseCalendarDates(input.value);if(parsed.error){message.textContent='请先修正上方无效日期，再继续点选。';return}
   const next=parsed.dates.includes(value)?parsed.dates.filter(d=>d!==value):[...parsed.dates,value].sort(),{lower,upper}=bounds(),error=calendarDateError(next.join('\n'),other(),lower,upper);
   if(error){message.textContent=error;paint();return}emitValue(input,next.join('\n'));
  }
 });
 const sync=()=>{const {lower,upper}=bounds();calendar.config.min=typeof calendar.config.min==='object'?layBound(lower,'0100-01-01'):lower||'0100-01-01';calendar.config.max=typeof calendar.config.max==='object'?layBound(upper,'9999-12-31'):upper||'9999-12-31';refresh()};
 input.addEventListener('input',refresh);root.addEventListener('change',sync);
 new MutationObserver(paint).observe(canvas,{childList:true,subtree:true});
 refresh();
}
function bindDate(input,root){
 if(input.dataset.dateBound||input.readOnly||!window.laydate)return;
 const dateLabel=(input.getAttribute('aria-label')||input.labels?.[0]?.textContent||'日期').replace(/\*/g,'').trim();
 input.setAttribute('aria-label',dateLabel);
 input.dataset.dateBound='true';input.type='text';input.inputMode='numeric';input.autocomplete='off';input.placeholder='例：2026-10-20';
 const wrap=document.createElement('div');wrap.className='date-assist';input.before(wrap);wrap.append(input);
 const message=document.createElement('span');message.className='date-message';message.setAttribute('aria-live','polite');
 const validate=()=>{if(input.disabled||input.closest('[data-condition-inactive]')){input.setCustomValidity('');message.textContent='';return}
  const bounds=boundsFor(input,root),error=dateError(input.value,bounds.min,bounds.max);input.setCustomValidity(error);message.textContent=error;input.setAttribute('aria-invalid',String(!!error));
 };
 const pick=button('选日期',()=>{},'btn date-open');pick.setAttribute('aria-label','选择'+dateLabel);
 wrap.append(pick);
 const instance=window.laydate.render({elem:pick,trigger:'click',type:'date',format:'yyyy-MM-dd',lang:'cn',position:'fixed',theme:'#265fd3',zIndex:100000,calendar:false,btns:['clear','now','confirm'],
  ready(){const cal=document.querySelector('.layui-laydate');if(cal){calendarOwner=pick;calendarKeyboard(cal,pick)}},
  done(value){pick.textContent='选日期';emitValue(input,value);validate();input.focus()}
 });
 pick.addEventListener('click',()=>{const bounds=boundsFor(input,root);pick.setAttribute('lay-date',normalizeDate(input.value)||'');instance.config.min=layBound(bounds.min,'0100-01-01');instance.config.max=layBound(bounds.max,'9999-12-31')},true);
 input.addEventListener('keydown',e=>{if(e.altKey&&e.key==='ArrowDown'){e.preventDefault();pick.click()}});
 input.addEventListener('input',validate);
 input.addEventListener('blur',()=>{const normal=normalizeDate(input.value);if(normal!==null&&normal!==input.value)emitValue(input,normal);validate()});
 root.addEventListener('change',validate);
 const quick=document.createElement('div');quick.className='date-quick';
 const choose=value=>{emitValue(input,value);validate();input.focus()};
 quick.append(button('今天',()=>{const now=new Date();choose(`${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`)},'btn text sm'),button('清空',()=>choose(''),'btn text sm'));
 if(input.name==='end_date')quick.append(button('同开始日',()=>{const start=root.querySelector('[name="start_date"]');if(start&&normalizeDate(start.value))choose(normalizeDate(start.value));else{message.textContent='请先填写有效的开始日期。';start?.focus()}},'btn text sm'));
 if(input.dataset.longTerm!==undefined){
  const label=document.createElement('label'),check=document.createElement('input');check.type='checkbox';check.dataset.longTermControl='true';check.checked=input.dataset.longTerm==='selected';
  label.append(check,document.createTextNode('长期有效'));quick.append(label);let previous=input.value;
  const sync=()=>{if(check.checked){previous=input.value||previous;input.value=''}else input.value=previous;input.disabled=check.checked;input.required=!check.checked;pick.disabled=check.checked;quick.querySelectorAll('button').forEach(b=>b.disabled=check.checked);validate()};
  check.addEventListener('change',()=>{sync();input.dispatchEvent(new Event('input',{bubbles:true}))});sync();
 }
 wrap.after(quick,message);validate();
}
const observedRoots=new WeakSet();
export function bindFormAssists(root){
 if(!root?.ownerDocument)return;
 root.querySelectorAll('[data-phrases]').forEach(bindPhrases);root.querySelectorAll('[data-text-limit]').forEach(bindTextLimit);
 root.querySelectorAll('input[type="date"]').forEach(input=>bindDate(input,input.form||root));
 root.querySelectorAll('form').forEach(bindRangeShortcuts);
 root.querySelectorAll('[data-multi-dates]').forEach(input=>bindCalendarMulti(input,input.form||root));
 if(!observedRoots.has(root)){
  observedRoots.add(root);
  new MutationObserver(()=>bindFormAssists(root)).observe(root,{childList:true,subtree:true});
  for(const event of ['wheel','touchmove'])root.addEventListener(event,()=>{if(calendarOwner)closeDateCalendar()},{capture:true,passive:true});
 }
}
export function validateFormAssists(form,draft=false){
 if(!form?.ownerDocument)return true;
 for(const input of form.querySelectorAll('[data-multi-dates]')){
  const other=form.querySelector(`[name="${input.name==='holidays'?'workdays':'holidays'}"]`);
  const error=calendarDateError(input.value,other?.value||'',normalizeDate(form.querySelector('[name=calendar_start]')?.value||'')||'',normalizeDate(form.querySelector('[name=calendar_end]')?.value||'')||'');
  input.setCustomValidity(error);if(error){input.focus();input.reportValidity();return false}
 }
 for(const input of form.querySelectorAll('[data-phrases],[data-text-limit]')){
  if(input.disabled||input.readOnly)continue;
  const error=phraseValidation(input.value,Number(input.dataset.textLimit),{draft:draft||!!input.closest('[data-condition-inactive]')});
  input.setCustomValidity(error);
  if(error){let parent=input.parentElement;while(parent&&parent!==form){if(parent.tagName==='DETAILS')parent.open=true;parent=parent.parentElement}input.focus();input.reportValidity();return false}
 }
 return true;
}
