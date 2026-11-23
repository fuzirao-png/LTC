export function createManualNoteAnalysisState(companyId, runId, expectedCompetition, result = {}) {
  const conflicts = Array.isArray(result.conflicts) ? result.conflicts : [];
  const skipped = Array.isArray(result.skipped_fields) ? result.skipped_fields : [];
  const updated = Array.isArray(result.updated_dimensions) ? result.updated_dimensions : [];
  let message = '客户分析正在更新，竞争对手字段将在本次运行完成后显示。';
  let status = 'pending';
  if (result.analysis?.status === 'failed') {
    status = 'failed';
    message = '竞争对手字段未进入报告：分析运行失败。';
  } else if (!updated.includes('competition')) {
    status = 'failed';
    const issue = conflicts.find((item) => item?.target === 'competition') || skipped.find((item) => item?.target === 'competition');
    message = issue?.reason === 'version_conflict'
      ? '竞争对手字段未进入报告：版本冲突，请重新提取后确认。'
      : '竞争对手字段未进入报告：本次字段未成功更新。';
  }
  return { companyId: String(companyId || ''), runId: String(runId || ''), expectedCompetition: String(expectedCompetition || ''), status, message };
}

export function resolveCompetitionUpdateStatus({ expectedCompetition, runStatus, currentCompetition }) {
  if (runStatus === 'failed' || runStatus === 'cancelled') return { status: 'failed', message: '竞争对手字段未进入报告：分析运行失败。' };
  if (runStatus !== 'completed') return { status: 'pending', message: '客户分析正在更新，竞争对手字段将在本次运行完成后显示。' };
  const expected = String(expectedCompetition || '').trim();
  const current = String(currentCompetition || '').trim();
  if (expected && current.includes(expected)) return { status: 'completed', message: '竞争对手字段已进入报告。' };
  return { status: 'failed', message: '竞争对手字段未进入报告：运行完成后未找到本次更新值。' };
}

export function saveManualNoteAnalysisState(state) {
  if (typeof sessionStorage === 'undefined' || !state?.companyId) return;
  sessionStorage.setItem(`manual-note-analysis:${state.companyId}`, JSON.stringify(state));
}

export function loadManualNoteAnalysisState(companyId) {
  if (typeof sessionStorage === 'undefined') return null;
  try { return JSON.parse(sessionStorage.getItem(`manual-note-analysis:${companyId}`) || 'null'); } catch { return null; }
}

export function clearManualNoteAnalysisState(companyId) {
  if (typeof sessionStorage !== 'undefined') sessionStorage.removeItem(`manual-note-analysis:${companyId}`);
}
