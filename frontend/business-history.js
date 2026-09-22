// Business snapshots are presented with an explicit field list, never raw data keys.
const escapeHtml=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fields={
 qualification:[['name','证书名称'],['category','资质类别'],['certificate_no','证书编号'],['issuer','发证机构'],['obtained','取得日期'],['expires','有效期至'],['state','留存时状态']],
 record:[['project','培训项目'],['project_code','项目编号'],['course','课程名称'],['course_code','课程编号'],['class_name','班级名称'],['class_code','班级编号'],['event_date','培训日期'],['hours','授课学时'],['participants','课程人次'],['income','归属培训收入'],['source','数据来源'],['external_key','来源业务编号'],['state','留存时状态']]
};
const equal=(a,b)=>String(a??'')===String(b??'');
function display(key,value,labels){
 if(key==='expires'&&!value)return '长期有效';
 if(value===null||value===undefined||value==='')return '未填写';
 if(key==='state')return labels[value]||'状态待核实';
 if(['hours','participants','income'].includes(key))return Number(value).toLocaleString('zh-CN',{maximumFractionDigits:2})+({hours:' 学时',participants:' 人次',income:' 元'}[key]);
 return String(value);
}
export function renderBusinessHistory(kind,revisions,{labels={},formatTime=String,attachmentButton=()=>''}={}){
 if(!revisions?.length)return '<p class="muted small mt12">暂无历史版本</p>';
 const ordered=[...revisions].sort((a,b)=>Number(a.version)-Number(b.version));
 return ordered.map((revision,index)=>{
  const data=revision.data||{},previous=index?ordered[index-1].data||{}:null;
  const rows=(fields[kind]||[]).filter(([key])=>Object.hasOwn(data,key));
  const changed=previous?(fields[kind]||[]).filter(([key])=>(Object.hasOwn(data,key)||Object.hasOwn(previous,key))&&!equal(data[key],previous[key])):[];
  const attachments=revision.attachment_ids||data.attachment_ids||[];
  const previousAttachments=index?(ordered[index-1].attachment_ids||previous.attachment_ids||[]):[];
  const attachmentChanged=previous&&[...attachments].sort().join('|')!==[...previousAttachments].sort().join('|');
  const changes=changed.map(([key,label])=>`<div class="history-change"><strong>${escapeHtml(label)}</strong><span>${escapeHtml(display(key,previous[key],labels))}</span><span aria-hidden="true">→</span><span>${escapeHtml(display(key,data[key],labels))}</span></div>`).join('')+(attachmentChanged?`<div class="history-change"><strong>佐证材料</strong><span>原 ${previousAttachments.length} 份</span><span aria-hidden="true">→</span><span>本版 ${attachments.length} 份${attachments.length===previousAttachments.length?'（材料已变更）':''}</span></div>`:'');
  return `<details class="business-history mt12"><summary>第 ${escapeHtml(revision.version)} 版 · ${escapeHtml(revision.reason||'版本留存')}</summary><div class="business-history-body">${revision.created_at?`<p class="muted small">留存时间：${escapeHtml(formatTime(revision.created_at))}</p>`:''}<h4>本次变化</h4>${changes||`<p class="muted small">${previous?'本版业务字段未变化，办理情况请查看流转记录。':'首次留存的业务信息。'}</p>`}<h4>本版业务信息</h4><dl class="kv">${rows.map(([key,label])=>`<dt>${escapeHtml(label)}</dt><dd>${escapeHtml(display(key,data[key],labels))}</dd>`).join('')}</dl>${kind==='qualification'?`<h4>本版佐证材料（${attachments.length} 份）</h4>${attachments.map((id,i)=>attachmentButton(id,i)).join('')||'<p class="muted small">本版未留存附件</p>'}`:''}</div></details>`;
 }).join('');
}
