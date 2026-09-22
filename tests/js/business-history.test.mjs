import test from 'node:test';
import assert from 'node:assert/strict';
import {renderBusinessHistory} from '../../frontend/business-history.js';

test('qualification versions show Chinese business fields and escaped changes, not internal keys',()=>{
 const rows=[{version:2,reason:'补充材料',data:{id:'hidden-id',teacher_id:'hidden-teacher',name:'新证书<script>',state:'APPROVED',expires:'2028-01-01'},attachment_ids:['file2']},{version:1,reason:'新建',data:{name:'旧证书',state:'DRAFT',expires:null},attachment_ids:['file1']}];
 const html=renderBusinessHistory('qualification',rows,{labels:{DRAFT:'草稿',APPROVED:'审核通过'},attachmentButton:(id)=>`下载 ${id}`});
 for(const text of ['证书名称','留存时状态','审核通过','草稿','长期有效','新证书&lt;script&gt;','材料已变更','下载 file2'])assert.ok(html.includes(text),text);
 for(const text of ['teacher_id','hidden-id','hidden-teacher','APPROVED','<script>','data-json'])assert.ok(!html.includes(text),text);
 assert.ok(html.indexOf('第 1 版')<html.indexOf('第 2 版'));
 assert.equal(rows[0].version,2,'rendering must not mutate API data');
});
test('training record versions include values, units, and before/after adjustment',()=>{
 const html=renderBusinessHistory('record',[{version:1,data:{course:'授课课程',hours:'0',income:'0',state:'VALID',participants:0,external_key:'YS-001',batch_id:'internal'}},{version:3,data:{course:'授课课程',hours:'3.5',income:'2200',state:'VALID',participants:27,external_key:'YS-001'}}],{labels:{VALID:'有效记录'}});
 for(const text of ['授课学时','0 学时','3.5 学时','2,200 元','27 人次','YS-001','有效记录','本次变化'])assert.ok(html.includes(text),text);
 for(const text of ['batch_id','VALID','internal','data-json'])assert.ok(!html.includes(text),text);
});
test('unknown fields and unknown workflow codes do not leak into version content',()=>{
 const html=renderBusinessHistory('record',[{version:1,data:{debug_field:'SECRET',state:'FUTURE_INTERNAL'}}]);
 assert.ok(html.includes('状态待核实'));
 assert.ok(!html.includes('SECRET'));assert.ok(!html.includes('FUTURE_INTERNAL'));
 assert.ok(renderBusinessHistory('record',[]).includes('暂无历史版本'));
});
