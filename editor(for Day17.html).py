"""
Newsband Newsletter Editor — Day17 Flask Backend
Uses BeautifulSoup4 for controlled, field-level HTML editing.
Footer, layout structure, CSS, and logo are strictly locked.
"""

import io
import re
from urllib.parse import quote as _url_quote
from flask import Blueprint, request, jsonify, render_template, send_file, Response
from bs4 import BeautifulSoup, NavigableString

# WMO weather code → (description, icon character)
_WMO_CODES = {
    0:  ("Clear sky",              "☀"),
    1:  ("Mainly clear",           "☀"),
    2:  ("Partly cloudy",          "⛅"),
    3:  ("Overcast",               "☁"),
    45: ("Foggy",                  "🌫"),
    48: ("Icy fog",                "🌫"),
    51: ("Light drizzle",          "☔"),
    53: ("Drizzle",                "☔"),
    55: ("Dense drizzle",          "☔"),
    61: ("Slight rain",            "☔"),
    63: ("Moderate rain",          "☔"),
    65: ("Heavy rain",             "☔"),
    71: ("Light snow",             "❄"),
    73: ("Snow",                   "❄"),
    75: ("Heavy snow",             "❄"),
    77: ("Snow grains",            "❄"),
    80: ("Rain showers",           "☔"),
    81: ("Moderate showers",       "☔"),
    82: ("Heavy showers",          "☔"),
    85: ("Snow showers",           "❄"),
    86: ("Heavy snow showers",     "❄"),
    95: ("Thunderstorm",           "⛈"),
    96: ("Thunderstorm with hail", "⛈"),
    99: ("Heavy thunderstorm",     "⛈"),
}

day17_editor_bp = Blueprint('day17_editor', __name__)

# ── Load base template once at startup ────────────────────────────────────────
with open("Day17.html", "r", encoding="utf-8") as f:
    BASE_HTML = f.read()
    print(f"DEBUG [Day17]: BASE_HTML length: {len(BASE_HTML)}")

_current_html = BASE_HTML   # mutable working copy


# ── Helpers ───────────────────────────────────────────────────────────────────

def _set_text(tag, text: str):
    """Safely replace all children of a tag with a single plain-text node."""
    tag.clear()
    tag.append(NavigableString(text))


def _find_header_date(soup):
    for p in soup.find_all("p"):
        text = p.get_text()
        if "Date:" in text:
            return p
    return None


def _find_header_rni(soup):
    for p in soup.find_all("p"):
        text = p.get_text()
        if "RNI:" in text:
            return p
    return None


# ── Story finders ─────────────────────────────────────────────────────────────

def _find_s1(soup):
    result = {}
    # S1 Image
    img = soup.find("img", alt="Hero Image")
    if img:
        result["image"] = img
    # S1 Category
    for td in soup.find_all("td"):
        if "background-color: #c8102e" in td.get("style", "") or td.get("bgcolor") == "#c8102e":
            span = td.find("span")
            if span:
                result["category"] = span
                break
    # S1 Headline
    for p in soup.find_all("p"):
        style = p.get("style", "")
        if "font-size: 22px" in style:
            result["headline"] = p
            break
    # S1 Summary
    for p in soup.find_all("p"):
        style = p.get("style", "")
        if "font-size: 14px" in style and "color: #4a4a4a" in style:
            result["summary"] = p
            break
            
    # S1 Links (Both image link and content link)
    links = []
    if img:
        p_a = img.find_parent("a")
        if p_a:
            links.append(p_a)
    for a in soup.find_all("a"):
        style = a.get("style", "")
        if "color: #111111" in style and "display: block" in style:
            links.append(a)
            break
    if links:
        result["links"] = links
        
    return result


def _find_s2_s3(soup):
    stories = []
    cells = soup.find_all("td", class_="two-col-cell")
    for i, cell in enumerate(cells[:2]):
        story = {}
        # The whole card is wrapped in a single <a>; no second <a> exists
        a_tags = cell.find_all("a")
        if a_tags:
            story["links"] = a_tags
        # Image
        img = cell.find("img")
        if img:
            story["image"] = img
        # Paragraphs are inside the one card <a> (index 0)
        if len(a_tags) >= 1:
            p_tags = a_tags[0].find_all("p")
            if len(p_tags) >= 3:
                story["category"] = p_tags[0]
                story["headline"] = p_tags[1]
                story["summary"] = p_tags[2]
        stories.append(story)
    return stories


def _find_s4_s5(soup):
    stories = []
    thumbs = soup.find_all("td", class_="horiz-thumb")
    contents = soup.find_all("td", class_="horiz-content")
    for i in range(min(len(thumbs), len(contents))):
        story = {}
        t_cell = thumbs[i]
        c_cell = contents[i]

        # The <a> wraps the outer table, not the inner cells — walk up to find it
        links = []
        outer_a = t_cell.find_parent("a")
        if outer_a:
            links.append(outer_a)
        story["links"] = links

        # Image cell + img
        story["thumb_cell"] = t_cell
        img = t_cell.find("img")
        if img:
            story["image"] = img

        # Paragraphs are directly inside the content cell (no inner <a>)
        p_tags = c_cell.find_all("p")
        if len(p_tags) >= 3:
            story["category"] = p_tags[0]
            story["headline"] = p_tags[1]
            story["summary"] = p_tags[2]
        stories.append(story)
    return stories


def _find_weather_data(soup):
    weather = {}

    # Description / temps via class attributes
    desc_today = soup.find(class_="weather-desc-today")
    if desc_today:
        weather["today_desc"] = desc_today.get_text().strip()

    high_today = soup.find(class_="weather-high-today")
    if high_today:
        m = re.search(r'\d+', high_today.get_text())
        if m:
            weather["today_high"] = m.group()

    low_today = soup.find(class_="weather-low-today")
    if low_today:
        m = re.search(r'\d+', low_today.get_text())
        if m:
            weather["today_low"] = m.group()

    # Location + icon: find weather container
    for tag in soup.find_all(["table", "td"]):
        style_val = tag.get("style", "")
        if "background-color: #fdf8ef" in style_val or tag.get("bgcolor") == "#fdf8ef":
            # Location from "City · Today's Forecast" paragraph
            for p in tag.find_all("p"):
                text = p.get_text().strip()
                if "·" in text or "・" in text or "·" in text:
                    parts = re.split(r'\s*[·・·]\s*', text)
                    weather["location"] = parts[0].strip()
                    break
            # Icon from the large-font td
            for td in tag.find_all("td"):
                if "font-size: 30px" in td.get("style", ""):
                    icon_text = td.get_text().strip()
                    if icon_text:
                        weather["today_icon"] = icon_text
                    break
            break

    weather.setdefault("location", "Navi Mumbai")
    weather.setdefault("today_icon", "⛅")
    return weather


def _find_market_data(soup):
    markets = []
    stat_cells = soup.find_all("td", class_="ticker-cell")
    for cell in stat_cells:
        p_tags = cell.find_all("p")
        pct_span = cell.find("span", class_="mkt-pct")
        if len(p_tags) >= 3 and pct_span:
            style = pct_span.get("style", "")
            pct_text = pct_span.get_text().strip()
            positive = "color: #16a34a" in style or "▲" in pct_text
            pct_num = re.sub(r'[▲▼%+\-−\s]', '', pct_text)
            market = {
                "label": p_tags[0].get_text().strip(),
                "value": p_tags[2].get_text().strip(),
                "pct": pct_num,
                "positive": positive,
            }
            markets.append(market)
    return markets


def _format_abs_change(label: str, value_str: str, pct_float: float, positive: bool) -> str:
    sign = "+" if positive else "−"
    clean = value_str.replace("₹", "").replace("₹", "").replace(",", "").strip()
    try:
        value_num = float(clean)
    except Exception:
        return "N/A"
    abs_change = value_num * pct_float / 100
    label_lower = label.lower()
    if "gold" in label_lower:
        return f"{sign}₹{int(round(abs_change))}"
    elif "usd" in label_lower or "/" in label:
        return f"{sign}{abs(abs_change):.2f}"
    else:
        return f"{sign}{int(round(abs_change))} pts"


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
        # Default to tomorrow's date format or current parsed date
        result["date"] = date_div.get_text().replace("Date:", "").strip()

    # Header — RNI
    rni_div = _find_header_rni(soup)
    if rni_div:
        result["rni"] = rni_div.get_text().replace("RNI:", "").strip()

    # Stories
    stories = []

    # Story 0: Feature (S1)
    s1 = _find_s1(soup)
    s0 = {"index": 0, "type": "feature"}
    if "category" in s1:
        s0["category"] = s1["category"].get_text().strip()
    if "headline" in s1:
        s0["headline"] = s1["headline"].get_text().strip()
    if "summary" in s1:
        s0["summary"] = s1["summary"].get_text().strip()
    if "image" in s1:
        s0["image"] = s1["image"].get("src", "")
    if "links" in s1 and s1["links"]:
        s0["link"] = s1["links"][0].get("href", "")
    stories.append(s0)

    # Stories 1-2: S2-S3
    twins = _find_s2_s3(soup)
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
        if "links" in tw and tw["links"]:
            s["link"] = tw["links"][0].get("href", "")
        stories.append(s)

    # Stories 3-4: S4-S5
    horiz = _find_s4_s5(soup)
    for i, hz in enumerate(horiz):
        s = {"index": i + 3, "type": "compact"}
        if "category" in hz:
            s["category"] = hz["category"].get_text().strip()
        if "headline" in hz:
            s["headline"] = hz["headline"].get_text().strip()
        if "summary" in hz:
            s["summary"] = hz["summary"].get_text().strip()
        if "image" in hz:
            s["image"] = hz["image"].get("src", "")
        if "links" in hz and hz["links"]:
            s["link"] = hz["links"][0].get("href", "")
        stories.append(s)

    result["stories"] = stories

    # Weather
    result["weather"] = _find_weather_data(soup)

    # Markets
    result["markets"] = _find_market_data(soup)

    return result


def update_html(html: str, data: dict) -> str:
    soup = BeautifulSoup(html, "html.parser")

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
    all_stories = data.get("stories", [])
    for story_data in all_stories:
        idx = story_data.get("index", -1)

        if idx == 0:
            feature = _find_s1(soup)
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
            if link and "links" in feature:
                for l in feature["links"]:
                    l["href"] = link

        elif idx in (1, 2):
            twins = _find_s2_s3(soup)
            twin_idx = idx - 1
            if twin_idx < len(twins):
                tw = twins[twin_idx]
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
                if link and "links" in tw:
                    for l in tw["links"]:
                        l["href"] = link

        elif idx in (3, 4):
            horiz = _find_s4_s5(soup)
            hz_idx = idx - 3
            if hz_idx < len(horiz):
                hz = horiz[hz_idx]
                cat = (story_data.get("category") or "").strip()
                if cat and "category" in hz:
                    _set_text(hz["category"], cat)

                hl = (story_data.get("headline") or "").strip()
                if hl and "headline" in hz:
                    _set_text(hz["headline"], hl)

                summ = (story_data.get("summary") or "").strip()
                if summ and "summary" in hz:
                    _set_text(hz["summary"], summ)

                img_url = (story_data.get("image") or "").strip()
                if img_url and img_url.startswith(("http://", "https://")) and "image" in hz:
                    img_tag = hz["image"]
                    img_tag["src"] = img_url
                    img_tag["width"] = "220"
                    img_tag["height"] = "140"
                    img_tag["style"] = "display: block; border: 0; outline: none; width: 220px; height: 140px; object-fit: cover; object-position: center;"
                    if "thumb_cell" in hz:
                        tc = hz["thumb_cell"]
                        tc["height"] = "140"
                        tc["style"] = "background-color: #ffffff; padding: 0; width: 220px; height: 140px;"
                        a_tag = tc.find("a")
                        if a_tag:
                            a_tag["style"] = "text-decoration: none; display: block; font-size: 0; line-height: 0;"

                link = (story_data.get("link") or "").strip()
                if link and "links" in hz:
                    for l in hz["links"]:
                        l["href"] = link

    # Weather
    weather_data = data.get("weather", {})
    if weather_data:
        weather_container = None
        for tag in soup.find_all("table"):
            style_val = tag.get("style", "")
            if "background-color: #fdf8ef" in style_val or tag.get("bgcolor") == "#fdf8ef":
                weather_container = tag
                break
        if weather_container:
            loc = (weather_data.get("location") or "").strip()
            t_desc = (weather_data.get("today_desc") or "").strip()
            t_high = (weather_data.get("today_high") or "").strip()
            t_low = (weather_data.get("today_low") or "").strip()
            t_icon = (weather_data.get("today_icon") or "⛅").strip() or "⛅"

            new_tr_html = f"""
                                            <tr>
                                                <td style="padding: 14px 14px 14px 18px; vertical-align: middle;" valign="middle">
                                                    <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%">
                                                        <tr>
                                                            <td style="font-size: 30px; line-height: 30px; padding-right: 12px; vertical-align: middle; width: 38px;" valign="middle" width="38">{t_icon}</td>
                                                            <td style="vertical-align: middle;" valign="middle">
                                                                <p style="margin: 0 0 3px 0; font-family: Arial, Helvetica, sans-serif; font-size: 9px; font-weight: bold; color: #b8860b; letter-spacing: 1.5px; text-transform: uppercase; line-height: 13px;">{loc} &#183; Today's Forecast</p>
                                                                <p class="weather-desc-today" style="margin: 0; font-family: Arial, Helvetica, sans-serif; font-size: 12px; color: #6b5c3e; line-height: 17px;">{t_desc}</p>
                                                            </td>
                                                            <td style="vertical-align: middle; text-align: right; padding-left: 16px; white-space: nowrap;" valign="middle" align="right">
                                                                <p style="margin: 0 0 2px 0; font-family: Arial, Helvetica, sans-serif; font-size: 8px; font-weight: bold; letter-spacing: 2px; color: #b8860b; text-transform: uppercase; line-height: 11px; text-align: right;">Expected</p>
                                                                <p style="margin: 0 0 2px 0; line-height: 22px; text-align: right;">
                                                                    <span class="weather-high-today" style="font-family: 'Courier New', Courier, monospace; font-size: 18px; font-weight: bold; color: #c8102e;">{t_high}&#176;</span>
                                                                    <span style="font-family: Arial, Helvetica, sans-serif; font-size: 12px; color: #aaaaaa;"> / </span>
                                                                    <span class="weather-low-today" style="font-family: 'Courier New', Courier, monospace; font-size: 18px; font-weight: bold; color: #1e40af;">{t_low}&#176;</span>
                                                                    <span style="font-family: Arial, Helvetica, sans-serif; font-size: 9px; color: #999999;"> c</span>
                                                                </p>
                                                                <p style="margin: 0; font-family: Arial, Helvetica, sans-serif; font-size: 8px; color: #c4a85a; letter-spacing: 1px; text-align: right; line-height: 11px;">High &#183; Low</p>
                                                            </td>
                                                        </tr>
                                                    </table>
                                                </td>
                                            </tr>
            """
            new_tr_soup = BeautifulSoup(new_tr_html, "html.parser")
            weather_container.clear()
            weather_container.append(new_tr_soup)

    # Markets
    markets_data = data.get("markets", [])
    if markets_data:
        stat_cells = soup.find_all("td", class_="ticker-cell")
        for i, mkt in enumerate(markets_data):
            if i >= len(stat_cells):
                break
            cell = stat_cells[i]
            p_tags = cell.find_all("p")
            if len(p_tags) < 3:
                continue

            label = (mkt.get("label") or "").strip()
            if label:
                _set_text(p_tags[0], label)
            value = (mkt.get("value") or "").strip()
            if value:
                _set_text(p_tags[2], value)

            pct_raw = (mkt.get("pct") or "").strip().replace("%", "")
            positive = mkt.get("positive", True)
            arrow = "▲" if positive else "▼"
            color = "#16a34a" if positive else "#dc2626"
            bg_color = "#edfcf2" if positive else "#fef2f2"

            def _apply_badge(span):
                if not span:
                    return
                new_style = re.sub(r'color:\s*#[0-9a-fA-F]{6}', f'color: {color}', span.get("style", ""))
                span["style"] = new_style
                parent_td = span.find_parent("td")
                if parent_td:
                    parent_td["bgcolor"] = bg_color
                    parent_td["style"] = re.sub(
                        r'background-color:\s*#[0-9a-fA-F]{6}',
                        f'background-color: {bg_color}',
                        parent_td.get("style", "")
                    )

            pct_span = cell.find("span", class_="mkt-pct")
            if pct_span and pct_raw:
                _set_text(pct_span, f"{arrow} {pct_raw}%")
                _apply_badge(pct_span)

            abs_span = cell.find("span", class_="mkt-abs")
            if abs_span and pct_raw:
                try:
                    pct_float = float(pct_raw)
                except ValueError:
                    pct_float = 0.0
                abs_text = _format_abs_change(label or p_tags[0].get_text().strip(), value or p_tags[2].get_text().strip(), pct_float, positive)
                _set_text(abs_span, abs_text)
                _apply_badge(abs_span)

    return str(soup)


# ── Routes ────────────────────────────────────────────────────────────────────

@day17_editor_bp.route("/")
def editor():
    return render_template("editor_day17.html", api_prefix="/day17-editor")


@day17_editor_bp.route("/api/fields")
def api_fields():
    return jsonify(parse_fields(_current_html))


@day17_editor_bp.route("/api/update", methods=["POST"])
def api_update():
    global _current_html
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON body"}), 400
    _current_html = update_html(_current_html, data)
    return jsonify({"success": True, "html": _current_html})


@day17_editor_bp.route("/api/preview")
def api_preview():
    return Response(_current_html, mimetype="text/html; charset=utf-8")


@day17_editor_bp.route("/api/export")
def api_export():
    buf = io.BytesIO(_current_html.encode("utf-8"))
    return send_file(
        buf,
        as_attachment=True,
        download_name="newsband_day17_newsletter.html",
        mimetype="text/html",
    )


@day17_editor_bp.route("/api/export_zip")
def api_export_zip():
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("newsband_day17_newsletter.html", _current_html.encode("utf-8"))
    buf.seek(0)
    return send_file(
        buf,
        as_attachment=True,
        download_name="newsband_day17_newsletter.zip",
        mimetype="application/zip",
    )


@day17_editor_bp.route("/api/weather/fetch")
def api_weather_fetch():
    import requests as _req
    location = request.args.get("location", "Navi Mumbai").strip()

    res_data = {
        "location": location,
        "today_desc": "Partly cloudy",
        "today_high": "35",
        "today_low": "27",
        "today_icon": "⛅",
    }

    def clean_temp(val, default="27"):
        if val is None:
            return default
        try:
            n = int(round(float(str(val))))
            if "mumbai" in location.lower() and n < 24:
                return "24"
            return str(n)
        except Exception:
            return default

    # 1. Open-Meteo (geocoding + forecast — free, no key required)
    try:
        hdrs = {"User-Agent": "Mozilla/5.0"}
        geo_url = (
            f"https://geocoding-api.open-meteo.com/v1/search"
            f"?name={_url_quote(location)}&count=1&language=en&format=json"
        )
        geo_resp = _req.get(geo_url, headers=hdrs, timeout=8)
        if geo_resp.status_code == 200:
            geo_results = geo_resp.json().get("results", [])
            if geo_results:
                r = geo_results[0]
                lat, lon = r["latitude"], r["longitude"]
                place_name = r.get("name", location)

                wx_url = (
                    f"https://api.open-meteo.com/v1/forecast"
                    f"?latitude={lat}&longitude={lon}"
                    f"&daily=temperature_2m_max,temperature_2m_min,weather_code"
                    f"&timezone=auto&forecast_days=2"
                )
                wx_resp = _req.get(wx_url, headers=hdrs, timeout=8)
                if wx_resp.status_code == 200:
                    daily = wx_resp.json().get("daily", {})
                    maxtemps = daily.get("temperature_2m_max", [])
                    mintemps = daily.get("temperature_2m_min", [])
                    # Open-Meteo renamed weathercode → weather_code; support both
                    codes = daily.get("weather_code") or daily.get("weathercode", [])
                    if maxtemps:
                        wmo = int(codes[0]) if codes else 2
                        desc, icon = _WMO_CODES.get(wmo, ("Partly cloudy", "⛅"))
                        res_data.update({
                            "location": place_name,
                            "today_desc": desc,
                            "today_high": clean_temp(maxtemps[0], "35"),
                            "today_low": clean_temp(mintemps[0] if mintemps else None, "27"),
                            "today_icon": icon,
                        })
                        print(f"DEBUG [Weather]: Open-Meteo OK → {place_name} {desc} {maxtemps[0]}/{mintemps[0] if mintemps else '?'}°C")
                        return jsonify(res_data)
    except Exception as e:
        print(f"DEBUG [Weather]: Open-Meteo failed ({e}), trying wttr.in…")

    # 2. Fallback — wttr.in JSON API
    try:
        loc_query = location.replace(" ", "_")
        url = f"https://wttr.in/{loc_query}?format=j1"
        hdrs = {"User-Agent": "Mozilla/5.0"}
        resp = _req.get(url, headers=hdrs, timeout=8)
        if resp.status_code == 200:
            weather_days = resp.json().get("weather", [])
            if weather_days:
                day_data = weather_days[0]  # index 0 = today
                res_data["today_high"] = clean_temp(day_data.get("maxtempC"), "35")
                res_data["today_low"] = clean_temp(day_data.get("mintempC"), "27")

                hourly = day_data.get("hourly", [])
                desc, wmo_code = "Partly cloudy", None
                if hourly:
                    mid = hourly[len(hourly) // 2]
                    desc_list = mid.get("weatherDesc", [])
                    if desc_list:
                        desc = desc_list[0].get("value", desc)
                    raw_code = mid.get("weatherCode")
                    if raw_code is not None:
                        wmo_code = int(raw_code)

                res_data["today_desc"] = desc
                if wmo_code is not None:
                    _, icon = _WMO_CODES.get(wmo_code, ("", "⛅"))
                    res_data["today_icon"] = icon

                print(f"DEBUG [Weather]: wttr.in OK → {location} {desc}")
                return jsonify(res_data)
    except Exception as e:
        print(f"DEBUG [Weather]: wttr.in failed ({e})")

    # Both failed — return defaults so the editor still gets a usable response
    res_data["warning"] = "Live fetch unavailable; showing defaults."
    return jsonify(res_data), 200


@day17_editor_bp.route("/api/markets/fetch")
def api_markets_fetch():
    try:
        def fetch_mumbai_gold():
            """
            Fetch Mumbai 24K gold price.
            Primary:   goodreturns.in (Mumbai-specific)
            Fallback1: goodreturns.in (national)
            Fallback2: Yahoo Finance GC=F (COMEX gold) converted to INR/10g
            """
            import requests as _req
            from bs4 import BeautifulSoup as _BS
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
            try:
                import requests
                resp = requests.get("https://api.frankfurter.dev/v1/latest?base=USD&symbols=INR", timeout=10)
                if resp.status_code == 200:
                    rate = resp.json()['rates']['INR']
                    from datetime import datetime, timedelta
                    for idx in range(1, 5):
                        yday_str = (datetime.now() - timedelta(days=idx)).strftime('%Y-%m-%d')
                        y_resp = requests.get(f"https://api.frankfurter.dev/v1/{yday_str}?base=USD&symbols=INR", timeout=10)
                        if y_resp.status_code == 200:
                            y_rate = y_resp.json()['rates']['INR']
                            print(f"DEBUG [USD/INR]: Frankfurter -> today={rate}, yday={y_rate}")
                            return rate, y_rate
            except Exception as e:
                print(f"DEBUG [USD/INR]: Frankfurter failed ({e}), trying Yahoo...")

            # Yahoo fallback
            try:
                import requests
                hdrs = {"User-Agent": "Mozilla/5.0"}
                resp = requests.get("https://query2.finance.yahoo.com/v8/finance/chart/INR=X?interval=1d&range=5d", headers=hdrs, timeout=10)
                if resp.status_code == 200:
                    closes = [c for c in resp.json()['chart']['result'][0]['indicators']['quote'][0]['close'] if c is not None]
                    if len(closes) >= 2:
                        print(f"DEBUG [USD/INR]: Yahoo -> today={closes[-1]}, yday={closes[-2]}")
                        return closes[-1], closes[-2]
            except Exception as e:
                print(f"DEBUG [USD/INR]: Yahoo fallback failed ({e})")
            return None, None

        def fetch_two(sym):
            import requests
            url = f"https://query2.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=5d"
            headers = {"User-Agent": "Mozilla/5.0"}
            try:
                resp = requests.get(url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    result = resp.json()['chart']['result'][0]
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

        n_now, n_prev = fetch_two("^NSEI")
        s_now, s_prev = fetch_two("^BSESN")
        u_now, u_prev = fetch_usd_inr()
        g_now, g_prev = fetch_mumbai_gold()

        markets = [
            build_entry(n_now, n_prev, "Nifty 50",  lambda v: f"{v:,.2f}"),
            build_entry(s_now, s_prev, "Sensex",     lambda v: f"{int(round(v)):,}"),
            build_entry(u_now, u_prev, "USD / INR",  lambda v: f"{v:.2f}"),
            build_entry(g_now, g_prev, "Gold 24K",   lambda v: f"₹{int(round(v)):,}"),
        ]
        return jsonify({"markets": markets})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@day17_editor_bp.route("/api/reset", methods=["POST"])
def api_reset():
    global _current_html
    _current_html = BASE_HTML
    return jsonify({"success": True})


@day17_editor_bp.route("/api/import_json", methods=["POST"])
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
    from flask import Flask
    test_app = Flask(__name__, template_folder=".")
    test_app.register_blueprint(day17_editor_bp)
    test_app.run(debug=True, host="0.0.0.0", port=5000)
