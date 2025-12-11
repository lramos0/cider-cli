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
from ipmap.viz.export import save_html, save_png
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
            # Optionally override org_col here if you want by default:
            # org_col="region",
        )
    else:
        # typer should prevent this, but just in case:
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
        from ipmap.viz.export import save_html, save_html_nested_16, save_html_with_backlink

        fig = build_16_heatmap(
            buckets_16,
            mode=mode,
            colorscale_mode=colorscale_mode,
            title=f"IPv4 /16 Address Space – {kind} (view={view})",
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
            # old behaviour
            if output.suffix.lower() not in (".html", ".htm"):
                output = output.with_suffix(".html")
            save_html(fig, output)
            typer.echo(f"Wrote visualization to {output}")
            return

        # --- NESTED MODE ---
        # 1) save top-level /16 HTML with click handler
        if output.suffix.lower() not in (".html", ".htm"):
            output = output.with_suffix(".html")

        save_html_nested_16(
            fig,
            output,
            nested_basename=output.stem,
        )

        # 2) generate one /24 HTML per populated /16
        if buckets_24 is not None and not buckets_24.empty:
            for (bx, by), sub in buckets_24.groupby(["bucket16_x", "bucket16_y"]):
                # build /24 figure for this /16
                fig24 = build_24_heatmap(
                    sub,
                    mode=mode,
                    colorscale_mode=colorscale_mode,
                    title=f"/24s under {bx}.{by}.0.0/16",
                    parent_label=f"{bx}.{by}.0.0/16",
                )
                out_24 = output.with_name(f"{output.stem}_16_{bx}_{by}.html")
                # include backlink to main /16 file (relative)
                save_html_with_backlink(
                    fig24,
                    out_24,
                    back_href=output.name,
                )

        typer.echo(f"Wrote nested /16 + /24 visualizations to {output}")
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
