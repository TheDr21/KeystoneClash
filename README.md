# Keystone Clash

Public standings, team links and stat leaders for the **Keystone Clash**
(September 11–13, 2026 · East End Park, McDonald PA), hosted by the
Lady Dukes Softball Club.

Live at **https://thedr21.github.io/KeystoneClash/**

## Files

| File | What it is |
|---|---|
| `index.html` | The whole page. No build step, no dependencies. |
| `data.json` | Everything that changes during the weekend. |
| `coaches-packet.pdf` | Two-page coaches packet: location, parking, rules, tie breakers. |
| `parking-map.png` | Annotated aerial of East End Park, shown in the Tournament info tab. |
| `raffle-qr.png` | QR for the 50/50 ticket page. |
| `scripts/update_raffle.py` | Reads the 50/50 total from the Zeffy API. |
| `.github/workflows/raffle.yml` | Runs that script every 30 minutes. |
| `draw.html` | Public draw result and verification page. |
| `scripts/draw_raffle.py` | Freezes the entry list, then draws the winner. |
| `scripts/verify_draw.py` | Anyone can run this to check the result. |
| `.github/workflows/draw.yml` | Manual only. Never runs on a timer. |

`index.html` fetches `data.json` on load. If that fetch fails it falls back to an
identical object inlined near the bottom of the HTML, so the page never renders
empty. **During the tournament you only need to edit and push `data.json`.**

## Updating during the weekend

Edit `data.json` and commit. GitHub Pages redeploys in under a minute.

### Records

Each team object takes:

```json
{ "name": "Pittsburgh Passion", "gc": "https://web.gc.com/teams/...",
  "w": 2, "l": 1, "t": 0, "rf": 19, "ra": 11 }
```

- `w` / `l` / `t` — wins, losses, ties
- `rf` / `ra` — runs scored, runs allowed
- `host: true` — optional, flags a Lady Dukes team

Standings sort by record, then fewest runs allowed, then run differential, then
runs scored — matching the printed tie breakers. Head-to-head cannot be derived
from a records table, so the page states that the TD applies it and that the
posted order may change.

### Stat leaders

Empty arrays render an "on the way" panel. Fill them and the tables appear:

```json
"leaders": {
  "hitting":  [{ "player": "", "team": "", "avg": ".545", "ops": "1.410", "h": 6, "rbi": 5 }],
  "pitching": [{ "player": "", "team": "", "era": "1.75", "ip": "8.0", "k": 14 }]
}
```

Rows render in the order given — sort before writing the file.

### Status line

`status` is the sentence under the masthead. Change it as the weekend moves:

- Friday AM — "Soft launch. Pools and team links are set…"
- Saturday AM — "Pool play resumes at 9:00. Bracket seeds post early afternoon."
- Saturday PM — "Seeds are final. Bracket play is underway."

Also bump `updated` (`YYYY-MM-DD`) so the timestamp is honest.

## Setup

Settings → Pages → Source: **Deploy from a branch** → `main` / `/ (root)`.

## Notes

Standings here are unofficial. The Tourney Machine bracket linked in the header
is the official record. Player stats are compiled from scored GameChanger games.

## 50/50 live total

The pot on the Tournament info tab comes from `data.json`:

```json
"raffle": { "raised": 1487.50, "updated": "2026-09-12T18:41:00+00:00" }
```

`raised` is the full amount taken in. The page displays it as the pot and shows
half of it as the payout. **When `raised` is 0 or missing the whole block is
hidden**, so the card looks normal before the first ticket sells.

### One-time setup

1. In Zeffy: Settings → Integrations → generate an API key (read-only).
2. In this repo: Settings → Secrets and variables → Actions → New repository
   secret, named `ZEFFY_API_KEY`.
3. Actions tab → "Update 50/50 total" → **Run workflow** to test it.

Read the log of that first run. It prints every campaign with its id, then the
full payload of the one it picked. Two things to confirm:

- **It picked the right campaign.** It matches any title containing "raffle".
  If you have more than one, set a repository *variable* `ZEFFY_CAMPAIGN_ID`.
- **The units are dollars, not cents.** If the payload shows `148750` where you
  expect `1487.50`, set the variable `ZEFFY_AMOUNT_IN_CENTS` to `1`.
- If it grabs the wrong number entirely, set `ZEFFY_RAISED_FIELD` to the exact
  key name from the payload.

The API key lives only in GitHub Secrets. It is never in `data.json`, never in
`index.html`, and never reaches a browser — the page is public, so a
client-side call would publish the key.

### During and after the weekend

Each run commits only when the number actually moves, and every commit triggers
a Pages rebuild. That's fine for a three-day event. **Turn the workflow off when
the tournament ends** — Actions tab → "Update 50/50 total" → ⋯ → Disable
workflow — or it keeps polling forever.

Scheduled runs are best-effort and often land late, which is why the page prints
"as of 3:41 PM" under the pot rather than implying it's live to the second.

If in-person sales don't go through Zeffy, the number on the page will be low
all weekend. Zeffy's Tap to Pay app keeps everything in one total.

## Running the draw

Two manual steps from Actions -> "50/50 draw". Never automated, never on a schedule.

### 1. Close sales, then `commit`

Run with `step: commit` and `draw_at` set to when you'll actually draw, ISO 8601
**with a timezone offset**:

    2026-09-13T18:00:00-04:00

This pulls every succeeded, unrefunded payment, assigns ticket numbers in
creation order, and writes:

- `raffle-entries.json` — ticket numbers and a 12-character `ref` per buyer.
  No names, no emails. The `ref` is `SHA256(zeffy_payment_id)[:12]`, so a buyer
  can find their own tickets using the payment id on their receipt.
- a `draw` block in `data.json` holding the SHA-256 commitment over that list
  and the **future** drand round the draw will use.

The script refuses a `draw_at` that maps to a round already produced. That
refusal is the whole point: the randomness must not exist yet.

**Sell nothing after this step.** Late sales won't be in the frozen list.

### 2. At the appointed time, `draw`

Run with `step: draw`. It re-hashes the published entry list and aborts if it
no longer matches the commitment, fetches that drand round, and computes:

    winning_ticket = SHA256(commitment + randomness) mod total_tickets + 1

The workflow then runs `verify_draw.py` and only publishes if it passes.

### Bundles

If you add tiered pricing, set the repo variable `ZEFFY_RATE_ENTRIES` to a JSON
map of Zeffy rate title to entries granted:

    {"Ten chances of winning": 10, "Twenty-five chances": 25}

Without it every ticket item counts as one entry.

### Verifying

    git clone https://github.com/TheDr21/KeystoneClash
    cd KeystoneClash
    python3 scripts/verify_draw.py

No API key needed. It refetches the beacon from drand and recomputes the winner.
