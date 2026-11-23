<script setup lang="ts">
import { ref, watch } from 'vue'
import { analysisApi, type CustomerProfile } from '../../../services/analysisApi'

const props = defineProps<{
  profile: CustomerProfile | null
  companyId: string
  etag: string
}>()
const emit = defineEmits<{ updated: [profile: CustomerProfile, etag?: string] }>()

const editing = ref(false)
const saving = ref(false)
const form = ref({ company_summary: '', business_model: '', geography_note: '' })
const error = ref('')

function startEdit() {
  if (!props.profile) return
  form.value = {
    company_summary: props.profile.company_type ?? '',
    business_model: props.profile.business_model ?? '',
    geography_note: props.profile.region_text ?? '',
  }
  editing.value = true
  error.value = ''
}

function cancelEdit() { editing.value = false }

async function save() {
  if (!props.profile) return
  saving.value = true
  error.value = ''
  try {
    const { data: updated, etag } = await analysisApi.updateProfile(props.companyId, form.value, props.profile.profile_version)
    emit('updated', updated, etag)
    editing.value = false
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

function fieldLabel(key: string): string {
  const labels: Record<string, string> = {
    company_type: '公司类型', region_text: '区域', employee_scale: '规模',
    business_model: '商业模式', esim_scenario: 'eSIM 场景', coverage: '覆盖范围',
    estimated_usage: '预估用量', integration: '技术对接', compliance: '合规',
    budget_text: '预算', decision_maker_text: '关键决策人', decision_cycle_text: '决策周期',
    source_summary: '来源摘要',
  }
  return labels[key] ?? key
}

function fieldValue(key: string): string {
  const val = (props.profile as any)?.[key]
  return val || '—'
}
</script>

<template>
  <div class="profile-card">
    <div class="card-header">
      <h3>客户画像</h3>
      <button v-if="!editing" @click="startEdit" class="btn-edit">编辑</button>
    </div>

    <div v-if="!profile" class="empty">暂无画像数据</div>

    <!-- read view -->
    <dl v-else-if="!editing" class="profile-grid">
      <div v-for="key in ['company_type','region_text','employee_scale','business_model','esim_scenario','coverage','estimated_usage','integration','compliance','budget_text','decision_maker_text','decision_cycle_text','source_summary']" :key="key" class="field">
        <dt>{{ fieldLabel(key) }}</dt>
        <dd>{{ fieldValue(key) }}</dd>
      </div>
    </dl>

    <!-- edit view -->
    <form v-else @submit.prevent="save" class="edit-form">
      <label>公司类型 <input v-model="form.company_summary" /></label>
      <label>商业模式 <input v-model="form.business_model" /></label>
      <label>区域 <input v-model="form.geography_note" /></label>
      <p v-if="error" class="form-error">{{ error }}</p>
      <div class="form-actions">
        <button type="submit" :disabled="saving">{{ saving ? '保存中…' : '保存' }}</button>
        <button type="button" @click="cancelEdit" class="btn-cancel">取消</button>
      </div>
    </form>

    <footer v-if="profile" class="card-footer">
      <span>版本 {{ profile.profile_version }}</span>
      <span v-if="profile.updated_at">更新于 {{ new Date(profile.updated_at).toLocaleString('zh-CN') }}</span>
    </footer>
  </div>
</template>

<style scoped>
.profile-card {  }
.card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.card-header h3 { margin: 0; }
.btn-edit { padding: 4px 16px; border: 1px solid #1890ff; color: #1890ff; background: #fff; border-radius: 4px; cursor: pointer; }
.profile-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 24px; }
.field { margin: 0; }
.field dt { font-size: .8rem; color: #999; }
.field dd { margin: 0 0 8px 0; }
.edit-form { display: flex; flex-direction: column; gap: 12px; max-width: 480px; }
.edit-form label { display: flex; flex-direction: column; font-size: .85rem; color: #666; gap: 4px; }
.edit-form input { padding: 6px 10px; border: 1px solid #d9d9d9; border-radius: 4px; }
.form-error { color: #ff4d4f; font-size: .85rem; }
.form-actions { display: flex; gap: 8px; }
.form-actions button { padding: 6px 20px; border: none; border-radius: 4px; cursor: pointer; }
.form-actions button[type="submit"] { background: #1890ff; color: #fff; }
.btn-cancel { background: #f5f5f5; }
.card-footer { margin-top: 16px; font-size: .75rem; color: #bbb; display: flex; gap: 16px; }
.empty { color: #999; padding: 24px 0; }
</style>
