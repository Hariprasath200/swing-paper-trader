"""Run once per trading day after market close (after ~4:30 PM IST)."""
import json
from db import conn
from universe import get_universe
from screener import market_regime, scan
from picker import pick_three, TRACKS
from paper import update_positions, add_pending, active_symbols

def main():
    ok, asof = market_regime()
    update_positions(asof)                                   # 1. fills / stops / targets / post-mortems
    with conn() as c:
        if c.execute("SELECT 1 FROM scans WHERE date=?", (asof,)).fetchone():
            print("Already scanned", asof); return
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
    for t, p in picks.items():
        print(asof, t, p["symbol"] if p["trade"] else p["reason"])

if __name__ == "__main__":
    main()
