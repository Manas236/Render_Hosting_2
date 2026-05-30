# Project Pandora — Context Reference

## Platform

**Newsband Editorial Intelligence Platform** — a private Flask web app for the Newsband
journalism team.  Hosted on Render.  Auth is session-based (single username/password in
`config.py`).

---

## Architecture

| Layer | Detail |
|---|---|
| Framework | Flask + Blueprints |
| HTML editing | BeautifulSoup 4 |
| AI | Google Gemini (`google-genai`) |
| Email analytics | Mailchimp API |
| Async/streaming | Gevent + SSE |
| Production server | Gunicorn (`wsgi.py`) |
| Hosting | Render |

All blueprints are registered in `app.py` via `create_app()`.

---

## Module Map

| File | Blueprint / Purpose |
|---|---|
| `app.py` | App factory — registers all blueprints |
| `config.py` | Auth credentials, paths, HTML constants |
| `helpers.py` | Auth decorator, HTML processing, form rendering |
| `login.py` | `login_bp` — `/` login + logout |
| `dashboard.py` | `dashboard_bp` — `/dashboard` main menu |
| `extractor.py` | `extractor_bp` — single-URL news extractor |
| `batch_extractor.py` | `batch_extractor_bp` — parallel article processing (SSE) |
| `codeview.py` | `codeview_bp` — HTML viewer + ZIP download |
| `upload_image.py` | `upload_image_bp` — push images to GitHub |
| `mailchimp_bp.py` | `mailchimp_bp` — Mailchimp campaign analytics |
| `social_pipeline_bp.py` | `social_pipeline_bp` — Social Pipeline dashboard + API |
| `social_utils.py` | Shared utilities for social pipeline state management |
| `editor_*.py` / `app11.py` | Per-template newsletter editors (Day 6–17, Template 1) |

---

## Social Pipeline

### Overview

The Social Pipeline is a runtime orchestration system for managing social media post
scheduling and publishing.  Its dashboard lives at `/social-pipeline` and provides:

- Live status view of all runtime state (auto-polls every 15 seconds)
- **Refresh** button — re-fetches `/api/social/status` without page reload
- **Reset Pipeline** button — calls `POST /api/social/reset` with confirmation modal

### State File Layout

All social pipeline data lives under `social_data/` (project root):

```
social_data/
├── runtime/          ← ALL files here are cleared on reset
│   ├── run_state.json          stage, in_progress, waiting_for_approval, current_post
│   ├── current_session.json    active session identity (id, started_at)
│   ├── scheduler_state.json    running, paused, next_run, stop_requested
│   ├── lock.json               orchestration mutex (owner, acquired_at)
│   ├── heartbeat.json          alive, last_beat
│   ├── queue_processing.json   processing, queue_size
│   ├── failed_run_marker.json  reason, failed_at
│   └── *.lock                  any stray lock files
└── persistent/       ← NEVER touched by reset
    ├── approved_posts/
    ├── captions/
    ├── generated_images/
    ├── payload_archive/
    ├── archive/
    ├── posted_history.json
    └── duplicate_protection.json
```

### Key Functions (`social_utils.py`)

| Function | Purpose |
|---|---|
| `reset_social_runtime_state()` | **Single source of truth** for clearing runtime state. Deletes all files in `runtime/`. Returns `{cleared, timestamp}`. |
| `get_pipeline_status()` | Reads all runtime files and returns a unified status dict. |
| `stop_scheduler()` | Writes `stop_requested=True` into `scheduler_state.json`. Returns `True` if scheduler was running. |
| `read_runtime_file(filename)` | Safe JSON read from `runtime/`; returns `None` if missing or corrupt. |
| `write_runtime_file(filename, data)` | Safe JSON write to `runtime/`. |

### API Endpoints (`social_pipeline_bp.py`)

| Method | Route | Auth | Description |
|---|---|---|---|
| `GET` | `/social-pipeline` | required | Dashboard UI |
| `GET` | `/api/social/status` | required | Returns current pipeline status JSON |
| `POST` | `/api/social/reset` | required | Stops scheduler if running, then clears all runtime state |

#### Reset response shape
```json
{
  "success": true,
  "message": "Pipeline state reset successfully",
  "scheduler_stopped": false,
  "cleared": ["run_state.json", "failed_run_marker.json"],
  "timestamp": "2026-05-28T10:00:00Z"
}
```

### Reset Behaviour

1. If scheduler is running (`scheduler_state.json#running == true`):
   - Write `stop_requested = true` into `scheduler_state.json`
   - Log `[social-reset] stopped scheduler before reset`
2. Call `reset_social_runtime_state()`:
   - Delete every file listed in `RUNTIME_FILES`
   - Delete any `*.lock` files in `runtime/`
   - Log `[social-reset] cleared runtime state: <filename>` for each file
   - Log `[social-reset] reset complete — cleared: [...]`
3. Return success JSON to UI
4. UI shows green banner: **"Pipeline state reset successfully"**

### Reset Button UI Rules

- Normal state: red-outline **Reset Pipeline** button
- When `in_progress == true`: amber-outline **Force Reset** button
- Clicking either opens a confirmation modal
- Modal shows an extra amber warning box when `in_progress == true`
- Button is never permanently disabled — force-reset is always available

---

## Environment Variables

```env
GEMINI_API_KEY_1=...   # up to 5 keys, rotated automatically
GEMINI_API_KEY_2=...
MAILCHIMP_API_KEY=...
GITHUB_TOKEN=...
```

---

## Deployment Notes

- Render filesystem is ephemeral on restart — `social_data/runtime/` files are naturally
  transient (correct behaviour).  `social_data/persistent/` would need a mounted disk or
  external storage for production durability.
- The app is registered as `app:app` for Gunicorn (`wsgi.py` imports from `app.py`).
