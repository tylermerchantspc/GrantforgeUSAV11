#!/usr/bin/env python3
# Append a single grant row to cache_v1.csv (manual mode)
import csv, os, datetime, hashlib

CSV = "cache_v1.csv"
HEADERS = ["Grant Title","Agency","Category","Short Summary","URL","Posted Date","Last Seen","Source","_id"]

def ensure_headers():
    if not os.path.exists(CSV) or os.path.getsize(CSV) == 0:
        with open(CSV,"w",newline="",encoding="utf-8") as f:
            csv.writer(f).writerow(HEADERS)

def make_id(title, url):
    return hashlib.sha256(f"{title}|{url}".encode("utf-8")).hexdigest()[:16]

def ask(p):
    return input(p).strip()

def main():
    ensure_headers()
    print("\n== GrantforgeUSA Quick Add ==")
    title = ask("Grant Title: ")
    agency = ask("Agency: ")
    cat = ask("Category (Education / 501(c)(3) / Small Business / Church / Other): ")
    summ = ask("Short Summary (1–2 sentences): ")
    url = ask("URL: ")
    posted = ask("Posted Date (YYYY-MM-DD or blank): ")
    last_seen = datetime.date.today().isoformat()
    source = "Manual cache (shutdown mode)"
    _id = make_id(title, url)
    with open(CSV,"a",newline="",encoding="utf-8") as f:
        csv.writer(f).writerow([title,agency,cat,summ,url,posted,last_seen,source,_id])
    print(f"\nSaved to {CSV} ✔  (_id={_id})")

if __name__ == "__main__":
    main()