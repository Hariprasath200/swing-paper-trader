import pandas as pd
import yfinance as yf
from config import *

def _flat(df):
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df

def _rsi(c, n=14):
    d = c.diff()
    up = d.clip(lower=0).rolling(n).mean()
    dn = (-d.clip(upper=0)).rolling(n).mean()
    return 100 - 100 / (1 + up / dn)

def _atr(df, n=14):
    pc = df.Close.shift()
    tr = pd.concat([df.High - df.Low, (df.High - pc).abs(), (df.Low - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def market_regime():
    """Nifty 50 above its 50-day average = OK to open new trades."""
    df = _flat(yf.download("^NSEI", period="6mo", progress=False, auto_adjust=True)).dropna()
    c = df.Close
    return bool(c.iloc[-1] > c.rolling(50).mean().iloc[-1]), df.index[-1].strftime("%Y-%m-%d")

def _evaluate(sym, df):
    if len(df) < 70:
        return None
    c, h, l, v = df.Close, df.High, df.Low, df.Volume
    last = float(c.iloc[-1])
    if last < MIN_PRICE or float((c * v).tail(20).mean()) < MIN_AVG_TURNOVER:
        return None
    sma20, sma50 = float(c.rolling(20).mean().iloc[-1]), float(c.rolling(50).mean().iloc[-1])
    if not (last > sma20 > sma50):
        return None
    rsi = float(_rsi(c).iloc[-1])
    if not RSI_MIN <= rsi <= RSI_MAX:
        return None
    high20 = float(h.iloc[-21:-1].max())
    prox = last / high20
    if prox < 0.96:
        return None
    volr = float(v.iloc[-1] / v.tail(20).mean())
    if volr < MIN_VOLUME_RATIO:
        return None
    ret63 = float(last / c.iloc[-64] - 1)
    if MAX_RET_63D is not None and ret63 * 100 > MAX_RET_63D:
        return None
    atr = float(_atr(df).iloc[-1])
    score = ret63 * 40 + min(volr, 3) * 10 + prox * 30
    return dict(symbol=sym, close=round(last, 2), sma20=round(sma20, 2), sma50=round(sma50, 2),
                rsi=round(rsi, 1), atr=round(atr, 2), atr_pct=round(atr / last * 100, 2),
                volume_ratio=round(volr, 2), pct_below_20d_high=round((1 - prox) * 100, 2),
                ret_63d_pct=round(ret63 * 100, 1), support_10d=round(float(l.tail(10).min()), 2),
                score=round(score, 2))

def scan(symbols, exclude=()):
    rows = []
    skip = set(exclude)
    symbols = [s for s in symbols if s not in skip]
    for i in range(0, len(symbols), BATCH):
        batch = [s + ".NS" for s in symbols[i:i + BATCH]]
        try:
            data = yf.download(batch, period="6mo", group_by="ticker", threads=True,
                               progress=False, auto_adjust=True)
        except Exception:
            continue
        if not isinstance(data.columns, pd.MultiIndex):
            data = pd.concat({batch[0]: data}, axis=1)
        for t in batch:
            try:
                r = _evaluate(t[:-3], data[t].dropna())
            except Exception:
                r = None
            if r:
                rows.append(r)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("score", ascending=False).head(TOP_N)
