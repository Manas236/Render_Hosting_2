from flask import Blueprint, request, redirect, url_for, Response, render_template_string
from bs4 import BeautifulSoup, Comment
from collections import defaultdict
import config
import helpers
from helpers import require_login

editor_bp = Blueprint('editor_bp', __name__)

EDITOR_PAGE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Newsband Editor</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #eef0f6; color: #1e2235; display: flex; flex-direction: column; height: 100vh; overflow: hidden; }
  #topbar { background: #ffffff; border-bottom: 1px solid #dde2ee; padding: 0 20px; height: 52px; display: flex; align-items: center; gap: 10px; flex-shrink: 0; box-shadow: 0 1px 4px rgba(0,0,0,0.07); }
  #topbar h1 { font-size: 15px; font-weight: 700; color: #1e2235; flex: 1; letter-spacing: 0.3px; }
  #topbar h1 span { color: #3b5bdb; }
  .btn { padding: 7px 18px; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 600; letter-spacing: 0.2px; transition: background 0.15s, transform 0.1s; }
  .btn:active { transform: scale(0.97); }
  .btn-save { background: #3b5bdb; color: #fff; }
  .btn-save:hover { background: #2f4ec4; }
  .btn-dl { background: #f0f2f8; color: #445; border: 1px solid #dde2ee; }
  .btn-dl:hover { background: #e2e6f3; }
  .btn-reset { background: transparent; color: #99a; border: 1px solid #dde2ee; }
  .btn-reset:hover { background: #f5f6fb; color: #556; }
  #main { display: flex; flex: 1; overflow: hidden; }
  #panel { width: 680px; min-width: 380px; background: #ffffff; overflow-y: auto; border-right: 1px solid #dde2ee; flex-shrink: 0; }
  #panel::-webkit-scrollbar { width: 6px; }
  #panel::-webkit-scrollbar-thumb { background: #d0d5e8; border-radius: 3px; }
  .sec-banner { background: #f0f3fb; border-left: 3px solid #3b5bdb; padding: 9px 14px; margin-top: 6px; font-size: 13px; font-weight: 700; letter-spacing: 1.2px; text-transform: uppercase; color: #3b5bdb; }
  .field { padding: 9px 14px 8px; border-bottom: 1px solid #f0f2f8; }
  .field-label { font-size: 13px; letter-spacing: 0.5px; text-transform: uppercase; color: #8898c0; margin-bottom: 6px; font-weight: 600; }
  textarea, .text-inp { width: 100%; background: #f7f8fc; color: #1e2235; border: 1px solid #dde2ee; border-radius: 5px; padding: 9px 11px; font-size: 15px; font-family: inherit; outline: none; transition: border-color 0.2s; }
  textarea { resize: vertical; min-height: 90px; font-size: 15px; padding: 10px 12px; line-height: 1.6; }
  textarea:focus, .text-inp:focus { border-color: #3b5bdb; background: #fff; }
  .img-thumb { width: 100%; height: 280px; object-fit: cover; border-radius: 4px; background: #eef0f6; display: block; margin-bottom: 5px; }
  .img-prefix { font-size: 12px; color: #aab; margin-bottom: 3px; word-break: break-all; }
  .style-row { display: flex; align-items: center; gap: 7px; }
  .palette-grid { display: grid; grid-template-columns: repeat(6, 26px); gap: 5px; margin-bottom: 7px; }
  .swatch { width: 26px; height: 26px; border-radius: 4px; border: 2px solid transparent; cursor: pointer; padding: 0; transition: transform 0.1s, border-color 0.1s; }
  .swatch:hover { transform: scale(1.15); }
  .swatch-active { border-color: #1e2235 !important; box-shadow: 0 0 0 1px #fff inset; }
  input[type=number] { width: 80px; background: #f7f8fc; color: #1e2235; border: 1px solid #dde2ee; border-radius: 5px; padding: 7px 10px; font-size: 15px; outline: none; }
  input[type=number]:focus { border-color: #3b5bdb; }
  .unit { font-size: 14px; color: #8898c0; }
  #align-status { display: inline-flex; align-items: center; gap: 6px; font-size: 11px; font-weight: 600; padding: 4px 10px; border-radius: 20px; background: #f0f3fb; color: #8898c0; border: 1px solid #dde2ee; transition: all 0.3s; white-space: nowrap; }
  #align-status.aligned { background: #ebfbee; color: #2f9e44; border-color: #b2f2bb; }
  #align-status.computing { background: #fff9db; color: #e67700; border-color: #ffe066; }
  #align-dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; flex-shrink: 0; }
  #preview-wrap { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
  #preview-bar { background: #ffffff; border-bottom: 1px solid #dde2ee; padding: 7px 16px; font-size: 11px; color: #8898c0; display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
  .live-dot { width: 7px; height: 7px; border-radius: 50%; background: #40c057; flex-shrink: 0; }
  iframe { flex: 1; border: none; width: 100%; height: 100%; }
  #toast { position: fixed; bottom: 20px; right: 20px; background: #2f9e44; color: #fff; padding: 10px 18px; border-radius: 8px; font-size: 13px; font-weight: 600; opacity: 0; pointer-events: none; transition: opacity 0.3s; z-index: 9999; }
  #toast.show { opacity: 1; }
</style>
</head>
<body>
<div id="topbar">
  <a href="/dashboard" class="btn btn-reset" style="text-decoration:none; display:inline-flex; align-items:center; margin-right: 14px; padding: 5px 12px; font-size: 13px;">← Dashboard</a>
  <h1>📰 Newsband <span>{{template_name}}</span></h1>
  {% if has_alignment %}
  <span id="align-status"><span id="align-dot"></span><span id="align-text">Logo alignment pending…</span></span>
  {% endif %}
  <button class="btn btn-reset" onclick="confirmReset()">↺ Reset</button>
  <button class="btn btn-dl" onclick="submitForm('download')">⬇ Download HTML</button>
  <button class="btn btn-save" onclick="manualSave()">💾 Save</button>
  <a href="/logout" class="btn btn-reset" style="text-decoration:none; display:inline-flex; align-items:center;">🚪 Logout</a>
</div>
<div id="main">
  <div id="panel">
    <form id="eform" method="POST" action="/editor/save">
      {{form_html|safe}}
      <input type="hidden" name="logo_spacer_height" id="logo_spacer_height" value="">
      <input type="hidden" name="dom_html" id="dom_html" value="">
    </form>
  </div>
  <div id="preview-wrap">
    <div id="preview-bar"><span class="live-dot"></span> Live Preview — changes appear instantly</div>
    <iframe id="pframe" src="/editor/preview/{{tid}}" onload="onPreviewLoad()"></iframe>
  </div>
</div>
<div id="toast">✔ Saved!</div>
<script>
const frame = () => document.getElementById('pframe').contentWindow;
function post(msg) { try { frame().postMessage(msg, '*'); } catch(e) { } }
function showToast(msg) { const t = document.getElementById('toast'); t.textContent = msg; t.classList.add('show'); setTimeout(() => t.classList.remove('show'), 2200); }
function setAlignStatus(state, spacerPx) {
  const pill = document.getElementById('align-status'), txt = document.getElementById('align-text');
  pill.classList.remove('aligned', 'computing');
  if (state === 'computing') { pill.classList.add('computing'); txt.textContent = 'Computing logo alignment…'; }
  else if (state === 'aligned') { pill.classList.add('aligned'); txt.textContent = '✓ Logo aligned to card 3 (spacer: ' + spacerPx + 'px)'; }
  else { txt.textContent = 'Logo alignment pending…'; }
}
function onPreviewLoad() { {% if has_alignment %}setAlignStatus('computing');{% endif %} pushAllStateToIframe(); {% if has_alignment %}setTimeout(() => post({ type: 'run_alignment' }), 400);{% endif %} }
window.addEventListener('message', function(ev) { if (ev.data && ev.data.type === 'spacer_computed') { document.getElementById('logo_spacer_height').value = ev.data.value; setAlignStatus('aligned', ev.data.value); } });
function triggerRealign() { {% if has_alignment %}setAlignStatus('computing'); setTimeout(() => post({ type: 'run_alignment' }), 250);{% endif %} }
document.querySelectorAll('textarea[data-eid]').forEach(el => { el.addEventListener('input', () => { post({ type: 'update', id: el.dataset.eid, fieldType: 'text', value: el.value }); triggerRealign(); }); });
document.querySelectorAll('input[data-eid][data-ftype="img"]').forEach(el => { el.addEventListener('input', () => { const base = el.dataset.base || '', full = base + el.value; post({ type: 'update', id: el.dataset.eid, fieldType: 'img', value: full }); const thumb = document.querySelector('img[data-thumb="' + el.dataset.eid + '"]'); if (thumb) thumb.src = full; triggerRealign(); }); });
document.querySelectorAll('input[data-eid][data-ftype="bg-img"]').forEach(el => { el.addEventListener('input', () => { const base = el.dataset.base || '', full = base + el.value; post({ type: 'update', id: el.dataset.eid, fieldType: 'bg-img', value: full }); const thumb = document.querySelector('img[data-thumb="' + el.dataset.eid + '"]'); if (thumb) thumb.src = full; triggerRealign(); }); });
document.querySelectorAll('input[data-eid][data-ftype="href"]').forEach(el => { el.addEventListener('input', () => { post({ type: 'update', id: el.dataset.eid, fieldType: 'href', value: el.value }); }); });
document.addEventListener('click', e => {
  const sw = e.target.closest('.swatch'); if (!sw) return;
  const hex = sw.dataset.color, sid = sw.dataset.sid;
  sw.closest('.palette-grid').querySelectorAll('.swatch').forEach(s => s.classList.remove('swatch-active')); sw.classList.add('swatch-active');
  const txt = document.querySelector('input[data-hexfor="' + sid + '"]'); if (txt) txt.value = hex;
  post({ type: 'style', styleId: sid, prop: sw.dataset.prop, ctype: sw.dataset.ctype, value: hex });
});
document.querySelectorAll('input[data-hexfor]').forEach(el => { el.addEventListener('input', () => { if (/^#[0-9a-fA-F]{6}$/.test(el.value)) { post({ type: 'style', styleId: el.dataset.hexfor, prop: el.dataset.prop, ctype: el.dataset.ctype, value: el.value }); } }); });
document.querySelectorAll('input[type=number][data-sid]').forEach(el => { el.addEventListener('input', () => { post({ type: 'style', styleId: el.dataset.sid, prop: el.dataset.prop, value: el.value + 'px' }); triggerRealign(); }); });
document.querySelectorAll('input[data-bgsid]').forEach(el => { el.addEventListener('input', () => { post({ type: 'style', styleId: el.dataset.bgsid, prop: 'background-image', value: "url('" + el.value + "')" }); }); });
function submitForm(action) {
  saveState(); const form = document.getElementById('eform'); form.action = '/editor/' + action + '/{{tid}}';
  if (action === 'download') { const iframe = document.querySelector('iframe'), domField = document.getElementById('dom_html'); if (iframe && iframe.contentDocument && domField) domField.value = iframe.contentDocument.documentElement.outerHTML; }
  form.submit();
}
function confirmReset() { if (confirm('Reset to original template? All unsaved changes will be lost.')) { localStorage.removeItem('newsband_editor_{{tid}}'); window.location.reload(); } }
function saveState() { const data = {}, fd = new FormData(document.getElementById('eform')); for (let [k, v] of fd.entries()) { data[k] = v; } localStorage.setItem('newsband_editor_{{tid}}', JSON.stringify(data)); }
function restoreState() { const saved = localStorage.getItem('newsband_editor_{{tid}}'); if (!saved) return; try { const data = JSON.parse(saved); for (let k in data) { const el = document.querySelector('[name="' + k + '"]'); if (el && el.value !== data[k]) el.value = data[k]; } } catch(e) { } }
document.getElementById('eform').addEventListener('input', saveState); window.addEventListener('DOMContentLoaded', restoreState);
function pushAllStateToIframe() {
  document.querySelectorAll('textarea[data-eid]').forEach(el => post({ type: 'update', id: el.dataset.eid, fieldType: 'text', value: el.value }));
  document.querySelectorAll('input[data-eid][data-ftype="img"]').forEach(el => { const base = el.dataset.base || ''; post({ type: 'update', id: el.dataset.eid, fieldType: 'img', value: base + el.value }); const thumb = document.querySelector('img[data-thumb="' + el.dataset.eid + '"]'); if (thumb) thumb.src = base + el.value; });
  document.querySelectorAll('input[data-eid][data-ftype="bg-img"]').forEach(el => { const base = el.dataset.base || ''; post({ type: 'update', id: el.dataset.eid, fieldType: 'bg-img', value: base + el.value }); const thumb = document.querySelector('img[data-thumb="' + el.dataset.eid + '"]'); if (thumb) thumb.src = base + el.value; });
  document.querySelectorAll('input[data-eid][data-ftype="href"]').forEach(el => post({ type: 'update', id: el.dataset.eid, fieldType: 'href', value: el.value }));
  document.querySelectorAll('input[data-hexfor]').forEach(el => post({ type: 'style', styleId: el.dataset.hexfor, prop: el.dataset.prop, ctype: el.dataset.ctype, value: el.value }));
  document.querySelectorAll('input[type=number][data-sid]').forEach(el => post({ type: 'style', styleId: el.dataset.sid, prop: el.dataset.prop, value: el.value + 'px' }));
  document.querySelectorAll('input[data-bgsid]').forEach(el => post({ type: 'style', styleId: el.dataset.bgsid, prop: 'background-image', value: "url('" + el.value + "')" }));
}
function manualSave() { saveState(); showToast('✔ Saved to your browser!'); }
</script>
</body>
</html>
"""

@editor_bp.route("/editor/<tid>")
@require_login
def editor(tid):
    """Main editor page — two-panel layout."""
    tcfg = config.TEMPLATES_CONFIG.get(tid)
    if not tcfg: return redirect(url_for('dashboard_bp.dashboard'))
    
    file_path = tcfg["file"]
    soup, elems = helpers.load_elements(file_path)
    helpers.fix_link_visibility(elems)
    style_controls = helpers.load_style_controls(soup)
    eid_to_elem = {e["id"]: e for e in elems}
    section_mapping = helpers.load_section_comments(soup)
    for eid, elem in eid_to_elem.items():
        if eid in section_mapping:
            lbl = helpers.get_field_label(section_mapping[eid])
            if lbl: elem["label_comment"] = lbl
    sid_to_scs = defaultdict(list)
    for sc in style_controls: sid_to_scs[sc["style_id"]].append(sc)

    form_parts, last_section, rendered_eids, rendered_sids = [], None, set(), set()
    for node in soup.descendants:
        if isinstance(node, Comment):
            section = str(node).strip()
            if section and section != last_section:
                last_section = section
                is_structural = section.upper().startswith("END") or "┌─" in section or "\n" in section
                if not helpers._section_is_footer(section) and not is_structural:
                    form_parts.append(f'<div class="sec-banner">📋 {helpers._esc(section.strip("= ").strip())}</div>')
        elif hasattr(node, "get"):
            eid, sid = node.get("data-editor-id"), node.get("data-style-id")
            if eid and eid in eid_to_elem and eid not in rendered_eids:
                elem = eid_to_elem[eid]
                if elem.get("visible", True): rendered_eids.add(eid); form_parts.append(helpers._render_field(elem))
            if sid and sid not in rendered_sids and sid in sid_to_scs:
                rendered_sids.add(sid)
                for sc in sid_to_scs[sid]: form_parts.append(helpers._render_style_control(sc))

    return render_template_string(
        EDITOR_PAGE, 
        form_html="\n".join(form_parts),
        tid=tid,
        template_name=tcfg["name"],
        has_alignment=tcfg.get("has_alignment", False)
    )

@editor_bp.route("/editor/preview/<tid>")
@require_login
def preview(tid):
    tcfg = config.TEMPLATES_CONFIG.get(tid)
    if not tcfg: return ""
    
    soup, _ = helpers.load_elements(tcfg["file"])
    helpers.load_style_controls(soup)
    
    if tcfg.get("has_alignment"):
        helpers.stamp_logo_spacer(soup)
        script_html = helpers._ALIGNMENT_SCRIPT
    else:
        script_html = helpers._BASIC_PREVIEW_SCRIPT
    
    script_tag = BeautifulSoup(script_html, "html.parser")
    body = soup.find("body")
    if body: body.append(script_tag)
        
    return Response(str(soup), mimetype="text/html")


@editor_bp.route("/editor/save/<tid>", methods=["POST"])
@require_login
def save(tid):
    return redirect(url_for('editor_bp.editor', tid=tid))

@editor_bp.route("/editor/download/<tid>", methods=["POST"])
@require_login
def download(tid):
    tcfg = config.TEMPLATES_CONFIG.get(tid)
    if not tcfg: return redirect(url_for('dashboard_bp.dashboard'))

    dom_html = request.form.get("dom_html", "").strip()
    if dom_html:
        soup = BeautifulSoup(dom_html, "html.parser")
        for script in soup.find_all("script"): script.decompose()
        helpers.strip_editor_attrs(soup)
        html = helpers.format_html(soup)
    else:
        logging.warning("download: dom_html not supplied; falling back to _process_form")
        html = helpers._process_form(request.form, tcfg["file"])
    return Response(html, mimetype="text/html", headers={"Content-Disposition": f'attachment; filename="{tcfg["file"].replace(".html", "")}_edited.html"'})
