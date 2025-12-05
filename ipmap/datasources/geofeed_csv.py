# ipmap/datasources/geofeed_csv.py

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

from ipmap.models import IpRecord
from ipmap.datasources.base import DataSource
from ipmap.utils.logging import get_logger

log = get_logger(__name__)


class GeofeedCsvSource(DataSource):
    """
    Load geofeed/RIR-style CSVs like the ones in the notebook.

    Expected columns (at minimum):
      - 'CIDR Prefix' : CIDR notation, e.g. '1.2.3.0/24'
      - 'Alpha2Code'  : country code (e.g. 'US', 'DE')

    If your CSVs use different column names, you can override them.
    """

    def __init__(
            self,
            path: str | Path,
            snapshot_date: Optional[str] = None,
            cidr_col: str = "CIDR Prefix",
            country_col: str = "Alpha2Code",
            source_name: str = "Geofeed",
    ) -> None:
        super().__init__(source_name=source_name, snapshot_date=snapshot_date)
        self.path = Path(path)
        self.cidr_col = cidr_col
        self.country_col = country_col
        log.debug(
            "Initialized GeofeedCsvSource: path=%s cidr_col=%s country_col=%s",
            self.path,
            self.cidr_col,
            self.country_col,
        )

    def load_records(self) -> Iterable[IpRecord]:
        if not self.path.exists():
            log.error("Geofeed CSV not found: %s", self.path)
            raise FileNotFoundError(f"Geofeed CSV not found: {self.path}")

        log.info("Reading geofeed CSV from %s", self.path)

        # More forgiving parser: handles ragged lines / extra commas better.
        # We also:
        #   - treat lines starting with '#' as comments
        #   - warn (not fail) on bad lines
        df = pd.read_csv(
            self.path,
            engine="python",
            on_bad_lines="warn",      # or "skip" if you want less spam
            comment="#",
            encoding="utf-8",
            encoding_errors="replace",   # <-- the key line
        )
        log.debug("Geofeed CSV shape after parse: %s", df.shape)

        if self.cidr_col not in df.columns:
            log.error("Missing column %r in geofeed CSV %s", self.cidr_col, self.path)
            raise ValueError(f"Missing column {self.cidr_col!r} in {self.path}")

        has_country = self.country_col in df.columns
        if not has_country:
            log.warning(
                "Geofeed CSV %s has no %r column; org will be None",
                self.path,
                self.country_col,
            )

        total = len(df)
        emitted = 0

        for _, row in df.iterrows():
            cidr_raw = row[self.cidr_col]
            if pd.isna(cidr_raw):
                continue

            cidr = str(cidr_raw).strip()
            if not cidr:
                continue

            if has_country and not pd.isna(row.get(self.country_col)):
                org = str(row[self.country_col]).strip()
                if not org:
                    org = None
            else:
                org = None

            emitted += 1
            yield IpRecord(
                ip=cidr,
                prefix_len=None,
                source=self.source_name,
                org=org,
                snapshot_date=self.snapshot_date,
            )

        log.info(
            "GeofeedCsvSource %s: total parsed rows=%d, emitted records=%d",
            self.path,
            total,
            emitted,
        )

