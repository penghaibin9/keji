# 跃科非学历教育 P0-R5 增量交付报告

日期：2026-09-18。版本：2026.09.18-p0-r5-fresh-only。

## 结论与交付性质

本轮已在校验过的 R4 原工程上完成六组内部增量，交付完整 R5 源码、增量补丁、测试日志/机器摘要和校验值；不是仅有说明文件的资源包。**源码组装 PASS；生产总门 BLOCKED。不能覆盖旧数据库，不能直接替换学校正式环境。**

恢复输入 `Yueke_NonDegree_Source_Checkpoint_P0_R4_InternalComplete_20260918.zip`，SHA256 `c069ddf5144cc7f9b3132fb7676b1303773c958a8d3447a1703de93ce7b986b4`。没有恢复到上一窗口未封包的 R5 文件/日志，本轮从可信 R4 重新做增量，并非重跑不存在的 R5 日志。R4 已有参训分表、主数据、入站计划、接口目录、组织考核等均沿用。

## 六项缺口与代码落点

| 项目 | 本轮落地 | 主要代码 |
|---|---|---|
| 新基线/旧库边界 | 全新空校冻结基线、安装来源/结构/校验值门；旧库、旧备份、伪版本号拒绝；同基线重复安装 no-op；恢复前后身份核验 | app/installation.py、alembic/versions、canonical_schema.json、scripts/deploy_control.py |
| 接口连接生命周期 | 配置→验证→显式启用；固定地址/密钥变量；过期/密钥轮换/配置变化失效；计划停用；恢复后撤销连接批准 | app/integrations.py、routes/integrations.py、app/maintenance.py、frontend/app.js |
| 同步佐证 | 明确 accepted=true 才成功、请求/回执摘要、逐次日志；历史幂等项纳入核对；同批重复拒绝；缺项不报完成；授权下载佐证 | app/integrations.py、routes/integrations.py |
| 组织考核打印/复制/排名 | 复制为新版本草稿，必须重新试算；同周期/层级/规则范围排名，并列名次及分页；归档快照打印并验摘要 | app/org_assessment.py、routes/calculations.py、frontend/app.js |
| 入站预览关联校验 | 教师组织/账号及课程项目预检查；确认时重验配置、内容、行数与关联；整批保存点回滚；撤销计划阻断 | app/reference_data.py、app/inbound_sync.py |
| 聚合状态筛选 | 首页/驾驶舱/组织页状态和退回筛选进入服务端、URL与考核穿透；培训收入/流水统计不混用考核状态 | app/read_queries.py、routes/business.py、frontend/scope.js |

后端表共 46 张（R4 原 44 张加安装来源、连接验证），另有 Alembic 版本表，共 47 张。没有重写原考核公式或臆造学校等级。

## 迁移证据保留

`backend/alembic_legacy_unverified/20260917_0002_org_assessment_and_sync.py` 原字节保留，SHA256：`4189c4e40192edf320277a76538df6cc3e86e911af1f8a1d02156e95ccf3f938`。历史父迁移 `20260917_0001` 仍缺失，没有伪造。

正式迁移图只包含新 `20260918_0001`（down_revision=None）。`installation_provenance` 只由新空库迁移最后一步写入；运行账户仅能读取。单改 Alembic 版本号不能通过来源/结构门。该机制不是针对能任意修改数据库、应用及校验清单的恶意高权限 DBA 的密码学证明。

备份必须带受 manifest 覆盖的来源回执；恢复只允许独立空目标，恢复库安装身份必须与回执一致。恢复后撤销会话、重置管理员并强制改密，同时断开接口、过期验证、取消自动计划、阻断未完成外部任务，避免恢复快照后自动重复外发。已完成历史证据不删除，不假装远端已回滚。

## 最终自动化结果

| 分组 | 通过 | 最终日志/XML前缀 |
|---|---:|---|
| 原基础安全/运维 P0 | 108 | evidence/r5/p0 |
| R5 安装来源/旧库拒绝专项 | 20 | evidence/r5/r5_installation |
| 原核心业务 API 与安全 | 81 | evidence/r5/r2_core |
| R3 扩展 | 73 | evidence/r5/r3_extensions |
| R4 + R5 业务收口 | 54 | evidence/r5/r4_r5_business |
| Python 合计 | **336** | evidence/r5/test_summary.json |
| 前端 Node 合同测试 | **40** | evidence/r5/frontend_final.log |

Python 0 失败、0 跳过。336 项包含 R4 原 281 项与本轮新增 55 项；不重复计中间运行。Node 为逻辑及入口合同测试，不冒充浏览器点击测试。修改过与新迁移边界冲突的旧期望；没有通过跳过测试或允许旧库来凑通过。

API 静态认证扫描 **119 条路由、0 个认证原语漏挂**，实际权限反向用例另在 Python 组内。静态扫描本身不等于所有安全风险已不存在。

冻结建表及索引共 **142 条 MySQL 方言语句**可编译（46 表、96 索引），证据为 `mysql_dialect_compile.json`；没有连接或执行 MySQL，绝不是 MySQL 数据库测试结果。SQLite 中的新基线、来源、重复执行及拒绝场景已实际运行，但不替代生产数据库。

## 未通过或待外部条件

1. **真实 MySQL 8.4**：未执行真实迁移、canonical 备份恢复、真实 schema/并发验收。模板继续为 false；release_gate 新增真实引擎、8.4版本、非合成证据类型要求，SQLite/编译结果即使布尔字段全 true 也不能冒充。
2. **原生浏览器**：Chromium 144.0.7559.96 实际启动成功，直接 HTTP 访问本地站点返回 200，但 Chromium 导航报 `net::ERR_BLOCKED_BY_ADMINISTRATOR`。未绕过策略；没有成功截图，也没有宣称真实页面/打印/四角色业务通过。
3. **三类外部系统**：没有学校真实适配器、网络、协议或凭据；接口生命周期是可施工的正式内部实现，不能宣称 SSO/中台/湘培已接通。R5 协议分支测试均为明确的无网络替身。
4. **正式 HTTPS 性能、学校真实积分/考核双轨样本与签认**：仍缺现场资料/环境。真实业务粒度、冲正、证书来源、SSO回调等不自行猜测。

总发布门实际输出 `BLOCKED`，阻断项为 mysql、browser、performance、school_sample、external；不再包含新空校源码迁移图缺失。部署脚本并非替代上述人工验收结论的凭据。

## 文件与复现

完整包包含 backend、frontend、deploy、scripts、tests、acceptance、docs 和 evidence；无 .env、学校数据、测试数据库、运行缓存、node_modules 或 .git。保留原 Excel 模板，没有在本轮篡改学校样本。R4 历史 README/校验清单/部署说明移入 evidence/r4_original_inputs；原误命名的 `--root` JSON 输出作为历史证据保留，不当命令执行。

源码关键入口：README_START_HERE.md、docs/R5_FRESH_CANONICAL_BOUNDARY.md、docs/R5_INTEGRATION_LIFECYCLE.md、docs/TEST_AND_ACCEPTANCE_GUIDE.md。最终证据只按 test_summary.json 引用；evidence/r5/intermediate_not_final 为中间失败、旧计数和已取代运行，不混入最终统计。

增量补丁只适用于上述 SHA256 的原 R4 包，可先在其干净副本运行 `git apply --check <补丁文件>`；没有这个完全相同的基线则使用完整 R5 包，不强制覆盖其他版本。只读源码核验：`python scripts/check_assembly.py --strict`。

下一验收动作固定为：**独立真实 MySQL 8.4 新空校安装 → 来源/结构核验 → 初始化与核心 HTTP/Excel 主链 → canonical 备份空目标恢复 → 伪版本/旧库拒绝 → 可用 HTTPS 原生浏览器四角色与打印验收。** 现阶段不要把 R5 覆盖到旧库或正式学校。
