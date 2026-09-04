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

  var KINDS = { sparkline: sparkline, comfort: comfort, ribbon: ribbon, axis: axis };

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
