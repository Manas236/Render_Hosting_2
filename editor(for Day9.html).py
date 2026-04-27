"""
Newsband Newsletter Editor — Flask Backend
Uses BeautifulSoup4 for controlled, field-level HTML editing.
Footer, layout structure, CSS, and logo are strictly locked.
"""

import io
import re
from flask import Blueprint, request, jsonify, render_template, send_file, Response
from bs4 import BeautifulSoup, NavigableString

day9_editor_bp = Blueprint('day9_editor', __name__)

# ── Load base template once at startup ────────────────────────────────────────
with open("Day9.html", "r", encoding="utf-8") as f:
    BASE_HTML = f.read()
    print(f"DEBUG: BASE_HTML length: {len(BASE_HTML)}")
    print(f"DEBUG: BASE_HTML snippet: {BASE_HTML[1500:1700]}") # Looking for header area

_current_html = BASE_HTML   # mutable working copy


# ── Helpers ───────────────────────────────────────────────────────────────────

def _set_text(tag, text: str):
    """Safely replace all children of a tag with a single plain-text node."""
    tag.clear()
    tag.append(NavigableString(text))


def _find_header_date(soup):
    hdr = soup.find(id="header")
    if not hdr:
        return None
    return hdr.find("div", style=lambda s: s and "color:#737373" in s)


def _find_header_rni(soup):
    hdr = soup.find(id="header")
    if not hdr:
        return None
    return hdr.find("div", style=lambda s: s and "color:#888888" in s)


def _find_cards(soup):
    return soup.find_all("a", class_="card-link")


def _find_category_td(card):
    return card.find(
        "td",
        style=lambda s: s and "color:#b8532d" in s and "letter-spacing:1.8px" in s,
    )


def _find_headline_td(card):
    return card.find("td", class_="title-text")


def _find_summary_td(card):
    return card.find(
        "td",
        style=lambda s: s and "color:#6b6357" in s and "padding-bottom:10px" in s,
    )


def _find_image_td(card):
    return card.find("td", style=lambda s: s and "background-image" in s)


def _find_image_img(card):
    return card.find(
        "img", style=lambda s: s and "border-radius:24px" in s
    )


# ── Parse: extract current editable fields ────────────────────────────────────

def parse_fields(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    result = {}

    # Header — Date
    date_div = _find_header_date(soup)
    if date_div:
        result["date"] = date_div.get_text().replace("Date:", "").strip()

    # Header — RNI
    rni_div = _find_header_rni(soup)
    if rni_div:
        result["rni"] = rni_div.get_text().replace("RNI:", "").strip()

    # Stories
    stories = []
    for i, card in enumerate(_find_cards(soup)):
        story = {"index": i}

        story["link"] = card.get("href", "")

        cat_td = _find_category_td(card)
        if cat_td:
            story["category"] = cat_td.get_text().replace("•", "").strip()

        hl_td = _find_headline_td(card)
        if hl_td:
            story["headline"] = hl_td.get_text().strip()

        sum_td = _find_summary_td(card)
        if sum_td:
            story["summary"] = sum_td.get_text().strip()

        img_tag = _find_image_img(card)
        if img_tag:
            story["image"] = img_tag.get("src", "")

        stories.append(story)

    result["stories"] = stories
    return result


# ── Update: apply user edits via BeautifulSoup ────────────────────────────────

def update_html(html: str, data: dict) -> str:
    soup = BeautifulSoup(html, "html.parser")

    # ── PROTECTED: footer is never touched ────────────────────────────────────
    # (We only operate on elements we explicitly target above)

    # Header — Date
    date_val = (data.get("date") or "").strip()
    if date_val:
        date_div = _find_header_date(soup)
        if date_div:
            _set_text(date_div, f"Date: {date_val}")

        # Also update the outro date stamp (NEWSBAND · DD · MM · YYYY)
        for td in soup.find_all("td"):
            raw = td.string
            if raw and "NEWSBAND" in raw and "\u00b7" in raw:
                parts = date_val.split("/")
                if len(parts) == 3:
                    try:
                        _set_text(
                            td,
                            f"NEWSBAND \u00b7 {parts[0]} \u00b7 {parts[1]} \u00b7 {parts[2]}",
                        )
                    except Exception:
                        pass
                break

    # Header — RNI
    rni_val = (data.get("rni") or "").strip()
    if rni_val:
        rni_div = _find_header_rni(soup)
        if rni_div:
            _set_text(rni_div, f"RNI: {rni_val}")

    # Stories
    cards = _find_cards(soup)
    for story_data in data.get("stories", []):
        idx = story_data.get("index", 0)
        if idx >= len(cards):
            continue
        card = cards[idx]

        # Link (href on the <a> tag)
        link = (story_data.get("link") or "").strip()
        if link:
            card["href"] = link

        # Category
        cat = (story_data.get("category") or "").strip()
        if cat:
            cat_td = _find_category_td(card)
            if cat_td:
                _set_text(cat_td, f"\u2022 {cat.upper()}")

        # Headline
        hl = (story_data.get("headline") or "").strip()
        if hl:
            hl_td = _find_headline_td(card)
            if hl_td:
                _set_text(hl_td, hl)

        # Summary
        summ = (story_data.get("summary") or "").strip()
        if summ:
            sum_td = _find_summary_td(card)
            if sum_td:
                _set_text(sum_td, summ)

        # Image URL — update both background-image style and img src
        img_url = (story_data.get("image") or "").strip()
        if img_url:
            # Validate: must look like a URL
            if img_url.startswith(("http://", "https://")):
                img_tag = _find_image_img(card)
                if img_tag:
                    img_tag["src"] = img_url

                bg_td = _find_image_td(card)
                if bg_td:
                    new_style = re.sub(
                        r"background-image:url\('[^']*'\)",
                        f"background-image:url('{img_url}')",
                        bg_td["style"],
                    )
                    bg_td["style"] = new_style

    return str(soup)


# ── Routes ────────────────────────────────────────────────────────────────────

@day9_editor_bp.route("/")
def editor():
    return render_template("editor.html")


@day9_editor_bp.route("/api/fields")
def api_fields():
    return jsonify(parse_fields(_current_html))


@day9_editor_bp.route("/api/update", methods=["POST"])
def api_update():
    global _current_html
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON body"}), 400
    _current_html = update_html(_current_html, data)
    return jsonify({"success": True, "html": _current_html})


@day9_editor_bp.route("/api/preview")
def api_preview():
    return Response(_current_html, mimetype="text/html; charset=utf-8")


@day9_editor_bp.route("/api/export")
def api_export():
    buf = io.BytesIO(_current_html.encode("utf-8"))
    return send_file(
        buf,
        as_attachment=True,
        download_name="newsband_newsletter.html",
        mimetype="text/html",
    )


@day9_editor_bp.route("/api/reset", methods=["POST"])
def api_reset():
    global _current_html
    _current_html = BASE_HTML
    return jsonify({"success": True})


@day9_editor_bp.route("/api/import_json", methods=["POST"])
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
    test_app.register_blueprint(day9_editor_bp)
    test_app.run(debug=True, host="0.0.0.0", port=5000)