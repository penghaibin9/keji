# R10 官方依据与采用记录

核实日期：2026-09-19。仅采用官方资料，不把第三方示例当成学校协议，也没有复制外部项目源码。

| 来源 | 与本轮有关的原则 | 采用位置与边界 |
|---|---|---|
| OWASP Authorization Cheat Sheet | 默认拒绝，并在每次请求核验授权；登录成功不等于拥有全部对象访问权 | `app/import_access.py`统一预览/错误文件/确认/回执校验，模板与上传入口匹配实际权限；`test_r10_import_access.py`复现撤权与正例 |
| MySQL 8.4 Consistent Nonlocking Reads | READ COMMITTED每次一致性读取可取得不同快照；REPEATABLE READ通常复用事务中的首次读取快照 | 沿用既有移交专用一致性读取事务；SQLite归档控制不冒充实际InnoDB并发、权限或恢复验收 |
| 原采购PDF第10项、第12项、第14项 | 原始依据可解释、归档结果不静默改写、材料按授权访问、结构化开放移交 | `org_evidence.py`绑定组织/规则/逐指标依据，冻结办理轨迹，排名与移交使用相同验证器 |

官方原文：

- https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- https://dev.mysql.com/doc/refman/8.4/en/innodb-consistent-read.html

项目原PDF：`acceptance/79a6e12c-5e54-4a9a-9d54-7dc1afb72ee3.pdf`。

上述文档用于确定实现原则，不证明学校接口已接通，也不证明本包完成真实MySQL/浏览器/并发验收。归档摘要与授权来源记录用于一致性核查，不是对可同时改写数据库及摘要的管理员的防篡改承诺。
