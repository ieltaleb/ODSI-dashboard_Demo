"""Writes synthetic production, PTA and EUR files so the app runs before you plug in real data."""
import os
import numpy as np
import pandas as pd

rng = np.random.default_rng(7)
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(out, exist_ok=True)

WELLS = {"SS01": (10800, 220), "SS02": (3500, 120), "SS03": (2600, 90)}
dates = pd.date_range("2016-10-01", "2023-08-21", freq="D")
t = (dates - dates[0]).days.values / 365.0
prod, pta = [], []
for w, (q0, k0) in WELLS.items():
    n = len(t)
    oil = q0 * np.exp(-0.3 * t) * (1 + 0.05 * rng.standard_normal(n))
    oil[rng.random(n) < 0.02] *= 0.2
    wc = np.clip(2 + 3.5 * t**1.4 + rng.normal(0, 0.5, n), 0, 60)
    dhgp = 15800 * np.exp(-0.085 * t) + rng.normal(0, 60, n)
    prod.append(pd.DataFrame({
        "date": dates, "well": w, "oil_rate": oil, "gas_rate": oil * 1.8,
        "water_rate": oil * wc / (100 - wc), "water_cut": wc,
        "np_mmstb": np.cumsum(oil) / 1e6, "dhgp": dhgp,
        "whp": 8000 * np.exp(-0.12 * t) + rng.normal(0, 80, n)}))
    idx = np.arange(5, n, 28)
    tt, q = t[idx], oil[idx]
    k = k0 * np.exp(-0.2 * tt) * (1 + 0.04 * rng.standard_normal(len(idx)))
    skin = 0.5 + 0.35 * np.exp(0.45 * tt) * (1 + 0.1 * rng.standard_normal(len(idx)))
    pstar = 16000 * np.exp(-0.05 * tt)
    pta.append(pd.DataFrame({
        "date": dates[idx], "well": w, "test_type": rng.choice(["DD", "PBU"], len(idx)),
        "k_md": k, "skin": skin, "dp_skin": skin * q * 0.12, "dp_skin_per_rate": skin * 0.12,
        "kh_mu": k * 85 / 0.6, "comp_eff": 100 / (1 + skin / 12), "p_star": pstar,
        "pi": q / np.maximum(pstar - dhgp[idx], 100)}))

pd.concat(prod).round(3).to_csv(os.path.join(out, "production.csv"), index=False)
pd.concat(pta).round(3).to_csv(os.path.join(out, "pta_results.csv"), index=False)
pd.DataFrame({"well": ["SS01", "SS02", "SS03"], "np_mmstb": [24, 6, 5],
              "p90": [30.3, 7.8, 8.3], "p50": [33.47, 8.82, 10.7],
              "p10": [37.95, 9.32, 11.4]}).to_csv(os.path.join(out, "eur.csv"), index=False)
print("Demo data written to", out)
