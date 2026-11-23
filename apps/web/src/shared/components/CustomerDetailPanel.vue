<script setup lang="ts">
import type { OperationCustomer, OperationDetail, OperationEmail, OperationMeeting } from '../../services/operationApi';
import EmailComposer from './EmailComposer.vue';
import MeetingUploader from './MeetingUploader.vue';
import { countryLabel, industryLabel, regionLabel, salesTierLabel, pipelineStageLabel, jobStatusLabel } from '../utils/labels';

defineProps<{
  customer: OperationCustomer | null;
  detail: OperationDetail | null;
  emails: OperationEmail[];
  meetings: OperationMeeting[];
  loading?: boolean;
  error?: string;
}>();

const emit = defineEmits<{
  close: [];
  sent: [];
  meetingUploaded: [];
}>();

const formatDate = (value?: string | null) => {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
};
</script>

<template>
  <aside v-if="customer" class="detail-panel">
    <div class="detail-header">
      <div>
        <h3>{{ customer.customerName }}</h3>
        <p>{{ industryLabel(customer.payload?.industry) }} / {{ regionLabel(customer.payload?.region) }} / {{ countryLabel(customer.payload?.country) }}</p>
      </div>
      <button class="btn" @click="emit('close')">关闭</button>
    </div>

    <div v-if="loading" class="detail-loading">详情加载中...</div>
    <div v-if="error" class="alert-error">{{ error }}</div>

    <section class="detail-section">
      <h4>客户信息</h4>
      <div class="kv-grid">
        <span>销售等级</span><strong>{{ salesTierLabel(customer.payload?.sales_tier || detail?.company.sales_tier) }}</strong>
        <span>ICP</span><strong>{{ customer.payload?.icp_score || detail?.company.icp_score || '-' }}</strong>
        <span>阶段</span><strong>{{ customer.payload?.stage || detail?.stage || '-' }}</strong>
        <span>负责人</span><strong>{{ customer.ownerName || detail?.company.assigned_to || '-' }}</strong>
        <span>官网</span>
        <strong>
          <a v-if="customer.payload?.website || detail?.company.website" :href="customer.payload?.website || detail?.company.website || ''" target="_blank" rel="noopener">
            {{ customer.payload?.website || detail?.company.website }}
          </a>
          <span v-else>-</span>
        </strong>
      </div>
      <p v-if="customer.payload?.analysis_summary" class="detail-note">{{ customer.payload.analysis_summary }}</p>
    </section>

    <section class="detail-section">
      <h4>联系人</h4>
      <div v-if="!detail?.contacts?.length" class="empty-inline">暂无联系人</div>
      <div v-for="contact in detail?.contacts || []" :key="contact.contact_id" class="list-row">
        <strong>{{ contact.name }}</strong>
        <span>{{ contact.title || contact.role || '-' }}</span>
        <span>{{ contact.email }}</span>
      </div>
    </section>

    <section class="detail-section">
      <h4>邮件触达</h4>
      <EmailComposer :customer="customer" :contacts="detail?.contacts || []" @sent="emit('sent')" />
    </section>

    <section class="detail-section">
      <h4>邮件历史</h4>
      <div v-if="emails.length === 0" class="empty-inline">暂无邮件记录</div>
      <div v-for="email in emails" :key="email.email_id || email.id || email.subject" class="list-row">
        <strong>{{ email.subject || '-' }}</strong>
        <span>{{ email.recipientName || email.recipientEmail || '-' }}</span>
        <span>{{ formatDate(email.sent_at || email.sentAt) }}</span>
      </div>
    </section>

    <section class="detail-section">
      <h4>会议上传</h4>
      <MeetingUploader :customer="customer" @uploaded="emit('meetingUploaded')" />
    </section>

    <section class="detail-section">
      <h4>会议历史</h4>
      <div v-if="meetings.length === 0" class="empty-inline">暂无会议记录</div>
      <div v-for="meeting in meetings" :key="meeting.meeting_id || meeting.createdAt" class="list-row">
        <strong>{{ meeting.title || '会议记录' }}</strong>
        <span>{{ meeting.transcript_status === 'completed' ? '已转写' : (meeting.transcript_status || '-') }}</span>
        <span>{{ formatDate(meeting.createdAt) }}</span>
      </div>
    </section>

    <section class="detail-section">
      <h4>待办</h4>
      <div v-if="!detail?.tasks?.length" class="empty-inline">暂无待办</div>
      <div v-for="task in detail?.tasks || []" :key="task.task_id" class="list-row">
        <strong>{{ task.description }}</strong>
        <span>{{ task.status === 'completed' ? '已完成' : task.status === 'open' ? '待处理' : (task.status || '-') }}</span>
        <span>{{ formatDate(task.due_date) }}</span>
      </div>
    </section>
  </aside>
</template>
