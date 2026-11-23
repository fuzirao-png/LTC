<script setup lang="ts">
defineProps<{
  value: unknown
  depth?: number
}>()

const FIELD_LABELS: Record<string, string> = {
  facts: '事实',
  inferences: '分析判断',
  unknowns: '待确认信息',
  sales_recommendations: '销售建议',
  recommendations: '建议',
  action: '建议行动',
  reason: '原因',
  text: '内容',
  item: '事项',
  evidence_ids: '证据编号',
  next_action: '下一步行动',
  target_customer: '目标客户',
  value_proposition: '价值主张',
  competitive_advantage: '竞争优势',
  risks: '风险',
  opportunities: '机会',
  strengths: '优势',
  weaknesses: '短板',
  summary: '摘要',
};

const isRecord = (value: unknown): value is Record<string, unknown> => (
  typeof value === 'object' && value !== null && !Array.isArray(value)
);

const isEmpty = (value: unknown) => (
  value === null
  || value === undefined
  || value === ''
  || (Array.isArray(value) && value.length === 0)
  || (isRecord(value) && Object.keys(value).length === 0)
);

const fieldLabel = (key: string) => FIELD_LABELS[key]
  || key.replace(/_/g, ' ').replace(/\b\w/g, (letter: string) => letter.toUpperCase());

const displayValue = (value: unknown) => {
  if (typeof value === 'boolean') return value ? '是' : '否';
  return String(value);
};
</script>

<template>
  <p v-if="isEmpty(value)" class="report-empty">暂无内容</p>

  <ul v-else-if="Array.isArray(value)" class="report-list">
    <li v-for="(item, index) in value" :key="index">
      <ReportValue v-if="typeof item === 'object' && item !== null" :value="item" :depth="(depth || 0) + 1" />
      <span v-else>{{ displayValue(item) }}</span>
    </li>
  </ul>

  <dl v-else-if="isRecord(value)" class="report-fields">
    <template v-for="(fieldValue, key) in value" :key="key">
      <div v-if="!isEmpty(fieldValue)" class="report-field">
        <dt>{{ fieldLabel(String(key)) }}</dt>
        <dd>
          <ReportValue
            v-if="typeof fieldValue === 'object' && fieldValue !== null"
            :value="fieldValue"
            :depth="(depth || 0) + 1"
          />
          <span v-else>{{ displayValue(fieldValue) }}</span>
        </dd>
      </div>
    </template>
  </dl>

  <p v-else class="report-copy">{{ displayValue(value) }}</p>
</template>

<style scoped>
.report-empty,
.report-copy {
  margin: 0;
  color: #667085;
  line-height: 1.65;
}

.report-list {
  display: grid;
  gap: 8px;
  padding-left: 20px;
  margin: 0;
}

.report-list > li {
  padding-left: 2px;
  color: #344054;
  line-height: 1.65;
}

.report-fields {
  display: grid;
  gap: 0;
  margin: 0;
}

.report-field {
  display: grid;
  grid-template-columns: minmax(110px, 28%) minmax(0, 1fr);
  gap: 16px;
  padding: 10px 0;
  border-top: 1px solid #eaecf0;
}

.report-field:first-child {
  padding-top: 0;
  border-top: 0;
}

.report-field dt {
  color: #475467;
  font-size: 12px;
  font-weight: 700;
}

.report-field dd {
  min-width: 0;
  margin: 0;
  color: #101828;
  overflow-wrap: anywhere;
}

.report-field .report-field {
  grid-template-columns: minmax(90px, 30%) minmax(0, 1fr);
}

@media (max-width: 640px) {
  .report-field,
  .report-field .report-field {
    grid-template-columns: 1fr;
    gap: 5px;
  }
}
</style>
