"""Summary statistics and time-series helpers for the dashboard."""
from datetime import timedelta
from collections import defaultdict

import pandas as pd

from src.utils import parse_datetime_dd_mm_yyyy


def compute_daily_counts(df, start_date=None, end_date=None):
    """Return a pandas Series indexed by date with the number of active
    Störungen on each day, optionally restricted to [start_date, end_date]."""
    daily_counts = defaultdict(int)

    for _, row in df.iterrows():
        start_dt = parse_datetime_dd_mm_yyyy(row.get("ZeitraumVon"))
        end_dt = parse_datetime_dd_mm_yyyy(row.get("ZeitraumBis"))

        if start_dt is None or end_dt is None:
            continue

        current_date = start_dt.date()
        last_date = end_dt.date()

        if current_date > last_date:
            continue

        while current_date <= last_date:
            daily_counts[current_date] += 1
            current_date += timedelta(days=1)

    if not daily_counts:
        return pd.Series(dtype=int)

    series = pd.Series(daily_counts).sort_index()

    if start_date is not None:
        series = series[series.index >= start_date]
    if end_date is not None:
        series = series[series.index <= end_date]

    return series


def top_n_categorical(df, column, n=10):
    """Return the top-n most common values of a column with their counts."""
    if column not in df.columns:
        return pd.Series(dtype=int)
    return df[column].value_counts().head(n)


def overall_date_range(df):
    """Return (min_date, max_date) across ZeitraumVon/ZeitraumBis, or (None, None)."""
    dates = []
    for col in ("ZeitraumVon", "ZeitraumBis"):
        if col in df.columns:
            parsed = df[col].apply(parse_datetime_dd_mm_yyyy).dropna()
            dates.extend(d.date() for d in parsed)

    if not dates:
        return None, None
    return min(dates), max(dates)
