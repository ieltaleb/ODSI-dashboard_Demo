import glob
import os
import zlib
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.io as pio
from dash import Dash, dcc, html, Input, Output

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
# One .xlsx workbook per well in data/, each with sheets: Production History, PTA, Volume tracking
PROD_RESAMPLE = "1h"  # raw rates and pressures are 1-minute, so average to this step
NAVY, BLUE, GOLD = "#171A66", "#0A23FB", "#DCA435"  # sampled from the ODSI website banner
GREEN, AMBER, RED, PURPLE = "#43A047", "#F9A825", "#D32F2F", "#8E3B8E"
pio.templates["plotly_white"].layout.font.family = "Open Sans, Segoe UI, Arial, sans-serif"


def read(name):
    p = os.path.join(DATA, name)
    if not os.path.exists(p):
        return pd.DataFrame()
    df = pd.read_csv(p)  # for Excel use pd.read_excel(p, sheet_name=...)
    if "date" in df:
        df["date"] = pd.to_datetime(df["date"], format="mixed")
    return df


PTA_RENAME = {"Start Time": "date", "Type": "test_type", "Total Perm": "k_md", "Skin": "skin", "Total Skin": "skin",
              "DP Skin": "dp_skin", "DP Total Skin": "dp_skin", "DPs/Q": "dp_skin_per_rate", "kh/mu": "kh_mu",
              "Comp Eff": "comp_eff", "PStar": "p_star", "PI": "pi", "PI_Oil": "pi"}
PROD_ALIAS = {"DHGP": "Calc. DHGP Use", "DHGT": "Calc. DHGT Use"}


def _clean(s):
    return s.map(lambda v: v.strip() if isinstance(v, str) and v.strip() else np.nan)


def _num(df, skip):
    for c in df.columns:
        if c not in skip:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def load_workbook_data(path):
    """Reads one well workbook. Sheets are found by keyword, so names and column prefixes can vary."""
    xl = pd.ExcelFile(path)
    names = xl.sheet_names
    pick = lambda *k: next((n for n in names if any(x in n.lower() for x in k)), None)
    s_pta, s_vol = pick("pta"), pick("volume")
    s_prod = pick("production") or next(n for n in names if n not in (s_pta, s_vol))
    stem = os.path.splitext(os.path.basename(path))[0]

    prod = xl.parse(s_prod)
    whp = next((str(c).strip() for c in prod.columns if str(c).strip().endswith("WHP")), "")
    well = stem  # the file name is the well name
    pre = whp[:-3].strip()  # a column prefix such as "A6" is dropped so column names match across files
    prod.columns = [str(c).strip()[len(pre) + 1:] if pre and str(c).strip().startswith(pre + " ") else str(c).strip()
                    for c in prod.columns]
    prod = prod.rename(columns={prod.columns[0]: "date", **{k: v for k, v in PROD_ALIAS.items() if v not in prod.columns}})
    prod["date"] = pd.to_datetime(prod["date"], errors="coerce")
    prod = _num(prod.dropna(subset=["date"]).copy(), {"date"}).replace(-99999, np.nan)  # the units row drops out here
    if "aOutQgas" not in prod and {"aOutQoil", "aOutProdGOR"} <= set(prod):
        prod["aOutQgas"] = prod["aOutQoil"] * prod["aOutProdGOR"] / 1000  # Mcf/d, from oil rate and GOR
    if "aOutNP" in prod:
        prod["np_mmbbl"] = prod["aOutNP"] / 1e6
    if "aOutWaterCut" in prod:
        prod["aOutWaterCut"] = prod["aOutWaterCut"].clip(lower=0)
    prod = prod.set_index("date").resample(PROD_RESAMPLE).mean().dropna(how="all").reset_index()
    prod["well"] = well

    pta = pd.DataFrame()
    if s_pta:
        pta = xl.parse(s_pta)
        pta.columns = [str(c).strip() for c in pta.columns]
        pta = pta.rename(columns=PTA_RENAME)
        pta["date"] = pd.to_datetime(pta["date"], errors="coerce")
        pta = _num(pta.dropna(subset=["date"]).copy(), {"date", "test_type", "End Time"})
        pta["well"] = well

    vol = pd.DataFrame()
    raw = xl.parse(s_vol, header=None) if s_vol else pd.DataFrame()
    hdr = next((r for r in range(min(len(raw), 12)) if raw.iloc[r].astype(str).str.strip().eq("Start Date").any()), None)
    if hdr is not None:
        nm = [str(c).strip() for c in raw.iloc[hdr]]
        body = raw.iloc[hdr + 2:].reset_index(drop=True)  # one units row sits under the header
        col = lambda n: body.iloc[:, nm.index(n)] if n in nm else None
        vol = pd.DataFrame({"date": pd.to_datetime(col("Start Date"), format="mixed", errors="coerce")})
        for n, k in [("Np", "np_mmstb"), ("TTA Vc", "tta_vc"), ("Vc", "vc"), ("VSld", "vsld"), ("Connected", "connected"), ("Mobile", "mobile")]:
            vol[k] = pd.to_numeric(col(n), errors="coerce") if col(n) is not None else np.nan
        side = lambda n: _clean(body.iloc[:, nm.index(n) + 1]) if n in nm and nm.index(n) + 1 < body.shape[1] else np.nan
        vol["drive"], vol["flag"] = side("VSld"), side("Mobile")  # text sits in the unlabeled column after each
        if vol["connected"].isna().all():  # no adjusted volumes in this sheet, so use the expansion volumes
            vol["connected"], vol["mobile"] = vol["vc"], vol["tta_vc"]
        vol = vol.dropna(subset=["date"]).sort_values("date")
        vol["drive"] = vol["drive"].ffill()
        vol["well"] = well
    return prod, pta, vol


def _cat(frames, fallback):
    frames = [f for f in frames if len(f)]
    if not frames:
        return fallback
    f = pd.concat(frames, ignore_index=True)
    if {"well", "date"} <= set(f):
        f = f.drop_duplicates(subset=["well", "date"]).sort_values(["well", "date"])
    return f


_P, _T, _V = [], [], []
for _f in sorted(glob.glob(os.path.join(DATA, "*.xlsx"))):
    if os.path.basename(_f).startswith("~$"):  # Excel lock file
        continue
    _pr, _pt, _vo = load_workbook_data(_f)
    _P.append(_pr)
    _T.append(_pt)
    _V.append(_vo)
PROD = _cat(_P, read("production.csv"))
PTA = _cat(_T, read("pta_results.csv"))
VOL = _cat(_V, pd.DataFrame(columns=["well", "date", "connected", "mobile", "drive", "flag"]))
EUR = read("eur.csv")
WELLS = sorted(set().union(*[set(d["well"]) for d in (PROD, PTA, VOL) if "well" in d]))

if not WELLS:
    print("No data found. Expected .xlsx workbooks in", DATA)

PROD_SERIES = [  # workbook column, label, axis, color
    ("WHP", "WHP", "y", "#1F3FD6"), ("Calc. DHGP Use", "DHGP", "y", "#F59E0B"), ("aOutDatumP", "Datum P", "y", "#E3242B"),
    ("aOutQgas", "Gas rate", "y2", "#2E9E3A"), ("np_mmbbl", "Np", "y3", "#9A7B0A"),
    ("aOutQoil", "Oil rate", "y4", "#A52A2A"), ("aOutQw", "Water rate", "y4", "#17A2B8"),
    ("aOutWaterCut", "Water cut", "y5", "#00A5BB"),
    ("WHT", "WHT", "y6", "#22C55E"), ("Calc. DHGT Use", "DHGT", "y6", "#14532D")]
PTA_PLOTS = [("k_md", "Total permeability (mD)"), ("skin", "Skin"), ("dp_skin", "ΔP skin (psi)"),
             ("dp_skin_per_rate", "ΔP skin / rate"), ("kh_mu", "Mobility thickness (md-ft/cp)"),
             ("comp_eff", "Completion efficiency (%)"), ("p_star", "P* (psia)"), ("pi", "Productivity index")]
THREATS = [("Compaction", "threat_compaction"), ("Permeability degradation", "threat_perm"),
           ("Skin", "threat_skin"), ("Asphaltene precipitation", "threat_asphaltene"),
           ("Screen velocity", "threat_screen"), ("Water encroachment", "threat_water"),
           ("Wellbore lift", "threat_lift")]


def band(v, cuts):
    return int(sum(v >= c for c in cuts))


DEMO_THREATS = True  # random placeholder scores. Set to False to use the rules in _real_threat_scores.


def threat_scores(well):
    if DEMO_THREATS:
        rng = np.random.default_rng(zlib.crc32(str(well).encode()))  # same well, same scores
        return {n: round(float(rng.uniform(0, 5)), 1) for n, _ in THREATS}
    return _real_threat_scores(well)


def _real_threat_scores(well):
    """Scores run 0 to 5. Uses a threat_* column in pta_results.csv when present, otherwise starter rules."""
    d = PTA[PTA["well"] == well].sort_values("date") if "well" in PTA else PTA
    if d.empty:
        return {n: 0 for n, _ in THREATS}
    last = d.iloc[-1]
    out = {n: (float(last[c]) if c in d and pd.notna(last[c]) else 0.0) for n, c in THREATS}
    if "threat_perm" not in d and "k_md" in d:
        out["Permeability degradation"] = band(100 * (1 - last["k_md"] / d["k_md"].max()), [10, 25, 40, 60, 80])
    if "threat_skin" not in d and "skin" in d:
        out["Skin"] = band(last["skin"], [2, 5, 10, 20, 30])
    return out


def clip(d, start, end):
    if "date" not in d:
        return d
    if start:
        d = d[d["date"] >= start]
    if end:
        d = d[d["date"] <= pd.Timestamp(end) + pd.Timedelta(days=1)]
    return d


KPIS = [("Oil rate", "aOutQoil", "bbl/d", 0), ("Gas rate", "aOutQgas", "Mcf/d", 0), ("Water cut", "aOutWaterCut", "%", 1),
        ("DHGP", "Calc. DHGP Use", "psia", 0), ("Np", "np_mmbbl", "MMbbl", 3)]


def kpi_cards(well, start, end):
    d = clip(PROD[PROD["well"] == well] if "well" in PROD else PROD, start, end)
    if "date" not in d:
        return []
    d = d.set_index("date")
    out = []
    for label, col, unit, dec in KPIS:
        s = d[col].dropna() if col in d else []
        if len(s) == 0:
            continue
        last = s.iloc[-1]
        prev = s.asof(s.index[-1] - pd.Timedelta(days=30))
        ch = "" if pd.isna(prev) else f"{'▲' if last > prev else '▼'} {abs(last - prev):,.{dec}f} vs 30 days earlier"
        out.append(html.Div(className="kpi", children=[
            html.Div(label, className="kpi-l"),
            html.Div([f"{last:,.{dec}f}", html.Span(f" {unit}")], className="kpi-v"),
            html.Div(ch, className="kpi-d")]))
    return out


def ax_cfg(title, color, side, pos=None):
    d = dict(title=dict(text=title, font=dict(color=color, size=11), standoff=2), tickfont=dict(color=color, size=10),
             side=side, overlaying="y", showgrid=False)
    if pos is not None:
        d.update(anchor="free", position=pos)
    return d


def prod_fig(well, shown, start=None, end=None, mark=None):
    d = clip(PROD[PROD["well"] == well] if "well" in PROD else PROD, start, end)
    f = go.Figure()
    for col, label, ax, color in PROD_SERIES:
        if col in d and label in (shown or []):
            f.add_trace(go.Scattergl(x=d["date"], y=d[col], name=label, yaxis=ax, mode="lines",
                                     line=dict(color=color, width=2.5)))
    if mark is not None and len(d):
        m = pd.Timestamp(mark)
        if d["date"].min() <= m <= d["date"].max():
            f.add_shape(type="line", x0=m, x1=m, y0=0, y1=1, yref="paper", line=dict(color=GOLD, width=2, dash="dash"))
            f.add_annotation(x=m, y=1, yref="paper", text="PTA test", showarrow=False, yanchor="bottom",
                             font=dict(color="#9A6F10", size=11))
    f.update_layout(  # three axes left (y, y2, y3) and three right (y4, y5, y6), as in the flyer
        template="plotly_white", height=520, margin=dict(t=40, b=40, l=10, r=10), hovermode="x unified",
        title="Production history", legend=dict(orientation="h", y=-0.15),
        xaxis=dict(domain=[0.17, 0.83], rangeselector=dict(bgcolor="#EEF1FB", activecolor=GOLD, buttons=[
            dict(count=7, label="1w", step="day", stepmode="backward"),
            dict(count=1, label="1m", step="month", stepmode="backward"), dict(step="all", label="All")])),
        yaxis=dict(title=dict(text="Pressure (psia)", font=dict(color="#1F3FD6", size=11), standoff=2),
                   tickfont=dict(color="#1F3FD6", size=10)),
        yaxis2=ax_cfg("Gas rate (Mcf/d)", "#2E9E3A", "left", 0.11),
        yaxis3=ax_cfg("Np (MMbbl)", "#9A7B0A", "left", 0.05),
        yaxis4=ax_cfg("Liquid rate (bbl/d)", "#A52A2A", "right"),
        yaxis5=ax_cfg("Water cut (%)", "#00A5BB", "right", 0.89),
        yaxis6=ax_cfg("Temperature (°F)", "#14532D", "right", 0.95))
    return f


def gauge_fig(well):
    s = threat_scores(well)
    f = make_subplots(rows=1, cols=len(THREATS), specs=[[{"type": "indicator"}] * len(THREATS)])
    for i, (name, _) in enumerate(THREATS, 1):
        v = s[name]
        color = GREEN if v < 2.5 else AMBER if v < 3.5 else RED
        f.add_trace(go.Indicator(mode="gauge+number", value=v, title=dict(text=name, font=dict(size=12)),
                                 gauge=dict(axis=dict(range=[0, 5]), bar=dict(color=color), steps=[dict(range=[0, 2.5], color="#E6F4E8"), dict(range=[2.5, 3.5], color="#FFF3D1"), dict(range=[3.5, 5], color="#FBE0E0")])), row=1, col=i)
    f.update_layout(template="plotly_white", height=210, margin=dict(t=60, b=10, l=20, r=20))
    return f


def pta_fig(well, types, start=None, end=None):
    d = clip(PTA[PTA["well"] == well] if "well" in PTA else PTA, start, end)
    if "test_type" in d and types:
        d = d[d["test_type"].isin(types)]
    f = make_subplots(rows=3, cols=3, subplot_titles=[t for _, t in PTA_PLOTS], vertical_spacing=0.11)
    for i, (c, _) in enumerate(PTA_PLOTS):
        if c in d:
            f.add_scatter(x=d["date"], y=d[c], mode="markers", marker=dict(size=6, color=BLUE),
                          showlegend=False, row=i // 3 + 1, col=i % 3 + 1)
    f.update_layout(template="plotly_white", height=780, margin=dict(t=40, b=30))
    return f


def vol_fig(well, start=None, end=None):
    d = clip(VOL[VOL["well"] == well], start, end)
    f = go.Figure()
    for col, name, color in [("connected", "Connected", GREEN), ("mobile", "Mobile", PURPLE)]:
        f.add_scatter(x=d["date"], y=d[col], name=name, mode="lines", fill="tozeroy", line=dict(color=color, width=2.5))
    dd = d.dropna(subset=["drive"])
    for _, r in dd[dd["drive"] != dd["drive"].shift()].iterrows():
        f.add_shape(type="line", x0=r["date"], x1=r["date"], y0=0, y1=1, yref="paper", line=dict(dash="dot", color="#888"))
        f.add_annotation(x=r["date"], y=1, yref="paper", text=str(r["drive"]), showarrow=False,
                         xanchor="left", yanchor="top", font=dict(size=10))
    for _, r in d[d["flag"].notna()].iterrows():
        f.add_annotation(x=r["date"], y=r["connected"], text=r["flag"], showarrow=True, arrowhead=2, ax=0, ay=-30,
                         font=dict(size=10))
    f.update_layout(template="plotly_white", height=480, margin=dict(t=40), title="Hydrocarbon volume tracking",
                    yaxis_title="MMSTB", hovermode="x unified", legend=dict(orientation="h", y=-0.12))
    return f


def eur_fig():
    if EUR.empty:
        return go.Figure()
    f = make_subplots(rows=2, cols=3, specs=[[{"type": "xy"}] * 3, [{"type": "domain"}] * 3], vertical_spacing=0.2,
                      subplot_titles=["P90 EUR", "P50 EUR", "P10 EUR", "Overall P90", "Overall P50", "Overall P10"])
    for i, c in enumerate(["p90", "p50", "p10"], 1):
        rem = (EUR[c] - EUR["np_mmstb"]).clip(lower=0)
        f.add_bar(x=EUR["well"], y=EUR["np_mmstb"], name="Np", marker_color=NAVY, showlegend=i == 1, row=1, col=i)
        f.add_bar(x=EUR["well"], y=rem, name="Remaining", marker_color=BLUE, showlegend=i == 1, row=1, col=i)
        f.add_pie(labels=["Np", "Remaining"], values=[EUR["np_mmstb"].sum(), rem.sum()], hole=0.55,
                  marker=dict(colors=[NAVY, BLUE]), showlegend=False, row=2, col=i)
    f.update_layout(template="plotly_white", barmode="stack", height=680, yaxis_title="MMSTB")
    return f


app = Dash(__name__, title="ODSI Reservoir Surveillance", external_stylesheets=[
    "https://fonts.googleapis.com/css2?family=Fjalla+One&family=Open+Sans:wght@400;600&display=swap"])
server = app.server
if os.getenv("DASH_USER"):  # set DASH_USER and DASH_PASS on the host to require a login
    import dash_auth
    dash_auth.BasicAuth(app, {os.environ["DASH_USER"]: os.environ["DASH_PASS"]})

_all = [d["date"] for d in (PROD, PTA, VOL) if "date" in d]
_dates = pd.concat(_all) if _all else pd.Series(dtype="datetime64[ns]")
D0, D1 = (_dates.min().date(), _dates.max().date()) if len(_dates) else (None, None)
types = sorted(PTA["test_type"].unique()) if "test_type" in PTA else []
chip = dict(inputClassName="chip-in", labelClassName="chip", inline=True)


def section(title, *children):
    return html.Div(className="card", children=[html.H3(title, className="card-t"), *children])


app.layout = html.Div([
    html.Div(className="topbar", children=[
        html.Img(src=app.get_asset_url("logo.png"), className="logo"),
        html.Span("OILFIELD DATA SERVICES INC.", className="wordmark"),
        html.Span("Answers, when you need them", className="tagline")]),
    html.Div(className="hero", children=html.Div(className="hero-in", children=[
        html.H1("Automated Reservoir & Production Engineering Surveillance"),
        html.Div(className="controls", children=[
            html.Label("Well"),
            dcc.Dropdown(id="well", options=[{"label": w, "value": w} for w in WELLS], value=WELLS[0] if WELLS else None, clearable=False, style={"width": "170px"}),
            html.Label("Dates"),
            dcc.DatePickerRange(id="dates", start_date=D0, end_date=D1, min_date_allowed=D0, max_date_allowed=D1,
                                display_format="MMM D, YYYY")])])),
    html.Div(className="page", children=[
        html.Div(f"No data found. Put one .xlsx workbook per well in {DATA} and restart the app.", className="warn") if not WELLS else None,
        html.Div(id="kpis", className="kpis"),
        dcc.Tabs(parent_className="tabs-parent", className="tabs-bar", content_className="tabs-body", children=[
            dcc.Tab(label="Production and PTA", className="tab-btn", selected_className="tab-btn--on", children=[
                section("Production history",
                        dcc.Checklist(id="series", options=[s[1] for s in PROD_SERIES], value=[s[1] for s in PROD_SERIES], **chip),
                        dcc.Graph(id="prod")),
                section("Threat analysis", dcc.Graph(id="gauges")),
                section("Pressure transient results",
                        html.P("Click any point to mark that test on the production history.", className="hint"),
                        dcc.Checklist(id="types", options=types, value=types, **chip), dcc.Graph(id="pta"))]),
            dcc.Tab(label="Volume tracking", className="tab-btn", selected_className="tab-btn--on", children=[section("Hydrocarbon volume tracking", dcc.Graph(id="vol"))]),
            dcc.Tab(label="Reserves", className="tab-btn", selected_className="tab-btn--on", children=[section(
                "Estimated ultimate recovery", html.P("Demo values until an EUR table is added.", className="hint"),
                dcc.Graph(figure=eur_fig()))])])])])

common = [Input("well", "value"), Input("dates", "start_date"), Input("dates", "end_date")]


@app.callback(Output("kpis", "children"), *common)
def _kpis(well, s, e):
    return kpi_cards(well, s, e)


@app.callback(Output("prod", "figure"), *common, Input("series", "value"), Input("pta", "clickData"))
def _prod(well, s, e, shown, click):
    return prod_fig(well, shown, s, e, click["points"][0]["x"] if click else None)


@app.callback(Output("gauges", "figure"), Input("well", "value"))
def _gauges(well):
    return gauge_fig(well)


@app.callback(Output("pta", "figure"), *common, Input("types", "value"))
def _pta(well, s, e, t):
    return pta_fig(well, t, s, e)


@app.callback(Output("vol", "figure"), *common)
def _vol(well, s, e):
    return vol_fig(well, s, e)


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=int(os.getenv("PORT", 8050)))
