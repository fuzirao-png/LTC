import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  COUNTRY_CLOCKS_BY_ISO,
  cityNameFor,
  countryCardLabel,
  countryNameFor,
  resolveCustomerClock,
} from '../src/shared/utils/customerClock.js';

assert.deepEqual(resolveCustomerClock({ country: 'JP' }), {
  countryCode: 'JP',
  countryName: '日本',
  regionCode: 'EA',
  label: '日本时间',
  timeZone: 'Asia/Tokyo',
});
assert.deepEqual(resolveCustomerClock({ country: 'KR' }), {
  countryCode: 'KR',
  countryName: '韩国',
  regionCode: 'EA',
  label: '韩国时间',
  timeZone: 'Asia/Seoul',
});
assert.deepEqual(resolveCustomerClock({ country: 'CN' }), {
  countryCode: 'CN',
  countryName: '中国大陆',
  regionCode: 'EA',
  label: '中国大陆时间',
  timeZone: 'Asia/Shanghai',
});
assert.deepEqual(resolveCustomerClock({ country: 'US', city: 'Los Angeles' }), {
  countryCode: 'US',
  countryName: '美国',
  regionCode: 'NA',
  label: '美国时间',
  timeZone: 'America/New_York',
});
assert.deepEqual(resolveCustomerClock({ country: 'JP', timeZone: 'Asia/Seoul' }), {
  countryCode: 'JP',
  countryName: '日本',
  regionCode: 'EA',
  label: '日本时间',
  timeZone: 'Asia/Seoul',
});
assert.equal(resolveCustomerClock({ country: '', region: 'EA' }), null);
assert.equal(countryNameFor('中国'), '中国大陆');
assert.equal(countryNameFor('United Kingdom'), '英国');
assert.equal(countryCardLabel('DE'), '德国');
assert.equal(countryCardLabel('Germany'), '德国');
assert.equal(countryCardLabel('Atlantis'), '国家待确认');
assert.equal(countryCardLabel(''), '国家待确认');
assert.equal(cityNameFor('Maidstone'), '梅德斯通');

const seed = readFileSync(new URL('../../../db/seeds/0001_region_country_v5.sql', import.meta.url), 'utf8');
const seedRows = [...seed.matchAll(/\('([A-Z]{2})', '([^']+)', '([A-Z]+)', (?:NULL|'[^']*'), '([^']+)'/g)]
  .map(([, countryCode, countryName, regionCode, timeZone]) => ({ countryCode, countryName, regionCode, timeZone }));

assert.equal(seedRows.length, 205);
assert.equal(Object.keys(COUNTRY_CLOCKS_BY_ISO).length, 205);
for (const row of seedRows) {
  assert.deepEqual(COUNTRY_CLOCKS_BY_ISO[row.countryCode], row);
}

console.log('Customer clock resolution tests passed');
