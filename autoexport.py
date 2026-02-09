import os
import time
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# Configuration
DOWNLOAD_DIR = r"C:\Users\Administrator\Downloads"
FETCH_INTERVAL_MIN = 15 # Fetching interval in minutes, Edit this field according to your needs

# DO NOT EDIT UNLESS YOU KNOW WHAT YOU ARE DOING
TARGET_URL = "https://strecken-info.de"
OUTPUT_FILENAME = "einschraenkungen.csv"
LOG_INTERVAL = 1
CLICK_TIMEOUT = 10
COOKIE_TIMEOUT = 5
DOWNLOAD_TIMEOUT = 60
# About this field is 30 instead of 60, see readme.md - "Notes - Fetch_Interval_SEC" section
FETCH_INTERVAL_SEC = FETCH_INTERVAL_MIN * 30



def setup_driver(download_dir):
    """Initialize and configure Chrome WebDriver"""
    options = Options()
    options.add_experimental_option("prefs", {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    })
    # options.add_argument("--headless")  # Uncomment for background mode
    
    return webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )


def safe_click(driver, xpath, timeout=CLICK_TIMEOUT):
    """Wait for element to be clickable and click it via JavaScript"""
    try:
        elem = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((By.XPATH, xpath))
        )
        driver.execute_script("arguments[0].click();", elem)
        return True
    except Exception as e:
        print(f"⚠️ Click failed: {xpath} - {str(e)[:50]}")
        return False


def handle_cookie_banner(driver):
    """Handle cookie consent - try direct button first, then iframe"""
    # Try direct button click
    try:
        btn = WebDriverWait(driver, COOKIE_TIMEOUT).until(
            EC.element_to_be_clickable((By.XPATH, "//button[text()='Akzeptieren']"))
        )
        driver.execute_script("arguments[0].click();", btn)
        print("🍪 Cookie accepted (direct)")
        return
    except:
        pass

    # Try iframe method
    try:
        iframe = driver.find_element(By.CSS_SELECTOR, "iframe")
        driver.switch_to.frame(iframe)
        btn = WebDriverWait(driver, COOKIE_TIMEOUT).until(
            EC.element_to_be_clickable((By.XPATH, "//button[text()='Akzeptieren']"))
        )
        driver.execute_script("arguments[0].click();", btn)
        driver.switch_to.default_content()
        print("🍪 Cookie accepted (iframe)")
    except:
        driver.switch_to.default_content()


def download_restriction_data(driver):
    """Navigate to restrictions page and export data"""
    try:
        driver.get(TARGET_URL)
        handle_cookie_banner(driver)

        if not safe_click(driver, "//*[text()='Einschränkungen']", CLICK_TIMEOUT):
            print("❌ Failed to click restrictions table")
            return False

        if not safe_click(driver, "//*[text()='Exportieren']", CLICK_TIMEOUT):
            print("❌ Failed to click export button")
            return False

        return True
    except Exception as e:
        print(f"❌ Navigation error: {e}")
        return False


def wait_for_file(src_path, timeout=DOWNLOAD_TIMEOUT):
    """Wait for file to appear in download directory"""
    for _ in range(timeout):
        if os.path.exists(src_path):
            return True
        time.sleep(1)
    return False


def save_export(driver, download_dir):
    """Export and rename file with timestamp"""
    src_path = os.path.join(download_dir, OUTPUT_FILENAME)
    
    if not download_restriction_data(driver):
        return False

    if not wait_for_file(src_path):
        print("❌ Download timeout - file not found")
        return False

    try:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        dst_path = os.path.join(download_dir, f"{timestamp}.csv")
        os.rename(src_path, dst_path)
        print(f"✅ Download successful: {dst_path}")
        return True
    except Exception as e:
        print(f"❌ Save failed: {e}")
        return False


def reset_driver_state(driver):
    """Clear cookies and open fresh tab for next cycle"""
    driver.delete_all_cookies()
    driver.execute_script("window.open('');")
    driver.close()
    driver.switch_to.window(driver.window_handles[0])


def countdown_timer(remaining_sec, interval=LOG_INTERVAL):
    """Display countdown until next fetch"""
    while remaining_sec > 0:
        print(f"⏱️ Next download in {remaining_sec}s", end="\r", flush=True)
        sleep_time = min(interval, remaining_sec)
        time.sleep(sleep_time)
        remaining_sec -= sleep_time
    print()


def main():
    """Main execution loop"""
    driver = setup_driver(DOWNLOAD_DIR)
    
    print(f"🚆 Auto-export started - fetching every {FETCH_INTERVAL_MIN} minutes")
    print(f"📁 Saving to: {DOWNLOAD_DIR}\n")

    try:
        while True:
            save_export(driver, DOWNLOAD_DIR)
            reset_driver_state(driver)
            countdown_timer(FETCH_INTERVAL_SEC)

    except KeyboardInterrupt:
        print("\n⏹️ Manually terminated (Ctrl+C)")
    finally:
        driver.quit()
        print("Driver closed.")


if __name__ == "__main__":
    main()
