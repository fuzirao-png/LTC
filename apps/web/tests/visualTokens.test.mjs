import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const css = readFileSync(new URL('../src/style.css', import.meta.url), 'utf8');
const requiredTokens = [
  '--bg-page', '--bg-panel', '--bg-hover', '--bg-selected', '--bg-disabled',
  '--text-main', '--text-muted', '--text-disabled',
  '--success-bg', '--warning-bg', '--danger-bg', '--info-bg',
  '--radius', '--radius-sm', '--radius-xs', '--shadow-sm', '--shadow-md',
  '--font-caption', '--font-small', '--font-body', '--font-title',
  '--space-1', '--space-2', '--space-3', '--space-4', '--space-5',
];

for (const token of requiredTokens) {
  assert.match(css, new RegExp(`${token.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*:`), `missing ${token}`);
}

assert.match(css, /--radius:\s*8px/);
assert.match(css, /button:disabled,[\s\S]*?cursor:\s*not-allowed/);
assert.match(css, /input:focus-visible,[\s\S]*?outline:\s*2px solid var\(--blue-primary\)/);
assert.match(css, /@media \(max-width: 760px\)[\s\S]*?\.nav-group[\s\S]*?overflow-x:\s*auto/);
assert.match(css, /\.stage-text,[\s\S]*?white-space:\s*nowrap/);

console.log('Visual token contract test passed');
