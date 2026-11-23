<script setup lang="ts">
export interface TableColumn {
  key: string;
  label: string;
  width?: string;
}

defineProps<{
  columns: TableColumn[];
  rows: Array<Record<string, any>>;
  emptyText?: string;
}>();
</script>

<template>
  <div class="table-wrap">
    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column.key" :style="{ width: column.width }">
            {{ column.label }}
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-if="rows.length === 0">
          <td :colspan="columns.length" class="empty-cell">{{ emptyText || '暂无数据' }}</td>
        </tr>
        <tr v-for="(row, index) in rows" :key="String(row.id || row.lead_id || row.company_id || index)">
          <td v-for="column in columns" :key="column.key">
            <slot :name="`cell-${column.key}`" :row="row" :value="row[column.key]">
              {{ row[column.key] || '-' }}
            </slot>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
