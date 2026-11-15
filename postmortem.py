"""Automatic post-mortem: WHY did a trade fail (or work)? Free, rule-based, no AI cost."""

def analyze(t, f, nifty_ret):
    """t: trade row (with exit info). f: features at entry. Returns (tags, text)."""
    e, stop, target = t["entry"], t["stop"], t["target"]
    days, reason = t["days_held"], t["exit_reason"]
    mfe, mae = t.get("mfe_pct") or 0.0, t.get("mae_pct") or 0.0
    target_pct = (target / e - 1) * 100
    progress = mfe / target_pct if target_pct else 0
    mkt = f"Nifty {nifty_ret:+.1f}% during the trade. " if nifty_ret is not None else ""
    if t["outcome"] == "SUCCESS":
        return "WORKED", f"Target hit in {days} day(s). {mkt}Best move before exit +{mfe:.1f}%, worst dip {mae:.1f}%."
    tags, notes = [], []
    atr = f.get("atr") or 0
    stop_atr = (e - stop) / atr if atr else None
    if reason == "STOP_GAP":
        tags.append("GAP_DOWN")
        notes.append("Opened below the stop (overnight gap). A stop cannot protect against news/gaps.")
    elif reason == "STOP" and days <= 3:
        tags.append("FAST_STOP")
        notes.append(f"Stopped out within {days} day(s): entry timing was poor or the stop was tight"
                     + (f" ({stop_atr:.1f} ATR)." if stop_atr else "."))
    elif reason == "STOP":
        tags.append("STOP_HIT")
        notes.append(f"Trend failed after {days} days; stop hit.")
    if reason == "TIMEOUT":
        if progress < 0.3:
            tags.append("STALLED")
            notes.append(f"Never got past {progress * 100:.0f}% of the way to target in {days} days: momentum faded.")
        else:
            tags.append("TIMEOUT")
            notes.append(f"Ran out of time at day {days}, reached {progress * 100:.0f}% of the way to target.")
    if progress >= 0.8 and reason != "TARGET":
        tags.append("NEAR_MISS")
        notes.append(f"Got within {100 - progress * 100:.0f}% of target (+{mfe:.1f}%) before failing: target may be too far, or a trailing stop would have helped.")
    if nifty_ret is not None and nifty_ret < -2:
        tags.append("MARKET_DRAG")
        notes.append(f"Broad market fell {nifty_ret:.1f}% meanwhile.")
    if (f.get("ret_63d_pct") or 0) > 50 or (f.get("rsi") or 0) > 68:
        tags.append("EXTENDED")
        notes.append(f"Entered an already-extended stock (63d return {f.get('ret_63d_pct')}%, RSI {f.get('rsi')}).")
    if (f.get("atr_pct") or 0) > 4:
        tags.append("VOLATILE")
        notes.append(f"Very volatile stock (ATR {f.get('atr_pct')}% of price): wide swings make time-limited targets less reliable.")
    if not tags:
        tags.append("UNCLEAR")
        notes.append("No single obvious cause; likely normal randomness.")
    return ",".join(tags), mkt + " ".join(notes)
