#!/usr/bin/env python3
"""
Verify the Keystone Clash 50/50 draw. No API key, no account, no trust in us.

    python3 scripts/verify_draw.py

It re-reads the two published files, re-fetches the drand round from a
third-party beacon we don't control, and recomputes the winning ticket. If
the entry list had been altered after the commitment was published, the
hash check below fails.

Check your own ticket: your Zeffy receipt has a payment id. Run

    python3 -c "import hashlib,sys;print(hashlib.sha256(sys.argv[1].encode()).hexdigest()[:12])" YOUR-PAYMENT-ID

and find that 'ref' in raffle-entries.json to see your ticket range.
"""

import hashlib
import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DRAND = "https://api.drand.sh"


def read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return json.load(f)


def main():
    d = read("data.json").get("draw") or {}
    entries = read("raffle-entries.json")

    if d.get("status") != "drawn":
        print(f"Draw has not happened yet (status: {d.get('status')}).")
        return 0

    ok = True

    # 1. Does the published entry list still match the published commitment?
    canon = json.dumps({"tickets": entries["tickets"],
                        "total": entries["total_tickets"]},
                       sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canon.encode()).hexdigest()
    match = digest == d["commitment"]
    ok &= match
    print(f"[{'ok ' if match else 'BAD'}] entry list matches commitment")
    print(f"      published  {d['commitment']}")
    print(f"      recomputed {digest}")

    # 2. Does the randomness really come from that drand round?
    rnd = d["beacon"]["round"]
    with urllib.request.urlopen(f"{DRAND}/public/{rnd}", timeout=30) as r:
        live = json.load(r)
    live_rand = live.get("randomness") or live.get("signature")
    same = live_rand == d["beacon"]["randomness"]
    ok &= same
    print(f"[{'ok ' if same else 'BAD'}] drand round {rnd} randomness matches")

    # 3. Does that randomness actually produce the announced ticket?
    seed = hashlib.sha256((d["commitment"] + live_rand).encode()).hexdigest()
    winning = (int(seed, 16) % entries["total_tickets"]) + 1
    right = winning == d["winning_ticket"]
    ok &= right
    print(f"[{'ok ' if right else 'BAD'}] winning ticket recomputes")
    print(f"      published  {d['winning_ticket']}")
    print(f"      recomputed {winning} of {entries['total_tickets']}")

    print("\nVERIFIED" if ok else "\nVERIFICATION FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
