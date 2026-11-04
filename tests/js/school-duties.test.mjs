// 用户与权限 › 学校审批职责页签（2026-11-04）：10 个职责逐行显示、缺人标红；添加、移除办理人按最新版本只改这一个职责；
// 没有学校审核身份的人先经账号保存接口加“学校业务审核”兼任身份。
import test from 'node:test';
import assert from 'node:assert/strict';
import {dutyRows,dutiesTabHtml,dutiesAction,accountWithSchoolReview,schoolReviewRole,DUTY_INFO} from '../../frontend/school-duties.js';

const esc=v=>String(v??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const LABELS={dean:'二级学院院长',coordinator:'归口学院复审',vice_president:'分管副校长',secretary:'教学秘书',finance:'财务核验',academic:'成果核验',discipline:'纪检核验',committee:'委员会评审',trainer_hr:'培训师资格认定（组织人事部）',trainer_filing:'外聘培训师备案（教务处）'};

function context(duties){
 const state={duties:structuredClone(duties),posts:[],puts:[],forms:[],toasts:[]};
 const c={esc,orgs:[{id:'school',kind:'school',parent_id:null},{id:'college1',kind:'college',parent_id:'school'}],
  act:(label,action,id)=>`<button data-action="${action}" data-id="${esc(id)}">${esc(label)}</button>`,
  table:(heads,rows)=>'<table>'+rows.map(r=>'<tr><td>'+r.join('</td><td>')+'</td></tr>').join('')+'</table>',
  note:(s)=>'<p>'+esc(s)+'</p>',reasonFields:(v,l)=>'<textarea name="reason">'+esc(v)+'</textarea>',
  formModal:(title,body,save,options)=>state.forms.push({title,body,save,options}),closeModal:()=>{},toast:m=>state.toasts.push(m),render:async()=>{},
  api:async(url,options={})=>{
   if(url==='/social/duties'&&!options.method)return structuredClone(state.duties);
   if(url==='/social/duties'&&options.method==='PUT'){state.puts.push(options.body);if(options.body.expected_version!==state.duties.version)throw Error('职责配置已变化');state.duties={...state.duties,assignments:options.body.assignments,version:state.duties.version+1};return {}}
   if(url==='/roles')return {items:[{id:'role-school',code:'school',kind:'school',active:true,permissions:['assessment.review','users.manage']},{id:'role-school-review',code:'school_review',kind:'school',active:true,permissions:['assessment.review']}]};
   if(url.startsWith('/users/')){state.posts.push({url,...options});return {}}
   throw Error('unexpected '+url)
  }};
 return {c,state};
}
const BASE={version:3,labels:LABELS,school_duties:Object.keys(LABELS).filter(k=>k!=='dean'),assignments:{coordinator:['r1'],dean:['d1','d2'],trainer_hr:['gone']},
 people:[{id:'r1',name:'审核人',org_name:'学校',usable:true},{id:'d1',name:'院长甲',org_name:'学院一',usable:true},{id:'d2',name:'院长乙',org_name:'学院二',usable:true},{id:'gone',name:'停用人',org_name:'学校',usable:false}]};

test('十个职责逐行显示，含二级学院院长；缺人、只有一人、账号不可用都标出来',async()=>{
 const rows=dutyRows(BASE);
 assert.equal(rows.length,10);assert.ok(rows.some(r=>r.code==='dean'));
 for(const r of rows)assert.ok(DUTY_INFO[r.code]?.flows.length,r.code);
 const by=Object.fromEntries(rows.map(r=>[r.code,r]));
 assert.equal(by.coordinator.single,true);assert.equal(by.dean.missing,false);assert.equal(by.trainer_hr.missing,true,'只有停用账号算缺人');assert.equal(by.finance.missing,true);
 const {c}=context(BASE);const html=await dutiesTabHtml(c);
 assert.match(html,/还没有可办理的人/);assert.match(html,/外聘培训师备案停在教务处/);assert.match(html,/停用人 · 学校 · 账号不可用/);
 assert.match(html,/data-action="duty-add" data-id="dean"/);assert.match(html,/data-action="duty-remove" data-id="coordinator\|r1"/);
});

test('添加：有学校审核身份的人直接加入；没有的先经账号保存接口加“学校业务审核”兼任身份，再按最新版本只改这一个职责',async()=>{
 const {c,state}=context(BASE);await dutiesTabHtml(c);
 await dutiesAction('duty-add','trainer_filing',c);
 const form=state.forms.at(-1);assert.match(form.title,/外聘培训师备案/);assert.match(form.body,/学校指定外聘培训师备案（教务处）办理人/,'办理说明预填');
 await assert.rejects(form.save({reason:'加人'}),/请先从搜索结果里选一个人/);
 // 模拟在搜索结果里选了一个没有学校审核身份的人
 const account={name:'教师甲',title:'',org_id:'dept1',role_id:'role-teacher',active:true,is_admin:false,version:4,extra_identities:[{role_id:'role-dept',org_id:'dept1',valid_until:null}]};
 const extras=accountWithSchoolReview(account,schoolReviewRole((await c.api('/roles')).items),'school');
 assert.deepEqual(extras.extra_identities,[{role_id:'role-dept',org_id:'dept1',valid_until:null},{role_id:'role-school-review',org_id:'school',valid_until:null}],'保留原兼任身份，只追加学校业务审核');
 assert.equal(extras.expected_version,4);assert.equal(schoolReviewRole([{id:'x',code:'school_review',kind:'school',active:true,permissions:['assessment.review','roles.manage']}]),null,'带系统管理权限的角色不能当兼任身份');
});

test('移除：按最新版本只去掉这一个人，其他职责原样；移除最后一人时提示会卡住什么',async()=>{
 const {c,state}=context(BASE);await dutiesTabHtml(c);
 await dutiesAction('duty-remove','coordinator|r1',c);
 const form=state.forms.at(-1);assert.match(form.body,/移除后这个职责就没有人了/);assert.match(form.body,/项目、结项、课程、基地走到学校这一级会停住/);
 state.duties.version=5;  // 别人刚保存过：用最新版本号，不覆盖别的职责
 state.duties.assignments={...state.duties.assignments,finance:['r1']};
 await form.save({reason:'调整'});
 const saved=state.puts.at(-1);assert.equal(saved.expected_version,5);assert.deepEqual(saved.assignments.coordinator,[]);assert.deepEqual(saved.assignments.finance,['r1']);assert.deepEqual(saved.assignments.dean,['d1','d2']);
});
