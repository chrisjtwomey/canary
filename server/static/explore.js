/* The explorer: one measurement over a window the viewer moves.

   The URL holds the view (metric, span, and to when it is not now), so a
   view can be bookmarked. Each change asks /history for the window's spec
   and charts.js draws it. While a drag or a zoom is under way the last
   drawing is stretched to the new window, and the new one is fetched when
   the pointer settles. A window that ends now is fetched again every
   minute, and within 10 s of a new reading. */
(function () {
  'use strict';

  var HOUR = 3600;
  var MIN_SPAN = HOUR;
  var MAX_SPAN = 92 * 24 * HOUR;
  var RELOAD_MS = 60000;
  var POLL_MS = 10000;
  var SETTLE_MS = 250;
  var G = Charts.grey;

  var chart = document.getElementById('chart');
  var base = document.getElementById('trace');
  var overlay = document.getElementById('overlay');
  var hero = document.getElementById('hero');

  var view = fromUrl();   // { metric, span, to }; to is null while the window ends now
  var data = null;        // the last /history answer drawn
  var plot = null;        // its plot's edges on the canvas, from charts.js
  var asked = 0;          // the newest request, so a slow older answer is dropped
  var settle = null;

  function clampSpan(span) {
    return Math.round(Math.min(MAX_SPAN, Math.max(MIN_SPAN, span)));
  }

  function fromUrl() {
    var q = new URLSearchParams(location.search);
    return {
      metric: q.get('metric') || 'co2',
      span: clampSpan(+q.get('span') || 24 * HOUR),
      to: q.get('to') ? +q.get('to') : null
    };
  }

  function toUrl() {
    var q = new URLSearchParams({ metric: view.metric, span: view.span });
    if (view.to !== null) q.set('to', view.to);
    history.replaceState(null, '', '?' + q.toString());
  }

  // The end of the window as a time, whether or not it follows now.
  function end() {
    if (view.to !== null) return view.to;
    return data ? data.now : Math.floor(Date.now() / 1000);
  }

  // A window that would end after now follows now instead.
  function setEnd(to) {
    var now = data ? data.now : Math.floor(Date.now() / 1000);
    view.to = to >= now ? null : Math.round(to);
  }

  function pressed() {
    document.querySelectorAll('#measures button').forEach(function (b) {
      b.setAttribute('aria-pressed', String(b.getAttribute('data-metric') === view.metric));
    });
    document.querySelectorAll('#windows button').forEach(function (b) {
      b.setAttribute('aria-pressed', String(+b.getAttribute('data-hours') * HOUR === view.span));
    });
    document.getElementById('later').disabled = view.to === null;
    document.getElementById('latest').disabled = view.to === null;
  }

  function load() {
    clearTimeout(settle);
    toUrl();
    pressed();
    var q = new URLSearchParams({ metric: view.metric, span: view.span });
    if (view.to !== null) q.set('to', view.to);
    var mine = ++asked;
    chart.classList.add('loading');
    fetch('../history?' + q.toString())
      .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
      .then(function (answer) {
        if (mine !== asked) return;
        data = answer;
        draw();
      })
      .catch(function () {
        if (mine === asked) document.getElementById('detail').textContent = 'Cannot reach the server. Pick a window again to retry.';
      })
      .then(function () {
        if (mine === asked) chart.classList.remove('loading');
      });
  }

  function loadSoon() {
    clearTimeout(settle);
    settle = setTimeout(load, SETTLE_MS);
  }

  // ── Drawing ──────────────────────────────────────────────────────

  function draw() {
    if (!data) return;
    base.style.transform = '';
    plot = Charts.draw(base, data.spec);
    document.getElementById('title').textContent = data.title;
    document.getElementById('stamp').textContent = data.stamp;
    document.getElementById('detail').textContent = data.detail;
    clearCursor();
    readout(null);
  }

  // Stretch the last drawing onto the window the view has moved to.
  function preview() {
    if (!data || !plot) return;
    var width = plot.r - plot.l;
    var oldSpan = data.to - data.from;
    var from = end() - view.span;
    var k = oldSpan / view.span;
    var shift = plot.l - k * plot.l + (data.from - from) / view.span * width;
    base.style.transform = 'translateX(' + shift + 'px) scaleX(' + k + ')';
    clearCursor();
  }

  function timeAt(x) {
    return data.from + (x - plot.l) / (plot.r - plot.l) * (data.to - data.from);
  }

  function xAt(ts) {
    return plot.l + (ts - data.from) / (data.to - data.from) * (plot.r - plot.l);
  }

  function nearest(points, ts) {
    if (!points || !points.length) return null;
    var lo = 0, hi = points.length - 1;
    while (hi - lo > 1) {
      var mid = (lo + hi) >> 1;
      if (points[mid][0] < ts) lo = mid; else hi = mid;
    }
    return Math.abs(points[lo][0] - ts) <= Math.abs(points[hi][0] - ts) ? points[lo] : points[hi];
  }

  function yAt(v) {
    var y = data.spec.y;
    return plot.b - (v - y.min) / ((y.max - y.min) || 1) * (plot.b - plot.t);
  }

  function overlayContext() {
    var r = overlay.getBoundingClientRect();
    var k = window.devicePixelRatio || 1;
    if (overlay.width !== Math.round(r.width * k)) overlay.width = Math.round(r.width * k);
    if (overlay.height !== Math.round(r.height * k)) overlay.height = Math.round(r.height * k);
    var ctx = overlay.getContext('2d');
    ctx.setTransform(k, 0, 0, k, 0, 0);
    ctx.clearRect(0, 0, r.width, r.height);
    return ctx;
  }

  function clearCursor() {
    overlayContext();
  }

  function cursor(p) {
    var ctx = overlayContext();
    var x = xAt(p[0]), y = yAt(p[1]);
    ctx.save();
    ctx.strokeStyle = G[2];
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(x, plot.t);
    ctx.lineTo(x, plot.b);
    ctx.stroke();
    ctx.restore();
    [[11, G[7]], [7, G[0]]].forEach(function (ring) {
      ctx.beginPath();
      ctx.arc(x, y, ring[0], 0, Math.PI * 2);
      ctx.fillStyle = ring[1];
      ctx.fill();
    });
  }

  var MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

  // "Tue 22 Sep, 09:48" in the server's zone, as the server writes its stamps.
  function clock(ts) {
    var part = {};
    new Intl.DateTimeFormat('en-GB', {
      timeZone: data.tz, weekday: 'short', day: 'numeric', month: 'numeric',
      hour: '2-digit', minute: '2-digit', hourCycle: 'h23'
    }).formatToParts(new Date(ts * 1000)).forEach(function (p) { part[p.type] = p.value; });
    return part.weekday + ' ' + (+part.day) + ' ' + MONTHS[part.month - 1] + ', ' +
           part.hour + ':' + part.minute;
  }

  // The hero shows the point under the pointer, or the window's last one.
  function readout(p) {
    var pts = data.spec.points;
    var shown = p || pts[pts.length - 1] || null;
    var value = hero.querySelector('.value');
    hero.querySelector('.unit').textContent = data.unit;
    var when = document.getElementById('when');
    if (!shown) {
      value.textContent = '—';
      when.textContent = '';
      return;
    }
    // As the pages write them: a comma in a whole number, none in a decimal.
    value.textContent = data.decimals ? shown[1].toFixed(data.decimals)
                                      : Math.round(shown[1]).toLocaleString('en-GB');
    var words = (p || !data.spec.now ? '' : 'Now, ') + clock(shown[0]);
    var second = data.second && nearest(data.spec.points2, shown[0]);
    if (second) {
      words += ' · ' + Math.round(second[1]) + ' ' + data.second.unit + ' ' +
               data.second.title.toLowerCase();
    }
    when.textContent = words;
  }

  // ── Moving through time ──────────────────────────────────────────

  var pointers = {};
  var drag = null;
  var pinch = null;

  function count() { return Object.keys(pointers).length; }

  function spread() {
    var p = Object.keys(pointers).map(function (id) { return pointers[id]; });
    return { d: Math.abs(p[0].clientX - p[1].clientX) || 1, x: (p[0].offsetX + p[1].offsetX) / 2 };
  }

  // Zoom by k about the time ts, from the view held at the gesture's start.
  function zoom(ts, k, span0, end0) {
    var span = clampSpan(span0 * k);
    var from0 = end0 - span0;
    var from = ts - (ts - from0) / span0 * span;
    view.span = span;
    setEnd(from + span);
    preview();
  }

  overlay.addEventListener('pointerdown', function (e) {
    if (!data) return;
    overlay.setPointerCapture(e.pointerId);
    pointers[e.pointerId] = e;
    if (count() === 2) {
      var s = spread();
      pinch = { d0: s.d, ts: timeAt(s.x), span0: view.span, end0: end() };
      drag = null;
    } else if (count() === 1) {
      drag = { x0: e.clientX, end0: end(), moved: false };
      overlay.classList.add('dragging');
    }
  });

  overlay.addEventListener('pointermove', function (e) {
    if (!data || !plot) return;
    if (pointers[e.pointerId]) pointers[e.pointerId] = e;
    if (pinch && count() === 2) {
      zoom(pinch.ts, pinch.d0 / spread().d, pinch.span0, pinch.end0);
    } else if (drag) {
      var dx = e.clientX - drag.x0;
      if (Math.abs(dx) > 3) drag.moved = true;
      if (drag.moved) {
        setEnd(drag.end0 - dx / (plot.r - plot.l) * view.span);
        preview();
      }
    } else if (e.pointerType === 'mouse') {
      var p = nearest(data.spec.points, timeAt(e.offsetX));
      if (p) {
        cursor(p);
        readout(p);
      }
    }
  });

  function release(e) {
    delete pointers[e.pointerId];
    overlay.classList.remove('dragging');
    if (pinch) {
      if (count() < 2) {
        pinch = null;
        drag = null;
        loadSoon();
      }
      return;
    }
    if (drag && drag.moved) {
      load();
    } else if (drag && e.pointerType !== 'mouse') {
      var p = nearest(data.spec.points, timeAt(e.offsetX));
      if (p) {
        cursor(p);
        readout(p);
      }
    }
    drag = null;
  }

  overlay.addEventListener('pointerup', release);
  overlay.addEventListener('pointercancel', release);
  overlay.addEventListener('pointerleave', function (e) {
    if (e.pointerType === 'mouse' && !drag && data) {
      clearCursor();
      readout(null);
    }
  });

  // A trackpad's pinch arrives as a wheel event with ctrlKey set.
  overlay.addEventListener('wheel', function (e) {
    if (!data || !plot) return;
    e.preventDefault();
    var k = Math.exp(e.deltaY * (e.ctrlKey ? 0.01 : 0.002));
    zoom(timeAt(e.offsetX), k, view.span, end());
    loadSoon();
  }, { passive: false });

  // ── Controls ─────────────────────────────────────────────────────

  document.getElementById('measures').addEventListener('click', function (e) {
    var metric = e.target.getAttribute('data-metric');
    if (!metric) return;
    view.metric = metric;
    load();
  });

  document.getElementById('windows').addEventListener('click', function (e) {
    var hours = +e.target.getAttribute('data-hours');
    if (!hours) return;
    view.span = clampSpan(hours * HOUR);
    load();
  });

  document.getElementById('earlier').addEventListener('click', function () {
    setEnd(end() - view.span);
    load();
  });

  document.getElementById('later').addEventListener('click', function () {
    setEnd(end() + view.span);
    load();
  });

  document.getElementById('latest').addEventListener('click', function () {
    view.to = null;
    load();
  });

  document.addEventListener('keydown', function (e) {
    if (e.altKey || e.ctrlKey || e.metaKey) return;
    if (e.key === 'ArrowLeft') document.getElementById('earlier').click();
    else if (e.key === 'ArrowRight' && view.to !== null) document.getElementById('later').click();
  });

  var resized = null;
  window.addEventListener('resize', function () {
    clearTimeout(resized);
    resized = setTimeout(draw, 150);
  });

  function following() { return view.to === null && !document.hidden && !drag && !pinch; }

  setInterval(function () {
    if (following()) load();
  }, RELOAD_MS);

  var stamp = null;   // the newest reading's, as the server last said
  setInterval(function () {
    if (!following()) return;
    fetch('stamp', { cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (s) {
        if (!s) return;
        if (stamp !== null && s.stamp !== stamp && following()) load();
        stamp = s.stamp;
      })
      .catch(function () {});
  }, POLL_MS);

  Promise.all([
    document.fonts.load('500 18px Fraunces'),
    document.fonts.load('italic 500 18px Fraunces')
  ]).then(load, load);
})();
