// Plain-Node assertion script for dashboard/src/chatResponse.js -- no test
// framework installed in this package, matching identity.js's precedent
// (dashboard/scripts/testIdentity.js) and node-gateway's
// scripts/testPolicyCache.js. Run with:
//   node scripts/testChatResponse.js
// from dashboard/.

import assert from 'node:assert/strict';
import {
  parseSentinelFlags,
  extractReplyText,
  buildChatOutcome,
  buildCompletionRequest,
} from '../src/chatResponse.js';

let passed = 0;
function check(label, fn) {
  fn();
  passed += 1;
  console.log(`  ok - ${label}`);
}

function fakeHeaders(map) {
  return { get: (name) => map[name.toLowerCase()] ?? null };
}

console.log('chatResponse.js');

check('parseSentinelFlags() returns [] for missing/null header', () => {
  assert.deepEqual(parseSentinelFlags(null), []);
  assert.deepEqual(parseSentinelFlags(undefined), []);
  assert.deepEqual(parseSentinelFlags(''), []);
});

check('parseSentinelFlags() returns [] and never throws on malformed JSON', () => {
  assert.deepEqual(parseSentinelFlags('{not json'), []);
  assert.deepEqual(parseSentinelFlags('"just a string"'), []);
});

check('parseSentinelFlags() drops malformed entries, keeps well-formed ones', () => {
  const raw = JSON.stringify([
    { category: 'PII_EXPOSURE', message: 'Masked personal information before forwarding this message.' },
    { category: 'NO_MESSAGE' },
    'not-an-object',
  ]);
  assert.deepEqual(parseSentinelFlags(raw), [
    { category: 'PII_EXPOSURE', message: 'Masked personal information before forwarding this message.' },
  ]);
});

check('extractReplyText() reads choices[0].message.content', () => {
  assert.equal(extractReplyText({ choices: [{ message: { content: 'hi there' } }] }), 'hi there');
});

check('extractReplyText() returns null (not throw) on missing/empty/wrong-shape content', () => {
  assert.equal(extractReplyText({}), null);
  assert.equal(extractReplyText({ choices: [] }), null);
  assert.equal(extractReplyText({ choices: [{ message: { content: '' } }] }), null);
  assert.equal(extractReplyText(null), null);
  assert.equal(extractReplyText(undefined), null);
});

check('buildChatOutcome() maps a clean 200 with no flags to ALLOW', () => {
  const outcome = buildChatOutcome({
    ok: true,
    status: 200,
    headers: fakeHeaders({ 'x-sentinel-action': 'ALLOW' }),
    body: { choices: [{ message: { content: 'Sure, here is the answer.' } }] },
  });
  assert.deepEqual(outcome, { state: 'ALLOW', reply: 'Sure, here is the answer.', flags: [] });
});

check('buildChatOutcome() maps ALLOW-with-advisory-flags to ALLOW carrying flags (not SANITIZE)', () => {
  const outcome = buildChatOutcome({
    ok: true,
    status: 200,
    headers: fakeHeaders({
      'x-sentinel-action': 'ALLOW',
      'x-sentinel-flags': JSON.stringify([{ category: 'ORG_MENTION', message: 'This message may contain an organization name. No content was removed; please review before sending.' }]),
    }),
    body: { choices: [{ message: { content: 'Reply text.' } }] },
  });
  assert.equal(outcome.state, 'ALLOW');
  assert.equal(outcome.flags.length, 1);
});

check('buildChatOutcome() maps a 200 with X-Sentinel-Action: SANITIZE to SANITIZE with flags', () => {
  const outcome = buildChatOutcome({
    ok: true,
    status: 200,
    headers: fakeHeaders({
      'x-sentinel-action': 'SANITIZE',
      'x-sentinel-flags': JSON.stringify([{ category: 'PII_EXPOSURE', message: 'Masked PII_EXPOSURE before forwarding this message.' }]),
    }),
    body: { choices: [{ message: { content: 'Reply based on the masked prompt.' } }] },
  });
  assert.equal(outcome.state, 'SANITIZE');
  assert.equal(outcome.reply, 'Reply based on the masked prompt.');
  assert.deepEqual(outcome.flags, [{ category: 'PII_EXPOSURE', message: 'Masked PII_EXPOSURE before forwarding this message.' }]);
});

check('buildChatOutcome() maps a 403 request_blocked body to BLOCK', () => {
  const outcome = buildChatOutcome({
    ok: false,
    status: 403,
    headers: fakeHeaders({}),
    body: {
      error: 'request_blocked',
      request_id: 'abc-123',
      risk_score: 92,
      categories: ['CONFIDENTIAL_COMPANY_DATA'],
      reason: 'Blocked by SentinelAI policy.',
      rewrite_guidance: 'Remove references to internal project names and try again.',
    },
  });
  assert.deepEqual(outcome, {
    state: 'BLOCK',
    requestId: 'abc-123',
    riskScore: 92,
    categories: ['CONFIDENTIAL_COMPANY_DATA'],
    reason: 'Blocked by SentinelAI policy.',
    rewriteGuidance: 'Remove references to internal project names and try again.',
  });
});

check('buildChatOutcome() maps a non-403 failure (e.g. 503 gateway_unavailable) to ERROR, not BLOCK', () => {
  const outcome = buildChatOutcome({
    ok: false,
    status: 503,
    headers: fakeHeaders({}),
    body: { error: 'gateway_unavailable', message: 'Request could not be safely processed.' },
  });
  assert.deepEqual(outcome, { state: 'ERROR', message: 'Request could not be safely processed.' });
});

check('buildChatOutcome() maps a 200 with an unreadable body to ERROR, not a crash', () => {
  const outcome = buildChatOutcome({
    ok: true,
    status: 200,
    headers: fakeHeaders({ 'x-sentinel-action': 'ALLOW' }),
    body: { unexpected: 'shape' },
  });
  assert.equal(outcome.state, 'ERROR');
});

check('buildCompletionRequest() wraps prompt text as a single-turn OpenAI-style body', () => {
  assert.deepEqual(buildCompletionRequest('hello'), { messages: [{ role: 'user', content: 'hello' }] });
});

console.log(`\n${passed}/${passed} checks passed.`);
