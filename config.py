import os
BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "paper_v2.db")

# ---- paper account -------------------------------------------------
START_CAPITAL = 100000.0     # virtual money (INR); large so cash never blocks a trade
TRADE_AMOUNT = 10000.0       # fixed rupees per trade -> quantity = TRADE_AMOUNT // entry price
TARGET_TRADES = 100          # completed trades before you judge the system
PRICE_SPLIT = 500            # LOW track < 500 <= HIGH track

# ---- screening filters (edit these when the Lessons tab suggests it) -
MIN_PRICE = 50
MIN_AVG_TURNOVER = 5e7       # Rs 5 crore/day traded
RSI_MIN, RSI_MAX = 50, 72
MIN_VOLUME_RATIO = 1.0
MAX_RET_63D = None           # e.g. 60 = skip stocks already up >60% in 63 days
TOP_N = 40
BATCH = 200

# ---- trade rules ---------------------------------------------------
ENTRY_PULLBACK_ATR = 0.25    # buy-limit this many ATR below last close
STOP_ATR = 1.5               # stop distance
TARGET_ATR = 2.7             # target distance (reward:risk = 1.8)
PENDING_DAYS = 3             # entry order lives 3 sessions
MAX_HOLD_DAYS = 15           # target not reached by day 15 = FAILURE
COST_PCT = 0.002             # ~0.2% round-trip costs
