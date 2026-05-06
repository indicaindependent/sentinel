#!/usr/bin/env python3
"""
SENTINEL — Database utilities
Contract ingestion, validation, and query helpers
"""

from pymongo import MongoClient
from typing import Optional
import os


def get_db():
    """Get MongoDB connection."""
    client = MongoClient(os.environ["MONGODB_URI"])
    return client["sentinel"]["contracts"]


def search_contracts(query: str, limit: int = 10) -> list[dict]:
    """Full-text search across contract records."""
    db = get_db()
    results = db.find(
        {"$text": {"$search": query}},
        {"score": {"$meta": "textScore"}}
    ).sort([("score", {"$meta": "textScore"})]).limit(limit)
    return list(results)


def get_by_agency(agency: str) -> list[dict]:
    """Get all contracts for a specific agency."""
    db = get_db()
    return list(db.find({"agency": {"$regex": agency, "$options": "i"}}))


def get_by_vendor(vendor: str) -> list[dict]:
    """Get all contracts awarded to a specific vendor."""
    db = get_db()
    return list(db.find({"vendor": {"$regex": vendor, "$options": "i"}}))


def get_stats() -> dict:
    """Get summary statistics."""
    db = get_db()
    pipeline = [
        {"$group": {
            "_id": None,
            "total_contracts": {"$sum": 1},
            "total_value": {"$sum": "$value_usd"},
            "agencies": {"$addToSet": "$agency"},
            "vendors": {"$addToSet": "$vendor"},
        }}
    ]
    result = list(db.aggregate(pipeline))
    return result[0] if result else {}
