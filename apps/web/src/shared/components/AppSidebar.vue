<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { useAuthStore } from '../../stores/auth';
import { useAppStore } from '../../stores/app';
import { useLegacyUiStore } from '../../stores/legacyUi';
import { regionLabel } from '../utils/labels';

const auth = useAuthStore();
const app = useAppStore();
const legacyUi = useLegacyUiStore();
const route = useRoute();
const router = useRouter();
const settingsEl = ref<HTMLElement | null>(null);

const salesAiItems = [
  { label: '客户分配', path: '/customer-allocation' },
  { label: '客户分析', path: '/customer-analysis' },
  { label: '客户运营', path: '/customer-operation' },
];

const bossItems = [
  { label: '线索收集', path: '/lead-collection' },
  { label: '线索分析', path: '/lead-analysis' },
  { label: '客户分配', path: '/boss-lead-assign' },
  { label: '销售管理', path: '/boss-sales-mgmt' },
];

const salesVisibleItems = computed(() => {
  if (legacyUi.salesNavTab === 'projects') return [];
  return salesAiItems;
});

const displayName = computed(() => {
  return auth.currentUser?.name || auth.currentUser?.username || legacyUi.roleName;
});
const displayRole = computed(() => {
  if (!auth.currentUser) return legacyUi.roleTitle;
  if (auth.currentUser.accountType === 'sales') {
    return `${regionLabel(auth.currentUser.regionCode)}区域-${auth.currentUser.salesTier || '未分级'}等级`;
  }
  return '战略管理';
});
const displayAvatar = computed(() => displayName.value.slice(0, 1).toUpperCase());
const isActive = (path: string) => route.path === path;

const openUserProfile = () => {
  legacyUi.settingsOpen = false;
  app.isProfileOpen = true;
};

const closeSettingsOutside = (event: MouseEvent) => {
  if (legacyUi.settingsOpen && settingsEl.value && !settingsEl.value.contains(event.target as Node)) {
    legacyUi.settingsOpen = false;
  }
};

onMounted(() => document.addEventListener('click', closeSettingsOutside));
onUnmounted(() => document.removeEventListener('click', closeSettingsOutside));

const logout = async () => {
  legacyUi.settingsOpen = false;
  legacyUi.paOpen = false;
  await auth.logout();
  await router.replace('/login');
};
</script>

<template>
  <aside class="app-sidebar legacy-sidebar">
    <div class="legacy-logo">
      <span class="legacy-logo-diamond">◆</span>
      <strong class="brand-name">TGT AI Native</strong>
    </div>

    <button class="legacy-user-switch" type="button" @click="openUserProfile">
      <span class="legacy-avatar">{{ displayAvatar }}</span>
      <span class="legacy-user-info">
        <strong>{{ displayName }}</strong>
        <small>{{ displayRole }}</small>
      </span>
    </button>

    <template v-if="legacyUi.currentRole === 'sales'">
      <div class="nav-group">
        <div class="nav-group-title">总览</div>
        <RouterLink class="nav-item" :class="{ active: isActive('/dashboard') }" to="/dashboard">
          <span>我的业绩</span>
        </RouterLink>
      </div>

      <div class="legacy-nav-tabs">
        <button :class="{ active: legacyUi.salesNavTab === 'ai-staff' }" @click="legacyUi.salesNavTab = 'ai-staff'">AI agent</button>
        <button :class="{ active: legacyUi.salesNavTab === 'projects' }" @click="legacyUi.salesNavTab = 'projects'">更多功能</button>
      </div>

      <div class="nav-group">
        <RouterLink v-for="item in salesVisibleItems" :key="item.path" class="nav-item" :class="{ active: isActive(item.path) }" :to="item.path">
          <span>{{ item.label }}</span>
        </RouterLink>
        <div v-if="legacyUi.salesNavTab === 'projects'" class="legacy-empty-nav">更多功能开发中，敬请期待</div>
      </div>
    </template>

    <template v-else>
      <div class="nav-group">
        <div class="nav-group-title">总览</div>
        <RouterLink class="nav-item" :class="{ active: isActive('/boss-dashboard') }" to="/boss-dashboard">
          <span>经营驾驶舱</span>
        </RouterLink>
      </div>
      <div class="nav-group">
        <div class="nav-group-title boss-title">AI Agent</div>
        <RouterLink v-for="item in bossItems" :key="item.path" class="nav-item" :class="{ active: isActive(item.path) }" :to="item.path">
          <span>{{ item.label }}</span>
        </RouterLink>
      </div>
    </template>

    <div ref="settingsEl" class="legacy-sidebar-footer">
      <button class="legacy-gear" type="button" @click.stop="legacyUi.settingsOpen = !legacyUi.settingsOpen">设置</button>
      <div v-if="legacyUi.settingsOpen" class="legacy-gear-menu">
        <div class="legacy-gear-title">当前账号</div>
        <div class="legacy-account-line">{{ displayName }} · {{ displayRole }}</div>
        <button type="button" @click="logout">退出登录</button>
      </div>
    </div>
  </aside>
</template>
