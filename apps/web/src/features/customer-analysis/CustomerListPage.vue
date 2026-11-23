<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { analysisApi } from '../../services/analysisApi'
import { toApiError } from '../../shared/api/client'

const router = useRouter()

interface CustomerRow {
  client_id: string
  name: string
  location: string
  company_type: string
  health_grade: string | null
  intention_level: string | null
  budget: string
  icp_score: number
  report_generated: boolean
}

const state = ref<'loading' | 'ready' | 'empty' | 'error'>('loading')
const error = ref('')
const customers = ref<CustomerRow[]>([])
const page = ref(1)
const pageSize = 20
const total = ref(0)

async function load() {
  state.value = 'loading'
  error.value = ''
  try {
    const result = await analysisApi.legacyAnalysisList(page.value, pageSize)
    customers.value = (result.items || []) as CustomerRow[]
    total.value = result.total as number
    state.value = customers.value.length ? 'ready' : 'empty'
  } catch (e) {
    error.value = toApiError(e).message
    state.value = 'error'
    customers.value = []
    total.value = 0
  }
}

function goDetail(clientId: string) {
  router.push({ name: 'customer-detail', params: { companyId: clientId } })
}

function prevPage() { if (page.value > 1) { page.value--; load() } }
function nextPage() { if (page.value * pageSize < total.value) { page.value++; load() } }

onMounted(load)
</script>

<template>
  <div class="customer-list">
    <header class="page-header">
      <h1>客户分析</h1>
      <span class="subtitle">共 {{ total }} 个客户</span>
    </header>

    <div v-if="state === 'loading'" class="loading">加载中…</div>
    <p v-if="error" class="error">{{ error }}</p>

    <template v-if="state === 'ready'">
      <table v-if="customers.length" class="customer-table">
        <thead>
          <tr>
            <th>公司名称</th>
            <th>区域</th>
            <th>行业</th>
            <th>健康度</th>
            <th>意向</th>
            <th>ICP 分数</th>
            <th>预算</th>
            <th>报告</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in customers" :key="row.client_id" @click="goDetail(row.client_id)" class="clickable">
            <td><strong>{{ row.name }}</strong></td>
            <td>{{ row.location }}</td>
            <td>{{ row.company_type }}</td>
            <td><span class="grade">{{ row.health_grade ?? '—' }}</span></td>
            <td>{{ row.intention_level ?? '—' }}</td>
            <td><span class="icp-score-number">{{ row.icp_score }}</span></td>
            <td>{{ row.budget }}</td>
            <td>{{ row.report_generated ? '✅' : '—' }}</td>
          </tr>
        </tbody>
      </table>

      <div v-else class="empty">
        <p>暂无客户分析数据</p>
        <p class="hint">通过线索搜索和候选入池后可在此查看客户分析。</p>
      </div>

      <div v-if="total > pageSize" class="pagination">
        <button :disabled="page <= 1" @click="prevPage">上一页</button>
        <span>{{ page }} / {{ Math.ceil(total / pageSize) }}</span>
        <button :disabled="page * pageSize >= total" @click="nextPage">下一页</button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.customer-list { max-width: 1100px; margin: 0 auto; padding: 24px 16px; }
.page-header { display: flex; align-items: baseline; gap: 12px; margin-bottom: 20px; }
.page-header h1 { margin: 0; }
.subtitle { color: #999; }
.customer-table { width: 100%; border-collapse: collapse; font-size: .9rem; }
.customer-table th { text-align: left; padding: 8px 12px; background: #fafafa; border-bottom: 2px solid #f0f0f0; color: #666; font-weight: 500; }
.customer-table td { padding: 10px 12px; border-bottom: 1px solid #f5f5f5; }
.clickable { cursor: pointer; }
.clickable:hover { background: #fafafa; }
.grade { font-weight: 600; }
.pagination { display: flex; justify-content: center; align-items: center; gap: 16px; margin-top: 24px; }
.pagination button { padding: 4px 16px; border: 1px solid #d9d9d9; border-radius: 4px; background: #fff; cursor: pointer; }
.pagination button:disabled { opacity: .4; cursor: default; }
.loading, .empty { text-align: center; padding: 48px 0; color: #666; }
.empty .hint { font-size: .85rem; color: #bbb; }
.error { color: #ff4d4f; }
</style>
