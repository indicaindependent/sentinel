#!/usr/bin/env python3
"""
Sentinel Mongo Push v1 — transforms harvested JSONL into Sentinel.contracts schema.

Schema match (from existing docs):
  _id (auto), award_id, agency_name, vendor_name, description,
  contract_value, contract_date, end_date, detected_at,
  city, state, location {type, coordinates}, confidence_score, confidence_tier,
  source_type, capabilities, imported_at, source, state_resolved

Strategy:
  1. Read JSONL line by line
  2. Transform to Sentinel schema with surveillance_score → confidence_score mapping
  3. Geocode state codes → coordinates via static state-centroid lookup
  4. Bulk upsert by award_id (dedupes against existing 249 + within batch)
  5. Print final count
"""
import os, json, sys, asyncio
from datetime import datetime
from dotenv import load_dotenv
import motor.motor_asyncio

load_dotenv(os.environ.get('SENTINEL_ENV', '.env'))
MONGO_URI = os.environ['MONGO_URI']

# US state centroid coords for geo-mapping (lat, lng → as [lng, lat] GeoJSON)
STATE_CENTROIDS = {
    "AL":[-86.79,32.81],"AK":[-152.40,61.37],"AZ":[-111.66,33.73],"AR":[-92.39,34.97],
    "CA":[-119.68,37.18],"CO":[-105.55,38.99],"CT":[-72.76,41.62],"DE":[-75.51,39.00],
    "FL":[-81.69,28.63],"GA":[-83.43,32.65],"HI":[-157.50,20.79],"ID":[-114.48,44.24],
    "IL":[-89.20,40.04],"IN":[-86.28,39.89],"IA":[-93.21,42.07],"KS":[-98.38,38.49],
    "KY":[-84.86,37.65],"LA":[-91.96,31.07],"ME":[-69.39,45.37],"MD":[-76.80,39.06],
    "MA":[-71.83,42.26],"MI":[-84.71,43.32],"MN":[-94.31,45.69],"MS":[-89.66,32.74],
    "MO":[-92.43,38.36],"MT":[-110.45,47.05],"NE":[-99.79,41.13],"NV":[-117.06,38.50],
    "NH":[-71.58,43.45],"NJ":[-74.51,40.30],"NM":[-106.12,34.41],"NY":[-75.53,42.95],
    "NC":[-79.81,35.63],"ND":[-99.78,47.53],"OH":[-82.79,40.29],"OK":[-97.49,35.59],
    "OR":[-122.07,44.93],"PA":[-77.20,40.59],"RI":[-71.51,41.68],"SC":[-80.95,33.86],
    "SD":[-99.44,44.30],"TN":[-86.69,35.85],"TX":[-97.56,31.05],"UT":[-111.86,40.15],
    "VT":[-72.71,44.05],"VA":[-78.17,37.77],"WA":[-121.49,47.40],"WV":[-80.95,38.49],
    "WI":[-89.62,44.27],"WY":[-107.30,42.99],"DC":[-77.03,38.90],"PR":[-66.59,18.22]
}


def score_to_tier(score):
    """surveillance_score (0-1) → confidence_tier"""
    if score >= 0.85: return "high"
    if score >= 0.55: return "medium"
    return "low"


def normalize_caps(caps):
    """Normalize capability tags from harvest format to Sentinel format."""
    norm = set()
    for c in caps or []:
        c_low = c.lower()
        if 'face' in c_low or 'facial' in c_low: norm.add('facial_recognition')
        if 'biometric' in c_low: norm.add('biometric')
        if 'license plate' in c_low or 'alpr' in c_low or 'lpr' in c_low: norm.add('alpr')
        if 'social media' in c_low: norm.add('social_media_monitoring')
        if 'wiretap' in c_low or 'pen register' in c_low: norm.add('communications_intercept')
        if 'cell' in c_low or 'stingray' in c_low or 'imsi' in c_low: norm.add('cell_site_simulator')
        if 'forensic' in c_low or 'cellebrite' in c_low or 'graykey' in c_low: norm.add('mobile_forensics')
        if 'gunshot' in c_low or 'shotspotter' in c_low: norm.add('acoustic_surveillance')
        if 'fusion' in c_low: norm.add('fusion_center')
        if 'body camera' in c_low or 'bwc' in c_low: norm.add('body_camera')
        if 'drone' in c_low or 'cuas' in c_low: norm.add('counter_drone')
        if 'sigint' in c_low: norm.add('signals_intelligence')
        if 'osint' in c_low: norm.add('open_source_intelligence')
        if 'predictive' in c_low: norm.add('predictive_policing')
        if c.startswith('vendor:'): norm.add(c.split(':')[1])
    if not norm:
        norm.add('surveillance')
    return sorted(norm)


def transform(record):
    """JSONL record → MongoDB doc matching Sentinel schema."""
    state = (record.get('state') or '').upper().strip()
    coords = STATE_CENTROIDS.get(state)
    location = {"type": "Point", "coordinates": coords} if coords else None

    score_pct = int(round((record.get('surveillance_score') or 0) * 100))

    return {
        "award_id":         record['award_id'],
        "vendor_name":      record.get('vendor', ''),
        "agency_name":      record.get('agency', ''),
        "sub_agency":       record.get('sub_agency', ''),
        "description":      record.get('description', ''),
        "contract_value":   record.get('value', 0),
        "contract_date":    record.get('award_date') or record.get('start_date') or '',
        "start_date":       record.get('start_date', ''),
        "end_date":         record.get('end_date', ''),
        "naics_code":       record.get('naics', ''),
        "naics_description":record.get('naics_desc', ''),
        "psc_code":         record.get('psc', ''),
        "psc_description":  record.get('psc_desc', ''),
        "city":             "",
        "state":            state,
        "state_resolved":   state,
        "location":         location,
        "confidence_score": score_pct,
        "confidence_tier":  score_to_tier(record.get('surveillance_score') or 0),
        "source_type":      "procurement_portal",
        "capabilities":     normalize_caps(record.get('capabilities')),
        "filter_reason":    record.get('filter_reason', ''),
        "imported_at":      datetime.utcnow().isoformat(),
        "source":           "usaspending",
        "detected_at":      datetime.utcnow().strftime("%Y-%m-%d"),
    }


async def main():
    input_file = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SENTINEL_HARVEST", "./sentinel_ingest/harvested.jsonl")
    dry_run = '--dry' in sys.argv

    client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
    db = client["sentinel"]

    pre_count = await db.contracts.count_documents({})
    print(f"Pre-push count:      {pre_count:,}")
    print(f"Input file:          {input_file}")
    print(f"Dry-run:             {dry_run}")

    # Make sure award_id is indexed (unique not enforced — old data may have nulls)
    try:
        await db.contracts.create_index([("location", "2dsphere")], background=True, name="location_2dsphere")
    except Exception as e:
        print(f'index warning: {str(e)[:120]}')
    print('✓ Indexes ensured (award_id already unique-sparse)')

    batch = []
    BATCH_SIZE = 500
    total_inserted = total_updated = total_skipped = total_errors = 0
    line_n = 0

    with open(input_file) as f:
        for line in f:
            line_n += 1
            try:
                rec = json.loads(line)
            except:
                total_errors += 1
                continue
            doc = transform(rec)
            batch.append(doc)
            if len(batch) >= BATCH_SIZE:
                ins, upd, skp = await flush(db, batch, dry_run)
                total_inserted += ins; total_updated += upd; total_skipped += skp
                batch = []
                if line_n % 2500 == 0:
                    print(f"   [{line_n:,} lines] inserted={total_inserted:,} updated={total_updated:,} skipped={total_skipped:,}")
        if batch:
            ins, upd, skp = await flush(db, batch, dry_run)
            total_inserted += ins; total_updated += upd; total_skipped += skp

    post_count = await db.contracts.count_documents({})
    print()
    print(f"Lines processed:     {line_n:,}")
    print(f"Inserted (new):      {total_inserted:,}")
    print(f"Updated (existing):  {total_updated:,}")
    print(f"Skipped (dry-run):   {total_skipped:,}")
    print(f"Errors (bad JSON):   {total_errors:,}")
    print(f"Post-push count:     {post_count:,}  (delta: +{post_count - pre_count:,})")
    client.close()


async def flush(db, batch, dry_run):
    if dry_run:
        return 0, 0, len(batch)
    from pymongo import UpdateOne
    ops = [UpdateOne({"award_id": d["award_id"]}, {"$set": d}, upsert=True) for d in batch]
    try:
        res = await db.contracts.bulk_write(ops, ordered=False)
        return (res.upserted_count, res.modified_count, 0)
    except Exception as e:
        print(f"   FLUSH ERR: {e}")
        return (0, 0, 0)


if __name__ == '__main__':
    asyncio.run(main())
