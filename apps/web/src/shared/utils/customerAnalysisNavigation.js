export function customerAnalysisRoute(companyId, options = {}) {
  const normalizedCompanyId = String(companyId || '').trim();
  if (!normalizedCompanyId) return { name: 'customerAnalysis' };
  const query = { companyId: normalizedCompanyId };
  const runId = String(options.runId || '').trim();
  if (runId) query.runId = runId;
  return {
    name: 'customerAnalysis',
    query,
  };
}

export function customerIdFromAnalysisQuery(value) {
  const candidate = Array.isArray(value) ? value[0] : value;
  return String(candidate || '').trim();
}

export function findAnalysisCustomer(customers, companyId) {
  const normalizedCompanyId = String(companyId || '').trim();
  if (!normalizedCompanyId) return null;
  return customers.find((customer) => (
    String(customer?.client_id || customer?.customerId || '').trim() === normalizedCompanyId
  )) || null;
}
