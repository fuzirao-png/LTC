import { defineStore } from 'pinia';

import { allocationApi, type LeadPoolItem } from '../services/allocationApi';
import { getApiErrorMessage } from '../services/http';
import { loadSalesLanding } from '../services/landingQueries';
import { useAuthStore } from './auth';

export const useAllocationStore = defineStore('allocation', {
  state: () => ({
    claimable: [] as LeadPoolItem[],
    mine: [] as LeadPoolItem[],
    all: [] as LeadPoolItem[],
    loading: false,
    error: '',
    salesPoolRequestId: 0,
  }),
  getters: {
    claimedCount: (state) => state.mine.length,
    claimableCount: (state) => state.claimable.length,
  },
  actions: {
    async loadSalesPool(refresh = false) {
      this.loading = true;
      this.error = '';
      const auth = useAuthStore();
      const userId = auth.currentUser?.userId || '';
      const requestId = ++this.salesPoolRequestId;
      const isCurrent = () => this.salesPoolRequestId === requestId && (auth.currentUser?.userId || '') === userId;
      try {
        const [claimable, mine] = await loadSalesLanding(userId, refresh);
        if (!isCurrent()) return;
        this.claimable = claimable.items || [];
        this.mine = mine.items || [];
      } catch (error) {
        if (!isCurrent()) return;
        this.claimable = [];
        this.mine = [];
        this.error = getApiErrorMessage(error, '销售线索池加载失败');
      } finally {
        if (isCurrent()) this.loading = false;
      }
    },
    async loadAll() {
      this.loading = true;
      this.error = '';
      try {
        this.all = (await allocationApi.all()).items || [];
      } catch (error) {
        this.all = [];
        this.error = getApiErrorMessage(error, '客户分配列表加载失败');
      } finally {
        this.loading = false;
      }
    },
    async claim(leadId: string, version: number) {
      this.loading = true;
      this.error = '';
      try {
        await allocationApi.claim(leadId, version);
        await this.loadSalesPool(true);
      } catch (error) {
        this.error = getApiErrorMessage(error, '领取失败');
        throw error;
      } finally {
        this.loading = false;
      }
    },
  },
});
