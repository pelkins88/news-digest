import logging
import os
from datetime import datetime, timezone
from typing import Optional

from anthropic import Anthropic

from . import config  # noqa: F401  (import triggers .env loading)
from .db import get_connection, init_db
from .interests import INTERESTS

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-5"
MAX_EXCERPT_CHARS = 600

DIGEST_TOOL = {
    "name": "build_digest",
    "description": "Select the most relevant and important articles from the batch and provide a short summary and category for each.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "article_id": {
                            "type": "integer",
                            "description": "The id of the source article",
                        },
                        "category": {
                            "type": "string",
                            "enum": [
                                "U.S. News",
                                "World News",
                                "Politics",
                                "Technology",
                                "Sports",
                                "Science",
                                "General Interest",
                            ],
                        },
                        "summary": {
                            "type": "string",
                            "description": "2-3 sentence summary of the article",
                        },
                    },
                    "required": ["article_id", "category", "summary"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["items"],
        "additionalProperties": False,
    },
}

SYSTEM_PROMPT = f"""You are a personal news curator. You will be given a batch of raw articles \
pulled from RSS feeds, each with an id, source, title, and short excerpt. Your job is to select \
only the articles that are genuinely relevant and important given the reader's interests, then \
write a short, informative summary for each selected article.

Reader's interests:
{INTERESTS}

Guidelines:
- Be selective. Do not include every article, only the ones that matter. A batch of 100+ raw \
articles should typically yield somewhere between 10 and 25 selected items, fewer if there isn't \
much genuinely important news.
- For sports, only include major developments (a trade, an injury to a star player, a championship \
result, a significant record) — never routine game recaps or score updates.
- Skip weather unless it describes a major, newsworthy event (a named storm, a significant \
disaster) rather than a routine local forecast.
- Skip duplicate or near-duplicate coverage of the same story from multiple sources — pick the best \
version.
- Write each summary as 2-3 plain sentences a busy reader can scan in a few seconds. Do not \
editorialize or add commentary beyond what the source reports.
- Assign exactly one category per item from the allowed list.
- Order items by importance, most important first.

Call the build_digest tool with your selections."""


def load_unprocessed_articles() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, source, title, link, published_at, summary_raw
            FROM articles
            WHERE processed_at IS NULL
            ORDER BY published_at DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def build_user_prompt(articles: list[dict]) -> str:
    lines = ["Articles:"]
    for a in articles:
        excerpt = (a["summary_raw"] or "")[:MAX_EXCERPT_CHARS]
        lines.append(
            f'- id={a["id"]} | source="{a["source"]}" | title="{a["title"]}" | excerpt="{excerpt}"'
        )
    return "\n".join(lines)


def call_claude(articles: list[dict]) -> list[dict]:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Copy backend/.env.example to backend/.env "
            "and add your key."
        )

    client = Anthropic()
    with client.messages.stream(
        model=MODEL,
        max_tokens=12000,
        thinking={"type": "adaptive"},
        output_config={"effort": "medium"},
        system=SYSTEM_PROMPT,
        tools=[DIGEST_TOOL],
        tool_choice={"type": "tool", "name": "build_digest"},
        messages=[{"role": "user", "content": build_user_prompt(articles)}],
    ) as stream:
        response = stream.get_final_message()

    for block in response.content:
        if block.type == "tool_use" and block.name == "build_digest":
            return block.input["items"]
    raise RuntimeError(f"Claude did not call build_digest (stop_reason={response.stop_reason})")


def store_digest(items: list[dict]) -> int:
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO digests (created_at, model, article_count) VALUES (?, ?, ?)",
            (now, MODEL, len(items)),
        )
        digest_id = cur.lastrowid
        for rank, item in enumerate(items):
            conn.execute(
                """
                INSERT INTO digest_items (digest_id, article_id, category, summary, rank)
                VALUES (?, ?, ?, ?, ?)
                """,
                (digest_id, item["article_id"], item["category"], item["summary"], rank),
            )
    return digest_id


def mark_considered_processed(articles: list[dict]) -> None:
    ids = [a["id"] for a in articles]
    if not ids:
        return
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        placeholders = ",".join("?" * len(ids))
        conn.execute(
            f"UPDATE articles SET processed_at = ? WHERE id IN ({placeholders})",
            (now, *ids),
        )


def run_summarize() -> Optional[int]:
    init_db()
    articles = load_unprocessed_articles()
    if not articles:
        logger.info("No unprocessed articles to summarize.")
        print("No new articles to summarize.")
        return None

    logger.info("Summarizing %d unprocessed articles", len(articles))
    items = call_claude(articles)
    digest_id = store_digest(items)
    mark_considered_processed(articles)

    logger.info("Digest #%d created with %d items", digest_id, len(items))
    print(f"Created digest #{digest_id} with {len(items)} items from {len(articles)} considered articles.")
    return digest_id
