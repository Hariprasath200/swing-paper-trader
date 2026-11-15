import json, subprocess, sys
from datetime import datetime, timedelta, timezone
import numpy as np, pandas as pd, streamlit as st
import plotly.graph_objects as go, plotly.express as px, yfinance as yf
from config import *
from hold_config import MIN_HOLD_DAYS, MAX_HOLD_CAP
from db import conn
from timeline import buy_window, sell_by, dfmt, dshort

st.set_page_config("SwingLab | NSE Paper Trader", page_icon="📈", layout="wide")

GREEN, RED, AMBER, CYAN, VIOLET, GREY = "#34D399", "#F43F5E", "#F5B942", "#22D3EE", "#A78BFA", "#64748B"
TRACK_COL = {"BEST": AMBER, "LOW": CYAN, "HIGH": VIOLET}
TRACK_NAME = {"BEST": "BEST OVERALL", "LOW": f"UNDER ₹{PRICE_SPLIT}", "HIGH": f"₹{PRICE_SPLIT} & ABOVE"}
IST = timezone(timedelta(hours=5, minutes=30))

st.markdown(f"""<style>
.stApp{{background:radial-gradient(900px 500px at 8% -8%,#1e3a8a40,transparent 60%),radial-gradient(800px 500px at 100% 0%,#0e749040,transparent 55%),#0B1020}}
.block-container{{padding-top:1.4rem;max-width:1300px}}
header[data-testid="stHeader"]{{background:transparent}}
.hero{{background:linear-gradient(120deg,#22D3EE1f,#A78BFA1f 55%,#F5B9421f);border:1px solid #ffffff18;border-radius:20px;padding:20px 26px;margin-bottom:14px}}
.hero h1{{margin:0;font-size:2rem;background:linear-gradient(90deg,{CYAN},{VIOLET},{AMBER});-webkit-background-clip:text;-webkit-text-fill-color:transparent}}
.hero p{{margin:4px 0 0;color:#94a3b8;font-size:.9rem;line-height:1.55}}
.kpi{{background:#111832d9;border:1px solid #ffffff12;border-radius:16px;padding:14px 16px;height:100%}}
.kpi .l{{font-size:.68rem;letter-spacing:.09em;text-transform:uppercase;color:#94a3b8}}
.kpi .v{{font-size:1.65rem;font-weight:700;line-height:1.25}}
.kpi .s{{font-size:.75rem;color:#94a3b8}}
.sym2{{font-size:1.45rem;font-weight:800;line-height:1.1}}
.head{{font-size:.95rem;line-height:1.45}}
.sub{{font-size:.78rem;color:#94a3b8;margin-top:2px}}
.pl{{font-size:1.45rem;font-weight:800;line-height:1.1;text-align:right}}
.plsub{{font-size:.72rem;color:#94a3b8;text-align:right;margin-bottom:6px}}
.lad2{{position:relative;height:8px;border-radius:6px;margin:12px 2px 4px;background:linear-gradient(90deg,{RED} 0%,{RED} var(--e),{GREEN} var(--e),{GREEN} 100%)}}
.lad2 i{{position:absolute;top:-4px;left:var(--e);width:3px;height:16px;background:#fff;border-radius:2px}}
.lad2 b{{position:absolute;top:-4px;left:var(--c);width:14px;height:14px;border-radius:50%;background:{CYAN};border:2px solid #0B1020;transform:translateX(-50%)}}
.lad-l{{display:flex;justify-content:space-between;font-size:.66rem;color:#94a3b8}}
.chip{{display:inline-block;padding:2px 10px;border-radius:999px;font-size:.66rem;font-weight:700;letter-spacing:.04em;vertical-align:middle;margin-right:4px}}
.pill{{display:inline-block;padding:4px 12px;border-radius:999px;font-weight:700;font-size:.78rem}}
.grid3{{display:grid;grid-template-columns:repeat(auto-fit,minmax(125px,1fr));gap:8px;margin:8px 0 12px}}
.cell{{background:#0B1020aa;border:1px solid #ffffff10;border-radius:10px;padding:8px 10px}}
.cell .l{{font-size:.62rem;color:#94a3b8;letter-spacing:.08em}}
.cell .v{{font-size:1rem;font-weight:700}}
.steps{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;margin:8px 0 12px}}
.step{{background:#0B1020aa;border:1px solid #ffffff10;border-top:3px solid var(--sc);border-radius:12px;padding:10px 12px}}
.step .n{{font-size:.62rem;letter-spacing:.1em;color:var(--sc);font-weight:700}}
.step .d{{font-weight:700;font-size:.92rem;margin:3px 0}}
.step .x{{font-size:.74rem;color:#94a3b8;line-height:1.35}}
div[data-testid="stVerticalBlockBorderWrapper"]{{border-radius:16px}}
.stTabs [data-baseweb="tab-list"]{{gap:6px}}
.stTabs [data-baseweb="tab"]{{background:#111832;border-radius:10px 10px 0 0;padding:8px 18px}}
.stTabs [aria-selected="true"]{{background:linear-gradient(90deg,#22D3EE33,#A78BFA33)}}
</style>""", unsafe_allow_html=True)

# ---------------- helpers ----------------
def has(x):
    return x is not None and not (isinstance(x, float) and np.isnan(x))

def chip(text, color):
    return f'<span class="chip" style="background:{color}26;color:{color};border:1px solid {color}66">{text}</span>'

def kpi(label, value, sub="", color="#E2E8F0"):
    return f'<div class="kpi"><div class="l">{label}</div><div class="v" style="color:{color}">{value}</div><div class="s">{sub}</div></div>'

def money(x, sign=False):
    if not has(x):
        return "–"
    return f"{'+' if sign and x > 0 else ''}{'-' if x < 0 else ''}₹{abs(x):,.0f}"

def pnl_color(x):
    return GREEN if x > 0 else RED if x < 0 else "#E2E8F0"

def fmt_ts(iso):
    try:
        t = datetime.fromisoformat(iso)
        mins = max(int((datetime.now(IST) - t).total_seconds() // 60), 0)
        age = f"{mins} min ago" if mins < 90 else f"{mins // 60} h ago" if mins < 2880 else f"{mins // 1440} days ago"
        return t.astimezone(IST).strftime("%d %b %Y, %I:%M %p IST"), age, mins
    except Exception:
        return None

def style_fig(fig, h=320):
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      margin=dict(l=10, r=10, t=44, b=10), height=h, font=dict(color="#cbd5e1"),
                      xaxis=dict(gridcolor="rgba(148,163,184,.12)"), yaxis=dict(gridcolor="rgba(148,163,184,.12)"))
    return fig

def gauge(value, title, maxv, color, mark=None, suffix=""):
    g = dict(axis=dict(range=[0, maxv], tickcolor="#475569"), bar=dict(color=color, thickness=.7),
             bgcolor="rgba(255,255,255,.06)", borderwidth=0)
    if mark is not None:
        g["threshold"] = dict(line=dict(color="#fff", width=3), thickness=.85, value=mark)
    fig = go.Figure(go.Indicator(mode="gauge+number", value=value, number=dict(suffix=suffix, font=dict(size=34)),
                                 title=dict(text=title, font=dict(size=13, color="#94a3b8")), gauge=g))
    return style_fig(fig, 230)

def status_of(r):
    if r.get("outcome") == "SUCCESS": return "SOLD · PROFIT", GREEN
    if r.get("outcome") == "FAILURE": return "SOLD · LOSS", RED
    return {"PENDING": ("WAITING TO BUY", AMBER), "OPEN": ("HOLDING", CYAN), "EXPIRED": ("NOT BOUGHT", GREY)}.get(r["status"], (r["status"], GREY))

def show_table(df, money_cols=(), price_cols=(), pct_cols=()):
    if df.empty:
        st.caption("Nothing here yet."); return
    try:
        fmt = {**{c_: "₹{:,.0f}" for c_ in money_cols}, **{c_: "{:,.2f}" for c_ in price_cols}, **{c_: "{:+.1f}%" for c_ in pct_cols}}
        s = df.style.format({k: v for k, v in fmt.items() if k in df}, na_rep="–")
        mp = getattr(s, "map", None) or s.applymap
        for c_ in money_cols:
            if c_ in df:
                s = mp(lambda v: f"color:{GREEN};font-weight:700" if isinstance(v, (int, float)) and v > 0
                       else f"color:{RED};font-weight:700" if isinstance(v, (int, float)) and v < 0 else "", subset=[c_])
                mp = getattr(s, "map", None) or s.applymap
        st.dataframe(s, hide_index=True)
    except Exception:
        st.dataframe(df, hide_index=True)

# ---------------- data ----------------
with st.sidebar:
    st.markdown("### Controls")
    if globals().get("LOCAL_RUN_BUTTON", False) and st.button("Run update + scan now", type="primary"):
        with st.spinner("Scanning the market (a few minutes)..."):
            r_ = subprocess.run([sys.executable, "run_daily.py"], capture_output=True, text=True, cwd=BASE)
        st.code((r_.stdout + r_.stderr)[-1200:])
    if st.button("Refresh page"):
        st.rerun()
    st.markdown("### Rules in force")
    st.markdown(f"- Buy limit: **{ENTRY_PULLBACK_ATR} ATR** below close\n- Stop: **{STOP_ATR} ATR**\n- Target: **{TARGET_ATR} ATR**\n"
                f"- Buy order lives: **{PENDING_DAYS} sessions**\n"
                f"- Time limit: **set per stock** from its own history ({MIN_HOLD_DAYS}–{MAX_HOLD_CAP} sessions, {MAX_HOLD_DAYS} if unsure)\n"
                f"- Per trade: **₹{TRADE_AMOUNT:,.0f}** fixed")
    st.caption("Paper trading only. Yahoo Finance data, free.")

c = conn()
trades = pd.read_sql("SELECT * FROM trades ORDER BY id DESC", c)
eq = pd.read_sql("SELECT * FROM equity ORDER BY date", c)
scans = pd.read_sql("SELECT * FROM scans ORDER BY date DESC", c)
ev = pd.read_sql("SELECT * FROM events ORDER BY ts", c)
snaps = pd.read_sql("SELECT * FROM snapshots ORDER BY ts", c)
meta = {r_[0]: r_[1] for r_ in pd.read_sql("SELECT key, value FROM meta", c).values}
for col in ["pnl", "entry", "last_price", "mfe_pct", "mae_pct", "days_held", "max_hold"]:
    trades[col] = pd.to_numeric(trades[col], errors="coerce")
done = trades[trades.outcome.notna()].copy()
done["success"] = (done.outcome == "SUCCESS").astype(int)
feats = pd.DataFrame([json.loads(s) if s else {} for s in done.features], index=done.index)
done = done.join(feats[[x for x in feats.columns if x not in done.columns]])
open_ = trades[trades.status == "OPEN"]

def metrics(d):
    if d.empty:
        return dict(n=0, hit=np.nan, exp=np.nan, pf=np.nan, pnl=0.0, dd=0.0)
    g, l = d.pnl[d.pnl > 0].sum(), -d.pnl[d.pnl < 0].sum()
    cum = d.sort_values("exit_date").pnl.cumsum()
    return dict(n=len(d), hit=d.success.mean() * 100, exp=d.pnl.mean(),
                pf=(g / l) if l > 0 else np.inf, pnl=d.pnl.sum(), dd=(cum - cum.cummax()).min())

m = metrics(done)
unreal = float(((open_.last_price - open_.entry) * open_.qty).sum()) if len(open_) else 0.0
equity = START_CAPITAL + m["pnl"] + unreal
rr = ((done.target - done.entry) / (done.entry - done.stop)).mean() if len(done) else TARGET_ATR / STOP_ATR
breakeven = 100 / (1 + rr)
latest_scan = scans.iloc[0].date if len(scans) else None

# ---------------- hero ----------------
regime = scans.iloc[0].regime if len(scans) else None
pill = (f'<span class="pill" style="background:{GREEN}26;color:{GREEN}">● MARKET OK</span>' if regime == "OK"
        else f'<span class="pill" style="background:{RED}26;color:{RED}">● MARKET WEAK (no new trades)</span>' if regime
        else f'<span class="pill" style="background:{GREY}33;color:#cbd5e1">● NO SCAN YET</span>')
upd, scn = fmt_ts(meta.get("last_update_iso", "")), fmt_ts(meta.get("last_scan_iso", ""))
upd_html = (f'<b>{upd[0]}</b> <span style="color:{GREEN if upd[2] < 120 else AMBER if upd[2] < 4320 else RED}">({upd[1]})</span>'
            if upd else "<b>–</b>")
scn_html = f'<b>{scn[0]}</b> (market data for {latest_scan})' if scn else f'<b>{latest_scan or "–"}</b>'
st.markdown(f'<div class="hero"><h1>SwingLab · NSE Paper Trader</h1><p>Finds 3 swing-trade ideas every day and paper-trades them '
            f'with fake money.<br>Positions updated: {upd_html}<br>Last full scan: {scn_html} &nbsp; {pill}</p></div>', unsafe_allow_html=True)

with st.expander("How to read this dashboard (30 seconds)"):
    st.markdown(f"""
**Each day** after market close, the system scans every NSE stock and picks **3 ideas** (best overall, best under ₹{PRICE_SPLIT}, best ₹{PRICE_SPLIT}+), then places a *paper* buy order for each.

{chip("WAITING TO BUY", AMBER)} the buy order is waiting for the price to dip to the buy limit (cancelled after {PENDING_DAYS} sessions) &nbsp;
{chip("HOLDING", CYAN)} bought, waiting for target or stop &nbsp;
{chip("SOLD · PROFIT", GREEN)} target hit in time &nbsp;
{chip("SOLD · LOSS", RED)} stop hit, gapped below the stop, or the time limit ran out &nbsp;
{chip("NOT BOUGHT", GREY)} the price never reached the buy limit (no loss)

**Time limit:** each stock gets its own limit ({MIN_HOLD_DAYS}–{MAX_HOLD_CAP} sessions), based on how fast that stock's past setups reached their targets. If there isn't enough history, it's {MAX_HOLD_DAYS}.
Tap **Details** on any stock to see when to buy, when to sell, and why it was picked.
""", unsafe_allow_html=True)

# ---------------- KPIs ----------------
k = st.columns(6)
cards = [
    kpi("Virtual equity", money(equity), f"{(equity / START_CAPITAL - 1) * 100:+.2f}% vs start", pnl_color(equity - START_CAPITAL)),
    kpi("Realized P&L", money(m["pnl"], True), f"{m['n']} completed trades", pnl_color(m["pnl"])),
    kpi("Open P&L", money(unreal, True), f"{len(open_)} open positions", pnl_color(unreal)),
    kpi("Avg per trade", money(m["exp"], True) if m["n"] else "–", "after costs", pnl_color(m["exp"] if m["n"] else 0)),
    kpi("Profit factor", ("∞" if m["pf"] == np.inf else f"{m['pf']:.2f}") if m["n"] else "–", "wins ÷ losses (>1.3 is good)",
        GREEN if m["n"] and m["pf"] >= 1.3 else AMBER),
    kpi("Max drawdown", money(m["dd"]) if m["n"] else "–", "worst losing streak", RED if m["dd"] < 0 else "#E2E8F0"),
]
for col, html in zip(k, cards):
    col.markdown(html, unsafe_allow_html=True)

g1, g2, g3 = st.columns([1, 1, 2.4])
g1.plotly_chart(gauge(m["n"], f"TRADES COMPLETED (goal {TARGET_TRADES})", TARGET_TRADES, CYAN), key="g_prog")
g2.plotly_chart(gauge(0 if np.isnan(m["hit"]) else m["hit"], f"TARGET-HIT RATE (white line = break-even {breakeven:.0f}%)",
                      100, GREEN if (m["n"] and m["hit"] >= breakeven) else AMBER, mark=breakeven, suffix="%"), key="g_hit")
if len(eq):
    fig = go.Figure(go.Scatter(x=eq.date, y=eq.equity, mode="lines", line=dict(color=CYAN, width=3),
                               fill="tozeroy", fillcolor="rgba(34,211,238,.10)"))
    lo, hi = eq.equity.min(), eq.equity.max()
    pad = max((hi - lo) * 0.3, 500)
    fig.update_yaxes(range=[lo - pad, hi + pad])
    fig.update_layout(title="Equity curve (virtual ₹)")
    g3.plotly_chart(style_fig(fig, 230), key="g_eq")
else:
    g3.info("The equity curve appears after the first scan.")

with st.expander("Readiness check before using real money"):
    gate = [("100+ completed trades", m["n"] >= TARGET_TRADES),
            ("Positive average P&L after costs", m["n"] > 0 and m["exp"] > 0),
            ("Profit factor ≥ 1.3", m["n"] > 0 and m["pf"] >= 1.3),
            ("Hit rate at least 10 points above break-even", m["n"] > 0 and m["hit"] >= breakeven + 10)]
    for label, ok in gate:
        st.markdown(("✅ " if ok else "⬜ ") + label)
    st.caption(f"With reward:risk of {rr:.1f}, a hit rate above ~{breakeven:.0f}% already breaks even. "
               "A 90% hit rate is not required to profit. Profit and drawdown matter more than hit rate alone.")

# ---------------- per-stock helpers ----------------
def mh(r):
    return int(r["max_hold"]) if has(r.get("max_hold")) else MAX_HOLD_DAYS

REASON = {"TARGET": "Target hit", "TARGET_GAP": "Gapped up past target", "STOP": "Stop hit",
          "STOP_GAP": "Gapped below stop", "TIMEOUT": "Time limit reached"}

def feat_of(r):
    try:
        return json.loads(r["features"]) if r.get("features") else {}
    except Exception:
        return {}

def seen(tid, kinds):
    mm = ev[(ev.trade_id == tid) & (ev.kind.isin(kinds))]
    f_ = fmt_ts(mm.iloc[0].ts) if len(mm) else None
    return f"<br>seen {f_[0]}" if f_ else ""

def step(n, color, title, date, extra):
    return (f'<div class="step" style="--sc:{color}"><div class="n">{n} · {title}</div>'
            f'<div class="d">{date}</div><div class="x">{extra}</div></div>')

def steps_html(r):
    tid, st_, n = r["id"], r["status"], mh(r)
    ws, we = buy_window(r["created_date"])
    bought = has(r["entry_date"])
    dh = int(r["days_held"]) if has(r["days_held"]) else 0
    qty, tgt, stp, pe = r["qty"], r["target"], r["stop"], r["plan_entry"]
    s1 = step(1, GREEN, "PICKED", dfmt(r["created_date"]), "After market close" + seen(tid, ["PICKED"]))
    if bought:
        s2 = step(2, GREEN, "BUY WINDOW", f"{dshort(ws)} → {dshort(we)}", f"Limit ₹{pe:,.2f}<br>filled {dshort(r['entry_date'])}")
        s3 = step(3, GREEN, "BOUGHT", dfmt(r["entry_date"]), f"₹{r['entry']:,.2f} × {qty} = ₹{r['entry'] * qty:,.0f}" + seen(tid, ["FILLED"]))
        sb = sell_by(r["entry_date"], n)
        if st_ == "OPEN":
            s4 = step(4, CYAN, "SELL BY", dfmt(sb), f"Close of session {n}<br>Day {dh} of {n} · {max(n - dh, 0)} left")
        else:
            s4 = step(4, GREY, "SELL BY", dfmt(sb), f"Deadline (sold after {dh} session{'s' if dh != 1 else ''})")
    elif st_ == "EXPIRED":
        s2 = step(2, GREY, "BUY WINDOW", f"{dshort(ws)} → {dshort(we)}", f"Not filled, cancelled {dshort(r['exit_date'])}" + seen(tid, ["EXPIRED"]))
        s3 = step(3, GREY, "BOUGHT", "Never bought", "No money used, no loss")
        s4 = step(4, GREY, "SELL BY", "–", "Not applicable")
    else:
        s2 = step(2, AMBER, "BUY WINDOW", f"{dshort(ws)} → {dshort(we)}", f"Buys when price falls to ₹{pe:,.2f}<br>(cancelled after {dshort(we)})")
        s3 = step(3, GREY, "BOUGHT", "Not yet", "Waiting for the buy limit")
        s4 = step(4, GREY, "SELL BY", f"≈ {dshort(sell_by(ws, n))} earliest", f"{n} sessions after the buy day")
    if st_ == "CLOSED":
        ok_ = r["outcome"] == "SUCCESS"
        s5 = step(5, GREEN if ok_ else RED, "SOLD", dfmt(r["exit_date"]),
                  f"₹{r['exit_price']:,.2f} · {REASON.get(r['exit_reason'], r['exit_reason'])}<br>P&L {money(r['pnl'], True)}"
                  + seen(tid, ["TARGET", "TARGET_GAP", "STOP", "STOP_GAP", "TIMEOUT"]))
    else:
        s5 = step(5, GREY, "SELL TRIGGER", "Target or stop", f"Target ₹{tgt:,.2f} · Stop ₹{stp:,.2f}<br>or the {n}-session limit")
    return '<div class="steps">' + s1 + s2 + s3 + s4 + s5 + '</div>'

def plain_summary(r):
    ws, we = buy_window(r["created_date"])
    n, st_ = mh(r), r["status"]
    if st_ == "PENDING":
        return (f"**What to do:** buy **{r['qty']} shares** at **₹{r['plan_entry']:,.2f}** or lower. The order is active "
                f"**{dfmt(ws)} to {dfmt(we)}**. If the price never falls that low, it's cancelled and nothing is lost. "
                f"Once bought, sell at **₹{r['target']:,.2f}** (profit) or **₹{r['stop']:,.2f}** (loss), or at the close of session {n} if neither happens.")
    if st_ == "OPEN":
        return (f"**Holding:** bought {r['qty']} shares at **₹{r['entry']:,.2f}** on {dfmt(r['entry_date'])}. Sell at "
                f"**₹{r['target']:,.2f}** (profit) or **₹{r['stop']:,.2f}** (loss). Deadline: **{dfmt(sell_by(r['entry_date'], n))}** (session {n}).")
    if st_ == "CLOSED":
        return (f"**Finished:** bought at ₹{r['entry']:,.2f} on {dfmt(r['entry_date'])}, sold at ₹{r['exit_price']:,.2f} on "
                f"{dfmt(r['exit_date'])} ({REASON.get(r['exit_reason'], r['exit_reason'])}). Result: **{money(r['pnl'], True)}**.")
    return f"**Not bought:** the price never reached ₹{r['plan_entry']:,.2f}, so the order was cancelled on {dfmt(r['exit_date'])}. No money used."

def details_body(r):
    f = feat_of(r)
    st.markdown(plain_summary(r))
    tab_a, tab_b, tab_c = st.tabs(["Plan & timeline", "Chart", "Why picked & log"])
    with tab_a:
        e = r["entry"] if has(r["entry"]) else r["plan_entry"]
        basis = "from this stock's own history" if f.get("hold_basis") == "history" else "default (not enough history)"
        cells = [("BUY LIMIT", f"₹{r['plan_entry']:,.2f}", ""),
                 ("STOP", f"₹{r['stop']:,.2f}", f"{(r['stop'] / e - 1) * 100:+.1f}%"),
                 ("TARGET", f"₹{r['target']:,.2f}", f"{(r['target'] / e - 1) * 100:+.1f}%"),
                 ("QUANTITY", f"{int(r['qty'])}", f"₹{e * r['qty']:,.0f}"),
                 ("TIME LIMIT", f"{mh(r)} sessions", basis)]
        st.markdown('<div class="grid3">' + "".join(
            f'<div class="cell"><div class="l">{a}</div><div class="v">{b}</div><div class="sub">{c_}</div></div>' for a, b, c_ in cells) + '</div>',
            unsafe_allow_html=True)
        st.markdown(steps_html(r), unsafe_allow_html=True)
        if r["status"] == "OPEN" and has(r["last_price"]):
            cur = r["last_price"]
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Current price", f"₹{cur:,.2f}")
            m2.metric("P&L so far", money((cur - r["entry"]) * r["qty"], True))
            m3.metric("To target", f"{(r['target'] / cur - 1) * 100:+.1f}%")
            m4.metric("To stop", f"{(r['stop'] / cur - 1) * 100:+.1f}%")
    with tab_b:
        try:
            h = yf.download(f"{r['symbol']}.NS", period="6mo", progress=False, auto_adjust=True)
            if isinstance(h.columns, pd.MultiIndex):
                h.columns = h.columns.get_level_values(0)
            fig = go.Figure(go.Candlestick(x=h.index, open=h.Open, high=h.High, low=h.Low, close=h.Close,
                                           increasing_line_color=GREEN, decreasing_line_color=RED))
            fig.add_hrect(y0=r["stop"], y1=r["plan_entry"], fillcolor=RED, opacity=.12, line_width=0)
            fig.add_hrect(y0=r["plan_entry"], y1=r["target"], fillcolor=GREEN, opacity=.12, line_width=0)
            for nm, y, cl in [("stop", r["stop"], RED), ("buy", r["plan_entry"], CYAN), ("target", r["target"], GREEN)]:
                fig.add_hline(y=y, line_color=cl, line_dash="dash", annotation_text=nm)
            fig.update_layout(xaxis_rangeslider_visible=False)
            st.plotly_chart(style_fig(fig, 420), key=f"cd_{r['id']}")
        except Exception:
            st.caption("Price chart unavailable (no data connection).")
        sn = snaps[snaps.trade_id == r["id"]]
        if len(sn) >= 2:
            fig = go.Figure(go.Scatter(x=sn.ts, y=sn.price, mode="lines+markers", line=dict(color=CYAN, width=2)))
            fig.update_layout(title="Monitored price (one point per update)")
            st.plotly_chart(style_fig(fig, 240), key=f"sn_{r['id']}")
    with tab_c:
        st.markdown(f"**Why it was picked:** {r['rationale']}")
        if f.get("hist_setups"):
            st.markdown(f"**This stock's history:** {f.get('hist_hits', 0)} of {f['hist_setups']} similar setups in the last year reached target"
                        + (f", typically in {f['hist_median_days']} sessions." if f.get("hist_median_days") else "."))
        if r.get("post_mortem"):
            st.markdown(f"**Post-mortem:** {r['post_mortem']}")
        te = ev[ev.trade_id == r["id"]]
        st.markdown("**Monitoring log**")
        if len(te):
            for _, e_ in te.iterrows():
                f_ = fmt_ts(e_.ts)
                st.markdown(f"- `{f_[0] if f_ else e_.ts}` **{e_.kind}**: {e_.note}")
        else:
            st.caption("The log starts from the first update after this feature was installed.")

def open_details(r):
    dlg = getattr(st, "dialog", None) or getattr(st, "experimental_dialog", None)
    if dlg is None:                                  # very old Streamlit: show inline instead
        with st.expander(f"{r['symbol']} details", expanded=True):
            details_body(r)
        return
    try:
        deco = dlg(f"{r['symbol']} · details", width="large")
    except TypeError:
        deco = dlg(f"{r['symbol']} · details")
    deco(lambda: details_body(r))()

def ladder_html(r):
    e = r["entry"] if has(r["entry"]) else r["plan_entry"]
    span = r["target"] - r["stop"]
    pe_ = min(max((e - r["stop"]) / span * 100, 0), 100)
    dot = ""
    if r["status"] == "OPEN" and has(r["last_price"]):
        pc = min(max((r["last_price"] - r["stop"]) / span * 100, 0), 100)
        dot = f'<b style="left:{pc:.1f}%"></b>'
    return (f'<div class="lad2" style="--e:{pe_:.1f}%"><i></i>{dot}</div><div class="lad-l">'
            f'<span style="color:{RED}">Stop ₹{r["stop"]:,.2f}</span><span style="color:{GREEN}">Target ₹{r["target"]:,.2f}</span></div>')

def stock_row(r, new_date):
    lab, col = status_of(r)
    st_, n = r["status"], mh(r)
    ws, we = buy_window(r["created_date"])
    chips = chip(r["track"], TRACK_COL.get(r["track"], GREY)) + chip(lab, col)
    if r["created_date"] == new_date and st_ in ("PENDING", "OPEN"):
        chips += chip("NEW", VIOLET)
    last = r["last_price"] if has(r["last_price"]) else None
    if st_ == "PENDING":
        head = f'<b>Buy at ₹{r["plan_entry"]:,.2f}</b> · window {dshort(ws)} → {dshort(we)}'
        sub = (f"Last price ₹{last:,.2f} ({(r['plan_entry'] / last - 1) * 100:+.1f}% to reach the buy limit)" if last
               else f"Qty {int(r['qty'])} · time limit {n} sessions once bought")
        pl, plsub, plc = "–", "not bought yet", "#94a3b8"
        body = head + f'<div class="sub">{sub}</div>' + ladder_html(r)
    elif st_ == "OPEN":
        cur = last or r["entry"]
        pv = (cur - r["entry"]) * r["qty"]
        head = f'Bought <b>₹{r["entry"]:,.2f}</b> on {dshort(r["entry_date"])} → now <b>₹{cur:,.2f}</b> ({(cur / r["entry"] - 1) * 100:+.1f}%)'
        dh = int(r["days_held"]) if has(r["days_held"]) else 0
        sub = f'Sell by {dshort(sell_by(r["entry_date"], n))} · day {dh} of {n}'
        pl, plsub, plc = money(pv, True), "profit/loss so far", pnl_color(pv)
        body = head + f'<div class="sub">{sub}</div>' + ladder_html(r)
    elif st_ == "CLOSED":
        head = (f'Bought <b>₹{r["entry"]:,.2f}</b> ({dshort(r["entry_date"])}) → sold <b>₹{r["exit_price"]:,.2f}</b> ({dshort(r["exit_date"])})')
        sub = f'{REASON.get(r["exit_reason"], r["exit_reason"])} · held {int(r["days_held"]) if has(r["days_held"]) else 0} sessions'
        pl, plsub, plc = money(r["pnl"], True), "final profit/loss", pnl_color(r["pnl"])
        body = head + f'<div class="sub">{sub}</div>'
    else:
        body = f'Buy order for ₹{r["plan_entry"]:,.2f} expired {dshort(r["exit_date"])}<div class="sub">The price never reached it. No money used.</div>'
        pl, plsub, plc = "₹0", "no trade happened", "#94a3b8"
    with st.container(border=True):
        a, b, c2 = st.columns([2, 4.4, 1.6])
        a.markdown(f'<div class="sym2">{r["symbol"]}</div><div style="margin-top:8px">{chips}</div>', unsafe_allow_html=True)
        b.markdown(f'<div class="head">{body}</div>', unsafe_allow_html=True)
        c2.markdown(f'<div class="pl" style="color:{plc}">{pl}</div><div class="plsub">{plsub}</div>', unsafe_allow_html=True)
        if c2.button("Details", key=f"det_{r['id']}"):
            open_details(r)

# ---------------- tabs ----------------
tab_stocks, tab_perf, tab_learn = st.tabs(["Stocks", "Performance", "Learning"])

with tab_stocks:
    if len(scans):
        picks = json.loads(scans.iloc[0].picks)
        miss = [f"**{TRACK_NAME[t_]}**: {p_.get('reason', '')}" for t_, p_ in picks.items() if not p_.get("trade")]
        if miss:
            st.info(f"No pick on {scans.iloc[0].date} for " + " · ".join(miss))
    f1, f2 = st.columns([1.3, 2])
    view = f1.radio("Show", ["Active", "Completed", "All"], horizontal=True)
    tsel = f2.multiselect("Tracks", ["BEST", "LOW", "HIGH"], default=["BEST", "LOW", "HIGH"])
    sub = trades[trades.track.isin(tsel)].copy()
    if view == "Active":
        sub = sub[sub.status.isin(["PENDING", "OPEN"])]
    elif view == "Completed":
        sub = sub[sub.status.isin(["CLOSED", "EXPIRED"])]
    sub["_o"] = sub.status.map({"OPEN": 0, "PENDING": 1, "CLOSED": 2, "EXPIRED": 3})
    sub = sub.sort_values(["_o", "id"], ascending=[True, False])
    if sub.empty:
        st.info("No stocks in this view yet. They appear after the first scan.")
    else:
        st.caption(f"{len(sub)} stock{'s' if len(sub) != 1 else ''}. Tap **Details** on any stock for the full plan.")
        show_all = st.checkbox("Show all", value=False) if len(sub) > 20 else True
        for _, r_ in (sub if show_all else sub.head(20)).iterrows():
            stock_row(r_.to_dict(), latest_scan)
    if len(scans):
        cands = json.loads(scans.iloc[0].candidates)
        if cands:
            with st.expander(f"Latest scan: all {len(cands)} candidates that passed the filters"):
                cd = pd.DataFrame(cands)
                keep = [x for x in ["symbol", "close", "rsi", "volume_ratio", "ret_63d_pct", "atr_pct", "hold_days", "score"] if x in cd]
                show_table(cd[keep], price_cols=["close"])

with tab_perf:
    cols = st.columns(3)
    for col, tr in zip(cols, ["BEST", "LOW", "HIGH"]):
        mm, cc = metrics(done[done.track == tr]), TRACK_COL[tr]
        col.markdown(f'<div class="kpi" style="border-top:4px solid {cc}"><div class="l" style="color:{cc}">{TRACK_NAME[tr]}</div>'
                     f'<div class="v" style="color:{pnl_color(mm["pnl"])}">{money(mm["pnl"], True)}</div>'
                     f'<div class="s">{mm["n"]} completed · hit rate {("%.0f%%" % mm["hit"]) if mm["n"] else "–"} · '
                     f'avg {money(mm["exp"], True) if mm["n"] else "–"}</div></div>', unsafe_allow_html=True)
    if done.empty:
        st.info("Charts appear after the first completed trade.")
    else:
        d2 = done.sort_values("exit_date").assign(cum=lambda x: x.groupby("track").pnl.cumsum())
        st.plotly_chart(style_fig(px.line(d2, x="exit_date", y="cum", color="track", color_discrete_map=TRACK_COL,
                                          title="Cumulative P&L by track", markers=True), 300), key="p_cum")
        c1, c2 = st.columns([1, 2.2])
        cnt = done.exit_reason.value_counts().reset_index()
        cnt.columns = ["reason", "count"]
        cmap = {"TARGET": GREEN, "TARGET_GAP": GREEN, "STOP": RED, "STOP_GAP": "#be123c", "TIMEOUT": AMBER}
        c1.plotly_chart(style_fig(px.pie(cnt, names="reason", values="count", hole=.62, color="reason",
                                         color_discrete_map=cmap, title="How trades ended"), 320), key="p_pie")
        dd = done.sort_values("exit_date")
        fig = px.bar(dd, x="symbol", y="pnl", color=dd.pnl.gt(0), color_discrete_map={True: GREEN, False: RED},
                     title="P&L of each completed trade")
        fig.update_layout(showlegend=False)
        c2.plotly_chart(style_fig(fig, 320), key="p_bar")

with tab_learn:
    fails = done[done.outcome == "FAILURE"]
    if fails.empty:
        st.info("No losing trades yet. When one happens, the cause is analysed here.")
    else:
        tags = fails.failure_tags.str.split(",").explode().value_counts().reset_index()
        tags.columns = ["cause", "count"]
        fig = px.bar(tags.sort_values("count"), x="count", y="cause", orientation="h", color="count",
                     color_continuous_scale=["#7c2d12", RED], title="Why trades failed (one trade can have several causes)")
        fig.update_layout(coloraxis_showscale=False)
        st.plotly_chart(style_fig(fig, 320), key="l_tags")
        show_table(fails[["symbol", "track", "exit_reason", "failure_tags", "pnl"]].rename(
            columns={"symbol": "Stock", "track": "Track", "exit_reason": "Ended by", "failure_tags": "Causes", "pnl": "P&L"}),
            money_cols=["P&L"])
        st.caption("Open a stock's Details → 'Why picked & log' for its full post-mortem.")
    if len(done) < 20:
        st.info(f"Pattern analysis unlocks at 20 completed trades (you have {len(done)}). With fewer, patterns are mostly luck.")
    else:
        overall = done.success.mean() * 100
        specs = [("rsi", [0, 55, 65, 100], ["<55", "55-65", ">65"], "RSI at entry"),
                 ("volume_ratio", [0, 1.5, 3, 100], ["<1.5x", "1.5-3x", ">3x"], "Volume vs average"),
                 ("ret_63d_pct", [-100, 20, 50, 1000], ["<20%", "20-50%", ">50%"], "63-day run-up"),
                 ("atr_pct", [0, 2, 4, 100], ["<2%", "2-4%", ">4%"], "Volatility (ATR % of price)"),
                 ("pct_below_20d_high", [-1, 1, 3, 100], ["<1%", "1-3%", ">3%"], "Distance below 20-day high")]
        tips, cols = [], st.columns(2)
        for i, (col, bins, labels, title) in enumerate(specs):
            if col not in done:
                continue
            d = done.assign(bucket=pd.cut(done[col], bins=bins, labels=labels))
            g = d.groupby("bucket", observed=True).agg(n=("id", "count"), hit=("success", "mean")).reset_index()
            g["hit"] = g.hit * 100
            fig = go.Figure(go.Bar(x=g.bucket.astype(str), y=g.hit, text=[f"{h:.0f}%<br>n={n}" for h, n in zip(g.hit, g.n)],
                                   marker_color=[GREEN if h >= overall else RED for h in g.hit]))
            fig.add_hline(y=overall, line_dash="dot", line_color="#fff", annotation_text=f"overall {overall:.0f}%")
            fig.update_layout(title=title, yaxis_range=[0, 100])
            cols[i % 2].plotly_chart(style_fig(fig, 280), key=f"l_{col}")
            for _, r_ in g.iterrows():
                if r_.n >= 8 and r_.hit < overall - 15:
                    tips.append(f"**{title} {r_.bucket}**: only {r_.hit:.0f}% hit rate over {int(r_.n)} trades (overall {overall:.0f}%). "
                                "Consider tightening that filter in `config.py`.")
        st.markdown("#### Suggestions")
        for t_ in tips or ["No bucket is clearly weaker yet."]:
            st.markdown("• " + t_)
        st.caption("Suggestions only. Small samples overfit easily: change one filter at a time and re-test on new trades.")
