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

`engine_node` remains a stub matching Task 2.1's original fixed response
contract (Task 4.3) — it does not yet consume `regex_findings`/
`ner_entities`/`vector_matches`/`categories`, so `/analyze`'s external
response is still byte-identical to before; only the internal state keys
now hold real data for downstream tasks to consume.
"""

import os
from typing import List, TypedDict

from langgraph.graph import StateGraph, START, END

from .categorizer.ollama_categorizer import classify_local, CategorizerUnavailableError
from .categorizer.groq_categorizer import classify_groq
from .detectors.regex_detector import detect_regex
from .detectors.ner_detector import detect_entities
from .detectors.vector_detector import search_company_context
from .risk_engine import VECTOR_SIMILARITY_FLOOR, calculate_risk


class PipelineState(TypedDict, total=False):
    # --- input ---
    request_id: str
    prompt: str

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


def regex_node(state: PipelineState) -> dict:
    # Task 3.1: real regex detection. Findings carry only spans/types/
    # severity/confidence — never raw matched text (project.md constraint).
    findings = detect_regex(state.get("prompt", ""))
    return {"regex_findings": [f.to_dict() for f in findings]}


def ner_node(state: PipelineState) -> dict:
    # Task 3.2: real NER extraction. Entities carry only spans/types/
    # confidence — never raw matched text (project.md constraint), and no
    # severity — extraction only, danger judgment is downstream (Phase 4).
    entities = detect_entities(state.get("prompt", ""))
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
    # Stub only — real merge logic (Phase 4) will normalize/dedupe across
    # detectors to avoid double-counting the same category. Here it just
    # concatenates whatever the (currently always-empty) stub lists hold,
    # so the shape is exercised without inventing real merge semantics.
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
    provider = os.getenv("RISK_MODEL_PROVIDER", "local")
    evidence = state.get("merged_evidence", [])

    if provider == "groq":
        result, provider_used = classify_groq(evidence), "groq"
    else:
        try:
            result, provider_used = classify_local(evidence), "local_llm"
        except CategorizerUnavailableError:
            result, provider_used = classify_groq(evidence), "groq"

    return {"categories": [c.to_dict() for c in result.categories], "categorizer_provider": provider_used}


def engine_node(state: PipelineState) -> dict:
    result = calculate_risk(state.get("categories", []), evidence=state.get("merged_evidence", []))
    detectors_fired = []
    if state.get("regex_findings"):
        detectors_fired.append("regex")
    if state.get("ner_entities"):
        detectors_fired.append("ner")
    if state.get("vector_matches"):
        detectors_fired.append("vector")
    if state.get("categories"):
        detectors_fired.append(state.get("categorizer_provider", "local_llm"))
    # Stub only — Task 4.3 implements calculate_risk(category_results).
    # Values here intentionally match Task 2.1's original hardcoded
    # AnalyzeResponse defaults exactly, preserving /analyze's contract.
    return {
        "risk_score": result.score,
        "risk_level": result.level,
        "action": result.action,
        "result_categories": result.categories,
        "detectors_fired": detectors_fired,
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
