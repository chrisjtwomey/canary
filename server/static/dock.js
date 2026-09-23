/* The Dock tab's drawings, with rough.js for the hand-drawn look the pages
   have: the day's reports as a dial, and the time before one report as a
   strip. Each is drawn from the settings form's inputs, and dragging one
   writes the inputs, so the form stays what a save sends. A locked input,
   such as an offline dock's, cannot be dragged. */
(function () {
  'use strict';

  var G = ['#000000', '#242424', '#494949', '#6d6d6d',
           '#929292', '#b6b6b6', '#dbdbdb', '#ffffff'];
  var FONT = 'Fraunces';
  var SEED = 7;
  var DAY_MIN = 1440;
  // What the dock does before a reading when the fan never stops.
  var PREWARM_S = 35;

  var form = document.getElementById('settings-form');
  if (!form || typeof rough === 'undefined') return;

  // ── The form's values ────────────────────────────────────────────
  function input(name) {
    return form.querySelector('[name="' + name + '"]:not([type=hidden])');
  }

  function number(name) {
    var el = input(name);
    if (!el) return NaN;
    return parseInt(el.value || el.getAttribute('data-default') || '', 10);
  }

  function on(name) {
    var el = form.querySelector('input[type=checkbox][name="' + name + '"]');
    return !!(el && el.checked);
  }

  function minutesOf(hhmm) {
    var m = /^(\d{1,2}):(\d{2})$/.exec(hhmm || '');
    return m ? (parseInt(m[1], 10) * 60 + parseInt(m[2], 10)) % DAY_MIN : NaN;
  }

  function hhmm(minutes) {
    var m = ((minutes % DAY_MIN) + DAY_MIN) % DAY_MIN;
    return ('0' + Math.floor(m / 60)).slice(-2) + ':' + ('0' + (m % 60)).slice(-2);
  }

  function locked(name) {
    var el = input(name);
    return !el || el.disabled;
  }

  // Writes as a person typing would, so config.js sees the change.
  function set(name, value) {
    var el = input(name);
    if (!el || el.disabled || el.value === String(value)) return;
    el.value = String(value);
    el.dispatchEvent(new Event('input', { bubbles: true }));
  }

  // The report intervals, which the form shows in minutes, in seconds.
  function schedule() {
    var every = number('posts.every') * 60;
    var quietEvery = number('posts.quiet.every') * 60;
    var from = minutesOf((input('posts.quiet.from') || {}).value);
    var to = minutesOf((input('posts.quiet.to') || {}).value);
    return {
      every: every > 0 ? every : 300,
      quietEvery: quietEvery > 0 ? quietEvery : (every > 0 ? every : 300),
      quiet: on('posts.quiet') && !isNaN(from) && !isNaN(to) && from !== to,
      from: from,
      to: to,
      dark: on('dock.led.off_in_quiet_hours')
    };
  }

  function inQuiet(s, minute) {
    if (!s.quiet) return false;
    return s.from < s.to ? minute >= s.from && minute < s.to
                         : minute >= s.from || minute < s.to;
  }

  // The minutes of the day a reading is taken on, as the server counts them.
  function slots(s) {
    var out = [];
    for (var m = 0; m < DAY_MIN; m++) {
      var step = inQuiet(s, m) ? s.quietEvery : s.every;
      if ((m * 60) % step === 0) out.push(m);
    }
    return out;
  }

  // ── Drawing ──────────────────────────────────────────────────────
  function prepare(canvas) {
    var r = canvas.getBoundingClientRect();
    var k = window.devicePixelRatio || 1;
    canvas.width = Math.round(r.width * k);
    canvas.height = Math.round(r.height * k);
    var ctx = canvas.getContext('2d');
    ctx.setTransform(k, 0, 0, k, 0, 0);
    ctx.clearRect(0, 0, r.width, r.height);
    return { w: r.width, h: r.height, ctx: ctx,
             rc: rough.canvas(canvas, { options: { seed: SEED } }) };
  }

  function text(ctx, s, x, y, o) {
    o = o || {};
    ctx.save();
    ctx.font = (o.italic ? 'italic ' : '') + (o.weight || 500) + ' ' +
               (o.size || 14) + 'px ' + FONT;
    ctx.fillStyle = o.color || G[2];
    ctx.textAlign = o.align || 'center';
    ctx.textBaseline = o.baseline || 'middle';
    if (o.halo) {
      ctx.strokeStyle = G[7];
      ctx.lineWidth = 4;
      ctx.lineJoin = 'round';
      ctx.strokeText(s, x, y);
    }
    ctx.fillText(s, x, y);
    ctx.restore();
  }

  // ── The dial: the day's reports ──────────────────────────────────
  // Midnight at the top, the day running clockwise. Each tick is a report;
  // the hatched band is slow mode (posts.quiet), dragged by its ends; the line inside it
  // is the light, dark.
  function Dial(canvas) {
    this.canvas = canvas;
    this.drag = null;
    var self = this;
    canvas.addEventListener('pointerdown', function (e) { self.down(e); });
    canvas.addEventListener('pointermove', function (e) { self.move(e); });
    canvas.addEventListener('pointerup', function () { self.drag = null; });
    canvas.addEventListener('pointercancel', function () { self.drag = null; });
  }

  Dial.prototype.geometry = function () {
    var r = this.canvas.getBoundingClientRect();
    var size = Math.min(r.width, r.height);
    return { cx: r.width / 2, cy: r.height / 2, R: size / 2 - 6 };
  };

  function angleOf(minute) { return -Math.PI / 2 + (minute / DAY_MIN) * 2 * Math.PI; }

  Dial.prototype.draw = function () {
    var p = prepare(this.canvas);
    if (!p.w) return;
    var g = this.geometry(), cx = g.cx, cy = g.cy, R = g.R;
    var s = schedule();
    var fixed = locked('posts.quiet.from');
    var ink = fixed ? G[4] : G[1];

    if (s.quiet) {
      var a0 = angleOf(s.from), a1 = angleOf(s.to);
      if (a1 <= a0) a1 += 2 * Math.PI;
      p.rc.arc(cx, cy, 2 * (R - 10), 2 * (R - 10), a0, a1, true,
               { stroke: 'none', fill: fixed ? G[5] : G[3], fillStyle: 'hachure',
                 hachureGap: 5, fillWeight: 1.2, roughness: 1.2 });
    }
    // The band is a ring: the middle is cleared for the light and the count.
    p.ctx.save();
    p.ctx.beginPath();
    p.ctx.arc(cx, cy, R - 34, 0, 2 * Math.PI);
    p.ctx.fillStyle = G[7];
    p.ctx.fill();
    p.ctx.restore();

    if (s.quiet && s.dark) {
      var b0 = angleOf(s.from), b1 = angleOf(s.to);
      if (b1 <= b0) b1 += 2 * Math.PI;
      p.rc.arc(cx, cy, 2 * (R - 42), 2 * (R - 42), b0, b1, false,
               { stroke: ink, strokeWidth: 3, roughness: 1.4 });
    }

    var readings = slots(s);
    p.ctx.save();
    p.ctx.strokeStyle = ink;
    readings.forEach(function (m) {
      var a = angleOf(m), quiet = inQuiet(s, m);
      var r0 = quiet ? R - 12 : R - 7;
      p.ctx.lineWidth = quiet ? 2 : 1;
      p.ctx.beginPath();
      p.ctx.moveTo(cx + Math.cos(a) * r0, cy + Math.sin(a) * r0);
      p.ctx.lineTo(cx + Math.cos(a) * R, cy + Math.sin(a) * R);
      p.ctx.stroke();
    });
    p.ctx.restore();
    p.rc.circle(cx, cy, 2 * R, { stroke: ink, strokeWidth: 1.6, roughness: 1.3 });

    [[0, '00'], [360, '06'], [720, '12'], [1080, '18']].forEach(function (h) {
      var a = angleOf(h[0]);
      text(p.ctx, h[1], cx + Math.cos(a) * (R - 58), cy + Math.sin(a) * (R - 58),
           { size: 13, italic: true, color: G[3] });
    });
    text(p.ctx, String(readings.length), cx, cy - 8, { size: 30, weight: 600, color: ink });
    text(p.ctx, 'reports a day', cx, cy + 16, { size: 13, italic: true, color: G[3] });

    if (s.quiet && !fixed) {
      [s.from, s.to].forEach(function (m) {
        var a = angleOf(m);
        p.rc.circle(cx + Math.cos(a) * (R - 22), cy + Math.sin(a) * (R - 22), 14,
                    { stroke: G[0], strokeWidth: 1.6, fill: G[7], fillStyle: 'solid',
                      roughness: 0.8 });
      });
    }
  };

  Dial.prototype.minuteAt = function (e) {
    var r = this.canvas.getBoundingClientRect(), g = this.geometry();
    var a = Math.atan2(e.clientY - r.top - g.cy, e.clientX - r.left - g.cx) + Math.PI / 2;
    if (a < 0) a += 2 * Math.PI;
    // Five-minute steps: the fields hold HH:MM, and a slot falls on a whole minute.
    return Math.round((a / (2 * Math.PI)) * DAY_MIN / 5) * 5 % DAY_MIN;
  };

  Dial.prototype.down = function (e) {
    var s = schedule();
    if (!s.quiet || locked('posts.quiet.from')) return;
    var r = this.canvas.getBoundingClientRect(), g = this.geometry();
    var x = e.clientX - r.left, y = e.clientY - r.top;
    var ends = [['posts.quiet.from', s.from], ['posts.quiet.to', s.to]];
    for (var i = 0; i < ends.length; i++) {
      var a = angleOf(ends[i][1]);
      var hx = g.cx + Math.cos(a) * (g.R - 22), hy = g.cy + Math.sin(a) * (g.R - 22);
      if (Math.hypot(x - hx, y - hy) <= 14) {
        this.drag = ends[i][0];
        this.canvas.setPointerCapture(e.pointerId);
        e.preventDefault();
        return;
      }
    }
  };

  Dial.prototype.move = function (e) {
    if (!this.drag) return;
    set(this.drag, hhmm(this.minuteAt(e)));
  };

  // ── The strip: the time before one report ────────────────────────
  // From the report before to this one, a day slot apart. The fan runs in
  // the hatched band, dragged by its left edge; past the start of the strip
  // it never stops.
  function Strip(canvas) {
    this.canvas = canvas;
    this.drag = false;
    var self = this;
    canvas.addEventListener('pointerdown', function (e) { self.down(e); });
    canvas.addEventListener('pointermove', function (e) { self.move(e); });
    canvas.addEventListener('pointerup', function () { self.drag = false; });
    canvas.addEventListener('pointercancel', function () { self.drag = false; });
  }

  Strip.prototype.geometry = function () {
    var r = this.canvas.getBoundingClientRect();
    var span = schedule().every;
    var left = 14, right = r.width - 14;
    return {
      left: left, right: right, span: span,
      x: function (before) { return right - (before / span) * (right - left); }
    };
  };

  function warmup() {
    var s = number('dock.pm.warmup_s');
    return isNaN(s) ? PREWARM_S : s;
  }

  function span(seconds) {
    if (seconds >= 60 && seconds % 60 === 0) return (seconds / 60) + ' min';
    if (seconds >= 60) return Math.floor(seconds / 60) + ' min ' + (seconds % 60) + ' s';
    return seconds + ' s';
  }

  Strip.prototype.draw = function () {
    var p = prepare(this.canvas);
    if (!p.w) return;
    var g = this.geometry();
    var fan = warmup();
    var always = fan === 0 || fan >= g.span;
    var lead = fan === 0 ? PREWARM_S : Math.min(fan, g.span);
    var fixed = locked('dock.pm.warmup_s');
    var ink = fixed ? G[4] : G[1];
    var axis = 72;

    var bandLeft = always ? g.left : g.x(lead);
    p.rc.rectangle(bandLeft, axis - 26, g.right - bandLeft, 26,
                   { stroke: ink, strokeWidth: 1.2, fill: fixed ? G[5] : G[3],
                     fillStyle: 'hachure', hachureGap: 5, roughness: 1.2 });
    text(p.ctx, always ? 'fan always on' : 'fan ' + span(fan),
         Math.max(bandLeft + 4, Math.min((bandLeft + g.right) / 2, g.right - 50)), axis - 46,
         { size: 14, italic: true, color: ink, halo: true });

    p.rc.line(g.left, axis, g.right, axis, { stroke: ink, strokeWidth: 1.6, roughness: 1 });
    [g.left, g.right].forEach(function (x) {
      p.rc.line(x, axis - 34, x, axis + 8, { stroke: G[0], strokeWidth: 2, roughness: 0.8 });
    });
    text(p.ctx, 'report', g.right, axis + 22, { size: 13, italic: true, align: 'right', color: G[2] });
    text(p.ctx, span(g.span) + ' before', g.left, axis + 22,
         { size: 13, italic: true, align: 'left', color: G[3] });

    // The pre-warm: settings, a recalibration, a stopped sensor started again.
    var pre = g.x(Math.min(lead, g.span));
    p.ctx.save();
    p.ctx.setLineDash([3, 4]);
    p.ctx.strokeStyle = G[2];
    p.ctx.beginPath();
    p.ctx.moveTo(pre, axis - 44);
    p.ctx.lineTo(pre, axis + 30);
    p.ctx.stroke();
    p.ctx.restore();
    text(p.ctx, 'pre-warm', pre - 6, axis + 22, { size: 13, italic: true, align: 'right', color: G[2], halo: true });

    if (!fixed && !always) {
      p.rc.line(bandLeft, axis - 30, bandLeft, axis + 4, { stroke: G[0], strokeWidth: 3, roughness: 0.6 });
    }
  };

  Strip.prototype.down = function (e) {
    if (locked('dock.pm.warmup_s')) return;
    var r = this.canvas.getBoundingClientRect(), g = this.geometry();
    var fan = warmup();
    var edge = fan === 0 || fan >= g.span ? g.left : g.x(fan);
    var x = e.clientX - r.left, y = e.clientY - r.top;
    if (Math.abs(x - edge) > 14 || y > 90) return;
    this.drag = true;
    this.canvas.setPointerCapture(e.pointerId);
    e.preventDefault();
  };

  Strip.prototype.move = function (e) {
    if (!this.drag) return;
    var r = this.canvas.getBoundingClientRect(), g = this.geometry();
    var x = e.clientX - r.left;
    if (x <= g.left + 2) {
      set('dock.pm.warmup_s', 0);
      return;
    }
    var before = (g.right - x) / (g.right - g.left) * g.span;
    set('dock.pm.warmup_s', Math.max(30, Math.min(600, Math.round(before / 5) * 5)));
  };

  // ── Wiring ───────────────────────────────────────────────────────
  var drawings = [];
  document.querySelectorAll('canvas[data-visual]').forEach(function (canvas) {
    var kind = canvas.getAttribute('data-visual');
    if (kind === 'dial') drawings.push(new Dial(canvas));
    if (kind === 'slot') drawings.push(new Strip(canvas));
  });
  if (!drawings.length) return;

  function redraw() { drawings.forEach(function (d) { d.draw(); }); }
  form.addEventListener('input', redraw);
  form.addEventListener('change', redraw);
  // A canvas on a closed tab has no size; it draws when its tab opens.
  if (typeof ResizeObserver !== 'undefined') {
    var seen = new ResizeObserver(redraw);
    drawings.forEach(function (d) { seen.observe(d.canvas); });
  } else {
    window.addEventListener('resize', redraw);
  }
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(redraw);
  redraw();
})();
