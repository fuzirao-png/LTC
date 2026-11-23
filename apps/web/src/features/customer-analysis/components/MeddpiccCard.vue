<script setup lang="ts">
import { ref } from 'vue'
import { analysisApi, type MeddpiccDimension } from '../../../services/analysisApi'
import { validationStatusLabel } from '../../../shared/utils/labels'

const props = defineProps<{
  dimensions: MeddpiccDimension[]
  companyId: string
}>()
const emit = defineEmits<{ updated: [dimCode: string, dim: MeddpiccDimension] }>()

const editingCode = ref<string | null>(null)
const saving = ref(false)
const form = ref({ status: 'unknown' as string, summary: '' })
const error = ref('')

const MEDDPICC_LABELS: Record<string, string> = {
  metrics: '量化指标', economic_buyer: '经济决策人', decision_criteria: '决策标准',
  decision_process: '决策流程', paper_process: '审批流程', identify_pain: '痛点识别',
  champion: '支持者', competition: '竞争情况',
}

const STATUS_LABELS: Record<string, string> = {
  unknown: '未知', partial: '部分确认', confirmed: '已确认', rejected: '已排除',
}

function startEdit(dim: MeddpiccDimension) {
  editingCode.value = dim.dimension_code
  form.value = { status: dim.status, summary: dim.summary ?? '' }
  error.value = ''
}

function cancelEdit() { editingCode.value = null }

async function save(dim: MeddpiccDimension) {
  saving.value = true
  error.value = ''
  try {
    const res = await analysisApi.updateMeddpicc(
      props.companyId, dim.dimension_code,
      { status: form.value.status, summary: form.value.summary },
      dim.version,
    )
    const updated = res.dimensions.find(d => d.dimension_code === dim.dimension_code)
    if (updated) emit('updated', dim.dimension_code, updated)
    editingCode.value = null
  } catch (e: any) {
    const code = e?.response?.data?.error?.code
    if (code === 'VERSION_CONFLICT') {
      error.value = '数据已被其他操作更新，请刷新页面后重试。'
    } else {
      error.value = e?.response?.data?.error?.message || '保存失败'
    }
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="meddpicc-card">
    <h3>MEDDPICC</h3>
    <div v-if="!dimensions.length" class="empty">暂无 MEDDPICC 数据</div>
    <div v-for="dim in dimensions" :key="dim.dimension_code" class="dim-row">
      <div class="dim-meta">
        <strong>{{ MEDDPICC_LABELS[dim.dimension_code] ?? dim.dimension_code }}</strong>
        <span class="status-tag" :class="dim.status">{{ STATUS_LABELS[dim.status] ?? ((dim.status && validationStatusLabel(dim.status) !== '未知') ? validationStatusLabel(dim.status) : dim.status) }}</span>
        <span v-if="dim.level" class="level">L{{ dim.level }}</span>
      </div>
      <p v-if="dim.summary && editingCode !== dim.dimension_code" class="dim-summary">{{ dim.summary }}</p>

      <!-- inline edit -->
      <div v-if="editingCode === dim.dimension_code" class="inline-edit">
        <select v-model="form.status">
          <option v-for="(label, val) in STATUS_LABELS" :key="val" :value="val">{{ label }}</option>
        </select>
        <textarea v-model="form.summary" rows="2" placeholder="摘要…" />
        <p v-if="error" class="form-error">{{ error }}</p>
        <div class="form-actions">
          <button @click="save(dim)" :disabled="saving">{{ saving ? '保存中…' : '保存' }}</button>
          <button @click="cancelEdit" class="btn-cancel">取消</button>
        </div>
      </div>

      <button v-else @click="startEdit(dim)" class="btn-edit">编辑</button>
      <footer class="dim-footer">v{{ dim.version }}</footer>
    </div>
  </div>
</template>

<style scoped>
.meddpicc-card h3 { margin-top: 0; }
.dim-row { border: 1px solid #f0f0f0; border-radius: 6px; padding: 12px; margin-bottom: 8px; }
.dim-meta { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.status-tag { font-size: .75rem; padding: 1px 8px; border-radius: 10px; background: #f5f5f5; }
.status-tag.confirmed { background: #f6ffed; color: #52c41a; }
.status-tag.partial { background: #fff7e6; color: #fa8c16; }
.status-tag.rejected { background: #fff2f0; color: #ff4d4f; }
.level { font-size: .75rem; color: #999; }
.dim-summary { margin: 0 0 8px 0; color: #555; font-size: .9rem; }
.inline-edit { display: flex; flex-direction: column; gap: 8px; margin-top: 8px; }
.inline-edit select, .inline-edit textarea { padding: 4px 8px; border: 1px solid #d9d9d9; border-radius: 4px; }
.form-error { color: #ff4d4f; font-size: .85rem; margin: 0; }
.form-actions { display: flex; gap: 8px; }
.form-actions button { padding: 4px 16px; border: none; border-radius: 4px; cursor: pointer; background: #1890ff; color: #fff; }
.btn-cancel { background: #f5f5f5 !important; color: #333 !important; }
.btn-edit { background: none; border: 1px solid #d9d9d9; border-radius: 4px; padding: 2px 10px; cursor: pointer; font-size: .8rem; margin-top: 4px; }
.dim-footer { font-size: .7rem; color: #ccc; margin-top: 6px; }
.empty { color: #999; padding: 24px 0; }
</style>
