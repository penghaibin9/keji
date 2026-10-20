// 学院台账报送与口径检查、首页五项指标、课程视频分钟资源。
// 推荐值按系统推荐口径计算，学校书面确认前只用于核对。
import {mineSchoolData} from './school-data.js?v=20261019-merge1&display=20261019-clean2';
import {historyDateSummary} from './history-projects.js?v=20261019-walk3&display=20261019-clean2&history_dates=20261020-images1';
let year = new Date().getFullYear();
let sourceView = 'school';
let sourceYear = null;
let openId = null;      // 正在核定的台账；为空时显示各学院列表
let rowFilter = 'all';  // 详情页行筛选：all / issues / serious
let tab = 'ledgers';    // 列表页：ledgers 各学院台账 / targets 年度目标与考核速算
let draft = {};        // 核定时已填但未保存的值，切换筛选时不丢
let lastPreview = null;
let lastFile = null;
let previewSequence = 0;

const LEVEL_TONE = {严重: 'red-b', 注意: 'orange-b', 提示: 'blue-b'};
const FILTERS = [['all', '全部行'], ['issues', '有问题的行'], ['serious', '严重问题']];

// 人次最多两位小数，整数不补 .00
const fmt = v => Number(v || 0).toLocaleString('zh-CN', {maximumFractionDigits: 2});
const reportedText = (c, items = []) => items.length ? items.map(x => `<div>${x.value == null ? '未提供' : fmt(x.value)} ${c.esc(x.unit)}</div>`).join('') : '未提供';
const reportedStats = (c, items = []) => items.length ? items.map(x => stat(c, '原表报送 · ' + x.unit, x.value == null ? '未提供' : fmt(x.value), x.value == null ? '' : x.unit, '保留原表单位，不跨单位相加')).join('') : stat(c, '原表报送量', '未提供', '');
const needsUnitReview = items => items?.some(x => x.unit !== '人次') || false;
const unitReviewNote = '以下试算量与当前核对量按各行口径核对，不作为原表人次统计；原表报送量仍按人次、人天、原表折算量分别列示。';

function issueList(c, issues) {
  if (!issues?.length) return '<span class="green small">未发现问题</span>';
  return issues.map(i => `<div class="ledger-issue"><span class="badge ${LEVEL_TONE[i.level] || 'blue-b'}">${c.esc(i.level)}</span> ${c.esc(i.text)}</div>`).join('');
}

const serious = r => r.issues?.some(i => i.level === '严重');

function yearTabs(c, periods = []) {
  const now = new Date().getFullYear();
  const years = sourceView === 'school' && periods.length ? periods.map(p => p.year) : [now - 1, now];
  return `<div class="ledger-years" role="group" aria-label="选择年度">${years.map(y => `<button type="button" class="btn ${y === year ? 'primary' : ''}" data-action="tz-year" data-id="${y}" aria-pressed="${y === year}">${y} 年</button>`).join('')}</div>`;
}

function stat(c, label, value, unit, hint, tone = '') {
  return `<div class="summary-item ${tone}"><label>${c.esc(label)}</label><strong>${value}<small>${c.esc(unit)}</small></strong>${hint ? `<p class="cell-sub">${c.esc(hint)}</p>` : ''}</div>`;
}

// 学院台账由学院报送、学校核定；教研室负责人只看本教研室平均积分，教师在“个人培训”看分给本人的人次。
const ledgerTabsFor = c => c.me?.role?.kind === 'dept' ? [['depts', '教研室平均积分']] : [['ledgers', c.me?.role?.kind === 'college' ? '本院台账' : '各学院台账'], ['targets', '年度目标与考核速算'], ['depts', '教研室平均积分']];

function pageTabs(c) {
  const tabs = ledgerTabsFor(c);
  if (tabs.length < 2) return '';
  return `<div class="ledger-tabs" role="tablist">${tabs.map(([k, l]) => `<button type="button" role="tab" class="tab ${tab === k ? 'active' : ''}" aria-selected="${tab === k}" data-action="tz-tab" data-id="${k}">${l}</button>`).join('')}</div>`;
}

export async function ledgerPage(c) {
  if (c.filter) sourceView = c.filter.source === 'other' ? 'other' : 'school';
  const invalidSource = c.filter?.source && !['school','other'].includes(c.filter.source);
  if (invalidSource || (c.filter && !c.filter.year)) sourceYear = null;
  else if (c.filter?.year && /^(20\d{2}|2100)$/.test(c.filter.year)) year = sourceYear = Number(c.filter.year);
  if (c.filter && (c.filter.ledger_id || null) !== openId) { resetLedgerView(); openId = c.filter.ledger_id || null; }
  if (c.filter) {
    tab = c.filter.ledger_tab || 'ledgers';
    rowFilter = FILTERS.some(([key]) => key === c.filter.ledger_filter) ? c.filter.ledger_filter : 'all';
  }
  if (!ledgerTabsFor(c).some(([k]) => k === tab)) tab = ledgerTabsFor(c)[0][0];
  if (openId && c.me?.role?.kind === 'dept') openId = null;
  if (openId) return detailPage(c, openId);
  if (tab === 'targets') return targetsPage(c);
  if (tab === 'depts') return deptsPage(c);
  const requestedYear = sourceView === 'school' ? sourceYear : year;
  const d = await c.api('/social/ledgers?' + new URLSearchParams({...(requestedYear == null ? {} : {year: String(requestedYear)}), source: sourceView}));
  if (d.year != null) year = sourceYear = d.year;
  const periodLabel = d.source === 'school' ? d.source_periods?.find(p => p.year === year)?.label || `${year} 年` : `${year} 年`;
  const schoolYear = d.source_periods?.some(p => p.year === year) ? year : d.source_periods?.at(-1)?.year || year;
  const college = c.me?.role?.kind === 'college', reported = d.items.length > 0;
  const unitReview = needsUnitReview(d.reported_quantities);
  const mixedUnits = (d.reported_quantities?.length || 0) > 1;
  const figures = d.items.some(x => x.school_figure);
  const sum = key => d.items.reduce((n, x) => n + Number(x.totals[key] || 0), 0);
  const badRows = d.items.reduce((n, x) => n + Number(x.data.summary?.serious || 0), 0);
  const waiting = d.items.filter(x => x.totals.pending_rows).length;
  // 有严重问题、还没核定的学院排前面，先处理
  const items = [...d.items].sort((a, b) => (b.totals.pending_rows ? 1 : 0) - (a.totals.pending_rows ? 1 : 0) || (b.data.summary?.serious || 0) - (a.data.summary?.serious || 0));
  const rows = items.map(x => {
    const go = d.can_review && x.totals.pending_rows;
    return [
      `<strong>${c.esc(x.org_name)}</strong><div class="cell-sub">第 ${x.data.version_no} 版 · ${c.esc(x.data.template_label)}</div>`,
      reportedText(c, x.reported_quantities), fmt(x.totals.recommended_total),
      `<strong>${fmt(x.totals.final_total)}</strong>${x.totals.pending_rows ? `<div class="cell-sub">含 ${x.totals.pending_rows} 行待核定推荐值</div>` : ''}`,
      ...(figures ? [x.school_figure ? `${fmt(x.school_figure.value)}<div class="cell-sub ${needsUnitReview(x.reported_quantities) ? '' : Number(x.school_figure.diff) ? 'ledger-cut' : 'green'}">${needsUnitReview(x.reported_quantities) ? '按各行口径核对，不计算跨单位差额' : Number(x.school_figure.diff) ? '相差 ' + fmt(x.school_figure.diff) : '一致'}</div>` : '<span class="muted">未登记</span>'] : []),
      x.data.summary?.serious ? `<span class="badge red-b">${x.data.summary.serious} 行严重</span>` : '<span class="badge green-b">无严重问题</span>',
      `<span class="badge ${x.totals.state === '已核定' ? 'green-b' : x.totals.state === '部分核定' ? 'orange-b' : 'blue-b'}">${c.esc(x.totals.state)}</span>`,
      `<button type="button" class="btn ${go ? 'primary' : ''} sm" data-action="tz-detail" data-id="${c.esc(x.id)}">${go ? '去核定' : '查看'}</button>`];
  });
  return c.pageHead(college ? '报送本院年度统计表，核对系统检查结果和学校核定进度。' : '学院报来的《社会培训人次统计表》在这里上传。系统按制度复算每一行，标出口径问题，继续教育学院逐行核定。',
      (d.can_submit ? c.act('上传学院统计表', 'tz-upload', '', 'primary', 'plus') : ''))
    + pageTabs(c) + yearTabs(c, d.source_periods)
    + (d.source_catalog_available ? `<div class="ledger-years" role="group" aria-label="台账资料来源">${[['school','学校原始台账'],['other','其他台账（含测试）']].map(([value,label]) => `<a class="btn ${sourceView === value ? 'primary' : ''}" href="${c.esc('#ledgers?' + new URLSearchParams({year: String(value === 'school' ? schoolYear : year), source: value}))}" aria-current="${sourceView === value ? 'page' : 'false'}">${label}</a>`).join('')}</div>` : '')
    + (d.source_note ? `<div class="info-banner">${c.icon('help')}<div>${c.esc(d.source_note)}${c.me?.role?.kind === 'school' ? ` <a href="#cockpit?report_year=${year}">管理驾驶舱</a>` : ''}</div></div>` : '')
    + `<section class="summary-row ledger-stats mt16">${stat(c, '已报送学院', d.items.length, '个', !reported ? (d.missing.length ? '本年度尚未报送' : '暂无应报送学院或台账') : d.missing.length ? (d.source === 'school' ? d.missing.length + ' 个学院待补资料或待导入' : '还有 ' + d.missing.length + ' 个学院没报') : '应报学院都已报送', d.missing.length ? 'warn' : '')}${reportedStats(c, d.reported_quantities)}${stat(c, unitReview ? '推荐试算量' : '按推荐口径', mixedUnits ? '按行查看' : fmt(sum('recommended_total')), unitReview ? '' : '人次', mixedUnits ? '人次、人天及折算量不合并，请查看各学院或逐行口径' : unitReview ? '按各行口径核对，不作为原表人次统计' : '系统按制度复算，待学校确认')}${stat(c, unitReview ? '当前核对量' : !reported ? '当前汇总人次' : waiting ? '当前汇总（含待核定）' : '核定人次', reported ? mixedUnits ? '分单位核对' : fmt(sum('final_total')) : '—', unitReview ? '' : '人次', !reported ? '尚未报送，暂无核定结果' : mixedUnits ? '各学院与项目行分别核对，不形成跨单位合计' : waiting ? waiting + ' 个学院待核定' : '全部核定', waiting ? 'warn' : '')}${stat(c, '有严重问题的行', badRows, '行', '漏除 8、浏览量当人数、分配超总数等', badRows ? 'bad' : '')}</section>`
    + (unitReview ? c.note(unitReviewNote, false, '单位与核对口径') : '') + c.note(d.note, false, '统计口径')
    + (d.missing.length ? c.note((d.source === 'school' ? '学校原表待补／待导入：' : '还没报送：') + d.missing.map(m => m.org_name + (m.source_status ? '（' + m.source_status + '）' : '')).join('、'), true) : '')
    + (d.online?.projects ? c.note(`线上影响力：${d.online.projects} 个线上项目，约 ${fmt(d.online.views)} 次浏览/观看。没有实名签到和结业，不计人次，单独登记。`) : '')
    + `<div class="card mt16"><div class="card-head"><div><h2>${c.esc(periodLabel)}${college ? '本院' : '各学院'}台账</h2></div></div>${c.table(['学院', '原表报送量（分单位）', unitReview ? '推荐试算量' : '推荐口径', unitReview ? '当前核对量' : '当前汇总', ...(figures ? [unitReview ? '学校人工核对数' : '学校人工核定'] : []), '口径问题', '状态', ''], rows, college ? '本院本年度尚未报送统计表' : '这一年还没有学院报送', d.can_submit ? '选择学院统计表，先检查再确认报送。' : '等待有报送权限的人员上传统计表。')}</div>`;
}

function previewHtml(c, r, fileName) {
  const s = r.summary;
  const unitReview = needsUnitReview(r.reported_quantities);
  return `<section class="ledger-preview mt16"><div class="detail-action-context"><strong>已检查文件</strong><p>${c.esc(fileName)}</p></div><dl class="kv"><dt>识别到的学院</dt><dd>${c.esc(r.meta.college || '未识别')}</dd><dt>年度</dt><dd>${c.esc(r.meta.year || '未识别')}</dd><dt>表格版本</dt><dd>${c.esc(r.template_label)}</dd><dt>负责人 / 经办人</dt><dd>${c.esc(r.meta.leader || '—')} / ${c.esc(r.meta.handler || '—')}</dd></dl>`
    + `<div class="summary-row mt16">${stat(c, '项目行数', s.rows, '行')}${reportedStats(c, r.reported_quantities)}${stat(c, unitReview ? '推荐试算量' : '按推荐口径', fmt(s.recommended_total), unitReview ? '' : '人次')}${stat(c, '严重问题', s.serious, '行', '', s.serious ? 'bad' : '')}</div>`
    + `<form id="ledger-submit-form" class="form-grid mt16">${c.field('org_id', '报送学院', 'select', r.suggested_org_id || '', {options: [['', '请选择学院'], ...r.colleges.map(o => [o.id, o.name])]})}${c.field('year', '统计年度', 'number', r.meta.year || year, {min: 2020, max: 2100})}${c.field('reason', '报送说明', 'textarea', '学院报送' + (r.meta.year || year) + '年社会培训人次统计表', {full: true})}</form>`
    + (unitReview ? c.note(unitReviewNote) : '') + r.notes.map(n => c.note(n, true)).join('') + c.note(r.note)
    + rowsTable(c, r.rows, false) + '</section>';
}

// 列尽量少，核定值和理由放在同一格，一屏看完不横向滚动
function rowsTable(c, rows, review, ledger = null) {
  const unitReview = needsUnitReview(ledger?.reported_quantities);
  const historical = r => !ledger || !r.history ? '' : `<div class="mt8">${historyDateSummary(c,r.history)}<a class="btn sm mt8" href="${c.esc('#projects?' + new URLSearchParams({project_view:'history',history_year:String(ledger.data.year),history_ledger:ledger.id,history_row:String(r.row_no)}))}">查看历史项目资料与依据</a></div>`;
  const bindings = r => !ledger?.can_draft ? '' : `<div class="mt8">${(r.allocations || []).map((a, i) => `<div class="cell-sub">${c.esc(a.name)}：${c.esc(a.binding_status || '待确认人员')}${!a.teacher_id ? c.act('确认人员', 'tz-bind-person', `${ledger.id}|${r.row_no}|${i}`) : ''}</div>`).join('')}${!r.project_id ? c.act(r.project_link_status === 'pending' ? '核对原项目或新建' : '关联已有项目', 'tz-bind-project', `${ledger.id}|${r.row_no}`) + c.act('确认负责人', 'tz-bind-owner', `${ledger.id}|${r.row_no}`) : ''}</div>`;
  return `<div class="ledger-rows">` + c.table(['行', '培训项目', '原表报送量', '推荐值（系统怎么算）', '发现的问题', ...(review ? ['核定值 / 理由'] : ledger ? ['项目核定值 / 理由'] : [])], rows.map(r => [
    `${r.row_no}${serious(r) ? '<span class="ledger-flag" title="有严重问题"></span>' : ''}`,
    `<strong>${c.esc(r.name)}</strong>${historical(r)}${r.allocation ? `<div class="cell-sub">原填分配：${c.esc(r.allocation)}</div>` : ''}${r.project_code ? `<div class="mt8"><span class="badge green-b">已关联 ${c.esc(r.project_code)}</span>${r.project_id ? c.act('查看项目', 'social-detail', 'social_project|' + r.project_id, 'sm') : ''}</div>` : ''}${bindings(r)}`,
    `<strong>${c.esc(r.claimed_raw !== '' && r.claimed_raw != null ? r.claimed_raw : r.claimed ?? '—')}</strong><div class="cell-sub">${c.esc(r.people_raw !== '' && r.people_raw != null ? r.people_raw : r.people ?? '—')} 人 · ${c.esc(r.hours ?? '—')} 课时</div>`,
    `<strong>${fmt(r.recommended)}</strong><div class="cell-sub">${c.esc(r.mode || '')}${r.basis ? ' · ' + c.esc(r.basis) : ''}</div>`,
    issueList(c, r.issues),
    ...(review ? [`<div class="ledger-decide"><input class="ledger-approved" type="number" min="0" step="0.01" data-row="${r.row_no}" data-recommended="${c.esc(r.recommended)}" aria-label="第 ${r.row_no} 行核定值" value="${c.esc(draft[r.row_no]?.approved ?? r.approved ?? '')}" placeholder="推荐 ${c.esc(r.recommended)}"><input class="ledger-reason" type="text" maxlength="500" data-row="${r.row_no}" aria-label="第 ${r.row_no} 行核定理由" value="${c.esc(draft[r.row_no]?.reason ?? r.approved_reason ?? '')}" placeholder="和推荐值不同时写理由"></div>`] : ledger ? [r.approved == null ? '待核定' : `<strong>${fmt(r.approved)} ${unitReview ? '（按行口径）' : '人次'}</strong><div class="cell-sub">${c.esc(r.approved_reason || '已核定')}</div>`] : [])]),
    '这个筛选下没有行', '换一个筛选看看。') + '</div>';
}

function invalidateLedgerPreview() {
  lastPreview = null; lastFile = null; previewSequence++;
  const button = document.getElementById('ledger-submit-btn');
  if (button) button.disabled = true;
}

async function openUpload(c) {
  invalidateLedgerPreview();
  c.modal('上传学院统计表', `<p>选择本院《社会培训人次统计表》（.xlsx 或 .xls）。检查只读取和复算，点击“确认报送”才保存。</p><div class="form-grid mt16">${c.field('ledger_file', '统计表文件', 'file', '', {accept: '.xlsx,.xls', full: true})}</div><div id="ledger-preview-result" aria-live="polite"></div>`,
    c.act('取消', 'close') + c.act('检查这份表', 'tz-preview', '', '', 'search') + `<button type="button" class="btn primary" data-action="tz-submit" id="ledger-submit-btn" disabled>确认报送</button>`, true, '学院台账 / 检查与报送');
  document.getElementById('f-ledger_file')?.addEventListener('change', () => {
    invalidateLedgerPreview();
    document.getElementById('ledger-preview-result').innerHTML = c.note('文件已更换，请重新检查，确认结果后再报送。');
  });
}

async function preview(c) {
  invalidateLedgerPreview();
  const sequence = previewSequence;
  const input = document.getElementById('f-ledger_file');
  const file = input?.files?.[0];
  if (!file) throw Error('请先选择统计表文件');
  const fd = new FormData(); fd.set('file', file);
  const box = document.getElementById('ledger-preview-result');
  box.innerHTML = '<p class="muted mt16">正在读取和复算，请稍候……</p>';
  try {
    const result = await c.api('/social/ledgers/preview', {method: 'POST', body: fd});
    if (sequence !== previewSequence || input.files?.[0] !== file) return;
    box.innerHTML = previewHtml(c, result, file.name);
    lastPreview = result; lastFile = file;
    document.getElementById('ledger-submit-btn').disabled = false;
  } catch (err) {
    if (sequence !== previewSequence) return;
    box.innerHTML = c.note(err.message, true); throw err;
  }
}

async function submit(c) {
  if (!lastPreview || !lastFile) throw Error('请先检查这份表');
  if (document.getElementById('f-ledger_file')?.files?.[0] !== lastFile) { invalidateLedgerPreview(); throw Error('统计表已更换，请重新检查后报送'); }
  const form = document.getElementById('ledger-submit-form');
  const v = Object.fromEntries(new FormData(form));
  if (!v.org_id) throw Error('请选择报送学院');
  const fd = new FormData(); fd.set('file', lastFile); fd.set('org_id', v.org_id); fd.set('year', v.year); fd.set('reason', v.reason || '');
  const saved = await c.api('/social/ledgers', {method: 'POST', body: fd});
  year = saved.data.year; resetLedgerView(); openId = saved.id;
  c.closeModal(); c.toast('已报送，等待继续教育学院核定');
  return c.nav ? c.nav('ledgers', {year: String(year), ledger_id: saved.id, source: sourceView}) : c.render();
}

// 核定页：整页显示，表格够宽，逐行核对不挤在弹窗里
async function detailPage(c, id) {
  let d;
  try { d = await c.api('/social/ledgers/' + encodeURIComponent(id)); } catch (err) { openId = null; throw err; }
  year = d.data.year;
  const college = c.me?.role?.kind === 'college';
  const t = d.totals, s = d.data.summary, all = d.data.rows;
  const unitReview = needsUnitReview(d.reported_quantities);
  const shown = rowFilter === 'serious' ? all.filter(serious) : rowFilter === 'issues' ? all.filter(r => r.issues?.length) : all;
  const count = {all: all.length, issues: all.filter(r => r.issues?.length).length, serious: all.filter(serious).length};
  const versions = d.versions.length > 1 ? `<details class="business-guide data-details mt16"><summary>历次报送（${d.versions.length} 版）</summary>${c.table(['版本', '报送时间', '原表报送量（分单位）', unitReview ? '推荐试算量' : '推荐口径', unitReview ? '当前核对量' : '当前汇总', ''], d.versions.map(v => ['第 ' + v.version_no + ' 版', c.esc(c.ts(v.created_at)), reportedText(c, v.reported_quantities), fmt(v.totals.recommended_total), fmt(v.totals.final_total), v.id === d.id ? '<span class="muted small">当前查看</span>' : c.link('查看这一版', 'tz-detail', v.id)]))}</details>` : '';
  const tools = d.can_review
    ? `<div class="ledger-review-bar"><span>${unitReview ? '核定：按各行口径填写认可的核对值，不把人天或折算量直接当作人次。' : '核定：在“核定值”里填继续教育学院认可的人次，'}留空表示暂不核定；和推荐值不同的要写理由。</span><span class="ledger-review-actions">${c.act('空着的行填入推荐值', 'tz-fill', '', '', 'check')}<button type="button" class="btn primary" data-action="tz-review-save" data-id="${c.esc(d.id)}|${d.version}">保存核定</button></span></div>`
    : '';
  const done = all.filter(r => r.approved != null && r.approved !== '').length;
  const left = all.filter(r => !r.project_id && Number(r.approved ?? r.recommended) > 0).length;
  const drafts = d.can_draft ? `<div class="card mt16 card-pad ledger-next"><div><h2>项目关联与草稿</h2><p class="cell-sub">换版后保留明确的原项目关联；重名人员与待关联项目请先逐行确认。草稿的日期、核算方式、层级和场景须核实后才能正式备案。人次为 0 的行不生成。${d.drafts ? `已关联 ${d.drafts} 个项目。` : ''}</p></div>${left ? `<button type="button" class="btn primary" data-action="tz-drafts" data-id="${c.esc(d.id)}|${d.version}">生成项目草稿（${left} 行）</button>` : '<span class="badge green-b">当前无可生成的项目行</span>'}</div>` : '';
  const fig = d.school_figure;
  const figureResult = !fig ? '' : unitReview
    ? `已登记人工核对数 ${fmt(fig.value)}，当前核对量 ${fmt(t.final_total)}；按各行口径核对，不计算跨单位差额（${c.esc(fig.reason)}）。`
    : `已登记 <strong>${fmt(fig.value)}</strong> 人次，系统当前汇总 ${fmt(t.final_total)}，${Number(fig.diff) ? `<span class="ledger-cut">相差 ${fmt(fig.diff)}</span>` : '<span class="green">一致</span>'}（${c.esc(fig.reason)}）`;
  const figure = d.can_review ? `<div class="card mt16 card-pad"><h2>${unitReview ? '学校人工核对数' : '学校人工核定数（和系统对比）'}</h2><p class="cell-sub mt8">${unitReview ? '人工核对数须与各行采用的核算口径对应，不作为原表人次统计；仍有未核定行时，数字一致也不代表完成核定。' : '把继续教育学院以前人工算的这份台账总数填进来，系统与当前汇总逐份对比；仍有未核定行时，即使数字一致也不代表完成核定，不能据此启用正式口径。'}</p>${fig ? `<p class="mt8">${figureResult}</p>` : ''}<div class="form-grid mt16">${c.field('school_figure', unitReview ? '学校人工核对数' : '学校人工核定人次', 'number', fig?.value ?? '', {required: false, min: 0, step: 0.01})}${c.field('school_figure_reason', '来源说明', 'text', '', {hint: unitReview ? '说明原表单位及逐行核对依据，不填跨单位合计' : '例如：2025 年资料包文件夹名中的核定数'})}</div><div class="mt16"><button type="button" class="btn" data-action="tz-figure" data-id="${c.esc(d.id)}|${d.version}">保存${unitReview ? '核对数' : '对比数'}</button></div></div>` : (fig ? c.note(unitReview ? `学校人工核对数 ${fmt(fig.value)}；按各行口径核对，不计算跨单位差额。` : `学校人工核定 ${fmt(fig.value)} 人次，与系统相差 ${fmt(fig.diff)}`) : '');
  const original = d.data.file.id && c.can('file.read') ? c.act('查看报送原件', 'attachment-download', d.data.file.id) : '';
  return `<div class="ledger-detail">` + c.pageHead(college ? `${d.org_name} · ${d.data.year} 年 · 第 ${d.data.version_no} 版` : `${d.org_name} · ${d.data.year} 年 · 第 ${d.data.version_no} 版 · ${d.data.template_label} · ${d.submitted_by_name || '—'}报送《${d.data.file.name}》`, original + c.act(college ? '返回本院台账' : '返回各学院列表', 'tz-back', '', '', 'chevron'))
    + `<div class="detail-action-context"><span>当前查看台账</span><strong>${c.esc(d.org_name)} · ${c.esc(d.data.year)} 年 · 第 ${c.esc(d.data.version_no)} 版</strong><p>${t.pending_rows ? `待学校核定 · ${t.pending_rows} 行未核定，当前汇总含推荐值` : all.some(r => r.history?.date_prefill) ? '报送量已核定 · 历史预填日期仍待学校复核' : '学校已核定 · 全部项目行已核定'}</p></div>`
    + (college ? `<details class="detail-fold"><summary>报送资料与版本说明</summary><dl class="kv"><dt>统计表</dt><dd>${c.esc(d.data.file.name)}</dd><dt>报送人</dt><dd>${c.esc(d.submitted_by_name || '—')}</dd><dt>表格版本</dt><dd>${c.esc(d.data.template_label)}</dd></dl></details>` : '')
    + `<section class="summary-row ledger-stats">${reportedStats(c, d.reported_quantities)}${stat(c, unitReview ? '推荐试算量' : '按推荐口径', fmt(t.recommended_total), unitReview ? '' : '人次', unitReview ? '按各行口径核对，不作为原表人次统计' : '系统推荐口径，待学校确认')}${stat(c, unitReview ? '当前核对量' : t.pending_rows ? '当前汇总（含待核定）' : '核定人次', fmt(t.final_total), unitReview ? '' : '人次', t.pending_rows ? t.pending_rows + ' 行未核定（暂用推荐值）' : '全部核定', t.pending_rows ? 'warn' : '')}${college ? '' : stat(c, '严重问题', s.serious, '行', '需要重点核对', s.serious ? 'bad' : '')}${stat(c, '已核定', `${done}/${all.length}`, '行', done === all.length ? '全部核定' : '留空的行暂用推荐值', done === all.length ? '' : 'warn')}</section>`
    + (unitReview ? c.note(unitReviewNote, false, '单位与核对口径') : '') + (d.data.notes || []).map(n => c.note(n, true)).join('') + (college && d.note ? `<details class="detail-fold mt16"><summary>推荐值与正式核定的区别</summary><p>${c.esc(d.note)}</p></details>` : c.note(d.note, false, '统计口径'))
    + `<div class="card mt16"><div class="card-head"><div class="ledger-filter" role="group" aria-label="筛选行">${FILTERS.map(([k, l]) => `<button type="button" class="btn sm ${rowFilter === k ? 'primary' : ''}" data-action="tz-filter" data-id="${k}" aria-pressed="${rowFilter === k}">${l}（${count[k]}）</button>`).join('')}</div></div>${tools}${rowsTable(c, shown, d.can_review, d)}`
    + (d.can_review ? `<div class="form-grid card-pad">${c.field('ledger_review_reason', '本次核定说明', 'textarea', '', {full: true, hint: unitReview ? '请按各行口径说明原表单位、备案方式及核定依据' : '例如：按 2026 年推荐口径核定，线上浏览量不计人次'})}</div>` : '') + '</div>'
    + drafts + figure + versions + '</div>';
}

async function makeDrafts(c, code) {
  const [id, version] = code.split('|');
  const r = await c.api('/social/ledgers/' + encodeURIComponent(id) + '/projects', {method: 'POST', body: {expected_version: Number(version), rows: [], reason: '由学院台账生成项目草稿'}});
  c.toast(`已生成 ${r.made.length} 个项目草稿` + (r.skipped.length ? `，${r.skipped.length} 行没生成：` + r.skipped.map(x => `第${x.row_no}行${x.reason}`).join('；') : '') + '。到“培训项目”里补全后提交备案。');
  await c.render();
}

async function saveFigure(c, code) {
  const [id, version] = code.split('|');
  const value = document.getElementById('f-school_figure')?.value ?? '';
  const reason = document.getElementById('f-school_figure_reason')?.value || '';
  if (reason.trim().length < 2) throw Error('请写来源说明');
  await c.api('/social/ledgers/' + encodeURIComponent(id) + '/school-figure', {method: 'POST', body: {expected_version: Number(version), value: value === '' ? null : value, reason}});
  c.toast('已保存，返回台账查看核对记录'); await c.render();
}

// 年度目标与考核速算（规划第 2、7 步）
async function targetsPage(c) {
  const d = await c.api('/social/targets?year=' + year);
  const cell = (actual, target, unit = '') => `${actual == null ? '<span class="muted">无数据</span>' : fmt(actual) + unit}<div class="cell-sub">目标 ${target == null || target === '' ? '未下达' : fmt(target) + unit}${actual != null && Number(target) > 0 ? ' · 完成 ' + Math.round(actual / target * 100) + '%' : ''}</div>`;
  const labels = {students: '在校生数（人）', income: '收入目标（元）', participants: '培训人次目标', priority: '重点群体人次目标', priority_actual: '重点群体实际人次', compliance_failures: '其他不合规次数（不含项目结算核验）', veto_reason: '一票否决依据'};
  const input = (x, key, type = 'number') => `<label class="target-field"><span>${labels[key]}</span><input class="ledger-target" type="${type}" ${type === 'number' ? `min="0" step="${key === 'compliance_failures' ? 1 : 0.01}"` : 'maxlength="500" placeholder="填写处分文件号，无则留空"'} data-org="${c.esc(x.org_id)}" data-key="${key}" value="${c.esc(x.targets?.[key] ?? '')}" aria-label="${c.esc(x.org_name)} · ${labels[key]}"></label>`;
  const cards = d.items.map(x => {
    const e = x.estimate, t = x.targets || {}, sg = x.suggest;
    const grade = e.grade ? `<span class="badge ${e.grade === '优秀' ? 'green-b' : e.grade.startsWith('不合格') ? 'red-b' : 'blue-b'}">${c.esc(e.grade)}</span>` : '<span class="badge orange-b">待补充</span>';
    const missing = e.total == null ? `<p class="target-missing">还缺：${c.esc(e.missing.join('、'))}</p>` : '';
    const score = e.total == null ? '—' : fmt(e.total);
    return `<details class="target-college" data-org="${c.esc(x.org_id)}"><summary><span class="target-college-name"><strong>${c.esc(x.org_name)}</strong><small><span class="target-expand">${d.can_edit ? '展开填写与核对' : '展开查看明细'}</span><span class="target-collapse">${d.can_edit ? '收起填写区域' : '收起明细'}</span></small></span><span class="target-metric"><small>到账收入（元）</small><strong>${x.actual.income == null ? '无数据' : fmt(x.actual.income)}</strong></span><span class="target-metric"><small>当前汇总人次</small><strong>${x.actual.participants == null ? '未报台账' : fmt(x.actual.participants)}</strong></span><span class="target-metric"><small>速算总分</small><strong class="ledger-score">${score}</strong></span><span class="target-grade">${grade}</span><span class="target-chevron" aria-hidden="true">${c.icon('down')}</span></summary>${missing}
      <div class="target-body">${d.can_edit ? `<section class="target-form-section"><h3>年度目标</h3><div class="target-fields">${['students','income','participants','priority'].map(key => input(x, key)).join('')}</div>${sg ? `<p class="cell-sub">建议：人次 ${fmt(sg.participants)} · 重点群体 ${fmt(sg.priority)}</p>` : ''}</section><section class="target-form-section"><h3>学校核验信息</h3><p class="cell-sub">其他不合规次数须排除项目结算核验；历史数值请核对后再保存，避免重复扣分。</p><div class="target-fields target-verification">${input(x,'priority_actual')}${input(x,'compliance_failures')}${input(x,'veto_reason','text')}</div></section>` : `<section class="target-form-section"><h3>年度目标与完成情况</h3><div class="target-readonly"><div><small>培训收入</small>${cell(x.actual.income,t.income,' 元')}</div><div><small>培训人次</small>${cell(x.actual.participants,t.participants)}</div><div><small>重点群体人次</small>${cell(x.actual.priority,t.priority)}</div><div><small>在校生数</small>${t.students == null ? '未填写' : fmt(t.students) + ' 人'}</div></div>${sg ? `<p class="cell-sub">建议：人次 ${fmt(sg.participants)} · 重点群体 ${fmt(sg.priority)}</p>` : ''}</section>`}
      <section class="target-calculation"><h3>速算依据 <small>按已保存数据计算，供核对参考</small></h3><div class="target-readonly"><div><small>培训成果</small>国家 ${c.esc(x.achievements.national)} · 省 ${c.esc(x.achievements.province)} · 校 ${c.esc(x.achievements.school)}<div class="cell-sub">${fmt(e.results)} 分${x.achievements_pending ? ` · 另有 ${c.esc(x.achievements_pending)} 项待确认认定年度` : ''}</div></div><div><small>资金管理</small><strong>${e.cost == null ? '待财务核验' : fmt(e.cost) + ' 分'}</strong><div class="cell-sub">${e.cost_details?.length ? e.cost_details.map(c.esc).join('；') : '没有扣分'}</div></div><div class="target-score-detail"><small>分项得分</small>${e.total == null ? '数据补齐并保存后计算' : `${e.metrics.map(m => c.esc(m.label) + ' ' + fmt(m.score)).join(' · ')} · 成果 ${fmt(e.results)} · 资金 ${fmt(e.cost)} · 加分 ${fmt(e.bonus)}`}</div></div>${e.veto ? `<p class="mine-due">一票否决：${c.esc(e.veto)}</p>` : ''}</section></div></details>`;
  }).join('');
  return c.pageHead('按学院下达年度目标，核对完成情况与考核速算结果。', '') + pageTabs(c)
    + `<div class="target-yearbar">${yearTabs(c)}<span>速算仅供核对，正式结果以学院年度考核为准</span></div><section class="card target-workspace"><div class="card-head"><div><h2>${year} 年学院目标</h2><p>共 ${d.items.length} 个学院 · 点击学院展开${d.can_edit ? '填写' : '明细'}${d.can_edit ? '，修改后统一保存' : ''}</p></div>${d.can_edit ? `<div class="ledger-actions">${c.act('填入建议目标', 'tz-suggest')}<button type="button" class="btn primary" data-action="tz-targets-save">保存目标</button></div>` : ''}</div>${cards || '<p class="card-pad">没有可查看的学院</p>'}</section>
    <details class="business-guide target-rules"><summary>查看统计口径与目标填写说明</summary><div class="card-pad">${c.note(d.note, false, '统计口径')}<p>收入取本年度已结项且经财务确认的项目实际到账收入，每个项目只计一次；人次取学院台账当前汇总，未核定行暂用推荐值；是否完成核定请查看学院台账状态。重点群体由学校核验登记。</p><p>先填写在校生数，再点“填入建议目标”：培训人次按在校生数的 2 倍、重点群体按 0.5 倍填入空白目标，已有数值不会覆盖。收入目标由学校确定后填写。</p><p>留空表示未填写，填写 0 表示明确为零。建议目标依据管理办法第二十三条及考核细则；收入基准按在校生数和教师数各占 50%，具体金额待学校确定。</p></div></details>`;
}

async function saveTargets(c) {
  const expanded = new Set([...document.querySelectorAll('.target-college[open]')].map(x=>x.dataset.org));
  const items = {};
  for (const x of document.querySelectorAll('.ledger-target')) (items[x.dataset.org] ||= {org_id: x.dataset.org})[x.dataset.key] = x.value.trim() === '' ? null : x.dataset.key === 'compliance_failures' ? Number(x.value) : x.value.trim();
  await c.api('/social/targets', {method: 'PUT', body: {year, items: Object.values(items).map(x=>({...x,compliance_scope:'other_only'})), reason: `下达 ${year} 年学院社会培训目标`}});
  c.toast('目标已保存'); await c.render();
  for(const panel of document.querySelectorAll('.target-college'))panel.open=expanded.has(panel.dataset.org);
}

function fillSuggested(c) {
  let n = 0;
  const get = (org, key) => [...document.querySelectorAll('.ledger-target')].find(x => x.dataset.org === org && x.dataset.key === key);
  for (const x of document.querySelectorAll('.ledger-target[data-key="students"]')) {
    const students = Number(x.value); if (!x.value || !(students > 0)) continue;
    for (const [key, times] of [['participants', 2], ['priority', 0.5]]) { const box = get(x.dataset.org, key); if (box && box.value === '') { box.value = String(students * times); n++; } }
  }
  c.toast(n ? `已按在校生数填入 ${n} 个建议目标，检查后点“保存目标”` : '先填各学院在校生数；已经填了目标的格子不会被覆盖');
}

async function deptsPage(c) {
  const d = await c.api('/social/departments?year=' + year);
  const rows = d.items.map(x => [x.rank == null ? '—' : c.esc(x.rank), `<strong>${c.esc(x.name)}</strong><div class="cell-sub">${c.esc(x.college)}</div>`, `${c.esc(x.teachers)} 人<div class="cell-sub">其中 ${c.esc(x.with_points)} 人有已归档积分</div>`, x.total == null ? '<span class="muted">暂无已归档数据</span>' : fmt(x.total), x.average == null ? `<span class="muted">${Number(x.teachers) === 0 ? '没有在岗老师，暂不计算' : '暂未计算'}</span>` : `<strong>${fmt(x.average)}</strong>`]);
  return `<div class="dept-points-page">` + c.pageHead(c.me?.role?.kind === 'dept' ? '查看本教研室的年度平均积分；仅汇总已归档积分，未归档申报不计入。' : '查看教研室年度平均社会培训积分，按全体在岗教师人数计算。', '') + pageTabs(c) + yearTabs(c)
    + `<section class="card mt16"><div class="card-head"><div><h2>${c.esc(d.year ?? year)} 年教研室平均积分</h2><p class="cell-sub">已归档社会培训积分合计 ÷ 在岗教师人数；没有积分的教师也计入分母。</p></div></div>${c.table(['名次', '教研室', '在岗人数（分母）', '已归档积分合计', '人均积分'], rows, '当前年度没有可查看的教研室', '请切换年度查看；组织与教师范围以系统授权为准。')}</section>`
    + (d.note ? `<details class="detail-fold mt16"><summary>统计口径与考核说明</summary><p>${c.esc(d.note)}</p></details>` : '') + '</div>';
}

async function openConflicts(c) {
  const d = await c.api('/social/conflicts');
  const opts = [...d.teachers.map(t => ['teacher|' + t.id, '老师：' + t.name]), ...d.orgs.map(o => ['org|' + o.id, '学院：' + o.name])];
  const list = c.table(['申报人', '回避对象', '原因', '申报日期', ''], d.items.map(x => [c.esc(x.user_name), c.esc(x.target_name), c.esc(x.reason), c.esc(x.declared_on), x.active === false ? `已撤回（${c.esc(x.withdrawn_on)}）` : x.user_id === c.me.user?.id ? c.act('撤回', 'tz-conflict-withdraw', x.id) : '回避中']), '还没有利益冲突申报。');
  const form = d.can_declare ? `<div class="form-grid mt16">${c.field('conflict_target', '和谁存在利益冲突', 'select', '', {options: opts})}${c.field('conflict_reason', '原因（如亲属关系、利益往来）', 'text', '')}</div>` : '';
  c.modal('利益冲突申报与回避', c.note(d.note, false, '统计口径') + form + `<h3 class="mt20">${d.all ? '全校申报记录（供纪检抽查）' : '我的申报'}</h3>` + list, c.act('关闭', 'close') + (d.can_declare ? c.act('提交申报', 'tz-conflict-save', '', 'primary') : ''), true);
}

async function saveConflict(c) {
  const [target_kind, target_id] = (document.getElementById('f-conflict_target')?.value || '').split('|');
  const reason = document.getElementById('f-conflict_reason')?.value || '';
  if (!target_id) throw Error('请选择回避对象');
  if (reason.trim().length < 2) throw Error('请写申报原因');
  await c.api('/social/conflicts', {method: 'POST', body: {target_kind, target_id, reason}});
  c.toast('已申报。审批到这个对象时系统会要求你回避'); return openConflicts(c);
}

async function withdrawConflict(c, id) {
  return c.formModal('撤回利益冲突申报',c.field('reason','撤回原因','textarea','',{full:true}),async v=>{
    if(v.reason.trim().length<2)throw Error('请写明撤回原因');
    await c.api('/social/conflicts/' + encodeURIComponent(id) + '/withdraw', {method: 'POST', body: {reason:v.reason}});
    c.toast('已撤回');await openConflicts(c);
  },{submit:'确认撤回',returnTo:()=>openConflicts(c),returnLabel:'返回申报记录'});
}

function captureDraft() {
  const reasons = Object.fromEntries([...document.querySelectorAll('.ledger-reason')].map(x => [x.dataset.row, x.value]));
  for (const x of document.querySelectorAll('.ledger-approved')) draft[x.dataset.row] = {approved: x.value, reason: reasons[x.dataset.row] || ''};
}

export function resetLedgerView(fromMenu = false) { openId = null; rowFilter = 'all'; draft = {}; if (fromMenu) { tab = 'ledgers'; sourceView = 'school'; sourceYear = null; } }

function fillRecommended(c) {
  let n = 0;
  for (const x of document.querySelectorAll('.ledger-approved')) if (x.value === '') { x.value = x.dataset.recommended; n++; }
  c.toast(n ? `已填入 ${n} 行推荐值，检查后点“保存核定”` : '没有空着的行');
}

async function saveReview(c, code) {
  const [id, version] = code.split('|');
  captureDraft();
  const rows = Object.entries(draft).filter(([, v]) => v.approved !== '').map(([row, v]) => ({row_no: Number(row), approved: v.approved, reason: v.reason}));
  if (!rows.length) throw Error('请至少填写一行核定值');
  const reason = document.getElementById('f-ledger_review_reason')?.value || '';
  if (reason.trim().length < 2) throw Error('请填写本次核定说明');
  await c.api('/social/ledgers/' + encodeURIComponent(id) + '/review', {method: 'POST', body: {expected_version: Number(version), rows, reason}});
  draft = {}; c.toast('核定已保存'); await c.render();
}

export async function resourceStatsPage(c) {
  const d = await c.api('/social/resource-stats');
  const dept = c.me?.role?.kind === 'dept';
  const total = k => d.items.reduce((n, x) => n + Number(x[k] || 0), 0);
  const courses = c.can('records.read') && (!c.pageAllowed || c.pageAllowed('courses')) ? c.act(dept ? '查看课程资源' : '去登记课程资源', 'nav', 'courses', '', 'book') : '';
  return `<div class="resource-stats-page">` + c.pageHead(dept ? '查看本教研室相关课程的资源建设情况；本页仅供查阅，资源由有权限的经办人员登记。' : '按学院统计培训课程资源建设：课程数、资源数、视频数和视频总分钟数。资源在“培训课程”里登记。', courses)
    + `<section class="summary-row">${stat(c, '课程', total('courses'), '门')}${stat(c, '资源', total('resources'), '个')}${stat(c, '视频', total('videos'), '个')}${stat(c, '视频总时长', fmt(total('minutes')), '分钟')}</section>`
    + `<section class="card mt16"><div class="card-head"><h2>${dept ? '本教研室课程资源' : '各学院课程资源'}</h2></div>${c.table([dept ? '教研室' : '学院', '课程', '资源', '视频', '视频总分钟'], d.items.map(x => [c.esc(x.org_name), c.number(x.courses), c.number(x.resources), c.number(x.videos), `<strong>${fmt(x.minutes)}</strong>`]), dept ? '本教研室暂未登记课程资源' : '还没有登记课程资源', dept ? '相关课程的资源完成登记后，这里会自动汇总。' : '在“培训课程”里给课程登记视频和时长后，这里自动统计。')}</section>` + c.note(d.note, false, '统计口径') + '</div>';
}

// 首页最上面一排：人次、收入、成果、双师型、双师型初/中/高级（老师手写菜单顶部）。
// 老师看本人：我的人次、我参与的收入、本院成果、我的双师型级别、我的社会培训积分。
// extra：调用方追加的指标格（管理角色的人均授课学分）；more：标题栏右侧的“更多统计”入口。
export async function homeIndicators(c, stats, extra = '', more = '') {
  let o;
  try { o = await c.api('/social/overview?year=' + new Date().getFullYear()); } catch (err) { return c.note('首页指标暂时读取失败：' + err.message, true); }
  if (!o) return '';
  const teacher = c.me.role.kind === 'teacher', dept = c.me.role.kind === 'dept';
  // 学校首页的人次与驾驶舱同源：取学院原表报送值，人次、人天、原表折算量分开，不合成一个“人次”。
  let report = null;
  if (c.me.role.kind === 'school' && c.can('records.read')) { try { const r = await c.api('/social/cockpit'); if (r?.available) report = r; } catch { report = null; } }
  const p = o.participants || {}, dual = o.dual || {}, lv = dual.levels || {}, al = o.achievements?.levels || {}, pts = o.points;
  const explanations = [];
  const card = (label, value, unit, foot, target, ico, brief = '') => {
    const key = target === 'qualifications' ? 'qualifications' : target === 'points' ? 'points' : 'records';
    const permission = {qualifications: 'qualification.read', points: 'points.read', records: 'records.read'}[key];
    if (o.sections?.[key] === false || !c.can(permission)) return '';
    explanations.push(`<li><strong>${c.esc(label)}</strong><span>${c.esc(foot)}</span></li>`);
    return `<button type="button" class="kpi" data-action="nav" data-id="${target}" ${c.pageAllowed(target) ? '' : 'disabled'}><span class="kpi-label">${c.esc(label)}</span><span class="kpi-icon">${c.icon(ico)}</span><div class="kpi-value${/^[\d.,\-]+$/.test(String(value)) ? '' : ' kpi-text'}">${value}<small>${c.esc(unit)}</small></div>${brief ? `<div class="kpi-foot">${c.esc(brief)}</div>` : ''}</button>`;
  };
  const achievements = card(teacher || dept ? '所属学院培训成果' : '培训成果', c.number(o.achievements?.total), '项', `${teacher ? '你所在学院今年登记的成果：' : ''}国家级 ${al.national ?? 0} · 省级 ${al.province ?? 0} · 校级 ${al.school ?? 0}`, 'outcomes', 'award', teacher ? '' : o.achievements?.total ? `国家级 ${al.national ?? 0} · 省级 ${al.province ?? 0} · 校级 ${al.school ?? 0}` : `${o.year} 年还没有登记成果`);
  // 双师型合成一格：人数是主数，初/中/高级放在格子下方，不再单独占一格。
  const dualCard = label => card(label, c.number(dual.total), '人', '以审核通过的教师资质为准；按资质类别中的级别分初级、中级、高级' + (lv['未分级'] ? `，另有 ${lv['未分级']} 人未写级别` : ''), 'qualifications', 'cert',
    dual.total ? `初级 ${lv['初级'] ?? 0} · 中级 ${lv['中级'] ?? 0} · 高级 ${lv['高级'] ?? 0}` + (lv['未分级'] ? ` · 未分级 ${lv['未分级']}` : '') : '还没有审核通过的双师型资质');
  const cards = teacher
    ? [card('我的培训人次', fmt(p.mine?.value), '人次', `学院统计表里分给你的人次（涉及 ${p.mine?.projects || 0} 个项目），仅供参考，以项目核定为准`, 'mine', 'users', '原表分配 · 仅供核对'),
       card('我参与的培训收入', c.number(stats?.income, 2), '元', '你授课的项目里按规则归到你名下的收入（本统计周期）', 'records', 'wallet'),
       achievements,
       card('我的双师型', dual.mine ? (dual.mine === '未分级' ? '已认定' : dual.mine) : '未认定', '', dual.mine ? '以审核通过的资质为准' : '有证书可在“教师资质”里申报', 'qualifications', 'cert'),
       card('我的社会培训积分', fmt(pts?.year), '分', `今年已认定的积分。近五年累计 ${fmt(pts?.five_years)} 分（目标 ${pts?.five_year_target || 340} 分），按现行办法可折职称分 ${fmt(pts?.title_points)} 分（试算）` + (pts?.trial != null ? `；另有 ${fmt(pts.trial)} 分还在审批中` : ''), 'points', 'award', '本年度已认定')]
    : dept
    ? [card('本教研室课程人次', c.number(stats?.participants), '人次', '本教研室教师授课业务 · 按当前统计周期', 'records', 'users'),
       card('本教研室培训收入', c.number(stats?.income, 2), '元', '归属培训收入 · 按当前统计周期', 'records', 'wallet'),
       achievements,
       dualCard('本教研室双师型教师')]
    : [report ? card('培训人次（原表报送）', fmt(report.totals.person_times), '人次', `${report.period?.label || ''} · 学院原表报送值，待学校核定；与管理驾驶舱同一来源。人天 ${fmt(report.totals.person_days)}、原表折算量 ${fmt(report.totals.raw_conversions)} 分开统计，不计入人次；${report.totals.colleges} 个学院报送`, 'cockpit', 'users',
         `另有 ${fmt(report.totals.person_days)} 人天 · ${report.totals.colleges} 个学院报送`) : card(p.pending_rows ? '培训人次（待核定）' : '培训人次', fmt(p.final), '人次', (p.completion ? `完成年度目标 ${Math.round(p.completion)}%（目标 ${fmt(p.target)}）· ` : '') + `${p.reported}/${p.colleges} 个学院已报` + (Number(o.online?.views) ? ` · 线上浏览 ${fmt(o.online.views)} 另计` : ''), 'ledgers', 'users',
         p.reported ? `${p.reported}/${p.colleges} 个学院已报台账` : `学院还没报送 ${o.year} 年台账`),
       // 两个收入口径名字分开：首页取“结项到账收入”（社会培训管理办法），驾驶舱和培训数据取“归属培训收入”（授课流水）。
       card(o.income ? '结项到账收入' : '归属培训收入', o.income ? c.number(o.income.actual, 2) : c.number(stats?.income, 2), '元', o.income ? o.income.source_note + '驾驶舱的“归属培训收入”按授课流水统计，两者口径不同。' : '归属培训收入（按当前统计周期）', 'records', 'wallet',
         o.income && !Number(o.income.actual) ? '还没有结项并核验到账的项目' : ''),
       achievements,
       dualCard('双师型教师')];
  const todo = !teacher && !dept && c.can('records.read') && o.sections?.records !== false && p.pending_ledgers ? `<div class="home-ledger-todo">${c.icon('data')}<span><strong>${p.pending_ledgers} 个学院的 ${o.year} 年台账待核定</strong> · ${p.pending_rows} 行待核定（含推荐值）</span>${c.act(o.can_review ? '去核定' : '查看核定进度', 'nav', 'ledgers', 'primary', 'arrow')}</div>` : '';
  return `<section class="home-indicators" aria-label="${c.esc(o.scope)}核心指标"><div class="workbench-section-head"><h2>${teacher ? '培训概况' : c.esc(o.scope)+'概况'}</h2><div class="home-indicators-tools"><details class="metric-help"><summary>统计说明</summary><div><p>${c.esc(o.note)}</p><ul>${explanations.join('')}</ul></div></details>${more}</div></div><div class="kpis kpis-5">${cards.join('')}${extra}</div>${todo}</section>`;
}

export async function ledgerAction(name, id, c) {
  if(name==='mine-section'){
    if(!['projects','claims','allocations','resources'].includes(id))return;
    const section=document.getElementById('mine-'+id);if(!section)return;
    section.focus({preventScroll:true});section.scrollIntoView({block:'start',behavior:'auto'});return;
  }
  if (['tz-bind-person', 'tz-bind-project', 'tz-bind-owner'].includes(name)) return bindLedgerRow(name, id, c);
  if (name === 'tz-year') { tab = c.filter?.ledger_tab || tab; year = sourceYear = Number(id); resetLedgerView(); return c.nav ? c.nav('ledgers', {year: String(year), source: sourceView, ...(tab === 'ledgers' ? {} : {ledger_tab: tab})}) : c.render(); }
  if (name === 'tz-upload') return openUpload(c);
  if (name === 'tz-preview') return preview(c);
  if (name === 'tz-submit') return submit(c);
  if (name === 'tz-detail') { resetLedgerView(); openId = id; return c.nav ? c.nav('ledgers', {year: String(year), ledger_id: id, source: sourceView}) : c.render(); }
  if (name === 'tz-back') { resetLedgerView(); return c.nav ? c.nav('ledgers', {year: String(year), source: sourceView}) : c.render(); }
  if (name === 'tz-filter') { captureDraft(); rowFilter = FILTERS.some(([key]) => key === id) ? id : 'all'; if (c.filter) { c.filter.ledger_filter = rowFilter; c.syncLocation?.(true); } return c.render(); }
  if (name === 'tz-fill') return fillRecommended(c);
  if (name === 'tz-review-save') return saveReview(c, id);
  if (name === 'tz-tab') { tab = id; resetLedgerView(); return c.nav ? c.nav('ledgers', {year: String(year), source: sourceView, ledger_tab: tab}) : c.render(); }
  if (name === 'tz-drafts') return makeDrafts(c, id);
  if (name === 'tz-figure') return saveFigure(c, id);
  if (name === 'tz-targets-save') return saveTargets(c);
  if (name === 'tz-suggest') return fillSuggested(c);
  if (name === 'tz-conflicts') return openConflicts(c);
  if (name === 'tz-conflict-save') return saveConflict(c);
  if (name === 'tz-conflict-withdraw') return withdrawConflict(c, id);
}

async function bindLedgerRow(action, code, c) {
  captureDraft();
  const [id, rowNo, index] = code.split('|');
  const ledger = await c.api('/social/ledgers/' + encodeURIComponent(id));
  if (!ledger.can_draft) throw Error('当前账号没有台账关联权限');
  const row = ledger.data.rows.find(r => r.row_no === Number(rowNo));
  if (!row) throw Error('台账行不存在，请刷新后重试');
  const people = [['', '请选择明确的人员'], ...(ledger.teacher_options || []).map(t => [t.id, `${t.name} · 工号 ${t.employee_no || '未登记'}`])];
  const personal = action === 'tz-bind-person', owner = action === 'tz-bind-owner';
  const title = personal ? '确认个人分配归属' : owner ? '确认项目负责人' : '确认项目关联';
  let body = c.note(`第 ${rowNo} 行：${row.name}`);
  if (personal) body += c.note('原表姓名：' + (row.allocations?.[Number(index)]?.name || '待核对')) + c.field('teacher_id', '对应教师及工号', 'select', '', {options: people});
  else if (owner) body += c.field('owner_id', '项目负责人及工号', 'select', row.owner_id || '', {options: people});
  else body += c.field('action', '办理方式', 'select', '', {options: [['', '请选择办理方式'], ['link', '关联已有项目'], ['new', '确认是独立新项目']]}) + c.field('project_id', '已有项目（选择关联时必填）', 'select', '', {required: false, options: [['', '请选择项目'], ...(ledger.project_options || []).map(p => [p.id, `${p.name} · ${p.code}`])]});
  body += c.field('reason', '确认依据与说明', 'textarea');
  c.formModal(title, body, async v => {
    const endpoint = personal ? 'person' : 'project-link';
    const data = {...v, expected_version: ledger.version};
    if (personal) data.allocation_index = Number(index);
    if (owner) data.action = 'owner';
    if (data.action === 'link' && !data.project_id) throw Error('请选择要关联的已有项目');
    await c.api(`/social/ledgers/${encodeURIComponent(id)}/rows/${rowNo}/${endpoint}`, {method: 'POST', body: data});
    c.closeModal(); c.toast('关联已确认并保留办理记录'); await c.render();
  }, {submit: '确认关联', contextLabel: '学院台账 / '+title, returnTo: () => { c.closeModal(); openId = id; return c.render(); }, returnLabel: '返回学院台账'});
}

const LEVELS = {national: '国家级', province: '省级', school: '校级'};

export function mineReminders(c, m, limit = m.reminders.length) {
  return `<div class="mine-reminders">${m.reminders.slice(0, limit).map(r => {
    const project = (m.projects || []).find(p => r.id === 'social_project|' + p.id && p.deadline);
    const deadline = project?.deadline;
    const text = deadline ? `${project.name} · ${deadline.estimated ? '申报日期待学校确认' : deadline.days_left < 0 ? '已过申报期限' : '请于 ' + deadline.date + ' 前申报'}` : r.text;
    const action = r.action === 'social-claim-new' && m.claim_ready?.reason ? '' : c.act(r.action_label || (r.action === 'social-claim-new' ? '去申报' : '去处理'), r.action, r.id);
    return `<div class="mine-reminder${r.level === 'warn' ? ' warn' : ''}"><div class="reminder-copy"><span>${c.esc(text)}</span>${deadline ? `<details class="inline-note"><summary>查看说明</summary><p>${c.esc(r.text)}</p></details>` : ''}</div>${action}</div>`;
  }).join('')}</div>`;
}

// 个人培训：老师手写菜单“个人培训 → 系统打开显示个人”。只放本人的东西，按“先办事、再看数”排列。
export async function minePage(c) {
  let m;
  try { m = await c.api('/social/mine?year=' + new Date().getFullYear()); } catch (err) { return c.pageHead('只显示本人的培训、积分和资质。') + c.note('我的培训明细读取失败：' + err.message, true); }
  const e = c.esc;
  const sections = {records: c.can('records.read'), points: c.can('points.read'), qualifications: c.can('qualification.read'), ...m.sections};
  const ready = m.claim_ready, blocked = sections.points && ready?.reason && c.me.user?.staff_no;
  const actions = (c.me.user?.staff_no && sections.points && c.can('points.read') ? (blocked ? '' : c.act('申报本人积分', 'social-claim-new', '', 'primary')) : '') + (c.can('qualification.write') && c.me.user?.staff_no ? c.act('申报我的资质', 'qualification-form', '') : '');
  const sd = await mineSchoolData(c);
  const head = c.pageHead('按本人项目查看培训参与、积分申报和台账分配。', actions) + (sd.identity || `<p class="mine-identity">${e(m.name)} · ${e(m.org_name)}</p>`) + sd.banner;
  let pending;
  try { pending = await c.api('/todos?attention=handle&page=1&size=1'); } catch { pending = null; }
  const todo = `<section class="card mine-status"><div><strong>待我处理 <span class="workbench-count">${pending ? pending.total : '—'}</span></strong><p>${pending ? (pending.attention_counts?.waiting ? `${pending.attention_counts.waiting} 项等待核对或学校确认，不计入待我处理。` : '与“待办中心”使用同一办理口径。') : '待办暂未读取成功，请到“待办中心”重试。'}</p></div>${c.act('查看待办中心','nav','todos','light')}</section>` +
    (blocked ? `<details class="mine-claim-blocked"><summary>积分申报暂未开放</summary><p>${e(ready.reason)}</p></details>` : '');
  const claimCell = p => {
    if (p.claim) return e(p.claim.state_label);
    const d = p.deadline;
    if (!d) return '—';
    if (d.estimated) return `<details class="inline-note"><summary>日期待确认</summary><p>预计截止 ${e(d.date)}（待学校确认）</p></details>`;
    return `<span class="${d.days_left <= 5 ? 'mine-due' : ''}">${d.days_left < 0 ? '已过申报期限' : `截止 ${e(d.date)}，还剩 ${d.days_left} 个自然日`}</span>`;
  };
  const projects = `<section class="card"><div class="card-head"><div><h2>我的培训项目（${m.projects.length}）</h2></div>${c.pageAllowed('projects') ? c.link('全部项目', 'nav', 'projects') : ''}</div>` +
    c.table(['项目', '我的角色', '项目状态', '积分申报', '操作'], m.projects.map(p => [`<strong>${e(p.name)}</strong><p class="cell-sub">${e(p.code)} · ${e(p.cohort)}${p.start_date ? ' · ' + e(p.start_date) + ' 至 ' + e(p.end_date) : ''}</p>`, e(p.roles.join('、') || '—'), e(p.state_label), claimCell(p), c.act('查看项目', 'social-detail', 'social_project|' + p.id)]), '还没有我的培训项目。') + `</section>`;
  const claims = `<section class="card"><div class="card-head"><div><h2>我的积分申报（${m.claims.length}）</h2><p>审批中的分值为试算，完整流程和待确认项在详情查看。</p></div>${c.pageAllowed('recognition') ? c.link('全部申报', 'nav', 'recognition') : ''}</div>` +
    c.table(['项目', '申报积分', '当前进度', '操作'], m.claims.map(x => [`<strong>${e(x.project)}</strong><p class="cell-sub">${e(x.state_label)}${x.blockers ? ` · ${x.blockers} 项待确认` : ''}</p>`, x.total == null ? '—' : `${fmt(x.total)}<span class="cell-sub">${x.state==='ARCHIVED'?'已认定':'试算'}</span>`, blocked&&['DRAFT','RETURNED'].includes(x.state)?'<span class="muted">等待学校确认申报口径</span>':e(x.steps.find(s=>s.current)?.label||x.state_label), c.act('查看详情', 'social-detail', 'social_claim|' + x.id)]), '还没有积分申报。') + `</section>`;
  const allocations = `<section class="card mine-allocations"><div class="card-head"><div><h2>台账里分给我的人次</h2><p>原表分配与个人核定分别保留，以个人核定结果为准。</p></div></div>` +
    c.table(['年度', '学院', '培训项目', '原表分配', '个人核定状态'], m.allocations.map(a => [String(a.year), e(a.org_name), `${e(a.name)}<p class="cell-sub">第 ${a.row_no} 行${a.project_code ? ' · 项目 ' + e(a.project_code) : ''}</p>`, `${fmt(a.original_value ?? a.value)}<p class="cell-sub">原表参考数</p>`, `<details class="inline-note"><summary>${a.reviewed ? '已核定' : '待个人核定'}</summary><p>${e(a.review_status || '待个人分配复核')}</p></details>` + (a.project_approved != null ? `<p class="cell-sub">项目核定人次 ${fmt(a.project_approved)}</p>` : '') + (a.approved_value != null ? `<p class="cell-sub">个人核定 ${fmt(a.approved_value)}</p>` : '')]), '台账里还没有分给我的人次。') + `</section>`;
  const r = m.courses || {courses: 0, videos: 0, minutes: 0};
  const extra = `<section class="card"><div class="card-head"><div><h2>本人的课程资源与成果</h2><p>已入培训课程库的资源；与教务、超星授课学分分别统计。成果只列本人，学院汇总在成果页查看。</p></div><div>${c.pageAllowed('courses')?c.link('培训课程','nav','courses'):''}${c.pageAllowed('outcomes')?c.link('培训成果','nav','outcomes'):''}</div></div><div class="card-pad"><div class="mine-mini"><div><label>课程</label><strong>${r.courses}</strong></div><div><label>视频</label><strong>${r.videos}</strong></div><div><label>视频分钟</label><strong>${fmt(r.minutes)}</strong></div><div><label>本人成果</label><strong>${m.achievements.length}</strong></div></div>` +
    (m.achievements.length ? `<ul class="mine-list">${m.achievements.map(a => `<li>${e(a.name)} · ${e(LEVELS[a.level] || a.level)}${a.auto ? '（满意度自动生成）' : ''}</li>`).join('')}</ul>` : '') + `</div></section>`;
  // 没有数据的板块不再各占一大块，合成一行说明；有记录后自动出现。
  const empties = [], keep = (show, isEmpty, label, html) => { if (!show) return ''; if (isEmpty) { empties.push(label); return ''; } return html; };
  const projectHtml = keep(sections.records, !m.projects.length, '培训项目', `<div class="mt20 mine-section" id="mine-projects" tabindex="-1">${projects}</div>`);
  const claimHtml = keep(sections.points, !m.claims.length, '积分申报', `<div class="mt20 mine-section" id="mine-claims" tabindex="-1">${claims}</div>`);
  const allocationHtml = keep(sections.records, !m.allocations.length, '台账分给我的人次', `<div class="mt20 mine-section" id="mine-allocations" tabindex="-1">${allocations}</div>`);
  const extraHtml = keep(sections.records, !(r.courses || r.videos || Number(r.minutes) || m.achievements.length), '课程资源与成果', `<div class="mt20 mine-section" id="mine-resources" tabindex="-1">${extra}</div>`);
  const related = `<nav class="mine-related" aria-label="个人业务明细">${c.pageAllowed('credits')?c.link('查看授课学分与课程','nav','credits'):''}${sections.qualifications&&c.pageAllowed('qualifications')?c.link('教师资质 · '+m.qualifications.length+' 项','nav','qualifications'):''}${sections.points&&c.pageAllowed('points')?c.link('查看已认定积分','nav','points'):''}${sections.records&&c.pageAllowed('records')?c.link('授课与参训记录','nav','records'):''}</nav>`;
  const emptyLine = empties.length ? `<p class="mine-empty-line">暂无记录：${e(empties.join('、'))}。</p>` : '';
  // 老师菜单只留常用几项，其余页面从这里进入。
  const more = [['projects', '培训项目'], ['courses', '培训课程'], ['bases', '培训基地'], ['outcomes', '培训成果'], ['disputes', '我提出的核对'], ['exports', '导出下载']].filter(([p]) => c.pageAllowed(p) && (p !== 'qualifications' || sections.qualifications));
  const moreLinks = more.length ? `<nav class="mine-more" aria-label="更多入口"><span>更多：</span>${more.map(([p, l]) => c.link(l, 'nav', p)).join('')}</nav>` : '';
  const jumps=[['projects','培训项目',projectHtml],['claims','积分申报',claimHtml],['allocations','分配人次',allocationHtml],['resources','资源与成果',extraHtml]].filter(([, ,content])=>content);
  const jumpNav=jumps.length>1?`<nav class="mine-section-nav" aria-label="我的培训明细分区定位"><span>快速定位</span>${jumps.map(([key,label])=>c.act(label,'mine-section',key,'text')).join('')}</nav>`:'';
  return `<div class="mine-page">${head}${todo}<div class="mine-tools-row">${related}${moreLinks?`<details class="mine-tools"><summary>更多业务入口</summary>${moreLinks}</details>`:''}</div>${jumpNav}<div class="mine-detail-workspace">${projectHtml}${claimHtml}${allocationHtml}${extraHtml}</div>${emptyLine}<div class="mt20">${c.note(m.note, false, '数据与申报说明')}</div></div>`;
}
