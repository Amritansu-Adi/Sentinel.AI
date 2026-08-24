"""
SentinelAI — python-detection service (contract fixed Task 2.1, live since Phase 3-4)

`/analyze` runs the full regex/NER/vector -> categorizer -> deterministic
engine pipeline (see pipeline.py). Task 7.1 adds an optional `policy_config`
request field (live Mongo policy, forwarded by node-gateway) and Task 7.2
adds `flags`/`rewrite_guidance` to the response — see AnalyzeRequest/
AnalyzeResponse below and risk_engine.py's module docstring for the
two-tier action policy this now runs on.
"""

from typing import Any, Dict, List, Literal, Optional

from fastapi import FastAPI
from pydantic import BaseModel, Field

from .pipeline import pipeline
from .sanitizer import sanitize

app = FastAPI(
    title="SentinelAI Detection Service",
    description="Internal-only service. Not client-facing — called by node-gateway.",
    version="0.1.0",
)


class AnalyzeRequest(BaseModel):
    request_id: str
    prompt: str
    # Task 7.1: optional live policy document — node-gateway fetches this
    # from MongoDB (`policy_config` collection, cached with a TTL) and
    # forwards it here as a plain object: {thresholds, category_weights}.
    # Absent/None whenever Mongo is unreachable or unseeded; the engine
    # falls back to its own hardcoded defaults in that case, never a 4xx.
    policy_config: Optional[Dict[str, Any]] = None


class AnalyzeResponse(BaseModel):
    # Mirrors node-gateway's Mongoose `Request` schema (src/models/Request.js)
    # field-for-field so the two sides of the contract can't silently drift:
    # risk_score: Number 0-100, risk_level/action: fixed enums, both list fields.
    risk_score: float = Field(..., ge=0, le=100)
    risk_level: Literal["SAFE", "LOW", "HIGH", "CRITICAL"]
    action: Literal["ALLOW", "SANITIZE", "BLOCK"]
    categories: List[str]
    detectors_fired: List[str]
    # Internal gateway-only field. Present only after the deterministic engine
    # has selected SANITIZE; no raw detector values are ever returned.
    sanitized_prompt: Optional[str] = None
    # Task 7.2/7.3: populated whenever Tier 2a/2b fires (SANITIZE or
    # ALLOW-with-advisory). Never contains the raw sensitive value —
    # category name + a fixed human-readable message only.
    flags: List[Dict[str, str]] = Field(default_factory=list)
    # Task 7.2/7.3: populated only on BLOCK. Deterministic, category-level
    # template — never names or quotes the matched confidential document.
    rewrite_guidance: Optional[str] = None


@app.get("/health")
def health():
    # Mirrors node-gateway's /health shape/intent (src/index.js) — liveness
    # only, no downstream dependency checks.
    return {"status": "ok", "service": "python-detection"}


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(payload: AnalyzeRequest) -> AnalyzeResponse:
    # Runs the detection graph (regex/NER/vector -> merge -> categorizer ->
    # deterministic engine). Sanitization and external-provider enforcement
    # are intentionally owned by the gateway in Task 5.2.
    pipeline_input = {"request_id": payload.request_id, "prompt": payload.prompt}
    if payload.policy_config is not None:
        pipeline_input["policy_config"] = payload.policy_config
    result = pipeline.invoke(pipeline_input)
    sanitized_prompt = None
    if result["action"] == "SANITIZE":
        sanitized_prompt = sanitize(
            payload.prompt,
            result.get("regex_findings", []) + result.get("ner_entities", []),
        )
    return AnalyzeResponse(
        risk_score=result["risk_score"],
        risk_level=result["risk_level"],
        action=result["action"],
        categories=result["result_categories"],
        detectors_fired=result["detectors_fired"],
        sanitized_prompt=sanitized_prompt,
        flags=result.get("flags", []),
        rewrite_guidance=result.get("rewrite_guidance"),
    )