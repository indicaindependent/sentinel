"""
SENTINEL — Surveillance Contract Intelligence Agent
Google Cloud Rapid Agent Hackathon 2026 | GitLab Track
Stack: FastAPI + Google ADK 1.32 + Gemini 2.5 Pro + MongoDB MCP
Live: sentinel.osintnet.uk
"""

import os, json, asyncio, uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import motor.motor_asyncio
from contextlib import asynccontextmanager

# ── Google ADK / Gemini config ────────────────────────────────────────────────
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "FALSE")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
if GEMINI_API_KEY:
    os.environ["GOOGLE_API_KEY"] = GEMINI_API_KEY

MONGO_URI = os.environ.get("MONGO_URI", "")

# ── Arize Platform Tracing (arize-otel official SDK) ─────────────────────────
ARIZE_SPACE_ID  = os.environ.get("ARIZE_SPACE_ID", "")
ARIZE_API_KEY   = os.environ.get("ARIZE_API_KEY", "")
ARIZE_PROJECT   = os.environ.get("ARIZE_PROJECT_NAME", "sentinel-surveillance")

tracer_provider = None  # default
if ARIZE_SPACE_ID and ARIZE_API_KEY:
    try:
        from arize.otel import register as arize_register, Transport as arize_transport
        from openinference.instrumentation.google_genai import GoogleGenAIInstrumentor

        tracer_provider = arize_register(
            space_id=ARIZE_SPACE_ID,
            api_key=ARIZE_API_KEY,
            project_name=ARIZE_PROJECT,
            transport=arize_transport.HTTP,
        )
        GoogleGenAIInstrumentor().instrument(tracer_provider=tracer_provider)
        print(f"✓ Arize tracing active — model: {ARIZE_PROJECT} | space: {ARIZE_SPACE_ID}")
    except Exception as _arize_err:
        print(f"⚠ Arize tracing init failed: {_arize_err}")
else:
    print("⚠ ARIZE_SPACE_ID/API_KEY not set — tracing disabled")


# ── Dynatrace Platform Tracing (Track 5 — Hackathon Partner Bucket) ──────────
try:
    from dynatrace_otel import attach_dynatrace_exporter, sentinel_metrics, smoke_test
    if 'tracer_provider' in dir() and tracer_provider is not None:
        attach_dynatrace_exporter(tracer_provider)
    _dt_smoke = smoke_test()
    print(f"✓ Dynatrace smoke test: {_dt_smoke}")
except Exception as _dt_err:
    print(f"⚠ Dynatrace init failed: {_dt_err}")
    import traceback; traceback.print_exc()




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
app.mount("/static", StaticFiles(directory="/home/ptsdpete/sentinel/static"), name="static")
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
    s = str(d).strip()
    if s in ("—", "-", "null", "None", ""): return "—"
    try:
        if isinstance(d, datetime): return d.strftime("%Y-%m-%d")
        # Try to parse ISO date strings
        from datetime import datetime as dt
        parsed = dt.fromisoformat(s.replace("Z",""))
        return parsed.strftime("%b %d, %Y")
    except:
        return s[:10] if len(s) >= 10 else s

def normalize(c):
    loc = c.get("location") or {}
    # Build place string safely — filter out None/empty/literal "None"
    city  = c.get("city") or ""
    state = c.get("state") or c.get("state_resolved") or ""
    city  = "" if str(city).strip().lower() in ("none", "null", "") else str(city).strip()
    state = "" if str(state).strip().lower() in ("none", "null", "") else str(state).strip()
    place_parts = [p for p in [city, state] if p]
    place = ", ".join(place_parts) if place_parts else ""
    # Fix award_date — stored as "—" string in some docs
    raw_date = c.get("award_date") or c.get("contract_date") or ""
    if str(raw_date).strip() in ("—", "-", "null", "None", ""):
        raw_date = None
    return {
        "id":           str(c.get("_id", "")),
        "vendor":       c.get("vendor_name") or "Unknown",
        "agency":       c.get("agency_name") or "",
        "value":        float(c.get("contract_value", 0) or 0),
        "award_date":   fmt_date(raw_date),
        "naics":        c.get("naics_code") or "",
        "place":        place,
        "description":  c.get("description") or "",
        "capabilities": c.get("capabilities") or [],
        "source":       c.get("source") or "",
        "coords":       loc.get("coordinates") if loc else None,
        "state_resolved": state or c.get("state_resolved") or "",
    }

# ── Pages ─────────────────────────────────────────────────────────────────────

@app.get("/sw.js")
async def service_worker():
    from fastapi.responses import FileResponse
    return FileResponse("/home/ptsdpete/sentinel/static/sw.js", media_type="application/javascript")
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


# ── Map: contract aggregation by state ───────────────────────────────────────
@app.get("/api/contracts/by-state")
async def get_contracts_by_state(
    min_value: Optional[float] = None,
    vendor:    Optional[str]   = None,
):
    """Aggregate all 66,576 contracts by state for the map view.
    Returns one record per state with total value, contract count,
    top-vendor info, and the state centroid coordinates."""
    match = {"state_resolved": {"$nin": [None, ""]}}
    if min_value: match["contract_value"] = {"$gte": min_value}
    if vendor:    match["vendor_name"] = {"$regex": vendor, "$options": "i"}

    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": "$state_resolved",
            "contract_count": {"$sum": 1},
            "total_value": {"$sum": "$contract_value"},
            "max_value": {"$max": "$contract_value"},
            "top_vendor": {"$first": "$vendor_name"},
            "top_agency": {"$first": "$agency_name"},
            "any_coords": {"$first": "$location"},
        }},
        {"$sort": {"total_value": -1}},
    ]
    docs = await db.contracts.aggregate(pipeline).to_list(length=None)

    # Fallback centroid table (state abbr → [lon, lat])
    CENTROIDS = {
        'AL':[-86.79,32.81],'AK':[-152.40,61.37],'AZ':[-111.66,33.73],'AR':[-92.44,34.97],
        'CA':[-119.68,36.12],'CO':[-105.31,39.06],'CT':[-72.76,41.60],'DE':[-75.51,38.99],
        'DC':[-77.03,38.90],'FL':[-81.69,27.77],'GA':[-83.64,33.04],'HI':[-157.50,20.13],
        'ID':[-114.48,44.24],'IL':[-88.99,40.35],'IN':[-86.26,39.85],'IA':[-93.21,42.01],
        'KS':[-96.73,38.53],'KY':[-84.67,37.65],'LA':[-91.87,31.17],'ME':[-69.38,44.69],
        'MD':[-76.80,39.06],'MA':[-71.53,42.23],'MI':[-84.54,43.33],'MN':[-93.90,45.69],
        'MS':[-89.68,32.74],'MO':[-92.29,38.46],'MT':[-110.45,46.92],'NE':[-98.27,41.13],
        'NV':[-117.05,38.31],'NH':[-71.56,43.45],'NJ':[-74.52,40.30],'NM':[-106.25,34.84],
        'NY':[-74.95,42.17],'NC':[-79.81,35.63],'ND':[-99.78,47.53],'OH':[-82.76,40.39],
        'OK':[-96.93,35.57],'OR':[-122.07,44.57],'PA':[-77.21,40.59],'RI':[-71.51,41.68],
        'SC':[-80.95,33.86],'SD':[-99.44,44.30],'TN':[-86.69,35.75],'TX':[-97.56,31.05],
        'UT':[-111.86,40.15],'VT':[-72.71,44.05],'VA':[-78.17,37.77],'WA':[-121.49,47.40],
        'WV':[-80.95,38.49],'WI':[-89.62,44.27],'WY':[-107.30,42.99],'PR':[-66.45,18.22],
        'VI':[-64.78,18.34],'GU':[144.79,13.44],'AS':[-170.13,-14.27],'MP':[145.71,15.18],
    }
    states = []
    for d in docs:
        state = d['_id']
        if not state: continue
        # Prefer coords from data, fall back to centroid table
        co = d.get('any_coords')
        lon, lat = None, None
        if isinstance(co, dict) and isinstance(co.get('coordinates'), list) and len(co['coordinates']) == 2:
            lon, lat = co['coordinates']
        elif state in CENTROIDS:
            lon, lat = CENTROIDS[state]
        if lon is None: continue
        states.append({
            'state': state,
            'contract_count': d['contract_count'],
            'total_value': float(d['total_value'] or 0),
            'max_value':   float(d['max_value']   or 0),
            'top_vendor':  d.get('top_vendor', ''),
            'top_agency':  d.get('top_agency', ''),
            'coords': [lon, lat],
        })
    return {'states': states, 'total_states': len(states)}


# ── Map: paginated geo-marker stream (for zoom-in detail view) ───────────────
@app.get("/api/contracts/markers")
async def get_contract_markers(
    state:     Optional[str]   = None,
    vendor:    Optional[str]   = None,
    min_value: Optional[float] = None,
    skip:      int = 0,
    limit:     int = Query(default=2000, le=5000),
):
    """Return individual contract markers — used at high zoom levels.
    Each contract gets jittered coords so points don't stack on identical state centroids."""
    filt = {"location": {"$ne": None}}
    if state:     filt["state_resolved"] = state.upper()
    if vendor:    filt["vendor_name"] = {"$regex": vendor, "$options": "i"}
    if min_value: filt["contract_value"] = {"$gte": min_value}

    cursor = db.contracts.find(
        filt,
        projection={
            '_id': 0, 'vendor_name': 1, 'agency_name': 1, 'contract_value': 1,
            'award_date': 1, 'description': 1, 'location': 1, 'state_resolved': 1,
            'capabilities': 1,
        }
    ).sort('contract_value', -1).skip(skip).limit(limit)

    docs = await cursor.to_list(length=limit)
    total = await db.contracts.count_documents(filt)

    # Jitter identical coords so same-state points don't pancake
    import random
    random.seed(42)  # deterministic
    markers = []
    for d in docs:
        loc = d.get('location') or {}
        co = loc.get('coordinates') if isinstance(loc, dict) else loc
        if not co or not isinstance(co, list) or len(co) != 2: continue
        lon, lat = co[0], co[1]
        # ±0.6° jitter (~40mi) — keeps points in-state but visually distinct
        jlon = lon + (random.random() - 0.5) * 1.2
        jlat = lat + (random.random() - 0.5) * 1.2
        markers.append({
            'vendor':   d.get('vendor_name', ''),
            'agency':   d.get('agency_name', ''),
            'value':    float(d.get('contract_value') or 0),
            'date':     d.get('award_date', ''),
            'desc':     (d.get('description') or '')[:200],
            'state':    d.get('state_resolved', ''),
            'caps':     d.get('capabilities', []),
            'coords':   [jlon, jlat],
        })
    return {'markers': markers, 'total': total, 'returned': len(markers)}


# ── AI Query — ADK + Gemini 2.5 Pro + MongoDB MCP ────────────────────────────
class QueryRequest(BaseModel):
    question:   str
    session_id: Optional[str] = None


@app.get("/api/contracts/top-vendors")
async def get_top_vendors(limit: int = 25):
    """Return top vendors by total contract value — for UI filter dropdowns."""
    pipeline = [
        {"$match": {"vendor_name": {"$nin": [None, ""]}}},
        {"$group": {
            "_id": "$vendor_name",
            "total_value": {"$sum": "$contract_value"},
            "contract_count": {"$sum": 1},
        }},
        {"$sort": {"total_value": -1}},
        {"$limit": limit},
    ]
    docs = await db.contracts.aggregate(pipeline).to_list(length=None)
    return {
        "vendors": [
            {"name": d["_id"], "total_value": d["total_value"], "contract_count": d["contract_count"]}
            for d in docs
        ]
    }


@app.post("/api/query")
async def query_agent(req: QueryRequest):
    if not GEMINI_API_KEY:
        return {"answer": "GEMINI_API_KEY not configured.", "engine": "none"}

    session_id = req.session_id or str(uuid.uuid4())

    # ── Track 5: wrap the whole agent call in a Dynatrace-visible span ────
    try:
        from opentelemetry import trace as _otel_trace
        _tracer = _otel_trace.get_tracer("sentinel.api.query")
    except Exception:
        _tracer = None

    def _span(name):
        if _tracer is None:
            from contextlib import nullcontext
            return nullcontext()
        return _tracer.start_as_current_span(name)

    # Try full ADK + MongoDB MCP path first
    with _span("sentinel.api.query") as root_span:
        try:
            if root_span is not None and hasattr(root_span, "set_attribute"):
                root_span.set_attribute("sentinel.session_id", session_id)
                root_span.set_attribute("sentinel.question_length", len(req.question or ""))
            runner = await get_adk_runner()
            if runner is not None:
                from google.genai import types as gtypes

                # ── FIX: get_session() returns None when missing, doesn't raise.
                #         Also pass session_id explicitly to create_session.
                existing = await runner.session_service.get_session(
                    app_name="sentinel", user_id="user", session_id=session_id
                )
                if existing is None:
                    await runner.session_service.create_session(
                        app_name="sentinel",
                        user_id="user",
                        session_id=session_id,
                    )
                    if root_span is not None and hasattr(root_span, "set_attribute"):
                        root_span.set_attribute("sentinel.session.created", True)
                else:
                    if root_span is not None and hasattr(root_span, "set_attribute"):
                        root_span.set_attribute("sentinel.session.reused", True)

                user_msg = gtypes.Content(
                    role="user",
                    parts=[gtypes.Part(text=req.question)]
                )

                answer_parts = []
                with _span("sentinel.adk.run_async") as adk_span:
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
                    if adk_span is not None and hasattr(adk_span, "set_attribute"):
                        adk_span.set_attribute("sentinel.answer_parts", len(answer_parts))

                if answer_parts:
                    # ── Track 5: emit business metric ─────────────────────
                    try:
                        from dynatrace_otel import sentinel_metrics
                        sentinel_metrics.contracts_queried(
                            count=1, query_type="adk_mcp_path"
                        )
                    except Exception:
                        pass
                    if root_span is not None and hasattr(root_span, "set_attribute"):
                        root_span.set_attribute("sentinel.engine", "adk_mcp")
                        root_span.set_attribute("sentinel.outcome", "success")
                    return {
                        "answer":     "\n".join(answer_parts),
                        "session_id": session_id,
                        "engine":     "gemini-2.5-pro + ADK + MongoDB MCP",
                    }
        except Exception as e:
            print(f"ADK path error: {e}")
            if root_span is not None and hasattr(root_span, "set_attribute"):
                root_span.set_attribute("sentinel.adk.error", str(e)[:200])
                root_span.set_attribute("sentinel.outcome", "adk_fallback")

        # Fallback: direct Gemini 2.5 Pro with DB context
        result = await gemini_direct(req.question, session_id)
        try:
            from dynatrace_otel import sentinel_metrics
            sentinel_metrics.contracts_queried(
                count=1, query_type="gemini_direct_fallback"
            )
        except Exception:
            pass
        return result


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
        "track": "GitLab Track — Google Cloud Rapid Agent Hackathon 2026",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
