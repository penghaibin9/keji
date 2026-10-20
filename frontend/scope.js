/* Query context only: this is not authorization. The server always rechecks scope. */
export const BUSINESS_KEYS = Object.freeze(['q','teacher_id','org_id','start','end','project_code','course_code']);
const PERIOD_PAGES = new Set(['home','cockpit','records','points','assessment','disputes','organization','rules']);
const WORKSPACE_KEYS=['q','org_id','workspace_status','workspace_pick','workspace_page','resource_page','package','one_skill'];
const PAGE_KEYS = Object.freeze({
  courses:WORKSPACE_KEYS,bases:WORKSPACE_KEYS,outcomes:WORKSPACE_KEYS,trainers:WORKSPACE_KEYS,
  home: [...BUSINESS_KEYS,'state','returned'], cockpit: [...BUSINESS_KEYS,'state','returned','report_year','report_college','report_project','report_unit'], records: [...BUSINESS_KEYS,'tab'], credits: ['tab','q','school_year','problem','review','origin','term_name','org_id','missing_credit'], creditreview: ['q','school_year','all','org_id','pick'], organization: [...BUSINESS_KEYS,'state','returned','tab'],
  assessment: [...BUSINESS_KEYS,'state','returned','business_scope','progress','tab'],
  points: ['teacher_id','org_id'], disputes: ['teacher_id','state'],
  ledgers: ['year','ledger_id','source','ledger_tab','ledger_filter'],
  projects: [...BUSINESS_KEYS,'project_view','project_status','project_pick','workspace_page','resource_page','history_year','history_issue','history_page','history_ledger','history_row'],
  qualifications: ['q','teacher_id','org_id','state'], rules: [],
  audit: ['q','module','result','start','end','actor','org_id','object_id','request_id','kind'], imports: ['q'], notices: ['q'], permissions: ['q','hr_state'],
  todos: ['q','type','stage','tab','state','period_id','org_id'], sync: [], sso:['tab','impl_step'], hub:['tab','impl_step','data_type','state'], province:['tab','impl_step','data_type','state'], guide:[], operations: [], exports: [], help: [],
});
function valuesFor(keys, values = {}) {
  const result = {};
  for (const key of keys) {
    const value = values[key];
    if (value === undefined || value === null || value === '') continue;
    if (typeof value !== 'string' || value.length > (key === 'q' ? 100 : 128) || /[\x00-\x1f]/.test(value))
      throw Error('筛选条件格式不正确，请重新选择。');
    result[key] = value;
  }
  return result;
}
export const businessFilters = values => valuesFor([...BUSINESS_KEYS,'period_id'], values);
export const aggregateFilters = values => valuesFor([...BUSINESS_KEYS,'period_id','state','returned'], values);
export const pageFilters = (page, values) => valuesFor(PAGE_KEYS[page] || [], values);
export function drillFilters(destination, current, overrides = {}) {
  const merged = {...businessFilters(current), ...(destination === 'assessment' ? valuesFor(['state','returned'],current) : {}), ...overrides};
  if (destination === 'assessment') merged.business_scope = 'true';
  return pageFilters(destination, merged);
}
export function navigationHash(page, filter, periodId = '') {
  const fields = pageFilters(page, filter);
  if (PERIOD_PAGES.has(page) && periodId !== '')
    fields.period_id = valuesFor(['period_id'], {period_id: periodId}).period_id;
  const q = new URLSearchParams(Object.entries(fields).sort(([a],[b]) => a.localeCompare(b))).toString();
  return '#' + page + (q ? '?' + q : '');
}
export function restoreNavigation(hash, titles) {
  const raw = hash.replace(/^#/, '');
  const split = raw.indexOf('?');
  const page = split < 0 ? raw : raw.slice(0, split);
  if (!Object.hasOwn(titles, page)) return {page:'home', filter:{}, periodId:''};
  const query = split < 0 ? '' : raw.slice(split + 1);
  const params = new URLSearchParams(query);
  const fields = {};
  for (const [key, value] of params) {
    if (Object.hasOwn(fields, key)) throw Error('筛选条件重复，请重置筛选。');
    Object.defineProperty(fields, key, {value, enumerable:true, configurable:true});
  }
  const filter = pageFilters(page, fields);
  const periodId = PERIOD_PAGES.has(page) ? (valuesFor(['period_id'], fields).period_id || '') : '';
  return {page, filter, periodId};
}
export function selectedPeriod(control, previous) {
  return control ? control.value : previous; // An empty value means ALL, not "keep old".
}
