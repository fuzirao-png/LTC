<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { allocationApi } from '../../services/allocationApi';
import { countryLabel, salesTierLabel, pipelineStageLabel, regionLabel as sharedRegionLabel } from '../../shared/utils/labels';
const regionLabel = (code: string | null) => sharedRegionLabel(code) === '未知' ? '—' : sharedRegionLabel(code);

interface SalesUser {
  user_id: string; username: string; display_name: string;
  account_type: string; sales_tier: string | null; region_code: string | null;
  status: string; capacity_limit: number | null;
  active_assignment_count: number; version: number;
}

interface HandoverItem {
  user_id: string; display_name: string; sales_tier: string;
  region_code: string; active_leads: number; status: string; leads: HandoverLead[];
}

interface HandoverLead {
  lead_id: string; company_id: string; company_name: string;
  departed_user_id: string; departed_user_name: string;
  sales_tier: string; region_code: string | null;
  required_sales_tier: string; customer_grade: string | null;
  customer_region_code: string | null;
  country_code: string | null; country_name: string | null;
  pipeline_stage: string; allocation_status: 'claimed'; version: number;
}

// ---- state ----
const users = ref<SalesUser[]>([]);
const loading = ref(false);
const error = ref('');
const regionFilter = ref('all');
const tierFilter = ref('all');
const statusFilter = ref('all');
const handoverTierFilter = ref('all');
const handoverRegionFilter = ref('all');
const handoverCountryFilter = ref('all');
const departDialog = ref<{ user: SalesUser | null; reason: string; saving: boolean }>({ user: null, reason: '', saving: false });
const handoverLeads = ref<HandoverLead[]>([]);
const handoverSaving = ref<string | null>(null);
const poolReturningUserId = ref<string | null>(null);
const handoverTarget = ref<Record<string, string>>({});
const assignmentMessage = ref('');

// ---- computed ----
const salesUsers = computed(() => users.value.filter(u => u.account_type === 'sales'));
const activeSalesUsers = computed(() => salesUsers.value.filter(u => u.status === 'active'));

const handoverPending = computed<HandoverItem[]>(() => Object.values(
  handoverLeads.value.reduce<Record<string, HandoverItem>>((groups, lead) => {
    const item = groups[lead.departed_user_id] || {
      user_id: lead.departed_user_id, display_name: lead.departed_user_name,
      sales_tier: lead.sales_tier, region_code: lead.region_code || '',
      active_leads: 0, status: '待交接', leads: [],
    };
    item.active_leads += 1;
    item.leads.push(lead);
    groups[lead.departed_user_id] = item;
    return groups;
  }, {}),
));
const handoverTierOptions = computed(() => [...new Set(handoverPending.value.map((item) => item.sales_tier).filter(Boolean))]);
const handoverRegionOptions = computed(() => [...new Set(handoverPending.value.map((item) => item.region_code).filter(Boolean))]);
const handoverCountryOptions = computed(() => [...new Map(handoverLeads.value
  .map((lead): [string, string] => [lead.country_code || lead.country_name || '', lead.country_name || countryLabel(lead.country_code)])
  .filter(([code]) => code)).entries()]);
const filteredHandoverPending = computed(() => handoverPending.value
  .filter((item) => (
    (handoverTierFilter.value === 'all' || item.sales_tier === handoverTierFilter.value)
    && (handoverRegionFilter.value === 'all' || item.region_code === handoverRegionFilter.value)
  ))
  .map((item) => {
    const leads = handoverCountryFilter.value === 'all'
      ? item.leads
      : item.leads.filter((lead) => (lead.country_code || lead.country_name) === handoverCountryFilter.value);
    return { ...item, leads, active_leads: leads.length };
  })
  .filter((item) => item.leads.length > 0));

const activeCount = computed(() => salesUsers.value.filter(u => u.status === 'active').length);
const departedCount = computed(() => salesUsers.value.filter(u => u.status === 'departed').length);
const pendingHandoverCount = computed(() => handoverPending.value.reduce((s, h) => s + h.active_leads, 0));

const filteredRoster = computed(() => {
  return salesUsers.value.filter(u => {
    if (regionFilter.value !== 'all' && u.region_code !== regionFilter.value) return false;
    if (tierFilter.value !== 'all' && u.sales_tier !== tierFilter.value) return false;
    if (statusFilter.value !== 'all' && u.status !== statusFilter.value) return false;
    return true;
  });
});

const statusLabel = (s: string) => s === 'active' ? '在职' : s === 'departed' ? '已离职' : s === 'disabled' ? '已禁用' : s;

function eligibleSalesFor(salesTier: string, regionCode: string | null | undefined): SalesUser[] {
  return activeSalesUsers.value.filter((user) => (
    user.sales_tier === salesTier
    && user.region_code === regionCode
    && (user.capacity_limit == null || user.active_assignment_count < user.capacity_limit)
  ));
}

const eligibleHandoverTargets = (lead: HandoverLead) => eligibleSalesFor(lead.required_sales_tier, lead.customer_region_code);
const poolStageHandoverLeads = (item: HandoverItem) => item.leads.filter((lead) => lead.pipeline_stage === 'new');
const handoverCountryLabel = (lead: HandoverLead) => lead.country_name || countryLabel(lead.country_code) || '—';
const handoverCountrySummary = (item: HandoverItem) => [...new Set(item.leads.map(handoverCountryLabel))].join(' / ');

function assignmentError(e: any, fallback: string): string {
  const detail = e?.response?.data?.detail;
  const code = typeof detail === 'string' ? detail : detail?.code;
  const messages: Record<string, string> = {
    SALES_TIER_MISMATCH: '所选销售等级与客户要求不匹配，请重新选择。',
    SALES_REGION_MISMATCH: '所选销售区域与客户所属区域不匹配，请重新选择。',
    SALES_CAPACITY_EXCEEDED: '所选销售的客户容量已满，请选择其他销售。',
    TARGET_NOT_ACTIVE_SALES: '所选销售当前不在职，请重新选择。',
    HANDOVER_LEAD_NOT_PENDING: '该客户已不在待交接状态，请刷新后重试。',
    VERSION_CONFLICT: '客户信息已更新，请刷新后重试。',
  };
  return messages[code] || (typeof detail === 'string' ? detail : detail?.message) || e?.message || fallback;
}

// ---- actions ----
async function load() {
  loading.value = true;
  error.value = '';
  try {
    const [data, pending] = await Promise.all([
      allocationApi.listUsers(),
      allocationApi.listHandoverLeads(),
    ]);
    users.value = data.filter((u: any) => u.account_type === 'sales');
    handoverLeads.value = pending;
  } catch (e: any) {
    error.value = e?.message || '加载销售列表失败';
  } finally {
    loading.value = false;
  }
}

async function assignHandover(lead: HandoverLead) {
  const targetUserId = handoverTarget.value[lead.lead_id];
  const target = eligibleHandoverTargets(lead).find((user) => user.user_id === targetUserId);
  if (!target) {
    error.value = '请选择一名等级、区域与客户匹配的在职销售。';
    return;
  }
  if (!window.confirm(`确认将 ${lead.company_name} 交接给 ${target.display_name}？`)) return;
  handoverSaving.value = lead.lead_id;
  assignmentMessage.value = '';
  error.value = '';
  try {
    await allocationApi.assignHandoverLead(lead.lead_id, target.user_id, lead.version);
    assignmentMessage.value = `${lead.company_name} 已交接给 ${target.display_name}。`;
    delete handoverTarget.value[lead.lead_id];
    await load();
  } catch (e: any) {
    error.value = assignmentError(e, '离职客户交接失败');
  } finally {
    handoverSaving.value = null;
  }
}

async function returnToPool(item: HandoverItem) {
  const poolLeads = poolStageHandoverLeads(item);
  if (!poolLeads.length) return;
  if (!window.confirm(`确认将 ${item.display_name} 名下 ${poolLeads.length} 个待领取客户一键回池？`)) return;
  poolReturningUserId.value = item.user_id;
  assignmentMessage.value = '';
  error.value = '';
  try {
    const result = await allocationApi.returnHandoverToPool(item.user_id);
    const returnedCount = Number(result?.returned_count ?? poolLeads.length);
    assignmentMessage.value = `已将 ${returnedCount} 个待领取客户退回资源池。`;
    await load();
  } catch (e: any) {
    error.value = assignmentError(e, '待领取客户回池失败');
  } finally {
    poolReturningUserId.value = null;
  }
}

async function openDepart(user: SalesUser) {
  const confirmed = window.confirm('\u786e\u8ba4\u6807\u8bb0 ' + user.display_name + ' \u4e3a\u79bb\u804c\uff1f\n\n'
    + '\u8be5\u9500\u552e\u540d\u4e0b ' + assignmentCount(user) + ' \u4e2a\u5ba2\u6237\u5c06\u81ea\u52a8\u751f\u6210\u5f85\u4ea4\u63a5\u6e05\u5355\u3002\n'
    + '\u8be5\u8d26\u53f7\u5c06\u7acb\u5373\u5931\u53bb\u767b\u5f55\u6743\u9650\uff0c\u4ea4\u63a5\u8bf7\u6c42\u5c06\u63a8\u9001\u7ed9\u76f4\u5c5e\u4e3b\u7ba1\u3002\n\n'
    + '\u6b64\u64cd\u4f5c\u4e0d\u53ef\u64a4\u9500\u3002');
  if (!confirmed) return;
  error.value = '';
  try {
    await allocationApi.departUser(user.user_id, '\u7ba1\u7406\u6807\u8bb0\u79bb\u804c\uff0c\u8fdb\u5165\u4ea4\u63a5\u6d41\u7a0b', user.version);
    await load();
  } catch (e: any) {
    error.value = e?.message || '\u64cd\u4f5c\u5931\u8d25';
  }
}

// Count active leads per user from their assignment count
function assignmentCount(user: SalesUser): number {
  return user.active_assignment_count || 0;
}

onMounted(load);
</script>

<template>
  <div class="content-main legacy-analysis">
    <!-- Header bar -->
    <div class="agent-live-bar">
      <div class="live-dot" />
      <span>销售管理 · 离职交接</span>
      <div class="live-stat">
      </div>
    </div>

    <div class="legacy-page-title">销售管理</div>
    <div style="font-size:12px;color:var(--text-secondary);margin-bottom:14px;">
      管理销售人员在职状态与离职交接。标记离职后，该销售名下客户进入交接待办，由管理员逐条分配或批量回库。
    </div>

    <!-- Loading / Error -->
    <div v-if="loading" style="padding:40px;text-align:center;color:var(--text-muted);">加载中...</div>
    <div v-if="error" class="alert-error" role="alert">{{ error }}</div>

    <template v-if="!loading">
      <!-- KPI cards -->
      <div class="metric-cards four-col">
        <div class="metric-card">
          <div class="metric-label">在职销售</div>
          <div class="metric-val">{{ activeCount }}</div>
          <div class="metric-sub">MA {{ salesUsers.filter(u=>u.status==='active'&&u.sales_tier==='MA').length }} / SA {{ salesUsers.filter(u=>u.status==='active'&&u.sales_tier==='SA').length }} / A {{ salesUsers.filter(u=>u.status==='active'&&u.sales_tier==='A').length }}</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">交接待办</div>
          <div class="metric-val" style="color:var(--orange-warn);">{{ handoverPending.length }}</div>
          <div class="metric-sub">{{ handoverPending.map(h => h.display_name).join(' · ') || '无' }}</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">待交接客户</div>
          <div class="metric-val" style="color:var(--red-badge);">{{ pendingHandoverCount }}</div>
          <div class="metric-sub">共 {{ pendingHandoverCount }} 个客户待分配</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">超时预警</div>
          <div class="metric-val" style="color:var(--green-ok);">0</div>
          <div class="metric-sub">SLA: 3工作日</div>
        </div>
      </div>

      <!-- Handover pending panel -->
      <div class="panel" style="margin-bottom:14px;">
        <div class="panel-header">
          <span>交接待办</span>
        </div>
        <div class="panel-body">
          <div class="separate-filter-bar" aria-label="交接待办筛选条件">
            <label class="filter-control">等级<select v-model="handoverTierFilter" aria-label="交接销售等级"><option value="all">全部</option><option v-for="tier in handoverTierOptions" :key="tier" :value="tier">{{ salesTierLabel(tier) }}</option></select></label>
            <label class="filter-control">区域<select v-model="handoverRegionFilter" aria-label="交接销售区域"><option value="all">全部</option><option v-for="region in handoverRegionOptions" :key="region" :value="region">{{ regionLabel(region) }}</option></select></label>
            <label class="filter-control">国家<select v-model="handoverCountryFilter" aria-label="交接客户国家"><option value="all">全部</option><option v-for="[code, label] in handoverCountryOptions" :key="code" :value="code">{{ label }}</option></select></label>
          </div>
          <div v-if="!handoverPending.length" class="handover-empty">暂无交接待办</div>
          <table v-else class="matrix-table handover-table">
            <colgroup>
              <col class="handover-col-customer" />
              <col class="handover-col-tier" />
              <col class="handover-col-location" />
              <col class="handover-col-country" />
              <col class="handover-col-status" />
              <col class="handover-col-action" />
            </colgroup>
            <thead>
              <tr>
                <th>离职销售 / 客户</th>
                <th>等级</th>
                <th>区域</th>
                <th>国家</th>
                <th>客户 / 跟进状态</th><th>操作</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="h in filteredHandoverPending" :key="h.user_id">
                <tr class="handover-summary-row">
                  <td style="font-weight:600;">{{ h.display_name }}</td>
                  <td>{{ salesTierLabel(h.sales_tier) }}</td>
                  <td>{{ regionLabel(h.region_code) }}</td>
                  <td>{{ handoverCountrySummary(h) }}</td>
                  <td style="color:var(--red-badge);font-weight:600;">{{ h.active_leads }}</td>
                  <td class="handover-summary-action">逐条分配或批量回库</td>
                </tr>
                <tr v-for="lead in h.leads" :key="lead.lead_id" class="handover-lead-row">
                  <td><span class="handover-lead">{{ lead.company_name }}</span></td>
                  <td>{{ lead.customer_grade || '未评级' }}</td>
                  <td>{{ regionLabel(lead.customer_region_code) }}</td>
                  <td>{{ handoverCountryLabel(lead) }}</td>
                  <td><span class="handover-stage">{{ pipelineStageLabel(lead.pipeline_stage) }}</span></td>
                  <td class="handover-assign-cell">
                    <div class="handover-assign-controls">
                      <select
                        v-model="handoverTarget[lead.lead_id]"
                        class="assign-select"
                        :disabled="!eligibleHandoverTargets(lead).length"
                        :aria-label="`为 ${lead.company_name} 选择交接销售`"
                      >
                        <option value="">{{ eligibleHandoverTargets(lead).length ? '选择匹配销售' : '暂无可接收销售' }}</option>
                        <option v-for="user in eligibleHandoverTargets(lead)" :key="user.user_id" :value="user.user_id">
                          {{ user.display_name }} · {{ salesTierLabel(user.sales_tier || '') }} · {{ regionLabel(user.region_code) }}
                        </option>
                      </select>
                      <button
                        class="btn-xs primary"
                        type="button"
                        :disabled="handoverSaving === lead.lead_id || !handoverTarget[lead.lead_id]"
                        @click="assignHandover(lead)"
                      >{{ handoverSaving === lead.lead_id ? '交接中...' : '确认分配' }}</button>
                    </div>
                  </td>
                </tr>
                <tr v-if="poolStageHandoverLeads(h).length" class="handover-pool-row">
                  <td colspan="6">
                    <div class="handover-pool-action">
                      <span>仅回池 {{ poolStageHandoverLeads(h).length }} 个尚未跟进的待领取客户</span>
                      <button
                        class="btn-xs"
                        type="button"
                        :disabled="poolReturningUserId === h.user_id"
                        @click="returnToPool(h)"
                      >{{ poolReturningUserId === h.user_id ? '回池中...' : '一键回池待领取客户' }}</button>
                    </div>
                  </td>
                </tr>
              </template>
              <tr v-if="!filteredHandoverPending.length"><td colspan="6" class="handover-empty">没有符合当前筛选条件的交接待办</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-if="assignmentMessage" class="alert-info">{{ assignmentMessage }}</div>

      <!-- Sales roster panel -->
      <div class="panel">
        <div class="panel-header">
          <span>销售名册</span>
          <span style="font-size:10px;color:var(--text-muted);">点击"标记离职"触发交接流程</span>
        </div>
        <div class="panel-body" style="padding:0;">
          <div class="separate-filter-bar" aria-label="销售名册筛选条件">
            <label class="filter-control">区域<select v-model="regionFilter" aria-label="销售名册区域"><option value="all">全部</option><option value="EA">东亚</option><option value="NA">北美</option><option value="SEA">东南亚</option><option value="EU">欧洲</option><option value="ME">中东</option></select></label>
            <label class="filter-control">等级<select v-model="tierFilter" aria-label="销售名册等级"><option value="all">全部</option><option value="MA">MA</option><option value="SA">SA</option><option value="A">A</option></select></label>
            <label class="filter-control">在职状态<select v-model="statusFilter" aria-label="销售名册在职状态"><option value="all">全部</option><option value="active">在职</option><option value="departed">已离职</option></select></label>
          </div>

          <div class="table-scroll">
            <table class="matrix-table">
              <thead>
                <tr>
                  <th style="width:100px;">姓名</th>
                  <th style="width:90px;">区域</th>
                  <th style="width:70px;">等级</th>
                  <th style="width:90px;">在职状态</th>
                  <th style="width:100px;">名下客户</th>
                  <th style="width:120px;">操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="u in filteredRoster" :key="u.user_id">
                  <td style="font-weight:600;">{{ u.display_name }}</td>
                  <td>{{ regionLabel(u.region_code) }}</td>
                  <td>{{ u.sales_tier }}</td>
                  <td>
                    <span :style="{ color: u.status === 'active' ? 'var(--green-ok)' : 'var(--text-muted)' }">{{ statusLabel(u.status) }}</span>
                  </td>
                  <td>{{ assignmentCount(u) }}</td>
                  <td>
                    <button v-if="u.status === 'active'" class="btn-xs" style="color:var(--red-badge);border-color:var(--red-badge);" @click="openDepart(u)">标记离职</button>
                    <span v-else style="font-size:10px;color:var(--text-muted);">—</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </template>


  </div>
</template>

<style scoped>
.metric-cards.four-col {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 14px;
}
.metric-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px 16px;
}
.metric-label { font-size: 11px; color: var(--text-muted); margin-bottom: 4px; }
.metric-val { font-size: 24px; font-weight: 700; }
.metric-sub { font-size: 10px; color: var(--text-secondary); margin-top: 4px; }
.table-filter-tags {
  display: flex; flex-wrap: wrap; gap: 6px; align-items: center;
  padding: 10px 12px; border-bottom: 1px solid var(--border-light); background: #F8FBFF;
}
.table-filter-tag {
  font-size: 10px; padding: 4px 8px; border: 1px solid var(--border);
  border-radius: 999px; background: #fff; color: var(--text-secondary); cursor: pointer;
}
.table-filter-tag.active {
  background: var(--blue-light); border-color: rgba(37,99,235,0.28); color: var(--blue-primary); font-weight: 700;
}
.matrix-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.matrix-table th { text-align: left; padding: 8px 12px; font-size: 10px; color: var(--text-muted); font-weight: 600; text-transform: uppercase; border-bottom: 1px solid var(--border); }
.matrix-table td { padding: 8px 12px; border-bottom: 1px solid var(--border-light); }
.table-scroll { overflow-x: auto; width: 100%; }
.panel { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; box-shadow: 0 1px 4px rgba(15,23,42,0.04); }
.panel-header { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; border-bottom: 1px solid var(--border-light); font-size: 13px; font-weight: 600; background: linear-gradient(135deg,#FAFBFF,#F8FAFC); }
.panel-body { padding: 14px 16px; }
.alert-error { padding: 12px 16px; background: #FEF2F2; border: 1px solid #FECACA; border-radius: 6px; color: #DC2626; font-size: 12px; margin-bottom: 12px; }
.hard-report-panel { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.3); z-index: 500; display: flex; align-items: center; justify-content: center; }
.hard-report-close { position: absolute; top: 16px; right: 16px; background: var(--bg-card); border: 1px solid var(--border); border-radius: 50%; width: 32px; height: 32px; cursor: pointer; }
.handover-leads { display: flex; flex-wrap: wrap; gap: 6px; }
.handover-table { table-layout: fixed; min-width: 960px; }
.handover-col-customer { width: 17%; }
.handover-col-tier { width: 14%; }
.handover-col-location { width: 13%; }
.handover-col-country { width: 13%; }
.handover-col-status { width: 12%; }
.handover-col-action { width: 31%; }
.handover-summary-row td { background: #FAFCFF; }
.handover-lead-row td { padding-top: 7px; padding-bottom: 7px; vertical-align: middle; }
.handover-assign-cell { text-align: left; }
.handover-assign-controls { display: flex; width: 100%; min-width: 0; align-items: center; justify-content: flex-start; gap: 8px; }
.handover-pool-row td { background: #FAFCFF; }
.handover-pool-action { display: flex; align-items: center; justify-content: flex-end; gap: 10px; color: var(--text-muted); font-size: 10px; }
.legacy-hidden-filters { display: none; }
.roster-filter { display:flex; gap:6px; align-items:center; }
.roster-filter select { min-width:58px; padding:3px 5px; border:1px solid var(--border); border-radius:5px; background:#fff; color:var(--text-primary); font-size:10px; cursor:pointer; }
.handover-empty { padding:28px 16px; text-align:center; color:var(--text-muted); font-size:12px; }
.handover-lead { display: inline-block; max-width: 100%; padding: 4px 8px; border: 1px solid var(--border-light); background: #F8FBFF; color: var(--text-secondary); font-size: 11px; overflow-wrap: anywhere; }
.handover-stage { color: var(--text-secondary); font-size: 11px; white-space: nowrap; }
.assign-select { flex: 1 1 auto; min-width: 0; padding: 5px 7px; border: 1px solid var(--border); border-radius: 5px; background: #fff; font-size: 11px; }
.handover-assign-controls .btn-xs { flex: 0 0 auto; white-space: nowrap; }

@media (max-width: 720px) {
  .metric-cards.four-col { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .panel-body { overflow-x: auto; }
  .panel-body > .matrix-table { min-width: 760px; }
  .handover-assign-controls { flex-wrap: nowrap; }
}
</style>
