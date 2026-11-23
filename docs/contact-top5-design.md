# 联系人 Top 5 与邮件触达设计

依据：`LTC_联系人排序_邮件沟通与客户分析更新规则_20260801.md`

## 实现范围

本次实现 MD 第 1-3 章中的联系人闭环：

- 六维评分、角色席位和 Top 5 多样性约束。
- 备选联系人、人工置顶、换位、替换和移出。
- 邮件沟通左侧联系人面板、推荐/手动新增抽屉。
- 未验证、退信、退订、离职和合法触达状态的发送保护。
- 客户回复后暂停同公司其他触达，仅允许继续回复原联系人。
- 联系人增删改、排序、替换、移出和恢复触达的审计记录。

MD 第 4 章的统一证据层、5 分钟防抖、冲突队列和客户分析报告增量更新不在本次实现范围内。

## 现有数据支撑

线上 LTC 业务只使用一个 PostgreSQL 数据库 `ltc`。联系人数据分两层：

- `ltc.contact`：35 条正式联系人，32 条活跃、3 条归档。
- `ltc.candidate_contact`：88 条去重后候选联系人。
- 24 条候选联系人已晋升为正式联系人，两层数据不能直接相加。
- 其余 64 条候选联系人属于 7 家尚未晋升的线索公司。
- 全库结构化联系人跨层去重后约 99 人。

26 家正式公司的“活跃正式联系人”分布是：16 家 0 人、7 家 1 人、1 家 2 人、1 家 8 人、1 家 15 人。这只是正式公司口径，不代表全库只有这些联系人。

线索晋升公司时，现有 `promotion_adapter` 会将该公司的活跃 `candidate_contact` 同步为正式 `contact`。因此邮件沟通界面以正式 `contact` 为触达主体是正确的；未晋升公司的候选联系人不应进入正式客户的邮件触达。

## 数据模型

`0017_contact_priority_roster.sql` 新增：

- `contact.employment_status`：在职、离职或未知。
- `contact.legal_basis_status`：允许、禁止或未知。
- `contact.last_verified_at`：联系人最近验证时间。
- `company_contact_roster`：Top 5/备选、排名、评分明细、推荐理由、置顶、互动锁定和触达状态。
- `company_outreach_state`：公司级触达暂停/恢复状态。

Top 5 位置通过部分唯一索引限制为 1-5，不允许静默加入第 6 人。

## 排序与触达

排序服务使用 MD 定义的六维权重，并依次填充采购、商务、业务、技术和备选席位。中英文职位使用词边界匹配，避免将 `Product Director` 中的 `cto` 子串误判为 CTO。

硬过滤条件：

- 联系人已归档/非活跃。
- `employment_status='departed'`。
- `legal_basis_status='blocked'`。
- 邮箱无效、退信或退订。
- 命中全局 `email_suppression`。

邮箱待验证可以进入 Top 5，但发送前必须拦截。界面默认选择 Top 5 中顺位最靠前的已验证联系人。

客户回复时，系统将公司触达状态改为 `paused`，并将原联系人标记为 `engagement_locked/replied`。暂停期间只允许对该联系人发送 `reply_followup` 或 `meeting_followup`。

## API 与界面

- `GET /api/v1/companies/{company_id}/contact-roster`
- `POST /api/v1/companies/{company_id}/contact-roster/recalculate`
- `PATCH /api/v1/companies/{company_id}/contact-roster/{contact_id}`
- `POST /api/v1/companies/{company_id}/outreach/resume`

邮件沟通界面左侧显示 `联系人 n/5`、Top 5 顺位、职位、分数、邮箱状态和触达状态。`+` 打开推荐联系人/手动新增抽屉。已满 5 人时必须选择替换对象并填写原因。

## 后续阶段

- D0/D2/D5/D7/D10 自动触达调度和“同日相似邮件”频控。
- 未验证采购联系人的自动验证任务。
- 自动发现更高分联系人时的提醒，不自动覆盖销售排序。
- MD 第 4 章客户分析证据、冲突、防抖和版本机制。
