import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {aggregateFilters,businessFilters,drillFilters,navigationHash,restoreNavigation} from '../../frontend/scope.js';
const source=fs.readFileSync(new URL('../../frontend/app.js',import.meta.url),'utf8');
const current={org_id:'org1',project_code:'P1',state:'SCHOOL',returned:'true',period_id:'period2026'};
for(const page of ['home','cockpit','organization']) {
  test(`${page} preserves assessment status in URL without polluting training scope`,()=>{
    const result=restoreNavigation(navigationHash(page,current,current.period_id),{home:'首页',cockpit:'驾驶舱',organization:'组织'});
    assert.equal(result.filter.state,'SCHOOL');assert.equal(result.filter.returned,'true');
    assert.equal(result.periodId,'period2026');assert.equal(businessFilters(result.filter).state,undefined);
  });
}
test('aggregate drill preserves status only when drilling into assessments',()=>{
  assert.equal(aggregateFilters(current).state,'SCHOOL');
  assert.equal(drillFilters('assessment',current).state,'SCHOOL');
  assert.equal(drillFilters('assessment',current).returned,'true');
  assert.equal(drillFilters('records',current).state,undefined);
  assert.equal(drillFilters('records',current).returned,undefined);
});
test('organization copy, print and ranking have registered handlers and server calls',()=>{
  for(const handler of ["'org-print':printOrganizationAssessment","'org-ranking':organizationRanking","'org-rule-copy':copyOrganizationRule"])assert.ok(source.includes(handler));
  assert.match(source,/organization-assessments\/ranking/);
  assert.match(source,/过程稿（非最终结果）/);assert.match(source,/own_organization_only/);
});
test('connection controls separate probe activation disconnect and evidence download',()=>{
  for(const handler of ['connection-probe','connection-activate','connection-disconnect','sync-proof'])assert.ok(source.includes(handler));
  assert.match(source,/sync-tasks\/.*\/evidence/);
  assert.match(source,/state_filter_note/);
});
