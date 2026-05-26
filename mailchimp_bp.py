import os
import time
from datetime import datetime, timezone, timedelta
from flask import Blueprint, render_template, jsonify, request
import requests
from helpers import require_login

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

mailchimp_bp = Blueprint('mailchimp_bp', __name__)

_cache = {}
_CACHE_TTL = 300  # 5-minute TTL


def _api_config():
    api_key = os.environ.get("MAILCHIMP_API_KEY", "")
    if not api_key:
        raise RuntimeError("MAILCHIMP_API_KEY environment variable is not set.")
    server = api_key.split("-")[-1]
    return f"https://{server}.api.mailchimp.com/3.0", {"Authorization": f"Bearer {api_key}"}


def _get_campaigns(base_url, headers, date):
    campaigns, offset, limit = [], 0, 100
    while True:
        r = requests.get(
            f"{base_url}/campaigns",
            headers=headers,
            params={
                "count": limit,
                "offset": offset,
                "status": "sent",
                "since_send_time": f"{date}T00:00:00+00:00",
                "before_send_time": f"{date}T23:59:59+00:00",
            },
            timeout=20,
        )
        r.raise_for_status()
        batch = r.json().get("campaigns", [])
        campaigns.extend(batch)
        if len(batch) < limit:
            break
        offset += limit
    return campaigns


def _get_report(base_url, headers, cid):
    r = requests.get(f"{base_url}/reports/{cid}", headers=headers, timeout=20)
    r.raise_for_status()
    return r.json()


def _get_unsub_count(base_url, headers, cid):
    count, offset, limit = 0, 0, 1000
    while True:
        r = requests.get(
            f"{base_url}/reports/{cid}/unsubscribed",
            headers=headers,
            params={"count": limit, "offset": offset},
            timeout=20,
        )
        r.raise_for_status()
        batch = r.json().get("unsubscribes", [])
        count += len(batch)
        if len(batch) < limit:
            break
        offset += limit
    return count


def _pct(part, total):
    return round(part / total * 100, 2) if total else 0.0


def _build_stats(date):
    base_url, headers = _api_config()
    campaigns_raw = _get_campaigns(base_url, headers, date)
    result = []
    totals = {"sent": 0, "opens": 0, "clicks": 0, "bounces": 0, "unsubscribes": 0}

    for c in campaigns_raw:
        rpt = _get_report(base_url, headers, c["id"])
        sent = rpt.get("emails_sent", 0)
        opens = rpt.get("opens", {}).get("opens_total", 0)
        clicks = rpt.get("clicks", {}).get("clicks_total", 0)
        b = rpt.get("bounces", {})
        bounces = b.get("hard_bounces", 0) + b.get("soft_bounces", 0)
        unsubs = _get_unsub_count(base_url, headers, c["id"])

        totals["sent"] += sent
        totals["opens"] += opens
        totals["clicks"] += clicks
        totals["bounces"] += bounces
        totals["unsubscribes"] += unsubs

        result.append({
            "id": c["id"],
            "title": c.get("settings", {}).get("title", ""),
            "subject": c.get("settings", {}).get("subject_line", ""),
            "send_time": c.get("send_time", ""),
            "emails_sent": sent,
            "opens": opens,
            "clicks": clicks,
            "bounces": bounces,
            "unsubscribes": unsubs,
            "open_rate": _pct(opens, sent),
            "click_rate": _pct(clicks, sent),
            "bounce_rate": _pct(bounces, sent),
            "unsub_rate": _pct(unsubs, sent),
        })

    s = totals["sent"]
    totals.update({
        "open_rate": _pct(totals["opens"], s),
        "click_rate": _pct(totals["clicks"], s),
        "bounce_rate": _pct(totals["bounces"], s),
        "unsub_rate": _pct(totals["unsubscribes"], s),
    })
    return result, totals


@mailchimp_bp.route("/")
@require_login
def index():
    return render_template("mailchimp_dashboard.html")


@mailchimp_bp.route("/api/stats")
@require_login
def api_stats():
    now = datetime.now(timezone.utc)
    requested = request.args.get("date")
    dates = [requested] if requested else [
        now.strftime("%Y-%m-%d"),
        (now - timedelta(days=1)).strftime("%Y-%m-%d"),
        (now - timedelta(days=2)).strftime("%Y-%m-%d"),
    ]

    for date in dates:
        entry = _cache.get(date)
        if entry and (time.time() - entry["ts"]) < _CACHE_TTL:
            return jsonify(entry["data"])

        try:
            campaigns, totals = _build_stats(date)
        except RuntimeError as e:
            return jsonify({"error": str(e)}), 500
        except requests.RequestException as e:
            return jsonify({"error": f"Mailchimp API error: {e}"}), 502

        if campaigns or requested:
            payload = {"report_date": date, "campaigns": campaigns, "totals": totals}
            _cache[date] = {"data": payload, "ts": time.time()}
            return jsonify(payload)

    return jsonify({
        "report_date": None,
        "campaigns": [],
        "totals": {
            "sent": 0, "opens": 0, "clicks": 0, "bounces": 0, "unsubscribes": 0,
            "open_rate": 0, "click_rate": 0, "bounce_rate": 0, "unsub_rate": 0,
        },
        "empty": True,
        "checked_dates": dates,
    })
