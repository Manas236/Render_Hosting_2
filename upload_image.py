from flask import Blueprint, request, jsonify, render_template_string
import os
import uuid
import time
from werkzeug.utils import secure_filename

upload_image_bp = Blueprint('upload_image_bp', __name__)

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploaded_images")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}
PUBLIC_BASE_URL = os.environ.get('PUBLIC_BASE_URL', 'https://newsbandnewsletter.in')
_CLEANUP_AGE_SECONDS = 150 * 86400  # 150 days


def cleanup_old_images() -> int:
    """Delete images older than 150 days. Returns count of files removed."""
    cutoff = time.time() - _CLEANUP_AGE_SECONDS
    real_upload_dir = os.path.realpath(UPLOAD_DIR)
    removed = 0
    try:
        for fname in os.listdir(real_upload_dir):
            fpath = os.path.join(real_upload_dir, fname)
            real_fpath = os.path.realpath(fpath)
            # Only delete regular files that live directly inside UPLOAD_DIR
            if os.path.dirname(real_fpath) != real_upload_dir:
                continue
            if os.path.isfile(real_fpath) and os.path.getmtime(real_fpath) < cutoff:
                os.remove(real_fpath)
                removed += 1
    except OSError:
        pass
    return removed


HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Image Uploader</title>
  <style>
    /* ── Theme variables ── */
    body.theme-dark {
      --bg:         #0f1117;
      --card:       #1a1d27;
      --border:     #2d3148;
      --input-bg:   #0f1117;
      --text:       #e2e8f0;
      --subtext:    #4b5563;
      --label:      #94a3b8;
      --accent:     #7c3aed;
      --accent-h:   #6d28d9;
      --accent-dim: #3b2f6e;
      --badge-bg:   #12151f;
      --badge-col:  #a78bfa;
      --btn-text:   #ffffff;
    }
    body.theme-light {
      --bg:         #f1f5f9;
      --card:       #ffffff;
      --border:     #e2e8f0;
      --input-bg:   #f8fafc;
      --text:       #1e293b;
      --subtext:    #94a3b8;
      --label:      #64748b;
      --accent:     #6d28d9;
      --accent-h:   #5b21b6;
      --accent-dim: #c4b5fd;
      --badge-bg:   #ede9fe;
      --badge-col:  #6d28d9;
      --btn-text:   #ffffff;
    }
    body.theme-dracula {
      --bg:         #282a36;
      --card:       #1e1f29;
      --border:     #44475a;
      --input-bg:   #282a36;
      --text:       #f8f8f2;
      --subtext:    #6272a4;
      --label:      #bd93f9;
      --accent:     #ff79c6;
      --accent-h:   #ff5baf;
      --accent-dim: #6b2e52;
      --badge-bg:   #44475a;
      --badge-col:  #bd93f9;
      --btn-text:   #282a36;
    }
    body.theme-forest {
      --bg:         #0d1f0f;
      --card:       #132a15;
      --border:     #2a4d2d;
      --input-bg:   #0d1f0f;
      --text:       #d4edda;
      --subtext:    #4a7a50;
      --label:      #81c784;
      --accent:     #43a047;
      --accent-h:   #388e3c;
      --accent-dim: #1b4d1e;
      --badge-bg:   #1b3a1e;
      --badge-col:  #a5d6a7;
      --btn-text:   #ffffff;
    }
    body.theme-ocean {
      --bg:         #05101f;
      --card:       #0a1e35;
      --border:     #163354;
      --input-bg:   #05101f;
      --text:       #cfe8ff;
      --subtext:    #3a6a9a;
      --label:      #64b5f6;
      --accent:     #0288d1;
      --accent-h:   #0277bd;
      --accent-dim: #01375a;
      --badge-bg:   #0d2744;
      --badge-col:  #4fc3f7;
      --btn-text:   #ffffff;
    }
    body.theme-sunset {
      --bg:         #1a0a00;
      --card:       #2b1100;
      --border:     #4d2000;
      --input-bg:   #1a0a00;
      --text:       #ffe8cc;
      --subtext:    #7a3b00;
      --label:      #ffb74d;
      --accent:     #f4511e;
      --accent-h:   #e64a19;
      --accent-dim: #6b1f0a;
      --badge-bg:   #3d1500;
      --badge-col:  #ff8a65;
      --btn-text:   #ffffff;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      font-family: 'Segoe UI', sans-serif;
      background: var(--bg);
      color: var(--text);
      display: flex;
      justify-content: center;
      align-items: flex-start;
      min-height: 100vh;
      padding: 30px 20px;
      transition: background 0.3s, color 0.3s;
    }

    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 36px;
      width: 100%;
      max-width: 520px;
      box-shadow: 0 8px 40px rgba(0,0,0,0.4);
      transition: background 0.3s, border-color 0.3s;
    }

    /* ── Back to dashboard ── */
    .back-link {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 0.8rem;
      font-weight: 600;
      color: var(--label);
      text-decoration: none;
      margin-bottom: 20px;
      padding: 8px 14px;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--badge-bg);
      transition: color 0.2s, border-color 0.2s, background 0.2s;
    }
    .back-link:hover {
      color: var(--accent);
      border-color: var(--accent);
    }

    /* ── Theme switcher ── */
    .theme-bar {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 28px;
      flex-wrap: wrap;
    }
    .theme-bar span {
      font-size: 0.72rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.07em;
      color: var(--label);
      margin-right: 4px;
    }
    .theme-btn {
      width: 26px; height: 26px;
      border-radius: 50%;
      border: 2px solid transparent;
      cursor: pointer;
      transition: transform 0.15s, border-color 0.15s;
      position: relative;
    }
    .theme-btn:hover { transform: scale(1.18); }
    .theme-btn.active { border-color: var(--text); transform: scale(1.18); }
    .theme-btn[data-theme="dark"]    { background: radial-gradient(circle at 35% 35%, #4b5563, #0f1117); }
    .theme-btn[data-theme="light"]   { background: radial-gradient(circle at 35% 35%, #ffffff, #cbd5e1); }
    .theme-btn[data-theme="dracula"] { background: radial-gradient(circle at 35% 35%, #ff79c6, #282a36); }
    .theme-btn[data-theme="forest"]  { background: radial-gradient(circle at 35% 35%, #43a047, #0d1f0f); }
    .theme-btn[data-theme="ocean"]   { background: radial-gradient(circle at 35% 35%, #0288d1, #05101f); }
    .theme-btn[data-theme="sunset"]  { background: radial-gradient(circle at 35% 35%, #f4511e, #1a0a00); }

    /* tooltip */
    .theme-btn::after {
      content: attr(data-label);
      position: absolute;
      bottom: 130%; left: 50%;
      transform: translateX(-50%);
      background: var(--card);
      border: 1px solid var(--border);
      color: var(--text);
      font-size: 0.7rem;
      padding: 3px 7px;
      border-radius: 4px;
      white-space: nowrap;
      pointer-events: none;
      opacity: 0;
      transition: opacity 0.15s;
    }
    .theme-btn:hover::after { opacity: 1; }

    /* ── Header ── */
    h1 { font-size: 1.5rem; color: var(--accent); margin-bottom: 6px; }
    .subtitle { font-size: 0.85rem; color: var(--subtext); margin-bottom: 22px; }
    .repo-badge {
      display: inline-block;
      background: var(--badge-bg);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 6px 12px;
      font-family: monospace;
      font-size: 0.78rem;
      color: var(--badge-col);
      margin-bottom: 28px;
      word-break: break-all;
    }

    label {
      display: block;
      font-size: 0.78rem;
      font-weight: 600;
      color: var(--label);
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 8px;
    }

    /* ── Drop zone ── */
    .drop-zone {
      border: 2px dashed var(--border);
      border-radius: 10px;
      padding: 36px 20px;
      text-align: center;
      cursor: pointer;
      transition: border-color 0.2s, background 0.2s;
      margin-bottom: 16px;
      position: relative;
    }
    .drop-zone:hover, .drop-zone.dragover {
      border-color: var(--accent);
      background: var(--badge-bg);
    }
    .drop-zone input[type="file"] {
      position: absolute; inset: 0; opacity: 0; cursor: pointer; width: 100%; height: 100%;
    }
    .drop-icon { font-size: 2rem; margin-bottom: 10px; }
    .drop-text { font-size: 0.9rem; color: var(--subtext); }
    .drop-text span { color: var(--badge-col); text-decoration: underline; }

    .file-preview {
      display: none;
      align-items: center;
      gap: 12px;
      background: var(--badge-bg);
      border-radius: 8px;
      padding: 10px 14px;
      margin-bottom: 20px;
    }
    .file-preview img { width: 48px; height: 48px; object-fit: cover; border-radius: 6px; }
    .file-name { font-size: 0.85rem; color: var(--text); word-break: break-all; }
    .file-size { font-size: 0.75rem; color: var(--subtext); }

    button {
      width: 100%;
      padding: 13px;
      background: var(--accent);
      color: var(--btn-text);
      border: none;
      border-radius: 8px;
      font-size: 1rem;
      font-weight: 700;
      cursor: pointer;
      transition: background 0.2s;
    }
    button:hover { background: var(--accent-h); }
    button:disabled { background: var(--accent-dim); cursor: not-allowed; }

    .output {
      margin-top: 24px;
      background: var(--input-bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 16px;
      font-family: monospace;
      font-size: 0.8rem;
      line-height: 1.8;
      white-space: pre-wrap;
      display: none;
    }
    .output.show    { display: block; }
    .output.success { border-color: #22c55e; }
    .output.error   { border-color: #ef4444; }

    /* ── URL box ── */
    .url-box {
      display: none;
      margin-top: 16px;
      background: var(--badge-bg);
      border: 1px solid #22c55e;
      border-radius: 8px;
      padding: 14px 16px;
    }
    .url-box.show { display: block; }
    .url-label {
      font-size: 0.72rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: #22c55e;
      margin-bottom: 8px;
    }
    .url-row {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .url-link {
      flex: 1;
      font-family: monospace;
      font-size: 0.78rem;
      color: var(--badge-col);
      word-break: break-all;
      text-decoration: none;
    }
    .url-link:hover { text-decoration: underline; }
    .copy-btn {
      width: auto;
      padding: 5px 12px;
      font-size: 0.75rem;
      font-weight: 600;
      border-radius: 6px;
      white-space: nowrap;
      flex-shrink: 0;
    }
  </style>
</head>
<body class="theme-light">
<div class="card">

  <a href="{{ url_for('dashboard_bp.dashboard') }}" class="back-link" id="backLink">&#8592; Back to Dashboard</a>

  <!-- Theme switcher -->
  <div class="theme-bar">
    <span>Theme</span>
    <button class="theme-btn"        data-theme="dark"    data-label="Dark"    onclick="setTheme(this)" title=""></button>
    <button class="theme-btn active" data-theme="light"   data-label="Light"   onclick="setTheme(this)" title=""></button>
    <button class="theme-btn"        data-theme="dracula" data-label="Dracula" onclick="setTheme(this)" title=""></button>
    <button class="theme-btn"        data-theme="forest"  data-label="Forest"  onclick="setTheme(this)" title=""></button>
    <button class="theme-btn"        data-theme="ocean"   data-label="Ocean"   onclick="setTheme(this)" title=""></button>
    <button class="theme-btn"        data-theme="sunset"  data-label="Sunset"  onclick="setTheme(this)" title=""></button>
  </div>

  <h1>🖼️ Image Uploader</h1>
  <p class="subtitle">Drop an image — it gets saved and served instantly.</p>
  <div class="repo-badge">🌐 {{ base_url }}/uploads/</div>

  <label>Image</label>
  <div class="drop-zone" id="dropZone">
    <input type="file" id="fileInput" accept="image/*" onchange="previewFile(this)" />
    <div class="drop-icon">☁️</div>
    <div class="drop-text">Drag & drop, <span>browse</span>, or <span>Ctrl+V</span></div>
    <div class="drop-text" style="font-size:0.75rem;margin-top:6px;">PNG · JPG · JPEG · WEBP · GIF</div>
  </div>

  <div class="file-preview" id="filePreview">
    <img id="previewImg" src="" alt="preview" />
    <div>
      <div class="file-name" id="fileName"></div>
      <div class="file-size" id="fileSize"></div>
    </div>
  </div>

  <button id="btn" onclick="uploadImage()">🚀 Upload Image</button>
  <div class="output" id="output"></div>

  <!-- URL box (shown only on success) -->
  <div class="url-box" id="urlBox">
    <div class="url-label">🔗 Your image is available at</div>
    <div class="url-row">
      <a id="rawUrl" class="url-link" href="#" target="_blank"></a>
      <button class="copy-btn" onclick="copyUrl()">📋 Copy</button>
    </div>
  </div>

</div>

<script>
  /* ── Theme switcher ── */
  function setTheme(btn) {
    document.body.className = 'theme-' + btn.dataset.theme;
    document.querySelectorAll('.theme-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    localStorage.setItem('img-uploader-theme', btn.dataset.theme);
  }
  const saved = localStorage.getItem('img-uploader-theme');
  if (saved) {
    const btn = document.querySelector('[data-theme="' + saved + '"]');
    if (btn) setTheme(btn);
  }

  /* ── Drag & drop ── */
  const dropZone = document.getElementById('dropZone');
  dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('dragover'); });
  dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
  dropZone.addEventListener('drop', e => {
    e.preventDefault(); dropZone.classList.remove('dragover');
    if (e.dataTransfer.files[0]) {
      document.getElementById('fileInput').files = e.dataTransfer.files;
      previewFile(document.getElementById('fileInput'));
    }
  });

  function previewFile(input) {
    const file = input.files[0];
    if (!file) return;
    document.getElementById('filePreview').style.display = 'flex';
    document.getElementById('fileName').textContent = file.name;
    document.getElementById('fileSize').textContent = (file.size / 1024).toFixed(1) + ' KB';
    const reader = new FileReader();
    reader.onload = e => document.getElementById('previewImg').src = e.target.result;
    reader.readAsDataURL(file);
  }

  /* ── Copy URL ── */
  function copyUrl() {
    const url = document.getElementById('rawUrl').textContent;
    navigator.clipboard.writeText(url).then(() => {
      const btn = document.querySelector('.copy-btn');
      btn.textContent = '✅ Copied!';
      setTimeout(() => btn.textContent = '📋 Copy', 2000);
    });
  }

  /* ── Clipboard paste ── */
  document.addEventListener('paste', function(e) {
    const items = e.clipboardData && e.clipboardData.items;
    if (!items) return;
    for (let i = 0; i < items.length; i++) {
      if (items[i].type.startsWith('image/')) {
        const file = items[i].getAsFile();
        if (!file) continue;
        const dt = new DataTransfer();
        dt.items.add(file);
        const input = document.getElementById('fileInput');
        input.files = dt.files;
        previewFile(input);
        dropZone.classList.add('dragover');
        setTimeout(() => dropZone.classList.remove('dragover'), 300);
        break;
      }
    }
  });

  /* ── Upload ── */
  async function uploadImage() {
    const fileInput = document.getElementById('fileInput');
    const file = fileInput.files[0];
    if (!file) { alert('Please select an image first.'); return; }

    const btn    = document.getElementById('btn');
    const out    = document.getElementById('output');
    const urlBox = document.getElementById('urlBox');

    btn.disabled = true;
    urlBox.classList.remove('show');
    out.className = 'output show';
    out.classList.remove('success', 'error');
    out.textContent = '⏳ Saving image...\\n';

    const formData = new FormData();
    formData.append('image', file);

    try {
      const res  = await fetch('{{ url_for("upload_image_bp.push") }}', { method: 'POST', body: formData });
      const text = await res.text();
      let data;
      try {
        data = JSON.parse(text);
      } catch (err) {
        throw new Error(`Server error (${res.status}): ${text.substring(0, 60)}...`);
      }

      out.textContent = '';
      for (const step of data.steps) {
        out.textContent += step.icon + '  ' + step.name + '\\n';
        if (step.output)
          out.textContent += '    ' + step.output.trim().replace(/\\n/g, '\\n    ') + '\\n';
        out.textContent += '\\n';
      }

      out.classList.add(data.success ? 'success' : 'error');
      out.textContent += data.success
        ? '✅ Done! Image saved and ready.'
        : '❌ Something went wrong. See details above.';

      if (data.success && data.raw_url) {
        const anchor = document.getElementById('rawUrl');
        anchor.href        = data.raw_url;
        anchor.textContent = data.raw_url;
        urlBox.classList.add('show');
      }

    } catch (e) {
      out.textContent = '❌ Request failed: ' + e.message;
      out.classList.add('error');
    }
    btn.disabled = false;
  }
</script>
</body>
</html>
"""


@upload_image_bp.route('/')
def index():
    return render_template_string(HTML, base_url=PUBLIC_BASE_URL)


@upload_image_bp.route('/push', methods=['POST'])
def push():
    image = request.files.get('image')

    if not image or not image.filename:
        return jsonify({'success': False,
                        'steps': [{'icon': '❌', 'name': 'Upload', 'output': 'No image received.'}]})

    steps = []

    # Sanitise the original filename
    original_name = secure_filename(image.filename)
    if not original_name:
        return jsonify({'success': False,
                        'steps': [{'icon': '❌', 'name': 'Validate', 'output': 'Invalid filename.'}]})

    ext = original_name.rsplit('.', 1)[-1].lower() if '.' in original_name else ''
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({'success': False,
                        'steps': [{'icon': '❌', 'name': 'Validate',
                                   'output': f'File type .{ext} not allowed. Accepted: {", ".join(sorted(ALLOWED_EXTENSIONS))}.'}]})

    # Unique filename — UUID prefix prevents any collision
    unique_filename = f"{uuid.uuid4().hex[:12]}_{original_name}"
    save_path = os.path.join(UPLOAD_DIR, unique_filename)

    try:
        image.save(save_path)
        steps.append({'icon': '✅', 'name': f'Saved  →  {unique_filename}', 'output': ''})
    except Exception as e:
        return jsonify({'success': False,
                        'steps': [{'icon': '❌', 'name': 'Save image', 'output': str(e)}]})

    # Run expiry cleanup on every upload (lightweight, O(n) files in dir)
    deleted = cleanup_old_images()
    if deleted > 0:
        steps.append({'icon': '🧹', 'name': f'Expired {deleted} image(s) older than 150 days', 'output': ''})

    public_url = f"{PUBLIC_BASE_URL}/uploads/{unique_filename}"
    steps.append({'icon': '🔗', 'name': 'Public URL ready', 'output': public_url})

    return jsonify({'success': True, 'steps': steps, 'raw_url': public_url})


if __name__ == '__main__':
    from flask import Flask
    test_app = Flask(__name__)
    test_app.register_blueprint(upload_image_bp)
    test_app.run(debug=True, port=5000)
