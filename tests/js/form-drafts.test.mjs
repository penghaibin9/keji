import test from 'node:test';
import assert from 'node:assert/strict';
import {draftPayload,draftOwnerKey,restorableDraft,draftSavedSnapshot,restoreDraftValues} from '../../frontend/form-drafts.js';
import {rememberForm,dirtyForms} from '../../frontend/form-assist.js';

test('草稿保留未完成文字和空值，不保存密码、隐藏身份或文件内容',()=>{
 const form={elements:[
  {name:'name',type:'text',value:'  未填完  '},{name:'income',type:'number',value:''},
  {name:'password',type:'password',value:'secret'},{name:'owner_id',type:'hidden',value:'other'},
  {name:'code',type:'text',value:'immutable',readOnly:true},
  {name:'one_skill',type:'checkbox',checked:false},{name:'mode',type:'radio',value:'a',checked:false},
  {name:'mode',type:'radio',value:'b',checked:true},{name:'proof_files',type:'file',files:[{name:'方案.pdf',content:'not stored'}]},
  {type:'checkbox',dataset:{longTermControl:'true'},checked:true}
 ],querySelectorAll:()=>[]};
 const data=draftPayload(form);
 assert.deepEqual(data.values,{name:'  未填完  ',income:'',one_skill:false,mode:'b',_long_term:true});
 assert.deepEqual(data.files,{proof_files:['方案.pdf']});assert.deepEqual(data.auxiliary,[]);
});
test('暂存仅保存文字，选中文件尚未上传时仍保留离开保护',()=>{
 const form={elements:[{name:'name',type:'text',value:'已暂存'},{name:'file',type:'file',files:[{name:'a.pdf',size:10,lastModified:1}]}]};
 rememberForm(form,draftSavedSnapshot(form));
 assert.equal(dirtyForms({querySelectorAll:()=>[form]}).length,1);
 form.elements[1].files=[];assert.equal(dirtyForms({querySelectorAll:()=>[form]}).length,0);
});
test('业务版本改变不能直接恢复；身份键区分用户角色与组织',()=>{
 assert.equal(restorableDraft({source_version:4},4),true);assert.equal(restorableDraft({source_version:3},4),false);
 assert.equal(restorableDraft({source_version:null},null),true);
 assert.notEqual(draftOwnerKey({user_id:'u',role_id:'r1',org_id:'o'}),draftOwnerKey({user_id:'u',role_id:'r2',org_id:'o'}));
});
test('恢复不覆盖只读来源，不保留当前选错的文件，失效选项须重选',()=>{
 const make=(name,value,extra={})=>({name,value,type:'text',dispatchEvent(){},...extra});
 const name=make('name','当前'),code=make('code','原编号',{readOnly:true});
 const select=make('period_id','now',{tagName:'SELECT',options:[{value:'now'}],selectedIndex:0,labels:[{textContent:'适用周期 *'}]});
 const file=make('file','已选文件',{type:'file'});
 const form={elements:[name,code,select,file],querySelector:()=>null};
 const warnings=restoreDraftValues(form,{values:{name:'暂存名称',code:'不能改',period_id:'expired'},auxiliary:[]});
 assert.equal(name.value,'暂存名称');assert.equal(code.value,'原编号');assert.equal(file.value,'');
 assert.equal(select.selectedIndex,-1);assert.match(warnings[0],/重新检索确认/);
});
test('从长期有效切回有到期日时，恢复日期不被切换事件清空',()=>{
 const expires={name:'expires',type:'text',value:'',disabled:true,dispatchEvent(){}};
 const flag={checked:true,dispatchEvent(){expires.disabled=this.checked;expires.value=''}};
 const form={elements:[expires],querySelector:s=>s==='[data-long-term-control]'?flag:null};
 restoreDraftValues(form,{values:{expires:'2030-10-21',_long_term:false},auxiliary:[]});
 assert.equal(flag.checked,false);assert.equal(expires.disabled,false);assert.equal(expires.value,'2030-10-21');
});
