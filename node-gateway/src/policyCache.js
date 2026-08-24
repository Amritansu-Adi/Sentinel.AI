// Task 7.1: live `policy_config` wiring.
//
// Fetches the singleton `policy_config` document (_id: "active") from
// MongoDB and caches it in memory for POLICY_CACHE_TTL_SECONDS (default
// 30s) — balances "changes take effect quickly" against "don't hit Mongo
// every request". Lazily initialized (no fetch at module load) so this
// file can be required without a live Mongo connection, e.g. in unit
// tests that only exercise other parts of the gateway.
//
// Boundary (project.md Task 7.1): if Mongo is unreachable, or no `active`
// document exists yet (fresh install before `npm run seed:policy`), this
// module must NEVER throw out of `getPolicyConfig()` and must never cause
// a request to hard-fail. It resolves to `null` instead, and callers
// treat `null` as "omit policy_config, let the detection service fall
// back to its own hardcoded defaults" — exactly risk_engine.py's existing
// `policy_config=None` behavior, unchanged by this task.

const { PolicyConfig } = require('./models');

const TTL_MS = (Number(process.env.POLICY_CACHE_TTL_SECONDS) || 30) * 1000;

let cachedValue = null; // plain-object shape: { thresholds, category_weights } | null
let cachedAt = 0; // epoch ms of last successful (or confirmed-absent) fetch
let inFlight = null; // dedupes concurrent refetches when the cache is cold/expired

function mapToPlainObject(map) {
  // Mongoose `Map` fields deserialize to a JS Map instance on a hydrated
  // document; Object.fromEntries handles both a Map and an already-plain
  // object (via Object.entries) so this is safe either way.
  if (map instanceof Map) return Object.fromEntries(map);
  if (map && typeof map === 'object') return { ...map };
  return {};
}

async function fetchFromMongo() {
  const doc = await PolicyConfig.findById('active').lean();
  if (!doc) return null;
  return {
    thresholds: { ...doc.thresholds },
    category_weights: mapToPlainObject(doc.category_weights),
  };
}

function isFresh() {
  return Date.now() - cachedAt < TTL_MS;
}

// Returns the cached/live policy_config as a plain object, or null if
// Mongo is unreachable / no active document exists. Never throws.
async function getPolicyConfig() {
  if (isFresh()) return cachedValue;
  if (inFlight) return inFlight;

  inFlight = fetchFromMongo()
    .then((value) => {
      cachedValue = value;
      cachedAt = Date.now();
      return cachedValue;
    })
    .catch((error) => {
      // Mongo unreachable or query failed: keep serving the last known
      // good value (even if stale) rather than dropping policy behavior
      // to defaults on a transient blip. If there has never been a
      // successful fetch, cachedValue is already null, which is the
      // correct "fall back to hardcoded defaults" signal downstream.
      console.error('[policyCache] failed to fetch policy_config, using last known value:', error.message);
      cachedAt = Date.now(); // still avoid hammering Mongo every request while it's down
      return cachedValue;
    })
    .finally(() => {
      inFlight = null;
    });

  return inFlight;
}

// Test-only escape hatch — not used in the request path.
function _resetCacheForTests() {
  cachedValue = null;
  cachedAt = 0;
  inFlight = null;
}

module.exports = { getPolicyConfig, _resetCacheForTests };