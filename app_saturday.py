"""

Newsband — Saturday Edition Editor (Day 23)

Blueprint : day23_editor, mounted at /day23-editor by app.py
Template  : Day23.html  (Saturday layout — no market ticker)
            [01 top story] [AQI strip | 02 | 03] [04 image-left] [05 image-right]
Page      : templates/editor_saturday.html

How it works
  * The template file is re-read on every render, so design tweaks to
    Day23.html show up without restarting.
  * Only the elements listed in find_parts() are edited (BeautifulSoup).
    Layout, CSS, logo and footer are never touched.
  * The editor state is auto-saved to saturday_draft.json and read back on
    every request, so a restart, a closed tab or a second server worker
    doesn't lose the issue in progress. "Reset" deletes the draft.
  * /api/import_json accepts the Batch Extractor's {"stories": [...]} payload.
"""

import io
import json
import os
import re
from datetime import datetime

from bs4 import BeautifulSoup, NavigableString
from bs4.dammit import EntitySubstitution
from bs4.formatter import HTMLFormatter
from flask import Blueprint, Response, jsonify, render_template, request, send_file

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_FILE = os.path.join(BASE_DIR, "Day23.html")
DRAFT_FILE = os.path.join(BASE_DIR, "saturday_draft.json")
URL_PREFIX = "/day23-editor"

# Category corner-tab icons live here as <theme-key>.png
ICON_BASE = "https://raw.githubusercontent.com/Manas236/Newsband/main/icons/"

# ── Category themes ───────────────────────────────────────────────────────────
# pill_bg / pill_fg colour the category pill; accent colours the corner tab
# (and the short bar under the top story). The first five match Day23.html.
THEMES = {
    "technology":    {"label": "Technology",    "pill_bg": "#e0e7ff", "pill_fg": "#4338ca", "accent": "#4f46e5",
                      "aliases": ["tech", "ai", "gadgets"]},
    "business":      {"label": "Business",      "pill_bg": "#dcfce7", "pill_fg": "#15803d", "accent": "#16a34a",
                      "aliases": ["markets", "economy", "finance", "money"]},
    "world":         {"label": "World",         "pill_bg": "#ede9fe", "pill_fg": "#6d28d9", "accent": "#7c3aed",
                      "aliases": ["international", "global"]},
    "sports":        {"label": "Sports",        "pill_bg": "#fee2e2", "pill_fg": "#b91c1c", "accent": "#dc2626",
                      "aliases": ["sport", "cricket", "football"]},
    "entertainment": {"label": "Entertainment", "pill_bg": "#fef3c7", "pill_fg": "#92400e", "accent": "#d97706",
                      "aliases": ["film", "movies", "bollywood", "music", "culture"]},
    "india":         {"label": "India",         "pill_bg": "#ffedd5", "pill_fg": "#9a3412", "accent": "#ea580c",
                      "aliases": ["national", "nation"]},
    "politics":      {"label": "Politics",      "pill_bg": "#dbeafe", "pill_fg": "#1d4ed8", "accent": "#2563eb",
                      "aliases": ["elections", "government"]},
    "health":        {"label": "Health",        "pill_bg": "#ccfbf1", "pill_fg": "#0f766e", "accent": "#0d9488",
                      "aliases": ["wellness", "medicine"]},
    "science":       {"label": "Science",       "pill_bg": "#cffafe", "pill_fg": "#155e75", "accent": "#0891b2",
                      "aliases": ["space"]},
    "environment":   {"label": "Environment",   "pill_bg": "#ecfccb", "pill_fg": "#3f6212", "accent": "#65a30d",
                      "aliases": ["climate", "weather"]},
    "lifestyle":     {"label": "Lifestyle",     "pill_bg": "#fce7f3", "pill_fg": "#be185d", "accent": "#db2777",
                      "aliases": ["food", "travel", "fashion"]},
}

# ── AQI scales (bands low → high; the strip shows them bottom → top) ─────────
AQI_SCALES = {
    "cpcb": {
        "label": "CPCB (India)",
        "bands": [
            {"key": "good",         "name": "Good",         "max": 50,   "color": "#009865"},
            {"key": "satisfactory", "name": "Satisfactory", "max": 100,  "color": "#a3c853"},
            {"key": "moderate",     "name": "Moderate",     "max": 200,  "color": "#fff833"},
            {"key": "poor",         "name": "Poor",         "max": 300,  "color": "#f29c33"},
            {"key": "very_poor",    "name": "Very Poor",    "max": 400,  "color": "#e93f33"},
            {"key": "severe",       "name": "Severe",       "max": None, "color": "#af2d24"},
        ],
    },
    "us_epa": {
        "label": "US EPA (IQAir etc.)",
        "bands": [
            {"key": "good",           "name": "Good",           "max": 50,   "color": "#00e400"},
            {"key": "moderate",       "name": "Moderate",       "max": 100,  "color": "#ffff00"},
            {"key": "usg",            "name": "Unhealthy (SG)", "max": 150,  "color": "#ff7e00"},
            {"key": "unhealthy",      "name": "Unhealthy",      "max": 200,  "color": "#ff0000"},
            {"key": "very_unhealthy", "name": "Very Unhealthy", "max": 300,  "color": "#8f3f97"},
            {"key": "hazardous",      "name": "Hazardous",      "max": None, "color": "#7e0023"},
        ],
    },
}
AQI_NA_COLOR = "#c7cdea"   # pill colour when the score isn't a number
AQI_NAVY = "#1b2550"       # strip background; also dark text on light pills

AQI_KEYS = ("location", "value", "scale", "band", "label", "recorded", "source")
STORY_KEYS = ("category", "theme", "tag", "headline", "summary", "image", "link")

day23_editor_bp = Blueprint("day23_editor", __name__)


class _TemplateFormatter(HTMLFormatter):
    """Escape only & < >, keep the template's attribute order, write <img ...> not <img .../>."""
    def attributes(self, tag):
        return list(tag.attrs.items())


OUTPUT_FORMATTER = _TemplateFormatter(
    entity_substitution=EntitySubstitution.substitute_xml,
    void_element_close_prefix=None,
)


# ── Small helpers ─────────────────────────────────────────────────────────────

def _norm(s):
    return re.sub(r"\s+", "", s or "").lower()


def _has(tag, needle):
    """True if the tag's inline style contains `needle` (whitespace-insensitive)."""
    return _norm(needle) in _norm(tag.get("style"))


def _text(tag):
    return " ".join(tag.get_text().split()) if tag is not None else ""


def _set_text(tag, text):
    if tag is None:
        return
    tag.clear()
    tag.append(NavigableString(text))


def get_style_prop(style, prop):
    m = re.search(r"(?<![\w-])" + re.escape(prop) + r"\s*:\s*([^;]*)", style or "", re.I)
    return m.group(1).strip() if m else ""


def set_style_prop(style, prop, value):
    """Replace one CSS property in an inline style, keeping everything else as is.
    `background` never matches `background-image`; `color` never matches `background-color`."""
    style = style or ""
    pat = re.compile(r"(?<![\w-])(" + re.escape(prop) + r")\s*:\s*[^;]*", re.I)
    if pat.search(style):
        return pat.sub(lambda m: f"{m.group(1)}:{value}", style, count=1)
    s = style.rstrip()
    if s and not s.endswith(";"):
        s += ";"
    return (s + f" {prop}:{value};").strip()


def _luminance(hex_color):
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    def chan(c):
        c = int(c, 16) / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = chan(h[0:2]), chan(h[2:4]), chan(h[4:6])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def readable_text_on(bg):
    """Navy or white — whichever reads better on `bg`."""
    lum = _luminance(bg)
    on_navy = (lum + 0.05) / (_luminance(AQI_NAVY) + 0.05)
    on_white = 1.05 / (lum + 0.05)
    return AQI_NAVY if on_navy >= on_white else "#ffffff"


def _to_int(v):
    s = str(v if v is not None else "").strip()
    return int(s) if re.fullmatch(r"\d{1,4}", s) else None


def auto_band_index(score, bands):
    if score is None:
        return None
    for i, b in enumerate(bands):
        if b["max"] is None or score <= b["max"]:
            return i
    return len(bands) - 1


def theme_for_category(label):
    """Match a typed category ('Tech', 'Cricket', 'National') to a theme key, or None."""
    k = (label or "").strip().lower()
    if not k:
        return None
    for key, t in THEMES.items():
        if k == key or k == t["label"].lower() or k in t["aliases"]:
            return key
    return None


def _valid_image(url):
    return bool(re.match(r"^https?://\S+$", (url or "").strip()))


def _normalize_link(link):
    link = (link or "").strip()
    if not link:
        return "#"
    if re.match(r"^(https?:|mailto:|tel:|#|\*\|)", link, re.I):
        return link
    return "https://" + link


# ── Locate every editable element in the template ─────────────────────────────

def _card_parts(card):
    tds = card.find_all("td")
    imgs = card.find_all("img")
    hero = next((i for i in imgs if i.parent is not None and i.parent.name == "a"), None)
    icon = next((i for i in imgs if i is not hero), None)
    return {
        "cat": next((td for td in tds if _has(td, "border-radius:999px") and _has(td, "text-transform:uppercase")), None),
        # card 01 only: the "· Top story" kicker next to the category pill
        "tag": next((td for td in tds if _has(td, "text-transform:uppercase") and not _has(td, "border-radius:999px")), None),
        "title": card.find("a", class_="card-title"),
        "summary": card.find("p"),
        "hero": hero,
        "icon": icon,
        "tab": icon.parent if icon is not None else None,
        # card 01 only: the short accent bar above the summary
        "bar": next((d for d in card.find_all("div") if _has(d, "height:3px")), None),
        "links": card.find_all("a"),
    }


def _aqi_parts(soup):
    strip = next((td for td in soup.find_all("td") if _has(td, f"background:{AQI_NAVY}")), None)
    if strip is None:
        return None
    divs = strip.find_all("div")

    def value_after(label):
        for d in divs:
            if _text(d).lower() == label:
                return d.find_next_sibling("div")
        return None

    band_cells = [td for td in strip.find_all("td") if td.get("width") == "8"]  # top → bottom
    return {
        "location": next((d for d in divs if _has(d, "letter-spacing:1.6px")), None),
        "value": next((d for d in divs if _has(d, "font-size:46px")), None),
        "pill": next((td for td in strip.find_all("td") if _has(td, "border-radius:999px")), None),
        "band_cells": band_cells,
        "markers": [c.find_next_sibling("td") for c in band_cells],
        "recorded": value_after("recorded"),
        "source": value_after("source"),
    }


def find_parts(soup):
    date_div = rni_div = None
    for div in soup.find_all("div"):
        t = _text(div)
        if date_div is None and t.startswith("Date:"):
            date_div = div
        elif rni_div is None and t.startswith("RNI:"):
            rni_div = div
    cards = [td for td in soup.find_all("td") if _has(td, "border:1px solid #e6e8ee")]  # 01..05 in order
    return {
        "date": date_div,
        "rni": rni_div,
        "aqi": _aqi_parts(soup),
        "cards": [_card_parts(c) for c in cards],
    }


# ── Template → state ──────────────────────────────────────────────────────────

def parse_state(html):
    P = find_parts(BeautifulSoup(html, "html.parser"))
    state = {
        "date": _text(P["date"]).replace("Date:", "", 1).strip(),
        "rni": _text(P["rni"]).replace("RNI:", "", 1).strip(),
        "aqi": {},
        "stories": [],
    }

    A = P["aqi"]
    if A:
        low_to_high = list(reversed(A["band_cells"]))
        colors = [get_style_prop(c.get("style"), "background").lower() for c in low_to_high]
        scale_key = next((k for k, s in AQI_SCALES.items()
                          if [b["color"] for b in s["bands"]] == colors), "cpcb")
        bands = AQI_SCALES[scale_key]["bands"]
        value = _text(A["value"])
        marked = next((i for i, m in enumerate(reversed(A["markers"])) if m is not None and _text(m)), None)
        auto_idx = auto_band_index(_to_int(value), bands)
        band = "auto" if marked is None or marked == auto_idx else bands[marked]["key"]
        shown = bands[marked]["name"] if marked is not None else ""
        pill_text = _text(A["pill"])
        state["aqi"] = {
            "location": _text(A["location"]),
            "value": value,
            "scale": scale_key,
            "band": band,
            "label": "" if pill_text == shown else pill_text,
            "recorded": _text(A["recorded"]),
            "source": _text(A["source"]),
        }

    for c in P["cards"]:
        theme = ""
        if c["icon"] is not None:
            key = os.path.splitext(os.path.basename(c["icon"].get("src", "")))[0]
            theme = key if key in THEMES else ""
        if not theme and c["tab"] is not None:
            accent = get_style_prop(c["tab"].get("style"), "background").lower()
            theme = next((k for k, t in THEMES.items() if t["accent"] == accent), "")
        story = {
            "category": _text(c["cat"]),
            "theme": theme,
            "headline": _text(c["title"]),
            "summary": _text(c["summary"]),
            "image": c["hero"].get("src", "") if c["hero"] is not None else "",
            "link": c["links"][0].get("href", "#") if c["links"] else "#",
        }
        if c["tag"] is not None:
            story["tag"] = _text(c["tag"]).lstrip("·").strip()
        state["stories"].append(story)
    return state


# ── State → HTML ──────────────────────────────────────────────────────────────

def _render_aqi(A, aqi):
    scale = AQI_SCALES.get(aqi.get("scale")) or AQI_SCALES["cpcb"]
    bands = scale["bands"]
    raw_value = str(aqi.get("value", "")).strip()
    score = _to_int(raw_value)

    band_key = aqi.get("band") or "auto"
    if band_key == "auto":
        idx = auto_band_index(score, bands)
    else:
        idx = next((i for i, b in enumerate(bands) if b["key"] == band_key), None)

    if "location" in aqi:
        _set_text(A["location"], aqi["location"])
    _set_text(A["value"], raw_value or "—")
    if "recorded" in aqi:
        _set_text(A["recorded"], aqi["recorded"])
    if "source" in aqi:
        _set_text(A["source"], aqi["source"])

    # Scale colours: band_cells run top → bottom, bands run low → high
    for cell, band in zip(reversed(A["band_cells"]), bands):
        cell["style"] = set_style_prop(cell.get("style"), "background", band["color"])

    # ◀ marker beside today's band
    for j, m in enumerate(reversed(A["markers"])):
        if m is None:
            continue
        if j == idx:
            _set_text(m, "◀")
            m["style"] = set_style_prop(m.get("style"), "line-height", "10px")
        else:
            m.clear()

    # Category pill
    if A["pill"] is not None:
        if idx is not None:
            bg, label = bands[idx]["color"], (aqi.get("label") or "").strip() or bands[idx]["name"]
        else:
            bg, label = AQI_NA_COLOR, (aqi.get("label") or "").strip() or "N/A"
        style = set_style_prop(A["pill"].get("style"), "background", bg)
        A["pill"]["style"] = set_style_prop(style, "color", readable_text_on(bg))
        _set_text(A["pill"], label)


def _apply_theme(c, key):
    t = THEMES.get(key)
    if not t:
        return  # unknown theme: leave the template's colours alone
    if c["cat"] is not None:
        style = set_style_prop(c["cat"].get("style"), "background", t["pill_bg"])
        c["cat"]["style"] = set_style_prop(style, "color", t["pill_fg"])
    if c["tab"] is not None:
        c["tab"]["style"] = set_style_prop(c["tab"].get("style"), "background", t["accent"])
    if c["icon"] is not None:
        c["icon"]["src"] = ICON_BASE + t.get("icon", key + ".png")
    if c["bar"] is not None:
        c["bar"]["style"] = set_style_prop(c["bar"].get("style"), "background", t["accent"])


def render(template_html, state):
    soup = BeautifulSoup(template_html, "html.parser")
    P = find_parts(soup)

    if "date" in state:
        _set_text(P["date"], f"Date: {state['date']}".rstrip())
    if "rni" in state:
        _set_text(P["rni"], f"RNI: {state['rni']}".rstrip())

    if P["aqi"] and state.get("aqi"):
        _render_aqi(P["aqi"], state["aqi"])

    for c, s in zip(P["cards"], state.get("stories", [])):
        if "category" in s:
            _set_text(c["cat"], s["category"])
        _apply_theme(c, s.get("theme", ""))
        if c["tag"] is not None and "tag" in s:
            _set_text(c["tag"], f"· {s['tag']}" if s["tag"].strip() else "")
        if "headline" in s:
            _set_text(c["title"], s["headline"])
            if c["hero"] is not None:
                c["hero"]["alt"] = s["headline"]
        if "summary" in s:
            _set_text(c["summary"], s["summary"])
        if c["hero"] is not None and _valid_image(s.get("image")):
            c["hero"]["src"] = s["image"].strip()
        if "link" in s:
            href = _normalize_link(s["link"])
            for a in c["links"]:
                a["href"] = href

    html = soup.decode(formatter=OUTPUT_FORMATTER)
    # Put back the template's entities so the export stays plain ASCII where it was
    return (html.replace(">◀</td>", ">&#9664;</td>")
                .replace(" ", "&nbsp;")
                .replace("·", "&middot;"))


# ── Pre-send checks ───────────────────────────────────────────────────────────

def check(state):
    warnings = []
    d = (state.get("date") or "").strip()
    try:
        dt = datetime.strptime(d, "%d/%m/%Y")
        if dt.weekday() != 5:
            warnings.append(f"Date {d} is a {dt:%A}; this is the Saturday template.")
    except ValueError:
        warnings.append("Date should be in DD/MM/YYYY format.")

    aqi = state.get("aqi") or {}
    if aqi and _to_int(aqi.get("value")) is None and (aqi.get("band") or "auto") == "auto":
        warnings.append("AQI score isn't a number, so the strip shows N/A.")
    if aqi and not (aqi.get("source") or "").strip():
        warnings.append("AQI source is empty.")

    for i, s in enumerate(state.get("stories", []), 1):
        n = f"Story {i:02d}"
        img = (s.get("image") or "").strip()
        if not _valid_image(img):
            warnings.append(f"{n}: image URL is missing or not a link.")
        elif "placehold.co" in img:
            warnings.append(f"{n}: image is still the placeholder.")
        if _normalize_link(s.get("link")) == "#":
            warnings.append(f"{n}: no article link.")
        if not (s.get("headline") or "").strip():
            warnings.append(f"{n}: headline is empty.")
    return warnings


# ── State store (draft on disk) ───────────────────────────────────────────────

def load_template():
    with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
        return f.read()


def load_draft():
    try:
        with open(DRAFT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) and isinstance(data.get("stories"), list) else None
    except (OSError, ValueError):
        return None


def save_draft(state):
    tmp = DRAFT_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DRAFT_FILE)


def merge_state(current, patch):
    """Apply a full or partial state (form data or pasted JSON) onto `current`."""
    out = json.loads(json.dumps(current))
    for k in ("date", "rni"):
        if k in patch and patch[k] is not None:
            out[k] = str(patch[k]).strip()

    if isinstance(patch.get("aqi"), dict):
        aqi = out.setdefault("aqi", {})
        for k in AQI_KEYS:
            if k in patch["aqi"] and patch["aqi"][k] is not None:
                aqi[k] = str(patch["aqi"][k]).strip()
        if aqi.get("scale") not in AQI_SCALES:
            aqi["scale"] = "cpcb"
        valid_bands = {b["key"] for b in AQI_SCALES[aqi["scale"]]["bands"]}
        if aqi.get("band") not in valid_bands:
            aqi["band"] = "auto"

    if isinstance(patch.get("stories"), list):
        for i, sp in enumerate(patch["stories"]):
            if not isinstance(sp, dict):
                continue
            idx = sp.get("index", i)
            if not isinstance(idx, int) or not 0 <= idx < len(out["stories"]):
                continue
            story = out["stories"][idx]
            for k in STORY_KEYS:
                if k in sp and sp[k] is not None:
                    story[k] = str(sp[k]).strip()
            # Pasted JSON often has a category but no theme: pick one from the name
            if "category" in sp and "theme" not in sp:
                matched = theme_for_category(sp["category"])
                if matched:
                    story["theme"] = matched
            if story.get("theme") not in THEMES:
                story["theme"] = ""
    return out


def current_state():
    """The template's content with the saved draft on top.

    Read from disk on every request (not cached in a global) so every server
    worker sees the same issue and an export never comes from a stale copy."""
    base = parse_state(load_template())
    draft = load_draft()
    return merge_state(base, draft) if draft else base


def _payload(state, include_state=True):
    html = render(load_template(), state)
    out = {"html": html, "warnings": check(state), "draft": os.path.exists(DRAFT_FILE)}
    if include_state:
        out["state"] = state
    return out


def _export_name(state):
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", (state.get("date") or "").strip())
    stamp = f"{int(m.group(1)):02d}-{int(m.group(2)):02d}-{m.group(3)}" if m else datetime.now().strftime("%d-%m-%Y")
    return f"Newsband_Saturday_{stamp}.html"


# ── Routes ────────────────────────────────────────────────────────────────────

@day23_editor_bp.route("/")
def editor():
    return render_template("editor_saturday.html", api_prefix=URL_PREFIX)


@day23_editor_bp.route("/api/state")
def api_state():
    data = _payload(current_state())
    data["themes"] = {k: {kk: vv for kk, vv in t.items()} for k, t in THEMES.items()}
    data["scales"] = AQI_SCALES
    data["template"] = os.path.basename(TEMPLATE_FILE)
    return jsonify(data)


@day23_editor_bp.route("/api/update", methods=["POST"])
@day23_editor_bp.route("/api/import_json", methods=["POST"])  # Batch Extractor "send"
def api_update():
    """Body: full or partial state. Returns rendered HTML, warnings and the merged state."""
    patch = request.get_json(silent=True)
    if not isinstance(patch, dict):
        return jsonify({"success": False, "error": "Body must be a JSON object"}), 400
    state = merge_state(current_state(), patch)
    save_draft(state)
    return jsonify({"success": True, **_payload(state)})


@day23_editor_bp.route("/api/preview")
def api_preview():
    return Response(render(load_template(), current_state()), mimetype="text/html; charset=utf-8")


@day23_editor_bp.route("/api/export")
def api_export():
    state = current_state()
    buf = io.BytesIO(render(load_template(), state).encode("utf-8"))
    return send_file(buf, as_attachment=True, download_name=_export_name(state), mimetype="text/html")


@day23_editor_bp.route("/api/reset", methods=["POST"])
def api_reset():
    try:
        os.remove(DRAFT_FILE)
    except OSError:
        pass
    return jsonify({"success": True, **_payload(current_state())})
