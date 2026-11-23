<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue';

import type { LeadPoolItem } from '../../services/allocationApi';
import type { AnalysisCompany } from '../../services/leadApi';
import { countryLabel, pipelineStageLabel, regionCodeForCountryLabel } from '../../shared/utils/labels';
import { useAllocationStore } from '../../stores/allocation';
import { useLeadStore } from '../../stores/lead';

interface AssignRow {
  key?: string;
  channel: string;
  scenario: string;
  company: string;
  score: number;
  grade: string;
  region: string;
  country: string;
  tier: string;
  owner: string;
  status: string;
  suggestion: string;
  intro: string;
  website: string;
}

interface RankingRow {
  rank: number;
  name: string;
  region: string;
  amount: string;
  customerCount: number;
  conversionRate: string;
  followRate: string;
}

const allocation = useAllocationStore();
const lead = useLeadStore();
const rankingPeriod = ref<'month' | 'quarter' | 'year'>('month');
const filterAssignIndustry = ref('all');
const filterAssignCountry = ref('all');
const filterAssignScore = ref('all');
const filterAssignGrade = ref('all');
const filterAssignRegion = ref('all');
const filterAssignTier = ref('all');
const filterAssignStatus = ref('all');
const rankingNameFilter = ref('all');
const rankingRegionFilter = ref('all');
const sortKey = ref('');
const sortDir = ref<'asc' | 'desc'>('asc');
const selectedRow = ref<AssignRow | null>(null);
const detailCloseButton = ref<HTMLButtonElement | null>(null);
const detailTrigger = ref<HTMLElement | null>(null);

function toggleSort(key: string) {
  if (sortKey.value === key) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc';
  } else {
    sortKey.value = key;
    sortDir.value = 'asc';
  }
}
function sortIcon(key: string) {
  if (sortKey.value !== key) return '↕';
  return sortDir.value === 'asc' ? '↑' : '↓';
}

const fallbackRows: AssignRow[] = [
  { channel: 'B端', scenario: '商旅OTA', company: 'TechTravel Inc.', score: 91, grade: 'A', region: '北美', country: '美国', tier: 'MA', owner: '张伟', status: '已跟进', suggestion: '继续推进会议，补企业套餐报价。', intro: '北美企业差旅技术平台。', website: '' },
  { channel: 'B端', scenario: '差旅平台', company: 'GlobalLink Travel', score: 94, grade: 'A', region: '东亚', country: '日本', tier: 'MA', owner: '李明', status: '已跟进', suggestion: '推进企业差旅管理方案和试点范围。', intro: '企业差旅管理服务商。', website: '' },
  { channel: 'B端', scenario: '金融科技', company: 'NorthBridge Mobility', score: 84, grade: 'B', region: '北美', country: '美国', tier: 'SA', owner: '张伟', status: '今日待跟', suggestion: '24小时内首触达，先验证预算周期。', intro: '跨境支付与移动服务平台。', website: '' },
  { channel: 'B端', scenario: '差旅平台', company: 'Pacific TMC Japan', score: 86, grade: 'B', region: '东亚', country: '日本', tier: 'SA', owner: '李明', status: '已跟进', suggestion: '补齐预算人，推进日语场景方案。', intro: '日本本地企业差旅管理公司。', website: '' },
  { channel: 'B端', scenario: '差旅平台', company: 'J-Trip Solutions', score: 80, grade: 'B', region: '东亚', country: '日本', tier: 'SA', owner: '李明', status: '待触达', suggestion: '发送首封邮件，保留低成本培育节奏。', intro: '日本企业旅行解决方案提供商。', website: '' },
  { channel: 'B端', scenario: '商旅OTA', company: 'AsiaBiz Travel', score: 78, grade: 'B', region: '东南亚', country: '新加坡', tier: 'A', owner: '陈静', status: '已触达', suggestion: '进入低频培育，观察企业客户比例。', intro: '东南亚商旅预订平台。', website: '' },
  { channel: 'B端', scenario: '金融科技', company: 'FinMiles Wallet', score: 60, grade: 'C', region: '东南亚', country: '泰国', tier: 'A', owner: '陈静', status: '待触达', suggestion: '轻触达验证权益入口和预算窗口。', intro: '差旅积分与支付钱包。', website: '' },
  { channel: 'B端', scenario: '差旅平台', company: 'TravelCorp EU', score: 62, grade: 'C', region: '欧洲', country: '英国', tier: 'A', owner: '王芳', status: '48h未跟', suggestion: '暂停新增分配，先补决策人和邮箱。', intro: '欧洲企业差旅服务商。', website: '' },
  { channel: 'B端', scenario: '商旅OTA', company: 'VoyageSphere', score: 68, grade: 'C', region: '欧洲', country: '德国', tier: 'A', owner: '王芳', status: '跟进慢', suggestion: '主管介入检查，确认是否继续保留。', intro: '欧洲商旅 OTA。', website: '' },
  { channel: 'B端', scenario: '差旅平台', company: 'Global Stay Desk', score: 56, grade: 'C', region: '欧洲', country: '法国', tier: 'A', owner: '王芳', status: '72h未跟', suggestion: '先退回补数，暂缓正式推进。', intro: '全球住宿与差旅管理平台。', website: '' },
];

const rankingData = {
  month: [
    ['1', '张伟', '北美', '$8,400', '23', '15.2%', '94%'],
    ['2', '李明', '日本', '$6,200', '19', '12.1%', '88%'],
    ['3', '陈静', '东南亚', '$5,800', '16', '11.4%', '85%'],
    ['4', '王芳', '欧洲', '$2,100', '14', '8.3%', '71%'],
  ],
  quarter: [
    ['1', '张伟', '北美', '$25,600', '68', '14.8%', '92%'],
    ['2', '李明', '日本', '$19,400', '57', '12.6%', '87%'],
    ['3', '陈静', '东南亚', '$16,900', '49', '11.1%', '84%'],
    ['4', '王芳', '欧洲', '$6,700', '42', '7.9%', '70%'],
  ],
  year: [
    ['1', '张伟', '北美', '$92,000', '264', '13.9%', '91%'],
    ['2', '李明', '日本', '$70,500', '228', '11.7%', '86%'],
    ['3', '陈静', '东南亚', '$61,800', '190', '10.8%', '82%'],
    ['4', '王芳', '欧洲', '$23,600', '171', '7.4%', '69%'],
  ],
} as const;

type CustomerGrade = "A" | "B" | "C";
type SalesTier = "MA" | "SA" | "A";

const salesTierByCustomerGrade: Record<CustomerGrade, SalesTier> = {
  A: "MA",
  B: "SA",
  C: "A",
};

const gradeFromScore = (score: number): CustomerGrade => {
  if (score >= 80) return "A";
  if (score >= 60) return "B";
  return "C";
};

const salesTierForCustomerGrade = (grade: CustomerGrade): SalesTier => salesTierByCustomerGrade[grade];
const customerGradeForSalesTier = (tier: unknown): CustomerGrade | undefined => {
  const normalized = String(tier || "").toUpperCase();
  if (normalized === "MA") return "A";
  if (normalized === "SA") return "B";
  if (normalized === "A") return "C";
  return undefined;
};

const scenarioNames: Record<string, string> = { travel_platform: "差旅平台", travel_ota: "商旅OTA", ota: "商旅OTA", fintech: "金融科技", financial_technology: "金融科技", other: "其他" };
const scenarioText = (value: unknown) => { const text = String(value || "").trim(); return scenarioNames[text.toLowerCase()] || text || "其他"; };
const regionNames: Record<string, string> = { NA: '北美', EA: '东亚', SEA: '东南亚', EU: '欧洲', ME: '中东', OTHER: '其他' };
const regionText = (value: unknown, country?: unknown) => {
  const text = String(value || '').trim();
  const code = text.toUpperCase();
  const inferred = regionCodeForCountryLabel(String(country || '').trim());
  const isPending = ['待确认', '待补齐', '未知', 'UNKNOWN', 'N/A', '-'].includes(code);
  return (!isPending && (regionNames[text] || regionNames[code] || text)) || regionNames[inferred] || '其他';
};
const countryNames: Record<string, string> = { JAPAN: '日本', KOREA: '韩国', CHINA: '中国', USA: '美国', CANADA: '加拿大', SINGAPORE: '新加坡', MALAYSIA: '马来西亚', THAILAND: '泰国', UK: '英国', GERMANY: '德国', FRANCE: '法国' };
const countryText = (value: unknown) => { const text = String(value || '').trim(); return countryNames[text.toUpperCase()] || countryLabel(text) || text; };
const regionCountryText = (region: unknown, country: unknown) => {
  const values = [regionText(region), countryText(country)].filter((item) => item && item !== '待确认');
  return [...new Set(values)].join('-') || '待确认';
};
const companyKey = (value: unknown) => String(value || '').trim().toLowerCase();
const displayChannel = (value: unknown, fallback = 'B端') => {
  const text = String(value || fallback).trim() || fallback;
  const normalized = text.toLowerCase();
  if (normalized === 'dialog_web_search' || normalized === 'web_search' || normalized === 'search') {
    return 'B端';
  }
  return text;
};
const getAnalysisCompanyName = (row: AnalysisCompany) => row.company_name || row.name || row.company || '-';
const followStatus = (item: LeadPoolItem | undefined) => {
  if (!item || item.pool_status === 'claimable') return '待领取';
  if (!item.pipeline_stage || item.pipeline_stage === 'new') return '已领取';
  return pipelineStageLabel(item.pipeline_stage);
};

const normalizeLead = (item: LeadPoolItem): AssignRow => {
  const raw = item as LeadPoolItem & Record<string, any>;
  const rawScore = raw.score ?? raw.icp_score ?? raw.icpScore;
  const score = rawScore === undefined || rawScore === null || rawScore === '' ? 0 : Math.round(Number(rawScore));
  const owner = raw.owner_name || raw.owner_username || (item.pool_status === 'claimable' ? '待领取' : '-');
  const salesTier = item.sales_tier || raw.payload?.sales_tier || '-';
  const grade = raw.customer_size_grade
    || customerGradeForSalesTier(salesTier)
    || (score >= 0 ? gradeFromScore(score) : undefined)
    || 'C';
  return {
    key: item.lead_id,
    channel: 'B端',
    scenario: scenarioText(raw.industry || raw.industry_tag || raw.payload?.industry),
    company: item.name || raw.company_name || '-',
    score,
    grade,
    region: regionText(raw.region || raw.payload?.region, raw.country || raw.payload?.country),
    country: countryText(raw.country || raw.payload?.country) || '待确认',
    tier: salesTier,
    owner,
    status: raw.follow_status || followStatus(item),
    suggestion: raw.service_suggestion || raw.next_action || (item.pool_status === 'claimable' ? '待销售领取后进入跟进。' : '继续跟进并回流客户反馈。'),
    intro: String(item.intro || raw.company_intro || '').trim() || '暂无公司简介。',
    website: String(item.website || raw.website || '').trim(),
  };
};

const allocationByCompany = computed(() => {
  const map = new Map<string, LeadPoolItem>();
  allocation.all.forEach((item) => {
    const raw = item as LeadPoolItem & Record<string, any>;
    [item.lead_id, item.name, raw.company_id, raw.company_name].filter(Boolean).forEach((key) => {
      map.set(companyKey(key), item);
    });
  });
  return map;
});

const findAllocationForAnalysis = (item: AnalysisCompany) => {
  const company = getAnalysisCompanyName(item);
  const raw = item as AnalysisCompany & Record<string, any>;
  return allocationByCompany.value.get(companyKey(raw.promoted_lead_id))
    || allocationByCompany.value.get(companyKey(raw.promoted_company_id))
    || allocationByCompany.value.get(companyKey(item.company_id))
    || allocationByCompany.value.get(companyKey(item.validation_company_id))
    || allocationByCompany.value.get(companyKey(company));
};

const normalizeAnalysisCompany = (item: AnalysisCompany, matchedAllocation = findAllocationForAnalysis(item)): AssignRow => {
  const raw = item as AnalysisCompany & Record<string, any>;
  const rawScore = item.icp_score ?? item.icpScore ?? raw.score;
  const score = rawScore === undefined || rawScore === null || rawScore === '' ? 0 : Math.round(Number(rawScore));
  const company = getAnalysisCompanyName(item);
  const matchedRaw = (matchedAllocation || {}) as LeadPoolItem & Record<string, any>;
  const poolStatus = matchedAllocation?.pool_status;
  const owner = matchedRaw.owner_name || matchedRaw.owner_username || (poolStatus === 'claimed' ? '已分配' : '待领取');
  const status = matchedRaw.follow_status || followStatus(matchedAllocation);
  const grade = item.customer_size_grade
    || matchedRaw.customer_size_grade
    || customerGradeForSalesTier(matchedAllocation?.sales_tier)
    || gradeFromScore(score);

  return {
    key: String(item.company_id || item.validation_company_id || raw.candidate_id || raw.id || company),
    channel: 'B端',
    scenario: scenarioText(item.industry_tag || raw.industry),
    company,
    score,
    grade,
    region: regionText(item.region, item.country),
    country: countryText(item.country) || '待确认',
    tier: matchedAllocation?.sales_tier || salesTierForCustomerGrade(grade),
    owner,
    status,
    suggestion: matchedRaw.service_suggestion || matchedRaw.next_action || (poolStatus ? '已同步分配池，等待销售推进。' : '来自线索分析池，待同步到客户分配池。'),
    intro: String(item.company_intro || matchedAllocation?.intro || '').trim() || '暂无公司简介。',
    website: String(item.website || matchedAllocation?.website || '').trim(),
  };
};

const baseRows = computed(() => {
  const matchedLeadIds = new Set<string>();
  const analysisRows = lead.analysisCompanies.map((item) => {
    const matchedAllocation = findAllocationForAnalysis(item);
    if (matchedAllocation) matchedLeadIds.add(matchedAllocation.lead_id);
    return normalizeAnalysisCompany(item, matchedAllocation);
  });
  const allocationOnlyRows = allocation.all
    .filter((item) => !matchedLeadIds.has(item.lead_id))
    .map(normalizeLead);
  const mergedRows = [...analysisRows, ...allocationOnlyRows];
  return mergedRows.length > 0 ? mergedRows : fallbackRows;
});

const industryOptions = computed(() => [...new Set(baseRows.value.map((row) => row.scenario))].sort());
const countryOptions = computed(() => [...new Set(
  baseRows.value
    .filter((row) => filterAssignRegion.value === 'all' || row.region.startsWith(filterAssignRegion.value))
    .map((row) => row.country),
)].sort());
const tierOptions = computed(() => [...new Set(baseRows.value.map((row) => row.tier).filter((tier) => tier && tier !== '-'))].sort());
const statusOptions = computed(() => [...new Set(baseRows.value.map((row) => row.status).filter(Boolean))].sort());

watch(filterAssignRegion, () => {
  if (filterAssignCountry.value !== 'all' && !countryOptions.value.includes(filterAssignCountry.value)) filterAssignCountry.value = 'all';
});

const rows = computed(() => {
  let list = baseRows.value;

  // filters
  if (filterAssignIndustry.value !== 'all') list = list.filter(r => r.scenario === filterAssignIndustry.value);
  if (filterAssignCountry.value !== 'all') list = list.filter(r => r.country === filterAssignCountry.value);
  if (filterAssignScore.value !== 'all') {
    list = list.filter((row) => {
      if (filterAssignScore.value === '90_plus') return row.score >= 90;
      if (filterAssignScore.value === '80_89') return row.score >= 80 && row.score < 90;
      if (filterAssignScore.value === '70_79') return row.score >= 70 && row.score < 80;
      if (filterAssignScore.value === '60_69') return row.score >= 60 && row.score < 70;
      return row.score < 60;
    });
  }
  if (filterAssignGrade.value !== 'all') list = list.filter(r => r.grade === filterAssignGrade.value);
  if (filterAssignRegion.value !== 'all') list = list.filter(r => r.region.startsWith(filterAssignRegion.value));
  if (filterAssignTier.value !== 'all') list = list.filter(r => r.tier === filterAssignTier.value);
  if (filterAssignStatus.value !== 'all') list = list.filter(r => r.status === filterAssignStatus.value);

  // sort
  if (sortKey.value) {
    const k = sortKey.value;
    const d = sortDir.value === 'asc' ? 1 : -1;
    list = [...list].sort((a, b) => {
      const va = (a as any)[k] ?? ''; const vb = (b as any)[k] ?? '';
      if (typeof va === 'number') return (va - vb) * d;
      return String(va).localeCompare(String(vb)) * d;
    });
  }
  return sortKey.value ? list : [...list].sort((a, b) => b.score - a.score);
});

const activeFilters = computed(() => {
  let n = 0;
  if (filterAssignIndustry.value !== 'all') n++;
  if (filterAssignCountry.value !== 'all') n++;
  if (filterAssignScore.value !== 'all') n++;
  if (filterAssignGrade.value !== 'all') n++;
  if (filterAssignRegion.value !== 'all') n++;
  if (filterAssignTier.value !== 'all') n++;
  if (filterAssignStatus.value !== 'all') n++;
  return n;
});

const resetAssignFilters = () => {
  filterAssignIndustry.value = 'all';
  filterAssignCountry.value = 'all';
  filterAssignScore.value = 'all';
  filterAssignGrade.value = 'all';
  filterAssignRegion.value = 'all';
  filterAssignTier.value = 'all';
  filterAssignStatus.value = 'all';
};

const assignedCount = computed(() => rows.value.filter((row) => row.owner !== '待领取' && row.status !== '待领取').length);
const assignedRows = computed(() => rows.value.filter((row) => row.owner !== '待领取' && row.status !== '待领取'));
const followupPendingStatuses = new Set(['待领取', '已领取', '待触达', '今日待跟', '48h未跟', '72h未跟', '跟进慢']);
const followedCount = computed(() => assignedRows.value.filter((row) => !followupPendingStatuses.has(row.status)).length);
const claimedFollowRate = computed(() => (assignedRows.value.length ? Math.round((followedCount.value / assignedRows.value.length) * 100) : 0));
const wonCount = computed(() => assignedRows.value.filter((row) => row.status === '已成交').length);
const conversionRate = computed(() => (assignedRows.value.length ? ((wonCount.value / assignedRows.value.length) * 100).toFixed(1) : '0.0'));
const filterCount = activeFilters;
const unfollowed48h = computed(() => rows.value.filter((row) => row.status === '48h未跟' || row.status === '待触达').length);
const unfollowed72h = computed(() => rows.value.filter((row) => row.status === '72h未跟').length);

const rankingBaseRows = computed<RankingRow[]>(() => {
  const data = rankingData[rankingPeriod.value];
  return data.map((row) => ({
    rank: Number(row[0]),
    name: row[1],
    region: row[2],
    amount: row[3],
    customerCount: Number(row[4]),
    conversionRate: row[5],
    followRate: row[6],
  }));
});
const rankingNameOptions = computed(() => [...new Set(rankingBaseRows.value.map((row) => row.name))]);
const rankingRegionOptions = computed(() => [...new Set(rankingBaseRows.value.map((row) => row.region))]);
const rankingRows = computed(() => rankingBaseRows.value.filter((row) => (
  (rankingNameFilter.value === 'all' || row.name === rankingNameFilter.value)
  && (rankingRegionFilter.value === 'all' || row.region === rankingRegionFilter.value)
)));

const setRankingPeriod = (period: 'month' | 'quarter' | 'year') => {
  rankingPeriod.value = period;
};

const rankingTabClass = (period: 'month' | 'quarter' | 'year') => ({
  active: rankingPeriod.value === period,
});

const rankingTabStyle = (period: 'month' | 'quarter' | 'year') =>
  rankingPeriod.value === period
    ? {
        color: '#ffffff',
        background: 'var(--blue)',
        borderColor: 'var(--blue)',
      }
    : {};

const openDetail = async (row: AssignRow, event: Event) => {
  detailTrigger.value = event.currentTarget instanceof HTMLElement ? event.currentTarget : null;
  selectedRow.value = row;
  await nextTick();
  detailCloseButton.value?.focus();
};

const closeDetail = async () => {
  const trigger = detailTrigger.value;
  selectedRow.value = null;
  await nextTick();
  if (trigger?.isConnected) trigger.focus();
};

const handleKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Escape' && selectedRow.value) void closeDetail();
};

onMounted(() => {
  document.addEventListener('keydown', handleKeydown);
  void Promise.all([lead.loadAnalysisCompanies(500), allocation.loadAll()]);
});

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown);
});
</script>

<template>
  <div class="content-main boss-lead-assign">
    <div class="agent-live-bar">
      <div class="live-dot" />
      <span>客户分配 · 销售领用列表</span>
    </div>

    <div class="legacy-page-title">客户分配</div>
    <div class="legacy-page-subtitle">这里直接看哪些销售拿到了哪些客户线索、线索质量如何、有没有及时跟进，以及系统下一步建议。</div>

    <div class="metric-cards col3">
      <article class="metric-card"><div class="metric-label">已领取</div><div class="metric-val main">{{ assignedCount }}</div><div class="metric-sub">本月累计</div></article>
      <article class="metric-card"><div class="metric-label">跟进率</div><div class="metric-val blue">{{ claimedFollowRate }}%</div><div class="metric-sub">本月</div></article>
      <article class="metric-card"><div class="metric-label">转化率</div><div class="metric-val blue">{{ conversionRate }}%</div><div class="metric-sub">领取→成交</div></article>
    </div>

    <div v-if="allocation.error" class="alert-error" role="alert">{{ allocation.error }}</div>

    <section class="panel">
      <div class="panel-header"><span>客户线索</span></div>
      <div class="panel-body no-padding">
        <div class="assign-filter-bar" aria-label="客户分配筛选条件">
          <label>
            <span>行业</span>
            <select v-model="filterAssignIndustry" aria-label="行业筛选">
              <option value="all">全部行业</option>
              <option v-for="industry in industryOptions" :key="industry" :value="industry">{{ industry }}</option>
            </select>
          </label>
          <label>
            <span>ICP</span>
            <select v-model="filterAssignScore" aria-label="ICP 筛选">
              <option value="all">全部分数</option>
              <option value="90_plus">90+</option>
              <option value="80_89">80-89</option>
              <option value="70_79">70-79</option>
              <option value="60_69">60-69</option>
              <option value="under_60">&lt;60</option>
            </select>
          </label>
          <label>
            <span>客户等级</span>
            <select v-model="filterAssignGrade" aria-label="客户等级筛选">
              <option value="all">全部等级</option>
              <option value="A">A</option>
              <option value="B">B</option>
              <option value="C">C</option>
            </select>
          </label>
          <label>
            <span>区域市场</span>
            <select v-model="filterAssignRegion" aria-label="区域市场筛选">
              <option value="all">全部区域</option>
              <option value="北美">北美</option>
              <option value="东亚">东亚</option>
              <option value="东南亚">东南亚</option>
              <option value="欧洲">欧洲</option>
            </select>
          </label>
          <label>
            <span>国家</span>
            <select v-model="filterAssignCountry" aria-label="国家筛选">
              <option value="all">全部国家</option>
              <option v-for="country in countryOptions" :key="country" :value="country">{{ country }}</option>
            </select>
          </label>
          <label>
            <span>销售等级</span>
            <select v-model="filterAssignTier" aria-label="销售等级筛选">
              <option value="all">全部等级</option>
              <option v-for="tier in tierOptions" :key="tier" :value="tier">{{ tier }}</option>
            </select>
          </label>
          <label>
            <span>跟进状态</span>
            <select v-model="filterAssignStatus" aria-label="跟进状态筛选">
              <option value="all">全部状态</option>
              <option v-for="status in statusOptions" :key="status" :value="status">{{ status }}</option>
            </select>
          </label>
          <div class="assign-filter-actions">
            <span>共 {{ rows.length }} 条<span v-if="activeFilters"> · {{ activeFilters }} 个条件</span></span>
            <button type="button" :disabled="!activeFilters" @click="resetAssignFilters">清空筛选</button>
          </div>
        </div>
        <div class="table-scroll">
        <table class="matrix-table assign-management-table">
          <thead>
            <tr>
              <th class="sortable" @click="toggleSort('channel')">渠道 {{ sortIcon('channel') }}</th>
              <th class="sortable" @click="toggleSort('scenario')">行业 {{ sortIcon('scenario') }}</th>
              <th>公司名称</th>
              <th class="sortable" @click="toggleSort('score')">ICP {{ sortIcon('score') }}</th>
              <th>客户等级</th>
              <th>区域市场</th>
              <th>国家</th>
              <th>销售等级</th><th>销售名称</th>
              <th>跟进状态</th>
              <th>服务建议</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="row.key || `${row.company}:${row.country}`">
              <td>{{ row.channel }}</td><td>{{ row.scenario }}</td><td class="customer-name">{{ row.company }}</td>
              <td><span class="icp-score-number">{{ row.score || '-' }}</span></td>
              <td>{{ row.grade }}</td><td>{{ row.region }}</td><td>{{ row.country }}</td><td>{{ row.tier }}</td><td class="customer-name">{{ row.owner }}</td>
              <td><span :class="['stage-text', row.status.includes('未') || row.status === '待领取' ? 'amber' : 'green']">{{ row.status }}</span></td>
              <td>{{ row.suggestion }}</td>
            </tr>
            <tr v-if="!rows.length"><td colspan="11" class="assign-empty">没有符合当前条件的客户线索</td></tr>
          </tbody>
        </table>
        </div>
      </div>
    </section>

    <section class="panel ranking-panel">
      <div class="panel-header">
        <span>销售排名</span>
        <div class="period-tabs">
          <button class="period-tab" :class="rankingTabClass('month')" :style="rankingTabStyle('month')" type="button" @click="setRankingPeriod('month')">月度</button>
          <button class="period-tab" :class="rankingTabClass('quarter')" :style="rankingTabStyle('quarter')" type="button" @click="setRankingPeriod('quarter')">季度</button>
          <button class="period-tab" :class="rankingTabClass('year')" :style="rankingTabStyle('year')" type="button" @click="setRankingPeriod('year')">年度</button>
        </div>
      </div>
      <div class="panel-body no-padding">
        <table class="matrix-table">
          <thead>
            <tr>
              <th>排名</th>
              <th><label class="filter-head"><span>姓名</span><select v-model="rankingNameFilter" class="filter-select" aria-label="销售排名姓名"><option value="all">全部</option><option v-for="name in rankingNameOptions" :key="name" :value="name">{{ name }}</option></select></label></th>
              <th><label class="filter-head"><span>区域市场</span><select v-model="rankingRegionFilter" class="filter-select" aria-label="销售排名区域"><option value="all">全部</option><option v-for="region in rankingRegionOptions" :key="region" :value="region">{{ region }}</option></select></label></th>
              <th>成交额</th><th>客户量</th><th>转化率</th><th>跟进率</th>
            </tr>
          </thead>
          <tbody :key="rankingPeriod">
            <tr v-for="row in rankingRows" :key="row.name" :class="{ 'highlight-row': row.name === '李明' }">
              <td>{{ row.rank }}</td>
              <td class="customer-name">{{ row.name }}</td>
              <td>{{ row.region }}</td>
              <td>{{ row.amount }}</td>
              <td>{{ row.customerCount }}</td>
              <td>{{ row.conversionRate }}</td>
              <td>{{ row.followRate }}</td>
            </tr>
            <tr v-if="!rankingRows.length"><td colspan="7" class="assign-empty">没有符合当前筛选条件的销售数据</td></tr>
          </tbody>
        </table>
      </div>
    </section>


    <div v-if="selectedRow" class="legacy-modal-mask assign-detail-mask" role="presentation" @click.self="closeDetail">
      <section class="assign-detail-dialog" role="dialog" aria-modal="true" aria-labelledby="assign-detail-title">
        <button ref="detailCloseButton" class="dialog-close" type="button" aria-label="关闭客户详情" @click="closeDetail">关闭</button>
        <div class="lead-detail-heading">客户详情</div>
        <h2 id="assign-detail-title">{{ selectedRow.company }}</h2>
        <p class="assign-detail-subtitle">{{ selectedRow.scenario }} · {{ selectedRow.region }} · {{ selectedRow.country }}</p>
        <div class="assign-detail-grid">
          <div><span>ICP 评分</span><strong>{{ selectedRow.score || '-' }} / {{ selectedRow.grade }}</strong></div>
          <div><span>销售等级</span><strong>{{ selectedRow.tier }}</strong></div>
          <div><span>当前领取人</span><strong>{{ selectedRow.owner }}</strong></div>
          <div><span>跟进状态</span><strong>{{ selectedRow.status }}</strong></div>
        </div>
        <section class="assign-detail-section"><h3>公司简介</h3><p>{{ selectedRow.intro }}</p><a v-if="selectedRow.website" :href="selectedRow.website" target="_blank" rel="noreferrer">访问官网</a></section>
        <section class="assign-detail-section"><h3>服务建议</h3><p>{{ selectedRow.suggestion }}</p></section>
      </section>
    </div>
  </div>
</template>

<style scoped>
.alert-stat {
  color: #d97706; font-weight: 600;
}
.alert-stat.critical {
  color: #dc2626;
}
.live-stat {
  display: flex; gap: 14px; align-items: center;
}
.sortable {
  cursor: pointer; user-select: none;
}
.sortable:hover {
  color: var(--blue);
}
.filter-head {
  display: flex; gap: 6px; align-items: center;
}
.filter-select {
  font-size: 10px; padding: 2px 4px; border: 1px solid var(--border); border-radius: 4px; background: #fff; cursor: pointer; max-width: 100%;
}
.assign-filter-bar {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr)) auto;
  gap: 8px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  background: #f8fafc;
}
.assign-filter-bar label {
  display: grid;
  gap: 4px;
  min-width: 0;
  color: var(--text-muted);
  font-size: 10px;
  font-weight: 600;
}
.assign-filter-bar select {
  width: 100%;
  min-width: 0;
  height: 32px;
  padding: 0 24px 0 7px;
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--text-main);
  background: #fff;
  font: inherit;
  font-weight: 500;
}
.assign-filter-actions {
  display: flex;
  align-items: flex-end;
  justify-content: flex-end;
  gap: 6px;
  min-width: 0;
  color: var(--text-muted);
  font-size: 10px;
}
.assign-filter-actions button {
  height: 32px;
  padding: 0 9px;
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--text-main);
  background: #fff;
  cursor: pointer;
  white-space: nowrap;
}
.assign-filter-actions button:disabled { cursor: default; opacity: 0.45; }
.assign-management-table { min-width: 1280px; table-layout: fixed; }
.assign-management-table th,
.assign-management-table td { box-sizing: border-box; vertical-align: middle; }
.assign-management-table th:nth-child(1), .assign-management-table td:nth-child(1) { width: 72px; }
.assign-management-table th:nth-child(2), .assign-management-table td:nth-child(2) { width: 108px; }
.assign-management-table th:nth-child(3), .assign-management-table td:nth-child(3) { width: 150px; }
.assign-management-table th:nth-child(4), .assign-management-table td:nth-child(4) { width: 94px; }
.assign-management-table th:nth-child(5), .assign-management-table td:nth-child(5) { width: 90px; }
.assign-management-table th:nth-child(6), .assign-management-table td:nth-child(6) { width: 120px; }
.assign-management-table th:nth-child(7), .assign-management-table td:nth-child(7) { width: 100px; }
.assign-management-table th:nth-child(8), .assign-management-table td:nth-child(8) { width: 86px; }
.assign-management-table th:nth-child(9), .assign-management-table td:nth-child(9) { width: 100px; }
.assign-management-table th:nth-child(10), .assign-management-table td:nth-child(10) { width: 110px; }
.assign-management-table th:nth-child(11), .assign-management-table td:nth-child(11) { width: 210px; }
.assign-management-table th:nth-child(12), .assign-management-table td:nth-child(12) { width: 70px; text-align: center; }
.assign-empty { padding: 24px !important; text-align: center; color: var(--text-muted); }
.assign-detail-mask { align-items: flex-start; overflow: auto; padding: 28px 16px; }
.assign-detail-dialog { position: relative; width: min(720px, calc(100vw - 32px)); padding: 24px; border-radius: 8px; background: #fff; box-shadow: 0 20px 60px rgba(15, 23, 42, 0.24); }
.assign-detail-dialog h2 { margin: 8px 0 4px; font-size: 20px; letter-spacing: 0; }
.assign-detail-subtitle { margin: 0 0 18px; color: var(--text-muted); }
.assign-detail-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
.assign-detail-grid > div { display: flex; min-height: 72px; flex-direction: column; gap: 6px; padding: 12px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg-soft); }
.assign-detail-grid span { color: var(--text-muted); font-size: 11px; }
.assign-detail-section { margin-top: 16px; padding-top: 14px; border-top: 1px solid var(--border); }
.assign-detail-section h3 { margin: 0 0 6px; font-size: 13px; letter-spacing: 0; }
.assign-detail-section p { margin: 0; color: var(--text-main); line-height: 1.65; }
@media (max-width: 720px) {
  .assign-filter-bar { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .assign-detail-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 460px) {
  .assign-filter-bar { grid-template-columns: 1fr; }
}
</style>
