"""Merge raw strecken-info.de exports into a single deduplicated CSV."""
import glob
import os

import pandas as pd

from src.utils import CSV_SEP, CSV_ENCODING, parse_datetime_dd_mm_yyyy, read_strecken_csv


def deduplicate(data_dir="data", output_path="output/deduped_stoerungen.csv",
                strategy="latest", filter_typ="Störung"):
    """Read all CSVs in data_dir, keep one row per ID, write the result.

    strategy:
      - "latest": keep the row with the latest ZeitraumBis for each ID
      - "first": keep the first occurrence (by file order) for each ID

    Returns (deduped_df, skipped_files) where skipped_files lists CSVs that
    could not be read or were missing expected columns.
    """
    csv_files = sorted(glob.glob(os.path.join(data_dir, "*.csv")))

    all_data = []
    skipped_files = []

    for file in csv_files:
        try:
            df = read_strecken_csv(file)
            df = df[df["Typ"] == filter_typ]
            if not df.empty:
                all_data.append(df)
        except Exception:
            skipped_files.append(os.path.basename(file))

    if not all_data:
        return pd.DataFrame(), skipped_files

    combined_df = pd.concat(all_data, ignore_index=True)

    if strategy == "first":
        deduped_df = combined_df.drop_duplicates(subset=["ID"], keep="first")
    else:
        combined_df = combined_df.copy()
        combined_df["_ZeitraumBis_dt"] = combined_df["ZeitraumBis"].apply(parse_datetime_dd_mm_yyyy)
        combined_df = combined_df.sort_values(
            by=["ID", "_ZeitraumBis_dt"], ascending=[True, False]
        )
        deduped_df = combined_df.drop_duplicates(subset=["ID"], keep="first")
        deduped_df = deduped_df.drop(columns=["_ZeitraumBis_dt"])

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    deduped_df.to_csv(output_path, sep=CSV_SEP, encoding=CSV_ENCODING, index=False)

    return deduped_df, skipped_files
