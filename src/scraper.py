"""Selenium-based exporter for strecken-info.de restriction data."""
import os
import time
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.microsoft import EdgeChromiumDriverManager

TARGET_URL = "https://strecken-info.de"
# The site's export button downloads a file whose name starts with this
# prefix (e.g. "einschraenkungen.csv" or "einschraenkungen_11.06.2026.csv"
# depending on the site version) - match by prefix instead of an exact name.
EXPORT_FILE_PREFIX = "einschraenkungen"
CLICK_TIMEOUT = 10
COOKIE_TIMEOUT = 5
DOWNLOAD_TIMEOUT = 60

BROWSERS = ["auto", "chrome", "edge"]


def _download_prefs(download_dir):
    return {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    }


def _setup_chrome(download_dir, headless, driver_path=None):
    options = ChromeOptions()
    options.add_experimental_option("prefs", _download_prefs(download_dir))
    if headless:
        options.add_argument("--headless")
    service = ChromeService(driver_path) if driver_path else ChromeService(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)


def _setup_edge(download_dir, headless, driver_path=None):
    options = EdgeOptions()
    options.add_experimental_option("prefs", _download_prefs(download_dir))
    if headless:
        options.add_argument("--headless")
    service = EdgeService(driver_path) if driver_path else EdgeService(EdgeChromiumDriverManager().install())
    return webdriver.Edge(service=service, options=options)


def setup_driver(download_dir, headless=False, browser="auto", driver_path=None):
    """Initialize and configure a Chrome or Edge WebDriver.

    browser: "chrome", "edge", or "auto" (try Chrome, fall back to Edge if
    the Chrome binary isn't found - Edge is preinstalled on Windows).
    driver_path: optional path to a manually downloaded chromedriver/msedgedriver
    executable. If set, this is used directly instead of downloading a driver
    via webdriver_manager (useful if the driver-download servers aren't reachable).
    """
    if browser == "chrome":
        return _setup_chrome(download_dir, headless, driver_path)
    if browser == "edge":
        return _setup_edge(download_dir, headless, driver_path)

    try:
        return _setup_chrome(download_dir, headless, driver_path)
    except WebDriverException as e:
        if "cannot find Chrome binary" not in str(e):
            raise
        return _setup_edge(download_dir, headless, driver_path)


def safe_click(driver, xpath, timeout=CLICK_TIMEOUT):
    """Wait for element to be clickable and click it via JavaScript."""
    try:
        elem = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((By.XPATH, xpath))
        )
        driver.execute_script("arguments[0].click();", elem)
        return True
    except Exception:
        return False


def _is_clickable(driver, xpath, timeout):
    """Check whether an element is present and clickable, without clicking it."""
    try:
        WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((By.XPATH, xpath))
        )
        return True
    except Exception:
        return False


def _save_debug_artifacts(driver, download_dir, reason):
    """Save a screenshot and page source to help diagnose a failed fetch."""
    try:
        debug_dir = os.path.join(download_dir, "debug")
        os.makedirs(debug_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        driver.save_screenshot(os.path.join(debug_dir, f"{timestamp}_failure.png"))
        with open(os.path.join(debug_dir, f"{timestamp}_failure.html"), "w", encoding="utf-8") as f:
            f.write(driver.page_source)
    except Exception:
        pass


def handle_cookie_banner(driver):
    """Handle cookie consent - try direct button first, then iframe."""
    try:
        btn = WebDriverWait(driver, COOKIE_TIMEOUT).until(
            EC.element_to_be_clickable((By.XPATH, "//button[text()='Akzeptieren']"))
        )
        driver.execute_script("arguments[0].click();", btn)
        return
    except Exception:
        pass

    try:
        iframe = driver.find_element(By.CSS_SELECTOR, "iframe")
        driver.switch_to.frame(iframe)
        btn = WebDriverWait(driver, COOKIE_TIMEOUT).until(
            EC.element_to_be_clickable((By.XPATH, "//button[text()='Akzeptieren']"))
        )
        driver.execute_script("arguments[0].click();", btn)
        driver.switch_to.default_content()
    except Exception:
        driver.switch_to.default_content()


def download_restriction_data(driver):
    """Navigate to restrictions page and export data.

    Returns (success, reason) where reason describes the failing step
    (or "ok" on success), used for diagnostics.
    """
    try:
        driver.get(TARGET_URL)
    except Exception as e:
        return False, f"page did not load: {e}"

    handle_cookie_banner(driver)

    if not safe_click(driver, "//*[text()='Einschränkungen']", CLICK_TIMEOUT):
        return False, "could not click 'Einschränkungen'"

    # "Einschränkungen" is a toggle. If "Exportieren" doesn't show up shortly
    # after, the panel was probably already open and this click just closed
    # it again - click once more to re-open it.
    if not _is_clickable(driver, "//*[text()='Exportieren']", timeout=3):
        if not safe_click(driver, "//*[text()='Einschränkungen']", CLICK_TIMEOUT):
            return False, "could not re-click 'Einschränkungen'"

    if not safe_click(driver, "//*[text()='Exportieren']", CLICK_TIMEOUT):
        return False, "could not click 'Exportieren'"

    return True, "ok"


def _find_export_files(download_dir):
    """Return export CSVs in download_dir, e.g. "einschraenkungen.csv" or
    "einschraenkungen_11.06.2026.csv" - the site has used both naming schemes.
    Ignores partial/in-progress downloads."""
    return [
        f for f in os.listdir(download_dir)
        if f.lower().startswith(EXPORT_FILE_PREFIX.lower())
        and f.lower().endswith(".csv")
    ]


def _archive_file(download_dir, filename):
    """Rename a downloaded export file to a timestamped name, avoiding collisions."""
    src_path = os.path.join(download_dir, filename)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    dst_path = os.path.join(download_dir, f"{timestamp}.csv")
    suffix = 1
    while os.path.exists(dst_path):
        dst_path = os.path.join(download_dir, f"{timestamp}_{suffix}.csv")
        suffix += 1
    os.rename(src_path, dst_path)
    return dst_path


def save_export(driver, download_dir):
    """Export and rename file with timestamp. Returns (success, message)."""
    # Archive any leftover export file(s) from a previous cycle first, so the
    # browser doesn't save the new download under a "(1)" suffixed name and
    # so leftover files don't get mistaken for this cycle's download.
    for f in _find_export_files(download_dir):
        _archive_file(download_dir, f)

    ok, reason = download_restriction_data(driver)
    if not ok:
        _save_debug_artifacts(driver, download_dir, reason)
        return False, f"Fetch failed: {reason}"

    new_file = None
    for _ in range(DOWNLOAD_TIMEOUT):
        files = _find_export_files(download_dir)
        if files:
            new_file = files[0]
            break
        time.sleep(1)

    if new_file is None:
        _save_debug_artifacts(driver, download_dir, "download did not complete")
        return False, "Fetch failed: download did not start or complete in time"

    try:
        dst_path = _archive_file(download_dir, new_file)
        return True, f"Downloaded and saved to {dst_path}"
    except Exception as e:
        return False, f"Downloaded but failed to save file: {e}"


def reset_driver_state(driver):
    """Clear cookies and open fresh tab for next cycle."""
    driver.delete_all_cookies()
    driver.execute_script("window.open('');")
    driver.close()
    driver.switch_to.window(driver.window_handles[0])


def fetch_once(download_dir, headless=False, browser="auto", driver_path=None):
    """Run a single fetch cycle. Returns (success, message)."""
    os.makedirs(download_dir, exist_ok=True)
    driver = None
    try:
        driver = setup_driver(download_dir, headless, browser, driver_path)
        return save_export(driver, download_dir)
    except WebDriverException:
        return False, "No usable browser found (Chrome or Edge) - please install one and try again"
    except Exception as e:
        if "Could not reach host" in str(e) and not driver_path:
            return False, (
                "Could not download the browser driver (driver-download server unreachable). "
                "Download chromedriver/msedgedriver manually and set 'Driver path' in the settings below."
            )
        return False, f"Error: {e}"
    finally:
        if driver is not None:
            driver.quit()


def run_loop(download_dir, interval_min, headless, stop_event, status_queue, browser="auto", driver_path=None):
    """Continuously fetch on an interval until stop_event is set.

    Sleeps interval_min * 30 seconds between cycles (half the requested
    interval). This compensates for the "Einschränkungen" toggle sometimes
    staying open between cycles - on the cycle where the toggle is already
    open, the export click fails and that cycle is skipped, but the next
    (half-interval-later) cycle succeeds, so the effective successful-export
    interval still matches interval_min.
    """
    os.makedirs(download_dir, exist_ok=True)
    interval_sec = interval_min * 30

    try:
        driver = setup_driver(download_dir, headless, browser, driver_path)
    except WebDriverException:
        status_queue.put("No usable browser found (Chrome or Edge) - please install one and try again")
        return

    try:
        while not stop_event.is_set():
            success, message = save_export(driver, download_dir)
            timestamp = datetime.now().strftime("%H:%M:%S")
            if success:
                status_queue.put(f"[{timestamp}] Download successful")
            else:
                status_queue.put(f"[{timestamp}] {message} (will retry next cycle)")

            reset_driver_state(driver)

            for _ in range(interval_sec):
                if stop_event.is_set():
                    break
                time.sleep(1)
    finally:
        driver.quit()
        status_queue.put("Acquisition stopped")
