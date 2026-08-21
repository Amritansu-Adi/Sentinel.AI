"""
SentinelAI — python-detection service (Task 4.1: Local LLM categorizer, Ollama)

Scope boundary (per project.md Task 4.1): interpret already-extracted
evidence into risk CATEGORIES + confidence only. This module never
outputs, computes, or implies an ALLOW/SANITIZE/BLOCK decision — that is
the deterministic risk engine's exclusive authority (Task 4.3, per
project.md's non-negotiable architectural principle: "No LLM in this
system is allowed to make the final security decision").

CRITICAL PRIVACY/ARCHITECTURE PROPERTY: this module is never given the
raw prompt text. `classify_local()` only receives `merged_evidence` —
the Finding/Entity/Match dicts already produced by Task 3.1/3.2/3.3,
which themselves carry no raw matched substrings (project.md's
"never log/carry the raw value" constraint). This means even a local LLM
call never sees an employee's actual PII/credentials/confidential text —
it reasons purely over typed metadata (types, severities, spans-as-
offsets, confidences, company-doc titles/classifications). This is
enforced by construction: nothing in this module ever reads a `prompt`
key from anywhere.

Evidence shape asymmetry (flagged across Task 3.2 and 3.3's handovers,
resolved here): `merged_evidence` mixes three structurally different
dicts — regex `Finding` (has `severity`), NER `Entity` (has `value_span`,
no `severity`), and vector `Match` (has `doc_id`, no `value_span`). This
module distinguishes them by key presence (see `_describe_evidence_item`)
and renders each into one readable line for the LLM prompt. This is a
presentation-layer reconciliation only — it does NOT solve Task 4.3's
separate problem of numerically weighting three differently-shaped
evidence kinds in the deterministic risk engine.

Provider contract: `classify_local(evidence) -> CategoryResult` is the
fixed interface `classify_groq(evidence) -> CategoryResult`
(python-detection/app/categorizer/groq_categorizer.py, Task 4.2) matches
exactly — a drop-in swap dispatched by `pipeline.py`'s `categorizer_node`
via `RISK_MODEL_PROVIDER`, with `CategorizerUnavailableError` from this
module triggering Groq fallback when `RISK_MODEL_PROVIDER=local`.
"""

import json
import os
from dataclasses import dataclass
from typing import List

# --------------------------------------------------------------------------
# Fixed category set — verbatim from project.md Task 4.1. Nothing outside
# this tuple is a valid `category` value; anything else the model emits is
# dropped (see _parse_response) rather than trusted.
# --------------------------------------------------------------------------
CATEGORY_NAMES = (
    "PII_EXPOSURE",
    "CREDENTIAL_EXPOSURE",
    "FINANCIAL_DATA",
    "CONFIDENTIAL_COMPANY_DATA",
    "INTERNAL_SYSTEM_INFORMATION",
    "SOURCE_CODE_SENSITIVE",
    "SECURITY_SENSITIVE_INFORMATION",
    "SAFE",
    "UNKNOWN",
)
_CATEGORY_SET = frozenset(CATEGORY_NAMES)

# Both env vars already existed in project.md's Phase-0 env table; this is
# the first task to actually read them (same "wire it for real" precedent
# Task 3.3 set for VECTOR_MODEL_NAME/FAISS_INDEX_PATH).
_OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
_OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b-instruct-q4_K_M")

# Not in project.md's env var table — a hardcoded operational default
# rather than a new config surface (Directive #5: don't invent config
# project.md didn't ask for). Bumped 30->60 in Task 4.2: live docker-compose
# testing during 4.1 confirmed qwen2.5:1.5b-instruct-q4_K_M takes 35-40s on
# cold start, which tripped the old 30s ceiling on first request.
_REQUEST_TIMEOUT_SECONDS = 60

# temperature=0 for reproducibility — project.md §6 explicitly tests that
# "same evidence input produces same category shape" (4.1/4.2 contract
# test), which a nonzero-temperature categorizer would make flaky.
_MODEL_OPTIONS = {"temperature": 0}

_SYSTEM_PROMPT = f"""You are a security-evidence categorizer inside SentinelAI, an internal LLM-prompt inspection gateway.

You do NOT see the user's original prompt text. You only see a list of evidence items already extracted by upstream detectors (regex pattern matches, named-entity recognition, and semantic matches against a company knowledge base). Every evidence item is metadata only — a type, a severity/confidence, a character span, or a matched document's title/classification. It never contains the actual sensitive text.

Your only job: read the evidence and decide which of the following FIXED categories it indicates, with a confidence (0.0-1.0) and a short evidence-based rationale for each. Use ONLY these category names, exactly as spelled:
- PII_EXPOSURE: personal data such as names, emails, phone numbers, or national ID numbers may be present.
- CREDENTIAL_EXPOSURE: API keys, tokens, JWTs, or private key material may be present.
- FINANCIAL_DATA: financial account numbers, payment details, or similar financial data may be present.
- CONFIDENTIAL_COMPANY_DATA: content semantically resembles a confidential or internal company document.
- INTERNAL_SYSTEM_INFORMATION: internal system, infrastructure, or architecture details may be present.
- SOURCE_CODE_SENSITIVE: proprietary source code or code-adjacent secrets may be present.
- SECURITY_SENSITIVE_INFORMATION: security-relevant material (e.g. database connection strings) may be present.
- SAFE: the evidence indicates no meaningful risk.
- UNKNOWN: evidence is present but its risk category cannot be confidently determined.

Rules you must follow exactly:
1. You NEVER decide or output ALLOW, SANITIZE, or BLOCK, and you never mention those words. A separate deterministic system makes that decision — you only output categories, confidences, and rationale.
2. Only reason about the evidence items given to you below. Never invent evidence that was not provided.
3. Evidence may justify more than one category at once (e.g. both PII_EXPOSURE and CREDENTIAL_EXPOSURE) — include every category that applies, each with its own confidence.
4. If evidence is present but does not clearly fit any category above, use UNKNOWN rather than guessing.
5. Output ONLY the JSON object matching the given schema. No prose, no markdown fences, nothing outside the JSON.

Valid category values: {", ".join(CATEGORY_NAMES)}."""

# Passed as `format=` to force schema-constrained decoding (Ollama
# structured outputs) rather than relying on prompt instructions alone —
# still defensively re-validated in _parse_response since constrained
# decoding is a strong hint, not a proof, across all model backends.
_RESPONSE_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "categories": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "enum": list(CATEGORY_NAMES)},
                    "confidence": {"type": "number"},
                    "evidence": {"type": "string"},
                },
                "required": ["category", "confidence", "evidence"],
            },
        }
    },
    "required": ["categories"],
}


@dataclass(frozen=True)
class CategoryFinding:
    category: str  # one of CATEGORY_NAMES
    confidence: float  # 0.0-1.0
    evidence: str  # short rationale, generated by the model from typed evidence only

    def to_dict(self) -> dict:
        return {"category": self.category, "confidence": self.confidence, "evidence": self.evidence}


@dataclass(frozen=True)
class CategoryResult:
    categories: List[CategoryFinding]

    def to_dict(self) -> dict:
        return {"categories": [c.to_dict() for c in self.categories]}


class CategorizerError(Exception):
    """Base class for classify_local() failures."""


class CategorizerUnavailableError(CategorizerError):
    """Raised when Ollama could not be reached or errored at the transport/
    HTTP level (connection refused, DNS failure, timeout, non-2xx
    response) — i.e. the categorizer never got a usable response at all.

    Deliberately distinct from a malformed-but-received response (which
    _parse_response degrades to an UNKNOWN CategoryFinding instead of
    raising — see _parse_response's docstring for the rationale). Task
    4.2's Groq fallback should catch this specific exception to trigger
    provider failover, without also masking output-shape bugs as if they
    were connectivity problems.
    """


# --------------------------------------------------------------------------
# Lazy singleton client — same rationale as Task 3.2/3.3's lazy model/index
# loading: importing this module must not require `ollama` installed or
# reachable, and must not pay any connection cost until a real
# classify_local() call with non-empty evidence happens.
# --------------------------------------------------------------------------
_client = None


def _get_client():
    global _client
    if _client is None:
        import ollama  # local import, see module-level comment above

        _client = ollama.Client(host=_OLLAMA_BASE_URL, timeout=_REQUEST_TIMEOUT_SECONDS)
    return _client


def _describe_evidence_item(item: dict) -> str:
    """Renders one merged_evidence dict into a single readable line,
    branching on key presence to distinguish Finding/Entity/Match (see
    module docstring's "Evidence shape asymmetry" section). Falls back to
    a generic key dump for any future evidence shape this wasn't written
    against, rather than raising — a new detector shape should degrade
    gracefully here, not break categorization."""
    span = item.get("value_span")
    span_str = f"[{span[0]},{span[1]}]" if isinstance(span, (list, tuple)) and len(span) == 2 else "n/a"

    if "severity" in item:  # regex Finding
        return (
            f"- source=REGEX type={item.get('type')} severity={item.get('severity')} "
            f"confidence={item.get('confidence')} span={span_str}"
        )
    if "doc_id" in item:  # vector Match
        return (
            f"- source=COMPANY_KNOWLEDGE_MATCH doc_id={item.get('doc_id')} "
            f"title={item.get('title')!r} classification={item.get('classification')} "
            f"similarity={item.get('similarity')}"
        )
    if "value_span" in item:  # NER Entity
        return f"- source=NER type={item.get('type')} confidence={item.get('confidence')} span={span_str}"

    return f"- source=UNKNOWN fields={sorted(item.keys())}"


def _format_evidence(evidence: List[dict]) -> str:
    lines = [_describe_evidence_item(item) for item in evidence]
    return "Evidence items:\n" + "\n".join(lines)


def _parse_response(raw_content: str) -> CategoryResult:
    """Defensively parses/validates the model's JSON output.

    Design choice: a malformed-but-received response degrades to a single
    UNKNOWN CategoryFinding rather than raising. UNKNOWN already exists in
    the fixed category set specifically to mean "evidence exists but we
    can't confidently categorize it" — an unparseable model response is
    exactly that case, just at the categorizer level instead of the
    evidence level. This is NOT the same failure mode as
    CategorizerUnavailableError (Ollama unreachable): here the model DID
    respond, so silently masking it as SAFE would be the actual bug (that
    would make a real evidence signal vanish); UNKNOWN preserves "this
    needs attention" for the deterministic engine without the categorizer
    pretending to know something it doesn't.
    """
    try:
        parsed = json.loads(raw_content)
    except (json.JSONDecodeError, TypeError):
        return CategoryResult([CategoryFinding("UNKNOWN", 0.5, "categorizer response was not valid JSON")])

    if not isinstance(parsed, dict) or not isinstance(parsed.get("categories"), list):
        return CategoryResult(
            [CategoryFinding("UNKNOWN", 0.5, "categorizer response did not match the expected schema")]
        )

    findings: List[CategoryFinding] = []
    for raw_item in parsed["categories"]:
        if not isinstance(raw_item, dict):
            continue
        category = raw_item.get("category")
        if category not in _CATEGORY_SET:
            continue  # schema/enum already constrains this at generation time; re-checked defensively here
        try:
            confidence = float(raw_item.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))
        evidence_text = str(raw_item.get("evidence", ""))[:500]  # cap runaway output
        findings.append(CategoryFinding(category=category, confidence=confidence, evidence=evidence_text))

    if not findings:
        return CategoryResult(
            [CategoryFinding("UNKNOWN", 0.5, "categorizer returned no valid category entries")]
        )
    return CategoryResult(findings)


def classify_local(evidence: List[dict]) -> CategoryResult:
    """Interprets `merged_evidence` (regex Findings + NER Entities + vector
    Matches, as dicts) into risk categories + confidence, using a local
    Ollama model. Never sees raw prompt text (see module docstring) and
    never outputs an ALLOW/SANITIZE/BLOCK decision (project.md boundary —
    that's Task 4.3's deterministic engine, exclusively).

    Empty evidence short-circuits to a single SAFE(1.0) finding without
    creating a client or making a network call — same "no work for a
    no-op input" contract as detect_entities/search_company_context.

    Raises CategorizerUnavailableError if Ollama can't be reached at all.
    Never raises for a malformed-but-received response — see
    _parse_response's docstring."""
    if not evidence:
        return CategoryResult([CategoryFinding("SAFE", 1.0, "no detector evidence")])

    import httpx  # local import, same lazy-dependency discipline as ollama below
    import ollama  # local import, see module-level comment near _get_client

    client = _get_client()
    try:
        response = client.chat(
            model=_OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _format_evidence(evidence)},
            ],
            format=_RESPONSE_JSON_SCHEMA,
            options=_MODEL_OPTIONS,
        )
    except ConnectionError as exc:
        # ollama.Client wraps httpx.ConnectError into the builtin
        # ConnectionError itself (see ollama._client.Client._request_raw).
        raise CategorizerUnavailableError(f"Could not reach Ollama at {_OLLAMA_BASE_URL}") from exc
    except httpx.TimeoutException as exc:
        raise CategorizerUnavailableError(f"Ollama request timed out after {_REQUEST_TIMEOUT_SECONDS}s") from exc
    except ollama.ResponseError as exc:
        # Ollama reached, but returned a non-2xx (e.g. model not pulled).
        raise CategorizerUnavailableError(f"Ollama returned an error: {exc}") from exc

    # response.message is required by ollama's ChatResponse type; only
    # its .content is Optional[str] (e.g. a model that returns nothing).
    content = response.message.content
    if not content:
        return CategoryResult([CategoryFinding("UNKNOWN", 0.5, "categorizer returned an empty response")])

    return _parse_response(content)