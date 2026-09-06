#!/usr/bin/env python3
"""Fetch the latest daily mortgage rate data from FRED (Optimal Blue Mortgage
Market Indices) and update the rate ledger bar in index.html.

Data source: https://fred.stlouisfed.org/series/OBMMIC30YF
             https://fred.stlouisfed.org/series/OBMMIC15YF
These are public, no-API-key, no-cost series published by the Federal Reserve
Bank of St. Louis, updated daily on business days. No commercial-use
restriction; attribution is included in the page footer/caption.

This script is meant to be run by .github/workflows/update-rates.yml on a
schedule. It only rewrites index.html; it does not commit or push (the
workflow handles that).
"""
import re
import sys
import urllib.request
from datetime import datetime

SERIES = {
    "30YR": "OBMMIC30YF",
    "15YR": "OBMMIC15YF",
}

INDEX_HTML = "index.html"


def fetch_latest(series_id):
    url = f"https://fred.stlouisfed.org/data/{series_id}.txt"
    req = urllib.request.Request(
        url,
        headers={
            # FRED serves a different (non-data) response to generic
            # scripted user agents; a normal browser-looking UA gets the
            # plain-text data file.
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/plain,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        text = resp.read().decode("utf-8", errors="replace")

    last_date, last_val = None, None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 2:
            continue
        try:
            datetime.strptime(parts[0], "%Y-%m-%d")
            float(parts[1])
        except ValueError:
            continue
        last_date, last_val = parts[0], parts[1]

    if last_date is None:
        preview = " | ".join(text.splitlines()[:15])
        raise RuntimeError(
            f"Could not parse any data rows from {series_id} ({url}). "
            f"First lines of response: {preview[:500]}"
        )
    return last_date, last_val


def fmt_pct(val):
    return f"{float(val):.2f}%"


def fmt_date(date_str):
    d = datetime.strptime(date_str, "%Y-%m-%d")
    # Cross-platform day-of-month without leading zero
    return f"{d.strftime('%b')} {d.day}, {d.year}"


def replace_marker(html, key, new_value):
    pattern = re.compile(rf"(<!--RATE:{key}-->)(.*?)(<!--/RATE:{key}-->)", re.DOTALL)
    if not pattern.search(html):
        raise RuntimeError(f"Marker RATE:{key} not found in {INDEX_HTML}")
    return pattern.sub(lambda m: m.group(1) + new_value + m.group(3), html)


def main():
    date30, val30 = fetch_latest(SERIES["30YR"])
    date15, val15 = fetch_latest(SERIES["15YR"])
    as_of_date = max(date30, date15)

    with open(INDEX_HTML, "r", encoding="utf-8") as f:
        html = f.read()

    html = replace_marker(html, "30YR", fmt_pct(val30))
    html = replace_marker(html, "15YR", fmt_pct(val15))
    html = replace_marker(html, "ASOF", f"Updated {fmt_date(as_of_date)}")

    with open(INDEX_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"30-yr fixed: {fmt_pct(val30)} (as of {date30})")
    print(f"15-yr fixed: {fmt_pct(val15)} (as of {date15})")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"update_rates.py failed: {exc}", file=sys.stderr)
        sys.exit(1)
