"""Deterministic policy scoring for SentinelAI (Task 4.3).

This module is deliberately free of LLM and network calls. It combines
detector and categorizer categories, counts each once, then makes the only
final policy decision in the detection service.
"""

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from .categorizer.ollama_categorizer import CATEGORY_NAMES

DEFAULT_CATEGORY_WEIGHTS = {
    "CREDENTIAL_EXPOSURE": 90, "PII_EXPOSURE": 80, "FINANCIAL_DATA": 75,
    "CONFIDENTIAL_COMPANY_DATA": 70, "SOURCE_CODE_SENSITIVE": 50,
    "SECURITY_SENSITIVE_INFORMATION": 65, "INTERNAL_SYSTEM_INFORMATION": 50,
    "UNKNOWN": 15, "SAFE": 0,
}
DEFAULT_THRESHOLDS = {"safe_max": 29, "low_max": 59, "high_max": 79}

# Top-k vector retrieval is relative. Unrelated nearest neighbours must not
# become company-data evidence merely because they are in the top three.
VECTOR_SIMILARITY_FLOOR = 0.60

_REGEX_CATEGORY_MAP = {
    "PAN_CARD": "PII_EXPOSURE", "AADHAAR": "PII_EXPOSURE",
    "EMAIL": "PII_EXPOSURE", "PHONE": "PII_EXPOSURE",
    "API_KEY_STRIPE": "CREDENTIAL_EXPOSURE", "API_KEY_AWS": "CREDENTIAL_EXPOSURE",
    "API_KEY_GITHUB": "CREDENTIAL_EXPOSURE", "API_KEY_SLACK": "CREDENTIAL_EXPOSURE",
    "API_KEY_GOOGLE": "CREDENTIAL_EXPOSURE", "API_KEY_GENERIC": "CREDENTIAL_EXPOSURE",
    "JWT": "CREDENTIAL_EXPOSURE", "PRIVATE_KEY_HEADER": "CREDENTIAL_EXPOSURE",
    "DB_CONNECTION_STRING": "SECURITY_SENSITIVE_INFORMATION",
}
_VALID_CATEGORIES = frozenset(CATEGORY_NAMES)


@dataclass(frozen=True)
class RiskResult:
    score: float
    level: str
    action: str
    categories: list[str]

    def to_dict(self) -> dict:
        return {"score": self.score, "level": self.level, "action": self.action, "categories": self.categories}


def categories_from_evidence(evidence: Iterable[Mapping[str, object]]) -> set[str]:
    """Map typed metadata to categories without examining raw prompt text."""
    categories: set[str] = set()
    for item in evidence:
        if "severity" in item:
            category = _REGEX_CATEGORY_MAP.get(item.get("type"))
            if category:
                categories.add(category)
        elif "doc_id" in item:
            try:
                similarity = float(item.get("similarity", 0))
            except (TypeError, ValueError):
                similarity = 0.0
            if similarity >= VECTOR_SIMILARITY_FLOOR and item.get("classification") in {"CONFIDENTIAL", "INTERNAL"}:
                categories.add("CONFIDENTIAL_COMPANY_DATA")
        elif item.get("type") in {"PERSON", "ORG", "LOCATION"}:
            categories.add("PII_EXPOSURE")
    return categories


def normalize_categories(category_results: Sequence[Mapping[str, object]], evidence: Iterable[Mapping[str, object]] = ()) -> list[str]:
    """Deduplicate categories across detector and LLM sources."""
    categories = categories_from_evidence(evidence)
    categories.update(
        item["category"] for item in category_results
        if isinstance(item.get("category"), str) and item["category"] in _VALID_CATEGORIES
    )
    if len(categories) > 1:
        categories.discard("SAFE")
    if not categories:
        return ["SAFE"]
    return [category for category in CATEGORY_NAMES if category in categories]


def calculate_risk(category_results: Sequence[Mapping[str, object]], *, evidence: Iterable[Mapping[str, object]] = (), policy_config: Mapping[str, Mapping[str, object]] | None = None) -> RiskResult:
    """Apply policy weights once per category and return score, level, action.

    LLM confidence is not multiplied into weights: confidence describes the
    interpretation, while detector evidence is already factual metadata.
    """
    weights, thresholds = dict(DEFAULT_CATEGORY_WEIGHTS), dict(DEFAULT_THRESHOLDS)
    if policy_config:
        weights.update(policy_config.get("category_weights", {}))
        thresholds.update(policy_config.get("thresholds", {}))
    categories = normalize_categories(category_results, evidence)
    score = min(100.0, float(sum(max(0, float(weights.get(category, 0))) for category in categories)))
    safe_max, low_max, high_max = (float(thresholds[key]) for key in ("safe_max", "low_max", "high_max"))
    if not 0 <= safe_max <= low_max <= high_max <= 100:
        raise ValueError("policy thresholds must satisfy 0 <= safe_max <= low_max <= high_max <= 100")
    if score <= safe_max:
        level, action = "SAFE", "ALLOW"
    elif score <= low_max:
        level, action = "LOW", "ALLOW"
    elif score <= high_max:
        level, action = "HIGH", "SANITIZE"
    else:
        level, action = "CRITICAL", "BLOCK"
    return RiskResult(score=score, level=level, action=action, categories=categories)
