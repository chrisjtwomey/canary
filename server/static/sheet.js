/* The drawings on the Config page's sheet tabs, with rough.js for the
   hand-drawn look the pages have: a day of syncs or page changes as a
   dial, the time before one sync as a strip, the minutes after the SCD41
   starts as another, the image with its drawn area as a panel, the
   Comfort page's edges, the space the stores take on the disk, and
   the status light playing one of its looks. All but the disk and the
   light are drawn from the settings form's inputs, and dragging one
   writes the inputs, so the form stays what a save sends. A locked input, such as an offline
   dock's, cannot be dragged. The position grid sets the drawn area's two
   alignments the same way. */
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
  var SYNC = 'dock.sync.week';
  var LIGHT = { 'dock.sync.week': 'dock.led.schedule' };
  // What a dial's count is of, for one and for more; a sync by default.
  var COUNTS = { 'display.schedule.week': ['page a day', 'pages a day'] };

  // The ranges of the group of days a schedule shows, from the form's rows,
  // in order of their starts: each {start, every, row}, the interval in
  // seconds, 0 for off.
  function ranges(key) {
    var out = [];
    var week = form.querySelector('fieldset[data-key="' + key + '"]');
    var group = week && (week.querySelector('.group:not([hidden])') || week.querySelector('.group'));
    if (!group) return out;
    group.querySelectorAll('.list > .row').forEach(function (row) {
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

  // Whether a schedule's ranges cannot be changed, as an offline dock's cannot.
  function scheduleLocked(key) {
    var first = ranges(key)[0];
    var el = first && first.row.querySelector('input[type=time]');
    return !el || el.disabled;
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

  function dashed(ctx, x, top, bottom, dash, color, width) {
    ctx.save();
    ctx.setLineDash(dash);
    ctx.strokeStyle = color;
    ctx.lineWidth = width || 1;
    ctx.beginPath();
    ctx.moveTo(x, top);
    ctx.lineTo(x, bottom);
    ctx.stroke();
    ctx.restore();
  }

  // The value to keep, which the server marks on a drawing's canvas; a
  // field below it shows its caution.
  function recommended(canvas) {
    var rec = parseFloat(canvas.getAttribute('data-recommended'));
    return isNaN(rec) ? null : rec;
  }

  // The line, and its label at the top on the side away from the band.
  function markRecommended(p, x, axis, bandSide) {
    dashed(p.ctx, x, axis - 56, axis + 8, [6, 4], G[4], 1.5);
    var left = bandSide === 'right';
    text(p.ctx, 'recommended', left ? x - 6 : x + 6, axis - 58,
         { size: 13, italic: true, color: G[4], halo: true, align: left ? 'right' : 'left' });
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
    var fixed = scheduleLocked(this.key);
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
    if (s.ranges.length < 2 || scheduleLocked(this.key)) return;
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
    var rec = recommended(this.canvas);
    if (rec !== null && rec < g.span) markRecommended(p, g.x(rec), axis, 'right');
    text(p.ctx, always ? 'fan always on' : 'warm-up ' + span(fan),
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
    dashed(p.ctx, pre, axis - 44, axis + 30, [3, 4], G[2]);
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

  // ── The start strip: the minutes after the SCD41 starts ──────────
  // Time runs from the start on the left. The hatched band is the warm-up,
  // dragged by its right edge. Each dot is a reading: the first a fan
  // warm-up after the start, as the pre-warm starts the SCD41 again after a
  // change to its settings, then one each sync. An open dot is a reading in
  // the warm-up, which has CO₂ only.
  var START_SPAN_S = 600;
  var SCD41_WARMUP = 'dock.scd41.warmup_s';

  function Start(canvas) {
    this.canvas = canvas;
    this.drag = false;
    var self = this;
    canvas.addEventListener('pointerdown', function (e) { self.down(e); });
    canvas.addEventListener('pointermove', function (e) { self.move(e); });
    canvas.addEventListener('pointerup', function () { self.drag = false; });
    canvas.addEventListener('pointercancel', function () { self.drag = false; });
  }

  Start.prototype.geometry = function () {
    var r = this.canvas.getBoundingClientRect();
    var left = 14, right = r.width - 14;
    return {
      left: left, right: right,
      x: function (after) { return left + (after / START_SPAN_S) * (right - left); }
    };
  };

  Start.prototype.warmup = function () {
    var s = number(SCD41_WARMUP);
    if (isNaN(s)) s = recommended(this.canvas) || 0;
    return Math.max(0, Math.min(START_SPAN_S, s));
  };

  Start.prototype.draw = function () {
    var p = prepare(this.canvas);
    if (!p.w) return;
    var g = this.geometry();
    var w = this.warmup();
    var fixed = locked(SCD41_WARMUP);
    var ink = fixed ? G[4] : G[1];
    var axis = 72;

    if (w > 0) {
      p.rc.rectangle(g.left, axis - 26, g.x(w) - g.left, 26,
                     { stroke: ink, strokeWidth: 1.2, fill: fixed ? G[5] : G[3],
                       fillStyle: 'hachure', hachureGap: 5, roughness: 1.2 });
    }
    var rec = recommended(this.canvas);
    if (rec !== null) markRecommended(p, g.x(rec), axis, 'left');
    text(p.ctx, w > 0 ? 'warm-up ' + span(w) : 'no warm-up',
         Math.max(g.left + 50, Math.min((g.left + g.x(w)) / 2, g.right - 50)), axis - 40,
         { size: 14, italic: true, color: ink, halo: true });

    p.rc.line(g.left, axis, g.right, axis, { stroke: ink, strokeWidth: 1.6, roughness: 1 });
    p.rc.line(g.left, axis - 34, g.left, axis + 8, { stroke: G[0], strokeWidth: 2, roughness: 0.8 });
    text(p.ctx, 'startup', g.left, axis + 22, { size: 13, italic: true, align: 'left', color: G[2] });
    text(p.ctx, span(START_SPAN_S) + ' after', g.right, axis + 22,
         { size: 13, italic: true, align: 'right', color: G[3] });

    var fan = warmup();
    var gap = shortest(schedule(SYNC));
    var first = fan === 0 ? PREWARM_S : Math.min(fan, gap);
    for (var t = first; t <= START_SPAN_S; t += gap) {
      var kept = t >= w;
      p.rc.circle(g.x(t), axis, 11, { stroke: G[0], strokeWidth: 1.4, roughness: 0.5,
                                      fill: kept ? G[1] : G[7], fillStyle: 'solid' });
    }

    if (!fixed) {
      var edge = w > 0 ? g.x(w) : g.left;
      p.rc.line(edge, axis - 30, edge, axis + 4, { stroke: G[0], strokeWidth: 3, roughness: 0.6 });
    }
  };

  Start.prototype.down = function (e) {
    if (locked(SCD41_WARMUP)) return;
    var r = this.canvas.getBoundingClientRect(), g = this.geometry();
    var w = this.warmup();
    var edge = w > 0 ? g.x(w) : g.left;
    var x = e.clientX - r.left, y = e.clientY - r.top;
    if (Math.abs(x - edge) > 14 || y > 90) return;
    this.drag = true;
    this.canvas.setPointerCapture(e.pointerId);
    e.preventDefault();
  };

  Start.prototype.move = function (e) {
    if (!this.drag) return;
    var r = this.canvas.getBoundingClientRect(), g = this.geometry();
    var x = e.clientX - r.left;
    if (x <= g.left + 2) {
      set(SCD41_WARMUP, 0);
      return;
    }
    var after = (x - g.left) / (g.right - g.left) * START_SPAN_S;
    set(SCD41_WARMUP, Math.max(0, Math.min(START_SPAN_S, Math.round(after / 5) * 5)));
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

  // ── The light's preview: one look, played as the dock plays it ───
  // A dot lit to the level the dock's StatusLed gives the look of the row
  // last changed or clicked, on the smoothness the slider holds, at full
  // brightness. The level is perceived light, which the screen shows as it
  // is, so it takes no gamma. The timings are StatusLed's.
  var LED_FLASH_MS = 150;
  var LED_BLIP_MS = 50;
  var LED_GROUP_STEP_MS = 300;
  var LED_GROUPS = { double_flash: 2, double_pulse: 2, triple_flash: 3, triple_pulse: 3 };
  var LED_STEPS = [4, 8, 16, 32, 64, 0];

  function ledSteps() {
    var el = form.querySelector('input.stops[name="dock.led.smoothness"]');
    var steps = LED_STEPS[(el ? parseInt(el.value, 10) : 3) - 1];
    return steps === undefined ? 16 : steps;
  }

  // As StatusLed's levelDuty: the nearest step, or no step with 0.
  function onStep(level, steps) {
    level = Math.max(0, Math.min(1, level));
    return steps > 1 ? Math.round(level * (steps - 1)) / (steps - 1) : level;
  }

  function sine(phase, period) { return 0.5 * (1 - Math.cos(2 * Math.PI * phase / period)); }

  // The light of `pattern`, 0 to 1, at `phase` ms into a cycle of `length`.
  function ledLevel(pattern, phase, length, steps) {
    var group = LED_GROUPS[pattern];
    if (group) {
      if (phase >= group * LED_GROUP_STEP_MS) return 0;
      var step = phase % LED_GROUP_STEP_MS;
      if (/flash$/.test(pattern)) return step < LED_FLASH_MS ? 1 : 0;
      return onStep(sine(step, LED_GROUP_STEP_MS), steps);
    }
    var third = Math.floor(length / 3);
    switch (pattern) {
      case 'solid': return 1;
      case 'pulse': return onStep(sine(phase, length), steps);
      case 'flash': return phase < Math.min(LED_FLASH_MS, length / 2) ? 1 : 0;
      case 'blip': return phase < Math.min(LED_BLIP_MS, length / 2) ? 1 : 0;
      case 'swell':
        if (phase < third) return onStep(sine(phase, 2 * third), steps);
        if (phase < length - third) return 1;
        return onStep(sine(phase - (length - 2 * third), 2 * third), steps);
      case 'ramp': return onStep(phase / length, steps);
      default: return 0;
    }
  }

  // The light's brightness, 0 to 100; the default while the field is empty.
  function ledBrightness() {
    var el = input('dock.led.brightness_pct');
    var pct = el ? parseInt(el.value || el.getAttribute('data-default') || '', 10) : NaN;
    return isNaN(pct) ? 15 : Math.max(0, Math.min(100, pct));
  }

  // The dot's lit area grows with the brightness, from 6 px across to its
  // full 30, and 0 is dark.
  var LED_DOT_MIN_PX = 6;
  var LED_DOT_MAX_PX = 30;

  function LedPreview(box) {
    var looks = form.querySelector('fieldset.looks');
    var dot = box.querySelector('.dot');
    var words = box.querySelector('.led-look');
    // The row a person picked; until then the dot follows the dock's light.
    var picked = null, playing = '', startedMs = 0;

    function rows() {
      return looks ? Array.prototype.slice.call(looks.querySelectorAll('.list > .row')) : [];
    }
    function rowFor(trigger) {
      return rows().filter(function (r) {
        return r.querySelector('select[name$=".trigger"]').value === trigger;
      })[0] || null;
    }
    function mark(r) {
      rows().forEach(function (other) { other.classList.toggle('previewing', other === r); });
    }

    if (looks) {
      ['focusin', 'input', 'change', 'click'].forEach(function (type) {
        looks.addEventListener(type, function (e) {
          var r = e.target.closest && e.target.closest('.list > .row');
          if (r) picked = r;
        });
      });
    }

    // What the dot plays: the picked row; else the row of the trigger the
    // dock last reported, "dark" or "updating" for those two; else Running's
    // row, or the first.
    function current() {
      if (picked && picked.isConnected) return { row: picked };
      var light = box.getAttribute('data-light');
      if (light === 'dark' || light === 'updating') return { state: light, now: true };
      var r = light && rowFor(light);
      if (r) return { row: r, now: true };
      return { row: rowFor('running') || rows()[0] || null };
    }

    function frame(now) {
      requestAnimationFrame(frame);
      if (!box.offsetParent) return;   // its tab is closed
      var c = current(), r = c.row, level = 0, text = 'No pattern', look = '';
      mark(r || null);
      if (c.state === 'dark') {
        text = 'Off';
      } else if (c.state === 'updating') {
        // An update's pulse, as it starts: once a second at a quarter of the light.
        text = 'Updating';
        look = 'updating';
        level = 0.25 * onStep(sine((now - startedMs) % 1000, 1000), ledSteps());
      } else if (r) {
        var trigger = r.querySelector('select[name$=".trigger"]');
        var pattern = r.querySelector('select[name$=".pattern"]');
        var still = pattern.value === 'off' || pattern.value === 'solid';
        var length = Math.round(parseFloat(r.querySelector('input[name$=".length_s"]').value) * 1000);
        look = pattern.value + '/' + length;
        var parts = [trigger.options[trigger.selectedIndex].text,
                     pattern.options[pattern.selectedIndex].text];
        if (!still && length > 0) parts.push((length / 1000) + ' s');
        text = parts.join(' · ');
        if (still) level = ledLevel(pattern.value, 0, 1, 0);
        else if (length > 0) level = ledLevel(pattern.value, (now - startedMs) % length, length, ledSteps());
      }
      // A new look starts from the beginning of its cycle, as on the dock.
      if (look !== playing) {
        playing = look;
        startedMs = now;
      }
      if (c.now) text = 'Now: ' + text;
      var pct = ledBrightness();
      if (!pct) level = 0;
      var size = LED_DOT_MIN_PX + (LED_DOT_MAX_PX - LED_DOT_MIN_PX) * Math.sqrt(pct / 100);
      dot.style.setProperty('--level', level.toFixed(3));
      dot.style.setProperty('--size', size.toFixed(1) + 'px');
      if (words.textContent !== text) words.textContent = text;
    }
    requestAnimationFrame(frame);
  }

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

  // ── The comfort chart: the Comfort page's four edges ─────────────
  // Temperature across, humidity up, as on the Comfort page: the
  // comfortable area hatched, and its four edges dashed, each running on to
  // where its acceptable edges are. Each comfortable edge drags, and the
  // dot at the area's centre moves every edge together. The acceptable
  // edges have no line, so only their fields set them. The room's last six
  // hours trail to its reading now, and the words beside the chart are what
  // the Comfort page would say of it with the edges as drawn.
  var BOXES = [
    { temp: ['comfort.temp_from', 'comfort.temp_to'], rh: ['comfort.rh_from', 'comfort.rh_to'] },
    { temp: ['comfort.acceptable_temp_from', 'comfort.acceptable_temp_to'],
      rh: ['comfort.acceptable_rh_from', 'comfort.acceptable_rh_to'] }
  ];
  var TEMP_SPAN = [14, 30], RH_SPAN = [20, 90];
  // A drag moves an edge in half degrees, and in whole percent: the
  // humidity sensor is good to about 2 %.
  var STEP = { temp: 0.5, rh: 1 };

  function snap(v, axis) {
    return Math.round(v / STEP[axis]) * STEP[axis];
  }

  // A humid edge follows a dew point, as metrics.rh_along_dew_point has it:
  // its setting is the % at the comfortable range's middle temperature.
  var MAGNUS_A = 17.62, MAGNUS_B = 243.12;
  function alongDew(rhAt, atC, t) {
    return rhAt * Math.exp(MAGNUS_A * atC / (MAGNUS_B + atC) - MAGNUS_A * t / (MAGNUS_B + t));
  }
  function centreC() {
    var a = box(0);
    return (a.temp[0] + a.temp[1]) / 2;
  }
  function humidAt(i, t) {
    return alongDew(box(i).rh[1], centreC(), t);
  }

  // ISO 7730's predicted mean vote, as metrics.pmv has it, for the person
  // metrics names: sitting, in a jumper, in still air.
  function pmv(ta, rh) {
    var pa = rh * 10 * Math.exp(16.6536 - 4030.183 / (ta + 235));
    var icl = 0.155 * 1.0, m = 1.1 * 58.15;
    var fcl = icl <= 0.078 ? 1 + 1.29 * icl : 1.05 + 0.645 * icl;
    var hcf = 12.1 * Math.sqrt(0.1), taa = ta + 273;
    var tcla = taa + (35.5 - ta) / (3.5 * icl + 0.1);
    var p1 = icl * fcl, p2 = p1 * 3.96, p3 = p1 * 100, p4 = p1 * taa;
    var p5 = 308.7 - 0.028 * m + p2 * Math.pow(taa / 100, 4);
    var xn = tcla / 100, xf = tcla / 50, hc = hcf;
    for (var i = 0; i < 150 && Math.abs(xn - xf) > 0.00015; i++) {
      xf = (xf + xn) / 2;
      hc = Math.max(hcf, 2.38 * Math.pow(Math.abs(100 * xf - taa), 0.25));
      xn = (p5 + p4 * hc - p2 * Math.pow(xf, 4)) / (100 + p3 * hc);
    }
    var tcl = 100 * xn - 273;
    var loss = 3.05e-3 * (5733 - 6.99 * m - pa) + (m > 58.15 ? 0.42 * (m - 58.15) : 0) +
               1.7e-5 * m * (5867 - pa) + 0.0014 * m * (34 - ta) +
               3.96 * fcl * (Math.pow(xn, 4) - Math.pow(taa / 100, 4)) + fcl * hc * (tcl - ta);
    return (0.303 * Math.exp(-0.036 * m) + 0.028) * (m - loss);
  }

  // The temperature at rh % that feels as tempAt does at 50 %, to 0.01 C,
  // as metrics.temp_along_feel has it: a temperature edge at rh.
  function alongFeel(tempAt, rh) {
    if (rh === 50) return tempAt;
    var target = pmv(tempAt, 50), lo = tempAt - 15, hi = tempAt + 15;
    for (var i = 0; i < 40; i++) {
      var mid = (lo + hi) / 2;
      if (pmv(mid, rh) < target) lo = mid; else hi = mid;
    }
    return Math.round((lo + hi) / 2 * 100) / 100;
  }

  // The setting whose temperature edge passes through t at rh %: edges lie
  // close to parallel, so each step moves the setting by what it misses by.
  function settingThrough(t, rh) {
    var s = t;
    for (var i = 0; i < 3; i++) s += t - alongFeel(s, rh);
    return s;
  }

  // The % where the temperature edge set at tempAt meets the humid edge set
  // at rhAt, as pages/comfort.py finds it.
  function meet(tempAt, rhAt) {
    var c = centreC(), lo = 0, hi = 100;
    if (hi <= alongDew(rhAt, c, alongFeel(tempAt, hi))) return hi;
    for (var i = 0; i < 30; i++) {
      var mid = (lo + hi) / 2;
      if (mid < alongDew(rhAt, c, alongFeel(tempAt, mid))) lo = mid; else hi = mid;
    }
    return (lo + hi) / 2;
  }

  // A temperature edge from rh0 up to rh1 %, and a humid edge from t0 to
  // t1 C, as [t, rh] points.
  function tempLine(tempAt, rh0, rh1) {
    var pts = [[alongFeel(tempAt, rh0), rh0]];
    for (var rh = Math.floor(rh0 / 5 + 1) * 5; rh < rh1; rh += 5) pts.push([alongFeel(tempAt, rh), rh]);
    pts.push([alongFeel(tempAt, rh1), rh1]);
    return pts;
  }
  function humidLine(rhAt, t0, t1) {
    var c = centreC(), pts = [[t0, alongDew(rhAt, c, t0)]];
    for (var t = Math.floor(t0 * 2 + 1) / 2; t < t1; t += 0.5) pts.push([t, alongDew(rhAt, c, t)]);
    pts.push([t1, alongDew(rhAt, c, t1)]);
    return pts;
  }

  function complete() {
    var a = box(0), b = box(1);
    return !isNaN(a.temp[0] + a.temp[1] + a.rh[0] + a.rh[1] + b.temp[0] + b.temp[1] + b.rh[0] + b.rh[1]);
  }

  // Where along its side of the area an edge's word may go, as
  // pages/comfort.py's PLACES.
  var PLACES = [0.2, 0.35, 0.5, 0.65, 0.8];

  // The four comfortable edges, as pages/comfort.py's comfort_lines gives
  // them: each to where its acceptable edges are, with five places for its
  // word on the area's side and the way out from the area.
  function edges() {
    var a = box(0), b = box(1), c = centreC(), dry = a.rh[0], wet = a.rh[1];
    var top0 = meet(a.temp[0], wet), top1 = meet(a.temp[1], wet);
    var h0 = alongFeel(a.temp[0], top0), h1 = alongFeel(a.temp[1], top1);
    function up(tempAt) {
      var top = meet(tempAt, wet);
      return PLACES.map(function (f) {
        var rh = dry + f * (top - dry);
        return [alongFeel(tempAt, rh), rh, alongFeel(tempAt, rh + 1), rh + 1];
      });
    }
    function across(rhOf, t0, t1) {
      return PLACES.map(function (f) {
        var t = t0 + f * (t1 - t0);
        return [t, rhOf(t), t + 0.5, rhOf(t + 0.5)];
      });
    }
    function humid(t) { return alongDew(wet, c, t); }
    function level() { return dry; }
    return [
      { text: 'cool', key: BOXES[0].temp[0], axis: 'temp', out: [-1, 0],
        points: tempLine(a.temp[0], b.rh[0], meet(a.temp[0], b.rh[1])), at: up(a.temp[0]) },
      { text: 'warm', key: BOXES[0].temp[1], axis: 'temp', out: [1, 0],
        points: tempLine(a.temp[1], b.rh[0], meet(a.temp[1], b.rh[1])), at: up(a.temp[1]) },
      { text: 'humid', key: BOXES[0].rh[1], axis: 'rh', out: [0, 1],
        points: humidLine(wet, alongFeel(b.temp[0], meet(b.temp[0], wet)),
                          alongFeel(b.temp[1], meet(b.temp[1], wet))),
        at: across(humid, h0, h1) },
      { text: 'dry', key: BOXES[0].rh[0], axis: 'rh', out: [0, -1],
        points: [[alongFeel(b.temp[0], dry), dry], [alongFeel(b.temp[1], dry), dry]],
        at: across(level, alongFeel(a.temp[0], dry), alongFeel(a.temp[1], dry)) }
    ];
  }

  // The comfortable area's outline: up the cool edge, along the humid edge,
  // down the warm edge.
  function area() {
    var a = box(0), dry = a.rh[0], wet = a.rh[1];
    var top0 = meet(a.temp[0], wet), top1 = meet(a.temp[1], wet);
    return tempLine(a.temp[0], dry, top0)
      .concat(humidLine(wet, alongFeel(a.temp[0], top0), alongFeel(a.temp[1], top1)).slice(1, -1))
      .concat(tempLine(a.temp[1], dry, top1).reverse());
  }

  function real(name) {
    var el = input(name);
    if (!el) return NaN;
    return parseFloat(el.value || el.getAttribute('data-default') || '');
  }

  function box(i) {
    var b = BOXES[i];
    return { temp: b.temp.map(real), rh: b.rh.map(real) };
  }

  // A value's band, low to high: beyond the acceptable range, between the
  // ranges, or inside the comfortable one, as metrics.Comfort counts them.
  function band(v, inner, outer, names) {
    if (v < outer[0]) return names[0];
    if (v < inner[0]) return names[1];
    if (v > outer[1]) return names[4];
    if (v > inner[1]) return names[3];
    return names[2];
  }

  // The Comfort page's sentence, from metrics.VERDICTS on the canvas.
  function comfortWords(t, rh, table) {
    var inner = box(0), outer = box(1);
    function at(e) { return alongFeel(e, rh); }
    var row = table.words[band(t, inner.temp.map(at), outer.temp.map(at), table.temp)];
    var wet = band(rh, [inner.rh[0], humidAt(0, t)], [outer.rh[0], humidAt(1, t)], table.rh);
    return row[table.rh.indexOf(wet)];
  }

  function ComfortChart(canvas) {
    this.canvas = canvas;
    this.drag = null;
    this.trail = [];
    this.now = document.getElementById('comfort-now');
    this.verdicts = JSON.parse(canvas.getAttribute('data-verdicts') || 'null');
    var self = this;
    canvas.addEventListener('pointerdown', function (e) { self.down(e); });
    canvas.addEventListener('pointermove', function (e) { self.move(e); });
    canvas.addEventListener('pointerup', function () { self.drag = null; });
    canvas.addEventListener('pointercancel', function () { self.drag = null; });
    canvas.addEventListener('pointerleave', function () { if (!self.drag) canvas.style.cursor = ''; });
    // The server's /history: temperature, with humidity as its second line.
    fetch('../history?metric=temperature&span=21600').then(function (r) {
      return r.ok ? r.json() : null;
    }).then(function (h) {
      if (!h) return;
      var rh = {};
      (h.spec.points2 || []).forEach(function (p) { rh[p[0]] = p[1]; });
      self.trail = h.spec.points.filter(function (p) { return rh[p[0]] !== undefined; })
        .map(function (p) { return [p[1], rh[p[0]]]; });
      self.draw();
    }).catch(function () {});
  }

  ComfortChart.prototype.geometry = function () {
    var r = this.canvas.getBoundingClientRect();
    var m = { l: 42, r: 10, t: 10, b: 30 };
    function scale(span, a, b) {
      return {
        at: function (v) { return a + (v - span[0]) / (span[1] - span[0]) * (b - a); },
        of: function (px) { return span[0] + (px - a) / (b - a) * (span[1] - span[0]); }
      };
    }
    return { m: m, w: r.width, h: r.height,
             x: scale(TEMP_SPAN, m.l, r.width - m.r), y: scale(RH_SPAN, r.height - m.b, m.t) };
  };

  ComfortChart.prototype.draw = function () {
    var p = prepare(this.canvas);
    if (!p.w) return;
    var g = this.geometry();
    function px(pts) { return pts.map(function (q) { return [g.x.at(q[0]), g.y.at(q[1])]; }); }
    var lines = complete() ? edges() : [];
    // As the Comfort page draws them: the area hatched light, the edges
    // dashed, cut at the plot's frame.
    if (lines.length) {
      p.rc.polygon(px(area()), { stroke: 'none', fill: G[5], fillStyle: 'hachure', hachureGap: 7,
                                 hachureAngle: 45, fillWeight: 1, roughness: 1.2 });
      p.ctx.save();
      p.ctx.beginPath();
      p.ctx.rect(g.m.l, g.m.t, g.w - g.m.l - g.m.r, g.h - g.m.t - g.m.b);
      p.ctx.clip();
      lines.forEach(function (l) {
        p.rc.curve(px(l.points), { stroke: G[2], strokeWidth: 1.6, strokeLineDash: [6, 5], roughness: 0.8,
                                   bowing: 0.5 });
      });
      p.ctx.restore();
    }
    var axisY = g.h - g.m.b;
    p.rc.line(g.m.l, g.m.t, g.m.l, axisY, { stroke: G[2], strokeWidth: 1.6, roughness: 0.8 });
    p.rc.line(g.m.l, axisY, g.w - g.m.r, axisY, { stroke: G[2], strokeWidth: 1.6, roughness: 0.8 });
    [16, 20, 24, 28].forEach(function (t) {
      text(p.ctx, t + '°', g.x.at(t), axisY + 16, { size: 13, color: G[2] });
    });
    [30, 50, 70, 90].forEach(function (v) {
      text(p.ctx, v + '%', g.m.l - 8, g.y.at(v), { size: 13, color: G[2], align: 'right' });
    });

    var n = this.trail.length;
    this.trail.forEach(function (pt, i) {
      p.ctx.fillStyle = i === n - 1 ? G[0] : G[5 - Math.round(3 * i / Math.max(1, n - 1))];
      p.ctx.beginPath();
      p.ctx.arc(g.x.at(pt[0]), g.y.at(pt[1]), i === n - 1 ? 5 : 3, 0, 2 * Math.PI);
      p.ctx.fill();
    });
    if (n) {
      var last = this.trail[n - 1];
      p.rc.circle(g.x.at(last[0]), g.y.at(last[1]), 22, { stroke: G[0], strokeWidth: 1.5, roughness: 1 });
    }
    this.edgeWords(p, g, lines);
    var dot = this.dot();
    if (dot) {
      p.ctx.save();
      p.ctx.fillStyle = G[1];
      p.ctx.strokeStyle = G[7];
      p.ctx.lineWidth = 2;
      p.ctx.beginPath();
      p.ctx.arc(dot.x, dot.y, 6, 0, 2 * Math.PI);
      p.ctx.fill();
      p.ctx.stroke();
      p.ctx.restore();
    }
    this.words();
  };

  // Each edge's word on a white card on the far side of the edge from the
  // area, at its place farthest from the room's last hours, as the Comfort
  // page writes them.
  ComfortChart.prototype.edgeWords = function (p, g, lines) {
    var seen = this.trail.map(function (q) { return [g.x.at(q[0]), g.y.at(q[1])]; });
    p.ctx.font = 'italic 500 12px ' + FONT;
    lines.forEach(function (l) {
      var at = l.at.map(function (q) {
        var x0 = g.x.at(q[0]), y0 = g.y.at(q[1]);
        return [x0, y0, Math.atan2(g.y.at(q[3]) - y0, g.x.at(q[2]) - x0)];
      });
      var best = at[2], far = -1;
      if (seen.length) at.forEach(function (q) {
        var d = Math.min.apply(null, seen.map(function (s) { return Math.hypot(q[0] - s[0], q[1] - s[1]); }));
        if (d > far) { far = d; best = q; }
      });
      var ang = best[2];
      if (ang > Math.PI / 2) ang -= Math.PI;
      if (ang <= -Math.PI / 2) ang += Math.PI;
      var side = -Math.sin(ang) * l.out[0] - Math.cos(ang) * l.out[1] >= 0 ? 1 : -1;
      var cw = p.ctx.measureText(l.text).width + 10, off = side * 13;
      p.ctx.save();
      p.ctx.translate(best[0], best[1]);
      p.ctx.rotate(ang);
      p.ctx.fillStyle = G[7];
      p.ctx.beginPath();
      if (p.ctx.roundRect) p.ctx.roundRect(-cw / 2, off - 9, cw, 18, 4); else p.ctx.rect(-cw / 2, off - 9, cw, 18);
      p.ctx.fill();
      text(p.ctx, l.text, 0, off, { size: 12, italic: true, color: G[1] });
      p.ctx.restore();
    });
  };

  // The reading now, and the Comfort page's words for it with these edges.
  ComfortChart.prototype.words = function () {
    if (!this.now) return;
    var last = this.trail[this.trail.length - 1];
    var t = this.now.querySelector('.now-temp'), rh = this.now.querySelector('.now-rh');
    var verdict = this.now.querySelector('.verdict');
    if (!last || !this.verdicts) {
      verdict.textContent = last ? '' : 'No reading yet.';
      return;
    }
    // Judged as shown, as the Comfort page judges it.
    t.textContent = last[0].toFixed(1);
    rh.textContent = last[1].toFixed(0);
    verdict.textContent = comfortWords(parseFloat(t.textContent), parseFloat(rh.textContent),
                                       this.verdicts);
  };

  // The comfortable edge under a point: the nearest within 9 pixels, along
  // the part of it that is drawn.
  ComfortChart.prototype.edgeAt = function (x, y) {
    if (!complete()) return null;
    var g = this.geometry(), best = null, t = g.x.of(x), rh = g.y.of(y);
    edges().forEach(function (l) {
      var first = l.points[0], end = l.points[l.points.length - 1], d;
      if (l.axis === 'temp') {
        if (y > g.y.at(first[1]) + 8 || y < g.y.at(end[1]) - 8) return;
        d = Math.abs(x - g.x.at(alongFeel(real(l.key), rh)));
      } else {
        if (x < g.x.at(first[0]) - 8 || x > g.x.at(end[0]) + 8) return;
        d = Math.abs(y - g.y.at(l.text === 'humid' ? humidAt(0, t) : real(l.key)));
      }
      if (d <= 9 && (!best || d < best.d)) best = { key: l.key, axis: l.axis, d: d };
    });
    return best;
  };

  // The dot that moves every edge: at the comfortable ranges' centre.
  ComfortChart.prototype.dot = function () {
    var g = this.geometry(), a = box(0);
    if (isNaN(a.temp[0] + a.temp[1] + a.rh[0] + a.rh[1])) return null;
    return { x: g.x.at((a.temp[0] + a.temp[1]) / 2), y: g.y.at((a.rh[0] + a.rh[1]) / 2) };
  };

  // What a press at a point takes hold of: the dot, else an edge.
  ComfortChart.prototype.handleAt = function (x, y) {
    var dot = this.dot();
    if (dot && Math.abs(x - dot.x) <= 9 && Math.abs(y - dot.y) <= 9) return { both: true };
    return this.edgeAt(x, y);
  };

  ComfortChart.prototype.down = function (e) {
    var r = this.canvas.getBoundingClientRect();
    var x = e.clientX - r.left, y = e.clientY - r.top;
    var hold = this.handleAt(x, y);
    if (!hold) return;
    var keys = hold.key ? [hold.key] : BOXES[0].temp.concat(BOXES[0].rh, BOXES[1].temp, BOXES[1].rh);
    if (keys.some(locked)) return;
    if (!hold.key) hold.from = { x: x, y: y, inner: box(0), outer: box(1) };
    this.drag = hold;
    this.canvas.setPointerCapture(e.pointerId);
    e.preventDefault();
  };

  // The dot moves every edge, in steps, within the chart.
  ComfortChart.prototype.moveBox = function (x, y) {
    var g = this.geometry(), f = this.drag.from;
    var by = { temp: snap(g.x.of(x) - g.x.of(f.x), 'temp'), rh: snap(g.y.of(y) - g.y.of(f.y), 'rh') };
    ['temp', 'rh'].forEach(function (axis) {
      var span = axis === 'temp' ? TEMP_SPAN : RH_SPAN;
      var d = Math.max(span[0] - f.outer[axis][0], Math.min(span[1] - f.outer[axis][1], by[axis]));
      var inner = BOXES[0][axis], outer = BOXES[1][axis];
      // Outer edge, inner edge, inner edge, outer edge, leading side first.
      var steps = [[outer, f.outer, 1], [inner, f.inner, 1], [inner, f.inner, 0], [outer, f.outer, 0]];
      if (d < 0) steps = steps.map(function (st) { return [st[0], st[1], 1 - st[2]]; });
      steps.forEach(function (st) { set(st[0][st[2]], st[1][axis][st[2]] + d); });
    });
  };

  // An edge moves in steps, between its acceptable edge and the comfortable
  // edge opposite. With nothing held, the pointer shows what a press would
  // take.
  ComfortChart.prototype.move = function (e) {
    var r = this.canvas.getBoundingClientRect(), g = this.geometry();
    var x = e.clientX - r.left, y = e.clientY - r.top;
    if (!this.drag) {
      var hold = this.handleAt(x, y);
      this.canvas.style.cursor = !hold ? '' : !hold.key ? 'move'
        : hold.axis === 'temp' ? 'ew-resize' : 'ns-resize';
      return;
    }
    if (!this.drag.key) {
      this.moveBox(x, y);
      return;
    }
    var key = this.drag.key, axis = this.drag.axis;
    var inner = BOXES[0][axis], outer = BOXES[1][axis];
    var t = g.x.of(x), rh = g.y.of(y);
    // A temperature edge is set by the setting whose edge passes under the
    // pointer; the humid edge by the dew point under the pointer, as the %
    // it gives at the middle temperature.
    var v = axis === 'temp' ? settingThrough(t, rh)
      : key === inner[1] ? alongDew(rh, t, centreC()) : rh;
    v = snap(v, axis);
    var limits = {};
    limits[inner[0]] = [real(outer[0]), real(inner[1]) - STEP[axis]];
    limits[inner[1]] = [real(inner[0]) + STEP[axis], real(outer[1])];
    if (key === inner[1] && axis === 'rh') {
      // Above the dry edge where the warm edge meets it, where the humid
      // edge is lowest.
      var a = box(0);
      limits[key][0] = Math.max(limits[key][0],
        Math.ceil((a.rh[0] + 1) / alongDew(1, centreC(), alongFeel(a.temp[1], a.rh[0]))));
    }
    set(key, Math.max(limits[key][0], Math.min(limits[key][1], v)));
  };

  // ── Wiring ───────────────────────────────────────────────────────
  var drawings = [];
  document.querySelectorAll('canvas[data-visual]').forEach(function (canvas) {
    var kind = canvas.getAttribute('data-visual');
    if (kind === 'dial') drawings.push(new Dial(canvas));
    if (kind === 'slot') drawings.push(new Strip(canvas));
    if (kind === 'start') drawings.push(new Start(canvas));
    if (kind === 'panel') drawings.push(new Panel(canvas));
    if (kind === 'disk') drawings.push(new Disk(canvas));
    if (kind === 'comfort') drawings.push(new ComfortChart(canvas));
  });
  var ledPreview = document.querySelector('[data-visual="led"]');
  if (ledPreview) LedPreview(ledPreview);
  if (!drawings.length && !grids.length) return;

  function redraw() {
    drawings.forEach(function (d) { d.draw(); });
    markGrids();
  }
  form.addEventListener('input', redraw);
  form.addEventListener('change', redraw);
  // config.js asks for one when what a drawing shows changes without an
  // input: an import, or another group of days chosen.
  form.addEventListener('redraw', redraw);
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
