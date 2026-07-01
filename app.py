"""Streamlit dashboard: configure/run acquisition and view disruption stats."""
import os
import queue
import threading
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

from src.analytics import compute_daily_counts, overall_date_range, top_n_categorical
from src.dedup import deduplicate
from src.scraper import fetch_once, run_loop, BROWSERS
from src.utils import (
    load_settings, save_settings, read_strecken_csv, parse_datetime_dd_mm_yyyy,
    browse_for_folder, rerun, get_acquisition_state,
)

OUTPUT_PATH = os.path.join("output", "deduped_stoerungen.csv")

st.set_page_config(page_title="Strecken-Info Dashboard", layout="wide")

if "settings" not in st.session_state:
    st.session_state.settings = load_settings()

# Single process-wide acquisition state, shared across all sessions - see
# get_acquisition_state() in src/utils.py for why this can't live here.
_acquisition_state = get_acquisition_state()

tab_acquisition, tab_dashboard = st.tabs(["Acquisition", "Dashboard"])


# ---------------------------------------------------------------------------
# Tab 1: Acquisition
# ---------------------------------------------------------------------------
with tab_acquisition:
    st.header("Acquisition")
    st.caption("Configure the download directory and fetch interval, then start automatic acquisition.")

    settings = st.session_state.settings

    if "download_dir_input" not in st.session_state:
        st.session_state.download_dir_input = settings["download_dir"]

    dir_col, browse_col = st.columns([4, 1])
    with browse_col:
        st.markdown("<div style='height: 1.8em'></div>", unsafe_allow_html=True)
        browse_clicked = st.button("Browse...")

    if browse_clicked:
        selected = browse_for_folder(st.session_state.download_dir_input)
        if selected:
            st.session_state.download_dir_input = selected
            rerun()

    with dir_col:
        download_dir = st.text_input("Download directory", key="download_dir_input")
    fetch_interval_min = st.number_input(
        "Fetch interval (minutes)", min_value=1, max_value=180,
        value=int(settings["fetch_interval_min"]),
    )
    headless = st.checkbox("Headless mode (no visible browser window)", value=settings["headless"])
    browser = st.selectbox(
        "Browser", BROWSERS,
        index=BROWSERS.index(settings.get("browser", "auto")),
        help="auto: prefer Chrome, fall back to Edge if Chrome isn't installed",
    )
    driver_path = st.text_input(
        "Driver path (optional)", value=settings.get("driver_path", ""),
        help=(
            "Leave blank to auto-download the matching chromedriver/msedgedriver. "
            "If that fails with 'Could not reach host', download the driver manually "
            "and put its full path here."
        ),
    )

    if (download_dir != settings["download_dir"]
            or fetch_interval_min != settings["fetch_interval_min"]
            or headless != settings["headless"]
            or browser != settings.get("browser", "auto")
            or driver_path != settings.get("driver_path", "")):
        st.session_state.settings = {
            "download_dir": download_dir,
            "fetch_interval_min": fetch_interval_min,
            "headless": headless,
            "browser": browser,
            "driver_path": driver_path,
        }
        save_settings(st.session_state.settings)

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("Fetch once now"):
            with st.spinner("Fetching..."):
                success, message = fetch_once(download_dir, headless, browser, driver_path or None)
            if success:
                st.success(message)
            else:
                st.error(message)

    running = (
        _acquisition_state["thread"] is not None
        and _acquisition_state["thread"].is_alive()
    )

    with col2:
        if st.button("Start automatic acquisition", disabled=running):
            stop_event = threading.Event()
            status_queue = queue.Queue()
            thread = threading.Thread(
                target=run_loop,
                args=(download_dir, fetch_interval_min, headless, stop_event, status_queue, browser, driver_path or None),
                daemon=True,
            )
            _acquisition_state["thread"] = thread
            _acquisition_state["stop_event"] = stop_event
            _acquisition_state["status_queue"] = status_queue
            _acquisition_state["status_log"] = []
            _acquisition_state["interval_min"] = fetch_interval_min
            _acquisition_state["last_status_time"] = None  # set accurately on first cycle report
            thread.start()
            rerun()

    with col3:
        if st.button("Stop automatic acquisition", disabled=not running):
            _acquisition_state["stop_event"].set()
            rerun()

    status_queue = _acquisition_state["status_queue"]
    if status_queue is not None:
        while not status_queue.empty():
            item = status_queue.get()
            if isinstance(item, tuple):
                # (message, cycle_end_datetime) - use the thread's timestamp so
                # the countdown reflects when the sleep actually started, not
                # when this drain happened.
                msg, cycle_end = item
                _acquisition_state["status_log"].append(msg)
                _acquisition_state["last_status_time"] = cycle_end
            else:
                _acquisition_state["status_log"].append(item)

    status_log = _acquisition_state["status_log"]

    if running:
        st.info("Automatic acquisition is running...")

        csv_count = 0
        if os.path.isdir(download_dir):
            csv_count = len([f for f in os.listdir(download_dir) if f.lower().endswith(".csv")])
        successes = sum(1 for line in status_log if "Download successful" in line)
        failures = len(status_log) - successes

        m1, m2, m3 = st.columns(3)
        m1.metric("CSV files collected", csv_count)
        m2.metric("Successful fetches (since start)", successes)
        m3.metric("Failed fetches (since start)", failures)

        running_interval_min = _acquisition_state["interval_min"] or fetch_interval_min
        last_status_time = _acquisition_state["last_status_time"]
        if last_status_time is None:
            st.caption("First fetch in progress...")
        elif running_interval_min:
            interval_sec = running_interval_min * 60
            elapsed = (datetime.now() - last_status_time).total_seconds()
            remaining = max(0, interval_sec - elapsed)
            mins, secs = divmod(int(remaining), 60)
            st.progress(min(1.0, max(0.0, 1 - remaining / interval_sec)))
            st.caption(f"Next fetch in about {mins}m {secs:02d}s")
    else:
        st.caption("Automatic acquisition is not running")

    if running:
        st.button("Refresh status")

    if status_log:
        st.caption(f"Latest: {status_log[-1]}")
        with st.expander("Status log", expanded=False):
            st.text("\n".join(status_log[-20:]))


# ---------------------------------------------------------------------------
# Tab 2: Dashboard
# ---------------------------------------------------------------------------
with tab_dashboard:
    st.header("Dashboard")

    if st.button("Run deduplication"):
        with st.spinner("Processing..."):
            df, skipped = deduplicate(
                data_dir=st.session_state.settings["download_dir"],
                output_path=OUTPUT_PATH,
            )
        st.session_state["deduped_df"] = df
        st.success(f"Done: {len(df)} records, {len(skipped)} file(s) skipped")
        if skipped:
            with st.expander(f"Skipped files ({len(skipped)})"):
                st.write(skipped)

    df = st.session_state.get("deduped_df")
    if df is None and os.path.exists(OUTPUT_PATH):
        df = read_strecken_csv(OUTPUT_PATH)
        st.session_state["deduped_df"] = df

    if df is None or df.empty:
        st.info("No data yet - click 'Run deduplication' to generate it.")
    else:
        # --- Summary metrics ---
        top_wirkung = top_n_categorical(df, "Wirkung", 1)
        top_ursache = top_n_categorical(df, "Ursache", 1)
        date_min, date_max = overall_date_range(df)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total disruptions", len(df))
        c2.metric("Regions affected", df["Region"].nunique())
        c3.metric(
            "Most common effect (Wirkung)",
            top_wirkung.index[0] if len(top_wirkung) else "-",
            help=f"Occurs {top_wirkung.iloc[0]} times" if len(top_wirkung) else None,
        )
        c4.metric(
            "Data date range",
            f"{date_min} ~ {date_max}" if date_min else "-",
        )

        st.markdown("---")

        # --- Daily trend ---
        st.subheader("Daily disruption count")
        if date_min and date_max:
            range_start, range_end = st.slider(
                "Select date range",
                min_value=date_min,
                max_value=date_max,
                value=(date_min, date_max),
            )
            daily_counts = compute_daily_counts(df, range_start, range_end)
            if not daily_counts.empty:
                daily_counts.index = pd.to_datetime(daily_counts.index)
                st.bar_chart(daily_counts)
            else:
                st.info("No data in the selected range")

        st.markdown("---")

        # --- Breakdowns ---
        st.subheader("Breakdowns (Top 10)")
        b1, b2, b3 = st.columns(3)
        with b1:
            st.caption("By region (Region)")
            st.bar_chart(top_n_categorical(df, "Region", 10))
        with b2:
            st.caption("By effect (Wirkung)")
            st.bar_chart(top_n_categorical(df, "Wirkung", 10))
        with b3:
            st.caption("By cause (Ursache)")
            st.bar_chart(top_n_categorical(df, "Ursache", 10))

        st.markdown("---")

        # --- Recent disruptions table ---
        st.subheader("Currently relevant disruptions")
        recent_days = st.slider("Show disruptions active within the last/next N days", 1, 90, 14)

        df_dates = df.copy()
        df_dates["_von"] = pd.to_datetime(df_dates["ZeitraumVon"].apply(parse_datetime_dd_mm_yyyy))
        df_dates["_bis"] = pd.to_datetime(df_dates["ZeitraumBis"].apply(parse_datetime_dd_mm_yyyy))

        today = datetime.now()
        cutoff = today - timedelta(days=recent_days)

        mask = df_dates["_bis"] >= cutoff
        recent_df = df_dates[mask].sort_values("_von", ascending=False)

        display_cols = ["ID", "Ort", "Region", "Wirkung", "Ursache", "ZeitraumVon", "ZeitraumBis"]
        st.dataframe(recent_df[display_cols].reset_index(drop=True))
