export interface ReplyAnalysisInput {
  intentLevel?: string | null;
  nextAction?: string | null;
  evidenceQuote?: string | null;
}

export interface ReplyAnalysisDisplay {
  intent: string;
  nextAction: string;
  evidence: string;
}

export function previewReplyContent(content?: string | null): string;
export function formatReplyAnalysis(analysis?: ReplyAnalysisInput): ReplyAnalysisDisplay;

export function displayFailureCompany(failure?: { companyName?: string | null; companyId?: string | null }): string;
