import { config } from '../config/runtime';
import { api } from '../shared/api/client';
import { createHttpClient } from './http';

export const operationHttp = createHttpClient(config.operationApiBase);

export interface OperationCustomer {
  company_id?: string;
  companyId?: string;
  display_name?: string;
  customerName: string;
  ownerId?: string;
  ownerName?: string;
  tag?: string;
  contact?: string;
  stage?: string;
  progress?: number;
  stageDates?: {
    acquiredAt?: string | null;
    emailedAt?: string | null;
    repliedAt?: string | null;
    meetingAt?: string | null;
    proposalAt?: string | null;
    wonAt?: string | null;
  };
  latestTitle?: string;
  latestTime?: string | null;
  latestBody?: string;
  latestInboundReply?: {
    subject?: string;
    body?: string;
    intent?: string;
    receivedAt?: string | null;
  } | null;
  tasks?: OperationTask[];
  signal?: string;
  outboundEmailCount?: number;
  inboundEmailCount?: number;
  showEmailRecord?: boolean;
  contactEmailCount?: number;
  icpScore?: number | null;
  icpGrade?: string | null;
  payload?: {
    industry?: string;
    website?: string;
    city?: string;
    country?: string;
    region?: string;
    sales_tier?: string;
    icp_score?: number;
    icp_grade?: string;
    contact_count?: number;
    contact_email_count?: number;
    stage?: string;
    analysis_summary?: string;
    [key: string]: unknown;
  };
}

export interface OperationTask {
  task_id: string;
  task_type: 'email' | 'meeting' | 'proposal';
  description: string;
  due_date?: string | null;
  status: 'pending' | 'in_progress' | 'done' | 'cancelled' | 'overdue' | 'completed' | 'open';
}

export interface OperationCompany {
  company_id: string;
  company_name: string;
  industry?: string | null;
  website?: string | null;
  city?: string | null;
  country?: string | null;
  region?: string | null;
  sales_tier?: string | null;
  icp_score?: number | null;
  icp_grade?: string | null;
  assigned_to?: string | null;
  stage?: string;
}

export interface OperationContact {
  contact_id: string;
  company_id: string;
  name: string;
  title?: string | null;
  email: string;
  role?: string | null;
}

export interface ContactRosterItem {
  contact_id: string;
  company_id: string;
  full_name: string;
  title?: string | null;
  department?: string | null;
  primary_email?: string | null;
  source_primary_email?: string | null;
  email_status: 'unknown' | 'valid' | 'invalid' | 'risky' | 'opted_out' | 'bounced';
  linkedin_url?: string | null;
  source?: string | null;
  employment_status?: 'unknown' | 'active' | 'departed';
  legal_basis_status?: 'unknown' | 'allowed' | 'blocked';
  roster_status?: 'active' | 'backup';
  position?: number | null;
  role_group?: string | null;
  priority_score?: number | null;
  score_breakdown?: Record<string, number>;
  recommendation_reason?: string | null;
  is_pinned?: boolean;
  engagement_locked?: boolean;
  outreach_status?: string;
  last_engagement_at?: string | null;
  blocked_reason?: string | null;
  roster_version?: number | null;
  version?: number | null;
}

export interface ContactRoster {
  company_id: string;
  initialized: boolean;
  active: ContactRosterItem[];
  backup: ContactRosterItem[];
  total: number;
  limit: number;
  ranking_version: string;
}

export interface ManualContactPayload {
  full_name: string;
  title?: string;
  department?: string;
  primary_email?: string;
  linkedin_url?: string;
  legal_basis_status?: 'unknown' | 'allowed' | 'blocked';
}

export interface ContactUpdatePayload {
  full_name?: string;
  title?: string;
  department?: string;
  relationship_role?: 'decision_maker' | 'influencer' | 'executor' | 'general_employee';
  priority?: 'P1' | 'P2' | 'P3';
  primary_email?: string;
  normalized_email?: string;
  email_status?: 'unknown' | 'valid' | 'invalid' | 'risky' | 'opted_out' | 'bounced';
  phone?: string;
  linkedin_url?: string;
}

export interface OperationEmailAttachment {
  attachment_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  download_url: string;
}

export interface OperationEmailDraft {
  email_id: string;
  company_id: string;
  contact_id: string;
  parent_email_id?: string;
  purpose: 'first_touch' | 'reply_followup' | 'meeting_followup';
  status: 'draft';
  recipient_email: string;
  contact_name?: string;
  subject: string;
  body_text: string;
  version: number;
  created_at?: string | null;
  updated_at?: string | null;
  attachments: OperationEmailAttachment[];
}

export interface EmailDraftSavePayload {
  contactId: string;
  subject: string;
  body: string;
  purpose: 'first_touch' | 'reply_followup' | 'meeting_followup';
  parentEmailId?: string;
  attachments?: File[];
}

export interface OperationEmail {
  email_id?: string;
  id?: string;
  company_id?: string;
  contact_id?: string;
  direction?: string;
  recipientName?: string;
  recipientEmail?: string;
  deliveredTo?: string;
  provider?: string;
  subject?: string;
  body?: string;
  bodyPreview?: string;
  status?: string;
  smtpStatus?: 'submitted' | 'rejected' | string;
  deliveryStatus?: 'unconfirmed' | 'confirmed' | 'bounced' | string;
  deliveryConfirmed?: boolean;
  sent_at?: string | null;
  sentAt?: string | null;
  receivedAt?: string | null;
  repliedAt?: string | null;
  createdAt?: string | null;
  replied_at?: string | null;
  messageId?: string;
  from_address?: string;
  to_address?: string;
  message_id?: string;
  contact_name?: string;
  contact_email?: string;
  attachments?: OperationEmailAttachment[];
}

export interface PaNotification {
  id: string;
  role?: string;
  type?: string;
  eventType?: string;
  messageId?: string;
  companyId?: string;
  emailId?: string;
  priority?: string;
  title?: string;
  body?: string;
  customerName?: string;
  subject?: string;
  from?: string;
  to?: string;
  notificationTarget?: {
    companyId?: string;
    emailId?: string;
    messageId?: string;
  };
  read?: boolean;
  createdAt?: string;
  updatedAt?: string;
}

export interface InboundMailDetail {
  notificationId: string;
  messageId?: string;
  from?: string;
  to?: string;
  subject?: string;
  bodyPreview?: string;
  bodyText?: string;
  receivedAt?: string;
  raw?: Record<string, unknown>;
}

export interface OperationMeeting {
  meeting_id?: string;
  id?: string;
  company_id?: string;
  title?: string;
  customerName?: string;
  meeting_time?: string;
  createdAt?: string;
  transcript_status?: string;
  transcript?: string | null;
  summary?: unknown;
}

export interface OperationTask {
  task_id: string;
  description: string;
  status: 'pending' | 'in_progress' | 'done' | 'cancelled' | 'overdue' | 'completed' | 'open';
  due_date?: string | null;
}

export interface OperationDetail {
  company: OperationCompany;
  contacts: OperationContact[];
  emails: OperationEmail[];
  meetings: OperationMeeting[];
  tasks: OperationTask[];
  stage: string;
}

export interface EmailGeneratePayload {
  companyId?: string;
  contactId?: string;
  customerName: string;
  recipientName: string;
  recipientEmail: string;
  recipientTitle?: string | null;
  currentSubject?: string;
  currentBody?: string;
  customPrompt?: string;
  mode?: 'initial' | 'regenerate';
}

export interface EmailGenerateResult {
  success: boolean;
  subject: string;
  body: string;
  model?: string;
  message?: string;
}

export interface EmailTranslatePayload {
  customerName: string;
  recipientName: string;
  sourceSubject: string;
  sourceText: string;
  targetLanguage: string;
}

export interface EmailTranslateResult {
  success: boolean;
  language: string;
  translatedSubject: string;
  translatedText: string;
  model?: string;
  message?: string;
}

export type EmailAgentOperation = 'generate' | 'optimize' | 'translate' | 'rewrite';

export interface EmailAgentPayload {
  companyId: string;
  contactId: string;
  customerName?: string;
  recipientName?: string;
  recipientEmail?: string;
  recipientTitle?: string;
  subject?: string;
  body?: string;
  instruction?: string;
  operation: EmailAgentOperation;
  targetLanguage?: string;
}

export interface EmailAgentResult {
  success: boolean;
  agent: 'email-agent';
  operation: EmailAgentOperation;
  subject: string;
  body: string;
  language?: string | null;
  skills: string[];
  changes: string[];
  model: string;
  message: string;
}

export interface EmailSendPayload {
  companyId?: string;
  contactId?: string;
  customerName: string;
  recipientName: string;
  recipientEmail: string;
  to?: string;
  subject: string;
  body: string;
  chineseDraft?: string;
  locale?: string;
  purpose?: 'first_touch' | 'reply_followup' | 'meeting_followup';
  draftId?: string;
  attachments?: File[];
}

export interface EmailSendResult {
  success: boolean;
  message?: string;
  record?: OperationEmail;
  traceId?: string;
}

export interface ManualNoteField {
  dimension: string;
  target?: string;
  target_table?: string;
  target_version?: number;
  extracted: string;
  previous?: string | null;
  confidence?: number;
  action?: string;
  selected?: boolean;
}

export interface ManualNoteExtraction {
  success: boolean;
  fields: ManualNoteField[];
  unidentified: string;
}

export interface ManualNoteRecord {
  noteId: string;
  companyId: string;
  salesId: string;
  rawText: string;
  confirmStatus: 'pending' | 'confirmed' | 'discarded';
  extractedFields?: ManualNoteField[];
}

export interface ManualNoteAnalysisResult {
  status: 'queued' | 'running' | 'completed' | 'failed';
  runId: string | null;
  message: string;
}

export interface ManualNoteFieldIssue {
  dimension?: string;
  target?: string;
  target_version?: number;
  current_version?: number | null;
  reason: string;
}

export interface ManualNoteConfirmationResult {
  note: ManualNoteRecord;
  analysis: ManualNoteAnalysisResult;
  updated_dimensions: string[];
  conflicts: ManualNoteFieldIssue[];
  skipped_fields: ManualNoteFieldIssue[];
}

function emailDraftForm(payload: EmailDraftSavePayload) {
  const form = new FormData();
  form.append('contactId', payload.contactId);
  form.append('subject', payload.subject);
  form.append('body', payload.body);
  form.append('purpose', payload.purpose);
  if (payload.parentEmailId) form.append('parentEmailId', payload.parentEmailId);
  for (const attachment of payload.attachments || []) {
    form.append('attachments', attachment, attachment.name);
  }
  return form;
}

export const operationApi = {
  async exportCustomers() {
    const { data } = await operationHttp.get<{ success: boolean; items: OperationCustomer[] }>('/internal/customers/export');
    return data;
  },
  async homeCards() {
    const { data } = await operationHttp.get<{ success: boolean; items: OperationCustomer[] }>('/internal/customers/home-cards');
    return data;
  },
  async getCustomerOperations(companyId: string) {
    const { data } = await operationHttp.get<{ data: OperationDetail }>(
      `/customers/${encodeURIComponent(companyId)}/operations`,
    );
    return data.data;
  },
  async getContactRoster(companyId: string) {
    const { data } = await operationHttp.get<{ data: ContactRoster }>(
      `/companies/${encodeURIComponent(companyId)}/contact-roster`,
    );
    return data.data;
  },
  async recalculateContactRoster(companyId: string) {
    const { data } = await operationHttp.post<{ data: ContactRoster }>(
      `/companies/${encodeURIComponent(companyId)}/contact-roster/recalculate`,
    );
    return data.data;
  },
  async mutateContactRoster(
    companyId: string,
    contactId: string,
    payload: {
      action: 'activate' | 'backup' | 'pin' | 'unpin' | 'move';
      position?: number;
      replace_contact_id?: string;
      reason?: string;
    },
  ) {
    const { data } = await operationHttp.patch<{ data: ContactRoster }>(
      `/companies/${encodeURIComponent(companyId)}/contact-roster/${encodeURIComponent(contactId)}`,
      payload,
    );
    return data.data;
  },
  async updateContact(companyId: string, contactId: string, version: number, payload: ContactUpdatePayload) {
    const { data } = await operationHttp.patch<{ data: OperationContact }>(
      `/contacts/${encodeURIComponent(contactId)}`,
      payload,
      { headers: { 'If-Match': String(version) } },
    );
    return data.data;
  },
  async createManualContact(companyId: string, payload: ManualContactPayload) {
    const { data } = await operationHttp.post<{ data: ContactRosterItem }>(
      `/companies/${encodeURIComponent(companyId)}/contacts`,
      payload,
    );
    return data.data;
  },
  async getEmailDrafts(companyId: string) {
    const { data } = await operationHttp.get<{ success: boolean; items: OperationEmailDraft[] }>(
      `/customers/${encodeURIComponent(companyId)}/email-drafts`,
    );
    return data.items || [];
  },
  async createEmailDraft(companyId: string, payload: EmailDraftSavePayload) {
    const { data } = await operationHttp.post<{ success: boolean; item: OperationEmailDraft }>(
      `/customers/${encodeURIComponent(companyId)}/email-drafts`,
      emailDraftForm(payload),
    );
    return data.item;
  },
  async updateEmailDraft(emailId: string, version: number, payload: EmailDraftSavePayload) {
    const { data } = await operationHttp.patch<{ success: boolean; item: OperationEmailDraft }>(
      `/email-drafts/${encodeURIComponent(emailId)}`,
      emailDraftForm(payload),
      { headers: { 'If-Match': String(version) } },
    );
    return data.item;
  },
  async deleteEmailDraft(emailId: string, version: number) {
    await operationHttp.delete(`/email-drafts/${encodeURIComponent(emailId)}`, {
      headers: { 'If-Match': String(version) },
    });
  },
  async deleteEmailDraftAttachment(emailId: string, attachmentId: string, version: number) {
    const { data } = await operationHttp.delete<{ success: boolean; item: OperationEmailDraft }>(
      `/email-drafts/${encodeURIComponent(emailId)}/attachments/${encodeURIComponent(attachmentId)}`,
      { headers: { 'If-Match': String(version) } },
    );
    return data.item;
  },
  async getEmailHistory(companyId: string) {
    const { data } = await operationHttp.get<{ success: boolean; items: OperationEmail[] }>(
      `/customers/${encodeURIComponent(companyId)}/email-history`,
    );
    return data.items || [];
  },
  async getMeetingHistory(customerName: string) {
    // v3.6: use /meetings with company filter
    const { data } = await operationHttp.get<{ success: boolean; items: OperationMeeting[] }>('/meetings', {
      params: { customerName },
    });
    return data.items || [];
  },
  async extractManualNote(companyId: string, rawText: string) {
    const { data } = await operationHttp.post<ManualNoteExtraction>(
      `/customers/${encodeURIComponent(companyId)}/manual-notes/extract`,
      { rawText },
    );
    return data;
  },
  async confirmManualNote(companyId: string, rawText: string, extractedFields: ManualNoteField[]) {
    const { data } = await operationHttp.post<{ success: boolean } & ManualNoteConfirmationResult>(
      `/customers/${encodeURIComponent(companyId)}/manual-notes`,
      { rawText, extractedFields, confirmStatus: 'confirmed' },
    );
    return {
      note: data.note,
      analysis: data.analysis,
      updated_dimensions: data.updated_dimensions || [],
      conflicts: data.conflicts || [],
      skipped_fields: data.skipped_fields || [],
    };
  },
  async listInboundMailNotifications() {
    const { data } = await api.get<{ success: boolean; items: PaNotification[] }>('/inbound-mail/notifications');
    return data.items || [];
  },
  async markInboundMailNotificationRead(notificationId: string) {
    const { data } = await api.patch<{ success: boolean; item: PaNotification }>(
      `/inbound-mail/notifications/${encodeURIComponent(notificationId)}/read`,
    );
    return data.item;
  },
  async getInboundMailNotificationDetail(notificationId: string) {
    const { data } = await api.get<{ success: boolean; item: InboundMailDetail }>(
      `/inbound-mail/notifications/${encodeURIComponent(notificationId)}`,
    );
    return data.item;
  },
  async generateEmail(payload: EmailGeneratePayload) {
    const { data } = await operationHttp.post<EmailGenerateResult>('/email/generate', payload);
    return data;
  },
  async translateEmail(payload: EmailTranslatePayload) {
    const { data } = await operationHttp.post<EmailTranslateResult>('/email/translate', payload);
    return data;
  },
  async runEmailAgent(payload: EmailAgentPayload) {
    const { data } = await operationHttp.post<EmailAgentResult>('/customer-operation/email/agent', payload);
    return data;
  },
  async sendEmail(payload: EmailSendPayload) {
    let requestBody: EmailSendPayload | FormData = payload;
    if (payload.attachments?.length) {
      const form = new FormData();
      for (const [key, value] of Object.entries(payload)) {
        if (key === 'attachments' || value === undefined) continue;
        form.append(key, String(value));
      }
      for (const attachment of payload.attachments) {
        form.append('attachments', attachment, attachment.name);
      }
      requestBody = form;
    }
    const response = await operationHttp.post<EmailSendResult>('/email/send', requestBody);
    return {
      ...response.data,
      traceId: String(response.headers['x-trace-id'] || ''),
    };
  },
};
