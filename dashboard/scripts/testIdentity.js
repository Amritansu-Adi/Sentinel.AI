// Plain-Node assertion script for dashboard/src/identity.js -- no test
// framework installed in this package, matching node-gateway's
// scripts/testPolicyCache.js precedent. Run with:
//   node scripts/testIdentity.js
// from dashboard/.

import assert from 'node:assert/strict';

// Minimal in-memory localStorage polyfill -- identity.js reads
// globalThis.localStorage specifically so this is a clean seam.
class MemoryStorage {
  constructor() { this._data = new Map(); }
  getItem(key) { return this._data.has(key) ? this._data.get(key) : null; }
  setItem(key, value) { this._data.set(key, String(value)); }
  removeItem(key) { this._data.delete(key); }
}
globalThis.localStorage = new MemoryStorage();

const { getIdentity, setIdentity, clearIdentity, identityHeaders } = await import('../src/identity.js');

let passed = 0;
function check(label, fn) {
  fn();
  passed += 1;
  console.log(`  ok - ${label}`);
}

console.log('identity.js');

check('getIdentity() is null when nothing stored', () => {
  assert.equal(getIdentity(), null);
});

check('setIdentity() trims fields and defaults name to employeeId', () => {
  const result = setIdentity({ employeeId: '  EMP-1  ', name: '  ', department: ' Sales ' });
  assert.deepEqual(result, { employeeId: 'EMP-1', name: 'EMP-1', department: 'Sales' });
});

check('getIdentity() returns exactly what was persisted', () => {
  setIdentity({ employeeId: 'EMP-2', name: 'Priya Sharma', department: 'Engineering' });
  assert.deepEqual(getIdentity(), { employeeId: 'EMP-2', name: 'Priya Sharma', department: 'Engineering' });
});

check('setIdentity() rejects a blank employeeId', () => {
  assert.throws(() => setIdentity({ employeeId: '   ' }), /employeeId is required/);
});

check('clearIdentity() removes the stored identity', () => {
  setIdentity({ employeeId: 'EMP-3' });
  clearIdentity();
  assert.equal(getIdentity(), null);
});

check('getIdentity() degrades to null on corrupt stored JSON, does not throw', () => {
  globalThis.localStorage.setItem('sentinelai_identity', 'not-json{{{');
  assert.doesNotThrow(() => getIdentity());
  assert.equal(getIdentity(), null);
});

check('identityHeaders() returns {} for null identity', () => {
  assert.deepEqual(identityHeaders(null), {});
});

check('identityHeaders() always includes x-employee-id, omits blank department', () => {
  const headers = identityHeaders({ employeeId: 'EMP-4', name: 'Ravi', department: '' });
  assert.deepEqual(headers, { 'x-employee-id': 'EMP-4', 'x-employee-name': 'Ravi' });
});

check('identityHeaders() includes department when present', () => {
  const headers = identityHeaders({ employeeId: 'EMP-5', name: 'Anu', department: 'Legal' });
  assert.deepEqual(headers, { 'x-employee-id': 'EMP-5', 'x-employee-name': 'Anu', 'x-employee-department': 'Legal' });
});

console.log(`${passed}/${passed} checks pass`);
