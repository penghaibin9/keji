# API 接口目录

> 由 `scripts/generate_api_catalog.py` 从当前源码自动生成。认证原语列只表示源码入口使用标准服务端认证/事务原语，不能替代运行时越权测试。

当前 API 路由：**121**；静态认证门：**PASS**。

| 方法 | 路径 | 模块文件 | 处理函数 | 认证/事务原语 | 公开 |
|---|---|---|---|---|---|
| GET | `/api/assessment-summary/latest` | `backend/app/routes/calculations.py` | `latest_assessment_summary` | read_operation | 否 |
| GET | `/api/assessments` | `backend/app/routes/calculations.py` | `assessments` | read_operation | 否 |
| POST | `/api/assessments/calculate` | `backend/app/routes/calculations.py` | `assessment_calculate` | command | 否 |
| GET | `/api/assessments/{ident}` | `backend/app/routes/calculations.py` | `assessment_detail` | read_operation | 否 |
| POST | `/api/assessments/{ident}/actions` | `backend/app/routes/calculations.py` | `assessment_action` | command | 否 |
| POST | `/api/assessments/{ident}/adjust` | `backend/app/routes/calculations.py` | `assessment_adjust` | command | 否 |
| GET | `/api/assessments/{ident}/attachments/{attachment_id}/download` | `backend/app/routes/calculations.py` | `assessment_frozen_attachment` | current_actor | 否 |
| GET | `/api/assessments/{ident}/evidence` | `backend/app/routes/calculations.py` | `assessment_evidence_download` | current_actor | 否 |
| GET | `/api/assessments/{ident}/print` | `backend/app/routes/calculations.py` | `assessment_print` | read_operation | 否 |
| POST | `/api/attachments/{ident}/detach` | `backend/app/routes/files.py` | `detach` | command | 否 |
| GET | `/api/attachments/{ident}/download` | `backend/app/routes/files.py` | `download` | current_actor | 否 |
| POST | `/api/attachments/{kind}/{ident}` | `backend/app/routes/files.py` | `upload` | command, current_actor | 否 |
| GET | `/api/audit` | `backend/app/routes/admin.py` | `audit_list` | read_operation | 否 |
| POST | `/api/auth/login` | `backend/app/routes/auth.py` | `login` | — | 是 |
| POST | `/api/auth/logout` | `backend/app/routes/auth.py` | `logout` | command | 否 |
| GET | `/api/auth/me` | `backend/app/routes/auth.py` | `me` | current_actor | 否 |
| POST | `/api/auth/password` | `backend/app/routes/auth.py` | `change_password` | command | 否 |
| GET | `/api/connections` | `backend/app/routes/tasks.py` | `connections` | read_operation | 否 |
| GET | `/api/connections/catalog` | `backend/app/routes/integrations.py` | `connection_catalog` | read_operation | 否 |
| GET | `/api/connections/summary` | `backend/app/routes/integrations.py` | `connection_summary` | read_operation | 否 |
| POST | `/api/connections/validate` | `backend/app/routes/integrations.py` | `validate_mapping` | command | 否 |
| PUT | `/api/connections/{ident}` | `backend/app/routes/integrations.py` | `update_connection` | command | 否 |
| POST | `/api/connections/{ident}/activate/{check_id}` | `backend/app/routes/integrations.py` | `connection_activate` | command | 否 |
| GET | `/api/connections/{ident}/checks` | `backend/app/routes/integrations.py` | `connection_checks` | read_operation | 否 |
| POST | `/api/connections/{ident}/disconnect` | `backend/app/routes/integrations.py` | `connection_disconnect` | command | 否 |
| POST | `/api/connections/{ident}/inbound/preview` | `backend/app/routes/integrations.py` | `inbound_preview` | command | 否 |
| POST | `/api/connections/{ident}/inbound/pull` | `backend/app/routes/integrations.py` | `inbound_pull` | command | 否 |
| POST | `/api/connections/{ident}/probe` | `backend/app/routes/integrations.py` | `connection_probe` | command | 否 |
| POST | `/api/connections/{ident}/sync` | `backend/app/routes/integrations.py` | `manual_sync` | command | 否 |
| GET | `/api/delivery/configuration` | `backend/app/routes/delivery.py` | `configuration` | read_operation | 否 |
| GET | `/api/delivery/configuration.xlsx` | `backend/app/routes/delivery.py` | `configuration_xlsx` | current_actor | 否 |
| GET | `/api/dictionaries` | `backend/app/routes/admin.py` | `dictionaries` | read_operation | 否 |
| GET | `/api/disputes` | `backend/app/routes/business.py` | `disputes` | read_operation | 否 |
| POST | `/api/disputes` | `backend/app/routes/business.py` | `dispute_create` | command | 否 |
| GET | `/api/disputes/{ident}` | `backend/app/routes/business.py` | `dispute_detail` | read_operation | 否 |
| POST | `/api/disputes/{ident}/resolve` | `backend/app/routes/business.py` | `dispute_resolve` | command | 否 |
| POST | `/api/exports` | `backend/app/routes/tasks.py` | `create_export` | command | 否 |
| GET | `/api/imports` | `backend/app/routes/tasks.py` | `imports` | read_operation | 否 |
| GET | `/api/imports/templates/{kind}` | `backend/app/routes/tasks.py` | `import_template` | current_actor | 否 |
| GET | `/api/imports/{ident}` | `backend/app/routes/tasks.py` | `import_detail` | read_operation | 否 |
| POST | `/api/imports/{ident}/confirm` | `backend/app/routes/tasks.py` | `import_confirm` | command | 否 |
| GET | `/api/imports/{ident}/errors` | `backend/app/routes/tasks.py` | `import_errors` | current_actor | 否 |
| POST | `/api/imports/{kind}/preview` | `backend/app/routes/tasks.py` | `import_preview` | command, current_actor | 否 |
| GET | `/api/inbound-batches/{ident}` | `backend/app/routes/integrations.py` | `inbound_detail` | read_operation | 否 |
| POST | `/api/inbound-batches/{ident}/confirm` | `backend/app/routes/integrations.py` | `inbound_confirm` | command | 否 |
| GET | `/api/integration-schedules` | `backend/app/routes/integrations.py` | `integration_schedules` | read_operation | 否 |
| POST | `/api/integration-schedules` | `backend/app/routes/integrations.py` | `create_integration_schedule` | command | 否 |
| PUT | `/api/integration-schedules/{ident}` | `backend/app/routes/integrations.py` | `update_integration_schedule` | command | 否 |
| GET | `/api/notices` | `backend/app/routes/admin.py` | `notices` | read_operation | 否 |
| POST | `/api/notices` | `backend/app/routes/admin.py` | `create_notice` | command | 否 |
| PUT | `/api/notices/{ident}` | `backend/app/routes/admin.py` | `update_notice` | command | 否 |
| GET | `/api/operations` | `backend/app/routes/tasks.py` | `operations` | read_operation | 否 |
| GET | `/api/organization-assessment-rules` | `backend/app/routes/calculations.py` | `organization_rules` | read_operation | 否 |
| POST | `/api/organization-assessment-rules` | `backend/app/routes/calculations.py` | `create_organization_rule` | command | 否 |
| POST | `/api/organization-assessment-rules/{ident}/actions` | `backend/app/routes/calculations.py` | `organization_rule_action` | command | 否 |
| POST | `/api/organization-assessment-rules/{ident}/copy` | `backend/app/routes/calculations.py` | `copy_organization_rule` | command | 否 |
| POST | `/api/organization-assessment-rules/{ident}/trial` | `backend/app/routes/calculations.py` | `trial_organization_rule` | command | 否 |
| GET | `/api/organization-assessments` | `backend/app/routes/calculations.py` | `list_organization_assessments` | read_operation | 否 |
| POST | `/api/organization-assessments/calculate` | `backend/app/routes/calculations.py` | `calculate_organization_assessments` | command | 否 |
| GET | `/api/organization-assessments/ranking` | `backend/app/routes/calculations.py` | `organization_assessment_ranking` | read_operation | 否 |
| GET | `/api/organization-assessments/{ident}` | `backend/app/routes/calculations.py` | `organization_assessment_detail` | read_operation | 否 |
| POST | `/api/organization-assessments/{ident}/actions` | `backend/app/routes/calculations.py` | `organization_assessment_action` | command | 否 |
| GET | `/api/organization-assessments/{ident}/print` | `backend/app/routes/calculations.py` | `organization_assessment_print` | read_operation | 否 |
| GET | `/api/organization-workbench` | `backend/app/routes/business.py` | `organization_workbench` | read_operation | 否 |
| GET | `/api/organizations` | `backend/app/routes/admin.py` | `organizations` | read_operation | 否 |
| POST | `/api/organizations` | `backend/app/routes/admin.py` | `create_org` | command | 否 |
| PUT | `/api/organizations/{ident}` | `backend/app/routes/admin.py` | `update_org` | command | 否 |
| POST | `/api/organizations/{ident}/state` | `backend/app/routes/admin.py` | `org_action` | command | 否 |
| GET | `/api/participations` | `backend/app/routes/reference.py` | `participation_list` | read_operation | 否 |
| POST | `/api/participations` | `backend/app/routes/reference.py` | `participation_create` | command | 否 |
| GET | `/api/participations/{ident}` | `backend/app/routes/reference.py` | `participation_detail` | read_operation | 否 |
| PUT | `/api/participations/{ident}` | `backend/app/routes/reference.py` | `participation_update` | command | 否 |
| GET | `/api/periods` | `backend/app/routes/admin.py` | `periods` | read_operation | 否 |
| POST | `/api/periods` | `backend/app/routes/admin.py` | `create_period` | command | 否 |
| POST | `/api/periods/{ident}/close` | `backend/app/routes/admin.py` | `close_period` | command | 否 |
| GET | `/api/point-balances` | `backend/app/routes/calculations.py` | `balances` | read_operation | 否 |
| POST | `/api/point-balances/{ident}/actions` | `backend/app/routes/calculations.py` | `balance_action` | command | 否 |
| GET | `/api/points` | `backend/app/routes/calculations.py` | `points` | read_operation | 否 |
| POST | `/api/points/adjust` | `backend/app/routes/calculations.py` | `point_adjust` | command | 否 |
| POST | `/api/points/calculate` | `backend/app/routes/calculations.py` | `point_calculate` | command | 否 |
| GET | `/api/points/{ident}` | `backend/app/routes/calculations.py` | `point_detail` | read_operation | 否 |
| GET | `/api/qualification-categories` | `backend/app/routes/admin.py` | `categories` | read_operation | 否 |
| GET | `/api/qualifications` | `backend/app/routes/business.py` | `qualifications` | read_operation | 否 |
| POST | `/api/qualifications` | `backend/app/routes/business.py` | `qualification_create` | command | 否 |
| GET | `/api/qualifications/{ident}` | `backend/app/routes/business.py` | `qualification_detail` | read_operation | 否 |
| PUT | `/api/qualifications/{ident}` | `backend/app/routes/business.py` | `qualification_update` | command | 否 |
| POST | `/api/qualifications/{ident}/actions` | `backend/app/routes/business.py` | `qualification_action` | command | 否 |
| GET | `/api/records` | `backend/app/routes/business.py` | `records` | read_operation | 否 |
| POST | `/api/records` | `backend/app/routes/business.py` | `record_create` | command | 否 |
| GET | `/api/records/{ident}` | `backend/app/routes/business.py` | `record_detail` | read_operation | 否 |
| PUT | `/api/records/{ident}` | `backend/app/routes/business.py` | `record_update` | command | 否 |
| GET | `/api/reference/courses` | `backend/app/routes/reference.py` | `courses` | read_operation | 否 |
| GET | `/api/reference/projects` | `backend/app/routes/reference.py` | `projects` | read_operation | 否 |
| GET | `/api/reference/teacher-hr` | `backend/app/routes/reference.py` | `teacher_hr` | read_operation | 否 |
| GET | `/api/roles` | `backend/app/routes/admin.py` | `roles` | read_operation | 否 |
| POST | `/api/roles` | `backend/app/routes/admin.py` | `copy_role` | command | 否 |
| PUT | `/api/roles/{ident}` | `backend/app/routes/admin.py` | `update_role` | command | 否 |
| GET | `/api/rules` | `backend/app/routes/calculations.py` | `rules` | read_operation | 否 |
| POST | `/api/rules` | `backend/app/routes/calculations.py` | `create_rule` | command | 否 |
| POST | `/api/rules/{ident}/actions` | `backend/app/routes/calculations.py` | `rule_action` | command | 否 |
| POST | `/api/rules/{ident}/trial` | `backend/app/routes/calculations.py` | `trial` | command | 否 |
| GET | `/api/settings` | `backend/app/routes/admin.py` | `settings` | read_operation | 否 |
| PUT | `/api/settings/{key}` | `backend/app/routes/admin.py` | `update_setting` | command | 否 |
| GET | `/api/settings/{key}/history` | `backend/app/routes/admin.py` | `setting_history` | read_operation | 否 |
| GET | `/api/statistics` | `backend/app/routes/business.py` | `statistics` | read_operation | 否 |
| GET | `/api/sync-items` | `backend/app/routes/integrations.py` | `sync_items` | read_operation | 否 |
| GET | `/api/sync-items/{ident}` | `backend/app/routes/integrations.py` | `sync_item_detail` | read_operation | 否 |
| POST | `/api/sync-items/{ident}/retry` | `backend/app/routes/integrations.py` | `retry_sync_item` | command | 否 |
| GET | `/api/sync-tasks/{ident}/evidence` | `backend/app/routes/integrations.py` | `sync_evidence` | read_operation | 否 |
| POST | `/api/sync-tasks/{ident}/retry-failed` | `backend/app/routes/integrations.py` | `retry_sync_failed` | command | 否 |
| GET | `/api/tasks` | `backend/app/routes/tasks.py` | `tasks` | read_operation | 否 |
| GET | `/api/tasks/{ident}` | `backend/app/routes/tasks.py` | `task_detail` | read_operation | 否 |
| GET | `/api/tasks/{ident}/download` | `backend/app/routes/tasks.py` | `task_download` | current_actor | 否 |
| POST | `/api/tasks/{ident}/retry` | `backend/app/routes/tasks.py` | `task_retry` | command | 否 |
| GET | `/api/teacher-activity-summary` | `backend/app/routes/reference.py` | `teacher_activity_summary` | read_operation | 否 |
| GET | `/api/teachers` | `backend/app/routes/admin.py` | `teachers` | read_operation | 否 |
| GET | `/api/todos` | `backend/app/routes/business.py` | `todos` | read_operation | 否 |
| GET | `/api/users` | `backend/app/routes/admin.py` | `users` | read_operation | 否 |
| POST | `/api/users` | `backend/app/routes/admin.py` | `create_user` | command | 否 |
| PUT | `/api/users/{ident}` | `backend/app/routes/admin.py` | `update_user` | command | 否 |
| POST | `/api/users/{ident}/reset-password` | `backend/app/routes/admin.py` | `reset_user` | command | 否 |

## 使用边界

- `/api/auth/login` 是当前唯一公开业务 API；其他接口必须进入服务端认证/权限路径。
- 路由目录不包含学校 SSO、数据中台和湘培的外部协议细节；外部协议以真实联调文档和责任方签认为准。
- 生产 OpenAPI/Swagger 默认关闭；本文件用于交付、审计和版本比对。
