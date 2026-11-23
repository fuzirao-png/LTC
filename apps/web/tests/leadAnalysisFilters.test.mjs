import assert from 'node:assert/strict';

import { filterAnalysisRows, matchesCustomerSize, matchesScoreBucket } from '../src/features/lead-analysis/leadAnalysisFilters.js';

for (const [score, bucket] of [[90, '90_plus'], [89, '80_89'], [80, '80_89'], [79, '70_79'], [70, '70_79'], [69, '60_69'], [60, '60_69'], [59, 'under_60']]) {
  assert.equal(matchesScoreBucket(score, bucket), true, `${score} should match ${bucket}`);
}

assert.equal(matchesCustomerSize('A', 'A'), true);
assert.equal(matchesCustomerSize('B', 'B'), true);
assert.equal(matchesCustomerSize('C', 'C'), true);
assert.equal(matchesCustomerSize('A', 'B'), false);
assert.equal(matchesCustomerSize('unknown', 'all'), true);

const rows = [
  { id: 'match', sourceKey: 'web_search', scenario: '差旅平台', score: 90, sizeKey: 'A', regionKey: '东亚' },
  { id: 'wrong-source', sourceKey: 'manual_upload', scenario: '差旅平台', score: 90, sizeKey: 'A', regionKey: '东亚' },
  { id: 'wrong-size', sourceKey: 'web_search', scenario: '差旅平台', score: 90, sizeKey: 'B', regionKey: '东亚' },
  { id: 'wrong-region', sourceKey: 'web_search', scenario: '差旅平台', score: 90, sizeKey: 'A', regionKey: '北美' },
];

const filtered = filterAnalysisRows(rows, {
  source: 'web_search',
  industry: '差旅平台',
  score: '90_plus',
  size: 'A',
  region: '东亚',
});
assert.deepEqual(filtered.map((row) => row.id), ['match']);

console.log('Lead analysis filter tests passed');
