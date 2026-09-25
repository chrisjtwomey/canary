/* Each span marked data-age counts on from the moment the page got it, and
   each marked data-in counts down to "now", in the words metrics.py's
   fmt_duration uses. The count starts from this browser's clock, so a clock
   that differs from the server's does not change it. */
(function () {
  'use strict';

  function words(seconds) {
    var s = Math.floor(seconds);
    if (s < 60) return s + ' s';
    var m = Math.floor(s / 60);
    if (m < 60) return m + ' min';
    var h = Math.floor(m / 60);
    m %= 60;
    if (h < 24) return m ? h + ' h ' + m + ' min' : h + ' h';
    var d = Math.floor(h / 24);
    h %= 24;
    return h ? d + ' d ' + h + ' h' : d + ' d';
  }

  function tick() {
    var now = Date.now();
    document.querySelectorAll('[data-age]').forEach(function (el) {
      if (el._since === undefined) el._since = now;
      var text = words(+el.getAttribute('data-age') + (now - el._since) / 1000);
      if (el.textContent !== text) el.textContent = text;
    });
    document.querySelectorAll('[data-in]').forEach(function (el) {
      if (el._since === undefined) el._since = now;
      var left = +el.getAttribute('data-in') - (now - el._since) / 1000;
      var text = left >= 1 ? words(left) : 'now';
      if (el.textContent !== text) el.textContent = text;
    });
  }

  setInterval(tick, 1000);
})();
