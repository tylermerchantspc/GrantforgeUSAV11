#!/usr/bin/env python3
"""
GrantforgeUSA - BASIC RSS Updater (No Filters)
If your filtered updater finds 0 rows, run this version.

Usage:
  python rss_auto_to_csv_basic.py

Requires:
  pip install feedparser pandas python-dateutil
"""
import feedparser, pandas as pd, hashlib, json, os
from datetime import datetime
from dateutil import parser as dateparser

OUTPUT_CSV = "cache_v1.csv"
LOG_FILE   = "auto_update_log.json"

RSS_FEEDS = [
    "https://www.grants.gov/rss/GG_NewOppsByCategory.xml",
    "https://www.grants.gov/rss/GG_OppModByCategory.xml",
    "https://www.grants.gov/rss/GG_NewOppsByAgency.xml",
    "https://www.grants.gov/rss/GG_OppModByAgency.xml",
]

COLUMNS = ["Grant Title","Agency","Category","Short Summary","URL","Posted Date","Last Seen","Source","_id"]

def norm(t): return " ".join(str(t or "").split())
def make_id(title, link):
    return hashlib.sha256((title or "" + "|" + link or "").encode("utf-8")).hexdigest()[:16]
def parse_date(x):
    if not x: return ""
    try: return dateparser.parse(x).strftime("%Y-%m-%d")
    except Exception: return ""

def fetch_all():
    rows = []
    totals = {}
    for url in RSS_FEEDS:
        d = feedparser.parse(url)
        totals[url] = len(d.entries)
        for e in d.entries:
            title = norm(e.get("title"))
            link  = norm(e.get("link"))
            desc  = norm(e.get("summary") or e.get("description"))
            pub   = parse_date(e.get("published") or e.get("pubDate"))
            cat   = norm(e.get("category") or "")
            agency = norm(e.get("tags")[0]["term"]) if e.get("tags") else ""
            rows.append({
                "Grant Title": title,
                "Agency": agency,
                "Category": cat,
                "Short Summary": desc[:320],
                "URL": link,
                "Posted Date": pub,
                "Last Seen": datetime.utcnow().strftime("%Y-%m-%d"),
                "Source": url.rsplit("/",1)[-1],
                "_id": hashlib.sha256((title + '|' + link).encode('utf-8')).hexdigest()[:16],
            })
    return pd.DataFrame(rows, columns=COLUMNS), totals

def merge(new_df, path):
    if os.path.exists(path):
        old = pd.read_csv(path)
        if "_id" not in old.columns:
            old["_id"] = old.apply(lambda r: hashlib.sha256(((r.get("Grant Title","") + "|" + r.get("URL",""))).encode("utf-8")).hexdigest()[:16], axis=1)
    else:
        old = pd.DataFrame(columns=COLUMNS)
    merged = pd.concat([old, new_df], ignore_index=True)
    merged.sort_values(["_id","Last Seen"], inplace=True)
    merged = merged.drop_duplicates(subset=["_id"], keep="last")
    return merged[COLUMNS]

def main():
    new_df, totals = fetch_all()
    merged = merge(new_df, OUTPUT_CSV)
    merged.to_csv(OUTPUT_CSV, index=False)
    log = {
        "run_at_utc": datetime.utcnow().isoformat(),
        "feeds_checked": [{"url": k, "entries_found": v} for k,v in totals.items()],
        "new_records_fetched": len(new_df),
        "total_records_after_merge": len(merged),
        "note": "Basic updater runs with NO FILTERS."
    }
    with open(LOG_FILE, "w") as f: json.dump(log, f, indent=2)
    print("Feed entry counts:")
    for k,v in totals.items(): print(f"  {v:4d}  {k}")
    print(f"OK: {OUTPUT_CSV} now has {len(merged)} rows. Log: {LOG_FILE}")

if __name__ == "__main__":
    main()
