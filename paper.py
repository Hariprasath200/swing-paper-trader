import json
from datetime import datetime, timedelta, timezone
import pandas as pd
import yfinance as yf
from config import *
from db import conn
from postmortem import analyze

IST = timezone(timedelta(hours=5, minutes=30))

def _ev(c, trade_id, kind, note):
    c.execute("INSERT INTO events(trade_id, ts, kind, note) VALUES(?,?,?,?)",
              (trade_id, datetime.now(IST).isoformat(timespec="seconds"), kind, note))

def _flat(df):
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df

def _bars(symbol, start):
    return _flat(yf.download(f"{symbol}.NS", start=start, progress=False, auto_adjust=True)).dropna()

def active_symbols():
    with conn() as c:
        return [r[0] for r in c.execute("SELECT symbol FROM trades WHERE status IN ('PENDING','OPEN')")]

def add_pending(p, asof):
    with conn() as c:
        cur = c.execute("INSERT INTO trades(track,symbol,status,created_date,plan_entry,stop,target,qty,features,rationale)"
                        " VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (p["track"], p["symbol"], "PENDING", asof, p["entry"], p["stop"], p["target"],
                         p["qty"], json.dumps(p["features"]), p["rationale"]))
        _ev(c, cur.lastrowid, "PICKED", f"Picked after market close from {asof} data. Buy limit "
            f"₹{p['entry']:,.2f}, stop ₹{p['stop']:,.2f}, target ₹{p['target']:,.2f}, qty {p['qty']}.")

def simulate(t, bars, live_date=None):
    """Replay daily bars from scratch (idempotent). If stop and target both sit inside one
    candle, the stop is assumed to hit first (conservative).
    live_date: today's still-forming bar. Price touches (fill/stop/target) count on it, but
    day-based events (expiry, 15-day timeout) wait for the finished candle."""
    status, entry, stop, target = "PENDING", t["plan_entry"], t["stop"], t["target"]
    entry_date = exit_date = exit_price = reason = None
    pend = held = 0
    hi = lo = last = None
    for ts, b in bars.iterrows():
        d = ts.strftime("%Y-%m-%d")
        if d <= t["created_date"]:
            continue
        o, h, l, cl = (float(b.Open), float(b.High), float(b.Low), float(b.Close))
        partial = (d == live_date)
        last, filled_now = cl, False
        if status == "PENDING":
            if l <= entry:
                entry, status, entry_date, filled_now = min(entry, o), "OPEN", d, True
                hi, lo = entry, min(entry, l)
            elif partial:
                continue
            else:
                pend += 1
                if pend >= PENDING_DAYS:
                    status, exit_date = "EXPIRED", d
                    break
                continue
        else:
            hi, lo = max(hi, h), min(lo, l)
        held += 1
        if not filled_now and o <= stop:      exit_price, reason = o, "STOP_GAP"
        elif l <= stop:                       exit_price, reason = stop, "STOP"
        elif not filled_now and o >= target:  exit_price, reason = o, "TARGET_GAP"
        elif h >= target:                     exit_price, reason = target, "TARGET"
        elif held >= MAX_HOLD_DAYS and not partial: exit_price, reason = cl, "TIMEOUT"
        if reason:
            status, exit_date = "CLOSED", d
            break
    out = dict(status=status, entry=None if status in ("PENDING", "EXPIRED") else entry,
               entry_date=entry_date, exit_date=exit_date, exit_price=exit_price,
               exit_reason=reason, outcome=None, days_held=held or None, last_price=last,
               pnl=None, mfe_pct=None, mae_pct=None)
    if entry_date:
        out["mfe_pct"] = round((hi / entry - 1) * 100, 2)
        out["mae_pct"] = round((lo / entry - 1) * 100, 2)
    if status == "CLOSED":
        out["pnl"] = round((exit_price - entry) * t["qty"] - COST_PCT * t["qty"] * (entry + exit_price) / 2, 2)
        out["outcome"] = "SUCCESS" if reason.startswith("TARGET") else "FAILURE"
    return out

def _nifty_ret(n, d0, d1):
    try:
        a, b = float(n.loc[:d0].iloc[-1]), float(n.loc[:d1].iloc[-1])
        return round((b / a - 1) * 100, 2)
    except Exception:
        return None

def update_positions(asof, live_date=None):
    with conn() as c:
        rows = [dict(r) for r in c.execute("SELECT * FROM trades WHERE status IN ('PENDING','OPEN')")]
        nifty = None
        if rows:
            start = min(r["created_date"] for r in rows)
            nifty = _flat(yf.download("^NSEI", start=start, progress=False, auto_adjust=True)).dropna().Close
        for t in rows:
            u = simulate(t, _bars(t["symbol"], t["created_date"]), live_date)
            u.update(nifty_ret_pct=None, failure_tags=None, post_mortem=None, id=t["id"])
            if u["status"] == "CLOSED":
                u["nifty_ret_pct"] = _nifty_ret(nifty, u["entry_date"], u["exit_date"])
                u["failure_tags"], u["post_mortem"] = analyze({**t, **u}, json.loads(t["features"]),
                                                              u["nifty_ret_pct"])
            c.execute("UPDATE trades SET status=:status, entry=:entry, entry_date=:entry_date,"
                      " exit_date=:exit_date, exit_price=:exit_price, exit_reason=:exit_reason,"
                      " outcome=:outcome, days_held=:days_held, last_price=:last_price, pnl=:pnl,"
                      " mfe_pct=:mfe_pct, mae_pct=:mae_pct, nifty_ret_pct=:nifty_ret_pct,"
                      " failure_tags=:failure_tags, post_mortem=:post_mortem WHERE id=:id", u)
            if t["status"] == "PENDING" and u["entry_date"]:
                _ev(c, t["id"], "FILLED", f"Bought {t['qty']} @ ₹{u['entry']:,.2f} (session {u['entry_date']}).")
            if u["status"] == "CLOSED":
                _ev(c, t["id"], u["exit_reason"], f"Sold @ ₹{u['exit_price']:,.2f} (session {u['exit_date']}): "
                    f"{u['outcome']}, P&L ₹{u['pnl']:,.0f}.")
            elif u["status"] == "EXPIRED":
                _ev(c, t["id"], "EXPIRED", f"Buy order not filled within {PENDING_DAYS} sessions; cancelled (no loss).")
            if u["status"] in ("PENDING", "OPEN") and u["last_price"] is not None:
                c.execute("INSERT INTO snapshots(trade_id, ts, price) VALUES(?,?,?)",
                          (t["id"], datetime.now(IST).isoformat(timespec="seconds"), u["last_price"]))
        realized = c.execute("SELECT COALESCE(SUM(pnl),0) FROM trades WHERE status='CLOSED'").fetchone()[0]
        unreal = c.execute("SELECT COALESCE(SUM((last_price-entry)*qty),0) FROM trades "
                           "WHERE status='OPEN' AND last_price IS NOT NULL").fetchone()[0]
        c.execute("INSERT OR REPLACE INTO equity VALUES(?,?,?,?)",
                  (asof, START_CAPITAL + realized + unreal, realized, unreal))
