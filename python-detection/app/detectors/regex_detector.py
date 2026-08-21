"""
SentinelAI — python-detection service (Task 3.1: Regex detector)

Scope boundary (per project.md Task 3.1): pattern-matching only. No NER,
no vector search, no interpretation of severity beyond a fixed static
table. This module never decides ALLOW/SANITIZE/BLOCK — it only produces
Findings for the merge/categorizer/engine stages downstream.

SECURITY CONSTRAINT (explicit in project.md, non-negotiable): never log
the raw matched value. Every Finding carries `value_span` (character
offsets into the original prompt) and `type`, never the matched
substring itself. No `print`/`logging` call in this module may include
match.group(); this is enforced by construction — the module contains no
logging calls at all.
"""

import re
from dataclasses import dataclass
from typing import List, Pattern, Tuple

# --------------------------------------------------------------------------
# Finding contract — matches project.md §5 Task 3.1:
#   [{type, value_span, severity, confidence}]
# `value_span` is a (start, end) character-offset tuple, never the raw text.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    type: str
    value_span: Tuple[int, int]
    severity: str  # LOW | MEDIUM | HIGH | CRITICAL — static per pattern type
    confidence: float  # 0.0-1.0, static per pattern type (regex is deterministic)

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "value_span": list(self.value_span),  # JSON-friendly (tuple -> [start, end])
            "severity": self.severity,
            "confidence": self.confidence,
        }


# --------------------------------------------------------------------------
# Pattern table. Each entry: (type_name, compiled_pattern, severity, confidence).
# Compiled once at import time — this runs on every /analyze call, so
# per-call re.compile() would be wasted work.
# --------------------------------------------------------------------------

# PAN (India Permanent Account Number): 5 letters, 4 digits, 1 letter.
_PAN = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")

# Aadhaar (India national ID): 12 digits, optionally space/hyphen grouped 4-4-4.
_AADHAAR = re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b")

# Email — practical RFC-5322-ish pattern, not the full spec.
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

# Phone — India-biased (project context) but tolerant of a leading +CC and
# common separators; anchored to 10 core digits to avoid swallowing PAN/Aadhaar.
_PHONE = re.compile(r"(?<!\d)(?:\+?\d{1,3}[\s-]?)?[6-9]\d{9}(?!\d)")

# API keys — common vendor-prefixed token shapes (Stripe, AWS, GitHub, Slack,
# Google, generic "sk-"/"key-" style). Kept as named alternatives so
# `type` can be more specific than a single generic "API_KEY" bucket.
_API_KEY_PATTERNS = [
    ("API_KEY_STRIPE", re.compile(r"\bsk_(?:live|test)_[A-Za-z0-9]{16,}\b")),
    ("API_KEY_AWS", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("API_KEY_GITHUB", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("API_KEY_SLACK", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("API_KEY_GOOGLE", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("API_KEY_GENERIC", re.compile(r"\b(?:sk|key|api)-[A-Za-z0-9]{20,}\b")),
]

# JWT — strictly 3 base64url segments separated by dots, each segment
# non-empty, to avoid matching arbitrary dotted base64-looking text.
_JWT = re.compile(r"\b[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")

# Private key headers — PEM-style block openers. Presence of the header
# alone is sufficient evidence; we don't need to match the full body.
_PRIVATE_KEY_HEADER = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----"
)

# DB connection strings — common scheme://user:pass@host[:port]/db shapes.
_DB_CONN_STRING = re.compile(
    r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp):\/\/"
    r"[^\s:/@]+:[^\s:/@]+@[^\s/]+(?:\/[^\s]*)?",
    re.IGNORECASE,
)

# type -> (severity, confidence). Regex matches are deterministic (no model
# uncertainty), so confidence is high but not 1.0 — reserves headroom for
# known false-positive-prone types (Aadhaar/phone overlap with other
# 10-12 digit sequences).
_SEVERITY_CONFIDENCE = {
    "PAN_CARD": ("HIGH", 0.95),
    "AADHAAR": ("HIGH", 0.85),
    "EMAIL": ("LOW", 0.97),
    "PHONE": ("LOW", 0.80),
    "API_KEY_STRIPE": ("CRITICAL", 0.98),
    "API_KEY_AWS": ("CRITICAL", 0.98),
    "API_KEY_GITHUB": ("CRITICAL", 0.98),
    "API_KEY_SLACK": ("CRITICAL", 0.95),
    "API_KEY_GOOGLE": ("CRITICAL", 0.95),
    "API_KEY_GENERIC": ("HIGH", 0.75),
    "JWT": ("HIGH", 0.70),  # lower confidence — shape overlaps other dotted tokens
    "PRIVATE_KEY_HEADER": ("CRITICAL", 0.99),
    "DB_CONNECTION_STRING": ("CRITICAL", 0.95),
}


def _scan(pattern: Pattern, type_name: str, text: str) -> List[Finding]:
    severity, confidence = _SEVERITY_CONFIDENCE[type_name]
    return [
        Finding(
            type=type_name,
            value_span=(m.start(), m.end()),
            severity=severity,
            confidence=confidence,
        )
        for m in pattern.finditer(text)
    ]


def _dedupe_overlaps(findings: List[Finding]) -> List[Finding]:
    """When two findings' spans overlap (e.g. a DB connection string's
    embedded credentials also loosely matching a generic API key pattern),
    keep the one with higher severity, then higher confidence, then the
    wider span (more specific match wins). Non-overlapping findings are
    all kept regardless of type."""
    if not findings:
        return []

    severity_rank = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
    # Sort by span start so we can do a single linear overlap pass.
    ordered = sorted(findings, key=lambda f: (f.value_span[0], f.value_span[1]))

    kept: List[Finding] = []
    for current in ordered:
        overlapped_index = None
        for i, existing in enumerate(kept):
            if current.value_span[0] < existing.value_span[1] and current.value_span[1] > existing.value_span[0]:
                overlapped_index = i
                break
        if overlapped_index is None:
            kept.append(current)
            continue

        existing = kept[overlapped_index]
        current_key = (
            severity_rank[current.severity],
            current.confidence,
            current.value_span[1] - current.value_span[0],
        )
        existing_key = (
            severity_rank[existing.severity],
            existing.confidence,
            existing.value_span[1] - existing.value_span[0],
        )
        if current_key > existing_key:
            kept[overlapped_index] = current
        # else: keep existing, drop current

    return kept


def detect_regex(text: str) -> List[Finding]:
    """Scan `text` for PAN, Aadhaar, email, phone, API keys, JWTs, private
    key headers, and DB connection strings. Returns deduplicated Findings
    with character-offset spans only — never the matched substring.

    Empty/whitespace-only input returns an empty list; this function never
    raises on malformed/adversarial input (regex scanning is total over
    any str)."""
    if not text:
        return []

    findings: List[Finding] = []
    findings += _scan(_PAN, "PAN_CARD", text)
    findings += _scan(_AADHAAR, "AADHAAR", text)
    findings += _scan(_EMAIL, "EMAIL", text)
    findings += _scan(_PHONE, "PHONE", text)
    for type_name, pattern in _API_KEY_PATTERNS:
        findings += _scan(pattern, type_name, text)
    findings += _scan(_JWT, "JWT", text)
    findings += _scan(_PRIVATE_KEY_HEADER, "PRIVATE_KEY_HEADER", text)
    findings += _scan(_DB_CONN_STRING, "DB_CONNECTION_STRING", text)

    return _dedupe_overlaps(findings)
