/* Calendar timelapse. One pizza per location and one per cable. Cable lines only. */
(function () {
  var node = document.getElementById("timelapse-data");
  var svg = document.getElementById("timelapse-map");
  if (!node || !svg) return;
  var payload = JSON.parse(node.textContent);
  var places = payload.places || [];
  var labels = payload.labels || [];
  if (!places.length) return;
  var origin = payload.origin;
  var horizon = payload.horizon;
  var NS = "http://www.w3.org/2000/svg";
  var DAY = 86400000;
  var time = origin;
  var playing = true;
  var timer = null;
  var delay = 400;
  var pace = DAY;
  var sliderMax = 1000;
  var layout = project(places);
  var laidGrey = "#b7c0ca";
  var buriedGrey = "#5c6770";
  var sliceOrder = [
    "MP Installed",
    "S St Installed",
    "Filter Layer",
    "Armour Layer",
    "IAC Lay",
    "IAC Burial",
    "WTG Installed",
    "WTG Commissioned"
  ];

  function el(tag, attrs, text) {
    var element = document.createElementNS(NS, tag);
    Object.keys(attrs).forEach(function (key) { element.setAttribute(key, attrs[key]); });
    if (text) element.textContent = text;
    return element;
  }

  function project(points) {
    var xs = [];
    var ys = [];
    points.forEach(function (point) {
      xs.push(point.x);
      ys.push(point.y);
      if (point.x1 != null && point.y1 != null) {
        xs.push(point.x1);
        ys.push(point.y1);
      }
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

  function wedge(cx, cy, radius, start, end) {
    var x0 = cx + radius * Math.cos(start);
    var y0 = cy + radius * Math.sin(start);
    var x1 = cx + radius * Math.cos(end);
    var y1 = cy + radius * Math.sin(end);
    var large = end - start > Math.PI ? 1 : 0;
    return "M " + cx + " " + cy + " L " + x0 + " " + y0
      + " A " + radius + " " + radius + " 0 " + large + " 1 " + x1 + " " + y1 + " Z";
  }

  function titled(element, text) {
    var title = document.createElementNS(NS, "title");
    title.textContent = text;
    element.appendChild(title);
    return element;
  }

  function drawPizza(place) {
    var slices = place.slices || [];
    if (!slices.length) return;
    var cx = layout.X(place.x);
    var cy = layout.Y(place.y);
    var radius = place.kind === "cable" ? 11 : 14;
    var installing = false;
    if (slices.length === 1) {
      var only = slices[0];
      installing = only.start <= time && time < only.end;
      svg.appendChild(titled(el("circle", {
        cx: cx, cy: cy, r: radius,
        fill: time >= only.end ? only.color : "#ffffff",
        stroke: "#c5ced6", "stroke-width": 1
      }), only.label));
    } else {
      slices.forEach(function (slice, index) {
        if (slice.start <= time && time < slice.end) installing = true;
        var start = -Math.PI / 2 + (index * 2 * Math.PI) / slices.length;
        var end = -Math.PI / 2 + ((index + 1) * 2 * Math.PI) / slices.length;
        svg.appendChild(titled(el("path", {
          d: wedge(cx, cy, radius, start, end),
          fill: time >= slice.end ? slice.color : "#ffffff",
          stroke: "#ffffff", "stroke-width": 1
        }), slice.label));
      });
      svg.appendChild(el("circle", {
        cx: cx, cy: cy, r: radius, fill: "none", stroke: "#c5ced6", "stroke-width": 1
      }));
    }
    if (installing && place.kind !== "cable") {
      svg.appendChild(el("circle", {
        cx: cx, cy: cy, r: radius + 5, fill: "none", stroke: "#172033", "stroke-width": 3
      }));
    }
    if (place.kind !== "cable") {
      svg.appendChild(el("text", {
        x: cx + radius + 6, y: cy + 4, "text-anchor": "start", class: "label"
      }, place.id));
    }
  }

  function sliceNamed(place, label) {
    var slices = place.slices || [];
    var index;
    for (index = 0; index < slices.length; index += 1) {
      if (slices[index].label === label) return slices[index];
    }
    return null;
  }

  function cableStyle(place) {
    var lay = sliceNamed(place, "IAC Lay");
    var burial = sliceNamed(place, "IAC Burial");
    var laying = lay && lay.start <= time && time < lay.end;
    var burying = burial && burial.start <= time && time < burial.end;
    if (burying) return { stroke: burial.color, opacity: 0.95, active: true };
    if (laying) return { stroke: lay.color, opacity: 0.95, active: true };
    if (burial && time >= burial.end) return { stroke: buriedGrey, opacity: 0.9, active: false };
    if (lay && time >= lay.end) return { stroke: laidGrey, opacity: 0.65, active: false };
    return null;
  }

  function drawCableLine(place, style) {
    svg.appendChild(el("line", {
      x1: layout.X(place.x1), y1: layout.Y(place.y1),
      x2: layout.X(place.x2), y2: layout.Y(place.y2),
      class: "route",
      stroke: style.stroke,
      "stroke-width": 4,
      opacity: style.opacity
    }));
  }

  function drawCables() {
    var active = [];
    places.forEach(function (place) {
      if (place.kind !== "cable" || place.x1 == null || place.x2 == null) return;
      var style = cableStyle(place);
      if (!style) return;
      if (style.active) active.push({ place: place, style: style });
      else drawCableLine(place, style);
    });
    active.forEach(function (item) { drawCableLine(item.place, item.style); });
  }

  function drawLabels() {
    labels.forEach(function (label) {
      svg.appendChild(el("text", {
        x: layout.X(label.x), y: layout.Y(label.y),
        "text-anchor": "middle", class: "label"
      }, label.id));
    });
  }

  function counts() {
    var seen = {};
    places.forEach(function (place) {
      place.slices.forEach(function (slice) {
        if (!seen[slice.label]) seen[slice.label] = { color: slice.color, total: 0, done: 0 };
        seen[slice.label].total += 1;
        if (time >= slice.end) seen[slice.label].done += 1;
      });
    });
    return seen;
  }

  function legend() {
    var host = document.getElementById("timelapse-legend");
    if (!host) return;
    host.textContent = "";
    var seen = counts();
    sliceOrder.forEach(function (label) {
      var item = seen[label];
      if (!item) return;
      var row = document.createElement("span");
      var swatch = document.createElement("span");
      swatch.style.display = "inline-block";
      swatch.style.width = "0.75em";
      swatch.style.height = "0.75em";
      swatch.style.marginRight = "0.35em";
      swatch.style.background = item.color;
      swatch.style.verticalAlign = "middle";
      row.appendChild(swatch);
      row.appendChild(document.createTextNode(label + " " + item.done + "/" + item.total));
      host.appendChild(row);
    });
  }

  function statusText() {
    var text = formatDate(time);
    var names = [];
    places.forEach(function (place) {
      place.slices.forEach(function (slice) {
        if (slice.start <= time && time < slice.end) names.push(slice.label + " " + place.id);
      });
    });
    if (names.length) text += " · " + names.join(", ");
    return text;
  }

  function sliderValue() {
    if (horizon <= origin) return 0;
    return Math.round(((time - origin) / (horizon - origin)) * sliderMax);
  }

  function draw() {
    base();
    drawCables();
    drawLabels();
    places.forEach(drawPizza);
    legend();
    document.getElementById("timelapse-status").textContent = statusText();
    document.getElementById("timelapse-slider").value = String(sliderValue());
  }

  function nextStart(after) {
    var found = null;
    places.forEach(function (place) {
      place.slices.forEach(function (slice) {
        if (slice.start > after && (found === null || slice.start < found)) found = slice.start;
      });
    });
    return found;
  }

  function previousStart(before) {
    var found = null;
    places.forEach(function (place) {
      place.slices.forEach(function (slice) {
        if (slice.start < before && (found === null || slice.start > found)) found = slice.start;
      });
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
