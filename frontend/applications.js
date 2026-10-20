// 老师发起的申请（培训课程申报、培训基地申请）：进度、详情与办理、我的申请、申请表。
// 只调用 /api/applications；谁能办、回避、代办、版本和材料都由后端核对，这里按后端给的 permissions 显示按钮。
import {materialUploadForm} from './approval-flow.js?v=20261017-multi-materials2';
import {renderTrainingWorkspace} from './training-workspace.js?v=20261019-walk3&nav=20261020-m2';
import {courseFactsHtml, onlineCard} from './school-data.js?v=20261019-merge1&display=20261019-clean2';
import {imageField, takeImage, saveImageAfter, coverButton} from './display-image.js?v=20261019-img3';
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
  const d = await load(id), e = c.esc, x = d.item, p = d.permissions, sectioned = ['teacher', 'dept', 'college'].includes(c.me?.role?.kind);
  const value = v => /^https?:\/\//.test(v) ? `<a href="${e(v)}" target="_blank" rel="noopener noreferrer">${e(v)}</a>` : e(v);
  const rows = d.fields.map(([k,v]) => sectioned ? `<div class="${/简介|说明|依据|经历|资质|面向/.test(k)||String(v??'').length>70?'wide':''}"><dt>${e(k)}</dt><dd>${value(v)}</dd></div>` : `<dt>${e(k)}</dt><dd>${value(v)}</dd>`).join('');
  const files = d.attachments.length ? c.downloads&&(!c.can||c.can('file.read')) ? c.downloads(d.attachments) : `<ul class="apply-files">${d.attachments.map(f=>`<li>${e(f.name)}</li>`).join('')}</ul>` : '<p class="detail-empty">还没有上传材料。'+(p.upload?'需要补充时，可使用下方“上传材料”。':'')+'</p>';
  const progress = {...d.progress};
  const ownApplication=p.edit||p.submit||x.data?.created_by===c.me.user.id||d.applicant?.id===c.me.user.id;
  if(['dept','college'].includes(c.me?.role?.kind)&&x.state==='RETURNED'&&!ownApplication){progress.text=progress.text.replace('待你补正','待申请人补正');progress.headline=progress.headline.replace('请补正后重新提交','请由原申请人补正后重新提交');}
  const headline = progress.headline + (d.applicant?.id === c.me.user.id && progress.tone === 'blue' ? '无需你操作。' : '');
  const status = `<span class="badge ${d.progress.tone==='green'?'green-b':d.progress.tone==='red'?'red-b':'blue-b'}">${e(d.state_label)}</span>`;
  const navigation = `<nav class="detail-section-nav" aria-label="申请详情分区"><button type="button" data-detail-section="application-info">申请资料</button><button type="button" data-detail-section="application-materials">材料 · ${d.attachments.length}</button><button type="button" data-detail-section="application-history">办理记录</button></nav>`;
  const mayImage = [x.data?.created_by, x.data?.teacher_id].includes(c.me.user.id) || (['college', 'school'].includes(c.me.role.kind) && c.can('records.write'));
  const imageLabel = d.flow === 'trainer' || d.flow === 'trainer_external' ? '头像' : '封面';
  const cover = x.data?.cover_id ? `<figure class="detail-cover"><img src="/api/social/images/${e(x.data.cover_id)}" alt="${e(x.name)}${imageLabel}" loading="lazy"></figure>` : '';
  const body = sectioned ? `<div class="application-detail"><section class="detail-status-summary"><div><strong>${e(progress.text)}</strong><p>${e(headline)}</p><small>申请人 ${e(d.applicant?.name||'')} · ${e(d.org_name)}</small></div>${status}</section><details class="detail-fold application-flow"><summary>查看完整审批流程</summary>${progressHtml({...progress,headline},e)}</details>${navigation}<section id="application-info" class="detail-section"><h3>申请资料</h3>${cover}<dl class="detail-facts-grid">${rows}</dl></section><section id="application-materials" class="detail-section"><div class="detail-section-title"><h3>申请材料</h3><span>${d.attachments.length} 份</span></div>${files}</section><section id="application-history" class="detail-section"><h3>办理记录</h3>${events(d.events)}</section>${p.withdraw?'<p class="detail-action-note">撤回后申请暂停审核；修改并重新提交时，将从第一级重新审核。</p>':''}</div>` : `<div class="between"><p class="muted small">${e(d.label)} · 申请人 ${e(d.applicant?.name||'')} · ${e(d.org_name)}</p>${status}</div>${progressHtml({...progress,headline},e)}<dl class="kv mt16">${rows}</dl><h3 class="mt16">申请材料</h3>${files}<h3 class="mt16">办理记录</h3>${events(d.events)}`;
  const foot = [x.kind==='course_apply'&&x.state==='ACTIVE'&&c.can?.('points.read')?c.act('积分办理','course-points',x.id,'primary'):'',mayImage ? coverButton(c, 'resource', x, imageLabel) : '', p.approve?c.act('通过','app-approve',x.id,'primary'):'',p.return?c.act('退回','app-return',x.id,'danger'):'',p.edit?c.act('补正资料','app-edit',x.id,'primary'):'',p.submit?c.act('重新提交','app-submit',x.id,p.edit?'':'primary'):'',p.upload?c.act('上传材料','app-upload',x.id):'',p.withdraw?c.act('撤回','app-withdraw',x.id,'light'):'',c.act('关闭','close')].join('');
  c.modal(d.label+' · '+x.name,body,foot,true,sectioned?d.label+' / 申请详情':'');
}

function decide(id, action) {
  const d = opened, label = {approve: '通过', return: '退回', submit: '重新提交', withdraw: '撤回'}[action];
  const level = (d.progress.nodes.find(n => n.state === 'current') || {}).label || '';
  const hint = action === 'return' ? '写清楚要补什么。老师补正后从这一级接着审，不从头走。' : action === 'approve' ? (level ? '本次办理：' + level + '。' : '') + '通过后自动转到下一级，最后一级通过即生效。' : action === 'withdraw' ? '撤回后可修改再提交，会从第一级重新审。' : '会从退回的那一级接着审。';
  const value = {approve: '材料齐全，同意', return: '', submit: '已按意见补正，重新提交', withdraw: '撤回修改'}[action];
  const needBasis = action === 'approve' && ['组织人事部认定', '教务处备案审核'].includes(level);
  const fillCourseware = action === 'approve' && ['course','teaching_course'].includes(d.flow) && ['学院审批','学校审批'].includes(level) && !d.item.data?.courseware?.checked;
  const result = c.formModal(label + '：' + d.item.name, `<div class="detail-action-context"><span>办理事项</span><strong>${c.esc(d.item.name)}</strong><p>${c.esc(d.state_label||d.progress.text)}</p></div>` + c.note(needBasis ? hint + '请在“依据说明”里写' + (level === '组织人事部认定' ? '资格认定文号和日期。' : '备案依据。') : hint, action === 'withdraw') + (fillCourseware ? applicationSection('补充课件审查记录', coursewareFields(d.item.data?.courseware), '已在本环节完成审查的，可登记审查人、日期和记录编号；尚未完成请退回补正，不代替实际材料核验。') : '') + c.reasonFields(action === 'return' ? value : '', action === 'return' ? '退回原因' : '办理意见', false, level === '组织人事部认定' ? '例：湘人认〔2026〕12号，2026年10月16日' : level === '教务处备案审核' ? '例：教务处备案〔2026〕7号' : '例：学院会议纪要〔2026〕3号、协议编号、材料编号', action === 'return' ? '例：资格依据不够具体，请补充证书编号和授课经历' : '例：' + value, action !== 'return'), async v => {
    if (needBasis && !(v.basis || '').trim()) throw Error('请填写依据说明：' + (level === '组织人事部认定' ? '资格认定文号和日期' : '备案依据'));
    if (fillCourseware && v.cw_checked && !((v.cw_reviewer || '').trim() && v.cw_on)) throw Error('请填写课件审查人和审查日期');
    await c.api('/applications/' + id + '/actions', {method: 'POST', body: {action, expected_version: d.item.version, reason: v.reason || value, basis: v.basis, ...(fillCourseware && v.cw_checked ? {courseware: coursewareValue(v)} : {})}});
    c.closeModal(); c.toast(label + '完成'); await c.renderKeep(); await showApplication(id);
  }, {submit: '确认' + label, returnTo: () => showApplication(id), contextLabel:d.label+' / '+label, hint:action==='withdraw'?'返回详情不会撤回申请；只有点击“确认撤回”才会执行。':''});
  if (fillCourseware) bindApplicationConditions();
  return result;
}

function upload(id) {
  const d = opened;
  return materialUploadForm(c,{kind:'social_resource',id,title:'上传材料：'+d.item.name,contextLabel:d.label+' / 补充材料',intro:`<div class="detail-action-context"><span>材料所属申请</span><strong>${c.esc(d.item.name)}</strong><p>当前已有 ${d.attachments?.length||0} 份材料；本次新增材料保留在同一申请中。</p></div>`,latest:async()=>{const fresh=await load(id);return {version:fresh.item.version,attachments:fresh.attachments}},after:()=>showApplication(id)});
}

// ---- 申请表 ----

function applicationCorrection(existing) {
  if (!existing || !['RETURNED','WITHDRAWN'].includes(existing.item.state)) return '';
  const returned = [...(existing.events || [])].reverse().find(event => /退回/.test(event.action));
  return `<section class="application-correction" aria-label="本次补正要求"><h3>${existing.item.state === 'RETURNED' ? '按审核意见补正' : '撤回后修改'}</h3><p>${c.esc(existing.item.state === 'RETURNED' ? returned?.reason || '请先核对原申请的办理记录，再补充资料。' : '原申请资料和材料会保留，修改后需重新提交审核。')}</p><small>保存补正不会自动提交；保存后回到详情，核对无误再重新提交。</small></section>`;
}

function applicationSection(title, body, description = '') {
  return `<fieldset class="social-fieldset"><legend>${c.esc(title)}</legend>${description ? `<p class="social-fieldset-note">${c.esc(description)}</p>` : ''}<div class="social-form-fields">${body}</div></fieldset>`;
}
function formIsCurrent(ctx, page, user) { return (!ctx.currentPage || ctx.currentPage() === page) && (!ctx.currentUser || ctx.currentUser() === user); }
function applicantInfo() {
  return c.me?.role?.kind === 'teacher' && c.me.user?.name ? `<div class="application-identity"><span>申报人</span><strong>${c.esc(c.me.user.name)}</strong><span>校内教师 · 申请归属本人</span></div>` : '';
}
export function bindApplicationConditions() {
  if (typeof document === 'undefined') return;
  const form = document.getElementById('edit-form');
  if (!form) return;
  const checked = name => !!form.querySelector(`input[name="${name}"]:checked`);
  const required = (name, need) => {
    const input = form.querySelector(`[name="${name}"]`);
    if (!input) return;
    input.required = need;
    const label = input.closest('.form-field')?.querySelector('label');
    label?.querySelector('b')?.remove();
    if (need) label?.insertAdjacentHTML('beforeend', ' <b>*</b>');
  };
  const sync = () => {
    required('partner', form.querySelector('input[name="onsite"]:checked')?.value === 'no');
    required('target_groups', checked('one_skill'));
    required('cw_reviewer', checked('cw_checked'));
    required('cw_on', checked('cw_checked'));
  };
  form.addEventListener('change', sync); sync();
}

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

// 管理办法第十六条：培训包、“一人一技”专项两个标记。
function packageFields(d = {}) {
  return c.field('package', '培训包', 'checkbox', !!d.package, {required: false, checkLabel: '按培训包开发（成套的教学包）', full: true}) +
    c.field('one_skill', '“一人一技”专项', 'checkbox', !!d.one_skill, {required: false, checkLabel: '面向“一人一技”专项培训行动', full: true}) +
    c.field('target_groups', '重点群体与行动对接', 'textarea', d.target_groups || '', {required: false, full: true, hint: '勾选“一人一技”专项时必填：面向哪些重点群体、怎么对接行动。', placeholder: '例：脱贫人口、返乡青年；对接“一人一技”行动，学员结业后推荐就业'});
}

const packageValue = v => ({package: !!v.package, one_skill: !!v.one_skill, target_groups: v.target_groups || ''});

function coursewareFields(cw = {}) {
  return c.field('cw_checked', '课件审查状态', 'checkbox', !!cw.checked, {required: false, checkLabel: '已有学院课件审查记录（政治方向、知识产权、内容质量）', full: true}) +
    c.field('cw_reviewer', '审查人或审查组', 'text', cw.reviewer || '', {required: !!cw.checked, hint: '勾选已有审查记录时必填。', placeholder: '例：学院课件审查组'}) + c.field('cw_on', '审查日期', 'date', cw.reviewed_on || '', {required: !!cw.checked}) +
    c.field('cw_ref', '审查记录编号', 'text', cw.reference || '', {required: false, placeholder: '例：KJ-2026-03'});
}

const coursewareValue = v => ({checked: !!v.cw_checked, reviewer: v.cw_reviewer || '', reviewed_on: v.cw_on || null, reference: v.cw_ref || ''});

// 培训课程申报（课程遴选）之一：从“我的课程”里选一门本人的教务或超星课，课程信息带出来。course 为“我的课程”里那一行。
export function teachingCourseForm(course, existing = null) {
  const e = c.esc, d = existing?.item?.data || {};
  const facts = `<div class="apply-source"><span class="badge ${course.origin === 'CX' ? 'green-b' : 'blue-b'}">${course.origin === 'CX' ? '超星' : '教务'}</span><strong>${e(course.course_name)}</strong><span>${e(course.course_code)} · ${e(course.term_name)}${course.credit != null ? ' · ' + e(course.credit) + ' 学分' : ''}${course.hours != null ? ' · ' + e(course.hours) + ' 学时' : ''}</span></div>`;
  const body = `<div class="application-form">${applicantInfo()}${applicationCorrection(existing)}${c.note('课程通过教研室、学院和学校审批后入库；课程入库不单独记积分，实际授课积分按培训项目核算。')}` +
    applicationSection('一、课程来源与教学安排', facts +
      c.field('teaching_mode', '教学方式（单选）', 'select', d.teaching_mode || 'lecture', {options: TEACHING_MODES, chips: true}) +
      c.field('ideology', '思政属性（单选）', 'select', d.ideology || 'course_ideology', {options: IDEOLOGY, chips: true}) +
      c.field('hours', '培训学时', 'number', d.hours ?? course.hours ?? '', {required: false, min: 0, step: '0.5', hint: '已带出原课程学时，可按社会培训实际安排调整。'})) +
    applicationSection('二、培训内容与面向对象', audienceFields(d.audience) + c.field('intro', '课程简介', 'textarea', d.intro || course.description || '', {required: false, full: true, hint: '说明培训对象、主要内容，以及学员完成后能掌握的技能。'})) +
    applicationSection('三、专项属性', packageFields(d)) +
    applicationSection('四、已有课件审查记录', coursewareFields(d.courseware), '有正式的学院课件审查记录时再勾选；未审查时保持未勾选，由审批环节核验。') +
    applicationSection('五、封面与申报说明', imageField(c, 'cover_file', '课程封面（选填）') + c.field('reason', '本次申报说明', 'textarea', '', {required: false, full: true, hint: existing ? '说明按审核意见补充了哪些内容。保存后仍需重新提交。' : '可简要说明课程适用人群或申报依据。'})) + '</div>';
  const result = c.formModal(existing ? '补正培训课程申报' : '申报为培训课程', body, async v => {
    const image = takeImage(v, 'cover_file');
    const data = {source: 'teaching', course_term_id: course.id, hours: v.hours, teaching_mode: v.teaching_mode, ideology: v.ideology, audience: audienceValue(v), intro: v.intro || '', courseware: coursewareValue(v), ...packageValue(v)};
    if (!data.audience) throw Error('请至少选择一类面向对象');
    const r = existing ? await c.api('/applications/courses/' + existing.item.id, {method: 'PUT', body: {data, reason: v.reason || (existing ? '按意见补正' : '申报为培训课程'), expected_version: existing.item.version}})
      : await c.api('/applications/courses', {method: 'POST', body: {data, reason: v.reason || (existing ? '按意见补正' : '申报为培训课程')}});
    await saveImageAfter(c, 'resource', r, image);
    c.closeModal(); c.toast(existing ? '已保存，请点“重新提交”' : '已提交，等待教研室审核'); await c.renderKeep(); await showApplication(r.item.id);
  }, {wide: true, page: true, contextLabel: existing ? '我的申请 / 补正资料' : '我要申报 / 填写资料', submit: existing ? '保存补正' : '提交申报', returnTo: existing ? () => showApplication(existing.item.id) : null});
  bindApplicationConditions(); return result;
}

// 培训课程申报之二：新填一门不来自本人学历课的课程（教研室、学院可以代老师登记）。
export async function manualCourseForm(existing = null, projectCode = '') {
  const formContext = c, origin = c.currentPage?.(), user = c.currentUser?.();
  const d = existing?.item?.data || {project_code: projectCode};
  const college = c.me.role.kind === 'college';
  const who = c.me.role.kind === 'teacher' ? '' : c.teacherField(d.teacher_id || '', 'teacher_id', '主讲教师（输入工号或姓名检索）');
  const project = c.projectField ? await c.projectField(c, d.project_code || '') : c.field('project_code', '关联项目编号', 'text', d.project_code || '', {required: false, hint: '不关联项目可留空。'});
  if (!formIsCurrent(formContext, origin, user)) return;
  const body = `<div class="application-form">${applicantInfo()}${applicationCorrection(existing)}${c.note(college ? '学院登记后提交学校审批，通过后进入培训课程库。' : '课程依次由教研室、学院和学校审批，通过后进入培训课程库；入库不直接记社会培训积分。')}` +
    applicationSection('一、课程基本资料', who + c.field('code', '课程编号', 'text', d.code || '', {readonly: !!existing, hint: '填写课程材料上的编号；补正时保留原编号。', placeholder: '例：SOC-2026-001'}) + c.field('name', '课程名称', 'text', existing?.item?.name || '', {placeholder: '例：社区营养配餐'}) +
      c.field('hours', '学时', 'number', d.hours ?? '', {min: 0, step: '0.5', hint: '按本次培训实际安排填写。'}) +
      c.field('teaching_mode', '教学方式（单选）', 'select', d.teaching_mode || 'lecture', {options: TEACHING_MODES, chips: true}) +
      c.field('ideology', '思政属性（单选）', 'select', d.ideology || 'course_ideology', {options: IDEOLOGY, chips: true})) +
    applicationSection('二、课程内容与关联项目', c.field('intro', '课程简介', 'textarea', d.intro || '', {required: false, full: true, hint: '说明面向哪些社会学员、培训内容和预期学习效果。'}) + project) +
    applicationSection('三、专项属性', packageFields(d)) +
    applicationSection('四、已有课件审查记录', coursewareFields(d.courseware), '有正式的学院课件审查记录时再勾选；未审查时保持未勾选，由审批环节核验。') +
    applicationSection('五、封面与申报说明', imageField(c, 'cover_file', '课程封面（选填）') + c.field('reason', '本次申报说明', 'textarea', '', {required: false, full: true, hint: existing ? '说明本次补正内容；保存后仍需重新提交。' : '可填写申报依据或需要审核人员了解的情况。'})) + '</div>';
  const result = c.formModal(existing ? '补正培训课程申报' : '新填一门培训课程', body, async v => {
    const image = takeImage(v, 'cover_file');
    const data = {source: 'manual', code: v.code, name: v.name, project_code: v.project_code || '', teacher_id: v.teacher_id || null, hours: v.hours,
      teaching_mode: v.teaching_mode, ideology: v.ideology, intro: v.intro || '', courseware: coursewareValue(v), ...packageValue(v)};
    const r = existing ? await c.api('/applications/courses/' + existing.item.id, {method: 'PUT', body: {data, reason: v.reason || (existing ? '按意见补正' : '申报培训课程'), expected_version: existing.item.version}})
      : await c.api('/applications/courses', {method: 'POST', body: {data, reason: v.reason || (existing ? '按意见补正' : '申报培训课程')}});
    await saveImageAfter(c, 'resource', r, image);
    c.closeModal(); c.toast(existing ? '已保存，请点“重新提交”' : college ? '已提交，等待学校审批' : c.me.role.kind === 'dept' ? '已提交，等待学院审批' : '已提交，等待教研室审核'); await c.renderKeep(); await showApplication(r.item.id);
  }, {wide: true, page: true, contextLabel: existing ? '我的申请 / 补正资料' : college ? '培训课程 / 填写资料' : '我要申报 / 填写资料', submit: existing ? '保存补正' : '提交申报', returnTo: existing ? () => showApplication(existing.item.id) : null});
  bindApplicationConditions(); return result;
}

export function baseForm(existing = null) {
  const d = existing?.item?.data || {};
  const who = c.me.role.kind === 'teacher' ? '' : c.teacherField(d.teacher_id || '', 'teacher_id', '基地负责人（输入工号或姓名检索）');
  const used = new Set(d.usages || ['practice']);
  const college = c.me.role.kind === 'college';
  const body = `<div class="application-form">${applicantInfo()}${applicationCorrection(existing)}${c.note(college ? '学院登记后提交学校审批，通过后进入基地清单。' : '提交后由学院、学校依次审批，通过后进入基地清单。')}` +
    applicationSection('一、基地基本资料', who +
      c.field('code', '来源编号', 'text', existing?.item?.code || '', {readonly: !!existing, hint: '填写共建协议编号或学院登记编号。', placeholder: '例：JD-2026-001'}) + c.field('name', '基地名称', 'text', existing?.item?.name || '', {placeholder: '例：湘茶思政实践教学基地'}) +
      c.field('manager_name', '基地负责人', 'text', d.manager_name || '', {required: false, hint: '校内基地填学校负责人，校外基地填共建单位联系人；不填则按申请人显示。', placeholder: '例：张老师'}) +
      `<fieldset class="form-field full apply-tags"><legend>基地用途（可多选） <b>*</b></legend><div class="apply-tag-row">${BASE_USAGES.map(([k, l]) => `<label><input type="checkbox" name="usage_${k}" ${used.has(k) ? 'checked' : ''}>${c.esc(l)}</label>`).join('')}</div></fieldset>` +
      c.field('level', '基地级别（单选）', 'select', d.level || 'school', {options: [['school', '校级'], ['city', '市级'], ['province', '省级及以上']], chips: true})) +
    applicationSection('二、地点与共建信息', c.field('onsite', '校内 / 校外（单选）', 'select', d.onsite === false ? 'no' : 'yes', {options: [['yes', '校内'], ['no', '校外']], chips: true}) +
      c.field('partner', '共建单位', 'text', d.partner || '', {required: d.onsite === false, hint: '选择校外基地时必须填写；请使用共建单位全称。'}) + c.field('established_on', '设立日期', 'date', d.established_on || '') + c.field('recognized_on', '认定日期', 'date', d.recognized_on || '', {required: false, hint: '学校或上级正式认定的日期；与设立日期、审批生效日期分开记录，没有认定可不填。'}) +
      c.field('location', '具体地点', 'text', d.location || '', {required: false, hint: '可填写基地所在校区、楼宇或校外地址。'})) +
    applicationSection('三、认定依据与申请说明', imageField(c, 'cover_file', '基地封面（选填）', '选填，PNG 或 JPG，不超过 5MB；场地照片可在基地详情里继续添加。仅用于展示，不能代替认定材料。') + c.field('recognition', '基地认定依据', 'textarea', d.recognition || '', {full: true, hint: '填写共建协议、学校发文或学院会议纪要等正式依据。'}) +
      c.field('reason', '本次申请说明', 'textarea', '', {full: true, required: false, hint: existing ? '说明本次补正内容；保存后仍需重新提交。' : '补充说明设立用途或本次申请事项，与上面的认定依据分开填写。'})) + '</div>';
  const result = c.formModal(existing ? '补正培训基地申请' : '申请培训基地', body, async v => {
    const image = takeImage(v, 'cover_file');
    const data = {code: v.code, name: v.name, teacher_id: v.teacher_id || null, usages: BASE_USAGES.map(([k]) => k).filter(k => v['usage_' + k]), onsite: v.onsite === 'yes',
      partner: v.partner || '', level: v.level || 'school', established_on: v.established_on, manager_name: v.manager_name || '', recognized_on: v.recognized_on || null, location: v.location || '', recognition: v.recognition};
    if (!data.usages.length) throw Error('请选择基地用途');
    const r = existing ? await c.api('/applications/bases/' + existing.item.id, {method: 'PUT', body: {data, reason: v.reason || (existing ? '按意见补正' : '申请培训基地'), expected_version: existing.item.version}})
      : await c.api('/applications/bases', {method: 'POST', body: {data, reason: v.reason || (existing ? '按意见补正' : '申请培训基地')}});
    await saveImageAfter(c, 'resource', r, image);
    c.closeModal(); c.toast(existing ? '已保存，请点“重新提交”' : college ? '已提交，等待学校审批' : '已提交，等待学院审批'); await c.renderKeep(); await showApplication(r.item.id);
  }, {wide: true, page: true, contextLabel: existing ? '我的申请 / 补正资料' : college ? '培训基地 / 填写资料' : '我要申报 / 填写资料', submit: existing ? '保存补正' : '提交申报', returnTo: existing ? () => showApplication(existing.item.id) : null});
  bindApplicationConditions(); return result;
}

// 培训师申报（管理办法第十五条）：校内老师本人申报，外聘培训师由学院负责人登记。
const TRAINER_DIRECTIONS = [['subsidy', '补贴性培训'], ['enterprise', '社会化自主培训'], ['community', '社区公益培训'], ['rural', '对口帮扶培训'], ['other', '其他非学历培训'], ['one_skill', '“一人一技”专项']];

export async function trainerForm(existing = null, source = '') {
  const formContext = c, origin = c.currentPage?.(), user = c.currentUser?.();
  const d = existing?.item?.data || {}, e = c.esc;
  const external = (existing ? d.source : source) === 'external';
  const picked = new Set(d.directions || []);
  let quals = '';
  if (!external) {
    let mineQuals = [];
    if (!c.can || c.can('qualification.read')) {
      try { mineQuals = (await c.api('/qualifications?size=100&state=APPROVED')).items || []; }
      catch { if (!formIsCurrent(formContext, origin, user)) return; throw Error('本人已审核资质暂未读取，请稍后重试；已有申请及资质引用未更改。'); }
    }
    if (!formIsCurrent(formContext, origin, user)) return;
    const chosen = new Set(d.qualification_ids || (d.qualifications || []).map(q => q.id));
    const available = new Set(mineQuals.map(q => q.id));
    const old = d.qualifications || [];
    const choices = [...mineQuals, ...[...chosen].filter(id => !available.has(id)).map((id, i) => ({...(old.find(q => q.id === id) || {name: '原引用资质' + (i + 1)}), id, retained: true}))];
    const validity = q => q.expires ? '有效期至 ' + q.expires : q.expires === null ? '长期有效' : '有效期待核实';
    quals = choices.length ? `<fieldset class="form-field full apply-tags"><legend>引用本人已审核资质（可多选）</legend><div class="apply-qualification-list">${choices.map(q => `<label><input type="checkbox" name="qual_${e(q.id)}" ${chosen.has(q.id) ? 'checked' : ''}><span><strong>${e(q.name)}</strong><small>${e(q.issuer || '发证机构待核实')} · ${e(validity(q))}${q.retained ? ' · 原引用，当前状态请核实' : ''}</small></span></label>`).join('')}</div><p class="hint">保留原引用；若资质审核状态发生变化，请核实或取消该引用后再保存。</p></fieldset>` : '<p class="hint form-field full">暂无可引用的已审核资质，可在下方填写职称、行业经历等资格依据。</p>';
  }
  const body = `<div class="application-form">${applicantInfo()}${applicationCorrection(existing)}${c.note(external ? '由学院登记，教务处审核备案后进入培训师资库。' : '教研室、学院、学校审核后，由组织人事部认定并进入培训师资库。')}` +
    applicationSection('一、基本信息与培训业务类别',
      (external ? c.field('name', '姓名', 'text', existing?.item?.name || '') + c.field('unit', '工作单位', 'text', d.unit || '') : '') +
      c.field('title', '职称或职务', 'text', d.title || '', {required: false, hint: '填写本人现有职称、职业技能等级或岗位。'}) +
      c.field('specialty', '专业特长', 'text', d.specialty || '', {required: false, hint: '例：茶艺、电商运营、家政服务；与下面的“培训业务类别”分开填写。'}) +
      `<fieldset class="form-field full apply-tags"><legend>培训业务类别（可多选） <b>*</b></legend><div class="apply-tag-row">${TRAINER_DIRECTIONS.map(([k, l]) => `<label><input type="checkbox" name="dir_${k}" ${picked.has(k) ? 'checked' : ''}>${e(l)}</label>`).join('')}</div></fieldset>`) +
    applicationSection('二、资质与资格依据', quals + c.field('qualification_basis', '资格依据', 'textarea', d.qualification_basis || '', {full: true, hint: '说明职称、职业资格或行业经历，以及它们能够支持的培训方向。'})) +
    applicationSection('三、授课经历与申报说明', imageField(c, 'cover_file', '培训师头像（选填）') + c.field('experience', '授课经历', 'textarea', d.experience || '', {required: false, full: true, hint: '可填写近年授课项目、培训期数和学员人次。'}) +
      c.field('reason', '本次申报说明', 'textarea', '', {full: true, required: false, hint: existing ? '说明本次补正内容；保存后仍需重新提交。' : '可补充说明本次申报的专业特长与相关依据。'})) + '</div>';
  return c.formModal(existing ? '补正培训师申报' : external ? '登记外聘培训师' : '申报培训师', body, async (v, f) => {
    const image = takeImage(v, 'cover_file');
    const data = {source: external ? 'external' : 'internal', name: v.name || '', unit: v.unit || '', title: v.title || '', specialty: v.specialty || '', directions: TRAINER_DIRECTIONS.map(([k]) => k).filter(k => v['dir_' + k]),
      qualification_ids: [...f.querySelectorAll('input[name^="qual_"]:checked')].map(i => i.name.slice(5)), qualification_basis: v.qualification_basis, experience: v.experience || ''};
    if (!data.directions.length) throw Error('请至少选择一个培训业务类别');
    const r = existing ? await c.api('/applications/trainers/' + existing.item.id, {method: 'PUT', body: {data, reason: v.reason || (existing ? '按意见补正' : external ? '登记外聘培训师' : '申报培训师'), expected_version: existing.item.version}})
      : await c.api('/applications/trainers', {method: 'POST', body: {data, reason: v.reason || (existing ? '按意见补正' : external ? '登记外聘培训师' : '申报培训师')}});
    await saveImageAfter(c, 'resource', r, image);
    c.closeModal(); c.toast(existing ? '已保存，请点“重新提交”' : external ? '已提交，等待教务处备案审核' : '已提交，等待教研室审核'); await c.renderKeep(); await showApplication(r.item.id);
  }, {wide: true, page: true, contextLabel: existing ? '我的申请 / 补正资料' : c.me.role.kind==='college' ? '培训师资库 / 填写资料' : '我要申报 / 填写资料', submit: existing ? '保存补正' : '提交申报', returnTo: existing ? () => showApplication(existing.item.id) : null});
}

// 培训师资库：学校看全校，学院和教研室看本院；学校可以给在库培训师记“推荐进入省级师资库”。
export async function trainersHtml(ctx) {
  c = ctx;
  const e = c.esc;
  const d = await c.api('/applications/trainers');
  const school = c.me.role.kind === 'school';
  // 人事认定、教务处备案职责没人时，申请会卡住：给学校管理员直接提示并提供配置入口。
  const gaps = (d.duty_gaps || []).map(g => `<li><strong>${e(g.label)}</strong>尚未指定办理人${g.pending ? `，已有 ${e(g.pending)} 条申请在等待` : ''}</li>`).join('');
  const before = gaps ? `<section class="duty-gap-notice" role="status"><div><h3>培训师认定流程缺少办理人</h3><ul>${gaps}</ul><p>指定后，等待中的申请会自动进入对应人员的待办，无需重新提交。</p></div>${c.act('配置审批职责','social-duties','','primary')}</section>` : '';
  return renderTrainingWorkspace('trainers',d,c,{actions:c.act('查看待认定申报','nav','todos','primary')+(c.me.role.kind==='college'?c.act('登记外聘培训师','app-trainer-new','external'):''),total:d.total,before});
}

async function edit(id) {
  const d = opened?.item?.id === id ? opened : await load(id);
  if (d.flow === 'trainer' || d.flow === 'trainer_external') return trainerForm(d);
  if (d.flow === 'base') return baseForm(d);
  if (d.flow === 'course') return manualCourseForm(d);
  const course = d.item.data.course || {};
  return teachingCourseForm({id: d.item.data.course_term_id, origin: course.origin, course_name: course.course_name, course_code: course.course_code,
    term_name: course.term_name, credit: course.credit, hours: course.hours, description: course.description}, d);
}

// ---- 我的申请 ----

let applicationFilter='';
function applicationOpenButton(x) {
  const label=x.state==='RETURNED'?'去补正':x.progress?.tone==='blue'?'查看进度':'查看详情';
  return x.type==='social_project'?c.act(label,'social-detail','social_project|'+x.id,'sm'):c.act(label,'app-detail',x.id,x.state==='RETURNED'?'sm primary':'sm');
}
export async function myApplicationsHtml(ctx) {
  c = ctx;
  const e = c.esc;
  let m;
  try { m = await c.api('/applications/mine'); } catch (err) { return c.note('我的申请读取失败：' + err.message, true); }
  const n = m.counts, sharedLayout = ['teacher','dept','college'].includes(c.me?.role?.kind);
  const visible=m.items.filter(x=>!applicationFilter||(applicationFilter==='draft'?['DRAFT','WITHDRAWN'].includes(x.state)&&x.progress.tone==='gray':x.progress.tone===({returned:'red',pending:'blue',done:'green'}[applicationFilter])));
  const chips = `<div class="apply-counts">${sharedLayout ? `<span>草稿 <b>${n.draft || 0}</b></span>` : ''}<span>审批中 <b>${n.pending}</b></span><span class="${n.returned ? 'warn' : ''}">待我补正 <b>${n.returned}</b></span><span>已办结 <b>${n.done}</b></span></div>`;

  return `<div class="card${sharedLayout ? ' teacher-applications' : ''}"><div class="card-head"><div><h2>我的申请</h2><p>课程、项目、基地和培训师申请 · 查看当前进度与办理方</p></div>${chips}</div>` +
    (sharedLayout?`<div class="application-status-filter" role="group" aria-label="申请状态筛选">${[['','全部'],['draft','草稿'],['pending','办理中'],['returned','待补正'],['done','已办结']].map(([key,label])=>`<button type="button" class="btn sm ${applicationFilter===key?'primary':''}" data-action="app-mine-filter" data-id="${key}" aria-pressed="${applicationFilter===key}">${label}</button>`).join('')}</div>`:'')+c.table(['申请', '进度', '操作'], (sharedLayout?visible:m.items).map(x => [`<strong>${e(x.name)}</strong><p class="cell-sub">${e(x.label)} · ${e(x.state_label)}</p>`,
      sharedLayout ? `<div class="apply-progress-copy"><strong class="apply-current">${e(x.progress.text)}</strong><p class="cell-sub">${e(x.progress.headline || '')}</p></div>` : progressHtml({...x.progress, nodes: x.nodes, label: x.label}, e, {compact: true}), applicationOpenButton(x)]), applicationFilter?'当前状态没有申请':'还没有申请', applicationFilter?'切换状态查看其他申请。':c.me?.role?.kind==='college'?'从“培训课程管理”“培训基地管理”或“培训师资库”发起申请，提交后在这里查看进度。':c.me?.role?.kind==='dept'?'从“培训课程管理”或“培训基地管理”发起申请，提交后在这里查看进度。':'从左侧“我要申报”选择要办理的业务。') + `</div>`;
}

// 老师左侧的四个申报菜单：每个菜单一页，上面是“新建”，下面是本人这一类申请的进度。
export const APPLY_PAGES = {
  apply_course: {title: '申报培训课程', flows: ['course', 'teaching_course'], action: 'course|', button: '新申报一门培训课程', intro: '从我的课程里选，或新填一门；教研室、学院、学校逐级审批，通过后进入培训课程库。'},
  apply_project: {title: '申报培训项目', flows: ['project', 'project_close'], action: 'projects|social-project-new', button: '新申报一个培训项目', intro: '本人为负责人；学院审批后由学校备案。项目已备案后在这里办结项。'},
  apply_base: {title: '申请培训基地', flows: ['base'], action: 'bases|app-base-new', button: '新申请一个培训基地', intro: '实践教学或思政实践教学基地；学院审批后学校审批，通过后进入基地清单。'},
  apply_trainer: {title: '申报培训师', flows: ['trainer'], action: 'trainer|', button: '新申报培训师', intro: '校内遴选：教研室、学院、学校审核后，由组织人事部认定，进入培训师资库。'}
};

export async function applyPageHtml(ctx, key) {
  c = ctx;
  const e = c.esc, cfg = APPLY_PAGES[key];
  let m;
  try { m = await c.api('/applications/mine'); } catch (err) { return c.note('读取失败：' + err.message, true); }
  const mine = (m.items || []).filter(x => cfg.flows.includes(x.flow));
  const active = mine.filter(x => x.progress?.tone === 'green');
  const trainer = key === 'apply_trainer' ? mine[0] : null;
  const back = mine.filter(x => x.state === 'RETURNED').length;
  const open = x => '<div class="action-row">'+(x.type === 'social_project' ? c.act(x.state === 'DRAFT' ? '继续完善' : '查看详情', 'social-detail', 'social_project|' + x.id, 'sm') : c.act(x.state === 'RETURNED' ? '去补正' : '查看详情', 'app-detail', x.id, x.state === 'RETURNED' ? 'sm primary' : 'sm'))+(key==='apply_course'&&x.state==='ACTIVE'&&c.can?.('points.read')?c.act('积分办理','course-points',x.id,'sm primary'):'')+'</div>';
  const actions = key === 'apply_course'
    ? c.act('从我的课程导入', 'teacher-apply', 'credits|', 'primary') + c.act('手动填写课程', 'teacher-apply', 'courses|app-course-new', '')
    : trainer ? c.act(['RETURNED','WITHDRAWN'].includes(trainer.state) ? '补正原申请' : '查看原申请', ['RETURNED','WITHDRAWN'].includes(trainer.state) ? 'app-edit' : 'app-detail', trainer.id, 'primary') : c.act(cfg.button, 'teacher-apply', cfg.action, 'primary');
  const html = `<div class="teacher-apply-page"><section class="card apply-entry"><div class="apply-entry-top"><div><p class="apply-intro">${e(cfg.intro)}</p><p class="apply-entry-hint">${key === 'apply_project' ? '先保存草稿，再上传材料并提交学院审批。' : key === 'apply_course' ? '已有教务或超星课程可导入；课程入库不直接记社会培训积分。' : trainer ? '培训师实行一人一单；后续查看、补正和重新提交均沿原申请办理。' : '填写资料后提交；审核进度和补正意见在下方查看。'}</p></div><div class="apply-entry-actions">${actions}</div></div></section>` +
    `<section class="card teacher-applications apply-list"><div class="card-head"><div><h2>申报记录</h2><p>查看当前办理方；完整流程和材料在详情中保留。</p></div><span class="badge ${back ? 'orange-b' : 'gray-b'}">${back ? '待补正 ' + back + ' 项' : '共 ' + mine.length + ' 项'}</span></div>` +
    (mine.length ? c.table(['申请', '当前进度', '操作'], mine.map(x => [`<strong>${e(x.name)}</strong><p class="cell-sub">${e(x.label)} · ${e(x.state_label)}</p>`,
      `<div class="apply-progress-copy"><strong class="apply-current">${e(x.progress?.text || x.state_label)}</strong><p class="cell-sub">${e(x.progress?.headline || '')}</p></div>`, open(x)])) : '<p class="apply-empty">还没有申报记录。从上方选择申报方式，提交后会在这里显示进度。</p>') + '</section>';
  const approved = (title, description, headers, rows, empty) => `<details class="card apply-approved"${rows.length ? ' open' : ''}><summary><strong>${title}</strong><span>${rows.length} 项</span></summary><p class="apply-approved-note">${description}</p>${rows.length ? c.table(headers, rows) : `<p class="apply-empty">${empty}</p>`}</details></div>`;
  if (key === 'apply_base') {
    const usage = Object.fromEntries(BASE_USAGES);
    return html + approved('我的培训基地', '已通过审批并进入基地清单。', ['基地名称 / 编号', '用途', '设立日期', '操作'], active.map(x => [`<strong>${e(x.name)}</strong><p class="cell-sub">${e(x.code || '')}</p>`, e((x.info?.usages || []).map(k => usage[k] || k).join('、') || '—'), e(x.info?.established_on || x.info?.effective_on || '—'), c.act('查看详情', 'app-detail', x.id, 'sm')]), '暂无已入库基地，完成审批后显示。');
  }
  if (key === 'apply_trainer') return html + approved('我的培训师资格', '已通过认定并进入培训师资库。', ['培训师', '单位 / 职称', '生效日期', '操作'], active.map(x => [`<strong>${e(x.name)}</strong><p class="cell-sub">${e(x.code || '')}</p>`, e([x.info?.unit, x.info?.title].filter(Boolean).join(' · ') || '—'), e(x.info?.effective_on || '—'), c.act('查看详情', 'app-detail', x.id, 'sm')]), '暂无已认定资格，完成认定后显示。');
  if (key !== 'apply_course') return html + '</div>';
  const modeName = Object.fromEntries(TEACHING_MODES);
  return html + approved('我的培训课程', '已通过审批并进入培训课程库。', ['课程名称 / 编号', '学时', '教学方式', '操作'], active.map(x => [`<strong>${e(x.name)}</strong><p class="cell-sub">${e(x.course?.course_code || x.code || '')}</p>`, x.course?.hours != null && x.course.hours !== '' ? e(x.course.hours) : '—', e(modeName[x.course?.teaching_mode] || '—'), '<div class="action-row">'+c.act('查看课程', 'app-detail', x.id, 'sm')+(c.can?.('points.read')?c.act('积分办理','course-points',x.id,'sm primary'):'')+'</div>']), '暂无已入库课程，完成审批后显示。');
}

// 首页卡片：只列还没办结的申请（最多 3 条），没有就不显示。
export async function homeApplicationsHtml(ctx) {
  c = ctx;
  const e = c.esc;
  let m;
  try { m = await c.api('/applications/mine'); } catch { return ''; }
  const open = (m?.items || []).filter(x => x.progress?.tone !== 'green').slice(0, 3);
  if (!open.length) return '';
  const row = x => `<div class="apply-home-row"><div><strong>${e(x.name)}</strong><p class="cell-sub">${e(x.label)}</p></div><div><strong class="apply-current">${e(x.progress.text)}</strong><p class="cell-sub">${e(x.progress.headline || '')}</p></div>` +
    applicationOpenButton(x) + `</div>`;
  return `<section class="card"><div class="card-head"><div><h2>我的申请</h2></div>${c.act('全部申请', 'todos-tab', 'mine', 'text')}</div><div class="card-pad">${open.map(row).join('')}</div></section>`;
}

// ---- 我的课程（老师）与在线课程库（教研室、学院、学校） ----

let mine = null, mineVisible = [], library = null, libFilter = {}, libPage = 1, detailRequest = 0;
const safeUrl = u => /^https?:\/\//i.test(String(u || '')) ? String(u) : '';
// 封面只用超星自己的图片（页面安全策略只放行 *.chaoxing.com）。
const cover = u => { const v = safeUrl(u); try { return v && /(^|\.)chaoxing\.com$/i.test(new URL(v).hostname) ? v.replace(/^http:/i, 'https:') : ''; } catch { return ''; } };
const num = v => v == null || v === '' ? '—' : String(Number(v));
const SOURCE = {1: '自建', 2: '克隆', 3: '映射'};

// 申报期限：每学年一个截止日；截止后学院开放补报才能申报。
function applyButton(x, index, cls, label = '申报为培训课程') {
  const w = x.window || {};
  if (w.state === 'closed') return `<span class="muted small" title="截止后需要补报请联系学院负责人">已于 ${c.esc(w.deadline)} 截止</span>`;
  return c.act(w.state === 'reopened' ? '补报为培训课程' : label, 'mc-apply', String(index), cls);
}

function declarationState(x) {
  if (!x.application) return ['未申报', 'gray-b', '申报后审核'];
  const a = x.application;
  if (a.state === 'ACTIVE') return ['已入库', 'green-b', '积分另行认定'];
  if (a.state === 'RETURNED') return ['退回补正', 'orange-b', '请按审核意见补充材料'];
  return [a.state_label || '申报处理中', 'blue-b', '积分尚未认定'];
}

function courseTerm(term) {
  const label = String(term || ''), short = label.match(/^(\d{4})(?:-(\d{4}))?-([12])$/), full = label.match(/^(\d{4})[-—](\d{4})\s*学年\s*第([一二12])学期$/);
  const match = short || full;
  if (!match) return `<span class="my-course-term">${c.esc(label || '待补充')}</span>`;
  const end = match[2] || Number(match[1]) + 1, semester = ['1', '一'].includes(match[3]) ? '1' : '2';
  return `<span class="my-course-term"><span>${match[1]}—${end} 学年</span><span>第${semester}学期</span></span>`;
}
const originalCourse = x => ({...x, calculated_credit:x.credit, credit: Object.hasOwn(x, 'source_credit') ? x.source_credit : x.credit, hours: Object.hasOwn(x, 'source_hours') ? x.source_hours : x.hours,
  term_name: x.source_term_name || x.terms[0]?.term_name || ''});

function deadlineNotes(d) {
  return (d.deadline_reminders || []).map(w => c.note(`${w.school_year} 学年的课程申报${w.state === 'reopened' ? '补报' : ''}将于 ${w.state === 'reopened' ? w.reopen_until : w.deadline} 截止，还剩 ${w.days_left} 天，你还有这个学年的课没申报。`, true, '申报截止提醒')).join('');
}

function statusStrip(x, index, scope) {
  const e = c.esc, a = x.application;
  if (a) return `<div class="mc-status ${a.state === 'ACTIVE' ? 'ok' : a.state === 'RETURNED' ? 'warn' : ''}"><span>培训课程：${e(a.state_label)}</span>${c.act(a.state === 'RETURNED' ? '去补正' : '看进度', 'app-detail', a.id, 'sm text')}</div>`;
  return scope === 'mine' ? `<div class="mc-status"><span>还没申报为培训课程</span>${applyButton(x, index, 'sm primary')}</div>` : `<div class="mc-status muted"><span>未申报</span></div>`;
}

function courseCard(x, index, scope) {
  const e = c.esc, img = cover(x.cover_url), terms = x.terms.length;
  const who = scope === 'library' ? `<p class="cell-sub">${e(x.teacher_name)}${x.matched ? '' : '（没对上老师）'} · ${e(x.org_name || x.college_name)}</p>` : '';
  const stats = `<div class="mc-stats"><span><b>${x.credit == null ? '缺' : num(x.credit)}</b>学分</span><span><b>${x.hours != null ? num(x.hours) : e(x.period_text || '—')}</b>学时</span><span><b>${num(x.chapters)}</b>章节</span></div>`;
  return `<article class="mc-card"><button type="button" class="mc-cover ${img?'':'is-empty'}" data-action="${scope === 'mine' ? 'mc-detail' : 'lib-detail'}" data-id="${index}" aria-label="查看 ${e(x.course_name)}">${img ? `<img src="${e(img)}" alt="" loading="lazy" referrerpolicy="no-referrer">` : (c.icon?c.icon('book'):'')}<span class="mc-origin">${x.origin === 'CX' ? '超星' : '教务'}</span>${terms > 1 ? `<span class="mc-terms">${terms} 个学期</span>` : ''}</button>` +
    `<div class="mc-body">${scope==='mine'?`<button type="button" class="mc-title" data-action="mc-detail" data-id="${index}">${e(x.course_name)}</button>`:`<strong title="${e(x.course_name)}">${e(x.course_name)}</strong>`}${who}<p class="cell-sub">${e(x.years.join('、'))}${x.course_source ? ' · ' + e(SOURCE[x.course_source] || '') : ''}${x.stale ? ' · 超过一年没更新' : ''}</p>${stats}` +
    `${x.problems.length ? `<p class="mc-problem">${e(x.problems[0])}</p>` : ''}${x.identity.startsWith('JW|') && x.origin === 'CX' ? `<p class="cell-sub">对应教务课 ${e(x.identity.slice(3))}，同学年只算一次</p>` : ''}${statusStrip(x, index, scope)}</div></article>`;
}

export async function myCoursesHtml(ctx, tab, year, search = '') {
  c = ctx;
  const e = c.esc;
  mine = await c.api('/applications/teaching-courses');
  const pick = x => !year || x.years.includes(year);
  const needle = search.trim().toLocaleLowerCase();
  const list = mine.courses.map((x, i) => [x, i]).filter(([x]) => (tab === 'all' || x.origin === (tab === 'cx' ? 'CX' : 'JW')) && pick(x) && (!needle || [x.course_name,x.course_code,...x.terms.map(t=>t.course_code)].join(' ').toLocaleLowerCase().includes(needle)));
  mineVisible = list.map(([,i])=>i);
  const years = [...new Set(mine.courses.flatMap(x => x.years))].sort().reverse();
  const chips = `<form id="filters" class="filterbar my-course-filters"><input type="hidden" name="tab" value="${e(tab)}"><label for="my-course-year">学年</label><select id="my-course-year" name="school_year" aria-label="学年"><option value="">全部学年</option>${[...new Set([...years,...(year?[year]:[])])].map(y=>`<option value="${e(y)}" ${year===y?'selected':''}>${e(y)}</option>`).join('')}</select><nav aria-label="课程来源" class="my-course-sources">${[['all','全部课程'],['jw','教务课程'],['cx','超星课程']].map(([key,label])=>`<button type="button" class="btn ${tab===key?'primary':''}" data-action="credits-tab" data-id="${key}" aria-pressed="${tab===key}">${label}</button>`).join('')}</nav><input name="q" aria-label="搜索课程名称或课程号" placeholder="搜索课程名称或课程号" value="${e(search)}"><button class="btn primary" type="submit">筛选</button>${c.act('重置','reset-filters','','text')}</form>`;
  const tip = `<details class="business-guide course-guide"><summary>如何申报为培训课程</summary><p>适合面向社会学员开设的课程，可沿原课程申报；经教研室、学院、学校审核后入库，同一门课只申报一次。课程入库和常规学历课堂不单独记社会培训积分，积分按培训项目的授课人次计算。每学年的课程原则上在学年结束后的 9 月 30 日前申报，以学校设置的期限为准；截止后请联系学院负责人补报。</p></details>` + deadlineNotes(mine);
  const empty = `<div class="course-empty">${c.icon?c.icon('book'):''}<h3>${needle?'没有符合条件的课程':(year?'所选学年暂无':'暂无')+(tab==='cx'?'作为建课人的超星课程':tab==='all'?'课程记录':'教务授课记录')}</h3><p>${tab==='cx'?'请先确认你是课程建课人；教学团队成员的课程由建课人申报。':'学校同步教务授课数据后，会按课程号合并显示开课学期。'}</p>${tab==='cx'&&c.me?.user?.staff_no?c.act('认领我的超星课程','cx-claim','','light'):''}${year?c.act('查看全部学年','mc-year','','text'):''}</div>`;
  const source = `<p class="course-source">数据来源：${tab==='cx'?'超星建课记录':tab==='all'?'教务与超星课程记录':'教务授课记录'} · 2020-2021 学年起${tab==='cx'?' · 学分、视频资源与社会培训积分分别统计':''}。同步时间以学校对接记录为准。</p>`;
  const flow = `<ol class="my-course-flow" aria-label="课程办理流程">${[['data','数据采集'],['file','课程申报'],['check','审核入库'],['users','项目培训与结项'],['award','积分认定']].map(([ico,label])=>`<li>${c.icon?.(ico)||''}<span>${label}</span></li>`).join('')}</ol>`;
  const table = list.length ? c.table(['课程名称','课程来源','开课学期','学分 / 学时','申报与积分状态','申报操作','课程详情'],list.map(([x,i])=>{
    const raw=originalCourse(x),[label,tone,hint]=declarationState(x),terms=x.terms.filter(t=>!year||t.school_year===year);
    return [`<div class="my-course-name" data-course-index="${i}"><strong>${e(x.course_name)}</strong><span>课程号：${e(x.course_code)}</span></div>`,
      `<span class="badge ${x.origin==='CX'?'orange-b':'blue-b'}">${x.origin==='CX'?'超星':'教务系统'}</span>`,
      terms.map(t=>courseTerm(t.term_name)).join('')+(terms.length>1?`<p class="cell-sub">${terms.length} 个学期</p>`:''),
      `<div class="my-course-credit">${raw.credit==null?'<span class="amber">学分未填写</span>':`<strong>${e(c.number(raw.credit,2))}</strong> 学分`}<p class="cell-sub">${[raw.hours!=null?e(num(raw.hours))+' 学时':raw.period_text?e(raw.period_text)+' 学时':'',raw.chapters!=null?e(raw.chapters)+' 章':''].filter(Boolean).join(' · ')}</p></div>`,
      `<span class="badge ${tone}">${e(label)}</span><p class="cell-sub">${e(hint)}</p>`,
      x.application?c.act(x.application.state==='RETURNED'?'去补正':'查看申报','app-detail',x.application.id,'sm light')+(x.application.state==='ACTIVE'&&c.can?.('points.read')?c.act('积分办理','course-points',x.application.id,'sm primary'):''):applyButton(x,i,'sm primary','申报课程'),
      c.act('课程详情','mc-detail',String(i),'text')];
  })) : empty;
  return `<section class="my-courses-workspace">${flow}${chips}<p class="my-course-count">共 ${list.length} 条课程记录 · 教务 ${list.filter(([x])=>x.origin==='JW').length} 条 · 超星 ${list.filter(([x])=>x.origin==='CX').length} 条</p><div class="card teacher-course-table">${table}</div><p class="my-course-policy">课程学分与教师积分分别统计；课程先申报审核，积分以实际培训业务认定结果为准。</p>${source}${tip}</section>`;
}

async function courseDetail(x, scope) {
  if (!x) return;
  const request = ++detailRequest;
  const context=c, page=c.currentPage?.(), user=c.currentUser?.();
  const e = c.esc, url = safeUrl(x.course_url);
  const rows = [['课程名称', e(x.course_name)], ['来源', x.origin === 'CX' ? '超星' + (x.course_source ? '（' + e(SOURCE[x.course_source] || x.course_source) + '）' : '') : '教务'],
    ['课程号', `<span class="mono">${e(x.course_code)}</span>`], ['学分', x.credit == null ? '<span class="badge orange-b">缺学分</span>' : num(x.credit)], ['学时', x.hours != null ? num(x.hours) : e(x.period_text || '—')],
    ['章节数', num(x.chapters)], ...(scope === 'library' ? [['建课人', e(x.teacher_name) + (x.matched ? '' : '（工号没对上账号，等老师认领）')], ['所属', e(x.org_name || x.college_name)]] : []),
    ['教学团队', e(x.team_names || '')], ['对应教务课', x.origin === 'CX' && x.identity.startsWith('JW|') ? e(x.identity.slice(3)) + ' <span class="muted small">同学年教务已有时只算一次</span>' : ''],
    ['超星最后修改', e(String(x.edited_at_source || '').slice(0, 10))]].filter(([k, v]) => ['学分', '学时'].includes(k) || (v && v !== '—'));
  const terms = c.table(['学期', '学年', '学分', '学时', '授课认定'], x.terms.map(t => [e(t.term_name), e(t.school_year), t.credit == null ? '缺学分' : num(t.credit), num(t.hours), e(t.counted === false ? '不重复计算' : ({pending: '待认定', approved: '已认定', excluded: '不计分'}[t.review] || '—'))]));
  let progress = '';
  if (x.application) { const d = await c.api('/applications/' + x.application.id).catch(() => null); if (d) progress = '<h3 class="mt16">培训课程申报进度</h3>' + progressHtml(d.progress, e); }
  const intro = x.description ? `<details class="cx-intro-box mt16"${x.description.length <= 160 ? ' open' : ''}><summary>课程简介</summary><div class="cx-intro small">${e(x.description)}</div></details>` : '';
  const problems = x.problems.map(p => c.note(p, true)).join('');
  const index = (scope === 'mine' ? mine.courses : library.items).indexOf(x);
  if (request !== detailRequest || context!==c || !formIsCurrent(context,page,user)) return;
  if (scope === 'mine') {
    if(typeof document!=='undefined')document.querySelectorAll('.my-course-name[data-course-index]').forEach(row=>row.setAttribute('aria-current',String(row.dataset.courseIndex===String(index))));
    const [label,tone,hint]=declarationState(x),raw=originalCourse(x);
    const detail=courseFactsHtml(c,raw,'mc:'+index,`<span class="badge ${tone}">${e(label)}</span>`)+`<p class="my-course-declaration">${e(hint)}</p><details class="cx-intro-box mt16"><summary>逐学期授课与学分认定</summary><p class="small muted">基本信息展示最近一条来源记录；各学期核算学分以以下记录为准。</p>${terms}</details>${progress}`;
    const foot=`<span class="cx-detail-note">课程学分不等同于教师积分。</span>${c.act('返回课程列表','close')}${url?`<a class="btn" href="${e(url)}" target="_blank" rel="noopener noreferrer">去超星看课</a>`:''}${x.application?c.act(x.application.state==='RETURNED'?'去补正':'查看申报','app-detail',x.application.id,'primary'):applyButton(x,index,'primary','申报这门课程')}`;
    const workspace=typeof document!=='undefined'&&document.getElementById('mc-course-workspace');
    if(workspace){workspace.querySelector('.cx-course-detail').innerHTML=detail;workspace.querySelector('.cx-course-detail').scrollTop=0;workspace.querySelectorAll('[data-course-index]').forEach(card=>{const selected=card.dataset.courseIndex===String(index);card.classList.toggle('selected',selected);card.setAttribute('aria-current',String(selected))});document.getElementById('mc-course-footer').innerHTML=foot;return;}
    const visible=(mineVisible.includes(index)?mineVisible:mine.courses.map((_,i)=>i)).filter(i=>mine.courses[i].origin===x.origin);
    c.modal('我的课程 · 课程详情',`<div id="mc-course-workspace" class="cx-course-workspace"><section class="cx-course-list" aria-label="我的课程列表"><h3>共 ${visible.length} 条课程记录</h3><div class="cx-course-scroll">${visible.map(i=>onlineCard(c,originalCourse(mine.courses[i]),i,i===index,'mc-detail')).join('')}</div></section><section class="cx-course-detail" aria-label="课程详情">${detail}</section></div>`,`<div id="mc-course-footer">${foot}</div>`,true,'我的课程 / 课程详情');
    return;
  }
  const foot = [url ? `<a class="btn" href="${e(url)}" target="_blank" rel="noopener noreferrer">去超星看课 ↗</a>` : '',
    scope === 'mine' && !x.application ? applyButton(x, index, 'primary') : '',
    x.application ? c.act('查看申报', 'app-detail', x.application.id) : '', c.act('关闭', 'close')].join('');
  c.modal(x.course_name, problems + `<dl class="kv">${rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('')}</dl><h3 class="mt16">开课学期</h3>${terms}${intro}${progress}<p class="small muted mt16">学分按学期逐条算：同一学年教务已有这门课时超星课只算一次。同一门课只能申报一次培训课程，不在别的学年重复申报。</p>`, foot, true);
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

// 首页“我的超星课”：本学年在用门数、已认定学分、要处理的课（缺学分、被退回）。
export async function homeCoursesHtml(ctx) {
  c = ctx;
  const e = c.esc;
  let d;
  try { d = await c.api('/applications/teaching-courses'); } catch { return ''; }
  if (!Array.isArray(d?.courses)) return '';
  mine = d;
  mineVisible = [];
  const cx = d.courses.filter(x => x.origin === 'CX');
  const notes = deadlineNotes(d);
  if (!cx.length) return notes ? `<section class="card"><div class="card-head"><div><h2>培训课程申报</h2></div>${c.act('去我的课程', 'nav-mycourses', 'jw', 'text')}</div><div class="card-pad">${notes}</div></section>` : '';
  const now = cx.filter(x => x.years.includes(d.school_year_now));
  const credit = Number(d.years?.find(y => y.school_year === d.school_year_now)?.cx_credit ?? 0);
  const todo = cx.map(x => [x, d.courses.indexOf(x)]).filter(([x]) => x.problems.length || x.application?.state === 'RETURNED').slice(0, 3);
  const row = ([x, i]) => `<div class="apply-home-row"><div><strong>${e(x.course_name)}</strong></div><span class="${x.application?.state === 'RETURNED' ? 'red' : 'mc-problem'}">${e(x.application?.state === 'RETURNED' ? '培训课程申报被退回' : x.problems[0].split('：')[0])}</span>${c.act('查看', 'mc-detail', String(i), 'sm')}</div>`;
  return `<section class="card"><div class="card-head"><div><h2>我的超星课</h2><p>作为建课人 · ${e(d.school_year_now)} 学年</p></div>${c.act('全部 ' + cx.length + ' 门', 'nav-mycourses', 'cx', 'text')}</div><div class="card-pad">${notes}<div class="mc-home-stats"><span><b>${now.length}</b>本学年在用</span><span><b>${credit.toFixed(1)}</b>已认定学分</span><span><b>${todo.length}</b>需要处理</span></div>${todo.map(row).join('')}</div></section>`;
}

export async function courseAction(action, id, ctx) {
  c = ctx;
  if (action === 'mc-detail') return /^\d+$/.test(String(id)) && courseDetail(mine?.courses[Number(id)], 'mine');
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
  if(action==='app-mine-filter'){applicationFilter=['draft','pending','returned','done'].includes(id)?id:'';return ctx.render();}
  c = ctx;
  if (action === 'app-detail') return showApplication(id);
  if (action === 'app-edit') return edit(id);
  if (action === 'app-upload') return upload(id);
  if (action === 'app-course-new') return manualCourseForm(null, id || '');
  if (action === 'app-base-new') return baseForm();
  if (action === 'app-trainer-new') return trainerForm(null, id || 'internal');
  if (action === 'trainer-recommend') return c.formModal('推荐进入省级师资库', c.note('只在系统里记一笔推荐，实际报送仍走湘培直通车接口。') + c.reasonFields('择优推荐进入省级师资库', '推荐说明'), async v => {
    await c.api('/applications/trainers/' + id + '/recommend', {method: 'POST', body: {reason: v.reason, basis: v.basis}});
    c.closeModal(); c.toast('已记录推荐'); await c.render();
  }, {submit: '确认推荐'});
  const map = {'app-approve': 'approve', 'app-return': 'return', 'app-submit': 'submit', 'app-withdraw': 'withdraw'};
  if (map[action]) {
    if (opened?.item?.id !== id) await load(id);
    return decide(id, map[action]);
  }
  throw Error('操作无效');
}
