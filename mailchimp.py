import os
import requests
from datetime import datetime, timezone, timedelta

API_KEY = os.environ.get("MAILCHIMP_API_KEY", "")
SERVER_PREFIX = API_KEY.split("-")[-1] if API_KEY else ""
BASE_URL = f"https://{SERVER_PREFIX}.api.mailchimp.com/3.0"
HEADERS = {"Authorization": f"Bearer {API_KEY}"}

NOW = datetime.now(timezone.utc)
TODAY = NOW.strftime("%Y-%m-%d")
YESTERDAY = (NOW - timedelta(days=1)).strftime("%Y-%m-%d")
DAY_BEFORE_YESTERDAY = (NOW - timedelta(days=2)).strftime("%Y-%m-%d")

def get_all_campaigns(date):
    campaigns = []
    offset = 0
    limit = 100
    while True:
        r = requests.get(
            f"{BASE_URL}/campaigns",
            headers=HEADERS,
            params={
                "count": limit,
                "offset": offset,
                "status": "sent",
                "since_send_time": f"{date}T00:00:00+00:00",
                "before_send_time": f"{date}T23:59:59+00:00",
            }
        )
        r.raise_for_status()
        data = r.json()
        batch = data.get("campaigns", [])
        campaigns.extend(batch)
        if len(batch) < limit:
            break
        offset += limit
    return campaigns

def get_report(campaign_id):
    r = requests.get(f"{BASE_URL}/reports/{campaign_id}", headers=HEADERS)
    r.raise_for_status()
    return r.json()

def get_unsubscribe_count(campaign_id):
    count = 0
    offset = 0
    limit = 1000
    while True:
        r = requests.get(
            f"{BASE_URL}/reports/{campaign_id}/unsubscribed",
            headers=HEADERS,
            params={"count": limit, "offset": offset}
        )
        r.raise_for_status()
        data = r.json()
        batch = data.get("unsubscribes", [])
        count += len(batch)
        if len(batch) < limit:
            break
        offset += limit
    return count

def main():
    all_campaigns = get_all_campaigns(TODAY)
    report_date = TODAY

    if not all_campaigns:
        all_campaigns = get_all_campaigns(YESTERDAY)
        report_date = YESTERDAY

    if not all_campaigns:
        all_campaigns = get_all_campaigns(DAY_BEFORE_YESTERDAY)
        report_date = DAY_BEFORE_YESTERDAY

    if not all_campaigns:
        print(f"No campaigns sent on {TODAY}, {YESTERDAY}, or {DAY_BEFORE_YESTERDAY}.")
        return

    total_sent        = 0
    total_opens       = 0
    total_clicks      = 0
    total_bounces     = 0
    total_unsubscribes = 0

    for camp in all_campaigns:
        report = get_report(camp["id"])
        total_sent         += report.get("emails_sent", 0)
        total_opens        += report.get("opens", {}).get("opens_total", 0)
        total_clicks       += report.get("clicks", {}).get("clicks_total", 0)
        bounces             = report.get("bounces", {})
        total_bounces      += bounces.get("hard_bounces", 0) + bounces.get("soft_bounces", 0)
        total_unsubscribes += get_unsubscribe_count(camp["id"])

    print(f"Campaigns sent on {report_date}:\n")
    print(f"Total mails sent:    {total_sent}")
    print(f"Total mails opened:  {total_opens}")
    print(f"Total mails clicked: {total_clicks}")
    print(f"Total mails bounced: {total_bounces}")
    print(f"Unsubscribers:       {total_unsubscribes}")

if __name__ == "__main__":
    main()
