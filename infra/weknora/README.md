# LTC 的 WeKnora 自托管部署

这里保留 WeKnora 的运行依赖，不把官方的大型 Compose 文件直接复制到 LTC 根目录。服务使用官方 `v0.7.2` 镜像，LTC 只通过 HTTP 检索接口读取知识片段。

## 集成启动（推荐）

先在仓库根目录创建 `.env`，至少填写 LTC 数据库和 JWT 配置；WeKnora 的密钥也必须替换为真实随机值。然后执行：

```bash
docker compose -f compose.yaml -f infra/weknora/compose.yaml up -d
```

访问：

- LTC Web：`http://localhost:5173`
- WeKnora 管理界面：`http://localhost:18080`
- WeKnora API（仅用于初始化/调试）：`http://localhost:18081`

这里的 `api` 和 `weknora-app` 在同一个 Compose 网络中，LTC API 使用容器地址 `http://weknora-app:8080`，不依赖宿主机回环地址。

## 首次初始化

1. 打开 WeKnora 管理界面，注册一个管理员账号并登录。
2. 在 WeKnora 中配置可用的 embedding/LLM 模型。没有 embedding 模型时，知识可以上传但无法完成向量检索。
3. 创建两个知识库，例如“案例库”和“话术库”，上传对应文档并等待处理完成。
4. 在账户信息或空间 API Key 页面创建一个 `viewer` API Key；如果需要限制访问范围，创建时只授权这两个知识库。
5. 把 API Key 和知识库 ID 写入仓库根目录 `.env`：

```env
LTC_WEKNORA_BASE_URL=http://weknora-app:8080
LTC_WEKNORA_API_KEY=sk-...
LTC_WEKNORA_KNOWLEDGE_BASE_IDS=<案例库ID>,<话术库ID>
```

重启 LTC API 使配置生效：

```bash
docker compose -f compose.yaml -f infra/weknora/compose.yaml up -d --force-recreate api
```

## 独立启动 WeKnora

如果 LTC API 不在同一个 Compose 项目中运行：

```bash
cp infra/weknora/.env.example infra/weknora/.env
docker compose --env-file infra/weknora/.env -f infra/weknora/compose.yaml up -d
```

这时 LTC API 使用宿主机地址：

```env
LTC_WEKNORA_BASE_URL=http://localhost:18081
```

若 LTC API 也在另一个容器中运行，请使用两个项目共享的 Docker network，并将 `LTC_WEKNORA_BASE_URL` 改为可解析的 WeKnora 服务地址；不要在容器内使用 `localhost` 指向另一个容器。

## LTC 侧验证

登录 LTC 后，进入“数据库”的“案例库”或“话术库”搜索。也可以直接调用：

```bash
curl -X POST http://localhost:8000/api/v1/knowledge/search \
  -H 'Authorization: Bearer <ltc-access-token>' \
  -H 'Content-Type: application/json' \
  -d '{"query":"日本商旅客户首次触达话术","limit":10}'
```

WeKnora 的 API Key 只保存在 LTC 后端环境变量，不下发到浏览器。WeKnora 不访问 LTC PostgreSQL，也不写入 `company`、`sales_lead`、`meeting` 等业务事实表；需要改变业务数据时仍必须走 LTC API 的权限和审计链路。
