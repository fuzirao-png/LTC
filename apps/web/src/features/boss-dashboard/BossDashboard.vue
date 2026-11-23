<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { allocationApi } from '../../services/allocationApi';
import { useAuthStore } from '../../stores/auth';

const auth = useAuthStore();
const dashboardOwnerName = computed(
  () => auth.currentUser?.name || auth.currentUser?.username || '当前账号',
);

const period = ref<'month' | 'quarter' | 'year'>('month');
const healthRegionFilter = ref('all');
const agentNameFilter = ref('all');

interface SalesUser {
  user_id: string; username: string; display_name: string;
  account_type: string; sales_tier: string | null; region_code: string | null;
  status: string; capacity_limit: number | null;
  active_assignment_count: number; version: number;
}

const salesUsers = ref<SalesUser[]>([]);
import { regionLabel } from '../../shared/utils/labels';

const totalLeads = ref(0);
const claimableLeads = ref(0);
const claimedLeads = ref(0);
const loading = ref(false);
const error = ref('');

const liveKpis = computed(() => {
  const active = salesUsers.value.filter(u => u.status === 'active');
  const totalCapacity = active.reduce((s, u) => s + (u.capacity_limit || 0), 0);
  const totalAssigned = active.reduce((s, u) => s + (u.active_assignment_count || 0), 0);
  return {
    activeSalesCount: active.length,
    totalCapacity,
    totalAssigned,
    utilizationPct: totalCapacity > 0 ? Math.round((totalAssigned / totalCapacity) * 100) : 0,
  };
});

// ---- Prototype-aligned period data (exact match) ----
interface FunnelItem { label: string; count: string; pct: string; rate: string; width: number }
interface RegionItem { label: string; amount: string; conv: string; width: number }
interface ScenarioItem { label: string; share: string; conv: string; width: number }
interface HealthRow { region: string; countries: string; sales: string; amount: string; conv: string; status: string }

const ceoData = computed(() => {
  const data: Record<string, {
    revenue: string; revenueSub: string; profit: string; profitSub: string;
    conversion: string; conversionSub: string;
    funnel: FunnelItem[]; regions: RegionItem[]; scenarios: ScenarioItem[]; health: HealthRow[];
  }> = {
    month: {
      revenue: '$42,800 <span class="yo-y">同比 +18%</span>', revenueSub: '月度经营收入',
      profit: '$13,700 <span class="yo-y">同比 +12%</span>', profitSub: '月度经营利润',
      conversion: '11.8%', conversionSub: '月度线索到成交',
      funnel: [
        { label: '线索池', count: '1,247', pct: '100%', rate: '11.8%', width: 100 },
        { label: '已触达', count: '312', pct: '25%', rate: '18.4%', width: 54 },
        { label: '有意向', count: '18', pct: '5.8%', rate: '44.4%', width: 30 },
        { label: '商机', count: '8', pct: '2.4%', rate: '62.5%', width: 20 },
        { label: '成交', count: '5', pct: '1.6%', rate: '—', width: 14 },
      ],
      regions: [
        { label: '北美', amount: '$18.2k', conv: '15.2%', width: 100 },
        { label: '东亚', amount: '$12.4k', conv: '12.1%', width: 68 },
        { label: '东南亚', amount: '$8.6k', conv: '11.4%', width: 47 },
        { label: '欧洲', amount: '$3.6k', conv: '8.3%', width: 20 },
      ],
      scenarios: [
        { label: '差旅平台', share: '52%', conv: '12.8%', width: 100 },
        { label: '商旅OTA', share: '34%', conv: '11.7%', width: 65 },
        { label: '金融科技', share: '14%', conv: '9.2%', width: 27 },
      ],
      health: [
        { region: '北美', countries: '美国 / 加拿大', sales: '5', amount: '$18,200', conv: '15.2%', status: '高承接' },
        { region: '东亚', countries: '日本 / 韩国', sales: '4', amount: '$12,400', conv: '12.1%', status: '稳定' },
        { region: '东南亚', countries: '新加坡 / 泰国', sales: '3', amount: '$8,600', conv: '11.4%', status: '可加配' },
        { region: '欧洲', countries: '英国 / 德国', sales: '3', amount: '$3,600', conv: '8.3%', status: '需干预' },
        { region: '中东', countries: '阿联酋 / 沙特', sales: '2', amount: '$2,100', conv: '9.5%', status: '起步阶段' },
        { region: '其他', countries: '多地区', sales: '1', amount: '$800', conv: '6.2%', status: '探索阶段' },
      ],
    },
    quarter: {
      revenue: '$126,400 <span class="yo-y">同比 +21%</span>', revenueSub: '季度经营收入',
      profit: '$39,600 <span class="yo-y">同比 +16%</span>', profitSub: '季度经营利润',
      conversion: '12.4%', conversionSub: '季度线索到成交',
      funnel: [
        { label: '线索池', count: '3,680', pct: '100%', rate: '12.4%', width: 100 },
        { label: '已触达', count: '1,012', pct: '27.5%', rate: '19.8%', width: 56 },
        { label: '有意向', count: '86', pct: '8.5%', rate: '38.4%', width: 34 },
        { label: '商机', count: '33', pct: '3.2%', rate: '57.6%', width: 22 },
        { label: '成交', count: '19', pct: '1.8%', rate: '—', width: 15 },
      ],
      regions: [
        { label: '北美', amount: '$54.8k', conv: '14.8%', width: 100 },
        { label: '东亚', amount: '$38.2k', conv: '12.6%', width: 70 },
        { label: '东南亚', amount: '$24.9k', conv: '11.1%', width: 45 },
        { label: '欧洲', amount: '$8.5k', conv: '7.9%', width: 16 },
      ],
      scenarios: [
        { label: '差旅平台', share: '49%', conv: '13.1%', width: 100 },
        { label: '商旅OTA', share: '36%', conv: '12.3%', width: 73 },
        { label: '金融科技', share: '15%', conv: '9.8%', width: 31 },
      ],
      health: [
        { region: '北美', countries: '美国 / 加拿大', sales: '5', amount: '$54,800', conv: '14.8%', status: '高承接' },
        { region: '东亚', countries: '日本 / 韩国', sales: '4', amount: '$38,200', conv: '12.6%', status: '稳定' },
        { region: '东南亚', countries: '新加坡 / 泰国', sales: '3', amount: '$24,900', conv: '11.1%', status: '可加配' },
        { region: '欧洲', countries: '英国 / 德国', sales: '3', amount: '$8,500', conv: '7.9%', status: '需干预' },
        { region: '中东', countries: '阿联酋 / 沙特', sales: '2', amount: '$6,400', conv: '9.8%', status: '起步阶段' },
        { region: '其他', countries: '多地区', sales: '1', amount: '$2,300', conv: '6.5%', status: '探索阶段' },
      ],
    },
    year: {
      revenue: '$386,000 <span class="yo-y">同比 +26%</span>', revenueSub: '年度经营收入',
      profit: '$118,400 <span class="yo-y">同比 +19%</span>', profitSub: '年度经营利润',
      conversion: '10.6%', conversionSub: '年度线索到成交',
      funnel: [
        { label: '线索池', count: '12,860', pct: '100%', rate: '10.6%', width: 100 },
        { label: '已触达', count: '3,420', pct: '26.6%', rate: '17.1%', width: 56 },
        { label: '有意向', count: '298', pct: '8.7%', rate: '32.9%', width: 34 },
        { label: '商机', count: '98', pct: '2.9%', rate: '54.1%', width: 22 },
        { label: '成交', count: '53', pct: '1.5%', rate: '—', width: 15 },
      ],
      regions: [
        { label: '北美', amount: '$182.4k', conv: '13.9%', width: 100 },
        { label: '东亚', amount: '$124.0k', conv: '11.7%', width: 68 },
        { label: '东南亚', amount: '$81.2k', conv: '10.8%', width: 45 },
        { label: '欧洲', amount: '$34.0k', conv: '7.4%', width: 19 },
      ],
      scenarios: [
        { label: '差旅平台', share: '47%', conv: '11.5%', width: 100 },
        { label: '商旅OTA', share: '38%', conv: '10.9%', width: 81 },
        { label: '金融科技', share: '15%', conv: '8.6%', width: 32 },
      ],
      health: [
        { region: '北美', countries: '美国 / 加拿大', sales: '5', amount: '$182,400', conv: '13.9%', status: '高承接' },
        { region: '东亚', countries: '日本 / 韩国', sales: '4', amount: '$124,000', conv: '11.7%', status: '稳定' },
        { region: '东南亚', countries: '新加坡 / 泰国', sales: '3', amount: '$81,200', conv: '10.8%', status: '可加配' },
        { region: '欧洲', countries: '英国 / 德国', sales: '3', amount: '$34,000', conv: '7.4%', status: '需干预' },
        { region: '中东', countries: '阿联酋 / 沙特', sales: '2', amount: '$19,200', conv: '9.2%', status: '起步阶段' },
        { region: '其他', countries: '多地区', sales: '1', amount: '$7,800', conv: '5.9%', status: '探索阶段' },
      ],
    },
  };
  return data[period.value] || data.month;
});

// Agent Health Assessment (prototype-aligned)
interface AgentHealth {
  label: string;
  trustworthiness: number;
  dataValidation: number;
  ruleConsistency: number;
  resultVerification: number;
  anomalyRate: number;
}

const agentHealthRows: AgentHealth[] = [
  { label: '线索收集Agent', trustworthiness: 90, dataValidation: 96, ruleConsistency: 92, resultVerification: 72, anomalyRate: 4 },
  { label: '线索分析Agent', trustworthiness: 86, dataValidation: 93, ruleConsistency: 88, resultVerification: 66, anomalyRate: 6 },
  { label: '客户分配Agent', trustworthiness: 78, dataValidation: 90, ruleConsistency: 82, resultVerification: 54, anomalyRate: 9 },
  { label: '客户分析Agent', trustworthiness: 84, dataValidation: 91, ruleConsistency: 86, resultVerification: 61, anomalyRate: 7 },
  { label: '客户运营Agent', trustworthiness: 76, dataValidation: 88, ruleConsistency: 80, resultVerification: 49, anomalyRate: 10 },
];

const healthRegionOptions = computed(() => [...new Set(ceoData.value.health.map((row) => row.region))]);
const filteredHealthRows = computed(() => ceoData.value.health.filter((row) => (
  (healthRegionFilter.value === 'all' || row.region === healthRegionFilter.value)
)));
const agentNameOptions = [...new Set(agentHealthRows.map((row) => row.label))];
const filteredAgentHealthRows = computed(() => agentHealthRows.filter((row) => (
  (agentNameFilter.value === 'all' || row.label === agentNameFilter.value)
)));
const customerCountForRegion = (region: string) => salesUsers.value
  .filter((user) => user.status === 'active' && regionLabel(user.region_code) === region)
  .reduce((sum, user) => sum + Number(user.active_assignment_count || 0), 0);

async function loadData() {
  loading.value = true;
  error.value = '';
  try {
    const users = await allocationApi.listUsers();
    salesUsers.value = users.filter((u: any) => u.account_type === 'sales');
  } catch (e: any) {
    error.value = e?.message || '加载数据失败';
  }

  try {
    const leads = await allocationApi.all();
    totalLeads.value = leads.total || leads.items.length;
    claimableLeads.value = leads.items.filter((lead) => lead.pool_status === 'claimable').length;
    claimedLeads.value = leads.items.filter((lead) => lead.pool_status === 'claimed').length;
  } catch { /* ignore */ }

  loading.value = false;
}

onMounted(loadData);
</script>

<template>
  <div class="content-main legacy-analysis">
    <div class="agent-live-bar">
      <div class="live-dot" />
      <span>{{ dashboardOwnerName }} · 经营驾驶舱</span>
      <div class="live-stat">
      </div>
    </div>

    <div class="ceo-header-row">
      <div>
        <div class="dashboard-title">{{ dashboardOwnerName }} · 经营驾驶舱</div>
        <div class="dashboard-subtitle">直接看经营结果、销售健康度、Agent健康度和需要管理介入的动作。</div>
      </div>
    </div>

    <div class="ceo-period-row">
      <div class="ceo-period-tabs">
        <button class="ceo-period-tab" :class="{ active: period === 'month' }" type="button" @click="period = 'month'">月度</button>
        <button class="ceo-period-tab" :class="{ active: period === 'quarter' }" type="button" @click="period = 'quarter'">季度</button>
        <button class="ceo-period-tab" :class="{ active: period === 'year' }" type="button" @click="period = 'year'">年度</button>
      </div>
    </div>

    <!-- KPI cards: Prototype-aligned 营收/利润/转化率 -->
    <div class="ceo-kpi-row">
      <article class="metric-card ceo-kpi-card">
        <div class="metric-label">营收</div>
        <div class="metric-val blue" v-html="ceoData.revenue" />
        <div class="metric-sub">{{ ceoData.revenueSub }}</div>
      </article>
      <article class="metric-card ceo-kpi-card">
        <div class="metric-label">利润</div>
        <div class="metric-val blue" v-html="ceoData.profit" />
        <div class="metric-sub">{{ ceoData.profitSub }}</div>
      </article>
      <article class="metric-card ceo-kpi-card">
        <div class="metric-label">转化率</div>
        <div class="metric-val blue">{{ ceoData.conversion }}</div>
        <div class="metric-sub">{{ ceoData.conversionSub }}</div>
      </article>
    </div>

    <div class="row-2 ceo-row">
      <!-- 销售漏斗 panel -->
      <section class="panel ceo-panel funnel-panel">
        <div class="panel-header"><span>销售漏斗</span></div>
        <div class="panel-body">
          <div class="sales-funnel-table">
            <div class="sales-funnel-header" aria-hidden="true">
              <span>阶段</span><span class="sales-funnel-bar-heading">漏斗</span><span>数量</span><span>占比</span>
            </div>
            <div v-for="row in ceoData.funnel" :key="row.label" class="sales-funnel-row">
              <span class="sales-funnel-stage">{{ row.label }}</span>
              <div class="sales-funnel-bar">
                <div class="sales-funnel-fill" :style="{ width: `${row.width}%` }" />
              </div>
              <strong class="sales-funnel-count">{{ row.count }}</strong>
              <span class="sales-funnel-pct">{{ row.pct }}</span>
            </div>
          </div>
        </div>
      </section>

      <!-- 分布漏斗 panel -->
      <section class="panel ceo-panel distribution-panel">
        <div class="panel-header"><span>分布漏斗</span></div>
        <div class="panel-body">
          <div class="distribution-group">
            <div class="distribution-title">区域市场</div>
            <div class="distribution-funnel-table">
              <div class="sales-funnel-header" aria-hidden="true">
                <span>区域</span><span class="sales-funnel-bar-heading">漏斗</span><span>金额</span><span>转化率</span>
              </div>
              <div v-for="row in ceoData.regions" :key="row.label" class="sales-funnel-row">
                <span class="sales-funnel-stage">{{ row.label }}</span>
                <div class="sales-funnel-bar"><div class="sales-funnel-fill" :style="{ width: `${row.width}%` }" /></div>
                <strong class="sales-funnel-count">{{ row.amount }}</strong>
                <span class="sales-funnel-pct">{{ row.conv }}</span>
              </div>
            </div>
          </div>
          <div class="distribution-group">
            <div class="distribution-title">应用场景漏斗</div>
            <div class="distribution-funnel-table">
              <div class="sales-funnel-header" aria-hidden="true">
                <span>场景</span><span class="sales-funnel-bar-heading">漏斗</span><span>占比</span><span>转化率</span>
              </div>
              <div v-for="row in ceoData.scenarios" :key="row.label" class="sales-funnel-row">
                <span class="sales-funnel-stage">{{ row.label }}</span>
                <div class="sales-funnel-bar"><div class="sales-funnel-fill" :style="{ width: `${row.width}%` }" /></div>
                <strong class="sales-funnel-count">{{ row.share }}</strong>
                <span class="sales-funnel-pct">{{ row.conv }}</span>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>

    <div class="row-2 ceo-row">
      <!-- 销售评估 table -->
      <section class="panel ceo-panel">
        <div class="panel-header"><span>销售评估</span></div>
        <div class="panel-body" style="padding:0;">
          <div class="separate-filter-bar" aria-label="销售评估筛选条件">
            <label class="filter-control">区域<select v-model="healthRegionFilter" aria-label="销售评估区域"><option value="all">全部</option><option v-for="region in healthRegionOptions" :key="region" :value="region">{{ region }}</option></select></label>
          </div>
          <table class="matrix-table">
            <thead>
              <tr>
                <th>区域</th>
                <th>国家</th><th>团队销售人数</th><th>客户数量</th><th>成交额</th><th>转化率</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in filteredHealthRows" :key="row.region">
                <td style="font-weight:700;">{{ row.region }}</td>
                <td>{{ row.countries }}</td>
                <td>{{ row.sales }}</td>
                <td>{{ customerCountForRegion(row.region) }}</td>
                <td style="color:var(--blue);font-weight:800;">{{ row.amount }}</td>
                <td>{{ row.conv }}</td>
              </tr>
              <tr v-if="!filteredHealthRows.length"><td colspan="6" class="table-empty">没有符合当前筛选条件的数据</td></tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- Agent评估 table -->
      <section class="panel ceo-panel">
        <div class="panel-header"><span>Agent评估</span></div>
        <div class="panel-body" style="padding:0;">
          <div class="separate-filter-bar" aria-label="Agent评估筛选条件">
            <label class="filter-control">Agent<select v-model="agentNameFilter" aria-label="Agent 类型"><option value="all">全部</option><option v-for="agent in agentNameOptions" :key="agent" :value="agent">{{ agent }}</option></select></label>
          </div>
          <table class="matrix-table">
            <thead><tr>
              <th>Agent</th>
              <th>系统可信度</th><th>数据校验</th><th>规则一致</th><th>结果验证</th><th>异常率</th>
            </tr></thead>
            <tbody>
              <tr v-for="a in filteredAgentHealthRows" :key="a.label">
                <td style="font-weight:700;">{{ a.label }}</td>
                <td style="color:var(--blue);font-weight:800;">{{ a.trustworthiness }}%</td>
                <td>{{ a.dataValidation }}%</td>
                <td>{{ a.ruleConsistency }}%</td>
                <td>{{ a.resultVerification }}%</td>
                <td>{{ a.anomalyRate }}%</td>
              </tr>
              <tr v-if="!filteredAgentHealthRows.length"><td colspan="6" class="table-empty">没有符合当前筛选条件的数据</td></tr>
            </tbody>
          </table>
          <div class="agent-footnote">
            系统可信度口径：数据校验通过率 × 35% + 规则一致率 × 35% + 结果验证率 × 20% - 异常率 × 10%。该指标主要由脚本自动计算，不依赖销售主观反馈；人工抽检只作为规则校准，不进入日常甩锅链路。
          </div>
        </div>
      </section>
    </div>

  </div>
</template>

<style scoped>
/* ---- Funnel Stack V3 (prototype-aligned pyramid shape) ---- */
.funnel-stack-v3 {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 10px;
  width: 100%;
  padding: 2px 0;
}
.funnel-segment-v3 {
  height: 28px;
  box-sizing: border-box;
  width: 100%;
  position: relative;
  color: #0F172A;
  font-size: 11px;
  font-weight: 800;
}
.funnel-track-v3 {
  position: absolute;
  left: 0;
  right: 0;
  top: 3px;
  height: 22px;
  border-radius: 6px;
  background: #E2E8F0;
  border: 1px solid rgba(15,23,42,0.08);
  overflow: hidden;
}
.funnel-fill-v3 {
  height: 100%;
  margin: 0;
  border-radius: 5px;
  box-shadow: 0 1px 3px rgba(15,23,42,0.12);
  min-width: 14px;
  transition: width 0.3s ease;
}
.funnel-text-v3 {
  position: absolute;
  inset: 0;
  display: grid;
  grid-template-columns: 92px minmax(56px, 1fr) minmax(145px, 1.15fr);
  align-items: center;
  justify-items: stretch;
  gap: 8px;
  padding: 0 14px;
  white-space: nowrap;
  overflow: hidden;
}
.funnel-text-v3 span {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  text-align: center;
}
.funnel-text-v3 .muted-label {
  font-weight: 700;
  color: #475569;
  font-size: 10px;
  text-align: right;
}

.funnel-panel,
.distribution-panel {
  min-height: 390px;
}
.funnel-panel .panel-body,
.distribution-panel .panel-body {
  padding: 28px 24px 30px;
}
.distribution-panel .panel-body {
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  gap: 24px;
}
.distribution-group {
  width: 100%;
}
.distribution-title {
  margin-bottom: 12px;
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 700;
}

.sales-funnel-table {
  display: flex;
  flex-direction: column;
  width: 100%;
}
.sales-funnel-header,
.sales-funnel-row {
  display: grid;
  grid-template-columns: 92px minmax(0, 1fr) 64px 72px;
  align-items: center;
  column-gap: 18px;
}
.sales-funnel-header {
  min-height: 38px;
  padding: 0 4px 12px;
  color: #7890b0;
  font-size: 12px;
  font-weight: 700;
  border-bottom: 1px solid #dce6f2;
}
.sales-funnel-header span:first-child,
.sales-funnel-stage {
  text-align: center;
}
.sales-funnel-header span:nth-last-child(-n+2),
.sales-funnel-count,
.sales-funnel-pct {
  text-align: right;
}
.sales-funnel-bar-heading,
.sales-funnel-bar {
  border-right: 2px dashed #d8e3f0;
}
.sales-funnel-bar-heading {
  padding-right: 18px;
}
.sales-funnel-row {
  min-height: 50px;
  padding: 8px 4px;
  color: #233653;
  font-size: 12px;
}
.sales-funnel-bar {
  height: 20px;
  padding-right: 18px;
  box-sizing: border-box;
}
.sales-funnel-fill {
  height: 100%;
  border-radius: 6px;
  background: #b9d5f3;
  transition: width .3s ease;
}
.sales-funnel-count {
  color: #14213a;
  font-size: 14px;
  font-variant-numeric: tabular-nums;
}
.sales-funnel-pct {
  color: #5e7698;
  font-variant-numeric: tabular-nums;
}

@media (max-width: 900px) {
  .row-2 {
    grid-template-columns: 1fr;
  }
  .funnel-panel,
  .distribution-panel {
    min-height: 0;
  }
}

@media (max-width: 560px) {
  .funnel-panel .panel-body,
  .distribution-panel .panel-body {
    padding: 20px 14px 24px;
  }
  .funnel-text-v3 {
    grid-template-columns: 68px 48px minmax(108px, 1fr);
    gap: 4px;
    padding: 0 10px;
    font-size: 10px;
  }
  .funnel-text-v3 .muted-label {
    font-size: 9px;
  }
  .sales-funnel-header,
  .sales-funnel-row {
    grid-template-columns: 68px minmax(0, 1fr) 48px 52px;
    column-gap: 8px;
  }
  .sales-funnel-bar {
    padding-right: 8px;
  }
  .sales-funnel-bar-heading {
    padding-right: 8px;
  }
}

/* KPI row */
.ceo-kpi-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-bottom: 14px;
}
.ceo-kpi-card {
  padding: 16px;
}

/* YoY indicator */
:deep(.yo-y) {
  font-size: 13px;
  color: var(--blue);
}

/* Agent footnote */
.agent-footnote {
  margin-top: 10px;
  padding: 10px 12px;
  background: var(--bg-base);
  border: 1px solid var(--border-light);
  border-radius: 10px;
  font-size: 10px;
  color: var(--text-muted);
  line-height: 1.5;
}

/* Reuse styles from global */
.ceo-header-row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.dashboard-title { font-size: 20px; font-weight: 700; }
.dashboard-subtitle { font-size: 12px; color: var(--text-secondary); margin-top: 2px; }
.ceo-period-row { margin-bottom: 14px; }
.ceo-period-tabs { display: inline-flex; gap: 4px; padding: 4px; border: 1px solid var(--border-light); border-radius: 10px; background: #fff; }
.ceo-period-tab { font-size: 11px; padding: 5px 12px; border-radius: 7px; cursor: pointer; color: var(--text-secondary); border: none; background: none; }
.ceo-period-tab.active { background: var(--blue-light); color: var(--blue); font-weight: 800; }
.metric-cards.col3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.metric-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 14px 16px; }
.metric-label { font-size: 11px; color: var(--text-muted); margin-bottom: 4px; }
.metric-val { font-size: 24px; font-weight: 700; }
.metric-val.blue { color: var(--blue); }
.metric-sub { font-size: 10px; color: var(--text-secondary); margin-top: 4px; }
.row-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.ceo-row { margin-bottom: 14px; }
.panel { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; margin-bottom: 14px; }
.panel-header { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; border-bottom: 1px solid var(--border-light); font-size: 13px; font-weight: 600; background: linear-gradient(135deg,#FAFBFF,#F8FAFC); }
.panel-body { padding: 14px 16px; }
.matrix-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.matrix-table th { text-align: left; padding: 8px 12px; font-size: 10px; color: var(--text-muted); font-weight: 600; text-transform: uppercase; border-bottom: 1px solid var(--border); }
.matrix-table td { padding: 8px 12px; border-bottom: 1px solid var(--border-light); }
.table-header-filter { display: flex; align-items: center; gap: 6px; }
.table-header-filter select { max-width: 110px; padding: 3px 5px; border: 1px solid var(--border); border-radius: 5px; background: #fff; color: var(--text-primary); font-size: 10px; cursor: pointer; }
.table-empty { padding: 24px !important; color: var(--text-muted); text-align: center; }
.management-copy { font-size: 12px; line-height: 1.9; color: var(--text-secondary); }
.management-copy p { margin-bottom: 10px; }
.management-copy p:last-child { margin-bottom: 0; }
.ceo-panel { box-shadow: 0 1px 4px rgba(15,23,42,0.04); }
</style>
