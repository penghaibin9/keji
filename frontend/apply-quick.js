// 2026-11-09 按设计稿：老师“新申报”用普通大小的弹窗、一页填完、点选为主（不再全屏）。
// 只填审批要用的内容；受众、课时、教学方式等上报信息在项目运行里补，结项前补齐（后端 report_pending 已支持）。
// 补正、修改仍用原来的完整表单；后端的必填、校验、审批规则都没有改。
import {checkUploadFiles,uploadEntries,uploadSequential} from './approval-flow.js?v=20261110-doc2';

const CATEGORY=[['community','社区公益培训'],['subsidy','补贴性培训'],['enterprise','企业定制培训'],['rural','乡村帮扶培训'],['other','其他非学历培训']];
const OUTCOMES=['结业证书','职业技能等级证书','满意度 95% 以上','就业或增收'];
const GROUPS=['退役军人','农村劳动力','失业人员','残疾人','老年人','其他'];
const VENUES=[['base','校内培训基地'],['campus','其他校内场所'],['offsite','校外（一事一议）']];
const LEVELS=[['school','校级'],['city','市级'],['province','省级']];
const SCENES=[['ordinary','普通授课'],['full_day','全天集中'],['dispatched','外派送教']];
const MODES=[['module','按模块（学时）核算'],['person_day','按人天核算']];
const CLASS_TYPES=[['technical','技能培训班'],['lecture','讲座']];
const TEACHING=[['lecture','讲授'],['practice','实训实操'],['case','案例研讨'],['onsite','现场教学'],['online','线上自学']];
const IDEOLOGY=[['course_ideology','课程思政'],['ideology_course','思政课程'],['none','无']];
const USAGES=[['practice','实践教学'],['ideology','思政实践教学']];
const DIRECTIONS=[['subsidy','补贴性培训'],['enterprise','企业定制培训'],['community','社区公益培训'],['rural','乡村帮扶培训'],['other','其他非学历培训'],['one_skill','“一人一技”专项']];

const today=()=>{const d=new Date();return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0')};
const autoCode=prefix=>prefix+'-'+today().replace(/-/g,'')+'-'+Math.random().toString(36).slice(2,6).toUpperCase();
function chips(c,name,options,{multi=false,checked=[],label='',required=true,hint=''}={}){
 const e=c.esc;
 return `<fieldset class="form-field full qa-field"><legend>${e(label)}${required?' <b>*</b>':' <span class="qa-opt">选填</span>'}</legend><div class="choice-row">${options.map(([v,l])=>`<label class="choice"><input type="${multi?'checkbox':'radio'}" name="${multi?name+'__'+e(v):name}" value="${e(v)}"${checked.includes(v)?' checked':''}><span>${e(l)}</span></label>`).join('')}</div>${hint?`<p class="hint">${e(hint)}</p>`:''}</fieldset>`;
}
const picked=(form,name,options)=>options.map(([v])=>v).filter(v=>form.querySelector(`[name="${name}__${v}"]`)?.checked);
const radio=(form,name)=>form.querySelector(`[name="${name}"]:checked`)?.value||'';
const text=(form,name)=>(form.querySelector(`[name="${name}"]`)?.value||'').trim();
function quick(c,target,list){return `<div class="qa-quick">${list.map(([l,v])=>`<button type="button" class="btn sm light" data-qa-fill="${c.esc(target)}" data-qa-value="${c.esc(v)}">${c.esc(l)}</button>`).join('')}</div>`}
const upload=(c,label,hint)=>`<div class="form-field full"><label for="f-qa_files">${c.esc(label)}</label><input type="file" id="f-qa_files" name="qa_files" multiple accept=".pdf,.png,.jpg,.jpeg,.docx,.xlsx,.pptx"><p class="hint">${c.esc(hint)}</p></div>`;
const wrap=html=>`<div class="qa-form">${html}</div>`;
const cond=(show,html)=>`<div class="form-field full qa-cond" data-qa-show="${show}" hidden><div class="form-grid">${html}</div></div>`;

// 条件显示（data-qa-show="字段=值"）、快捷填写按钮、公益类收入自动为 0。
function bind(){
 if(typeof document==='undefined')return;
 const form=document.querySelector('#modal-root #edit-form');if(!form)return;
 const sync=()=>{
  form.querySelectorAll('[data-qa-show]').forEach(box=>{const [n,v]=box.dataset.qaShow.split('=');const on=v.split('|').some(x=>radio(form,n)===x||form.querySelector(`[name="${n}__${x}"]`)?.checked||(x==='on'&&form.querySelector(`[name="${n}"]`)?.checked));box.hidden=!on});
  const inc=form.querySelector('[name="expected_income"]');if(inc&&form.querySelector('[name="category"]')){const pub=radio(form,'category')==='community';inc.readOnly=pub;if(pub)inc.value='0'}
 };
 form.addEventListener('change',sync);form.addEventListener('input',sync);
 form.addEventListener('click',ev=>{const b=ev.target.closest('[data-qa-fill]');if(!b)return;ev.preventDefault();
  const name=b.dataset.qaFill,val=b.dataset.qaValue;
  if(name==='days'){const s=form.querySelector('[name="start_date"]'),en=form.querySelector('[name="end_date"]');if(!s.value)s.value=today();const d=new Date(s.value+'T00:00:00');d.setDate(d.getDate()+Number(val)-1);en.value=d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0')}
  else{const t=form.querySelector(`[name="${name}"]`);if(t){t.value=val;t.dispatchEvent(new Event('input',{bubbles:true}))}}
  sync()});
 sync();
}

async function uploadFiles(c,kind,id,version,form){
 const files=checkUploadFiles(form.querySelector('[name="qa_files"]')?.files||[]);
 if(!files.length)return {version,failed:[]};
 return uploadSequential({api:c.api,kind,id,version,entries:uploadEntries(files),reason:'立项方案材料'});
}

function projectForm(c){
 const e=c.esc;
 // 2026-11-09 设计图 v2：必填只有名称、类别、起止日期、预估人次（外加学校要求的方案材料）；场地、收入、成果等收进“结项前补”，带默认值。
 const body=c.field('name','项目名称','text','',{full:true})
  +chips(c,'category',CATEGORY,{label:'培训类别'})
  +c.field('start_date','开始日期','date',today())+c.field('end_date','结束日期','date','')
  +`<div class="form-field full qa-days">${quick(c,'days',[['1 天',1],['3 天',3],['1 周',7],['1 个月',30],['一学期',120]])}</div>`
  +c.field('expected_participants','预估人次','number','',{min:0,step:'1'})
  +cond('category=subsidy',chips(c,'groups',GROUPS.map(x=>[x,x]),{multi:true,label:'重点群体'})+c.field('groups_note','行动对接','text','',{required:false,full:true}))
  +upload(c,'方案材料','')
  +`<details class="form-field full qa-more"><summary>结项前补：场地、收入、预期成果、一人一技、积分口径</summary><div class="form-grid">`
  +chips(c,'venue_type',VENUES,{label:'培训场地',checked:['base'],required:false})
  +c.field('venue_place','具体地点','text','',{required:false,full:true})
  +cond('venue_type=offsite',c.field('venue_reason','外出理由','text','',{required:false,full:true})+c.field('venue_ref','议定文号或会议日期','text','',{required:false,full:true}))
  +c.field('expected_income','预计收入（元）','number','',{min:0,step:'0.01',required:false})
  +chips(c,'outcome',OUTCOMES.map(x=>[x,x]),{multi:true,label:'预期成果',checked:['结业证书'],required:false})
  +`<div class="form-field full"><label class="choice qa-check"><input type="checkbox" name="one_skill"><span>“一人一技”项目</span></label></div>`
  +cond('one_skill=on',chips(c,'groups1',GROUPS.map(x=>[x,x]),{multi:true,label:'重点群体'}))
  +chips(c,'level',LEVELS,{label:'项目级别',checked:['school'],required:false})+chips(c,'scene',SCENES,{label:'培训场景',checked:['ordinary'],required:false})+chips(c,'mode',MODES,{label:'核算方式',checked:['module'],required:false})+chips(c,'class_type',CLASS_TYPES,{label:'班型',checked:['technical'],required:false})+c.field('cohort','期次','text','第一期',{required:false})+c.field('code','项目编号','text','',{required:false})
  +`</div></details>`;
 c.formModal('新申报培训项目',wrap(body),async(v,form)=>{
  const need=[[text(form,'name'),'项目名称'],[radio(form,'category'),'培训类别'],[text(form,'start_date'),'开始日期'],[text(form,'end_date'),'结束日期'],[v.expected_participants!=null&&v.expected_participants!=='','预估人次']];
  for(const [val,l] of need)if(!val)throw Error('请填写或选择：'+l);
  if(text(form,'end_date')<text(form,'start_date'))throw Error('结束日期不能早于开始日期');
  const outcomes=picked(form,'outcome',OUTCOMES.map(x=>[x,x]));
  if(!outcomes.length)outcomes.push('结业证书');
  const venue={type:radio(form,'venue_type')||'base',place:text(form,'venue_place')||VENUES.find(x=>x[0]===(radio(form,'venue_type')||'base'))?.[1]||'',offsite_reason:text(form,'venue_reason'),offsite_ref:text(form,'venue_ref')};
  if(venue.type==='offsite'&&!(venue.offsite_reason&&venue.offsite_ref))throw Error('校外培训请填写外出理由和议定文号（或会议日期）');
  const one=!!form.querySelector('[name="one_skill"]')?.checked,cat=radio(form,'category');
  const groups=[...new Set([...picked(form,'groups',GROUPS.map(x=>[x,x])),...picked(form,'groups1',GROUPS.map(x=>[x,x])),text(form,'groups_note')].filter(Boolean))].join('；');
  if((one||cat==='subsidy')&&!groups)throw Error('补贴性培训或“一人一技”项目请选择重点群体');
  const files=form.querySelector('[name="qa_files"]')?.files||[];
  if(!files.length)throw Error('请附上方案材料');
  checkUploadFiles(files);
  const income=cat==='community'?'0':(v.expected_income==null||v.expected_income===''?'0':String(v.expected_income));
  const data={code:text(form,'code')||autoCode('XM'),name:text(form,'name'),cohort:text(form,'cohort')||'第一期',org_id:(c.me?.org?.kind==='college'?c.me.org.id:c.me?.org?.parent_id)||c.me.user.org_id,owner_id:c.me.user.id,
   category:cat,high_risk:false,expected_income:income,expected_participants:Number(v.expected_participants),expected_outcomes:outcomes.join('；'),
   start_date:text(form,'start_date'),end_date:text(form,'end_date'),mode:radio(form,'mode')||'module',class_type:radio(form,'class_type')||'technical',
   level:radio(form,'level')||'school',scene:radio(form,'scene')||'ordinary',target_groups:groups,one_skill:one,
   dates_confirmed:true,level_confirmed:true,scene_confirmed:true,mode_confirmed:true,venue};
  const r=await c.api('/social/projects',{method:'POST',body:{reason:'申报培训项目',data}});
  const up=await uploadFiles(c,'social_project',r.item.id,r.item.version,form);
  if(up.failed?.length){c.closeModal();c.toast('项目已保存为草稿，但有材料没传上：'+up.failed.map(x=>x.name).join('、')+'。请在详情里补传后提交。',true);await c.render?.();return}
  try{await c.api('/social/projects/'+r.item.id+'/actions',{method:'POST',body:{action:'submit',expected_version:up.version,reason:'提交学院审批'}})}
  catch(err){c.closeModal();c.toast('项目已保存为草稿，暂未提交：'+err.message,true);await c.render?.();return}
  c.closeModal();c.toast('已提交学院审批');await c.render?.();
 },{submit:'提交学院审批',stepper:false,contextLabel:'培训项目 / 新申报',hint:''});
 bind();
}

function courseForm(c){
 const body=c.field('name','课程名称','text','',{full:true,placeholder:'例如：社区茶艺入门'})
  +`<div class="form-field"><label for="f-hours">培训学时 <b>*</b></label><input type="number" id="f-hours" name="hours" min="0" step="0.5" required>${quick(c,'hours',[['4',4],['8',8],['16',16],['24',24],['32',32]])}</div>`
  +chips(c,'teaching_mode',TEACHING,{label:'教学方式',checked:['lecture']})
  +`<details class="form-field full qa-more"><summary>更多</summary><div class="form-grid">${chips(c,'ideology',IDEOLOGY,{label:'思政属性',checked:['course_ideology']})}${c.field('intro','课程简介','textarea','',{required:false,full:true,rows:2,textLimit:2000})}${c.field('code','课程编号（不填自动生成）','text','',{required:false})}</div></details>`;
 c.formModal('新申报培训课程',wrap(body),async(v,form)=>{
  if(!text(form,'name'))throw Error('请填写课程名称');if(v.hours==null)throw Error('请填写学时');
  const data={source:'manual',code:text(form,'code')||autoCode('KC'),name:text(form,'name'),project_code:'',teacher_id:null,hours:v.hours,teaching_mode:radio(form,'teaching_mode')||'lecture',ideology:radio(form,'ideology')||'course_ideology',intro:text(form,'intro')};
  await c.api('/applications/courses',{method:'POST',body:{data,reason:'申报培训课程'}});
  c.closeModal();c.toast('已提交学院审批。课件审查记录在学院审批时核验。');await c.render?.();
 },{submit:'提交学院审批',stepper:false,contextLabel:'培训课程 / 新申报'});
 bind();
}

function baseForm(c){
 const body=c.field('name','基地名称','text','',{full:true,placeholder:'例如：茶艺实训基地'})
  +chips(c,'onsite',[['yes','校内'],['no','校外']],{label:'校内还是校外',checked:['yes']})
  +cond('onsite=no',c.field('partner','共建单位','text','',{required:false,full:true,placeholder:'合作单位全称'}))
  +c.field('location','具体地点','text','',{full:true,placeholder:'例如：实训楼 101 / XX 镇 XX 村'})
  +chips(c,'usage',USAGES,{multi:true,label:'用途',checked:['practice']})
  +`<details class="form-field full qa-more"><summary>选填：认定依据、级别、设立日期、负责人</summary><div class="form-grid"><div class="form-field full"><label for="f-recognition">认定依据</label><input id="f-recognition" name="recognition" maxlength="200">${quick(c,'recognition',[['共建协议','共建协议（编号：）'],['学校发文','学校发文（文号：）'],['学院会议纪要','学院会议纪要（日期：）']])}</div>${chips(c,'level',[['school','校级'],['city','市级'],['province','省级及以上']],{label:'基地级别',checked:['school'],required:false})}${c.field('established_on','设立日期','date','',{required:false})}${c.field('manager_name','基地负责人','text','',{required:false,placeholder:'不填就是本人'})}${c.field('code','来源编号（不填自动生成）','text','',{required:false})}</div></details>`;
 c.formModal('新申报培训基地',wrap(body),async(v,form)=>{
  const usages=picked(form,'usage',USAGES);
  if(!text(form,'name'))throw Error('请填写基地名称');if(!usages.length)throw Error('请选择用途');
  const onsite=radio(form,'onsite')!=='no';if(!onsite&&!text(form,'partner'))throw Error('校外基地请填写共建单位');
  const data={code:text(form,'code')||autoCode('JD'),name:text(form,'name'),teacher_id:null,usages,onsite,partner:text(form,'partner'),level:radio(form,'level')||'school',
   established_on:text(form,'established_on')||today(),manager_name:text(form,'manager_name'),recognized_on:null,location:text(form,'location'),recognition:text(form,'recognition')};
  await c.api('/applications/bases',{method:'POST',body:{data,reason:'申请培训基地'}});
  c.closeModal();c.toast('已提交学院审批');await c.render?.();
 },{submit:'提交学院审批',stepper:false,contextLabel:'培训基地 / 新申报',hint:''});
 bind();
}

async function trainerForm(c){
 const e=c.esc;let quals=[];
 try{quals=(await c.api('/qualifications?size=100&state=APPROVED')).items||[]}catch{quals=[]}
 const me=c.me?.user||{};
 const body=`<div class="form-field full qa-source"><strong>本人资料已带出</strong><span>${e(me.name||'')}${quals.length?' · 已审核资质：'+e(quals.map(q=>q.name).join('、')):''}</span></div>`
  +c.field('specialty','能教什么','text','',{full:true,placeholder:'例如：茶艺、电商运营、家政服务'})
  +chips(c,'dir',DIRECTIONS,{multi:true,label:'主要面向哪类培训'})
  +(quals.length?`<fieldset class="form-field full qa-field"><legend>引用已审核资质</legend><div class="choice-row">${quals.map(q=>`<label class="choice"><input type="checkbox" name="qual_${e(q.id)}" checked><span>${e(q.name)}</span></label>`).join('')}</div></fieldset>`:'')
  +`<div class="form-field full"><label for="f-qualification_basis">资格依据（有已审核资质可不填）</label><input id="f-qualification_basis" name="qualification_basis" maxlength="2000" placeholder="职称、职业资格或行业经历，一句话即可">${quick(c,'qualification_basis',[['职称','具有 职称，从事相关教学 年'],['职业资格','持有 职业资格证书'],['行业经历','有 年行业一线工作经历']])}</div>`;
 c.formModal('申报培训师',wrap(body),async(v,form)=>{
  const directions=picked(form,'dir',DIRECTIONS);
  if(!directions.length)throw Error('请至少选一类培训');const quals=[...form.querySelectorAll('input[name^="qual_"]:checked')];if(!text(form,'qualification_basis')&&!quals.length)throw Error('请填写资格依据，或勾选要引用的已审核资质');
  const data={source:'internal',name:'',unit:'',title:text(form,'title'),specialty:text(form,'specialty'),directions,
   qualification_ids:[...form.querySelectorAll('input[name^="qual_"]:checked')].map(i=>i.name.slice(5)),qualification_basis:text(form,'qualification_basis')||'引用本人已审核资质',experience:''};
  await c.api('/applications/trainers',{method:'POST',body:{data,reason:'申报培训师'}});
  c.closeModal();c.toast('已提交，学院审核后报组织人事部认定。');await c.render?.();
 },{submit:'提交学院审批',stepper:false,contextLabel:'培训师资 / 新申报',hint:''});
 bind();
}

export async function quickApply(c,type){
 if(type==='project')return projectForm(c);
 if(type==='course')return courseForm(c);
 if(type==='base')return baseForm(c);
 if(type==='trainer')return trainerForm(c);
 throw Error('此申报入口暂不可用');
}
