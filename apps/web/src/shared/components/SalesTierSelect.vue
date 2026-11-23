<script setup lang="ts">
import { salesTierLabel } from '../utils/labels';
const model = defineModel<string>({ default: '' });
const tiers = ['MA', 'SA', 'A'];
</script>

<template>
  <select v-model="model" class="field-control">
    <option value="">全部等级</option>
    <option v-for="tier in tiers" :key="tier" :value="tier">{{ salesTierLabel(tier) }}</option>
  </select>
</template>
