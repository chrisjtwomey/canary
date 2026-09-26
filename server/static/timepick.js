/* The Config page's own time picker: an hour and a minute column in the
   pages' ink, opened by the clock button beside each time input. The
   browser's picker takes its colours from the system. Each choice sets
   the input and fires input on it, so the form and the drawings follow;
   closing fires change, once, when anything was chosen. */
(function () {
  'use strict';

  var open = null;   // {box, input, button, changed} while a picker shows

  function pad(n) { return (n < 10 ? '0' : '') + n; }

  // The input's hour and minute; NaN for each while it is empty.
  function parts(input) {
    var m = /^(\d{2}):(\d{2})/.exec(input.value);
    return m ? [parseInt(m[1], 10), parseInt(m[2], 10)] : [NaN, NaN];
  }

  function set(input, hour, minute) {
    input.value = pad(hour) + ':' + pad(minute);
    input.dispatchEvent(new Event('input', { bubbles: true }));
    open.changed = true;
  }

  function column(label, count, chosen) {
    var col = document.createElement('div');
    col.className = 'col';
    col.setAttribute('role', 'listbox');
    col.setAttribute('aria-label', label);
    for (var i = 0; i < count; i++) {
      var b = document.createElement('button');
      b.type = 'button';
      b.textContent = pad(i);
      b.setAttribute('role', 'option');
      b.setAttribute('aria-selected', String(i === chosen));
      b.setAttribute('data-value', String(i));
      col.appendChild(b);
    }
    return col;
  }

  function mark(col, value) {
    col.querySelectorAll('button').forEach(function (b) {
      b.setAttribute('aria-selected', String(+b.getAttribute('data-value') === value));
    });
  }

  function chosenIn(col) {
    return col.querySelector('[aria-selected="true"]') || col.firstChild;
  }

  function close(refocus) {
    if (!open) return;
    var was = open;
    open = null;
    was.box.remove();
    was.button.setAttribute('aria-expanded', 'false');
    if (was.changed) was.input.dispatchEvent(new Event('change', { bubbles: true }));
    if (refocus) was.button.focus();
  }

  function show(button) {
    var input = button.parentElement.querySelector('input[type=time]');
    var now = parts(input);
    var hours = column('Hour', 24, now[0]);
    var minutes = column('Minute', 60, now[1]);
    var box = document.createElement('div');
    box.className = 'timepick';
    box.setAttribute('role', 'dialog');
    box.setAttribute('aria-label', 'Choose a time');
    box.append(hours, minutes);

    // An hour keeps the minute, or takes :00 on an empty input; a minute
    // finishes the choice.
    hours.addEventListener('click', function (e) {
      var b = e.target.closest('button');
      if (!b) return;
      var minute = parts(input)[1];
      set(input, +b.getAttribute('data-value'), isNaN(minute) ? 0 : minute);
      mark(hours, parts(input)[0]);
      mark(minutes, parts(input)[1]);
    });
    minutes.addEventListener('click', function (e) {
      var b = e.target.closest('button');
      if (!b) return;
      var hour = parts(input)[0];
      set(input, isNaN(hour) ? 0 : hour, +b.getAttribute('data-value'));
      close(true);
    });
    box.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        e.preventDefault();
        close(true);
        return;
      }
      var b = e.target.closest('button');
      if (!b) return;
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        var next = e.key === 'ArrowDown' ? b.nextElementSibling : b.previousElementSibling;
        if (next) next.focus();
      } else if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
        e.preventDefault();
        chosenIn(b.parentElement === hours ? minutes : hours).focus();
      }
    });

    document.body.appendChild(box);
    var r = input.getBoundingClientRect();
    box.style.left = (r.left + window.scrollX) + 'px';
    box.style.top = (r.bottom + window.scrollY + 4) + 'px';
    [hours, minutes].forEach(function (col) {
      var b = chosenIn(col);
      col.scrollTop = b.offsetTop - (col.clientHeight - b.offsetHeight) / 2;
    });
    button.setAttribute('aria-expanded', 'true');
    open = { box: box, input: input, button: button, changed: false };
    chosenIn(hours).focus({ preventScroll: true });
  }

  document.addEventListener('click', function (e) {
    var button = e.target.closest('.time .pick');
    if (!button || button.disabled) return;
    var again = open && open.button === button;
    close(again);
    if (!again) show(button);
  });

  // Alt+Down, the browser's key for its own picker, opens this one instead.
  document.addEventListener('keydown', function (e) {
    if (!e.altKey || e.key !== 'ArrowDown' || !e.target.matches('.time input[type=time]')) return;
    var button = e.target.parentElement.querySelector('.pick');
    if (!button || button.disabled) return;
    e.preventDefault();
    close(false);
    show(button);
  });

  document.addEventListener('mousedown', function (e) {
    if (open && !open.box.contains(e.target) && !open.button.contains(e.target)) close(false);
  });
  document.addEventListener('focusin', function (e) {
    if (open && !open.box.contains(e.target) && !open.button.contains(e.target)) close(false);
  });
  window.addEventListener('resize', function () { close(false); });
})();
