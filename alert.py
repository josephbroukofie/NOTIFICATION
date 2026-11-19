try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
FEED_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
STATE_FILE = "sent.json"

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
LEAD_MINUTES = int(os.getenv("LEAD_MINUTES", "30"))
LOCAL_TZ = ZoneInfo(os.getenv("LOCAL_TZ", "Africa/Accra"))
# Optional filter, e.g. "USD,EUR,GBP". Empty = all currencies.
CURRENCIES = {c.strip().upper() for c in os.getenv("CURRENCIES", "").split(",") if c.strip()}


def http_get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def send_telegram(text):
    data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text}).encode()
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        with urllib.request.urlopen(url, data=data, timeout=30) as r:
            r.read()
    except urllib.error.HTTPError as e:
        print("Telegram error:", e.code, e.read().decode())
        raise


def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state, now):
    # Drop entries older than 10 days so the file stays small
    cutoff = (now - timedelta(days=10)).isoformat()
    state = {k: v for k, v in state.items() if v >= cutoff}
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, sort_keys=True)


def main():
    if "--test" in sys.argv:
        send_telegram("✅ Forex news alert bot is connected and working.")
        return

    now = datetime.now(timezone.utc)
    window_end = now + timedelta(minutes=LEAD_MINUTES)
    state = load_state()

    events = http_get_json(FEED_URL)

    # Group upcoming high-impact events by release time
    groups = {}
    for e in events:
        if e.get("impact") != "High":
            continue
        if CURRENCIES and e.get("country", "").upper() not in CURRENCIES:
            continue
        when = datetime.fromisoformat(e["date"]).astimezone(timezone.utc)
        if not (now < when <= window_end):
            continue
        key = f'{e["country"]}|{e["title"]}|{e["date"]}'
        if key in state:
            continue
        groups.setdefault(when, []).append((key, e))

    for when in sorted(groups):
        local = when.astimezone(LOCAL_TZ)
        mins = max(1, int((when - now).total_seconds() // 60))
        lines = [
            f"🔴 HIGH IMPACT NEWS in ~{mins} min",
            f"🕒 {local.strftime('%a %d %b, %H:%M')} ({local.tzname()})",
            "",
        ]
        for _, e in groups[when]:
            line = f"• {e['country']} – {e['title']}"
            extra = []
            if e.get("forecast"):
                extra.append(f"Forecast: {e['forecast']}")
            if e.get("previous"):
                extra.append(f"Previous: {e['previous']}")
            if extra:
                line += "\n   " + " | ".join(extra)
            lines.append(line)
        lines += ["", "Prepare. Watch spreads and volatility."]

        send_telegram("\n".join(lines))
        for key, _ in groups[when]:
            state[key] = now.isoformat()

    save_state(state, now)


if __name__ == "__main__":
    main()
