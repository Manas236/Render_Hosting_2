from flask import Blueprint, request, render_template_string
from helpers import require_login, allowed_file

codeview_bp = Blueprint('codeview_bp', __name__)

CONVERTER_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>HTML Code Viewer</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet" />
    <style>
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: "DM Sans", sans-serif; background-color: #f5f4f0; color: #1a1a1a; min-height: 100vh; display: flex; flex-direction: column; align-items: center; padding: 48px 20px 64px; }
        header { text-align: center; margin-bottom: 40px; position: relative; }
        header h1 { font-size: 1.9rem; font-weight: 600; letter-spacing: -0.5px; color: #111; }
        header p { margin-top: 8px; font-size: 0.95rem; color: #666; }
        .btn-back-wrap { margin-bottom: 24px; text-align: center; }
        .btn-back { display: inline-block; font-size: 0.9rem; color: #555; text-decoration: none; font-weight: 500; transition: color 0.15s; }
        .btn-back:hover { color: #111; }
        .card { background: #ffffff; border: 1px solid #e0ddd6; border-radius: 14px; padding: 32px; width: 100%; max-width: 700px; box-shadow: 0 2px 12px rgba(0, 0, 0, 0.05); }
        .upload-zone { border: 2px dashed #c9c5bb; border-radius: 10px; padding: 40px 24px; text-align: center; background: #faf9f6; transition: border-color 0.2s, background 0.2s; cursor: pointer; }
        .upload-zone:hover, .upload-zone.drag-over { border-color: #888; background: #f2f1ec; }
        .upload-zone input[type="file"] { display: none; }
        .upload-icon { font-size: 2.4rem; margin-bottom: 12px; display: block; }
        .upload-zone label { display: block; cursor: pointer; }
        .upload-zone .upload-main-text { font-size: 1rem; font-weight: 500; color: #333; }
        .upload-zone .upload-sub-text { font-size: 0.85rem; color: #888; margin-top: 6px; }
        .selected-file-name { margin-top: 12px; font-size: 0.85rem; color: #555; font-family: "DM Mono", monospace; }
        .btn-primary { display: block; width: 100%; margin-top: 20px; padding: 13px; background: #1a1a1a; color: #fff; font-family: "DM Sans", sans-serif; font-size: 0.95rem; font-weight: 500; border: none; border-radius: 8px; cursor: pointer; transition: background 0.18s, transform 0.1s; }
        .btn-primary:hover { background: #333; }
        .btn-primary:active { transform: scale(0.99); }
        .error-banner { background: #fff1f1; border: 1px solid #f5c2c2; color: #b00020; border-radius: 8px; padding: 12px 16px; font-size: 0.9rem; margin-bottom: 20px; }
        .code-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
        .code-filename { font-size: 0.88rem; font-weight: 500; color: #555; font-family: "DM Mono", monospace; background: #f0ede7; padding: 4px 10px; border-radius: 6px; }
        .btn-copy { display: flex; align-items: center; gap: 6px; padding: 8px 16px; background: #f0ede7; border: 1px solid #ddd8cf; border-radius: 7px; font-family: "DM Sans", sans-serif; font-size: 0.88rem; font-weight: 500; color: #333; cursor: pointer; transition: background 0.15s, border-color 0.15s; }
        .btn-copy:hover { background: #e6e2da; border-color: #c9c5bb; }
        .btn-copy.copied { background: #e8f5e9; border-color: #a5d6a7; color: #2e7d32; }
        .code-block-wrapper { position: relative; background: #faf9f7; border: 1px solid #e5e2da; border-radius: 10px; overflow: hidden; }
        pre { overflow-x: auto; overflow-y: auto; max-height: 520px; padding: 20px 22px; font-family: "DM Mono", monospace; font-size: 0.82rem; line-height: 1.75; color: #2d2d2d; white-space: pre; }
        .upload-another { display: inline-block; margin-top: 24px; font-size: 0.88rem; color: #888; text-decoration: none; border-bottom: 1px solid #ccc; padding-bottom: 1px; transition: color 0.15s, border-color 0.15s; }
        .upload-another:hover { color: #333; border-color: #555; }
    </style>
</head>
<body>
    <div class="btn-back-wrap"><a href="/dashboard" class="btn-back">← Back to Dashboard</a></div>
    <header><h1>HTML Code Viewer</h1><p>Upload an HTML file to view and copy its source code.</p></header>
    <div class="card">
        {% if error %}<div class="error-banner">⚠ {{ error }}</div>{% endif %}
        {% if not code %}
        <form method="POST" action="/converter" enctype="multipart/form-data" id="uploadForm">
            <div class="upload-zone" id="dropZone" onclick="document.getElementById('fileInput').click()">
                <span class="upload-icon">📄</span>
                <label><span class="upload-main-text">Click to choose a file</span><span class="upload-sub-text">or drag and drop it here · .html / .htm only</span></label>
                <input type="file" id="fileInput" name="file" accept=".html,.htm" onchange="handleFileSelect(this)" />
                <div class="selected-file-name" id="fileName"></div>
            </div>
            <button type="submit" class="btn-primary">View Source Code →</button>
        </form>
        {% else %}
        <div class="code-header"><span class="code-filename">{{ filename }}</span><button class="btn-copy" id="copyBtn" onclick="copyCode()"><span id="copyIcon">⎘</span><span id="copyLabel">Copy Code</span></button></div>
        <div class="code-block-wrapper"><pre id="codeContent">{{ code }}</pre></div>
        <a href="/converter" class="upload-another">← Upload another file</a>
        {% endif %}
    </div>
    <script>
        const dropZone = document.getElementById("dropZone");
        if (dropZone) {
            dropZone.addEventListener("dragover", (e) => { e.preventDefault(); dropZone.classList.add("drag-over"); });
            dropZone.addEventListener("dragleave", () => { dropZone.classList.remove("drag-over"); });
            dropZone.addEventListener("drop", (e) => { e.preventDefault(); dropZone.classList.remove("drag-over"); const files = e.dataTransfer.files; if (files.length > 0) { const input = document.getElementById("fileInput"); input.files = files; handleFileSelect(input); } });
        }
        function handleFileSelect(input) { const nameEl = document.getElementById("fileName"); if (input.files.length > 0) nameEl.textContent = "Selected: " + input.files[0].name; }
        function copyCode() {
            const code = document.getElementById("codeContent").textContent;
            function showCopied() {
                const btn = document.getElementById("copyBtn"), label = document.getElementById("copyLabel"), icon = document.getElementById("copyIcon");
                btn.classList.add("copied"); label.textContent = "Copied!"; icon.textContent = "✓";
                setTimeout(() => { btn.classList.remove("copied"); label.textContent = "Copy Code"; icon.textContent = "⎘"; }, 2000);
            }
            if (navigator.clipboard && navigator.clipboard.writeText) { navigator.clipboard.writeText(code).then(showCopied).catch(() => { const ta = document.createElement("textarea"); ta.value = code; ta.style.position = "fixed"; ta.style.opacity = "0"; document.body.appendChild(ta); ta.select(); document.execCommand("copy"); document.body.removeChild(ta); showCopied(); }); }
            else { const ta = document.createElement("textarea"); ta.value = code; ta.style.position = "fixed"; ta.style.opacity = "0"; document.body.appendChild(ta); ta.select(); document.execCommand("copy"); document.body.removeChild(ta); showCopied(); }
        }
    </script>
</body>
</html>
"""

@codeview_bp.route("/converter", methods=["GET", "POST"])
@require_login
def converter():
    if request.method == "POST":
        file = request.files.get("file")
        if not file or file.filename == "": return render_template_string(CONVERTER_HTML, error="No file selected.", code=None)
        if not allowed_file(file.filename): return render_template_string(CONVERTER_HTML, error="Only .html and .htm files are accepted.", code=None)
        try:
            raw_bytes = file.read()
            code_text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError: return render_template_string(CONVERTER_HTML, error="Could not read the file. Make sure it is a valid UTF-8 HTML file.", code=None)
        return render_template_string(CONVERTER_HTML, code=code_text, filename=file.filename, error=None)
    return render_template_string(CONVERTER_HTML, code=None, error=None)
