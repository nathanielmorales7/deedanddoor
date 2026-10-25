#!/usr/bin/env python3
"""
Updates the "median sale price" stat on each DFW city landing page from
Redfin's public city-level housing market data (the "city_market_tracker"
file Redfin publishes for free reuse via its Data Center).

How it works:
  1. Downloads and streams Redfin's city_market_tracker.tsv.gz (covers every
     US city Redfin tracks, refreshed monthly).
  2. For each city listed in cities.json, finds the most recent row where
     region_type == "city" and property_type == "All Residential".
  3. Rewrites the content between the "AUTO:PRICE:START" / "AUTO:PRICE:END"
     HTML comments in that city's page with the new price and the month it's
     as of.

This script only edits text between those two markers — nothing else on the
page is touched. If a city can't be found in the data (name mismatch, schema
change upstream, etc.) it's skipped and reported, not guessed at.

Run manually to test:
    python3 update_city_stats.py --cities-dir ../../..
"""

import argparse
import csv
import gzip
import io
import json
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

REDFIN_URL = "https://redfin-public-data.s3-us-west-2.amazonaws.com/redfin_market_tracker/city_market_tracker.tsv000.gz"

MARKER_START = "<!-- AUTO:PRICE:START -->"
MARKER_END = "<!-- AUTO:PRICE:END -->"

MONTH_ABBR = ["Jan.", "Feb.", "Mar.", "Apr.", "May", "June", "July",
              "Aug.", "Sept.", "Oct.", "Nov.", "Dec."]


def fetch_latest_prices(target_regions):
    """
    Streams the Redfin city_market_tracker file and returns, for each
    requested "City, ST" region, the most recent (period_end, median_sale_price)
    found for region_type == "city" and property_type == "All Residential".
    """
    print(f"Downloading {REDFIN_URL} ...", file=sys.stderr)
    req = urllib.request.Request(REDFIN_URL, headers={"User-Agent": "deedanddoor-stats-bot/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        raw = resp.read()

    print(f"Downloaded {len(raw):,} bytes, decompressing + scanning ...", file=sys.stderr)
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as gz:
        text_stream = io.TextIOWrapper(gz, encoding="utf-8", errors="replace")
        reader = csv.DictReader(text_stream, delimiter="\t")

        best = {}  # region -> (period_end date, median_sale_price str)
        wanted = set(target_regions)

        for row in reader:
            if row.get("region_type") != "city":
                continue
            if row.get("property_type") != "All Residential":
                continue
            region = (row.get("region") or "").strip()
            if region not in wanted:
                continue

            period_end_raw = row.get("period_end")
            price_raw = row.get("median_sale_price")
            if not period_end_raw or not price_raw:
                continue
            try:
                period_end = datetime.strptime(period_end_raw[:10], "%Y-%m-%d")
                price = float(price_raw)
            except ValueError:
                continue

            prev = best.get(region)
            if prev is None or period_end > prev[0]:
                best[region] = (period_end, price)

    return best


def format_stat_block(period_end, price, indent):
    month_label = f"{MONTH_ABBR[period_end.month - 1]} {period_end.year}"
    price_label = f"${price:,.0f}"
    return (
        f"{indent}{MARKER_START}\n"
        f"{indent}<div class=\"val\">{price_label}</div>\n"
        f"{indent}<div class=\"sub\">Redfin, {month_label}</div>\n"
        f"{indent}{MARKER_END}"
    )


def update_file(path, period_end, price):
    original = path.read_text(encoding="utf-8")
    pattern = re.compile(
        r"([ \t]*)" + re.escape(MARKER_START) + r".*?" + re.escape(MARKER_END),
        re.DOTALL,
    )
    match = pattern.search(original)
    if not match:
        print(f"  [skip] {path.name}: no AUTO:PRICE markers found", file=sys.stderr)
        return False

    indent = match.group(1)
    replacement = format_stat_block(period_end, price, indent)
    updated = pattern.sub(replacement, original, count=1)

    if updated == original:
        print(f"  [no change] {path.name}: already up to date", file=sys.stderr)
        return False

    path.write_text(updated, encoding="utf-8")
    print(f"  [updated] {path.name}: ${price:,.0f} as of "
          f"{MONTH_ABBR[period_end.month - 1]} {period_end.year}", file=sys.stderr)
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cities-dir", default=".",
                         help="Directory containing the city HTML pages (default: current dir)")
    parser.add_argument("--config", default=str(Path(__file__).with_name("cities.json")),
                         help="Path to cities.json")
    args = parser.parse_args()

    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    cities = config["cities"]
    target_regions = [c["redfin_region"] for c in cities]

    prices = fetch_latest_prices(target_regions)

    any_changed = False
    missing = []
    print("\nResults:", file=sys.stderr)
    for city in cities:
        region = city["redfin_region"]
        file_path = Path(args.cities_dir) / city["file"]

        if region not in prices:
            missing.append(region)
            print(f"  [missing] {region}: not found in Redfin data "
                  f"(schema or name may have changed)", file=sys.stderr)
            continue

        if not file_path.exists():
            print(f"  [missing file] {file_path}", file=sys.stderr)
            continue

        period_end, price = prices[region]
        if update_file(file_path, period_end, price):
            any_changed = True

    if missing:
        print(f"\n{len(missing)} of {len(cities)} cities not found in this month's "
              f"data: {', '.join(missing)}. Nothing was changed for those pages.",
              file=sys.stderr)

    # Signal to the calling workflow whether anything changed.
    print("changed=true" if any_changed else "changed=false")


if __name__ == "__main__":
    main()
