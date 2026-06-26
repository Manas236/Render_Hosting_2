from flask import Blueprint, render_template_string
from helpers import require_login
import config

schedule_mailchimp_bp = Blueprint('schedule_mailchimp_bp', __name__)


@schedule_mailchimp_bp.route('/')
@require_login
def index():
    """Schedule Mailchimp Newsletter — work-in-progress placeholder page."""
    return render_template_string(SCHEDULE_MAILCHIMP_HTML, logo_url=config.LOGO_URL)


SCHEDULE_MAILCHIMP_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Schedule Mailchimp Newsletter — Newsband</title>
  <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,700;0,900;1,700&family=IBM+Plex+Mono:wght@400;500;600&family=Source+Sans+3:wght@300;400;600&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    :root {
      --ink: #0a0a0a; --paper: #f4f0e8; --accent: #c8102e; --mid: #5a5247;
      --rule: #1a1a1a; --faint: #e0dbd0;
      --mc: #ffe01b; --mc-dark: #1a1a1a; --amber: #92400e; --amber-bg: #fef3c7;
    }
    html, body { height: 100%; }
    body {
      background-color: var(--paper);
      background-image: repeating-linear-gradient(0deg, transparent, transparent 27px, var(--faint) 27px, var(--faint) 28px);
      min-height: 100vh; display: flex; align-items: center; justify-content: center;
      font-family: 'Source Sans 3', sans-serif; color: var(--ink); overflow-x: hidden;
    }
    .page-wrap { width: 100%; max-width: 620px; padding: 24px; }

    /* ── Masthead ── */
    .masthead { text-align: center; border-top: 4px solid var(--rule); border-bottom: 1px solid var(--rule); padding: 14px 0 12px; margin-bottom: 6px; }
    .masthead::before { content: ''; display: block; height: 2px; background: var(--accent); margin-bottom: 12px; }
    .masthead-logo { max-width: 240px; max-height: 70px; display: block; margin: 0 auto; }
    .masthead-tagline { font-family: 'IBM Plex Mono', monospace; font-size: 0.62rem; letter-spacing: 0.18em; color: var(--mid); text-transform: uppercase; margin-top: 10px; }
    .dateline {
      font-family: 'IBM Plex Mono', monospace; font-size: 0.6rem; color: var(--mid);
      padding: 4px 0; border-bottom: 1px solid var(--rule); margin-bottom: 28px;
      letter-spacing: 0.08em; display: flex; justify-content: space-between; align-items: center;
    }
    .dateline a { color: var(--accent); text-decoration: none; font-weight: 600; letter-spacing: 0.1em; }
    .dateline a:hover { text-decoration: underline; }

    /* ── Card shell ── */
    .card {
      position: relative; background: #fff; border: 1px solid #c8c2b5;
      padding: 0; box-shadow: 6px 6px 0 var(--ink); overflow: hidden;
      animation: slideUp 0.55s cubic-bezier(0.22, 1, 0.36, 1) both;
    }
    @keyframes slideUp { from { opacity: 0; transform: translateY(22px); } to { opacity: 1; transform: translateY(0); } }

    /* ── Diagonal "under construction" hazard strip ── */
    .hazard {
      height: 12px;
      background: repeating-linear-gradient(45deg, var(--mc) 0 16px, var(--mc-dark) 16px 32px);
      background-size: 45px 45px;
      animation: hazard-roll 1.4s linear infinite;
    }
    @keyframes hazard-roll { from { background-position: 0 0; } to { background-position: 45px 0; } }

    .card-body { padding: 40px 44px 46px; text-align: center; }

    /* ── Animated build icon ── */
    .build-icon {
      position: relative; width: 96px; height: 96px; margin: 4px auto 26px;
      display: flex; align-items: center; justify-content: center;
    }
    .build-icon .gear {
      position: absolute; font-size: 3.6rem; line-height: 1;
      filter: drop-shadow(2px 2px 0 var(--faint));
    }
    .build-icon .gear-main { animation: spin 6s linear infinite; }
    .build-icon .gear-sm {
      font-size: 1.9rem; top: -6px; right: -10px;
      animation: spin-rev 4s linear infinite;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
    @keyframes spin-rev { to { transform: rotate(-360deg); } }

    /* ── Status pill ── */
    .status-pill {
      display: inline-flex; align-items: center; gap: 8px;
      font-family: 'IBM Plex Mono', monospace; font-size: 0.64rem; font-weight: 600;
      letter-spacing: 0.14em; text-transform: uppercase;
      padding: 6px 14px; margin-bottom: 22px;
      color: var(--amber); background: var(--amber-bg); border: 1px solid #f59e0b;
    }
    .status-pill .blink { width: 8px; height: 8px; border-radius: 50%; background: #f59e0b; animation: blink 1.2s ease-in-out infinite; }
    @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.25; } }

    .headline {
      font-family: 'Playfair Display', serif; font-weight: 900;
      font-size: 2rem; line-height: 1.12; color: var(--ink); margin-bottom: 12px;
    }
    .headline .accent { color: var(--accent); font-style: italic; }
    .subhead {
      font-size: 0.92rem; color: var(--mid); line-height: 1.6; font-weight: 300;
      max-width: 420px; margin: 0 auto 30px;
    }
    .subhead strong { font-weight: 600; color: var(--ink); }

    /* ── Faux progress bar ── */
    .progress-wrap { margin: 0 auto 8px; max-width: 380px; text-align: left; }
    .progress-label {
      display: flex; justify-content: space-between; align-items: baseline;
      font-family: 'IBM Plex Mono', monospace; font-size: 0.58rem;
      letter-spacing: 0.1em; text-transform: uppercase; color: var(--mid); margin-bottom: 7px;
    }
    .progress-track { height: 14px; border: 1px solid var(--rule); background: var(--paper); padding: 2px; }
    .progress-fill {
      height: 100%; width: 0;
      background: repeating-linear-gradient(45deg, var(--accent) 0 8px, #a50d26 8px 16px);
      background-size: 22px 22px;
      animation: fill-up 2.2s cubic-bezier(0.22, 1, 0.36, 1) 0.4s forwards, stripe-move 0.8s linear infinite;
    }
    @keyframes fill-up { to { width: 42%; } }
    @keyframes stripe-move { from { background-position: 0 0; } to { background-position: 22px 0; } }

    /* ── Build checklist ── */
    .rule-divider { display: flex; align-items: center; gap: 10px; margin: 34px 0 20px; }
    .rule-divider span { flex: 1; height: 1px; background: var(--faint); }
    .rule-divider em { font-family: 'IBM Plex Mono', monospace; font-size: 0.58rem; color: #aaa; font-style: normal; letter-spacing: 0.12em; white-space: nowrap; text-transform: uppercase; }

    .checklist { list-style: none; text-align: left; max-width: 400px; margin: 0 auto; }
    .checklist li {
      display: flex; align-items: flex-start; gap: 12px;
      font-family: 'IBM Plex Mono', monospace; font-size: 0.72rem; color: var(--mid);
      padding: 9px 0; border-bottom: 1px dashed var(--faint); line-height: 1.45;
    }
    .checklist li:last-child { border-bottom: none; }
    .checklist .mark { flex-shrink: 0; width: 16px; text-align: center; font-weight: 600; }
    .checklist .done .mark { color: #1a7a3c; }
    .checklist .done { color: var(--ink); }
    .checklist .wip .mark { color: var(--amber); animation: blink 1.4s ease-in-out infinite; }
    .checklist .todo { opacity: 0.6; }
    .checklist .todo .mark { color: #aaa; }

    /* ── Footer note + back button ── */
    .actions { margin-top: 34px; }
    .back-btn {
      display: inline-flex; align-items: center; gap: 8px; text-decoration: none;
      font-family: 'IBM Plex Mono', monospace; font-size: 0.7rem; font-weight: 600;
      letter-spacing: 0.08em; text-transform: uppercase;
      color: var(--ink); background: var(--paper); border: 1px solid var(--ink);
      padding: 11px 22px; box-shadow: 3px 3px 0 var(--faint); transition: all 0.15s;
    }
    .back-btn:hover { background: var(--ink); color: #fff; box-shadow: 4px 4px 0 var(--accent); transform: translate(-1px, -1px); }
    .back-btn:active { transform: translate(2px, 2px); box-shadow: 1px 1px 0 var(--accent); }

    .footer-note { font-family: 'IBM Plex Mono', monospace; font-size: 0.58rem; color: #aaa; text-align: center; margin-top: 26px; letter-spacing: 0.08em; }
  </style>
</head>
<body>
  <div class="page-wrap">
    <div class="masthead">
      <img src="{{ logo_url }}" alt="Newsband" class="masthead-logo" />
      <div class="masthead-tagline">Automated Campaign Scheduling</div>
    </div>
    <div class="dateline">
      <span>BUILD &amp; DEPLOYMENT PIPELINE</span>
      <a href="{{ url_for('dashboard_bp.dashboard') }}">&#8592; DASHBOARD</a>
    </div>

    <div class="card">
      <div class="hazard"></div>
      <div class="card-body">
        <div class="build-icon">
          <span class="gear gear-main">⚙️</span>
          <span class="gear gear-sm">⚙️</span>
        </div>

        <div class="status-pill"><span class="blink"></span>Under Construction</div>

        <h1 class="headline">Schedule <span class="accent">Mailchimp</span><br>Newsletter</h1>
        <p class="subhead">
          A one-click scheduler to queue your finished newsletter straight into
          <strong>Mailchimp</strong> — pick a send date, choose an audience, and let it fly.
          This feature is currently <strong>in development</strong>.
        </p>

        <div class="progress-wrap">
          <div class="progress-label"><span>Development Progress</span><span>≈ 42%</span></div>
          <div class="progress-track"><div class="progress-fill"></div></div>
        </div>

        <div class="rule-divider"><span></span><em>Build Checklist</em><span></span></div>
        <ul class="checklist">
          <li class="done"><span class="mark">✔</span><span>Connect Mailchimp API &amp; authenticate account</span></li>
          <li class="done"><span class="mark">✔</span><span>Pull audiences &amp; saved segments</span></li>
          <li class="wip"><span class="mark">▸</span><span>Date &amp; time picker with timezone handling</span></li>
          <li class="todo"><span class="mark">○</span><span>Template preview &amp; subject-line editor</span></li>
          <li class="todo"><span class="mark">○</span><span>Confirm &amp; schedule send</span></li>
        </ul>

        <div class="actions">
          <a href="{{ url_for('dashboard_bp.dashboard') }}" class="back-btn">&#8592; Back to Dashboard</a>
        </div>
      </div>
      <div class="hazard"></div>
    </div>

    <div class="footer-note">NEWSBAND JOURNALISM PLATFORM &nbsp;&middot;&nbsp; FEATURE IN DEVELOPMENT</div>
  </div>
</body>
</html>"""
