"""
Newsband Newsletter Editor — Day9(2) Flask Backend
Uses BeautifulSoup4 for controlled, field-level HTML editing.
Footer, layout structure, CSS, and logo are strictly locked.

Based on editor(for Day9.html).py with market section support
adapted from editor(for Day12(2).html).py.
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

day9_2_editor_bp = Blueprint('day9_2_editor', __name__)

# ── Load base template once at startup ────────────────────────────────────────
with open("Day9(2).html", "r", encoding="utf-8") as f:
    BASE_HTML = f.read()
    print(f"DEBUG [Day9_2]: BASE_HTML length: {len(BASE_HTML)}")

_current_html = BASE_HTML   # mutable working copy


# ── Helpers ───────────────────────────────────────────────────────────────────

def _set_text(tag, text: str):
    """Safely replace all children of a tag with a single plain-text node."""
    tag.clear()
    tag.append(NavigableString(text))


def _find_header_date(soup):
    hdr = soup.find(id="header")
    if not hdr:
        # Fallback: search by style
        for div in soup.find_all("div"):
            style = div.get("style", "")
            if "color:#737373" in style and "font-weight:600" in style:
                text = div.get_text()
                if "Date:" in text:
                    return div
        return None
    return hdr.find("div", style=lambda s: s and "color:#737373" in s)


def _find_header_rni(soup):
    hdr = soup.find(id="header")
    if not hdr:
        # Fallback: search by style
        for div in soup.find_all("div"):
            style = div.get("style", "")
            if "color:#888888" in style and "font-size:9px" in style:
                text = div.get_text()
                if "RNI:" in text:
                    return div
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


# ── Market section helpers ────────────────────────────────────────────────────

def _find_market_data(soup):
    """
    Find the markets section data in Day9(2).html.
    The market section is a 1×4 dark ticker strip (background-color:#0f172a).
    Returns list of 4 dicts (Sensex, Nifty, USD/INR, Gold).
    """
    markets = []

    dark_container = None
    for tag in soup.find_all(["table", "td"]):
        if "background-color:#0f172a" in tag.get("style", ""):
            dark_container = tag
            break

    if not dark_container:
        return markets

    ticker_cells = [
        td for td in dark_container.find_all("td")
        if td.get("valign") == "top" and td.get("width") == "25%"
    ]

    for cell in ticker_cells:
        divs = cell.find_all("div")
        if len(divs) >= 3:
            change_text = divs[2].get_text().strip()
            positive = "color:#10b981" in divs[2].get("style", "")
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


# ── Weather section helpers ───────────────────────────────────────────────────

def _find_weather_data(soup):
    weather = {}

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

    for tag in soup.find_all(["table", "td"]):
        style_val = tag.get("style", "")
        if "background-color: #fdf8ef" in style_val or tag.get("bgcolor") == "#fdf8ef":
            for p in tag.find_all("p"):
                text = p.get_text().strip()
                if "·" in text or "·" in text:
                    parts = re.split(r'\s*[··]\s*', text)
                    weather["location"] = parts[0].strip()
                    break
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

        # Also update the outro date stamp (NEWSBAND · DD · MM · YYYY)
        # BS4 decodes &middot; to the actual · character (\u00b7)
        for td in soup.find_all("td"):
            txt = td.string
            if txt and "NEWSBAND" in txt and ("\u00b7" in txt or "·" in txt):
                try:
                    from datetime import datetime as _dt
                    parsed = _dt.strptime(date_val, "%B %d, %Y")
                    _set_text(
                        td,
                        f"NEWSBAND · {parsed.day:02d} · {parsed.month:02d} · {parsed.year}",
                    )
                except ValueError:
                    parts = date_val.split("/")
                    if len(parts) == 3:
                        try:
                            _set_text(
                                td,
                                f"NEWSBAND · {parts[0]} · {parts[1]} · {parts[2]}",
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

    # Markets
    markets_data = data.get("markets", [])
    if markets_data:
        dark_container = None
        for tag in soup.find_all(["table", "td"]):
            if "background-color:#0f172a" in tag.get("style", ""):
                dark_container = tag
                break

        if dark_container:
            ticker_cells = [
                td for td in dark_container.find_all("td")
                if td.get("valign") == "top" and td.get("width") == "25%"
            ]

            for i, mkt in enumerate(markets_data):
                if i >= len(ticker_cells):
                    break
                cell = ticker_cells[i]
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
                    color = "#10b981" if positive else "#ef4444"
                    existing_style = divs[2].get("style", "")
                    divs[2]["style"] = re.sub(
                        r'color:#[0-9a-fA-F]{6}', f'color:{color}', existing_style)

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
                                                                <p style="margin: 0 0 3px 0; font-family: 'Courier New', Courier, monospace; font-size: 9px; font-weight: bold; color: #b8860b; letter-spacing: 1.5px; text-transform: uppercase; line-height: 13px;">{loc} &#183; Today's Forecast</p>
                                                                <p class="weather-desc-today" style="margin: 0; font-family: Arial, Helvetica, sans-serif; font-size: 12px; color: #6b5c3e; line-height: 17px;">{t_desc}</p>
                                                            </td>
                                                            <td style="vertical-align: middle; text-align: right; padding-left: 16px; white-space: nowrap;" valign="middle" align="right">
                                                                <p style="margin: 0 0 2px 0; font-family: 'Courier New', Courier, monospace; font-size: 8px; font-weight: bold; letter-spacing: 2px; color: #b8860b; text-transform: uppercase; line-height: 11px; text-align: right;">Expected</p>
                                                                <p style="margin: 0 0 2px 0; line-height: 22px; text-align: right;">
                                                                    <span class="weather-high-today" style="font-family: 'Courier New', Courier, monospace; font-size: 18px; font-weight: bold; color: #b8532d;">{t_high}&#176;</span>
                                                                    <span style="font-family: Arial, Helvetica, sans-serif; font-size: 12px; color: #aaaaaa;"> / </span>
                                                                    <span class="weather-low-today" style="font-family: 'Courier New', Courier, monospace; font-size: 18px; font-weight: bold; color: #1e40af;">{t_low}&#176;</span>
                                                                    <span style="font-family: Arial, Helvetica, sans-serif; font-size: 9px; color: #999999;"> c</span>
                                                                </p>
                                                                <p style="margin: 0; font-family: 'Courier New', Courier, monospace; font-size: 8px; color: #c4a85a; letter-spacing: 1px; text-align: right; line-height: 11px;">High &#183; Low</p>
                                                            </td>
                                                        </tr>
                                                    </table>
                                                </td>
                                            </tr>
            """
            new_tr_soup = BeautifulSoup(new_tr_html, "html.parser")
            weather_container.clear()
            weather_container.append(new_tr_soup)

    return str(soup)


# ── Routes ────────────────────────────────────────────────────────────────────

@day9_2_editor_bp.route("/")
def editor():
    return render_template("editor_day9_2.html", api_prefix="/day9-2-editor")


@day9_2_editor_bp.route("/api/fields")
def api_fields():
    return jsonify(parse_fields(_current_html))


@day9_2_editor_bp.route("/api/update", methods=["POST"])
def api_update():
    global _current_html
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON body"}), 400
    _current_html = update_html(_current_html, data)
    return jsonify({"success": True, "html": _current_html})


@day9_2_editor_bp.route("/api/preview")
def api_preview():
    return Response(_current_html, mimetype="text/html; charset=utf-8")


@day9_2_editor_bp.route("/api/export")
def api_export():
    buf = io.BytesIO(_current_html.encode("utf-8"))
    return send_file(
        buf,
        as_attachment=True,
        download_name="newsband_day9_2_newsletter.html",
        mimetype="text/html",
    )


@day9_2_editor_bp.route("/api/weather/fetch")
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
                day_data = weather_days[0]
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

    res_data["warning"] = "Live fetch unavailable; showing defaults."
    return jsonify(res_data), 200


@day9_2_editor_bp.route("/api/markets/fetch")
def api_markets_fetch():
    """
    Fetch live market data from Yahoo Finance + gold from goodreturns.in
    with multiple fallback sources for gold prices.
    """
    try:
        def fetch_mumbai_gold():
            """
            Fetch Mumbai 24K gold price with multiple fallback sources.
            Primary:   goodreturns.in
            Fallback1: goodreturns.in gold-rates page (national)
            Fallback2: Yahoo Finance GC=F (COMEX gold) converted to INR/10g
            """
            import requests as _req
            from bs4 import BeautifulSoup as _BS
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"}

            # ── Primary: goodreturns.in ──────────────────────────────────────
            try:
                url = "https://www.goodreturns.in/gold-rates/mumbai.html"
                resp = _req.get(url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    soup = _BS(resp.text, 'html.parser')
                    tables = soup.find_all('table')
                    if tables:
                        table = tables[0]  # Table 0 = 24K
                        for tr in table.find_all('tr'):
                            cols = [td.get_text(strip=True) for td in tr.find_all(['th', 'td'])]
                            if len(cols) >= 3 and cols[0] == '10':
                                today_str = cols[1].replace('₹', '').replace(',', '').strip()
                                yday_str = cols[2].replace('₹', '').replace(',', '').strip()
                                if today_str and today_str != 'N/A' and yday_str and yday_str != 'N/A':
                                    today_val = float(today_str)
                                    yday_val = float(yday_str)
                                    if today_val > 0 and yday_val > 0:
                                        print("DEBUG [Gold]: goodreturns.in -> success")
                                        return today_val, yday_val
                    print("DEBUG [Gold]: goodreturns.in returned N/A or invalid data, trying fallback...")
            except Exception as e:
                print(f"DEBUG [Gold]: goodreturns.in failed ({e}), trying fallback...")

            # ── Fallback 1: goodreturns.in gold-rates page (national) ────────
            try:
                url2 = "https://www.goodreturns.in/gold-rates/"
                resp2 = _req.get(url2, headers=headers, timeout=10)
                if resp2.status_code == 200:
                    soup2 = _BS(resp2.text, 'html.parser')
                    tables2 = soup2.find_all('table')
                    if tables2:
                        table2 = tables2[0]
                        for tr in table2.find_all('tr'):
                            cols = [td.get_text(strip=True) for td in tr.find_all(['th', 'td'])]
                            if len(cols) >= 3 and cols[0] == '10':
                                today_str = cols[1].replace('₹', '').replace(',', '').strip()
                                yday_str = cols[2].replace('₹', '').replace(',', '').strip()
                                if today_str and today_str != 'N/A' and yday_str and yday_str != 'N/A':
                                    today_val = float(today_str)
                                    yday_val = float(yday_str)
                                    if today_val > 0 and yday_val > 0:
                                        print("DEBUG [Gold]: goodreturns.in (national) fallback -> success")
                                        return today_val, yday_val
            except Exception as e:
                print(f"DEBUG [Gold]: goodreturns.in (national) fallback failed ({e})")

            # ── Fallback 2: Yahoo Finance GC=F (COMEX gold, USD/troy oz) ─────
            try:
                import requests
                gold_url = "https://query2.finance.yahoo.com/v8/finance/chart/GC=F?interval=1d&range=5d"
                gold_resp = requests.get(gold_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
                if gold_resp.status_code == 200:
                    gold_data = gold_resp.json()
                    gold_result = gold_data['chart']['result'][0]
                    gold_closes = gold_result['indicators']['quote'][0]['close']
                    valid_gold = [c for c in gold_closes if c is not None]

                    usd_url = "https://query2.finance.yahoo.com/v8/finance/chart/INR=X?interval=1d&range=5d"
                    usd_resp = requests.get(usd_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
                    usd_data = usd_resp.json()
                    usd_result = usd_data['chart']['result'][0]
                    usd_closes = usd_result['indicators']['quote'][0]['close']
                    valid_usd = [c for c in usd_closes if c is not None]

                    if len(valid_gold) >= 2 and len(valid_usd) >= 1:
                        usd_inr = valid_usd[-1]
                        gold_today_usd = valid_gold[-1]
                        gold_prev_usd = valid_gold[-2]
                        today_inr = (gold_today_usd / 31.1035) * 10 * usd_inr
                        prev_inr = (gold_prev_usd / 31.1035) * 10 * usd_inr
                        print(f"DEBUG [Gold]: Yahoo Finance COMEX fallback -> INR {today_inr:.0f}/10g")
                        return round(today_inr), round(prev_inr)
            except Exception as e:
                print(f"DEBUG [Gold]: Yahoo Finance COMEX fallback failed ({e})")

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

        def fetch_usd_inr():
            """
            Primary:  Frankfurter API (ECB daily rates, free, reliable)
            Fallback: Yahoo Finance INR=X
            """
            import requests
            from datetime import datetime, timedelta
            headers = {"User-Agent": "Mozilla/5.0"}
            try:
                resp = requests.get("https://api.frankfurter.app/latest?from=USD&to=INR", headers=headers, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    today_rate = float(data['rates']['INR'])
                    today_dt = datetime.strptime(data['date'], "%Y-%m-%d")
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
                resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
                if resp.status_code == 200:
                    closes = [c for c in resp.json()['chart']['result'][0]['indicators']['quote'][0]['close'] if c is not None]
                    if len(closes) >= 2:
                        return float(closes[-1]), float(closes[-2])
            except Exception:
                pass
            return None, None

        s_now, s_prev = fetch_two("^BSESN")
        n_now, n_prev = fetch_two("^NSEI")
        u_now, u_prev = fetch_usd_inr()
        g_now, g_prev = fetch_mumbai_gold()

        markets = [
            build_entry(s_now, s_prev, "SENSEX",        lambda v: f"{int(round(v)):,}"),
            build_entry(n_now, n_prev, "NIFTY 50",       lambda v: f"{int(round(v)):,}"),
            build_entry(u_now, u_prev, "USD / INR",      lambda v: f"{v:.2f}"),
            build_entry(g_now, g_prev, "GOLD 24K (MUMBAI)", lambda v: f"{int(round(v)):,}"),
        ]
        return jsonify({"markets": markets})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@day9_2_editor_bp.route("/api/reset", methods=["POST"])
def api_reset():
    global _current_html
    _current_html = BASE_HTML
    return jsonify({"success": True})


@day9_2_editor_bp.route("/api/import_json", methods=["POST"])
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
    test_app.register_blueprint(day9_2_editor_bp)
    test_app.run(debug=True, host="0.0.0.0", port=5000)
