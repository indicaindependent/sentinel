"""
SENTINEL — Surveillance Contract Intelligence Agent
Google Cloud Rapid Agent Hackathon 2026 | MongoDB Track
Stack: FastAPI + Google ADK 1.32 + Gemini 2.5 Pro + MongoDB MCP
Live: sentinel.osintnet.uk
"""

import os, json, asyncio, uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import motor.motor_asyncio
from contextlib import asynccontextmanager

# ── Google ADK / Gemini config ────────────────────────────────────────────────
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "FALSE")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
if GEMINI_API_KEY:
    os.environ["GOOGLE_API_KEY"] = GEMINI_API_KEY

MONGO_URI = os.environ.get("MONGO_URI", "")

# ── DB client ─────────────────────────────────────────────────────────────────
db_client = None
db = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global db_client, db
    db_client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
    db = db_client["sentinel"]
    print("✓ MongoDB connected")
    yield
    db_client.close()

app = FastAPI(title="SENTINEL API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── ADK runner (lazy init) ────────────────────────────────────────────────────
_adk_runner = None
_adk_lock = asyncio.Lock()

async def get_adk_runner():
    global _adk_runner
    if _adk_runner is not None:
        return _adk_runner
    async with _adk_lock:
        if _adk_runner is not None:
            return _adk_runner
        try:
            from google.adk.runners import Runner
            from google.adk.sessions import InMemorySessionService
            from agent import root_agent
            session_svc = InMemorySessionService()
            _adk_runner = Runner(
                agent=root_agent,
                app_name="sentinel",
                session_service=session_svc,
            )
            print("✓ ADK Runner: Gemini 2.5 Pro + MongoDB MCP")
        except Exception as e:
            print(f"✗ ADK init failed: {e}")
            _adk_runner = None
    return _adk_runner

# ── Helpers ───────────────────────────────────────────────────────────────────
def fmt_usd(v):
    if not v: return "$0"
    v = float(v)
    if v >= 1e9: return f"${v/1e9:.2f}B"
    if v >= 1e6: return f"${v/1e6:.1f}M"
    if v >= 1e3: return f"${v/1e3:.0f}K"
    return f"${v:,.0f}"

def fmt_date(d):
    if not d: return "—"
    try:
        if isinstance(d, datetime): return d.strftime("%Y-%m-%d")
        return str(d)[:10]
    except: return str(d)

def normalize(c):
    loc = c.get("location") or {}
    return {
        "id":           str(c.get("_id", "")),
        "vendor":       c.get("vendor_name", "Unknown"),
        "agency":       c.get("agency_name", ""),
        "value":        float(c.get("contract_value", 0) or 0),
        "award_date":   fmt_date(c.get("award_date") or c.get("contract_date")),
        "naics":        c.get("naics_code", ""),
        "place":        f"{c.get('city','')}, {c.get('state','')}".strip(", "),
        "description":  c.get("description", ""),
        "capabilities": c.get("capabilities", []),
        "source":       c.get("source", ""),
        "coords":       loc.get("coordinates") if loc else None,
        "state_resolved": c.get("state_resolved", ""),
    }

# ── Pages ─────────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index():
    p = os.path.join(os.path.dirname(__file__), "index.html")
    with open(p) as f:
        return HTMLResponse(content=f.read())

@app.get("/legal", response_class=HTMLResponse)
@app.get("/legal/{page}", response_class=HTMLResponse)
@app.get("/tos", response_class=HTMLResponse)
@app.get("/privacy", response_class=HTMLResponse)
@app.get("/about", response_class=HTMLResponse)
async def legal_page(page: str = "tos"):
    p = os.path.join(os.path.dirname(__file__), "legal.html")
    with open(p) as f:
        return HTMLResponse(content=f.read())

# ── Data API ──────────────────────────────────────────────────────────────────
@app.get("/api/stats")
async def get_stats():
    total = await db.contracts.count_documents({})
    agg = await db.contracts.aggregate([
        {"$group": {"_id": None, "total": {"$sum": "$contract_value"}}}
    ]).to_list(1)
    total_value = agg[0]["total"] if agg else 0

    top_vendors = await db.contracts.aggregate([
        {"$group": {"_id": "$vendor_name", "total": {"$sum": "$contract_value"}, "count": {"$sum": 1}}},
        {"$sort": {"total": -1}}, {"$limit": 10}
    ]).to_list(10)

    top_agencies = await db.contracts.aggregate([
        {"$group": {"_id": "$agency_name", "total": {"$sum": "$contract_value"}, "count": {"$sum": 1}}},
        {"$sort": {"total": -1}}, {"$limit": 10}
    ]).to_list(10)

    return {
        "total_contracts":  total,
        "total_value":      total_value,
        "total_value_fmt":  fmt_usd(total_value),
        "top_vendors":  [{"name": v["_id"], "total": v["total"], "total_fmt": fmt_usd(v["total"]), "count": v["count"]} for v in top_vendors],
        "top_agencies": [{"name": a["_id"], "total": a["total"], "total_fmt": fmt_usd(a["total"]), "count": a["count"]} for a in top_agencies],
        "ai_engine": "Gemini 2.5 Pro + Google ADK + MongoDB MCP",
    }

@app.get("/api/contracts")
async def get_contracts(
    search:    Optional[str]   = None,
    vendor:    Optional[str]   = None,
    agency:    Optional[str]   = None,
    min_value: Optional[float] = None,
    limit:     int = Query(default=100, le=500),
    skip:      int = 0,
):
    filt = {}
    if search:
        filt["$or"] = [
            {"vendor_name": {"$regex": search, "$options": "i"}},
            {"agency_name": {"$regex": search, "$options": "i"}},
            {"description": {"$regex": search, "$options": "i"}},
        ]
    if vendor:    filt["vendor_name"]    = {"$regex": vendor, "$options": "i"}
    if agency:    filt["agency_name"]    = {"$regex": agency, "$options": "i"}
    if min_value: filt["contract_value"] = {"$gte": min_value}

    cursor = db.contracts.find(filt).sort("contract_value", -1).skip(skip).limit(limit)
    docs   = await cursor.to_list(limit)
    total  = await db.contracts.count_documents(filt)
    return {"contracts": [normalize(c) for c in docs], "total": total}

# ── AI Query — ADK + Gemini 2.5 Pro + MongoDB MCP ────────────────────────────
class QueryRequest(BaseModel):
    question:   str
    session_id: Optional[str] = None

@app.post("/api/query")
async def query_agent(req: QueryRequest):
    if not GEMINI_API_KEY:
        return {"answer": "GEMINI_API_KEY not configured.", "engine": "none"}

    session_id = req.session_id or str(uuid.uuid4())

    # Try full ADK + MongoDB MCP path first
    try:
        runner = await get_adk_runner()
        if runner is not None:
            from google.genai import types as gtypes

            try:
                await runner.session_service.get_session(
                    app_name="sentinel", user_id="user", session_id=session_id
                )
            except Exception:
                await runner.session_service.create_session(
                    app_name="sentinel", user_id="user", session_id=session_id
                )

            user_msg = gtypes.Content(
                role="user",
                parts=[gtypes.Part(text=req.question)]
            )

            answer_parts = []
            async for event in runner.run_async(
                user_id="user",
                session_id=session_id,
                new_message=user_msg,
            ):
                if event.is_final_response():
                    if event.content and event.content.parts:
                        for part in event.content.parts:
                            if hasattr(part, "text") and part.text:
                                answer_parts.append(part.text)

            if answer_parts:
                return {
                    "answer":     "\n".join(answer_parts),
                    "session_id": session_id,
                    "engine":     "gemini-2.5-pro + ADK + MongoDB MCP",
                }
    except Exception as e:
        print(f"ADK path error: {e}")

    # Fallback: direct Gemini 2.5 Pro with DB context
    return await gemini_direct(req.question, session_id)

async def gemini_direct(question: str, session_id: str):
    """Direct Gemini 2.5 Pro call with MongoDB context injected."""
    try:
        from google import genai

        client = genai.Client(api_key=GEMINI_API_KEY)

        # Pull top contracts for context
        contracts = await db.contracts.find({}).sort("contract_value", -1).limit(40).to_list(40)
        agg = await db.contracts.aggregate([
            {"$group": {"_id": None, "total": {"$sum": "$contract_value"}, "count": {"$sum": 1}}}
        ]).to_list(1)
        total_val = agg[0]["total"] if agg else 0
        total_cnt = agg[0]["count"] if agg else 0

        ctx = f"SENTINEL Database: {total_cnt} contracts, {fmt_usd(total_val)} total\n\nTOP CONTRACTS:\n"
        for c in contracts:
            ctx += (f"- {c.get('vendor_name','?')} | {c.get('agency_name','?')} | "
                    f"{fmt_usd(c.get('contract_value',0))} | "
                    f"{fmt_date(c.get('award_date'))} | {c.get('state','')}\n")

        prompt = (
            "You are SENTINEL, an elite OSINT agent analyzing U.S. government surveillance "
            "and AI procurement contracts. Answer using ONLY the data below — no hallucinations. "
            "Cite specific vendors, dollar amounts, and agencies.\n\n"
            f"{ctx}\n\nUSER QUESTION: {question}\n\n"
            "Give a direct, factual answer with specific numbers. "
            "End with one suggested follow-up query."
        )

        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=prompt,
        )
        return {
            "answer":     response.text,
            "session_id": session_id,
            "engine":     "gemini-2.5-pro (direct + MongoDB context)",
        }
    except Exception as e:
        return {"answer": f"Analysis error: {str(e)}", "engine": "error", "session_id": session_id}

@app.get("/api/health")
async def health():
    count = await db.contracts.count_documents({})
    return {
        "status":    "operational",
        "contracts": count,
        "ai_engine": "Gemini 2.5 Pro + Google ADK 1.32",
        "mcp":       "MongoDB MCP Server (mongodb-mcp-server)",
        "track":     "MongoDB — Google Cloud Rapid Agent Hackathon 2026",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
