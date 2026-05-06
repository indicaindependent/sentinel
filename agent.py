#!/usr/bin/env python3
"""
SENTINEL — Surveillance Contract Intelligence Agent
Federal contract OSINT tool powered by Google Gemini + ADK
Author: Indica Independent Media (https://osintnet.uk)
"""

from google.adk.agents import Agent
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, StdioServerParameters
import os

SYSTEM_PROMPT = """You are SENTINEL — a federal surveillance contract intelligence agent.
You have access to a verified database of 249 surveillance contracts totaling $3.83 billion.

When asked about contracts:
- Query the MongoDB database for relevant records
- Cite contract values, agencies, vendors, and dates
- Provide sourced, factual answers
- Flag patterns across multiple contracts

Categories tracked: facial recognition, predictive policing, location tracking,
biometric databases, social media monitoring, license plate readers.
"""

def create_sentinel_agent():
    """Create the SENTINEL agent with MCP tools."""
    mongodb_toolset = MCPToolset(
        connection_params=StdioServerParameters(
            command="npx",
            args=["-y", "@modelcontextprotocol/server-mongodb", os.environ["MONGODB_URI"]],
        )
    )
    
    agent = Agent(
        model="gemini-2.5-pro-preview-05-06",
        name="sentinel",
        description="Federal surveillance contract intelligence agent",
        instruction=SYSTEM_PROMPT,
        tools=[mongodb_toolset],
    )
    return agent
