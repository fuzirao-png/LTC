<script setup lang="ts">
import { analysisApi, type AnalysisSuggestion } from '../../../services/analysisApi'

defineProps<{ suggestions: AnalysisSuggestion[] }>()
const emit = defineEmits<{ review: [suggestionId: string, accepted: boolean] }>()

async function accept(s: AnalysisSuggestion) {
  try { await analysisApi.acceptSuggestion(s.suggestion_id, s.version); emit('review', s.suggestion_id, true) }
  catch (e: any) { alert(e?.response?.data?.error?.code === 'VERSION_CONFLICT' ? '数据已被更新，请刷新后重试。' : '接受建议失败') }
}
async function reject(s: AnalysisSuggestion) {
  try { await analysisApi.rejectSuggestion(s.suggestion_id, s.version); emit('review', s.suggestion_id, false) }
  catch (e: any) { alert(e?.response?.data?.error?.code === 'VERSION_CONFLICT' ? '数据已被更新，请刷新后重试。' : '拒绝建议失败') }
}

function fmtVal(v: unknown): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}
</script>

<template>
  <div class="suggestion-list">
    <h3>分析建议</h3>
    <div v-if="!suggestions.length" class="empty">暂无建议</div>
    <div v-for="s in suggestions" :key="s.suggestion_id" class="suggestion-row" :class="s.status">
      <div class="sg-header">
        <strong>{{ s.summary }}</strong>
        <span class="sg-type">{{ s.target_type }} / {{ s.target_path }}</span>
      </div>
      <div class="sg-change">
        <div class="old-val"><small>当前值</small> {{ fmtVal(s.current_value_snapshot) }}</div>
        <div class="arrow">→</div>
        <div class="new-val"><small>建议值</small> {{ fmtVal(s.proposed_value) }}</div>
      </div>
      <div v-if="s.confidence !== null" class="sg-conf">置信度 {{ Math.round(s.confidence * 100) }}%</div>

      <div v-if="s.status === 'pending'" class="sg-actions">
        <button @click="accept(s)" class="btn-accept">采纳</button>
        <button @click="reject(s)" class="btn-reject">拒绝</button>
      </div>
      <div v-else class="sg-reviewed">{{ s.status === 'accepted' ? '已采纳' : '已拒绝' }}</div>
    </div>
  </div>
</template>

<style scoped>
.suggestion-list h3 { margin-top: 0; }
.suggestion-row { border: 1px solid #f0f0f0; border-radius: 6px; padding: 12px; margin-bottom: 8px; }
.suggestion-row.accepted { opacity: .7; background: #f6ffed; }
.suggestion-row.rejected { opacity: .6; background: #fafafa; }
.sg-header { display: flex; justify-content: space-between; margin-bottom: 8px; }
.sg-type { font-size: .8rem; color: #999; }
.sg-change { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.old-val, .new-val { font-size: .9rem; }
.old-val small, .new-val small { display: block; color: #999; }
.new-val { color: #1890ff; font-weight: 600; }
.arrow { color: #ccc; }
.sg-conf { font-size: .8rem; color: #999; margin-bottom: 8px; }
.sg-actions { display: flex; gap: 8px; }
.sg-actions button { padding: 4px 16px; border: none; border-radius: 4px; cursor: pointer; }
.btn-accept { background: #52c41a; color: #fff; }
.btn-reject { background: #ff4d4f; color: #fff; }
.sg-reviewed { font-size: .85rem; color: #999; }
.empty { color: #999; padding: 24px 0; }
</style>
