"""One-time clean-up: delete duplicate trades (same symbol + created_date + track), keep the oldest copy.
Also removes the duplicates' events/snapshots and fixes the equity rows they inflated."""
import shutil, sqlite3, sys
from config import DB_PATH, START_CAPITAL

shutil.copy(DB_PATH, DB_PATH + ".backup")                 # safety copy (do NOT commit it)
c = sqlite3.connect(DB_PATH)
dups = [r[0] for r in c.execute(
    "SELECT id FROM trades WHERE id NOT IN (SELECT MIN(id) FROM trades GROUP BY symbol, created_date, track)")]
print("duplicate trade ids to delete:", dups)
if dups:
    q = ",".join("?" * len(dups))
    for tbl in ("events", "snapshots"):
        c.execute(f"DELETE FROM {tbl} WHERE trade_id IN ({q})", dups)
    c.execute(f"DELETE FROM trades WHERE id IN ({q})", dups)
    realized = c.execute("SELECT COALESCE(SUM(pnl),0) FROM trades WHERE status='CLOSED'").fetchone()[0]
    # Rebuild unrealized for each past date from that date's last snapshots of still-valid trades
    for (d,) in c.execute("SELECT date FROM equity").fetchall():
        u = 0.0
        for tid, entry, qty, edate in c.execute("SELECT id, entry, qty, entry_date FROM trades WHERE entry IS NOT NULL").fetchall():
            if edate and edate <= d:
                r = c.execute("SELECT price FROM snapshots WHERE trade_id=? AND substr(ts,1,10)<=? "
                              "ORDER BY id DESC LIMIT 1", (tid, d)).fetchone()
                if r:
                    u += (r[0] - entry) * qty
        c.execute("UPDATE equity SET equity=?, realized=?, unrealized=? WHERE date=?",
                  (START_CAPITAL + realized + u, realized, u, d))
    c.commit()
print("trades left:", c.execute("SELECT COUNT(*) FROM trades").fetchone()[0])
for r in c.execute("SELECT * FROM equity ORDER BY date"): print(r)