# 联系人邮箱验证回填迁移结果

## 背景

客户运营中，部分联系人已经有真实入站回信，但联系人评分原因仍显示“邮箱未验证”。根因是收信入库后只记录了邮件和回复状态，没有同步把 `ltc.contact.email_status` 更新为 `valid`，历史邮件也没有回填 `last_verified_at`。

## 迁移类型

- 类型：数据迁移
- 是否变更表结构：否
- 迁移文件：`db/migrations/0021_contact_email_verification_backfill.sql`

## 迁移规则

对所有满足以下条件的联系人进行回填：

- `ltc.contact.status = 'active'`
- 存在同公司、同联系人、方向为 `inbound` 的 `ltc.email_message`

回填内容：

- `email_status = 'valid'`
- `last_verified_at = max(COALESCE(email_message.received_at, email_message.created_at))`
- 同步更新 `updated_at` 和 `version`

## 本地迁移结果

- 有真实入站邮件的活跃联系人：11 个
- 迁移后已具备 `email_status = 'valid'` 且 `last_verified_at` 非空的联系人：11 个

`zonglin` 账号相关结果：

- `Nexus Business Travel / Evan / ronlinyang123@gmail.com`：已更新为 `valid`，验证时间为 `2026-08-06 06:32:28 UTC`
- `Nexus Business Travel / 宋广硕 / 826698876@qq.com`：已更新为 `valid`，验证时间为 `2026-08-05 06:03:47 UTC`
- `clay.com / verification@clay.com`：已更新为 `valid`，验证时间为 `2026-08-03 16:42:09 UTC`

## 后续影响

联系人排序/评分读取 roster 时会重新计算分数。回填后，这类已有回信联系人不应再因为 `email_status = unknown/risky` 出现“邮箱未验证”的评分原因。
