# ipmap/datasources/base.py

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, Optional

import pandas as pd

from ipmap.models import IpRecord
from ipmap.utils.logging import get_logger

log = get_logger(__name__)


class DataSource(ABC):
    """
    Abstract base class for all IP data sources (pcap, geofeed CSV, MaxMind snapshots, etc.).

    Subclasses should:
      - Accept a path (file or directory) plus optional parameters in __init__
      - Implement load_records() as a generator or iterator of IpRecord
    """

    def __init__(self, source_name: str, snapshot_date: Optional[str] = None) -> None:
        self.source_name = source_name
        self.snapshot_date = snapshot_date
        log.debug(
            "Initialized DataSource: source_name=%s snapshot_date=%s",
            self.source_name,
            self.snapshot_date,
        )

    @abstractmethod
    def load_records(self) -> Iterable[IpRecord]:
        """
        Yield IpRecord instances.

        Implementations should:
          - Skip non-IPv4 data (or leave that to downstream filters)
          - Fill IpRecord.source with a stable identifier (e.g. 'Geofeed', 'MaxMind', 'PCAP')
          - Optionally set snapshot_date if applicable (e.g. MaxMind dump date)
        """
        ...


def datasource_to_dataframe(ds: DataSource) -> pd.DataFrame:
    """
    Convenience helper: read all records from a DataSource into a pandas DataFrame
    whose columns match IpRecord's fields.
    """
    log.info("Loading records from datasource %s", ds.source_name)
    records = list(ds.load_records())
    log.info("Datasource %s produced %d records", ds.source_name, len(records))

    if not records:
        cols = [f.name for f in IpRecord.__dataclass_fields__.values()]
        return pd.DataFrame(columns=cols)

    return pd.DataFrame([r.__dict__ for r in records])

