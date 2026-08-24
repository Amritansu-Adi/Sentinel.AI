"""Deterministic, span-only prompt sanitization (Task 5.1).

The sanitizer receives detector metadata, never runs another detector, and
never asks an LLM to rewrite text.  Consequently it can only redact content
whose character offsets were already identified by the regex or NER stages.
"""

from collections.abc import Mapping, Sequence


_PLACEHOLDERS = {
    "PAN_CARD": "[PAN_CARD]",
    "AADHAAR": "[AADHAAR_NUMBER]",
    "EMAIL": "[EMAIL_ADDRESS]",
    "PHONE": "[PHONE_NUMBER]",
    "API_KEY_STRIPE": "[API_KEY]",
    "API_KEY_AWS": "[API_KEY]",
    "API_KEY_GITHUB": "[API_KEY]",
    "API_KEY_SLACK": "[API_KEY]",
    "API_KEY_GOOGLE": "[API_KEY]",
    "API_KEY_GENERIC": "[API_KEY]",
    "JWT": "[JWT_TOKEN]",
    "PRIVATE_KEY_HEADER": "[PRIVATE_KEY]",
    "DB_CONNECTION_STRING": "[DATABASE_CONNECTION_STRING]",
    "PERSON": "[PERSON_NAME]",
    "ORG": "[ORGANIZATION]",
    "LOCATION": "[LOCATION]",
}

# When detector spans overlap, preserve the more security-specific token.
# Regex detectors are ordered above NER labels; lower values have priority.
_TYPE_PRIORITY = {name: index for index, name in enumerate(_PLACEHOLDERS)}
_DEFAULT_PLACEHOLDER = "[REDACTED_SENSITIVE_DATA]"


def _as_mapping(finding: object) -> Mapping[str, object] | None:
    if isinstance(finding, Mapping):
        return finding
    to_dict = getattr(finding, "to_dict", None)
    candidate = to_dict() if callable(to_dict) else None
    return candidate if isinstance(candidate, Mapping) else None


def _valid_span(value: object, text_length: int) -> tuple[int, int] | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 2:
        return None
    start, end = value
    if isinstance(start, bool) or isinstance(end, bool) or not isinstance(start, int) or not isinstance(end, int):
        return None
    if start < 0 or end > text_length or start >= end:
        return None
    return start, end


def sanitize(text: str, findings: Sequence[object]) -> str:
    """Replace identified regex/NER spans with stable placeholder tokens.

    Invalid metadata is ignored rather than guessed from the input text.  For
    an overlapping group, the entire union is redacted once, using the most
    specific available placeholder; this guarantees no part of either
    detected value is retained. Vector matches have no prompt span and are
    therefore intentionally not sanitizable in this task.
    """
    if not text or not findings:
        return text

    spans: list[tuple[int, int, str, int]] = []
    for raw_finding in findings:
        finding = _as_mapping(raw_finding)
        if finding is None:
            continue
        span = _valid_span(finding.get("value_span"), len(text))
        finding_type = finding.get("type")
        if span is None or not isinstance(finding_type, str):
            continue
        placeholder = _PLACEHOLDERS.get(finding_type, _DEFAULT_PLACEHOLDER)
        spans.append((*span, placeholder, _TYPE_PRIORITY.get(finding_type, len(_TYPE_PRIORITY))))

    if not spans:
        return text

    spans.sort(key=lambda item: (item[0], item[1], item[3]))
    replacements: list[tuple[int, int, str]] = []
    start, end, placeholder, priority = spans[0]
    for next_start, next_end, next_placeholder, next_priority in spans[1:]:
        if next_start < end:
            end = max(end, next_end)
            if next_priority < priority:
                placeholder, priority = next_placeholder, next_priority
            continue
        replacements.append((start, end, placeholder))
        start, end, placeholder, priority = next_start, next_end, next_placeholder, next_priority
    replacements.append((start, end, placeholder))

    # Reverse order keeps all original detector offsets valid.
    sanitized = text
    for start, end, placeholder in reversed(replacements):
        sanitized = sanitized[:start] + placeholder + sanitized[end:]
    return sanitized
