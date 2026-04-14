from flask import Blueprint, request, redirect, url_for, session, render_template_string
import config

login_bp = Blueprint('login_bp', __name__)

LOGIN_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Newsband — Login</title>
  <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,700;0,900;1,700&family=IBM+Plex+Mono:wght@400;500&family=Source+Sans+3:wght@300;400;600&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    :root { --ink: #0a0a0a; --paper: #f4f0e8; --accent: #c8102e; --mid: #5a5247; --rule: #1a1a1a; --faint: #e0dbd0; }
    body { background-color: var(--paper); background-image: repeating-linear-gradient(0deg, transparent, transparent 27px, var(--faint) 27px, var(--faint) 28px); min-height: 100vh; display: flex; align-items: center; justify-content: center; font-family: 'Source Sans 3', sans-serif; }
    .page-wrap { width: 100%; max-width: 480px; padding: 24px; }
    .masthead { text-align: center; border-top: 4px solid var(--rule); border-bottom: 1px solid var(--rule); padding: 14px 0 12px; margin-bottom: 6px; position: relative; }
    .masthead::before { content: ''; display: block; height: 2px; background: var(--accent); margin-bottom: 12px; }
    .masthead-logo { max-width: 260px; max-height: 80px; width: auto; height: auto; object-fit: contain; display: block; margin: 0 auto; }
    .masthead-tagline { font-family: 'IBM Plex Mono', monospace; font-size: 0.62rem; letter-spacing: 0.18em; color: var(--mid); text-transform: uppercase; margin-top: 10px; }
    .dateline { font-family: 'IBM Plex Mono', monospace; font-size: 0.6rem; color: var(--mid); text-align: center; padding: 4px 0; border-bottom: 1px solid var(--rule); margin-bottom: 32px; letter-spacing: 0.08em; }
    .card { background: #fff; border: 1px solid #c8c2b5; padding: 36px 40px 40px; box-shadow: 4px 4px 0 var(--ink); animation: slideUp 0.5s cubic-bezier(0.22, 1, 0.36, 1) both; }
    @keyframes slideUp { from { opacity: 0; transform: translateY(20px); } to   { opacity: 1; transform: translateY(0); } }
    .card-headline { font-family: 'Playfair Display', serif; font-size: 1.45rem; font-weight: 700; color: var(--ink); margin-bottom: 4px; line-height: 1.2; }
    .card-sub { font-size: 0.82rem; color: var(--mid); margin-bottom: 28px; font-weight: 300; }
    .rule-divider { display: flex; align-items: center; gap: 10px; margin-bottom: 24px; }
    .rule-divider span { flex: 1; height: 1px; background: var(--faint); }
    .rule-divider em { font-family: 'IBM Plex Mono', monospace; font-size: 0.6rem; color: #aaa; font-style: normal; letter-spacing: 0.1em; white-space: nowrap; }
    .login-field { margin-bottom: 20px; }
    .login-field label { display: block; font-family: 'IBM Plex Mono', monospace; font-size: 0.65rem; letter-spacing: 0.14em; text-transform: uppercase; color: var(--mid); margin-bottom: 7px; }
    input[type="text"], input[type="password"] { width: 100%; padding: 11px 14px; border: 1px solid #c8c2b5; border-bottom: 2px solid var(--ink); background: var(--paper); font-family: 'IBM Plex Mono', monospace; font-size: 0.92rem; color: var(--ink); outline: none; transition: border-color 0.2s, background 0.2s; }
    input[type="text"]:focus, input[type="password"]:focus { background: #fff; border-color: var(--accent); border-bottom-color: var(--accent); }
    .error-banner { background: var(--accent); color: #fff; font-family: 'IBM Plex Mono', monospace; font-size: 0.72rem; letter-spacing: 0.06em; padding: 10px 14px; margin-bottom: 20px; display: flex; align-items: center; gap: 8px; animation: shake 0.4s cubic-bezier(0.36, 0.07, 0.19, 0.97); }
    @keyframes shake { 0%, 100% { transform: translateX(0); } 20% { transform: translateX(-6px); } 40% { transform: translateX(6px); } 60% { transform: translateX(-4px); } 80% { transform: translateX(4px); } }
    .error-banner::before { content: '⚠'; font-size: 0.9rem; }
    button[type="submit"] { width: 100%; padding: 13px; background: var(--ink); color: var(--paper); border: none; font-family: 'IBM Plex Mono', monospace; font-size: 0.8rem; letter-spacing: 0.18em; text-transform: uppercase; cursor: pointer; margin-top: 8px; position: relative; transition: background 0.15s, box-shadow 0.15s; box-shadow: 3px 3px 0 var(--accent); }
    button[type="submit"]:hover { background: var(--accent); box-shadow: 3px 3px 0 var(--ink); }
    button[type="submit"]:active { transform: translate(2px, 2px); box-shadow: 1px 1px 0 var(--ink); }
    .footer-note { font-family: 'IBM Plex Mono', monospace; font-size: 0.58rem; color: #aaa; text-align: center; margin-top: 28px; letter-spacing: 0.08em; }
  </style>
</head>
<body>
  <div class="page-wrap">
    <div class="masthead">
      <img src="{{ logo_url }}" alt="Newsband" class="masthead-logo" />
      <div class="masthead-tagline">Editorial Intelligence Platform</div>
    </div>
    <div class="dateline">SECURE ACCESS PORTAL</div>
    <div class="card">
      <div class="card-headline">Press Credentials Required</div>
      <div class="card-sub">Sign in with your journalist access credentials.</div>
      <div class="rule-divider"><span></span><em>AUTHORIZED PERSONNEL ONLY</em><span></span></div>
      {% if error %}
      <div class="error-banner">Access denied — check your credentials and try again.</div>
      {% endif %}
      <form method="POST" action="{{ url_for('login_bp.login') }}">
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

@login_bp.route('/', methods=['GET', 'POST'])
def login():
    """Login page — entry point."""
    if session.get('logged_in'):
        return redirect(url_for('dashboard_bp.dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        if username == config.VALID_USERNAME and password == config.VALID_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('dashboard_bp.dashboard'))
        return render_template_string(LOGIN_HTML, error=True, logo_url=config.LOGO_URL)
    return render_template_string(LOGIN_HTML, error=False, logo_url=config.LOGO_URL)

@login_bp.route('/logout')
def logout():
    """Clear session and redirect to login."""
    session.clear()
    return redirect(url_for('login_bp.login'))
