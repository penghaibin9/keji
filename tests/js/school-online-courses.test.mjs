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

test('超星课程详情：字段齐全、空字段不显示、简介转义、可返回',async()=>{
 const c=context([course(0),course(1,{credit:3,hours:48,course_type:'9',description:'',score:null,team_names:'',team_staff_nos:'',jw_course_code:'',major:''})]);await showStaffDetail(c,'J001');
 await onlineHandlers['online-detail']('0',c);
 for(const text of ['尔雅课','克隆','计算机','公共课','J001','甲（J001）、乙（J002）','2025-03-01 08:00:00','2025-06-01 09:30:00','64/32','仅供参考，不计入学分','&lt;b&gt;简介&lt;/b&gt;'])assert.ok(c.html.includes(text),text);
 assert.match(c.html,/data-action="course-detail" data-id="K0\|cx:0"/);assert.match(c.foot,/data-action="staff-detail" data-id="J001"/);assert.match(c.foot,/去超星看课/);
 await onlineHandlers['online-detail']('1',c);
 assert.match(c.html,/<strong>3\.00<\/strong><\/dd>/);assert.match(c.html,/学时<\/dt><dd>48</);assert.match(c.html,/课程类型<\/dt><dd>9/);
 for(const gone of ['课程简介','<dt>教学团队','<dt>对应教务课','<dt>所属专业','score','false','>0<'])assert.ok(!c.html.includes(gone),gone);
 const before=c.html;await onlineHandlers['online-detail']('99',c);assert.equal(c.html,before);
});

test('从超星详情点进教务课程后可以返回超星课程',async()=>{
 const c=context([]);c.api=async()=>({items:[{code:'K0',name:'总库课',credit:1,hours:1,weekly_hours:1,dept:'',extra:{}}]});
 await showCourseDetail(c,'K0','cx:3');assert.match(c.foot,/data-action="online-detail" data-id="3">返回超星课程/);
 await showCourseDetail(c,'K0','J001|2025-2026|staff');assert.match(c.foot,/data-action="credit-detail"[^>]*>返回学年明细/);
 c.api=async()=>({items:[]});await showCourseDetail(c,'K9','cx:1');assert.match(c.foot,/返回超星课程/);
});
