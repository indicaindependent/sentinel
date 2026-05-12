# SENTINEL Ingest Pipeline

Reproducible pipeline that grew the SENTINEL dataset from **249 contracts ($3.83B)** to **66,576 contracts ($377.93B)** in a single 48-minute run.

## Pipeline stages

```
vendor_counts.json  ->  ingest.py  ->  harvested.jsonl
                                          |
                                          v
                                       scrub.py  ->  harvested_clean.jsonl
                                                         |
                                                         v
                                                  push_to_mongo.py  ->  MongoDB Atlas
```

## Files

| File | Purpose |
|---|---|
| `filters.json` | PSC, NAICS, and keyword filter spec (45 PSCs, 32 NAICS, 69 keywords) |
| `vendor_counts.json` | The 39 vendor names + USASpending contract counts to harvest |
| `ingest.py` | USASpending.gov harvester (resume-safe, 8-retry backoff, word-boundary classifier) |
| `scrub.py` | Final blacklist scrub (removes ~0.13% remaining false positives) |
| `push_to_mongo.py` | Transforms JSONL -> Sentinel schema -> bulk upserts to MongoDB |
| `ingest_summary.json` | Per-vendor kept/filtered/duplicate counts from the May 12, 2026 run |

## Reproducing the run

```bash
# 1. Set MONGO_URI in /home/ptsdpete/sentinel/.env
# 2. Activate the sentinel venv (motor, pymongo, dotenv)
source /home/ptsdpete/sentinel/venv/bin/activate

# 3. Harvest from USASpending (~30 min)
python3 ingest.py vendor_counts.json harvested.jsonl

# 4. Final scrub (instant)
python3 scrub.py harvested.jsonl harvested_clean.jsonl

# 5. Dry-run the push to verify transforms
python3 push_to_mongo.py harvested_clean.jsonl --dry

# 6. Push to MongoDB Atlas (~5 min for 66K records)
python3 push_to_mongo.py harvested_clean.jsonl
```

## Confidence-score formula

Every harvested contract gets a numeric confidence score `s in [0, 1]`:

$$
s = \min\!\left(1.0,\ \ \mathbf{1}_{V} \cdot 1.0 \;+\; \mathbf{1}_{P} \cdot 0.4 \;+\; \mathbf{1}_{N} \cdot 0.3 \;+\; \min\!\big(0.6,\ 0.2 \cdot k\big)\right)
$$

where $\mathbf{1}_{V}, \mathbf{1}_{P}, \mathbf{1}_{N}$ are indicator variables for vendor/PSC/NAICS matches, and $k$ is the keyword-hit count in the award description.

Buckets:
- `high`   — $s \ge 0.85$ (vendor-tagged products)
- `medium` — $0.55 \le s < 0.85$ (multi-signal matches)
- `low`    — $s < 0.55$ (single-signal matches, retained for transparency)

## False-positive handling

Naive substring matching `"AXON" in vendor_name` originally matched FAXON, MAXON, CHEMAXON, JAXON, SAXON, etc. Fixed via word-boundary regex:

```python
r'\bAXON\s+(ENTERPRISE|INC|LLC|CORP|INDUSTRIES|TECHNOLOGIES|HOLDINGS)\b'
```

Final false-positive rate after `scrub.py`: **<= 0.13%** (89 of 66,551 ambiguous records).

## Vendor tiers

- **Tier 1 — Surveillance products** (24 vendors): Palantir, Clearview AI, Axon, Cellebrite, Anduril, Pen-Link, Magnet Forensics, Verint, Grayshift, NSO Group, Paragon Solutions, NICE Systems, Babel Street, Vigilant Solutions, Dataminr, Cognyte, ShotSpotter, Cobwebs, SoundThinking, Voyager Labs, Flock Safety, Fusus, Forensic Logic, TSYMMETRY
- **Tier 2 — General contractors with surveillance work** (15 vendors): Motorola Solutions, L3Harris, Peraton, Booz Allen, Leidos, CACI, ManTech, SAIC, GDIT, Thundercat, I3 Federal, V3GATE, Affigent, West Publishing, LexisNexis, Thomson Reuters, RELX, Oracle America

Tier 2 vendors only contribute records where PSC/NAICS/keyword signals confirm surveillance scope.

## Production output

| Metric | Value |
|---|---|
| Harvest runtime | 30 min |
| Push runtime | ~5 min |
| Raw records harvested | 93,734 |
| Records kept after classifier | 66,551 |
| Records filtered as non-surveillance | 27,183 |
| Cross-vendor duplicates | 29,815 |
| Records kept after final scrub | 66,449 |
| Records in MongoDB | 66,576 (includes 127 pre-existing FaceHeatmap records) |
| Total contract value | $377,931,792,446 |

---

*Pipeline run: May 12, 2026 17:22-18:05 UTC by Bumboclaat for PTSDPete / VPDLNY.*
