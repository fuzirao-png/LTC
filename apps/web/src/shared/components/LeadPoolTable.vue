<script setup lang="ts">
import type { LeadPoolItem } from '../../services/allocationApi';
import DataTable, { type TableColumn } from './DataTable.vue';
import StatusBadge from './StatusBadge.vue';

defineProps<{
  rows: LeadPoolItem[];
  loading?: boolean;
}>();

const emit = defineEmits<{
  claim: [lead: LeadPoolItem];
}>();

const claimRow = (row: Record<string, any>) => {
  emit('claim', row as LeadPoolItem);
};

const columns: TableColumn[] = [
  { key: 'name', label: '客户', width: '26%' },
  { key: 'sales_tier', label: '销售等级', width: '96px' },
  { key: 'region', label: '区域', width: '100px' },
  { key: 'score', label: '分数', width: '80px' },
  { key: 'pool_status', label: '状态', width: '92px' },
  { key: 'owner_name', label: '领取人', width: '120px' },
  { key: 'actions', label: '操作', width: '120px' },
];
</script>

<template>
  <DataTable :columns="columns" :rows="rows" :empty-text="loading ? '加载中...' : '暂无线索'">
    <template #cell-name="{ row }">
      <div class="lead-name">{{ row.name }}</div>
      <div class="lead-sub">{{ row.industry || row.website || '-' }}</div>
    </template>
    <template #cell-pool_status="{ row }">
      <StatusBadge :status="row.pool_status" />
    </template>
    <template #cell-owner_name="{ row }">
      {{ row.owner_name || row.owner_username || '-' }}
    </template>
    <template #cell-actions="{ row }">
      <button class="btn btn-primary btn-small claim-button" :disabled="row.pool_status !== 'claimable'" @click="claimRow(row)">
        领取
      </button>
    </template>
  </DataTable>
</template>
