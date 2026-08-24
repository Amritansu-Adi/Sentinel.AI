// Task 8.1 — Lightweight user identity.
//
// No new backend auth surface: this reuses node-gateway's existing
// x-employee-id / x-employee-name / x-employee-department header contract
// (see node-gateway/src/index.js -> employeeFromRequest()). Identity lives
// client-side only, in localStorage, and is attached as headers on every
// gateway request -- there is no server-side session for end users.
//
// Pure functions only (no React) so this file is directly unit-testable
// with a plain Node script -- see dashboard/scripts/testIdentity.js.

const STORAGE_KEY = 'sentinelai_identity';

function storage() {
  // Guarded so this module never throws in environments without
  // localStorage (SSR, plain-Node test scripts without a polyfill, private
  // browsing tabs that disable storage) -- callers get null/no-op instead
  // of a crash.
  return typeof globalThis.localStorage !== 'undefined' ? globalThis.localStorage : null;
}

/**
 * Reads the persisted identity, if any.
 * @returns {{employeeId: string, name: string, department: string} | null}
 */
export function getIdentity() {
  const store = storage();
  if (!store) return null;
  let raw;
  try {
    raw = store.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed.employeeId !== 'string' || !parsed.employeeId.trim()) return null;
    return {
      employeeId: parsed.employeeId,
      name: typeof parsed.name === 'string' && parsed.name.trim() ? parsed.name : parsed.employeeId,
      department: typeof parsed.department === 'string' ? parsed.department : '',
    };
  } catch {
    // Corrupt/foreign JSON in the key -- treat as "not identified" rather
    // than throwing and breaking the chat entry screen.
    return null;
  }
}

/**
 * Validates, trims, and persists an identity. Name defaults to the employee
 * ID when left blank; department is optional.
 * @throws {Error} if employeeId is blank after trimming.
 */
export function setIdentity({ employeeId, name, department } = {}) {
  const trimmedId = (employeeId || '').trim();
  if (!trimmedId) throw new Error('employeeId is required');
  const identity = {
    employeeId: trimmedId,
    name: (name || '').trim() || trimmedId,
    department: (department || '').trim(),
  };
  const store = storage();
  if (store) store.setItem(STORAGE_KEY, JSON.stringify(identity));
  return identity;
}

/** Clears the persisted identity. */
export function clearIdentity() {
  const store = storage();
  if (store) store.removeItem(STORAGE_KEY);
}

/**
 * Maps an identity to the exact header names node-gateway's
 * employeeFromRequest() reads. Returns {} for a null/incomplete identity so
 * callers can spread this directly into fetch() headers unconditionally.
 */
export function identityHeaders(identity) {
  if (!identity || !identity.employeeId) return {};
  const headers = { 'x-employee-id': identity.employeeId };
  if (identity.name) headers['x-employee-name'] = identity.name;
  if (identity.department) headers['x-employee-department'] = identity.department;
  return headers;
}
