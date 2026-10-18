// 审批精简的公共办理逻辑：只编排现有单条接口，不替代后端的权限、回避、版本和来源校验。
export const MAX_ATTACHMENTS=50;
export const UPLOAD_PATTERN=/\.(pdf|png|jpe?g)$/i;

// 选好的文件先整体检查：类型、大小和单个对象 50 份上限，任何一份不合格都不开始保存或上传。
export function checkUploadFiles(files,existing=0,{maxBytes=10*1024*1024,max=MAX_ATTACHMENTS}={}){
 const list=[...(files||[])],bad=[];
 for(const file of list){
  if(!UPLOAD_PATTERN.test(file.name))bad.push(file.name+'：只能是 .jpg、.png 或 .pdf 文件');
  else if(file.size>maxBytes)bad.push(file.name+'：超过 '+Math.round(maxBytes/1024/1024)+' 兆字节，请压缩或分页后再传');
 }
 if(bad.length)throw Error('以下材料不能上传，请更换后再选：\n'+bad.join('\n'));
 if(existing+list.length>max)throw Error('单个业务最多 '+max+' 份附件，已有 '+existing+' 份，本次最多还能选 '+Math.max(0,max-existing)+' 份');
 return list;
}

export const uploadEntries=files=>[...(files||[])].map(file=>({file,name:file.name,status:'waiting',error:''}));
export const failedEntries=entries=>(entries||[]).filter(x=>x.status!=='done');
const STATUS={waiting:'等待上传',uploading:'正在上传',done:'已上传',failed:'上传失败'};
export function uploadStatusHtml(entries,esc){
 return '<ul class="upload-status" aria-live="polite">'+(entries||[]).map(x=>'<li data-status="'+x.status+'"><span>'+esc(x.name)+'</span><b>'+esc(STATUS[x.status]||x.status)+(x.status==='failed'&&x.error?'：'+esc(x.error):'')+'</b></li>').join('')+'</ul>';
}

async function fileDigest(file){
 try{if(!globalThis.crypto?.subtle||!file.arrayBuffer)return '';const hash=await globalThis.crypto.subtle.digest('SHA-256',await file.arrayBuffer());return [...new Uint8Array(hash)].map(b=>b.toString(16).padStart(2,'0')).join('')}catch{return ''}
}

// 业务材料每份使版本加一，考核和同步佐证不改业务版本；逐份上传，失败标明，其余照常继续。
// 失败后重新读取最新版本，并按文件校验值确认“看似失败、实际已入库”的情况，避免补传时重复。
export async function uploadSequential({api,kind,id,version,entries,reason,latest,onProgress=()=>{}}){
 let current=version;
 for(const entry of entries){
  if(entry.status==='done')continue;
  entry.status='uploading';entry.error='';onProgress(entries);
  const fd=new FormData();fd.set('file',entry.file);fd.set('reason',reason||'补充佐证材料');fd.set('expected_version',String(current));
  try{await api('/attachments/'+kind+'/'+id,{method:'POST',body:fd});entry.status='done';current+=['assessment','org_assessment','sync_task'].includes(kind)?0:1}
  catch(error){
   entry.status='failed';entry.error=String(error?.message||'上传没有完成').split('\n')[0];
   if(latest){
    try{const fresh=await latest();current=fresh.version;const sha=await fileDigest(entry.file);
     if(sha&&(fresh.attachments||[]).some(a=>a.sha256===sha&&a.name===entry.name)){entry.status='done';entry.error=''}}
    catch{}
   }
  }
  onProgress(entries);
 }
 return {version:current,entries,failed:failedEntries(entries)};
}

// 共用材料表单：保留已上传结果，再次提交只重试失败文件；重新选文件则按最新附件数校验。
export function materialUploadForm(c,{kind,id,title,intro='',contextLabel='',latest,after}){
 let entries=null;
 const max=kind==='qualification'?20:MAX_ATTACHMENTS;
 return c.formModal(title,intro+c.field('file','材料文件（可一次选择多张图片或多份文件）','file','',{multiple:true,accept:'.pdf,.png,.jpg,.jpeg',full:true,hint:'支持照片或扫描件，单个最大 10 兆字节。电脑可按住控制键多选，手机可在相册勾选多张。'})+'<div id="upload-progress" class="form-field full"></div>'+c.field('reason','材料说明','textarea','补充申请材料',{full:true}),async(v,f)=>{
  const chosen=Array.from(f.querySelector('#f-file').files||[]);
  if(!chosen.length)throw Error('请选择要上传的材料，可一次选择多份。');
  const fresh=await latest(),selected=chosen.map(file=>entries?.find(entry=>entry.file===file)||uploadEntries([file])[0]);
  checkUploadFiles(failedEntries(selected).map(entry=>entry.file),(fresh.attachments||[]).length,{max});
  entries=selected;
  const box=f.querySelector('#upload-progress');
  const result=await uploadSequential({api:c.api,kind,id,version:fresh.version,entries,reason:v.reason,latest,onProgress:list=>{if(box)box.innerHTML=uploadStatusHtml(list,c.esc)}});
  if(result.failed.length)throw Error('已上传 '+(entries.length-result.failed.length)+' 份，另有 '+result.failed.length+' 份未完成。请查看每份结果，再次点击“上传材料”只补传失败文件；已上传的不会重复上传。');
  c.closeModal();c.toast('已上传 '+entries.length+' 份材料');await after();
 },{submit:'上传材料',returnTo:after,contextLabel,stepper:false,hint:'支持一次多选，确认后逐份上传；选好文件后不会立即上传。'});
}

// 批量办理＝前端按勾选顺序逐条调用现有单条接口。每条单独请求、单独留痕，失败条目附原因，不混进成功。
export async function runBatch(items,perform,onProgress=()=>{}){
 const ok=[],failed=[];
 for(const [index,item] of items.entries()){
  try{const result=await perform(item,index);ok.push({item,result})}
  catch(error){failed.push({item,error:String(error?.message||'办理没有完成').split('\n')[0]})}
  onProgress({done:index+1,total:items.length,ok,failed});
 }
 return {ok,failed};
}

// 同一业务、同一环节才允许一起办理；环节不同或混入其他业务一律拒绝，不替审核人猜。
export function batchStage(items,stageOf){
 if(!items.length)throw Error('请先勾选要办理的事项');
 const stages=new Set(items.map(x=>x.type+'|'+stageOf(x)));
 if(stages.size>1)throw Error('只能同时办理同一业务、同一审批环节的事项，请按环节分开勾选');
 const stage=stageOf(items[0]);if(!stage)throw Error('所选事项当前不在可批量办理的环节');
 return stage;
}

// 连续办理队列：记住打开详情时列表里的顺序，只提供“下一条”的位置，不代为办理。
export function nextCode(queue,current){
 if(!queue?.codes?.length)return '';
 const at=queue.codes.indexOf(current);
 return at>=0&&at<queue.codes.length-1?queue.codes[at+1]:'';
}

// 可批量的环节：积分认定按状态分审核与归档（归档沿用原入账逻辑）；教师考核分确认与归档。本人事项一律不可勾选。
export const CLAIM_BATCH={'待院长初审':'approve','待归口复审':'approve','待分管副校长审批':'approve','待教学秘书归档':'archive'};
export const ASSESSMENT_BATCH={DEPARTMENT:'confirm',COLLEGE:'confirm',SCHOOL:'confirm',READY:'archive'};
export const BATCH_LABELS={confirm:'批量确认',approve:'批量审核',archive:'批量归档'};
export function batchMode(item,meId){
 if(!item?.teacher_id||item.teacher_id===meId)return '';
 if(item.type==='social_claim'&&item.title==='社会培训积分认定')return CLAIM_BATCH[item.state]||'';
 if(item.type==='assessment'&&item.title!=='本人考核确认')return ASSESSMENT_BATCH[item.state]||'';
 return '';
}
// 每条先重新读取最新数据和版本：本人事项、环节已变化、未解决核对或来源变化直接列为未办理；
// 其余交给原单条接口，后端照常校验职责、回避、版本和来源，每条各自留痕。
export function batchPerformer({api,meId,mode,reason,basis='',total}){
 return async(x,i)=>{
  const note=(basis?basis+'；':'')+'批量办理第'+(i+1)+'/'+total+'条';
  if(x.type==='social_claim'){
   const d=await api('/social/objects/social_claim/'+x.id),it=d.item;
   if(it.teacher_id===meId)throw Error('本人申报按回避规定须由其他人员办理');
   if(d.state_label!==x.state)throw Error('办理环节已变化（当前：'+d.state_label+'），请单独打开核对');
   await api('/social/claims/'+x.id+'/actions',{method:'POST',body:{action:'approve',expected_version:it.version,reason,basis:note}});
   return d.state_label;
  }
  if(x.type==='assessment'){
   const d=await api('/assessments/'+x.id),it=d.assessment;
   if(it.teacher_id===meId)throw Error('本人考核按回避规定须由其他人员办理');
   if(it.state!==x.state)throw Error('办理环节已变化，请单独打开核对');
   if(d.confirmation_blockers?.count)throw Error('有 '+d.confirmation_blockers.count+' 项数据核对尚未完成');
   if(d.open_point_reviews)throw Error('该教师有积分核对尚未办结');
   if(d.source_changes?.changed)throw Error('计算依据已变化，请单独打开重新核对');
   await api('/assessments/'+x.id+'/actions',{method:'POST',body:{action:mode==='archive'?'archive':'confirm',expected_version:it.version,reason,basis:note}});
   return it.state;
  }
  throw Error('该类事项不支持批量办理');
 };
}
