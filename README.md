# Strecken-Info webdriver

An automated web scraping script that exports railway restriction data from [strecken-info.de](https://strecken-info.de) and saves it with timestamped filenames.

## Overview

This Python script uses Selenium WebDriver to automate the process of:
1. Accessing the strecken-info.de website
2. Automatically handling cookie consent banners
3. Navigating to the "Einschränkungen" (Restrictions) section
4. Exporting the data as a CSV file
5. Saving the file with a timestamp in the format `YYYY-MM-DD_HH-MM.csv`
6. Running on a configurable interval (default: every 15 minutes)


## Requirements

- Python 3.x
- `selenium` - Web automation library
- `webdriver-manager` - Automatic Chrome WebDriver management

## Installation

1. Install required packages:
```bash
pip install selenium webdriver-manager
```

2. Ensure you have Google Chrome installed
   - Download from: https://www.google.de/intl/de/chrome/
   - WebDriver Manager will automatically handle the ChromeDriver

## Usage

### Run the Script
```bash
python autoexport.py
```

The script will:
- Perform the first export immediately
- Wait for the configured interval (default: 15 minutes)
- Repeat continuously until manually terminated with `Ctrl+C`

## Output

Files are saved with timestamped filenames to prevent conflicts:
- Pattern: `YYYY-MM-DD_HH-MM.csv`
- Example: `2026-02-08_14-30.csv`
- Location: Configured in `DOWNLOAD_DIR` (Look for your script configuration lon top)

## Configuration

### Change Fetch Interval
```python
DOWNLOAD_DIR = r"C:\Your\Custom\Path"  # Use raw string (r"") for Windows paths
FETCH_INTERVAL_MIN = 15                                     # Interval in minutes
```

### Headless Mode
To run the browser in the background without showing the UI:
```python
options.add_argument("--headless")  # Uncomment this line
```
## How It Works

1. **Browser Setup**: Initializes Chrome WebDriver with download preferences
2. **Website Navigation**: Opens https://strecken-info.de
3. **Cookie Handling**: Automatically accepts cookie consent (direct button or iframe)
4. **Element Clicking**: Click "Einschränkungen" menu
5. **Export Trigger**: Clicks "Exportieren" button to initiate download
6. **Download Wait**: Waits up to 60 seconds for file to appear
7. **File Rename**: Renames downloaded file with timestamp (prevents conflicts)
8. **State Reset**: Clears cookies and opens new tab for next cycle
9. **Countdown**: Displays countdown timer until next fetch
10. **Repeat**: Continues indefinitely until Ctrl+C is pressed


**Common Issues:**
- **"Failed to click restrictions table"**: Increase `CLICK_TIMEOUT` or check if website is accessible
- **"Download timeout - file not found"**: Increase `DOWNLOAD_TIMEOUT` or verify the export works manually
- **Chrome not found**: Install Google Chrome or check installation path

## Notes
- The script runs indefinitely - use `Ctrl+C` to stop
- Website maintenance may cause temporary failures (Rarely) - script will retry on next interval

### FETCH_INTERVAL_SEC
Due to the dummy Selenium (or dummy me), the toggle "Einschränkungen" is not always off every time you close the tab. It could be sometimes not require you to click, which you can directly download it, but sometimes due to webside maintenance, the toggle is automatically off.
To eliminate this uncertainty, the script will:
- Still click the toggle (It may close the toggle)
- Fail to click "export", shows download failure
- Guarantee the next download to be successful

So `FETCH_INTERVAL_SEC` is set as half of a minute (30 seconds) to make sure you are having exactly the period you want.

You may observe this situation by setting your fetching inverval to 60 seconds, and 1 minute every fetching. If you have a good idea how to fix this, please contact me.


