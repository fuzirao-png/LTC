import assert from 'node:assert/strict';
import {
  EMAIL_REGENERATE_PRESETS,
  buildEmailAgentPayload,
  buildEmailDraft,
  buildRegenerateEmailPayload,
} from '../src/features/customer-operation/emailDraft.js';

const customer = { companyId: 'company-1', name: 'GlobalLink Travel', tag: '差旅平台' };
const contact = { contactId: 'contact-1', name: 'Sarah Chen', email: 's.chen@globallink.com', role: 'Head of Technology' };

const base = buildEmailDraft(customer, contact, 'Zong Lin');
const payload = buildRegenerateEmailPayload(customer, contact, 'Re: Topic', base, '强调 GDPR 合规', 'Zong Lin');

assert.equal(base.includes('补充重点：'), false);
assert.equal(base.endsWith('Zong Lin'), true);
assert.equal(payload.mode, 'regenerate');
assert.equal(payload.currentBody, base);
assert.equal(payload.customPrompt, '强调 GDPR 合规');
assert.equal(payload.salesName, 'Zong Lin');
assert.equal(payload.companyId, 'company-1');
assert.equal(payload.contactId, 'contact-1');
assert.deepEqual(EMAIL_REGENERATE_PRESETS, [
  { label: '强调GDPR合规', prompt: '强调GDPR合规' },
  { label: '正式语气表达', prompt: '正式语气表达' },
]);

const agentPayload = buildEmailAgentPayload({
  customer,
  contact,
  subject: 'Re: Topic',
  body: base,
  instruction: '强调 GDPR 合规',
  operation: 'rewrite',
  targetLanguage: 'en',
});

assert.deepEqual(agentPayload, {
  companyId: 'company-1',
  contactId: 'contact-1',
  customerName: 'GlobalLink Travel',
  recipientName: 'Sarah Chen',
  recipientEmail: 's.chen@globallink.com',
  recipientTitle: 'Head of Technology',
  subject: 'Re: Topic',
  body: base,
  instruction: '强调 GDPR 合规',
  operation: 'rewrite',
  targetLanguage: 'en',
});

console.log('email draft test passed');
