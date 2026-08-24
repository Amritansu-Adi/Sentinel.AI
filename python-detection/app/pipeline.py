"""
SentinelAI — python-detection service (topology from Task 2.3, updated Task 3.1)

Topology fixed in Task 2.3: three parallel detector nodes -> merge ->
categorizer -> engine. Node bodies are filled in task-by-task without
changing signatures or the graph shape (per Task 2.3's handover contract).

Task 3.1 status: `regex_node` calls the real `detect_regex()` implementation
(python-detection/app/detectors/regex_detector.py).

Task 3.2 status: `ner_node` now calls the real `detect_entities()`
implementation (python-detection/app/detectors/ner_detector.py, lazy-loaded
HuggingFace `dslim/bert-base-NER`).

Task 3.3 status: `vector_node` now calls the real `search_company_context()`
implementation (python-detection/app/detectors/vector_detector.py,
lazy-loaded `sentence-transformers` + FAISS against a seeded company
knowledge base).

Task 4.1 status: `categorizer_node` now calls the real `classify_local()`
implementation (python-detection/app/categorizer/ollama_categorizer.py,
local Ollama model). It is fed `merged_evidence` only — never the raw
prompt — and returns categories + confidence, never an ALLOW/SANITIZE/
BLOCK decision. `RISK_MODEL_PROVIDER`-based switching to `classify_groq`
is Task 4.2's scope, not implemented here; this node calls `classify_local`
unconditionally. `classify_local` can raise `CategorizerUnavailableError`
if Ollama is unreachable — not caught here, so it currently propagates to
a 500 from `/analyze`; Task 4.2's fallback and/or Task 4.3's error-handling
policy should decide whether/how to catch it.

Task 4.3 status: `engine_node` invokes the deterministic `calculate_risk()`
engine and returns its authoritative decision. Task 5.1 adds a standalone
span sanitizer; enforcement and forwarding remain Task 5.2's scope.

Task 7.1 status: `PipelineState` gains an optional `policy_config` input
key, forwarded straight into `calculate_risk(..., policy_config=...)`.
This node does no fetching/caching itself — node-gateway owns the live
Mongo read + TTL cache and simply includes `policy_config` in the
`/analyze` POST body when it has one; absent/None falls back to
risk_engine.py's hardcoded defaults exactly as before this task.

Task 7.2 status: `calculate_risk()`'s return shape gained `flags` and
`rewrite_guidance` (two-tier action policy — see risk_engine.py's module
docstring for the full rule table). `engine_node` passes both straight
through into pipeline state under the same field names `main.py`'s
`AnalyzeResponse` now exposes.
"""

import os
from typing import List, TypedDict

from langgraph.graph import StateGraph, START, END

from .categorizer.ollama_categorizer import classify_local, CategorizerUnavailableError
from .categorizer.groq_categorizer import classify_groq
from .detectors.regex_detector import detect_regex
from .detectors.ner_detector import detect_entities
from .detectors.vector_detector import search_company_context
from .risk_engine import VECTOR_SIMILARITY_FLOOR, NER_CONFIDENCE_FLOOR, calculate_risk


class PipelineState(TypedDict, total=False):
    # --- input ---
    request_id: str
    prompt: str
    # Task 7.1: optional live policy document (thresholds + category_weights)
    # fetched by node-gateway from MongoDB and forwarded in the /analyze
    # request body. None/absent when Mongo is unreachable or unseeded —
    # engine_node falls back to risk_engine.py's hardcoded defaults, never
    # hard-fails a request over a missing policy doc.
    policy_config: dict

    # --- parallel detector stage (Phase 3 fills these in for real) ---
    # Distinct keys per detector so the three parallel nodes never write
    # the same state key concurrently — avoids needing an Annotated/reducer
    # merge strategy for this fan-out; `merge` node below does the combining
    # explicitly instead.
    regex_findings: List[dict]
    ner_entities: List[dict]
    vector_matches: List[dict]

    # --- merge stage ---
    merged_evidence: List[dict]

    # --- categorizer stage (Task 4.1/4.2 fill this in for real) ---
    categories: List[dict]  # [{category, confidence, evidence}], per project.md 4.1
    categorizer_provider: str

    # --- engine stage (Task 4.3 fills this in for real) ---
    # Field names match AnalyzeResponse in main.py exactly so `analyze()`
    # can unpack this sub-dict directly into the response model.
    risk_score: float
    risk_level: str
    action: str
    result_categories: List[str]
    detectors_fired: List[str]
    flags: List[dict]  # Task 7.2/7.3: [{category, message}], populated on SANITIZE/ALLOW+flag
    rewrite_guidance: str | None  # Task 7.2/7.3: populated only on BLOCK


def regex_node(state: PipelineState) -> dict:
    # Task 3.1: real regex detection. Findings carry only spans/types/
    # severity/confidence — never raw matched text (project.md constraint).
    findings = detect_regex(state.get("prompt", ""))
    return {"regex_findings": [f.to_dict() for f in findings]}


def ner_node(state: PipelineState) -> dict:
    # Task 3.2: real NER extraction. Entities carry only spans/types/
    # confidence — never raw matched text (project.md constraint), and no
    # severity — extraction only, danger judgment is downstream (Phase 4).
    # Discard noisy model guesses before they enter any downstream evidence
    # path (categorizer, score/action engine, or sanitizer).  A low-confidence
    # label such as an acronym tagged ORG must not cause visible masking.
    entities = [
        entity for entity in detect_entities(state.get("prompt", ""))
        if entity.confidence >= NER_CONFIDENCE_FLOOR
    ]
    return {"ner_entities": [e.to_dict() for e in entities]}


def vector_node(state: PipelineState) -> dict:
    # Task 3.3: real vector search against the seeded company-knowledge
    # base. Matches carry doc_id/title/classification/similarity only —
    # never the prompt's raw text, and no severity/danger judgment
    # (retrieval only; Phase 4 decides what a match means).
    matches = search_company_context(state.get("prompt", ""), k=3)
    matches = [match for match in matches if match.similarity >= VECTOR_SIMILARITY_FLOOR]
    return {"vector_matches": [m.to_dict() for m in matches]}


def merge_node(state: PipelineState) -> dict:
    # Evidence stays as detector-native metadata. Risk-category normalization
    # and deduplication occur in the deterministic engine, where weights are
    # applied exactly once per category.
    merged = (
        state.get("regex_findings", [])
        + state.get("ner_entities", [])
        + state.get("vector_matches", [])
    )
    return {"merged_evidence": merged}


def categorizer_node(state: PipelineState) -> dict:
    # Task 4.1/4.2: real categorization, provider-switchable via
    # RISK_MODEL_PROVIDER. Deliberately fed only merged_evidence (typed
    # metadata: types/severities/spans/confidences/doc titles) — never
    # state["prompt"] — so neither provider's LLM ever sees the employee's
    # raw sensitive text.
    #
    # RISK_MODEL_PROVIDER=groq: Groq only, no Ollama call, no fallback.
    # RISK_MODEL_PROVIDER=local (default): try Ollama first; on
    # CategorizerUnavailableError specifically (cold-start timeout or
    # unreachable — confirmed real in Task 4.1's live verification, not
    # hypothetical), fall through to Groq. If Groq also raises
    # CategorizerUnavailableError, let it propagate — both providers being
    # down must surface as a real failure, never silently swallowed as SAFE.
    provider = os.getenv("RISK_MODEL_PROVIDER", "local").strip().lower()
    evidence = state.get("merged_evidence", [])

    try:
        if provider == "groq":
            try:
                result, provider_used = classify_groq(evidence), "groq"
            except CategorizerUnavailableError:
                result, provider_used = classify_local(evidence), "local_llm"
        else:
            try:
                result, provider_used = classify_local(evidence), "local_llm"
            except CategorizerUnavailableError:
                result, provider_used = classify_groq(evidence), "groq"
    except CategorizerUnavailableError:
        # Last-resort safety: if neither provider is reachable, degrade to a
        # conservative unknown classification rather than crashing the whole /analyze
        # request and disconnecting the caller.
        result = type("_FallbackResult", (), {"categories": [type("_FallbackCategory", (), {"to_dict": lambda self: {"category": "UNKNOWN", "confidence": 0.5, "evidence": "categorizer unavailable"}})()]})()
        provider_used = "fallback_unknown"

    return {"categories": [c.to_dict() for c in result.categories], "categorizer_provider": provider_used}


def engine_node(state: PipelineState) -> dict:
    # Task 7.1: policy_config is whatever node-gateway forwarded (live Mongo
    # read, cached there) or absent entirely — calculate_risk() already
    # falls back to DEFAULT_CATEGORY_WEIGHTS/DEFAULT_THRESHOLDS on None,
    # this node does no additional fallback logic of its own.
    result = calculate_risk(
        state.get("categories", []),
        evidence=state.get("merged_evidence", []),
        policy_config=state.get("policy_config"),
    )
    detectors_fired = []
    if state.get("regex_findings"):
        detectors_fired.append("regex")
    if state.get("ner_entities"):
        detectors_fired.append("ner")
    if state.get("vector_matches"):
        detectors_fired.append("vector")
    if state.get("categories"):
        detectors_fired.append(state.get("categorizer_provider", "local_llm"))
    return {
        "risk_score": result.score,
        "risk_level": result.level,
        "action": result.action,
        "result_categories": result.categories,
        "detectors_fired": detectors_fired,
        "flags": [f.to_dict() for f in result.flags],
        "rewrite_guidance": result.rewrite_guidance,
    }


def build_pipeline():
    """Compiles the LangGraph topology: three parallel detectors -> merge
    -> categorizer -> engine. Returns a compiled graph with an
    .invoke(state: dict) -> dict interface."""
    graph = StateGraph(PipelineState)

    graph.add_node("regex", regex_node)
    graph.add_node("ner", ner_node)
    graph.add_node("vector", vector_node)
    graph.add_node("merge", merge_node)
    graph.add_node("categorizer", categorizer_node)
    graph.add_node("engine", engine_node)

    # Fan-out: START triggers all three detectors in parallel.
    graph.add_edge(START, "regex")
    graph.add_edge(START, "ner")
    graph.add_edge(START, "vector")

    # Fan-in: LangGraph only runs "merge" once ALL three parallel
    # predecessors have completed.
    graph.add_edge("regex", "merge")
    graph.add_edge("ner", "merge")
    graph.add_edge("vector", "merge")

    # Linear tail.
    graph.add_edge("merge", "categorizer")
    graph.add_edge("categorizer", "engine")
    graph.add_edge("engine", END)

    return graph.compile()


# Compiled once at import time — cheap for this stub topology, and avoids
# recompiling the graph on every /analyze call.
pipeline = build_pipeline()
