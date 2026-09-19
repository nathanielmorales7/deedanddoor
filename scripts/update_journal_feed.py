#!/usr/bin/env python3
"""
Regenerates the "latest journal post" hero card and 3-card teaser grid on
index.html from the actual set of published Journal posts, so the homepage
never goes stale again after a new post is added.

Reads two kinds of posts:
  1. Flat hand-built files in the repo root: journal-*.html
  2. Jekyll/Decap CMS posts: _posts/*.md (front matter + markdown body)

For each post it needs: title, publish date, a short excerpt, and the URL
the post lives at. It sorts everything by date (newest first), then
rewrites the two marked blocks in index.html:

  <!--JOURNAL:HERO--> ... <!--/JOURNAL:HERO-->   (newest post)
  <!--JOURNAL:GRID--> ... <!--/JOURNAL:GRID-->    (3 newest posts)

Only writes index.html if the generated content actually changed, so a
no-op run doesn't create an empty commit.
"""

import glob
import os
import re
import sys
from datetime import datetime

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_PATH = os.path.join(REPO_ROOT, "index.html")

HERO_START = "<!--JOURNAL:HERO-->"
HERO_END = "<!--/JOURNAL:HERO-->"
GRID_START = "<!--JOURNAL:GRID-->"
GRID_END = "<!--/JOURNAL:GRID-->"


def strip_tags(text):
    return re.sub(r"<[^>]+>", "", text).strip()


def short_date(dt):
    """'Sep 19' style, no leading zero, no OS-specific strftime flags."""
    return "{} {}".format(dt.strftime("%b"), dt.day)


def parse_flat_post(path):
    """Parse a hand-built journal-*.html post from the repo root."""
    with open(path, "r", encoding="utf-8") as f:
        html = f.read()

    hero_section = re.search(
        r'<section class="idx-page article-hero">(.*?)</section>', html, re.S
    )
    if not hero_section:
        print("  skip {}: no article-hero section found".format(path))
        return None
    hero_html = hero_section.group(1)

    title_match = re.search(r"<h1>(.*?)</h1>", hero_html, re.S)
    if not title_match:
        print("  skip {}: no <h1> found".format(path))
        return None
    title = strip_tags(title_match.group(1))

    meta_match = re.search(
        r'<div class="article-meta">(.*?)</div>', hero_html, re.S
    )
    if not meta_match:
        print("  skip {}: no .article-meta found".format(path))
        return None
    meta_text = strip_tags(meta_match.group(1))
    date_part = meta_text.split("·")[0].strip()  # split on "·"
    try:
        date = datetime.strptime(date_part, "%b %d, %Y")
    except ValueError:
        print("  skip {}: could not parse date '{}'".format(path, date_part))
        return None

    desc_match = re.search(
        r'<meta\s+name="description"\s+content="([^"]*)"', html
    )
    excerpt = desc_match.group(1).strip() if desc_match else ""
    if not excerpt:
        print("  warn {}: no meta description, excerpt will be blank".format(path))

    return {
        "title": title,
        "date": date,
        "excerpt": excerpt,
        "href": os.path.basename(path),
    }


def parse_front_matter(md_text):
    """Very small YAML front-matter parser — just enough for this repo's
    flat 'key: value' post fields (no nested structures)."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", md_text, re.S)
    if not match:
        return {}, md_text
    raw_fm, body = match.group(1), match.group(2)
    fields = {}
    for line in raw_fm.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        value = value.strip().strip('"').strip("'")
        fields[key.strip()] = value
    return fields, body


def parse_cms_post(path):
    """Parse a Decap CMS-authored post from _posts/*.md."""
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()

    fields, body = parse_front_matter(raw)
    title = fields.get("title", "").strip()
    if not title:
        print("  skip {}: no title in front matter".format(path))
        return None

    date_raw = fields.get("date", "").strip()
    date = None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            date = datetime.strptime(date_raw, fmt)
            break
        except ValueError:
            continue
    if date is None:
        # fall back to the date prefix Decap puts in the filename itself
        name_match = re.match(r"(\d{4}-\d{2}-\d{2})-", os.path.basename(path))
        if name_match:
            date = datetime.strptime(name_match.group(1), "%Y-%m-%d")
        else:
            print("  skip {}: could not parse a date".format(path))
            return None

    excerpt = fields.get("excerpt", "").strip()
    if not excerpt:
        # fall back to the first non-empty paragraph of the body
        for para in body.split("\n\n"):
            para = strip_tags(re.sub(r"[*_`#>]", "", para)).strip()
            if para:
                excerpt = (para[:157] + "...") if len(para) > 160 else para
                break

    # Mirrors _config.yml's `permalink: /journal-:title.html` rule, where
    # Jekyll's :title is the filename slug with the leading date stripped.
    slug_match = re.match(
        r"\d{4}-\d{2}-\d{2}-(.+)\.md$", os.path.basename(path)
    )
    slug = slug_match.group(1) if slug_match else os.path.splitext(os.path.basename(path))[0]
    href = "journal-{}.html".format(slug)

    return {"title": title, "date": date, "excerpt": excerpt, "href": href}


def linked_flat_posts():
    """The set of journal-*.html filenames actually linked from journal.html.

    journal.html is the site's master post index and is already updated by
    hand whenever a new flat post is published (a separate step from this
    script). Treating it as the source of truth means a stray/duplicate
    journal-*.html file sitting in the repo but not linked from anywhere
    (e.g. an old draft that was renamed) can never leak onto the homepage."""
    journal_path = os.path.join(REPO_ROOT, "journal.html")
    if not os.path.exists(journal_path):
        return None  # no journal.html to check against; don't filter
    with open(journal_path, "r", encoding="utf-8") as f:
        html = f.read()
    return set(re.findall(r'href="(journal-[a-z0-9-]+\.html)"', html))


def collect_posts():
    posts = []
    valid_flat = linked_flat_posts()

    for path in sorted(glob.glob(os.path.join(REPO_ROOT, "journal-*.html"))):
        if valid_flat is not None and os.path.basename(path) not in valid_flat:
            print(
                "  skip {}: not linked from journal.html (looks like a stray/orphaned file)".format(
                    path
                )
            )
            continue
        post = parse_flat_post(path)
        if post:
            posts.append(post)

    for path in sorted(glob.glob(os.path.join(REPO_ROOT, "_posts", "*.md"))):
        post = parse_cms_post(path)
        if post:
            posts.append(post)

    posts.sort(key=lambda p: p["date"], reverse=True)
    return posts


def render_hero(post):
    return (
        '<div class="hero-card">\n'
        '  <div class="hero-post-tag">Latest from the journal · {date}</div>\n'
        "  <h3>{title}</h3>\n"
        "  <p>{excerpt}</p>\n"
        '  <a href="{href}" class="hero-post-link">Read the post →</a>\n'
        "</div>"
    ).format(
        date=short_date(post["date"]),
        title=post["title"],
        excerpt=post["excerpt"],
        href=post["href"],
    )


def render_grid(posts):
    cards = []
    for post in posts:
        cards.append(
            (
                '  <a class="blog-card" href="{href}">\n'
                '    <div class="blog-date">{date}</div>\n'
                "    <h3>{title}</h3>\n"
                "    <p>{excerpt}</p>\n"
                "  </a>"
            ).format(
                href=post["href"],
                date=short_date(post["date"]),
                title=post["title"],
                excerpt=post["excerpt"],
            )
        )
    return '<div class="blog-grid">\n' + "\n".join(cards) + "\n</div>"


def replace_between(html, start_marker, end_marker, new_inner):
    pattern = re.compile(
        re.escape(start_marker) + r".*?" + re.escape(end_marker), re.S
    )
    replacement = start_marker + "\n" + new_inner + "\n" + end_marker
    if not pattern.search(html):
        raise SystemExit(
            "Could not find {} ... {} in index.html".format(
                start_marker, end_marker
            )
        )
    return pattern.sub(lambda m: replacement, html, count=1)


def main():
    posts = collect_posts()
    if not posts:
        print("No posts found — leaving index.html untouched.")
        return

    print("Found {} post(s), newest first:".format(len(posts)))
    for p in posts[:5]:
        print("  {}  {}  {}".format(p["date"].strftime("%Y-%m-%d"), p["href"], p["title"]))

    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        original = f.read()

    updated = replace_between(original, HERO_START, HERO_END, render_hero(posts[0]))
    updated = replace_between(updated, GRID_START, GRID_END, render_grid(posts[:3]))

    if updated == original:
        print("index.html already up to date; nothing to write.")
        return

    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        f.write(updated)
    print("index.html updated with the latest journal post(s).")


if __name__ == "__main__":
    sys.exit(main())
