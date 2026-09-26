/* The drawings on the Config page's sheet tabs, with rough.js for the
   hand-drawn look the pages have: a day of syncs or page changes as a
   dial, the time before one sync as a strip, the image with its drawn
   area as a panel, and the space the stores take on the disk. The first
   three are drawn from the settings form's inputs, and dragging one
   writes the inputs, so the form stays what a save sends. A locked
   input, such as an offline dock's, cannot be dragged. The position
   grid sets the drawn area's two alignments the same way. */
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

  function choice(name) {
    var el = form.querySelector('input[type=radio][name="' + name + '"]:checked');
    return el ? el.value : '';
  }

  // Checks a radio as a click would, so config.js sees the change.
  function choose(name, value) {
    var el = form.querySelector('input[type=radio][name="' + name + '"][value="' + value + '"]');
    if (!el || el.disabled || el.checked) return;
    el.checked = true;
    el.dispatchEvent(new Event('change', { bubbles: true }));
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

  // The dock's schedule, which the strip draws the time before a sync of,
  // and the light's schedule, which only the dock's dial draws.
  var SYNC = 'dock.sync';
  var LIGHT = { 'dock.sync': 'dock.led.schedule' };
  // What a dial's count is of, for one and for more; a sync by default.
  var COUNTS = { 'display.schedule.ranges': ['page a day', 'pages a day'] };

  // A schedule's ranges from the form's rows, in order of their starts:
  // each {start, every, row}, the interval in seconds, 0 for off.
  function ranges(key) {
    var out = [];
    form.querySelectorAll('fieldset[data-key="' + key + '"] .list > .row').forEach(function (row) {
      var start = minutesOf(row.querySelector('input[type=time]').value);
      var every = parseInt(row.querySelector('input[type=number]').value, 10) * 60;
      if (!isNaN(start)) out.push({ start: start, every: every >= 0 ? every : 0, row: row });
    });
    return out.sort(function (a, b) { return a.start - b.start; });
  }

  // The range a minute of the day is in: the last to start at or before it,
  // or before the first start, the last of the day.
  function rangeAt(list, minute) {
    var at = list[list.length - 1];
    list.forEach(function (r) { if (r.start <= minute) at = r; });
    return at;
  }

  function schedule(key) {
    var light = LIGHT[key];
    var from = light ? minutesOf((input(light + '.from') || {}).value) : NaN;
    var to = light ? minutesOf((input(light + '.to') || {}).value) : NaN;
    return {
      ranges: ranges(key),
      light: !!light && on(light) && !isNaN(from) && !isNaN(to) && from !== to,
      from: from,
      to: to
    };
  }

  // The minutes of the day a reading is taken on, as the server counts them.
  function slots(s) {
    var out = [];
    if (!s.ranges.length) return out;
    for (var m = 0; m < DAY_MIN; m++) {
      var step = rangeAt(s.ranges, m).every;
      if (step > 0 && (m * 60) % step === 0) out.push(m);
    }
    return out;
  }

  // The shortest time between two readings, for the strip.
  function shortest(s) {
    var steps = s.ranges.map(function (r) { return r.every; }).filter(function (e) { return e > 0; });
    return steps.length ? Math.min.apply(null, steps) : 300;
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

  // ── The dial: a day of syncs or page changes ─────────────────────
  // Midnight at the top, the day running clockwise. Each tick is a sync; a
  // hatched band is a range that is off. A handle at each range's start drags
  // it round. The line inside is the light's schedule.
  function Dial(canvas) {
    this.canvas = canvas;
    this.key = canvas.getAttribute('data-schedule') || SYNC;
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
    var s = schedule(this.key);
    var fixed = locked(this.key + '.from');
    var ink = fixed ? G[4] : G[1];

    s.ranges.forEach(function (r, i) {
      if (r.every > 0) return;
      var next = s.ranges[(i + 1) % s.ranges.length];
      var a0 = angleOf(r.start), a1 = angleOf(next.start);
      if (a1 <= a0) a1 += 2 * Math.PI;
      p.rc.arc(cx, cy, 2 * (R - 10), 2 * (R - 10), a0, a1, true,
               { stroke: 'none', fill: fixed ? G[5] : G[3], fillStyle: 'hachure',
                 hachureGap: 5, fillWeight: 1.2, roughness: 1.2 });
    });
    // The band is a ring: the middle is cleared for the light and the count.
    p.ctx.save();
    p.ctx.beginPath();
    p.ctx.arc(cx, cy, R - 34, 0, 2 * Math.PI);
    p.ctx.fillStyle = G[7];
    p.ctx.fill();
    p.ctx.restore();

    if (s.light) {
      var b0 = angleOf(s.from), b1 = angleOf(s.to);
      if (b1 <= b0) b1 += 2 * Math.PI;
      p.rc.arc(cx, cy, 2 * (R - 42), 2 * (R - 42), b0, b1, false,
               { stroke: ink, strokeWidth: 3, roughness: 1.4 });
    }

    var readings = slots(s);
    p.ctx.save();
    p.ctx.strokeStyle = ink;
    var tightest = shortest(s);
    readings.forEach(function (m) {
      // A tick grows with its range's interval, so a slower range stands out.
      var a = angleOf(m), slow = rangeAt(s.ranges, m).every > tightest;
      var r0 = slow ? R - 12 : R - 7;
      p.ctx.lineWidth = slow ? 2 : 1;
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
    var count = COUNTS[this.key] || ['sync a day', 'syncs a day'];
    text(p.ctx, count[readings.length === 1 ? 0 : 1], cx, cy + 16,
         { size: 13, italic: true, color: G[3] });

    if (!fixed && s.ranges.length > 1) {
      s.ranges.forEach(function (r) {
        var a = angleOf(r.start);
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
    var s = schedule(this.key);
    if (s.ranges.length < 2 || locked(this.key + '.from')) return;
    var r = this.canvas.getBoundingClientRect(), g = this.geometry();
    var x = e.clientX - r.left, y = e.clientY - r.top;
    for (var i = 0; i < s.ranges.length; i++) {
      var a = angleOf(s.ranges[i].start);
      var hx = g.cx + Math.cos(a) * (g.R - 22), hy = g.cy + Math.sin(a) * (g.R - 22);
      if (Math.hypot(x - hx, y - hy) <= 14) {
        this.drag = s.ranges[i].row.querySelector('input[type=time]');
        this.canvas.setPointerCapture(e.pointerId);
        e.preventDefault();
        return;
      }
    }
  };

  // A start moves up to its neighbours' and no further, so the ranges keep their order.
  Dial.prototype.move = function (e) {
    if (!this.drag) return;
    var el = this.drag, list = ranges(this.key);
    var i = list.findIndex(function (r) { return r.row.contains(el); });
    if (i < 0) return;
    var prev = list[(i - 1 + list.length) % list.length].start;
    var next = list[(i + 1) % list.length].start;
    var m = this.minuteAt(e);
    var span = (next - prev + DAY_MIN) % DAY_MIN || DAY_MIN;
    var at = (m - prev + DAY_MIN) % DAY_MIN;
    if (at < 5 || at > span - 5) return;
    if (el.value === hhmm(m)) return;
    el.value = hhmm(m);
    el.dispatchEvent(new Event('input', { bubbles: true }));
  };

  // ── The strip: the time before one sync ──────────────────────────
  // From the sync before to this one, the shortest gap the schedule has.
  // The fan runs in the hatched band, dragged by its left edge; past the
  // start of the strip it never stops.
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
    var span = shortest(schedule(SYNC));
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
    text(p.ctx, 'sync', g.right, axis + 22, { size: 13, italic: true, align: 'right', color: G[2] });
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

  // ── The panel: the image and its drawn area ──────────────────────
  // The image to scale with its dimension lines, and the drawn area hatched
  // where its alignment puts it. The round handle, on the corner away from
  // where the area is anchored, resizes it; a dot at each of the nine places
  // moves it there.
  var ACROSS = { left: 0, center: 0.5, right: 1 };
  var DOWN = { top: 0, center: 0.5, bottom: 1 };

  function Panel(canvas) {
    this.canvas = canvas;
    this.drag = false;
    var self = this;
    canvas.addEventListener('pointerdown', function (e) { self.down(e); });
    canvas.addEventListener('pointermove', function (e) { self.move(e); });
    canvas.addEventListener('pointerup', function () { self.drag = false; });
    canvas.addEventListener('pointercancel', function () { self.drag = false; });
  }

  function picture() {
    var w = number('image.width'), h = number('image.height');
    w = w > 0 ? w : 1280;
    h = h > 0 ? h : 720;
    var iw = number('image.innerWidth'), ih = number('image.innerHeight');
    return { w: w, h: h,
             iw: iw > 0 ? Math.min(iw, w) : w, ih: ih > 0 ? Math.min(ih, h) : h,
             x: ACROSS.hasOwnProperty(choice('image.innerAlignX')) ? choice('image.innerAlignX') : 'center',
             y: DOWN.hasOwnProperty(choice('image.innerAlignY')) ? choice('image.innerAlignY') : 'center' };
  }

  Panel.prototype.geometry = function () {
    var r = this.canvas.getBoundingClientRect();
    var s = picture();
    var left = 30, top = 30;
    var k = Math.min((r.width - left - 10) / s.w, (r.height - top - 10) / s.h);
    var W = s.w * k, H = s.h * k, iw = s.iw * k, ih = s.ih * k;
    var ix = left + (W - iw) * ACROSS[s.x], iy = top + (H - ih) * DOWN[s.y];
    return {
      s: s, k: k, X: left, Y: top, W: W, H: H, ix: ix, iy: iy, iw: iw, ih: ih,
      hx: s.x === 'right' ? ix : ix + iw,
      hy: s.y === 'bottom' ? iy : iy + ih
    };
  };

  Panel.prototype.draw = function () {
    var p = prepare(this.canvas);
    if (!p.w) return;
    var g = this.geometry(), s = g.s;
    var fixed = locked('image.innerWidth');
    var ink = fixed ? G[4] : G[1];

    p.rc.rectangle(g.X, g.Y, g.W, g.H, { stroke: G[1], strokeWidth: 1.6, roughness: 1.2 });
    p.rc.rectangle(g.ix, g.iy, g.iw, g.ih,
                   { stroke: ink, strokeWidth: 1.2, fill: fixed ? G[5] : G[4],
                     fillStyle: 'hachure', hachureGap: 6, roughness: 1.1 });

    // Dimension lines, as a drawing gives them: the size along the top and
    // down the left.
    var above = g.Y - 12, beside = g.X - 12;
    p.rc.line(g.X, above, g.X + g.W, above, { stroke: G[3], roughness: 0.6 });
    p.rc.line(g.X, above - 5, g.X, above + 5, { stroke: G[3], roughness: 0.4 });
    p.rc.line(g.X + g.W, above - 5, g.X + g.W, above + 5, { stroke: G[3], roughness: 0.4 });
    text(p.ctx, s.w + ' px', g.X + g.W / 2, above, { size: 12, italic: true, color: G[2], halo: true });
    p.rc.line(beside, g.Y, beside, g.Y + g.H, { stroke: G[3], roughness: 0.6 });
    p.rc.line(beside - 5, g.Y, beside + 5, g.Y, { stroke: G[3], roughness: 0.4 });
    p.rc.line(beside - 5, g.Y + g.H, beside + 5, g.Y + g.H, { stroke: G[3], roughness: 0.4 });
    p.ctx.save();
    p.ctx.translate(beside, g.Y + g.H / 2);
    p.ctx.rotate(-Math.PI / 2);
    text(p.ctx, s.h + ' px', 0, 0, { size: 12, italic: true, color: G[2], halo: true });
    p.ctx.restore();

    Object.keys(DOWN).forEach(function (y) {
      Object.keys(ACROSS).forEach(function (x) {
        var here = x === s.x && y === s.y;
        p.ctx.save();
        p.ctx.beginPath();
        p.ctx.arc(g.X + g.W * ACROSS[x], g.Y + g.H * DOWN[y], here ? 4.5 : 3.5, 0, 2 * Math.PI);
        p.ctx.fillStyle = here ? ink : G[7];
        p.ctx.strokeStyle = here ? ink : G[3];
        p.ctx.lineWidth = 1.5;
        p.ctx.fill();
        p.ctx.stroke();
        p.ctx.restore();
      });
    });

    // Over the dots, and clear of the middle one.
    text(p.ctx, s.iw + ' × ' + s.ih, g.ix + g.iw / 2, g.iy + g.ih / 2 + 20,
         { size: 14, weight: 600, color: ink, halo: true });

    if (!fixed) {
      p.rc.circle(g.hx, g.hy, 14, { stroke: G[0], strokeWidth: 1.6, fill: G[7],
                                    fillStyle: 'solid', roughness: 0.8 });
    }
  };

  Panel.prototype.down = function (e) {
    if (locked('image.innerWidth')) return;
    var r = this.canvas.getBoundingClientRect(), g = this.geometry();
    var x = e.clientX - r.left, y = e.clientY - r.top;
    if (Math.hypot(x - g.hx, y - g.hy) <= 12) {
      this.drag = true;
      this.canvas.setPointerCapture(e.pointerId);
      e.preventDefault();
      return;
    }
    Object.keys(DOWN).forEach(function (yv) {
      Object.keys(ACROSS).forEach(function (xv) {
        if (Math.hypot(x - (g.X + g.W * ACROSS[xv]), y - (g.Y + g.H * DOWN[yv])) <= 10) {
          choose('image.innerAlignX', xv);
          choose('image.innerAlignY', yv);
        }
      });
    });
  };

  // Ten-pixel steps: a drag to the pixel is finer than the drawing shows.
  Panel.prototype.move = function (e) {
    if (!this.drag) return;
    var r = this.canvas.getBoundingClientRect(), g = this.geometry(), s = g.s;
    var x = e.clientX - r.left, y = e.clientY - r.top;
    function span(at, start, size, anchor) {
      if (anchor === 0) return at - start;
      if (anchor === 1) return start + size - at;
      return 2 * Math.abs(at - (start + size / 2));
    }
    function snap(v, most) { return Math.max(10, Math.min(most, Math.round(v / 10) * 10)); }
    set('image.innerWidth', snap(span(x, g.X, g.W, ACROSS[s.x]) / g.k, s.w));
    set('image.innerHeight', snap(span(y, g.Y, g.H, DOWN[s.y]) / g.k, s.h));
  };

  // ── The disk: the space the stores' files take ───────────────────
  // The disk as a bar, the part in use hatched and the files' part solid at
  // its start. Under it the files' part is drawn larger, as a detail view is
  // on a drawing: a section a file, sized by its bytes and filled its own
  // way, and a key to the fills below. It only shows.
  var FILLS = [
    { fillStyle: 'hachure', fill: G[3] },
    { fillStyle: 'cross-hatch', fill: G[4] },
    { fillStyle: 'dots', fill: G[3] },
    { fillStyle: 'solid', fill: G[5] }
  ];

  function bytes(n) {
    if (n < 1000) return n + ' bytes';
    var units = [['GB', 1e9], ['MB', 1e6]];
    for (var i = 0; i < units.length; i++) {
      if (n >= units[i][1]) {
        var v = n / units[i][1];
        return (v >= 100 ? v.toFixed(0) : v.toFixed(1).replace(/\.0$/, '')) + ' ' + units[i][0];
      }
    }
    return (n / 1000).toFixed(0) + ' kB';
  }

  function Disk(canvas) {
    this.canvas = canvas;
  }

  Disk.prototype.data = function () {
    try {
      return JSON.parse(this.canvas.getAttribute('data-disk') || '{}');
    } catch (e) {
      return {};
    }
  };

  Disk.prototype.draw = function () {
    var d = this.data(), stores = d.stores || [];
    var width = this.canvas.getBoundingClientRect().width;
    if (!width) return;
    var L = 4, R = width - 4;
    var cols = Math.max(1, Math.min(stores.length, Math.floor((R - L) / 130)));
    var rows = Math.ceil(stores.length / cols);
    var known = d.total > 0;
    var top = known ? 78 : 4, keyTop = top + 26 + 18;
    this.canvas.style.height = (keyTop + rows * 40) + 'px';
    var p = prepare(this.canvas);
    if (!p.w) return;

    var files = stores.reduce(function (sum, s) { return sum + s.size; }, 0);
    if (known) {
      var used = d.total - d.free;
      var usedX = L + (used / d.total) * (R - L);
      var markX = Math.min(usedX, L + Math.max(4, (files / d.total) * (R - L)));
      text(p.ctx, bytes(used) + ' used', L, 10, { size: 13, italic: true, align: 'left', color: G[3] });
      text(p.ctx, bytes(d.free) + ' free of ' + bytes(d.total), R, 10,
           { size: 14, italic: true, align: 'right', color: G[1] });
      p.rc.rectangle(L, 22, usedX - L, 20, { stroke: 'none', fill: G[4], fillStyle: 'hachure',
                                             hachureGap: 5, roughness: 1.1 });
      p.rc.rectangle(L, 22, markX - L, 20, { stroke: 'none', fill: G[0], fillStyle: 'solid',
                                             roughness: 0.6 });
      p.rc.rectangle(L, 22, R - L, 20, { stroke: G[1], strokeWidth: 1.4, roughness: 1.1 });
      p.ctx.save();
      p.ctx.setLineDash([3, 4]);
      p.ctx.strokeStyle = G[3];
      p.ctx.beginPath();
      p.ctx.moveTo(L, 44);
      p.ctx.lineTo(L, top - 2);
      p.ctx.moveTo(markX, 44);
      p.ctx.lineTo(R, top - 2);
      p.ctx.stroke();
      p.ctx.restore();
      text(p.ctx, 'Files: ' + bytes(files), R, top - 12,
           { size: 13, italic: true, align: 'right', color: G[2], halo: true });
    }

    // Each file at least wide enough to see, the rest shared by size.
    var least = 6, shown = stores.filter(function (s) { return s.size > 0; });
    var room = R - L - least * shown.length;
    var x = L;
    stores.forEach(function (s, i) {
      if (!(s.size > 0)) return;
      var w = least + (files ? room * s.size / files : 0);
      p.rc.rectangle(x, top, w, 26, Object.assign({ stroke: 'none', hachureGap: 7,
                                                    fillWeight: 0.8, roughness: 1.1 },
                                                  FILLS[i % FILLS.length]));
      if (x > L) p.rc.line(x, top, x, top + 26, { stroke: G[1], strokeWidth: 1.2, roughness: 0.6 });
      x += w;
    });
    p.rc.rectangle(L, top, R - L, 26, { stroke: G[1], strokeWidth: 1.6, roughness: 1.1 });
    if (!files) {
      text(p.ctx, 'No files yet.', (L + R) / 2, top + 13, { size: 13, italic: true, color: G[3] });
    }

    // The key: a swatch filled as its section is, the file's name and bytes.
    var slot = (R - L) / cols;
    stores.forEach(function (s, i) {
      var kx = L + (i % cols) * slot, ky = keyTop + Math.floor(i / cols) * 40;
      p.rc.rectangle(kx, ky, 18, 18, Object.assign({ stroke: G[1], strokeWidth: 1, hachureGap: 5,
                                                     fillWeight: 0.8, roughness: 0.8 },
                                                   FILLS[i % FILLS.length]));
      text(p.ctx, s.name, kx + 26, ky + 8, { size: 14, italic: true, align: 'left', color: G[1] });
      text(p.ctx, s.size > 0 ? bytes(s.size) : 'no file yet', kx + 26, ky + 26,
           { size: 13, italic: true, align: 'left', color: G[3] });
    });
  };

  // ── The position grid ────────────────────────────────────────────
  var grids = Array.prototype.slice.call(form.querySelectorAll('.grid3'));
  grids.forEach(function (grid) {
    grid.addEventListener('click', function (e) {
      var b = e.target.closest('button');
      if (!b || b.disabled) return;
      choose(grid.getAttribute('data-x'), b.getAttribute('data-x'));
      choose(grid.getAttribute('data-y'), b.getAttribute('data-y'));
    });
  });

  function markGrids() {
    grids.forEach(function (grid) {
      var x = choice(grid.getAttribute('data-x')), y = choice(grid.getAttribute('data-y'));
      grid.querySelectorAll('button').forEach(function (b) {
        var on = b.getAttribute('data-x') === x && b.getAttribute('data-y') === y;
        b.setAttribute('aria-pressed', on ? 'true' : 'false');
      });
    });
  }

  // ── Wiring ───────────────────────────────────────────────────────
  var drawings = [];
  document.querySelectorAll('canvas[data-visual]').forEach(function (canvas) {
    var kind = canvas.getAttribute('data-visual');
    if (kind === 'dial') drawings.push(new Dial(canvas));
    if (kind === 'slot') drawings.push(new Strip(canvas));
    if (kind === 'panel') drawings.push(new Panel(canvas));
    if (kind === 'disk') drawings.push(new Disk(canvas));
  });
  if (!drawings.length && !grids.length) return;

  function redraw() {
    drawings.forEach(function (d) { d.draw(); });
    markGrids();
  }
  form.addEventListener('input', redraw);
  form.addEventListener('change', redraw);
  // config.js says so when an import changes what the stores hold.
  form.addEventListener('held', redraw);
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
