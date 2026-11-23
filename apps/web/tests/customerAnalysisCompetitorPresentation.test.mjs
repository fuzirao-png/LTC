import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const component = fs.readFileSync(
  path.resolve('src/features/customer-analysis/CustomerAnalysis.vue'),
  'utf8',
);

assert.match(component, /已确认竞争对手/);
assert.match(component, /data\.meddpicc\?\.competition/);
