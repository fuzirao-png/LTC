<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { analysisApi, type AnalysisReport, type CustomerProfile, type MeddpiccDimension, type AnalysisSuggestion, type AnalysisRun } from '../../services/analysisApi'
import ProfileCard from './components/ProfileCard.vue'
import MeddpiccCard from './components/MeddpiccCard.vue'
import ReportCard from './components/ReportCard.vue'
import SuggestionList from './components/SuggestionList.vue'
import AnalysisRunPanel from './components/AnalysisRunPanel.vue'

const route = useRoute()
const router = useRouter()
const companyId = route.params.companyId as string

type LoadState = 'loading' | 'ready' | 'empty' | 'error' | 'conflict'

const state = ref<LoadState>('loading')
const errorMessage = ref('')
const conflictMessage = ref('')
const activeTab = ref<'profile' | 'meddpicc' | 'report' | 'suggestions'>('profile')

const profile = ref<CustomerProfile | null>(null)
const profileEtag = ref('')
const meddpicc = ref<MeddpiccDimension[]>([])
const currentReport = ref<AnalysisReport | null>(null)
const suggestions = ref<AnalysisSuggestion[]>([])
const activeRun = ref<AnalysisRun | null>(null)

async function loadAll() {
  state.value = 'loading'
  errorMessage.value = ''
  let failures = 0
  // Load individually so we can show partial data even if some calls fail
  try {
    const p = await analysisApi.getProfile(companyId)
    profile.value = p.data; profileEtag.value = p.etag
  } catch { failures++ }
  try {
    const m = await analysisApi.getMeddpicc(companyId)
    meddpicc.value = m.dimensions
  } catch { failures++ }
  try {
    currentReport.value = await analysisApi.getCurrentReport(companyId)
  } catch { failures++ }
  try {
    const s = await analysisApi.listSuggestions(companyId)
    suggestions.value = Array.isArray(s) ? s : []
  } catch { failures++ }
  const hasAnyData = profile.value || meddpicc.value.length > 0 || currentReport.value || suggestions.value.length > 0
  if (failures >= 4) {
    errorMessage.value = '加载客户分析数据失败'
    state.value = 'error'
  } else if (!hasAnyData) {
    state.value = 'empty'
  } else {
    state.value = 'ready'
  }
}

async function onProfileUpdated(updated: CustomerProfile, etag?: string) {
  profile.value = updated
  profileEtag.value = etag || `"${updated.profile_version}"`
}

async function onMeddpiccUpdated(dimCode: string, updated: MeddpiccDimension) {
  const idx = meddpicc.value.findIndex(d => d.dimension_code === dimCode)
  if (idx >= 0) meddpicc.value[idx] = updated
}

async function onRunCreated(run: AnalysisRun) {
  activeRun.value = run
}

async function onRunStatusChanged(run: AnalysisRun | null) {
  activeRun.value = run
  if (run && (run.status === 'completed' || run.status === 'failed')) {
    // refresh report
    try { currentReport.value = await analysisApi.getCurrentReport(companyId) } catch { /* ignore */ }
  }
}

async function onSuggestionReview(suggestionId: string, accepted: boolean) {
  suggestions.value = suggestions.value.filter(s => s.suggestion_id !== suggestionId)
  // refresh profile after accepting
  if (accepted) {
    try {
      const p = await analysisApi.getProfile(companyId)
      profile.value = p.data; profileEtag.value = p.etag
    } catch { /* ignore */ }
  }
}

onMounted(loadAll)
</script>

<template>
  <div class="customer-detail">
    <header class="page-header">
      <button class="back-btn" @click="router.push({ name: 'customer-list' })">← 返回列表</button>
      <h1>{{ profile?.company_type || '客户详情' }}</h1>
      <span v-if="profile?.completeness_score" class="completeness">
        信息完整度 {{ Math.round(profile.completeness_score * 100) }}%
      </span>
    </header>

    <div v-if="state === 'loading'" class="loading">加载中…</div>
    <div v-else-if="state === 'error'" class="error">
      <p>{{ errorMessage }}</p>
      <button @click="loadAll">重试</button>
    </div>
    <div v-else-if="state === 'conflict'" class="error">
      <p>{{ conflictMessage || '数据已被其他操作更新，请刷新页面。' }}</p>
      <button @click="loadAll">刷新</button>
    </div>
    <div v-else-if="state === 'empty'" class="empty-hint">暂无客户分析数据。</div>

    <template v-else>
      <!-- tab bar -->
      <nav class="tabs">
        <button :class="{ active: activeTab === 'profile' }" @click="activeTab = 'profile'">客户画像</button>
        <button :class="{ active: activeTab === 'meddpicc' }" @click="activeTab = 'meddpicc'">MEDDPICC</button>
        <button :class="{ active: activeTab === 'report' }" @click="activeTab = 'report'">
          分析报告
          <span v-if="activeRun && activeRun.status === 'running'" class="badge running">生成中</span>
        </button>
        <button :class="{ active: activeTab === 'suggestions' }" @click="activeTab = 'suggestions'">
          建议
          <span v-if="suggestions.filter(s=>s.status==='pending').length" class="badge">
            {{ suggestions.filter(s => s.status === 'pending').length }}
          </span>
        </button>
      </nav>

      <!-- tab content -->
      <section class="tab-content">
        <ProfileCard
          v-if="activeTab === 'profile'"
          :profile="profile"
          :company-id="companyId"
          :etag="profileEtag"
          @updated="onProfileUpdated"
        />
        <MeddpiccCard
          v-if="activeTab === 'meddpicc'"
          :dimensions="meddpicc"
          :company-id="companyId"
          @updated="onMeddpiccUpdated"
        />
        <template v-if="activeTab === 'report'">
          <AnalysisRunPanel
            :company-id="companyId"
            :active-run="activeRun"
            @run-created="onRunCreated"
            @status-changed="onRunStatusChanged"
          />
          <ReportCard
            v-if="currentReport"
            :report="currentReport"
          />
          <p v-else class="empty-hint">暂无分析报告，点击上方按钮生成。</p>
        </template>
        <SuggestionList
          v-if="activeTab === 'suggestions'"
          :suggestions="suggestions"
          @review="onSuggestionReview"
        />
      </section>
    </template>
  </div>
</template>

<style scoped>
.customer-detail { max-width: 960px; margin: 0 auto; padding: 24px 16px; }
.page-header { display: flex; align-items: baseline; gap: 16px; margin-bottom: 20px; }
.page-header h1 { margin: 0; font-size: 1.5rem; }
.back-btn { background: none; border: 1px solid #ccc; border-radius: 6px; padding: 4px 12px; cursor: pointer; }
.completeness { font-size: .85rem; color: #666; }
.tabs { display: flex; gap: 4px; margin-bottom: 20px; border-bottom: 1px solid #e0e0e0; }
.tabs button { padding: 8px 20px; border: none; background: none; cursor: pointer; border-radius: 8px 8px 0 0; position: relative; }
.tabs button.active { background: #fff; border: 1px solid #e0e0e0; border-bottom-color: #fff; margin-bottom: -1px; font-weight: 600; }
.badge { background: #e6f7ff; color: #1890ff; padding: 1px 6px; border-radius: 10px; font-size: .75rem; margin-left: 4px; }
.badge.running { background: #fff7e6; color: #fa8c16; }
.tab-content { background: #fff; border-radius: 0 8px 8px 8px; padding: 20px; min-height: 300px; }
.loading, .error { text-align: center; padding: 48px 0; color: #666; }
.empty-hint { color: #999; text-align: center; padding: 32px 0; }
</style>
