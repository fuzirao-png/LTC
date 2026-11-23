import { allocationApi } from './allocationApi';
import { leadApi } from './leadApi';
import { createPrefetchedPage } from './prefetchedPage';

const fetchSalesPool = (refresh: boolean) => Promise.all([
  allocationApi.claimable(refresh), allocationApi.mine(refresh),
]);
const salesPool = createPrefetchedPage<Awaited<ReturnType<typeof fetchSalesPool>>>();
const candidates = createPrefetchedPage<Awaited<ReturnType<typeof leadApi.listValidationCompanies>>>();

export function loadSalesLanding(userId: string, refresh = false) {
  if (refresh) {
    salesPool.clear();
    return fetchSalesPool(true);
  }
  return salesPool.load([userId, 'sales-pool', 100], () => fetchSalesPool(false));
}

export function loadCandidateLanding(userId: string, size = 100, refresh = false) {
  const params = { page: 1, size, sort: 'last_updated', order: 'desc' };
  if (refresh) {
    candidates.clear();
    return leadApi.listValidationCompanies(params, true);
  }
  return candidates.load([userId, 'lead-candidates', params], () => leadApi.listValidationCompanies(params));
}

export function clearLandingQueries() {
  salesPool.clear();
  candidates.clear();
}
