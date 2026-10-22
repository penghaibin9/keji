// 生成《手册菜单按钮核对表》：帮助章节与侧栏、页面标题的对照，以及帮助里引用的按钮、菜单字样在源码里的位置。
// 只做静态核对，不代替学校浏览器或真实账号验收。用法：node scripts/build_help_menu_check.mjs
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {HELP_VERSION,HELP_TOPICS,HELP_FAQS,HELP_ALIASES} from '../frontend/help-content.js';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const app=fs.readFileSync(path.join(root,'frontend/app.js'),'utf8');
const titles=Object.fromEntries([...app.match(/const titles=\{([^\n]+)\};/)[1].matchAll(/(?:^|,)(\w+):'([^']+)'/g)].map(x=>[x[1],x[2]]));
const tabs={};for(const [,group,body] of app.match(/const pageGroups=\{([^\n]+)\};/)[1].matchAll(/(\w+):\{title:'[^']+',tabs:\[(.*?)\]\]\}/g))for(const [,id,label] of body.matchAll(/\['(\w+)','([^']+)'/g))tabs[id]=label;
for(const [,id,label] of (app.match(/const managerListTabs=\{([^}]+)\}/)?.[1]||'').matchAll(/(\w+):'([^']+)'/g))tabs[id]=label+'（管理人员）';
const groupOf={};
const nav=app.slice(app.indexOf('function navItems(){'),app.indexOf('let sidebarPage'));
for(const [,group,body] of nav.matchAll(/\['(工作台|教师发展|统计分析|系统管理)',\[(.*?)\]\]/g))for(const [,id] of body.matchAll(/\['(\w+)','/g))groupOf[id]=group;
for(const [,id] of (nav.match(/business=teacher\?(.*?);/)?.[1]||'').matchAll(/\['(\w+)','/g))groupOf[id]='培训业务';
for(const [id,g] of Object.entries({creditreview:'教师发展',imports:'系统管理',exports:'系统管理',rules:'系统管理',policy:'系统管理',settings:'系统管理',audit:'系统管理',operations:'系统管理',annual:'教师发展',recognition:'教师发展'}))groupOf[id]??=g;
const sources=['app.js','applications.js','social-training.js','school-data.js','approval-flow.js','training-workspace.js','help-system.js'].map(f=>'frontend/'+f).concat(['applications.py','social_training.py','approver_setup.py'].map(f=>'backend/app/'+f)).map(f=>[f,fs.readFileSync(path.join(root,f),'utf8').split('\n')]);
const where=text=>{const hits=[];for(const [file,lines] of sources){lines.forEach((line,i)=>{if(line.includes(text)&&hits.length<2)hits.push(`${file}:${i+1}`)});if(hits.length>=2)break}return hits};
// 说明里加引号的举例和提醒用语，不是界面字样。
const PROSE=new Set(['完成培训','按规定','协助','*','教师','脱贫人口、返乡青年；结业后推荐就业','社区营养配餐','2026年社区茶艺公益培训','2026年度教师考核规则','2026年度社会培训执行口径','2026年度教研室考核','2026年度','关于开展2026年社会培训项目申报的通知','副教授','教务处科员','学院课件审查组','第一期','学校','需要','需要我办的事','我交的申请','退回','附件','其他']);
const quoted=new Map();
const note=(text,from)=>{for(const part of text.split(/\s*→\s*/)){const t=part.trim();if(!t||PROSE.has(t))continue;if(!quoted.has(t))quoted.set(t,new Set());quoted.get(t).add(from)}};
for(const t of HELP_TOPICS)for(const text of [t.purpose,...t.steps,t.done])for(const [,q] of text.matchAll(/“([^”]+)”/g))note(q,t.title);
for(const [q,a] of HELP_FAQS)for(const [,x] of (q+a).matchAll(/“([^”]+)”/g))note(x,'常见问题');
const COMPOSED={'全部 N 门':'按门数组合显示（“全部 ”+门数+“ 门”）','院长初审 → 归口复审 → 分管副校长审批 → 教学秘书归档':'流程说明'};
const rows=[...quoted].sort(([a],[b])=>a.localeCompare(b,'zh')).map(([text,from])=>{const hits=where(text);return {text,from:[...from],hits,status:hits.length?'源码包含原文字样':COMPOSED[text]||'未在源码找到，需人工核对'}});
const missing=rows.filter(r=>!r.hits.length&&!COMPOSED[r.text]);
const esc=v=>String(v).replace(/\|/g,'\\|');
const md=[`# 手册菜单按钮核对表（${HELP_VERSION.slice(0,4)}年${Number(HELP_VERSION.slice(4,6))}月${Number(HELP_VERSION.slice(6))}日）`,'',
`本表由 \`scripts/build_help_menu_check.mjs\` 按当前源码生成。系统内帮助、帮助中心和《用户操作手册_系统内版_${HELP_VERSION}》共 ${HELP_TOPICS.length} 个章节，章节名与侧栏菜单、页面标题一致；同名页面用括号注明页签。帮助中引用的 ${rows.length} 项按钮、菜单或提示字样，${rows.length-missing.length} 项已在源码找到或属于组合文字${missing.length?`，${missing.length} 项需人工核对`:''}。此表为静态核对，不代替学校浏览器或真实账号验收。`,'',
'## 一、菜单与帮助章节对照','','| 页面代码 | 侧栏分组 | 页面标题 | 页签 | 帮助章节 | 可搜索的旧名称 |','|---|---|---|---|---|---|',
...HELP_TOPICS.map(t=>`| \`${t.id}\` | ${esc(groupOf[t.id]||(t.id==='help'?'顶部“帮助中心”':'—'))} | ${esc(titles[t.id]||'（不是业务页面）')} | ${esc(tabs[t.id]||'—')} | ${esc(t.title)} | ${esc((HELP_ALIASES[t.id]||[]).join('、')||'—')} |`),'',
'## 二、帮助引用的按钮、菜单和提示字样','','<details>','<summary>实施人员使用：查看引用位置与源码位置</summary>','','| 字样 | 引用章节 | 源码位置 | 核对说明 |','|---|---|---|---|',
...rows.map(r=>`| ${esc(r.text)} | ${esc(r.from.slice(0,3).join('、')+(r.from.length>3?' 等':''))} | ${r.hits.map(h=>'`'+h+'`').join('、')||'—'} | ${esc(r.status)} |`),'','</details>',''].join('\n');
fs.writeFileSync(path.join(root,`docs/手册菜单按钮核对表_${HELP_VERSION}.md`),md);
console.log(`核对表已生成：${HELP_TOPICS.length}个章节，${rows.length}项字样，需人工核对${missing.length}项`);
if(missing.length)console.log(missing.map(r=>r.text+'（'+r.from.join('、')+'）').join('\n'));
