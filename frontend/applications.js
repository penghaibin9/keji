// 老师发起的申请（社会培训课申报、培训课程申请、培训基地申请）：进度、详情与办理、我的申请、申请表。
// 只调用 /api/applications；谁能办、回避、代办、版本和材料都由后端核对，这里按后端给的 permissions 显示按钮。
let c = null, opened = null;

export const AUDIENCE = ['企业职工', '社区居民', '退役军人', '新型职业农民', '中小学教师', '机关事业单位人员', '待业及转岗人员', '老年学员'];
export const TEACHING_MODES = [['lecture', '讲授'], ['practice', '实训实操'], ['case', '案例研讨'], ['onsite', '现场教学'], ['online', '线上自学']];
export const IDEOLOGY = [['course_ideology', '课程思政'], ['ideology_course', '思政课程'], ['none', '无']];
const BASE_USAGES = [['practice', '实践教学基地'], ['ideology', '思政实践教学基地']];
const TONE = {green: 'ok', red: 'warn', blue: '', gray: 'muted'};

const time = v => v ? String(v).replace('T', ' ').slice(0, 16) : '';

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
    progressHtml(d.progress, e) + `<dl class="kv mt16">${rows}</dl><h3 class="mt16">申请材料</h3>${files}<h3 class="mt16">办理记录</h3>${events(d.events)}`;
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
  const open = m.items.filter(x => x.progress.tone !== 'green').slice(0, 3);
  if (!open.length) return '';
  const row = x => `<div class="apply-home-row"><div><strong>${e(x.name)}</strong><p class="cell-sub">${e(x.label)}</p></div>${progressHtml({...x.progress, nodes: x.nodes, label: x.label}, e, {compact: true})}` +
    (x.type === 'social_project' ? c.act('查看', 'social-detail', 'social_project|' + x.id, 'sm') : c.act(x.state === 'RETURNED' ? '去补正' : '查看', 'app-detail', x.id, x.state === 'RETURNED' ? 'sm primary' : 'sm')) + `</div>`;
  return `<section class="card"><div class="card-head"><div><h2>我的申请</h2></div>${c.act('全部申请', 'todos-tab', 'mine', 'text')}</div><div class="card-pad">${open.map(row).join('')}</div></section>`;
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
