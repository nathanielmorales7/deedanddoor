#!/usr/bin/env python3
"""Fetch the latest daily mortgage rate data from FRED (Optimal Blue Mortgage
Market Indices) and update the rate ledger bar in index.html.

Uses FRED's official API (api.stlouisfed.org), not the fred.stlouisfed.org
website's plain-text export — that export is meant for browsers and is
unreliable from datacenter/CI IP ranges (GitHub Actions included), which
either return an unparseable response or hang until timeout. The official
API is built for exactly this kind of automated access.

Series: https://fred.stlouisfed.org/series/OBMMIC30YF
        https://fred.stlouisfed.org/series/OBMMIC15YF
Free, no-cost, updated daily on business days. No commercial-use
restriction; attribution is included in the page footer/caption.

Requires a free FRED API key (get one at
https://fred.stlouisfed.org/docs/api/api_key.html) stored as the repo
secret FRED_API_KEY, passed to this script as an environment variable by
.github/workflows/update-rates.yml.

This script only rewrites index.html; it does not commit or push (the
workflow handles that).
"""
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime

SERIES = {
    "30YR": "OBMMIC30YF",
    "15YR": "OBMMIC15YF",
}

INDEX_HTML = "index.html"
API_KEY = os.environ.get("FRED_API_KEY", "").strip()


def fetch_latest(series_id):
    if not API_KEY:
        raise RuntimeError(
            "FRED_API_KEY environment variable is not set. "
            "Add it as a repo secret (Settings > Secrets and variables > "
            "Actions) and pass it to this step in the workflow file."
        )

    params = {
        "series_id": series_id,
        "api_key": API_KEY,
        "file_type": "json",
        "sort_order": "desc",
        "limit": 10,
    }
    url = "https://api.stlouisfed.org/fred/series/observations?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "deed-and-door-rate-bot/1.0"})

    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)

    for obs in data.get("observations", []):
        date_str, val_str = obs.get("date"), obs.get("value")
        if not date_str or val_str in (None, ".", ""):
            continue
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
            float(val_str)
        except ValueError:
            continue
        return date_str, val_str

    raise RuntimeError(f"No usable observations returned for {series_id}. Raw response: {data}")


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
    run_date = datetime.utcnow().strftime("%Y-%m-%d")

    with open(INDEX_HTML, "r", encoding="utf-8") as f:
        html = f.read()

    html = replace_marker(html, "30YR", fmt_pct(val30))
    html = replace_marker(html, "15YR", fmt_pct(val15))
    html = replace_marker(html, "ASOF", f"Last Checked {fmt_date(run_date)}")

    with open(INDEX_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"30-yr fixed: {fmt_pct(val30)} (as of {date30})")
    print(f"15-yr fixed: {fmt_pct(val15)} (as of {date15})")
    print(f"Last checked: {run_date}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"update_rates.py failed: {exc}", file=sys.stderr)
        sys.exit(1)
