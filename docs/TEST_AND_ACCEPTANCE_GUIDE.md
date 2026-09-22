> R7 增量优先参见 `docs/R7_DEPLOYMENT_ACCEPTANCE.md`：新空校配置工具、文件 UID、逐表恢复核对及独立 MySQL 执行器。无 R7 数据对账回执的旧备份不允许直接自动恢复；本轮生产门仍 BLOCKED。

> R6 更新：教师考核历史投影、原附件、审计导出及开放移交 v2 详见 `R6_EVIDENCE_CHAIN_AND_HANDOVER.md`；原手册其余功能继续适用。

# R5 测试与验收指南

所有命令从工程根目录运行。分组保存日志，外层超时时先检查对应日志/退出信息，不将截断直接判定为通过或失败。

```bash
python -m pytest -q tests/p0 --ignore=tests/p0/test_r5_installation.py
python -m pytest -q tests/p0/test_r5_installation.py
python -m pytest -q tests/r2/test_api.py tests/r2/test_hardening.py
python -m pytest -q tests/r2/test_r3_*.py
python -m pytest -q tests/r2/test_r4_*.py tests/r2/test_r5_closeout.py
node --test tests/js/*.test.mjs
python scripts/check_assembly.py --strict
python scripts/route_security_audit.py
```

组数与证据路径见 R5_DELTA_ACCEPTANCE.md。pytest 包含 SQLite 合成业务、API 控制流、隔离命令/协议替身及旧库拒绝测试，不是生产 MySQL/外部系统/浏览器验证。Node 40 项为实际 JS 逻辑和静态入口合同断言，不是浏览器点击验收。路由扫描仅检查标准认证原语是否挂载，不独立证明所有权限安全。

R5 的新空校来源/拒绝专项使用新冻结迁移实际建 SQLite 测试库；业务 API 组使用 fixture 建测试模型。没有把模型 create_all 当成生产迁移。旧 0002 代码只在隔离 helper 测试中保留，不属于旧库升级支持。

## 必须保留的现场门

- 真实 MySQL 8.4/InnoDB：新空校迁移、同基线复跑、canonical 备份空目标恢复、结构核对，以及旧库/缺来源/stamp 拒绝。模板 acceptance/mysql_evidence.template.json 中必须标明真实引擎、版本、非合成类型并附日志，不能只把布尔值填 true。
- 原生浏览器四角色与反向安全流程：实际 HTTPS、前端、Cookie/CSRF、打印预览及业务读回。当前 Chromium 能启动但访问本地站点被 ERR_BLOCKED_BY_ADMINISTRATOR 阻断，不绕过管理策略、不记成功。
- 正式 HTTPS 性能、学校真实积分/考核双轨样本签认、三类外部接口真实协议和责任方联调，仍分别验收。当前没有真实现场输入，不作通过声明。

`python scripts/release_gate.py --root . --mysql acceptance/mysql_evidence.template.json --browser evidence/r5/native_browser_attempt.json --output evidence/r5/release_gate.json` 当前应退出 2 并输出 BLOCKED。这是正确阻断，不是可以删掉或改松的测试。
