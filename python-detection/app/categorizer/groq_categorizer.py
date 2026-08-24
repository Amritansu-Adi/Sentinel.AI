"""
SentinelAI — python-detection service (Task 4.2: Groq categorizer fallback)

Drop-in swap for `classify_local(evidence) -> CategoryResult`
(ollama_categorizer.py, Task 4.1) — same signature, same return shape,
same architectural boundary (never outputs ALLOW/SANITIZE/BLOCK; that is
the deterministic risk engine's exclusive authority, Task 4.3).

Per Task 4.2's handover spec, this module does NOT redefine
`CATEGORY_NAMES` / `CategoryFinding` / `CategoryResult` / `CategorizerError`
/ `CategorizerUnavailableError` / `_SYSTEM_PROMPT` / `_format_evidence` /
`_parse_response` — all are imported from `ollama_categorizer.py`. A
second copy of `CATEGORY_NAMES` (or a re-typed system prompt) with even
one typo would be a silent categorization bug; importing guarantees byte-
identical text and behavior across both providers.

CRITICAL PRIVACY PROPERTY (same as classify_local): this module is never
given the raw prompt — only `merged_evidence` (typed metadata: types,
severities, spans-as-offsets, confidences, company-doc titles/
classifications). Enforced by construction: nothing here reads a `prompt`
key.

Structured output differs from Ollama: Groq's free tier does not support
JSON-schema-constrained decoding (`format=<schema>`), so this uses
`response_format={"type": "json_object"}` plus an explicit instruction
appended to the user turn, and leans on `_parse_response`'s existing
defensive validation (enum re-check, confidence clamp, malformed-JSON ->
UNKNOWN) exactly as the Ollama path does — not reimplemented here.
"""

import os
from typing import List

from .ollama_categorizer import (
    CategoryFinding,
    CategoryResult,
    CategorizerUnavailableError,
    _SYSTEM_PROMPT,
    _format_evidence,
    _parse_response,
)

# Both already existed in project.md's Phase-0 env table; this is the
# first task to actually read them (same "wire it for real" precedent
# Task 3.3/4.1 set for their own env vars).
_GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
_GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

# Hardcoded operational default, not a new config surface (same rationale
# as ollama_categorizer's _REQUEST_TIMEOUT_SECONDS). Groq's hosted
# llama-3.1-8b-instant is fast on this evidence-only payload (project.md
# §6/handover §7.5 expect <5s) — 30s is a generous ceiling for network
# jitter, not a tuned-for-slowness value like Ollama's cold-start figure.
_REQUEST_TIMEOUT_SECONDS = 30

# Groq lacks Ollama's format=<json_schema> constrained decoding, so the
# JSON-object requirement is reinforced in the user turn in addition to
# being inherited from the shared _SYSTEM_PROMPT's rule #5 ("Output ONLY
# the JSON object... no prose, no markdown fences").
_JSON_OBJECT_INSTRUCTION = (
    '\n\nRespond with only a single JSON object of the exact shape '
    '{"categories": [{"category": ..., "confidence": ..., "evidence": ...}]}. '
    "No prose, no markdown fences, nothing else."
)

# --------------------------------------------------------------------------
# Lazy singleton client — same rationale as ollama_categorizer's
# _get_client: importing this module must not require `groq` installed,
# and classify_groq([]) must not pay any client/connection cost.
# --------------------------------------------------------------------------
_client = None


def _get_client():
    global _client
    if _client is None:
        import groq  # local import, see module-level comment above

        _client = groq.Groq(api_key=_GROQ_API_KEY, timeout=_REQUEST_TIMEOUT_SECONDS)
    return _client


def classify_groq(evidence: List[dict]) -> CategoryResult:
    """Interprets `merged_evidence` into risk categories + confidence using
    Groq's hosted API. Drop-in swap for classify_local: same signature,
    same CategoryResult shape, same privacy property (evidence only, never
    raw prompt), same boundary (never an ALLOW/SANITIZE/BLOCK decision).

    Empty evidence short-circuits to a single SAFE(1.0) finding without
    creating a client, importing `groq`, or making a network call — same
    contract as classify_local.

    Raises CategorizerUnavailableError if Groq can't be reached or returns
    a non-2xx/API error, so pipeline.py's dispatch logic can treat both
    providers' failures identically without a provider-specific except
    clause. Never raises for a malformed-but-received response — degrades
    to UNKNOWN via the shared _parse_response, same as classify_local."""
    if not evidence:
        return CategoryResult([CategoryFinding("SAFE", 1.0, "no detector evidence")])

    if not _GROQ_API_KEY:
        raise CategorizerUnavailableError("GROQ_API_KEY is not configured")

    import groq  # local import, see _get_client

    client = _get_client()
    try:
        response = client.chat.completions.create(
            model=_GROQ_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _format_evidence(evidence) + _JSON_OBJECT_INSTRUCTION},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
    except (groq.APITimeoutError, groq.APIConnectionError, groq.APIStatusError) as exc:
        raise CategorizerUnavailableError(f"Groq categorizer unavailable: {exc}") from exc

    content = response.choices[0].message.content
    if not content:
        return CategoryResult([CategoryFinding("UNKNOWN", 0.5, "categorizer returned an empty response")])

    return _parse_response(content)