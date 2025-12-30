# ipmap/viz/export.py

from __future__ import annotations
import gzip
import json
from pathlib import Path
from typing import Union

import plotly.io as pio
from plotly.graph_objs import Figure

from ipmap.utils.logging import get_logger

log = get_logger(__name__)


PathLike = Union[str, Path]


def _compress_button_data(button_data: dict | None) -> str:
    """
    Convert button data to minified JSON string for embedding in HTML.

    This reduces file size by:
    - Using compact JSON formatting (no whitespace)
    - Rounding numeric values to reduce precision
    """
    if button_data is None:
        return "null"

    # Create a copy to avoid modifying the original
    compressed = {}

    for key, value in button_data.items():
        if key in ("z_primary", "z_country", "z_records"):
            # Round numeric arrays to 2 decimal places (or None)
            if isinstance(value, list):
                compressed[key] = [
                    [round(v, 2) if isinstance(v, (int, float)) and v is not None else v
                     for v in row]
                    for row in value
                ]
            else:
                compressed[key] = value
        else:
            compressed[key] = value

    # Use compact JSON encoding (no spaces)
    return json.dumps(compressed, separators=(',', ':'))


def _write_html_with_compression(
    html: str,
    path: Path,
    compress: bool = True
) -> tuple[int, int]:
    """
    Write HTML to file, optionally with gzip compression.

    Returns:
        tuple of (original_size_bytes, written_size_bytes)
    """
    html_bytes = html.encode("utf-8")
    original_size = len(html_bytes)

    if compress:
        # Write gzipped version
        gz_path = path.with_suffix(path.suffix + ".gz")
        with gzip.open(gz_path, "wb", compresslevel=9) as f:
            f.write(html_bytes)
        compressed_size = gz_path.stat().st_size

        # Also write uncompressed for compatibility
        path.write_bytes(html_bytes)

        log.info(
            f"Wrote {path} ({original_size / 1024 / 1024:.1f} MB) and "
            f"{gz_path.name} ({compressed_size / 1024 / 1024:.1f} MB, "
            f"{100 * (1 - compressed_size / original_size):.1f}% smaller)"
        )
        return original_size, compressed_size
    else:
        path.write_bytes(html_bytes)
        log.info(f"Wrote {path} ({original_size / 1024 / 1024:.1f} MB)")
        return original_size, original_size


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


def save_html_with_whois_on_click(
        fig: Figure,
        path: PathLike,
        include_plotlyjs: str = "cdn",
        div_id: str = "ipmap_figure",
        provider: str = "rdap_org",
) -> None:
    """
    Save Plotly HTML and inject JS so clicking a cell opens a WHOIS/RDAP lookup
    for the clicked /16. Also includes custom HTML buttons for mode/colorscale switching.

    provider:
      - "rdap_org": https://rdap.org/ip/<ip>   (best generic RDAP aggregator)
      - "arin":     https://rdap.arin.net/registry/ip/<ip> (ARIN-only coverage)
    """
    out_path = Path(path)
    log.info("Saving HTML visualization (with whois-on-click) to %s", out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if provider == "arin":
        base = "https://rdap.arin.net/registry/ip/"
    else:
        base = "https://rdap.org/ip/"

    # Extract button data if available (use compressed format)
    button_data = getattr(fig, '_button_data', None)
    button_data_json = _compress_button_data(button_data)

    # Generate the initial HTML with plotly
    html_content = pio.to_html(
        fig,
        include_plotlyjs=include_plotlyjs,
        full_html=False,
        div_id=div_id,
        config={"responsive": True},
    )

    # Build complete HTML with custom button toolbar
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>IPv4 /16 Address Space Visualization</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        body {{
            margin: 0;
            padding: 0;
            background: #111111;
            color: #EEEEEE;
            font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            overflow: hidden;
        }}
        
        #ipmap_figure, svg, rect.draglayer.cursor-crosshair, main-svg {{
          min-width: 95vw;
          max-width: 95vw;
          max-height: 95vw;
        }}

        .toolbar {{
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            height: 50px;
            background: #1a1a1a;
            border-bottom: 1px solid #333;
            display: flex;
            align-items: center;
            padding: 0 16px;
            gap: 12px;
            z-index: 1000;
            box-shadow: 0 2px 8px rgba(0,0,0,0.3);
        }}

        .button-group {{
            display: flex;
            gap: 8px;
            align-items: center;
        }}

        .button-group-label {{
            font-size: 12px;
            color: #999;
            margin-right: 4px;
        }}

        .toolbar button {{
            background: rgba(255,255,255,0.08);
            border: 1px solid rgba(255,255,255,0.15);
            color: #ddd;
            padding: 6px 12px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 12px;
            transition: all 0.2s;
        }}

        .toolbar button:hover {{
            background: rgba(255,255,255,0.12);
            border-color: rgba(255,255,255,0.25);
        }}

        .toolbar button.active {{
            background: rgba(74, 179, 255, 0.2);
            border-color: rgba(74, 179, 255, 0.5);
            color: #4ab3ff;
        }}

        .divider {{
            width: 1px;
            height: 24px;
            background: rgba(255,255,255,0.15);
        }}

        #content {{
            position: fixed;
            top: 10px;
            left: 0;
            right: 0;
            bottom: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
            box-sizing: border-box;
        }}

        #{div_id} {{
            width: 100% !important;
            height: 100% !important;
            max-width: min(100%, 100vh);
            max-height: min(100%, 100vw);
            aspect-ratio: 5 / 3;
        }}

        .toast {{
            position: fixed;
            left: 16px;
            bottom: 16px;
            padding: 10px 14px;
            background: rgba(20,20,20,0.9);
            border: 1px solid rgba(255,255,255,0.2);
            border-radius: 8px;
            color: #eee;
            font-size: 13px;
            z-index: 9999;
            animation: fadeIn 0.2s;
        }}

        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(10px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
    </style>
</head>
<body>
    <div class="toolbar">
        <div class="button-group">
            <span class="button-group-label">Mode:</span>
            <button id="btn-primary" class="mode-btn active" data-mode="primary">col</button>
            <button id="btn-country" class="mode-btn" data-mode="country_count">COUNT(DISTINCT(col))</button>
            <button id="btn-records" class="mode-btn" data-mode="record_count">COUNT(col)</button>
        </div>

        <div class="divider"></div>

        <div class="button-group">
            <span class="button-group-label">Colors:</span>
            <button id="btn-default" class="color-btn active" data-colorscheme="default">Default</button>
            <button id="btn-neon" class="color-btn" data-colorscheme="neon">Neon</button>
        </div>

        <div class="divider"></div>

        <div class="button-group">
            <button id="btn-overlays" class="overlay-btn active" data-enabled="true">Overlays</button>
        </div>
    </div>

    <div id="content">
        {html_content}
    </div>

    <script>
    (function() {{
        var buttonData = {button_data_json};
        var gd = document.getElementById("{div_id}");
        var currentMode = "primary";
        var currentColorscheme = "default";
        var overlaysEnabled = true;

        // Store original overlays (shapes and annotations)
        var originalShapes = buttonData && buttonData.overlay_shapes ? buttonData.overlay_shapes : [];
        var originalAnnotations = buttonData && buttonData.overlay_annotations ? buttonData.overlay_annotations : [];

        // Toast notification
        function toast(msg) {{
            var t = document.createElement("div");
            t.className = "toast";
            t.textContent = msg;
            document.body.appendChild(t);
            setTimeout(function() {{
                if (t && t.parentNode) t.parentNode.removeChild(t);
            }}, 1800);
        }}

        // Update button active states
        function updateButtonStates() {{
            document.querySelectorAll('.mode-btn').forEach(function(btn) {{
                btn.classList.toggle('active', btn.dataset.mode === currentMode);
            }});
            document.querySelectorAll('.color-btn').forEach(function(btn) {{
                btn.classList.toggle('active', btn.dataset.colorscheme === currentColorscheme);
            }});
            document.querySelectorAll('.overlay-btn').forEach(function(btn) {{
                btn.classList.toggle('active', overlaysEnabled);
            }});
        }}

        // Mode switching
        function switchMode(mode) {{
            if (!buttonData || !gd) return;
            currentMode = mode;

            var update = {{}};

            if (mode === "primary") {{
                update.z = [buttonData.z_primary];
                update.colorscale = [currentColorscheme === "neon" ?
                    buttonData.primary_colorscale_neon :
                    buttonData.primary_colorscale_default];
                update.zmin = [0];
                update.zmax = [Math.max(
                    buttonData.org_code_map ? Math.max(...Object.values(buttonData.org_code_map)) : 0,
                    1
                )];
                update.hovertemplate = [buttonData.hover_primary];
                update['colorbar.title'] = ["Org index"];
            }} else if (mode === "country_count") {{
                update.z = [buttonData.z_country];
                update.colorscale = [[[0.0, "#f7fbff"], [0.29, "#f7fbff"], [0.30, "#6baed6"], [0.50, "#6baed6"], [0.51, "#b30000"], [1.0, "#b30000"]]];
                update.zmin = [0];
                update.zmax = [Math.max(Math.min(buttonData.max_country, 10), 1)];
                update.hovertemplate = [buttonData.hover_country];
                update['colorbar.title'] = ["# orgs"];
            }} else if (mode === "record_count") {{
                update.z = [buttonData.z_records];
                update.colorscale = [[[0.0, "#f7fbff"], [0.29, "#f7fbff"], [0.30, "#6baed6"], [0.50, "#6baed6"], [0.51, "#b30000"], [1.0, "#b30000"]]];
                update.zmin = [0];
                update.zmax = [Math.max(buttonData.max_records, 1)];
                update.hovertemplate = [buttonData.hover_records];
                update['colorbar.title'] = ["# prefixes"];
            }}

            Plotly.update(gd, update, {{}});
            updateButtonStates();
        }}

        // Colorscheme switching
        function switchColorscheme(scheme) {{
            if (!buttonData || !gd || currentMode !== "primary") return;
            currentColorscheme = scheme;

            var colorscale = scheme === "neon" ?
                buttonData.primary_colorscale_neon :
                buttonData.primary_colorscale_default;

            Plotly.restyle(gd, {{ colorscale: [colorscale] }});
            updateButtonStates();
        }}

        // Overlay toggling
        function toggleOverlays() {{
            if (!gd) return;
            overlaysEnabled = !overlaysEnabled;

            var layoutUpdate = {{}};
            if (overlaysEnabled) {{
                // Show overlays
                layoutUpdate.shapes = originalShapes;
                layoutUpdate.annotations = originalAnnotations;
            }} else {{
                // Hide overlays
                layoutUpdate.shapes = [];
                layoutUpdate.annotations = [];
            }}

            Plotly.relayout(gd, layoutUpdate);
            updateButtonStates();
        }}

        // Setup event listeners
        document.addEventListener("DOMContentLoaded", function() {{
            // Mode buttons
            document.querySelectorAll('.mode-btn').forEach(function(btn) {{
                btn.addEventListener('click', function() {{
                    switchMode(this.dataset.mode);
                }});
            }});

            // Color buttons
            document.querySelectorAll('.color-btn').forEach(function(btn) {{
                btn.addEventListener('click', function() {{
                    switchColorscheme(this.dataset.colorscheme);
                }});
            }});

            // Overlay button
            document.querySelectorAll('.overlay-btn').forEach(function(btn) {{
                btn.addEventListener('click', function() {{
                    toggleOverlays();
                }});
            }});

            // WHOIS click handler
            if (gd && gd.on) {{
                gd.on("plotly_click", function(evt) {{
                    if (!evt || !evt.points || !evt.points.length) return;
                    var p = evt.points[0];
                    var x = p.x;
                    var y = p.y;

                    if (x === undefined || y === undefined) return;

                    var ip = x + "." + y + ".0.0";
                    var cidr = ip + "/16";
                    var url = "{base}" + encodeURIComponent(ip);

                    toast("Opening WHOIS/RDAP for " + cidr);
                    window.open(url, "_blank", "noopener,noreferrer");
                }});
            }}

            // Handle window resize
            window.addEventListener("resize", function() {{
                if (gd && window.Plotly) {{
                    Plotly.Plots.resize(gd);
                }}
            }});

            // Initial resize to ensure proper sizing
            setTimeout(function() {{
                if (gd && window.Plotly) {{
                    Plotly.Plots.resize(gd);
                }}
            }}, 100);
        }});
    }})();
    </script>
</body>
</html>"""

    # Write HTML with optional compression
    original_size, final_size = _write_html_with_compression(html, out_path, compress=True)
    log.debug("HTML (with whois-on-click and custom buttons) written successfully to %s", out_path)

    # Check file size and warn if over 100MB
    file_size_mb = final_size / (1024 * 1024)
    if file_size_mb > 100:
        log.warning(
            f"Compressed file size is {file_size_mb:.1f} MB, which exceeds 100 MB. "
            f"Consider using the .html.gz file for hosting (serves with Content-Encoding: gzip)."
        )
    elif original_size / (1024 * 1024) > 100:
        log.info(
            f"Original file was {original_size / (1024 * 1024):.1f} MB. "
            f"Use the .html.gz file for better hosting performance."
        )

def save_html_with_backlink_and_whois(
        fig: Figure,
        path: PathLike,
        back_href: str,
        include_plotlyjs: str = "cdn",
        div_id: str = "ipmap_figure",
        whois_provider: str = "rdap_org",
        # NEW: parent /16 (e.g. "113.52.0.0/16")
        parent_cidr: str | None = None,
        # NEW: if True, clicking /24 shows /24 RDAP; if False, panel stays on /16
        update_panel_on_click: bool = True,
) -> None:
    """
    Save a /24 figure as HTML with an "inside view":
      - left: Plotly 16x16 grid
      - right: RDAP JSON panel (defaults to parent /16)
      - an arrow pointing from grid -> panel
      - click /24 cell optionally updates the panel
    """
    out_path = Path(path)
    log.info("Saving nested /24 HTML (inside view) to %s", out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Base RDAP URL
    if whois_provider == "arin":
        base = "https://rdap.arin.net/registry/ip/"
    else:
        base = "https://rdap.org/ip/"

    # Extract button data if available (use compressed format)
    button_data = getattr(fig, '_button_data', None)
    button_data_json = _compress_button_data(button_data)

    # Ensure div id is stable so CSS works
    fig_html = pio.to_html(
        fig,
        include_plotlyjs=False,
        full_html=False,
        div_id=div_id,
        config={"responsive": True},
    )

    # Try to infer parent /16 from parent_cidr or from title text
    parent_ip = None
    parent_display = None
    if parent_cidr:
        parent_display = parent_cidr
        # "a.b.0.0/16" -> "a.b.0.0"
        parent_ip = parent_cidr.split("/")[0].strip()
    else:
        # fallback: if caller didn’t pass parent_cidr, the panel will stay empty until click
        parent_display = "parent /16"
        parent_ip = ""

    html = f"""<!DOCTYPE html>
        <html>
          <head>
            <meta charset="utf-8" />
            <title>{fig.layout.title.text if fig.layout.title else "IPv4 /24 inside view"}</title>
            <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
            <style>
                body {{
                    margin: 0;
                    padding: 0;
                    background: #111111;
                    color: #EEEEEE;
                    font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
                    overflow: hidden;
                }}
        
                .toolbar {{
                    position: fixed;
                    top: 0;
                    left: 0;
                    right: 0;
                    height: 50px;
                    background: #1a1a1a;
                    border-bottom: 1px solid #333;
                    display: flex;
                    align-items: center;
                    padding: 0 16px;
                    gap: 12px;
                    z-index: 1000;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.3);
                }}
        
                .button-group {{
                    display: flex;
                    gap: 8px;
                    align-items: center;
                }}
        
                .button-group-label {{
                    font-size: 12px;
                    color: #999;
                    margin-right: 4px;
                }}
        
                .toolbar button {{
                    background: rgba(255,255,255,0.08);
                    border: 1px solid rgba(255,255,255,0.15);
                    color: #ddd;
                    padding: 6px 12px;
                    border-radius: 6px;
                    cursor: pointer;
                    font-size: 12px;
                    transition: all 0.2s;
                }}
        
                .toolbar button:hover {{
                    background: rgba(255,255,255,0.12);
                    border-color: rgba(255,255,255,0.25);
                }}
        
                .toolbar button.active {{
                    background: rgba(74, 179, 255, 0.2);
                    border-color: rgba(74, 179, 255, 0.5);
                    color: #4ab3ff;
                }}
        
                .divider {{
                    width: 1px;
                    height: 24px;
                    background: rgba(255,255,255,0.15);
                }}
                /* Inside-view layout */
              .wrap {{
                position: relative;
                height: calc(20vh);
                display: flex;
                gap: 14px;
                padding: 12px;
                box-sizing: border-box;
              }}
        
              .left {{
                flex: 1 1 auto;
                min-width: 650px;
                min-height: 650px;
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 14px;
                background: rgba(255,255,255,0.02);
                overflow: hidden;
                position: relative;
              }}

              /* Force Plotly to fill the left panel */
              #{div_id} {{
                width: 100% !important;
                height: 100% !important;
              }}
        
              .right {{
                min-width: 520px;
                min-height: 520px;
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 14px;
                background: rgba(255,255,255,0.02);
                overflow: hidden;
                display: flex;
                flex-direction: column;
              }}
        
              .panelHeader {{
                padding: 10px 12px;
                border-bottom: 1px solid rgba(255,255,255,0.08);
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 10px;
              }}
              .panelHeader .title {{
                font-size: 13px;
                color: #eaeaea;
                font-weight: 600;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
              }}
              .panelHeader .sub {{
                font-size: 11px;
                color: #a9a9a9;
              }}
              .panelHeader button {{
                background: rgba(255,255,255,0.06);
                border: 1px solid rgba(255,255,255,0.12);
                color: #eee;
                padding: 6px 10px;
                border-radius: 10px;
                cursor: pointer;
                font-size: 12px;
              }}
              .panelHeader button:hover {{
                background: rgba(255,255,255,0.10);
              }}
        
              .panelBody {{
                padding: 5px 6px;
                overflow: auto;
                font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
                font-size: 12px;
                line-height: 1.35;
                white-space: pre;
              }}
        
              /* Arrow overlay */
              svg#arrowLayer {{
                position: absolute;
                inset: 0;
                pointer-events: none;
              }}
              #content {{
                    position: fixed;
                    top: 10px;
                    left: 0;
                    right: 0;
                    bottom: 0;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    padding: 20px;
                    box-sizing: border-box;
              }}
        
              #{div_id} {{
                    width: 100% !important;
                    height: 100% !important;
                    max-width: min(100%, 100vh);
                    max-height: min(100%, 100vw);
                    aspect-ratio: 5 / 3;
              }}
        
              .toast {{
                    position: fixed;
                    left: 16px;
                    bottom: 16px;
                    padding: 10px 14px;
                    background: rgba(20,20,20,0.9);
                    border: 1px solid rgba(255,255,255,0.2);
                    border-radius: 8px;
                    color: #eee;
                    font-size: 13px;
                    z-index: 9999;
                    animation: fadeIn 0.2s;
              }}
        
              @keyframes fadeIn {{
                from {{ opacity: 0; transform: translateY(10px); }}
                to {{ opacity: 1; transform: translateY(0); }}
              }}
            </style>
          </head>
          <body>
            <div class="toolbar">
              <a href="{back_href}">&larr; Back to /16 view</a>

              <div class="divider"></div>

              <div class="button-group">
                <span class="button-group-label">Mode:</span>
                <button id="btn-primary" class="mode-btn active" data-mode="primary">col</button>
                <button id="btn-country" class="mode-btn" data-mode="country_count">COUNT(DISTINCT(col))</button>
                <button id="btn-records" class="mode-btn" data-mode="record_count">COUNT(col)</button>
              </div>

              <div class="divider"></div>

              <div class="button-group">
                <span class="button-group-label">Colors:</span>
                <button id="btn-default" class="color-btn active" data-colorscheme="default">Default</button>
                <button id="btn-neon" class="color-btn" data-colorscheme="neon">Neon</button>
              </div>

              <span class="hint" style="margin-left: auto;">Click a cell to {( "update the panel" if update_panel_on_click else "open RDAP in a new tab" )}.</span>
            </div>
        
            <div class="wrap" id="wrap">
              <svg id="arrowLayer"></svg>
        
              <div class="left" id="leftPanel">
                {fig_html}
              </div>
        
              <div class="right" id="rightPanel">
                <div class="panelHeader">
                  <div>
                    <div class="title" id="whoisTitle">RDAP: {parent_display}</div>
                    <div class="sub" id="whoisSub">Source: {base}</div>
                  </div>
                  <button id="openBtn" title="Open RDAP in a new tab">Open</button>
                </div>
                <div class="panelBody" id="whoisBody">Loading…</div>
              </div>
            </div>
        
            <script>
            (function() {{
              var BASE = {json.dumps(base)};
              var parentIp = {json.dumps(parent_ip)};
              var updateOnClick = {str(bool(update_panel_on_click)).lower()};
              var buttonData = {button_data_json};
              var gd = document.getElementById({json.dumps(div_id)});
              var currentMode = "primary";
              var currentColorscheme = "default";

              function pretty(obj) {{
                try {{ return JSON.stringify(obj, null, 2); }} catch (e) {{ return String(obj); }}
              }}

              // Update button active states
              function updateButtonStates() {{
                document.querySelectorAll('.mode-btn').forEach(function(btn) {{
                  btn.classList.toggle('active', btn.dataset.mode === currentMode);
                }});
                document.querySelectorAll('.color-btn').forEach(function(btn) {{
                  btn.classList.toggle('active', btn.dataset.colorscheme === currentColorscheme);
                }});
              }}

              // Mode switching
              function switchMode(mode) {{
                if (!buttonData || !gd) return;
                currentMode = mode;

                var update = {{}};

                if (mode === "primary") {{
                  update.z = [buttonData.z_primary];
                  update.colorscale = [currentColorscheme === "neon" ?
                      buttonData.primary_colorscale_neon :
                      buttonData.primary_colorscale_default];
                  update.zmin = [0];
                  update.zmax = [Math.max(
                      buttonData.org_code_map ? Math.max(...Object.values(buttonData.org_code_map)) : 0,
                      1
                  )];
                  update.hovertemplate = [buttonData.hover_primary];
                  update['colorbar.title'] = ["Org index"];
                }} else if (mode === "country_count") {{
                  update.z = [buttonData.z_country];
                  update.colorscale = [[[0.0, "#f7fbff"], [0.29, "#f7fbff"], [0.30, "#6baed6"], [0.50, "#6baed6"], [0.51, "#b30000"], [1.0, "#b30000"]]];
                  update.zmin = [0];
                  update.zmax = [Math.max(Math.min(buttonData.max_country, 10), 1)];
                  update.hovertemplate = [buttonData.hover_country];
                  update['colorbar.title'] = ["# orgs"];
                }} else if (mode === "record_count") {{
                  update.z = [buttonData.z_records];
                  update.colorscale = [[[0.0, "#f7fbff"], [0.29, "#f7fbff"], [0.30, "#6baed6"], [0.50, "#6baed6"], [0.51, "#b30000"], [1.0, "#b30000"]]];
                  update.zmin = [0];
                  update.zmax = [Math.max(buttonData.max_records, 1)];
                  update.hovertemplate = [buttonData.hover_records];
                  update['colorbar.title'] = ["# prefixes"];
                }}

                Plotly.update(gd, update, {{}});
                updateButtonStates();
              }}

              // Colorscheme switching
              function switchColorscheme(scheme) {{
                if (!buttonData || !gd || currentMode !== "primary") return;
                currentColorscheme = scheme;

                var colorscale = scheme === "neon" ?
                    buttonData.primary_colorscale_neon :
                    buttonData.primary_colorscale_default;

                Plotly.restyle(gd, {{ colorscale: [colorscale] }});
                updateButtonStates();
              }}
        
              function setPanel(targetIp, label) {{
                var titleEl = document.getElementById("whoisTitle");
                var bodyEl = document.getElementById("whoisBody");
                var openBtn = document.getElementById("openBtn");
        
                var url = BASE + encodeURIComponent(targetIp || "");
                titleEl.textContent = "RDAP: " + (label || targetIp || "(none)");
                openBtn.onclick = function() {{
                  if (!targetIp) return;
                  window.open(url, "_blank", "noopener,noreferrer");
                }};
        
                if (!targetIp) {{
                  bodyEl.textContent = "No IP selected (click a cell).";
                  return;
                }}
        
                bodyEl.textContent = "Loading " + url + " …";
        
                // NOTE: RDAP endpoints usually return JSON. If CORS blocks fetch in your env,
                // we’ll show a friendly message and the user can use the Open button.
                fetch(url, {{ method: "GET" }})
                  .then(function(r) {{
                    if (!r.ok) throw new Error("HTTP " + r.status);
                    return r.json();
                  }})
                  .then(function(j) {{
                    bodyEl.textContent = pretty(j);
                  }})
                  .catch(function(err) {{
                    bodyEl.textContent =
                      "Could not fetch RDAP JSON from the browser (often CORS).\\n\\n" +
                      "Error: " + String(err) + "\\n\\n" +
                      "Use the 'Open' button to view RDAP in a new tab:\\n" + url;
                  }});
              }}
        
              function drawArrow() {{
                var wrap = document.getElementById("wrap");
                var left = document.getElementById("leftPanel");
                var right = document.getElementById("rightPanel");
                var svg = document.getElementById("arrowLayer");
                if (!wrap || !left || !right || !svg) return;
        
                var wRect = wrap.getBoundingClientRect();
                var lRect = left.getBoundingClientRect();
                var rRect = right.getBoundingClientRect();
        
                // Start near right edge center of left panel
                var x1 = (lRect.right - wRect.left) - 10;
                var y1 = (lRect.top - wRect.top) + (lRect.height * 0.35);
        
                // End near left edge upper area of right panel
                var x2 = (rRect.left - wRect.left) + 10;
                var y2 = (rRect.top - wRect.top) + 34;
        
                svg.setAttribute("width", wRect.width);
                svg.setAttribute("height", wRect.height);
                svg.innerHTML = "";
        
                var defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
                var marker = document.createElementNS("http://www.w3.org/2000/svg", "marker");
                marker.setAttribute("id", "arrowHead");
                marker.setAttribute("markerWidth", "10");
                marker.setAttribute("markerHeight", "10");
                marker.setAttribute("refX", "9");
                marker.setAttribute("refY", "3");
                marker.setAttribute("orient", "auto");
                var path = document.createElementNS("http://www.w3.org/2000/svg", "path");
                path.setAttribute("d", "M0,0 L10,3 L0,6 Z");
                path.setAttribute("fill", "rgba(255,255,255,0.45)");
                marker.appendChild(path);
                defs.appendChild(marker);
                svg.appendChild(defs);
        
                var line = document.createElementNS("http://www.w3.org/2000/svg", "path");
                var cx = (x1 + x2) / 2;
                // a slight curve
                var d = "M " + x1 + " " + y1 + " C " + (cx) + " " + y1 + ", " + (cx) + " " + y2 + ", " + x2 + " " + y2;
                line.setAttribute("d", d);
                line.setAttribute("fill", "none");
                line.setAttribute("stroke", "rgba(255,255,255,0.35)");
                line.setAttribute("stroke-width", "2");
                line.setAttribute("marker-end", "url(#arrowHead)");
                svg.appendChild(line);
              }}
        
              document.addEventListener("DOMContentLoaded", function() {{
                // Force Plotly to fill the left panel
                if (window.Plotly && gd) {{
                  setTimeout(function() {{ Plotly.Plots.resize(gd); drawArrow(); }}, 0);
                }} else {{
                  drawArrow();
                }}

                // Mode buttons
                document.querySelectorAll('.mode-btn').forEach(function(btn) {{
                  btn.addEventListener('click', function() {{
                    switchMode(this.dataset.mode);
                  }});
                }});

                // Color buttons
                document.querySelectorAll('.color-btn').forEach(function(btn) {{
                  btn.addEventListener('click', function() {{
                    switchColorscheme(this.dataset.colorscheme);
                  }});
                }});

                // Initial panel: parent /16 if provided
                if (parentIp) {{
                  setPanel(parentIp, {json.dumps(parent_display)});
                }} else {{
                  setPanel("", "");
                }}

                window.addEventListener("resize", function() {{
                  if (window.Plotly && gd) Plotly.Plots.resize(gd);
                  drawArrow();
                }});

                // Clicking a /24 cell:
                if (gd && gd.on) {{
                  gd.on("plotly_click", function(evt) {{
                    if (!evt || !evt.points || !evt.points.length) return;
                    var p = evt.points[0];
                    var label = (p.text !== undefined && p.text !== null) ? String(p.text) : "";
                    if (!label || label.indexOf(".") === -1) return;

                    // label is "a.b.c" from your text_grid
                    var ip24 = label + ".0";
                    var cidr24 = ip24 + "/24";

                    if (updateOnClick) {{
                      setPanel(ip24, cidr24);
                    }} else {{
                      window.open(BASE + encodeURIComponent(ip24), "_blank", "noopener,noreferrer");
                    }}
                  }});
                }}
              }});
            }})();
            </script>
          </body>
        </html>
    """
    # Write HTML with compression
    _write_html_with_compression(html, out_path, compress=True)
    log.debug("Nested /24 HTML (inside view) written successfully to %s", out_path)



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
        frames_dir: str = "frames",
) -> None:
    """
    Save the top-level /16 figure as HTML with custom buttons and inject JS that:
      - listens for plotly_click
      - redirects to <frames_dir>/<nested_basename>_<bucket_x>_<bucket_y>.html

    Parameters
    ----------
    frames_dir : str
        Subdirectory name where frame files are stored (default: "frames")
    """
    out_path = Path(path)
    log.info("Saving nested /16 HTML visualization to %s", out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Extract button data if available (use compressed format)
    button_data = getattr(fig, '_button_data', None)
    button_data_json = _compress_button_data(button_data)

    # Generate the initial HTML with plotly
    html_content = pio.to_html(
        fig,
        include_plotlyjs=include_plotlyjs,
        full_html=False,
        div_id=div_id,
        config={"responsive": True},
    )

    # Build complete HTML with custom button toolbar
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>IPv4 /16 Address Space Visualization</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        body {{
            margin: 0;
            padding: 0;
            background: #111111;
            color: #EEEEEE;
            font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            overflow: hidden;
        }}

        #ipmap_figure, svg, rect.draglayer.cursor-crosshair, main-svg {{
            min-width: 95vw;
            max-width: 95vw;
            max-height: 95vw;
        }}
        .toolbar {{
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            height: 50px;
            background: #1a1a1a;
            border-bottom: 1px solid #333;
            display: flex;
            align-items: center;
            padding: 0 16px;
            gap: 12px;
            z-index: 1000;
            box-shadow: 0 2px 8px rgba(0,0,0,0.3);
        }}

        .button-group {{
            display: flex;
            gap: 8px;
            align-items: center;
        }}

        .button-group-label {{
            font-size: 12px;
            color: #999;
            margin-right: 4px;
        }}

        .toolbar button {{
            background: rgba(255,255,255,0.08);
            border: 1px solid rgba(255,255,255,0.15);
            color: #ddd;
            padding: 6px 12px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 12px;
            transition: all 0.2s;
        }}

        .toolbar button:hover {{
            background: rgba(255,255,255,0.12);
            border-color: rgba(255,255,255,0.25);
        }}

        .toolbar button.active {{
            background: rgba(74, 179, 255, 0.2);
            border-color: rgba(74, 179, 255, 0.5);
            color: #4ab3ff;
        }}

        .divider {{
            width: 1px;
            height: 24px;
            background: rgba(255,255,255,0.15);
        }}

        .hint {{
            font-size: 12px;
            color: #777;
            margin-left: auto;
        }}

        #content {{
            position: fixed;
            top: 10px;
            left: 0;
            right: 0;
            bottom: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
            box-sizing: border-box;
        }}

        #{div_id} {{
            width: 100% !important;
            height: 100% !important;
            max-width: min(100%, 100vh);
            max-height: min(100%, 100vw);
            aspect-ratio: 5 / 3;
        }}
    </style>
</head>
<body>
    <div class="toolbar">
        <div class="button-group">
            <span class="button-group-label">Mode:</span>
            <button id="btn-primary" class="mode-btn active" data-mode="primary">col</button>
            <button id="btn-country" class="mode-btn" data-mode="country_count">COUNT(DISTINCT(col))</button>
            <button id="btn-records" class="mode-btn" data-mode="record_count">COUNT(col)</button>
        </div>

        <div class="divider"></div>

        <div class="button-group">
            <span class="button-group-label">Colors:</span>
            <button id="btn-default" class="color-btn active" data-colorscheme="default">Default</button>
            <button id="btn-neon" class="color-btn" data-colorscheme="neon">Neon</button>
        </div>

        <div class="divider"></div>

        <div class="button-group">
            <button id="btn-overlays" class="overlay-btn active" data-enabled="true">Overlays</button>
        </div>

        <span class="hint">Click a cell to drill down to /24 view</span>
    </div>

    <div id="content">
        {html_content}
    </div>

    <script>
    (function() {{
        var buttonData = {button_data_json};
        var gd = document.getElementById("{div_id}");
        var currentMode = "primary";
        var currentColorscheme = "default";
        var overlaysEnabled = true;

        // Store original overlays (shapes and annotations)
        var originalShapes = buttonData && buttonData.overlay_shapes ? buttonData.overlay_shapes : [];
        var originalAnnotations = buttonData && buttonData.overlay_annotations ? buttonData.overlay_annotations : [];

        // Update button active states
        function updateButtonStates() {{
            document.querySelectorAll('.mode-btn').forEach(function(btn) {{
                btn.classList.toggle('active', btn.dataset.mode === currentMode);
            }});
            document.querySelectorAll('.color-btn').forEach(function(btn) {{
                btn.classList.toggle('active', btn.dataset.colorscheme === currentColorscheme);
            }});
            document.querySelectorAll('.overlay-btn').forEach(function(btn) {{
                btn.classList.toggle('active', overlaysEnabled);
            }});
        }}

        // Mode switching
        function switchMode(mode) {{
            if (!buttonData || !gd) return;
            currentMode = mode;

            var update = {{}};

            if (mode === "primary") {{
                update.z = [buttonData.z_primary];
                update.colorscale = [currentColorscheme === "neon" ?
                    buttonData.primary_colorscale_neon :
                    buttonData.primary_colorscale_default];
                update.zmin = [0];
                update.zmax = [Math.max(
                    buttonData.org_code_map ? Math.max(...Object.values(buttonData.org_code_map)) : 0,
                    1
                )];
                update.hovertemplate = [buttonData.hover_primary];
                update['colorbar.title'] = ["Org index"];
            }} else if (mode === "country_count") {{
                update.z = [buttonData.z_country];
                update.colorscale = [[[0.0, "#f7fbff"], [0.29, "#f7fbff"], [0.30, "#6baed6"], [0.50, "#6baed6"], [0.51, "#b30000"], [1.0, "#b30000"]]];
                update.zmin = [0];
                update.zmax = [Math.max(Math.min(buttonData.max_country, 10), 1)];
                update.hovertemplate = [buttonData.hover_country];
                update['colorbar.title'] = ["# orgs"];
            }} else if (mode === "record_count") {{
                update.z = [buttonData.z_records];
                update.colorscale = [[[0.0, "#f7fbff"], [0.29, "#f7fbff"], [0.30, "#6baed6"], [0.50, "#6baed6"], [0.51, "#b30000"], [1.0, "#b30000"]]];
                update.zmin = [0];
                update.zmax = [Math.max(buttonData.max_records, 1)];
                update.hovertemplate = [buttonData.hover_records];
                update['colorbar.title'] = ["# prefixes"];
            }}

            Plotly.update(gd, update, {{}});
            updateButtonStates();
        }}

        // Colorscheme switching
        function switchColorscheme(scheme) {{
            if (!buttonData || !gd || currentMode !== "primary") return;
            currentColorscheme = scheme;

            var colorscale = scheme === "neon" ?
                buttonData.primary_colorscale_neon :
                buttonData.primary_colorscale_default;

            Plotly.restyle(gd, {{ colorscale: [colorscale] }});
            updateButtonStates();
        }}

        // Overlay toggling
        function toggleOverlays() {{
            if (!gd) return;
            overlaysEnabled = !overlaysEnabled;

            var layoutUpdate = {{}};
            if (overlaysEnabled) {{
                // Show overlays
                layoutUpdate.shapes = originalShapes;
                layoutUpdate.annotations = originalAnnotations;
            }} else {{
                // Hide overlays
                layoutUpdate.shapes = [];
                layoutUpdate.annotations = [];
            }}

            Plotly.relayout(gd, layoutUpdate);
            updateButtonStates();
        }}

        // Setup event listeners
        document.addEventListener("DOMContentLoaded", function() {{
            // Mode buttons
            document.querySelectorAll('.mode-btn').forEach(function(btn) {{
                btn.addEventListener('click', function() {{
                    switchMode(this.dataset.mode);
                }});
            }});

            // Color buttons
            document.querySelectorAll('.color-btn').forEach(function(btn) {{
                btn.addEventListener('click', function() {{
                    switchColorscheme(this.dataset.colorscheme);
                }});
            }});

            // Overlay button
            document.querySelectorAll('.overlay-btn').forEach(function(btn) {{
                btn.addEventListener('click', function() {{
                    toggleOverlays();
                }});
            }});

            // Nested navigation click handler
            if (gd && gd.on) {{
                gd.on('plotly_click', function(evt) {{
                    if (!evt || !evt.points || !evt.points.length) return;
                    var p = evt.points[0];
                    var x = p.x;
                    var y = p.y;
                    if (x === undefined || y === undefined) return;
                    var url = "{frames_dir}/{nested_basename}_" + x + "_" + y + ".html";
                    window.location.href = url;
                }});
            }}

            // Handle window resize
            window.addEventListener("resize", function() {{
                if (gd && window.Plotly) {{
                    Plotly.Plots.resize(gd);
                }}
            }});

            // Initial resize to ensure proper sizing
            setTimeout(function() {{
                if (gd && window.Plotly) {{
                    Plotly.Plots.resize(gd);
                }}
            }}, 100);
        }});
    }})();
    </script>
</body>
</html>"""

    # Write HTML with compression
    original_size, final_size = _write_html_with_compression(html, out_path, compress=True)
    log.debug("Nested /16 HTML written successfully to %s", out_path)

    # Check file size and warn if over 100MB
    file_size_mb = final_size / (1024 * 1024)
    if file_size_mb > 100:
        log.warning(
            f"Compressed file size is {file_size_mb:.1f} MB, which exceeds 100 MB. "
            f"Consider using the .html.gz file for hosting."
        )
    elif original_size / (1024 * 1024) > 100:
        log.info(
            f"Original file was {original_size / (1024 * 1024):.1f} MB. "
            f"Use the .html.gz file for better hosting performance."
        )

def save_html_with_backlink(
        fig: Figure,
        path: PathLike,
        back_href: str,
        include_plotlyjs: str = "cdn",
        div_id: str = "ipmap_figure",
) -> None:
    """
    Save a figure as HTML with a "Back to /16 view" link and custom buttons at the top.
    """
    out_path = Path(path)
    log.info("Saving nested /24 HTML visualization to %s", out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Extract button data if available (use compressed format)
    button_data = getattr(fig, '_button_data', None)
    button_data_json = _compress_button_data(button_data)

    # We want just the div for the figure, no full HTML wrapper.
    fig_html = pio.to_html(
        fig,
        include_plotlyjs=False,
        full_html=False,
        div_id=div_id,
        config={"responsive": True},
    )

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8" />
    <title>{fig.layout.title.text if fig.layout.title else "IPv4 /24 view"}</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        body {{
            margin: 0;
            padding: 0;
            background: #111111;
            color: #EEEEEE;
            font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            height: 100vh;
            display: flex;
            overflow: hidden;
        }}

        .toolbar {{
            height: 44px;
            padding: 8px 12px;
            border-bottom: 1px solid #333;
            background: #181818;
            display: flex;
            gap: 14px;
            align-items: center;
            flex-shrink: 0;
        }}

        .toolbar a {{
            color: #4ab3ff;
            text-decoration: none;
            font-size: 14px;
        }}

        .toolbar a:hover {{
            text-decoration: underline;
        }}

        .button-group {{
            display: flex;
            gap: 6px;
            align-items: center;
        }}

        .button-group-label {{
            font-size: 11px;
            color: #999;
            margin-right: 4px;
        }}

        .toolbar button {{
            background: rgba(255,255,255,0.06);
            border: 1px solid rgba(255,255,255,0.12);
            color: #ddd;
            padding: 4px 10px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 11px;
            transition: all 0.2s;
        }}

        .toolbar button:hover {{
            background: rgba(255,255,255,0.10);
            border-color: rgba(255,255,255,0.20);
        }}

        .toolbar button.active {{
            background: rgba(74, 179, 255, 0.2);
            border-color: rgba(74, 179, 255, 0.5);
            color: #4ab3ff;
        }}

        .divider {{
            width: 1px;
            height: 20px;
            background: rgba(255,255,255,0.15);
        }}

        #content {{
            flex: 1;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
            box-sizing: border-box;
            min-height: 0;
        }}

        #{div_id} {{
            width: 100% !important;
            height: 100% !important;
            max-width: min(100%, 100vh);
            max-height: min(100%, 100vw);
            aspect-ratio: 5 / 3;
        }}
    </style>
</head>
<body>
    <div class="toolbar">
        <a href="{back_href}">&larr; Back to /16 view</a>

        <div class="divider"></div>

        <div class="button-group">
            <span class="button-group-label">Mode:</span>
            <button id="btn-primary" class="mode-btn active" data-mode="primary">col</button>
            <button id="btn-country" class="mode-btn" data-mode="country_count">COUNT(DISTINCT(col))</button>
            <button id="btn-records" class="mode-btn" data-mode="record_count">COUNT(col)</button>
        </div>

        <div class="divider"></div>

        <div class="button-group">
            <span class="button-group-label">Colors:</span>
            <button id="btn-default" class="color-btn active" data-colorscheme="default">Default</button>
            <button id="btn-neon" class="color-btn" data-colorscheme="neon">Neon</button>
        </div>
    </div>

    <div id="content">
        {fig_html}
    </div>

    <script>
    (function() {{
        var buttonData = {button_data_json};
        var gd = document.getElementById("{div_id}");
        var currentMode = "primary";
        var currentColorscheme = "default";

        // Update button active states
        function updateButtonStates() {{
            document.querySelectorAll('.mode-btn').forEach(function(btn) {{
                btn.classList.toggle('active', btn.dataset.mode === currentMode);
            }});
            document.querySelectorAll('.color-btn').forEach(function(btn) {{
                btn.classList.toggle('active', btn.dataset.colorscheme === currentColorscheme);
            }});
        }}

        // Mode switching
        function switchMode(mode) {{
            if (!buttonData || !gd) return;
            currentMode = mode;

            var update = {{}};

            if (mode === "primary") {{
                update.z = [buttonData.z_primary];
                update.colorscale = [currentColorscheme === "neon" ?
                    buttonData.primary_colorscale_neon :
                    buttonData.primary_colorscale_default];
                update.zmin = [0];
                update.zmax = [Math.max(
                    buttonData.org_code_map ? Math.max(...Object.values(buttonData.org_code_map)) : 0,
                    1
                )];
                update.hovertemplate = [buttonData.hover_primary];
                update['colorbar.title'] = ["Org index"];
            }} else if (mode === "country_count") {{
                update.z = [buttonData.z_country];
                update.colorscale = [[[0.0, "#f7fbff"], [0.29, "#f7fbff"], [0.30, "#6baed6"], [0.50, "#6baed6"], [0.51, "#b30000"], [1.0, "#b30000"]]];
                update.zmin = [0];
                update.zmax = [Math.max(Math.min(buttonData.max_country, 10), 1)];
                update.hovertemplate = [buttonData.hover_country];
                update['colorbar.title'] = ["# orgs"];
            }} else if (mode === "record_count") {{
                update.z = [buttonData.z_records];
                update.colorscale = [[[0.0, "#f7fbff"], [0.29, "#f7fbff"], [0.30, "#6baed6"], [0.50, "#6baed6"], [0.51, "#b30000"], [1.0, "#b30000"]]];
                update.zmin = [0];
                update.zmax = [Math.max(buttonData.max_records, 1)];
                update.hovertemplate = [buttonData.hover_records];
                update['colorbar.title'] = ["# prefixes"];
            }}

            Plotly.update(gd, update, {{}});
            updateButtonStates();
        }}

        // Colorscheme switching
        function switchColorscheme(scheme) {{
            if (!buttonData || !gd || currentMode !== "primary") return;
            currentColorscheme = scheme;

            var colorscale = scheme === "neon" ?
                buttonData.primary_colorscale_neon :
                buttonData.primary_colorscale_default;

            Plotly.restyle(gd, {{ colorscale: [colorscale] }});
            updateButtonStates();
        }}

        // Setup event listeners
        document.addEventListener("DOMContentLoaded", function() {{
            // Mode buttons
            document.querySelectorAll('.mode-btn').forEach(function(btn) {{
                btn.addEventListener('click', function() {{
                    switchMode(this.dataset.mode);
                }});
            }});

            // Color buttons
            document.querySelectorAll('.color-btn').forEach(function(btn) {{
                btn.addEventListener('click', function() {{
                    switchColorscheme(this.dataset.colorscheme);
                }});
            }});

            // Handle window resize
            window.addEventListener("resize", function() {{
                if (gd && window.Plotly) {{
                    Plotly.Plots.resize(gd);
                }}
            }});

            // Initial resize to ensure proper sizing
            setTimeout(function() {{
                if (gd && window.Plotly) {{
                    Plotly.Plots.resize(gd);
                }}
            }}, 100);
        }});
    }})();
    </script>
</body>
</html>"""

    # Write HTML with compression
    _write_html_with_compression(html, out_path, compress=True)
    log.debug("Nested /24 HTML written successfully to %s", out_path)


def save_html_consolidated(
        fig_16: Figure,
        views_24: list[dict],
        output_path: PathLike,
        mode: str = "primary",
        colorscale_mode: str = "default",
        include_plotlyjs: str = "cdn",
        whois_provider: str = "rdap_org",
) -> None:
    """
    Save a single HTML with /16 + all /24 views embedded.
    Uses JavaScript show/hide to switch between views.

    Parameters
    ----------
    fig_16 : Figure
        The /16 heatmap figure.
    views_24 : list[dict]
        List of dicts with keys: 'bx', 'by', 'figure', 'parent_cidr'
    output_path : PathLike
        Output path for the consolidated HTML file.
    mode : str
        Initial mode ("primary", "country_count", "record_count").
    colorscale_mode : str
        Initial colorscale mode ("default", "neon").
    include_plotlyjs : str
        How to include Plotly.js ("cdn", "directory", "inline").
    whois_provider : str
        RDAP provider ("rdap_org" or "arin").
    """
    output_path = Path(output_path)
    log.info(f"Saving consolidated HTML with {len(views_24)} /24 views to {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Extract button data for /16
    button_data_16 = getattr(fig_16, '_button_data', None)

    # 2. Generate /16 Plotly HTML (div only)
    html_16 = pio.to_html(
        fig_16,
        include_plotlyjs=False,
        full_html=False,
        div_id="ipmap_figure_16",
        config={"responsive": True},
    )

    # 3. Generate all /24 Plotly HTMLs (divs only) + collect button data
    views_24_html = []
    for view in views_24:
        bx, by = view['bx'], view['by']
        fig = view['figure']
        button_data = getattr(fig, '_button_data', None)

        html = pio.to_html(
            fig,
            include_plotlyjs=False,
            full_html=False,
            div_id=f"ipmap_figure_24_{bx}_{by}",
            config={"responsive": True},
        )

        views_24_html.append({
            'bx': bx,
            'by': by,
            'html': html,
            'button_data': button_data,
            'parent_cidr': view['parent_cidr'],
            'div_id': f"ipmap_figure_24_{bx}_{by}",
        })

    # 4. Build complete HTML document
    html_doc = _build_consolidated_html_template(
        html_16=html_16,
        button_data_16=button_data_16,
        views_24=views_24_html,
        whois_provider=whois_provider,
    )

    # 5. Write to disk with compression
    original_size, final_size = _write_html_with_compression(html_doc, output_path, compress=True)
    log.info(f"Consolidated HTML written successfully to {output_path}")

    # 6. Check file size and warn if over 100MB
    file_size_mb = final_size / (1024 * 1024)
    if file_size_mb > 100:
        log.warning(
            f"Compressed file size is {file_size_mb:.1f} MB, which exceeds 100 MB. "
            f"Consider using the .html.gz file for hosting. "
            f"Consolidated mode embeds all /24 views - use separate files for very large datasets."
        )
    elif original_size / (1024 * 1024) > 100:
        log.info(
            f"Original file was {original_size / (1024 * 1024):.1f} MB. "
            f"Use the .html.gz file for better hosting performance."
        )


def _build_consolidated_html_template(
        html_16: str,
        button_data_16: dict | None,
        views_24: list[dict],
        whois_provider: str,
) -> str:
    """
    Build the complete HTML document for consolidated nested view.

    Parameters
    ----------
    html_16 : str
        Plotly HTML for /16 figure (div only).
    button_data_16 : dict | None
        Button data for /16 figure (z-matrices, colorscales, etc.).
    views_24 : list[dict]
        List of dicts with keys: 'bx', 'by', 'html', 'button_data', 'parent_cidr', 'div_id'
    whois_provider : str
        RDAP provider ("rdap_org" or "arin").

    Returns
    -------
    str
        Complete HTML document.
    """
    # Base RDAP URL
    if whois_provider == "arin":
        rdap_base = "https://rdap.arin.net/registry/ip/"
    else:
        rdap_base = "https://rdap.org/ip/"

    # Build button data JSON for all views (with compression for each view)
    all_button_data = {}

    # Compress /16 button data
    if button_data_16:
        all_button_data["16"] = json.loads(_compress_button_data(button_data_16))
    else:
        all_button_data["16"] = None

    parent_cidrs = {}
    for view in views_24:
        view_id = f"24-{view['bx']}-{view['by']}"
        # Compress each /24 button data
        if view['button_data']:
            all_button_data[view_id] = json.loads(_compress_button_data(view['button_data']))
        else:
            all_button_data[view_id] = None
        parent_cidrs[view_id] = view['parent_cidr']

    # Use compact JSON encoding
    all_button_data_json = json.dumps(all_button_data, separators=(',', ':'))
    parent_cidrs_json = json.dumps(parent_cidrs, separators=(',', ':'))

    # Generate /24 view containers HTML
    views_24_containers = ""
    for view in views_24:
        bx, by = view['bx'], view['by']
        view_id = f"24-{bx}-{by}"
        views_24_containers += f"""
    <div id="view-{view_id}" class="view-container" style="display:none">
        <div class="split-pane">
            <div class="left">
                {view['html']}
            </div>
            <div class="right">
                <div class="panelHeader">
                    <div>
                        <div class="title" id="rdap-title-{view_id}">RDAP: {view['parent_cidr']}</div>
                        <div class="sub">Click a /24 cell to update</div>
                    </div>
                    <button onclick="copyRdap()">Copy JSON</button>
                </div>
                <div class="panelBody" id="rdap-panel-{view_id}"></div>
            </div>
        </div>
    </div>
"""

    # Build complete HTML
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>IPv4 Address Space Visualization (Consolidated Nested)</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        body {{
            margin: 0;
            padding: 0;
            background: #111111;
            color: #EEEEEE;
            font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            overflow: hidden;
        }}

        /* Toolbar */
        .toolbar {{
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            height: 50px;
            background: #1a1a1a;
            border-bottom: 1px solid #333;
            display: flex;
            align-items: center;
            padding: 0 16px;
            gap: 12px;
            z-index: 1000;
            box-shadow: 0 2px 8px rgba(0,0,0,0.3);
        }}

        .button-group {{
            display: flex;
            gap: 8px;
            align-items: center;
        }}

        .button-group-label {{
            font-size: 12px;
            color: #999;
            margin-right: 4px;
        }}

        .toolbar button, .toolbar a.button {{
            background: rgba(255,255,255,0.08);
            border: 1px solid rgba(255,255,255,0.15);
            color: #ddd;
            padding: 6px 12px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 12px;
            transition: all 0.2s;
            text-decoration: none;
            display: inline-block;
        }}

        .toolbar button:hover, .toolbar a.button:hover {{
            background: rgba(255,255,255,0.12);
            border-color: rgba(255,255,255,0.25);
        }}

        .toolbar button.active {{
            background: rgba(74, 179, 255, 0.2);
            border-color: rgba(74, 179, 255, 0.5);
            color: #4ab3ff;
        }}

        .divider {{
            width: 1px;
            height: 24px;
            background: rgba(255,255,255,0.15);
        }}

        .view-indicator {{
            font-size: 14px;
            color: #4ab3ff;
            margin-left: 16px;
            font-weight: 500;
        }}

        #back-btn {{
            display: none;
        }}

        /* View containers */
        .view-container {{
            position: fixed;
            top: 60px;
            left: 0;
            right: 0;
            bottom: 0;
        }}

        /* /16 view styling */
        #view-16 {{
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
            box-sizing: border-box;
        }}

        #ipmap_figure_16 {{
            width: 100% !important;
            height: 100% !important;
            max-width: min(100%, 100vh);
            max-height: min(100%, 100vw);
            aspect-ratio: 5 / 3;
        }}

        /* /24 view split-pane layout */
        .split-pane {{
            display: flex;
            gap: 16px;
            height: 100%;
            padding: 20px;
            box-sizing: border-box;
        }}

        .left {{
            flex: 1 1 auto;
            min-width: 650px;
            min-height: 650px;
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 14px;
            background: rgba(255,255,255,0.02);
            overflow: hidden;
            position: relative;
        }}

        .left > div {{
            width: 100% !important;
            height: 100% !important;
        }}

        .right {{
            min-width: 520px;
            min-height: 520px;
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 14px;
            background: rgba(255,255,255,0.02);
            overflow: hidden;
            display: flex;
            flex-direction: column;
        }}

        .panelHeader {{
            padding: 10px 12px;
            border-bottom: 1px solid rgba(255,255,255,0.08);
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 10px;
        }}

        .panelHeader .title {{
            font-size: 13px;
            color: #eaeaea;
            font-weight: 600;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}

        .panelHeader .sub {{
            font-size: 11px;
            color: #a9a9a9;
        }}

        .panelHeader button {{
            background: rgba(255,255,255,0.06);
            border: 1px solid rgba(255,255,255,0.12);
            color: #eee;
            padding: 6px 10px;
            border-radius: 10px;
            cursor: pointer;
            font-size: 12px;
        }}

        .panelHeader button:hover {{
            background: rgba(255,255,255,0.10);
        }}

        .panelBody {{
            padding: 5px 6px;
            overflow: auto;
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
            font-size: 12px;
            line-height: 1.35;
            white-space: pre;
            flex: 1;
        }}
    </style>
</head>
<body>
    <div class="toolbar">
        <a href="#" id="back-btn" class="button" onclick="goBack(); return false;">&larr; Back to /16</a>

        <div class="divider"></div>

        <div class="button-group">
            <span class="button-group-label">Mode:</span>
            <button id="btn-primary" class="mode-btn active" data-mode="primary">col</button>
            <button id="btn-country" class="mode-btn" data-mode="country_count">COUNT(DISTINCT(col))</button>
            <button id="btn-records" class="mode-btn" data-mode="record_count">COUNT(col)</button>
        </div>

        <div class="divider"></div>

        <div class="button-group">
            <span class="button-group-label">Colors:</span>
            <button id="btn-default" class="color-btn active" data-colorscheme="default">Default</button>
            <button id="btn-neon" class="color-btn" data-colorscheme="neon">Neon</button>
        </div>

        <div class="divider"></div>

        <div class="button-group">
            <button id="btn-overlays" class="overlay-btn active" data-enabled="true">Overlays</button>
        </div>

        <span class="view-indicator" id="view-indicator">/16 Overview</span>
    </div>

    <div id="view-16" class="view-container" style="display:block">
        {html_16}
    </div>

{views_24_containers}

    <script>
    (function() {{
        // Global state
        var currentView = '16';
        var currentMode = 'primary';
        var currentColorscheme = 'default';
        var overlaysEnabled = true;
        var allButtonData = {all_button_data_json};
        var parentCidrs = {parent_cidrs_json};
        var rdapBase = "{rdap_base}";

        // Store original overlays for /16 view
        var originalShapes16 = allButtonData['16'] && allButtonData['16'].overlay_shapes ? allButtonData['16'].overlay_shapes : [];
        var originalAnnotations16 = allButtonData['16'] && allButtonData['16'].overlay_annotations ? allButtonData['16'].overlay_annotations : [];

        // Get all Plotly graph divs
        var gd16 = document.getElementById('ipmap_figure_16');
        var allGds = {{}};
        allGds['16'] = gd16;

        // Register all /24 graph divs
        {''.join([f"allGds['24-{v['bx']}-{v['by']}'] = document.getElementById('{v['div_id']}');\n        " for v in views_24])}

        // Navigation functions
        function showView(viewId) {{
            console.log('Switching to view:', viewId);

            // Hide all views
            document.querySelectorAll('.view-container').forEach(function(v) {{
                v.style.display = 'none';
            }});

            // Show selected view
            var viewElem = document.getElementById('view-' + viewId);
            if (viewElem) {{
                viewElem.style.display = viewId === '16' ? 'flex' : 'block';
            }}

            currentView = viewId;

            // Update toolbar
            var backBtn = document.getElementById('back-btn');
            var viewIndicator = document.getElementById('view-indicator');

            if (viewId === '16') {{
                backBtn.style.display = 'none';
                viewIndicator.textContent = '/16 Overview';
            }} else {{
                backBtn.style.display = 'block';
                var cidr = parentCidrs[viewId] || viewId;
                viewIndicator.textContent = 'Inside ' + cidr;

                // Update RDAP panel
                updateRdapPanel(viewId, cidr);
            }}

            // Trigger resize for Plotly
            setTimeout(function() {{
                var gd = allGds[viewId];
                if (gd && window.Plotly) {{
                    Plotly.Plots.resize(gd);
                }}
            }}, 100);
        }}

        function goBack() {{
            showView('16');
        }}

        // RDAP fetching
        function updateRdapPanel(viewId, cidr) {{
            var panelId = 'rdap-panel-' + viewId;
            var titleId = 'rdap-title-' + viewId;
            var panel = document.getElementById(panelId);
            var title = document.getElementById(titleId);

            if (!panel) return;

            // Extract IP from CIDR
            var ip = cidr.split('/')[0];
            var url = rdapBase + ip;

            panel.textContent = 'Loading...';
            if (title) title.textContent = 'RDAP: ' + cidr;

            fetch(url)
                .then(function(resp) {{
                    if (!resp.ok) throw new Error('HTTP ' + resp.status);
                    return resp.json();
                }})
                .then(function(data) {{
                    panel.textContent = JSON.stringify(data, null, 2);
                }})
                .catch(function(err) {{
                    panel.textContent = 'Error: ' + err.message;
                }});
        }}

        function copyRdap() {{
            var viewId = currentView;
            if (viewId === '16') return;

            var panelId = 'rdap-panel-' + viewId;
            var panel = document.getElementById(panelId);
            if (!panel) return;

            var text = panel.textContent;
            navigator.clipboard.writeText(text).then(function() {{
                console.log('RDAP JSON copied to clipboard');
            }}).catch(function(err) {{
                console.error('Failed to copy:', err);
            }});
        }}

        // Mode switching
        function updateButtonStates() {{
            document.querySelectorAll('.mode-btn').forEach(function(btn) {{
                btn.classList.toggle('active', btn.dataset.mode === currentMode);
            }});
            document.querySelectorAll('.color-btn').forEach(function(btn) {{
                btn.classList.toggle('active', btn.dataset.colorscheme === currentColorscheme);
            }});
            document.querySelectorAll('.overlay-btn').forEach(function(btn) {{
                btn.classList.toggle('active', overlaysEnabled);
            }});
        }}

        function switchMode(mode) {{
            currentMode = mode;
            updateButtonStates();

            // Update all figures
            for (var viewId in allGds) {{
                var gd = allGds[viewId];
                var buttonData = allButtonData[viewId];
                if (gd && buttonData) {{
                    updateFigure(gd, mode, buttonData);
                }}
            }}
        }}

        function switchColorscheme(scheme) {{
            currentColorscheme = scheme;
            updateButtonStates();

            // Re-apply current mode with new colorscheme
            switchMode(currentMode);
        }}

        // Overlay toggling (only for /16 view)
        function toggleOverlays() {{
            if (!gd16) return;
            overlaysEnabled = !overlaysEnabled;

            var layoutUpdate = {{}};
            if (overlaysEnabled) {{
                // Show overlays
                layoutUpdate.shapes = originalShapes16;
                layoutUpdate.annotations = originalAnnotations16;
            }} else {{
                // Hide overlays
                layoutUpdate.shapes = [];
                layoutUpdate.annotations = [];
            }}

            Plotly.relayout(gd16, layoutUpdate);
            updateButtonStates();
        }}

        function updateFigure(gd, mode, buttonData) {{
            if (!gd || !buttonData) return;

            var update = {{}};

            if (mode === 'primary') {{
                update.z = [buttonData.z_primary];
                update.colorscale = [currentColorscheme === 'neon' ?
                    buttonData.primary_colorscale_neon :
                    buttonData.primary_colorscale_default];
                update.zmin = [0];
                update.zmax = [Math.max(
                    buttonData.org_code_map ? Math.max(...Object.values(buttonData.org_code_map)) : 0,
                    1
                )];
                update.hovertemplate = [buttonData.hover_primary];
                update['colorbar.title'] = ['Org index'];
            }} else if (mode === 'country_count') {{
                update.z = [buttonData.z_country];
                update.colorscale = [[[0.0, "#f7fbff"], [0.29, "#f7fbff"], [0.30, "#6baed6"], [0.50, "#6baed6"], [0.51, "#b30000"], [1.0, "#b30000"]]];
                update.zmin = [0];
                update.zmax = [Math.max(Math.min(buttonData.max_country || 10, 10), 1)];
                update.hovertemplate = [buttonData.hover_country];
                update['colorbar.title'] = ['Countries'];
            }} else if (mode === 'record_count') {{
                update.z = [buttonData.z_records];
                update.colorscale = [[[0.0, "#08519c"], [0.25, "#3182bd"], [0.50, "#6baed6"], [0.75, "#bdd7e7"], [1.0, "#eff3ff"]]];
                update.zmin = [0];
                update.zmax = [Math.max(buttonData.max_records || 1, 1)];
                update.hovertemplate = [buttonData.hover_records];
                update['colorbar.title'] = ['Records'];
            }}

            Plotly.restyle(gd, update, [0]);
        }}

        // Event listeners
        document.addEventListener('DOMContentLoaded', function() {{
            // Mode buttons
            document.querySelectorAll('.mode-btn').forEach(function(btn) {{
                btn.addEventListener('click', function() {{
                    switchMode(this.dataset.mode);
                }});
            }});

            // Color buttons
            document.querySelectorAll('.color-btn').forEach(function(btn) {{
                btn.addEventListener('click', function() {{
                    switchColorscheme(this.dataset.colorscheme);
                }});
            }});

            // Overlay button
            document.querySelectorAll('.overlay-btn').forEach(function(btn) {{
                btn.addEventListener('click', function() {{
                    toggleOverlays();
                }});
            }});

            // /16 click handler - navigate to /24 view
            if (gd16 && gd16.on) {{
                gd16.on('plotly_click', function(evt) {{
                    if (!evt || !evt.points || !evt.points.length) return;
                    var p = evt.points[0];
                    var x = p.x;
                    var y = p.y;
                    if (x === undefined || y === undefined) return;

                    var viewId = '24-' + x + '-' + y;
                    showView(viewId);
                }});
            }}

            // /24 click handlers - update RDAP panel
            {''.join([f'''
            (function() {{
                var gd = document.getElementById('{v['div_id']}');
                if (gd && gd.on) {{
                    gd.on('plotly_click', function(evt) {{
                        if (!evt || !evt.points || !evt.points.length) return;
                        var p = evt.points[0];
                        var x = p.x;
                        var y = p.y;
                        if (x === undefined || y === undefined) return;

                        // Calculate /24 CIDR: bx.by.x.0/24
                        var cidr = '{v['bx']}' + '.' + '{v['by']}' + '.' + x + '.0/24';
                        updateRdapPanel('24-{v['bx']}-{v['by']}', cidr);
                    }});
                }}
            }})();
            ''' for v in views_24])}

            // Window resize
            window.addEventListener('resize', function() {{
                var gd = allGds[currentView];
                if (gd && window.Plotly) {{
                    Plotly.Plots.resize(gd);
                }}
            }});

            // Initial resize
            setTimeout(function() {{
                if (gd16 && window.Plotly) {{
                    Plotly.Plots.resize(gd16);
                }}
            }}, 100);
        }});
    }})();
    </script>
</body>
</html>"""

    return html
