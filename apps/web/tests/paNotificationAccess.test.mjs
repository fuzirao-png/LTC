import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import {
  canAccessMailNotifications,
  dedupeMailNotifications,
  removeCompletedReminder,
} from '../src/app/layouts/paNotificationAccess.js';

assert.equal(canAccessMailNotifications({ accountType: 'sales' }), true);
assert.equal(canAccessMailNotifications({ accountType: 'strategic' }), false);
assert.equal(canAccessMailNotifications(null), false);

const first = { id: 'first', messageId: '<same@example.test>' };
const duplicate = { id: 'duplicate', notificationTarget: { messageId: '<same@example.test>' } };
const withoutMessageId = { id: 'unique' };
assert.deepEqual(dedupeMailNotifications([first, duplicate, withoutMessageId, withoutMessageId]), [first, withoutMessageId]);

const reminders = [{ id: 'mail' }, { id: 'meeting' }, { id: 'proposal' }];
assert.deepEqual(removeCompletedReminder(reminders, 'meeting'), [{ id: 'mail' }, { id: 'proposal' }]);

const layout = readFileSync(new URL('../src/app/layouts/AppLayout.vue', import.meta.url), 'utf8');
assert.match(layout, /邮件回复优先级/);
assert.match(layout, /会议时间/);
assert.match(layout, /方案发送优先级/);
assert.match(layout, /completePaReminder/);
assert.match(layout, /<div class="pa-section-title">邮件提醒<\/div>/);
assert.doesNotMatch(layout, /paTodoItems/);
assert.doesNotMatch(layout, /<div class="pa-section-title">日程<\/div>/);

console.log('PA notification access test passed');
