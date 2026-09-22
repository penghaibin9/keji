import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {businessFilters,pageFilters,drillFilters,navigationHash,restoreNavigation,selectedPeriod} from '../../frontend/scope.js';
const titles={home:'首页',cockpit:'驾驶舱',records:'记录',assessment:'考核',organization:'组织',points:'积分'};
const filters={project_code:'P1',course_code:'C1',start:'2026-09-01',end:'2026-09-30',org_id:'c1',teacher_id:'t1'};

test('all approved scope keys survive a records drill',()=>{
  const result=drillFilters('records',filters,{org_id:'d1'});
  assert.deepEqual(result,{...filters,org_id:'d1'});
});
test('assessment drill carries business scope marker',()=>{
  assert.deepEqual(drillFilters('assessment',filters,{state:'TEACHER'}),{...filters,state:'TEACHER',business_scope:'true'});
});
test('workflow-only flags never leak into record SQL filters',()=>{
  assert.deepEqual(pageFilters('records',{...filters,state:'TEACHER',returned:'true',business_scope:'true'}),filters);
});
test('URL refresh/back restores exactly the applied context',()=>{
  const hash=navigationHash('assessment',{...filters,returned:'true',business_scope:'true'},'p');
  assert.deepEqual(restoreNavigation(hash,titles),{page:'assessment',filter:{...filters,returned:'true',business_scope:'true'},periodId:'p'});
});
test('selecting all periods really clears the prior period',()=>{
  assert.equal(selectedPeriod({value:''},'old-period'),'');
  assert.equal(selectedPeriod(null,'old-period'),'old-period');
});
test('duplicate URL scope is rejected rather than widened',()=>{
  assert.throws(()=>restoreNavigation('#records?org_id=a&org_id=b',titles));
});
test('non-business pages do not inherit workflow flags or business IDs',()=>{
  assert.deepEqual(pageFilters('points',{...filters,state:'TEACHER'}),{teacher_id:'t1',org_id:'c1'});
});
test('unknown and prototype-like page names never become valid routes',()=>{
  assert.equal(restoreNavigation('#__proto__?org_id=x',titles).page,'home');
});
test('malformed values are rejected',()=>{
  assert.throws(()=>businessFilters({q:'x'.repeat(101)}));
  assert.throws(()=>businessFilters({org_id:['x']}));
});
const source=readFileSync(new URL('../../frontend/app.js',import.meta.url),'utf8');
function actualNavigationContext(){
  const context={titles,page:'cockpit',filter:{...filters},periodId:'p',tablePage:2,location:{hash:'#cockpit',pathname:'/',search:''},
    businessFilters,pageFilters,drillFilters,navigationHash,restoreNavigation,selectedPeriod,
    $:()=>null,render:()=>{},setMobileMenu:()=>{},history:{replaceState(...args){context.location.hash=args[2].slice(args[2].indexOf('#'));}}};
  vm.createContext(context);
  for(const name of ['syncLocation','nav','scopeNav']){
    vm.runInContext(source.split('\n').find(x=>x.startsWith('function '+name+'(')),context);
  }
  return context;
}
test('actual app scopeNav preserves conditions and persists them into hash',()=>{
  const c=actualNavigationContext();vm.runInContext("scopeNav('records',{org_id:'d1'})",c);
  assert.deepEqual(JSON.parse(JSON.stringify(c.filter)),{...filters,org_id:'d1'});
  assert.equal(restoreNavigation(c.location.hash,titles).periodId,'p');
});
test('actual bindFilters clears period and preserves drill identity',()=>{
  const c=actualNavigationContext();c.page='assessment';c.filter={...filters,business_scope:'true'};
  let listener;
  const form={addEventListener(name,fn){listener=fn;}};
  c.$=s=>s==='#filters'?form:s==='#period-filter'?{value:''}:null;
  c.FormData=class{*[Symbol.iterator](){yield ['project_code','P1'];yield ['returned','true'];}};
  c.toast=()=>{};c.teachers=[];
  const start=source.indexOf('function bindFilters(){'),end=source.indexOf('const listQuery=',start);
  vm.runInContext(source.slice(start,end),c);vm.runInContext('bindFilters()',c);
  listener({preventDefault(){}});
  assert.equal(c.periodId,'');assert.equal(c.filter.business_scope,'true');assert.equal(c.filter.returned,'true');
  assert.equal(new URLSearchParams(c.location.hash.split('?')[1]).get('period_id'),null);
});
test('HTML controls and handlers are connected in the real app source',()=>{
  assert.ok(source.includes('returned:true'));
  assert.ok(source.includes("'scope-nav':id=>scopeNav(id)"));
  assert.ok(source.includes('filtersBar({search:false,dates:true,project:true,states:'));
  assert.ok(!source.includes("?.value||periodId"));
});
