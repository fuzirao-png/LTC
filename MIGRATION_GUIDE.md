# v3.6 Migration Guide

## 当前 LTC 目录结构

```
LTC/
  apps/                         ← v3.6 新代码，唯一运行时
    api/src/ltc/
      modules/                    ← 5 个业务模块 (iam/lead_intelligence/sales_crm/
      │                               customer_analysis/customer_operation)
      │                             + read_models
      │                            每个模块: interfaces → application → domain → infrastructure
      platform/                    ← 平台能力: jobs/idempotency/events/media/auth...
    web/src/                      ← Vue 3 FSD 前端: entities/features/shared
    worker/src/ltc_worker/        ← Worker: handlers/ + lease/registry/runtime

  db/                            ← PostgreSQL 16 Migration + Seed
    migrations/0001_v3_6_initial.sql  ← 42 张表, 3 个视图, 11 函数, 24 触发器
    seeds/0001_region_country_v5.sql  ← 6 区 205 国家/地区幂等 Seed

  contracts/                     ← OpenAPI 3.1 契约 + SHA256 基线
  tests/                         ← contract / integration / unit / e2e
  docs/architecture/v3.6/        ← 唯一架构事实源 (6 份文档)

  ── 以下为旧代码，只读，仅作迁移提取来源 ──
  clue_agent/                    → apps/api/modules/lead_intelligence
  customer-analysis-agent/       → apps/api/modules/customer_analysis
  customer-operation-agent/      → apps/api/modules/customer_operation
  Customer Allocation/           → apps/api/modules/sales_crm
  meeting-analysis-service/      → apps/worker/handlers/

  archive/                       ← 已归档旧产物，不参与构建
```

## 迁移原则

### 只能做的事

- 从旧服务读取算法逻辑、prompt 结构、输出 schema
- 参考旧代码理解业务意图和数据流
- 复用旧代码中的纯函数（提取后放到新模块 domain 层或 infrastructure 层）

### 不能做的事

- 在新代码中 `import` 旧服务模块
- 通过 localhost HTTP 调用旧服务
- 在新模块里写旧服务的表名、路由或文件路径
- 把旧服务的数据库连接或配置复制到新模块

## 迁移步骤 (每个旧服务)

### 1. 理解阶段

1. 阅读该旧服务的 `.MIGRATION_SOURCE` 标记文件，确认迁移目标和目标模块
2. 阅读 `docs/architecture/v3.6/` 中对应模块的规范
3. 在旧代码中找到核心算法、入口函数和输出结构

### 2. 提取阶段

4. 在目标模块中建立四层骨架：
   - `domain/` — 纯领域模型、值对象、领域事件
   - `application/` — Use Case 类、命令/查询处理器
   - `infrastructure/` — Provider Adapter、Repository 实现
   - `interfaces/` — FastAPI Router、请求/响应 Schema

5. 提取旧代码逻辑：
   - 纯函数 → `domain/`
   - API 调用逻辑 → `infrastructure/` 的 Provider Port 实现
   - 请求处理流程 → `application/` 的 Use Case
   - HTTP 端点 → `interfaces/` 的 Router

### 3. 接入阶段

6. 在 `modules/registry.py` 确认模块的表归属正确
7. 如果是长任务，在 `apps/worker/src/ltc_worker/handlers/` 创建 Handler
8. 写集成测试，确保迁移前后的关键输出一致

### 4. 清理阶段

9. 数据核对通过后，将旧服务目录移到 `archive/legacy/`
10. 删除旧服务中的 `.MIGRATION_SOURCE` 标记

## 旧服务 → 新模块映射

| 旧目录 | 新模块 | 核心能力 |
|---|---|---|
| `clue_agent/` | `lead_intelligence` | 对话搜索、Web Search/Apollo Provider、候选抽取、ICP 评分、客户规模 |
| `Customer Allocation/` | `sales_crm` | Pool 视图、Claim/Assign/Release/Transfer、Depart 回池 |
| `customer-analysis-agent/` | `customer_analysis` | Profile、MEDDPICC、分析报告、Sales Guide |
| `customer-operation-agent/` | `customer_operation` | 邮件草稿、发送、会议、任务、手动记录 |
| `meeting-analysis-service/` | Worker handlers | 音频处理、分片 ASR、转写、摘要 |

## 模块四层结构

```
apps/api/src/ltc/modules/<name>/
  interfaces/     ← FastAPI Router, Request/Response DTO
  application/    ← Use Case (无框架依赖), Command/Query
  domain/         ← Entity, Value Object, Domain Event, Port 接口
  infrastructure/ ← Repository 实现, Provider Adapter, 外部 API 调用
```

### 依赖方向 (必须遵守)

```
interfaces → application → domain
                ↓
           infrastructure → domain (实现 Port)
```

- `domain` 不能引用 FastAPI、SQLAlchemy、HTTP 库
- `application` 只能调用 domain 类型和 infrastructure 的 Port 接口
- `infrastructure` 实现 domain 中定义的 Port，可以引用任何外部库

## 迁移检查清单

在声称某个能力"迁移完成"前：

- [ ] 旧服务的所有核心业务逻辑都有对应的新实现
- [ ] 没有 import 旧服务代码
- [ ] 没有 localhost HTTP 调用穿越到旧服务
- [ ] 新模块表归属与 registry.py 一致
- [ ] 跨模块协调走 Application Port/UoW，异步走 Outbox
- [ ] 集成测试覆盖关键路径
- [ ] 旧数据核对通过
- [ ] 旧服务目录已归档
