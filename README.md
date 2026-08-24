<div align="center">

```text

███████╗███████╗███╗   ██╗████████╗██╗███╗   ██╗███████╗██╗      █████╗ ██╗
██╔════╝██╔════╝████╗  ██║╚══██╔══╝██║████╗  ██║██╔════╝██║     ██╔══██╗██║
███████╗█████╗  ██╔██╗ ██║   ██║   ██║██╔██╗ ██║█████╗  ██║     ███████║██║
╚════██║██╔══╝  ██║╚██╗██║   ██║   ██║██║╚██╗██║██╔══╝  ██║     ██╔══██║██║
███████║███████╗██║ ╚████║   ██║   ██║██║ ╚████║███████╗███████╗██║  ██║██║
╚══════╝╚══════╝╚═╝  ╚═══╝   ╚═╝   ╚═╝╚═╝  ╚═══╝╚══════╝╚══════╝╚═╝  ╚═╝╚═╝

```

# Sentinel.AI

### AI-Powered LLM Traffic Security Gateway

**Intercept · Detect · Score · Sanitize · Protect**

[![Node.js](https://img.shields.io/badge/Node.js-20+-339933?style=flat-square\&logo=node.js\&logoColor=white)](https://nodejs.org/)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square\&logo=python\&logoColor=white)](https://python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=flat-square\&logo=fastapi)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Python-1C3C3C?style=flat-square)](https://www.langchain.com/langgraph)
[![HuggingFace](https://img.shields.io/badge/HuggingFace-Transformers-FFD21E?style=flat-square\&logo=huggingface\&logoColor=black)](https://huggingface.co/)
[![FAISS](https://img.shields.io/badge/FAISS-Vector_Search-0468FF?style=flat-square)](https://github.com/facebookresearch/faiss)
[![MongoDB](https://img.shields.io/badge/MongoDB-7-47A248?style=flat-square\&logo=mongodb\&logoColor=white)](https://www.mongodb.com/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square\&logo=docker\&logoColor=white)](https://www.docker.com/)

</div>

---

## What is Sentinel.AI?

**Sentinel.AI** is an AI-powered security gateway designed to protect organizations from sensitive information being accidentally sent to external LLM providers such as ChatGPT, Claude, Gemini, or other OpenAI-compatible APIs.

Instead of allowing an application or employee to communicate directly with an external model, Sentinel.AI sits in the middle:

```text
Employee / Application
        │
        ▼
┌─────────────────────────┐
│   Sentinel.AI Gateway   │
│      Node + Express     │
└────────────┬────────────┘
             │
             │ /analyze
             ▼
┌─────────────────────────┐
│ Python Detection Engine │
│        FastAPI          │
└────────────┬────────────┘
             │
             ▼
      ┌──────────────┐
      │  LangGraph   │
      │   Pipeline   │
      └──────┬───────┘
             │
      ┌──────┼─────────────┐
      ▼      ▼             ▼
   Regex    NER       Vector Search
 Detector  Detector       FAISS
      │      │             │
      └──────┼─────────────┘
             ▼
      Evidence Merging
             │
             ▼
      Risk Categorizer
      ┌──────┴──────┐
      │             │
    Ollama         Groq
    Local          Fallback
      │             │
      └──────┬──────┘
             ▼
    Deterministic Risk
          Engine
             │
       Score: 0–100
             │
      ┌──────┼──────┐
      ▼      ▼      ▼
    ALLOW SANITIZE BLOCK
```

The central security principle is:

> **Detectors find evidence → the LLM interprets the evidence → the deterministic engine makes the final security decision.**

The LLM is therefore **never trusted to directly decide whether a request should be allowed or blocked**.

---

## The Problem

Employees increasingly use LLMs to write code, analyze documents, debug systems, and work with internal information.

That creates a security problem.

A user might accidentally paste:

* Personal information
* API keys
* Authentication tokens
* Database connection strings
* Internal system information
* Confidential project details
* Sensitive source code
* Financial information

Once submitted directly to an external LLM provider, that information has already crossed the organization's security boundary.

Traditional DLP systems are not designed specifically around LLM traffic and contextual prompts.

**Sentinel.AI adds an intelligent policy checkpoint between the user and the external LLM.**

- A vector match classified `CONFIDENTIAL` at or above the similarity floor is `BLOCK`.
- Regex or sufficiently confident NER findings are masked and forwarded as `SANITIZE`.
- Internal vector matches and non-spannable categorizer findings are forwarded as `ALLOW` with an advisory flag.
- Requests with no evidence are `ALLOW` with no flag.

# Core Architecture

Sentinel.AI is intentionally split into independent components.

### 1. Node.js Gateway

The gateway is the client-facing layer.

Responsibilities:

* OpenAI-compatible request interception
* Prompt extraction
* Request ID generation
* Communication with the Python detection service
* Eventually enforcing ALLOW / SANITIZE / BLOCK decisions
* Eventually forwarding permitted requests to an external LLM provider

Current endpoint:

```http
POST /v1/chat/completions
```

Health endpoint:

```http
GET /health
```

The gateway currently extracts text from standard OpenAI-style `messages` payloads and forwards the extracted prompt to the detection service.

---

### 2. Python Detection Service

The detection service is an internal FastAPI application.

Its job is to perform the security analysis independently of the Node gateway.

Current structure:

```text
python-detection/
├── app/
│   ├── categorizer/
│   ├── data/
│   ├── detectors/
│   ├── main.py
│   ├── pipeline.py
│   └── risk_engine.py
├── Dockerfile
├── requirements.txt
└── test_risk_engine.py
```

The service exposes the internal `/analyze` contract.

This separation keeps the gateway lightweight while allowing the AI/security pipeline to evolve independently.

---

# Detection Pipeline

Sentinel.AI uses multiple sources of evidence rather than relying on a single model.

```text
                 Prompt
                   │
        ┌──────────┼──────────┐
        ▼          ▼          ▼
      Regex       NER       FAISS
     Detector   Detector   Retrieval
        │          │          │
        └──────────┼──────────┘
                   ▼
            Evidence Merge
                   │
                   ▼
           Risk Categorizer
                   │
                   ▼
          Deterministic Engine
                   │
             Risk Score
                   │
          ┌────────┼────────┐
          ▼        ▼        ▼
        ALLOW   SANITIZE   BLOCK
```

## Regex Detection

The regex layer is intended to catch high-confidence sensitive patterns such as:

* PAN numbers
* Aadhaar numbers
* Email addresses
* Phone numbers
* API keys
* JWTs
* Private-key headers
* Database connection strings

Regex detection provides fast, deterministic evidence before higher-level interpretation.

---

## Named Entity Recognition

Sentinel.AI uses Hugging Face Transformers with:

```text
dslim/bert-base-NER
```

The NER detector identifies entities such as:

* PERSON
* ORGANIZATION
* LOCATION

The NER layer is deliberately responsible for **entity extraction**, not deciding whether an entity is dangerous.

---

## Company Knowledge Retrieval

Sentinel.AI also supports contextual detection using vector search.

The planned pipeline uses:

```text
sentence-transformers
        +
all-MiniLM-L6-v2
        +
FAISS
```

Company documents can be embedded into a local FAISS index and queried against incoming prompts.

This allows the system to identify prompts that are semantically related to confidential internal information even when the exact wording does not appear in the prompt.

Example:

```text
Company document:
"Project Orion is our internal autonomous billing platform."

User prompt:
"Explain the architecture of our internal autonomous payment system."

        ↓

Semantic similarity

        ↓

Potential CONFIDENTIAL_COMPANY_DATA evidence
```

---

# Risk Categorization

After evidence is collected, Sentinel.AI passes the evidence to a risk categorization layer.

The supported model strategy is:

### Local-first

```text
Ollama
qwen2.5:1.5b-instruct-q4_K_M
```

### Optional fallback

```text
Groq
llama-3.1-8b-instant
```

The model does **not** decide whether the request should be allowed or blocked.

Instead, it returns structured security categories and confidence.

Example categories include:

```text
PII_EXPOSURE
CREDENTIAL_EXPOSURE
FINANCIAL_DATA
CONFIDENTIAL_COMPANY_DATA
INTERNAL_SYSTEM_INFORMATION
SOURCE_CODE_SENSITIVE
SECURITY_SENSITIVE_INFORMATION
SAFE
UNKNOWN
```

---

# Deterministic Risk Engine

The final security decision belongs to a deterministic Python risk engine.

Conceptually:

```text
Evidence
   │
   ▼
Category normalization
   │
   ▼
Category weights
   │
   ▼
Risk score: 0–100
   │
   ▼
Policy thresholds
   │
   ├── 0–29  → ALLOW
   ├── 30–59 → ALLOW
   ├── 60–79 → SANITIZE
   └── 80–100 → BLOCK
```

The thresholds are configurable through environment variables:

```env
RISK_THRESHOLD_SAFE_MAX=29
RISK_THRESHOLD_LOW_MAX=59
RISK_THRESHOLD_HIGH_MAX=79
```

The important design decision is that **no LLM call occurs inside the final risk calculation**.

This makes the enforcement layer deterministic, testable, and auditable.

---

# Sanitization

When a request contains sensitive information but does not meet the blocking threshold, Sentinel.AI can sanitize the identified spans before the request reaches the external model.

Examples:

```text
john@example.com
        ↓
[EMAIL]

ABCDE1234F
        ↓
[PAN_CARD]

John Smith
        ↓
[PERSON_NAME]

Internal Project Orion architecture
        ↓
[CONFIDENTIAL_PROJECT]
```

Sanitization is deterministic and operates only on spans already identified by the detection pipeline.

The sanitizer does not use an LLM to rewrite sensitive content.

---

# Security Decision Model

Every request eventually follows one of three paths.

### ALLOW

The original prompt is forwarded.

```text
Prompt
  ↓
Analysis
  ↓
Low risk
  ↓
ALLOW
  ↓
External LLM
```

### SANITIZE

Sensitive content is replaced before forwarding.

```text
Prompt
  ↓
Analysis
  ↓
Medium risk
  ↓
SANITIZE
  ↓
Redacted prompt
  ↓
External LLM
```

### BLOCK

The request never reaches the external model.

```text
Prompt
  ↓
Analysis
  ↓
High/Critical risk
  ↓
BLOCK
  ↓
Rejected
```

This is the core security boundary of Sentinel.AI.

---

# LangGraph Pipeline

The Python detection layer is designed around a LangGraph workflow.

The pipeline follows a linear evidence-gathering architecture rather than a collection of independent autonomous agents.

Conceptually:

```text
START
  │
  ├── Regex Detector
  ├── NER Detector
  └── Vector Search
          │
          ▼
    Evidence Merge
          │
          ▼
    Risk Categorizer
          │
          ▼
    Risk Engine
          │
          ▼
        END
```

LangGraph is used as the orchestration layer; the final security decision remains deterministic.

---

# Data & Audit Model

Sentinel.AI is designed around MongoDB for persistent security/audit information.

Primary collections include:

### `requests`

Stores audit events.

Example fields:

```text
request_id
timestamp
employee_id
risk_score
risk_level
action
categories
detectors_fired
sanitized
original_char_count
sanitized_char_count
```

Sensitive raw values should not be persisted in the audit record.

---

### `employees`

Stores aggregated employee-level risk information:

```text
employee_id
name
department
total_requests
total_violations
avg_risk
risk_tier
```

---

### `policy_config`

Stores the active security policy:

```text
thresholds
category_weights
version
updated_at
```

---

### `company_knowledge`

Stores metadata for internal documents used by the semantic retrieval layer.

The FAISS index contains the corresponding vector representations.

---

# Current Repository Structure

```text
Sentinel.AI/
│
├── node-gateway/
│   ├── src/
│   │   ├── index.js
│   │   └── models/
│   ├── Dockerfile
│   └── package.json
│
├── python-detection/
│   ├── app/
│   │   ├── categorizer/
│   │   ├── data/
│   │   ├── detectors/
│   │   ├── main.py
│   │   ├── pipeline.py
│   │   └── risk_engine.py
│   ├── Dockerfile
│   ├── requirements.txt
│   └── test_risk_engine.py
│
├── docker-compose.yml
├── project.md
├── handover.md
└── README.md
```

The repository currently separates the Node gateway from the Python detection service, matching the intended architecture.

---

# Technology Stack

| Layer                     | Technology                   |
| ------------------------- | ---------------------------- |
| Gateway                   | Node.js, Express.js          |
| Detection API             | Python, FastAPI              |
| Pipeline orchestration    | LangGraph                    |
| Pattern detection         | Python Regex                 |
| NER                       | Hugging Face Transformers    |
| NER model                 | `dslim/bert-base-NER`        |
| Embeddings                | Sentence Transformers        |
| Vector search             | FAISS                        |
| Local risk categorization | Ollama                       |
| Optional LLM fallback     | Groq                         |
| Risk engine               | Deterministic Python         |
| Sanitization              | Regex / NER span replacement |
| Database                  | MongoDB                      |
| Local infrastructure      | Docker Compose               |
| External LLM              | OpenAI-compatible API        |

---

# Environment Variables

Example configuration:

```env
# Gateway
GATEWAY_PORT=4000
DETECTION_SERVICE_URL=http://localhost:8000

# MongoDB
MONGODB_URI=

# Authentication
JWT_SECRET=

# Risk model
RISK_MODEL_PROVIDER=local

# Ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:1.5b-instruct-q4_K_M

# Groq fallback
GROQ_API_KEY=
GROQ_MODEL=llama-3.1-8b-instant

# External LLM
EXTERNAL_LLM_BASE_URL=
EXTERNAL_LLM_API_KEY=

# Embeddings / retrieval
VECTOR_MODEL_NAME=all-MiniLM-L6-v2
NER_MODEL_NAME=dslim/bert-base-NER
FAISS_INDEX_PATH=./data/company_index.faiss

# Risk thresholds
RISK_THRESHOLD_SAFE_MAX=29
RISK_THRESHOLD_LOW_MAX=59
RISK_THRESHOLD_HIGH_MAX=79
```

Never commit real API keys or secrets to the repository.

---

# Running Locally

## Prerequisites

Install:

* Node.js 20+
* Python 3.11+
* Docker Desktop / Docker Engine
* MongoDB through Docker Compose
* Ollama if using the local risk model

---

## Clone

```bash
git clone https://github.com/Amritansu-Adi/Sentinel.AI.git
cd Sentinel.AI
```

Run the focused checks:

## Start Infrastructure

```bash
docker compose up --build
```

The development stack is designed around:

```text
node-gateway
python-detection
mongodb
ollama
```

The repository's Compose configuration maps the gateway to port `4000`, the detection service to `8000`, MongoDB to `27017`, and Ollama to `11434`.

> Note: the current `docker-compose.yml` contains a reconstruction warning in the repository itself. Reconcile it with the intended/current local environment before treating it as a production deployment definition.

---

# API

## Gateway Health

```http
GET /health
```

Example response:

```json
{
  "status": "ok",
  "service": "node-gateway"
}
```

---

## OpenAI-Compatible Gateway

```http
POST /v1/chat/completions
```

Example:

```json
{
  "messages": [
    {
      "role": "user",
      "content": "Hello, explain machine learning."
    }
  ]
}
```

The gateway extracts the latest textual message, generates a UUID request ID, and sends the prompt to the Python detection service.

The current implementation intentionally stops before external LLM forwarding and final ALLOW/SANITIZE/BLOCK enforcement; those belong to later implementation phases.

---

# Development Roadmap

Sentinel.AI is being built incrementally.

### Phase 1 — Gateway Foundation

* Node/Express gateway
* Docker setup
* OpenAI-compatible interception endpoint
* MongoDB data models

### Phase 2 — Detection Service

* FastAPI service
* Node → Python communication
* LangGraph pipeline skeleton

### Phase 3 — Detection

* Regex detector
* Hugging Face NER
* FAISS company-knowledge retrieval

### Phase 4 — Risk Intelligence

* Local Ollama categorizer
* Groq fallback
* Deterministic risk engine

### Phase 5 — Enforcement

* Sanitization
* ALLOW / SANITIZE / BLOCK enforcement
* External LLM forwarding
* MongoDB audit logging

### Phase 6 — Dashboard

* React + Vite
* TailwindCSS
* Authentication
* Risk statistics
* Request analytics
* Employee risk overview
* Recharts visualizations

### Phase 7 — Deployment & Testing

* Full Docker Compose stack
* Free-tier deployment
* End-to-end tests
* ALLOW / SANITIZE / BLOCK test scenarios

These phases reflect the project's current architecture plan rather than claiming that all of them are already implemented.

---

# Testing

The project includes risk-engine tests under:

```text
python-detection/test_risk_engine.py
```

The intended verification strategy covers:

```text
Safe prompt
    ↓
ALLOW

PII-containing prompt
    ↓
SANITIZE

Credential + confidential information
    ↓
BLOCK
```

Additional tests should verify:

* Detector accuracy
* Correct entity spans
* Vector retrieval
* Category normalization
* Risk-score consistency
* Sanitization removing sensitive values
* BLOCK requests never reaching the external LLM
* Audit events containing no raw secrets

---

# Security Principles

Sentinel.AI follows several deliberate security constraints.

### 1. The LLM does not make the final decision

LLMs classify evidence.

The deterministic risk engine decides.

### 2. Sensitive values should not be logged

Detectors should record types and spans rather than raw credentials or PII.

### 3. Sanitization is deterministic

The system should never ask an LLM to decide how sensitive information is redacted.

### 4. BLOCK means no external request

A blocked prompt must never be forwarded to the external LLM provider.

### 5. Detection and enforcement are separated

The Python service analyzes.

The gateway enforces.

This makes the security boundary easier to reason about and test.

---

# Why Sentinel.AI?

Most LLM applications focus on making models more capable.

Sentinel.AI focuses on making their **usage safer**.

The goal is not to replace existing LLM providers.

It is to create a security layer that can sit between existing applications and those providers without requiring users to fundamentally change how they interact with AI.

```text
                  Without Sentinel.AI

Employee ───────────────────────► External LLM
             Sensitive data


                  With Sentinel.AI

Employee
   │
   ▼
Sentinel.AI
   │
   ├── Detect
   ├── Classify
   ├── Score
   ├── Sanitize
   └── Enforce
   │
   ▼
External LLM
```

---

# Project Status

**Status: Active development**

The repository currently contains the gateway and Python detection-service foundation, while the broader architecture is being implemented phase by phase.

The project blueprint defines the intended complete system, but this README deliberately distinguishes **implemented foundation** from **planned functionality** rather than presenting the roadmap as finished software.

---

## Repository

**GitHub:**
https://github.com/Amritansu-Adi/Sentinel.AI

---

## License

MIT License.

---

<div align="center">

### Sentinel.AI

**An AI security gateway for safer LLM adoption.**

Built by **Amritansu**

</div>
