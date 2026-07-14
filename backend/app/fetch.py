import html
import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from time import struct_time
from typing import Optional

import feedparser

from .config import FEEDS_PATH
from .db import get_connection, init_db

logger = logging.getLogger(__name__)

TAG_RE = re.compile(r"<[^>]+>")

# feedparser's default User-Agent honestly identifies itself as a feed
# reader. Tried swapping in a spoofed browser UA to dodge suspected bot
# blocking, but that backfired — ESPN's feed reliably returns zero entries
# for the spoofed UA and reliably works with the honest one. Don't
# reintroduce a custom agent without re-testing against all feeds first.
FETCH_RETRIES = 3
FETCH_RETRY_DELAY_SECONDS = 3


@dataclass
class Article:
    guid: str
    source: str
    title: str
    link: str
    published_at: Optional[str]
    summary_raw: str


def load_feeds() -> list[dict]:
    with open(FEEDS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def clean_text(raw: Optional[str]) -> str:
    if not raw:
        return ""
    text = TAG_RE.sub(" ", raw)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def parsed_time_to_iso(t: Optional[struct_time]) -> Optional[str]:
    if not t:
        return None
    return datetime(*t[:6], tzinfo=timezone.utc).isoformat()


def fetch_feed(name: str, url: str) -> list[Article]:
    # Retry on *any* empty result, not just parse errors — a feed can return
    # a well-formed but empty response (bozo=False, zero entries) during a
    # transient block/rate-limit, which isn't a parse failure at all.
    parsed = None
    for attempt in range(1, FETCH_RETRIES + 1):
        parsed = feedparser.parse(url)
        if parsed.entries:
            break
        reason = f": {parsed.get('bozo_exception')}" if parsed.bozo else " (empty response)"
        logger.warning("Attempt %d/%d for feed %s (%s) returned no entries%s", attempt, FETCH_RETRIES, name, url, reason)
        if attempt < FETCH_RETRIES:
            time.sleep(FETCH_RETRY_DELAY_SECONDS)

    if not parsed.entries:
        logger.warning("Giving up on feed %s (%s) after %d attempts", name, url, FETCH_RETRIES)
        return []

    articles = []
    for entry in parsed.entries:
        guid = entry.get("id") or entry.get("guid") or entry.get("link")
        link = entry.get("link")
        if not guid or not link:
            continue
        published = entry.get("published_parsed") or entry.get("updated_parsed")
        articles.append(
            Article(
                guid=guid,
                source=name,
                title=clean_text(entry.get("title", "")),
                link=link,
                published_at=parsed_time_to_iso(published),
                summary_raw=clean_text(entry.get("summary") or entry.get("description")),
            )
        )
    return articles


def fetch_all() -> list[Article]:
    feeds = load_feeds()
    all_articles: list[Article] = []
    for feed in feeds:
        name, url = feed["name"], feed["url"]
        try:
            articles = fetch_feed(name, url)
            logger.info("Fetched %d entries from %s", len(articles), name)
            all_articles.extend(articles)
        except Exception:
            logger.exception("Error fetching feed %s (%s)", name, url)
    return all_articles


def store_articles(articles: list[Article]) -> int:
    now = datetime.now(timezone.utc).isoformat()
    inserted = 0
    with get_connection() as conn:
        for a in articles:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO articles
                    (guid, source, title, link, published_at, summary_raw, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (a.guid, a.source, a.title, a.link, a.published_at, a.summary_raw, now),
            )
            if cur.rowcount:
                inserted += 1
    return inserted


def run_fetch() -> None:
    init_db()
    articles = fetch_all()
    inserted = store_articles(articles)
    logger.info("Fetch complete: %d entries seen, %d new articles stored", len(articles), inserted)
    print(f"Fetched {len(articles)} entries across all feeds, stored {inserted} new articles.")
