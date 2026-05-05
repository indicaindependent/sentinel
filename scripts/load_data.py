"""
SENTINEL — MongoDB Atlas Data Loader
Loads all 85 contracts from contracts.json into sentinel_db.contracts
Run once after MongoDB Atlas M0 cluster is created.
Usage: MONGODB_URI=mongodb+srv://... python scripts/load_data.py
"""

import os, json, sys
from pathlib import Path

try:
    from pymongo import MongoClient
except ImportError:
    print("pip install pymongo")
    sys.exit(1)

MONGODB_URI = os.environ.get("MONGODB_URI")
if not MONGODB_URI:
    print("MONGODB_URI required")
    sys.exit(1)

data_path = Path(__file__).parent.parent / "data" / "contracts.json"
with open(data_path) as f:
    contracts = json.load(f)
print(f"Loaded {len(contracts)} contracts")

client = MongoClient(MONGODB_URI)
db  = client["sentinel_db"]
col = db["contracts"]

existing = col.count_documents({})
if existing > 0:
    print(f"Dropping {existing} existing records")
    col.drop()

result = col.insert_many(contracts)
print(f"Inserted {len(result.inserted_ids)} contracts")

col.create_index("state")
col.create_index("vendor_name")
col.create_index("risk_level")
col.create_index("confidence_tier")
col.create_index([("agency_name", "text"), ("vendor_name", "text"), ("notes", "text")])
print("Indexes created")
print(f"Done: {col.count_documents({})} contracts in sentinel_db.contracts")
client.close()
