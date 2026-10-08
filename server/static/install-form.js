/* The install page's network settings. Each saves when a person leaves its
   field, through /web/config as the Settings page saves; these take effect
   without a restart. An install writes what the server has saved, so the
   Install buttons wait from the first key until the save is done. Show and
   Reset work as config.js has them. */
(function () {
  'use strict';

  var POLL_MS = 2000;
  var GIVE_UP_MS = 180000;

  document.documentElement.classList.add('js');
  var form = document.getElementById('network-form');
  if (!form) return;
  var status = document.getElementById('network-status');
  var pending = Promise.resolve();

  function say(text) { status.textContent = text; }

  function inputs() { return form.querySelectorAll('input[data-initial]'); }

  function edited() {
    return Array.prototype.some.call(inputs(), function (input) {
      return input.value !== input.getAttribute('data-initial');
    });
  }

  function installs(on) {
    document.querySelectorAll('#install .boards button').forEach(function (button) {
      button.disabled = !on;
    });
  }

  function showError(key, text) {
    form.querySelectorAll('.field.invalid').forEach(function (field) {
      field.classList.remove('invalid');
      var old = field.querySelector('.error');
      if (old) old.remove();
    });
    var field = key && form.querySelector('[data-field="' + key + '"]');
    if (!field) return;
    var p = document.createElement('p');
    p.className = 'error';
    p.textContent = text;
    field.classList.add('invalid');
    field.appendChild(p);
  }

  function resets() {
    form.querySelectorAll('input[data-default]').forEach(function (input) {
      var reset = input.closest('.field').querySelector('.reset');
      if (reset) reset.hidden = input.value === input.getAttribute('data-default');
    });
  }

  // The page's values for epd's install.js, as the server now has them. The
  // board rows appear only once nothing is missing, so the page opens again
  // when that changes.
  function renew() {
    return fetch('install/config', { cache: 'no-store' })
      .then(function (r) { return r.json(); })
      .then(function (config) {
        var element = document.getElementById('install-config');
        var before = JSON.parse(element.textContent);
        element.textContent = JSON.stringify(config);
        if ((before.missing.length === 0) !== (config.missing.length === 0)) location.reload();
      });
  }

  function waitForRestart(config) {
    var started = Date.now();

    function next() {
      if (Date.now() - started > GIVE_UP_MS) {
        say('The server has not come back. Check its log.');
        return;
      }
      setTimeout(poll, POLL_MS);
    }

    function poll() {
      fetch('../about', { cache: 'no-store' })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (about) {
          if (about && about.server && about.server.config === config) {
            location.reload();
            return;
          }
          next();
        })
        .catch(next);
    }

    next();
  }

  function saveNow() {
    var data = new FormData(form);
    data.set('action', 'save');
    say('Saving…');
    return fetch(form.getAttribute('action'), {
      method: 'POST', body: data, headers: { Accept: 'application/json' }
    })
      .then(function (r) { return r.json(); })
      .then(function (answer) {
        if (answer.saved && answer.restarted !== false) {
          say('Restarting…');
          waitForRestart(answer.config);
          return;
        }
        if (answer.field || answer.problem) {
          showError(answer.field, answer.error);
          say(answer.field ? 'Not saved.' : 'Not saved: ' + answer.problem);
          return;
        }
        showError(null);
        inputs().forEach(function (input) {
          input.setAttribute('data-initial', input.value);
        });
        say('');
        return renew().then(function () { installs(!edited()); });
      })
      .catch(function () { say('Cannot reach the server. Check that it is running.'); });
  }

  function save() {
    installs(false);
    pending = pending.then(saveNow);
  }

  form.addEventListener('change', save);
  form.addEventListener('submit', function (e) {
    e.preventDefault();
    save();
  });
  form.addEventListener('input', function () {
    installs(false);
    resets();
  });

  form.addEventListener('click', function (e) {
    var reveal = e.target.closest('.reveal');
    if (reveal) {
      var secret = document.getElementById(reveal.getAttribute('aria-controls'));
      var hidden = secret.type === 'password';
      secret.type = hidden ? 'text' : 'password';
      reveal.textContent = hidden ? 'Hide' : 'Show';
    }
    var reset = e.target.closest('.reset');
    if (reset) {
      var input = reset.closest('.field').querySelector('input[data-default]');
      input.value = input.getAttribute('data-default');
      resets();
      save();
    }
  });

  resets();
})();
