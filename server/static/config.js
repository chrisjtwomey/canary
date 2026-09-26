/* The config page: one tab at a time, fields that show only for some values
   of another, images and pools as tags that drag into order, a count of
   unsaved changes, and a list of what a save changes before it happens.
   Without it the form still posts, with every tab shown at once. */
(function () {
  'use strict';

  var nav = document.querySelector('nav.tabs');
  if (!nav) return;
  document.documentElement.classList.add('js');

  var tabs = all('a[data-tab]', nav);
  var panels = all('.panel[data-tab]');
  var settings = document.getElementById('settings-form');
  var yamlForm = document.getElementById('yaml-form');
  var restoreForm = document.getElementById('restore-form');
  var dialog = document.getElementById('review');
  var POLL_MS = 2000;
  var GIVE_UP_MS = 180000;
  var leaving = false;
  var saving = false;
  var touched = false;
  var dragging = null;

  function all(selector, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(selector));
  }

  function trim(s) { return s.trim(); }

  function names() { return tabs.map(function (t) { return t.getAttribute('data-tab'); }); }

  // ── Tabs ─────────────────────────────────────────────────────────
  function open(name, focus) {
    if (names().indexOf(name) < 0) name = names()[0];
    tabs.forEach(function (t) {
      var on = t.getAttribute('data-tab') === name;
      t.setAttribute('aria-selected', on ? 'true' : 'false');
      t.tabIndex = on ? 0 : -1;
      if (on && focus) t.focus();
    });
    panels.forEach(function (p) { p.hidden = p.getAttribute('data-tab') !== name; });
    if (settings) settings.hidden = name === 'yaml';
    if (yamlForm) yamlForm.hidden = name !== 'yaml';
    all('input[name=tab]', settings || document).forEach(function (i) { i.value = name; });
    if (location.hash.slice(1) !== name) history.replaceState(null, '', '#' + name);
  }

  tabs.forEach(function (t, i) {
    t.addEventListener('click', function (e) {
      e.preventDefault();
      open(t.getAttribute('data-tab'));
    });
    t.addEventListener('keydown', function (e) {
      var step = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
      if (!step) return;
      e.preventDefault();
      open(names()[(i + step + tabs.length) % tabs.length], true);
    });
  });
  window.addEventListener('hashchange', function () { open(location.hash.slice(1)); });

  // ── Values, and whether they have changed ────────────────────────
  function chipsValue(input) {
    return input.value.split(',').map(trim).filter(Boolean).join(', ');
  }

  function rowsValue(box) {
    return JSON.stringify(all('.list > .row', box).map(function (row) {
      return all('input[name], select[name]', row).map(function (el) {
        return el.classList.contains('chips') ? chipsValue(el) : el.value.trim();
      });
    }).filter(function (cells) { return cells.some(Boolean); }));
  }

  function valueOf(el) {
    if (el.classList.contains('segments')) {
      var on = el.querySelector('input:checked');
      return on ? on.value : '';
    }
    if (el.classList.contains('rows')) return rowsValue(el);
    if (el.type === 'checkbox') return el.checked ? 'true' : 'false';
    if (el.classList.contains('chips')) return chipsValue(el);
    if (el.tagName === 'TEXTAREA') return el.value.replace(/\r\n/g, '\n');
    return el.value.trim();
  }

  function isChanged(el) {
    return !el.disabled && valueOf(el) !== (el.getAttribute('data-initial') || '');
  }

  function changedIn(root) { return all('[data-key]', root).filter(isChanged); }

  function refresh() {
    var changed = changedIn(document);
    tabs.forEach(function (t) {
      var name = t.getAttribute('data-tab');
      t.classList.toggle('changed', changed.some(function (el) {
        var p = el.closest('.panel');
        return p && p.getAttribute('data-tab') === name;
      }));
    });
    all('.field[data-field]').forEach(function (f) {
      f.classList.toggle('changed', changed.some(function (el) { return f.contains(el); }));
    });
    if (touched) {
      all('.savebar .status').forEach(function (s) {
        var n = changedIn(s.closest('form')).length;
        s.textContent = n === 0 ? s.getAttribute('data-idle')
          : n === 1 ? '1 unsaved change' : n + ' unsaved changes';
      });
    }
    whens();
    markDefaults();
  }

  function setValue(el, value) {
    if (el.classList.contains('segments')) {
      all('input', el).forEach(function (r) { r.checked = r.value === value; });
    } else if (el.type === 'checkbox') {
      el.checked = value === 'true';
    } else {
      el.value = value;
      if (el._tags) el._tags.render();
    }
  }

  function markDefaults() {
    all('[data-default]').forEach(function (el) {
      var field = el.closest('.field');
      var reset = field && field.querySelector('.reset');
      if (reset) reset.hidden = valueOf(el) === el.getAttribute('data-default') || el.disabled;
    });
  }

  document.addEventListener('click', function (e) {
    var reset = e.target.closest('.reset');
    if (!reset) return;
    var el = reset.closest('.field').querySelector('[data-default]');
    setValue(el, el.getAttribute('data-default'));
    edited();
  });

  document.addEventListener('focusout', function (e) {
    var el = e.target;
    if (!el.matches || !el.matches('input[data-default]') || el.value.trim() !== '') return;
    setValue(el, el.getAttribute('data-default'));
    edited();
  });

  function whens() {
    all('[data-when]').forEach(function (box) {
      var parts = box.getAttribute('data-when').split('=');
      var source = document.querySelector('[data-key="' + parts[0] + '"]');
      box.hidden = source ? parts[1].split('|').indexOf(valueOf(source)) < 0 : false;
    });
  }

  function edited() {
    touched = true;
    refresh();
  }

  document.addEventListener('input', edited);
  document.addEventListener('change', edited);

  // ── Tags: a pool's images, and the pools' order ──────────────────
  function poolNames() {
    return all('.pools .list .pool-name').map(function (i) { return i.value.trim(); })
      .filter(Boolean);
  }

  function short(name) { return name.replace(/\.png$/, ''); }

  function tags(input) {
    var box = document.createElement('div');
    var adder = document.createElement('select');
    box.className = 'chiplist';
    adder.className = 'adder';
    adder.setAttribute('aria-label', input.hasAttribute('data-options-from')
      ? 'Add a pool' : 'Add an image');
    input.type = 'hidden';
    input.parentNode.insertBefore(box, input.nextSibling);

    function items() { return input.value.split(',').map(trim).filter(Boolean); }

    function write(list) {
      input.value = list.join(', ');
      render();
      input.dispatchEvent(new Event('input', { bubbles: true }));
    }

    function options() {
      return input.hasAttribute('data-options-from') ? poolNames()
        : (input.getAttribute('data-options') || '').split(' ').filter(Boolean);
    }

    function move(from, to) {
      var list = items();
      var item = list.splice(from, 1)[0];
      list.splice(Math.max(0, Math.min(to, list.length)), 0, item);
      write(list);
    }

    function dropAt(e, index) {
      e.preventDefault();
      box.classList.remove('over');
      if (!dragging) return;
      if (dragging.input === input) {
        move(dragging.index, index > dragging.index ? index - 1 : index);
      } else {
        var from = dragging.input._tags;
        var item = from.items()[dragging.index];
        var rest = from.items();
        rest.splice(dragging.index, 1);
        from.write(rest);
        var list = items();
        list.splice(index, 0, item);
        write(list);
      }
      dragging = null;
    }

    function render() {
      box.textContent = '';
      items().forEach(function (name, i, list) {
        var chip = document.createElement('span');
        var words = document.createElement('span');
        var x = document.createElement('button');
        chip.className = 'chip';
        chip.draggable = true;
        chip.tabIndex = 0;
        chip.title = name;
        words.textContent = short(name);
        x.type = 'button';
        x.className = 'x';
        x.textContent = '×';
        x.setAttribute('aria-label', 'Remove ' + name);
        x.addEventListener('click', function () {
          var rest = items();
          rest.splice(i, 1);
          write(rest);
        });
        chip.addEventListener('keydown', function (e) {
          if (!e.altKey) return;
          var step = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
          if (!step || i + step < 0 || i + step >= list.length) return;
          e.preventDefault();
          move(i, i + step);
          box.querySelectorAll('.chip')[i + step].focus();
        });
        chip.addEventListener('dragstart', function (e) {
          dragging = { input: input, index: i };
          e.dataTransfer.effectAllowed = 'move';
          e.dataTransfer.setData('text/plain', name);
          chip.classList.add('dragging');
        });
        chip.addEventListener('dragend', function () {
          chip.classList.remove('dragging');
          all('.chip.over, .chiplist.over').forEach(function (c) { c.classList.remove('over'); });
        });
        chip.addEventListener('dragover', function (e) {
          if (!dragging) return;
          e.preventDefault();
          e.stopPropagation();
          chip.classList.add('over');
        });
        chip.addEventListener('dragleave', function () { chip.classList.remove('over'); });
        chip.addEventListener('drop', function (e) {
          e.stopPropagation();
          dropAt(e, i);
        });
        chip.appendChild(words);
        chip.appendChild(x);
        box.appendChild(chip);
      });
      if (!items().length && input.placeholder) {
        box.appendChild(cell('span', input.placeholder, 'empty'));
      }
      adder.textContent = '';
      adder.add(new Option('+', ''));
      options().forEach(function (o) { adder.add(new Option(short(o), o)); });
      box.appendChild(adder);
    }

    box.addEventListener('dragover', function (e) {
      if (!dragging) return;
      e.preventDefault();
      box.classList.add('over');
    });
    box.addEventListener('dragleave', function (e) {
      if (!box.contains(e.relatedTarget)) box.classList.remove('over');
    });
    box.addEventListener('drop', function (e) { dropAt(e, items().length); });
    adder.addEventListener('change', function (e) {
      e.stopPropagation();
      if (!adder.value) return;
      var list = items();
      list.push(adder.value);
      write(list);
    });

    input._tags = { items: items, write: write, render: render };
    render();
  }

  // ── A schedule: time ranges round the clock ──────────────────────
  // Each row is a time range from its start to the next row's. Add halves
  // the time left after the latest start, so the day stays covered; × gives
  // a range's hours to the one before. The rows stay in order of their
  // starts, as the day runs.
  var DAY_MIN = 1440;

  function minutesOf(hhmm) {
    var m = /^(\d{1,2}):(\d{2})$/.exec(hhmm || '');
    return m ? (parseInt(m[1], 10) * 60 + parseInt(m[2], 10)) % DAY_MIN : NaN;
  }

  function hhmm(minutes) {
    var m = ((minutes % DAY_MIN) + DAY_MIN) % DAY_MIN;
    return ('0' + Math.floor(m / 60)).slice(-2) + ':' + ('0' + (m % 60)).slice(-2);
  }

  function clock(box) {
    var list = box.querySelector('.list');
    var add = box.querySelector('.add');
    var max = parseInt(box.getAttribute('data-max'), 10) || 8;
    // Rendered disabled while the dock is offline, and kept so.
    var locked = !!add && add.disabled;

    function rows() { return all('.list > .row', box); }
    function startOf(row) { return minutesOf(row.querySelector('input[type=time]').value); }

    function limits() {
      var n = rows().length;
      rows().forEach(function (row) {
        row.querySelector('.remove').disabled = locked || n <= 1;
      });
      if (add) add.disabled = locked || n >= max;
    }

    function sort() {
      var now = rows();
      var sorted = now.slice().sort(function (a, b) { return startOf(a) - startOf(b); });
      if (sorted.every(function (row, i) { return row === now[i]; })) return;
      var focused = document.activeElement;
      sorted.forEach(function (row) { list.appendChild(row); });
      if (focused && box.contains(focused)) focused.focus();
    }

    // The add button's new row, last and blank, starts halfway through the
    // time range that starts latest, which runs on past midnight to the
    // earliest start, on a five-minute step, with its interval. When that
    // range is too short for it, no row is added.
    box._added = function (row) {
      var others = rows().filter(function (r) { return r !== row && !isNaN(startOf(r)); })
        .sort(function (a, b) { return startOf(a) - startOf(b); });
      var latest = others[others.length - 1];
      var from = latest ? startOf(latest) : 0;
      var length = latest ? startOf(others[0]) + DAY_MIN - from : 0;
      var middle = from + Math.round(length / 10) * 5;
      if (!latest || middle <= from || middle >= from + length) {
        row.remove();
        limits();
        return;
      }
      row.querySelector('input[type=time]').value = hhmm(middle);
      row.querySelector('input[type=number]').value =
        latest.querySelector('input[type=number]').value;
      sort();
      limits();
      box.dispatchEvent(new Event('input', { bubbles: true }));
    };
    // A start takes its row into order once it is set: when its input
    // loses focus, or when the picker closes. The browser reports a change
    // at each digit typed, and a row moved then takes the typing with it.
    list.addEventListener('change', function (e) {
      if (e.target.type === 'time' && e.target !== document.activeElement) sort();
    });
    list.addEventListener('focusout', function (e) {
      if (e.target.type === 'time') setTimeout(sort, 0);
    });
    box.addEventListener('input', limits);
    limits();
  }

  // ── The light's looks: a trigger, its pattern and its length ─────
  // One row to a trigger at most, kept in the triggers' order, which is the
  // order the dock tries them in. A new row takes the first trigger with no
  // row, in its default look.
  function looks(box) {
    var list = box.querySelector('.list');
    var add = box.querySelector('.add');
    var defaults = JSON.parse(box.getAttribute('data-looks'));
    // Each pattern that has a length, and its shortest.
    var shortest = JSON.parse(box.getAttribute('data-min'));
    var order = Object.keys(defaults);
    // Rendered disabled while the dock is offline, and kept so.
    var locked = add && add.disabled;

    function rows() { return all('.list > .row', box); }
    function triggerOf(row) { return row.querySelector('select[name$=".trigger"]'); }
    function patternOf(row) { return row.querySelector('select[name$=".pattern"]'); }
    function used() { return rows().map(function (row) { return triggerOf(row).value; }); }

    function limits() {
      var taken = used();
      rows().forEach(function (row) {
        var own = triggerOf(row).value;
        all('option', triggerOf(row)).forEach(function (o) {
          o.disabled = o.value !== own && taken.indexOf(o.value) >= 0;
        });
        var min = shortest[patternOf(row).value];
        row.querySelector('.length').classList.toggle('idle', min === undefined);
        if (min !== undefined) row.querySelector('input[type=number]').min = min;
      });
      if (add) add.disabled = locked || taken.length >= order.length;
    }

    function sort() {
      var sorted = rows().slice().sort(function (a, b) {
        return order.indexOf(triggerOf(a).value) - order.indexOf(triggerOf(b).value);
      });
      var focused = document.activeElement;
      sorted.forEach(function (row) { list.appendChild(row); });
      if (focused && box.contains(focused)) focused.focus();
    }

    box._added = function (row) {
      var taken = used().slice(0, -1);
      var free = order.filter(function (t) { return taken.indexOf(t) < 0; })[0];
      triggerOf(row).value = free;
      patternOf(row).value = defaults[free][0];
      row.querySelector('input[type=number]').value = defaults[free][1];
      sort();
      limits();
    };
    list.addEventListener('change', function (e) {
      if (e.target.name && /\.trigger$/.test(e.target.name)) sort();
    });
    box.addEventListener('input', limits);
    box.addEventListener('change', limits);
    limits();
  }

  function poolsChanged() {
    all('input[data-options-from]').forEach(function (i) { if (i._tags) i._tags.render(); });
  }

  // ── Rows: the pools, a schedule's ranges, the light's looks ──────
  all('fieldset.rows').forEach(function (box) {
    var list = box.querySelector('.list');
    var blank = box.querySelector('template');
    var add = box.querySelector('.add');
    all('input.chips', list).forEach(tags);
    if (add) add.addEventListener('click', function () {
      if (add.disabled) return;
      var row = blank.content.firstElementChild.cloneNode(true);
      list.appendChild(row);
      all('input.chips', row).forEach(tags);
      if (box._added) box._added(row);
      row.querySelector('input, select').focus();
      edited();
    });
    list.addEventListener('click', function (e) {
      var remove = e.target.closest('.remove');
      if (!remove || remove.disabled) return;
      remove.closest('.row').remove();
      poolsChanged();
      // An input event, so the drawings of the tab redraw as for a typed change.
      box.dispatchEvent(new Event('input', { bubbles: true }));
    });
    if (box.classList.contains('clock')) clock(box);
    if (box.classList.contains('looks')) looks(box);
    if (box.classList.contains('pools')) {
      list.addEventListener('input', function (e) {
        if (e.target.classList.contains('pool-name')) poolsChanged();
      });
    }
  });
  all('.field input.chips').forEach(function (i) { if (!i._tags) tags(i); });

  // ── A store out to a file, and back in ───────────────────────────
  all('form[id^="import-"]').forEach(function (form) {
    var store = form.id.slice('import-'.length);
    var row = document.querySelector('[data-import="' + store + '"]');
    var file = row.querySelector('input[type=file]');
    var button = row.querySelector('button');
    // The picker is the button, and the dialog asks about replacing.
    row.querySelector('.pick').hidden = true;

    function say(words, bad) {
      var p = row.querySelector('.report') || row.appendChild(document.createElement('p'));
      p.className = 'report ' + (bad ? 'error' : 'help');
      p.textContent = words;
    }

    // What the store holds now: its line, its Download link and the disk.
    function held(answer) {
      var value = document.querySelector('[data-contents="' + store + '"] .value');
      value.textContent = '';
      answer.contents.forEach(function (part, i) {
        if (i) value.appendChild(document.createTextNode(' · '));
        value.appendChild(document.createElement('span')).textContent = part;
      });
      row.querySelector('[data-export]').hidden = !answer.records;
      var disk = document.getElementById('visual-disk');
      if (!disk) return;
      disk.setAttribute('data-disk', JSON.stringify(answer.disk));
      disk.dispatchEvent(new Event('held', { bubbles: true }));
    }

    function ask(answer) {
      document.getElementById('review-list').textContent = '';
      document.getElementById('review-title').textContent = 'Replace existing records?';
      document.getElementById('review-lead').textContent = answer.words;
      var confirm = document.getElementById('review-confirm');
      confirm.textContent = 'Replace';
      dialog.returnValue = '';
      dialog.onclose = function () {
        if (dialog.returnValue === 'confirm') {
          send(true);
          return;
        }
        say('Nothing imported.', false);
        file.value = '';
      };
      dialog.showModal();
      confirm.focus();
    }

    function send(replace) {
      var chosen = file.files[0];
      if (!chosen) return;
      var data = new FormData();
      data.set('file', chosen);
      if (replace) data.set('replace', 'true');
      button.classList.add('busy');
      say('Importing ' + chosen.name + '…', false);
      fetch(form.getAttribute('action'), {
        method: 'POST', body: data, headers: { Accept: 'application/json' }
      })
        .then(function (r) {
          return r.json().then(function (answer) { return { code: r.status, answer: answer }; });
        })
        .then(function (got) {
          button.classList.remove('busy');
          if (got.code === 409) {
            ask(got.answer);
            return;
          }
          say(got.answer.words, got.answer.bad);
          if (!got.answer.bad) held(got.answer);
          // Picking the same file again says nothing unless the input is empty.
          file.value = '';
        })
        .catch(function () {
          button.classList.remove('busy');
          say('No answer from the server.', true);
        });
    }

    button.addEventListener('click', function (e) {
      e.preventDefault();
      file.click();
    });
    file.addEventListener('change', function () { send(false); });
    form.addEventListener('submit', function (e) { e.preventDefault(); });
  });

  // ── Check, save, restore ─────────────────────────────────────────
  function firstInvalid(form) {
    return all('input, select, textarea', form).filter(function (el) {
      return !el.disabled && !el.closest('.field[hidden]') && !el.checkValidity();
    })[0];
  }

  function status(form, words) {
    var s = form.querySelector('.savebar .status') ||
      document.querySelector('form:not([hidden]) .savebar .status');
    if (s) s.textContent = words;
  }

  function cell(tag, text, klass) {
    var c = document.createElement(tag);
    c.textContent = text;
    if (klass) c.className = klass;
    return c;
  }

  function confirmSave(form, submitter, answer) {
    var list = document.getElementById('review-list');
    list.textContent = '';
    answer.changes.forEach(function (c) {
      var row = document.createElement('tr');
      row.appendChild(cell('th', c.name));
      row.appendChild(cell('td', c.old, 'old'));
      row.appendChild(cell('td', '→', 'to'));
      row.appendChild(cell('td', c['new'], 'new'));
      list.appendChild(row);
    });
    document.getElementById('review-title').textContent = form.getAttribute('data-title');
    document.getElementById('review-confirm').textContent = form.getAttribute('data-confirm');
    document.getElementById('review-lead').textContent =
      answer.changes.length === 0 ? 'Only comments and layout change.' : '';
    dialog.returnValue = '';
    dialog.onclose = function () {
      if (dialog.returnValue === 'confirm') {
        save(form, submitter);
        return;
      }
      touched = true;
      refresh();
    };
    dialog.showModal();
    document.getElementById('review-confirm').focus();
  }

  function review(form, submitter) {
    var data = new FormData(form);
    data.set('action', 'review');
    status(form, 'Checking…');
    fetch(form.getAttribute('action'), {
      method: 'POST', body: data, headers: { Accept: 'application/json' }
    })
      .then(function (r) { return r.json(); })
      .then(function (answer) {
        var check = form.querySelector('button[value=check]');
        if (answer.problem && check) {
          leaving = true;
          form.requestSubmit(check);
        } else if (answer.problem) {
          status(form, 'Not restored: ' + answer.problem);
        } else if (answer.same) {
          status(form, 'No changes.');
        } else {
          confirmSave(form, submitter, answer);
        }
      })
      .catch(function () { status(form, 'No answer from the server.'); });
  }

  function busy(submitter, on) {
    saving = on;
    submitter.classList.toggle('busy', on);
    submitter.setAttribute('aria-busy', on ? 'true' : 'false');
    all('.savebar button, .restore button').forEach(function (b) {
      if (b !== submitter) b.disabled = on;
    });
    all('a.discard').forEach(function (a) {
      a.classList.toggle('off', on);
      a.setAttribute('aria-disabled', on ? 'true' : 'false');
    });
  }

  function save(form, submitter) {
    var data = new FormData(form);
    data.set('action', 'save');
    busy(submitter, true);
    status(form, 'Saving…');
    fetch(form.getAttribute('action'), {
      method: 'POST', body: data, headers: { Accept: 'application/json' }
    })
      .then(function (r) { return r.json(); })
      .then(function (answer) {
        if (answer.saved) {
          status(form, 'Restarting…');
          waitForRestart(form, submitter);
          return;
        }
        busy(submitter, false);
        status(form, answer.problem ? 'Not saved: ' + answer.problem : 'No changes.');
      })
      .catch(function () {
        busy(submitter, false);
        status(form, 'No answer from the server.');
      });
  }

  // A server that answers straight away has not restarted yet, so an answer
  // counts only after a failure.
  function waitForRestart(form, submitter) {
    var started = Date.now();
    var wentDown = false;

    function next() {
      if (Date.now() - started > GIVE_UP_MS) {
        busy(submitter, false);
        status(form, 'The server has not come back. Check its log.');
        return;
      }
      setTimeout(poll, POLL_MS);
    }

    function poll() {
      fetch('../about', { cache: 'no-store' })
        .then(function (r) {
          if (r.ok && wentDown) {
            leaving = true;
            location.replace('config?saved=1' + location.hash);
            return;
          }
          if (!r.ok) wentDown = true;
          next();
        })
        .catch(function () {
          wentDown = true;
          next();
        });
    }

    next();
  }

  [settings, yamlForm, restoreForm].forEach(function (form) {
    if (!form) return;
    form.addEventListener('submit', function (e) {
      var submitter = e.submitter;
      var action = submitter ? submitter.value : 'check';
      if (saving) {
        e.preventDefault();
        return;
      }
      var bad = firstInvalid(form);
      if (bad) {
        e.preventDefault();
        var panel = bad.closest('.panel');
        if (panel) open(panel.getAttribute('data-tab'));
        bad.reportValidity();
        return;
      }
      if (action !== 'save') {
        leaving = true;
        return;
      }
      e.preventDefault();
      review(form, submitter);
    });
  });

  all('a.discard').forEach(function (a) {
    a.addEventListener('click', function (e) {
      e.preventDefault();
      if (saving) return;
      leaving = true;
      // The empty query makes this a new request, not a jump to the fragment.
      location.assign('config?' + location.hash);
    });
  });
  // The empty query comes off again, or the next Discard would name the
  // address the page is at and only jump to the fragment.
  if (/\?$/.test(location.href.split('#')[0])) {
    history.replaceState(history.state, '', location.pathname + location.hash);
  }

  window.addEventListener('beforeunload', function (e) {
    if (leaving || changedIn(document).length === 0) return;
    e.preventDefault();
    e.returnValue = '';
  });

  // A check's result, with the save it offers. It lists what the save
  // changes, so the save goes ahead without the review the save bar's
  // button asks for.
  var notice = document.getElementById('notice');
  if (notice && notice.showModal) {
    notice.addEventListener('close', function () {
      if (notice.returnValue !== 'save') return;
      var button = document.querySelector('form:not([hidden]) .savebar button[value=save]');
      if (button && !button.disabled) save(button.form, button);
    });
    notice.showModal();
  }

  // The Dock tab's lines about the dock, fresh every 10 s. When the dock goes
  // offline or comes back, the page loads again to lock or unlock its
  // settings, unless that would lose something typed.
  var LIVE_MS = 10000;
  var dockState = document.getElementById('dock-state');
  var ppm = document.getElementById('recalibrate-ppm');
  var locked = dockState && dockState.getAttribute('data-offline') === 'true';

  function untouched() {
    return !saving && changedIn(document).length === 0 && !document.querySelector('dialog[open]')
      && (!ppm || ppm.value === ppm.defaultValue);
  }

  function live() {
    if (document.hidden || saving) return;
    fetch('config/live', { cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (s) {
        if (!s) return;
        dockState.outerHTML = s.state;
        dockState = document.getElementById('dock-state');
        var line = document.getElementById('recalibrate-state');
        if (line) line.textContent = s.recalibration;
        if (s.offline !== locked && untouched()) {
          leaving = true;
          location.reload();
        }
      })
      .catch(function () {});
  }

  if (dockState) setInterval(live, LIVE_MS);

  open(nav.getAttribute('data-open') || location.hash.slice(1));
  if (location.search) history.replaceState(null, '', 'config' + location.hash);
  refresh();
  var wrong = document.querySelector('.field.invalid input:not([type=hidden]), .field.invalid select');
  if (wrong && !wrong.closest('[hidden]')) wrong.focus();
})();
