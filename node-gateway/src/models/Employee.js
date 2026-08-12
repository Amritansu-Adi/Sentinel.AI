const mongoose = require('mongoose');

// Per-employee rollup, updated by Task 6.2's aggregation logic — not written
// to per-request (that would double-write vs. the `requests` collection).
const employeeSchema = new mongoose.Schema(
  {
    employee_id: { type: String, required: true, unique: true, index: true },
    name: { type: String, required: true },
    department: { type: String, default: '' },
    total_requests: { type: Number, required: true, default: 0, min: 0 },
    total_violations: { type: Number, required: true, default: 0, min: 0 },
    avg_risk: { type: Number, required: true, default: 0, min: 0, max: 100 },
    // NOTE: case preserved exactly as project.md §4 specifies (Low/Medium/High),
    // distinct from the requests.risk_level enum (SAFE/LOW/HIGH/CRITICAL).
    risk_tier: {
      type: String,
      required: true,
      default: 'Low',
      enum: ['Low', 'Medium', 'High'],
    },
  },
  { collection: 'employees', versionKey: false },
);

module.exports = mongoose.model('Employee', employeeSchema);
