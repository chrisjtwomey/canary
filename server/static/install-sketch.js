/* The device as a sketch on the install page, so a person can tell which
   board is which: the display in its cradle on the dock. Beside the
   board list it has a line from each part to the row that installs it; on a
   narrow screen it sits above the list, with each part named. rough.js draws
   it, as it draws the charts. Runs after epd's install.js has drawn the
   list. */
(function () {
  'use strict';

  var NS = 'http://www.w3.org/2000/svg';
  var SEED = 7;
  var INK = '#000000';
  var SOFT = '#494949';
  var MID = '#929292';
  var FAINT = '#b6b6b6';
  var PAPER = '#ffffff';
  var GAP = 84;      // between the list and the sketch, where the lines run
  var BESIDE = 1.3;  // how much larger the sketch is beside the list than above it

  var LINE = { stroke: INK, strokeWidth: 1.7, roughness: 1.7, bowing: 1.6 };
  var THIN = { stroke: SOFT, strokeWidth: 1.2, roughness: 1.6, bowing: 1.4 };
  var SOLID = { stroke: INK, strokeWidth: 1.7, roughness: 1.7, bowing: 1.6,
                fill: PAPER, fillStyle: 'solid' };
  var SLOT = { stroke: INK, strokeWidth: 1, roughness: 1.2, fill: SOFT, fillStyle: 'solid' };
  var DOT = { stroke: INK, fill: INK, fillStyle: 'solid', roughness: 0.6 };
  var LEADER = { stroke: SOFT, strokeWidth: 1.5, roughness: 0.7, bowing: 0.4 };

  function hatched(gap, angle, colour) {
    return { stroke: INK, strokeWidth: 1.7, roughness: 1.7, bowing: 1.6, fill: colour,
             fillStyle: 'hachure', hachureGap: gap, hachureAngle: angle, fillWeight: 0.7 };
  }

  // The sketch is traced from the render in hardware/images/device.png, the
  // device seen from its front left: P maps the render's pixels to its own.
  var S = 0.27;
  var M = 10;
  function P(x, y) { return [(x - 150) * S + M, (y - 55) * S + M]; }
  var W = Math.round(1060 * S + 2 * M);
  var H = Math.round(860 * S + 2 * M + 14);

  var main = document.getElementById('install');
  var list = main && main.querySelector('ul.boards');
  if (!list || typeof rough === 'undefined') return;
  var boards = JSON.parse(document.getElementById('install-config').textContent).boards;

  // Where each part's line ends, and where its name goes on a narrow screen.
  var PARTS = {
    'canary-display': { name: 'Display', at: P(393, 614), label: P(330, 205), anchor: 'end' },
    'canary-dock': { name: 'Dock', at: P(400, 840), label: P(500, 960), anchor: 'start' }
  };

  var svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('class', 'sketch');
  svg.setAttribute('aria-hidden', 'true');
  list.parentNode.insertBefore(svg, list);

  function text(part) {
    var t = document.createElementNS(NS, 'text');
    t.setAttribute('x', part.label[0]);
    t.setAttribute('y', part.label[1]);
    t.setAttribute('text-anchor', part.anchor);
    t.textContent = part.name;
    return t;
  }

  function polygon(points) { return points.map(function (p) { return P(p[0], p[1]); }); }

  // A closed path through points with each corner rounded by radius r.
  function rounded(points, r) {
    function toward(from, to) {
      var dx = to[0] - from[0], dy = to[1] - from[1], len = Math.hypot(dx, dy);
      var t = Math.min(r, len / 2) / len;
      return [from[0] + dx * t, from[1] + dy * t];
    }
    var d = '';
    points.forEach(function (p, i) {
      var a = toward(p, points[(i + points.length - 1) % points.length]);
      var b = toward(p, points[(i + 1) % points.length]);
      d += (i ? 'L' : 'M') + a.join(' ') + 'Q' + p.join(' ') + ' ' + b.join(' ');
    });
    return d + 'Z';
  }

  // A point on the screen, as a fraction across it and down it.
  function onScreen(u, v) {
    var tl = [425, 265], tr = [1045, 110], bl = [535, 715], br = [1105, 470];
    var top = [tl[0] + (tr[0] - tl[0]) * u, tl[1] + (tr[1] - tl[1]) * u];
    var bottom = [bl[0] + (br[0] - bl[0]) * u, bl[1] + (br[1] - bl[1]) * u];
    return P(top[0] + (bottom[0] - top[0]) * v, top[1] + (bottom[1] - top[1]) * v);
  }

  // A vent slot in the dock's left end, from its top corner.
  function slot(x) {
    var top = 545 + 0.74 * (x - 155) + 40;
    return rounded(polygon([[x, top], [x + 9, top + 7], [x + 9, top + 102], [x, top + 95]]), 1.5);
  }

  // The device's shadow on the desk, along the dock's front.
  function shadow(rs, g) {
    g.appendChild(rs.polygon(polygon([[470, 915], [1205, 600], [1285, 618], [560, 948]]),
                             { stroke: 'none', fill: MID, fillStyle: 'hachure', hachureGap: 5,
                               hachureAngle: -20, fillWeight: 0.6, roughness: 1.8 }));
  }

  // The display, leaning back: the left side of its frame with its USB port,
  // its face, the bezel round the screen, and a page on the screen.
  function display(rs, g) {
    g.appendChild(rs.path(rounded(polygon([[285, 250], [335, 235], [468, 805], [400, 700]]), 4),
                          hatched(4, 70, SOFT)));
    g.appendChild(rs.path(rounded(polygon([[376, 585], [396, 580], [410, 642], [390, 648]]), 1.5),
                          SOLID));
    g.appendChild(rs.path(rounded(polygon([[335, 235], [1105, 55], [1200, 515], [468, 805]]), 9),
                          SOLID));
    g.appendChild(rs.path(rounded([onScreen(-0.03, -0.05), onScreen(1.03, -0.05),
                                   onScreen(1.03, 1.04), onScreen(-0.03, 1.04)], 5), THIN));
    g.appendChild(rs.path(rounded([onScreen(0, 0), onScreen(1, 0), onScreen(1, 1),
                                   onScreen(0, 1)], 3),
                          { stroke: SOFT, strokeWidth: 1.3, roughness: 1.6, fill: FAINT,
                            fillStyle: 'hachure', hachureGap: 6, hachureAngle: 50,
                            fillWeight: 0.6 }));
    g.appendChild(rs.line.apply(rs, onScreen(0.06, 0.12).concat(onScreen(0.32, 0.12), [LINE])));
    g.appendChild(rs.line.apply(rs, onScreen(0.06, 0.22).concat(onScreen(0.2, 0.22), [THIN])));
    var trace = [[0.06, 0.82], [0.16, 0.66], [0.26, 0.72], [0.38, 0.48], [0.5, 0.58],
                 [0.62, 0.36], [0.74, 0.44], [0.86, 0.26], [0.94, 0.3]];
    g.appendChild(rs.curve(trace.map(function (p) { return onScreen(p[0], p[1]); }),
                           { stroke: INK, strokeWidth: 2, roughness: 1.4 }));
    g.appendChild(rs.circle.apply(rs, onScreen(0.94, 0.3).concat([7, DOT])));
  }

  // The dock: its top behind the display, its left end with two banks of
  // vents, and its front with the lip of the cradle, the name plate and the
  // light.
  function dock(rs, g) {
    g.appendChild(rs.path(rounded(polygon([[155, 545], [345, 485], [400, 700], [445, 760]]), 6),
                          SOLID));
    g.appendChild(rs.path(rounded(polygon([[155, 545], [445, 760], [470, 915], [160, 690]]), 7),
                          hatched(7, -35, MID)));
    [188, 204, 220, 236, 270, 286, 302].forEach(function (x) {
      g.appendChild(rs.path(slot(x), SLOT));
    });
    g.appendChild(rs.path(rounded(polygon([[445, 760], [1195, 500], [1205, 600], [470, 915]]), 7),
                          SOLID));
    g.appendChild(rs.line.apply(rs, P(452, 800).concat(P(1198, 535), [THIN])));
    var at = P(875, 712);
    var plate = rs.ellipse(at[0], at[1], 196 * S, 56 * S, LINE);
    plate.setAttribute('transform', 'rotate(-23 ' + at.join(' ') + ')');
    g.appendChild(plate);
    g.appendChild(rs.circle.apply(rs, P(1125, 595).concat([54 * S, LINE])));
    g.appendChild(rs.circle.apply(rs, P(1125, 595).concat([26 * S, THIN])));
  }

  // The whole device. The dock is drawn after the display, over the frame's
  // foot, as the cradle hides it.
  function device(rs, g) {
    shadow(rs, g);
    display(rs, g);
    dock(rs, g);
  }

  // A line from a row, at height y, to a part, as a diagram's callout has:
  // level from the row's arrow, then one bend to run at 45 degrees.
  function leader(rs, y, end) {
    var bend = Math.max(30, end[0] - Math.abs(end[1] - y));
    svg.appendChild(rs.linearPath([[12, y], [bend, y], end], LEADER));
    svg.appendChild(rs.line(12, y, 22, y - 6, LEADER));
    svg.appendChild(rs.line(12, y, 22, y + 6, LEADER));
    svg.appendChild(rs.circle(end[0], end[1], 6, DOT));
  }

  // Where the sketch goes beside the rows, in main's coordinates: level with
  // the top of the network form when the page has one, in the space beside
  // it, else centred on the rows, but never above main's own top.
  function placeBeside(box, rows, k) {
    var form = document.getElementById('network-form');
    var rowsTop = rows.top - box.top;
    var sketchTop = form ? form.getBoundingClientRect().top - box.top
                         : Math.max(0, rowsTop + rows.height / 2 - H * k / 2);
    var svgTop = Math.min(rowsTop, sketchTop);
    return { svgTop: svgTop, sketchTop: sketchTop,
             height: Math.max(rowsTop + rows.height, sketchTop + H * k) - svgTop };
  }

  function draw() {
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    var rs = rough.svg(svg, { options: { seed: SEED } });
    var box = main.getBoundingClientRect();
    var rows = list.getBoundingClientRect();
    var beside = box.width >= rows.right - box.left + GAP + W * BESIDE;
    var k = beside ? BESIDE : 1;
    var at = placeBeside(box, rows, k);

    svg.classList.toggle('beside', beside);
    svg.setAttribute('width', beside ? GAP + W * k : W);
    svg.setAttribute('height', beside ? at.height : H);
    svg.style.left = beside ? (rows.right - box.left) + 'px' : '';
    svg.style.top = beside ? at.svgTop + 'px' : '';

    var x0 = beside ? GAP : 0;
    var y0 = beside ? at.sketchTop - at.svgTop : 0;
    var g = document.createElementNS(NS, 'g');
    g.setAttribute('transform', 'translate(' + x0 + ',' + y0 + ') scale(' + k + ')');
    device(rs, g);
    svg.appendChild(g);

    var items = list.children;
    boards.forEach(function (board, i) {
      var part = PARTS[board.product];
      var row = items[i] && items[i].querySelector('.board');
      if (!part || !row) return;
      if (!beside) {
        g.appendChild(text(part));
        return;
      }
      var r = row.getBoundingClientRect();
      leader(rs, r.top + r.height / 2 - box.top - at.svgTop,
             [x0 + part.at[0] * k, y0 + part.at[1] * k]);
    });
  }

  var queued = false;
  function redraw() {
    if (queued) return;
    queued = true;
    requestAnimationFrame(function () { queued = false; draw(); });
  }

  draw();
  window.addEventListener('resize', redraw);
  if (window.ResizeObserver) new ResizeObserver(redraw).observe(list);
  if (document.fonts) document.fonts.ready.then(redraw);
})();
