import assert from 'node:assert/strict';
import test from 'node:test';

import { cityNameFor } from '../src/shared/utils/customerClock.js';

test('translates known customer cities to Chinese', () => {
  assert.equal(cityNameFor('Berlin'), '柏林');
  assert.equal(cityNameFor('Tokyo'), '东京');
  assert.equal(cityNameFor('Singapore'), '新加坡');
  assert.equal(cityNameFor('Global'), '\u57ce\u5e02\u5f85\u786e\u8ba4');
});

test('preserves Chinese and unknown city names', () => {
  assert.equal(cityNameFor('柏林'), '柏林');
  assert.equal(cityNameFor('Munich'), 'Munich');
  assert.equal(cityNameFor(''), '');
});
