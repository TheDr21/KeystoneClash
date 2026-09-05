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
