import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import { sanitizeCustomerName } from '../src/shared/utils/customerName.js';

const source = readFileSync(
  new URL('../src/features/customer-operation/CustomerOperation.vue', import.meta.url),
  'utf8',
);

assert.equal(
  sanitizeCustomerName(['acme', 'Acme Corporation'], 'https://www.acme.com'),
  'Acme Corporation',
  'a website-derived prefix should be skipped in favor of a valid customer name',
);
assert.equal(
  sanitizeCustomerName(['Nexus Business Travel'], 'https://nexusbusinesstravel.com/'),
  'Nexus Business Travel',
  'a legitimate multi-word brand matching its domain prefix must remain visible',
);
assert.equal(
  sanitizeCustomerName(['KAYAK'], 'https://www.kayak.co.kr/business'),
  'KAYAK',
  'an uppercase brand matching its domain prefix must remain visible',
);
assert.equal(
  sanitizeCustomerName(['AC-ME'], 'acme.com'),
  '客户名称待确认',
  'a normalized website-derived prefix must not leak through the fallback',
);
assert.equal(
  sanitizeCustomerName(['https://acme.com', 'sales@acme.com'], 'acme.com'),
  '客户名称待确认',
  'URLs and email addresses should not be shown as customer names',
);
assert.equal(
  sanitizeCustomerName(['qq.com'], ''),
  '客户名称待确认',
  'a bare domain must not be shown as a customer name',
);

assert.match(
  source,
  /const customerName = String\(customer\.display_name \|\| ''\)\.trim\(\) \|\| sanitizeCustomerName\(\[/,
  'customer normalization should sanitize API name candidates against the customer website',
);
assert.match(source, /name: customerName/);
assert.match(source, /filter\(\(customer\) => customer\.name !== '客户名称待确认'\)/);
assert.doesNotMatch(source, /homeCards\.value\.find\(\(item\) => item\.customerName === customer\.name\)/);
assert.doesNotMatch(source, /homeCards\.value\.find\(\(item\) => item\.customerName === meetingCustomer\.value\?\.name\)/);
assert.match(source, /shared\/utils\/customerName\.js/);

console.log('customer operation name sanitization test passed');
