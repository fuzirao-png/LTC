<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import {
  analysisApi,
  type CoreFieldCatalog,
  type CoreFieldItem,
  type CoreFieldsResponse,
  type EvidenceSummary,
} from '../../services/analysisApi';
import { useAuthStore } from '../../stores/auth';
import { customerIdFromAnalysisQuery, findAnalysisCustomer } from '../../shared/utils/customerAnalysisNavigation.js';
import { countryCardLabel, resolveCustomerClock } from '../../shared/utils/customerClock.js';
import { sanitizeCustomerName } from '../../shared/utils/customerName.js';
import { regionLabel } from '../../shared/utils/labels';
import {
  clearManualNoteAnalysisState,
  loadManualNoteAnalysisState,
  resolveCompetitionUpdateStatus,
  type ManualNoteAnalysisState,
} from './manualNoteAnalysisState.js';

// ---- types ----

interface CustomerListItem {
  customerId: string;
  client_id: string;
  customerName: string;
  companyName?: string;
  industry: string;
  icpScore: number;
  opportunityScore?: number;
  riskLevel: 'low' | 'medium' | 'high';
  budget: string;
  analysisSummary: string;
  reportGenerated: boolean;
  profileCompleteness?: number;
  reportCoverage?: number;
  // E1 new fields from backend
  decisionMakerText?: string;
  decisionCycleText?: string;
  employeeScale?: string;
  regionText?: string;
  country?: string;
  city?: string;
  region?: string;
  regionTime?: string;
  timeZone?: string;
  completenessScore?: number;
  // E3: inline profile_structure from list API
  profileStructure?: ProfileStructure;
}

interface ProfileStructure {
  customer_view?: {
    concerns?: string;
    partners?: string;
    impression_of_us?: string;
  };
  latest_news?: { title: string; summary: string }[];
}

interface Customer360Data {
  company_id: string;
  customerName?: string;
  customer_profile: {
    client_id?: string;
    company_type?: string;
    region_text?: string;
    employee_scale?: string;
    business_model?: string;
    esim_scenario?: string;
    coverage?: string;
    estimated_usage?: string;
    integration?: string;
    compliance?: string;
    budget_text?: string;
    decision_maker_text?: string;
    decision_maker_contact_id?: string;
    decision_cycle_text?: string;
    decision_maker_team_label?: string;
    completeness_score?: number;
    source_summary?: string;
    extra_payload?: Record<string, unknown>;
    [key: string]: unknown;
  };
  meddpicc: Record<string, {
    level?: string;
    status?: string;
    desc?: string;
    summary?: string;
    [key: string]: unknown;
  }>;
  /** PRD $7.4 5-section flat text */
  analysis_report: {
    market_analysis?: string;
    company_analysis?: string;
    competitor_analysis?: string;
    product_suggestion?: string;
    sales_guidance?: Record<string, unknown>;
    confidence?: number;
    _content_source?: string;
    _is_real_analysis?: boolean;
    _raw?: Record<string, unknown>;
    evidence_summary?: EvidenceSummary;
    [key: string]: unknown;
  };
  /** E2 new field from backend */
  profile_structure?: ProfileStructure;
  core_fields?: CoreFieldsResponse | null;
  field_catalog?: CoreFieldCatalog | null;
}

// ---- state ----

const customers = ref<CustomerListItem[]>([]);
const loading = ref(false);
const selectedCustomer = ref<Customer360Data | null>(null);
const reportLoading = ref(false);
const error = ref('');
const acceptingCandidates = ref(false);
const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const clockNow = ref(new Date());
const pendingAnalysisRunId = ref('');
const activeAnalysisRunId = ref('');
const manualNoteAnalysisState = ref<ManualNoteAnalysisState | null>(null);
let clockTimer: number | undefined;
let analysisRunTimer: number | undefined;
let analysisRefreshTimer: number | undefined;
let analysisRefreshCompanyId = '';
let analysisRefreshAttempts = 0;

// ---- computed ----

const customerList = computed(() => customers.value);
const hasRealAnalysis = computed(() => selectedCustomer.value?.analysis_report?._is_real_analysis === true);
const marketLabel = computed(() => {
  const regionCode = auth.currentUser?.regionCode;
  return regionCode ? `${regionLabel(regionCode)}市场` : '全部市场';
});

function displayName(item: CustomerListItem): string {
  return item.customerName || item.companyName || item.client_id;
}

function customerLocation(item: CustomerListItem): string {
  return countryCardLabel(item.country);
}

function customerTime(item: CustomerListItem): string {
  if (item.regionTime) return item.regionTime;
  const region = String(item.region || '').toUpperCase();
  const clock = resolveCustomerClock(item);
  if (!clock) return `${region ? regionLabel(region) : '当地'}时间待确认`;
  try {
    const time = new Intl.DateTimeFormat('zh-CN', {
      timeZone: clock.timeZone,
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }).format(clockNow.value);
    return `${clock.label} ${time}`;
  } catch {
    return `${clock.label}待确认`;
  }
}

function completenessPercent(customer: CustomerListItem): { label: string; color: string } {
  const score = customer.reportCoverage ?? customer.completenessScore ?? customer.profileCompleteness ?? -1;
  if (score > 0 && score <= 1) {
    // completeness_score is 0-1 from backend ($7.2 profile model)
    const pct = Math.round(score * 100);
    return { label: `${pct}%`, color: 'blue-text' };
  }
  if (score >= 0) return { label: `${score}%`, color: 'blue-text' };
  return { label: '待补全', color: 'muted' };
}

function borderForCustomer(_customer: CustomerListItem): string {
  return 'blue';
}

function icpGrade(customer: CustomerListItem): string {
  if (customer.icpScore >= 85) return 'A';
  if (customer.icpScore >= 72) return 'B+';
  if (customer.icpScore >= 60) return 'B';
  return 'C';
}

function decisionMakerText(customer: CustomerListItem): string {
  return customer.decisionMakerText || '待确认';
}

function decisionCycleText(customer: CustomerListItem): string {
  return customer.decisionCycleText || '待确认';
}

function profilePercent(value: number | null | undefined): string {
  if (value == null || value < 0) return '--';
  return String(Math.round(value <= 1 ? value * 100 : value)) + '%';
}

function customerType(customer: CustomerListItem): string {
  const value = customer.industry || '';
  if (/ota|商旅|travel platform|travel agency/i.test(value)) return '商旅 OTA';
  if (/金融|fintech|finance/i.test(value)) return '金融科技';
  return '差旅平台';
}


function textOrDash(val: string | undefined | null): string {
  if (!val || !val.trim()) return '暂无数据';
  return val.trim();
}

const reportFieldLabels: Record<string, string> = {
  name: '名称',
  title: '标题',
  analysis: '分析',
  position: '定位',
  coverage: '覆盖范围',
  price_range: '价格范围',
  rationale: '理由',
  our_diff: '我方差异化',
  scenario: '场景',
  demand: '需求',
  opportunity: '机会',
  size: '规模',
  our_fit: '我方匹配',
  main_business: '主营业务',
  revenue_model: '商业模式',
  geography: '覆盖区域',
  employee_scale: '员工规模',
  esim_scenario: 'eSIM场景',
  integration: '集成方式',
  estimated_usage: '预估用量',
  business_model: '业务模式',
  compliance: '合规要求',
  status: '状态',
  summary: '摘要',
  detail: '详情',
  metric: '指标',
  actors: '参与角色',
  process_steps: '流程步骤',
  next_question: '下一步问题',
  risk: '风险',
  conclusion: '结论',
  recommendation: '建议',
  evidence: '依据',
  strengths: '优势',
  weaknesses: '不足',
  opportunities: '机会',
  threats: '挑战',
};

function polishReportCopy(value: string): string {
  return value
    .trim()
    .replace(/[（(]([^()（）\n]{1,80})[）)]/g, '，$1')
    .replace(/，\s*([，。；])/g, '$1')
    .replace(/\s*\|\s*/g, '；')
    .replace(/，{2,}/g, '，');
}

function reportFieldLabel(key: string): string {
  return reportFieldLabels[key] || key.replace(/_/g, ' ');
}

const internalEvidenceIdPattern = /\b(?:internal-manual-note|internal-email|context):[a-z0-9-]+\b/gi;
const internalEvidenceFieldKeys = new Set(['evidence', 'evidence_id', 'evidence_ids', 'evidence_refs']);

function cleanReportText(value: string): string {
  return value
    .replace(/(?:证据|依据)\s*[：:]\s*(?:internal-manual-note|internal-email|context):[a-z0-9-]+[。；;，,\s]*/gi, '')
    .replace(internalEvidenceIdPattern, '')
    .trim();
}

function shouldRenderReportField(key: string, item: unknown): boolean {
  if (key.startsWith('_') || item == null || item === '') return false;
  if (internalEvidenceFieldKeys.has(key.trim().toLowerCase())) return false;
  return true;
}

function renderText(value: unknown, depth = 0): string {
  if (typeof value === 'string') return cleanReportText(polishReportCopy(textOrDash(value))) || '暂无数据';
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (Array.isArray(value)) {
    const items = value.map((item) => renderText(item, depth + 1)).filter((item) => item !== '暂无数据');
    return items.length ? items.map((item) => `• ${item}`).join('\n') : '暂无数据';
  }
  if (value && typeof value === 'object') {
    const rows = Object.entries(value as Record<string, unknown>)
      .filter(([key, item]) => shouldRenderReportField(key, item))
      .map(([key, item]) => `${reportFieldLabel(key)}：${renderText(item, depth + 1)}`);
    return rows.join(depth ? '；' : '\n') || '暂无数据';
  }
  return '暂无数据';
}

const MISSING_REPORT_INFO = '信息缺失，需要销售进行跟进补齐';

interface NarrativeReportDefinition {
  key: string;
  title: string;
  section: 'market_analysis' | 'company_analysis' | 'competitor_analysis' | 'pain_analysis' | 'product_suggestion';
  rawKey: string;
}

function renderCompetitorRelations(value: unknown): string {
  if (!Array.isArray(value)) return '';
  return value
    .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === 'object'))
    .map((item) => {
      const name = String(item.entity_name || '').trim();
      if (!name) return '';
      const relation = item.relation_type === 'customer_partner'
        ? '合作伙伴'
        : item.relation_type === 'customer_competitor'
          ? '客户竞品'
          : '市场竞争参考';
      const state = item.customer_fact_status === 'confirmed'
        ? '已确认'
        : item.evidence_state === 'knowledge_supported'
          ? '知识库支持，客户未确认'
          : item.evidence_state === 'external_supported'
            ? '联网资料支持，客户未确认'
            : '待确认';
      const reason = String(item.reason || '').trim();
      return `${name}：${relation}（${state}）${reason ? `，${renderText(reason)}` : ''}`;
    })
    .filter(Boolean)
    .join('\n');
}

interface NarrativeReportField {
  key: string;
  label: string;
  value: string;
}

function reportSourceCounts(data: Customer360Data): EvidenceSummary {
  return data.analysis_report?.evidence_summary || data.core_fields?.source_counts || {
    total_count: 0,
    email_count: 0,
    inbound_email_count: 0,
    outbound_email_count: 0,
    manual_note_count: 0,
    meeting_count: 0,
    web_count: 0,
  };
}

function evidenceSourceLabel(sourceType: unknown, direction?: unknown): string {
  if (sourceType === 'internal_manual_note') return '销售手工记录';
  if (sourceType === 'internal_email') return direction === 'outbound' ? '我方邮件' : '客户来信';
  if (sourceType === 'internal_company' || sourceType === 'internal_profile') return '客户主数据';
  if (sourceType === 'internal_lead' || sourceType === 'internal_assessment') return '内部客户资料';
  if (sourceType === 'internal_meddpicc') return '已确认 MEDDPICC';
  return '联网资料';
}

function coreFieldSource(field: CoreFieldItem): string {
  const evidence = field.candidate?.evidence_refs?.[0] as Record<string, unknown> | undefined;
  if (evidence) {
    const metadata = evidence.metadata as Record<string, unknown> | undefined;
    return evidenceSourceLabel(evidence.source_type, metadata?.direction);
  }
  const source = String(field.provenance?.source || '');
  if (source === 'confirmed_manual_note') return '销售手工记录';
  if (source === 'accepted_analysis_suggestion') return '已采纳分析建议';
  if (source === 'manual') return '销售确认';
  return '';
}

function averageReportCoverage(): string {
  if (!customers.value.length) return '--';
  const total = customers.value.reduce((sum, customer) => {
    const score = customer.reportCoverage ?? customer.completenessScore ?? customer.profileCompleteness ?? 0;
    return sum + (score <= 1 ? score * 100 : score);
  }, 0);
  return String(Math.round(total / customers.value.length));
}

const narrativeReportDefinitions: NarrativeReportDefinition[] = [
  { key: 'market', title: '市场分析', section: 'market_analysis', rawKey: 'market' },
  { key: 'company', title: '公司分析', section: 'company_analysis', rawKey: 'company' },
  { key: 'competitor', title: '竞争分析', section: 'competitor_analysis', rawKey: 'competitor' },
  { key: 'pain', title: '需求痛点', section: 'pain_analysis', rawKey: 'pain' },
  { key: 'product', title: '产品建议', section: 'product_suggestion', rawKey: 'product' },
];

const narrativeFieldDefinitions: Record<string, { key: string; label: string; paths: string[] }[]> = {
  market: [
    { key: 'coverage_judgement', label: '覆盖判断', paths: ['structure.coverage_judgement', 'coverage', 'facts.0.text'] },
    { key: 'market_opportunity', label: '市场机会', paths: ['market_opportunity', 'trend', 'inferences.0.text'] },
    { key: 'amplification_path', label: '放大路径', paths: ['amplification_path', 'scenario_opportunity', 'sales_recommendations.0.action'] },
  ],
  company: [
    { key: 'core_scenario', label: '核心场景', paths: ['core_scenario', 'operation', 'scenario_demand.0.scenario', 'facts.0.text'] },
    { key: 'platform_embedding', label: '平台嵌入', paths: ['platform_embedding', 'product.integration', 'product', 'facts.1.text'] },
    { key: 'expansion_direction', label: '扩展方向', paths: ['expansion_direction', 'target_market', 'scenario_opportunity', 'inferences.0.text'] },
  ],
  competitor: [
    { key: 'competitor_scope', label: '竞对范围', paths: ['competitor_scope', 'products', 'services', 'facts.0.text'] },
    { key: 'roi_estimate', label: 'ROI测算', paths: ['roi_estimate', 'pricing', 'recommended_price', 'inferences.0.text'] },
    { key: 'competitive_strategy', label: '竞争策略', paths: ['competitive_strategy', 'services', 'sales_recommendations.0.action', 'inferences.0.text'] },
  ],
  pain: [
    { key: 'three_layer_pain', label: '三层痛点', paths: ['three_layer_pain', 'layers', 'requirement', 'facts.0.text'] },
    { key: 'technical_integration', label: '技术集成', paths: ['technical_integration', 'integration', 'layers.1', 'facts.1.text'] },
  ],
  product: [
    { key: 'recommended_solution', label: '推荐方案', paths: ['recommended_solution', 'recommended', 'facts.0.text'] },
    { key: 'configuration_solution', label: '配置方案', paths: ['configuration_solution', 'recommended.0.our_diff', 'product', 'facts.1.text'] },
    { key: 'delivery_path', label: '交付路径', paths: ['delivery_path', 'recommended_price.payment_terms', 'actions', 'sales_recommendations.0.action'] },
  ],
};

function meaningfulValue(value: unknown): boolean {
  if (value == null || value === '') return false;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === 'object') return Object.keys(value as Record<string, unknown>).length > 0;
  return !/^暂无|^待确认$|^待分析$/.test(String(value).trim());
}

function evidenceStatusLabel(item: any): string {
  if (item?.customer_fact_status === 'confirmed') return '已确认'
  if (item?.evidence_state === 'knowledge_supported') return '知识库支持，客户未确认'
  if (item?.evidence_state === 'external_supported') return '联网资料支持，客户未确认'
  if (item?.evidence_state === 'inferred') return '推断，待确认'
  if (item?.evidence_state === 'missing') return '缺少证据'
  return item?.status === 'partial' ? '待补全' : '待确认'
}

// Older persisted reports contain one generated paragraph copied into several
// fields. Treat it as stale data so the renderer can fall through to the
// structured facts, inferences, unknowns, or sales recommendations instead.
function isPlaceholderValue(value: unknown): boolean {
  if (typeof value === 'string') return /^待确认竞品\d*$/.test(value.trim()) || value.trim() === '待确认';
  if (Array.isArray(value)) return value.length > 0 && value.every((item) => isPlaceholderValue(item));
  if (value && typeof value === 'object') return isPlaceholderValue((value as Record<string, unknown>).name);
  return false;
}

function isLegacyTemplateNarrative(value: unknown): boolean {
  if (typeof value !== 'string') return false;
  return [
    '现有线索显示，客户主要关注',
    '本段判断依据包括',
    '本轮销售推进的关键',
    '应在下一次会议中逐项补证',
    '准备一页式说明、风险清单和下一步行动',
  ].some((marker) => value.includes(marker));
}

function valueAtPath(value: Record<string, unknown>, path: string): unknown {
  return path.split('.').reduce<unknown>((current, part) => {
    if (current && typeof current === 'object' && !Array.isArray(current)) {
      return (current as Record<string, unknown>)[part];
    }
    if (Array.isArray(current) && /^\d+$/.test(part)) return current[Number(part)];
    return undefined;
  }, value);
}

function firstMeaningfulAtPaths(module: Record<string, unknown>, paths: string[]): unknown {
  return paths
    .map((path) => valueAtPath(module, path))
    .find((value) => meaningfulValue(value) && !isPlaceholderValue(value) && !isLegacyTemplateNarrative(value) && isChineseNarrative(value));
}

function isChineseNarrative(value: unknown): boolean {
  const text = renderText(value).replace(/https?:\/\/\S+|\b(?:exa|web|weknora|internal):[a-z0-9:_/-]+\b/gi, '');
  const chinese = (text.match(/[\u3400-\u4dbf\u4e00-\u9fff]/g) || []).length;
  const latin = (text.match(/[A-Za-z]/g) || []).length;
  return chinese >= 4 && chinese >= latin * 0.35;
}

function cleanNarrativeFieldText(value: string): string {
  return value
    .replace(/(?:引用)?证据\s*[:：][^。；\n]+[。；]?/g, '')
    .replace(/(?:evidence_ids?|evidence_refs?)\s*[:：][^。；\n]+[。；]?/gi, '')
    .replace(/\b(?:internal|exa|weknora|web):[a-z0-9_-]+\b/gi, '')
    .replace(/[ \t]{2,}/g, ' ')
    .replace(/([，。；])\s*([，。；])/g, '$1')
    .trim();
}

function narrativeModuleFields(moduleName: string, module: Record<string, unknown> | undefined): NarrativeReportField[] {
  if (!module) return [];
  return (narrativeFieldDefinitions[moduleName] || []).map((definition) => {
    const value = firstMeaningfulAtPaths(module, definition.paths);
    const relationText = moduleName === 'competitor' && definition.key === 'competitor_scope' && Array.isArray(module.competitor_relations)
      ? renderCompetitorRelations(module.competitor_relations)
      : '';
    return {
      key: definition.key,
      label: definition.label,
      value: meaningfulValue(value) || relationText
        ? [meaningfulValue(value) ? cleanNarrativeFieldText(renderText(value)) : '', relationText].filter(Boolean).join('\n') || MISSING_REPORT_INFO
        : MISSING_REPORT_INFO,
    };
  });
}

function structuredModuleSections(module: Record<string, unknown> | undefined): string[] {
  if (!module) return [];
  const definitions: {
    key: 'facts' | 'inferences' | 'unknowns' | 'sales_recommendations';
    title: string;
    valueKey: 'text' | 'item' | 'action';
    detailKey?: 'reason';
  }[] = [
    { key: 'facts', title: '事实', valueKey: 'text' },
    { key: 'inferences', title: '推断', valueKey: 'text' },
    { key: 'unknowns', title: '未知项', valueKey: 'item', detailKey: 'reason' },
    { key: 'sales_recommendations', title: '销售建议', valueKey: 'action', detailKey: 'reason' },
  ];
  return definitions.flatMap((definition) => {
    const values = module[definition.key];
    if (!Array.isArray(values)) return [];
    const lines = values
      .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === 'object'))
      .map((item) => {
        const value = item[definition.valueKey];
        if (!meaningfulValue(value)) return '';
        const detail = definition.detailKey ? item[definition.detailKey] : null;
        const suffix = meaningfulValue(detail) ? `：${renderText(detail)}` : '';
        return `• ${renderText(value)}${suffix}`;
      })
      .filter(Boolean);
    return lines.length ? [`【${definition.title}】\n${lines.join('\n')}`] : [];
  });
}

function narrativeReportSections(data: Customer360Data) {
  const raw = data.analysis_report?._raw || {};
  return narrativeReportDefinitions.map((definition) => {
    const flat = data.analysis_report?.[definition.section];
    const rawModule = raw[definition.rawKey] as Record<string, unknown> | undefined;
    let fields = narrativeModuleFields(definition.key, rawModule);
    const competitorRelations: unknown[] = Array.isArray(rawModule?.competitor_relations) ? rawModule.competitor_relations : [];
    if (false && definition.key === 'competitor' && competitorRelations.length) {
      fields = [
        ...fields,
        {
          key: 'competitor_relations',
          label: '瀹㈡埛绔炲搧/鍚堜綔鍏崇郴',
          value: renderCompetitorRelations(competitorRelations),
        },
      ];
    }
    const structuredSections = structuredModuleSections(rawModule);
    const generatedSections = Array.isArray(rawModule?.sections)
      ? rawModule.sections
          .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === 'object'))
          .filter((item) => meaningfulValue(item.content))
          .map((item) => `【${String(item.subtitle || '分析结论')}】\n${renderText(item.content)}`)
      : [];
    const generatedSummary = meaningfulValue(rawModule?.analysis_summary)
      ? renderText(rawModule?.analysis_summary)
      : '';
    let value = structuredSections.length
      ? structuredSections.join('\n\n')
      : generatedSections.length
      ? [generatedSummary, ...generatedSections].filter(Boolean).join('\n\n')
      : meaningfulValue(flat) ? flat : null;
    if (definition.key === 'competitor') {
      if (
        manualNoteAnalysisState.value?.companyId === data.company_id &&
        manualNoteAnalysisState.value.status !== 'completed'
      ) {
        value = manualNoteAnalysisState.value.message;
      } else {
      const competition = data.meddpicc?.competition;
      const confirmedCompetitor = competition?.summary || competition?.desc;
      if (meaningfulValue(confirmedCompetitor)) {
        const confirmedLine = `【已确认竞争对手】\n${renderText(confirmedCompetitor)}`;
        value = meaningfulValue(value) ? `${confirmedLine}\n\n${renderText(value)}` : confirmedLine;
      }
      }
    }
    return {
      ...definition,
      fields,
      value: meaningfulValue(value) ? renderText(value) : MISSING_REPORT_INFO,
    };
  });
}

function coreFieldGroups(data: Customer360Data) {
  const fields = data.core_fields?.fields || [];
  const groups = data.field_catalog?.groups || [];
  return groups.map((group) => ({
    ...group,
    fields: group.fields.map((definition) => {
      const field = fields.find((item) => item.field_id === definition.id);
      return field ? { ...definition, ...field } : {
        group_id: group.id,
        group_label: group.label,
        field_id: definition.id,
        label: definition.label,
        target_type: definition.target_type,
        value: null,
        status: 'missing',
        candidate: null,
        provenance: {},
        collection_method: definition.collection_method,
        missing_guidance: definition.missing_guidance,
      } satisfies CoreFieldItem;
    }),
  }));
}

function coreFieldValue(field: CoreFieldItem): string {
  if (meaningfulValue(field.value)) return renderText(field.value);
  if (field.candidate && meaningfulValue(field.candidate.proposed_value)) {
    return renderText(field.candidate.proposed_value);
  }
  return field.missing_guidance || MISSING_REPORT_INFO;
}

function coreFieldIsMissing(field: CoreFieldItem): boolean {
  return !meaningfulValue(field.value) && !meaningfulValue(field.candidate?.proposed_value);
}

function coreFieldStatus(field: CoreFieldItem): string {
  if (field.candidate) return '待采纳';
  if (field.status === 'confirmed') return '已确认';
  if (field.status === 'partial') return '部分确认';
  if (field.collection_method === 'sales_confirmation') return '需访谈';
  return '缺失';
}

interface SalesGuideDimension {
  code: string;
  label: string;
  status: string;
  summary: string;
  judgement: string;
  salesQuestion: string;
  nextAction: string;
  risk: string;
  questions: string[];
  actions: string[];
  talkTrack: string[];
  emailDraft: { subject: string; body: string } | null;
}

function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.map((item) => String(item || '').trim()).filter(Boolean)
    : [];
}

function salesGuideDimensions(data: Customer360Data | null): SalesGuideDimension[] {
  if (!data) return [];
  const source = data.meddpicc as any;
  const dimensions = Array.isArray(source)
    ? source
    : Array.isArray(source.dimensions)
      ? source.dimensions
      : Object.entries(source).map(([dimension_code, value]) => ({ dimension_code, ...(value as any) }));

  const raw = dimensions.map((dim: any) => ({
    code: String(dim.dimension_code || dim.code || ''),
    status: String(dim.status || 'unknown'),
    summary: String(dim.summary || dim.desc || dim.payload?.summary || dim.payload?.desc || '').trim(),
    salesQuestion: String(dim.sales_question || dim.follow_up_question || dim.question || dim.payload?.sales_question || dim.payload?.follow_up_question || '').trim(),
    nextAction: String(dim.next_action || dim.action || dim.recommendation || dim.payload?.next_action || dim.payload?.action || '').trim(),
    risk: String(dim.risk || dim.payload?.risk || '').trim(),
  })).filter((dim: any) => dim.code);

  // The prototype presents three sales-guide decisions while the API stores
  // the underlying MEDDPICC evidence as eight separate dimensions.
  const groups = [
    { code: 'customer_demand', guideKey: 'customer_need', label: '客户需求', members: ['metrics', 'identify_pain'], question: '客户当前最需要解决的业务问题及量化目标是什么？' },
    { code: 'decision_path', guideKey: 'decision_chain', label: '决策链路', members: ['economic_buyer', 'decision_criteria', 'decision_process', 'paper_process', 'champion'], question: '预算、技术、采购和最终签字分别由谁负责？' },
    { code: 'competitive_advantage', guideKey: 'competitive_edge', label: '竞争优势', members: ['competition'], question: '客户正在比较哪些方案，最看重哪项差异？' },
  ];

  const reportGuide = data.analysis_report?.sales_guidance || {};
  const candidateByCode = new Map(
    (data.core_fields?.fields || [])
      .filter((field) => field.target_type === 'meddpicc' && field.candidate)
      .map((field) => [field.field_id, field.candidate?.proposed_value as Record<string, unknown>]),
  );

  return groups.map((group) => {
    const matched = raw.filter((dim: any) => group.members.includes(dim.code));
    const candidates = group.members
      .map((code) => candidateByCode.get(code))
      .filter((item): item is Record<string, unknown> => Boolean(item));
    const statuses = [
      ...matched.map((dim: any) => dim.status),
      ...candidates.map((candidate) => String(candidate.status || 'unknown')),
    ];
    const status = statuses.includes('confirmed') ? 'confirmed' : statuses.includes('partial') ? 'partial' : 'unknown';
    const guide = (reportGuide[group.guideKey] || {}) as Record<string, unknown>;
    const guideItems = Array.isArray(guide.items)
      ? guide.items.filter((item): item is Record<string, unknown> => Boolean(item && typeof item === 'object'))
      : [];
    const summaries = [
      ...matched.map((dim: any) => dim.summary).filter(Boolean),
      ...candidates.map((candidate) => candidate.summary).filter(Boolean),
      ...guideItems.map((item) => item.analysis).filter(Boolean),
    ].map(String);
    const questions = matched.map((dim: any) => dim.salesQuestion).filter(Boolean);
    const actions = matched.map((dim: any) => dim.nextAction).filter(Boolean);
    const guideQuestions = stringList(guide.questions);
    const guideActions = stringList(guide.actions);
    const talkTrack = stringList(guide.talk_track);
    const risks = [
      ...matched.map((dim: any) => dim.risk).filter(Boolean),
      ...candidates.map((candidate) => (candidate.payload as Record<string, unknown> | undefined)?.risk).filter(Boolean),
    ].map(String);
    const judgement = summaries.join(' ') || (guideQuestions.length ? '已生成销售指引，关键事实仍需在沟通中确认。' : MISSING_REPORT_INFO);
    const rawDraft = guide.email_draft as Record<string, unknown> | undefined;
    const emailDraft = rawDraft && meaningfulValue(rawDraft.subject) && meaningfulValue(rawDraft.body)
      ? { subject: String(rawDraft.subject), body: String(rawDraft.body) }
      : null;
    return {
      code: group.code,
      label: group.label,
      status,
      summary: judgement,
      judgement,
      salesQuestion: guideQuestions.join(' ') || questions.join(' ') || group.question,
      nextAction: guideActions.join(' ') || actions.join(' ') || (status === 'confirmed' ? '基于已确认信息推进方案和下一轮决策沟通。' : '补齐未确认信息后更新客户画像与推进计划。'),
      risk: risks.join(' ') || (status === 'confirmed' ? '仍需持续核对信息时效，避免依据过期。' : '关键信息未确认，可能导致方案偏差或推进延误。'),
      questions: guideQuestions.length ? guideQuestions : [group.question],
      actions: guideActions.length ? guideActions : [status === 'confirmed' ? '基于已确认信息推进方案和下一轮决策沟通。' : '补齐未确认信息后更新客户画像与推进计划。'],
      talkTrack,
      emailDraft,
    };
  });
}

function profileStructure(data: Customer360Data | null): ProfileStructure {
  return data?.profile_structure || {
    customer_view: { concerns: '待分析', partners: '待确认', impression_of_us: '待评估' },
    latest_news: [],
  };
}

function customerViewPoints(data: Customer360Data | null): { label: string; value: string }[] {
  const view = profileStructure(data).customer_view || {};
  return [
    { label: '关注点', value: view.concerns || '待分析' },
    { label: '合作方', value: view.partners || '待确认' },
    { label: '觉得我们如何', value: view.impression_of_us || '待评估' },
  ];
}

function latestNews(data: Customer360Data | null): { title: string; summary: string }[] {
  return profileStructure(data).latest_news || [];
}

/** Display name for the selected customer in the report panel. */
function selectedCustomerName(data: Customer360Data): string {
  // Use the profile's company_summary or company_type as display name.
  // The customer name is not in the 360 payload, but we can derive it.
  const profile = data?.customer_profile || {}
  return (profile as any).company_summary || profile.company_type || data.company_id || '待确认'
}

function routeValue(value: unknown): string {
  const candidate = Array.isArray(value) ? value[0] : value;
  return String(candidate || '').trim();
}

function applyCustomerReport(customer: CustomerListItem, raw: unknown) {
  const payload = (raw as any)?.data || raw as any;
  const id = customer.client_id || customer.customerId;
  selectedCustomer.value = {
    company_id: id,
    customerName: (raw as any)?.customerName || (raw as any)?.companyName || payload?.customerName || payload?.companyName || customer.customerName || customer.companyName || id,
    customer_profile: {
      company_id: id,
      company_type: customer.industry || null,
      region_text: customer.regionText || null,
      employee_scale: customer.employeeScale || null,
      budget_text: customer.budget || null,
      decision_maker_text: customer.decisionMakerText || null,
      decision_cycle_text: customer.decisionCycleText || null,
      completeness_score: customer.completenessScore ?? customer.profileCompleteness ?? null,
      ...(payload?.customer_profile || payload?.profile || {}),
    },
    meddpicc: payload?.meddpicc || {},
    analysis_report: payload?.analysis_report || payload?.analysis_modules || payload?.report || {},
    profile_structure: payload?.profile_structure || customer.profileStructure,
    core_fields: payload?.core_fields || null,
    field_catalog: payload?.field_catalog || null,
  };
}

async function loadCustomerReport(customer: CustomerListItem) {
  const id = customer.client_id || customer.customerId;
  if (!id) return;
  const raw = await analysisApi.legacyCustomer360(id);
  applyCustomerReport(customer, raw);
}

function stopAnalysisRunPolling() {
  if (analysisRunTimer !== undefined) {
    window.clearInterval(analysisRunTimer);
    analysisRunTimer = undefined;
  }
  activeAnalysisRunId.value = '';
}

function stopCurrentReportPolling() {
  if (analysisRefreshTimer !== undefined) {
    window.clearInterval(analysisRefreshTimer);
    analysisRefreshTimer = undefined;
  }
  analysisRefreshCompanyId = '';
  analysisRefreshAttempts = 0;
}

function stripRunIdFromRoute() {
  if (!route.query.runId) return;
  const nextQuery = { ...route.query };
  delete (nextQuery as Record<string, unknown>).runId;
  router.replace({ query: nextQuery }).catch(() => {});
}

async function refreshRequestedCustomer(companyId: string) {
  const customer = findAnalysisCustomer(customers.value, companyId);
  if (!customer) return;
  await loadCustomerReport(customer);
}

async function refreshCurrentReportUntilReal(companyId: string) {
  if (analysisRefreshCompanyId !== companyId) return;
  const customer = findAnalysisCustomer(customers.value, companyId);
  if (!customer) {
    stopCurrentReportPolling();
    return;
  }
  await loadCustomerReport(customer);
  if (selectedCustomer.value?.company_id !== companyId) {
    stopCurrentReportPolling();
    return;
  }
  if (hasRealAnalysis.value) {
    stopCurrentReportPolling();
    return;
  }
  analysisRefreshAttempts += 1;
  if (analysisRefreshAttempts >= 12) {
    stopCurrentReportPolling();
  }
}

function startCurrentReportPolling(companyId: string) {
  if (analysisRefreshTimer !== undefined && analysisRefreshCompanyId === companyId) return;
  stopCurrentReportPolling();
  analysisRefreshCompanyId = companyId;
  analysisRefreshAttempts = 0;
  void refreshCurrentReportUntilReal(companyId);
  if (!hasRealAnalysis.value && selectedCustomer.value?.company_id === companyId) {
    analysisRefreshTimer = window.setInterval(() => {
      void refreshCurrentReportUntilReal(companyId);
    }, 8_000);
  }
}

async function refreshWhenAnalysisRunSettles(companyId: string, runId: string) {
  stopAnalysisRunPolling();
  activeAnalysisRunId.value = runId;
  const poll = async () => {
    try {
      const { data } = await analysisApi.getAnalysisRun(runId);
      if (data.status === 'completed' || data.status === 'failed' || data.status === 'cancelled') {
        stopAnalysisRunPolling();
        pendingAnalysisRunId.value = '';
        await refreshRequestedCustomer(companyId);
        if (
          manualNoteAnalysisState.value?.companyId === companyId &&
          manualNoteAnalysisState.value.status === 'pending'
        ) {
          const competition = selectedCustomer.value?.meddpicc?.competition;
          const currentCompetition = String(competition?.summary || competition?.desc || '');
          const resolved = resolveCompetitionUpdateStatus({
            expectedCompetition: manualNoteAnalysisState.value.expectedCompetition,
            runStatus: data.status,
            currentCompetition,
          });
          manualNoteAnalysisState.value = {
            ...manualNoteAnalysisState.value,
            ...resolved,
          };
          clearManualNoteAnalysisState(companyId);
        }
        if (!hasRealAnalysis.value && data.status === 'completed') {
          startCurrentReportPolling(companyId);
        }
        stripRunIdFromRoute();
      }
    } catch (error) {
      console.error('CustomerAnalysis run polling error:', error);
      stopAnalysisRunPolling();
    }
  };
  await poll();
  if (activeAnalysisRunId.value === runId) {
    analysisRunTimer = window.setInterval(() => {
      void poll();
    }, 8_000);
  }
}

// ---- actions ----

onMounted(async () => {
  await loadCustomers();
  await openRequestedCustomer();
  clockTimer = window.setInterval(() => {
    clockNow.value = new Date();
  }, 30_000);
});

onUnmounted(() => {
  if (clockTimer !== undefined) window.clearInterval(clockTimer);
  stopAnalysisRunPolling();
  stopCurrentReportPolling();
});

async function loadCustomers() {
  loading.value = true;
  error.value = '';
  try {
    const pageSize = 100;
    const raw: any[] = [];
    let page = 1;
    let total = 0;
    do {
      const res = (await analysisApi.legacyCustomerList(page, pageSize)) as any;
      const items = Array.isArray(res)
        ? res
        : (res?.list || res?.items || res?.data?.list || res?.data?.items || []);
      raw.push(...items);
      total = Number(res?.total || raw.length);
      if (!items.length) break;
      page += 1;
    } while (raw.length < total);
    customers.value = raw.map((item: any) => {
      const customerName = sanitizeCustomerName(
        [item.companyName, item.customerName, item.legalName, item.name],
        item.website || item.primaryDomain || item.primary_domain,
      );
      return {
      customerId: item.customerId || item.client_id || '',
      client_id: item.client_id || item.customerId || '',
      customerName,
      companyName: customerName,
      industry: item.industry || '待确认',
      icpScore: item.icpScore ?? item.icp_score ?? 0,
      opportunityScore: item.opportunityScore ?? 0,
      riskLevel: item.riskLevel || 'medium',
      budget: item.budget || '待确认',
      analysisSummary: item.analysisSummary || item.summary || '',
      reportGenerated: item.reportGenerated ?? false,
      profileCompleteness: item.profileCompleteness ?? null,
      reportCoverage: item.reportCoverage ?? item.report_coverage ?? item.profileCompleteness ?? null,
      decisionMakerText: item.decisionMakerText || '待确认',
      decisionCycleText: item.decisionCycleText || '待确认',
      employeeScale: item.employeeScale || '待确认',
      regionText: item.regionText || '待确认',
      country: item.country || item.country_name || '',
      city: item.city || '',
      region: item.region || item.region_code || '',
      regionTime: item.regionTime || item.region_time || '',
      timeZone: item.timeZone || item.time_zone || '',
      completenessScore: item.completenessScore ?? item.profileCompleteness ?? null,
      profileStructure: item.profileStructure || null,
      };
    });
  } catch (e: any) {
    error.value = e?.message || '加载客户列表失败';
    console.error('CustomerAnalysis loadCustomers error:', e);
  } finally {
    loading.value = false;
  }
}

async function openProfile(customer: CustomerListItem) {
  const id = customer.client_id || customer.customerId;
  if (!id) return;
  reportLoading.value = true;
  try {
    await loadCustomerReport(customer);
  } catch (e: any) {
    console.error('CustomerAnalysis openProfile error:', e);
  } finally {
    reportLoading.value = false;
  }
}

async function acceptAllCoreFieldCandidates() {
  const data = selectedCustomer.value;
  if (!data?.core_fields || acceptingCandidates.value) return;
  const candidates = data.core_fields.fields
    .map((field) => field.candidate)
    .filter((candidate): candidate is NonNullable<CoreFieldItem['candidate']> => Boolean(candidate));
  if (!candidates.length) return;
  acceptingCandidates.value = true;
  try {
    await analysisApi.reviewSuggestionsBatch(
      data.company_id,
      Number(data.customer_profile.profile_version || 0),
      candidates.map((candidate) => ({
        suggestion_id: candidate.suggestion_id,
        suggestion_version: candidate.version,
        action: 'accept',
      })),
    );
    const customer = customers.value.find(
      (item) => (item.client_id || item.customerId) === data.company_id,
    );
    if (customer) await openProfile(customer);
  } catch (e: any) {
    error.value = e?.response?.data?.error?.message || e?.message || '批量采纳失败';
  } finally {
    acceptingCandidates.value = false;
  }
}

async function openRequestedCustomer() {
  const companyId = customerIdFromAnalysisQuery(route.query.companyId);
  const runId = routeValue(route.query.runId);
  if (!companyId) return;
  const customer = findAnalysisCustomer(customers.value, companyId);
  if (!customer) return;
  manualNoteAnalysisState.value = loadManualNoteAnalysisState(companyId);
  const shouldReload =
    selectedCustomer.value?.company_id !== companyId ||
    pendingAnalysisRunId.value !== runId;
  if (!shouldReload) return;
  stopCurrentReportPolling();
  if (!runId) {
    startCurrentReportPolling(companyId);
    stopAnalysisRunPolling();
  }
  pendingAnalysisRunId.value = runId;
  await openProfile(customer);
  if (runId) {
    await refreshWhenAnalysisRunSettles(companyId, runId);
  }
}

watch(
  () => [route.query.companyId, route.query.runId],
  async () => {
    if (!loading.value) await openRequestedCustomer();
  },
);

function closeProfile() {
  selectedCustomer.value = null;
  stopCurrentReportPolling();
}


</script>

<template>
  <div class="content-main legacy-analysis">
    <div class="agent-live-bar">
      <div class="live-dot" />
      <span>客户分析 · 运行中</span>
      <div class="live-stat">
        <span>已分析: <strong>{{ customers.length }}家</strong></span>
        <span>平均报告字段覆盖度: <strong>{{ averageReportCoverage() }}%</strong></span>
      </div>
    </div>

    <div class="legacy-page-title">客户分析 · {{ marketLabel }}</div>

    <!-- Loading -->
    <div v-if="loading" class="analysis-state">正在加载客户分析数据...</div>

    <!-- Error -->
    <div v-else-if="error" class="alert-error" role="alert">{{ error }}</div>

    <!-- Empty -->
    <div v-else-if="!customers.length" class="analysis-state">暂无客户数据</div>

    <!-- Customer list -->
    <div v-else class="analysis-list">
      <section
        v-for="customer in customerList"
        :key="customer.client_id || customer.customerId"
        :class="['panel', 'analysis-card', borderForCustomer(customer)]"
      >
        <div class="analysis-card-head">
          <div class="analysis-card-identity">
            <div class="analysis-card-location-row">
              <span class="analysis-location">{{ customerLocation(customer) }}</span>
              <strong>{{ displayName(customer) }}</strong>
              <span class="analysis-time">{{ customerTime(customer) }}</span>
            </div>
          </div>
        </div>

        <!-- B1: customer analysis summary -->
        <div class="analysis-metrics">
          <div>
            <strong :class="completenessPercent(customer).color">{{ completenessPercent(customer).label }}</strong>
            <span>画像完整度</span>
          </div>
          <div>
            <strong :class="customer.budget !== '待确认' ? 'green' : 'muted'">{{ customer.budget }}</strong>
            <span>预算</span>
          </div>
          <div>
            <strong class="blue-text">{{ decisionMakerText(customer) }}</strong>
            <span>关键决策人</span>
          </div>
          <div>
            <strong class="blue-text">{{ decisionCycleText(customer) }}</strong>
            <span>决策周期</span>
          </div>
        </div>

        <!-- E3: inline 画像结构 dual-panel (aligned with prototype) -->
        <div class="profile-grid-inline">
          <div class="profile-grid-inline-title">
            <span>画像结构</span>
            <small>支持手动填写和 AI 转录识别</small>
          </div>
          <div class="profile-structure-grid">
            <div class="profile-structure-panel customer-view-panel">
              <div class="profile-structure-title blue-text">客户视角</div>
              <div class="profile-view-item"><strong>关注点：</strong>{{ customer.profileStructure?.customer_view?.concerns || '待分析' }}</div>
              <div class="profile-view-item"><strong>合作方：</strong>{{ customer.profileStructure?.customer_view?.partners || '待确认' }}</div>
              <div class="profile-view-item"><strong>觉得我们如何：</strong>{{ customer.profileStructure?.customer_view?.impression_of_us || '待评估' }}</div>
            </div>
            <div class="profile-structure-panel latest-news-panel">
              <div class="profile-structure-title blue-text">最新资讯</div>
              <template v-if="customer.profileStructure?.latest_news?.length">
                <div v-for="news in customer.profileStructure?.latest_news" :key="news.title" class="profile-news-item">· {{ news.title }}：{{ news.summary }}</div>
              </template>
              <div v-else class="profile-empty">暂无最新资讯</div>
            </div>
          </div>
        </div>

        <div class="card-actions">

          <button class="btn-xs primary" type="button" @click="openProfile(customer)">
            详细报告
          </button>
        </div>
      </section>
    </div>

    <!-- Detail Report Panel -->
    <div v-if="selectedCustomer" class="legacy-full-panel hard-report-panel">
      <button class="hard-report-close" type="button" aria-label="关闭客户详细报告" title="关闭" @click="closeProfile">×</button>

      <div v-if="reportLoading" class="analysis-state">正在加载报告...</div>

      <div v-else class="legacy-report-wrap hard-report-wrap">
        <!-- C1: Report header aligned with prototype -->
        <div class="legacy-report-head hard-report-head">
          <div>
            <div class="legacy-report-title">
              {{ selectedCustomer.customerName || selectedCustomer.customer_profile?.company_type || '待确认' }} · 客户详细报告
            </div>
            <div class="legacy-report-subtitle">
          {{ hasRealAnalysis ? 'AI 智能分析 · 基于多维度数据生成' : '证据模板分析 · AI 服务暂不可用' }}
            </div>
          </div>
        </div>

        <div v-if="!hasRealAnalysis" class="analysis-source-warning" role="alert">
          当前展示的是基于客户资料和会议证据生成的模板分析；AI 服务恢复后可重新生成增强版报告。
        </div>

        <!-- B2: Profile hero section (aligned with prototype: gradient bg + company info + 4 KPIs) -->
        <section class="report-hero">
          <div class="report-kpis">
            <div>
              <strong class="green">{{ profilePercent(selectedCustomer.core_fields?.candidate_coverage ?? selectedCustomer.customer_profile?.completeness_score) }}</strong>
              <span>报告字段覆盖度</span>
            </div>
            <div>
              <strong class="blue">{{ selectedCustomer.customer_profile?.budget_text || '待确认' }}</strong>
              <span>预算</span>
            </div>
            <div>
              <strong>{{ selectedCustomer.customer_profile?.decision_maker_text || '待确认' }}</strong>
              <span>关键决策人</span>
            </div>
            <div>
              <strong class="green">{{ selectedCustomer.customer_profile?.decision_cycle_text || '待确认' }}</strong>
              <span>决策周期</span>
            </div>
          </div>
        </section>

        <section class="report-source-strip" aria-label="本次报告数据来源">
          <span>本次报告数据来源</span>
          <b>客户来信 {{ reportSourceCounts(selectedCustomer).inbound_email_count }} 封</b>
          <b>我方邮件 {{ reportSourceCounts(selectedCustomer).outbound_email_count }} 封</b>
          <b>销售手工记录 {{ reportSourceCounts(selectedCustomer).manual_note_count }} 条</b>
          <b>会议摘要 {{ reportSourceCounts(selectedCustomer).meeting_count || 0 }} 条</b>
          <b>知识库资料 {{ reportSourceCounts(selectedCustomer).knowledge_count || 0 }} 条</b>
          <b>联网资料 {{ reportSourceCounts(selectedCustomer).web_count }} 条</b>
        </section>

        <!-- Sales-facing report: keep the card layout, but render every design field. -->
        <div class="hard-report-modules">
          <section
            v-for="module in narrativeReportSections(selectedCustomer)"
            :key="module.key"
            class="report-section report-module-section"
            >
            <div class="report-section-title">{{ module.title }}</div>
            <div class="report-module-fields">
              <div v-for="field in module.fields" :key="field.key" class="report-module-block">
                <div class="report-point-label">{{ field.label }}</div>
                <div :class="['report-module-detail', { missing: field.value === MISSING_REPORT_INFO }]">
                  {{ field.value }}
                </div>
              </div>
            </div>
          </section>
        </div>

        <!-- Sales guide: MEDDPICC dimensions -->
        <section class="report-section sales-guide-section">
          <div class="report-section-title">销售指引</div>
          <p class="sales-guide-subtitle">基于本次报告生成；未确认事实会保留为销售追问，不会伪造成已确认信息。</p>
          <div class="sales-guide-grid">
            <details v-for="dim in salesGuideDimensions(selectedCustomer)" :key="dim.code" class="sales-guide-card">
              <summary>
                <div class="sales-guide-card-head">
                  <span>{{ dim.label }}</span>
                  <em>{{ dim.status === 'confirmed' ? '已确认' : dim.status === 'partial' ? '待补全' : '待确认' }}</em>
                </div>
                <p>{{ dim.summary }}</p>
                <b>点击展开更多销售分析</b>
              </summary>
              <div class="sales-guide-detail">
                <div><strong>判断依据：</strong>{{ dim.judgement }}</div>
                <div>
                  <strong>销售追问：</strong>
                  <ul><li v-for="question in dim.questions" :key="question">{{ question }}</li></ul>
                </div>
                <div>
                  <strong>下一步动作：</strong>
                  <ul><li v-for="action in dim.actions" :key="action">{{ action }}</li></ul>
                </div>
                <div v-if="dim.talkTrack.length">
                  <strong>沟通话术：</strong>
                  <ul><li v-for="line in dim.talkTrack" :key="line">{{ line }}</li></ul>
                </div>
                <div v-if="dim.emailDraft" class="sales-guide-email">
                  <strong>跟进邮件：</strong>
                  <span>主题：{{ dim.emailDraft.subject }}</span>
                  <p>{{ dim.emailDraft.body }}</p>
                </div>
                <div class="sales-guide-risk"><strong>风险：</strong>{{ dim.risk }}</div>
              </div>
            </details>
            <div v-if="!salesGuideDimensions(selectedCustomer).length" class="sales-guide-empty">
              暂无 MEDDPICC 数据
            </div>
          </div>
        </section>

      </div>
    </div>
  </div>
</template>

<style scoped>
.legacy-analysis,
.legacy-analysis button,
.legacy-analysis input,
.legacy-analysis select,
.legacy-analysis textarea {
  font-family: var(--font-sans);
}

.analysis-state {
  padding: 40px 16px;
  color: var(--text-muted);
  text-align: center;
}

.analysis-source-warning {
  margin: 12px 0;
  padding: 10px 12px;
  border: 1px solid #f2c56b;
  border-radius: var(--radius-sm);
  color: #7a4b00;
  background: #fff8e8;
  font-size: var(--font-small);
  line-height: var(--line-normal);
}

.analysis-card {
  padding: 16px;
}

.analysis-card-head {
  align-items: flex-start;
}

.analysis-card-identity {
  display: flex;
  flex: 1 1 auto;
  min-width: 0;
}

.analysis-card-location-row {
  display: flex;
  min-width: 0;
  flex-wrap: wrap;
  gap: 8px 12px;
  align-items: baseline;
}

.analysis-card-location-row strong {
  overflow-wrap: anywhere;
  color: var(--text-main);
  font-size: var(--font-subtitle);
  line-height: var(--line-compact);
}

.analysis-location,
.analysis-time {
  color: var(--text-muted);
  font-size: var(--font-small);
  line-height: var(--line-compact);
}

.analysis-metrics {
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin: 14px 0;
}

.analysis-metrics > div {
  display: grid;
  min-height: 62px;
  padding: 9px 8px;
  align-content: center;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
}

.analysis-metrics strong {
  overflow-wrap: anywhere;
  font-size: var(--font-body);
  line-height: var(--line-compact);
}

.analysis-metrics span {
  margin-top: 5px;
  color: var(--text-muted);
  font-size: var(--font-small);
}

.profile-grid-inline {
  margin-top: 2px;
}

.profile-structure-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.profile-grid-inline-title {
  display: flex;
  gap: 8px;
  align-items: baseline;
  margin-bottom: 8px;
  font-size: var(--font-body);
  font-weight: 700;
}

.profile-grid-inline-title small,
.profile-empty {
  color: var(--text-muted);
  font-size: var(--font-small);
  font-weight: 400;
}

.profile-structure-panel {
  min-width: 0;
  padding: 12px 14px;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  background: #fff;
}

.customer-view-panel {
  border-left: 3px solid #2864ef;
}

.latest-news-panel {
  border-left: 3px solid #2864ef;
}

.profile-structure-title {
  margin-bottom: 8px;
  font-weight: 700;
}

.profile-view-item,
.profile-news-item {
  font-size: var(--font-body);
  line-height: var(--line-body);
}

.hard-report-panel {
  position: fixed;
  inset: 0;
  z-index: 200;
  overflow-y: auto;
  background: #fff;
  color: #152238;
}

.hard-report-close {
  position: fixed;
  top: 28px;
  right: 28px;
  z-index: 3;
  display: grid;
  width: 38px;
  height: 38px;
  place-items: center;
  border: 1px solid #d8e0ea;
  border-radius: 8px;
  background: #fff;
  color: #152238;
  font-size: 24px;
  line-height: 1;
  box-shadow: 0 3px 12px rgba(30, 55, 90, .08);
  cursor: pointer;
}

.hard-report-wrap {
  width: min(1440px, calc(100% - 80px));
  margin: 0 auto;
  padding: 32px 0 60px;
}

.hard-report-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 20px;
  padding: 0 52px 16px 0;
  border-bottom: 1px solid #d7e0ea;
}

.hard-report-head > div {
  flex: 1;
}

.hard-report-head .legacy-report-title {
  font-size: 23px;
  line-height: 1.3;
  font-weight: 700;
  color: #152238;
}

.hard-report-head .legacy-report-subtitle {
  margin-top: 5px;
  font-size: 13px;
  color: #718096;
}

.hard-report-wrap .report-hero {
  margin-bottom: 20px;
  padding: 16px 18px 18px;
  background: #f8fafc;
  border: 1px solid #d8e1eb;
  border-radius: 8px;
}

.hard-report-wrap .report-hero::before {
  content: '客户画像';
  display: block;
  margin-bottom: 12px;
  font-size: 16px;
  font-weight: 700;
  color: #152238;
}

.hard-report-wrap .report-kpis {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.hard-report-wrap .report-kpis > div {
  min-height: 82px;
  padding: 10px;
  border: 1px solid #e0e7ef;
  border-radius: 8px;
  background: #fff;
  text-align: center;
}

.hard-report-wrap .report-kpis strong {
  display: block;
  color: #152238;
  font-size: 22px;
  font-weight: 800;
}

.hard-report-wrap .report-kpis span {
  display: block;
  margin-top: 5px;
  color: #718096;
  font-size: 11px;
}

.hard-report-wrap .core-fields-section {
  padding: 18px 0 4px;
  border-top: 1px solid #e0e7ef;
}

.hard-report-wrap .report-source-strip {
  display: flex;
  min-height: 42px;
  align-items: center;
  gap: 18px;
  padding: 10px 0;
  border-bottom: 1px solid #e0e7ef;
  color: #52647a;
  font-size: 12px;
  flex-wrap: wrap;
}

.hard-report-wrap .report-source-strip span {
  color: #26384c;
  font-weight: 700;
}

.hard-report-wrap .report-source-strip b {
  font-weight: 500;
}

.hard-report-wrap .core-field-source {
  display: block;
  margin-top: 4px;
  color: #718096;
  font-size: 11px;
}

.hard-report-wrap .core-fields-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.hard-report-wrap .core-fields-summary {
  margin: -7px 0 14px;
  color: #52647a;
  font-size: 12px;
}

.hard-report-wrap .core-field-groups {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px 22px;
}

.hard-report-wrap .core-field-group {
  min-width: 0;
}

.hard-report-wrap .core-field-group h3 {
  margin: 0;
  padding: 8px 10px;
  border-left: 3px solid #2864ef;
  color: #152238;
  background: #f3f6fa;
  font-size: 13px;
}

.hard-report-wrap .core-field-row {
  padding: 10px;
  border-bottom: 1px solid #e7edf4;
}

.hard-report-wrap .core-field-label {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  color: #26374d;
  font-size: 12px;
  font-weight: 700;
}

.hard-report-wrap .core-field-label em {
  color: #718096;
  font-size: 11px;
  font-style: normal;
  font-weight: 500;
}

.hard-report-wrap .core-field-label em.candidate {
  color: #8a5700;
}

.hard-report-wrap .core-field-value {
  margin-top: 5px;
  color: #52647a;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-line;
  overflow-wrap: anywhere;
}

.hard-report-wrap .core-field-value.missing {
  color: #8a96a5;
}

.hard-report-wrap .narrative-report-copy {
  min-height: 44px;
}

.hard-report-wrap .hard-report-modules {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.hard-report-wrap .report-module-section {
  margin: 0;
  padding: 16px 18px 18px;
  border: 1px solid #e0e7ef;
  border-left: 4px solid #2864ef;
  border-radius: 8px;
  background: #f8fafc;
}

.hard-report-wrap .report-module-section:nth-child(2) {
  border-left-color: #2864ef;
}

.hard-report-wrap .report-module-section:nth-child(3) {
  border-left-color: #2864ef;
}

.hard-report-wrap .report-module-section:nth-child(4) {
  border-left-color: #2864ef;
}

.hard-report-wrap .report-section-title {
  margin-bottom: 12px;
  color: #152238;
  font-size: 17px;
  font-weight: 700;
}

.hard-report-wrap .report-section-title span {
  margin-left: 10px;
  color: #2864ef;
  font-size: 11px;
  font-weight: 600;
}

.hard-report-wrap .report-module-block {
  min-height: 74px;
  padding: 12px 14px;
  border: 1px solid #e0e7ef;
  border-radius: 8px;
  background: #fff;
}

.hard-report-wrap .report-module-fields {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0;
}

.hard-report-wrap .report-points-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.hard-report-wrap .report-point {
  min-width: 0;
  padding: 12px 14px;
  border: 1px solid #e0e7ef;
  border-radius: 8px;
  background: #fff;
}

.hard-report-wrap .report-point-label {
  margin-bottom: 7px;
  color: #152238;
  font-size: 13px;
  font-weight: 700;
}

.hard-report-wrap .report-module-detail.missing {
  color: #718096;
}

.hard-report-wrap .report-module-detail {
  color: #52647a;
  font-size: 13px;
  line-height: 1.75;
  white-space: pre-line;
  overflow-wrap: anywhere;
}

.hard-report-wrap .report-section:not(.report-module-section) {
  margin-top: 22px;
}

.hard-report-wrap .sales-guide-section {
  padding: 16px 18px 18px;
  border: 1px solid #e0e7ef;
  border-left: 4px solid #2864ef;
  border-radius: 8px;
  background: #f8fafc;
}

.hard-report-wrap .sales-guide-card p,
.hard-report-wrap .sales-guide-detail {
  font-size: 13px;
}

.hard-report-wrap .sales-guide-detail > div + div {
  margin-top: 12px;
}

.hard-report-wrap .sales-guide-detail ul {
  margin: 6px 0 0;
  padding-left: 20px;
}

.hard-report-wrap .sales-guide-detail li + li {
  margin-top: 4px;
}

.hard-report-wrap .sales-guide-email span,
.hard-report-wrap .sales-guide-email p {
  display: block;
  margin: 6px 0 0;
  white-space: pre-line;
}

.hard-report-wrap .sales-guide-card summary b,
.hard-report-wrap .sales-guide-card-head em {
  font-size: 11px;
}

.sales-guide-empty {
  grid-column: 1 / -1;
  padding: 20px;
  color: var(--text-muted);
  text-align: center;
}

.analysis-run-button {
  border: 1px solid #2864ef;
  background: #eef4ff;
  color: #1e55c7;
}

.analysis-run-button:disabled {
  cursor: wait;
  opacity: .65;
}

.analysis-run-message {
  color: #64748b;
  font-size: 12px;
}

.analysis-run-message.completed {
  color: #16834a;
}

.analysis-run-message.failed,
.analysis-run-message.cancelled {
  color: #c43d3d;
}

@media (max-width: 760px) {
  .hard-report-wrap .core-field-groups { grid-template-columns: 1fr; }
  .hard-report-wrap .core-fields-head { align-items: stretch; flex-direction: column; }
  .hard-report-wrap { width: calc(100% - 28px); padding-top: 22px; }
  .hard-report-close { top: 12px; right: 12px; }
  .hard-report-wrap .report-kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .analysis-card-head,
  .profile-grid-inline-title { align-items: flex-start; }
  .analysis-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .profile-grid-inline-title { flex-direction: column; gap: 2px; }
  .profile-structure-grid { grid-template-columns: 1fr; }
  .hard-report-wrap .report-points-grid { grid-template-columns: 1fr; }
  .hard-report-wrap .report-module-section { padding: 14px; }
}
</style>
