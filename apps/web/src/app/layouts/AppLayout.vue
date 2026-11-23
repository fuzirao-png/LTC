<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import AppSidebar from '../../shared/components/AppSidebar.vue';
import TopHeader from '../../shared/components/TopHeader.vue';
import UserProfile from '../../shared/components/UserProfile.vue';
import paBirdUrl from '../../assets/pa-bird.webp';
import { operationApi, type PaNotification, type InboundMailDetail } from '../../services/operationApi';
import { useAuthStore } from '../../stores/auth';
import { useAppStore } from '../../stores/app';
import { useLegacyUiStore } from '../../stores/legacyUi';
import {
  canAccessMailNotifications,
  dedupeMailNotifications,
  removeCompletedReminder,
} from './paNotificationAccess.js';

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const app = useAppStore();
const legacyUi = useLegacyUiStore();
const paNotifications = ref<PaNotification[]>([]);
const paNotificationsLoading = ref(false);
const emailDetail = ref<InboundMailDetail | null>(null);
const emailDetailLoading = ref(false);
const emailDetailError = ref('');
let paRefreshTimer: ReturnType<typeof setInterval> | null = null;
const canLoadMailNotifications = computed(() => canAccessMailNotifications(auth.currentUser));

watch(() => route.path, () => {
  legacyUi.settingsOpen = false;
  app.isProfileOpen = false;
});

type PaReminder = {
  id: string;
  label: string;
  meta: string;
  action: '处理' | '查看';
  path: string;
  tone: 'urgent' | 'attention' | 'info';
};

const salesReminders = ref<PaReminder[]>([
  { id: 'reply-priority', label: '邮件回复优先级：Sakura Travel Corp 索要产品资料', meta: '高优先级', action: '处理', path: '/customer-operation', tone: 'urgent' },
  { id: 'meeting-time', label: '会议时间：Pacific TMC 产品演示，明天 10:00', meta: '待确认', action: '查看', path: '/customer-operation', tone: 'attention' },
  { id: 'proposal-priority', label: '方案发送优先级：GlobalLink 企业方案待发送', meta: '今天完成', action: '处理', path: '/customer-operation', tone: 'info' },
]);

const bossReminders: PaReminder[] = [
  { id: 'europe-risk', label: '欧洲区转化率下滑 12%，需评估资源调整', meta: '待决策', action: '查看', path: '/boss-dashboard', tone: 'urgent' },
  { id: 'japan-growth', label: '日本区增速 11%，建议增加资源投入', meta: '待决策', action: '查看', path: '/boss-lead-assign', tone: 'attention' },
];

const paReminders = computed(() => (legacyUi.currentRole === 'boss' ? bossReminders : salesReminders.value));
const paBadgeCount = computed(() => paReminders.value.length + (legacyUi.currentRole === 'sales' ? paNotifications.value.length : 0));

const paCommandItems = ['增加日本资源', '主攻B端客户群', '扩大GEO投放'];
const bossCommand = ref('');
const bossCommandHistory = ref<string[]>([]);

const selectBossCommand = (command: string) => {
  bossCommand.value = command;
};

const submitBossCommand = () => {
  const command = bossCommand.value.trim();
  if (!command) return;
  bossCommandHistory.value.unshift(command);
  bossCommand.value = '';
};

const paAssistantName = computed(
  () => auth.currentUser?.name || auth.currentUser?.username || legacyUi.roleName,
);
const pageTitle = computed(() => (
  route.path === '/boss-dashboard'
    ? `${paAssistantName.value} · 经营驾驶舱`
    : String(route.meta.title || '总览')
));
const breadcrumbRoot = computed(() => {
  const path = route.path;
  if (legacyUi.currentRole === 'boss') return path === '/boss-dashboard' ? '总览' : 'Agent';
  if (path === '/dashboard') return '总览';
  if (path === '/db-cases' || path === '/db-scripts') return '数据库';
  return 'AI agent';
});

const loadPaNotifications = async () => {
  if (!canLoadMailNotifications.value) {
    paNotifications.value = [];
    return;
  }
  paNotificationsLoading.value = true;
  try {
    const items = await operationApi.listInboundMailNotifications();
    paNotifications.value = dedupeMailNotifications(items.filter((notification) => !notification.read));
  } catch (error) {
    console.warn('Failed to load PA mail notifications', error);
  } finally {
    paNotificationsLoading.value = false;
  }
};

const openPaNotification = async (notification: PaNotification) => {
  const target = notification.notificationTarget || {};
  const companyId = target.companyId || notification.companyId || '';
  const emailId = target.emailId || notification.emailId || '';

  try {
    await operationApi.markInboundMailNotificationRead(notification.id);
  } catch {
    // Keep navigation working even if persistence fails.
  }
  paNotifications.value = paNotifications.value.filter((item) => item.id !== notification.id);

  // When the inbound email is linked to a known customer, jump straight to that
  // customer's email history detail page.
  if (companyId && emailId) {
    legacyUi.openEmailTarget({
      companyId,
      emailId,
      messageId: target.messageId || notification.messageId,
      notificationId: notification.id,
    });
    legacyUi.paOpen = false;
    await router.push('/customer-operation');
    return;
  }

  // Otherwise (sender not matched to a customer) show the raw email detail inline
  // so the notification is still actionable instead of doing nothing.
  emailDetail.value = null;
  emailDetailError.value = '';
  emailDetailLoading.value = true;
  legacyUi.paOpen = false;
  try {
    emailDetail.value = await operationApi.getInboundMailNotificationDetail(notification.id);
  } catch (error) {
    emailDetailError.value = error instanceof Error ? error.message : '邮件详情加载失败';
  } finally {
    emailDetailLoading.value = false;
  }
};

const closeEmailDetail = () => {
  emailDetail.value = null;
  emailDetailError.value = '';
  emailDetailLoading.value = false;
};

const openPaReminder = async (reminder: PaReminder) => {
  legacyUi.paOpen = false;
  await router.push(reminder.path);
};

const completePaReminder = (reminderId: string) => {
  salesReminders.value = removeCompletedReminder(salesReminders.value, reminderId);
};

const handlePaReminder = (reminder: PaReminder) => {
  if (legacyUi.currentRole === 'boss') {
    void openPaReminder(reminder);
    return;
  }
  completePaReminder(reminder.id);
};

const fabEl = ref<HTMLElement | null>(null);
const fabLeft = ref<number | null>(null);
const fabBottom = ref<number | null>(null);
let dragging = false;
let hasMoved = false;
let dragStartX = 0;
let dragStartY = 0;
let dragStartLeft = 0;
let dragStartBottom = 0;

function startDrag(e: MouseEvent) {
  if (!fabEl.value) return;
  e.preventDefault();
  dragging = true;
  hasMoved = false;
  const rect = fabEl.value.getBoundingClientRect();
  dragStartX = e.clientX;
  dragStartY = e.clientY;
  dragStartLeft = rect.left;
  dragStartBottom = window.innerHeight - rect.bottom;
  fabEl.value.style.transition = 'none';
  document.addEventListener('mousemove', onDrag);
  document.addEventListener('mouseup', stopDrag);
}

function onDrag(e: MouseEvent) {
  if (!dragging) return;
  const dx = e.clientX - dragStartX;
  const dy = e.clientY - dragStartY;
  if (Math.abs(dx) < 3 && Math.abs(dy) < 3) return;
  hasMoved = true;
  const size = 64;
  fabLeft.value = Math.max(8, Math.min(window.innerWidth - size - 8, dragStartLeft + dx));
  fabBottom.value = Math.max(8, Math.min(window.innerHeight - size - 8, dragStartBottom - dy));
}

function stopDrag() {
  dragging = false;
  document.removeEventListener('mousemove', onDrag);
  document.removeEventListener('mouseup', stopDrag);
  if (fabEl.value) fabEl.value.style.transition = 'all 0.3s';
}

function onFabClick() {
  if (hasMoved) {
    hasMoved = false;
    return;
  }
  legacyUi.paOpen = !legacyUi.paOpen;
  if (legacyUi.paOpen && canLoadMailNotifications.value) void loadPaNotifications();
}

const fabStyle = computed(() => {
  if (fabLeft.value === null || fabBottom.value === null) return {};
  return { left: `${fabLeft.value}px`, bottom: `${fabBottom.value}px`, right: 'auto' };
});

const popupStyle = computed(() => {
  if (fabLeft.value === null || fabBottom.value === null) return {};
  return { left: `${Math.max(8, fabLeft.value - 420 + 64)}px`, bottom: `${fabBottom.value + 72}px`, right: 'auto' };
});

function onDocumentClick(e: MouseEvent) {
  if (!legacyUi.paOpen) return;
  const popup = document.getElementById('paPopup');
  const fab = fabEl.value;
  if (popup && fab && !popup.contains(e.target as Node) && !fab.contains(e.target as Node)) {
    legacyUi.paOpen = false;
  }
}

function onDocumentKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && legacyUi.paOpen) legacyUi.paOpen = false;
}

onMounted(() => {
  document.addEventListener('click', onDocumentClick);
  window.addEventListener('keydown', onDocumentKeydown);
  if (!canLoadMailNotifications.value) return;
  void loadPaNotifications();
  paRefreshTimer = window.setInterval(() => {
    if (!legacyUi.paOpen) {
      void loadPaNotifications();
    }
  }, 15000);
});

onUnmounted(() => {
  document.removeEventListener('click', onDocumentClick);
  window.removeEventListener('keydown', onDocumentKeydown);
  if (paRefreshTimer) {
    window.clearInterval(paRefreshTimer);
    paRefreshTimer = null;
  }
});
</script>

<template>
  <div class="app-shell legacy-shell">
    <AppSidebar />
    <main class="app-main">
      <TopHeader :breadcrumb="breadcrumbRoot" :title="pageTitle" />
      <section class="page-body legacy-page-body">
        <RouterView />
      </section>
    </main>
    <UserProfile />

    <button
      ref="fabEl"
      :class="['legacy-pa-fab', { boss: legacyUi.currentRole === 'boss' }]"
      :style="fabStyle"
      type="button"
      :title="legacyUi.currentRole === 'boss' ? '战略指令' : 'PA 助手'"
      @mousedown="startDrag"
      @click="onFabClick"
    >
      <span class="legacy-pa-avatar">
        <img :src="paBirdUrl" alt="" />
      </span>
      <span class="legacy-fab-badge">{{ paBadgeCount }}</span>
    </button>

    <div
      v-if="legacyUi.paOpen"
      id="paPopup"
      class="legacy-pa-popup"
      :style="popupStyle"
    >
      <div class="legacy-pa-head">
        <strong v-if="legacyUi.currentRole === 'boss'">{{ paAssistantName }} · 战略指令</strong>
        <strong v-else>PA · {{ paAssistantName }}的助手</strong>
        <button type="button" @click="legacyUi.paOpen = false">✕</button>
      </div>
      <div class="legacy-pa-body">
        <template v-if="legacyUi.currentRole === 'boss'">
          <div class="pa-section-title">战略简报</div>
          <p class="boss-pa-brief">日本区线索质量与承接效率保持领先；欧洲区转化下滑，需要评估资源配置和线索完整度。</p>
        </template>
        <div class="pa-section-title">{{ legacyUi.currentRole === 'boss' ? '待决策' : '重要事项' }} · {{ paReminders.length }} 条</div>
        <div class="pa-reminder-list">
          <button
            v-for="reminder in paReminders"
            :key="reminder.id"
            :class="['pa-reminder-card', reminder.tone]"
            type="button"
            :aria-label="legacyUi.currentRole === 'sales' ? `完成事项：${reminder.label}` : reminder.label"
            @click="handlePaReminder(reminder)"
          >
            <span class="pa-reminder-icon" aria-hidden="true">{{ legacyUi.currentRole === 'boss' ? '!' : '📧' }}</span>
            <span class="pa-reminder-copy">
              <strong>{{ reminder.label }}</strong>
              <small>{{ reminder.meta }}</small>
            </span>
            <span class="pa-reminder-action">{{ legacyUi.currentRole === 'sales' ? '✓' : reminder.action }}</span>
          </button>
        </div>

        <template v-if="legacyUi.currentRole === 'boss'">
          <div class="pa-section-title">快捷指令</div>
          <div class="legacy-pa-actions">
            <button v-for="item in paCommandItems" :key="item" type="button" @click="selectBossCommand(item)">
              {{ item }}
            </button>
          </div>
          <div class="pa-section-title">指令记录</div>
          <div v-if="bossCommandHistory.length" class="boss-command-history">
            <span v-for="(item, index) in bossCommandHistory" :key="`${item}-${index}`">{{ item }}</span>
          </div>
          <div v-else class="legacy-empty-nav">暂无指令记录</div>
          <div class="boss-command-input">
            <input v-model="bossCommand" type="text" placeholder="输入战略指令" @keydown.enter="submitBossCommand" />
            <button type="button" :disabled="!bossCommand.trim()" @click="submitBossCommand">下达</button>
          </div>
        </template>

        <template v-if="canLoadMailNotifications">
          <div class="pa-section-title">邮件提醒</div>
          <div v-if="paNotificationsLoading" class="legacy-empty-nav">正在加载通知...</div>
          <div v-else-if="paNotifications.length === 0" class="legacy-empty-nav">暂无邮件提醒</div>
          <button
            v-for="notification in paNotifications"
            :key="notification.id"
            type="button"
            class="legacy-pa-notification"
            @click="openPaNotification(notification)"
          >
            <strong>{{ notification.customerName || notification.subject || '未命名邮件' }}</strong>
            <span>{{ notification.body || notification.title }}</span>
          </button>
        </template>
      </div>
    </div>

    <div
      v-if="emailDetail || emailDetailLoading || emailDetailError"
      class="inbound-mail-detail-overlay"
      @click.self="closeEmailDetail"
    >
      <div class="inbound-mail-detail-modal">
        <div class="inbound-mail-detail-head">
          <strong>邮件详情</strong>
          <button type="button" @click="closeEmailDetail">✕</button>
        </div>
        <div v-if="emailDetailLoading" class="inbound-mail-detail-body">正在加载邮件详情...</div>
        <div v-else-if="emailDetailError" class="inbound-mail-detail-body inbound-mail-detail-error">
          {{ emailDetailError }}
        </div>
        <div v-else-if="emailDetail" class="inbound-mail-detail-body">
          <div class="inbound-mail-detail-subject">{{ emailDetail.subject || '（无主题）' }}</div>
          <div class="inbound-mail-detail-meta">
            <span><em>发件人</em>{{ emailDetail.from || '—' }}</span>
            <span><em>收件人</em>{{ emailDetail.to || '—' }}</span>
            <span v-if="emailDetail.receivedAt"><em>时间</em>{{ emailDetail.receivedAt }}</span>
          </div>
          <pre class="inbound-mail-detail-content">{{ emailDetail.bodyText || emailDetail.bodyPreview || '（无正文）' }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>
