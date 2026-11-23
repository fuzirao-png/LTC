<script setup lang="ts">
import { onMounted, onUnmounted, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import MainLayout from '../../app/layouts/AppLayout.vue';
import { prefetchLanding } from '../../app/router';
import { useAuthStore } from '../../stores/auth';
import { useLegacyUiStore } from '../../stores/legacyUi';
import LoginView from '../../features/auth/LoginView.vue';

const auth = useAuthStore();
const legacyUi = useLegacyUiStore();
const route = useRoute();
const router = useRouter();

const defaultPathForCurrentUser = () => (auth.isSales ? '/dashboard' : '/boss-dashboard');
const salesPaths = new Set(['/welcome', '/dashboard', '/customer-allocation', '/customer-analysis', '/customer-operation', '/meeting-analysis', '/db-cases', '/db-scripts']);
const bossPaths = new Set(['/welcome', '/boss-dashboard', '/lead-collection', '/lead-analysis', '/email-automation', '/boss-lead-assign', '/boss-sales-mgmt']);

const routeAllowedForCurrentUser = () => {
  if (!auth.currentUser) return true;
  if (auth.isSales) return salesPaths.has(route.path);
  return bossPaths.has(route.path);
};

const ensureRoleRoute = async () => {
  if (!auth.currentUser) return;
  await router.isReady();
  const user = auth.currentUser;
  if (!user) return;
  if (route.path === '/' || route.path === '/login' || !routeAllowedForCurrentUser()) {
    const path = route.path === '/login' && !auth.isSales ? '/lead-collection' : defaultPathForCurrentUser();
    prefetchLanding(path, user.userId, auth.isSales);
    await router.replace(path);
  } else {
    prefetchLanding(route.path, user.userId, auth.isSales);
  }
};

const handleSessionExpired = () => auth.expireSession();

onMounted(() => {
  window.addEventListener('ltc:auth-expired', handleSessionExpired);
  if (!auth.profileLoaded && !auth.loading) {
    void auth.loadProfile();
  }
});

onUnmounted(() => {
  window.removeEventListener('ltc:auth-expired', handleSessionExpired);
});

watch(
  () => auth.currentUser,
  async (user) => {
    legacyUi.applyUser(user);
    if (user) await ensureRoleRoute();
  },
  { immediate: true },
);

watch(
  () => route.path,
  () => {
    void ensureRoleRoute();
  },
);
</script>

<template>
  <div v-if="!auth.profileLoaded" class="auth-loading-screen">
    <div class="auth-card">
      <div class="legacy-logo-icon">L</div>
      <strong>正在确认登录状态...</strong>
    </div>
  </div>

  <LoginView v-else-if="!auth.isAuthenticated" />

  <MainLayout v-else />
</template>
