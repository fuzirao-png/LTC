# 历史邮件关联回填 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 安全回填本地历史入站邮件与外发邮件的父子关联，并同步可确认的回复状态。

**Architecture:** 在邮件基础设施层抽出纯函数匹配器，统一规范化网关包装的 Message-ID 和回复主题。新增一次性 CLI 回填脚本，在单事务中只更新唯一高置信候选；无候选和多候选仅统计不修改。现有实时收信流程复用相同 Message-ID 规范化规则。

**Tech Stack:** Python 3、PostgreSQL、stdlib unittest、pg8000。

---

### Task 1: 添加可测试的匹配规则

**Files:**
- Modify: `apps/api/src/ltc/modules/customer_operation/infrastructure/mail_store.py`
- Test: `apps/api/tests/test_historical_email_linkage.py`

- [ ] 提取 Message-ID token 规范化函数：去掉空白、外层 `< >`，兼容网关前缀后唯一保留完整 token。
- [ ] 提取回复主题规范化函数：去除常见 `Re/Fwd/自动回复/OOO` 前缀后比较大小写折叠文本。
- [ ] 为完整匹配、网关包装匹配、主题规范化和不安全多候选分别写单元测试。
- [ ] 运行 `cd apps/api && PYTHONPATH=src python -m unittest tests.test_historical_email_linkage -v`，先确认新测试在实现前失败。

### Task 2: 实现数据库回填服务

**Files:**
- Create: `apps/api/src/ltc/scripts/backfill_historical_email_links.py`
- Test: `apps/api/tests/test_historical_email_linkage.py`

- [ ] 实现 `plan_backfill(rows)` 纯函数，输出 `matched`、`ambiguous`、`unmatched` 和跳过原因，不执行 SQL。
- [ ] 实现 PostgreSQL 查询：只取未关联 inbound；优先唯一 Message-ID 候选，其次同公司/联系人/收件人/主题/30 天窗口候选。
- [ ] 实现单事务更新 `parent_email_id`、`thread_key`、外发 `replied_at` 和 `status`，使用 `WHERE parent_email_id IS NULL` 保证幂等。
- [ ] 增加 `--dry-run` 和默认报告，禁止脚本发送邮件或访问远程服务器。
- [ ] 运行专项测试，确认重复运行不会产生二次变更。

### Task 3: 执行本地回填并验收

**Files:**
- No production source changes beyond Task 1–2.
- Runtime data: local PostgreSQL `ltc` only.

- [ ] 先执行 `--dry-run`，核对预计 27 条高置信关联及 3 条歧义跳过。
- [ ] 执行正式回填，记录 matched/ambiguous/unmatched 统计。
- [ ] 查询入站总数、parent 关联数、外发 replied 状态和正文标题哈希，确认没有内容丢失或误关联。
- [ ] 运行现有邮件、客户操作和全量 API 专项测试。

### Task 4: 更新文档

**Files:**
- Modify: `docs/superpowers/specs/2026-09-01-historical-email-linkage-design.md`

- [ ] 追加实际执行时间、回填数量、跳过数量和验证命令，不记录账号、密码或邮件正文。
