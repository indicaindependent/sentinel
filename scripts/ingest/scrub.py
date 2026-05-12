#!/usr/bin/env python3
'''Final scrub — remove obvious non-surveillance false positives by vendor blacklist.'''
import json, re, sys

# Vendors that contain AXON/SAXON/etc but are clearly not surveillance
NEVER_INCLUDE_PATTERNS = [
    r'\bFAXON\b', r'\bMAXON\b', r'\bJAXON\b', r'\bCLAXON\b', r'\bPLAXON\b',
    r'\bCHEMAXON\b', r'\bNORAXON\b', r'\bAAXON\b',
    r'\bSAXON\b', r'\bSAXONICA\b', r'\bSAXONS\b',
    r'\bTAXON', r'\bAXONICS\b', r'\bINTERAXON\b',
    r'\bDAXON\b', r'\bMAXONS\b',
    # Other obvious non-surveillance vendors that sneak in via NAICS
    r'\bFAXON FIREARMS\b',
    r'\bMAXON FURNITURE\b',
    r'^\s*FAXON\b',
]
NEVER = [re.compile(p, re.IGNORECASE) for p in NEVER_INCLUDE_PATTERNS]

# Also reject if description mentions clear non-surveillance keywords AND no vendor tag
DESC_BLACKLIST = ['furniture', 'office supplies', 'cleaning service', 'plant taxonom',
                  'glass repair', 'restoration of', 'building maintenance']

inp = sys.argv[1]
outp = sys.argv[2]
kept = rejected = 0
with open(inp) as fin, open(outp, 'w') as fout:
    for line in fin:
        r = json.loads(line)
        v = (r.get('vendor') or '').upper()
        if any(p.search(v) for p in NEVER):
            rejected += 1
            continue
        desc = (r.get('description') or '').lower()
        reason = r.get('filter_reason','')
        # If filter was only PSC/NAICS (no vendor tag) AND description matches blacklist, drop
        if not reason.startswith('surv-vendor:') and any(b in desc for b in DESC_BLACKLIST):
            rejected += 1
            continue
        fout.write(line)
        kept += 1
print(f'Kept:     {kept:,}')
print(f'Rejected: {rejected:,}')
