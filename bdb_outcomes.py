"""
Big Data Bowl 2027 starter: regular-season outcomes for NFL players, ready to join to Combine tracking data.

The competition asks how Combine sensor tracking links to regular-season performance. Kaggle supplies the Combine
side. This script pulls the regular-season side from EndzoneAPI in a few bulk calls per season:

  - Next Gen Stats season aggregates: receiving (separation, cushion, YAC over expected), rushing (yards over
    expected, efficiency) and passing (time to throw, completion % over expected, air yards).
  - Season totals and ranks for the stats that usually stand in for "performance": receiving and rushing yards,
    passing EPA, PPR fantasy points, and for defenders sacks, QB hits, solo tackles, passes defended, interceptions.
    Offensive linemen have no box-score stats here; for them use snap counts (get_snap_counts) per game.

It writes one wide CSV per season (one row per player, GSIS id plus name, position, team), and, if you pass a
Combine player file, a matched table with your Combine columns beside the outcomes.

Cost: about 70 EndzoneAPI credits and under two minutes per season (14 calls, paced for the free plan's rate limit). The free plan's 500 credits a month cover several seasons.
Usage:
  export ENDZONE_API_KEY=...            # free key: https://endzoneapi.com/signup
  python bdb_outcomes.py --seasons 2023 2024 2025
  python bdb_outcomes.py --seasons 2024 --combine players.csv --name-col displayName --pos-col position
"""
import argparse
import os
import re
import sys
import time

import pandas as pd
import requests

BASE = "https://mcp.endzoneapi.com/v1"
NGS_SOURCES = ["ngs_receiving", "ngs_rushing", "ngs_passing"]
# (stat, position or None, how many): totals that are common "regular-season performance" targets.
LEADERS = [
    ("receiving_yards", "WR", 100), ("receiving_yards", "TE", 60), ("receiving_yards", "RB", 60),
    ("rushing_yards", "RB", 80), ("passing_epa", "QB", 50),
    ("fantasy_points_ppr", None, 100), ("def_sacks", None, 100), ("def_interceptions", None, 100),
    ("def_tackles_solo", None, 100), ("def_pass_defended", None, 100), ("def_qb_hits", None, 100),
]
POS_GROUP = {"HB": "RB", "FB": "RB", "OLB": "LB", "ILB": "LB", "MLB": "LB", "DE": "DL", "DT": "DL", "NT": "DL", "IDL": "DL",
             "EDGE": "DL", "CB": "DB", "S": "DB", "FS": "DB", "SS": "DB", "SAF": "DB", "OT": "OL", "OG": "OL", "C": "OL", "G": "OL", "T": "OL"}

calls = 0
# Low-balance keys (most free accounts) may make 10 calls a minute; one call every 6.5 seconds stays under it.
PACE_SECONDS = 6.5
_last = 0.0


def call(tool, **params):
    global calls, _last
    key = os.environ.get("ENDZONE_API_KEY")
    if not key:
        sys.exit("Set ENDZONE_API_KEY (free key: https://endzoneapi.com/signup)")
    for attempt in range(4):
        wait = PACE_SECONDS - (time.time() - _last)
        if wait > 0:
            time.sleep(wait)
        _last = time.time()
        r = requests.post(f"{BASE}/{tool}", headers={"x-api-key": key}, json=params, timeout=90)
        if r.status_code == 429 and attempt < 3:
            time.sleep(20)  # the limit is per minute
            continue
        if r.status_code == 402:
            sys.exit(f"Out of credits on {tool}: {r.text[:200]}")
        r.raise_for_status()
        calls += 1
        return r.json()["data"]


def season_outcomes(season):
    frames = []
    for src in NGS_SOURCES:
        d = call("get_advanced_stats", source=src, season=season, week=0, limit=200)
        rows = [{"player_id": s["player_id"], "name": s["name"], "position": s["position"], "team": s["team"],
                 **{f"{src}_{k}": v for k, v in (s.get("metrics") or {}).items()}} for s in d.get("stats", [])]
        if rows:
            frames.append(pd.DataFrame(rows))
    for stat, pos, n in LEADERS:
        d = call("get_player_leaders", stat=stat, season=season, limit=n, **({"position": pos} if pos else {}))
        col = f"{stat}" if pos is None else f"{stat}_{pos.lower()}"
        rows = [{"player_id": x["player_id"], "name": x["name"], "position": x["position"], "team": x["team"],
                 "games": x.get("games"), col: x["value"], f"{col}_rank": x["rank"]} for x in d.get("leaders", [])]
        if rows:
            frames.append(pd.DataFrame(rows))
    if not frames:
        return pd.DataFrame()
    keys = ["player_id", "name", "position", "team"]
    out = frames[0]
    for f in frames[1:]:
        dup = [c for c in f.columns if c in out.columns and c not in keys]
        out = out.merge(f.drop(columns=[c for c in dup if c != "games"]), on=keys, how="outer", suffixes=("", "_dup"))
        if "games_dup" in out:
            out["games"] = out["games"].fillna(out.pop("games_dup"))
    # One row per player: a traded player arrives with one team per source; keep the first value of each column.
    out = out.groupby("player_id", as_index=False, sort=False).first()
    out.insert(0, "season", season)
    return out


def norm_name(s):
    s = re.sub(r"[.'`]", "", str(s).lower())
    s = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", "", s)
    return re.sub(r"[^a-z]+", " ", s).strip()


def pos_group(p):
    p = str(p).upper()
    return POS_GROUP.get(p, p)


def match(combine, outcomes, name_col, pos_col):
    c = combine.copy()
    c["_name"], c["_pos"] = c[name_col].map(norm_name), c[pos_col].map(pos_group)
    o = outcomes.copy()
    o["_name"], o["_pos"] = o["name"].map(norm_name), o["position"].map(pos_group)
    merged = c.merge(o, on=["_name", "_pos"], how="left", suffixes=("", "_nfl"))
    # Same name, different position label (a college LB listed as DL in the NFL): fall back to name alone when unique.
    miss = merged["player_id"].isna()
    if miss.any():
        unique = o.drop_duplicates("_name", keep=False).set_index("_name")
        for i in merged.index[miss]:
            n = merged.at[i, "_name"]
            if n in unique.index:
                for col in o.columns:
                    if col not in ("_name", "_pos") and col in merged.columns:
                        merged.at[i, col] = unique.at[n, col]
    return merged.drop(columns=["_name", "_pos"])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seasons", type=int, nargs="+", required=True)
    ap.add_argument("--combine", help="CSV of Combine players to match (one row per player)")
    ap.add_argument("--name-col", default="displayName")
    ap.add_argument("--pos-col", default="position")
    ap.add_argument("--out", default="outcomes")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    allseasons = []
    for s in a.seasons:
        df = season_outcomes(s)
        df.to_csv(f"{a.out}/outcomes_{s}.csv", index=False)
        print(f"{s}: {len(df)} players, {df.shape[1]} columns -> {a.out}/outcomes_{s}.csv")
        allseasons.append(df)
    if a.combine:
        outcomes = pd.concat(allseasons, ignore_index=True)
        combine = pd.read_csv(a.combine)
        m = match(combine, outcomes, a.name_col, a.pos_col)
        m.to_csv(f"{a.out}/combine_matched.csv", index=False)
        found = m.groupby(a.name_col)["player_id"].apply(lambda x: x.notna().any())
        print(f"Matched {int(found.sum())} of {len(found)} Combine players (players with no NFL output in these stats stay unmatched).")
    print(f"{calls} API calls, about {calls * 5} credits.")


if __name__ == "__main__":
    main()
