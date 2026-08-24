"""Deterministic policy scoring + two-tier action policy for SentinelAI
(Task 4.3, redesigned Task 7.2).

This module is deliberately free of LLM and network calls.

SCORE vs ACTION (Task 7.2 — read this before changing anything below):
These are now two independent computations over the same evidence:

  * SCORE/LEVEL (`_score_categories`) — unchanged mechanism from Task 4.3.
    Category weights sum, capped at 100, mapped to SAFE/LOW/HIGH/CRITICAL
    via policy thresholds. This is a pure severity signal for the admin
    dashboard. It no longer drives the action.

  * ACTION (`determine_action`) — NEW. Rule-based over raw evidence kind,
    evaluated in fixed tier order, first match wins:
      Tier 1 (BLOCK):    a vector Match with classification == CONFIDENTIAL
                          and similarity >= VECTOR_SIMILARITY_FLOOR. Only
                          this tier may ever produce BLOCK. Wins regardless
                          of what else is present in the same request.
      Tier 2a (SANITIZE): any regex Finding or NER Entity (PERSON/ORG/
                          LOCATION) is present — i.e. anything with a
                          spannable value_span the sanitizer can mask.
      Tier 2b (ALLOW+flag): a vector Match with classification == INTERNAL
                          (similarity >= floor), OR an LLM-only category
                          (FINANCIAL_DATA/SOURCE_CODE_SENSITIVE/
                          SECURITY_SENSITIVE_INFORMATION/UNKNOWN) asserted
                          by the categorizer with no corresponding regex/
                          NER span backing it.
      Tier 3 (ALLOW):    no evidence at all.

Why this split exists: the old design let a single NER ORG hit (weight 80,
above high_max=79) BLOCK a request outright before the sanitizer ever ran,
even with zero actual sensitive content present ("here are the project
details" — no real detail, blocked anyway). Tier 2a now guarantees the
sanitizer gets a chance on anything it can actually mask; only a confirmed
match against real confidential company knowledge can still BLOCK.
"""

from dataclasses import dataclass, field
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

# `dslim/bert-base-NER` can assign PERSON/ORG/LOCATION labels to harmless
# acronyms and place names.  NER is useful only when the model is sufficiently
# certain: lower-confidence predictions are not evidence for scoring,
# categorization, sanitization, or action selection.  Keep this independent of
# the live score policy for now; it is an evidence-quality guard, not a risk
# weight.
NER_CONFIDENCE_FLOOR = 0.85

_REGEX_CATEGORY_MAP = {
    "PAN_CARD": "PII_EXPOSURE", "AADHAAR": "PII_EXPOSURE",
    "EMAIL": "PII_EXPOSURE", "PHONE": "PII_EXPOSURE",
    "API_KEY_STRIPE": "CREDENTIAL_EXPOSURE", "API_KEY_AWS": "CREDENTIAL_EXPOSURE",
    "API_KEY_GITHUB": "CREDENTIAL_EXPOSURE", "API_KEY_SLACK": "CREDENTIAL_EXPOSURE",
    "API_KEY_GOOGLE": "CREDENTIAL_EXPOSURE", "API_KEY_GENERIC": "CREDENTIAL_EXPOSURE",
    "JWT": "CREDENTIAL_EXPOSURE", "PRIVATE_KEY_HEADER": "CREDENTIAL_EXPOSURE",
    "DB_CONNECTION_STRING": "SECURITY_SENSITIVE_INFORMATION",
}
_NER_CATEGORY = "PII_EXPOSURE"  # PERSON/ORG/LOCATION all score as PII_EXPOSURE
_VALID_CATEGORIES = frozenset(CATEGORY_NAMES)

# Categories a spannable detector (regex/NER) can ever produce. An LLM
# category outside this set has no possible detector-evidence backing, so
# it always falls to Tier 2b when asserted (never masks anything, never
# blocks anything on its own).
_SPANNABLE_CATEGORIES = frozenset(_REGEX_CATEGORY_MAP.values()) | {_NER_CATEGORY}

_HUMAN_CATEGORY_LABELS = {
    "PII_EXPOSURE": "personal information",
    "CREDENTIAL_EXPOSURE": "credentials or secrets",
    "FINANCIAL_DATA": "financial data",
    "CONFIDENTIAL_COMPANY_DATA": "confidential company information",
    "INTERNAL_SYSTEM_INFORMATION": "internal system information",
    "SOURCE_CODE_SENSITIVE": "sensitive source code",
    "SECURITY_SENSITIVE_INFORMATION": "security-sensitive information",
    "UNKNOWN": "unclassified sensitive content",
}


@dataclass(frozen=True)
class Flag:
    category: str
    message: str

    def to_dict(self) -> dict:
        return {"category": self.category, "message": self.message}


@dataclass(frozen=True)
class RiskResult:
    score: float
    level: str
    action: str
    categories: list[str]
    flags: list[Flag] = field(default_factory=list)
    rewrite_guidance: str | None = None

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "level": self.level,
            "action": self.action,
            "categories": self.categories,
            "flags": [f.to_dict() for f in self.flags],
            "rewrite_guidance": self.rewrite_guidance,
        }


def _is_regex_finding(item: Mapping[str, object]) -> bool:
    return "severity" in item


def _is_vector_match(item: Mapping[str, object]) -> bool:
    return "doc_id" in item


def _is_ner_entity(item: Mapping[str, object]) -> bool:
    return not _is_regex_finding(item) and not _is_vector_match(item) and item.get("type") in {"PERSON", "ORG", "LOCATION"}


def _ner_confidence(item: Mapping[str, object]) -> float:
    try:
        return float(item.get("confidence", 0))
    except (TypeError, ValueError):
        return 0.0


def _is_actionable_ner_entity(item: Mapping[str, object]) -> bool:
    return _is_ner_entity(item) and _ner_confidence(item) >= NER_CONFIDENCE_FLOOR


def filter_actionable_evidence(evidence: Iterable[Mapping[str, object]]) -> list[Mapping[str, object]]:
    """Remove low-confidence NER predictions while preserving all other
    detector evidence.  This boundary is shared by the pipeline and direct
    engine callers so untrusted NER guesses cannot affect any decision path.
    """
    return [
        item for item in evidence
        if not _is_ner_entity(item) or _is_actionable_ner_entity(item)
    ]


def _similarity(item: Mapping[str, object]) -> float:
    try:
        return float(item.get("similarity", 0))
    except (TypeError, ValueError):
        return 0.0


def categories_from_evidence(evidence: Iterable[Mapping[str, object]]) -> set[str]:
    """Map typed metadata to score categories without examining raw prompt
    text. Used for SCORE only — see module docstring. CONFIDENTIAL and
    INTERNAL vector matches both contribute CONFIDENTIAL_COMPANY_DATA
    severity weight; which tier of ACTION they trigger is decided
    separately in `determine_action`."""
    categories: set[str] = set()
    for item in evidence:
        if _is_regex_finding(item):
            category = _REGEX_CATEGORY_MAP.get(item.get("type"))
            if category:
                categories.add(category)
        elif _is_vector_match(item):
            if _similarity(item) >= VECTOR_SIMILARITY_FLOOR and item.get("classification") in {"CONFIDENTIAL", "INTERNAL"}:
                categories.add("CONFIDENTIAL_COMPANY_DATA")
        elif _is_actionable_ner_entity(item):
            categories.add(_NER_CATEGORY)
    return categories


def normalize_categories(category_results: Sequence[Mapping[str, object]], evidence: Iterable[Mapping[str, object]] = ()) -> list[str]:
    """Deduplicate categories across detector and LLM sources. SCORE input
    only — unchanged from Task 4.3."""
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


def _score_categories(categories: list[str], weights: Mapping[str, object], thresholds: Mapping[str, object]) -> tuple[float, str]:
    score = min(100.0, float(sum(max(0, float(weights.get(category, 0))) for category in categories)))
    safe_max, low_max, high_max = (float(thresholds[key]) for key in ("safe_max", "low_max", "high_max"))
    if not 0 <= safe_max <= low_max <= high_max <= 100:
        raise ValueError("policy thresholds must satisfy 0 <= safe_max <= low_max <= high_max <= 100")
    if score <= safe_max:
        level = "SAFE"
    elif score <= low_max:
        level = "LOW"
    elif score <= high_max:
        level = "HIGH"
    else:
        level = "CRITICAL"
    return score, level


def _rewrite_guidance_for_block() -> str:
    # Category-level only — never names or quotes the matched document
    # (project.md §3.5 constraint, verified by Task 7's test suite).
    return (
        "This message appears to reference confidential company, project, "
        "or team information. Please remove any internal project names, "
        "team/client details, or proprietary specifics and rephrase your "
        "request in general terms before resending."
    )


def determine_action(
    category_results: Sequence[Mapping[str, object]],
    evidence: Sequence[Mapping[str, object]],
) -> tuple[str, list[Flag], str | None]:
    """Two-tier action policy (Task 7.2). Returns (action, flags,
    rewrite_guidance). Evaluated in fixed order, first match wins —
    Tier 1 always wins over everything else, regardless of what other
    evidence is also present in the same request."""
    evidence = list(evidence)

    # --- Tier 1: strict block -------------------------------------------------
    confidential_matches = [
        item for item in evidence
        if _is_vector_match(item) and item.get("classification") == "CONFIDENTIAL" and _similarity(item) >= VECTOR_SIMILARITY_FLOOR
    ]
    if confidential_matches:
        return "BLOCK", [], _rewrite_guidance_for_block()

    # --- Tier 2a: mask & allow (spannable regex/NER evidence) -----------------
    flags: list[Flag] = []
    spannable_categories: set[str] = set()
    for item in evidence:
        if _is_regex_finding(item):
            category = _REGEX_CATEGORY_MAP.get(item.get("type"), "UNKNOWN")
            spannable_categories.add(category)
        elif _is_actionable_ner_entity(item):
            spannable_categories.add(_NER_CATEGORY)

    if spannable_categories:
        for category in sorted(spannable_categories):
            label = _HUMAN_CATEGORY_LABELS.get(category, category)
            flags.append(Flag(category=category, message=f"Masked {label} before forwarding this message."))
        return "SANITIZE", flags, None

    # --- Tier 2b: flag & allow (non-spannable evidence) ------------------------
    internal_matches = [
        item for item in evidence
        if _is_vector_match(item) and item.get("classification") == "INTERNAL" and _similarity(item) >= VECTOR_SIMILARITY_FLOOR
    ]
    for _match in internal_matches:
        flags.append(Flag(
            category="CONFIDENTIAL_COMPANY_DATA",
            message="This message resembles internal company documentation. No content was removed; please confirm it's appropriate to share.",
        ))

    llm_only_categories = {
        item["category"] for item in category_results
        if isinstance(item.get("category"), str)
        and item["category"] in _VALID_CATEGORIES
        and item["category"] != "SAFE"
        and item["category"] not in _SPANNABLE_CATEGORIES
    }
    for category in sorted(llm_only_categories):
        label = _HUMAN_CATEGORY_LABELS.get(category, category)
        flags.append(Flag(category=category, message=f"This message may contain {label}. No content was removed; please review before sending."))

    if flags:
        return "ALLOW", flags, None

    # --- Tier 3: safe -----------------------------------------------------------
    return "ALLOW", [], None


def calculate_risk(
    category_results: Sequence[Mapping[str, object]],
    *,
    evidence: Iterable[Mapping[str, object]] = (),
    policy_config: Mapping[str, Mapping[str, object]] | None = None,
) -> RiskResult:
    """Computes SCORE/LEVEL (weighted-sum severity, policy-configurable —
    Task 7.1 wires live `policy_config` from MongoDB) and ACTION (two-tier
    evidence-kind rule table, Task 7.2) as independent outputs over the
    same evidence. A request can legitimately be CRITICAL severity with a
    SANITIZE action at the same time — that means "serious exposure that
    was successfully masked", which is intentional under this policy.

    LLM confidence is not multiplied into weights: confidence describes the
    interpretation, while detector evidence is already factual metadata.
    """
    weights, thresholds = dict(DEFAULT_CATEGORY_WEIGHTS), dict(DEFAULT_THRESHOLDS)
    if policy_config:
        weights.update(policy_config.get("category_weights", {}))
        thresholds.update(policy_config.get("thresholds", {}))

    evidence = filter_actionable_evidence(evidence)
    categories = normalize_categories(category_results, evidence)
    score, level = _score_categories(categories, weights, thresholds)
    action, flags, rewrite_guidance = determine_action(category_results, evidence)

    return RiskResult(score=score, level=level, action=action, categories=categories, flags=flags, rewrite_guidance=rewrite_guidance)
