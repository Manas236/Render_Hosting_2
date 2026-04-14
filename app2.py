"""
Newsband Newsletter Template Editor
Flask app — two-panel live editor for the Newsband email HTML template.

Usage:
  python app.py
  Open http://127.0.0.1:5000
"""

from flask import Flask, request, redirect, Response, session, render_template_string, url_for
from bs4 import BeautifulSoup, NavigableString, Comment
from functools import wraps
import os
import re
import logging

app = Flask(__name__)
app.secret_key = 'newsband-secret-key-2024'
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024  # 2 MB limit
logging.basicConfig(level=logging.INFO)

ALLOWED_EXTENSIONS = {"html", "htm"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# ─────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────
VALID_USERNAME = 'newsband'
VALID_PASSWORD = 'Journalism'
LOGO_URL = "https://raw.githubusercontent.com/Manas236/Newsband/main/newsband-logo-0022.png"


def require_login(f):
    """Decorator — redirects to login page if user is not authenticated."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────
ORIGINAL_FILE = "template1.html"
GITHUB_BASE   = "https://raw.githubusercontent.com/Manas236/Newsband/main/"

# Tags we care about when indexing the document
TEXT_TAGS    = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "td", "span", "strong"}
ALL_EDITABLE = TEXT_TAGS | {"img", "a"}

# Protected URL (immutable)
PROTECTED_URL_BASE = "https://singlecolorimage.com"

# ── Section-level access control ──────────────────────────────────────────────
# Any section comment containing one of these keywords (case-insensitive) is
# completely locked — no elements inside it will appear in the editor.
FOOTER_SECTION_KEYWORDS  = {"footer"}

# Sidebar sections are partially locked: only Date and RNI Number fields show.
SIDEBAR_SECTION_KEYWORDS = {"sidebar"}

# Regex that matches text belonging to a Date or RNI Number field.
_SIDEBAR_ALLOWED_RE = re.compile(
    r'rni'
    r'|(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)'
    r'|(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?'
    r'|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)'
    r'|\b\d{1,2}\b'
    r'|\b20\d{2}\b',
    re.I,
)


# ══════════════════════════════════════════════════════════════════
#  UTILITY HELPERS
# ══════════════════════════════════════════════════════════════════

def get_html_file() -> str:
    """Always load the pristine original template."""
    with open(ORIGINAL_FILE, encoding="utf-8") as f:
        return f.read()


def _has_editable_descendant(el) -> bool:
    """Return True if any descendant of el has an editable tag name."""
    return any(
        getattr(d, "name", None) in ALL_EDITABLE
        for d in el.descendants
    )


def wrap_bare_text_nodes(soup) -> None:
    """
    Wrap bare NavigableStrings inside elements that also have editable-tag children.
    This makes raw text nodes addressable via data-editor-id.
    """
    for el in soup.find_all(True):
        has_editable_child = any(
            getattr(c, "name", None) in ALL_EDITABLE for c in el.children
        )
        if not has_editable_child:
            continue
        for child in list(el.children):
            if (
                isinstance(child, NavigableString)
                and not isinstance(child, Comment)
                and child.strip()
            ):
                span = soup.new_tag("span")
                span["data-temp-span"] = "true"
                span.string = str(child)
                child.replace_with(span)


def superscript_ordinal(text: str) -> str:
    """
    Convert ordinal suffixes (1st, 2nd, 3rd, 4th, etc.) to Unicode superscripts.
    If text already has Unicode superscripts, it remains unchanged.
    """
    text = re.sub(r'(\d+)th', r'\1ᵗʰ', text)
    text = re.sub(r'(\d+)st', r'\1ˢᵗ', text)
    text = re.sub(r'(\d+)nd', r'\1ⁿᵈ', text)
    text = re.sub(r'(\d+)rd', r'\1ʳᵈ', text)
    return text


def _is_sidebar_allowed(text: str) -> bool:
    """Return True if element text belongs to the Date or RNI Number field."""
    return bool(_SIDEBAR_ALLOWED_RE.search(text.strip()))


def _section_is_footer(section: str) -> bool:
    s = section.lower()
    return any(kw in s for kw in FOOTER_SECTION_KEYWORDS)


def _section_is_sidebar(section: str) -> bool:
    s = section.lower()
    return any(kw in s for kw in SIDEBAR_SECTION_KEYWORDS)


def is_in_sidebar(node) -> bool:
    """Return True if node is a descendant of the structural sidebar."""
    for p in node.parents:
        if getattr(p, "get", lambda x: None)("id") == "sidebar":
            return True
    return False


def is_in_footer(node) -> bool:
    """Return True if node is a descendant of the structural footer."""
    for p in node.parents:
        if getattr(p, "get", lambda x: None)("id") == "footer-cell":
            return True
    return False


# ══════════════════════════════════════════════════════════════════
#  WHITESPACE / LINE-COLLAPSING FIX
# ══════════════════════════════════════════════════════════════════

def collapse_inner_whitespace(html_fragment: str) -> str:
    r"""
    Collapse runs of whitespace (spaces, tabs, newlines) that come from
    source-code indentation inside an HTML element into a single space,
    while preserving intentional <br> / <br/> / <br /> line breaks.

    The problem:
      The newsletter HTML is pretty-printed with deep indentation, e.g.:

          <span style="...">Minor
                                                  rape case: Accused held</span>

      BeautifulSoup's get_text() / decode_contents() preserves those raw
      newlines + spaces, so the editor textarea shows:

          Minor
                                                  rape case: Accused held

    The fix:
      1. Temporarily replace <br> variants with a placeholder.
      2. Collapse all whitespace runs (\s+) into a single space.
      3. Restore <br> placeholders back to actual <br> tags.
      4. Strip leading/trailing whitespace.
    """
    # Step 1: protect <br> variants
    _BR_PLACEHOLDER = "\x00BR\x00"
    out = re.sub(r"<br\s*/?>", _BR_PLACEHOLDER, html_fragment, flags=re.I)

    # Step 2: collapse all whitespace runs to a single space
    out = re.sub(r"\s+", " ", out)

    # Step 3: restore <br> tags
    out = out.replace(_BR_PLACEHOLDER, "<br>")

    # Step 4: clean up spaces around <br> (avoid " <br> " → keep tight)
    out = re.sub(r"\s*<br>\s*", "<br>", out)

    return out.strip()


def load_elements():
    """
    Core indexing engine.
    Walks soup.descendants so section comments are visible inline, enabling
    per-section access control:
       • Footer sections  → entirely excluded from the editor.
       • Sidebar sections → only Date and RNI Number fields are included.

    Returns:
        soup      – the parsed BeautifulSoup tree (with IDs stamped)
        elements  – list of dicts: {id, type, tag, text, inner_html, el, visible}
    """
    html = get_html_file()
    soup = BeautifulSoup(html, "html.parser")
    wrap_bare_text_nodes(soup)

    elements       = []
    counter        = 0
    current_section = ""   # tracks the most recent HTML comment text

    for node in soup.descendants:

        # ── Track section comments ────────────────────────────────
        if isinstance(node, Comment):
            current_section = str(node).strip()
            continue

        # Only process Tag nodes
        if not getattr(node, "name", None):
            continue

        tag = node.name
        if tag not in ALL_EDITABLE:
            continue

        # ── Global section visibility logic ──────────────────────
        is_footer  = is_in_footer(node)
        is_sidebar = is_in_sidebar(node)

        # ── IMG ──────────────────────────────────────────────────
        if tag == "img":
            src = (node.get("src") or "").strip()
            if not src:
                continue

            # Skip indexing if it points to the protected URL base
            if PROTECTED_URL_BASE in src:
                continue

            eid = f"el-{counter}"
            node["data-editor-id"] = eid

            visible = not (is_footer or is_sidebar)
            elements.append({
                "id": eid, "type": "img", "tag": tag,
                "text": src, "inner_html": src, "el": node,
                "visible": visible
            })
            counter += 1

        # ── A (links) ────────────────────────────────────────────
        elif tag == "a":
            href = (node.get("href") or "").strip()
            # If it's not a real link, or it's from the protected website, we skip indexing entirely
            if not href or href == "#" or href.startswith("mailto:") or PROTECTED_URL_BASE in href:
                continue

            eid = f"el-{counter}"
            node["data-editor-id"] = eid

            # Visible if not footer/sidebar
            visible = not (is_footer or is_sidebar)

            elements.append({
                "id": eid, "type": "href", "tag": tag,
                "text": href, "inner_html": href, "el": node,
                "visible": visible
            })
            counter += 1

        # ── TEXT NODES ───────────────────────────────────────────
        else:
            # Skip structural wrappers (contain editable children)
            if _has_editable_descendant(node):
                continue

            # td: skip if it has non-<br> element children
            if tag == "td":
                non_br_kids = [
                    c for c in node.children
                    if getattr(c, "name", None) and c.name != "br"
                ]
                if non_br_kids:
                    continue

            if tag == "span" and _has_editable_descendant(node):
                continue

            text = node.get_text()
            if not text.strip():
                continue

            eid = f"el-{counter}"
            node["data-editor-id"] = eid

            # Visibility: matches regex if sidebar; hidden if footer
            visible = True
            if is_footer:
                visible = False
            elif is_sidebar:
                visible = _is_sidebar_allowed(text)

            # Store inner HTML (preserves <br> tags) for accurate export comparison
            inner_html = node.decode_contents()

            # ── FIX: collapse source-code indentation whitespace ──
            inner_html = collapse_inner_whitespace(inner_html)
            text       = collapse_inner_whitespace(text)

            elements.append({
                "id": eid, "type": "text", "tag": tag,
                "text": text, "inner_html": inner_html, "el": node,
                "visible": visible
            })
            counter += 1

    # Collect background images from <td> elements and append as bg-img entries
    bg_elems, counter = extract_td_background_images(soup, counter_start=counter)
    elements.extend(bg_elems)

    return soup, elements


# ══════════════════════════════════════════════════════════════════
#  BACKGROUND-IMAGE EXTRACTOR  (generic, template-independent)
# ══════════════════════════════════════════════════════════════════

# Matches background-image or the background shorthand containing a url()
_TD_BG_URL_RE = re.compile(
    r"background(?:-image)?\s*:\s*url\(\s*['\"]?(.*?)['\"]?\s*\)",
    re.I,
)


def extract_td_background_images(soup, counter_start: int = 0) -> tuple:
    """
    Generic function that scans any BeautifulSoup parse tree for <td> elements
    carrying background images and returns element dicts compatible with the
    load_elements() elements list.

    Detection covers:
      • inline style — background-image: url(...)
      • inline style — background: url(...)  (shorthand)
      • legacy HTML  — background="..."  attribute

    Constraints honoured:
      • Does NOT modify the DOM (no <img> injection, no attribute removal).
      • Does NOT touch rendering or fallback logic.
      • Skips <td> elements already stamped with data-editor-id.
      • Respects the same footer / sidebar visibility rules as load_elements().

    Args:
        soup:          BeautifulSoup parse tree.  load_elements() must have
                       already been called on it so that data-editor-id stamps
                       are present on previously-indexed nodes.
        counter_start: Next free integer for generating unique el-N IDs.

    Returns:
        (bg_elements, next_counter)
        bg_elements  – list of element dicts with type="bg-img".
        next_counter – counter value after all new IDs have been assigned.
    """
    bg_elements: list = []
    counter = counter_start

    for td in soup.find_all("td"):
        # Skip nodes already indexed by load_elements()
        if td.get("data-editor-id"):
            continue

        in_footer  = is_in_footer(td)
        in_sidebar = is_in_sidebar(td)

        # Read both sources independently so the save path can update all of them.
        style_url = ""
        style_str = td.get("style", "")
        if style_str:
            m = _TD_BG_URL_RE.search(style_str)
            if m:
                style_url = m.group(1).strip()

        attr_url = td.get("background", "").strip()

        # Canonical URL shown in the editor: style takes precedence, attr is fallback.
        url = style_url or attr_url
        if not url or PROTECTED_URL_BASE in url:
            continue

        eid = f"el-{counter}"
        td["data-editor-id"] = eid
        counter += 1

        visible = not (in_footer or in_sidebar)

        bg_elements.append({
            "id":            eid,
            "type":          "bg-img",
            "tag":           "td",
            "text":          url,
            "inner_html":    url,
            "el":            td,
            "visible":       visible,
            # Track which locations carry the URL so _process_form can sync all of them.
            "_style_bg_url": style_url,   # empty string if absent
            "_attr_bg_url":  attr_url,    # empty string if absent
        })

    return bg_elements, counter


def fix_link_visibility(elements) -> None:
    """
    Post-process the elements list from load_elements() to ensure EVERY
    structurally distinct <a> tag is visible and editable — not just the
    first occurrence of each href value.

    load_elements() deduplicates by href string, so if multiple <a> tags
    share the same href (e.g. "https://example.com"), only the first one
    gets visible=True.  This function fixes that: every <a> element that
    is NOT in the footer or sidebar is marked visible, preserving the
    original document order.
    """
    for elem in elements:
        if elem["type"] != "href":
            continue
        node = elem["el"]
        # Re-evaluate visibility: visible unless inside footer or sidebar,
        # or if it's pointing to the protected URL base (though these should be skipped by indexing)
        href = (node.get("href") or "").strip()
        if is_in_footer(node) or is_in_sidebar(node) or PROTECTED_URL_BASE in href:
            elem["visible"] = False
        else:
            elem["visible"] = True


def load_section_comments(soup) -> dict:
    """
    Must be called after load_elements() (data-editor-id already stamped).
    Walks document order; maps element_id → nearest preceding HTML comment.
    """
    mapping  = {}
    pending  = None

    for node in soup.descendants:
        if isinstance(node, Comment):
            pending = str(node).strip()
        elif hasattr(node, "get") and node.get("data-editor-id") and pending:
            eid = node["data-editor-id"]
            if eid not in mapping:
                mapping[eid] = pending
            pending = None

    return mapping


def load_style_controls(soup) -> list:
    """
    Must be called after load_elements().
    Walks the tree extracting specific CSS properties into a list of style controls.
    Stamps data-style-id on each matched element.

    Control types:
        table  → background-color  (Card Background Color)
        a      → color             (Title Link Color)
               → font-size        (Title Font Size)
        td     → background-image  (Background Image URL)
               → color            (Body Text Color)
               → background-color (Background Color)
               → font-size        (Body Font Size)
        span   → color            (Number Color)
               → font-size        (Number Font Size)
    """
    controls    = []
    style_seq   = [0]          # mutable counter
    seen_py_ids = set()        # Python id() of already-stamped elements
    current_section = None

    # ── inner helpers ──────────────────────────────────────────────

    def _normalize_hex(h: str) -> str:
        h = h.strip().lower()
        if h.startswith("#") and len(h) == 4:
            h = "#" + h[1] * 2 + h[2] * 2 + h[3] * 2
        return h

    def _ensure_style_id(el) -> str:
        py_id = id(el)
        if py_id not in seen_py_ids:
            sid = f"style-{style_seq[0]}"
            style_seq[0] += 1
            el["data-style-id"] = sid
            seen_py_ids.add(py_id)
        return el.get("data-style-id", "")

    def _find_hex(style_str: str, prop: str):
        # (?<![a-zA-Z-]) prevents matching 'color' inside 'background-color'
        m = re.search(
            rf"(?<![a-zA-Z-]){re.escape(prop)}\s*:\s*(#[0-9a-fA-F]{{3,8}})",
            style_str,
        )
        return _normalize_hex(m.group(1)) if m else None

    def _find_font_size(style_str: str):
        m = re.search(r"font-size\s*:\s*(\d+(?:\.\d+)?)", style_str)
        return m.group(1) if m else None

    def _find_bg_image(style_str: str):
        m = re.search(r"background-image\s*:\s*url\(['\"]?(.*?)['\"]?\)", style_str)
        return m.group(1) if m else None

    def _add(el, label, ctype, prop, val):
        sid = _ensure_style_id(el)
        controls.append({
            "id":       f"sc-{len(controls)}",
            "style_id": sid,
            "section":  current_section,
            "label":    label,
            "type":     ctype,
            "prop":     prop,
            "value":    val,
            "el":       el,
        })

    # ── main walk ─────────────────────────────────────────────────

    for node in soup.descendants:
        if isinstance(node, Comment):
            current_section = str(node).strip()
            continue

        if not getattr(node, "name", None):
            continue

        # Sidebar & Footer → PROTECT STYLES (locked)
        if is_in_footer(node) or is_in_sidebar(node):
            continue

        style_str = node.get("style", "")
        if not style_str:
            continue

        tag = node.name

        if tag == "table":
            bg = _find_hex(style_str, "background-color")
            if bg:
                _add(node, "Card Background Color", "color", "background-color", bg)

        elif tag == "a":
            color = _find_hex(style_str, "color")
            if color:
                _add(node, "Title Link Color", "color", "color", color)
            fs = _find_font_size(style_str)
            if fs:
                _add(node, "Title Font Size", "number", "font-size", fs)

            accent = _find_hex(style_str, "--accent")
            if accent:
                _add(node, "Card Accent Color", "accent-color", "--accent", accent)

        elif tag == "td":
            # Skip td wrappers whose DIRECT child is an already-indexed <a>
            direct_a = node.find("a", recursive=False)
            if direct_a and direct_a.get("data-editor-id"):
                continue

            bg_img = _find_bg_image(style_str)
            if bg_img and PROTECTED_URL_BASE not in bg_img:
                _add(node, "Background Image URL", "url", "background-image", bg_img)

            color = _find_hex(style_str, "color")
            if color:
                _add(node, "Body Text Color", "color", "color", color)

            bg = _find_hex(style_str, "background-color")
            if bg:
                _add(node, "Background Color", "color", "background-color", bg)

            fs = _find_font_size(style_str)
            if fs:
                _add(node, "Body Font Size", "number", "font-size", fs)

        elif tag == "span":
            color = _find_hex(style_str, "color")
            if color:
                _add(node, "Number Color", "color", "color", color)
            fs = _find_font_size(style_str)
            if fs:
                _add(node, "Number Font Size", "number", "font-size", fs)

    return controls


# ══════════════════════════════════════════════════════════════════
#  LOGO ALIGNMENT HELPER
# ══════════════════════════════════════════════════════════════════

def stamp_logo_spacer(soup) -> None:
    """
    Find the logo-alignment spacer <td> inside #sidebar and stamp it with
    data-logo-spacer="true" so JS and _process_form can target it reliably.

    The spacer is the <td height="50"> (or whatever current value) that sits
    between the QR block and the logo background <td>. It is identified by:
      - being inside #sidebar
      - having a numeric height attribute
      - containing only whitespace / &nbsp; (no real child elements)
    """
    sidebar = soup.find(id="sidebar")
    if not sidebar:
        return

    for td in sidebar.find_all("td"):
        h = td.get("height")
        if not h:
            continue
        try:
            int(str(h))
        except ValueError:
            continue
        # Must be a pure spacer: no child elements (only text/nbsp)
        child_tags = [c for c in td.children if getattr(c, "name", None)]
        if child_tags:
            continue
        text = td.get_text().strip()
        # Accept empty, &nbsp;, or just whitespace
        if text and text != "\xa0":
            continue
        td["data-logo-spacer"] = "true"
        logging.info("stamp_logo_spacer: stamped td with height=%s", h)
        return   # only stamp the first match (there should be only one)


# ══════════════════════════════════════════════════════════════════
#  SAVE / FORMAT HELPERS
# ══════════════════════════════════════════════════════════════════

def fix_date_br(text: str) -> str:
    """
    Ensure day-name and date are separated by <br>.
    e.g. 'Saturday March 21' → 'Saturday<br>March 21'
    """
    days = ("Monday", "Tuesday", "Wednesday", "Thursday",
            "Friday", "Saturday", "Sunday")
    for day in days:
        if text.startswith(day):
            rest = text[len(day):]
            if re.match(r'^\s*<br\s*/?>', rest, re.I):
                text = f"{day}<br>{re.sub(r'^\s*<br\s*/?>\s*', '', rest, flags=re.I)}"
            else:
                text = f"{day}<br>{rest.lstrip()}"
            break
    return text


def update_style_prop(style_str: str, prop: str, new_value: str) -> str:
    """Surgically replace (or append) a single CSS property in an inline style string."""

    # (?<![a-zA-Z-]) prevents 'color' from matching inside 'background-color'
    pattern = rf"(?<![a-zA-Z-])({re.escape(prop)}\s*:\s*)[^;]+"
    if re.search(pattern, style_str):
        return re.sub(pattern, rf"\g<1>{new_value}", style_str)
    # Property not present — append it
    sep = "" if style_str.rstrip().endswith(";") else ";"
    return f"{style_str.rstrip()}{sep} {prop}: {new_value};"


def sanitize_hex_color(raw: str) -> str:
    """Strip whitespace and validate a hex color. Returns cleaned value."""
    v = raw.strip()
    if not re.match(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$", v):
        logging.warning("sanitize_hex_color: unexpected value %r", v)
    return v


def format_html(soup) -> str:
    """
    Compact serialization — deliberately NOT prettify() to avoid
    whitespace-gap bugs in email clients.
    """
    return str(soup)


def strip_editor_attrs(soup) -> None:
    """Remove data-editor-id, data-style-id, and data-logo-spacer before writing the final file."""
    for el in soup.find_all(True):
        el.attrs.pop("data-editor-id",   None)
        el.attrs.pop("data-style-id",    None)
        el.attrs.pop("data-logo-spacer", None)

    # Unwrap temporary spans added by wrap_bare_text_nodes
    for span in soup.find_all("span", {"data-temp-span": "true"}):
        span.unwrap()


def _norm(s: str) -> str:
    return s.strip()


# ══════════════════════════════════════════════════════════════════
#  LOGIN PAGE TEMPLATE
# ══════════════════════════════════════════════════════════════════

LOGIN_HTML = f"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Newsband — Login</title>
  <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,700;0,900;1,700&family=IBM+Plex+Mono:wght@400;500&family=Source+Sans+3:wght@300;400;600&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    :root {{
      --ink: #0a0a0a;
      --paper: #f4f0e8;
      --accent: #c8102e;
      --mid: #5a5247;
      --rule: #1a1a1a;
      --faint: #e0dbd0;
    }}

    body {{
      background-color: var(--paper);
      background-image:
        repeating-linear-gradient(0deg, transparent, transparent 27px, var(--faint) 27px, var(--faint) 28px);
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      font-family: 'Source Sans 3', sans-serif;
    }}

    .page-wrap {{
      width: 100%;
      max-width: 480px;
      padding: 24px;
    }}

    .masthead {{
      text-align: center;
      border-top: 4px solid var(--rule);
      border-bottom: 1px solid var(--rule);
      padding: 14px 0 12px;
      margin-bottom: 6px;
      position: relative;
    }}

    .masthead::before {{
      content: '';
      display: block;
      height: 2px;
      background: var(--accent);
      margin-bottom: 12px;
    }}

    .masthead-logo {{
      max-width: 260px;
      max-height: 80px;
      width: auto;
      height: auto;
      object-fit: contain;
      display: block;
      margin: 0 auto;
    }}

    .masthead-tagline {{
      font-family: 'IBM Plex Mono', monospace;
      font-size: 0.62rem;
      letter-spacing: 0.18em;
      color: var(--mid);
      text-transform: uppercase;
      margin-top: 10px;
    }}

    .dateline {{
      font-family: 'IBM Plex Mono', monospace;
      font-size: 0.6rem;
      color: var(--mid);
      text-align: center;
      padding: 4px 0;
      border-bottom: 1px solid var(--rule);
      margin-bottom: 32px;
      letter-spacing: 0.08em;
    }}

    .card {{
      background: #fff;
      border: 1px solid #c8c2b5;
      padding: 36px 40px 40px;
      box-shadow: 4px 4px 0 var(--ink);
      animation: slideUp 0.5s cubic-bezier(0.22, 1, 0.36, 1) both;
    }}

    @keyframes slideUp {{
      from {{ opacity: 0; transform: translateY(20px); }}
      to   {{ opacity: 1; transform: translateY(0); }}
    }}

    .card-headline {{
      font-family: 'Playfair Display', serif;
      font-size: 1.45rem;
      font-weight: 700;
      color: var(--ink);
      margin-bottom: 4px;
      line-height: 1.2;
    }}

    .card-sub {{
      font-size: 0.82rem;
      color: var(--mid);
      margin-bottom: 28px;
      font-weight: 300;
    }}

    .rule-divider {{
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 24px;
    }}

    .rule-divider span {{
      flex: 1;
      height: 1px;
      background: var(--faint);
    }}

    .rule-divider em {{
      font-family: 'IBM Plex Mono', monospace;
      font-size: 0.6rem;
      color: #aaa;
      font-style: normal;
      letter-spacing: 0.1em;
      white-space: nowrap;
    }}

    .login-field {{
      margin-bottom: 20px;
    }}

    .login-field label {{
      display: block;
      font-family: 'IBM Plex Mono', monospace;
      font-size: 0.65rem;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      color: var(--mid);
      margin-bottom: 7px;
    }}

    input[type="text"],
    input[type="password"] {{
      width: 100%;
      padding: 11px 14px;
      border: 1px solid #c8c2b5;
      border-bottom: 2px solid var(--ink);
      background: var(--paper);
      font-family: 'IBM Plex Mono', monospace;
      font-size: 0.92rem;
      color: var(--ink);
      outline: none;
      transition: border-color 0.2s, background 0.2s;
    }}

    input[type="text"]:focus,
    input[type="password"]:focus {{
      background: #fff;
      border-color: var(--accent);
      border-bottom-color: var(--accent);
    }}

    .error-banner {{
      background: var(--accent);
      color: #fff;
      font-family: 'IBM Plex Mono', monospace;
      font-size: 0.72rem;
      letter-spacing: 0.06em;
      padding: 10px 14px;
      margin-bottom: 20px;
      display: flex;
      align-items: center;
      gap: 8px;
      animation: shake 0.4s cubic-bezier(0.36, 0.07, 0.19, 0.97);
    }}

    @keyframes shake {{
      0%, 100% {{ transform: translateX(0); }}
      20%       {{ transform: translateX(-6px); }}
      40%       {{ transform: translateX(6px); }}
      60%       {{ transform: translateX(-4px); }}
      80%       {{ transform: translateX(4px); }}
    }}

    .error-banner::before {{ content: '⚠'; font-size: 0.9rem; }}

    button[type="submit"] {{
      width: 100%;
      padding: 13px;
      background: var(--ink);
      color: var(--paper);
      border: none;
      font-family: 'IBM Plex Mono', monospace;
      font-size: 0.8rem;
      letter-spacing: 0.18em;
      text-transform: uppercase;
      cursor: pointer;
      margin-top: 8px;
      position: relative;
      transition: background 0.15s, box-shadow 0.15s;
      box-shadow: 3px 3px 0 var(--accent);
    }}

    button[type="submit"]:hover {{
      background: var(--accent);
      box-shadow: 3px 3px 0 var(--ink);
    }}

    button[type="submit"]:active {{
      transform: translate(2px, 2px);
      box-shadow: 1px 1px 0 var(--ink);
    }}

    .footer-note {{
      font-family: 'IBM Plex Mono', monospace;
      font-size: 0.58rem;
      color: #aaa;
      text-align: center;
      margin-top: 28px;
      letter-spacing: 0.08em;
    }}
  </style>
</head>
<body>
  <div class="page-wrap">

    <div class="masthead">
      <img src="{LOGO_URL}" alt="Newsband" class="masthead-logo" />
      <div class="masthead-tagline">Editorial Intelligence Platform</div>
    </div>
    <div class="dateline">SECURE ACCESS PORTAL</div>

    <div class="card">
      <div class="card-headline">Press Credentials Required</div>
      <div class="card-sub">Sign in with your journalist access credentials.</div>

      <div class="rule-divider">
        <span></span><em>AUTHORIZED PERSONNEL ONLY</em><span></span>
      </div>

      {{% if error %}}
      <div class="error-banner">Access denied — check your credentials and try again.</div>
      {{% endif %}}

      <form method="POST" action="/">
        <div class="login-field">
          <label for="username">Username</label>
          <input type="text" id="username" name="username" placeholder="Enter username" autocomplete="username" required />
        </div>
        <div class="login-field">
          <label for="password">Password</label>
          <input type="password" id="password" name="password" placeholder="Enter password" autocomplete="current-password" required />
        </div>
        <button type="submit">→ &nbsp; Access Dashboard</button>
      </form>
    </div>

    <div class="footer-note">NEWSBAND JOURNALISM PLATFORM &nbsp;·&nbsp; CONFIDENTIAL</div>
  </div>
</body>
</html>
"""


DASHBOARD_HTML = f"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Newsband — Dashboard</title>
  <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,700;0,900;1,700&family=IBM+Plex+Mono:wght@400;500&family=Source+Sans+3:wght@300;400;600&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    :root {{
      --ink: #0a0a0a;
      --paper: #f4f0e8;
      --accent: #c8102e;
      --mid: #5a5247;
      --rule: #1a1a1a;
      --faint: #e0dbd0;
    }}

    body {{
      background-color: var(--paper);
      background-image:
        repeating-linear-gradient(0deg, transparent, transparent 27px, var(--faint) 27px, var(--faint) 28px);
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      font-family: 'Source Sans 3', sans-serif;
    }}

    .page-wrap {{
      width: 100%;
      max-width: 580px;
      padding: 24px;
    }}

    .masthead {{
      text-align: center;
      border-top: 4px solid var(--rule);
      border-bottom: 1px solid var(--rule);
      padding: 14px 0 12px;
      margin-bottom: 6px;
      position: relative;
    }}

    .masthead::before {{
      content: '';
      display: block;
      height: 2px;
      background: var(--accent);
      margin-bottom: 12px;
    }}

    .masthead-logo {{
      max-width: 260px;
      max-height: 80px;
      width: auto;
      height: auto;
      object-fit: contain;
      display: block;
      margin: 0 auto;
    }}

    .masthead-tagline {{
      font-family: 'IBM Plex Mono', monospace;
      font-size: 0.62rem;
      letter-spacing: 0.18em;
      color: var(--mid);
      text-transform: uppercase;
      margin-top: 10px;
    }}

    .dateline {{
      font-family: 'IBM Plex Mono', monospace;
      font-size: 0.6rem;
      color: var(--mid);
      text-align: center;
      padding: 4px 0;
      border-bottom: 1px solid var(--rule);
      margin-bottom: 32px;
      letter-spacing: 0.08em;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    .dateline a {{
      color: var(--accent);
      text-decoration: none;
      font-weight: 600;
      letter-spacing: 0.1em;
    }}
    .dateline a:hover {{
      text-decoration: underline;
    }}

    .card {{
      background: #fff;
      border: 1px solid #c8c2b5;
      padding: 36px 40px 40px;
      box-shadow: 4px 4px 0 var(--ink);
      animation: slideUp 0.5s cubic-bezier(0.22, 1, 0.36, 1) both;
    }}

    @keyframes slideUp {{
      from {{ opacity: 0; transform: translateY(20px); }}
      to   {{ opacity: 1; transform: translateY(0); }}
    }}

    .card-headline {{
      font-family: 'Playfair Display', serif;
      font-size: 1.45rem;
      font-weight: 700;
      color: var(--ink);
      margin-bottom: 4px;
      line-height: 1.2;
    }}

    .card-sub {{
      font-size: 0.82rem;
      color: var(--mid);
      margin-bottom: 28px;
      font-weight: 300;
    }}

    .rule-divider {{
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 24px;
    }}

    .rule-divider span {{
      flex: 1;
      height: 1px;
      background: var(--faint);
    }}

    .rule-divider em {{
      font-family: 'IBM Plex Mono', monospace;
      font-size: 0.6rem;
      color: #aaa;
      font-style: normal;
      letter-spacing: 0.1em;
      white-space: nowrap;
    }}

    .dashboard-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
    }}

    .dash-btn {{
      display: block;
      text-decoration: none;
      padding: 24px 20px;
      background: var(--paper);
      border: 1px solid #c8c2b5;
      color: var(--ink);
      text-align: center;
      transition: all 0.2s;
      box-shadow: 3px 3px 0 var(--faint);
    }}

    .dash-btn:hover {{
      background: #fff;
      border-color: var(--ink);
      box-shadow: 4px 4px 0 var(--ink);
      transform: translate(-1px, -1px);
    }}

    .dash-btn:active {{
      transform: translate(2px, 2px);
      box-shadow: 1px 1px 0 var(--ink);
    }}

    .dash-btn-icon {{
      font-size: 2.2rem;
      margin-bottom: 12px;
      display: block;
    }}

    .dash-btn-title {{
      font-family: 'IBM Plex Mono', monospace;
      font-size: 0.8rem;
      font-weight: 600;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      margin-bottom: 8px;
      color: var(--ink);
    }}

    .dash-btn-desc {{
      font-size: 0.72rem;
      color: var(--mid);
      line-height: 1.4;
      font-family: 'Source Sans 3', sans-serif;
    }}

    .footer-note {{
      font-family: 'IBM Plex Mono', monospace;
      font-size: 0.58rem;
      color: #aaa;
      text-align: center;
      margin-top: 28px;
      letter-spacing: 0.08em;
    }}
  </style>
</head>
<body>
  <div class="page-wrap">

    <div class="masthead">
      <img src="{LOGO_URL}" alt="Newsband" class="masthead-logo" />
      <div class="masthead-tagline">Editorial Intelligence Platform</div>
    </div>
    <div class="dateline">
      <span>SECURE ACCESS PORTAL</span>
      <a href="/logout">LOGOUT ⍈</a>
    </div>

    <div class="card">
      <div class="card-headline">Dashboard</div>
      <div class="card-sub">Select a tool to proceed.</div>

      <div class="rule-divider">
        <span></span><em>AVAILABLE TOOLS</em><span></span>
      </div>

      <div class="dashboard-grid">
        <a href="/editor" class="dash-btn">
          <span class="dash-btn-icon">📰</span>
          <div class="dash-btn-title">Template Editor</div>
          <div class="dash-btn-desc">Create and edit newsletter templates visually.</div>
        </a>
        <a href="/converter" class="dash-btn">
          <span class="dash-btn-icon">💻</span>
          <div class="dash-btn-title">Code Viewer</div>
          <div class="dash-btn-desc">Upload, view, and copy raw HTML code.</div>
        </a>
      </div>

    </div>

    <div class="footer-note">NEWSBAND JOURNALISM PLATFORM &nbsp;·&nbsp; CONFIDENTIAL</div>
  </div>
</body>
</html>
"""


CONVERTER_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>HTML Code Viewer</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link
        href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600&family=DM+Mono:wght@400;500&display=swap"
        rel="stylesheet"
    />
    <style>
        *, *::before, *::after {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: "DM Sans", sans-serif;
            background-color: #f5f4f0;
            color: #1a1a1a;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 48px 20px 64px;
        }

        header {
            text-align: center;
            margin-bottom: 40px;
            position: relative;
        }

        header h1 {
            font-size: 1.9rem;
            font-weight: 600;
            letter-spacing: -0.5px;
            color: #111;
        }

        header p {
            margin-top: 8px;
            font-size: 0.95rem;
            color: #666;
        }

        .btn-back-wrap {
            margin-bottom: 24px;
            text-align: center;
        }

        .btn-back {
            display: inline-block;
            font-size: 0.9rem;
            color: #555;
            text-decoration: none;
            font-weight: 500;
            transition: color 0.15s;
        }
        
        .btn-back:hover {
            color: #111;
        }

        .card {
            background: #ffffff;
            border: 1px solid #e0ddd6;
            border-radius: 14px;
            padding: 32px;
            width: 100%;
            max-width: 700px;
            box-shadow: 0 2px 12px rgba(0, 0, 0, 0.05);
        }

        /* ── Upload zone ── */
        .upload-zone {
            border: 2px dashed #c9c5bb;
            border-radius: 10px;
            padding: 40px 24px;
            text-align: center;
            background: #faf9f6;
            transition: border-color 0.2s, background 0.2s;
            cursor: pointer;
        }

        .upload-zone:hover,
        .upload-zone.drag-over {
            border-color: #888;
            background: #f2f1ec;
        }

        .upload-zone input[type="file"] {
            display: none;
        }

        .upload-icon {
            font-size: 2.4rem;
            margin-bottom: 12px;
            display: block;
        }

        .upload-zone label {
            display: block;
            cursor: pointer;
        }

        .upload-zone .upload-main-text {
            font-size: 1rem;
            font-weight: 500;
            color: #333;
        }

        .upload-zone .upload-sub-text {
            font-size: 0.85rem;
            color: #888;
            margin-top: 6px;
        }

        .selected-file-name {
            margin-top: 12px;
            font-size: 0.85rem;
            color: #555;
            font-family: "DM Mono", monospace;
        }

        .btn-primary {
            display: block;
            width: 100%;
            margin-top: 20px;
            padding: 13px;
            background: #1a1a1a;
            color: #fff;
            font-family: "DM Sans", sans-serif;
            font-size: 0.95rem;
            font-weight: 500;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            transition: background 0.18s, transform 0.1s;
        }

        .btn-primary:hover {
            background: #333;
        }

        .btn-primary:active {
            transform: scale(0.99);
        }

        /* ── Error banner ── */
        .error-banner {
            background: #fff1f1;
            border: 1px solid #f5c2c2;
            color: #b00020;
            border-radius: 8px;
            padding: 12px 16px;
            font-size: 0.9rem;
            margin-bottom: 20px;
        }

        /* ── Code viewer ── */
        .code-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 12px;
        }

        .code-filename {
            font-size: 0.88rem;
            font-weight: 500;
            color: #555;
            font-family: "DM Mono", monospace;
            background: #f0ede7;
            padding: 4px 10px;
            border-radius: 6px;
        }

        .btn-copy {
            display: flex;
            align-items: center;
            gap: 6px;
            padding: 8px 16px;
            background: #f0ede7;
            border: 1px solid #ddd8cf;
            border-radius: 7px;
            font-family: "DM Sans", sans-serif;
            font-size: 0.88rem;
            font-weight: 500;
            color: #333;
            cursor: pointer;
            transition: background 0.15s, border-color 0.15s;
        }

        .btn-copy:hover {
            background: #e6e2da;
            border-color: #c9c5bb;
        }

        .btn-copy.copied {
            background: #e8f5e9;
            border-color: #a5d6a7;
            color: #2e7d32;
        }

        .code-block-wrapper {
            position: relative;
            background: #faf9f7;
            border: 1px solid #e5e2da;
            border-radius: 10px;
            overflow: hidden;
        }

        pre {
            overflow-x: auto;
            overflow-y: auto;
            max-height: 520px;
            padding: 20px 22px;
            font-family: "DM Mono", monospace;
            font-size: 0.82rem;
            line-height: 1.75;
            color: #2d2d2d;
            white-space: pre;
        }

        .upload-another {
            display: inline-block;
            margin-top: 24px;
            font-size: 0.88rem;
            color: #888;
            text-decoration: none;
            border-bottom: 1px solid #ccc;
            padding-bottom: 1px;
            transition: color 0.15s, border-color 0.15s;
        }

        .upload-another:hover {
            color: #333;
            border-color: #555;
        }
    </style>
</head>
<body>
    <div class="btn-back-wrap">
        <a href="/dashboard" class="btn-back">← Back to Dashboard</a>
    </div>

    <header>
        <h1>HTML Code Viewer</h1>
        <p>Upload an HTML file to view and copy its source code.</p>
    </header>

    <div class="card">

        {% if error %}
        <div class="error-banner">⚠ {{ error }}</div>
        {% endif %}

        {% if not code %}

        <!-- ── Upload form ── -->
        <form
            method="POST"
            action="/converter"
            enctype="multipart/form-data"
            id="uploadForm"
        >
            <div
                class="upload-zone"
                id="dropZone"
                onclick="document.getElementById('fileInput').click()"
            >
                <span class="upload-icon">📄</span>
                <label>
                    <span class="upload-main-text">Click to choose a file</span>
                    <span class="upload-sub-text">or drag and drop it here · .html / .htm only</span>
                </label>
                <input
                    type="file"
                    id="fileInput"
                    name="file"
                    accept=".html,.htm"
                    onchange="handleFileSelect(this)"
                />
                <div class="selected-file-name" id="fileName"></div>
            </div>

            <button type="submit" class="btn-primary">View Source Code →</button>
        </form>

        {% else %}

        <!-- ── Code viewer ── -->
        <div class="code-header">
            <span class="code-filename">{{ filename }}</span>
            <button class="btn-copy" id="copyBtn" onclick="copyCode()">
                <span id="copyIcon">⎘</span>
                <span id="copyLabel">Copy Code</span>
            </button>
        </div>

        <div class="code-block-wrapper">
            <pre id="codeContent">{{ code }}</pre>
        </div>

        <a href="/converter" class="upload-another">← Upload another file</a>

        {% endif %}

    </div>

    <script>
        // ── Drag-and-drop ──
        const dropZone = document.getElementById("dropZone");

        if (dropZone) {
            dropZone.addEventListener("dragover", (e) => {
                e.preventDefault();
                dropZone.classList.add("drag-over");
            });

            dropZone.addEventListener("dragleave", () => {
                dropZone.classList.remove("drag-over");
            });

            dropZone.addEventListener("drop", (e) => {
                e.preventDefault();
                dropZone.classList.remove("drag-over");

                const files = e.dataTransfer.files;
                if (files.length > 0) {
                    const input = document.getElementById("fileInput");
                    input.files = files;
                    handleFileSelect(input);
                }
            });
        }

        // ── Show selected filename ──
        function handleFileSelect(input) {
            const nameEl = document.getElementById("fileName");
            if (input.files.length > 0) {
                nameEl.textContent = "Selected: " + input.files[0].name;
            }
        }

        // ── Copy code ──
        function copyCode() {
            const code = document.getElementById("codeContent").innerText;

            function showCopied() {
                const btn = document.getElementById("copyBtn");
                const label = document.getElementById("copyLabel");
                const icon = document.getElementById("copyIcon");

                btn.classList.add("copied");
                label.textContent = "Copied!";
                icon.textContent = "✓";

                setTimeout(() => {
                    btn.classList.remove("copied");
                    label.textContent = "Copy Code";
                    icon.textContent = "⎘";
                }, 2000);
            }

            // Try modern clipboard API first, fall back to execCommand
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(code).then(showCopied).catch(() => {
                    // Fallback: legacy copy via temporary textarea
                    const ta = document.createElement("textarea");
                    ta.value = code;
                    ta.style.position = "fixed";
                    ta.style.opacity = "0";
                    document.body.appendChild(ta);
                    ta.select();
                    document.execCommand("copy");
                    document.body.removeChild(ta);
                    showCopied();
                });
            } else {
                // No clipboard API at all — use legacy method
                const ta = document.createElement("textarea");
                ta.value = code;
                ta.style.position = "fixed";
                ta.style.opacity = "0";
                document.body.appendChild(ta);
                ta.select();
                document.execCommand("copy");
                document.body.removeChild(ta);
                showCopied();
            }
        }
    </script>

</body>
</html>
"""

# ══════════════════════════════════════════════════════════════════
#  EDITOR UI TEMPLATE
# ══════════════════════════════════════════════════════════════════

EDITOR_PAGE = """\
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Newsband Editor</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #eef0f6; color: #1e2235;
    display: flex; flex-direction: column; height: 100vh;
    align-items: center; overflow: hidden;
  }

  #main {
    display: flex; flex: 1; width: 100%; max-width: 100vw;
    overflow: hidden; justify-content: center;
  }

  /* ── TOP BAR ── */
  #topbar {
    background: #ffffff; border-bottom: 1px solid #dde2ee;
    padding: 0 20px; height: 52px; width: 100%;
    display: flex; align-items: center; gap: 10px; flex-shrink: 0;
    box-shadow: 0 1px 4px rgba(0,0,0,0.07);
    z-index: 10;
  }
  #topbar h1 { font-size: 15px; font-weight: 700; color: #1e2235; flex: 1; letter-spacing: 0.3px; }
  #topbar h1 span { color: #3b5bdb; }
  .btn {
    padding: 7px 18px; border: none; border-radius: 6px;
    cursor: pointer; font-size: 13px; font-weight: 600; letter-spacing: 0.2px;
    transition: background 0.15s, transform 0.1s;
  }
  .btn:active { transform: scale(0.97); }
  .btn-save     { background: #3b5bdb; color: #fff; }
  .btn-save:hover { background: #2f4ec4; }
  .btn-dl       { background: #f0f2f8; color: #445; border: 1px solid #dde2ee; }
  .btn-dl:hover { background: #e2e6f3; }
  .btn-reset    { background: transparent; color: #99a; border: 1px solid #dde2ee; }
  .btn-reset:hover { background: #f5f6fb; color: #556; }

  /* ── TWO-PANEL BODY ── */
  #main { display: flex; flex: 1; overflow: hidden; width: 100%; }

  /* ── LEFT PANEL ── */
  #panel {
    width: 680px; min-width: 380px;
    background: #ffffff; overflow-y: auto;
    border-right: 1px solid #dde2ee; flex-shrink: 0;
  }
  #panel::-webkit-scrollbar { width: 6px; }
  #panel::-webkit-scrollbar-thumb { background: #d0d5e8; border-radius: 3px; }

  /* Section banner */
  .sec-banner {
    background: #f0f3fb; border-left: 3px solid #3b5bdb;
    padding: 9px 14px; margin-top: 6px;
    font-size: 13px; font-weight: 700; letter-spacing: 1.2px;
    text-transform: uppercase; color: #3b5bdb;
  }

  /* Field rows */
  .field {
    padding: 9px 14px 8px; border-bottom: 1px solid #f0f2f8;
  }
  .field-label {
    font-size: 13px; letter-spacing: 0.5px; text-transform: uppercase;
    color: #8898c0; margin-bottom: 6px; font-weight: 600;
  }
  textarea, .text-inp {
    width: 100%; background: #f7f8fc; color: #1e2235;
    border: 1px solid #dde2ee; border-radius: 5px;
    padding: 9px 11px; font-size: 15px; font-family: inherit;
    outline: none; transition: border-color 0.2s;
  }
  textarea { resize: vertical; min-height: 90px; font-size: 15px; padding: 10px 12px; line-height: 1.6; }
  textarea:focus, .text-inp:focus { border-color: #3b5bdb; background: #fff; }

  /* Image field */
  .img-thumb {
    width: 100%; height: 280px; object-fit: cover;
    border-radius: 4px; background: #eef0f6;
    display: block; margin-bottom: 5px;
  }
  .img-prefix { font-size: 12px; color: #aab; margin-bottom: 3px; word-break: break-all; }

  /* Style controls */
  .style-row { display: flex; align-items: center; gap: 7px; }
  .palette-grid {
    display: grid; grid-template-columns: repeat(6, 26px); gap: 5px; margin-bottom: 7px;
  }
  .swatch {
    width: 26px; height: 26px; border-radius: 4px; border: 2px solid transparent;
    cursor: pointer; padding: 0; transition: transform 0.1s, border-color 0.1s;
  }
  .swatch:hover { transform: scale(1.15); }
  .swatch-active { border-color: #1e2235 !important; box-shadow: 0 0 0 1px #fff inset; }
  input[type=number] {
    width: 80px; background: #f7f8fc; color: #1e2235;
    border: 1px solid #dde2ee; border-radius: 5px;
    padding: 7px 10px; font-size: 15px; outline: none;
  }
  input[type=number]:focus { border-color: #3b5bdb; }
  .unit { font-size: 14px; color: #8898c0; }

  /* ── Removed Logo Alignment Status Styles ── */

  /* ── RIGHT PANEL: PREVIEW ── */
  #preview-wrap {
    flex: 1; display: flex; flex-direction: column; overflow: hidden;
    background: #f8f9fa; border-left: 1px solid #dde2ee;
    align-items: center; /* Center the preview iframe horizontally */
  }
  #preview-bar {
    background: #ffffff; border-bottom: 1px solid #dde2ee;
    padding: 7px 16px; font-size: 11px; color: #8898c0;
    display: flex; align-items: center; gap: 8px; flex-shrink: 0; width: 100%;
  }
  .live-dot { width: 7px; height: 7px; border-radius: 50%; background: #40c057; flex-shrink: 0; }
  iframe {
    flex: 1; border: none; width: 100%; height: 100%; max-width: 794px;
    margin: 0 auto; background: #fff;
    box-shadow: 0 0 20px rgba(0,0,0,0.05);
    transition: transform 0.2s;
    transform-origin: top center;
  }

  @media (max-width: 1200px) {
    #panel { width: 450px; }
  }

  @media (max-width: 900px) {
    #main { flex-direction: column; }
    #panel { width: 100%; height: 50%; border-right: none; border-bottom: 1px solid #dde2ee; }
    iframe { max-width: 100%; }
  }

  /* Toast */
  #toast {
    position: fixed; bottom: 20px; right: 20px;
    background: #2f9e44; color: #fff;
    padding: 10px 18px; border-radius: 8px;
    font-size: 13px; font-weight: 600;
    opacity: 0; pointer-events: none;
    transition: opacity 0.3s;
    z-index: 9999;
  }
  #toast.show { opacity: 1; }
</style>
</head>
<body>

<!-- ── TOP BAR ── -->
<div id="topbar">
  <a href="/dashboard" class="btn btn-reset" style="text-decoration:none; display:inline-flex; align-items:center; margin-right: 14px; padding: 5px 12px; font-size: 13px;">← Dashboard</a>
  <h1>📰 Newsband <span>Template Editor</span></h1>
  <button class="btn btn-reset" onclick="confirmReset()">↺ Reset</button>
  <button class="btn btn-dl"   onclick="submitForm('download')">⬇ Download HTML</button>
  <button class="btn btn-save" onclick="manualSave()">💾 Save</button>
  <a href="/logout" class="btn btn-reset" style="text-decoration:none; display:inline-flex; align-items:center;">🚪 Logout</a>
</div>

<!-- ── MAIN BODY ── -->
<div id="main">

  <!-- LEFT PANEL -->
  <div id="panel">
    <form id="eform" method="POST" action="/editor/save">
      %(form_html)s
    </form>
  </div>

  <!-- RIGHT PANEL -->
  <div id="preview-wrap">
    <div id="preview-bar">
      <span class="live-dot"></span> Live Preview — changes appear instantly
    </div>
    <iframe id="pframe" src="/editor/preview" onload="onPreviewLoad()"></iframe>
  </div>

</div>

<div id="toast">✔ Saved!</div>

<script>
/* ── helpers ── */
const frame = () => document.getElementById('pframe').contentWindow;

function post(msg) {
  try { frame().postMessage(msg, '*'); } catch(e) {}
}

function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2200);
}

/* ── When iframe finishes loading, push all state ── */
function onPreviewLoad() {
  pushAllStateToIframe();
}

/* ── Receive messages back from iframe if needed ── */
window.addEventListener('message', function(ev) {
  var d = ev.data;
  if (!d || !d.type) return;
  // (No longer listening for spacer_computed)
});

/* ── live preview: text ── */
document.querySelectorAll('textarea[data-eid]').forEach(el => {
  el.addEventListener('input', () => {
    post({ type: 'update', id: el.dataset.eid, fieldType: 'text', value: el.value });
  });
});

/* ── live preview: image URL ── */
document.querySelectorAll('input[data-eid][data-ftype="img"]').forEach(el => {
  el.addEventListener('input', () => {
    const base = el.dataset.base || '';
    const full = base + el.value;
    post({ type: 'update', id: el.dataset.eid, fieldType: 'img', value: full });
    const thumb = document.querySelector('img[data-thumb="' + el.dataset.eid + '"]');
    if (thumb) thumb.src = full;
  });
});

/* ── live preview: td background-image URL ── */
document.querySelectorAll('input[data-eid][data-ftype="bg-img"]').forEach(el => {
  el.addEventListener('input', () => {
    const base = el.dataset.base || '';
    const full = base + el.value;
    post({ type: 'update', id: el.dataset.eid, fieldType: 'bg-img', value: full });
    const thumb = document.querySelector('img[data-thumb="' + el.dataset.eid + '"]');
    if (thumb) thumb.src = full;
  });
});

/* ── live preview: href ── */
document.querySelectorAll('input[data-eid][data-ftype="href"]').forEach(el => {
  el.addEventListener('input', () => {
    post({ type: 'update', id: el.dataset.eid, fieldType: 'href', value: el.value });
  });
});

/* ── live preview: palette swatch ── */
document.addEventListener('click', e => {
  const sw = e.target.closest('.swatch');
  if (!sw) return;
  const hex = sw.dataset.color;
  const sid = sw.dataset.sid;
  // update active state
  sw.closest('.palette-grid').querySelectorAll('.swatch').forEach(s => s.classList.remove('swatch-active'));
  sw.classList.add('swatch-active');
  // sync text input
  const txt = document.querySelector('input[data-hexfor="' + sid + '"]');
  if (txt) txt.value = hex;
  post({ type: 'style', styleId: sid, prop: sw.dataset.prop, ctype: sw.dataset.ctype, value: hex });
});

/* ── live preview: hex text input ── */
document.querySelectorAll('input[data-hexfor]').forEach(el => {
  el.addEventListener('input', () => {
    if (/^#[0-9a-fA-F]{6}$/.test(el.value)) {
      post({ type: 'style', styleId: el.dataset.hexfor, prop: el.dataset.prop, ctype: el.dataset.ctype, value: el.value });
    }
  });
});

/* ── live preview: font-size number ── */
document.querySelectorAll('input[type=number][data-sid]').forEach(el => {
  el.addEventListener('input', () => {
    post({ type: 'style', styleId: el.dataset.sid, prop: el.dataset.prop, value: el.value + 'px' });
  });
});

/* ── live preview: background-image URL ── */
document.querySelectorAll('input[data-bgsid]').forEach(el => {
  el.addEventListener('input', () => {
    post({ type: 'style', styleId: el.dataset.bgsid, prop: 'background-image',
           value: "url('" + el.value + "')" });
  });
});

/* ── form submit ── */
function submitForm(action) {
  saveState();
  const form = document.getElementById('eform');
  form.action = '/editor/' + action;
  form.submit();
}

/* ── reset ── */
function confirmReset() {
  if (confirm('Reset to original template? All unsaved changes will be lost.')) {
    localStorage.removeItem('newsband_editor');
    window.location.reload();
  }
}

/* ── localStorage auto-save ── */
function saveState() {
  const data = {};
  const fd = new FormData(document.getElementById('eform'));
  for (let [k, v] of fd.entries()) {
    data[k] = v;
  }
  localStorage.setItem('newsband_editor', JSON.stringify(data));
}

function restoreState() {
  const saved = localStorage.getItem('newsband_editor');
  if (!saved) return;
  try {
    const data = JSON.parse(saved);
    for (let k in data) {
      const el = document.querySelector('[name="' + k + '"]');
      if (el && el.value !== data[k]) {
        el.value = data[k];
      }
    }
  } catch(e) {}
}

document.getElementById('eform').addEventListener('input', saveState);
window.addEventListener('DOMContentLoaded', restoreState);

function pushAllStateToIframe() {
  document.querySelectorAll('textarea[data-eid]').forEach(el => {
    post({ type: 'update', id: el.dataset.eid, fieldType: 'text', value: el.value });
  });
  document.querySelectorAll('input[data-eid][data-ftype="img"]').forEach(el => {
    const base = el.dataset.base || '';
    post({ type: 'update', id: el.dataset.eid, fieldType: 'img', value: base + el.value });
    const thumb = document.querySelector('img[data-thumb="' + el.dataset.eid + '"]');
    if (thumb) thumb.src = base + el.value;
  });
  document.querySelectorAll('input[data-eid][data-ftype="bg-img"]').forEach(el => {
    const base = el.dataset.base || '';
    post({ type: 'update', id: el.dataset.eid, fieldType: 'bg-img', value: base + el.value });
    const thumb = document.querySelector('img[data-thumb="' + el.dataset.eid + '"]');
    if (thumb) thumb.src = base + el.value;
  });
  document.querySelectorAll('input[data-eid][data-ftype="href"]').forEach(el => {
    post({ type: 'update', id: el.dataset.eid, fieldType: 'href', value: el.value });
  });
  document.querySelectorAll('input[data-hexfor]').forEach(el => {
    post({ type: 'style', styleId: el.dataset.hexfor, prop: el.dataset.prop, ctype: el.dataset.ctype, value: el.value });
  });
  document.querySelectorAll('input[type=number][data-sid]').forEach(el => {
    post({ type: 'style', styleId: el.dataset.sid, prop: el.dataset.prop, value: el.value + 'px' });
  });
  document.querySelectorAll('input[data-bgsid]').forEach(el => {
    post({ type: 'style', styleId: el.dataset.bgsid, prop: 'background-image', value: "url('" + el.value + "')" });
  });
}

function manualSave() {
  saveState();
  showToast('✔ Saved to your browser!');
}
</script>
</body>
</html>
"""

# ══════════════════════════════════════════════════════════════════
#  FORM RENDERING HELPERS
# ══════════════════════════════════════════════════════════════════

def _esc(s: str) -> str:
    """HTML-escape a string for use in attribute values or textarea content."""
    return (
        s.replace("&", "&amp;")
         .replace('"', "&quot;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
    )


def _render_field(elem: dict, custom_label: str = None) -> str:
    eid   = elem["id"]
    etype = elem["type"]
    text  = elem["text"]

    # Fallback logic for labels
    if etype in ("img", "bg-img"):
        default_label = "🖼 Image URL" if etype == "img" else "🌄 Background Image URL"
    elif etype == "href":
        default_label = "🔗 Link URL"
    else:
        default_label = "✏ Text"

    label = custom_label if custom_label else default_label
    if not label: # Safeguard
        label = default_label

    if etype in ("img", "bg-img"):
        # bg-img: background image on a <td>; rendered identically to <img>
        # but uses data-ftype="bg-img" so JS and save logic update the right attr.
        ftype = etype  # "img" or "bg-img"
        label = "🖼 Image URL" if etype == "img" else "🌄 Background Image URL"
        if text.startswith(GITHUB_BASE):
            filename = text[len(GITHUB_BASE):]
            prefix_block = f'<div class="img-prefix">📁 {GITHUB_BASE}</div>'
            inp = (
                f'<input class="text-inp" type="text" name="field_{eid}" '
                f'data-eid="{eid}" data-ftype="{ftype}" data-base="{GITHUB_BASE}" '
                f'value="{_esc(filename)}">'
            )
        else:
            prefix_block = ""
            inp = (
                f'<input class="text-inp" type="text" name="field_{eid}" '
                f'data-eid="{eid}" data-ftype="{ftype}" '
                f'value="{_esc(text)}">'
            )
        thumb = (
            f'<img class="img-thumb" src="{_esc(text)}" '
            f'data-thumb="{eid}" onerror="this.style.opacity=0.15" alt="">'
        )
        return (
            f'<div class="field">'
            f'<div class="field-label">{label}</div>'
            f'{thumb}{prefix_block}{inp}'
            f'</div>'
        )

    elif etype == "href":
        return (
            f'<div class="field">'
            f'<div class="field-label">🔗 Link URL</div>'
            f'<input class="text-inp" type="text" name="field_{eid}" '
            f'data-eid="{eid}" data-ftype="href" value="{_esc(text)}">'
            f'</div>'
        )

    else:
        inner = elem.get("inner_html", elem["text"])
        display = (
            inner.replace("<br/>", "\n")
                 .replace("<br />", "\n")
                 .replace("<br>", "\n")
        )
        display = re.sub(r"<[^>]+>", "", display)
        rows = max(8, min(14, display.count("\n") + 8))
        return (
            f'<div class="field">'
            f'<div class="field-label">✏ Text</div>'
            f'<textarea name="field_{eid}" data-eid="{eid}" rows="{rows}">'
            f'{_esc(display)}</textarea>'
            f'</div>'
        )


def _render_style_control(sc: dict, custom_label: str = None) -> str:
    sid   = sc["style_id"]
    label = custom_label if custom_label else sc["label"]
    if not label:
        label = sc["label"]
    ctype = sc["type"]
    prop  = sc["prop"]
    val   = sc["value"]
    sc_id = sc["id"]

    if ctype == "color" or ctype == "accent-color":
        hex6 = val.lower() if re.match(r"^#[0-9a-fA-F]{6}$", val) else "#000000"
        palette = [
            "#c8102e", "#c8781a", "#d4920f", "#8d3222", "#6d4c41", "#bf360c",
            "#1c4f7c", "#1565c0", "#37474f", "#00796b", "#2a7a5c", "#1b6e3a",
            "#8b2a6e", "#4a148c", "#6a1c4b", "#3d5a80", "#2d5986", "#1a1a1a",
        ]
        swatches = "".join(
            f'<button type="button" class="swatch{"  swatch-active" if c == hex6 else ""}" '
            f'style="background:{c}" data-color="{c}" '
            f'data-sid="{sid}" data-prop="{prop}" data-ctype="{ctype}" title="{c}"></button>'
            for c in palette
        )
        return (
            f'<div class="field">'
            f'<div class="field-label">🎨 {label}</div>'
            f'<div class="palette-grid">{swatches}</div>'
            f'<input class="text-inp" type="text" name="style_{sc_id}" '
            f'data-hexfor="{sid}" data-prop="{prop}" data-ctype="{ctype}" '
            f'value="{hex6}" maxlength="7" placeholder="#rrggbb" style="width:90px;">'
            f'</div>'
        )

    elif ctype == "number":
        return (
            f'<div class="field">'
            f'<div class="field-label">🔠 {label}</div>'
            f'<div class="style-row">'
            f'<input type="number" name="style_{sc_id}" '
            f'data-sid="{sid}" data-prop="{prop}" value="{val}" '
            f'min="1" max="120" step="0.5">'
            f'<span class="unit">px</span>'
            f'</div></div>'
        )

    elif ctype == "url":
        return (
            f'<div class="field">'
            f'<div class="field-label">🌄 {label}</div>'
            f'<input class="text-inp" type="text" name="style_{sc_id}" '
            f'data-bgsid="{sid}" value="{_esc(val)}" placeholder="https://...">'
            f'</div>'
        )

    return ""


# ══════════════════════════════════════════════════════════════════
#  SHARED FORM PROCESSOR  (used by /save and /download)
# ══════════════════════════════════════════════════════════════════

def _normalize_br(s: str) -> str:
    """Normalise all <br> variants to a canonical form before comparison."""
    return re.sub(r"<br\s*/?>", "<br>", s, flags=re.I)


def _process_form(form_data) -> str:
    """
    Apply submitted form values onto a fresh parse of the current HTML.
    Writes result to SAVED_FILE and returns the clean HTML string.
    """
    soup, elems    = load_elements()
    fix_link_visibility(elems)
    style_controls = load_style_controls(soup)

    # ── Stamp logo spacer so we can find it below ─────────────────
    stamp_logo_spacer(soup)

    # ── content fields ────────────────────────────────────────────
    for elem in elems:
        eid = elem["id"]
        key = f"field_{eid}"
        if key not in form_data:
            continue

        new_val = form_data[key]
        el      = elem["el"]
        etype   = elem["type"]

        if etype == "img":
            old_src = el.get("src", "")
            # Protection: if old src contains protected URL, reject change
            if PROTECTED_URL_BASE in old_src:
                continue

            base    = GITHUB_BASE if old_src.startswith(GITHUB_BASE) else ""
            full    = base + new_val if base else new_val
            if _norm(full) != _norm(old_src):
                el["src"] = full

        elif etype == "bg-img":
            # elem["text"] is the canonical URL that was shown in the editor field.
            old_url = elem["text"]
            base    = GITHUB_BASE if old_url.startswith(GITHUB_BASE) else ""
            full    = base + new_val if base else new_val
            # Protection: if old url contains protected URL, reject change
            if PROTECTED_URL_BASE in old_url:
                continue

            if _norm(full) == _norm(old_url):
                continue

            # Update every location that originally carried a background URL so that
            # both the style attribute and the HTML background attribute stay in sync.
            # This prevents one stale reference from silently overriding the new value.
            has_style_bg = bool(elem.get("_style_bg_url"))
            has_bg_attr  = bool(elem.get("_attr_bg_url"))

            if has_style_bg:
                el["style"] = update_style_prop(
                    el.get("style", ""), "background-image", f"url('{full}')"
                )
            if has_bg_attr:
                el["background"] = full
            if not has_style_bg and not has_bg_attr:
                # Fallback: element was somehow indexed without either; write to style.
                el["style"] = update_style_prop(
                    el.get("style", ""), "background-image", f"url('{full}')"
                )

        elif etype == "href":
            old_href = el.get("href", "")
            if PROTECTED_URL_BASE in old_href:
                continue
            if _norm(new_val) != _norm(old_href):
                el["href"] = new_val

        else:
            new_html = new_val.replace("\n", "<br>")
            new_html = fix_date_br(new_html)
            new_html = superscript_ordinal(new_html)

            old_inner = elem.get("inner_html", "")
            if re.sub(r"\s+", "", _normalize_br(new_html)) == re.sub(r"\s+", "", _normalize_br(old_inner)):
                continue

            el.clear()
            frag = BeautifulSoup(new_html, "html.parser")
            for child in list(frag.contents):
                el.append(child)

    # ── style controls ────────────────────────────────────────────
    for sc in style_controls:
        key = f"style_{sc['id']}"
        if key not in form_data:
            continue

        new_val = form_data[key].strip()
        el      = sc["el"]
        prop    = sc["prop"]
        ctype   = sc["type"]

        if not new_val:
            continue

        if ctype == "color" or ctype == "accent-color":
            new_val = sanitize_hex_color(new_val)
        elif ctype == "number":
            new_val = new_val + "px"
        elif ctype == "url":
            inner = re.sub(r"^url\(['\"]?|['\"]?\)$", "", new_val).strip()
            # Protection: if new URL contains protected URL, reject change
            if PROTECTED_URL_BASE in inner:
                continue
            new_val = f"url('{inner}')"

        if ctype == "accent-color":
            old_hex = sc["value"].strip().lower()
            if old_hex and new_val and old_hex != new_val.lower():
                pattern = re.compile(re.escape(old_hex), re.IGNORECASE)
                if el.get("style"):
                    el["style"] = pattern.sub(new_val, el["style"])
                for child in el.descendants:
                    if hasattr(child, "get") and child.get("style"):
                        child["style"] = pattern.sub(new_val, child["style"])
            continue

        el["style"] = update_style_prop(el.get("style", ""), prop, new_val)

    # (Logo spacer alignment logic removed)

    # ── finalise ──────────────────────────────────────────────────
    strip_editor_attrs(soup)
    html = format_html(soup)

    return html


# ══════════════════════════════════════════════════════════════════
#  FLASK ROUTES
# ══════════════════════════════════════════════════════════════════

# ── Login / Logout ────────────────────────────────────────────────

@app.route('/', methods=['GET', 'POST'])
def login():
    """Login page — entry point."""
    if session.get('logged_in'):
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        if username == VALID_USERNAME and password == VALID_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('dashboard'))
        return render_template_string(LOGIN_HTML, error=True)
    return render_template_string(LOGIN_HTML, error=False)


@app.route('/logout')
def logout():
    """Clear session and redirect to login."""
    session.clear()
    return redirect(url_for('login'))


# ── Dashboard & Converter ─────────────────────────────────────────

@app.route('/dashboard')
@require_login
def dashboard():
    """Dashboard page — routes to Editor or Converter."""
    return render_template_string(DASHBOARD_HTML)


@app.route("/converter", methods=["GET", "POST"])
@require_login
def converter():
    if request.method == "POST":
        file = request.files.get("file")

        if not file or file.filename == "":
            return render_template_string(CONVERTER_HTML, error="No file selected.", code=None)

        if not allowed_file(file.filename):
            return render_template_string(
                CONVERTER_HTML,
                error="Only .html and .htm files are accepted.",
                code=None,
            )

        try:
            raw_bytes = file.read()
            code_text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return render_template_string(
                CONVERTER_HTML,
                error="Could not read the file. Make sure it is a valid UTF-8 HTML file.",
                code=None,
            )

        return render_template_string(
            CONVERTER_HTML,
            code=code_text,
            filename=file.filename,
            error=None,
        )

    return render_template_string(CONVERTER_HTML, code=None, error=None)


# ── Editor ────────────────────────────────────────────────────────

@app.route("/editor")
@require_login
def editor():
    """Main editor page — two-panel layout."""
    from collections import defaultdict

    soup, elems    = load_elements()
    fix_link_visibility(elems)
    style_controls = load_style_controls(soup)

    eid_to_elem: dict = {e["id"]: e for e in elems}
    eid_to_comment   = load_section_comments(soup)

    sid_to_scs: dict = defaultdict(list)
    for sc in style_controls:
        sid_to_scs[sc["style_id"]].append(sc)

    form_parts      = []
    last_section    = None
    rendered_eids   = set()
    rendered_sids   = set()

    for node in soup.descendants:

        if isinstance(node, Comment):
            section = str(node).strip()
            if section and section != last_section:
                last_section = section
                # Don't show a section banner for footer — it has no editable fields anyway
                if not _section_is_footer(section):
                    label = section.strip("= ").strip()
                    form_parts.append(f'<div class="sec-banner">📋 {_esc(label)}</div>')
            continue

        if not hasattr(node, "get"):
            continue

        eid = node.get("data-editor-id")
        sid = node.get("data-style-id")

        if eid and eid in eid_to_elem and eid not in rendered_eids:
            elem = eid_to_elem[eid]
            if elem.get("visible", True):
                rendered_eids.add(eid)
                # Use comment as label if available, stripping common markers
                raw_label = eid_to_comment.get(eid)
                clean_label = None
                if raw_label:
                    clean_label = raw_label.strip("= -").strip()
                form_parts.append(_render_field(elem, custom_label=clean_label))

        if sid and sid not in rendered_sids and sid in sid_to_scs:
            rendered_sids.add(sid)
            for sc in sid_to_scs[sid]:
                form_parts.append(_render_style_control(sc))

    # AFTER — avoids % operator entirely, no escaping issues
    page = EDITOR_PAGE.replace("%(form_html)s", "\n".join(form_parts))
    return page


# ── Alignment JS injected into the preview iframe ─────────────────────────────
_ALIGNMENT_SCRIPT = """
<script>
(function() {

  function superscriptOrdinal(text) {
    if (typeof text !== 'string') return text;
    return text
        .replace(/(\d+)th/g, '$1ᵗʰ')
        .replace(/(\d+)st/g, '$1ˢᵗ')
        .replace(/(\d+)nd/g, '$1ⁿᵈ')
        .replace(/(\d+)rd/g, '$1ʳᵈ');
  }

  // Receive the existing content/style update messages
  window.addEventListener('message', function(ev) {
    var d = ev.data;
    if (!d || !d.type) return;

    if (d.type === 'update') {
      var el = document.querySelector('[data-editor-id="' + d.id + '"]');
      if (!el) return;
      if (d.fieldType === 'text') {
        var processed = d.value.replace(/\\n/g, '<br>');
        el.innerHTML = superscriptOrdinal(processed);
      } else if (d.fieldType === 'img') {
        el.src = d.value;
      } else if (d.fieldType === 'bg-img') {
        el.style.backgroundImage = "url('" + d.value + "')";
      } else if (d.fieldType === 'href') {
        el.href = d.value;
      }
    }

    if (d.type === 'style') {
      var el = document.querySelector('[data-style-id="' + d.styleId + '"]');
      if (!el) return;

      if (d.ctype === 'accent-color') {
        const oldHex = el.style.getPropertyValue('--accent').trim();
        const newHex = d.value;
        if (oldHex && newHex && oldHex.toLowerCase() !== newHex.toLowerCase()) {
           var regex = new RegExp(oldHex, 'ig');
           function recUpdate(node) {
              if (node.nodeType === Node.ELEMENT_NODE) {
                 const st = node.getAttribute('style');
                 if (st && regex.test(st)) {
                    node.setAttribute('style', st.replace(regex, newHex));
                 }
                 for (let i=0; i<node.childNodes.length; i++) {
                    recUpdate(node.childNodes[i]);
                 }
              }
           }
           recUpdate(el);
        }
        return;
      }

      if (d.prop === 'background-image') {
        var url = d.value.replace(/^url\\(['\\"']?|['\\"']?\\)$/g, '');
        el.style.backgroundImage = "url('" + url + "')";
      } else if (d.prop === 'font-size') {
        el.style.fontSize = d.value;
      } else {
        el.style.setProperty(d.prop, d.value);
      }
    }
  });

})();
</script>
"""


@app.route("/editor/preview")
@require_login
def preview():
    """
    Serve the newsletter HTML inside an iframe.
    Stamps data-editor-id, data-style-id, and data-logo-spacer, then appends
    the combined postMessage listener + alignment script.
    """
    soup, _ = load_elements()        # stamps data-editor-id
    load_style_controls(soup)        # stamps data-style-id
    stamp_logo_spacer(soup)          # stamps data-logo-spacer on the spacer td

    script_tag = BeautifulSoup(_ALIGNMENT_SCRIPT, "html.parser")

    body = soup.find("body")
    if body:
        body.append(script_tag)

    return Response(str(soup), mimetype="text/html")


@app.route("/editor/save", methods=["POST"])
@require_login
def save():
    """No-op endpoint. Edits are saved in localStorage; redirecting back."""
    return redirect(url_for('editor'))


@app.route("/editor/download", methods=["POST"])
@require_login
def download():
    """Generate the file entirely dynamically and stream as download."""
    html = _process_form(request.form)
    return Response(
        html,
        mimetype="text/html",
        headers={"Content-Disposition": 'attachment; filename="newsletter.html"'},
    )


# ══════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # If the file exists from a previous un-migrated version, clean it up
    if os.path.exists("opt-7.html"):
        os.remove("opt-7.html")
    app.run(debug=True, port=5000)
