#!/usr/bin/env python3
"""
GrantforgeUSA - RSS Auto Cache Updater (No login / No UEI / No SAM)
- Reads Grants.gov public RSS feeds (new & modified, by category/agency)
- Builds cache_v1.csv with columns that match our app
- Safe during shutdowns; no scraping, no private APIs

Requires (one-time):
  pip install feedparser pandas python-dateutil
Run:
  python rss_auto_to_csv.py
"""

import feedparser
import pandas as pd
import hashlib
from datetime import datetime
from dateutil import parser as dateparser
import os, json

OUTPUT_CSV = "cache_v1.csv"
LOG_FILE   = "auto_update_log.json"

RSS_FEEDS = [
    "https://www.grants.gov/rss/GG_NewOppsByCategory.xml",
    "https://www.grants.gov/rss/GG_OppModByCategory.xml",
    "https://www.grants.gov/rss/GG_NewOppsByAgency.xml",
    "https://www.grants.gov/rss/GG_OppModByAgency.xml",
]

# Keep this list small & meaningful. Empty list = keep everything.
FILTER_KEYWORDS = ["education","nonprofit","501(c)(3)","small business","church","community","youth","school"]

COLUMNS = ["Grant Title","Agency","Category","Short Summary","URL","Posted Date","Last Seen","Source","_id"]

def norm(t): return " ".join(str(t or "").split())

def make_id(title, link):
    raw = (title or "") + "|" + (link or "")
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

def parse_date(x):
    if not x: return ""
    try:
        return dateparser.parse(x).strftime("%Y-%m-%d")
    except Exception:
        return ""

def fetch():
    items = []
    for url in RSS_FEEDS:
        d = feedparser.parse(url)
        for e in d.entries:
            title = norm(e.get("title"))
            link  = norm(e.get("link"))
            desc  = norm(e.get("summary") or e.get("description"))
            pub   = parse_date(e.get("published") or e.get("pubDate"))
            cat   = norm(e.get("category") or "")
            agency = norm(e.get("tags")[0]["term"]) if e.get("tags") else ""

            blob = (title + " " + desc).lower()
            if FILTER_KEYWORDS and not any(k in blob for k in [k.lower() for k in FILTER_KEYWORDS]):
                continue

            items.append({
                "Grant Title": title,
                "Agency": agency,
                "Category": cat,
                "Short Summary": desc[:320],
                "URL": link,
                "Posted Date": pub,
                "Last Seen": datetime.utcnow().strftime("%Y-%m-%d"),
                "Source": url.rsplit("/",1)[-1],
                "_id": make_id(title, link),
            })
    return pd.DataFrame(items, columns=COLUMNS)

def merge(new_df, path):
    if os.path.exists(path):
        old = pd.read_csv(path)
        if "_id" not in old.columns:
            old["_id"] = old.apply(lambda r: make_id(r.get("Grant Title",""), r.get("URL","")), axis=1)
    else:
        old = pd.DataFrame(columns=COLUMNS)

    merged = pd.concat([old, new_df], ignore_index=True)
    merged.sort_values(["_id","Last Seen"], inplace=True)
    merged = merged.drop_duplicates(subset=["_id"], keep="last")
    return merged[COLUMNS]

def main():
    new_df = fetch()
    if new_df.empty:
        print("No entries matched filters; keeping existing cache if present.")
    merged = merge(new_df, OUTPUT_CSV) if not new_df.empty else (
        pd.read_csv(OUTPUT_CSV) if os.path.exists(OUTPUT_CSV) else pd.DataFrame(columns=COLUMNS)
    )
    merged.to_csv(OUTPUT_CSV, index=False)
    log = {
        "run_at_utc": datetime.utcnow().isoformat(),
        "feeds_checked": RSS_FEEDS,
        "new_records_fetched": 0 if new_df.empty else len(new_df),
        "total_records_after_merge": len(merged),
        "filter_keywords": FILTER_KEYWORDS,
    }
    with open(LOG_FILE, "w") as f:
        json.dump(log, f, indent=2)
    print(f"OK: {OUTPUT_CSV} now has {len(merged)} rows. Log: {LOG_FILE}")

if __name__ == "__main__":
    main()