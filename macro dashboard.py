#!/usr/bin/env python3
"""
Macro Risk Dashboard
====================
Fetches 11 market indicators and writes risk_dashboard.html

SETUP (run once):
    pip install requests yfinance

RUN:
    python macro_dashboard.py
"""

import io, csv, sys, datetime, os

try:
    import requests
except ImportError:
    sys.exit("Run:  pip install requests yfinance")

# ── Fallback values (used if live fetch fails) ─────────────────────────────
FALLBACK = {
    "VIX": 18.9,  "VVIX": 91.0,  "SKEW": 145.0, "MOVE": 69.0,
    "FNG": 50,    "FNG_RATING": "Neutral",
    "US10Y": 4.40, "US2Y": 4.13, "T10Y2Y": 0.27, "HYOAS": 2.63,
    "HYG": 79.85, "LQD": 109.50, "DXY": 100.5,
}

# ── Data fetchers ──────────────────────────────────────────────────────────
def _fred_latest(series_id):
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=" + series_id
    r = requests.get(url, timeout=25)
    r.raise_for_status()
    rows = list(csv.reader(io.StringIO(r.text)))
    for row in reversed(rows[1:]):
        if len(row) >= 2 and row[1] not in (".", "", "NaN"):
            return float(row[1])
    return None

def _yf_last(ticker):
    import yfinance as yf
    hist = yf.Ticker(ticker).history(period="5d")
    closes = hist["Close"].dropna() if len(hist) else []
    return float(closes.iloc[-1]) if len(closes) else None

def _fng_label(score):
    if score <= 24:   return "Extreme Fear"
    if score <= 44:   return "Fear"
    if score <= 55:   return "Neutral"
    if score <= 75:   return "Greed"
    return "Extreme Greed"

def _cnn_fng():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.cnn.com/markets/fear-and-greed",
        "Origin": "https://www.cnn.com",
    }
    urls = [
        "https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
        "https://production.dataviz.cnn.io/index/fearandgreed/graphdata/",
    ]
    for url in urls:
        try:
            r = requests.get(url, headers=headers, timeout=25)
            r.raise_for_status()
            data = r.json()
            if "fear_and_greed" in data:
                fg = data["fear_and_greed"]
                score = round(float(fg["score"]))
                rating = str(fg.get("rating", _fng_label(score))).title()
                return score, rating
            elif "score" in data:
                score = round(float(data["score"]))
                rating = str(data.get("rating", _fng_label(score))).title()
                return score, rating
        except Exception:
            continue
    raise ValueError("All CNN endpoints failed")

def _safe(fn, *args):
    try:
        return fn(*args)
    except Exception as exc:
        print("  [warn] %s%s -> %s" % (fn.__name__, args, exc), file=sys.stderr)
        return None

def gather():
    d = dict(FALLBACK)
    print("Fetching live indicators...")

    for key, tkr in [("VIX","^VIX"),("VVIX","^VVIX"),("SKEW","^SKEW"),
                     ("MOVE","^MOVE"),("HYG","HYG"),("LQD","LQD"),("DXY","DX-Y.NYB")]:
        v = _safe(_yf_last, tkr)
        if v is not None:
            d[key] = round(v, 2)

    for key, sid in [("US10Y","DGS10"),("US2Y","DGS2"),
                     ("T10Y2Y","T10Y2Y"),("HYOAS","BAMLH0A0HYM2")]:
        v = _safe(_fred_latest, sid)
        if v is not None:
            d[key] = v

    fng = _safe(_cnn_fng)
    if fng:
        d["FNG"], d["FNG_RATING"] = fng

    d["HYG_LQD"] = round(d["HYG"] / d["LQD"], 3) if d.get("HYG") and d.get("LQD") else None
    return d

# ── Signal logic ────────────────────────────────────────────────────────────
def _band(v, calm_hi, elev_hi, calm_lbl, elev_lbl, stress_lbl):
    if v < calm_hi:   return (calm_lbl, "green")
    if v <= elev_hi:  return (elev_lbl, "amber")
    return (stress_lbl, "red")

def sig_vix(v):    return _band(v, 16, 25,   "Calm",      "Elevated",  "Stress")
def sig_vvix(v):   return _band(v, 95, 110,  "Normal",    "Elevated",  "Stress")
def sig_skew(v):   return _band(v, 135, 150, "Calm",      "Elevated",  "Stress")
def sig_move(v):   return _band(v, 90, 130,  "Contained", "Elevated",  "Stress")
def sig_10y(v):    return _band(v, 3.5, 4.5, "Low",       "Firm",      "High")
def sig_2y(v):     return _band(v, 3.5, 4.5, "Low",       "Firm",      "High")
def sig_hyoas(v):  return _band(v, 3.5, 5.0, "Tight",     "Widening",  "Stressed")
def sig_dxy(v):    return _band(v, 100, 105, "Weak",      "Moderate",  "Strong")

def sig_fng(score, rating):
    if score < 25:    cls = "red"
    elif score < 45:  cls = "amber"
    elif score <= 75: cls = "green"
    else:             cls = "amber"
    return (rating, cls)

def sig_2s10s(v):
    if v < 0:     return ("Inverted", "red")
    if v < 0.20:  return ("Flat",     "amber")
    return ("Normal", "green")

def sig_ratio(hyoas):
    if hyoas < 3.5:  return ("Stable", "green")
    if hyoas < 5.0:  return ("Soft",   "amber")
    return ("Weak", "red")

# ── HTML builder ────────────────────────────────────────────────────────────
CSS = """
*{box-sizing:border-box;margin:0;padding:0;}
body{background:#0d1117;font-family:system-ui,sans-serif;padding:32px;color:#f1f5f9;}
.container{max-width:1100px;margin:0 auto;}
h1{font-size:28px;font-weight:800;color:#f8fafc;margin-bottom:4px;}
.subtitle{font-size:13px;color:#64748b;font-family:monospace;margin-bottom:24px;}
.banner{border-radius:14px;border:2px solid;padding:16px 22px;margin-bottom:24px;}
.banner p{font-size:13px;color:#cbd5e1;line-height:1.65;margin-top:6px;}
.sig-row{display:flex;align-items:center;gap:10px;}
.sig-label{font-size:15px;font-weight:700;font-family:monospace;letter-spacing:.1em;}
.date-tag{font-size:11px;color:#64748b;font-family:monospace;margin-left:auto;}
.dot{border-radius:50%;display:inline-block;flex-shrink:0;}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px;}
.tile{border-radius:12px;border:1px solid;padding:16px 18px;}
.tile-top{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px;}
.tile-desc{font-size:10px;color:#64748b;font-family:monospace;letter-spacing:.08em;text-transform:uppercase;}
.tile-label{font-size:13px;font-weight:600;color:#f1f5f9;margin-top:2px;}
.tile-val{font-size:28px;font-weight:700;font-family:monospace;color:#f8fafc;line-height:1;margin-bottom:8px;}
.tile-note{font-size:11px;line-height:1.5;}
.tile-levels{display:flex;gap:0;margin-top:10px;border-radius:6px;overflow:hidden;font-size:10px;font-family:monospace;}
.lvl{flex:1;text-align:center;padding:4px 2px;font-weight:700;letter-spacing:.04em;}
.lvl-green{background:#14532d;color:#86efac;}
.lvl-amber{background:#78350f;color:#fde68a;}
.lvl-red{background:#7f1d1d;color:#fca5a5;}
.lvl-active-green{background:#22c55e;color:#052e16;}
.lvl-active-amber{background:#f59e0b;color:#422006;}
.lvl-active-red{background:#ef4444;color:#2d0a0a;}
.pill{display:inline-block;font-size:11px;font-weight:700;letter-spacing:.06em;padding:3px 10px;border-radius:999px;text-transform:uppercase;}
.green-tile{background:#052e16;border-color:#166534;}
.green-note{color:#4ade80;}
.green-pill{background:#14532d;color:#86efac;border:1px solid #166534;}
.amber-tile{background:#422006;border-color:#92400e;}
.amber-note{color:#fbbf24;}
.amber-pill{background:#78350f;color:#fde68a;border:1px solid #92400e;}
.red-tile{background:#2d0a0a;border-color:#991b1b;}
.red-note{color:#f87171;}
.red-pill{background:#7f1d1d;color:#fca5a5;border:1px solid #991b1b;}
.green-banner{background:#052e16;border-color:#166534;}
.amber-banner{background:#422006;border-color:#92400e;}
.red-banner{background:#2d0a0a;border-color:#991b1b;}
.section-title{font-size:11px;color:#475569;font-family:monospace;text-transform:uppercase;letter-spacing:.14em;margin:22px 0 10px;}
.legend{display:flex;gap:20px;margin-top:22px;padding-top:16px;border-top:1px solid #1e293b;align-items:center;flex-wrap:wrap;}
.legend-item{display:flex;align-items:center;gap:6px;font-size:11px;color:#64748b;font-family:monospace;}
.footer{font-size:11px;color:#334155;font-family:monospace;margin-left:auto;}
.analysis{background:#0f172a;border:1px solid #1e293b;border-radius:14px;padding:24px 28px;margin-top:24px;}
.analysis h2{font-size:14px;font-weight:700;color:#94a3b8;font-family:monospace;text-transform:uppercase;letter-spacing:.12em;margin-bottom:18px;}
.analysis-row{display:flex;gap:12px;margin-bottom:12px;align-items:flex-start;}
.analysis-dot{width:9px;height:9px;border-radius:50%;flex-shrink:0;margin-top:4px;}
.analysis-text{font-size:13px;color:#cbd5e1;line-height:1.6;}
.analysis-text strong{color:#f1f5f9;}
.analysis-divider{height:1px;background:#1e293b;margin:16px 0;}
.action-box{background:#1e293b;border-radius:10px;padding:16px 20px;margin-top:16px;}
.action-box h3{font-size:12px;font-weight:700;color:#64748b;font-family:monospace;text-transform:uppercase;letter-spacing:.1em;margin-bottom:10px;}
.action-box p{font-size:13px;color:#cbd5e1;line-height:1.6;}
.analysis-block{margin-top:8px;font-size:13px;color:#cbd5e1;line-height:1.7;}
.analysis-tag{display:inline-block;font-size:10px;font-weight:700;font-family:monospace;letter-spacing:.1em;color:#64748b;text-transform:uppercase;margin-right:8px;margin-bottom:2px;}
"""

TILE_TPL = """
<div class="tile {cls}-tile">
  <div class="tile-top">
    <div>
      <div class="tile-desc">{desc}</div>
      <div class="tile-label">{label}</div>
    </div>
    <span class="dot" style="width:9px;height:9px;background:{dot};margin-top:3px"></span>
  </div>
  <div class="tile-val">{val}</div>
  <div class="tile-note {cls}-note">{note} <span class="pill {cls}-pill">{pill}</span></div>
  <div class="tile-levels">{levels}</div>
</div>
"""

DOTS = {"green": "#22c55e", "amber": "#f59e0b", "red": "#ef4444"}
BANNER_LABELS = {"green": "RISK ON", "amber": "CAUTION", "red": "RISK OFF"}
BANNER_DOTS = {"green": "#22c55e", "amber": "#f59e0b", "red": "#ef4444"}

def _fmt_bps(v):
    return ("%+d bps" % round(v * 100))

# Level band definitions per indicator: (green_label, amber_label, red_label)
LEVELS = {
    "VIX":          ("< 16  CALM",     "16–25  ELEVATED",  "> 25  STRESS"),
    "VVIX":         ("< 95  NORMAL",   "95–110  ELEVATED", "> 110  STRESS"),
    "SKEW Index":   ("< 135  CALM",    "135–150  ELEVATED","> 150  STRESS"),
    "MOVE Index":   ("< 90  CALM",     "90–130  ELEVATED", "> 130  STRESS"),
    "Fear & Greed": ("40–60  NEUTRAL", "25–39 / 61–75",    "< 25 or > 75"),
    "10Y Treasury": ("< 3.5%  LOW",    "3.5–4.5%  FIRM",   "> 4.5%  HIGH"),
    "2Y Treasury":  ("< 3.5%  LOW",    "3.5–4.5%  FIRM",   "> 4.5%  HIGH"),
    "2s10s Spread": ("> 20bps  NORMAL","0–20bps  FLAT",    "< 0  INVERTED"),
    "HY Credit Spread": ("< 3.5%  TIGHT", "3.5–5%  WIDE", "> 5%  STRESS"),
    "HYG / LQD":    ("> 0.75  STABLE", "0.70–0.75  SOFT",  "< 0.70  WEAK"),
    "DXY":          ("< 100  WEAK",    "100–105  MODERATE","> 105  STRONG"),
}

def _make_levels(label, cls):
    bands = LEVELS.get(label)
    if not bands:
        return ""
    g, a, r = bands
    g_cls = "lvl-active-green" if cls == "green" else "lvl-green"
    a_cls = "lvl-active-amber" if cls == "amber" else "lvl-amber"
    r_cls = "lvl-active-red"   if cls == "red"   else "lvl-red"
    return (f"<span class='lvl {g_cls}'>{g}</span>"
            f"<span class='lvl {a_cls}'>{a}</span>"
            f"<span class='lvl {r_cls}'>{r}</span>")

def make_tile(label, desc, val_str, sig_tuple):
    pill_txt, cls = sig_tuple
    dot_color = DOTS.get(cls, "#64748b")
    notes = {
        "green":  "Benign — no stress signal",
        "amber":  "Elevated — monitor closely",
        "red":    "Stress — risk-off signal",
    }
    levels_html = _make_levels(label, cls)
    return TILE_TPL.format(
        cls=cls, desc=desc, label=label,
        dot=dot_color, val=val_str,
        note=notes.get(cls, ""), pill=pill_txt,
        levels=levels_html
    )

def build_analysis(d):
    """Generate detailed plain-English narrative analysis of all indicators."""

    def row(sig, label, what_is_it, current_level, why_it_matters, watch_for):
        dot = {"green": "#22c55e", "amber": "#f59e0b", "red": "#ef4444"}.get(sig, "#64748b")
        status_colors = {"green": "#4ade80", "amber": "#fbbf24", "red": "#f87171"}
        sc = status_colors.get(sig, "#94a3b8")
        return f'''<div class="analysis-row">
  <span class="analysis-dot" style="background:{dot}"></span>
  <div class="analysis-text">
    <strong style="font-size:14px">{label}</strong>
    <div class="analysis-block"><span class="analysis-tag">WHAT IS IT</span>{what_is_it}</div>
    <div class="analysis-block"><span class="analysis-tag" style="color:{sc}">CURRENT LEVEL</span>{current_level}</div>
    <div class="analysis-block"><span class="analysis-tag">WHY IT MATTERS</span>{why_it_matters}</div>
    <div class="analysis-block"><span class="analysis-tag">WATCH FOR</span>{watch_for}</div>
  </div>
</div>'''

    rows = []

    # ── VIX ──────────────────────────────────────────────────────────────────
    v = d["VIX"]
    s = sig_vix(v)[1]
    what = ("The VIX — formally the CBOE Volatility Index — measures the market's expectation of S&P 500 volatility "
            "over the next 30 days. It is derived from the prices of S&P 500 options. When traders are fearful they "
            "pay more for options (insurance), pushing VIX higher. When calm they pay less, pushing it lower. "
            "It is often called the 'Fear Gauge' of equity markets. Key levels: below 15 = calm, 15–25 = moderate "
            "uncertainty, above 25 = elevated fear, above 35 = panic/crisis.")
    if s == "green":
        current = (f"At {v:.1f}, VIX is in calm territory — well below the stress threshold of 25. The options market "
                   "is not pricing significant near-term risk. This indicates that institutional players are not aggressively "
                   "hedging their portfolios, which is a permissive environment for swing trading and holding risk positions.")
        matters = ("Low VIX means low cost of capital and low risk premiums — both supportive for growth stock valuations. "
                   "For your AI supply chain names (AAOI, MU, GLW, ONTO), a calm VIX environment means the macro is not "
                   "fighting your positions. Trend following and momentum strategies work best when VIX is low and stable.")
        watch = ("Watch for VIX spiking above 20 intraday — that is often the first sign of institutional selling pressure. "
                 "Also watch for VIX dropping below 12 — extreme complacency historically precedes sharp reversals as "
                 "smart money uses the low-vol environment to quietly distribute positions.")
    elif s == "amber":
        current = (f"At {v:.1f}, VIX is in elevated territory — the market is nervous but not panicking. "
                   "This level indicates meaningful uncertainty. Options premiums are expensive, meaning the "
                   "market is actively pricing in risk of a near-term move lower.")
        matters = ("Elevated VIX compresses the valuation multiples that growth stocks like your AI supply chain names "
                   "trade on. Institutions reduce risk at this level, which creates selling pressure on high-beta names. "
                   "New position entries carry higher risk and your stops need to be wider to account for increased swings.")
        watch = ("A VIX move above 25 would escalate this to a red signal — reduce size before that happens. "
                 "Conversely, if VIX drops back below 18 it signals the fear spike is fading and the coast is clearing. "
                 "Watch VVIX alongside — if VVIX is also rising it confirms the fear is genuine not a temporary spike.")
    else:
        current = (f"At {v:.1f}, VIX is in stress territory — this is a risk-off environment. "
                   "Historical context: VIX above 30 accompanied the 2020 COVID crash (peak 85), 2022 rate shock (peak 38), "
                   "and 2018 volatility event (peak 50). At this level institutional forced selling accelerates.")
        matters = ("Your AI supply chain positions are high-beta growth names — they will fall harder and faster than "
                   "the broad market in a VIX stress event. AAOI, MU and similar names can drop 15–30% in weeks during "
                   "VIX spikes. This is not the time to hold full size. The SMC framework will show liquidity sweeps "
                   "and stop hunts becoming more violent at these levels.")
        watch = ("Watch for VIX to peak and then make a lower high — that double-top structure in VIX often marks "
                 "the bottom in equities. Do not re-enter positions until VIX is convincingly declining. "
                 "A drop back below 25 is the first sign of stabilisation.")

    rows.append(row(s, f"① VIX — Equity Fear Gauge ({v:.1f})", what, current, matters, watch))

    # ── VVIX ─────────────────────────────────────────────────────────────────
    v = d["VVIX"]
    s = sig_vvix(v)[1]
    what = ("VVIX measures the volatility of the VIX itself — it is the 'volatility of volatility'. "
            "While VIX tells you how much fear exists today, VVIX tells you how uncertain the market is "
            "about future volatility. Think of it as a second-order risk gauge. It is calculated from "
            "options on VIX futures. Key insight: VVIX almost always spikes BEFORE VIX spikes, making "
            "it one of the best leading indicators of incoming volatility. Normal range is 80–100.")
    if s == "green":
        current = (f"At {v:.0f}, VVIX is calm — the market has a stable view of near-term volatility. "
                   "No institutional panic buying of VIX options is occurring. This is consistent with "
                   "a low-risk backdrop and confirms that the low VIX reading is genuine rather than temporary.")
        matters = ("When VVIX is calm alongside VIX, it confirms the risk-on environment is durable. "
                   "It means the smart money is not quietly hedging behind the scenes while the retail crowd "
                   "remains complacent. For your swing trades this means trend continuation setups have "
                   "a higher probability of playing out cleanly without sudden volatility interruptions.")
        watch = ("The critical signal is VVIX rising sharply while VIX remains low — that divergence "
                 "is the classic early warning of an impending volatility spike. If VVIX breaks above 100 "
                 "while VIX is still below 20, start reducing your most leveraged or highest-beta positions.")
    elif s == "amber":
        current = (f"At {v:.0f}, VVIX is elevated — institutions are starting to buy protection on volatility itself. "
                   "This tells you that sophisticated players are positioning for a potential VIX spike ahead. "
                   "This is an early warning signal that should not be ignored even if VIX itself is still calm.")
        matters = ("This is one of the most important setups to understand: VVIX leading VIX. When VVIX rises "
                   "before VIX it gives you a 3–10 day window to reduce risk before the main volatility event "
                   "hits. In SMC terms think of this as smart money accumulating short positions or protective "
                   "puts before the liquidity sweep that triggers retail stop losses.")
        watch = ("If VVIX continues rising above 110 that is a strong signal to cut position sizes. "
                 "Watch whether VIX starts confirming the VVIX move — if both are rising together the "
                 "risk event is likely already beginning. A VVIX drop back below 90 would be the all-clear.")
    else:
        current = (f"At {v:.0f}, VVIX is in stress territory — a major volatility event is either underway "
                   "or imminent. At this level institutional hedging demand is extreme. VIX is almost "
                   "certainly elevated as well or about to spike hard.")
        matters = ("Extreme VVIX means the cost of hedging is prohibitive and market makers are pulling "
                   "liquidity from options markets — this creates the conditions for gap moves and "
                   "outsized single-day swings in individual stocks. Your SMC order blocks and FVGs "
                   "will be violated aggressively at these levels.")
        watch = ("Do not attempt to buy dips or call bottoms until VVIX drops below 100. "
                 "The market is in a disorderly state. Wait for calm to return — VVIX declining "
                 "from its peak is the first sign that the volatility event is peaking.")

    rows.append(row(s, f"② VVIX — Volatility of Volatility ({v:.0f})", what, current, matters, watch))

    # ── SKEW ─────────────────────────────────────────────────────────────────
    v = d["SKEW"]
    s = sig_skew(v)[1]
    what = ("The CBOE SKEW Index measures the perceived tail risk in the S&P 500 — specifically the cost of "
            "buying far out-of-the-money (OTM) put options relative to at-the-money options. "
            "A high SKEW means institutions are paying a significant premium for deep downside protection, "
            "implying they fear a black swan event. Unlike VIX which measures general volatility, SKEW "
            "specifically measures the fear of a sudden large crash. Normal range is 100–135. "
            "Values above 145 indicate elevated tail risk pricing.")
    if s == "green":
        current = (f"At {v:.0f}, SKEW is in the normal range — the market is not pricing an imminent crash event. "
                   "Demand for deep OTM put protection is modest. This tells you that while everyday volatility "
                   "may exist (reflected in VIX), the market does not fear a sudden severe dislocation.")
        matters = ("Low SKEW alongside low VIX is the most benign combination — it means both general fear "
                   "and tail risk fear are absent. For your AI supply chain positions this is the ideal "
                   "backdrop. Momentum and trend-following strategies work best when SKEW is low because "
                   "it means the distribution of returns is more 'normal' rather than skewed to the downside.")
        watch = ("Watch for SKEW rising above 140 while VIX remains low — this is a sophisticated "
                 "warning sign. It means large institutions are quietly buying crash protection even "
                 "while the surface appears calm. This type of divergence often precedes corrections of 10–20%.")
    elif s == "amber":
        current = (f"At {v:.0f}, SKEW is moderately elevated — some institutional players are paying up for "
                   "tail risk protection. This does not mean a crash is imminent but it does mean that "
                   "sophisticated market participants are more nervous about downside scenarios than the "
                   "headline VIX would suggest.")
        matters = ("Elevated SKEW can persist for weeks or months before anything happens — or nothing happens at all. "
                   "However as a swing trader you should note it as a yellow flag. It often reflects macro "
                   "uncertainty (Fed policy, geopolitical events) that has not yet translated into broad equity fear. "
                   "For your AI names watch for any sector-specific catalyst that could accelerate the move.")
        watch = ("If SKEW breaks above 150 alongside a rising VVIX that is a powerful warning combination. "
                 "Also watch if SKEW is rising while VIX is falling — that divergence historically resolves "
                 "with VIX catching up to SKEW's implied warning.")
    else:
        current = (f"At {v:.0f}, SKEW is at elevated levels — significant tail risk hedging is occurring. "
                   "Large institutional money is paying a substantial premium for deep downside protection. "
                   "This is the level seen before major market dislocations.")
        matters = ("Very high SKEW combined with elevated VIX and VVIX is one of the most dangerous "
                   "combinations in macro risk management. It signals that the smart money has already "
                   "positioned defensively and the retail crowd may not yet be aware of the risk. "
                   "For your AI positions this suggests the risk/reward of holding full size is poor.")
        watch = ("Monitor whether SKEW is rising or falling from this level. A falling SKEW from extreme "
                 "highs can actually be bullish as it means the tail risk hedgers are unwinding protection. "
                 "But if SKEW is still rising stay defensive.")

    rows.append(row(s, f"③ SKEW Index — Tail Risk / Crash Fear ({v:.0f})", what, current, matters, watch))

    # ── MOVE ─────────────────────────────────────────────────────────────────
    v = d["MOVE"]
    s = sig_move(v)[1]
    what = ("The MOVE Index (ICE BofA US Bond Market Option Volatility Estimate) is the bond market equivalent "
            "of the VIX. It measures expected volatility in US Treasury yields by tracking options on 2Y, 5Y, "
            "10Y, and 30Y Treasury futures. High MOVE = high uncertainty about where interest rates are heading. "
            "Low MOVE = rates are stable and the Fed narrative is settled. Key levels: below 80 = calm, "
            "80–120 = moderate uncertainty, above 120 = elevated rate stress. MOVE peaked at ~160 in 2022 "
            "during the most aggressive Fed hiking cycle in 40 years.")
    if s == "green":
        current = (f"At {v:.0f}, MOVE is comfortably below the 80 threshold — bond market volatility is "
                   "subdued and the market has a clear and settled view on the interest rate path. "
                   "Treasury auctions are going smoothly and there is no material uncertainty about "
                   "Fed policy direction in the near term.")
        matters = ("MOVE directly impacts growth stock valuations through the discount rate mechanism. "
                   "When rates are stable and MOVE is low, the DCF (discounted cash flow) models that "
                   "institutional investors use to price AI infrastructure stocks produce stable valuations. "
                   "Low MOVE is therefore a direct tailwind for your AAOI, MU, and ONTO positions. "
                   "It also means financing costs for tech companies are predictable and manageable.")
        watch = ("Any CPI print, Fed speech, or Treasury auction that surprises the market can spike MOVE rapidly. "
                 "A MOVE break above 100 is the first serious warning for growth stock holders. "
                 "Watch for MOVE rising ahead of key macro events — it often spikes before earnings seasons "
                 "if there is macro uncertainty in the backdrop.")
    elif s == "amber":
        current = (f"At {v:.0f}, MOVE is elevated — the bond market is uncertain about the rate path. "
                   "This typically happens around Fed meetings, major inflation prints, or geopolitical events "
                   "that could shift monetary policy. Options traders are paying up for rate protection.")
        matters = ("Elevated MOVE creates a challenging environment for growth stocks. When rate uncertainty is high "
                   "institutional portfolio managers reduce their duration risk — which means selling high-multiple "
                   "growth stocks. Your AI supply chain names are particularly sensitive because they trade on "
                   "future earnings potential which gets discounted more aggressively when rates are uncertain. "
                   "Expect wider intraday ranges and less reliable technical setups during elevated MOVE periods.")
        watch = ("Watch whether MOVE is trending higher or has peaked. If it is rolling over from elevated levels "
                 "that is constructive for your positions. If it is still rising watch for the 120 level as "
                 "the line in the sand. Also watch the 10Y yield itself — if it is breaking key levels "
                 "MOVE will follow and compress your AI stock multiples further.")
    else:
        current = (f"At {v:.0f}, MOVE is in stress territory — this is a bond market crisis environment. "
                   "Rate volatility of this magnitude was last seen during the 2022 Fed hiking cycle and the "
                   "2020 COVID liquidity crisis. Treasury markets are disorderly and the rate path is deeply uncertain.")
        matters = ("Extreme MOVE is the single most dangerous macro environment for long-duration growth stocks. "
                   "When bond volatility is this high institutional investors are forced to hedge or reduce "
                   "risk across all asset classes. Correlations go to 1 — everything falls together. "
                   "AI supply chain stocks which were trading on 2025-2027 earnings expectations will see "
                   "those valuations compressed dramatically as the discount rate uncertainty explodes.")
        watch = ("Do not add to any growth positions until MOVE drops below 120. The priority is capital "
                 "preservation. Watch for MOVE to peak and make a lower high — that double-top structure "
                 "is often the signal that the bond crisis is peaking and it is safe to begin rebuilding positions.")

    rows.append(row(s, f"④ MOVE Index — Bond Market Volatility ({v:.0f})", what, current, matters, watch))

    # ── Fear & Greed ─────────────────────────────────────────────────────────
    v = d["FNG"]
    s = sig_fng(v, "")[1]
    rating = d.get("FNG_RATING", "")
    what = ("The CNN Fear & Greed Index is a composite sentiment indicator that combines 7 different market signals: "
            "market momentum (S&P vs 50-day MA), stock price strength (52-week highs vs lows), stock price breadth "
            "(advancing vs declining volume), put/call ratio, junk bond demand (HY vs IG spread), market volatility (VIX), "
            "and safe haven demand (stock vs bond returns). It scores 0–100 where 0 = extreme fear and 100 = extreme greed. "
            "It is a contrarian indicator — extreme readings in either direction often signal reversals.")
    if s == "green":
        current = (f"At {v} ({rating}), sentiment is in the neutral zone — the market is balanced between fear and greed. "
                   "Neither the bulls nor bears have overwhelming dominance. This is historically the most "
                   "sustainable zone for equity markets and the zone where the most reliable technical setups occur.")
        matters = ("Neutral sentiment means the crowd is not making extreme bets in either direction, which reduces "
                   "the risk of sudden sentiment-driven reversals. For your SMC framework this is ideal — "
                   "order blocks and FVGs tend to hold more reliably when sentiment is balanced. "
                   "It also means there is room for the index to move in either direction giving you clean risk/reward.")
        watch = ("Watch for the index moving toward the extremes (below 25 or above 75). "
                 "A move toward extreme fear while your technical setups are showing accumulation is a "
                 "powerful buy signal. A move toward extreme greed while you are holding positions is "
                 "a signal to take partial profits and tighten stops.")
    elif s == "amber" and v > 60:
        current = (f"At {v} ({rating}), greed is elevated — the retail crowd is becoming increasingly bullish. "
                   "More investors are buying stocks, momentum chasers are active, and risk appetite is high. "
                   "This is a contrarian warning signal as the easy money has likely already been made.")
        matters = ("In SMC terms elevated greed is when smart money distributes — they sell their accumulated "
                   "positions into the retail buying frenzy. This creates the conditions for a liquidity sweep "
                   "above recent highs followed by a reversal. For your AI supply chain names it means "
                   "chasing breakouts at this level carries significant reversal risk.")
        watch = ("If the index reaches above 80 (extreme greed) that is a strong signal to take profits on "
                 "your strongest positions. Watch for a sudden spike down in the index from extreme greed — "
                 "that rapid sentiment reversal often corresponds to the smart money liquidity grab before "
                 "a meaningful correction.")
    elif s == "amber" and v < 40:
        current = (f"At {v} ({rating}), fear is elevated — investors are nervous and risk aversion is rising. "
                   "This level sees increased selling pressure as retail investors cut positions and sentiment turns negative. "
                   "Headlines are typically negative and the crowd is becoming increasingly bearish.")
        matters = ("Elevated fear creates the setup for SMC accumulation — smart money buys when retail is fearful. "
                   "For your AI supply chain names watch for order blocks forming at key support levels. "
                   "Fear-driven selling often overshoots fundamentals creating genuine value opportunities "
                   "in quality names like MU and GLW that have strong structural tailwinds.")
        watch = ("Watch for the index stabilising and turning back up from the 25–40 range — that reversal "
                 "from fear often marks the start of a new leg higher. Combine with SMC confirmation "
                 "(break of structure on the daily) before adding to positions.")
    else:
        current = (f"At {v} ({rating}), sentiment is at an extreme — this is either maximum panic or maximum euphoria. "
                   "Extreme readings historically have a strong mean-reversion tendency within 2–6 weeks.")
        matters = ("Extreme fear below 20 has historically been one of the best buying opportunities in markets. "
                   "Extreme greed above 80 has historically been one of the best times to reduce exposure. "
                   "The key is patience — extremes can persist longer than expected before reversing.")
        watch = ("For extreme fear: wait for confirmation of reversal (VIX peaking, HY spreads tightening) "
                 "before buying. For extreme greed: start scaling out of positions and tightening stops "
                 "rather than making one large exit decision.")

    rows.append(row(s, f"⑤ Fear & Greed Index ({v} — {rating})", what, current, matters, watch))

    rows.append('<div class="analysis-divider"></div>')

    # ── 10Y ──────────────────────────────────────────────────────────────────
    v = d["US10Y"]
    s = sig_10y(v)[1]
    what = ("The US 10-Year Treasury yield is the benchmark for long-term borrowing costs in the world. "
            "It represents the annual return investors demand for lending money to the US government for 10 years. "
            "It is the single most important number in global finance because it is used as the risk-free rate "
            "in virtually every asset valuation model. When 10Y rises growth stocks fall (higher discount rate = "
            "lower present value of future earnings). When 10Y falls growth stocks tend to rise. "
            "It is set by market forces (bond supply/demand) not directly by the Fed.")
    if s == "green":
        current = (f"At {v:.2f}%, the 10Y yield is in a benign range — not exerting significant downward "
                   "pressure on equity valuations. The market is comfortable with the current rate level "
                   "and is not pricing an escalation in long-term inflation or fiscal stress.")
        matters = ("For your AI supply chain positions the 10Y is crucial. Names like AAOI and ONTO "
                   "are priced on future earnings that may be 2–4 years out. A lower 10Y means those "
                   "future earnings are discounted less aggressively — supporting higher valuations today. "
                   "Below 4.5% the interest rate headwind is manageable for growth stocks.")
        watch = ("Watch the 4.5% level closely — if 10Y breaks and holds above 4.5% it shifts from "
                 "green to amber and multiple compression begins. Also watch the real yield (10Y minus "
                 "inflation expectations) — that is what truly drives growth stock valuations.")
    elif s == "amber":
        current = (f"At {v:.2f}%, the 10Y is at a firm level — equity valuations are under pressure. "
                   "This level is high enough to make the risk/reward of owning high-multiple growth "
                   "stocks less attractive compared to holding Treasuries. Institutional rotations "
                   "from growth to value tend to occur at these levels.")
        matters = ("At this rate level a stock trading at 40x forward earnings becomes harder to justify. "
                   "Institutional models start flagging growth stocks as expensive relative to the risk-free rate. "
                   "For AAOI specifically — which has had volatile earnings — the elevated 10Y means "
                   "the market will demand more earnings certainty before expanding the multiple.")
        watch = ("Watch the 5% level as the critical threshold. If 10Y approaches 5% start reducing "
                 "your highest-multiple positions. Also watch for the 10Y to begin declining — "
                 "that reversal is often the catalyst for a strong growth stock rally.")
    else:
        current = (f"At {v:.2f}%, the 10Y is above 5% — this is a significant headwind for growth equities. "
                   "This level has not been sustained for extended periods since 2007. It makes "
                   "Treasury bonds genuinely competitive with equities for the first time in over a decade.")
        matters = ("Above 5% the 'TINA' (There Is No Alternative to stocks) trade breaks down. "
                   "Institutional investors can earn 5%+ risk-free, which dramatically raises the "
                   "hurdle rate for owning volatile growth stocks. AI supply chain names which are "
                   "priced for perfection will face the most severe multiple compression.")
        watch = ("The key question at these levels is: will the Fed pivot? Watch Fed communications closely. "
                 "A credible pivot signal will cause the 10Y to drop sharply and trigger a major "
                 "growth stock rally. Until then maintain defensive positioning.")

    rows.append(row(s, f"⑥ 10Y Treasury Yield ({v:.2f}%)", what, current, matters, watch))

    # ── 2Y ───────────────────────────────────────────────────────────────────
    v = d["US2Y"]
    s = sig_2y(v)[1]
    what = ("The US 2-Year Treasury yield is the most sensitive indicator of Fed policy expectations. "
            "Unlike the 10Y which reflects long-term growth and inflation views, the 2Y is almost entirely "
            "driven by expectations of where the Fed funds rate will be over the next 2 years. "
            "When the 2Y is high the market expects the Fed to keep rates elevated. When the 2Y is falling "
            "the market is pricing in rate cuts — which is historically very bullish for risk assets. "
            "The 2Y is where traders look to front-run Fed policy changes.")
    if s == "green":
        current = (f"At {v:.2f}%, the 2Y is low — the market is pricing a relatively dovish Fed outlook. "
                   "Rate cuts are either already priced in or the market believes the Fed is close to "
                   "cutting. This is a very supportive backdrop for risk assets and growth stocks specifically.")
        matters = ("When the 2Y is falling it means monetary conditions are loosening — access to capital "
                   "becomes cheaper for growth companies and the discount rate used to value future earnings falls. "
                   "Historically the best periods for AI and tech stocks have coincided with declining 2Y yields. "
                   "This is currently a tailwind for your entire AI supply chain portfolio.")
        watch = ("Watch for the 2Y to start rising again — that would signal the market is re-pricing "
                 "the Fed as more hawkish than expected. Any hot inflation data or strong jobs report "
                 "can cause the 2Y to spike quickly. A 2Y move above 4% is the first caution signal.")
    elif s == "amber":
        current = (f"At {v:.2f}%, the 2Y is elevated — the Fed is still restrictive and the market is "
                   "not pricing imminent rate cuts. This means the cost of capital for growth companies "
                   "remains high and the discount rate for valuing future earnings is elevated.")
        matters = ("An elevated 2Y is a headwind but not a crisis for growth stocks — it simply means "
                   "valuations are more compressed than they would be in a cutting cycle. "
                   "The key is direction: if the 2Y is declining from these levels that is constructive "
                   "even if the absolute level is still high. Rate of change matters more than the level.")
        watch = ("Watch Fed meeting outcomes and CPI prints closely — these are the primary drivers of "
                 "2Y moves. A surprise rate cut or a series of soft inflation prints will bring the "
                 "2Y down quickly and provide a strong catalyst for growth stock re-rating.")
    else:
        current = (f"At {v:.2f}%, the 2Y above 5% signals the market expects the Fed to remain extremely "
                   "restrictive for an extended period. This is the most challenging environment for "
                   "growth stock investing — high rates with no near-term relief in sight.")
        matters = ("At 5%+ on the 2Y you are essentially competing against a risk-free 5% return every time "
                   "you hold a volatile growth stock. The risk premium demanded by investors for owning "
                   "AI supply chain names increases substantially, compressing valuations further.")
        watch = ("A 2Y above 5% historically either leads to a Fed pivot (bullish) or a credit event "
                 "(bearish). Watch for cracks in the corporate credit market — widening HY spreads "
                 "alongside a high 2Y is the most dangerous combination.")

    rows.append(row(s, f"⑦ 2Y Treasury Yield ({v:.2f}%)", what, current, matters, watch))

    # ── 2s10s ────────────────────────────────────────────────────────────────
    v = d["T10Y2Y"]
    s = sig_2s10s(v)[1]
    bps = round(v * 100)
    what = ("The 2s10s spread is the difference between the 10-Year and 2-Year Treasury yields, expressed in "
            "basis points (1 bp = 0.01%). A positive spread (normal curve) means long rates are higher than "
            "short rates — the normal healthy condition reflecting expectations of future growth. "
            "A negative spread (inverted curve) means short rates exceed long rates — historically one of "
            "the most reliable recession predictors. Every US recession since 1955 has been preceded by "
            "yield curve inversion. However the lag can be 6–24 months making timing difficult. "
            "The dangerous zone is actually immediately AFTER inversion ends — that un-inversion often "
            "marks the start of the actual recession.")
    if s == "green":
        current = (f"At {bps:+d} bps, the yield curve is positively sloped — the normal healthy configuration. "
                   "Long-term rates are appropriately higher than short-term rates reflecting confidence "
                   "in future economic growth. This is the baseline condition for a healthy economy.")
        matters = ("A positive yield curve means banks can borrow short and lend long profitably — "
                   "this supports credit creation and economic activity. For your AI supply chain names "
                   "a positive curve is supportive because it reflects market confidence in sustained "
                   "economic growth which drives enterprise tech and infrastructure spending.")
        watch = ("Watch for the curve flattening — a trend toward 0 bps is the first warning. "
                 "Historically inversion starts with the short end rising faster than the long end "
                 "as the Fed hikes rates. If the 2s10s drops below 25 bps start paying close attention.")
    elif s == "amber":
        current = (f"At {bps:+d} bps, the yield curve is flat or very slightly positive — this is the "
                   "transitional zone coming out of inversion. This is actually one of the most "
                   "historically dangerous positions to be in. Research shows recession risk peaks "
                   "not during inversion but in the 6–18 months after the curve un-inverts.")
        matters = ("The transition from inverted back to flat/positive has historically coincided with "
                   "the actual onset of recession. This is because the un-inversion typically happens "
                   "as the Fed starts cutting rates in response to economic weakness — which means the "
                   "damage is already done. For your positions this warrants heightened caution despite "
                   "the improving curve shape.")
        watch = ("Watch the reason for the un-inversion: is the 10Y rising (growth expectations improving — bullish) "
                 "or is the 2Y falling (Fed cutting due to weakness — potentially bearish near-term). "
                 "The mechanism matters enormously for how to position.")
    else:
        current = (f"At {bps:+d} bps, the yield curve is inverted — short rates exceed long rates. "
                   "This configuration has preceded every US recession since 1955. The market is "
                   "signalling that current Fed policy is too tight and will eventually need to be reversed.")
        matters = ("Yield curve inversion does not mean an immediate recession — the average lead time "
                   "is 12–18 months. However it does mean: (1) credit conditions are tightening, "
                   "(2) bank lending profitability is squeezed, (3) corporate financing costs are elevated. "
                   "For AI supply chain companies this means slower enterprise spending growth and "
                   "tighter access to capital for expansion plans.")
        watch = ("Watch the depth of inversion — deeper inversion historically correlates with more "
                 "severe recessions. Also watch for the un-inversion signal which paradoxically is "
                 "often when you should become most cautious about equities.")

    rows.append(row(s, f"⑧ 2s10s Yield Curve Spread ({bps:+d} bps)", what, current, matters, watch))

    # ── HY Spread ────────────────────────────────────────────────────────────
    v = d["HYOAS"]
    s = sig_hyoas(v)[1]
    what = ("The High Yield (HY) Option-Adjusted Spread (BAMLH0A0HYM2 from FRED) measures the extra yield "
            "that below-investment-grade ('junk') corporate bond issuers must pay over equivalent US Treasuries. "
            "When lenders are confident they demand less extra yield (tight spreads). When they are worried "
            "about defaults they demand more (wide spreads). This is the 'lenders spread' — it directly "
            "measures credit market stress. Key insight: credit markets often lead equity markets because "
            "bond investors are more sophisticated and have access to better fundamental information. "
            "Key levels: below 3.5% = tight/benign, 3.5–5% = widening/caution, above 5% = stress.")
    if s == "green":
        current = (f"At {v:.2f}%, HY spreads are near historic lows — lenders are highly confident and "
                   "demanding minimal risk premium. This is a green light from the credit markets. "
                   "Corporate balance sheets are healthy, default rates are low, and access to capital "
                   "for growth companies is easy and cheap.")
        matters = ("Tight HY spreads are one of the most bullish macro signals for risk assets. "
                   "It means the financial plumbing of the economy is working smoothly. "
                   "For your AI supply chain positions it means the companies you hold have easy access "
                   "to debt financing for capital expenditure — critical for the massive data centre "
                   "buildout that is driving demand for optical networking (AAOI), memory (MU), "
                   "and fibre (GLW). It also means market makers and institutional investors "
                   "are comfortable providing liquidity in risk assets.")
        watch = ("The concern with extremely tight spreads (below 3%) is complacency — there is "
                 "limited room for further compression but significant room for widening. "
                 "Watch for HY spreads moving above 3.5% as the first alert. "
                 "Any sudden widening above 4% would be a significant warning signal requiring "
                 "immediate review of position sizes.")
    elif s == "amber":
        current = (f"At {v:.2f}%, HY spreads are widening — credit markets are starting to price risk. "
                   "Lenders are demanding more compensation for the possibility of default. "
                   "This is an early warning signal that financial conditions are tightening "
                   "and corporate stress is beginning to emerge in pockets of the market.")
        matters = ("Widening HY spreads historically lead equity market corrections by 4–8 weeks. "
                   "Bond investors see the corporate fundamentals first and move to protect themselves "
                   "before equity investors react. For your AI positions this is the time to start "
                   "tightening stops, avoiding new leveraged positions, and reviewing which holdings "
                   "have the most credit-sensitive characteristics.")
        watch = ("The 4.5% level is your key threshold — if spreads break above 4.5% and continue "
                 "widening that is a firm signal to reduce exposure to your most speculative "
                 "AI supply chain names. Watch HYG/LQD ratio alongside — if both are confirming "
                 "the stress signal it is more reliable than either alone.")
    else:
        current = (f"At {v:.2f}%, HY spreads are in stress territory — credit markets are pricing "
                   "meaningful default risk. This level has historically been associated with "
                   "economic recessions, credit crises, or major equity bear markets.")
        matters = ("Wide HY spreads mean the cost of capital for leveraged companies has spiked. "
                   "Companies that rely on debt financing for growth — including many in the AI "
                   "infrastructure space — face significantly higher borrowing costs. "
                   "More importantly wide spreads signal that institutional risk appetite has collapsed "
                   "and forced selling is likely occurring across risk assets including equities.")
        watch = ("Watch for HY spreads to peak and begin narrowing — that is typically the signal "
                 "that the credit stress event is resolving. The peak in HY spreads often marks "
                 "the trough in equity markets. Do not add risk until spreads are convincingly "
                 "tightening from their highs.")

    rows.append(row(s, f"⑨ HY Credit Spread / BAMLH0A0HYM2 ({v:.2f}%)", what, current, matters, watch))

    # ── HYG/LQD ──────────────────────────────────────────────────────────────
    ratio = d.get("HYG_LQD")
    ratio_txt = ("%.3f" % ratio) if ratio is not None else "n/a"
    s_ratio = sig_ratio(d["HYOAS"])[1]
    what = ("The HYG/LQD ratio compares the performance of high yield corporate bonds (HYG ETF) versus "
            "investment grade corporate bonds (LQD ETF). When the ratio is rising HY is outperforming IG — "
            "meaning the market is in risk-on mode (investors prefer riskier bonds). When the ratio is falling "
            "HY is underperforming IG — meaning investors are rotating to safety (risk-off). "
            "It is a real-time credit stress proxy that moves faster than spread data from FRED. "
            "A declining HYG/LQD ratio often precedes equity market weakness by days to weeks.")
    rows.append(row(s_ratio, f"⑩ HYG/LQD Ratio ({ratio_txt})", what,
        f"At {ratio_txt}, the ratio {'is stable and above 0.75, confirming risk-on credit conditions' if s_ratio == 'green' else 'is showing mild stress — HY is underperforming IG' if s_ratio == 'amber' else 'is showing significant stress — HY is materially underperforming IG'}. "
        f"This {'confirms the constructive picture from the HY spread data' if s_ratio == 'green' else 'is an early warning sign worth monitoring alongside the HY spread' if s_ratio == 'amber' else 'is a serious risk-off signal consistent with the elevated HY spread'}.",
        "The HYG/LQD ratio is most useful as a real-time momentum indicator for credit conditions. "
        "A steadily declining ratio over multiple weeks is a powerful warning signal even before "
        "it reaches extreme levels — the trend matters as much as the level. "
        "For your AI supply chain positions a declining HYG/LQD ratio means institutional risk "
        "appetite is shrinking and liquidity in your stocks will likely deteriorate.",
        "Watch for the ratio to break below its 20-day moving average — that is often the first "
        "actionable signal. Also watch for divergence: if equities are making new highs but "
        "HYG/LQD is declining that is a classic warning that the equity rally lacks credit support."))

    # ── DXY ──────────────────────────────────────────────────────────────────
    v = d["DXY"]
    s = sig_dxy(v)[1]
    what = ("The DXY (US Dollar Index) measures the value of the US dollar against a basket of 6 major "
            "currencies (Euro 57.6%, Japanese Yen 13.6%, British Pound 11.9%, Canadian Dollar 9.1%, "
            "Swedish Krona 4.2%, Swiss Franc 3.6%). A rising DXY means the dollar is strengthening — "
            "which tightens global financial conditions, increases debt service costs for dollar-denominated "
            "borrowers worldwide, and typically pressures risk assets. A falling DXY means looser financial "
            "conditions and is historically bullish for equities, commodities, and emerging markets.")
    if s == "green":
        current = (f"At {v:.1f}, the DXY is weak — the dollar is not exerting tightening pressure on "
                   "global financial conditions. This is typically associated with an accommodative Fed "
                   "stance, strong global risk appetite, and capital flowing into risk assets globally.")
        matters = ("A weak dollar is constructive for your AI supply chain holdings in several ways. "
                   "First it means global financial conditions are loose — supportive for risk assets broadly. "
                   "Second many of your AI names have significant international revenue (semiconductor sales "
                   "to Asian data centres, optical networking to European carriers) — a weak dollar "
                   "boosts the USD value of those overseas earnings. Third it reduces the refinancing "
                   "stress on emerging market companies that are major buyers of US tech components.")
        watch = ("Watch for the DXY to start strengthening above 102. A rising dollar combined with "
                 "rising rates is a toxic combination for risk assets. The DXY often moves inversely "
                 "to risk appetite — if you see DXY spiking up check your other risk indicators simultaneously.")
    elif s == "amber":
        current = (f"At {v:.1f}, the DXY is showing moderate strength — financial conditions are "
                   "tightening at the margins. This level of dollar strength creates headwinds but "
                   "is not yet at levels that historically cause major market dislocations.")
        matters = ("Moderate dollar strength squeezes international earnings of US multinationals, "
                   "increases debt service costs for emerging market dollar borrowers, and signals "
                   "that global liquidity conditions are tightening. For your AI names watch "
                   "companies with significant Asian manufacturing or sales exposure more carefully.")
        watch = ("Watch the 106 level as the key threshold. DXY above 106 has historically been "
                 "associated with significant stress in emerging market economies and risk asset selloffs. "
                 "Also watch for DXY strength coinciding with rising MOVE — that combination signals "
                 "a global tightening cycle that is particularly dangerous for growth stocks.")
    else:
        current = (f"At {v:.1f}, the DXY is strong — global financial conditions are tight. "
                   "This level of dollar strength is a significant headwind for risk assets worldwide. "
                   "Historically DXY above 106-110 has been associated with EM currency crises, "
                   "commodity price collapses, and broad risk asset selloffs.")
        matters = ("A very strong dollar creates a negative feedback loop: it raises the real cost of "
                   "dollar debt globally, forcing asset sales to service obligations, which pressures "
                   "all risk assets further. For AI supply chain names specifically it reduces "
                   "demand from international customers facing higher dollar-denominated prices "
                   "for US-made semiconductors and networking equipment.")
        watch = ("Watch for the Fed to signal concern about dollar strength — that is often the "
                 "catalyst for a reversal. Also watch for DXY to make a lower high from extreme "
                 "levels — that technical reversal often marks the start of a risk-on recovery.")

    rows.append(row(s, f"⑪ DXY — US Dollar Index ({v:.1f})", what, current, matters, watch))

    # Action box
    all_sigs = [sig_vix(d["VIX"])[1], sig_vvix(d["VVIX"])[1], sig_skew(d["SKEW"])[1],
                sig_move(d["MOVE"])[1], sig_fng(d["FNG"], "")[1], sig_10y(d["US10Y"])[1],
                sig_2y(d["US2Y"])[1], sig_2s10s(d["T10Y2Y"])[1],
                sig_hyoas(d["HYOAS"])[1], sig_dxy(d["DXY"])[1]]
    reds = all_sigs.count("red")
    ambers = all_sigs.count("amber")
    overall = "red" if reds >= 2 else "amber" if (reds >= 1 or ambers >= 3) else "green"

    if overall == "green":
        action = ("Risk-On — Constructive Environment",
                  "All major risk gauges are in the green or at worst amber. "
                  "This is a permissive environment for holding and building AI supply chain positions. "
                  "Continue to hold AAOI, MU, GLW, ONTO, and GLW with defined stops. "
                  "New entries on SMC setups (order block retests, FVG fills) are reasonable. "
                  "Stay alert to any sudden MOVE or VIX spike as the first sign of regime change.")
    elif overall == "amber":
        action = ("Caution — Mixed Signals",
                  "The macro picture is mixed. Not a risk-off emergency but not a green light to add aggressively. "
                  "Hold existing AI supply chain positions but tighten stops to recent structure lows. "
                  "Avoid adding new full-size positions until signals clarify. "
                  "Focus on which indicators are amber — if MOVE and HY spread are both elevated, "
                  "that is more serious than elevated SKEW alone.")
    else:
        action = ("Risk-Off — Elevated Danger",
                  "Multiple indicators are in the red simultaneously — this is a macro stress environment. "
                  "Consider reducing position sizes on AI supply chain names, especially high-beta names like AAOI. "
                  "Do not add new positions. Raise cash reserves. "
                  "Wait for HY spreads to tighten back below 4% and VIX to drop below 20 "
                  "before re-engaging with conviction. Patience is the edge here.")

    action_html = f'<div class="action-box"><h3>⚡ Trader Action — {action[0]}</h3><p>{action[1]}</p></div>'

    return f'''
<div class="analysis">
  <h2>📊 Indicator Analysis — What Each Level Means Today</h2>
  {''.join(rows)}
  {action_html}
</div>'''

def build_html(d):
    fng_sig = sig_fng(d["FNG"], d.get("FNG_RATING", "-"))
    ratio = d.get("HYG_LQD")
    ratio_txt = ("%.3f" % ratio) if ratio is not None else "n/a"

    tiles_vol = [
        make_tile("VIX",          "Equity implied volatility",      "%.1f"  % d["VIX"],   sig_vix(d["VIX"])),
        make_tile("VVIX",         "Volatility of volatility",       "%.0f"  % d["VVIX"],  sig_vvix(d["VVIX"])),
        make_tile("SKEW Index",   "Tail risk / black swan",         "%.0f"  % d["SKEW"],  sig_skew(d["SKEW"])),
        make_tile("MOVE Index",   "Bond market volatility",         "%.0f"  % d["MOVE"],  sig_move(d["MOVE"])),
        make_tile("Fear & Greed", "CNN sentiment (0–100)",          "%d"    % d["FNG"],   fng_sig),
    ]
    tiles_rates = [
        make_tile("10Y Treasury",     "Long-term rate environment",       "%.2f%%" % d["US10Y"],  sig_10y(d["US10Y"])),
        make_tile("2Y Treasury",      "Fed expectations / short end",     "%.2f%%" % d["US2Y"],   sig_2y(d["US2Y"])),
        make_tile("2s10s Spread",     "Yield curve · inversion = risk",   _fmt_bps(d["T10Y2Y"]),  sig_2s10s(d["T10Y2Y"])),
        make_tile("HY Credit Spread", "BAMLH0A0HYM2 · lenders spread",   "%.2f%%" % d["HYOAS"],  sig_hyoas(d["HYOAS"])),
        make_tile("HYG / LQD",        "Credit stress proxy",              ratio_txt,               sig_ratio(d["HYOAS"])),
        make_tile("DXY",              "US Dollar Index",                  "%.1f"  % d["DXY"],    sig_dxy(d["DXY"])),
    ]

    all_sigs = [sig_vix(d["VIX"])[1], sig_vvix(d["VVIX"])[1], sig_skew(d["SKEW"])[1],
                sig_move(d["MOVE"])[1], fng_sig[1], sig_10y(d["US10Y"])[1],
                sig_2y(d["US2Y"])[1], sig_2s10s(d["T10Y2Y"])[1],
                sig_hyoas(d["HYOAS"])[1], sig_dxy(d["DXY"])[1]]
    reds = all_sigs.count("red")
    ambers = all_sigs.count("amber")
    overall = "red" if reds >= 2 else "amber" if (reds >= 1 or ambers >= 3) else "green"

    summaries = {
        "green": "Macro backdrop is constructive — credit spreads, bond vol, and equity vol all subdued. Supportive for AI supply chain positions. No SMC red flags.",
        "amber": "Mixed signals across indicators. Caution warranted — consider tightening stops on high-beta AI supply chain names. Monitor HY spreads and MOVE closely.",
        "red":   "Multiple risk indicators elevated simultaneously. Consider reducing exposure. Wait for macro conditions to stabilise before adding to positions.",
    }

    today = datetime.date.today().strftime("%B %d, %Y")

    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Macro Risk Dashboard — {today}</title>
<style>{CSS}</style></head><body>
<div class="container">
  <h1>Daily Macro Risk Dashboard</h1>
  <div class="subtitle">Cross-Asset Risk Monitor · {today} · Live where available, fallback otherwise</div>

  <div class="banner {overall}-banner">
    <div class="sig-row">
      <span class="dot" style="width:13px;height:13px;background:{BANNER_DOTS[overall]}"></span>
      <span class="sig-label" style="color:{BANNER_DOTS[overall]}">{BANNER_LABELS[overall]}</span>
      <span class="date-tag">{today}</span>
    </div>
    <p>{summaries[overall]}</p>
  </div>

  <div class="section-title">Volatility & Sentiment</div>
  <div class="grid">{''.join(tiles_vol)}</div>

  <div class="section-title">Rates, Curve & Credit</div>
  <div class="grid">{''.join(tiles_rates)}</div>

  {build_analysis(d)}

  <div class="legend">
    <div class="legend-item"><span class="dot" style="width:8px;height:8px;background:#22c55e"></span>Risk On / Calm</div>
    <div class="legend-item"><span class="dot" style="width:8px;height:8px;background:#f59e0b"></span>Caution / Elevated</div>
    <div class="legend-item"><span class="dot" style="width:8px;height:8px;background:#ef4444"></span>Risk Off / Stress</div>
    <span class="footer">VIX/VVIX/SKEW/MOVE/HYG/LQD/DXY via Yahoo Finance · 10Y/2Y/HY Spread via FRED · Fear & Greed via CNN · Educational only</span>
  </div>
</div>
</body></html>"""
    return html

# ── Main ────────────────────────────────────────────────────────────────────
def main():
    data = gather()

    print("\n  Macro Risk Dashboard — %s" % datetime.date.today())
    print("  " + "-" * 50)
    print("  VIX    %-8s     10Y Yield  %.2f%%" % (data["VIX"],  data["US10Y"]))
    print("  VVIX   %-8s     2Y Yield   %.2f%%" % (data["VVIX"], data["US2Y"]))
    print("  SKEW   %-8s     2s10s      %s"     % (data["SKEW"], _fmt_bps(data["T10Y2Y"])))
    print("  MOVE   %-8s     HY Spread  %.2f%%" % (data["MOVE"], data["HYOAS"]))
    print("  F&G    %-8s     HYG/LQD    %s"     % (data["FNG"],  data.get("HYG_LQD", "n/a")))
    print("  DXY    %-8s"                        % data["DXY"])
    print("  " + "-" * 50)

    html = build_html(data)
    out = os.path.abspath("risk_dashboard.html")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(html)
    print("\n  Saved: %s" % out)

    try:
        import webbrowser
        webbrowser.open("file://" + out)
        print("  Opening in browser...")
    except Exception:
        print("  Open that file in your browser to view the dashboard.")

if __name__ == "__main__":
    main()
