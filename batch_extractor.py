"""
Batch Extractor — processes up to 5 article URLs with streaming SSE responses.
"""

from flask import Blueprint
import sys
import os
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit("Missing dependency: pip install beautifulsoup4")

try:
    import requests
except ImportError:
    requests = None



try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from flask import Flask, request as flask_request, jsonify, render_template_string
except ImportError:
    sys.exit("Missing dependency: pip install flask")


logger = logging.getLogger("BatchExtractor")
logger.setLevel(logging.INFO)
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter(
        '[%(asctime)s] [%(levelname)s] %(message)s', '%H:%M:%S'))
    logger.addHandler(ch)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
    "Accept-Language": "en-US,en;q=0.9",
}

# ── Dynamic key discovery: finds GEMINI_API_KEY_1 … GEMINI_API_KEY_N ──────────


def _discover_api_keys() -> list[str]:
    """Scan env vars for GEMINI_API_KEY_<n> and return them sorted by n."""
    import re as _re
    found = {}
    for name, val in os.environ.items():
        m = _re.fullmatch(r'GEMINI_API_KEY_(\d+)', name)
        if m and val and val.strip():
            found[int(m.group(1))] = val.strip()
    keys = [found[k] for k in sorted(found)]
    logger.info(f"[*] Discovered {len(keys)} Gemini API key(s)")
    return keys


API_KEYS = _discover_api_keys()

TEMPLATE_APP_URL = os.getenv("TEMPLATE_APP_URL", "http://localhost:5000")

_key_index = 0
_key_lock = threading.Lock()

GEMINI_MODELS = [
    "gemini-3.1-flash-lite-preview",
    "gemini-2.5-flash-lite",
    "gemini-3-flash-preview",
    "gemini-2.5-flash",
]


def _next_key() -> str:
    global _key_index
    with _key_lock:
        key = API_KEYS[_key_index]
        _key_index = (_key_index + 1) % len(API_KEYS)
    return key


def _call_gemini(prompt: str) -> str | None:
    """Try all keys/models with thread-safe rotation. Returns text or None on exhaustion.
    Reduced retries for Render's constrained environment."""
    if not API_KEYS:
        return None
    for _ in range(len(API_KEYS)):
        api_key = _next_key()
        masked = f"{api_key[:6]}...{api_key[-4:]}" if len(
            api_key) > 10 else "***"
        for model in GEMINI_MODELS:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
                headers = {'Content-Type': 'application/json'}
                data = {"contents": [{"parts": [{"text": prompt}]}]}
                
                resp = requests.post(url, headers=headers, json=data, timeout=30)
                if resp.ok:
                    res_json = resp.json()
                    candidates = res_json.get("candidates", [])
                    if candidates and candidates[0].get("content", {}).get("parts"):
                        return candidates[0]["content"]["parts"][0]["text"].strip()
                elif resp.status_code == 429:
                    logger.warning(f"[!] Rate limited {model} key {masked}")
                else:
                    logger.error(f"[!] {model} failed: HTTP {resp.status_code}")
                    break
            except Exception as e:
                err = str(e)
                logger.error(f"[!] {model} failed: {err[:100]}")
                break
    return None


def fetch_html(source: str) -> str:
    path = Path(source)
    if path.is_file():
        return path.read_text(encoding="utf-8", errors="replace")
    if requests is None:
        sys.exit("Install requests to fetch URLs: pip install requests")
    resp = requests.get(source, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding
    return resp.text


def extract(source: str) -> dict:
    html = fetch_html(source)
    soup = BeautifulSoup(html, "html.parser")

    title_tag = soup.find(class_="maan-title-text")
    title = title_tag.get_text(strip=True) if title_tag else ""

    img_tag = soup.find(class_="maan-post-img")
    image_url = img_tag.find(
        "img")["src"] if img_tag and img_tag.find("img") else ""

    content_tags = soup.find_all(class_="maan-text")
    content_tag = (
        max(content_tags, key=lambda t: len(t.find_all("p")), default=None)
        if content_tags else None
    )
    if content_tag:
        ps = content_tag.find_all("p")
        leaf_ps = [p.get_text(strip=True) for p in ps if not p.find(
            "p") and p.get_text(strip=True)]
        if leaf_ps:
            content = leaf_ps[0]
        else:
            text_lines = [l.strip()
                          for l in content_tag.get_text().split("\n") if l.strip()]
            content = text_lines[0] if text_lines else ""
    else:
        content = ""

    return {"title": title, "image_url": image_url, "content": content}


def summarize_short(content: str) -> str:
    """Summarize to ≤25 words (prompt), hard-capped at 30 words."""
    prompt = (
        "Summarize the following text in 25 words or fewer. "
        "Be specific and preserve key facts. "
        "Reply with only the summary, nothing else.\n\n"
        f"Text: {content}"
    )
    result = _call_gemini(prompt)
    if not result:
        logger.warning(
            "[!] summarize_short exhausted all keys — returning original")
        return content
    words = result.split()
    return " ".join(words[:30]) if len(words) > 30 else result


def categorize(title: str, snippet: str) -> str:
    prompt = (
        "Analyze this news article and determine the single most accurate, distinctly topical category.\n"
        "IMPORTANT RULES:\n"
        "1. DO NOT use generic terms like 'Local News', 'Trending News', 'Latest News', or 'General News'.\n"
        "2. Choose a specific topic (e.g. 'Art & Culture', 'Civics', 'Law & Crime', 'Geopolitics', "
        "'Technology', 'Healthcare', 'Infrastructure').\n\n"
        f"Title: {title}\nSnippet: {snippet[:300]}\n\n"
        "Reply with only the exact category name (1-3 words maximum), nothing else."
    )
    result = _call_gemini(prompt)
    if not result:
        logger.warning("[!] categorize exhausted all keys")
        return "Uncategorized"
    return result


def process_url(url: str) -> dict:
    """Full pipeline for one URL. Always returns a dict (story or error)."""
    try:
        logger.info(f"[*] Processing: {url}")
        extracted = extract(url)
        title = extracted["title"]
        image_url = extracted.get("image_url") or ""
        raw_content = extracted["content"]

        word_count = len(raw_content.split()) if raw_content else 0
        if word_count > 25:
            logger.info(f"[*] {word_count} words -> summarizing")
            final_summary = summarize_short(raw_content) or raw_content
        else:
            logger.info(
                f"[*] {word_count} words -> already short, skipping summarize")
            final_summary = raw_content

        categorize_input = final_summary if final_summary else raw_content[:300]
        category = categorize(title, categorize_input)

        logger.info(f"[+] Done: {url}")
        return {
            "category": category.upper(),
            "headline": title,
            "summary": final_summary,
            "image": image_url,
            "link": url,
        }
    except Exception as e:
        logger.error(f"[X] Failed {url}: {e}")
        return {"link": url, "error": str(e)}


batch_extractor_bp = Blueprint('batch_extractor_bp', __name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Batch News Extractor</title>
    <link href="https://fonts.googleapis.com/css2?family=Space+Mono:ital,wght@0,400;0,700;1,400;1,700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #ffffff;
            --text: #000000;
            --muted: #555555;
            --border: #000000;
            --yellow: #ffff00;
            --green: #00c800;
            --red: #cc0000;
        }
        * { box-sizing: border-box; }
        body {
            font-family: 'Space Mono', 'Courier New', monospace;
            background: var(--bg);
            color: var(--text);
            margin: 0;
            padding: 2rem;
            display: flex;
            justify-content: center;
        }
        .container { max-width: 860px; width: 100%; }
        h1 {
            font-size: 2.2rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: -2px;
            border-bottom: 4px solid var(--border);
            padding-bottom: 1rem;
            margin-bottom: 2rem;
        }
        .url-row {
            display: flex;
            align-items: center;
            gap: 0.75rem;
            margin-bottom: 0.9rem;
        }
        .url-label {
            font-size: 0.85rem;
            font-weight: 700;
            text-transform: uppercase;
            min-width: 52px;
            letter-spacing: -0.5px;
        }
        input[type="text"] {
            flex: 1;
            padding: 0.75rem 1rem;
            border: 3px solid var(--border);
            background: var(--bg);
            color: var(--text);
            font-size: 0.9rem;
            outline: none;
            box-shadow: 3px 3px 0 var(--border);
            font-family: inherit;
            transition: all 0.1s;
        }
        input[type="text"]:focus {
            transform: translate(1px, 1px);
            box-shadow: 2px 2px 0 var(--border);
        }
        .status-dot {
            width: 28px;
            height: 28px;
            border: 2px solid var(--border);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.7rem;
            font-weight: 700;
            flex-shrink: 0;
            background: #f0f0f0;
            color: var(--muted);
            letter-spacing: 0;
        }
        .status-dot.processing { background: var(--yellow); color: var(--text); }
        .status-dot.success    { background: var(--green);  color: #fff; }
        .status-dot.failed     { background: var(--red);    color: #fff; }
        .actions {
            display: flex;
            gap: 1rem;
            margin: 1.5rem 0 2rem;
        }
        button {
            background: var(--text);
            color: #fff;
            border: 3px solid var(--border);
            padding: 0.85rem 2rem;
            font-size: 1rem;
            font-weight: 700;
            text-transform: uppercase;
            cursor: pointer;
            box-shadow: 4px 4px 0 var(--border);
            font-family: inherit;
            transition: all 0.1s;
            letter-spacing: -0.5px;
        }
        button:hover { background: #222; }
        button:active, button:disabled {
            transform: translate(4px, 4px);
            box-shadow: 0 0 0 var(--border);
        }
        button:disabled { opacity: 0.45; cursor: not-allowed; }
        #clear-btn {
            background: #fff;
            color: var(--text);
        }
        #clear-btn:hover { background: #f0f0f0; }
        .loader {
            display: none;
            padding: 1rem;
            border: 3px solid var(--border);
            background: var(--yellow);
            box-shadow: 4px 4px 0 var(--border);
            font-weight: 700;
            text-transform: uppercase;
            margin-bottom: 1.5rem;
            letter-spacing: -0.5px;
        }
        .output-section { display: none; }
        .output-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 2px dashed var(--border);
            padding-bottom: 0.5rem;
            margin-bottom: 1rem;
        }
        .output-title {
            font-weight: 700;
            text-transform: uppercase;
            font-size: 1rem;
            letter-spacing: -0.5px;
        }
        .copy-btn {
            background: #fff;
            color: var(--text);
            border: 2px solid var(--border);
            padding: 0.4rem 1rem;
            font-size: 0.8rem;
            box-shadow: 2px 2px 0 var(--border);
        }
        .copy-btn:hover { background: #f0f0f0; }
        .copy-btn.copied {
            background: var(--text);
            color: #fff;
            transform: translate(2px, 2px);
            box-shadow: 0 0 0 var(--border);
        }
        #json-output {
            border: 3px solid var(--border);
            padding: 1.25rem;
            box-shadow: 6px 6px 0 var(--border);
            white-space: pre-wrap;
            word-break: break-all;
            font-size: 0.82rem;
            line-height: 1.55;
            max-height: 560px;
            overflow-y: auto;
            margin: 0;
            background: #fafafa;
        }
    </style>
</head>
<body>
<div class="container">
    <h1>Batch Extractor</h1>

    <div id="url-inputs">
        <div class="url-row">
            <span class="url-label">URL 1</span>
            <input type="text" class="url-field" placeholder="https://...">
            <div class="status-dot" id="dot-0">—</div>
        </div>
        <div class="url-row">
            <span class="url-label">URL 2</span>
            <input type="text" class="url-field" placeholder="https://...">
            <div class="status-dot" id="dot-1">—</div>
        </div>
        <div class="url-row">
            <span class="url-label">URL 3</span>
            <input type="text" class="url-field" placeholder="https://...">
            <div class="status-dot" id="dot-2">—</div>
        </div>
        <div class="url-row">
            <span class="url-label">URL 4</span>
            <input type="text" class="url-field" placeholder="https://...">
            <div class="status-dot" id="dot-3">—</div>
        </div>
        <div class="url-row">
            <span class="url-label">URL 5</span>
            <input type="text" class="url-field" placeholder="https://...">
            <div class="status-dot" id="dot-4">—</div>
        </div>
    </div>

    <div class="actions">
        <button id="process-btn">Process All</button>
        <button id="clear-btn">Clear</button>
    </div>

    <div id="loader" class="loader">Processing in parallel — please wait...</div>

    <div id="output-section" class="output-section">
        <div class="output-header">
            <span class="output-title">Stories JSON</span>
            <div style="display:flex;gap:0.5rem;align-items:center;">
                <button class="copy-btn" id="copy-btn">Copy</button>
                <button class="copy-btn" id="send-btn">Send to Template</button>
            </div>
        </div>
        <div id="send-status" style="display:none;padding:0.5rem 0.75rem;margin-bottom:0.75rem;font-size:0.8rem;font-weight:700;border:2px solid var(--border);"></div>
        <pre id="json-output"></pre>
    </div>
</div>

<script>
    const processBtn = document.getElementById('process-btn');
    const clearBtn   = document.getElementById('clear-btn');
    const loader     = document.getElementById('loader');
    const outputSection = document.getElementById('output-section');
    const jsonOutput    = document.getElementById('json-output');
    const copyBtn       = document.getElementById('copy-btn');

    function getDots() {
        return [0,1,2,3,4].map(i => document.getElementById('dot-' + i));
    }

    function setDot(dot, state) {
        dot.className = 'status-dot ' + state;
        dot.textContent = state === 'processing' ? '...' : state === 'success' ? '✓' : state === 'failed' ? '✗' : '—';
    }

    function resetDots() {
        getDots().forEach(d => setDot(d, ''));
    }

    clearBtn.addEventListener('click', () => {
        document.querySelectorAll('.url-field').forEach(f => f.value = '');
        resetDots();
        outputSection.style.display = 'none';
        jsonOutput.textContent = '';
    });

    processBtn.addEventListener('click', async () => {
        const fields = document.querySelectorAll('.url-field');
        const urls = Array.from(fields).map(f => f.value.trim()).filter(Boolean);

        if (urls.length === 0) {
            alert('Please enter at least one URL.');
            return;
        }

        processBtn.disabled = true;
        loader.style.display = 'block';
        outputSection.style.display = 'none';

        const dots = getDots();
        Array.from(fields).forEach((f, i) => {
            if (f.value.trim()) setDot(dots[i], 'processing');
            else setDot(dots[i], '');
        });

        try {
            // Build SSE URL with query params
            const params = new URLSearchParams();
            urls.forEach(u => params.append('url', u));
            const sseUrl = '{{ url_for("batch_extractor_bp.api_batch_stream") }}?' + params.toString();

            const allStories = [];
            // Map url→input index for dot updates
            const urlToIdx = {};
            Array.from(fields).forEach((f, i) => {
                const u = f.value.trim();
                if (u) urlToIdx[u] = i;
            });

            await new Promise((resolve, reject) => {
                const es = new EventSource(sseUrl);

                es.addEventListener('result', (ev) => {
                    const story = JSON.parse(ev.data);
                    allStories.push(story);
                    const idx = urlToIdx[story.link];
                    if (idx !== undefined) {
                        setDot(dots[idx], story.error ? 'failed' : 'success');
                    }
                    // Live-update the JSON output
                    jsonOutput.textContent = JSON.stringify({ stories: allStories }, null, 2);
                    outputSection.style.display = 'block';
                });

                es.addEventListener('done', () => {
                    es.close();
                    resolve();
                });

                es.addEventListener('error_msg', (ev) => {
                    es.close();
                    reject(new Error(ev.data));
                });

                es.onerror = () => {
                    es.close();
                    if (allStories.length === 0) {
                        reject(new Error('Connection lost before any results'));
                    } else {
                        resolve(); // partial results OK
                    }
                };
            });

        } catch (err) {
            alert('Request failed: ' + err.message);
            getDots().forEach(d => { if (d.classList.contains('processing')) setDot(d, 'failed'); });
        } finally {
            processBtn.disabled = false;
            loader.style.display = 'none';
        }
    });

    copyBtn.addEventListener('click', async () => {
        try {
            await navigator.clipboard.writeText(jsonOutput.textContent);
            copyBtn.textContent = 'Copied!';
            copyBtn.classList.add('copied');
            setTimeout(() => { copyBtn.textContent = 'Copy'; copyBtn.classList.remove('copied'); }, 2000);
        } catch {
            alert('Copy failed — try HTTPS or allow clipboard access.');
        }
    });

    const sendBtn    = document.getElementById('send-btn');
    const sendStatus = document.getElementById('send-status');

    sendBtn.addEventListener('click', async () => {
        const payload = jsonOutput.textContent;
        if (!payload) return;

        sendBtn.disabled = true;
        sendStatus.style.display = 'block';
        sendStatus.style.background = '#ffff00';
        sendStatus.style.color = '#000';
        sendStatus.textContent = 'Sending to template app...';

        try {
            const resp = await fetch('{{ url_for("batch_extractor_bp.api_send") }}', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: payload,
                signal: AbortSignal.timeout(20000)
            });
            const text = await resp.text();
            let result;
            try {
                result = JSON.parse(text);
            } catch (err) {
                throw new Error(`Server Error (${resp.status}): ${text.substring(0, 60)}...`);
            }
            if (resp.ok && result.success) {
                sendStatus.style.background = '#00c800';
                sendStatus.style.color = '#fff';
                sendStatus.textContent = 'Sent successfully!';
            } else {
                sendStatus.style.background = '#cc0000';
                sendStatus.style.color = '#fff';
                sendStatus.textContent = 'Failed: ' + (result.error || 'Unknown error');
            }
        } catch (err) {
            sendStatus.style.background = '#cc0000';
            sendStatus.style.color = '#fff';
            sendStatus.textContent = 'Failed: ' + err.message;
        } finally {
            sendBtn.disabled = false;
        }
    });
</script>
</body>
</html>
"""


@batch_extractor_bp.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)


@batch_extractor_bp.route("/api/batch", methods=["POST"])
def api_batch():
    """Legacy JSON endpoint — kept for backward compat but may timeout on Render."""
    data = flask_request.json or {}
    urls = [u.strip() for u in data.get("urls", []) if u and u.strip()]
    if not urls:
        return jsonify({"error": "No URLs provided"}), 400

    logger.info(f"[*] Batch of {len(urls)} URLs received")
    stories = [None] * len(urls)

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_to_idx = {executor.submit(
            process_url, url): i for i, url in enumerate(urls)}
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                stories[idx] = future.result()
            except Exception as e:
                stories[idx] = {"link": urls[idx], "error": str(e)}

    logger.info(f"[+] Batch complete. {sum(1 for s in stories if 'error' not in s)} success, "
                f"{sum(1 for s in stories if 'error' in s)} failed.")
    return jsonify({"stories": stories})


@batch_extractor_bp.route("/api/batch-stream")
def api_batch_stream():
    """SSE streaming endpoint — streams each result as it completes.
    Sends keepalive comments every 5 s so Render never sees 30 s of silence."""
    from flask import Response, stream_with_context
    import queue

    urls = [u.strip()
            for u in flask_request.args.getlist("url") if u and u.strip()]
    if not urls:
        def error_stream():
            yield 'event: error_msg\ndata: No URLs provided\n\n'
        return Response(error_stream(), mimetype='text/event-stream')

    logger.info(f"[*] SSE Batch of {len(urls)} URLs received")

    def generate():
        yield ': keepalive\n\n'

        result_q = queue.Queue()

        def _worker(idx, url):
            try:
                story = process_url(url)
            except Exception as e:
                story = {"link": url, "error": str(e)}
            result_q.put((idx, story))

        # Launch each URL in its own thread
        for i, url in enumerate(urls):
            t = threading.Thread(target=_worker, args=(i, url), daemon=True)
            t.start()

        # Emit results strictly in input order (URL 1 → story 0, URL 2 → story 1, …)
        buffer = {}          # idx → story, for results that arrived early
        next_to_emit = 0     # the index we're waiting to send next
        total = len(urls)

        while next_to_emit < total:
            try:
                idx, story = result_q.get(timeout=5)
                buffer[idx] = story

                # Flush as many in-order results as possible
                while next_to_emit in buffer:
                    s = buffer.pop(next_to_emit)
                    yield f'event: result\ndata: {json.dumps(s)}\n\n'
                    next_to_emit += 1
            except queue.Empty:
                # No result yet — keepalive to prevent Render 30 s timeout
                yield ': keepalive\n\n'

        yield 'event: done\ndata: complete\n\n'

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
        }
    )


@batch_extractor_bp.route("/api/send", methods=["POST"])
def api_send():
    """Proxy: forward stories JSON to the template app's /api/import_json internally."""
    import datetime
    from social_utils import write_runtime_file

    payload = flask_request.json or {}
    endpoints = [
        "/day8-editor/api/import_json",
        "/day9-editor/api/import_json",
        "/day6temp-editor/api/import_json",
        "/template1-editor/api/import_json",
        "/day11-editor/api/import_json",
        "/day12-editor/api/import_json",
        "/day15-editor/api/import_json",
        "/day12-2-editor/api/import_json",
        "/day9-2-editor/api/import_json",
        "/day17-editor/api/import_json",
    ]

    results = []
    success_count = 0

    from flask import current_app
    client = current_app.test_client()

    for target in endpoints:
        logger.info(f"[*] Forwarding to {target} internally")
        try:
            resp = client.post(target, json=payload)
            if resp.status_code == 200:
                success_count += 1
                results.append({"endpoint": target, "ok": True})
            else:
                logger.error(f"[X] Forward failed to {target}: returned {resp.status_code}")
                results.append({"endpoint": target, "ok": False, "reason": f"HTTP {resp.status_code}"})
        except Exception as e:
            logger.error(f"[X] Forward failed to {target}: {e}")
            results.append({"endpoint": target, "ok": False, "reason": str(e)[:120]})

    failed_details = [r for r in results if not r['ok']]
    write_runtime_file('last_send_result.json', {
        'timestamp': datetime.datetime.utcnow().isoformat() + 'Z',
        'total': len(endpoints),
        'success_count': success_count,
        'results': results,
        'failed': failed_details,
    })
    logger.info(f"[+] Send result persisted: {success_count}/{len(endpoints)} success")

    if success_count > 0:
        return jsonify({
            "success": True,
            "message": f"Sent to {success_count} editors",
            "errors": [f"{f['endpoint']}: {f['reason']}" for f in failed_details],
        })
    else:
        return jsonify({
            "error": "Failed to send to any editors",
            "details": [f"{f['endpoint']}: {f['reason']}" for f in failed_details],
        }), 502


if __name__ == "__main__":
    from flask import Flask
    test_app = Flask(__name__)
    test_app.register_blueprint(batch_extractor_bp)
    test_app.run(debug=True, port=5002)
