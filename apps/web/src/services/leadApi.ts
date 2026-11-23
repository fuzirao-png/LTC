import { config } from '../config/runtime';
import { createHttpClient } from './http';
import { createIdempotencyKey } from '../shared/api/idempotency';
import { INDUSTRY_LABELS, REGION_LABELS } from '../shared/utils/labels';

const http = createHttpClient(config.leadApiBase);

export const DEFAULT_LEAD_SEARCH_TARGET = 500;
export const MAX_LEAD_SEARCH_RESULTS = 2000;

export interface EmailAutomationRun {
  runId: string;
  startedAt?: string | null;
  completedAt?: string | null;
  status: string;
  candidates: number;
  sent: number;
  failed: number;
  skipped: number;
  failureSummary?: { total: number; byCode: Record<string, number>; unavailable?: boolean };
  deliverySummary?: {
    replied?: number;
    hard_bounce?: number;
    soft_bounce?: number;
    delivered_confirmed?: number;
  };
}

export interface EmailAutomationFailure { phase: string; code: string; message: string; hint?: string; attempts: number; companyId?: string | null; companyName?: string | null; contactId?: string | null; contactName?: string | null; recipientEmail?: string | null; }

export interface EmailAutomationReply {
  emailId: string;
  companyId?: string | null;
  companyName?: string | null;
  contactId?: string | null;
  contactName?: string | null;
  emailAddress?: string | null;
  recipientEmail?: string | null;
  subject: string;
  content: string;
  receivedAt?: string | null;
  analysis: {
    intentLevel?: string | null;
    nextAction?: string | null;
    confidence?: number | null;
    evidenceQuote?: string | null;
  };
}

// ---- v3.6 Backend-aligned types ----

export interface LeadCandidate {
  candidate_id: string;
  search_run_id?: string;
  company_name: string;
  website?: string;
  industry_tag?: string;
  region?: string;
  country?: string;
  city?: string;
  icp_score?: number | {
    D1?: number;
    D2?: number;
    D3?: number;
    D4?: number;
    total?: number;
    grade?: string;
    explanations?: {
      D1?: string;
      D2?: string;
      D3?: string;
      D4?: string;
    };
  };
  icp_grade?: string;
  icp_dimension_summary?: string;
  company_intro?: string;
  industry_code?: string;
  country_code?: string;
  region_code?: string;
  employee_count?: number;
  source_channel?: string;
  status?: string;
  version?: number;
  customer_size_grade?: 'A' | 'B' | 'C';
  promoted_company_id?: string;
  promoted_lead_id?: string;
  contacts?: LeadContact[];
}

export interface LeadContact {
  candidate_contact_id?: string | null;
  full_name?: string;
  title?: string;
  department?: string;
  relationship_role?: string;
  priority?: string;
  email?: string;
  email_status?: string | null;
  email_type?: string | null;
  email_score?: number | null;
  phone?: string;
  linkedin_url?: string;
}

export interface LeadSearchRun {
  search_run_id: string;
  query_text: string;
  search_mode: string;
  status: string;
  target_count?: number;
  candidate_count?: number;
  candidates_count?: number;
  enriched_count?: number;
  scored_count?: number;
  progress_percent?: number;
  progress_message?: string | null;
  error_message?: string | null;
  created_at?: string;
  started_at?: string;
  completed_at?: string;
}

export interface LeadSearchRunCreate {
  query_text: string;
  search_mode?: 'company_only' | 'contact_only' | 'both';
  target_count?: number;
  scene_code?: 'S1' | 'S2' | 'S3';
}

/** Backend envelope */
export interface Envelope<T> {
  request_id: string;
  data: T;
  page?: { next_cursor: string | null; has_more: boolean };
}

// ---- Legacy UI types (kept for backward compat) ----

export interface AnalysisCompany {
  company_id?: string;
  validation_company_id?: string;
  company_name: string;
  website?: string;
  industry_tag?: string;
  region?: string;
  country?: string;
  city?: string;
  icp_score?: number | {
    D1?: number;
    D2?: number;
    D3?: number;
    D4?: number;
    total?: number;
    grade?: string;
    explanations?: {
      D1?: string;
      D2?: string;
      D3?: string;
      D4?: string;
    };
  };
  icp_grade?: string;
  icp_breakdown?: { d1?: number; d2?: number; d3?: number; d4?: number };
  d1_score_explanation?: string;
  d2_score_explanation?: string;
  d3_score_explanation?: string;
  d4_score_explanation?: string;
  icp_dimension_summary?: string;
  name?: string;
  company?: string;
  id?: string;
  company_intro?: string;
  icpGrade?: string;
  icpScore?: number;
  contacts?: LeadContact[];
  employee_count?: number;
  source_channel?: string;
  candidate_version?: number;
  candidate_status?: string;
  customer_size_grade?: 'A' | 'B' | 'C';
  promoted_company_id?: string;
  promoted_lead_id?: string;
}

export interface LeadSearchPayload {
  user_input: string;
  search_provider?: string;
  search_mode?: 'web' | 'company' | 'both';
  limit?: number;
  env_path?: string;
  include_trace?: boolean;
  route_context?: Record<string, unknown>;
}

export interface LeadSearchTrace {
  stage?: string;
  title?: string;
  detail?: string;
  text?: string;
  progress_percent?: number;
  completed_count?: number;
  target_count?: number;
  results?: Array<{ title?: string; url?: string; name?: string }>;
}

export interface LeadProviderTrace {
  provider_code: string;
  operation: string;
  status: string;
  result_count: number;
  error_message?: string | null;
}

export interface LeadSearchReply {
  reply?: string;
  leads?: AnalysisCompany[];
  results?: AnalysisCompany[];
  items?: AnalysisCompany[];
  accepted_rows?: AnalysisCompany[];
  updated_rows?: AnalysisCompany[];
  requires_user_input?: boolean;
  missing_fields?: string[];
  payload?: Record<string, unknown>;
  action?: string;
  next_step?: string;
  decision_trace?: LeadSearchTrace[];
  [key: string]: unknown;
}

export type LeadSearchEvent =
  | { type: 'trace'; data: LeadSearchTrace }
  | { type: 'reply'; data: LeadSearchReply }
  | { type: 'status'; data: LeadSearchRun };

// ---- Helpers ----

function normalizeSearchRows(data: LeadSearchReply): AnalysisCompany[] {
  const rows = data.leads || data.results || data.items || data.accepted_rows || data.updated_rows || [];
  return Array.isArray(rows) ? rows : [];
}

function candidateToAnalysisCompany(c: LeadCandidate): AnalysisCompany {
  const score = typeof c.icp_score === 'object' && c.icp_score !== null
    ? c.icp_score
    : undefined;
  const rawIndustry = c.industry_code || c.industry_tag || '';
  const rawRegion = c.region_code || c.region || '';
  return {
    company_id: c.candidate_id,
    validation_company_id: c.candidate_id,
    company_name: c.company_name,
    website: c.website,
    industry_tag: INDUSTRY_LABELS[rawIndustry] || rawIndustry,
    region: REGION_LABELS[rawRegion] || rawRegion,
    country: c.country_code || c.country,
    city: c.city,
    icp_score: score?.total ?? (typeof c.icp_score === 'number' ? c.icp_score : undefined),
    icp_grade: c.icp_grade || score?.grade,
    icp_breakdown: score ? { d1: score.D1, d2: score.D2, d3: score.D3, d4: score.D4 } : undefined,
    d1_score_explanation: score?.explanations?.D1,
    d2_score_explanation: score?.explanations?.D2,
    d3_score_explanation: score?.explanations?.D3,
    d4_score_explanation: score?.explanations?.D4,
    icp_dimension_summary: c.icp_dimension_summary,
    company_intro: c.company_intro,
    contacts: Array.isArray(c.contacts) ? c.contacts : [],
    employee_count: c.employee_count,
    source_channel: c.source_channel,
    candidate_version: c.version,
    candidate_status: c.status,
    customer_size_grade: c.customer_size_grade,
    promoted_company_id: c.promoted_company_id,
    promoted_lead_id: c.promoted_lead_id,
  };
}

const ACTIVE_SEARCH_STORAGE_KEY = 'ltc.active-lead-search.v1';
const CURRENT_USER_STORAGE_KEY = 'ltc.current-user-id';
const TERMINAL_SEARCH_STATUSES = new Set(['completed', 'partial', 'failed', 'cancelled']);

export interface ActiveLeadSearch {
  searchRunId: string;
  jobId?: string;
  query: string;
  limit: number;
}

function wait(ms: number) {
  return new Promise<void>((resolve) => window.setTimeout(resolve, ms));
}

function normalizeSearchTarget(value?: number) {
  const target = Number.isFinite(value) ? Math.floor(Number(value)) : DEFAULT_LEAD_SEARCH_TARGET;
  return Math.min(Math.max(target, 1), MAX_LEAD_SEARCH_RESULTS);
}

function saveActiveSearch(search: ActiveLeadSearch | null) {
  if (typeof window === 'undefined') return;
  const key = activeSearchStorageKey();
  if (search) window.localStorage.setItem(key, JSON.stringify(search));
  else window.localStorage.removeItem(key);
}

function readActiveSearch(): ActiveLeadSearch | null {
  if (typeof window === 'undefined') return null;
  const key = activeSearchStorageKey();
  try {
    const parsed = JSON.parse(window.localStorage.getItem(key) || 'null');
    return parsed?.searchRunId
      ? { ...parsed, limit: normalizeSearchTarget(Number(parsed.limit)) } as ActiveLeadSearch
      : null;
  } catch {
    window.localStorage.removeItem(key);
    return null;
  }
}

function activeSearchStorageKey() {
  const userId = window.sessionStorage.getItem(CURRENT_USER_STORAGE_KEY)?.trim();
  return userId ? `${ACTIVE_SEARCH_STORAGE_KEY}.${userId}` : ACTIVE_SEARCH_STORAGE_KEY;
}

function isTransientRequestError(error: unknown) {
  const status = Number((error as any)?.response?.status || 0);
  return !status || status === 408 || status === 429 || status >= 500;
}

async function fetchSearchReply(search: ActiveLeadSearch, limit = search.limit): Promise<LeadSearchReply> {
  const { data: candidateData } = await http.get<Envelope<LeadCandidate[]>>('/lead-candidates', {
    params: { search_run_id: search.searchRunId, limit: normalizeSearchTarget(limit) },
  });
  const items: LeadCandidate[] = ((candidateData as any)?.data || []) as LeadCandidate[];
  const rows = items.map(candidateToAnalysisCompany);
  let decisionTrace: LeadSearchTrace[] = [];
  try {
    const { data: traceData } = await http.get(`/lead-search-runs/${encodeURIComponent(search.searchRunId)}/trace`);
    const trace = (traceData as any)?.data || {};
    decisionTrace = (trace.providers || []).map((provider: LeadProviderTrace) => ({
      stage: provider.provider_code,
      title: `${provider.provider_code} · ${provider.status}`,
      detail: `${provider.operation} · ${provider.result_count || 0} 条${provider.error_message ? ` · ${provider.error_message}` : ''}`,
    }));
  } catch {
    // Candidate results stay usable while trace retrieval reconnects.
  }
  return {
    reply: `搜索已完成 (run_id: ${search.searchRunId})，返回 ${rows.length} 条候选线索`,
    rows,
    decision_trace: decisionTrace,
    search_run_id: search.searchRunId,
  };
}

async function waitForSearchRun(
  search: ActiveLeadSearch,
  onEvent?: (event: LeadSearchEvent) => void,
): Promise<LeadSearchReply> {
  let retryDelay = 3000;
  let connectionNoticeShown = false;
  let lastInterimCount = -1;
  while (true) {
    let run: LeadSearchRun;
    try {
      const { data } = await http.get<Envelope<LeadSearchRun>>(
        `/lead-search-runs/${encodeURIComponent(search.searchRunId)}`,
      );
      run = (data as any)?.data || data;
      retryDelay = 3000;
      connectionNoticeShown = false;
      onEvent?.({ type: 'status', data: run });
    } catch (error) {
      if (!isTransientRequestError(error)) throw error;
      if (!connectionNoticeShown) {
        onEvent?.({
          type: 'trace',
          data: { stage: 'reconnecting', title: '连接暂时中断', detail: '后台任务仍在运行，正在自动续查' },
        });
        connectionNoticeShown = true;
      }
      retryDelay = Math.min(Math.round(retryDelay * 1.5), 15000);
      await wait(retryDelay);
      continue;
    }
    if (TERMINAL_SEARCH_STATUSES.has(run.status)) {
      if (run.status === 'failed' || run.status === 'cancelled') {
        saveActiveSearch(null);
        throw new Error(run.error_message || `线索搜索已${run.status === 'cancelled' ? '取消' : '失败'}`);
      }
      try {
        const resultLimit = Math.min(
          Math.max(search.limit, run.candidate_count ?? run.candidates_count ?? 0),
          MAX_LEAD_SEARCH_RESULTS,
        );
        const reply = await fetchSearchReply(search, resultLimit);
        saveActiveSearch(null);
        return reply;
      } catch (error) {
        if (!isTransientRequestError(error)) throw error;
        if (!connectionNoticeShown) {
          onEvent?.({
            type: 'trace',
            data: { stage: 'reconnecting', title: '结果读取暂时中断', detail: '搜索已完成，正在重新获取候选线索' },
          });
          connectionNoticeShown = true;
        }
        await wait(retryDelay);
        continue;
      }
    }
    const interimCount = Number(run.enriched_count ?? run.scored_count ?? 0);
    if (interimCount > 0 && interimCount !== lastInterimCount) {
      lastInterimCount = interimCount;
      try {
        onEvent?.({ type: 'reply', data: await fetchSearchReply(search, search.limit) });
      } catch (error) {
        if (!isTransientRequestError(error)) throw error;
      }
    }
    await wait(retryDelay);
  }
}

async function observeSearchEvents(jobId: string, onEvent?: (event: LeadSearchEvent) => void) {
  const baseUrl = config.leadApiBase || '/api/v1';
  const sseUrl = `${baseUrl}/jobs/${encodeURIComponent(jobId)}/events`;
  await new Promise<void>((resolve) => {
    const es = new EventSource(sseUrl, { withCredentials: true });
    let settled = false;
    const finish = () => {
      if (settled) return;
      settled = true;
      es.close();
      resolve();
    };
    es.addEventListener('step_completed', (event: MessageEvent) => {
      let data: any = {};
      try { data = JSON.parse(event.data); } catch { /* ignore malformed progress only */ }
      onEvent?.({
        type: 'trace',
        data: {
          stage: data.step_code,
          title: data.message || data.step_code,
          detail: data.progress_percent != null ? `${data.progress_percent}%` : undefined,
          progress_percent: Number(data.progress_percent || 0),
          completed_count: Number(data.payload?.completed_count || 0),
          target_count: Number(data.payload?.target_count || 0),
        },
      });
    });
    es.addEventListener('candidate_completed', (event: MessageEvent) => {
      let data: any = {};
      try { data = JSON.parse(event.data); } catch { /* ignore malformed progress only */ }
      onEvent?.({
        type: 'trace',
        data: {
          stage: 'candidate_done',
          title: data.message || '已完成企业评估',
          detail: data.payload?.candidate_id || '',
          progress_percent: Number(data.progress_percent || 0),
          completed_count: Number(data.payload?.completed_count || 0),
          target_count: Number(data.payload?.target_count || 0),
        },
      });
    });
    es.addEventListener('completed', finish);
    es.addEventListener('error', finish);
    // SSE is an optional progress channel. Switch to status polling if it is quiet.
    window.setTimeout(finish, 20000);
  });
}

async function parseNdjsonStream(response: Response, onEvent?: (event: LeadSearchEvent) => void): Promise<LeadSearchReply> {
  if (!response.body) throw new Error('后端未返回流式响应');
  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';
  let finalData: LeadSearchReply = {};

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split(/\r?\n/);
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (!line.trim()) continue;
      const event = JSON.parse(line) as LeadSearchEvent;
      onEvent?.(event);
      if (event.type === 'reply') finalData = event.data || {};
    }
  }
  return finalData;
}

// ---- v3.6 Lead Intelligence API ----

export const leadApi = {
  // ---- Candidates (replaces /api/lead-discovery/validation-companies) ----

  /** GET /api/v1/lead-candidates — v3.6 endpoint */
  async listValidationCompanies(params = { page: 1, size: 50, sort: 'last_updated', order: 'desc' }, refresh = false) {
    const { data } = await http.get<Envelope<LeadCandidate[]>>('/lead-candidates', {
      params: { limit: params.size },
      headers: refresh ? { 'Cache-Control': 'no-cache' } : undefined,
    });
    const items: LeadCandidate[] = (data as any).data || [];
    return {
      items: items.map(candidateToAnalysisCompany),
      total: Number.isFinite(Number((data as any).page?.total)) ? Number((data as any).page.total) : items.length,
    };
  },

  // ---- Analysis companies (promoted from candidates) ----
  // Backend: no dedicated endpoint yet — candidates serve both roles

  /** GET /api/v1/lead-candidates — reused for analysis companies (filtered client-side) */
  async listAnalysisCompanies(params = { page: 1, size: 100, sort: 'last_updated', order: 'desc' }) {
    const { data } = await http.get<Envelope<LeadCandidate[]>>('/lead-candidates', {
      params: { limit: params.size, analysis_pool: true },
    });
    const items: LeadCandidate[] = (data as any).data || [];
    return {
      items: items.map(candidateToAnalysisCompany),
      total: Number.isFinite(Number((data as any).page?.total)) ? Number((data as any).page.total) : items.length,
    };
  },

  // ---- ICP dimension summary ----
  // Backend v3.6: ICP dimension summary is embedded in candidate enrichment results.
  // The lead-candidates list already includes icp_dimension_summary. No dedicated
  // batch backfill endpoint exists; run refresh-enrichment per candidate instead.

  /** Trigger refresh-enrichment for candidates missing dimension summaries */
  async refreshCandidates(rows: AnalysisCompany[]) {
    const results = await Promise.allSettled(rows.map((row) => {
      const candidateId = row.validation_company_id || row.company_id;
      if (!candidateId || row.candidate_version == null) {
        return Promise.reject(new Error('候选线索缺少版本信息，请刷新列表后重试'));
      }
      return http.post(
        `/lead-candidates/${encodeURIComponent(candidateId)}:refresh-enrichment`,
        {},
        {
          headers: {
            'Idempotency-Key': createIdempotencyKey(),
            'If-Match': String(row.candidate_version),
          },
        },
      );
    }));
    return {
      updated_count: results.filter((item) => item.status === 'fulfilled').length,
      failed_count: results.filter((item) => item.status === 'rejected').length,
      succeeded_candidate_ids: rows
        .filter((_, index) => results[index]?.status === 'fulfilled')
        .map((row) => String(row.validation_company_id || row.company_id || ''))
        .filter(Boolean),
    };
  },

  // ---- Promotion to analysis ----
  // Backed by POST /api/v1/lead-candidates:select (Strategic only)

  /** POST /api/v1/lead-candidates:select — batch-promote candidates to Sales Leads */
  async promoteToAnalysis(rows: AnalysisCompany[]) {
    const items = rows.map((row) => ({
      candidate_id: row.validation_company_id || row.company_id,
      expected_version: row.candidate_version,
    })).filter((item): item is { candidate_id: string; expected_version: number } => (
      Boolean(item.candidate_id) && item.expected_version != null
    ));
    if (items.length !== rows.length) {
      throw new Error('候选线索缺少版本信息，请刷新列表后重试');
    }
    const { data } = await http.post<Envelope<any>>('/lead-candidates:select', { items }, {
      headers: { 'Idempotency-Key': createIdempotencyKey() },
    });
    const result = (data as any).data || data || {};
    return {
      updated_count: (result.succeeded || []).length,
      company_ids: (result.succeeded || []).map((s: any) => s.company_id || s.lead_id),
      succeeded_candidate_ids: (result.succeeded || [])
        .map((s: any) => String(s.candidate_id || ''))
        .filter(Boolean),
      failed: result.failed || [],
      success: !(result.failed || []).length,
    };
  },

  // ---- Strategic email outreach Agent ----
  async previewEmailAutomation() {
    const { data } = await http.get('/email-automation/preview');
    return (data as any)?.data || data;
  },

  async runEmailAutomation(payload: Record<string, unknown> = {}) {
    const { data } = await http.post('/email-automation/agent/run', payload);
    return (data as any)?.data || data;
  },

  async getEmailAutomationRun(runId: string) {
    const { data } = await http.get(`/email-automation/runs/${runId}`);
    return (data as any)?.data || data;
  },

  async listEmailAutomationRuns(limit = 20): Promise<{ items: EmailAutomationRun[] }> {
    const { data } = await http.get('/email-automation/runs', { params: { limit } });
    return ((data as any)?.data || data) as { items: EmailAutomationRun[] };
  },

  async listEmailAutomationReplies(runId: string, params: { page?: number; pageSize?: number } = {}) {
    const { data } = await http.get(`/email-automation/runs/${runId}/replies`, { params });
    return (data as any)?.data || data;
  },
  async listEmailAutomationFailures(runId: string, params: { page?: number; pageSize?: number; code?: string } = {}) {
    const { data } = await http.get(`/email-automation/runs/${runId}/failures`, { params });
    return (data as any)?.data || data;
  },


  // ---- Search runs (replaces /api/lead-discovery/dialogue-search) ----

  /** POST /api/v1/lead-search-runs — v3.6 endpoint */
  async createSearchRun(payload: LeadSearchRunCreate): Promise<LeadSearchRun> {
    const { data } = await http.post<Envelope<LeadSearchRun>>('/lead-search-runs', {
      query_text: payload.query_text,
      search_mode: payload.search_mode ?? 'both',
      target_count: normalizeSearchTarget(payload.target_count),
      scene_code: payload.scene_code ?? 'S1',
    }, {
      headers: { 'Idempotency-Key': createIdempotencyKey() },
    });
    return (data as any).data;
  },

  /** GET /api/v1/lead-search-runs/{id} */
  async getSearchRun(searchRunId: string): Promise<LeadSearchRun> {
    const { data } = await http.get<Envelope<LeadSearchRun>>(`/lead-search-runs/${encodeURIComponent(searchRunId)}`);
    return (data as any).data;
  },

  /** GET /api/v1/lead-search-runs/{id}/trace */
  async getSearchTrace(searchRunId: string): Promise<LeadSearchTrace[]> {
    const { data } = await http.get(`/lead-search-runs/${encodeURIComponent(searchRunId)}/trace`);
    return (data as any).data || (data as any) || [];
  },

  async getCandidate(candidateId: string): Promise<Record<string, any>> {
    const { data } = await http.get<Envelope<Record<string, any>>>(
      `/lead-candidates/${encodeURIComponent(candidateId)}`,
    );
    return (data as any).data || {};
  },

  async importCandidates(file: File) {
    const form = new FormData();
    form.append('file', file, file.name);
    const { data } = await http.post<Envelope<{ search_run_id: string; imported_count: number }>>(
      '/lead-candidates:import', form,
    );
    return (data as any).data;
  },

  // ---- Search API ----

  getActiveSearch(): ActiveLeadSearch | null {
    return readActiveSearch();
  },

  async cancelActiveSearch() {
    const active = readActiveSearch();
    if (!active) return null;
    const { data } = await http.post(
      `/lead-search-runs/${encodeURIComponent(active.searchRunId)}:cancel`,
      {},
      { headers: { 'Idempotency-Key': createIdempotencyKey(), 'If-Match': '0' } },
    );
    saveActiveSearch(null);
    return (data as any)?.data || data;
  },

  async resumeDialogueSearch(onEvent?: (event: LeadSearchEvent) => void): Promise<LeadSearchReply | null> {
    const active = readActiveSearch();
    if (!active) return null;
    return waitForSearchRun(active, onEvent);
  },

  /** Create one search run and keep polling that run until the backend reaches a terminal state. */
  async dialogueSearch(payload: LeadSearchPayload): Promise<LeadSearchReply> {
    // 1. Create search run
    const { data: createRes } = await http.post<LeadSearchReply>('/lead-search-runs', {
      query_text: payload.user_input,
      search_mode: payload.search_mode === 'web' ? 'company_only' : 'both',
      target_count: normalizeSearchTarget(payload.limit),
      scene_code: 'S1',
    }, {
      headers: { 'Idempotency-Key': createIdempotencyKey() },
    });
    const envelope = (createRes as any).data;
    const searchRunId = envelope?.resource_id || envelope?.search_run_id || '';
    if (!searchRunId) {
      throw new Error('线索搜索响应缺少 run_id');
    }
    const active = { searchRunId, query: payload.user_input, limit: normalizeSearchTarget(payload.limit) };
    saveActiveSearch(active);
    return waitForSearchRun(active);
  },

  /** Real SSE streaming via GET /api/v1/jobs/{job_id}/events. */
  async streamDialogueSearch(payload: LeadSearchPayload, onEvent?: (event: LeadSearchEvent) => void): Promise<LeadSearchReply> {
    // 1. Create search run → get job_id
    const { data: createRes } = await http.post<any>('/lead-search-runs', {
      query_text: payload.user_input,
      search_mode: payload.search_mode === 'web' ? 'company_only' : 'both',
      target_count: normalizeSearchTarget(payload.limit),
      scene_code: 'S1',
    }, {
      headers: { 'Idempotency-Key': createIdempotencyKey() },
    });
    const envelope = createRes.data || createRes;
    const searchRunId = envelope?.resource_id || envelope?.search_run_id;
    const jobId = envelope?.job?.job_id || '';
    if (!searchRunId) throw new Error('线索搜索响应缺少 run_id');
    const active = { searchRunId, jobId, query: payload.user_input, limit: normalizeSearchTarget(payload.limit) };
    saveActiveSearch(active);
    if (jobId) await observeSearchEvents(jobId, onEvent);
    return waitForSearchRun(active, onEvent);
  },
};
