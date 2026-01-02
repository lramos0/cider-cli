# ipmap/utils/date_detection.py

from __future__ import annotations
from typing import Optional
import re
import pandas as pd
from ipmap.utils.logging import get_logger

log = get_logger(__name__)


def detect_date_column(df: pd.DataFrame) -> Optional[str]:
    """
    Detect if the DataFrame has a date-like column.

    Returns:
        Column name if found, None otherwise
    """
    if df.empty:
        return None

    # Common date column name patterns
    date_patterns = [
        r'date',
        r'month',
        r'year',
        r'time',
        r'ingest.*date',
        r'snapshot.*date',
        r'partition',
        r'dt',
        r'ds',
    ]

    # Check column names
    for col in df.columns:
        col_lower = str(col).lower()
        for pattern in date_patterns:
            if re.search(pattern, col_lower):
                # Verify the column has date-like values
                sample = df[col].dropna().head(10)
                if _looks_like_dates(sample):
                    log.info(f"Detected date column: {col}")
                    return col

    return None


def _looks_like_dates(series: pd.Series) -> bool:
    """
    Check if a pandas Series contains date-like values.
    """
    if series.empty:
        return False

    # Convert to strings and check patterns
    str_values = series.astype(str).tolist()

    date_like_count = 0
    for val in str_values[:10]:  # Check first 10 values
        val = val.strip()

        # Check for various date formats:
        # - ISO dates: 2025-01-01, 2025/01/01
        # - Month numbers: 1, 2, ..., 12
        # - Year: 2023, 2024, 2025
        # - Year-month: 2025-01, 202501
        patterns = [
            r'^\d{4}[-/]\d{1,2}[-/]\d{1,2}',  # YYYY-MM-DD or YYYY/MM/DD
            r'^\d{4}[-/]\d{1,2}$',             # YYYY-MM or YYYY/MM
            r'^\d{6,8}$',                       # YYYYMM or YYYYMMDD
            r'^(0?[1-9]|1[0-2])$',             # Month: 1-12
            r'^20[0-9]{2}$',                    # Year: 2000-2099
        ]

        for pattern in patterns:
            if re.match(pattern, val):
                date_like_count += 1
                break

    # If at least 70% of sampled values look like dates
    return date_like_count >= len(str_values) * 0.7


def parse_date_column(df: pd.DataFrame, date_col: str) -> pd.DataFrame:
    """
    Parse and normalize the date column to a standard format (YYYY-MM).

    Returns:
        DataFrame with a new 'time_period' column
    """
    df = df.copy()

    # Try to parse as datetime
    try:
        dates = pd.to_datetime(df[date_col], errors='coerce')
        # Extract year-month
        df['time_period'] = dates.dt.to_period('M').astype(str)
    except Exception as e:
        log.warning(f"Could not parse {date_col} as datetime: {e}")
        # Fallback: use the column as-is (string representation)
        df['time_period'] = df[date_col].astype(str)

    # Remove rows where time_period couldn't be determined
    df = df[df['time_period'].notna() & (df['time_period'] != 'NaT')]

    log.info(f"Parsed date column {date_col}, found {df['time_period'].nunique()} unique time periods")

    return df


def get_sorted_time_periods(df: pd.DataFrame) -> list[str]:
    """
    Get sorted list of unique time periods from the DataFrame.
    """
    if 'time_period' not in df.columns:
        return []

    periods = df['time_period'].dropna().unique().tolist()

    # Try to sort chronologically
    try:
        periods_sorted = sorted(periods)
    except Exception:
        periods_sorted = periods

    return periods_sorted
