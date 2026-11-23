import { api, toApiError } from '../shared/api/client'
import { createIdempotencyKey } from '../shared/api/idempotency'
import { normalizeCurrentAnalysisReport } from './analysisReportAdapter'

/** Customer profile as returned by the v3.6 API. */
export interface CustomerProfile {
  company_id: string
  company_type: string | null
  region_text: string | null
  employee_scale: string | null
  business_model: string | null
  esim_scenario: string | null
  coverage: string | null
  estimated_usage: string | null
  integration: string | null
  compliance: string | null
  budget_text: string | null
  decision_maker_text: string | null
  decision_maker_contact_id: string | null
  decision_cycle_text: string | null
  completeness_score: number
  missing_fields: string[]
  extra_payload: Record<string, unknown>
  field_provenance: Record<string, unknown>
  source_summary: string | null
  last_enriched_at: string | null
  profile_version: number
  updated_by: string | null
  updated_at: string
  company_summary?: string | null
  geography_note?: string | null
}

/** Single MEDDPICC dimension. */
export interface MeddpiccDimension {
  company_id: string
  dimension_code: string
  level: string | null
  status: 'unknown' | 'partial' | 'confirmed' | 'rejected'
  summary: string | null
  payload: Record<string, unknown>
  evidence_refs: Record<string, unknown>[]
  version: number
  updated_at: string
}

export interface MeddpiccResponse {
  company_id: string
  dimensions: MeddpiccDimension[]
}

/** Analysis run. */
export interface AnalysisRun {
  run_id: string
  company_id: string
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'
  current_job_id: string
  report_id: string | null
  version: number
  error_code: string | null
  error_message: string | null
  report_type?: string
  trigger_type?: string
  research_mode?: 'initial_external' | 'internal_only'
  external_research_allowed?: boolean
  trigger_context?: Record<string, unknown>
}

export interface AnalysisRunAsync {
  resource_type: 'analysis_run'
  resource_id: string
  job: {
    job_id: string
    status: string
    status_url: string
    events_url: string
  }
}

/** Analysis report. */
export interface AnalysisReport {
  report_id: string
  company_id: string
  analysis_run_id: string
  report_type: string
  version_no: number
  schema_version: string
  prompt_version: string | null
  generation_attempts: number
  research_meta: Record<string, unknown>
  header: Record<string, unknown>
  summary: string
  health_grade: string | null
  intention_level: string | null
  confidence: number | null
  section_confidence: Record<string, number>
  low_confidence_sections: string[]
  data_sources: string[]
  evidence_refs: Record<string, unknown>[]
  evidence_summary: EvidenceSummary
  profile_snapshot: Record<string, unknown>
  meddpicc_snapshot: Record<string, unknown>
  icp_snapshot: Record<string, unknown>
  scale_snapshot: Record<string, unknown>
  market: Record<string, unknown>
  company: Record<string, unknown>
  competitor: Record<string, unknown>
  pain: Record<string, unknown>
  product: Record<string, unknown>
  modules: { module_name: string; sections: string[] }[]
  sales_guide: Record<string, unknown>
  generated_by: string
  model_name: string | null
  content_source: string
  generated_at: string
  superseded_at: string | null
}

/** Analysis suggestion. */
export interface AnalysisSuggestion {
  suggestion_id: string
  company_id: string
  report_id: string
  target_type: string
  dimension_code: string | null
  target_path: string
  target_version_at_creation: number
  current_value_snapshot: unknown
  proposed_value: unknown
  evidence_refs: Record<string, unknown>[]
  confidence: number | null
  status: 'pending' | 'accepted' | 'rejected'
  summary: string
  version: number
  created_at: string
}

export interface EvidenceSummary {
  total_count: number
  email_count: number
  inbound_email_count: number
  outbound_email_count: number
  manual_note_count: number
  meeting_count?: number
  web_count: number
  knowledge_count?: number
  exa_count?: number
}

export interface CoreFieldCatalog {
  version: string
  profile_field_count: number
  core_field_count: number
  groups: {
    id: string
    label: string
    fields: {
      id: string
      label: string
      target_type: 'profile' | 'meddpicc'
      collection_method: 'public_or_internal' | 'sales_confirmation'
      missing_guidance: string
    }[]
  }[]
}

export interface CoreFieldItem {
  group_id: string
  group_label: string
  field_id: string
  label: string
  target_type: 'profile' | 'meddpicc'
  value: unknown
  status: string
  candidate: AnalysisSuggestion | null
  provenance: Record<string, unknown>
  collection_method?: 'public_or_internal' | 'sales_confirmation'
  missing_guidance?: string
}

export interface CoreFieldsResponse {
  catalog_version: string
  company_id: string
  confirmed_profile_completeness: number
  candidate_coverage: number
  source_counts: EvidenceSummary
  fields: CoreFieldItem[]
}

/** ICP score for a company. */
export interface IcpScore {
  total_score: number
  grade: string
  dimension_scores: Record<string, number>
  change_reason: string | null
}

/** Envelope wrapper used across all v3.6 responses. */
export interface Envelope<T> {
  request_id: string
  data: T
  page?: { next_cursor: string | null; has_more: boolean }
}

export interface ListResult<T> {
  items: T[]
  next_cursor: string | null
  has_more: boolean
}

// ---------------------------------------------------------------------------
// v3.6 Customer Analysis API
// ---------------------------------------------------------------------------

export const analysisApi = {
  async getFieldCatalog(): Promise<CoreFieldCatalog> {
    const res = await api.get<Envelope<CoreFieldCatalog>>('/customer-analysis/field-catalog')
    return res.data.data
  },

  async getCoreFields(companyId: string): Promise<CoreFieldsResponse> {
    const res = await api.get<Envelope<CoreFieldsResponse>>(
      `/companies/${encodeURIComponent(companyId)}/core-fields`,
    )
    return res.data.data
  },

  // ---- Profile ----

  /** GET /api/v1/companies/{id}/profile */
  async getProfile(companyId: string): Promise<{ data: CustomerProfile; etag: string }> {
    const res = await api.get<Envelope<CustomerProfile>>(`/companies/${encodeURIComponent(companyId)}/profile`)
    return { data: res.data.data, etag: res.headers['etag'] as string }
  },

  /** PATCH /api/v1/companies/{id}/profile */
  async updateProfile(
    companyId: string,
    changes: { company_summary?: string; business_model?: string; geography_note?: string },
    expectedVersion: number,
  ): Promise<{ data: CustomerProfile; etag: string }> {
    const res = await api.patch<Envelope<CustomerProfile>>(
      `/companies/${encodeURIComponent(companyId)}/profile`,
      changes,
      {
        headers: {
          'If-Match': `"${expectedVersion}"`,
          'Idempotency-Key': createIdempotencyKey(),
        },
      },
    )
    return { data: res.data.data, etag: res.headers['etag'] as string }
  },

  // ---- MEDDPICC ----

  /** GET /api/v1/companies/{id}/meddpicc */
  async getMeddpicc(companyId: string): Promise<MeddpiccResponse> {
    const res = await api.get<Envelope<MeddpiccResponse>>(`/companies/${encodeURIComponent(companyId)}/meddpicc`)
    return res.data.data
  },

  /** PATCH /api/v1/companies/{id}/meddpicc/{dimension} */
  async updateMeddpicc(
    companyId: string,
    dimensionCode: string,
    payload: { status: string; summary?: string; payload?: Record<string, unknown> },
    expectedVersion: number,
  ): Promise<MeddpiccResponse> {
    const res = await api.patch<Envelope<MeddpiccResponse>>(
      `/companies/${encodeURIComponent(companyId)}/meddpicc/${encodeURIComponent(dimensionCode)}`,
      payload,
      {
        headers: {
          'If-Match': `"${expectedVersion}"`,
          'Idempotency-Key': createIdempotencyKey(),
        },
      },
    )
    return res.data.data
  },

  // ---- Analysis Runs ----

  /** POST /api/v1/companies/{id}/analysis-runs */
  async createAnalysisRun(
    companyId: string,
    opts: { report_type?: string; force_refresh?: boolean; trigger_type?: string } = {},
  ): Promise<AnalysisRunAsync> {
    const res = await api.post<Envelope<AnalysisRunAsync>>(
      `/companies/${encodeURIComponent(companyId)}/analysis-runs`,
      {
        report_type: opts.report_type ?? 'customer_analysis',
        force_refresh: opts.force_refresh ?? false,
        trigger_type: opts.trigger_type ?? 'manual',
      },
      {
        headers: { 'Idempotency-Key': createIdempotencyKey() },
        timeout: 30_000,
      },
    )
    return res.data.data
  },

  /** GET /api/v1/analysis-runs/{run_id} */
  async getAnalysisRun(runId: string): Promise<{ data: AnalysisRun; etag: string }> {
    const res = await api.get<Envelope<AnalysisRun>>(`/analysis-runs/${encodeURIComponent(runId)}`)
    return { data: res.data.data, etag: res.headers['etag'] as string }
  },

  /** POST /api/v1/analysis-runs/{run_id}:retry */
  async retryAnalysisRun(runId: string, expectedVersion: number): Promise<AnalysisRunAsync> {
    const res = await api.post<Envelope<AnalysisRunAsync>>(
      `/analysis-runs/${encodeURIComponent(runId)}:retry`,
      {},
      {
        headers: {
          'If-Match': `"${expectedVersion}"`,
          'Idempotency-Key': createIdempotencyKey(),
        },
      },
    )
    return res.data.data
  },

  /** POST /api/v1/analysis-runs/{run_id}:cancel */
  async cancelAnalysisRun(runId: string, expectedVersion: number): Promise<AnalysisRunAsync> {
    const res = await api.post<Envelope<AnalysisRunAsync>>(
      `/analysis-runs/${encodeURIComponent(runId)}:cancel`,
      {},
      {
        headers: {
          'If-Match': `"${expectedVersion}"`,
          'Idempotency-Key': createIdempotencyKey(),
        },
      },
    )
    return res.data.data
  },

  // ---- Reports ----

  /** GET /api/v1/companies/{id}/analysis-reports/current */
  async getCurrentReport(companyId: string): Promise<AnalysisReport> {
    const res = await api.get<Envelope<AnalysisReport>>(
      `/companies/${encodeURIComponent(companyId)}/analysis-reports/current`,
    )
    return res.data.data
  },

  /** GET /api/v1/companies/{id}/analysis-reports */
  async listReports(
    companyId: string,
    cursor?: string,
    limit = 20,
  ): Promise<ListResult<AnalysisReport>> {
    const params: Record<string, string> = { limit: String(limit) }
    if (cursor) params.cursor = cursor
    const res = await api.get<Envelope<AnalysisReport[]>>(
      `/companies/${encodeURIComponent(companyId)}/analysis-reports`,
      { params },
    )
    return {
      items: res.data.data,
      next_cursor: res.data.page?.next_cursor ?? null,
      has_more: res.data.page?.has_more ?? false,
    }
  },

  /** GET /api/v1/analysis-reports/{report_id} */
  async getReport(reportId: string): Promise<AnalysisReport> {
    const res = await api.get<Envelope<AnalysisReport>>(`/analysis-reports/${encodeURIComponent(reportId)}`)
    return res.data.data
  },

  // ---- Suggestions ----

  /** GET /api/v1/companies/{id}/analysis-suggestions */
  async listSuggestions(companyId: string): Promise<AnalysisSuggestion[]> {
    const res = await api.get<Envelope<AnalysisSuggestion[]>>(
      `/companies/${encodeURIComponent(companyId)}/analysis-suggestions`,
    )
    return res.data.data
  },

  /** POST /api/v1/analysis-suggestions/{id}:accept */
  async acceptSuggestion(suggestionId: string, expectedVersion: number): Promise<AnalysisSuggestion> {
    const res = await api.post<Envelope<AnalysisSuggestion>>(
      `/analysis-suggestions/${encodeURIComponent(suggestionId)}:accept`,
      {},
      {
        headers: {
          'If-Match': `"${expectedVersion}"`,
          'Idempotency-Key': createIdempotencyKey(),
        },
      },
    )
    return res.data.data
  },

  /** POST /api/v1/analysis-suggestions/{id}:reject */
  async rejectSuggestion(suggestionId: string, expectedVersion: number): Promise<AnalysisSuggestion> {
    const res = await api.post<Envelope<AnalysisSuggestion>>(
      `/analysis-suggestions/${encodeURIComponent(suggestionId)}:reject`,
      {},
      {
        headers: {
          'If-Match': `"${expectedVersion}"`,
          'Idempotency-Key': createIdempotencyKey(),
        },
      },
    )
    return res.data.data
  },

  async reviewSuggestionsBatch(
    companyId: string,
    profileVersion: number,
    items: {
      suggestion_id: string
      suggestion_version: number
      action: 'accept' | 'keep_original' | 'edit'
      edited_value?: unknown
      review_note?: string
    }[],
  ): Promise<{ profile: CustomerProfile; suggestions: AnalysisSuggestion[] }> {
    const res = await api.post<Envelope<{ profile: CustomerProfile; suggestions: AnalysisSuggestion[] }>>(
      `/companies/${encodeURIComponent(companyId)}/analysis-suggestions:review-batch`,
      { profile_version: profileVersion, items },
      { headers: { 'Idempotency-Key': createIdempotencyKey() } },
    )
    return res.data.data
  },

  // ---- Legacy compat (used by existing frontend views) ----
  // These methods call legacy backend routes that are kept for backward compat.

  /** @deprecated Use listReports + getProfile instead */
  async legacyAnalysisList(page = 1, pageSize = 20) {
    const { data } = await api.get('/api/analysis/list', { params: { page, pageSize } }) as any;
    const list = data?.list || data?.items || [];
    return { items: list, total: data?.total || list.length, page, page_size: pageSize };
  },

  /** @deprecated Use listReports + getProfile instead */
  async legacyCustomerList(page = 1, pageSize = 20) {
    const { data } = await api.get('/api/customers/analysis/list', { params: { page, pageSize } }) as any;
    // Legacy routes may be returned either directly or inside the standard
    // envelope. Normalize both shapes so the analysis page never treats a
    // valid response as an empty customer list.
    const payload = data?.data && typeof data.data === 'object' ? data.data : data;
    const list = Array.isArray(payload) ? payload : (payload?.list || payload?.items || []);
    return { items: Array.isArray(list) ? list : [], total: Number(payload?.total || list.length || 0), page, page_size: pageSize };
  },

  /** @deprecated Use getProfile + getMeddpicc + getCurrentReport instead */
  async legacyCustomer360(clientId: string): Promise<unknown> {
    // Migrated: fetch all v3.6 data for a customer and return combined view
    try {
      const [profile, meddpicc, report, coreFields, fieldCatalog] = await Promise.all([
        this.getProfile(clientId).catch(() => null),
        this.getMeddpicc(clientId).catch(() => null),
        this.getCurrentReport(clientId).catch(() => null),
        this.getCoreFields(clientId).catch(() => null),
        this.getFieldCatalog().catch(() => null),
      ]);
      return {
        company_id: clientId,
        profile: profile?.data || null,
        meddpicc,
        analysis_report: normalizeCurrentAnalysisReport(report),
        core_fields: coreFields,
        field_catalog: fieldCatalog,
      };
    } catch {
      return { company_id: clientId, error: 'Failed to load customer data' };
    }
  },
}
