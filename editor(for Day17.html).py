"""
Newsband Newsletter Editor — Day17 Flask Backend (v3 layout)
Uses BeautifulSoup4 for controlled, field-level HTML editing.
Footer, layout structure, CSS, and logo are strictly locked.

Every editable element in Day17.html carries a class hook, so the finders
below never depend on inline styles:
    .hdr-date / .hdr-rni            header date + RNI
    .preheader                      inbox preview text (auto-generated)
    .edition-day                    "Friday, 3 April" (derived from date)
    .story[data-story=N]            story container, N = 0..4
        .story-cat / .story-headline / .story-summary / .story-img
        every <a> inside gets the story link
    .wx-temp .wx-loc .wx-desc .wx-high .wx-low .wx-feels .wx-humidity .wx-aqi
    .mkt-cell  > .mkt-label / .mkt-value / .mkt-change
    .mkt-stamp                      "03 APR 2026 · 15:30 IST" (set on update)
"""

import io
import re
from datetime import datetime, timedelta
from urllib.parse import quote as _url_quote
from flask import Blueprint, request, jsonify, render_template, send_file, Response
from bs4 import BeautifulSoup, NavigableString

# WMO weather code → short condition text
_WMO_CODES = {
    0:  "Clear sky",
    1:  "Mainly clear",
    2:  "Partly cloudy",
    3:  "Overcast",
    45: "Foggy",
    48: "Icy fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Dense drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    71: "Light snow",
    73: "Snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Rain showers",
    81: "Moderate showers",
    82: "Heavy showers",
    85: "Snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with hail",
    99: "Heavy thunderstorm",
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


def _one(soup, cls):
    return soup.find(class_=cls)


def _num(text: str) -> str:
    """First integer/decimal in a string, or ''."""
    m = re.search(r'-?\d+(?:\.\d+)?', text or "")
    return m.group() if m else ""


def _story_block(soup, idx: int):
    return soup.find(class_="story", attrs={"data-story": str(idx)})


def _edition_day_from_date(date_val: str) -> str:
    """'April 3, 2026' → 'Friday, 3 April'. Returns '' if unparseable."""
    for fmt in ("%B %d, %Y", "%d/%m/%Y", "%Y-%m-%d", "%d %B %Y"):
        try:
            dt = datetime.strptime(date_val.strip(), fmt)
            return f"{dt.strftime('%A')}, {dt.day} {dt.strftime('%B')}"
        except ValueError:
            continue
    return ""


def _format_change(label: str, value_str: str, pct_float: float, positive: bool) -> str:
    """'▲ 310  +0.42%' — absolute move is back-solved from the closing value."""
    arrow = "▲" if positive else "▼"
    sign = "+" if positive else "−"
    pct_txt = f"{sign}{abs(pct_float):.2f}%"
    clean = value_str.replace("₹", "").replace(",", "").strip()
    try:
        value_num = float(clean)
    except Exception:
        return f"{arrow} {pct_txt}"
    factor = 1 + (pct_float / 100 if positive else -pct_float / 100)
    abs_change = abs(value_num - value_num / factor) if factor else 0.0
    label_lower = label.lower()
    if "usd" in label_lower or "/" in label:
        abs_txt = f"{abs_change:.2f}"
    else:
        abs_txt = f"{abs_change:,.0f}"
    return f"{arrow} {abs_txt}  {pct_txt}"


def _build_preheader(weather: dict) -> str:
    temp = (weather.get("today_temp") or "").strip()
    desc = (weather.get("today_desc") or "").strip()
    loc = (weather.get("location") or "").strip()
    lead = ""
    if temp and loc:
        cond = f" and {desc[0].lower() + desc[1:]}" if desc else ""
        lead = f"{temp}°{cond} in {loc}. "
    return lead + "Five stories, and where Gold, the rupee, Nifty and Sensex closed."


# ── Parse: extract current editable fields ────────────────────────────────────

def get_tomorrow_date_str() -> str:
    dt = datetime.now() + timedelta(days=1)
    return dt.strftime("%B %d, %Y").replace(" 0", " ")


def _find_weather_data(soup):
    weather = {}
    for key, cls in (
        ("location", "wx-loc"), ("today_desc", "wx-desc"),
    ):
        el = _one(soup, cls)
        if el:
            weather[key] = el.get_text().strip()
    for key, cls in (
        ("today_temp", "wx-temp"), ("today_high", "wx-high"), ("today_low", "wx-low"),
        ("today_feels", "wx-feels"), ("today_humidity", "wx-humidity"), ("today_aqi", "wx-aqi"),
    ):
        el = _one(soup, cls)
        if el:
            weather[key] = _num(el.get_text())
    weather.setdefault("location", "Navi Mumbai")
    return weather


def _find_market_data(soup):
    markets = []
    for cell in soup.find_all("td", class_="mkt-cell"):
        label = cell.find(class_="mkt-label")
        value = cell.find(class_="mkt-value")
        change = cell.find(class_="mkt-change")
        if not (label and value and change):
            continue
        change_text = change.get_text()
        m = re.search(r'(\d+(?:\.\d+)?)\s*%', change_text)
        positive = "▲" in change_text or ("color: #4cc07a" in change.get("style", "") and "▼" not in change_text)
        markets.append({
            "label": label.get_text().strip(),
            "value": value.get_text().strip(),
            "pct": m.group(1) if m else "",
            "positive": positive,
        })
    return markets


def parse_fields(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    result = {}

    # Header — Date (always seeded with tomorrow's date, like the other editors)
    if _one(soup, "hdr-date"):
        result["date"] = get_tomorrow_date_str()

    # Header — RNI
    rni_div = _one(soup, "hdr-rni")
    if rni_div:
        result["rni"] = rni_div.get_text().replace("RNI:", "").strip()

    # Stories 0..4
    types = {0: "feature", 1: "medium", 2: "medium", 3: "compact", 4: "compact"}
    stories = []
    for idx in range(5):
        block = _story_block(soup, idx)
        if not block:
            continue
        s = {"index": idx, "type": types[idx]}
        cat = block.find(class_="story-cat")
        if cat:
            s["category"] = cat.get_text().strip()
        hl = block.find(class_="story-headline")
        if hl:
            s["headline"] = hl.get_text().strip()
            s["link"] = hl.get("href", "")
        summ = block.find(class_="story-summary")
        if summ:
            s["summary"] = summ.get_text().strip()
        img = block.find(class_="story-img")
        if img:
            s["image"] = img.get("src", "")
        stories.append(s)
    result["stories"] = stories

    result["weather"] = _find_weather_data(soup)
    result["markets"] = _find_market_data(soup)
    return result


# ── Update: write fields back into the HTML ───────────────────────────────────

def update_html(html: str, data: dict) -> str:
    soup = BeautifulSoup(html, "html.parser")

    # Header — Date (+ derived edition-bar day)
    date_val = (data.get("date") or "").strip()
    if date_val:
        date_div = _one(soup, "hdr-date")
        if date_div:
            _set_text(date_div, f"Date: {date_val}")
        day_txt = _edition_day_from_date(date_val)
        ed = _one(soup, "edition-day")
        if ed and day_txt:
            _set_text(ed, day_txt)

    # Header — RNI
    rni_val = (data.get("rni") or "").strip()
    if rni_val:
        rni_div = _one(soup, "hdr-rni")
        if rni_div:
            _set_text(rni_div, f"RNI: {rni_val}")

    # Stories
    for story_data in data.get("stories", []):
        idx = story_data.get("index", -1)
        block = _story_block(soup, idx)
        if not block:
            continue

        cat = (story_data.get("category") or "").strip()
        cat_el = block.find(class_="story-cat")
        if cat and cat_el:
            _set_text(cat_el, cat)

        hl = (story_data.get("headline") or "").strip()
        hl_el = block.find(class_="story-headline")
        if hl and hl_el:
            _set_text(hl_el, hl)

        summ = (story_data.get("summary") or "").strip()
        summ_el = block.find(class_="story-summary")
        if summ and summ_el:
            _set_text(summ_el, summ)

        img_url = (story_data.get("image") or "").strip()
        img_el = block.find(class_="story-img")
        if img_url and img_url.startswith(("http://", "https://")) and img_el:
            img_el["src"] = img_url
            if hl:
                img_el["alt"] = hl

        link = (story_data.get("link") or "").strip()
        if link:
            for a in block.find_all("a"):
                a["href"] = link

    # Weather — accept both the editor's today_* keys and the short JSON-import keys
    weather_data = data.get("weather") or {}
    if weather_data:
        aliases = {
            "today_desc": "desc", "today_high": "high", "today_low": "low",
            "today_temp": "temp", "today_feels": "feels", "today_humidity": "humidity",
            "today_aqi": "aqi",
        }
        for long_key, short_key in aliases.items():
            if not weather_data.get(long_key) and weather_data.get(short_key):
                weather_data[long_key] = weather_data[short_key]

        for key, cls in (
            ("location", "wx-loc"), ("today_desc", "wx-desc"), ("today_temp", "wx-temp"),
            ("today_high", "wx-high"), ("today_low", "wx-low"), ("today_feels", "wx-feels"),
            ("today_humidity", "wx-humidity"), ("today_aqi", "wx-aqi"),
        ):
            val = str(weather_data.get(key) or "").strip()
            el = _one(soup, cls)
            if val and el:
                _set_text(el, val)

        pre = _one(soup, "preheader")
        if pre:
            merged = _find_weather_data(soup)
            _set_text(pre, _build_preheader(merged))

    # Markets
    markets_data = data.get("markets", [])
    if markets_data:
        cells = soup.find_all("td", class_="mkt-cell")
        for i, mkt in enumerate(markets_data):
            if i >= len(cells):
                break
            cell = cells[i]
            label_el = cell.find(class_="mkt-label")
            value_el = cell.find(class_="mkt-value")
            change_el = cell.find(class_="mkt-change")
            if not (label_el and value_el and change_el):
                continue

            label = (mkt.get("label") or "").strip()
            if label:
                _set_text(label_el, label)
            value = (mkt.get("value") or "").strip()
            if value:
                _set_text(value_el, value)

            pct_raw = str(mkt.get("pct") or "").strip().replace("%", "")
            positive = mkt.get("positive", True)
            if pct_raw:
                try:
                    pct_float = float(pct_raw)
                except ValueError:
                    pct_float = 0.0
                _set_text(change_el, _format_change(
                    label or label_el.get_text().strip(),
                    value or value_el.get_text().strip(),
                    pct_float, positive,
                ))
                color = "#4cc07a" if positive else "#ff6b6b"
                change_el["style"] = re.sub(
                    r'color:\s*#[0-9a-fA-F]{6}', f'color: {color}', change_el.get("style", "")
                )

        # Close stamp — markets shut at 15:30 IST on the day the editor is used
        stamp = _one(soup, "mkt-stamp")
        if stamp:
            _set_text(stamp, f"{datetime.now().strftime('%d %b %Y').upper()} · 15:30 IST")

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
        "today_temp": "31",
        "today_high": "35",
        "today_low": "27",
        "today_feels": "35",
        "today_humidity": "70",
        "today_aqi": "",
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

    def clean_int(val, default=""):
        if val is None:
            return default
        try:
            return str(int(round(float(str(val)))))
        except Exception:
            return default

    hdrs = {"User-Agent": "Mozilla/5.0"}

    # 1. Open-Meteo (geocoding + forecast + air quality — free, no key required)
    try:
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
                    f"&current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code"
                    f"&daily=temperature_2m_max,temperature_2m_min,weather_code"
                    f"&timezone=auto&forecast_days=2"
                )
                wx_resp = _req.get(wx_url, headers=hdrs, timeout=8)
                if wx_resp.status_code == 200:
                    body = wx_resp.json()
                    daily = body.get("daily", {})
                    current = body.get("current", {})
                    maxtemps = daily.get("temperature_2m_max", [])
                    mintemps = daily.get("temperature_2m_min", [])
                    # Open-Meteo renamed weathercode → weather_code; support both
                    codes = daily.get("weather_code") or daily.get("weathercode", [])
                    if maxtemps:
                        wmo = current.get("weather_code")
                        if wmo is None:
                            wmo = int(codes[0]) if codes else 2
                        desc = _WMO_CODES.get(int(wmo), "Partly cloudy")
                        res_data.update({
                            "location": place_name,
                            "today_desc": desc,
                            "today_temp": clean_temp(current.get("temperature_2m"), "31"),
                            "today_high": clean_temp(maxtemps[0], "35"),
                            "today_low": clean_temp(mintemps[0] if mintemps else None, "27"),
                            "today_feels": clean_temp(current.get("apparent_temperature"), "35"),
                            "today_humidity": clean_int(current.get("relative_humidity_2m"), "70"),
                        })

                        # AQI is a separate Open-Meteo endpoint; failure here is non-fatal
                        try:
                            aq_url = (
                                f"https://air-quality-api.open-meteo.com/v1/air-quality"
                                f"?latitude={lat}&longitude={lon}&current=us_aqi&timezone=auto"
                            )
                            aq_resp = _req.get(aq_url, headers=hdrs, timeout=8)
                            if aq_resp.status_code == 200:
                                aqi = aq_resp.json().get("current", {}).get("us_aqi")
                                res_data["today_aqi"] = clean_int(aqi, "")
                        except Exception as e:
                            print(f"DEBUG [Weather]: Open-Meteo AQI failed ({e})")

                        print(f"DEBUG [Weather]: Open-Meteo OK → {place_name} {desc} "
                              f"{res_data['today_temp']}°C ({maxtemps[0]}/{mintemps[0] if mintemps else '?'}) "
                              f"AQI {res_data['today_aqi'] or '?'}")
                        return jsonify(res_data)
    except Exception as e:
        print(f"DEBUG [Weather]: Open-Meteo failed ({e}), trying wttr.in…")

    # 2. Fallback — wttr.in JSON API
    try:
        loc_query = location.replace(" ", "_")
        url = f"https://wttr.in/{loc_query}?format=j1"
        resp = _req.get(url, headers=hdrs, timeout=8)
        if resp.status_code == 200:
            body = resp.json()
            weather_days = body.get("weather", [])
            current = (body.get("current_condition") or [{}])[0]
            if weather_days:
                day_data = weather_days[0]  # index 0 = today
                res_data["today_high"] = clean_temp(day_data.get("maxtempC"), "35")
                res_data["today_low"] = clean_temp(day_data.get("mintempC"), "27")
                res_data["today_temp"] = clean_temp(current.get("temp_C"), res_data["today_high"])
                res_data["today_feels"] = clean_temp(current.get("FeelsLikeC"), res_data["today_temp"])
                res_data["today_humidity"] = clean_int(current.get("humidity"), "70")

                desc_list = current.get("weatherDesc") or []
                desc = desc_list[0].get("value") if desc_list else None
                if not desc:
                    hourly = day_data.get("hourly", [])
                    if hourly:
                        mid_desc = hourly[len(hourly) // 2].get("weatherDesc", [])
                        desc = mid_desc[0].get("value") if mid_desc else None
                res_data["today_desc"] = desc or "Partly cloudy"

                print(f"DEBUG [Weather]: wttr.in OK → {location} {res_data['today_desc']}")
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
