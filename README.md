# Strecken-Info Dashboard

A local Streamlit dashboard for exporting and visualizing railway restriction
("Störung") data from [strecken-info.de](https://strecken-info.de).

## Overview

This project does three things, all from one Streamlit app:

1. **Acquisition**: Uses Selenium to periodically open strecken-info.de, export
   the "Einschränkungen" (restrictions) table as CSV, and save it with a
   timestamped filename.
2. **Processing**: Merges all downloaded CSVs, filters to "Störung" entries,
   and deduplicates by ID (keeping the record with the latest end date).
3. **Visualization**: Shows summary metrics, a daily disruption trend chart,
   breakdowns by region/effect/cause, and a table of currently relevant
   disruptions.

## Project layout

```
strecken-info-export/
├── app.py              # Streamlit entry point - run this
├── requirements.txt
├── settings.json        # created automatically, stores your acquisition settings
├── data/                  # raw downloaded CSVs
├── output/                 # deduplicated CSV used by the dashboard
└── src/
    ├── utils.py             # shared CSV constants, date parsing, settings
    ├── scraper.py             # Selenium acquisition logic
    ├── dedup.py                # merges + deduplicates raw CSVs
    └── analytics.py             # daily counts and category breakdowns
```

## Requirements

- Python 3.x
- Google Chrome installed (for the acquisition step)

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```bash
streamlit run app.py
```

This opens a local web page with two tabs:

### Acquisition

- Set the **download directory** (defaults to `data/` in the project folder,
  or use **Browse...** to pick a folder), the **fetch interval** in minutes,
  the **browser** (auto/Chrome/Edge), and whether to run **headless**. These
  settings are saved automatically to `settings.json`.
- **Fetch once now**: runs a single export cycle immediately.
- **Start automatic acquisition / Stop automatic acquisition**: runs the
  export cycle on a loop in the background until stopped.

### Dashboard

- **Run deduplication**: merges all CSVs in the download directory into
  `output/deduped_stoerungen.csv` and reports how many files were skipped
  (e.g. unreadable/malformed exports).
- Summary metrics, a daily disruption trend chart with a selectable date
  range, top-10 breakdowns by Region/Wirkung/Ursache, and a table of
  disruptions that are currently active or recently ended.

## Notes

### Fetch interval / "Einschränkungen" toggle quirk

The "Einschränkungen" toggle on strecken-info.de doesn't always reset between
visits. Sometimes the export works immediately on a fresh page; other times
the toggle is already open and the export click fails for that cycle.

To compensate, the automatic acquisition loop sleeps for **half** of the
configured interval between cycles. If a cycle fails because of this toggle
state, the very next (half-interval-later) cycle will succeed, so the
effective successful-export interval still matches what you configured.

### Headless mode

Headless mode runs Chrome without a visible window. It works the same as the
normal mode but is useful for running the acquisition loop unattended.

### Driver path / "Could not reach host" error

On first use, this app tries to auto-download a matching chromedriver/
msedgedriver. If your network can't reach the driver-download servers (common
behind certain firewalls/proxies, even when strecken-info.de itself is
reachable), you'll get an error like `Could not reach host. Are you offline?`.

To fix this, download the driver manually and set its full path in the
**Driver path** field:

- Chrome: download the matching version from
  [Chrome for Testing](https://googlechromelabs.github.io/chrome-for-testing/)
  and unzip `chromedriver.exe`.
- Edge: download the matching version from
  [Microsoft Edge WebDriver](https://developer.microsoft.com/microsoft-edge/tools/webdriver/)
  and unzip `msedgedriver.exe`.

Match the driver version to your installed browser version (check via
`chrome://version` or `edge://version`). Once a path is set, no network
request to the driver-download servers is made.
