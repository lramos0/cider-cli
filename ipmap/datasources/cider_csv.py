# ipmap/datasources/cider_csv.py

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional, Sequence

import json
import re

import pandas as pd

from ipmap.models import IpRecord
from ipmap.datasources.base import DataSource
from ipmap.utils.logging import get_logger

log = get_logger(__name__)


class CiderCsvSource(DataSource):
    """
    Load 'cider' ban/alarm CSVs exported from Spark.

    IP extraction:
      - ipAddress (string)
      - ipAddresses (array<string> serialized as JSON or delimited)
      - aggregatedIps.ipAddresses (array<string> serialized as JSON or delimited)
        (or whatever you exported it as; see ip_list_cols)

    Grouping key:
      - org_col (default: countryCode)
      - If org_col contains a JSON list and explode_org=True, emit one record per org value.
        This is useful for fields like behaviorTypes.
    """

    def __init__(
            self,
            path: str | Path,
            snapshot_date: Optional[str] = None,
            ip_col: str = "ipAddress",
            ip_list_cols: Sequence[str] = ("ipAddresses", "aggregatedIps.ipAddresses"),
            org_col: str = "countryCode",
            explode_org: bool = False,
            source_name: str = "Cider",
    ) -> None:
        super().__init__(source_name=source_name, snapshot_date=snapshot_date)
        self.path = Path(path)
        self.ip_col = ip_col
        self.ip_list_cols = tuple(ip_list_cols)
        self.org_col = org_col
        self.explode_org = explode_org

        log.debug(
            "Initialized CiderCsvSource: path=%s ip_col=%s ip_list_cols=%s org_col=%s explode_org=%s",
            self.path,
            self.ip_col,
            self.ip_list_cols,
            self.org_col,
            self.explode_org,
        )

    def _parse_json_or_split_list(self, raw: object) -> list[str]:
        """
        Parse a serialized list of strings from Spark CSV.

        Handles:
          - JSON list: '["a","b"]'
          - JSON string: '"a"' (degenerate case)
          - Delimited text: 'a,b' or 'a b'
        """
        if raw is None or pd.isna(raw):
            return []

        s = str(raw).strip()
        if not s:
            return []

        # Try JSON first if it looks like JSON
        if (s.startswith("[") and s.endswith("]")) or (s.startswith('"') and s.endswith('"')):
            try:
                parsed = json.loads(s)
                if isinstance(parsed, str):
                    parsed = [parsed]
                if isinstance(parsed, list):
                    out = []
                    for x in parsed:
                        xs = str(x).strip()
                        if xs:
                            out.append(xs)
                    return out
            except Exception:
                pass

        # Fallback: split on comma or whitespace
        parts = re.split(r"[,\s]+", s)
        return [p.strip() for p in parts if p.strip()]

    def _parse_ip_list(self, raw: object) -> list[str]:
        # alias for readability
        return self._parse_json_or_split_list(raw)

    def _parse_org_values(self, row: pd.Series, has_org: bool) -> list[Optional[str]]:
        """
        Returns a list of org values to emit for this row.
        - If explode_org=False: returns [org_or_None]
        - If explode_org=True and org_col contains a list-like value: returns [org1, org2, ...]
        """
        if not has_org or pd.isna(row.get(self.org_col)):
            return [None]

        raw = row.get(self.org_col)
        s = str(raw).strip()
        if not s:
            return [None]

        if not self.explode_org:
            return [s]

        # explode_org=True: try to parse list, otherwise treat as single
        vals = self._parse_json_or_split_list(s)
        if not vals:
            return [None]
        return vals

    def load_records(self) -> Iterable[IpRecord]:
        if not self.path.exists():
            log.error("Cider CSV not found: %s", self.path)
            raise FileNotFoundError(f"Cider CSV not found: {self.path}")

        log.info("Reading Cider CSV from %s", self.path)

        df = pd.read_csv(
            self.path,
            engine="python",
            on_bad_lines="warn",
            comment="#",
            encoding="utf-8",
            encoding_errors="replace",
        )
        log.debug("Cider CSV shape after parse: %s", df.shape)

        # Validate there is at least one IP column
        has_any_ip_col = (self.ip_col in df.columns) or any(c in df.columns for c in self.ip_list_cols)
        if not has_any_ip_col:
            log.error(
                "Cider CSV has none of the expected IP columns: %r or any of %r",
                self.ip_col,
                self.ip_list_cols,
            )
            raise ValueError(
                f"Cider CSV must contain at least one IP column: "
                f"{self.ip_col!r} or one of {self.ip_list_cols!r}"
            )

        has_org = self.org_col in df.columns
        if not has_org:
            log.warning(
                "Cider CSV %s has no %r column; org will be None",
                self.path,
                self.org_col,
            )

        total = len(df)
        emitted = 0

        for _, row in df.iterrows():
            ips: set[str] = set()

            # Single IP column
            if self.ip_col in df.columns:
                ip_raw = row.get(self.ip_col)
                if ip_raw is not None and not pd.isna(ip_raw):
                    ip = str(ip_raw).strip()
                    if ip:
                        ips.add(ip)

            # IP list columns
            for col in self.ip_list_cols:
                if col not in df.columns:
                    continue
                ips.update(self._parse_ip_list(row.get(col)))

            if not ips:
                continue

            org_values = self._parse_org_values(row, has_org=has_org)

            for ip in ips:
                for org in org_values:
                    emitted += 1
                    yield IpRecord(
                        ip=ip,
                        prefix_len=None,  # normalize_dataframe will sort this out
                        source=self.source_name,
                        org=org,
                        snapshot_date=self.snapshot_date,
                    )

        log.info(
            "CiderCsvSource %s: total parsed rows=%d, emitted records=%d",
            self.path,
            total,
            emitted,
        )
