import test from 'node:test';
import assert from 'node:assert/strict';
import {renderSchoolCockpit,drawSchoolChart,chartRegionAt,bindSchoolCockpit} from '../../frontend/school-cockpit.js';
import {navigationHash,restoreNavigation,businessFilters} from '../../frontend/scope.js';

test('原表展示区分零值与缺失，转义来源文字，不把人天累计成人次',()=>{
 const period={year:2026,label:'2026年1—8月',start:'2026-01-01',end:'2026-08-31'};
 const d={period,periods:[period],read_at:'2026-10-19T00:00:00Z',version:'hash',college:'',project:'',
  totals:{person_times:'0',person_days:'20',records:2,colleges:1,person_times_colleges:1},
  colleges:['合成<学院>'],projects:[{id:'p',name:'项目<script>',college:'合成<学院>'}],rank:[{name:'合成<学院>',value:'0'}],
  composition:[{name:'合成<学院>',value:2}],comparison:[{...period,records:2,colleges:1}],
  table:[{college:'合成<学院>',records:{2026:2},selected_records:2,quantities:[{value:'0',unit:'人次'},{value:'20',unit:'人天'}],status:'待核定'},
   {college:'缺资料学院',records:{2026:null},selected_records:null,quantities:[],status:'待补资料'}],
  details:[{college:'合成<学院>',name:'项目<script>',file:'学校原表.xlsx',row:4,cell:'E4',value:'20',unit:'人天',numbered:true,status:'学校未核定'}],warnings:[],excluded:[],note:'原表报送值',comparison_note:'非同期资料对照'};
 const html=renderSchoolCockpit(d,{icon:()=>''});
 assert.match(html,/sc-main-value">0<small>人次/);assert.match(html,/20 <span>人天/);
 assert.match(html,/未提供/);assert.match(html,/合成&lt;学院&gt;/);assert.match(html,/项目&lt;script&gt;/);
 assert.doesNotMatch(html,/<script>|NaN|undefined|sc-main-value">20<small>人次/);
 assert.match(html,/aria-label="教研室" disabled/);assert.match(html,/aria-label="课程" disabled/);
 assert.match(html,/data-sc-open="sc-sources"/);
 assert.match(html,/待导入台账/);
 assert.match(html,/data-sc-photo-open/);assert.match(html,/<dialog class="sc-photo-viewer"/);
 assert.match(html,/data-sc-unit="人天"/);assert.match(html,/data-sc-year="2026"/);
 assert.match(html,/按项目记录筛选合成&lt;学院&gt;/);
 const ledger={id:'ledger<id>',year:2026,version_no:2,review_state:'待核定',is_latest:false};
 d.table[0].ledger=ledger;d.details[0].ledger=ledger;
 const imported=renderSchoolCockpit(d,{icon:()=>''});
 assert.match(imported,/已导入 · 第2版 · 待核定（历史版本）/);
 assert.match(imported,/href="#ledgers\?year=2026&amp;ledger_id=ledger%3Cid%3E"/);
 assert.doesNotMatch(imported,/ledger<id>/);
 d.totals.person_times_colleges=0;d.totals.person_times=null;
 assert.match(renderSchoolCockpit(d,{icon:()=>''}),/sc-main-value">20<small>人天/);
 d.totals.colleges=0;d.totals.person_days=null;d.totals.records=0;d.rank=[];
 const missing=renderSchoolCockpit(d,{icon:()=>''});
 assert.match(missing,/sc-main-value">未提供<small><\/small>/);
 assert.match(missing,/当前学院尚未提供本期资料/);assert.doesNotMatch(missing,/未提供<small>条/);
 assert.match(missing,/暂无本期明细/);assert.doesNotMatch(missing,/class="sc-chart-actions"/);
});

function drawnRegions(kind,d){
 const previous=globalThis.window;globalThis.window={devicePixelRatio:2};
 const context=Object.fromEntries(['scale','fillText','beginPath','stroke','setLineDash','moveTo','lineTo','fillRect','arc'].map(name=>[name,()=>{}]));
 const canvas={dataset:{scChart:kind},clientWidth:200,clientHeight:200,getContext:()=>context};
 try{return drawSchoolChart(canvas,d)}finally{globalThis.window=previous}
}

test('环图只命中实际扇区，中央空洞不误筛选，百分比按记录总数计算',()=>{
 const regions=drawnRegions('donut',{totals:{records:10},composition:[{name:'甲学院',value:7},{name:'乙学院',value:3}]});
 assert.equal(chartRegionAt(regions,100,100),undefined);
 assert.equal(chartRegionAt(regions,199,199),undefined);
 assert.equal(chartRegionAt(regions,100,30).filter.report_college,'甲学院');
 assert.equal(chartRegionAt(regions,50,50).filter.report_college,'乙学院');
 assert.match(chartRegionAt(regions,50,50).label,/3条，占本期30.0%/);
 assert.deepEqual(drawnRegions('donut',{totals:{records:0},composition:[]}),[]);
});

test('条形图零值可查看，缺失量不冒充零；点击标签或柱形定位同一学院',()=>{
 const regions=drawnRegions('rank',{rank:[{name:'零值学院',value:'0'},{name:'缺资料学院',value:null}]});
 const zero=chartRegionAt(regions,10,regions[0].y+2),missing=chartRegionAt(regions,190,regions[1].y+2);
 assert.equal(zero.filter.report_college,'零值学院');assert.match(zero.label,/0人次/);
 assert.equal(missing.filter.report_college,'缺资料学院');assert.match(missing.label,/未提供/);assert.doesNotMatch(missing.label,/0人次/);
 assert.equal(chartRegionAt(regions,10,0),undefined);
});

test('年度柱图切换资料年度且保留非同期说明，不把无资料画成有记录',()=>{
 const regions=drawnRegions('years',{period:{year:2026},comparison:[{year:2025,label:'2025年全年',records:null,colleges:0},{year:2026,label:'2026年1—8月',records:28,colleges:6}]});
 assert.equal(chartRegionAt(regions,40,190).filter.report_year,'2025');
 assert.match(chartRegionAt(regions,40,190).label,/未提供/);
 assert.equal(chartRegionAt(regions,150,190).filter.report_year,'2026');
 assert.match(regions[1].label,/28条.*非同期，不算同比/);
});

test('来源项目按学院编号首行下钻，续行进入所属项目，未关联原件不生成假链接',()=>{
 const period={year:2025,label:'2025年全年',start:'2025-01-01',end:'2025-12-31'},ledger={id:'ledger-a',year:2025,version_no:1,review_state:'待核定',is_latest:true};
 const detail=(row,numbered,linked=ledger)=>({college:'甲学院',row,numbered,ledger:linked,name:'来源'+row,file:'原表.xlsx',cell:'E'+row,value:'8',unit:'人次',status:'待核'});
 const d={period,periods:[period],read_at:'2026-10-19T00:00:00Z',version:'v',college:'',project:'',totals:{person_times:'24',person_days:null,records:3,colleges:1,person_times_colleges:1},colleges:['甲学院'],projects:[],rank:[],composition:[],comparison:[],table:[],details:[detail(4,true),detail(5,false),detail(8,true),detail(9,true,null)],warnings:[],excluded:[],note:'',comparison_note:''};
 const html=renderSchoolCockpit(d,{icon:()=>''});
 assert.equal((html.match(/history_ledger=ledger-a&amp;history_row=4/g)||[]).length,2);
 assert.equal((html.match(/history_ledger=ledger-a&amp;history_row=8/g)||[]).length,1);
 assert.doesNotMatch(html,/history_row=5|history_row=9/);
 assert.match(html,/data-sc-source-row data-sc-row-unit="人次"/);
});

test('原表筛选可刷新恢复，并与教师授课统计的查询字段分开',()=>{
 const source={report_year:'2026',report_college:'软件学院',report_project:'source-4',org_id:'o',project_code:'p'};
 const hash=navigationHash('cockpit',source,'cycle');
 const restored=restoreNavigation(hash,{cockpit:'学校管理驾驶舱'});
 assert.deepEqual(restored.filter,source);assert.equal(restored.periodId,'cycle');
 assert.deepEqual(businessFilters(restored.filter),{org_id:'o',project_code:'p'});
 const ledger=restoreNavigation(navigationHash('ledgers',{year:'2025',ledger_id:'source-ledger',source:'other'}),{ledgers:'学院台账与口径检查'});
 assert.deepEqual(ledger.filter,{year:'2025',ledger_id:'source-ledger',source:'other'});
});


test('来源单位筛选可从地址恢复，保留人天分列且不触发业务汇总查询',()=>{
 const form={addEventListener(){},elements:Object.fromEntries(['report_college','report_year','report_project'].map(k=>[k,{addEventListener(){}}]))};
 const rows=['人次','人天'].map(unit=>({dataset:{scRowUnit:unit},hidden:false}));
 const buttons=['','人次','人天'].map(unit=>({dataset:{scSourceUnit:unit},setAttribute(k,v){this[k]=v},addEventListener(k,f){this[k]=f}}));
 const panel={open:false},label={textContent:''};
 const root={querySelector:s=>({'#sc-filters':form,'#sc-sources':panel,'#sc-source-filter-label':label}[s]),querySelectorAll:s=>s==='[data-sc-source-row]'?rows:s==='[data-sc-source-unit]'?buttons:[]};
 const filter={report_year:'2026',report_unit:'人天'},restored=restoreNavigation(navigationHash('cockpit',filter),{cockpit:'驾驶舱'}).filter;
 let remembered='';bindSchoolCockpit(root,{details:[{unit:'人次'},{unit:'人天'}]},()=>{throw Error('不应重查汇总')},{sourceUnit:restored.report_unit,onSourceUnit:v=>{remembered=v}});
 assert.equal(panel.open,true);assert.deepEqual(rows.map(r=>r.hidden),[true,false]);assert.match(label.textContent,/人天 · 1行/);
 buttons[0].click();assert.equal(remembered,'all');assert.deepEqual(rows.map(r=>r.hidden),[false,false]);
});
