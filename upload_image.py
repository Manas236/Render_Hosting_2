from flask import Blueprint, request, jsonify, render_template_string
import subprocess
import os
from dotenv import load_dotenv

load_dotenv()
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

upload_image_bp = Blueprint('upload_image_bp', __name__)

# Save images locally relative to the app so they can be pushed to the same repository
REPO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploaded_images")
os.makedirs(REPO_PATH, exist_ok=True)

HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Git Image Pusher</title>
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

    input[type="text"] {
      width: 100%;
      padding: 10px 14px;
      background: var(--input-bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      color: var(--text);
      font-size: 0.9rem;
      margin-bottom: 8px;
      outline: none;
      transition: border-color 0.2s;
    }
    input[type="text"]:focus { border-color: var(--accent); }
    .hint { font-size: 0.75rem; color: var(--subtext); margin-bottom: 22px; }

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

    /* ── Raw URL box ── */
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

  <h1>🖼️ Git Image Pusher</h1>
  <p class="subtitle">Drop an image — it gets saved and pushed automatically.</p>
  <div class="repo-badge">📁 {{ repo_path }}</div>

  <label>Image</label>
  <div class="drop-zone" id="dropZone">
    <input type="file" id="fileInput" accept="image/*" onchange="previewFile(this)" />
    <div class="drop-icon">☁️</div>
    <div class="drop-text">Drag & drop or <span>browse</span></div>
    <div class="drop-text" style="font-size:0.75rem;margin-top:6px;">PNG · JPG · JPEG · WEBP · GIF</div>
  </div>

  <div class="file-preview" id="filePreview">
    <img id="previewImg" src="" alt="preview" />
    <div>
      <div class="file-name" id="fileName"></div>
      <div class="file-size" id="fileSize"></div>
    </div>
  </div>

  <label>Commit Message</label>
  <input type="text" id="commitMsg" placeholder="Leave blank to auto-number (1st commit, 2nd…)" />
  <p class="hint">✨ Leave blank and it will auto-increment: 1st commit, 2nd commit, 3rd commit…</p>

  <button id="btn" onclick="pushImage()">🚀 Save & Push to GitHub</button>
  <div class="output" id="output"></div>

  <!-- Raw URL box (shown only on success) -->
  <div class="url-box" id="urlBox">
    <div class="url-label">🔗 Your image is saved at</div>
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
    localStorage.setItem('git-pusher-theme', btn.dataset.theme);
  }
  const saved = localStorage.getItem('git-pusher-theme');
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

  /* ── Push ── */
  async function pushImage() {
    const fileInput = document.getElementById('fileInput');
    const file = fileInput.files[0];
    if (!file) { alert('Please select an image first.'); return; }

    const commitMsg = document.getElementById('commitMsg').value.trim();
    const btn    = document.getElementById('btn');
    const out    = document.getElementById('output');
    const urlBox = document.getElementById('urlBox');

    btn.disabled = true;
    urlBox.classList.remove('show');
    out.className = 'output show';
    out.classList.remove('success', 'error');
    out.textContent = '⏳ Saving image and running git commands...\\n';

    const formData = new FormData();
    formData.append('image', file);
    formData.append('commit_msg', commitMsg);

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
        ? '✅ Done! Image pushed to GitHub.'
        : '❌ Something went wrong. See details above.';

      /* ── Show raw URL box on success ── */
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


def run_cmd(cmd):
    result = subprocess.run(
        cmd, cwd=REPO_PATH,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, shell=True
    )
    return (result.stdout + result.stderr).strip(), result.returncode


def ordinal(n):
    suffix = "th" if 11 <= (n % 100) <= 13 else {1:"st",2:"nd",3:"rd"}.get(n % 10, "th")
    return f"{n}{suffix} commit"


def get_next_commit_label():
    output, _ = run_cmd("git rev-list --count HEAD")
    try:
        return ordinal(int(output.strip()) + 1)
    except ValueError:
        return ordinal(1)


@upload_image_bp.route('/')
def index():
    return render_template_string(HTML, repo_path=REPO_PATH)


@upload_image_bp.route('/push', methods=['POST'])
def push():
    image      = request.files.get('image')
    commit_msg = request.form.get('commit_msg', '').strip()

    if not image:
        return jsonify({'success': False,
                        'steps': [{'icon': '❌', 'name': 'Upload', 'output': 'No image received.'}]})

    steps = []

    # Save image
    save_path = os.path.join(REPO_PATH, image.filename)
    try:
        image.save(save_path)
        steps.append({'icon': '✅', 'name': f'Saved  →  {image.filename}', 'output': ''})
    except Exception as e:
        return jsonify({'success': False,
                        'steps': [{'icon': '❌', 'name': 'Save image', 'output': str(e)}]})

    if not commit_msg:
        commit_msg = get_next_commit_label()

    # Render environments often lack the 'origin' remote and run in a detached HEAD state.
    # We construct the URL directly and sync via rebase before pushing HEAD to main.
    auth_url = f"https://{GITHUB_TOKEN}@github.com/Manas236/Render_Hosting_2.git" if GITHUB_TOKEN else "https://github.com/Manas236/Render_Hosting_2.git"

    commands = [
        ('git add .',                     'git add .'),
        (f'git commit -m "{commit_msg}"', f'git -c user.name="Newsband Image Pusher" -c user.email="bot@newsband.app" commit --allow-empty -m "{commit_msg}"'),
        ('git pull (sync with remote)',   f'git -c user.name="Newsband Image Pusher" -c user.email="bot@newsband.app" pull --rebase {auth_url} main'),
        ('git push to repository',        f'git push {auth_url} HEAD:main'),
    ]

    success = True
    for label, cmd in commands:
        output, code = run_cmd(cmd)
        if GITHUB_TOKEN:
            output = output.replace(GITHUB_TOKEN, "***")
        ok = (code == 0)
        steps.append({'icon': '✅' if ok else '❌', 'name': label, 'output': output})
        if not ok:
            success = False
            break

    # Build raw GitHub URL (URL-encode spaces just in case)
    encoded_filename = image.filename.replace(' ', '%20')
    raw_url = (
        f"https://raw.githubusercontent.com/Manas236/Render_Hosting_2/main/uploaded_images/{encoded_filename}"
        if success else None
    )

    return jsonify({'success': success, 'steps': steps, 'raw_url': raw_url})


if __name__ == '__main__':
    from flask import Flask
    test_app = Flask(__name__)
    test_app.register_blueprint(upload_image_bp)
    test_app.run(debug=True, port=5000)