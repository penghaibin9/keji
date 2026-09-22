// Contract-only checks, not a browser navigation or rendering acceptance.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
const source=fs.readFileSync(new URL('../../frontend/app.js',import.meta.url),'utf8');
test('dashboard separates business commit from transport completion',()=>{
  assert.ok(source.includes('badge(x.latest_task.display_state||x.latest_task.state)'));
  assert.ok(source.includes('成功 / 失败 / 待确认（条）'));
  assert.ok(source.includes('x.latest_task.pending_confirmation_count??0'));
});
test('dashboard explains record counts and distinguishes empty successful pull',()=>{
  assert.ok(source.includes("NO_CHANGES:'拉取完成 · 无新增'"));
  assert.ok(source.includes('拉取完成但尚未确认入库的记录单列待确认'));
  assert.ok(source.includes('不能把0条失败解释为任务成功'));
});
