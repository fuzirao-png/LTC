<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';

import {
  operationApi,
  type ContactRoster,
  type ContactRosterItem,
  type EmailAgentResult,
  type ManualNoteField,
  type OperationContact,
  type OperationCustomer,
} from '../../services/operationApi';
import type { OperationEmail, OperationEmailAttachment, OperationEmailDraft } from '../../services/operationApi';
import { getApiErrorMessage } from '../../services/http';
import type { MeetingRecord } from '../../services/meetingApi';
import { useAuthStore } from '../../stores/auth';
import { useMeetingStore } from '../../stores/meeting';
import { useLegacyUiStore } from '../../stores/legacyUi';
import { customerAnalysisRoute } from '../../shared/utils/customerAnalysisNavigation.js';
import { countryCardLabel, resolveCustomerClock } from '../../shared/utils/customerClock.js';
import { sanitizeCustomerName } from '../../shared/utils/customerName.js';
import { contactDisplayName, contactEmail, contactTitle, sortContacts } from '../../shared/utils/contactOrdering.js';
import { regionLabel } from '../../shared/utils/labels';
import { createManualNoteAnalysisState, saveManualNoteAnalysisState } from '../customer-analysis/manualNoteAnalysisState.js';
import { sortActiveRosterContacts, sortBackupRosterContacts } from './contactRosterOrdering.js';
import { EMAIL_REGENERATE_PRESETS, buildEmailAgentPayload, buildEmailDraft } from './emailDraft.js';

interface OperationCard {
  companyId?: string;
  name: string;
  locationLabel: string;
  regionalTime: string;
  tag: string;
  contact: string;
  border: string;
  needsContactEmail: boolean;
  progress: number;
  stageRank: number;
  steps: string[];
  dates: string[];
  latestInboundReply?: OperationCustomer['latestInboundReply'];
  tasks: NonNullable<OperationCustomer['tasks']>;
}

interface EmailContact {
  contactId?: string;
  key: string;
  name: string;
  email: string;
  role: string;
  group: 'influencer' | 'decision' | 'executor';
  initial: string;
  position?: number;
  score?: number;
  outreachStatus?: string;
  pinned?: boolean;
  locked?: boolean;
  recommendationReason?: string;
}

const router = useRouter();
const auth = useAuthStore();
const meeting = useMeetingStore();
const legacyUi = useLegacyUiStore();
const currentSalesName = computed(
  () => auth.currentUser?.name || auth.currentUser?.username || '',
);
const homeCards = ref<OperationCustomer[]>([]);
const homeCardsError = ref('');
const homeCardsLoaded = ref(false);
const homeCardsLoading = ref(false);
const emailCustomer = ref<OperationCard | null>(null);
const meetingCustomer = ref<OperationCard | null>(null);
const meetingFileInput = ref<HTMLInputElement | null>(null);
const emailAttachmentInput = ref<HTMLInputElement | null>(null);
const emailTranslatePicker = ref<HTMLElement | null>(null);
const selectedMeetingFile = ref<File | null>(null);
const meetingDragActive = ref(false);
const activeMeetingAudioUrl = ref('');
const selectedEmailContact = ref<EmailContact | null>(null);
const emailSubject = ref('');
const emailDraft = ref('');
const emailDraftEditor = ref<HTMLElement | null>(null);
const emailPrompt = ref('');
const emailFeedback = ref('');
const emailTranslateOpen = ref(false);
const emailTranslateMenuOpen = ref(false);
const emailTranslationSubject = ref('');
const emailTranslation = ref('');
const emailAgentCandidate = ref<EmailAgentResult | null>(null);
const emailTranslating = ref(false);
const emailAttachments = ref<File[]>([]);
const emailDragActive = ref(false);
const emailReplaceConfirmOpen = ref(false);
const emailEditOpen = ref(false);
const emailEditSubject = ref('');
const emailEditBody = ref('');
const emailSendReceipt = ref<{ messageId: string; traceId: string; deliveredTo: string; provider: string } | null>(null);
const emailSending = ref(false);
const emailRegenerating = ref(false);
const emailHistory = ref<OperationEmail[]>([]);
const emailDrafts = ref<OperationEmailDraft[]>([]);
const emailDraftId = ref('');
const emailDraftVersion = ref<number | null>(null);
const emailDraftSaving = ref(false);
const emailDraftDirty = ref(false);
const emailDraftSavedAt = ref('');
const savedEmailAttachments = ref<OperationEmailAttachment[]>([]);
const emailContacts = ref<OperationContact[]>([]);
const contactRoster = ref<ContactRoster | null>(null);
const contactRosterLoading = ref(false);
const contactRosterError = ref('');
const contactDrawerOpen = ref(false);
const contactDrawerTab = ref<'recommended' | 'manual'>('recommended');
const contactRosterWorking = ref(false);
const pendingRosterContact = ref<ContactRosterItem | null>(null);
const replacementContactId = ref('');
const rosterActionReason = ref('');
const manualContactForm = ref({
  fullName: '',
  title: '',
  department: '',
  email: '',
  linkedinUrl: '',
});
const contactDrawerMode = ref<'manual' | 'edit'>('manual');
const editingContactId = ref('');
const editingContactVersion = ref<number | null>(null);
const emailPurpose = ref<'first_touch' | 'reply_followup' | 'meeting_followup'>('first_touch');
const emailAgentPendingPurpose = ref<'first_touch' | 'reply_followup'>('first_touch');
const emailHistoryLoading = ref(false);
const emailHistoryError = ref('');
const selectedEmailHistory = ref<OperationEmail | null>(null);
const meetingSegmentPageState = ref<Record<string, number>>({});
let meetingPollTimer: number | undefined;
let regionalClockTimer: number | undefined;
let meetingDragDepth = 0;
let emailDragDepth = 0;
let emailHistoryRequestId = 0;
let emailDraftAutosaveTimer: number | undefined;
let suppressEmailDraftDirty = false;
let emailDraftRevision = 0;
let emailDraftSessionVersion = 0;
const clockNow = ref(new Date());

// ---- Manual record modal (aligned with prototype) ----
const manualRecordCustomer = ref<OperationCard | null>(null);
const manualRecordType = ref<'email' | 'meeting' | 'note'>('note');
const manualRecordNote = ref('');
const manualRecordTime = ref('');
const manualRecordMessage = ref('');
const manualRecordFields = ref<ManualNoteField[]>([]);
const manualRecordUnidentified = ref('');
const manualRecordExtracting = ref(false);
const manualRecordSaving = ref(false);
const manualRecordStep = ref<'input' | 'review' | 'saved'>('input');

const emailTranslateLanguages = [
  { key: 'ja', flag: '🇯🇵', name: '日语', sub: 'Japanese' },
  { key: 'en', flag: '🇬🇧', name: '英语', sub: 'English' },
  { key: 'fr', flag: '🇫🇷', name: '法语', sub: 'French' },
  { key: 'de', flag: '🇩🇪', name: '德语', sub: 'German' },
  { key: 'es', flag: '🇪🇸', name: '西班牙语', sub: 'Spanish' },
  { key: 'zh', flag: '🇨🇳', name: '中文（本地润色）', sub: 'Chinese' },
] as const;

type EmailTranslateLanguage = (typeof emailTranslateLanguages)[number];
const selectedTranslateLanguage = ref<EmailTranslateLanguage>(emailTranslateLanguages[0]);

const emptyEmailContact: EmailContact = {
  key: 'empty', name: '未选择联系人', email: '—', role: '暂无联系人数据', group: 'decision', initial: '—',
};

const stageOrder = ['assigned', 'emailed', 'replied', 'meeting', 'proposal', 'won'] as const;

const normalizeStage = (stage?: string) => {
  const text = String(stage || '').toLowerCase();
  if (text.includes('won') || text.includes('deal') || text.includes('成交')) return 'won';
  if (text.includes('proposal') || text.includes('方案')) return 'proposal';
  if (text.includes('meeting') || text.includes('会议')) return 'meeting';
  if (text.includes('replied') || text.includes('reply') || text.includes('回复')) return 'replied';
  if (text.includes('email') || text.includes('触达') || text.includes('邮件')) return 'emailed';
  return 'assigned';
};

const stageProgress = (stage?: string) => ({
  assigned: 8.5,
  emailed: 25,
  replied: 42,
  meeting: 58.5,
  proposal: 75.5,
  won: 100,
}[normalizeStage(stage)]);

const stageRank = (stage?: string) => stageOrder.indexOf(normalizeStage(stage));

const textOf = (value: unknown, fallback = '-') => {
  const text = String(value ?? '').trim();
  return text || fallback;
};

const replyIntentLabel = (intent?: string) => ({
  interested: '有兴趣',
  pricing: '询价',
  product_question: '产品问题',
  not_interested: '暂不考虑',
  unsubscribe: '退订',
}[String(intent || '')] || '客户回复');

const replyIntentClass = (intent?: string) => `reply-intent-${String(intent || 'default').replace(/[^a-z_]/g, '') || 'default'}`;

const formatDateLabel = (value?: string | null) => {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return `${date.getMonth() + 1}/${String(date.getDate()).padStart(2, '0')}`;
};

const formatDateCountLabel = (value: string | null | undefined, count: number) => {
  const dateLabel = formatDateLabel(value);
  if (dateLabel === '—' || count <= 0) return dateLabel;
  return `${dateLabel} · ${count}封`;
};

const stageDatesToTimeline = (
  stageDates: OperationCustomer['stageDates'] | undefined,
  outboundEmailCount: number,
  inboundEmailCount: number,
) => [
  formatDateLabel(stageDates?.acquiredAt),
  formatDateCountLabel(stageDates?.emailedAt, outboundEmailCount),
  formatDateCountLabel(stageDates?.repliedAt, inboundEmailCount),
  formatDateLabel(stageDates?.meetingAt),
  formatDateLabel(stageDates?.proposalAt),
  formatDateLabel(stageDates?.wonAt),
];

const customerLocationLabel = (country: unknown) => countryCardLabel(country);

const customerRegionalTime = (country: unknown, region: unknown) => {
  const regionCode = String(region || '').trim().toUpperCase();
  const config = resolveCustomerClock({ country });
  if (!config) return `${regionCode ? regionLabel(regionCode) : '当地'}时间待确认`;
  try {
    const time = new Intl.DateTimeFormat('zh-CN', {
      timeZone: config.timeZone,
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }).format(clockNow.value);
    return `${config.label} ${time}`;
  } catch {
    return `${config.label}待确认`;
  }
};

const normalizeCustomer = (customer: OperationCustomer): OperationCard => {
  const payload = (customer.payload || {}) as Record<string, unknown>;
  const customerRecord = customer as unknown as Record<string, unknown>;
  const stage = String(customer.stage || payload.stage || '');
  const progress = Number(customer.progress || stageProgress(stage));
  const website = payload.website || customerRecord.website;
  const customerName = String(customer.display_name || '').trim() || sanitizeCustomerName([
    payload.legal_name,
    payload.legalName,
    payload.company_name,
    payload.companyName,
    customerRecord.company_name,
    customerRecord.companyName,
    customer.customerName,
  ], website);
  const country = payload.country || payload.country_code || customerRecord.country || customerRecord.country_code;
  const region = payload.region || payload.region_code || customerRecord.region || customerRecord.region_code;
  const ownerName = customer.contact || customer.ownerName || payload.assigned_to;
  const outboundEmailCount = Number(customer.outboundEmailCount ?? payload.outbound_email_count ?? 0);
  const inboundEmailCount = Number(customer.inboundEmailCount ?? payload.inbound_email_count ?? 0);
  const icpScore = Number(payload.icp_score ?? customerRecord.icp_score ?? customer.icpScore ?? NaN);
  const contactEmailCount = Number(payload.contact_email_count ?? customerRecord.contact_email_count ?? customer.contactEmailCount ?? 0);
  const needsContactEmail = Number.isFinite(icpScore) && icpScore > 75 && contactEmailCount <= 0;
  return {
    companyId: customer.company_id || String(customerRecord.companyId || ''),
    name: customerName,
    locationLabel: customerLocationLabel(country),
    regionalTime: customerRegionalTime(country, region),
    tag: textOf(customer.tag || payload.industry),
    contact: textOf(ownerName),
    border: needsContactEmail ? 'red' : 'blue',
    needsContactEmail,
    progress,
    stageRank: stageRank(stage),
    steps: ['已获得', '已邮件', '已回复', '会议', '方案', '成交'],
    dates: stageDatesToTimeline(customer.stageDates, outboundEmailCount, inboundEmailCount),
    latestInboundReply: customer.latestInboundReply,
    tasks: customer.tasks || [],
  };
};

const customers = computed(() => {
  // The API is already scoped to the signed-in sales owner.  Never substitute
  // shared demo cards for an empty result, otherwise two sales accounts could
  // appear to own the same customers.
  return homeCards.value
    .map(normalizeCustomer)
    .filter((customer) => customer.name !== '客户名称待确认');
});
const meetingCount = computed(() => customers.value.filter((customer) => customer.progress >= 65).length);
const latestMeetingRecord = computed(() => meeting.records[0] || null);
const meetingTotalDuration = computed(() => meeting.records.reduce((sum, item) => sum + Number(item.durationSeconds || 0), 0));

const formatDurationText = (seconds?: number) => {
  const total = Math.max(0, Math.round(Number(seconds || 0)));
  const minutes = Math.floor(total / 60);
  const rest = total % 60;
  return `${String(minutes).padStart(2, '0')}:${String(rest).padStart(2, '0')}`;
};

const formatMeetingDateText = (value?: string | null) => {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return `${date.getMonth() + 1}/${date.getDate()} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
};

const meetingAverageDuration = computed(() => {
  if (!meeting.records.length) return '00:00';
  return formatDurationText(meetingTotalDuration.value / meeting.records.length);
});

const meetingInsight = computed(() => summarizeMeetingValue(latestMeetingRecord.value?.summary) || '上传会议录音或视频后，这里会自动汇总本次会议重点');
const meetingNextStep = computed(() => (meeting.records.length ? '查看结构化纪要并继续跟进' : '上传会议录音'));

const meetingStatDemand = computed(() => {
  const latest = latestMeetingRecord.value;
  if (!latest) return '待判断';
  const actionCount = getMeetingActionItems(latest).length;
  if (actionCount > 2) return '强';
  if (actionCount > 0) return '中';
  return '待判断';
});

const trimMeetingText = (value: unknown, limit = 160) => {
  const text = summarizeMeetingValue(value).replace(/\s+/g, ' ').trim();
  if (!text) return '';
  return text.length > limit ? `${text.slice(0, limit - 1)}…` : text;
};

const formatMeetingItemText = (value: unknown) => {
  if (typeof value === 'string') return value.trim();
  if (!value || typeof value !== 'object') return String(value || '').trim();
  const item = value as Record<string, unknown>;
  const task = String(item.task || item.text || item.title || item.description || '').trim();
  const owner = String(item.owner || item.owner_name || item.ownerName || '').trim();
  const deadline = String(item.deadline || item.due || item.due_date || item.date || '').trim();
  const parts = [task];
  if (owner) parts.push(`负责人：${owner}`);
  if (deadline) parts.push(`截止：${deadline}`);
  return parts.filter(Boolean).join(' · ') || JSON.stringify(item);
};

const meetingSummaryParts = (record: MeetingRecord) => {
  const summary = (record.summary || {}) as Record<string, unknown>;
  const customerLine = `${meetingCustomer.value?.name || record.customerName || '客户'} · 上传录音/视频 · ${meetingCustomer.value?.tag || record.source || '会议分析服务'}`;
  const coreLine =
    summarizeMeetingValue(summary.core_summary || summary.coreSummary || summary.summary || summary.description || summary.text || '') ||
    summarizeMeetingValue(summary.key_summary || summary.keySummary || summary.highlight || summary.highlights || '') ||
    '暂无摘要';
  const nextLine =
    summarizeMeetingValue(summary.next_step || summary.nextStep || summary.action || summary.follow_up || summary.followUp || formatMeetingItemText(record.actionItems?.[0])) ||
    '查看结构化纪要并继续跟进';
  return { customerLine, coreLine, nextLine };
};

const meetingSummaryLines = (record: MeetingRecord) => {
  if (typeof record.summary === 'string') {
    return record.summary.split(/\r?\n+/).map((line) => line.trim()).filter(Boolean).slice(0, 8);
  }
  if (!record.summary || typeof record.summary !== 'object') return ['暂无摘要'];
  const summary = record.summary as Record<string, unknown>;
  const lines = [
    ...extractMeetingList(summary.customer_needs || summary.customerNeeds).map((item) => `客户需求：${item}`),
    ...extractMeetingList(summary.pain_points || summary.painPoints).map((item) => `客户痛点：${item}`),
    ...extractMeetingList(summary.buying_signals || summary.buyingSignals).map((item) => `购买信号：${item}`),
    ...extractMeetingList(summary.decisions).map((item) => `会议决策：${item}`),
  ];
  return lines.length ? lines.slice(0, 8) : [meetingSummaryParts(record).coreLine];
};

const getMeetingDecisions = (record: MeetingRecord) =>
  extractMeetingList((record as Record<string, unknown>).decisions || (record.summary as Record<string, unknown> | null)?.decisions || record.actionItems);

const getMeetingRisks = (record: MeetingRecord) =>
  extractMeetingList((record as Record<string, unknown>).risks || (record.summary as Record<string, unknown> | null)?.risks);

const getMeetingKeywords = (record: MeetingRecord) =>
  extractMeetingList((record as Record<string, unknown>).keywords || (record.summary as Record<string, unknown> | null)?.keywords);

const getMeetingRecordIndex = (record: MeetingRecord, index: number) => {
  const sorted = [...meeting.records]
    .filter(Boolean)
    .sort((a, b) => {
      const leftTime = new Date(a.createdAt || a.meeting_time || 0).getTime();
      const rightTime = new Date(b.createdAt || b.meeting_time || 0).getTime();
      if (leftTime !== rightTime) return leftTime - rightTime;
      return String(a.id || a.meeting_id || '').localeCompare(String(b.id || b.meeting_id || ''));
    });
  const target = sorted.findIndex((item) => (item.id || item.meeting_id) === (record.id || record.meeting_id));
  return target >= 0 ? target + 1 : index + 1;
};

const getMeetingActionItems = (record: MeetingRecord) => {
  const list = extractMeetingList((record as Record<string, unknown>).actionItems || (record.summary as Record<string, unknown> | null)?.action_items || (record.summary as Record<string, unknown> | null)?.actionItems);
  return list;
};

const getMeetingTranscriptSegments = (record: MeetingRecord) => {
  const rawSegments = Array.isArray((record as Record<string, unknown>).segments) ? ((record as Record<string, unknown>).segments as Array<Record<string, unknown>>) : [];
  if (rawSegments.length > 0) {
    return rawSegments
      .map((segment, index) => ({
        speaker: String(segment.speaker || segment.speaker_name || segment.role || `说话者${index + 1}`),
        start: Number(segment.start ?? segment.startSeconds ?? segment.begin ?? index * 12),
        end: Number(segment.end ?? segment.endSeconds ?? segment.finish ?? (index + 1) * 12),
        text: String(segment.text || segment.content || segment.transcript || '').trim(),
      }))
      .filter((segment) => segment.text);
  }

  const transcript = String(record.fullTranscript || record.transcript || '').trim();
  if (!transcript) return [];

  return transcript
    .split(/\r?\n+/)
    .map((line, index) => ({
      speaker: index % 2 === 0 ? '客户' : '销售',
      start: index * 8,
      end: index * 8 + 8,
      text: line.trim(),
    }))
    .filter((segment) => segment.text);
};

const getMeetingSegmentPage = (recordId: string, totalPages: number) => {
  const current = meetingSegmentPageState.value[recordId] ?? 0;
  return Math.min(Math.max(0, current), Math.max(0, totalPages - 1));
};

const setMeetingSegmentPage = (recordId: string, page: number) => {
  meetingSegmentPageState.value = {
    ...meetingSegmentPageState.value,
    [recordId]: Math.max(0, Number(page) || 0),
  };
};

const renderMeetingSegments = (record: MeetingRecord) => {
  const segments = getMeetingTranscriptSegments(record);
  if (segments.length === 0) {
    return [{
      speaker: '系统',
      start: 0,
      end: 0,
      text: record.fullTranscript || record.transcript || '当前这条录音已上传到后端，但还没有拿到文字内容。',
    }];
  }
  return segments;
};

const getMeetingSegmentView = (record: MeetingRecord, index: number) => {
  const recordId = String(record.id || record.meeting_id || record.title || index);
  const segments = getMeetingTranscriptSegments(record);
  const visibleSegments = segments.length > 0 ? segments : renderMeetingSegments(record);
  const totalPages = Math.max(1, Math.ceil(visibleSegments.length / 4));
  const currentPage = getMeetingSegmentPage(recordId, totalPages);
  return {
    recordId,
    segments: visibleSegments.slice(currentPage * 4, currentPage * 4 + 4),
    currentPage,
    totalPages,
  };
};

const playMeetingRecord = (record: MeetingRecord) => {
  if (!record.audioUrl) return;
  activeMeetingAudioUrl.value = record.audioUrl;
  meeting.message = `正在播放：${record.title || '会议录音'}`;
};

const deleteMeetingRecord = async (record: MeetingRecord) => {
  const recordId = record.id || record.meeting_id;
  if (!recordId) return;
  await meeting.deleteRecord(recordId);
};

const loadHomeCards = async () => {
  homeCardsError.value = '';
  homeCardsLoading.value = true;
  try {
    homeCards.value = (await operationApi.homeCards()).items || [];
    focusPendingEmailTarget();
  } catch (error) {
    homeCardsError.value = error instanceof Error ? error.message : '客户运营首页加载失败';
  } finally {
    homeCardsLoaded.value = true;
    homeCardsLoading.value = false;
  }
};

const focusPendingEmailTarget = () => {
  const target = legacyUi.pendingEmailTarget;
  if (!target) return;
  const customer = customers.value.find((item) => item.companyId === target.companyId);
  if (!customer) return;
  if (emailCustomer.value?.companyId !== customer.companyId) {
    openEmailDialog(customer);
  }
};

const extractEmailAddress = (value: string) => {
  const match = value.match(/<([^>]+)>/);
  return (match?.[1] || value).trim();
};

const emailContactFromHistory = (record: OperationEmail): EmailContact | null => {
  if (record.direction !== 'inbound') return null;
  const fromAddress = String(record.from_address || record.recipientEmail || '').trim();
  const email = extractEmailAddress(String(record.contact_email || fromAddress));
  const displayName = fromAddress.includes('<') ? fromAddress.split('<')[0].trim() : '';
  const name = String(record.contact_name || record.recipientName || displayName || email.split('@')[0] || '').trim();
  if (!email && !name) return null;
  const key = (email || name).toLowerCase();
  return {
    contactId: record.contact_id,
    key,
    name: name || email,
    email: email || '—',
    role: '邮件来信人',
    group: 'decision',
    initial: (name || email || '?').charAt(0).toUpperCase(),
  };
};

const syncPendingEmailHistoryTarget = () => {
  const target = legacyUi.pendingEmailTarget;
  if (!target || !emailCustomer.value || emailCustomer.value.companyId !== target.companyId) return false;
  if (!emailHistory.value.length) return false;
  const matched = emailHistory.value.find((record) => {
    const recordKey = getEmailHistoryKey(record);
    // Match on any identifier the notification target may carry. email_id is the
    // canonical id returned by the backend; id is often empty.
    return (
      (target.emailId && (record.email_id === target.emailId || record.id === target.emailId)) ||
      (target.messageId && (record.message_id === target.messageId || record.messageId === target.messageId)) ||
      (target.emailId && recordKey === target.emailId)
    );
  });
  if (matched) {
    selectedEmailHistory.value = matched;
    const sender = emailContactFromHistory(matched);
    if (sender) selectedEmailContact.value = sender;
    legacyUi.clearEmailTarget();
    return true;
  }
  return false;
};

const currentEmailContact = computed(() => selectedEmailContact.value || emailContactNodes.value.find((contact) => hasUsableEmail(contact.email)) || emailContactNodes.value[0] || emptyEmailContact);

const rosterRoleLabel = (role?: string | null) => ({
  procurement: '采购负责人',
  commercial: '商务负责人',
  business: '业务负责人',
  technical: '技术负责人',
  product: '产品负责人',
  operations: '运营负责人',
  finance_legal: '财务/法务',
  executive: '高层负责人',
  other: '备选联系人',
}[String(role || '')] || '待归类');

const outreachStatusLabel = (status?: string) => ({
  not_contacted: '未联系',
  scheduled: '待触达',
  sent: '已发送',
  replied: '已回复',
  meeting: '已参会',
  bounced: '已退信',
  opted_out: '已退订',
}[String(status || 'not_contacted')] || '未联系');

const rosterItemToEmailContact = (item: ContactRosterItem): EmailContact => ({
  contactId: item.contact_id,
  key: item.contact_id,
  name: item.full_name,
  email: item.source_primary_email || item.primary_email || '—',
  role: `${item.title || rosterRoleLabel(item.role_group)} · ${rosterRoleLabel(item.role_group)}`,
  group: item.role_group === 'technical' ? 'executor' : item.role_group === 'finance_legal' ? 'influencer' : 'decision',
  initial: (item.full_name || item.source_primary_email || item.primary_email || '?').charAt(0).toUpperCase(),
  position: item.position || undefined,
  score: Number(item.priority_score || 0),
  outreachStatus: item.outreach_status,
  pinned: Boolean(item.is_pinned),
  locked: Boolean(item.engagement_locked),
  recommendationReason: item.recommendation_reason || '',
});

const hasUsableEmail = (value?: string | null) => {
  const text = String(value || '').trim();
  return Boolean(text && text !== '—');
};

const operationContactEmailById = computed(() => {
  const lookup = new Map<string, string>();
  for (const contact of emailContacts.value) {
    if (!hasUsableEmail(contact.email)) continue;
    const contactId = String(contact.contact_id || '').trim().toLowerCase();
    const contactName = contactDisplayName(contact).trim().toLowerCase();
    const email = String(contact.email).trim();
    if (contactId) lookup.set(contactId, email);
    if (contactName) lookup.set(contactName, email);
  }
  return lookup;
});

const rosterItemToEmailContactWithFallback = (item: ContactRosterItem): EmailContact => {
  const contact = rosterItemToEmailContact(item);
  const fallbackEmail = operationContactEmailById.value.get(String(item.contact_id || '').trim().toLowerCase())
    || operationContactEmailById.value.get(String(item.full_name || '').trim().toLowerCase())
    || '';
  return fallbackEmail ? { ...contact, email: fallbackEmail, initial: (contact.name || fallbackEmail || '?').charAt(0).toUpperCase() } : contact;
};
const rosterItemHasEmail = (item: ContactRosterItem) => {
  if (hasUsableEmail(item.source_primary_email) || hasUsableEmail(item.primary_email)) return true;
  const fallbackEmail = operationContactEmailById.value.get(String(item.contact_id || '').trim().toLowerCase())
    || operationContactEmailById.value.get(String(item.full_name || '').trim().toLowerCase())
    || '';
  return hasUsableEmail(fallbackEmail);
};
const activeRosterContacts = computed(() => sortActiveRosterContacts(
  (contactRoster.value?.active || []).filter(rosterItemHasEmail),
));
const backupRosterContacts = computed(() => sortBackupRosterContacts(
  (contactRoster.value?.backup || []).filter(rosterItemHasEmail),
));

const emailContactNodes = computed<EmailContact[]>(() => {
  if (contactRoster.value?.initialized) {
    return activeRosterContacts.value.map(rosterItemToEmailContactWithFallback);
  }
  const seen = new Map<string, EmailContact>();
  const addSender = (name: string, email: string, role: string, contactId?: string) => {
    const cleanName = name.trim();
    const cleanEmail = email.trim();
    const dedupeKey = (cleanEmail || cleanName).toLowerCase();
    if (!dedupeKey || seen.has(dedupeKey)) return;
    seen.set(dedupeKey, {
      contactId,
      key: dedupeKey,
      name: cleanName || (cleanEmail ? cleanEmail.split('@')[0] : '未知来信人'),
      email: cleanEmail || '—',
      role: role || '邮件来信人',
      group: 'decision',
      initial: (cleanName || cleanEmail || '?').charAt(0).toUpperCase(),
    });
  };

  for (const contact of sortContacts(emailContacts.value as unknown as Record<string, unknown>[])) {
    addSender(contactDisplayName(contact), contactEmail(contact), contactTitle(contact) || '客户联系人', String(contact.contact_id || ''));
  }
  for (const record of emailHistory.value.filter((item) => item.direction === 'inbound')) {
    const sender = emailContactFromHistory(record);
    if (sender) addSender(sender.name, sender.email, sender.role, sender.contactId);
  }

  // Fallback to the customer's primary contact when the emails carried no sender info.
  if (!seen.size && emailCustomer.value) {
    const raw = emailCustomer.value.contact || '';
    const [namePart, ...roleParts] = raw.split('·');
    const name = namePart.trim();
    if (name && name !== '—') {
      addSender(name, '', roleParts.join('·').trim() || '客户联系人');
    }
  }

  return sortContacts(Array.from(seen.values()).map((contact) => ({ ...contact, title: contact.role }))) as EmailContact[];
});

const openEmailDialog = (customer: OperationCard) => {
  suppressEmailDraftDirty = true;
  if (emailDraftAutosaveTimer) window.clearTimeout(emailDraftAutosaveTimer);
  emailDraftAutosaveTimer = undefined;
  emailCustomer.value = customer;
  selectedEmailContact.value = null;
  emailSubject.value = `Re: Enterprise eSIM Solution for ${customer.name}`;
  emailDraft.value = '';
  emailPrompt.value = '';
  emailFeedback.value = '';
  emailTranslateOpen.value = false;
  emailTranslateMenuOpen.value = false;
  emailTranslationSubject.value = '';
  emailTranslation.value = '';
  emailAgentCandidate.value = null;
  emailAttachments.value = [];
  emailDrafts.value = [];
  emailDraftId.value = '';
  emailDraftVersion.value = null;
  emailDraftDirty.value = false;
  emailDraftSavedAt.value = '';
  savedEmailAttachments.value = [];
  emailDragActive.value = false;
  emailReplaceConfirmOpen.value = false;
  emailEditOpen.value = false;
  emailSendReceipt.value = null;
  emailRegenerating.value = false;
  emailPurpose.value = 'first_touch';
  emailAgentPendingPurpose.value = 'first_touch';
  contactRoster.value = null;
  contactRosterError.value = '';
  contactDrawerOpen.value = false;
  pendingRosterContact.value = null;
  replacementContactId.value = '';
  rosterActionReason.value = '';
  emailDragDepth = 0;
  selectedEmailHistory.value = null;
  void loadEmailHistory(customer);
};

const openMeetingRecord = (customer: OperationCard) => {
  const sourceCustomer = homeCards.value.find((item) => item.customerName === customer.name);
  const sourceRecord = sourceCustomer as unknown as Record<string, unknown> | undefined;
  const companyId = customer.companyId
    || sourceCustomer?.company_id
    || sourceCustomer?.companyId
    || String(sourceRecord?.companyId || '');
  meeting.selectedCustomerName = customer.name;
  meeting.selectedCompanyId = companyId || '';
  meeting.error = '';
  meeting.message = '';
  meeting.activeJob = null;
  void router.push('/meeting-analysis');
};

const openManualRecord = (customer: OperationCard) => {
  manualRecordCustomer.value = customer;
  manualRecordType.value = 'note';
  manualRecordNote.value = '';
  manualRecordTime.value = new Date().toISOString().slice(0, 16);
  manualRecordMessage.value = '';
  manualRecordFields.value = [];
  manualRecordUnidentified.value = '';
  manualRecordStep.value = 'input';
};

const closeManualRecord = () => {
  manualRecordCustomer.value = null;
  manualRecordMessage.value = '';
  manualRecordFields.value = [];
  manualRecordUnidentified.value = '';
  manualRecordStep.value = 'input';
};

const extractManualRecord = async () => {
  const customer = manualRecordCustomer.value;
  const companyId = customer?.companyId || '';
  if (!customer || !companyId || !manualRecordNote.value.trim()) {
    manualRecordMessage.value = companyId ? '请输入记录内容。' : '当前客户缺少公司标识，无法保存。';
    return;
  }
  manualRecordExtracting.value = true;
  manualRecordMessage.value = '';
  try {
    const result = await operationApi.extractManualNote(companyId, manualRecordNote.value.trim());
    manualRecordFields.value = (result.fields || []).map((field) => ({ ...field, selected: field.selected !== false }));
    manualRecordUnidentified.value = result.unidentified || '';
    manualRecordStep.value = 'review';
  } catch (error) {
    manualRecordMessage.value = error instanceof Error ? error.message : '提取失败，请稍后重试。';
  } finally {
    manualRecordExtracting.value = false;
  }
};

const confirmManualRecord = async () => {
  const customer = manualRecordCustomer.value;
  const companyId = customer?.companyId || '';
  if (!customer || !companyId) return;
  const selectedFields = manualRecordFields.value.filter((field) => field.selected !== false && field.extracted.trim());
  manualRecordSaving.value = true;
  manualRecordMessage.value = '';
  try {
    const result = await operationApi.confirmManualNote(companyId, manualRecordNote.value.trim(), selectedFields);
    manualRecordStep.value = 'saved';
    if (result.analysis.status === 'failed') {
      manualRecordMessage.value = `已确认 ${selectedFields.length} 条结构化信息，但客户分析更新失败，请稍后重试。`;
    } else if (result.analysis.status === 'completed') {
      manualRecordMessage.value = `已确认 ${selectedFields.length} 条结构化信息，客户分析报告已更新。`;
    } else if (result.analysis.status === 'running') {
      manualRecordMessage.value = `已确认 ${selectedFields.length} 条结构化信息，客户分析报告正在更新。`;
    } else {
      manualRecordMessage.value = `已确认 ${selectedFields.length} 条结构化信息，客户分析报告已进入更新队列。`;
    }
    const competitionField = selectedFields.find((field) => field.target === 'competition');
    if (competitionField) {
      saveManualNoteAnalysisState(createManualNoteAnalysisState(
        companyId,
        result.analysis.runId || '',
        competitionField.extracted,
        result,
      ));
    }
    await router.push(customerAnalysisRoute(companyId, { runId: result.analysis.runId || '' }));
  } catch (error) {
    manualRecordMessage.value = error instanceof Error ? error.message : '保存失败，请稍后重试。';
  } finally {
    manualRecordSaving.value = false;
  }
};

const closeOperationModal = () => {
  emailHistoryRequestId += 1;
  emailCustomer.value = null;
  meetingCustomer.value = null;
  selectedMeetingFile.value = null;
  meetingDragActive.value = false;
  meetingDragDepth = 0;
  activeMeetingAudioUrl.value = '';
  emailTranslateOpen.value = false;
  emailTranslateMenuOpen.value = false;
  emailAgentCandidate.value = null;
  emailAttachments.value = [];
  emailDragActive.value = false;
  emailDrafts.value = [];
  emailDraftId.value = '';
  emailDraftVersion.value = null;
  emailDraftDirty.value = false;
  emailDraftSavedAt.value = '';
  savedEmailAttachments.value = [];
  emailReplaceConfirmOpen.value = false;
  emailEditOpen.value = false;
  emailSendReceipt.value = null;
  emailDragDepth = 0;
  emailFeedback.value = '';
  meeting.error = '';
  meeting.message = '';
  meeting.activeJob = null;
  stopMeetingPolling();
  emailHistory.value = [];
  emailContacts.value = [];
  contactRoster.value = null;
  contactRosterError.value = '';
  contactDrawerOpen.value = false;
  emailHistoryError.value = '';
  selectedEmailHistory.value = null;
};

const formatDraftSavedTime = (value?: string | null) => {
  if (!value) return '刚刚';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '刚刚';
  return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
};

const clearEmailDraftAutosaveTimer = () => {
  if (emailDraftAutosaveTimer) window.clearTimeout(emailDraftAutosaveTimer);
  emailDraftAutosaveTimer = undefined;
};

const scheduleEmailDraftAutosave = () => {
  clearEmailDraftAutosaveTimer();
  emailDraftAutosaveTimer = window.setTimeout(() => {
    if (emailDraftDirty.value) void saveEmailDraft(false);
  }, 3000);
};

const markEmailDraftDirty = () => {
  emailDraftRevision += 1;
  emailDraftDirty.value = true;
  scheduleEmailDraftAutosave();
};

const applyGeneratedEmailAgentResult = (
  result: EmailAgentResult,
  purpose: 'first_touch' | 'reply_followup',
) => {
  emailSubject.value = result.subject || emailSubject.value;
  emailDraft.value = result.body;
  emailPurpose.value = purpose;
  emailAgentCandidate.value = null;
  emailAgentPendingPurpose.value = 'first_touch';
  emailTranslationSubject.value = '';
  emailTranslation.value = '';
  emailTranslateOpen.value = false;
  emailTranslateMenuOpen.value = false;
  emailReplaceConfirmOpen.value = false;
  selectedEmailHistory.value = null;
  markEmailDraftDirty();
};

const latestDraftForContact = (contactId?: string) => (
  emailDrafts.value.find((draft) => draft.contact_id === contactId) || null
);

const startFreshEmailDraftSession = (contact: EmailContact) => {
  suppressEmailDraftDirty = true;
  clearEmailDraftAutosaveTimer();
  emailDraftSessionVersion += 1;
  selectedEmailHistory.value = null;
  selectedEmailContact.value = contact;
  emailDraftId.value = '';
  emailDraftVersion.value = null;
  emailSubject.value = `Re: Enterprise eSIM Solution for ${emailCustomer.value?.name || ''}`;
  emailDraft.value = emailCustomer.value
    ? buildEmailDraft(emailCustomer.value, contact, currentSalesName.value)
    : '';
  emailPurpose.value = 'first_touch';
  savedEmailAttachments.value = [];
  emailAttachments.value = [];
  emailDraftDirty.value = false;
  emailDraftSavedAt.value = '';
  void nextTick(() => {
    syncEmailDraftEditor();
    suppressEmailDraftDirty = false;
  });
};

const applySavedDraft = (item: OperationEmailDraft) => {
  suppressEmailDraftDirty = true;
  clearEmailDraftAutosaveTimer();
  emailDraftSessionVersion += 1;
  selectedEmailHistory.value = null;
  emailDraftId.value = item.email_id;
  emailDraftVersion.value = item.version;
  emailSubject.value = item.subject || '';
  emailDraft.value = item.body_text || '';
  emailPurpose.value = item.purpose || 'first_touch';
  savedEmailAttachments.value = item.attachments || [];
  emailAttachments.value = [];
  const matchingContact = emailContactNodes.value.find((contact) => contact.contactId === item.contact_id);
  if (matchingContact) selectedEmailContact.value = matchingContact;
  emailDraftDirty.value = false;
  emailDraftSavedAt.value = item.updated_at || '';
  void nextTick(() => {
    syncEmailDraftEditor();
    suppressEmailDraftDirty = false;
  });
};

const switchEmailDraftContact = async (contact: EmailContact) => {
  if (!emailCustomer.value || selectedEmailHistory.value) return;
  if (currentEmailContact.value.contactId === contact.contactId) return;
  clearEmailDraftAutosaveTimer();
  if (emailDraftDirty.value) {
    const saved = await saveEmailDraft(false);
    if (!saved || emailDraftDirty.value) return;
  }
  const savedDraft = latestDraftForContact(contact.contactId);
  if (savedDraft) applySavedDraft(savedDraft);
  else startFreshEmailDraftSession(contact);
  emailFeedback.value = savedDraft
    ? `已切换到 ${contact.name}，已恢复该联系人的最近草稿`
    : `已切换到 ${contact.name}，已创建新的邮件草稿`;
  emailTranslateOpen.value = false;
  emailTranslateMenuOpen.value = false;
};

const saveEmailDraft = async (manual = true) => {
  if (!emailCustomer.value?.companyId || emailDraftSaving.value || selectedEmailHistory.value) return false;
  const contactId = currentEmailContact.value.contactId || '';
  if (!contactId) {
    if (manual) emailFeedback.value = '请先选择有效联系人，再保存草稿。';
    return false;
  }
  emailDraftSaving.value = true;
  const saveRevision = emailDraftRevision;
  const saveSessionVersion = emailDraftSessionVersion;
  if (manual) emailFeedback.value = '正在保存草稿...';
  try {
    const payload = {
      contactId,
      subject: emailSubject.value,
      body: emailDraft.value,
      purpose: emailPurpose.value,
      attachments: emailAttachments.value,
    };
    const item = emailDraftId.value && emailDraftVersion.value !== null
      ? await operationApi.updateEmailDraft(emailDraftId.value, emailDraftVersion.value, payload)
      : await operationApi.createEmailDraft(emailCustomer.value.companyId, payload);
    if (saveSessionVersion === emailDraftSessionVersion) {
      emailDraftId.value = item.email_id;
      emailDraftVersion.value = item.version;
      savedEmailAttachments.value = item.attachments || [];
      emailDraftSavedAt.value = item.updated_at || new Date().toISOString();
      if (saveRevision === emailDraftRevision) {
        emailDraftDirty.value = false;
        emailAttachments.value = [];
      }
    }
    emailDrafts.value = [item, ...emailDrafts.value.filter((draft) => draft.email_id !== item.email_id)];
    emailFeedback.value = `草稿已保存 ${formatDraftSavedTime(emailDraftSavedAt.value)}`;
    return saveRevision === emailDraftRevision;
  } catch (error) {
    emailFeedback.value = getApiErrorMessage(error, '草稿保存失败，请重试。');
    return false;
  } finally {
    emailDraftSaving.value = false;
    if (emailDraftDirty.value) scheduleEmailDraftAutosave();
  }
};

const requestCloseOperationModal = async () => {
  if (emailCustomer.value && emailDraftDirty.value && !selectedEmailHistory.value) {
    if (!window.confirm('当前邮件有未保存的修改，是否保存到草稿箱后关闭？')) return;
    const saved = await saveEmailDraft(false);
    if (!saved || emailDraftDirty.value) return;
  }
  closeOperationModal();
};

const removeSavedEmailAttachment = async (attachment: OperationEmailAttachment) => {
  if (!emailDraftId.value || emailDraftVersion.value === null) return;
  try {
    const item = await operationApi.deleteEmailDraftAttachment(
      emailDraftId.value, attachment.attachment_id, emailDraftVersion.value,
    );
    emailDraftVersion.value = item.version;
    savedEmailAttachments.value = item.attachments || [];
    emailDrafts.value = emailDrafts.value.map((draft) => draft.email_id === item.email_id ? item : draft);
    emailFeedback.value = `已移除附件：${attachment.filename}`;
  } catch (error) {
    emailFeedback.value = getApiErrorMessage(error, '附件删除失败。');
  }
};

const deleteSavedDraft = async (item: OperationEmailDraft) => {
  try {
    await operationApi.deleteEmailDraft(item.email_id, item.version);
    emailDrafts.value = emailDrafts.value.filter((draft) => draft.email_id !== item.email_id);
    if (emailDraftId.value === item.email_id) {
      startFreshEmailDraftSession(currentEmailContact.value);
    }
    emailFeedback.value = '草稿已删除。';
  } catch (error) {
    emailFeedback.value = getApiErrorMessage(error, '草稿删除失败。');
  }
};

const emailDeliveryStatusLabel = (record: OperationEmail) => {
  if (record.status === 'bounced' || record.deliveryStatus === 'bounced') return '退信';
  if (record.status === 'delivery_confirmed' || record.deliveryStatus === 'confirmed' || record.deliveryConfirmed) return '已确认投递';
  if (record.status === 'smtp_submitted' || record.status === 'sent' || record.smtpStatus === 'submitted') return '已提交 SMTP，待回执';
  return '';
};

const formatEmailHistoryTime = (record: OperationEmail) => {
  const value = record.sentAt || record.sent_at || record.repliedAt || record.replied_at || record.receivedAt || record.createdAt;
  if (!value) return '刚刚';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '刚刚';
  return `${date.getMonth() + 1}/${date.getDate()} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
};

const getEmailHistoryKey = (record: OperationEmail) =>
  record.id || record.email_id || record.sentAt || record.sent_at || record.receivedAt || record.createdAt || `${record.subject || ''}-${record.bodyPreview || ''}`;

const selectEmailHistoryRecord = (record: OperationEmail) => {
  const isSelected = getEmailHistoryKey(selectedEmailHistory.value || {}) === getEmailHistoryKey(record);
  selectedEmailHistory.value = isSelected ? null : record;
  if (!isSelected) {
    const sender = emailContactFromHistory(record);
    if (sender) selectedEmailContact.value = sender;
  }
  emailFeedback.value = '已打开历史邮件详情。';
};

const generateFromEmailHistory = async () => {
  const history = selectedEmailHistory.value;
  if (!history || !emailCustomer.value || emailRegenerating.value) return;

  const isInbound = history.direction === 'inbound';
  const originalSubject = String(history.subject || '').trim();
  const originalBody = String(history.body || history.bodyPreview || '').trim();
  const replySubject = originalSubject && !/^re:/i.test(originalSubject)
    ? `Re: ${originalSubject}`
    : originalSubject || `Re: ${emailCustomer.value.name}`;
  const instruction = isInbound
    ? '请根据这封客户来信生成一封专业、具体的回复。直接回应客户提出的问题，并给出清晰的下一步行动。'
    : '请基于这封已发送邮件生成一封自然的后续跟进邮件，避免机械重复原文，并给出清晰的下一步行动。';

  emailRegenerating.value = true;
  emailFeedback.value = isInbound ? 'AI 正在根据客户来信生成回复' : 'AI 正在生成后续跟进邮件';
  try {
    const result = await operationApi.runEmailAgent(buildEmailAgentPayload({
      customer: emailCustomer.value,
      contact: currentEmailContact.value,
      subject: replySubject,
      body: originalBody,
      instruction,
      operation: 'generate',
    }));
    applyGeneratedEmailAgentResult(result, 'reply_followup');
    emailPrompt.value = '';
    emailFeedback.value = isInbound ? '已生成客户回复并更新邮件内容。' : '已生成跟进邮件并更新邮件内容。';
  } catch (error) {
    emailFeedback.value = error instanceof Error
      ? `生成失败：${error.message}`
      : '生成失败，请稍后重试。';
  } finally {
    emailRegenerating.value = false;
  }
};

const loadEmailHistory = async (customer: OperationCard) => {
  const companyId = customer.companyId || '';
  const requestId = ++emailHistoryRequestId;
  emailHistoryLoading.value = true;
  contactRosterLoading.value = true;
  emailHistoryError.value = '';
  contactRosterError.value = '';
  try {
    const [historyResult, detailResult, rosterResult, draftsResult] = await Promise.allSettled([
      companyId ? operationApi.getEmailHistory(companyId) : Promise.resolve([]),
      companyId ? operationApi.getCustomerOperations(companyId) : Promise.resolve(null),
      companyId ? operationApi.getContactRoster(companyId) : Promise.resolve(null),
      companyId ? operationApi.getEmailDrafts(companyId) : Promise.resolve([]),
    ]);
    if (requestId !== emailHistoryRequestId || emailCustomer.value?.companyId !== companyId) return;
    emailHistory.value = historyResult.status === 'fulfilled' ? historyResult.value : [];
    emailDrafts.value = draftsResult.status === 'fulfilled' ? draftsResult.value : [];
    emailContacts.value = detailResult.status === 'fulfilled' ? detailResult.value?.contacts || [] : [];
    let roster = rosterResult.status === 'fulfilled' ? rosterResult.value : null;
    if (companyId && roster && !roster.initialized) {
      roster = await operationApi.recalculateContactRoster(companyId);
    }
    contactRoster.value = roster;
    if (rosterResult.status === 'rejected') {
      contactRosterError.value = rosterResult.reason instanceof Error ? rosterResult.reason.message : '联系人排序加载失败';
    }
    if (historyResult.status === 'rejected') throw historyResult.reason;
    const focusedPendingTarget = syncPendingEmailHistoryTarget();
    if (!focusedPendingTarget && emailDrafts.value.length) {
      applySavedDraft(emailDrafts.value[0]);
    } else if (!focusedPendingTarget && emailContactNodes.value.length) {
      const contact = emailContactNodes.value.find((item) => hasUsableEmail(item.email)) || emailContactNodes.value[0];
      startFreshEmailDraftSession(contact);
    }
    await nextTick();
    suppressEmailDraftDirty = false;
  } catch (error) {
    if (requestId !== emailHistoryRequestId || emailCustomer.value?.companyId !== companyId) return;
    emailHistory.value = [];
    emailHistoryError.value = error instanceof Error ? error.message : '历史邮件加载失败';
    suppressEmailDraftDirty = false;
  } finally {
    if (requestId === emailHistoryRequestId) {
      emailHistoryLoading.value = false;
      contactRosterLoading.value = false;
    }
  }
};

const applyRosterResult = (roster: ContactRoster) => {
  contactRoster.value = roster;
  const currentId = selectedEmailContact.value?.contactId;
  const currentActive = roster.active.find((item) => item.contact_id === currentId);
  if (currentActive) {
    selectedEmailContact.value = rosterItemToEmailContactWithFallback(currentActive);
  } else if (roster.active.length) {
    selectedEmailContact.value = rosterItemToEmailContactWithFallback(roster.active[0]);
  }
};

const resetContactDrawerForm = () => {
  manualContactForm.value = { fullName: '', title: '', department: '', email: '', linkedinUrl: '' };
  contactDrawerMode.value = 'manual';
  editingContactId.value = '';
  editingContactVersion.value = null;
};

const openContactDrawer = (mode: 'manual' | 'edit' = 'manual', item: ContactRosterItem | null = null) => {
  contactDrawerTab.value = 'manual';
  contactDrawerOpen.value = true;
  pendingRosterContact.value = null;
  replacementContactId.value = '';
  rosterActionReason.value = '';
  if (mode === 'edit' && item) {
    contactDrawerMode.value = 'edit';
    editingContactId.value = item.contact_id;
    editingContactVersion.value = Number(item.version || 0) || null;
    manualContactForm.value = {
      fullName: item.full_name || '',
      title: item.title || '',
      department: item.department || '',
      email: item.primary_email || '',
      linkedinUrl: item.linkedin_url || '',
    };
  } else {
    resetContactDrawerForm();
  }
};

const mutateRoster = async (
  item: ContactRosterItem,
  action: 'activate' | 'backup' | 'pin' | 'unpin' | 'move',
  options: { position?: number; replaceContactId?: string; reason?: string } = {},
) => {
  const companyId = emailCustomer.value?.companyId || '';
  if (!companyId || contactRosterWorking.value) return;
  contactRosterWorking.value = true;
  contactRosterError.value = '';
  try {
    const roster = await operationApi.mutateContactRoster(companyId, item.contact_id, {
      action,
      position: options.position,
      replace_contact_id: options.replaceContactId,
      reason: options.reason,
    });
    applyRosterResult(roster);
  } catch (error) {
    contactRosterError.value = getApiErrorMessage(error, '联系人操作失败');
  } finally {
    contactRosterWorking.value = false;
  }
};

const requestActivateRosterContact = async (item: ContactRosterItem) => {
  if ((contactRoster.value?.active.length || 0) < 5) {
    await mutateRoster(item, 'activate', { reason: '销售手动加入Top 5' });
    return;
  }
  pendingRosterContact.value = item;
  replacementContactId.value = contactRoster.value?.active
    .slice()
    .reverse()
    .find((contact) => !contact.is_pinned && !contact.engagement_locked)?.contact_id || '';
  rosterActionReason.value = '';
};

const confirmRosterReplacement = async () => {
  const item = pendingRosterContact.value;
  if (!item || !replacementContactId.value || !rosterActionReason.value.trim()) {
    contactRosterError.value = '请选择替换对象并填写替换原因。';
    return;
  }
  await mutateRoster(item, 'activate', {
    replaceContactId: replacementContactId.value,
    reason: rosterActionReason.value.trim(),
  });
  if (!contactRosterError.value) {
    pendingRosterContact.value = null;
    replacementContactId.value = '';
    rosterActionReason.value = '';
  }
};

const moveRosterContact = async (item: ContactRosterItem, delta: number) => {
  const target = Number(item.position || 0) + delta;
  if (target < 1 || target > (contactRoster.value?.active.length || 0)) return;
  await mutateRoster(item, 'move', { position: target, reason: '销售手动调整联系人顺位' });
};

const editRosterContact = (item: ContactRosterItem) => {
  openContactDrawer('edit', item);
};

const removeRosterContact = async (item: ContactRosterItem) => {
  const reason = window.prompt('\u8bf7\u8f93\u5165\u79fb\u51fa Top 5 \u7684\u539f\u56e0');
  if (!reason?.trim()) return;
  await mutateRoster(item, 'backup', { reason: reason.trim() });
};

const saveContactFromDrawer = async () => {
  const companyId = emailCustomer.value?.companyId || '';
  const form = manualContactForm.value;
  if (!companyId || !form.fullName.trim()) {
    contactRosterError.value = '\u8054\u7cfb\u4eba\u59d3\u540d\u4e0d\u80fd\u4e3a\u7a7a\u3002';
    return;
  }
  contactRosterWorking.value = true;
  contactRosterError.value = '';
  try {
    if (contactDrawerMode.value === 'edit' && editingContactId.value && editingContactVersion.value != null) {
      await operationApi.updateContact(companyId, editingContactId.value, editingContactVersion.value, {
        full_name: form.fullName.trim(),
        title: form.title.trim() || undefined,
        department: form.department.trim() || undefined,
        primary_email: form.email.trim() || undefined,
        linkedin_url: form.linkedinUrl.trim() || undefined,
      });
      const roster = await operationApi.recalculateContactRoster(companyId);
      applyRosterResult(roster);
      resetContactDrawerForm();
      contactDrawerOpen.value = false;
      return;
    }
    const created = await operationApi.createManualContact(companyId, {
      full_name: form.fullName.trim(),
      title: form.title.trim() || undefined,
      department: form.department.trim() || undefined,
      primary_email: form.email.trim() || undefined,
      linkedin_url: form.linkedinUrl.trim() || undefined,
      legal_basis_status: 'unknown',
    });
    const roster = await operationApi.getContactRoster(companyId);
    applyRosterResult(roster);
    resetContactDrawerForm();
    contactDrawerTab.value = 'recommended';
    const candidate = roster.backup.find((item) => item.contact_id === created.contact_id) || created;
    contactRosterWorking.value = false;
    await requestActivateRosterContact(candidate);
  } catch (error) {
    contactRosterError.value = getApiErrorMessage(error, contactDrawerMode.value === 'edit' ? '\u8054\u7cfb\u4eba\u66f4\u65b0\u5931\u8d25' : '\u624b\u52a8\u65b0\u589e\u8054\u7cfb\u4eba\u5931\u8d25');
  } finally {
    contactRosterWorking.value = false;
  }
};

const chooseMeetingFile = () => {
  if (!meetingFileInput.value) return;
  // Reset the native input so choosing the same recording again still emits change.
  meetingFileInput.value.value = '';
  meetingFileInput.value.click();
};

const handleMeetingFile = (event: Event) => {
  const file = (event.target as HTMLInputElement).files?.[0];
  selectedMeetingFile.value = file || null;
  meeting.error = '';
  meeting.message = file ? `已选择：${file.name}` : '';
};

const handleMeetingDragEnter = (event: DragEvent) => {
  event.preventDefault();
  meetingDragDepth += 1;
  meetingDragActive.value = true;
};

const handleMeetingDragOver = (event: DragEvent) => {
  event.preventDefault();
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy';
  meetingDragActive.value = true;
};

const handleMeetingDragLeave = (event: DragEvent) => {
  event.preventDefault();
  meetingDragDepth = Math.max(0, meetingDragDepth - 1);
  if (meetingDragDepth === 0) meetingDragActive.value = false;
};

const handleMeetingDrop = (event: DragEvent) => {
  event.preventDefault();
  meetingDragDepth = 0;
  meetingDragActive.value = false;
  const file = event.dataTransfer?.files?.[0] || null;
  selectedMeetingFile.value = file;
  meeting.error = '';
  meeting.message = file ? `已选择：${file.name}` : '';
};

const summarizeMeetingValue = (value: unknown): string => {
  if (!value) return '暂无摘要';
  if (typeof value === 'string') return value;
  if (Array.isArray(value)) return value.map((item) => summarizeMeetingValue(item)).join('；');
  if (typeof value === 'object') {
    const record = value as Record<string, unknown>;
    return String(record.text || record.summary || record.description || record.action || record.point || JSON.stringify(record));
  }
  return String(value);
};

const extractMeetingList = (value: unknown): string[] => {
  if (!value) return [];
  if (Array.isArray(value)) return value.map((item) => formatMeetingItemText(item)).filter(Boolean);
  if (typeof value === 'string') return value.split(/[；;\n]/).map((item) => item.trim()).filter(Boolean);
  if (typeof value === 'object') {
    const record = value as Record<string, unknown>;
    const fields = [record.items, record.decisions, record.risks, record.keywords, record.points, record.list];
    const fromFields = fields.flatMap((item) => extractMeetingList(item));
    if (fromFields.length) return fromFields;
    return [formatMeetingItemText(record)];
  }
  return [summarizeMeetingValue(value)];
};

const stopMeetingPolling = () => {
  if (meetingPollTimer) {
    window.clearTimeout(meetingPollTimer);
    meetingPollTimer = undefined;
  }
};

const changeMeetingSegmentPage = (recordId: string, delta: number) => {
  const record = meeting.records.find((item) => (item.id || item.meeting_id) === recordId);
  if (!record) return;
  const segments = renderMeetingSegments(record);
  if (segments.length <= 4) return;
  const totalPages = Math.max(1, Math.ceil(segments.length / 4));
  const current = getMeetingSegmentPage(recordId, totalPages);
  const next = Math.min(Math.max(0, current + delta), totalPages - 1);
  if (next === current) return;
  setMeetingSegmentPage(recordId, next);
};

const pollMeetingJob = (jobId: string) => {
  stopMeetingPolling();
  meetingPollTimer = window.setTimeout(async () => {
    const job = await meeting.pollJob(jobId);
    if (job && !['completed', 'error'].includes(job.status)) {
      pollMeetingJob(jobId);
      return;
    }
    if (job?.status === 'completed' && meetingCustomer.value) {
      await meeting.loadHistory(meetingCustomer.value.companyId, meetingCustomer.value.name);
    }
  }, 1800);
};

const uploadMeeting = async () => {
  if (!meetingCustomer.value) return;
  if (!selectedMeetingFile.value) {
    meeting.error = '请选择会议录音或视频文件。';
    return;
  }
  const companyId = meetingCustomer.value.companyId;
  if (!companyId) {
    meeting.error = '当前客户未关联公司 ID，请刷新客户运营列表后重试。';
    return;
  }
  meetingCustomer.value.companyId = companyId;
  const job = await meeting.upload(selectedMeetingFile.value, companyId, meetingCustomer.value.name);
  // The store already exposes the API error. Do not immediately clear it by
  // loading history when the upload failed and returned no job.
  if (meeting.error) return;
  if (job?.id) {
    pollMeetingJob(job.id);
  } else {
    await meeting.loadHistory(meetingCustomer.value.companyId, meetingCustomer.value.name);
  }
};

const selectEmailContact = (contact: EmailContact) => {
  void switchEmailDraftContact(contact);
};

const showHistoryEmail = (type: 'received' | 'sent') => {
  if (type === 'received') {
    emailDraft.value = `Sarah，您好：

收到您关于 coverage list 和 enterprise pricing 的问题。我们建议先确认 8 个国家的出行频次、预计激活人数和是否需要统一账单导出。

我会在邮件中附上覆盖清单、企业价格口径和 GDPR / SLA 摘要，方便您内部评估。

${currentSalesName.value}`;
    emailFeedback.value = '已载入客户回复场景，可继续生成跟进邮件。';
    return;
  }

  emailDraft.value = `Sarah，您好：

关于贵司 8 个国家的差旅通信管理，我们可以提供企业 eSIM、多国覆盖、统一后台和月度账单导出能力。

如果方便，我们可以先按试点国家和预估用量给出企业报价。

${currentSalesName.value}`;
  emailFeedback.value = '已载入历史触达邮件，可继续编辑或重新生成。';
};

const emailDraftTextFromEditor = (editor: HTMLElement) => editor.innerText.replace(/\r\n/g, '\n');

const updateEmailDraft = (event: Event) => {
  emailDraft.value = emailDraftTextFromEditor(event.target as HTMLElement);
};

const handleEmailDraftBeforeInput = (event: InputEvent) => {
  if (event.inputType !== 'insertParagraph' && event.inputType !== 'insertLineBreak') return;
  event.preventDefault();
  document.execCommand('insertText', false, '\n');
  if (event.target instanceof HTMLElement) {
    emailDraft.value = emailDraftTextFromEditor(event.target);
  }
};

const syncEmailDraftEditor = () => {
  const editor = emailDraftEditor.value;
  if (!editor) return;
  const value = selectedEmailHistory.value
    ? String(selectedEmailHistory.value.body || selectedEmailHistory.value.bodyPreview || '')
    : emailDraft.value;
  if (emailDraftTextFromEditor(editor) !== value) editor.textContent = value;
};

watch([emailDraft, selectedEmailHistory], () => {
  void nextTick(syncEmailDraftEditor);
}, { flush: 'post' });

const formatEmail = (command: 'bold' | 'italic' | 'underline') => {
  document.execCommand(command);
  emailFeedback.value = '已应用格式。';
};

const addEmailHint = (hint: string) => {
  emailPrompt.value = hint;
  regenerateEmail(hint);
};

const regenerateEmail = async (hint = emailPrompt.value) => {
  if (!emailCustomer.value || emailRegenerating.value) return;
  emailRegenerating.value = true;
  emailFeedback.value = 'AI正在根据你的指令重新生成';
  try {
    const operation = emailDraft.value.trim() ? 'rewrite' : 'generate';
    const result = await operationApi.runEmailAgent(buildEmailAgentPayload({
      customer: emailCustomer.value,
      contact: currentEmailContact.value,
      subject: emailSubject.value,
      body: emailDraft.value,
      instruction: hint,
      operation,
    }));
    applyGeneratedEmailAgentResult(result, 'first_touch');
    emailFeedback.value = '已根据指令更新邮件内容。';
  } catch (error) {
    emailFeedback.value = error instanceof Error ? `重新生成失败：${error.message}` : '重新生成失败，请稍后重试。';
  } finally {
    emailRegenerating.value = false;
    emailTranslateOpen.value = false;
    emailTranslateMenuOpen.value = false;
  }
};

const runEmailTranslation = async () => {
  const sourceSubject = emailSubject.value.trim();
  const sourceText = emailDraft.value.trim();
  if (!sourceText) {
    emailTranslateOpen.value = false;
    emailTranslation.value = '';
    emailAgentCandidate.value = null;
    emailFeedback.value = '请先生成或填写邮件正文，再进行翻译。';
    return;
  }

  emailTranslating.value = true;
  emailFeedback.value = '';
  try {
    const result = await operationApi.runEmailAgent(buildEmailAgentPayload({
      customer: emailCustomer.value || { name: '', tag: '' },
      contact: currentEmailContact.value,
      subject: sourceSubject,
      body: sourceText,
      operation: 'translate',
      targetLanguage: selectedTranslateLanguage.value.key,
    }));
    emailAgentCandidate.value = result;
    emailTranslationSubject.value = result.subject;
    emailTranslation.value = result.body;
    emailTranslateOpen.value = true;
    emailFeedback.value = '已生成' + selectedTranslateLanguage.value.name + '翻译结果。';
  } catch (error) {
    emailTranslationSubject.value = '';
    emailTranslation.value = '';
    emailAgentCandidate.value = null;
    emailTranslateOpen.value = false;
    emailFeedback.value = getApiErrorMessage(error, '邮件翻译失败，请稍后重试。');
  } finally {
    emailTranslating.value = false;
  }
};
const toggleTranslateMenu = () => {
  emailTranslateMenuOpen.value = !emailTranslateMenuOpen.value;
};

const closeTranslateMenuOutside = (event: MouseEvent) => {
  if (emailTranslateMenuOpen.value && emailTranslatePicker.value && !emailTranslatePicker.value.contains(event.target as Node)) {
    emailTranslateMenuOpen.value = false;
  }
};

const selectTranslateLanguage = (language: EmailTranslateLanguage) => {
  selectedTranslateLanguage.value = language;
  emailTranslateMenuOpen.value = false;
  void runEmailTranslation();
};

const translateEmail = () => {
  emailTranslateMenuOpen.value = false;
  if (emailTranslateOpen.value && emailTranslation.value) {
    emailTranslateOpen.value = false;
    emailFeedback.value = '已收起翻译结果。';
    return;
  }
  void runEmailTranslation();
};

const useEmailTranslation = () => {
  if (!emailTranslation.value) return;
  emailReplaceConfirmOpen.value = true;
};

const closeEmailReplaceConfirm = () => {
  emailReplaceConfirmOpen.value = false;
};

const confirmEmailReplacement = () => {
  if (emailAgentCandidate.value) {
    emailSubject.value = emailAgentCandidate.value.subject || emailSubject.value;
    emailDraft.value = emailAgentCandidate.value.body;
    emailPurpose.value = emailAgentPendingPurpose.value;
    emailAgentPendingPurpose.value = 'first_touch';
    emailAgentCandidate.value = null;
  } else if (emailTranslation.value) {
    emailSubject.value = emailTranslationSubject.value || emailSubject.value;
    emailDraft.value = emailTranslation.value;
  } else {
    return;
  }
  emailTranslateOpen.value = false;
  emailTranslateMenuOpen.value = false;
  emailReplaceConfirmOpen.value = false;
  emailFeedback.value = `已替换为${selectedTranslateLanguage.value.name}译文。`;
};

const copyEmailTranslation = async () => {
  if (!emailTranslation.value) return;
  try {
    await navigator.clipboard.writeText(
      [emailTranslationSubject.value, emailTranslation.value].filter(Boolean).join('\n\n'),
    );
    emailFeedback.value = `已复制${selectedTranslateLanguage.value.name}译文。`;
  } catch {
    emailFeedback.value = '复制失败，请检查浏览器剪贴板权限。';
  }
};

const openEmailEdit = () => {
  emailEditSubject.value = emailSubject.value;
  emailEditBody.value = emailDraft.value;
  emailEditOpen.value = true;
};

const closeEmailEdit = () => {
  emailEditOpen.value = false;
};

const applyEmailEdit = () => {
  if (!emailEditSubject.value.trim() || !emailEditBody.value.trim()) {
    emailFeedback.value = '邮件主题和正文不能为空。';
    return;
  }
  emailSubject.value = emailEditSubject.value.trim();
  emailDraft.value = emailEditBody.value.trim();
  emailEditOpen.value = false;
  emailFeedback.value = '已应用邮件修改。';
};

const addEmailAttachments = (files: FileList | File[]) => {
  const incoming = Array.from(files);
  if (!incoming.length) return;
  const existing = new Set(emailAttachments.value.map((file) => `${file.name}:${file.size}:${file.lastModified}`));
  const accepted = incoming.filter((file) => {
    const key = `${file.name}:${file.size}:${file.lastModified}`;
    if (existing.has(key)) return false;
    existing.add(key);
    return true;
  });
  emailAttachments.value = [...emailAttachments.value, ...accepted];
  if (accepted.length) markEmailDraftDirty();
  emailFeedback.value = accepted.length
    ? `已添加 ${accepted.length} 个附件。`
    : '所选附件已在列表中。';
};

const chooseEmailAttachments = () => {
  if (!emailAttachmentInput.value) return;
  emailAttachmentInput.value.value = '';
  emailAttachmentInput.value.click();
};

const handleEmailAttachmentSelection = (event: Event) => {
  const files = (event.target as HTMLInputElement).files;
  if (files) addEmailAttachments(files);
};

const removeEmailAttachment = (index: number) => {
  const removed = emailAttachments.value[index];
  emailAttachments.value = emailAttachments.value.filter((_, itemIndex) => itemIndex !== index);
  if (removed) markEmailDraftDirty();
  emailFeedback.value = removed ? `已移除附件：${removed.name}` : '';
};

const handleEmailDragEnter = (event: DragEvent) => {
  event.preventDefault();
  emailDragDepth += 1;
  emailDragActive.value = true;
};

const handleEmailDragOver = (event: DragEvent) => {
  event.preventDefault();
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy';
  emailDragActive.value = true;
};

const handleEmailDragLeave = (event: DragEvent) => {
  event.preventDefault();
  emailDragDepth = Math.max(0, emailDragDepth - 1);
  if (emailDragDepth === 0) emailDragActive.value = false;
};

const handleEmailDrop = (event: DragEvent) => {
  event.preventDefault();
  emailDragDepth = 0;
  emailDragActive.value = false;
  if (event.dataTransfer?.files) addEmailAttachments(event.dataTransfer.files);
};

const setEmailFeedback = (type: 'up' | 'down') => {
  emailFeedback.value = type === 'up' ? '已记录：这封邮件满意。' : '已记录：这封邮件需要继续优化。';
};

const sendEmail = async () => {
  if (!emailCustomer.value || emailSending.value) return;
  const contact = currentEmailContact.value;
  const recipientEmail = contact.email.trim();
  if (!recipientEmail || recipientEmail === '—') {
    emailFeedback.value = '当前联系人缺少有效邮箱，请先从来信记录中选择收件人。';
    return;
  }
  if (!emailSubject.value.trim() || !emailDraft.value.trim()) {
    emailFeedback.value = '邮件主题和正文不能为空。';
    return;
  }

  emailSending.value = true;
  emailFeedback.value = '正在发送邮件...';
  selectedEmailHistory.value = null;
  try {
    if (emailDraftDirty.value || !emailDraftId.value) {
      const saved = await saveEmailDraft(false);
      if (!saved || emailDraftDirty.value) return;
    }
    const result = await operationApi.sendEmail({
      companyId: emailCustomer.value.companyId,
      contactId: contact.contactId,
      customerName: emailCustomer.value.name,
      recipientName: contact.name,
      recipientEmail,
      to: recipientEmail,
      subject: emailSubject.value.trim(),
      body: emailDraft.value.trim(),
      purpose: emailPurpose.value,
      draftId: emailDraftId.value,
    });
    emailFeedback.value = result.message || `邮件已发送：${contact.name}`;
    emailSendReceipt.value = {
      messageId: result.record?.messageId || result.record?.message_id || '',
      traceId: result.traceId || '',
      deliveredTo: result.record?.deliveredTo || recipientEmail,
      provider: result.record?.provider || '',
    };
    emailAttachments.value = [];
    emailDraftId.value = '';
    emailDraftVersion.value = null;
    emailDraftDirty.value = false;
    emailDraftSavedAt.value = '';
    savedEmailAttachments.value = [];
    await loadEmailHistory(emailCustomer.value);
  } catch (error) {
    emailFeedback.value = error instanceof Error ? `发送失败：${error.message}` : '发送失败，请稍后重试。';
  } finally {
    emailSending.value = false;
  }
};

watch(
  [emailSubject, emailDraft, selectedEmailContact, emailPurpose],
  () => {
    if (suppressEmailDraftDirty || !emailCustomer.value || selectedEmailHistory.value) return;
    markEmailDraftDirty();
  },
  { deep: true },
);

onMounted(() => {
  document.addEventListener('click', closeTranslateMenuOutside);
  regionalClockTimer = window.setInterval(() => {
    clockNow.value = new Date();
  }, 60_000);
  void loadHomeCards();
});

onUnmounted(() => {
  document.removeEventListener('click', closeTranslateMenuOutside);
  if (regionalClockTimer) window.clearInterval(regionalClockTimer);
  clearEmailDraftAutosaveTimer();
});

watch(
  () => legacyUi.pendingEmailTarget,
  (target) => {
    if (!target) return;
    focusPendingEmailTarget();
    syncPendingEmailHistoryTarget();
  },
  { immediate: true, deep: true },
);

watch(
  () => customers.value,
  () => {
    focusPendingEmailTarget();
    syncPendingEmailHistoryTarget();
  },
  { deep: true },
);
</script>

<template>
  <div class="content-main legacy-operation">
    <div class="agent-live-bar">
      <div class="live-dot" />
      <span>客户运营 · 运行中</span>
      <div class="live-stat">
        <span>数量: <strong>{{ customers.length }}家</strong></span>
        <span>今日跟进: <strong>5次</strong></span>
        <span>今日会议: <strong>{{ meetingCount }}场</strong></span>
      </div>
    </div>

    <div class="operation-title-row">
      <div class="dashboard-title">客户运营</div>
    </div>

    <div v-if="homeCardsError" class="alert-error" role="alert">{{ homeCardsError }}</div>

    <div class="ai-monitor-strip">
      <div class="ai-pulse">
        <span />
      </div>
      <strong>AI Agent 实时监控中</strong>
    </div>

    <div class="operation-list">
    <div v-if="homeCardsLoading && !customers.length" class="operation-loading">正在加载客户运营数据...</div>
    <div v-else-if="!customers.length" class="operation-loading">暂无客户运营数据</div>
    <section v-for="customer in customers" :key="customer.companyId || customer.name" :class="['panel', 'operation-card', customer.border]">
      <div class="operation-head">
        <div class="operation-customer-identity">
          <span class="operation-location">{{ customer.locationLabel }}</span>
          <strong>{{ customer.name }}</strong>
          <span class="operation-region-time">{{ customer.regionalTime }}</span>
          </div>
        <span v-if="customer.needsContactEmail" class="contact-email-alert">需补齐联系人邮箱</span>
      </div>

      <div class="progress-bar operation-progress">
        <div class="fill" :style="{ width: `${customer.progress}%` }" />
      </div>
      <div class="operation-steps">
        <div v-for="(step, index) in customer.steps" :key="step" :class="{ done: index <= customer.stageRank }">
          <strong>{{ step }}</strong>
          <span>{{ customer.dates[index] }}</span>
        </div>
      </div>

      <div v-if="customer.latestInboundReply" class="latest-reply-card">
        <div class="latest-reply-heading">
          <strong>最新回复</strong>
          <span v-if="customer.latestInboundReply.intent" class="reply-intent-badge" :class="replyIntentClass(customer.latestInboundReply.intent)">{{ replyIntentLabel(customer.latestInboundReply.intent) }}</span>
        </div>
        <div class="latest-reply-subject">{{ customer.latestInboundReply.subject || '无主题' }}</div>
        <div class="latest-reply-body">{{ customer.latestInboundReply.body || '暂无回复内容' }}</div>
        <button class="btn-xs primary" type="button" @click="openEmailDialog(customer)">查看邮件</button>
      </div>

      <div v-if="customer.tasks.length" class="follow-up-task-card">
        <div class="follow-up-task-heading"><strong>跟进任务</strong><span>D0–D10</span></div>
        <div v-for="task in customer.tasks" :key="task.task_id" class="follow-up-task-row">
          <span class="follow-up-task-type">{{ task.task_type === 'meeting' ? '会议' : task.task_type === 'proposal' ? '方案' : '邮件' }}</span>
          <span class="follow-up-task-description">{{ task.description }}</span>
          <span class="follow-up-task-date">{{ task.due_date || '待安排' }}</span>
        </div>
      </div>

      <div class="card-actions">
        <button class="btn-xs primary" type="button" @click="openEmailDialog(customer)">邮件沟通</button>
        <button class="btn-xs primary" type="button" @click="openMeetingRecord(customer)">会议沟通</button>
        <button class="btn-xs primary" type="button" @click="openManualRecord(customer)">手动记录</button>
      </div>
    </section>
    </div>

    <div v-if="emailCustomer" id="emailDialog" class="email-workbench">
      <button class="fixed-close-btn" type="button" @click="requestCloseOperationModal">×</button>
      <div
        class="email-dialog-shell"
        @dragenter="handleEmailDragEnter"
        @dragover="handleEmailDragOver"
        @dragleave="handleEmailDragLeave"
        @drop="handleEmailDrop"
      >
        <div v-if="emailDragActive" class="email-drop-overlay" aria-live="polite">
          <strong>松开即可添加附件</strong>
          <span>文件将随本次邮件一起发送</span>
        </div>
        <aside class="email-left-panel">
          <div class="email-panel-title">
            <strong>联系人 {{ activeRosterContacts.length || emailContactNodes.length }}/5</strong>
            <button class="contact-add-button" type="button" title="添加联系人" aria-label="添加联系人" @click="() => openContactDrawer()">+</button>
          </div>

          <div class="email-recipient-card">
            <div class="email-section-label">收件人</div>
            <div class="email-recipient-row">
              <div class="email-avatar">{{ currentEmailContact.initial }}</div>
              <div>
                <strong>{{ currentEmailContact.name }}</strong>
                <span>{{ currentEmailContact.email }}</span>
              </div>
            </div>
          </div>

          <div class="email-contact-map contact-roster-panel">
            <div v-if="contactRosterLoading" class="email-map-empty">正在加载联系人...</div>
            <div v-else-if="contactRosterError" class="contact-roster-error">{{ contactRosterError }}</div>
            <div v-else-if="activeRosterContacts.length" class="contact-roster-list">
              <div
                v-for="(item, rosterIndex) in activeRosterContacts"
                :key="item.contact_id"
                :class="['contact-roster-row', { selected: currentEmailContact.contactId === item.contact_id }]"
              >
                <button class="contact-roster-select" type="button" @click="selectEmailContact(rosterItemToEmailContactWithFallback(item))">
                  <span class="contact-roster-rank">{{ rosterIndex + 1 }}</span>
                  <span class="contact-roster-main">
                    <strong>{{ item.full_name }}</strong>
                    <small>{{ item.title || rosterRoleLabel(item.role_group) }}</small>
                    <span>
                      <i>{{ outreachStatusLabel(item.outreach_status) }}</i>
                    </span>
                  </span>
                  <b :title="item.recommendation_reason || ''">{{ Math.round(Number(item.priority_score || 0)) }}</b>
                </button>
                <div class="contact-roster-actions">
                  <div class="contact-roster-actions-arrows">
                    <button type="button" title="上移" :disabled="item.position === 1 || contactRosterWorking" @click="moveRosterContact(item, -1)">↑</button>
                    <button type="button" title="下移" :disabled="item.position === activeRosterContacts.length || contactRosterWorking" @click="moveRosterContact(item, 1)">↓</button>
                  </div>
                  <button type="button" :disabled="contactRosterWorking" @click="mutateRoster(item, item.is_pinned ? 'unpin' : 'pin', { reason: item.is_pinned ? '销售取消置顶' : '销售手动置顶' })">{{ item.is_pinned ? '取消置顶' : '置顶' }}</button>
                  <button type="button" :disabled="contactRosterWorking" @click="editRosterContact(item)">编辑</button>
                  <button type="button" :disabled="item.is_pinned || item.engagement_locked || contactRosterWorking" @click="removeRosterContact(item)">移出</button>
                </div>
              </div>
            </div>
            <div v-else-if="!emailContactNodes.length" class="email-map-empty">暂无联系人</div>
            <div v-else class="email-sender-nodes">
              <button
                v-for="sender in emailContactNodes"
                :key="sender.key"
                :class="['email-contact-item', 'email-sender-node', { selected: currentEmailContact.key === sender.key }]"
                type="button"
                @click="selectEmailContact(sender)"
              >
                <span class="contact-avatar blue">{{ sender.initial }}</span>
                <span><strong>{{ sender.name }}</strong><small>{{ sender.email }}</small></span>
                <em>{{ sender.role }}</em>
              </button>
            </div>
            <button class="contact-view-all" type="button" @click="() => openContactDrawer()">查看全部联系人（{{ contactRoster?.total || emailContactNodes.length }}）</button>
          </div>

          <div class="email-history-pane email-draft-list-pane">
            <div class="email-section-title">草稿箱（{{ emailDrafts.length }}）</div>
            <div v-if="!emailDrafts.length" class="email-history-empty">暂无已保存草稿</div>
            <div
              v-for="item in emailDrafts"
              :key="item.email_id"
              :class="['email-draft-list-item', { active: emailDraftId === item.email_id }]"
            >
              <button type="button" @click="applySavedDraft(item)">
                <strong>{{ item.subject || '无主题草稿' }}</strong>
                <small>{{ formatDraftSavedTime(item.updated_at) }}</small>
              </button>
              <button type="button" :aria-label="`删除草稿 ${item.subject || '无主题'}`" @click="deleteSavedDraft(item)">×</button>
            </div>
          </div>

          <div class="email-history-pane">
            <div class="email-section-title">历史邮件</div>
            <div v-if="emailHistoryLoading" class="email-history-empty">正在加载历史邮件...</div>
            <div v-else-if="emailHistoryError" class="email-history-empty">{{ emailHistoryError }}</div>
            <div v-else-if="emailHistory.length === 0" class="email-history-empty">暂无历史邮件记录</div>
            <button
              v-for="record in emailHistory"
              :key="record.id || `${record.subject}-${record.sentAt || record.createdAt}`"
              :class="['email-history-item', record.direction === 'inbound' ? 'received' : 'sent', { active: selectedEmailHistory && getEmailHistoryKey(selectedEmailHistory) === getEmailHistoryKey(record) }]"
              type="button"
              @click="selectEmailHistoryRecord(record)"
            >
              <span>
                <strong>{{ record.direction === 'inbound' ? '收到 · 客户回复' : '发出 · 触达邮件' }}</strong>
                <small>{{ formatEmailHistoryTime(record) }}{{ emailDeliveryStatusLabel(record) ? ` · ${emailDeliveryStatusLabel(record)}` : '' }}</small>
              </span>
              <em>{{ record.bodyPreview || record.subject }}</em>
            </button>
          </div>
        </aside>

        <section class="email-right-panel">
          <div class="email-topbar">
            <span>收件人：<strong>{{ currentEmailContact.name }}</strong></span>
            <span v-if="selectedEmailHistory" class="email-history-mode-pill">历史邮件只读预览中</span>
          </div>
          <div class="email-subject-row">
            <span>Subject</span>
            <input v-model="emailSubject" />
          </div>
          <div class="email-formatbar">
            <button type="button" @click="formatEmail('bold')">B</button>
            <button type="button" @click="formatEmail('italic')"><i>I</i></button>
            <button type="button" @click="formatEmail('underline')"><u>U</u></button>
          </div>

          <div class="email-preview-stack">
            <div v-if="emailRegenerating" class="email-regenerating-mask" role="status" aria-live="assertive">
              <span class="email-regenerating-spinner" aria-hidden="true" />
              <strong>AI正在根据你的指令重新生成</strong>
            </div>
            <div class="email-preview-body">
              <div class="email-gradient-line" />
              <div class="email-feedback-box">
                <button title="满意" type="button" @click="setEmailFeedback('up')">👍</button>
                <button title="不满意" type="button" @click="setEmailFeedback('down')">👎</button>
              </div>
              <div class="email-draft-grid">
                <div class="email-draft-panel">
                  <div class="email-draft-head">
                    <span class="email-draft-title">{{ selectedEmailHistory ? '👁 历史邮件预览' : '✏️ 编辑邮件' }}</span>
                    <div class="email-draft-head-actions">
                      <span class="email-draft-lang">{{ selectedEmailHistory ? '只读' : '中文 · 内部编辑' }}</span>
                      <button
                        v-if="selectedEmailHistory"
                        class="primary"
                        type="button"
                        :disabled="emailRegenerating"
                        @click="generateFromEmailHistory"
                      >
                        {{ emailRegenerating
                          ? '生成中...'
                          : selectedEmailHistory.direction === 'inbound' ? 'AI 生成回复' : 'AI 生成跟进' }}
                      </button>
                      <button v-if="!selectedEmailHistory" type="button" @click="openEmailEdit">编辑</button>
                    </div>
                  </div>
                  <div
                    ref="emailDraftEditor"
                    id="emailAIContent"
                    class="email-draft-body"
                    :contenteditable="!selectedEmailHistory"
                    @beforeinput="handleEmailDraftBeforeInput"
                    @input="updateEmailDraft"
                  />
                  <div
                    v-if="selectedEmailHistory?.direction === 'inbound' && selectedEmailHistory.attachments?.length"
                    class="email-history-attachments"
                  >
                    <a
                      v-for="attachment in selectedEmailHistory.attachments"
                      :key="attachment.attachment_id"
                      :href="attachment.download_url"
                      target="_blank"
                      rel="noopener"
                    >
                      <strong>{{ attachment.filename }}</strong>
                      <span>{{ Math.max(1, Math.ceil(attachment.size_bytes / 1024)) }} KB · 下载</span>
                    </a>
                  </div>
                  <div v-if="!selectedEmailHistory" class="email-translate-bar">
                    <div ref="emailTranslatePicker" class="email-translate-picker">
                      <button :class="{ open: emailTranslateMenuOpen }" type="button" @click="toggleTranslateMenu">
                        🌐 翻译为 {{ selectedTranslateLanguage.name }} ▾
                      </button>
                      <div v-if="emailTranslateMenuOpen" class="email-translate-menu">
                        <button v-for="language in emailTranslateLanguages" :key="language.key" type="button" @click="selectTranslateLanguage(language)">
                          <span>{{ language.flag }}</span>
                          <strong>{{ language.name }}</strong>
                          <em>{{ language.sub }}</em>
                        </button>
                      </div>
                    </div>
                    <button class="email-translate-run" type="button" :disabled="emailTranslating" @click="translateEmail">
                      {{ emailTranslating ? '翻译中…' : (emailTranslateOpen ? '收起译文' : '生成译文') }}
                    </button>
                    <span>选择目标语言，即刻生成本地化版本</span>
                  </div>
                  <div v-if="emailTranslateOpen && !selectedEmailHistory" class="email-translate-result">
                    <div class="email-translate-result-head">
                      <strong>{{ selectedTranslateLanguage.flag }} {{ selectedTranslateLanguage.name }} 翻译结果</strong>
                      <div class="email-translate-result-actions">
                        <button type="button" @click="copyEmailTranslation">复制</button>
                        <button type="button" @click="useEmailTranslation">替换为译文</button>
                        <button type="button" aria-label="关闭翻译结果" @click="emailTranslateOpen = false">✕</button>
                      </div>
                    </div>
                    <div v-if="emailTranslationSubject" class="email-translate-result-subject">
                      <strong>主题：</strong>{{ emailTranslationSubject }}
                    </div>
                    <div class="email-translate-result-body">{{ emailTranslation }}</div>
                  </div>
                </div>
              </div>
              <div v-if="emailFeedback" class="email-feedback-text">{{ emailFeedback }}</div>
              <section v-if="emailSendReceipt" class="email-send-receipt" aria-label="发送跟踪">
                <div class="email-send-receipt-head"><strong>发送跟踪</strong><span>可用于日志和邮件服务排查</span></div>
                <dl>
                  <div><dt>Message-ID</dt><dd>{{ emailSendReceipt.messageId || '服务商未返回' }}</dd></div>
                  <div><dt>Trace-ID</dt><dd>{{ emailSendReceipt.traceId || '当前网关未返回' }}</dd></div>
                  <div><dt>实际投递</dt><dd>{{ emailSendReceipt.deliveredTo }}</dd></div>
                  <div v-if="emailSendReceipt.provider"><dt>提供方</dt><dd>{{ emailSendReceipt.provider }}</dd></div>
                </dl>
              </section>
            </div>

            <div v-if="!selectedEmailHistory" class="email-prompt-panel">
              <input ref="emailAttachmentInput" class="email-attachment-input" type="file" multiple @change="handleEmailAttachmentSelection" />
              <div :class="['email-attachment-zone', { active: emailDragActive }]" @click="chooseEmailAttachments">
                <button type="button" @click.stop="chooseEmailAttachments">添加附件</button>
                <span>点击选择或将文件拖入邮件窗口</span>
              </div>
              <div v-if="emailAttachments.length" class="email-attachment-list">
                <div v-for="(file, index) in emailAttachments" :key="`${file.name}-${file.size}-${file.lastModified}`">
                  <span><strong>{{ file.name }}</strong><small>{{ Math.max(1, Math.ceil(file.size / 1024)) }} KB</small></span>
                  <button type="button" :aria-label="`移除附件 ${file.name}`" @click="removeEmailAttachment(index)">×</button>
                </div>
              </div>
              <div v-if="savedEmailAttachments.length" class="email-attachment-list email-saved-attachment-list">
                <div v-for="attachment in savedEmailAttachments" :key="attachment.attachment_id">
                  <a :href="attachment.download_url" target="_blank" rel="noopener">
                    <strong>{{ attachment.filename }}</strong>
                    <small>{{ Math.max(1, Math.ceil(attachment.size_bytes / 1024)) }} KB · 已保存</small>
                  </a>
                  <button type="button" :aria-label="`删除已保存附件 ${attachment.filename}`" @click="removeSavedEmailAttachment(attachment)">×</button>
                </div>
              </div>
              <div class="email-prompt-row">
                <input id="emailPrompt" v-model="emailPrompt" placeholder="输入邮件调整要求" :disabled="emailRegenerating" @keyup.enter="regenerateEmail()" />
                <button class="btn-xs primary" type="button" :disabled="emailRegenerating" @click="regenerateEmail()">重新生成</button>
              </div>
              <div class="email-quick-prompts">
                <button
                  v-for="preset in EMAIL_REGENERATE_PRESETS"
                  :key="preset.prompt"
                  class="btn-xs"
                  type="button"
                  :disabled="emailRegenerating"
                  @click="addEmailHint(preset.prompt)"
                >{{ preset.label }}</button>
              </div>
            </div>
          </div>

          <div class="email-bottom-bar">
            <span class="email-draft-save-status">
              {{ emailDraftSaving ? '保存中...' : (emailDraftDirty ? '有未保存的修改' : (emailDraftSavedAt ? `已保存 ${formatDraftSavedTime(emailDraftSavedAt)}` : '')) }}
            </span>
            <button class="btn-outline" type="button" @click="requestCloseOperationModal">取消</button>
            <button class="btn-outline" type="button" :disabled="emailDraftSaving || !!selectedEmailHistory" @click="saveEmailDraft(true)">
              {{ emailDraftSaving ? '保存中...' : '保存草稿' }}
            </button>
            <button class="btn-xs primary" type="button" :disabled="emailSending" @click="sendEmail">
              {{ emailSending ? '发送中...' : '发送邮件' }}
            </button>
          </div>
        </section>

        <div v-if="contactDrawerOpen" class="contact-drawer-mask" @click.self="contactDrawerOpen = false">
          <aside class="contact-drawer" role="dialog" aria-modal="true" aria-labelledby="contact-drawer-title">
            <header>
              <div>
                <strong id="contact-drawer-title">联系人</strong>
                <span>{{ activeRosterContacts.length || 0 }}/5 · 共 {{ contactRoster?.total || 0 }} 人</span>
              </div>
              <button type="button" title="关闭" aria-label="关闭联系人抽屉" @click="contactDrawerOpen = false">×</button>
            </header>
            <div class="contact-drawer-tabs">
              <button :class="{ active: contactDrawerTab === 'recommended' }" type="button" @click="contactDrawerTab = 'recommended'">{{ '推荐联系人' }}</button>
              <button :class="{ active: contactDrawerTab === 'manual' }" type="button" @click="contactDrawerTab = 'manual'">{{ contactDrawerMode === 'edit' ? '编辑联系人' : '手动新增' }}</button>
            </div>

            <div v-if="contactRosterError" class="contact-roster-error drawer-error">{{ contactRosterError }}</div>

            <div v-if="contactDrawerTab === 'recommended'" class="contact-drawer-body">
              <div v-if="!backupRosterContacts.length" class="email-map-empty">暂无备用联系人</div>
              <template v-for="item in backupRosterContacts" :key="item.contact_id">
                <div class="contact-recommendation-row">
                  <div class="contact-recommendation-main">
                    <strong>{{ item.full_name }}</strong>
                    <span>{{ item.title || rosterRoleLabel(item.role_group) }}</span>
                    <small>{{ item.source || '未知来源' }} · {{ rosterRoleLabel(item.role_group) }}</small>
                    <em>{{ item.blocked_reason || item.recommendation_reason }}</em>
                  </div>
                  <b>{{ Math.round(Number(item.priority_score || 0)) }}</b>
                  <button type="button" :disabled="Boolean(item.blocked_reason) || contactRosterWorking" @click="requestActivateRosterContact(item)">
                    {{ item.blocked_reason ? '不可加入' : '加入' }}
                  </button>
                </div>

                <div v-if="pendingRosterContact?.contact_id === item.contact_id" class="contact-replacement-panel">
                  <strong>替换为 {{ pendingRosterContact.full_name }}</strong>
                  <label>
                    替换对象
                    <select v-model="replacementContactId">
                      <option value="">请选择</option>
                      <option
                        v-for="activeItem in activeRosterContacts"
                        :key="activeItem.contact_id"
                        :value="activeItem.contact_id"
                        :disabled="activeItem.is_pinned || activeItem.engagement_locked"
                      >{{ activeItem.position }}. {{ activeItem.full_name }}{{ activeItem.is_pinned || activeItem.engagement_locked ? '（已锁定）' : '' }}</option>
                    </select>
                  </label>
                  <label>
                    替换原因
                    <input v-model="rosterActionReason" maxlength="1000" />
                  </label>
                  <div>
                    <button type="button" @click="pendingRosterContact = null">取消</button>
                    <button class="primary" type="button" :disabled="contactRosterWorking" @click="confirmRosterReplacement">确认替换</button>
                  </div>
                </div>
              </template>
            </div>

            <form v-else class="contact-drawer-body contact-manual-form" @submit.prevent="saveContactFromDrawer">
              <label>姓名<input v-model="manualContactForm.fullName" required maxlength="300" /></label>
              <label>职位<input v-model="manualContactForm.title" maxlength="300" /></label>
              <label>部门<input v-model="manualContactForm.department" maxlength="200" /></label>
              <label>邮箱<input v-model="manualContactForm.email" type="email" maxlength="320" /></label>
              <label>LinkedIn<input v-model="manualContactForm.linkedinUrl" type="url" maxlength="500" /></label>
              <button class="primary" type="submit" :disabled="contactRosterWorking">{{ contactRosterWorking ? '\u4fdd\u5b58\u4e2d...' : (contactDrawerMode === 'edit' ? '\u4fdd\u5b58\u4fee\u6539' : '\u4fdd\u5b58\u5e76\u52a0\u5165') }}</button>
            </form>
          </aside>
        </div>

        <div v-if="emailReplaceConfirmOpen" class="email-confirm-mask" role="dialog" aria-modal="true" aria-labelledby="email-replace-title">
          <div class="email-confirm-dialog">
            <h3 id="email-replace-title">确认替换邮件内容</h3>
            <p>当前主题和正文将被{{ selectedTranslateLanguage.name }}译文覆盖，此操作不会发送邮件。</p>
            <div>
              <button type="button" @click="closeEmailReplaceConfirm">取消</button>
              <button class="primary" type="button" @click="confirmEmailReplacement">确认替换</button>
            </div>
          </div>
        </div>

        <div v-if="emailEditOpen" class="email-confirm-mask" role="dialog" aria-modal="true" aria-labelledby="email-edit-title">
          <div class="email-edit-dialog">
            <div class="email-edit-head"><h3 id="email-edit-title">编辑邮件</h3><button type="button" aria-label="关闭编辑邮件" @click="closeEmailEdit">✕</button></div>
            <label>主题<input v-model="emailEditSubject" /></label>
            <label>正文<textarea v-model="emailEditBody" rows="12" /></label>
            <div class="email-edit-actions">
              <button type="button" @click="closeEmailEdit">取消</button>
              <button class="primary" type="button" @click="applyEmailEdit">✓ 应用修改</button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <section v-if="meetingCustomer" class="meeting-record-page">
      <button class="meeting-record-page-close" type="button" aria-label="关闭会议沟通" @click="closeOperationModal">✕</button>
      <div class="meeting-record-page-inner">
          <div class="meeting-title-row">
            <div class="meeting-title-heading">
              <div>
              <div class="meeting-title">会议沟通记录</div>
              <div class="meeting-subtitle">客户：<strong>{{ meetingCustomer.name }}</strong></div>
              </div>
            </div>
          </div>

          <div class="meeting-prototype-upload-block">
            <label
              :class="['meeting-prototype-drop', { active: meetingDragActive }]"
              @click="chooseMeetingFile"
              @dragenter="handleMeetingDragEnter"
              @dragover="handleMeetingDragOver"
              @dragleave="handleMeetingDragLeave"
              @drop="handleMeetingDrop"
            >
              <span class="meeting-prototype-upload-icon" aria-hidden="true">📁</span>
              <span class="meeting-prototype-upload-copy">
                <strong>{{ meetingDragActive ? '松开即可上传会议文件' : '上传会议录音 / 录屏' }}</strong>
                <small>支持 MP3 / WAV / M4A 音频，或 MP4 / MOV / WebM 视频录屏</small>
              </span>
              <span v-if="selectedMeetingFile" class="meeting-prototype-file-chip">
                ✓ {{ selectedMeetingFile.name }}
              </span>
              <input ref="meetingFileInput" type="file" accept="audio/*,video/*,.mp3,.wav,.m4a,.mp4,.mov,.webm,.mkv,.avi" hidden @change="handleMeetingFile" />
            </label>

            <div class="meeting-prototype-ai-strip">
              <strong>✨ AI 会议分析</strong>
              <div class="meeting-prototype-ai-stats">
                <span>本月 <b>{{ meeting.records.length }}次</b> 会议 · 平均 <b>{{ meetingAverageDuration }}</b></span>
                <span>意向度：<b class="meeting-prototype-blue">{{ meetingStatDemand }}</b></span>
                <span>决策人参与率：<b>—</b></span>
                <span>下一步：<b>{{ meetingNextStep }}</b></span>
              </div>
              <button class="btn-xs primary meeting-prototype-analyze" type="button" :disabled="meeting.uploading || !selectedMeetingFile" @click="uploadMeeting">
                {{ meeting.uploading ? '分析中...' : '上传并分析' }}
              </button>
            </div>
          </div>

          <div class="meeting-status-row">
            <span class="meeting-status-chip">待开始</span>
            <span class="meeting-status-text">{{ meeting.message || '上传会议录音或视频后，将调用后端生成会议分析' }}</span>
          </div>

          <audio v-if="activeMeetingAudioUrl" class="meeting-audio" :src="activeMeetingAudioUrl" controls />

          <div v-if="meeting.error" class="alert-error" role="alert">{{ meeting.error }}</div>

          <div class="meeting-record-list">
            <article v-for="(record, index) in meeting.records" :key="record.id || record.meeting_id || record.title || index" class="meeting-record-card">
              <div class="meeting-record-head">
                <div class="meeting-record-head-meta">
                  <span class="meeting-record-index">会议录音 {{ getMeetingRecordIndex(record, index) }}</span>
                  <span class="meeting-record-time">{{ formatMeetingDateText(record.createdAt || record.meeting_time) }} · 时长 {{ formatDurationText(record.durationSeconds) }}</span>
                </div>
                <div class="meeting-record-actions">
                  <button v-if="record.audioUrl" class="btn-xs primary" type="button" @click="playMeetingRecord(record)">播放上传文件</button>
                  <button v-if="record.id || record.meeting_id" class="btn-xs" type="button" @click="deleteMeetingRecord(record)">删除</button>
                </div>
              </div>

              <div class="meeting-analysis-box">
                <div class="meeting-analysis-title">AI 会议摘要</div>
                <div class="meeting-analysis-body">
                  <div class="meeting-summary-line"><strong>1. 客户信息：</strong>{{ meetingSummaryParts(record).customerLine }}</div>
                  <div class="meeting-summary-block">
                    <strong>2. 核心纪要：</strong>
                    <div v-for="(line, lineIndex) in meetingSummaryLines(record)" :key="lineIndex" class="meeting-summary-item">{{ line }}</div>
                  </div>
                  <div class="meeting-summary-line"><strong>3. 下一步：</strong>{{ meetingSummaryParts(record).nextLine }}</div>
                </div>
              </div>

              <div class="meeting-legacy-grid">
                <div class="meeting-segment-panel">
                  <div class="meeting-section-label">逐段对话</div>
                  <div class="meeting-segment-list">
                    <div
                      v-for="segment in getMeetingSegmentView(record, index).segments"
                      :key="`${record.id || record.meeting_id || index}-${segment.start}-${segment.end}`"
                      class="meeting-segment-item"
                    >
                      <div style="display:flex;justify-content:space-between;gap:12px;margin-bottom:6px;">
                        <span style="font-size:11px;font-weight:700;color:var(--blue-primary);">{{ segment.speaker }}</span>
                        <span style="font-size:10px;color:var(--text-muted);">{{ formatDurationText(segment.start) }} - {{ formatDurationText(segment.end) }}</span>
                      </div>
                      <div style="font-size:12px;color:var(--text-secondary);white-space:pre-wrap;">{{ segment.text }}</div>
                    </div>
                  </div>
                  <div v-if="getMeetingSegmentView(record, index).totalPages > 1" class="meeting-segment-pagination">
                    <span class="meeting-segment-page-info">
                      第 {{ getMeetingSegmentView(record, index).currentPage + 1 }} / {{ getMeetingSegmentView(record, index).totalPages }} 页
                    </span>
                    <div class="meeting-segment-page-actions">
                      <button
                        type="button"
                        :disabled="getMeetingSegmentView(record, index).currentPage === 0"
                        class="btn-xs meeting-segment-page-button"
                        title="上一页"
                        aria-label="上一页"
                        @click="changeMeetingSegmentPage(getMeetingSegmentView(record, index).recordId, -1)"
                      >
                        ←
                      </button>
                      <button
                        type="button"
                        :disabled="getMeetingSegmentView(record, index).currentPage >= getMeetingSegmentView(record, index).totalPages - 1"
                        class="btn-xs meeting-segment-page-button"
                        title="下一页"
                        aria-label="下一页"
                        @click="changeMeetingSegmentPage(getMeetingSegmentView(record, index).recordId, 1)"
                      >
                        →
                      </button>
                    </div>
                  </div>
                </div>
                <div class="meeting-right-stack">
                  <div class="meeting-chip-panel meeting-chip-panel-green">
                    <div class="meeting-section-label">会议决策</div>
                    <div class="meeting-chip-list">
                      <span v-for="item in getMeetingDecisions(record)" :key="item">{{ item }}</span>
                      <span v-if="getMeetingDecisions(record).length === 0">暂无提取到会议决策</span>
                    </div>
                  </div>
                  <div class="meeting-chip-panel meeting-chip-panel-red">
                    <div class="meeting-section-label">风险提醒</div>
                    <div class="meeting-chip-list">
                      <span v-for="item in getMeetingRisks(record)" :key="item">{{ item }}</span>
                      <span v-if="getMeetingRisks(record).length === 0">暂无提取到风险</span>
                    </div>
                  </div>
                  <div class="meeting-chip-panel">
                    <div class="meeting-section-label">关键字</div>
                    <div class="meeting-keyword-list">
                      <span v-for="item in getMeetingKeywords(record)" :key="item">{{ item }}</span>
                      <span v-if="getMeetingKeywords(record).length === 0">暂无关键字</span>
                    </div>
                  </div>
                  <div class="meeting-chip-panel meeting-chip-panel-muted">
                    <div class="meeting-section-label">文件信息</div>
                    <div class="meeting-file-list">
                      <div>文件：{{ record.fileName || record.title || 'meeting-recording.webm' }}</div>
                      <div>来源：{{ record.source || '会议分析服务' }}</div>
                      <div>状态：{{ record.transcript_status || 'completed' }}</div>
                    </div>
                  </div>
                </div>
              </div>

            </article>
            <div v-if="meeting.records.length === 0" class="empty-inline">当前客户还没有真实会议分析结果。请上传会议录音或视频文件。</div>
          </div>
        </div>
    </section>

    <!-- Manual Record page (aligned with the prototype) -->
    <section v-if="manualRecordCustomer" class="manual-record-page">
      <div class="manual-record-page-header">
        <div class="manual-record-heading">
          <span class="manual-record-heading-icon" aria-hidden="true">📝</span>
          <div>
            <h1>手动记录</h1>
            <div class="manual-record-subtitle">客户：<strong>{{ manualRecordCustomer.name }}</strong></div>
          </div>
        </div>
        <button class="manual-record-page-close" type="button" aria-label="关闭手动记录" @click="closeManualRecord">×</button>
      </div>

      <div class="manual-record-divider" />

      <div class="manual-record-tip">
        <span aria-hidden="true">💡</span>
        <span><strong>使用说明：</strong>用自然语言记录在非正式场合了解到的客户信息，如展会交流、电话沟通、社交场合等。AI 会自动识别并提取为结构化字段，补充至客户分析报告的四大维度共 17 个信息点。</span>
      </div>

      <div v-if="manualRecordStep === 'input'" class="manual-record-content">
        <label for="manual-record-note">记录内容</label>
        <textarea id="manual-record-note" v-model="manualRecordNote" placeholder="例：今天在展会上碰到他们 CTO，聊到他们 Q3 要扩容东南亚团队，决策人其实是 CFO 不是 CTO，预算大概 5 万美金以内..." rows="7" />
      </div>

      <div v-else class="manual-record-review">
        <div class="manual-record-review-head">
          <div>提取结果</div>
          <button v-if="manualRecordStep === 'review'" type="button" @click="manualRecordStep = 'input'">返回修改原文</button>
        </div>
        <p v-if="!manualRecordFields.length" class="manual-record-empty">未自动识别出结构化字段，可返回修改原文后重新提取。</p>
        <label v-for="(field, index) in manualRecordFields" :key="`${field.dimension}-${index}`" class="manual-record-field">
          <input v-model="field.selected" type="checkbox" :disabled="manualRecordStep === 'saved'">
          <span class="manual-record-field-body">
            <span class="manual-record-field-meta">{{ field.dimension }}<small v-if="field.confidence != null">置信度 {{ Math.round(field.confidence * 100) }}%</small></span>
            <input v-model="field.extracted" type="text" :disabled="manualRecordStep === 'saved'" aria-label="提取值">
          </span>
        </label>
        <div v-if="manualRecordUnidentified && manualRecordUnidentified !== '（无）'" class="manual-record-unidentified">未匹配内容：{{ manualRecordUnidentified }}</div>
      </div>

      <div v-if="manualRecordMessage" class="manual-record-page-message">{{ manualRecordMessage }}</div>

      <div class="manual-record-page-actions">
        <button class="manual-record-cancel" type="button" @click="closeManualRecord">{{ manualRecordStep === 'saved' ? '关闭' : '取消记录' }}</button>
        <button v-if="manualRecordStep === 'input'" class="manual-record-submit" type="button" :disabled="!manualRecordNote.trim() || manualRecordExtracting" @click="extractManualRecord">{{ manualRecordExtracting ? '提取中...' : '提取匹配' }}</button>
        <button v-else-if="manualRecordStep === 'review'" class="manual-record-submit" type="button" :disabled="manualRecordSaving" @click="confirmManualRecord">{{ manualRecordSaving ? '保存中...' : '确认录入' }}</button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.operation-customer-identity {
  display: flex;
  min-width: 0;
  gap: 12px;
  align-items: baseline;
}
.operation-customer-identity strong {
  min-width: 0;
  overflow-wrap: anywhere;
  color: #172033;
  font-size: 15px;
}
.operation-location,
.operation-region-time {
  flex: none;
  color: #64748b;
  font-size: 11px;
}
.operation-location { color: #0369a1; font-weight: 700; }
.operation-region-time { margin-left: auto; }
.contact-email-alert {
  flex: none;
  padding: 4px 9px;
  color: #b91c1c;
  font-size: 12px;
  font-weight: 700;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 4px;
}
.email-preview-stack { position: relative; }
.email-regenerating-mask {
  position: absolute;
  inset: 0;
  z-index: 90;
  display: flex;
  gap: 10px;
  align-items: center;
  justify-content: center;
  color: #075985;
  background: rgba(255, 255, 255, 0.96);
}
.email-regenerating-mask strong { font-size: 15px; }
.email-regenerating-spinner {
  width: 20px;
  height: 20px;
  border: 2px solid #bae6fd;
  border-top-color: #0284c7;
  border-radius: 50%;
  animation: email-regenerating-spin 0.8s linear infinite;
}
@keyframes email-regenerating-spin { to { transform: rotate(360deg); } }
.email-drop-overlay {
  position: absolute; inset: 12px; z-index: 560; display: grid; place-content: center; gap: 6px;
  text-align: center; pointer-events: none; color: #075985; background: rgba(240, 249, 255, 0.96);
  border: 2px dashed #0284c7; border-radius: 8px;
}
.email-drop-overlay strong { font-size: 18px; }
.email-drop-overlay span { font-size: 12px; color: #47748a; }
.email-feedback-box { top: 62px; }
.email-draft-head-actions, .email-translate-result-actions { display: flex; gap: 6px; align-items: center; }
.email-draft-body { white-space: pre-wrap; }
.email-draft-head-actions button, .email-translate-result-actions button {
  padding: 4px 8px; color: #075985; font-size: 11px; cursor: pointer; background: #fff;
  border: 1px solid #bae6fd; border-radius: 5px;
}
.email-history-attachments { display: grid; gap: 6px; padding: 10px 14px; border-top: 1px solid #e2e8f0; }
.email-history-attachments a { display: flex; justify-content: space-between; gap: 12px; padding: 8px 10px; color: #0369a1; text-decoration: none; background: #f0f9ff; border: 1px solid #bae6fd; border-radius: 6px; }
.email-history-attachments a:hover { background: #e0f2fe; }
.email-history-attachments span { color: #64748b; font-size: 11px; white-space: nowrap; }
.email-draft-list-pane { border-bottom: 1px solid #e2e8f0; }
.email-draft-list-item { display: flex; align-items: stretch; gap: 4px; padding: 4px 8px; }
.email-draft-list-item > button:first-child { display: grid; flex: 1; gap: 3px; min-width: 0; padding: 8px; text-align: left; background: #fff; border: 1px solid #e2e8f0; border-radius: 6px; }
.email-draft-list-item > button:first-child strong { overflow: hidden; color: #334155; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.email-draft-list-item > button:first-child small { color: #94a3b8; font-size: 10px; }
.email-draft-list-item.active > button:first-child { background: #eff6ff; border-color: #93c5fd; }
.email-draft-list-item > button:last-child { padding: 0 7px; color: #94a3b8; background: transparent; border: 0; }
.email-saved-attachment-list a { display: grid; flex: 1; color: inherit; text-decoration: none; }
.email-draft-save-status { flex: 1; color: #64748b; font-size: 11px; }
.email-attachment-input { display: none; }
.email-attachment-zone {
  display: flex; gap: 8px; align-items: center; padding: 8px 10px; margin-bottom: 8px; cursor: pointer;
  color: #64748b; font-size: 11px; background: #f8fafc; border: 1px dashed #94a3b8; border-radius: 6px;
}
.email-attachment-zone.active { color: #0369a1; background: #f0f9ff; border-color: #0284c7; }
.email-attachment-zone button { padding: 4px 8px; cursor: pointer; background: #fff; border: 1px solid #cbd5e1; border-radius: 5px; }
.email-attachment-list { display: grid; gap: 5px; margin-bottom: 8px; }
.email-attachment-list > div {
  display: flex; justify-content: space-between; align-items: center; padding: 6px 8px; background: #fff; border: 1px solid #e2e8f0; border-radius: 5px;
}
.email-attachment-list span { display: flex; min-width: 0; gap: 8px; align-items: center; }
.email-attachment-list strong { max-width: 360px; overflow: hidden; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.email-attachment-list small { color: #94a3b8; font-size: 10px; }
.email-attachment-list button { width: 24px; height: 24px; cursor: pointer; color: #64748b; background: transparent; border: 0; }
.email-confirm-mask {
  position: absolute; inset: 0; z-index: 570; display: grid; place-items: center; padding: 20px; background: rgba(15, 23, 42, 0.48);
}
.email-confirm-dialog, .email-edit-dialog { width: min(480px, 100%); padding: 20px; background: #fff; border-radius: 8px; box-shadow: 0 18px 48px rgba(15, 23, 42, 0.24); }
.email-confirm-dialog h3, .email-edit-dialog h3 { margin: 0; color: #172033; font-size: 16px; }
.email-confirm-dialog p { margin: 10px 0 18px; color: #64748b; font-size: 13px; line-height: 1.6; }
.email-confirm-dialog > div, .email-edit-actions { display: flex; gap: 8px; justify-content: flex-end; }
.email-confirm-dialog button, .email-edit-dialog button { padding: 7px 12px; cursor: pointer; background: #fff; border: 1px solid #cbd5e1; border-radius: 6px; }
.email-confirm-dialog button.primary, .email-edit-dialog button.primary { color: #fff; background: #0284c7; border-color: #0284c7; }
.email-edit-dialog { width: min(660px, 100%); }
.email-edit-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
.email-edit-head button { padding: 4px 8px; border: 0; }
.email-edit-dialog label { display: grid; gap: 6px; margin-bottom: 12px; color: #475569; font-size: 12px; font-weight: 700; }
.email-edit-dialog input, .email-edit-dialog textarea { box-sizing: border-box; width: 100%; padding: 9px 10px; color: #172033; font: inherit; border: 1px solid #cbd5e1; border-radius: 6px; outline: none; }
.email-edit-dialog textarea { resize: vertical; line-height: 1.55; }
.email-edit-dialog input:focus, .email-edit-dialog textarea:focus { border-color: #0284c7; box-shadow: 0 0 0 3px rgba(2, 132, 199, 0.12); }
.email-translate-menu { z-index: 80; }
.meeting-prototype-drop.active { color: #0369a1; background: #f0f9ff; border-color: #0284c7; box-shadow: 0 0 0 3px rgba(2, 132, 199, 0.12); }
.email-send-receipt { padding: 10px 12px; margin-top: 8px; color: #334155; background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 6px; }
.email-send-receipt-head { display: flex; gap: 8px; align-items: baseline; margin-bottom: 8px; }
.email-send-receipt-head strong { color: #166534; font-size: 12px; }
.email-send-receipt-head span { color: #64748b; font-size: 10px; }
.email-send-receipt dl { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px 14px; margin: 0; }
.email-send-receipt dl > div { min-width: 0; }
.email-send-receipt dt { color: #64748b; font-size: 9px; text-transform: uppercase; }
.email-send-receipt dd { margin: 2px 0 0; overflow-wrap: anywhere; color: #1e293b; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 10px; line-height: 1.4; }
@media (max-width: 760px) { .email-send-receipt dl { grid-template-columns: 1fr; } }

.manual-record-page {
  position: fixed;
  inset: 0;
  z-index: 500;
  margin-left: 240px;
  padding: 34px 38px 48px;
  overflow-y: auto;
  background: #eef6ff;
  color: #16233d;
}
.manual-record-page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  max-width: 1670px;
  margin: 0 auto;
}
.manual-record-heading { display: flex; gap: 14px; align-items: flex-start; }
.manual-record-heading-icon { font-size: 32px; line-height: 1.1; }
.manual-record-heading h1 { margin: 0; font-size: 28px; line-height: 1.2; font-weight: 800; }
.manual-record-subtitle { margin-top: 5px; color: #8a98ad; font-size: 15px; }
.manual-record-subtitle strong { color: #16233d; }
.manual-record-page-close {
  width: 48px; height: 48px; border: 1px solid #d5e0ef; border-radius: 10px;
  background: #fff; color: #9aaac0; font-size: 34px; font-weight: 300; line-height: 1;
  cursor: pointer; box-shadow: 0 2px 6px rgba(40, 72, 110, 0.08);
}
.manual-record-page-close:hover { color: #315b91; border-color: #a9c0de; }
.manual-record-divider { max-width: 1670px; height: 2px; margin: 28px auto 30px; background: #c7d8ed; }
.manual-record-tip {
  display: flex; gap: 8px; align-items: flex-start; max-width: 1670px; margin: 0 auto 28px;
  padding: 21px 27px; border: 1px solid #d4dfed; border-radius: 14px;
  background: linear-gradient(105deg, #edf7ff 0%, #fffaf0 100%); color: #53647b; font-size: 16px; line-height: 1.65;
}
.manual-record-tip > span:first-child { font-size: 19px; line-height: 1.5; }
.manual-record-tip strong { color: #31435e; }
.manual-record-content { max-width: 1670px; margin: 0 auto; }
.manual-record-content label { display: block; margin-bottom: 13px; font-size: 16px; font-weight: 800; }
.manual-record-content textarea {
  display: block; width: 100%; min-height: 176px; resize: vertical; box-sizing: border-box;
  padding: 22px 20px; border: 2px solid #c7d5e6; border-radius: 14px; outline: none;
  background: #fff; color: #26354d; font: inherit; font-size: 16px; line-height: 1.65;
}
.manual-record-content textarea:focus { border-color: #70a7e4; box-shadow: 0 0 0 3px rgba(77, 144, 219, 0.12); }
.manual-record-content textarea::placeholder { color: #8996a7; opacity: 1; }
.manual-record-page-message { max-width: 1670px; margin: 14px auto 0; color: #1b7a58; font-size: 14px; }
.manual-record-review { max-width: 1000px; margin: 0 auto; }
.manual-record-review-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; font-size: 17px; font-weight: 800; }
.manual-record-review-head button { border: 0; background: transparent; color: #087ca1; cursor: pointer; }
.manual-record-field { display: flex; gap: 12px; align-items: flex-start; margin-bottom: 10px; padding: 14px; border: 1px solid #cad8e8; border-radius: 8px; background: #fff; }
.manual-record-field > input { width: 18px; height: 18px; margin-top: 25px; accent-color: #078fae; }
.manual-record-field-body { display: grid; flex: 1; gap: 6px; min-width: 0; }
.manual-record-field-meta { display: flex; justify-content: space-between; gap: 12px; color: #31435e; font-weight: 700; }
.manual-record-field-meta small { color: #718096; font-weight: 500; }
.manual-record-field-body input { width: 100%; box-sizing: border-box; padding: 9px 10px; border: 1px solid #bacbdf; border-radius: 6px; color: #25334a; font: inherit; }
.manual-record-unidentified, .manual-record-empty { padding: 12px 14px; border: 1px solid #e1cda6; border-radius: 8px; background: #fff9e9; color: #68582e; }
.manual-record-page-actions { display: flex; gap: 12px; justify-content: flex-end; max-width: 1670px; margin: 22px auto 0; }
.manual-record-cancel, .manual-record-submit {
  border-radius: 7px; padding: 8px 14px; font-size: 13px; font-weight: 700; cursor: pointer;
}
.manual-record-cancel { border: 1px solid #d5dfeb; background: #fff; color: #4d5c70; }
.manual-record-submit { border: 1px solid #0a9ec7; background: #06a7cb; color: #fff; box-shadow: 0 3px 8px rgba(0, 145, 190, 0.2); }
.manual-record-submit:disabled { opacity: 0.5; cursor: not-allowed; }
@media (max-width: 900px) {
  .manual-record-page { margin-left: 0; padding: 24px 18px 36px; }
  .manual-record-tip { font-size: 14px; padding: 16px; }
  .manual-record-heading h1 { font-size: 24px; }
}
@media (min-width: 901px) and (max-width: 1280px) {
  .manual-record-page { margin-left: 220px; }
}
@media (min-width: 901px) and (max-width: 1080px) {
  .manual-record-page { margin-left: 0; }
}

.meeting-record-page {
  position: fixed;
  top: 48px;
  right: 0;
  bottom: 0;
  left: 240px;
  z-index: 500;
  overflow-y: auto;
  background: var(--bg-base);
}
.meeting-record-page-inner {
  width: min(1600px, calc(100% - 80px));
  margin: 0 auto;
  padding: 28px 0 48px;
}
.meeting-record-page-close {
  position: fixed;
  top: 16px;
  right: 16px;
  z-index: 2;
  padding: 8px 16px;
  color: var(--text-muted);
  font-size: 13px;
  cursor: pointer;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: 0 2px 6px rgba(15, 23, 42, 0.08);
}
.meeting-record-page-close:hover { color: var(--blue-primary); border-color: var(--blue-primary); }
.meeting-record-page .meeting-title-row {
  align-items: center;
  padding-bottom: 16px;
  margin-bottom: 28px;
  border-bottom: 2px solid var(--border);
}
.meeting-title-heading { display: flex; gap: 12px; align-items: center; }
.meeting-prototype-upload-block { display: grid; gap: 14px; margin-bottom: 28px; }
.meeting-prototype-drop {
  display: flex;
  gap: 12px;
  align-items: center;
  min-width: 0;
  padding: 14px 18px;
  cursor: pointer;
  background: var(--bg-card);
  border: 2px dashed var(--blue-primary);
  border-radius: var(--radius);
}
.meeting-prototype-drop:hover { background: #f5fbff; }
.meeting-prototype-upload-icon {
  display: grid;
  width: 40px;
  height: 40px;
  flex: 0 0 40px;
  place-items: center;
  color: #fff;
  font-size: 18px;
  background: var(--tuge-gradient);
  border-radius: 50%;
  box-shadow: 0 0 16px rgba(37, 99, 235, 0.3);
}
.meeting-prototype-upload-copy { display: grid; gap: 2px; min-width: 0; flex: 1; }
.meeting-prototype-upload-copy strong { color: var(--blue-primary); font-size: 14px; }
.meeting-prototype-upload-copy small { overflow: hidden; color: var(--text-muted); font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.meeting-prototype-file-chip {
  max-width: 240px;
  overflow: hidden;
  padding: 5px 12px;
  color: var(--blue-primary);
  font-size: 11px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
  background: #f0f9ff;
  border-radius: 999px;
}
.meeting-prototype-ai-strip {
  display: flex;
  gap: 32px;
  align-items: center;
  padding: 18px 24px;
  background: #f0f9ff;
  border: 1px solid var(--border);
  border-radius: var(--radius);
}
.meeting-prototype-ai-strip > strong { flex: 0 0 auto; font-size: 15px; white-space: nowrap; }
.meeting-prototype-ai-stats { display: flex; flex: 1; gap: 28px; align-items: center; min-width: 0; color: var(--text-secondary); font-size: 12px; }
.meeting-prototype-ai-stats span { white-space: nowrap; }
.meeting-prototype-ai-stats b { color: var(--text-main); }
.meeting-prototype-ai-stats .meeting-prototype-blue { color: var(--blue-primary); }
.meeting-prototype-analyze { flex: 0 0 auto; }
.meeting-record-page .meeting-record-list { display: flex; flex-direction: column; gap: 20px; margin-bottom: 28px; }
.meeting-record-page .meeting-record-card { padding: 24px; border-radius: var(--radius); box-shadow: var(--shadow-sm); }
@media (max-width: 1280px) {
  .meeting-record-page { left: 220px; }
  .meeting-record-page-inner { width: calc(100% - 48px); }
  .meeting-prototype-ai-strip { gap: 18px; }
  .meeting-prototype-ai-stats { gap: 14px; }
}
@media (max-width: 1080px) {
  .meeting-record-page { top: 0; left: 0; }
  .meeting-record-page-inner { width: calc(100% - 32px); padding-top: 24px; }
  .meeting-prototype-ai-strip { align-items: flex-start; flex-direction: column; }
  .meeting-prototype-ai-stats { flex-wrap: wrap; }
}
@media (max-width: 640px) {
  .meeting-prototype-drop { align-items: flex-start; }
  .meeting-prototype-file-chip { max-width: 130px; }
  .meeting-prototype-ai-stats { display: grid; gap: 6px; }
}
.latest-reply-card { margin: 12px 0; padding: 12px; border: 1px solid #bae6fd; border-radius: 8px; background: #f0f9ff; }
.latest-reply-heading { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.reply-intent-badge { padding: 2px 7px; border-radius: 10px; background: #dbeafe; color: #1d4ed8; font-size: 11px; }
.reply-intent-pricing { background: #fef3c7; color: #92400e; }
.reply-intent-product_question { background: #e0e7ff; color: #3730a3; }
.reply-intent-not_interested { background: #f1f5f9; color: #475569; }
.reply-intent-unsubscribe { background: #fee2e2; color: #b91c1c; }
.follow-up-task-card { margin: 12px 0; padding: 12px; border: 1px solid #dbeafe; border-radius: 8px; background: #fff; }
.follow-up-task-heading { display: flex; justify-content: space-between; margin-bottom: 8px; color: var(--text-main); }
.follow-up-task-heading span { color: var(--text-muted); font-size: 11px; }
.follow-up-task-row { display: grid; grid-template-columns: 42px 1fr auto; gap: 8px; align-items: center; padding: 6px 0; border-top: 1px solid #f1f5f9; font-size: 12px; }
.follow-up-task-type { color: var(--blue-primary); font-weight: 600; }
.follow-up-task-description { color: var(--text-secondary); }
.follow-up-task-date { color: var(--text-muted); white-space: nowrap; }
.latest-reply-subject { margin-bottom: 4px; font-weight: 600; color: var(--text-main); }
.latest-reply-body { display: -webkit-box; margin-bottom: 8px; overflow: hidden; color: var(--text-muted); font-size: 12px; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
</style>
