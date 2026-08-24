# EXECUTION HANDOVER STATE: Task 4.3 — Deterministic risk engine (Phase 4 IN PROGRESS)

## 0. PROTOCOL FOR ALL FUTURE AGENTS (Amritansu's standing instruction)
Every agent working this project must, at the end of its turn:
1. Keep **all** files from the bundle it received (do not drop or silently rewrite prior work outside your task scope).
2. Add only the files/edits your specific task requires.
3. **Claude agents only:** Return **one single bundle** (archive) containing the full cumulative project state: this `handover.md`, `project.md`, `docker-compose.yml`, `node-gateway/`, `python-detection/`, and any further service directories added later. Codex agents must make changes directly in the shared project folder and must not create an archive unless Amritansu explicitly asks.
4. This instruction must be re-copied verbatim into the next handover's §0 so it never gets lost.

---

## TASK 4.1 ARCHIVED STATE (do not modify — carried forward for agent continuity)

### 1. Execution Summary (4.1)
- **Completed:** Implemented `classify_local(evidence) -> CategoryResult` in new module `python-detection/app/categorizer/ollama_categorizer.py` (new `categorizer/` package). Calls a local Ollama model via the official `ollama` PyPI client (explicitly named in project.md §2 as "Ollama's client"), using Ollama's JSON-schema-constrained structured output (`format=<schema>`) to force `{"categories": [{"category", "confidence", "evidence"}]}` shaped output, with defensive Python-side re-validation on top (never trusts the model's output blindly). System prompt fixes the 9 categories verbatim from project.md and explicitly forbids the model from ever outputting ALLOW/SANITIZE/BLOCK. Wired into `pipeline.py`'s existing `categorizer_node(state) -> dict` — same signature, same `{"categories": [...]}` return shape, no topology change.
- **Current Target State at end of 4.1:** `categorizer_node` now produces real categories from real (mocked-transport-tested) Ollama calls. `merge_node` and `engine_node` remain stubs (`merge_node`'s naive concatenation is unchanged — still Task 4.3's job to dedupe/weight; `engine_node`'s stub is Task 4.3's job to replace). `/analyze`'s **external** response contract is still byte-identical to Task 2.1 (verified — `engine_node` doesn't consume `categories`/`regex_findings`/`ner_entities`/`vector_matches` yet).

### 2. Infrastructure & System Provisions (4.1)
- **New pip package** (in `python-detection/requirements.txt`): `ollama==0.6.2`. This is **not an unauthorized addition** — project.md §2 explicitly names "Ollama's client" as an already-approved Python-native tool in the stack table. Verified via `pip install --dry-run` — resolved cleanly with zero version bumps to any existing pin. `ollama` pulls in `httpx` transitively; no separate HTTP client was added.
- **No new environment variables added.** `OLLAMA_BASE_URL` and `OLLAMA_MODEL` already existed in project.md's env table — Task 4.1 is the first task to actually **read** them.
- **One hardcoded constant:** `_REQUEST_TIMEOUT_SECONDS = 30` in `ollama_categorizer.py`. **Amritansu's confirmed decision: bump to 60 during Task 4.2** — the live docker-compose run during 4.1 verification revealed the local model (`qwen2.5:1.5b-instruct-q4_K_M`) takes 35–40s on cold start, which causes a `CategorizerUnavailableError` timeout on first request. Bumping to 60s is Task 4.2's responsibility as it touches `pipeline.py` and `ollama_categorizer.py` anyway.
- **No changes to `Dockerfile`.** New files live inside the existing `python-detection/app/` package tree, covered by the existing `COPY ./app ./app`.
- **No changes to `node-gateway/`.**

### 3. Integration Contracts & Data Types (4.1)
`CategoryFinding` / `CategoryResult` — the dataclasses `classify_local` returns:
```python
# python-detection/app/categorizer/ollama_categorizer.py
@dataclass(frozen=True)
class CategoryFinding:
    category: str        # one of the 9 fixed CATEGORY_NAMES
    confidence: float    # 0.0-1.0, clamped
    evidence: str        # short model-generated rationale, capped at 500 chars

    def to_dict(self) -> dict: ...  # -> {"category", "confidence", "evidence"}

@dataclass(frozen=True)
class CategoryResult:
    categories: List[CategoryFinding]

    def to_dict(self) -> dict: ...  # -> {"categories": [...]}
```
Public function:
```python
def classify_local(evidence: List[dict]) -> CategoryResult
```
- `CATEGORY_NAMES` (module-level tuple, exported): `PII_EXPOSURE, CREDENTIAL_EXPOSURE, FINANCIAL_DATA, CONFIDENTIAL_COMPANY_DATA, INTERNAL_SYSTEM_INFORMATION, SOURCE_CODE_SENSITIVE, SECURITY_SENSITIVE_INFORMATION, SAFE, UNKNOWN` — verbatim from project.md.
- **`evidence` param is `merged_evidence`** — **never the raw prompt**. Load-bearing privacy property: the LLM sees only typed metadata (type/severity/span-offsets/confidence/doc-title/classification), never the employee's actual sensitive text.
- **Two distinct failure modes:**
  - `CategorizerUnavailableError` (subclass of `CategorizerError`) — raised on transport failure (timeout, connection refused, non-2xx). **Currently propagates as 500 — Task 4.2 catches this to trigger Groq fallback.**
  - Malformed model output — does NOT raise; `_parse_response()` degrades to `CategoryFinding("UNKNOWN", 0.5, ...)`.
- **Reproducibility:** `options={"temperature": 0}` always passed. Task 4.2's `classify_groq` must do the same.
- `pipeline.py`'s `categorizer_node` as left by Task 4.1:
```python
def categorizer_node(state: PipelineState) -> dict:
    result = classify_local(state.get("merged_evidence", []))
    return {"categories": [c.to_dict() for c in result.categories]}
```

### 4. Live Verification Results (4.1) — docker-compose confirmed
- All 4 containers confirmed running (`docker ps` verified by Amritansu): node-gateway `:4000`, python-detection `:8000`, mongodb `:27017`, ollama `:11434`.
- `qwen2.5:1.5b-instruct-q4_K_M` pulled and confirmed present (`ollama list` verified).
- **Cold-start timeout confirmed real:** First `/analyze` call raises `CategorizerUnavailableError` (30s timeout, model takes 35–40s on first call). Second call (warm model) succeeds and returns 200. This is the primary driver for Task 4.2 — the fallback is not optional polish, it is the error handler for a confirmed real failure mode.
- **`.env` confirmed:** `OLLAMA_BASE_URL=http://ollama:11434` (Docker Compose service name, not localhost). Container env verified via `docker exec ... env | findstr OLLAMA`.
- **`docker-compose.yml` risk resolved:** The Task 1.1-era flag about this file never being run is now closed — stack runs.
- **FAISS volume mount still unresolved** — index rebuilds every restart. Still Task 7.1's scope.

---

## TASK 4.2 ARCHIVED STATE (do not modify — carried forward for agent continuity)

### 1. Execution Summary (4.2)
- **Completed:** Implemented `classify_groq(evidence) -> CategoryResult` in new module `python-detection/app/categorizer/groq_categorizer.py`. It imports (never redefines) `CategoryFinding`/`CategoryResult`/`CategorizerUnavailableError`/`_SYSTEM_PROMPT`/`_format_evidence`/`_parse_response` from `ollama_categorizer.py`, uses Groq's official Python SDK (`groq==1.6.0`, checked against live PyPI index — actual latest release, not guessed) with `temperature=0` and `response_format={"type": "json_object"}` (Groq free tier has no schema-constrained decoding, so the JSON-object instruction is reinforced in the user turn). Bumped `ollama_categorizer._REQUEST_TIMEOUT_SECONDS` 30→60. Wired `pipeline.py`'s `categorizer_node` to dispatch on `RISK_MODEL_PROVIDER` exactly per the Task 4.1 handover's specified logic (verbatim, not altered).
- **Current Target State at end of 4.2:** `categorizer_node` is now provider-switchable and self-healing: `RISK_MODEL_PROVIDER=groq` → Groq only; `RISK_MODEL_PROVIDER=local` (default) → Ollama first, Groq fallback on `CategorizerUnavailableError` only, double-failure propagates uncaught (never silently becomes SAFE). `merge_node` and `engine_node` remain untouched stubs — still Task 4.3's job. `/analyze`'s external response contract is still byte-identical to Task 2.1 (verified below).

### 2. Infrastructure & System Provisions (4.2)
- **New pip package** (in `python-detection/requirements.txt`): `groq==1.6.0` — verified against PyPI's live version index at execution time (not assumed from training data), official Groq Python SDK per project.md's stack table.
- **No new environment variables added.** `GROQ_API_KEY` and `GROQ_MODEL` already existed in project.md's env table — this task is the first to read them (`os.getenv`, same "wire it for real" pattern as 3.3/4.1).
- **One constant changed, one added:**
  - `ollama_categorizer._REQUEST_TIMEOUT_SECONDS`: `30` → `60` (per Task 4.1 handover's confirmed decision).
  - `groq_categorizer._REQUEST_TIMEOUT_SECONDS = 30` — new, hardcoded (not in project.md's env table, same "operational default not a config surface" rationale as Ollama's). Groq's hosted `llama-3.1-8b-instant` is expected sub-5s on this evidence-only payload; 30s is jitter headroom, not a tuned-for-slowness value.
- **No changes to `Dockerfile`.** New file lives inside the existing `python-detection/app/categorizer/` package, covered by `COPY ./app ./app`.
- **No changes to `node-gateway/`.**

### 3. Integration Contracts & Data Types (4.2)
```python
# python-detection/app/categorizer/groq_categorizer.py
def classify_groq(evidence: List[dict]) -> CategoryResult
```
- Identical return shape to `classify_local` — `CategoryResult` / `CategoryFinding` are the **same imported classes**, not parallel redefinitions (`groq_categorizer.CategoryResult is ollama_categorizer.CategoryResult` — verified true).
- Same two failure-mode split as `classify_local`:
  - `CategorizerUnavailableError` (imported, same class) — raised on `groq.APITimeoutError` / `groq.APIConnectionError` / `groq.APIStatusError`. Caught by `categorizer_node`'s fallback dispatch.
  - Malformed-but-received response — never raises; degrades to `UNKNOWN` via the **shared** `_parse_response` (verified `groq_categorizer._parse_response is ollama_categorizer._parse_response`).
- Empty evidence short-circuits to `SAFE(1.0)` **without** creating a Groq client or importing `groq` at all (verified via mock — `_get_client` not called for `classify_groq([])`).
- `pipeline.py`'s `categorizer_node` as left by Task 4.2 (implemented exactly per Task 4.1 handover's §5 rule 5 spec, unmodified):
```python
def categorizer_node(state: PipelineState) -> dict:
    provider = os.getenv("RISK_MODEL_PROVIDER", "local")
    evidence = state.get("merged_evidence", [])
    if provider == "groq":
        result = classify_groq(evidence)
    else:
        try:
            result = classify_local(evidence)
        except CategorizerUnavailableError:
            result = classify_groq(evidence)
    return {"categories": [c.to_dict() for c in result.categories]}
```

### 4. Verification Results (4.2)
Ran in an isolated venv (fastapi/pydantic/langgraph/ollama/groq installed; torch/transformers/faiss deliberately **not** installed and not needed — `ner_detector`/`vector_detector` confirmed lazy-import-only at module scope, mocked out for these tests):
- ✅ **Import safety:** `classify_groq([])` short-circuits without calling `_get_client` or importing `groq` (mock-verified).
- ✅ **`_parse_response` reuse:** confirmed same function object across both modules; malformed JSON → `UNKNOWN`, out-of-range confidence (5.0) → clamped to `1.0`.
- ✅ **No redefinition:** `CategoryResult`, `CategoryFinding`, `CategorizerUnavailableError`, `_SYSTEM_PROMPT`, `_format_evidence` all confirmed identical objects (`is` comparison) between `groq_categorizer` and `ollama_categorizer`.
- ✅ **`categorizer_node` dispatch, all 4 scenarios from Task 4.1 handover §7.3:**
  (a) `RISK_MODEL_PROVIDER=groq` → Groq called, Ollama not called.
  (b) `RISK_MODEL_PROVIDER=local`, Ollama succeeds → Ollama called, Groq not called.
  (c) `RISK_MODEL_PROVIDER=local`, Ollama raises `CategorizerUnavailableError` → Groq called as fallback.
  (d) both raise `CategorizerUnavailableError` → exception propagates uncaught (not swallowed as SAFE).
- ✅ **FastAPI contract regression:** `pipeline.invoke(...)` with detectors/categorizer mocked still returns `risk_score=0.0, risk_level=SAFE, action=ALLOW, result_categories=[], detectors_fired=[]` — `engine_node` confirmed still ignores `categories` (correct, that's Task 4.3's job). `categories` key itself is populated correctly inside pipeline state, just not yet consumed.
- ✅ `ollama_categorizer._REQUEST_TIMEOUT_SECONDS == 60` confirmed.
- ✅ All modified/created files confirmed to `py_compile` cleanly.
- ⚠️ **NOT verified (no Docker/live API access in this execution environment):** the live docker-compose test against a real Groq API key (handover §7.5 — `<5s` response, swap `RISK_MODEL_PROVIDER` back and forth) and the cross-provider contract test (§7.6 — same evidence → same category *names* from both live providers). **Amritansu must run these two before considering 4.2 fully closed**; static/unit verification above covers everything that doesn't require live network credentials.

### 5. Open Issues Carried Forward (updated)
- **Live docker-compose + real Groq API key test** — unverified in this session (§4 above), carried forward as a manual step, not a code gap.
- **`category_weights`** — locked per Task 4.1 handover §6, unchanged, still valid for Task 4.3.
- **`merge_node` deduplication** — still naive concatenation. Task 4.3's job; confirmed risk unchanged (regex + LLM both flagging `CREDENTIAL_EXPOSURE` double-counts without dedup).
- **Similarity floor for vector matches** — still unaddressed, still Task 4.3's open design question.
- **FAISS volume mount** — still Task 7.1's scope, unchanged.

---

## TASK 4.3 ARCHIVED STATE (COMPLETE)

### 1. Execution Summary (4.3)
- **Completed:** Added `python-detection/app/risk_engine.py` with the pure, network-free `calculate_risk(category_results, *, evidence=(), policy_config=None) -> RiskResult` implementation. It is the sole source of `ALLOW`, `SANITIZE`, and `BLOCK` decisions. `pipeline.py`'s `engine_node` now invokes it and returns its score, level, action, normalized categories, and detector provenance.
- **Normalization:** The engine deterministically maps regex types, NER entity types, and sufficiently relevant confidential/internal vector matches to the fixed category set, then unions those categories with LLM output. Every category can contribute its weight once only: regex plus LLM agreement on `CREDENTIAL_EXPOSURE` scores 90, not 180. `SAFE` is removed whenever any non-safe category exists.
- **Scoring:** Uses the locked Task 4.2 weights, caps the sum at 100, and maps scores using `safe_max=29`, `low_max=59`, `high_max=79`: 0-29 SAFE/ALLOW, 30-59 LOW/ALLOW, 60-79 HIGH/SANITIZE, 80-100 CRITICAL/BLOCK. LLM confidence is not multiplied into a weight; detector evidence is factual metadata and confidence is not a policy multiplier.
- **Vector relevance:** Added a fixed `VECTOR_SIMILARITY_FLOOR = 0.60`; below-floor top-k matches are filtered before categorization/scoring, resolving the false-positive issue carried from 4.2.
- **Policy seed:** Updated `node-gateway/scripts/seedPolicyConfig.js` from obsolete placeholder weights to the approved locked values. Existing MongoDB `policy_config/active` documents are intentionally not overwritten by the idempotent seed script; re-seed/migrate it manually if one was created with the old values.

### 2. Files Changed (4.3)
- **Created:** `python-detection/app/risk_engine.py`
- **Modified:** `python-detection/app/pipeline.py` (engine integration, vector filter, records `local_llm` or `groq` categorizer provenance)
- **Modified:** `node-gateway/scripts/seedPolicyConfig.js` (locked category weights)
- **Created:** `python-detection/test_risk_engine.py` (standard-library unit tests)

### 3. Verification Results (4.3)
- Unit coverage verifies: no evidence -> `SAFE/ALLOW` (0); PAN evidence -> `CRITICAL/BLOCK` (80); API-key regex plus the same LLM category -> exactly `CRITICAL/BLOCK` (90, no double count); a confidential vector match at 0.59 -> `SAFE/ALLOW` (filtered). Note the locked PII weight (80) exceeds `high_max` (79), so this is the required result under the frozen policy despite Phase 7's older broad example calling for a PII sanitize scenario.
- Remaining live verification: run the full Python test command and exercise `/analyze` in the Docker stack once models are available. Task 5.1 is next.

---

## CURRENT TASK: Task 5.1 — Sanitizer

Per project.md Phase 4, Task 4.3: implement `calculate_risk(category_results) -> {score, level, action}` in the Python detection service — the **only** place a final ALLOW/SANITIZE/BLOCK decision is made (no LLM call inside this function). Must consume `merged_evidence`/`categories` from pipeline state, dedupe across detector sources before applying the **locked** category weights (Task 4.1 handover §6), sum to a 0–100 score, and map to risk level/action via `policy_config` thresholds (`RISK_THRESHOLD_SAFE_MAX=29`, `RISK_THRESHOLD_LOW_MAX=59`, `RISK_THRESHOLD_HIGH_MAX=79`). Replaces `engine_node`'s stub in `pipeline.py` — this is the task that finally breaks the "byte-identical to Task 2.1" response contract on purpose. See "Open Issues Carried Forward" above for the two known design problems (merge dedup, vector similarity floor) this task must resolve.

---

## TASK 4.2 SPECIFICATION (as received — preserved for reference, now COMPLETE per above)

### 5. Task 4.2 Specification

**Objective:** Implement `classify_groq(evidence) -> CategoryResult` as a drop-in swap for `classify_local`. Wire provider selection into `categorizer_node` via `RISK_MODEL_PROVIDER` env var. Catch `CategorizerUnavailableError` from Ollama to trigger Groq fallback. Bump `_REQUEST_TIMEOUT_SECONDS` to 60 in `ollama_categorizer.py`.

**Files to create/modify (python-detection only — no node-gateway changes):**
- **CREATE** `python-detection/app/categorizer/groq_categorizer.py` — `classify_groq` implementation
- **MODIFY** `python-detection/app/categorizer/ollama_categorizer.py` — bump `_REQUEST_TIMEOUT_SECONDS = 30` → `60`
- **MODIFY** `python-detection/app/pipeline.py` — update `categorizer_node` to dispatch on `RISK_MODEL_PROVIDER` with fallback logic
- **MODIFY** `python-detection/requirements.txt` — add `groq` package (official Groq Python SDK)

**Strict implementation rules for the agent:**

1. **Do NOT redefine `CATEGORY_NAMES`, `CategoryFinding`, `CategoryResult`, `CategorizerError`, `CategorizerUnavailableError`.** Import them from `ollama_categorizer.py`. If the agent judges they belong in a shared `categorizer/types.py`, that refactor is acceptable only if it moves — not duplicates — the definitions, and updates the import in `ollama_categorizer.py` accordingly. A second copy of `CATEGORY_NAMES` with even one typo is a silent categorization bug.

2. **Reuse `_format_evidence` and `_describe_evidence_item`** from `ollama_categorizer.py` (import or move to shared module). Groq receives the same evidence-only payload — the privacy property (no raw prompt to LLM) must hold for both providers identically.

3. **System prompt for Groq must carry the same boundary rule verbatim:** the model must never output ALLOW/SANITIZE/BLOCK — categories and confidence only. Copy the exact rule text from `ollama_categorizer.py`'s system prompt.

4. **`temperature=0`** must be set on the Groq API call. Groq's SDK param name is `temperature` (same as Ollama's). Required for the project.md §6 contract test — "same evidence input, same category shape from both providers."

5. **`categorizer_node` fallback dispatch logic — exact required behaviour:**
```python
def categorizer_node(state: PipelineState) -> dict:
    provider = os.getenv("RISK_MODEL_PROVIDER", "local")
    evidence = state.get("merged_evidence", [])
    
    if provider == "groq":
        result = classify_groq(evidence)
    else:
        try:
            result = classify_local(evidence)
        except CategorizerUnavailableError:
            # Ollama cold-start timeout or unreachable — fall through to Groq
            result = classify_groq(evidence)
    
    return {"categories": [c.to_dict() for c in result.categories]}
```
   - When `RISK_MODEL_PROVIDER=groq`: Groq only, no Ollama call, no fallback chain.
   - When `RISK_MODEL_PROVIDER=local` (default): try Ollama first; on `CategorizerUnavailableError` specifically (not bare `Exception`), fall through to Groq. If Groq also raises `CategorizerUnavailableError`, let it propagate — do not swallow both failures silently as SAFE.

6. **Groq structured output:** Use Groq's `response_format={"type": "json_object"}` (not JSON schema like Ollama — Groq's free tier doesn't support schema-constrained output). The system prompt must instruct the model to return only the JSON object `{"categories": [...]}` with no preamble. `_parse_response` from `ollama_categorizer.py` is already defensive against malformed output — reuse it directly.

7. **`GROQ_API_KEY` and `GROQ_MODEL` env vars** are already in project.md's env table. Task 4.2 is the first task to read them (`os.getenv`). `GROQ_MODEL` default: `llama-3.1-8b-instant`.

8. **No changes to `Dockerfile`** — new file is inside `python-detection/app/categorizer/`, covered by `COPY ./app ./app`.

9. **No changes to `node-gateway/`.**

### 6. Confirmed Category Weights (locked — for Task 4.3's seed script)
These are Amritansu's final decisions. Task 4.3's agent must use exactly these values when implementing the `policy_config` seed script and the deterministic scoring formula. Do not alter them.

| Category | Weight |
|---|---|
| CREDENTIAL_EXPOSURE | 90 |
| PII_EXPOSURE | 80 |
| FINANCIAL_DATA | 75 |
| CONFIDENTIAL_COMPANY_DATA | 70 |
| SOURCE_CODE_SENSITIVE | 50 |
| SECURITY_SENSITIVE_INFORMATION | 65 |
| INTERNAL_SYSTEM_INFORMATION | 50 |
| UNKNOWN | 15 |
| SAFE | 0 |

### 7. Verification Required (Task 4.2 PASS criteria)
The agent must verify all of the following before declaring Task 4.2 complete:

1. **Import safety:** `groq_categorizer.py` imports cleanly with `groq` package absent (lazy import, same discipline as `ollama_categorizer.py`). `classify_groq([])` short-circuits without touching the import.
2. **`_parse_response` reuse:** same defensive parsing (invalid category → UNKNOWN, out-of-range confidence → clamped, non-JSON → UNKNOWN) applies to Groq's response path — not reimplemented, reused.
3. **`categorizer_node` dispatch test:** mock both `classify_local` and `classify_groq`; assert (a) `RISK_MODEL_PROVIDER=groq` calls only Groq, (b) `RISK_MODEL_PROVIDER=local` calls Ollama first, (c) when Ollama raises `CategorizerUnavailableError` with `RISK_MODEL_PROVIDER=local`, Groq is called as fallback, (d) when both raise `CategorizerUnavailableError`, the exception propagates (not swallowed).
4. **FastAPI contract regression:** `/analyze` still returns the Task 2.1 dummy shape (`risk_score: 0.0, risk_level: SAFE, action: ALLOW, categories: [], detectors_fired: []`) — `engine_node` still doesn't consume categories (correct, that's Task 4.3).
5. **Live docker-compose test:** with `RISK_MODEL_PROVIDER=groq` in `.env`, restart python-detection container, send the same test prompt, confirm 200 response in <5s (Groq is fast — if it takes 30s+, the API key or model name is wrong). Then swap back to `RISK_MODEL_PROVIDER=local`, confirm warm-Ollama path still works.
6. **Contract test (project.md §6):** same evidence input sent through both providers (swap env var, restart container, re-send). Assert both return the same category names in the response (confidence values may differ slightly — that's acceptable; category set shape must match).

### 8. Open Issues Carried Forward

- **`_REQUEST_TIMEOUT_SECONDS` bump to 60** — Task 4.2's responsibility. One-line change in `ollama_categorizer.py`. Do this first, before anything else in the task.
- **`category_weights` are now locked** (§6 above) — Task 4.3 unblocked on this front.
- **`merge_node` deduplication** — still naive concatenation from Task 2.3. Task 4.3's job. The confirmed risk: if regex fires `CREDENTIAL_EXPOSURE` and Ollama also categorises `CREDENTIAL_EXPOSURE`, the weight gets counted twice. Task 4.3 must dedupe before scoring.
- **Similarity floor for vector matches** — `vector_node` returns top-k with no threshold, meaning low-relevance matches inflate `merged_evidence` and cause unnecessary Ollama/Groq calls. Still open design question for Task 4.3.
- **Multimodal `messages[].content` / "only last message used as prompt" assumption** from Task 1.2 — unchanged, python-detection doesn't touch this.
- **FAISS volume mount** — index rebuilds every restart. Task 7.1.
