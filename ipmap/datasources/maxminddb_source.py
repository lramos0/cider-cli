# ipmap/datasources/maxminddb_source.py

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

from ipmap.models import IpRecord
from ipmap.datasources.base import DataSource
from ipmap.utils.logging import get_logger

log = get_logger(__name__)


class MaxMindCsvSource(DataSource):
    """
    Load a MaxMind GeoLite2 City snapshot from CSV files, like in the notebook.

    We expect a directory with at least:
      - GeoLite2-City-Blocks-IPv4.csv
      - GeoLite2-City-Locations-en.csv

    This class merges them on 'geoname_id' and emits IpRecord instances with:
      - ip = network (CIDR string, e.g. '1.2.3.0/24')
      - org = country_iso_code (2-letter country code)
    """

    def __init__(
            self,
            folder: str | Path,
            snapshot_date: Optional[str] = None,
            blocks_filename: str = "GeoLite2-City-Blocks-IPv4.csv",
            locations_filename: str = "GeoLite2-City-Locations-en.csv",
            source_name: str = "MaxMind",
    ) -> None:
        super().__init__(source_name=source_name, snapshot_date=snapshot_date)
        self.folder = Path(folder)
        self.blocks_filename = blocks_filename
        self.locations_filename = locations_filename

        log.debug(
            "Initialized MaxMindCsvSource: folder=%s blocks=%s locations=%s",
            self.folder,
            self.blocks_filename,
            self.locations_filename,
        )

    @property
    def blocks_path(self) -> Path:
        return self.folder / self.blocks_filename

    @property
    def locations_path(self) -> Path:
        return self.folder / self.locations_filename

    def load_records(self) -> Iterable[IpRecord]:
        if not self.blocks_path.exists():
            log.error("MaxMind blocks CSV not found: %s", self.blocks_path)
            raise FileNotFoundError(f"MaxMind blocks CSV not found: {self.blocks_path}")
        if not self.locations_path.exists():
            log.error("MaxMind locations CSV not found: %s", self.locations_path)
            raise FileNotFoundError(f"MaxMind locations CSV not found: {self.locations_path}")

        log.info(
            "Reading MaxMind CSV snapshot from %s (blocks) and %s (locations)",
            self.blocks_path,
            self.locations_path,
        )

        blocks = pd.read_csv(self.blocks_path)
        log.debug("Blocks CSV shape: %s", blocks.shape)

        # Only need geoname_id + country_iso_code for your use case
        locs = pd.read_csv(self.locations_path, usecols=["geoname_id", "country_iso_code"])
        log.debug("Locations CSV shape: %s", locs.shape)

        if "network" not in blocks.columns:
            log.error("Expected 'network' column in %s", self.blocks_path)
            raise ValueError(f"Expected column 'network' in {self.blocks_path}")

        # Cast geoname_id to a common type for the join
        blocks["geoname_id"] = blocks["geoname_id"].astype("Int64")
        locs["geoname_id"] = locs["geoname_id"].astype("Int64")

        merged = blocks.merge(locs, on="geoname_id", how="left")
        log.debug("Merged MaxMind DF shape: %s", merged.shape)

        total = len(merged)
        emitted = 0

        for _, row in merged.iterrows():
            network_raw = row["network"]
            if pd.isna(network_raw):
                continue

            network = str(network_raw).strip()
            if not network:
                continue

            country = row.get("country_iso_code")
            org = str(country).strip() if pd.notna(country) else None

            emitted += 1
            yield IpRecord(
                ip=network,
                prefix_len=None,
                source=self.source_name,
                org=org,
                snapshot_date=self.snapshot_date,
            )

        log.info(
            "MaxMindCsvSource %s: total rows=%d, emitted records=%d",
            self.folder,
            total,
            emitted,
        )
