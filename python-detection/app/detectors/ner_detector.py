"""
SentinelAI — python-detection service (Task 3.2: NER detector)

Scope boundary (per project.md Task 3.2): entity extraction only. No
interpretation of whether an entity is "dangerous" — that judgment belongs
to the categorizer/engine stages downstream (Phase 4). Accordingly `Entity`
carries no `severity` field (unlike regex_detector.Finding, whose severity
is a static, non-judgmental property of the pattern type itself — an NER
severity would necessarily encode a risk opinion this task is not scoped
to make).

Design choice (flagged as open in Task 3.1's handover §5, resolved here):
`Entity` mirrors `Finding`'s `type` / `value_span` / `confidence` fields for
downstream merge/categorizer consistency, but drops `severity` for the
reason above. `confidence` here is the NER model's own per-entity score
(dynamic), whereas regex's confidence is static per pattern type — both are
plain floats in the same [0.0, 1.0] range so downstream code can treat them
uniformly regardless of source.

SECURITY CONSTRAINT (same as regex_detector, project.md, non-negotiable):
never log the raw matched value. Every Entity carries `value_span`
(character offsets into the original prompt) and `type`, never the entity
text itself. No `print`/`logging` call in this module may include matched
text; this is enforced by construction — the module contains no logging
calls at all.
"""

import os
from dataclasses import dataclass
from typing import List, Tuple

# --------------------------------------------------------------------------
# Entity contract — see module docstring for the design rationale vs.
# regex_detector.Finding.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Entity:
    type: str  # "PERSON" | "ORG" | "LOCATION" — project.md's 3 in-scope labels
    value_span: Tuple[int, int]
    confidence: float  # 0.0-1.0, the NER model's own per-entity score

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "value_span": list(self.value_span),  # JSON-friendly (tuple -> [start, end])
            "confidence": self.confidence,
        }


# dslim/bert-base-NER emits CoNLL-style short codes; project.md scopes this
# task to PERSON/ORG/LOCATION only, so MISC (and anything unrecognized) is
# dropped rather than guessed at.
_LABEL_MAP = {
    "PER": "PERSON",
    "ORG": "ORG",
    "LOC": "LOCATION",
}

# Task 7.5: was hardcoded despite NER_MODEL_NAME being spec'd in
# project.md's env table since Phase 0 — now actually read via os.getenv,
# same "wire it for real" precedent Task 3.3 set for VECTOR_MODEL_NAME.
_MODEL_NAME = os.getenv("NER_MODEL_NAME", "dslim/bert-base-NER")

# --------------------------------------------------------------------------
# Model loading is lazy (first-call singleton), not import-time. Two
# reasons: (1) importing `transformers`/`torch` at module import time would
# make every import of this module pay HuggingFace's load cost, including
# in contexts that never call detect_entities (e.g. a future unit test that
# only exercises regex_detector but imports the `detectors` package); (2)
# it keeps FastAPI's own startup fast — the model loads on the first
# `/analyze` call that reaches this node instead of blocking app boot.
# Trade-off (flagging, not blocking): first real request after container
# start pays the model-load latency. Not addressed here — a startup
# warm-up hook would be a FastAPI/main.py change outside this task's scope
# (python-detection/app/detectors/ only, per project.md Task 3.2).
# --------------------------------------------------------------------------
_ner_pipeline = None


def _get_ner_pipeline():
    global _ner_pipeline
    if _ner_pipeline is None:
        from transformers import pipeline as hf_pipeline  # local import, see above

        _ner_pipeline = hf_pipeline(
            "ner",
            model=_MODEL_NAME,
            aggregation_strategy="simple",  # merges wordpiece tokens into whole-entity spans
            # Forced CPU: project.md's stack ceiling is 12GB RAM / 2GB VRAM,
            # too tight to assume a usable GPU is present. Flagging per
            # Directive #5 — if a GPU is confirmed available in the actual
            # deployment target, this is a one-line change, not a redesign.
            device=-1,
        )
    return _ner_pipeline


def detect_entities(text: str) -> List[Entity]:
    """Scan `text` for PERSON/ORG/LOCATION entities using dslim/bert-base-NER.
    Returns Entities with character-offset spans only — never the matched
    text. Extraction only; no severity/danger judgment (project.md
    boundary — that's downstream).

    Empty/whitespace-only input returns an empty list without loading the
    model (avoids paying model-load cost on a no-op call)."""
    if not text or not text.strip():
        return []

    ner = _get_ner_pipeline()
    raw = ner(text)

    entities: List[Entity] = []
    for item in raw:
        mapped_type = _LABEL_MAP.get(item["entity_group"])
        if mapped_type is None:
            continue  # MISC or any other label — out of project.md's scope for 3.2
        entities.append(
            Entity(
                type=mapped_type,
                value_span=(int(item["start"]), int(item["end"])),
                confidence=float(item["score"]),
            )
        )
    return entities