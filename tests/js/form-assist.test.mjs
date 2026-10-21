import test from 'node:test';
import assert from 'node:assert/strict';
import {fileSignatureError,validateFileSelection,appendPhrase,normalizeDate,dateError,formSnapshot,rememberForm,dirtyForms,allowFormLeave,phraseValidation,PHRASES,actionPhrases} from '../../frontend/form-assist.js';
import {quickDateRange,parseCalendarDates,calendarDateError} from '../../frontend/form-assist.js';

test('统计快捷区间正确处理跨年和闰年，不依赖时区转换',()=>{
 assert.deepEqual(quickDateRange('previous-month',new Date(2026,0,12)),['2025-12-01','2025-12-31']);
 assert.deepEqual(quickDateRange('month',new Date(2024,1,28)),['2024-02-01','2024-02-29']);
 assert.deepEqual(quickDateRange('year',new Date(2026,9,21)),['2026-01-01','2026-12-31']);
 assert.throws(()=>quickDateRange('semester'),/不支持/);
});
test('校历保留非连续日期，批量粘贴去重排序，拒绝无效、越界及冲突',()=>{
 assert.deepEqual(parseCalendarDates(['2026/10/3，2026-10-01','2026-10-03'].join('\n')).dates,['2026-10-01','2026-10-03']);
 assert.match(parseCalendarDates('2026-02-30').error,/无效/);
 assert.match(calendarDateError('2026-10-01','2026-10-01','2026-01-01','2026-12-31'),/同时标为/);
 assert.match(calendarDateError('2027-01-01','','2026-01-01','2026-12-31'),/开始与结束日期之间/);
 assert.equal(calendarDateError(['2026-10-01','2026-10-03'].join('\n'),'2026-10-02','2026-01-01','2026-12-31'),'');
 assert.deepEqual(parseCalendarDates('').dates,[]);
});
test('选中文件的文件头检查发现错扩展名和空文件，完整结构仍交给服务端',async()=>{
 assert.equal(await fileSignatureError([new File([new Uint8Array([255,216,255,224])],'photo.jpg')]),'');
 assert.match(await fileSignatureError([new File([new Uint8Array([255,216,255,224])],'photo.png')]),/扩展名不符/);
 assert.match(await fileSignatureError([new File([],'empty.pdf')]),/损坏/);
 assert.equal(await fileSignatureError([new File(['%PDF-1.7'],'document.pdf')]),'');
 assert.match(await fileSignatureError([{name:'gone.jpg',slice(){throw Error('gone')}}]),/无法读取/);
});

test('选中文件时区分封面和佐证，校验类型大小及已有材料数量',()=>{
 const file=(name,size=100)=>({name,size});
 assert.equal(validateFileSelection([file('a.jpg')],{kind:'cover'}),'');
 assert.match(validateFileSelection([file('a.pdf')],{kind:'cover'}),/PNG、JPG/);
 assert.match(validateFileSelection([file('a.jpg',6*1024*1024)],{kind:'cover'}),/5MB/);
 assert.equal(validateFileSelection([file('a.pdf')],{kind:'proof',existing:19,max:20}),'');
 assert.match(validateFileSelection([file('a.pdf'),file('b.jpg')],{kind:'proof',existing:19,max:20}),/最多.*1.*份/);
 assert.match(validateFileSelection([file('a.pdf',11*1024*1024)],{kind:'proof'}),/超过 10/);
 assert.match(validateFileSelection([file('a.exe')],{kind:'proof'}),/只能是/);
 assert.equal(validateFileSelection([],{kind:'proof',existing:50}),'');
});

test('常用语保留原文与换行，重复选用不追加，超限不截断',()=>{
 assert.equal(appendPhrase('','申请审核').value,'申请审核');
 assert.equal(appendPhrase('原文  ','申请审核').value,'原文  \n申请审核');
 assert.equal(appendPhrase('原文\n','申请审核').value,'原文\n申请审核');
 assert.equal(appendPhrase('原文\n申请审核','申请审核').value,'原文\n申请审核');
 assert.equal(appendPhrase('原文','申请审核',5).value,'原文');
 assert.equal(appendPhrase('😀','好',3).value,'😀\n好');
});
test('审批、退回、撤回使用不同句式，技术动作不自动附审批结论',()=>{
 assert.equal(actionPhrases('return'),'return');assert.equal(actionPhrases('approve'),'approve');
 assert.equal(actionPhrases('withdraw'),'withdraw');assert.equal(actionPhrases('activate'),'');
 assert.ok(PHRASES.return.every(s=>!s.includes('同意通过')));
});
test('待补全句式允许暂存，正式提交必须补齐；草稿也不允许超长',()=>{
 assert.match(phraseValidation('依据【请补充材料】',2000),/补齐/);
 assert.equal(phraseValidation('依据【请补充材料】',2000,{draft:true}),'');
 assert.match(phraseValidation('abcdef',5,{draft:true}),/不能超过/);
 assert.equal(phraseValidation('已核对附件第三页',2000),'');
});
test('日期按日历解析，不把无效日期滚入下个月，不作时区换算',()=>{
 assert.equal(normalizeDate('2024/2/29'),'2024-02-29');
 assert.equal(normalizeDate('2026-2-29'),null);assert.equal(normalizeDate('2026-04-31'),null);
 assert.equal(normalizeDate('2026-13-01'),null);assert.equal(normalizeDate('2026-10-00'),null);
 assert.equal(normalizeDate(' 2026.1.2 '),'2026-01-02');
 assert.equal(normalizeDate(''), '');assert.equal(normalizeDate('01-02-2026'),null);
 assert.equal(normalizeDate('9999-12-31'),'9999-12-31');
 assert.match(dateError('2026-10-19','2026-10-20'),/不能早于/);
 assert.match(dateError('2027-01-01','','2026-12-31'),/不能晚于/);
 assert.equal(dateError('2026-10-20','2026-10-20','2026-10-20'),'');
});
test('防丢检测覆盖正文、选择项和文件；撤销更改或成功保存后不再提醒',()=>{
 const text={name:'reason',type:'textarea',value:''},choice={name:'option',type:'checkbox',checked:false},file={name:'proof',type:'file',files:[]};
 const form={elements:[text,choice,file]},root={querySelectorAll:()=>[form],querySelector:()=>null};
 rememberForm(form);assert.deepEqual(dirtyForms(root),[]);
 text.value='临时内容';assert.equal(dirtyForms(root).length,1);
 let prompts=0;assert.equal(allowFormLeave(root,()=>{prompts++;return false}),false);assert.equal(prompts,1);
 text.value='';assert.equal(allowFormLeave(root,()=>{throw Error('不应提示')}),true);
 choice.checked=true;assert.equal(dirtyForms(root).length,1);rememberForm(form);
 file.files=[{name:'说明.pdf',size:12,lastModified:1}];assert.equal(dirtyForms(root).length,1);
 const submitted=formSnapshot(form);text.value='保存过程中新增的文字';rememberForm(form,submitted);
 assert.equal(dirtyForms(root).length,1,'异步保存期间新编辑的内容仍需保护');
 rememberForm(form);assert.equal(dirtyForms(root).length,0);
});
test('无名称的辅助工作行也受防丢保护，草稿选择器本身不触发误报',()=>{
 const work={type:'text',value:'原工作',matches:()=>true,getAttribute:()=> '工作说明'};
 const picker={type:'select-one',value:'',dataset:{assistControl:'true'},matches:()=>true};
 const form={elements:[work,picker]},root={querySelectorAll:()=>[form]};
 rememberForm(form);picker.value='some-draft';assert.equal(dirtyForms(root).length,0);
 work.value='新工作说明';assert.equal(dirtyForms(root).length,1);
});
