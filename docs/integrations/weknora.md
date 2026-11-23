# WeKnora 知识检索接入

自托管运行文件位于 [`infra/weknora`](../../infra/weknora/README.md)。推荐使用组合 Compose 启动 LTC 和 WeKnora；生产部署请固定 `WEKNORA_VERSION`，不要直接使用 `latest`。

LTC 通过后端适配器调用 WeKnora 的只读检索接口，WeKnora 不直接访问或修改 LTC PostgreSQL 业务表。

## 配置

在部署环境设置：

```env
LTC_WEKNORA_BASE_URL=http://weknora-app:8080
LTC_WEKNORA_API_KEY=sk-<viewer-api-key>
LTC_WEKNORA_KNOWLEDGE_BASE_IDS=kb-cases,kb-scripts
LTC_WEKNORA_TIMEOUT_SECONDS=20
```

`LTC_WEKNORA_KNOWLEDGE_BASE_IDS` 是默认知识库列表；请求也可以临时传入知识库 ID。未配置时，LTC 返回 `503 KNOWLEDGE_NOT_CONFIGURED`；WeKnora 不可用时返回 `502 KNOWLEDGE_PROVIDER_UNAVAILABLE`。

API Key 应在 WeKnora 中创建为 `viewer`，并且只授权 LTC 需要检索的知识库。不要把 WeKnora API Key 放到前端代码、浏览器 localStorage 或提交到 Git；它只由 LTC 后端通过 `X-API-Key` 调用 WeKnora。

如果 LTC API 在宿主机直接运行（例如 `./start.sh`），将地址改为 `http://localhost:18081`；容器内不能用 `localhost` 访问另一个容器。

## API

```http
POST /api/v1/knowledge/search
Authorization: Bearer <ltc-access-token>
Content-Type: application/json
```

```json
{
  "query": "日本商旅客户首次触达话术",
  "limit": 10
}
```

页面入口是现有“数据库”下的“案例库”和“话术库”。静态案例和话术仍保留为离线兜底，搜索结果展示 WeKnora 返回的片段、来源文件和相似度。

## 数据边界

- LTC PostgreSQL 继续保存公司、线索、客户、会议和跟进任务等业务事实。
- WeKnora 只保存用于检索的知识内容，例如案例、话术、产品文档和流程说明。
- 任何需要改变客户状态或业务字段的动作，必须经过 LTC API 和现有权限/审计链路。
