# ipmap/processing/normalize.py

from __future__ import annotations

from dataclasses import asdict
from typing import Iterable, Optional, Tuple

import ipaddress
import pandas as pd

from ipmap.utils.logging import get_logger

log = get_logger(__name__)


def _clean_ip_string(raw: object) -> Optional[str]:
    """
    Convert a raw IP/prefix string-like value into a cleaned string.

    - Converts to str
    - Strips whitespace
    - Strips common BOM / zero-width chars (e.g. '\ufeff')
    - Returns None if empty after cleaning
    """
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None

    s = str(raw)
    # strip whitespace first
    s = s.strip()
    # strip BOM / zero-width if present
    # (there may be multiple BOM chars, so lstrip them)
    s = s.lstrip("\ufeff\ufeff\ufeff")
    # could also strip other weird chars here if needed

    if not s:
        return None
    return s


def _parse_ip_and_prefix(ip: str, prefix_len: Optional[int]) -> Tuple[str, int]:
    """
    Normalize an IP or CIDR string into (network_address, prefix_len).

    - If ip already has a /len, we trust that and ignore prefix_len arg.
    - If ip has no /len, we use prefix_len or default to /32.
    """
    if ip is None:
        raise ValueError("IP is None")

    ip_str = _clean_ip_string(ip)
    if not ip_str:
        raise ValueError("Empty/invalid IP string after cleaning")

    # Case 1: CIDR given in the string
    if "/" in ip_str:
        net = ipaddress.ip_network(ip_str, strict=False)
        return str(net.network_address), net.prefixlen

    # Case 2: bare address + optional prefix_len
    plen = int(prefix_len) if prefix_len is not None else 32
    net = ipaddress.ip_network(f"{ip_str}/{plen}", strict=False)
    return str(net.network_address), net.prefixlen


def normalize_dataframe(
        df: pd.DataFrame,
        ip_col: str = "ip",
        prefix_len_col: str = "prefix_len",
) -> pd.DataFrame:
    """
    Given a DataFrame with at least [ip_col, prefix_len_col],
    return a new DataFrame where:

      - ip_col is normalized to network_address (string)
      - prefix_len_col is an integer prefix length
      - rows with unparseable IPs are dropped (with a warning)

    Any extra columns are preserved.
    """
    if ip_col not in df.columns:
        raise ValueError(f"normalize_dataframe: missing ip_col {ip_col!r}")
    if prefix_len_col not in df.columns:
        raise ValueError(f"normalize_dataframe: missing prefix_len_col {prefix_len_col!r}")

    log.info(
        "Normalizing DataFrame IPs: rows=%d ip_col=%s prefix_len_col=%s",
        len(df),
        ip_col,
        prefix_len_col,
    )

    ip_series = df[ip_col]
    prefix_series = df[prefix_len_col]

    norm_ips: list[str] = []
    norm_prefixes: list[int] = []
    keep_indices: list[int] = []

    for i, (raw_ip, raw_plen) in enumerate(zip(ip_series, prefix_series)):
        cleaned_ip = _clean_ip_string(raw_ip)
        if cleaned_ip is None:
            log.debug("Row %d: empty/NaN IP, skipping", i)
            continue

        plen_val: Optional[int] = None
        if raw_plen is not None and not (isinstance(raw_plen, float) and pd.isna(raw_plen)):
            try:
                plen_val = int(raw_plen)
            except Exception:
                log.warning(
                    "Row %d: invalid prefix_len=%r; treating as None (will default)",
                    i,
                    raw_plen,
                )

        try:
            n_ip, n_plen = _parse_ip_and_prefix(cleaned_ip, plen_val)
        except ValueError as e:
            # Don't blow up the entire pipeline for one bad row.
            log.warning(
                "Row %d: could not parse IP/prefix %r (prefix_len=%r): %s; skipping row",
                i,
                raw_ip,
                raw_plen,
                e,
            )
            continue

        norm_ips.append(n_ip)
        norm_prefixes.append(n_plen)
        keep_indices.append(i)

    if not keep_indices:
        log.warning("normalize_dataframe: no valid IPs after normalization; returning empty DataFrame")
        return df.iloc[0:0].copy()

    norm_df = df.iloc[keep_indices].copy()
    norm_df[ip_col] = norm_ips
    norm_df[prefix_len_col] = norm_prefixes

    log.info(
        "normalize_dataframe: input rows=%d, kept=%d, dropped=%d",
        len(df),
        len(norm_df),
        len(df) - len(norm_df),
        )
    return norm_df
