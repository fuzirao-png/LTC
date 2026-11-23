# LTC Agent 全模块后端实现纲要

> 基准文档：PRD v1.1 §7 + 前后端分离设计 v3.6 + DDD 四层架构
> 参考模块：`customer_analysis`（已实现的完整 DDD 模块，~4,200 行）
> 状态：customer_analysis 已完整实现；另外 5 个模块均为空骨架

---

## 零、架构总览

### 0.1 模块与表所有权（来自 registry.py）

| 模块 | 表数 | 状态 | v0 优先级 |
|---|---|---|---|
| **iam** | 3 (user_account, auth_session, ref_region_country) | 空骨架 | **P0**（多账号登录必需） |
| **lead_intelligence** | 12 (lead_search_run → lead_negative_filter_result) | 空骨架 | **P0**（线索链路必需） |
| **sales_crm** | 5 (company, contact, sales_lead, lead_assignment, lead_stage_transition) | 空骨架 | **P0**（客户主数据必需） |
| **customer_analysis** | 5 (customer_profile, customer_meddpicc_dimension, analysis_run, analysis_report, analysis_suggestion) | **已完整实现** ✅ | — |
| **customer_operation** | 9 (email_message, email_attachment, email_delivery_attempt, email_suppression, meeting, meeting_segment, follow_up_task, customer_activity, manual_note) | 骨架 + 1 域模型 | **P0**（邮件+会议必需） |
| **read_models** | 0（无自有表，纯查询） | 空骨架 | **P1**（查询优化） |
| **平台** | 8 (job*, idempotency_record, outbox_event, external_event, audit_log, media_asset) | DB 已有 / registry 定义 | **P0**（基础设施） |

### 0.2 DDD 四层架构模式（所有模块统一遵循）

```
modules/<name>/
  interfaces/
    router.py      — FastAPI Router, 使用 build_<name>_router(service) 工厂
    schemas.py     — Request/Response Pydantic models
  application/
    service.py     — 用例协调器（领域对象 + Port 调用）
    ports.py       — Protocol 接口定义（Repository/Generator/Job port）
  domain/
    models.py      — 纯数据类（frozen=True, version 乐观锁, to_dict()）
    errors.py      — 领域错误（基类 + NotFound/VersionConflict/InvalidState）
  infrastructure/
    postgres_repository.py — PostgreSQL 持久化（乐观锁 WHERE version=$N）
    bootstrap.py   — DI 容器 + build_local_container() 工厂
    adapters.py    — 外部适配器（LLM/API/邮件/ASR）
```

### 0.3 全局规则（所有模块共享）

1. **version 字段**：所有可变表都有 `version bigint NOT NULL DEFAULT 0`，所有 UPSERT 带 `WHERE version = $prev_version`
2. **Idempotency-Key**：所有 mutation 端点接受 `Idempotency-Key` header（幂等写入）
3. **If-Match**：所有 PATCH 端点接受 `If-Match` header（乐观锁 version）
4. **Soft delete**：用 `status` 字段标记废弃，不做物理删除
5. **跨模块只读**：模块 A 读模块 B 的数据通过 Port（Protocol），不能直接写模块 B 的表
6. **错误码**：ResourceNotFoundError → 404, VersionConflictError → 409, InvalidStateError → 409, 其他 → 400
7. **Router 挂载**：`build_*_router(service)` 工厂函数 → `app.include_router(router, prefix=api_prefix)`
8. **DI**：`build_local_container()` → dataclass Container(service, repository, contexts)
9. **API prefix**：v3.6 端点 `/api/v1/...`；遗留端点 `/api/...`（兼容前端过渡期）

### 0.4 平台表（不属于任何业务模块）

| 表 | 用途 | 谁写 |
|---|---|---|
| `job` + `job_attempt` + `job_progress_event` | 异步任务队列 | Task Runtime（平台） |
| `idempotency_record` | 幂等键去重 | Task Runtime |
| `outbox_event` | 模块间事件 | 各模块 service |
| `external_event` | webhook 回调事件 | 平台适配器 |
| `audit_log` | 操作审计 | 平台中间件 |
| `media_asset` | 文件存储引用 | 各模块（会议录音、邮件附件等） |

---

## 一、IAM 模块（Identity & Access Management）

### 1.1 定位

| 项 | 内容 |
|---|---|
| 职责 | 用户认证（JWT 双 token）、角色权限（sales/strategic 双类型）、区域/国家 ref 数据 |
| 拥有的表 | `user_account`、`auth_session`、`ref_region_country` |
| 依赖 | 无（平台基础层，不依赖任何业务模块） |
| 对应 PRD | §6.1 双视角（sales vs boss）、`多账号登录编排_v1.md` |
| 前端 API | `allocationApi.ts` — `me()`、`login()`、`logout()` |

### 1.2 DB 表字段摘要

**user_account** (3 表中最核心)：
- user_id, username, password_hash, display_name, email
- account_type: `sales` | `strategic`
- sales 专用：sales_tier (`MA`/`SA`/`A`), region_code, capacity_limit
- status: `active` | `disabled` | `departed`
- 安全字段：failed_login_attempts, locked_until, token_version
- 离职字段：departed_at, departed_by, departure_reason (status='departed' 时必须填)
- version, created_at, updated_at

**auth_session**：
- session_id, user_id (FK → user_account), refresh_token_hash
- issued_token_version (与 user_account.token_version 对齐，token 吊销用)
- ip_address, user_agent, expires_at
- revoked_at / revoke_reason (logout/disabled/departed/security)
- last_seen_at

**ref_region_country**：
- country_code (PK, ISO 2-letter), country_name, region_code, subregion, default_timezone

### 1.3 目录结构（待建文件）

```text
apps/api/src/ltc/modules/iam/
  interfaces/
    router.py                  # [新建] FastAPI Router
    schemas.py                 # [新建] Pydantic schemas
  application/
    service.py                 # [新建] AuthService + UserService
    ports.py                   # [新建] Port 接口
  domain/
    models.py                  # [新建] User, AuthSession, TokenPair
    errors.py                  # [新建] IAM 领域错误
  infrastructure/
    postgres_repository.py     # [新建] PostgreSQL 用户/会话仓库
    jwt_adapter.py             # [新建] JWT (access + refresh) 签发/验证
    password_hasher.py         # [新建] bcrypt/argon2 哈希
    bootstrap.py               # [新建] DI 容器
```

### 1.4 领域模型

```python
# domain/models.py

@dataclass(frozen=True)
class User:
    user_id: UUID
    username: str
    password_hash: str      # bcrypt hash, 永远不会通过 API 返回
    display_name: str
    email: str | None
    account_type: Literal["sales", "strategic"]
    sales_tier: Literal["MA", "SA", "A"] | None   # 仅 sales
    region_code: str | None                         # 仅 sales
    capacity_limit: int | None                      # 仅 sales
    status: Literal["active", "disabled", "departed"]
    failed_login_attempts: int
    locked_until: datetime | None
    token_version: int       # 递增可吊销所有 refresh token
    last_login_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime

    def lock_account(self) -> "User": ...
    def record_login_success(self) -> "User": ...
    def record_login_failure(self, max_attempts: int = 5) -> "User": ...
    def increment_token_version(self) -> "User": ...

@dataclass(frozen=True)
class AuthSession:
    session_id: UUID
    user_id: UUID
    refresh_token_hash: str
    issued_token_version: int
    ip_address: str | None
    user_agent: str | None
    expires_at: datetime
    revoked_at: datetime | None
    revoke_reason: str | None

    def is_active(self) -> bool: ...
    def revoke(self, reason: str) -> "AuthSession": ...

@dataclass(frozen=True)
class TokenPair:
    access_token: str       # JWT, 15min TTL
    refresh_token: str      # opaque, 7d TTL
    token_type: str = "Bearer"
    expires_in: int = 900
```

### 1.5 API 端点设计

| 方法 | 路径 | 说明 | 前端对应 |
|---|---|---|---|
| `POST` | `/api/v1/auth/login` | 登录 → TokenPair + set-cookie | `allocationApi.login()` |
| `POST` | `/api/v1/auth/logout` | 退出（revoke refresh token） | `allocationApi.logout()` |
| `POST` | `/api/v1/auth/refresh` | refresh token → 新 TokenPair | — |
| `GET` | `/api/v1/auth/me` | 当前用户信息 | `allocationApi.me()` |
| `GET` | `/api/v1/users` | 用户列表（strategic 可见全部, sales 仅自己） | — |
| `POST` | `/api/v1/users` | 创建用户（strategic only） | — |
| `PATCH` | `/api/v1/users/{id}` | 更新用户（status/sales_tier/region） | — |
| `GET` | `/api/v1/regions` | ref_region_country 完整列表 | — |

### 1.6 JWT 认证中间件

```python
# 在 infrastructure/ 或 platform/ 中实现全局中间件
# 所有 /api/v1/* 请求自动解析 Authorization: Bearer <token>
# 解析后注入 request.state.current_user: User

# Access token payload:
{
  "sub": "user_id",
  "username": "...",
  "account_type": "sales|strategic",
  "token_version": 3,
  "iat": ..., "exp": ...
}

# Refresh token: 存 auth_session 表，每次 refresh 轮换
```

### 1.7 权限校验

| 端点类别 | 校验规则 |
|---|---|
| `/api/v1/auth/*` | 无需认证 |
| `GET /api/v1/users` | strategic: 全量；sales: 仅自己 |
| `POST/PATCH /api/v1/users` | strategic only |
| 所有业务端点（customer_analysis 等） | 需有效 access token |
| 遗留端点 `/api/*` | 暂时跳过认证（v0 过渡期） |

### 1.8 实施顺序

| 优先级 | 内容 | 说明 |
|---|---|---|
| **P0-1** | domain/models.py + errors.py | 数据类先行 |
| **P0-2** | infrastructure/password_hasher.py + jwt_adapter.py | 纯工具，不依赖 DB |
| **P0-3** | infrastructure/postgres_repository.py | DB CRUD |
| **P0-4** | application/service.py | 用例（login/refresh/logout/CRUD user） |
| **P0-5** | interfaces/router.py + schemas.py | 端点 |
| **P0-6** | infrastructure/bootstrap.py | DI 容器 |
| **P0-7** | main.py 挂载 + 全局 auth 中间件 | 集成 |

---

## 二、Lead Intelligence 模块（线索智能）

### 2.1 定位

| 项 | 内容 |
|---|---|
| 职责 | 线索发现（5 来源搜索）、线索富化（公司+决策人补全）、线索去重、ICP 评分、客户体量分层、负向过滤 |
| 拥有的表 | 12 张：`lead_search_run` → `lead_negative_filter_result` |
| 依赖（只读） | sales_crm → Company/Contact 写入 Port；customer_analysis → ICP 评分结果 |
| 对应 PRD | §7 模块 01 线索收集 + 模块 02 线索分析；Agent 1-3 (线索层) + Agent 4-5 (分析层) |
| 前端 API | `leadApi.ts` — 6 个方法（含流式 NDJSON search） |

### 2.2 DB 表关系（12 张表分为 3 组）

**搜索执行组**（3 表）：
- `lead_search_run` — 一次搜索任务（query_text, scene_code S1-S3, target_count, status）
- `search_provider_execution` — 每个 provider 的执行记录（web_search/apollo, request_hash）
- `search_evidence` — 搜索命中证据（url, snippet, content_hash）

**候选处理组**（4 表）：
- `lead_candidate` — 候选公司记录（company_name, domain, source, status）
- `candidate_observation` — 候选观察（证据片段序列）
- `candidate_evidence` — 候选证据（关联到 search_evidence 或 enrichment_evidence）
- `candidate_contact` — 候选联系人（name, title, email, linkedin_url, confidence）

**富化与评分组**（5 表）：
- `lead_enrichment_run` — 一次富化运行（provider_code, status）
- `enrichment_evidence` — 富化证据（enrichment_type, field, raw_value, confidence）
- `lead_icp_assessment` — ICP 评分结果（scenario_id S1-S5, 4 维度分, total_score, grade A/B/C/D/X）
- `customer_scale_assessment` — 客户体量分层（tier 大/中/小, employee_count, revenue_range）
- `lead_negative_filter_result` — 负向过滤结果（filter_rule X1-X10, triggered, reason）

### 2.3 目录结构（待建文件）

```text
apps/api/src/ltc/modules/lead_intelligence/
  interfaces/
    router.py                       # [新建] FastAPI Router
    schemas.py                      # [新建] Pydantic schemas
  application/
    service.py                      # [新建] LeadService
    ports.py                        # [新建] Port 接口
  domain/
    models.py                       # [新建] LeadSearchRun, LeadCandidate, ICPScore, ...
    errors.py                       # [新建]
  infrastructure/
    postgres_repository.py          # [新建] PostgreSQL 仓库（12 表）
    search_provider_adapter.py      # [新建] Exa/Apollo API 适配器
    enrichment_adapter.py           # [新建] Apollo 决策人查找 + ScrapingBee
    icp_scorer.py                   # [新建] 规则引擎（5 场景 4 维度，纯 Python）
    dedup_engine.py                 # [新建] 去重引擎（Levenshtein + 模糊匹配）
    llm_adapter.py                  # [新建] LLM ICP 评分（GPT-5.4-mini fallback 到规则）
    bootstrap.py                    # [新建] DI 容器
```

### 2.4 领域模型

```python
# 核心模型（12 张表对应 12 个 dataclass）

@dataclass(frozen=True)
class LeadSearchRun:
    search_run_id: UUID
    dialogue_session_id: str | None   # 多轮对话关联
    query_text: str
    search_mode: Literal["company_only", "contact_only", "both"]
    target_count: int                  # 1-200
    scene_code: Literal["S1", "S2", "S3"]
    orchestration_profile: str         # 编排配置名
    status: Literal["queued", "running", "completed", "partial", "failed", "cancelled"]
    evidence_count: int
    candidate_count: int
    enriched_count: int
    scored_count: int
    current_job_id: UUID
    # ...
    version: int

@dataclass(frozen=True)
class LeadCandidate:
    candidate_id: UUID
    search_run_id: UUID
    company_name: str
    normalized_name: str
    domain: str | None
    website: str | None
    country_code: str | None
    industry_code: str | None
    description: str | None
    source_code: str                   # exa/apollo/manual/scraping
    status: Literal["new", "enriching", "enriched", "scored", "duplicate", "rejected", "promoted"]
    dedup_key: str | None
    dedup_master_id: UUID | None       # 指向去重后的主 candidate
    promoted_to_company_id: UUID | None  # 提升到 company 表后的 ID
    version: int
    # ...

@dataclass(frozen=True)
class LeadIcpAssessment:
    icp_assessment_id: UUID
    candidate_id: UUID
    scenario_id: Literal["S1", "S2", "S3", "S4", "S5"]
    dimension_scores: JsonObject       # {"D1": 40, "D2": 30, "D3": 15, "D4": 0}
    total_score: float                 # 0-100
    grade: Literal["A", "B", "C", "D", "X"]
    reason: str                        # ≤200 字
    model_name: str | None             # LLM 模型名或 "rule_engine"
    prompt_version: str | None
    assessment_mode: Literal["llm", "rule", "manual"]
    version: int
    # ...
```

### 2.5 核心业务流程

```
[管理面板创建搜索] → POST /api/v1/lead-discovery/search
  → LeadSearchRun (status=queued)
  → job 队列 → search_provider_execution (Exa + Apollo 并行)
  → search_evidence 写入
  → lead_candidate 写入 (status=new)
  → [自动触发] enrichment job
  → LeadEnrichmentAgent → candidate_contact + enrichment_evidence
  → [自动触发] dedup job
  → LeadDedupAgent → 模糊匹配 → 标记 duplicate/合并
  → [自动触发] ICP scoring job
  → ICPScoreAgent → lead_icp_assessment (LLM → rule fallback)
  → [自动触发] tier + negative filter
  → DealTierAgent → customer_scale_assessment
  → 负向过滤 → lead_negative_filter_result
  → 升级到 analysis: POST /api/v1/lead-discovery/.../promote-to-analysis
  → 写入 sales_crm.company + sales_crm.sales_lead
```

### 2.6 流式搜索（前端 leadApi.ts 已定义）

```
POST /api/v1/lead-discovery/dialogue-search/stream
  Content-Type: application/json
  Response: text/plain (NDJSON)

每行格式：
{"type": "trace", "step": "search", "provider": "exa", "results_found": 25}
{"type": "trace", "step": "enrich", "candidate": "Acme Corp", "contacts_found": 3}
{"type": "reply", "results": [...], "total": 25, "requires_user_input": false}
```

### 2.7 实施顺序

| 优先级 | 内容 | 说明 |
|---|---|---|
| **P0-1** | domain/models.py（12 个 dataclass）+ errors.py | 数据类先行 |
| **P0-2** | infrastructure/icp_scorer.py + dedup_engine.py | 纯规则引擎，无外部依赖 |
| **P0-3** | infrastructure/postgres_repository.py | 12 表 CRUD |
| **P0-4** | application/ports.py + service.py（搜索/富化/评分/去重） | 用例层 |
| **P0-5** | infrastructure/search_provider_adapter.py | Exa + Apollo API |
| **P0-6** | infrastructure/enrichment_adapter.py | Apollo 决策人 + ScrapingBee |
| **P0-7** | interfaces/router.py + schemas.py | REST + NDJSON stream |
| **P0-8** | infrastructure/llm_adapter.py | LLM ICP 评分（后于 rule engine） |
| **P0-9** | infrastructure/bootstrap.py + main.py 挂载 | 集成 |

---

## 三、Sales CRM 模块

### 3.1 定位

| 项 | 内容 |
|---|---|
| 职责 | 客户主数据（Company/Contact）、销售线索（Lead）、线索分配（Assignment）、阶段流转（Stage Transition） |
| 拥有的表 | 5 张：`company`、`contact`、`sales_lead`、`lead_assignment`、`lead_stage_transition` |
| 依赖（只读） | customer_analysis → Profile/MEDDPICC 读 Port；lead_intelligence → candidate 来源 |
| 对应 PRD | §6.5 客户分配 + §7 模块 03 客户分配；Agent 7 (AssignmentAgent) |
| 前端 API | `allocationApi.ts` — claimable/mine/all/claim + ingest events |

### 3.2 DB 表关系

**company** — 核心主数据表：
- company_id (PK), origin_candidate_id (FK → lead_candidate)
- company_name, normalized_company_name, legal_name, primary_domain, website
- country_code, region_code (NA/EA/SEA/EU/ME/OTHER), city, industry_code (TMC/TRAVEL_OTA/FINTECH/OTHER)
- employee_count, company_intro
- lifecycle_status: `prospect` | `active_customer` | `inactive` | `archived`
- version, created_by, created_at, updated_at, archived_at

**contact** — 联系人：
- contact_id (PK), company_id (FK → company)
- full_name, normalized_name, title, department, relationship_role (decision_maker/influencer/executor/general_employee)
- priority (P1/P2/P3), primary_email, email_status, phone, linkedin_url
- source (candidate/manual/operation)
- last_contacted_at, status (active/inactive/archived)

**sales_lead** — 销售线索（lead_intelligence.candidate 升级后的可分配对象）：
- lead_id (PK), company_id (FK), source_candidate_id (FK → lead_candidate)
- adopted_icp_assessment_id, adopted_scale_assessment_id
- required_sales_tier (MA/SA/A), pool_region_code
- allocation_status: `claimable` | `claimed` | `archived`
- pipeline_stage: `new` → `contacted` → `engaged` → `meeting` → `proposal` → `won`/`lost`/`dormant`
- current_owner_user_id (FK → user_account)
- current_assignment_started_at, first_touch_at, sla_due_at
- dynamic_bonus_points, a_segment (A1/A2/A3/A4)

**lead_assignment** — 分配历史：
- assignment_id, lead_id, company_id, from_user_id, to_user_id
- assignment_type (claim/assign/reassign/release), reason, version

**lead_stage_transition** — 阶段流转审计：
- transition_id, lead_id, from_stage, to_stage, triggered_by, reason

### 3.3 目录结构（待建文件）

```text
apps/api/src/ltc/modules/sales_crm/
  interfaces/
    router.py                     # [新建] FastAPI Router
    schemas.py                    # [新建] Pydantic schemas
  application/
    service.py                    # [新建] CRMService
    ports.py                      # [新建] Port 接口
  domain/
    models.py                     # [新建] Company, Contact, SalesLead, Assignment, StageTransition
    errors.py                     # [新建]
  infrastructure/
    postgres_repository.py        # [新建] PostgreSQL 仓库（5 表）
    bootstrap.py                  # [新建] DI 容器
```

### 3.4 领域模型

```python
@dataclass(frozen=True)
class Company:
    company_id: UUID
    company_name: str
    normalized_company_name: str
    primary_domain: str | None
    website: str | None
    country_code: str | None
    region_code: str | None       # NA/EA/SEA/EU/ME/OTHER
    city: str | None
    industry_code: str | None     # TMC/TRAVEL_OTA/FINTECH/OTHER
    company_intro: str | None
    employee_count: int | None
    lifecycle_status: Literal["prospect", "active_customer", "inactive", "archived"]
    version: int
    created_by: UUID | None
    archived_at: datetime | None
    # ...

@dataclass(frozen=True)
class Contact:
    contact_id: UUID
    company_id: UUID
    full_name: str
    title: str | None
    relationship_role: Literal["decision_maker", "influencer", "executor", "general_employee"] | None
    priority: Literal["P1", "P2", "P3"] | None
    primary_email: str | None
    phone: str | None
    linkedin_url: str | None
    source: Literal["candidate", "manual", "operation"]
    status: Literal["active", "inactive", "archived"]
    version: int
    # ...

@dataclass(frozen=True)
class SalesLead:
    lead_id: UUID
    company_id: UUID
    source_candidate_id: UUID
    adopted_icp_assessment_id: UUID
    adopted_scale_assessment_id: UUID
    required_sales_tier: Literal["MA", "SA", "A"]
    pool_region_code: str | None
    allocation_status: Literal["claimable", "claimed", "archived"]
    pipeline_stage: Literal["new", "contacted", "engaged", "meeting", "proposal", "won", "lost", "dormant"]
    current_owner_user_id: UUID | None
    sla_due_at: datetime | None
    version: int

    def claim(self, user_id: UUID) -> "SalesLead": ...
    def release(self, reason: str) -> "SalesLead": ...
    def transition_stage(self, to_stage: str, reason: str) -> "SalesLead": ...
```

### 3.5 API 端点设计

**REST v3.6 端点**：

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/v1/companies` | 公司列表（分页+筛选） |
| `GET` | `/api/v1/companies/{id}` | 公司详情 |
| `POST` | `/api/v1/companies` | 创建公司 |
| `PATCH` | `/api/v1/companies/{id}` | 更新公司 |
| `GET` | `/api/v1/companies/{id}/contacts` | 公司联系人列表 |
| `POST` | `/api/v1/contacts` | 创建联系人 |
| `PATCH` | `/api/v1/contacts/{id}` | 更新联系人 |

**Lead Pool 端点（前端的 allocationApi.ts）**：

| 方法 | 路径 | 说明 | 前端调用 |
|---|---|---|---|
| `GET` | `/api/v1/lead-pool/claimable` | 可领取线索 | `allocationApi.claimable()` |
| `GET` | `/api/v1/lead-pool/mine` | 我的线索 | `allocationApi.mine()` |
| `GET` | `/api/v1/lead-pool/all` | 所有线索（strategic） | `allocationApi.all()` |
| `POST` | `/api/v1/lead-pool/{id}/claim` | 领取线索 | `allocationApi.claim(leadId)` |

**线索升级端点（lead_intelligence → sales_crm）**：

| 方法 | 路径 | 说明 | 前端调用 |
|---|---|---|---|
| `GET` | `/api/v1/lead-discovery/validation-companies` | 待验证公司 | `leadApi.listValidationCompanies()` |
| `GET` | `/api/v1/lead-discovery/analysis-companies` | 分析中公司 | `leadApi.listAnalysisCompanies()` |
| `POST` | `/api/v1/lead-discovery/.../promote-to-analysis` | 升级到 sales_lead | `leadApi.promoteToAnalysis()` |

### 3.6 客户分配 Agent（AssignmentAgent — PRD Agent 7）

核心逻辑（v0 纯规则，不上 ML）：

```
POST /lead-pool/{lead_id}/claim
  → 校验 sales_tier 匹配（user.sales_tier ≥ lead.required_sales_tier）
  → 校验容量（user 当前 claimed 数量 < capacity_limit）
  → SELECT ... FOR UPDATE 锁定 lead 行
  → 乐观锁检查 version
  → UPDATE allocation_status='claimed', current_owner_user_id=$user_id
  → INSERT INTO lead_assignment (type='claim')
  → INSERT INTO lead_stage_transition (from_stage='new', to_stage='contacted')
  → 返回更新后的 lead
```

### 3.7 实施顺序

| 优先级 | 内容 | 说明 |
|---|---|---|
| **P0-1** | domain/models.py（5 个模型）+ errors.py | 数据类先行 |
| **P0-2** | infrastructure/postgres_repository.py | 5 表 CRUD + claim 冲突处理 |
| **P0-3** | application/ports.py + service.py | 用例（CRUD + claim/release/transition） |
| **P0-4** | interfaces/router.py + schemas.py | REST + lead-pool 端点 |
| **P0-5** | infrastructure/bootstrap.py + main.py 挂载 | 集成 |

---

## 四、Customer Operation 模块（客户运营）

> 已有详细计划在 `docs/customer_operation_backend_plan.md`。本节为精简版，重点标注与 PRD §7.10/§7.11 对齐的关键更新。

### 4.1 定位

| 项 | 内容 |
|---|---|
| 职责 | 邮件生成/发送/回复识别、会议上传/转写/摘要、跟进任务、客户活动日志 |
| 拥有的表 | 9 张：`email_message`、`email_attachment`、`email_delivery_attempt`、`email_suppression`、`meeting`、`meeting_segment`、`follow_up_task`、`customer_activity`、`manual_note` |
| 依赖（只读） | sales_crm → Company/Contact；customer_analysis → Report |
| 对应 PRD | §7.10 数据流 1-4 + §7.11 Agent 8-15 |
| 前端 API | `operationApi.ts` + `meetingApi.ts` |

### 4.2 与已有计划的更新点

**已有计划** `customer_operation_backend_plan.md` 是正确的。以下为关键对齐：

1. **email_context 50+ 字段**（PRD §7.10 数据流 1）：EmailContextBuilder 必须从 `analysis_report`（5 段 text + sales_guidance）、`company`（scenario_id/icp_grade）、`meddpicc`（decision_chain）拼装 50+ 字段 JSON

2. **会议摘要反哺链路**（PRD §7.10 数据流 3）：`meeting.summary` JSON 中的 `pain_points_mentioned`/`buying_signals`/`competitors_mentioned` → 触发 `customer_analysis` 生成 `analysis_report v2`（新 version_no，不覆盖 v1）

3. **已有 `customer_activity.py`** 保持不变，只增加 repository 写入逻辑

4. **前端接口完全对齐**：operationApi 和 meetingApi 已在前端定义好，后端 router 的路径/参数/响应格式必须严格匹配

### 4.3 文件清单（待建/待修改）

```text
apps/api/src/ltc/modules/customer_operation/
  interfaces/
    router.py                       # [新建] ~400 行，10 个端点
    schemas.py                      # [新建] ~100 行
  application/
    service.py                      # [新建] ~300 行
    ports.py                        # [新建] ~50 行
  domain/
    customer_activity.py            # 已有（47 行），保持不变
    email_message.py                # [新建] EmailMessage 实体
    meeting.py                      # [新建] Meeting 实体
    follow_up_task.py               # [新建] FollowUpTask 实体
    errors.py                       # [新建]
  infrastructure/
    postgres_repository.py          # [新建] ~400 行，9 表 CRUD
    email_context_builder.py        # [新建] ~150 行，50+ 字段拼装
    llm_adapter.py                  # [新建] OpenAI-compatible
    email_provider_adapter.py       # [新建] SendGrid/Resend
    asr_adapter.py                  # [新建] Whisper-1 API
    bootstrap.py                    # [新建] DI 容器
```

---

## 五、Read Models 模块（读模型）

### 5.1 定位

| 项 | 内容 |
|---|---|
| 职责 | 跨模块查询优化（JOIN 多表）、Dashboard 数据聚合、经营驾驶舱投影 |
| 拥有的表 | 无（query-only，不持有任何业务表） |
| 依赖 | 可读所有模块的表（通过 DB view 或 JOIN） |
| 对应 PRD | §6.2 销售面板 + §6.3 管理面板 + §7 模块 07 销售面板 + 模块 08 管理面板 |
| 前端 API | `legacy_sales_dashboard` / `legacy_boss_dashboard`（当前在 customer_analysis router 中，应迁移到此） |

### 5.2 目录结构

```text
apps/api/src/ltc/modules/read_models/
  interfaces/
    router.py                     # [新建] Read-only 查询端点
  queries/
    sales_dashboard.py            # [新建] 销售面板查询
    boss_dashboard.py             # [新建] 老板驾驶舱查询
    customer_operations_view.py   # [新建] 客户运营全景查询
    pipeline_funnel.py            # [新建] 销售漏斗查询
```

### 5.3 查询端点设计

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/v1/dashboard/sales` | 销售面板（我的业绩、待办、客户列表） |
| `GET` | `/api/v1/dashboard/boss` | 老板驾驶舱（经营指标、团队产能、Agent 监控） |
| `GET` | `/api/v1/customers/{id}/operations` | 客户运营全景（公司+联系人+邮件+会议+任务） |
| `GET` | `/api/v1/pipeline/funnel` | 销售漏斗（各 stage 数量+金额） |
| `GET` | `/api/v1/customers/export` | 客户列表导出（CSV） |

### 5.4 查询实现方式

- **简单查询**：直接 JOIN 2-3 表，返回 dict
- **复杂聚合**：PostgreSQL VIEW（在 DB migration 中预建）
- **现有 legacy 端点**：从 `customer_analysis/router.py` 逐步迁移到 read_models
  - `GET /api/sales/dashboard` → `GET /api/v1/dashboard/sales`
  - `GET /api/boss/dashboard` → `GET /api/v1/dashboard/boss`

### 5.5 实施顺序

| 优先级 | 内容 | 说明 |
|---|---|---|
| P1-1 | queries/sales_dashboard.py | 销售面板聚合 |
| P1-2 | queries/boss_dashboard.py | 老板驾驶舱 |
| P1-3 | queries/customer_operations_view.py | 客户运营全景 |
| P1-4 | interfaces/router.py | 查询端点 |
| P2 | 从 customer_analysis router 迁移 legacy dashboard 端点 | 清退遗留 |

---

## 六、跨模块集成方案

### 6.1 main.py 最终形态

```python
def create_app(settings: AppSettings | None = None) -> FastAPI:
    runtime_settings = settings or get_settings()
    app = FastAPI(...)

    # IAM (P0 — 最先挂载，因为其他模块需要 auth 中间件)
    iam_container = build_iam_container(...)
    app.include_router(
        build_iam_router(iam_container.service),
        prefix=runtime_settings.api_prefix,
    )

    # Sales CRM (P0 — 客户主数据)
    crm_container = build_crm_container(connection_factory=...)
    app.include_router(
        build_crm_router(crm_container.service),
        prefix=runtime_settings.api_prefix,
    )

    # Lead Intelligence (P0 — 线索)
    lead_container = build_lead_container(
        connection_factory=...,
        crm_service=crm_container.service,   # write Port for promote
    )
    app.include_router(
        build_lead_router(lead_container.service),
        prefix=runtime_settings.api_prefix,
    )

    # Customer Analysis (已有)
    analysis_container = build_local_container(...)
    app.include_router(
        build_customer_analysis_router(analysis_container.service),
        prefix=runtime_settings.api_prefix,
    )

    # Customer Operation (P0)
    operation_container = build_operation_container(
        connection_factory=...,
        crm_service=crm_container.service,
        analysis_service=analysis_container.service,
    )
    app.include_router(
        build_customer_operation_router(operation_container.service),
        prefix=runtime_settings.api_prefix,
    )

    # Read Models (P1)
    read_router = build_read_models_router(connection_factory=...)
    app.include_router(read_router, prefix=runtime_settings.api_prefix)

    return app
```

### 6.2 跨模块数据流契约（不允许模块 A 直接写模块 B 的表）

| 流 | 来源模块 | 目标模块 | 通过 | 事件 |
|---|---|---|---|---|
| 线索 → CRM | lead_intelligence | sales_crm | `promoteToAnalysis()` → CRMService.create_company() | `lead.promoted` |
| CRM → 分析 | sales_crm | customer_analysis | `upsert_context()` → analysis context cache | `customer.assigned` |
| 分析 → 邮件 | customer_analysis | customer_operation | EmailContextBuilder 读 Report | `report.generated` |
| 会议 → 分析 | customer_operation | customer_analysis | analysis v2 refresh | `meeting.summarized` |
| 会议 → 邮件 | customer_operation | customer_operation | EmailContextBuilder（同模块内） | 销售点击按钮 |

### 6.3 数据流 1 实现要点（客户分析 → 邮件生成）

```python
# customer_operation/infrastructure/email_context_builder.py

class EmailContextBuilder:
    """Pure data assembly — no LLM, no side effects.
    Reads from analysis, CRM, and operation tables through Ports."""

    def build(self, company_id: UUID, contact_id: UUID,
              purpose: Literal["first_touch", "reply_followup", "meeting_followup"]
              ) -> EmailContext:
        # Source 1: Customer Analysis Report Read Port
        report = self.analysis_port.get_current_report(company_id)
        analysis_overview = report.get("report_payload", {}).get("market", {})

        # Source 2: Sales CRM Read Port
        company = self.crm_port.get_company(company_id)
        contact = self.crm_port.get_contact(contact_id)

        # Source 3: Email History (own module)
        recent_emails = self.email_repo.list_by_company(company_id, limit=10)

        # Assembly: 50+ field email_context
        return EmailContext(
            # from analysis_report (PRD §7.10 数据流 1)
            analysis_overview=self._flatten(analysis_overview),
            company_brief=report.get("report_payload", {}).get("company", {}),
            competitor_context=report.get("report_payload", {}).get("competitor", {}),
            recommended_products=report.get("report_payload", {}).get("product", {}),
            next_strategy=report.get("sales_guide_payload", {}),
            # from company
            template_id=company.scenario_id or "S1",
            tone="assertive" if company.icp_grade == "A" else "standard",
            # from meddpicc
            decision_chain=self._decision_chain_snapshot(company_id),
            # from recent emails
            recent_context=[e.summary for e in recent_emails[:5]],
            # from contact
            recipient_name=contact.full_name,
            recipient_title=contact.title,
            # ...
        )
```

---

## 七、全局实施路线图

### 7.1 优先级矩阵

| 阶段 | 内容 | 依赖 | 预估工作量 | 并行度 |
|---|---|---|---|---|
| **Phase 0** | IAM domain + JWT 中间件 | 无 | 2-3 天 | 可与 Phase 1 并行 |
| **Phase 1** | Sales CRM domain + repository + router | 无（除了 user FK） | 3-4 天 | 可与 Phase 0 并行 |
| **Phase 2** | Lead Intelligence domain + service + router | Sales CRM (promote) | 4-5 天 | 需要 Phase 1 完成 |
| **Phase 3** | Customer Operation domain + service + router | Sales CRM + Customer Analysis | 5-7 天 | 需要 Phase 1 完成 |
| **Phase 4** | Read Models queries + dashboard | 所有模块 | 2-3 天 | 最后 |
| **Phase 5** | 集成测试 + main.py 挂载 + 全链路调通 | Phase 0-4 | 2-3 天 | — |

### 7.2 文件统计

| 模块 | 待建 .py 文件数 | 预估代码行数 | 难度 |
|---|---|---|---|
| IAM | ~10 | ~1,200 | 中（安全关键） |
| Lead Intelligence | ~12 | ~2,500 | 高（12 表 + 流式 + 多 Agent） |
| Sales CRM | ~8 | ~1,500 | 中（5 表 + 分配状态机） |
| Customer Operation | ~12 | ~2,500 | 高（9 表 + 多外部 API） |
| Read Models | ~5 | ~600 | 低（纯查询） |
| **总计** | **~47** | **~8,300** | — |

### 7.3 参考模式速查

每个模块的第一个文件对照 customer_analysis 的同名文件写：
- `domain/models.py` ← `customer_analysis/domain/models.py` (446 行)
- `domain/errors.py` ← `customer_analysis/domain/errors.py` (24 行)
- `application/service.py` ← `customer_analysis/application/service.py` (674 行)
- `infrastructure/postgres_repository.py` ← `customer_analysis/infrastructure/postgres_repository.py` (561 行)
- `infrastructure/bootstrap.py` ← `customer_analysis/infrastructure/bootstrap.py` (53 行)
- `interfaces/router.py` ← `customer_analysis/interfaces/router.py` (860 行)
- `interfaces/schemas.py` ← `customer_analysis/interfaces/schemas.py` (68 行)

---

## 八、v3.2 前端原型差异分析（2026-07-22 原型 vs 当前计划）

> 原型文件：`platform_framework_prototype-v3.2-20260722.html`（6155 行）
> 基准：本文档 §0-§7 + `customer_operation_backend_plan.md`

### 8.0 原型导航结构

**Sales 侧边栏（李明）**：
| 视图 ID | 面包屑 | 说明 |
|---|---|---|
| `dashboard` | 我的业绩 | 指标卡 + 客户列表 |
| `lead-assign` | 客户分配 | 资源池 + 我的线索 |
| `customer-analysis` | 客户分析 | 公司卡 + 画像结构 |
| `customer-mgmt` | 客户运营 | 6 阶段进度条 |
| `db-cases` | 案例库 | 23 条成交案例 |
| `db-scripts` | 话术库 | 28 条话术模板 |

**CEO 侧边栏（Alex）**：
| 视图 ID | 面包屑 | 说明 |
|---|---|---|
| `ceo-dashboard` | 经营驾驶舱 | 营收/利润/漏斗/Agent健康度 |
| `ceo-lead-collect` | 线索收集Agent | 对话式搜索 + 批量入库 |
| `ceo-lead-analyze` | 线索分析Agent | 总线索库 + 分析报告 |
| `ceo-lead-assign` | 客户分配 | 分配监控 + 销售排名 |
| `ceo-sales-mgmt` | 销售管理 | 离职交接 + 销售名册 |

### 8.1 缺口 #1：画像结构（Structured Profile）— Customer Analysis 模块

**原型表现**：`view-customer-analysis` 中每个公司卡片展开后显示 2 列结构：
- 左列「客户视角」：关注点 / 合作方 / 觉得我们如何（3 个文本区）
- 右列「最新资讯」：时间线形式展示关键动态

**当前计划缺漏**：
- `CustomerProfile` 模型（§2.4）有 13 个 text 字段但缺少「关注点」「合作方」「觉得我们如何」这三项
- 没有「最新资讯」时间线数据结构

**后端需补充**：

```
customer_profile 表新增列：
  - key_concerns: text               — 关注点（客户视角第一部分）
  - partners_involved: text          — 合作方（客户视角第二部分）
  - customer_perception: text        — 觉得我们如何（客户视角第三部分）

新建表 customer_news_item：
  - news_id: UUID PK
  - company_id: UUID FK → company
  - title: text                     — 资讯标题
  - source: text                    — 来源
  - url: text                       — 原文链接
  - occurred_at: date               — 发生日期
  - summary: text                   — 摘要
  - version: int
  - created_at: timestamptz

API 端点新增：
  POST /api/v1/customers/{id}/news         — 添加资讯条目（手动或 Agent 抓取）
  GET  /api/v1/customers/{id}/news         — 获取资讯时间线
  PATCH /api/v1/customers/{id}/profile     — 更新画像结构字段
```

**影响文件**：`customer_analysis/domain/models.py`、`customer_analysis/infrastructure/postgres_repository.py`、DB migration

### 8.2 缺口 #2：Pipeline 阶段进度条 — Customer Operation 模块

**原型表现**：`view-customer-mgmt` 中每个客户显示 6 阶段水平进度条：
- 已获得 → 已邮件 → 已回复 → 会议 → 方案 → 成交
- 每阶段有状态颜色（绿=完成/橙=当前/灰=未到达）+ 完成日期
- 不同客户在不同阶段（GlobalLink 已完成 5/6，Nagoya 在「已邮件」阶段）

**当前计划缺漏**：
- `sales_lead.pipeline_stage` 只有 8 个文本状态，缺少每个阶段的时间戳
- `lead_stage_transition` 表有流转记录，但没有聚合为进度条所需的 API

**后端需补充**：

```
API 端点：
  GET /api/v1/lead-pool/mine/pipeline     — 销售名下所有 lead 的 pipeline 进度列表
    返回格式：
    {
      "leads": [
        {
          "lead_id": "...",
          "company_name": "...",
          "stages": [
            {"stage": "new",         "label": "已获得", "completed": true,  "completed_at": "2026-06-03"},
            {"stage": "contacted",   "label": "已邮件", "completed": true,  "completed_at": "2026-06-03"},
            {"stage": "engaged",     "label": "已回复", "completed": true,  "completed_at": "2026-06-04"},
            {"stage": "meeting",     "label": "会议",   "completed": true,  "completed_at": "2026-06-05"},
            {"stage": "proposal",    "label": "方案",   "completed": false, "completed_at": null},
            {"stage": "won",         "label": "成交",   "completed": false, "completed_at": null}
          ],
          "current_stage": "meeting",
          "progress_pct": 66.7
        }
      ]
    }
```

**实现**：`sales_crm` 模块中 `lead_stage_transition` 表已有所有数据，只需在 read_models 或 sales_crm router 中加一个聚合查询端点。

**影响文件**：`sales_crm/interfaces/router.py`（新端点）、`read_models/queries/pipeline_funnel.py`（或直接在 Sales CRM 内部实现）

### 8.3 缺口 #3：手动记录 AI 提取管道（Manual Note Pipeline）— Customer Operation 模块

**原型表现**：`manualNoteModal` 有 4 个状态：
1. **输入** — 自然语言 textarea + "提取匹配"按钮
2. **提取中** — 加载动画 "AI 正在识别和提取信息... 匹配四大维度 17 个信息点"
3. **确认** — 逐条显示识别到的字段，冲突字段需选择"覆盖"或"保留原值"
4. **成功** — "已写入客户分析报告（v2）" + 原始记录存档 + 旧版本保留 + 跳转

**当前计划缺漏**：
- `manual_note` 表只有基础字段（note_id, company_id, content, author_user_id, version）
- 缺少 AI 提取结果的结构化存储
- 缺少冲突检测和 resolution 机制
- 客户分析报告 v2 增量更新机制未定义

**后端需补充**：

```
manual_note 表扩展：
  - processing_status: enum('raw', 'extracting', 'extracted', 'confirmed', 'applied', 'failed')
  - extracted_fields: jsonb        — AI 提取的结构化字段（17 个信息点映射）
    {
      "market_analysis.pain_points": {"value": "...", "confidence": 0.85},
      "company_analysis.business_model": {"value": "...", "confidence": 0.72},
      ...
    }
  - conflicts: jsonb               — 冲突检测结果
    [{"field": "...", "existing": "...", "new": "...", "resolution": null}]
  - resolution: jsonb              — 用户确认后的解决方案
    {"market_analysis.pain_points": "overwrite", "company_analysis.business_model": "keep_existing"}
  - applied_report_version_no: int — 应用后生成的新报告版本号
  - applied_at: timestamptz

API 端点：
  POST /api/v1/manual-notes                      — 创建原始记录 (status=raw)
  POST /api/v1/manual-notes/{id}/extract         — 触发 AI 提取 (status=extracting → extracted)
  GET  /api/v1/manual-notes/{id}/extracted       — 获取提取结果（extracted_fields + conflicts）
  POST /api/v1/manual-notes/{id}/confirm         — 确认提取结果（status=confirmed → applied）
     body: { resolutions: {"field": "overwrite|keep_existing", ...} }
  GET  /api/v1/manual-notes                      — 客户维度的手动记录列表

AI 提取逻辑：
  Prompt: "从以下非正式记录中提取结构化客户信息，映射到以下 17 个维度：
    市场分析(4)：行业规模、竞争格局、市场趋势、需求特征
    公司分析(5)：业务模式、组织架构、决策链、预算周期、技术栈
    竞争分析(4)：替代方案、差异化优势、竞争威胁、价格敏感度
    产品建议(4)：推荐方案、切入点、风险点、下一步动作
    对于无法确定的信息，标记 confidence < 0.5 并放到 '未识别' 区域。
    对于与已有数据冲突的字段，标记为 conflict。"

降级（PRD §9.5.4 模块 9）：
  LLM 超时(>15s) → Flash 模型 → 仅提取高置信度字段 → 剩余字段标记为手动补充
```

**影响文件**：`customer_operation/domain/email_message.py`（新建 manual_note 模型）、`customer_operation/application/service.py`（ManualNoteService）、`customer_operation/infrastructure/llm_adapter.py`（新增 manual_note extraction 方法）、`customer_operation/interfaces/router.py`（5 个新端点）、DB migration（manual_note 表扩展）

### 8.4 缺口 #4：邮件 Dialog 完整需求 — Customer Operation 模块

**原型表现**：`emailDialog` 全屏弹窗，布局为左面板（联系人+历史）+ 右面板（编辑+翻译）：

| 区域 | 原型功能 | 后端缺口 |
|---|---|---|
| 左侧联系人关系图 | 3 类角色（间接影响者/核心决策人/执行者）SVG 连线，点击切换收件人 | `contact.relationship_role` 字段已有，但关系图需要 `contact` 的 role + 关联 grouping 信息 |
| 左侧历史邮件 | 入站/出站 时间线（direction + 摘要），点击查看详情 | email 表已有 direction/purpose/status，需要 list + detail API |
| 右侧 AI 生成预览 | 编辑区 + 👍/👎 反馈按钮 + 翻译下拉 | **缺反馈收集端点** |
| 翻译功能 | 5 种目标语言（日/英/法/德/西 + 中文润色），替换 workflow | 翻译 API 已有（operationApi.translateEmail），但需要多语言支持 |
| 重新生成 | 自然语言 prompt + 快捷提示（GDPR/ROI/正式语气/多国覆盖） | **缺 regenerate API**，目前 generate 没有 prompt 参数 |
| 文件附件 | 拖拽上传（PDF/Word/Excel/图片） | **缺附件上传端点** |
| 发送 | 最终发送按钮 | send API 已有 |

**后端需补充**：

```
API 端点：
  # 邮件反馈（RLHF 数据收集）
  POST /api/v1/email/{id}/feedback
    body: { rating: "up"|"down", reason: str? }

  # 邮件重新生成（带 prompt）
  POST /api/v1/email/generate
    body: { company_id, contact_id, purpose, prompt_hints?: string[] }

  # 附件上传
  POST /api/v1/email/attachments
    body: multipart/form-data (file)
    → { attachment_id, filename, content_type, size_bytes, storage_url }

  # 邮件详情（含历史线程）
  GET /api/v1/email/{id}
    → { email_message, thread: [...] }

  # 联系人关系图数据
  GET /api/v1/companies/{id}/contact-graph
    → {
      "contacts": [
        { contact_id, name, role: "decision_maker"|"influencer"|"executor", title, influence_edge }
      ],
      "edges": [
        { from_contact_id, to_contact_id, relationship: "budget_influence"|"task_delegation"|"reports_to" }
      ]
    }
```

**影响文件**：`customer_operation/interfaces/router.py`（+5 端点）、`customer_operation/infrastructure/email_provider_adapter.py`（附件上传到 S3）、DB migration（email_feedback 表，可选）

### 8.5 缺口 #5：案例库 + 话术库 — Read Models 模块

**原型表现**：
- **案例库**（`db-cases`）：23 条案例，每条约 8 个字段（状态/行业/规模/区域/金额/周期/关键动作/成功因素），可关联话术编号
- **话术库**（`db-scripts`）：28 条模板，表格展示（编号/名称/类型/适用场景/回复率/版本），可点击"使用"

**当前计划缺漏**：
- PRD 中没有案例库/话术库对应的 Agent 或数据表
- 这些是销售个人沉淀的内容，不属于标准 DDD 模块

**后端需补充**：

```
新建表（数据库独立，可与 read_models 同层）：

case_library（案例库）：
  - case_id: UUID PK
  - owner_user_id: UUID — 沉淀该案例的销售
  - company_name: text
  - industry: text
  - employee_count: int?
  - region: text
  - deal_amount: text
  - deal_cycle_days: int — 成单周期
  - lifecycle_status: enum('won', 'lost', 'in_progress')
  - key_actions: text[] — 关键动作列表
  - success_factors: text[] — 成功因素
  - linked_script_ids: text[] — 关联话术编号（如 ["S007 v1.3"]）
  - version: int
  - created_at: timestamptz

script_library（话术库）：
  - script_id: UUID PK
  - owner_user_id: UUID?
  - script_code: text — 编号（S007, S008 等）
  - script_name: text — 话术名称
  - script_type: enum('email', 'linkedin', 'phone', 'other')
  - applicable_scenario: text — 适用场景
  - reply_rate: float? — 回复率（从案例自动计算）
  - content: text — 话术原文
  - version_label: text — 版本号（v1.0, v1.3）
  - status: enum('active', 'archived')
  - version: int
  - created_at: timestamptz

API 端点：
  GET    /api/v1/cases                          — 案例列表（按 owner 过滤）
  POST   /api/v1/cases                          — 新建案例
  GET    /api/v1/cases/{id}                     — 案例详情
  GET    /api/v1/scripts                        — 话术列表
  POST   /api/v1/scripts                        — 新建话术
  GET    /api/v1/scripts/{id}                   — 话术详情
```

**影响文件**：新建模块或放入 `read_models/` — `read_models/queries/case_library.py`、`read_models/queries/script_library.py`、DB migration（2 新表）

### 8.6 缺口 #6：CEO 经营驾驶舱 — Read Models 模块

**原型表现**：`ceo-dashboard` 包含：
1. 指标卡（3 个）：营收（同比+18%）、利润（同比+12%）、转化率（11.8%）— 月/季/年切换
2. 全局漏斗 + 分布漏斗（区域市场 + 应用场景二维）
3. 销售评估健康度表（区域/国家/团队人数/成交额/转化率/健康度）
4. Agent 健康度表（5 个 Agent × 5 维度 → 系统可信度评分）
5. 管理建议（叙事文本）

**当前计划缺漏**：
- `read_models/queries/boss_dashboard.py` 只提到名称，没有具体查询
- Agent 健康度评估完全是新领域

**后端需补充**：

```
API 端点：
  GET /api/v1/dashboard/boss
    query: period=month|quarter|year

响应：
  {
    "metrics": {
      "revenue": { "value": 42800, "yoy_change_pct": 18 },
      "profit":  { "value": 13700, "yoy_change_pct": 12 },
      "conversion_rate": { "value": 11.8 }
    },
    "funnel": {
      "global": [
        { "stage": "新线索", "count": 892 },
        { "stage": "已分配", "count": 156 },
        { "stage": "已跟进", "count": 98 },
        { "stage": "会议", "count": 42 },
        { "stage": "方案", "count": 28 },
        { "stage": "成交", "count": 12 }
      ],
      "by_region": [ ... ],
      "by_scenario": [ ... ]
    },
    "sales_health": [
      { "region": "东亚", "country": "日本", "headcount": 1, "revenue": 5600, "conversion": 14.2, "health": "good" },
      ...
    ],
    "agent_health": [
      {
        "agent": "线索收集Agent",
        "trust_score": 90,
        "data_validation": 96,
        "rule_consistency": 92,
        "outcome_validation": 72,
        "anomaly_rate": 4,
        "verdict": "可继续放量"
      },
      ...
    ],
    "management_advice": "..."
  }

Agent 健康度计算（确定性规则）：
  trust_score = data_validation × 0.35 + rule_consistency × 0.35 + outcome_validation × 0.20 - anomaly_rate × 0.10
  判定：≥85% → "可继续放量" / 80-85% → "稳定输出" / 75-80% → "维持门槛" / 70-75% → "先收紧规则" / <70% → "补齐回流"
```

**影响文件**：`read_models/queries/boss_dashboard.py`（完整实现 ~200 行）、`read_models/interfaces/router.py`

### 8.7 缺口 #7：CEO 线索收集 — Lead Intelligence 模块

**原型表现**：`ceo-lead-collect` 中 CEO 以自然语言对话方式找线索：
- 左侧：候选线索结果（公司列表 + 命中原因 + 勾选批量操作）
- 右侧：对话流（用户输入 + Agent 流式回复 + 快捷提示词）
- 操作：批量回拨 / 批量入库 / 全部入库
- 文件上传：CSV/Excel/PDF/DOC/TXT

**当前计划缺漏**：
- §2 已有 `POST /api/v1/lead-discovery/dialogue-search/stream`（NDJSON），与对话 UI 匹配 ✅
- 缺少「批量入库」端点 — 原型有 CEO 一键入库操作
- 缺少文件上传端点 — 原型支持手动上传客户资料

**后端需补充**：

```
API 端点：
  # 批量入库（将所选候选公司升级到 sales_crm）
  POST /api/v1/lead-discovery/batch-promote
    body: { candidate_ids: UUID[], target_pool_region?: string }
    → { promoted: N, failed: [...], already_promoted: [...] }

  # 文件上传解析
  POST /api/v1/lead-discovery/upload
    body: multipart/form-data (file: CSV/Excel/PDF/DOC/TXT)
    → { parsed_candidates: [...], errors: [...] }
    # 后端解析文件内容，对每行/每段尝试提取公司名称 + 域名
    # 对候选结果做去重检查后返回
```

**影响文件**：`lead_intelligence/interfaces/router.py`（+2 端点）、`lead_intelligence/application/service.py`（batch_promote + parse_upload）

### 8.8 缺口 #8：CEO 销售管理（离职交接）— Sales CRM 模块

**原型表现**：`ceo-sales-mgmt` 中：
- 指标卡（4 个）：在职销售、交接待办、待交接客户、超时预警
- 交接待办列表：按紧急度排序（沟通中期 > 资源池），SLA 3 工作日
- 销售名册：姓名/区域/等级/在职状态/名下客户/跟进率 → 点击「标记离职」触发交接流程
- 离职交接详情卡：客户 × 当前状态 × 交接方式（逐条分配/指定接替人/批量回库）

**当前计划缺漏**：
- `user_account.status` 有 `departed` 状态，但缺少完整的离职交接流程
- 没有「待交接客户」锁定机制 — 离职期间客户不应出现在普通资源池

**后端需补充**：

```
user_account 表新增列：
  - departure_handover_status: enum('active', 'pending_handover', 'handover_in_progress', 'handover_complete', 'archived')

API 端点：
  # 标记离职
  POST /api/v1/users/{id}/mark-departed
    body: { departure_reason: str, handover_target_user_id?: UUID }
    → 设置 status='departed', departure_handover_status='pending_handover'
    → 自动生成待交接列表（该销售名下所有 allocation_status='claimed' 的 lead）

  # 获取待交接列表
  GET /api/v1/handover/pending
    → { departing_user_id, customers: [
        { lead_id, company_name, current_pipeline_stage, urgency, suggest_action }
      ] }

  # 逐条交接
  POST /api/v1/handover/{lead_id}/transfer
    body: { to_user_id: UUID }

  # 批量回库
  POST /api/v1/handover/batch-release
    body: { lead_ids: UUID[] }
    → 所有勾选 lead 的 allocation_status → 'claimable', current_owner → NULL

  # 离职完成
  POST /api/v1/users/{id}/complete-handover
    → departure_handover_status → 'handover_complete'

  # 销售名册
  GET /api/v1/users?account_type=sales
    → [{ user_id, display_name, region, sales_tier, status, departure_handover_status, active_lead_count, followup_rate }]
```

**影响文件**：`iam/interfaces/router.py`（+3 端点）、`sales_crm/interfaces/router.py`（+3 端点）、`sales_crm/application/service.py`（handover 用例）、`iam/domain/models.py`（User 模型 + handover status 字段）

### 8.9 缺口 #9：Customer 360 复合数据（滑出面板）— Read Models

**原型表现**：`customerDetailPanel`（440px 右侧滑出），5 区：
1. 公司基本信息（名称/行业/规模/区域/简介）
2. 联系人信息（姓名/角色/邮箱/电话）
3. 分析摘要（ICP 评分 + 风险等级 + 关键发现）
4. 推荐话术（根据场景 + ICP 匹配）
5. AI 建议下一步动作

**当前计划缺漏**：
- 这个 360 查询需要跨 4 个模块（sales_crm + customer_analysis + lead_intelligence + read_models/scripts）
- 当前没有聚合端点

**后端需补充**：

```
API 端点：
  GET /api/v1/customers/{id}/compound-360
    → {
      "company": { ... },                    # 来自 sales_crm.company
      "contacts": [ ... ],                   # 来自 sales_crm.contact
      "analysis_snapshot": {                 # 来自 customer_analysis
        "icp_score": 94,
        "icp_grade": "A",
        "risk_level": "low",
        "key_findings": "..."               # 取最后一份 report 的 summary
      },
      "recommended_scripts": [              # 来自 script_library
        { "script_code": "S007", "script_name": "...", "match_reason": "场景匹配" }
      ],
      "ai_next_steps": [                    # 来自 customer_operation 最新 meeting summary 或 manual note
        { "action": "...", "source": "latest_meeting_summary" }
      ]
    }
```

**影响文件**：`read_models/queries/customer_operations_view.py`（跨模块聚合）

### 8.10 缺口 #10：老板钻取面板（Boss Drilldown）— Read Models

**原型表现**：`bossDrilldownPanel` 从 CEO dashboard 的任意指标卡点击钻取：
- 显示"该指标背后的规则、风险、责任和动作建议"
- 包含管理钻取的标题 + 副标题 + body（动态渲染）

**后端需补充**：

```
API 端点：
  GET /api/v1/dashboard/boss/drilldown
    query: metric=revenue|profit|conversion&period=month|quarter|year
    → {
      "metric": "revenue",
      "period": "month",
      "rules": "营收口径 = SUM(销售成交额) WHERE won_at IN period...",
      "risks": ["欧洲区字段缺失导致漏计", "转换率低影响总营收基数"],
      "responsibilities": ["李明（东亚）主责营收", "张伟（北美）补报"],
      "actions": ["复查欧洲区成交数据", "推动东南亚成单节奏"]
    }
```

**影响文件**：`read_models/queries/boss_dashboard.py`（+drilldown 方法）

### 8.11 缺口 #11：邮件翻译多语言支持 — Customer Operation 模块

**原型表现**：翻译下拉支持 6 个选项：
- 🇯🇵 日语、🇬🇧 英语、🇫🇷 法语、🇩🇪 德语、🇪🇸 西班牙语、🇨🇳 中文（本地润色）
- 翻译结果可「替换为译文」或「复制」
- 当前 API `translateEmail` 只有单语言

**后端需补充**：

```
已有 API 修改：
  POST /api/v1/email/translate
    body: {
      email_id?: UUID,             # 可选，翻译已有邮件
      source_text?: string,        # 可选，翻译临时文本
      target_locale: "ja"|"en"|"fr"|"de"|"es"|"zh"  # 目标语言
    }
    → { translated_text, source_locale, target_locale, model_used }
```

**影响文件**：`customer_operation/interfaces/schemas.py`（扩展 translate request）、`customer_operation/infrastructure/llm_adapter.py`

### 8.12 缺口 #12：邮件 RLHF 反馈收集 — Customer Operation 模块

**原型表现**：邮件预览区有 👍/👎 按钮，点击后显示反馈状态

**后端需补充**：

```
新建表 email_feedback：
  - feedback_id: UUID PK
  - email_id: UUID FK → email_message
  - user_id: UUID FK → user_account
  - rating: enum('up', 'down')
  - reason: text?                   — 可选反馈理由
  - created_at: timestamptz

API 端点：
  POST /api/v1/email/{id}/feedback
    body: { rating: "up"|"down", reason?: string }
```

**用途**：收集 RLHF 数据，后续用于微调 EmailGenerationAgent。数据量要求：≥1000 条才开始影响模型权重。

**影响文件**：`customer_operation/interfaces/router.py`、DB migration（email_feedback 表）

### 8.13 缺口汇总：各模块需新增的文件/端点

| 模块 | 缺口数 | 新增端点 | 新增/修改文件 | 新增表 |
|---|---|---|---|---|
| customer_analysis | 1 (#1 画像结构) | 3 | models.py, repository.py, router.py, DB migration | customer_news_item |
| customer_operation | 5 (#3 #4 #11 #12 + 附件) | 12 | router.py, service.py, llm_adapter.py, email_provider_adapter.py, manual_note domain | email_feedback, manual_note 扩展 |
| sales_crm | 2 (#2 pipeline + #8 handover) | 6 | router.py, service.py | — |
| lead_intelligence | 1 (#7 batch + upload) | 2 | router.py, service.py | — |
| read_models | 5 (#5 cases/scripts + #6 CEO dashboard + #9 360 + #10 drilldown) | 6 | boss_dashboard.py, customer_operations_view.py, case_library.py, script_library.py | case_library, script_library |
| iam | 1 (#8 departure) | 2 | router.py, models.py | user_account 扩展 |

**总增量**：~31 个新端点、~15 个新/改文件、~4 张新表、~4 张表扩展

### 8.14 前端"越界"实现清单（当前在 JS 中，应迁移到后端）

> 以下逻辑在原型中全部由前端 `setTimeout` + 硬编码数据模拟，**实际架构划分应属于后端**。
> 每项标注所属 DDD 模块 + 对应原型 JS 函数/位置。

| # | 越界内容 | 原型位置 | JS 做法 | 应归属模块 | 后端应如何实现 |
|---|---|---|---|---|---|
| **A1** | **邮件内容生成** | `generateEmailForContact` L2971 | 前端根据联系人角色（CFO/CTO/默认）硬编码 3 套中/英/日邮件模板 | `customer_operation` | `POST /api/v1/email/generate` → EmailGenerationAgent 调 LLM，基于 email_context（50+ 字段）生成 subject + body |
| **A2** | **邮件翻译** | `translateChineseDraft` L2874 | 前端 JS 硬编码 `if locale==='en' {...} else if locale==='ja' {...}` 的翻译模板 | `customer_operation` | `POST /api/v1/email/translate` → 调 LLM 做真正的 NMT 翻译，支持 6 种语言 |
| **A3** | **邮件重新生成** | `regenerateEmail` L3032 | `setTimeout` + 硬编码 prompt 对应的中文/本地化回复文本 | `customer_operation` | `POST /api/v1/email/generate` 加 `prompt_hints` 参数 → LLM 根据提示重新生成 |
| **A4** | **手动记录 AI 提取** | `submitManualNote` L3352 | `setTimeout` 1.5s 后返回硬编码的 3 条 extracted_fields（CFO 决策人/扩容计划/预算区间） | `customer_operation` | `POST /api/v1/manual-notes/{id}/extract` → LLM 从自然语言提取 17 个结构化字段 + 冲突检测 |
| **A5** | **邮件发送** | `sendEmail` L3047 | `alert('邮件已发送！')` — 没有真正发送 | `customer_operation` | `POST /api/v1/email/send` → EmailDeliveryAgent 调 SendGrid/Resend 实际投递 |
| **A6** | **用户登录** | `doLogin` L2764 | 前端 `if (pwd === '123456')` 硬编码密码验证 | `iam` | `POST /api/v1/auth/login` → bcrypt 验密 + JWT 签发 + refresh token |
| **B1** | **CEO 驾驶舱全部指标** | HTML L2304-2388 | 所有数据硬编码在 HTML：营收 $42,800、利润 $13,700、转化率 11.8%、漏斗各级数量、Agent 健康度 5 行 | `read_models` | `GET /api/v1/dashboard/boss?period=month` → 后端跨表聚合（sales_lead + lead_stage_transition + company）计算真实指标 |
| **B2** | **CEO 钻取面板全部报告** | `openBossDrilldown` L3723 + `contentMap` L3730-3999 | **~50 个**预置报告内容块，全部硬编码中文 HTML 文本（collect_db_list / analysis_quality_report / analysis_channel_report / assign_alloc_report / ...） | `read_models` | `GET /api/v1/dashboard/boss/drilldown?metric=...` → 后端查询对应维度数据，LLM 生成叙事分析文本 |
| **B3** | **CEO 线索收集对话** | `sendCeoLeadFinderQuery` / `ceoLeadFinderSave` 等（HTML L2392-2447） | 候选线索列表硬编码 HTML，没有真正的对话流或后端搜索 | `lead_intelligence` | `POST /api/v1/lead-discovery/dialogue-search/stream` (NDJSON) → 真正调用搜索 API，返回流式结果 |
| **B4** | **CEO 线索分析详情** | `leadDetailData` L3504 | 10 家公司的 5 维度 ICP 评分 + 系统判断全部硬编码 JS object | `lead_intelligence` | `GET /api/v1/lead-discovery/candidates/{id}/icp` → 读 `lead_icp_assessment` 表返回真实评分 |
| **B5** | **CEO 销售管理数据** | `salesMgmtData` L3437 | 4 个销售 + 离职交接 + 3 个客户名称/阶段/ICP 全部硬编码 JS object | `iam` + `sales_crm` | `GET /api/v1/users?account_type=sales` + `GET /api/v1/handover/pending` → 后端读 DB |
| **B6** | **CEO 销售排名** | HTML table（L2568） | 排名表是空的，由 JS `renderSalesRanking()` 动态渲染但数据源仍是硬编码 | `read_models` | `GET /api/v1/dashboard/boss` → 后端 JOIN sales_lead + user_account 按成交额排序 |
| **C1** | **Dashboard 指标卡** | HTML L489-497 | 成交额度 $7,700、转化率 34.6%、目标完成度 48.3%、团队对比 Top25% 全部硬编码 | `read_models` | `GET /api/v1/dashboard/sales` → 后端聚合当前销售的真实 pipeline 数据 |
| **C2** | **Pipeline 进度条数据** | HTML L1350-1478 | 每个客户的 6 阶段进度（哪些完成、完成日期）全部硬编码在每个 `<div>` 中 | `sales_crm` | `GET /api/v1/lead-pool/mine/pipeline` → 后端读 `lead_stage_transition` 表聚合每个 lead 的阶段时间线 |
| **C3** | **客户 360 详情面板** | `customerDetailPanel` HTML | 公司信息/联系人/分析摘要/推荐话术/AI 建议全部硬编码 | `read_models` | `GET /api/v1/customers/{id}/compound-360` → 跨 4 模块聚合 |
| **C4** | **客户分析报告（详细报告面板）** | `analysisReportPanel` HTML | 市场分析/公司分析/竞争分析/产品建议的完整报告文本全部硬编码 | `customer_analysis` | 已有 `legacyCustomer360` API，但报告内容应由后端 LLM 生成，前端不应硬编码 |
| **C5** | **案例库 23 条** | HTML L2230-2280 | 3 条案例（GlobalLink / Sakura / ASEAN）的名称/金额/周期/关键动作/成功因素全部硬编码 | `read_models` | `GET /api/v1/cases` → 读 `case_library` 表 |
| **C6** | **话术库 28 条** | HTML L2285-2299 | 5 条话术（编号/名称/类型/场景/回复率）全部硬编码 | `read_models` | `GET /api/v1/scripts` → 读 `script_library` 表 |
| **C7** | **客户分配资源池** | HTML `view-lead-assign` | 可领取线索表格数据全部硬编码 | `sales_crm` | `GET /api/v1/lead-pool/claimable` → 后端读 `sales_lead` WHERE allocation_status='claimable' |
| **D1** | **联系人关系图** | HTML L5144-5218 | 联系人角色（间接影响者/核心决策人/执行者）、连线关系、名称/邮箱/职位全部硬编码 | `sales_crm` | `GET /api/v1/companies/{id}/contact-graph` → 后端读 `contact` 表返回 relationship_role + 边关系 |
| **D2** | **历史邮件** | HTML L5222-5234 | 2 封历史邮件（收到/发出）的日期/摘要/内容全部硬编码 | `customer_operation` | `GET /api/v1/email/history?company_id=...` → 读 `email_message` 表 |
| **D3** | **会议列表 + AI 摘要** | HTML L5437-5481 | 2 次会议的名称/时间/时长/参会人/摘要 5 点全部硬编码 | `customer_operation` | `GET /api/v1/meeting/history?company_id=...` → 读 `meeting` 表，summary 字段来自 ASR + LLM 转写 |
| **D4** | **客户运营列表的 pipeline + 联系人** | HTML `view-customer-mgmt` L1280-1478 | 4 家客户的 pipeline 状态、联系人信息全部硬编码 | `sales_crm` + `customer_operation` | 多个已有 API 组合 |

### 8.15 越界严重程度分级

| 级别 | 数量 | 说明 | 示例 |
|---|---|---|---|
| **P0 — 核心链路** | 6 | 直接影响产品可用的功能，前端完全在"假装" | A1 邮件生成、A4 AI 提取、A6 登录、B3 线索收集对话、C4 客户分析报告、C2 pipeline 进度 |
| **P1 — 数据展示** | 10 | 前端硬编码数据，应改为后端 API 返回真实数据 | B1 CEO 驾驶舱、C1 指标卡、C5 案例库、C6 话术库、C7 资源池、D1 关系图、D2 历史邮件、D3 会议列表、B5 销售管理、B6 销售排名 |
| **P2 — AI 能力** | 4 | 前端 `setTimeout` 模拟 LLM 调用 | A2 翻译、A3 重新生成、A5 发送、B4 ICP 详情 |
| **P3 — 叙事生成** | 1 | 50+ 段管理报告硬编码在前端 | B2 CEO 钻取面板 |

### 8.16 调整后的优先级矩阵

| 阶段 | 内容 | 新增内容 | 预估工作量 |
|---|---|---|---|
| **Phase 0** | IAM domain + JWT 中间件 | + 离职交接端点（#8）+ **A6 登录**（前端硬编码密码→后端 JWT） | 2-3 天 → **3-4 天** |
| **Phase 1** | Sales CRM domain + repository + router | + pipeline 进度端点（#2）+ handover 端点（#8）+ **C2 pipeline/C7 资源池/D1 关系图** | 3-4 天 → **4-5 天** |
| **Phase 2** | Lead Intelligence domain + service + router | + 批量入库 + 文件上传（#7）+ **B3 对话搜索/B4 ICP 评分** | 4-5 天 → **5-6 天** |
| **Phase 3** | Customer Operation domain + service + router | + manual note pipe（#3）+ 邮件反馈（#12）+ 附件上传 + 多语言翻译（#11）+ 联系人关系图（#4）+ **A1 邮件生成/A2 翻译/A3 重新生成/A5 发送/D2 历史邮件/D3 会议摘要** | 5-7 天 → **8-10 天** |
| **Phase 4** | Read Models queries + dashboard | + CEO dashboard（#6）+ 案例库（#5）+ 话术库（#5）+ 360 复合数据（#9）+ drilldown（#10）+ **B1 CEO 指标/B2 钻取面板/C1 sales 指标/C5 案例库/C6 话术库** | 2-3 天 → **4-5 天** |
| **Phase 5** | Customer Analysis 扩展 | 画像结构（#1）+ news_item（#1）+ **C4 报告面板去硬编码** | **新增 2-3 天** |
| **Phase 6** | 集成测试 + main.py 挂载 | — | 2-3 天 |
| **总计** | | | **~8,300 行 → ~12,000 行** |
