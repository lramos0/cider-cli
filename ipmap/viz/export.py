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


def save_html_nested_16(
        fig: Figure,
        path: PathLike,
        nested_basename: str,
        include_plotlyjs: str = "cdn",
        div_id: str = "ipmap_figure",
) -> None:
    """
    Save the top-level /16 figure as HTML and inject JS that:
      - listens for plotly_click
      - redirects to <nested_basename>_16_<bucket_x>_<bucket_y>.html
    """
    out_path = Path(path)
    log.info("Saving nested /16 HTML visualization to %s", out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    post_script = f"""
document.addEventListener("DOMContentLoaded", function() {{
  var gd = document.getElementById("{div_id}");
  if (!gd || !gd.addEventListener) return;

  gd.on('plotly_click', function(evt) {{
    if (!evt || !evt.points || !evt.points.length) return;
    var p = evt.points[0];
    var x = p.x;
    var y = p.y;
    if (x === undefined || y === undefined) return;
    var url = "{nested_basename}_16_" + x + "_" + y + ".html";
    window.location.href = url;
  }});
}});
"""

    html = pio.to_html(
        fig,
        include_plotlyjs=include_plotlyjs,
        full_html=True,
        div_id=div_id,
        post_script=post_script,
    )

    out_path.write_text(html, encoding="utf-8")
    log.debug("Nested /16 HTML written successfully to %s", out_path)

def save_html_with_backlink(
        fig: Figure,
        path: PathLike,
        back_href: str,
        include_plotlyjs: str = "cdn",
        div_id: str = "ipmap_figure",
) -> None:
    """
    Save a figure as HTML with a simple "Back to /16 view" link at the top.
    """
    out_path = Path(path)
    log.info("Saving nested /24 HTML visualization to %s", out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # We want just the div for the figure, no full HTML wrapper.
    fig_html = pio.to_html(
        fig,
        include_plotlyjs=False,
        full_html=False,
        div_id=div_id,
    )

    html = f"""
        <!DOCTYPE html>
        <html>
          <head>
            <meta charset="utf-8" />
            <title>{fig.layout.title.text if fig.layout.title else "IPv4 /24 view"}</title>
            <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
            <style>
              body {{
                margin: 0;
                background: #111111;
                color: #EEEEEE;
                font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
              }}
              .toolbar {{
                padding: 8px 12px;
                border-bottom: 1px solid #333;
                background: #181818;
              }}
              .toolbar a {{
                color: #4ab3ff;
                text-decoration: none;
                font-size: 14px;
              }}
              .toolbar a:hover {{
                text-decoration: underline;
              }}
            </style>
          </head>
          <body>
            <div class="toolbar">
              <a href="{back_href}">&larr; Back to /16 view</a>
            </div>
            {fig_html}
          </body>
        </html>
        """

    out_path.write_text(html, encoding="utf-8")
    log.debug("Nested /24 HTML written successfully to %s", out_path)
