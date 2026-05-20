"""
Newsband Newsletter Editor — Day12(2) Flask Backend
Uses BeautifulSoup4 for controlled, field-level HTML editing.
Footer, layout structure, CSS, and logo are strictly locked.

Based on editor(for Day12.html).py with market section support
adapted from editor(for Day15.html).py.
"""

import io
import re
from flask import Blueprint, request, jsonify, render_template, send_file, Response
from bs4 import BeautifulSoup, NavigableString

day12_2_editor_bp = Blueprint('day12_2_editor', __name__)

# ── Load base template once at startup ────────────────────────────────────────
with open("Day12(2).html", "r", encoding="utf-8") as f:
    BASE_HTML = f.read()
    print(f"DEBUG [Day12_2]: BASE_HTML length: {len(BASE_HTML)}")

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


def _find_articles(soup):
    """
    Return a list of article containers. Day12(2) has 5 articles:
      [0] Featured article   — direct <a> child wrapping a full table
      [1] Article 1           — horizontal card (image left, text right)
      [2] Article 2           — horizontal card
      [3] Left grid card      — vertical card in two-column grid
      [4] Right grid card     — vertical card in two-column grid
    Each article is wrapped in an <a> tag with style containing
    "text-decoration:none" and "display:block".
    """
    articles = []
    for a_tag in soup.find_all("a"):
        style = a_tag.get("style", "")
        if "text-decoration:none" in style and "display:block" in style:
            # Skip footer links (social icons, website, etc.)
            parent_td = a_tag.find_parent("td")
            if parent_td:
                parent_style = parent_td.get("style", "")
                if "background-color:#0a0a0a" in parent_style:
                    continue
            articles.append(a_tag)
    return articles


def _find_category(article_a):
    """Find category <p> tag. Category paragraphs have letter-spacing:1.5px and text-transform:uppercase."""
    for p in article_a.find_all("p"):
        style = p.get("style", "")
        if "letter-spacing:1.5px" in style and "text-transform:uppercase" in style:
            return p
    return None


def _find_headline(article_a):
    """Find headline tag — could be h1, h2, or h3."""
    for tag_name in ["h1", "h2", "h3"]:
        tag = article_a.find(tag_name)
        if tag:
            return tag
    return None


def _find_summary(article_a):
    """Find the summary paragraph — text-align:justify, color:#555555."""
    for p in article_a.find_all("p"):
        style = p.get("style", "")
        if "text-align:justify" in style and "color:#555555" in style:
            return p
    return None


def _find_image(article_a):
    """Find the main <img> tag in the article (not button icons)."""
    for img in article_a.find_all("img"):
        style = img.get("style", "")
        if "border-radius" in style and "width:100%" in style:
            return img
    return None


# ── Market section helpers ────────────────────────────────────────────────────

def _find_market_data(soup):
    """
    Find the markets section data in Day12(2).html.
    The market section is a 1×4 dark ticker strip (background-color:#0f172a).
    Returns list of 4 dicts (Sensex, Nifty, USD/INR, Gold).
    """
    markets = []

    dark_td = None
    for td in soup.find_all("td"):
        if "background-color:#0f172a" in td.get("style", ""):
            dark_td = td
            break

    if not dark_td:
        return markets

    ticker_cells = [
        td for td in dark_td.find_all("td")
        if td.get("valign") == "top" and td.get("width") == "25%"
    ]

    for cell in ticker_cells:
        divs = cell.find_all("div")
        if len(divs) >= 3:
            market = {
                "label": divs[0].get_text().strip(),
                "value": divs[1].get_text().strip(),
                "change": divs[2].get_text().strip(),
            }
            market["positive"] = "color:#10b981" in divs[2].get("style", "")
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
        result["date"] = get_tomorrow_date_str()

    # Header — RNI
    rni_div = _find_header_rni(soup)
    if rni_div:
        result["rni"] = rni_div.get_text().replace("RNI:", "").strip()

    # Stories
    stories = []
    articles = _find_articles(soup)
    for i, article in enumerate(articles):
        story = {"index": i}

        story["link"] = article.get("href", "")

        cat = _find_category(article)
        if cat:
            story["category"] = cat.get_text().strip()

        hl = _find_headline(article)
        if hl:
            story["headline"] = hl.get_text().strip()

        summ = _find_summary(article)
        if summ:
            story["summary"] = summ.get_text().strip()

        img = _find_image(article)
        if img:
            story["image"] = img.get("src", "")

        stories.append(story)

    result["stories"] = stories

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

    # Stories
    articles = _find_articles(soup)
    for story_data in data.get("stories", []):
        idx = story_data.get("index", 0)
        if idx >= len(articles):
            continue
        article = articles[idx]

        # Link (href on the <a> tag)
        link = (story_data.get("link") or "").strip()
        if link:
            article["href"] = link

        # Category
        cat = (story_data.get("category") or "").strip()
        if cat:
            cat_tag = _find_category(article)
            if cat_tag:
                _set_text(cat_tag, cat.upper())

        # Headline
        hl = (story_data.get("headline") or "").strip()
        if hl:
            hl_tag = _find_headline(article)
            if hl_tag:
                _set_text(hl_tag, hl)

        # Summary
        summ = (story_data.get("summary") or "").strip()
        if summ:
            sum_tag = _find_summary(article)
            if sum_tag:
                _set_text(sum_tag, summ)

        # Image URL — update img src
        img_url = (story_data.get("image") or "").strip()
        if img_url:
            if img_url.startswith(("http://", "https://")):
                img_tag = _find_image(article)
                if img_tag:
                    img_tag["src"] = img_url

    # Markets
    markets_data = data.get("markets", [])
    if markets_data:
        dark_td = None
        for td in soup.find_all("td"):
            if "background-color:#0f172a" in td.get("style", ""):
                dark_td = td
                break

        if dark_td:
            ticker_cells = [
                td for td in dark_td.find_all("td")
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
                    change = (mkt.get("change") or "").strip()
                    if change:
                        _set_text(divs[2], change)
                    positive = mkt.get("positive", True)
                    color = "#10b981" if positive else "#ef4444"
                    existing_style = divs[2].get("style", "")
                    divs[2]["style"] = re.sub(
                        r'color:#[0-9a-fA-F]{6}', f'color:{color}', existing_style)

    return str(soup)


# ── Routes ────────────────────────────────────────────────────────────────────

@day12_2_editor_bp.route("/")
def editor():
    return render_template("editor_day12_2.html", api_prefix="/day12-2-editor")


@day12_2_editor_bp.route("/api/fields")
def api_fields():
    return jsonify(parse_fields(_current_html))


@day12_2_editor_bp.route("/api/update", methods=["POST"])
def api_update():
    global _current_html
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON body"}), 400
    _current_html = update_html(_current_html, data)
    return jsonify({"success": True, "html": _current_html})


@day12_2_editor_bp.route("/api/preview")
def api_preview():
    return Response(_current_html, mimetype="text/html; charset=utf-8")


@day12_2_editor_bp.route("/api/export")
def api_export():
    buf = io.BytesIO(_current_html.encode("utf-8"))
    return send_file(
        buf,
        as_attachment=True,
        download_name="newsband_day12_2_newsletter.html",
        mimetype="text/html",
    )


@day12_2_editor_bp.route("/api/markets/fetch")
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
            Fallback1: bankbazaar.com gold rate page
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
                                # Check for N/A or empty values
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
            # Convert to INR per 10 grams:
            #   1 troy oz = 31.1035 grams
            #   price_inr_per_10g = (gold_usd / 31.1035) * 10 * usd_inr
            try:
                import requests
                # Get gold price in USD
                gold_url = "https://query2.finance.yahoo.com/v8/finance/chart/GC=F?interval=1d&range=5d"
                gold_resp = requests.get(gold_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
                if gold_resp.status_code == 200:
                    gold_data = gold_resp.json()
                    gold_result = gold_data['chart']['result'][0]
                    gold_closes = gold_result['indicators']['quote'][0]['close']
                    valid_gold = [c for c in gold_closes if c is not None]

                    # Get USD/INR rate
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
                        # Convert: USD per troy oz -> INR per 10g
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

        def build_entry(now, prev, label, value_fmt, chg_dec=2):
            if now is None or prev is None:
                return {"label": label, "value": "N/A", "change": "N/A", "positive": True}
            chg = now - prev
            pct = (chg / prev) * 100
            arrow = "▲" if chg >= 0 else "▼"
            sign = "+" if pct >= 0 else "−"
            chg_str = f"{arrow} {abs(chg):,.{chg_dec}f}  ({sign}{abs(pct):.2f}%)"
            return {"label": label, "value": value_fmt(now), "change": chg_str, "positive": chg >= 0}

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
            build_entry(g_now, g_prev, "GOLD 24K (MUMBAI)", lambda v: f"{int(round(v)):,}", chg_dec=0),
        ]
        return jsonify({"markets": markets})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@day12_2_editor_bp.route("/api/reset", methods=["POST"])
def api_reset():
    global _current_html
    _current_html = BASE_HTML
    return jsonify({"success": True})


@day12_2_editor_bp.route("/api/import_json", methods=["POST"])
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
    test_app.register_blueprint(day12_2_editor_bp)
    test_app.run(debug=True, host="0.0.0.0", port=5000)
