# SETUP.md -- Windows + VS Code

## 1. Prerequisites

- Python 3.10+ (3.9 is the code's stated minimum, but 3.10+ is recommended).
  Install from python.org and tick "Add python.exe to PATH".
- VS Code, with the Python extension installed.

## 2. Get the project onto your laptop

Copy the whole `BIOGAP/` folder to your machine, then open it in VS Code
(`File > Open Folder...`).

## 3. Create a virtual environment

Open a terminal in VS Code (`` Ctrl+` ``):

```powershell
python -m venv venv
venv\Scripts\activate
```

Your prompt should now start with `(venv)`.

## 4. Install dependencies

```powershell
pip install -r requirements.txt
```

## 5. Run the real data ingestion

```powershell
python -m src.pipeline
```

Watch the printed per-source status. Expect one of:

- `status: SUCCESS, retained: <N>` -- real data was retrieved and written to
  `data/raw/` and `data/processed/`.
- `status: FAILED` -- a real network/API error occurred. The exact
  exception is printed. See Troubleshooting below. No data is written for
  that source.
- `status: UNTESTED` -- the connector was never attempted (this currently
  only applies to `src/ingestion/gbif_bulk_download.py` when no GBIF
  account credentials are set). No data is written for that source.

## 6. Launch the application

```powershell
streamlit run app.py
```

This opens your browser to the app (usually `http://localhost:8501`). Use
the sidebar to navigate between pages.

## 7. Run the automated tests (optional but recommended)

```powershell
pytest tests/
```

All tests use synthetic fixture data defined in `tests/conftest.py` and
never touch `data/raw/` or `data/processed/`. If any test fails after you
modify the code, treat that as a signal to fix the code before trusting the
app's output, not to change the test's expectation.

## Troubleshooting

**`ModuleNotFoundError` for any package**
You're not in the virtual environment, or `pip install -r requirements.txt`
didn't complete. Re-run both steps 3 and 4.

**GBIF/iNaturalist ingestion hangs or times out, or the Streamlit app shows
"Connecting..." and never finishes**
This was a real design issue in earlier versions, not just a network
symptom: the old single "Run ingestion pipeline" button ran every source
back-to-back with no bound smaller than GBIF's 100,000-record offset cap,
which could take many minutes with no visible progress -- on Streamlit
Cloud that looks exactly like a lost connection. The app now ingests one
source at a time (see README.md's "Staged ingestion" section), bounded to
a few thousand records per click, with live progress shown via
`st.status()`. If a single-source click still hangs, it's a genuine
network/firewall/proxy issue: test general access by opening
`https://api.gbif.org/v1/occurrence/search?limit=1` in your browser. If
that also fails, it's a network/firewall issue on your machine or
deployment environment, not a bug in this code. If you're behind a
corporate proxy:
```powershell
$env:HTTPS_PROXY = "http://your-proxy:port"
```

**`SSLError` / certificate verification failed**
```powershell
pip install --upgrade certifi requests
```
Do not disable SSL verification as a workaround -- that's a real security
risk, not a fix.

**GBIF ingestion stops with "reached the GBIF search offset cap of
100,000 records"**
Your bounding box genuinely contains more than 100,000 GBIF-indexed
records. This is actually good feasibility news, but requires switching to
GBIF's asynchronous *occurrence download* endpoint (needs a free GBIF
account) via `src/ingestion/gbif_bulk_download.py`. Note this is separate
from, and much rarer than, the app's normal interactive fetch limit
(`CONFIG.gbif_interactive_record_limit`, default 8,000) -- most runs will
stop there long before ever approaching the 100,000 API ceiling; that stop
is expected, not an error, and is reported as such in the per-source
result, not as this offset-cap message.

**The Streamlit app shows "Verified dataset pending" on every page**
This means `data/processed/combined_standard.csv` doesn't exist yet or is
empty -- run `python -m src.pipeline` from the CLI, or click "Fetch GBIF
observations" on the Overview page (this alone is enough to unlock every
analysis page; "Add iNaturalist observations" is an optional second step).

**Maps don't render / look broken**
Confirm `streamlit-folium` installed correctly (`pip show streamlit-folium`).
If you changed `src/visualization/maps.py`'s tile provider, note that some
tile providers (e.g. recent CartoDB tiles) now require their own API key --
the shipped default (`OpenStreetMap`) does not.

## Changing the study area

Edit `config.json` in the project root (create it if it doesn't exist) or
set environment variables `BIOGAP_MIN_LAT`, `BIOGAP_MAX_LAT`,
`BIOGAP_MIN_LON`, `BIOGAP_MAX_LON`. Example `config.json`:

```json
{
  "bbox": {
    "min_lat": 18.75,
    "max_lat": 19.50,
    "min_lon": 72.75,
    "max_lon": 73.35,
    "is_official_polygon": false
  }
}
```

No other file needs to change for a different bounding box.
