from flask import Blueprint, render_template_string, url_for
import config
from helpers import require_login

dashboard_bp = Blueprint('dashboard_bp', __name__)

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Newsband — Dashboard</title>
  <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,700;0,900;1,700&family=IBM+Plex+Mono:wght@400;500&family=Source+Sans+3:wght@300;400;600&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    :root { --ink: #0a0a0a; --paper: #f4f0e8; --accent: #c8102e; --mid: #5a5247; --rule: #1a1a1a; --faint: #e0dbd0; }
    body { background-color: var(--paper); background-image: repeating-linear-gradient(0deg, transparent, transparent 27px, var(--faint) 27px, var(--faint) 28px); min-height: 100vh; display: flex; align-items: center; justify-content: center; font-family: 'Source Sans 3', sans-serif; }
    .page-wrap { width: 100%; max-width: 580px; padding: 24px; }
    .masthead { text-align: center; border-top: 4px solid var(--rule); border-bottom: 1px solid var(--rule); padding: 14px 0 12px; margin-bottom: 6px; position: relative; }
    .masthead::before { content: ''; display: block; height: 2px; background: var(--accent); margin-bottom: 12px; }
    .masthead-logo { max-width: 260px; max-height: 80px; width: auto; height: auto; object-fit: contain; display: block; margin: 0 auto; }
    .masthead-tagline { font-family: 'IBM Plex Mono', monospace; font-size: 0.62rem; letter-spacing: 0.18em; color: var(--mid); text-transform: uppercase; margin-top: 10px; }
    .dateline { font-family: 'IBM Plex Mono', monospace; font-size: 0.6rem; color: var(--mid); text-align: center; padding: 4px 0; border-bottom: 1px solid var(--rule); margin-bottom: 32px; letter-spacing: 0.08em; display: flex; justify-content: space-between; align-items: center; }
    .dateline a { color: var(--accent); text-decoration: none; font-weight: 600; letter-spacing: 0.1em; }
    .dateline a:hover { text-decoration: underline; }
    .card { background: #fff; border: 1px solid #c8c2b5; padding: 36px 40px 40px; box-shadow: 4px 4px 0 var(--ink); animation: slideUp 0.5s cubic-bezier(0.22, 1, 0.36, 1) both; }
    @keyframes slideUp { from { opacity: 0; transform: translateY(20px); } to   { opacity: 1; transform: translateY(0); } }
    .card-headline { font-family: 'Playfair Display', serif; font-size: 1.45rem; font-weight: 700; color: var(--ink); margin-bottom: 4px; line-height: 1.2; }
    .card-sub { font-size: 0.82rem; color: var(--mid); margin-bottom: 28px; font-weight: 300; }
    .rule-divider { display: flex; align-items: center; gap: 10px; margin-bottom: 24px; }
    .rule-divider span { flex: 1; height: 1px; background: var(--faint); }
    .rule-divider em { font-family: 'IBM Plex Mono', monospace; font-size: 0.6rem; color: #aaa; font-style: normal; letter-spacing: 0.1em; white-space: nowrap; }
    .dashboard-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    .dash-btn { display: block; text-decoration: none; padding: 24px 20px; background: var(--paper); border: 1px solid #c8c2b5; color: var(--ink); text-align: center; transition: all 0.2s; box-shadow: 3px 3px 0 var(--faint); }
    .dash-btn:hover { background: #fff; border-color: var(--ink); box-shadow: 4px 4px 0 var(--ink); transform: translate(-1px, -1px); }
    .dash-btn:active { transform: translate(2px, 2px); box-shadow: 1px 1px 0 var(--ink); }
    .dash-btn-icon { font-size: 2.2rem; margin-bottom: 12px; display: block; }
    .dash-btn-photo-wrap { width: 100%; height: 260px; background: #e0dbd0; margin-bottom: 16px; border: 1px solid #c8c2b5; overflow: hidden; border-radius: 4px; }
    .dash-btn-photo { width: 100%; height: 100%; object-fit: cover; object-position: top; opacity: 0.9; transition: opacity 0.2s; }
    .dash-btn:hover .dash-btn-photo { opacity: 1; }
    .dash-btn-title { font-family: 'IBM Plex Mono', monospace; font-size: 0.8rem; font-weight: 600; letter-spacing: 0.05em; text-transform: uppercase; margin-bottom: 8px; color: var(--ink); }
    .dash-btn-desc { font-size: 0.72rem; color: var(--mid); line-height: 1.4; font-family: 'Source Sans 3', sans-serif; }
    .footer-note { font-family: 'IBM Plex Mono', monospace; font-size: 0.58rem; color: #aaa; text-align: center; margin-top: 28px; letter-spacing: 0.08em; }
  </style>
</head>
<body>
  <div class="page-wrap">
    <div class="masthead">
      <img src="{{ logo_url }}" alt="Newsband" class="masthead-logo" />
      <div class="masthead-tagline">Editorial Intelligence Platform</div>
    </div>
    <div class="dateline">
      <span>SECURE ACCESS PORTAL</span>
      <a href="{{ url_for('login_bp.logout') }}">LOGOUT ⍈</a>
    </div>
    <div class="card">
      <div class="card-headline">Dashboard</div>
      <div class="card-sub">Select a tool to proceed.</div>
      <div class="rule-divider"><span></span><em>NEWSLETTER EDITORS</em><span></span></div>
      <div class="dashboard-grid">
        <a href="{{ url_for('day11_editor.editor') }}" class="dash-btn">
          <div class="dash-btn-photo-wrap">
            <img src="/static_files/Day11.png" class="dash-btn-photo" alt="Day11 Editor" />
          </div>
          <div class="dash-btn-title">Day 11 Editor</div>
          <div class="dash-btn-desc">Visual editor specifically for Day11.</div>
        </a>
        <a href="{{ url_for('template1_editor.editor') }}" class="dash-btn">
          <div class="dash-btn-photo-wrap">
            <img src="/static_files/template1.png" class="dash-btn-photo" alt="Template1 Editor" />
          </div>
          <div class="dash-btn-title">Template 1 Editor</div>
          <div class="dash-btn-desc">Visual editor for template1.html.</div>
        </a>
        <a href="{{ url_for('day8_v2_editor.editor') }}" class="dash-btn">
          <div class="dash-btn-photo-wrap">
            <img src="/static_files/Day8.png" class="dash-btn-photo" alt="Day8 Editor" />
          </div>
          <div class="dash-btn-title">Day8 Editor</div>
          <div class="dash-btn-desc">Visual editor specifically for Day8.</div>
        </a>
        <a href="{{ url_for('day9_editor.editor') }}" class="dash-btn">
          <div class="dash-btn-photo-wrap">
            <img src="/static_files/Day9.png" class="dash-btn-photo" alt="Day9 Editor" />
          </div>
          <div class="dash-btn-title">Day 9 Editor</div>
          <div class="dash-btn-desc">Visual editor specifically for Day9.</div>
        </a>
      </div>

      <div class="rule-divider" style="margin-top: 36px;"><span></span><em>UTILITY TOOLS</em><span></span></div>
      <div class="dashboard-grid">
        <a href="{{ url_for('codeview_bp.converter') }}" class="dash-btn" style="display: flex; flex-direction: column; justify-content: center; align-items: center;">
          <span class="dash-btn-icon">💻</span>
          <div class="dash-btn-title">Code Viewer</div>
          <div class="dash-btn-desc">Upload and copy raw HTML code.</div>
        </a>
        <a href="{{ url_for('extractor_bp.index') }}" target="_blank" class="dash-btn" style="display: flex; flex-direction: column; justify-content: center; align-items: center;">
          <span class="dash-btn-icon">📰</span>
          <div class="dash-btn-title">News Extractor Analyzer</div>
          <div class="dash-btn-desc">Extract and analyze news content.</div>
        </a>
        <a href="{{ url_for('batch_extractor_bp.index') }}" target="_blank" class="dash-btn" style="display: flex; flex-direction: column; justify-content: center; align-items: center;">
          <span class="dash-btn-icon">⚡</span>
          <div class="dash-btn-title">Batch Extractor</div>
          <div class="dash-btn-desc">Process multiple articles in parallel.</div>
        </a>
      </div>
    </div>
    <div class="footer-note">NEWSBAND JOURNALISM PLATFORM &nbsp;·&nbsp; CONFIDENTIAL</div>
  </div>
</body>
</html>
"""

@dashboard_bp.route('/dashboard')
@require_login
def dashboard():
    """Dashboard page — routes to Editor or Converter."""
    return render_template_string(
        DASHBOARD_HTML, 
        logo_url=config.LOGO_URL
    )
