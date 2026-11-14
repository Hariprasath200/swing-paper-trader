import sqlite3
from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  track TEXT, symbol TEXT, status TEXT, created_date TEXT,
  plan_entry REAL, entry REAL, stop REAL, target REAL, qty INTEGER,
  entry_date TEXT, exit_date TEXT, exit_price REAL, exit_reason TEXT,
  outcome TEXT, days_held INTEGER, last_price REAL, pnl REAL,
  mfe_pct REAL, mae_pct REAL, nifty_ret_pct REAL,
  features TEXT, rationale TEXT, failure_tags TEXT, post_mortem TEXT);
CREATE TABLE IF NOT EXISTS equity(
  date TEXT PRIMARY KEY, equity REAL, realized REAL, unrealized REAL);
CREATE TABLE IF NOT EXISTS scans(
  date TEXT PRIMARY KEY, regime TEXT, candidates TEXT, picks TEXT);
"""

def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    return c
