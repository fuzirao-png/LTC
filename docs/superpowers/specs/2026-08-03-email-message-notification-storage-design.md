# 邮件提醒迁移到 email_message 设计

## 目标

将客户运营的邮件提醒从本地 `pa-notifications.json` 迁移到 PostgreSQL 的现有 `ltc.email_message` 表，保持销售隔离、未读状态、邮件详情跳转和消息去重，不再依赖本地提醒文件。

## 当前问题

- 邮件本体已经写入 `ltc.email_message`，提醒却单独写入本地 JSON，存在双写和不同步。
- 本地文件不适合多进程和多人部署，数据库备份也不会自动包含提醒状态。
- 不能直接把所有历史入站邮件都当作提醒，否则迁移后会突然展示大量旧邮件。

## 数据模型

在 `ltc.email_message` 增加三个可空字段：

- `notification_created_at timestamptz`：不为空表示该入站邮件已生成前端提醒。
- `notification_read_at timestamptz`：为空表示未读，不为空表示已读。
- `notification_dismissed_at timestamptz`：预留隐藏/删除提醒能力；当前接口只过滤不为空的记录。

新增部分索引：

`(sales_user_id, notification_created_at DESC) WHERE notification_created_at IS NOT NULL AND notification_dismissed_at IS NULL`。

不修改分布式迁移 `0001`，新增 `0016_email_message_notifications.sql`。

## 写入流程

1. IMAP 收到邮件并成功写入 `email_message`。
2. 仅当邮件实际关联到客户与销售、并成功完成入库时，设置 `notification_created_at`。
3. 邮件入库和提醒创建在同一个数据库事务中完成，不再调用 `PaNotificationService.create_from_event` 写 JSON。
4. 内部邮箱之间且没有显式客户联系人的邮件仍返回 `None`，不创建提醒。

## 查询和已读

提醒列表直接查询 `email_message`：

- `direction = 'inbound'`
- `sales_user_id = 当前登录销售`
- `notification_created_at IS NOT NULL`
- `notification_dismissed_at IS NULL`

按 `notification_created_at DESC` 返回最多 50 条，并映射成前端当前使用的提醒结构。提醒 `id` 直接使用 `email_id`，跳转继续使用 `company_id + email_id`。

标记已读时执行带销售归属条件的更新：

`UPDATE ... SET notification_read_at = now() WHERE email_id = ? AND sales_user_id = 当前销售`。

## 历史数据迁移

提供一次性迁移脚本读取当前运行目录下的 `pa-notifications.json`：

- 使用记录中的 `emailId` 匹配 `email_message.email_id`。
- 写入 `notification_created_at`。
- JSON 中 `read=true` 的记录同步写入 `notification_read_at`。
- 没有有效 `emailId` 或数据库中不存在对应邮件的旧提醒跳过并输出统计。
- 脚本可重复执行，更新使用幂等条件。

迁移成功后，JSON 文件保留为备份但业务代码不再读取或写入它。

## API 与前端兼容

保留现有接口地址和响应结构：

- `GET /api/v1/inbound-mail/notifications`
- `PATCH /api/v1/inbound-mail/notifications/{email_id}/read`
- `GET /api/v1/inbound-mail/notifications/{email_id}`

前端不需要修改主要展示和跳转逻辑，只需继续把提醒 `id` 传给已读和详情接口。

## 测试

- 入站邮件事务成功后生成数据库提醒。
- 入库失败时不生成提醒。
- li.ming、zonglin 等销售只能读取自己的提醒。
- 标记已读不能修改其他销售的邮件。
- 历史 JSON 已读状态迁移正确且脚本幂等。
- 提醒详情仍能跳转到对应客户和历史邮件。
- 删除 JSON 后提醒接口仍正常工作。

## 非目标

- 本次不建立通用通知中心。
- 会议、任务、分析报告等非邮件提醒不写入 `email_message`。
- 本次不增加推送、WebSocket 或浏览器系统通知。
