# Email Message Notification Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将邮件提醒从本地 JSON 迁移到现有 `ltc.email_message` 表，同时保持当前提醒接口和前端跳转协议兼容。

**Architecture:** 使用 `email_message.notification_created_at/read_at/dismissed_at` 表达提醒生命周期。IMAP 入站邮件与提醒创建在同一事务完成；提醒应用服务通过 PostgreSQL 存储查询、标记已读和加载详情；一次性脚本将现有 JSON 状态回填到数据库。

**Tech Stack:** PostgreSQL、FastAPI、pg8000、Python unittest/pytest、Vue 3/TypeScript。

---

### Task 1: 增加 email_message 提醒字段

**Files:**
- Create: `db/migrations/0016_email_message_notifications.sql`
- Test: `apps/api/tests/test_email_message_notification_migration.py`

- [ ] **Step 1: 编写失败的迁移结构测试**

测试连接本地 PostgreSQL，断言三个字段和部分索引存在：

`notification_created_at`、`notification_read_at`、`notification_dismissed_at`，以及按 `sales_user_id, notification_created_at DESC` 的部分索引。

- [ ] **Step 2: 运行测试确认失败**

Run: `$env:PYTHONPATH="$PWD\apps\api\src"; python -m pytest apps/api/tests/test_email_message_notification_migration.py -q`

Expected: FAIL，字段不存在。

- [ ] **Step 3: 创建 0016 迁移**

迁移使用 `ADD COLUMN IF NOT EXISTS`，并创建：

`CREATE INDEX IF NOT EXISTS ix_email_message_sales_notification ON ltc.email_message (sales_user_id, notification_created_at DESC) WHERE notification_created_at IS NOT NULL AND notification_dismissed_at IS NULL;`

- [ ] **Step 4: 应用迁移并验证测试通过**

Run: `docker exec -i ltc-postgres-1 psql -U ltc -d ltc < db/migrations/0016_email_message_notifications.sql`

Run: 迁移结构测试。

Expected: PASS。

### Task 2: 在邮件入库事务中创建提醒

**Files:**
- Modify: `apps/api/src/ltc/modules/customer_operation/infrastructure/mail_store.py`
- Modify: `apps/api/src/ltc/modules/customer_operation/application/inbound_mail_service.py`
- Test: `apps/api/tests/test_mail_store_invariants.py`
- Test: `apps/api/tests/test_inbound_mail_poller.py`

- [ ] **Step 1: 编写失败测试**

断言入站邮件 INSERT/UPDATE 会设置 `notification_created_at`，且内部邮箱被跳过时不创建提醒；处理器不再调用 JSON `create_from_event`。

- [ ] **Step 2: 运行失败测试**

Run: `python -m pytest apps/api/tests/test_mail_store_invariants.py apps/api/tests/test_inbound_mail_poller.py -q`

Expected: FAIL，现有 SQL 没有提醒字段且处理器仍写 JSON。

- [ ] **Step 3: 修改入站邮件事务**

在成功关联客户和销售的入站邮件写入中设置：

- `notification_created_at = COALESCE(notification_created_at, now())`
- 新提醒保持 `notification_read_at = NULL`
- 重复轮询同一 Message-ID 不重置已读状态

处理器从数据库返回的邮件上下文构造轮询结果，不再写 `pa-notifications.json`。

- [ ] **Step 4: 验证相关测试通过**

Run: Task 2 测试。

Expected: PASS。

### Task 3: 新增 PostgreSQL 提醒存储

**Files:**
- Create: `apps/api/src/ltc/modules/customer_operation/infrastructure/postgres_mail_notification_store.py`
- Modify: `apps/api/src/ltc/modules/customer_operation/application/pa_notification_service.py`
- Test: `apps/api/tests/test_postgres_mail_notification_store.py`
- Test: `apps/api/tests/test_user_mailbox_isolation.py`

- [ ] **Step 1: 编写存储行为失败测试**

覆盖：

- 只返回当前 `sales_user_id` 的入站提醒
- 排除 `notification_created_at IS NULL` 和已 dismissed 的记录
- `read` 由 `notification_read_at IS NOT NULL` 映射
- 提醒 `id` 使用 `email_id`
- 返回现有字段：`companyId/emailId/salesUserId/subject/from/to/body/notificationTarget`
- 标记已读必须同时匹配 `email_id + sales_user_id`

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest apps/api/tests/test_postgres_mail_notification_store.py apps/api/tests/test_user_mailbox_isolation.py -q`

Expected: FAIL，新存储不存在。

- [ ] **Step 3: 实现 PostgreSQL 存储与应用服务**

`PostgresMailNotificationStore` 提供：

- `list_notifications(role, unread_only, user_id, limit=50)`
- `get_notification(email_id, user_id)`
- `mark_read(email_id, user_id)`

`PaNotificationService` 默认使用该存储，业务路径不再读取或写入 JSON。保留旧 JSON 读取能力仅供迁移脚本显式调用，不作为默认存储。

- [ ] **Step 4: 运行存储和隔离测试**

Expected: PASS。

### Task 4: 同步提醒接口逻辑

**Files:**
- Modify: `apps/api/src/ltc/modules/customer_operation/application/service.py`
- Modify: `apps/api/src/ltc/modules/customer_operation/application/inbound_mail_service.py`
- Modify: `apps/api/src/ltc/modules/customer_operation/interfaces/router.py`
- Test: `apps/api/tests/test_customer_operation_auth.py`
- Test: `apps/api/tests/test_customer_operation_real_routes.py`

- [ ] **Step 1: 编写接口失败测试**

验证：

- GET 列表继续返回 `{success, items}`
- 管理者继续看不到销售邮箱提醒
- PATCH 使用提醒 ID（即 email_id）标记当前销售已读
- 跨销售标记已读返回 404
- GET 详情从 PostgreSQL 邮件记录加载并保留客户运营跳转参数
- 手动轮询接口返回数据库创建的提醒，不依赖 JSON

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest apps/api/tests/test_customer_operation_auth.py apps/api/tests/test_customer_operation_real_routes.py -q`

- [ ] **Step 3: 修改接口和应用服务**

保持 URL 不变：

- `GET /api/v1/inbound-mail/notifications`
- `PATCH /api/v1/inbound-mail/notifications/{email_id}/read`
- `GET /api/v1/inbound-mail/notifications/{email_id}`

所有查询和更新均传递当前登录销售的 `user_id`，详情接口不再读取 `inbound-mail-history.json`。

- [ ] **Step 4: 运行接口测试**

Expected: PASS。

### Task 5: 迁移现有 JSON 提醒状态

**Files:**
- Create: `scripts/migrate_pa_notifications_to_email_message.py`
- Test: `apps/api/tests/test_notification_json_migration.py`

- [ ] **Step 1: 编写幂等迁移失败测试**

临时 JSON 包含已读、未读、无效 emailId 三种记录；测试断言有效记录更新数据库时间字段，无效记录计入 skipped，重复运行不会破坏状态。

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest apps/api/tests/test_notification_json_migration.py -q`

- [ ] **Step 3: 实现迁移脚本**

脚本读取 `LegacyFileStore().data_dir / pa-notifications.json`，使用参数化 SQL 按 `email_id + sales_user_id` 更新；输出 scanned/migrated/skipped/already_migrated。不得输出邮箱密码或数据库密码。

- [ ] **Step 4: 在当前数据库执行并核对 35 条提醒**

Run: `$env:PYTHONPATH="$PWD\apps\api\src"; python scripts/migrate_pa_notifications_to_email_message.py`

Expected: 有效 JSON 提醒被迁移，重复执行结果稳定。

### Task 6: 前端契约兼容与完整验证

**Files:**
- Modify only if required: `apps/web/src/services/operationApi.ts`
- Modify only if required: `apps/web/src/app/layouts/AppLayout.vue`
- Test: existing frontend typecheck/build

- [ ] **Step 1: 核对提醒类型和调用协议**

确认提醒 `id` 仍为字符串、PATCH/详情 URL 不变、`read` 和 `notificationTarget` 字段仍存在。若完全兼容则不修改前端。

- [ ] **Step 2: 运行后端完整相关测试**

Run: customer-operation、mailbox isolation、main、intent、attachment 相关 pytest。

- [ ] **Step 3: 运行前端验证**

Run: `cd apps/web; npm run typecheck; npm run build`

- [ ] **Step 4: 重启并进行真实验证**

验证 API 200、zonglin 只看到自己的提醒、当前“方案讨论”提醒仍未读、标记已读后数据库 `notification_read_at` 更新、删除/重命名 JSON 后接口仍正常。

- [ ] **Step 5: 检查差异**

Run: `git diff --check`。不提交、不推送，除非用户另行要求。
