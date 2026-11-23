import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const component = readFileSync(
  new URL('../src/features/customer-operation/CustomerOperation.vue', import.meta.url),
  'utf8',
);
const api = readFileSync(
  new URL('../src/services/operationApi.ts', import.meta.url),
  'utf8',
);

assert.ok(component.includes('const saveEmailDraft = async'));
assert.ok(component.includes('}, 3000)'));
assert.ok(component.includes('@click="saveEmailDraft(true)"'));
assert.ok(component.includes('{{ emailDrafts.length }}'));
assert.ok(component.includes('@click="applySavedDraft(item)"'));
assert.ok(component.includes('savedEmailAttachments'));
assert.ok(component.includes('@click="removeSavedEmailAttachment(attachment)"'));
assert.ok(component.includes('@click="requestCloseOperationModal"'));
assert.match(component, /draftId:\s*emailDraftId\.value/);
assert.ok(api.includes('async createEmailDraft'));
assert.ok(api.includes('async updateEmailDraft'));
assert.ok(api.includes("'If-Match': String(version)"));

assert.ok(component.includes('const latestDraftForContact ='));
assert.ok(component.includes('const startFreshEmailDraftSession ='));
assert.ok(component.includes('const switchEmailDraftContact = async'));
assert.ok(component.includes('switchEmailDraftContact(contact)'));
assert.ok(component.includes('applySavedDraft(emailDrafts.value[0])'));
assert.ok(component.includes('const saveRevision = emailDraftRevision'));
assert.ok(component.includes('if (saveRevision === emailDraftRevision)'));
assert.ok(component.includes('clearEmailDraftAutosaveTimer()'));
assert.ok(component.includes('const markEmailDraftDirty = () =>'));
assert.ok(component.includes('if (saveRevision === emailDraftRevision) {'));
assert.ok(component.includes('markEmailDraftDirty();'));
assert.ok(!component.includes('void switchEmailDraftContact(contact);\n  return;'));
assert.ok(component.includes('return saveRevision === emailDraftRevision;'));
assert.ok(component.includes('if (!saved || emailDraftDirty.value) return;'));
assert.ok(component.includes('已切换到 ${contact.name}，已恢复该联系人的最近草稿'));
assert.ok(component.includes('已切换到 ${contact.name}，已创建新的邮件草稿'));
assert.ok(!component.includes('???'));

console.log('customer operation email draft regression test passed');
