require('dotenv').config();
const crypto = require('node:crypto');
const express = require('express');
const { Readable } = require('node:stream');
const { pipeline } = require('node:stream/promises');
const { connect, Request, Employee } = require('./models');
const { issueAdminToken, requireAdmin } = require('./auth');
const { getPolicyConfig } = require('./policyCache');

const app = express();
app.use(express.json({ limit: '1mb' }));
app.use((req, res, next) => {
  res.set('Access-Control-Allow-Origin', process.env.DASHBOARD_ORIGIN || 'http://localhost:5173');
  res.set('Access-Control-Allow-Headers', 'Authorization, Content-Type, x-employee-id, x-employee-name, x-employee-department');
  if (req.method === 'OPTIONS') return res.sendStatus(204);
  return next();
});

const PORT = process.env.GATEWAY_PORT || 4000;
const DETECTION_SERVICE_URL = process.env.DETECTION_SERVICE_URL || 'http://localhost:8000';
const EXTERNAL_LLM_BASE_URL = process.env.EXTERNAL_LLM_BASE_URL;
const EXTERNAL_LLM_API_KEY = process.env.EXTERNAL_LLM_API_KEY;
const ADMIN_EMAIL = process.env.ADMIN_EMAIL || 'admin@sentinelai.local';
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || 'sentinelai-admin-change-me';

app.get('/health', (_req, res) => res.status(200).json({ status: 'ok', service: 'node-gateway' }));

function extractPromptText(messages) {
  if (!Array.isArray(messages) || messages.length === 0) return null;
  const last = messages[messages.length - 1];
  if (!last || typeof last !== 'object') return null;
  if (typeof last.content === 'string') return last.content.trim() ? last.content : null;
  if (!Array.isArray(last.content)) return null;
  const text = last.content.filter((part) => part && part.type === 'text' && typeof part.text === 'string')
    .map((part) => part.text).join('\n').trim();
  return text || null;
}

function replaceLastPrompt(body, prompt) {
  const messages = body.messages.map((message, index) => {
    if (index !== body.messages.length - 1) return message;
    return { ...message, content: prompt };
  });
  return { ...body, messages };
}

function employeeFromRequest(req) {
  const employeeId = String(req.get('x-employee-id') || 'unattributed').slice(0, 128);
  return {
    employee_id: employeeId,
    name: String(req.get('x-employee-name') || employeeId).slice(0, 128),
    department: String(req.get('x-employee-department') || '').slice(0, 128),
  };
}

async function callDetectionService(requestId, promptText) {
  // Task 7.1: attach the live (TTL-cached) policy_config when available.
  // getPolicyConfig() never throws and resolves to null on any Mongo
  // failure, so a policy-fetch problem can never block a request — the
  // detection service falls back to its own hardcoded defaults on null.
  const policyConfig = await getPolicyConfig();
  const body = { request_id: requestId, prompt: promptText };
  if (policyConfig) body.policy_config = policyConfig;

  const response = await fetch(`${DETECTION_SERVICE_URL}/analyze`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`detection service responded with ${response.status}`);
  return response.json();
}

async function writeAuditEvent({ requestId, employee, analysis, originalPrompt, sanitizedPrompt }) {
  await Request.create({
    request_id: requestId, timestamp: new Date(), employee_id: employee.employee_id,
    risk_score: analysis.risk_score, risk_level: analysis.risk_level, action: analysis.action,
    categories: analysis.categories || [], detectors_fired: analysis.detectors_fired || [],
    flags: analysis.flags || [],
    sanitized: analysis.action === 'SANITIZE', original_char_count: originalPrompt.length,
    sanitized_char_count: sanitizedPrompt ? sanitizedPrompt.length : null,
  });
  await Employee.updateOne(
    { employee_id: employee.employee_id },
    { $setOnInsert: { ...employee, total_requests: 0, total_violations: 0, avg_risk: 0, risk_tier: 'Low' } },
    { upsert: true },
  );
}

function externalCompletionUrl() {
  if (!EXTERNAL_LLM_BASE_URL || !EXTERNAL_LLM_API_KEY) return null;
  const base = EXTERNAL_LLM_BASE_URL.replace(/\/$/, '');
  return base.endsWith('/v1/chat/completions') ? base : `${base}/v1/chat/completions`;
}

function setSentinelHeaders(res, analysis) {
  // Task 7.3: the response body on ALLOW/SANITIZE is a byte-for-byte
  // passthrough of the upstream provider's real reply (must stay
  // untouched for programmatic callers), so masking/advisory metadata
  // goes out as headers instead. Values are fixed category names +
  // template messages (see risk_engine.py's _HUMAN_CATEGORY_LABELS) —
  // plain ASCII, safe as raw header values.
  res.set('X-Sentinel-Action', analysis.action);
  if (analysis.flags && analysis.flags.length > 0) {
    res.set('X-Sentinel-Flags', JSON.stringify(analysis.flags));
  }
}

async function forwardCompletion(req, res, requestId, body, analysis) {
  const target = externalCompletionUrl();
  if (!target) return res.status(503).json({ error: 'external_provider_unavailable', request_id: requestId, message: 'External LLM forwarding is not configured.' });
  const upstream = await fetch(target, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${EXTERNAL_LLM_API_KEY}` },
    body: JSON.stringify(body),
  });
  const contentType = upstream.headers.get('content-type');
  if (contentType) res.set('Content-Type', contentType);
  setSentinelHeaders(res, analysis);
  res.status(upstream.status);
  if (!upstream.body) return res.end();
  await pipeline(Readable.fromWeb(upstream.body), res);
}

app.post('/auth/login', (req, res) => {
  const { email, password } = req.body || {};
  if (email !== ADMIN_EMAIL || password !== ADMIN_PASSWORD) {
    return res.status(401).json({ error: 'invalid_credentials', message: 'Invalid email or password.' });
  }
  return res.json({ access_token: issueAdminToken(ADMIN_EMAIL), token_type: 'Bearer', user: { email: ADMIN_EMAIL, role: 'admin' } });
});

app.get('/stats/summary', requireAdmin, async (_req, res, next) => {
  try {
    const start = new Date(); start.setHours(0, 0, 0, 0);
    const [summary] = await Request.aggregate([
      { $match: { timestamp: { $gte: start } } },
      { $group: { _id: null, total: { $sum: 1 }, allowed: { $sum: { $cond: [{ $eq: ['$action', 'ALLOW'] }, 1, 0] } }, sanitized: { $sum: { $cond: [{ $eq: ['$action', 'SANITIZE'] }, 1, 0] } }, blocked: { $sum: { $cond: [{ $eq: ['$action', 'BLOCK'] }, 1, 0] } }, avg_risk: { $avg: '$risk_score' } } },
    ]);
    const [categories, timeline] = await Promise.all([
      Request.aggregate([{ $match: { timestamp: { $gte: start } } }, { $unwind: '$categories' }, { $group: { _id: '$categories', count: { $sum: 1 } } }, { $sort: { count: -1, _id: 1 } }, { $limit: 8 }, { $project: { _id: 0, category: '$_id', count: 1 } }]),
      Request.aggregate([{ $match: { timestamp: { $gte: start } } }, { $group: { _id: { $dateToString: { format: '%H:00', date: '$timestamp' } }, requests: { $sum: 1 } } }, { $sort: { _id: 1 } }, { $project: { _id: 0, hour: '$_id', requests: 1 } }]),
    ]);
    return res.json({ today: { total: summary?.total || 0, allowed: summary?.allowed || 0, sanitized: summary?.sanitized || 0, blocked: summary?.blocked || 0, avg_risk: Number((summary?.avg_risk || 0).toFixed(1)) }, top_categories: categories, requests_over_time: timeline });
  } catch (error) { return next(error); }
});

app.get('/stats/employees', requireAdmin, async (_req, res, next) => {
  try {
    const employees = await Request.aggregate([
      { $group: { _id: '$employee_id', total_requests: { $sum: 1 }, total_violations: { $sum: { $cond: [{ $ne: ['$action', 'ALLOW'] }, 1, 0] } }, avg_risk: { $avg: '$risk_score' } } },
      { $lookup: { from: 'employees', localField: '_id', foreignField: 'employee_id', as: 'profile' } },
      { $unwind: { path: '$profile', preserveNullAndEmptyArrays: true } },
      { $project: { _id: 0, employee_id: '$_id', name: { $ifNull: ['$profile.name', 'Unattributed'] }, department: { $ifNull: ['$profile.department', ''] }, total_requests: 1, total_violations: 1, avg_risk: { $round: ['$avg_risk', 1] } } },
      { $addFields: { risk_tier: { $switch: { branches: [{ case: { $gte: ['$avg_risk', 60] }, then: 'High' }, { case: { $gte: ['$avg_risk', 30] }, then: 'Medium' }], default: 'Low' } } } },
      { $sort: { avg_risk: -1, employee_id: 1 } },
    ]);
    return res.json({ employees });
  } catch (error) { return next(error); }
});

app.post('/v1/chat/completions', async (req, res, next) => {
  const promptText = extractPromptText(req.body?.messages);
  if (promptText === null) return res.status(400).json({ error: 'invalid_request', message: 'Expected non-empty "messages" array with extractable text content.' });
  const requestId = crypto.randomUUID();
  const employee = employeeFromRequest(req);
  try {
    const analysis = await callDetectionService(requestId, promptText);
    if (!['ALLOW', 'SANITIZE', 'BLOCK'].includes(analysis.action)) throw new Error('detection service returned an invalid action');
    const sanitizedPrompt = analysis.action === 'SANITIZE' ? analysis.sanitized_prompt : null;
    if (analysis.action === 'SANITIZE' && typeof sanitizedPrompt !== 'string') throw new Error('detection service did not return sanitized_prompt');
    await writeAuditEvent({ requestId, employee, analysis, originalPrompt: promptText, sanitizedPrompt });
    if (analysis.action === 'BLOCK') {
      return res.status(403).json({
        error: 'request_blocked',
        request_id: requestId,
        risk_score: analysis.risk_score,
        categories: analysis.categories || [],
        reason: 'Blocked by SentinelAI policy.',
        rewrite_guidance: analysis.rewrite_guidance || null,
      });
    }
    return forwardCompletion(req, res, requestId, analysis.action === 'SANITIZE' ? replaceLastPrompt(req.body, sanitizedPrompt) : req.body, analysis);
  } catch (error) { return next(error); }
});

app.use((error, _req, res, _next) => {
  console.error('[node-gateway] request failed:', error.message);
  res.status(503).json({ error: 'gateway_unavailable', message: 'Request could not be safely processed.' });
});

if (require.main === module) {
  connect().then(() => app.listen(PORT, () => console.log(`[node-gateway] listening on port ${PORT}`)))
    .catch((error) => { console.error('[node-gateway] MongoDB connection failed:', error.message); process.exitCode = 1; });
}

module.exports = { app, extractPromptText, replaceLastPrompt };