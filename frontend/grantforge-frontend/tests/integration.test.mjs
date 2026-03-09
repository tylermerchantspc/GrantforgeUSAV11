import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const appPath = path.resolve(__dirname, '../src/App.jsx');
const configPath = path.resolve(__dirname, '../src/config.js');
const appSource = fs.readFileSync(appPath, 'utf8');
const configSource = fs.readFileSync(configPath, 'utf8');

test('critical endpoint routes are configured', () => {
  assert.ok(configSource.includes("preview: `${API_BASE}/preview`"));
  assert.ok(configSource.includes("checkout: `${API_BASE}/create-checkout-session`"));
  assert.ok(configSource.includes("downloadBySession: `${API_BASE}/download-by-session`"));
});

test('intake UI has no phone field and has required payment CTA', () => {
  assert.equal(/phone/i.test(appSource), false);
  assert.ok(appSource.includes('Pay Now — $2,500'));
  assert.ok(appSource.includes('Download Grant Narrative PDF'));
});
