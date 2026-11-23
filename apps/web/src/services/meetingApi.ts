import { config } from '../config/runtime';
import { createHttpClient } from './http';
import { createIdempotencyKey } from '../shared/api/idempotency';

export const meetingHttp = createHttpClient(config.operationApiBase || config.meetingApiBase);

export interface MeetingJob {
  id: string;
  customerName: string;
  status: 'queued' | 'transcribing' | 'summarizing' | 'completed' | 'error' | string;
  progress: number;
  message?: string;
  createdAt?: string;
  startedAt?: string;
  completedAt?: string;
  errorMessage?: string;
  transcriptProvider?: string;
  recordId?: string;
}

export interface MeetingActionItem {
  task?: string | null;
  owner?: string | null;
  due_at?: string | null;
  [key: string]: unknown;
}

export interface MeetingSummary {
  core_summary?: string | null;
  customer_needs?: string[];
  pain_points?: string[];
  buying_signals?: string[];
  action_items?: MeetingActionItem[];
  decisions?: string[];
  risks?: string[];
  keywords?: string[];
  next_step?: string | null;
  [key: string]: unknown;
}

export interface MeetingSegment {
  sequence_no?: number;
  sequenceNo?: number;
  speaker_id?: string | null;
  speaker_label?: string | null;
  speaker?: string | null;
  start_seconds?: number;
  end_seconds?: number;
  start?: number;
  end?: number;
  transcript_text?: string;
  text?: string;
  confidence?: number | null;
}

export interface MeetingRecord {
  id?: string;
  meeting_id?: string;
  companyId?: string;
  company_id?: string;
  customerName?: string;
  company_name?: string;
  title?: string;
  source?: string;
  fileName?: string;
  durationSeconds?: number;
  duration_seconds?: number;
  createdAt?: string;
  created_at?: string;
  meeting_time?: string;
  transcript_status?: string;
  processing_status?: string;
  transcript?: string;
  fullTranscript?: string;
  summary?: string | MeetingSummary | null;
  nextStep?: string | null;
  decisions?: string[];
  risks?: string[];
  keywords?: string[];
  actionItems?: Array<MeetingActionItem | string>;
  segments?: MeetingSegment[];
  audioUrl?: string;
}

export interface MeetingUploadResult {
  success: boolean;
  message?: string;
  job?: MeetingJob;
  meeting_id?: string;
}

function toJob(value: any): MeetingJob | null {
  const data = value?.data || value;
  const id = data?.meeting_id || data?.id;
  if (!id) return null;
  const rawStatus = String(data?.status || data?.processing_status || 'uploaded');
  const status = ['failed', 'cancelled'].includes(rawStatus) ? 'error' : rawStatus;
  return {
    id: String(id),
    customerName: data?.company_name || data?.customerName || '',
    status,
    progress: status === 'completed' ? 100 : 0,
    message: data?.error_message || data?.message,
  };
}

function toRecord(value: any): MeetingRecord {
  const data = value?.data || value;
  const meetingId = data.meeting_id || data.id;
  const summary = data.summary && typeof data.summary === 'object' ? data.summary : data.summary || null;
  const toStringList = (items: unknown) => Array.isArray(items) ? items.map((item) => String(item)) : [];
  return {
    id: meetingId,
    meeting_id: data.meeting_id,
    companyId: data.company_id,
    company_id: data.company_id,
    customerName: data.company_name || data.customerName,
    company_name: data.company_name,
    title: data.title,
    fileName: data.title,
    source: data.source,
    durationSeconds: data.duration_seconds,
    duration_seconds: data.duration_seconds,
    createdAt: data.created_at,
    created_at: data.created_at,
    meeting_time: data.meeting_started_at,
    transcript_status: data.transcript_status,
    processing_status: data.processing_status,
    transcript: data.transcript_text,
    fullTranscript: data.transcript_text,
    summary,
    nextStep: data.next_step || summary?.next_step || null,
    decisions: toStringList(data.decisions?.length ? data.decisions : summary?.decisions),
    risks: toStringList(data.risks?.length ? data.risks : summary?.risks),
    keywords: toStringList(data.keywords?.length ? data.keywords : summary?.keywords),
    actionItems: Array.isArray(summary?.action_items) ? summary.action_items : [],
    segments: Array.isArray(data.segments)
      ? data.segments.map((segment: any) => ({
          sequence_no: segment.sequence_no,
          sequenceNo: segment.sequence_no,
          speaker_id: segment.speaker_id,
          speaker_label: segment.speaker_label,
          speaker: segment.speaker_label || segment.speaker_id || segment.speaker || '',
          start_seconds: segment.start_seconds ?? segment.start ?? 0,
          end_seconds: segment.end_seconds ?? segment.end ?? 0,
          start: segment.start_seconds ?? segment.start ?? 0,
          end: segment.end_seconds ?? segment.end ?? 0,
          transcript_text: segment.transcript_text || segment.text || '',
          text: segment.transcript_text || segment.text || '',
          confidence: segment.confidence,
        }))
      : [],
    audioUrl: meetingId ? `/api/v1/meetings/${encodeURIComponent(meetingId)}/audio` : undefined,
  };
}

export const meetingApi = {
  async getHistory(companyId?: string) {
    const { data } = await meetingHttp.get<{ data?: any[] }>('/meetings', {
      params: companyId ? { company_id: companyId } : {},
    });
    const rows = ((data as any).data || []).map(toRecord);
    // The list endpoint is intentionally lightweight; load details for the
    // transcript, summary, and action items shown in the history cards.
    return Promise.all(
      rows.map(async (row: MeetingRecord) => {
        if (!row.id) return row;
        try {
          const { data: detail } = await meetingHttp.get<any>(`/meetings/${encodeURIComponent(row.id)}`);
          const detailRecord = toRecord(detail);
          return {
            ...row,
            ...detailRecord,
            customerName: detailRecord.customerName || row.customerName,
            company_name: detailRecord.company_name || row.company_name,
          };
        } catch {
          return row;
        }
      }),
    );
  },
  async uploadMeeting(payload: { companyId: string; title?: string; file: File; durationSeconds?: number }) {
    const formData = new FormData();
    formData.append('company_id', payload.companyId);
    if (payload.title) formData.append('title', payload.title);
    formData.append('file', payload.file, payload.file.name || `meeting-${Date.now()}.webm`);

    const { data } = await meetingHttp.post<any>('/meetings/upload', formData, {
      headers: {
        // Override the JSON default before Axios transforms the FormData.
        // Axios then lets the browser append the multipart boundary.
        'Content-Type': 'multipart/form-data',
        'Idempotency-Key': createIdempotencyKey(),
      },
      timeout: 600000,
    });
    const job = toJob(data);
    return {
      success: true,
      message: data?.message || (job ? '会议文件已上传，正在处理' : undefined),
      job: job || undefined,
      meeting_id: data?.data?.meeting_id,
    };
  },
  async getJob(jobId: string) {
    const { data } = await meetingHttp.get<any>(`/meetings/${encodeURIComponent(jobId)}`);
    const detail = data?.data || {};
    const job = toJob(detail);
    if (!job) throw new Error('会议任务响应缺少 meeting_id');
    job.progress = job.status === 'completed' ? 100 : job.status === 'failed' || job.status === 'error' ? 100 : 0;
    return job;
  },
  async findRecentJob(companyId: string, title: string, startedAt: number) {
    const records = await this.getHistory(companyId);
    const threshold = startedAt - 60_000;
    const record = records.find((item) => {
      const createdAt = new Date(item.createdAt || item.created_at || 0).getTime();
      return createdAt >= threshold && (!title || item.title === title || item.fileName === title);
    });
    return record ? toJob(record) : null;
  },
  async deleteRecord(recordId: string) {
    await meetingHttp.delete(`/meetings/${encodeURIComponent(recordId)}`);
  },
};
