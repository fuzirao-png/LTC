import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const source = readFileSync(
  new URL('../src/features/lead-collection/LeadCollection.vue', import.meta.url),
  'utf8',
);

assert.match(source, />全部入库</);
assert.match(source, /管理者可先补全和筛选，再将确认通过的线索人工入库/);
assert.doesNotMatch(source, /一刀全部入库|后端能力已接入|自动.*可领取线索池|>重新查找</);

console.log('lead collection copy test passed');
