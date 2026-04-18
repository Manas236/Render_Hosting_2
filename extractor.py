"""
HTML Extractor — pulls title, image, and content from maan-themed pages.
"""

import sys
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
    from google import genai
    from google.genai import types
except ImportError:
    sys.exit("Missing dependency: pip install google-genai")

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from flask import Flask, request, jsonify, render_template_string, Blueprint
except ImportError:
    sys.exit("Missing dependency: pip install flask")


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
    "Accept-Language": "en-US,en;q=0.9",
}


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

    # Title
    title_tag = soup.find(class_="maan-title-text")
    title = title_tag.get_text(strip=True) if title_tag else ""

    # Image URL
    img_tag = soup.find(class_="maan-post-img")
    image_url = img_tag.find("img")["src"] if img_tag and img_tag.find("img") else ""

    # Content — direct child <p> tags inside maan-text (recursive=False avoids blob duplicates)
    content_tags = soup.find_all(class_="maan-text")
    content_tag = max(content_tags, key=lambda t: len(t.find_all("p")), default=None) if content_tags else None
    if content_tag:
        # Find all p tags.
        ps = content_tag.find_all("p")
        # Filter for those that actually contain text and don't have other p tags inside them
        leaf_ps = [p.get_text(strip=True) for p in ps if not p.find("p") and p.get_text(strip=True)]
        
        if leaf_ps:
            # Strictly return ONLY the first paragraph
            content = leaf_ps[0]
        else:
            # Fallback: if no p tags, maybe just the first line of text
            text_lines = [l.strip() for l in content_tag.get_text().split('\n') if l.strip()]
            content = text_lines[0] if text_lines else ""
    else:
        content = ""

    return {"title": title, "image_url": image_url, "content": content}


import os
import logging

logger = logging.getLogger("Extractor")
logger.setLevel(logging.INFO)
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', '%H:%M:%S'))
    logger.addHandler(ch)

API_KEYS = [
    os.getenv("GEMINI_API_KEY_1"),
    os.getenv("GEMINI_API_KEY_2"),
    os.getenv("GEMINI_API_KEY_3"),
    os.getenv("GEMINI_API_KEY_4"),
    os.getenv("GEMINI_API_KEY_5"),
]
API_KEYS = [k.strip() for k in API_KEYS if k and k.strip()]
current_key_index = 0

GEMINI_MODELS = [
    "gemini-3.1-flash-lite-preview",
    "gemini-2.5-flash-lite",
    "gemini-3-flash-preview",
    "gemini-2.5-flash"
]

def summarize(content: str) -> str:
    """Ask Gemini to summarize content to 20 words or less. Only called when content exceeds 25 words."""
    global current_key_index
    if not API_KEYS:
        logger.error("No GEMINI_API_KEYs found in .env")
        return content

    prompt = (
        f"Summarize the following text in 2-3 concise sentences (around 40-60 words). "
        f"Preserve the key details, people, and context — do not reduce it to a headline. "
        f"Reply with only the summary, nothing else.\n\n"
        f"Text: {content}"
    )

    for _ in range(len(API_KEYS)):
        api_key = API_KEYS[current_key_index]
        masked = f"{api_key[:6]}...{api_key[-4:]}" if len(api_key) > 10 else "***"
        logger.info(f"--- Summarize Key Index {current_key_index} ({masked}) ---")
        client = genai.Client(api_key=api_key)

        for model in GEMINI_MODELS:
            try:
                logger.info(f"[*] Summarizing with model: {model}")
                response = client.models.generate_content(model=model, contents=prompt)
                if not response or not response.text:
                    logger.warning(f"[!] Empty response from {model}")
                    continue
                summary = response.text.strip()
                logger.info(f"[+] Summary: {summary}")
                return summary
            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "exhausted" in error_str.lower() or "Quota" in error_str:
                    logger.warning(f"[!] Rate Limited (429) on {model}: {error_str[:150]}")
                else:
                    logger.error(f"[!] Model {model} failed: {error_str[:150]}")

        logger.warning(f"[!] All models failed for key index {current_key_index}. Cycling to next key...")
        current_key_index = (current_key_index + 1) % len(API_KEYS)

    logger.critical("Exhausted all API keys and models for summarization!")
    return content


def categorize(title: str, snippet: str) -> str:
    """Ask Google Gemini API to categorize the article with cyclic key fallback."""
    global current_key_index
    if not API_KEYS:
        logger.error("No GEMINI_API_KEYs found in .env")
        return "(categorization failed: No GEMINI_API_KEYs found in .env)"

    prompt = (
        f"Analyze this news article and determine the single most accurate, distinctly topical category.\n"
        f"IMPORTANT RULES:\n"
        f"1. DO NOT use generic or non-topical terms like 'Local News', 'Trending News', 'Latest News', or 'General News'.\n"
        f"2. Choose a specific, definitive topic (e.g., 'Art & Culture', 'Civics', 'Law & Crime', 'Geopolitics', 'Technology', 'Healthcare', 'Infrastructure').\n\n"
        f"Title: {title}\n"
        f"Snippet: {snippet[:300]}\n\n"
        f"Reply with only the exact category name (1-3 words maximum), nothing else."
    )

    for _ in range(len(API_KEYS)):
        api_key = API_KEYS[current_key_index]
        masked = f"{api_key[:6]}...{api_key[-4:]}" if len(api_key) > 10 else "***"
        logger.info(f"--- Key Index {current_key_index} ({masked}) ---")
        client = genai.Client(api_key=api_key)
        
        for model in GEMINI_MODELS:
            try:
                logger.info(f"[*] Trying model: {model}")
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                )
                if not response or not response.text:
                    logger.warning(f"[!] Empty response from {model}")
                    continue
                    
                cat_result = response.text.strip()
                logger.info(f"[+] Categorization success: {cat_result}")
                return cat_result
            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "exhausted" in error_str.lower() or "Quota" in error_str:
                    logger.warning(f"[!] Rate Limited (429) on {model}: {error_str[:150]}")
                else:
                    logger.error(f"[!] Model {model} failed: {error_str[:150]}")
                pass
                
        # If we reach here, all models failed for this key. Cycle to the next key.
        logger.warning(f"[!] All models failed for key index {current_key_index}. Cycling to next key...")
        current_key_index = (current_key_index + 1) % len(API_KEYS)
        
    logger.critical("Exhausted all API keys and models!")
    return "(categorization failed: exhausted all keys and models)"


# ══════════════════════════════════════════════════════════════════════════════
#  CONFIGURE HERE — just change source and run: python app.py
# ══════════════════════════════════════════════════════════════════════════════

source = ""               # ← paste URL or local file path here
output = ""               # ← save to file e.g. "result.txt" (leave "" to print to terminal)

# ══════════════════════════════════════════════════════════════════════════════

extractor_bp = Blueprint('extractor_bp', __name__, url_prefix='/extractor')

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>News Extractor</title>
    <link href="https://fonts.googleapis.com/css2?family=Space+Mono:ital,wght@0,400;0,700;1,400;1,700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #ffffff;
            --surface-color: #ffffff;
            --primary-color: #000000;
            --primary-hover: #222222;
            --text-main: #000000;
            --text-muted: #444444;
            --border-color: #000000;
            --success-color: #000000;
        }
        body {
            font-family: 'Space Mono', 'Courier New', monospace;
            background-color: var(--bg-color);
            color: var(--text-main);
            margin: 0;
            padding: 2rem;
            display: flex;
            justify-content: center;
        }
        .container {
            max-width: 800px;
            width: 100%;
        }
        h1 {
            text-align: left;
            font-weight: 700;
            margin-bottom: 2rem;
            font-size: 2.5rem;
            text-transform: uppercase;
            letter-spacing: -2px;
            border-bottom: 4px solid var(--border-color);
            padding-bottom: 1rem;
            color: var(--text-main);
        }
        .input-group {
            display: flex;
            gap: 1rem;
            margin-bottom: 3rem;
        }
        input[type="text"] {
            flex: 1;
            padding: 1rem;
            border-radius: 0;
            border: 3px solid var(--border-color);
            background: var(--surface-color);
            color: var(--text-main);
            font-size: 1rem;
            outline: none;
            box-shadow: 4px 4px 0px var(--border-color);
            transition: all 0.1s ease;
            font-family: 'Space Mono', 'Courier New', monospace;
        }
        input[type="text"]:focus {
            transform: translate(2px, 2px);
            box-shadow: 2px 2px 0px var(--border-color);
        }
        button {
            background: var(--primary-color);
            color: white;
            border: 3px solid var(--border-color);
            padding: 1rem 2rem;
            border-radius: 0;
            font-size: 1rem;
            font-weight: 700;
            text-transform: uppercase;
            cursor: pointer;
            box-shadow: 4px 4px 0px var(--border-color);
            transition: all 0.1s ease;
            font-family: 'Space Mono', 'Courier New', monospace;
        }
        button:hover {
            background: var(--primary-hover);
        }
        button:active {
            transform: translate(4px, 4px);
            box-shadow: 0px 0px 0px var(--border-color);
        }
        button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
            transform: translate(4px, 4px);
            box-shadow: 0px 0px 0px var(--border-color);
        }
        .loader {
            display: none;
            text-transform: uppercase;
            font-weight: 700;
            margin: 2rem 0;
            border: 3px solid var(--border-color);
            padding: 1rem;
            background: #ffff00;
            box-shadow: 4px 4px 0px var(--border-color);
            color: var(--text-main);
            letter-spacing: -0.5px;
        }
        .results {
            display: none;
            flex-direction: column;
            gap: 2rem;
        }
        .card {
            background: var(--surface-color);
            border: 3px solid var(--border-color);
            padding: 1.5rem;
            box-shadow: 6px 6px 0px var(--border-color);
        }
        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1.5rem;
            border-bottom: 2px dashed var(--border-color);
            padding-bottom: 0.5rem;
        }
        .card-title {
            font-size: 1.1rem;
            text-transform: uppercase;
            font-weight: 700;
            letter-spacing: -0.5px;
        }
        .copy-btn {
            background: #ffffff;
            color: var(--primary-color);
            border: 2px solid var(--border-color);
            padding: 0.4rem 1rem;
            font-size: 0.8rem;
            box-shadow: 2px 2px 0px var(--border-color);
            border-radius: 0;
        }
        .copy-btn:hover {
            background: #f0f0f0;
        }
        .copy-btn.copied {
            background: var(--primary-color);
            color: #ffffff;
            box-shadow: 0px 0px 0px var(--border-color);
            transform: translate(2px, 2px);
        }
        .content-box {
            font-size: 0.95rem;
            line-height: 1.6;
            margin: 0;
            white-space: pre-wrap;
            word-wrap: break-word;
            font-family: inherit;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>News Extractor Analyzer</h1>
        <form id="extract-form" class="input-group">
            <input type="text" id="url" placeholder="Paste URL here..." required>
            <button type="submit" id="submit-btn" style="min-width: 150px;">Extract</button>
        </form>

        <div id="loader" class="loader">Extracting & Categorizing...</div>

        <div id="results" class="results" style="display: none;">
            <div class="card">
                <div class="card-header">
                    <span class="card-title">Title</span>
                    <button class="copy-btn" onclick="copyText('title-content', this)">Copy</button>
                </div>
                <div id="title-content" class="content-box"></div>
            </div>
            
            <div class="card">
                <div class="card-header">
                    <span class="card-title">Category</span>
                    <button class="copy-btn" onclick="copyText('category-content', this)">Copy</button>
                </div>
                <div id="category-content" class="content-box"></div>
            </div>

            <div class="card">
                <div class="card-header">
                    <span class="card-title">Image URL</span>
                    <button class="copy-btn" onclick="copyText('image-content', this)">Copy</button>
                </div>
                <div id="image-content" class="content-box"></div>
            </div>

            <div class="card">
                <div class="card-header">
                    <span class="card-title">Content</span>
                    <button class="copy-btn" onclick="copyText('article-content', this)">Copy</button>
                </div>
                <div id="article-content" class="content-box"></div>
            </div>
        </div>
    </div>

    <script>
        const form = document.getElementById('extract-form');
        const submitBtn = document.getElementById('submit-btn');
        const loader = document.getElementById('loader');
        const results = document.getElementById('results');

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const url = document.getElementById('url').value;
            
            submitBtn.disabled = true;
            loader.style.display = 'block';
            results.style.display = 'none';

            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 60000); // 60s timeout

            try {
                const response = await fetch("{{ url_for('extractor_bp.api_extract') }}", {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url }),
                    signal: controller.signal
                });
                clearTimeout(timeoutId);

                const data = await response.json();
                
                if (response.ok) {
                    document.getElementById('title-content').textContent = data.title;
                    document.getElementById('category-content').textContent = data.category;
                    document.getElementById('image-content').textContent = data.image_url;
                    document.getElementById('article-content').textContent = data.content;
                    results.style.display = 'flex';
                } else {
                    alert('Error: ' + (data.error || 'Unknown error'));
                }
            } catch (err) {
                console.error('Fetch error:', err);
                alert('Network request failed. Please check the console (F12) for details.');
            } finally {
                submitBtn.disabled = false;
                loader.style.display = 'none';
            }
        });

        async function copyText(elementId, btn) {
            const textToCopy = document.getElementById(elementId).textContent;
            try {
                await navigator.clipboard.writeText(textToCopy);
                const originalText = btn.textContent;
                btn.textContent = 'Copied!';
                btn.classList.add('copied');
                setTimeout(() => {
                    btn.textContent = 'Copy';
                    btn.classList.remove('copied');
                }, 2000);
            } catch (err) {
                console.error('Failed to copy', err);
                alert('Failed to copy text. Your browser might require HTTPS or you blocked clipboard access.');
            }
        }
    </script>
</body>
</html>
"""

@extractor_bp.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@extractor_bp.route('/api/extract', methods=['POST'])
def api_extract():
    data = request.json
    source_url = data.get('url')
    logger.info(f"[*] Received extraction request for: {source_url}")
    if not source_url:
        return jsonify({"error": "No URL provided"}), 400
        
    try:
        extracted = extract(source_url)
        logger.info(f"[+] Content extracted. Categorizing...")
        raw_content = extracted["content"]
        word_count = len(raw_content.split()) if raw_content else 0
        if word_count > 60:
            logger.info(f"[*] Content is {word_count} words — summarizing...")
            final_content = summarize(raw_content)
        else:
            logger.info(f"[*] Content is {word_count} words — short enough, skipping summarization.")
            final_content = raw_content
        snippet = final_content.split("\n\n")[0] if final_content else ""
        category = categorize(extracted["title"], snippet)
        
        logger.info(f"[+] Extraction complete for: {source_url}")
        return jsonify({
            "title": extracted["title"],
            "image_url": extracted["image_url"],
            "content": final_content,
            "category": category
        })
    except Exception as e:
        logger.error(f"[X] Extraction failed: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    # Use 5001 - port 5060 is blocked by browsers as "Unsafe" (SIP port)
    test_app = Flask(__name__)
    test_app.register_blueprint(extractor_bp)
    test_app.run(debug=True, port=5001)
