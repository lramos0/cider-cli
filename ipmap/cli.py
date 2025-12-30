from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, Literal

import typer
import pandas as pd

from ipmap.datasources.base import datasource_to_dataframe
from ipmap.datasources.geofeed_csv import GeofeedCsvSource
from ipmap.datasources.maxminddb_source import MaxMindCsvSource
from ipmap.datasources.pcap import PcapSource
from ipmap.datasources.cider_csv import CiderCsvSource
from ipmap.processing.normalize import normalize_dataframe
from ipmap.processing.bucket import bucket_16, bucket_24, bucket_32
from ipmap.processing.stats import attach_primary_and_counts
from ipmap.viz.heatmap import build_16_heatmap
from ipmap.viz.export import save_html, save_png, save_html_with_whois_on_click
from ipmap.utils.logging import get_logger

app = typer.Typer(help="IPv4 address space visualization (pcap, geofeed CSV, MaxMind CSV).")

log = get_logger(__name__)

ViewType = Literal["/16", "/24", "/32"]
KindType = Literal["geofeed", "maxmind", "pcap", "cider"]
ModeType = Literal["primary", "country_count", "record_count"]
ColorscaleType = Literal["default", "neon"]
OutputFormat = Literal["html", "png"]


def _load_dataframe(
        input_path: Path,
        kind: KindType,
        snapshot_date: Optional[str],
        pcap_direction: str,
        pcap_sample_rate: int,
        cider_group_col: Optional[str] = None,
        cider_group_explode: bool = False,
) -> pd.DataFrame:
    """
    Internal helper to instantiate the right DataSource,
    load records, and return a DataFrame.
    """
    input_path = input_path.expanduser().resolve()
    log.info("Input: %s (kind=%s)", input_path, kind)

    if kind == "geofeed":
        ds = GeofeedCsvSource(
            path=input_path,
            snapshot_date=snapshot_date,
        )
    elif kind == "maxmind":
        ds = MaxMindCsvSource(
            folder=input_path,
            snapshot_date=snapshot_date,
        )
    elif kind == "pcap":
        ds = PcapSource(
            path=input_path,
            direction=pcap_direction,
            sample_rate=pcap_sample_rate,
            snapshot_date=snapshot_date,
        )
    elif kind == "cider":
        ds = CiderCsvSource(
            path=input_path,
            snapshot_date=snapshot_date,
            org_col=cider_group_col or "countryCode",
            explode_org=cider_group_explode,
        )
    else:
        raise typer.BadParameter(f"Unsupported kind: {kind}")

    df = datasource_to_dataframe(ds)
    if df.empty:
        log.warning("No records loaded from %s", input_path)
    else:
        log.info("Loaded %d records from %s", len(df), input_path)

    return df


@app.command()
def map(
        input: Path = typer.Argument(
            ...,
            exists=True,
            help="Path to input file or directory (pcap, geofeed CSV, or MaxMind CSV folder).",
        ),
        kind: KindType = typer.Option(
            ...,
            "--kind",
            "-k",
            help="Type of input: geofeed | maxmind | pcap | cider",
        ),
        view: ViewType = typer.Option(
            "/16",
            "--view",
            "-v",
            help="Aggregation level: /16 | /24 | /32 (currently only /16 is visualized).",
        ),
        output: Path = typer.Option(
            Path("ipmap.html"),
            "--output",
            "-o",
            help="Output file path (HTML or PNG).",
        ),
        output_format: OutputFormat = typer.Option(
            "html",
            "--output-format",
            "-f",
            help="Output format: html | png",
        ),
        snapshot_date: Optional[str] = typer.Option(
            None,
            "--snapshot-date",
            help="Optional snapshot date label (e.g. 2025-09-02) stored in the data.",
        ),
        mode: ModeType = typer.Option(
            "primary",
            "--mode",
            "-m",
            help=(
                    "Coloring mode for /16 view: "
                    "primary (categorical primary org), "
                    "country_count (# unique orgs per /16), "
                    "record_count (# prefixes per /16). "
                    "Note: you can also switch modes interactively in the HTML."
            ),
        ),
        colorscale_mode: ColorscaleType = typer.Option(
            "default",
            "--colorscale",
            "-c",
            help="Colorscale for categorical primary mode: default | neon",
        ),
        nested: bool = typer.Option(
            False,
            "--nested",
            help="Enable nested drill-down: generate /24 HTMLs per /16 and make /16 cells clickable.",
        ),
        pcap_direction: str = typer.Option(
            "both",
            "--pcap-direction",
            help="For kind=pcap, which endpoints to count: src | dst | both",
        ),
        pcap_sample_rate: int = typer.Option(
            1,
            "--pcap-sample-rate",
            help="For kind=pcap, use every Nth packet (1 = use all).",
        ),
        cider_group_col: Optional[str] = typer.Option(
            None,
            "--cider-group-col",
            help=(
                    "For kind=cider: which CSV column to use as the grouping key (stored as 'org'). "
                    "Examples: countryCode, region, behaviorType, decisionSource, behaviorTypes, etc."
            ),
        ),
        cider_group_explode: bool = typer.Option(
            False,
            "--cider-group-explode",
            help=(
                    "For kind=cider: if the group column contains a JSON list (e.g. behaviorTypes), "
                    "emit one record per value."
            ),
        ),
        whois_on_click: bool = typer.Option(
            True,
            "--whois-on-click/--no-whois-on-click",
            help="In HTML output, clicking a /16 cell opens a WHOIS/RDAP lookup in a new tab.",
        ),
        whois_provider: str = typer.Option(
            "rdap_org",
            "--whois-provider",
            help='WHOIS provider for click-to-whois: "rdap_org" (recommended) or "arin".',
        ),


):
    """
    Build an IP map visualization from a pcap, geofeed CSV, or MaxMind CSV snapshot.

    Example:

        ipmap map geofeed.csv --kind geofeed --view /16 -o geofeed_map.html
        ipmap map GeoLite2-City-CSV_20250902 --kind maxmind -o mm_map.html
        ipmap map capture.pcap --kind pcap --view /16 --pcap-direction src -o pcap_map.html
    """
    # 1) load
    df = _load_dataframe(
        input_path=input,
        kind=kind,
        snapshot_date=snapshot_date,
        pcap_direction=pcap_direction,
        pcap_sample_rate=pcap_sample_rate,
        cider_group_col=cider_group_col,
        cider_group_explode=cider_group_explode,
    )

    if df.empty:
        typer.echo("No records loaded; nothing to visualize.", err=True)
        raise typer.Exit(code=1)

    # 2) normalize IPs / prefixes
    df = normalize_dataframe(df, ip_col="ip", prefix_len_col="prefix_len")

    print("=== df.head() AFTER normalize ===")
    print(df.head(10))
    print("=== column dtypes ===")
    print(df.dtypes)

    # Count IPv4 vs IPv6 in a dumb way
    print("IPv4-ish vs IPv6-ish counts (based on ':' presence):")
    print(df["ip"].str.contains(":", na=True).value_counts())

    # 3) bucket + stats depending on view
    if view == "/16":
        buckets_16 = bucket_16(
            df,
            ip_col="ip",
            org_col="org",
            extra_group_cols=["source", "snapshot_date"],
        )
        buckets_16 = attach_primary_and_counts(
            buckets_16,
            orgs_col="orgs",
            primary_col="primary_org",
            count_col="num_countries",
        )

        # If nested, also compute /24 buckets once here
        buckets_24 = None
        if nested:

            buckets_24 = bucket_24(
                df,
                ip_col="ip",
                org_col="org",
                extra_group_cols=["source", "snapshot_date"],
            )
            buckets_24 = attach_primary_and_counts(
                buckets_24,
                orgs_col="orgs",
                primary_col="primary_org",
                count_col="num_countries",
            )

        from ipmap.viz.heatmap import build_16_heatmap, build_24_heatmap
        from ipmap.viz.export import (
            save_html,
            save_html_nested_16,
            save_html_with_backlink_and_whois,
            save_html_consolidated,
        )

        fig = build_16_heatmap(
            buckets_16,
            mode=mode,
            colorscale_mode=colorscale_mode,
            title=f"CIDR Map produced via cider-cli",
        )

        # 4) export
        output = output.expanduser().resolve()
        if output_format != "html":
            # keep existing PNG behavior, nested doesn’t apply
            if output.suffix.lower() != ".png":
                output = output.with_suffix(".png")
            save_png(fig, output)
            typer.echo(f"Wrote visualization to {output}")
            return

        # HTML export, with optional nested behaviour
        if not nested:
            if output.suffix.lower() not in (".html", ".htm"):
                output = output.with_suffix(".html")

            if whois_on_click:
                save_html_with_whois_on_click(fig, output, provider=whois_provider)
            else:
                save_html(fig, output)

            typer.echo(f"Wrote visualization to {output}")
            return


    # --- NESTED MODE ---
        if output.suffix.lower() not in (".html", ".htm"):
            output = output.with_suffix(".html")

        # 1) Prompt user BEFORE generating /24 figures (to avoid wasted computation)
        consolidate = typer.confirm(
            "Would you like to consolidate under a single .html?",
            default=True
        )

        if buckets_24 is None or buckets_24.empty:
            log.warning("No /24 data available for nested mode")
            # Fall back to simple /16 export
            if whois_on_click:
                save_html_with_whois_on_click(fig, output, provider=whois_provider)
            else:
                save_html(fig, output)
            typer.echo(f"Wrote visualization to {output}")
            return

        # Create a set of /16 blocks that have data (to avoid generating /24 views for empty /16s)
        blocks_with_data = set(
            zip(buckets_16['bucket_x'].astype(int), buckets_16['bucket_y'].astype(int))
        )
        log.info(f"Found {len(blocks_with_data)} /16 blocks with data")

        if consolidate:
            # 2a) CONSOLIDATE MODE: Generate all /24 figures in memory
            log.info("Generating /24 views for consolidated HTML...")
            list_of_24_views = []

            for (bx, by), sub in buckets_24.groupby(["bucket16_x", "bucket16_y"]):
                # Skip this /16 block if it has no data in the /16 view
                if (int(bx), int(by)) not in blocks_with_data:
                    log.debug(f"Skipping /24 view for {bx}.{by}.0.0/16 (no data in /16 view)")
                    continue

                # build /24 figure for this /16
                fig24 = build_24_heatmap(
                    sub,
                    mode=mode,
                    colorscale_mode=colorscale_mode,
                    title=f"/24s under {bx}.{by}.0.0/16",
                    parent_label=f"{bx}.{by}.0.0/16",
                )
                list_of_24_views.append({
                    'bx': bx,
                    'by': by,
                    'figure': fig24,
                    'parent_cidr': f"{bx}.{by}.0.0/16",
                })

            # Save consolidated HTML
            save_html_consolidated(
                fig_16=fig,
                views_24=list_of_24_views,
                output_path=output,
                mode=mode,
                colorscale_mode=colorscale_mode,
            )
            typer.echo(f"Wrote consolidated nested visualization to {output}")
        else:
            # 2b) FRAMES MODE: Generate individual /24 HTMLs in frames/ directory
            frames_dir = output.parent / "frames"
            frames_dir.mkdir(parents=True, exist_ok=True)
            log.info(f"Generating individual /24 frames in {frames_dir}...")

            # Extract base name for frame files (use output stem, e.g. "dss" from "dss.html")
            nested_basename = output.stem

            # Save the main /16 view with nested navigation (clickable cells)
            save_html_nested_16(
                fig,
                output,
                nested_basename="frame",
                frames_dir="frames",
            )

            # Generate and save each /24 view individually
            count = 0
            for (bx, by), sub in buckets_24.groupby(["bucket16_x", "bucket16_y"]):
                # Skip this /16 block if it has no data in the /16 view
                if (int(bx), int(by)) not in blocks_with_data:
                    continue

                # build /24 figure for this /16
                fig24 = build_24_heatmap(
                    sub,
                    mode=mode,
                    colorscale_mode=colorscale_mode,
                    title=f"/24s under {bx}.{by}.0.0/16",
                    parent_label=f"{bx}.{by}.0.0/16",
                )

                # Save to frames directory with naming that matches nested_16 expectations
                frame_path = frames_dir / f"frame_{bx}_{by}.html"
                save_html_with_backlink_and_whois(
                    fig24,
                    frame_path,
                    back_href=f"../{output.name}",
                    parent_cidr=f"{bx}.{by}.0.0/16",
                    update_panel_on_click=True,
                )
                count += 1

            typer.echo(f"Wrote /16 view to {output}")
            typer.echo(f"Wrote {count} /24 frames to {frames_dir}/")

        return


def main() -> None:
    """Entry point for console_scripts."""
    try:
        app()
    except KeyboardInterrupt:
        # Graceful Ctrl+C handling
        typer.echo("Interrupted by user.", err=True)
        sys.exit(130)


if __name__ == "__main__":
    main()
