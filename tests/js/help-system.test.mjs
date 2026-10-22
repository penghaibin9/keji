import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {HELP_TOPICS,FIELD_HELP,FIELD_LABEL_HELP,HELP_FAQS} from '../../frontend/help-content.js';
import {inferHelpPage,describeField,helpSearch,fieldError,cleanHelpHints,fieldSentences,requirementText} from '../../frontend/help-system.js';
test('全部当前页面必须有独立帮助主题，新增页面会报遗漏',()=>{
 const app=fs.readFileSync(new URL('../../frontend/app.js',import.meta.url),'utf8');
 const titles=app.match(/const titles=\{([^\n]+)\};/)[1];
 const pages=[...titles.matchAll(/(?:^|,)(\w+):/g)].map(x=>x[1]);
 assert.equal(new Set(HELP_TOPICS.map(t=>t.id)).size,HELP_TOPICS.length);
 assert.deepEqual(pages.filter(id=>!HELP_TOPICS.find(t=>t.id===id)),[]);
 for(const t of HELP_TOPICS){assert.ok(t.steps.length>=3);assert.ok(t.done);assert.ok(t.purpose)}
});
test('跨页面办理窗口按事项选择教程，不按原待办页面误配',()=>{
 assert.equal(inferHelpPage('todos','申请培训基地'),'apply_base');
 assert.equal(inferHelpPage('todos','积分认定'),'recognition');
 assert.equal(inferHelpPage('projects','项目结项'),'projects');
 assert.equal(inferHelpPage('home','教师资质审核'),'qualifications');
 assert.equal(inferHelpPage('rules','新建考核周期'),'rules');
 assert.equal(inferHelpPage('rules','新建组织考核规则'),'rules');
});
function input(extra={}){return {name:'hours',type:'number',tagName:'INPUT',labels:[{textContent:'培训学时 *'}],dataset:{},required:true,disabled:false,readOnly:false,placeholder:'例：8',getAttribute:key=>({min:'0',step:'0.5'}[key]??null),closest:()=>({querySelectorAll:()=>[]}),...extra}}
test('字段说明按当前条件读必填与限制，显式零不丢失',()=>{
 const f=describeField(input());assert.equal(f.requirement,'当前必填');assert.deepEqual(f.limits,['不能填负数','可以填 0.5 学时这样的半学时']);assert.equal(f.explanation,FIELD_HELP.hours);
 assert.equal(describeField(input({required:false})).requirement,'当前选填');
 assert.equal(describeField(input({readOnly:true})).requirement,'自动带出／只读');
 assert.equal(describeField(input({disabled:true})).requirement,'当前不可填写');
});
test('说明采集不读取用户输入值和附件内容',()=>{
 const i=input();Object.defineProperty(i,'value',{get(){throw Error('不得采集输入值')}});Object.defineProperty(i,'files',{get(){throw Error('不得采集文件内容')}});
 assert.equal(describeField(i).example,'8');assert.equal(describeField(input({type:'hidden'})),null);
});
test('旧菜单名称可找到教程，搜索不涉及业务授权或跳转',()=>{
 assert.ok(helpSearch('我的课程',{credits:['我的课程']}).some(t=>t.id==='credits'));
 assert.ok(helpSearch('材料上传失败').some(t=>t.id==='help'));
 assert.equal(helpSearch('不可能出现的词汇').length,0);
});
test('原生浏览器校验使用中文说明，零下限完整显示',()=>{
 assert.equal(fieldError({validity:{rangeUnderflow:true},min:'0'}),'不能小于 0。');
 assert.equal(fieldError({validity:{typeMismatch:true},validationMessage:'Please enter a number.'}),'填写格式不符合要求，请核对本项说明。');
});
test('字段手册保留业务条件，排除实时字数和工具条提示',()=>{
 assert.deepEqual(cleanHelpHints(['已填 12 / 最多 2000 字','选择校外基地时必填。','常用语 · 点击填入，可继续修改']),['选择校外基地时必填。']);
});

test('帮助标题与侧栏、页面标题一致，旧名称仍可搜到',()=>{
 const app=fs.readFileSync(new URL('../../frontend/app.js',import.meta.url),'utf8');
 const titles=Object.fromEntries([...app.match(/const titles=\{([^\n]+)\};/)[1].matchAll(/(?:^|,)(\w+):'([^']+)'/g)].map(x=>[x[1],x[2]]));
 for(const t of HELP_TOPICS)if(titles[t.id])assert.ok(t.title===titles[t.id]||t.title.startsWith(titles[t.id]+'（'),t.id+'：'+t.title);
 for(const [old,id] of [['培训项目与结项','projects'],['培训课程库','courses'],['培训基地清单','bases'],['培训课程申报','apply_course'],['审批职责','policy'],['设置负责人','permissions'],['超星课程认领','credits']])assert.ok(helpSearch(old).some(t=>t.id===id),old);
 assert.equal(HELP_TOPICS[0].id,'quickstart');
 for(const q of ['找不到按钮','看进度','积分为什么','附件传不上去'])assert.ok(HELP_FAQS.some(([a])=>a.includes(q)),q);
});
function control(extra={}){const attrs=extra.attrs||{};return {type:'text',tagName:'INPUT',labels:[],dataset:{},required:false,disabled:false,readOnly:false,placeholder:'',name:'',id:'',getAttribute:k=>attrs[k]??null,closest:()=>null,parentElement:null,...extra}}
test('候选人和组织名单只说明怎么选，不把人名当成填写项',()=>{
 const container={getAttribute:k=>k==='aria-label'?'候选老师（可多选）':null,querySelectorAll:()=>[]};
 const person=control({type:'checkbox',labels:[{textContent:'测试教师一 J001'}],closest:sel=>sel==='#duty-options'?{}:null,form:{querySelectorAll:()=>[]}});
 const duty=describeField(person);assert.equal(duty.key,'duty_people');assert.equal(duty.label,'选择办理人（可多选）');assert.deepEqual(duty.options,[]);assert.match(duty.explanation,/灰色/);assert.match(duty.explanation,/回避/);
 const scope=control({type:'checkbox',name:'org_ids',labels:[{textContent:'某学院'}],closest:sel=>sel.includes('role=group')?container:null,form:{querySelectorAll:()=>[]}});
 const org=describeField(scope);assert.equal(org.key,'org_ids');assert.doesNotMatch(org.label,/某学院/);assert.deepEqual(org.options,[]);
});
test('字段说明只保留一条最具体的说明，限制写成人话',()=>{
 const wrap={querySelectorAll:()=>[{textContent:'填写课程材料上的编号；补正时保留原编号。'}],querySelector:()=>null};
 const code=describeField(control({name:'code',labels:[{textContent:'课程编号 *'}],required:true,placeholder:'例：SOC-2026-001',closest:sel=>sel.includes('form-field')?wrap:null}));
 assert.equal(code.explanation,FIELD_LABEL_HELP['课程编号']);assert.deepEqual(code.hints,[]);
 const text=fieldSentences(code).join('');assert.doesNotMatch(text,/。；|。。/);assert.equal(text.split('SOC-2026-001').length,2);
 for(const label of ['姓名','组织名称','组织层级','通知标题'])assert.ok(FIELD_LABEL_HELP[label]&&!/方案、证书|下载模板|职称/.test(FIELD_LABEL_HELP[label]),label);
 const upload=describeField(control({type:'file',name:'file',multiple:true,dataset:{uploadMax:'20'},labels:[{textContent:'证书材料'}],attrs:{accept:'.pdf,.png,.jpg,.jpeg'},closest:sel=>sel.includes('form-field')?{querySelectorAll:()=>[{textContent:'单个最大 10 兆字节。'}],querySelector:()=>null}:null}));
 assert.ok(upload.limits.includes('支持 PDF、PNG、JPG，单个不超过 10MB'));assert.ok(upload.limits.includes('最多 20 份（含已上传的）'));
 assert.equal(requirementText({label:'依据说明（选填）',requirement:'当前选填'}),'');
});
