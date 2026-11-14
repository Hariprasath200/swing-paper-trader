"""Run on a schedule. Market hours (9:15-15:45 IST): update open trades only.
After close: update + full scan for the next day's 3 picks. `--force` forces a full scan."""
import json, sys
from datetime import datetime, time, timedelta, timezone
from db import conn
from universe import get_universe
from screener import market_regime, scan
from picker import pick_three, TRACKS
from paper import update_positions, add_pending, active_symbols

IST = timezone(timedelta(hours=5, minutes=30))

def _save_meta():
    with conn() as c:
        c.execute("INSERT OR REPLACE INTO meta VALUES('last_update', ?)",
                  (datetime.now(IST).strftime("%d %b %H:%M IST"),))

def main(force=False):
    now = datetime.now(IST)
    before_final = now.time() < time(15, 45)              # today's candle may still be forming
    live_date = now.strftime("%Y-%m-%d") if before_final else None
    market_hours = now.weekday() < 5 and time(9, 15) <= now.time() < time(15, 45)
    ok, asof = market_regime()
    update_positions(asof, live_date)                     # 1. fills / stops / targets / post-mortems
    if market_hours and not force:
        _save_meta()
        print(now.strftime("%H:%M"), "market open: positions updated. New picks are made after close.")
        return
    with conn() as c:
        if c.execute("SELECT 1 FROM scans WHERE date=?", (asof,)).fetchone():
            _save_meta(); print("Already scanned", asof); return
    cands = []
    if not ok:
        picks = {t: {"trade": False, "track": t, "reason": "market weak (Nifty below 50-day average)"} for t in TRACKS}
    else:
        cands = scan(get_universe(), exclude=active_symbols()).to_dict("records")   # 2. screen all NSE
        if not cands:
            picks = {t: {"trade": False, "track": t, "reason": "no stock passed the filters"} for t in TRACKS}
        else:
            picks = pick_three(cands)                        # 3. BEST / LOW / HIGH
            for p in picks.values():
                if p["trade"]:
                    add_pending(p, asof)                     # 4. paper orders
    with conn() as c:
        c.execute("INSERT INTO scans VALUES(?,?,?,?)",
                  (asof, "OK" if ok else "WEAK", json.dumps(cands), json.dumps(picks)))
    _save_meta()
    for t, p in picks.items():
        print(asof, t, p["symbol"] if p["trade"] else p["reason"])

if __name__ == "__main__":
    main(force="--force" in sys.argv)
