export interface AnalysisCustomerIdentity {
  client_id?: string;
  customerId?: string;
}

export interface CustomerAnalysisRouteLocation {
  name: 'customerAnalysis';
  query?: { companyId: string; runId?: string };
}

export interface CustomerAnalysisRouteOptions {
  runId?: unknown;
}

export function customerAnalysisRoute(companyId: unknown, options?: CustomerAnalysisRouteOptions): CustomerAnalysisRouteLocation;
export function customerIdFromAnalysisQuery(value: unknown): string;
export function findAnalysisCustomer<T extends AnalysisCustomerIdentity>(customers: T[], companyId: unknown): T | null;
