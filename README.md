<div align="center">

```text
███████╗███████╗███╗   ██╗████████╗██╗███╗   ██╗███╗   ██╗███████╗██╗      █████╗ ██╗
██╔════╝██╔════╝████╗  ██║╚══██╔══╝██║████╗  ██║████╗  ██║██╔════╝██║     ██╔══██╗██║
███████╗█████╗  ██╔██╗ ██║   ██║   ██║██╔██╗ ██║██╔██╗ ██║█████╗  ██║     ███████║██║
╚════██║██╔══╝  ██║╚██╗██║   ██║   ██║██║╚██╗██║██║╚██╗██║██╔══╝  ██║     ██╔══██║██║
███████║███████╗██║ ╚████║   ██║   ██║██║ ╚████║██║ ╚████║███████╗███████╗██║  ██║██║
╚══════╝╚══════╝╚═╝  ╚═══╝   ╚═╝   ╚═╝╚═╝  ╚═══╝╚═╝  ╚═══╝╚══════╝╚══════╝╚═╝  ╚═╝╚═╝
```

# Sentinel.AI

### AI-Powered LLM Traffic Security Gateway

**Intercept · Detect · Score · Sanitize · Protect**

[![Node.js](https://img.shields.io/badge/Node.js-20+-339933?style=flat-square&logo=node.js&logoColor=white)](https://nodejs.org/)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Python-1C3C3C?style=flat-square)](https://www.langchain.com/langgraph)
[![HuggingFace](https://img.shields.io/badge/HuggingFace-Transformers-FFD21E?style=flat-square&logo=huggingface&logoColor=black)](https://huggingface.co/)
[![FAISS](https://img.shields.io/badge/FAISS-Vector_Search-0468FF?style=flat-square)](https://github.com/facebookresearch/faiss)
[![MongoDB](https://img.shields.io/badge/MongoDB-7-47A248?style=flat-square&logo=mongodb&logoColor=white)](https://www.mongodb.com/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white)](https://www.docker.com/)

</div>

---

## SentinelAI

SentinelAI is a policy-enforcing gateway for external LLM requests. It inspects the last user message, gathers regex, NER, and company-knowledge evidence, and makes a deterministic `ALLOW`, `SANITIZE`, or `BLOCK` decision before an external provider is called.

## Current Architecture

```text
Client / dashboard
        |
        v
node-gateway :4000 ---- MongoDB :27017
        |
        v
python-detection :8000 ---- Ollama :11434 (optional local categorizer)
        |
        v
External OpenAI-compatible LLM provider
```

The `dashboard/` directory is a separate Vite application. It provides the admin view and the identified end-user chat view at `/chat`.

### Enforcement policy

- A vector match classified `CONFIDENTIAL` at or above the similarity floor is `BLOCK`.
- Regex or sufficiently confident NER findings are masked and forwarded as `SANITIZE`.
- Internal vector matches and non-spannable categorizer findings are forwarded as `ALLOW` with an advisory flag.
- Requests with no evidence are `ALLOW` with no flag.

Risk score and risk level are recorded for audit and dashboard reporting. They do not override the action policy.

## Requirements

- Docker Desktop with Docker Compose
- A MongoDB deployment (the local Compose service is suitable for development)
- An OpenAI-compatible external LLM endpoint and API key
- At least 4 GB of free disk space for Python dependencies and downloaded HuggingFace models

Ollama is included for local categorization. A Groq account can be used instead by setting `RISK_MODEL_PROVIDER=groq`.

## Local Setup

From the repository root:

```powershell
Copy-Item .env.example .env
# Edit .env and set ADMIN_PASSWORD, JWT_SECRET, and external LLM settings.
docker compose up --build -d
docker compose ps
```

Seed the initial policy after MongoDB is running:

```powershell
Push-Location node-gateway
npm install
npm run seed:policy
Pop-Location
```

The services are available at:

| Service | URL | Purpose |
|---|---|---|
| Gateway | `http://localhost:4000` | Client-facing API |
| Detection | `http://localhost:8000` | Internal analysis API |
| MongoDB | `mongodb://localhost:27017` | Audit and policy data |
| Ollama | `http://localhost:11434` | Optional local categorizer |

The first detection request may be slow while HuggingFace models are downloaded and loaded.

## Dashboard

```powershell
Push-Location dashboard
npm install
Copy-Item .env.example .env
npm run dev
Pop-Location
```

Open `http://localhost:5173`. Set `VITE_GATEWAY_URL` in `dashboard/.env` when the gateway is not on `http://localhost:4000`.

For a production static build:

```powershell
Push-Location dashboard
npm ci
npm run build
Pop-Location
```

Publish `dashboard/dist/` with a static host such as Vercel, Cloudflare Pages, or an HTTPS reverse proxy. Set `VITE_GATEWAY_URL` to the public HTTPS gateway URL at build time.

## Environment Variables

Copy `.env.example` to `.env`. Never commit `.env`.

| Variable | Required | Description |
|---|---:|---|
| `MONGODB_URI` | Yes | MongoDB connection string |
| `JWT_SECRET` | Yes | Long random secret for admin tokens |
| `ADMIN_EMAIL` | Yes | Admin login email |
| `ADMIN_PASSWORD` | Yes | Strong admin login password |
| `DASHBOARD_ORIGIN` | Yes in production | Exact dashboard origin allowed by CORS |
| `EXTERNAL_LLM_BASE_URL` | Yes | Provider base URL, with or without `/v1/chat/completions` |
| `EXTERNAL_LLM_API_KEY` | Yes | Provider API key |
| `RISK_MODEL_PROVIDER` | No | `local` or `groq` |
| `OLLAMA_BASE_URL` | No | Defaults to the Compose Ollama service |
| `OLLAMA_MODEL` | No | Local categorizer model |
| `GROQ_API_KEY` / `GROQ_MODEL` | For Groq | Groq categorizer settings |
| `VECTOR_MODEL_NAME` | No | Sentence-transformers model |
| `NER_MODEL_NAME` | No | HuggingFace NER model |
| `FAISS_INDEX_PATH` | No | Company-knowledge index path |
| `POLICY_CACHE_TTL_SECONDS` | No | Gateway policy cache duration; defaults to 30 seconds |

`DETECTION_SERVICE_URL` and `GATEWAY_PORT` are set for the Compose network in `docker-compose.yml`. The threshold variables document the fallback policy used when MongoDB has no active policy.

Generate a secret on PowerShell with:

```powershell
([Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32))).ToLower()
```

## API

### Health checks

```powershell
Invoke-RestMethod http://localhost:4000/health
Invoke-RestMethod http://localhost:8000/health
```

### Chat completions

`POST /v1/chat/completions` accepts an OpenAI-compatible request. The gateway analyzes the last message, logs the decision, sanitizes it when required, and forwards allowed requests to the configured provider.

```json
{
  "model": "external-model",
  "messages": [{"role": "user", "content": "Hello"}]
}
```

Responses for forwarded requests preserve the provider body and add:

- `X-Sentinel-Action`: `ALLOW` or `SANITIZE`
- `X-Sentinel-Flags`: JSON advisory or masking metadata when applicable

Blocked requests return HTTP `403` with `request_id`, `risk_score`, `categories`, and `rewrite_guidance`. The guidance is category-level and does not reveal matched company documents.

Admin login is `POST /auth/login`. Dashboard statistics require the returned Bearer token at `/stats/summary` and `/stats/employees`.

## Production Deployment

This repository does not contain cloud credentials or a selected hosting provider, so no production deployment can be completed from source control alone. The supported production shape is:

1. Run `node-gateway` and `python-detection` as private services on a Docker-capable host.
2. Use MongoDB Atlas or a private managed MongoDB instance; seed `policy_config` once with `npm run seed:policy`.
3. Use a managed HTTPS static host for `dashboard/dist/`.
4. Configure the dashboard's `VITE_GATEWAY_URL` to the HTTPS gateway URL.
5. Configure `DASHBOARD_ORIGIN` to that exact dashboard origin.
6. Configure an external LLM provider, or run Ollama on a host with persistent model storage.

Before exposing the gateway:

- Set non-default `JWT_SECRET` and `ADMIN_PASSWORD`.
- Do not expose ports `27017`, `8000`, or `11434` publicly.
- Put the gateway behind HTTPS and restrict CORS to the dashboard origin.
- Store secrets in the host/provider secret manager, not in Compose files or git.
- Add backups and access controls for MongoDB audit data.
- Confirm the external provider is configured before accepting traffic; otherwise the gateway returns `503` rather than forwarding unsafely.
- Pin image versions and review the downloaded model sizes before selecting a small production host.

The included `docker-compose.yml` is a local deployment baseline. It publishes internal ports for local verification and should not be used unchanged as a public internet perimeter.

## Verification

Run the focused checks:

```powershell
node-gateway\scripts\testPolicyCache.js
Push-Location dashboard
node scripts/testIdentity.js
node scripts/testChatResponse.js
npm ci
npm run build
Pop-Location
```

With the stack running, execute the live suite from the repository root:

```powershell
python manual_test_suite.py
```

Results are written under `test_logs/`. The previous recorded run completed 108 cases with 96 matches, 10 mismatches, 2 reviews, and 0 errors, before the latest risk-engine fixes. Re-run the suite after restarting the detection service; do not call the deployment production-ready until that post-fix run is reviewed.

## Repository Layout

```text
node-gateway/       Express gateway, Mongo models, auth, policy cache
python-detection/   FastAPI detection pipeline and deterministic risk engine
dashboard/          React/Vite admin and end-user chat UI
test_logs/          Manual-suite output
manual_test_suite.py
docker-compose.yml
.env.example
```

## License

No license file is currently included. Add a license before distributing the project publicly.
