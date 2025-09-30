from google.cloud import firestore
import hashlib, json, datetime, requests

db = firestore.Client()

CACHE_TTL_HOURS = 24

def _make_cache_key(keyword: str) -> str:
    return hashlib.sha256(keyword.lower().encode("utf-8")).hexdigest()[:12]

def find_grants(keyword: str):
    key = _make_cache_key(keyword)
    doc_ref = db.collection("grants_cache").document(key)
    snap = doc_ref.get()

    # 1. Serve from cache if still valid
    if snap.exists:
        data = snap.to_dict()
        ts = data.get("timestamp")
        if ts and (datetime.datetime.utcnow() - ts.replace(tzinfo=None)) < datetime.timedelta(hours=CACHE_TTL_HOURS):
            return data.get("items", [])

    # 2. Try real external fetch (future-proof placeholder)
    try:
        resp = requests.get(
            "https://example.com/api/grants?q=" + keyword,
            headers={"User-Agent": "GrantForgeUSA/1.0"},
            timeout=8,
        )
        if resp.ok:
            items = resp.json().get("items", [])
        else:
            items = []
    except Exception:
        items = []

    # 3. Fallback demo data if empty
    if not items:
        items = [
            {"id": "E-001", "title": "Education Grant A", "agency": "Sample Agency", "score": 0.92},
            {"id": "E-002", "title": "Education Grant B", "agency": "Sample Agency", "score": 0.85},
            {"id": "E-003", "title": "Education Grant C", "agency": "Sample Agency", "score": 0.80},
        ]

    # 4. Cache results
    doc_ref.set({
        "keyword": keyword,
        "items": items,
        "timestamp": datetime.datetime.utcnow()
    })

    return items
