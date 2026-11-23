# 05 - API 接口契约

> 版本：v3.6
> Base Path：`/api/v1`
> 本文档是前后端和模块联调基线；实现后由代码生成 OpenAPI，不再维护一份不完整的平行 YAML
> v3.6：账号角色改为 Sales/Strategic；增加 Strategic 直接离职回池 API；Disable 仅禁登录；当前 scene_code 仅 S1-S3；Apollo 仅作为内部 Provider，不暴露独立入口
> v3.5（历史记录，冲突口径已由 v3.6 覆盖）：曾使用 Manager 与 S1-S5 契约；账号管理、登录锁定、批量确认、路径和幂等修订继续保留

---

## 1. 通用契约

### 1.1 认证

- 使用 HttpOnly、Secure、SameSite Cookie；
- Actor 只能从服务端 Session 解析；
- 请求体中的 `user_id/owner_id/role` 不能作为可信 Actor；
- 每个 Company/Lead/Email/Meeting 请求独立授权；
- 不存在和不可见的资源统一返回 404。

### 1.2 成功响应

单资源：

```json
{
  "request_id": "req_xxx",
  "data": {}
}
```

列表：

```json
{
  "request_id": "req_xxx",
  "data": [],
  "page": {
    "next_cursor": "opaque_cursor",
    "has_more": true
  }
}
```

异步：

```json
{
  "request_id": "req_xxx",
  "data": {
    "resource_type": "lead_search_run",
    "resource_id": "uuid",
    "status": "queued",
    "job": {
      "job_id": "uuid",
      "job_type": "lead.search_pipeline.v1",
      "status": "queued",
      "status_url": "/api/v1/jobs/uuid",
      "events_url": "/api/v1/jobs/uuid/events"
    }
  }
}
```

### 1.3 错误响应

```json
{
  "request_id": "req_xxx",
  "error": {
    "code": "SALES_LEAD_NOT_CLAIMABLE",
    "message": "该销售线索已不在可领取状态。",
    "details": {
      "lead_id": "uuid"
    }
  }
}
```

### 1.4 通用规则

| 规则 | 要求 |
|---|---|
| 时间 | UTC RFC3339 |
| ID | UUID 字符串 |
| JSON 字段 | `snake_case` |
| 分页 | Cursor，默认 20，最大 100 |
| 更新 | 使用 `If-Match: "version"`，成功返回 `ETag` |
| 副作用命令 | Select/Claim/Assign/Release/Transfer/Send 等使用 `Idempotency-Key` |
| 长任务 | 202 + resource_id + job_id |
| Progress | SSE，Polling 降级 |
| Actor | Session 解析 |
| DTO | 不暴露 ORM 和任意数据库 JSON |

不是所有 POST 都要求 Idempotency-Key。只对可能重复产生副作用的命令使用。

### 1.5 幂等键和 Request Hash

幂等唯一范围为 `principal_type + principal_id + scope + Idempotency-Key`。HTTP Scope 使用固定命令名，不使用原始 URL 字符串，例如 `candidate_select`、`lead_claim`、`meeting_upload`。

`request_hash = SHA-256(canonical_json(...))`，统一规则：

- 包含 Route Path 参数、业务请求体和标准化后的 `If-Match`；
- JSON Object Key 排序，数组保持业务顺序；缺省值先按 DTO 补齐，空字符串不得与 NULL 混用；
- 不包含 Cookie、Access Token、Request ID、Trace ID 和客户端时间等瞬时数据；
- Multipart 使用规范化元数据和文件 SHA-256，不把临时文件路径纳入 Hash；
- 同 Key 同 Hash：completed 重放原状态码/响应；普通命令 in-progress 返回 409 `IDEMPOTENCY_IN_PROGRESS`；
- 同 Key 不同 Hash：返回 409 `IDEMPOTENCY_KEY_REUSED`；
- 领域写入、幂等 completed 状态和可重放响应在同一数据库事务提交。

批量 Select/Transfer 是可恢复批次，使用两级 Checkpoint：

1. Batch Parent 保存整批 canonical request hash，状态为 in_progress/completed；
2. 每个 Item 使用独立幂等记录，并与该 Item 的领域 UoW 同事务提交；
3. 同 Hash 重试若 Parent 仍 in_progress，先用 `pg_try_advisory_lock(stable_hash64(principal_type,principal_id,scope,key))` 取得单执行者锁；取得后从未完成 Item 续跑，未取得返回 409；
4. Advisory Lock 是 session-level：Coordinator 必须 pin 同一个 physical PostgreSQL connection，使用 `try/finally` 显式执行 `pg_advisory_unlock` 后才能归还连接池；Unlock 失败则销毁该连接，应用 Shutdown 关闭全部连接兜底；
5. 所有 Item 都有终态 Checkpoint 后，聚合结果并把 Parent 标记 completed；
6. 同 Key 改变 Item 集合、顺序或任一字段会改变 Parent Hash，返回 409。

`stable_hash64` 使用固定算法/seed，并将 Principal Type、Principal ID、Scope、Key 以带长度前缀的 UTF-8 字节串编码，禁止使用进程随机 Hash。批次异常路径必须先释放锁；锁释放后，同 Hash 请求可取得锁并从 Item Checkpoint 继续。

---

## 2. IAM

### 2.1 Login

```http
POST /api/v1/auth/login
```

请求：

```json
{
  "username": "ma.east",
  "password": "******"
}
```

响应：

```json
{
  "request_id": "req_xxx",
  "data": {
    "user": {
      "user_id": "uuid",
      "username": "ma.east",
      "display_name": "销售A",
      "account_type": "sales",
      "sales_tier": "MA",
      "region_code": "EA",
      "capacity_limit": 15
    },
    "capabilities": [
      "sales_lead.view_pool",
      "sales_lead.claim",
      "sales_lead.release"
    ]
  }
}
```

错误：

- `AUTH_INVALID_CREDENTIALS`
- `USER_LOCKED`
- `USER_DISABLED`
- `USER_DEPARTED`

连续 5 次密码失败返回 `USER_LOCKED` 并锁定 30 分钟，到期自动恢复；锁定事件写审计并告警。

### 2.2 Refresh/Logout/Me

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/auth/refresh` | 刷新 Access Token |
| POST | `/api/v1/auth/logout` | 撤销当前 Session，204 |
| GET | `/api/v1/auth/me` | 当前用户、Capability、Active Assignment Count |

### 2.3 账号管理（Strategic）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/users` | 用户列表（region/tier/status 筛选） |
| POST | `/api/v1/users` | 创建 sales/strategic 账号；sales 必须绑定 sales_tier/region_code/capacity_limit |
| PATCH | `/api/v1/users/{user_id}` | 当前只允许修改 display_name/email；等级和区域调整 Deferred |
| POST | `/api/v1/users/{user_id}:disable` | 安全禁用并撤销全部 Session；不释放客户、不清 Task、不取消业务 Job |
| POST | `/api/v1/users/{user_id}:enable` | 启用 disabled 账号；不得恢复 departed 账号 |
| POST | `/api/v1/users/{user_id}:unlock` | 解除登录锁定 |
| POST | `/api/v1/users/{user_id}:reset-password` | 重置为一次性临时密码，首次登录强制修改 |
| POST | `/api/v1/users/{user_id}:depart` | Strategic 将 active/disabled Sales 标记离职并原子释放其客户回原池 |

写操作均要求 `Idempotency-Key`，更新既有 User 同时要求 `If-Match`，并写 `audit_log`。多账号登录的账号创建入口即本节端点（登录即分配：sales 创建时绑定 region×tier，登录后资源池视图由账号属性决定，无需运行时选择）。

`depart` 请求：

```http
POST /api/v1/users/{user_id}:depart
Idempotency-Key: uuid
If-Match: "user_version"
```

```json
{
  "reason": "employee_departure"
}
```

成功响应：

```json
{
  "request_id": "req_xxx",
  "data": {
    "user_id": "uuid",
    "status": "departed",
    "released_lead_count": 12,
    "returned_pools": [
      {"region_code": "SEA", "sales_tier": "SA", "count": 12}
    ],
    "departed_at": "2026-07-20T08:00:00Z"
  }
}
```

服务端在一个事务内完成 User departed、Session 撤销、全部 active Assignment 结束、Lead owner 清空并回 `claimable`、Audit/Outbox 写入。Lead 保留原 `required_sales_tier/pool_region_code/pool_region_mapping_version/allocation_rule_version`。该命令不创建申请、审批、`handover_request` 或异步 Job。

---

## 3. Lead Intelligence

### 3.1 创建对话搜索

```http
POST /api/v1/lead-search-runs
Idempotency-Key: uuid
```

请求：

```json
{
  "query_text": "寻找日本和韩国有跨境差旅能力的 TMC，优先有 API 对接能力",
  "search_mode": "both",
  "target_count": 20,
  "scene_code": "S1"
}
```

规则：

- 只接受对话文本；
- 不接受 File/Multipart；
- 不接受 manual/crawler/geo 等 source type；
- Provider、Prompt、Rule 的最终版本由服务端配置决定，客户端不得指定 Provider；
- 默认执行 Search Orchestration → Web Search/Apollo Provider Execution → Evidence → Observation → Candidate → Contact → D1-D4 → ICP → Scale；
- 当前 `scene_code` 只接受 S1/S2/S3，S4/S5 返回 `SCENE_NOT_SUPPORTED` 且不创建 Search Run/Job。

响应：202，返回 `search_run_id` 和 `job_id`。

错误：

- `DIALOGUE_QUERY_EMPTY`
- `DIALOGUE_QUERY_TOO_LONG`
- `SEARCH_MODE_INVALID`
- `TARGET_COUNT_OUT_OF_RANGE`
- `SEARCH_RUN_ALREADY_ACTIVE`
- `SCENE_NOT_SUPPORTED`

### 3.2 Search Run 查询

```http
GET /api/v1/lead-search-runs/{search_run_id}
```

响应重点字段：

```json
{
  "request_id": "req_xxx",
  "data": {
    "search_run_id": "uuid",
    "query_text": "...",
    "search_mode": "both",
    "scene_code": "S1",
    "status": "running",
    "current_step": "enriching",
    "progress_percent": 62.5,
    "provider_executions": [
      {"provider_code": "web_search", "status": "succeeded", "result_count": 24},
      {"provider_code": "apollo", "status": "running", "result_count": 0}
    ],
    "counts": {
      "evidence": 36,
      "candidate": 18,
      "enriched": 10,
      "scored": 8,
      "duplicate": 2,
      "rejected": 1
    },
    "current_job_id": "uuid",
    "error_summary": null
  }
}
```

### 3.3 SSE

```http
GET /api/v1/jobs/{job_id}/events
Accept: text/event-stream
Last-Event-ID: 42
```

事件类型：

- `progress`
- `step_started`
- `step_completed`
- `candidate_upserted`
- `candidate_scored`
- `warning`
- `error`
- `completed`

SSE Payload 不包含模型敏感内部推理。

### 3.4 Search Run 命令

| 方法 | 路径 | 权限 |
|---|---|---|
| POST | `/api/v1/lead-search-runs/{id}:cancel` | 发起人/Strategic |
| POST | `/api/v1/lead-search-runs/{id}:retry` | Strategic |

两项命令都要求 `If-Match` 和 `Idempotency-Key`。Retry 保留旧 Job 的终态，新建 `retry_of_job_id=旧 Job` 的 queued Job，并原子更新 Search Run 的 `current_job_id`。Cancel 同时更新 Search Run 和当前 Job，不允许只改一边。

### 3.5 Candidate 列表

```http
GET /api/v1/lead-candidates
```

参数：

- `search_run_id`
- `processing_status`
- `assessments_stale`
- `validation_status`
- `region_code`
- `country_code`
- `industry_code`
- `icp_grade`
- `min_icp_score`
- `negative_filter_result`（none/X1-X6）
- `a_segment`（A1-A3 由当前 ICP 派生，不落库；A4 请在 Sales Lead 列表筛选）
- `scene_code`（S1-S3）
- `customer_tier`
- `required_sales_tier`
- `cursor`
- `limit`

Candidate 列表不是 Sales Claim Pool。

### 3.6 Candidate 详情

```http
GET /api/v1/lead-candidates/{candidate_id}
```

响应结构：

```json
{
  "request_id": "req_xxx",
  "data": {
    "candidate": {
      "candidate_id": "uuid",
      "company_name": "Example TMC",
      "website": "https://example.com",
      "normalized_domain": "example.com",
      "industry_code": "TMC",
      "region_code": "EA",
      "country_code": "JP",
      "processing_status": "eligible",
      "assessments_stale": false,
      "version": 4
    },
    "contacts": [
      {
        "candidate_contact_id": "uuid",
        "full_name": "A",
        "title": "VP",
        "relationship_role": "decision_maker",
        "priority": "P1",
        "email_status": "valid"
      }
    ],
    "icp": {
      "icp_assessment_id": "uuid",
      "scene_code": "S1",
      "rule_version": "tmc-2026-06-26",
      "d1_score": 30,
      "d2_score": 22.5,
      "d3_score": 15,
      "d4_score": 7.5,
      "total_score": 75,
      "grade": "B",
      "hard_gate_passed": true
    },
    "customer_scale": {
      "scale_assessment_id": "uuid",
      "d1_scale_score": 30,
      "d2_commercial_score": 26.25,
      "d3_coverage_score": 18.75,
      "total_score": 75,
      "computed_tier": "medium",
      "effective_tier": "medium",
      "required_sales_tier": "SA"
    },
    "evidence": []
  }
}
```

### 3.7 Candidate 命令

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/lead-candidates/{id}:refresh-enrichment` | 新建富化版本和 Job |
| POST | `/api/v1/lead-candidates/{id}:reject` | Strategic 驳回 |
| POST | `/api/v1/lead-candidates/{id}:reopen` | Strategic 重新打开 |
| POST | `/api/v1/lead-candidates/{id}:merge` | 合并重复 Candidate |

Refresh Enrichment：

```http
POST /api/v1/lead-candidates/{candidate_id}:refresh-enrichment
If-Match: "candidate_version"
Idempotency-Key: uuid
```

创建 `lead_enrichment_run(status=queued)` 和 Job，并将 Candidate 标记 `assessments_stale=true`。旧 current ICP/Scale 继续可读，但 stale 期间禁止 Select。Candidate 已 promoted 时仍允许 Refresh，但不会修改现有 Sales Lead 的 adopted ICP/Scale。

Merged/archived Candidate 不允许 Refresh；同一 Candidate 同时最多一个 queued/running Enrichment Run。

Enrichment Run 命令：

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/lead-enrichment-runs/{run_id}:retry` | 新建 Job，旧 Job 保持终态 |
| POST | `/api/v1/lead-enrichment-runs/{run_id}:cancel` | Run 和当前 Job 同事务取消 |

两项命令都要求 `If-Match` 和 `Idempotency-Key`。

### 3.8 Candidate Merge

```http
POST /api/v1/lead-candidates/{source_candidate_id}:merge
If-Match: "source_version"
Idempotency-Key: uuid
```

请求：

```json
{
  "target_candidate_id": "uuid-target",
  "target_expected_version": 7,
  "reason": "同一官网和法定主体，保留信息更完整的 Candidate"
}
```

事务规则：

- Source 和 Target 按 ID 排序加锁，避免双向合并死锁；
- Source 不能是 promoted/merged/archived，Target 不能是 merged/archived；
- Target 必须是 Canonical Candidate，禁止 Merge Chain；
- Target 可以已经 promoted，但 Source 只标记 merged，不伪造 Promotion；
- Source Observation/Evidence 保留原主键，通过 Canonical Resolver 汇总；
- Contact 合并记录明确的 Source Contact → Target Contact 映射；
- Source 最终写入 `processing_status=merged`、`merged_into_candidate_id` 和 `merged_at`；
- Target 写 `assessments_stale=true`，并原子创建 Enrichment Run + Job；
- 重评成功前 Target 不可 Select；失败或取消后继续 stale，必须 Retry。

响应：202（Merge 已提交，Canonical Candidate 正在重评）。

```json
{
  "request_id": "req_xxx",
  "data": {
    "source_candidate_id": "uuid-source",
    "canonical_candidate_id": "uuid-target",
    "source_status": "merged",
    "canonical_status": "eligible",
    "canonical_assessments_stale": true,
    "enrichment_run_id": "uuid-run",
    "current_job_id": "uuid-job"
  }
}
```

### 3.9 批量选择入池

```http
POST /api/v1/lead-candidates:select
Idempotency-Key: uuid
```

请求：

```json
{
  "items": [
    {
      "candidate_id": "uuid-1",
      "expected_version": 4,
      "override": false,
      "override_reason": null
    },
    {
      "candidate_id": "uuid-2",
      "expected_version": 8,
      "override": true,
      "override_reason": "区域战略优先，已人工复核证据"
    }
  ]
}
```

事务结果：

- 创建/复用 Company；
- 晋升 Contact；
- 创建 Sales Lead，`allocation_status=claimable`，或复用同一 Company 已有开放 Sales Lead；
- Candidate 标记 promoted；
- 返回 ID Mapping。

`override=true` 时 `override_reason` 必填。普通选择要求 Candidate=eligible；Strategic Override 只允许对已有 current ICP/Scale 的 scored Candidate 使用。两者都要求 `assessments_stale=false`，不能绕过缺失评估、stale、merged、archived 或已 promoted 状态。

补全池路由（v3.5）：Scale `effective_tier=unknown` 或公司区域未知的 Candidate 允许入池并落入数据补全池（`promotion_result=created_completion_lead`）。区域已知的 `scale_unknown` 仅对同区域 A 级销售可见；区域未知时 `pool_region_code=NULL`，对全部 Sales 隐藏，仅供 Strategic 查看和后台补全。

响应：

```json
{
  "request_id": "req_xxx",
  "data": {
    "succeeded": [
      {
        "candidate_id": "uuid-1",
        "company_id": "uuid-company",
        "lead_id": "uuid-lead",
        "selected_icp_assessment_id": "uuid-icp",
        "selected_scale_assessment_id": "uuid-scale",
        "promotion_result": "created_lead",
        "allocation_status": "claimable"
      }
    ],
    "failed": [
      {
        "candidate_id": "uuid-2",
        "code": "CANDIDATE_NOT_READY",
        "message": "缺少当前客户规模评估"
      }
    ]
  }
}
```

批量接口允许部分成功。先建立 Batch Parent：Scope=`candidate_select_batch`，Hash 覆盖补齐 DTO 缺省值后的整个有序 `items` 数组；随后每一项的 Promotion 事务独立，并使用 Item Checkpoint 保证进程在部分提交后崩溃仍可安全重试：

- Item Scope=`candidate_select_item`；
- Item Key=`{request_idempotency_key}:{candidate_id}`；
- Item Hash 覆盖 `candidate_id/expected_version/override/override_reason`；
- 每项 Promotion、Item completed 状态和 Item 响应在同一事务提交；
- 顶层响应由所有 Item Checkpoint 重组，已完成项只重放，不再次晋升；
- 全部 Item 完成后，顶层响应和 Batch Parent completed 在同一短事务提交；
- 同一批次不得出现重复 `candidate_id`，否则整批返回 422。

若复用开放 Sales Lead，响应 `promotion_result=reused_open_lead`，Candidate 记录该 Lead，但 Select 不替换该 Lead 已采用的 ICP/Scale，也不重复追加 `pool_entry`。每项必须使用自己的 `expected_version`；某一项版本冲突只使该项失败。

---

## 4. Sales CRM

### 4.1 Sales Lead Pool

```http
GET /api/v1/sales-leads/pool
```

后端根据：

- Actor Sales Tier；
- Actor `region_code` 与 Lead `pool_region_code` 精确匹配；
- Lead `required_sales_tier`；
- Lead `pool_region_code`；
- `allocation_status=claimable`；
- 当前 Capacity；

返回可领取资源。

可见性补充（v3.5）：`data_completion_pool=scale_unknown` 的 Lead 按 `pool_region_code` 正常参与强制 Region 过滤（仅同区域 A 级销售可见）；`data_completion_pool=region_unknown` 的 Lead 对 Sales Pool API 不可见，仅 Strategic 全局列表和后台补全 Worker 可见。当前没有关闭 Region Filter 的配置开关。

前端不得再次过滤或扩展权限。

### 4.2 Strategic 全局 Sales Lead 列表

```http
GET /api/v1/sales-leads
```

仅 Strategic 可用，不应用 Sales Tier、Region 或 Capacity 的自助领取过滤。筛选参数：

- `allocation_status`
- `pipeline_stage`
- `owner_user_id`，支持 `unassigned`
- `required_sales_tier`
- `pool_region_code`
- `country_code`
- `company_query`
- `sla_state`
- `a_segment`（含 A4 动态升级客户筛选）
- `task_due_before`
- `sort`
- `cursor`
- `limit`

列表项固定返回：

```text
lead_id
company_summary
current_assignment
adopted_icp_scale_summary
required_sales_tier
pool_region_code
allocation_status
pipeline_stage
sla_due_at
last_activity_at
version
available_actions
```

Strategic 从该列表执行 Assign、Release、Transfer 和 Batch Transfer。`/workspaces/strategic` 只提供汇总和快捷入口，不能替代可分页的资源列表。

`sla_state` 只表示首次触达 SLA：`pending` = 已分配未首触且未到期，`overdue` = 已分配未首触且已到期，`completed` = 已首触，`not_applicable` = 未分配。后续动作时限使用 Follow-up Task，不复用 Sales Lead SLA。

### 4.3 我的 Sales Lead

```http
GET /api/v1/sales-leads/mine
```

参数：

- `pipeline_stage`
- `allocation_status`
- `task_due_before`
- `cursor`
- `limit`

### 4.4 Sales Lead 详情

```http
GET /api/v1/sales-leads/{lead_id}
```

返回：

- Sales Lead；
- Company Summary；
- Current Assignment；
- Adopted ICP/Scale Summary；
- SLA；
- Pipeline；
- Version。

### 4.5 Claim

```http
POST /api/v1/sales-leads/{lead_id}:claim
Idempotency-Key: uuid
If-Match: "4"
```

请求 Body 为空。Owner 来自 Session。

响应：

```json
{
  "request_id": "req_xxx",
  "data": {
    "lead_id": "uuid",
    "assignment_id": "uuid",
    "allocation_status": "claimed",
    "owner_user_id": "uuid",
    "assigned_at": "2026-07-16T08:00:00Z",
    "sla_due_at": "2026-07-17T08:00:00Z",
    "version": 5
  }
}
```

错误：

- `SALES_LEAD_NOT_CLAIMABLE`
- `SALES_TIER_MISMATCH`
- `SALES_REGION_MISMATCH`
- `SALES_CAPACITY_EXCEEDED`
- `VERSION_CONFLICT`

### 4.6 Strategic Assign

```http
POST /api/v1/sales-leads/{lead_id}:assign
Idempotency-Key: uuid
If-Match: "4"
```

请求：

```json
{
  "assignee_user_id": "uuid",
  "reason_code": "strategic_assignment",
  "reason_text": "指派给同区域同等级的空闲销售"
}
```

响应字段与 Claim 一致，并额外返回 `assignment_type=manual`。目标用户必须 active，且 Capacity、Tier 和 Region 全部满足；`region_unknown` Lead 不允许 Assign。当前契约不接受任何跨 Tier、跨 Region 或超 Capacity Override 字段。

### 4.7 Release/Transfer

权限：Sales 只能 Release 自己的 active Assignment；Sales 可将本人 Lead 转交给**同 Region、同 Tier** 销售（原因必填，Capability `sales_lead.transfer_own`）。Strategic Transfer/Batch Transfer 同样必须匹配目标 Sales 的 Region/Tier/Capacity；跨 Region、跨 Tier 和超 Capacity 调度随完整销售管理 Deferred。

Release：

```http
POST /api/v1/sales-leads/{lead_id}:release
Idempotency-Key: uuid
If-Match: "lead_version"
```

```json
{
  "reason_code": "capacity_rebalance",
  "reason_text": "释放回资源池，由其他销售继续跟进"
}
```

成功后 active Assignment 结束，`allocation_status=claimable`、`current_owner_user_id=NULL`。

```json
{
  "request_id": "req_xxx",
  "data": {
    "lead_id": "uuid",
    "ended_assignment_id": "uuid",
    "allocation_status": "claimable",
    "current_owner_user_id": null,
    "pipeline_stage": "engaged",
    "version": 7
  }
}
```

Transfer：

```http
POST /api/v1/sales-leads/{lead_id}:transfer
Idempotency-Key: uuid
If-Match: "lead_version"
```

```json
{
  "to_assignee_user_id": "uuid",
  "reason_code": "workload_handoff",
  "reason_text": "转交给同区域同等级销售继续跟进"
}
```

Transfer 在一个事务中结束旧 Assignment 并创建新 Assignment。目标 Sales 必须与 Lead 的 Region/Tier 匹配且未超过 Capacity；当前没有 Override 分支。

```json
{
  "request_id": "req_xxx",
  "data": {
    "lead_id": "uuid",
    "previous_assignment_id": "uuid-old",
    "new_assignment_id": "uuid-new",
    "from_owner_user_id": "uuid-sales-a",
    "to_owner_user_id": "uuid-sales-b",
    "assigned_at": "2026-07-17T02:00:00Z",
    "version": 8
  }
}
```

Batch Transfer：

```http
POST /api/v1/sales-leads:batch-transfer
Idempotency-Key: uuid
```

```json
{
  "items": [
    {
      "lead_id": "uuid-1",
      "expected_version": 5,
      "to_assignee_user_id": "uuid-sales",
      "reason_code": "workload_rebalance",
      "reason_text": "同区域同等级销售之间调整工作量"
    }
  ]
}
```

每项独立 UoW，批次只聚合结果：

```json
{
  "request_id": "req_xxx",
  "data": {
    "succeeded": [
      {
        "lead_id": "uuid-1",
        "previous_assignment_id": "uuid-old",
        "new_assignment_id": "uuid-new",
        "version": 6
      }
    ],
    "failed": [
      {
        "lead_id": "uuid-2",
        "code": "VERSION_CONFLICT",
        "message": "Sales Lead 已被其他操作更新"
      }
    ]
  }
}
```

Batch Transfer 使用与 Candidate Select 相同的可恢复两级幂等：

- Batch Parent Scope=`lead_batch_transfer`，Hash 覆盖整个有序 `items` 数组；
- Item Scope=`lead_batch_transfer_item`，Item Key=`{request_idempotency_key}:{lead_id}`；
- Item Hash 覆盖 `lead_id/expected_version/to_assignee_user_id/reason_code/reason_text`；
- 每个 Transfer UoW、Item completed 和 Item 响应同事务提交；
- 全部 Item 完成后 Parent completed；中断重试只处理无终态 Checkpoint 的 Item；
- 同一批次重复 `lead_id` 整批返回 422。

### 4.8 First Touch 和 Stage

权限：当前 active Owner 和 Strategic 可执行；未分配的 claimable Lead 不允许伪造运营阶段。

First Touch：

```http
POST /api/v1/sales-leads/{lead_id}:first-touch
Idempotency-Key: uuid
If-Match: "lead_version"
```

```json
{
  "contact_id": "uuid",
  "channel": "call",
  "occurred_at": "2026-07-17T02:00:00Z",
  "note": "首次电话接通，客户希望下周演示"
}
```

`contact_id` 必须属于 Lead 的 Company。服务端在同一事务写入 `first_touch_at=COALESCE(原值, occurred_at)`、清空 Sales Lead `sla_due_at` 并追加唯一 First Touch Transition；Assignment 上的原始 SLA 保留审计。已记录时幂等返回原结果。

```json
{
  "request_id": "req_xxx",
  "data": {
    "lead_id": "uuid",
    "transition_id": "uuid",
    "contact_id": "uuid",
    "first_touch_at": "2026-07-17T02:00:00Z",
    "pipeline_stage": "contacted",
    "version": 6
  }
}
```

显式改阶段：

```http
POST /api/v1/sales-leads/{lead_id}:change-stage
Idempotency-Key: uuid
If-Match: "lead_version"
```

```json
{
  "target_stage": "meeting",
  "reason_code": "meeting_booked",
  "reason_text": "已确认会议时间"
}
```

此接口只处理用户显式动作，`source_type=user` 由服务端写入。Email/Meeting 自动推进只能通过 Outbox Consumer 调用内部 Pipeline Command，客户端不得伪造 `source_type/source_resource_id`。

Won/Lost：

```http
POST /api/v1/sales-leads/{lead_id}:mark-won
Idempotency-Key: uuid
If-Match: "lead_version"

POST /api/v1/sales-leads/{lead_id}:mark-lost
Idempotency-Key: uuid
If-Match: "lead_version"
```

```json
{
  "reason_code": "commercial_terms_accepted",
  "reason_text": "商务条款已确认",
  "closed_at": "2026-07-17T03:00:00Z"
}
```

Won/Lost 必须提供结构化 `reason_code`；`closed_at` 可省略并由服务端取当前时间。成功响应统一返回：

```json
{
  "request_id": "req_xxx",
  "data": {
    "lead_id": "uuid",
    "transition_id": "uuid",
    "from_stage": "proposal",
    "to_stage": "won",
    "occurred_at": "2026-07-17T03:00:00Z",
    "version": 9
  }
}
```

不提供任意 `PATCH pipeline_stage`。

### 4.9 Company/Contact

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/companies/{company_id}` | Company |
| PATCH | `/api/v1/companies/{company_id}` | 允许的主数据更新 |
| GET | `/api/v1/companies/{company_id}/contacts` | Contact |
| POST | `/api/v1/companies/{company_id}/contacts` | 新增 Contact |
| PATCH | `/api/v1/contacts/{contact_id}` | 更新 Contact |
| GET | `/api/v1/sales-leads/{lead_id}/adopted-icp` | 当前销售周期采用的四维 ICP |
| GET | `/api/v1/sales-leads/{lead_id}/adopted-scale` | 当前销售周期采用的客户规模 |

---

## 5. Customer Analysis

### 5.1 Profile

```http
GET   /api/v1/companies/{company_id}/profile
PATCH /api/v1/companies/{company_id}/profile
```

PATCH 使用 `If-Match`，只允许更新显式字段。AI 报告不通过本接口自动覆盖数据。

### 5.2 MEDDPICC

```http
GET   /api/v1/companies/{company_id}/meddpicc
PATCH /api/v1/companies/{company_id}/meddpicc/{dimension_code}
```

合法 Dimension：

- `metrics`
- `economic_buyer`
- `decision_criteria`
- `decision_process`
- `paper_process`
- `identify_pain`
- `champion`
- `competition`

单维更新避免整个大 JSON 的并发覆盖。

### 5.3 生成报告

```http
POST /api/v1/companies/{company_id}/analysis-runs
Idempotency-Key: uuid
```

请求：

```json
{
  "report_type": "customer_analysis",
  "force_refresh": false,
  "trigger_type": "manual"
}
```

API 组装：

- Company Snapshot；
- Sales Lead Snapshot；
- Sales Lead Adopted 四维 ICP Snapshot；
- Sales Lead Adopted Customer Scale Snapshot；
- Profile Version/Snapshot；
- MEDDPICC Revision/Snapshot；
- Engagement Cutoff/Snapshot；
- Prompt/Schema/Model Policy；
- Input Hash。

报告可以在 Sales Lead 入池后生成，不要求已经 Assignment。

### 5.4 Run 和 Report

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/analysis-runs/{run_id}` | Run 状态 |
| POST | `/api/v1/analysis-runs/{run_id}:retry` | 失败后新建 Job，旧 Job 保持终态 |
| POST | `/api/v1/analysis-runs/{run_id}:cancel` | 取消 queued/running Run |
| GET | `/api/v1/companies/{company_id}/analysis-reports/current` | 当前报告 |
| GET | `/api/v1/companies/{company_id}/analysis-reports` | 历史 |
| GET | `/api/v1/analysis-reports/{report_id}` | 详情 |

Analysis Retry/Cancel 要求 `If-Match` 和 `Idempotency-Key`。

Report DTO 至少固定：

```text
header
summary
health_grade
intention_level
profile_snapshot
meddpicc_snapshot
icp_snapshot
scale_snapshot
market
company
competitor
pain
product
sales_guide
evidence_refs
```

禁止只返回任意 `report_payload: object` 而不定义稳定 DTO。

### 5.5 Suggestion

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/companies/{company_id}/analysis-suggestions` | 待审建议 |
| POST | `/api/v1/analysis-suggestions/{id}:accept` | 接受 |
| POST | `/api/v1/analysis-suggestions/{id}:reject` | 拒绝 |

Accept 需要 `If-Match` 或 Target Version，避免覆盖用户刚刚修改的字段。

---

## 6. Customer Operation

### 6.1 Customer Timeline

```http
GET /api/v1/companies/{company_id}/timeline
```

聚合：

- Stage Transition；
- Email；
- Meeting；
- Task；
- Customer Activity；
- Analysis Report。

Timeline 是只读 Query，不新建重复事实。

### 6.2 Email

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/companies/{company_id}/emails` | 历史 |
| POST | `/api/v1/companies/{company_id}/email-drafts` | 生成草稿 |
| GET | `/api/v1/email-messages/{email_id}` | 详情 |
| PATCH | `/api/v1/email-messages/{email_id}` | 编辑 Draft |
| POST | `/api/v1/email-messages/{email_id}:translate` | 翻译 |
| POST | `/api/v1/email-messages/{email_id}:approve` | 审批 |
| POST | `/api/v1/email-messages/{email_id}:send` | 发送 |
| POST | `/api/v1/webhooks/email/{provider_code}` | Provider Webhook |

发送要求：

- `Idempotency-Key`；
- `If-Match`；
- Contact 属于 Company；
- Address 不在 Suppression；
- Actor 有 Lead 权限；
- Provider 不确定时进入 Reconcile。

### 6.3 Meeting

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/companies/{company_id}/meetings` | 历史 |
| POST | `/api/v1/companies/{company_id}/meetings` | Multipart 上传 |
| GET | `/api/v1/meetings/{meeting_id}` | 状态/转写/摘要 |
| GET | `/api/v1/meetings/{meeting_id}/segments` | 分片 |
| GET | `/api/v1/meetings/{meeting_id}/media` | 授权媒体访问 |
| POST | `/api/v1/meetings/{meeting_id}:retry` | 新建 Job，旧 Job 保持终态 |
| POST | `/api/v1/meetings/{meeting_id}:cancel` | 取消尚未完成的处理 |
| DELETE | `/api/v1/meetings/{meeting_id}` | 逻辑删除 |

Meeting Retry/Cancel/Delete 要求 `If-Match`；Retry/Cancel 还要求 `Idempotency-Key`。

上传字段：

- `file`
- `lead_id` 可选；
- `primary_contact_id` 可选；
- `title` 可选；
- `meeting_started_at` 可选。

上传必须携带 `Idempotency-Key`。服务端在创建 Media/Meeting/Job 前计算文件 SHA-256，请求 Hash 至少覆盖：

```text
company_id
lead_id
primary_contact_id
title
meeting_started_at
file_sha256
```

相同 Key + 相同 Hash 返回原 `meeting_id/job_id`；相同 Key + 不同 Hash 返回 `IDEMPOTENCY_KEY_REUSED`。

`lead_id` 可空。任何未关联 Sales Lead 的 Meeting 都只进入 Company Timeline/Analysis，不触发 Sales CRM Pipeline。Cancel 只允许 uploaded/queued/处理中状态；Delete 只允许 completed/failed/cancelled，运行中的 Meeting 必须先 Cancel。

成功响应 202，使用通用异步 Envelope 返回 `resource_type=meeting, resource_id=meeting_id, job`。

`GET /api/v1/meetings/{meeting_id}` 的完成态响应固定为：

```json
{
  "request_id": "req_xxx",
  "data": {
    "meeting_id": "uuid",
    "company_id": "uuid",
    "lead_id": "uuid",
    "processing_status": "completed",
    "transcript_status": "done",
    "transcript_text": "...",
    "summary_schema_version": 1,
    "summary": {
      "customer_needs": ["需要覆盖亚太地区"],
      "pain_points": ["现有漫游成本高"],
      "buying_signals": ["要求试点报价"],
      "action_items": [
        {
          "task": "发送试点方案",
          "owner": "uuid-or-null",
          "due_at": "2026-07-20T08:00:00Z"
        }
      ],
      "decisions": ["先在日本团队试点"],
      "risks": ["预算尚未审批"],
      "keywords": ["eSIM", "APAC"],
      "next_step": "发送试点方案并确认演示时间"
    },
    "version": 3
  }
}
```

Summary v1 是封闭 DTO：六个 `array<string>` 字段、`action_items` 对象数组和 `next_step: string|null`；八个 Key 在完成态全部存在，空数组写 `[]`。处理未完成或失败/取消时 `summary=null`，仍返回 `summary_schema_version=1`。数据库 Generated Column 不作为重复 API 字段返回。

### 6.4 Task

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/follow-up-tasks` | 列表 |
| POST | `/api/v1/companies/{company_id}/follow-up-tasks` | 创建 |
| PATCH | `/api/v1/follow-up-tasks/{task_id}` | 编辑未完成任务 |
| POST | `/api/v1/follow-up-tasks/{task_id}:complete` | 完成 |
| POST | `/api/v1/follow-up-tasks/{task_id}:cancel` | 取消 |

`overdue` 是查询派生状态，不作为 PATCH 值。

### 6.5 Activity

```http
POST /api/v1/companies/{company_id}/activities
```

请求：

```json
{
  "lead_id": "uuid",
  "activity_type": "call",
  "direction": "outbound",
  "subject": "首次电话沟通",
  "body": "客户要求补充 API 文档",
  "outcome_code": "follow_up_required",
  "occurred_at": "2026-07-16T08:00:00Z"
}
```

---

### 6.6 手动记录（v3.4 新增，v3.5 修订）

```http
POST   /api/v1/companies/{company_id}/manual-notes    # 创建手动记录
GET    /api/v1/companies/{company_id}/manual-notes    # 查询手动记录列表
GET    /api/v1/manual-notes/{note_id}                 # 获取单条记录详情（含提取结果）
POST   /api/v1/manual-notes/{note_id}:confirm         # 批量确认提取结果
POST   /api/v1/manual-notes/{note_id}:discard         # 弃用提取结果
POST   /api/v1/manual-notes/{note_id}:retry-extract   # 重试提取
```

创建手动记录：

```http
POST /api/v1/companies/{company_id}/manual-notes
Idempotency-Key: uuid
```

```json
{
  "raw_text": "今天在展会上碰到他们CTO，聊到他们Q3要扩容东南亚团队，决策人其实是CFO不是CTO，预算大概5万美金以内"
}
```

系统响应（202 + job_id）：

```json
{
  "note_id": "uuid",
  "raw_text": "原文...",
  "confirm_status": "pending",
  "job": {
    "job_id": "uuid",
    "job_type": "manual_note.extract.v1",
    "status": "queued",
    "status_url": "/api/v1/jobs/uuid",
    "events_url": "/api/v1/jobs/uuid/events"
  }
}
```

提取完成后 SSE 推送确认卡片结构（提取结果）。确认为**批量确认**：前端默认整批采纳提取值，销售可展开逐条调整 `action` 或编辑值后一次提交。确认请求：

```http
POST /api/v1/manual-notes/{note_id}:confirm
Idempotency-Key: uuid
If-Match: "note_version"
```

```json
{
  "confirmed_fields": [
    { "index": 0, "action": "accept" },
    { "index": 1, "action": "keep_original" },
    { "index": 2, "action": "edit", "edited_value": "CFO" }
  ]
}
```

`action` 枚举：`accept`（采纳提取值）/ `keep_original`（保留原值）/ `edit`（使用 edited_value）。服务端按提取时记录的 `target_version` 逐项校验目标字段版本，已被他人更新返回 409 `VERSION_CONFLICT`，不静默覆盖。

确认后系统写入 `customer_profile` 或 `customer_meddpicc_dimension`，创建 `analysis_report` 新版本，报告对应段落标注"信息更新于 YYYY-MM-DD 销售手动记录"。

验收标准：
- [ ] 手动记录 API 入口在 Customer Operation 模块下
- [ ] 提取失败时 `raw_text` 不丢失，可通过 retry-extract 重试
- [ ] 确认卡片默认整批采纳（批量确认），销售可展开逐条调整；冲突项提供"覆盖/保留原值/编辑"选择
- [ ] 目标字段版本冲突返回 409，不静默覆盖
- [ ] 确认后触发分析报告重新生成，旧版本保留

---

## 7. Job 和 Read Model

### 7.1 Job

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/jobs/{job_id}` | 状态、Attempt 摘要、Progress |
| GET | `/api/v1/jobs/{job_id}/events` | SSE |
| POST | `/api/v1/ops/jobs/{job_id}:retry` | Strategic/运维排障入口 |
| POST | `/api/v1/ops/jobs/{job_id}:cancel` | Strategic/运维排障入口 |

业务界面必须优先调用 Search Run、Enrichment Run、Analysis Run、Meeting、Email 等资源命令。`/ops/jobs/*` 不能直接更新 Job 行，而是根据 `aggregate_type` 委托所属模块的 Retry/Cancel Application Port，在同一事务中更新领域资源和 Job。

人工 Retry 的响应包含：

```json
{
  "request_id": "req_xxx",
  "data": {
    "resource_type": "analysis_run",
    "resource_id": "uuid",
    "previous_job_id": "uuid-old",
    "current_job_id": "uuid-new",
    "status": "queued"
  }
}
```

旧 Job 保持 `failed_final/cancelled`，新 Job 使用 `retry_of_job_id` 建立历史链。禁止把旧 Job 从终态改回 queued。

### 7.2 Workspace/Dashboard

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/workspaces/sales` | Sales 工作台 |
| GET | `/api/v1/workspaces/strategic` | Strategic 工作台 |
| GET | `/api/v1/dashboards/lead-funnel` | 搜索/候选/入池 Funnel |
| GET | `/api/v1/dashboards/allocation` | Pool/Capacity/SLA |
| GET | `/api/v1/dashboards/pipeline` | Pipeline Funnel |
| GET | `/api/v1/companies/{company_id}/360` | Customer 360 |

Dashboard 返回真实聚合，不使用静态演示数字作为成功兜底。

---

## 8. 错误码

| HTTP | Code | 场景 |
|---:|---|---|
| 400 | `INVALID_COMMAND` | 参数组合错误 |
| 400 | `DIALOGUE_QUERY_EMPTY` | 空 Query |
| 401 | `AUTHENTICATION_REQUIRED` | 未登录 |
| 401 | `AUTH_INVALID_CREDENTIALS` | 用户名或密码错误 |
| 403 | `USER_DISABLED` | 账号已安全禁用 |
| 403 | `USER_DEPARTED` | 销售账号已离职 |
| 403 | `USER_LOCKED` | 账号登录锁定，30 分钟后自动恢复 |
| 403 | `PERMISSION_DENIED` | Capability 不足 |
| 404 | `RESOURCE_NOT_FOUND` | 不存在或不可见 |
| 409 | `VERSION_CONFLICT` | 乐观锁冲突 |
| 409 | `IDEMPOTENCY_KEY_REUSED` | 相同 Key 对应不同 Request Hash |
| 409 | `IDEMPOTENCY_IN_PROGRESS` | 相同命令正在执行或可恢复批次未取得执行锁 |
| 409 | `SALES_LEAD_NOT_CLAIMABLE` | 已被领取/不可领取 |
| 409 | `ACTIVE_ASSIGNMENT_EXISTS` | 已有 active Assignment |
| 409 | `ACTIVE_ASSIGNMENT_NOT_FOUND` | Release/Transfer 时没有 active Assignment |
| 409 | `TRANSFER_TARGET_UNCHANGED` | Transfer 目标与当前负责人相同 |
| 409 | `USER_ALREADY_DEPARTED` | 目标销售已经离职 |
| 409 | `CANDIDATE_ALREADY_PROMOTED` | 已入池 |
| 409 | `CANDIDATE_ALREADY_MERGED` | Source 已被合并 |
| 409 | `MERGE_TARGET_NOT_CANONICAL` | Target 已合并或形成 Merge Chain |
| 409 | `ENRICHMENT_ALREADY_ACTIVE` | Candidate 已有 queued/running Enrichment Run |
| 422 | `CANDIDATE_NOT_READY` | 缺 ICP/Scale |
| 422 | `SCENE_NOT_SUPPORTED` | 当前只支持 S1/S2/S3；S4/S5 Deferred |
| 422 | `CANDIDATE_ASSESSMENTS_STALE` | Candidate 合并/刷新后尚未完成重评 |
| 422 | `PROMOTION_OVERRIDE_REASON_REQUIRED` | Strategic Override 未填写原因 |
| 422 | `ICP_HARD_GATE_FAILED` | 硬门槛失败 |
| 422 | `SALES_TIER_MISMATCH` | Tier 不匹配 |
| 422 | `SALES_REGION_MISMATCH` | Sales Region 与 Lead Pool Region 不匹配 |
| 422 | `SALES_CAPACITY_EXCEEDED` | 容量超限 |
| 422 | `TARGET_NOT_SALES` | Depart/Assign 目标不是 Sales 账号 |
| 422 | `USER_NOT_ACTIVE` | Assign/Transfer 的目标销售不是 active 状态 |
| 422 | `ASSIGNEE_NOT_AVAILABLE` | 目标销售禁用、离职、登录锁定或无有效容量 |
| 422 | `CONTACT_COMPANY_MISMATCH` | Contact 不属于 Lead 的 Company |
| 422 | `INVALID_STAGE_TRANSITION` | 非法 Stage |
| 422 | `RESOURCE_NOT_RETRYABLE` | 当前领域资源不允许 Retry |
| 422 | `RESOURCE_NOT_CANCELLABLE` | 当前领域资源不允许 Cancel |
| 422 | `EMAIL_SUPPRESSED` | 退订/退信 |
| 422 | `EMAIL_NOT_SENDABLE` | 邮件状态不合法 |
| 422 | `MEDIA_VALIDATION_FAILED` | 文件校验失败 |
| 429 | `RATE_LIMITED` | 应用限流 |
| 429 | `PROVIDER_RATE_LIMITED` | Provider 限流 |
| 503 | `PROVIDER_UNAVAILABLE` | Provider 不可用 |

业务规则拒绝通常使用 409 或 422，不把 `REGION_SCOPE_DENIED` 错写成通用 403；403 表示账户根本没有该能力。

---

## 9. 明确禁止的旧 API

| 旧路径/模式 | 处置 |
|---|---|
| `/api/leads/import` | 删除 |
| `/api/leads/manual` | 删除 |
| `/api/leads/apollo-search` | 删除独立入口；Apollo 仅由对话搜索内部 Provider Adapter 调用 |
| `crawl_c_upgrade` | 删除 |
| `/api/lead-discovery/validation-companies/promote-to-analysis` | 替换为 `/lead-candidates:select` |
| `/api/enriched-companies/*` | 删除 |
| `/api/analysis/icp/*` | 删除六维 ICP |
| `/internal/events/*` | 删除模块间 HTTP |
| `/api/email/*` 兼容路径 | 切换后删除 |
| `/api/meeting/*` 兼容路径 | 切换后删除 |
| `PATCH /pipeline` 任意改状态 | 替换为业务命令 |
| 前端传 owner/user_id | 拒绝 |

---

## 10. 契约验收

- [ ] Candidate Select 返回 candidate/company/lead ID Mapping。
- [ ] 客户端不能指定 Provider；Web Search/Apollo 每次调用在 Search Run 中可追溯，单 Provider 失败可返回 partial。
- [ ] Claim 使用 Sales Lead ID，不使用 Candidate ID。
- [ ] Claim 并发冲突返回 409。
- [ ] Release 后 Pool 查询可再次看到 Lead。
- [ ] Strategic 可分页筛选全局 Sales Lead，并直接执行 Assign/Transfer。
- [ ] Batch Transfer 每项携带 expected_version，并允许部分成功。
- [ ] First Touch/Stage/Won/Lost 使用结构化命令而非任意 PATCH。
- [ ] ICP DTO 当前只接受 S1/S2/S3；S4/S5 返回 `SCENE_NOT_SUPPORTED` 且不创建 Run/Job/Assessment。
- [ ] Scale DTO 支持 8.75 等小数。
- [ ] Report DTO 明确定义五模块。
- [ ] Profile/MEDDPICC Suggestion 有 Accept/Reject。
- [ ] Email Send 有 Idempotency 和 Reconcile。
- [ ] Meeting 有 Transcript、Segment、Summary 和 Retry。
- [ ] SSE 支持 Last-Event-ID。
- [ ] 所有 Company Operation 使用正式 Company/Lead/Contact ID。
- [ ] IAM 提供账号管理 API（创建/禁用/启用/解锁/重置密码）；连续 5 次密码失败锁定 30 分钟并告警。
- [ ] 账号类型只有 Sales/Strategic，不返回 `is_boss` 或第三种管理角色。
- [ ] Strategic Depart 在一个事务内禁止登录、结束全部 active Assignment 并让 Lead 保留原区域×等级、区域映射版本和分配规则版本快照回池；不创建审批、Handover 或 Job。
- [ ] Disable 只撤销登录，既有 Assignment、Task Assignee 和业务 Job 不变。
- [ ] Sales 只能向同 Region、同 Tier 销售转交本人 Lead；Strategic Assign/Batch Transfer 同样不得跨 Region/Tier 或超过 Capacity。
- [ ] 手动记录默认批量确认；目标字段版本冲突返回 409。
- [ ] 邮件 opened/clicked 由 Webhook 推进并触发 I1 加分；A4 升级只触发一次 Analysis Run 和跟进 Task。
- [ ] 3 个工作日未首触达的 Lead 被自动释放并通知原销售。

完整销售管理 API（等级调整、离职申请审批、复杂交接、池子健康度）的验收随 §11 Deferred；当前 Strategic 直接离职回池按 §2.3 验收。

---

## 11. 完整销售管理 API（Deferred）

> **Deferred**：当前不实现等级调整、离职申请审批、复杂交接待办、销售健康度或自动晋升，不为这些能力预建 Router、空 Service、表或前端菜单。当前 Strategic 直接离职回池是 §2.3 的 `POST /users/{user_id}:depart`，不属于本节，也不依赖 `handover_request`。

未来若纳入范围，需要重新评审并显式启用：

- 销售等级调整与历史；
- 离职申请、审批与逐客户交接；
- 交接 SLA 和超时提醒；
- 销售名册、池子健康度和人员容量规划；
- 返聘或 departed 账号重新激活。

在正式启用前，不保留任何 `/api/v1/sales-management/*` 当前契约。

以下只是未来边界，不属于当前 `/api/v1` 实现和验收范围：

```text
POST /api/v1/strategic-directives
POST /api/v1/strategic-directives/{id}:activate
GET  /api/v1/strategic-directives/current

POST /api/v1/lead-collection-campaigns
POST /api/v1/lead-collection-campaigns/{id}:start
POST /api/v1/lead-collection-campaigns/{id}:pause
POST /api/v1/lead-collection-campaigns/{id}:replan
GET  /api/v1/lead-collection-campaigns/{id}
GET  /api/v1/dashboards/strategy-resources
```

未来契约要求：

- 创建 Directive 时区域比例必须合计 100%；
- Campaign 保存 Directive Version/Snapshot；
- Replan 必须携带 Expected Version 和原因；
- Campaign 只创建 Search Run，不绕过 Candidate Selection；
- Dashboard 返回区域目标、实际资源、质量、缺口和趋势；
- Directive/Campaign 不直接指定 Sales Owner。
