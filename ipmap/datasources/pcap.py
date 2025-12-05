# ipmap/datasources/pcap.py

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

from ipmap.models import IpRecord
from ipmap.datasources.base import DataSource
from ipmap.utils.logging import get_logger

log = get_logger(__name__)


class PcapSource(DataSource):
    """
    Load IPv4 addresses from a pcap file using scapy.

    Each observed IPv4 endpoint becomes an IpRecord with:
      - ip = 'a.b.c.d'
      - prefix_len = 32
      - source = 'PCAP' (by default)
      - org = None (you can join with MaxMind/Geofeed separately later)

    Parameters
    ----------
    path : str | Path
        Path to the .pcap / .pcapng file.
    direction : {'src', 'dst', 'both'}, default 'both'
        Which IPs to emit per packet.
    sample_rate : int, default 1
        Use every Nth packet (1 = use all).
    """

    def __init__(
            self,
            path: str | Path,
            direction: str = "both",
            sample_rate: int = 1,
            source_name: str = "PCAP",
            snapshot_date: Optional[str] = None,
    ) -> None:
        super().__init__(source_name=source_name, snapshot_date=snapshot_date)
        self.path = Path(path)

        if direction not in ("src", "dst", "both"):
            raise ValueError("direction must be one of: 'src', 'dst', 'both'")
        if sample_rate < 1:
            raise ValueError("sample_rate must be >= 1")

        self.direction = direction
        self.sample_rate = sample_rate

        log.debug(
            "Initialized PcapSource: path=%s direction=%s sample_rate=%d",
            self.path,
            self.direction,
            self.sample_rate,
        )

    def load_records(self) -> Iterable[IpRecord]:
        try:
            from scapy.all import rdpcap, IP  # type: ignore
        except Exception as e:
            log.error(
                "PcapSource requires scapy to be installed. "
                "Install with `pip install scapy`."
            )
            raise RuntimeError(
                "PcapSource requires scapy to be installed. "
                "Install with `pip install scapy`."
            ) from e

        if not self.path.exists():
            log.error("PCAP file not found: %s", self.path)
            raise FileNotFoundError(f"PCAP file not found: {self.path}")

        log.info("Reading PCAP from %s", self.path)
        packets = rdpcap(str(self.path))
        log.debug("Loaded %d packets from %s", len(packets), self.path)

        emitted = 0

        for idx, pkt in enumerate(packets):
            # Subsample if sample_rate > 1
            if idx % self.sample_rate != 0:
                continue

            if not pkt.haslayer(IP):
                continue

            ip_layer = pkt[IP]
            candidates: list[str] = []

            if self.direction in ("src", "both"):
                candidates.append(ip_layer.src)
            if self.direction in ("dst", "both"):
                candidates.append(ip_layer.dst)

            for ip in candidates:
                # Skip IPv6 just in case
                if ":" in ip:
                    continue

                emitted += 1
                yield IpRecord(
                    ip=ip,
                    prefix_len=32,
                    source=self.source_name,
                    org=None,
                    snapshot_date=self.snapshot_date,
                )

        log.info(
            "PcapSource %s: packets=%d, emitted IPv4 records=%d",
            self.path,
            len(packets),
            emitted,
        )
