import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {HELP_TOPICS,FIELD_HELP} from '../../frontend/help-content.js';
import {inferHelpPage,describeField,helpSearch,fieldError,cleanHelpHints} from '../../frontend/help-system.js';
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
 const f=describeField(input());assert.equal(f.requirement,'当前必填');assert.ok(f.limits.includes('最小值：0'));assert.equal(f.explanation,FIELD_HELP.hours);
 assert.equal(describeField(input({required:false})).requirement,'当前选填');
 assert.equal(describeField(input({readOnly:true})).requirement,'自动带出／只读');
 assert.equal(describeField(input({disabled:true})).requirement,'当前不可填写');
});
test('说明采集不读取用户输入值和附件内容',()=>{
 const i=input();Object.defineProperty(i,'value',{get(){throw Error('不得采集输入值')}});Object.defineProperty(i,'files',{get(){throw Error('不得采集文件内容')}});
 assert.equal(describeField(i).example,'例：8');assert.equal(describeField(input({type:'hidden'})),null);
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
