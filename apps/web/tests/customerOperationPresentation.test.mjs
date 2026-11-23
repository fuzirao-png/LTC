import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const source = readFileSync(
  new URL('../src/features/customer-operation/CustomerOperation.vue', import.meta.url),
  'utf8',
);
const operationApiSource = readFileSync(
  new URL('../src/services/operationApi.ts', import.meta.url),
  'utf8',
);

assert.match(source, /customer\.locationLabel/);
assert.match(source, /customer\.regionalTime/);
assert.match(source, /resolveCustomerClock\(\{ country \}\)/);
assert.doesNotMatch(source, /regionalClockConfig/);
assert.match(source, /sanitizeCustomerName/);

assert.doesNotMatch(source, /最近邮件交互/);
assert.doesNotMatch(source, />链接<\/button>/);
assert.doesNotMatch(source, />列表<\/button>/);

assert.match(source, /emailRegenerating/);
assert.match(source, /editRosterContact/);
assert.match(source, /removeRosterContact/);
assert.match(source, /saveContactFromDrawer/);
assert.match(source, /contactDrawerMode\.value === 'edit'/);
assert.match(source, /AI正在根据你的指令重新生成/);
assert.match(source, /EMAIL_REGENERATE_PRESETS/);
assert.match(source, /operationApi\.getCustomerOperations/);
assert.match(source, /emailContactNodes/);
assert.match(source, /class="contact-avatar blue"/);
assert.doesNotMatch(source, /class="contact-avatar green"/);
assert.match(source, /companyId: emailCustomer\.value\.companyId/);
assert.match(source, /contactId: contact\.contactId/);
assert.match(source, /customer\.contact \|\| customer\.ownerName \|\| payload\.assigned_to/);
assert.doesNotMatch(source, /const dynamicContact: EmailContact \| null = contactName && contactName !== '—' \?/);
assert.doesNotMatch(source, /selectedEmailContact\.value = dynamicContact;/);
assert.match(source, /operationContactEmailById/);
assert.match(source, /rosterItemToEmailContactWithFallback/);
assert.match(source, /rosterItemHasEmail/);
assert.match(source, /activeRosterContacts = computed\(\(\) => sortActiveRosterContacts\(/);
assert.match(source, /\(contactRoster\.value\?\.active \|\| \[\]\)\.filter\(rosterItemHasEmail\)/);
assert.match(source, /backupRosterContacts = computed\(\(\) => sortBackupRosterContacts\(/);
assert.match(source, /\(contactRoster\.value\?\.backup \|\| \[\]\)\.filter\(rosterItemHasEmail\)/);
assert.match(source, /selectedEmailContact\.value \|\| emailContactNodes\.value\.find/);
assert.match(source, /@click="selectEmailContact\(rosterItemToEmailContactWithFallback\(item\)\)"/);
assert.match(source, /source_primary_email/);
assert.match(source, /item\.source_primary_email \|\| item\.primary_email \|\| '—'/);
assert.match(source, /requestId !== emailHistoryRequestId \|\| emailCustomer\.value\?\.companyId !== companyId/);
assert.match(source, /contactEmailCount/);
assert.match(source, /icpScore > 75/);
assert.match(source, /需补齐联系人邮箱/);
assert.match(source, /border: needsContactEmail \? 'red' : 'blue'/);
assert.match(source, /sourceCustomer\?\.company_id[\s\S]*sourceCustomer\?\.companyId/);
assert.match(source, /sourceCustomer\?\.company_id[\s\S]*sourceCustomer\?\.companyId/);
assert.doesNotMatch(source, /fallbackEmailContacts/);
assert.match(operationApiSource, /operationHttp\.get<\{ data: OperationDetail \}>/);
assert.match(operationApiSource, /operationHttp\.patch<\{ data: OperationContact \}>/);
assert.match(operationApiSource, /async updateContact\(/);
assert.match(operationApiSource, /return data\.data/);

assert.doesNotMatch(source, /meeting-title-icon/);
assert.doesNotMatch(source, /<span[^>]*>🎥<\/span>/);

console.log('customer operation presentation test passed');
