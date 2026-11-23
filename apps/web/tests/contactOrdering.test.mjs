import assert from 'node:assert/strict';

import {
  contactDisplayName,
  formatContactSummary,
  hasContactData,
  sortContacts,
} from '../src/shared/utils/contactOrdering.js';

const ordered = sortContacts([
  { full_name: 'Mina', title: 'Operations Manager' },
  { full_name: 'Chris', title: 'Chief Executive Officer' },
  { full_name: 'Bianca', title: 'Commercial Manager' },
  { firstName: 'Parker', lastName: 'Lee', jobTitle: 'Procurement Manager' },
  { full_name: 'Dylan', title: 'Director of Technology' },
]);

assert.deepEqual(
  ordered.map(contactDisplayName),
  ['Parker Lee', 'Bianca', 'Chris', 'Dylan', 'Mina'],
);
assert.equal(formatContactSummary(ordered, 2), 'Parker Lee · Procurement Manager、Bianca · Commercial Manager');
assert.equal(hasContactData({ email: 'provider@example.com' }), true);
assert.equal(hasContactData({}), false);

console.log('contact ordering tests passed');
