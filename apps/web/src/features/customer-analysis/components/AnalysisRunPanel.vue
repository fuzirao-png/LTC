<script setup lang="ts">
import { ref } from 'vue'
import { analysisApi, type AnalysisRun } from '../../../services/analysisApi'
import { openJobEvents } from '../../../shared/api/sse'
import { jobStatusLabel } from '../../../shared/utils/labels'

const props = defineProps<{
  companyId: string
  activeRun: AnalysisRun | null
}>()
const emit = defineEmits<{
  'run-created': [run: AnalysisRun]
  'status-changed': [run: AnalysisRun | null]
}>()

const creating = ref(false)
const polling = ref<ReturnType<typeof setInterval> | null>(null)
const error = ref('')
const pollingRunId = ref<string | null>(null)

async function createRun() {
  creating.value = true
  error.value = ''
  try {
    const result = await analysisApi.createAnalysisRun(props.companyId, { trigger_type: 'manual' })
    // fetch the actual run
    const run = await analysisApi.getAnalysisRun(result.resource_id)
    emit('run-created', run.data)
    // start SSE for progress
    startPolling(run.data.run_id, result.job.job_id)
  } catch (e: any) {
    error.value = e?.response?.data?.error?.message || '创建分析任务失败'
  } finally {
    creating.value = false
  }
}

function startPolling(runId: string, jobId: string) {
  // SSE primary
  const es = openJobEvents(jobId, (event) => {
    try {
      const payload = JSON.parse(event.data)
      if (payload.type === 'completed' || payload.type === 'error') {
        es.close()
        stopPolling()
        refreshRun(runId)
      }
    } catch { /* ignore parse errors */ }
  })
  es.onerror = () => { es.close(); stopPolling() }

  // polling fallback every 10s
  polling.value = setInterval(() => refreshRun(runId), 10_000)
  pollingRunId.value = runId
}

function stopPolling() {
  if (polling.value) { clearInterval(polling.value); polling.value = null }
  pollingRunId.value = null
}

async function refreshRun(runId: string) {
  try {
    const { data } = await analysisApi.getAnalysisRun(runId)
    emit('status-changed', data)
    if (data.status === 'completed' || data.status === 'failed' || data.status === 'cancelled') {
      stopPolling()
    }
  } catch { stopPolling() }
}

async function retryRun() {
  if (!props.activeRun) return
  try {
    const result = await analysisApi.retryAnalysisRun(props.activeRun.run_id, props.activeRun.version)
    const { data } = await analysisApi.getAnalysisRun(result.resource_id)
    emit('status-changed', data)
    startPolling(data.run_id, result.job.job_id)
  } catch (e: any) {
    error.value = e?.response?.data?.error?.code === 'VERSION_CONFLICT'
      ? '数据已被更新，请刷新页面后重试。'
      : (e?.response?.data?.error?.message || '重试失败')
  }
}

async function cancelRun() {
  if (!props.activeRun) return
  try {
    await analysisApi.cancelAnalysisRun(props.activeRun.run_id, props.activeRun.version)
    const { data } = await analysisApi.getAnalysisRun(props.activeRun.run_id)
    emit('status-changed', data)
    stopPolling()
  } catch (e: any) {
    error.value = e?.response?.data?.error?.code === 'VERSION_CONFLICT'
      ? '数据已被更新，请刷新页面后重试。'
      : (e?.response?.data?.error?.message || '取消失败')
  }
}
</script>

<template>
  <div class="run-panel">
    <div class="run-actions">
      <button @click="createRun" :disabled="creating" class="btn-primary">
        {{ creating ? '创建中…' : '生成分析报告' }}
      </button>
      <button
        v-if="activeRun && activeRun.status === 'failed'"
        @click="retryRun"
        class="btn-secondary"
      >重试</button>
      <button
        v-if="activeRun && (activeRun.status === 'queued' || activeRun.status === 'running')"
        @click="cancelRun"
        class="btn-danger"
      >取消</button>
    </div>

    <div v-if="error" class="run-error">{{ error }}</div>

    <div v-if="activeRun" class="run-status">
      <span class="status-label" :class="activeRun.status">{{ jobStatusLabel(activeRun.status) }}</span>
      <code class="run-id">run {{ activeRun.run_id.slice(0,8) }}</code>
      <span v-if="activeRun.error_message" class="run-error-msg">{{ activeRun.error_message }}</span>
    </div>
  </div>
</template>

<style scoped>
.run-panel { margin-bottom: 16px; }
.run-actions { display: flex; gap: 8px; }
.run-actions button { padding: 6px 20px; border: none; border-radius: 4px; cursor: pointer; font-size: .9rem; }
.btn-primary { background: #1890ff; color: #fff; }
.btn-primary:disabled { opacity: .6; }
.btn-secondary { background: #fa8c16; color: #fff; }
.btn-danger { background: #ff4d4f; color: #fff; }
.run-error { color: #ff4d4f; font-size: .85rem; margin-top: 8px; }
.run-status { margin-top: 8px; display: flex; align-items: center; gap: 8px; font-size: .85rem; }
.status-label { padding: 2px 10px; border-radius: 10px; background: #f5f5f5; }
.status-label.running { background: #e6f7ff; color: #1890ff; }
.status-label.completed { background: #f6ffed; color: #52c41a; }
.status-label.failed { background: #fff2f0; color: #ff4d4f; }
.status-label.cancelled { background: #fafafa; color: #999; }
.run-id { font-size: .8rem; color: #bbb; }
.run-error-msg { color: #ff4d4f; }
</style>
