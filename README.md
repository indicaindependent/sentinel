# SENTINEL — Surveillance Contract Intelligence Agent

[![Live Demo](https://img.shields.io/badge/Live%20Demo-sentinel.osintnet.uk-ef4444?style=for-the-badge)](https://sentinel.osintnet.uk)
[![Google Cloud](https://img.shields.io/badge/Google%20ADK-1.32-4285F4?style=for-the-badge&logo=google-cloud)](https://cloud.google.com)
[![Gemini](https://img.shields.io/badge/Gemini-2.5%20Pro-8E75B2?style=for-the-badge&logo=google)](https://deepmind.google/gemini)
[![MongoDB](https://img.shields.io/badge/MongoDB-MCP-47A248?style=for-the-badge&logo=mongodb)](https://mongodb.com)
[![GitLab](https://img.shields.io/badge/GitLab-MCP%20Track-FC6D26?style=for-the-badge&logo=gitlab)](https://gitlab.com/indicaindependent/sentinel)
[![Arize AX](https://img.shields.io/badge/Arize%20AX-Tracing-7C3AED?style=for-the-badge)](https://arize.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)

> *$3.83 billion in government surveillance contracts. One agent to find them, trace them, and explain them.*

---

## What Is SENTINEL?

SENTINEL is an AI-powered OSINT agent that makes government surveillance spending transparent and searchable. It holds a verified dataset of **249 surveillance contracts** totaling **$3.83 billion** — covering facial recognition, predictive policing, location tracking, biometric databases, and more.

Ask it anything in plain English. Get sourced, grounded answers in seconds.

```
"Which agency spent the most on facial recognition?"
"Show me all Palantir contracts over $100 million"
"What surveillance tools did DHS purchase in 2023?"
"Which vendors supply both ICE and CBP?"
```

---

## Architecture — 4-Track Integration Stack

### Track 1 — Google Cloud (Core Intelligence)
- **Google ADK 1.32** — agent orchestration and tool-calling loop
- **Gemini 2.5 Pro** — reasoning, synthesis, natural language generation
- FastAPI + Uvicorn backend, deployed on Ubuntu 24.04 via systemd
- Live endpoint: `sentinel.osintnet.uk`

### Track 2 — MongoDB (Knowledge Store + MCP)
- **MongoDB Atlas** stores all 249 verified surveillance contracts
- **MongoDB MCP Server** gives the ADK agent structured real-time access
- Zero hallucination: every answer grounded in live contract records
- Supports filtering, aggregation, and cross-vendor analysis

### Track 3 — GitLab (Version Control + MCP)
- Full source hosted at `gitlab.com/indicaindependent/sentinel`
- **GitLab MCP Server** integrated via `SseConnectionParams`
- Agent can introspect its own codebase — a self-aware OSINT tool
- MIT licensed, OSI compliant

### Track 4 — Arize AX (Observability + Tracing)
- **Arize AX** captures full OpenInference traces of every agent invocation
- Every Gemini call, MongoDB query, and tool decision logged as a span
- Integrated via `arize-otel` + `openinference-instrumentation-google-genai`
- Project: `sentinel-surveillance` in Arize space
- Production-grade LLM observability for a public-interest tool

---

## Dataset

| Metric | Value |
|--------|-------|
| Total contracts | 249 |
| Total value | $3.83 billion |
| Sources | USASpending.gov + agency portals |
| Top vendor | Palantir USG Inc ($1.76B) |
| Coverage | Facial recognition, predictive policing, location tracking, biometrics, CCTV, social monitoring |

---

## Tech Stack

```
Backend:     Python 3.12, FastAPI, Uvicorn
AI Agent:    Google ADK 1.32, Gemini 2.5 Pro
Database:    MongoDB Atlas + Motor (async driver)
MCP Tools:   MongoDB MCP Server, GitLab MCP Server
Tracing:     Arize AX, arize-otel, OpenInference, OpenTelemetry
Frontend:    Vanilla JS/HTML, served via FastAPI static files
Infra:       Cloudflare Workers, Cloudflare Zero Trust, Ubuntu 24.04
Deploy:      systemd service, Cloudflare Tunnel
```

---

## Quick Start

```bash
git clone https://github.com/indicaindependent/sentinel
cd sentinel
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Set environment variables
export GEMINI_API_KEY="your-key"
export MONGO_URI="your-mongodb-uri"
export ARIZE_SPACE_ID="your-space-id"
export ARIZE_API_KEY="your-arize-key"
export ARIZE_PROJECT_NAME="sentinel-surveillance"

python main.py
```

---

## Hackathon Tracks

| Track | Integration | Status |
|-------|-------------|--------|
| Google Cloud Rapid Agent | ADK 1.32 + Gemini 2.5 Pro | ✅ Live |
| MongoDB | Atlas + MCP Server | ✅ Live |
| GitLab | Repo + MCP Server | ✅ Live |
| Arize AX | arize-otel + OpenInference | ✅ Live |

---

## Changelog

### v3.0 — May 6, 2026
- ✅ Arize AX tracing integration — full OpenInference span coverage
- ✅ GitLab MCP dual-tool integration alongside MongoDB MCP
- ✅ Migrated tracing to `arize-otel` official SDK (HTTP transport)
- ✅ All 4 hackathon tracks simultaneously active

### v2.0 — May 5, 2026
- ✅ Full Claude → Gemini 2.5 Pro migration
- ✅ GitLab repository + MIT license
- ✅ MongoDB MCP server integration

### v1.0 — May 3, 2026
- ✅ Initial deployment
- ✅ 249 contracts dataset
- ✅ FastAPI + ADK + Gemini stack

---

## License

MIT License — see [LICENSE](LICENSE)

Built by [Indica Independent Media](https://osintnet.uk) | Tools free at point of use.
