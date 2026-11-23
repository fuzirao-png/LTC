<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useRouter } from 'vue-router';

import type { LeadPoolItem } from '../../services/allocationApi';
import { useAllocationStore } from '../../stores/allocation';
import { useAuthStore } from '../../stores/auth';
import { pipelineStageLabel } from '../../shared/utils/labels';
import { api } from '../../shared/api/client';

const auth = useAuthStore();
const allocation = useAllocationStore();
const router = useRouter();
const customerNameFilter = ref('all');
const customerStageFilter = ref('all');

interface SalesOverview {
  conversion_rate: number;
  total_contract_amount_year: number;
  personal_target_completion: number;
}

interface TeamMetrics {
  team_quota: number | null;
  team_target: number | null;
  personal_rank: number | null;
  team_size: number;
  company_rank: number | null;
  company_size: number;
  average_deal_amount: number | null;
}

const salesOverview = ref<SalesOverview>({
  conversion_rate: 0,
  total_contract_amount_year: 0,
  personal_target_completion: 0,
});
const teamMetrics = ref<TeamMetrics>({
  team_quota: null,
  team_target: null,
  personal_rank: null,
  team_size: 0,
  company_rank: null,
  company_size: 0,
  average_deal_amount: null,
});

const formatMoney = (value: number) => new Intl.NumberFormat('en-US', {
  style: 'currency', currency: 'USD', maximumFractionDigits: 0,
}).format(Number(value || 0));
const formatRate = (value: number) => `${Math.round(Number(value || 0) * 1000) / 10}%`;
const topMetrics = computed(() => [
  { label: '成交额度（本年）', value: formatMoney(salesOverview.value.total_contract_amount_year), sub: '以已成交客户记录为准', color: 'blue' },
  { label: '转化率', value: formatRate(salesOverview.value.conversion_rate), sub: '已成交 / 当前客户', color: 'blue' },
  { label: '个人目标完成度', value: `${Math.round(salesOverview.value.personal_target_completion)}%`, sub: '按年度个人目标计算', color: 'blue' },
]);

const formatDate = (value?: string | null) => {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return `${date.getMonth() + 1}/${String(date.getDate()).padStart(2, '0')}`;
};

const normalizeLead = (lead: LeadPoolItem) => ({
  name: lead.name,
  stage: pipelineStageLabel(lead.pipeline_stage),
  stageClass: 'blue',
  amount: '—',
  lastFollow: formatDate(lead.claimed_at),
  action: '跟进',
  primary: true,
  target: '/customer-operation',
});

const allCustomers = computed(() => {
  return allocation.mine.slice(0, 6).map(normalizeLead);
});
const customerNameOptions = computed(() => [...new Set(allCustomers.value.map((customer) => customer.name))]);
const customerStageOptions = computed(() => [...new Set(allCustomers.value.map((customer) => customer.stage))]);
const customers = computed(() => allCustomers.value.filter((customer) => (
  (customerNameFilter.value === 'all' || customer.name === customerNameFilter.value)
  && (customerStageFilter.value === 'all' || customer.stage === customerStageFilter.value)
)));

const followUpRate = computed(() => {
  const total = allocation.mine.length;
  if (!total) return '0%';
  const followed = allocation.mine.filter((lead) => lead.pipeline_stage && lead.pipeline_stage !== 'new').length;
  return `${Math.round((followed / total) * 100)}%`;
});
const detailStats = computed(() => [
  { label: '我的线索', value: String(allocation.mine.length), color: 'blue' },
  { label: '转化率', value: formatRate(salesOverview.value.conversion_rate), color: 'green' },
  { label: '客户跟进率', value: followUpRate.value, color: 'amber' },
  { label: '平均成单周期', value: '待回流', color: 'main' },
]);
const aiSuggestion = computed(() => {
  if (allocation.mine.length === 0) return '当前没有负责中的客户。';
  return `当前有 ${allocation.mine.length} 条客户，请优先处理最近有活动的客户。`;
});

const go = (path: string) => {
  void router.push(path);
};

// ---- Customer detail slide-out panel (aligned with prototype) ----
const selectedCustomer = ref<string | null>(null);

interface CustomerDetail {
  name: string; tag: string; location: string; founded: string; employees: string;
  description: string; extra: string; funding: string;
  contacts: { name: string; role: string; email: string }[];
  intent: string; decisionCycle: string; commPref: string; focus: string;
  bestTime: string; budgetSignal: string;
  strategy: string; script: string;
  suggestions: { label: string; primary: boolean }[];
}

const customerDetails: Record<string, CustomerDetail> = {
  'Pacific TMC Japan': {
    name: 'Pacific TMC Japan', tag: '差旅平台', location: '东京', founded: '2010', employees: '500+',
    description: '日本领先的差旅管理公司，服务于 200+ 企业客户', extra: '', funding: '',
    contacts: [
      { name: 'Tanaka Kenji', role: 'Head of Global Travel', email: 'k.tanaka@pacific-tmc.jp' },
      { name: 'Sato Yuki', role: 'IT Manager', email: 'y.sato@pacific-tmc.jp' },
    ],
    intent: '强', decisionCycle: '约4周', commPref: '邮件', focus: '成本透明化、合规性',
    bestTime: '周二上午', budgetSignal: '$5,000/年预估',
    strategy: '基于客户企业差旅管理场景，推荐"多国通讯成本统一管理"切入角度。结合现有供应商合同到期信号，建议强调ROI和合规性。',
    script: '"Hi Tanaka-san, Pacific TMC在差旅管理领域的经验非常匹配我们的企业eSIM方案。我们覆盖日本及东南亚主要国家，企业定价根据用量阶梯优惠。方便约30分钟会议详细聊聊吗？"',
    suggestions: [
      { label: '约会议', primary: true },
      { label: '发资料', primary: false },
      { label: '自定义回复', primary: false },
    ],
  },
  'GlobalLink Travel': {
    name: 'GlobalLink Travel', tag: '差旅平台', location: '伦敦', founded: '2012', employees: '2000+',
    description: '管理8个国家的差旅业务', extra: 'Series B融资 $12M (3周前)', funding: '',
    contacts: [
      { name: 'Sarah Chen', role: 'Head of Technology · 最终拍板', email: 's.chen@globallink.com' },
    ],
    intent: '强', decisionCycle: '约2周', commPref: '邮件', focus: '合规性',
    bestTime: '周二上午', budgetSignal: 'Series B',
    strategy: '基于客户8国差旅管理场景，推荐"多国通讯成本统一管理"切入角度。结合Series B融资信号，建议强调ROI和合规性。',
    script: '"Hi Sarah, GlobalLink在8个国家的差旅管理需求非常匹配我们的企业eSIM方案。覆盖列表包括[国家]，企业定价根据用量阶梯优惠。方便约30分钟会议详细聊聊吗？"',
    suggestions: [
      { label: '约会议', primary: true },
      { label: '发资料', primary: false },
      { label: '自定义回复', primary: false },
    ],
  },
};

const currentDetail = computed(() => selectedCustomer.value ? customerDetails[selectedCustomer.value] : null);

const openCustomerDetail = (name: string) => {
  if (customerDetails[name]) selectedCustomer.value = name;
};
const closeCustomerDetail = () => { selectedCustomer.value = null; };

watch(
  () => ({ profileLoaded: auth.profileLoaded, userId: auth.currentUser?.userId || '' }),
  ({ profileLoaded, userId }, previous) => {
    if (!previous || previous.userId !== userId) {
      allocation.claimable = [];
      allocation.mine = [];
      allocation.error = '';
    }
    if (profileLoaded && userId && auth.isSales) {
      void allocation.loadSalesPool();
      void api.get('/api/sales/dashboard')
        .then((response) => {
        salesOverview.value = { ...salesOverview.value, ...(response.data?.data?.overview || {}) };
          teamMetrics.value = { ...teamMetrics.value, ...(response.data?.data?.team_metrics || {}) };
        })
        .catch(() => {
          salesOverview.value = { conversion_rate: 0, total_contract_amount_year: 0, personal_target_completion: 0 };
          teamMetrics.value = { team_quota: null, team_target: null, personal_rank: null, team_size: 0, company_rank: null, company_size: 0, average_deal_amount: null };
        });
    }
  },
  { immediate: true },
);

interface FunnelRow { label: string; count: number; pct: string; width: number; color: string }
const funnelRows = computed<FunnelRow[]>(() => {
  const total = allocation.mine.length;
  const stageDefinitions = [
    { code: 'contacted', label: '已触达', color: '#b8d4f5' },
    { code: 'engaged', label: '已回复', color: '#8bb9ef' },
    { code: 'meeting', label: '已会议', color: '#5b9bf0' },
    { code: 'proposal', label: '已方案', color: '#347af0' },
    { code: 'won', label: '已成交', color: '#2563eb' },
  ];
  return [
    { label: '我的线索', count: total, pct: total ? '100.0%' : '0.0%', width: total ? 100 : 0, color: '#d9e8f9' },
    ...stageDefinitions.map(({ code, label, color }) => {
      const count = allocation.mine.filter((lead) => lead.pipeline_stage === code).length;
      const percentage = total ? (count / total) * 100 : 0;
      return { label, count, pct: `${percentage.toFixed(1)}%`, width: percentage, color };
    }),
  ];
});
const teamMetricCards = computed(() => [
  { label: '本月团队额度', value: teamMetrics.value.team_quota == null ? '待配置' : formatMoney(teamMetrics.value.team_quota), sub: teamMetrics.value.team_target == null ? '月度目标待配置' : `目标 ${formatMoney(teamMetrics.value.team_target)}`, color: 'blue' },
  { label: '我的团队内排名', value: teamMetrics.value.personal_rank == null ? '待配置' : `${teamMetrics.value.personal_rank}/${teamMetrics.value.team_size}`, sub: '按本月已成交客户数', color: 'blue' },
  { label: '团队公司内排名', value: teamMetrics.value.company_rank == null ? '待配置' : `${teamMetrics.value.company_rank}/${teamMetrics.value.company_size}`, sub: '按本月已成交客户数', color: 'blue' },
  { label: '均值对比', value: teamMetrics.value.average_deal_amount == null ? '待配置' : formatMoney(teamMetrics.value.average_deal_amount), sub: '团队均值 · 公司均值待配置', color: 'blue' },
]);
</script>

<template>
  <div class="content-main legacy-dashboard">
    <div class="dashboard-title-row">
      <div class="dashboard-title">我的业绩</div>
    </div>

    <!-- KPI cards sourced from the authenticated user and sales pool. -->
    <div class="metric-cards col3">
      <article v-for="metric in topMetrics" :key="metric.label" class="metric-card">
        <div class="metric-label">{{ metric.label }}</div>
        <div :class="['metric-val', metric.color]">{{ metric.value }}</div>
        <div class="metric-sub">{{ metric.sub }}</div>
      </article>
    </div>

    <!-- Monthly performance detail, aligned with the HTML prototype. -->
    <section class="panel">
      <div class="panel-header"><span>本月业绩详情</span></div>
      <div class="panel-body performance-body">
        <div class="deal-progress">
          <div class="progress-head">
            <span>成交额进度</span>
            <strong>暂无月度成交数据</strong>
          </div>
          <div class="progress-bar">
            <div class="fill" style="width: 0%" />
          </div>
          <div class="progress-note">月度成交目标待配置</div>
        </div>

        <div class="dashboard-stat-grid">
          <div v-for="item in detailStats" :key="item.label" class="dashboard-stat">
            <strong :class="item.color">{{ item.value }}</strong>
            <span>{{ item.label }}</span>
          </div>
        </div>

        <div class="ai-suggestion">
          <strong>AI建议</strong>
          <p>{{ aiSuggestion }}</p>
        </div>
      </div>
    </section>

    <!-- 我的客户概览 panel -->
    <section class="panel">
      <div class="panel-header">
        <span>我的客户概览</span>
        <small>{{ allocation.mine.length }} 家客户</small>
      </div>
      <div class="panel-body no-padding">
        <table class="matrix-table">
          <thead>
            <tr>
              <th><label class="table-header-filter"><span>客户</span><select v-model="customerNameFilter" aria-label="客户名称"><option value="all">全部</option><option v-for="name in customerNameOptions" :key="name" :value="name">{{ name }}</option></select></label></th>
              <th><label class="table-header-filter"><span>阶段</span><select v-model="customerStageFilter" aria-label="客户阶段"><option value="all">全部</option><option v-for="stage in customerStageOptions" :key="stage" :value="stage">{{ stage }}</option></select></label></th>
              <th>成交额</th>
              <th>最近跟进</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="customers.length === 0">
              <td colspan="5">暂无客户数据</td>
            </tr>
            <tr v-for="customer in customers" :key="customer.name" class="clickable-row" @click="openCustomerDetail(customer.name)">
              <td class="customer-name">{{ customer.name }}</td>
              <td><span :class="['stage-dot', customer.stageClass]">{{ customer.stage }}</span></td>
              <td>{{ customer.amount }}</td>
              <td>{{ customer.lastFollow }}</td>
              <td>
                <button :class="['btn-xs', { primary: customer.primary }]" type="button" @click.stop="go(customer.target)">
                  {{ customer.action }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- 销售漏斗 -->
    <section class="panel">
      <div class="panel-header"><span>销售漏斗</span></div>
      <div class="panel-body sales-funnel-panel-body">
        <div class="sales-funnel-scroll">
          <div class="funnel-table-dashboard" role="table" aria-label="销售漏斗阶段统计">
            <div class="funnel-header-dashboard" role="row">
              <span role="columnheader">阶段</span>
              <span class="funnel-bar-heading" role="columnheader">漏斗</span>
              <span role="columnheader">数量</span>
              <span role="columnheader">占比</span>
            </div>
            <div v-for="row in funnelRows" :key="row.label" class="funnel-row-dashboard" role="row">
              <span class="funnel-stage-dashboard" role="cell">{{ row.label }}</span>
              <div class="funnel-bar-dashboard" role="cell">
                <div
                  class="funnel-fill-dashboard"
                  :style="{
                    width: row.count > 0 ? `max(${row.width}%, 24px)` : '0',
                    backgroundColor: row.color,
                  }"
                  aria-hidden="true"
                />
              </div>
              <strong class="funnel-count-dashboard" role="cell">{{ row.count }}</strong>
              <span class="funnel-share-dashboard" role="cell">{{ row.pct }}</span>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section class="team-metrics-row" aria-label="团队业绩指标">
      <article v-for="metric in teamMetricCards" :key="metric.label" class="metric-card">
        <div class="metric-label">{{ metric.label }}</div>
        <div :class="['metric-val', metric.color]">{{ metric.value }}</div>
        <div class="metric-sub">{{ metric.sub }}</div>
      </article>
    </section>

    <!-- Customer Detail Slide-out Panel -->
    <div v-if="selectedCustomer" class="customer-detail-mask" @click.self="closeCustomerDetail">
      <aside class="customer-detail-slide">
        <div class="cd-head">
          <div>
            <div class="cd-name">{{ currentDetail?.name }}</div>
            <div class="cd-badge-row">
              <span v-if="currentDetail?.tag" class="cd-tag">{{ currentDetail?.tag }}</span>
              <span v-if="currentDetail?.location" style="font-size:10px;color:var(--text-muted);">{{ currentDetail?.location }}</span>
            </div>
          </div>
          <div class="cd-head-actions">
            <button class="btn-xs primary" type="button">发邮件</button>
            <button class="btn-xs" type="button">约会议</button>
            <button class="btn-xs" type="button" @click="closeCustomerDetail">✕</button>
          </div>
        </div>

        <div class="cd-company-info">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
            <span style="font-size:16px;">🏢</span>
            <span style="font-weight:600;">{{ currentDetail?.name }}</span>
            <span class="cd-tag">{{ currentDetail?.tag }}</span>
          </div>
          <div class="cd-meta-text">
            <div v-if="currentDetail?.location && currentDetail?.founded">📍 {{ currentDetail?.location }} · 成立于{{ currentDetail?.founded }} · {{ currentDetail?.employees }}员工</div>
            <div v-if="currentDetail?.description">{{ currentDetail?.description }}</div>
            <div v-if="currentDetail?.extra">{{ currentDetail?.extra }}</div>
          </div>
        </div>

        <div class="cd-section" v-if="currentDetail?.contacts?.length">
          <div class="cd-section-title">👤 联系人</div>
          <div v-for="c in currentDetail.contacts" :key="c.email" class="cd-contact-card">
            <div class="cd-contact-head">
              <div>
                <div class="cd-contact-name">{{ c.name }}</div>
                <div class="cd-contact-role">{{ c.role }}</div>
              </div>
            </div>
            <div class="cd-contact-email">{{ c.email }}</div>
          </div>
        </div>

        <div class="cd-section">
          <div class="cd-section-title">📊 客户分析报告</div>
          <div class="cd-analysis-box">
            <div class="cd-analysis-grid">
              <div><span class="cd-kv">购买意向：</span><strong style="color:var(--green-ok);">{{ currentDetail?.intent || '—' }}</strong></div>
              <div><span class="cd-kv">决策周期：</span><strong>{{ currentDetail?.decisionCycle || '—' }}</strong></div>
              <div><span class="cd-kv">沟通偏好：</span><strong>{{ currentDetail?.commPref || '—' }}</strong></div>
              <div><span class="cd-kv">关注点：</span><strong>{{ currentDetail?.focus || '—' }}</strong></div>
              <div><span class="cd-kv">最佳触达：</span><strong>{{ currentDetail?.bestTime || '—' }}</strong></div>
              <div><span class="cd-kv">预算信号：</span><strong>{{ currentDetail?.budgetSignal || '—' }}</strong></div>
            </div>
            <div class="cd-strategy">
              <div class="cd-strategy-title">💡 策略分析：</div>
              <div>{{ currentDetail?.strategy || '—' }}</div>
            </div>
            <div class="cd-source">客户分析 · 基于3次交互自动产出</div>
          </div>
        </div>

        <div class="cd-section" v-if="currentDetail?.script">
          <div class="cd-section-title">📝 推荐话术</div>
          <div class="cd-script-box">
            <div class="cd-script-text">"{{ currentDetail?.script }}"</div>
            <div class="cd-script-copy">[复制话术]</div>
          </div>
        </div>

        <div class="cd-section">
          <div class="cd-ai-footer">
            <div class="cd-ai-title">🤖 AI推荐下一步</div>
            <div class="cd-ai-sub">立即回复，发送产品覆盖册 + 约30分钟会议</div>
            <div class="cd-ai-buttons" v-if="currentDetail?.suggestions">
              <button v-for="s in currentDetail.suggestions" :key="s.label" :class="['btn-xs', { primary: s.primary }]" type="button">{{ s.label }}</button>
            </div>
          </div>
        </div>
      </aside>
    </div>
  </div>
</template>

<style scoped>
/* ---- Dashboard sales funnel ---- */
.sales-funnel-panel-body {
  padding: 0 18px 18px;
}

.sales-funnel-scroll {
  overflow-x: auto;
}

.funnel-table-dashboard {
  min-width: 620px;
  color: #172033;
}

.funnel-header-dashboard,
.funnel-row-dashboard {
  display: grid;
  grid-template-columns: 118px minmax(280px, 1fr) 92px 92px;
  align-items: center;
}

.funnel-header-dashboard {
  min-height: 42px;
  color: #7183a3;
  font-size: 12px;
  border-bottom: 1px solid #dce4ef;
}

.funnel-header-dashboard > span {
  text-align: right;
}

.funnel-header-dashboard > span:first-child,
.funnel-header-dashboard .funnel-bar-heading {
  text-align: center;
}

.funnel-bar-heading,
.funnel-bar-dashboard {
  box-sizing: border-box;
  height: 100%;
  border-right: 1px dashed #d7e1ee;
}

.funnel-bar-heading {
  display: grid;
  align-items: center;
  padding-right: 18px;
}

.funnel-row-dashboard {
  min-height: 42px;
  font-size: 13px;
}

.funnel-stage-dashboard {
  padding-right: 16px;
  color: #253958;
  text-align: right;
  white-space: nowrap;
}

.funnel-bar-dashboard {
  display: flex;
  align-items: center;
  padding-right: 18px;
}

.funnel-fill-dashboard {
  max-width: 100%;
  height: 28px;
  border-radius: 4px;
  transition: width 0.25s ease;
}

.funnel-count-dashboard,
.funnel-share-dashboard {
  padding-left: 14px;
  text-align: right;
  white-space: nowrap;
}

.funnel-count-dashboard {
  color: #0f172a;
  font-size: 14px;
}

.funnel-share-dashboard {
  color: #526b91;
  font-variant-numeric: tabular-nums;
}

/* Ranking amount color */
.rank-amount {
  color: var(--blue);
  font-weight: 800;
}

/* Team metrics row */
.team-metrics-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-top: 12px;
}

/* Period tabs inline */
.period-tabs-inline {
  display: inline-flex;
  gap: 4px;
  padding: 4px;
  border: 1px solid var(--border-light);
  border-radius: 10px;
  background: #fff;
}
.period-tabs-inline button {
  font-size: 11px;
  padding: 5px 12px;
  border-radius: 7px;
  cursor: pointer;
  color: var(--text-secondary);
  border: none;
  background: none;
}
.period-tabs-inline button.active {
  background: var(--blue-light);
  color: var(--blue);
  font-weight: 800;
}

/* Change up indicator */
.change.up {
  color: var(--blue);
  font-weight: 600;
}

/* Stage dot color (prototype-aligned: all use blue-primary) */
.stage-dot { font-weight: 600; }
.stage-dot.blue { color: var(--blue); }
.stage-dot.green { color: var(--blue); }
.stage-dot.amber { color: var(--blue); }
.stage-dot.muted { color: var(--text-muted); }

/* ---- Customer detail slide-out panel ---- */
.customer-detail-mask {
  position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.3); z-index: 200;
  display: flex; justify-content: flex-end;
}
.customer-detail-slide {
  width: 440px; max-width: 100vw; height: 100vh;
  background: #fff; border-left: 1px solid var(--border);
  box-shadow: -4px 0 16px rgba(0,0,0,0.1);
  overflow-y: auto; padding: 16px;
  animation: slideInRight 0.2s ease;
}
@keyframes slideInRight {
  from { transform: translateX(100%); }
  to { transform: translateX(0); }
}
.cd-head {
  display: flex; align-items: flex-start; justify-content: space-between;
  margin-bottom: 14px;
}
.cd-name { font-size: 16px; font-weight: 700; }
.cd-badge-row { display: flex; gap: 6px; align-items: center; margin-top: 2px; }
.cd-tag {
  font-size: 10px; padding: 2px 8px; background: var(--blue-light);
  color: var(--blue); border-radius: 6px; font-weight: 600;
}
.cd-head-actions { display: flex; gap: 6px; }
.cd-company-info {
  padding: 10px 12px; background: var(--bg-base); border-radius: 8px;
  margin-bottom: 12px;
}
.cd-meta-text { font-size: 11px; color: var(--text-secondary); line-height: 1.8; }
.cd-section { margin-bottom: 12px; }
.cd-section-title { font-weight: 600; font-size: 12px; margin-bottom: 8px; }
.cd-contact-card {
  padding: 8px; background: var(--bg-base); border-radius: 6px;
  margin-bottom: 6px;
}
.cd-contact-head { display: flex; align-items: center; justify-content: space-between; }
.cd-contact-name { font-weight: 600; font-size: 12px; }
.cd-contact-role { font-size: 10px; color: var(--text-muted); }
.cd-contact-email { font-size: 10px; color: var(--text-muted); margin-top: 4px; }
.cd-analysis-box {
  padding: 10px; background: #F0F9FF; border-radius: 6px;
  border-left: 3px solid var(--cyan-accent); font-size: 11px; line-height: 1.6;
}
.cd-analysis-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 6px;
  margin-bottom: 8px;
}
.cd-kv { color: var(--text-muted); }
.cd-strategy {
  margin-top: 8px; padding: 6px; background: #fff; border-radius: 4px;
}
.cd-strategy-title { font-weight: 600; margin-bottom: 2px; }
.cd-strategy div:last-child { color: var(--text-secondary); }
.cd-source { margin-top: 6px; font-size: 10px; color: var(--text-muted); }
.cd-script-box {
  padding: 10px; background: var(--bg-base); border-radius: 6px; font-size: 11px; line-height: 1.6;
}
.cd-script-text { font-style: italic; padding: 6px; background: #fff; border-radius: 4px; }
.cd-script-copy { margin-top: 4px; color: var(--blue); cursor: pointer; font-size: 10px; }
.cd-ai-footer {
  padding: 10px; background: var(--blue-light); border-radius: 8px;
}
.cd-ai-title { font-weight: 600; font-size: 12px; margin-bottom: 6px; }
.cd-ai-sub { font-size: 11px; color: var(--text-secondary); margin-bottom: 8px; }
.cd-ai-buttons { display: flex; gap: 6px; }

.clickable-row { cursor: pointer; }
.clickable-row:hover { background: #F8FBFF; }
.table-header-filter { display: flex; align-items: center; gap: 6px; }
.table-header-filter select { max-width: 150px; padding: 3px 5px; border: 1px solid var(--border); border-radius: 5px; background: #fff; color: var(--text-primary); font-size: 10px; cursor: pointer; }
.legacy-dashboard .dashboard-stat-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); }
@media (max-width: 760px) {
  .legacy-dashboard .dashboard-stat-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
