import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
const source=fs.readFileSync(new URL('../../frontend/app.js',import.meta.url),'utf8');

test('三级考核菜单保留且内部有四类对象页签',()=>{
  assert.match(source,/assessment:'三级考核'/);
  assert.match(source,/\['teacher','dept','college','school'\]/);
  assert.match(source,/教师考核.*教研室考核.*学院考核.*学校考核/s);
});

test('组织考核前端只调用正式组织接口而不是教师汇总冒充',()=>{
  assert.match(source,/\/organization-assessments\?/);
  assert.match(source,/\/organization-assessments\/calculate/);
  assert.match(source,/\/organization-assessment-rules/);
  assert.match(source,/逐指标原始值、数据来源、统计范围、公式、权重、规则版本和取数时间/);
});

test('组织规则和状态动作均有真实handler连接',()=>{
  for(const token of ['org-assessment-calc','org-assessment-action','org-rule-form','org-rule-trial','org-rule-action']){
    assert.match(source,new RegExp("['\"]?"+token.replaceAll('-','\\-')+"['\"]?"));
  }
});

test('普通教师不会出现组织考核页签集合',()=>{
  assert.match(source,/me\.role\.kind==='dept'\?\['teacher','dept'\]:\['teacher'\]/);
});

test('teacher home uses explicit latest assessment summary instead of first score-sorted row', () => {
  assert.match(source, /assessment-summary\/latest/)
  assert.match(source, /最近考核得分/)
  assert.doesNotMatch(source, /考核列表首条得分/)
})

test('organization management consumes server workbench with todos and assessment progress', () => {
  assert.match(source, /organization-workbench/)
  assert.match(source, /本范围待处理事项/)
  assert.match(source, /教师考核处理进度/)
})

test('sync workspace exposes procurement data catalog and manual supplement without fake success', () => {
  assert.match(source, /connections\/catalog/)
  assert.match(source, /实施人员补传/)
  assert.match(source, /真实接口尚未连接，没有向外发送数据/)
  assert.match(source, /manual-sync/)
})

test('sync task details expose per-item logs and single or batch retry', () => {
  assert.match(source, /逐笔同步记录/)
  assert.match(source, /sync-item-retry/)
  assert.match(source, /sync-tasks\/.*retry-failed/)
  assert.match(source, /单条补传/)
})

test('base settings consume server dictionaries without allowing workflow-state configuration', () => {
  assert.match(source, /api\('\/dictionaries'\)/)
  assert.match(source, /business_dictionary:'业务字典与状态显示'/)
  assert.match(source, /不能新增、删除状态码或改变流程/)
  assert.match(source, /Object\.assign\(labels,businessConfig\.status_labels/)
})

test('record source, notice category and Excel row limit use school configuration', () => {
  assert.match(source, /businessConfig\.record_sources\.filter/)
  assert.match(source, /manualSources\.map/)
  assert.match(source, /businessConfig\.notice_categories\.map/)
  assert.match(source, /businessConfig\.import_max_rows/)
})

test('unified todo can land directly on organization assessment detail', () => {
  assert.match(source, /organization_assessment:showOrgAssessment/)
  assert.match(source, /\['assessment','organization_assessment'\]\.includes\(x\.type\)/)
})

test('school cockpit reads real connection summary instead of hardcoded NOT_CONNECTED badge', () => {
  assert.match(source, /connections\/summary/)
  assert.match(source, /connection_state/)
  assert.match(source, /latest_task/)
  assert.doesNotMatch(source, /async cockpit\(\)[\s\S]{0,3000}badge\('NOT_CONNECTED'\)/)
})

test('cockpit shows descriptive score bands and labels active scope instead of inventing school grades', () => {
  assert.match(source, /assessment_score_bands/)
  assert.match(source, /已生成教师考核分值分布/)
  assert.match(source, /不定义“优秀\/合格”等学校等级/)
  assert.match(source, /活跃培训项目/)
  assert.match(source, /活跃课程/)
  assert.match(source, /不冒充学校基础库总量/)
})

test('teacher workbench separates teaching facts from teacher participation facts', () => {
  assert.match(source, /teacher-activity-summary/)
  assert.match(source, /本人授课记录/)
  assert.match(source, /本人参训记录/)
  assert.match(source, /授课与本人参训分开统计/)
  assert.match(source, /\/participations\?/)
})

test('Excel center exposes participation as its own import and export contract', () => {
  assert.match(source, /\['participations','教师参训记录'\]/)
  assert.match(source, /导出参训表格/)
  assert.match(source, /participations:'教师参训'/)
})

test('school data hub exposes explicit inbound preview and confirm rather than direct hidden write', () => {
  assert.match(source, /inbound\/preview/)
  assert.match(source, /生成预览/)
  assert.match(source, /确认写入主数据/)
  assert.match(source, /inbound-batches\/.*\/confirm/)
  assert.match(source, /尚未写正式主数据/)
})

test('cockpit distinguishes active transaction scale from reference master totals', () => {
  assert.match(source, /master_data_counts/)
  assert.match(source, /当前筛选活跃规模按有效培训流水去重/)
  assert.match(source, /基础主数据：项目/)
})

test('operations exposes an authorized delivery configuration and data dictionary download', () => {
  assert.match(source, /下载初始化配置与数据字典/)
  assert.match(source, /\/delivery\/configuration\.xlsx/)
})

test('sync workspace exposes full incremental pull and explicitly approved schedules', () => {
  assert.match(source, /全量 \/ 增量拉取/)
  assert.match(source, /定时同步计划/)
  assert.match(source, /inbound-pull/)
  assert.match(source, /schedule-form/)
  assert.match(source, /只有真实连接已启用，并且管理员明确批准自动入库/)
})

test('sync page queries integration tasks so inbound pull is not confused with exports', () => {
  assert.ok(source.includes("api('/tasks?'+query({kind:'integration',...f}))"))
  assert.ok(source.includes('connection_id:c.id'))
})

test('local mapping trial selects a real procurement data type code from catalog', () => {
  assert.match(source, /async function mappingTrial\(id\).*connections\/catalog/s)
  assert.match(source, /采购数据类型/)
  assert.doesNotMatch(source, /field\('data_type','数据类型','text','教师基础信息'\)/)
})

test('live connection editor preserves actual mapping and never auto-fills guessed source fields', () => {
  assert.match(source, /async function connectionForm\(id\).*connections\/catalog/s)
  assert.ok(source.includes('JSON.stringify(x.mappings||[],null,2)'))
  assert.ok(!source.includes('SAMPLE-001')); assert.ok(!source.includes('x.mappings:[example]'))
  assert.match(source, /entry\.data_types\.map/)
  assert.match(source, /请选择/)
})
