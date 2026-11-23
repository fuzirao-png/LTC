import { defineStore } from 'pinia';

import { allocationApi } from '../services/allocationApi';
import { getApiErrorMessage } from '../services/http';
import { clearLandingQueries } from '../services/landingQueries';

// ---- v3.6 IAM-aligned types ----

/** Matches backend account_type */
export type AccountType = 'sales' | 'strategic';

/** Matches backend sales_tier enum */
export type SalesTier = 'MA' | 'SA' | 'A';

/** Matches backend region_code enum */
export type RegionCode = 'NA' | 'EA' | 'SEA' | 'EU' | 'ME' | 'OTHER';

/** Matches backend UserResponse schema */
export interface CurrentUser {
  userId: string;          // backend: user_id
  username: string;        // backend: username
  name: string;            // backend: display_name
  accountType: AccountType; // backend: account_type ('sales' | 'strategic')
  salesTier: SalesTier | null;   // backend: sales_tier
  regionCode: RegionCode | null; // backend: region_code
  capacityLimit: number | null;  // backend: capacity_limit
  activeAssignmentCount: number; // backend: active_assignment_count
  status: string;          // backend: status ('active' | 'disabled' | 'departed')
  capabilities: string[];  // backend: capabilities from auth envelope
  version?: number;        // backend: version (from user list, not auth/me)
}

// ---- DEV demo support (only when no real backend) ----

const demoUserStorageKey = 'ltc-demo-current-user';
const currentUserStorageKey = 'ltc.current-user-id';

function saveCurrentUserIdentity(user: CurrentUser | null) {
  if (typeof window === 'undefined') return;
  if (user?.userId) window.sessionStorage.setItem(currentUserStorageKey, user.userId);
  else window.sessionStorage.removeItem(currentUserStorageKey);
}

function demoUserFromUsername(username: string): CurrentUser {
  const normalized = username.trim() || 'ma.na';
  const lower = normalized.toLowerCase();
  const isStrategic = ['alex', 'boss', 'admin', 'strategy', 'strategy.ops'].includes(lower);

  if (isStrategic) {
    return {
      userId: normalized,
      username: normalized,
      name: lower === 'alex' ? 'Alex' : normalized,
      accountType: 'strategic',
      salesTier: null,
      regionCode: null,
      capacityLimit: null,
      activeAssignmentCount: 0,
      status: 'active',
      capabilities: ['iam:list_users', 'iam:manage_users', 'sales:view_all', 'sales:assign'],
    };
  }

  return {
    userId: normalized,
    username: normalized,
    name: normalized,
    accountType: 'sales',
    salesTier: lower.startsWith('ma.') ? 'MA' : lower.startsWith('sa.') ? 'SA' : 'A',
    regionCode: lower.includes('.na') ? 'NA' : lower.includes('.east') ? 'EA' : lower.includes('.eu') ? 'EU' : 'EA',
    capacityLimit: 10,
    activeAssignmentCount: 0,
    status: 'active',
    capabilities: ['sales:view_own', 'sales:claim'],
  };
}

// ---- Store ----

export const useAuthStore = defineStore('auth', {
  state: () => ({
    currentUser: null as CurrentUser | null,
    loading: false,
    profileLoaded: false,
    error: '',
  }),

  getters: {
    isAuthenticated: (state) => Boolean(state.currentUser),
    isSales: (state) => state.currentUser?.accountType === 'sales',
    isStrategic: (state) => state.currentUser?.accountType === 'strategic',
    /** @deprecated kept for backward compat — use isStrategic instead */
    isManager: (state) => state.currentUser?.accountType === 'strategic',
    displayName: (state) => state.currentUser?.name || state.currentUser?.username || '未登录',
  },

  actions: {
    /** Normalize backend UserResponse into CurrentUser */
    normalizeUser(raw: any): CurrentUser {
      return {
        userId: raw.user_id || raw.userId || raw.sub || '',
        username: raw.username || '',
        name: raw.display_name || raw.name || raw.username || '',
        accountType: (raw.account_type === 'strategic' ? 'strategic' : 'sales') as AccountType,
        salesTier: raw.sales_tier || raw.salesTier || null,
        regionCode: raw.region_code || raw.regionCode || null,
        capacityLimit: raw.capacity_limit ?? raw.capacityLimit ?? null,
        activeAssignmentCount: Number(raw.active_assignment_count ?? raw.activeAssignmentCount ?? 0),
        status: raw.status || 'active',
        capabilities: raw.capabilities || [],
        version: raw.version,
      };
    },

    setUser(raw: any) {
      this.currentUser = this.normalizeUser(raw);
      saveCurrentUserIdentity(this.currentUser);
    },

    expireSession() {
      clearLandingQueries();
      saveCurrentUserIdentity(null);
      this.currentUser = null;
      this.profileLoaded = true;
      this.loading = false;
      this.error = '登录状态已过期，请重新登录。';
    },

    async loadProfile() {
      this.loading = true;
      this.error = '';
      try {
        // Real IAM: GET /api/v1/auth/me → envelope { data: { user, capabilities } }
        const envelope = await allocationApi.me();
        const authData = (envelope as any).data || envelope;
        const user = authData.user || authData;
        const currentUser = this.normalizeUser(user);
        currentUser.capabilities = authData.capabilities || [];
        this.currentUser = currentUser;
        saveCurrentUserIdentity(currentUser);
      } catch {
        saveCurrentUserIdentity(null);
        this.currentUser = null;
        this.error = '';
      } finally {
        this.profileLoaded = true;
        this.loading = false;
      }
    },

    async login(username: string, password: string) {
      clearLandingQueries();
      this.loading = true;
      this.error = '';
      try {
        const envelope = await allocationApi.login({ username, password });

        // Real IAM: parse response envelope
        const authData = (envelope as any).data || envelope;
        const user = authData.user || authData;
        const currentUser = this.normalizeUser(user);
        currentUser.capabilities = authData.capabilities || [];
        this.currentUser = currentUser;
        saveCurrentUserIdentity(currentUser);
        this.profileLoaded = true;
      } catch (error) {
        saveCurrentUserIdentity(null);
        this.currentUser = null;
        this.error = getApiErrorMessage(error, '登录失败');
        throw error;
      } finally {
        this.loading = false;
      }
    },

    async logout() {
      try {
        await allocationApi.logout();
      } finally {
        clearLandingQueries();
        saveCurrentUserIdentity(null);
        this.currentUser = null;
        this.profileLoaded = true;
      }
    },
  },
});
