"""One HTML file of the installation visual, opened outside the app."""

from __future__ import annotations

import json
from html import escape
from pathlib import Path

from django.conf import settings

from apps.optimisation.models import OptimisationRun
from apps.optimisation.services.timelapse import timelapse_payload

_STYLE = """
body { margin: 0; font-family: system-ui, sans-serif; color: #1c2833; background: #f4f6f8; }
main { max-width: 1280px; margin: 0 auto; padding: 24px 20px 40px; }
h1 { font-size: 1.4rem; margin: 0 0 0.25rem; }
p { margin: 0 0 1rem; color: #52606d; }
.timelapse-stage:fullscreen, .timelapse-stage:-webkit-full-screen {
  display: flex; flex-direction: column; box-sizing: border-box;
  width: 100%; height: 100%; padding: 16px 20px 12px; background: #fbfcfe;
}
.timelapse-stage:fullscreen .timelapse-map, .timelapse-stage:-webkit-full-screen .timelapse-map {
  flex: 1 1 auto; width: 100%; height: 100%; min-height: 0; border: 0;
}
.timelapse-map { display: block; width: 100%; height: auto; background: #fbfcfe; border: 1px solid #d5dde5; border-radius: 8px; }
.timelapse-map .grid { stroke: #dce3ea; stroke-width: 1; }
.timelapse-map .tick { fill: #52606d; font-size: 11px; }
.timelapse-map .label { font-size: 10px; font-weight: 600; paint-order: stroke; stroke: white; stroke-width: 4px; stroke-linejoin: round; fill: #172033; }
.timelapse-map .point { stroke: white; stroke-width: 2; }
.timelapse-map .route { fill: none; stroke-linecap: round; stroke-linejoin: round; }
.timelapse-controls { display: flex; gap: 10px; align-items: center; padding: 12px 0 4px; flex-wrap: wrap; }
.timelapse-controls button, .timelapse-controls select { padding: 7px 12px; border: 1px solid #aab6c2; border-radius: 7px; background: white; font-weight: 600; }
.timelapse-controls input[type="range"] { flex: 1; min-width: 180px; }
#timelapse-legend { display: flex; flex-wrap: wrap; gap: 0.75rem; margin-bottom: 0.5rem; font-size: 0.9rem; }
#timelapse-status { font-weight: 700; margin-bottom: 0.5rem; }
"""


def visual_filename(run: OptimisationRun) -> str:
    return f"sequencer_visual_run{run.pk}.html"


def build_visual_html(run: OptimisationRun) -> str | None:
    payload = timelapse_payload(run)
    player = payload.get("player") if payload else None
    if not player or not player.get("places"):
        return None
    script = Path(settings.BASE_DIR, "static", "js", "timelapse.js").read_text(encoding="utf-8")
    data = json.dumps(player, ensure_ascii=True).replace("<", "\\u003c")
    title = escape(f"{run.scenario.project.name} · {run.scenario.name} · run {run.pk}")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>{_STYLE}</style>
</head>
<body>
  <main>
    <h1>{title}</h1>
    <p>Installation sequence. Pace x1 is one calendar day per second. Step jumps to the next start. This file opens in a browser without Sequencer.</p>
    <div id="timelapse-stage" class="timelapse-stage">
      <div id="timelapse-status"></div>
      <div id="timelapse-legend"></div>
      <svg id="timelapse-map" class="timelapse-map" viewBox="0 0 1500 860" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Installation sequence on easting and northing axes"></svg>
      <div class="timelapse-controls">
        <button type="button" id="timelapse-play">Pause</button>
        <button type="button" id="timelapse-prev">◀ Step</button>
        <button type="button" id="timelapse-next">Step ▶</button>
        <label>Pace
          <select id="timelapse-speed">
            <option value="0.5">x0.5</option>
            <option value="1" selected>x1</option>
            <option value="2">x2</option>
            <option value="4">x4</option>
          </select>
        </label>
        <input id="timelapse-slider" type="range" min="0" max="1000" value="0">
        <button type="button" id="timelapse-fullscreen">Full screen</button>
      </div>
    </div>
  </main>
  <script type="application/json" id="timelapse-data">{data}</script>
  <script>
{script}
  </script>
</body>
</html>
"""
