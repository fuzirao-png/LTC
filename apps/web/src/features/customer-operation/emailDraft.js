export const EMAIL_REGENERATE_PRESETS = Object.freeze([
  { label: '强调GDPR合规', prompt: '强调GDPR合规' },
  { label: '正式语气表达', prompt: '正式语气表达' },
]);

export const buildEmailDraft = (customer, contact, salesName) => `${contact.name.split(' ')[0]}，您好：

感谢您对企业 eSIM 方案的关注。结合贵司当前${customer.tag}业务和跨境沟通需求，我们建议先从覆盖清单、企业价格、合规保障和 SLA 条款四个方面对齐。

我们可以提供统一后台、多国套餐、用量阶梯价和月度账单导出，帮助贵司降低跨国通信管理成本。

是否方便本周安排 30 分钟会议，我们可以进一步确认试点国家和报价口径？

${salesName}`;

export const buildRegenerateEmailPayload = (
  customer,
  contact,
  currentSubject,
  currentBody,
  customPrompt = '',
  salesName = '',
) => ({
  companyId: customer.companyId || customer.company_id || '',
  contactId: contact.contactId || contact.contact_id || '',
  salesName,
  customerName: customer.name,
  recipientName: contact.name,
  recipientEmail: contact.email,
  recipientTitle: contact.role,
  currentSubject,
  currentBody,
  customPrompt: customPrompt.trim(),
  mode: 'regenerate',
});

export const buildEmailAgentPayload = ({
  customer,
  contact,
  subject = '',
  body = '',
  instruction = '',
  operation,
  targetLanguage = '',
}) => ({
  companyId: customer.companyId || customer.company_id || '',
  contactId: contact.contactId || contact.contact_id || '',
  customerName: customer.name || customer.customerName || '',
  recipientName: contact.name || '',
  recipientEmail: contact.email || contact.primary_email || '',
  recipientTitle: contact.role || contact.title || '',
  subject,
  body,
  instruction: instruction.trim(),
  operation,
  targetLanguage,
});
