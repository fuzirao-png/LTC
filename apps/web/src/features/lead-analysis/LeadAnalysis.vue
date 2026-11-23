<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';

import { getApiErrorMessage } from '../../services/http';
import { leadApi, type AnalysisCompany } from '../../services/leadApi';
import { useLeadStore } from '../../stores/lead';
import { countryLabel, regionCodeForCountryLabel } from '../../shared/utils/labels';
import { filterAnalysisRows } from './leadAnalysisFilters.js';

type RawAnalysisCompany = AnalysisCompany & Record<string, any>;

interface AnalysisRow {
  id: string;
  source: string;
  sourceKey: string;
  scenario: string;
  company: string;
  score: number;
  grade: string;
  size: string;
  sizeKey: string;
  region: string;
  regionKey: string;
  country: string;
  summary: string;
  raw: RawAnalysisCompany | null;
}

interface OutreachPreviewItem {
  companyId: string;
  companyName: string;
  contactId: string;
  contactName: string;
  recipientEmail: string;
  region: string;
  industry: string;
  icpScore: number;
  contactScore: number;
  template: string;
}

interface OutreachPreviewCompany {
  companyId: string;
  companyName: string;
  region: string;
  industry: string;
  icpScore: number;
  contacts: OutreachPreviewItem[];
}

interface IcpDimension {
  key: string;
  title: string;
  score: string;
  max: number;
  text: string;
}

const lead = useLeadStore();
const selectedRow = ref<AnalysisRow | null>(null);
const page = ref(1);
const pageSize = 10;
const sortKey = ref('score');
const sortDir = ref<'asc' | 'desc'>('desc');
const filterSource = ref('all');
const filterIndustry = ref('all');
const filterScore = ref('all');
const filterSize = ref('all');
const filterRegion = ref('all');
const filterCountry = ref('all');
const selectedIds = ref<Set<string>>(new Set());
const outreachRunning = ref(false);
const outreachMessage = ref('');
const outreachError = ref('');
const outreachPreviewOpen = ref(false);
const outreachPreviewLoading = ref(false);
const outreachPreviewCompanies = ref<OutreachPreviewCompany[]>([]);
const selectedOutreachContactIds = ref<Set<string>>(new Set());

function toggleSort(key: string) { if (sortKey.value === key) { sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'; } else { sortKey.value = key; sortDir.value = 'asc'; } }
function sortIcon(key: string) { if (sortKey.value !== key) return '↕'; return sortDir.value === 'asc' ? '↑' : '↓'; }

const valueOf = (value: unknown, fallback = '-') => {
  const text = String(value ?? '').trim();
  return text || fallback;
};

const scenarioNames: Record<string, string> = { travel_platform: '差旅平台', travel: '差旅平台', tmc: '差旅平台', travel_management_company: '差旅平台', travel_ota: '商旅OTA', ota: '商旅OTA', fintech: '金融科技', financial_technology: '金融科技', fintech_platform: '金融科技', other: '其他' };
const scenarioText = (value: unknown) => { const text = String(value || '').trim(); return scenarioNames[text.toLowerCase()] || text || '其他'; };
const regionNames: Record<string, string> = { NA: '北美', EA: '东亚', SEA: '东南亚', EU: '欧洲', ME: '中东', OTHER: '其他' };
const regionText = (value: unknown, country?: unknown) => {
  const text = String(value || '').trim();
  const code = text.toUpperCase();
  const inferred = regionCodeForCountryLabel(String(country || '').trim());
  const isPending = ['待确认', '待补齐', '未知', 'UNKNOWN', 'N/A', '-'].includes(code);
  return (!isPending && (regionNames[text] || regionNames[code] || text)) || regionNames[inferred] || '其他';
};
const countryText = (value: unknown) => countryLabel(String(value || '').trim());
const regionCountryText = (region: unknown, country: unknown) => {
  const values = [regionText(region), countryText(country)].filter((item) => item && item !== '待确认');
  return [...new Set(values)].join('-') || '待确认';
};

const sourceText = (_value?: unknown) => 'B端';

const customerSize = (value: unknown, assessedGrade: unknown) => {
  const assessed = String(assessedGrade || '').trim().toUpperCase();
  const count = Number(value);
  const key = ['A', 'B', 'C'].includes(assessed)
    ? assessed
    : Number.isFinite(count) && count >= 0
      ? count >= 500 ? 'A' : count >= 100 ? 'B' : 'C'
      : 'unknown';
  return { key, label: key === 'unknown' ? '-' : key };
};

const gradeFromScore = (score: number) => {
  if (score >= 80) return 'A';
  if (score >= 60) return 'B';
  if (score >= 40) return 'C';
  return 'D';
};

const buildShortSummary = (raw: RawAnalysisCompany, score: number) => {
  const explicit = String(raw.icp_dimension_summary ?? '').trim();
  if (explicit) return explicit.length > 34 ? `${explicit.slice(0, 34)}...` : explicit;
  if (score >= 90) return '高度适合出境eSIM合作';
  if (score >= 75) return '具备合作潜力，需补关键证据';
  if (score >= 60) return '可观察，需验证场景和决策链';
  return '等待系统补齐分析判断';
};

const normalizeRow = (item: AnalysisCompany): AnalysisRow => {
  const raw = item as RawAnalysisCompany;
  const scorePayload = typeof item.icp_score === 'object' && item.icp_score !== null
    ? item.icp_score
    : null;
  const score = Math.round(Number(scorePayload?.total ?? item.icp_score ?? item.icpScore ?? raw.score ?? 0));
  const company = item.company_name || item.name || item.company || '-';
  const sourceKey = 'b2b';
  const size = customerSize(
    item.employee_count ?? raw.employeeCount ?? raw.company_size,
    item.customer_size_grade ?? raw.customerSizeGrade ?? raw.scale_score?.effective_tier,
  );
  return {
    id: String(item.company_id || item.validation_company_id || item.id || company),
    source: sourceText(sourceKey),
    sourceKey,
    scenario: scenarioText(item.industry_tag || raw.industry),
    company: valueOf(company),
    score,
    grade: String(item.icp_grade || item.icpGrade || scorePayload?.grade || gradeFromScore(score)),
    size: size.label,
    sizeKey: size.key,
    regionKey: regionText(item.region || raw.region, item.country || raw.country),
    region: regionText(item.region || raw.region, item.country || raw.country),
    country: countryText(item.country || raw.country) || '待确认',
    summary: buildShortSummary(raw, score),
    raw,
  };
};

const listNames = (value: unknown) => {
  if (!Array.isArray(value) || value.length === 0) return '-';
  return value
    .map((item) => {
      if (typeof item === 'string') return item;
      const record = item as Record<string, unknown>;
      return [record.name, record.title || record.role, record.email].filter(Boolean).join(' · ');
    })
    .filter(Boolean)
    .join('；');
};

const allRows = computed(() => lead.analysisCompanies.map(normalizeRow));
const sourceOptions = computed(() => [...new Map(allRows.value.map((row) => [row.sourceKey, row.source])).entries()]);
const industryOptions = computed(() => [...new Set(allRows.value.map((row) => row.scenario))].sort());
const regionOptions = computed(() => [...new Set(allRows.value.map((row) => row.regionKey))].sort());
const countryOptions = computed(() => [...new Set(
  allRows.value
    .filter((row) => filterRegion.value === 'all' || row.regionKey === filterRegion.value)
    .map((row) => row.country)
    .filter((value) => value !== '待确认'),
)].sort());

watch(filterRegion, () => {
  if (filterCountry.value !== 'all' && !countryOptions.value.includes(filterCountry.value)) filterCountry.value = 'all';
  page.value = 1;
});

const rows = computed(() => {
  let list = filterAnalysisRows(allRows.value, {
    source: filterSource.value,
    industry: filterIndustry.value,
    score: filterScore.value,
    size: filterSize.value,
    region: filterRegion.value,
  }) as AnalysisRow[];
  if (filterCountry.value !== 'all') list = list.filter((row) => row.country === filterCountry.value);
  const k = sortKey.value || 'score';
  const d = sortKey.value ? (sortDir.value === 'asc' ? 1 : -1) : -1;
  list = [...list].sort((a, b) => { const va = (a as any)[k] ?? ''; const vb = (b as any)[k] ?? ''; if (typeof va === 'number') return (va - vb) * d; return String(va).localeCompare(String(vb)) * d; });
  return list;
});
const totalPages = computed(() => Math.max(1, Math.ceil(rows.value.length / pageSize)));
const paginatedRows = computed(() => { const start = (page.value - 1) * pageSize; return rows.value.slice(start, start + pageSize); });
const selectedCount = computed(() => selectedIds.value.size);
const allPageSelected = computed(() => paginatedRows.value.length > 0 && paginatedRows.value.every((row) => selectedIds.value.has(row.id)));
const activeFilters = computed(() => {
  const scoreLabels: Record<string, string> = { '90_plus': '90+', '80_89': '80-89', '70_79': '70-79', '60_69': '60-69', 'under_60': '<60' };
  const sizeLabels: Record<string, string> = { A: 'A', B: 'B', C: 'C' };
  return [
    filterSource.value !== 'all' ? `来源：${sourceOptions.value.find(([key]) => key === filterSource.value)?.[1] || filterSource.value}` : '',
    filterIndustry.value !== 'all' ? `行业：${filterIndustry.value}` : '',
    filterScore.value !== 'all' ? `分数：${scoreLabels[filterScore.value]}` : '',
    filterSize.value !== 'all' ? `规模：${sizeLabels[filterSize.value]}` : '',
    filterRegion.value !== 'all' ? `区域：${filterRegion.value}` : '',
    filterCountry.value !== 'all' ? `国家：${filterCountry.value}` : '',
  ].filter(Boolean);
});
const total = computed(() => lead.analysisTotal || rows.value.length);
const displayedTotal = computed(() => activeFilters.value.length ? rows.value.length : total.value);
const abRate = computed(() => {
  const count = rows.value.filter((row) => row.grade === 'A' || row.grade === 'B').length;
  return rows.value.length ? Math.round((count / rows.value.length) * 100) : 0;
});

const selectedDimensions = computed<IcpDimension[]>(() => {
  const raw = selectedRow.value?.raw;
  const scorePayload: Record<string, unknown> = typeof raw?.icp_score === 'object' && raw.icp_score !== null
    ? raw.icp_score as Record<string, unknown>
    : {};
  const breakdown = raw?.icp_breakdown || raw?.icpBreakdown || {
    d1: scorePayload.D1 ?? scorePayload.d1,
    d2: scorePayload.D2 ?? scorePayload.d2,
    d3: scorePayload.D3 ?? scorePayload.d3,
    d4: scorePayload.D4 ?? scorePayload.d4,
  };
  const fallback = selectedRow.value?.summary || '等待系统补齐该维度解释。';
  return [
    { key: 'd1', title: 'D1 跨境出行场景匹配', score: valueOf(breakdown.d1 ?? raw?.d1_score), max: 40, text: valueOf(raw?.d1_score_explanation, fallback) },
    { key: 'd2', title: 'D2 增值服务/交叉销售潜力', score: valueOf(breakdown.d2 ?? raw?.d2_score), max: 30, text: valueOf(raw?.d2_score_explanation, fallback) },
    { key: 'd3', title: 'D3 客户规模与品牌背书', score: valueOf(breakdown.d3 ?? raw?.d3_score), max: 20, text: valueOf(raw?.d3_score_explanation, fallback) },
    { key: 'd4', title: 'D4 技术/API接入能力', score: valueOf(breakdown.d4 ?? raw?.d4_score), max: 10, text: valueOf(raw?.d4_score_explanation, fallback) },
  ];
});

const openDetail = (row: AnalysisRow) => {
  selectedRow.value = row;
};

const closeDetail = () => {
  selectedRow.value = null;
};

const resetFilters = () => {
  filterSource.value = 'all';
  filterIndustry.value = 'all';
  filterScore.value = 'all';
  filterSize.value = 'all';
  filterRegion.value = 'all';
  filterCountry.value = 'all';
  page.value = 1;
};

const toggleRowSelection = (rowId: string) => {
  const next = new Set(selectedIds.value);
  if (next.has(rowId)) next.delete(rowId);
  else next.add(rowId);
  selectedIds.value = next;
};

const togglePageSelection = () => {
  const next = new Set(selectedIds.value);
  const shouldSelect = !allPageSelected.value;
  for (const row of paginatedRows.value) {
    if (shouldSelect) next.add(row.id);
    else next.delete(row.id);
  }
  selectedIds.value = next;
};

const clearSelection = () => {
  selectedIds.value = new Set();
};

const runFirstTouch = async () => {
  if (outreachPreviewLoading.value || outreachRunning.value) return;
  outreachPreviewLoading.value = true;
  outreachMessage.value = '';
  outreachError.value = '';
  try {
    const result = await leadApi.previewEmailAutomation();
    outreachPreviewCompanies.value = (result?.companies || []) as OutreachPreviewCompany[];
    selectedOutreachContactIds.value = new Set(outreachPreviewCompanies.value.flatMap((company) => company.contacts.map((contact) => contact.contactId)));
    outreachPreviewOpen.value = true;
  } catch (error) {
    outreachError.value = getApiErrorMessage(error, '首轮触达执行失败');
  } finally {
    outreachPreviewLoading.value = false;
  }
};

const closeOutreachPreview = () => {
  if (outreachRunning.value) return;
  outreachPreviewOpen.value = false;
};

const waitForEmailAutomationRun = async (runId: string) => {
  for (let attempt = 0; attempt < 120; attempt += 1) {
    await new Promise((resolve) => window.setTimeout(resolve, 1000));
    const run = await leadApi.getEmailAutomationRun(runId);
    if (run?.status === 'completed') return run;
    if (run?.status === 'failed') throw new Error('首轮触达后台任务失败');
  }
  throw new Error('首轮触达任务处理超时，请稍后查看发送记录');
};

const confirmFirstTouch = async () => {
  const selectedContactIds = [...selectedOutreachContactIds.value];
  if (outreachRunning.value || !selectedContactIds.length) return;
  outreachRunning.value = true;
  outreachMessage.value = '';
  outreachError.value = '';
  try {
    const result = await leadApi.runEmailAutomation({ enabled: true, selectedContactIds });
    if (result?.status === 'already_running') {
      throw new Error('????????????????????');
    }
    const run = result?.status === 'queued' && result?.runId
      ? await waitForEmailAutomationRun(String(result.runId))
      : result;
    const sent = Number(run?.sent || 0);
    const failed = Number(run?.failed || 0);
    const skipped = Number(run?.skipped || 0);
    outreachMessage.value = `首轮触达已完成：发送成功 ${sent} 条，发送失败 ${failed} 条${skipped ? `，跳过 ${skipped} 条` : ''}`;
    outreachPreviewOpen.value = false;
    await lead.loadAnalysisCompanies();
  } catch (error) {
    outreachError.value = getApiErrorMessage(error, '首轮触达执行失败');
  } finally {
    outreachRunning.value = false;
  }
};
const outreachContactIds = computed(() => outreachPreviewCompanies.value.flatMap((company) => company.contacts.map((contact) => contact.contactId)));
const outreachAllSelected = computed(() => outreachContactIds.value.length > 0 && outreachContactIds.value.every((id) => selectedOutreachContactIds.value.has(id)));
const outreachSelectedCount = computed(() => selectedOutreachContactIds.value.size);
const toggleOutreachContact = (contactId: string) => {
  const next = new Set(selectedOutreachContactIds.value);
  if (next.has(contactId)) next.delete(contactId); else next.add(contactId);
  selectedOutreachContactIds.value = next;
};
const toggleAllOutreach = () => {
  selectedOutreachContactIds.value = outreachAllSelected.value ? new Set() : new Set(outreachContactIds.value);
};

onMounted(() => {
  void lead.loadAnalysisCompanies();
});
</script>

<template>
  <div class="content-main boss-lead-analysis">
    <div class="agent-live-bar">
      <div class="live-dot" />
      <span>线索分析 · 池子分析</span>
      <div class="live-stat">
      </div>
    </div>

    <div v-if="lead.error" class="alert-error" role="alert">{{ lead.error }}</div>

    <div class="dashboard-title-row">
      <div>
        <div class="dashboard-title">线索分析</div>
        <div class="dashboard-subtitle">总线索库仅展示经管理者筛选并人工入库、当前可由销售领取的线索。</div>
      </div>
    </div>

    <section class="panel lead-analysis-pool">
      <div class="panel-header lead-analysis-panel-header">
        <span>总线索库</span>
        <button class="btn-xs primary first-touch-button" type="button" :disabled="outreachRunning" @click="runFirstTouch">
          {{ outreachRunning ? '触达中...' : '首轮触达' }}
        </button>
      </div>
      <div v-if="outreachMessage" class="analysis-outreach-message" role="status">{{ outreachMessage }}</div>
      <div v-if="outreachError" class="analysis-outreach-error" role="alert">{{ outreachError }}</div>
      <div class="panel-body no-padding">
        <div class="analysis-filter-bar" aria-label="线索筛选条件">
          <label>来源<select v-model="filterSource" aria-label="来源" @change="page = 1"><option value="all">全部来源</option><option v-for="[key, label] in sourceOptions" :key="key" :value="key">{{ label }}</option></select></label>
          <label>行业<select v-model="filterIndustry" aria-label="行业" @change="page = 1"><option value="all">全部行业</option><option v-for="industry in industryOptions" :key="industry" :value="industry">{{ industry }}</option></select></label>
          <label>ICP评分<select v-model="filterScore" aria-label="ICP评分" @change="page = 1"><option value="all">全部分数</option><option value="90_plus">90+</option><option value="80_89">80-89</option><option value="70_79">70-79</option><option value="60_69">60-69</option><option value="under_60">&lt;60</option></select></label>
          <label>客户规模<select v-model="filterSize" aria-label="客户规模" @change="page = 1"><option value="all">全部等级</option><option value="A">A</option><option value="B">B</option><option value="C">C</option></select></label>
          <label>区域<select v-model="filterRegion" aria-label="区域" @change="page = 1"><option value="all">全部区域</option><option v-for="region in regionOptions" :key="region" :value="region">{{ region }}</option></select></label>
          <label>国家<select v-model="filterCountry" aria-label="国家" @change="page = 1"><option value="all">全部国家</option><option v-for="country in countryOptions" :key="country" :value="country">{{ country }}</option></select></label>
          <button class="btn-xs" type="button" :disabled="!activeFilters.length" @click="resetFilters">清空筛选</button>
        </div>
        <div class="analysis-filter-status" aria-live="polite">
          <span class="analysis-selection-status">已选 {{ selectedCount }} 条<button v-if="selectedCount" type="button" @click="clearSelection">清空选择</button></span>
        </div>
        <div class="table-scroll">
          <table class="matrix-table lead-analysis-table">
            <thead>
              <tr>
                <th class="selection-column"><input type="checkbox" aria-label="选择当前页全部线索" :checked="allPageSelected" @change="togglePageSelection"></th>
                <th class="sortable" @click="toggleSort('source')">来源 {{ sortIcon('source') }}</th>
                <th class="sortable" @click="toggleSort('scenario')">行业 {{ sortIcon('scenario') }}</th>
                <th>公司名称</th>
                <th class="sortable" @click="toggleSort('score')">ICP评分 {{ sortIcon('score') }}</th>
                <th class="sortable" @click="toggleSort('sizeKey')">客户规模 {{ sortIcon('sizeKey') }}</th>
                <th class="sortable" @click="toggleSort('region')">区域市场 {{ sortIcon('region') }}</th>
                <th>国家</th>
                <th class="analysis-action-column">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in paginatedRows" :key="row.id">
                <td class="selection-column"><input type="checkbox" :aria-label="`选择 ${row.company}`" :checked="selectedIds.has(row.id)" @change="toggleRowSelection(row.id)"></td>
                <td>{{ row.source }}</td>
                <td>{{ row.scenario }}</td>
                <td class="customer-name">{{ row.company }}</td>
                <td><span class="icp-score-number">{{ row.score || '-' }}</span></td>
                <td>{{ row.size }}</td>
                <td>{{ row.region }}</td>
                <td>{{ row.country }}</td>
                <td class="analysis-action-column"><button class="btn-xs primary" type="button" @click="openDetail(row)">查看</button></td>
              </tr>
              <tr v-if="!paginatedRows.length"><td colspan="9" class="analysis-empty">没有符合当前组合条件的线索</td></tr>
            </tbody>
          </table>
        </div>
        <!-- Pagination -->
        <div class="ceo-lead-pagination">
          <span class="ceo-lead-page-info">第 {{ page }} / {{ totalPages }} 页（共 {{ displayedTotal }} 条）</span>
          <div style="display:flex;gap:8px;"><button class="btn-xs" :disabled="page <= 1" @click="page = Math.max(1, page - 1)">上一页</button><button class="btn-xs primary" :disabled="page >= totalPages" @click="page = Math.min(totalPages, page + 1)">下一页</button></div>
        </div>
      </div>
    </section>


    <div v-if="outreachPreviewOpen" class="legacy-modal-mask outreach-preview-mask" @click.self="closeOutreachPreview">
      <section class="outreach-preview-dialog" role="dialog" aria-modal="true" aria-labelledby="outreach-preview-title">
        <div class="outreach-preview-header">
          <div>
            <div id="outreach-preview-title" class="lead-detail-heading">首轮触达预览</div>
            <div class="outreach-preview-summary">共 {{ outreachPreviewCompanies.length }} 家公司，{{ outreachSelectedCount }} 位联系人待发送；确认后将调用 email_outreach_agent 执行发送</div>
          </div>
          <button class="dialog-close" type="button" :disabled="outreachRunning" @click="closeOutreachPreview">关闭</button>
        </div>
        <div v-if="!outreachPreviewCompanies.length" class="outreach-preview-empty">当前没有符合条件的待触达公司</div>
        <div v-else class="outreach-preview-table-wrap">
          <table class="outreach-preview-table">
            <thead><tr><th><input type="checkbox" aria-label="全选联系人" :checked="outreachAllSelected" @change="toggleAllOutreach"></th><th>公司</th><th>联系人</th><th>邮箱</th><th>地区</th><th>ICP</th><th>联系人评分</th><th>模板</th></tr></thead>
            <tbody>
              <template v-for="company in outreachPreviewCompanies" :key="company.companyId">
                <tr class="outreach-company-row"><td colspan="8"><strong>{{ company.companyName || '-' }}</strong> · {{ company.region || '-' }} · ICP {{ company.icpScore || '-' }}</td></tr>
                <tr v-for="item in company.contacts" :key="item.companyId + '-' + item.contactId">
                  <td><input type="checkbox" :aria-label="'选择 ' + item.contactName" :checked="selectedOutreachContactIds.has(item.contactId)" @change="toggleOutreachContact(item.contactId)"></td>
                  <td>{{ item.companyName || '-' }}</td><td>{{ item.contactName || '-' }}</td><td>{{ item.recipientEmail || '-' }}</td><td>{{ item.region || '-' }}</td><td>{{ item.icpScore || '-' }}</td><td>{{ item.contactScore || '-' }}</td><td>{{ item.template === 'partner' ? '模板 A · 商旅跨境' : '模板 B · 企业差旅' }}</td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
        <div class="outreach-preview-actions">
          <router-link class="btn-xs" to="/email-automation">邮件触达历史</router-link>
          <div class="outreach-preview-actions-right">
          <button class="btn-xs" type="button" :disabled="outreachRunning" @click="closeOutreachPreview">取消</button>
          <button class="btn-xs primary" type="button" :disabled="outreachRunning || !outreachSelectedCount" @click="confirmFirstTouch">{{ outreachRunning ? '发送中...' : '确认发送' }}</button>
        </div>
        </div>
      </section>
    </div>

    <div v-if="selectedRow" class="legacy-modal-mask lead-detail-mask">
      <section class="lead-detail-dialog">
        <button class="dialog-close" type="button" @click="closeDetail">关闭</button>
        <div class="lead-detail-heading">分析</div>
        <div class="lead-detail-title">{{ selectedRow.company }}</div>
        <div class="lead-detail-subtitle">{{ selectedRow.scenario }} · {{ selectedRow.region }} · ICP {{ selectedRow.score || '-' }} / {{ selectedRow.grade }}</div>

        <section class="lead-company-profile">
          <h4>公司简介</h4>
          <p>{{ valueOf(selectedRow.raw?.company_intro || selectedRow.raw?.description || selectedRow.raw?.business_description, '暂无公司简介，等待后端补全。') }}</p>
        </section>

        <div class="lead-dimension-grid">
          <article v-for="item in selectedDimensions" :key="item.key" class="lead-dimension-card">
            <div class="lead-dimension-head">
              <strong>{{ item.title }}</strong>
              <span>{{ item.score }}/{{ item.max }}</span>
            </div>
            <p>{{ item.text }}</p>
          </article>
        </div>

      </section>
    </div>
  </div>
</template>

<style scoped>
.analysis-filter-bar { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 8px; padding: 10px; border-bottom: 1px solid var(--border); background: #f8fafc; }
.analysis-filter-bar label { display: flex; min-width: 116px; flex: 1 1 116px; max-width: 170px; flex-direction: column; gap: 4px; color: var(--text-muted); font-size: 10px; }
.analysis-filter-bar select { width: 100%; min-height: 30px; padding: 4px 6px; border: 1px solid var(--border); border-radius: 4px; background: #fff; color: var(--text-main); font-size: 12px; }
.analysis-filter-bar .btn-xs { min-height: 30px; }
.analysis-filter-status { display: flex; min-height: 34px; align-items: center; justify-content: space-between; gap: 12px; padding: 6px 10px; border-bottom: 1px solid var(--border); color: var(--text-muted); font-size: 11px; }
.analysis-filter-status > span:first-child { display: flex; flex-wrap: wrap; align-items: center; gap: 5px; }
.analysis-filter-status strong { padding: 2px 6px; border: 1px solid #bfdbfe; border-radius: 4px; background: #eff6ff; color: #1d4ed8; font-weight: 500; }
.analysis-selection-status { display: inline-flex; flex: 0 0 auto; align-items: center; gap: 6px; color: var(--text-main); }
.analysis-selection-status button { border: 0; background: transparent; color: var(--blue); cursor: pointer; font-size: 11px; }
.lead-analysis-panel-header { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.first-touch-button { min-width: 92px; }
.analysis-outreach-message, .analysis-outreach-error { margin: 10px 12px 0; padding: 8px 12px; border-radius: 6px; font-size: 13px; }
.analysis-outreach-message { color: #166534; background: #f0fdf4; border: 1px solid #bbf7d0; }
.analysis-outreach-error { color: #b91c1c; background: #fef2f2; border: 1px solid #fecaca; }
.outreach-preview-mask { z-index: 20; }
.outreach-preview-dialog { width: min(960px, calc(100vw - 32px)); max-height: min(720px, calc(100vh - 48px)); overflow: hidden; padding: 20px; border-radius: 10px; background: #fff; box-shadow: 0 20px 60px rgba(15, 23, 42, .2); } .outreach-preview-dialog .lead-detail-heading { font-size: 16px; } .outreach-preview-actions > .btn-xs { text-decoration: none; }
.outreach-preview-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.outreach-preview-summary { margin-top: 5px; color: var(--text-muted); font-size: 13px; }
.outreach-preview-table-wrap { max-height: 430px; margin-top: 18px; overflow: auto; border: 1px solid var(--border); border-radius: 6px; }
.outreach-preview-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.outreach-preview-table th, .outreach-preview-table td { padding: 10px 8px; border-bottom: 1px solid var(--border); text-align: left; white-space: nowrap; }
.outreach-preview-table th { background: #f8fafc; color: var(--text-muted); font-weight: 600; }
.outreach-preview-table tr:last-child td { border-bottom: 0; }
.outreach-preview-empty { margin-top: 24px; padding: 28px; border: 1px dashed var(--border); color: var(--text-muted); text-align: center; }
.outreach-preview-actions { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-top: 18px; }.outreach-preview-actions-right { display: flex; gap: 8px; }
.lead-analysis-table { min-width: 980px; }
.lead-analysis-table .selection-column { width: 42px; text-align: center; }
.lead-analysis-table th:nth-child(2), .lead-analysis-table td:nth-child(2) { width: 11%; }
.lead-analysis-table th:nth-child(3), .lead-analysis-table td:nth-child(3) { width: 13%; }
.lead-analysis-table th:nth-child(4), .lead-analysis-table td:nth-child(4) { width: 21%; }
.lead-analysis-table th:nth-child(5), .lead-analysis-table td:nth-child(5) { width: 9%; }
.lead-analysis-table th:nth-child(6), .lead-analysis-table td:nth-child(6) { width: 16%; }
.lead-analysis-table th:nth-child(7), .lead-analysis-table td:nth-child(7) { width: 15%; }
.lead-analysis-table th:nth-child(8), .lead-analysis-table td:nth-child(8) { width: 74px; text-align: center; }
.lead-analysis-table .analysis-action-column { width: 84px; min-width: 84px; text-align: center; white-space: nowrap; }
.lead-analysis-table .analysis-action-column .btn-xs { display: inline-flex; min-width: 52px; align-items: center; justify-content: center; white-space: nowrap; word-break: keep-all; writing-mode: horizontal-tb; }
.analysis-empty { padding: 24px !important; text-align: center !important; color: var(--text-muted); }
.sortable { cursor: pointer; user-select: none; }
.sortable:hover { color: var(--blue); }
@media (max-width: 720px) {
  .analysis-filter-bar { padding-right: 64px; }
  .analysis-filter-bar label { max-width: none; }
  .analysis-filter-status { align-items: flex-start; flex-direction: column; padding-right: 64px; }
}
</style>
