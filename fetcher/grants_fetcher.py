import time, hashlib
from typing import List, Dict
from google.cloud import firestore
import requests  # future-proof; safe even if unused now

# Normalized result:
# {"id": "...", "title": "...", "agency": "...", "url": "...", "deadline": "...", "score": float}

def _cache_key(keyword: str) -> str:
    return hashlib.sha256(keyword.strip().lower().encode()).hexdigest()

def find_grants(keyword: str) -> List[Dict]:
    """
    Day 7: cached demo fetcher.
    Later we can replace the TODO call with real Grants.gov without touching the API layer.
    """
    db = firestore.Client()
    key = _cache_key(keyword)
    snap = db.collection("grants_cache").document(key).get()
    if snap.exists:
        cached = snap.to_dict()
        if time.time() - cached.get("ts", 0) < 86400:  # 24h TTL
            return cached.get("items", [])

    # ---- Future real call (placeholder) ----
    items: List[Dict] = []
    try:
        # Example for the real integration (commented for now):
        # resp = requests.get("https://api.grants.gov/endpoint", params={"q": keyword}, timeout=10)
        # data = resp.json()
        # items = [
        #   {
        #     "id": d.get("opportunityNumber"),
        #     "title": d.get("title"),
        #     "agency": d.get("agency"),
        #     "url": d.get("url"),
        #     "deadline": d.get("closeDate"),
        #     "score": 0.90
        #   } for d in data.get("opportunities", [])
        # ]
        pass
    except Exception:
        # network or parse problems fall back to demo data
        items = []

    # Fallback demo data (keeps app useful today)
    if not items:
        kw = keyword.strip().title()
        items = [
            {"id": f"{kw[:1]}-001", "title": f"{kw} Opportunity A", "agency": "Sample Agency",
             "url": "https://example.org/a", "deadline": None, "score": 0.92},
            {"id": f"{kw[:1]}-002", "title": f"{kw} Opportunity B", "agency": "Sample Agency",
             "url": "https://example.org/b", "deadline": None, "score": 0.87},
            {"id": f"{kw[:1]}-003", "title": f"{kw} Opportunity C", "agency": "Sample Agency",
             "url": "https://example.org/c", "deadline": None, "score": 0.83},
        ]

    db.collection("grants_cache").document(key).set({"ts": time.time(), "items": items})
    return items
