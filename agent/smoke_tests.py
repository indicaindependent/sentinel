"""
SENTINEL Smoke Tests
Run these before every deploy to verify core functionality.
Usage: python -m agent.smoke_tests
"""

import sys
import os
import traceback
from .tools import (
    identify_surveillance_capabilities,
    get_vendor_profile,
    check_ban_loophole,
    get_investigation_summary,
)

PASS = "✅"
FAIL = "❌"
results = []


def test(name: str, fn, *args, validator=None, **kwargs):
    try:
        result = fn(*args, **kwargs)
        if validator and not validator(result):
            results.append((FAIL, name, f"Validator failed. Got: {str(result)[:120]}"))
            return
        results.append((PASS, name, ""))
    except Exception as e:
        results.append((FAIL, name, f"{type(e).__name__}: {e}"))


# ─── Tool tests ───────────────────────────────────────────────────────────────
test("get_investigation_summary returns totals",
     get_investigation_summary,
     validator=lambda r: r.get("total_contracts") == 85)

test("get_investigation_summary has key_findings",
     get_investigation_summary,
     validator=lambda r: len(r.get("key_findings", [])) >= 3)

test("get_vendor_profile: Clearview AI (exact match)",
     get_vendor_profile, "Clearview AI",
     validator=lambda r: r.get("found") and r.get("concern_level") == 5)

test("get_vendor_profile: FBI FACE Services",
     get_vendor_profile, "FBI FACE Services",
     validator=lambda r: r.get("found") and r.get("concern_level") >= 4)

test("get_vendor_profile: unknown vendor graceful",
     get_vendor_profile, "UnknownVendorXYZ",
     validator=lambda r: r.get("found") == False and "error" not in r)

test("identify_capabilities: Clearview + ICE",
     identify_surveillance_capabilities,
     "ICE / DHS", "Clearview AI",
     validator=lambda r: r.get("concern_level", 0) >= 4 and len(r.get("capabilities", [])) > 0)

test("identify_capabilities: FBI + DMV",
     identify_surveillance_capabilities,
     "AK Division of Motor Vehicles", "FBI FACE Services",
     validator=lambda r: r.get("concern_level", 0) >= 3)

test("check_ban_loophole: CA (has ban + FBI loophole)",
     check_ban_loophole, "CA", "FBI FACE Services",
     validator=lambda r: r.get("has_ban") and r.get("has_fbi_federal_loophole")
                         and r.get("concern") == "critical")

test("check_ban_loophole: TX (no ban)",
     check_ban_loophole, "TX", "Clearview AI",
     validator=lambda r: not r.get("has_ban") and r.get("concern") == "low")

test("check_ban_loophole: MA (ban, no FBI loophole)",
     check_ban_loophole, "MA", "Clearview AI",
     validator=lambda r: r.get("has_ban") and not r.get("has_fbi_federal_loophole"))

test("identify_capabilities returns no exception on empty input",
     identify_surveillance_capabilities, "", "",
     validator=lambda r: "error" not in r)

# ─── Results ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n═══════════════════════════════════════")
    print("  SENTINEL SMOKE TEST SUITE")
    print("═══════════════════════════════════════")
    passed = sum(1 for r in results if r[0] == PASS)
    failed = sum(1 for r in results if r[0] == FAIL)
    for status, name, msg in results:
        suffix = f"  → {msg}" if msg else ""
        print(f"  {status} {name}{suffix}")
    print("───────────────────────────────────────")
    print(f"  {passed}/{len(results)} passed", "🎉" if failed == 0 else "⚠️")
    print("═══════════════════════════════════════\n")
    sys.exit(0 if failed == 0 else 1)
