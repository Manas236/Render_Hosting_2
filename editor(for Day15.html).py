"""
Newsband Newsletter Editor — Day15 Flask Backend
Uses BeautifulSoup4 for controlled, field-level HTML editing.
Footer, layout structure, CSS, and logo are strictly locked.
"""

import io
import re
from flask import Blueprint, request, jsonify, render_template, send_file, Response
from bs4 import BeautifulSoup, NavigableString

day15_editor_bp = Blueprint('day15_editor', __name__)

# ── Load base template once at startup ────────────────────────────────────────
with open("Day15.html", "r", encoding="utf-8") as f:
    BASE_HTML = f.read()
    print(f"DEBUG [Day15]: BASE_HTML length: {len(BASE_HTML)}")

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


def _find_masthead_text(soup):
    """Find the masthead strip text (e.g. 'Today's Top Stories')."""
    for td in soup.find_all("td"):
        style = td.get("style", "")
        if "letter-spacing:4px" in style and "color:#8b2a1f" in style and "text-transform:uppercase" in style:
            return td
    return None


# ── Story finders ─────────────────────────────────────────────────────────────

def _find_feature_story(soup):
    """
    Find the feature (hero) story section.
    It's the full-bleed section with a hero image and large headline.
    Returns dict with tag references.
    """
    result = {}

    # Hero image — the large full-width image (width:100%; max-width:754px)
    for img in soup.find_all("img"):
        style = img.get("style", "")
        if "max-width:754px" in style and "width:100%" in style:
            result["image"] = img
            break

    # Category tag — inside the feature section, small text with background:#8b2a1f
    # The feature section has the category label with padding:5px 10px
    for td in soup.find_all("td"):
        style = td.get("style", "")
        if "background:#8b2a1f" in style and "padding:5px 10px" in style:
            result["category"] = td
            break

    # "Top Story" label next to category
    for td in soup.find_all("td"):
        style = td.get("style", "")
        if "color:#6b6b6b" in style and "letter-spacing:2.5px" in style:
            text = td.get_text().strip()
            if "Top Story" in text:
                result["top_story_label"] = td
                break

    # Headline — large Georgia font, 40px
    for td in soup.find_all("td"):
        style = td.get("style", "")
        if "font-size:40px" in style and "font-weight:700" in style:
            result["headline"] = td
            break

    # Summary — 17px Georgia, text-align:justify
    for td in soup.find_all("td"):
        style = td.get("style", "")
        if "font-size:17px" in style and "line-height:1.6" in style and "text-align:justify" in style:
            result["summary"] = td
            break

    # Link — "Read Full Story →"
    for a in soup.find_all("a"):
        text = a.get_text().strip()
        if "Read Full Story" in text:
            result["link"] = a
            break

    return result


def _find_twin_stories(soup):
    """
    Find the two twin medium stories (side-by-side columns).
    Returns list of 2 dicts with tag references.
    """
    stories = []

    # Find images with max-width:320px (twin story images)
    twin_images = []
    for img in soup.find_all("img"):
        style = img.get("style", "")
        if "max-width:320px" in style and "width:100%" in style:
            twin_images.append(img)

    # Find 23px headlines (twin story headlines)
    twin_headlines = []
    for td in soup.find_all("td"):
        style = td.get("style", "")
        if "font-size:23px" in style and "font-weight:700" in style:
            twin_headlines.append(td)

    # Find twin categories — spans with background:#8b2a1f and padding:4px 9px
    twin_cats = []
    for span in soup.find_all("span"):
        style = span.get("style", "")
        if "background:#8b2a1f" in style and "padding:4px 9px" in style:
            twin_cats.append(span)

    # Find twin summaries — 14px, line-height:1.55, text-align:justify, color:#3a3a3a
    twin_summaries = []
    for td in soup.find_all("td"):
        style = td.get("style", "")
        if "font-size:14px" in style and "line-height:1.55" in style and "color:#3a3a3a" in style and "text-align:justify" in style:
            twin_summaries.append(td)

    # Find twin wrapper <a> tags — contain max-width:320px images (distinct from
    # feature at 754px and compact at 240px). The "Read →" text is in a <span>,
    # not a separate <a>, so the outer wrapper is the only link element available.
    twin_wrappers = []
    for a in soup.find_all("a"):
        style = a.get("style", "")
        if "display:block" in style and "text-decoration:none" in style and "color:inherit" in style:
            for img in a.find_all("img"):
                if "max-width:320px" in img.get("style", ""):
                    twin_wrappers.append(a)
                    break

    # Build stories from matched elements
    for i in range(min(2, len(twin_headlines))):
        story = {"index": i}
        if i < len(twin_images):
            story["image"] = twin_images[i]
        if i < len(twin_cats):
            story["category"] = twin_cats[i]
        if i < len(twin_headlines):
            story["headline"] = twin_headlines[i]
        if i < len(twin_summaries):
            story["summary"] = twin_summaries[i]
        if i < len(twin_wrappers):
            story["link"] = twin_wrappers[i]
        stories.append(story)

    return stories


def _find_compact_stories(soup):
    """
    Find the 2 compact stories (image+text side-by-side).
    These are wrapped in <a display:block> tags containing max-width:240px images.
    Returns list of 2 dicts with tag references.
    """
    stories = []

    # Find wrapping <a> tags: display:block; text-decoration:none; color:inherit
    # each wraps an entire compact story card (image + text).
    compact_wrappers = []
    for a in soup.find_all("a"):
        style = a.get("style", "")
        if "display:block" in style and "text-decoration:none" in style and "color:inherit" in style:
            for img in a.find_all("img"):
                if "max-width:240px" in img.get("style", ""):
                    compact_wrappers.append(a)
                    break

    for i, wrapper in enumerate(compact_wrappers[:2]):
        story = {"index": i, "link": wrapper}

        for img in wrapper.find_all("img"):
            if "max-width:240px" in img.get("style", ""):
                story["image"] = img
                break

        for span in wrapper.find_all("span"):
            if "background:#8b2a1f" in span.get("style", "") and "padding:4px 9px" in span.get("style", ""):
                story["category"] = span
                break

        for td in wrapper.find_all("td"):
            if "font-size:21px" in td.get("style", "") and "font-weight:700" in td.get("style", ""):
                story["headline"] = td
                break

        for td in wrapper.find_all("td"):
            if "font-size:14px" in td.get("style", "") and "line-height:1.55" in td.get("style", "") and "color:#3a3a3a" in td.get("style", ""):
                story["summary"] = td
                break

        stories.append(story)

    return stories


def _find_market_data(soup):
    """
    Find the markets ticker data.
    Returns list of 4 dicts (Sensex, Nifty, USD/INR, Gold).
    """
    markets = []
    dark_section = None
    for td in soup.find_all("td"):
        style = td.get("style", "")
        if "background:#0f0f0f" in style:
            dark_section = td
            break

    if not dark_section:
        return markets

    stat_cells = []
    for td in dark_section.find_all("td"):
        width = td.get("width", "")
        valign = td.get("valign", "")
        if width == "25%" and valign == "top":
            stat_cells.append(td)

    for cell in stat_cells:
        divs = cell.find_all("div")
        if len(divs) >= 3:
            change_text = divs[2].get_text().strip()
            positive = "color:#4caf7a" in divs[2].get("style", "")
            pct_match = re.search(r'([\d.]+)%', change_text)
            pct = pct_match.group(1) if pct_match else "0.00"
            market = {
                "label": divs[0].get_text().strip(),
                "value": divs[1].get_text().strip(),
                "pct": pct,
                "positive": positive,
            }
            markets.append(market)

    return markets


def _format_change_str(label: str, value_str: str, pct_float: float, positive: bool) -> str:
    arrow = "▲" if positive else "▼"
    sign = "+" if positive else "−"
    clean = value_str.replace("₹", "").replace(",", "").strip()
    try:
        value_num = float(clean)
    except Exception:
        return f"{arrow} N/A  ({sign}{abs(pct_float):.2f}%)"
    abs_change = value_num * pct_float / 100
    label_lower = label.lower()
    if "gold" in label_lower:
        return f"{arrow} {int(round(abs_change))}  ({sign}{abs(pct_float):.2f}%)"
    elif "usd" in label_lower or "/" in label:
        return f"{arrow} {abs(abs_change):.2f}  ({sign}{abs(pct_float):.2f}%)"
    else:
        return f"{arrow} {int(round(abs_change)):,}  ({sign}{abs(pct_float):.2f}%)"


# ── WMO weather codes ─────────────────────────────────────────────────────────

_WMO_CODES = {
    0:  ("Clear sky",            "☀"),
    1:  ("Mainly clear",         "☀"),
    2:  ("Partly cloudy",        "⛅"),
    3:  ("Overcast",             "☁"),
    45: ("Fog",                  "🌫"),
    48: ("Icy fog",              "🌫"),
    51: ("Light drizzle",        "🌦"),
    53: ("Moderate drizzle",     "🌦"),
    55: ("Dense drizzle",        "🌧"),
    61: ("Light rain",           "🌧"),
    63: ("Moderate rain",        "🌧"),
    65: ("Heavy rain",           "🌧"),
    71: ("Light snow",           "❄"),
    73: ("Moderate snow",        "❄"),
    75: ("Heavy snow",           "❄"),
    77: ("Snow grains",          "❄"),
    80: ("Light showers",        "🌦"),
    81: ("Moderate showers",     "🌧"),
    82: ("Heavy showers",        "⛈"),
    85: ("Slight snow showers",  "❄"),
    86: ("Heavy snow showers",   "❄"),
    95: ("Thunderstorm",         "⛈"),
    96: ("Thunderstorm w/ hail", "⛈"),
    99: ("Thunderstorm w/ hail", "⛈"),
}


def _find_weather_data(soup):
    """
    Find the Day15 weather band.
    Returns dict with location, today_desc, today_high, today_low.
    """
    weather = {}

    # Location div: letter-spacing:3px + color:#8b2a1f, contains · separator
    for div in soup.find_all("div"):
        style = div.get("style", "")
        if "letter-spacing:3px" in style and "color:#8b2a1f" in style:
            text = div.get_text()
            if "·" in text or "Weather" in text:
                parts = text.split("·")
                if parts:
                    weather["location"] = parts[0].strip().strip("\xa0").strip()
                break

    desc_div = soup.find(class_="weather-desc-today")
    if desc_div:
        weather["today_desc"] = desc_div.get_text().strip()

    high_span = soup.find(class_="weather-high-today")
    if high_span:
        m = re.search(r"\d+", high_span.get_text())
        if m:
            weather["today_high"] = m.group()

    low_span = soup.find(class_="weather-low-today")
    if low_span:
        m = re.search(r"\d+", low_span.get_text())
        if m:
            weather["today_low"] = m.group()

    weather.setdefault("location", "Navi Mumbai")
    weather.setdefault("today_desc", "")
    weather.setdefault("today_high", "")
    weather.setdefault("today_low", "")
    return weather


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

    # Masthead text
    mast = _find_masthead_text(soup)
    if mast:
        result["masthead"] = mast.get_text().strip()

    # Stories — build a unified list
    stories = []

    # Story 0: Feature
    feature = _find_feature_story(soup)
    s0 = {"index": 0, "type": "feature"}
    if "category" in feature:
        s0["category"] = feature["category"].get_text().strip()
    if "headline" in feature:
        s0["headline"] = feature["headline"].get_text().strip()
    if "summary" in feature:
        s0["summary"] = feature["summary"].get_text().strip()
    if "image" in feature:
        s0["image"] = feature["image"].get("src", "")
    if "link" in feature:
        s0["link"] = feature["link"].get("href", "")
    stories.append(s0)

    # Stories 1-2: Twin medium
    twins = _find_twin_stories(soup)
    for i, tw in enumerate(twins):
        s = {"index": i + 1, "type": "medium"}
        if "category" in tw:
            s["category"] = tw["category"].get_text().strip()
        if "headline" in tw:
            s["headline"] = tw["headline"].get_text().strip()
        if "summary" in tw:
            s["summary"] = tw["summary"].get_text().strip()
        if "image" in tw:
            s["image"] = tw["image"].get("src", "")
        if "link" in tw:
            s["link"] = tw["link"].get("href", "")
        stories.append(s)

    # Stories 3-4: Compact
    compacts = _find_compact_stories(soup)
    for i, c in enumerate(compacts):
        s = {"index": i + 3, "type": "compact"}
        if "category" in c:
            s["category"] = c["category"].get_text().strip()
        if "headline" in c:
            s["headline"] = c["headline"].get_text().strip()
        if "summary" in c:
            s["summary"] = c["summary"].get_text().strip()
        if "image" in c:
            s["image"] = c["image"].get("src", "")
        if "link" in c:
            s["link"] = c["link"].get("href", "")
        stories.append(s)

    result["stories"] = stories

    # Weather
    result["weather"] = _find_weather_data(soup)

    # Markets
    result["markets"] = _find_market_data(soup)

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

    # Masthead text
    mast_val = (data.get("masthead") or "").strip()
    if mast_val:
        mast = _find_masthead_text(soup)
        if mast:
            # Preserve surrounding whitespace
            _set_text(mast, mast_val)

    # Stories
    all_stories = data.get("stories", [])
    for story_data in all_stories:
        idx = story_data.get("index", -1)

        if idx == 0:
            # Feature story
            feature = _find_feature_story(soup)
            cat = (story_data.get("category") or "").strip()
            if cat and "category" in feature:
                _set_text(feature["category"], cat)

            hl = (story_data.get("headline") or "").strip()
            if hl and "headline" in feature:
                _set_text(feature["headline"], hl)

            summ = (story_data.get("summary") or "").strip()
            if summ and "summary" in feature:
                _set_text(feature["summary"], summ)

            img_url = (story_data.get("image") or "").strip()
            if img_url and img_url.startswith(("http://", "https://")) and "image" in feature:
                feature["image"]["src"] = img_url

            link = (story_data.get("link") or "").strip()
            if link and "link" in feature:
                feature["link"]["href"] = link

        elif idx in (1, 2):
            # Twin stories
            twins = _find_twin_stories(soup)
            tw_idx = idx - 1
            if tw_idx < len(twins):
                tw = twins[tw_idx]
                cat = (story_data.get("category") or "").strip()
                if cat and "category" in tw:
                    _set_text(tw["category"], cat)

                hl = (story_data.get("headline") or "").strip()
                if hl and "headline" in tw:
                    _set_text(tw["headline"], hl)

                summ = (story_data.get("summary") or "").strip()
                if summ and "summary" in tw:
                    _set_text(tw["summary"], summ)

                img_url = (story_data.get("image") or "").strip()
                if img_url and img_url.startswith(("http://", "https://")) and "image" in tw:
                    tw["image"]["src"] = img_url

                link = (story_data.get("link") or "").strip()
                if link and "link" in tw:
                    tw["link"]["href"] = link

        elif idx in (3, 4):
            # Compact stories
            compacts = _find_compact_stories(soup)
            c_idx = idx - 3
            if c_idx < len(compacts):
                c = compacts[c_idx]
                cat = (story_data.get("category") or "").strip()
                if cat and "category" in c:
                    _set_text(c["category"], cat)

                hl = (story_data.get("headline") or "").strip()
                if hl and "headline" in c:
                    _set_text(c["headline"], hl)

                summ = (story_data.get("summary") or "").strip()
                if summ and "summary" in c:
                    _set_text(c["summary"], summ)

                img_url = (story_data.get("image") or "").strip()
                if img_url and img_url.startswith(("http://", "https://")) and "image" in c:
                    c["image"]["src"] = img_url

                link = (story_data.get("link") or "").strip()
                if link and "link" in c:
                    c["link"]["href"] = link

    # Markets
    markets_data = data.get("markets", [])
    if markets_data:
        # Find market cells
        dark_section = None
        for td in soup.find_all("td"):
            style = td.get("style", "")
            if "background:#0f0f0f" in style:
                dark_section = td
                break

        if dark_section:
            stat_cells = []
            for td in dark_section.find_all("td"):
                width = td.get("width", "")
                valign = td.get("valign", "")
                if width == "25%" and valign == "top":
                    stat_cells.append(td)

            for i, mkt in enumerate(markets_data):
                if i >= len(stat_cells):
                    break
                cell = stat_cells[i]
                divs = cell.find_all("div")
                if len(divs) >= 3:
                    label = (mkt.get("label") or "").strip()
                    if label:
                        _set_text(divs[0], label)
                    value = (mkt.get("value") or "").strip()
                    if value:
                        _set_text(divs[1], value)
                    positive = mkt.get("positive", True)
                    pct_raw = (mkt.get("pct") or "").strip().replace("%", "")
                    try:
                        pct_float = float(pct_raw)
                    except ValueError:
                        pct_float = 0.0
                    value_str = value or divs[1].get_text().strip()
                    change_str = _format_change_str(label or divs[0].get_text().strip(), value_str, pct_float, positive)
                    _set_text(divs[2], change_str)
                    color = "#4caf7a" if positive else "#e07a6b"
                    existing_style = divs[2].get("style", "")
                    divs[2]["style"] = re.sub(r'color:#[0-9a-fA-F]{6}', f'color:{color}', existing_style)

    # Weather
    weather_data = data.get("weather", {})
    if weather_data:
        loc = (weather_data.get("location") or "").strip()
        t_desc = (weather_data.get("today_desc") or "").strip()
        t_high = (weather_data.get("today_high") or "").strip()
        t_low = (weather_data.get("today_low") or "").strip()

        if loc:
            for div in soup.find_all("div"):
                style = div.get("style", "")
                if "letter-spacing:3px" in style and "color:#8b2a1f" in style:
                    text = div.get_text()
                    if "·" in text or "Weather" in text:
                        _set_text(div, f"{loc}\xa0·\xa0Today's Weather")
                        break

        if t_desc:
            desc_div = soup.find(class_="weather-desc-today")
            if desc_div:
                _set_text(desc_div, t_desc)

        if t_high:
            high_span = soup.find(class_="weather-high-today")
            if high_span:
                _set_text(high_span, f"{t_high}°")

        if t_low:
            low_span = soup.find(class_="weather-low-today")
            if low_span:
                _set_text(low_span, f"{t_low}°")

    return str(soup)


# ── Routes ────────────────────────────────────────────────────────────────────

@day15_editor_bp.route("/")
def editor():
    return render_template("editor_day15.html", api_prefix="/day15-editor")


@day15_editor_bp.route("/api/fields")
def api_fields():
    return jsonify(parse_fields(_current_html))


@day15_editor_bp.route("/api/update", methods=["POST"])
def api_update():
    global _current_html
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON body"}), 400
    _current_html = update_html(_current_html, data)
    return jsonify({"success": True, "html": _current_html})


@day15_editor_bp.route("/api/preview")
def api_preview():
    return Response(_current_html, mimetype="text/html; charset=utf-8")


@day15_editor_bp.route("/api/export")
def api_export():
    buf = io.BytesIO(_current_html.encode("utf-8"))
    return send_file(
        buf,
        as_attachment=True,
        download_name="newsband_day15_newsletter.html",
        mimetype="text/html",
    )


@day15_editor_bp.route("/api/export_zip")
def api_export_zip():
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("newsband_day15_newsletter.html", _current_html.encode("utf-8"))
    buf.seek(0)
    return send_file(
        buf,
        as_attachment=True,
        download_name="newsband_day15_newsletter.zip",
        mimetype="application/zip",
    )


@day15_editor_bp.route("/api/markets/fetch")
def api_markets_fetch():
    try:
        def fetch_mumbai_gold():
            """
            Fetch Mumbai 24K gold price.
            Primary:   goodreturns.in (Mumbai-specific)
            Fallback1: goodreturns.in (national)
            Fallback2: Yahoo Finance GC=F (COMEX gold) converted to INR/10g
            """
            import os
            import requests as _req
            from bs4 import BeautifulSoup as _BS
            from datetime import datetime, timedelta
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"}

            # Fallback 1: goodreturns.in Mumbai
            try:
                url = "https://www.goodreturns.in/gold-rates/mumbai.html"
                resp = _req.get(url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    soup = _BS(resp.text, 'html.parser')
                    tables = soup.find_all('table')
                    if tables:
                        table = tables[0]
                        for tr in table.find_all('tr'):
                            cols = [td.get_text(strip=True) for td in tr.find_all(['th', 'td'])]
                            if len(cols) >= 3 and cols[0] == '10':
                                today_str = cols[1].replace('₹', '').replace(',', '').strip()
                                yday_str = cols[2].replace('₹', '').replace(',', '').strip()
                                if today_str and today_str != 'N/A' and yday_str and yday_str != 'N/A':
                                    today_val, yday_val = float(today_str), float(yday_str)
                                    if today_val > 0 and yday_val > 0:
                                        print("DEBUG [Gold]: goodreturns.in Mumbai -> success")
                                        return today_val, yday_val
                print("DEBUG [Gold]: goodreturns.in Mumbai returned N/A, trying fallback...")
            except Exception as e:
                print(f"DEBUG [Gold]: goodreturns.in Mumbai failed ({e}), trying fallback...")

            # Fallback 2: goodreturns.in national
            try:
                url2 = "https://www.goodreturns.in/gold-rates/"
                resp2 = _req.get(url2, headers=headers, timeout=10)
                if resp2.status_code == 200:
                    soup2 = _BS(resp2.text, 'html.parser')
                    tables2 = soup2.find_all('table')
                    if tables2:
                        for tr in tables2[0].find_all('tr'):
                            cols = [td.get_text(strip=True) for td in tr.find_all(['th', 'td'])]
                            if len(cols) >= 3 and cols[0] == '10':
                                today_str = cols[1].replace('₹', '').replace(',', '').strip()
                                yday_str = cols[2].replace('₹', '').replace(',', '').strip()
                                if today_str and today_str != 'N/A' and yday_str and yday_str != 'N/A':
                                    today_val, yday_val = float(today_str), float(yday_str)
                                    if today_val > 0 and yday_val > 0:
                                        print("DEBUG [Gold]: goodreturns.in national -> success")
                                        return today_val, yday_val
            except Exception as e:
                print(f"DEBUG [Gold]: goodreturns.in national failed ({e})")

            # Fallback 3: Yahoo Finance COMEX (GC=F) + USD/INR conversion
            # 1 troy oz = 31.1035g -> price_inr_per_10g = (gold_usd/31.1035)*10*usd_inr
            try:
                import requests
                hdrs = {"User-Agent": "Mozilla/5.0"}
                gold_resp = requests.get("https://query2.finance.yahoo.com/v8/finance/chart/GC=F?interval=1d&range=5d", headers=hdrs, timeout=10)
                usd_resp = requests.get("https://query2.finance.yahoo.com/v8/finance/chart/INR=X?interval=1d&range=5d", headers=hdrs, timeout=10)
                if gold_resp.status_code == 200 and usd_resp.status_code == 200:
                    gold_closes = [c for c in gold_resp.json()['chart']['result'][0]['indicators']['quote'][0]['close'] if c is not None]
                    usd_closes = [c for c in usd_resp.json()['chart']['result'][0]['indicators']['quote'][0]['close'] if c is not None]
                    if len(gold_closes) >= 2 and len(usd_closes) >= 1:
                        usd_inr = usd_closes[-1]
                        today_inr = (gold_closes[-1] / 31.1035) * 10 * usd_inr
                        prev_inr = (gold_closes[-2] / 31.1035) * 10 * usd_inr
                        print(f"DEBUG [Gold]: COMEX fallback -> INR {today_inr:.0f}/10g")
                        return round(today_inr), round(prev_inr)
            except Exception as e:
                print(f"DEBUG [Gold]: COMEX fallback failed ({e})")

            return None, None

        def fetch_usd_inr():
            """
            Fetch USD/INR exchange rate.
            Primary:   Frankfurter API (ECB daily rates, free, reliable)
            Fallback:  Yahoo Finance INR=X
            """
            import requests
            from datetime import datetime, timedelta
            headers = {"User-Agent": "Mozilla/5.0"}

            try:
                resp = requests.get("https://api.frankfurter.app/latest?from=USD&to=INR", headers=headers, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    today_rate = float(data['rates']['INR'])
                    today_date_str = data['date']
                    today_dt = datetime.strptime(today_date_str, "%Y-%m-%d")
                    prev_dt = today_dt - timedelta(days=1)
                    resp_prev = requests.get(
                        f"https://api.frankfurter.app/{prev_dt.strftime('%Y-%m-%d')}?from=USD&to=INR",
                        headers=headers, timeout=10
                    )
                    if resp_prev.status_code == 200:
                        prev_rate = float(resp_prev.json()['rates']['INR'])
                        print(f"DEBUG [USD/INR]: Frankfurter -> {today_rate:.2f}")
                        return today_rate, prev_rate
            except Exception as e:
                print(f"DEBUG [USD/INR]: Frankfurter failed ({e}), trying Yahoo...")

            try:
                url = "https://query2.finance.yahoo.com/v8/finance/chart/INR=X?interval=1d&range=5d"
                resp = requests.get(url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    closes = [c for c in resp.json()['chart']['result'][0]['indicators']['quote'][0]['close'] if c is not None]
                    if len(closes) >= 2:
                        return float(closes[-1]), float(closes[-2])
            except Exception:
                pass
            return None, None

        def fetch_two(sym):
            import requests
            url = f"https://query2.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=5d"
            headers = {"User-Agent": "Mozilla/5.0"}
            try:
                resp = requests.get(url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    result = data['chart']['result'][0]
                    closes = result['indicators']['quote'][0]['close']
                    valid_closes = [c for c in closes if c is not None]
                    if len(valid_closes) >= 2:
                        return float(valid_closes[-1]), float(valid_closes[-2])
            except Exception:
                pass
            return None, None

        def build_entry(now, prev, label, value_fmt):
            if now is None or prev is None:
                return {"label": label, "value": "N/A", "pct": "0.00", "positive": True}
            chg = now - prev
            pct = (chg / prev) * 100
            return {"label": label, "value": value_fmt(now), "pct": f"{abs(pct):.2f}", "positive": chg >= 0}

        s_now, s_prev = fetch_two("^BSESN")
        n_now, n_prev = fetch_two("^NSEI")
        u_now, u_prev = fetch_usd_inr()
        g_now, g_prev = fetch_mumbai_gold()

        markets = [
            build_entry(s_now, s_prev, "Sensex",                   lambda v: f"{int(round(v)):,}"),
            build_entry(n_now, n_prev, "Nifty 50",                  lambda v: f"{int(round(v)):,}"),
            build_entry(u_now, u_prev, "USD / INR",                 lambda v: f"{v:.2f}"),
            build_entry(g_now, g_prev, "Gold 24K (Mumbai) ₹/10g",  lambda v: f"{int(round(v)):,}"),
        ]
        return jsonify({"markets": markets})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@day15_editor_bp.route("/api/reset", methods=["POST"])
def api_reset():
    global _current_html
    _current_html = BASE_HTML
    return jsonify({"success": True})


@day15_editor_bp.route("/api/weather/fetch")
def api_weather_fetch():
    import requests as _req
    location = request.args.get("location", "Navi Mumbai").strip() or "Navi Mumbai"
    try:
        hdrs = {"User-Agent": "Mozilla/5.0 (Newsband/1.0; +https://newsband.in)"}

        # Geocode via Nominatim
        geo_resp = _req.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": location, "format": "json", "limit": 1},
            headers=hdrs, timeout=8,
        )
        geo_data = geo_resp.json() if geo_resp.status_code == 200 else []
        if not geo_data:
            return jsonify({"error": f"Could not geocode '{location}'"}), 400
        lat, lon = geo_data[0]["lat"], geo_data[0]["lon"]

        # Fetch from Open-Meteo (free, no API key)
        wx_resp = _req.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat, "longitude": lon,
                "daily": "temperature_2m_max,temperature_2m_min,weather_code",
                "timezone": "auto", "forecast_days": 2,
            },
            headers=hdrs, timeout=8,
        )
        if wx_resp.status_code != 200:
            return jsonify({"error": "Weather API unavailable"}), 500

        daily = wx_resp.json().get("daily", {})
        maxtemps = daily.get("temperature_2m_max", [None, None])
        mintemps = daily.get("temperature_2m_min", [None, None])
        codes = daily.get("weather_code") or daily.get("weathercode", [2, 2])

        # index 1 = tomorrow (newsletter is scheduled for the next day)
        wmo = int(codes[1]) if len(codes) > 1 else 2
        desc, _ = _WMO_CODES.get(wmo, ("Partly cloudy", "⛅"))
        tmrw_high = maxtemps[1] if len(maxtemps) > 1 else None
        tmrw_low  = mintemps[1] if len(mintemps) > 1 else None
        today_high = str(round(tmrw_high)) if tmrw_high is not None else "—"
        today_low  = str(round(tmrw_low))  if tmrw_low  is not None else "—"

        print(f"DEBUG [Weather/Day15]: {location} tomorrow → {desc} {today_high}°/{today_low}°C")
        return jsonify({
            "weather": {
                "location": location,
                "today_desc": desc,
                "today_high": today_high,
                "today_low": today_low,
            }
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@day15_editor_bp.route("/api/import_json", methods=["POST"])
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
    test_app.register_blueprint(day15_editor_bp)
    test_app.run(debug=True, host="0.0.0.0", port=5000)
