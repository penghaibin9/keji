import test from 'node:test';
import assert from 'node:assert/strict';
import {historyProjectsPage,projectViewTabs,historyDateSummary} from '../../frontend/history-projects.js';
import {navigationHash,restoreNavigation} from '../../frontend/scope.js';

const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function context(answer,filter={}){
 const requests=[];
 return {filter,requests,esc,api:async path=>{requests.push(path);return answer},
  pageHead:(text,actions)=>'<header>'+esc(text)+actions+'</header>',note:text=>'<p>'+esc(text)+'</p>',
  table:(heads,rows,empty='')=>'<table><thead>'+heads.map(h=>'<th>'+esc(h)+'</th>').join('')+'</thead><tbody>'+rows.map(r=>'<tr>'+r.map(v=>'<td>'+v+'</td>').join('')+'</tr>').join('')+'</tbody></table>'+(!rows.length?esc(empty):''),
  act:(label,action,id)=>'<button data-action="'+esc(action)+'" data-id="'+esc(id)+'">'+esc(label)+'</button>',
  downloads:items=>items.map(a=>'<a data-attachment="'+esc(a.id)+'">'+esc(a.name)+'</a>').join('')};
}
const history={owner:{name:null,role:null,evidence:null,account_id:null},confirmed_start:null,confirmed_end:null,date_facts:[],conflicts:[],pending_notes:[],attachment_ids:[]};

test('日期依据按文件指纹关联原图，重名文件和无权限时不误开',async()=>{
 const fingerprint='a'.repeat(64),fact={kind:'source',text:'现场日期',evidence:'学校资料/图片1.png；文件指纹：'+fingerprint+'；位置：现场屏幕',start_date:'2026-03-30',end_date:'2026-03-30'};
 const answer={ledger_id:'ledger-a',year:2026,name:'历史项目',college:'学院',sequence:'1',status:'资料待完善',source_file:'原表.xlsx',source_rows:[4],history:{...history,date_facts:[fact],date_prefill:fact},missing:[],rows:[],can_read_files:true,attachments:[{id:'wrong',name:'图片1.png',sha256:'b'.repeat(64),mime:'image/png'},{id:'right',name:'图片1.png',sha256:fingerprint,mime:'image/png'}]};
 const c=context(answer,{history_ledger:'ledger-a',history_row:'4'}),html=await historyProjectsPage(c);
 assert.equal((html.match(/data-action="attachment-preview" data-id="right"/g)||[]).length,2);
 assert.doesNotMatch(html,/data-action="attachment-preview" data-id="wrong"/);
 assert.match(html,/class="material-list mt8"/);assert.match(html,/data-material-name="图片1.png"/);
 assert.doesNotMatch(html,/[a-f0-9]{64}/);assert.match(html,/待学校复核/);
 answer.can_read_files=false;assert.doesNotMatch(await historyProjectsPage(c),/查看原图|data-attachment/);
 answer.can_read_files=true;answer.attachments[1].mime='application/pdf';
 assert.match(await historyProjectsPage(c),/data-action="attachment-download" data-id="right"/);
});

test('history list shows numbered sources and missing facts, with original business reachable',async()=>{
 const answer={year:2025,years:[2025,2026],issue:'missing',counts:{all:53,missing:53,conflict:2},note:'原件同源，续行归入编号',items:[{college:'软件学院',sequence:'1',name:'<历史项目>',source_rows:[4,5],ledger_id:'ledger-a',row_no:4,history,status:'资料待完善',materials_count:2}]};
 const c=context(answer,{history_year:'2025',history_issue:'missing'}),html=await historyProjectsPage(c);
 assert.equal(c.requests[0],'/social/history-projects?issue=missing&year=2025');
 assert.match(html,/&lt;历史项目&gt;/);assert.match(html,/第4行、第5行/);assert.match(html,/待确认/);
 assert.match(html,/href="#projects\?project_view=business&amp;history_year=2025&amp;history_issue=missing"/);assert.match(html,/history_issue=missing&amp;history_ledger=ledger-a&amp;history_row=4/);
 assert.doesNotMatch(html,/social-transition|social-project-new|social-close|生成项目草稿/);
 assert.match(html,/专属材料/);assert.match(html,/2份已关联/);
 answer.items[0].materials_count=0;assert.match(await historyProjectsPage(c),/<td>待关联<\/td>/);
});

test('history detail keeps date nature and hides attachment links without permission',async()=>{
 const answer={ledger_id:'ledger-a',year:2025,name:'有计划材料的历史项目',college:'软件学院',sequence:'1',status:'资料待完善',source_file:'学校原表.xlsx',source_rows:[4,5],history:{...history,date_facts:[{kind:'planned',text:'拟于六月安排',evidence:'方案第2页',start_date:'2025-06-01',end_date:'2025-06-05'}]},missing:['负责人账号待关联'],rows:[{row_no:4,name:'历史项目',claimed_raw:'0人次',people_raw:'0',hours:8,materials:null}],attachments:[{id:'hidden',name:'不应显示'}],can_read_files:false};
 const c=context(answer,{project_view:'history',history_year:'2025',history_issue:'conflict',history_ledger:'ledger-a',history_row:'4'}),html=await historyProjectsPage(c);
 assert.equal(c.requests[0],'/social/history-projects/ledger-a/4');
 assert.match(html,/计划安排日期/);assert.match(html,/拟于六月安排/);assert.match(html,/0人次/);assert.match(html,/当前账号未授权读取材料文件/);
 assert.match(html,/history_issue=conflict/);assert.match(html,/source=school&amp;ledger_id=ledger-a/);
 assert.doesNotMatch(html,/data-attachment|null|undefined|social-transition|social-project-edit/);
 answer.can_read_files=true;answer.attachments=[{id:'proof',name:'项目专属材料.pdf'}];answer.project_id='real-project';
 const allowed=await historyProjectsPage(c);assert.match(allowed,/data-attachment="proof"/);assert.match(allowed,/social_project\|real-project/);
});

test('history deep links round trip all view, year, issue and source identity fields',()=>{
 const filter={project_view:'history',history_year:'2026',history_issue:'conflict',history_ledger:'ledger-a',history_row:'8'};
 const hash=navigationHash('projects',filter);
 assert.deepEqual(restoreNavigation(hash,{home:'首页',projects:'培训项目'}).filter,filter);
 const tabs=projectViewTabs(context({},filter),'business');assert.match(tabs,/学校历史资料/);assert.match(tabs,/项目业务办理/);
});

test('日期依据仅展示文件名和位置，不渲染技术校验入口且保留原始依据数据',async()=>{
 const fingerprint='a'.repeat(64),raw='2025年资料/学院/服务证明.docx；文件指纹：'+fingerprint+'；位置：第2页第3段';
 const answer={ledger_id:'ledger-a',year:2025,name:'历史项目',college:'软件学院',sequence:'1',status:'资料待完善',source_file:'原表.xlsx',source_rows:[4],history:{...history,date_facts:[{kind:'source',text:'服务证明记载',evidence:raw}]},missing:[],rows:[],attachments:[],can_read_files:true};
 const c=context(answer,{history_ledger:'ledger-a',history_row:'4'}),html=await historyProjectsPage(c),visible=html.replace(/<details\b[\s\S]*?<\/details>/g,'');
 assert.match(visible,/原材料记载日期/);assert.match(visible,/服务证明\.docx · 第2页第3段/);
 assert.doesNotMatch(visible,/2025年资料\/学院|[a-f0-9]{64}/);
 assert.doesNotMatch(html,/实施人员使用|原件校验依据|2025年资料\/学院|[a-f0-9]{64}/);assert.equal(answer.history.date_facts[0].evidence,raw);
 answer.history={...history};assert.match(await historyProjectsPage(c),/尚无可确认的日期事实/);
});

test('预填期间始终标待复核，详情保留判断依据且不会冒充原件确认日期',async()=>{
 const prefill={kind:'source',start_date:'2025-07-14',end_date:'2025-07-14',text:'按原表单次服务预填 <img src=x onerror=alert(1)>',evidence:'2025年资料/学院/服务证明.png；文件指纹：'+'a'.repeat(64)+'；位置：正文首段'};
 const summary=historyDateSummary({esc},{date_prefill:prefill,confirmed_start:null,confirmed_end:null});
 assert.match(summary,/2025-07-14/);assert.match(summary,/历史预填 · 待学校复核/);
 assert.doesNotMatch(summary,/已确认|已核定|已结项/);
 const answer={ledger_id:'ledger-a',year:2025,name:'历史项目',college:'软件学院',sequence:'1',status:'有冲突待核对',source_file:'原表.xlsx',source_rows:[4],history:{...history,date_prefill:prefill,conflicts:['候选材料归属待核']},missing:['历史预填日期待学校复核'],rows:[],attachments:[],can_read_files:false};
 const html=await historyProjectsPage(context(answer,{history_ledger:'ledger-a',history_row:'4'}));
 assert.match(html,/历史日期预填/);assert.match(html,/&lt;img src=x onerror=alert\(1\)&gt;/);
 assert.match(html,/候选材料归属待核/);assert.match(html,/服务证明.png · 正文首段/);
 assert.doesNotMatch(html,/<img src=x|确认开始日期|确认结束日期/);
 const listing={year:2025,years:[2025],issue:'prefill',date_prefill_count:1,counts:{all:1,missing:1,conflict:1},note:'预填待核',items:[{...answer,row_no:4,materials_count:0}]};
 const c=context(listing,{history_issue:'prefill'}),listHtml=await historyProjectsPage(c);
 assert.match(c.requests[0],/issue=prefill/);assert.match(listHtml,/历史日期（待核）/);assert.ok(listHtml.includes(summary));
});


test('历史分页保留筛选和详情返回位置，切换年度重置页码',async()=>{
 const answer={year:2025,years:[2025,2026],issue:'missing',counts:{all:201,missing:201,conflict:0},note:'',items:[],total:201,page:2,size:200};
 const c=context(answer,{history_year:'2025',history_issue:'missing',history_page:'2'}),html=await historyProjectsPage(c);
 assert.match(c.requests[0],/page=2/);assert.match(html,/共 201 条 · 第 2 \/ 2 页/);
 assert.match(html,/history_page=1/);assert.doesNotMatch(html,/下一页/);
 assert.match(html,/href="#projects\?project_view=history&amp;history_year=2026&amp;history_issue=missing"/);
 const filter={project_view:'history',history_year:'2025',history_issue:'missing',history_page:'2'};
 assert.deepEqual(restoreNavigation(navigationHash('projects',filter),{projects:'培训项目'}).filter,filter);
});


test('历史待核说明提取旧字典中的业务内容，路径指纹不进入页面',async()=>{
 const raw="{'evidence_id': 'DATE-037', 'note': '仅写约30分钟，没有日历日期。', 'source': {'relative_path': '资料/学院/培训方案.docx', 'sha256': '"+'a'.repeat(64)+"', 'location': '正文第11段'}}";
 const answer={ledger_id:'ledger-a',year:2026,name:'历史项目',college:'学院',sequence:'1',status:'资料待完善',source_file:'原表.xlsx',source_rows:[4],history:{...history},missing:[raw],rows:[],attachments:[],can_read_files:false};
 const html=await historyProjectsPage(context(answer,{history_ledger:'ledger-a',history_row:'4'}));
 assert.match(html,/仅写约30分钟，没有日历日期。/);assert.match(html,/培训方案.docx · 正文第11段/);
 assert.doesNotMatch(html,/evidence_id|relative_path|sha256|资料\/学院|[a-f0-9]{64}/);assert.equal(answer.missing[0],raw);
 const item=JSON.parse(JSON.stringify({note:'材料日期待核',source:{relative_path:'资料/材料.pdf',location:'第2页',sha256:'b'.repeat(64)}}));
 answer.missing=[JSON.stringify(item)];const json=await historyProjectsPage(context(answer,{history_ledger:'ledger-a',history_row:'4'}));assert.match(json,/材料日期待核/);assert.match(json,/材料.pdf · 第2页/);assert.doesNotMatch(json,/relative_path|sha256|b{64}/);
});
