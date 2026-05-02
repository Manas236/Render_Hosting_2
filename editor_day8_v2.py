"""
Newsband Newsletter Editor — Flask Backend for Day 8 (v2)
Uses BeautifulSoup4 for controlled, field-level HTML editing.
"""

import io
from flask import Blueprint, request, jsonify, render_template, send_file, Response
from bs4 import BeautifulSoup, NavigableString

day8_v2_editor_bp = Blueprint('day8_v2_editor', __name__)

# ── Load base template once at startup ────────────────────────────────────────
with open("Day8.html", "r", encoding="utf-8") as f:
    BASE_HTML = f.read()

_current_html = BASE_HTML   # mutable working copy


# ── Helpers ───────────────────────────────────────────────────────────────────

def _set_text(tag, text: str):
    """Safely replace all children of a tag with a single plain-text node."""
    tag.clear()
    tag.append(NavigableString(text))


def _find_header_date(soup):
    return soup.find("div", style=lambda s: s and "color:#737373" in s.replace(" ", ""))


def _find_header_rni(soup):
    return soup.find("div", style=lambda s: s and "color:#888888" in s.replace(" ", ""))


def _find_cards(soup):
    return soup.find_all("table", class_="card-table")


def _find_category_div(card):
    return card.find(
        "div",
        style=lambda s: s and "letter-spacing:3.5px" in s.replace(" ", ""),
    )


def _find_headline_div(card):
    return card.find("div", class_="card-headline")


def _find_summary_div(card):
    return card.find(
        "div",
        style=lambda s: s and "line-height:1.7" in s.replace(" ", ""),
    )


def _find_image_img(card):
    return card.find("img", style=lambda s: s and "object-fit:cover" in s.replace(" ", ""))


# ── Parse: extract current editable fields ────────────────────────────────────

def get_tomorrow_date_str() -> str:
    from datetime import datetime, timedelta
    dt = datetime.now() + timedelta(days=1)
    return dt.strftime("%B %d, %Y").replace(" 0", " ")

def parse_fields(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    result = {}

    date_div = _find_header_date(soup)
    if date_div:
        result["date"] = get_tomorrow_date_str()

    rni_div = _find_header_rni(soup)
    if rni_div:
        result["rni"] = rni_div.get_text().replace("RNI:", "").strip()

    stories = []
    for i, card in enumerate(_find_cards(soup)):
        story = {"index": i}

        link_tag = card.find("a", href=True)
        if link_tag:
            story["link"] = link_tag.get("href", "")

        cat_div = _find_category_div(card)
        if cat_div:
            story["category"] = cat_div.get_text().strip()

        hl_div = _find_headline_div(card)
        if hl_div:
            story["headline"] = hl_div.get_text().strip()

        sum_div = _find_summary_div(card)
        if sum_div:
            story["summary"] = sum_div.get_text().strip()

        img_tag = _find_image_img(card)
        if img_tag:
            story["image"] = img_tag.get("src", "")

        stories.append(story)

    result["stories"] = stories
    return result


# ── Update: apply user edits via BeautifulSoup ────────────────────────────────

def update_html(html: str, data: dict) -> str:
    soup = BeautifulSoup(html, "html.parser")

    date_val = (data.get("date") or "").strip()
    if date_val:
        date_div = _find_header_date(soup)
        if date_div:
            _set_text(date_div, f"Date: {date_val}")

    rni_val = (data.get("rni") or "").strip()
    if rni_val:
        rni_div = _find_header_rni(soup)
        if rni_div:
            _set_text(rni_div, f"RNI: {rni_val}")

    cards = _find_cards(soup)
    for story_data in data.get("stories", []):
        idx = story_data.get("index", 0)
        if idx >= len(cards):
            continue
        card = cards[idx]

        link = (story_data.get("link") or "").strip()
        if link:
            for a_tag in card.find_all("a", href=True):
                a_tag["href"] = link

        cat = (story_data.get("category") or "").strip()
        if cat:
            cat_div = _find_category_div(card)
            if cat_div:
                _set_text(cat_div, cat)

        hl = (story_data.get("headline") or "").strip()
        if hl:
            hl_div = _find_headline_div(card)
            if hl_div:
                _set_text(hl_div, hl)

        summ = (story_data.get("summary") or "").strip()
        if summ:
            sum_div = _find_summary_div(card)
            if sum_div:
                _set_text(sum_div, summ)

        img_url = (story_data.get("image") or "").strip()
        if img_url:
            if img_url.startswith(("http://", "https://")):
                img_tag = _find_image_img(card)
                if img_tag:
                    img_tag["src"] = img_url

    return str(soup)


# ── Routes ────────────────────────────────────────────────────────────────────

@day8_v2_editor_bp.route("/")
def editor():
    return render_template("editor_day8.html")


@day8_v2_editor_bp.route("/api/fields")
def api_fields():
    return jsonify(parse_fields(_current_html))


@day8_v2_editor_bp.route("/api/update", methods=["POST"])
def api_update():
    global _current_html
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON body"}), 400
    _current_html = update_html(_current_html, data)
    return jsonify({"success": True, "html": _current_html})


@day8_v2_editor_bp.route("/api/preview")
def api_preview():
    return Response(_current_html, mimetype="text/html; charset=utf-8")


@day8_v2_editor_bp.route("/api/export")
def api_export():
    buf = io.BytesIO(_current_html.encode("utf-8"))
    return send_file(
        buf,
        as_attachment=True,
        download_name="newsband_newsletter_day8.html",
        mimetype="text/html",
    )


@day8_v2_editor_bp.route("/api/reset", methods=["POST"])
def api_reset():
    global _current_html
    _current_html = BASE_HTML
    return jsonify({"success": True})


@day8_v2_editor_bp.route("/api/import_json", methods=["POST"])
def api_import_json():
    global _current_html
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    stories = data.get("stories", [])
    for i, s in enumerate(stories):
        s.setdefault("index", i)

    _current_html = update_html(_current_html, data)
    return jsonify({"success": True, "html": _current_html, "fields": parse_fields(_current_html)})
