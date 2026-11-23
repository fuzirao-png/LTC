# 03b - DDD 领域驱动设计中文讲解

> 版本：v3.6
> 性质：面向团队讲解的辅助读物，非规范文档
> 配套规范：`03-DDD领域驱动设计.md`
> v3.6：账号统一为销售/战略；战略人员可直接执行离职回池；禁用不再回池；S4/S5 整体延期；Apollo 作为对话搜索内部数据 Provider
> v3.5：销售管理（晋升/离职交接）整体转 Deferred；动态意向加分落点改为 Sales Lead；新增分配规则矩阵与 SLA、自动释放、登录锁定、数据补全池、手动记录批量确认
> v3.4：新增手动记录（Manual Note）、LLM 提取 Skill、报告反哺；v3.3：晋升/离职、负向过滤/动态意向
> 用途：帮助同事理解模块边界、业务语言、协作关系和关键规则

---

## 一、快速理解：这个系统在做什么

LTC Agent 是一个 B2B 销售智能系统。它做的事情可以用一句话概括：

**从互联网上发现潜在客户 → 自动评估这家公司值不值得跟进 → 分配给合适的销售 → 帮助销售理解客户、写邮件、开会、推进成交。**

为了实现这个目标，我们把系统拆成了 7 个模块，每个模块管一块事情。

---

## 二、7 个模块一句话解释

| 模块 | 一句话 |
|------|--------|
| **IAM**（身份与权限） | 管谁能登系统、谁是销售谁是战略人员、销售在哪个区域、能接多少客户 |
| **Lead Intelligence**（线索智能） | 对话搜索互联网、抓取公司信息、自动评估匹配度和客户体量 |
| **Sales CRM**（销售客户管理） | 管公司资料、联系人、销售线索的分配、认领、转交和跟进阶段 |
| **Customer Analysis**（客户分析） | 自动生成客户画像、MEDDPICC 评分、五模块分析报告 |
| **Customer Operation**（客户运营） | 写邮件、发邮件、上传会议录音、ASR 转写、任务管理 |
| **Task Runtime**（任务运行时） | 所有异步任务的调度框架：Job 队列、重试、进度推送、事件发布 |
| **Read Models**（只读视图） | 销售工作台、战略人员仪表盘、漏斗图等只读查询 |

**关键规则**：每个数据库表只能由一个模块写入。比如 Company 表只有 Sales CRM 能改，Lead Intelligence 不能直接写 Company。

---

## 三、核心业务语言（Ubiquitous Language）

我们的代码和数据库命名都统一使用以下术语。跟同事沟通时请对照这些标准叫法：

### 3.1 线索阶段（还没进正式客户库）

| 术语 | 中文 | 含义 |
|------|------|------|
| Search Run | 搜索运行 | 战略人员发起一次"帮我找做差旅管理的公司"的对话搜索 |
| Provider Execution | 数据源调用 | 一次对话搜索内部调用 Web Search 或 Apollo 的可追溯执行记录 |
| Search Evidence | 搜索证据 | 搜索返回的网页、公司信息等原始材料 |
| Candidate Observation | 候选观察 | 模型从某次搜索的一批网页中抽取出的公司快照 |
| Lead Candidate | 候选企业 | 多次搜索去重后的全局候选身份（同一家公司不会出现两次） |
| Candidate Contact | 候选联系人 | 在搜索阶段发现的联系人，分为决策者/影响者/执行者/普通员工 |
| Enrichment Run | 富化运行 | 对候选企业补充 D1-D4 四个维度的详细信息 |
| ICP Assessment | ICP 评分 | 四维匹配度打分（这个客户跟我们的业务多匹配？） |
| Customer Scale Assessment | 客户体量评估 | 三维客户规模打分（决定进 MA/SA/A 哪个销售池） |

### 3.2 CRM 阶段（已进入正式客户库）

| 术语 | 中文 | 含义 |
|------|------|------|
| Company | 公司 | 被选入销售资源池的企业主数据。不等于"已成交客户" |
| Contact | 联系人 | 可用于分析和运营的正式联系人 |
| Sales Lead | 销售线索 | 一次可分配、可跟进的销售周期。挂靠在 Company 下 |
| Assignment | 分配关系 | 一段时间内某个销售对这个线索的负责关系 |
| Pipeline Stage | 销售阶段 | new→contacted→engaged→meeting→proposal→won/lost |

### 3.3 关键区分（容易搞混）

- **Candidate ≠ Company**：候选是搜索发现的"可能值得跟进的公司"，入池后才变成正式 Company
- **ICP ≠ Scale**：ICP 回答"匹配不匹配"，Scale 回答"大不大，进哪个池"
- **Tier Change ≠ Assignment Transfer**：晋升改的是"未来路由"，转交改的是"已产生的归属"（**v3.5 起晋升功能 Deferred，暂不做**）
- **Departed ≠ Disabled**：disabled 只阻断登录和撤销 Session，不动客户；departed 由 Strategic 操作，并在同一事务把名下客户释放回原区域×等级池
- **Assignment ≠ Pipeline**：Assignment 管"谁在跟"，Pipeline 管"跟到哪了"
- **Observation ≠ Evidence**：Evidence 是搜索到的网页，Observation 是从这些网页中抽取的公司快照

---

## 四、各模块详细讲解

### 4.1 IAM（身份与权限）

**管什么**：用户账户、登录会话、销售等级、区域、容量。

**核心概念**：
- **Sales Tier（销售等级）**：MA（大客户销售）、SA（中客户销售）、A（普通销售）。这决定了销售能认领什么级别的客户。
- **Region Code（区域）**：NA（北美）、EA（东亚）、SEA（东南亚）、EU（欧洲）、**ME（中东）**、OTHER（其他）
- **Capacity（容量）**：一个销售最多同时跟多少个客户。推荐默认 MA=15、SA=25、A=40
- **Strategic（战略人员）**：可以搜索、全局查看、指派，以及直接将 Sales 标记离职并回池；不使用 `is_boss` 隐式角色

**不做什么**：不做通用 RBAC 角色权限系统。当前只有 Sales 和 Strategic 两种账户类型，权限矩阵用代码维护。

### 4.2 Lead Intelligence（线索智能）

**一句话**：这是整个系统的"入口"。所有线索都从对话搜索来，没有手工上传。

**拥有哪些数据**：
- 搜索运行记录（谁搜了什么、搜到了多少）
- Provider Execution（一次 Web Search/Apollo 调用的状态、成本、延迟和错误）
- 搜索证据（每条网页的内容、URL、所属域名）
- 候选企业（去重后的全局身份）
- 候选观察（每次搜索抽取出什么公司）
- 候选联系人（四类角色：决策者/影响者/执行者/普通员工）
- 负向过滤结果（X 排除 / D 暂存 / 通过）
- 富化运行（D1-D4 四个维度）
- 场景化 ICP 评分（当前只启用 S1/S2/S3 四维规则；S4/S5 整体延期）
- 客户体量评估（三维规模打分，证据不足时输出 unknown）

注意：**动态意向加分不归 Lead Intelligence 管**（v3.5 起）。触达发生在分配之后，加分累计在 Sales Lead 上，由 Sales CRM 执行——见 4.3 和 8.3。

**关键规则**：
- 对话搜索是唯一用户入口，没有批量上传、没有手动录入；Apollo 是内部 Provider，不是独立入口
- 同一家公司出现在多次搜索中会**自动去重**，合并为一个 Candidate
- 去重靠域名精确匹配 + 公司名+国家匹配，不会只按公司名就合并
- 每经过搜索富化成功一次，旧的 ICP 和 Scale 评分会被新的替代

### 4.3 Sales CRM（销售客户管理）

**一句话**：这是系统的"心脏"。管公司、联系人、销售线索的分配和跟进。

**核心流程**：

```
战略人员勾选候选 → 创建 Company + Contact + Sales Lead（入池）
                                        ↓
                               Sales Lead 状态 = claimable
                                        ↓
                    销售认领(Claim) 或 战略人员指派(Assign)
                                        ↓
                               Assignment 生效，开始跟进
                                        ↓
                          Pipeline 推进: new → contacted → ...
                                        ↓
                               won（成交）或 lost（流失）
```

**关键规则**：
- **入池才创建 Company**：Claim 时不创建 Company
- **Release 后回到池里**：释放后 Sales Lead 变回 claimable，别人可以认领
- **一个 Company 最多一个未关闭的 Sales Lead**：防止同一个客户被多人同时跟进
- **一个 Sales Lead 最多一个 active Assignment**：同一时间只有一个人在跟
- **当前不能跨池分配**：Claim/Assign/Transfer 的目标销售必须匹配 Lead 的区域×等级且有容量；区域未知 Lead 对 Sales 隐藏
- **动态意向加分在这里累计**：触达后的打开/点击/回复加分写在 Sales Lead 上，静态 B 级 Lead 动态总分到 80 自动升级 A4（详见 8.3）

**Assignment 的四种类型**：
| 类型 | 含义 |
|------|------|
| claim | 销售自己认领 |
| manual | 战略人员指派 |
| transfer | 从一个销售转给另一个 |
| reclaim | 之前释放过又重新认领 |

### 4.4 Customer Analysis（客户分析）

**一句话**：自动生成客户画像、MEDDPICC 评分、五模块分析报告。

**输入什么**：
- Company 基本信息
- 入池时采用的 ICP 评分（四维匹配度）
- 入池时采用的客户体量评分
- 当前 Profile（客户画像）
- MEDDPICC 八个维度
- 已有的邮件、会议、任务等运营记录

**输出什么**：
- 五模块分析报告（不可修改，每版追加）
- Sales Guide（销售指南）
- Profile/MEDDPICC 的修改建议（需人工审核接受）

**关键规则**：
- 报告**不可修改**。想改就生成新版本
- 只读取**四维 ICP**，不重新计算旧六维 ICP
- AI 建议不会静默覆盖人工填写的数据，需要用户点"接受"
- 同一个人工输入 + 同一个 Prompt + 同一个 Schema 不会重复生成

### 4.5 Customer Operation（客户运营）

**一句话**：写邮件、发邮件、传会议录音、管理待办任务。

**邮件链路**：
```
生成草稿(AI) → 人工编辑 → 审批 → 排队发送 → Provider 发送 → 送达/退信/回复
```

**会议链路**：
```
上传音视频 → 提取音频 → 标准化 → 分片 → 并行 ASR 转写 → 摘要 → 存入结构化 Segment
```

**关键规则**：
- 所有邮件、会议、任务都关联正式 Company/Lead，不关联 Candidate
- 发送前检查退订名单
- Provider 超时（发了但不知道成没成功）进入"待对账"状态，不盲重试
- 会议转写和摘要出错了可以取消重来

### 4.6 Task Runtime（任务运行时）

**一句话**：所有"异步执行"的通用框架。不是业务模块。

**提供什么能力**：
- **Job 队列**：搜索、LLM 调用、邮件发送等长任务排队执行
- **Lease 租约**：Worker 领取任务后获得租约，防止重复执行
- **Progress Event**：前端可以实时看到搜索/分析的进度
- **Outbox**：事务提交后发布事件，保证事件不丢
- **Idempotency**：防止重复提交同一个命令
- **Audit Log**：技术审计日志（不替代业务历史表）

**不做什么**：不判断"谁能认领"、"谁能发邮件"等业务规则。那些是各业务模块的事。

---

## 五、模块之间的协作方式

### 5.1 同步协作（在一个数据库事务里完成）

用于必须"要么全成功、要么全失败"的操作：

| 操作 | 谁调谁 | 说明 |
|------|--------|------|
| 候选入池 | Lead Intelligence → Sales CRM | 战略人员勾选后在同一事务内创建 Company + Contact + Sales Lead |
| 认领/指派 | API → Sales CRM | 纯数据库操作，不需要等外部服务 |
| 销售离职 | IAM → Sales CRM | Strategic 一次命令内禁用登录、结束 Assignment、客户回原池，全部成功或全部回滚 |
| 接受建议 | API → Customer Analysis | 接受 AI 提出的 Profile 修改建议 |

### 5.2 异步协作（通过 Outbox 事件）

用于事务提交后的副作用：

| 事件 | 谁发出 | 谁消费 | 干什么 |
|------|--------|--------|--------|
| 销售线索创建 | Sales CRM | Analysis / Read Models | 触发首份分析报告 |
| 线索分配 | Sales CRM | Operation / Read Models | 更新工作台 |
| 邮件已发送 | Customer Operation | Sales CRM / Analysis | 自动推进 Pipeline 到 contacted |
| 会议已分析 | Customer Operation | Sales CRM / Analysis | 更新客户时间线 |
| 用户被禁用 | IAM | Read Models | 只刷新账号安全状态，不改变客户、任务或业务 Job |
| 销售已离职 | IAM + Sales CRM | Read Models / Notification | 回池已在同步事务完成，事件只刷新视图和通知 |

---

## 六、核心业务规则（Policy）

### 6.1 候选身份识别（两个候选是不是同一家公司）

优先级从高到低：
1. **域名精确匹配**（最可靠）
2. **法定名 + 国家相同**
3. **归一化名称 + 国家相同**
4. **低置信度相似**→ 不自动合并，进入人工审核

**绝不只按公司名就合并**——不同国家的同名公司太多了。

### 6.2 销售能不能认领这个线索

必须同时满足：
- 这个人是 Sales（Strategic 不能自己认领）
- 线索状态是 claimable
- 销售等级匹配（MA 销售才能领大客户）
- 区域策略允许（开启时区域也要匹配）
- 当前跟进的客户数还没达到容量上限

### 6.3 公司匹配（入池时是新建还是复用已有公司）

候选入池时，系统判断：
- 能找到已有 Company → 复用
- 找不到 → 新建 Company
- 不确定 → 人工判断

如果复用的 Company 已经有未关闭的 Sales Lead，不创建第二个，直接复用已有的。

### 6.4 Pipeline 推进规则

```
用户手动点击 → 同步调 Sales CRM Command（带版本号，冲突返回 409）
邮件/会议自动推进 → 通过 Outbox Event 消费（按事件 ID 幂等，只允许单调前进）
```

**关键**：邮件和会议不会让阶段倒退。比如已经到了 Meeting 阶段，再收到一封邮件不会倒回 contacted。

### 6.5 邮件发送安全规则

发送前必须检查：
- 操作人有这个 Sales Lead 的权限
- 收件人属于这个 Company
- 邮箱没有被退订
- 邮件状态是可以发送的
- 不是重复发送（相同的幂等键）

### 6.6 分配规则矩阵与 SLA（v3.5 新增）

Lead 进哪个池、多久之内必须首触，由一张 **Config-as-Code 的规则矩阵**决定（不建运行时规则表）：

- 维度：ICP 档（A≥80 / B 60-79.99）× 体量（大/中/小）× 6 大区 = **36 条规则**，外加 **2 条数据补全规则**（体量 unknown / 区域 unknown）
- 首触 SLA：A 档大客户 **24h**；其余 A 档及 B 档大/中客户 **24-48h**；小客户 **3 个工作日**
- 决策链确认 SLA：A 档大客户 48h、其余 3 个工作日，通过自动创建 follow_up_task 表达
- 矩阵带版本号，Lead 入池时在 `sales_lead.allocation_rule_version` 记录当时版本，**规则更新不回溯存量 Lead**

### 6.7 3 天未首触自动释放（v3.5 新增）

销售认领了 Lead 却**超过 3 个工作日没有首次触达**，定时 Job（`crm.auto_release_overdue.v1`，每小时扫描）会自动把 Lead 释放回池、通知原销售。事件复用 `crm.lead_released.v1`（原因码 `auto_release_no_first_touch`）。

边界：已首触的不释放；跟进中 14 天无活动**只提醒不释放**；T1-T3 时间衰减 Deferred。

### 6.8 登录锁定（v3.5 新增）

连续 **5 次**密码失败 → 账号锁定 **30 分钟**，到期首次认证自动恢复。锁定事件写审计日志并告警。配套新增账号管理 API（创建/禁用/启用/解锁/重置密码）。

### 6.9 数据补全池：unknown 分支（v3.5 新增）

ICP≥60 但体量评不出（unknown）或区域未知的 Lead 不进正式池，进**数据补全池**：区域已知的 `scale_unknown` 只对同区域 A 级销售可见；`region_unknown` 对全部 Sales 隐藏，仅 Strategic 和后台 Worker 可见。补全完成后允许**一次性**修正 adopted Scale，或修正区域×等级及其规则版本；区域已知但 Scale 仍 unknown 时转入对应区域 A 补全池——这是“入池资格快照不可变”的唯一例外（详见规范 §6.10）。

### 6.10 手动记录：17 点提取目录与批量确认（v3.5 新增）

手动记录（Manual Note）的 LLM 提取目标是一份"**四大维度 17 个信息点**"目录 v1（详见规范 §6.16：D1 公司与业务 4 点、D2 场景与方案 5 点、D3 商务与决策 4 点、D4 MEDDPICC 高频 4 维；清单待 PM 确认后修订）。

确认方式是**批量确认**：确认卡片默认整批采纳提取值，销售可展开逐条调整（accept/keep_original/edit）后一次提交。提取时会快照每个目标字段的版本号，确认时校验，被别人改过的项返回 409 冲突，绝不静默覆盖。

---

## 七、事件速查表

事件描述了"已经发生的事实"。所有事件都通过 Outbox 发布，保证不丢。

| 事件名 | 中文含义 | 谁发出 | 主要消费者 |
|--------|----------|--------|-----------|
| `lead.candidate_scored.v1` | 候选评分完成 | Lead Intelligence | 工作台刷新 |
| `crm.sales_lead_created.v1` | 销售线索入池 | Sales CRM | 分析报告、工作台 |
| `crm.lead_assigned.v1` | 线索已分配 | Sales CRM | 运营、工作台 |
| `crm.lead_released.v1` | 线索已释放 | Sales CRM | 运营、工作台 |
| `crm.lead_transferred.v1` | 线索已转交 | Sales CRM | 运营、工作台 |
| `crm.pipeline_changed.v1` | 销售阶段变更 | Sales CRM | 分析、工作台 |
| `analysis.report_generated.v1` | 分析报告生成 | Customer Analysis | 运营、工作台 |
| `analysis.suggestion_accepted.v1` | 分析建议被接受 | Customer Analysis | 工作台 |
| `engagement.email_sent.v1` | 邮件已发送 | Customer Operation | CRM推进、分析 |
| `engagement.email_replied.v1` | 邮件被回复 | Customer Operation | CRM推进、分析 |
| `engagement.meeting_analyzed.v1` | 会议分析完成 | Customer Operation | CRM推进、分析 |
| `engagement.task_completed.v1` | 任务已完成 | Customer Operation | 工作台 |
| `iam.user_disabled.v1` | 用户被安全禁用 | IAM | 只刷新账号状态，不改客户归属 |
| `iam.sales_departed.v1` | 销售已离职 | IAM + Sales CRM | 刷新战略视图、池统计和通知；回池已在同步事务完成 |
| **`engagement.email_opened.v1`（新增 v3.5）** | **邮件被打开** | **Customer Operation** | **CRM（I1 加分）、工作台** |
| **`engagement.email_clicked.v1`（新增 v3.5）** | **邮件链接被点击** | **Customer Operation** | **CRM（I1 加分）、工作台** |
| **`crm.dynamic_intent_bonus_applied.v1`（新增 v3.5）** | **动态意向加分已生效** | **Sales CRM** | **分析、运营、工作台** |
| **`sales.tier_change.v1`（Deferred）** | **销售等级变更** | **IAM** | **当前不发布、不消费** |
| **`sales.handover_completed.v1`（Deferred）** | **交接完成** | **IAM** | **当前不发布、不消费** |
| **`company.owner_change.v1`（Deferred）** | **客户归属转移（交接）** | **Sales CRM** | **当前不发布、不消费** |
| **`manual_note.confirmed.v1`（新增 v3.4）** | **手动记录确认** | **Customer Operation** | **分析、工作台** |
| **`manual_note.discarded.v1`（新增 v3.4）** | **手动记录弃用** | **Customer Operation** | **工作台** |

两点说明：v3.3 版的动态加分事件（挂在 Lead Intelligence 下）已作废，由 `crm.dynamic_intent_bonus_applied.v1` 取代（生产者改为 Sales CRM）；3 天未首触的自动释放**复用** `crm.lead_released.v1`（`reason_code=auto_release_no_first_touch` 区分），不另设事件。

---

## 八、账号变化、负向过滤与动态加分

### 8.1 等级调整（Deferred）

当前不提供晋升/降级 API、等级历史、审批或销售健康度。Sales 的 region/tier 在创建账号时配置；未来需要动态调整时再评审历史客户、容量和路由规则。

### 8.2 当前离职流程：Strategic 一键回原池

```text
active/disabled Sales
  → Strategic 点击“标记离职”
  → 同一事务：账号 departed + Session 撤销 + Assignment 结束 + Lead 回原池
```

关键细节：

- 没有申请、审批、交接待办或中间状态；
- active 或安全 disabled 的 Sales 都可以被正式标记离职；
- 离职后立即不能登录；
- 所有 active Assignment 以 `reason_code=sales_departed` 结束；
- Lead 清空 owner、变回 claimable，但保留入池时的区域、区域映射版本、销售等级和分配规则版本，所以回到原区域×等级池；
- User、Session、Assignment、Lead、Audit、Outbox 任一步失败则全部回滚；
- Disable 只处理安全登录，不释放客户；
- Claim/Assign/Transfer/Depart 都先锁 Sales User，再按稳定顺序锁 Lead/Assignment，避免离职并发时又产生新归属。

### 8.3 负向过滤和动态加分

搜索到的候选不是直接评分，先过一层"看能不能做"：

- X 类（排除）：完全没跨境场景、跟 eSIM 无关、已拒绝半年没变 → 不进主流程
- D 类（暂存）：规模太小、没联系方式 → 放一边，等补数据或季度复查

触达后的加分（v3.5 起累计在 **Sales Lead** 上，不在候选上）：

| 行为 | 加分 | 数据源 |
|------|:--:|------|
| I1 打开邮件 / 点击链接 | +2 | 邮件 Provider Webhook（`engagement.email_opened/email_clicked.v1`），每封邮件合计最多 +2 |
| I2 回复但只做普通询问 | +5 | 回复意图 `intent_level=product_question` |
| I3 明确问价格/套餐/分成/API/合作模式 | +8 | `intent_level=pricing` |
| I4 愿意开会、要求方案、转给负责人 | +10 | `intent_level=interested` |

规则要点：

- 动态总分 = `min(100, adopted ICP 静态总分 + 累计加分)`，加分由 Sales CRM 消费 engagement 事件时执行
- 静态 B 级（60-79）Lead 动态总分 ≥80 → 升级为 **A4**，**保持原 owner 不重新分配**
- 升级时发布 `crm.dynamic_intent_bonus_applied.v1`，Consumer **立即**创建 Analysis Run + 跟进 Task（不是延迟 24 小时的定时任务）
- A4 **只升级一次**，后续加分不再重复触发

静态 A1-A3 细分在**入池时**按 adopted ICP 计算并快照在 `sales_lead.a_segment`（不满足为空）；候选侧不落库，只按当前 ICP 派生展示。

### 8.4 A 类客户不是铁板一块

A 级客户分四种：

| 类型 | 是什么 | 谁跟 |
|------|------|------|
| A1 战略大客户 | 总分≥85 且规模维度≥80%权重；或年国际订单≥10万 / 企业客户≥500 / 月活≥100万 任一满足 | MA 主跟 + 区域负责人协同 |
| A2 高适配客户 | 总分≥80 且跨境场景维度≥80%权重，且增值服务/数据触达维度≥80%权重 | 资深销售主跟 |
| A3 技术可快速试点 | 总分≥75 且技术接入维度≥80%权重 | 方案销售 + 产品支持，2-4 周 POC |
| A4 高意向动态升级 | B 级但触达后动态总分加到 80 以上 | 保持原 owner，立即触发分析 + 跟进 Task |

## 九、给开发人员的模块边界检查清单

每次提交代码前检查：

1. 这次改动属于哪个模块？
2. 有没有写其他模块的表？（不允许）
3. 有没有新增跨模块依赖？是同步还是异步？
4. 有没有新增业务状态？状态转换都合法吗？
5. 并发安全吗？用了乐观锁吗？
6. 幂等吗？同一个请求重复提交会出错吗？
7. 外部 Provider 调用在数据库事务外吗？（必须在事务外！）
8. 保存了规则版本、Prompt 版本、Schema 版本吗？
9. 删除了旧代码路径吗？还是又叠加了一层兼容？

**以下行为直接打回**：
- Claim 时创建 Company（入池时才创建）
- 把 Candidate 当 Sales Lead 用
- 把 ICP 评分当客户规模用
- 新增六维 ICP
- 让 Analysis 或 Operation 模块复制 Company 主数据
- 用审计日志替代 Pipeline 历史
- 用公司名称做关联键
- 在前端判断 owner、grade、tier 或 status
- 模块间走 localhost HTTP 互调
