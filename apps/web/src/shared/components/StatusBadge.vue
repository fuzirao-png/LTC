<script setup lang="ts">
import { poolStatusLabel } from '../utils/labels';

const props = defineProps<{
  status?: string | null;
}>();

const statusMap: Record<string, string> = {
  claimable: '未领取',
  claimed: '已领取',
  selected: '已选择',
  pending: '待处理',
  assigned: '已分配',
  emailed: '已触达',
  replied: '已回复',
  meeting: '已开会',
};
</script>

<template>
  <span :class="['status-badge', `status-${props.status || 'default'}`]">
    {{ statusMap[props.status || ''] || poolStatusLabel(props.status) || props.status || '未知' }}
  </span>
</template>
