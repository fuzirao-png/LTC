<script setup lang="ts">
import { computed, onMounted, watch } from 'vue';
import { useRouter } from 'vue-router';

import DataTable, { type TableColumn } from '../../shared/components/DataTable.vue';
import PageSection from '../../shared/components/PageSection.vue';
import StatusBadge from '../../shared/components/StatusBadge.vue';
import { useAllocationStore } from '../../stores/allocation';
import { useAuthStore } from '../../stores/auth';
import { useLeadStore } from '../../stores/lead';

const allocation = useAllocationStore();
const auth = useAuthStore();
const lead = useLeadStore();
const router = useRouter();

const columns: TableColumn[] = [
  { key: 'name', label: '客户', width: '26%' },
  { key: 'sales_tier', label: '销售等级' },
  { key: 'region', label: '区域' },
  { key: 'score', label: 'ICP' },
  { key: 'pool_status', label: '领取状态' },
  { key: 'owner_name', label: '销售' },
  { key: 'claimed_at', label: '领取时间' },
];

const scoreOf = (row: Record<string, unknown>) => {
  const value = Number(row.icp_score ?? row.icpScore ?? row.score ?? 0);
  return Number.isFinite(value) ? Math.round(value) : 0;
};

const gradeOf = (row: Record<string, unknown>) => {
  const grade = String(row.icp_grade || row.icpGrade || '').toUpperCase();
  if (grade) return grade;
  const score = scoreOf(row);
  if (score >= 88) return 'A';
  if (score >= 75) return 'B';
  if (score >= 60) return 'C';
  return 'D';
};

const groupCount = <T,>(rows: T[], getter: (row: T) => string | undefined | null) =>
  rows.reduce<Record<string, number>>((acc, row) => {
    const key = getter(row)?.trim() || '未知';
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});

const averageScore = computed(() => {
  const scores = lead.analysisCompanies.map((item) => scoreOf(item as Record<string, unknown>)).filter(Boolean);
  if (!scores.length) return 0;
  return Math.round(scores.reduce((sum, score) => sum + score, 0) / scores.length);
});

const gradeCounts = computed(() => groupCount(lead.analysisCompanies, (row) => gradeOf(row as Record<string, unknown>)));
const abCount = computed(() => (gradeCounts.value.A || 0) + (gradeCounts.value.B || 0));
const abRate = computed(() => (lead.analysisCompanies.length ? Math.round((abCount.value / lead.analysisCompanies.length) * 100) : 0));
const claimedCount = computed(() => allocation.all.filter((item) => item.pool_status === 'claimed').length);
const claimRate = computed(() => (allocation.all.length ? Math.round((claimedCount.value / allocation.all.length) * 100) : 0));
const tierCounts = computed(() => groupCount(allocation.all, (row) => row.sales_tier));
const regionCounts = computed(() => groupCount(allocation.all, (row) => row.region || row.country));
const topRegions = computed(() => Object.entries(regionCounts.value).sort((a, b) => b[1] - a[1]).slice(0, 5));
const missingSummaryCount = computed(() => lead.missingDimensionSummaryCount);

const riskRegion = computed(() => {
  const entries = Object.entries(regionCounts.value).sort((a, b) => b[1] - a[1]);
  return entries[0]?.[0] || '暂无';
});

const managementJudgement = computed(() => {
  if (!allocation.all.length && !lead.analysisCompanies.length) return '等待数据进入系统';
  if (claimRate.value < 50) return '优先提升销售领取率';
  if (abRate.value < 50) return '先控量提质，再扩大分配';
  if (missingSummaryCount.value > 0) return '补齐系统判断，减少待确认样本';
  return '结构健康，可以稳定推进';
});

const formatDate = (value?: string | null) => {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
};

const loadAll = async () => {
  if (!auth.isAuthenticated) return;
  await Promise.all([allocation.loadAll(), lead.loadAnalysisCompanies(500), lead.loadValidationCompanies(500)]);
};

watch(
  () => [auth.profileLoaded, auth.isAuthenticated],
  ([profileLoaded, isAuthenticated]) => {
    if (profileLoaded && isAuthenticated && allocation.all.length === 0 && lead.analysisCompanies.length === 0) {
      void loadAll();
    }
  },
  { immediate: true },
);

onMounted(() => {
  if (auth.profileLoaded && auth.isAuthenticated) void loadAll();
});
</script>

<template>
  <PageSection title="战略视角" subtitle="管理侧查看线索质量、分配结构、销售领取和当前风险。">
    <template #actions>
      <button v-if="auth.isAuthenticated" class="btn" :disabled="allocation.loading || lead.loading" @click="loadAll">刷新</button>
    </template>

    <div v-if="!auth.profileLoaded" class="alert-info">正在确认登录状态...</div>

    <div v-else-if="!auth.isAuthenticated" class="alert-info auth-prompt">
      <span>请先登录后查看战略数据。</span>
      <button class="btn btn-primary" @click="router.push('/login')">去登录</button>
    </div>

    <template v-else>
      <div v-if="allocation.error || lead.error" class="alert-error">{{ allocation.error || lead.error }}</div>

      <div class="strategy-metrics">
        <div class="metric-card compact"><span>收集池</span><strong>{{ lead.validationTotal || lead.validationCompanies.length }}</strong></div>
        <div class="metric-card compact"><span>分析池</span><strong>{{ lead.analysisTotal || lead.analysisCompanies.length }}</strong></div>
        <div class="metric-card compact"><span>A/B 占比</span><strong>{{ abRate }}%</strong></div>
        <div class="metric-card compact"><span>平均 ICP</span><strong>{{ averageScore }}</strong></div>
        <div class="metric-card compact"><span>领取率</span><strong>{{ claimRate }}%</strong></div>
        <div class="metric-card compact"><span>待补判断</span><strong>{{ missingSummaryCount }}</strong></div>
      </div>

      <div class="strategy-grid">
        <section class="strategy-card">
          <h3>管理判断</h3>
          <p>{{ managementJudgement }}</p>
          <div class="strategy-kv">
            <span>当前重点区域</span><strong>{{ riskRegion }}</strong>
            <span>已领取</span><strong>{{ claimedCount }} / {{ allocation.all.length }}</strong>
            <span>MA / SA / A</span><strong>{{ tierCounts.MA || 0 }} / {{ tierCounts.SA || 0 }} / {{ tierCounts.A || 0 }}</strong>
          </div>
        </section>

        <section class="strategy-card">
          <h3>质量分析</h3>
          <p>
            分析池内 A 类 {{ gradeCounts.A || 0 }} 条，B 类 {{ gradeCounts.B || 0 }} 条，C/D 或待评分
            {{ Math.max(lead.analysisCompanies.length - abCount, 0) }} 条。管理重点应放在高分样本放大和低完整度样本补齐。
          </p>
        </section>

        <section class="strategy-card">
          <h3>区域分布</h3>
          <div v-if="topRegions.length === 0" class="empty-inline">暂无区域数据</div>
          <div v-for="[regionName, count] in topRegions" :key="regionName" class="distribution-row">
            <span>{{ regionName }}</span>
            <strong>{{ count }}</strong>
          </div>
        </section>
      </div>

      <DataTable :columns="columns" :rows="allocation.all" :empty-text="allocation.loading ? '加载中...' : '暂无分配数据'">
        <template #cell-pool_status="{ row }">
          <StatusBadge :status="row.pool_status" />
        </template>
        <template #cell-owner_name="{ row }">
          {{ row.owner_name || row.owner_username || '-' }}
        </template>
        <template #cell-claimed_at="{ row }">
          {{ formatDate(row.claimed_at) }}
        </template>
      </DataTable>
    </template>
  </PageSection>
</template>
