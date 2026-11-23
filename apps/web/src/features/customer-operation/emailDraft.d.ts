export interface EmailDraftCustomer {
  companyId?: string;
  company_id?: string;
  customerName?: string;
  name: string;
  tag: string;
}

export interface EmailDraftContact {
  contactId?: string;
  contact_id?: string;
  primary_email?: string;
  title?: string;
  name: string;
  email: string;
  role: string;
}

export type EmailAgentOperation = 'generate' | 'optimize' | 'translate' | 'rewrite';

export declare const EMAIL_REGENERATE_PRESETS: ReadonlyArray<{
  label: '强调GDPR合规' | '正式语气表达';
  prompt: '强调GDPR合规' | '正式语气表达';
}>;

export declare const buildEmailDraft: (
  customer: EmailDraftCustomer,
  contact: EmailDraftContact,
  salesName: string,
) => string;

export declare const buildRegenerateEmailPayload: (
  customer: EmailDraftCustomer,
  contact: EmailDraftContact,
  currentSubject: string,
  currentBody: string,
  customPrompt?: string,
  salesName?: string,
) => {
  salesName: string;
  customerName: string;
  recipientName: string;
  recipientEmail: string;
  recipientTitle: string;
  currentSubject: string;
  currentBody: string;
  customPrompt: string;
  mode: 'regenerate';
};

export declare const buildEmailAgentPayload: (input: {
  customer: EmailDraftCustomer;
  contact: EmailDraftContact;
  subject?: string;
  body?: string;
  instruction?: string;
  operation: EmailAgentOperation;
  targetLanguage?: string;
}) => {
  companyId: string;
  contactId: string;
  customerName: string;
  recipientName: string;
  recipientEmail: string;
  recipientTitle: string;
  subject: string;
  body: string;
  instruction: string;
  operation: EmailAgentOperation;
  targetLanguage: string;
};
