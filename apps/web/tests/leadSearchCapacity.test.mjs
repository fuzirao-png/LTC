import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const readSource = (path) => readFileSync(new URL(path, import.meta.url), 'utf8');

const api = readSource('../src/services/leadApi.ts');
const store = readSource('../src/stores/lead.ts');
const collection = readSource('../src/features/lead-collection/LeadCollection.vue');

assert.match(api, /export const DEFAULT_LEAD_SEARCH_TARGET = 500;/);
assert.match(api, /export const MAX_LEAD_SEARCH_RESULTS = 2000;/);
assert.match(api, /while \(true\)/, 'search status polling must not have a global deadline');
assert.doesNotMatch(api, /(?:deadline|startedAt|maxWait|300000|5 \* 60)/i);
assert.match(api, /Math\.max\([\s\S]*?search\.limit[\s\S]*?run\.candidate/);
assert.match(api, /Math\.min\([\s\S]*?MAX_LEAD_SEARCH_RESULTS/);
assert.match(store, /runDialogueSearch\(query: string, limit = DEFAULT_LEAD_SEARCH_TARGET\)/);
assert.match(collection, /parseLeadSearchTarget\(query\.value, MAX_LEAD_SEARCH_RESULTS\) \?\? DEFAULT_LEAD_SEARCH_TARGET/);

console.log('Lead search capacity contract test passed');
