import logging
from flask import Blueprint, render_template_string, jsonify
from helpers import require_login
from social_utils import get_pipeline_status, reset_social_runtime_state, stop_scheduler
import config

logger = logging.getLogger(__name__)

social_pipeline_bp = Blueprint('social_pipeline_bp', __name__)


@social_pipeline_bp.route('/social-pipeline')
@require_login
def dashboard():
    return render_template_string(SOCIAL_PIPELINE_HTML, logo_url=config.LOGO_URL)


@social_pipeline_bp.route('/api/social/status')
@require_login
def status():
    try:
        return jsonify(get_pipeline_status()), 200
    except Exception as e:
        logger.error('Social pipeline status error: %s', e)
        return jsonify({'error': str(e)}), 500


@social_pipeline_bp.route('/api/social/reset', methods=['POST'])
@require_login
def reset():
    try:
        scheduler_stopped = stop_scheduler()
        if scheduler_stopped:
            logger.info('[social-reset] stopped scheduler before reset')

        result = reset_social_runtime_state()
        logger.info('[social-reset] pipeline reset complete — cleared: %s', result['cleared'])

        return jsonify({
            'success': True,
            'message': 'Pipeline state reset successfully',
            'scheduler_stopped': scheduler_stopped,
            'cleared': result['cleared'],
            'timestamp': result['timestamp'],
        }), 200
    except Exception as e:
        logger.error('[social-reset] reset error: %s', e)
        return jsonify({'success': False, 'error': str(e)}), 500


SOCIAL_PIPELINE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Social Pipeline — Newsband</title>
  <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,700;0,900;1,700&family=IBM+Plex+Mono:wght@400;500&family=Source+Sans+3:wght@300;400;600&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    :root {
      --ink: #0a0a0a; --paper: #f4f0e8; --accent: #c8102e; --mid: #5a5247;
      --rule: #1a1a1a; --faint: #e0dbd0;
      --green: #166534; --green-bg: #dcfce7; --green-dot: #22c55e;
      --amber: #92400e; --amber-bg: #fef3c7; --amber-dot: #f59e0b;
      --red: #991b1b;  --red-bg: #fee2e2;   --red-dot: #ef4444;
      --blue: #1e40af; --blue-bg: #dbeafe;  --blue-dot: #3b82f6;
    }
    body {
      background-color: var(--paper);
      background-image: repeating-linear-gradient(0deg, transparent, transparent 27px, var(--faint) 27px, var(--faint) 28px);
      min-height: 100vh;
      font-family: 'Source Sans 3', sans-serif;
    }
    .page-wrap { width: 100%; max-width: 860px; margin: 0 auto; padding: 24px; }

    /* ── Masthead ── */
    .masthead { text-align: center; border-top: 4px solid var(--rule); border-bottom: 1px solid var(--rule); padding: 14px 0 12px; margin-bottom: 6px; }
    .masthead::before { content: ''; display: block; height: 2px; background: var(--accent); margin-bottom: 12px; }
    .masthead-logo { max-width: 220px; max-height: 60px; display: block; margin: 0 auto; }
    .masthead-tagline { font-family: 'IBM Plex Mono', monospace; font-size: 0.62rem; letter-spacing: 0.18em; color: var(--mid); text-transform: uppercase; margin-top: 10px; }
    .dateline {
      font-family: 'IBM Plex Mono', monospace; font-size: 0.6rem; color: var(--mid);
      padding: 4px 0; border-bottom: 1px solid var(--rule); margin-bottom: 24px;
      letter-spacing: 0.08em; display: flex; justify-content: space-between; align-items: center;
    }
    .dateline a { color: var(--accent); text-decoration: none; font-weight: 600; letter-spacing: 0.1em; }
    .dateline a:hover { text-decoration: underline; }

    /* ── Card shell ── */
    .card { background: #fff; border: 1px solid #c8c2b5; padding: 28px 32px 36px; box-shadow: 4px 4px 0 var(--ink); animation: slideUp 0.4s cubic-bezier(0.22, 1, 0.36, 1) both; }
    @keyframes slideUp { from { opacity: 0; transform: translateY(16px); } to { opacity: 1; transform: translateY(0); } }
    .card-headline { font-family: 'Playfair Display', serif; font-size: 1.4rem; font-weight: 700; color: var(--ink); margin-bottom: 4px; }
    .card-sub { font-size: 0.82rem; color: var(--mid); margin-bottom: 20px; font-weight: 300; }

    /* ── Rule divider ── */
    .rule-divider { display: flex; align-items: center; gap: 10px; margin: 24px 0 18px; }
    .rule-divider span { flex: 1; height: 1px; background: var(--faint); }
    .rule-divider em { font-family: 'IBM Plex Mono', monospace; font-size: 0.6rem; color: #aaa; font-style: normal; letter-spacing: 0.1em; white-space: nowrap; }

    /* ── Banners ── */
    .banner { padding: 10px 16px; font-family: 'IBM Plex Mono', monospace; font-size: 0.72rem; margin-bottom: 16px; border: 1px solid; display: none; }
    .banner.visible { display: flex; align-items: center; gap: 8px; }
    .banner-success { background: var(--green-bg); color: var(--green); border-color: var(--green-dot); }
    .banner-error   { background: var(--red-bg);   color: var(--red);   border-color: var(--red-dot); }

    /* ── Control bar ── */
    .control-bar { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-bottom: 0; }
    .btn {
      font-family: 'IBM Plex Mono', monospace; font-size: 0.72rem; font-weight: 500;
      letter-spacing: 0.06em; padding: 8px 18px; border: 1px solid; cursor: pointer;
      text-transform: uppercase; transition: all 0.15s; background: transparent;
    }
    .btn:disabled { opacity: 0.45; cursor: not-allowed; }
    .btn-refresh { color: var(--ink); border-color: var(--ink); }
    .btn-refresh:hover:not(:disabled) { background: var(--ink); color: #fff; }
    .btn-reset { color: var(--red); border-color: var(--red); }
    .btn-reset:hover:not(:disabled) { background: var(--red); color: #fff; }
    .btn-force { color: var(--amber); border-color: var(--amber); }
    .btn-force:hover:not(:disabled) { background: var(--amber); color: #fff; }
    .last-refresh { font-family: 'IBM Plex Mono', monospace; font-size: 0.6rem; color: var(--mid); margin-left: auto; }

    /* ── Status grid ── */
    .status-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 12px; }
    .sc { border: 1px solid #c8c2b5; padding: 14px 16px; background: var(--paper); }
    .sc-label { font-family: 'IBM Plex Mono', monospace; font-size: 0.58rem; letter-spacing: 0.12em; text-transform: uppercase; color: var(--mid); margin-bottom: 8px; }
    .sc-value { margin-bottom: 6px; }
    .sc-detail { font-size: 0.67rem; color: var(--mid); line-height: 1.45; font-family: 'IBM Plex Mono', monospace; }

    /* ── Status pills ── */
    .pill {
      display: inline-flex; align-items: center; gap: 5px;
      padding: 2px 8px; font-family: 'IBM Plex Mono', monospace;
      font-size: 0.65rem; font-weight: 500;
    }
    .pill-idle    { background: var(--green-bg); color: var(--green); }
    .pill-active  { background: var(--amber-bg); color: var(--amber); }
    .pill-failed  { background: var(--red-bg);   color: var(--red); }
    .pill-waiting { background: var(--blue-bg);  color: var(--blue); }
    .dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
    .dot-green { background: var(--green-dot); }
    .dot-amber { background: var(--amber-dot); }
    .dot-red   { background: var(--red-dot); }
    .dot-blue  { background: var(--blue-dot); }
    @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.35; } }
    .dot-pulse { animation: blink 1.4s ease-in-out infinite; }

    /* ── Loading skeleton ── */
    .sk-row { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 12px; }
    .sk { border: 1px solid #ddd; padding: 14px 16px; background: #f9f8f5; }
    .sk-bar { height: 10px; border-radius: 2px; background: var(--faint); margin-bottom: 8px; }
    .sk-bar.w60 { width: 60%; }
    .sk-bar.w80 { width: 80%; }
    @keyframes shimmer { 0%{opacity:.6} 50%{opacity:1} 100%{opacity:.6} }
    .sk-bar { animation: shimmer 1.5s ease-in-out infinite; }

    /* ── Modal ── */
    .overlay { position: fixed; inset: 0; background: rgba(10,10,10,.55); display: none; align-items: center; justify-content: center; z-index: 200; }
    .overlay.open { display: flex; }
    .modal { background: #fff; border: 2px solid var(--ink); padding: 28px 32px; max-width: 440px; width: 92%; box-shadow: 6px 6px 0 var(--ink); }
    .modal-title { font-family: 'Playfair Display', serif; font-size: 1.05rem; font-weight: 700; color: var(--ink); margin-bottom: 12px; }
    .modal-body { font-size: 0.82rem; color: var(--mid); line-height: 1.65; margin-bottom: 18px; }
    .modal-warn { background: var(--amber-bg); color: var(--amber); border: 1px solid var(--amber-dot); padding: 8px 12px; font-family: 'IBM Plex Mono', monospace; font-size: 0.67rem; line-height: 1.5; margin-bottom: 16px; display: none; }
    .modal-warn.visible { display: block; }
    .modal-actions { display: flex; gap: 10px; justify-content: flex-end; }
    .btn-cancel  { color: var(--mid); border-color: var(--mid); }
    .btn-cancel:hover  { background: var(--mid); color: #fff; }
    .btn-confirm { color: var(--red); border-color: var(--red); }
    .btn-confirm:hover { background: var(--red); color: #fff; }

    .footer-note { font-family: 'IBM Plex Mono', monospace; font-size: 0.58rem; color: #aaa; text-align: center; margin-top: 28px; letter-spacing: 0.08em; }

    /* ── Template send table ── */
    .send-summary { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
    .send-ts { font-family: 'IBM Plex Mono', monospace; font-size: 0.6rem; color: var(--mid); }
    .send-table { display: flex; flex-direction: column; gap: 3px; }
    .send-row {
      display: grid; grid-template-columns: 1fr 90px auto;
      align-items: center; gap: 10px;
      font-family: 'IBM Plex Mono', monospace; font-size: 0.65rem;
      padding: 6px 10px; border: 1px solid var(--faint); background: var(--paper);
    }
    .send-row.send-ok   { border-left: 3px solid var(--green-dot); }
    .send-row.send-fail { border-left: 3px solid var(--red-dot); background: var(--red-bg); }
    .send-ep { color: var(--ink); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .send-reason { font-size: 0.6rem; color: var(--red); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .send-never { font-family: 'IBM Plex Mono', monospace; font-size: 0.72rem; color: var(--mid); padding: 12px 0; }
  </style>
</head>
<body>
<div class="page-wrap">

  <div class="masthead">
    <img src="{{ logo_url }}" alt="Newsband" class="masthead-logo" />
    <div class="masthead-tagline">Social Pipeline Control</div>
  </div>
  <div class="dateline">
    <span>ORCHESTRATION DASHBOARD</span>
    <a href="{{ url_for('dashboard_bp.dashboard') }}">&#8592; DASHBOARD</a>
  </div>

  <div class="card">
    <div class="card-headline">Social Pipeline</div>
    <div class="card-sub">Runtime orchestration state monitor &amp; control panel.</div>

    <div id="banner-success" class="banner banner-success">&#10003;&nbsp; Pipeline state reset successfully</div>
    <div id="banner-error"   class="banner banner-error"></div>

    <div class="control-bar">
      <button class="btn btn-refresh" id="btn-refresh" onclick="loadStatus()">Refresh</button>
      <button class="btn btn-reset"   id="btn-reset"   onclick="openModal()">Reset Pipeline</button>
      <span class="last-refresh" id="last-refresh"></span>
    </div>

    <div class="rule-divider"><span></span><em>PIPELINE STATUS</em><span></span></div>

    <div id="status-area">
      <div class="sk-row">
        <div class="sk"><div class="sk-bar w60"></div><div class="sk-bar w80"></div></div>
        <div class="sk"><div class="sk-bar w60"></div><div class="sk-bar w80"></div></div>
        <div class="sk"><div class="sk-bar w60"></div><div class="sk-bar w80"></div></div>
        <div class="sk"><div class="sk-bar w60"></div><div class="sk-bar w80"></div></div>
        <div class="sk"><div class="sk-bar w60"></div><div class="sk-bar w80"></div></div>
        <div class="sk"><div class="sk-bar w60"></div><div class="sk-bar w80"></div></div>
        <div class="sk"><div class="sk-bar w60"></div><div class="sk-bar w80"></div></div>
        <div class="sk"><div class="sk-bar w60"></div><div class="sk-bar w80"></div></div>
      </div>
    </div>

    <div class="rule-divider"><span></span><em>TEMPLATE SEND</em><span></span></div>
    <div id="send-detail-area"><div class="send-never">Loading…</div></div>
  </div>

  <div class="footer-note">NEWSBAND JOURNALISM PLATFORM &nbsp;&middot;&nbsp; SOCIAL PIPELINE</div>
</div>

<!-- ── Reset confirmation modal ── -->
<div class="overlay" id="overlay">
  <div class="modal">
    <div class="modal-title">Reset Social Pipeline Runtime State?</div>
    <div class="modal-body">
      This will clear all transient orchestration state and leave the pipeline
      <strong>idle and safe to rerun</strong>.<br><br>
      Content, approved posts, captions, generated images, payload archives,
      and post history will <strong>not</strong> be affected.
    </div>
    <div class="modal-warn" id="modal-warn">
      Warning: pipeline is actively publishing. Force-resetting may interrupt
      in-flight operations. Proceed only if you intend to abort the current run.
    </div>
    <div class="modal-actions">
      <button class="btn btn-cancel"  onclick="closeModal()">Cancel</button>
      <button class="btn btn-confirm" id="btn-confirm" onclick="confirmReset()">Confirm Reset</button>
    </div>
  </div>
</div>

<script>
(function () {
  var lastStatus = null;
  var secondsAgo = 0;
  var tickTimer = null;
  var pollTimer = null;

  /* ─ helpers ─ */
  function esc(s) {
    if (s == null) return '';
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }
  function shortTime(s) {
    if (!s) return '—';
    try { return new Date(s).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit', second:'2-digit'}); }
    catch (e) { return esc(s); }
  }
  function dot(cls, pulse) {
    return '<span class="dot ' + cls + (pulse ? ' dot-pulse' : '') + '"></span>';
  }
  function pill(cls, dotCls, pulse, label) {
    return '<span class="pill ' + cls + '">' + dot(dotCls, pulse) + esc(label) + '</span>';
  }
  function stagePill(stage, inProgress) {
    if (inProgress) return pill('pill-active', 'dot-amber', true, stage || 'in-progress');
    var s = (stage || 'idle').toLowerCase();
    if (s === 'idle')                 return pill('pill-idle',    'dot-green', false, 'idle');
    if (s === 'failed')               return pill('pill-failed',  'dot-red',   false, 'failed');
    if (s === 'waiting_for_approval') return pill('pill-waiting', 'dot-blue',  false, 'waiting');
    if (s === 'scheduled')            return pill('pill-waiting', 'dot-blue',  false, 'scheduled');
    return pill('pill-active', 'dot-amber', true, stage);
  }
  function card(label, valueHtml, detail) {
    return '<div class="sc">'
      + '<div class="sc-label">' + label + '</div>'
      + '<div class="sc-value">' + valueHtml + '</div>'
      + (detail ? '<div class="sc-detail">' + detail + '</div>' : '')
      + '</div>';
  }

  /* ─ render ─ */
  function renderStatus(d) {
    var cards = '';

    // 1. Pipeline Stage
    cards += card('Pipeline Stage',
      stagePill(d.stage, d.in_progress),
      d.in_progress ? 'Operation in progress' : 'No active operation'
    );

    // 2. Approval Status
    var approvalPill;
    if (d.waiting_for_approval) {
      approvalPill = pill('pill-waiting', 'dot-blue', false, 'waiting for approval');
    } else if (d.approval_sent) {
      approvalPill = pill('pill-active', 'dot-amber', false, 'approval sent');
    } else {
      approvalPill = pill('pill-idle', 'dot-green', false, 'not waiting');
    }
    var postDetail = d.current_post
      ? 'Post: ' + esc(String(d.current_post).substring(0, 38))
      : 'No current post';
    cards += card('Approval', approvalPill, postDetail);

    // 3. Active Session
    cards += card('Active Session',
      d.has_active_session
        ? pill('pill-active', 'dot-amber', false, 'session active')
        : pill('pill-idle',   'dot-green', false, 'no session'),
      d.has_active_session
        ? 'ID: ' + esc(d.session_id) + '<br>Started: ' + shortTime(d.session_started)
        : 'No active session'
    );

    // 4. Scheduler
    var schPill;
    if (d.scheduler_running) {
      schPill = pill('pill-active',  'dot-amber', true,  'running');
    } else if (d.scheduler_paused) {
      schPill = pill('pill-waiting', 'dot-blue',  false, 'paused');
    } else {
      schPill = pill('pill-idle',    'dot-green', false, 'stopped');
    }
    var schDetail = (d.scheduler_running && d.scheduler_next_run)
      ? 'Next: ' + shortTime(d.scheduler_next_run) : '';
    cards += card('Scheduler', schPill, schDetail);

    // 5. Orchestration Lock
    cards += card('Orch. Lock',
      d.has_lock
        ? pill('pill-failed', 'dot-red',   false, 'locked')
        : pill('pill-idle',   'dot-green', false, 'unlocked'),
      d.has_lock
        ? 'Owner: ' + esc(d.lock_owner) + '<br>Since: ' + shortTime(d.lock_acquired)
        : 'No active lock'
    );

    // 6. Heartbeat
    cards += card('Heartbeat',
      d.heartbeat_alive
        ? pill('pill-active', 'dot-green', true,  'alive')
        : pill('pill-idle',   'dot-green', false, 'inactive'),
      d.heartbeat_last ? 'Last: ' + shortTime(d.heartbeat_last) : 'No heartbeat recorded'
    );

    // 7. Queue Processing
    cards += card('Queue',
      d.queue_processing
        ? pill('pill-active', 'dot-amber', true,  'processing')
        : pill('pill-idle',   'dot-green', false, 'idle'),
      d.queue_processing ? 'Size: ' + (d.queue_size || 0) : 'Queue empty'
    );

    // 8. Failed Run Marker
    cards += card('Failed Run',
      d.has_failed
        ? pill('pill-failed', 'dot-red',   false, 'failed run')
        : pill('pill-idle',   'dot-green', false, 'none'),
      d.has_failed
        ? 'Reason: ' + esc(d.failed_reason) + '<br>At: ' + shortTime(d.failed_at)
        : 'No failed run recorded'
    );

    document.getElementById('status-area').innerHTML =
      '<div class="status-grid">' + cards + '</div>';

    // ── Template Send detail table ──
    var sendArea = document.getElementById('send-detail-area');
    if (!d.send_ever_run) {
      sendArea.innerHTML = '<div class="send-never">No template send has been recorded yet. Use the Batch Extractor\'s "Send to Template" to populate this.</div>';
    } else {
      var stTotal   = d.send_total || 0;
      var stOk      = d.send_success_count || 0;
      var stResults = d.send_results || [];
      var summaryPill;
      if (stOk === stTotal) {
        summaryPill = pill('pill-idle',   'dot-green', false, stOk + ' / ' + stTotal + ' received');
      } else if (stOk > 0) {
        summaryPill = pill('pill-active', 'dot-amber', false, stOk + ' / ' + stTotal + ' received');
      } else {
        summaryPill = pill('pill-failed', 'dot-red',   false, '0 / ' + stTotal + ' received');
      }
      var html = '<div class="send-summary">' + summaryPill
        + '<span class="send-ts">Last sent: ' + shortTime(d.send_timestamp) + '</span></div>';
      if (stResults.length > 0) {
        html += '<div class="send-table">';
        stResults.forEach(function(r) {
          var rowPill  = r.ok
            ? pill('pill-idle',   'dot-green', false, 'ok')
            : pill('pill-failed', 'dot-red',   false, 'failed');
          var name     = esc(r.endpoint.replace('/api/import_json', ''));
          var reasonHtml = (!r.ok && r.reason)
            ? '<span class="send-reason">' + esc(r.reason) + '</span>'
            : '<span></span>';
          html += '<div class="send-row ' + (r.ok ? 'send-ok' : 'send-fail') + '">'
            + '<span class="send-ep">' + name + '</span>'
            + '<span>' + rowPill + '</span>'
            + reasonHtml
            + '</div>';
        });
        html += '</div>';
      }
      sendArea.innerHTML = html;
    }

    // Update reset button label based on in_progress
    var btnReset = document.getElementById('btn-reset');
    if (d.in_progress) {
      btnReset.textContent = 'Force Reset';
      btnReset.className   = 'btn btn-force';
    } else {
      btnReset.textContent = 'Reset Pipeline';
      btnReset.className   = 'btn btn-reset';
    }
    btnReset.disabled = false;

    lastStatus = d;
  }

  /* ─ fetch ─ */
  function loadStatus() {
    document.getElementById('btn-refresh').disabled = true;
    fetch('/api/social/status')
      .then(function (r) { return r.json(); })
      .then(function (d) {
        renderStatus(d);
        secondsAgo = 0;
        startTick();
        document.getElementById('btn-refresh').disabled = false;
      })
      .catch(function (e) {
        document.getElementById('status-area').innerHTML =
          '<div style="font-family:IBM Plex Mono,monospace;font-size:.72rem;color:#991b1b;padding:12px 0;">'
          + 'Error loading status: ' + esc(String(e)) + '</div>';
        document.getElementById('btn-refresh').disabled = false;
      });
  }

  /* ─ tick counter ─ */
  function startTick() {
    clearInterval(tickTimer);
    secondsAgo = 0;
    tick();
    tickTimer = setInterval(tick, 1000);
  }
  function tick() {
    var el = document.getElementById('last-refresh');
    if (el) el.textContent = 'Refreshed ' + secondsAgo + 's ago';
    secondsAgo++;
  }

  /* ─ auto-poll every 15 s ─ */
  function startPoll() {
    clearInterval(pollTimer);
    pollTimer = setInterval(loadStatus, 15000);
  }

  /* ─ modal ─ */
  window.openModal = function () {
    var warn    = document.getElementById('modal-warn');
    var confirm = document.getElementById('btn-confirm');
    if (lastStatus && lastStatus.in_progress) {
      warn.classList.add('visible');
      confirm.textContent = 'Force Reset';
    } else {
      warn.classList.remove('visible');
      confirm.textContent = 'Confirm Reset';
    }
    document.getElementById('overlay').classList.add('open');
  };
  window.closeModal = function () {
    document.getElementById('overlay').classList.remove('open');
  };
  window.confirmReset = function () {
    closeModal();
    var btnReset = document.getElementById('btn-reset');
    btnReset.disabled    = true;
    btnReset.textContent = 'Resetting…';

    fetch('/api/social/reset', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d.success) {
          showBanner('success', '✓  Pipeline state reset successfully');
        } else {
          showBanner('error', 'Reset failed: ' + (d.error || 'Unknown error'));
        }
        loadStatus();
      })
      .catch(function (e) {
        showBanner('error', 'Reset failed: ' + esc(String(e)));
        loadStatus();
      });
  };

  /* close modal on overlay click */
  document.getElementById('overlay').addEventListener('click', function (e) {
    if (e.target === this) closeModal();
  });

  /* ─ banners ─ */
  function showBanner(type, msg) {
    var el = document.getElementById('banner-' + type);
    if (!el) return;
    if (type === 'error') el.textContent = msg;
    el.classList.add('visible');
    setTimeout(function () { el.classList.remove('visible'); }, 5500);
  }

  /* ─ init ─ */
  window.loadStatus = loadStatus;
  loadStatus();
  startPoll();
})();
</script>
</body>
</html>"""
