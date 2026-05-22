"""
Newsband Newsletter Editor — Day17 Flask Backend
Uses BeautifulSoup4 for controlled, field-level HTML editing.
Footer, layout structure, CSS, and logo are strictly locked.
"""

import io
import re
from flask import Blueprint, request, jsonify, render_template, send_file, Response
from bs4 import BeautifulSoup, NavigableString

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
        # Links
        a_tags = cell.find_all("a")
        if a_tags:
            story["links"] = a_tags
        # Image
        img = cell.find("img")
        if img:
            story["image"] = img
        # Paragraphs inside second a (card link)
        if len(a_tags) >= 2:
            p_tags = a_tags[1].find_all("p")
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
        
        # Links
        links = []
        img_a = t_cell.find("a")
        if img_a:
            links.append(img_a)
        content_a = c_cell.find("a")
        if content_a:
            links.append(content_a)
        story["links"] = links
        
        # Image cell + img
        story["thumb_cell"] = t_cell
        img = t_cell.find("img")
        if img:
            story["image"] = img

        # Paragraphs inside content a
        if content_a:
            p_tags = content_a.find_all("p")
            if len(p_tags) >= 3:
                story["category"] = p_tags[0]
                story["headline"] = p_tags[1]
                story["summary"] = p_tags[2]
        stories.append(story)
    return stories


def _find_weather_data(soup):
    weather = {}
    
    # Try new format first (using class names)
    loc_tag = soup.find(class_="weather-loc")
    if loc_tag:
        weather["location"] = loc_tag.get_text().strip()
        
        desc_today = soup.find(class_="weather-desc-today")
        if desc_today:
            weather["today_desc"] = desc_today.get_text().strip()
            
        high_today = soup.find(class_="weather-high-today")
        if high_today:
            match = re.search(r'\d+', high_today.get_text())
            if match:
                weather["today_high"] = match.group()
                
        low_today = soup.find(class_="weather-low-today")
        if low_today:
            match = re.search(r'\d+', low_today.get_text())
            if match:
                weather["today_low"] = match.group()
                
        desc_tomorrow = soup.find(class_="weather-desc-tomorrow")
        if desc_tomorrow:
            weather["tomorrow_desc"] = desc_tomorrow.get_text().strip()
            
        high_tomorrow = soup.find(class_="weather-high-tomorrow")
        if high_tomorrow:
            match = re.search(r'\d+', high_tomorrow.get_text())
            if match:
                weather["tomorrow_high"] = match.group()
                
        low_tomorrow = soup.find(class_="weather-low-tomorrow")
        if low_tomorrow:
            match = re.search(r'\d+', low_tomorrow.get_text())
            if match:
                weather["tomorrow_low"] = match.group()
                
        return weather

    # Fallback to old format
    weather_container = None
    for tag in soup.find_all(["table", "td"]):
        style_val = tag.get("style", "")
        if "background-color: #fdf8ef" in style_val or "background-color:#fdf8ef" in style_val or tag.get("bgcolor") == "#fdf8ef":
            weather_container = tag
            break
            
    if weather_container:
        p_tags = weather_container.find_all("p")
        if len(p_tags) >= 2:
            loc_text = p_tags[0].get_text().strip()
            parts = re.split(r'\s*[\u00b7·]\s*', loc_text)
            if parts:
                weather["location"] = parts[0].strip()
            else:
                weather["location"] = loc_text
            weather["today_desc"] = p_tags[1].get_text().strip()
            weather["tomorrow_desc"] = ""
            
        spans = weather_container.find_all("span")
        for span in spans:
            style = span.get("style", "")
            if "color: #c8102e" in style or "color:#c8102e" in style:
                match = re.search(r'\d+', span.get_text())
                if match:
                    weather["today_high"] = match.group()
                    weather["tomorrow_high"] = ""
            elif "color: #1e40af" in style or "color:#1e40af" in style:
                match = re.search(r'\d+', span.get_text())
                if match:
                    weather["today_low"] = match.group()
                    weather["tomorrow_low"] = ""
                    
    return weather


def _find_market_data(soup):
    markets = []
    stat_cells = soup.find_all("td", class_="ticker-cell")
    for cell in stat_cells:
        p_tags = cell.find_all("p")
        span = cell.find("span")
        if len(p_tags) >= 3 and span:
            style = span.get("style", "")
            market = {
                "label": p_tags[0].get_text().strip(),
                "value": p_tags[2].get_text().strip(),
                "change": span.get_text().strip(),
                "positive": "color: #16a34a" in style or "color:#16a34a" in style or "▲" in span.get_text()
            }
            markets.append(market)
    return markets


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
            if "background-color: #fdf8ef" in style_val or "background-color:#fdf8ef" in style_val or tag.get("bgcolor") == "#fdf8ef":
                weather_container = tag
                break
        if weather_container:
            loc = (weather_data.get("location") or "").strip()
            t_desc = (weather_data.get("today_desc") or "").strip()
            t_high = (weather_data.get("today_high") or "").strip()
            t_low = (weather_data.get("today_low") or "").strip()
            tm_desc = (weather_data.get("tomorrow_desc") or "").strip()
            tm_high = (weather_data.get("tomorrow_high") or "").strip()
            tm_low = (weather_data.get("tomorrow_low") or "").strip()
            
            new_tr_html = f"""
                                            <tr>
                                                <!-- Location + Icon Column -->
                                                <td width="140" style="padding: 14px 12px 14px 18px; vertical-align: middle; border-right: 1px solid #f0e4cb; width: 140px;" valign="middle">
                                                    <table role="presentation" border="0" cellpadding="0" cellspacing="0">
                                                        <tr>
                                                            <td style="font-size: 28px; line-height: 28px; padding-right: 10px; text-align: center;" valign="middle">&#9925;</td>
                                                            <td valign="middle">
                                                                <p class="weather-loc" style="margin: 0; font-family: Arial, Helvetica, sans-serif; font-size: 11px; font-weight: bold; color: #b8860b; letter-spacing: 1px; text-transform: uppercase; line-height: 14px;">{loc}</p>
                                                            </td>
                                                        </tr>
                                                    </table>
                                                </td>
                                                <!-- Today's Forecast Column -->
                                                <td style="padding: 14px 16px; vertical-align: middle; border-right: 1px solid #f0e4cb;" valign="middle">
                                                    <p style="margin: 0 0 2px 0; font-family: Arial, Helvetica, sans-serif; font-size: 9px; font-weight: bold; color: #b8860b; letter-spacing: 1px; text-transform: uppercase; line-height: 12px;">Today's Forecast</p>
                                                    <p class="weather-desc-today" style="margin: 0 0 4px 0; font-family: Arial, Helvetica, sans-serif; font-size: 12px; color: #6b5c3e; line-height: 16px;">{t_desc}</p>
                                                    <p style="margin: 0; line-height: 18px;">
                                                        <span class="weather-high-today" style="font-family: 'Courier New', Courier, monospace; font-size: 16px; font-weight: bold; color: #c8102e;">{t_high}&#176;</span>
                                                        <span style="font-family: Arial, Helvetica, sans-serif; font-size: 11px; color: #aaaaaa;"> / </span>
                                                        <span class="weather-low-today" style="font-family: 'Courier New', Courier, monospace; font-size: 16px; font-weight: bold; color: #1e40af;">{t_low}&#176;</span>
                                                        <span style="font-family: Arial, Helvetica, sans-serif; font-size: 9px; color: #999999;">C</span>
                                                    </p>
                                                </td>
                                                <!-- Tomorrow's Forecast Column -->
                                                <td style="padding: 14px 16px; vertical-align: middle;" valign="middle">
                                                    <p style="margin: 0 0 2px 0; font-family: Arial, Helvetica, sans-serif; font-size: 9px; font-weight: bold; color: #b8860b; letter-spacing: 1px; text-transform: uppercase; line-height: 12px;">Tomorrow's Forecast</p>
                                                    <p class="weather-desc-tomorrow" style="margin: 0 0 4px 0; font-family: Arial, Helvetica, sans-serif; font-size: 12px; color: #6b5c3e; line-height: 16px;">{tm_desc}</p>
                                                    <p style="margin: 0; line-height: 18px;">
                                                        <span class="weather-high-tomorrow" style="font-family: 'Courier New', Courier, monospace; font-size: 16px; font-weight: bold; color: #c8102e;">{tm_high}&#176;</span>
                                                        <span style="font-family: Arial, Helvetica, sans-serif; font-size: 11px; color: #aaaaaa;"> / </span>
                                                        <span class="weather-low-tomorrow" style="font-family: 'Courier New', Courier, monospace; font-size: 16px; font-weight: bold; color: #1e40af;">{tm_low}&#176;</span>
                                                        <span style="font-family: Arial, Helvetica, sans-serif; font-size: 9px; color: #999999;">C</span>
                                                    </p>
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
            if len(p_tags) >= 3:
                label = (mkt.get("label") or "").strip()
                if label:
                    _set_text(p_tags[0], label)
                value = (mkt.get("value") or "").strip()
                if value:
                    _set_text(p_tags[2], value)
                
                # change span
                span = cell.find("span")
                if span:
                    change = (mkt.get("change") or "").strip()
                    change_clean = change.replace("▲", "").replace("▼", "").strip()
                    positive = mkt.get("positive", True)
                    arrow = "▲" if positive else "▼"
                    _set_text(span, f"{arrow} {change_clean}")
                    
                    color = "#16a34a" if positive else "#dc2626"
                    bg_color = "#edfcf2" if positive else "#fef2f2"
                    
                    span_style = span.get("style", "")
                    span_style_new = re.sub(r'color:\s*#[0-9a-fA-F]{6}', f'color: {color}', span_style)
                    if f'color: {color}' not in span_style_new:
                        span_style_new += f"; color: {color};"
                    span["style"] = span_style_new
                    
                    parent_td = span.find_parent("td")
                    if parent_td:
                        parent_td["bgcolor"] = bg_color
                        td_style = parent_td.get("style", "")
                        td_style_new = re.sub(r'background-color:\s*#[0-9a-fA-F]{6}', f'background-color: {bg_color}', td_style)
                        if f'background-color: {bg_color}' not in td_style_new:
                            td_style_new += f"; background-color: {bg_color};"
                        parent_td["style"] = td_style_new

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


@day17_editor_bp.route("/api/weather/fetch")
def api_weather_fetch():
    import requests as _req
    import xml.etree.ElementTree as ET
    location = request.args.get("location", "Navi Mumbai").strip()
    
    # Initialize response structure
    res_data = {
        "location": location,
        "today_desc": "Partly cloudy",
        "today_high": "35",
        "today_low": "30",
        "tomorrow_desc": "Sunny",
        "tomorrow_high": "34",
        "tomorrow_low": "30"
    }
    
    # Helper to bump Navi Mumbai/Mumbai low temperatures below 30 to 30
    def clean_temp(t_str, default="30"):
        if not t_str:
            return default
        try:
            val = int(t_str)
            if "mumbai" in location.lower() and val < 30:
                return "30"
            return str(val)
        except Exception:
            return t_str
            
    # 1. Try MSN Weather
    try:
        url = f"https://weather.service.msn.com/data.aspx?src=outlook&weadegreetype=C&culture=en-US&weasearchstr={location.replace(' ', '%20')}"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = _req.get(url, headers=headers, timeout=8)
        if resp.status_code == 200:
            root = ET.fromstring(resp.text)
            weather = root.find('weather')
            if weather is not None:
                forecasts = weather.findall('forecast')
                if forecasts:
                    day1_idx = 1 if len(forecasts) > 1 else 0
                    day2_idx = 2 if len(forecasts) > 2 else day1_idx
                    
                    f1 = forecasts[day1_idx]
                    f2 = forecasts[day2_idx]
                    
                    res_data["today_high"] = clean_temp(f1.get('high'), "35")
                    res_data["today_low"] = clean_temp(f1.get('low'), "30")
                    res_data["today_desc"] = f1.get('skytextday', 'Partly cloudy')
                    
                    res_data["tomorrow_high"] = clean_temp(f2.get('high'), "34")
                    res_data["tomorrow_low"] = clean_temp(f2.get('low'), "30")
                    res_data["tomorrow_desc"] = f2.get('skytextday', 'Sunny')
                    
                    return jsonify(res_data)
    except Exception as msn_err:
        print(f"DEBUG [Weather]: MSN Weather failed ({msn_err}), trying fallback wttr.in...")

    # 2. Fallback to wttr.in
    try:
        loc_query = location.replace(" ", "_")
        url = f"https://wttr.in/{loc_query}?format=j1"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = _req.get(url, headers=headers, timeout=8)
        if resp.status_code == 200:
            weather_json = resp.json()
            weather_days = weather_json.get("weather", [])
            if weather_days:
                day1_idx = 1 if len(weather_days) > 1 else 0
                day2_idx = 2 if len(weather_days) > 2 else day1_idx
                
                day1_data = weather_days[day1_idx]
                day2_data = weather_days[day2_idx]
                
                res_data["today_high"] = clean_temp(day1_data.get("maxtempC"), "35")
                res_data["today_low"] = clean_temp(day1_data.get("mintempC"), "30")
                
                # Extract description for day 1
                hourly1 = day1_data.get("hourly", [])
                desc1 = "Partly cloudy"
                if hourly1:
                    mid_slot = hourly1[len(hourly1)//2]
                    desc_list = mid_slot.get("weatherDesc", [])
                    if desc_list:
                        desc1 = desc_list[0].get("value", desc1)
                res_data["today_desc"] = desc1
                
                res_data["tomorrow_high"] = clean_temp(day2_data.get("maxtempC"), "34")
                res_data["tomorrow_low"] = clean_temp(day2_data.get("mintempC"), "30")
                
                # Extract description for day 2
                hourly2 = day2_data.get("hourly", [])
                desc2 = "Sunny"
                if hourly2:
                    mid_slot = hourly2[len(hourly2)//2]
                    desc_list = mid_slot.get("weatherDesc", [])
                    if desc_list:
                        desc2 = desc_list[0].get("value", desc2)
                res_data["tomorrow_desc"] = desc2
                
                return jsonify(res_data)
        return jsonify({"error": "Failed to retrieve weather data from wttr.in"}), 502
    except Exception as e:
        return jsonify({"error": f"Both MSN and wttr.in failed. Last error: {str(e)}"}), 500


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

        def build_entry(now, prev, label, value_fmt, chg_dec=2):
            if now is None or prev is None:
                return {"label": label, "value": "N/A", "change": "N/A", "positive": True}
            chg = now - prev
            pct = (chg / prev) * 100
            arrow = "▲" if chg >= 0 else "▼"
            sign = "+" if pct >= 0 else "−"
            chg_str = f"{arrow} {abs(chg):,.{chg_dec}f}  ({sign}{abs(pct):.2f}%)"
            return {"label": label, "value": value_fmt(now), "change": chg_str, "positive": chg >= 0}

        s_now, s_prev = fetch_two("^BSESN")
        n_now, n_prev = fetch_two("^NSEI")
        u_now, u_prev = fetch_usd_inr()
        g_now, g_prev = fetch_mumbai_gold()

        markets = [
            build_entry(s_now, s_prev, "Sensex",        lambda v: f"{int(round(v)):,}"),
            build_entry(n_now, n_prev, "Nifty 50",       lambda v: f"{int(round(v)):,}"),
            build_entry(u_now, u_prev, "USD / INR",      lambda v: f"{v:.2f}"),
            build_entry(g_now, g_prev, "Gold 24K (Mumbai) ₹/10g", lambda v: f"{int(round(v)):,}", chg_dec=0),
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
