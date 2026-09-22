/* The browse page: the page the URL's fragment names, scaled to the stage,
   reloaded every minute. The arrow keys step through the menu. */
(function () {
  'use strict';

  var RELOAD_MS = 60000;
  var frame = document.getElementById('page');
  var stage = document.getElementById('stage');
  var links = Array.prototype.slice.call(document.querySelectorAll('nav a[data-page]'));
  var names = links.map(function (a) { return a.getAttribute('data-page'); });
  var W = +frame.getAttribute('width');
  var H = +frame.getAttribute('height');

  function current() {
    var name = decodeURIComponent(location.hash.slice(1));
    return names.indexOf(name) >= 0 ? name : names[0];
  }

  function show() {
    var name = current();
    var link = links[names.indexOf(name)];
    if (frame.getAttribute('src') !== name) frame.setAttribute('src', name);
    links.forEach(function (a) {
      if (a === link) a.setAttribute('aria-current', 'page');
      else a.removeAttribute('aria-current');
    });
    var span = link.closest('.links[id]');
    var radio = span && document.getElementById(span.id.replace('links-', 'span-'));
    if (radio) radio.checked = true;
    frame.title = link.textContent;
    document.title = link.textContent + ' · Canary';
  }

  function fit() {
    var k = Math.min(1, stage.clientWidth / W);
    frame.style.transform = 'scale(' + k + ')';
    stage.style.height = Math.ceil(H * k) + 'px';
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

  window.addEventListener('hashchange', show);
  window.addEventListener('resize', fit);
  document.addEventListener('keydown', onKey);
  // A click on the page gives it the focus, and its keys with it.
  frame.addEventListener('load', function () {
    frame.contentDocument.addEventListener('keydown', onKey);
  });
  setInterval(function () {
    if (!document.hidden) frame.contentWindow.location.reload();
  }, RELOAD_MS);

  show();
  fit();
})();
