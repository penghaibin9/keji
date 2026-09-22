# R9 官方资料核实与采用记录

日期：2026-09-19（北京时间）。资料只用于解释技术行为和修复设计，不作为真实MySQL或学校外部接口已经通过的证据。

| 官方文档 | 核实内容 | 本轮采用位置与验收边界 |
|---|---|---|
| SQLAlchemy 2.0 — Populate Existing | Session里已加载的对象不会因为再次查询同一主键而默认刷新。`populate_existing=True`显式刷新现有对象，也会覆盖尚未刷新的对象值。 | `backend/app/sync_policy.py`：先按顺序取得父任务锁，再读取并刷新明细、重查版本；先刷盘再刷新。`test_manual_retry_reloads_item_that_finished_while_waiting_for_parent`及版本负例复现的是受控identity-map陈旧场景，不是假称多进程InnoDB并发测试。 |
| MySQL 8.4 — Fractional Seconds | DATETIME未显式指定小数秒精度时默认为0，低精度存储会发生舍入或按SQL模式截断。时间相等不能证明两个操作的先后，随机UUID也不是操作顺序。 | `backend/app/integrations.py`：新连接验证回执绑定递增Connection.version；相同秒、随机ID逆序、时钟回退、重复证明都加入控制测试。不改冻结表结构；新增证明的版本号不是对DBA的数字签名。 |
| MySQL 8.4 — Locking Reads | `FOR UPDATE`针对数据库行提供锁定读取，锁随事务结束释放。数据库行锁和Python已加载对象是否刷新是两个问题。 | 保持先父任务、后明细的锁顺序；保留事务、任务租约和原有权限检查。运行账号权限和真实锁竞争仍待独立MySQL8.4。 |
| MySQL 8.4 — Installing Generic Binaries | 官方提供Unix/Linux通用二进制安装方式。 | 已检查沙箱无docker/mysql/mysqld，官方CDN域名解析失败，未取得二进制、未安装引擎。未改用MariaDB或SQLite冒充MySQL验收。 |

来源（官方原文）：

- https://docs.sqlalchemy.org/en/20/orm/queryguide/api.html#populate-existing
- https://dev.mysql.com/doc/refman/8.4/en/fractional-seconds.html
- https://dev.mysql.com/doc/refman/8.4/en/innodb-locking-reads.html
- https://dev.mysql.com/doc/refman/8.4/en/binary-installation.html

运行记录：`evidence/r9/official-download-network.log`、`environment.json`、`mysql/mysql_acceptance.json`。没有导入互联网上不明来源的业务代码、没有修改Chromium管理员策略、没有连接用户电脑/GitHub/学校生产系统。
