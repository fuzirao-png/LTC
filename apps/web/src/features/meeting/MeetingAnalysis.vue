<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';

import PageSection from '../../shared/components/PageSection.vue';
import { jobStatusLabel } from '../../shared/utils/labels';
import type { MeetingActionItem, MeetingRecord, MeetingSummary } from '../../services/meetingApi';
import { useMeetingStore } from '../../stores/meeting';
import { useOperationStore } from '../../stores/operation';
import {
  cleanTranscriptText,
  formatMeetingDate,
  formatMeetingDuration,
  formatTranscriptRange,
  resolveMeetingSpeaker,
  splitHighlightedText,
} from './meetingPresentation.js';

const PAGE_SIZE = 10;

type SectionKey = 'summary' | 'todos' | 'decisions' | 'risks' | 'transcript';

const meeting = useMeetingStore();
const operation = useOperationStore();
const router = useRouter();
const fileInput = ref<HTMLInputElement | null>(null);
const transcriptSection = ref<HTMLElement | null>(null);
const selectedFile = ref<File | null>(null);
const selectedRecordId = ref('');
const searchQuery = ref('');
const currentPage = ref(1);
const expanded = ref<Record<SectionKey, boolean>>({
  summary: true,
  todos: true,
  decisions: true,
  risks: true,
  transcript: true,
});
let pollTimer: number | undefined;

const customerOptions = computed(() =>
  operation.customers
    .map((item) => item.customerName)
    .filter((name, index, list) => Boolean(name) && list.indexOf(name) === index),
);

const selectedCompanyId = computed(() =>
  operation.customers.find((item) => item.customerName === meeting.selectedCustomerName)?.company_id
  || operation.customers.find((item) => item.customerName === meeting.selectedCustomerName)?.companyId
  || meeting.selectedCompanyId
  || '',
);

const recordKey = (record: MeetingRecord) => String(record.meeting_id || record.id || '');

const selectedRecord = computed(() =>
  meeting.records.find((record) => recordKey(record) === selectedRecordId.value)
  || meeting.records[0]
  || null,
);

const summaryData = computed<MeetingSummary | null>(() => {
  const summary = selectedRecord.value?.summary;
  return summary && typeof summary === 'object' && !Array.isArray(summary) ? summary : null;
});

const asTextList = (value: unknown) => (
  Array.isArray(value)
    ? value.map((item) => cleanTranscriptText(item)).filter(Boolean)
    : []
);

const customerNeeds = computed(() => asTextList(summaryData.value?.customer_needs));
const painPoints = computed(() => asTextList(summaryData.value?.pain_points));
const buyingSignals = computed(() => asTextList(summaryData.value?.buying_signals));

const coreSummary = computed(() => {
  const summary = selectedRecord.value?.summary;
  if (typeof summary === 'string') {
    return cleanTranscriptText(summary).split(/\n+/).filter(Boolean).slice(0, 3);
  }

  const paragraphs: string[] = [];
  const nextStep = cleanTranscriptText(summaryData.value?.next_step || selectedRecord.value?.nextStep || '');
  if (nextStep) paragraphs.push(nextStep);
  for (const need of customerNeeds.value) {
    if (paragraphs.length >= 3) break;
    paragraphs.push(need);
  }
  return paragraphs;
});

const actionItems = computed(() => {
  const source = selectedRecord.value?.actionItems?.length
    ? selectedRecord.value.actionItems
    : summaryData.value?.action_items || [];
  return source.map((value) => {
    if (typeof value === 'string') {
      return { task: cleanTranscriptText(value), owner: '待分配', dueAt: '待定' };
    }
    const item = value as MeetingActionItem;
    return {
      task: cleanTranscriptText(item.task || item.text || item.description || item.action || '未命名待办'),
      owner: cleanTranscriptText(item.owner || '') || '待分配',
      dueAt: item.due_at ? formatMeetingDate(item.due_at, false) : '待定',
    };
  });
});

const decisions = computed(() => {
  const rootItems = asTextList(selectedRecord.value?.decisions);
  return rootItems.length ? rootItems : asTextList(summaryData.value?.decisions);
});

const risks = computed(() => {
  const rootItems = asTextList(selectedRecord.value?.risks);
  return rootItems.length ? rootItems : asTextList(summaryData.value?.risks);
});

const keywords = computed(() => {
  const rootItems = asTextList(selectedRecord.value?.keywords);
  return rootItems.length ? rootItems : asTextList(summaryData.value?.keywords);
});

const transcriptSegments = computed(() => (
  (selectedRecord.value?.segments || []).map((segment, index) => {
    const text = cleanTranscriptText(segment.transcript_text || segment.text || '');
    const speaker = resolveMeetingSpeaker(segment, index);
    return {
      sequence: Number(segment.sequence_no || segment.sequenceNo || index + 1),
      start: Number(segment.start_seconds ?? segment.start ?? 0),
      end: Number(segment.end_seconds ?? segment.end ?? 0),
      text: text || '暂无可用转录文本',
      speaker,
    };
  })
));

const normalizedSearch = computed(() => cleanTranscriptText(searchQuery.value).toLocaleLowerCase());

const filteredSegments = computed(() => {
  if (!normalizedSearch.value) return transcriptSegments.value;
  return transcriptSegments.value.filter((segment) => segment.text.toLocaleLowerCase().includes(normalizedSearch.value));
});

const totalPages = computed(() => Math.max(1, Math.ceil(filteredSegments.value.length / PAGE_SIZE)));
const visibleSegments = computed(() => {
  const start = (currentPage.value - 1) * PAGE_SIZE;
  return filteredSegments.value.slice(start, start + PAGE_SIZE);
});

const customerName = computed(() => (
  selectedRecord.value?.customerName
  || selectedRecord.value?.company_name
  || meeting.selectedCustomerName
  || selectedRecord.value?.company_id
  || '-'
));

const statusPresentation = (value: unknown, kind: 'processing' | 'transcript') => {
  const status = String(value || '').toLowerCase();
  if (kind === 'processing') {
    if (status === 'completed') return { label: '已完成', tone: 'success' };
    if (status === 'failed' || status === 'error') return { label: '失败', tone: 'danger' };
    if (status === 'uploaded') return { label: '已上传', tone: 'neutral' };
    return { label: status ? '处理中' : '未知', tone: status ? 'warning' : 'neutral' };
  }
  if (status === 'done' || status === 'completed') return { label: '已转录', tone: 'success' };
  if (status === 'failed' || status === 'error') return { label: '转录失败', tone: 'danger' };
  if (status === 'pending') return { label: '待转录', tone: 'warning' };
  return { label: status ? '转录中' : '未知', tone: status ? 'warning' : 'neutral' };
};

const processingStatus = computed(() => statusPresentation(selectedRecord.value?.processing_status, 'processing'));
const transcriptStatus = computed(() => statusPresentation(selectedRecord.value?.transcript_status, 'transcript'));

const recordOptionLabel = (record: MeetingRecord) => {
  const title = cleanTranscriptText(record.title || '会议记录');
  return `${title} · ${formatMeetingDate(record.createdAt || record.created_at, false)}`;
};

const stopPolling = () => {
  if (pollTimer) {
    window.clearTimeout(pollTimer);
    pollTimer = undefined;
  }
};

const schedulePoll = (jobId: string) => {
  stopPolling();
  pollTimer = window.setTimeout(async () => {
    const job = await meeting.pollJob(jobId);
    if (job && !['completed', 'error'].includes(job.status)) schedulePoll(jobId);
  }, 1800);
};

const chooseFile = (event: Event) => {
  const input = event.target as HTMLInputElement;
  selectedFile.value = input.files?.[0] || null;
};

const upload = async () => {
  if (!selectedFile.value) {
    meeting.error = '请先选择会议录音或视频文件';
    return;
  }
  if (!selectedCompanyId.value) {
    meeting.error = '当前客户缺少公司 ID，无法上传会议文件';
    return;
  }
  meeting.selectedCompanyId = selectedCompanyId.value;
  const job = await meeting.upload(selectedFile.value, selectedCompanyId.value, meeting.selectedCustomerName);
  if (job?.id) schedulePoll(job.id);
};

const closeMeetingAnalysis = () => router.back();

const toggleSection = (section: SectionKey) => {
  expanded.value[section] = !expanded.value[section];
};

const applySearch = async (keyword: string) => {
  searchQuery.value = keyword;
  currentPage.value = 1;
  expanded.value.transcript = true;
  await nextTick();
  transcriptSection.value?.scrollIntoView({ behavior: 'smooth', block: 'start' });
};

watch(
  () => meeting.selectedCustomerName,
  async (name) => {
    const customer = operation.customers.find((item) => item.customerName === name);
    const companyId = customer?.company_id || customer?.companyId || meeting.selectedCompanyId || '';
    meeting.selectedCompanyId = companyId;
    selectedRecordId.value = '';
    if (name && companyId) await meeting.loadHistory(companyId, name);
  },
);

watch(
  () => meeting.records.map(recordKey).join('|'),
  () => {
    if (!meeting.records.some((record) => recordKey(record) === selectedRecordId.value)) {
      selectedRecordId.value = recordKey(meeting.records[0] || {});
    }
  },
  { immediate: true },
);

watch(selectedRecordId, () => {
  searchQuery.value = '';
  currentPage.value = 1;
});

watch(searchQuery, () => {
  currentPage.value = 1;
});

watch(totalPages, (pages) => {
  if (currentPage.value > pages) currentPage.value = pages;
});

onMounted(async () => {
  if (operation.customers.length === 0) await operation.loadCustomers();
  if (!meeting.selectedCustomerName && customerOptions.value[0]) {
    meeting.selectedCustomerName = customerOptions.value[0];
    return;
  }
  if (meeting.selectedCustomerName) {
    const companyId = selectedCompanyId.value || meeting.selectedCompanyId;
    meeting.selectedCompanyId = companyId;
    if (companyId) await meeting.loadHistory(companyId, meeting.selectedCustomerName);
  }
});

onUnmounted(stopPolling);
</script>

<template>
  <PageSection title="会议沟通">
    <template #actions>
      <button
        class="fixed-close-btn"
        type="button"
        title="关闭"
        aria-label="关闭会议沟通并返回上一页"
        @click="closeMeetingAnalysis"
      >×</button>
    </template>

    <div class="meeting-analysis-workspace">
      <section class="meeting-command-bar" aria-label="会议筛选和上传">
        <div class="meeting-control-field meeting-current-customer">
          <span>当前客户</span>
          <strong>{{ meeting.selectedCustomerName || '正在加载客户...' }}</strong>
        </div>

        <label class="meeting-control-field meeting-control-record">
          <span>会议记录</span>
          <select v-model="selectedRecordId" :disabled="meeting.records.length === 0">
            <option v-if="meeting.records.length === 0" value="">暂无会议记录</option>
            <option v-for="record in meeting.records" :key="recordKey(record)" :value="recordKey(record)">
              {{ recordOptionLabel(record) }}
            </option>
          </select>
        </label>

        <div class="meeting-upload-controls">
          <input
            ref="fileInput"
            class="meeting-file-input"
            type="file"
            accept="audio/*,video/*"
            aria-label="选择会议音频或视频文件"
            @change="chooseFile"
          />
          <button class="meeting-file-button" type="button" title="选择文件" @click="fileInput?.click()">
            <span aria-hidden="true">+</span>
            <span>{{ selectedFile?.name || '选择文件' }}</span>
          </button>
          <button
            class="btn btn-primary meeting-upload-button"
            type="button"
            :disabled="meeting.uploading || !meeting.selectedCustomerName"
            @click="upload"
          >
            {{ meeting.uploading ? '上传中...' : '上传并分析' }}
          </button>
        </div>
      </section>

      <div v-if="meeting.error" class="meeting-feedback meeting-feedback-error" role="alert">{{ meeting.error }}</div>
      <div v-else-if="meeting.message && !meeting.activeJob" class="meeting-feedback meeting-feedback-success">{{ meeting.message }}</div>

      <section v-if="meeting.activeJob" class="meeting-job-status" aria-live="polite">
        <div>
          <strong>{{ jobStatusLabel(meeting.activeJob.status) }}</strong>
          <span>{{ meeting.activeJob.progress }}%</span>
        </div>
        <div class="meeting-progress"><span :style="{ width: `${meeting.activeJob.progress || 0}%` }"></span></div>
        <p>{{ meeting.activeJob.message || meeting.message }}</p>
      </section>

      <div v-if="meeting.loading && meeting.records.length === 0" class="meeting-page-state">正在加载会议详情...</div>
      <div v-else-if="!selectedRecord" class="meeting-page-state">暂无会议记录</div>

      <template v-else>
        <section class="meeting-basic-band" aria-labelledby="meeting-basic-title">
          <div class="meeting-band-heading meeting-basic-heading">
            <div>
              <span class="meeting-eyebrow">会议详情</span>
              <h3 id="meeting-basic-title">会议基本信息</h3>
            </div>
            <div class="meeting-status-cluster" aria-label="会议状态">
              <span :class="['meeting-status', `is-${processingStatus.tone}`]">{{ processingStatus.label }}</span>
              <span :class="['meeting-status', `is-${transcriptStatus.tone}`]">{{ transcriptStatus.label }}</span>
            </div>
          </div>

          <dl class="meeting-meta-grid">
            <div>
              <dt>会议标题</dt>
              <dd class="meeting-meta-title">{{ cleanTranscriptText(selectedRecord.title || '会议记录') }}</dd>
            </div>
            <div>
              <dt>客户公司</dt>
              <dd>{{ customerName }}</dd>
            </div>
            <div>
              <dt>会议时长</dt>
              <dd>{{ formatMeetingDuration(selectedRecord.durationSeconds || selectedRecord.duration_seconds) }}</dd>
            </div>
            <div>
              <dt>处理状态</dt>
              <dd>{{ processingStatus.label }}</dd>
            </div>
            <div>
              <dt>转录状态</dt>
              <dd>{{ transcriptStatus.label }}</dd>
            </div>
            <div>
              <dt>创建时间</dt>
              <dd>{{ formatMeetingDate(selectedRecord.createdAt || selectedRecord.created_at) }}</dd>
            </div>
          </dl>
        </section>

        <section class="meeting-content-band" aria-labelledby="meeting-summary-title">
          <div class="meeting-band-heading">
            <div>
              <span class="meeting-eyebrow">AI 分析</span>
              <h3 id="meeting-summary-title">会议摘要</h3>
            </div>
            <button
              class="meeting-collapse-button"
              type="button"
              :aria-expanded="expanded.summary"
              :aria-label="expanded.summary ? '折叠会议摘要' : '展开会议摘要'"
              :title="expanded.summary ? '折叠' : '展开'"
              @click="toggleSection('summary')"
            >
              <span aria-hidden="true">{{ expanded.summary ? '−' : '+' }}</span>
            </button>
          </div>

          <div v-show="expanded.summary" class="meeting-summary-content">
            <div class="meeting-core-summary">
              <h4>核心摘要</h4>
              <p v-for="(paragraph, index) in coreSummary" :key="index">{{ paragraph }}</p>
              <p v-if="coreSummary.length === 0" class="meeting-empty-copy">暂无核心摘要</p>
            </div>

            <div class="meeting-summary-columns">
              <section>
                <h4>客户需求</h4>
                <ul v-if="customerNeeds.length">
                  <li v-for="item in customerNeeds" :key="item">{{ item }}</li>
                </ul>
                <p v-else class="meeting-empty-copy">暂无客户需求</p>
              </section>
              <section>
                <h4>痛点</h4>
                <ul v-if="painPoints.length">
                  <li v-for="item in painPoints" :key="item">{{ item }}</li>
                </ul>
                <p v-else class="meeting-empty-copy">暂无痛点</p>
              </section>
              <section>
                <h4>购买信号</h4>
                <ul v-if="buyingSignals.length">
                  <li v-for="item in buyingSignals" :key="item">{{ item }}</li>
                </ul>
                <p v-else class="meeting-empty-copy">暂无购买信号</p>
              </section>
            </div>

            <div v-if="keywords.length" class="meeting-keywords">
              <span>关键词</span>
              <div>
                <button
                  v-for="keyword in keywords"
                  :key="keyword"
                  type="button"
                  :class="['meeting-keyword', { active: searchQuery === keyword }]"
                  @click="applySearch(keyword)"
                >
                  {{ keyword }}
                </button>
              </div>
            </div>
          </div>
        </section>

        <section class="meeting-structured-grid" aria-label="会议结构化信息">
          <article class="meeting-structured-card is-todo">
            <header>
              <div>
                <h3>待办TODO</h3>
                <span>{{ actionItems.length }}</span>
              </div>
              <button
                class="meeting-collapse-button"
                type="button"
                :aria-expanded="expanded.todos"
                :aria-label="expanded.todos ? '折叠待办TODO' : '展开待办TODO'"
                :title="expanded.todos ? '折叠' : '展开'"
                @click="toggleSection('todos')"
              ><span aria-hidden="true">{{ expanded.todos ? '−' : '+' }}</span></button>
            </header>
            <ol v-show="expanded.todos" class="meeting-structured-list">
              <li v-for="(item, index) in actionItems" :key="`${item.task}-${index}`">
                <span class="meeting-item-index">{{ index + 1 }}</span>
                <div>
                  <p>{{ item.task }}</p>
                  <div class="meeting-item-meta">
                    <span>负责人：{{ item.owner }}</span>
                    <span>截止：{{ item.dueAt }}</span>
                  </div>
                </div>
              </li>
              <li v-if="actionItems.length === 0" class="meeting-structured-empty">暂无待办事项</li>
            </ol>
          </article>

          <article class="meeting-structured-card is-decision">
            <header>
              <div>
                <h3>会议决策</h3>
                <span>{{ decisions.length }}</span>
              </div>
              <button
                class="meeting-collapse-button"
                type="button"
                :aria-expanded="expanded.decisions"
                :aria-label="expanded.decisions ? '折叠会议决策' : '展开会议决策'"
                :title="expanded.decisions ? '折叠' : '展开'"
                @click="toggleSection('decisions')"
              ><span aria-hidden="true">{{ expanded.decisions ? '−' : '+' }}</span></button>
            </header>
            <ol v-show="expanded.decisions" class="meeting-structured-list">
              <li v-for="(item, index) in decisions" :key="`${item}-${index}`">
                <span class="meeting-item-marker" aria-hidden="true">✓</span>
                <p>{{ item }}</p>
              </li>
              <li v-if="decisions.length === 0" class="meeting-structured-empty">暂无会议决策</li>
            </ol>
          </article>

          <article class="meeting-structured-card is-risk">
            <header>
              <div>
                <h3>风险提醒</h3>
                <span>{{ risks.length }}</span>
              </div>
              <button
                class="meeting-collapse-button"
                type="button"
                :aria-expanded="expanded.risks"
                :aria-label="expanded.risks ? '折叠风险提醒' : '展开风险提醒'"
                :title="expanded.risks ? '折叠' : '展开'"
                @click="toggleSection('risks')"
              ><span aria-hidden="true">{{ expanded.risks ? '−' : '+' }}</span></button>
            </header>
            <ol v-show="expanded.risks" class="meeting-structured-list">
              <li v-for="(item, index) in risks" :key="`${item}-${index}`">
                <span class="meeting-item-marker" aria-hidden="true">!</span>
                <p>{{ item }}</p>
              </li>
              <li v-if="risks.length === 0" class="meeting-structured-empty">暂无风险提醒</li>
            </ol>
          </article>
        </section>

        <section ref="transcriptSection" class="meeting-transcript-band" aria-labelledby="meeting-transcript-title">
          <div class="meeting-band-heading">
            <div>
              <span class="meeting-eyebrow">会议原文</span>
              <h3 id="meeting-transcript-title">逐段对话</h3>
            </div>
            <div class="meeting-transcript-heading-actions">
              <span>{{ normalizedSearch ? `匹配 ${filteredSegments.length} 段` : `共 ${transcriptSegments.length} 段` }}</span>
              <button
                class="meeting-collapse-button"
                type="button"
                :aria-expanded="expanded.transcript"
                :aria-label="expanded.transcript ? '折叠逐段对话' : '展开逐段对话'"
                :title="expanded.transcript ? '折叠' : '展开'"
                @click="toggleSection('transcript')"
              ><span aria-hidden="true">{{ expanded.transcript ? '−' : '+' }}</span></button>
            </div>
          </div>

          <div v-show="expanded.transcript" class="meeting-transcript-content">
            <div class="meeting-search-row">
              <label for="meeting-transcript-search">搜索对话</label>
              <div class="meeting-search-field">
                <input
                  id="meeting-transcript-search"
                  v-model="searchQuery"
                  type="search"
                  placeholder="输入关键词"
                  autocomplete="off"
                />
                <button
                  v-if="searchQuery"
                  type="button"
                  aria-label="清空搜索"
                  title="清空"
                  @click="searchQuery = ''"
                >×</button>
              </div>
            </div>

            <ol v-if="visibleSegments.length" class="meeting-transcript-list">
              <li
                v-for="segment in visibleSegments"
                :key="segment.sequence"
                :class="['meeting-transcript-item', { 'is-match': normalizedSearch }]"
              >
                <span :class="['meeting-timeline-dot', `is-${segment.speaker.tone}`]" aria-hidden="true"></span>
                <div class="meeting-transcript-meta">
                  <time>{{ formatTranscriptRange(segment.start, segment.end) }}</time>
                  <strong :class="`is-${segment.speaker.tone}`">{{ segment.speaker.label }}</strong>
                </div>
                <p>
                  <template v-for="(chunk, index) in splitHighlightedText(segment.text, searchQuery)" :key="index">
                    <mark v-if="chunk.match">{{ chunk.text }}</mark>
                    <span v-else>{{ chunk.text }}</span>
                  </template>
                </p>
              </li>
            </ol>
            <div v-else class="meeting-transcript-empty">未找到匹配的对话内容</div>

            <nav v-if="filteredSegments.length" class="meeting-pagination" aria-label="逐段对话分页">
              <button type="button" :disabled="currentPage === 1" @click="currentPage -= 1">上一页</button>
              <span>第 {{ currentPage }} 页 / 共 {{ totalPages }} 页</span>
              <button type="button" :disabled="currentPage === totalPages" @click="currentPage += 1">下一页</button>
            </nav>
          </div>
        </section>
      </template>
    </div>
  </PageSection>
</template>

<style scoped>
.meeting-analysis-workspace {
  color: var(--text-primary, #172033);
  background: #f6f8fb;
}

.meeting-command-bar {
  display: grid;
  grid-template-columns: minmax(180px, 0.75fr) minmax(260px, 1.25fr) auto;
  gap: 12px;
  align-items: end;
  padding: 14px 16px;
  background: #fff;
  border-bottom: 1px solid var(--border-light, #e4e9f0);
}

.meeting-control-field {
  display: grid;
  min-width: 0;
  gap: 5px;
  color: var(--text-muted, #667085);
  font-size: 12px;
  font-weight: 700;
}

.meeting-control-field select {
  width: 100%;
  min-width: 0;
  height: 36px;
  padding: 0 10px;
  color: var(--text-primary, #172033);
  background: #fff;
  border: 1px solid var(--border, #d4dbe5);
  border-radius: 6px;
}

.meeting-upload-controls {
  display: grid;
  grid-template-columns: minmax(110px, 190px) auto;
  gap: 8px;
}

.meeting-file-input {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
}

.meeting-file-button {
  display: flex;
  min-width: 0;
  height: 36px;
  gap: 7px;
  align-items: center;
  padding: 0 11px;
  color: var(--text-secondary, #344054);
  cursor: pointer;
  background: #fff;
  border: 1px solid var(--border, #d4dbe5);
  border-radius: 6px;
}

.meeting-file-button span:first-child {
  font-size: 18px;
  line-height: 1;
}

.meeting-file-button span:last-child {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.meeting-upload-button {
  height: 36px;
  white-space: nowrap;
}

.meeting-feedback,
.meeting-job-status {
  margin: 12px 16px 0;
  padding: 10px 12px;
  border: 1px solid;
  border-radius: 6px;
  font-size: 13px;
}

.meeting-feedback-error {
  color: #b42318;
  background: #fff5f4;
  border-color: #fecdca;
}

.meeting-feedback-success {
  color: #067647;
  background: #ecfdf3;
  border-color: #abefc6;
}

.meeting-job-status {
  display: grid;
  gap: 7px;
  color: #175cd3;
  background: #eff8ff;
  border-color: #b2ddff;
}

.meeting-job-status > div:first-child {
  display: flex;
  justify-content: space-between;
}

.meeting-job-status p {
  margin: 0;
}

.meeting-progress {
  height: 6px;
  overflow: hidden;
  background: #d1e9ff;
  border-radius: 3px;
}

.meeting-progress span {
  display: block;
  height: 100%;
  background: #1570ef;
}

.meeting-page-state {
  min-height: 220px;
  padding: 80px 20px;
  color: var(--text-muted, #667085);
  text-align: center;
}

.meeting-basic-band,
.meeting-content-band,
.meeting-transcript-band {
  padding: 20px 22px;
  background: #fff;
  border-top: 1px solid var(--border-light, #e4e9f0);
}

.meeting-basic-band {
  border-top: 0;
}

.meeting-band-heading,
.meeting-structured-card > header {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
}

.meeting-band-heading h3,
.meeting-structured-card h3 {
  margin: 2px 0 0;
  font-size: 16px;
  line-height: 1.35;
}

.meeting-eyebrow {
  color: #667085;
  font-size: 11px;
  font-weight: 700;
}

.meeting-status-cluster {
  display: flex;
  gap: 7px;
  flex-wrap: wrap;
}

.meeting-status {
  padding: 4px 8px;
  border: 1px solid;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 700;
}

.meeting-status.is-success {
  color: #067647;
  background: #ecfdf3;
  border-color: #abefc6;
}

.meeting-status.is-danger {
  color: #b42318;
  background: #fff5f4;
  border-color: #fecdca;
}

.meeting-status.is-warning {
  color: #93370d;
  background: #fffaeb;
  border-color: #fedf89;
}

.meeting-status.is-neutral {
  color: #475467;
  background: #f2f4f7;
  border-color: #d0d5dd;
}

.meeting-meta-grid {
  display: grid;
  grid-template-columns: minmax(220px, 1.5fr) repeat(5, minmax(110px, 1fr));
  gap: 14px 20px;
  margin: 18px 0 0;
}

.meeting-meta-grid > div {
  min-width: 0;
}

.meeting-meta-grid dt {
  margin-bottom: 4px;
  color: var(--text-muted, #667085);
  font-size: 11px;
}

.meeting-meta-grid dd {
  min-width: 0;
  margin: 0;
  color: var(--text-primary, #172033);
  font-size: 13px;
  font-weight: 650;
  overflow-wrap: anywhere;
}

.meeting-meta-grid .meeting-meta-title {
  font-size: 14px;
  font-weight: 750;
}

.meeting-collapse-button {
  display: grid;
  width: 30px;
  height: 30px;
  flex: 0 0 30px;
  place-items: center;
  padding: 0;
  color: #475467;
  cursor: pointer;
  background: #f8fafc;
  border: 1px solid var(--border, #d4dbe5);
  border-radius: 5px;
  font-size: 18px;
  line-height: 1;
}

.meeting-summary-content,
.meeting-transcript-content {
  margin-top: 18px;
}

.meeting-core-summary {
  padding-bottom: 18px;
  border-bottom: 1px solid var(--border-light, #e4e9f0);
}

.meeting-core-summary h4,
.meeting-summary-columns h4 {
  margin: 0 0 8px;
  color: #344054;
  font-size: 13px;
}

.meeting-core-summary p {
  max-width: 1080px;
  margin: 6px 0 0;
  color: var(--text-secondary, #344054);
  font-size: 14px;
  line-height: 1.8;
}

.meeting-summary-columns {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0;
  padding: 18px 0;
}

.meeting-summary-columns section {
  min-width: 0;
  padding: 0 20px;
  border-left: 1px solid var(--border-light, #e4e9f0);
}

.meeting-summary-columns section:first-child {
  padding-left: 0;
  border-left: 0;
}

.meeting-summary-columns ul {
  display: grid;
  gap: 7px;
  padding: 0;
  margin: 0;
  list-style: none;
}

.meeting-summary-columns li {
  position: relative;
  padding-left: 13px;
  color: var(--text-secondary, #344054);
  font-size: 13px;
  line-height: 1.65;
}

.meeting-summary-columns li::before {
  position: absolute;
  top: 9px;
  left: 0;
  width: 4px;
  height: 4px;
  content: '';
  background: #667085;
  border-radius: 50%;
}

.meeting-empty-copy {
  margin: 0;
  color: var(--text-muted, #667085);
  font-size: 13px;
}

.meeting-keywords {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 12px;
  align-items: start;
  padding-top: 14px;
  border-top: 1px solid var(--border-light, #e4e9f0);
}

.meeting-keywords > span {
  padding-top: 5px;
  color: #475467;
  font-size: 12px;
  font-weight: 700;
}

.meeting-keywords > div {
  display: flex;
  gap: 7px;
  flex-wrap: wrap;
}

.meeting-keyword {
  padding: 4px 9px;
  color: #175cd3;
  cursor: pointer;
  background: #eff8ff;
  border: 1px solid #b2ddff;
  border-radius: 4px;
  font-size: 12px;
}

.meeting-keyword.active {
  color: #fff;
  background: #175cd3;
  border-color: #175cd3;
}

.meeting-structured-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  padding: 18px 22px;
  border-top: 1px solid var(--border-light, #e4e9f0);
}

.meeting-structured-card {
  min-width: 0;
  overflow: hidden;
  background: #fff;
  border: 1px solid var(--border, #d4dbe5);
  border-radius: 8px;
}

.meeting-structured-card > header {
  min-height: 54px;
  padding: 11px 13px;
  border-bottom: 1px solid var(--border-light, #e4e9f0);
}

.meeting-structured-card > header > div {
  display: flex;
  gap: 8px;
  align-items: center;
}

.meeting-structured-card > header h3 {
  margin: 0;
  font-size: 14px;
}

.meeting-structured-card > header > div > span {
  display: grid;
  min-width: 22px;
  height: 20px;
  place-items: center;
  color: #475467;
  background: #f2f4f7;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 700;
}

.meeting-structured-card.is-todo {
  border-top: 3px solid #1570ef;
}

.meeting-structured-card.is-decision {
  border-top: 3px solid #079455;
}

.meeting-structured-card.is-risk {
  border-top: 3px solid #dc6803;
}

.meeting-structured-list {
  max-height: 400px;
  padding: 0 14px;
  margin: 0;
  overflow: auto;
  list-style: none;
}

.meeting-structured-list > li {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr);
  gap: 9px;
  padding: 14px 0;
  border-top: 1px solid var(--border-light, #e4e9f0);
}

.meeting-structured-list > li:first-child {
  border-top: 0;
}

.meeting-structured-list p {
  margin: 0;
  color: var(--text-secondary, #344054);
  font-size: 13px;
  line-height: 1.65;
  overflow-wrap: anywhere;
}

.meeting-item-index,
.meeting-item-marker {
  display: grid;
  width: 22px;
  height: 22px;
  place-items: center;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 800;
}

.meeting-item-index {
  color: #175cd3;
  background: #eff8ff;
}

.is-decision .meeting-item-marker {
  color: #067647;
  background: #ecfdf3;
}

.is-risk .meeting-item-marker {
  color: #b54708;
  background: #fffaeb;
}

.meeting-item-meta {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 9px;
}

.meeting-item-meta span {
  padding: 3px 6px;
  color: #475467;
  background: #f2f4f7;
  border-radius: 4px;
  font-size: 11px;
}

.meeting-structured-list .meeting-structured-empty {
  display: block;
  color: var(--text-muted, #667085);
  text-align: center;
}

.meeting-transcript-heading-actions {
  display: flex;
  gap: 12px;
  align-items: center;
}

.meeting-transcript-heading-actions > span {
  color: var(--text-muted, #667085);
  font-size: 12px;
}

.meeting-search-row {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: flex-end;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border-light, #e4e9f0);
}

.meeting-search-row label {
  color: #475467;
  font-size: 12px;
  font-weight: 700;
}

.meeting-search-field {
  position: relative;
  width: min(100%, 320px);
}

.meeting-search-field input {
  width: 100%;
  height: 36px;
  padding: 0 38px 0 11px;
  color: var(--text-primary, #172033);
  background: #fff;
  border: 1px solid var(--border, #d4dbe5);
  border-radius: 6px;
}

.meeting-search-field button {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 28px;
  height: 28px;
  padding: 0;
  color: #667085;
  cursor: pointer;
  background: transparent;
  border: 0;
  font-size: 18px;
}

.meeting-transcript-list {
  position: relative;
  display: grid;
  padding: 6px 0 0;
  margin: 0;
  list-style: none;
}

.meeting-transcript-list::before {
  position: absolute;
  top: 20px;
  bottom: 20px;
  left: 92px;
  width: 1px;
  content: '';
  background: #d0d5dd;
}

.meeting-transcript-item {
  position: relative;
  display: grid;
  grid-template-columns: 76px minmax(0, 1fr);
  gap: 38px;
  padding: 18px 0;
}

.meeting-transcript-item + .meeting-transcript-item {
  border-top: 1px solid #f2f4f7;
}

.meeting-transcript-item.is-match {
  background: #fffdf5;
}

.meeting-timeline-dot {
  position: absolute;
  z-index: 1;
  top: 24px;
  left: 87px;
  width: 11px;
  height: 11px;
  background: #1570ef;
  border: 3px solid #fff;
  border-radius: 50%;
  box-shadow: 0 0 0 1px #84adff;
}

.meeting-timeline-dot.is-secondary {
  background: #079455;
  box-shadow: 0 0 0 1px #75e0a7;
}

.meeting-transcript-meta {
  display: grid;
  gap: 7px;
  align-content: start;
}

.meeting-transcript-meta time {
  color: #667085;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 11px;
  white-space: nowrap;
}

.meeting-transcript-meta strong {
  color: #175cd3;
  font-size: 12px;
}

.meeting-transcript-meta strong.is-secondary {
  color: #067647;
}

.meeting-transcript-item > p {
  margin: 0;
  color: var(--text-secondary, #344054);
  font-size: 14px;
  line-height: 1.8;
  overflow-wrap: anywhere;
}

.meeting-transcript-item mark {
  padding: 1px 2px;
  color: #7a2e0e;
  background: #fef0c7;
  border-radius: 2px;
}

.meeting-transcript-empty {
  padding: 50px 16px;
  color: var(--text-muted, #667085);
  text-align: center;
}

.meeting-pagination {
  display: grid;
  grid-template-columns: 82px auto 82px;
  gap: 12px;
  align-items: center;
  justify-content: center;
  padding-top: 16px;
  border-top: 1px solid var(--border-light, #e4e9f0);
}

.meeting-pagination button {
  height: 32px;
  color: #344054;
  cursor: pointer;
  background: #fff;
  border: 1px solid var(--border, #d4dbe5);
  border-radius: 5px;
}

.meeting-pagination button:disabled {
  cursor: not-allowed;
  opacity: .45;
}

.meeting-pagination span {
  min-width: 118px;
  color: #667085;
  font-size: 12px;
  text-align: center;
}

.meeting-file-button:focus-visible,
.meeting-collapse-button:focus-visible,
.meeting-keyword:focus-visible,
.meeting-pagination button:focus-visible,
.meeting-search-field input:focus-visible,
.meeting-control-field select:focus-visible {
  outline: 2px solid var(--blue-primary, #2563eb);
  outline-offset: 2px;
}

@media (max-width: 1180px) {
  .meeting-command-bar {
    grid-template-columns: minmax(180px, .8fr) minmax(260px, 1.2fr);
  }

  .meeting-upload-controls {
    grid-column: 1 / -1;
    justify-content: end;
  }

  .meeting-meta-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 900px) {
  .meeting-structured-grid,
  .meeting-summary-columns {
    grid-template-columns: 1fr;
  }

  .meeting-summary-columns {
    gap: 16px;
  }

  .meeting-summary-columns section,
  .meeting-summary-columns section:first-child {
    padding: 0 0 16px;
    border: 0;
    border-bottom: 1px solid var(--border-light, #e4e9f0);
  }

  .meeting-summary-columns section:last-child {
    padding-bottom: 0;
    border-bottom: 0;
  }
}

@media (max-width: 680px) {
  .meeting-command-bar,
  .meeting-meta-grid {
    grid-template-columns: 1fr;
  }

  .meeting-upload-controls {
    grid-column: auto;
    grid-template-columns: minmax(0, 1fr) auto;
    justify-content: stretch;
  }

  .meeting-basic-band,
  .meeting-content-band,
  .meeting-transcript-band {
    padding: 18px 15px;
  }

  .meeting-structured-grid {
    padding: 15px;
  }

  .meeting-basic-heading {
    align-items: flex-start;
  }

  .meeting-search-row {
    display: grid;
    justify-content: stretch;
  }

  .meeting-search-field {
    width: 100%;
  }

  .meeting-transcript-list::before {
    left: 8px;
  }

  .meeting-transcript-item {
    grid-template-columns: 1fr;
    gap: 9px;
    padding: 18px 0 18px 26px;
  }

  .meeting-timeline-dot {
    top: 23px;
    left: 3px;
  }

  .meeting-transcript-meta {
    display: flex;
    gap: 10px;
    align-items: center;
  }

  .meeting-pagination {
    grid-template-columns: 72px minmax(112px, auto) 72px;
    gap: 6px;
  }
}
</style>
