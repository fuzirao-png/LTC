# LTC 前端 Vue 工程化迁移说明

## 当前策略

当前采用并行迁移策略：

- `index.html`：旧版静态单页，暂时保留为服务器 demo 兜底入口。
- `app.html`：新版 Vue 3 + Vite 工程化入口。
- `src/`：新版页面、组件、store、API service 的长期维护目录。

在新版链路稳定前，不直接删除旧 `index.html`，避免影响服务器当前演示。

## 新版目录约定

```text
src/
  main.ts                 Vue 应用启动入口
  App.vue                 应用根组件
  router/index.ts         页面路由
  layouts/MainLayout.vue  主布局
  components/
    layout/               侧边栏、顶部栏
    common/               通用表格、状态标签、页面区块
    allocation/           客户分配业务组件
    operation/            客户运营业务组件
  config/runtime.ts       兼容 runtime-config.js / APP_CONFIG 的运行配置
  services/               后端 API 封装
  stores/                 Pinia 状态管理
  views/                  页面级组件
```

## 已迁入 Vue 的页面

- 总览：`src/views/DashboardView.vue`
- 登录：`src/views/LoginView.vue`
- 战略视角：`src/views/StrategyView.vue`，已迁移实时管理看板，展示收集、分析、分配指标、A/B 占比、领取率、区域分布和质量判断。
- 线索收集：`src/views/LeadCollection.vue`，已接入 `dialogue-search/stream` NDJSON 流式搜索，支持非流式兜底；支持勾选候选线索并加入分析池、同步客户分配池。
- 线索分析：`src/views/LeadAnalysis.vue`
- 客户分配：`src/views/CustomerAllocation.vue`
- 客户运营：`src/views/CustomerOperation.vue`，已接入客户列表、客户详情、联系人、邮件历史、会议历史、待办；支持邮件生成、翻译、发送；支持在客户详情内上传会议文件并刷新会议历史。
- 会议分析：`src/views/MeetingAnalysis.vue`，已接入客户选择、会议文件上传、任务轮询、历史摘要、转写和待办展示。

## 已抽离的接口层

- `src/services/leadApi.ts`
  - 分析池列表
  - 验证池列表
  - ICP 系统判断补生成
  - 对话式线索搜索
  - NDJSON 流式事件解析
  - 验证池候选线索加入分析池
- `src/services/allocationApi.ts`
  - 登录、登出、当前用户
  - 可领取线索、我的线索、管理视角全部分配线索
  - 领取线索
  - 接收 `customer.assigned` 事件并写入销售线索池
- `src/services/operationApi.ts`
  - 客户运营服务 HTTP client
  - 运营客户导出列表
  - 客户运营详情
  - 邮件历史
  - 会议历史
  - 邮件生成、翻译、发送
- `src/services/meetingApi.ts`
  - 会议上传
  - 会议任务状态
  - 会议历史记录
  - 删除会议记录

## 已抽离的状态层

- `src/stores/auth.ts`
  - 当前登录用户
  - 登录、登出、加载 profile
- `src/stores/allocation.ts`
  - 可领取线索、已领取线索、管理视角全部线索
  - 领取动作和错误状态
- `src/stores/lead.ts`
  - 线索分析池、验证池
  - 系统判断缺失数量和补生成动作
  - 线索收集搜索日志、trace 事件和候选结果
- `src/stores/operation.ts`
  - 客户运营客户列表
  - 当前客户详情、邮件历史、会议历史
- `src/stores/meeting.ts`
  - 会议上传、轮询、历史记录和删除

## 迁移原则

1. 页面组件不直接裸写 `fetch`，统一走 `services`。
2. 页面共享状态不放局部变量，统一走 `stores`。
3. 表格、状态标签、筛选器、按钮区等复用 UI 放到 `components/common` 或对应业务目录。
4. 新增页面必须进 `router/index.ts`，不再使用旧的 `switchView()`。
5. 新功能优先写到 Vue 入口，旧 `index.html` 只做兜底和临时修复。

## 本地验证

```powershell
npm install
npm run dev
```

访问：

```text
http://127.0.0.1:5173/app.html
```

构建：

```powershell
npm run build
```

## 服务器切换建议

第一阶段先不要直接切换 `index.html`。

建议顺序：

1. 本地验证 `app.html` 核心链路：登录、线索收集、线索分析、战略视角、客户分配、客户运营、会议分析。
2. 服务器部署后先通过 `/app.html` 灰度访问。
3. 确认 API base、cookie、权限、领取状态、邮件和会议上传都正常。
4. 再把默认首页从 `index.html` 切到 `app.html`。
5. 最后清理旧 `index.html` 中已迁移逻辑。

## 下一批迁移重点

1. 客户运营详情继续补动作按钮：创建待办、更新客户阶段。
2. 会议分析后续增强：实时录音、浏览器临时转写、音频播放。
3. 旧 `index.html` 中剩余管理弹窗和 PA 交互按业务价值拆分重做。
4. 旧 `src/components/overlays` 中乱码文件暂不纳入构建，后续按业务重新实现。
