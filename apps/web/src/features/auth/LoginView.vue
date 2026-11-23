<script setup lang="ts">
import { nextTick, ref } from 'vue';
import { useRouter } from 'vue-router';

import paBirdUrl from '../../assets/pa-bird.webp';
import { prefetchLanding } from '../../app/router';
import { useAuthStore } from '../../stores/auth';
import { useLegacyUiStore } from '../../stores/legacyUi';

const auth = useAuthStore();
const legacyUi = useLegacyUiStore();
const router = useRouter();

const username = ref('alex');
const password = ref('');
const errorMsg = ref('');
const showError = ref(false);
const showHint = ref(false);
const passwordInput = ref<HTMLInputElement | null>(null);

const hostName = 'alex';

const submit = async () => {
  showError.value = false;
  showHint.value = false;
  try {
    await auth.login(username.value || hostName, password.value);
    legacyUi.applyUser(auth.currentUser);
    const path = auth.isSales ? '/dashboard' : '/lead-collection';
    if (auth.currentUser) prefetchLanding(path, auth.currentUser.userId, auth.isSales);
    await router.replace(path);
  } catch {
    errorMsg.value = '密码输入错误';
    showError.value = true;
    showHint.value = false;
    await nextTick();
    passwordInput.value?.focus();
  }
};
</script>

<template>
  <main class="login-screen">
    <img class="login-background" src="/login-bg.webp" alt="" fetchpriority="high" />
    <form class="login-card" @submit.prevent="submit">
      <div class="logo-fallback">
        <img :src="paBirdUrl" alt="途鸽" width="72" height="72" />
      </div>
      <div class="product-name">TGT AI Native</div>
      <div class="product-sub">智能销售协同平台</div>

      <label class="login-label" for="login-username">账号</label>
      <input
        id="login-username"
        v-model="username"
        type="text"
        class="login-input"
        placeholder="账号"
        autocomplete="username"
        @keydown.enter.prevent="submit"
      />
      <label class="login-label" for="login-password">密码</label>
      <input
        id="login-password"
        ref="passwordInput"
        v-model="password"
        type="password"
        class="login-input"
        placeholder="请输入密码"
        autocomplete="current-password"
        :aria-invalid="showError"
        :aria-describedby="showError ? 'login-error' : undefined"
        @keydown.enter.prevent="submit"
      />
      <button class="login-btn" type="submit" :disabled="auth.loading">
        {{ auth.loading ? '登录中...' : '登 录' }}
      </button>

      <div v-if="showError" id="login-error" class="login-error-msg" role="alert">{{ errorMsg }}</div>
      <div v-if="showHint" class="login-hint-text">提示：默认密码 123456</div>
    </form>
  </main>
</template>

<style scoped>
.login-screen {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #182441;
}

.login-background {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.login-card {
  position: relative;
  background: rgba(255,255,255,0.15);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(255,255,255,0.25);
  border-radius: 16px;
  padding: 40px 48px;
  max-width: 380px;
  width: 90%;
  box-shadow: 0 20px 60px rgba(0,0,0,0.3);
  text-align: center;
  animation: slideUp 0.4s ease;
}

@keyframes slideUp {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}

.logo-fallback {
  width: 72px; height: 72px;
  margin: 0 auto 16px;
  border-radius: 12px;
  background: linear-gradient(135deg, #2563EB, #1D4ED8);
  overflow: hidden;
  display: flex; align-items: center; justify-content: center;
}

.logo-fallback img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.product-name {
  font-size: 20px; font-weight: 700;
  color: #fff; margin-bottom: 4px;
}

.product-sub {
  font-size: 13px;
  color: rgba(255,255,255,0.7);
  margin-bottom: 28px;
}

.login-label {
  display: block;
  margin: 0 0 6px;
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  text-align: left;
}

.login-input {
  width: 100%;
  padding: 12px 16px;
  font-size: 14px;
  border: 1px solid rgba(255,255,255,0.3);
  border-radius: 8px;
  outline: none;
  box-sizing: border-box;
  margin-bottom: 12px;
  transition: border-color 0.2s;
  background: rgba(255,255,255,0.1);
  color: #fff;
}

.login-input::placeholder {
  color: rgba(255,255,255,0.5);
}

.login-input:focus {
  border-color: rgba(255,255,255,0.6);
  box-shadow: 0 0 0 3px rgba(255,255,255,0.1);
}

.login-btn {
  width: 100%;
  padding: 12px;
  font-size: 14px; font-weight: 600;
  color: #fff;
  background: linear-gradient(135deg, #2563EB, #1D4ED8);
  border: none;
  border-radius: 8px;
  cursor: pointer;
  transition: opacity 0.2s;
}

.login-btn:hover:not(:disabled) { opacity: 0.9; }
.login-btn:active:not(:disabled) { opacity: 0.8; }
.login-btn:disabled { opacity: 0.6; cursor: not-allowed; }

.login-error-msg {
  display: block;
  margin-top: 10px;
  font-size: 12px;
  color: #60A5FA;
}

.login-hint-text {
  margin-top: 20px;
  font-size: 11px;
  color: rgba(255,255,255,0.5);
}
</style>
