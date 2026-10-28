/* Calendar timelapse. FOU circles, WTG squares. Within-trip legs only. */
(function () {
  var node = document.getElementById("timelapse-data");
  var svg = document.getElementById("timelapse-map");
  if (!node || !svg) return;
  var payload = JSON.parse(node.textContent);
  var data = payload.activities || [];
  var labels = payload.labels || [];
  if (!data.length) return;
  var origin = payload.origin;
  var horizon = payload.horizon;
  var NS = "http://www.w3.org/2000/svg";
  var DAY = 86400000;
  var packageColor = { FOU: "#1f77b4", IAC: "#2ca02c", WTG: "#ff7f0e" };
  var dormant = "#b7c0ca";
  var time = origin;
  var playing = true;
  var timer = null;
  var delay = 400;
  var pace = DAY;
  var sliderMax = 1000;
  var layout = project(data);

  function el(tag, attrs, text) {
    var node = document.createElementNS(NS, tag);
    Object.keys(attrs).forEach(function (key) { node.setAttribute(key, attrs[key]); });
    if (text) node.textContent = text;
    return node;
  }

  function project(points) {
    var xs = [];
    var ys = [];
    points.forEach(function (point) {
      xs.push(point.x);
      ys.push(point.y);
      if (point.x2 != null && point.y2 != null) {
        xs.push(point.x2);
        ys.push(point.y2);
      }
    });
    labels.forEach(function (label) {
      xs.push(label.x);
      ys.push(label.y);
    });
    var minX = Math.min.apply(null, xs);
    var maxX = Math.max.apply(null, xs);
    var minY = Math.min.apply(null, ys);
    var maxY = Math.max.apply(null, ys);
    if (minX === maxX) { minX -= 1; maxX += 1; }
    if (minY === maxY) { minY -= 1; maxY += 1; }
    var plotW = 1360;
    var plotH = 680;
    var scale = Math.min(plotW / (maxX - minX), plotH / (maxY - minY));
    var usedW = (maxX - minX) * scale;
    var usedH = (maxY - minY) * scale;
    var originX = 110 + (plotW - usedW) / 2;
    var originY = 70 + (plotH - usedH) / 2;
    return {
      minX: minX, maxX: maxX, minY: minY, maxY: maxY, scale: scale,
      X: function (x) { return originX + (x - minX) * scale; },
      Y: function (y) { return originY + (maxY - y) * scale; },
      left: originX, right: originX + usedW, top: originY, bottom: originY + usedH
    };
  }

  function stepSize(span) {
    var rough = span / 6;
    if (rough <= 0) return 1;
    var power = Math.pow(10, Math.floor(Math.log10(rough)));
    var fraction = rough / power;
    var factor = fraction >= 7.5 ? 10 : fraction >= 3.5 ? 5 : fraction >= 1.5 ? 2 : 1;
    return factor * power;
  }

  function pad(value) {
    return (value < 10 ? "0" : "") + value;
  }

  function formatDate(ms) {
    var date = new Date(ms);
    return date.getUTCFullYear() + "-" + pad(date.getUTCMonth() + 1) + "-" + pad(date.getUTCDate())
      + " " + pad(date.getUTCHours()) + ":" + pad(date.getUTCMinutes());
  }

  function color(point) {
    return packageColor[point.package] || packageColor.FOU;
  }

  function started(point) { return point.start <= time; }
  function installing(point) { return point.start <= time && time < point.end; }

  function base() {
    svg.innerHTML = "";
    var xStep = stepSize(layout.maxX - layout.minX);
    var yStep = stepSize(layout.maxY - layout.minY);
    var x = Math.ceil(layout.minX / xStep) * xStep;
    for (; x <= layout.maxX + xStep * 0.001; x += xStep) {
      var px = layout.X(x);
      svg.appendChild(el("line", { x1: px, y1: layout.top, x2: px, y2: layout.bottom, class: "grid" }));
      svg.appendChild(el("text", { x: px, y: layout.bottom + 22, "text-anchor": "middle", class: "tick" }, String(Math.round(x))));
    }
    var y = Math.ceil(layout.minY / yStep) * yStep;
    for (; y <= layout.maxY + yStep * 0.001; y += yStep) {
      var py = layout.Y(y);
      svg.appendChild(el("line", { x1: layout.left, y1: py, x2: layout.right, y2: py, class: "grid" }));
      svg.appendChild(el("text", { x: layout.left - 8, y: py + 4, "text-anchor": "end", class: "tick" }, String(Math.round(y))));
    }
    svg.appendChild(el("text", {
      x: (layout.left + layout.right) / 2, y: 840, "text-anchor": "middle", class: "tick", "font-weight": "bold"
    }, "Easting [m]"));
    svg.appendChild(el("text", {
      x: 28, y: (layout.top + layout.bottom) / 2, "text-anchor": "middle", class: "tick",
      "font-weight": "bold", transform: "rotate(-90 28 " + ((layout.top + layout.bottom) / 2) + ")"
    }, "Northing [m]"));
  }

  function groups() {
    var grouped = {};
    data.forEach(function (point) {
      if (!grouped[point.package]) grouped[point.package] = [];
      grouped[point.package].push(point);
    });
    Object.keys(grouped).forEach(function (packageName) {
      grouped[packageName].sort(function (left, right) { return left.seq - right.seq; });
    });
    return grouped;
  }

  function drawRoutes(points) {
    var active = {};
    points.forEach(function (point) {
      if (started(point) && time < point.end) active[point.trip] = true;
    });
    var i;
    for (i = 1; i < points.length; i += 1) {
      var previous = points[i - 1];
      var current = points[i];
      if (previous.trip !== current.trip || !active[current.trip]) continue;
      if (!started(previous) || !started(current)) continue;
      svg.appendChild(el("line", {
        x1: layout.X(previous.x), y1: layout.Y(previous.y),
        x2: layout.X(current.x), y2: layout.Y(current.y),
        class: "route",
        stroke: color(current),
        "stroke-width": 5,
        opacity: 0.95
      }));
    }
  }

  function drawLabels() {
    labels.forEach(function (label) {
      svg.appendChild(el("text", {
        x: layout.X(label.x), y: layout.Y(label.y),
        "text-anchor": "middle", class: "label"
      }, label.id));
    });
  }

  function drawCables() {
    data.forEach(function (point) {
      if (point.package !== "IAC" || point.x2 == null || point.y2 == null) return;
      if (time < point.start) return;
      var finished = time >= point.end;
      svg.appendChild(el("line", {
        x1: layout.X(point.x), y1: layout.Y(point.y),
        x2: layout.X(point.x2), y2: layout.Y(point.y2),
        class: "route",
        stroke: finished ? dormant : packageColor.IAC,
        "stroke-width": 4,
        opacity: finished ? 0.65 : 0.95
      }));
    });
  }

  function locations() {
    var byId = {};
    data.forEach(function (point) {
      if (point.package === "IAC") return;
      var place = byId[point.id];
      if (!place) {
        place = { id: point.id, x: point.x, y: point.y, fou: null, wtg: null };
        byId[point.id] = place;
      }
      if (point.package === "WTG") place.wtg = point;
      else place.fou = point;
      if (point.package !== "WTG") {
        place.x = point.x;
        place.y = point.y;
      }
    });
    return Object.keys(byId).map(function (id) { return byId[id]; });
  }

  function drawLocation(place) {
    var fouDone = place.fou && started(place.fou);
    var wtgDone = place.wtg && started(place.wtg);
    var on = (place.fou && installing(place.fou)) || (place.wtg && installing(place.wtg));
    var fill = dormant;
    if (wtgDone) fill = packageColor.WTG;
    else if (fouDone) fill = packageColor.FOU;
    var px = layout.X(place.x);
    var py = layout.Y(place.y);
    if (wtgDone) {
      var side = on ? 16 : 10;
      svg.appendChild(el("rect", {
        x: px - side / 2, y: py - side / 2, width: side, height: side,
        class: "point", fill: fill
      }));
    } else {
      svg.appendChild(el("circle", {
        cx: px, cy: py, r: on ? 8 : 5, class: "point", fill: fill
      }));
    }
    if (on) {
      svg.appendChild(el("circle", {
        cx: px, cy: py, r: 16, fill: "none", stroke: fill, "stroke-width": 3, opacity: 0.85
      }));
    }
    var seq = (place.fou && place.fou.seq) || (place.wtg && place.wtg.seq) || 1;
    var dx = seq % 2 ? 14 : -14;
    var anchor = seq % 2 ? "start" : "end";
    var installed = fouDone || wtgDone;
    var nameSize = installed ? 16 : 12;
    svg.appendChild(el("text", {
      x: px + dx, y: py - 12, "text-anchor": anchor, class: "label",
      style: "font-size:" + nameSize + "px"
    }, place.id));
    var lines = [];
    if (fouDone) lines.push("#" + place.fou.seq + " T" + place.fou.trip);
    if (wtgDone) lines.push("#" + place.wtg.seq + " T" + place.wtg.trip);
    lines.forEach(function (line, index) {
      svg.appendChild(el("text", {
        x: px + dx, y: py + 18 + index * 14, "text-anchor": anchor, class: "label",
        style: "font-size:12px"
      }, line));
    });
  }

  function statusText() {
    var text = formatDate(time);
    var names = [];
    data.forEach(function (point) {
      if (installing(point)) names.push(point.package + " " + point.id);
    });
    if (names.length) text += " · Installing " + names.join(", ");
    ["FOU", "IAC", "WTG"].forEach(function (packageName) {
      var rows = data.filter(function (point) { return point.package === packageName; });
      if (!rows.length) return;
      var complete = rows.filter(function (point) { return time >= point.end; }).length;
      text += " · " + packageName + " " + complete + "/" + rows.length + " complete";
    });
    return text;
  }

  function sliderValue() {
    if (horizon <= origin) return 0;
    return Math.round(((time - origin) / (horizon - origin)) * sliderMax);
  }

  function draw() {
    base();
    var grouped = groups();
    Object.keys(grouped).forEach(function (packageName) {
      if (packageName === "IAC") return;
      drawRoutes(grouped[packageName]);
    });
    drawCables();
    drawLabels();
    locations().forEach(drawLocation);
    document.getElementById("timelapse-status").textContent = statusText();
    document.getElementById("timelapse-slider").value = String(sliderValue());
  }

  function nextStart(after) {
    var found = null;
    data.forEach(function (point) {
      if (point.start > after && (found === null || point.start < found)) found = point.start;
    });
    return found;
  }

  function previousStart(before) {
    var found = null;
    data.forEach(function (point) {
      if (point.start < before && (found === null || point.start > found)) found = point.start;
    });
    return found;
  }

  function advance() {
    if (time >= horizon) {
      time = origin;
      draw();
      return;
    }
    var boundary = nextStart(time);
    var candidate = Math.min(horizon, time + pace);
    time = boundary !== null && boundary < candidate ? boundary : candidate;
    draw();
  }

  function schedule() {
    clearInterval(timer);
    if (playing) timer = setInterval(advance, delay);
  }

  document.getElementById("timelapse-play").onclick = function () {
    playing = !playing;
    document.getElementById("timelapse-play").textContent = playing ? "Pause" : "Play";
    schedule();
  };
  document.getElementById("timelapse-prev").onclick = function () {
    var boundary = previousStart(time);
    time = boundary === null ? origin : boundary;
    draw();
  };
  document.getElementById("timelapse-next").onclick = function () {
    var boundary = nextStart(time);
    time = boundary === null ? horizon : boundary;
    draw();
  };
  document.getElementById("timelapse-speed").onchange = function (event) {
    pace = (+event.target.value) * DAY;
  };
  var slider = document.getElementById("timelapse-slider");
  slider.max = String(sliderMax);
  slider.oninput = function (event) {
    var fraction = +event.target.value / sliderMax;
    time = origin + fraction * Math.max(horizon - origin, 0);
    draw();
  };
  var stage = document.getElementById("timelapse-stage");
  var fullscreenButton = document.getElementById("timelapse-fullscreen");
  function fullscreenElement() {
    return document.fullscreenElement || document.webkitFullscreenElement || null;
  }
  function syncFullscreenButton() {
    fullscreenButton.textContent = fullscreenElement() === stage ? "Exit full screen" : "Full screen";
  }
  fullscreenButton.onclick = function () {
    if (fullscreenElement() === stage) {
      if (document.exitFullscreen) document.exitFullscreen();
      else if (document.webkitExitFullscreen) document.webkitExitFullscreen();
      return;
    }
    if (stage.requestFullscreen) stage.requestFullscreen();
    else if (stage.webkitRequestFullscreen) stage.webkitRequestFullscreen();
  };
  document.addEventListener("fullscreenchange", syncFullscreenButton);
  document.addEventListener("webkitfullscreenchange", syncFullscreenButton);
  draw();
  schedule();
})();
