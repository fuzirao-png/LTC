<script setup lang="ts">
import type { AnalysisReport } from '../../../services/analysisApi'

defineProps<{ report: AnalysisReport }>()

const MODULE_LABELS: Record<string, string> = {
  market: '市场分析', company: '公司分析', competitor: '竞品分析',
  pain: '痛点分析', product: '产品建议',
}
</script>

<template>
  <div class="report-card">
    <div class="report-header">
      <h3>分析报告</h3>
      <div class="badges">
        <span v-if="report.health_grade" class="badge health">健康度 {{ report.health_grade }}</span>
        <span v-if="report.intention_level" class="badge intent">意向 {{ report.intention_level }}</span>
        <span v-if="report.confidence !== null" class="badge conf">置信度 {{ Math.round(report.confidence * 100) }}%</span>
      </div>
    </div>

    <p class="report-summary">{{ report.summary }}</p>

    <!-- 5 modules -->
    <div class="modules">
      <details v-for="mod in report.modules" :key="mod.module_name" class="module-section">
        <summary>{{ MODULE_LABELS[mod.module_name] ?? mod.module_name }}</summary>
        <div v-if="(report as any)[mod.module_name]" class="module-body">
          <pre class="module-json">{{ JSON.stringify((report as any)[mod.module_name], null, 2) }}</pre>
        </div>
        <p v-else class="empty-section">暂无内容</p>
      </details>
    </div>

    <!-- sales guide -->
    <details v-if="report.sales_guide && Object.keys(report.sales_guide).length" class="module-section">
      <summary>销售指南</summary>
      <pre class="module-json">{{ JSON.stringify(report.sales_guide, null, 2) }}</pre>
    </details>

    <!-- low confidence warnings -->
    <div v-if="report.low_confidence_sections.length" class="low-conf">
      <p>⚠ 低置信度段落：{{ report.low_confidence_sections.join('、') }}</p>
    </div>

    <footer class="report-footer">
      <span>v{{ report.version_no }} · {{ report.generated_by }}</span>
      <span>{{ new Date(report.generated_at).toLocaleString('zh-CN') }}</span>
    </footer>
  </div>
</template>

<style scoped>
.report-card { margin-top: 20px; }
.report-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.report-header h3 { margin: 0; }
.badges { display: flex; gap: 6px; }
.badge { font-size: .8rem; padding: 2px 10px; border-radius: 10px; }
.badge.health { background: #f6ffed; color: #52c41a; }
.badge.intent { background: #e6f7ff; color: #1890ff; }
.badge.conf { background: #f5f5f5; color: #666; }
.report-summary { line-height: 1.6; color: #333; margin-bottom: 16px; }
.modules { display: flex; flex-direction: column; gap: 8px; }
.module-section { border: 1px solid #f0f0f0; border-radius: 6px; padding: 8px 12px; }
.module-section summary { cursor: pointer; font-weight: 500; }
.module-body { margin-top: 8px; }
.module-json { font-size: .8rem; background: #fafafa; padding: 12px; border-radius: 4px; overflow-x: auto; max-height: 300px; }
.empty-section { color: #999; font-size: .85rem; }
.low-conf { margin-top: 12px; padding: 8px; background: #fff7e6; border-radius: 4px; color: #ad6800; font-size: .85rem; }
.report-footer { margin-top: 16px; font-size: .75rem; color: #bbb; display: flex; gap: 16px; }
</style>
