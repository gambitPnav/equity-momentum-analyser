"""Bundle bse-responses/<DD-MM-YY>/*.json into frontend/data.js.

Run from anywhere:  python algorithms/build_data.py
Re-run it whenever you add a new day's files.

The BSE files hold every stock, so only meaningful movers are bundled
for the page. Tune MIN_MOVE / MIN_TRADES below.
"""
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "bse-responses"
OUT = ROOT / "frontend" / "data.js"

MIN_MOVE = 5.0    # keep stocks that moved at least this many percent
MIN_TRADES = 50   # keep stocks with at least this many trades


def slim(path, sign):
    if not path.exists():
        print("  missing:", path)
        return []
    rows = json.loads(path.read_text(encoding="utf-8")).get("Table", [])
    out = []
    for r in rows:
        chg = r.get("change_percent")
        if chg is None or chg * sign < MIN_MOVE or (r.get("nooftrd") or 0) < MIN_TRADES:
            continue
        out.append({
            "code": r.get("scrip_cd"),
            "name": r.get("scripname"),
            "full": r.get("LONG_NAME"),
            "grp": r.get("scrip_grp"),
            "chg": chg,
            "ltp": r.get("ltradert"),
            "prev": r.get("prevdayclose"),
            "trades": r.get("nooftrd"),
            "vol": r.get("trd_vol"),
        })
    return out


days = []
for folder in sorted(SRC.iterdir()):
    if not folder.is_dir():
        continue
    try:
        iso = datetime.strptime(folder.name, "%d-%m-%y").date().isoformat()
    except ValueError:
        print("skipping folder with unexpected name:", folder.name)
        continue
    g = slim(folder / "bse-gainer.json", 1)
    l = slim(folder / "bse-loser.json", -1)
    print(f"{folder.name}: {len(g)} gainers, {len(l)} losers kept")
    days.append({"date": iso, "gainers": g, "losers": l})

days.sort(key=lambda d: d["date"])
OUT.write_text("window.BSE_DATA = " + json.dumps(days) + ";\n", encoding="utf-8")
print(f"Wrote {len(days)} days to {OUT}")