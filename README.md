# Personal News Aggregator

**Live at: https://pelkins88.github.io/news-digest/** — free GitHub Pages
hosting, updates automatically twice a day (~7am / ~4pm ET) via GitHub
Actions. No server to run, nothing needs to stay on.

## Project structure

```
.github/workflows/
  update.yml                    # scheduled job: fetch + commit docs/data/latest.json
docs/                            # GitHub Pages root — this is what's actually deployed
  index.html                      # mobile-first single-page UI (static; all state in localStorage)
  static/
    manifest.json                  # PWA manifest for "Add to Home Screen"
    icons/                          # app icons (180/192/512px)
  data/
    latest.json                     # generated snapshot of articles, committed by the Action
backend/
  app/
    config.py                     # paths, .env loading
    fetch.py                       # fetch + normalize + dedupe RSS feeds
    build_static.py                 # generates docs/data/latest.json (used by the GitHub Action)
    feeds.json                       # your RSS feed list (edit this)
    interests.py                      # interest categories used by the summarization prompt
    summarize.py                       # Claude API summarization step (needs ANTHROPIC_API_KEY — not enabled yet)
    db.py, main.py                      # optional live-server mode (see "Local network mode" below) — not used by the live site
  requirements-static.txt            # minimal deps for the GitHub Action (feedparser, python-dotenv)
  requirements.txt                    # full deps, only needed for local-server mode
  run_build_static.py                  # CLI: regenerate docs/data/latest.json locally
```

## How it works

Twice a day, a GitHub Actions workflow (`.github/workflows/update.yml`) runs
`backend/run_build_static.py`, which fetches all your RSS feeds fresh, picks
up to 144 articles round-robin (so no single busy feed dominates), and
commits the result to `docs/data/latest.json`. GitHub Pages serves
`docs/index.html`, which reads that JSON file directly — **there's no live
backend in production**.

Everything interactive — Hide, Don't Care (mute keywords), Save, and
read-tracking — lives in your **iPhone's browser storage** (`localStorage`),
not a server. That means:
- It works instantly, with zero network calls for those actions
- It's **per-device** — actions on your iPhone won't show up if you ever open
  the site on another device/browser
- Clearing Safari's site data on your phone would reset it

## Editing your feed list or interests

Edit `backend/app/feeds.json` (feeds) or `backend/app/interests.py`
(summarization prompt topics), commit, and push — the next scheduled run (or
a manual one, see below) will pick up the change.

```powershell
git add backend/app/feeds.json
git commit -m "Update feed list"
git push
```

## Manually triggering an update

GitHub → your repo → **Actions** tab → **"Update news data"** → **Run workflow**.
Useful for testing changes without waiting for the next scheduled run.

## Frontend features

- **Feed filter** — dropdown + Apply to show only one feed, or "View Saved"
- **Search** — live text filter over whatever's currently displayed
- **Hide** — removes an article from view (persists in this browser only)
- **Don't care** — mutes a keyword (whole-word match); any current or future
  article containing it is filtered out. Manage the list via **Manage Filters**
- **Save** — moves an article to the "View Saved" list, off the main feed
- **Read dimming** — clicking a headline dims that card going forward
- **Refresh button** — re-checks `data/latest.json` for anything newer than
  what's currently loaded (doesn't trigger a new fetch — that's the scheduled
  job's job)
- **Add to Home Screen** (iOS Safari only — Chrome on iOS can't do full-screen
  PWAs) — Share → Add to Home Screen gives it a proper icon and launches
  full-screen without browser chrome

## Summarization step (optional, needs an API key)

Not yet wired into the GitHub Actions workflow. Once you add an
`ANTHROPIC_API_KEY`, ask to have it folded into `build_static.py` so the
scheduled job sends the batch to Claude and the site shows a curated digest
instead of raw articles.

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env    # add your ANTHROPIC_API_KEY
python run_summarize.py
```

Get a key at console.anthropic.com — pay-as-you-go, no free tier, estimated
cost for this project is a few dollars a month.

## Local network mode (optional, not used by the live site)

Earlier in development this ran as a live FastAPI server + SQLite database on
your PC, reachable over your home WiFi. That code is still here
(`backend/app/main.py`, `db.py`) in case you ever want it again — hide/mute/save
synced across devices in that mode, and there was a live Refresh button. It's
no longer configured to run automatically (no scheduled tasks, no forced
always-on power setting) since GitHub Pages replaced it as the primary way to
use this. To bring it back temporarily:

```powershell
cd backend
.venv\Scripts\activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Status

- [x] Fetch step (RSS parsing, dedup)
- [x] Static site on GitHub Pages, twice-daily auto-update via GitHub Actions
- [x] Feed filter, search, Hide, Don't-care mute list, Save/View Saved, read dimming, Add to Home Screen
- [x] Local network mode (FastAPI + SQLite) — built, functional, currently unused
- [ ] Claude summarization step — built, but disabled until an API key is added and wired into the static build
