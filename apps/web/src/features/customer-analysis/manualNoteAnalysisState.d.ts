export interface ManualNoteAnalysisState {
  companyId: string;
  runId: string;
  expectedCompetition: string;
  status: 'pending' | 'completed' | 'failed';
  message: string;
}

export function createManualNoteAnalysisState(companyId: string, runId: string, expectedCompetition: string, result?: { updated_dimensions?: string[]; conflicts?: Array<{ target?: string; reason?: string }>; skipped_fields?: Array<{ target?: string; reason?: string }> }): ManualNoteAnalysisState;
export function resolveCompetitionUpdateStatus(input: { expectedCompetition: string; runStatus: string; currentCompetition: string }): Pick<ManualNoteAnalysisState, 'status' | 'message'>;
export function saveManualNoteAnalysisState(state: ManualNoteAnalysisState): void;
export function loadManualNoteAnalysisState(companyId: string): ManualNoteAnalysisState | null;
export function clearManualNoteAnalysisState(companyId: string): void;
