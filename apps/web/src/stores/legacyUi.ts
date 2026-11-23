import { defineStore } from 'pinia';

import type { CurrentUser } from './auth';

export type LegacyRole = 'sales' | 'boss';

function roleFromUser(user: CurrentUser | null): LegacyRole {
  return user?.accountType === 'sales' ? 'sales' : 'boss';
}

export const useLegacyUiStore = defineStore('legacyUi', {
  state: () => ({
    currentRole: 'sales' as LegacyRole,
    salesNavTab: 'ai-staff' as 'ai-staff' | 'database' | 'projects',
    settingsOpen: false,
    paOpen: false,
    pendingEmailTarget: null as null | {
      companyId: string;
      emailId: string;
      messageId?: string;
      notificationId?: string;
    },
  }),
  getters: {
    roleName: (state) => (state.currentRole === 'boss' ? '战略账号' : '销售账号'),
    roleTitle: (state) => (state.currentRole === 'boss' ? '经营视角' : '日本销售'),
    roleAvatar: (state) => (state.currentRole === 'boss' ? '战' : '销'),
  },
  actions: {
    applyUser(user: CurrentUser | null) {
      this.currentRole = roleFromUser(user);
      this.settingsOpen = false;
      this.paOpen = false;
      this.pendingEmailTarget = null;
    },
    openEmailTarget(target: { companyId: string; emailId: string; messageId?: string; notificationId?: string }) {
      this.pendingEmailTarget = target;
      this.paOpen = false;
    },
    clearEmailTarget() {
      this.pendingEmailTarget = null;
    },
  },
});
