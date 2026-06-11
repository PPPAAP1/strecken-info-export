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
OUTPUT_FILENAME = "einschraenkungen.csv"
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
    """Navigate to restrictions page and export data."""
    try:
        driver.get(TARGET_URL)
        handle_cookie_banner(driver)

        if not safe_click(driver, "//*[text()='Einschränkungen']", CLICK_TIMEOUT):
            return False

        if not safe_click(driver, "//*[text()='Exportieren']", CLICK_TIMEOUT):
            return False

        return True
    except Exception:
        return False


def wait_for_file(src_path, timeout=DOWNLOAD_TIMEOUT):
    """Wait for file to appear in download directory."""
    for _ in range(timeout):
        if os.path.exists(src_path):
            return True
        time.sleep(1)
    return False


def save_export(driver, download_dir):
    """Export and rename file with timestamp. Returns True on success."""
    src_path = os.path.join(download_dir, OUTPUT_FILENAME)

    if not download_restriction_data(driver):
        return False

    if not wait_for_file(src_path):
        return False

    try:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        dst_path = os.path.join(download_dir, f"{timestamp}.csv")
        os.rename(src_path, dst_path)
        return True
    except Exception:
        return False


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
        if save_export(driver, download_dir):
            return True, f"Downloaded and saved to {download_dir}"
        return False, "Fetch failed: click/download step did not succeed - check that the site is reachable"
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
            success = save_export(driver, download_dir)
            timestamp = datetime.now().strftime("%H:%M:%S")
            if success:
                status_queue.put(f"[{timestamp}] Download successful")
            else:
                status_queue.put(f"[{timestamp}] Download failed this cycle (will retry next cycle)")

            reset_driver_state(driver)

            for _ in range(interval_sec):
                if stop_event.is_set():
                    break
                time.sleep(1)
    finally:
        driver.quit()
        status_queue.put("Acquisition stopped")
