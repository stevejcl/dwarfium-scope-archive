"""
api/wiki_images.py

Looks up a representative image for a DSO catalog target from Wikipedia /
Wikimedia Commons, along with its licensing metadata, and caches the result
in DsoImageCache so we only hit the network once per target.

Lookup strategy — IMPORTANT:
  We resolve candidate Wikipedia titles by EXACT title + redirect lookup
  only (action=query&titles=...&redirects=1), never by Wikipedia's
  free-text search. Free-text search on a bare catalog code like "NGC 7234"
  or "M 110" is unreliable — it matches on loose relevance rather than
  requiring the string to actually be a page title, and short alphanumeric
  astro codes collide with unrelated topics (e.g. "NGC" is also the
  Numismatic Guaranty Company, so "NGC 7234" can match a coin-grading
  article; "M 110" can match "110 m haies", a French athletics event).
  Exact-title + redirects lookup requires the string to literally BE (or
  redirect to) a real page title, which avoids that whole failure class.
  If no candidate title resolves to a page with an image, we treat the
  target as having no image rather than falling back to a risky free-text
  search — a missing photo is fine, a wrong one is not.

Licensing approach:
  - We resolve the image through Commons (not a raw Wikipedia page image),
    because Commons enforces free-license-only uploads. A Wikipedia
    article's lead image is sometimes a *local*, non-free "fair use"
    upload that only Wikipedia itself is allowed to display — those never
    live on Commons, so if the lookup can't find the file there we treat
    it as unusable and cache a "not_found" result rather than guessing.
  - Every image we do cache carries its license short name + artist/credit
    string, so the UI can render a proper attribution line next to it.

Network: a handful of lightweight calls per uncached target (one per
candidate title tried, then one Commons imageinfo call). Nothing here is
called automatically at startup or in a tight loop — callers should gate
this behind an explicit "show images" opt-in (offline-first: no surprise
network use) and cache aggressively.
"""

from __future__ import annotations

import re
import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import Optional

import requests

WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
REQUEST_TIMEOUT = 6  # seconds — keep short, this must never hang the UI

# Wikimedia's API etiquette policy requires a descriptive User-Agent with a
# real way to reach the operator — requests without one get rate-limited or
# blocked outright. Replace the contact with a real email/URL before release.
WIKIPEDIA_HEADERS = {
    "User-Agent": "DwarfiumScopeArchive/1.0 (https://github.com/stevejcl/dwarfium-scope-archive)"
}

# The UI can kick off many concurrent lookups at once (one background task
# per visible target card). A burst of simultaneous requests from the same
# IP looks like abuse to Wikimedia's edge, and gets 403'd even with a
# compliant User-Agent. This serializes all Wikimedia/Commons calls across
# threads with a minimum spacing between them, regardless of how many cards
# are loading in parallel.
_RATE_LOCK = threading.Lock()
_MIN_REQUEST_INTERVAL = 0.4  # seconds between requests, across all threads
_last_request_ts = 0.0


def _throttled_get(url: str, params: dict):
    global _last_request_ts
    with _RATE_LOCK:
        wait = _last_request_ts + _MIN_REQUEST_INTERVAL - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        resp = requests.get(url, params=params, headers=WIKIPEDIA_HEADERS, timeout=REQUEST_TIMEOUT)
        _last_request_ts = time.monotonic()
    return resp

# Re-attempt a lookup that previously found nothing after this many days,
# in case a Wikipedia article/image has since appeared.
NOT_FOUND_RETRY_DAYS = 30

# Catalog prefix -> full name, used to build extra candidate titles.
# NGC/IC articles are titled exactly "NGC 1234" / "IC 1234" on Wikipedia,
# so those are left as-is (candidate list already includes the raw form).
CATALOG_PREFIX_EXPANSION = {
    "M": "Messier",
    "C": "Caldwell",
    "B": "Barnard",
    "SH2": "Sharpless",
}

_DESIGNATION_RE = re.compile(r"^\s*([A-Za-z]+)\s*(\d+)\s*$")


def _candidate_titles(catalog_id: str, display_name: Optional[str]) -> list[str]:
    """Build an ordered list of Wikipedia title candidates to try via exact
    title+redirect lookup. No free-text search — see module docstring."""
    candidates: list[str] = []

    def add(title: Optional[str]):
        if title and title not in candidates:
            candidates.append(title)

    add(catalog_id)

    m = _DESIGNATION_RE.match(catalog_id or "")
    if m:
        prefix, number = m.group(1).upper(), m.group(2)
        add(f"{prefix}{number}")  # e.g. "M110", "NGC7234" (common redirect form)
        expansion = CATALOG_PREFIX_EXPANSION.get(prefix)
        if expansion:
            add(f"{expansion} {number}")  # e.g. "Messier 110", "Caldwell 9"

    # Only try display_name if it looks like a plausible title, not a note
    # like "B 92 - on northside of M24".
    if display_name and " - " not in display_name and display_name != catalog_id:
        add(display_name)

    return candidates


def get_cached_image(conn: sqlite3.Connection, catalog_id: str) -> Optional[dict]:
    """Return the cached row for catalog_id, or None if nothing cached yet."""
    cur = conn.execute(
        "SELECT catalog_id, status, thumb_url, file_page_url, artist, "
        "license_short_name, credit, fetched_at "
        "FROM DsoImageCache WHERE catalog_id = ?",
        (catalog_id,),
    )
    row = cur.fetchone()
    if not row:
        return None
    return {
        "catalog_id": row[0],
        "status": row[1],
        "thumb_url": row[2],
        "file_page_url": row[3],
        "artist": row[4],
        "license_short_name": row[5],
        "credit": row[6],
        "fetched_at": row[7],
    }


def _is_stale_not_found(cached: dict) -> bool:
    if cached["status"] != "not_found":
        return False
    try:
        fetched = datetime.fromisoformat(cached["fetched_at"])
    except (TypeError, ValueError):
        return True
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - fetched).days >= NOT_FOUND_RETRY_DAYS


def _upsert(conn: sqlite3.Connection, catalog_id: str, status: str, **fields) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    row = {
        "catalog_id": catalog_id,
        "status": status,
        "thumb_url": fields.get("thumb_url"),
        "file_page_url": fields.get("file_page_url"),
        "artist": fields.get("artist"),
        "license_short_name": fields.get("license_short_name"),
        "credit": fields.get("credit"),
        "fetched_at": now,
    }
    conn.execute(
        """
        INSERT INTO DsoImageCache
            (catalog_id, status, thumb_url, file_page_url, artist, license_short_name, credit, fetched_at)
        VALUES (:catalog_id, :status, :thumb_url, :file_page_url, :artist, :license_short_name, :credit, :fetched_at)
        ON CONFLICT(catalog_id) DO UPDATE SET
            status = excluded.status,
            thumb_url = excluded.thumb_url,
            file_page_url = excluded.file_page_url,
            artist = excluded.artist,
            license_short_name = excluded.license_short_name,
            credit = excluded.credit,
            fetched_at = excluded.fetched_at
        """,
        row,
    )
    conn.commit()
    return row


def _strip_html(text: Optional[str]) -> str:
    if not text:
        return ""
    return re.sub(r"<[^>]+>", "", text).strip()


def _lookup_pageimage_by_title(title: str) -> Optional[str]:
    """Exact title + redirect lookup — no free-text search. Returns the lead
    image's file title (e.g. 'Andromeda Galaxy.jpg') if the title (or a
    redirect from it) resolves to a real Wikipedia page with an image."""
    params = {
        "action": "query",
        "format": "json",
        "titles": title,
        "redirects": 1,
        "prop": "pageimages",
        "piprop": "name",
    }
    resp = _throttled_get(WIKIPEDIA_API, params)
    resp.raise_for_status()
    pages = (resp.json().get("query") or {}).get("pages") or {}
    for page in pages.values():
        if "missing" in page:
            continue
        name = page.get("pageimage")
        if name:
            return name
    return None


def _fetch_commons_imageinfo(filename: str) -> Optional[dict]:
    """Look up filename ('Foo.jpg') on Commons and return url + license
    metadata, or None if the file isn't hosted on Commons (e.g. it's a
    local non-free fair-use upload on Wikipedia, which we must not use)."""
    params = {
        "action": "query",
        "format": "json",
        "titles": f"File:{filename}",
        "prop": "imageinfo",
        "iiprop": "url|extmetadata",
        "iiurlwidth": 500,
    }
    resp = _throttled_get(COMMONS_API, params)
    resp.raise_for_status()
    pages = (resp.json().get("query") or {}).get("pages") or {}
    for page in pages.values():
        if "missing" in page:
            continue
        infos = page.get("imageinfo") or []
        if not infos:
            continue
        info = infos[0]
        meta = info.get("extmetadata") or {}
        return {
            "thumb_url": info.get("thumburl") or info.get("url"),
            "file_page_url": info.get("descriptionurl"),
            "artist": _strip_html((meta.get("Artist") or {}).get("value")),
            "license_short_name": (meta.get("LicenseShortName") or {}).get("value") or "",
            "credit": _strip_html((meta.get("Credit") or {}).get("value")),
        }
    return None


def fetch_and_cache_image(conn: sqlite3.Connection, catalog_id: str, display_name: str) -> Optional[dict]:
    """Look up an image for this target, caching the outcome either way.
    Returns the cached dict on success, or None if unavailable (no image,
    no usable license, or a network error)."""
    cached = get_cached_image(conn, catalog_id)
    if cached is not None and not _is_stale_not_found(cached):
        return cached if cached["status"] == "found" else None

    try:
        filename = None
        for title in _candidate_titles(catalog_id, display_name):
            filename = _lookup_pageimage_by_title(title)
            if filename:
                break

        if not filename:
            row = _upsert(conn, catalog_id, "not_found")
            return None

        info = _fetch_commons_imageinfo(filename)
        if not info or not info["thumb_url"]:
            # Image exists on Wikipedia but not on Commons -> most likely a
            # non-free local upload. Don't use it.
            row = _upsert(conn, catalog_id, "not_found")
            return None

        row = _upsert(conn, catalog_id, "found", **info)
        return row

    except requests.RequestException as e:
        # Network/offline: don't cache a permanent failure, just skip for now.
        print(f"[wiki_images] lookup failed for {catalog_id}: {e}")
        return None
    except Exception as e:
        print(f"[wiki_images] unexpected error for {catalog_id}: {e}")
        return None