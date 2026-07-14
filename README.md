# Personal News Aggregator

## Project structure

```
backend/
  app/
    __init__.py
    config.py                 # paths, .env loading
    db.py                     # SQLite schema + connection helper
    feeds.json                 # your RSS feed list (edit this)
    fetch.py                   # fetch + normalize + dedupe + store articles
    interests.py                # interest categories used by the summarization prompt
    summarize.py                # Claude API summarization step (needs ANTHROPIC_API_KEY — not enabled yet)
    main.py                     # FastAPI app: frontend, /api/latest, save/hide/mute/refresh endpoints
  data/
    news.db                    # SQLite database (created on first run, gitignored)
    fetch.log                   # log of scheduled fetch runs
  requirements.txt
  .env.example                  # copy to .env and add ANTHROPIC_API_KEY (only needed for summarization)
  run_fetch.py                   # CLI: run the fetch step once
  run_summarize.py                # CLI: run the summarization step once (needs API key)
  run_fetch_scheduled.ps1          # wrapper the Windows scheduled task calls
  preview_articles.py               # throwaway script: dumps raw articles to a static HTML preview
frontend/
  index.html                        # mobile-first single-page UI
  preview.html                       # output of preview_articles.py (raw article dump)
  static/
    manifest.json                     # PWA manifest for "Add to Home Screen"
    icons/                             # app icons (180/192/512px)
```

## Setup

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Summarization is optional and currently **not enabled** — the frontend shows raw
fetched articles until you add an `ANTHROPIC_API_KEY`. To enable it later:
`copy .env.example .env`, add your key, then see "Summarization step" below.

## Running the fetch step

Edit `backend/app/feeds.json` to change your RSS feed list. Then:

```powershell
cd backend
.venv\Scripts\activate
python run_fetch.py
```

Fetches every feed, normalizes entries, dedupes against `data/news.db` by GUID,
and inserts new articles. Safe to re-run — already-seen articles are skipped.
You can also trigger this from the web app itself via the **Refresh** button
(calls `POST /api/refresh`), no terminal needed.

## Running the web app

```powershell
cd backend
.venv\Scripts\activate
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Then open **http://127.0.0.1:8000** in a browser. It shows up to 144 recent
fetched articles (18 per feed, round-robin interleaved so no single busy feed
dominates), or, once summarization is enabled, the latest curated digest.
To view from your iPhone, both devices need to be on the same network and
you'd use your PC's local IP instead of `127.0.0.1` — ask if you want help
setting that up, or with a proper deployment.

### Frontend features

- **Feed filter** — dropdown + Apply to show only one feed, or "View Saved"
- **Search** — live text filter over whatever's currently displayed
- **Hide** — soft-removes an article permanently (`articles.hidden_at`)
- **Don't care** — mutes a keyword (whole-word match); any current or future
  article containing it is filtered out. Manage the list via **Manage Filters**
- **Save** — bookmarks an article into the "View Saved" list
  (`articles.saved_at`); independent of Hide/mute filtering
- **Read dimming** — clicking a headline dims that card going forward
  (stored in the browser's `localStorage`, so it's per-device, not synced)
- **Add to Home Screen** (iOS) — Safari → Share → Add to Home Screen gives it
  a proper icon and launches full-screen without browser chrome

## Twice-daily automation

A Windows Scheduled Task named **`NewsAggregatorFetch`** runs the fetch step
automatically at **7:00 AM and 6:00 PM daily**. It calls
`backend/run_fetch_scheduled.ps1`, which runs `run_fetch.py` and appends output
to `backend/data/fetch.log`.

Manage it from PowerShell:

```powershell
Get-ScheduledTaskInfo -TaskName "NewsAggregatorFetch"   # last run time/result, next run time
Start-ScheduledTask -TaskName "NewsAggregatorFetch"      # run it right now
Unregister-ScheduledTask -TaskName "NewsAggregatorFetch" -Confirm:$false   # remove it
```

Or find it in the Windows **Task Scheduler** app under the root `\` folder to
change the times. It only runs while you're logged into Windows (no stored
password) — it won't fire while the PC is off or locked out at the login screen.

## Summarization step (optional, needs an API key)

Sends unsummarized articles to Claude (`claude-sonnet-5`) with a prompt
describing your interests (edit `backend/app/interests.py` to change them),
and stores the selected/summarized results as a "digest" in `data/news.db`.
Once a digest exists, the frontend automatically shows it instead of raw
articles — no code changes needed.

```powershell
cd backend
.venv\Scripts\activate
python run_summarize.py
```

Requires `ANTHROPIC_API_KEY` in `backend/.env` (get one at console.anthropic.com;
pay-as-you-go, no free tier — estimated cost for this project is a few dollars
a month). To fold it into the twice-daily automation later, add a call to
`run_summarize.py` in `run_fetch_scheduled.ps1` after the fetch step.

## Status

- [x] Fetch step (RSS parsing, dedup, storage)
- [x] FastAPI backend + mobile-first frontend
- [x] Twice-daily scheduled fetch
- [x] Feed filter, search, Hide, Don't-care mute list, Save/View Saved, read dimming, manual refresh, Add to Home Screen
- [ ] Claude summarization step — built, but disabled until an API key is added
