import test from 'node:test';
import assert from 'node:assert/strict';
import {materialUploadForm,uploadSequential,uploadEntries} from '../../frontend/approval-flow.js';

const file=name=>new File(['synthetic attachment'],name,{type:'image/png'});
function uploadForm({kind='social_resource',existing=0,fail=new Set()}={}){
 const state={version:4,attachments:Array.from({length:existing},(_,i)=>({name:'旧材料'+i})),posts:[],closed:0,returned:0,progress:{innerHTML:''}};
 const files=[file('材料1.png'),file('材料2.png'),file('材料3.png')];
 const c={esc:s=>String(s).replaceAll('<','&lt;'),field:(name,label,type,value,opts)=>`<input name="${name}" type="${type}" ${opts.multiple?'multiple':''}>`,
  formModal:(title,body,save,options)=>{Object.assign(state,{body,save,options})},closeModal:()=>state.closed++,toast:message=>state.message=message,
  api:async(url,{body})=>{const name=body.get('file').name,version=Number(body.get('expected_version'));state.posts.push({name,version,url});assert.equal(version,state.version);if(fail.has(name))throw Error('合成上传失败');state.attachments.push({name});if(!['assessment','org_assessment','sync_task'].includes(kind))state.version++}
 };
 const latest=async()=>({version:state.version,attachments:state.attachments});
 materialUploadForm(c,{kind,id:'synthetic',title:'上传材料',latest,after:async()=>state.returned++});
 const form={querySelector:selector=>selector==='#f-file'?{files}:state.progress};
 return {state,files,save:()=>state.save({reason:'合成测试'},form)};
}

test('材料表单一次选择三张，逐份上传并带正确版本，完成后返回原详情',async()=>{
 for(const kind of ['social_resource','qualification','dispute','assessment','org_assessment','sync_task']){
  const {state,save}=uploadForm({kind});assert.match(state.body,/type="file" multiple/);
  await save();assert.equal(state.posts.length,3);assert.deepEqual(state.posts.map(p=>p.version),['assessment','org_assessment','sync_task'].includes(kind)?[4,4,4]:[4,5,6]);
  assert.equal(state.closed,1);assert.equal(state.returned,1);assert.match(state.message,/已上传 3 份/);assert.equal((state.progress.innerHTML.match(/已上传/g)||[]).length,3);
 }
});

test('部分失败保留表单及成功结果，再次上传只补失败图片',async()=>{
 const fail=new Set(['材料2.png']),{state,save}=uploadForm({fail});
 await assert.rejects(save(),/已上传 2 份，另有 1 份未完成/);assert.equal(state.closed,0);assert.equal(state.returned,0);assert.match(state.progress.innerHTML,/上传失败/);
 fail.clear();await save();assert.deepEqual(state.posts.map(p=>p.name),['材料1.png','材料2.png','材料3.png','材料2.png']);assert.equal(state.attachments.length,3);assert.equal(state.closed,1);
});

test('部分失败后移除错误文件并添加新图，已上传图片仍不重复上传',async()=>{
 const fail=new Set(['材料2.png']),{state,files,save}=uploadForm({fail});
 await assert.rejects(save(),/另有 1 份未完成/);files.splice(1,1);files.push(file('补充.png'));
 await save();assert.deepEqual(state.posts.map(p=>p.name),['材料1.png','材料2.png','材料3.png','补充.png']);assert.equal(state.attachments.length,3);
});

test('材料整体校验不漏掉第二张，资质保留20份上限，校验失败不上传',async()=>{
 const a=uploadForm();a.files[1]={name:'第二张.txt',size:2};await assert.rejects(a.save(),/第二张.txt/);assert.equal(a.state.posts.length,0);
 const b=uploadForm({kind:'qualification',existing:18});await assert.rejects(b.save(),/最多 20 份附件/);assert.equal(b.state.posts.length,0);
 const empty=uploadForm();empty.files.length=0;await assert.rejects(empty.save(),/请选择要上传的材料/);assert.equal(empty.state.posts.length,0);
});

test('考核佐证的上传响应丢失时仍读取最新附件核对，不改变业务版本',async()=>{
 let uploads=0;const f=file('佐证.png'),entries=uploadEntries([f]);
 const hash=await crypto.subtle.digest('SHA-256',await f.arrayBuffer()),sha=[...new Uint8Array(hash)].map(x=>x.toString(16).padStart(2,'0')).join('');
 const result=await uploadSequential({api:async()=>{uploads++;throw Error('响应丢失')},kind:'assessment',id:'a',version:8,entries,reason:'合成测试',latest:async()=>({version:8,attachments:[{name:f.name,sha256:sha}]})});
 assert.equal(uploads,1);assert.equal(result.failed.length,0);assert.equal(result.version,8);
});
