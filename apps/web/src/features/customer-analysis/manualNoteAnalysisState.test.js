import test from 'node:test';
import assert from 'node:assert/strict';

import {
  createManualNoteAnalysisState,
  resolveCompetitionUpdateStatus,
} from './manualNoteAnalysisState.js';

test('creates pending state for an updated competition field', () => {
  assert.deepEqual(createManualNoteAnalysisState('company-1', 'run-1', '飞猪', {
    updated_dimensions: ['competition'],
    conflicts: [],
    skipped_fields: [],
  }), {
    companyId: 'company-1',
    runId: 'run-1',
    expectedCompetition: '飞猪',
    status: 'pending',
    message: '客户分析正在更新，竞争对手字段将在本次运行完成后显示。',
  });
});

test('analysis start failure is immediately terminal', () => {
  const state = createManualNoteAnalysisState('company-1', '', '飞猪', {
    analysis: { status: 'failed' },
    updated_dimensions: ['competition'],
    conflicts: [],
    skipped_fields: [],
  });
  assert.equal(state.status, 'failed');
  assert.equal(state.message, '竞争对手字段未进入报告：分析运行失败。');
});

test('reports explicit failure for conflict or skipped competition', () => {
  const conflict = createManualNoteAnalysisState('company-1', 'run-1', '飞猪', {
    updated_dimensions: [],
    conflicts: [{ target: 'competition', reason: 'version_conflict' }],
    skipped_fields: [],
  });
  assert.equal(conflict.status, 'failed');
  assert.equal(conflict.message, '竞争对手字段未进入报告：版本冲突，请重新提取后确认。');
});

test('completed run verifies the refreshed competition value', () => {
  assert.deepEqual(resolveCompetitionUpdateStatus({
    expectedCompetition: '飞猪',
    runStatus: 'completed',
    currentCompetition: '飞猪、任意公司',
  }), {
    status: 'completed',
    message: '竞争对手字段已进入报告。',
  });
  assert.equal(resolveCompetitionUpdateStatus({
    expectedCompetition: '飞猪',
    runStatus: 'completed',
    currentCompetition: '旧竞争对手',
  }).message, '竞争对手字段未进入报告：运行完成后未找到本次更新值。');
});

test('failed run reports competition did not enter report', () => {
  assert.equal(resolveCompetitionUpdateStatus({
    expectedCompetition: '飞猪',
    runStatus: 'failed',
    currentCompetition: '',
  }).message, '竞争对手字段未进入报告：分析运行失败。');
});
