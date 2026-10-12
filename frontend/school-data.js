// 学校数据中台的人事、授课、课程总库在各角色页面里的展示：教师名册、教师详情、课程详情、本人学分卡片。
// 数据范围和可见字段由服务器决定（/api/reference/staff-roster），这里只负责显示。
'use strict';

// 性别沿用国标常用值；学历、学位必须按学校码表显示，不能猜测学校代码含义。
const CODE_TABLES = {
  gender: {'0': '未知', '1': '男', '2': '女', '9': '未说明'}
};
const PROBLEM_BADGE = {no_account: 'red-b', unit_mismatch: 'orange-b', inactive_teaching: 'orange-b', missing_credit: 'orange-b'};
const PROBLEM_SHORT = {no_account: '未对应账号', unit_mismatch: '单位对不上', inactive_teaching: '不在职但有授课', missing_credit: '缺学分'};

// 学校导入的码表（对接与同步 → 代码对照），优先于上面的国标常用值。
let schoolCodes = {};
const CODE_ALIAS = {manage_dept: 'unit', dept: 'unit'};
export async function loadCodeTables(api) {
  try { schoolCodes = (await api('/reference/code-tables')).tables || {}; } catch { schoolCodes = {}; }
  return schoolCodes;
}

// 有对照显示中文；没有对照显示原代码并标“待码表”。
export function codeLabel(c, type, code) {
  const v = String(code ?? '').trim();
  if (!v) return '<span class="muted small">—</span>';
  const school = schoolCodes[CODE_ALIAS[type] || type]?.[v]?.label;
  if (school) return c.esc(school);
  const hit = CODE_TABLES[type]?.[v];
  if (hit) return c.esc(hit);
  // 学校直接给了中文的，原样显示；只有代码才提示待码表。
  return /[\u4e00-\u9fa5]/.test(v) ? c.esc(v) : `${c.esc(v)}<span class="muted small">（待码表）</span>`;
}

const problemBadges = (c, row) => row.problems.length
  ? row.problems.map(p => `<span class="badge ${PROBLEM_BADGE[p] || 'gray-b'}">${PROBLEM_SHORT[p] || c.esc(p)}${p === 'missing_credit' ? ' ' + row.missing_credit.length + ' 门' : ''}</span>`).join(' ')
  : '<span class="muted small">—</span>';
const activeBadge = row => row.active ? '<span class="badge green-b">在职</span>' : '<span class="badge gray-b">不在职</span>';
const accountBadge = row => row.user_id ? '<span class="badge green-b">已对应</span>' : '<span class="badge red-b">未对应账号</span>';

// ---------- 教师名册（组织管理页） ----------
let roster = {q: '', active: '', problem: '', org_id: '', school_year: '', page: 1};
let rosterCtx = null;

// 从别的页面（如对接与同步的问题数）带着筛选进入名册。
export function presetRoster(values) { roster = {...roster, ...values, page: 1}; }

const rosterTitle = kind => ({dept: '本室教师名册', college: '本院教师名册', school: '全校教师名册'})[kind] || '教师名册';
const rosterScopeNote = kind => kind === 'school'
  ? '学校能看到人事表里全部老师，包括还没对上本系统账号的；没对上账号的老师授课学分算不进积分，请在“账号与权限”里建账号。'
  : '只列已经对上本系统账号的老师。人事表里还没对上账号的老师，由学校管理员在“账号与权限”里处理。';

async function rosterBody(c) {
  const kind = c.me.role.kind;
  const params = {page: roster.page, size: 50};
  for (const k of ['q', 'active', 'problem', 'org_id', 'school_year']) if (roster[k]) params[k] = roster[k];
  let d;
  try { d = await c.api('/reference/staff-roster?' + new URLSearchParams(params)); }
  catch (err) { return `${c.note('读取失败，请稍后重试：' + err.message, true)}<div class="card-pad">${c.act('重试', 'roster-reload', '', 'sm')}</div>`; }
  if (!d.ever_synced) return c.note(kind === 'school' ? '人事数据尚未同步，请到“对接与同步”更新。' : '等待学校同步人事数据。');
  const showCollege = kind === 'school', showDept = kind !== 'dept';
  const head = ['工号', '姓名', ...(showCollege ? ['学院'] : []), ...(showDept ? ['教研室'] : []), '职称', '教职工类别', '在职状态', '本地账号', `${d.school_year} 学分`, '提示', '操作'];
  const rows = d.items.map(x => [
    `<span class="mono">${c.esc(x.staff_no)}</span>`, `<strong>${c.esc(x.name)}</strong>`,
    ...(showCollege ? [x.college_name ? c.esc(x.college_name) : `<span class="muted small">人事单位：${c.esc(x.hr_org_name || '—')}</span>`] : []),
    ...(showDept ? [c.esc(x.org_name || '—')] : []),
    c.esc(x.title || '—'), codeLabel(c, 'staff_type', x.staff_type), activeBadge(x), accountBadge(x),
    `<strong>${c.number(x.total_credit, 2)}</strong>`, problemBadges(c, x), c.link('查看', 'staff-detail', x.staff_no)]);
  const filtered = ['q', 'active', 'problem', 'org_id'].some(k => roster[k]);
  const pages = d.total > d.size ? `<div class="pagination"><span>共 ${c.number(d.total)} 人 · 第 ${d.page} 页</span><div class="pages"><button data-action="roster-page" data-id="${d.page - 1}" ${d.page <= 1 ? 'disabled' : ''}>上一页</button><button class="active">${d.page}</button><button data-action="roster-page" data-id="${d.page + 1}" ${d.page * d.size >= d.total ? 'disabled' : ''}>下一页</button></div></div>` : `<div class="pagination"><span>共 ${c.number(d.total)} 人</span></div>`;
  return (d.private_fields ? '' : ``) +
    (d.items.length ? c.table(head, rows) : `<div class="empty"><h3>${filtered ? '没有符合条件的老师' : '本范围还没有老师'}</h3><p>${filtered ? '可以清空筛选再看。' : '老师账号对上人事表工号后会出现在这里。'}</p>${filtered ? c.act('清空筛选', 'roster-reset', '', 'sm') : ''}</div>`) + pages;
}

function rosterFilters(c) {
  const kind = c.me.role.kind;
  const orgs = (c.orgs || []).filter(o => o.active !== false && o.kind !== 'school');
  const orgSelect = kind === 'dept' ? '' : `<select name="org_id" aria-label="组织"><option value="">${kind === 'school' ? '全部学院和教研室' : '全部教研室'}</option>${orgs.map(o => `<option value="${c.esc(o.id)}" ${roster.org_id === o.id ? 'selected' : ''}>${o.kind === 'dept' ? '　' : ''}${c.esc(o.name)}</option>`).join('')}</select>`;
  const now = new Date(), y0 = now.getMonth() >= 8 ? now.getFullYear() : now.getFullYear() - 1;
  const years = [0, 1, 2].map(i => `${y0 - i}-${y0 - i + 1}`);
  const yearSelect = `<select name="school_year" aria-label="学年">${years.map((y, i) => `<option value="${i ? y : ''}" ${(roster.school_year || '') === (i ? y : '') ? 'selected' : ''}>${y} 学年${i ? '' : '（本学年）'}</option>`).join('')}</select>`;
  return `<form id="roster-filters" class="filterbar"><input name="q" placeholder="姓名或工号" aria-label="姓名或工号" maxlength="40" value="${c.esc(roster.q)}">${orgSelect}${yearSelect}<select name="active" aria-label="在职状态"><option value="">在职状态：全部</option><option value="true" ${roster.active === 'true' ? 'selected' : ''}>在职</option><option value="false" ${roster.active === 'false' ? 'selected' : ''}>不在职</option></select><label class="inline-check"><input type="checkbox" name="problem" value="true" ${roster.problem === 'true' ? 'checked' : ''}>只看有问题的</label><button class="btn primary" type="submit">筛选</button>${c.act('重置', 'roster-reset', '', 'text')}</form>`;
}

export async function rosterSection(c) {
  rosterCtx = c;
  const kind = c.me.role.kind;
  return `<section class="card mt20" id="staff-roster"><div class="card-head"><div><h2>${rosterTitle(kind)}</h2><p>人事同步 · 只读</p></div></div>${rosterFilters(c)}${c.note(rosterScopeNote(kind),false,'名册范围')}<div id="staff-roster-body">${await rosterBody(c)}</div></section>`;
}

async function refreshRoster() {
  const box = document.getElementById('staff-roster-body');
  if (!box || !rosterCtx) return;
  box.innerHTML = '<p class="card-pad muted">正在读取…</p>';
  box.innerHTML = await rosterBody(rosterCtx);
}

// 测试环境（node）没有 document，只在浏览器里挂监听。
if (typeof document !== 'undefined') document.addEventListener('submit', e => {
  if (e.target.id !== 'roster-filters') return;
  e.preventDefault();
  const f = new FormData(e.target);
  roster = {q: String(f.get('q') || '').trim(), active: String(f.get('active') || ''), problem: f.get('problem') ? 'true' : '', org_id: String(f.get('org_id') || ''), school_year: String(f.get('school_year') || ''), page: 1};
  refreshRoster();
});

export const rosterHandlers = {
  'roster-page': async id => { roster.page = Math.max(1, Number(id) || 1); await refreshRoster(); },
  'roster-reset': async () => { roster = {q: '', active: '', problem: '', org_id: '', school_year: '', page: 1}; const box = document.getElementById('staff-roster'); if (box && rosterCtx) box.outerHTML = await rosterSection(rosterCtx); },
  'roster-reload': async () => refreshRoster()
};

// ---------- 教师详情 ----------
export async function showStaffDetail(c, staffNo) {
  const d = await c.api('/reference/staff-roster/' + encodeURIComponent(staffNo));
  const x = d.staff, e = c.esc;
  const self = c.me.user?.staff_no && c.me.user.staff_no === x.staff_no;
  const kv = [['工号', `<span class="mono">${e(x.staff_no)}</span>`], ['人事单位', e(x.hr_org_name || '—')], ['本系统组织', e([x.college_name, x.org_name].filter(Boolean).join(' / ') || '—')],
    ['职称', e(x.title || '—')], ['职务', e(x.duty || '—')], ['岗位', e([x.post_name, x.post_type].filter(Boolean).join(' · ') || '—')],
    ['教职工类别', codeLabel(c, 'staff_type', x.staff_type)], ['在职状态', activeBadge(x) + (x.hr_status_code ? ' ' + codeLabel(c, 'hr_status', x.hr_status_code) : '')],
    ...('edu' in x ? [['性别', codeLabel(c, 'gender', x.gender)], ['学历', codeLabel(c, 'edu', x.edu)], ['学位', codeLabel(c, 'degree', x.degree)]] : [])];
  const warn = [
    !x.user_id ? c.note('这位老师的工号在本系统没有账号，授课学分算不进积分。请在“账号与权限”里建账号。', true) : '',
    x.problems.includes('unit_mismatch') ? c.note(`人事单位“${x.hr_org_name}”和本系统组织不一致，请学校管理员核对组织设置。`, true) : '',
    x.problems.includes('inactive_teaching') ? c.note('人事状态为不在职，但本学年还有授课记录，请核对。', true) : ''].join('');
  const years = c.table(['学年', '教务学分', '超星学分', '合计', '课程数', '提示', ''], d.years.map(y => [e(y.school_year), c.number(y.jw_credit, 2), c.number(y.cx_credit, 2), `<strong>${c.number(y.total_credit, 2)}</strong>`, c.number(y.courses), y.missing_credit.length ? `<span class="badge orange-b">${y.missing_credit.length} 门缺学分</span>` : '<span class="muted small">—</span>', c.link('两学期明细', 'credit-detail', x.staff_no + '|' + y.school_year+'|staff')]), '还没有授课记录', '教务排课和超星课程同步后显示。');
  const online = d.online_courses.length ? `<div class="online-cards">${d.online_courses.slice(0, 6).map(o => onlineCard(c, o)).join('')}</div>${d.online_courses.length > 6 ? `<p class="small muted mt8">共 ${d.online_courses.length} 门，完整列表在“授课与学分 → 授课明细”里筛“超星”。</p>` : ''}` : '<p class="muted small">没有作为建课人的超星课程。</p>';
  c.modal(`${x.name} · 教师信息`, `<dl class="kv">${kv.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('')}</dl>${warn ? '<div class="mt16">' + warn + '</div>' : ''}<h3 class="mt20">各学年授课学分</h3>${years}<h3 class="mt20">超星课程（建课人）</h3>${online}<p class="small muted mt16">${x.hr_updated_at ? '人事系统更新于 ' + e(x.hr_updated_at.slice(0, 10)) + ' · ' : ''}信息有误请到人事处更正，下次同步自动更新。${'edu' in x || self ? '' : '性别、学历、学位默认只有本人和学校能看到。'}</p>`, '', true);
}

// 超星学期写法“2025-2”转成“2025-2026 第二学期”；教务写法原样显示。
const termText = t => { const m = /^(\d{4})-([12])$/.exec(String(t || '')); return m ? `${m[1]}-${Number(m[1]) + 1} 学年${m[2] === '1' ? '第一' : '第二'}学期` : String(t || ''); };

function onlineCard(c, o) {
  const e = c.esc;
  const safeUrl = u => /^https?:\/\//i.test(String(u || '')) ? String(u) : '';
  const cover = safeUrl(o.cover_url), url = safeUrl(o.course_url);
  return `<div class="online-card${String(o.archived) === '1' ? ' archived' : ''}"><div class="online-cover">${cover ? `<img src="${e(cover)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">` : ''}<span>超星</span></div><div class="online-body"><strong>${e(o.course_name)}</strong><p class="cell-sub">${e(termText(o.term_name))}${o.group_name ? ' · ' + e(o.group_name) : ''}</p><p><b>${o.credit == null ? '—' : c.number(o.credit, 2)}</b> 学分 · ${o.hours == null ? '—' : c.number(o.hours, 0)} 学时${o.chapters ? ' · ' + e(o.chapters) + ' 章' : ''}</p>${o.jw_course_code ? `<p class="cell-sub">对应教务课 ${e(o.jw_course_code)}，同学年教务已有时只算一次</p>` : ''}${String(o.archived) === '1' ? '<span class="badge gray-b">已归档</span> ' : ''}${url ? `<a class="btn sm" href="${e(url)}" target="_blank" rel="noopener noreferrer">去超星看课</a>` : ''}</div></div>`;
}

// ---------- 课程总库详情（所有角色可看单门课） ----------
export async function showCourseDetail(c, code, back='') {
  const d = await c.api('/reference/school-courses?' + new URLSearchParams({code, size: 20}));
  const e = c.esc;
  if (!d.items.length) return c.modal(`课程 ${code}`, c.note('课程总库里没有这门课，所以教务授课取不到学分。请联系教务处核对课程号。', true),back?c.act('返回学年明细','credit-detail',back):'');
  const x = d.items[0], ex = x.extra || {};
  const kv = [['课程号', `<span class="mono">${e(x.code)}</span>`], ['学分', x.credit == null ? '<span class="badge red-b">无学分</span>' : `<strong>${c.number(x.credit, 2)}</strong>`], ['总学时', x.hours == null ? '—' : c.number(x.hours, 2)], ['周学时', x.weekly_hours == null ? '—' : c.number(x.weekly_hours, 2)],
    ['开课单位', codeLabel(c, 'unit', x.dept)], ['年度版本', e(x.course_version || '—')],
    ...[['nature', '课程性质'], ['category', '课程类别'], ['attribute', '课程属性'], ['group', '课程大类'], ['teach_mode', '授课方式'], ['exam_mode', '考核方式'], ['manage_dept', '管理单位']].filter(([k]) => ex[k]).map(([k, l]) => [l, codeLabel(c, k, ex[k])])];
  const versions = d.items.length > 1 ? `<h3 class="mt20">所有版本</h3>${c.table(['版本', '学分', '总学时', ''], d.items.map((v, i) => [e(v.course_version || '—'), v.credit == null ? '—' : c.number(v.credit, 2), v.hours == null ? '—' : c.number(v.hours, 2), i === 0 ? '<span class="badge green-b">计分用这一版</span>' : '']))}` : '';
  c.modal(`${x.name}`, `<dl class="kv">${kv.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('')}</dl>${versions}<p class="small muted mt16">来自教务课程总库，只读。学分有误请联系教务处更正，下次同步自动更新。</p>`,back?c.act('返回学年明细','credit-detail',back):'');
}

// ---------- 个人培训：人事抬头和本学年学分卡片 ----------
export async function mineSchoolData(c) {
  const [r, credits] = await Promise.all([
    c.api('/reference/staff-roster?size=1').catch(() => null),
    c.can('records.read') ? c.api('/reference/teacher-credits?' + new URLSearchParams({size: 1, detail: 'true'})).catch(() => null) : null]);
  const me = r?.items?.[0];
  const e = c.esc;
  let identity = '', banner = '';
  if (me) identity = `<p class="mine-identity">${e(me.name)} · <span class="mono">${e(me.staff_no)}</span> · ${e([me.college_name, me.org_name].filter(Boolean).join(' ') || me.hr_org_name || '')}${me.title ? ' · ' + e(me.title) : ''}${me.duty ? ' · ' + e(me.duty) : ''} · ${c.link('人事信息', 'staff-detail', me.staff_no)}</p>`;
  else if (r && r.ever_synced && c.me.user?.staff_no) banner = c.note('你的工号在学校人事系统里查不到，授课学分暂时算不进积分。请联系学校管理员核对工号。', true);
  const cy = credits?.items?.[0];
  if (!c.can('records.read')) return {identity, banner, card: '', empty: false};
  let card;
  if (!cy) card = `<section class="card mine-credit"><div class="card-head"><div><h2>本学年授课学分</h2><p>来自教务系统和超星，按课程号查课程总库学分。</p></div></div><p class="card-pad muted">还没有教务或超星授课记录。</p></section>`;
  else {
    const term = n => cy.details.filter(d => d.term_no === n && d.counted && d.credit != null).reduce((a, d) => a + Number(d.credit), 0);
    card = `<section class="card mine-credit"><div class="card-head"><div><h2>${e(cy.school_year)} 学年授课学分</h2><p>来自教务系统和超星，按课程号查课程总库学分；两个学期合计。</p></div>${c.link('两学期明细', 'credit-detail', cy.staff_no + '|' + cy.school_year)}</div><div class="card-pad mine-credit-body"><div><strong class="mine-credit-total">${c.number(cy.total_credit, 2)}</strong><span class="muted small">合计学分</span></div><dl><div><dt>第一学期</dt><dd>${c.number(term(1), 2)}</dd></div><div><dt>第二学期</dt><dd>${c.number(term(2), 2)}</dd></div><div><dt>教务</dt><dd>${c.number(cy.jw_credit, 2)}</dd></div><div><dt>超星</dt><dd>${c.number(cy.cx_credit, 2)}</dd></div></dl></div>${cy.missing_credit.length ? `<div class="card-pad" style="padding-top:0">${c.note(`有 ${cy.missing_credit.length} 门课（${cy.missing_credit.join('、')}）暂无学分，请联系教务处核对课程总库。`, true)}</div>` : ''}</section>`;
  }
  return {identity, banner, card, empty: !cy};
}
