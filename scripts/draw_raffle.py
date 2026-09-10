#!/usr/bin/env python3
"""
Keystone Clash 50/50 draw — commit and reveal.

Two steps, run from the Actions tab:

  commit   Freeze the entry list. Reads every succeeded payment from Zeffy,
           assigns ticket numbers in a deterministic order, publishes the
           list with no personal data, and records a SHA-256 of it plus the
           drand round the draw will use. That round is in the future, so
           nobody — including us — can know the result yet.

  draw     Fetch that round's randomness, derive the winning ticket, publish
           it. Anyone can rerun scripts/verify_draw.py and land on the same
           ticket.

Environment: ZEFFY_API_KEY (read-only), and the same optional overrides
used by update_raffle.py.
"""

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

ZEFFY = "https://api.zeffy.com/api/v1"
DRAND = "https://api.drand.sh"
UA = "KeystoneClash-RaffleBot/1.0 (+https://github.com/TheDr21/KeystoneClash)"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data.json")
ENTRIES = os.path.join(ROOT, "raffle-entries.json")

KEY = os.environ.get("ZEFFY_API_KEY", "").strip()
MATCH = os.environ.get("ZEFFY_CAMPAIGN_MATCH", "raffle").strip().lower()
CAMPAIGN_ID = os.environ.get("ZEFFY_CAMPAIGN_ID", "").strip()

# Bundles: map a Zeffy rate title to how many entries it grants.
# "$50 for 10 entries" -> {"Ten chances of winning": 10}
RATES = json.loads(os.environ.get("ZEFFY_RATE_ENTRIES", "{}"))


# Diagnostics only — this script never prints payment or buyer data.
_log = []


def note(m):
    print(m)
    _log.append(str(m))


def flush():
    try:
        with open(os.path.join(ROOT, "draw-debug.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(_log) + "\n")
    except Exception:
        pass


def die(msg):
    note(f"ERROR: {msg}")
    flush()
    sys.exit(1)


def get(url):
    req = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": UA}
    )
    if url.startswith(ZEFFY):
        req.add_header("Authorization", f"Bearer {KEY}")
    note(f"GET {url}")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", "replace")
            note(f"  {r.status}, {len(body)} bytes")
            if "drand" in url:
                note("  " + body[:400])
            return json.loads(body)
    except urllib.error.HTTPError as e:
        die(f"HTTP {e.code} from {url}: {e.read().decode('utf-8','replace')[:300]}")
    except urllib.error.URLError as e:
        die(f"could not reach {url}: {e.reason}")


def as_list(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for k in ("data", "items", "results"):
            if isinstance(payload.get(k), list):
                return payload[k]
    return []


def load(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False, sort_keys=False)
        f.write("\n")


# --------------------------------------------------------------------------
# entries
# --------------------------------------------------------------------------

def campaign_id():
    if CAMPAIGN_ID:
        return CAMPAIGN_ID
    for c in as_list(get(ZEFFY + "/campaigns")):
        if MATCH in str(c.get("title") or "").lower():
            return c["id"]
    die(f"no campaign title contains {MATCH!r}")


def fetch_payments(cid):
    """Every succeeded, unrefunded payment for this campaign, oldest first."""
    out, after = [], None
    for _ in range(20):
        url = ZEFFY + "/payments?limit=100" + (f"&starting_after={after}" if after else "")
        payload = get(url)
        rows = as_list(payload)
        if not rows:
            break
        for p in rows:
            if p.get("campaign_id") != cid or p.get("status") != "succeeded":
                continue
            if p.get("refund_status") not in (None, "none"):
                continue
            out.append(p)
        after = rows[-1].get("id")
        if len(rows) < 100:
            break
    # Deterministic order: creation time, then id as the tiebreak.
    out.sort(key=lambda p: (p.get("created", 0), p.get("id", "")))
    return out


def entries_for(payment):
    """How many raffle entries this payment bought."""
    n = 0
    for item in payment.get("items") or []:
        if item.get("type") != "ticket":
            continue
        qty = item.get("quantity") or 1
        per = RATES.get(item.get("rate_title") or "", 1)
        n += qty * per
    return n or 1        # never silently drop a paying buyer


def build_entries(payments):
    """Ticket numbers only. No name, no email, nothing identifying."""
    tickets, ticket_no = [], 0
    for p in payments:
        count = entries_for(p)
        # Buyers verify their own tickets against the payment id on their
        # Zeffy receipt. Hashing keeps the raw id off a public page.
        ref = hashlib.sha256(p["id"].encode()).hexdigest()[:12]
        first = ticket_no + 1
        ticket_no += count
        tickets.append({"ref": ref, "from": first, "to": ticket_no})
    return tickets, ticket_no


def commitment(tickets, total):
    """SHA-256 over a canonical rendering of the frozen entry list."""
    canon = json.dumps({"tickets": tickets, "total": total},
                       sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode()).hexdigest()


# --------------------------------------------------------------------------
# drand
# --------------------------------------------------------------------------

def chain_info():
    info = get(DRAND + "/info")
    return info["hash"], int(info["genesis_time"]), int(info["period"])


def round_at(ts, genesis, period):
    if ts <= genesis:
        return 1
    return ((ts - genesis) // period) + 1


def beacon(rnd):
    return get(f"{DRAND}/public/{rnd}")


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def cmd_commit(args):
    if not KEY:
        die("ZEFFY_API_KEY is not set.")
    cid = campaign_id()
    payments = fetch_payments(cid)
    if not payments:
        die("no succeeded payments — nothing to draw.")

    tickets, total = build_entries(payments)
    digest = commitment(tickets, total)

    chash, genesis, period = chain_info()
    draw_at = datetime.fromisoformat(args.draw_at)
    if draw_at.tzinfo is None:
        die("--draw-at needs a timezone offset, e.g. 2026-09-13T18:00:00-04:00")
    target = round_at(int(draw_at.timestamp()), genesis, period)

    now_round = round_at(int(datetime.now(timezone.utc).timestamp()), genesis, period)
    if target <= now_round:
        die(f"draw round {target} is not in the future (current {now_round}). "
            "Pick a later --draw-at.")

    save(ENTRIES, {
        "note": "Frozen entry list. Ticket numbers only, no personal data. "
                "'ref' is the first 12 hex of SHA-256 of the Zeffy payment id "
                "on your receipt.",
        "total_tickets": total,
        "tickets": tickets,
    })

    data = load(DATA, {})
    data["draw"] = {
        "status": "committed",
        "buyers": len(payments),
        "total_tickets": total,
        "commitment": digest,
        "committed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "beacon": {"chain": chash, "round": target,
                   "draw_at": draw_at.isoformat()},
        "winning_ticket": None,
    }
    save(DATA, data)

    flush()
    print(f"Committed {total} tickets across {len(payments)} buyer(s).")
    print(f"  commitment  {digest}")
    print(f"  drand round {target}  (available {draw_at.isoformat()})")


def cmd_draw(args):
    data = load(DATA, {})
    d = data.get("draw") or {}
    if d.get("status") != "committed":
        die(f"draw status is {d.get('status')!r}, expected 'committed'.")

    entries = load(ENTRIES)
    if not entries:
        die("raffle-entries.json is missing.")

    # The published list must still hash to what we committed.
    recomputed = commitment(entries["tickets"], entries["total_tickets"])
    if recomputed != d["commitment"]:
        die("entry list no longer matches the commitment. Refusing to draw.")

    rnd = d["beacon"]["round"]
    b = beacon(rnd)
    randomness = b.get("randomness") or b.get("signature")
    if not randomness:
        die(f"drand round {rnd} returned no randomness field.")

    total = entries["total_tickets"]
    seed = hashlib.sha256((d["commitment"] + randomness).encode()).hexdigest()
    winning = (int(seed, 16) % total) + 1

    holder = next((t for t in entries["tickets"]
                   if t["from"] <= winning <= t["to"]), None)

    d.update({
        "status": "drawn",
        "winning_ticket": winning,
        "winning_ref": holder["ref"] if holder else None,
        "beacon": {**d["beacon"], "randomness": randomness},
        "seed": seed,
        "drawn_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    data["draw"] = d
    save(DATA, data)

    print(f"Round {rnd} randomness {randomness}")
    print(f"Winning ticket {winning} of {total}  (ref {d['winning_ref']})")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("commit", help="freeze the entry list")
    c.add_argument("--draw-at", required=True,
                   help="when the draw happens, ISO 8601 with offset")
    c.set_defaults(fn=cmd_commit)

    d = sub.add_parser("draw", help="reveal the winner")
    d.set_defaults(fn=cmd_draw)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
