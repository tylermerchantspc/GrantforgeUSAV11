If your first updater returned 0 rows:
1) Open Terminal in the V11_FaithMode/data folder.
2) Run:
   python rss_auto_to_csv_basic.py
3) It will show how many entries each RSS feed returned, and it will fill cache_v1.csv with everything (no filters).
4) Open cache_v1.csv in Excel to confirm rows exist.
5) If rows appear, we can add filters later. If not, your network may be blocking RSS or the feeds are temporarily empty.
