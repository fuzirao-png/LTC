import test from 'node:test';
import assert from 'node:assert/strict';

import {
  sortActiveRosterContacts,
  sortBackupRosterContacts,
} from './contactRosterOrdering.js';

test('active roster puts pinned contacts first then sorts by score', () => {
  const result = sortActiveRosterContacts([
    { contact_id: 'high', full_name: 'High', priority_score: 95, position: 1, is_pinned: false },
    { contact_id: 'pinned', full_name: 'Pinned', priority_score: 20, position: 3, is_pinned: true },
    { contact_id: 'mid', full_name: 'Mid', priority_score: 80, position: 2, is_pinned: false },
  ]);

  assert.deepEqual(result.map((item) => item.contact_id), ['pinned', 'high', 'mid']);
});

test('active roster uses position when scores tie', () => {
  const result = sortActiveRosterContacts([
    { contact_id: 'second', full_name: 'Second', priority_score: 80, position: 2 },
    { contact_id: 'first', full_name: 'First', priority_score: 80, position: 1 },
  ]);

  assert.deepEqual(result.map((item) => item.contact_id), ['first', 'second']);
});

test('backup roster sorts by score then name', () => {
  const result = sortBackupRosterContacts([
    { contact_id: 'b', full_name: 'Beta', priority_score: 70 },
    { contact_id: 'a', full_name: 'Alpha', priority_score: 70 },
    { contact_id: 'top', full_name: 'Top', priority_score: 90 },
  ]);

  assert.deepEqual(result.map((item) => item.contact_id), ['top', 'a', 'b']);
});

test('ordering helpers do not mutate API arrays', () => {
  const contacts = [
    { contact_id: 'low', full_name: 'Low', priority_score: 10 },
    { contact_id: 'high', full_name: 'High', priority_score: 90 },
  ];

  sortActiveRosterContacts(contacts);

  assert.deepEqual(contacts.map((item) => item.contact_id), ['low', 'high']);
});
