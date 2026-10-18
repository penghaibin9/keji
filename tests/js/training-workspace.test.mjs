import test from 'node:test';
import assert from 'node:assert/strict';
import {trainingModels,filterTrainingRows,trainingState,trainingChange,renderTrainingWorkspace} from '../../frontend/training-workspace.js';
const esc=v=>String(v??'').replace(/[&<>"']/g,x=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));
const context=id=>({me:{user:{id},role:{kind:'teacher'}},esc,icon:()=>'<svg></svg>',orgName:()=> '学院',teacherName:()=> '教师',orgs:[],act:(l,a,id='')=>`<button data-action="${a}" data-id="${esc(id)}">${esc(l)}</button>`});
test('筛选合并关键词学院状态，未知场地不冒充校内基地',()=>{
 const rows=trainingModels('bases',{resources:[{id:'a',kind:'base',name:'甲基地',org_name:'甲学院',data:{onsite:true}},{id:'b',kind:'base',name:'乙基地',org_name:'乙学院',data:{}},{id:'c',kind:'base',name:'丙基地',org_name:'甲学院',data:{onsite:false}}]},context('filter'));
 assert.equal(rows[1].category,'unknown');assert.deepEqual(filterTrainingRows(rows,{q:'基地',org:'甲学院',tab:'internal'},'bases').map(x=>x.id),['a']);assert.equal(filterTrainingRows(rows,{tab:'external'},'bases').length,1);
});
test('切换选中项只改变当前用户当前页面，重筛选后不残留不匹配的详情',()=>{
 const c=context('one'),other=context('two'),w={projects:[{id:'a',state:'FILED',data:{name:'甲项目'}},{id:'b',state:'DRAFT',data:{name:'乙项目'}}]};
 trainingChange('projects',c,'pick','b');assert.equal(trainingState('projects',other).selected,'');
 trainingChange('projects',c,'tab','FILED');const html=renderTrainingWorkspace('projects',w,c);assert.equal(trainingState('projects',c).selected,'a');assert.match(html,/甲项目/);assert.doesNotMatch(html,/乙项目/);
});
test('只读师资不出现详情办理入口，封面与业务字段转义并保留明确零值',()=>{
 const c=context('safe');const html=renderTrainingWorkspace('trainers',{items:[{id:'x',name:'<script>',directions:[],can_view_detail:false}]},c);
 assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/data-action="app-detail"/);assert.match(html,/仅可查看基础信息/);
 const course=renderTrainingWorkspace('courses',{courses:[{code:'c',name:'零学时',cover_url:'javascript:alert(1)'}],course_info:{c:{hours:0}}},c);
 assert.match(course,/0 学时/);assert.doesNotMatch(course,/javascript:/);assert.match(course,/示意图/);
});
