import { defineStore } from 'pinia'
import { api, toApiError } from '../../shared/api/client'
import type { ApiError } from '../../shared/api/errors'

type RuntimeState = 'idle' | 'loading' | 'ready' | 'error'
type Me = { display_name?: string; account_type?: 'sales' | 'strategic' }

export const useRuntimeStore = defineStore('runtime', {
  state: () => ({ state: 'idle' as RuntimeState, me: null as Me | null, error: null as ApiError | null }),
  actions: {
    async refresh() {
      this.state = 'loading'
      this.error = null
      try {
        // Verify API connectivity via health endpoint (no auth required for demo)
        const { data } = await api.get('/health')
        this.me = { display_name: data?.data?.status === 'ok' ? 'Demo 用户' : '未知', account_type: 'sales' }
        this.state = 'ready'
      } catch (error) {
        // Fallback: treat as ready for local demo (backend may be starting)
        this.me = { display_name: '离线模式', account_type: 'sales' }
        this.state = 'ready'
      }
    },
  },
})
