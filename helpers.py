import re
import math
import logging
from functools import wraps
from flask import session, redirect, url_for, request
from bs4 import BeautifulSoup, NavigableString, Comment
import config

# ─────────────────────────────────────────────
# Auth Helpers
# ─────────────────────────────────────────────

def require_login(f):
    """Decorator — redirects to login page if user is not authenticated."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login_bp.login'))
        return f(*args, **kwargs)
    return decorated

# ─────────────────────────────────────────────
# HTML Processing Utility Helpers
# ─────────────────────────────────────────────

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in config.ALLOWED_EXTENSIONS

def get_html_file(file_path: str = None) -> str:
    """Load the pristine template from the specified path."""
    path = file_path or config.ORIGINAL_FILE
    with open(path, encoding="utf-8") as f:
        return f.read()

def _has_editable_descendant(el) -> bool:
    """Return True if any descendant of el has an editable tag name."""
    return any(
        getattr(d, "name", None) in config.ALL_EDITABLE
        for d in el.descendants
    )

def wrap_bare_text_nodes(soup) -> None:
    """
    Wrap bare NavigableStrings inside elements that also have editable-tag children.
    This makes raw text nodes addressable via data-editor-id.
    """
    for el in soup.find_all(True):
        has_editable_child = any(
            getattr(c, "name", None) in config.ALL_EDITABLE for c in el.children
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
    """Convert ordinal suffixes to Unicode superscripts."""
    text = re.sub(r'(\d+)th', r'\1ᵗʰ', text)
    text = re.sub(r'(\d+)st', r'\1ˢᵗ', text)
    text = re.sub(r'(\d+)nd', r'\1ⁿᵈ', text)
    text = re.sub(r'(\d+)rd', r'\1ʳᵈ', text)
    return text

def _is_sidebar_allowed(text: str) -> bool:
    """Return True if element text belongs to the Date or RNI Number field."""
    return bool(config._SIDEBAR_ALLOWED_RE.search(text.strip()))

def _section_is_footer(section: str) -> bool:
    s = section.lower()
    return any(kw in s for kw in config.FOOTER_SECTION_KEYWORDS)

def _section_is_sidebar(section: str) -> bool:
    s = section.lower()
    return any(kw in s for kw in config.SIDEBAR_SECTION_KEYWORDS)

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

def collapse_inner_whitespace(html_fragment: str) -> str:
    """Collapse runs of whitespace while preserving <br> tags."""
    _BR_PLACEHOLDER = "\x00BR\x00"
    out = re.sub(r"<br\s*/?>", _BR_PLACEHOLDER, html_fragment, flags=re.I)
    out = re.sub(r"\s+", " ", out)
    out = out.replace(_BR_PLACEHOLDER, "<br>")
    out = re.sub(r"\s*<br>\s*", "<br>", out)
    return out.strip()

# ─────────────────────────────────────────────
# Indexing & Style Processing
# ─────────────────────────────────────────────

def load_elements(file_path: str = None):
    """Core indexing engine for HTML elements."""
    html = get_html_file(file_path)
    soup = BeautifulSoup(html, "html.parser")
    wrap_bare_text_nodes(soup)

    elements       = []
    counter        = 0
    seen_hrefs     = set()

    for node in soup.descendants:
        if isinstance(node, Comment): continue

        if not getattr(node, "name", None): continue

        tag = node.name
        if tag not in config.ALL_EDITABLE: continue

        is_footer  = is_in_footer(node)
        is_sidebar = is_in_sidebar(node)

        if tag == "img":
            src = (node.get("src") or "").strip()
            if not src or "singlecolorimage.com" in src: continue

            eid = f"el-{counter}"
            node["data-editor-id"] = eid
            elements.append({
                "id": eid, "type": "img", "tag": tag,
                "text": src, "inner_html": src, "el": node,
                "visible": not (is_footer or is_sidebar)
            })
            counter += 1

        elif tag == "a":
            href = (node.get("href") or "").strip()
            if not href or href == "#" or href.startswith("mailto:"): continue

            eid = f"el-{counter}"
            node["data-editor-id"] = eid
            visible = not (is_footer or is_sidebar) and (href not in seen_hrefs)
            seen_hrefs.add(href)

            elements.append({
                "id": eid, "type": "href", "tag": tag,
                "text": href, "inner_html": href, "el": node,
                "visible": visible
            })
            counter += 1

        else:
            if _has_editable_descendant(node): continue
            if tag == "td":
                non_br_kids = [c for c in node.children if getattr(c, "name", None) and c.name != "br"]
                if non_br_kids: continue

            text = node.get_text()
            if not text.strip(): continue

            eid = f"el-{counter}"
            node["data-editor-id"] = eid

            visible = True
            if is_footer: visible = False
            elif is_sidebar: visible = _is_sidebar_allowed(text)

            inner_html = node.decode_contents()
            inner_html = collapse_inner_whitespace(inner_html)
            text       = collapse_inner_whitespace(text)

            elements.append({
                "id": eid, "type": "text", "tag": tag,
                "text": text, "inner_html": inner_html, "el": node,
                "visible": visible
            })
            counter += 1

    bg_elems, counter = extract_td_background_images(soup, counter_start=counter)
    elements.extend(bg_elems)
    return soup, elements

_TD_BG_URL_RE = re.compile(r"background(?:-image)?\s*:\s*url\(\s*['\"]?(.*?)['\"]?\s*\)", re.I)

def extract_td_background_images(soup, counter_start: int = 0) -> tuple:
    bg_elements: list = []
    counter = counter_start
    for td in soup.find_all("td"):
        if td.get("data-editor-id"): continue
        in_footer  = is_in_footer(td)
        in_sidebar = is_in_sidebar(td)
        style_url = ""
        style_str = td.get("style", "")
        if style_str:
            m = _TD_BG_URL_RE.search(style_str)
            if m: style_url = m.group(1).strip()
        attr_url = td.get("background", "").strip()
        url = style_url or attr_url
        if not url or "singlecolorimage.com" in url: continue
        eid = f"el-{counter}"
        td["data-editor-id"] = eid
        counter += 1
        bg_elements.append({
            "id": eid, "type": "bg-img", "tag": "td",
            "text": url, "inner_html": url, "el": td,
            "visible": not (in_footer or in_sidebar),
            "_style_bg_url": style_url, "_attr_bg_url": attr_url,
        })
    return bg_elements, counter

def fix_link_visibility(elements) -> None:
    for elem in elements:
        if elem["type"] != "href": continue
        node = elem["el"]
        elem["visible"] = not (is_in_footer(node) or is_in_sidebar(node))

def load_section_comments(soup) -> dict:
    mapping, pending = {}, None
    for node in soup.descendants:
        if isinstance(node, Comment):
            pending = str(node).strip()
        elif hasattr(node, "get") and node.get("data-editor-id") and pending:
            eid = node["data-editor-id"]
            if eid not in mapping: mapping[eid] = pending
            pending = None
    return mapping

def get_field_label(comment: str) -> str:
    if not comment: return ""
    if "\n" in comment or "┌─" in comment or comment.strip().startswith("END "): return ""
    label = re.sub(r'[\(\[].*?[\)\]]', '', comment)
    return label.strip()

def load_style_controls(soup) -> list:
    controls, style_seq, seen_py_ids = [], [0], set()
    current_section = None

    def _normalize_hex(h: str) -> str:
        h = h.strip().lower()
        if h.startswith("#") and len(h) == 4: h = "#" + h[1] * 2 + h[2] * 2 + h[3] * 2
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
        m = re.search(rf"(?<![a-zA-Z-]){re.escape(prop)}\s*:\s*(#[0-9a-fA-F]{{3,8}})", style_str)
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
            "id": f"sc-{len(controls)}", "style_id": sid,
            "section": current_section, "label": label,
            "type": ctype, "prop": prop, "value": val, "el": el,
        })

    for node in soup.descendants:
        if isinstance(node, Comment):
            current_section = str(node).strip()
            continue
        if not getattr(node, "name", None): continue
        if is_in_footer(node) or is_in_sidebar(node): continue
        style_str = node.get("style", "")
        if not style_str: continue
        tag = node.name

        if tag == "table":
            bg = _find_hex(style_str, "background-color")
            if bg: _add(node, "Card Background Color", "color", "background-color", bg)
        elif tag == "a":
            color = _find_hex(style_str, "color")
            if color: _add(node, "Title Link Color", "color", "color", color)
            fs = _find_font_size(style_str)
            if fs: _add(node, "Title Font Size", "number", "font-size", fs)
            accent = _find_hex(style_str, "--accent")
            if accent: _add(node, "Card Accent Color", "accent-color", "--accent", accent)
        elif tag == "td":
            direct_a = node.find("a", recursive=False)
            if direct_a and direct_a.get("data-editor-id"): continue
            bg_img = _find_bg_image(style_str)
            if bg_img and "singlecolorimage.com" not in bg_img:
                _add(node, "Background Image URL", "url", "background-image", bg_img)
            color = _find_hex(style_str, "color")
            if color: _add(node, "Body Text Color", "color", "color", color)
            bg = _find_hex(style_str, "background-color")
            if bg: _add(node, "Background Color", "color", "background-color", bg)
            fs = _find_font_size(style_str)
            if fs: _add(node, "Body Font Size", "number", "font-size", fs)
        elif tag == "span":
            color = _find_hex(style_str, "color")
            if color: _add(node, "Number Color", "color", "color", color)
            fs = _find_font_size(style_str)
            if fs: _add(node, "Number Font Size", "number", "font-size", fs)

    return controls

# ─────────────────────────────────────────────
# Layout & Equalization Helpers
# ─────────────────────────────────────────────

def equalize_card_heights(soup) -> None:
    EMAIL_WIDTH = 600
    all_trs = soup.find_all("tr")
    for tr in all_trs:
        card_tds = [td for td in tr.find_all("td", class_="col-stack", recursive=False)]
        if len(card_tds) < 2: continue
        card_widths = []
        for td in card_tds:
            w_attr = td.get("width", "33%").replace("%", "")
            try: pct = float(w_attr)
            except ValueError: pct = 33.0
            card_widths.append(EMAIL_WIDTH * pct / 100.0)
        heights = [_estimate_card_height(td, cw) for td, cw in zip(card_tds, card_widths)]
        if not heights: continue
        max_h = max(heights)
        for td, h in zip(card_tds, heights):
            diff = max_h - h
            if diff < 2: continue
            pad_px = int(math.ceil(diff))
            card_table = td.find("table", recursive=True)
            if not card_table: continue
            content_td = card_table.find("td", class_="card-content")
            if not content_td: continue
            existing_style = content_td.get("style", "")
            existing_style = re.sub(r';\s*padding-bottom\s*:[^;]*', '', existing_style, flags=re.I)
            existing_style = re.sub(r'^padding-bottom\s*:[^;]*;?\s*', '', existing_style, flags=re.I)
            content_td["style"] = existing_style.rstrip('; ') + f"; padding-bottom:{pad_px}px;"

def _estimate_card_height(card_td, container_width_px: float) -> float:
    total_h = 0.0
    card_table = card_td.find("table", recursive=True)
    if not card_table: return 0.0
    img = card_table.find("img")
    if img:
        img_h = _px(img.get("height", "0"))
        if img_h == 0: img_h = _px(_extract_style_val(img.get("style", ""), "height"))
        total_h += img_h + 1
    content_td = card_table.find("td", class_="card-content")
    if not content_td: return total_h
    padding_str = _extract_style_val(content_td.get("style", ""), "padding")
    pad_parts = [_px(p) for p in padding_str.split()]
    if len(pad_parts) == 3: pad_top, _, pad_bot = pad_parts
    elif len(pad_parts) == 4: pad_top, _, pad_bot, _ = pad_parts
    elif len(pad_parts) == 2: pad_top = pad_bot = pad_parts[0]
    elif len(pad_parts) == 1: pad_top = pad_bot = pad_parts[0]
    else: pad_top = pad_bot = 0.0
    total_h += pad_top + pad_bot
    pad_left = pad_parts[3] if len(pad_parts) == 4 else (pad_parts[1] if len(pad_parts) >= 2 else (pad_parts[0] if pad_parts else 0.0))
    pad_right = pad_parts[1] if len(pad_parts) >= 2 else (pad_parts[0] if pad_parts else 0.0)
    content_w = container_width_px - pad_left - pad_right - 2
    if content_w <= 0: content_w = 150
    card_inner = content_td.find("div", class_="card-inner")
    content_root = card_inner if card_inner else content_td
    for block in content_root.find_all(["p", "h2"]):
        text = block.get_text(strip=True)
        if not text: continue
        style = block.get("style", "")
        fs = _px(_extract_style_val(style, "font-size")) or 14.0
        lh_raw = _extract_style_val(style, "line-height")
        lh_px = (_px(lh_raw) if _px(lh_raw) >= 4 else fs * _px(lh_raw)) if lh_raw else fs * 1.4
        avg_char_w = fs * 0.52
        ls = _px(_extract_style_val(style, "letter-spacing"))
        if ls > 0: avg_char_w += ls
        chars_per_line = max(1, int(content_w / avg_char_w))
        num_lines = math.ceil(len(text) / chars_per_line)
        margin_str = _extract_style_val(style, "margin")
        m_parts = [_px(p) for p in margin_str.split()]
        mt = mb = (m_parts[0] if len(m_parts) == 1 else (m_parts[0] if len(m_parts) == 2 else m_parts[0])) if m_parts else 0.0
        if len(m_parts) >= 3: mb = m_parts[2]
        total_h += (num_lines * lh_px) + mt + mb
    return total_h

def _extract_style_val(style_str: str, prop: str) -> str:
    if not style_str: return ""
    m = re.search(rf'{re.escape(prop)}\s*:\s*([^;]+)', style_str, re.I)
    return m.group(1).strip() if m else ""

def _px(val: str) -> float:
    m = re.match(r'([\d.]+)', str(val).strip())
    return float(m.group(1)) if m else 0.0

def stamp_logo_spacer(soup) -> None:
    sidebar = soup.find(id="sidebar")
    if not sidebar: return
    for td in sidebar.find_all("td"):
        h = td.get("height")
        if not h: continue
        try: int(str(h))
        except ValueError: continue
        if [c for c in td.children if getattr(c, "name", None)]: continue
        text = td.get_text().strip()
        if text and text != "\xa0": continue
        td["data-logo-spacer"] = "true"
        return

# ─────────────────────────────────────────────
# Form & Rendering Helpers
# ─────────────────────────────────────────────

def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")

def fix_date_br(text: str) -> str:
    days = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
    for day in days:
        if text.startswith(day):
            rest = text[len(day):]
            if re.match(r'^\s*<br\s*/?>', rest, re.I):
                text = f"{day}<br>{re.sub(r'^\s*<br\s*/?>\s*', '', rest, flags=re.I)}"
            else: text = f"{day}<br>{rest.lstrip()}"
            break
    return text

def update_style_prop(style_str: str, prop: str, new_value: str) -> str:
    pattern = rf"(?<![a-zA-Z-])({re.escape(prop)}\s*:\s*)[^;]+"
    if re.search(pattern, style_str): return re.sub(pattern, rf"\g<1>{new_value}", style_str)
    sep = "" if style_str.rstrip().endswith(";") else ";"
    return f"{style_str.rstrip()}{sep} {prop}: {new_value};"

def sanitize_hex_color(raw: str):
    v = raw.strip()
    if re.match(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$", v): return v
    return None

def format_html(soup) -> str:
    return str(soup)

def strip_editor_attrs(soup) -> None:
    for el in soup.find_all(True):
        el.attrs.pop("data-editor-id", None)
        el.attrs.pop("data-style-id", None)
        el.attrs.pop("data-logo-spacer", None)
    for span in soup.find_all("span", {"data-temp-span": "true"}): span.unwrap()

def _normalize_br(s: str) -> str:
    return re.sub(r"<br\s*/?>", "<br>", s, flags=re.I)

def _process_form(form_data, file_path: str = None) -> str:
    soup, elems = load_elements(file_path)
    fix_link_visibility(elems)
    style_controls = load_style_controls(soup)
    stamp_logo_spacer(soup)

    for elem in elems:
        eid = elem["id"]
        key = f"field_{eid}"
        if key not in form_data: continue
        new_val, el, etype = form_data[key], elem["el"], elem["type"]

        if etype == "img":
            old_src = el.get("src", "")
            base = config.GITHUB_BASE if old_src.startswith(config.GITHUB_BASE) else ""
            full = base + new_val if base else new_val
            if full.strip() != old_src.strip(): el["src"] = full
        elif etype == "bg-img":
            old_url = elem["text"]
            base = config.GITHUB_BASE if old_url.startswith(config.GITHUB_BASE) else ""
            full = base + new_val if base else new_val
            if full.strip() == old_url.strip(): continue
            has_style_bg = bool(elem.get("_style_bg_url"))
            has_bg_attr  = bool(elem.get("_attr_bg_url"))
            if has_style_bg: el["style"] = update_style_prop(el.get("style", ""), "background-image", f"url('{full}')")
            if has_bg_attr: el["background"] = full
            if not has_style_bg and not has_bg_attr: el["style"] = update_style_prop(el.get("style", ""), "background-image", f"url('{full}')")
        elif etype == "href":
            if new_val.strip() != el.get("href", "").strip(): el["href"] = new_val
        else:
            new_html = superscript_ordinal(fix_date_br(new_val.replace("\n", "<br>")))
            if re.sub(r"\s+", "", _normalize_br(new_html)) == re.sub(r"\s+", "", _normalize_br(elem.get("inner_html", ""))): continue
            el.clear()
            frag = BeautifulSoup(new_html, "html.parser")
            for child in list(frag.contents): el.append(child)

    for sc in style_controls:
        key = f"style_{sc['id']}"
        if key not in form_data: continue
        new_val, el, prop, ctype = form_data[key].strip(), sc["el"], sc["prop"], sc["type"]
        if not new_val: continue
        if ctype == "color" or ctype == "accent-color":
            new_val = sanitize_hex_color(new_val)
            if new_val is None: continue
        elif ctype == "number": new_val = new_val + "px"
        elif ctype == "url":
            clean_url = re.sub(r"^url\(['\"]?|['\"]?\)$", "", new_val).strip()
            new_val = f"url('{clean_url}')"

        if ctype == "accent-color":
            old_hex = sc["value"].strip().lower()
            if old_hex and new_val and old_hex != new_val.lower():
                pattern = re.compile(re.escape(old_hex), re.IGNORECASE)
                if el.get("style"): el["style"] = pattern.sub(new_val, el["style"])
                for child in el.descendants:
                    if hasattr(child, "get") and child.get("style"): child["style"] = pattern.sub(new_val, child["style"])
            continue
        el["style"] = update_style_prop(el.get("style", ""), prop, new_val)

    spacer_height_raw = form_data.get("logo_spacer_height", "").strip()
    if spacer_height_raw:
        try:
            spacer_height = int(spacer_height_raw)
            if spacer_height >= 0:
                spacer_td = soup.find("td", {"data-logo-spacer": "true"})
                if spacer_td:
                    spacer_td["height"] = str(spacer_height)
                    spacer_td["style"] = update_style_prop(spacer_td.get("style", ""), "height", f"{spacer_height}px")
        except ValueError: pass

    strip_editor_attrs(soup)
    return format_html(soup)

def _render_field(elem: dict) -> str:
    eid, etype, text = elem["id"], elem["type"], elem["text"]
    if etype in ("img", "bg-img"):
        label = "🖼 Image URL" if etype == "img" else "🌄 Background Image URL"
        if text.startswith(config.GITHUB_BASE):
            filename = text[len(config.GITHUB_BASE):]
            prefix_block = f'<div class="img-prefix">📁 {config.GITHUB_BASE}</div>'
            inp = f'<input class="text-inp" type="text" name="field_{eid}" data-eid="{eid}" data-ftype="{etype}" data-base="{config.GITHUB_BASE}" value="{_esc(filename)}">'
        else:
            prefix_block = ""
            inp = f'<input class="text-inp" type="text" name="field_{eid}" data-eid="{eid}" data-ftype="{etype}" value="{_esc(text)}">'
        thumb = f'<img class="img-thumb" src="{_esc(text)}" data-thumb="{eid}" onerror="this.style.opacity=0.15" alt="">'
        return f'<div class="field"><div class="field-label">{label}</div>{thumb}{prefix_block}{inp}</div>'
    elif etype == "href":
        return f'<div class="field"><div class="field-label">🔗 Link URL</div><input class="text-inp" type="text" name="field_{eid}" data-eid="{eid}" data-ftype="href" value="{_esc(text)}"></div>'
    else:
        inner = elem.get("inner_html", elem["text"])
        display = re.sub(r"<[^>]+>", "", inner.replace("<br/>", "\n").replace("<br />", "\n").replace("<br>", "\n"))
        rows = max(8, min(14, display.count("\n") + 8))
        custom_label = elem.get("label_comment", "Text")
        return f'<div class="field"><div class="field-label">✏ {custom_label}</div><textarea name="field_{eid}" data-eid="{eid}" rows="{rows}">{_esc(display)}</textarea></div>'

def _render_style_control(sc: dict) -> str:
    sid, label, ctype, prop, val, sc_id = sc["style_id"], sc["label"], sc["type"], sc["prop"], sc["value"], sc["id"]
    if ctype in ("color", "accent-color"):
        hex6 = val.lower() if re.match(r"^#[0-9a-fA-F]{6}$", val) else "#000000"
        palette = ["#c8102e", "#c8781a", "#d4920f", "#8d3222", "#6d4c41", "#bf360c", "#1c4f7c", "#1565c0", "#37474f", "#00796b", "#2a7a5c", "#1b6e3a", "#8b2a6e", "#4a148c", "#6a1c4b", "#3d5a80", "#2d5986", "#1a1a1a"]
        swatches = "".join(f'<button type="button" class="swatch{"  swatch-active" if c == hex6 else ""}" style="background:{c}" data-color="{c}" data-sid="{sid}" data-prop="{prop}" data-ctype="{ctype}" title="{c}"></button>' for c in palette)
        return f'<div class="field"><div class="field-label">🎨 {label}</div><div class="palette-grid">{swatches}</div><input class="text-inp" type="text" name="style_{sc_id}" data-hexfor="{sid}" data-prop="{prop}" data-ctype="{ctype}" value="{hex6}" maxlength="7" placeholder="#rrggbb" style="width:90px;"></div>'
    elif ctype == "number":
        return f'<div class="field"><div class="field-label">🔠 {label}</div><div class="style-row"><input type="number" name="style_{sc_id}" data-sid="{sid}" data-prop="{prop}" value="{val}" min="1" max="120" step="0.5"><span class="unit">px</span></div></div>'
    elif ctype == "url":
        return f'<div class="field"><div class="field-label">🌄 {label}</div><input class="text-inp" type="text" name="style_{sc_id}" data-bgsid="{sid}" value="{_esc(val)}" placeholder="https://... house-icon.png"></div>'
    return ""

_ALIGNMENT_SCRIPT = """
<script>
(function() {
  function superscriptOrdinal(text) { if (typeof text !== 'string') return text; return text.replace(/(\\d+)th/g, '$1ᵗʰ').replace(/(\\d+)st/g, '$1ˢᵗ').replace(/(\\d+)nd/g, '$1ⁿᵈ').replace(/(\\d+)rd/g, '$1ʳᵈ'); }
  function runAlignment() {
    var mainContent = document.getElementById('main-content'); if (!mainContent) return;
    var allTables = mainContent.querySelectorAll('table'), cardTables = [];
    for (var i = 0; i < allTables.length; i++) { var s = allTables[i].getAttribute('style') || ''; if (s.indexOf('border-radius') !== -1 && s.indexOf('overflow: hidden') !== -1) cardTables.push(allTables[i]); }
    if (cardTables.length < 3) return;
    var card3 = cardTables[2], card3Rect = card3.getBoundingClientRect(), scrollY = window.pageYOffset || document.documentElement.scrollTop, card3MidY = card3Rect.top + scrollY + card3Rect.height / 2;
    var logoTd = document.querySelector('td[background*="newsband-logo"]');
    if (!logoTd) { var allTds = document.querySelectorAll('td'); for (var j = 0; j < allTds.length; j++) { var st = allTds[j].getAttribute('style') || ''; if (st.indexOf('newsband-logo') !== -1) { logoTd = allTds[j]; break; } } }
    if (!logoTd) return;
    var logoTdRect = logoTd.getBoundingClientRect(), logoTdTop = logoTdRect.top + scrollY, logoCurrentCenter = logoTdTop + 255;
    var spacerTd = document.querySelector('[data-logo-spacer="true"]'); if (!spacerTd) return;
    var currentHeight = parseInt(spacerTd.getAttribute('height') || '50', 10), delta = card3MidY - logoCurrentCenter, newHeight = Math.max(0, Math.round(currentHeight + delta));
    spacerTd.setAttribute('height', newHeight); spacerTd.style.height = newHeight + 'px'; spacerTd.style.lineHeight = newHeight + 'px';
    window.parent.postMessage({ type: 'spacer_computed', value: newHeight }, '*');
  }
  window.addEventListener('message', function(ev) {
    if (ev.data && ev.data.type === 'run_alignment') runAlignment();
    var d = ev.data; if (!d || !d.type) return;
    if (d.type === 'update') {
      var el = document.querySelector('[data-editor-id="' + d.id + '"]'); if (!el) return;
      if (d.fieldType === 'text') { el.innerHTML = superscriptOrdinal(d.value.replace(/\\n/g, '<br>')); }
      else if (d.fieldType === 'img') el.src = d.value;
      else if (d.fieldType === 'bg-img') el.style.backgroundImage = "url('" + d.value + "')";
      else if (d.fieldType === 'href') el.href = d.value;
      requestAnimationFrame(function() { setTimeout(equalizeCardHeights, 50); });
    }
    if (d.type === 'style') {
      var el = document.querySelector('[data-style-id="' + d.styleId + '"]'); if (!el) return;
      if (d.ctype === 'accent-color') {
        const oldHex = el.style.getPropertyValue('--accent').trim(); const newHex = d.value;
        if (oldHex && newHex && oldHex.toLowerCase() !== newHex.toLowerCase()) {
           var regex = new RegExp(oldHex, 'ig');
           function recUpdate(node) {
              if (node.nodeType === Node.ELEMENT_NODE) {
                 const st = node.getAttribute('style'); if (st && regex.test(st)) node.setAttribute('style', st.replace(regex, newHex));
                 for (let i=0; i<node.childNodes.length; i++) recUpdate(node.childNodes[i]);
              }
           }
           recUpdate(el);
        }
        return;
      }
      if (d.prop === 'background-image') el.style.backgroundImage = "url('" + d.value.replace(/^url\\(["']?|["']?\\)$/g, '') + "')";
      else if (d.prop === 'font-size') el.style.fontSize = d.value;
      else el.style.setProperty(d.prop, d.value);
    }
  });
  window.addEventListener('load', function() { setTimeout(runAlignment, 300); requestAnimationFrame(function() { setTimeout(equalizeCardHeights, 100); }); });
  function equalizeCardHeights() {
    var allTrs = document.querySelectorAll('tr');
    for (var t = 0; t < allTrs.length; t++) {
      var tr = allTrs[t], cardTds = [];
      for (var c = 0; c < tr.children.length; c++) { var ch = tr.children[c]; if (ch.tagName === 'TD' && ch.classList.contains('col-stack')) cardTds.push(ch); }
      if (cardTds.length < 2) continue;
      var cards = [];
      for (var i = 0; i < cardTds.length; i++) { var ctd = cardTds[i].querySelector('.card-content'), inner = ctd ? ctd.querySelector('.card-inner') : null; cards.push({td: cardTds[i], ctd: ctd, inner: inner}); }
      for (var i = 0; i < cards.length; i++) if (cards[i].ctd) cards[i].ctd.style.paddingBottom = '';
      void tr.offsetHeight; var heights = [];
      for (var i = 0; i < cards.length; i++) heights.push(cards[i].inner ? cards[i].inner.getBoundingClientRect().height : 0);
      var maxH = Math.max.apply(null, heights);
      for (var i = 0; i < cards.length; i++) { var diff = maxH - heights[i]; if (diff < 2 || !cards[i].ctd) continue; cards[i].ctd.style.paddingBottom = Math.round(diff) + 'px'; }
    }
  }
})();
</script>
"""

# Basic preview script — handles live update/style messages without alignment or card equalization.
# Used for templates that don't have the sidebar/logo alignment feature.
_BASIC_PREVIEW_SCRIPT = """
<script>
(function() {
  function superscriptOrdinal(text) {
    if (typeof text !== 'string') return text;
    return text.replace(/(\\d+)th/g, '$1ᵗʰ').replace(/(\\d+)st/g, '$1ˢᵗ').replace(/(\\d+)nd/g, '$1ⁿᵈ').replace(/(\\d+)rd/g, '$1ʳᵈ');
  }
  window.addEventListener('message', function(ev) {
    var d = ev.data; if (!d || !d.type) return;
    if (d.type === 'update') {
      var el = document.querySelector('[data-editor-id="' + d.id + '"]'); if (!el) return;
      if (d.fieldType === 'text') {
        el.innerHTML = superscriptOrdinal(d.value.replace(/\\n/g, '<br>'));
      } else if (d.fieldType === 'img') {
        el.src = d.value;
      } else if (d.fieldType === 'bg-img') {
        el.style.backgroundImage = "url('" + d.value + "')";
      } else if (d.fieldType === 'href') {
        el.href = d.value;
      }
    }
    if (d.type === 'style') {
      var el = document.querySelector('[data-style-id="' + d.styleId + '"]'); if (!el) return;
      if (d.ctype === 'accent-color') {
        var oldHex = el.style.getPropertyValue('--accent').trim(); var newHex = d.value;
        if (oldHex && newHex && oldHex.toLowerCase() !== newHex.toLowerCase()) {
           var regex = new RegExp(oldHex, 'ig');
           function recUpdate(node) {
              if (node.nodeType === Node.ELEMENT_NODE) {
                 var st = node.getAttribute('style'); if (st && regex.test(st)) node.setAttribute('style', st.replace(regex, newHex));
                 for (var i=0; i<node.childNodes.length; i++) recUpdate(node.childNodes[i]);
              }
           }
           recUpdate(el);
        }
        return;
      }
      if (d.prop === 'background-image') {
        el.style.backgroundImage = "url('" + d.value.replace(/^url\\(["']?|["']?\\)$/g, '') + "')";
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

