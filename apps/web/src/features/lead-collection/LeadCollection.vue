<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';

import {
  DEFAULT_LEAD_SEARCH_TARGET,
  MAX_LEAD_SEARCH_RESULTS,
  leadApi,
  type AnalysisCompany,
} from '../../services/leadApi';
import { useLeadStore } from '../../stores/lead';
import { contactDisplayName, contactEmail, contactTitle, formatContactSummary, sortContacts } from '../../shared/utils/contactOrdering.js';
import { countryLabel, regionCodeForCountryLabel, regionLabel } from '../../shared/utils/labels';
import { parseLeadSearchTarget } from './leadSearchTarget';

const query = ref('');
const uploadInput = ref<HTMLInputElement | null>(null);
const selectedDetail = ref<Record<string, any> | null>(null);
const detailLoading = ref(false);
const selectedRowIds = ref<string[]>([]);
const actionMessage = ref('');
const currentPage = ref(1);
const pageSize = 10;
const lead = useLeadStore();
const now = ref(Date.now());
let clockTimer: number | undefined;

// ---- filters (prototype-aligned) ----
const filterIndustry = ref('all');
const filterScore = ref('all');
const filterSize = ref('all');
const filterRegion = ref('all');

const fallbackLogs = [
  { role: 'agent' as const, text: '已接入线索收集能力，可按区域、行业、场景查找候选公司。' },
  { role: 'trace' as const, text: '当前仅展示数据库中的真实候选线索。' },
];

const getName = (item: AnalysisCompany) => item.company_name || item.name || item.company || '-';
const getId = (item: AnalysisCompany, index: number) =>
  String(item.validation_company_id || item.company_id || item.id || getName(item) || index);
const getScore = (item: AnalysisCompany) => Math.round(Number(item.icp_score ?? item.icpScore ?? 0));
const getScoreText = (score: number) => (score > 0 ? String(score) : '待评分');
const sizeTier = (value: unknown) => {
  const text = String(value || '').trim().toLowerCase();
  if (['a', 'b', 'c'].includes(text)) return text.toUpperCase();
  const number = Number((text.match(/\d+/) || ['0'])[0]);
  return number >= 500 ? 'A' : number >= 100 ? 'B' : 'C';
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
const displayChannel = (_value?: unknown) => 'B端';
const websiteHref = (value: unknown) => {
  const text = String(value || '').trim();
  if (!text || ['待补齐', '-', '未知'].includes(text)) return '';
  return /^https?:\/\//i.test(text) ? text : `https://${text}`;
};
const contactText = (value: unknown) => Array.isArray(value) ? formatContactSummary(value, 2) : String(value || '').trim();
const selectedDetailContacts = computed(() => sortContacts(Array.isArray(selectedDetail.value?.contacts) ? selectedDetail.value.contacts : []));

const sourceRows = computed(() => {
  if (lead.searchRows.length) return lead.searchRows;
  if (lead.validationCompanies.length) return lead.validationCompanies;
  return [];
});

interface LeadRow {
  id: string;
  raw: AnalysisCompany | null;
  name: string;
  channel: string;
  scenario: string;
  region: string;
  regionKey: string;
  country: string;
  score: number;
  size: string;
  website: string;
  contacts: string;
  intro: string;
}

const rows = computed<LeadRow[]>(() => {
  if (!sourceRows.value.length) return [];
  return sourceRows.value.map((item, index) => ({
    id: getId(item, index),
    raw: item,
    name: getName(item),
    channel: displayChannel((item as any).channel || (item as any).source || (item as any).source_channel),
    scenario: scenarioText(item.industry_tag || (item as any).industry),
    regionKey: regionText(item.region, item.country),
    region: regionText(item.region, item.country),
    country: countryText(item.country) || '待确认',
    score: getScore(item),
    size: sizeTier((item as any).customer_size_grade || (item as any).size || (item as any).companySize || (item as any).company_size || (item as any).employee_count || (item as any).employeeCount || (item as any).organization_size || (item as any).organization_num_employees || (item as any).organization_employee_count || (item as any).headcount),
    website: (item as any).website || (item as any).official_website || '待补齐',
    contacts:
      contactText((item as any).contacts) ||
      (item as any).contact_name ||
      (Array.isArray((item as any).decision_makers)
        ? (item as any).decision_makers.map((c: any) => c.name).filter(Boolean).slice(0, 2).join('、')
        : '') ||
      '待补齐',
    intro: item.company_intro || '暂无公司简介',
  })).sort((a, b) => b.score - a.score);
});

// ---- filtering ----
const filteredRows = computed(() => {
  return rows.value.filter(item => {
    if (filterIndustry.value !== 'all' && item.scenario !== filterIndustry.value) return false;
    if (filterScore.value !== 'all') {
      const s = item.score;
      if (filterScore.value === '90+' && s < 90) return false;
      if (filterScore.value === '80-89' && (s < 80 || s >= 90)) return false;
      if (filterScore.value === '70-79' && (s < 70 || s >= 80)) return false;
      if (filterScore.value === '60-69' && (s < 60 || s >= 70)) return false;
      if (filterScore.value === 'lt60' && s >= 60) return false;
    }
    if (filterSize.value !== 'all') {
      if (filterSize.value !== item.size) return false;
    }
    if (filterRegion.value !== 'all' && item.regionKey !== filterRegion.value) return false;
    return true;
  });
});

const totalPages = computed(() => Math.max(1, Math.ceil(filteredRows.value.length / pageSize)));
const paginatedRows = computed(() => {
  const start = (currentPage.value - 1) * pageSize;
  return filteredRows.value.slice(start, start + pageSize);
});

watch(totalPages, (pageCount) => {
  currentPage.value = Math.min(currentPage.value, pageCount);
});

function setFilter(key: 'industry' | 'score' | 'size' | 'region', val: string) {
  if (key === 'industry') filterIndustry.value = val;
  else if (key === 'score') filterScore.value = val;
  else if (key === 'size') filterSize.value = val;
  else if (key === 'region') filterRegion.value = val;
  currentPage.value = 1;
}

const activeFilterCount = computed(() => {
  let n = 0;
  if (filterIndustry.value !== 'all') n++;
  if (filterScore.value !== 'all') n++;
  if (filterSize.value !== 'all') n++;
  if (filterRegion.value !== 'all') n++;
  return n;
});

function clearFilters() {
  filterIndustry.value = 'all';
  filterScore.value = 'all';
  filterSize.value = 'all';
  filterRegion.value = 'all';
  currentPage.value = 1;
}

const logs = computed(() => (lead.searchLogs.length ? lead.searchLogs : fallbackLogs));
const candidateCount = computed(() => rows.value.length);
const pendingCount = computed(() => rows.value.length);
const selectedSourceRows = computed(() =>
  rows.value.filter((row) => selectedRowIds.value.includes(row.id)).map((row) => row.raw).filter((row): row is AnalysisCompany => Boolean(row)),
);
const allRowsSelected = computed(() => rows.value.length > 0 && rows.value.every((row) => selectedRowIds.value.includes(row.id)));
const searchElapsed = computed(() => {
  const startedAt = Date.parse(lead.searchStartedAt);
  if (!Number.isFinite(startedAt)) return '刚刚开始';
  const totalSeconds = Math.max(0, Math.floor((now.value - startedAt) / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return minutes ? `${minutes}分${String(seconds).padStart(2, '0')}秒` : `${seconds}秒`;
});
const visibleSearchProgress = computed(() => Math.min(100, Math.max(3, lead.searchProgress || 0)));
const searchCountText = computed(() => {
  if (!lead.searchTargetCount) return '正在识别候选企业';
  return `已完成 ${lead.searchCompletedCount} / ${lead.searchTargetCount} 家`;
});

const runSearch = async () => {
  if (lead.searching || !query.value.trim()) return;
  currentPage.value = 1;
  clearFilters();
  const targetCount = parseLeadSearchTarget(query.value, MAX_LEAD_SEARCH_RESULTS) ?? DEFAULT_LEAD_SEARCH_TARGET;
  await lead.runDialogueSearch(query.value, targetCount);
  await lead.loadValidationCompanies(100, true);
  selectedRowIds.value = lead.searchRows.length ? lead.searchRows.map((item, index) => getId(item, index)) : [];
};

const saveCurrentRows = async () => {
  await lead.saveRowsToAnalysisAndAllocation(selectedSourceRows.value);
  await lead.loadValidationCompanies(100, true);
  selectedRowIds.value = [];
};

const saveAllRows = async () => {
  await lead.saveRowsToAnalysisAndAllocation(rows.value.map((row) => row.raw).filter((row): row is AnalysisCompany => Boolean(row)));
  await lead.loadValidationCompanies(100, true);
  selectedRowIds.value = [];
};

const backfillSelectedRows = async () => {
  if (selectedSourceRows.value.length === 0) return;
  const result = await lead.backfillRows(selectedSourceRows.value);
  await lead.loadValidationCompanies(100, true);
  actionMessage.value = `已触发 ${result.updated_count} 条线索的后端补全任务${result.failed_count ? `，失败 ${result.failed_count} 条` : ''}。`;
};

const fillHighPotentialQuery = () => {
  query.value = '找高潜差旅平台、商旅OTA、金融科技客户';
};

const uploadCandidates = async (event: Event) => {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  actionMessage.value = '正在导入 CSV...';
  try {
    const result = await leadApi.importCandidates(file);
    actionMessage.value = `已从 ${file.name} 导入 ${result.imported_count} 条候选线索。`;
    await lead.loadValidationCompanies(100, true);
  } catch (error) {
    actionMessage.value = error instanceof Error ? error.message : 'CSV 导入失败。';
  } finally {
    input.value = '';
  }
};

const openLeadDetail = async (row: LeadRow) => {
  selectedDetail.value = null;
  detailLoading.value = true;
  try {
    selectedDetail.value = row.raw ? await leadApi.getCandidate(row.id) : {
      company_name: row.name, website: row.website, company_intro: row.intro,
      region_code: row.region, icp_score: { total: row.score }, contacts: [],
    };
  } catch (error) {
    actionMessage.value = error instanceof Error ? error.message : '线索详情加载失败。';
  } finally {
    detailLoading.value = false;
  }
};

const toggleAll = (checked: boolean) => {
  selectedRowIds.value = checked ? rows.value.filter((row) => row.raw).map((row) => row.id) : [];
};

const toggleRow = (rowId: string, checked: boolean) => {
  selectedRowIds.value = checked ? Array.from(new Set([...selectedRowIds.value, rowId])) : selectedRowIds.value.filter((id) => id !== rowId);
};

onMounted(() => {
  clockTimer = window.setInterval(() => { now.value = Date.now(); }, 1000);
  if (!lead.searchLogs.length) {
    lead.addSearchLog('agent', '已接入线索收集能力，可按区域、行业、场景查找候选公司。');
  }
  void lead.loadValidationCompanies(100);
  void lead.resumeDialogueSearch();
});

onUnmounted(() => {
  if (clockTimer !== undefined) window.clearInterval(clockTimer);
});
</script>

<template>
  <div class="content-main boss-lead-collection">
    <div class="agent-live-bar">
      <div class="live-dot" />
      <span>线索收集 · 对话入库</span>
      <div class="live-stat">
        <span>今日对话 <strong>{{ logs.length }}次</strong></span>
        <span>候选线索 <strong>{{ candidateCount }}条</strong></span>
        <span>待筛选 <strong>{{ pendingCount }}条</strong></span>
      </div>
    </div>

    <div class="dashboard-title-row">
      <div>
        <div class="dashboard-title">线索收集</div>
        <div class="dashboard-subtitle">这里主要通过对话 UI 收集线索库：管理者描述要找的线索，系统承接后端搜索能力，返回候选公司、命中原因和入库动作。</div>
      </div>
    </div>

    <section class="ceo-lead-finder">
      <div class="ceo-lead-finder-head">
        <div>
          <div class="ceo-lead-finder-title">搜索线索结果</div>
          <div class="ceo-lead-finder-sub">上方展示候选线索，管理者可先补全和筛选，再将确认通过的线索人工入库，也可以一键全部入库。</div>
        </div>
      </div>

      <div class="ceo-lead-finder-body">
        <div class="ceo-lead-results">
          <div class="ceo-lead-result-top">
            <div>
              <div class="ceo-lead-result-title">候选线索结果</div>
              <div class="ceo-lead-result-summary">
                {{ filteredRows.length !== rows.length
                  ? `筛选后 ${filteredRows.length} 条（共 ${rows.length} 条）`
                  : `找到 ${rows.length} 条候选线索，已按匹配度排序。` }}
              </div>
            </div>
            <div class="ceo-lead-result-tools">
              <label><input type="checkbox" :checked="allRowsSelected" @change="toggleAll(($event.target as HTMLInputElement).checked)" />全选</label>
            </div>
          </div>

          <div class="lead-collection-filter-bar" aria-label="候选线索筛选条件">
            <label>
              <span>区域市场</span>
              <select :value="filterRegion" @change="setFilter('region', ($event.target as HTMLSelectElement).value)">
                <option value="all">全部区域</option>
                <option value="东亚">东亚</option>
                <option value="北美">北美</option>
                <option value="东南亚">东南亚</option>
                <option value="欧洲">欧洲</option>
                <option value="中东">中东</option>
                <option value="其他">其他</option>
              </select>
            </label>
            <label>
              <span>应用场景</span>
              <select :value="filterIndustry" @change="setFilter('industry', ($event.target as HTMLSelectElement).value)">
                <option value="all">全部场景</option>
                <option value="差旅平台">差旅平台</option>
                <option value="商旅OTA">商旅OTA</option>
                <option value="金融科技">金融科技</option>
                <option value="其他">其他</option>
              </select>
            </label>
            <label>
              <span>ICP评分</span>
              <select :value="filterScore" @change="setFilter('score', ($event.target as HTMLSelectElement).value)">
                <option value="all">全部分数</option>
                <option value="90+">90+</option>
                <option value="80-89">80-89</option>
                <option value="70-79">70-79</option>
                <option value="60-69">60-69</option>
                <option value="lt60">&lt;60</option>
              </select>
            </label>
            <label>
              <span>客户规模</span>
              <select :value="filterSize" @change="setFilter('size', ($event.target as HTMLSelectElement).value)">
                <option value="all">全部规模</option>
                <option value="A">A</option>
                <option value="B">B</option>
                <option value="C">C</option>
              </select>
            </label>
            <button class="btn-xs" type="button" :disabled="activeFilterCount === 0" @click="clearFilters">清空筛选</button>
          </div>

          <div class="lead-collection-filter-status">
            <span>筛选结果 {{ filteredRows.length }} 条</span>
            <span v-if="activeFilterCount">已启用 {{ activeFilterCount }} 个筛选条件</span>
          </div>

          <div class="ceo-lead-list">
            <div class="table-scroll">
              <table class="matrix-table ceo-lead-table">
                <thead>
                  <tr>
                    <th class="check-col"></th>
                    <th class="region-col">区域市场</th>
                    <th class="scene-col">应用场景</th>
                    <th class="name-col">公司名称</th>
                    <th class="icp-col">ICP评分</th>
                    <th class="size-col">客户规模</th>
                    <th class="view-col">查看</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(item) in paginatedRows" :key="item.id">
                    <td><input type="checkbox" :aria-label="`选择线索 ${item.name}`" :checked="selectedRowIds.includes(item.id)" :disabled="!item.raw" @change="toggleRow(item.id, ($event.target as HTMLInputElement).checked)" /></td>
                    <td><span class="ceo-lead-cell" :title="item.region">{{ item.region }}</span></td>
                    <td><span class="ceo-lead-cell" :title="item.scenario">{{ item.scenario }}</span></td>
                    <td><span class="ceo-lead-cell ceo-lead-name" :title="item.name">{{ item.name }}</span></td>
                    <td><span class="ceo-lead-cell ceo-lead-icp" :title="getScoreText(item.score)">{{ getScoreText(item.score) }}</span></td>
                    <td><span class="ceo-lead-cell" :title="item.size">{{ item.size }}</span></td>
                    <td>
                      <button class="ceo-lead-view-btn" type="button" :aria-label="`查看 ${item.name} 的详情`" @click="openLeadDetail(item)">查看</button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- 分页控件 -->
          <div class="ceo-lead-pagination">
            <span class="ceo-lead-page-info">第 {{ currentPage }} / {{ totalPages }} 页（共 {{ filteredRows.length }} 条）</span>
            <div style="display:flex;gap:8px;">
              <button class="btn-xs" :disabled="currentPage <= 1" @click="currentPage = Math.max(1, currentPage - 1)">上一页</button>
              <button class="btn-xs primary" :disabled="currentPage >= totalPages" @click="currentPage = Math.min(totalPages, currentPage + 1)">下一页</button>
            </div>
          </div>

          <div class="ceo-lead-actions">
            <button class="btn-xs" type="button" :disabled="lead.saving || selectedSourceRows.length === 0" @click="backfillSelectedRows">批量回拨</button>
            <button class="btn-xs primary" type="button" :disabled="lead.saving || selectedSourceRows.length === 0" @click="saveCurrentRows">批量入库</button>
            <button class="btn-xs primary" type="button" :disabled="lead.saving || rows.every((row) => !row.raw)" @click="saveAllRows">全部入库</button>
          </div>
        </div>

        <div class="ceo-lead-chat">
          <div class="ceo-lead-quick-actions">
          </div>
          <section v-if="lead.searching" class="lead-search-progress" role="status" aria-live="polite">
            <div class="lead-search-progress-head">
              <div class="lead-search-progress-title">
                <span class="lead-search-spinner" aria-hidden="true" />
                <div>
                  <strong>后台正在收集线索</strong>
                  <span>{{ searchCountText }} · {{ searchElapsed }}</span>
                </div>
              </div>
              <button type="button" :disabled="lead.cancellingSearch" @click="lead.cancelSearch">
                {{ lead.cancellingSearch ? '取消中' : '取消' }}
              </button>
            </div>
            <div class="lead-search-progress-track" role="progressbar" aria-label="线索搜索进度" :aria-valuenow="visibleSearchProgress" aria-valuemin="0" aria-valuemax="100">
              <span :style="{ width: `${visibleSearchProgress}%` }" />
            </div>
            <div class="lead-search-progress-detail">
              <span>{{ lead.searchProgressMessage || '正在调用外部数据源' }}</span>
              <strong>{{ visibleSearchProgress }}%</strong>
            </div>
            <p>搜索会在后台继续，可切换页面；候选完成后会逐条出现在左侧结果中。</p>
          </section>
          <div class="ceo-lead-chat-log">
            <div v-for="(item, index) in logs" :key="index" :class="['ceo-lead-msg', item.role === 'user' ? 'user' : 'agent']">{{ item.text }}</div>
            <div v-if="lead.error" class="ceo-lead-msg agent" role="alert">{{ lead.error }}</div>
            <div v-if="lead.lastSaveMessage" class="ceo-lead-msg agent">{{ lead.lastSaveMessage }}</div>
            <div v-if="actionMessage" class="ceo-lead-msg agent">{{ actionMessage }}</div>
          </div>
          <div class="ceo-lead-prompts" />
<div class="ceo-lead-input-row">
            <input ref="uploadInput" class="sr-only" type="file" accept=".csv,text/csv" aria-label="上传线索 CSV" @change="uploadCandidates">
            <button class="ceo-upload-btn" type="button" title="上传线索 CSV" aria-label="上传线索 CSV" @click="uploadInput?.click()">+</button>
            <input v-model="query" type="text" aria-label="线索搜索条件" placeholder="输入要找的线索条件..." @keydown.enter="runSearch" />
            <button class="ceo-lead-send" type="button" :disabled="lead.searching || !query.trim()" @click="runSearch">{{ lead.searching ? '后台搜索中' : '查找' }}</button>
          </div>
        </div>
      </div>
    </section>

    <div v-if="detailLoading || selectedDetail" class="lead-detail-backdrop" @click.self="selectedDetail = null">
      <aside class="lead-detail-panel" aria-label="线索详情">
        <div class="lead-detail-head">
          <h2>{{ selectedDetail?.company_name || '加载线索详情...' }}</h2>
          <button type="button" aria-label="关闭线索详情" @click="selectedDetail = null">×</button>
        </div>
        <template v-if="selectedDetail">
          <dl>
            <div>
              <dt>官网</dt>
              <dd><a v-if="websiteHref(selectedDetail.website)" :href="websiteHref(selectedDetail.website)" target="_blank" rel="noopener noreferrer">{{ selectedDetail.website }}</a><span v-else>待补齐</span></dd>
            </div>
            <div><dt>区域</dt><dd>{{ regionLabel(selectedDetail.region_code) || '待确认' }}</dd></div>
            <div><dt>国家</dt><dd>{{ countryLabel(selectedDetail.country_code) || '待确认' }}</dd></div>
            <div><dt>行业</dt><dd>{{ selectedDetail.industry_code || '待确认' }}</dd></div>
            <div><dt>员工数</dt><dd>{{ selectedDetail.employee_count ?? '待补齐' }}</dd></div>
            <div><dt>ICP</dt><dd>{{ selectedDetail.icp_score?.total ?? '待评分' }}</dd></div>
          </dl>
          <section><h3>公司简介</h3><p>{{ selectedDetail.company_intro || '暂无简介' }}</p></section>
          <section><h3>联系人</h3><p v-if="!selectedDetailContacts.length">暂无联系人</p><p v-for="contact in selectedDetailContacts" :key="contactEmail(contact) || contactDisplayName(contact)">{{ contactDisplayName(contact) }} · {{ contactTitle(contact) || '职务待补齐' }} · {{ contactEmail(contact) || '邮箱待补齐' }}</p></section>
        </template>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.lead-collection-filter-bar { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)) auto; gap: 10px; align-items: end; padding: 12px 10px; border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); background: #f8fafc; }
.lead-collection-filter-bar label { display: flex; min-width: 0; flex-direction: column; gap: 5px; color: var(--text-muted); font-size: 11px; }
.lead-collection-filter-bar select { box-sizing: border-box; width: 100%; min-width: 0; min-height: 36px; padding: 6px 10px; color: var(--text-main); background: #fff; border: 1px solid var(--border); border-radius: 5px; font-size: 13px; cursor: pointer; }
.lead-collection-filter-bar select:focus { border-color: var(--blue); outline: 2px solid rgba(37, 99, 235, .12); outline-offset: 1px; }
.lead-collection-filter-bar .btn-xs { min-height: 36px; padding-inline: 14px; white-space: nowrap; }
.lead-collection-filter-status { display: flex; min-height: 34px; align-items: center; justify-content: space-between; gap: 12px; padding: 6px 10px; color: var(--text-muted); border-bottom: 1px solid var(--border); font-size: 11px; }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; }
.ceo-lead-quick-actions { padding: 8px 12px 0; }
.ceo-lead-quick-actions button { border: 1px solid #b9c9dc; border-radius: 6px; padding: 6px 10px; background: #fff; color: #25466e; cursor: pointer; }
.lead-search-progress { flex: 0 0 auto; padding: 12px; color: #1d3048; background: #fff; border: 1px solid #cddcf0; border-radius: 8px; box-shadow: 0 4px 14px rgba(37, 99, 235, .08); }
.lead-search-progress-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.lead-search-progress-title { display: flex; align-items: center; gap: 9px; min-width: 0; }
.lead-search-progress-title div { min-width: 0; }
.lead-search-progress-title strong { display: block; font-size: 12px; line-height: 1.4; }
.lead-search-progress-title span { display: block; margin-top: 2px; color: #65778d; font-size: 10px; line-height: 1.4; }
.lead-search-spinner { width: 16px; height: 16px; flex: 0 0 auto; border: 2px solid #d9e5f5; border-top-color: #2563eb; border-radius: 50%; animation: lead-search-spin .8s linear infinite; }
.lead-search-progress-head button { flex: 0 0 auto; padding: 4px 7px; color: #4b6078; cursor: pointer; background: transparent; border: 1px solid #cbd7e6; border-radius: 5px; font-size: 10px; }
.lead-search-progress-head button:disabled { cursor: wait; opacity: .55; }
.lead-search-progress-track { height: 6px; margin-top: 11px; overflow: hidden; background: #e7edf6; border-radius: 3px; }
.lead-search-progress-track span { display: block; height: 100%; background: #2563eb; border-radius: inherit; transition: width .35s ease; }
.lead-search-progress-detail { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-top: 7px; color: #52657a; font-size: 10px; }
.lead-search-progress-detail span { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.lead-search-progress-detail strong { color: #2563eb; }
.lead-search-progress p { margin: 8px 0 0; color: #738399; font-size: 10px; line-height: 1.5; }
@keyframes lead-search-spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .lead-search-spinner { animation: none; } }
@media (max-width: 900px) { .lead-collection-filter-bar { grid-template-columns: repeat(2, minmax(0, 1fr)); } .lead-collection-filter-bar .btn-xs { justify-self: start; } }
.ceo-lead-intro-preview { width: 100%; min-height: 32px; padding: 0; color: var(--text-secondary); text-align: left; background: transparent; border: 0; cursor: pointer; }
.ceo-lead-intro-preview span { display: -webkit-box; overflow: hidden; line-height: 16px; overflow-wrap: anywhere; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.ceo-lead-intro-preview:hover span { color: var(--text-main); text-decoration: underline; text-underline-offset: 2px; }
.ceo-lead-intro-preview:focus-visible { outline: 2px solid var(--blue); outline-offset: 2px; border-radius: 2px; }
.lead-detail-backdrop { position: fixed; inset: 0; z-index: 700; background: rgba(16, 31, 50, .38); }
.lead-detail-panel { position: absolute; top: 0; right: 0; width: min(520px, 92vw); height: 100%; box-sizing: border-box; overflow-y: auto; padding: 22px; background: #fff; box-shadow: -8px 0 24px rgba(15, 35, 60, .18); }
.lead-detail-head { display: flex; align-items: center; justify-content: space-between; gap: 16px; border-bottom: 1px solid #dbe4ef; }
.lead-detail-head h2 { font-size: 20px; }
.lead-detail-head button { width: 36px; height: 36px; border: 0; background: transparent; color: #52657a; font-size: 28px; cursor: pointer; }
.lead-detail-panel dl { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.lead-detail-panel dl div { padding: 10px; border: 1px solid #e0e7ef; border-radius: 6px; }
.lead-detail-panel dt { color: #6a7b90; font-size: 12px; }
.lead-detail-panel dd { margin: 4px 0 0; overflow-wrap: anywhere; color: #1d3048; }
.lead-detail-panel section { margin-top: 18px; }
.lead-detail-panel h3 { font-size: 14px; }
.lead-detail-panel p { color: #43556b; line-height: 1.6; }
</style>
