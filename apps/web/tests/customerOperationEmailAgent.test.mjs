import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const source = readFileSync(
  new URL('../src/features/customer-operation/CustomerOperation.vue', import.meta.url),
  'utf8',
);

assert.match(source, /emailAgentCandidate/);
assert.match(source, /await operationApi\.runEmailAgent\(/);
assert.match(
  source,
  /const applyGeneratedEmailAgentResult = \([\s\S]*result: EmailAgentResult,[\s\S]*purpose: 'first_touch' \| 'reply_followup',[\s\S]*emailSubject\.value = result\.subject \|\| emailSubject\.value;[\s\S]*emailDraft\.value = result\.body;[\s\S]*markEmailDraftDirty\(\)/,
  'generated Agent results must directly replace the active subject and body and mark the draft dirty',
);
assert.match(
  source,
  /const generateFromEmailHistory = async \(\) => \{[\s\S]*applyGeneratedEmailAgentResult\(result, 'reply_followup'\)/,
  'history reply generation must directly apply the Agent result',
);
assert.match(
  source,
  /const regenerateEmail = async[\s\S]*applyGeneratedEmailAgentResult\(result, 'first_touch'\)/,
  'regenerate and rewrite must directly apply the Agent result',
);
assert.doesNotMatch(
  source,
  /已根据指令生成邮件候选，请确认后使用。|已生成客户回复候选，请确认后使用。|已生成跟进邮件候选，请确认后使用。/,
  'generated Agent results must not wait for confirmation',
);
assert.doesNotMatch(source, /email-agent-preview|email-agent-panel|email-agent-sidebar/);

console.log('customer operation email agent test passed');
