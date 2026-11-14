"""Chooses 3 stocks per day: BEST (any price), LOW (<500), HIGH (>=500). All distinct."""
from config import *

TRACKS = ["BEST", "LOW", "HIGH"]

def _build(c, track):
    atr = c["atr"]
    e = round(c["close"] - ENTRY_PULLBACK_ATR * atr, 2)
    stop, target = round(e - STOP_ATR * atr, 2), round(e + TARGET_ATR * atr, 2)
    qty = int(TRADE_AMOUNT // e)
    if stop <= 0 or qty < 1:
        return None
    feats = dict(c)
    why = (f"Rule-based {track} pick: uptrend (close>SMA20>SMA50), RSI {c['rsi']}, "
           f"volume {c['volume_ratio']}x average, {c['pct_below_20d_high']}% below 20-day high, "
           f"63-day return {c['ret_63d_pct']}%, ATR {c['atr_pct']}% of price.")
    return dict(trade=True, track=track, symbol=c["symbol"], entry=e, stop=stop,
                target=target, qty=qty, features=feats, rationale=why)

def pick_three(cands):
    """cands must be sorted by score, best first."""
    picks, used = {}, set()
    rules = {"BEST": lambda c: True,
             "LOW": lambda c: c["close"] < PRICE_SPLIT,
             "HIGH": lambda c: c["close"] >= PRICE_SPLIT}
    for track in TRACKS:
        for c in cands:
            if c["symbol"] in used or not rules[track](c):
                continue
            p = _build(c, track)
            if p:
                picks[track] = p
                used.add(c["symbol"])
                break
        else:
            picks[track] = {"trade": False, "track": track, "reason": "no qualifying stock in this track today"}
    return picks
