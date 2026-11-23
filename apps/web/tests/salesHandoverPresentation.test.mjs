import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const source = readFileSync(
  new URL('../src/features/boss-dashboard/BossSalesManagement.vue', import.meta.url),
  'utf8',
);
const allocationApi = readFileSync(
  new URL('../src/services/allocationApi.ts', import.meta.url),
  'utf8',
);

assert.match(source, /eligibleHandoverTargets/);
assert.match(source, /allocationApi\.assignHandoverLead\(/);
assert.doesNotMatch(source, /allocationApi\.assignLead\(/);
assert.match(source, /poolStageHandoverLeads/);
assert.match(source, /lead\.pipeline_stage === 'new'/);
assert.match(source, /allocationApi\.returnHandoverToPool\(item\.user_id\)/);
assert.match(source, /一键回池待领取客户/);
assert.match(source, /v-model="handoverTarget\[lead\.lead_id\]"/);
assert.match(source, /@click="assignHandover\(lead\)"/);
assert.match(source, /确认分配/);
assert.match(source, /SALES_TIER_MISMATCH:[\s\S]*?所选销售等级与客户要求不匹配/);
assert.doesNotMatch(source, /v-for="user in activeSalesUsers"/);
assert.doesNotMatch(source, /离职客户暂不进入普通销售资源池/);
assert.doesNotMatch(source, /销售管理 · 手动分配|主管分配不考核过程|manualLeads|selectedAssignee/);
assert.match(allocationApi, /region:\s*item\.pool_region_code\s*\|\|\s*undefined/);
assert.match(source, /salesUsers\.filter\(u=>u\.status==='active'&&u\.sales_tier==='MA'\)\.length/);
assert.match(source, /salesUsers\.filter\(u=>u\.status==='active'&&u\.sales_tier==='SA'\)\.length/);
assert.match(source, /salesUsers\.filter\(u=>u\.status==='active'&&u\.sales_tier==='A'\)\.length/);
assert.match(source, /<div class="metric-sub">MA \{\{/);
assert.doesNotMatch(source, /<div class="metric-sub">\{\{ salesTierLabel\('MA'\) \}\}/);

console.log('sales handover presentation test passed');
