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

    By default it tries to pull IPs from:
      - 'ipAddress'                         (string)
      - 'ipAddresses'                       (array<string> -> serialized as JSON or delimited)
      - 'aggregatedIps.ipAddresses'         (array<string> -> serialized as JSON or delimited)

    The label used for coloring (org) defaults to 'countryCode', but you can
    override that (e.g. 'region', 'behaviorType', etc.).
    """

    def __init__(
            self,
            path: str | Path,
            snapshot_date: Optional[str] = None,
            ip_col: str = "ipAddress",
            ip_list_cols: Sequence[str] = ("ipAddresses", "aggregatedIps.ipAddresses"),
            org_col: str = "countryCode",
            source_name: str = "Cider",
    ) -> None:
        super().__init__(source_name=source_name, snapshot_date=snapshot_date)
        self.path = Path(path)
        self.ip_col = ip_col
        self.ip_list_cols = tuple(ip_list_cols)
        self.org_col = org_col

        log.debug(
            "Initialized CiderCsvSource: path=%s ip_col=%s ip_list_cols=%s org_col=%s",
            self.path,
            self.ip_col,
            self.ip_list_cols,
            self.org_col,
        )

    def _parse_ip_list(self, raw: object) -> list[str]:
        """
        Parse a serialized list of IPs from Spark CSV.

        Handles:
          - JSON list: '["1.2.3.4","1.2.3.5"]'
          - JSON string: '"1.2.3.4"' (degenerate case)
          - Delimited text: '1.2.3.4,1.2.3.5' or '1.2.3.4 1.2.3.5'
        """
        if pd.isna(raw):
            return []

        s = str(raw).strip()
        if not s:
            return []

        # Try JSON first
        if (s.startswith("[") and s.endswith("]")) or (s.startswith('"') and s.endswith('"')):
            try:
                parsed = json.loads(s)
                if isinstance(parsed, str):
                    parsed = [parsed]
                if isinstance(parsed, list):
                    return [
                        str(x).strip()
                        for x in parsed
                        if str(x).strip()
                    ]
            except Exception:
                # Fall back to heuristic splitting
                pass

        # Fallback: split on comma or whitespace
        parts = re.split(r"[,\s]+", s)
        return [p.strip() for p in parts if p.strip()]

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

        has_any_ip_col = False
        if self.ip_col in df.columns:
            has_any_ip_col = True
        for col in self.ip_list_cols:
            if col in df.columns:
                has_any_ip_col = True
                break

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
                ip_raw = row[self.ip_col]
                if not pd.isna(ip_raw):
                    ip = str(ip_raw).strip()
                    if ip:
                        ips.add(ip)

            # IP list columns
            for col in self.ip_list_cols:
                if col not in df.columns:
                    continue
                ips.update(self._parse_ip_list(row[col]))

            if not ips:
                continue

            if has_org and not pd.isna(row.get(self.org_col)):
                org = str(row[self.org_col]).strip()
                if not org:
                    org = None
            else:
                org = None

            for ip in ips:
                emitted += 1
                yield IpRecord(
                    ip=ip,
                    prefix_len=None,            # normalize_dataframe will sort this out
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
