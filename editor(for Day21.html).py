"""
Newsband Newsletter Editor — Day21 Flask Backend
Uses BeautifulSoup4 for controlled, field-level HTML editing.
Footer, layout structure, CSS, and logo are strictly locked.

Every editable element in Day21.html carries a class hook, so the finders
below never depend on inline styles:
    .hdr-date / .hdr-rni            header date + RNI
    .preheader                      inbox preview text (auto-generated)
    .story[data-story=N]            story card, N = 0..4
        .story-cat / .story-headline / .story-summary / .story-img
        every <a> inside gets the story link
    .aqi-tile .aqi-loc .aqi-value .aqi-cat .aqi-pollutant  (AQI tile;
        .aqi-accent / .aqi-rule recolour with the AQI category)
    .mkt-cell  > .mkt-label / .mkt-value / .mkt-change (coloured pill)
"""

import io
import re
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, render_template, send_file, Response
from bs4 import BeautifulSoup, NavigableString

# CPCB National AQI categories → tile colours.
#   bg     — tile background (always paired with white text, so these stay dark
#            enough to read; the yellow/orange bands are deepened accordingly)
#   accent — the small uppercase labels on the tile
#   rule   — the thin divider line
_AQI_PALETTE = {
    "good":         {"bg": "#049a5b", "accent": "#c4ead8", "rule": "#3bb47e"},
    "satisfactory": {"bg": "#5b9830", "accent": "#dcecc8", "rule": "#86ba60"},
    "moderate":     {"bg": "#b07a00", "accent": "#f3e3bf", "rule": "#cf9e2f"},
    "poor":         {"bg": "#e8590c", "accent": "#ffe3cf", "rule": "#f39a63"},
    "verypoor":     {"bg": "#d32f2f", "accent": "#ffd6d6", "rule": "#e97070"},
    "severe":       {"bg": "#7a1620", "accent": "#eac4c9", "rule": "#ab4652"},
}


def _canon_category(cat: str) -> str:
    """Normalise a category label to an _AQI_PALETTE key, or '' if unknown."""
    c = re.sub(r"[^a-z]", "", (cat or "").lower())
    return {
        "good": "good",
        "satisfactory": "satisfactory",
        "moderate": "moderate", "moderatelypolluted": "moderate",
        "poor": "poor",
        "verypoor": "verypoor",
        "severe": "severe",
    }.get(c, "")


day21_editor_bp = Blueprint('day21_editor', __name__)

# ── Load base template once at startup ────────────────────────────────────────
with open("Day21.html", "r", encoding="utf-8") as f:
    BASE_HTML = f.read()
    print(f"DEBUG [Day21]: BASE_HTML length: {len(BASE_HTML)}")

_current_html = BASE_HTML   # mutable working copy

# Zero-width filler after the preheader so inbox previews don't pull in body text
_PREHEADER_FILL = " ͏" * 8

# Change pill: text colour + pill background
_UP_COLOR, _UP_BG = "#15803d", "#e7f6ec"
_DOWN_COLOR, _DOWN_BG = "#dc2626", "#fdecec"


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


def _story_blocks(soup, idx: int):
    return soup.find_all(class_="story", attrs={"data-story": str(idx)})


def _story_find(blocks, cls):
    for block in blocks:
        el = block.find(class_=cls)
        if el:
            return el
    return None


def _format_change(label: str, value_str: str, pct_float: float, positive: bool) -> str:
    """'▲ 312.40 · 0.39%' — absolute move is back-solved from the closing value."""
    arrow = "▲" if positive else "▼"
    pct_txt = f"{abs(pct_float):.2f}%"
    clean = value_str.replace("₹", "").replace(",", "").strip()
    try:
        value_num = float(clean)
    except Exception:
        return f"{arrow} {pct_txt}"
    factor = 1 + (pct_float / 100 if positive else -pct_float / 100)
    abs_change = abs(value_num - value_num / factor) if factor else 0.0
    if "gold" in label.lower():
        abs_txt = f"{abs_change:,.0f}"
    else:
        abs_txt = f"{abs_change:,.2f}"
    return f"{arrow} {abs_txt} · {pct_txt}"


def _build_preheader(aqi: dict) -> str:
    value = (aqi.get("value") or "").strip()
    category = (aqi.get("category") or "").strip()
    loc = (aqi.get("location") or "").strip()
    lead = ""
    if value and loc:
        cat = f" ({category})" if category else ""
        lead = f"Air quality in {loc}: AQI {value}{cat}. "
    return lead + "Five stories from Navi Mumbai & Thane, plus where Sensex, Nifty, the rupee and gold closed."


# ── Parse: extract current editable fields ────────────────────────────────────

def get_tomorrow_date_str() -> str:
    dt = datetime.now() + timedelta(days=1)
    return dt.strftime("%B %d, %Y").replace(" 0", " ")


def _find_aqi_data(soup):
    aqi = {}
    for key, cls in (("location", "aqi-loc"), ("category", "aqi-cat"),
                     ("pollutant", "aqi-pollutant")):
        el = _one(soup, cls)
        if el:
            aqi[key] = el.get_text().strip()
    el = _one(soup, "aqi-value")
    if el:
        aqi["value"] = _num(el.get_text())
    aqi.setdefault("location", "Navi Mumbai")
    return aqi


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
        markets.append({
            "label": label.get_text().strip(),
            "value": value.get_text().strip(),
            "pct": m.group(1) if m else "",
            "positive": "▼" not in change_text,
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
        blocks = _story_blocks(soup, idx)
        if not blocks:
            continue
        s = {"index": idx, "type": types[idx]}
        cat = _story_find(blocks, "story-cat")
        if cat:
            s["category"] = cat.get_text().strip()
        hl = _story_find(blocks, "story-headline")
        if hl:
            s["headline"] = hl.get_text().strip()
            s["link"] = hl.get("href", "")
        summ = _story_find(blocks, "story-summary")
        if summ:
            s["summary"] = summ.get_text().strip()
        img = _story_find(blocks, "story-img")
        if img:
            s["image"] = img.get("src", "")
        stories.append(s)
    result["stories"] = stories

    result["aqi"] = _find_aqi_data(soup)
    result["markets"] = _find_market_data(soup)
    return result


# ── Update: write fields back into the HTML ───────────────────────────────────

def update_html(html: str, data: dict) -> str:
    soup = BeautifulSoup(html, "html.parser")

    # Header — Date
    date_val = (data.get("date") or "").strip()
    if date_val:
        date_div = _one(soup, "hdr-date")
        if date_div:
            _set_text(date_div, f"Date: {date_val}")

    # Header — RNI
    rni_val = (data.get("rni") or "").strip()
    if rni_val:
        rni_div = _one(soup, "hdr-rni")
        if rni_div:
            _set_text(rni_div, f"RNI: {rni_val}")

    # Stories
    for story_data in data.get("stories", []):
        idx = story_data.get("index", -1)
        blocks = _story_blocks(soup, idx)
        if not blocks:
            continue

        cat = (story_data.get("category") or "").strip()
        cat_el = _story_find(blocks, "story-cat")
        if cat and cat_el:
            _set_text(cat_el, cat)

        hl = (story_data.get("headline") or "").strip()
        hl_el = _story_find(blocks, "story-headline")
        if hl and hl_el:
            _set_text(hl_el, hl)

        summ = (story_data.get("summary") or "").strip()
        summ_el = _story_find(blocks, "story-summary")
        if summ and summ_el:
            _set_text(summ_el, summ)

        img_url = (story_data.get("image") or "").strip()
        img_el = _story_find(blocks, "story-img")
        if img_url and img_url.startswith(("http://", "https://")) and img_el:
            img_el["src"] = img_url
            if hl:
                img_el["alt"] = hl

        link = (story_data.get("link") or "").strip()
        if link:
            for block in blocks:
                for a in block.find_all("a"):
                    a["href"] = link

    # Air Quality (AQI tile)
    aqi_data = data.get("aqi") or {}
    if aqi_data:
        for key, cls in (
            ("location", "aqi-loc"), ("value", "aqi-value"),
            ("category", "aqi-cat"), ("pollutant", "aqi-pollutant"),
        ):
            val = str(aqi_data.get(key) or "").strip()
            el = _one(soup, cls)
            if val and el:
                _set_text(el, val)

        # Recolour the tile to match the AQI category
        palette = _AQI_PALETTE.get(_canon_category(aqi_data.get("category", "")))
        if palette:
            tile = _one(soup, "aqi-tile")
            if tile:
                tile["bgcolor"] = palette["bg"]
                tile["style"] = re.sub(
                    r'background-color:\s*#[0-9a-fA-F]{6}',
                    f'background-color:{palette["bg"]}', tile.get("style", ""))
            for el in soup.find_all(class_="aqi-accent"):
                el["style"] = re.sub(
                    r'(?<![-\w])color:\s*#[0-9a-fA-F]{6}',
                    f'color:{palette["accent"]}', el.get("style", ""))
            rule = _one(soup, "aqi-rule")
            if rule:
                rule["style"] = re.sub(
                    r'background-color:\s*#[0-9a-fA-F]{6}',
                    f'background-color:{palette["rule"]}', rule.get("style", ""))

        pre = _one(soup, "preheader")
        if pre:
            _set_text(pre, _build_preheader(_find_aqi_data(soup)) + _PREHEADER_FILL)

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
                color, bg = (_UP_COLOR, _UP_BG) if positive else (_DOWN_COLOR, _DOWN_BG)
                style = change_el.get("style", "")
                style = re.sub(r'background-color:\s*#[0-9a-fA-F]{6}', f'background-color:{bg}', style)
                style = re.sub(r'(?<![-\w])color:\s*#[0-9a-fA-F]{6}', f'color:{color}', style)
                change_el["style"] = style

    return str(soup)


# ── Routes ────────────────────────────────────────────────────────────────────

@day21_editor_bp.route("/")
def editor():
    return render_template("editor_day21.html", api_prefix="/day21-editor")


@day21_editor_bp.route("/api/fields")
def api_fields():
    return jsonify(parse_fields(_current_html))


@day21_editor_bp.route("/api/update", methods=["POST"])
def api_update():
    global _current_html
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON body"}), 400
    _current_html = update_html(_current_html, data)
    return jsonify({"success": True, "html": _current_html})


@day21_editor_bp.route("/api/preview")
def api_preview():
    return Response(_current_html, mimetype="text/html; charset=utf-8")


@day21_editor_bp.route("/api/export")
def api_export():
    buf = io.BytesIO(_current_html.encode("utf-8"))
    return send_file(
        buf,
        as_attachment=True,
        download_name="newsband_day21_newsletter.html",
        mimetype="text/html",
    )


@day21_editor_bp.route("/api/export_zip")
def api_export_zip():
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("newsband_day21_newsletter.html", _current_html.encode("utf-8"))
    buf.seek(0)
    return send_file(
        buf,
        as_attachment=True,
        download_name="newsband_day21_newsletter.zip",
        mimetype="application/zip",
    )


@day21_editor_bp.route("/api/markets/fetch")
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

            def _parse_goodreturns_gold(soup):
                # goodreturns.in's summary table now combines price+change in
                # one cell (e.g. "₹1,55,680(-160)"), so pull from its per-day
                # history table ('Date' | '24K' | '22K') instead — one clean
                # per-gram price per row.
                import re
                tables = soup.find_all('table')
                if len(tables) < 2:
                    return None, None
                per_gram = []
                for tr in tables[1].find_all('tr'):
                    cols = [td.get_text(strip=True) for td in tr.find_all(['th', 'td'])]
                    if len(cols) < 2:
                        continue
                    m = re.match(r'₹\s*([\d,]+)', cols[1])
                    if not m:
                        continue
                    per_gram.append(float(m.group(1).replace(',', '')))
                    if len(per_gram) >= 2:
                        break
                if len(per_gram) >= 2:
                    return per_gram[0] * 10, per_gram[1] * 10
                return None, None

            # Fallback 1: goodreturns.in Mumbai
            try:
                url = "https://www.goodreturns.in/gold-rates/mumbai.html"
                resp = _req.get(url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    today_val, yday_val = _parse_goodreturns_gold(_BS(resp.text, 'html.parser'))
                    if today_val and yday_val:
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
                    today_val, yday_val = _parse_goodreturns_gold(_BS(resp2.text, 'html.parser'))
                    if today_val and yday_val:
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
            Primary:   Yahoo Finance INR=X (live spot rate, matches Google Finance)
            Fallback:  Frankfurter API (ECB daily reference rate, only updates
                       once per business day so it can lag/repeat over weekends)
            """
            try:
                import requests
                hdrs = {"User-Agent": "Mozilla/5.0"}
                resp = requests.get("https://query2.finance.yahoo.com/v8/finance/chart/INR=X?interval=1d&range=5d", headers=hdrs, timeout=10)
                if resp.status_code == 200:
                    result = resp.json()['chart']['result'][0]
                    meta = result.get('meta', {})
                    today, prev = meta.get('regularMarketPrice'), meta.get('chartPreviousClose')
                    if today and prev:
                        print(f"DEBUG [USD/INR]: Yahoo (live) -> today={today}, prev={prev}")
                        return float(today), float(prev)
                    closes = [c for c in result['indicators']['quote'][0]['close'] if c is not None]
                    if len(closes) >= 2:
                        print(f"DEBUG [USD/INR]: Yahoo (closes) -> today={closes[-1]}, prev={closes[-2]}")
                        return float(closes[-1]), float(closes[-2])
            except Exception as e:
                print(f"DEBUG [USD/INR]: Yahoo failed ({e}), trying Frankfurter...")

            # Frankfurter fallback
            try:
                import requests
                resp = requests.get("https://api.frankfurter.dev/v1/latest?base=USD&symbols=INR", timeout=10)
                if resp.status_code == 200:
                    rate = resp.json()['rates']['INR']
                    from datetime import datetime, timedelta
                    for idx in range(1, 8):
                        yday_str = (datetime.now() - timedelta(days=idx)).strftime('%Y-%m-%d')
                        y_resp = requests.get(f"https://api.frankfurter.dev/v1/{yday_str}?base=USD&symbols=INR", timeout=10)
                        if y_resp.status_code == 200:
                            y_rate = y_resp.json()['rates']['INR']
                            if y_rate != rate:
                                print(f"DEBUG [USD/INR]: Frankfurter -> today={rate}, yday={y_rate}")
                                return rate, y_rate
            except Exception as e:
                print(f"DEBUG [USD/INR]: Frankfurter fallback failed ({e})")
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

        # Same order and number formats as the Day21 cards
        markets = [
            build_entry(s_now, s_prev, "Sensex",     lambda v: f"{v:,.2f}"),
            build_entry(n_now, n_prev, "Nifty 50",   lambda v: f"{v:,.2f}"),
            build_entry(u_now, u_prev, "USD / INR",  lambda v: f"₹{v:.2f}"),
            build_entry(g_now, g_prev, "Gold 24K",   lambda v: f"₹{int(round(v)):,}"),
        ]
        return jsonify({"markets": markets})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@day21_editor_bp.route("/api/reset", methods=["POST"])
def api_reset():
    global _current_html
    _current_html = BASE_HTML
    return jsonify({"success": True})


@day21_editor_bp.route("/api/import_json", methods=["POST"])
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
    test_app = Flask(__name__, template_folder="templates")
    test_app.register_blueprint(day21_editor_bp)
    test_app.run(debug=True, host="0.0.0.0", port=5000)
