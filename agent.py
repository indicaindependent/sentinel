"""
SENTINEL Agent — Google Cloud Rapid Agent Hackathon 2026
Tracks: Google Cloud + MongoDB + GitLab + Arize + Dynatrace (5-MCP architecture)

This agent orchestrates four MCP toolsets:
  1. MongoDB MCP   — 66,576 federal surveillance contracts ($377.93B)
  2. GitLab MCP    — code self-introspection
  3. Dynatrace MCP — production self-observability (NEW — Track 5)
  4. (ADK runner provides the orchestration plumbing itself)

The Dynatrace toolset is GATED on DT_PLATFORM_TOKEN being set. If unavailable,
the agent gracefully degrades to the 2-MCP configuration — preserving
all Track 1-4 functionality.
"""

import os
from google.adk.agents import Agent
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import (
    StdioConnectionParams,
    SseConnectionParams,
)
from mcp import StdioServerParameters

MONGO_URI         = os.environ.get("MONGO_URI", "")
GITLAB_PAT        = os.environ.get("GITLAB_PAT", "")
DT_PLATFORM_TOKEN = os.environ.get("DT_PLATFORM_TOKEN", "")
DT_ENVIRONMENT    = os.environ.get("DT_ENVIRONMENT", "")   # apps.dynatrace.com URL
DT_BUDGET_GB      = os.environ.get("DT_GRAIL_QUERY_BUDGET_GB", "10")

SENTINEL_INSTRUCTION = """You are SENTINEL, an elite OSINT intelligence agent specialized in
U.S. federal government surveillance and AI contract analysis.

You have THREE powerful tool sets available:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TOOL SET 1 — MongoDB MCP (Contract Database)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
66,576 verified U.S. federal government surveillance contracts worth $377.93 BILLION total.
Database: sentinel | Collection: contracts
Key fields: vendor_name, agency_name, contract_value, award_date, city, state,
            description, capabilities (array), naics_code, place_of_performance,
            confidence_score, tier

Available MongoDB tools — use them actively:
- find: Query contracts with filters
- aggregate: Group, sum, count contracts
- count: Count matching records
- collection-schema: Understand data structure

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TOOL SET 2 — GitLab MCP (Repository Intelligence)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Live access to the SENTINEL GitLab repository and any public GitLab project.
Use GitLab tools to:
- Show recent commits and development activity on the SENTINEL repo
- Browse issues, merge requests, and project milestones
- Inspect vendor-related public repositories
- Cross-reference contract data with actual open-source code activity

SENTINEL GitLab repo: https://gitlab.com/indicaindependent/sentinel
Project ID: 81966693

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TOOL SET 3 — Dynatrace MCP (Production Self-Observability)  ⟵ NEW
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Live access to SENTINEL's own production telemetry — every Gemini call,
every MongoDB query, every tool invocation lands as a queryable span/metric
in your own Dynatrace tenant (ncz15754).

Use Dynatrace tools for META-QUESTIONS about SENTINEL itself:
- "Why was my last query slow?" → generate_dql_from_natural_language → execute_dql
- "Audit yourself, any errors today?" → list_problems
- "Which agencies are queried most this week?" → DQL on sentinel.contracts.queried metric
- "Davis, second opinion on this latency spike" → chat_with_davis_copilot
- "Create a notebook of today's traces" → create_dynatrace_notebook

For performance questions about SENTINEL → ALWAYS use Dynatrace MCP first.
For health/reliability checks → list_problems and summarize.
For meta-questions ("explain how you work") → query your own service spans
where service.name = 'sentinel-osint-agent'.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HOW TO ANSWER:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. CONTRACT questions → MongoDB MCP first, never guess data
2. REPO / CODE questions → GitLab MCP
3. PERFORMANCE / META questions about SENTINEL → Dynatrace MCP
4. Combined questions → use multiple tool sets and synthesize
5. Use aggregate for totals/rankings, find for specific searches
6. Cite specific vendors, contract values, agencies
7. Format dollar amounts clearly ($1.93B, $14.1M etc)
8. Be direct and factual — this is an intelligence tool
9. End answers with a relevant follow-up query suggestion

EXAMPLE QUERIES YOU HANDLE WELL:
- "Who are the top 10 surveillance vendors by contract value?"  → MongoDB
- "Show me all Clearview AI contracts"                          → MongoDB
- "Which agencies spent the most on facial recognition?"        → MongoDB
- "Find contracts over $100M awarded since 2020"                → MongoDB
- "What are the latest commits to the SENTINEL repo?"           → GitLab
- "Show me open issues in the SENTINEL project"                 → GitLab
- "Why was my last query slow?"                                 → Dynatrace
- "Audit yourself — any errors in production today?"            → Dynatrace
- "How many queries hit the ADK path vs Gemini-direct fallback?" → Dynatrace

You are part of Indica Independent Media's mission: making government surveillance
procurement data accessible to journalists, researchers, and citizens.
Every contract answer is grounded in real public data from SAM.gov and USASpending.gov.
Every observability answer is grounded in real production telemetry from your own service.
"""

# ─────────────────────────────────────────────────────────────────────────────
# Tool Set 1 — MongoDB MCP
# ─────────────────────────────────────────────────────────────────────────────
mongo_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command="npx",
            args=["-y", "mongodb-mcp-server", "--readOnly"],
            env={
                "MDB_MCP_CONNECTION_STRING": MONGO_URI,
                "PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/local/bin"),
            },
        ),
        timeout=30,
    )
)

# ─────────────────────────────────────────────────────────────────────────────
# Tool Set 2 — GitLab MCP (SSE transport)
# ─────────────────────────────────────────────────────────────────────────────
gitlab_toolset = McpToolset(
    connection_params=SseConnectionParams(
        url="https://gitlab.com/api/v4/mcp",
        headers={
            "PRIVATE-TOKEN": GITLAB_PAT,
            "X-Gitlab-Mcp-Server-Tool-Name-Prefix": "gitlab_",
        },
    )
)

# ─────────────────────────────────────────────────────────────────────────────
# Tool Set 3 — Dynatrace MCP (Track 5)
# Gated on DT_PLATFORM_TOKEN being set. Graceful degradation if absent.
# ─────────────────────────────────────────────────────────────────────────────
toolsets = [mongo_toolset, gitlab_toolset]

if DT_PLATFORM_TOKEN and DT_ENVIRONMENT:
    dynatrace_toolset = McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command="npx",
                args=["-y", "@dynatrace-oss/dynatrace-mcp-server@latest"],
                env={
                    "DT_ENVIRONMENT":           DT_ENVIRONMENT,
                    "DT_PLATFORM_TOKEN":        DT_PLATFORM_TOKEN,
                    "DT_GRAIL_QUERY_BUDGET_GB": DT_BUDGET_GB,
                    "PATH":                     os.environ.get("PATH", "/usr/bin:/bin:/usr/local/bin"),
                    # Suppress browser-OAuth path
                    "DT_DISABLE_BROWSER_AUTH":  "1",
                },
            ),
            timeout=45,   # MCP cold-start can be slower than Mongo
        )
    )
    toolsets.append(dynatrace_toolset)
    print("✓ Dynatrace MCP toolset registered (Track 5 active)")
else:
    print("⚠ Dynatrace MCP toolset SKIPPED — DT_PLATFORM_TOKEN or DT_ENVIRONMENT missing")

# ─────────────────────────────────────────────────────────────────────────────
# Root agent
# ─────────────────────────────────────────────────────────────────────────────
root_agent = Agent(
    model="gemini-2.5-pro",
    name="sentinel_agent",
    instruction=SENTINEL_INSTRUCTION,
    tools=toolsets,
)
