# LTC AI Native Sales Platform

当前仓库是 LTC AI Native 销售管理平台，采用 Python/FastAPI 模块化单体 + Vue 3 前端。

## 模块

| 模块 | 路径 | 类型 |
|------|------|------|
| IAM | `apps/api/src/ltc/modules/iam/` | Supporting |
| Lead Intelligence | `apps/api/src/ltc/modules/lead_intelligence/` | Core |
| Sales CRM | `apps/api/src/ltc/modules/sales_crm/` | Core |
| Customer Analysis | `apps/api/src/ltc/modules/customer_analysis/` | Core |
| Customer Operation | `apps/api/src/ltc/modules/customer_operation/` | Core |
| Worker | `apps/worker/src/ltc_worker/` | Background job processing |
| Observability | `apps/api/src/ltc/platform/observability/` | Telemetry, anomaly detection, Agent KPI |
| Web Frontend | `apps/web/` | Vue 3 + Vite |

## 本地启动

```bash
# 初始化数据库并启动 API、Worker、前端、Redis 和 Collector
make up
```

访问:
- 前端: http://localhost:5173
- API: http://localhost:8000
- API Docs: http://localhost:8000/api/v1/docs

### 测试账户

所有账户密码均为 `123456`：

| 角色 | 用户名 | 类型 | 层级 | 区域 |
|------|--------|------|------|------|
| 管理员 | `boss.admin` | strategic | — | — |
| 运营 | `strategy.ops` | strategic | — | — |
| 销售主管 | `lin.wei` | sales | MA | EA |
| 销售 | `chen.jie` | sales | A | SEA |
| 销售 | `zhang.wei` | sales | SA | NA |

### 完整流程测试

**线索收集 → 候选 → 评估 → 晋升 → 分析：**

1. 以 `strategy.ops` 登录，调用 `POST /api/v1/lead-search-runs` 创建搜索任务
2. Worker 处理搜索管道（`lead.search_pipeline.v1`），产出 scored/eligible 候选
3. 以 `strategy.ops` 登录，调用 `POST /api/v1/lead-candidates:select` 晋升候选
4. 以匹配 tier 的销售登录（如 `chen.jie`），调用 `POST /api/v1/sales-leads/{lead_id}:claim`
5. 调用 `POST /api/v1/companies/{company_id}/analysis-runs` 触发分析报告生成

Compose 默认启动 `crm`、`analysis` 和 `media` 队列消费者。线索搜索仍使用默认的 API `inline` 模式。

### 会议转写与首页加载

- 在 `.env` 配置 `LTC_ASR_BASE_URL`、`LTC_ASR_API_KEY` 和 `LTC_ASR_MODEL` 后，可从会议沟通页上传音视频。API 和 Worker 共用 `ltc_meeting_media` 卷。升级旧容器前，需备份并迁移旧容器 `/tmp/ltc/meetings` 中仍需访问的录音到该卷，保持数据库中的路径有效。
- Worker 将已完成分片写入 PostgreSQL。重启后，过期租约约 30 秒后可回收，重试按 `transcript_ref` 复用分片。若请求已到达 ASR、但结果尚未提交，重试仍会发送同一 `Idempotency-Key`，去重取决于 ASR 提供方是否支持该请求头。
- `LTC_ASR_MAX_PARALLEL_REQUESTS` 限制每个 Worker 进程的在途请求数，`LTC_ASR_TARGET_LATENCY_SECONDS` 控制降载阈值。Collector 导出 `asr_concurrency_limit`、`asr_in_flight`、`asr_pending`、`asr_request_duration` 和 `media_queue_pending`。
- Collector 保留决策窗口内的 ERROR 与慢链路，并对其余链路抽样 5%。重试或排队超过 60 秒的任务使用链接到原请求的独立 trace。默认将采样后的 trace 和指标写入 `ltc_telemetry` 卷，等待窗口和慢链路阈值可用 `LTC_TRACE_DECISION_WAIT` 和 `LTC_TRACE_SLOW_MS` 配置。[OpenTelemetry 尾部采样文档](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/processor/tailsamplingprocessor/README.md)
- 销售登录后预取业绩页的线索数据，运营账号预取线索收集首页。Redis 缓存有效期为 30 秒。使用 `start.sh` 或 `start.bat` 时，配置 `LTC_REDIS_URL` 可启用本地缓存。Redis 不可用时查询回退到 PostgreSQL。

### 数据存储

- PostgreSQL: `localhost:55432`, 库名 `ltc`, 用户 `ltc`
- 初始化: `./scripts/init_database_container.sh`（自动执行迁移 + 种子数据）
- 迁移: `db/migrations/`（按序号执行，禁止修改已分发的 `0001`）
- 种子数据: `db/seeds/`（首次启动自动加载）

| 文件 | 内容 | 行数 |
|------|------|------|
| `0001_region_country_v5.sql` | 区域-国家对照表 (205行, 6大区) | — |
| `0002_customer_operation_demo.sql` | 客户运营演示: 邮件/会议/任务 | 1 公司, 1 联系人, 2 邮件, 1 会议 |
| `0003_lead_demo_leads.sql` | 线索候选: ICP + 体量评估 | 20 候选 (TMC/FINTECH/OTA/OTHER, 大/中/小) |

### 迁移文件

| 文件 | 说明 |
|------|------|
| `0001_v3_6_initial.sql` | 初始 schema: 42 张核心表 + 约束 + 索引 |
| `0002_email_mailbox_monitor.sql` | 邮箱监控表 |
| `0003_email_mailbox_monitor_secret_value.sql` | 邮箱密钥字段 |
| `0004_relax_analysis_run_constraints.sql` | 放宽 analysis_run 约束（inline 模式兼容） |
| `0005_telemetry_events.sql` | v3.3: ai_event, tool_event, lead_lifecycle_event 三张遥测表 |
| `0006_agent_kpi_functions.sql` | v3.3: Agent 质量评分 SQL 函数 |

### 数据埋点与可观测性 (v3.3)

可观测性平台位于 `apps/api/src/ltc/platform/observability/`：

| 组件 | 文件 | 说明 |
|------|------|------|
| AI 事件 | `domain/telemetry_events.py` | AiEvent / ToolEvent / LifecycleEvent 值对象 |
| 生命周期代码 | `domain/lifecycle_codes.py` | 25 个 EVT-xx 事件代码常量 |
| 事件发射器 | `application/event_emitter.py` | EventEmitter 服务（ai_call / tool_call / lifecycle） |
| 异常检测 | `application/anomaly_detector.py` | P1-P4 四级异常检测引擎 |
| Telemetry Writer | `infrastructure/telemetry_writer.py` | TelemetryWriter 协议 + Postgres/内存实现 |

**AI 事件已嵌入的适配器：**
- `lead_intelligence/infrastructure/llm.py` — IcpScoreAgent
- `customer_analysis/infrastructure/adapters.py` — CustomerAnalysisAgent
- `customer_operation/infrastructure/llm_adapter.py` — EmailGenerationAgent
- `meeting_analysis/infrastructure/summary_adapter.py` — MeetingSummaryAgent

**Agent KPI 查询示例：**
```sql
SELECT ltc.compute_agent_quality_score('CustomerAnalysisAgent', '2026-07-01');
-- → 73.23 (A 级)
SELECT ltc.compute_agent_grade('CustomerAnalysisAgent', '2026-07-01');
-- → 'A'
```

**重新初始化数据库（清空所有数据）：**
```bash
docker compose down -v   # 删除 volume
docker compose up -d     # 重新创建并加载种子数据
```

## 架构

详见 `docs/architecture/v3.6/`

### 关键目录

```text
apps/api/src/ltc/modules/iam/               — 认证、账号管理、离职回池
apps/api/src/ltc/modules/lead_intelligence/ — 对话搜索、候选、四维ICP评分
apps/api/src/ltc/modules/sales_crm/          — 公司、销售线索、分配、管道
apps/api/src/ltc/modules/customer_analysis/  — 客户画像、MEDDPICC、分析报告
apps/api/src/ltc/modules/customer_operation/ — 邮件、会议、跟进任务
apps/worker/src/ltc_worker/                  — 后台任务处理器（14种job类型）
apps/api/src/ltc/platform/observability/     — 遥测、异常检测、Agent考核
apps/web/src/features/                       — Vue 前端页面
```

## 变更规则

- 架构或业务范围变化：先修改 `docs/architecture/v3.6/`
- API 变化：同步 OpenAPI 契约
- 数据库变化：新增 Migration，禁止修改已分发的 `0001`
- 新模块只能写自己拥有的表，跨模块同步走 Application Port/UoW，异步走 Outbox
- `.env`、Token、Provider Key、数据库密码和生产连接串禁止提交
