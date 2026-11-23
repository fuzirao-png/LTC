import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const reportCard = readFileSync(new URL('../src/features/customer-analysis/components/ReportCard.vue', import.meta.url), 'utf8');
const reportValue = readFileSync(new URL('../src/features/customer-analysis/components/ReportValue.vue', import.meta.url), 'utf8');
const customerAnalysis = readFileSync(new URL('../src/features/customer-analysis/CustomerAnalysis.vue', import.meta.url), 'utf8');

assert.match(reportCard, /结构化分析报告/);
assert.match(reportCard, /MODULE_ORDER = \['market', 'company', 'competitor', 'pain', 'product'\]/);
assert.match(reportCard, /<ReportValue/);
assert.doesNotMatch(reportCard, /JSON\.stringify/);
assert.doesNotMatch(reportCard, /<pre/);
assert.match(reportValue, /v-else-if="Array\.isArray\(value\)"/);
assert.match(reportValue, /v-else-if="isRecord\(value\)"/);
assert.match(customerAnalysis, /import ReportValue from '.\/components\/ReportValue\.vue'/);
assert.match(customerAnalysis, /structuredContent: Object\.fromEntries/);
assert.match(customerAnalysis, /<ReportValue :value="module\.structuredContent"/);

console.log('Structured report presentation tests passed');
