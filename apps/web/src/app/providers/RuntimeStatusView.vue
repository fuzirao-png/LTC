<script setup lang="ts">
import { onMounted } from 'vue'
import { useRuntimeStore } from './runtime'
import { accountTypeLabel } from '../../shared/utils/labels'

const runtime = useRuntimeStore()
onMounted(() => void runtime.refresh())
</script>

<template>
  <section aria-live="polite">
    <template v-if="runtime.state === 'loading'">正在验证当前会话…</template>
    <template v-else-if="runtime.state === 'ready'"><strong>服务已连接</strong><p>{{ runtime.me?.display_name ?? '当前用户' }} · {{ accountTypeLabel(runtime.me?.account_type) }}</p></template>
    <template v-else-if="runtime.state === 'error'"><strong>暂未连接</strong><p>{{ runtime.error?.code }}：{{ runtime.error?.message }}</p><button type="button" @click="runtime.refresh">重试</button></template>
    <template v-else>等待连接。</template>
  </section>
  <p class="hint">客户端仅通过同源 <code>/api/v1</code> 访问 v3.6 后端。</p>
</template>
