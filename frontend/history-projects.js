// 历史来源直接使用已报送台账，不用缺失资料拼造普通项目。
const kindNames={actual:'实际培训日期',planned:'计划安排日期',news:'报道日期',source:'原材料记载日期'};
const issueNames={all:'全部来源',missing:'资料待完善',conflict:'有冲突待核对',prefill:'日期预填待核'};
const shown=(c,value)=>value==null||value===''?'待确认':c.esc(value);
function historyHref(c,extra={}){
 const values={project_view:'history',history_year:c.filter?.history_year,history_issue:c.filter?.history_issue,history_page:c.filter?.history_page,...extra};
 return '#projects?'+new URLSearchParams(Object.entries(values).filter(([,v])=>v!=null&&v!==''));
}
export function projectViewTabs(c,active){
 return '<div class="ledger-years" role="group" aria-label="培训项目资料范围"><a class="btn '+(active==='history'?'primary':'')+'" href="'+c.esc(historyHref(c))+'">学校历史资料</a><a class="btn '+(active==='business'?'primary':'')+'" href="'+c.esc(historyHref(c,{project_view:'business'}))+'">项目业务办理</a></div>';
}
function facts(c,pairs){return c.table(['核对事项','来源事实'],pairs.map(([label,value])=>[c.esc(label),value]))}
function evidence(c,value,attachments=[]){
 const parts=String(value||'').split('；'),file=parts[0].split(/[\\/]/).at(-1).replace(/\b[a-f0-9]{64}\b/gi,'').trim(),location=parts.find(x=>/^\s*位置[:：]/.test(x))?.replace(/^\s*位置[:：]\s*/,'');
 const fingerprint=parts.find(x=>/^\s*文件指纹[:：]/.test(x))?.match(/\b[a-f0-9]{64}\b/i)?.[0],attachment=attachments.find(a=>fingerprint&&a.sha256?.toLowerCase()===fingerprint.toLowerCase());
 const action=!attachment?'':attachment.mime?.startsWith('image/')?'<div class="material-list mt8"><button type="button" class="btn sm" data-action="attachment-preview" data-id="'+c.esc(attachment.id)+'" data-material-name="'+c.esc(attachment.name)+'" aria-label="查看原图 '+c.esc(file)+'">查看原图</button></div>':c.act('下载依据','attachment-download',attachment.id,'sm');
 return c.esc([file||'原件依据',location].filter(Boolean).join(' · '))+action;
}
function historyNoteText(value){
 const raw=String(value??'');
 if(!/^\s*\{/.test(raw)||!/(?:evidence_id|relative_path|sha256)/.test(raw))return raw;
 let data;try{data=JSON.parse(raw)}catch{}
 // 兼容旧整理记录中的字典文本，只提取业务文字，不执行文本内容。
 const field=name=>{
  if(typeof data?.[name]==='string')return data[name];
  if(typeof data?.source?.[name]==='string')return data.source[name];
  const match=new RegExp("'"+name+"'\\s*:\\s*'((?:\\\\.|[^'\\\\])*)'").exec(raw);
  return match?match[1].replace(/\\(['"\\])/g,'$1').replace(/\\n/g,' '):'';
 };
 const note=field('note')||'此项原材料记载仍需核对。',file=field('relative_path').split(/[\\/]/).at(-1),location=field('location');
 return note+(file?'（依据：'+[file,location].filter(Boolean).join(' · ')+'）':'');
}
export function historyDateSummary(c,h={}){
 const p=h.date_prefill,start=p?.start_date||h.confirmed_start,end=p?.end_date||h.confirmed_end;
 if(!start&&!end)return '<span class="muted">日期待补</span>';
 return '<span class="history-date-value">'+shown(c,start)+'</span>'+(end&&end!==start?'<br><span class="history-date-value">至 '+c.esc(end)+'</span>':'')+'<div class="mt8"><span class="badge orange-b">'+(p?'历史预填 · 待学校复核':'原件期间 · 待学校复核')+'</span></div>';
}
function prefillPanel(c,p,attachments){
 if(!p)return '';
 return '<section class="history-date-prefill mt16"><h3>历史日期预填</h3>'+historyDateSummary(c,{date_prefill:p})+'<p class="mt8">'+c.esc(p.text)+'</p><div class="mt8"><strong>原件依据：</strong>'+evidence(c,p.evidence,attachments)+'</div><p class="hint">这是历史整理建议，尚未经学校复核，不代表已备案、已结项或已认定积分。</p></section>';
}
export async function historyProjectsPage(c){
 const ledger=c.filter?.history_ledger,row=c.filter?.history_row;
 if(ledger&&row){
  const d=await c.api('/social/history-projects/'+encodeURIComponent(ledger)+'/'+encodeURIComponent(row)),h=d.history,o=h.owner,attachments=d.can_read_files?d.attachments:[];
  const back=historyHref(c,{history_year:d.year}),ledgerHref='#ledgers?'+new URLSearchParams({year:String(d.year),source:'school',ledger_id:d.ledger_id});
  return '<section class="social-workspace history-projects">'+c.pageHead('历史项目资料核对，不代表已备案、已结项或已认定积分。','<a class="btn" href="'+c.esc(back)+'">返回历史清单</a>')+projectViewTabs(c,'history')+
   '<section class="card mt16 card-pad"><h2>'+c.esc(d.name)+'</h2><p>'+c.esc(d.college)+' · '+d.year+' 年 · 原序号 '+c.esc(d.sequence)+' · '+c.esc(d.status)+'</p>'+prefillPanel(c,h.date_prefill,attachments)+facts(c,[['负责人姓名',shown(c,o.name)],['材料记载角色',shown(c,o.role)],['姓名与角色依据',o.evidence?evidence(c,o.evidence):shown(c,null)],['负责人账号',o.account_id?'已按材料关联':'待关联，不以录入账号代替'],['原件记载实际开始',shown(c,h.confirmed_start)],['原件记载实际结束',shown(c,h.confirmed_end)],['原表文件',c.esc(d.source_file)],['原表位置',c.esc(d.source_rows.map(n=>'第 '+n+' 行').join('、'))]])+'</section>'+
   '<section class="card mt16 card-pad"><h2>日期事实与性质</h2>'+c.table(['日期性质','来源记载与核对说明','记载开始','记载结束','依据'],h.date_facts.map(f=>[c.esc(kindNames[f.kind]||'待核实'),c.esc(f.text),shown(c,f.start_date),shown(c,f.end_date),evidence(c,f.evidence,attachments)]), '尚无可确认的日期事实')+'<p class="hint">计划安排、新闻报道和原材料记载分别保留，不能代替已确认的实际培训日期。</p></section>'+
   '<section class="card mt16 card-pad"><h2>待补与冲突</h2>'+[...h.conflicts.map(v=>c.note('冲突：'+historyNoteText(v),true)),...d.missing.map(v=>c.note(historyNoteText(v)))].join('')+(!h.conflicts.length&&!d.missing.length?'<p>已关联本次确认资料。</p>':'')+'</section>'+
   '<section class="card mt16 card-pad"><h2>项目专属材料</h2>'+(d.can_read_files?c.downloads(d.attachments):c.note('当前账号未授权读取材料文件。'))+'<p class="hint">这里只关联本项目已核对材料，学院整表仍在来源台账按原权限查阅。</p></section>'+
   '<section class="card mt16 card-pad"><h2>来源与已有项目</h2>'+c.table(['原表行','原项目名称','原报送值','人数原文','课时','材料原文'],d.rows.map(r=>[r.row_no,c.esc(r.name),shown(c,r.claimed_raw||r.claimed),shown(c,r.people_raw),shown(c,r.hours),shown(c,r.materials)]))+'<a class="btn" href="'+c.esc(ledgerHref)+'">查看来源台账</a>'+(d.project_id?c.act('查看已关联项目','social-detail','social_project|'+d.project_id):'<p class="hint">尚未关联普通业务项目，不以缺失资料自动建档。</p>')+'</section></section>';
 }
 const values={issue:c.filter?.history_issue||'all'};if(c.filter?.history_year)values.year=c.filter.history_year;
 if(c.filter?.history_page)values.page=c.filter.history_page;
 const d=await c.api('/social/history-projects?'+new URLSearchParams(values));
 const links=(entries,key)=>entries.map(([value,label])=>'<a class="btn '+(String(key==='history_year'?d.year:d.issue)===String(value)?'primary':'')+'" href="'+c.esc(historyHref(c,{history_year:d.year,[key]:value,history_page:null}))+'">'+c.esc(label)+'</a>').join('');
 const page=d.page||1,pages=Math.max(1,Math.ceil((d.total??d.items.length)/(d.size||200)));
 const paging='<nav class="ledger-years" aria-label="历史资料分页"><span>共 '+(d.total??d.items.length)+' 条 · 第 '+page+' / '+pages+' 页</span>'+[[page-1,'上一页'],[page+1,'下一页']].filter(([n])=>n>=1&&n<=pages).map(([n,label])=>'<a class="btn" href="'+c.esc(historyHref(c,{history_year:d.year,history_page:n}))+'">'+label+'</a>').join('')+'</nav>';
 const rows=d.items.map(x=>[c.esc(x.college),c.esc(x.sequence),'<strong>'+c.esc(x.name)+'</strong><p class="cell-sub">原表 '+c.esc(x.source_rows.map(n=>'第'+n+'行').join('、'))+'</p>',shown(c,x.history.owner.name),historyDateSummary(c,x.history),x.materials_count?c.esc(x.materials_count+'份已关联'):'待关联',c.esc(x.status),'<a class="btn sm" href="'+c.esc(historyHref(c,{history_year:d.year,history_ledger:x.ledger_id,history_row:x.row_no}))+'">查看资料</a>']);
 return '<section class="social-workspace history-projects">'+c.pageHead('按学校原始台账整理历史培训资料，未知事实保留待确认。','')+projectViewTabs(c,'history')+
  '<div class="ledger-years" role="group" aria-label="历史资料年度">'+links(d.years.map(y=>[y,y+' 年']),'history_year')+'</div><div class="ledger-years" role="group" aria-label="历史资料问题">'+links(Object.entries(issueNames),'history_issue')+'</div>'+c.note(d.note)+
  '<section class="summary-row mt16">'+[['编号来源',d.counts.all],['待完善',d.counts.missing],['有冲突',d.counts.conflict],['日期预填待核',d.date_prefill_count??0]].map(([label,value])=>'<div class="summary-item"><label>'+label+'</label><strong>'+value+'<small>条</small></strong></div>').join('')+'</section>'+
  '<section class="card mt16 card-pad history-project-list"><h2>'+d.year+' 年学校历史资料</h2>'+c.table(['学院','原序号','项目来源','负责人姓名','历史日期（待核）','专属材料','资料状态','查看'],rows,'所选分类暂无历史来源资料')+paging+'</section></section>';
}
