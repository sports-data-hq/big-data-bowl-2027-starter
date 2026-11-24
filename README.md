# Big Data Bowl 2027 starter: regular-season outcomes for Combine players

The [NFL Big Data Bowl 2027](https://www.kaggle.com/competitions/nfl-big-data-bowl-2027) asks how Combine sensor
tracking links to regular-season performance. Kaggle gives you the Combine side. This script gets you the
regular-season side in about 14 API calls per season, then matches it to your Combine players by name and position.

## What you get

One CSV per season, one row per player (GSIS id, name, position, team), with:

| Group | Columns |
|---|---|
| Player tracking, receiving | separation, cushion, YAC and YAC over expected, intended air yards, catch %, targets, yards |
| Player tracking, rushing | rush yards over expected (total and per attempt), efficiency, time to line of scrimmage |
| Player tracking, passing | time to throw, completion % over expected, aggressiveness, air yards |
| Season totals and rank | receiving and rushing yards, passing EPA, PPR fantasy points, sacks, QB hits, solo tackles, passes defended, interceptions |

With `--combine`, it also writes `combine_matched.csv`: your Combine rows with the outcomes beside them.

Example (2024 season): 616 players, 69 columns. A sample of eight 2024 Combine names matched seven. The one miss
was an offensive tackle, because linemen have no box-score stats; use per-game snap counts (`get_snap_counts`) for them.

## Run it

```bash
pip install pandas requests
export ENDZONE_API_KEY=...        # free key at https://endzoneapi.com/signup?utm_source=github&utm_campaign=bdb2027
python bdb_outcomes.py --seasons 2023 2024 2025
python bdb_outcomes.py --seasons 2024 2025 --combine players.csv --name-col displayName --pos-col position
```

Cost: about 70 credits per season. The free plan's 500 credits a month cover several seasons. The script paces
itself to the free plan's rate limit, so each season takes under two minutes.

## Matching

Names are normalized (case, punctuation, Jr./Sr./II/III) and matched with a position group (EDGE/DE/DT as DL,
CB/S as DB, OT/OG/C as OL). If the position label differs between college and the NFL, it falls back to the name
alone when that name is unique. Check the unmatched rows by hand: they are usually linemen or players with no NFL
snaps in the seasons you pulled.

## Data and rules

- The competition rules allow outside data that is reasonably accessible to everyone and low cost. EndzoneAPI has
  a free plan, so everyone can reproduce your inputs.
- Use the outcomes in your analysis and publish what you find. Don't republish the raw tables as a dataset of
  their own ([terms](https://endzoneapi.com/docs/timing-and-rights)).
- This repo does not include any Big Data Bowl data. That data comes from Kaggle under its own license.

## More from EndzoneAPI

Play-by-play with EPA and win probability since 1999, weekly player stats, snap counts, depth charts and injuries
are all in the same API: [endzoneapi.com/docs](https://endzoneapi.com/docs).

EndzoneAPI is independent and not affiliated with the NFL or Kaggle.
