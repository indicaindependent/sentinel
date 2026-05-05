"""
SENTINEL Custom Intelligence Tools
These supplement the MongoDB MCP tools with higher-level analysis capabilities.
All tools are designed to be called by the Gemini ADK agent.
"""

import json
import os
import structlog
from typing import Optional

log = structlog.get_logger()

# ─── Capability Keyword Map ───────────────────────────────────────────────────
CAPABILITY_KEYWORDS = {
    "real_time_matching": [
        "real-time", "realtime", "live", "streaming", "continuous monitoring",
        "real time face", "live feed", "video surveillance"
    ],
    "database_search": [
        "database", "repository", "image repository", "photo database",
        "mugshot", "watchlist", "gallery search", "identity resolution"
    ],
    "mobile_deployment": [
        "mobile", "handheld", "portable", "field deployment", "body-worn",
        "body camera", "BWC", "in-field"
    ],
    "mass_surveillance": [
        "mass", "bulk", "population", "crowd", "large-scale",
        "high volume", "widespread", "pervasive"
    ],
    "border_immigration": [
        "border", "immigration", "customs", "CBP", "ICE", "HSI",
        "deportation", "removal", "entry", "exit", "travel"
    ],
    "law_enforcement": [
        "law enforcement", "police", "criminal", "suspect", "arrest",
        "investigation", "crime", "fugitive", "wanted"
    ]
}

CONCERN_WEIGHTS = {
    "real_time_matching": 3,
    "mass_surveillance": 3,
    "border_immigration": 2,
    "database_search": 1,
    "mobile_deployment": 2,
    "law_enforcement": 1,
}

VENDOR_PROFILES = {
    "Clearview AI": {
        "description": "Private company. Built product by scraping ~30 billion photos from internet without consent.",
        "legal_issues": "Found illegal by courts in Australia, France, Italy, Greece, UK. Multiple US lawsuits pending.",
        "concern_level": 5,
        "known_clients": ["ICE/HSI", "CBP", "DOD", "NYPD", "Chicago PD"],
        "data_source": "Scraped internet photos (non-consensual)",
    },
    "FBI FACE Services": {
        "description": "Federal Bureau of Investigation facial recognition unit. Accesses 29 state DMV databases.",
        "legal_issues": "No federal law specifically requires warrant for facial recognition searches. No opt-out for citizens.",
        "concern_level": 4,
        "known_clients": ["29 state DMVs", "Federal law enforcement agencies"],
        "data_source": "State driver's license photos (government-held)",
    },
    "Idemia": {
        "description": "French multinational (formerly MorphoTrust). Provides identity verification to governments worldwide.",
        "legal_issues": "Limited public litigation in US. European operations subject to GDPR scrutiny.",
        "concern_level": 3,
        "known_clients": ["12 state DMVs", "TSA", "various state agencies"],
        "data_source": "Government-issued ID photos, biometric enrollment",
    },
    "LACRIS": {
        "description": "Los Angeles County Regional Identification System. County-operated facial recognition network serving Southern California law enforcement.",
        "legal_issues": "Subject to California AB 1215 (2019 moratorium on police body cam FR). Municipal bans in some jurisdictions.",
        "concern_level": 4,
        "known_clients": ["LAPD", "LA County Sheriff", "surrounding agencies"],
        "data_source": "Booking photos, DMV photos, law enforcement databases",
    },
    "NEC": {
        "description": "Japanese multinational technology corporation. One of the world's largest facial recognition vendors.",
        "legal_issues": "Limited US-specific litigation. NIST ranked NEC systems highly but demographic disparities documented.",
        "concern_level": 3,
        "known_clients": ["Various US agencies", "International law enforcement"],
        "data_source": "Government enrollment databases",
    },
}

BAN_JURISDICTIONS = {
    "CA": ["San Francisco", "Oakland", "Berkeley"],
    "MA": ["Boston", "Somerville", "Cambridge", "Springfield", "Northampton"],
    "ME": ["Portland"],
    "MN": ["Minneapolis"],
    "OR": ["Portland"],
    "GA": ["Brookhaven"],
    "LA": ["New Orleans (reversed)"],
}

FBI_LOOPHOLE_STATES = {"CA", "ME", "MN", "OR"}  # Have bans BUT FBI still has DMV access


def identify_surveillance_capabilities(
    agency_name: str,
    vendor_name: str,
    notes: str = "",
    source: str = ""
) -> dict:
    """
    Analyse contract metadata to identify likely surveillance capabilities.
    Maps agency type + vendor profile to probable deployment capabilities.

    Returns:
        capabilities (list): Plain-language capability descriptions
        concern_level (int): 1-5 scale (5 = most concerning)
        concern_reasons (list): Specific reasons for concern rating
        vendor_context (str): Key facts about the vendor
    """
    log.info("tool_called", tool="identify_surveillance_capabilities",
             agency=agency_name, vendor=vendor_name)
    try:
        text = f"{agency_name} {vendor_name} {notes} {source}".lower()

        capabilities = []
        concern_score = 0
        concern_reasons = []

        # Check capability keywords
        for cap, keywords in CAPABILITY_KEYWORDS.items():
            if any(kw.lower() in text for kw in keywords):
                capabilities.append(cap.replace("_", " ").title())
                concern_score += CONCERN_WEIGHTS.get(cap, 1)

        # Vendor-specific capabilities
        vendor_info = VENDOR_PROFILES.get(vendor_name, {})
        if vendor_info:
            concern_score = max(concern_score, vendor_info.get("concern_level", 1))
            if vendor_info.get("legal_issues"):
                concern_reasons.append(f"Vendor legal issues: {vendor_info['legal_issues']}")
            if not capabilities and vendor_info.get("description"):
                capabilities.append("Identity resolution via vendor database")

        # Agency-type inferences
        if any(x in agency_name.upper() for x in ["ICE", "CBP", "HSI", "HOMELAND"]):
            capabilities.append("Immigration enforcement face matching")
            concern_reasons.append("Immigration enforcement context — affects undocumented populations")
            concern_score = max(concern_score, 4)

        if "DMV" in agency_name.upper() or "Motor Vehicles" in agency_name:
            capabilities.append("Driver's licence database access (affects all licence holders)")
            if vendor_name == "FBI FACE Services":
                concern_reasons.append(
                    "FBI federal access to DMV photos — no consent mechanism, no opt-out, "
                    "no notification to individuals when their image is searched"
                )

        # Ban jurisdiction + still active
        from_state = ""
        for state, cities in BAN_JURISDICTIONS.items():
            if state in agency_name or any(city in agency_name for city in cities):
                from_state = state
                concern_reasons.append(
                    f"Jurisdiction has enacted a facial recognition ban — "
                    f"yet this deployment appears active or was active"
                )

        concern_level = min(5, max(1, concern_score))
        if not capabilities:
            capabilities = ["Facial recognition identity matching (capability details undisclosed)"]

        result = {
            "capabilities": capabilities,
            "concern_level": concern_level,
            "concern_reasons": concern_reasons,
            "vendor_context": vendor_info.get("description", "No profile on file."),
            "vendor_legal_issues": vendor_info.get("legal_issues", "No known issues documented."),
            "data_source": vendor_info.get("data_source", "Unknown"),
        }
        log.info("tool_success", tool="identify_surveillance_capabilities",
                 concern_level=concern_level, cap_count=len(capabilities))
        return result

    except Exception as e:
        log.error("tool_error", tool="identify_surveillance_capabilities", error=str(e))
        return {"error": str(e), "capabilities": [], "concern_level": 0, "concern_reasons": []}


def get_vendor_profile(vendor_name: str) -> dict:
    """
    Return a comprehensive profile of a surveillance vendor.
    Includes concern level, known legal issues, client list, data sources.

    Args:
        vendor_name: Name of the vendor (e.g. "Clearview AI", "FBI FACE Services")

    Returns:
        dict with profile data or closest match
    """
    log.info("tool_called", tool="get_vendor_profile", vendor=vendor_name)
    try:
        # Exact match
        if vendor_name in VENDOR_PROFILES:
            profile = VENDOR_PROFILES[vendor_name].copy()
            profile["vendor_name"] = vendor_name
            profile["found"] = True
            log.info("tool_success", tool="get_vendor_profile", found=True)
            return profile

        # Fuzzy match
        vl = vendor_name.lower()
        for k, v in VENDOR_PROFILES.items():
            if k.lower() in vl or vl in k.lower():
                profile = v.copy()
                profile["vendor_name"] = k
                profile["found"] = True
                profile["note"] = f"Matched '{vendor_name}' to profile '{k}'"
                log.info("tool_success", tool="get_vendor_profile", found=True, fuzzy=True)
                return profile

        log.info("tool_success", tool="get_vendor_profile", found=False)
        return {
            "vendor_name": vendor_name,
            "found": False,
            "description": "No profile on file for this vendor.",
            "concern_level": 2,
            "note": "Vendor not in SENTINEL knowledge base. Check open sources for more information.",
        }
    except Exception as e:
        log.error("tool_error", tool="get_vendor_profile", error=str(e))
        return {"error": str(e), "vendor_name": vendor_name, "found": False}


def check_ban_loophole(state_code: str, vendor_name: str) -> dict:
    """
    Check if a state has a facial recognition ban AND still has federal access.
    This surfaces the 'ban evasion loophole' finding.

    Args:
        state_code: Two-letter state code (e.g. "CA", "ME")
        vendor_name: Vendor name to check

    Returns:
        dict with loophole status and explanation
    """
    log.info("tool_called", tool="check_ban_loophole", state=state_code, vendor=vendor_name)
    try:
        has_ban = state_code.upper() in BAN_JURISDICTIONS
        has_fbi_loophole = state_code.upper() in FBI_LOOPHOLE_STATES
        banned_cities = BAN_JURISDICTIONS.get(state_code.upper(), [])

        result = {
            "state": state_code.upper(),
            "has_ban": has_ban,
            "banned_cities": banned_cities,
            "has_fbi_federal_loophole": has_fbi_loophole,
            "loophole_explanation": None,
            "concern": "low",
        }

        if has_ban and has_fbi_loophole:
            result["loophole_explanation"] = (
                f"{state_code.upper()} has enacted local bans on facial recognition in "
                f"{', '.join(banned_cities)}. However, the FBI FACE Services unit maintains "
                f"a data-sharing agreement with the {state_code.upper()} DMV, giving federal "
                f"law enforcement access to driver's licence photos. Local bans cannot legally "
                f"bind federal agencies — creating a loophole that effectively nullifies the "
                f"democratic intent of the ban."
            )
            result["concern"] = "critical"
        elif has_ban:
            result["loophole_explanation"] = (
                f"{state_code.upper()} has enacted bans in {', '.join(banned_cities)}, "
                f"but does not appear in the confirmed FBI FACE federal access network. "
                f"Local bans may still be bypassed by state-level agencies or contractors "
                f"operating outside municipal jurisdiction."
            )
            result["concern"] = "moderate"

        log.info("tool_success", tool="check_ban_loophole", concern=result["concern"])
        return result
    except Exception as e:
        log.error("tool_error", tool="check_ban_loophole", error=str(e))
        return {"error": str(e), "state": state_code}


def get_investigation_summary() -> dict:
    """
    Return top-level statistics about the entire SENTINEL database.
    Used for the dashboard overview and agent orientation.

    Returns:
        dict with counts, totals, key findings
    """
    log.info("tool_called", tool="get_investigation_summary")
    return {
        "total_contracts": 85,
        "states_documented": 48,
        "unique_agencies": 84,
        "unique_vendors": 9,
        "total_documented_value_usd": 9390620,
        "contracts_with_known_value": 5,
        "contracts_value_hidden_pct": 94,
        "verified_contracts": 38,
        "red_risk_contracts": 43,
        "fbi_dmv_network_states": 29,
        "fbi_estimated_people_affected": 200000000,
        "clearview_federal_contracts": 4,
        "clearview_largest_contract_usd": 9200000,
        "ban_states": list(BAN_JURISDICTIONS.keys()),
        "loophole_states": list(FBI_LOOPHOLE_STATES),
        "top_vendors": [
            {"name": "FBI FACE Services", "contracts": 29, "states": 29},
            {"name": "Clearview AI",      "contracts": 17, "states": 11},
            {"name": "Idemia",            "contracts": 13, "states": 12},
            {"name": "LACRIS",            "contracts":  7, "states":  1},
            {"name": "NEC",               "contracts":  3, "states":  3},
        ],
        "key_findings": [
            "FBI FACE Services accesses 29 state DMV databases — ~200M Americans affected",
            "Clearview AI holds $9.2M+ in federal contracts despite being found illegal in 5 countries",
            "4 ban states (CA, ME, MN, OR) still have active FBI federal access — loophole documented",
            "94% of contract values are hidden from public — financial opacity is systemic",
            "3 vendors control 71% of all documented contracts — effective oligopoly",
        ],
        "source": "FaceHeatMap database (faceheatmap.app) — Indica Independent Media",
        "last_updated": "2026-05-02",
    }
