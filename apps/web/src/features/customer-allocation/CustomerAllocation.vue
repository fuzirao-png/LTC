<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue';
import { useRouter } from 'vue-router';

import type { LeadPoolItem, PipelineStage } from '../../services/allocationApi';
import { countryLabel, industryLabel, pipelineStageLabel } from '../../shared/utils/labels';
import { useAllocationStore } from '../../stores/allocation';
import { useAuthStore } from '../../stores/auth';

const allocation = useAllocationStore();
const auth = useAuthStore();
const router = useRouter();
const industryFilter = ref('');
const countryFilter = ref('');
const myIndustryFilter = ref('');
const myCountryFilter = ref('');
const myStatusFilter = ref('');
const pendingClaim = ref<LeadPoolItem | null>(null);
const claimMessage = ref('');
const claimConfirmButton = ref<HTMLButtonElement | null>(null);
const claimTrigger = ref<HTMLElement | null>(null);
const pipelineStages: PipelineStage[] = ['new', 'contacted', 'engaged', 'meeting', 'proposal', 'won', 'lost', 'dormant'];

const displayCountry = (row: Pick<LeadPoolItem, 'country'>) => countryLabel(row.country) || '国家待确认';

const claimableRows = computed(() => {
  const user = auth.currentUser;
  if (!user || user.accountType !== 'sales' || !user.salesTier || !user.regionCode) return [];
  return allocation.claimable.filter((row) => row.sales_tier === user.salesTier && row.region === user.regionCode);
});
const assignedCount = computed(() => auth.currentUser?.activeAssignmentCount ?? allocation.mine.length);
const claimedFollowRate = computed(() => {
  const claimedCount = allocation.mine.length;
  if (!claimedCount) return '0%';
  const followedCount = allocation.mine.filter((row) => row.pipeline_stage && row.pipeline_stage !== 'new').length;
  return `${Math.round((followedCount / claimedCount) * 100)}%`;
});
const conversionRate = computed(() => {
  const claimedCount = allocation.mine.length;
  if (!claimedCount) return '0.0%';
  const convertedCount = allocation.mine.filter((row) => row.pipeline_stage === 'won').length;
  return `${((convertedCount / claimedCount) * 100).toFixed(1)}%`;
});
const filteredRows = computed(() =>
  claimableRows.value.filter((row) => {
    const industryMatched = !industryFilter.value || row.industry === industryFilter.value;
    const countryMatched = !countryFilter.value || row.country === countryFilter.value;
    return industryMatched && countryMatched;
  }),
);
const poolPage = ref(1);
const poolPageSize = 10;
const poolTotalPages = computed(() => Math.max(1, Math.ceil(filteredRows.value.length / poolPageSize)));
const paginatedClaimable = computed(() => {
  const start = (poolPage.value - 1) * poolPageSize;
  return filteredRows.value.slice(start, start + poolPageSize);
});

const industries = computed(() => [...new Set(claimableRows.value.map((row) => row.industry).filter(Boolean))].sort());
const countries = computed(() => [...new Set(claimableRows.value.map((row) => row.country).filter(Boolean))].sort());

const filteredMyLeads = computed(() =>
  allocation.mine.filter((row) => {
    const industryMatched = !myIndustryFilter.value || row.industry === myIndustryFilter.value;
    const countryMatched = !myCountryFilter.value || row.country === myCountryFilter.value;
    const statusMatched = !myStatusFilter.value || row.pipeline_stage === myStatusFilter.value;
    return industryMatched && countryMatched && statusMatched;
  }),
);
const myLeadPage = ref(1);
const myLeadPageSize = 10;
const myLeadTotalPages = computed(() => Math.max(1, Math.ceil(filteredMyLeads.value.length / myLeadPageSize)));
const paginatedMyLeads = computed(() => {
  const start = (myLeadPage.value - 1) * myLeadPageSize;
  return filteredMyLeads.value.slice(start, start + myLeadPageSize);
});

const myIndustries = computed(() => [...new Set(allocation.mine.map((row) => row.industry).filter(Boolean))].sort());
const myCountries = computed(() => [...new Set(allocation.mine.map((row) => row.country).filter(Boolean))].sort());

const formatDate = (value?: string | null) => {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return `${date.getMonth() + 1}/${String(date.getDate()).padStart(2, '0')}`;
};

const loadSalesPool = async () => {
  if (!auth.isSales) {
    allocation.claimable = [];
    allocation.mine = [];
    return;
  }
  claimMessage.value = '';
  await allocation.loadSalesPool();
};

const requestClaim = async (lead: LeadPoolItem, event: Event) => {
  claimMessage.value = '';
  claimTrigger.value = event.currentTarget instanceof HTMLElement ? event.currentTarget : null;
  pendingClaim.value = lead;
  await nextTick();
  claimConfirmButton.value?.focus();
};

const cancelClaim = async () => {
  const trigger = claimTrigger.value;
  pendingClaim.value = null;
  await nextTick();
  if (trigger?.isConnected) trigger.focus();
};

const handleClaimKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Escape' && !allocation.loading) void cancelClaim();
};

const confirmClaim = async () => {
  const selectedLead = pendingClaim.value;
  if (!selectedLead) return;
  if (!auth.isAuthenticated) {
    await router.push('/login');
    return;
  }
  try {
    await allocation.claim(selectedLead.lead_id, selectedLead.version ?? 0);
    await auth.loadProfile();
    claimMessage.value = `已领取 ${selectedLead.name}，可进入客户运营继续跟进。`;
    pendingClaim.value = null;
  } catch {
    if (!allocation.error) allocation.error = '领取失败';
  }
};

watch(
  () => ({
    profileLoaded: auth.profileLoaded,
    userId: auth.currentUser?.userId || '',
  }),
  ({ profileLoaded, userId }, previous) => {
    if (!previous || previous.userId !== userId) {
      allocation.claimable = [];
      allocation.mine = [];
      allocation.all = [];
      allocation.error = '';
      pendingClaim.value = null;
      claimMessage.value = '';
    }
    if (profileLoaded && userId) void loadSalesPool();
  },
  { immediate: true },
);

watch([industryFilter, countryFilter], () => {
  poolPage.value = 1;
});

watch([myIndustryFilter, myCountryFilter, myStatusFilter], () => {
  myLeadPage.value = 1;
});
</script>

<template>
  <div class="content-main legacy-allocation allocation-prototype">
    <div class="agent-live-bar">
      <div class="live-dot" />
      <span>客户分配 · 运行中</span>
      <div class="live-stat">
      </div>
    </div>

    <div class="legacy-page-title">客户分配</div>

    <div v-if="!auth.profileLoaded" class="alert-info">正在确认登录状态...</div>

    <div v-else-if="!auth.isAuthenticated" class="alert-info auth-prompt">
      <span>请先登录销售账号，再查看可领取线索。</span>
      <button class="btn btn-primary" @click="router.push('/login')">去登录</button>
    </div>

    <template v-else>
      <div v-if="allocation.error" class="alert-error" role="alert">{{ allocation.error }}</div>
      <div v-if="claimMessage" class="alert-info">{{ claimMessage }}</div>

      <div class="metric-cards col3 allocation-metric-cards">
        <article class="metric-card">
          <div class="metric-label">已领取</div>
          <div class="metric-val main">{{ assignedCount }}</div>
          <div class="metric-sub">本月累计</div>
        </article>
        <article class="metric-card">
          <div class="metric-label">跟进率</div>
          <div class="metric-val blue">{{ claimedFollowRate }}</div>
          <div class="metric-sub">本月</div>
        </article>
        <article class="metric-card">
          <div class="metric-label">转化率</div>
          <div class="metric-val blue">{{ conversionRate }}</div>
          <div class="metric-sub">领取→成交</div>
        </article>
      </div>

      <section class="panel allocation-panel">
        <div class="panel-header">
          <span>资源池</span>
        </div>
        <div class="panel-body no-padding">
          <div class="separate-filter-bar" aria-label="资源池筛选条件">
            <label class="filter-control">所在行业<select v-model="industryFilter" aria-label="资源池行业"><option value="">全部</option><option v-for="ind in industries" :key="ind" :value="ind">{{ industryLabel(ind) }}</option></select></label>
            <label class="filter-control">国家<select v-model="countryFilter" aria-label="资源池国家"><option value="">全部</option><option v-for="country in countries" :key="country" :value="country">{{ countryLabel(country) }}</option></select></label>
          </div>
          <table class="matrix-table">
            <thead>
              <tr>
                <th>所在行业</th>
                <th>公司名称</th>
                <th>公司简介</th>
                <th>官网</th>
                <th>国家</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="filteredRows.length === 0">
                <td colspan="6">暂无可领取线索</td>
              </tr>
              <tr v-for="(lead, index) in paginatedClaimable" :key="lead.lead_id" :class="{ 'highlight-row': index === 0 }">
                <td>{{ industryLabel(lead.industry) }}</td>
                <td class="customer-name">{{ lead.name }}</td>
                <td class="allocation-intro">{{ lead.intro || '-' }}</td>
                <td>
                  <a v-if="lead.website" :href="lead.website" target="_blank" rel="noreferrer">{{ lead.website.replace(/^https?:\/\//, '') }}</a>
                  <span v-else>-</span>
                </td>
                <td>{{ displayCountry(lead) }}</td>
                <td><button class="btn-xs primary" type="button" @click="requestClaim(lead, $event)">领取</button></td>
              </tr>
            </tbody>
          </table>
          <div class="ceo-lead-pagination">
            <span class="ceo-lead-page-info">第 {{ poolPage }} / {{ poolTotalPages }} 页（共 {{ filteredRows.length }} 条）</span>
            <div style="display:flex;gap:8px;"><button class="btn-xs" :disabled="poolPage <= 1" @click="poolPage = Math.max(1, poolPage - 1)">上一页</button><button class="btn-xs primary" :disabled="poolPage >= poolTotalPages" @click="poolPage = Math.min(poolTotalPages, poolPage + 1)">下一页</button></div>
          </div>
        </div>
      </section>

      <section class="panel allocation-panel">
        <div class="panel-header">
          <span>我的线索</span>
        </div>
        <div class="panel-body no-padding">
          <div class="separate-filter-bar" aria-label="我的线索筛选条件">
            <label class="filter-control">所在行业<select v-model="myIndustryFilter" aria-label="我的线索行业"><option value="">全部</option><option v-for="ind in myIndustries" :key="ind" :value="ind">{{ industryLabel(ind) }}</option></select></label>
            <label class="filter-control">国家<select v-model="myCountryFilter" aria-label="我的线索国家"><option value="">全部</option><option v-for="country in myCountries" :key="country" :value="country">{{ countryLabel(country) }}</option></select></label>
            <label class="filter-control">状态<select v-model="myStatusFilter" aria-label="我的线索状态"><option value="">全部</option><option v-for="stage in pipelineStages" :key="stage" :value="stage">{{ pipelineStageLabel(stage) }}</option></select></label>
          </div>
          <table class="matrix-table">
            <thead>
              <tr>
                <th>所在行业</th>
                <th>公司名称</th>
                <th>领取时间</th>
                <th>国家</th>
                <th>状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="allocation.mine.length === 0">
                <td colspan="6">暂无已领取线索</td>
              </tr>
              <tr v-else-if="filteredMyLeads.length === 0">
                <td colspan="6">没有符合当前筛选条件的线索，请调整或清空筛选条件</td>
              </tr>
              <tr v-for="lead in paginatedMyLeads" :key="lead.lead_id">
                <td>{{ industryLabel(lead.industry) }}</td>
                <td class="customer-name">{{ lead.name }}</td>
                <td>{{ formatDate(lead.claimed_at) }}</td>
                <td>{{ displayCountry(lead) }}</td>
                <td>
                  <span style="color:var(--blue-primary);font-weight:600;">{{ pipelineStageLabel(lead.pipeline_stage) }}</span>
                </td>
                <td><button class="btn-xs primary" type="button" @click="router.push('/customer-operation')">跟进</button></td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="ceo-lead-pagination">
          <span class="ceo-lead-page-info">第 {{ myLeadPage }} / {{ myLeadTotalPages }} 页（共 {{ filteredMyLeads.length }} 条）</span>
          <div style="display:flex;gap:8px;"><button class="btn-xs" :disabled="myLeadPage <= 1" @click="myLeadPage = Math.max(1, myLeadPage - 1)">上一页</button><button class="btn-xs primary" :disabled="myLeadPage >= myLeadTotalPages" @click="myLeadPage = Math.min(myLeadTotalPages, myLeadPage + 1)">下一页</button></div>
        </div>
      </section>
    </template>

    <div v-if="pendingClaim" class="legacy-modal-mask" role="presentation" @click.self="cancelClaim" @keydown="handleClaimKeydown">
      <div class="claim-dialog" role="dialog" aria-modal="true" aria-labelledby="claim-dialog-title" aria-describedby="claim-dialog-description">
        <div id="claim-dialog-title" class="claim-title">确认领取线索</div>
        <div id="claim-dialog-description" class="claim-message">
          确定领取 <strong>{{ pendingClaim.name }}</strong> 的线索？领取后需在7天内完成首次跟进。
        </div>
        <div class="claim-actions">
          <button ref="claimConfirmButton" class="btn-primary" type="button" :disabled="allocation.loading" @click="confirmClaim">确认领取</button>
          <button class="btn-outline" type="button" :disabled="allocation.loading" @click="cancelClaim">取消</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.allocation-filter { display: flex; align-items: center; gap: 6px; }
.allocation-filter select { min-width: 64px; max-width: 120px; padding: 3px 5px; border: 1px solid var(--border); border-radius: 5px; background: #fff; color: var(--text-primary); cursor: pointer; }
</style>
