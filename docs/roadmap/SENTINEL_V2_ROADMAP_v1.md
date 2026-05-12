# SENTINEL v2 — COMPREHENSIVE ROADMAP
## "What's Next" — Four-Item Build Plan

**Date:** May 12, 2026
**Author:** Bumboclaat (for Pete / VPDLNY / Indica Independent Media)
**Current state:** 249 federal contracts / $3.83B tracked, Gemini 2.5 Pro + Google ADK, FastAPI on OptiPlex via CF Tunnel
**Constraint:** Do not migrate Sentinel off OptiPlex until after hackathon judging (~June 12)

---

## EXECUTIVE SUMMARY

The four "What's Next" items range from **trivially shippable (alerts)** to **legitimately heavy (state/local data)**. Order of impact-per-hour:

1. **Alert system** — ship this week — high journalist value, full CF edge, ~6h work
2. **Public API + docs** — ship this week — turns Sentinel into research infrastructure, ~8h
3. **CourtListener integration** — ship next week — adds court-records dimension, ~6h
4. **State/local expansion to 1,000+ contracts** — 2-3 days — biggest dataset jump, slowest payoff

All four items respect the **Pete Architecture Doctrine**: alert system and public API live on CF edge, court records and state/local ingestion run as cron jobs that update MongoDB Atlas directly. Sentinel-core stays on OptiPlex through hackathon.

---

## ITEM 1 — ALERT SYSTEM (Ship First)

### What it does
Users subscribe to specific vendors or agencies. When a new contract matching their watchlist is awarded, they get an email or Telegram alert within 24 hours.

### Why first
- Single highest journalist/activist value-add of all four items
- Pure CF edge build (Worker + D1 + Cron + Email/Telegram fanout)
- Zero impact on hackathon submission — runs entirely in parallel
- Sets up the database schema we'll reuse for the public API

### Architecture

```
[CF Cron Trigger — every 6h]
   ↓
[sentinel-alert-watcher worker]
   ↓ poll USAspending API (last_modified_date filter)
   ↓
[D1: tracked_vendors + subscriptions tables]
   ↓ match new awards against subscriptions
   ↓
[fanout: Resend (email) + Telegram Bot API]
   ↓
[MongoDB Atlas update — record alert sent]
```

### Components to build

**1.1 — D1 schema (`sentinel-alerts` database)**
```sql
CREATE TABLE subscribers (
  id TEXT PRIMARY KEY,
  email TEXT,
  telegram_chat_id TEXT,
  created_at INTEGER,
  confirmed INTEGER DEFAULT 0,
  confirm_token TEXT,
  unsubscribe_token TEXT
);

CREATE TABLE subscriptions (
  id TEXT PRIMARY KEY,
  subscriber_id TEXT,
  watch_type TEXT,  -- 'vendor' | 'agency' | 'keyword' | 'naics'
  watch_value TEXT, -- 'Palantir', 'FBI', 'facial recognition', etc.
  min_value_usd INTEGER DEFAULT 0,
  created_at INTEGER,
  active INTEGER DEFAULT 1
);

CREATE TABLE alerts_sent (
  id TEXT PRIMARY KEY,
  subscription_id TEXT,
  contract_award_id TEXT,
  sent_at INTEGER,
  channel TEXT  -- 'email' | 'telegram'
);

CREATE TABLE last_poll (
  source TEXT PRIMARY KEY,  -- 'usaspending'
  last_action_date TEXT,
  last_run_at INTEGER
);
```

**1.2 — Worker `sentinel-alert-watcher`** (~250 LOC)
- Cron trigger: `0 */6 * * *` (every 6 hours)
- Polls USAspending `/api/v2/search/spending_by_award/` with filter:
  ```json
  {
    "filters": {
      "time_period": [{"start_date": "<last_poll>", "end_date": "<now>"}],
      "naics_codes": [<surveillance/IT naics>],
      "award_type_codes": ["A","B","C","D"]
    },
    "fields": ["Award ID","Recipient Name","Award Amount","Awarding Agency","Description","Action Date"]
  }
  ```
- For each new award, run match against `subscriptions` table
- Push matches to a `pending_alerts` queue (CF Queues or D1 table)
- Daily digest at 9 AM ET if any pending alerts

**1.3 — Worker `sentinel-alert-fanout`** (~150 LOC)
- Cron trigger: `0 13 * * *` (9 AM ET daily)
- Reads `pending_alerts`, groups by subscriber, sends digest
- Email via Resend API (already in your stack — check secrets)
- Telegram via Bot API (you already have @ScrambleMeBot infra)
- Records to `alerts_sent`, clears queue

**1.4 — Worker `sentinel-alert-signup`** (~200 LOC)
- Public endpoint: `https://alerts.sentinel.osintnet.uk`
- Form: email or telegram chat_id, choose vendors/agencies/keywords to watch
- Sends double-opt-in confirm email/telegram message
- Manage subscriptions page (token-based, no password needed)
- Embedded on sentinel.osintnet.uk via iframe or subdomain

### Hard considerations

- **USAspending API rate limit:** Unauthenticated, undocumented but observed ~60 req/min. Worker should chunk requests and respect 1s between calls.
- **Vendor name fuzziness:** "PALANTIR USG INC" vs "PALANTIR TECHNOLOGIES INC." vs "Palantir Inc" — need normalization. Use a regex pre-clean + Levenshtein distance < 0.15 for match. Workers AI's BGE embedding model can do semantic match if Levenshtein is too noisy.
- **Email deliverability:** Use Resend with verified domain `sentinel.osintnet.uk`. Set up SPF/DKIM/DMARC.
- **Double opt-in is mandatory** to avoid spam complaints destroying domain reputation.
- **Free CF tier on Workers Paid plan ($5/mo we already pay):** 10M req/mo included, plenty.

### Deliverables
- 3 CF Workers deployed
- D1 `sentinel-alerts` database created and seeded with surveillance NAICS codes
- Signup page live at `alerts.sentinel.osintnet.uk`
- First test subscription cycle end-to-end verified
- 10-12 pre-seeded "tracked vendor" watchlists journalists can subscribe to with one click (Palantir, Clearview, Cellebrite, ShotSpotter, Axon, NSO/Cellebrite, Anduril, etc.)

### Time estimate
**6-8 hours of focused work.** Could ship today if you give the green light.

---

## ITEM 2 — PUBLIC API FOR JOURNALISTS (Ship Second)

### What it does
Stable, documented, rate-limited public API endpoint that journalists, researchers, civil liberties orgs, and other tools can use to query Sentinel's surveillance contract database.

### Why second
- Massively multiplies Sentinel's impact — other people build on top of you
- Foundation for partnerships (EFF, ACLU, ProPublica, The Markup, etc.)
- FastAPI already auto-generates OpenAPI docs — 80% of the work is exposing what already exists
- Sets up the "Sentinel is infrastructure" narrative for funding applications

### Architecture

```
[journalist's tool] → [api.sentinel.osintnet.uk]
                          ↓
                      [CF Worker]
                          ↓ (rate limit check + API key validation)
                          ↓
                      [proxy to OptiPlex FastAPI via tunnel]
                          ↓
                      [return JSON]
```

CF Worker handles auth + rate limit + caching. OptiPlex FastAPI handles the actual queries (where MongoDB Atlas data lives). After hackathon, the FastAPI tier migrates to a CF Worker + D1 cache.

### Components to build

**2.1 — Domain + DNS**
- New subdomain: `api.sentinel.osintnet.uk`
- Cloudflare DNS proxy enabled
- Custom worker route → `sentinel-api-gateway` worker

**2.2 — Worker `sentinel-api-gateway`** (~300 LOC)
- API key authentication (header: `X-API-Key: sk_live_<32chars>`)
- D1 table `api_keys` with: id, key_hash, owner_email, tier, created, last_used, requests_today, rate_limit_per_hour
- 3 tiers:
  - **Anonymous** (no key): 60 req/hour, IP-throttled
  - **Free** (free signup): 1,000 req/hour, 50K req/month
  - **Journalist** (manual approval): 10,000 req/hour, 1M req/month, includes bulk export
- Rate limit via CF Workers Rate Limit API (currently unmetered/free in beta)
- Response caching: KV cache popular queries 5 min

**2.3 — Endpoint coverage** (mirror FastAPI, add bulk/search)
```
GET  /v1/contracts                    — paginated list with filters
GET  /v1/contracts/{award_id}         — single contract
GET  /v1/contracts/search?q=          — full-text search
GET  /v1/vendors                      — vendors with totals
GET  /v1/vendors/{name}               — vendor detail + all contracts
GET  /v1/agencies                     — awarding agencies with totals
GET  /v1/agencies/{name}              — agency detail
GET  /v1/stats                        — high-level stats (already exists)
GET  /v1/timeline?vendor=             — time-series of contracts
GET  /v1/export.csv?filter=           — bulk CSV (journalist tier only)
POST /v1/alerts/subscribe             — proxies to alert signup
```

**2.4 — Docs site** `api.sentinel.osintnet.uk/docs`
- FastAPI already generates OpenAPI at `/docs` — reskin it
- Add: getting started, code examples (curl, Python, JS), rate limits, attribution requirements
- License: CC-BY 4.0 for the data + MIT for the example code
- Required attribution string for users: *"Data via Sentinel — sentinel.osintnet.uk — Indica Independent Media"*

**2.5 — Free signup flow**
- Page: `api.sentinel.osintnet.uk/signup`
- Email confirmation → auto-issue free-tier key
- Dashboard at `api.sentinel.osintnet.uk/dashboard` showing usage + rotation
- Journalist tier requires email to `partnerships@sentinel.osintnet.uk` with bio + use case (manual approval, lightweight)

### Hard considerations

- **CORS:** Must enable for cross-origin browser use — `Access-Control-Allow-Origin: *` on all GET endpoints
- **Abuse prevention:** Anonymous tier strictly IP-bound; aggressive bot detection via CF's existing edge security
- **Attribution enforcement:** No technical enforcement, but documentation + email outreach when violations spotted
- **Caching invalidation:** New contracts every 6h (from alert system), so 5-min KV cache is safe
- **API stability commitment:** Document `/v1` will not change in backward-incompatible ways for 12 months — earn trust

### Deliverables
- `api.sentinel.osintnet.uk` live with all 9 endpoints
- Docs page with curl/Python/JS examples for top 5 endpoints
- 5+ pre-seeded API keys for friendly orgs (EFF, ACLU, Markup) we can email when ready
- Public dashboard at `api.sentinel.osintnet.uk/stats` showing API health + most-queried vendors
- Devpost submission updated to mention the public API (huge differentiator)

### Time estimate
**8-10 hours.** Most painful part is reskinning OpenAPI docs.

---

## ITEM 3 — COURTLISTENER INTEGRATION (Ship Third)

### What it does
For every tracked vendor, automatically pull federal court cases mentioning them as a party, and surface those cases as "Legal Challenges" on each vendor's Sentinel profile.

### Why third
- Adds the legal-accountability dimension to surveillance contracts
- CourtListener has a real, free, well-documented API (5,000 req/hr free tier)
- Stories like "Clearview AI signed $X contract while losing 3 lawsuits about that exact product" write themselves
- Makes Sentinel uniquely useful — no other surveillance tracker links to court records

### Architecture

```
[CF Cron — daily 4 AM ET]
   ↓
[sentinel-court-watcher worker]
   ↓ for each tracked vendor:
   ↓   query CourtListener /search/?q="Palantir"&type=r (RECAP)
   ↓   query CourtListener /search/?q="Palantir"&type=o (opinions)
   ↓
[MongoDB Atlas: court_cases collection]
   ↓
[Sentinel UI: vendor profile shows linked cases]
```

### Components to build

**3.1 — CourtListener API integration**
- Free API key from courtlistener.com/help/api (instant)
- Endpoints used:
  - `/api/rest/v4/search/?type=r` — RECAP docket search (PACER-derived)
  - `/api/rest/v4/search/?type=o` — case opinions
  - `/api/rest/v4/dockets/{id}/` — docket details
- Rate limit: 5,000 req/hr unauthenticated, higher with API key — well within budget for ~50 tracked vendors

**3.2 — Worker `sentinel-court-watcher`** (~250 LOC)
- Cron `0 8 * * *` (4 AM ET)
- For each vendor in `tracked_vendors`, search CourtListener
- For each new case found:
  - Pull docket metadata (court, filing date, case name, party list, nature of suit)
  - Determine if vendor is plaintiff/defendant/third-party
  - Score relevance (vendor in party name = high, vendor in opinion text only = low)
  - Insert into MongoDB `court_cases` collection
- Notification: high-relevance new cases trigger alert subscribers (re-use Item 1 fanout)

**3.3 — MongoDB Atlas schema**
```javascript
{
  _id: ObjectId,
  vendor_name: "PALANTIR TECHNOLOGIES INC.",
  case_name: "Doe v. Palantir Technologies, Inc.",
  court: "N.D. Cal.",
  filed_date: ISODate,
  case_number: "3:23-cv-04127",
  nature_of_suit: "Civil Rights: Other",
  parties: { plaintiffs: [...], defendants: [...] },
  vendor_role: "defendant",
  relevance_score: 0.92,
  courtlistener_url: "https://www.courtlistener.com/docket/...",
  pacer_url: "https://...",
  recap_documents: [...],
  ingested_at: ISODate,
  status: "active"
}
```

**3.4 — Sentinel UI: vendor profile court tab**
- On `sentinel.osintnet.uk/vendor/<name>`, add new "Legal Challenges" tab
- Lists cases sorted by filing date, links to CourtListener docket
- Counter: "X active lawsuits naming this vendor"
- Filterable by case status, court, nature of suit
- This is a minor `index.html` edit + new FastAPI endpoint `/api/v1/vendors/{name}/cases`

### Hard considerations

- **Entity matching is fuzzy.** "Palantir USG Inc" in a contract != "Palantir Technologies, Inc." in a lawsuit caption. Need same normalization layer as alert system (shared util).
- **CourtListener's search is full-text.** A search for "Palantir" returns cases that mention Palantir but aren't *about* Palantir. Relevance scoring + party-list check filters this.
- **PACER content is paywalled.** CourtListener has RECAP — documents donated by RECAP browser extension users — but coverage is incomplete. Linking out to PACER (where users with PACER accounts can pay) is the workaround for non-RECAP docs.
- **Volume:** ~30-50 tracked vendors × ~daily polling = manageable. If we add 1,000+ vendors from state/local expansion, throttle to weekly polling.

### Deliverables
- CourtListener API key acquired and stored in CF secrets
- Worker `sentinel-court-watcher` deployed and on cron
- MongoDB `court_cases` collection populated with initial backfill (one-time search for all current vendors)
- New "Legal Challenges" tab on vendor profile pages
- FastAPI endpoint `/api/v1/vendors/{name}/cases` exposed publicly

### Time estimate
**6-8 hours,** including initial backfill that may take 2-3h of API polling alone.

---

## ITEM 4 — STATE/LOCAL EXPANSION TO 1,000+ CONTRACTS (Ship Last)

### What it does
Adds state and local government surveillance contracts to Sentinel, taking the dataset from 249 federal-only to 1,000+ across all jurisdictions.

### Why last (and why I'm honest about the difficulty)
- This is **the heaviest lift of all four items.** No unified API. Every state and city is a separate scrape.
- High payoff: state/local is where most surveillance abuse actually happens (LPRs, body cams, predictive policing, fusion center contracts)
- After Items 1-3 ship, this is what differentiates Sentinel from the dozens of federal-only trackers
- **Realistic strategy:** Don't try to cover all 50 states. Cover 5-7 high-impact jurisdictions deeply.

### Phase 4A — State portals with usable APIs/exports

These are the realistic free targets:

| Source | Coverage | Access method | Est. contracts |
|---|---|---|---|
| **NYC OpenData** | NYC agencies | Socrata API (`data.cityofnewyork.us`) — free, no key needed | 200-400 |
| **California DGS SCPRS** | CA state | CSV export (catalog.data.gov) — refresh quarterly | 300-500 |
| **NY State OpenData** | NY state + LDCs | Socrata API (`data.ny.gov`) — free | 150-300 |
| **Texas CMBL/CPA** | TX state | Web scrape (no public API) | 100-200 |
| **Chicago Data Portal** | Chicago | Socrata API — free | 50-100 |
| **LA Controller** | LA city | CSV exports | 50-100 |
| **MA COMMBUYS** | MA state | API + CSV | 50-100 |

Target: **1,500-2,000 total contracts** across federal + 7 jurisdictions. Hits the 1,000+ goal comfortably.

### Components to build

**4.1 — Surveillance vendor canonical list** (`tracked_vendors_v2.json`)
- Master list of ~60 known surveillance vendors with all known aliases/subsidiaries
- Shared across all ingest workers
- Maintained manually but with utility to add via API

**4.2 — Workers/scripts per source**

Each is a small script that runs as a cron job, normalizes data into the Sentinel schema, and inserts to MongoDB:

- `sentinel-ingest-nyc.js` — Socrata API call, filter by vendor list, weekly
- `sentinel-ingest-ca-dgs.py` — Download CSV, parse, dedupe, monthly
- `sentinel-ingest-ny-state.js` — Socrata API call, weekly
- `sentinel-ingest-tx.py` — Playwright scrape (heaviest), monthly
- `sentinel-ingest-chicago.js` — Socrata API, weekly
- `sentinel-ingest-la.py` — CSV download, monthly
- `sentinel-ingest-ma.js` — API call, weekly

CF Workers can do the JS-API ones. Python scrapers run on OptiPlex via systemd timers.

**4.3 — Unified contract schema additions**

Current schema is federal-shaped. Add:
```javascript
{
  // ... existing fields
  jurisdiction_level: "federal" | "state" | "local",
  jurisdiction_state: "CA" | "NY" | ...,
  jurisdiction_locality: "New York City" | null,
  source_system: "USAspending" | "NYC_OpenData" | "CA_DGS" | ...,
  source_url: "...",
  ingested_at: ISODate
}
```

**4.4 — UI filters**
- Add jurisdiction filter to Sentinel front page
- "Federal / State / Local" toggle
- State picker dropdown
- Stats page breaks down by jurisdiction

**4.5 — Vendor normalization improvement**
- Build a real entity resolution layer using BGE embeddings (already in our Workers AI stack)
- Migrate from Levenshtein-only matching to semantic + lexical hybrid
- Manually review and confirm top 100 vendor mappings

### Hard considerations

- **Schema drift is severe.** NYC's "vendor_name" is CA's "supplier_name" is TX's "Company Name". Need a per-source mapper.
- **Date formats vary.** ISO 8601, MM/DD/YYYY, fiscal-year shorthand. Normalize to UTC ISO 8601 at ingest.
- **Currency formatting varies.** "$1,234,567.89", "1234567.89", "1.23M". Parse to integer cents at ingest.
- **TX has no API.** Playwright scrape with random delays. Highest fragility risk.
- **Surveillance classification is judgment-heavy.** Is a "body camera storage contract" a surveillance contract? (Yes.) Is a "police laptop purchase" surveillance? (Probably not.) Need a clear classification rubric documented and applied at ingest, with human review queue for ambiguous cases.
- **Watch for license restrictions.** NYC OpenData is fully open. CA DGS data is "for public use" but commercial use unclear. Read each source's TOS before scraping.

### Deliverables
- 7 ingest scripts/workers deployed and on cron
- Master tracked vendor list expanded to ~60 entities with aliases
- Sentinel dataset reaches 1,500-2,000 contracts within 30 days of ingest run
- UI updated with jurisdiction filters
- Documentation page listing data sources + refresh cadence + known gaps

### Time estimate
**2-3 days of focused work,** spread across a week to allow ingest jobs to run and reveal data-quality issues. First 50% of contracts comes fast (Socrata APIs); last 30% (Texas, weird state portals) takes the longest.

---

## CROSS-CUTTING CONCERNS

### Hackathon timing
- **Sentinel hackathon judging is ~June 12, 2026** (one month out)
- **Items 1, 2, 3 should ship before judging.** They strengthen the submission.
- **Item 4 ships after judging** unless we have a clean window. Risk of data-quality regressions hurting demo.
- Update Devpost submission text after each item to reflect new capabilities

### MongoDB Atlas capacity
- Current: 249 contracts. Atlas free tier = 512 MB.
- After 1,500 contracts + court cases + alert metadata: estimated ~50 MB usage. Comfortably under free tier.
- If we blow past free tier: upgrade is $9/mo (M2 shared) — well within budget.

### Sentinel-core stays on OptiPlex
- Per Pete's doctrine: do not migrate Sentinel off OptiPlex until after hackathon judging
- All new workers run on CF edge as **satellites** to the OptiPlex core
- Post-hackathon (June 13+): migrate FastAPI → CF Worker, swap MongoDB Atlas → D1 + Vectorize. Migration plan already drafted at `/app/SENTINEL_EDGE_MIGRATION_PLAN_v1.md`.

### Funding/legitimacy benefits
- Public API + journalist tier opens door to grants (Knight Foundation, OTF, Shuttleworth — applications already drafted for some)
- Each item strengthens the "Sentinel is critical surveillance accountability infrastructure" narrative
- CourtListener integration unlocks partnership conversation with Free Law Project itself

---

## RECOMMENDED EXECUTION ORDER

**Week of May 12-18, 2026:**
1. Item 1 (Alerts) — 6-8h — ship by Wed May 14
2. Item 2 (Public API) — 8-10h — ship by Fri May 16
3. Item 3 (CourtListener) — 6-8h — ship by Sun May 18

**Week of May 19-25:**
4. Devpost final update with all three new features — May 19
5. Polish, bug fixes, marketing push to partners — May 20-25

**Week of May 26 - June 11:** (hackathon judging period)
- Sentinel locked, no changes
- Begin Item 4 ingest scripts in development but do not deploy to production

**Post-judging (June 13+):**
6. Item 4 (State/Local expansion) — 2-3 days
7. Edge migration of Sentinel core per pre-existing plan

---

## DECISION POINTS — PETE'S CALL

Before I start building, I need answers on:

1. **Green light to start Item 1 today?** Or do you want to pace these across the week?
2. **Resend API key for email alerts** — do you have one already, or should I set up a Resend account on the `sentinel.osintnet.uk` domain?
3. **CourtListener API key** — do you want me to register this under `indicaindependent@gmail.com` or create a fresh account `sentinel@osintnet.uk`?
4. **Subdomain confirmations:**
   - `alerts.sentinel.osintnet.uk` — for Item 1 signup page — OK?
   - `api.sentinel.osintnet.uk` — for Item 2 public API — OK?
5. **Partner outreach** — do you want to ping EFF/ACLU/The Markup/ProPublica with API access *before* or *after* hackathon judging? (My recommendation: after — let the hackathon be the launch moment.)

---

**End of plan. Total scope: ~32-40 hours of work across 4 items. All-in budget impact: ~$0 (everything on existing CF Workers Paid plan + free API tiers).**

*Ready to build whenever Pete gives the word. B)*
