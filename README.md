# Reservoir surveillance dashboard (Plotly Dash)

## Run it locally
    pip install -r requirements.txt
    python make_demo_data.py     # synthetic production, PTA and EUR files (skip once you have real data)
    python app.py                # opens on http://localhost:8050

Put one `.xlsx` workbook per well in `data/` (sheets Production History, PTA, Volume tracking). The app loads every workbook in the folder.
`data/example_data.xlsx` is the first one.
Sheets are found by keyword (a sheet with PTA in its name, one with Volume, and the production sheet).
The well name is the workbook file name (A6.xlsx shows as A6). Use one file per well.
The CSV files below are the older demo layout. They only load when the workbook is missing, except `eur.csv`, which is always used and is still demo data.

## Data files (all in `data/`)
- `production.csv`: date, well, whp, dhgp, oil_rate, gas_rate, water_rate, water_cut, np_mmstb
- `pta_results.csv`: date, well, test_type (DD or PBU), k_md, skin, dp_skin, dp_skin_per_rate, kh_mu, comp_eff, p_star, pi.
  Add optional threat_compaction, threat_perm, threat_skin, threat_asphaltene, threat_screen, threat_water, threat_lift
  columns (0 to 5) to drive the gauges. Without them, only permeability degradation and skin are scored, using starter
  cut-offs in `threat_scores()`. Replace those with your own criteria.
- `eur.csv`: well, np_mmstb, p90, p50, p10 (EUR totals in MMSTB)
- The well name comes from the prefix of the first data column in Production History (for example "A6 WHP").
- Production History is averaged to `PROD_RESAMPLE` (1 hour) at load. Change it in `app.py` for more or less detail.

Rename your own columns to match, or edit `PROD_SERIES`, `PTA_PLOTS` and `THREATS` at the top of `app.py`.
For Excel, swap `pd.read_csv` for `pd.read_excel` in `read()` and add `openpyxl` to requirements.

## Hosting
Any host that runs Python works. The app object for the server is `app:server`.

1. Render or Railway (fastest). Push this folder to a private GitHub repo, create a Web Service,
   build command `pip install -r requirements.txt`, start command `gunicorn app:server`.
2. Azure App Service or AWS Elastic Beanstalk if your company already uses them. Same start command.
3. Your own VM behind nginx, if the data can't leave your network.

Before sharing a link, add a login. Set `DASH_USER` and `DASH_PASS` as environment variables on the host
and the app switches on basic auth. For client-facing use with several clients, put it behind SSO
(Azure AD, Okta) and filter each client's wells on the server. Don't commit real client data to a public repo.
