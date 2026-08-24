"""
SentinelAI — python-detection service (Task 3.3: Vector search / company knowledge)

Scope boundary (per project.md Task 3.3): retrieval only. This module
finds which seeded company-knowledge documents a prompt semantically
resembles and returns them with a similarity score — it does NOT decide
whether that similarity is dangerous, and it does NOT assign severity.
That judgment belongs to Phase 4 (categorizer + deterministic risk engine),
same boundary discipline as Task 3.1 (regex) and Task 3.2 (NER).

DESIGN DECISION — why `Match` is NOT shaped like `Finding`/`Entity`
(resolves the open question Task 3.2's handover §5 flagged):
`Finding` and `Entity` are both evidence *about a span inside the prompt*
(type + value_span + confidence). A vector match is evidence of a
different kind — it says "this whole prompt resembles this whole
document", not "this substring at [12:34] is a PAN card". Forcing a
`value_span` onto a whole-prompt semantic match would be misleading (which
span would it even point to?). So `Match` carries doc-identifying fields
instead: `doc_id`, `title`, `classification`, `similarity`. Task 4.3's
merge/categorizer logic must already treat `Finding` and `Entity` as
structurally different (per Task 3.2's handover) — this adds a third,
differently-shaped evidence type to that same reconciliation, not a new
problem.

SECURITY NOTE: `Match` never includes the seeded document's raw `content`,
only `doc_id`/`title`/`classification` — consistent with the project's
"don't carry raw sensitive text through the pipeline" posture, even though
here the sensitive text belongs to the (fake) company, not the employee.
"""

import os
from dataclasses import dataclass
from typing import List, Optional, Tuple

from ..data.company_knowledge import COMPANY_DOCS

_MODEL_NAME = os.getenv("VECTOR_MODEL_NAME", "all-MiniLM-L6-v2")
_INDEX_PATH = os.getenv("FAISS_INDEX_PATH", "./data/company_index.faiss")
_META_PATH = _INDEX_PATH + ".meta.json"


@dataclass(frozen=True)
class Match:
    doc_id: str
    title: str
    classification: str  # CONFIDENTIAL | INTERNAL | PUBLIC
    similarity: float  # 0.0-1.0 cosine similarity (normalized embeddings + inner-product index)

    def to_dict(self) -> dict:
        return {
            "doc_id": self.doc_id,
            "title": self.title,
            "classification": self.classification,
            "similarity": self.similarity,
        }


# --------------------------------------------------------------------------
# Lazy singletons. Same rationale as Task 3.2's `ner_detector.py`: importing
# this module must NOT import `sentence_transformers`/`faiss` or touch disk
# — only the first real `search_company_context()` call does, keeping
# FastAPI startup fast and unit-import-safe without the model/index present.
# --------------------------------------------------------------------------
_model = None
_index = None
_index_docs: Optional[List[dict]] = None  # row i -> COMPANY_DOCS[i]-shaped dict, in index order


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(_MODEL_NAME)
    return _model


def _embed_normalized(texts: List[str]):
    """Encode `texts` and L2-normalize so FAISS inner-product search over
    them is equivalent to cosine similarity."""
    import faiss

    model = _get_model()
    vectors = model.encode(texts, convert_to_numpy=True)
    faiss.normalize_L2(vectors)
    return vectors


def _build_index():
    """Embeds COMPANY_DOCS, builds a flat inner-product FAISS index, and
    persists both the index and a JSON metadata sidecar (doc_id/title/
    classification per row, same order as the index) to disk at
    FAISS_INDEX_PATH, so a later process can load without re-embedding."""
    import json

    import faiss

    contents = [doc["content"] for doc in COMPANY_DOCS]
    vectors = _embed_normalized(contents)

    dimension = vectors.shape[1]
    index = faiss.IndexFlatIP(dimension)
    index.add(vectors)

    index_dir = os.path.dirname(_INDEX_PATH)
    if index_dir:
        os.makedirs(index_dir, exist_ok=True)
    faiss.write_index(index, _INDEX_PATH)

    docs_meta = [
        {"doc_id": d["doc_id"], "title": d["title"], "classification": d["classification"]}
        for d in COMPANY_DOCS
    ]
    with open(_META_PATH, "w", encoding="utf-8") as f:
        json.dump(docs_meta, f)

    return index, docs_meta


def _load_index() -> Tuple[object, List[dict]]:
    """Loads a previously persisted index + metadata sidecar from disk."""
    import json

    import faiss

    index = faiss.read_index(_INDEX_PATH)
    with open(_META_PATH, "r", encoding="utf-8") as f:
        docs_meta = json.load(f)
    return index, docs_meta


def _get_index() -> Tuple[object, List[dict]]:
    global _index, _index_docs
    if _index is None:
        if os.path.exists(_INDEX_PATH) and os.path.exists(_META_PATH):
            _index, _index_docs = _load_index()
        else:
            _index, _index_docs = _build_index()
    return _index, _index_docs


def search_company_context(text: str, k: int = 3) -> List[Match]:
    """Returns the top-`k` seeded company-knowledge documents most
    semantically similar to `text`, ranked by cosine similarity.

    Empty/whitespace-only input returns `[]` without loading the model or
    touching the index/disk — same short-circuit contract as Task 3.2's
    `detect_entities`."""
    if not text or not text.strip():
        return []

    index, docs_meta = _get_index()
    query_vector = _embed_normalized([text])
    k = min(k, index.ntotal)
    if k <= 0:
        return []

    scores, indices = index.search(query_vector, k)

    matches: List[Match] = []
    for score, row in zip(scores[0], indices[0]):
        if row < 0:  # FAISS pads with -1 if k > ntotal (shouldn't happen given clamp above, kept defensive)
            continue
        doc = docs_meta[row]
        matches.append(
            Match(
                doc_id=doc["doc_id"],
                title=doc["title"],
                classification=doc["classification"],
                similarity=float(score),
            )
        )
    return matches
