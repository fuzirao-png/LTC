export function matchesScoreBucket(score, bucket) {
  if (bucket === '90_plus') return score >= 90;
  if (bucket === '80_89') return score >= 80 && score < 90;
  if (bucket === '70_79') return score >= 70 && score < 80;
  if (bucket === '60_69') return score >= 60 && score < 70;
  if (bucket === 'under_60') return score < 60;
  return true;
}

export function matchesCustomerSize(sizeGrade, size) {
  return size === 'all' || sizeGrade === size;
}

export function filterAnalysisRows(rows, filters) {
  return rows.filter((row) => (
    (filters.source === 'all' || row.sourceKey === filters.source)
    && (filters.industry === 'all' || row.scenario === filters.industry)
    && matchesScoreBucket(row.score, filters.score)
    && matchesCustomerSize(row.sizeKey, filters.size)
    && (filters.region === 'all' || row.regionKey === filters.region)
  ));
}
