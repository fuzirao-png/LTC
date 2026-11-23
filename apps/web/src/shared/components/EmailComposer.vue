<script setup lang="ts">
import { computed, ref, watch } from 'vue';

import { getApiErrorMessage } from '../../services/http';
import { operationApi, type OperationContact, type OperationCustomer } from '../../services/operationApi';

const props = defineProps<{
  customer: OperationCustomer | null;
  contacts: OperationContact[];
}>();

const emit = defineEmits<{
  sent: [];
}>();

const languageOptions = [
  { value: 'ja', label: '日语' },
  { value: 'en', label: '英语' },
  { value: 'fr', label: '法语' },
  { value: 'de', label: '德语' },
  { value: 'es', label: '西班牙语' },
  { value: 'zh', label: '中文' },
];

const selectedContactId = ref('');
const subject = ref('');
const body = ref('');
const prompt = ref('');
const targetLanguage = ref('en');
const translatedSubject = ref('');
const translatedText = ref('');
const busy = ref('');
const message = ref('');
const error = ref('');

const selectedContact = computed(() => props.contacts.find((contact) => contact.contact_id === selectedContactId.value) || props.contacts[0] || null);

watch(
  () => props.contacts,
  (contacts) => {
    if (!contacts.length) {
      selectedContactId.value = '';
      return;
    }
    if (!contacts.some((contact) => contact.contact_id === selectedContactId.value)) {
      selectedContactId.value = contacts[0].contact_id;
    }
  },
  { immediate: true },
);

const clearStatus = () => {
  message.value = '';
  error.value = '';
};

const generateDraft = async () => {
  if (!props.customer || !selectedContact.value) return;
  clearStatus();
  busy.value = 'generate';
  try {
    const result = await operationApi.generateEmail({
      companyId: props.customer.company_id || props.customer.companyId,
      contactId: selectedContact.value.contact_id,
      customerName: props.customer.customerName,
      recipientName: selectedContact.value.name,
      recipientEmail: selectedContact.value.email,
      recipientTitle: selectedContact.value.title || selectedContact.value.role || '',
      currentSubject: subject.value,
      currentBody: body.value,
      customPrompt: prompt.value,
      mode: subject.value && body.value ? 'regenerate' : 'initial',
    });
    subject.value = result.subject || subject.value;
    body.value = result.body || body.value;
    translatedSubject.value = '';
    translatedText.value = '';
    message.value = `草稿已生成${result.model ? ` · ${result.model}` : ''}`;
  } catch (err) {
    error.value = getApiErrorMessage(err, '邮件草稿生成失败');
  } finally {
    busy.value = '';
  }
};

const translateDraft = async () => {
  if (!props.customer || !selectedContact.value || !body.value.trim()) return;
  clearStatus();
  busy.value = 'translate';
  try {
    const result = await operationApi.translateEmail({
      customerName: props.customer.customerName,
      recipientName: selectedContact.value.name,
      sourceSubject: subject.value,
      sourceText: body.value,
      targetLanguage: targetLanguage.value,
    });
    translatedSubject.value = result.translatedSubject;
    translatedText.value = result.translatedText;
    message.value = `已翻译为 ${languageOptions.find((item) => item.value === result.language)?.label || result.language}${result.model ? ` · ${result.model}` : ''}`;
  } catch (err) {
    error.value = getApiErrorMessage(err, '邮件翻译失败');
  } finally {
    busy.value = '';
  }
};

const useTranslation = () => {
  if (!translatedText.value) return;
  subject.value = translatedSubject.value;
  body.value = translatedText.value;
  translatedSubject.value = '';
  translatedText.value = '';
  message.value = '已替换为译文';
};

const sendEmail = async () => {
  if (!props.customer || !selectedContact.value) return;
  clearStatus();
  if (!subject.value.trim() || !body.value.trim()) {
    error.value = '请先确认主题和正文';
    return;
  }
  busy.value = 'send';
  try {
    const result = await operationApi.sendEmail({
      companyId: props.customer.company_id || props.customer.companyId,
      contactId: selectedContact.value.contact_id,
      customerName: props.customer.customerName,
      recipientName: selectedContact.value.name,
      recipientEmail: selectedContact.value.email,
      to: selectedContact.value.email,
      subject: subject.value,
      body: body.value,
      chineseDraft: body.value,
      locale: targetLanguage.value,
      attachments: [],
    });
    message.value = result.message || '邮件发送成功';
    emit('sent');
  } catch (err) {
    error.value = getApiErrorMessage(err, '邮件发送失败');
  } finally {
    busy.value = '';
  }
};
</script>

<template>
  <div class="email-composer">
    <div class="composer-row">
      <label>
        <span>联系人</span>
        <select v-model="selectedContactId" :disabled="contacts.length === 0">
          <option v-for="contact in contacts" :key="contact.contact_id" :value="contact.contact_id">
            {{ contact.name }} · {{ contact.title || contact.role || contact.email }}
          </option>
        </select>
      </label>
      <button class="btn" :disabled="!selectedContact || busy === 'generate'" @click="generateDraft">
        {{ busy === 'generate' ? '生成中...' : '生成草稿' }}
      </button>
    </div>

    <label>
      <span>优化指令</span>
      <input v-model="prompt" placeholder="例如：突出多国覆盖、语气更正式、强调 ROI" />
    </label>

    <label>
      <span>主题</span>
      <input v-model="subject" placeholder="邮件主题" />
    </label>

    <label>
      <span>正文</span>
      <textarea v-model="body" rows="8" placeholder="先生成草稿，也可以手动编辑正文" />
    </label>

    <div class="composer-row">
      <label class="composer-language">
        <span>翻译</span>
        <select v-model="targetLanguage">
          <option v-for="item in languageOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
        </select>
      </label>
      <button class="btn" :disabled="!body.trim() || busy === 'translate'" @click="translateDraft">
        {{ busy === 'translate' ? '翻译中...' : '翻译正文' }}
      </button>
      <button class="btn btn-primary" :disabled="!selectedContact || busy === 'send'" @click="sendEmail">
        {{ busy === 'send' ? '发送中...' : '发送邮件' }}
      </button>
    </div>

    <div v-if="translatedText" class="translation-box">
      <div class="translation-head">
        <strong>翻译结果</strong>
        <button class="btn btn-small" @click="useTranslation">替换正文</button>
      </div>
      <p v-if="translatedSubject"><strong>{{ translatedSubject }}</strong></p>
      <p>{{ translatedText }}</p>
    </div>

    <div v-if="message" class="success-inline">{{ message }}</div>
    <div v-if="error" class="alert-error">{{ error }}</div>
    <div v-if="contacts.length === 0" class="empty-inline">暂无联系人，暂不能发送邮件</div>
  </div>
</template>
