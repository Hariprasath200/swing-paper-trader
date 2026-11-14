import io, os
import pandas as pd
import requests

URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
CACHE = "universe_cache.csv"

def get_universe():
    """All NSE EQ-series symbols. Falls back to a cached/manual CSV."""
    try:
        r = requests.get(URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text))
        df.columns = [c.strip() for c in df.columns]
        syms = df[df["SERIES"].str.strip() == "EQ"]["SYMBOL"].str.strip().tolist()
        pd.Series(syms).to_csv(CACHE, index=False, header=False)
        return syms
    except Exception as e:
        if os.path.exists(CACHE):
            return pd.read_csv(CACHE, header=None)[0].tolist()
        raise RuntimeError(
            f"Could not fetch NSE list ({e}). Download EQUITY_L.csv from nseindia.com "
            f"and save the SYMBOL column (one per line, no header) as {CACHE}.")
