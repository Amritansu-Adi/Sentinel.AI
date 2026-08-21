require('dotenv').config();
const { connect, PolicyConfig } = require('../src/models');

// Thresholds mirror .env.example (RISK_THRESHOLD_*) exactly.
const DEFAULT_THRESHOLDS = { safe_max: 29, low_max: 59, high_max: 79 };

// Task 4.3: approved policy weights, locked in handover.md.
const DEFAULT_CATEGORY_WEIGHTS = {
  CREDENTIAL_EXPOSURE: 90,
  PII_EXPOSURE: 80,
  FINANCIAL_DATA: 75,
  CONFIDENTIAL_COMPANY_DATA: 70,
  SOURCE_CODE_SENSITIVE: 50,
  SECURITY_SENSITIVE_INFORMATION: 65,
  INTERNAL_SYSTEM_INFORMATION: 50,
  UNKNOWN: 15,
  SAFE: 0,
};

async function seed() {
  await connect();

  const existing = await PolicyConfig.findById('active');
  if (existing) {
    console.log('[seed] policy_config "active" already exists — skipping. (Delete it manually to re-seed.)');
    return;
  }

  await PolicyConfig.create({
    _id: 'active',
    thresholds: DEFAULT_THRESHOLDS,
    category_weights: DEFAULT_CATEGORY_WEIGHTS,
    version: 1,
    updated_at: new Date(),
  });

  console.log('[seed] policy_config "active" created with default thresholds + category weights.');
}

seed()
  .catch((err) => {
    console.error('[seed] failed:', err.message);
    process.exitCode = 1;
  })
  .finally(async () => {
    const mongoose = require('mongoose');
    await mongoose.disconnect();
  });
