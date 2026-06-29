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

schedule_mailchimp_2_bp = Blueprint('schedule_mailchimp_2_bp', __name__)

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
@schedule_mailchimp_2_bp.route('/')
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


@schedule_mailchimp_2_bp.route('/api/audiences')
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


@schedule_mailchimp_2_bp.route('/api/preview', methods=["POST"])
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


@schedule_mailchimp_2_bp.route('/api/schedule', methods=["POST"])
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


@schedule_mailchimp_2_bp.route('/api/test', methods=["POST"])
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
  <title>Schedule Mailchimp Newsletter — Newsband</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Playfair+Display:ital,wght@0,700;0,900;1,700&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    :root {
      --bg: #f7f1ea; --panel: #fffdf9; --line: #eadfdb;
      --text: #171717; --muted: #77706c; --red: #e1163f; --red-2: #c51436;
      --ink: #151515;
      --shadow: 0 18px 50px rgba(20,10,10,.08);
      --shadow-soft: 0 8px 24px rgba(20,10,10,.05);
      --radius: 22px;
      --green: #1a7a3c; --green-bg: #e9f6ee; --red-bg: #fdecea;
    }
    html, body { min-height: 100%; }
    body {
      font-family: 'Inter', ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
      color: var(--text);
      background:
        linear-gradient(180deg, rgba(255,255,255,.52), rgba(255,255,255,.52)),
        repeating-linear-gradient(0deg, #efe4dd 0 1px, var(--bg) 1px 28px);
      min-height: 100vh;
    }
    .shell { max-width: 1240px; margin: 0 auto; padding: 20px 18px 40px; }

    /* ── Top bar ── */
    .topbar {
      display: flex; align-items: center; justify-content: space-between;
      padding: 10px 6px 18px; border-bottom: 1px solid rgba(0,0,0,.08); margin-bottom: 22px;
    }
    .brand { display: flex; flex-direction: column; gap: 8px; }
    .brand-logo { max-height: 52px; max-width: 240px; display: block; }
    .tagline { font-size: 11px; letter-spacing: .32em; color: #9a8f87; text-transform: uppercase; margin-left: 2px; }
    .navlink {
      display: inline-flex; align-items: center; gap: 9px; color: var(--red);
      font-weight: 600; letter-spacing: .04em; text-transform: uppercase; font-size: 13px; text-decoration: none;
    }
    .navlink:hover { color: var(--red-2); }

    /* ── Hero ── */
    .hero { display: grid; grid-template-columns: 1.1fr .9fr; gap: 28px; align-items: center; padding: 20px 6px 30px; }
    .hero h1 {
      font-family: 'Playfair Display', serif; font-size: clamp(40px, 5vw, 68px);
      line-height: .98; margin: 0 0 16px; letter-spacing: -.03em; font-weight: 700;
    }
    .hero h1 em { color: var(--red); font-style: italic; }
    .hero p { font-size: 17px; line-height: 1.75; color: var(--muted); max-width: 520px; margin: 0; }

    .art { position: relative; min-height: 300px; display: flex; align-items: center; justify-content: center; }
    .halo {
      position: absolute; width: min(360px, 90%); aspect-ratio: 1; border-radius: 50%;
      background: radial-gradient(circle at 50% 50%, rgba(225,22,63,.16), rgba(225,22,63,.06) 35%, rgba(225,22,63,0) 70%);
      filter: blur(2px);
    }
    .envelope {
      width: min(360px, 94%); height: 240px; position: relative; transform: rotate(-3deg);
      filter: drop-shadow(0 26px 36px rgba(30,10,10,.14));
    }
    .envelope .back, .envelope .front, .envelope .paper, .envelope .seal { position: absolute; }
    .envelope .back {
      inset: 38px 34px 34px 34px;
      background: linear-gradient(145deg, rgba(225,22,63,.12), rgba(225,22,63,.03));
      border-radius: 18px; transform: skewX(-12deg);
    }
    .envelope .front {
      left: 26px; right: 26px; bottom: 18px; top: 96px; border-radius: 18px;
      background: linear-gradient(180deg, #fff, #fff7f2); border: 1px solid rgba(225,22,63,.3);
      clip-path: polygon(0 0, 50% 60%, 100% 0, 100% 100%, 0 100%);
    }
    .envelope .paper {
      left: 94px; right: 66px; top: 28px; bottom: 56px; border-radius: 14px;
      background: #fff; border: 1px solid rgba(0,0,0,.06); transform: rotate(7deg); padding: 16px 18px;
    }
    .paper .mark { font-family: 'Playfair Display', serif; font-size: 28px; line-height: 1; margin-bottom: 14px; font-weight: 700; }
    .paper .mark .red { color: var(--red); }
    .paper .pline { height: 9px; border-radius: 99px; background: #f0efec; margin: 10px 0; }
    .paper .pline.short { width: 60%; }
    .seal {
      right: 16px; bottom: 18px; width: 84px; height: 84px; border-radius: 50%;
      background: linear-gradient(180deg, #ff4966, var(--red)); display: grid; place-items: center;
      box-shadow: 0 18px 30px rgba(225,22,63,.22);
    }
    .seal span { font-size: 38px; }

    /* ── Board ── */
    .board {
      display: grid; grid-template-columns: 1.5fr 1fr; gap: 20px; align-items: start;
      background: rgba(255,255,255,.42); border: 1px solid rgba(255,255,255,.7);
      border-radius: 28px; padding: 18px; box-shadow: var(--shadow);
    }
    .board-main { display: flex; flex-direction: column; gap: 16px; }
    .board-side { display: flex; flex-direction: column; gap: 16px; position: sticky; top: 20px; }

    .card {
      background: linear-gradient(180deg, rgba(255,255,255,.9), rgba(255,255,255,.78));
      border: 1px solid rgba(235,224,220,.9); border-radius: 22px;
      box-shadow: var(--shadow-soft); padding: 20px;
    }
    .duo { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }

    .section-title {
      display: flex; align-items: center; gap: 12px; font-weight: 700;
      letter-spacing: .1em; text-transform: uppercase; font-size: 13px; margin-bottom: 16px;
    }
    .badge {
      width: 30px; height: 30px; border-radius: 50%; display: grid; place-items: center;
      background: rgba(225,22,63,.12); color: var(--red); font-weight: 800; font-size: 13px; flex-shrink: 0;
    }
    .opt { color: #9a8f87; font-weight: 600; text-transform: none; letter-spacing: 0; }

    /* ── Inputs ── */
    .input, .select {
      width: 100%; border: 1px solid #ddd4cf; background: #fff; border-radius: 12px;
      height: 48px; padding: 0 14px; font: inherit; color: var(--text); outline: none;
      box-shadow: inset 0 1px 0 rgba(255,255,255,.8);
    }
    .input::placeholder { color: #b3aaa4; }
    .input:focus, .select:focus { border-color: var(--red); box-shadow: 0 0 0 3px rgba(225,22,63,.12); }
    .label { font-size: 12px; letter-spacing: .16em; text-transform: uppercase; color: #6f6864; margin-bottom: 8px; font-weight: 700; }
    .row { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }

    /* ── Dropzone ── */
    .dropzone {
      border: 1.5px dashed #d7ccc6; background: linear-gradient(180deg, #fff, #fff9f5);
      border-radius: 18px; min-height: 150px; display: grid; place-items: center;
      text-align: center; padding: 24px; cursor: pointer; transition: .15s;
    }
    .dropzone:hover, .dropzone.drag { border-color: var(--red); background: #fff; }
    .upload-icon {
      width: 52px; height: 52px; border-radius: 16px; background: rgba(225,22,63,.08);
      display: grid; place-items: center; margin: 0 auto 12px; color: var(--red);
    }
    .dz-main { display: block; font-size: 16px; font-weight: 600; margin-bottom: 6px; }
    .dz-sub { display: block; font-size: 11px; color: #a09188; letter-spacing: .1em; text-transform: uppercase; }
    .dropzone.has-file { border-style: solid; border-color: var(--green); background: var(--green-bg); }
    .dropzone.has-file .upload-icon { background: rgba(26,122,60,.12); color: var(--green); }

    /* ── Live preview ── */
    .preview-wrap {
      display: none; margin-top: 16px; border: 1px solid var(--line); border-radius: 16px;
      overflow: hidden; background: #fff; box-shadow: var(--shadow-soft);
    }
    .preview-wrap.show { display: block; animation: slideUp .3s ease both; }
    .preview-bar { display: flex; align-items: center; gap: 9px; background: #faf3ee; border-bottom: 1px solid var(--line); padding: 9px 12px; }
    .preview-lights { display: flex; gap: 6px; flex-shrink: 0; }
    .preview-lights i { width: 11px; height: 11px; border-radius: 50%; display: block; }
    .preview-lights .r { background: #ff5f57; } .preview-lights .y { background: #febc2e; } .preview-lights .g { background: #28c840; }
    .preview-url {
      flex: 1; min-width: 0; text-align: center; font-size: 11px; letter-spacing: .04em;
      color: var(--muted); background: #fff; border: 1px solid var(--line); border-radius: 6px;
      padding: 4px 8px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }
    .preview-bar button {
      flex-shrink: 0; background: var(--ink); border: 0; color: #fff; font: inherit; font-size: 11px;
      font-weight: 600; letter-spacing: .04em; text-transform: uppercase; padding: 5px 10px; border-radius: 8px; cursor: pointer;
    }
    .preview-bar button:hover { background: var(--red); }
    .preview-stage { position: relative; background: #e8e4de; max-height: 70vh; overflow-y: auto; overflow-x: hidden; }
    .preview-frame { border: none; background: #fff; transform-origin: top left; display: block; }
    .preview-loading { padding: 22px; text-align: center; font-size: 12px; color: var(--muted); letter-spacing: .04em; }

    /* ── Fullscreen preview overlay ── */
    .pv-overlay { display: none; position: fixed; inset: 0; background: rgba(20,10,10,.82); z-index: 1000; padding: 22px; }
    .pv-overlay.show { display: flex; flex-direction: column; }
    .pv-overlay-bar { display: flex; align-items: center; gap: 9px; background: var(--panel); border: 1px solid var(--line); border-radius: 12px 12px 0 0; padding: 10px 14px; }
    .pv-overlay-frame { flex: 1; width: 100%; border: 1px solid var(--line); border-top: none; border-radius: 0 0 12px 12px; background: #fff; }
    .pv-close { flex-shrink: 0; background: var(--red); border: 0; color: #fff; font: inherit; font-size: 12px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; padding: 6px 12px; border-radius: 8px; cursor: pointer; }

    /* ── Test row ── */
    .test-wrap { display: grid; grid-template-columns: 1fr auto; gap: 12px; align-items: start; }
    .btn {
      height: 48px; border-radius: 12px; border: 0; padding: 0 18px; font: inherit; font-weight: 700;
      cursor: pointer; letter-spacing: .05em; text-transform: uppercase;
      display: inline-flex; align-items: center; justify-content: center; gap: 8px; transition: .15s;
    }
    .btn.dark { background: var(--ink); color: #fff; white-space: nowrap; }
    .btn.dark:hover:not(:disabled) { background: var(--red); }
    .btn.dark:disabled { opacity: .55; cursor: not-allowed; }
    .btn.red {
      background: linear-gradient(90deg, #ef3f53, var(--red-2)); color: #fff; width: 100%; height: 54px;
      font-size: 14px; box-shadow: 0 12px 24px rgba(225,22,63,.26); margin-top: 18px;
    }
    .btn.red:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 16px 30px rgba(225,22,63,.32); }
    .btn.red:disabled { opacity: .6; cursor: not-allowed; }
    .subtle { color: #8f817a; font-size: 13px; line-height: 1.7; margin-top: 10px; }

    /* ── When-to-send switcher ── */
    .switcher { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    .pill {
      height: 54px; border-radius: 14px; border: 1px solid #dfd4cf; background: #fff;
      display: flex; align-items: center; justify-content: center; gap: 10px; font: inherit; font-weight: 700;
      color: #6e6762; cursor: pointer; transition: .15s;
    }
    .pill:hover { border-color: rgba(225,22,63,.4); }
    .pill.active { border-color: rgba(225,22,63,.85); color: var(--red); box-shadow: inset 0 0 0 1px rgba(225,22,63,.15); }

    /* ── Summary ── */
    .summary-head { position: relative; font-weight: 800; font-size: 16px; margin-bottom: 16px; padding-bottom: 10px; }
    .summary-head::after { content: ''; position: absolute; left: 0; bottom: 0; width: 42px; height: 2px; background: var(--red); }
    .summary .item { padding: 14px 0; border-bottom: 1px solid rgba(0,0,0,.06); }
    .summary .item:last-of-type { border-bottom: 0; }
    .summary .k { font-weight: 700; margin-bottom: 4px; font-size: 14px; }
    .summary .v { color: #6f6864; line-height: 1.55; font-size: 14px; word-break: break-word; }
    .note { margin-top: 14px; padding: 14px; border: 1px solid rgba(225,22,63,.14); background: rgba(225,22,63,.04); border-radius: 16px; color: #7f5d56; font-size: 13.5px; line-height: 1.6; }

    /* ── Quick tips ── */
    .tip { display: grid; grid-template-columns: 24px 1fr; gap: 12px; align-items: start; padding: 11px 0; color: #6c655f; font-size: 14px; line-height: 1.5; }
    .tip .dot { width: 24px; height: 24px; border-radius: 8px; background: rgba(225,22,63,.10); display: grid; place-items: center; color: var(--red); font-size: 12px; }

    /* ── Result ── */
    .result { display: none; padding: 16px 18px; border-radius: 16px; font-size: 14px; line-height: 1.55; }
    .result.show { display: block; animation: slideUp .3s ease both; }
    .result.ok { background: var(--green-bg); border: 1px solid var(--green); }
    .result.err { background: var(--red-bg); border: 1px solid var(--red); }
    .result h4 { font-family: 'Playfair Display', serif; font-size: 1.05rem; margin-bottom: 6px; }
    .result.ok h4 { color: var(--green); }
    .result.err h4 { color: var(--red); }
    .result code { font-size: .85em; background: rgba(0,0,0,.06); padding: 1px 5px; border-radius: 4px; }

    .footer-link { text-align: center; margin-top: 22px; }
    .footer-link a { color: var(--red); font-weight: 700; letter-spacing: .04em; text-decoration: none; }
    .footer-link a:hover { text-decoration: underline; }

    .spinner { width: 14px; height: 14px; border: 2px solid rgba(255,255,255,.4); border-top-color: #fff; border-radius: 50%; animation: spin .7s linear infinite; display: inline-block; vertical-align: -2px; }
    @keyframes spin { to { transform: rotate(360deg); } }
    @keyframes slideUp { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: translateY(0); } }

    @media (max-width: 980px) {
      .hero, .board { grid-template-columns: 1fr; }
      .art { order: -1; }
      .board-side { position: static; }
    }
    @media (max-width: 640px) {
      .topbar { flex-direction: column; align-items: flex-start; gap: 14px; }
      .row, .test-wrap, .switcher, .duo { grid-template-columns: 1fr; }
      .shell { padding-inline: 12px; }
      .board { padding: 12px; }
      .card { padding: 16px; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <header class="topbar">
      <div class="brand">
        <img src="{{ logo_url }}" alt="Newsband" class="brand-logo"/>
        <div class="tagline">Automated Campaign Scheduling</div>
      </div>
      <a class="navlink" href="{{ url_for('dashboard_bp.dashboard') }}">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
          <rect x="3" y="3" width="7" height="7" rx="1.6"/><rect x="14" y="3" width="7" height="7" rx="1.6"/>
          <rect x="3" y="14" width="7" height="7" rx="1.6"/><rect x="14" y="14" width="7" height="7" rx="1.6"/>
        </svg>
        Dashboard
      </a>
    </header>

    <section class="hero">
      <div class="hero-copy">
        <h1>Schedule your <em>Mailchimp</em> Newsletter</h1>
        <p>Attach your newsletter exported from this software and ship it straight to your Mailchimp audience.</p>
      </div>
      <div class="art" aria-hidden="true">
        <div class="halo"></div>
        <div class="envelope">
          <div class="back"></div>
          <div class="paper">
            <div class="mark">news<span class="red">band</span></div>
            <div class="pline short"></div>
            <div class="pline"></div>
            <div class="pline short"></div>
          </div>
          <div class="front"></div>
          <div class="seal"><span>🐵</span></div>
        </div>
      </div>
    </section>

    <form id="schedule-form">
      <main class="board">
        <div class="board-main">
          <!-- 1. Newsletter file + live preview -->
          <section class="card">
            <div class="section-title"><span class="badge">1</span> Newsletter File</div>
            <label class="dropzone" id="dropzone">
              <span class="upload-icon" aria-hidden="true">
                <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M12 13V3"/><path d="m8 7 4-4 4 4"/>
                  <path d="M20 17.5a4.5 4.5 0 0 0-3-8 6 6 0 0 0-11.5 2A3.5 3.5 0 0 0 6 18.5"/>
                </svg>
              </span>
              <span class="dz-main" id="dz-text">Click or drop your ZIP / HTML file here</span>
              <span class="dz-sub" id="dz-sub">Exported from a Newsband editor</span>
              <input type="file" id="file-input" accept=".zip,.html,.htm" hidden>
            </label>

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
          </section>

          <!-- 2. Audience -->
          <section class="card">
            <div class="section-title"><span class="badge">2</span> Audience</div>
            <select id="audience" class="select" required>
              <option value="">Loading audiences…</option>
            </select>
          </section>

          <!-- 3. Subject line -->
          <section class="card">
            <div class="section-title"><span class="badge">3</span> Subject Line</div>
            <input type="text" id="subject" class="input" value="{{ default_subject }}" required>
          </section>

          <!-- 4 & 5. From name / email -->
          <div class="duo">
            <section class="card">
              <div class="section-title"><span class="badge">4</span> From Name</div>
              <input type="text" id="from_name" class="input" value="{{ default_from_name }}" required>
            </section>
            <section class="card">
              <div class="section-title"><span class="badge">5</span> From Email</div>
              <input type="email" id="from_email" class="input" value="{{ default_from_email }}" required>
            </section>
          </div>

          <!-- 6. Send a test first -->
          <section class="card">
            <div class="section-title"><span class="badge">6</span> Send a Test First <span class="opt">(optional)</span></div>
            <div class="test-wrap">
              <input type="text" id="test_email" class="input" value="manasgawde@gmail.com, contact@newsband.in" placeholder="you@example.com, teammate@example.com">
              <button type="button" class="btn dark" id="btn-test">✉ Send Test</button>
            </div>
            <div class="subtle">Delivers this exact newsletter to the address(es) above so you can review it before scheduling. Separate multiple with commas.</div>
          </section>

          <!-- 7. When to send -->
          <section class="card">
            <div class="section-title"><span class="badge">7</span> When to Send</div>
            <div class="switcher">
              <button type="button" id="btn-schedule" class="pill active">📅 Schedule</button>
              <button type="button" id="btn-now" class="pill">⚡ Send Now</button>
            </div>
            <div id="time-field">
              <div class="row" style="margin-top:14px">
                <div>
                  <div class="label">Delivery Date</div>
                  <input type="date" id="send_date" class="input" value="{{ default_send_date }}">
                </div>
                <div>
                  <div class="label">Delivery Time</div>
                  <select id="send_clock" class="select"></select>
                </div>
              </div>
              <div class="subtle">Interpreted as India Standard Time (IST). Times are sent in 15-minute intervals.</div>
            </div>
            <button type="submit" class="btn red" id="submit-btn"><span id="submit-label">📅 Schedule Campaign</span></button>
          </section>

          <div class="result" id="result"></div>
        </div>

        <aside class="board-side">
          <section class="card summary">
            <div class="summary-head">Campaign Summary</div>
            <div class="item"><div class="k">Audience</div><div class="v" id="sum-audience">—</div></div>
            <div class="item"><div class="k">Subject</div><div class="v" id="sum-subject">—</div></div>
            <div class="item"><div class="k">From</div><div class="v" id="sum-from">—</div></div>
            <div class="item"><div class="k">Test Email</div><div class="v" id="sum-test">—</div></div>
            <div class="item"><div class="k">Send On</div><div class="v" id="sum-sendon">—</div></div>
            <div class="note">You can review all details before confirming the schedule.</div>
          </section>

          <section class="card">
            <div class="summary-head">💡 Quick Tips</div>
            <div class="tip"><div class="dot">✦</div><div>Send a test email to preview your newsletter in your inbox.</div></div>
            <div class="tip"><div class="dot">✦</div><div>Double-check your subject line for better engagement.</div></div>
            <div class="tip"><div class="dot">✦</div><div>Campaign will be sent to the selected audience at the scheduled time.</div></div>
          </section>
        </aside>
      </main>
    </form>

    <div class="footer-link"><a href="{{ url_for('dashboard_bp.dashboard') }}">&#8592; Back to Dashboard</a></div>
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

    // ── Campaign Summary (live) ──
    var sumAudience = document.getElementById('sum-audience');
    var sumSubject = document.getElementById('sum-subject');
    var sumFrom = document.getElementById('sum-from');
    var sumTest = document.getElementById('sum-test');
    var sumSendon = document.getElementById('sum-sendon');
    var subjectInput = document.getElementById('subject');
    var fromNameInput = document.getElementById('from_name');
    var fromEmailInput = document.getElementById('from_email');
    var sendDateInput = document.getElementById('send_date');

    function escapeHtml(s) {
      return (s || '').replace(/[&<>"']/g, function (c) {
        return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
      });
    }
    function fmtSendOn() {
      if (sendNow) return 'Immediately — Send Now';
      var d = sendDateInput.value;
      var dd = d ? d.split('-').reverse().join('-') : '—';
      var t = clockSel.options[clockSel.selectedIndex];
      return dd + ' at ' + (t ? t.textContent : '—') + ' IST';
    }
    function updateSummary() {
      var aOpt = audienceSel.options[audienceSel.selectedIndex];
      sumAudience.textContent = (aOpt && aOpt.value) ? aOpt.textContent : '—';
      sumSubject.textContent = subjectInput.value || '—';
      var fn = fromNameInput.value || '—';
      var fe = fromEmailInput.value || '';
      sumFrom.innerHTML = escapeHtml(fn) + (fe ? '<br>' + escapeHtml(fe) : '');
      sumTest.textContent = (testEmail.value || '').trim() || '—';
      sumSendon.textContent = fmtSendOn();
    }
    [subjectInput, fromNameInput, fromEmailInput, testEmail, sendDateInput].forEach(function (el) {
      el.addEventListener('input', updateSummary);
    });
    audienceSel.addEventListener('change', updateSummary);
    clockSel.addEventListener('change', updateSummary);

    // ── Load audiences ──
    fetch('api/audiences')
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) {
        if (!res.ok) { audienceSel.innerHTML = '<option value="">⚠ ' + (res.d.error || 'Could not load audiences') + '</option>'; updateSummary(); return; }
        var want = (res.d.default_name || '').toLowerCase().replace(/[\\s_]+/g, '');
        var list = res.d.audiences || [];
        if (!list.length) { audienceSel.innerHTML = '<option value="">No audiences found</option>'; updateSummary(); return; }
        audienceSel.innerHTML = '';
        list.forEach(function (a) {
          var opt = document.createElement('option');
          opt.value = a.id;
          opt.textContent = a.name + ' (' + a.members + ' contacts)';
          var norm = (a.name || '').toLowerCase().replace(/[\\s_]+/g, '');
          if (norm === want) { opt.selected = true; DEFAULT_AUDIENCE = a.id; }
          audienceSel.appendChild(opt);
        });
        updateSummary();
      })
      .catch(function () { audienceSel.innerHTML = '<option value="">⚠ Network error loading audiences</option>'; updateSummary(); });

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
      updateSummary();
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

    // ── Initial summary render ──
    updateSummary();
  })();
  </script>
</body>
</html>"""
