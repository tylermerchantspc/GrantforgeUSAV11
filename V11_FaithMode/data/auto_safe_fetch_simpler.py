#!/usr/bin/env python3
# GrantforgeUSA — Simpler.Grants.gov full fetch (no API keys)
# Crawls search pages, visits each opportunity, extracts Title/Agency/Deadline (if present),
# includes items even with no visible deadline when SAFE_DAYS == 0,
# writes safe_cache_v1.csv

import os
import re
import time
import hashlib
from typing import List, Optional, Tuple
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup
import pandas as pd

# -------------------- SETTINGS --------------------
BASE = "https://simpler.grants.gov"

# If empty, we'll auto-paginate /search?page=1..until empty (up to PAGE_CAP)
CUSTOM_SEARCH_URLS: List[str] = []

PAGE_CAP = 300               # hard cap so we don't loop forever
REQUEST_DELAY = 0.5          # seconds between requests (be polite)
TIMEOUT = 30                 # request timeout
MAX_RETRIES = 3
RETRY_SLEEP = 1.5

SAFE_DAYS = 0                # 0 = include everything; >0 = require that many days left
INCLUDE_NO_DEADLINE = True   # include rows that lack a readable deadline when SAFE_DAYS == 0

OUTPUT = "safe_cache_v1.csv"

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome Safari"
    )
}
# ---------------------------------------------------

# Month maps (full and short)
MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9,
    "oct": 10, "nov": 11, "dec": 12
}

# Labels we look for on detail pages
DEADLINE_LABELS = ["Close Date", "Closing", "Closes", "Application Closing Date", "Closing Date"]
POSTED_LABELS   = ["Posted", "Open Date", "Posting Date", "Post Date"]

# Human date like "January 21, 2026" or "Jan 21, 2026"
DATE_REGEX = re.compile(r"\b([A-Za-z]{3,9})\s+(\d{1,2}),\s*(\d{4})\b")

session = requests.Session()
session.headers.update(UA)

def fetch(url: str) -> str:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = session.get(url, timeout=TIMEOUT)
            r.raise_for_status()
            time.sleep(REQUEST_DELAY)
            return r.text
        except Exception:
            if attempt == MAX_RETRIES:
                raise
            time.sleep(RETRY_SLEEP)
    return ""

def month_to_num(mon: str) -> Optional[int]:
    return MONTHS.get(mon.strip().lower())

def parse_human_date(txt: str) -> Optional[str]:
    if not txt:
        return None
    m = DATE_REGEX.search(txt)
    if not m:
        return None
    mon = month_to_num(m.group(1))
    if not mon:
        return None
    try:
        day = int(m.group(2))
        year = int(m.group(3))
        dt = datetime(year, mon, day, tzinfo=timezone.utc)
        return dt.date().isoformat()
    except Exception:
        return None

def text_of(el) -> str:
    return el.get_text(" ", strip=True) if el else ""

def first_match_text(soup: BeautifulSoup, labels: List[str]) -> Optional[str]:
    # Try several HTML patterns: data-testid, label text with nearby value, dt/dd tables.
    # 1) data-testid variants often used on Simpler
    for label in labels:
        for key in [
            label.lower().replace(" ", "-"),
            label.lower().replace(" ", ""),
            label.lower().replace(" ", "_"),
        ]:
            tag = soup.find(attrs={"data-testid": key})
            if tag:
                iso = parse_human_date(text_of(tag))
                if iso:
                    return iso

    # 2) literal text labels in the DOM
    for label in labels:
        lbl = soup.find(string=re.compile(rf"{re.escape(label)}", re.I))
        if lbl:
            parent = getattr(lbl, "parent", None)
            if parent:
                # parent text
                iso = parse_human_date(text_of(parent))
                if iso:
                    return iso
                # dt/dd or th/td patterns
                if parent.name in ("dt", "th"):
                    dd = parent.find_next("dd") or parent.find_next("td")
                    if dd:
                        iso = parse_human_date(text_of(dd))
                        if iso:
                            return iso
                # next sibling string containing a date
                sib = parent.find_next(string=DATE_REGEX)
                if sib:
                    iso = parse_human_date(str(sib))
                    if iso:
                        return iso
    return None

def find_dates(soup: BeautifulSoup, fulltext: str) -> Tuple[Optional[str], Optional[str]]:
    deadline_iso = first_match_text(soup, DEADLINE_LABELS)
    posted_iso   = first_match_text(soup, POSTED_LABELS)

    # Fallback to full text
    if not deadline_iso:
        deadline_iso = parse_human_date(fulltext)
    if not posted_iso:
        posted_iso = parse_human_date(fulltext)

    return deadline_iso, posted_iso

def opportunity_to_record(url: str) -> Optional[dict]:
    try:
        html = fetch(url)
    except Exception:
        return None

    soup = BeautifulSoup(html, "lxml")

    # Title
    h1 = soup.find("h1")
    title = text_of(h1)

    # Full text for fallbacks
    fulltext = soup.get_text("\n", strip=True)

    # Agency
    agency = ""
    m_ag = re.search(r"Agency\s*:\s*(.+?)(?:\n|$)", fulltext)
    if m_ag:
        agency = m_ag.group(1).strip()

    # Dates
    deadline_iso, posted_iso = find_dates(soup, fulltext)

    # Days left (only if we have a deadline)
    days_left_str = ""
    if deadline_iso:
        try:
            dl = datetime.fromisoformat(deadline_iso)
            days_left = (dl - datetime.now(timezone.utc)).days
            days_left_str = str(days_left)
            # Enforce cutoff if SAFE_DAYS > 0
            if SAFE_DAYS > 0 and days_left < SAFE_DAYS:
                return None
        except Exception:
            pass
    else:
        # No deadline present
        if SAFE_DAYS > 0 or not INCLUDE_NO_DEADLINE:
            return None

    # Short Summary
    short_summary = ""
    desc_hdr = soup.find(string=re.compile(r"Description", re.I))
    if desc_hdr and getattr(desc_hdr, "parent", None):
        short_summary = text_of(desc_hdr.parent)[:280]
    if not short_summary:
        short_summary = fulltext[:280]

    rec = {
        "Grant Title": title,
        "Agency": agency,
        "Category": "",
        "Short Summary": short_summary,
        "URL": url,
        "Posted Date": posted_iso or "",
        "Deadline": deadline_iso or "",
        "Days Left": days_left_str,
        "Last Seen": datetime.utcnow().date().isoformat(),
        "Source": "simpler.grants.gov",
        "_id": hashlib.sha256((title + "|" + url).encode("utf-8")).hexdigest()[:16],
    }
    return rec

def build_search_urls() -> List[str]:
    if CUSTOM_SEARCH_URLS:
        return CUSTOM_SEARCH_URLS[:]
    # Auto paginate until we stop finding new links or hit PAGE_CAP
    return [f"{BASE}/search?page={p}" for p in range(1, PAGE_CAP + 1)]

def search_links(url: str) -> List[str]:
    try:
        html = fetch(url)
    except Exception:
        return []
    soup = BeautifulSoup(html, "lxml")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/opportunity/" in href:
            links.append(href if href.startswith("http") else BASE + href)
    # unique preserve order
    seen, uniq = set(), []
    for L in links:
        if L not in seen:
            uniq.append(L); seen.add(L)
    return uniq

def main():
    # Gather links, stop when a page yields no links for 3 consecutive pages (to avoid crawling deep empties)
    consecutive_empty = 0
    all_links = []
    for url in build_search_urls():
        page_links = search_links(url)
        if not page_links:
            consecutive_empty += 1
            if consecutive_empty >= 3 and not CUSTOM_SEARCH_URLS:
                break
        else:
            consecutive_empty = 0
            all_links.extend(page_links)
        if len(all_links) > 5000:  # hard sanity cap
            break

    # unique list
    seen, links = set(), []
    for L in all_links:
        if L not in seen:
            links.append(L); seen.add(L)

    if not links:
        print("WARNING: No opportunity links found. Tip: put a filtered Simpler URL into CUSTOM_SEARCH_URLS and re-run.")
        return

    records = []
    for i, L in enumerate(links, start=1):
        rec = opportunity_to_record(L)
        if rec:
            records.append(rec)
        if i % 25 == 0:
            print(f"... processed {i} pages, kept {len(records)} so far")
        if len(records) >= 10000:  # safety limit
            break

    if not records:
        print("WARNING: No opportunities collected (check site structure or add filtered URLs).")
        return

    df = pd.DataFrame(records)
    # Normalize columns and dedupe
    cols = ["Grant Title","Agency","Category","Short Summary","URL","Posted Date","Deadline","Days Left","Last Seen","Source","_id"]
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    df = df[cols]
    df.sort_values(["_id","Last Seen"], inplace=True)
    df = df.drop_duplicates(subset=["_id"], keep="last")

    df.to_csv(OUTPUT, index=False, encoding="utf-8")
    print(f"OK: Safe cache rebuilt -> {OUTPUT} ({len(df)} records).")

if __name__ == "__main__":
    main()