import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const apiSource = fs.readFileSync(path.join(root, 'src/services/leadApi.ts'), 'utf8');
const storeSource = fs.readFileSync(path.join(root, 'src/stores/lead.ts'), 'utf8');
const authStoreSource = fs.readFileSync(path.join(root, 'src/stores/auth.ts'), 'utf8');
const viewSource = fs.readFileSync(path.join(root, 'src/features/lead-collection/LeadCollection.vue'), 'utf8');
const analysisViewSource = fs.readFileSync(path.join(root, 'src/features/lead-analysis/LeadAnalysis.vue'), 'utf8');
const assignmentViewSource = fs.readFileSync(path.join(root, 'src/features/boss-dashboard/BossLeadAssign.vue'), 'utf8');
const customerListSource = fs.readFileSync(path.join(root, 'src/features/customer-analysis/CustomerListPage.vue'), 'utf8');
const styleSource = fs.readFileSync(path.join(root, 'src/style.css'), 'utf8');

test('lead promotion uses the candidate version and one backend transaction path', () => {
  assert.match(apiSource, /expected_version:\s*row\.candidate_version/);
  assert.doesNotMatch(storeSource, /ingestAssignedCustomer/);
  assert.doesNotMatch(storeSource, /syncRowsToAllocationPool/);
});

test('analysis pool and selected refresh use real backend state', () => {
  assert.match(apiSource, /analysis_pool:\s*true/);
  assert.match(apiSource, /refreshCandidates/);
  assert.match(apiSource, /'If-Match':\s*String\(row\.candidate_version\)/);
  assert.match(viewSource, /backfillSelectedRows[\s\S]*backfillRows\(selectedSourceRows\.value\)/);
  assert.match(apiSource, /succeeded_candidate_ids/);
  assert.match(storeSource, /dismissCandidateRows\(result\.succeeded_candidate_ids\)/);
  assert.match(storeSource, /dismissCandidateRows\(promoteResult\.succeeded_candidate_ids\)/);
});

test('customer size prefers backend A B C assessment', () => {
  assert.match(viewSource, /customer_size_grade/);
  assert.match(apiSource, /customer_size_grade/);
  assert.match(analysisViewSource, /label:\s*key === 'unknown' \? '-' : key/);
  assert.match(analysisViewSource, /<label>客户规模<select[\s\S]*?<option value="A">A<\/option>[\s\S]*?<option value="B">B<\/option>[\s\S]*?<option value="C">C<\/option>/);
  assert.match(analysisViewSource, /<th class="sortable" @click="toggleSort\('sizeKey'\)">客户规模/);
  assert.doesNotMatch(analysisViewSource, /公司规模|500人以上|100-499人|100人以下|规模待确认/);
  assert.match(analysisViewSource, /grade:\s*String\(item\.icp_grade/);
});

test('customer assignment keeps customer grade and sales tier strictly aligned', () => {
  assert.match(assignmentViewSource, /salesTierByCustomerGrade:[\s\S]*?A: ["']MA["'][\s\S]*?B: ["']SA["'][\s\S]*?C: ["']A["']/);
  assert.match(assignmentViewSource, /const grade = item\.customer_size_grade[\s\S]*?gradeFromScore\(score\)/);
  assert.match(assignmentViewSource, /tier: matchedAllocation\?\.sales_tier \|\| salesTierForCustomerGrade\(grade\)/);
  assert.doesNotMatch(assignmentViewSource, /salesTierFromScore/);
});

test('lead country codes use centralized Chinese labels and the action column stays removed', () => {
  assert.match(analysisViewSource, /import \{ countryLabel \} from '\.\.\/\.\.\/shared\/utils\/labels'/);
  assert.match(analysisViewSource, /countryLabel\(String\(value \|\| ''\)\.trim\(\)\)/);
  assert.doesNotMatch(viewSource, /<th class="action-col">操作<\/th>/);
  assert.doesNotMatch(viewSource, /<td><button class="btn-xs" type="button" @click="openLeadDetail\(item\)">查看<\/button><\/td>/);
});

test('empty database state does not render demo companies', () => {
  assert.doesNotMatch(viewSource, /fallbackLeads|GlobalLink Travel|TechTravel Inc\./);
  assert.match(viewSource, /if \(!sourceRows\.value\.length\) return \[\]/);
});

test('long-running searches expose progress, interim rows, and cancellation', () => {
  assert.match(apiSource, /type: 'status'/);
  assert.match(apiSource, /interimCount > 0/);
  assert.match(apiSource, /cancelActiveSearch/);
  assert.match(storeSource, /searchCompletedCount/);
  assert.match(storeSource, /cancelSearch/);
  assert.match(viewSource, /后台正在收集线索/);
  assert.match(viewSource, /role="progressbar"/);
  assert.match(viewSource, /lead\.cancelSearch/);
});

test('active searches are isolated by authenticated manager', () => {
  assert.match(apiSource, /activeSearchStorageKey/);
  assert.match(apiSource, /CURRENT_USER_STORAGE_KEY/);
  assert.match(apiSource, /sessionStorage\.getItem\(CURRENT_USER_STORAGE_KEY\)/);
  assert.match(authStoreSource, /saveCurrentUserIdentity\(currentUser\)/);
  assert.match(authStoreSource, /sessionStorage\.setItem\(currentUserStorageKey, user\.userId\)/);
});

test('total lead library only presents filtered claimable leads', () => {
  assert.match(apiSource, /analysis_pool:\s*true/);
  assert.doesNotMatch(analysisViewSource, /fallbackRows|GlobalLink Travel|TechTravel Inc\./);
  assert.match(analysisViewSource, /经管理者筛选并人工入库、当前可由销售领取/);
  assert.doesNotMatch(storeSource, /已入库/);
  assert.match(storeSource, /找到线索 \$\{analysisCount\} 条，失败 \$\{failedCount\} 条/);
});

test('ICP scores render as unframed black text across lead tables', () => {
  assert.match(viewSource, /class="ceo-lead-cell ceo-lead-icp"/);
  assert.match(analysisViewSource, /class="icp-score-number"/);
  assert.match(assignmentViewSource, /class="icp-score-number"/);
  assert.match(customerListSource, /class="icp-score-number"/);
  assert.match(styleSource, /\.icp-score-number\s*\{[\s\S]*?color:\s*#111827;[\s\S]*?background:\s*transparent;[\s\S]*?border:\s*0;/);
  assert.doesNotMatch(viewSource, /ceo-lead-icp',\s*item\.score/);
});

test('lead collection view header and actions share the same centered column', () => {
  assert.match(viewSource, /<th class="view-col">查看<\/th>/);
  assert.match(styleSource, /\.ceo-lead-table th\.view-col,\s*\.ceo-lead-table td:last-child\s*\{\s*text-align:\s*center;/);
});

test('lead analysis omits the redundant current-condition summary', () => {
  assert.doesNotMatch(analysisViewSource, /当前条件：/);
  assert.match(analysisViewSource, /class="analysis-selection-status">已选/);
});

test('customer assignment filters fit one desktop row', () => {
  assert.match(assignmentViewSource, /class="assign-filter-bar"/);
  assert.match(assignmentViewSource, /grid-template-columns:\s*repeat\(7, minmax\(0, 1fr\)\) auto/);
});

test('newly claimed leads only show the claimed status', () => {
  assert.match(assignmentViewSource, /pipeline_stage === 'new'\) return '已领取'/);
  assert.doesNotMatch(assignmentViewSource, /已领取\s*·\s*待触达/);
});

test('assignment follow-up filter omits the daily follow-up option', () => {
  assert.doesNotMatch(assignmentViewSource, /<option value="今日待跟">今日待跟<\/option>/);
});

test('analysis detail preserves backend D1-D4 scores', () => {
  assert.match(apiSource, /icp_breakdown:\s*score\s*\?\s*\{[\s\S]*?d1:\s*score\.D1[\s\S]*?d4:\s*score\.D4/);
  assert.match(apiSource, /d1_score_explanation:\s*score\?\.explanations\?\.D1/);
  assert.match(apiSource, /d4_score_explanation:\s*score\?\.explanations\?\.D4/);
  assert.match(analysisViewSource, /scorePayload\?\.total/);
  assert.match(analysisViewSource, /scorePayload\.D1\s*\?\?\s*scorePayload\.d1/);
});

test('company introductions use a two-line clickable preview and full detail panel', () => {
  assert.match(viewSource, /intro:\s*item\.company_intro\s*\|\|\s*'暂无公司简介'/);
  assert.match(viewSource, /class="ceo-lead-intro-preview"[\s\S]*?@click="openLeadDetail\(item\)"/);
  assert.match(viewSource, /-webkit-line-clamp:\s*2/);
  assert.match(viewSource, /selectedDetail\.company_intro\s*\|\|\s*'暂无简介'/);
  assert.match(styleSource, /\.ceo-lead-table\s*\{[\s\S]*?min-width:\s*1460px\s*!important/);
  assert.match(styleSource, /\.ceo-lead-table \.intro-col\s*\{\s*width:\s*280px/);
  assert.doesNotMatch(viewSource, /reason:\s*item\.icp_dimension_summary\s*\|\|\s*item\.company_intro/);
});
