import { defineStore } from 'pinia';

import { getApiErrorMessage, isTransientApiError } from '../services/http';
import { meetingApi, type MeetingJob, type MeetingRecord } from '../services/meetingApi';

const ACTIVE_MEETING_JOB_PREFIX = 'ltc.active-meeting-job.v1.';

function persistActiveJob(companyId: string, job: MeetingJob | null) {
  if (typeof window === 'undefined' || !companyId) return;
  const key = `${ACTIVE_MEETING_JOB_PREFIX}${companyId}`;
  if (job) window.localStorage.setItem(key, JSON.stringify(job));
  else window.localStorage.removeItem(key);
}

function readActiveJob(companyId: string): MeetingJob | null {
  if (typeof window === 'undefined' || !companyId) return null;
  try {
    const parsed = JSON.parse(window.localStorage.getItem(`${ACTIVE_MEETING_JOB_PREFIX}${companyId}`) || 'null');
    return parsed?.id ? parsed as MeetingJob : null;
  } catch {
    window.localStorage.removeItem(`${ACTIVE_MEETING_JOB_PREFIX}${companyId}`);
    return null;
  }
}

const wait = (ms: number) => new Promise<void>((resolve) => window.setTimeout(resolve, ms));

export const useMeetingStore = defineStore('meeting', {
  state: () => ({
    selectedCustomerName: '',
    selectedCompanyId: '',
    records: [] as MeetingRecord[],
    activeJob: null as MeetingJob | null,
    loading: false,
    uploading: false,
    error: '',
    message: '',
  }),
  actions: {
    async loadHistory(companyId?: string, customerName?: string) {
      const resolvedCompanyId = companyId ?? this.selectedCompanyId;
      if (companyId) this.selectedCompanyId = companyId;
      if (customerName) this.selectedCustomerName = customerName;
      this.loading = true;
      this.error = '';
      try {
        this.records = await meetingApi.getHistory(resolvedCompanyId || undefined);
      } catch (error) {
        this.error = getApiErrorMessage(error, '会议历史加载失败');
      } finally {
        this.loading = false;
      }
    },
    async upload(file: File, companyId?: string, customerName?: string) {
      const resolvedCompanyId = companyId ?? this.selectedCompanyId;
      if (!resolvedCompanyId) {
        this.error = '请先选择客户';
        return null;
      }
      this.uploading = true;
      this.error = '';
      this.message = '';
      const startedAt = Date.now();
      try {
        const result = await meetingApi.uploadMeeting({ companyId: resolvedCompanyId, title: file.name, file });
        this.activeJob = result.job || null;
        if (this.activeJob) persistActiveJob(resolvedCompanyId, this.activeJob);
        this.message = result.message || result.job?.message || '会议文件已上传';
        return this.activeJob;
      } catch (error) {
        if (isTransientApiError(error)) {
          this.message = '上传连接暂时中断，后台可能已接收文件，正在恢复任务状态';
          const recovered = await this.recoverUploadedJob(resolvedCompanyId, file.name, startedAt, customerName);
          if (recovered) return recovered;
          this.message = '暂未确认上传响应；页面会保留当前状态，可稍后重新打开客户继续查看';
          return null;
        }
        this.error = getApiErrorMessage(error, '会议文件上传失败');
        return null;
      } finally {
        this.uploading = false;
      }
    },
    async pollJob(jobId: string) {
      try {
        const job = await meetingApi.getJob(jobId);
        this.activeJob = job;
        this.message = job.message || '';
        if (job.status === 'completed') {
          persistActiveJob(this.selectedCompanyId, null);
          await this.loadHistory(this.selectedCompanyId, this.selectedCustomerName);
        }
        if (job.status === 'error') {
          persistActiveJob(this.selectedCompanyId, null);
          this.error = job.errorMessage || job.message || '会议处理失败';
        } else {
          persistActiveJob(this.selectedCompanyId, job);
        }
        return job;
      } catch (error) {
        if (isTransientApiError(error)) {
          this.error = '';
          this.message = '连接暂时中断，后台分析仍在运行，正在自动重连';
          const current = this.activeJob?.id === jobId ? this.activeJob : null;
          return current || {
            id: jobId,
            customerName: this.selectedCustomerName,
            status: 'processing',
            progress: 0,
          };
        }
        this.error = getApiErrorMessage(error, '会议任务状态读取失败');
        return null;
      }
    },
    restoreActiveJob(companyId?: string) {
      const resolvedCompanyId = companyId ?? this.selectedCompanyId;
      const job = readActiveJob(resolvedCompanyId);
      if (!job || ['completed', 'error'].includes(job.status)) return null;
      this.activeJob = job;
      this.message = '已恢复后台会议分析任务，正在查询最新进度';
      return job;
    },
    async recoverUploadedJob(companyId: string, title: string, startedAt: number, customerName?: string) {
      for (let attempt = 0; attempt < 8; attempt += 1) {
        try {
          const job = await meetingApi.findRecentJob(companyId, title, startedAt);
          if (job) {
            this.activeJob = job;
            this.selectedCompanyId = companyId;
            if (customerName) this.selectedCustomerName = customerName;
            if (!['completed', 'error'].includes(job.status)) persistActiveJob(companyId, job);
            this.error = '';
            this.message = job.status === 'completed'
              ? '后台会议分析已完成'
              : '已找回后台会议分析任务，正在继续查询';
            return job;
          }
        } catch (error) {
          if (!isTransientApiError(error)) {
            this.error = getApiErrorMessage(error, '会议任务恢复失败');
            return null;
          }
        }
        await wait(Math.min(2000 + attempt * 1000, 8000));
      }
      return null;
    },
    async deleteRecord(recordId: string) {
      this.error = '';
      this.message = '';
      try {
        await meetingApi.deleteRecord(recordId);
        await this.loadHistory(this.selectedCompanyId, this.selectedCustomerName);
        this.message = '会议记录已删除';
      } catch (error) {
        this.error = getApiErrorMessage(error, '会议记录删除失败');
      }
    },
  },
});
