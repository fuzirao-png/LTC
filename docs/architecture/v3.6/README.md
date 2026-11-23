# LTC Agent 架构文档

> 版本：v3.6
> 日期：2026-07-20
> 状态：目标架构评审基线
> v3.6：当前范围收敛为对话搜索唯一入口（Apollo 为内部 Provider）；账号类型统一为 Sales/Strategic；Strategic 可直接标记 Sales 离职并原子释放客户回原区域×等级池；安全禁用不再释放客户；S4/S5 整体转入 Deferred，当前只启用 S1/S2/S3 四维 ICP
> v3.5（历史记录，冲突口径已由 v3.6 覆盖）：曾定义 S4 临时权重并将全部离职交接 Deferred；其余批量确认、动态意向、数据补全、负向过滤、分配规则与 SLA、自动释放、IAM 管理和区域参考表修订继续保留
> v3.4：整合手动记录功能 PRD v1.0、多账号登录与销售管理 PRD v1.0、ICP 评分规则 v1.0、区域国家对照表 v5
> 适用范围：开发阶段重构，可重建 PostgreSQL 数据库，可删除未完成和已弃用代码

本目录是 LTC 项目的唯一架构事实源。当前代码用于证明业务意图和可复用能力，不代表现有目录、SQLite 表、内存 Store、静态数组和临时 HTTP 服务必须被保留。

当前架构基线不包含人员安排和时间计划。项目排期应在架构和数据库评审通过后单独编写。

## 核心结论

1. 对话搜索是唯一用户侧线索收集入口；Apollo、网页搜索及未来数据源只作为内部 Provider，不增加独立入口。
2. 搜索证据、候选观察和全局候选必须分开建模。
3. 四维 ICP 是唯一业务匹配评分。
4. 客户规模 D1-D3 是独立模型，只用于确定 MA/SA/A 销售池。
5. Strategic 勾选候选后，先创建 Company、Contact 和 Sales Lead 进入资源池。
6. Sales Claim 或 Strategic Assign 只创建负责人关系，不在认领时创建 Company；两者都必须匹配目标 Sales 的区域×等级和容量，当前无跨池 Override。
7. Customer Analysis 不再计算旧六维 ICP，只读取四维 ICP 快照。
8. PostgreSQL 是唯一业务事实源；SQLite、JSON 文件、内存 Store 和前端静态数组退出正式链路。
9. 采用前后端分离、FastAPI 模块化单体和独立 Worker，不建设业务微服务。
10. Dashboard 是只读查询模型，Meeting Analysis 是 Customer Operation 下的 Worker 能力。
11. 后续支持“战略指令 + 季度线索收集 Campaign + 区域目标比例”，但不进入当前实现范围。
12. 手动记录的提取确认采用批量确认：默认整批采纳，销售可展开逐条调整后一次提交。
13. 动态意向加分作用于 Sales Lead（触达发生在分配后），可将 B 级 Lead 升级为 A4；Candidate 侧静态 A1-A3 由当前 ICP 派生不落库，Sales Lead 入池时在 `a_segment` 保存 adopted ICP 对应快照。
14. 客户规模允许 unknown（证据不足）：区域已知但体量 unknown 的 Lead 只对同区域 A 级销售可见；区域未知的 Lead 对 Sales 隐藏，补全后按区域×等级入池。
15. 当前只有 Sales 和 Strategic 两类账号；Sales 只能看到本人区域×等级匹配的池，Strategic 可将 Sales 标记离职。
16. 离职无需申请或审批：账号立即失去登录权限，名下 active Assignment 原子结束，Lead 保留入池时区域×等级、区域映射版本和分配规则版本快照并回到对应 claimable 池。
17. 安全禁用只撤销登录和 Session，不改变客户归属；active/disabled Sales 都可由 Strategic 执行 Depart，只有该命令触发离职回池。

## 规则源对齐

当 PRD、专项维护表和编排文档冲突时，以以下口径为准（已与管理层确认）：

| 规则 | 权威口径 | 被取代的旧口径 |
|---|---|---|
| ICP 维度 | 当前仅启用 S1/S2/S3 四维：S1 40/30/20/10、S2/S3 35/25/25/15 | S4 酒店航司、S5 APP 工作室整体 Deferred；旧 Excel 五维和 v3.5 临时四维权重均不进入当前实现 |
| 动态意向加分 | +2/+5/+8/+10（I1-I4），总分封顶 100 | 主 PRD 的 +2/+5/+15/+30 为旧版 |
| 负向过滤 | X1-X6（排除 X / 暂存 D） | 主 PRD 的 X1-X10 减分制为旧版 |
| 区域模型 | 6 大区 205 个国家/地区（对照表 v5）；分配规则表已同步中东，共 36 条正式规则 + 2 条补全规则 | 主 PRD、旧 ICP 工作簿与编排文档的 5 区域为旧版 |
| 时间衰减 T1-T3 | Deferred，当前不实现 | 主 PRD F1.2.8 |
| 手动记录确认 | 批量确认 | 手动记录 PRD §六“冲突时逐条单独确认” |
| 账号与销售管理 | 当前实现 Sales/Strategic、多账号登录、区域×等级池可见性、Strategic 直接离职回池；等级调整、申请审批、交接待办、销售健康度等仍 Deferred | 多账号登录与销售管理 PRD 的完整销售管理流程 |

“后续/Deferred”章节只用于约束兼容边界和未来演进方向。当前开发 Agent 不得据此生成 Migration、数据库表、Router、Job、测试桩、空 Service 或前端菜单；只有管理层将该能力正式纳入当前范围并更新本目录后才允许实现。

## 阅读顺序

| # | 文档 | 内容 | 主要读者 |
|---|---|---|---|
| 1 | `01-架构总览.md` | 业务理解、现状审查、目标拓扑、模块边界、状态机 | 所有人 |
| 2 | `02-前后端分离设计.md` | Web/API/Worker 边界、前端结构、后端分层和依赖规则 | 前端、后端 |
| 3 | `03-DDD领域驱动设计.md` | 领域语言、Context Map、聚合、Policy、Command、Event（**规范**） | 后端、Agent 开发 |
| 3b | `03b-DDD中文讲解.md` | 模块边界、业务语言、协作关系、Policy、Event 的中文讲解（**讲解**） | 所有人、新同事 |
| 4 | `04-数据模型设计.md` | 独立数据库评审稿、表和字段、约束、索引、迁移规则（**规范**） | 后端、数据库评审人 |
| 4b | `04b-数据模型中文讲解.md` | 42 张表、每个字段的业务含义、设计 FAQ 的中文讲解（**讲解**） | 所有人、新同事 |
| 5 | `05-API接口契约.md` | `/api/v1` 接口、命令、错误码、幂等和并发 | 前端、后端、测试 |
| 6 | `06-异步任务设计.md` | Job、Attempt、Progress、Worker Lease、Outbox、Provider | 后端、Agent 开发 |

## v3.6 工程基线

架构评审结论已经下沉为以下可执行工程产物，后续重构必须以同一版本成套使用：

| 产物 | 路径 | 用途 |
|---|---|---|
| Docker 运行入口 | `../../../compose.yaml` | 本地/CI 的 Web、API、PostgreSQL 和验收服务编排 |
| 重构实施说明 | `../v3.6-rebuild-guide.md` | 新旧边界、当前落地状态和后续纵向切片顺序 |
| PostgreSQL 初始 Migration | `../../../db/migrations/0001_v3_6_initial.sql` | PostgreSQL 16 空库建表、约束、索引和只读视图 |
| 区域国家 Seed | `../../../db/seeds/0001_region_country_v5.sql` | v5 的 6 区 205 国家/地区，幂等整体替换 |
| OpenAPI 契约 | `../../../contracts/openapi/LTC_OpenAPI_v3.6.yaml` | 当前 `/api/v1` 路径、请求响应、枚举和错误模型 |
| 自动化契约测试 | `../../../tests/contract/test_v3_6_repository.py` | 校验文档、SQL、OpenAPI、模块边界和当前范围 |
| PostgreSQL 一键验收 | `../../../scripts/verify_database.py` | Docker PG16 Migration、Seed、负向约束、并发和备份恢复 |
| 数据库验收说明 | `../../../db/README.md` | 自动化覆盖及数据库/应用层责任边界 |
| 受控基线校验和 | `../../../contracts/v3.6.sha256` | 接收方校验架构、数据库与 API 产物无非预期漂移 |

根目录的 v1.x/v2.0 SQL、OpenAPI 和历史说明只作迁移溯源，不再是开发事实源。任何表、字段或接口变更，都必须先更新本目录的规范文档，再同步上述 v3.6 产物和契约测试。

## 快速查找

| 任务 | 阅读内容 |
|---|---|
| 理解端到端业务 | 01 §1、§5 |
| 理解四维 ICP 和客户规模 | 01 §2 |
| 开发前端 | 02 + 05 |
| 开发对话搜索和富化 | 03 Lead Intelligence + 04 Lead 表 + 06 |
| 开发客户分配 | 03 Sales CRM + 04 CRM 表 + 05 Sales CRM API |
| 开发客户分析 | 03 Customer Analysis + 04 Analysis 表 + 05 Analysis API |
| 开发邮件、会议和任务 | 03 Customer Operation + 04 Engagement 表 + 05、06 |
| 审查数据库和字段 | 04 §1–§16 |
| 审查数据库冗余、反规范化和设计一致性 | 04 §17–§18 |
| 理解并发 Claim | 03 Claim Policy + 04 事务要求 + 05 Claim API |
| 理解模块间事件 | 03 Event + 06 Outbox |

## 当前代码的使用方式

### 可复用

- `LTC/clue_agent/`：对话搜索、流式执行、网页搜索、候选抽取、联系人补全、D1-D4 富化、客户规模分层。
- `LTC/customer-analysis-agent/`：Profile、MEDDPICC、五模块报告、Sales Guide 的输出结构。
- `LTC/customer-operation-agent/`：邮件生成、翻译、回复意图和任务概念。
- `LTC/meeting-analysis-service/`：音视频处理、分片、并行 ASR、转写、摘要和 Fallback。
- `LTC/Customer Allocation/`：Sales/Strategic 权限动作、Tier 和容量概念。
- `LTC/index.html` 与 `LTC/src/*.vue`：页面和交互需求参考。

### 必须删除或重写

- 手工上传、B 端旧来源、GEO、C 端爬虫和 Apollo 独立/占位入口；Apollo Provider Adapter 保留在对话搜索内部；
- 客户分析六维 ICP；
- 静态 `CLAIMABLE_LEADS`；
- 固定 `li_ming` owner 和临时 `claim_*` ID；
- 前端 88/75 ICP 阈值和基于 ICP 推导 MA/SA/A；
- SQLite 双库、JSON 历史文件和内存 Store；
- 8787 Node 业务编排和模块间 localhost HTTP；
- 重复兼容 API。

## 文档维护规则

- 模块、表、API、状态和事件名称必须在六份文档中一致。
- API 实现前先更新 `05-API接口契约.md`。
- 表或字段变更先更新 `04-数据模型设计.md`。
- 新增跨模块依赖先更新 `03-DDD领域驱动设计.md`。
- 不以减少表数量为目标，也不允许为“企业级感”增加无业务用途的表。
- Prompt 和评分规则当前采用 Config-as-Code；只有确认需要在线发布时再设计运行时配置表。
- 标记为“后续/Deferred/当前不实现”的内容不得进入当前代码、DDL、API 或验收测试。
