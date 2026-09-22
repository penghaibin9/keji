/* Approved integration-first visual language. Pure presentation; no fixtures or writes. */
const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const connectorInfo = Object.freeze({
 sso:{page:'sso',title:'学校统一认证',short:'统一认证',symbol:'shield',color:'blue',direction:'学校账号 → 本平台',description:'使用学校已有账号，关联本人、组织和权限。',owner:'学校信息中心 / 统一认证系统厂商',needed:'认证协议、测试入口、应用登记、身份与组织字段、回调与退出约定。',boundary:'实际登录适配器仍需按学校协议开发与联调。登记地址、保存映射或本地校验均不等于单点登录已经接通。'},
 middle:{page:'hub',title:'学校数据中台',short:'数据中台',symbol:'data',color:'teal',direction:'学校数据 → 本平台',description:'接入教师、项目、课程、培训收入和课程人次。',owner:'学校信息中心 / 数据中台及源系统责任人',needed:'接口清单、字段字典、脱敏样本、数据唯一编号、更新与冲正规则、分页/游标和同步频率。',boundary:'目前内部确认入库支持教师人事、项目和课程；收入/人次自动入站和真实分页协议仍待适配，不用本地有表冒充已接通。'},
 province:{page:'province',title:'湘培直通车',short:'湘培直通车',symbol:'sync',color:'purple',direction:'业务数据 → 省级平台',description:'按省级规范同步业务，保存逐笔结果和失败记录。',owner:'学校业务部门 / 省级平台接口责任单位',needed:'省级接口规范、授权条件、字段字典、11类数据来源、幂等/重试约定、脱敏报文及联调窗口。',boundary:'培训计划、学习过程、结业结果、证书仍需确认权威来源；省级真实适配器与回执联调未完成，教师资质证书不能替代学员结业证书。'}
});
export function connectorStatus(state) {
 if(state === 'CONNECTED') return {text:'连接证明有效',kind:'good'};
 if(state === 'NOT_CONNECTED') return {text:'待对接',kind:'pending'};
 return {text:'状态未获取',kind:'unknown'};
}
export function connectorCards(items,{actionable=false,icon=()=>'',compact=false,restricted=false}={}) {
 return `<div class="connector-grid ${compact?'compact':''}">${Object.entries(connectorInfo).map(([code,m])=>{
  const item=items?.find(x=>(x.connection?.code||x.code)===code);
  const status=connectorStatus(item?.connection?.state||item?.connection_state);
  const latest=item?.latest_task;
  return `<article class="connector-card ${m.color}"><span class="connector-icon">${icon(m.symbol)}</span><div class="grow"><div class="connector-title"><h3>${escape(m.title)}</h3>${restricted?'<span class="connector-status unknown">学校统一管理</span>':`<span class="connector-status ${status.kind}">${status.text}</span>`}</div><p>${escape(compact?m.direction:m.description)}</p>${!compact&&latest?`<p class="connector-latest">最近业务记录：成功 ${escape(latest.success_count??0)} / 失败 ${escape(latest.failed_count??0)} / 待确认 ${escape(latest.pending_confirmation_count??0)}</p>`:''}${!compact&&!restricted&&!item?'<p>尚未取得该连接配置，不能判断为已接通。</p>':''}</div>${actionable?`<button type="button" class="btn text" data-action="nav" data-id="${m.page}" aria-label="管理${escape(m.title)}">${icon('chevron')}</button>`:''}</article>`;
 }).join('')}</div>`;
}
export function incomeChart(trend) {
 const rows=(Array.isArray(trend)?trend:[]).map(x=>({month:String(x.month??''),income:x.income===null||x.income===''||x.income===undefined||typeof x.income==='boolean'?NaN:Number(x.income)}));
 if(!rows.length) return '<div class="empty"><h3>暂无收入趋势</h3><p>接入或核对业务数据后，按业务月份展示；不填入示例金额。</p></div>';
 if(rows.some(x=>!Number.isFinite(x.income))) return '<div class="info-banner warn">收入数据格式异常，请联系管理员核对；未用零值替代。</div>';
 const width=740,height=240,left=62,right=22,top=18,bottom=36;
 let min=Math.min(0,...rows.map(x=>x.income)),max=Math.max(0,...rows.map(x=>x.income));
 if(min===max)max=min+1;
 const Y=v=>top+(max-v)/(max-min)*(height-top-bottom);
 const X=i=>rows.length===1?(width+left-right)/2:left+i/(rows.length-1)*(width-left-right);
 const coords=rows.map((r,i)=>`${X(i).toFixed(2)},${Y(r.income).toFixed(2)}`);
 const fmt=v=>Math.abs(v)>=10000?(v/10000).toLocaleString('zh-CN',{maximumFractionDigits:1})+'万':v.toLocaleString('zh-CN',{maximumFractionDigits:0});
 const ticks=Array.from({length:5},(_,i)=>min+(max-min)*i/4);
 return `<div class="income-chart"><svg viewBox="0 0 ${width} ${height}" role="img" aria-label="培训收入月度趋势，含负向更正；详细金额见下方表格"><title>培训收入趋势（元）</title>${ticks.map(v=>`<line x1="${left}" x2="${width-right}" y1="${Y(v)}" y2="${Y(v)}" class="grid-line"/><text x="${left-10}" y="${Y(v)+4}" text-anchor="end">${escape(fmt(v))}</text>`).join('')}<line x1="${left}" x2="${width-right}" y1="${Y(0)}" y2="${Y(0)}" class="zero-line"/><polygon class="trend-area" points="${X(0)},${Y(0)} ${coords.join(' ')} ${X(rows.length-1)},${Y(0)}"/><polyline class="trend-line" points="${coords.join(' ')}"/>${rows.map((r,i)=>`<circle cx="${X(i)}" cy="${Y(r.income)}" r="3.5" class="trend-dot"><title>${escape(r.month)}：${escape(r.income.toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2}))} 元</title></circle>${rows.length<=12||i%Math.ceil(rows.length/12)===0||i===rows.length-1?`<text x="${X(i)}" y="${height-9}" text-anchor="middle">${escape(r.month)}</text>`:''}`).join('')}</svg><details class="chart-data"><summary>查看精确月度金额</summary><table><thead><tr><th>业务月份</th><th>收入（元）</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${escape(r.month)}</td><td>${escape(r.income.toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2}))}</td></tr>`).join('')}</tbody></table></details></div>`;
}
export function guideCards({icon=()=>''}={}) {
 return `<div class="guide-grid">${Object.entries(connectorInfo).map(([code,m])=>`<article class="card guide-card"><div class="card-head"><span class="connector-icon ${m.color}">${icon(m.symbol)}</span><h2>${escape(m.title)}</h2></div><div class="card-pad"><div class="guide-step"><b>1</b><div><h3>先找谁</h3><p>${escape(m.owner)}</p></div></div><div class="guide-step"><b>2</b><div><h3>向对方要什么</h3><p>${escape(m.needed)}</p></div></div><div class="guide-step"><b>3</b><div><h3>技术人员来做</h3><p>核对协议与字段 → 开发或安装适配器 → 验证权限、异常和重复提交 → 取得联调记录 → 明确启用。</p></div></div><div class="guide-step"><b>4</b><div><h3>怎样才算接通</h3><p>${code==='sso'?'真实学校账号完成登录、身份与范围校验、退出及异常测试。':code==='middle'?'真实脱敏样本拉取、预览、确认入库及重复/失败恢复均通过，数量与来源对得上。':'省级平台返回可核验的逐笔回执；失败重试、补传与重复识别按双方约定通过。'}</p></div></div><p class="guide-boundary">${escape(m.boundary)}</p><button class="btn" type="button" data-action="nav" data-id="${m.page}">进入${escape(m.short)}</button></div></article>`).join('')}</div>`;
}
export function scopedDateFilters(filter,period) {
 // Intersect explicit dates with the selected period, never replace a narrower filter.
 const out={...filter};
 if(period){
  const start=period.start_date||period.start||period.starts; const end=period.end_date||period.end||period.ends;
  if(start&&(!out.start||out.start<start))out.start=start;
  if(end&&(!out.end||out.end>end))out.end=end;
 }
 return out;
}
