# 湖南科技职业学院一站式非学历教育智慧前台：安装与接收说明

本工程的正式安装入口为 `scripts/deployment_config.py` 和 `scripts/install.sh --initialize-new-school`。安装包、镜像和版本信息以同版 `release-metadata.json` 为准；采购验收仍须完成学校实际环境、正常账号和业务流程核验。

1. 接收后先执行 `sha256sum -c SHA256SUMS` 核对安装包、离线镜像及全部分卷。解压后执行 `python3 scripts/check_assembly.py --strict`，确认源码齐套及迁移头 `20261013_0005`。校验不符时停止安装。
2. 在学校确认的新空目录和新空数据库安装；已有学校系统另走备份及升级流程。先核对主机、架构、端口、域名、证书、恢复管理员和服务器外的备份位置。
3. 用 `docker image load -i <完整离线镜像包>` 加载镜像，依据版本元数据核对三个镜像的标签、内容标识和处理器架构。不要混用不同版本的镜像或分卷。
4. 由实施人员运行 `python3 scripts/deployment_config.py prepare --help` 查看配置参数，填写学校名称、访问地址、三个同版镜像标签、匹配的正式证书和私钥，并使用 `--new-school-only`。私有配置在学校受控目录生成，不进入交付包。生成后执行 `python3 scripts/deployment_config.py verify` 核验。
5. 完成目标及恢复保护核验并取得部署授权后，执行 `sudo bash scripts/install.sh --initialize-new-school`。该入口用于新学校空库，不能覆盖已有学校数据库。
6. 按[管理员操作手册](docs/ADMIN_OPERATIONS_MANUAL.md)完成登录、四类角色业务和权限、附件、下载、刷新、备份与隔离恢复演练。发生错误立即停止后续步骤，保留诊断记录和现有数据。

教师及管理人员操作见[用户手册](docs/USER_MANUAL.md)，外部系统接入见[接口对接说明](docs/INTERFACE_INTEGRATION_GUIDE.md)，交付资料见[源代码与资料移交清单](docs/源代码与资料移交清单.md)。

本地合成数据回归、源码检查和镜像核对分别记录；真实统一认证、数据中台、学校服务器性能、双轨计分比对和最终验收仍须学校现场验证。交付包不包含学校账号口令、私钥、运行数据库、上传材料或本地测试截图。
