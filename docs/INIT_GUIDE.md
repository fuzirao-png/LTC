# LTC 本地开发环境初始化指南

## 适用对象

测试人员、部署工程师、新加入的开发者。

## 前置条件

- Docker Desktop (Mac/Windows) 或 Docker Engine + Docker Compose (Linux)
- Git
- 至少 4GB 可用内存

## 快速启动

```bash
# 1. 克隆仓库并进入目录
cd LTC

# 2. 初始化数据库表结构（仅首次）
docker compose run --rm database-init

# 3. 启动全部服务（API + Web + PostgreSQL）
docker compose up -d

# 4. 等待 API 健康检查通过
until curl -s http://localhost:8000/health/live | grep -q ok; do sleep 1; done
echo "API ready"

# 5. 播种演示数据（可重复执行，自动清理旧种子数据）
docker compose exec api python -m ltc.scripts.seed_dev_data
```

服务端口：

| 服务 | 地址 | 说明 |
|------|------|------|
| Web 前端 | http://localhost:5173 | Vue 3 SPA |
| API 后端 | http://localhost:8000 | FastAPI REST |
| API 文档 | http://localhost:8000/docs | Swagger UI |
| PostgreSQL | localhost:55432 | 数据库直连（调试用） |

## 种子数据说明

运行 `seed_dev_data` 后，数据库中会有：

### 演示账号

所有演示账号密码统一为 **`123456`**（仅开发环境，与原型一致）。

| 账号 | 角色 | 区域 | 等级 | 容量 | 看到哪些线索 |
|------|------|------|------|------|-------------|
| `boss.admin` | 战略 | - | - | - | 全部(经营视角) |
| `strategy.ops` | 战略 | - | - | - | 全部(经营视角) |
| `li.ming` | 销售 | 东亚(EA) | MA | 10 | Sakura Travel, Osaka CS, Pacific TMC |
| `wang.fang` | 销售 | 北美(NA) | MA | 10 | TechVentures |
| `zhao.lei` | 销售 | 东亚(EA) | SA | 15 | Kyoto Business Travel |
| `chen.jie` | 销售 | 东南亚(SEA) | A | 20 | SingTel Connect, Bangkok Logistics |

### 区域×等级 销售池矩阵

每个销售**只能看到**与自己 `(region_code, sales_tier)` 匹配的线索：

```
              MA                    SA                A
EA    Sakura Travel           Kyoto BT
      Osaka CS
      Pacific TMC

NA    TechVentures             GlobalTrade

SEA                                                   SingTel Connect
                                                      Bangkok Logistics
```

## 多账号验证测试

用不同账号登录，确认看到的销售池不同：

```bash
# 1. 以 li.ming (MA/EA) 登录
TOKEN=$(curl -s -c /tmp/cookies.txt -b /tmp/cookies.txt \
  http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"li.ming","password":"123456"}' | \
  python3 -c "import json,sys; print('ok')")

# 2. 查看他能看到的线索池
curl -s -b /tmp/cookies.txt http://localhost:8000/api/v1/sales-leads/pool | \
  python3 -c "
import json,sys
data=json.load(sys.stdin)['data']
for item in data:
    print(f\"  {item['company_name']:30s} tier={item['required_sales_tier']} region={item['pool_region_code']}\")
"

# 预期输出: 3 条线索，全部是 MA/EA

# 3. 换 chen.jie (A/SEA) 登录
curl -s -c /tmp/cookies2.txt -b /tmp/cookies2.txt \
  http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"chen.jie","password":"123456"}'

# 4. 查看他的池
curl -s -b /tmp/cookies2.txt http://localhost:8000/api/v1/sales-leads/pool | \
  python3 -c "
import json,sys
data=json.load(sys.stdin)['data']
for item in data:
    print(f\"  {item['company_name']:30s} tier={item['required_sales_tier']} region={item['pool_region_code']}\")
"

# 预期输出: 2 条线索，全部是 A/SEA
```

## 权限模型

```
战略账号 (account_type='strategic')
  ├── 查看全部用户列表    GET /api/v1/users
  ├── 创建/管理用户       POST/PATCH /api/v1/users/*
  ├── 查看全部线索        GET /api/v1/sales-leads
  ├── 分配线索            POST /api/v1/sales-leads/{id}:assign
  ├── 批量转交            POST /api/v1/sales-leads:batch-transfer
  └── 人员离职处理        POST /api/v1/users/{id}:depart

销售账号 (account_type='sales')
  ├── 查看自己的线索池    GET /api/v1/sales-leads/pool   (过滤 region+tier)
  ├── 查看我的线索        GET /api/v1/sales-leads/mine
  ├── 认领线索            POST /api/v1/sales-leads/{id}:claim (校验 region+tier)
  ├── 释放线索            POST /api/v1/sales-leads/{id}:release
  ├── 首次触达            POST /api/v1/sales-leads/{id}:first-touch
  └── 阶段变更            POST /api/v1/sales-leads/{id}:change-stage
```

## 重置数据

```bash
# 重新播种（UPDATE 模式，不删除已有数据）
docker compose exec api python -m ltc.scripts.seed_dev_data

# 完全重置数据库（删除全部数据，重新建表）
docker compose down -v
docker compose run --rm database-init
docker compose up -d
docker compose exec api python -m ltc.scripts.seed_dev_data
```

## 常用接口测试

```bash
BASE="http://localhost:8000/api/v1"

# --- 健康检查 ---
curl $BASE/../health/live        # API 存活
curl $BASE/../health/ready       # API 就绪（含 DB 连接检查）

# --- IAM 接口 ---
# 登录
curl -c /tmp/cookies.txt $BASE/auth/login -H 'Content-Type: application/json' \
  -d '{"username":"boss.admin","password":"123456"}'

# 查看当前用户
curl -b /tmp/cookies.txt $BASE/auth/me

# 查看用户列表
curl -b /tmp/cookies.txt "$BASE/users?region_code=EA&sales_tier=MA"

# --- Sales CRM 接口 ---
# 查看线索池（销售视角，自动过滤）
curl -b /tmp/cookies.txt $BASE/sales-leads/pool

# 查看我的线索
curl -b /tmp/cookies.txt $BASE/sales-leads/mine

# 查看全部线索（战略视角）
curl -b /tmp/cookies.txt $BASE/sales-leads
```

## 常见问题

### 1. 端口冲突
```bash
# 修改 .env 文件中的端口
LTC_API_PUBLISHED_PORT=8001
LTC_WEB_PUBLISHED_PORT=5174
LTC_DB_PUBLISHED_PORT=55433
```

### 2. 数据库连接失败
```bash
# 确认 postgres 容器已启动
docker compose ps postgres

# 查看数据库日志
docker compose logs postgres
```

### 3. 登录失败 "AUTH_INVALID_CREDENTIALS"
```bash
# 确认已运行种子脚本
docker compose exec api python -m ltc.scripts.seed_dev_data
```

### 4. 销售池为空
- 确认当前登录的是销售账号（而非战略账号）
- 销售的 `sales_tier` 和 `region_code` 必须匹配线索的 `required_sales_tier` 和 `pool_region_code`
- 如果销售容量已满（`capacity_limit` 达到上限），池也会为空
