import test from 'node:test';
import assert from 'node:assert/strict';
import {showStaffDetail, onlineHandlers, loadCodeTables} from '../../frontend/school-data.js';

const esc=x=>String(x??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const course=(i,extra={})=>({course_code:'CX'+i,course_name:'超星课'+i,term_name:'2025-2',credit:null,hours:32,cover_url:'javascript:alert(1)',
 course_url:'https://mooc1.chaoxing.com/c'+i,group_name:'公共课',chapters:'12',course_type:'1',course_source:'2',archived:'0',
 team_names:'甲,乙',team_staff_nos:'J001,J002',jw_course_code:'K'+i,nature:null,course_owner:'J001',major:'计算机',score:'2.5',
 created_at_source:'2025-03-01T08:00:00',edited_at_source:'2025-06-01 09:30:00',description:'<b>简介</b>',...extra});

function context(online){
 const c={esc,number:(x,d)=>Number(x).toFixed(d),me:{user:{}},note:t=>t,table:()=>'',link:(l,a,id)=>`<a data-action="${a}" data-id="${esc(id)}">${l}</a>`,
  act:(l,a,id)=>`<button data-action="${a}" data-id="${esc(id)}">${l}</button>`,modal:(title,html,foot)=>{c.title=title;c.html=html;c.foot=foot}};
 c.api=async()=>({staff:{staff_no:'J001',name:'测试',problems:[],user_id:'u'},years:[],online_courses:online});
 return c;
}

test('超星课程卡片显示类型、来源、学分来源，并只放前 6 门',async()=>{
 await loadCodeTables(async()=>({tables:{}}));
 const c=context(Array.from({length:8},(_,i)=>course(i)));await showStaffDetail(c,'J001');
 assert.equal((c.html.match(/class="online-card[ "]/g)||[]).length,6);
 assert.match(c.html,/尔雅课/);assert.match(c.html,/来源：克隆/);assert.match(c.html,/2\.50<\/b> 学分<span[^>]*>（超星课程学分）/);
 assert.match(c.html,/学分只算给建课人/);assert.match(c.html,/data-action="online-all" data-id="1">显示全部/);
 assert.doesNotMatch(c.html,/javascript:/);
});

test('超星课程详情列出全部字段并转义简介，可返回教师信息',async()=>{
 const c=context([course(0),course(1,{credit:3,course_type:'9',description:''})]);await showStaffDetail(c,'J001');
 await onlineHandlers['online-detail']('0',c);
 for(const text of ['尔雅课','克隆','计算机','公共课','J001','甲,乙 / J001,J002','2025-03-01 08:00:00','2025-06-01 09:30:00','取自超星“课程学分”','&lt;b&gt;简介&lt;/b&gt;'])assert.ok(c.html.includes(text),text);
 assert.match(c.html,/data-action="course-detail" data-id="K0"/);assert.match(c.foot,/data-action="staff-detail" data-id="J001"/);assert.match(c.foot,/去超星看课/);
 await onlineHandlers['online-detail']('1',c);
 assert.match(c.html,/<strong>3\.00<\/strong><\/dd>/);assert.match(c.html,/课程类型<\/dt><dd>9/);assert.doesNotMatch(c.html,/课程简介/);
 const before=c.html;await onlineHandlers['online-detail']('99',c);assert.equal(c.html,before);
});
