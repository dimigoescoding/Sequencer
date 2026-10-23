/* Installation timelapse. Within-trip legs only. Equal easting/northing scale. */
(function () {
  var node = document.getElementById("timelapse-data");
  var svg = document.getElementById("timelapse-map");
  if (!node || !svg) return;
  var data = JSON.parse(node.textContent);
  if (!data.length) return;
  var NS = "http://www.w3.org/2000/svg";
  var colors = [
    "#1f77b4", "#aec7e8", "#ff7f0e", "#ffbb78", "#2ca02c", "#98df8a",
    "#d62728", "#ff9896", "#9467bd", "#c5b0d5", "#8c564b", "#c49c94",
    "#e377c2", "#f7b6d2", "#7f7f7f", "#c7c7c7", "#bcbd22", "#dbdb8d",
    "#17becf", "#9edae5"
  ];
  data.forEach(function (point) {
    point.color = colors[(point.trip - 1) % colors.length];
  });
  var frame = 0;
  var playing = true;
  var timer = null;
  var delay = 600;
  var layout = project(data);

  function el(tag, attrs, text) {
    var node = document.createElementNS(NS, tag);
    Object.keys(attrs).forEach(function (key) { node.setAttribute(key, attrs[key]); });
    if (text) node.textContent = text;
    return node;
  }

  function project(points) {
    var minX = Math.min.apply(null, points.map(function (p) { return p.x; }));
    var maxX = Math.max.apply(null, points.map(function (p) { return p.x; }));
    var minY = Math.min.apply(null, points.map(function (p) { return p.y; }));
    var maxY = Math.max.apply(null, points.map(function (p) { return p.y; }));
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

  function step(span) {
    var rough = span / 6;
    if (rough <= 0) return 1;
    var power = Math.pow(10, Math.floor(Math.log10(rough)));
    var fraction = rough / power;
    var factor = fraction >= 7.5 ? 10 : fraction >= 3.5 ? 5 : fraction >= 1.5 ? 2 : 1;
    return factor * power;
  }

  function base() {
    svg.innerHTML = "";
    var xStep = step(layout.maxX - layout.minX);
    var yStep = step(layout.maxY - layout.minY);
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

  function draw() {
    base();
    var shown = data.slice(0, frame + 1);
    var active = shown[shown.length - 1].trip;
    var i;
    for (i = 1; i < shown.length; i += 1) {
      var previous = shown[i - 1];
      var current = shown[i];
      if (previous.trip !== current.trip) continue;
      var faded = current.trip !== active;
      svg.appendChild(el("line", {
        x1: layout.X(previous.x), y1: layout.Y(previous.y),
        x2: layout.X(current.x), y2: layout.Y(current.y),
        class: "route",
        stroke: faded ? "#718096" : current.color,
        "stroke-width": faded ? 2 : 5,
        opacity: faded ? 0.15 : 0.95
      }));
    }
    shown.forEach(function (point, index) {
      var px = layout.X(point.x);
      var py = layout.Y(point.y);
      var latest = index === shown.length - 1;
      svg.appendChild(el("circle", {
        cx: px, cy: py, r: latest ? 8 : 5, class: "point", fill: point.color
      }));
      if (latest) {
        svg.appendChild(el("circle", {
          cx: px, cy: py, r: 14, fill: "none", stroke: point.color, "stroke-width": 3, opacity: 0.8
        }));
      }
      var dx = point.seq % 2 ? 9 : -9;
      var anchor = point.seq % 2 ? "start" : "end";
      var dy = point.seq % 3 ? -9 : 15;
      svg.appendChild(el("text", {
        x: px + dx, y: py + dy, "text-anchor": anchor, class: "label"
      }, point.id + "  #" + point.seq + "  T" + point.trip));
    });
    var point = shown[shown.length - 1];
    document.getElementById("timelapse-status").textContent =
      "Installed " + point.seq + "/" + data.length + " · Trip " + point.trip + " · " + point.id;
    document.getElementById("timelapse-slider").value = String(frame + 1);
  }

  function schedule() {
    clearInterval(timer);
    if (playing) {
      timer = setInterval(function () {
        frame = (frame + 1) % data.length;
        draw();
      }, delay);
    }
  }

  document.getElementById("timelapse-play").onclick = function () {
    playing = !playing;
    document.getElementById("timelapse-play").textContent = playing ? "Pause" : "Play";
    schedule();
  };
  document.getElementById("timelapse-prev").onclick = function () {
    frame = Math.max(0, frame - 1);
    draw();
  };
  document.getElementById("timelapse-next").onclick = function () {
    frame = Math.min(data.length - 1, frame + 1);
    draw();
  };
  document.getElementById("timelapse-speed").onchange = function (event) {
    delay = +event.target.value;
    schedule();
  };
  document.getElementById("timelapse-slider").oninput = function (event) {
    frame = +event.target.value - 1;
    draw();
  };
  document.getElementById("timelapse-slider").max = String(data.length);
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
      if (document.exitFullscreen) {
        document.exitFullscreen();
      } else if (document.webkitExitFullscreen) {
        document.webkitExitFullscreen();
      }
      return;
    }
    if (stage.requestFullscreen) {
      stage.requestFullscreen();
    } else if (stage.webkitRequestFullscreen) {
      stage.webkitRequestFullscreen();
    }
  };
  document.addEventListener("fullscreenchange", syncFullscreenButton);
  document.addEventListener("webkitfullscreenchange", syncFullscreenButton);
  draw();
  schedule();
})();
