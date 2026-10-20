/* 学院原始报送资料展示；所有数值和筛选选项均来自同一个后端结果。 */
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=v=>v===null||v===undefined?'未提供':Number(v).toLocaleString('zh-CN',{maximumFractionDigits:2});
const colors=['#2477f5','#60a8fa','#3cc5ee','#45d6d9','#10b9bb','#8bdaa0','#9aabf4','#7793b1'];
const option=(v,l,s)=>`<option value="${esc(v)}"${String(v)===String(s)?' selected':''}>${esc(l)}</option>`;
const quantity=items=>items.length?items.map(x=>`${num(x.value)} <span>${esc(x.unit)}</span>`).join(' / '):'<span class="sc-muted">未提供</span>';
const ledgerLink=ledger=>ledger?`<span>已导入 · 第${num(ledger.version_no)}版 · ${esc(ledger.review_state)}${ledger.is_latest?'':'（历史版本）'}</span><br><a href="${esc('#ledgers?'+new URLSearchParams({year:String(ledger.year),ledger_id:ledger.id}))}">查看台账</a>`:'<span class="sc-muted">待导入台账</span>';

export function renderSchoolCockpit(d,{icon,schoolName='湖南科技职业学院',local=false}={}){
 const previewLabel=local?'本地验证 · ':'';
 const t=d.totals,p=d.period,years=d.periods.map(x=>x.year),old=years.filter(y=>y!==p.year);
 const hasTimes=t.person_times_colleges>0,hasDays=t.person_days!==null;
 const title=!t.colleges?'本期报送资料':hasTimes?(d.college?'本学院报送人次':`${t.person_times_colleges===5?'五':num(t.person_times_colleges)+'个'}学院报送人次`):hasDays?'本学院报送人天':'本期项目记录';
 const value=!t.colleges?null:hasTimes?t.person_times:hasDays?t.person_days:t.records,unit=!t.colleges?'':hasTimes?'人次':hasDays?'人天':'条';
 const dayColleges=d.details.filter(x=>x.unit==='人天').map(x=>x.college),dayName=[...new Set(dayColleges)];
 const secondary=[...(!hasTimes&&hasDays?[['报送人次',t.person_times,'人次','file','sc-sources','人次']]:[[(dayName.length===1?dayName[0]+'报送人天':'报送人天'),t.person_days,'人天','file','sc-sources','人天']]),['本期项目记录',t.colleges?t.records:null,'条','file','sc-sources',''],['已报送学院',t.colleges,'个','school','sc-colleges','']];
 const heads=new Map(),detailLinks=d.details.map(x=>{if(x.numbered)heads.set(x.college,x.row);const row=heads.get(x.college);return x.ledger&&row?`#projects?${new URLSearchParams({project_view:'history',history_year:String(p.year),history_ledger:x.ledger.id,history_row:String(row)})}`:null});
 const sourceUnits=[...new Set(d.details.map(x=>x.unit))];
 const collegeButtons=d.rank.map(x=>`<button type="button" data-sc-college="${esc(x.name)}" aria-label="按培训规模筛选${esc(x.name)}">${esc(x.name)}</button>`).join('');
 const button=(text,target)=>`<button type="button" class="sc-text-button" data-sc-open="${target}">${text}${icon('arrow')}</button>`;
 const selectedNote=d.project?'已筛选单条项目；年度对照保留所选学院的完整报送期间。':d.college?`当前学院：${d.college}`:'人次、人天分别统计。';
 return `<article class="sc-cockpit" aria-label="管理驾驶舱"><header class="sc-header"><div class="sc-brand">${schoolName==='湖南科技职业学院'?'<img src="/assets/assets/school-brand-header.png" alt="湖南科技职业学院" width="570" height="98">':`<strong>${esc(schoolName)}</strong>`}</div><h1>管理驾驶舱</h1><div class="sc-period"><strong>${esc(p.label)}已报资料</strong><span>${previewLabel}学院原表报送值 · 待学校核定</span></div><div class="sc-header-tools"><span>资料读取日期：${new Date(d.read_at).toLocaleDateString('zh-CN',{timeZone:'Asia/Shanghai'})}</span><div><button type="button" data-sc-refresh>刷新原表数据</button><button type="button" data-action="nav" data-id="home">返回工作台</button></div></div></header>
 <form id="sc-filters" class="sc-filters" aria-label="学校资料筛选"><label>${icon('filter')}学院<select name="report_college" aria-label="学院">${option('','全部学院',d.college)}${d.colleges.map(x=>option(x,x,d.college)).join('')}</select></label><label class="sc-unmapped">${icon('users')}教研室<select aria-label="教研室" disabled><option>待关联</option></select></label><label>${icon('file')}项目<select name="report_project" aria-label="项目">${option('','全部记录',d.project)}${d.projects.map(x=>option(x.id,x.name,d.project)).join('')}</select></label><label class="sc-unmapped">${icon('book')}课程<select aria-label="课程" disabled><option>待关联</option></select></label><label class="sc-period-filter">${icon('clock')}<span class="sr-only">资料期间</span><select name="report_year" aria-label="资料期间">${d.periods.map(x=>option(x.year,`${x.start.replaceAll('-','.')} — ${x.end.replaceAll('-','.')}`,p.year)).join('')}</select></label><button class="sc-query" type="submit">查询</button><button class="sc-reset" type="reset">重置</button></form>
 <div class="sc-body"><section class="sc-overview"><div class="sc-summary"><div class="sc-headline"><div class="sc-metric-label">${icon('users')}<h2>${esc(title)}</h2><button type="button" class="sc-help" data-sc-open="sc-method" aria-label="查看统计口径">${icon('help')}</button></div><button type="button" class="sc-value-link" data-sc-open="sc-sources" data-sc-unit="${unit==='条'?'':unit}" aria-label="查看${esc(title)}来源明细"${value===null?' disabled':''}><span class="sc-main-value">${num(value)}<small>${unit}</small></span><span class="sc-action-hint">${value===null?'暂无本期明细':'点击查看来源明细 '+icon('arrow')}</span></button><p>${t.colleges?'明细汇总，待学校核定':'当前学院尚未提供本期资料'}</p></div><div class="sc-secondary"><p>${esc(selectedNote)}</p><div class="sc-secondary-metrics">${secondary.map(([l,v,u,i,target,filterUnit])=>`<button type="button" data-sc-open="${target}" data-sc-unit="${filterUnit}" aria-label="查看${esc(l)}明细"${v===null?' disabled':''}>${icon(i)}<span>${esc(l)}</span><strong>${num(v)}<small>${v===null?'':u}</small></strong></button>`).join('')}</div></div></div><figure class="sc-photo"><button type="button" class="sc-photo-open" data-sc-photo-open aria-label="放大查看学校培训现场照片"><img src="/assets/assets/training-cockpit.jpg" alt="智能装备技术学院汽车工程师启蒙培训现场，学校原始资料照片" width="420" height="315"><span>放大照片 · 查看相关资料 ${icon('arrow')}</span></button><figcaption><strong>学校资料照片 · 车轮上的梦想，汽车工程师启蒙</strong><span>智能装备技术学院 · 2026.05.22</span></figcaption></figure></section>
 <section class="sc-analysis" aria-label="报送资料图表"><div class="sc-panel sc-rank"><p class="sc-interaction-hint">悬停看数值，点击图形筛选学院</p><div class="sc-section-title"><h2>${icon('chart')}学院培训规模 <small>（按报送人次）</small></h2><span>单位：人次</span></div>${d.rank.length?'<canvas data-sc-chart="rank" role="img" aria-label="学院报送人次条形图，悬停查看数值，点击图形联动筛选"></canvas>':'<div class="sc-chart-empty">本期资料无可比较的人次数据</div>'}${collegeButtons?`<details class="sc-chart-actions"><summary>按学院筛选</summary><div>${collegeButtons}</div></details>`:''}<p class="sc-chart-note">${t.person_days!==null?'注：人天单列，不参与人次排行。':'原表折算量与人次分别列示，未换算合并。'}</p></div><div class="sc-panel sc-records"><div class="sc-section-title"><h2>${icon('file')}项目记录构成与年度对比</h2></div><div class="sc-record-analysis"><div class="sc-composition"><div class="sc-section-title sc-subtitle"><h3>本期项目记录（按学院）</h3><span>单位：条</span></div><div class="sc-donut-content"><canvas data-sc-chart="donut" role="img" aria-label="本期项目记录构成，悬停查看数值，点击扇区或右侧学院筛选"></canvas><ul>${d.composition.map((x,i)=>`<li><button type="button" data-sc-college="${esc(x.name)}" aria-label="按项目记录筛选${esc(x.name)}" aria-pressed="${d.college===x.name}"><i style="background:${colors[i%colors.length]}"></i><span>${esc(x.name)}</span><strong>${num(x.value)}<small>条</small></strong></button></li>`).join('')}</ul></div></div><div class="sc-year-chart"><div class="sc-subtitle"><h3>年度资料对比</h3><p>非同期资料对照，不计算同比</p></div><canvas data-sc-chart="years" role="img" aria-label="各年度原表项目记录数，精确数值见来源对比表"></canvas><div class="sc-year-actions">${d.comparison.map(x=>`<button type="button" data-sc-year="${x.year}" aria-pressed="${x.year===p.year}" aria-label="查看${x.year}年资料">${x.year}年</button>`).join('')}</div></div></div></div></section>
 <section class="sc-panel sc-comparison" id="sc-colleges" tabindex="-1"><div class="sc-section-title"><h2>${icon('file')}学院项目记录对比</h2>${button('查看来源明细','sc-sources')}</div><div class="sc-table-wrap" tabindex="0" role="region" aria-label="可左右滚动查看完整表格"><table class="sc-table"><thead><tr><th>学院</th>${old.map(y=>`<th>${esc(d.periods.find(x=>x.year===y).label)}记录（条）</th>`).join('')}<th>${esc(p.label)}记录（条）</th><th>本期报送量</th><th>资料状态</th><th>系统台账</th></tr></thead><tbody>${d.table.map(r=>`<tr><th scope="row"><button type="button" data-sc-college="${esc(r.college)}">${esc(r.college)}</button></th>${old.map(y=>`<td>${num(r.records[y])}</td>`).join('')}<td>${num(r.selected_records)}</td><td>${quantity(r.quantities)}</td><td class="sc-source-state">${esc(r.status)}</td><td>${r.selected_records===null?'未提供':ledgerLink(r.ledger)}</td></tr>`).join('')}</tbody></table></div>${d.project?'<p class="sc-chart-note">本期记录与报送量按所选项目筛选；其他年度列保留学院原表期间。</p>':''}</section>
 <footer class="sc-status-strip"><span>${icon('wallet')}<b>培训收入</b><small>原表未提供</small></span><span>${icon('users')}<b>教师参与</b><small>待关联</small></span><span>${icon('book')}<b>课程／班级</b><small>待补充</small></span><span>${icon('assess')}<b>考核结果</b><small>待接入</small></span><span>${icon('sync')}<b>省级平台</b><small>详见实际回执</small></span>${button('查看口径','sc-method')}</footer>
 <details class="sc-detail-panel" id="sc-method"><summary>统计口径与原表核对说明</summary><p>${esc(d.note)}</p><p>${esc(d.comparison_note)}</p><p>本屏按原表资料期间筛选，不把缺少完整日期的项目按天拆分。教研室、课程、教师及财务数据未关联到原表时，不参与本屏筛选和累计。</p>${d.warnings.map(w=>`<p><strong>${esc(w.college)}：</strong>${esc(w.text)}</p>`).join('')}${d.excluded.map(x=>`<p><strong>${esc(x.college)}：</strong>${esc(x.file)}，${esc(x.reason)}。</p>`).join('')}<p>学校核定值在学院台账核定页面办理；本屏读取原表；系统台账按学院、年度和同一原件匹配。台账推荐值与核定值在对应台账中查看，不替换本屏原表值。</p></details>
 <details class="sc-detail-panel" id="sc-sources"><summary>来源明细 · ${num(t.records)}条编号项目记录，${num(d.details.length)}行原表明细</summary><div class="sc-source-units" role="group" aria-label="按原表单位查看来源"><button type="button" data-sc-source-unit="" aria-pressed="true">全部明细</button>${sourceUnits.map(u=>`<button type="button" data-sc-source-unit="${esc(u)}" aria-pressed="false">${esc(u)}</button>`).join('')}</div><p id="sc-source-filter-label" aria-live="polite">点击项目名称查看历史日期、依据和待核事项。</p><div class="sc-table-wrap" tabindex="0" role="region" aria-label="可左右滚动查看完整表格"><table class="sc-table"><thead><tr><th>学院</th><th>项目名称</th><th>报送值</th><th>原表文件</th><th>来源位置</th><th>原表状态</th><th>系统台账</th></tr></thead><tbody>${d.details.map((x,i)=>`<tr data-sc-source-row data-sc-row-unit="${esc(x.unit)}"><th scope="row">${esc(x.college)}</th><td>${detailLinks[i]?`<a href="${esc(detailLinks[i])}">${esc(x.name)}</a>`:esc(x.name)}${x.numbered?'':'（原表续行，查看所属编号项目）'}</td><td>${num(x.value)} ${esc(x.unit)}</td><td>${esc(x.file)}</td><td>第${num(x.row)}行 · ${esc(x.cell)}</td><td>${esc(x.status)}</td><td>${ledgerLink(x.ledger)}</td></tr>`).join('')}</tbody></table></div></details><dialog class="sc-photo-viewer" aria-labelledby="sc-photo-title"><div class="sc-photo-toolbar"><h2 id="sc-photo-title">车轮上的梦想 · 汽车工程师启蒙</h2><button type="button" data-sc-photo-close aria-label="关闭照片" autofocus>关闭</button></div><img src="/assets/assets/training-cockpit.jpg" alt="学校原始资料中的汽车工程师启蒙培训现场"><p>智能装备技术学院 · 2026年5月22日。原始资料照片，不代表当前筛选项目均发生在该日。</p><button type="button" class="sc-query" data-sc-photo-source>查看该学院2026年资料</button></dialog></div></article>`;
}

export function bindSchoolCockpit(root,data,onFilter,{sourceUnit='',onSourceUnit=()=>{}}={}){
 const form=root.querySelector('#sc-filters');if(!form)return;
 const values=()=>Object.fromEntries(new FormData(form));
 form.addEventListener('submit',event=>{event.preventDefault();onFilter(values())});
 form.addEventListener('reset',event=>{event.preventDefault();onFilter({})});
 form.elements.report_college.addEventListener('change',()=>{const v=values();v.report_project='';onFilter(v)});
 form.elements.report_year.addEventListener('change',()=>{const v=values();v.report_project='';onFilter(v)});
 form.elements.report_project.addEventListener('change',()=>onFilter(values()));
 root.querySelector('[data-sc-refresh]')?.addEventListener('click',()=>onFilter(values()));
 root.querySelectorAll('[data-sc-college]').forEach(button=>button.addEventListener('click',()=>onFilter({...values(),report_college:button.dataset.scCollege,report_project:''})));
 root.querySelectorAll('[data-sc-year]').forEach(button=>button.addEventListener('click',()=>onFilter({...values(),report_year:button.dataset.scYear,report_project:''})));
 const filterSources=(unit,remember=true)=>{
  let count=0;root.querySelectorAll('[data-sc-source-row]').forEach(row=>{row.hidden=!!unit&&row.dataset.scRowUnit!==unit;if(!row.hidden)count++});
  root.querySelectorAll('[data-sc-source-unit]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.scSourceUnit===unit)));
  if(remember)onSourceUnit(unit||'all');
  const label=root.querySelector('#sc-source-filter-label');if(label)label.textContent=`当前显示：${unit||'全部单位'} · ${count}行明细。点击项目名称查看日期、依据和待核事项。`;
 };
 if(sourceUnit==='all'||data.details.some(x=>x.unit===sourceUnit)){filterSources(sourceUnit==='all'?'':sourceUnit,false);const panel=root.querySelector('#sc-sources');if(panel)panel.open=true;}
 root.querySelectorAll('[data-sc-source-unit]').forEach(button=>button.addEventListener('click',()=>filterSources(button.dataset.scSourceUnit)));
 root.querySelectorAll('[data-sc-open]').forEach(button=>button.addEventListener('click',()=>{
  const panel=root.querySelector('#'+button.dataset.scOpen);if(!panel)return;
  if(button.dataset.scOpen==='sc-sources')filterSources(button.dataset.scUnit||'');
  if(panel.tagName==='DETAILS')panel.open=true;
  panel.scrollIntoView({behavior:window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches?'auto':'smooth',block:'start'});
 }));
 const photo=root.querySelector('.sc-photo-viewer'),photoButton=root.querySelector('[data-sc-photo-open]');
 photoButton?.addEventListener('click',()=>photo.showModal());
 root.querySelector('[data-sc-photo-close]')?.addEventListener('click',()=>photo.close());
 photo?.addEventListener('close',()=>photoButton.focus());
 photo?.addEventListener('click',event=>{if(event.target===photo){const r=photo.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)photo.close()}});
 root.querySelector('[data-sc-photo-source]')?.addEventListener('click',()=>{photo.close();onFilter({report_year:'2026',report_college:'智能装备技术学院',report_project:''})});
 root.querySelectorAll('[data-sc-chart]').forEach(canvas=>{
  const panel=canvas.closest('.sc-panel'),tip=document.createElement('div');tip.className='sc-chart-tooltip';tip.hidden=true;tip.setAttribute('role','tooltip');panel.append(tip);
  let regions=[],hovered=-1,progress=window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches?1:0;
  const draw=()=>{regions=drawSchoolChart(canvas,data,hovered,progress)};draw();
  const locate=event=>{const r=canvas.getBoundingClientRect();return chartRegionAt(regions,(event.clientX-r.left)*canvas.clientWidth/r.width,(event.clientY-r.top)*canvas.clientHeight/r.height)};
  canvas.addEventListener('pointermove',event=>{
   const found=locate(event),index=regions.indexOf(found);if(index!==hovered){hovered=index;draw()}
   tip.hidden=!found;canvas.style.cursor=found?'pointer':'';
   if(found){tip.textContent=found.label+' · 点击查看资料';const r=panel.getBoundingClientRect();tip.style.left=Math.max(8,Math.min(event.clientX-r.left+12,panel.clientWidth-238))+'px';tip.style.top=Math.max(8,Math.min(event.clientY-r.top+12,panel.clientHeight-tip.offsetHeight-8))+'px'}
  });
  canvas.addEventListener('pointerleave',()=>{hovered=-1;tip.hidden=true;canvas.style.cursor='';draw()});
  canvas.addEventListener('click',event=>{const found=locate(event);if(found)onFilter({...values(),...found.filter,report_project:''})});
  if(progress<1){const start=performance.now();const animate=now=>{if(!canvas.isConnected)return;progress=Math.min(1,(now-start)/320);draw();if(progress<1)requestAnimationFrame(animate)};requestAnimationFrame(animate)}
  if(typeof ResizeObserver!=='undefined'){const observer=new ResizeObserver(()=>{if(!canvas.isConnected){observer.disconnect();return}draw()});observer.observe(canvas)}
 });
}

export function chartRegionAt(regions,x,y){
 return regions.find(r=>{
  if(r.shape==='arc'){const radius=Math.hypot(x-r.cx,y-r.cy),angle=(Math.atan2(y-r.cy,x-r.cx)+Math.PI/2+2*Math.PI)%(2*Math.PI);return radius>=r.inner&&radius<=r.outer&&angle>=r.start&&angle<r.end}
  return x>=r.x&&x<=r.x+r.width&&y>=r.y&&y<=r.y+r.height;
 });
}

export function drawSchoolChart(canvas,d,hovered=-1,progress=1){
 const width=canvas.clientWidth,height=canvas.clientHeight,regions=[];if(!width||!height)return regions;
 const ratio=window.devicePixelRatio||1;canvas.width=width*ratio;canvas.height=height*ratio;
 const c=canvas.getContext('2d');if(!c)return regions;c.scale(ratio,ratio);c.font='14px "Microsoft YaHei", sans-serif';c.fillStyle='#113675';
 const text=(s,x,y,align='left',bold=false,size=14)=>{c.textAlign=align;c.font=`${bold?'600 ':''}${size}px "Microsoft YaHei", sans-serif`;c.fillStyle='#143774';c.fillText(s,x,y)};
 const grid=(x1,x2,y)=>{c.beginPath();c.strokeStyle='#e2edfc';c.setLineDash([3,3]);c.moveTo(x1,y);c.lineTo(x2,y);c.stroke();c.setLineDash([])};
 const kind=canvas.dataset.scChart;
 if(kind==='donut'){
  const total=d.totals.records,cx=width/2,cy=height/2,r=Math.min(width,height)*.42,thick=r*.38;
  if(!total){text('暂无项目记录',cx,cy,'center');return regions}
  let a=-Math.PI/2;d.composition.forEach(x=>{const b=a+x.value/total*Math.PI*2;if(x.value>0){const i=regions.length;c.beginPath();c.strokeStyle=colors[i%colors.length];c.globalAlpha=hovered<0||hovered===i?1:.35;c.lineWidth=thick+(hovered===i?3:0);const finish=a+(b-a)*progress;if(finish-a>.016){c.arc(cx,cy,r-thick/2,a+.008,finish-.008);c.stroke()}regions.push({shape:'arc',cx,cy,inner:r-thick,outer:r,start:a+Math.PI/2,end:b+Math.PI/2,filter:{report_college:x.name},label:`${x.name}：${num(x.value)}条，占本期${(Number(x.value)/total*100).toFixed(1)}%`})}a=b});
  c.globalAlpha=1;text(num(total),cx,cy+7,'center',true,35);text('本期项目记录',cx,cy+29,'center',false,12);return regions;
 }
 if(kind==='rank'){
  const left=Math.min(155,Math.max(125,width*.32)),right=70,top=15,bottom=25,plot=width-left-right,rows=d.rank;
  const max=Math.max(1,...rows.map(x=>Number(x.value))),step=Math.pow(10,Math.floor(Math.log10(max))),limit=Math.ceil(max*1.1/step)*step;
  const ticks=width<400?2:5;
  for(let i=0;i<=ticks;i++){const x=left+plot*i/ticks;c.beginPath();c.strokeStyle='#e2edfc';c.moveTo(x,top);c.lineTo(x,height-bottom);c.stroke();text(num(limit*i/ticks),x,height-5,'center',false,11)}
  const slot=(height-top-bottom)/rows.length;rows.forEach((x,i)=>{const y=top+slot*(i+.5),w=x.value===null?0:Number(x.value)/limit*plot;text(x.name,left-12,y+5,'right',false,13);c.fillStyle=hovered===i?'#004ccb':'#368cf7';c.globalAlpha=hovered<0||hovered===i?1:.45;c.fillRect(left,y-9,w*progress,18);c.globalAlpha=1;text(num(x.value),left+w+10,y+5,'left',true,14);regions.push({shape:'rect',x:0,y:top+slot*i,width,height:slot,filter:{report_college:x.name},label:`${x.name}：${num(x.value)}${x.value===null?'':'人次'}，人天不混入`})});return regions;
 }
 const rows=d.comparison,left=30,compact=(width-40)/rows.length<100,bottom=compact?58:42,top=25,plot=height-top-bottom,max=Math.max(1,...rows.map(x=>x.records||0)),limit=Math.ceil(max/10)*10;
 for(let i=0;i<=3;i++){const y=height-bottom-plot*i/3;grid(left,width-10,y);text(num(limit*i/3),left-8,y+4,'right',false,11)}
 rows.forEach((x,i)=>{const slot=(width-left-10)/rows.length,cx=left+slot*(i+.5),w=Math.min(74,slot*.55),h=(x.records||0)/limit*plot;c.fillStyle=hovered===i?'#004ccb':x.year===d.period.year?'#2679f6':'#a6cdfc';c.fillRect(cx-w/2,height-bottom-h*progress,w,h*progress);text(num(x.records),cx,height-bottom-h-7,'center',true,16);if(compact){text(`${x.year}年`,cx,height-39,'center',false,11);text(x.label.replace(`${x.year}年`,''),cx,height-23,'center',false,11);text(`${x.colleges}个学院`,cx,height-7,'center',false,11)}else{text(x.label,cx,height-23,'center',false,11);text(`（${x.colleges}个学院）`,cx,height-6,'center',false,11)}regions.push({shape:'rect',x:left+slot*i,y:top,width:slot,height:height-top,filter:{report_year:String(x.year)},label:`${x.label}：${num(x.records)}条，${x.colleges}个学院；非同期，不算同比`})});
 return regions;
}
