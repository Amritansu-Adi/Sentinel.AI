// Task 7.1 verification script — no test framework installed in this
// package, so this is a plain-Node assertion script (run with `node
// scripts/testPolicyCache.js`), not a Jest/Mocha suite. Mocks
// PolicyConfig.findById directly rather than requiring a live MongoDB
// connection, so this is safe to run in any environment.

const assert = require('node:assert/strict');

// --- Mock PolicyConfig before requiring policyCache -------------------------
const Module = require('node:module');
const path = require('node:path');

const modelsPath = path.join(__dirname, '..', 'src', 'models.js');
let mockDoc = null;
let mongoShouldThrow = false;
let findByIdCallCount = 0;

const fakeModels = {
  PolicyConfig: {
    findById: (_id) => ({
      lean: async () => {
        findByIdCallCount += 1;
        if (mongoShouldThrow) throw new Error('mock mongo failure');
        return mockDoc;
      },
    }),
  },
};

const originalResolve = Module._resolveFilename;
const originalLoad = Module._load;
Module._load = function (request, parent, isMain) {
  if (request === './models' || request.endsWith(path.join('node-gateway', 'src', 'models'))) {
    return fakeModels;
  }
  return originalLoad.apply(this, arguments);
};

process.env.POLICY_CACHE_TTL_SECONDS = '0.05'; // 50ms, fast test TTL

const { getPolicyConfig, _resetCacheForTests } = require('../src/policyCache');

async function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function run() {
  // 1. No active document yet -> resolves to null, never throws.
  _resetCacheForTests();
  mockDoc = null;
  findByIdCallCount = 0;
  const empty = await getPolicyConfig();
  assert.equal(empty, null, 'expected null when no active policy_config document exists');
  console.log('PASS: missing policy_config document resolves to null');

  // 2. Document exists, Map field converts to a plain object.
  _resetCacheForTests();
  mockDoc = {
    thresholds: { safe_max: 29, low_max: 59, high_max: 79 },
    category_weights: new Map([['PII_EXPOSURE', 80], ['CREDENTIAL_EXPOSURE', 90]]),
  };
  const value = await getPolicyConfig();
  assert.deepEqual(value.thresholds, { safe_max: 29, low_max: 59, high_max: 79 });
  assert.deepEqual(value.category_weights, { PII_EXPOSURE: 80, CREDENTIAL_EXPOSURE: 90 });
  console.log('PASS: Mongoose Map category_weights converts to a plain object');

  // 3. Cache is honoured within TTL — a second call before TTL expiry must
  // not re-query Mongo.
  const callsBefore = findByIdCallCount;
  await getPolicyConfig();
  assert.equal(findByIdCallCount, callsBefore, 'expected cached value to be served without a second Mongo query');
  console.log('PASS: within-TTL calls are served from cache, not re-fetched');

  // 4. Changing the underlying doc + waiting past TTL picks up the change
  // without a redeploy.
  mockDoc = {
    thresholds: { safe_max: 29, low_max: 59, high_max: 79 },
    category_weights: new Map([['PII_EXPOSURE', 10]]),
  };
  await sleep(80); // > 50ms TTL
  const updated = await getPolicyConfig();
  assert.equal(updated.category_weights.PII_EXPOSURE, 10, 'expected updated weight to be picked up after TTL expiry');
  console.log('PASS: policy_config changes take effect after TTL expiry, without redeploy');

  // 5. Mongo failure never throws — falls back to last known value.
  _resetCacheForTests();
  mockDoc = { thresholds: { safe_max: 29, low_max: 59, high_max: 79 }, category_weights: new Map([['PII_EXPOSURE', 80]]) };
  await getPolicyConfig(); // seed a good cached value
  await sleep(80);
  mongoShouldThrow = true;
  const fallback = await getPolicyConfig();
  assert.deepEqual(fallback.category_weights, { PII_EXPOSURE: 80 }, 'expected last known value on Mongo failure, no throw');
  mongoShouldThrow = false;
  console.log('PASS: Mongo failure never throws, falls back to last known cached value');

  console.log('\nAll policyCache.js Task 7.1 checks passed.');
}

run()
  .catch((error) => {
    console.error('FAIL:', error.message);
    process.exitCode = 1;
  })
  .finally(() => {
    Module._load = originalLoad;
  });
