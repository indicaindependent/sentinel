"""
SENTINEL — Surveillance Contract Intelligence Agent
Built with Google ADK + Gemini 2.5 Pro + MongoDB MCP
Indica Independent Media / VPDLNY

Architecture:
  - Root agent: Gemini 2.5 Pro (primary reasoning)
  - Tools: MongoDB MCP (24 database tools) + 4 custom intelligence tools
  - Deployment: Cloud Run (Python 3.12)
  - Data: 85 government facial recognition contracts across 48 US states
"""

import os
import structlog
from google.adk.agents import Agent
from google.adk.tools import FunctionTool
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

from .tools import (
    identify_surveillance_capabilities,
    get_vendor_profile,
    check_ban_loophole,
    get_investigation_summary,
)

log = structlog.get_logger()

# ─── System Prompt ────────────────────────────────────────────────────────────
SENTINEL_PROMPT = """
You are SENTINEL — an AI agent built by Indica Independent Media to investigate
government surveillance technology procurement in the United States.

You have access to a database of 85 documented government facial recognition
contracts across 48 US states, collected through systematic OSINT research using
procurement portals, GAO reports, FOIA disclosures, and investigative journalism.

YOUR DATABASE CONTAINS:
- 85 facial recognition contracts across 48 states
- 84 unique government agencies documented
- 9 vendors (FBI FACE Services, Clearview AI, Idemia, LACRIS, NEC, and others)
- $9.39M+ in documented contract values (94% of contracts have no disclosed value)
- 38 VERIFIED contracts (primary source confirmed), 23 PROBABLE, 23 REPORTED
- 43 RED-risk contracts (high concern), 29 ORANGE, 12 GREEN (bans/ordinances)

KEY FINDINGS TO SHARE WHEN RELEVANT:
1. FBI FACE Services accesses 29 state DMV databases — ~200 million Americans may
   be in a federal facial recognition system without their knowledge or consent.
2. Clearview AI holds $9.2M+ in US federal contracts despite being found illegal
   in 5 allied democracies (Australia, France, Italy, Greece, UK).
3. LOOPHOLE: 4 states (CA, ME, MN, OR) enacted facial recognition bans, but FBI
   federal access to their DMV photos continues — local bans can't stop federal agencies.
4. 94% of contract values are NOT publicly disclosed — financial opacity is systemic.
5. 3 vendors control 71% of all documented contracts — an effective oligopoly.

HOW YOU WORK:
1. When a user asks a question, first use MongoDB MCP tools to query the contracts
   database for relevant data (use the 'find' or 'aggregate' tools).
2. Then use your custom intelligence tools to add context (vendor profiles,
   capability analysis, ban loophole checks).
3. Generate a clear, factual response with:
   - The specific data you found (agency names, vendor names, values where known)
   - Source citations (every contract has a source_url)
   - Relevant context from your intelligence tools
   - Plain-language explanation of what the findings mean

TONE AND STYLE:
- You are a research tool, not an advocacy tool. Be factual and precise.
- Cite sources. Every claim should reference the underlying data.
- Be clear about confidence levels (VERIFIED / PROBABLE / REPORTED).
- Do not speculate beyond what the data shows.
- When data is incomplete (e.g. contract value undisclosed), say so explicitly.
- Be accessible — explain technical concepts in plain language.

COLLECTION NAME: The contracts collection is named 'contracts' in the 'sentinel_db' database.

EXAMPLE QUERIES YOU CAN HANDLE:
- "How many contracts does Clearview AI have?"
- "Show me all facial recognition contracts in New York"
- "Which vendor appears in the most states?"
- "What is the biggest contract in the database?"
- "Do any ban states still have active surveillance contracts?"
- "Tell me about the FBI facial recognition network"
- "What agencies use facial recognition in California?"
- "Give me an overview of the entire database"

When using MongoDB aggregate tool, use proper MDB aggregation pipeline syntax.
When using MongoDB find tool, use proper MDB query syntax with filter objects.
"""

# ─── Build Agent ─────────────────────────────────────────────────────────────
def create_sentinel_agent() -> Agent:
    """
    Create and return the fully configured SENTINEL agent.
    Called once at startup. MongoDB MCP session is managed by ADK.
    """
    mongodb_uri = os.environ.get("MONGODB_URI")
    if not mongodb_uri:
        raise ValueError("MONGODB_URI environment variable is required")

    log.info("sentinel_init", mongodb_uri_set=bool(mongodb_uri))

    # MongoDB MCP toolset — read-only for safety
    mongo_tools = McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command="npx",
                args=["-y", "mongodb-mcp-server", "--readOnly"],
                env={
                    "MDB_MCP_CONNECTION_STRING": mongodb_uri,
                    "MDB_MCP_READ_ONLY": "true",
                    "MDB_MCP_LOG_PATH": "/tmp/mdb-mcp-logs",
                },
            ),
            timeout=45,
        )
    )

    # Custom intelligence tools
    custom_tools = [
        FunctionTool(func=identify_surveillance_capabilities),
        FunctionTool(func=get_vendor_profile),
        FunctionTool(func=check_ban_loophole),
        FunctionTool(func=get_investigation_summary),
    ]

    agent = Agent(
        model="gemini-2.5-pro",
        name="sentinel",
        description=(
            "SENTINEL — Surveillance Contract Intelligence Agent. "
            "Investigates US government facial recognition procurement "
            "using a database of 85 documented contracts across 48 states."
        ),
        instruction=SENTINEL_PROMPT,
        tools=[mongo_tools] + custom_tools,
    )

    log.info("sentinel_ready", model="gemini-2.5-pro", tools_count=5)
    return agent


# ─── Module-level agent instance (loaded once by ADK server) ─────────────────
root_agent = create_sentinel_agent()
