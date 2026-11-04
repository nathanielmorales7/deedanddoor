#!/usr/bin/env python3
"""
post_to_gbp.py

Automatically creates a Google Business Profile "Local Post" linking to the
newest Deed & Door Journal entry, whenever one is published or updated.

How it decides what the "newest" post is:
  - journal.html is treated as the source of truth for which journal-*.html
    files count as real, live posts (same pattern used by
    scripts/update_journal_feed.py) - this filters out orphaned/unlinked
    files that still exist in the repo.
  - Each real post page carries a <script type="application/ld+json"> block
    with @type "BlogPosting" (added sitewide during the 2026-09-29 GEO push).
    That JSON-LD is the source of the post's headline, description, and
    datePublished - far more reliable than scraping visible byline text.
  - Posts are sorted by datePublished, newest first.

How it avoids reposting the same thing on every run:
  - The newest post's URL is recorded in scripts/.gbp_state.json after a
    successful post. If the newest post's URL matches what's already
    recorded, the script exits without calling the Google API at all.
  - This means the workflow can safely trigger on every push touching
    journal-*.html (edits to older posts, typo fixes, etc.) without
    spamming the Business Profile - it only ever posts when the *newest*
    post actually changes.

Required environment variables (set as GitHub Actions repo secrets):
  GOOGLE_CLIENT_ID       - OAuth 2.0 Web application client ID
  GOOGLE_CLIENT_SECRET   - OAuth 2.0 client secret
  GOOGLE_REFRESH_TOKEN   - long-lived refresh token (business.manage scope)
  GBP_ACCOUNT_ID         - numeric Business Profile account ID
  GBP_LOCATION_ID        - numeric Business Profile location ID

Exit codes:
  0 - success (either posted, or nothing new to post)
  1 - a real failure (parsing, auth, or API error) - should fail the Action
      so it's visible in the Actions tab rather than silently doing nothing.
"""

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SITE_BASE_URL = "https://deedanddoor.com"
STATE_FILE = Path(__file__).resolve().parent / ".gbp_state.json"

TOKEN_URL = "https://oauth2.googleapis.com/token"
LOCALPOSTS_URL_TMPL = (
    "https://mybusiness.googleapis.com/v4/accounts/{account_id}"
    "/locations/{location_id}/localPosts"
)

# Google's Local Post summary field has a hard cap; stay comfortably under it.
MAX_SUMMARY_LEN = 1500


def log(msg):
    print(msg, flush=True)


def get_real_journal_filenames():
    """journal.html is the source of truth for which journal-*.html files
    are real, live posts (filters out orphaned files sitting in the repo)."""
    journal_html = (REPO_ROOT / "journal.html").read_text(encoding="utf-8")
    filenames = sorted(set(re.findall(r'href="(journal-[a-z0-9\-]+\.html)"', journal_html)))
    if not filenames:
        raise RuntimeError("No journal-*.html links found in journal.html - can't determine real posts.")
    return filenames


def extract_blogposting_jsonld(html_text, filename):
    """Find the <script type="application/ld+json"> block whose @type is
    BlogPosting and return it as a parsed dict. Returns None if not found."""
    for match in re.finditer(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html_text,
        re.DOTALL | re.IGNORECASE,
    ):
        block_text = match.group(1).strip()
        try:
            data = json.loads(block_text)
        except json.JSONDecodeError:
            continue
        candidates = data if isinstance(data, list) else [data]
        for candidate in candidates:
            if isinstance(candidate, dict) and candidate.get("@type") == "BlogPosting":
                return candidate
    log(f"  (no BlogPosting JSON-LD found in {filename}, skipping)")
    return None


def load_posts():
    posts = []
    for filename in get_real_journal_filenames():
        path = REPO_ROOT / filename
        if not path.exists():
            log(f"  (journal.html links to {filename} but the file is missing, skipping)")
            continue
        html_text = path.read_text(encoding="utf-8")
        blogposting = extract_blogposting_jsonld(html_text, filename)
        if not blogposting:
            continue
        headline = (blogposting.get("headline") or "").strip()
        description = (blogposting.get("description") or "").strip()
        date_published = (blogposting.get("datePublished") or "").strip()
        if not (headline and date_published):
            log(f"  ({filename}'s BlogPosting block is missing headline or datePublished, skipping)")
            continue
        posts.append(
            {
                "filename": filename,
                "url": f"{SITE_BASE_URL}/{filename}",
                "headline": headline,
                "description": description,
                "date_published": date_published,
            }
        )
    if not posts:
        raise RuntimeError("No journal posts with usable BlogPosting JSON-LD were found.")
    posts.sort(key=lambda p: p["date_published"], reverse=True)
    return posts


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def build_summary(headline, description):
    summary = f"New on the Deed & Door Journal: {headline}"
    if description:
        summary = f"{summary} — {description}"
    if len(summary) > MAX_SUMMARY_LEN:
        summary = summary[: MAX_SUMMARY_LEN - 1].rstrip() + "…"
    return summary


def get_access_token(client_id, client_secret, refresh_token):
    body = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    encoded = "&".join(f"{k}={urllib.parse.quote(v)}" for k, v in body.items())
    req = urllib.request.Request(
        TOKEN_URL,
        data=encoded.encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Token refresh failed: HTTP {e.code} - {e.read().decode('utf-8', 'ignore')}") from e
    access_token = payload.get("access_token")
    if not access_token:
        raise RuntimeError(f"Token refresh response had no access_token: {payload}")
    return access_token


def create_local_post(access_token, account_id, location_id, post):
    url = LOCALPOSTS_URL_TMPL.format(account_id=account_id, location_id=location_id)
    body = {
        "languageCode": "en-US",
        "summary": build_summary(post["headline"], post["description"]),
        "topicType": "STANDARD",
        "callToAction": {
            "actionType": "LEARN_MORE",
            "url": post["url"],
        },
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"localPosts create failed: HTTP {e.code} - {e.read().decode('utf-8', 'ignore')}") from e


def main():
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    refresh_token = os.environ.get("GOOGLE_REFRESH_TOKEN")
    account_id = os.environ.get("GBP_ACCOUNT_ID")
    location_id = os.environ.get("GBP_LOCATION_ID")

    missing = [
        name
        for name, val in [
            ("GOOGLE_CLIENT_ID", client_id),
            ("GOOGLE_CLIENT_SECRET", client_secret),
            ("GOOGLE_REFRESH_TOKEN", refresh_token),
            ("GBP_ACCOUNT_ID", account_id),
            ("GBP_LOCATION_ID", location_id),
        ]
        if not val
    ]
    if missing:
        log(f"ERROR: missing required environment variable(s): {', '.join(missing)}")
        sys.exit(1)

    log("Scanning journal posts...")
    posts = load_posts()
    newest = posts[0]
    log(f"Newest post: {newest['headline']!r} ({newest['url']}, published {newest['date_published']})")

    state = load_state()
    if state.get("last_posted_url") == newest["url"]:
        log("Already posted this one - nothing to do.")
        sys.exit(0)

    log("Refreshing Google OAuth access token...")
    access_token = get_access_token(client_id, client_secret, refresh_token)

    log("Creating Google Business Profile local post...")
    result = create_local_post(access_token, account_id, location_id, newest)
    log(f"Posted successfully: {result.get('name', '(no name returned)')}")

    save_state(
        {
            "last_posted_url": newest["url"],
            "last_posted_headline": newest["headline"],
            "last_posted_date_published": newest["date_published"],
        }
    )
    log("State file updated.")


if __name__ == "__main__":
    main()
