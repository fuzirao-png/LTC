<script setup lang="ts">
import { onUnmounted, ref } from 'vue';

import { getApiErrorMessage } from '../../services/http';
import { meetingApi, type MeetingJob } from '../../services/meetingApi';
import type { OperationCustomer } from '../../services/operationApi';

const props = defineProps<{
  customer: OperationCustomer | null;
}>();

const emit = defineEmits<{
  uploaded: [];
}>();

const fileInput = ref<HTMLInputElement | null>(null);
const selectedFile = ref<File | null>(null);
const activeJob = ref<MeetingJob | null>(null);
const uploading = ref(false);
const message = ref('');
const error = ref('');
let pollTimer: number | undefined;

const customerCompanyId = () => String(props.customer?.company_id || props.customer?.companyId || '').trim();

const chooseFile = (event: Event) => {
  const input = event.target as HTMLInputElement;
  selectedFile.value = input.files?.[0] || null;
  message.value = '';
  error.value = '';
};

const stopPolling = () => {
  if (pollTimer) {
    window.clearTimeout(pollTimer);
    pollTimer = undefined;
  }
};

const pollJob = (jobId: string) => {
  stopPolling();
  pollTimer = window.setTimeout(async () => {
    try {
      const job = await meetingApi.getJob(jobId);
      activeJob.value = job;
      message.value = job.message || '';
      if (job.status === 'completed') {
        emit('uploaded');
        stopPolling();
        return;
      }
      if (job.status === 'error') {
        error.value = job.errorMessage || job.message || '会议处理失败';
        stopPolling();
        return;
      }
      pollJob(jobId);
    } catch (err) {
      error.value = getApiErrorMessage(err, '会议任务状态读取失败');
      pollJob(jobId);
    }
  }, 1800);
};

const upload = async () => {
  const companyId = customerCompanyId();
  if (!companyId) {
    error.value = '请先选择客户';
    return;
  }
  if (!selectedFile.value) {
    error.value = '请先选择会议录音或视频文件';
    return;
  }
  uploading.value = true;
  error.value = '';
  message.value = '';
  activeJob.value = null;
  try {
    const result = await meetingApi.uploadMeeting({
      companyId,
      file: selectedFile.value,
    });
    activeJob.value = result.job || null;
    message.value = result.message || result.job?.message || '会议文件已上传';
    if (result.job?.id) pollJob(result.job.id);
    else emit('uploaded');
  } catch (err) {
    error.value = getApiErrorMessage(err, '会议文件上传失败');
  } finally {
    uploading.value = false;
  }
};

onUnmounted(stopPolling);
</script>

<template>
  <div class="meeting-uploader">
    <div class="file-picker compact" @click="fileInput?.click()">
      <input ref="fileInput" type="file" accept="audio/*,video/*" @change="chooseFile" />
      <strong>{{ selectedFile?.name || '选择会议文件' }}</strong>
      <span>{{ selectedFile ? `${Math.round(selectedFile.size / 1024)} KB` : '上传后自动生成摘要和待办' }}</span>
    </div>

    <button class="btn btn-primary" :disabled="uploading || !customer" @click="upload">
      {{ uploading ? '上传中...' : '上传会议' }}
    </button>

    <div v-if="activeJob" class="job-card compact">
      <div class="job-head">
        <strong>{{ activeJob.status }}</strong>
        <span>{{ activeJob.progress }}%</span>
      </div>
      <div class="progress-bar"><span :style="{ width: `${activeJob.progress || 0}%` }"></span></div>
      <p>{{ activeJob.message || message }}</p>
    </div>

    <div v-if="message && !activeJob" class="success-inline">{{ message }}</div>
    <div v-if="error" class="alert-error">{{ error }}</div>
  </div>
</template>
