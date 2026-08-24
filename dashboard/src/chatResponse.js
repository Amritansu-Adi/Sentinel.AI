// Task 8.2 — pure helpers for turning a POST /v1/chat/completions gateway
// response into the three UI states project.md §5 Task 8.2 requires
// (ALLOW / SANITIZE / BLOCK). Kept dependency-free and React-free, same
// reasoning as identity.js: directly unit-testable with a plain Node
// script (see dashboard/scripts/testChatResponse.js), no framework needed.
//
// Contract this consumes (node-gateway/src/index.js, unchanged by this
// task):
//   - ALLOW/SANITIZE: HTTP 2xx, body is a byte-for-byte upstream chat
//     completion (OpenAI-compatible `choices[0].message.content` shape),
//     `X-Sentinel-Action` header is ALLOW or SANITIZE, `X-Sentinel-Flags`
//     (JSON array of {category, message}) present only when non-empty.
//   - BLOCK: HTTP 403, JSON body {error:'request_blocked', request_id,
//     risk_score, categories, reason, rewrite_guidance}. No upstream call
//     is made, so there is no reply to render.
//   - Anything else (network failure, 5xx, malformed body): ERROR, a
//     gateway/detection-service problem, not a policy decision.
//
// Note: per risk_engine.py's determine_action(), ALLOW can itself carry
// non-empty flags (LLM-only category hits with no masking applied --
// advisory only, nothing removed). That's distinct from SANITIZE (where
// content *was* masked) even though both surface via X-Sentinel-Flags, so
// callers must branch on `state`, not merely on flags.length.

/**
 * Parses the `X-Sentinel-Flags` header: a JSON array of
 * `{category, message}` (see risk_engine.py `Flag.to_dict()`). The
 * `message` field is already a template string with no raw prompt
 * content in it -- safe to render verbatim. Never throws; a
 * missing/malformed header degrades to `[]`.
 */
export function parseSentinelFlags(headerValue) {
  if (!headerValue) return [];
  try {
    const parsed = JSON.parse(headerValue);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (flag) => flag && typeof flag.category === 'string' && typeof flag.message === 'string',
    );
  } catch {
    return [];
  }
}

/**
 * Best-effort assistant-reply extraction from an OpenAI-compatible chat
 * completion body. EXTERNAL_LLM_BASE_URL is provider-configurable
 * (project.md: Groq primary) but all OpenAI-compatible providers share
 * this `choices[0].message.content` shape. Returns null (never throws) on
 * any shape mismatch so the caller can render a distinct ERROR state
 * instead of crashing on `undefined`.
 */
export function extractReplyText(completionBody) {
  const content = completionBody?.choices?.[0]?.message?.content;
  return typeof content === 'string' && content.length > 0 ? content : null;
}

/**
 * Normalizes a fetch Response (already `.json()`-parsed) into one of four
 * UI outcomes. `headers` must expose `.get(name)` (a real fetch Headers
 * object already lowercases lookups, so callers don't need to case-match).
 *
 * @returns {
 *   {state:'BLOCK', requestId, riskScore, categories, reason, rewriteGuidance} |
 *   {state:'ALLOW'|'SANITIZE', reply, flags} |
 *   {state:'ERROR', message}
 * }
 */
export function buildChatOutcome({ ok, status, headers, body }) {
  if (!ok && status === 403 && body && body.error === 'request_blocked') {
    return {
      state: 'BLOCK',
      requestId: typeof body.request_id === 'string' ? body.request_id : null,
      riskScore: typeof body.risk_score === 'number' ? body.risk_score : null,
      categories: Array.isArray(body.categories) ? body.categories : [],
      reason: typeof body.reason === 'string' ? body.reason : 'Blocked by SentinelAI policy.',
      rewriteGuidance: typeof body.rewrite_guidance === 'string' ? body.rewrite_guidance : null,
    };
  }
  if (!ok) {
    return {
      state: 'ERROR',
      message: (body && typeof body.message === 'string' && body.message) || `Request failed (${status}).`,
    };
  }
  const action = headers.get('x-sentinel-action');
  const flags = parseSentinelFlags(headers.get('x-sentinel-flags'));
  const reply = extractReplyText(body);
  if (reply === null) {
    return { state: 'ERROR', message: 'Gateway response did not include a readable reply.' };
  }
  return { state: action === 'SANITIZE' ? 'SANITIZE' : 'ALLOW', reply, flags };
}

/** Builds the OpenAI-style request body extractPromptText()/replaceLastPrompt() on the gateway expect: a single-turn user message. Task 8.2 keeps each send a fresh one-message request (no running conversation replayed upstream) -- simplest correct thing given the gateway only inspects the *last* message for detection. */
export function buildCompletionRequest(promptText) {
  return { messages: [{ role: 'user', content: promptText }] };
}
