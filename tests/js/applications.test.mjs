// 申请进度组件：详情、我的申请、首页三处共用同一份后端进度数据。
import test from 'node:test';
import assert from 'node:assert/strict';
import {progressHtml} from '../../frontend/applications.js';

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
