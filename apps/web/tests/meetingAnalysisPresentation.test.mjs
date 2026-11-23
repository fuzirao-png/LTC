import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import {
  cleanTranscriptText,
  formatMeetingDate,
  formatMeetingDuration,
  formatTranscriptRange,
  resolveMeetingSpeaker,
  splitHighlightedText,
} from '../src/features/meeting/meetingPresentation.js';

assert.equal(
  cleanTranscriptText('途国科技介绍人性机器人。😮 福利业参与。'),
  '途鸽科技介绍人形机器人。傅利叶参与。',
);
assert.equal(cleanTranscriptText('Yeah。我们继续。😊'), '我们继续。');
assert.equal(cleanTranscriptText('O. 请稍等'), '请稍等');
assert.equal(cleanTranscriptText('通信机成需要联调'), '通信机器人需要联调');

assert.equal(formatMeetingDuration(2352.99), '39分13秒');
assert.equal(formatMeetingDuration(0), '-');
assert.equal(formatMeetingDate('not-a-date'), 'not-a-date');
assert.equal(formatTranscriptRange(0, 58.82), '00:00 - 00:58');
assert.equal(formatTranscriptRange(3599, 3601), '59:59 - 60:01');

assert.deepEqual(resolveMeetingSpeaker({ speaker_label: '张经理' }, 0), {
  label: '张经理',
  tone: 'primary',
});
assert.deepEqual(resolveMeetingSpeaker({ speaker_id: 'speaker_1' }, 0), {
  label: '说话人B',
  tone: 'secondary',
});
assert.equal(resolveMeetingSpeaker({ text: '我们这边是途鸽科技' }, 1).label, '我方');
assert.equal(resolveMeetingSpeaker({ text: '我想了解你们能提供什么方案' }, 0).label, '客户方');
assert.equal(resolveMeetingSpeaker({ text: '好的' }, 0).label, '说话人A');
assert.equal(resolveMeetingSpeaker({ text: '明白' }, 1).label, '说话人B');

assert.deepEqual(splitHighlightedText('WiFi 与 wifi 双网连接', 'wifi'), [
  { text: 'WiFi', match: true },
  { text: ' 与 ', match: false },
  { text: 'wifi', match: true },
  { text: ' 双网连接', match: false },
]);

const component = readFileSync(
  new URL('../src/features/meeting/MeetingAnalysis.vue', import.meta.url),
  'utf8',
);
const apiSource = readFileSync(
  new URL('../src/services/meetingApi.ts', import.meta.url),
  'utf8',
);
const authGateSource = readFileSync(
  new URL('../src/shared/components/AuthGate.vue', import.meta.url),
  'utf8',
);
const sidebarSource = readFileSync(
  new URL('../src/shared/components/AppSidebar.vue', import.meta.url),
  'utf8',
);
const routerSource = readFileSync(
  new URL('../src/app/router/index.ts', import.meta.url),
  'utf8',
);
const customerOperationSource = readFileSync(
  new URL('../src/features/customer-operation/CustomerOperation.vue', import.meta.url),
  'utf8',
);

assert.match(component, /const PAGE_SIZE = 10/);
assert.match(component, /\?\.company_id[\s\S]*\?\.companyId[\s\S]*meeting\.selectedCompanyId/);
assert.match(component, /customer\?\.company_id[\s\S]*customer\?\.companyId[\s\S]*meeting\.selectedCompanyId/);
assert.match(component, /summaryData\.value\?\.core_summary/);
assert.match(component, /selectedRecord\.value\?\.fullTranscript[\s\S]*selectedRecord\.value\?\.transcript/);
assert.match(component, />会议基本信息</);
assert.doesNotMatch(component, /<select v-model=\"meeting\.selectedCustomerName\">/);
assert.doesNotMatch(component, /请选择客户/);
assert.match(component, /当前客户/);
assert.match(component, />会议摘要</);
assert.match(component, />待办TODO</);
assert.match(component, />会议决策</);
assert.match(component, />风险提醒</);
assert.match(component, />逐段对话</);
assert.match(component, /splitHighlightedText\(segment\.text, searchQuery\)/);
assert.match(component, /grid-template-columns: repeat\(3, minmax\(0, 1fr\)\)/);
assert.match(component, /max-height: 400px/);
assert.match(component, /@media \(max-width: 900px\)/);
assert.match(component, /const router = useRouter\(\)/);
assert.match(component, /const closeMeetingAnalysis = \(\) => router\.back\(\)/);
assert.match(component, /aria-label="关闭会议沟通并返回上一页"/);
assert.doesNotMatch(component, /@click="refreshHistory"/);

assert.match(apiSource, /decisions: toStringList/);
assert.match(apiSource, /core_summary\?: string \| null/);
assert.match(apiSource, /risks: toStringList/);
assert.match(apiSource, /keywords: toStringList/);
assert.match(apiSource, /speaker_label: segment\.speaker_label/);
assert.match(apiSource, /sequence_no: segment\.sequence_no/);
assert.match(authGateSource, /salesPaths[\s\S]*?\/meeting-analysis/);
assert.match(authGateSource, /await router\.isReady\(\)/);
assert.doesNotMatch(sidebarSource, /label: '会议沟通', path: '\/meeting-analysis'/);
assert.match(routerSource, /path: '\/meeting-analysis'[\s\S]*?title: '会议沟通'/);
assert.match(customerOperationSource, /openMeetingRecord[\s\S]*?router\.push\('\/meeting-analysis'\)/);

console.log('Meeting analysis presentation tests passed');
