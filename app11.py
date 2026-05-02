"""
Newsband Newsletter Editor — Flask Backend for Day11.html
Uses BeautifulSoup4 for controlled, field-level HTML editing.
This handles the special JS bundler wrapper in Day11.html.
"""

import io
import re
import json
from datetime import datetime
from flask import Blueprint, request, jsonify, render_template, send_file, Response
from bs4 import BeautifulSoup, NavigableString

day11_editor_bp = Blueprint('day11_editor', __name__)

# ── Load base template once at startup ────────────────────────────────────────
with open("Day11.html", "r", encoding="utf-8") as f:
    BASE_HTML = f.read()

_current_html = BASE_HTML   # mutable working copy


# ── Helpers ───────────────────────────────────────────────────────────────────

class MockCard:
    def __init__(self, index, headline_tag, summary_tag, img_tag, category_text=""):
        self.index = index
        self.headline_tag = headline_tag
        self.summary_tag = summary_tag
        self.img_tag = img_tag
        self.category_text = category_text

def _parse_date_parts(date_val: str):
    """Return (dd, mm, yyyy) strings from various date input formats, or None."""
    parts = date_val.split("/")
    if len(parts) == 3:
        return parts[0].strip(), parts[1].strip(), parts[2].strip()
    for fmt in ("%B %d, %Y", "%d %B %Y", "%B %d %Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(date_val.strip(), fmt)
            return f"{dt.day:02d}", f"{dt.month:02d}", str(dt.year)
        except ValueError:
            continue
    return None

def _set_text(tag, text: str):
    tag.clear()
    tag.append(NavigableString(text))

def _find_header_date(soup):
    return soup.find("div", style=lambda s: s and "color:#737373" in s)

def _find_header_rni(soup):
    return soup.find("div", style=lambda s: s and "color:#888888" in s)

def _find_cards(soup):
    cards = []
    
    # 1. Intro Card (Index 0)
    intro_hl = soup.find("td", style=lambda s: s and "font-size:32px" in s)
    intro_sum = soup.find("td", style=lambda s: s and "font-size:13px" in s and "padding:0" in s)
    intro_img = soup.find("img", width="754")
    if intro_hl and intro_sum and intro_img:
        cards.append(MockCard(0, intro_hl, intro_sum, intro_img, category_text="Featured"))
        
    # 2. Event Cards
    cat_tds = soup.find_all(["td", "div"], style=lambda s: s and "letter-spacing:1.5px" in s and "text-transform:uppercase" in s)
    for cat_td in cat_tds:
        card_table = cat_td.find_parent("table")
        if card_table and card_table not in cards:
            cards.append(card_table)
            
    return cards

def _find_category_td(card):
    if isinstance(card, MockCard):
        return None
    return card.find(["td", "div"], style=lambda s: s and "letter-spacing:1.5px" in s and "text-transform:uppercase" in s)

def _find_headline_td(card):
    if isinstance(card, MockCard):
        return card.headline_tag
    return card.find(["td", "div"], style=lambda s: s and "letter-spacing:1px" in s and "text-transform:uppercase" in s)

def _find_summary_td(card):
    if isinstance(card, MockCard):
        return card.summary_tag
    return card.find(["td", "div"], style=lambda s: s and "text-align:justify" in s)

def _find_image_img(card):
    if isinstance(card, MockCard):
        return card.img_tag
    return card.find("img")

def _find_link_a(card):
    if isinstance(card, MockCard):
        return card.img_tag.find_parent("a")
    return card.find_parent("a")

def _get_inner_soup(html_str):
    outer_soup = BeautifulSoup(html_str, "html.parser")
    template_script = outer_soup.find("script", type="__bundler/template")
    if not template_script:
        return outer_soup, outer_soup, template_script
    
    inner_html_str = template_script.string
    inner_html = json.loads(inner_html_str)
    inner_soup = BeautifulSoup(inner_html, "html.parser")
    
    return outer_soup, inner_soup, template_script

# ── Parse: extract current editable fields ────────────────────────────────────

def parse_fields(html: str) -> dict:
    outer_soup, soup, _ = _get_inner_soup(html)
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
        story["link"] = "" # No links natively in Day11

        a_tag = _find_link_a(card)
        if a_tag:
            story["link"] = a_tag.get("href", "")

        if isinstance(card, MockCard):
            story["category"] = card.category_text
        else:
            cat_td = _find_category_td(card)
            if cat_td:
                story["category"] = cat_td.get_text().strip()

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
    outer_soup, soup, template_script = _get_inner_soup(html)

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
    cards = _find_cards(soup)
    for story_data in data.get("stories", []):
        idx = story_data.get("index", 0)
        if idx >= len(cards):
            continue
        card = cards[idx]

        # Category
        cat = (story_data.get("category") or "").strip()
        if cat:
            cat_td = _find_category_td(card)
            if cat_td:
                _set_text(cat_td, cat)

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

        # Image URL — update img src
        img_url = (story_data.get("image") or "").strip()
        if img_url:
            if img_url.startswith(("http://", "https://")):
                img_tag = _find_image_img(card)
                if img_tag:
                    img_tag["src"] = img_url

        # Link URL
        link_url = (story_data.get("link") or "").strip()
        if link_url:
            a_tag = _find_link_a(card)
            if a_tag:
                a_tag["href"] = link_url

    # Save back to script tag if it exists
    if template_script:
        # Prevent double-escaping of unicode characters (like \u2022 if present)
        new_inner_html_str = json.dumps(str(soup), ensure_ascii=False)
        template_script.string = new_inner_html_str
        return str(outer_soup)
    else:
        return str(soup)


# ── Routes ────────────────────────────────────────────────────────────────────

@day11_editor_bp.route("/")
def editor():
    return render_template("editor.html", api_prefix="/day11-editor")


@day11_editor_bp.route("/api/fields")
def api_fields():
    return jsonify(parse_fields(_current_html))


@day11_editor_bp.route("/api/update", methods=["POST"])
def api_update():
    global _current_html
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON body"}), 400
    _current_html = update_html(_current_html, data)
    return jsonify({"success": True, "html": _current_html})


@day11_editor_bp.route("/api/preview")
def api_preview():
    # Because Day11 uses a JS bundler, we serve the outer HTML directly
    return Response(_current_html, mimetype="text/html; charset=utf-8")


@day11_editor_bp.route("/api/export")
def api_export():
    buf = io.BytesIO(_current_html.encode("utf-8"))
    return send_file(
        buf,
        as_attachment=True,
        download_name="newsband_newsletter.html",
        mimetype="text/html",
    )


@day11_editor_bp.route("/api/reset", methods=["POST"])
def api_reset():
    global _current_html
    _current_html = BASE_HTML
    return jsonify({"success": True})


@day11_editor_bp.route("/api/import_json", methods=["POST"])
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


if __name__ == "__main__":
    from flask import Flask, redirect
    test_app = Flask(__name__, template_folder=".")
    test_app.register_blueprint(day11_editor_bp, url_prefix='/day11-editor')
    
    @test_app.route('/')
    def index():
        return redirect('/day11-editor/')
        
    test_app.run(debug=True, host="0.0.0.0", port=5000)
