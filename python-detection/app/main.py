"""
SentinelAI — python-detection service (Task 2.1: FastAPI scaffold + contract)

Scope boundary (per project.md Task 2.1): this is the internal detection
service's public contract only. `/analyze` returns a FIXED dummy response —
no regex/NER/vector/categorizer/engine logic lives here yet. Those land in
Phase 3 (detectors), Task 4.1/4.2 (categorizer), and Task 4.3 (deterministic
risk engine). request_id/prompt are accepted and validated per the contract
but are intentionally not used to compute anything in this task.
"""

from typing import List, Literal

from fastapi import FastAPI
from pydantic import BaseModel, Field

from .pipeline import pipeline

app = FastAPI(
    title="SentinelAI Detection Service",
    description="Internal-only service. Not client-facing — called by node-gateway.",
    version="0.1.0",
)


class AnalyzeRequest(BaseModel):
    request_id: str
    prompt: str


class AnalyzeResponse(BaseModel):
    # Mirrors node-gateway's Mongoose `Request` schema (src/models/Request.js)
    # field-for-field so the two sides of the contract can't silently drift:
    # risk_score: Number 0-100, risk_level/action: fixed enums, both list fields.
    risk_score: float = Field(..., ge=0, le=100)
    risk_level: Literal["SAFE", "LOW", "HIGH", "CRITICAL"]
    action: Literal["ALLOW", "SANITIZE", "BLOCK"]
    categories: List[str]
    detectors_fired: List[str]


@app.get("/health")
def health():
    # Mirrors node-gateway's /health shape/intent (src/index.js) — liveness
    # only, no downstream dependency checks.
    return {"status": "ok", "service": "python-detection"}


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(payload: AnalyzeRequest) -> AnalyzeResponse:
    # Task 2.3: now runs through the LangGraph skeleton (regex/ner/vector ->
    # merge -> categorizer -> engine), all still stub nodes per Task 2.3's
    # boundary. `engine_node`'s stub output intentionally matches Task 2.1's
    # original hardcoded values, so this response is byte-identical to
    # before — only the source of the values changed (graph, not literal).
    result = pipeline.invoke(
        {"request_id": payload.request_id, "prompt": payload.prompt}
    )
    return AnalyzeResponse(
        risk_score=result["risk_score"],
        risk_level=result["risk_level"],
        action=result["action"],
        categories=result["result_categories"],
        detectors_fired=result["detectors_fired"],
    )
