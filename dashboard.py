import json, subprocess, sys
import numpy as np, pandas as pd, streamlit as st
import plotly.graph_objects as go, plotly.express as px, yfinance as yf
from config import *
from db import conn

st.set_page_config("SwingLab | NSE Paper Trader", page_icon="📈", layout="wide")

GREEN, RED, AMBER, CYAN, VIOLET, GREY = "#34D399", "#F43F5E", "#F5B942", "#22D3EE", "#A78BFA", "#64748B"
TRACK_COL = {"BEST": AMBER, "LOW": CYAN, "HIGH": VIOLET}
TRACK_NAME = {"BEST": "BEST OVERALL", "LOW": f"UNDER ₹{PRICE_SPLIT}", "HIGH": f"₹{PRICE_SPLIT} & ABOVE"}

st.markdown(f"""<style>
.stApp{{background:radial-gradient(900px 500px at 8% -8%,#1e3a8a40,transparent 60%),radial-gradient(800px 500px at 100% 0%,#0e749040,transparent 55%),#0B1020}}
.block-container{{padding-top:1.4rem;max-width:1450px}}
header[data-testid="stHeader"]{{background:transparent}}
.hero{{background:linear-gradient(120deg,#22D3EE1f,#A78BFA1f 55%,#F5B9421f);border:1px solid #ffffff18;border-radius:20px;padding:20px 26px;margin-bottom:14px}}
.hero h1{{margin:0;font-size:2rem;background:linear-gradient(90deg,{CYAN},{VIOLET},{AMBER});-webkit-background-clip:text;-webkit-text-fill-color:transparent}}
.hero p{{margin:4px 0 0;color:#94a3b8;font-size:.92rem}}
.kpi{{background:#111832d9;border:1px solid #ffffff12;border-radius:16px;padding:14px 16px;height:100%}}
.kpi .l{{font-size:.68rem;letter-spacing:.09em;text-transform:uppercase;color:#94a3b8}}
.kpi .v{{font-size:1.65rem;font-weight:700;line-height:1.25}}
.kpi .s{{font-size:.75rem;color:#94a3b8}}
.pick{{background:#111832e6;border:1px solid #ffffff12;border-top:4px solid var(--c);border-radius:16px;padding:16px 18px;height:100%}}
.pick .tag{{font-size:.7rem;letter-spacing:.12em;font-weight:700}}
.pick .sym{{font-size:1.7rem;font-weight:800;margin:2px 0 8px}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:8px 0 12px}}
.cell{{background:#0B1020aa;border-radius:10px;padding:8px 10px}}
.cell .l{{font-size:.62rem;color:#94a3b8;letter-spacing:.08em}}
.cell .v{{font-size:1rem;font-weight:700}}
.ladder{{position:relative;height:10px;border-radius:6px;margin:14px 2px 6px;background:linear-gradient(90deg,{RED} 0%,{RED} var(--e),{GREEN} var(--e),{GREEN} 100%)}}
.ladder i{{position:absolute;top:-5px;left:var(--e);width:3px;height:20px;background:#fff;border-radius:2px}}
.lad-l{{display:flex;justify-content:space-between;font-size:.66rem;color:#94a3b8}}
.chip{{display:inline-block;padding:2px 10px;border-radius:999px;font-size:.68rem;font-weight:700;letter-spacing:.04em;vertical-align:middle}}
.muted{{color:#94a3b8;font-size:.82rem}}
.pill{{display:inline-block;padding:4px 12px;border-radius:999px;font-weight:700;font-size:.78rem}}
.stTabs [data-baseweb="tab-list"]{{gap:6px}}
.stTabs [data-baseweb="tab"]{{background:#111832;border-radius:10px 10px 0 0;padding:8px 16px}}
.stTabs [aria-selected="true"]{{background:linear-gradient(90deg,#22D3EE33,#A78BFA33)}}
</style>""", unsafe_allow_html=True)

def chip(text, color):
    return f'<span class="chip" style="background:{color}26;color:{color};border:1px solid {color}66">{text}</span>'

def kpi(label, value, sub="", color="#E2E8F0"):
    return f'<div class="kpi"><div class="l">{label}</div><div class="v" style="color:{color}">{value}</div><div class="s">{sub}</div></div>'

def money(x, sign=False):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "–"
    return f"{'+' if sign and x > 0 else ''}{'-' if x < 0 else ''}₹{abs(x):,.0f}"

def pnl_color(x):
    return GREEN if x > 0 else RED if x < 0 else "#E2E8F0"

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
    if r.get("outcome") == "SUCCESS": return "SUCCESS", GREEN
    if r.get("outcome") == "FAILURE": return "FAILED", RED
    return {"PENDING": ("PENDING", AMBER), "OPEN": ("OPEN", CYAN), "EXPIRED": ("EXPIRED", GREY)}.get(r["status"], (r["status"], GREY))

def show_table(df, money_cols=(), price_cols=(), pct_cols=()):
    if df.empty:
        st.caption("Nothing here yet."); return
    try:
        fmt = {**{c: "₹{:,.0f}" for c in money_cols}, **{c: "{:,.2f}" for c in price_cols}, **{c: "{:+.1f}%" for c in pct_cols}}
        s = df.style.format({k: v for k, v in fmt.items() if k in df}, na_rep="–")
        mp = getattr(s, "map", None) or s.applymap
        for c in money_cols:
            if c in df:
                s = mp(lambda v: f"color:{GREEN};font-weight:700" if isinstance(v, (int, float)) and v > 0
                       else f"color:{RED};font-weight:700" if isinstance(v, (int, float)) and v < 0 else "", subset=[c])
                mp = getattr(s, "map", None) or s.applymap
        st.dataframe(s, hide_index=True)
    except Exception:
        st.dataframe(df, hide_index=True)

# ---------------- data ----------------
with st.sidebar:
    st.markdown("### Controls")
    if LOCAL_RUN_BUTTON and st.button("Run update + scan now", type="primary"):
        with st.spinner("Scanning the market (a few minutes)..."):
            r = subprocess.run([sys.executable, "run_daily.py"], capture_output=True, text=True, cwd=BASE)
        st.code((r.stdout + r.stderr)[-1200:])
    if st.button("Refresh page"):
        st.rerun()
    st.markdown("### Rules in force")
    st.markdown(f"- Buy limit: **{ENTRY_PULLBACK_ATR} ATR** below close\n- Stop: **{STOP_ATR} ATR**\n- Target: **{TARGET_ATR} ATR**\n"
                f"- Max wait for entry: **{PENDING_DAYS} days**\n- Max hold: **{MAX_HOLD_DAYS} trading days**\n"
                f"- Per trade: **₹{TRADE_AMOUNT:,.0f}** fixed")
    st.caption("Paper trading only. Yahoo Finance data, free.")

c = conn()
trades = pd.read_sql("SELECT * FROM trades ORDER BY id DESC", c)
eq = pd.read_sql("SELECT * FROM equity ORDER BY date", c)
scans = pd.read_sql("SELECT * FROM scans ORDER BY date DESC", c)
for col in ["pnl", "entry", "last_price", "mfe_pct", "mae_pct", "days_held"]:
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

# ---------------- hero ----------------
regime = scans.iloc[0].regime if len(scans) else None
pill = (f'<span class="pill" style="background:{GREEN}26;color:{GREEN}">● MARKET OK</span>' if regime == "OK"
        else f'<span class="pill" style="background:{RED}26;color:{RED}">● MARKET WEAK (no new trades)</span>' if regime
        else f'<span class="pill" style="background:{GREY}33;color:#cbd5e1">● NO SCAN YET</span>')
last = scans.iloc[0].date if len(scans) else "–"
st.markdown(f'<div class="hero"><h1>SwingLab · NSE Paper Trader</h1><p>Finds 3 swing-trade ideas every day, '
            f'paper-trades them with fake money, and learns from every failure. Last scan: <b>{last}</b> &nbsp; {pill}</p></div>',
            unsafe_allow_html=True)

with st.expander("How to read this dashboard (30 seconds)"):
    st.markdown(f"""
**The daily cycle:** after market close the system scans every NSE stock → picks **3 ideas** (best overall, best under ₹{PRICE_SPLIT}, best ₹{PRICE_SPLIT}+) → places a *paper* buy order.

{chip("PENDING", AMBER)} waiting for the price to dip to the buy limit (cancelled after {PENDING_DAYS} days) &nbsp;
{chip("OPEN", CYAN)} bought, waiting for target or stop &nbsp;
{chip("SUCCESS", GREEN)} target hit within {MAX_HOLD_DAYS} days &nbsp;
{chip("FAILED", RED)} stop hit, gapped below the stop, or no target by day {MAX_HOLD_DAYS} &nbsp;
{chip("EXPIRED", GREY)} never bought (no loss)

**Price bar on each card:** left end = stop (loss), right end = target (profit), white line = buy price. **ATR** = the stock's typical daily move, used to size stop and target.
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

t0, t1, t2, t3, t4, t5, t6 = st.tabs(["Today's 3 picks", "Tracks", "Positions", "History", "Failure analysis", "Lessons", "Trade detail"])

# ---------------- Today ----------------
with t0:
    if scans.empty:
        st.info("No scan yet. Click **Run update + scan now** in the sidebar.")
    else:
        s = scans.iloc[0]
        picks = json.loads(s.picks)
        cols = st.columns(3)
        for col, tr in zip(cols, ["BEST", "LOW", "HIGH"]):
            p, cc = picks.get(tr, {}), TRACK_COL[tr]
            if not p.get("trade"):
                col.markdown(f'<div class="pick" style="--c:{cc}"><div class="tag" style="color:{cc}">{TRACK_NAME[tr]}</div>'
                             f'<div class="sym">No trade</div><div class="muted">{p.get("reason", "")}</div></div>', unsafe_allow_html=True)
                continue
            row = trades[(trades.track == tr) & (trades.created_date == s.date) & (trades.symbol == p["symbol"])]
            stt = chip(*status_of(row.iloc[0].to_dict())) if len(row) else ""
            e, st_, tg = p["entry"], p["stop"], p["target"]
            pos = (e - st_) / (tg - st_) * 100
            html = (f'<div class="pick" style="--c:{cc}"><div class="tag" style="color:{cc}">{TRACK_NAME[tr]}</div>'
                    f'<div class="sym">{p["symbol"]} {stt}</div>'
                    f'<div class="grid"><div class="cell"><div class="l">BUY LIMIT</div><div class="v">₹{e:,.2f}</div></div>'
                    f'<div class="cell"><div class="l">STOP</div><div class="v" style="color:{RED}">₹{st_:,.2f}</div></div>'
                    f'<div class="cell"><div class="l">TARGET</div><div class="v" style="color:{GREEN}">₹{tg:,.2f}</div></div>'
                    f'<div class="cell"><div class="l">QTY</div><div class="v">{p["qty"]}</div></div></div>'
                    f'<div class="ladder" style="--e:{pos:.1f}%"><i></i></div>'
                    f'<div class="lad-l"><span style="color:{RED}">risk -{(e - st_) / e * 100:.1f}%</span>'
                    f'<span style="color:{GREEN}">reward +{(tg - e) / e * 100:.1f}%</span></div>'
                    f'<div class="muted" style="margin-top:10px">{p["rationale"]}</div></div>')
            col.markdown(html, unsafe_allow_html=True)
        cands = json.loads(s.candidates)
        if cands:
            with st.expander(f"All {len(cands)} candidates that passed the filters on {s.date}"):
                show_table(pd.DataFrame(cands), price_cols=["close", "sma20", "sma50", "atr", "support_10d"])

# ---------------- Tracks ----------------
with t1:
    cols = st.columns(3)
    for col, tr in zip(cols, ["BEST", "LOW", "HIGH"]):
        mm, cc = metrics(done[done.track == tr]), TRACK_COL[tr]
        with col:
            st.markdown(f'<div class="kpi" style="border-top:4px solid {cc}"><div class="l" style="color:{cc}">{TRACK_NAME[tr]}</div>'
                        f'<div class="v" style="color:{pnl_color(mm["pnl"])}">{money(mm["pnl"], True)}</div>'
                        f'<div class="s">{mm["n"]} completed · hit rate {("%.0f%%" % mm["hit"]) if mm["n"] else "–"} · '
                        f'avg {money(mm["exp"], True) if mm["n"] else "–"}</div></div>', unsafe_allow_html=True)
            sub = trades[trades.track == tr].head(12).copy()
            sub["state"] = [status_of(r.to_dict())[0] for _, r in sub.iterrows()]
            show_table(sub[["id", "symbol", "state", "pnl"]], money_cols=["pnl"])
    if not done.empty:
        d2 = done.sort_values("exit_date").assign(cum=lambda x: x.groupby("track").pnl.cumsum())
        fig = px.line(d2, x="exit_date", y="cum", color="track", color_discrete_map=TRACK_COL,
                      title="Cumulative P&L by track", markers=True)
        st.plotly_chart(style_fig(fig, 300), key="trk_cum")

# ---------------- Positions ----------------
with t2:
    act = trades[trades.status.isin(["OPEN", "PENDING"])].copy()
    if len(act):
        act["unrealized"] = (act.last_price - act.entry) * act.qty
        act["to_target_%"] = (act.target / act.last_price.fillna(act.plan_entry) - 1) * 100
    show_table(act[["id", "track", "symbol", "status", "created_date", "plan_entry", "entry", "stop", "target", "qty",
                    "last_price", "days_held", "unrealized"]] if len(act) else act,
               money_cols=["unrealized"], price_cols=["plan_entry", "entry", "stop", "target", "last_price"])

# ---------------- History ----------------
with t3:
    hist = trades[trades.status.isin(["CLOSED", "EXPIRED"])].copy()
    c1, c2 = st.columns([1, 2.2])
    if not done.empty:
        cnt = done.exit_reason.value_counts().reset_index()
        cnt.columns = ["reason", "count"]
        cmap = {"TARGET": GREEN, "TARGET_GAP": GREEN, "STOP": RED, "STOP_GAP": "#be123c", "TIMEOUT": AMBER}
        c1.plotly_chart(style_fig(px.pie(cnt, names="reason", values="count", hole=.62, color="reason",
                                         color_discrete_map=cmap, title="How trades ended"), 320), key="h_pie")
        fig = px.bar(done.sort_values("exit_date"), x="id", y="pnl", color=done.sort_values("exit_date").pnl.gt(0),
                     color_discrete_map={True: GREEN, False: RED}, title="P&L of each completed trade")
        fig.update_layout(showlegend=False)
        c2.plotly_chart(style_fig(fig, 320), key="h_bar")
    show_table(hist[["id", "track", "symbol", "outcome", "entry_date", "exit_date", "days_held", "entry", "exit_price",
                     "exit_reason", "qty", "pnl", "mfe_pct", "mae_pct"]],
               money_cols=["pnl"], price_cols=["entry", "exit_price"], pct_cols=["mfe_pct", "mae_pct"])
    st.caption("mfe = best price move while open, mae = worst dip while open.")

# ---------------- Failure analysis ----------------
with t4:
    fails = done[done.outcome == "FAILURE"]
    if fails.empty:
        st.info("No failed trades yet. When one fails, its post-mortem appears here.")
    else:
        tags = fails.failure_tags.str.split(",").explode().value_counts().reset_index()
        tags.columns = ["cause", "count"]
        fig = px.bar(tags.sort_values("count"), x="count", y="cause", orientation="h", color="count",
                     color_continuous_scale=["#7c2d12", RED], title="Why trades failed (one trade can have several causes)")
        fig.update_layout(coloraxis_showscale=False)
        st.plotly_chart(style_fig(fig, 320), key="f_tags")
        st.markdown("#### Post-mortem of each failure")
        for _, r in fails.iterrows():
            with st.expander(f"#{r.id} {r.symbol} ({r.track}) · {r.exit_reason} · {money(r.pnl, True)} · {r.failure_tags}"):
                st.write(r.post_mortem)

# ---------------- Lessons ----------------
with t5:
    if len(done) < 20:
        st.info(f"Lessons unlock at 20 completed trades (you have {len(done)}). With fewer, patterns are mostly luck.")
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
            for _, r in g.iterrows():
                if r.n >= 8 and r.hit < overall - 15:
                    tips.append(f"**{title} {r.bucket}**: only {r.hit:.0f}% hit rate over {int(r.n)} trades (overall {overall:.0f}%). "
                                "Consider tightening that filter in `config.py`.")
        st.markdown("#### Suggestions")
        for t_ in tips or ["No bucket is clearly weaker yet."]:
            st.markdown("• " + t_)
        st.caption("Suggestions only. Small samples overfit easily: change one filter at a time and re-test on new trades.")

# ---------------- Trade detail ----------------
with t6:
    if trades.empty:
        st.write("No trades yet.")
    else:
        pick = st.selectbox("Choose a trade", [f"#{r.id} {r.symbol} ({r.track}, {status_of(r.to_dict())[0]})" for _, r in trades.iterrows()])
        t = trades[trades.id == int(pick.split()[0][1:])].iloc[0]
        lab, colr = status_of(t.to_dict())
        st.markdown(f"### {t.symbol} {chip(lab, colr)} {chip(t.track, TRACK_COL.get(t.track, GREY))}", unsafe_allow_html=True)
        a, b_, c_, d_ = st.columns(4)
        a.metric("Buy limit", f"₹{t.plan_entry:,.2f}")
        b_.metric("Stop", f"₹{t.stop:,.2f}")
        c_.metric("Target", f"₹{t.target:,.2f}")
        d_.metric("P&L", money(t.pnl, True) if pd.notna(t.pnl) else "open")
        st.write(f"**Why picked:** {t.rationale}")
        if t.post_mortem:
            st.write(f"**Post-mortem:** {t.post_mortem}")
        try:
            h = yf.download(f"{t.symbol}.NS", period="6mo", progress=False, auto_adjust=True)
            if isinstance(h.columns, pd.MultiIndex):
                h.columns = h.columns.get_level_values(0)
            fig = go.Figure(go.Candlestick(x=h.index, open=h.Open, high=h.High, low=h.Low, close=h.Close,
                                           increasing_line_color=GREEN, decreasing_line_color=RED))
            fig.add_hrect(y0=t.stop, y1=t.plan_entry, fillcolor=RED, opacity=.12, line_width=0)
            fig.add_hrect(y0=t.plan_entry, y1=t.target, fillcolor=GREEN, opacity=.12, line_width=0)
            for name, y, cl in [("stop", t.stop, RED), ("buy", t.plan_entry, CYAN), ("target", t.target, GREEN)]:
                fig.add_hline(y=y, line_color=cl, line_dash="dash", annotation_text=name)
            fig.update_layout(xaxis_rangeslider_visible=False)
            st.plotly_chart(style_fig(fig, 460), key="td_chart")
        except Exception:
            st.caption("Chart unavailable (no data connection).")
