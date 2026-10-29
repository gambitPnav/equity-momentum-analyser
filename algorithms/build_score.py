"""Per-stock scalping score from the daily BSE gainer/loser files.

Run:  python algorithms/score.py
Reads bse-responses/<DD-MM-YY>/bse-gainer.json + bse-loser.json (full market data)
Writes algorithms/scores.json and prints the top candidates for the next session.

Idea: every time a stock was a strong gainer on day D, look at what the NEXT day's
bar offered a buyer at the open (how high it went, how far it dipped). A stock's
score comes from its own history of those outcomes, smoothed toward the overall
hit rate so one lucky day doesn't rank a stock first.
"""
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "bse-responses"
OUT = ROOT / "algorithms" / "scores.json"

# ---- knobs: these are guesses, tune them ----
EVENT_MOVE = 5.0     # a "gainer event" = change_percent >= this
MIN_TRADES = 50      # liquidity floor (nooftrd) for events and candidates
TARGET = 0.02        # your scalp target as a fraction of the open (2%)
COST = 0.004         # assumed round-trip costs + slippage (0.4%); set your own
MIN_EVENTS = 3       # stocks with fewer past events are ranked below the rest
K = 5                # smoothing strength: events needed before own record dominates
SKIP_GROUPS = set()  # e.g. {"T", "Z"}: groups you can't trade intraday (check your broker)


def load_day(folder):
    bars = {}
    for name in ("bse-gainer.json", "bse-loser.json"):
        path = folder / name
        if not path.exists():
            continue
        for r in json.loads(path.read_text(encoding="utf-8")).get("Table", []):
            if not r.get("openrate") or not r.get("ltradert"):
                continue
            bars[r["scrip_cd"]] = {
                "name": r.get("scripname"),
                "full": r.get("LONG_NAME"),
                "grp": r.get("scrip_grp"),
                "open": r["openrate"],
                "high": r["highrate"],
                "low": r["lowrate"],
                "close": r["ltradert"],
                "chg": r["change_percent"],
                "trades": r.get("nooftrd") or 0,
                "vol": r.get("trd_vol") or 0,
                "ipo": "IPO" in (r.get("index_code") or ""),
            }
    return bars


def smoothed(wins, n, prior):
    return (wins + K * prior) / (n + K)


days = {}
for folder in SRC.iterdir():
    if folder.is_dir():
        try:
            iso = datetime.strptime(folder.name, "%d-%m-%y").date().isoformat()
        except ValueError:
            continue
        days[iso] = load_day(folder)
dates = sorted(days)
if len(dates) < 2:
    raise SystemExit("Need at least two days of data.")

# Past events: gainer on day d -> what did the next day's bar offer at the open?
events = {}
for d, n in zip(dates, dates[1:]):
    for code, b in days[d].items():
        if b["chg"] < EVENT_MOVE or b["trades"] < MIN_TRADES:
            continue
        nb = days[n].get(code)
        if not nb or nb["open"] <= 0:
            continue
        events.setdefault(code, []).append({
            "date": n,
            "room": nb["high"] / nb["open"] - 1,
            "dd": nb["low"] / nb["open"] - 1,
            "gap": nb["open"] / b["close"] - 1,
        })

all_events = [e for ev in events.values() for e in ev]
if not all_events:
    raise SystemExit("No qualifying events yet. Lower EVENT_MOVE or MIN_TRADES.")
hit = lambda e: e["room"] - COST >= TARGET
overall = sum(map(hit, all_events)) / len(all_events)

# Candidates: strong gainers on the latest day
latest = dates[-1]
rows = []
for code, b in days[latest].items():
    if b["chg"] < EVENT_MOVE or b["trades"] < MIN_TRADES or b["ipo"] or b["grp"] in SKIP_GROUPS:
        continue
    ev = events.get(code, [])
    n = len(ev)
    rows.append({
        "code": code, "name": b["name"], "full": b["full"], "grp": b["grp"],
        "today_chg": b["chg"], "trades": b["trades"], "vol": b["vol"],
        "n": n,
        "p_hit": round(smoothed(sum(map(hit, ev)), n, overall), 4),
        "avg_room": round(sum(e["room"] for e in ev) / n, 4) if n else None,
        "avg_dd": round(sum(e["dd"] for e in ev) / n, 4) if n else None,
        "avg_gap": round(sum(e["gap"] for e in ev) / n, 4) if n else None,
    })

rows.sort(key=lambda r: (r["n"] >= MIN_EVENTS, r["p_hit"]), reverse=True)
payload = {
    "for_session_after": latest,
    "params": {"EVENT_MOVE": EVENT_MOVE, "MIN_TRADES": MIN_TRADES, "TARGET": TARGET,
               "COST": COST, "MIN_EVENTS": MIN_EVENTS, "K": K},
    "overall_hit_rate": round(overall, 4),
    "total_events": len(all_events),
    "candidates": rows,
}
OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
(ROOT / "frontend" / "scores.js").write_text(
    "window.BSE_SCORES = " + json.dumps(payload) + ";\n", encoding="utf-8")

print(f"Days: {len(dates)} | past events: {len(all_events)} | overall hit rate: {overall:.1%}")
print(f"Candidates after {latest}: {len(rows)}  (top 20 below)\n")
print(f"{'stock':<14}{'grp':<5}{'today%':>8}{'n':>4}{'p_hit':>8}{'avg_room':>10}{'avg_dd':>9}")
for r in rows[:20]:
    f = lambda v: "   -   " if v is None else f"{v:.1%}"
    print(f"{r['name']:<14}{r['grp']:<5}{r['today_chg']:>8.2f}{r['n']:>4}{r['p_hit']:>8.1%}{f(r['avg_room']):>10}{f(r['avg_dd']):>9}")