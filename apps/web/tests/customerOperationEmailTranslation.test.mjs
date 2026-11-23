import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const source = readFileSync(
  new URL('../src/features/customer-operation/CustomerOperation.vue', import.meta.url),
  'utf8',
);

assert.match(
  source,
  /const sourceSubject = emailSubject\.value\.trim\(\);[\s\S]*const sourceText = emailDraft\.value\.trim\(\);[\s\S]*await operationApi\.runEmailAgent\([\s\S]*subject: sourceSubject,[\s\S]*body: sourceText,[\s\S]*operation: ['"]translate['"][\s\S]*targetLanguage: selectedTranslateLanguage\.value\.key/,
  'customer operation email translation must use email-agent with the selected language',
);
assert.match(
  source,
  /emailTranslationSubject\.value = result\.subject/,
  'customer operation email translation must display the Agent result subject',
);
assert.match(
  source,
  /emailTranslation\.value = result\.body/,
  'customer operation email translation must display the Agent result body',
);
assert.match(
  source,
  /emailSubject\.value = emailAgentCandidate\.value\.subject[\s\S]*emailDraft\.value = emailAgentCandidate\.value\.body/,
  'using the Agent translation must replace both the subject and body',
);
assert.match(
  source,
  /当前主题和正文将被\{\{ selectedTranslateLanguage\.name \}\}译文覆盖/,
  'the replacement confirmation must state that both subject and body will be replaced',
);
assert.match(
  source,
  /const emailTranslating = ref\(false\)/,
  'customer operation email translation must expose a loading state',
);
assert.doesNotMatch(
  source,
  /const buildTranslatedEmail =/,
  'customer operation email translation must not use a fixed local template',
);
assert.doesNotMatch(
  source,
  /Thank you for your interest in our enterprise eSIM solution/,
  'the fixed fallback email must be removed from the customer operation page',
);

console.log('customer operation email translation test passed');
