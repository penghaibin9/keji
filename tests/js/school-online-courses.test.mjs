import test from 'node:test';
import assert from 'node:assert/strict';
import {showStaffDetail, showCourseDetail, onlineHandlers, loadCodeTables} from '../../frontend/school-data.js';

const esc=x=>String(x??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const course=(i,extra={})=>({course_code:'CX'+i,course_name:'超星课'+i,term_name:'2025-2',credit:null,hours:null,period_text:'64/32',cover_url:'javascript:alert(1)',
 course_url:'https://mooc1.chaoxing.com/c'+i,group_name:'公共课',chapters:'12',course_type:'1',course_source:'2',archived:'0',
 team_names:'甲,乙',team_staff_nos:'J001,J002',jw_course_code:'K'+i,nature:null,course_owner:'J001',major:'计算机',score:'2.5',
 created_at_source:'2025-03-01T08:00:00',edited_at_source:'2025-06-01 09:30:00',description:'<b>简介</b>',...extra});

function context(online){
 const c={esc,number:(x,d)=>Number(x).toFixed(d),me:{user:{}},note:t=>t,table:()=>'',link:(l,a,id)=>`<a data-action="${a}" data-id="${esc(id)}">${l}</a>`,
  act:(l,a,id)=>`<button data-action="${a}" data-id="${esc(id)}">${l}</button>`,modal:(title,html,foot)=>{c.title=title;c.html=html;c.foot=foot}};
 c.api=async()=>({staff:{staff_no:'J001',name:'测试',problems:[],user_id:'u'},years:[],online_courses:online});
 return c;
}

test('超星课程卡片：标签、缺学分不拿 score 顶替、学时原样、只放前 3 门',async()=>{
 await loadCodeTables(async()=>({tables:{}}));
 const c=context(Array.from({length:8},(_,i)=>course(i)));await showStaffDetail(c,'J001');
 assert.equal((c.html.match(/class="online-card[ "]/g)||[]).length,3);
 assert.match(c.html,/共 8 门/);assert.match(c.html,/尔雅课/);assert.match(c.html,/来源：克隆/);
 assert.match(c.html,/缺学分<\/span> · 64\/32 学时 · 12 章/);assert.doesNotMatch(c.html,/2\.50/);
 assert.match(c.html,/学分只算给建课人/);assert.match(c.html,/data-action="online-all" data-id="1">显示全部/);
 assert.doesNotMatch(c.html,/javascript:|onerror|<img/);
});

test('超星封面只用 chaoxing.com 的图片',async()=>{
 const c=context([course(0,{cover_url:'http://p.ananas.chaoxing.com/a.png'}),course(1,{cover_url:'https://evil.example/chaoxing.com.png'})]);await showStaffDetail(c,'J001');
 assert.match(c.html,/<img src="https:\/\/p\.ananas\.chaoxing\.com\/a\.png"/);assert.equal((c.html.match(/<img/g)||[]).length,1);
});

test('超星课程未知性质不显示原代码徽标，详情保留中文待补说明',async()=>{
 await loadCodeTables(async()=>({tables:{}}));
 const c=context([course(0,{nature:'INTERNAL_NATURE_88'})]);await showStaffDetail(c,'J001');
 assert.doesNotMatch(c.html,/INTERNAL_NATURE_88|待学校补充说明|待码表/);
 await onlineHandlers['online-detail']('0',c);assert.match(c.html,/课程性质<\/dt><dd><span class="muted small">待学校补充说明/);assert.doesNotMatch(c.html,/INTERNAL_NATURE_88|待码表/);
 await loadCodeTables(async()=>({tables:{nature:{INTERNAL_NATURE_88:{label:'学校确认的课程性质'}}}}));await showStaffDetail(c,'J001');assert.match(c.html,/学校确认的课程性质/);assert.doesNotMatch(c.html,/INTERNAL_NATURE_88/);
 await loadCodeTables(async()=>({tables:{}}));
});

test('超星课程详情：字段齐全、空字段不显示、简介转义、可返回',async()=>{
 const c=context([course(0),course(1,{credit:3,hours:48,course_type:'9',description:'',score:null,team_names:'',team_staff_nos:'',jw_course_code:'',major:''})]);await showStaffDetail(c,'J001');
 await onlineHandlers['online-detail']('0',c);
 for(const text of ['尔雅课','克隆','计算机','公共课','J001','甲（J001）、乙（J002）','2025-03-01 08:00:00','2025-06-01 09:30:00','64/32','&lt;b&gt;简介&lt;/b&gt;'])assert.ok(c.html.includes(text),text);
 assert.doesNotMatch(c.html,/实施人员使用|超星参考分值/);assert.match(c.html,/data-action="course-detail" data-id="K0\|cx:0"/);assert.match(c.foot,/data-action="staff-detail" data-id="J001"/);assert.match(c.foot,/去超星看课/);
 await onlineHandlers['online-detail']('1',c);
 assert.match(c.html,/<strong>3\.00<\/strong><\/dd>/);assert.match(c.html,/学时<\/dt><dd>48</);assert.match(c.html,/课程类型<\/dt><dd>待学校补充说明/);
 for(const gone of ['课程简介','<dt>教学团队','<dt>对应教务课','<dt>所属专业','score','>false<','>0<'])assert.ok(!c.html.includes(gone),gone);
 const before=c.html;await onlineHandlers['online-detail']('99',c);assert.equal(c.html,before);
});

test('课程详情弹窗保留全部课程、原封面、完整超星字段和缺学分说明',async()=>{
 const c=context(Array.from({length:32},(_,i)=>course(i,i?{}:{course_name:'机械制图',course_code:'265641882',term_name:'2026-1',credit:null,hours:null,period_text:'',chapters:154,course_type:0,course_source:1,group_name:'智能装备技术学院',team_names:'皮杰',team_staff_nos:'2084',cover_url:'https://p.ananas.chaoxing.com/mechanical.png',created_at_source:'2026-08-05 09:35:53',edited_at_source:'2026-10-06 07:50:20'})));
 await showStaffDetail(c,'J001');await onlineHandlers['online-detail']('0',c);
 assert.equal((c.html.match(/data-course-index=/g)||[]).length,32);
 for(const text of ['cx-course-workspace','cx-course-detail','265641882','2026-2027 学年第一学期','154','自建课','课程来源</dt><dd>自建','智能装备技术学院','使用中','皮杰（2084）','2026-08-05 09:35:53','2026-10-06 07:50:20','超星未填写学分，暂不计入授课学分。'])assert.ok(c.html.includes(text),text);
 assert.match(c.html,/<img src="https:\/\/p\.ananas\.chaoxing\.com\/mechanical\.png"/);
 assert.match(c.html,/data-course-index="0" aria-current="true"/);
 assert.match(c.html,/data-course-index="0" aria-current="true" data-action="[a-z-]+" data-id="0"/,"整张课程卡片都能点击选择，不能只靠小字按钮");
 assert.doesNotMatch(c.html,/超星 score 字段/);
 assert.doesNotMatch(c.html,/实施人员使用|implementation-details|超星参考分值/);
 assert.match(c.foot,/cx-course-footer/);assert.match(c.foot,/返回教师信息/);
});

test('课程切换只更新右侧及底部，保留左侧滚动与焦点所在节点',async()=>{
 const c=context([course(0),course(1,{course_name:'第二门课',credit:0,hours:0,chapters:0,archived:'1',course_url:''})]);await showStaffDetail(c,'J001');
 let renders=0;const original=c.modal;c.modal=(...args)=>{renders++;original(...args)};
 await onlineHandlers['online-detail']('0',c);
 const panel={innerHTML:'',scrollTop:100},footer={innerHTML:''};
 const cards=[0,1].map(i=>({dataset:{courseIndex:String(i)},classList:{toggle:(name,on)=>{cards[i].selected=on}},setAttribute:(name,value)=>{cards[i][name]=value}}));
 const workspace={querySelector:()=>panel,querySelectorAll:()=>cards};
 const before=globalThis.document;
 globalThis.document={getElementById:id=>id==='cx-course-workspace'?workspace:footer};
 try{
  await onlineHandlers['online-detail']('1',c);
  assert.equal(renders,1);assert.equal(panel.scrollTop,0);assert.match(panel.innerHTML,/第二门课/);assert.match(panel.innerHTML,/<strong>0\.00<\/strong>/);assert.match(panel.innerHTML,/学时<\/dt><dd>0</);assert.match(panel.innerHTML,/章节数<\/dt><dd>0</);assert.match(panel.innerHTML,/已归档/);assert.doesNotMatch(panel.innerHTML,/cx-credit-warning/);
  assert.equal(cards[0].selected,false);assert.equal(cards[1]['aria-current'],'true');assert.doesNotMatch(footer.innerHTML,/去超星看课/);
  const saved=panel.innerHTML;for(const invalid of ['','-1','1.5','NaN','99'])await onlineHandlers['online-detail'](invalid,c);assert.equal(panel.innerHTML,saved);
 }finally{if(before===undefined)delete globalThis.document;else globalThis.document=before}
});

test('从超星详情点进教务课程后可以返回超星课程',async()=>{
 const c=context([]);c.api=async()=>({items:[{code:'K0',name:'总库课',credit:1,hours:1,weekly_hours:1,dept:'',extra:{}}]});
 await showCourseDetail(c,'K0','cx:3');assert.match(c.foot,/data-action="online-detail" data-id="3">返回超星课程/);
 await showCourseDetail(c,'K0','J001|2025-2026|staff');assert.match(c.foot,/data-action="credit-detail"[^>]*>返回学年明细/);
 c.api=async()=>({items:[]});await showCourseDetail(c,'K9','cx:1');assert.match(c.foot,/返回超星课程/);
});
