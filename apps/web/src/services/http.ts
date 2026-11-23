import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios';

type RetryableRequestConfig = InternalAxiosRequestConfig & { _ltcRetry?: boolean };

let refreshPromise: Promise<void> | null = null;
const HTTP_TIMEOUT_MS = 60_000;

const refreshSession = (baseURL: string) => {
  if (!refreshPromise) {
    refreshPromise = axios
      .post(`${baseURL.replace(/\/$/, '')}/auth/refresh`, undefined, {
        withCredentials: true,
        timeout: HTTP_TIMEOUT_MS,
      })
      .then(() => undefined)
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
};

const notifySessionExpired = () => {
  if (typeof window !== 'undefined') window.dispatchEvent(new Event('ltc:auth-expired'));
};

export const createHttpClient = (baseURL: string) => {
  const client = axios.create({
    baseURL,
    withCredentials: true,
    timeout: HTTP_TIMEOUT_MS,
  });

  client.interceptors.response.use(
    (response) => response,
    async (error: AxiosError) => {
      const request = error.config as RetryableRequestConfig | undefined;
      const requestUrl = String(request?.url || '');
      const isAuthRequest = requestUrl.includes('/auth/login') || requestUrl.includes('/auth/refresh');
      if (error.response?.status !== 401 || !request || request._ltcRetry || isAuthRequest) {
        return Promise.reject(error);
      }

      request._ltcRetry = true;
      try {
        await refreshSession(baseURL);
        return client.request(request);
      } catch {
        notifySessionExpired();
        return Promise.reject(error);
      }
    },
  );

  return client;
};

export function getApiErrorMessage(error: unknown, fallback = '请求失败') {
  if (axios.isAxiosError(error)) {
    const payload = error.response?.data as {
      detail?: string | { message?: string } | Array<{ msg?: string }>;
      reason?: string;
      error?: string;
    } | undefined;

    if (typeof payload?.detail === 'string') return payload.detail;
    if (Array.isArray(payload?.detail)) {
      const message = payload.detail.map((item) => item.msg).filter(Boolean).join('；');
      if (message) return message;
    }
    if (payload?.detail && typeof payload.detail === 'object' && 'message' in payload.detail) {
      if (payload.detail.message) return payload.detail.message;
    }
    return payload?.reason || payload?.error || error.message || fallback;
  }
  if (error instanceof Error) return error.message;
  return fallback;
}

export function isTransientApiError(error: unknown) {
  if (!axios.isAxiosError(error)) return false;
  const status = Number(error.response?.status || 0);
  return !status || status === 408 || status === 429 || status >= 500;
}
