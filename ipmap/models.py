# ipmap/models.py
from dataclasses import dataclass
from typing import Optional

@dataclass
class IpRecord:
    ip: str                 # "a.b.c.d" or "a.b.c.d/len"
    prefix_len: Optional[int]  # 24, 32, etc. (if known)
    source: str             # "Geofeed", "MaxMind", "PCAP"
    org: Optional[str]      # country code or ASN/org; whatever you’re coloring on
    snapshot_date: Optional[str] = None  # "2025-09-02"
