import type { AnalysisReport } from './analysisApi';

export interface NormalizedAnalysisReport extends AnalysisReport {
  _content_source: string;
  _is_real_analysis: boolean;
  _raw: {
    market?: Record<string, unknown>;
    company?: Record<string, unknown>;
    competitor?: Record<string, unknown>;
    pain?: Record<string, unknown>;
    product?: Record<string, unknown>;
  };
  sales_guidance: Record<string, unknown>;
}

export function normalizeCurrentAnalysisReport(
  report: AnalysisReport | null | undefined,
): NormalizedAnalysisReport | Record<string, never>;
