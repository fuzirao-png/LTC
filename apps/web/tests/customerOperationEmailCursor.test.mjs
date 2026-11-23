import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const source = readFileSync(
  new URL('../src/features/customer-operation/CustomerOperation.vue', import.meta.url),
  'utf8',
);

assert.match(source, /ref="emailDraftEditor"/);
assert.match(source, /@input="updateEmailDraft"/);
assert.doesNotMatch(source, /class="email-draft-body"[\s\S]*?v-text=/);
assert.match(source, /if \(emailDraftTextFromEditor\(editor\) !== value\) editor\.textContent = value/);
assert.match(source, /watch\(\[emailDraft, selectedEmailHistory\]/);

console.log('customer operation email cursor regression test passed');
