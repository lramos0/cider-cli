# ipmap/processing/bucket.py

from __future__ import annotations

from typing import List, Literal, Optional

import pandas as pd

from ipmap.utils.logging import get_logger

log = get_logger(__name__)

BucketLevel = Literal["/16", "/24", "/32"]


def _add_ipv4_octets(df: pd.DataFrame, ip_col: str = "ip") -> pd.DataFrame:
    """
    Add octet1..4 columns for IPv4 strings in ip_col.

    Keeps only rows that look like IPv4 and have octets 0–255.
    Accepts 'a.b.c.d' or 'a.b.c.d/len' and ignores everything after '/'.
    """
    log.info("Adding IPv4 octets from column %s (rows=%d)", ip_col, len(df))
    df = df.copy()

    # Extract "a.b.c.d" part before any "/"
    ip_only = df[ip_col].astype(str).str.split("/", n=1).str[0]

    parts = ip_only.str.extract(r"^(\d+)\.(\d+)\.(\d+)\.(\d+)$")
    parts = parts.rename(columns={0: "octet1", 1: "octet2", 2: "octet3", 3: "octet4"})

    # Drop rows that didn't match IPv4
    mask_valid = parts.notna().all(axis=1)
    invalid_count = (~mask_valid).sum()
    if invalid_count:
        log.warning("Dropping %d non-IPv4 rows based on %s", invalid_count, ip_col)

    df = df.loc[mask_valid].copy()
    parts = parts.loc[mask_valid]

    # Cast to int and ensure 0–255
    for col in ["octet1", "octet2", "octet3", "octet4"]:
        df[col] = parts[col].astype(int)

    mask_range = (
            df["octet1"].between(0, 255)
            & df["octet2"].between(0, 255)
            & df["octet3"].between(0, 255)
            & df["octet4"].between(0, 255)
    )
    out_of_range = (~mask_range).sum()
    if out_of_range:
        log.warning("Dropping %d rows with out-of-range octets", out_of_range)

    df = df.loc[mask_range].copy()
    log.debug("Remaining rows after IPv4 filter: %d", len(df))
    return df


def bucket_ipv4(
        df: pd.DataFrame,
        level: BucketLevel,
        ip_col: str = "ip",
        org_col: str = "org",
        extra_group_cols: Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    Generic bucketer for IPv4 into /16, /24, or /32 buckets.

    Input df columns:
      - ip_col: string 'a.b.c.d' or 'a.b.c.d/len'
      - org_col: value used when aggregating orgs (e.g. country code)
      - extra_group_cols: optional columns to keep distinct (e.g. source, snapshot_date)

    Output columns:
      For level="/16":
        bucket_x, bucket_y, bucket_label, orgs, num_prefixes

      For level="/24":
        bucket16_x, bucket16_y, bucket16_label,
        bucket24_index, bucket24_x, bucket24_y, bucket24_label,
        orgs, num_prefixes

      For level="/32":
        bucket16_x, bucket16_y, bucket16_label,
        bucket24_index, bucket24_x, bucket24_y, bucket24_label,
        bucket32_index, bucket32_x, bucket32_y, bucket32_label,
        orgs, num_prefixes
    """
    if extra_group_cols is None:
        extra_group_cols = []

    log.info(
        "Bucketing IPv4 addresses: level=%s rows=%d ip_col=%s org_col=%s",
        level,
        len(df),
        ip_col,
        org_col,
    )

    df = _add_ipv4_octets(df, ip_col=ip_col)

    # Base octets
    o1 = df["octet1"]
    o2 = df["octet2"]
    o3 = df["octet3"]
    o4 = df["octet4"]

    if level == "/16":
        df["bucket_x"] = o1
        df["bucket_y"] = o2
        df["bucket_label"] = o1.astype(str) + "." + o2.astype(str)

        group_cols = ["bucket_x", "bucket_y", "bucket_label"]

    elif level == "/24":
        df["bucket16_x"] = o1
        df["bucket16_y"] = o2
        df["bucket16_label"] = o1.astype(str) + "." + o2.astype(str)

        df["bucket24_index"] = o3  # 0–255 inside /16
        df["bucket24_x"] = (df["bucket24_index"] // 16).astype(int)
        df["bucket24_y"] = (df["bucket24_index"] % 16).astype(int)
        df["bucket24_label"] = (
                o1.astype(str) + "." + o2.astype(str) + "." + o3.astype(str)
        )

        group_cols = [
            "bucket16_x",
            "bucket16_y",
            "bucket16_label",
            "bucket24_index",
            "bucket24_x",
            "bucket24_y",
            "bucket24_label",
        ]

    elif level == "/32":
        df["bucket16_x"] = o1
        df["bucket16_y"] = o2
        df["bucket16_label"] = o1.astype(str) + "." + o2.astype(str)

        df["bucket24_index"] = o3
        df["bucket24_x"] = (df["bucket24_index"] // 16).astype(int)
        df["bucket24_y"] = (df["bucket24_index"] % 16).astype(int)
        df["bucket24_label"] = (
                o1.astype(str) + "." + o2.astype(str) + "." + o3.astype(str)
        )

        df["bucket32_index"] = o4
        df["bucket32_x"] = (df["bucket32_index"] // 16).astype(int)
        df["bucket32_y"] = (df["bucket32_index"] % 16).astype(int)
        df["bucket32_label"] = (
                o1.astype(str)
                + "."
                + o2.astype(str)
                + "."
                + o3.astype(str)
                + "."
                + o4.astype(str)
        )

        group_cols = [
            "bucket16_x",
            "bucket16_y",
            "bucket16_label",
            "bucket24_index",
            "bucket24_x",
            "bucket24_y",
            "bucket24_label",
            "bucket32_index",
            "bucket32_x",
            "bucket32_y",
            "bucket32_label",
        ]

    else:
        log.error("Unsupported bucket level: %s", level)
        raise ValueError(f"Unsupported level: {level!r}")

    # Include any extra grouping cols present in df
    group_cols += [c for c in extra_group_cols if c in df.columns]
    log.debug("Grouping on columns: %s", group_cols)

    # Aggregation: orgs list + num_prefixes (distinct ip strings)
    agg = (
        df.groupby(group_cols, dropna=False)
        .agg(
            orgs=(org_col, lambda x: list({str(o) for o in x.dropna()})),
            num_prefixes=(ip_col, "nunique"),
        )
        .reset_index()
    )

    log.info(
        "Bucketing complete: level=%s, resulting rows=%d",
        level,
        len(agg),
    )
    return agg


def bucket_16(
        df: pd.DataFrame,
        ip_col: str = "ip",
        org_col: str = "org",
        extra_group_cols: Optional[List[str]] = None,
) -> pd.DataFrame:
    """Convenience wrapper for level='/16'."""
    return bucket_ipv4(df, level="/16", ip_col=ip_col, org_col=org_col, extra_group_cols=extra_group_cols)


def bucket_24(
        df: pd.DataFrame,
        ip_col: str = "ip",
        org_col: str = "org",
        extra_group_cols: Optional[List[str]] = None,
) -> pd.DataFrame:
    """Convenience wrapper for level='/24'."""
    return bucket_ipv4(df, level="/24", ip_col=ip_col, org_col=org_col, extra_group_cols=extra_group_cols)


def bucket_32(
        df: pd.DataFrame,
        ip_col: str = "ip",
        org_col: str = "org",
        extra_group_cols: Optional[List[str]] = None,
) -> pd.DataFrame:
    """Convenience wrapper for level='/32'."""
    return bucket_ipv4(df, level="/32", ip_col=ip_col, org_col=org_col, extra_group_cols=extra_group_cols)
