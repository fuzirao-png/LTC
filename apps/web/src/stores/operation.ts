import { defineStore } from 'pinia';

import { getApiErrorMessage } from '../services/http';
import { allocationApi } from '../services/allocationApi';
import {
  operationApi,
  type OperationCustomer,
  type OperationDetail,
  type OperationEmail,
  type OperationMeeting,
} from '../services/operationApi';

export const useOperationStore = defineStore('operation', {
  state: () => ({
    customers: [] as OperationCustomer[],
    selectedCustomer: null as OperationCustomer | null,
    selectedDetail: null as OperationDetail | null,
    emailHistory: [] as OperationEmail[],
    meetingHistory: [] as OperationMeeting[],
    loading: false,
    detailLoading: false,
    error: '',
    detailError: '',
  }),
  actions: {
    async loadCustomers() {
      this.loading = true;
      this.error = '';
      try {
        const exported = (await operationApi.exportCustomers()).items || [];
        if (exported.length) {
          this.customers = exported;
        } else {
          // A claimed lead is still a valid customer even if the operation
          // export is temporarily empty or unavailable.
          const mine = (await allocationApi.mine()).items || [];
          this.customers = mine
            .filter((lead) => lead.company_id && lead.name)
            .map((lead) => ({
              company_id: lead.company_id,
              companyId: lead.company_id,
              customerName: lead.name,
              companyName: lead.name,
              ownerName: lead.owner_name || lead.owner_username || undefined,
              payload: {
                industry: lead.industry,
                website: lead.website,
                city: lead.city,
                country: lead.country,
                region: lead.region,
                sales_tier: lead.sales_tier,
              },
            }));
        }
      } catch (error) {
        try {
          const mine = (await allocationApi.mine()).items || [];
          this.customers = mine
            .filter((lead) => lead.company_id && lead.name)
            .map((lead) => ({
              company_id: lead.company_id,
              companyId: lead.company_id,
              customerName: lead.name,
              companyName: lead.name,
              ownerName: lead.owner_name || lead.owner_username || undefined,
              payload: { industry: lead.industry, city: lead.city, country: lead.country, region: lead.region },
            }));
        } catch {
          this.customers = [];
        }
        this.error = getApiErrorMessage(error, '客户运营列表加载失败');
      } finally {
        this.loading = false;
      }
    },
    async selectCustomer(customer: OperationCustomer) {
      this.selectedCustomer = customer;
      this.selectedDetail = null;
      this.emailHistory = [];
      this.meetingHistory = [];
      this.detailLoading = true;
      this.detailError = '';
      const companyId = customer.company_id;
      const customerName = customer.customerName;
      try {
        const [detailResult, emails, meetings] = await Promise.allSettled([
          companyId ? operationApi.getCustomerOperations(companyId) : Promise.resolve(null),
          operationApi.getEmailHistory(customerName),
          companyId ? operationApi.getMeetingHistory(companyId) : Promise.resolve([]),
        ]);

        if (detailResult.status === 'fulfilled') this.selectedDetail = detailResult.value;
        if (emails.status === 'fulfilled') this.emailHistory = emails.value;
        if (meetings.status === 'fulfilled') this.meetingHistory = meetings.value;

        const rejected = [detailResult, emails, meetings].find((item) => item.status === 'rejected');
        if (rejected && detailResult.status === 'rejected') {
          this.detailError = getApiErrorMessage(rejected.reason, '客户详情加载失败');
        }
      } catch (error) {
        this.detailError = getApiErrorMessage(error, '客户详情加载失败');
      } finally {
        this.detailLoading = false;
      }
    },
    closeDetail() {
      this.selectedCustomer = null;
      this.selectedDetail = null;
      this.emailHistory = [];
      this.meetingHistory = [];
      this.detailError = '';
    },
  },
});
