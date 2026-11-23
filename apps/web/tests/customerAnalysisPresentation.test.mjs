import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const component = readFileSync(new URL('../src/features/customer-analysis/CustomerAnalysis.vue', import.meta.url), 'utf8');
const analysisApi = readFileSync(new URL('../src/services/analysisApi.ts', import.meta.url), 'utf8');
const operationComponent = readFileSync(new URL('../src/features/customer-operation/CustomerOperation.vue', import.meta.url), 'utf8');
const fieldCatalog = readFileSync(new URL('../../api/src/ltc/modules/customer_analysis/domain/field_catalog.py', import.meta.url), 'utf8');
const css = readFileSync(new URL('../src/style.css', import.meta.url), 'utf8');
const labels = readFileSync(new URL('../src/shared/utils/labels.ts', import.meta.url), 'utf8');

assert.match(css, /--font-sans:\s*-apple-system/);
assert.match(css, /font-family:\s*var\(--font-sans\)/);

assert.match(component, /function polishReportCopy\(value: string\)/);
assert.match(component, /Object\.entries\(value as Record<string, unknown>\)/);
assert.doesNotMatch(component, /function renderText[^\n]+JSON\.stringify/);
assert.match(component, /internalEvidenceFieldKeys = new Set\(\['evidence', 'evidence_id', 'evidence_ids', 'evidence_refs'\]\)/);
assert.match(component, /cleanReportText\(polishReportCopy\(textOrDash\(value\)\)\)/);
assert.match(component, /shouldRenderReportField\(key, item\)/);
assert.doesNotMatch(component, /展开原始数据|showRawDebug|JSON\.stringify\(selectedCustomer\.analysis_report\._raw/);
assert.doesNotMatch(component, /（可手动填写 \/ AI转录识别）/);
assert.match(component, /支持手动填写和 AI 转录识别/);

assert.match(component, /class="analysis-card-identity"/);
assert.doesNotMatch(component, /class="analysis-card-state"/);
assert.match(component, /class="analysis-card-location-row"/);
assert.match(component, /\{\{ customerLocation\(customer\) \}\}[\s\S]*?\{\{ displayName\(customer\) \}\}[\s\S]*?\{\{ customerTime\(customer\) \}\}/);
assert.match(component, /countryCardLabel/);
assert.doesNotMatch(component, /cityLabel\(city\)/);
assert.doesNotMatch(component, /legacy-page-title[\s\S]{0,180}regionalTimeLabel/);
assert.match(component, /resolveCustomerClock\(item\)/);
assert.match(component, /时间待确认/);
assert.doesNotMatch(component, /regionalClockConfig/);
assert.doesNotMatch(component, /cityNameFor\(item\.city\)/);
assert.match(component, /return countryCardLabel\(item\.country\)/);
assert.match(labels, /BERLIN:\s*'柏林'/);
assert.match(labels, /MAIDSTONE:\s*'梅德斯通'/);
assert.match(labels, /ES:\s*'西班牙'/);
assert.match(component, /\.profile-structure-grid \{[\s\S]*?grid-template-columns:\s*repeat\(2, minmax\(0, 1fr\)\)/);
assert.match(component, /profile-structure-panel customer-view-panel[\s\S]*?profile-structure-panel latest-news-panel/);

assert.match(component, /const MISSING_REPORT_INFO = '信息缺失，需要销售进行跟进补齐'/);
assert.match(component, /真实 AI 分析尚未生成/);
assert.match(component, /class="analysis-source-warning" role="alert"/);
assert.match(component, /sanitizeCustomerName/);
assert.match(component, /const narrativeReportDefinitions:[\s\S]*?市场分析[\s\S]*?公司分析[\s\S]*?竞争分析[\s\S]*?需求痛点[\s\S]*?产品建议/);
const canonicalCoreFields = [
  'company_type', 'business_model', 'employee_scale', 'region_text',
  'esim_scenario', 'coverage', 'estimated_usage', 'integration', 'compliance',
  'budget_text', 'decision_maker_text', 'decision_maker_contact_id', 'decision_cycle_text',
  'metrics', 'economic_buyer', 'decision_process', 'identify_pain',
];
for (const fieldId of canonicalCoreFields) {
  assert.match(fieldCatalog, new RegExp(`"${fieldId}"`));
}
assert.equal(canonicalCoreFields.length, 17);
assert.doesNotMatch(component, /核心画像 17 项/);
assert.doesNotMatch(component, /coreFieldGroups\(selectedCustomer\)/);
assert.doesNotMatch(component, /批量采纳候选值/);
assert.match(component, /报告字段覆盖度/);
assert.match(component, /candidate_coverage/);
assert.match(component, /本次报告数据来源/);
assert.match(component, /客户来信 \{\{ reportSourceCounts\(selectedCustomer\)\.inbound_email_count \}\} 封/);
assert.match(component, /销售手工记录 \{\{ reportSourceCounts\(selectedCustomer\)\.manual_note_count \}\} 条/);
assert.doesNotMatch(component, /统一来源列表|report-evidence-section|filteredReportEvidence/);
assert.match(component, /来源：\{\{ coreFieldSource\(field\) \}\}/);
assert.match(analysisApi, /evidence_summary: EvidenceSummary/);
assert.match(analysisApi, /source_counts: EvidenceSummary/);
assert.match(component, /customer\.reportCoverage \?\?/);
assert.match(component, /route\.query\.runId/);
assert.match(component, /analysisApi\.getAnalysisRun/);
assert.match(component, /router\.replace/);
assert.match(component, /analysisRunTimer = window\.setInterval\(\(\) =>/);
assert.match(component, /refreshWhenAnalysisRunSettles/);
assert.match(component, /analysisRefreshTimer/);
assert.match(component, /refreshCurrentReportUntilReal/);
assert.match(component, /if \(!runId\) \{\s*startCurrentReportPolling\(companyId\);/);
const summaryMetrics = component.match(/<div class="analysis-metrics">([\s\S]*?)<!-- E3:/)?.[1] || '';
for (const label of ['画像完整度', '预算', '关键决策人', '决策周期']) {
  assert.match(summaryMetrics, new RegExp(`<span>${label}<\\/span>`));
}
assert.equal((summaryMetrics.match(/<span>/g) || []).length, 4);
assert.doesNotMatch(summaryMetrics, /决策团队/);
assert.doesNotMatch(component, /decisionTeamText|decisionTeamLabel/);
assert.match(component, /\.analysis-metrics \{[\s\S]*?grid-template-columns: repeat\(4, minmax\(0, 1fr\)\)/);
assert.doesNotMatch(component, /\.analysis-metrics > div:last-child/);
assert.match(component, /function averageReportCoverage/);
assert.match(component, /平均报告字段覆盖度/);
assert.match(component, /function coreFieldIsMissing/);
assert.match(component, /narrativeReportSections\(selectedCustomer\)/);
assert.match(component, /narrativeFieldDefinitions/);
assert.match(component, /function isPlaceholderValue\(value: unknown\)/);
assert.match(component, /!isPlaceholderValue\(value\)/);
for (const label of [
  '覆盖判断', '市场机会', '放大路径',
  '核心场景', '平台嵌入', '扩展方向',
  '竞对范围', 'ROI测算', '竞争策略',
  '三层痛点', '技术集成',
  '推荐方案', '配置方案', '交付路径',
]) {
  assert.match(component, new RegExp(label));
}
assert.match(component, /目标行业与区域/);
assert.match(component, /发展阶段、采购可能性与判断依据/);
assert.match(component, /仍需销售验证的问题/);
assert.match(component, /所需集成与实施步骤/);
assert.match(component, /<div class="report-section-title">\{\{ module\.title \}\}<\/div>/);
assert.match(component, /v-for="field in module\.fields"/);
assert.match(component, /class="report-module-fields"/);
assert.match(component, /\.hard-report-wrap \.report-module-fields \{[\s\S]*?grid-template-columns: 1fr/);
assert.doesNotMatch(component, /分析报告 \{\{ moduleIndex \+ 1 \}\}/);
assert.match(component, /rawModule\.sections/);
assert.match(component, /function structuredModuleSections/);
assert.match(component, /'facts', title: '事实'/);
assert.match(component, /'inferences', title: '推断'/);
assert.match(component, /'unknowns', title: '未知项'/);
assert.match(component, /'sales_recommendations', title: '销售建议'/);
assert.match(component, /function salesGuideDimensions/);
assert.match(component, /sales_guidance/);
assert.match(component, /沟通话术/);
assert.match(component, /跟进邮件/);
assert.match(analysisApi, /\/customer-analysis\/field-catalog/);
assert.match(analysisApi, /\/core-fields/);
assert.match(analysisApi, /analysis-suggestions:review-batch/);
assert.doesNotMatch(component, /class="report-company-name"/);
assert.doesNotMatch(component, /AI分析报告/);
assert.match(component, /<strong>判断依据：<\/strong>/);
assert.match(component, /<strong>销售追问：<\/strong>/);
assert.match(component, /<strong>下一步动作：<\/strong>/);
assert.match(component, /<strong>风险：<\/strong>/);
assert.doesNotMatch(component, /<strong>维度代码：<\/strong>/);
assert.doesNotMatch(component, /<strong>状态：<\/strong>/);
assert.match(component, /\.hard-report-wrap \.report-module-detail \{[\s\S]*?font-size: 13px/);
assert.match(component, /\.hard-report-wrap \.report-module-section \{[\s\S]*?border-radius: 8px/);
assert.match(component, /\.hard-report-wrap \.report-module-section:nth-child\(4\) \{[\s\S]*?border-left-color:\s*#2864ef/);
assert.match(component, /role="alert"/);
assert.doesNotMatch(component, /analysisApi\.createAnalysisRun/);
assert.doesNotMatch(component, /analysisButtonText|generateAnalysis|force_refresh: customer\.reportGenerated/);
assert.doesNotMatch(component, />\s*重新生成分析\s*<\/button>|>\s*生成分析报告\s*<\/button>/);
assert.match(operationComponent, /manualRecordSaving \? '保存中\.\.\.' : '确认录入'/);
assert.doesNotMatch(operationComponent, /确认并生成新版报告/);
assert.match(operationComponent, /customerAnalysisRoute\(companyId, \{ runId: result\.analysis\.runId \|\| '' \}\)/);
assert.match(analysisApi, /timeout: 30_000/);

const trailingMobileRules = component.match(/<\/style>[\s\S]*@media \(max-width: 760px\)/g) || [];
assert.equal(trailingMobileRules.length, 0, 'mobile rules must stay inside the scoped style block');

console.log('Customer analysis presentation contract test passed');
