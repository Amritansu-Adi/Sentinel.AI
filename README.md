<div align="center">

```
███████╗███████╗███╗   ██╗████████╗██╗███╗   ██╗███████╗██╗      █████╗ ██╗
██╔════╝██╔════╝████╗  ██║╚══██╔══╝██║████╗  ██║██╔════╝██║     ██╔══██╗██║
███████╗█████╗  ██╔██╗ ██║   ██║   ██║██╔██╗ ██║█████╗  ██║     ███████║██║
╚════██║██╔══╝  ██║╚██╗██║   ██║   ██║██║╚██╗██║██╔══╝  ██║     ██╔══██║██║
███████║███████╗██║ ╚████║   ██║   ██║██║ ╚████║███████╗███████╗██║  ██║██║
╚══════╝╚══════╝╚═╝  ╚═══╝   ╚═╝   ╚═╝╚═╝  ╚═══╝╚══════╝╚══════╝╚═╝  ╚═╝╚═╝
```

**AI Traffic Intelligence & Security Platform**

*Intercept · Classify · Sanitize · Protect*

---

[![Node.js](https://img.shields.io/badge/Node.js-20-339933?style=flat-square&logo=node.js&logoColor=white)](https://nodejs.org)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![React](https://img.shields.io/badge/React-18-61DAFB?style=flat-square&logo=react&logoColor=black)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?style=flat-square&logo=typescript&logoColor=white)](https://typescriptlang.org)
[![Apache Kafka](https://img.shields.io/badge/Apache_Kafka-231F20?style=flat-square&logo=apachekafka&logoColor=white)](https://kafka.apache.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?style=flat-square&logo=postgresql&logoColor=white)](https://postgresql.org)
[![Redis](https://img.shields.io/badge/Redis-7-DC382D?style=flat-square&logo=redis&logoColor=white)](https://redis.io)
[![Docker](https://img.shields.io/badge/Docker_Compose-2496ED?style=flat-square&logo=docker&logoColor=white)](https://docs.docker.com/compose)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

</div>

---

## What is SentinelAI?

SentinelAI is a **full-stack AI traffic intelligence platform** that sits as an intelligent proxy between your users and external LLM APIs (OpenAI, Gemini, etc.). Every outbound prompt is intercepted, classified for risk using locally-running HuggingFace models, scored 0–100, sanitized or blocked if sensitive — and surfaced in a live React dashboard.

**Zero paid API dependency. Zero GPU required for inference. Runs entirely on your laptop.**

```
User / App  →  [SentinelAI Gateway]  →  LLM API
                      │
              ┌───────▼────────┐
              │  AI Engine     │  HuggingFace NER
              │  (Python)      │  Toxicity classifier
              │                │  Indian PII classifier
              │  LangChain     │  Chain-of-thought reasoning
              └───────┬────────┘
                      │
              ┌───────▼────────┐
              │  Kafka Bus     │  audit · alert · verdict
              └───────┬────────┘
                      │
              ┌───────▼────────┐
              │  React         │  Live dashboard
              │  Dashboard     │  Prompt Playground
              └────────────────┘
```

---

## Features

| Feature | Status | Description |
|---|---|---|
| **Proxy Gateway** | ✅ Core | Intercepts all outbound LLM traffic. SHA-256 cache. BullMQ async classification. |
| **AI Classification Pipeline** | ✅ Core | Regex fast-path → HuggingFace NER + toxicity → risk score 0–100 |
| **Risk Scoring** | ✅ Core | 5-tier scoring: SAFE / LOW / MEDIUM / HIGH / CRITICAL with configurable weights |
| **Sanitization Engine** | ✅ Core | Replaces detected PII/credentials with typed placeholders before forwarding |
| **Live React Dashboard** | ✅ Core | WebSocket risk feed, Recharts histogram, audit log, alert management |
| **Feature A — Slack Alerts** | ✅ Approved | Slack Block Kit alerts on HIGH/CRITICAL verdicts with retry logic |
| **Feature B — Indian PII Classifier** | ✅ Approved | Fine-tuned BERT for Aadhaar, PAN, UPI IDs, Indian mobile numbers |
| **Feature D — Policy-as-Code** | ✅ Approved | YAML policy files, hot-reload without restart, version history + rollback |
| **Feature F — Prompt Playground** | ✅ Approved | Interactive tab to test any prompt through the full pipeline with SSE streaming |
| **LangChain Reasoning Agent** | ✅ Core | Chain-of-thought for ambiguous payloads (score 40–70). Session-aware memory. |
| **Semantic Deduplication** | ✅ Core | Chroma vector store — detects paraphrased duplicates that hash-cache misses |
| **Shadow Mode** | ✅ Core | Classify without blocking — calibrate thresholds against real traffic |
| **OpenTelemetry Tracing** | ✅ Core | Single trace ID across Node + Python services |
| Feature C — Browser Extension | 🔜 Future | Chrome Manifest V3 extension |
| Feature E — Multi-tenant | 🔜 Future | Org-scoped policies, audit logs, and alerts |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        sentinel-ai/ (monorepo)                      │
│                                                                     │
│  apps/                                                              │
│  ├── gateway/          Node.js · Express · BullMQ · port 3000       │
│  ├── auth/             Node.js · JWT · bcrypt  · port 3001          │
│  ├── alerts/           Node.js · Nodemailer · Slack · port 3002     │
│  ├── admin-api/        Node.js · YAML policy   · port 3003          │
│  ├── ai-engine/        Python · FastAPI · HuggingFace · port 8000   │
│  └── dashboard/        React 18 · Vite · Tailwind · port 5173       │
│                                                                     │
│  packages/                                                          │
│  ├── shared-types/     TypeScript interfaces                        │
│  ├── kafka-client/     KafkaJS wrapper with tracing                 │
│  └── prisma-client/    Prisma ORM + migrations                      │
│                                                                     │
│  infra/                                                             │
│  └── docker-compose.yml  PostgreSQL · Redis · Kafka · Chroma        │
│                                                                     │
│  config/policies/      YAML policy files (Feature D)               │
│  models/               HuggingFace checkpoints + Indian PII model   │
└─────────────────────────────────────────────────────────────────────┘
```

### Risk Scoring

| Score | Level | Action | Example |
|---|---|---|---|
| 0 – 19 | 🟢 SAFE | ALLOW | Generic tech question |
| 20 – 49 | 🔵 LOW | ALLOW + LOG | Vague internal terminology |
| 50 – 74 | 🟡 MEDIUM | SANITIZE | Employee name detected |
| 75 – 89 | 🟠 HIGH | SANITIZE + ALERT | Email or partial credential |
| 90 – 100 | 🔴 CRITICAL | BLOCK + ALERT | Full API key, Aadhaar, SSN |

Score = `keyword_density × 0.4 + category_severity × 0.4 + payload_length_normalized × 0.2`
All weights are configurable from the Admin UI and via YAML policy (Feature D).

---

## Prerequisites

- **Node.js 20+** and **npm 9+**
- **Python 3.11+** and **pip**
- **Docker Desktop** (or Docker Engine + Compose plugin)
- **~3 GB free disk space** (HuggingFace model downloads)
- **No GPU required** — all inference runs on CPU

> **Feature B only:** Training the Indian PII classifier requires a one-time run on [Google Colab](https://colab.research.google.com) (free T4 GPU, ~45 min). See [Feature B setup](#feature-b--indian-pii-classifier).

---

## Quick Start

### 1. Clone the repo

```bash
git clone https://github.com/your-username/sentinel-ai.git
cd sentinel-ai
```

### 2. Set up environment variables

```bash
cp .env.example .env
# Edit .env and fill in the required values (see Environment Variables section below)
```

### 3. Start infrastructure

```bash
docker compose up -d
# Wait for all services to be healthy (~30 seconds)
docker compose ps   # verify: postgres, redis, kafka, chroma all "healthy"
```

### 4. Install Node.js dependencies

```bash
npm install   # installs all workspaces
```

### 5. Run Prisma migrations and seed

```bash
npx prisma migrate deploy --schema packages/prisma-client/prisma/schema.prisma
npx prisma db seed --schema packages/prisma-client/prisma/schema.prisma
```

### 6. Set up Python AI engine

```bash
cd apps/ai-engine
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

> HuggingFace models will download automatically on first startup (~1.2 GB). This only happens once.

### 7. Start all services (in order)

Open separate terminals for each, or use a tool like [tmux](https://github.com/tmux/tmux):

```bash
# Terminal 1 — Auth service
npm run dev --workspace=apps/auth

# Terminal 2 — AI engine (wait for "Application startup complete")
cd apps/ai-engine && source venv/bin/activate && uvicorn main:app --reload --port 8000

# Terminal 3 — Admin API
npm run dev --workspace=apps/admin-api

# Terminal 4 — Gateway
npm run dev --workspace=apps/gateway

# Terminal 5 — Alert service
npm run dev --workspace=apps/alerts

# Terminal 6 — Dashboard
npm run dev --workspace=apps/dashboard
```

### 8. Open the dashboard

```
http://localhost:5173
```

Login with the seeded admin account:
- **Email:** `admin@sentinelai.local`
- **Password:** `changeme123`

> Change the password immediately via the Admin UI.

---

## Environment Variables

Create a `.env` file in the repo root. Never commit it — it's already in `.gitignore`.

```env
# Database
DATABASE_URL=postgres://sentinel:sentinel@localhost:5432/sentinelai

# Redis
REDIS_URL=redis://localhost:6379

# Kafka
KAFKA_BROKERS=localhost:9092

# Auth
JWT_SECRET=your-256-bit-secret-here   # generate: openssl rand -hex 32

# Internal service URLs
AI_ENGINE_URL=http://localhost:8000
CHROMA_URL=http://localhost:8001

# Email (use Mailtrap for dev — no real emails sent)
SMTP_HOST=smtp.mailtrap.io
SMTP_PORT=2525
SMTP_USER=your-mailtrap-user
SMTP_PASS=your-mailtrap-pass

# Feature A — Slack (optional during development)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
SLACK_ALERT_CHANNEL=#sentinelai-alerts

# Feature D — Policy config
POLICY_CONFIG_PATH=config/policies/active.yaml

# Development defaults
SHADOW_MODE=true       # set to false to enable enforcement
LOG_LEVEL=debug        # info in production
OTEL_EXPORTER_ENDPOINT=http://localhost:4318
```

Copy `.env.example` for a template with all keys pre-filled with safe placeholder values.

---

## HuggingFace Models

All models run locally on CPU. Downloaded automatically on first AI engine startup.

| Model | Task | Approx. size | CPU inference |
|---|---|---|---|
| `dslim/bert-base-NER` | Named entity recognition | 400 MB | ~200ms/request |
| `unitary/toxic-bert` | Toxicity classification | 400 MB | ~150ms/request |
| `iamollas/ethos-hate-speech-detection` | Hate speech (secondary) | 400 MB | ~150ms/request |
| `sentence-transformers/all-MiniLM-L6-v2` | Embeddings (Chroma) | 80 MB | ~50ms/request |
| Custom checkpoint (Feature B) | Indian PII detection | ~400 MB | ~100ms/request |

Model cache location: `models/` directory in the repo root.

---

## Feature B — Indian PII Classifier

This is the only part of the project that requires a GPU, and it's a one-time training step on Google Colab's free T4 GPU.

**Covered patterns:** Aadhaar numbers · PAN card numbers · UPI IDs · Indian mobile numbers (+91) · Indian postal addresses

### Training on Google Colab

1. Go to [colab.research.google.com](https://colab.research.google.com) → New notebook
2. Runtime → Change runtime type → **T4 GPU**
3. Upload `models/train_indian_pii.py` or paste it into a cell
4. Run the notebook (~45 minutes)
5. Download the exported checkpoint and place it in `models/indian_pii_classifier/`
6. Commit the checkpoint to the repo

### Fallback (no training)

If you skip training, the AI engine falls back to **regex-only Indian PII detection** — this covers ~90% of cases and works fine for a demo. Set `INDIAN_PII_MODEL=regex` in `.env` to use the fallback explicitly.

---

## Feature D — Policy-as-Code

Policies are YAML files in `config/policies/`. The Gateway hot-reloads the active policy file on change — no restart required.

```yaml
# config/policies/active.yaml
version: '1.0'
name: default-policy
shadow_mode: false
model_version: '1.2.0'
thresholds:
  safe_max: 19
  low_max: 49
  medium_max: 74
  high_max: 89
scoring_weights:
  keyword_density: 0.40
  category_severity: 0.40
  payload_length: 0.20
blocked_domains: []
allowed_domains:
  - api.openai.com
  - generativelanguage.googleapis.com
```

**Edit the file → Gateway picks up the change in < 1 second → no service restart.**

Policy history is tracked in the `policy_history` Postgres table. To roll back:

```bash
curl -X POST http://localhost:3003/admin/policy/rollback \
  -H "Authorization: Bearer <your-admin-jwt>"
```

---

## Feature F — Prompt Playground

Available at `http://localhost:5173/playground`.

Type any prompt → submit → watch the full classification pipeline run in real time via Server-Sent Events:

1. Regex fast-path matches
2. NER entities found
3. Toxicity scores
4. Risk score with category weight breakdown
5. LangChain reasoning steps (if score is 40–70)
6. Final verdict + confidence
7. Top-3 semantically similar past prompts from the audit log

**Rate limit:** 10 playground requests per user per minute (Redis sliding window).

---

## Demo Script

A 3-minute walkthrough for interviews or hackathon demos:

```
1. Shadow Mode        Open dashboard → Policies → Shadow Mode ON
                      Show: "What would have been blocked today?"

2. SANITIZE           Prompt Playground → type "Hi, my email is john@company.com"
                      Show: MEDIUM verdict, email replaced with [EMAIL]

3. BLOCK              Prompt Playground → type "My AWS key is AKIAIOSFODNN7EXAMPLE"
                      Show: CRITICAL verdict, request blocked, Slack alert fires

4. Hot-reload         Edit config/policies/active.yaml → lower safe_max to 10
                      Show: Gateway reloads, risk distribution shifts in real time

5. Session memory     Send 5 borderline prompts in quick succession
                      Show: 6th prompt gets higher risk due to session pattern
```

---

## Kafka Topics

| Topic | Producer | Consumers |
|---|---|---|
| `prompt.intercepted` | Gateway | AI engine, Audit service, Dashboard |
| `prompt.verdict` | AI engine | Gateway (enforce), Dashboard (WebSocket), Playground |
| `threat.alert` | AI engine | Alert service (email + Slack), Dashboard (notification bell) |
| `session.context` | Gateway | AI engine (session memory updates) |
| `policy.updated` | Admin API | Gateway (reload YAML), AI engine (recalibrate) |

**Debug Kafka manually:**

```bash
# Consume all verdict events
docker exec -it sentinel-kafka kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic prompt.verdict \
  --from-beginning
```

---

## Database Schema

```
audit_logs     — one row per intercepted prompt (hash only, never raw payload)
users          — admin · analyst · viewer roles, bcrypt passwords
alerts         — OPEN → REVIEWING → RESOLVED · DISMISSED lifecycle
policies       — single active policy row, JSONB thresholds
sessions       — per-user session aggregation for LangChain context
policy_history — full audit trail of every policy change (enables rollback)
```

Run migrations:

```bash
npx prisma migrate deploy --schema packages/prisma-client/prisma/schema.prisma
```

---

## Project Structure

```
sentinel-ai/
├── apps/
│   ├── gateway/            Express proxy, BullMQ, Redis cache, YAML loader
│   ├── auth/               JWT auth — register, login, role management
│   ├── alerts/             Kafka consumer, Nodemailer, Slack webhook
│   ├── admin-api/          Policy CRUD, shadow mode, YAML validation
│   ├── ai-engine/          FastAPI, HuggingFace pipelines, LangChain agent
│   └── dashboard/          React 18 + Vite + Tailwind + Recharts
├── packages/
│   ├── shared-types/       TypeScript interfaces shared across services
│   ├── kafka-client/       KafkaJS producer/consumer wrapper
│   └── prisma-client/      Prisma schema + migrations
├── config/
│   └── policies/
│       └── active.yaml     Active policy file (hot-reloaded)
├── infra/
│   └── docker-compose.yml  PostgreSQL, Redis, Kafka, Zookeeper, Chroma
├── models/
│   ├── train_indian_pii.py Training script (run on Colab)
│   └── indian_pii_classifier/  Trained checkpoint (committed after Colab run)
├── docs/                   Architecture decision records, API specs
├── .env.example            Template — copy to .env and fill in
└── README.md               This file
```

---

## Startup Order

Services have dependencies — start them in this order:

```
1. docker compose up -d          infrastructure (Postgres, Redis, Kafka, Chroma)
2. apps/auth                     JWT dependency of all other services
3. apps/ai-engine                loads HuggingFace models on startup (~20–60s)
4. apps/admin-api                policy must exist before Gateway reads it
5. apps/gateway                  reads active.yaml on startup
6. apps/alerts                   Kafka consumer + email/Slack config
7. apps/dashboard                Vite dev server on :5173
```

---

## Troubleshooting

**AI engine is slow to start**
Models download on first run (~1.2 GB). Subsequent starts are fast. Check `/health` endpoint: `curl http://localhost:8000/health` — wait for `{"status":"ready"}`.

**Kafka connection refused**
Wait 10–15 seconds after `docker compose up` for Kafka + Zookeeper to fully initialize. Check with `docker compose ps`.

**Redis cache not working**
Verify `REDIS_URL` in `.env` matches the Docker port. Default: `redis://localhost:6379`.

**Prisma migration errors**
Ensure `DATABASE_URL` is correct and the Postgres container is healthy before running migrations.

**Chroma embedding errors**
Chroma runs on port 8001. Verify with `curl http://localhost:8001/api/v1/heartbeat`.

**Indian PII model not found**
Either run the Colab training script and place the checkpoint in `models/indian_pii_classifier/`, or set `INDIAN_PII_MODEL=regex` in `.env` to use the regex fallback.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, Vite, TypeScript, Tailwind CSS v3, Recharts, React Query |
| Backend (API services) | Node.js 20, Express, TypeScript, Prisma ORM |
| AI engine | Python 3.11, FastAPI, LangChain, HuggingFace Transformers |
| Message bus | Apache Kafka (KafkaJS, confluent-kafka-python) |
| Job queue | BullMQ (Redis-backed) |
| Database | PostgreSQL 16 |
| Cache | Redis 7 |
| Vector store | Chroma (local, embedded) |
| Auth | JWT (jsonwebtoken), bcrypt |
| Observability | OpenTelemetry, Pino (structured JSON logs) |
| Infrastructure | Docker Compose |

---

## License

MIT — see [LICENSE](LICENSE).

---

<div align="center">

Built as a portfolio project · Student Edition · No GPU required · Zero paid API dependency

</div>
