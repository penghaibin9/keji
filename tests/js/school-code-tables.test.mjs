import test from 'node:test';
import assert from 'node:assert/strict';
import {codeLabel, loadCodeTables, showCourseDetail} from '../../frontend/school-data.js';

const esc=x=>String(x??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');

test('缺少学校学历学位和业务码表时提示补充说明，未匹配原代码不外露',async()=>{
 await loadCodeTables(async()=>({tables:{}}));
 for(const [type,code] of [['edu','21'],['degree','401'],['hr_status','01'],['staff_type','11'],['unit','0301'],['nature','1']]){
  const text=codeLabel({esc},type,code);
  assert.doesNotMatch(text,new RegExp(code));assert.match(text,/待学校补充说明/);
 }
 assert.doesNotMatch(codeLabel({esc},'edu','21'),/本科/);
 assert.doesNotMatch(codeLabel({esc},'degree','401'),/学士/);
 assert.equal(codeLabel({esc},'gender','2'),'女');
 assert.equal(codeLabel({esc},'edu','学校原有中文学历'),'学校原有中文学历');
 assert.equal(codeLabel({esc},'edu','学校<原有学历>'),'学校&lt;原有学历&gt;');
 assert.doesNotMatch(codeLabel({esc},'staff_type','INTERNAL_STAFF_11'),/INTERNAL_STAFF_11|待码表/);
});

test('学校码表优先并正确转义，加载失败后不保留旧学校码表',async()=>{
 await loadCodeTables(async()=>({tables:{edu:{'21':{label:'学校专用学历'}},degree:{'401':{label:'学校专用学位'}},gender:{'2':{label:'学校专用性别'}},unit:{'0301':{label:'<学院>'}}}}));
 for(const [type,code,text] of [['edu','21','学校专用学历'],['degree','401','学校专用学位'],['gender','2','学校专用性别'],['manage_dept','0301','&lt;学院&gt;']])assert.equal(codeLabel({esc},type,code),text);
 await loadCodeTables(async()=>{throw new Error('模拟加载失败')});
 assert.match(codeLabel({esc},'edu','21'),/待学校补充说明/);assert.doesNotMatch(codeLabel({esc},'edu','21'),/21|学校专用学历/);
});

test('课程开课单位复用学校单位码表，未导入时只显示中文待补提示',async()=>{
 const context={esc,number:x=>String(x),api:async()=>({items:[{code:'C1',name:'合成课程',credit:1,hours:1,weekly_hours:1,dept:'0301',extra:{}}]}),modal:(_title,html)=>{context.html=html}};
 await loadCodeTables(async()=>({tables:{}}));await showCourseDetail(context,'C1');
 assert.match(context.html,/待学校补充说明/);assert.doesNotMatch(context.html,/0301|待码表/);
 await loadCodeTables(async()=>({tables:{unit:{'0301':{label:'合成学院'}}}}));await showCourseDetail(context,'C1');
 assert.match(context.html,/开课单位<\/dt><dd>合成学院/);assert.doesNotMatch(context.html,/待学校补充说明|待码表/);
});
