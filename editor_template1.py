"""
Newsband Newsletter Editor — Flask Backend for Template1
Uses BeautifulSoup4 for controlled, field-level HTML editing.
"""

import io
from flask import Blueprint, request, jsonify, render_template, send_file, Response
from bs4 import BeautifulSoup, NavigableString

template1_editor_bp = Blueprint('template1_editor', __name__)

# ── Load base template once at startup ────────────────────────────────────────
with open("template1.html", "r", encoding="utf-8") as f:
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
    """
    Find all article <a> tags that wrap card content.
    Template1 has 5 stories:
      - Story 1: hero (yellow block + image, first <a>)
      - Stories 2-4: three square cards
      - Story 5: bottom section (image + yellow block)
    """
    cards = []
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        # Skip footer/social links
        if "instagram.com" in href or "facebook.com" in href or "x.com" in href or "youtube.com" in href:
            continue
        if href == "*|UNSUB|*":
            continue
        if "newsband.in" in href and "uploads" not in href:
            continue
        # Must contain a table (card structure)
        if a.find("table"):
            cards.append(a)
    return cards


def _find_category(card):
    """Find category <div> — identified by letter-spacing:1px or 2px and color:#E9B824."""
    for div in card.find_all("div"):
        style = (div.get("style") or "").replace(" ", "")
        if "color:#E9B824" in style and "letter-spacing" in style and "text-transform:uppercase" in style:
            # Skip "Featured Stories" section labels (they contain "margin-bottom:12px")
            if "margin-bottom:12px" in style:
                continue
            return div
    return None


def _find_headline(card):
    """Find headline <div> — identified by font-weight:800 or font-weight:700 and color:#1a1a1a and text-transform:uppercase."""
    for div in card.find_all("div"):
        style = (div.get("style") or "").replace(" ", "")
        if "color:#1a1a1a" in style and "text-transform:uppercase" in style and ("font-weight:800" in style or "font-weight:700" in style):
            return div
    return None


def _find_summary(card):
    """Find summary <p> — identified by text-align:justify."""
    for p in card.find_all("p"):
        style = (p.get("style") or "").replace(" ", "")
        if "text-align:justify" in style:
            return p
    return None


def _find_image(card):
    """Find the main content <img> (with object-fit:cover)."""
    return card.find("img", style=lambda s: s and "object-fit:cover" in s.replace(" ", ""))


def _find_bg_image_td(card):
    """Find a <td> with a background-image URL (used for hero/bottom image sections)."""
    for td in card.find_all("td"):
        style = (td.get("style") or "")
        if "background-image:url(" in style.replace(" ", ""):
            return td
    return None


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

        story["link"] = card.get("href", "")

        cat = _find_category(card)
        if cat:
            story["category"] = cat.get_text().strip()

        hl = _find_headline(card)
        if hl:
            story["headline"] = hl.get_text().strip()

        summ = _find_summary(card)
        if summ:
            story["summary"] = summ.get_text().strip()

        img = _find_image(card)
        if img:
            story["image"] = img.get("src", "")
        else:
            # Fallback: background-image on a <td>
            bg_td = _find_bg_image_td(card)
            if bg_td:
                import re
                m = re.search(r"background-image:\s*url\(['\"]?(.*?)['\"]?\)", bg_td.get("style", ""))
                if m:
                    story["image"] = m.group(1)

        stories.append(story)

    result["stories"] = stories
    return result


# ── Update: apply user edits via BeautifulSoup ────────────────────────────────

def update_html(html: str, data: dict) -> str:
    import re
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
            card["href"] = link

        cat_text = (story_data.get("category") or "").strip()
        if cat_text:
            cat_el = _find_category(card)
            if cat_el:
                _set_text(cat_el, cat_text)

        hl_text = (story_data.get("headline") or "").strip()
        if hl_text:
            hl_el = _find_headline(card)
            if hl_el:
                _set_text(hl_el, hl_text)

        summ_text = (story_data.get("summary") or "").strip()
        if summ_text:
            sum_el = _find_summary(card)
            if sum_el:
                _set_text(sum_el, summ_text)

        img_url = (story_data.get("image") or "").strip()
        if img_url and img_url.startswith(("http://", "https://")):
            img_el = _find_image(card)
            if img_el:
                img_el["src"] = img_url
            else:
                # Update background-image on <td>
                bg_td = _find_bg_image_td(card)
                if bg_td:
                    old_style = bg_td.get("style", "")
                    new_style = re.sub(
                        r"background-image:\s*url\(['\"]?.*?['\"]?\)",
                        f"background-image:url('{img_url}')",
                        old_style,
                    )
                    bg_td["style"] = new_style

    return str(soup)


# ── Routes ────────────────────────────────────────────────────────────────────

@template1_editor_bp.route("/")
def editor():
    return render_template("editor_template1.html")


@template1_editor_bp.route("/api/fields")
def api_fields():
    return jsonify(parse_fields(_current_html))


@template1_editor_bp.route("/api/update", methods=["POST"])
def api_update():
    global _current_html
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON body"}), 400
    _current_html = update_html(_current_html, data)
    return jsonify({"success": True, "html": _current_html})


@template1_editor_bp.route("/api/preview")
def api_preview():
    return Response(_current_html, mimetype="text/html; charset=utf-8")


@template1_editor_bp.route("/api/export")
def api_export():
    buf = io.BytesIO(_current_html.encode("utf-8"))
    return send_file(
        buf,
        as_attachment=True,
        download_name="newsband_newsletter_template1.html",
        mimetype="text/html",
    )


@template1_editor_bp.route("/api/reset", methods=["POST"])
def api_reset():
    global _current_html
    _current_html = BASE_HTML
    return jsonify({"success": True})


@template1_editor_bp.route("/api/import_json", methods=["POST"])
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
