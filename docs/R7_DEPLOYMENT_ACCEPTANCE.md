# R7｜新空校部署与恢复核对收口

日期：2026-09-18。唯一输入为 R6 完整源码包。范围仍是原采购 PDF 14 项、101 条；不扩大到其他系统，不全量重写已有功能。

## 结论与证据层级

本轮完成部署密钥文件权限、证书检查、私有初始化工具、Nginx 上传配置、数据库备份内容核对、独立 MySQL 验收执行器，并进行了新空校 HTTPS 合成业务验证。

**源码组装 PASS；生产发布 BLOCKED。** 本轮没有真实 MySQL 服务、Docker 镜像构建或 Docker 容器部署成功证据。SQLite 的新空库迁移、备份副本对账和 HTTPS 业务流只作为控制验证，不替代 MySQL。HTTPS 使用临时自签名本地证书并显式校验证书，未关闭 TLS 校验；不代表学校域名证书、反向代理或并发性能已验收。

实际完整回归：Python 443 项通过，0 失败、0 错误、0 跳过（相对 R6 新增 66 项）；Node 45 项通过。真实 HTTPS 87 次请求、6 组检查通过。证据见 `evidence/r7/test_summary.json`、`final-python.xml`、`node-tests.log`、`https_control/business_http.json`。

## 本轮修复

### 1. 私有配置生成和容器读取权限

新增 `scripts/deployment_config.py`。生成独立 root、迁移、应用、首次管理员四份随机凭据，不输出密码值，不使用公共默认密码。私有文件不进源码、报告或镜像上下文。已有 `.env`、密钥、TLS、运行数据库或文件目录不会被覆盖；符号链接、硬链接、特殊文件、弱凭据、凭据复用、账号串用、TLS 私钥不配对、域名不匹配、临近过期证书都会被相应检查拒绝。未完成的生成过程留下 `.prepare-incomplete`，不能当成功配置使用。

文件型 Docker Compose secret 的宿主机 UID/权限会影响容器读取，不能仅在 Compose 里写 mode 就认为已生效。本轮把应用/迁移 secret 归 UID 10001；MySQL 初始化使用的 secret 归 UID 999；前端固定使用 UID 10001，使其与 TLS 文件归属一致。部署前实际运行指定镜像的 `id -u mysql`，不是 999 时阻断并要求适配，不静默放宽权限。

`mysql-init/01-users.sh` 改用私有 `root.cnf`，不再把 root 密码拼进 `mysql -p...` 命令行。`.dockerignore` 明确排除运行数据、真实配置、TLS 私钥和密钥目录；没有使用会误伤 `backend/app/passwords.py` 的宽泛密码文件名排除规则。

已执行真实 OpenSSL 配对/域名检查、Unix UID 10001/999 子进程读取/互相拒读测试。**未执行真实 Docker secret 挂载和完整镜像启动测试。**

### 2. 合法附件不应先被代理过小限制挡住

`deploy/nginx.conf` 显式设置 101 MiB 请求上限，为后端最大 100 MiB 文件限制预留 multipart 空间；后端的学校级上传限制、实际字节检查、文件内容校验和权限检查仍然保留，不因代理上限放开而取消。本环境未运行 Nginx 容器，大附件代理行为仍须真实部署验证。

### 3. 恢复后必须核对数据库实际内容

新增 `backend/app/database_snapshot.py`：停止写入后，在一个读取事务中按主键稳定排序，记录 **47 张表（含 Alembic 版本表）**的列名、行数和带类型序列化后的 SHA256。Decimal、日期、时间、二进制、JSON、字符串和空值分别处理；证据文件不输出原始行或密码。数据摘要是完整性核对，不是防恶意 DBA 的数字签名。

备份增加 `database-reconciliation.json`。新空校恢复流程为：验证包清单和安装来源 → 确認空目标 → 导入 SQL → 验证安装身份 → 比较每表行数和内容摘要 → 恢复并核对原附件 → 迁移/会话及接口清理 → 应用授权 → 启动检查。内容不一致时保留维护锁、停止业务服务，不执行恢复后的开放流程。

**重要兼容边界：没有 R7 数据核对回执的旧备份不能直接自动恢复。** 包括部分来源合法但没有此回执的 R5/R6 备份。不得手工补写回执以绕过检查；须另行做受控恢复、来源审查和数据对账。旧 `20260917_0002` 数据库继续禁止升级或恢复到本基线。

SQLite 控制测试验证了：同一数据库反复读取摘要一致；真实 SQLite 备份副本内容一致；保持行数不变只改一项内容也能发现差异；缺来源和结构异常拒绝；恢复核对失败后不开放写入。Docker 故障注入测试明确标注为编排测试替身，未冒充数据库恢复演练。

### 4. 从真正空学校走 HTTPS 主链

`scripts/run_r7_https_control.py` 在临时独立目录执行 canonical migration 和 `app.cli init`，只初始化学校与管理员；没有调用 fixture populate，也没有用 SQL 直接塞入业务数据。之后实际 HTTPS 调用完成：

首次登录改密 → 创建两学院/两教研室及四级账号 → 下载/校验 Excel 错误行 → 预览不写正式业务 → 确认写入 → 相同幂等键重复提交不重复写入 → 资质与原附件 → 积分/考核规则试算、启用、计算 → 四级确认和归档 → 原附件权限验证 → 真实 worker 生成考核 Excel → 停用账号后旧会话立即失效。

87 次 HTTP 请求和 6 组组合检查记录保存在 `evidence/r7/https_control/`。其中 Excel、资质图片、考核证据全部是合成样本，不是学校真实样本。验收驱动中的 PNG 样本和导出任务终态识别在调试时修正，之前失败日志保留；最终通过的是正确格式图片和系统真实 `DONE` 终态，没有为通过测试放松业务校验。

原生 Chromium 正常导航仍返回 `ERR_BLOCKED_BY_ADMINISTRATOR`。没有修改管理员策略、关闭证书校验或把 HTTP 成功换算为浏览器成功。

## 下一环境直接执行的 MySQL 验收器

`scripts/run_mysql_acceptance.py` 不接收外部数据库 URL，不接入现有学校目录。它需要 Linux 管理员授权、Docker Compose、OpenSSL，以及**已在本地构建的 R7 API、前端和 MySQL 8.4 镜像**。依赖不存在就输出 BLOCKED，不下载、不用 SQLite 回退、不伪造成功。

```bash
# 先在独立验收机器构建此源码的镜像；不是在学校正式目录执行。
docker build -f deploy/Dockerfile.api -t local/nondegree-api:r7 .
docker build -f deploy/Dockerfile.frontend -t local/nondegree-frontend:r7 .
# MySQL 8.4 镜像须已经按单位镜像管理流程准备在本机。
sudo python3 scripts/run_mysql_acceptance.py --run-isolated \
  --api-image local/nondegree-api:r7 \
  --frontend-image local/nondegree-frontend:r7 \
  --mysql-image mysql:8.4 \
  --output /tmp/nondegree-r7-mysql-evidence-unique
```

执行器先校验 API/前端镜像包含的源码字节与当前工程一致，再创建两个随机项目名的独立临时实例，仅绑定 127.0.0.1 的随机端口。计划验证新空校安装、重复迁移、真正运行账号的 DDL/证据修改权限拒绝、与上述 HTTPS 共用的业务流、备份、第二空实例恢复、逐表内容核对、旧会话失效、归档与原附件不变、非空目标再次恢复被拒绝。

结束仅清理本次拥有的两个项目，不执行全局 `docker prune`。失败保留 BLOCKED 与明确诊断；清理失败时保留私有实验目录路径，必须由管理员处理。该执行器即使取得 `PASS_ISOLATED_MYSQL_SUBSET`，也只证明其覆盖的独立实验子集，**仍不自动满足整个采购验收或生产门**。崩溃恢复、并发故障矩阵、学校数据、真实外部接口和原生浏览器等另行验收。

本环境运行回执在 `evidence/r7/mysql/mysql_acceptance.json`：`DOCKER_UNAVAILABLE`，`mysql_tested=false`，`restore_executed=false`。

## 新学校配置生成入口

学校证书、域名、镜像和部署审批齐备后，管理员在**全新独立目录**使用：

```bash
sudo python3 scripts/deployment_config.py prepare --new-school-only \
  --school-name '已确认的学校名称' --origin 'https://已确认的学校域名' \
  --api-image local/nondegree-api:r7 --frontend-image local/nondegree-frontend:r7 \
  --mysql-image mysql:8.4 \
  --certificate /私有证书目录/fullchain.pem --private-key /私有证书目录/privkey.pem
sudo python3 scripts/deployment_config.py verify
```

以上只是生成/检查配置，不会启动服务。学校名称、域名、TLS 路径需要真实确认，不提供可误用的正式默认值。管理员初始密码仅保存于 `deploy/secrets/admin_password`，不得上传或与代码包一同转发。正式 install/backup/restore 仍有维护确认、空目标、来源和镜像核验等门禁，不因本轮多了自动配置工具而绕过。

## 连续性和未完成项

canonical head 仍为 `20260918_0001`；本轮未改数据库结构、业务表字段或冻结迁移，旧 `0002` 原字节保留。没有新增菜单或更改学校积分/考核口径。

待完成：真实 MySQL 8.4 和镜像/代理执行；原生浏览器四级角色与打印分页；学校域名 HTTPS 性能和 100 并发；真实学校代表样本双轨比对并签认；三类真实外部接口；培训试运行及合同履约。`acceptance/R7_PDF_101_Clause_Tracker.xlsx` 每条保留这些边界。

技术依据：Docker Compose service secrets（https://docs.docker.com/reference/compose-file/services/#secrets）、Docker secrets 指南（https://docs.docker.com/compose/how-tos/use-secrets/）、MySQL 8.4 mysqldump（https://dev.mysql.com/doc/refman/8.4/en/mysqldump.html）。这些公开文档不是本项目的实际执行证据。
