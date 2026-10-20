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

// 有对照显示中文；没有对照提示学校补充说明，不展示内部代码。
export function codeLabel(c, type, code) {
  const v = String(code ?? '').trim();
  if (!v) return '<span class="muted small">—</span>';
  const school = schoolCodes[CODE_ALIAS[type] || type]?.[v]?.label;
  if (school) return c.esc(school);
  const hit = CODE_TABLES[type]?.[v];
  if (hit) return c.esc(hit);
  // 学校直接给了中文的，原样显示；未匹配的代码不能猜测含义。
  return /[\u4e00-\u9fa5]/.test(v) ? c.esc(v) : '<span class="muted small">待学校补充说明</span>';
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

// 封面图加载失败（过期、被删）时去掉图片，露出默认底色。页面安全策略不允许写在标签里的 onerror。
if (typeof document !== 'undefined') document.addEventListener('error', e => { if (e.target?.matches?.('.online-cover img')) e.target.remove(); }, true);

export const rosterHandlers = {
  'roster-page': async id => { roster.page = Math.max(1, Number(id) || 1); await refreshRoster(); },
  'roster-reset': async () => { roster = {q: '', active: '', problem: '', org_id: '', school_year: '', page: 1}; const box = document.getElementById('staff-roster'); if (box && rosterCtx) box.outerHTML = await rosterSection(rosterCtx); },
  'roster-reload': async () => refreshRoster()
};

// ---------- 教师详情 ----------
// 最近打开的教师详情里的超星课程，供“显示全部”和“超星课程详情”用。
let cxOpen = {staffNo: '', staffName: '', items: []};
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
  const years = c.table(['学年', '教务学分', '超星学分', '已认定合计', '课程数', '提示', ''], d.years.map(y => [e(y.school_year), c.number(y.jw_credit, 2), c.number(y.cx_credit, 2), `<strong>${c.number(y.total_credit, 2)}</strong>`, c.number(y.courses), [y.pending_courses ? `<span class="badge orange-b">${y.pending_courses} 门待认定</span>` : '', y.excluded_courses ? `<span class="badge gray-b">${y.excluded_courses} 门不计分</span>` : '', y.missing_credit.length ? `<span class="badge orange-b">${y.missing_credit.length} 门缺学分</span>` : ''].join(' ') || '<span class="muted small">—</span>', c.link('两学期明细', 'credit-detail', x.staff_no + '|' + y.school_year+'|staff')]), '还没有授课记录', '教务排课和超星课程同步后显示。');
  cxOpen = {staffNo: x.staff_no, staffName: x.name, items: d.online_courses};
  const online = d.online_courses.length ? `<div id="online-cards">${onlineCards(c, false)}</div>` : '<p class="muted small">没有作为建课人的超星课程。</p>';
  c.modal(`${x.name} · 教师信息`, `<dl class="kv">${kv.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('')}</dl>${warn ? '<div class="mt16">' + warn + '</div>' : ''}<h3 class="mt20">各学年授课学分</h3>${years}<h3 class="mt20">超星课程（作为建课人${d.online_courses.length ? "，共 " + d.online_courses.length + " 门" : ""}）</h3>${online}<p class="small muted mt16">${x.hr_updated_at ? '人事系统更新于 ' + e(x.hr_updated_at.slice(0, 10)) + ' · ' : ''}信息有误请到人事处更正，下次同步自动更新。${'edu' in x || self ? '' : '性别、学历、学位默认只有本人和学校能看到。'}</p>`, '', true);
}

// 超星学期写法“2025-2”转成“2025-2026 第二学期”；教务写法原样显示。
const termText = t => { const m = /^(\d{4})-([12])$/.exec(String(t || '')); return m ? `${m[1]}-${Number(m[1]) + 1} 学年${m[2] === '1' ? '第一' : '第二'}学期` : String(t || ''); };

// 超星课程字段的代码含义（超星课程库接口说明）。
const CX_TYPE = {0: '自建课', 1: '尔雅课', 2: '学银在线', 3: '教发课', 4: '思政课', 5: '项目课'};
const CX_SOURCE = {1: '自建', 2: '克隆', 3: '映射'};
const safeUrl = u => /^https?:\/\//i.test(String(u || '')) ? String(u) : '';
// 封面只用超星自己的图片地址（页面安全策略只放行 *.chaoxing.com 的图片），其余显示默认底色。
const cxCover = u => { const v = safeUrl(u); try { return v && /(^|\.)chaoxing\.com$/i.test(new URL(v).hostname) ? v.replace(/^http:/i, 'https:') : ''; } catch { return ''; } };
// 学时：数值学时优先；超星的 coursePeriod 常是“64/32”这种写法，存在 period_text 里，原样显示。
const cxPeriod = o => o.hours != null ? String(Number(o.hours)) : String(o.period_text || '').trim();
const cxLabel = (map, v) => v == null || v === '' ? '' : (map[v] ?? '待学校补充说明');
// 统计只认超星的 credit（见 reference_data.annual_teaching_credits）；score 只在详情里原样展示，不顶替学分。
// 教学团队：姓名和工号个数对得上时配成“姓名（工号）”，否则分别原样显示。
const cxSplit = v => (Array.isArray(v) ? v : String(v || '').split(/[,，、;；]/)).map(x => String(x).trim()).filter(Boolean);
const cxTeam = o => { const n = cxSplit(o.team_names), s = cxSplit(o.team_staff_nos); return n.length && n.length === s.length ? [n.map((x, i) => `${x}（${s[i]}）`).join('、')] : [n.join('、'), s.join('、')].filter(Boolean); };

function onlineCards(c, all) {
  const list = all ? cxOpen.items : cxOpen.items.slice(0, 3);
  const more = cxOpen.items.length > 3 ? `<p class="small muted mt8">共 ${cxOpen.items.length} 门 · ${all ? c.link('收起', 'online-all', '0') : c.link('显示全部', 'online-all', '1')}</p>` : '';
  return `<div class="online-cards">${list.map((o, i) => onlineCard(c, o, i)).join('')}</div>${more}`;
}

export function onlineCard(c, o, i, selected = false, action = 'online-detail') {
  const e = c.esc;
  const cover = cxCover(o.cover_url), url = safeUrl(o.course_url), period = cxPeriod(o);
  const nature = o.nature ? codeLabel(c, 'nature', o.nature) : '';
  const tags = [cxLabel(CX_TYPE, o.course_type), cxLabel(CX_SOURCE, o.course_source) && '来源：' + cxLabel(CX_SOURCE, o.course_source)].filter(Boolean).map(t => `<span class="badge blue-b">${e(t)}</span>`)
    .concat(nature && !nature.includes('待学校补充说明') ? [`<span class="badge gray-b">${nature}</span>`] : [])
    .concat(String(o.archived) === '1' ? ['<span class="badge gray-b">已归档</span>'] : []).join(' ');
  const credit = o.credit == null ? '<span class="badge orange-b">缺学分</span>' : `<b>${c.number(o.credit, 2)}</b> 学分`;
  const meta = [credit, period && e(period) + ' 学时', o.chapters != null && String(o.chapters).trim() !== '' ? e(o.chapters) + ' 章' : ''].filter(Boolean).join(' · ');
  return `<div class="online-card${String(o.archived) === '1' ? ' archived' : ''}${selected ? ' selected' : ''}" data-course-index="${i}" aria-current="${selected}"><div class="online-cover">${cover ? `<img src="${e(cover)}" alt="" loading="lazy" referrerpolicy="no-referrer">` : ''}<span>超星</span></div><div class="online-body"><strong title="${e(o.course_name)}">${e(o.course_name)}</strong><p class="cell-sub">${e(termText(o.term_name) || '学期未填')}${o.group_name ? ' · ' + e(o.group_name) : ''}</p>${tags ? `<p class="online-tags">${tags}</p>` : ''}<p>${meta}</p>${o.jw_course_code ? `<p class="cell-sub">对应教务课 ${e(o.jw_course_code)}，同学年教务已有时只算一次</p>` : ''}${cxTeam(o).length ? '<p class="cell-sub online-team-note">有教学团队，学分只算给建课人</p>' : ''}<div class="online-actions">${c.act('查看详情', action, String(i), 'sm light')}${url ? `<a class="btn sm" href="${e(url)}" target="_blank" rel="noopener noreferrer">去超星看课</a>` : ''}</div></div></div>`;
}

// ---------- 超星课程详情（字段全部展示，只读） ----------
export function courseFactsHtml(c, o, back = '', declaration = '') {
  const e = c.esc, team = cxTeam(o), period = cxPeriod(o), source = o.origin === 'JW' ? '教务' : '超星';
  const day = v => v ? e(String(v).slice(0, 19).replace('T', ' ')) : '';
  const has = v => v != null && String(v).trim() !== '';
  // 值为空（null、''、false）的行不显示，避免一屏“—”。
  const rows = list => list.filter(([, v]) => v).map(([k, v]) => `<div class="cx-info-pair"><dt>${k}</dt><dd>${v}</dd></div>`).join('');
  const base = rows([[source + '课程号', o.course_code && `<span class="mono">${e(o.course_code)}</span>`], ['学期', e(termText(o.term_name) || '学期未填')],
    ['学分', o.credit == null ? '' : `<strong>${c.number(o.credit, 2)}</strong>`],
    ['学时', period && e(period)], ['章节数', has(o.chapters) && e(o.chapters)],
    ['课程类型', e(cxLabel(CX_TYPE, o.course_type))], ['课程来源', e(cxLabel(CX_SOURCE, o.course_source))],
    ['课程性质', o.nature && codeLabel(c, 'nature', o.nature)], ['所属专业', o.major && e(o.major)], ['课程分组', o.group_name && e(o.group_name)]]);
  const who = rows([['课程归属', o.course_owner && e(o.course_owner)], ['教学团队', team.length ? e(team.join(' / ')) : ''],
    ['对应教务课', o.jw_course_code && `${c.link(o.jw_course_code, 'course-detail', encodeURIComponent(o.jw_course_code) + '|' + back)} <span class="muted small">同一学年教务已有这门课时只算一次</span>`]]);
  const when = rows([['超星建课时间', day(o.created_at_source)], ['超星最后修改', day(o.edited_at_source)]]);
  const desc = String(o.description || '').trim();
  const intro = desc ? `<details class="cx-intro-box mt16"${desc.length <= 160 ? ' open' : ''}><summary>课程简介</summary><div class="cx-intro small">${e(desc)}</div></details>` : '';
  const block = (title, html, extra = '') => html || extra ? `<section class="cx-info-section"><h3>${title}</h3><dl class="cx-info-grid">${html}</dl>${extra}</section>` : '';
  const status = String(o.archived) === '1' ? '<span class="badge gray-b">已归档</span>' : '<span class="badge green-b">使用中</span>';
  const warning = o.credit == null ? `<div class="cx-credit-warning">${c.icon?.('warning') || ''}<strong>缺学分</strong><span>${source === '超星' ? '超星未填写' : '教务未提供'}学分，${o.calculated_credit != null ? '核算学分已按学校课程记录补齐，详见逐学期认定。' : '暂不计入授课学分。'}</span></div>` : '';
  return `<div class="cx-detail-heading"><h3>${e(o.course_name)}</h3><span class="badge blue-b">${source}课程</span>${status}${declaration}</div>${warning}${block('基本信息', base)}${block('归属与计分', who, `<p class="cx-counting-note">${source==='超星'?'学分仅计入建课人，教学团队成员不重复计算。':'教务课程按本人授课记录及学校认定结果核算学分。'}</p>`)}${block('超星记录', when)}${intro}`;
}

function showOnlineDetail(c, i) {
  if (!/^\d+$/.test(String(i))) return;
  const o = cxOpen.items[Number(i)];
  if (!o) return;
  const e = c.esc, url = safeUrl(o.course_url), detail = courseFactsHtml(c, o, 'cx:' + i);
  const foot = `<span class="cx-detail-note">信息有误请在超星修改，待学校同步后更新。</span>${url ? `<a class="btn primary" href="${e(url)}" target="_blank" rel="noopener noreferrer">去超星看课</a>` : ''}${cxOpen.staffNo ? c.act('返回教师信息', 'staff-detail', cxOpen.staffNo) : ''}`;
  const workspace = typeof document !== 'undefined' && document.getElementById('cx-course-workspace');
  if (workspace) {
    const panel = workspace.querySelector('.cx-course-detail');
    panel.innerHTML = detail;
    panel.scrollTop = 0;
    workspace.querySelectorAll('[data-course-index]').forEach(card => {
      const selected = card.dataset.courseIndex === String(Number(i));
      card.classList.toggle('selected', selected);
      card.setAttribute('aria-current', String(selected));
    });
    document.getElementById('cx-course-footer').innerHTML = foot;
    return;
  }
  c.modal(`${cxOpen.staffName || o.course_name} · ${cxOpen.staffName ? '教师信息' : '超星课程'}`, `<div id="cx-course-workspace" class="cx-course-workspace"><section class="cx-course-list" aria-label="超星课程列表"><h3>超星课程 · 共 ${cxOpen.items.length} 门</h3><div class="cx-course-scroll">${cxOpen.items.map((item, index) => onlineCard(c, item, index, index === Number(i))).join('')}</div></section><section class="cx-course-detail" aria-label="课程详情">${detail}</section></div>`, `<div id="cx-course-footer">${foot}</div>`, true, '个人培训 / 教师信息 / 超星课程');
}

export const onlineHandlers = {
  'online-detail': async (id, c) => showOnlineDetail(c, id),
  'online-all': async (id, c) => { const box = document.getElementById('online-cards'); if (box) box.innerHTML = onlineCards(c, id === '1'); }
};

// ---------- 课程总库详情（所有角色可看单门课） ----------
export async function showCourseDetail(c, code, back='') {
  // back：学年明细的 id，或“cx:序号”表示从超星课程详情点进来的。
  const backBtn = !back ? '' : back.startsWith('mc:') ? c.act('返回课程详情', 'mc-detail', back.slice(3)) : back.startsWith('cx:') ? c.act('返回超星课程', 'online-detail', back.slice(3)) : c.act('返回学年明细', 'credit-detail', back);
  const d = await c.api('/reference/school-courses?' + new URLSearchParams({code, size: 20}));
  const e = c.esc;
  if (!d.items.length) return c.modal(`课程 ${code}`, c.note('课程总库里没有这门课，所以教务授课取不到学分。请联系教务处核对课程号。', true),backBtn);
  const x = d.items[0], ex = x.extra || {};
  const kv = [['课程号', `<span class="mono">${e(x.code)}</span>`], ['学分', x.credit == null ? '<span class="badge red-b">无学分</span>' : `<strong>${c.number(x.credit, 2)}</strong>`], ['总学时', x.hours == null ? '—' : c.number(x.hours, 2)], ['周学时', x.weekly_hours == null ? '—' : c.number(x.weekly_hours, 2)],
    ['开课单位', codeLabel(c, 'unit', x.dept)], ['年度版本', e(x.course_version || '—')],
    ...[['nature', '课程性质'], ['category', '课程类别'], ['attribute', '课程属性'], ['group', '课程大类'], ['teach_mode', '授课方式'], ['exam_mode', '考核方式'], ['manage_dept', '管理单位']].filter(([k]) => ex[k]).map(([k, l]) => [l, codeLabel(c, k, ex[k])])];
  const versions = d.items.length > 1 ? `<h3 class="mt20">所有版本</h3>${c.table(['版本', '学分', '总学时', ''], d.items.map((v, i) => [e(v.course_version || '—'), v.credit == null ? '—' : c.number(v.credit, 2), v.hours == null ? '—' : c.number(v.hours, 2), i === 0 ? '<span class="badge green-b">计分用这一版</span>' : '']))}` : '';
  c.modal(`${x.name}`, `<dl class="kv">${kv.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('')}</dl>${versions}<p class="small muted mt16">来自教务课程总库，只读。学分有误请联系教务处更正，下次同步自动更新。</p>`,backBtn);
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
  // 超星登录名不是工号的老师，在这里认领自己建的超星课（不需要超星密码）。
  const claim = c.me.user?.staff_no ? ' ' + c.link('超星课没显示？认领', 'cx-claim', '') : '';
  let card;
  if (!cy) card = `<section class="card mine-credit"><div class="card-head"><div><h2>本学年授课学分</h2><p>来自教务系统和超星，按课程号查课程总库学分。</p></div></div><p class="card-pad muted">还没有教务或超星授课记录。${claim}</p></section>`;
  else {
    const term = n => cy.details.filter(d => d.term_no === n && d.counted && d.review === 'approved' && d.credit != null).reduce((a, d) => a + Number(d.credit), 0);
    card = `<section class="card mine-credit"><div class="card-head"><div><h2>${e(cy.school_year)} 学年授课学分</h2><p>来自教务系统和超星，按课程号查课程总库学分；两个学期合计，只算学校（教务处）已认定的课。</p></div><div>${c.link('两学期明细', 'credit-detail', cy.staff_no + '|' + cy.school_year)}${claim}</div></div><div class="card-pad mine-credit-body"><div><strong class="mine-credit-total">${c.number(cy.total_credit, 2)}</strong><span class="muted small">已认定学分</span></div><dl><div><dt>第一学期</dt><dd>${c.number(term(1), 2)}</dd></div><div><dt>第二学期</dt><dd>${c.number(term(2), 2)}</dd></div><div><dt>教务</dt><dd>${c.number(cy.jw_credit, 2)}</dd></div><div><dt>超星</dt><dd>${c.number(cy.cx_credit, 2)}</dd></div><div><dt>待认定</dt><dd>${c.number(cy.pending_credit, 2)}</dd></div></dl></div>${cy.pending_courses ? `<div class="card-pad" style="padding-top:0">${c.note(`有 ${cy.pending_courses} 门课（${c.number(cy.pending_credit, 2)} 学分）等学校（教务处）认定，认定后才计学分和积分。`, false)}</div>` : ''}${cy.missing_credit.length ? `<div class="card-pad" style="padding-top:0">${c.note(`有 ${cy.missing_credit.length} 门课（${cy.missing_credit.join('、')}）暂无学分，请联系教务处核对课程总库。`, true)}</div>` : ''}</section>`;
  }
  return {identity, banner, card, empty: !cy, claim};
}
