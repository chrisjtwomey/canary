/* The browse page: the page the URL's fragment names, scaled to the stage.
   It asks the server every 10 s whether the page's data has changed, and
   loads the new page behind the one on show before it swaps them. The
   whole browse page loads again when the server has restarted. The arrow
   keys step through the menu. */
(function () {
  'use strict';

  var POLL_MS = 10000;
  var frame = document.getElementById('page');
  var coming = null;    // the new page, while it loads behind the one on show
  var shown = null;     // the stamp of the data the page on show was built from
  var started = null;   // when the server started, as it first said
  var stage = document.getElementById('stage');
  var links = Array.prototype.slice.call(document.querySelectorAll('nav a[data-page]'));
  var names = links.map(function (a) { return a.getAttribute('data-page'); });
  // A phone gets each page upright, at the size web.py's PORTRAIT renders.
  var PANEL = { w: +frame.getAttribute('width'), h: +frame.getAttribute('height') };
  var PORTRAIT = { w: 540, h: 960 };
  var phone = window.matchMedia('(max-width: 640px)');

  function size() { return phone.matches ? PORTRAIT : PANEL; }

  function current() {
    var name = decodeURIComponent(location.hash.slice(1));
    return names.indexOf(name) >= 0 ? name : names[0];
  }

  function show() {
    var name = current();
    var link = links[names.indexOf(name)];
    var src = phone.matches ? name + '?shape=portrait' : name;
    if (frame.getAttribute('src') !== src) {
      drop();
      frame.setAttribute('src', src);
      shown = null;
      poll();
    }
    frame.setAttribute('width', size().w);
    frame.setAttribute('height', size().h);
    fit();
    links.forEach(function (a) {
      if (a === link) a.setAttribute('aria-current', 'page');
      else a.removeAttribute('aria-current');
    });
    var span = link.closest('.links[id]');
    var radio = span && document.getElementById(span.id.replace('links-', 'span-'));
    if (radio) radio.checked = true;
    frame.title = link.textContent;
    document.getElementById('here-name').textContent = link.textContent;
    document.getElementById('menu-open').checked = false;
    document.title = link.textContent + ' · Canary';
  }

  function fit() {
    var k = Math.min(1, stage.clientWidth / size().w);
    frame.style.transform = 'scale(' + k + ')';
    if (coming) coming.style.transform = frame.style.transform;
    stage.style.height = Math.ceil(size().h * k) + 'px';
  }

  function step(by) {
    var i = names.indexOf(current());
    location.hash = names[(i + by + names.length) % names.length];
  }

  function onKey(e) {
    if (e.altKey || e.ctrlKey || e.metaKey) return;
    if (e.key === 'ArrowRight') step(1);
    else if (e.key === 'ArrowLeft') step(-1);
  }

  // The switch shows the same measurement over the other span, so it moves
  // the page with it.
  var spans = Array.prototype.slice.call(document.querySelectorAll('.bar .spans input'));

  function pagesIn(radio) {
    var box = document.getElementById(radio.id.replace('span-', 'links-'));
    return Array.prototype.map.call(box.querySelectorAll('a[data-page]'), function (a) {
      return a.getAttribute('data-page');
    });
  }

  spans.forEach(function (radio, i) {
    radio.addEventListener('change', function () {
      var was = pagesIn(spans[1 - i]).indexOf(current());
      if (was >= 0) location.hash = pagesIn(radio)[was];
    });
  });

  document.getElementById('prev').addEventListener('click', function () { step(-1); });
  document.getElementById('next').addEventListener('click', function () { step(1); });
  window.addEventListener('hashchange', show);
  phone.addEventListener('change', show);
  window.addEventListener('resize', fit);
  document.addEventListener('keydown', onKey);
  // A click on the page gives it the focus, and its keys with it.
  function takeKeys(f) {
    f.addEventListener('load', function () {
      f.contentDocument.addEventListener('keydown', onKey);
    });
  }

  function drop() {
    if (coming) coming.remove();
    coming = null;
  }

  function swap() {
    drop();
    var next = coming = frame.cloneNode(false);
    next.style.position = 'absolute';
    next.style.top = next.style.left = '0';
    next.style.visibility = 'hidden';
    takeKeys(next);
    next.addEventListener('load', function () {
      if (next !== coming) return;
      next.style.position = next.style.top = next.style.left = next.style.visibility = '';
      frame.remove();
      frame = next;
      coming = null;
    });
    stage.appendChild(next);
  }

  function poll() {
    if (document.hidden) return;
    var asked = frame.getAttribute('src').split('?')[0];
    fetch('stamp?page=' + encodeURIComponent(asked), { cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (s) {
        if (!s || asked !== frame.getAttribute('src').split('?')[0]) return;
        if (started !== null && s.started !== started) {
          location.reload();
          return;
        }
        started = s.started;
        if (shown !== null && s.stamp !== shown) swap();
        shown = s.stamp;
      })
      .catch(function () {});
  }

  takeKeys(frame);
  setInterval(poll, POLL_MS);

  show();
  fit();
  poll();
})();
