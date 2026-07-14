import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import BACKEND_DIR
from .db import get_connection, init_db
from .fetch import fetch_all, load_feeds, store_articles

FRONTEND_DIR = BACKEND_DIR.parent / "docs"
FRONTEND_INDEX = FRONTEND_DIR / "index.html"
STATIC_DIR = FRONTEND_DIR / "static"
RAW_ITEM_LIMIT = 144  # up to 18 per feed across 8 configured feeds


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="News Aggregator", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class MuteRequest(BaseModel):
    keyword: str


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


def load_muted_keywords(conn) -> list[str]:
    rows = conn.execute("SELECT keyword FROM muted_keywords").fetchall()
    return [row["keyword"] for row in rows]


def filter_muted(rows: list[dict], keywords: list[str], text_field: str) -> list[dict]:
    if not keywords:
        return rows
    # Whole-word/phrase match only — a plain substring check on "mma" would
    # also hide anything containing "dilemma" or "summary".
    patterns = [re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE) for kw in keywords]
    filtered = []
    for row in rows:
        haystack = f"{row.get('title', '')} {row.get(text_field, '')}"
        if not any(p.search(haystack) for p in patterns):
            filtered.append(row)
    return filtered


def no_store(payload) -> JSONResponse:
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})


@app.get("/")
def serve_frontend():
    return FileResponse(FRONTEND_INDEX)


@app.post("/api/articles/{article_id}/hide")
def hide_article(article_id: int):
    with get_connection() as conn:
        conn.execute(
            "UPDATE articles SET hidden_at = datetime('now') WHERE id = ?",
            (article_id,),
        )
    return JSONResponse({"status": "ok"})


@app.post("/api/articles/{article_id}/save")
def save_article(article_id: int):
    with get_connection() as conn:
        conn.execute(
            "UPDATE articles SET saved_at = datetime('now') WHERE id = ?",
            (article_id,),
        )
    return JSONResponse({"status": "ok"})


@app.post("/api/articles/{article_id}/unsave")
def unsave_article(article_id: int):
    with get_connection() as conn:
        conn.execute(
            "UPDATE articles SET saved_at = NULL WHERE id = ?",
            (article_id,),
        )
    return JSONResponse({"status": "ok"})


@app.get("/api/saved")
def saved_articles():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, source, title, link, published_at, summary_raw, saved_at
            FROM articles
            WHERE saved_at IS NOT NULL AND hidden_at IS NULL
            ORDER BY saved_at DESC
            """
        ).fetchall()
    items = [dict(row) for row in rows]
    for item in items:
        item["is_saved"] = True
    return no_store({"mode": "saved", "generated_at": None, "items": items})


@app.post("/api/refresh")
def refresh_now():
    articles = fetch_all()
    inserted = store_articles(articles)
    return JSONResponse({"status": "ok", "seen": len(articles), "new": inserted})


@app.post("/api/mute")
def mute_keyword(payload: MuteRequest):
    keyword = payload.keyword.strip().lower()
    if not keyword:
        raise HTTPException(status_code=400, detail="keyword must not be empty")
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO muted_keywords (keyword, created_at) VALUES (?, datetime('now'))",
            (keyword,),
        )
    return JSONResponse({"status": "ok", "keyword": keyword})


@app.get("/api/muted")
def list_muted():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, keyword, created_at FROM muted_keywords ORDER BY created_at DESC"
        ).fetchall()
    return no_store([dict(row) for row in rows])


@app.delete("/api/muted/{muted_id}")
def unmute_keyword(muted_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM muted_keywords WHERE id = ?", (muted_id,))
    return JSONResponse({"status": "ok"})


@app.get("/api/latest")
def latest():
    with get_connection() as conn:
        muted = load_muted_keywords(conn)

        digest = conn.execute(
            "SELECT id, created_at FROM digests ORDER BY created_at DESC LIMIT 1"
        ).fetchone()

        if digest:
            rows = conn.execute(
                """
                SELECT di.category, di.summary, a.id, a.title, a.link, a.source, a.published_at
                FROM digest_items di
                JOIN articles a ON a.id = di.article_id
                WHERE di.digest_id = ? AND a.hidden_at IS NULL AND a.saved_at IS NULL
                ORDER BY di.rank
                """,
                (digest["id"],),
            ).fetchall()
            items = filter_muted([dict(row) for row in rows], muted, "summary")
            return no_store(
                {
                    "mode": "digest",
                    "generated_at": digest["created_at"],
                    "items": items,
                }
            )

        # Saved articles are deliberately excluded here — saving an article
        # is meant to move it off the main feed into the Saved list, not
        # bookmark it in place.
        rows = conn.execute(
            """
            SELECT id, source, title, link, published_at, summary_raw, fetched_at
            FROM articles
            WHERE hidden_at IS NULL AND saved_at IS NULL
            ORDER BY published_at DESC
            """
        ).fetchall()
        all_items = filter_muted([dict(row) for row in rows], muted, "summary_raw")

    source_order = [feed["name"] for feed in load_feeds()]
    items = round_robin(all_items, source_order, RAW_ITEM_LIMIT)
    generated_at = all_items[0]["fetched_at"] if all_items else None
    return no_store(
        {
            "mode": "raw",
            "generated_at": generated_at,
            "items": items,
        }
    )
