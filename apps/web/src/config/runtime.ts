export interface RuntimeConfig {
  leadApiBase: string;
  allocationApiBase: string;
  operationApiBase: string;
  meetingApiBase: string;
  analysisApiBase: string;
  leadEnvPath: string;
  searchProvider: string;
}

type WindowWithRuntime = Window & {
  LTC_RUNTIME_CONFIG?: Partial<RuntimeConfig>;
};

const runtimeWindow = window as WindowWithRuntime;
const runtimeConfig = runtimeWindow.LTC_RUNTIME_CONFIG || {};
const params = new URLSearchParams(window.location.search);

function normalizeApiBase(value?: string | null) {
  const text = String(value || '').trim();
  return text.replace(/\/+$/, '');
}

function resolveBase(options: {
  runtimeKey: keyof RuntimeConfig;
  queryKey: string;
  storageKey: string;
  fallback: string;
}) {
  return (
    normalizeApiBase(params.get(options.queryKey)) ||
    normalizeApiBase(window.localStorage.getItem(options.storageKey)) ||
    normalizeApiBase(runtimeConfig[options.runtimeKey]) ||
    options.fallback
  );
}

export const config: RuntimeConfig = {
  leadApiBase: resolveBase({
    runtimeKey: 'leadApiBase',
    queryKey: 'leadApiBase',
    storageKey: 'LEAD_AGENT_BASE',
    fallback: '/api/v1',
  }),
  allocationApiBase: resolveBase({
    runtimeKey: 'allocationApiBase',
    queryKey: 'allocationApiBase',
    storageKey: 'CUSTOMER_ALLOCATION_API_BASE',
    fallback: '/api/v1',
  }),
  operationApiBase: resolveBase({
    runtimeKey: 'operationApiBase',
    queryKey: 'operationApiBase',
    storageKey: 'CUSTOMER_OPERATION_API_BASE',
    fallback: '/api/v1',
  }),
  meetingApiBase: resolveBase({
    runtimeKey: 'meetingApiBase',
    queryKey: 'meetingApiBase',
    storageKey: 'MEETING_ANALYSIS_API_BASE',
    fallback: '/api/v1',
  }),
  analysisApiBase: resolveBase({
    runtimeKey: 'analysisApiBase',
    queryKey: 'analysisApiBase',
    storageKey: 'ANALYSIS_AGENT_BASE',
    fallback: '',
  }),
  leadEnvPath: normalizeApiBase(window.localStorage.getItem('LEAD_AGENT_ENV_PATH')) || '.env',
  searchProvider: normalizeApiBase(window.localStorage.getItem('LEAD_SEARCH_PROVIDER')) || 'exa',
};
