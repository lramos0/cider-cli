# ipmap/viz/export.py

from __future__ import annotations
import json
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

    # Extract button data if available
    button_data = getattr(fig, '_button_data', None)
    button_data_json = json.dumps(button_data) if button_data else "null"

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
            top: 50px;
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
            aspect-ratio: 1 / 1;
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
            <button id="btn-primary" class="mode-btn active" data-mode="primary">Primary</button>
            <button id="btn-country" class="mode-btn" data-mode="country_count"># Orgs</button>
            <button id="btn-records" class="mode-btn" data-mode="record_count"># Prefixes</button>
        </div>

        <div class="divider"></div>

        <div class="button-group">
            <span class="button-group-label">Colors:</span>
            <button id="btn-default" class="color-btn active" data-colorscheme="default">Default</button>
            <button id="btn-neon" class="color-btn" data-colorscheme="neon">Neon</button>
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

    out_path.write_text(html, encoding="utf-8")
    log.debug("HTML (with whois-on-click and custom buttons) written successfully to %s", out_path)

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

    # Extract button data if available
    button_data = getattr(fig, '_button_data', None)
    button_data_json = json.dumps(button_data) if button_data else "null"

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
              html, body {{
                height: 100%;
                margin: 0;
                background: #111111;
                color: #EEEEEE;
                font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
              }}
              .toolbar {{
                height: 44px;
                padding: 8px 12px;
                border-bottom: 1px solid #333;
                background: #181818;
                display: flex;
                gap: 14px;
                align-items: center;
                box-sizing: border-box;
              }}
              .toolbar a {{
                color: #4ab3ff;
                text-decoration: none;
                font-size: 14px;
              }}
              .toolbar a:hover {{ text-decoration: underline; }}
              .hint {{ font-size: 12px; color: #aaa; }}

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
                min-width: 520px;
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
                width: 800px;
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
            </style>
          </head>
          <body>
            <div class="toolbar">
              <a href="{back_href}">&larr; Back to /16 view</a>

              <div class="divider"></div>

              <div class="button-group">
                <span class="button-group-label">Mode:</span>
                <button id="btn-primary" class="mode-btn active" data-mode="primary">Primary</button>
                <button id="btn-country" class="mode-btn" data-mode="country_count"># Orgs</button>
                <button id="btn-records" class="mode-btn" data-mode="record_count"># Prefixes</button>
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
    out_path.write_text(html, encoding="utf-8")
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
) -> None:
    """
    Save the top-level /16 figure as HTML with custom buttons and inject JS that:
      - listens for plotly_click
      - redirects to <nested_basename>_16_<bucket_x>_<bucket_y>.html
    """
    out_path = Path(path)
    log.info("Saving nested /16 HTML visualization to %s", out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Extract button data if available
    button_data = getattr(fig, '_button_data', None)
    button_data_json = json.dumps(button_data) if button_data else "null"

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
            top: 50px;
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
            aspect-ratio: 1 / 1;
        }}
    </style>
</head>
<body>
    <div class="toolbar">
        <div class="button-group">
            <span class="button-group-label">Mode:</span>
            <button id="btn-primary" class="mode-btn active" data-mode="primary">Primary</button>
            <button id="btn-country" class="mode-btn" data-mode="country_count"># Orgs</button>
            <button id="btn-records" class="mode-btn" data-mode="record_count"># Prefixes</button>
        </div>

        <div class="divider"></div>

        <div class="button-group">
            <span class="button-group-label">Colors:</span>
            <button id="btn-default" class="color-btn active" data-colorscheme="default">Default</button>
            <button id="btn-neon" class="color-btn" data-colorscheme="neon">Neon</button>
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

            // Nested navigation click handler
            if (gd && gd.on) {{
                gd.on('plotly_click', function(evt) {{
                    if (!evt || !evt.points || !evt.points.length) return;
                    var p = evt.points[0];
                    var x = p.x;
                    var y = p.y;
                    if (x === undefined || y === undefined) return;
                    var url = "{nested_basename}_16_" + x + "_" + y + ".html";
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
    Save a figure as HTML with a "Back to /16 view" link and custom buttons at the top.
    """
    out_path = Path(path)
    log.info("Saving nested /24 HTML visualization to %s", out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Extract button data if available
    button_data = getattr(fig, '_button_data', None)
    button_data_json = json.dumps(button_data) if button_data else "null"

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
            flex-direction: column;
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
            max-height: min(100%, 100vw - 40px);
            aspect-ratio: 1 / 1;
        }}
    </style>
</head>
<body>
    <div class="toolbar">
        <a href="{back_href}">&larr; Back to /16 view</a>

        <div class="divider"></div>

        <div class="button-group">
            <span class="button-group-label">Mode:</span>
            <button id="btn-primary" class="mode-btn active" data-mode="primary">Primary</button>
            <button id="btn-country" class="mode-btn" data-mode="country_count"># Orgs</button>
            <button id="btn-records" class="mode-btn" data-mode="record_count"># Prefixes</button>
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

    out_path.write_text(html, encoding="utf-8")
    log.debug("Nested /24 HTML written successfully to %s", out_path)
