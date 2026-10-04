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
// 7.3/7.4/7.6 dashboard charts. Same inline-SVG language as incomeChart; no external libraries.
const finite = v => v !== null && v !== '' && v !== undefined && typeof v !== 'boolean' && Number.isFinite(Number(v));
const fmtNumber = (v, digits = 0) => Number(v).toLocaleString('zh-CN', {minimumFractionDigits: digits, maximumFractionDigits: digits});
export const RANK_METRICS = Object.freeze([
 {key:'income',label:'收入',unit:'元',digits:2},{key:'participants',label:'人次',unit:'人次',digits:0},
 {key:'teachers',label:'参与教师',unit:'人',digits:0},{key:'assessment_average',label:'考核均分',unit:'分',digits:2}]);
export function rankRows(colleges, metric = 'income') {
 // Colleges without a value for the metric (e.g. no assessment yet) stay listed last, never as zero.
 const rows = (Array.isArray(colleges) ? colleges : []).map(x => ({...x, value: finite(x[metric]) ? Number(x[metric]) : null}));
 return rows.sort((a, b) => (b.value ?? -Infinity) - (a.value ?? -Infinity) || String(a.name).localeCompare(String(b.name), 'zh-CN'));
}
export function percentChange(value) {
 if (!finite(value)) return '—';
 const n = Number(value);
 return (n > 0 ? '+' : '') + fmtNumber(n, 2) + '%';
}
export function barChart(rows, {unit = '', digits = 0, label = '数量', empty = '暂无数据'} = {}) {
 const list = (Array.isArray(rows) ? rows : []).map(x => ({name: String(x.name ?? x.label ?? ''), value: finite(x.value ?? x.count) ? Number(x.value ?? x.count) : null}));
 if (!list.length) return `<div class="empty"><h3>${escape(empty)}</h3></div>`;
 const max = Math.max(1, ...list.map(x => Math.abs(x.value ?? 0)));
 const width = 740, row = 30, left = 150, right = 90, height = list.length * row + 12;
 return `<div class="income-chart bar-chart"><svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escape(label)}条形图；精确数值见下方表格"><title>${escape(label)}</title>${list.map((x, i) => {
  const y = 6 + i * row, w = x.value === null ? 0 : Math.abs(x.value) / max * (width - left - right);
  return `<text x="${left - 10}" y="${y + 18}" text-anchor="end">${escape(x.name.length > 12 ? x.name.slice(0, 12) + '…' : x.name)}</text><rect x="${left}" y="${y + 6}" width="${w.toFixed(2)}" height="16" rx="3" class="bar-fill"><title>${escape(x.name)}：${x.value === null ? '无数据' : escape(fmtNumber(x.value, digits))} ${escape(unit)}</title></rect><text x="${(left + w + 6).toFixed(2)}" y="${y + 18}">${x.value === null ? '—' : escape(fmtNumber(x.value, digits))}</text>`;
 }).join('')}</svg><details class="chart-data"><summary>查看精确数值</summary><table><thead><tr><th>项目</th><th>${escape(label)}${unit ? '（' + escape(unit) + '）' : ''}</th></tr></thead><tbody>${list.map(x => `<tr><td>${escape(x.name)}</td><td>${x.value === null ? '—' : escape(fmtNumber(x.value, digits))}</td></tr>`).join('')}</tbody></table></details></div>`;
}
export function incomeParticipantsChart(trend) {
 // Dual series: income line (left axis, 元) and participants bars (right axis, 人次).
 const base = incomeChart(trend);
 const source = Array.isArray(trend) ? trend : [];
 if (!source.length || !base.includes('<svg')) return base;
 if (source.some(x => !finite(x.participants))) return base;
 const rows = source.map(x => ({month: String(x.month ?? ''), income: Number(x.income), participants: Number(x.participants)}));
 const width = 740, height = 250, left = 62, right = 62, top = 18, bottom = 36;
 let min = Math.min(0, ...rows.map(x => x.income)), max = Math.max(0, ...rows.map(x => x.income));
 if (min === max) max = min + 1;
 const pMax = Math.max(1, ...rows.map(x => x.participants));
 const Y = v => top + (max - v) / (max - min) * (height - top - bottom);
 const P = v => (height - bottom) - Math.max(0, v) / pMax * (height - top - bottom);
 const slot = (width - left - right) / rows.length, X = i => left + slot * (i + 0.5);
 const coords = rows.map((r, i) => `${X(i).toFixed(2)},${Y(r.income).toFixed(2)}`);
 const short = v => Math.abs(v) >= 10000 ? (v / 10000).toLocaleString('zh-CN', {maximumFractionDigits: 1}) + '万' : v.toLocaleString('zh-CN', {maximumFractionDigits: 0});
 const ticks = Array.from({length: 5}, (_, i) => min + (max - min) * i / 4);
 return `<div class="income-chart dual-chart"><div class="chart-legend"><span class="legend-line">培训收入（元，左轴）</span><span class="legend-bar">课程人次（右轴）</span></div><svg viewBox="0 0 ${width} ${height}" role="img" aria-label="培训收入与课程人次月度对比；详细数值见下方表格"><title>培训收入与课程人次趋势</title>${ticks.map(v => `<line x1="${left}" x2="${width - right}" y1="${Y(v)}" y2="${Y(v)}" class="grid-line"/><text x="${left - 10}" y="${Y(v) + 4}" text-anchor="end">${escape(short(v))}</text>`).join('')}${[0, 0.5, 1].map(f => `<text x="${width - right + 8}" y="${P(pMax * f) + 4}">${escape(fmtNumber(pMax * f))}</text>`).join('')}${rows.map((r, i) => `<rect x="${(X(i) - Math.min(18, slot * 0.3)).toFixed(2)}" y="${P(r.participants).toFixed(2)}" width="${Math.min(36, slot * 0.6).toFixed(2)}" height="${((height - bottom) - P(r.participants)).toFixed(2)}" class="bar-fill participants-bar"><title>${escape(r.month)}：${escape(fmtNumber(r.participants))} 人次</title></rect>`).join('')}<line x1="${left}" x2="${width - right}" y1="${Y(0)}" y2="${Y(0)}" class="zero-line"/><polyline class="trend-line" points="${coords.join(' ')}"/>${rows.map((r, i) => `<circle cx="${X(i)}" cy="${Y(r.income)}" r="3.5" class="trend-dot"><title>${escape(r.month)}：${escape(fmtNumber(r.income, 2))} 元</title></circle>${rows.length <= 12 || i % Math.ceil(rows.length / 12) === 0 || i === rows.length - 1 ? `<text x="${X(i)}" y="${height - 9}" text-anchor="middle">${escape(r.month)}</text>` : ''}`).join('')}</svg><details class="chart-data"><summary>查看精确月度数值</summary><table><thead><tr><th>业务月份</th><th>收入（元）</th><th>课程人次</th></tr></thead><tbody>${rows.map(r => `<tr><td>${escape(r.month)}</td><td>${escape(fmtNumber(r.income, 2))}</td><td>${escape(fmtNumber(r.participants))}</td></tr>`).join('')}</tbody></table></details></div>`;
}
export function syncStatusChart(items) {
 // Per connection: business records succeeded / failed / waiting confirmation from latest_task.
 const rows = (Array.isArray(items) ? items : []).map(x => ({name: String(x.name ?? x.code ?? ''), t: x.latest_task}));
 if (!rows.length) return '<div class="empty"><h3>暂无接口状态</h3></div>';
 const width = 740, row = 30, left = 150, right = 120, height = rows.length * row + 12;
 const total = r => r.t ? Number(r.t.success_count || 0) + Number(r.t.failed_count || 0) + Number(r.t.pending_confirmation_count || 0) : 0;
 const max = Math.max(1, ...rows.map(total));
 return `<div class="income-chart bar-chart"><div class="chart-legend"><span class="legend-ok">成功</span><span class="legend-fail">失败</span><span class="legend-wait">待确认</span></div><svg viewBox="0 0 ${width} ${height}" role="img" aria-label="各接口最近任务成功、失败、待确认记录数"><title>同步状态</title>${rows.map((r, i) => {
  const y = 6 + i * row, scale = v => Number(v || 0) / max * (width - left - right);
  if (!r.t) return `<text x="${left - 10}" y="${y + 18}" text-anchor="end">${escape(r.name)}</text><text x="${left}" y="${y + 18}">尚无任务</text>`;
  const ok = scale(r.t.success_count), bad = scale(r.t.failed_count), wait = scale(r.t.pending_confirmation_count);
  return `<text x="${left - 10}" y="${y + 18}" text-anchor="end">${escape(r.name)}</text><rect x="${left}" y="${y + 6}" width="${ok.toFixed(2)}" height="16" class="bar-ok"/><rect x="${(left + ok).toFixed(2)}" y="${y + 6}" width="${bad.toFixed(2)}" height="16" class="bar-fail"/><rect x="${(left + ok + bad).toFixed(2)}" y="${y + 6}" width="${wait.toFixed(2)}" height="16" class="bar-wait"/><text x="${(left + ok + bad + wait + 6).toFixed(2)}" y="${y + 18}">${escape(fmtNumber(r.t.success_count || 0))} / ${escape(fmtNumber(r.t.failed_count || 0))} / ${escape(fmtNumber(r.t.pending_confirmation_count || 0))}</text>`;
 }).join('')}</svg></div>`;
}
