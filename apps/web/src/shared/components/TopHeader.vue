<script setup lang="ts">
defineProps<{
  breadcrumb: string;
  title: string;
}>();
</script>

<template>
  <header class="top-header legacy-top-header">
    <div class="breadcrumb">{{ breadcrumb }} / <span>{{ title }}</span></div>
    <div class="header-actions" />
  </header>
</template>

<style scoped>
.top-header {
  position: relative;
  flex: 0 0 48px;
  height: 48px;
  background: var(--bg-card);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  padding: 0 20px;
  z-index: 1;
}

.breadcrumb {
  font-size: 12px;
  color: var(--text-muted);
}

.breadcrumb span {
  color: var(--text-primary);
  font-weight: 600;
}

.header-actions {
  margin-left: auto;
}
</style>
