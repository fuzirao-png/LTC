import { defineStore } from 'pinia';

import { config } from '../config/runtime';
import { getApiErrorMessage } from '../services/http';
import { loadCandidateLanding } from '../services/landingQueries';
import { useAuthStore } from './auth';
import {
  DEFAULT_LEAD_SEARCH_TARGET,
  leadApi,
  type AnalysisCompany,
  type LeadSearchEvent,
  type LeadSearchTrace,
} from '../services/leadApi';

function getCompanyName(row: AnalysisCompany) {
  return String(row.company_name || row.name || row.company || '').trim();
}

function getCompanyId(row: AnalysisCompany) {
  return String(row.validation_company_id || row.company_id || row.id || '').trim();
}

function withoutCandidateIds(rows: AnalysisCompany[], candidateIds: string[]) {
  const removed = new Set(candidateIds.filter(Boolean));
  return rows.filter((row) => !removed.has(getCompanyId(row)));
}

export const useLeadStore = defineStore('lead', {
  state: () => ({
    analysisCompanies: [] as AnalysisCompany[],
    validationCompanies: [] as AnalysisCompany[],
    searchRows: [] as AnalysisCompany[],
    dismissedCandidateIds: [] as string[],
    searchLogs: [] as Array<{ role: 'user' | 'agent' | 'trace' | 'error'; text: string }>,
    traceEvents: [] as LeadSearchTrace[],
    pendingRouteContext: null as Record<string, unknown> | null,
    analysisTotal: 0,
    validationTotal: 0,
    validationRequestId: 0,
    loading: false,
    searching: false,
    cancellingSearch: false,
    searchProgress: 0,
    searchCompletedCount: 0,
    searchTargetCount: 0,
    searchProgressMessage: '',
    searchStartedAt: '',
    cancelRequested: false,
    saving: false,
    error: '',
    lastSaveMessage: '',
  }),
  getters: {
    missingDimensionSummaryCount: (state) =>
      state.analysisCompanies.filter((item) => item.icp_score !== undefined && !String(item.icp_dimension_summary || '').trim()).length,
  },
  actions: {
    async loadAnalysisCompanies(size = 2000) {
      this.loading = true;
      this.error = '';
      try {
        const data = await leadApi.listAnalysisCompanies({ page: 1, size, sort: 'last_updated', order: 'desc' });
        this.analysisCompanies = data.items || [];
        this.analysisTotal = Number.isFinite(data.total) ? data.total : this.analysisCompanies.length;
      } catch (error) {
        this.error = getApiErrorMessage(error, '线索分析列表加载失败');
      } finally {
        this.loading = false;
      }
    },
    async loadValidationCompanies(size = 100, refresh = false) {
      this.loading = true;
      this.error = '';
      const auth = useAuthStore();
      const userId = auth.currentUser?.userId || '';
      const requestId = ++this.validationRequestId;
      const isCurrent = () => this.validationRequestId === requestId && (auth.currentUser?.userId || '') === userId;
      try {
        const data = await loadCandidateLanding(userId, size, refresh);
        if (!isCurrent()) return;
        this.validationCompanies = withoutCandidateIds(data.items || [], this.dismissedCandidateIds);
        this.validationTotal = Number.isFinite(data.total) ? data.total : this.validationCompanies.length;
      } catch (error) {
        if (!isCurrent()) return;
        this.error = getApiErrorMessage(error, '线索收集列表加载失败');
      } finally {
        if (isCurrent()) this.loading = false;
      }
    },
    addSearchLog(role: 'user' | 'agent' | 'trace' | 'error', text: string) {
      if (!text.trim()) return;
      this.searchLogs.push({ role, text });
    },
    dismissCandidateRows(candidateIds: string[]) {
      const ids = candidateIds.filter(Boolean);
      if (!ids.length) return;
      this.dismissedCandidateIds = [...new Set([...this.dismissedCandidateIds, ...ids])];
      this.searchRows = withoutCandidateIds(this.searchRows, ids);
      this.validationCompanies = withoutCandidateIds(this.validationCompanies, ids);
    },
    applySearchEvent(event: LeadSearchEvent) {
      if (event.type === 'status') {
        this.searchProgress = Math.max(this.searchProgress, Math.round(Number(event.data.progress_percent || 0)));
        this.searchCompletedCount = Math.max(this.searchCompletedCount, Number(event.data.enriched_count || 0));
        this.searchTargetCount = Number(event.data.candidate_count || event.data.target_count || this.searchTargetCount);
        this.searchProgressMessage = String(event.data.progress_message || this.searchProgressMessage || '正在准备搜索');
        this.searchStartedAt = event.data.started_at || event.data.created_at || this.searchStartedAt;
        return;
      }
      if (event.type === 'reply') {
        this.searchRows = (event.data.rows || []) as AnalysisCompany[];
        return;
      }
      this.traceEvents.push(event.data);
      this.searchProgress = Math.max(this.searchProgress, Math.round(Number(event.data.progress_percent || 0)));
      this.searchCompletedCount = Math.max(this.searchCompletedCount, Number(event.data.completed_count || 0));
      this.searchTargetCount = Number(event.data.target_count || this.searchTargetCount);
      this.searchProgressMessage = event.data.title || this.searchProgressMessage;
      this.addSearchLog('trace', [event.data.title, event.data.detail || event.data.text].filter(Boolean).join('：'));
    },
    async runDialogueSearch(query: string, limit = DEFAULT_LEAD_SEARCH_TARGET) {
      const text = query.trim();
      if (!text) return;
      this.loading = true;
      this.searching = true;
      this.error = '';
      this.lastSaveMessage = '';
      this.searchRows = [];
      this.dismissedCandidateIds = [];
      this.traceEvents = [];
      this.cancelRequested = false;
      this.cancellingSearch = false;
      this.searchProgress = 0;
      this.searchCompletedCount = 0;
      this.searchTargetCount = limit;
      this.searchProgressMessage = '正在创建后台搜索任务';
      this.searchStartedAt = new Date().toISOString();
      this.addSearchLog('user', text);
      this.addSearchLog('agent', '已收到条件，正在调用后端线索搜索能力。');

      const payload = {
        user_input: text,
        search_provider: config.searchProvider || 'exa',
        search_mode: 'both' as const,
        limit,
        env_path: config.leadEnvPath || undefined,
        include_trace: true,
        ...(this.pendingRouteContext ? { route_context: this.pendingRouteContext } : {}),
      };

      try {
        const data = await leadApi.streamDialogueSearch(payload, (event) => this.applySearchEvent(event));
        if (data.reply) this.addSearchLog('agent', data.reply);
        if (data.requires_user_input) {
          this.pendingRouteContext = {
            original_input: text,
            action: data.action || '',
            requires_user_input: true,
            missing_fields: data.missing_fields || [],
            payload: data.payload || {},
            next_step: data.next_step || '',
          };
          this.addSearchLog('agent', `还需要补充：${(data.missing_fields || []).join('、') || '更多检索条件'}`);
        } else {
          this.pendingRouteContext = null;
        }
        this.searchRows = (data.rows || []) as AnalysisCompany[];
        for (const trace of data.decision_trace || []) {
          this.traceEvents.push(trace);
          this.addSearchLog('trace', [trace.title, trace.detail].filter(Boolean).join('：'));
        }
        if (this.searchRows.length) {
          this.addSearchLog('agent', `已返回 ${this.searchRows.length} 条候选线索。`);
        }
        this.searchProgress = 100;
        this.searchProgressMessage = '搜索完成';
      } catch (error) {
        if (!this.cancelRequested) {
          this.error = getApiErrorMessage(error, '线索搜索失败');
          this.searchProgressMessage = '搜索未完成';
          this.addSearchLog('error', this.error);
        }
      } finally {
        this.loading = false;
        this.searching = false;
        this.cancellingSearch = false;
      }
    },
    async resumeDialogueSearch() {
      if (this.searching || !leadApi.getActiveSearch()) return;
      this.searching = true;
      this.loading = true;
      this.error = '';
      this.cancelRequested = false;
      this.searchProgressMessage = '正在恢复后台进度';
      this.searchStartedAt = new Date().toISOString();
      this.addSearchLog('agent', '检测到未完成的线索任务，正在恢复后台进度。');
      try {
        const data = await leadApi.resumeDialogueSearch((event) => this.applySearchEvent(event));
        if (!data) return;
        if (data.reply) this.addSearchLog('agent', data.reply);
        this.searchRows = (data.rows || []) as AnalysisCompany[];
        for (const trace of data.decision_trace || []) {
          this.traceEvents.push(trace);
          this.addSearchLog('trace', [trace.title, trace.detail].filter(Boolean).join('：'));
        }
      } catch (error) {
        if (!this.cancelRequested) {
          this.error = getApiErrorMessage(error, '线索任务恢复失败');
          this.addSearchLog('error', this.error);
        }
      } finally {
        this.searching = false;
        this.loading = false;
      }
    },
    async cancelSearch() {
      if (!this.searching || this.cancellingSearch) return;
      this.cancellingSearch = true;
      this.cancelRequested = true;
      this.searchProgressMessage = '正在取消后台任务';
      try {
        await leadApi.cancelActiveSearch();
        this.searchProgressMessage = '搜索已取消';
        this.addSearchLog('agent', '已取消本次搜索，已完成的候选仍会保留。');
      } catch (error) {
        this.cancelRequested = false;
        this.error = getApiErrorMessage(error, '取消搜索失败');
        this.addSearchLog('error', this.error);
      } finally {
        this.cancellingSearch = false;
      }
    },
    async promoteRowsToAnalysis(rows: AnalysisCompany[]) {
      const validRows = rows.filter((row) => getCompanyId(row));
      if (!validRows.length) {
        return {
          updated_count: 0,
          company_ids: [] as string[],
          succeeded_candidate_ids: [] as string[],
          failed: [],
          success: true,
        };
      }
      return leadApi.promoteToAnalysis(validRows);
    },
    async backfillRows(rows: AnalysisCompany[]) {
      const result = await leadApi.refreshCandidates(rows);
      this.dismissCandidateRows(result.succeeded_candidate_ids);
      const message = `已提交补全 ${result.updated_count} 条${result.failed_count ? `，失败 ${result.failed_count} 条` : ''}`;
      this.addSearchLog(result.failed_count ? 'error' : 'agent', message);
      return result;
    },
    async saveRowsToAnalysisAndAllocation(rows: AnalysisCompany[]) {
      const validRows = rows.filter(Boolean);
      if (!validRows.length) {
        this.lastSaveMessage = '请先选择候选线索';
        return;
      }
      this.saving = true;
      this.error = '';
      this.lastSaveMessage = '';
      try {
        const promoteResult = await this.promoteRowsToAnalysis(validRows);
        const analysisCount = Number(promoteResult.updated_count || promoteResult.company_ids?.length || 0);
        const failedCount = promoteResult.failed?.length || 0;
        this.dismissCandidateRows(promoteResult.succeeded_candidate_ids);
        this.lastSaveMessage = `找到线索 ${analysisCount} 条，失败 ${failedCount} 条`;
        this.addSearchLog('agent', this.lastSaveMessage);
        await this.loadAnalysisCompanies();
        return promoteResult;
      } catch (error) {
        this.error = getApiErrorMessage(error, '线索入库失败');
        this.addSearchLog('error', this.error);
        return null;
      } finally {
        this.saving = false;
      }
    },
  },
});
