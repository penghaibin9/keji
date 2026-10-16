// 申请进度组件：详情、我的申请、首页三处共用同一份后端进度数据。
import test from 'node:test';
import assert from 'node:assert/strict';
import {progressHtml, myCoursesHtml} from '../../frontend/applications.js';

const esc = s => String(s ?? '').replace(/[&<>"]/g, ch => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'})[ch]);
const p = {label: '社会培训课申报', text: '学院审批中 · 第 3 步 / 共 4 步', headline: '测试学院一负责人正在审批。无需你操作。', tone: 'blue',
  nodes: [{label: '提交', state: 'done', who: '测试教师一', at: '2026-10-01T09:00:00'}, {label: '教研室审核', state: 'done', who: '<b>主任</b>', acting_for: '缺负责人由学院代办'},
    {label: '学院审批', state: 'current', who: '院长', waiting_days: 3}, {label: '进入培训课程库', state: 'todo'}]};

test('full progress shows who, waiting days and handling tags, escaped', () => {
  const html = progressHtml(p, esc);
  assert.match(html, /<li class="current"><i>3<\/i><span>学院审批<\/span><small>院长 · 已等 3 天<\/small>/);
  assert.match(html, /缺负责人由学院代办/);
  assert.match(html, /&lt;b&gt;主任/);
  assert.match(html, /无需你操作/);
  assert.match(html, /测试教师一 · 2026-10-01 17:00/);  // UTC 显示成北京时间
});

test('compact progress keeps the nodes and one line only', () => {
  const html = progressHtml(p, esc, {compact: true});
  assert.match(html, /apply-progress compact/);
  assert.doesNotMatch(html, /已等|无需你操作|缺负责人/);
  assert.equal([...html.matchAll(/<li /g)].length, 4);
});

test('returned node shows the reason', () => {
  const html = progressHtml({...p, tone: 'red', nodes: [p.nodes[0], {label: '教研室审核', state: 'returned', reason: '补课件审查'}]}, esc);
  assert.match(html, /<li class="returned"><i>!<\/i>/);
  assert.match(html, /退回原因：补课件审查/);
});

const ctx = data => ({esc, api: async () => data, note: t => `<div class="note">${esc(t)}</div>`, table: (h, rows, empty) => rows.length ? rows.map(r => r.join('|')).join('\n') : empty,
  act: (label, action, id = '') => `<button data-action="${action}" data-id="${esc(id)}">${esc(label)}</button>`});
const card = (over = {}) => ({identity: 'CX|二维绘图软件应用', origin: 'CX', id: 't1', course_code: 'X1', course_name: '二维绘图软件应用', credit: 2, hours: 32, chapters: 12,
  terms: [{term_name: '2025-2', school_year: '2025-2026'}, {term_name: '2024-2', school_year: '2024-2025'}, {term_name: '2023-2', school_year: '2023-2024'}],
  years: ['2025-2026', '2024-2025', '2023-2024'], problems: [], application: null, cover_url: 'https://evil.example/a.png', ...over});

test('超星课一门课一张卡，写学期数，没申报的可以直接申报，封面只用超星图片', async () => {
  const html = await myCoursesHtml(ctx({courses: [card(), card({identity: 'CX|机械制图', course_name: '机械制图', credit: null, problems: ['超星没填学分'], terms: [{term_name: '2025-1', school_year: '2025-2026'}], years: ['2025-2026'],
    application: {id: 'a1', state: 'RETURNED', state_label: '退回补正'}})]}), 'cx', '');
  assert.equal([...html.matchAll(/class="mc-card"/g)].length, 2);
  assert.match(html, /3 个学期/);
  assert.match(html, /data-action="mc-apply" data-id="0">申报为社会培训课/);
  assert.match(html, /退回补正.*去补正/s);
  assert.match(html, /超星没填学分/);
  assert.doesNotMatch(html, /<img/);
});

test('按学年筛选：只列这个学年开过的课；教务课在教务课页签', async () => {
  const data = {courses: [card(), card({identity: 'JW|K1', origin: 'JW', course_name: '高等数学', years: ['2025-2026'], terms: [{term_name: '2025-2026-1', school_year: '2025-2026'}]})]};
  assert.equal([...(await myCoursesHtml(ctx(data), 'cx', '2023-2024')).matchAll(/class="mc-card"/g)].length, 1);
  const jw = await myCoursesHtml(ctx(data), 'jw', '');
  assert.match(jw, /高等数学/);
  assert.doesNotMatch(jw, /二维绘图/);
});

test('申报期限：截止的课不出申报按钮，补报中改成补报，到期前提醒', async () => {
  const data = {courses: [card({window: {state: 'closed', deadline: '2025-09-30'}}),
    card({identity: 'CX|茶艺', course_name: '茶艺', window: {state: 'reopened', deadline: '2025-09-30', reopen_until: '2025-10-20'}}),
    card({identity: 'CX|焊接', course_name: '焊接', window: {state: 'open', deadline: '2026-09-30'}})],
    deadline_reminders: [{school_year: '2025-2026', state: 'open', deadline: '2026-09-30', days_left: 5}]};
  const html = await myCoursesHtml(ctx(data), 'cx', '');
  assert.match(html, /已于 2025-09-30 截止/);
  assert.doesNotMatch(html, /data-id="0">申报为社会培训课/);
  assert.match(html, /data-id="1">补报为社会培训课/);
  assert.match(html, /data-id="2">申报为社会培训课/);
  assert.match(html, /2025-2026 学年的社会培训课申报将于 2026-09-30 截止，还剩 5 天/);
});
