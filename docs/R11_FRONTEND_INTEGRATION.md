# R11｜已确认 HTML 设计接回现有 R10 工程

## 权威输入与边界

- 需求：原采购 PDF，9页14项101条；不新增招生、排课、收费或工资系统。
- 代码：完整 R10，SHA256 `9ae18e5dbdbe4f548438a2d28a2ab1e1df50528eda122f9cf202c1b3eb1f8792`。
- 视觉/导航：已确认设计包，SHA256 `b4c170fc8861131d0ae4df46d464d731ddbf655d6da83cf0737b83901e87aea8`。
- 仅修改隔离源码副本；未连接用户电脑、GitHub、学校或生产服务。

## 接入方法

保留 R10 的真实 app.js 业务表单、详情、动作、api()、CSRF、会话、幂等、版本校验与后端状态机。从批准设计提取蓝白样式、导航分组、卡片、首页布局和对接中心信息结构，新增 portal.css / portal-ui.js，不加载原型的示例数据、角色切换、浏览器存储或模拟请求。

原19个主视图均保留，增加 sso、hub、province、guide 四个专门入口，共23个。菜单与直接路由均按当前真实权限控制，后端权限仍是最终裁决。教师不请求管理端连接状态。

新的 GET /api/inbound-batches 提供管理员当前连接的批次元数据分页，不包含原始人事行/原文件名；具体行仍走原详情权限。GET /api/connections/coordination.xlsx 下载空白沟通模板并审计。原 tasks 增加 connection_id/data_type/state 服务端过滤。没有变更数据库结构或重写历史迁移。

## 本轮对接页签

统一认证：接入概况、字段对应、验证与启用。中台：接入概况、字段对应、入站预览、采集任务、定时计划、验证与启用。湘培：接入概况、字段对应、同步任务、逐笔记录、验证与启用。

字段表格保存使用原 PUT /connections/{id}；上传/确认、拉取、计划、单条/批量补传继续调用已有真实服务。缺少协议、适配器或权威来源时如实显示，不能凭前端改状态。

## G01-G04 修复

G01统一待办包含中台拉取失败与外发失败，保留学校同步权限。G02分级工作台纳入当前组织及授权下属组织的组织考核，不能把全校系统异常放给基层。G03组织考核翻页发送 page/size。G04授课和参训独立分页，参训查询/导出使用选定周期与时间的交集。教师活动总览独立标注“全部历史”。

## Nginx 静态资源修复

原镜像把 frontend 文件平铺到 /usr/share/nginx/html，但 index.html 请求 /assets/app.js。原 location / 的 SPA fallback 可能返回 HTML。现为 /assets/ 配置 alias，缺失脚本404、不回落首页，并给未加哈希的资源 no-store。API Dockerfile 同时包含 nginx.conf，源码组装门必须检出配置，避免打包漏掉。

官方依据：NGINX ngx_http_core_module alias 定义替换匹配的 location 前缀，https://nginx.org/en/docs/http/ngx_http_core_module.html#alias 。本轮实际 system nginx+独立HTTPS验证，不是只检查字符串；但不是 Docker 镜像构建或 MySQL 验收。

## 交给实施人员的顺序

1. 从完整 R11 解压到独立目录，核验根 SHA256 清单。R10留作对照，不能直接覆盖旧库。
2. 使用这份源码分别构建API与前端镜像，配置中两个标签都使用本轮版本。compose 默认标签已更新为 2026.09.19-r11；不允许混用旧API或旧静态前端。
3. 按原 R7_DEPLOYMENT_ACCEPTANCE.md，在独立真实MySQL8.4和独立卷中执行空校/运行账号/业务/备份恢复验收。使用既有 run_mysql_acceptance.py --run-isolated，必须先有本版匹配的本地镜像。工具没有接入现有学校数据库的入口。
4. 按学校实际域名、证书与权限配置HTTPS。在原生浏览器走四角色登录、列表、表单、上传、下载、打印；离线页面截图不算这步完成。
5. 外部系统分别按协议补适配与联调、学校真实双轨样本与性能验收，之后由发布门裁决。不能删除阻断门，也不能通过 stamp 或补 provenance 绕过。

## 重测入口

```sh
python scripts/run_r11_tests.py --group r11_portal
python scripts/run_r11_tests.py --group all
python scripts/run_r11_portal_control.py
python scripts/run_r11_https_control.py
python scripts/run_r11_proxy_control.py
python scripts/render_r11_offline_layout.py
python scripts/check_assembly.py --strict
```

控制脚本仅新建临时回环服务及合成SQLite数据；真实MySQL用另一验收器。run_r11_proxy_control需要系统nginx及openssl；缺少时不会算成功。截图脚本仅对实际渲染器产出的静态HTML做set_content，无浏览器策略绕过，不能替代真实点击联调。

## 保留的兼容要求

新空校迁移头 `20260918_0001`，旧 `20260917_0002` 原字节保留，缺失旧0001未补造。旧备份缺内容对账回执不能自动恢复；旧Excel预览缺摘要/授权证明需重传；旧连接证明无逻辑版本需重验；旧组织归档缺轨迹不补造。R11不改变这些边界。

所有 evidence/r4..r10 是历史证据，不能累计冒充本轮测试；本轮结果只看 evidence/r11。原101条对照表保留原版本，本轮另加页面接线清单，不把UI接入率当采购完成率。
