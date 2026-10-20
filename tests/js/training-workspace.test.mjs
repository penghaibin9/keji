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
 assert.match(course,/0 学时/);assert.doesNotMatch(course,/javascript:/);assert.match(course,/暂无封面/);assert.doesNotMatch(course,/示意图/);
});

test('课程整卡使用原生按钮且选中状态关联右侧详情，资源入口保持独立',()=>{
 const c=context('card-select'),w={courses:[{code:'A',name:'甲课程'},{code:'B',name:'乙<课程>'}]};
 let html=renderTrainingWorkspace('courses',w,c);
 assert.match(html,/<button type="button" class="btn text tw-card-select" data-action="training-pick" data-id="A" aria-pressed="true" aria-controls="training-detail">甲课程<\/button>/);
 assert.match(html,/data-id="B" aria-pressed="false"/);
 trainingChange('courses',c,'pick','B');html=renderTrainingWorkspace('courses',w,c);
 assert.match(html,/data-id="B" aria-pressed="true" aria-controls="training-detail">乙&lt;课程&gt;/);
 assert.match(html,/<aside id="training-detail"[\s\S]*?<h3>乙&lt;课程&gt;<\/h3>/);
 assert.match(html,/data-action="social-course-resources" data-id="B"/);
});

test('培训数据整行选择更新右侧记录，师资共用行选择且不扩大详情权限',()=>{
 const c=context('row-select'),w={items:[{id:'r1',project:'甲项目',course:'甲课程',event_date:'2026-10-01',hours:0},{id:'r2',project:'乙项目',course:'乙课程',event_date:'2026-10-02',hours:8}]};
 let html=renderTrainingWorkspace('records',w,c);
 assert.match(html,/class="btn text tw-row-select" data-action="training-pick" data-id="r1" aria-pressed="true" aria-controls="training-detail"/);
 trainingChange('records',c,'pick','r2');html=renderTrainingWorkspace('records',w,c);
 assert.match(html,/data-id="r1" aria-pressed="false"/);assert.match(html,/data-id="r2" aria-pressed="true"/);
 assert.match(html,/<aside id="training-detail"[\s\S]*?<h3>乙项目<\/h3>[\s\S]*?乙课程[\s\S]*?2026-10-02/);
 const trainer=renderTrainingWorkspace('trainers',{items:[{id:'t',name:'只读师资',directions:[],can_view_detail:false}]},c);
 assert.match(trainer,/class="btn text tw-row-select"/);assert.doesNotMatch(trainer,/data-action="app-detail"/);
});
test('待审批不含草稿和退回，结项后显示实际有效人次与到账收入，已结项四步均完成',()=>{
 const school={...context('school-a'),me:{user:{id:'school-a'},role:{kind:'school'}},can:()=>true};
 const w={projects:[{id:'d',state:'DRAFT',data:{name:'草稿项目'}},{id:'r',state:'RETURNED',data:{name:'退回项目'}},{id:'s',state:'SUBMITTED',data:{name:'待备案项目'}},
  {id:'z',state:'CLOSED',version:3,owner_id:'t',data:{name:'已结项目',expected_participants:10,expected_income:500,total_hours:16,cover_id:'abcdefgh-1234'},closeout:{actual_income:'800'},metrics:{effective:30,actual_income:'800',courses:2,materials:4}}]};
 trainingChange('projects',school,'tab','pending');let html=renderTrainingWorkspace('projects',w,school);
 assert.match(html,/待备案项目/);assert.doesNotMatch(html,/草稿项目|退回项目/);assert.match(html,/办理备案/);
 trainingChange('projects',school,'tab','CLOSED');html=renderTrainingWorkspace('projects',w,school);
 assert.match(html,/有效人次<strong>30 人次/);assert.match(html,/到账收入<strong>800 元/);assert.match(html,/课程<strong>2 门/);assert.doesNotMatch(html,/预计人次/);
 assert.equal((html.match(/<li class="done">/g)||[]).length,4);assert.match(html,/项目材料 · 4 份/);
 assert.match(html,/src="\/api\/social\/images\/abcdefgh-1234"/);assert.match(html,/更换封面/);
 const teacher=context('other-teacher');trainingChange('projects',teacher,'tab','CLOSED');assert.doesNotMatch(renderTrainingWorkspace('projects',w,teacher),/更换封面|上传封面/);
});
test('基地显示用途、级别、共建单位和场地照片，学院可维护照片',()=>{
 const college={...context('college-a'),me:{user:{id:'college-a'},role:{kind:'college'}},can:()=>true};
 const html=renderTrainingWorkspace('bases',{resources:[{id:'b',kind:'base',name:'校外基地',version:2,org_name:'甲学院',data:{onsite:false,partner:'共建企业',usages:['ideology'],level:'city',photo_ids:['photo-0001-a','photo-0002-b']}}]},college);
 assert.match(html,/思政实践教学基地/);assert.match(html,/市级/);assert.match(html,/共建企业/);assert.match(html,/场地照片 · 2/);
 assert.match(html,/添加场地照片/);assert.match(html,/training-image-remove" data-id="resource\|b\|photo\|photo-0001-a\|2"/);
});
test('课程、基地、师资详情按规划展示完整字段，外聘培训师不显示授课课程',()=>{
 const c=context('fields');
 const course=renderTrainingWorkspace('courses',{courses:[{code:'C1',name:'茶艺课',project_code:'P1'}],projects:[{id:'p',org_id:'o',data:{code:'P1',name:'茶艺项目'}}],course_info:{C1:{hours:6,teaching_mode:'practice',ideology:'course_ideology',audience:'社区居民',package:true,one_skill:true,target_groups:'退役军人',intro:'课程简介文字',teacher_name:'王老师'}}},c);
 for(const t of ['面向对象','社区居民','课程思政','培训包、“一人一技”','重点群体与行动对接','退役军人','课程简介文字','课程编号','C1'])assert.ok(course.includes(t),t);
 const base=renderTrainingWorkspace('bases',{resources:[{id:'b',kind:'base',name:'基地',org_name:'学院',data:{onsite:false,partner:'共建',manager_name:'王联系人',established_on:'2026-02-01',recognized_on:'2026-03-05',effective_on:'2026-03-10',usages:['practice'],level:'city'}}]},c);
 for(const t of ['基地负责人','王联系人','设立日期','2026-02-01','认定日期','2026-03-05','审批生效日期','2026-03-10'])assert.ok(base.includes(t),t);
 const trainers=renderTrainingWorkspace('trainers',{items:[{id:'t1',name:'李老师',source:'internal',directions:['社区公益培训'],specialty:'茶艺',courses:['茶艺实操课'],can_view_detail:true},{id:'t2',name:'外聘',source:'external',unit:'机构',directions:[],specialty:'家政'}]},c);
 for(const t of ['专业特长','茶艺','培训业务类别','授课课程','茶艺实操课'])assert.ok(trainers.includes(t),t);
 const external=renderTrainingWorkspace('trainers',{items:[{id:'t2',name:'外聘',source:'external',unit:'机构',directions:[],specialty:'家政'}]},context('fields2'));
 assert.match(external,/外聘培训师暂无关联课程/);
});


test('培训项目的筛选与选中项按地址恢复，清空不残留旧关键词',async()=>{
 const {navigationHash,restoreNavigation}=await import('../../frontend/scope.js');
 const c=context('project-route');c.filter={project_view:'business',history_year:'2025'};
 c.setProjectViewState=s=>{c.filter={...c.filter,q:s.q,org_id:s.org,project_status:s.tab,project_pick:s.selected}};
 trainingChange('projects',c,'filter',{q:'项目甲',org:'college-a'});trainingChange('projects',c,'tab','FILED');trainingChange('projects',c,'pick','project-a');
 const fresh=context('project-route-reloaded');fresh.filter=restoreNavigation(navigationHash('projects',c.filter),{projects:'项目'}).filter;fresh.setProjectViewState=s=>{fresh.filter={...fresh.filter,q:s.q,org_id:s.org,project_status:s.tab,project_pick:s.selected}};
 assert.deepEqual(trainingState('projects',fresh),{q:'项目甲',org:'college-a',tab:'FILED',selected:'project-a',package:false,oneSkill:false});
 trainingChange('projects',fresh,'reset');assert.equal(trainingState('projects',fresh).q,'');assert.equal(fresh.filter.history_year,'2025');
});
