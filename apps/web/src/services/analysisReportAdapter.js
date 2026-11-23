const REAL_ANALYSIS_SOURCES = new Set(['llm', 'provider', 'external', 'research_worker']);

export function normalizeCurrentAnalysisReport(report) {
  if (!report || typeof report !== 'object') return {};

  const contentSource = String(
    report.content_source
      || (report.research_meta?.research_worker_used ? 'research_worker' : '')
      || '',
  ).trim().toLowerCase() || 'missing';
  const isRealAnalysis = REAL_ANALYSIS_SOURCES.has(contentSource);

  return {
    ...report,
    _content_source: contentSource,
    _is_real_analysis: isRealAnalysis,
    // Template reports are evidence-grounded fallbacks generated when the
    // LLM provider is unavailable. They still contain useful meeting/profile
    // content and must remain visible instead of being treated as empty.
    _raw: {
      market: report.market || {},
      company: report.company || {},
      competitor: report.competitor || {},
      pain: report.pain || {},
      product: report.product || {},
    },
    sales_guidance: report.sales_guide || {},
  };
}
