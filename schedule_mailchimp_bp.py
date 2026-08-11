import io
import os
import re
import zipfile
from datetime import datetime, timezone, timedelta

import requests
from flask import Blueprint, render_template_string, request, jsonify

from helpers import require_login
import config

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

schedule_mailchimp_bp = Blueprint('schedule_mailchimp_bp', __name__)

# ── Defaults (all overridable from the UI) ──────────────────────────
DEFAULT_AUDIENCE_NAME = "Push_160"
DEFAULT_SUBJECT = "Newsband Newsletter - Just Honest Journalism"
DEFAULT_FROM_NAME = "Newsband"
DEFAULT_FROM_EMAIL = "localnews@newsbandnewsletter.in"

# Mailchimp requires schedule times on the quarter hour, in UTC.
IST = timezone(timedelta(hours=5, minutes=30))


# ─────────────────────────────────────────────────────────────────────
# Mailchimp helpers
# ─────────────────────────────────────────────────────────────────────
def _api_config():
    api_key = os.environ.get("MAILCHIMP_API_KEY", "")
    if not api_key:
        raise RuntimeError("MAILCHIMP_API_KEY environment variable is not set.")
    server = api_key.split("-")[-1]
    return f"https://{server}.api.mailchimp.com/3.0", {"Authorization": f"Bearer {api_key}"}


def _mc_err(stage, exc):
    """Pull a human-readable message out of a Mailchimp error response."""
    resp = getattr(exc, "response", None)
    detail = ""
    if resp is not None:
        try:
            j = resp.json()
            detail = j.get("detail") or j.get("title") or ""
            errors = j.get("errors")
            if errors:
                detail += " — " + "; ".join(
                    f"{e.get('field', '')}: {e.get('message', '')}".strip(" :")
                    for e in errors
                )
        except ValueError:
            detail = resp.text[:300]
    return f"Failed to {stage}: {detail or exc}".strip()


def _extract_html(file_storage):
    """Return the newsletter HTML from an uploaded .zip or .html/.htm file."""
    filename = (file_storage.filename or "").lower()
    data = file_storage.read()
    if filename.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            html_names = [n for n in zf.namelist()
                          if n.lower().endswith((".html", ".htm"))
                          and not n.startswith("__MACOSX")]
            if not html_names:
                raise ValueError("the ZIP does not contain an .html file.")
            # Prefer the shallowest / shortest-named HTML file.
            html_names.sort(key=lambda n: (n.count("/"), len(n)))
            return zf.read(html_names[0]).decode("utf-8")
    return data.decode("utf-8")


def _to_mailchimp_utc(local_str):
    """Convert an IST 'YYYY-MM-DDTHH:MM' string to a quarter-hour UTC datetime."""
    naive = datetime.strptime(local_str, "%Y-%m-%dT%H:%M")
    utc = naive.replace(tzinfo=IST).astimezone(timezone.utc)
    rounded = int(round(utc.minute / 15.0) * 15)
    if rounded == 60:
        utc = utc.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    else:
        utc = utc.replace(minute=rounded, second=0, microsecond=0)
    return utc


def _default_send_time():
    """Next day at 9:00 AM IST, as 'YYYY-MM-DDTHH:MM' (split into date + time inputs)."""
    tomorrow = (datetime.now(IST) + timedelta(days=1)).replace(
        hour=9, minute=0, second=0, microsecond=0)
    return tomorrow.strftime("%Y-%m-%dT%H:%M")


class _CampaignError(Exception):
    """Raised when creating/filling a campaign fails. Carries a UI message,
    HTTP status and (when available) the draft campaign id."""
    def __init__(self, message, status=502, campaign_id=None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.campaign_id = campaign_id


def _create_campaign(base_url, headers, audience_id, subject, from_name, from_email, html):
    """Create a draft campaign and push its HTML content.

    Returns (campaign_id, campaign_json). Raises _CampaignError on failure.
    """
    payload = {
        "type": "regular",
        "recipients": {"list_id": audience_id},
        "settings": {
            "subject_line": subject,
            "title": f"{subject} — Newsband ({datetime.now(IST).strftime('%Y-%m-%d %H:%M')})",
            "from_name": from_name,
            "reply_to": from_email,
        },
    }
    try:
        r = requests.post(f"{base_url}/campaigns", headers=headers, json=payload, timeout=30)
        r.raise_for_status()
    except requests.RequestException as e:
        raise _CampaignError(_mc_err("create the campaign", e))
    campaign = r.json()
    cid = campaign["id"]

    try:
        rc = requests.put(
            f"{base_url}/campaigns/{cid}/content",
            headers=headers, json={"html": html}, timeout=30,
        )
        rc.raise_for_status()
    except requests.RequestException as e:
        raise _CampaignError(_mc_err("set the campaign content", e), campaign_id=cid)
    return cid, campaign


def _delete_campaign(base_url, headers, cid):
    """Best-effort cleanup of a throwaway draft campaign; failures are ignored."""
    try:
        requests.delete(f"{base_url}/campaigns/{cid}", headers=headers, timeout=20)
    except requests.RequestException:
        pass


# ─────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────
@schedule_mailchimp_bp.route('/')
@require_login
def index():
    default_date, default_clock = _default_send_time().split("T")
    return render_template_string(
        SCHEDULE_MAILCHIMP_HTML,
        logo_url=config.LOGO_URL,
        default_subject=DEFAULT_SUBJECT,
        default_from_name=DEFAULT_FROM_NAME,
        default_from_email=DEFAULT_FROM_EMAIL,
        default_send_date=default_date,
        default_send_clock=default_clock,
    )


@schedule_mailchimp_bp.route('/api/audiences')
@require_login
def api_audiences():
    try:
        base_url, headers = _api_config()
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500
    try:
        r = requests.get(
            f"{base_url}/lists",
            headers=headers,
            params={"count": 1000, "fields": "lists.id,lists.name,lists.stats.member_count"},
            timeout=20,
        )
        r.raise_for_status()
    except requests.RequestException as e:
        return jsonify({"error": _mc_err("load audiences", e)}), 502

    audiences = [
        {
            "id": l["id"],
            "name": l.get("name", ""),
            "members": l.get("stats", {}).get("member_count", 0),
        }
        for l in r.json().get("lists", [])
    ]
    return jsonify({"audiences": audiences, "default_name": DEFAULT_AUDIENCE_NAME})


@schedule_mailchimp_bp.route('/api/preview', methods=["POST"])
@require_login
def api_preview():
    """Extract and return the newsletter HTML so the UI can show a live preview."""
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "No file provided."}), 400
    try:
        html = _extract_html(f)
    except (ValueError, zipfile.BadZipFile) as e:
        return jsonify({"error": f"Could not read newsletter file: {e}"}), 400
    except UnicodeDecodeError:
        return jsonify({"error": "Newsletter file is not valid UTF-8 HTML."}), 400
    if not html.strip():
        return jsonify({"error": "The newsletter file is empty."}), 400
    return jsonify({"html": html})


@schedule_mailchimp_bp.route('/api/schedule', methods=["POST"])
@require_login
def api_schedule():
    try:
        base_url, headers = _api_config()
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500

    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "Please attach the newsletter ZIP or HTML file."}), 400
    try:
        html = _extract_html(f)
    except (ValueError, zipfile.BadZipFile) as e:
        return jsonify({"error": f"Could not read newsletter file: {e}"}), 400
    except UnicodeDecodeError:
        return jsonify({"error": "Newsletter file is not valid UTF-8 HTML."}), 400
    if not html.strip():
        return jsonify({"error": "The newsletter file is empty."}), 400

    audience_id = (request.form.get("audience_id") or "").strip()
    subject = (request.form.get("subject") or "").strip()
    from_name = (request.form.get("from_name") or "").strip()
    from_email = (request.form.get("from_email") or "").strip()
    send_now = request.form.get("send_now") == "true"
    send_time = (request.form.get("send_time") or "").strip()

    if not audience_id:
        return jsonify({"error": "Please choose an audience."}), 400
    if not subject:
        return jsonify({"error": "Please enter a subject line."}), 400
    if not from_name or not from_email:
        return jsonify({"error": "From name and from email are required."}), 400

    schedule_iso = None
    if not send_now:
        try:
            utc_dt = _to_mailchimp_utc(send_time)
        except ValueError:
            return jsonify({"error": "Invalid send time."}), 400
        if utc_dt <= datetime.now(timezone.utc) + timedelta(minutes=1):
            return jsonify({"error": "Send time must be in the future."}), 400
        schedule_iso = utc_dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")

    # 1) Create the campaign and push the HTML content
    try:
        cid, campaign = _create_campaign(
            base_url, headers, audience_id, subject, from_name, from_email, html)
    except _CampaignError as e:
        body = {"error": e.message}
        if e.campaign_id:
            body["campaign_id"] = e.campaign_id
        return jsonify(body), e.status

    # 2) Schedule (or send immediately)
    action = "send" if send_now else "schedule"
    body = {} if send_now else {"schedule_time": schedule_iso}
    try:
        ra = requests.post(
            f"{base_url}/campaigns/{cid}/actions/{action}",
            headers=headers, json=body, timeout=30,
        )
        ra.raise_for_status()
    except requests.RequestException as e:
        verb = "send" if send_now else "schedule"
        return jsonify({"error": _mc_err(f"{verb} the campaign", e),
                        "campaign_id": cid}), 502

    return jsonify({
        "success": True,
        "campaign_id": cid,
        "web_id": campaign.get("web_id"),
        "scheduled": not send_now,
        "schedule_time_utc": schedule_iso,
        "recipients": campaign.get("recipients", {}).get("recipient_count"),
    })


@schedule_mailchimp_bp.route('/api/test', methods=["POST"])
@require_login
def api_test():
    """Send a test copy of the newsletter to one or more addresses.

    Mailchimp can only test a campaign that already has content, so we spin up
    a throwaway draft, fire the test, then delete the draft.
    """
    try:
        base_url, headers = _api_config()
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500

    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "Please attach the newsletter ZIP or HTML file."}), 400
    try:
        html = _extract_html(f)
    except (ValueError, zipfile.BadZipFile) as e:
        return jsonify({"error": f"Could not read newsletter file: {e}"}), 400
    except UnicodeDecodeError:
        return jsonify({"error": "Newsletter file is not valid UTF-8 HTML."}), 400
    if not html.strip():
        return jsonify({"error": "The newsletter file is empty."}), 400

    audience_id = (request.form.get("audience_id") or "").strip()
    subject = (request.form.get("subject") or "").strip()
    from_name = (request.form.get("from_name") or "").strip()
    from_email = (request.form.get("from_email") or "").strip()

    if not audience_id:
        return jsonify({"error": "Please choose an audience."}), 400
    if not subject:
        return jsonify({"error": "Please enter a subject line."}), 400
    if not from_name or not from_email:
        return jsonify({"error": "From name and from email are required."}), 400

    raw_emails = request.form.get("test_emails") or ""
    test_emails = [e for e in re.split(r"[,;\s]+", raw_emails) if e]
    if not test_emails:
        return jsonify({"error": "Enter at least one email address to send the test to."}), 400
    if len(test_emails) > 10:
        return jsonify({"error": "Please limit test recipients to 10 addresses."}), 400
    bad = [e for e in test_emails if "@" not in e or "." not in e.rsplit("@", 1)[-1]]
    if bad:
        return jsonify({"error": "These don't look like valid emails: " + ", ".join(bad)}), 400

    # Build a draft campaign with the content, fire the test, then clean it up.
    try:
        cid, _campaign = _create_campaign(
            base_url, headers, audience_id, subject, from_name, from_email, html)
    except _CampaignError as e:
        return jsonify({"error": e.message}), e.status

    try:
        rt = requests.post(
            f"{base_url}/campaigns/{cid}/actions/test",
            headers=headers,
            json={"test_emails": test_emails, "send_type": "html"},
            timeout=30,
        )
        rt.raise_for_status()
    except requests.RequestException as e:
        _delete_campaign(base_url, headers, cid)
        return jsonify({"error": _mc_err("send the test email", e)}), 502

    # The test is out the door — the throwaway draft has served its purpose.
    _delete_campaign(base_url, headers, cid)

    return jsonify({"success": True, "test_emails": test_emails})


SCHEDULE_MAILCHIMP_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Schedule Mailchimp Newsletter (Classic) — Newsband</title>
  <link rel="icon" type="image/png" href="/static_files/NB-favicon.png" />
  <link rel="apple-touch-icon" href="/static_files/NB-favicon.png" />
  <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,700;0,900;1,700&family=IBM+Plex+Mono:wght@400;500;600&family=Source+Sans+3:wght@300;400;600&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    :root {
      --ink: #0a0a0a; --paper: #f4f0e8; --accent: #c8102e; --mid: #5a5247;
      --rule: #1a1a1a; --faint: #e0dbd0;
      --mc: #ffe01b; --green: #1a7a3c; --green-bg: #e6f4ea;
      --amber: #92400e; --amber-bg: #fef3c7; --red-bg: #fdecea;
    }
    html, body { min-height: 100%; }
    body {
      background-color: var(--paper);
      background-image: repeating-linear-gradient(0deg, transparent, transparent 27px, var(--faint) 27px, var(--faint) 28px);
      min-height: 100vh; display: flex; align-items: flex-start; justify-content: center;
      font-family: 'Source Sans 3', sans-serif; color: var(--ink); overflow-x: hidden; padding: 30px 0;
    }
    .page-wrap { width: 100%; max-width: 640px; padding: 24px; }

    .masthead { text-align: center; border-top: 4px solid var(--rule); border-bottom: 1px solid var(--rule); padding: 14px 0 12px; margin-bottom: 6px; }
    .masthead::before { content: ''; display: block; height: 2px; background: var(--accent); margin-bottom: 12px; }
    .masthead-logo { max-width: 240px; max-height: 70px; display: block; margin: 0 auto; }
    .masthead-tagline { font-family: 'IBM Plex Mono', monospace; font-size: 0.62rem; letter-spacing: 0.18em; color: var(--mid); text-transform: uppercase; margin-top: 10px; }
    .dateline {
      font-family: 'IBM Plex Mono', monospace; font-size: 0.6rem; color: var(--mid);
      padding: 4px 0; border-bottom: 1px solid var(--rule); margin-bottom: 24px;
      letter-spacing: 0.08em; display: flex; justify-content: space-between; align-items: center;
    }
    .dateline a { color: var(--accent); text-decoration: none; font-weight: 600; letter-spacing: 0.1em; }
    .dateline a:hover { text-decoration: underline; }

    .card {
      position: relative; background: #fff; border: 1px solid #c8c2b5;
      box-shadow: 6px 6px 0 var(--ink); overflow: hidden;
      animation: slideUp 0.5s cubic-bezier(0.22, 1, 0.36, 1) both;
    }
    @keyframes slideUp { from { opacity: 0; transform: translateY(18px); } to { opacity: 1; transform: translateY(0); } }
    .card-accent { height: 4px; background: var(--accent); }
    .card-body { padding: 32px 38px 38px; }

    .headline {
      font-family: 'Playfair Display', serif; font-weight: 900;
      font-size: 1.8rem; line-height: 1.12; text-align: center; margin-bottom: 8px;
    }
    .headline .accent { color: var(--accent); font-style: italic; }
    .subhead { font-size: 0.86rem; color: var(--mid); line-height: 1.55; font-weight: 300; text-align: center; max-width: 440px; margin: 0 auto 26px; }

    .field { margin-bottom: 18px; }
    .field-label {
      display: block; font-family: 'IBM Plex Mono', monospace; font-size: 0.62rem;
      font-weight: 600; letter-spacing: 0.12em; text-transform: uppercase;
      color: var(--mid); margin-bottom: 7px;
    }
    .field-label .req { color: var(--accent); }
    input[type=text], input[type=email], input[type=date], input[type=datetime-local], select {
      width: 100%; font-family: 'Source Sans 3', sans-serif; font-size: 0.92rem;
      color: var(--ink); background: var(--paper); border: 1px solid var(--rule);
      padding: 10px 12px; box-shadow: 2px 2px 0 var(--faint);
    }
    input:focus, select:focus { outline: none; border-color: var(--accent); box-shadow: 2px 2px 0 var(--accent); }
    select:disabled { opacity: 0.6; }

    /* Drop zone */
    .dropzone {
      display: block; border: 2px dashed var(--rule); background: var(--paper); padding: 24px 16px;
      text-align: center; cursor: pointer; transition: all 0.15s;
    }
    .dropzone:hover, .dropzone.drag { border-color: var(--accent); background: #fff; }
    .dropzone .dz-icon { font-size: 2rem; display: block; margin-bottom: 6px; line-height: 1; }
    .dropzone .dz-main { display: block; font-size: 0.9rem; font-weight: 600; }
    .dropzone .dz-sub { display: block; font-family: 'IBM Plex Mono', monospace; font-size: 0.6rem; color: var(--mid); letter-spacing: 0.08em; margin-top: 5px; text-transform: uppercase; }

    /* Preview — browser-frame style (scaled to fit width) */
    .preview-wrap { display: none; margin-bottom: 18px; border: 1px solid var(--rule); box-shadow: 4px 4px 0 var(--faint); background: #fff; }
    .preview-wrap.show { display: block; animation: slideUp 0.3s ease both; }
    .preview-bar { display: flex; align-items: center; gap: 9px; background: var(--paper); border-bottom: 1px solid var(--rule); padding: 8px 12px; }
    .preview-lights { display: flex; gap: 6px; flex-shrink: 0; }
    .preview-lights i { width: 11px; height: 11px; border-radius: 50%; display: block; }
    .preview-lights .r { background: #ff5f57; } .preview-lights .y { background: #febc2e; } .preview-lights .g { background: #28c840; }
    .preview-url {
      flex: 1; min-width: 0; text-align: center; font-family: 'IBM Plex Mono', monospace; font-size: 0.56rem;
      letter-spacing: 0.06em; color: var(--mid); background: #fff; border: 1px solid var(--faint); border-radius: 3px;
      padding: 3px 8px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }
    .preview-bar button {
      flex-shrink: 0; background: var(--ink); border: 1px solid var(--ink); color: #fff; font-family: 'IBM Plex Mono', monospace;
      font-size: 0.56rem; letter-spacing: 0.06em; text-transform: uppercase; padding: 4px 9px; cursor: pointer;
    }
    .preview-bar button:hover { background: var(--accent); border-color: var(--accent); }
    .preview-stage { position: relative; background: #d6d6d6; max-height: 70vh; overflow-y: auto; overflow-x: hidden; }
    .preview-frame { border: none; background: #fff; transform-origin: top left; display: block; }
    .preview-loading { padding: 24px; text-align: center; font-family: 'IBM Plex Mono', monospace; font-size: 0.66rem; color: var(--mid); letter-spacing: 0.08em; }

    /* Fullscreen preview overlay */
    .pv-overlay { display: none; position: fixed; inset: 0; background: rgba(10,10,10,0.82); z-index: 1000; padding: 22px; }
    .pv-overlay.show { display: flex; flex-direction: column; }
    .pv-overlay-bar { display: flex; align-items: center; gap: 9px; background: var(--paper); border: 1px solid var(--rule); padding: 9px 14px; }
    .pv-overlay-frame { flex: 1; width: 100%; border: 1px solid var(--rule); border-top: none; background: #fff; }
    .pv-close { flex-shrink: 0; background: var(--accent); border: 1px solid var(--ink); color: #fff; font-family: 'IBM Plex Mono', monospace; font-size: 0.58rem; letter-spacing: 0.06em; text-transform: uppercase; padding: 5px 11px; cursor: pointer; }
    .dropzone.has-file { border-style: solid; border-color: var(--green); background: var(--green-bg); }
    .dropzone.has-file .dz-icon { color: var(--green); }

    .row { display: flex; gap: 16px; }
    .row .field { flex: 1; }

    /* Send-test row */
    .test-row { display: flex; gap: 10px; align-items: stretch; }
    .test-row input { flex: 1; }
    .btn-test {
      flex-shrink: 0; white-space: nowrap; min-width: 118px;
      display: inline-flex; align-items: center; justify-content: center; gap: 7px;
      font-family: 'IBM Plex Mono', monospace; font-size: 0.66rem; font-weight: 600;
      letter-spacing: 0.08em; text-transform: uppercase; cursor: pointer;
      color: #fff; background: var(--ink); border: 1px solid var(--ink);
      padding: 0 16px; box-shadow: 2px 2px 0 var(--faint); transition: all 0.15s;
    }
    .btn-test:hover:not(:disabled) { background: var(--accent); border-color: var(--accent); }
    .btn-test:disabled { opacity: 0.55; cursor: not-allowed; }
    .field-label .opt { color: var(--mid); font-weight: 400; text-transform: none; letter-spacing: 0; }

    .when-toggle { display: flex; gap: 0; margin-bottom: 16px; border: 1px solid var(--rule); }
    .when-toggle button {
      flex: 1; font-family: 'IBM Plex Mono', monospace; font-size: 0.66rem; font-weight: 600;
      letter-spacing: 0.08em; text-transform: uppercase; padding: 10px; cursor: pointer;
      background: var(--paper); color: var(--mid); border: none; transition: all 0.15s;
    }
    .when-toggle button.active { background: var(--ink); color: #fff; }
    .when-toggle button + button { border-left: 1px solid var(--rule); }

    .tz-note { font-family: 'IBM Plex Mono', monospace; font-size: 0.58rem; color: var(--mid); letter-spacing: 0.06em; margin-top: 6px; }

    .submit-btn {
      width: 100%; display: inline-flex; align-items: center; justify-content: center; gap: 10px;
      font-family: 'IBM Plex Mono', monospace; font-size: 0.8rem; font-weight: 600;
      letter-spacing: 0.1em; text-transform: uppercase; cursor: pointer;
      color: #fff; background: var(--accent); border: 1px solid var(--ink);
      padding: 15px; box-shadow: 4px 4px 0 var(--ink); transition: all 0.15s; margin-top: 6px;
    }
    .submit-btn:hover:not(:disabled) { transform: translate(-1px,-1px); box-shadow: 5px 5px 0 var(--ink); }
    .submit-btn:active:not(:disabled) { transform: translate(2px,2px); box-shadow: 1px 1px 0 var(--ink); }
    .submit-btn:disabled { opacity: 0.55; cursor: not-allowed; }

    .result { margin-top: 20px; padding: 16px 18px; font-size: 0.86rem; line-height: 1.5; display: none; }
    .result.show { display: block; animation: slideUp 0.3s ease both; }
    .result.ok { background: var(--green-bg); border: 1px solid var(--green); }
    .result.err { background: var(--red-bg); border: 1px solid var(--accent); }
    .result h4 { font-family: 'Playfair Display', serif; font-size: 1.05rem; margin-bottom: 6px; }
    .result.ok h4 { color: var(--green); }
    .result.err h4 { color: var(--accent); }
    .result code { font-family: 'IBM Plex Mono', monospace; font-size: 0.78rem; background: rgba(0,0,0,0.06); padding: 1px 5px; }

    .back-link { display: block; text-align: center; margin-top: 22px; }
    .back-link a {
      font-family: 'IBM Plex Mono', monospace; font-size: 0.66rem; font-weight: 600;
      letter-spacing: 0.08em; text-transform: uppercase; color: var(--ink); text-decoration: none;
      border-bottom: 1px solid var(--accent); padding-bottom: 2px;
    }
    .footer-note { font-family: 'IBM Plex Mono', monospace; font-size: 0.56rem; color: #aaa; text-align: center; margin-top: 22px; letter-spacing: 0.08em; }
    .spinner { width: 14px; height: 14px; border: 2px solid rgba(255,255,255,0.4); border-top-color: #fff; border-radius: 50%; animation: spin 0.7s linear infinite; display: inline-block; }
    @keyframes spin { to { transform: rotate(360deg); } }
  </style>
</head>
<body>
  <div class="page-wrap">
    <div class="masthead">
      <img src="{{ logo_url }}" alt="Newsband" class="masthead-logo" />
      <div class="masthead-tagline">Automated Campaign Scheduling</div>
    </div>
    <div class="dateline">
      <span>MAILCHIMP DISPATCH DESK</span>
      <a href="{{ url_for('dashboard_bp.dashboard') }}">&#8592; DASHBOARD</a>
    </div>

    <div class="card">
      <div class="card-accent"></div>
      <div class="card-body">
        <h1 class="headline">Schedule <span class="accent">Mailchimp</span> Newsletter</h1>
        <p class="subhead">Attach the newsletter you exported from this software and ship it straight to your Mailchimp audience.</p>

        <form id="schedule-form">
          <!-- File -->
          <div class="field">
            <div class="field-label">Newsletter file <span class="req">*</span></div>
            <label class="dropzone" id="dropzone">
              <span class="dz-icon">📰</span>
              <span class="dz-main" id="dz-text">Click or drop your ZIP / HTML here</span>
              <span class="dz-sub" id="dz-sub">Exported from a Newsband editor</span>
              <input type="file" id="file-input" accept=".zip,.html,.htm" hidden>
            </label>
          </div>

          <!-- Preview -->
          <div class="preview-wrap" id="preview-wrap">
            <div class="preview-bar">
              <span class="preview-lights"><i class="r"></i><i class="y"></i><i class="g"></i></span>
              <span class="preview-url">newsband.in · newsletter preview · read-only</span>
              <button type="button" id="preview-expand">⤢ Expand</button>
              <button type="button" id="preview-toggle">Hide</button>
            </div>
            <div class="preview-loading" id="preview-loading">Rendering preview…</div>
            <div class="preview-stage" id="preview-stage" style="display:none;">
              <iframe class="preview-frame" id="preview-frame" sandbox="allow-same-origin allow-scripts"></iframe>
            </div>
          </div>

          <!-- Audience -->
          <div class="field">
            <div class="field-label">Audience <span class="req">*</span></div>
            <select id="audience" required>
              <option value="">Loading audiences…</option>
            </select>
          </div>

          <!-- Subject -->
          <div class="field">
            <div class="field-label">Subject line <span class="req">*</span></div>
            <input type="text" id="subject" value="{{ default_subject }}" required>
          </div>

          <!-- From -->
          <div class="row">
            <div class="field">
              <div class="field-label">From name <span class="req">*</span></div>
              <input type="text" id="from_name" value="{{ default_from_name }}" required>
            </div>
            <div class="field">
              <div class="field-label">From email <span class="req">*</span></div>
              <input type="email" id="from_email" value="{{ default_from_email }}" required>
            </div>
          </div>

          <!-- Send a test first -->
          <div class="field">
            <div class="field-label">Send a test first <span class="opt">(optional)</span></div>
            <div class="test-row">
              <input type="text" id="test_email" value="manasgawde@gmail.com, contact@newsband.in" placeholder="you@example.com, teammate@example.com">
              <button type="button" class="btn-test" id="btn-test">✉ Send test</button>
            </div>
            <div class="tz-note">Delivers this exact newsletter to the address(es) above so you can check it before scheduling. Separate multiple with commas.</div>
          </div>

          <!-- When -->
          <div class="field-label">When to send</div>
          <div class="when-toggle">
            <button type="button" id="btn-schedule" class="active">📅 Schedule</button>
            <button type="button" id="btn-now">⚡ Send now</button>
          </div>
          <div class="field" id="time-field">
            <div class="row">
              <div class="field" style="margin-bottom:0;">
                <div class="field-label">Delivery date</div>
                <input type="date" id="send_date" value="{{ default_send_date }}">
              </div>
              <div class="field" style="margin-bottom:0;">
                <div class="field-label">Delivery time</div>
                <select id="send_clock"></select>
              </div>
            </div>
            <div class="tz-note">Interpreted as India Standard Time (IST). Times step every 15&nbsp;minutes.</div>
          </div>

          <button type="submit" class="submit-btn" id="submit-btn">
            <span id="submit-label">📅 Schedule Campaign</span>
          </button>
        </form>

        <div class="result" id="result"></div>
      </div>
    </div>

    <div class="back-link"><a href="{{ url_for('dashboard_bp.dashboard') }}">&#8592; Back to Dashboard</a></div>
    <div class="footer-note">NEWSBAND JOURNALISM PLATFORM &nbsp;&middot;&nbsp; CAMPAIGN SCHEDULER</div>
  </div>

  <!-- Fullscreen preview -->
  <div class="pv-overlay" id="pv-overlay">
    <div class="pv-overlay-bar">
      <span class="preview-lights"><i class="r"></i><i class="y"></i><i class="g"></i></span>
      <span class="preview-url">newsband.in · full newsletter preview</span>
      <button type="button" class="pv-close" id="pv-close">✕ Close</button>
    </div>
    <iframe class="pv-overlay-frame" id="pv-frame" sandbox="allow-same-origin allow-scripts"></iframe>
  </div>

  <script>
  (function () {
    var sendNow = false;
    var fileInput = document.getElementById('file-input');
    var dropzone = document.getElementById('dropzone');
    var dzText = document.getElementById('dz-text');
    var dzSub = document.getElementById('dz-sub');
    var audienceSel = document.getElementById('audience');
    var btnSchedule = document.getElementById('btn-schedule');
    var btnNow = document.getElementById('btn-now');
    var timeField = document.getElementById('time-field');
    var submitLabel = document.getElementById('submit-label');
    var submitBtn = document.getElementById('submit-btn');
    var resultBox = document.getElementById('result');
    var testEmail = document.getElementById('test_email');
    var btnTest = document.getElementById('btn-test');
    var previewWrap = document.getElementById('preview-wrap');
    var previewStage = document.getElementById('preview-stage');
    var previewFrame = document.getElementById('preview-frame');
    var previewLoading = document.getElementById('preview-loading');
    var previewToggle = document.getElementById('preview-toggle');
    var previewExpand = document.getElementById('preview-expand');
    var pvOverlay = document.getElementById('pv-overlay');
    var pvFrame = document.getElementById('pv-frame');
    var pvClose = document.getElementById('pv-close');
    var currentPreviewHtml = '';
    var DEFAULT_AUDIENCE = '';

    // ── Build the 15-minute time dropdown (Mailchimp-style) ──
    var clockSel = document.getElementById('send_clock');
    var defaultClock = '{{ default_send_clock }}';
    for (var h = 0; h < 24; h++) {
      for (var m = 0; m < 60; m += 15) {
        var val = ('0' + h).slice(-2) + ':' + ('0' + m).slice(-2);
        var opt = document.createElement('option');
        opt.value = val;
        opt.textContent = (h % 12 || 12) + ':' + ('0' + m).slice(-2) + ' ' + (h < 12 ? 'AM' : 'PM');
        if (val === defaultClock) opt.selected = true;
        clockSel.appendChild(opt);
      }
    }

    // ── Load audiences ──
    fetch('api/audiences')
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) {
        if (!res.ok) { audienceSel.innerHTML = '<option value="">⚠ ' + (res.d.error || 'Could not load audiences') + '</option>'; return; }
        var want = (res.d.default_name || '').toLowerCase().replace(/[\\s_]+/g, '');
        var list = res.d.audiences || [];
        if (!list.length) { audienceSel.innerHTML = '<option value="">No audiences found</option>'; return; }
        audienceSel.innerHTML = '';
        list.forEach(function (a) {
          var opt = document.createElement('option');
          opt.value = a.id;
          opt.textContent = a.name + ' (' + a.members + ' contacts)';
          var norm = (a.name || '').toLowerCase().replace(/[\\s_]+/g, '');
          if (norm === want) { opt.selected = true; DEFAULT_AUDIENCE = a.id; }
          audienceSel.appendChild(opt);
        });
      })
      .catch(function () { audienceSel.innerHTML = '<option value="">⚠ Network error loading audiences</option>'; });

    // ── File picking ──
    function setFile(file) {
      if (!file) return;
      var ok = /\\.(zip|html?|htm)$/i.test(file.name);
      if (!ok) { alert('Please choose a .zip or .html file.'); return; }
      var dt = new DataTransfer(); dt.items.add(file); fileInput.files = dt.files;
      dropzone.classList.add('has-file');
      dzText.textContent = file.name;
      dzSub.textContent = (file.size / 1024).toFixed(0) + ' KB — ready to ship';
      loadPreview(file);
    }

    // ── Live preview (scaled to fit the panel width) ──
    function fitPreview() {
      var doc = previewFrame.contentDocument;
      if (!doc || !doc.body) return;
      var natW = Math.max(doc.documentElement.scrollWidth, doc.body.scrollWidth, 320);
      var natH = Math.max(doc.documentElement.scrollHeight, doc.body.scrollHeight, 200);
      previewFrame.style.width = natW + 'px';
      previewFrame.style.height = natH + 'px';
      var scale = Math.min(1, previewStage.clientWidth / natW);
      previewFrame.style.transform = 'scale(' + scale + ')';
      previewStage.style.height = Math.ceil(natH * scale) + 'px';
    }
    previewFrame.addEventListener('load', function () {
      fitPreview();
      setTimeout(fitPreview, 350);   // re-fit once images settle
    });
    window.addEventListener('resize', fitPreview);

    function loadPreview(file) {
      previewWrap.classList.add('show');
      previewToggle.textContent = 'Hide';
      previewLoading.textContent = 'Rendering preview…';
      previewLoading.style.display = 'block';
      previewStage.style.display = 'none';
      var fd = new FormData(); fd.append('file', file);
      fetch('api/preview', { method: 'POST', body: fd })
        .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
        .then(function (res) {
          if (!res.ok || !res.d.html) {
            previewLoading.textContent = '⚠ ' + (res.d.error || 'Could not render preview.');
            return;
          }
          currentPreviewHtml = res.d.html;
          previewFrame.srcdoc = currentPreviewHtml;
          previewLoading.style.display = 'none';
          previewStage.style.display = 'block';
        })
        .catch(function () { previewLoading.textContent = '⚠ Network error rendering preview.'; });
    }

    previewToggle.addEventListener('click', function () {
      var hidden = previewStage.style.display === 'none' && previewLoading.style.display === 'none';
      if (hidden) {
        if (currentPreviewHtml) { previewStage.style.display = 'block'; fitPreview(); }
        previewToggle.textContent = 'Hide';
      } else {
        previewStage.style.display = 'none';
        previewLoading.style.display = 'none';
        previewToggle.textContent = 'Show';
      }
    });

    // ── Fullscreen preview ──
    previewExpand.addEventListener('click', function () {
      if (!currentPreviewHtml) return;
      pvFrame.srcdoc = currentPreviewHtml;
      pvOverlay.classList.add('show');
    });
    function closeOverlay() { pvOverlay.classList.remove('show'); }
    pvClose.addEventListener('click', closeOverlay);
    pvOverlay.addEventListener('click', function (e) { if (e.target === pvOverlay) closeOverlay(); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeOverlay(); });
    fileInput.addEventListener('change', function () { setFile(fileInput.files[0]); });
    ['dragover', 'dragenter'].forEach(function (ev) {
      dropzone.addEventListener(ev, function (e) { e.preventDefault(); dropzone.classList.add('drag'); });
    });
    ['dragleave', 'dragend'].forEach(function (ev) {
      dropzone.addEventListener(ev, function () { dropzone.classList.remove('drag'); });
    });
    dropzone.addEventListener('drop', function (e) {
      e.preventDefault(); dropzone.classList.remove('drag');
      if (e.dataTransfer.files.length) setFile(e.dataTransfer.files[0]);
    });

    // ── Schedule / now toggle ──
    function setMode(now) {
      sendNow = now;
      btnNow.classList.toggle('active', now);
      btnSchedule.classList.toggle('active', !now);
      timeField.style.display = now ? 'none' : 'block';
      submitLabel.textContent = now ? '⚡ Send Campaign Now' : '📅 Schedule Campaign';
    }
    btnSchedule.addEventListener('click', function () { setMode(false); });
    btnNow.addEventListener('click', function () { setMode(true); });

    // ── Submit ──
    function showResult(ok, html) {
      resultBox.className = 'result show ' + (ok ? 'ok' : 'err');
      resultBox.innerHTML = html;
      resultBox.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    // ── Send test email ──
    btnTest.addEventListener('click', function () {
      if (!fileInput.files.length) { showResult(false, '<h4>Missing file</h4>Attach the newsletter ZIP or HTML first.'); return; }
      if (!audienceSel.value) { showResult(false, '<h4>No audience</h4>Pick an audience first.'); return; }
      var emails = (testEmail.value || '').trim();
      if (!emails) { showResult(false, '<h4>No test address</h4>Enter at least one email to send the test to.'); return; }

      var fd = new FormData();
      fd.append('file', fileInput.files[0]);
      fd.append('audience_id', audienceSel.value);
      fd.append('subject', document.getElementById('subject').value);
      fd.append('from_name', document.getElementById('from_name').value);
      fd.append('from_email', document.getElementById('from_email').value);
      fd.append('test_emails', emails);

      btnTest.disabled = true;
      var prevLabel = btnTest.innerHTML;
      btnTest.innerHTML = '<span class="spinner"></span> Sending…';
      resultBox.className = 'result';

      fetch('api/test', { method: 'POST', body: fd })
        .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
        .then(function (res) {
          if (!res.ok || !res.d.success) {
            showResult(false, '<h4>Test failed</h4>' + (res.d.error || 'Unknown error.'));
            return;
          }
          var sent = (res.d.test_emails || []).join(', ');
          showResult(true, '<h4>✅ Test sent</h4>Sent a test copy to <code>' + sent + '</code>. Check the inbox, then schedule when it looks right.');
        })
        .catch(function () { showResult(false, '<h4>Network error</h4>Could not reach the server.'); })
        .finally(function () { btnTest.disabled = false; btnTest.innerHTML = prevLabel; });
    });

    document.getElementById('schedule-form').addEventListener('submit', function (e) {
      e.preventDefault();
      if (!fileInput.files.length) { showResult(false, '<h4>Missing file</h4>Attach the newsletter ZIP or HTML first.'); return; }
      if (!audienceSel.value) { showResult(false, '<h4>No audience</h4>Pick an audience to send to.'); return; }

      var fd = new FormData();
      fd.append('file', fileInput.files[0]);
      fd.append('audience_id', audienceSel.value);
      fd.append('subject', document.getElementById('subject').value);
      fd.append('from_name', document.getElementById('from_name').value);
      fd.append('from_email', document.getElementById('from_email').value);
      fd.append('send_now', sendNow ? 'true' : 'false');
      fd.append('send_time', document.getElementById('send_date').value + 'T' + clockSel.value);

      submitBtn.disabled = true;
      var prev = submitLabel.textContent;
      submitLabel.innerHTML = '<span class="spinner"></span> Working…';
      resultBox.className = 'result';

      fetch('api/schedule', { method: 'POST', body: fd })
        .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
        .then(function (res) {
          if (!res.ok || !res.d.success) {
            showResult(false, '<h4>Couldn\\'t send</h4>' + (res.d.error || 'Unknown error.'));
            return;
          }
          var d = res.d;
          var msg = '<h4>' + (d.scheduled ? '✅ Campaign scheduled' : '✅ Campaign sent') + '</h4>';
          if (d.scheduled && d.schedule_time_utc) {
            msg += 'Send time (UTC): <code>' + d.schedule_time_utc + '</code><br>';
          }
          if (d.recipients != null) { msg += 'Recipients: <code>' + d.recipients + '</code><br>'; }
          msg += 'Campaign ID: <code>' + d.campaign_id + '</code>';
          showResult(true, msg);
        })
        .catch(function () { showResult(false, '<h4>Network error</h4>Could not reach the server.'); })
        .finally(function () { submitBtn.disabled = false; submitLabel.textContent = prev; });
    });
  })();
  </script>
</body>
</html>"""
