const mongoose = require('mongoose');

// Audit event — one document per intercepted prompt (Task 5.3 writes these).
// No raw sensitive values ever stored here, only scores/categories/counts.
const requestSchema = new mongoose.Schema(
  {
    request_id: { type: String, required: true, unique: true, index: true },
    timestamp: { type: Date, required: true, default: Date.now },
    employee_id: { type: String, required: true, index: true },
    risk_score: { type: Number, required: true, min: 0, max: 100 },
    risk_level: {
      type: String,
      required: true,
      enum: ['SAFE', 'LOW', 'HIGH', 'CRITICAL'],
    },
    action: {
      type: String,
      required: true,
      enum: ['ALLOW', 'SANITIZE', 'BLOCK'],
    },
    categories: { type: [String], default: [] },
    detectors_fired: { type: [String], default: [] },
    sanitized: { type: Boolean, required: true, default: false },
    original_char_count: { type: Number, required: true, min: 0 },
    sanitized_char_count: { type: Number, default: null },
  },
  { collection: 'requests', versionKey: false },
);

module.exports = mongoose.model('Request', requestSchema);
