# Customer Operation 后端实现纲要

> 基准文档：PRD v1.1 §7.11 + 前后端分离设计 v3.6 + DDD 四层架构
> 参考模块：`customer_analysis`（已实现的完整 DDD 模块）
> 前端已有接口：`operationApi.ts` + `meetingApi.ts`
> 所属模块：`customer_operation`（表所有权见 `registry.py` §5）

---

## 一、模块定位

| 项 | 内容 |
|---|---|
| 职责 | 邮件生成/发送/回复识别、会议上传/转写/摘要、跟进任务、客户活动日志 |
| 拥有的表 | `email_message`、`email_attachment`、`email_delivery_attempt`、`email_suppression`、`meeting`、`meeting_segment`、`follow_up_task`、`customer_activity`、`manual_note` |
| 依赖（允许） | Sales CRM → `Company`/`Contact`/`Lead` 访问 Port；Customer Analysis → `Report` 读取 Port |
| 禁止写 | Company/Contact 主数据、Profile/MEDDPICC、重新计算 ICP |

### PRD §7.11 对应的 Agent（8 个）

| # | Agent | 主模型 | v0 状态 |
|---|---|---|---|
| 8 | EmailContextBuilder | 无（字段拼装）| 必做 |
| 9 | EmailGenerationAgent | GPT-5.4-mini | 必做 |
| 10 | EmailDeliveryAgent | SendGrid + Resend | 必做 |
| 11 | EmailIntentAgent | DeepSeek-Pro | 必做 |
| 12 | MeetingIngestionAgent | 无（接收）| 必做 |
| 13 | ASRAgent | Whisper-1 | 必做 |
| 14 | MeetingSummaryAgent | GPT-5.5 | 必做 |
| 15 | FollowupStrategyAgent | GPT-5.4-mini | 必做 |

---

## 二、目录结构

完全复刻 `customer_analysis` 的四层结构：

```text
apps/api/src/ltc/modules/customer_operation/
  __init__.py                                   # 已有
  interfaces/
    __init__.py                                  # 已有（空）
    router.py                                    # [新建] FastAPI Router
    schemas.py                                   # [新建] Request/Response Pydantic schemas
  application/
    __init__.py                                  # 已有（空）
    service.py                                   # [新建] 应用层 Use Case
    ports.py                                     # [新建] Port 接口定义
  domain/
    __init__.py                                  # 已有（空）
    customer_activity.py                         # 已有
    email_message.py                             # [新建] EmailMessage 实体
    meeting.py                                   # [新建] Meeting 实体
    follow_up_task.py                            # [新建] FollowUpTask 实体
    errors.py                                    # [新建] 领域错误
  infrastructure/
    __init__.py                                  # 已有（空）
    postgres_repository.py                       # [新建] PostgreSQL 仓库
    email_context_builder.py                     # [新建] EmailContextBuilder 实现
    llm_adapter.py                               # [新建] OpenAI-compatible LLM 适配器
    email_provider_adapter.py                    # [新建] SendGrid/Resend 适配器
    asr_adapter.py                               # [新建] Whisper 适配器
    bootstrap.py                                 # [新建] DI 容器
```

---

## 三、核心 API 端点（对接前端已有调用）

| 方法 | 路径 | 对应前端方法 | 说明 |
|---|---|---|---|
| `POST` | `/api/email/generate` | `operationApi.generateEmail()` | 基于 email_context 生成邮件草稿 |
| `POST` | `/api/email/translate` | `operationApi.translateEmail()` | 邮件翻译（中→英/日） |
| `POST` | `/api/email/send` | `operationApi.sendEmail()` | 通过 SendGrid/Resend 发送 |
| `GET` | `/api/email/history` | `operationApi.getEmailHistory()` | 按客户名查邮件历史 |
| `POST` | `/api/meeting/upload` | `meetingApi.uploadMeeting()` | 上传录音文件 |
| `GET` | `/api/meeting/history` | `meetingApi.getHistory()` | 按客户名查会议历史 |
| `GET` | `/api/meeting/job` | `meetingApi.getJob()` | 查询转写/摘要任务状态 |
| `POST` | `/api/meeting/delete` | `meetingApi.deleteRecord()` | 删除会议记录 |
| `GET` | `/api/customers/{id}/operations` | `operationApi.getCustomerOperations()` | 客户运营全景（公司+联系人+邮件+会议+任务） |
| `GET` | `/internal/customers/export` | `operationApi.exportCustomers()` | 客户列表导出 |

---

## 四、领域模型

### 4.1 EmailMessage

```python
@dataclass(frozen=True)
class EmailMessage:
    email_id: UUID
    company_id: UUID
    contact_id: UUID | None
    direction: Literal["outbound", "inbound"]
    subject: str
    body: str
    body_preview: str | None
    status: Literal["draft", "sending", "sent", "delivered", "opened", "clicked", "replied", "bounced", "failed"]
    intent_level: Literal["interested", "pricing", "product_question", "not_interested", "unsubscribe"] | None
    ai_generated: bool
    model_name: str | None
    locale: str
    sendgrid_msg_id: str | None
    in_reply_to: UUID | None
    version: int
    created_at: datetime
    updated_at: datetime
```

### 4.2 Meeting

```python
@dataclass(frozen=True)
class Meeting:
    meeting_id: UUID
    company_id: UUID
    title: str | None
    meeting_time: datetime
    duration_seconds: int
    audio_url: str | None
    transcript_status: Literal["pending", "transcribing", "transcribed", "failed"]
    transcript: str | None
    transcript_confidence: float | None
    summary: JsonObject | None          # 结构化摘要 JSON
    asr_provider: str | None
    summary_model: str | None
    version: int
    created_at: datetime
    updated_at: datetime
```

### 4.3 FollowUpTask

```python
@dataclass(frozen=True)
class FollowUpTask:
    task_id: UUID
    company_id: UUID
    description: str
    status: Literal["pending", "done", "cancelled"]
    due_date: datetime | None
    source: Literal["system", "manual"]  # system = Agent 生成
    source_event: str | None             # "email.replied" / "meeting.summarized"
    version: int
    created_at: datetime
```

### 4.4 CustomerActivity（已有）

保持现有 `customer_activity.py`，增加 repository 写入逻辑。

---

## 五、跨模块数据流（PRD §7.10）

### 数据流 1：客户分析 → 邮件生成

| 来源 | 落点 | 用途 |
|---|---|---|
| `analysis_report.market_analysis` | `email_context.analysis_overview` | 邮件开头市场背景 |
| `analysis_report.company_analysis` | `email_context.company_brief` | 公司业务关联 |
| `analysis_report.competitor_analysis` | `email_context.competitor_context` | 差异化切入点 |
| `analysis_report.product_suggestion` | `email_context.recommended_products` | 推荐方案 |
| `company.scenario_id` | `email_context.template_id` | 选 S1-S5 模板 |
| `company.icp_grade` | `email_context.tone` | A 级=积极 |
| `customer_profile.meddpicc` | `email_context.decision_chain` | 决策链策略 |

### 数据流 4：会议摘要 → 邮件生成（会后跟进）

| 来源 | 落点 |
|---|---|
| `meeting.summary.action_items` | `email_context.latest_action_items` |
| `meeting.summary.next_step` | `email_context.latest_next_step` |
| `meeting.summary.sentiment` | `email_context.latest_sentiment` |

---

## 六、邮件生成流程（核心用例）

```
销售点击"生成邮件"
  → EmailContextBuilder 从多表拼装 50+ 字段 context
    ├── Customer Analysis Report Read Port → market/company/competitor/product
    ├── Sales CRM Read Port → company/contact 信息
    └── Email Repository → 最近邮件历史
  → EmailGenerationAgent 调 LLM 生成 subject + body
  → 返回 draft 供销售编辑
  → 销售编辑后点"发送"
  → EmailDeliveryAgent 调 SendGrid/Resend
  → webhook 回调更新 delivery status
```

### 降级（PRD §9.5.4 模块 5）

```
LLM 超时(>15s) → Flash (<5s) → 上封邮件模板替换 → 手动写
SendGrid 失败 → 保存草稿 + 队列重试3次 → Resend fallback
```

---

## 七、会议处理流程

```
销售上传录音
  → MeetingIngestionAgent 存 S3/OSS
  → ASRAgent 调 Whisper-1 转写
  → MeetingSummaryAgent 调 GPT-5.5 出结构化摘要
    ├── pain_points_mentioned
    ├── buying_signals
    ├── action_items
    ├── next_step
    └── sentiment
  → FollowupStrategyAgent 生成跟进任务
```

### 降级（PRD §9.5.4 模块 6）

```
Whisper 超时 → 切片30min并行 → 手动上传 transcript
Whisper 配额超限 → 本地 whisper.cpp fallback
```

---

## 八、与 customer_analysis 的架构对齐

| 维度 | customer_analysis（参考） | customer_operation（待建） |
|---|---|---|
| Router | `build_customer_analysis_router(service)` | `build_customer_operation_router(service)` |
| 挂载 | `app.include_router(router, prefix=api_prefix)` | 同上 |
| DI | `build_local_container()` → `CustomerAnalysisContainer` | `build_operation_container()` → `CustomerOperationContainer` |
| Repository | `PostgresCustomerAnalysisRepository` | `PostgresCustomerOperationRepository` |
| LLM | `OpenAICompatibleReportGenerator` | 复用同一个模式，用 operation 专用 prompt |
| Port | `ReportGeneratorPort` | `EmailGeneratorPort`、`ASRPort`、`DeliveryPort` |
| 依赖注入 | service 注入 repository + ports | 同上 |

---

## 九、实施顺序

| 优先级 | 内容 | 依赖 |
|---|---|---|
| **P0-1** | Domain 模型：`email_message.py`、`meeting.py`、`follow_up_task.py`、`errors.py` | 无 |
| **P0-2** | Application Ports + Service（纯 Python，无 DB/LLM） | P0-1 |
| **P0-3** | PostgreSQL Repository（建表 + CRUD） | P0-1，需 DB schema |
| **P0-4** | EmailContextBuilder（字段拼装，无 LLM） | P0-2 + Customer Analysis 读 Port |
| **P0-5** | Router + Schemas（interface 层） | P0-2 |
| P1-1 | LLM 适配器（EmailGeneration + Summary + Intent） | P0-4，需 LLM 环境变量 |
| P1-2 | Email Delivery（SendGrid/Resend） | P0-3，需 API key |
| P1-3 | ASR（Whisper-1） | P0-3，需 API key |
| P1-4 | FollowupStrategyAgent | P1-1 |
| P1-5 | DI 容器 + main.py 挂载 | P0-5 + P1-1 |
| P2 | Meeting segment 表、manual_note、email_attachment | P0-3 |
| P3 | webhook 回调（SendGrid event → update status）、SSE 进度 | P1-2 |

---

## 十、数据库表清单

| 表名 | 对应模型 | 关键字段 |
|---|---|---|
| `email_message` | EmailMessage | email_id, company_id, contact_id, direction, subject, body, status, intent_level, ai_generated, sendgrid_msg_id, in_reply_to, version |
| `email_attachment` | EmailAttachment | attachment_id, email_id, filename, content_type, size_bytes, storage_url |
| `email_delivery_attempt` | DeliveryAttempt | attempt_id, email_id, provider, status, response_code, started_at, completed_at |
| `email_suppression` | EmailSuppression | suppression_id, email_address, reason, created_at |
| `meeting` | Meeting | meeting_id, company_id, title, meeting_time, duration_seconds, audio_url, transcript_status, transcript, transcript_confidence, summary |
| `meeting_segment` | MeetingSegment | segment_id, meeting_id, start_offset, end_offset, speaker_role, text |
| `follow_up_task` | FollowUpTask | task_id, company_id, description, status, due_date, source, source_event, version |
| `customer_activity` | CustomerActivity | 已有（activity_id, company_id, lead_id, activity_type, direction, subject, body, ...） |
| `manual_note` | ManualNote | note_id, company_id, content, author_user_id, version |
