const mongoose = require('mongoose');

// Singleton config document — _id is pinned to the literal string "active"
// (default + immutable) so the collection can only ever hold one active
// policy document. Read live (TTL-cached) by node-gateway/src/policyCache.js
// as of Task 7.1 and forwarded into python-detection's /analyze call; no
// write path from the gateway exists yet (edits happen directly in Mongo,
// e.g. via mongosh or scripts/seedPolicyConfig.js).
const policyConfigSchema = new mongoose.Schema(
  {
    _id: { type: String, default: 'active', immutable: true },
    thresholds: {
      safe_max: { type: Number, required: true },
      low_max: { type: Number, required: true },
      high_max: { type: Number, required: true },
    },
    // Map<String, Number> rather than a fixed sub-schema so Task 4.x can add
    // categories later without a schema migration.
    category_weights: {
      type: Map,
      of: Number,
      required: true,
    },
    version: { type: Number, required: true, default: 1 },
    updated_at: { type: Date, required: true, default: Date.now },
  },
  { collection: 'policy_config', versionKey: false },
);

module.exports = mongoose.model('PolicyConfig', policyConfigSchema);