// 课程只作为办理入口，项目、材料和积分仍交给原业务处理函数。
export async function coursePointsAction(action, id, c) {
 const [applicationId,projectId='']=String(id||'').split('|'),user=c.me.user.id,page=c.currentPage?.();
 const current=()=>!c.currentUser||c.currentUser()===user&&(!c.currentPage||c.currentPage()===page);
 const d=await c.api('/applications/'+encodeURIComponent(applicationId)+'/course-points'+(projectId?'?project_id='+encodeURIComponent(projectId):''));
 if(!current())return;
 const key=applicationId+(d.project?'|'+d.project.id:projectId?'|'+projectId:'');
 if(action==='claim'){
  if(d.claim&&d.can_open_claim){c.closeModal();return c.runAction('social-detail','social_claim|'+d.claim.id)}
  if(!d.can_claim)throw Error(d.stage==='ready'?'请以 '+d.applicant.name+' 本人身份办理；如其他窗口切换了身份，请刷新页面后重试。':d.message);
  c.closeModal();return c.runAction('social-claim-new',[d.project.id,d.period_id,d.policy_id].join('|'));
 }
 if(action==='link'){
  if(!d.can_link)throw Error('当前课程或身份不能关联项目，请刷新办理状态。');
  const picker=await c.projectField(c,'',{name:'project_id',key:'id',optional:false,courseApplication:applicationId});
  if(!current())return;
  return c.formModal('关联培训项目',c.note('课程：'+d.course.name+'。请选择本人负责或有管理权限的项目；审核中、已结项项目不能改挂。')+picker+c.field('reason','关联说明','textarea','将已审批课程用于本项目培训',{full:true}),async v=>{
   const project=await c.api('/social/objects/social_project/'+encodeURIComponent(v.project_id));
   await c.api('/social/projects/'+encodeURIComponent(v.project_id)+'/courses/link',{method:'POST',body:{course_code:d.course.code,expected_version:project.item.version,reason:v.reason}});
   c.closeModal();c.toast('课程已关联项目');return coursePointsAction('open',applicationId+'|'+v.project_id,c);
  },{submit:'确认关联',contextLabel:'课程积分办理 / 关联项目',returnTo:()=>coursePointsAction('open',key,c)});
 }
 const e=c.esc,first=d.steps.findIndex(s=>!s.done),steps=`<ol class="apply-steps">${d.steps.map((s,i)=>`<li class="${s.done?'done':i===first?'current':''}"><i>${s.done?c.icon('check'):i+1}</i><span>${e(s.label)}</span></li>`).join('')}</ol>`;
 const project=d.project?`<p><strong>关联项目：</strong>${e(d.project.name)} · ${e(d.project.cohort)} <span class="badge blue-b">${e(d.project.state_label)}</span></p>`:'';
 const choices=d.projects.map(p=>`<p>${c.act(p.name+' · '+p.cohort,'course-points',applicationId+'|'+p.id,'light')}</p>`).join('');
 const body=`<div class="application-detail"><section class="detail-status-summary"><div><strong>${e(d.label)}</strong><p>${e(d.message)}</p><small>${d.claim?.state==='ARCHIVED'?'办理结果：':'下一步办理人：'}${e(d.responsible)}</small></div></section><section class="detail-section"><h3>${e(d.course.name)}</h3><p>课程编号：${e(d.course.code||'审批后生成')} · 积分申报人：${e(d.applicant.name)}</p>${project}${choices}</section><div class="apply-progress">${steps}</div><p class="detail-action-note">授课与课程资源开发等辅助工作沿同一项目申报，审核归档后计入个人积分。课程入库本身不直接计分；同一项目已有申请时继续原申请。</p>${d.stage==='ready'&&!d.can_claim?`<p class="detail-action-note">请由 ${e(d.applicant.name)} 使用本人身份提交积分申请。</p>`:''}</div>`;
 const actions=[['policy','deadline'].includes(d.stage)&&c.can?.('rules.manage')?c.act('配置周期','search-nav','rules')+c.act('配置积分口径','search-nav','policy'):'',d.can_link?c.act('关联培训项目','course-points-link',key,'primary'):'',d.stage==='link'&&d.can_create_project?c.act('申报培训项目','course-points-new-project',key):'',d.project?c.act(d.project.can_manage?'办理项目':'查看项目','social-detail','social_project|'+d.project.id):'',d.can_claim?c.act('填写积分申请','course-points-claim',key,'primary'):'',d.claim&&d.can_open_claim?c.act(d.claim.state==='ARCHIVED'?'查看积分认定':['DRAFT','RETURNED'].includes(d.claim.state)?'继续原积分申请':'查看积分申请','course-points-claim',key,'primary'):'',d.can_read_application?c.act('查看课程审批','app-detail',applicationId):'',c.act('关闭','close')].join('');
 c.modal('课程积分办理 · '+d.course.name,body,actions,true,'申报培训课程 / 后续办理');
}
