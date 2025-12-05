# ipmap/viz/export.py

from __future__ import annotations

from pathlib import Path
from typing import Union

import plotly.io as pio
from plotly.graph_objs import Figure

from ipmap.utils.logging import get_logger

log = get_logger(__name__)


PathLike = Union[str, Path]


def save_html(fig: Figure, path: PathLike, include_plotlyjs: str = "cdn") -> None:
    """
    Save a Plotly figure as a self-contained HTML file.

    Parameters
    ----------
    fig : plotly.graph_objs.Figure
        The figure to save.
    path : str | Path
        Output path for the HTML file.
    include_plotlyjs : {"cdn", "directory", "inline"}, default "cdn"
        Passed to plotly.io.write_html.
    """
    out_path = Path(path)
    log.info("Saving HTML visualization to %s", out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    pio.write_html(fig, file=str(out_path), include_plotlyjs=include_plotlyjs)
    log.debug("HTML written successfully to %s", out_path)


def save_png(
        fig: Figure,
        path: PathLike,
        scale: float = 2.0,
        width: int | None = None,
        height: int | None = None,
) -> None:
    """
    Save a Plotly figure as a PNG (requires kaleido).

    Parameters
    ----------
    fig : plotly.graph_objs.Figure
        The figure to save.
    path : str | Path
        Output path for the PNG file.
    scale : float, default 2.0
        Scale factor passed to plotly.io.write_image.
    width : int | None
        Explicit width in pixels (optional).
    height : int | None
        Explicit height in pixels (optional).
    """
    out_path = Path(path)
    log.info("Saving PNG visualization to %s", out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        pio.write_image(
            fig,
            file=str(out_path),
            scale=scale,
            width=width,
            height=height,
        )
    except Exception as e:
        log.error(
            "Failed to write PNG to %s; ensure 'kaleido' is installed. Error: %s",
            out_path,
            e,
        )
        raise
    else:
        log.debug("PNG written successfully to %s", out_path)
