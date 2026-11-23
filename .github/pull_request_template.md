## 变更概要

<!-- TL;DR: 改了什么，为什么这样改 -->

---

## 架构合规自检

_每一项都必须在提交前确认。CI 也会在这些维度上自动检查你的 PR。_

### 模块边界

- [ ] 新代码放在正确的模块 (`iam` / `lead_intelligence` / `sales_crm` / `customer_analysis` / `customer_operation`) 和正确的层 (`interfaces` / `application` / `domain` / `infrastructure`)
- [ ] 没有跨模块直接 import ORM Repository（跨模块同步走 Application Port/UoW）
- [ ] 没有从新代码 import 旧服务 (`clue_agent/`, `Customer Allocation/` 等) 或用 localhost HTTP 调旧服务

### 依赖方向

- [ ] `domain/` 没有引用 FastAPI、SQLAlchemy、HTTP 库
- [ ] `application/` 没有引用 FastAPI、SQLAlchemy，也没有直接引用 `infrastructure` 实现

### 范围约束

- [ ] 没有引入 S4/S5、Manager/Boss、离职审批、Handover、跨池 Override 等 Deferred 内容
- [ ] Apollo 没有作为独立 API 入口暴露

---

## 数据库

- [ ] 没有新增表/字段，或者——

_如果新增了表/字段：_
- [ ] 已更新 `docs/architecture/v3.6/04-数据模型设计.md`
- [ ] 已新增编号 Migration（**禁止修改** `db/migrations/0001_v3_6_initial.sql`）
- [ ] 已在 `modules/registry.py` 中声明表归属
- [ ] 已更新 `contracts/v3.6.sha256` 校验和

---

## API

- [ ] 没有新增/修改接口，或者——

_如果新增/修改了接口：_
- [ ] 已更新 `contracts/openapi/LTC_OpenAPI_v3.6.yaml`
- [ ] 已在 `contracts/v3.6.sha256` 同步校验和

---

## 测试

- [ ] `make test` 全部通过（或单步 `make contract-architecture` / `make api-test` 等）

---

## 部署

- [ ] 没有新增环境变量，或已同步 `.env.example`
- [ ] 没有提交 `.env`、Token、密码
