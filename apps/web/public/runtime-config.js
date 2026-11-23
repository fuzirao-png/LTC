window.LTC_RUNTIME_CONFIG = Object.assign(
  {
    leadApiBase: '/api/v1',
    allocationApiBase: '/api/v1',
    operationApiBase: '/api/v1',
    meetingApiBase: '/api/v1',
    analysisApiBase: '',
    leadEnvPath: '.env',
    searchProvider: 'exa',
  },
  window.LTC_RUNTIME_CONFIG || window.__LTC_CONFIG__ || {}
);
