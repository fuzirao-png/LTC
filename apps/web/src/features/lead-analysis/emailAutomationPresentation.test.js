import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

import {
  displayFailureCompany,
  formatReplyAnalysis,
  previewReplyContent,
} from './emailAutomationPresentation.js';

test('failure company display never exposes a UUID as the company name', () => {
  assert.equal(displayFailureCompany({ companyName: 'Acme', companyId: 'company-1' }), 'Acme');
  assert.equal(
    displayFailureCompany({ companyId: 'f4018ad0-a9b3-4efe-9e82-1ac816db5575' }),
    '未知公司',
  );
});

test('reply content preview keeps the complete configured summary visible', () => {
  const content = 'A'.repeat(140);

  assert.equal(previewReplyContent(content), `${'A'.repeat(120)}...`);

  const component = fs.readFileSync(
    new URL('./EmailAutomation.vue', import.meta.url),
    'utf8',
  );
  assert.match(component, /-webkit-line-clamp: 2;/);
});

test('expanded detail rows keep a fixed height and clip overflowing content', () => {
  const component = fs.readFileSync(
    new URL('./EmailAutomation.vue', import.meta.url),
    'utf8',
  );
  assert.match(component, /\.detail-table tbody tr \{ height: 56px; \}/);
  assert.match(component, /\.detail-table tbody td \{ height: 56px; max-height: 56px; overflow: hidden; \}/);
  assert.match(component, /\.detail-cell-content \{ display: -webkit-box; height: 38px; max-height: 38px; overflow: hidden;/);
  assert.match(component, /selectedFailure = item/);
  assert.match(component, /class=\"action-cell\"/);
  assert.match(component, /&#33258;&#21160;&#22238;&#22797;/);
  assert.match(component, /\.intent-label \{ font-weight: 700;/);
  assert.doesNotMatch(component, /\.intent-badge \{/);
});

test('reply analysis converts English model output to Chinese display text', () => {
  const analysis = formatReplyAnalysis({
    intentLevel: 'unsubscribe',
    nextAction: 'Remove the contact from marketing outreach.',
    evidenceQuote: 'unsubscribe',
  });

  assert.deepEqual(analysis, {
    intent: '\u9000\u8ba2',
    nextAction: '\u5efa\u8bae\u5c06\u8be5\u8054\u7cfb\u4eba\u79fb\u51fa\u8425\u9500\u89e6\u8fbe\u540d\u5355\u3002',
    evidence: '\u8bf7\u7ed3\u5408\u5ba2\u6237\u539f\u59cb\u90ae\u4ef6\u6b63\u6587\u5224\u65ad\u3002',
  });
});

test('reply analysis preserves already-Chinese recommendations', () => {
  const analysis = formatReplyAnalysis({
    intentLevel: 'pricing',
    nextAction: '请发送最新报价单。',
    evidenceQuote: '客户询问了价格。',
  });

  assert.equal(analysis.intent, '询价');
  assert.equal(analysis.nextAction, '请发送最新报价单。');
  assert.equal(analysis.evidence, '客户询问了价格。');
});

test('automatic replies display only the automatic reply label', () => {
  const analysis = formatReplyAnalysis({ intentLevel: 'automatic_reply' });
  assert.equal(analysis.intent, '\u81ea\u52a8\u56de\u590d');
  assert.equal(analysis.nextAction, '');
});
