export interface FilterableAnalysisRow {
  sourceKey: string;
  scenario: string;
  score: number;
  sizeKey: string;
  regionKey: string;
}

export interface AnalysisFilters {
  source: string;
  industry: string;
  score: string;
  size: string;
  region: string;
}

export function matchesScoreBucket(score: number, bucket: string): boolean;
export function matchesCustomerSize(sizeGrade: string, size: string): boolean;
export function filterAnalysisRows<T extends FilterableAnalysisRow>(rows: T[], filters: AnalysisFilters): T[];
