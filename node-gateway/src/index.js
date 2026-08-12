require('dotenv').config();
const crypto = require('node:crypto');
const express = require('express');

const app = express();
app.use(express.json());

const PORT = process.env.GATEWAY_PORT || 4000;
const DETECTION_SERVICE_URL = process.env.DETECTION_SERVICE_URL || 'http://localhost:8000';

// Liveness check for the gateway container itself.
// Intentionally does NOT ping Mongo/Ollama — those are separate
// containers with their own health checks in docker-compose.yml.
// A gateway that reports unhealthy because a downstream dependency
// is slow to start creates false-positive restarts under Compose.
app.get('/health', (_req, res) => {
  res.status(200).json({ status: 'ok', service: 'node-gateway' });
});

// Extracts a single plain-text prompt from an OpenAI-style `messages` array.
// Accepts both `content: "string"` and `content: [{type:"text", text:"..."}]`
// (multimodal-shaped) messages so downstream detection (Phase 3) never has
// to handle the union type itself. Non-text parts (images, etc.) are ignored
// for now — out of scope until a vision-aware detector exists.
function extractPromptText(messages) {
  if (!Array.isArray(messages) || messages.length === 0) return null;
  const last = messages[messages.length - 1];
  if (!last || typeof last !== 'object') return null;
  const { content } = last;
  if (typeof content === 'string') {
    return content.trim().length > 0 ? content : null;
  }
  if (Array.isArray(content)) {
    const text = content
      .filter((part) => part && part.type === 'text' && typeof part.text === 'string')
      .map((part) => part.text)
      .join('\n')
      .trim();
    return text.length > 0 ? text : null;
  }
  return null;
}

// Task 2.2: Node -> Python wiring.
// Calls DETECTION_SERVICE_URL/analyze and awaits+logs the response.
// Boundary: NO decision enforcement here — the `action`/`risk_level` in the
// response is deliberately not branched on (that's Task 5.2's job). This
// also does not write to MongoDB (Task 5.3) and does not call
// EXTERNAL_LLM_BASE_URL (Task 5.2). A detection-service failure is logged
// only; it must not change this endpoint's Task 1.2 response contract.
async function callDetectionService(requestId, promptText) {
  const response = await fetch(`${DETECTION_SERVICE_URL}/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ request_id: requestId, prompt: promptText }),
  });

  if (!response.ok) {
    throw new Error(`detection service responded with ${response.status}`);
  }

  return response.json();
}

// Task 1.2: OpenAI-compatible intercept endpoint.
// Does NOT forward to EXTERNAL_LLM_BASE_URL (Task 5.2) yet.
app.post('/v1/chat/completions', async (req, res) => {
  const promptText = extractPromptText(req.body && req.body.messages);

  if (promptText === null) {
    return res.status(400).json({
      error: 'invalid_request',
      message: 'Expected non-empty "messages" array with extractable text content.',
    });
  }

  const requestId = crypto.randomUUID();

  try {
    const analysis = await callDetectionService(requestId, promptText);
    console.log(`[node-gateway] /analyze result for ${requestId}:`, analysis);
  } catch (err) {
    // Logging only, per Task 2.2 boundary — no enforcement/fallback logic
    // yet. Endpoint contract below is unaffected by a detection-service
    // outage until Task 5.2 defines what enforcement failure should do.
    console.error(`[node-gateway] detection service call failed for ${requestId}:`, err.message);
  }

  res.status(200).json({ request_id: requestId, prompt_received: true });
});

app.listen(PORT, () => {
  console.log(`[node-gateway] listening on port ${PORT}`);
});
