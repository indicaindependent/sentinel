# SENTINEL — Surveillance Contract Intelligence Agent

<div align="center">

![SENTINEL](https://img.shields.io/badge/SENTINEL-OSINT_Intelligence-ef4444?style=for-the-badge&logo=google-cloud&logoColor=white)
![Gemini](https://img.shields.io/badge/Gemini_2.5_Pro-Google_AI-4285F4?style=for-the-badge&logo=google&logoColor=white)
![MongoDB](https://img.shields.io/badge/MongoDB_MCP-Partner_Integration-47A248?style=for-the-badge&logo=mongodb&logoColor=white)
![ADK](https://img.shields.io/badge/Google_ADK-1.32-blue?style=for-the-badge)

**Ask anything about U.S. government surveillance spending. Get answers in seconds.**

🔴 **[Live Demo → sentinel.osintnet.uk](https://sentinel.osintnet.uk)**

*Google Cloud Rapid Agent Hackathon 2026 — MongoDB Track*

</div>

---

## What Is SENTINEL?

Every facial recognition and AI surveillance contract awarded by the U.S. federal government is a public record. None of them are easy to find. We found **249 of them** — totaling **$3.83 billion** — and built an AI agent that lets anyone ask questions about government surveillance spending in plain English and get sourced, verified answers in seconds.

**This is not a chatbot.** SENTINEL is a reasoning agent that:
- Queries a real MongoDB database of 249 verified government contracts
- Uses multi-step reasoning to aggregate, filter, and analyze procurement data
- Surfaces relationships between vendors, agencies, and spending patterns
- Never hallucinates — every answer is grounded in real contract data

Built by **Indica Independent Media**, whose mission is to use information and knowledge to defend vulnerable communities against powerful entities.

---

## Architecture

```
User Query
    │
    ▼
FastAPI (sentinel.osintnet.uk)
    │
    ▼
Google ADK 1.32 Runner
    │
    ├── Gemini 2.5 Pro (reasoning + natural language)
    │
    └── MongoDB MCP Server (mongodb-mcp-server)
            │
            ▼
        MongoDB Atlas
        ├── 249 federal contracts
        ├── $3.83B total value
        ├── 2dsphere geo index
        └── Vendor / agency aggregations
```

### Tech Stack

| Layer | Technology |
|---|---|
| **AI Reasoning** | Gemini 2.5 Pro via Google ADK 1.32 |
| **Agent Framework** | Google Cloud Agent Development Kit (ADK) |
| **MCP Partner** | MongoDB MCP Server (`mongodb-mcp-server`) |
| **Database** | MongoDB Atlas M0 — `sentinel` cluster |
| **Backend** | FastAPI + Python 3.11 + Uvicorn |
| **Frontend** | Vanilla JS + Leaflet.js (dark map UI) |
| **Infrastructure** | Dell OptiPlex → Cloudflare Tunnel → CF Zero Trust |
| **Domain** | sentinel.osintnet.uk |

---

## The Data

SENTINEL's database contains **249 verified U.S. federal government contracts** sourced from:
- SAM.gov (System for Award Management)
- USASpending.gov
- 18 months of OSINT research by Indica Independent Media

**Highlights:**
- 🔴 Palantir USG Inc: **$1.93B** in surveillance/AI contracts
- 🔴 Palantir Technologies: **$1.71B** additional contracts
- Department of Defense: **$2.31B** total surveillance spend
- 29 unique government agencies tracked
- All contracts geocoded by state with 2dsphere indexing

---

## How The Agent Works

SENTINEL uses the **MongoDB MCP Server** as its primary tool for data access. When you ask a question, the ADK agent:

1. **Plans** — Gemini 2.5 Pro determines which MongoDB operations are needed
2. **Executes** — Issues `find`, `aggregate`, `count` commands via MCP
3. **Reasons** — Synthesizes results into a factual, sourced answer
4. **Suggests** — Proposes a follow-up query to dig deeper

### Example Queries
```
"Who are the top 5 vendors by total contract value?"
"Which agencies spent the most on facial recognition?"
"Show me all Clearview AI contracts"
"How many contracts were awarded after 2022 over $10M?"
"What states have the most surveillance contractors?"
```

---

## MongoDB MCP Integration

This project uses the official `mongodb-mcp-server` as the ADK agent's data superpowers:

```python
from google.adk.agents import Agent
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

root_agent = Agent(
    model="gemini-2.5-pro",
    name="sentinel_agent",
    instruction=SENTINEL_INSTRUCTION,
    tools=[
        McpToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(
                    command="npx",
                    args=["-y", "mongodb-mcp-server", "--readOnly"],
                    env={"MDB_MCP_CONNECTION_STRING": os.environ["MONGO_URI"]},
                ),
                timeout=30,
            )
        )
    ],
)
```

**MCP Tools Available to the Agent:**
- `find` — Query contracts with complex filters
- `aggregate` — Group, sum, rank by any field
- `count` — Count matching records
- `collection-schema` — Schema introspection
- `db-stats` — Database overview

---

## Local Setup

```bash
# Clone
git clone https://github.com/indicaindependent/sentinel.git
cd sentinel

# Python venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Node (for MongoDB MCP server)
node --version  # requires v18+

# Environment
cp .env.example .env
# Add your keys:
#   GEMINI_API_KEY=your_key_from_aistudio.google.com
#   MONGO_URI=your_mongodb_atlas_connection_string

# Run
uvicorn main:app --host 0.0.0.0 --port 8001 --reload
```

Open `http://localhost:8001`

---

## API Reference

```
GET  /api/health       — System status + engine info
GET  /api/stats        — Contract totals, top vendors/agencies
GET  /api/contracts    — Query contracts (search, vendor, agency, min_value)
POST /api/query        — Natural language query to Gemini + MongoDB MCP agent
```

---

## Judging Criteria Alignment

| Criterion | SENTINEL's Answer |
|---|---|
| **Technological Implementation** | Gemini 2.5 Pro + ADK 1.32 + MongoDB MCP — full partner stack |
| **Design** | Dark OSINT aesthetic, Leaflet map, responsive, zero UI friction |
| **Potential Impact** | Transparency tool for $3.83B in surveillance spend — accessible to any citizen |
| **Quality of Idea** | Real data, real problem — not a toy demo |

---

## Changelog

### v2.0 — May 5, 2026 — AI Engine Migration: Claude → Gemini 2.5 Pro

> **Full platform migration from Anthropic Claude to Google Gemini 2.5 Pro.**

This version migrated the entire SENTINEL AI reasoning engine from Anthropic's Claude (claude-opus-4-7) to **Google Gemini 2.5 Pro** via the **Google Cloud Agent Development Kit (ADK) 1.32** framework. The migration was completed to align with the **Google Cloud Rapid Agent Hackathon 2026** requirements and unlock the full ADK + MongoDB MCP partner integration stack.

**What changed:**

| Component | Before (v1.x) | After (v2.0) |
|-----------|--------------|--------------|
| AI Model | `claude-opus-4-7` (Anthropic) | `gemini-2.5-pro` (Google) |
| Agent Framework | Direct Anthropic API calls | Google ADK 1.32 `Runner` |
| Tool Integration | Custom function calling | MongoDB MCP Server via `McpToolset` |
| API Key | `ANTHROPIC_API_KEY` | `GEMINI_API_KEY` (AI Studio / GCP) |
| UI model label | `claude-opus-4-7` | `gemini-2.5-pro` |
| Legal text | "powered by Anthropic Claude" | "powered by Google Gemini 2.5 Pro" |

**Why Gemini 2.5 Pro:**
- Native ADK integration — `Agent(model="gemini-2.5-pro")` with zero adapter code
- Official MongoDB MCP partner stack (`McpToolset` + `StdioConnectionParams`)
- Gemini 2.5 Pro's extended context window handles full contract dataset summaries
- Required for Google Cloud Rapid Agent Hackathon eligibility

**Files changed:**
- `agent/sentinel_agent.py` — model swapped, ADK runner introduced
- `agent/tools.py` — MCP toolset replaces direct function calls
- `main.py` — ADK `Runner` + `InMemorySessionService` wired in
- `index.html` — UI model label + consent gate legal text updated
- `requirements.txt` — `google-adk>=1.32`, `anthropic` dependency removed

---

### v1.x — April 2026 — Initial Build (Anthropic Claude)

Original build using `claude-opus-4-7` with direct Anthropic API calls and custom MongoDB tool functions. Deprecated in favor of the ADK-native v2.0 stack.

---

## License

MIT License — see [LICENSE](LICENSE)

---

## About

Built by **[Indica Independent Media](https://osintnet.uk)** — a collective of technologists and artists who use knowledge and information to defend vulnerable communities.

> *"Every surveillance contract is a public record. We just made them readable."*
