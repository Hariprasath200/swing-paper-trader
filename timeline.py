"""Buy window / sell-by dates in trading days (weekends and NSE holidays skipped)."""
import os
from datetime import datetime
import numpy as np
from config import BASE, PENDING_DAYS, MAX_HOLD_DAYS

def _holidays():
    path = os.path.join(BASE, "nse_holidays.txt")
    if not os.path.exists(path):
        return []
    out = []
    for line in open(path, encoding="utf-8"):
        line = line.split("#")[0].strip()
        if line:
            out.append(line)
    return out

def add_td(d, n):
    """The date n trading days after d."""
    return str(np.busday_offset(d, n, roll="forward", holidays=_holidays()))

def buy_window(created):
    """Order is live from the next session until the PENDING_DAYS-th session."""
    return add_td(created, 1), add_td(created, PENDING_DAYS)

def sell_by(entry_date):
    """Day 1 is the buy session; the MAX_HOLD_DAYS-th session close is the deadline."""
    return add_td(entry_date, MAX_HOLD_DAYS - 1)

def dfmt(s):
    return datetime.strptime(s, "%Y-%m-%d").strftime("%a, %d %b %Y") if s else "–"

def dshort(s):
    return datetime.strptime(s, "%Y-%m-%d").strftime("%d %b") if s else "–"
