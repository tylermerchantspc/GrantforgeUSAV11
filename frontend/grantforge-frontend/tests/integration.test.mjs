import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const appPath = path.resolve(__dirname, '../src/App.jsx');
const configPath = path.resolve(__dirname, '../src/config.js');
const fetcherPath = path.resolve(__dirname, '../src/fetcher.js');
const appSource = fs.readFileSync(appPath, 'utf8');
const configSource = fs.readFileSync(configPath, 'utf8');
const fetcherSource = fs.readFileSync(fetcherPath, 'utf8');

test('critical endpoint routes are configured', () => {
  assert.ok(configSource.includes("preview: `${API_BASE}/preview`"));
  assert.ok(configSource.includes("checkout: `${API_BASE}/create-checkout-session`"));
  assert.ok(configSource.includes("downloadBySession: `${API_BASE}/download-by-session`"));
});

test('intake UI is polished and required validations are present', () => {
  assert.equal(appSource.includes('placeholder='), false);
  assert.equal(appSource.includes('Phone'), false);
  assert.equal(appSource.includes('phone'), false);
  assert.ok(appSource.includes('Organization name is required.'));
  assert.ok(appSource.includes('Please choose your organization category.'));
  assert.ok(appSource.includes('Please complete the required fields before continuing.'));
});

test('payment and download flow does not expose stripe session ids in URL', () => {
  assert.equal(appSource.includes('session_id'), false);
  assert.ok(appSource.includes('Missing secure checkout reference.'));
  assert.ok(fetcherSource.includes('checkout_ref'));
  assert.ok(appSource.includes('Pay Now — $2,500'));
});
