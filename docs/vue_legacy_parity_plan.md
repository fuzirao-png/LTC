# Vue 重构对齐旧界面迁移基准

> 目标：Vue 工程化只改变内部代码组织，不改变旧 `index.html` 的产品形态、页面路径、角色视角和核心交互。

## 一、结论

当前 `/app.html` 不能作为最终验收版本。旧界面的真实结构是“两套角色视角 + 单页切换 + 浮动 PA + 多个滑出/弹窗面板”，而不是一个通用后台管理台。

后续迁移原则：

- 旧页面视觉布局优先，Vue 页面必须先做到肉眼接近。
- 旧功能路径优先，不新增概念替代旧概念。
- 服务层、store、组件化可以重构，但用户看到的导航、按钮、表格、弹窗、流程不应改变。
- 旧 `index.html` 保留为线上稳定入口，`app.html` 只做 Vue 预览，全部对齐前不替换默认入口。

## 二、旧界面角色结构

### 登录与账号视角

旧界面是同一个产品界面，不是两个独立入口。登录只负责确认当前账号；登录成功后进入同一个 LTC AI Native 外壳，再根据真实账号权限显示对应视角。

现迁移规则：

- 未确认登录：只显示登录态检查，不渲染业务外壳。
- 未登录：显示旧风格登录页。
- 已登录销售账号：显示销售视角导航与销售数据。
- 已登录经营/管理账号：显示经营视角导航与管理数据。
- 旧界面的“切换账号”不再做前端假切换；真实系统里显示当前账号和退出登录。
- 如需 demo 快捷切换账号，必须走真实登录接口，不直接改前端角色状态。

### 销售视角

默认用户：李明，日本销售。

旧侧边栏结构：

| 分组 | 旧入口 | 旧 viewId | Vue 目标路由/组件 |
| --- | --- | --- | --- |
| 总览 | 我的业绩 | `dashboard` / `dashboardView` | `SalesDashboardView.vue` |
| AI员工 | 客户分配 | `lead-assign` / `view-lead-assign` | `SalesLeadAssignView.vue` |
| AI员工 | 客户分析 | `customer-analysis` / `view-customer-analysis` | `CustomerAnalysisView.vue` |
| AI员工 | 客户运营 | `customer-mgmt` / `view-customer-mgmt` | `CustomerMgmtView.vue` |
| 数据库 | 案例库 | `db-cases` / `view-db-cases` | `CaseLibraryView.vue` |
| 数据库 | 话术库 | `db-scripts` / `view-db-scripts` | `ScriptLibraryView.vue` |

销售视角必须保留：

- 左侧 240px 渐变侧边栏。
- 顶部 48px 面包屑。
- 用户头像/用户资料弹窗。
- 底部设置/切换账号入口。
- 右下角销售 PA 浮动按钮和弹窗。
- 客户详情滑出面板、邮件弹窗、会议弹窗。

### 经营视角

默认用户：Alex，经营视角。

旧侧边栏结构：

| 分组 | 旧入口 | 旧 viewId | Vue 目标路由/组件 |
| --- | --- | --- | --- |
| 总览 | 经营驾驶舱 | `ceo-dashboard` / `view-ceo-dashboard` | `BossDashboardView.vue` |
| AI员工 | 线索收集 | `ceo-lead-collect` / `view-ceo-lead-collect` | `BossLeadCollectView.vue` |
| AI员工 | 线索分析 | `ceo-lead-analyze` / `view-ceo-lead-analyze` | `BossLeadAnalyzeView.vue` |
| AI员工 | 客户分配 | `ceo-lead-assign` / `view-ceo-lead-assign` | `BossLeadAssignView.vue` |

经营视角必须保留：

- 与销售视角不同的侧边栏。
- Alex 角色切换后默认进入线索收集，不是战略视角空壳。
- 右下角战略 PA 浮动按钮和弹窗。
- 经营驾驶舱里的 Agent 流水线、销售团队、Pipeline 等结构。
- 线索收集里的对话式搜索、候选结果勾选、加入分析池/分配池。
- 线索分析里的 ICP 评分表和维度详情。
- 客户分配里的销售领取状态可见。

## 三、旧界面核心接口

旧 `index.html` 使用的后端基址：

| 变量 | 用途 | Vue service |
| --- | --- | --- |
| `MAIL_API_BASE` | 邮件、会议上传、旧前端静态服务 | `operationApi` / mail API |
| `CUSTOMER_OPERATION_API_BASE` | 客户运营、邮件历史、邮件生成/发送、会议历史 | `operationApi.ts` |
| `MEETING_ANALYSIS_API_BASE` | 会议分析服务 | `meetingApi.ts` |
| `ANALYSIS_AGENT_BASE` | 客户分析报告、客户画像、MEDDPICC | `operationApi.ts` 或独立 `analysisApi.ts` |
| `CUSTOMER_ALLOCATION_API_BASE` | 登录、销售资源池、领取、战略查看领取状态 | `allocationApi.ts` |
| `LEAD_AGENT_BASE` | 线索收集、线索分析、入池、ICP 维度补全 | `leadApi.ts` |

## 四、迁移顺序

### P0：停止偏离

- 不继续扩展当前新后台壳。
- 不替换旧 `index.html`。
- 不删除旧页面、旧数据、旧静态资源。

### P1：先迁移外壳

目标：Vue 的第一屏和旧页面结构一致。

任务：

- `LegacyShell.vue`：复刻旧 `.sidebar + .main-content + .top-header + .content-body`。
- `LegacySidebar.vue`：按当前角色显示销售/经营两套导航。
- `LegacyTopHeader.vue`：只显示旧面包屑，不额外加入新式标题区。
- `useLegacyUiStore`：管理 `currentRole`、`currentView`、PA 开关、弹窗开关。
- 路由可保留 hash，但展示逻辑要以旧 viewId 为核心。

验收：

- 打开 Vue 预览时，默认是销售视角“我的业绩”。
- 切换 Alex 后，侧边栏变为经营视角，默认进入“线索收集”或旧逻辑指定页。
- 视觉结构和旧页面一致：左侧宽度、顶部高度、内容区间距、卡片样式一致。

### P2：销售视角逐页迁移

先迁移静态结构，再接真实接口。

顺序：

1. 我的业绩
2. 客户分配
3. 客户分析
4. 客户运营
5. 案例库/话术库

重点：

- 客户分配不能做成新表格页，要保留旧页面的“运行中条 + 指标卡 + 资源池 + 我的线索”结构。
- 领取动作保留确认弹窗。
- 领取成功后仍要同步客户分析/客户运营事件。

### P3：经营视角逐页迁移

顺序：

1. 线索收集
2. 线索分析
3. 客户分配
4. 经营驾驶舱

重点：

- MA/SA/A、区域、销售领取状态在经营侧客户分配页可见。
- 已领取线索显示领取人，未领取显示待领取。
- 不用“战略视角”替代旧“经营驾驶舱/线索收集/线索分析/客户分配”。

### P4：弹窗和辅助能力迁移

- 用户资料弹窗。
- 销售 PA。
- 经营 PA。
- 客户详情滑出面板。
- 邮件弹窗。
- 会议上传/会议记录弹窗。
- 客户分析报告弹窗。

## 五、当前 Vue 代码处置

可复用：

- `src/services/*` API 封装。
- `src/stores/auth.ts` 登录态逻辑。
- `src/stores/allocation.ts` 领取/分配池逻辑。
- `src/stores/lead.ts` 线索收集/分析接口逻辑，但需要清理乱码文案。
- 部分表格、状态 badge 的小组件。

需要重做或重接：

- 当前 `AppSidebar.vue` 不符合旧角色结构，要替换为旧结构。
- 当前 `StrategyView.vue` 不是旧界面页面，要降级或拆成经营驾驶舱的一部分。
- 当前 `CustomerAllocation.vue` 不是旧客户分配布局，要按旧 `view-lead-assign` 重做。
- 当前 dashboard 是工程说明页，不是旧“我的业绩”，要重做。
- 旧迁移尝试文件中有大量乱码，不能直接上线。

## 六、每页验收清单

每迁移一页都必须检查：

- 页面标题、导航位置、按钮位置与旧界面一致。
- 旧页面的主卡片、表格、操作按钮不缺失。
- 旧弹窗/滑出面板入口仍可打开。
- API 请求只在旧页面对应交互触发时发生。
- 未登录时不提前请求受保护接口。
- 中文无乱码。
- `npm run build` 通过。
