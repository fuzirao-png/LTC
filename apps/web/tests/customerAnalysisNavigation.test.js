import assert from 'node:assert/strict';
import test from 'node:test';

import {
  customerAnalysisRoute,
  customerIdFromAnalysisQuery,
  findAnalysisCustomer,
} from '../src/shared/utils/customerAnalysisNavigation.js';

test('builds a customer analysis deep link', () => {
  assert.deepEqual(customerAnalysisRoute(' company-123 '), {
    name: 'customerAnalysis',
    query: { companyId: 'company-123' },
  });
  assert.deepEqual(customerAnalysisRoute('company-123', { runId: 'run-456' }), {
    name: 'customerAnalysis',
    query: { companyId: 'company-123', runId: 'run-456' },
  });
  assert.deepEqual(customerAnalysisRoute(''), { name: 'customerAnalysis' });
});

test('reads the company id from a route query value', () => {
  assert.equal(customerIdFromAnalysisQuery(' company-123 '), 'company-123');
  assert.equal(customerIdFromAnalysisQuery(['company-456', 'ignored']), 'company-456');
  assert.equal(customerIdFromAnalysisQuery(undefined), '');
});

test('finds the matching customer using either supported id field', () => {
  const customers = [
    { client_id: 'company-123', customerId: '' },
    { client_id: '', customerId: 'company-456' },
  ];
  assert.equal(findAnalysisCustomer(customers, 'company-456'), customers[1]);
  assert.equal(findAnalysisCustomer(customers, 'missing'), null);
});
