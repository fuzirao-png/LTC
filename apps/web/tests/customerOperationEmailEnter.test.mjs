import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const source = readFileSync(
  new URL('../src/features/customer-operation/CustomerOperation.vue', import.meta.url),
  'utf8',
);

assert.ok(source.includes('const emailDraftTextFromEditor = (editor: HTMLElement)'));
assert.ok(source.includes("event.inputType !== 'insertParagraph' && event.inputType !== 'insertLineBreak'"));
assert.ok(source.includes('event.preventDefault()'));
assert.ok(source.includes("document.execCommand('insertText', false, '\\n')"));
assert.ok(source.includes('emailDraftTextFromEditor(event.target as HTMLElement)'));
assert.ok(source.includes('@beforeinput="handleEmailDraftBeforeInput"'));
assert.ok(source.includes('.email-draft-body { white-space: pre-wrap; }'));

console.log('customer operation email enter regression test passed');
