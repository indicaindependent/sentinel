#!/usr/bin/env python3
"""
Sentinel USAspending Ingest v3 — production-grade, runs on OptiPlex.

Lessons baked in:
- Null-safe PSC/NAICS dict handling
- 8 retries with linear backoff up to 90s
- Per-page flush (resume-safe if process dies)
- Vendor-skip via existing seen IDs
- Word-boundary vendor name matching to avoid false positives (FAXON ≠ AXON)
- Heartbeat log every 5 pages
"""
import json, os, sys, time, re, urllib.request
from datetime import datetime

URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
PAGE_SIZE = 100
START_DATE = "2008-10-01"
END_DATE = datetime.utcnow().strftime("%Y-%m-%d")
UA = "Sentinel-Ingest/3.0 (sentinel.osintnet.uk)"
SLEEP = 0.6
MAX_PAGES_PER_VENDOR = 100  # USAspending caps at ~10k records via paging

BASE = "/home/ptsdpete/sentinel_ingest"

with open(f"{BASE}/filters.json") as f:
    F = json.load(f)
PSC_SET = set(F['psc_codes'].keys())
NAICS_SET = set(F['naics_codes'].keys())
KEYWORDS = [k.lower() for k in F['keywords']]

# Word-boundary patterns — no more FAXON/MAXON false positives
SURVEILLANCE_VENDOR_PATTERNS = [
    (r'\bPALANTIR\b', 'palantir'),
    (r'\bCLEARVIEW\b.*\bAI\b', 'clearview_ai'),
    (r'\bAXON\s+(ENTERPRISE|INC|LLC|CORP|INDUSTRIES|TECHNOLOGIES|HOLDINGS)\b', 'axon_enterprise'),
    (r'\bCELLEBRITE\b', 'cellebrite'),
    (r'\bANDURIL\b', 'anduril'),
    (r'\bPEN[\s\-]?LINK\b', 'pen_link'),
    (r'\bMAGNET\s+FORENSICS\b', 'magnet_forensics'),
    (r'\bVERINT\b', 'verint'),
    (r'\bGRAYSHIFT\b', 'grayshift'),
    (r'\bNSO\s+GROUP\b', 'nso_group'),
    (r'\bPARAGON\s+(SOLUTIONS|SOFTWARE)\b', 'paragon_solutions'),
    (r'\bNICE\s+(SYSTEMS|LTD|INC|AMERICAS)\b', 'nice_systems'),
    (r'\bBABEL\s+STREET\b', 'babel_street'),
    (r'\bVIGILANT\s+SOLUTIONS\b', 'vigilant_solutions'),
    (r'\bDATAMINR\b', 'dataminr'),
    (r'\bCOGNYTE\b', 'cognyte'),
    (r'\b(SHOTSPOTTER|SHOT\s+SPOTTER)\b', 'shotspotter'),
    (r'\bCOBWEBS\b', 'cobwebs'),
    (r'\bSOUND\s*THINKING\b', 'soundthinking'),
    (r'\bVOYAGER\s+LABS\b', 'voyager_labs'),
    (r'\bFLOCK\s+SAFETY\b', 'flock_safety'),
    (r'\bFUSUS\b', 'fusus'),
    (r'\bFORENSIC\s+LOGIC\b', 'forensic_logic'),
]
COMPILED_VENDOR_RE = [(re.compile(p, re.IGNORECASE), tag) for p, tag in SURVEILLANCE_VENDOR_PATTERNS]


def classify_vendor(vendor_name):
    """Return tag if vendor is a known surveillance-product vendor (word-boundary match)."""
    if not vendor_name:
        return None
    for pat, tag in COMPILED_VENDOR_RE:
        if pat.search(vendor_name):
            return tag
    return None


def is_surveillance(award, vendor_name):
    """Multi-signal classifier."""
    tag = classify_vendor(vendor_name)
    if tag:
        return True, f"surv-vendor:{tag}", [f"vendor:{tag}", "surveillance"], 1.0

    # Big-tent vendor: must match PSC/NAICS/keyword
    p = award.get('PSC') or {}
    n = award.get('NAICS') or {}
    psc = ((p.get('code') if isinstance(p, dict) else str(p)) or '').strip()
    naics = ((n.get('code') if isinstance(n, dict) else str(n)) or '').strip()
    desc = (award.get('Description') or '').lower()

    caps, reasons, score = [], [], 0.0
    if psc in PSC_SET:
        caps.append(f"psc:{psc}"); reasons.append(f"PSC{psc}"); score += 0.4
    if naics in NAICS_SET:
        caps.append(f"naics:{naics}"); reasons.append(f"NAICS{naics}"); score += 0.3
    matched = [k for k in KEYWORDS if k in desc]
    if matched:
        caps.extend([f"kw:{k}" for k in matched[:5]])
        reasons.append(f"kw:{','.join(matched[:3])}")
        score += min(0.6, 0.2 * len(matched))
    if not reasons:
        return False, "no-signal", [], 0.0
    return True, "|".join(reasons), caps, min(score, 1.0)


def fetch_page(vname, page):
    body = {"filters": {
        "recipient_search_text": [vname],
        "award_type_codes": ["A", "B", "C", "D"],
        "time_period": [{"start_date": START_DATE, "end_date": END_DATE}]},
        "fields": ["Award ID", "Recipient Name", "Award Amount", "Awarding Agency",
                   "Awarding Sub Agency", "Description", "Start Date", "End Date",
                   "Action Date", "Place of Performance State Code",
                   "Place of Performance Country Code", "NAICS", "PSC",
                   "recipient_id", "generated_internal_id"],
        "page": page, "limit": PAGE_SIZE,
        "sort": "Award Amount", "order": "desc"}
    req = urllib.request.Request(URL,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "User-Agent": UA},
        method="POST")
    for attempt in range(8):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.loads(r.read())
        except Exception as e:
            wait = min(90, 5 * (attempt + 1))
            print(f"     [retry {attempt+1}/8] {type(e).__name__}: {str(e)[:80]} — wait {wait}s", flush=True)
            time.sleep(wait)
    return None


def harvest(vname, total, out_handle, seen_ids):
    pages = min((total + PAGE_SIZE - 1) // PAGE_SIZE, MAX_PAGES_PER_VENDOR)
    kept = filt = dup = 0
    print(f"\n=== {vname} ({total:,} contracts → fetch {pages} pages) ===", flush=True)
    for p in range(1, pages + 1):
        d = fetch_page(vname, p)
        if not d:
            print(f"   page {p}: ABORT after retries", flush=True)
            break
        results = d.get('results', [])
        if not results:
            print(f"   page {p}: empty, done with vendor", flush=True)
            break
        page_kept = 0
        for award in results:
            aid = award.get('Award ID') or award.get('generated_internal_id')
            if not aid:
                continue
            if aid in seen_ids:
                dup += 1
                continue
            seen_ids.add(aid)
            keep, reason, caps, score = is_surveillance(award, award.get('Recipient Name') or vname)
            if not keep:
                filt += 1
                continue
            naics_o = award.get('NAICS') or {}
            psc_o = award.get('PSC') or {}
            rec = {
                'award_id': aid,
                'vendor': award.get('Recipient Name') or vname,
                'agency': award.get('Awarding Agency') or '',
                'sub_agency': award.get('Awarding Sub Agency') or '',
                'value': float(award.get('Award Amount') or 0),
                'award_date': award.get('Action Date') or award.get('Start Date') or '',
                'start_date': award.get('Start Date') or '',
                'end_date': award.get('End Date') or '',
                'description': award.get('Description') or '',
                'naics': naics_o.get('code', '') if isinstance(naics_o, dict) else str(naics_o),
                'naics_desc': naics_o.get('description', '') if isinstance(naics_o, dict) else '',
                'psc': psc_o.get('code', '') if isinstance(psc_o, dict) else str(psc_o),
                'psc_desc': psc_o.get('description', '') if isinstance(psc_o, dict) else '',
                'state': award.get('Place of Performance State Code') or '',
                'country': award.get('Place of Performance Country Code') or '',
                'capabilities': caps,
                'surveillance_score': score,
                'filter_reason': reason,
                'source': 'usaspending',
                'source_id': award.get('generated_internal_id') or aid,
                'ingested_at': datetime.utcnow().isoformat() + 'Z',
            }
            out_handle.write(json.dumps(rec) + '\n')
            kept += 1
            page_kept += 1
        out_handle.flush()
        if p % 5 == 0 or p == pages:
            print(f"   page {p}/{pages}: +{page_kept} (vendor kept={kept} filt={filt} dup={dup})", flush=True)
        time.sleep(SLEEP)
        if p * PAGE_SIZE >= 10000:
            print(f"   [stop] 10k page cap reached", flush=True)
            break
    return kept, filt, dup


def main():
    vendors_file = sys.argv[1] if len(sys.argv) > 1 else f"{BASE}/vendor_counts.json"
    output_file = sys.argv[2] if len(sys.argv) > 2 else f"{BASE}/harvested.jsonl"

    with open(vendors_file) as f:
        vendors = json.load(f)

    # Resume: read existing IDs
    seen_ids = set()
    completed_vendors = set()
    if os.path.exists(output_file):
        with open(output_file) as f:
            for line in f:
                try:
                    r = json.loads(line)
                    seen_ids.add(r['award_id'])
                    # Note vendors we've seen records from
                    tag = classify_vendor(r.get('vendor', ''))
                    if tag:
                        completed_vendors.add(tag)
                except:
                    pass
        print(f"Resuming: {len(seen_ids):,} existing IDs, {len(completed_vendors)} vendor tags seen", flush=True)

    out = open(output_file, 'a')
    summary = {'started': datetime.utcnow().isoformat() + 'Z', 'vendors': {}}

    for v in vendors:
        if v.get('contracts', 0) == 0:
            print(f"SKIP {v['vendor']}: 0 contracts in USAspending", flush=True)
            continue
        kept, filt, dup = harvest(v['vendor'], v['contracts'], out, seen_ids)
        summary['vendors'][v['vendor']] = {'kept': kept, 'filtered': filt, 'duplicates': dup}

    out.close()
    summary['finished'] = datetime.utcnow().isoformat() + 'Z'
    summary['total_kept'] = sum(v['kept'] for v in summary['vendors'].values())
    summary['total_filtered'] = sum(v['filtered'] for v in summary['vendors'].values())
    summary['total_duplicates'] = sum(v['duplicates'] for v in summary['vendors'].values())

    with open(output_file.replace('.jsonl', '.summary.json'), 'w') as f:
        json.dump(summary, f, indent=2)

    print(f"\n=== INGEST COMPLETE ===", flush=True)
    print(f"Kept:       {summary['total_kept']:,}", flush=True)
    print(f"Filtered:   {summary['total_filtered']:,}", flush=True)
    print(f"Duplicates: {summary['total_duplicates']:,}", flush=True)


if __name__ == '__main__':
    main()
