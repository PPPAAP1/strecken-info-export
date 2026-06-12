"""Shared constants and helpers for reading strecken-info.de exports."""
import json
import os
from datetime import datetime

import pandas as pd
import streamlit as st

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTINGS_PATH = os.path.join(PROJECT_ROOT, "settings.json")

CSV_SEP = ";"
CSV_ENCODING = "utf-8-sig"
EXPECTED_COLUMNS = [
    "ID", "Typ", "Ort", "Region", "Wirkung", "Ursache",
    "ZeitraumVon", "ZeitraumBis", "ZeitraumUnterbrochen",
]

DEFAULT_SETTINGS = {
    "download_dir": os.path.join(PROJECT_ROOT, "data"),
    "fetch_interval_min": 15,
    "headless": False,
    "browser": "auto",
    "driver_path": "",
}


def read_strecken_csv(path):
    """Read a strecken-info.de export CSV with the correct separator/encoding."""
    return pd.read_csv(path, sep=CSV_SEP, encoding=CSV_ENCODING, dtype=str)


def parse_datetime_dd_mm_yyyy(value):
    """Parse 'DD.MM.YYYY HH:MM' or 'DD.MM.YYYY <suffix>' (e.g. Tagesende, Mittags)."""
    if pd.isna(value):
        return None

    value = str(value).strip()

    try:
        return datetime.strptime(value, "%d.%m.%Y %H:%M")
    except ValueError:
        pass

    date_part = value.split(" ")[0]
    try:
        return datetime.strptime(date_part, "%d.%m.%Y")
    except ValueError:
        return None


def load_settings():
    """Load acquisition settings from settings.json, falling back to defaults."""
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                settings = json.load(f)
            merged = dict(DEFAULT_SETTINGS)
            merged.update(settings)
            return merged
        except (OSError, json.JSONDecodeError):
            pass
    return dict(DEFAULT_SETTINGS)


def save_settings(settings):
    """Persist acquisition settings to settings.json."""
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


def rerun():
    """Trigger a Streamlit rerun, on both old and new Streamlit versions.

    `st.rerun` was added in newer Streamlit and `st.experimental_rerun` was
    removed in even newer versions - so neither name alone is safe across
    the Streamlit versions this app runs under.
    """
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        st.experimental_rerun()


def browse_for_folder(initial_dir=None):
    """Open a native folder picker dialog. Returns the chosen path, or None if
    cancelled or unavailable (e.g. no display)."""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        return None

    root = tk.Tk()
    root.withdraw()
    root.wm_attributes("-topmost", 1)
    try:
        path = filedialog.askdirectory(initialdir=initial_dir or None, master=root)
    finally:
        root.destroy()
    return path or None
