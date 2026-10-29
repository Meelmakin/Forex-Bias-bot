"""Sends a Telegram alert ~1 hour before each high-impact economic-calendar
event, using Forex Factory's free public weekly calendar feed.

Reuses the same Telegram bot/chat as bias_bot.py.

Env vars:
    TELEGRAM_TOKEN, CHAT_ID        (required - same ones bias_bot.py uses)
    NEWS_CURRENCIES                 comma list, default: the 8 majors
    NEWS_LEAD_MINUTES               default 60 ("in 1 hour")
    NEWS_WINDOW_MINUTES             default 20 - the catch-window around the
                                     lead time, wide enough that a 15-minute
                                     check cadence can't skip an event
    NEWS_TZ                         IANA zone for the displayed times,
                                     default Africa/Lagos (WAT)

State: state/sent_news_alerts.json, keyed by the event's exact timestamp,
so the same event is never alerted twice even though several runs will see
it inside the catch-window.
"""
import json
import os
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests

CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
STATE_FILE = "state/sent_news_alerts.json"

LEAD_MINUTES = int(os.environ.get("NEWS_LEAD_MINUTES", "60"))
WINDOW_MINUTES = int(os.environ.get("NEWS_WINDOW_MINUTES", "20"))
CURRENCIES = {
    c.strip().upper()
    for c in os.environ.get("NEWS_CURRENCIES", "USD,EUR,GBP,JPY,AUD,NZD,CAD,CHF").split(",")
    if c.strip()
}
TZ_NAME = os.environ.get("NEWS_TZ", "Africa/Lagos")
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]


def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}


def save_state(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, sort_keys=True)


def fetch_calendar() -> list:
    resp = requests.get(CALENDAR_URL, timeout=20)
    resp.raise_for_status()
    return resp.json()


def send_message(text: str) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    resp = requests.post(
        url, data={"chat_id": CHAT_ID, "text": text, "disable_web_page_preview": True}, timeout=15
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Telegram send failed ({resp.status_code}): {resp.text}")


def fmt_event_time(dt: datetime, tz: ZoneInfo) -> str:
    return dt.astimezone(tz).strftime("%a %d %b, %H:%M")


def fmt_sent_time(dt: datetime, tz: ZoneInfo) -> str:
    local = dt.astimezone(tz)
    return f"{local.strftime('%d %b, %-I:%M %p')} {local.strftime('%Z')}"


def build_groups(events: list, now: datetime) -> dict:
    """Groups same-time High-impact events (in our currency list) that fall
    inside the catch-window around now + LEAD_MINUTES."""
    low = LEAD_MINUTES - WINDOW_MINUTES / 2
    high = LEAD_MINUTES + WINDOW_MINUTES / 2
    groups = {}

    for e in events:
        if e.get("impact") != "High":
            continue
        ccy = (e.get("country") or "").upper()
        if CURRENCIES and ccy not in CURRENCIES:
            continue
        try:
            event_time = datetime.fromisoformat(e["date"])
        except (KeyError, ValueError, TypeError):
            continue
        if event_time.tzinfo is None:
            event_time = event_time.replace(tzinfo=timezone.utc)

        minutes_until = (event_time - now).total_seconds() / 60
        if not (low <= minutes_until <= high):
            continue

        key = event_time.isoformat()
        groups.setdefault(key, {"time": event_time, "events": []})
        groups[key]["events"].append((ccy, (e.get("title") or "").strip()))

    return groups


def main() -> None:
    tz = ZoneInfo(TZ_NAME)
    now = datetime.now(timezone.utc)
    state = load_state()

    try:
        events = fetch_calendar()
    except Exception as exc:
        print(f"Failed to fetch calendar: {exc}", file=sys.stderr)
        return

    # Diagnostic: list every High-impact event in the fetched calendar,
    # regardless of currency filter or timing window, so a mismatch against
    # another bot's alerts is easy to spot.
    all_high = [e for e in events if e.get("impact") == "High"]
    print(f"All High-impact events in this week's feed ({len(all_high)}):")
    for e in all_high:
        try:
            et = datetime.fromisoformat(e["date"])
        except (KeyError, ValueError, TypeError):
            et = None
        et_str = et.astimezone(tz).strftime("%a %d %b, %H:%M") if et else "unparseable date"
        mins = f"{(et - now).total_seconds() / 60:+.0f} min" if et else "n/a"
        print(f"  {et_str} ({mins})  {e.get('country')}: {e.get('title')}")

    groups = build_groups(events, now)
    sent_count = 0

    for key, group in groups.items():
        if state.get(key):
            continue

        hours = LEAD_MINUTES / 60
        label = f"{hours:g} hour" + ("s" if hours != 1 else "")
        lines = [f"High-impact news in {label}", fmt_event_time(group["time"], tz)]
        for ccy, title in group["events"]:
            lines.append(f"{ccy}: {title}")
        lines.append("")
        lines.append(f"Sent {fmt_sent_time(now, tz)}")

        try:
            send_message("\n".join(lines))
            state[key] = True
            sent_count += 1
            print(f"Sent: {key} -> {[t for _, t in group['events']]}")
        except Exception as exc:
            print(f"Telegram send failed for {key}: {exc}", file=sys.stderr)

    save_state(state)
    print(f"Run complete. {sent_count} alert(s) sent, {len(groups)} group(s) in window, "
          f"{len(events)} total calendar events fetched.")


if __name__ == "__main__":
    main()
