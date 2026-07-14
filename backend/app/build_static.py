import hashlib
import json
import logging
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import BACKEND_DIR
from .fetch import Article, fetch_all, load_feeds

logger = logging.getLogger(__name__)

RAW_ITEM_LIMIT = 80  # up to 10 per feed across 8 configured feeds
MAX_ARTICLE_AGE = timedelta(days=3)
OUTPUT_PATH = BACKEND_DIR.parent / "docs" / "data" / "latest.json"


def stable_id(guid: str) -> str:
    """A short, DOM/localStorage-safe id derived from the article's GUID.
    There's no database anymore, so this replaces the old auto-increment id —
    it just needs to be stable across runs so hide/save/read tracking (all
    client-side now) keeps working as the same article reappears in future
    fetches."""
    return hashlib.sha1(guid.encode("utf-8")).hexdigest()[:12]


def round_robin(rows: list[dict], source_order: list[str], limit: int) -> list[dict]:
    """Interleave rows (already sorted newest-first) one-per-source, cycling
    through source_order repeatedly, so no single high-volume feed dominates."""
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(row["source"], []).append(row)

    ordered_sources = [s for s in source_order if s in groups]
    for s in groups:
        if s not in ordered_sources:
            ordered_sources.append(s)

    result: list[dict] = []
    idx = 0
    while len(result) < limit:
        added_any = False
        for source in ordered_sources:
            group = groups[source]
            if idx < len(group):
                result.append(group[idx])
                added_any = True
                if len(result) >= limit:
                    break
        if not added_any:
            break
        idx += 1
    return result


def article_to_dict(article: Article) -> dict:
    d = asdict(article)
    d["id"] = stable_id(article.guid)
    del d["guid"]
    return d


def is_recent(item: dict, now: datetime, max_age: timedelta) -> bool:
    published_at = item.get("published_at")
    if not published_at:
        # A handful of feed entries omit a publish date. Rather than
        # silently dropping otherwise-valid articles, give them the
        # benefit of the doubt and keep them.
        return True
    try:
        published = datetime.fromisoformat(published_at)
    except ValueError:
        return True
    return (now - published) <= max_age


def build(output_path: Path = OUTPUT_PATH) -> int:
    articles = fetch_all()
    items = [article_to_dict(a) for a in articles]
    items.sort(key=lambda i: i["published_at"] or "", reverse=True)

    now = datetime.now(timezone.utc)
    before_age_filter = len(items)
    items = [i for i in items if is_recent(i, now, MAX_ARTICLE_AGE)]
    logger.info(
        "Age filter (<= %d days): kept %d of %d articles",
        MAX_ARTICLE_AGE.days,
        len(items),
        before_age_filter,
    )

    source_order = [feed["name"] for feed in load_feeds()]
    selected = round_robin(items, source_order, RAW_ITEM_LIMIT)

    payload = {
        "mode": "raw",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "items": selected,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return len(selected)


def run_build() -> None:
    count = build()
    logger.info("Wrote %d items to %s", count, OUTPUT_PATH)
    print(f"Wrote {count} articles to {OUTPUT_PATH}")
