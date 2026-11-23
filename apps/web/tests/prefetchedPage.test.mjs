import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import ts from 'typescript';

const source = readFileSync(new URL('../src/services/prefetchedPage.ts', import.meta.url), 'utf8');
const { outputText } = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ESNext } });
const { createPrefetchedPage } = await import(`data:text/javascript,${encodeURIComponent(outputText)}`);

test('prefetch and mount share the pending promise and its resolved result', async () => {
  const page = createPrefetchedPage();
  let resolve;
  const load = () => new Promise((done) => { resolve = done; });
  const key = ['alice', 'candidates', 100];
  const prefetch = page.load(key, load);
  assert.equal(page.load([...key], () => assert.fail('duplicate request')), prefetch);
  resolve(['candidate']);
  await prefetch;
  assert.deepEqual(await page.load(key, () => assert.fail('duplicate request')), ['candidate']);
  assert.deepEqual(await page.load(['bob', ...key.slice(1)], async () => ['other']), ['other']);
});

test('failures and session changes allow a fresh request', async () => {
  const page = createPrefetchedPage();
  const key = ['alice', 'pool', 100];
  await assert.rejects(page.load(key, async () => { throw new Error('offline'); }), /offline/);
  assert.equal(await page.load(key, async () => 1), 1);
  page.clear();
  assert.equal(await page.load(key, async () => 2), 2);
});
