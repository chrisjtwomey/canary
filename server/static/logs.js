/* The Logs view: what the boards log, oldest at the top and newest at the
   end. It asks /logs for the newest lines, then every two seconds for the
   ones after them, and for the ones before when asked to show earlier lines.
   While the reader is at the end, new lines keep it there. */
(function () {
  'use strict';

  var POLL_MS = 2000;
  var PAGE = 200;
  var box = document.getElementById('log');
  var list = document.getElementById('lines');
  var empty = document.getElementById('empty');
  var earlierButton = document.getElementById('earlier');
  var newestButton = document.getElementById('newest');
  var status = document.getElementById('status');
  var board = document.getElementById('board');
  var level = document.getElementById('level');
  var find = document.getElementById('find');

  var tz = 'UTC';
  var first = null, last = null;          // the numbers of the lines shown at each end
  var firstDay = null, lastDay = null;    // the day each end is in
  var asked = 0;                          // bumped by a new filter, so old answers are dropped

  function get(extra) {
    var q = new URLSearchParams(extra);
    if (board.value) q.set('board', board.value);
    if (level.value) q.set('level', level.value);
    if (find.value.trim()) q.set('q', find.value.trim());
    return fetch('../logs?' + q.toString()).then(function (r) {
      return r.ok ? r.json() : Promise.reject(r.status);
    });
  }

  function format(ts, parts) {
    return new Intl.DateTimeFormat('en-GB', Object.assign({ timeZone: tz }, parts))
      .format(new Date(ts * 1000));
  }

  function dayOf(ts) { return format(ts, { weekday: 'short', day: 'numeric', month: 'short' }); }

  function cell(tag, className, text) {
    var el = document.createElement(tag);
    el.className = className;
    el.textContent = text;
    return el;
  }

  // A board's own stamp, before the level: the time column already says when.
  var BOARD_STAMP = /^\S+ - (?=(DEBUG|INFO|NOTICE|WARNING|ERROR|CRITICAL) - )/;

  function lineRow(line) {
    var li = document.createElement('li');
    li.className = 'line' + (line.level ? ' lv-' + line.level.toLowerCase() : '');
    li.title = line.text;
    li.appendChild(cell('time', 'at',
      format(line.received, { hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' })));
    li.appendChild(cell('span', 'board', line.board));
    li.appendChild(cell('span', 'text', line.text.replace(BOARD_STAMP, '')));
    return li;
  }

  function append(lines) {
    lines.forEach(function (line) {
      var day = dayOf(line.received);
      if (day !== lastDay) {
        list.appendChild(cell('li', 'day', day));
        lastDay = day;
        if (firstDay === null) firstDay = day;
      }
      list.appendChild(lineRow(line));
      last = line.id;
      if (first === null) first = line.id;
    });
  }

  function prepend(lines) {
    if (!lines.length) return;
    var block = document.createDocumentFragment(), day = null;
    lines.forEach(function (line) {
      var d = dayOf(line.received);
      if (d !== day) { block.appendChild(cell('li', 'day', d)); day = d; }
      block.appendChild(lineRow(line));
    });
    var endsOnFirstDay = day === firstDay && list.firstChild && list.firstChild.className === 'day';
    if (endsOnFirstDay) list.removeChild(list.firstChild);
    list.insertBefore(block, list.firstChild);
    first = lines[0].id;
    firstDay = dayOf(lines[0].received);
  }

  function offerBoards(names) {
    names.forEach(function (name) {
      var known = Array.prototype.some.call(board.options, function (o) { return o.value === name; });
      if (!known) board.appendChild(new Option(name, name));
    });
  }

  function atEnd() { return box.scrollHeight - box.scrollTop - box.clientHeight < 32; }

  function toEnd() {
    box.scrollTop = box.scrollHeight;
    newestButton.hidden = true;
  }

  function showEmpty() {
    var filtered = board.value || level.value || find.value.trim();
    empty.hidden = list.children.length > 0;
    empty.textContent = filtered ? 'No lines match.'
                                 : 'No log lines yet. Each board sends them once it connects.';
  }

  function failed(mine) {
    if (mine === asked) status.textContent = 'Cannot reach the server. Retrying.';
  }

  function load() {
    var mine = ++asked;
    get({ limit: PAGE }).then(function (answer) {
      if (mine !== asked) return;
      tz = answer.tz;
      list.textContent = '';
      first = last = firstDay = lastDay = null;
      append(answer.lines);
      offerBoards(answer.boards);
      earlierButton.hidden = answer.lines.length < PAGE;
      status.textContent = '';
      showEmpty();
      toEnd();
    }).catch(function () { failed(mine); });
  }

  function poll() {
    if (document.hidden) return;
    if (last === null) { load(); return; }
    var mine = asked;
    get({ after: last, limit: 500 }).then(function (answer) {
      if (mine !== asked) return;
      status.textContent = '';
      if (!answer.lines.length) return;
      var following = atEnd();
      append(answer.lines);
      offerBoards(answer.boards);
      showEmpty();
      if (following) toEnd();
      else newestButton.hidden = false;
    }).catch(function () { failed(mine); });
  }

  function earlier() {
    if (first === null) return;
    var mine = asked, height = box.scrollHeight;
    earlierButton.disabled = true;
    get({ before: first, limit: PAGE }).then(function (answer) {
      if (mine !== asked) return;
      prepend(answer.lines);
      box.scrollTop += box.scrollHeight - height;
      earlierButton.hidden = answer.lines.length < PAGE;
    }).catch(function () { failed(mine); }).then(function () {
      earlierButton.disabled = false;
    });
  }

  var typing;
  board.addEventListener('change', load);
  level.addEventListener('change', load);
  find.addEventListener('input', function () {
    clearTimeout(typing);
    typing = setTimeout(load, 300);
  });
  earlierButton.addEventListener('click', earlier);
  newestButton.addEventListener('click', toEnd);
  box.addEventListener('scroll', function () { if (atEnd()) newestButton.hidden = true; });
  setInterval(poll, POLL_MS);
  load();
})();
