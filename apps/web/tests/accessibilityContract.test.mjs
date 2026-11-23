import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const readSource = (path) => readFileSync(new URL(path, import.meta.url), 'utf8');

const login = readSource('../src/features/auth/LoginView.vue');
const allocation = readSource('../src/features/customer-allocation/CustomerAllocation.vue');
const bossAssign = readSource('../src/features/boss-dashboard/BossLeadAssign.vue');
const css = readSource('../src/style.css');
const index = readSource('../index.html');

assert.match(login, /<form[\s\S]*?@submit\.prevent="submit"/);
assert.match(login, /<label[^>]+for="login-username"/);
assert.match(login, /<label[^>]+for="login-password"/);
assert.match(login, /id="login-error"[^>]+role="alert"/);
assert.match(login, /passwordInput\.value\?\.focus\(\)/);

assert.match(allocation, /aria-label="资源池行业"/);
assert.doesNotMatch(allocation, /城市|cityFilter|myCityFilter/);
assert.doesNotMatch(allocation, /<th>城市<\/th>/);
assert.doesNotMatch(allocation, /displayCity\(lead\)/);
assert.doesNotMatch(allocation, /待领取/);
assert.match(allocation, /class="metric-cards col3 allocation-metric-cards"/);
assert.match(allocation, /role="dialog"[^>]+aria-modal="true"[^>]+aria-labelledby="claim-dialog-title"/);
assert.match(allocation, /event\.key === 'Escape'/);
assert.match(allocation, /claimConfirmButton\.value\?\.focus\(\)/);
assert.match(allocation, /if \(trigger\?\.isConnected\) trigger\.focus\(\)/);

assert.match(bossAssign, /role="dialog"[^>]+aria-modal="true"[^>]+aria-labelledby="assign-detail-title"/);
assert.match(bossAssign, /detailCloseButton\.value\?\.focus\(\)/);
assert.match(bossAssign, /event\.key === 'Escape'/);
assert.match(bossAssign, /if \(trigger\?\.isConnected\) trigger\.focus\(\)/);

assert.match(css, /button:focus-visible,[\s\S]*?outline:\s*2px solid var\(--blue-primary\)/);
assert.match(index, /<link rel="icon" href="data:," \/>/);

console.log('Accessibility contract test passed');
