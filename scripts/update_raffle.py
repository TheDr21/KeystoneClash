#!/usr/bin/env python3
"""
Pull the 50/50 running total from the Zeffy API and write it into data.json.

Run by .github/workflows/raffle.yml on a schedule. Nothing here touches the
browser, so the API key never leaves GitHub.

Environment:
  ZEFFY_API_KEY        required. Settings -> Integrations in Zeffy. Read-only.
  ZEFFY_CAMPAIGN_ID    optional. Exact campaign id. Skips name matching.
  ZEFFY_CAMPAIGN_MATCH optional. Substring to match a campaign title.
                       Default "raffle".
  ZEFFY_AMOUNT_IN_CENTS optional. Set to "1" if the API returns cents.
  ZEFFY_RAISED_FIELD   optional. Exact field name holding the total, if the
                       automatic search picks the wrong one.
"""

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

API = "https://api.zeffy.com/api/v1"
DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "data.json")

KEY = os.environ.get("ZEFFY_API_KEY", "").strip()
CAMPAIGN_ID = os.environ.get("ZEFFY_CAMPAIGN_ID", "").strip()
MATCH = os.environ.get("ZEFFY_CAMPAIGN_MATCH", "raffle").strip().lower()
IN_CENTS = os.environ.get("ZEFFY_AMOUNT_IN_CENTS", "").strip() in ("1", "true", "yes")
FIELD = os.environ.get("ZEFFY_RAISED_FIELD", "").strip()

# Field names Zeffy might use for "how much has been raised". The first match
# in this list wins; override with ZEFFY_RAISED_FIELD if it guesses wrong.
AMOUNT_KEYS = (
    "amountraised", "totalraised", "raised", "raisedamount",
    "amountcollected", "totalcollected", "collected",
    "totalamount", "amount",
)


DEBUG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "raffle-debug.txt")
_notes = []


def note(msg):
    print(msg)
    _notes.append(str(msg))


def flush_debug():
    try:
        with open(DEBUG, "w", encoding="utf-8") as f:
            f.write("\n".join(_notes) + "\n")
    except Exception:
        pass


def die(msg):
    note(f"ERROR: {msg}")
    flush_debug()
    sys.exit(1)


AUTH_STYLE = os.environ.get("ZEFFY_AUTH_STYLE", "bearer").strip().lower()


def auth_header():
    if AUTH_STYLE == "raw":
        return {"Authorization": KEY}
    if AUTH_STYLE == "apikey":
        return {"X-Api-Key": KEY}
    return {"Authorization": f"Bearer {KEY}"}


UA = ("KeystoneClash-RaffleBot/1.0 "
      "(+https://github.com/TheDr21/KeystoneClash)")


def get(path):
    h = {"Accept": "application/json", "User-Agent": UA}
    h.update(auth_header())
    req = urllib.request.Request(API + path, headers=h)
    note(f"GET {API}{path}  (auth style: {AUTH_STYLE})")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", "replace")
            note(f"  {r.status}, {len(body)} bytes")
            note("  body head: " + body[:900])
            return json.loads(body)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:900]
        die(f"HTTP {e.code} from {path}: {body}")
    except urllib.error.URLError as e:
        die(f"could not reach Zeffy: {e.reason}")


def as_list(payload):
    """Zeffy may return a bare list or wrap it in data/items/results."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for k in ("data", "items", "results", "campaigns"):
            if isinstance(payload.get(k), list):
                return payload[k]
    return []


def norm(k):
    return k.lower().replace("_", "").replace("-", "")


def find_amount(obj, depth=0):
    """Depth-first search for a plausible raised-amount number."""
    if depth > 6:
        return None
    if isinstance(obj, dict):
        if FIELD:
            for k, v in obj.items():
                if k == FIELD and isinstance(v, (int, float)):
                    return float(v), k
        else:
            for want in AMOUNT_KEYS:
                for k, v in obj.items():
                    if norm(k) == want and isinstance(v, (int, float)):
                        return float(v), k
        for v in obj.values():
            hit = find_amount(v, depth + 1)
            if hit:
                return hit
    elif isinstance(obj, list):
        for v in obj:
            hit = find_amount(v, depth + 1)
            if hit:
                return hit
    return None


def pick_campaign():
    campaigns = as_list(get("/campaigns"))
    if not campaigns:
        die("no campaigns returned. Check the API key's organization.")

    note(f"Found {len(campaigns)} campaign(s).")
    for c in campaigns:
        cid = c.get("id") or c.get("campaignId") or "?"
        title = c.get("title") or c.get("name") or "(untitled)"
        note(f"  {cid}  {title}")

    if CAMPAIGN_ID:
        for c in campaigns:
            if str(c.get("id") or c.get("campaignId")) == CAMPAIGN_ID:
                return c
        die(f"campaign id {CAMPAIGN_ID} not in the list above.")

    hits = [c for c in campaigns
            if MATCH in str(c.get("title") or c.get("name") or "").lower()]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        die(f"no campaign title contains {MATCH!r}. "
            f"Set ZEFFY_CAMPAIGN_ID to one of the ids above.")
    die(f"{len(hits)} campaigns match {MATCH!r}. Set ZEFFY_CAMPAIGN_ID.")


def main():
    if not KEY:
        die("ZEFFY_API_KEY is not set.")

    campaign = pick_campaign()
    title = campaign.get("title") or campaign.get("name") or "(untitled)"
    note(f"\nUsing campaign: {title}")
    note("Raw campaign payload:")
    note(json.dumps(campaign, indent=2)[:2500])

    # Cross-check against actual payments before trusting a campaign field.
    try:
        pay = get("/payments?limit=100")
        note("\nPAYMENTS PROBE:")
        rows = as_list(pay)
        note(f"  {len(rows)} payment(s) returned")
        for p in rows[:3]:
            note("  " + json.dumps(p, indent=2)[:1200])
    except SystemExit:
        note("  payments probe failed (see error above)")

    hit = find_amount(campaign)
    if not hit:
        die("could not find a raised-amount field. Look at the payload above "
            "and set ZEFFY_RAISED_FIELD to the right key name.")

    raised, key = hit
    if IN_CENTS:
        raised = raised / 100.0
    raised = round(raised, 2)
    note(f"\nRaised = {raised} (from field {key!r}, "
         f"cents mode {'on' if IN_CENTS else 'off'})")

    with open(DATA, encoding="utf-8") as f:
        data = json.load(f)

    prev = (data.get("raffle") or {}).get("raised")
    data["raffle"] = {
        "raised": raised,
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "url": (data.get("raffle") or {}).get(
            "url", "https://www.zeffy.com/en-US/ticketing/"
                   "lady-dukes-keystone-clash-tournament-raffle"),
    }

    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")

    note(f"data.json written. Previous {prev}, now {raised}.")
    flush_debug()


if __name__ == "__main__":
    main()
