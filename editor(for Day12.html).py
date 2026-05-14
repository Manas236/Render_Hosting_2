"""
Newsband Newsletter Editor — Day12 Flask Backend
Uses BeautifulSoup4 for controlled, field-level HTML editing.
Footer, layout structure, CSS, and logo are strictly locked.
"""

import io
from flask import Blueprint, request, jsonify, render_template, send_file, Response
from bs4 import BeautifulSoup, NavigableString

day12_editor_bp = Blueprint('day12_editor', __name__)

# ── Load base template once at startup ────────────────────────────────────────
with open("Day12.html", "r", encoding="utf-8") as f:
    BASE_HTML = f.read()
    print(f"DEBUG [Day12]: BASE_HTML length: {len(BASE_HTML)}")

_current_html = BASE_HTML   # mutable working copy


# ── Helpers ───────────────────────────────────────────────────────────────────

def _set_text(tag, text: str):
    """Safely replace all children of a tag with a single plain-text node."""
    tag.clear()
    tag.append(NavigableString(text))


def _find_header_date(soup):
    """Find the date div inside the header (font-weight:600; color:#737373)."""
    for div in soup.find_all("div"):
        style = div.get("style", "")
        if "color:#737373" in style and "font-weight:600" in style:
            text = div.get_text()
            if "Date:" in text:
                return div
    return None


def _find_header_rni(soup):
    """Find the RNI div inside the header (color:#888888)."""
    for div in soup.find_all("div"):
        style = div.get("style", "")
        if "color:#888888" in style and "font-size:9px" in style:
            text = div.get_text()
            if "RNI:" in text:
                return div
    return None


def _find_articles(soup):
    """
    Return a list of article containers. Day12 has 5 articles:
      [0] Featured article   — direct <a> child wrapping a full table
      [1] Article 1           — horizontal card (image left, text right)
      [2] Article 2           — horizontal card
      [3] Left grid card      — vertical card in two-column grid
      [4] Right grid card     — vertical card in two-column grid
    Each article is wrapped in an <a> tag with style containing
    "text-decoration:none" and "display:block".
    """
    articles = []
    for a_tag in soup.find_all("a"):
        style = a_tag.get("style", "")
        if "text-decoration:none" in style and "display:block" in style:
            # Skip footer links (social icons, website, etc.)
            parent_td = a_tag.find_parent("td")
            if parent_td:
                parent_style = parent_td.get("style", "")
                if "background-color:#0a0a0a" in parent_style:
                    continue
            articles.append(a_tag)
    return articles


def _find_category(article_a):
    """Find category <p> tag. Category paragraphs have letter-spacing:1.5px and text-transform:uppercase."""
    for p in article_a.find_all("p"):
        style = p.get("style", "")
        if "letter-spacing:1.5px" in style and "text-transform:uppercase" in style:
            return p
    return None


def _find_headline(article_a):
    """Find headline tag — could be h1, h2, or h3."""
    for tag_name in ["h1", "h2", "h3"]:
        tag = article_a.find(tag_name)
        if tag:
            return tag
    return None


def _find_summary(article_a):
    """Find the summary paragraph — text-align:justify, color:#555555."""
    for p in article_a.find_all("p"):
        style = p.get("style", "")
        if "text-align:justify" in style and "color:#555555" in style:
            return p
    return None


def _find_image(article_a):
    """Find the main <img> tag in the article (not button icons)."""
    for img in article_a.find_all("img"):
        style = img.get("style", "")
        if "border-radius" in style and "width:100%" in style:
            return img
    return None


# ── Parse: extract current editable fields ────────────────────────────────────

def get_tomorrow_date_str() -> str:
    from datetime import datetime, timedelta
    dt = datetime.now() + timedelta(days=1)
    return dt.strftime("%B %d, %Y").replace(" 0", " ")


def parse_fields(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    result = {}

    # Header — Date
    date_div = _find_header_date(soup)
    if date_div:
        result["date"] = get_tomorrow_date_str()

    # Header — RNI
    rni_div = _find_header_rni(soup)
    if rni_div:
        result["rni"] = rni_div.get_text().replace("RNI:", "").strip()

    # Stories
    stories = []
    articles = _find_articles(soup)
    for i, article in enumerate(articles):
        story = {"index": i}

        story["link"] = article.get("href", "")

        cat = _find_category(article)
        if cat:
            story["category"] = cat.get_text().strip()

        hl = _find_headline(article)
        if hl:
            story["headline"] = hl.get_text().strip()

        summ = _find_summary(article)
        if summ:
            story["summary"] = summ.get_text().strip()

        img = _find_image(article)
        if img:
            story["image"] = img.get("src", "")

        stories.append(story)

    result["stories"] = stories
    return result


# ── Update: apply user edits via BeautifulSoup ────────────────────────────────

def update_html(html: str, data: dict) -> str:
    soup = BeautifulSoup(html, "html.parser")

    # ── PROTECTED: footer is never touched ────────────────────────────────────

    # Header — Date
    date_val = (data.get("date") or "").strip()
    if date_val:
        date_div = _find_header_date(soup)
        if date_div:
            _set_text(date_div, f"Date: {date_val}")

    # Header — RNI
    rni_val = (data.get("rni") or "").strip()
    if rni_val:
        rni_div = _find_header_rni(soup)
        if rni_div:
            _set_text(rni_div, f"RNI: {rni_val}")

    # Stories
    articles = _find_articles(soup)
    for story_data in data.get("stories", []):
        idx = story_data.get("index", 0)
        if idx >= len(articles):
            continue
        article = articles[idx]

        # Link (href on the <a> tag)
        link = (story_data.get("link") or "").strip()
        if link:
            article["href"] = link

        # Category
        cat = (story_data.get("category") or "").strip()
        if cat:
            cat_tag = _find_category(article)
            if cat_tag:
                _set_text(cat_tag, cat.upper())

        # Headline
        hl = (story_data.get("headline") or "").strip()
        if hl:
            hl_tag = _find_headline(article)
            if hl_tag:
                _set_text(hl_tag, hl)

        # Summary
        summ = (story_data.get("summary") or "").strip()
        if summ:
            sum_tag = _find_summary(article)
            if sum_tag:
                _set_text(sum_tag, summ)

        # Image URL — update img src
        img_url = (story_data.get("image") or "").strip()
        if img_url:
            if img_url.startswith(("http://", "https://")):
                img_tag = _find_image(article)
                if img_tag:
                    img_tag["src"] = img_url

    return str(soup)


# ── Routes ────────────────────────────────────────────────────────────────────

@day12_editor_bp.route("/")
def editor():
    return render_template("editor_day12.html", api_prefix="/day12-editor")


@day12_editor_bp.route("/api/fields")
def api_fields():
    return jsonify(parse_fields(_current_html))


@day12_editor_bp.route("/api/update", methods=["POST"])
def api_update():
    global _current_html
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON body"}), 400
    _current_html = update_html(_current_html, data)
    return jsonify({"success": True, "html": _current_html})


@day12_editor_bp.route("/api/preview")
def api_preview():
    return Response(_current_html, mimetype="text/html; charset=utf-8")


@day12_editor_bp.route("/api/export")
def api_export():
    buf = io.BytesIO(_current_html.encode("utf-8"))
    return send_file(
        buf,
        as_attachment=True,
        download_name="newsband_day12_newsletter.html",
        mimetype="text/html",
    )


@day12_editor_bp.route("/api/reset", methods=["POST"])
def api_reset():
    global _current_html
    _current_html = BASE_HTML
    return jsonify({"success": True})


@day12_editor_bp.route("/api/import_json", methods=["POST"])
def api_import_json():
    """
    Accept a JSON body matching the stories schema and apply it.
    Schema:
      { "date": "DD/MM/YYYY", "rni": "...", "stories": [ { "category", "headline", "summary", "image", "link" }, ... ] }
    Stories are matched by array position (0-indexed).
    """
    global _current_html
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    # Re-index stories if they don't have an explicit index
    stories = data.get("stories", [])
    for i, s in enumerate(stories):
        s.setdefault("index", i)

    _current_html = update_html(_current_html, data)
    return jsonify({"success": True, "html": _current_html, "fields": parse_fields(_current_html)})


if __name__ == "__main__":
    from flask import Flask
    test_app = Flask(__name__, template_folder=".")
    test_app.register_blueprint(day12_editor_bp)
    test_app.run(debug=True, host="0.0.0.0", port=5000)
