> R7 增量优先参见 `docs/R7_DEPLOYMENT_ACCEPTANCE.md`：新空校配置工具、文件 UID、逐表恢复核对及独立 MySQL 执行器。无 R7 数据对账回执的旧备份不允许直接自动恢复；本轮生产门仍 BLOCKED。

# R5 部署、备份与恢复 Runbook

**当前总发布门 BLOCKED，不可直接覆盖正式系统。** 本文替代 R4 的迁移操作说明；R4 原说明保存在 evidence/r4_original_inputs/，不可按其中旧库升级步骤执行。

## 目标与边界

Nginx/HTTPS + FastAPI + worker + MySQL 8.4/InnoDB；运行与迁移账户分权。本基线只接纳独立空校 canonical 安装；旧 0001/0002 数据库及 R4 备份禁止使用新迁移升级或恢复。具体拒绝矩阵见 R5_FRESH_CANONICAL_BOUNDARY.md。

## 首次安装前

先在隔离 MySQL 8.4 环境完成新装、来源/结构核验、重复迁移、canonical 备份空目标恢复及旧库拒绝演练；补齐 HTTPS 原生浏览器、性能、真实双轨样本和外部接口证据。部署人员审核镜像、实际域名/TLS、deploy/.env、数据库 secret、管理员临时密码文件和 ND_SCHOOL_NAME。不能把合成账号或测试环境参数带入生产。

经审批在全新独立实例使用 `sudo bash scripts/install.sh --initialize-new-school`。脚本会检查空目标、使用冻结迁移、初始化空业务学校、安装最小权限并检查健康。它不会将已有旧库当空库，也不会给旧库补 provenance。任何失败保留维护标记；不可自动清库或手工 stamp。

## 当前 upgrade 命令的限制

`sudo bash scripts/upgrade.sh --allow-maintenance-window <审核过的API镜像> <审核过的前端镜像>` 仅允许来源及结构匹配当前 canonical 基线的数据库。它先核验再维护/停写/备份/切换；本轮仅验证同基线安全门与 no-op。没有宣称实现旧版本迁移；后续变更表结构必须新增经过独立验收的迁移，不修改 R5 冻结基线。

## 备份与恢复

`sudo bash scripts/backup.sh --allow-maintenance-window` 保存来源回执、数据库、附件及逐文件哈希。备份文件需与数据库凭据一样受控；保留政策由学校批准，不默认删历史备份。

`sudo bash scripts/restore.sh --into-empty-school <经审核的canonical备份目录> [管理员用户名]` 仅允许恢复到独立空目标。先验证文件和来源，再恢复、比较安装身份、清理会话/重置管理员、断开接口/撤销自动计划/阻断未完成外部任务、重新授权及检查。必须人工核对业务数量、附件哈希、归档校验码和真实登录后才可考虑切换访问地址。

这套源码中已有上述控制逻辑与隔离测试，**真实 MySQL/容器/HTTPS 机房演练尚未完成**；脚本存在不等于部署已验收。
