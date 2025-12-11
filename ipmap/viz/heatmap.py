# ipmap/viz/heatmap.py

from __future__ import annotations

from typing import List, Literal

import numpy as np
import pandas as pd
import plotly.graph_objs as go

from ipmap.utils.logging import get_logger

log = get_logger(__name__)

HeatmapMode = Literal["primary", "country_count", "record_count"]
ColorscaleMode = Literal["default", "neon"]


# ============================================================
# Color palette builders
# ============================================================

def _build_default_palette(n: int) -> List[str]:
    """Softer, professional palette for dark mode, evenly spaced hues."""
    if n <= 0:
        return []
    return [
        f"hsl({(i * 360.0 / n):.1f}, 45%, 65%)"
        for i in range(n)
    ]


def _build_neon_palette(n: int) -> List[str]:
    """High-saturation neon palette for dark backgrounds."""
    if n <= 0:
        return []
    return [
        f"hsl({(i * 360.0 / n):.1f}, 100%, 55%)"
        for i in range(n)
    ]


def _build_discrete_colorscale(colors: List[str]):
    """Convert a list of categorical colors → Plotly colorscale."""
    n = len(colors)
    if n <= 1:
        c = colors[0] if n else "#000000"
        return [[0.0, c], [1.0, c]]
    step = 1.0 / (n - 1)
    return [[i * step, c] for i, c in enumerate(colors)]


# For "count" mode (num_countries) – same style as your notebook
MAX_COUNT_FOR_COLOR = 10  # counts above this all look like "high"
COUNT_COLORSCALE = [
    [0.0,  "#f7fbff"],  # 0–2: very light
    [0.29, "#f7fbff"],
    [0.30, "#6baed6"],  # 3–5: blue
    [0.50, "#6baed6"],
    [0.51, "#b30000"],  # 6+: red
    [1.0,  "#b30000"],
]

def build_24_heatmap(
        df_buckets_24: pd.DataFrame,
        parent_label: str,
        mode: HeatmapMode = "primary",
        colorscale_mode: ColorscaleMode = "default",
        title: str | None = None,
) -> go.Figure:
    """
    Build a Plotly heatmap for IPv4 /24 buckets under a given /16.

    Expected columns in df_buckets_24:
      - bucket24_x (int)              # 0..15
      - bucket24_y (int)              # 0..15
      - bucket24_label (str)          # "a.b.c"
      - orgs (list of org values)
      - num_prefixes (int)
      - primary_org (str)
      - num_countries (int)
    """
    if df_buckets_24.empty:
        log.warning("build_24_heatmap received an empty DataFrame")
        fig = go.Figure()
        fig.update_layout(
            title=title or f"/24s under {parent_label} (no data)",
            paper_bgcolor="#111111",
            plot_bgcolor="#111111",
            font=dict(color="#EEEEEE"),
        )
        return fig

    required_base = {
        "bucket24_x",
        "bucket24_y",
        "num_prefixes",
        "primary_org",
        "num_countries",
    }
    missing = required_base - set(df_buckets_24.columns)
    if missing:
        raise ValueError(f"df_buckets_24 is missing required columns: {missing}")

    log.info(
        "Building /24 heatmap for %s: mode=%s colorscale_mode=%s rows=%d",
        parent_label,
        mode,
        colorscale_mode,
        len(df_buckets_24),
    )

    # --------------------------------------------------------------
    # 1) Build fixed 16x16 grid indices (0..15 in each direction)
    # --------------------------------------------------------------
    # We *intentionally* use the full 0–15 range so that the grid
    # is always 16x16, with empty buckets showing as gaps.
    x_vals = list(range(16))
    y_vals = list(range(16))
    x_to_idx = {x: i for i, x in enumerate(x_vals)}
    y_to_idx = {y: i for i, y in enumerate(y_vals)}

    z_primary = [[None for _ in x_vals] for _ in y_vals]
    z_country = [[0 for _ in x_vals] for _ in y_vals]
    z_records = [[0 for _ in x_vals] for _ in y_vals]

    # --------------------------------------------------------------
    # 2) Map primary_org → index and build palettes
    # --------------------------------------------------------------
    orgs = (
        df_buckets_24["primary_org"]
        .dropna()
        .astype(str)
        .unique()
    )
    orgs_sorted = sorted(orgs)
    org_code_map = {org: idx for idx, org in enumerate(orgs_sorted)}
    n_orgs = len(org_code_map)

    if colorscale_mode == "neon":
        primary_palette = _build_neon_palette(n_orgs)
    else:
        primary_palette = _build_default_palette(n_orgs)
    primary_colorscale_default = _build_discrete_colorscale(primary_palette)

    primary_palette_neon = _build_neon_palette(n_orgs)
    primary_colorscale_neon = _build_discrete_colorscale(primary_palette_neon)

    # --------------------------------------------------------------
    # 3) Fill z-matrices
    # --------------------------------------------------------------
    for _, row in df_buckets_24.iterrows():
        bx = int(row["bucket24_x"])
        by = int(row["bucket24_y"])

        # Ignore any stray out-of-range values, just in case
        if bx not in x_to_idx or by not in y_to_idx:
            continue

        xi = x_to_idx[bx]
        yi = y_to_idx[by]

        # primary
        org = row["primary_org"]
        if org is None or (isinstance(org, float) and np.isnan(org)):
            z_primary[yi][xi] = None
        else:
            z_primary[yi][xi] = org_code_map.get(str(org))

        # country_count (num_countries)
        z_country[yi][xi] = int(row["num_countries"])

        # record_count (num_prefixes)
        z_records[yi][xi] = int(row["num_prefixes"])

    # ------------------------------------------------------------------
    # 3b) Precompute max values for count modes (ignoring empty cells)
    # ------------------------------------------------------------------
    vals_country = [v for row in z_country for v in row if v is not None]
    max_country = max(vals_country) if vals_country else 0

    vals_records = [v for row in z_records for v in row if v is not None]
    max_records = max(vals_records) if vals_records else 0

    # --------------------------------------------------------------
    # 4) Choose initial mode
    # --------------------------------------------------------------
    if mode not in ("primary", "country_count", "record_count"):
        log.warning("Unknown mode %r for /24; falling back to 'primary'", mode)
        mode = "primary"

    if mode == "primary":
        z_init = z_primary
        colorscale_init = primary_colorscale_default
        zmin_init = 0
        zmax_init = max(org_code_map.values()) if org_code_map else 1
        hover_init = (
            "Bucket: %{text}<br>"
            "Primary org index: %{z}<extra></extra>"
        )
        colorbar_title_init = "Org index"
    elif mode == "country_count":
        z_init = z_country
        colorscale_init = COUNT_COLORSCALE
        zmin_init = 0
        zmax_init = max(min(max_country, MAX_COUNT_FOR_COLOR), 1)
        hover_init = (
            "Bucket: %{x}.%{y}.0.0/16<br>"
            "# unique orgs: %{z}<extra></extra>"
        )
        colorbar_title_init = "# orgs"

    else:  # record_count
        z_init = z_records
        colorscale_init = COUNT_COLORSCALE
        zmin_init = 0
        zmax_init = max(max_records, 1)
        hover_init = (
            "Bucket: %{x}.%{y}.0.0/16<br>"
            "# prefixes: %{z}<extra></extra>"
        )
        colorbar_title_init = "# prefixes"

    # We want each cell labeled with its actual a.b.c prefix
    # Build a text grid parallel to z_*
    text_grid = [["" for _ in x_vals] for _ in y_vals]
    for _, row in df_buckets_24.iterrows():
        bx = int(row["bucket24_x"])
        by = int(row["bucket24_y"])
        if bx not in x_to_idx or by not in y_to_idx:
            continue
        xi = x_to_idx[bx]
        yi = y_to_idx[by]
        text_grid[yi][xi] = str(row.get("bucket24_label", ""))

    # --------------------------------------------------------------
    # 5) Heatmap trace
    # --------------------------------------------------------------
    heatmap = go.Heatmap(
        z=z_init,
        x=x_vals,
        y=y_vals,
        text=text_grid,
        hovertemplate=hover_init,
        colorscale=colorscale_init,
        zmin=zmin_init,
        zmax=zmax_init,
        colorbar=dict(title=colorbar_title_init),
    )

    fig_title = title or f"/24s under {parent_label}"

    fig = go.Figure(data=[heatmap])
    fig.update_layout(
        title=fig_title,
        autosize=True,
        width=None,
        height=None,
        margin=dict(l=60, r=60, t=60, b=60),
        paper_bgcolor="#111111",
        plot_bgcolor="#111111",
        font=dict(color="#EEEEEE"),
        xaxis=dict(
            title="bucket24_x (0–15)",
            gridcolor="#333333",
            zerolinecolor="#333333",
            linecolor="#EEEEEE",
            range=[-0.5, 15.5],
            dtick=1,
            visible=False
        ),
        yaxis=dict(
            title="bucket24_y (0–15)",
            gridcolor="#333333",
            zerolinecolor="#333333",
            linecolor="#EEEEEE",
            range=[15.5, -0.5],  # reversed 0..15
            dtick=1,
            scaleanchor="x",
            scaleratio=1,
            visible=False
        ),
        clickmode="event+select",
    )

    fig.update_traces(
        xgap=1,
        ygap=1,
        colorbar=dict(
            thickness=18,
            len=0.75,
        ),
    )

    # --------------------------------------------------------------
    # 6) Optional colorscale toggle (same as /16)
    # --------------------------------------------------------------
    hover_primary = (
        "Bucket: %{text}<br>"
        "Primary org index: %{z}<extra></extra>"
    )
    hover_country = (
        "Bucket: %{text}<br>"
        "# unique orgs: %{z}<extra></extra>"
    )
    hover_records = (
        "Bucket: %{text}<br>"
        "# prefixes: %{z}<extra></extra>"
    )

    fig.update_layout(
        updatemenus=[
            dict(
                type="buttons",
                direction="left",
                x=0.0,
                y=1.02,
                xanchor="left",
                yanchor="bottom",
                pad=dict(r=10, t=0),
                font=dict(size=10),
                buttons=[
                    dict(
                        label="Primary (categorical)",
                        method="update",
                        args=[{
                            "z": [z_primary],
                            "colorscale": [primary_colorscale_default],
                            "zmin": [0],
                            "zmax": [max(org_code_map.values()) if org_code_map else 1],
                            "hovertemplate": [hover_primary],
                            "colorbar": [dict(title="Org index")],
                        }],
                    ),
                    dict(
                        label="# Orgs (country_count)",
                        method="update",
                        args=[{
                            "z": [z_country],
                            "colorscale": [COUNT_COLORSCALE],
                            "zmin": [0],
                            "zmax": [max(min(max_country, MAX_COUNT_FOR_COLOR), 1)],
                            "hovertemplate": [hover_country],
                            "colorbar": [dict(title="# orgs")],
                        }],
                    ),
                    dict(
                        label="# Prefixes (record_count)",
                        method="update",
                        args=[{
                            "z": [z_records],
                            "colorscale": [COUNT_COLORSCALE],
                            "zmin": [0],
                            "zmax": [max(max_records, 1)],
                            "hovertemplate": [hover_records],
                            "colorbar": [dict(title="# prefixes")],
                        }],
                    ),
                ],
            ),
            dict(
                type="buttons",
                direction="left",
                x=0.55,
                y=1.02,
                xanchor="left",
                yanchor="bottom",
                pad=dict(r=10, t=0),
                font=dict(size=10),
                buttons=[
                    dict(
                        label="Colors: default",
                        method="restyle",
                        args=[{"colorscale": [primary_colorscale_default]}],
                    ),
                    dict(
                        label="Colors: neon",
                        method="restyle",
                        args=[{"colorscale": [primary_colorscale_neon]}],
                    ),
                ],
            ),
        ]
    )

    log.debug("Finished building /24 heatmap figure for %s", parent_label)
    return fig

# ============================================================
# /16 heatmap builder
# ============================================================


def build_16_heatmap(
        df_buckets_16: pd.DataFrame,
        mode: HeatmapMode = "primary",
        colorscale_mode: ColorscaleMode = "default",
        title: str | None = None,
) -> go.Figure:
    """
    Build a Plotly heatmap for IPv4 /16 buckets.

    Expected columns in df_buckets_16:
      - bucket_x (int)             # first octet
      - bucket_y (int)             # second octet
      - bucket_label (str)         # "a.b"
      - orgs (list of org values)  # produced by bucket_16
      - num_prefixes (int)
      - primary_org (str)
      - num_countries (int)
    """
    if df_buckets_16.empty:
        log.warning("build_16_heatmap received an empty DataFrame")
        fig = go.Figure()
        fig.update_layout(
            title=title or "IPv4 /16 Address Space (no data)",
            paper_bgcolor="#111111",
            plot_bgcolor="#111111",
            font=dict(color="#EEEEEE"),
        )
        return fig

    required_base = {"bucket_x", "bucket_y", "num_prefixes", "primary_org", "num_countries"}
    missing = required_base - set(df_buckets_16.columns)
    if missing:
        raise ValueError(f"df_buckets_16 is missing required columns: {missing}")

    # Normalize mode aliases so CLI "--mode count" still works
    if mode == "count":
        mode = "country_count"

    log.info(
        "Building /16 heatmap: mode=%s colorscale_mode=%s rows=%d",
        mode,
        colorscale_mode,
        len(df_buckets_16),
    )

    # ------------------------------------------------------------------
    # 1) Build full IPv4 /16 grid axes (0..255 in each dimension)
    # ------------------------------------------------------------------
    x_vals = list(range(256))  # first octet 0–255
    y_vals = list(range(256))  # second octet 0–255
    x_to_idx = {x: i for i, x in enumerate(x_vals)}
    y_to_idx = {y: i for i, y in enumerate(y_vals)}

    # Initialize z-matrices for all modes.
    # Use None for "no data" so empty /16s are transparent (no color).
    z_primary = [[None for _ in x_vals] for _ in y_vals]
    z_country = [[None for _ in x_vals] for _ in y_vals]
    z_records = [[None for _ in x_vals] for _ in y_vals]

    # ------------------------------------------------------------------
    # 2) Prepare mapping for primary_org → index and palettes
    # ------------------------------------------------------------------
    orgs = (
        df_buckets_16["primary_org"]
        .dropna()
        .astype(str)
        .unique()
    )
    orgs_sorted = sorted(orgs)
    org_code_map = {org: idx for idx, org in enumerate(orgs_sorted)}
    n_orgs = len(org_code_map)

    # If there are no non-null orgs (typical for pcap), fall back to record_count
    if n_orgs == 0 and mode == "primary":
        log.info(
            "No non-null primary_org values; falling back to 'record_count' mode "
            "(this is expected for kind=pcap where org is empty)."
        )
        mode = "record_count"

    if colorscale_mode == "neon":
        primary_palette = _build_neon_palette(n_orgs)
    else:
        primary_palette = _build_default_palette(n_orgs)
    primary_colorscale_default = _build_discrete_colorscale(primary_palette)

    # A neon variant is always available for the colorscale toggle
    primary_palette_neon = _build_neon_palette(n_orgs)
    primary_colorscale_neon = _build_discrete_colorscale(primary_palette_neon)

    # ------------------------------------------------------------------
    # 3) Fill z-matrices
    # ------------------------------------------------------------------
    for _, row in df_buckets_16.iterrows():
        bx = int(row["bucket_x"])
        by = int(row["bucket_y"])
        xi = x_to_idx[bx]
        yi = y_to_idx[by]

        # primary (categorical)
        org = row["primary_org"]
        if org is None or (isinstance(org, float) and np.isnan(org)):
            z_primary[yi][xi] = None
        else:
            z_primary[yi][xi] = org_code_map.get(str(org))

        # country_count (num_countries)
        z_country[yi][xi] = int(row["num_countries"])

        # record_count (num_prefixes)
        z_records[yi][xi] = int(row["num_prefixes"])

    # ------------------------------------------------------------------
    # 4) Choose initial mode settings
    # ------------------------------------------------------------------
    if mode not in ("primary", "country_count", "record_count"):
        log.warning("Unknown mode %r; falling back to 'primary'", mode)
        mode = "primary"

    if mode == "primary":
        z_init = z_primary
        colorscale_init = primary_colorscale_default
        zmin_init = 0
        zmax_init = max(org_code_map.values()) if org_code_map else 1
        hover_init = (
            "Bucket: %{x}.%{y}.0.0/16<br>"
            "Primary org index: %{z}<extra></extra>"
        )
        colorbar_title_init = "Org index"

    elif mode == "country_count":
        z_init = z_country
        colorscale_init = COUNT_COLORSCALE
        zmin_init = 0

        vals = [v for row in z_country for v in row if v is not None]
        max_val = max(vals) if vals else 0
        zmax_init = max(min(max_val, MAX_COUNT_FOR_COLOR), 1)

        hover_init = (
            "Bucket: %{x}.%{y}.0.0/16<br>"
            "# unique orgs: %{z}<extra></extra>"
        )
        colorbar_title_init = "# orgs"

    else:  # record_count
        z_init = z_records
        colorscale_init = COUNT_COLORSCALE
        zmin_init = 0

        vals = [v for row in z_records for v in row if v is not None]
        max_val = max(vals) if vals else 0
        zmax_init = max(max_val, 1)

        hover_init = (
            "Bucket: %{x}.%{y}.0.0/16<br>"
            "# prefixes: %{z}<extra></extra>"
        )
        colorbar_title_init = "# prefixes"

    # ------------------------------------------------------------------
    # 5) Build initial Heatmap trace
    # ------------------------------------------------------------------
    heatmap = go.Heatmap(
        z=z_init,
        x=x_vals,
        y=y_vals,
        colorscale=colorscale_init,
        zmin=zmin_init,
        zmax=zmax_init,
        hovertemplate=hover_init,
        colorbar=dict(title=colorbar_title_init),
    )

    fig_title = title or "IPv4 /16 Address Space"
    fig = go.Figure(data=[heatmap])

    fig.update_layout(
        title=fig_title,
        autosize=True,
        width=None,
        height=None,
        margin=dict(l=60, r=60, t=60, b=60),
        paper_bgcolor="#111111",
        plot_bgcolor="#111111",
        font=dict(color="#EEEEEE"),
        xaxis=dict(
            title="First octet (0–255)",
            gridcolor="#333333",
            zerolinecolor="#333333",
            linecolor="#EEEEEE",
            range=[-0.5, 255.5],
            dtick=16,
            visible=False
        ),
        yaxis=dict(
            title="Second octet (0–255)",
            gridcolor="#333333",
            zerolinecolor="#333333",
            linecolor="#EEEEEE",
            range=[255.5, -0.5],
            dtick=16,
            visible=False
        ),
        clickmode="event+select",
    )

    fig.update_traces(
        xgap=1,
        ygap=1,
        colorbar=dict(
            thickness=18,
            len=0.75,
        ),
    )

    # ------------------------------------------------------------------
    # 6) Add interactive buttons (mode + colorscale)
    # ------------------------------------------------------------------
    hover_primary = (
        "Bucket: %{x}.%{y}.0.0/16<br>"
        "Primary org index: %{z}<extra></extra>"
    )
    hover_country = (
        "Bucket: %{x}.%{y}.0.0/16<br>"
        "# unique orgs: %{z}<extra></extra>"
    )
    hover_records = (
        "Bucket: %{x}.%{y}.0.0/16<br>"
        "# prefixes: %{z}<extra></extra>"
    )

    fig.update_layout(
        updatemenus=[
            # Mode selector
            dict(
                type="buttons",
                direction="left",
                x=0.0,
                y=1.02,
                xanchor="left",
                yanchor="bottom",
                pad=dict(r=10, t=0),
                font=dict(size=10),
                buttons=[
                    dict(
                        label="Primary (categorical)",
                        method="update",
                        args=[{
                            "z": [z_primary],
                            "colorscale": [primary_colorscale_default],
                            "zmin": [0],
                            "zmax": [max(org_code_map.values()) if org_code_map else 1],
                            "hovertemplate": [hover_primary],
                            "colorbar": [dict(title="Org index")],
                        }],
                    ),
                    dict(
                        label="# Orgs (country_count)",
                        method="update",
                        args=[{
                            "z": [z_country],
                            "colorscale": [COUNT_COLORSCALE],
                            "zmin": [0],
                            "zmax": [max(
                                min(
                                    max(v for row in z_country for v in row if v is not None),
                                    MAX_COUNT_FOR_COLOR,
                                ),
                                1,
                            )],
                            "hovertemplate": [hover_country],
                            "colorbar": [dict(title="# orgs")],
                        }],
                    ),
                    dict(
                        label="# Prefixes (record_count)",
                        method="update",
                        args=[{
                            "z": [z_records],
                            "colorscale": [COUNT_COLORSCALE],
                            "zmin": [0],
                            "zmax": [max(
                                max(v for row in z_records for v in row if v is not None),
                                1,
                            )],
                            "hovertemplate": [hover_records],
                            "colorbar": [dict(title="# prefixes")],
                        }],
                    ),
                ],
            ),
            # Colorscale selector (only meaningful for primary mode)
            dict(
                type="buttons",
                direction="left",
                x=0.55,
                y=1.02,
                xanchor="left",
                yanchor="bottom",
                pad=dict(r=10, t=0),
                font=dict(size=10),
                buttons=[
                    dict(
                        label="Colors: default",
                        method="restyle",
                        args=[{"colorscale": [primary_colorscale_default]}],
                    ),
                    dict(
                        label="Colors: neon",
                        method="restyle",
                        args=[{"colorscale": [primary_colorscale_neon]}],
                    ),
                ],
            ),
        ]
    )

    log.debug("Finished building /16 heatmap figure with interactive controls")
    return fig


