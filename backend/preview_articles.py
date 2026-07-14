import html
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.config import DB_PATH  # noqa: E402
from app.db import get_connection  # noqa: E402

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "frontend" / "preview.html"

CARD_TEMPLATE = """
    <article class="card">
      <div class="meta">
        <span class="source">{source}</span>
        <span class="dot">&middot;</span>
        <span class="date">{published}</span>
      </div>
      <h2><a href="{link}" target="_blank" rel="noopener">{title}</a></h2>
      <p class="snippet">{snippet}</p>
    </article>
"""

PAGE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fetch Preview</title>
<style>
  :root {{
    color-scheme: light dark;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    background: #f5f5f7;
    color: #1c1c1e;
    -webkit-font-smoothing: antialiased;
  }}
  header {{
    padding: 20px 16px 12px;
    max-width: 640px;
    margin: 0 auto;
  }}
  header h1 {{
    font-size: 1.4rem;
    margin: 0 0 4px;
  }}
  header p {{
    margin: 0;
    color: #6e6e73;
    font-size: 0.9rem;
  }}
  main {{
    max-width: 640px;
    margin: 0 auto;
    padding: 8px 16px 40px;
  }}
  .card {{
    background: #fff;
    border-radius: 12px;
    padding: 14px 16px;
    margin-bottom: 12px;
    box-shadow: 0 1px 2px rgba(0,0,0,0.06);
  }}
  .meta {{
    font-size: 0.78rem;
    color: #6e6e73;
    margin-bottom: 6px;
  }}
  .source {{
    font-weight: 600;
    color: #444;
  }}
  .dot {{
    margin: 0 4px;
  }}
  .card h2 {{
    font-size: 1.02rem;
    line-height: 1.35;
    margin: 0 0 6px;
  }}
  .card h2 a {{
    color: #1c1c1e;
    text-decoration: none;
  }}
  .card h2 a:hover {{
    text-decoration: underline;
  }}
  .snippet {{
    font-size: 0.88rem;
    line-height: 1.4;
    color: #48484a;
    margin: 0;
  }}
  @media (prefers-color-scheme: dark) {{
    body {{ background: #000; color: #f2f2f7; }}
    .card {{ background: #1c1c1e; box-shadow: none; }}
    .card h2 a {{ color: #f2f2f7; }}
    .snippet {{ color: #c7c7cc; }}
  }}
</style>
</head>
<body>
<header>
  <h1>Fetch Preview</h1>
  <p>{count} raw articles from starter feeds &mdash; unsummarized, sorted by published date</p>
</header>
<main>
{cards}
</main>
</body>
</html>
"""


def build_preview() -> None:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT source, title, link, published_at, summary_raw
            FROM articles
            ORDER BY published_at DESC
            """
        ).fetchall()

    cards = []
    for row in rows:
        snippet = row["summary_raw"] or ""
        if len(snippet) > 220:
            snippet = snippet[:220].rsplit(" ", 1)[0] + "..."
        cards.append(
            CARD_TEMPLATE.format(
                source=html.escape(row["source"]),
                published=html.escape((row["published_at"] or "")[:10]),
                link=html.escape(row["link"]),
                title=html.escape(row["title"]),
                snippet=html.escape(snippet),
            )
        )

    page = PAGE_TEMPLATE.format(count=len(rows), cards="".join(cards))
    OUTPUT_PATH.write_text(page, encoding="utf-8")
    print(f"Wrote {len(rows)} articles to {OUTPUT_PATH}")


if __name__ == "__main__":
    build_preview()
