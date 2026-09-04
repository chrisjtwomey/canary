/* Draws the charts a page declares, with rough.js for the hand-drawn look.
   A page hands over a list of specs in a JSON <script>; each names its
   canvas and kind. Canvases are sized from their CSS box, and the page is
   rendered at device scale 1, so one CSS pixel is one panel pixel. */
(function () {
  'use strict';

  var G = ['#000000', '#242424', '#494949', '#6d6d6d',
           '#929292', '#b6b6b6', '#dbdbdb', '#ffffff'];
  var FONT = 'Fraunces';
  var SEED = 7;

  function prepare(canvas) {
    var r = canvas.getBoundingClientRect();
    canvas.width = Math.round(r.width);
    canvas.height = Math.round(r.height);
    return {
      w: canvas.width,
      h: canvas.height,
      ctx: canvas.getContext('2d'),
      rc: rough.canvas(canvas, { options: { seed: SEED } })
    };
  }

  function linear(d0, d1, r0, r1) {
    var k = (r1 - r0) / ((d1 - d0) || 1);
    return function (v) { return r0 + (v - d0) * k; };
  }

  function label(ctx, s, x, y, o) {
    o = o || {};
    ctx.save();
    ctx.font = (o.italic ? 'italic ' : '') + (o.weight || 500) + ' ' +
               (o.size || 18) + 'px ' + FONT;
    ctx.fillStyle = o.color || G[2];
    ctx.textAlign = o.align || 'left';
    ctx.textBaseline = o.baseline || 'alphabetic';
    ctx.fillText(s, x, y);
    ctx.restore();
  }

  function dot(ctx, x, y, r, color) {
    ctx.save();
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();
    ctx.restore();
  }

  function marker(c, x, y) {
    dot(c.ctx, x, y, 12, G[7]);
    dot(c.ctx, x, y, 8, G[0]);
    c.rc.circle(x, y, 40, { stroke: G[0], strokeWidth: 2, roughness: 1.4, fill: 'none' });
  }

  function area(c, pts, y0, color, gap) {
    if (pts.length < 2) return;
    var poly = pts.slice();
    poly.push([pts[pts.length - 1][0], y0]);
    poly.push([pts[0][0], y0]);
    c.rc.polygon(poly, {
      fill: color, fillStyle: 'hachure', hachureGap: gap || 9, hachureAngle: -40,
      fillWeight: 1.2, stroke: 'none', roughness: 0.8
    });
  }

  function line(c, pts, width) {
    if (pts.length < 2) return;
    c.rc.curve(pts, {
      stroke: G[0], strokeWidth: width || 3, roughness: 0.7, bowing: 0.4,
      disableMultiStroke: true
    });
  }

  function sparkline(canvas, s) {
    var c = prepare(canvas);
    var m = { l: 12, r: 30, t: 30, b: 36 };
    var X = linear(s.x.min, s.x.max, m.l, c.w - m.r);
    var Y = linear(s.y.min, s.y.max, c.h - m.b, m.t);
    var pts = s.points.map(function (p) { return [X(p[0]), Y(p[1])]; });

    (s.guides || []).forEach(function (g) {
      var y = Y(g.y);
      c.rc.line(m.l, y, c.w - m.r, y, {
        stroke: G[4], strokeWidth: 1.5, roughness: 0.6, strokeLineDash: [9, 8]
      });
      label(c.ctx, g.label, c.w - m.r, y - 6, { size: 17, italic: true, color: G[3], align: 'right' });
    });

    area(c, pts, c.h - m.b, G[4]);
    line(c, pts, 3);

    (s.ticks || []).forEach(function (t) {
      var x = X(t.x);
      c.rc.line(x, c.h - m.b, x, c.h - m.b + 8, { stroke: G[2], strokeWidth: 1.5, roughness: 0.5 });
      label(c.ctx, t.label, x, c.h - 8, { size: 18, align: 'center' });
    });

    if (s.now) marker(c, X(s.now[0]), Y(s.now[1]));
  }

  function comfort(canvas, s) {
    var c = prepare(canvas);
    var m = { l: 60, r: 20, t: 20, b: 50 };
    var X = linear(s.x.min, s.x.max, m.l, c.w - m.r);
    var Y = linear(s.y.min, s.y.max, c.h - m.b, m.t);

    s.zones.forEach(function (z) {
      var x0 = X(z.t[0]), x1 = X(z.t[1]), y0 = Y(z.rh[1]), y1 = Y(z.rh[0]);
      c.rc.rectangle(x0, y0, x1 - x0, y1 - y0, {
        fill: z.color, fillStyle: 'hachure', hachureGap: z.gap, hachureAngle: 45,
        fillWeight: 1, stroke: z.color, strokeWidth: 1.5, roughness: 1.6, bowing: 1.2
      });
    });

    c.rc.line(m.l, m.t, m.l, c.h - m.b, { stroke: G[2], strokeWidth: 2, roughness: 0.8 });
    c.rc.line(m.l, c.h - m.b, c.w - m.r, c.h - m.b, { stroke: G[2], strokeWidth: 2, roughness: 0.8 });
    s.xticks.forEach(function (t) {
      label(c.ctx, t + '°', X(t), c.h - m.b + 32, { size: 20, align: 'center' });
    });
    s.yticks.forEach(function (t) {
      label(c.ctx, t + '%', m.l - 12, Y(t) + 7, { size: 20, align: 'right' });
    });

    var n = s.trail.length;
    s.trail.forEach(function (p, i) {
      var shade = G[5 - Math.round(3 * i / Math.max(1, n - 1))];
      dot(c.ctx, X(p[0]), Y(p[1]), 4, shade);
    });
    if (s.now) marker(c, X(s.now[0]), Y(s.now[1]));
  }

  function ribbon(canvas, s) {
    var c = prepare(canvas);
    var m = { l: 4, r: 24, t: 12, b: 6 };
    var X = linear(s.x.min, s.x.max, m.l, c.w - m.r);
    var Y = linear(s.y.min, s.y.max, c.h - m.b, m.t);

    (s.nights || []).forEach(function (nt) {
      c.ctx.fillStyle = G[6];
      c.ctx.fillRect(X(nt[0]), 0, X(nt[1]) - X(nt[0]), c.h - m.b);
    });

    var pts = s.points.map(function (p) { return [X(p[0]), Y(p[1])]; });
    area(c, pts, c.h - m.b, G[4], 10);
    line(c, pts, 2.5);
    c.rc.line(m.l, c.h - m.b, c.w - m.r, c.h - m.b, { stroke: G[3], strokeWidth: 1.5, roughness: 0.6 });
    if (s.now) dot(c.ctx, X(s.now[0]), Y(s.now[1]), 6, G[0]);
  }

  function axis(canvas, s) {
    var c = prepare(canvas);
    var m = { l: 4, r: 24 };
    var X = linear(s.x.min, s.x.max, m.l, c.w - m.r);
    s.ticks.forEach(function (t) {
      var x = X(t.x);
      c.rc.line(x, 0, x, 8, { stroke: G[2], strokeWidth: 1.5, roughness: 0.5 });
      label(c.ctx, t.label, x, 30, { size: 18, align: 'center' });
    });
  }

  function mulberry32(a) {
    return function () {
      a |= 0; a = a + 0x6D2B79F5 | 0;
      var t = Math.imul(a ^ a >>> 15, 1 | a);
      t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    };
  }

  // Particle counts as a cloud: one dot each, bigger and darker for the
  // larger size bins, denser towards the middle.
  function dotcloud(canvas, s) {
    var c = prepare(canvas);
    var rnd = mulberry32(s.seed || SEED);
    var cx = c.w / 2, cy = c.h / 2, rx = c.w / 2 - 14, ry = c.h / 2 - 14;
    s.dots.forEach(function (d) {
      for (var i = 0; i < d.n; i++) {
        var u = rnd() + rnd() - 1, v = rnd() + rnd() - 1;
        var x = cx + u * rx, y = cy + v * ry;
        if (d.rough) {
          c.rc.circle(x, y, d.r * 2, { stroke: d.color, strokeWidth: 1.5, fill: d.color,
            fillStyle: 'hachure', hachureGap: 3, roughness: 1.2 });
        } else {
          dot(c.ctx, x, y, d.r, d.color);
        }
      }
    });
  }

  // A banded scale with a marker: the IAQ index on Bosch's zones.
  function scale_(canvas, s) {
    var c = prepare(canvas);
    var m = { l: 12, r: 12, t: 30, b: 46 };
    var X = linear(s.min, s.max, m.l, c.w - m.r);
    var y0 = m.t, h = c.h - m.t - m.b;
    s.zones.forEach(function (z) {
      c.rc.rectangle(X(z.from), y0, X(z.to) - X(z.from), h, { fill: z.color, fillStyle: 'hachure',
        hachureGap: z.gap, hachureAngle: 45, fillWeight: 1, stroke: G[2], strokeWidth: 1.2, roughness: 1 });
      label(c.ctx, z.label, (X(z.from) + X(z.to)) / 2, y0 + h + 40,
        { size: 16, align: 'center', italic: true, color: G[3] });
    });
    (s.ticks || []).forEach(function (t) {
      label(c.ctx, String(t), X(t), y0 + h + 20, { size: 15, align: 'center', color: G[3] });
    });
    if (s.value != null) {
      var x = X(Math.max(s.min, Math.min(s.max, s.value)));
      c.rc.polygon([[x, y0 - 3], [x - 11, y0 - 24], [x + 11, y0 - 24]],
        { fill: G[0], fillStyle: 'solid', stroke: G[0], strokeWidth: 1.5, roughness: 1 });
      c.rc.line(x, y0, x, y0 + h, { stroke: G[0], strokeWidth: 3, roughness: 0.6 });
    }
  }

  // An aneroid barometer's dial. The set needle is where the pressure was
  // three hours ago, so the gap between the needles is the tendency.
  function dial(canvas, s) {
    var c = prepare(canvas);
    var cx = c.w / 2, cy = c.h * 0.56;
    var R = Math.min(c.w / 2, c.h * 0.56) - 14;
    var a0 = 215, a1 = -35;
    function ang(v) { return (a0 + (v - s.min) / (s.max - s.min) * (a1 - a0)) * Math.PI / 180; }
    function pt(v, r) { var a = ang(v); return [cx + r * Math.cos(a), cy - r * Math.sin(a)]; }

    var arc = [];
    for (var i = 0; i <= 120; i++) arc.push(pt(s.min + (s.max - s.min) * i / 120, R));
    c.rc.curve(arc, { stroke: G[0], strokeWidth: 2.5, roughness: 0.8, disableMultiStroke: true });

    for (var t = s.min; t <= s.max; t += s.tick) {
      var major = s.labels.indexOf(t) >= 0;
      var p1 = pt(t, R), p2 = pt(t, R - (major ? 20 : 11));
      c.rc.line(p1[0], p1[1], p2[0], p2[1], { stroke: G[0], strokeWidth: major ? 2 : 1.2, roughness: 0.5 });
    }
    s.labels.forEach(function (v) {
      var p = pt(v, R - 44);
      label(c.ctx, String(v), p[0], p[1] + 7, { size: 20, align: 'center' });
    });
    (s.legends || []).forEach(function (l) {
      var p = pt(l[0], R - 100);
      label(c.ctx, l[1], p[0], p[1] + 7, { size: 22, align: 'center', italic: true, color: G[2] });
    });

    if (s.set != null) {
      var q = pt(s.set, R - 24);
      c.rc.line(cx, cy, q[0], q[1], { stroke: G[3], strokeWidth: 2, roughness: 0.6, strokeLineDash: [7, 5] });
      c.rc.circle(q[0], q[1], 14, { stroke: G[3], strokeWidth: 1.5, fill: 'none', roughness: 1 });
    }
    if (s.value != null) {
      var n = pt(s.value, R - 24), tail = pt(s.value, -R * 0.16);
      c.rc.line(tail[0], tail[1], n[0], n[1], { stroke: G[0], strokeWidth: 4, roughness: 0.5 });
    }
    dot(c.ctx, cx, cy, 10, G[0]);
    dot(c.ctx, cx, cy, 4, G[7]);
  }

  // A hatched fraction of a box.
  function meter(canvas, s) {
    var c = prepare(canvas);
    var m = 3, w = c.w - 2 * m, h = c.h - 2 * m;
    c.rc.rectangle(m, m, w, h, { stroke: G[2], strokeWidth: 1.5, roughness: 1, fill: 'none' });
    var f = Math.max(0, Math.min(1, s.fraction));
    if (f > 0) {
      c.rc.rectangle(m, m, w * f, h, { fill: G[2], fillStyle: 'hachure', hachureGap: 6,
        fillWeight: 1.2, stroke: 'none', roughness: 1 });
    }
  }

  // Signal strength as rising bars, the first `filled` of them solid.
  function bars(canvas, s) {
    var c = prepare(canvas);
    var n = s.total, gap = 6, bw = (c.w - gap * (n - 1)) / n;
    for (var i = 0; i < n; i++) {
      var bh = c.h * (0.35 + 0.65 * i / (n - 1));
      var x = i * (bw + gap), y = c.h - bh;
      c.rc.rectangle(x, y, bw, bh, i < s.filled
        ? { fill: G[0], fillStyle: 'solid', stroke: G[0], roughness: 0.8 }
        : { fill: 'none', stroke: G[4], strokeWidth: 1.2, roughness: 0.8 });
    }
  }

  // Days of pressure as a barograph trace: the dial's legends as faint
  // bands, a rule at each midnight, the last hours drawn heavier.
  function barograph(canvas, s) {
    var c = prepare(canvas);
    var m = { l: 64, r: 44, t: 16, b: 40 };
    var X = linear(s.x.min, s.x.max, m.l, c.w - m.r);
    var Y = linear(s.y.min, s.y.max, c.h - m.b, m.t);
    (s.zones || []).forEach(function (z) {
      if (z.from > s.y.min && z.from < s.y.max) {
        var y = Y(z.from);
        c.rc.line(m.l, y, c.w - m.r, y, { stroke: G[4], strokeWidth: 1.5, roughness: 0.6, strokeLineDash: [9, 8] });
      }
      var mid = (Math.max(z.from, s.y.min) + Math.min(z.to, s.y.max)) / 2;
      if (z.from < s.y.max && z.to > s.y.min) {
        label(c.ctx, z.label, c.w - m.r - 6, Y(mid) + 6, { size: 17, italic: true, align: 'right', color: G[3] });
      }
    });
    (s.days || []).forEach(function (d) {
      var x = X(d.x);
      c.rc.line(x, m.t, x, c.h - m.b, { stroke: G[4], strokeWidth: 1.2, roughness: 0.5, strokeLineDash: [6, 6] });
    });
    (s.dayLabels || []).forEach(function (d) {
      label(c.ctx, d.label, X(d.x), c.h - 10, { size: 18, align: 'center' });
    });
    (s.yticks || []).forEach(function (v) {
      c.rc.line(m.l - 6, Y(v), m.l, Y(v), { stroke: G[3], strokeWidth: 1.2, roughness: 0.4 });
      label(c.ctx, String(v), m.l - 12, Y(v) + 6, { size: 15, align: 'right', color: G[3] });
    });
    c.rc.line(m.l, c.h - m.b, c.w - m.r, c.h - m.b, { stroke: G[3], strokeWidth: 1.5, roughness: 0.6 });
    line(c, s.points.map(function (p) { return [X(p[0]), Y(p[1])]; }), 2.5);
    if (s.recent && s.recent.length > 1) {
      line(c, s.recent.map(function (p) { return [X(p[0]), Y(p[1])]; }), 5);
    }
    if (s.set) {
      c.rc.circle(X(s.set[0]), Y(s.set[1]), 16, { stroke: G[2], strokeWidth: 1.5, fill: 'none', roughness: 1 });
    }
    if (s.now) marker(c, X(s.now[0]), Y(s.now[1]));
  }

  // The WMO pressure-tendency symbol: two legs, one per half of the window.
  function tendency(canvas, s) {
    var c = prepare(canvas);
    var pad = 50, w = c.w - 2 * pad, h = c.h - 2 * pad - 30;
    var lvl = { rising: 1, steady: 0, falling: -1 };
    var l1 = lvl[s.first], l2 = lvl[s.second];
    var x0 = pad, y0 = pad + h / 2 + (l1 + l2) * h / 6;
    var p1 = [x0 + w / 2, y0 - l1 * h / 3];
    var p2 = [p1[0] + w / 2, p1[1] - l2 * h / 3];
    c.rc.linearPath([[x0, y0], p1, p2], { stroke: G[0], strokeWidth: 10, roughness: 1.2, bowing: 1 });
    var dx = p2[0] - p1[0], dy = p2[1] - p1[1], L = Math.hypot(dx, dy);
    dx /= L; dy /= L;
    var a = 30;
    c.rc.polygon([
      [p2[0], p2[1]],
      [p2[0] - a * dx + a * 0.55 * dy, p2[1] - a * dy - a * 0.55 * dx],
      [p2[0] - a * dx - a * 0.55 * dy, p2[1] - a * dy + a * 0.55 * dx]
    ], { fill: G[0], fillStyle: 'solid', stroke: G[0], roughness: 1 });
    label(c.ctx, 'three hours ago', x0, c.h - 12, { size: 18, italic: true, color: G[3] });
    label(c.ctx, 'now', p2[0], c.h - 12, { size: 18, italic: true, color: G[3], align: 'right' });
  }

  // A vertical scale zoomed around now, a column up to the value, and
  // marks for where it was.
  function column(canvas, s) {
    var c = prepare(canvas);
    var m = { l: 76, r: 20, t: 24, b: 24 };
    var Y = linear(s.min, s.max, c.h - m.b, m.t);
    var x = m.l, colW = 46;
    (s.zones || []).forEach(function (z) {
      if (z.from > s.min && z.from < s.max) {
        var y = Y(z.from);
        c.rc.line(x + colW + 12, y, c.w - m.r, y, { stroke: G[4], strokeWidth: 1.5, roughness: 0.6, strokeLineDash: [9, 8] });
      }
      var mid = (Math.max(z.from, s.min) + Math.min(z.to, s.max)) / 2;
      if (z.from < s.max && z.to > s.min) {
        label(c.ctx, z.label, c.w - m.r - 6, Y(mid) + 6, { size: 17, italic: true, align: 'right', color: G[3] });
      }
    });
    for (var v = Math.ceil(s.min / 5) * 5; v <= s.max; v += 5) {
      c.rc.line(x - 8, Y(v), x, Y(v), { stroke: G[2], strokeWidth: 1.5, roughness: 0.4 });
      label(c.ctx, String(v), x - 14, Y(v) + 7, { size: 18, align: 'right' });
    }
    c.rc.rectangle(x, m.t, colW, c.h - m.t - m.b, { stroke: G[2], strokeWidth: 1.5, fill: 'none', roughness: 1 });
    if (s.value != null) {
      var yv = Y(s.value);
      c.rc.rectangle(x, yv, colW, c.h - m.b - yv, { fill: G[2], fillStyle: 'hachure', hachureGap: 6,
        fillWeight: 1.2, stroke: 'none', roughness: 1 });
      c.rc.line(x - 6, yv, x + colW + 6, yv, { stroke: G[0], strokeWidth: 3, roughness: 0.5 });
    }
    (s.marks || []).forEach(function (mk) {
      var y = Y(mk.y);
      c.rc.line(x + colW + 12, y, x + colW + 44, y, { stroke: G[2], strokeWidth: 1.5, roughness: 0.5, strokeLineDash: [4, 4] });
      label(c.ctx, mk.label, x + colW + 50, y + 6, { size: 17, italic: true, color: G[2] });
    });
  }

  var KINDS = { sparkline: sparkline, comfort: comfort, ribbon: ribbon, axis: axis,
                barograph: barograph, tendency: tendency, column: column,
                dotcloud: dotcloud, scale: scale_, dial: dial, meter: meter, bars: bars };

  function render(specs) {
    Promise.all([
      document.fonts.load('500 18px ' + FONT),
      document.fonts.load('italic 500 18px ' + FONT),
      document.fonts.ready
    ]).then(function () {
      specs.forEach(function (s) {
        var canvas = document.querySelector(s.canvas);
        if (canvas && KINDS[s.kind]) KINDS[s.kind](canvas, s);
      });
      document.body.setAttribute('data-charts', 'drawn');
    });
  }

  window.Charts = { render: render };
})();
