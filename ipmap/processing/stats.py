# ipmap/processing/stats.py

from __future__ import annotations

from typing import Dict, Hashable, Optional, Tuple

import numpy as np
import pandas as pd

from ipmap.utils.logging import get_logger

log = get_logger(__name__)


def primary_org(orgs) -> Optional[str]:
    """
    Given a list/array of org values, pick a single 'primary' one
    (most frequent, ignoring None/NaN). Mirrors the notebook logic.
    """
    if orgs is None:
        return None

    if isinstance(orgs, (list, tuple, np.ndarray, pd.Series)):
        vals = [
            str(o)
            for o in orgs
            if o is not None and not (isinstance(o, float) and np.isnan(o))
        ]
    else:
        vals = [str(orgs)]

    if not vals:
        return None

    uniq, counts = np.unique(vals, return_counts=True)
    winner = str(uniq[counts.argmax()])
    return winner


def count_nonnull_unique(orgs) -> int:
    """
    Count distinct non-null org values in a collection.
    Used to compute num_countries in the notebook.
    """
    if orgs is None:
        return 0

    if isinstance(orgs, (list, tuple, np.ndarray, pd.Series)):
        vals = {
            str(o)
            for o in orgs
            if o is not None and not (isinstance(o, float) and np.isnan(o))
        }
    else:
        vals = {str(orgs)} if orgs is not None else set()

    return len(vals)


def attach_primary_and_counts(
        df_buckets: pd.DataFrame,
        orgs_col: str = "orgs",
        primary_col: str = "primary_org",
        count_col: str = "num_countries",
) -> pd.DataFrame:
    """
    Add primary_org + num_countries columns to a bucket DataFrame
    that has an 'orgs' (list) column, like bucket_agg_16/24/32 in the notebook.
    """
    log.info(
        "Attaching primary_org and num_countries to bucket DataFrame (rows=%d)",
        len(df_buckets),
    )

    df = df_buckets.copy()
    df[primary_col] = df[orgs_col].apply(primary_org)
    df[count_col] = df[orgs_col].apply(count_nonnull_unique)

    log.debug("Attached primary_org + num_countries to %d rows", len(df))
    return df


def compute_feed_counts_16(
        df_buckets_24: pd.DataFrame,
        source_col: str = "source",
        date_col: str = "snapshot_date",  # or "mm_date" in your notebook
) -> Dict[Tuple[Hashable, Optional[Hashable]], Dict[Tuple[int, int], int]]:
    """
    Build a mapping similar to notebook feed_counts_16:

        feed_counts_16[(src, date)] -> {(bucket16_x, bucket16_y): num_distinct_24s}

    Expects df_buckets_24 to have:
      - bucket16_x, bucket16_y, bucket24_index
      - source_col (optional)
      - date_col   (optional)
    """
    log.info("Computing feed_counts_16 from df_buckets_24 (rows=%d)", len(df_buckets_24))

    required = {"bucket16_x", "bucket16_y", "bucket24_index"}
    missing = required - set(df_buckets_24.columns)
    if missing:
        log.error("df_buckets_24 is missing required columns: %s", missing)
        raise ValueError(f"df_buckets_24 is missing required columns: {missing}")

    df = df_buckets_24

    if source_col not in df.columns:
        log.debug("source_col %r not in df; using None for all sources", source_col)
        df = df.assign(**{source_col: None})
    if date_col not in df.columns:
        log.debug("date_col %r not in df; using None for all dates", date_col)
        df = df.assign(**{date_col: None})

    result: Dict[Tuple[Hashable, Optional[Hashable]], Dict[Tuple[int, int], int]] = {}

    for (src, date), grp in df.groupby([source_col, date_col]):
        counts = (
            grp.groupby(["bucket16_x", "bucket16_y"])["bucket24_index"]
            .nunique()
            .reset_index()
        )
        mapping = {
            (int(row["bucket16_x"]), int(row["bucket16_y"])): int(row["bucket24_index"])
            for _, row in counts.iterrows()
        }
        result[(src, date)] = mapping
        log.debug(
            "feed_counts_16: source=%r date=%r entries=%d",
            src,
            date,
            len(mapping),
        )

    log.info("Computed feed_counts_16 for %d (source,date) groups", len(result))
    return result


def compute_feed_counts_24(
        df_buckets_32: pd.DataFrame,
        source_col: str = "source",
        date_col: str = "snapshot_date",  # or "mm_date"
) -> Dict[Tuple[Hashable, Optional[Hashable]], Dict[Tuple[int, int, int], int]]:
    """
    Build a mapping similar to notebook feed_counts_24:

        feed_counts_24[(src, date)] ->
            {(bucket16_x, bucket16_y, bucket24_index): num_distinct_32s}

    Expects df_buckets_32 to have:
      - bucket16_x, bucket16_y, bucket24_index, bucket32_index
      - source_col (optional)
      - date_col   (optional)
    """
    log.info("Computing feed_counts_24 from df_buckets_32 (rows=%d)", len(df_buckets_32))

    required = {"bucket16_x", "bucket16_y", "bucket24_index", "bucket32_index"}
    missing = required - set(df_buckets_32.columns)
    if missing:
        log.error("df_buckets_32 is missing required columns: %s", missing)
        raise ValueError(f"df_buckets_32 is missing required columns: {missing}")

    df = df_buckets_32

    if source_col not in df.columns:
        log.debug("source_col %r not in df; using None for all sources", source_col)
        df = df.assign(**{source_col: None})
    if date_col not in df.columns:
        log.debug("date_col %r not in df; using None for all dates", date_col)
        df = df.assign(**{date_col: None})

    result: Dict[
        Tuple[Hashable, Optional[Hashable]],
        Dict[Tuple[int, int, int], int],
    ] = {}

    for (src, date), grp in df.groupby([source_col, date_col]):
        counts = (
            grp.groupby(["bucket16_x", "bucket16_y", "bucket24_index"])["bucket32_index"]
            .nunique()
            .reset_index()
        )
        mapping = {
            (
                int(row["bucket16_x"]),
                int(row["bucket16_y"]),
                int(row["bucket24_index"]),
            ): int(row["bucket32_index"])
            for _, row in counts.iterrows()
        }
        result[(src, date)] = mapping
        log.debug(
            "feed_counts_24: source=%r date=%r entries=%d",
            src,
            date,
            len(mapping),
        )

    log.info("Computed feed_counts_24 for %d (source,date) groups", len(result))
    return result
