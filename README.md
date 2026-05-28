<div align="center">

# 📰 Newsband Editorial Platform

**A private, all-in-one newsletter editing & content intelligence suite for journalists.**

![Python](https://img.shields.io/badge/Python-3.x-3776AB?style=flat&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-Web_Framework-000000?style=flat&logo=flask&logoColor=white)
![Gemini AI](https://img.shields.io/badge/Gemini_AI-Powered-4285F4?style=flat&logo=google&logoColor=white)
![Mailchimp](https://img.shields.io/badge/Mailchimp-Analytics-FFE01B?style=flat&logo=mailchimp&logoColor=black)
![Render](https://img.shields.io/badge/Deployed_on-Render-46E3B7?style=flat&logo=render&logoColor=white)

</div>

---

## ✨ What It Does

> Newsband is a private editorial toolkit — log in, pick your newsletter template, fill in articles, and export a print-ready HTML email. Alongside editing, it packs AI-powered article extraction, campaign analytics, and image management into one dashboard.

---

## 🗺️ App Map

```
Login
  └── Dashboard
        ├── 📝  Newsletter Editors  (10 templates)
        ├── 🔍  News Extractor       (single article)
        ├── 📦  Batch Extractor      (up to 5 at once)
        ├── 📊  Campaign Analytics   (Mailchimp stats)
        ├── 🖼️  Image Pusher         (GitHub upload)
        └── 💻  HTML Code Viewer     (inspect / export)
```

---

## 🧩 Features at a Glance

| Module | What you get |
|---|---|
| **Newsletter Editors** | 10 day-specific templates, live preview iframe, click-to-edit text, images, colors, links |
| **News Extractor** | Paste a URL → get title, image, 40-60 word AI summary, and Gemini-powered category tag |
| **Batch Extractor** | Process up to 5 URLs in parallel with real-time streaming results |
| **Campaign Analytics** | Connect Mailchimp and see opens, clicks, bounces, and unsubscribes per campaign |
| **Image Pusher** | Upload an image → automatically push it to the Newsband GitHub repo |
| **HTML Code Viewer** | Upload an `.html` file, view formatted source, copy to clipboard, or download as ZIP |

---

## 🖊️ Newsletter Templates

Each editor lets you modify content through a form on the left and see a **live preview** on the right — no HTML knowledge needed.

<details>
<summary><strong>View all 10 templates</strong></summary>

| Template | Special Features |
|---|---|
| Day 6 Template | Standard multi-article layout |
| Day 8 | Standard multi-article layout |
| Day 9 | Standard multi-article layout |
| Day 9 (2) | + Markets ticker |
| Day 11 | Standard multi-article layout |
| Day 12 | Standard multi-article layout |
| Day 12 (2) | + Markets ticker |
| Day 15 | Standard multi-article layout |
| Day 17 | + Weather widget + Markets ticker |
| Template 1 | Standard multi-article layout |

</details>

**Every editor includes:**
- ✏️ Editable text, headings, and paragraphs
- 🖼️ Image & background image URL fields
- 🎨 Color pickers for accents and text
- 🔗 Link/URL fields per article card
- 📐 Font size sliders
- ⬇️ Export the finished HTML

---

## ⚡ Quick Start

### 1 · Clone & install

```bash
git clone <repo-url>
cd "Project Pandora"
pip install -r requirements.txt
```

### 2 · Set environment variables

Copy `.env.example` to `.env` and fill in your keys:

```env
GEMINI_API_KEY_1=...   # up to 5 keys — rotated automatically
GEMINI_API_KEY_2=...
MAILCHIMP_API_KEY=...
GITHUB_TOKEN=...
```

### 3 · Run

```bash
python app.py
```

Then open `http://localhost:5000` and log in.

---

## 🔐 Authentication

The app is protected by a session-based login. All routes beyond `/` require a valid session — accessing them unauthenticated redirects to the login page.

---

## 🤖 AI Integration

The **News Extractor** and **Batch Extractor** use the **Google Gemini API** to:

- Summarize articles into **40-60 word** blurbs
- Assign a **category tag** (e.g. *Art & Culture*, *Technology*, *Healthcare*, *Finance* …)

Up to **5 Gemini API keys** are configured and rotated with automatic fallback if one is rate-limited.

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Web framework | Flask + Blueprints |
| HTML parsing & editing | BeautifulSoup 4 |
| AI summarization | Google Gemini (`google-genai`) |
| Async / streaming | Gevent + Server-Sent Events |
| Rate limiting | Flask-Limiter |
| Production server | Gunicorn |
| Hosting | Render |

---

## 📁 Project Structure

```
Project Pandora/
├── app.py                  # App factory — registers all blueprints
├── config.py               # App-wide constants and template config
├── helpers.py              # Auth decorator, HTML utils, form helpers
├── login.py                # Login / logout routes
├── dashboard.py            # Main dashboard
├── extractor.py            # Single-URL news extractor
├── batch_extractor.py      # Parallel batch extractor (SSE)
├── codeview.py             # HTML code viewer + ZIP download
├── upload_image.py         # GitHub image pusher
├── mailchimp.py            # Mailchimp campaign analytics
├── day8.py … day17.py      # Per-template editor blueprints
├── templates/              # Jinja2 HTML templates
├── *.html                  # Newsletter template source files
└── requirements.txt
```

---

<div align="center">
<sub>Built for the Newsband editorial team.</sub>
</div>
