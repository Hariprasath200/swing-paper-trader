"""Per-stock holding time limit settings (kept separate so config.py edits are not overwritten)."""
from config import MAX_HOLD_DAYS, PENDING_DAYS, ENTRY_PULLBACK_ATR, STOP_ATR, TARGET_ATR

MIN_HOLD_DAYS = 5            # never shorter than this
MAX_HOLD_CAP = 20            # never longer than this
DEFAULT_HOLD_DAYS = MAX_HOLD_DAYS   # used when the stock's history is too thin to decide (15)
HOLD_PERCENTILE = 85         # time limit = how long 85% of this stock's past winners took
MIN_HIST_SUCCESS = 8         # need at least this many past winners to trust the history
HIST_LOOKAHEAD = 20          # longest wait considered when replaying history
