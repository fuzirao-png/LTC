import assert from 'node:assert/strict';

import { parseLeadSearchTarget } from '../src/features/lead-collection/leadSearchTarget.js';

assert.equal(parseLeadSearchTarget('找十家北美携程', 2000), 10);
assert.equal(parseLeadSearchTarget('找二十五家旅行平台', 2000), 25);
assert.equal(parseLeadSearchTarget('找五百多家客户', 2000), 500);
assert.equal(parseLeadSearchTarget('找 600 家企业', 2000), 600);
assert.equal(parseLeadSearchTarget('找三千家企业', 2000), 2000);
assert.equal(parseLeadSearchTarget('找北美携程', 2000), null);

console.log('Lead search target parser test passed');
