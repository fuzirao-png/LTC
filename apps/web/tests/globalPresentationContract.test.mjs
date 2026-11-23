import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const readSource = (path) => readFileSync(new URL(path, import.meta.url), 'utf8');

const sidebar = readSource('../src/shared/components/AppSidebar.vue');
const legacySidebar = readSource('../src/shared/components/Sidebar.vue');
const layout = readSource('../src/app/layouts/AppLayout.vue');
const userProfile = readSource('../src/shared/components/UserProfile.vue');
const dashboard = readSource('../src/features/dashboards/DashboardView.vue');
const leadCollection = readSource('../src/features/lead-collection/LeadCollection.vue');
const customerAllocation = readSource('../src/features/customer-allocation/CustomerAllocation.vue');
const bossDashboard = readSource('../src/features/boss-dashboard/BossDashboard.vue');
const bossLeadAssign = readSource('../src/features/boss-dashboard/BossLeadAssign.vue');
const bossSalesManagement = readSource('../src/features/boss-dashboard/BossSalesManagement.vue');
const leadAnalysis = readSource('../src/features/lead-analysis/LeadAnalysis.vue');
const globalStyle = readSource('../src/style.css');

assert.doesNotMatch(sidebar, /AI员工/);
assert.match(sidebar, />AI agent</);
assert.doesNotMatch(sidebar, /系统在线|brand-status-dot/);
assert.doesNotMatch(legacySidebar, /AI员工|系统在线/);
assert.doesNotMatch(layout, /AI员工/);
assert.match(sidebar, /`\$\{regionLabel\(auth\.currentUser\.regionCode\)\}区域-\$\{auth\.currentUser\.salesTier \|\| '未分级'\}等级`/);
assert.match(userProfile, /`\$\{regionLabel\(user\.regionCode\)\}区域-\$\{user\.salesTier \|\| '未分级'\}等级`/);

assert.match(dashboard, /<div class="dashboard-title">我的业绩<\/div>/);
assert.doesNotMatch(dashboard, /dashboard-subtitle|userLine|今日/);
assert.doesNotMatch(dashboard, /待领取/);
assert.match(dashboard, /return allocation\.mine\.slice\(0, 6\)\.map\(normalizeLead\)/);
assert.match(dashboard, /role="table" aria-label="销售漏斗阶段统计"/);
assert.match(dashboard, />阶段<\/span>[\s\S]*?>漏斗<\/span>[\s\S]*?>数量<\/span>[\s\S]*?>占比<\/span>/);
for (const stage of ['我的线索', '已触达', '已回复', '已会议', '已方案', '已成交']) {
  assert.match(dashboard, new RegExp(stage));
}
assert.match(dashboard, /percentage\.toFixed\(1\)/);
assert.doesNotMatch(dashboard, /funnel-track-dashboard|funnel-text-dashboard/);
for (const metric of ['本月团队额度', '我的团队内排名', '团队公司内排名', '均值对比']) {
  assert.match(dashboard, new RegExp(metric));
}
assert.match(dashboard, /teamMetricCards/);

const tableViews = [leadCollection, customerAllocation, bossDashboard, bossLeadAssign, bossSalesManagement];
for (const view of tableViews) {
  assert.match(view, /class="separate-filter-bar"/);
}
assert.match(globalStyle, /\.separate-filter-bar\s*\{/);
assert.match(globalStyle, /\.separate-filter-bar \.filter-control select\s*\{/);

const embeddedFilterLabels = [
  '销售排名姓名', '销售排名区域', '管理客户行业', '资源池行业',
  '销售评估区域', 'Agent评估Agent', '销售名册区域',
];
for (const source of tableViews) {
  const tableHeads = source.match(/<thead>[\s\S]*?<\/thead>/g) || [];
  for (const label of embeddedFilterLabels) {
    assert.ok(tableHeads.every((head) => !head.includes(`aria-label="${label}"`)), `${label} must stay above the table`);
  }
}
const leadAnalysisHeads = leadAnalysis.match(/<thead>[\s\S]*?<\/thead>/g) || [];
assert.ok(leadAnalysisHeads.every((head) => !head.includes('aria-label="ICP 分数"')), 'ICP 分数筛选 must stay above the table');

console.log('Global presentation contract test passed');
