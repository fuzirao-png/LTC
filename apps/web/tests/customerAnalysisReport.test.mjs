import assert from 'node:assert/strict';
import test from 'node:test';

import { normalizeCurrentAnalysisReport } from '../src/services/analysisReportAdapter.js';

test('real provider reports expose structured modules to the 17-point view', () => {
  const normalized = normalizeCurrentAnalysisReport({
    content_source: 'llm',
    market: { structure: { tam: '100亿元' } },
    company: { business: { revenue_model: '订阅制' } },
    competitor: { products: ['竞品A'] },
    product: { recommended: ['方案A'] },
    sales_guide: { next_action: '安排演示' },
  });

  assert.equal(normalized._is_real_analysis, true);
  assert.equal(normalized._raw.market.structure.tam, '100亿元');
  assert.deepEqual(normalized.sales_guidance, { next_action: '安排演示' });
});

test('template reports cannot masquerade as real analysis content', () => {
  const normalized = normalizeCurrentAnalysisReport({
    content_source: 'template',
    market: { structure: { tam: '模板估算' } },
    sales_guide: { next_action: '模板动作' },
  });

  assert.equal(normalized._is_real_analysis, false);
  assert.deepEqual(normalized._raw, {});
  assert.deepEqual(normalized.sales_guidance, {});
});

test('research worker reports expose evidence-grounded structured modules', () => {
  const normalized = normalizeCurrentAnalysisReport({
    content_source: 'research_worker',
    market: {
      facts: [{ text: '公开市场事实', evidence_ids: ['exa:1'] }],
      inferences: [{ text: '市场推断', evidence_ids: ['exa:1', 'exa:2'] }],
      unknowns: [{ item: '采购时间表', reason: '客户尚未确认' }],
      sales_recommendations: [{ action: '确认时间表', reason: '降低推进风险', evidence_ids: ['exa:1'] }],
    },
    sales_guide: { next_action: '安排访谈' },
  });

  assert.equal(normalized._is_real_analysis, true);
  assert.equal(normalized._raw.market.facts[0].text, '公开市场事实');
  assert.deepEqual(normalized.sales_guidance, { next_action: '安排访谈' });
});

test('missing reports normalize to an empty view', () => {
  assert.deepEqual(normalizeCurrentAnalysisReport(null), {});
});
