import axios, { type AxiosError } from 'axios'
import type { ApiError } from './errors'

export const api = axios.create({ baseURL: '/api/v1', timeout: 10_000, withCredentials: true })

api.interceptors.request.use((config) => {
  const token = sessionStorage.getItem('ltc.access_token') || sessionStorage.getItem('ltc_access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

export function toApiError(error: unknown): ApiError {
  if (axios.isAxiosError(error)) {
    const response = error as AxiosError<{ error?: { code?: string; message?: string; details?: Record<string, unknown> } }>
    return { code: response.response?.data?.error?.code ?? 'NETWORK_ERROR', message: response.response?.data?.error?.message ?? response.message, details: response.response?.data?.error?.details }
  }
  return { code: 'UNKNOWN_ERROR', message: '发生未知错误' }
}
