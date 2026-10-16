// 老师发起的申请（社会培训课申报、培训课程申请、培训基地申请）：进度、详情与办理、我的申请、申请表。
// 只调用 /api/applications；谁能办、回避、代办、版本和材料都由后端核对，这里按后端给的 permissions 显示按钮。
let c = null, opened = null;

export const AUDIENCE = ['企业职工', '社区居民', '退役军人', '新型职业农民', '中小学教师', '机关事业单位人员', '待业及转岗人员', '老年学员'];
export const TEACHING_MODES = [['lecture', '讲授'], ['practice', '实训实操'], ['case', '案例研讨'], ['onsite', '现场教学'], ['online', '线上自学']];
export const IDEOLOGY = [['course_ideology', '课程思政'], ['ideology_course', '思政课程'], ['none', '无']];
const BASE_USAGES = [['practice', '实践教学基地'], ['ideology', '思政实践教学基地']];
const TONE = {green: 'ok', red: 'warn', blue: '', gray: 'muted'};

// 后端存的是 UTC，显示成北京时间（和页面其他地方的 ts() 一致）。
const time = v => {
  if (!v) return '';
  const d = new Date(/(?:Z|[+-]\d{2}:\d{2})$/.test(v) ? v : v + 'Z');
  return isNaN(d) ? String(v) : new Date(d.getTime() + 8 * 3600e3).toISOString().slice(0, 16).replace('T', ' ');
};

// 三处共用的进度：详情顶部（完整）、我的申请列表和首页（compact，只有节点和一句话）。
export function progressHtml(p, esc, {compact = false} = {}) {
  if (!p) return '';
  const tags = n => [n.acting_for, n.same_person].filter(Boolean).map(t => `<span class="handling-tag">${esc(t)}</span>`).join('');
  const nodes = p.nodes.map((n, i) => {
    const mark = n.state === 'done' ? '✓' : n.state === 'returned' ? '!' : String(i + 1);
    const sub = compact ? '' : [n.who ? esc(n.who) : '', n.at ? esc(time(n.at)) : '', n.state === 'current' && n.waiting_days ? '已等 ' + n.waiting_days + ' 天' : ''].filter(Boolean).join(' · ');
    return `<li class="${n.state}"><i>${mark}</i><span>${esc(n.label)}</span>${sub ? `<small>${sub}</small>` : ''}${compact ? '' : tags(n)}${!compact && n.reason ? `<small class="apply-reason">退回原因：${esc(n.reason)}</small>` : ''}</li>`;
  }).join('');
  return `<div class="apply-progress ${compact ? 'compact' : ''}" role="group" aria-label="${esc(p.label || '审批进度')}：${esc(p.text)}"><ol class="apply-steps">${nodes}</ol>` +
    `<p class="apply-headline ${TONE[p.tone] || ''}"><b>${esc(p.text)}</b>${!compact && p.headline ? ' ' + esc(p.headline) : ''}</p></div>`;
}

function events(list) {
  return c.eventsHtml((list || []).map(e => ({...e, after: {handling: e.handling}})));
}

async function load(id) {
  opened = await c.api('/applications/' + id);
  return opened;
}

export async function showApplication(id) {
  const d = await load(id), e = c.esc, x = d.item, p = d.permissions;
  const rows = d.fields.map(([k, v]) => `<dt>${e(k)}</dt><dd>${/^https?:\/\//.test(v) ? `<a href="${e(v)}" target="_blank" rel="noopener">${e(v)}</a>` : e(v)}</dd>`).join('');
  const files = d.attachments.length ? `<ul class="apply-files">${d.attachments.map(f => `<li>${e(f.name)}</li>`).join('')}</ul>` : '<p class="muted small">还没有上传材料。</p>';
  const body = `<div class="between"><div><h2>${e(x.name)}</h2><p class="muted small mt8">${e(d.label)} · 申请人 ${e(d.applicant?.name || '')} · ${e(d.org_name)}</p></div><span class="badge ${d.progress.tone === 'green' ? 'green-b' : d.progress.tone === 'red' ? 'red-b' : 'blue-b'}">${e(d.state_label)}</span></div>` +
    progressHtml({...d.progress, headline: d.progress.headline + (d.applicant?.id === c.me.user.id && d.progress.tone === 'blue' ? '无需你操作。' : '')}, e) + `<dl class="kv mt16">${rows}</dl><h3 class="mt16">申请材料</h3>${files}<h3 class="mt16">办理记录</h3>${events(d.events)}`;
  const foot = [p.approve ? c.act('通过', 'app-approve', x.id, 'primary') : '', p.return ? c.act('退回', 'app-return', x.id, 'danger') : '',
    p.edit ? c.act('补正资料', 'app-edit', x.id, 'primary') : '', p.submit ? c.act('重新提交', 'app-submit', x.id, p.edit ? '' : 'primary') : '',
    p.upload ? c.act('上传材料', 'app-upload', x.id) : '', p.withdraw ? c.act('撤回', 'app-withdraw', x.id, 'light') : '', c.act('关闭', 'close')].join('');
  c.modal(d.label + ' · ' + x.name, body, foot, true);
}

function decide(id, action) {
  const d = opened, label = {approve: '通过', return: '退回', submit: '重新提交', withdraw: '撤回'}[action];
  const level = (d.progress.nodes.find(n => n.state === 'current') || {}).label || '';
  const hint = action === 'return' ? '写清楚要补什么。老师补正后从这一级接着审，不从头走。' : action === 'approve' ? (level ? '本次办理：' + level + '。' : '') + '通过后自动转到下一级，最后一级通过即生效。' : action === 'withdraw' ? '撤回后可修改再提交，会从第一级重新审。' : '会从退回的那一级接着审。';
  const value = {approve: '材料齐全，同意', return: '', submit: '已按意见补正，重新提交', withdraw: '撤回修改'}[action];
  return c.formModal(label + '：' + d.item.name, c.note(hint) + c.reasonFields(value, action === 'return' ? '退回原因' : '办理意见'), async v => {
    await c.api('/applications/' + id + '/actions', {method: 'POST', body: {action, expected_version: d.item.version, reason: v.reason, basis: v.basis}});
    c.closeModal(); c.toast(label + '完成'); await c.renderKeep(); await showApplication(id);
  }, {submit: '确认' + label, returnTo: () => showApplication(id)});
}

function upload(id) {
  const d = opened;
  return c.formModal('上传材料：' + d.item.name, c.field('file', '材料文件', 'file', '', {accept: '.pdf,.png,.jpg,.jpeg', full: true, hint: '课件、审查记录、协议等，支持 .pdf、.png、.jpg，单个最大 10 兆字节。'}) + c.field('reason', '材料说明', 'text', '补充申请材料', {full: true}), async (v, f) => {
    const file = f.querySelector('#f-file').files[0];
    if (!file) throw Error('请选择文件');
    const fd = new FormData(); fd.set('file', file); fd.set('reason', v.reason); fd.set('expected_version', String(d.item.version));
    await c.api('/attachments/social_resource/' + id, {method: 'POST', body: fd});
    c.closeModal(); c.toast('已上传'); await showApplication(id);
  }, {submit: '上传', returnTo: () => showApplication(id)});
}

// ---- 申请表 ----

function audienceFields(value) {
  const picked = new Set(String(value || '').split('、').filter(Boolean));
  const other = [...picked].find(x => x.startsWith('其他：'));
  return `<fieldset class="form-field full apply-tags"><legend>面向对象 <b>*</b></legend><div class="apply-tag-row">${AUDIENCE.map((t, i) => `<label><input type="checkbox" name="aud_${i}" ${picked.has(t) ? 'checked' : ''}>${c.esc(t)}</label>`).join('')}</div>` +
    `<input name="aud_other" aria-label="其他面向对象" placeholder="其他（选填，如：家政服务人员）" maxlength="100" value="${c.esc(other ? other.slice(3) : '')}"><p class="hint">这门课准备面向哪些社会学员，可多选。</p></fieldset>`;
}

function audienceValue(v) {
  const list = AUDIENCE.filter((t, i) => v['aud_' + i]);
  if (String(v.aud_other || '').trim()) list.push('其他：' + v.aud_other.trim());
  return list.join('、');
}

function coursewareFields(cw = {}) {
  return c.field('cw_checked', '课件审查', 'checkbox', !!cw.checked, {required: false, checkLabel: '学院已审查课件（政治方向、知识产权、内容质量）', full: true}) +
    c.field('cw_reviewer', '审查人或审查组', 'text', cw.reviewer || '', {required: false}) + c.field('cw_on', '审查日期', 'date', cw.reviewed_on || '', {required: false}) +
    c.field('cw_ref', '审查记录编号', 'text', cw.reference || '', {required: false});
}

const coursewareValue = v => ({checked: !!v.cw_checked, reviewer: v.cw_reviewer || '', reviewed_on: v.cw_on || null, reference: v.cw_ref || ''});

// 社会培训课：老师从“我的课程”里选一门本人的教务或超星课申报。course 为“我的课程”里那一行。
export function teachingCourseForm(course, existing = null) {
  const e = c.esc, d = existing?.item?.data || {};
  const facts = `<div class="apply-source"><span class="badge ${course.origin === 'CX' ? 'green-b' : 'blue-b'}">${course.origin === 'CX' ? '超星' : '教务'}</span><strong>${e(course.course_name)}</strong><span>${e(course.course_code)} · ${e(course.term_name)}${course.credit != null ? ' · ' + e(course.credit) + ' 学分' : ''}${course.hours != null ? ' · ' + e(course.hours) + ' 学时' : ''}</span></div>`;
  const body = facts + c.note('把这门课申报为社会培训课：教研室审核 → 学院审批 → 学校（继续教育学院）审批，通过后进入培训课程库，按学校设置给你记积分。同一门课只申报一次。') +
    c.field('hours', '培训学时', 'number', d.hours ?? course.hours ?? '', {required: false, min: 0, step: '0.5', hint: '默认用这门课的学时，按社会培训实际安排可调整。'}) +
    c.field('teaching_mode', '教学方式', 'select', d.teaching_mode || 'lecture', {options: TEACHING_MODES}) +
    c.field('ideology', '思政属性', 'select', d.ideology || 'course_ideology', {options: IDEOLOGY}) +
    audienceFields(d.audience) + c.field('intro', '课程简介', 'textarea', d.intro || course.description || '', {required: false, full: true, hint: '面向社会学员怎么上、学完能做什么。'}) +
    coursewareFields(d.courseware) + c.field('reason', '申报说明', 'text', existing ? '按意见补正' : '申报为社会培训课', {full: true});
  return c.formModal(existing ? '补正社会培训课申报' : '申报为社会培训课', body, async v => {
    const data = {source: 'teaching', course_term_id: course.id, hours: v.hours, teaching_mode: v.teaching_mode, ideology: v.ideology, audience: audienceValue(v), intro: v.intro || '', courseware: coursewareValue(v)};
    if (!data.audience) throw Error('请至少选择一类面向对象');
    const r = existing ? await c.api('/applications/courses/' + existing.item.id, {method: 'PUT', body: {data, reason: v.reason, expected_version: existing.item.version}})
      : await c.api('/applications/courses', {method: 'POST', body: {data, reason: v.reason}});
    c.closeModal(); c.toast(existing ? '已保存，请点“重新提交”' : '已提交，等待教研室审核'); await c.renderKeep(); await showApplication(r.item.id);
  }, {wide: true, submit: existing ? '保存补正' : '提交申报', returnTo: existing ? () => showApplication(existing.item.id) : null});
}

// 培训课程申请：不来自本人学历课的培训课程（学院、学校可以代老师登记）。
export function manualCourseForm(existing = null) {
  const d = existing?.item?.data || {};
  const who = c.me.role.kind === 'teacher' ? '' : c.teacherField(d.teacher_id || '', 'teacher_id', '主讲教师（输入工号或姓名检索）');
  const body = c.note('学院审批 → 学校（继续教育学院）审批，通过后进入培训课程库。') + who +
    c.field('code', '课程编号', 'text', d.code || '', {readonly: !!existing}) + c.field('name', '课程名称', 'text', existing?.item?.name || '') +
    c.field('project_code', '关联项目编号', 'text', d.project_code || '', {required: false, hint: '不关联项目可留空。'}) +
    c.field('hours', '学时', 'number', d.hours ?? '', {min: 0, step: '0.5'}) +
    c.field('teaching_mode', '教学方式', 'select', d.teaching_mode || 'lecture', {options: TEACHING_MODES}) +
    c.field('ideology', '思政属性', 'select', d.ideology || 'course_ideology', {options: IDEOLOGY}) +
    c.field('intro', '课程简介', 'textarea', d.intro || '', {required: false, full: true}) + coursewareFields(d.courseware) +
    c.field('reason', '申请说明', 'text', existing ? '按意见补正' : '申请培训课程', {full: true});
  return c.formModal(existing ? '补正培训课程申请' : '申请培训课程', body, async v => {
    const data = {source: 'manual', code: v.code, name: v.name, project_code: v.project_code || '', teacher_id: v.teacher_id || null, hours: v.hours,
      teaching_mode: v.teaching_mode, ideology: v.ideology, intro: v.intro || '', courseware: coursewareValue(v)};
    const r = existing ? await c.api('/applications/courses/' + existing.item.id, {method: 'PUT', body: {data, reason: v.reason, expected_version: existing.item.version}})
      : await c.api('/applications/courses', {method: 'POST', body: {data, reason: v.reason}});
    c.closeModal(); c.toast(existing ? '已保存，请点“重新提交”' : '已提交，等待学院审批'); await c.renderKeep(); await showApplication(r.item.id);
  }, {wide: true, submit: existing ? '保存补正' : '提交申请', returnTo: existing ? () => showApplication(existing.item.id) : null});
}

export function baseForm(existing = null) {
  const d = existing?.item?.data || {};
  const who = c.me.role.kind === 'teacher' ? '' : c.teacherField(d.teacher_id || '', 'teacher_id', '基地负责人（输入工号或姓名检索）');
  const used = new Set(d.usages || ['practice']);
  const body = c.note('学院审批 → 学校（继续教育学院）审批，通过后进入基地清单。') + who +
    c.field('code', '来源编号', 'text', existing?.item?.code || '', {readonly: !!existing, hint: '协议编号或学院登记编号。'}) + c.field('name', '基地名称', 'text', existing?.item?.name || '') +
    `<fieldset class="form-field full apply-tags"><legend>基地用途 <b>*</b></legend><div class="apply-tag-row">${BASE_USAGES.map(([k, l]) => `<label><input type="checkbox" name="usage_${k}" ${used.has(k) ? 'checked' : ''}>${c.esc(l)}</label>`).join('')}</div></fieldset>` +
    c.field('onsite', '校内 / 校外', 'select', d.onsite === false ? 'no' : 'yes', {options: [['yes', '校内'], ['no', '校外']]}) +
    c.field('partner', '共建单位', 'text', d.partner || '', {required: false, hint: '校外基地必填。'}) + c.field('established_on', '设立日期', 'date', d.established_on || '') +
    c.field('location', '地点', 'text', d.location || '', {required: false}) + c.field('recognition', '认定依据', 'textarea', d.recognition || '', {full: true, hint: '共建协议、学校发文或学院会议纪要。'}) +
    c.field('reason', '申请说明', 'text', existing ? '按意见补正' : '申请培训基地', {full: true});
  return c.formModal(existing ? '补正培训基地申请' : '申请培训基地', body, async v => {
    const data = {code: v.code, name: v.name, teacher_id: v.teacher_id || null, usages: BASE_USAGES.map(([k]) => k).filter(k => v['usage_' + k]), onsite: v.onsite === 'yes',
      partner: v.partner || '', established_on: v.established_on, location: v.location || '', recognition: v.recognition};
    if (!data.usages.length) throw Error('请选择基地用途');
    const r = existing ? await c.api('/applications/bases/' + existing.item.id, {method: 'PUT', body: {data, reason: v.reason, expected_version: existing.item.version}})
      : await c.api('/applications/bases', {method: 'POST', body: {data, reason: v.reason}});
    c.closeModal(); c.toast(existing ? '已保存，请点“重新提交”' : '已提交，等待学院审批'); await c.renderKeep(); await showApplication(r.item.id);
  }, {wide: true, submit: existing ? '保存补正' : '提交申请', returnTo: existing ? () => showApplication(existing.item.id) : null});
}

async function edit(id) {
  const d = opened?.item?.id === id ? opened : await load(id);
  if (d.flow === 'base') return baseForm(d);
  if (d.flow === 'course') return manualCourseForm(d);
  const course = d.item.data.course || {};
  return teachingCourseForm({id: d.item.data.course_term_id, origin: course.origin, course_name: course.course_name, course_code: course.course_code,
    term_name: course.term_name, credit: course.credit, hours: course.hours, description: course.description}, d);
}

// ---- 我的申请 ----

export async function myApplicationsHtml(ctx) {
  c = ctx;
  const e = c.esc;
  let m;
  try { m = await c.api('/applications/mine'); } catch (err) { return c.note('我的申请读取失败：' + err.message, true); }
  const n = m.counts;
  const chips = `<div class="apply-counts"><span>审批中 <b>${n.pending}</b></span><span class="${n.returned ? 'warn' : ''}">待我补正 <b>${n.returned}</b></span><span>已办结 <b>${n.done}</b></span></div>`;
  const open = x => x.type === 'social_project' ? c.act('查看', 'social-detail', 'social_project|' + x.id, 'sm') : c.act(x.state === 'RETURNED' ? '去补正' : '查看', 'app-detail', x.id, x.state === 'RETURNED' ? 'sm primary' : 'sm');
  return `<div class="card"><div class="card-head"><div><h2>我的申请</h2><p>我提交的社会培训课申报、培训课程、培训基地和培训项目，走到哪一级、谁在办，都在这里。</p></div>${chips}</div>` +
    c.table(['申请', '进度', '操作'], m.items.map(x => [`<strong>${e(x.name)}</strong><p class="cell-sub">${e(x.label)} · ${e(x.state_label)}</p>`,
      progressHtml({...x.progress, nodes: x.nodes, label: x.label}, e, {compact: true}), open(x)]), '还没有申请', '在“我的课程”里选一门课申报为社会培训课，或从培训课程、培训基地页面发起申请。') + `</div>`;
}

// 首页卡片：只列还没办结的申请（最多 3 条），没有就不显示。
export async function homeApplicationsHtml(ctx) {
  c = ctx;
  const e = c.esc;
  let m;
  try { m = await c.api('/applications/mine'); } catch { return ''; }
  const open = (m?.items || []).filter(x => x.progress?.tone !== 'green').slice(0, 3);
  if (!open.length) return '';
  const row = x => `<div class="apply-home-row"><div><strong>${e(x.name)}</strong><p class="cell-sub">${e(x.label)}</p></div>${progressHtml({...x.progress, nodes: x.nodes, label: x.label}, e, {compact: true})}` +
    (x.type === 'social_project' ? c.act('查看', 'social-detail', 'social_project|' + x.id, 'sm') : c.act(x.state === 'RETURNED' ? '去补正' : '查看', 'app-detail', x.id, x.state === 'RETURNED' ? 'sm primary' : 'sm')) + `</div>`;
  return `<section class="card"><div class="card-head"><div><h2>我的申请</h2></div>${c.act('全部申请', 'todos-tab', 'mine', 'text')}</div><div class="card-pad">${open.map(row).join('')}</div></section>`;
}

// ---- 我的课程（老师）与在线课程库（教研室、学院、学校） ----

let mine = null, library = null, libFilter = {}, libPage = 1;
const safeUrl = u => /^https?:\/\//i.test(String(u || '')) ? String(u) : '';
// 封面只用超星自己的图片（页面安全策略只放行 *.chaoxing.com）。
const cover = u => { const v = safeUrl(u); try { return v && /(^|\.)chaoxing\.com$/i.test(new URL(v).hostname) ? v.replace(/^http:/i, 'https:') : ''; } catch { return ''; } };
const num = v => v == null || v === '' ? '—' : String(Number(v));
const SOURCE = {1: '自建', 2: '克隆', 3: '映射'};

function statusStrip(x, index, scope) {
  const e = c.esc, a = x.application;
  if (a) return `<div class="mc-status ${a.state === 'ACTIVE' ? 'ok' : a.state === 'RETURNED' ? 'warn' : ''}"><span>社会培训课：${e(a.state_label)}</span>${c.act(a.state === 'RETURNED' ? '去补正' : '看进度', 'app-detail', a.id, 'sm text')}</div>`;
  return scope === 'mine' ? `<div class="mc-status"><span>还没申报为社会培训课</span>${c.act('申报为社会培训课', 'mc-apply', String(index), 'sm primary')}</div>` : `<div class="mc-status muted"><span>未申报</span></div>`;
}

function courseCard(x, index, scope) {
  const e = c.esc, img = cover(x.cover_url), terms = x.terms.length;
  const who = scope === 'library' ? `<p class="cell-sub">${e(x.teacher_name)}${x.matched ? '' : '（没对上老师）'} · ${e(x.org_name || x.college_name)}</p>` : '';
  const stats = `<div class="mc-stats"><span><b>${x.credit == null ? '缺' : num(x.credit)}</b>学分</span><span><b>${x.hours != null ? num(x.hours) : e(x.period_text || '—')}</b>学时</span><span><b>${num(x.chapters)}</b>章节</span></div>`;
  return `<article class="mc-card"><button type="button" class="mc-cover" data-action="${scope === 'mine' ? 'mc-detail' : 'lib-detail'}" data-id="${index}" aria-label="查看 ${e(x.course_name)}">${img ? `<img src="${e(img)}" alt="" loading="lazy" referrerpolicy="no-referrer">` : ''}<span class="mc-origin">${x.origin === 'CX' ? '超星' : '教务'}</span>${terms > 1 ? `<span class="mc-terms">${terms} 个学期</span>` : ''}</button>` +
    `<div class="mc-body"><strong title="${e(x.course_name)}">${e(x.course_name)}</strong>${who}<p class="cell-sub">${e(x.years.join('、'))}${x.course_source ? ' · ' + e(SOURCE[x.course_source] || '') : ''}${x.stale ? ' · 超过一年没更新' : ''}</p>${stats}` +
    `${x.problems.length ? `<p class="mc-problem">${e(x.problems[0])}</p>` : ''}${x.identity.startsWith('JW|') && x.origin === 'CX' ? `<p class="cell-sub">对应教务课 ${e(x.identity.slice(3))}，同学年只算一次</p>` : ''}${statusStrip(x, index, scope)}</div></article>`;
}

export async function myCoursesHtml(ctx, tab, year) {
  c = ctx;
  const e = c.esc;
  mine = await c.api('/applications/teaching-courses');
  const pick = x => !year || x.years.includes(year);
  const list = mine.courses.map((x, i) => [x, i]).filter(([x]) => x.origin === (tab === 'cx' ? 'CX' : 'JW') && pick(x));
  const years = [...new Set(mine.courses.flatMap(x => x.years))].sort().reverse();
  const chips = `<div class="todo-chips" role="group" aria-label="学年">${[['', '全部学年（2020-2021 起）'], ...years.map(y => [y, y + ' 学年'])].map(([v, l]) => `<button type="button" class="btn sm ${(year || '') === v ? 'primary' : 'light'}" data-action="mc-year" data-id="${e(v)}">${e(l)}</button>`).join('')}</div>`;
  const tip = c.note('哪门课适合面向社会学员开设，你就选哪门申报为社会培训课：教研室审核 → 学院审批 → 学校审批，通过后进入培训课程库并给你记积分。同一门课只申报一次。常规学历课堂本身不算积分（积分办法第六条）。', false, '申报说明');
  if (tab === 'cx') return `<div class="card"><div class="card-head"><div><h2>我的超星课（${list.length}）</h2><p>只列你作为建课人的课；同一门课每学期一张卡合成一张。教学团队成员能看到课，积分只算给申报的主讲教师。</p></div></div><div class="card-pad">${chips}${tip}${list.length ? `<div class="mc-cards">${list.map(([x, i]) => courseCard(x, i, 'mine')).join('')}</div>` : '<p class="muted">这个学年没有作为建课人的超星课。</p>'}</div></div>`;
  return `<div class="card"><div class="card-head"><div><h2>我的教务课（${list.length}）</h2><p>按课程号合并，多个学期列在一起。</p></div></div><div class="card-pad">${chips}${tip}</div>` +
    c.table(['课程', '学期', '学分', '学时', '社会培训课', '操作'], list.map(([x, i]) => [`<strong>${e(x.course_name)}</strong><p class="cell-sub mono">${e(x.course_code)}</p>${x.problems.length ? `<p class="mc-problem">${e(x.problems[0])}</p>` : ''}`,
      e(x.terms.map(t => t.term_name).join('、')), x.credit == null ? '<span class="badge orange-b">缺学分</span>' : num(x.credit), num(x.hours),
      x.application ? e(x.application.state_label) : '<span class="muted">未申报</span>',
      x.application ? c.act(x.application.state === 'RETURNED' ? '去补正' : '看进度', 'app-detail', x.application.id, 'sm') : c.act('申报为社会培训课', 'mc-apply', String(i), 'sm primary')]), '这个学年没有教务授课', '教务系统同步后显示。') + `</div>`;
}

async function courseDetail(x, scope) {
  const e = c.esc, url = safeUrl(x.course_url);
  const rows = [['课程名称', e(x.course_name)], ['来源', x.origin === 'CX' ? '超星' + (x.course_source ? '（' + e(SOURCE[x.course_source] || x.course_source) + '）' : '') : '教务'],
    ['课程号', `<span class="mono">${e(x.course_code)}</span>`], ['学分', x.credit == null ? '<span class="badge orange-b">缺学分</span>' : num(x.credit)], ['学时', x.hours != null ? num(x.hours) : e(x.period_text || '—')],
    ['章节数', num(x.chapters)], ...(scope === 'library' ? [['建课人', e(x.teacher_name) + (x.matched ? '' : '（工号没对上账号，等老师认领）')], ['所属', e(x.org_name || x.college_name)]] : []),
    ['教学团队', e(x.team_names || '')], ['对应教务课', x.origin === 'CX' && x.identity.startsWith('JW|') ? e(x.identity.slice(3)) + ' <span class="muted small">同学年教务已有时只算一次</span>' : ''],
    ['超星最后修改', e(String(x.edited_at_source || '').slice(0, 10))]].filter(([k, v]) => ['学分', '学时'].includes(k) || (v && v !== '—'));
  const terms = c.table(['学期', '学年', '学分', '学时', '授课认定'], x.terms.map(t => [e(t.term_name), e(t.school_year), t.credit == null ? '缺学分' : num(t.credit), num(t.hours), e({PENDING: '待认定', APPROVED: '已认定', EXCLUDED: '不计分'}[t.review] || (t.counted === false ? '不重复计算' : '—'))]));
  let progress = '';
  if (x.application) { const d = await c.api('/applications/' + x.application.id).catch(() => null); if (d) progress = '<h3 class="mt16">社会培训课申报进度</h3>' + progressHtml(d.progress, e); }
  const intro = x.description ? `<details class="cx-intro-box mt16"${x.description.length <= 160 ? ' open' : ''}><summary>课程简介</summary><div class="cx-intro small">${e(x.description)}</div></details>` : '';
  const problems = x.problems.map(p => c.note(p, true)).join('');
  const index = (scope === 'mine' ? mine.courses : library.items).indexOf(x);
  const foot = [url ? `<a class="btn" href="${e(url)}" target="_blank" rel="noopener noreferrer">去超星看课 ↗</a>` : '',
    scope === 'mine' && !x.application ? c.act('申报为社会培训课', 'mc-apply', String(index), 'primary') : '',
    x.application ? c.act('查看申报', 'app-detail', x.application.id) : '', c.act('关闭', 'close')].join('');
  c.modal(x.course_name, problems + `<dl class="kv">${rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('')}</dl><h3 class="mt16">开课学期</h3>${terms}${intro}${progress}<p class="small muted mt16">计分按学期逐条算：同一学年教务已有这门课时超星课只算一次。申报为社会培训课后，同一门课只记一次积分，不在别的学年重复记。</p>`, foot, true);
}

export async function libraryHtml(ctx) {
  c = ctx;
  const e = c.esc, f = libFilter;
  library = await c.api('/applications/online-library?' + new URLSearchParams({...f, page: String(libPage)}));
  const d = library, qd = d.quality;
  const tile = (k, n, title, sub) => `<button type="button" class="lib-tile ${f.state === k ? 'active' : ''}" data-action="lib-state" data-id="${k}"><b>${n}</b><span>${title}</span><small>${sub}</small></button>`;
  const quality = `<div class="lib-tiles">${tile('missing_credit', qd.missing_credit, '缺学分', '超星没填学分，暂不计授课学分')}${tile('', qd.linked_jw, '对应教务课', '同学年教务已有时只算一次')}${tile('stale', qd.stale, '超过一年没更新', '近一年没改过内容，可能已停用')}${tile('unmatched', qd.unmatched, '没对上老师', '建课人登录名不是工号，等老师认领')}</div>`;
  const colleges = c.table(['学院', '自建', '克隆', '其他', '合计'], d.colleges.map(x => [e(x.name), x.self, x.clone, x.other, `<strong>${x.total}</strong>`]), '没有在线课程');
  const opt = (name, label, list) => `<select name="${name}" aria-label="${label}"><option value="">${label}</option>${list.map(([v, l]) => `<option value="${e(v)}" ${String(f[name] || '') === String(v) ? 'selected' : ''}>${e(l)}</option>`).join('')}</select>`;
  const orgPick = c.me.role.kind === 'dept' ? '' : opt('org_id', c.me.role.kind === 'school' ? '全部学院' : '全部教研室', c.orgs.filter(o => o.active !== false && (c.me.role.kind === 'school' ? o.kind === 'college' : o.kind === 'dept')).map(o => [o.id, o.name]));
  const bar = `<form id="lib-filters" class="filterbar">${opt('school_year', '全部学年', d.years.map(y => [y, y]))}${orgPick}${opt('source', '自建和克隆', [['1', '自建'], ['2', '克隆'], ['3', '映射']])}${opt('state', '全部状态', [...Object.entries(d.state_labels), ['stale', '超过一年没更新'], ['unmatched', '没对上老师']])}<input name="q" placeholder="课程名、老师或工号" aria-label="搜索" value="${e(f.q || '')}"><button class="btn primary" type="submit">筛选</button>${c.act('重置', 'lib-reset', '', 'text')}</form>`;
  const pages = Math.max(1, Math.ceil(d.total / d.size));
  const pager = `<div class="pagination"><span>共 ${d.total} 门 · 第 ${d.page} / ${pages} 页</span><div class="pages"><button data-action="lib-page" data-id="${d.page - 1}" ${d.page <= 1 ? 'disabled' : ''}>上一页</button><button data-action="lib-page" data-id="${d.page + 1}" ${d.page >= pages ? 'disabled' : ''}>下一页</button></div></div>`;
  return `<div class="card"><div class="card-head"><div><h2>数据质量</h2><p>点格子筛出对应的课。超星每周同步，有误请在超星平台修改。</p></div></div><div class="card-pad">${quality}</div></div>` +
    `<div class="card mt16"><div class="card-head"><div><h2>各学院在线课程</h2></div></div>${colleges}</div>` +
    `<div class="card mt16"><div class="card-head"><div><h2>在线课程（${d.total}）</h2><p>同一门课每学期一张卡合成一张。</p></div></div>${bar}<div class="card-pad">${d.items.length ? `<div class="mc-cards">${d.items.map((x, i) => courseCard(x, i, 'library')).join('')}</div>` : '<p class="muted">没有符合条件的课。</p>'}</div>${pager}</div>`;
}

export function libraryFilterSubmit(form) {
  libFilter = Object.fromEntries([...new FormData(form)].filter(([, v]) => String(v).trim()));
  libPage = 1;
}

// 首页“我的超星课”：本学年在用门数、可计学分、要处理的课（缺学分、被退回）。
export async function homeCoursesHtml(ctx) {
  c = ctx;
  const e = c.esc;
  let d;
  try { d = await c.api('/applications/teaching-courses'); } catch { return ''; }
  if (!Array.isArray(d?.courses)) return '';
  mine = d;
  const cx = d.courses.filter(x => x.origin === 'CX');
  if (!cx.length) return '';
  const now = cx.filter(x => x.years.includes(d.school_year_now));
  const credit = now.reduce((s, x) => s + (x.credit == null ? 0 : Number(x.credit)), 0);
  const todo = cx.map(x => [x, d.courses.indexOf(x)]).filter(([x]) => x.problems.length || x.application?.state === 'RETURNED').slice(0, 3);
  const row = ([x, i]) => `<div class="apply-home-row"><div><strong>${e(x.course_name)}</strong></div><span class="${x.application?.state === 'RETURNED' ? 'red' : 'mc-problem'}">${e(x.application?.state === 'RETURNED' ? '社会培训课申报被退回' : x.problems[0].split('：')[0])}</span>${c.act('查看', 'mc-detail', String(i), 'sm')}</div>`;
  return `<section class="card"><div class="card-head"><div><h2>我的超星课</h2><p>作为建课人 · ${e(d.school_year_now)} 学年</p></div>${c.act('全部 ' + cx.length + ' 门', 'nav-mycourses', 'cx', 'text')}</div><div class="card-pad"><div class="mc-home-stats"><span><b>${now.length}</b>本学年在用</span><span><b>${credit.toFixed(1)}</b>可计学分</span><span><b>${todo.length}</b>需要处理</span></div>${todo.map(row).join('')}</div></section>`;
}

export async function courseAction(action, id, ctx) {
  c = ctx;
  if (action === 'mc-detail') return courseDetail(mine.courses[Number(id)], 'mine');
  if (action === 'lib-detail') return courseDetail(library.items[Number(id)], 'library');
  if (action === 'mc-apply') {
    const x = mine.courses[Number(id)];
    c.closeModal();
    return teachingCourseForm({id: x.id, origin: x.origin, course_name: x.course_name, course_code: x.course_code, term_name: x.terms[0]?.term_name, credit: x.credit, hours: x.hours, description: x.description});
  }
  if (action === 'lib-state') { libFilter = {...libFilter, state: id}; if (!id) delete libFilter.state; libPage = 1; return c.render(); }
  if (action === 'lib-reset') { libFilter = {}; libPage = 1; return c.render(); }
  if (action === 'lib-page') { libPage = Math.max(1, Number(id)); return c.render(); }
  throw Error('操作无效');
}

export async function applicationAction(action, id, ctx) {
  c = ctx;
  if (action === 'app-detail') return showApplication(id);
  if (action === 'app-edit') return edit(id);
  if (action === 'app-upload') return upload(id);
  if (action === 'app-course-new') return manualCourseForm();
  if (action === 'app-base-new') return baseForm();
  const map = {'app-approve': 'approve', 'app-return': 'return', 'app-submit': 'submit', 'app-withdraw': 'withdraw'};
  if (map[action]) {
    if (opened?.item?.id !== id) await load(id);
    return decide(id, map[action]);
  }
  throw Error('操作无效');
}
