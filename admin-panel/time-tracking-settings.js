(function () {
  'use strict';

  if (!window.adminApp.ensureAuth()) return;
  window.adminApp.bindLogout('btn-logout');
  window.adminApp.mountSidebar('tt-rounding');

  var API_BASE = window.adminApp.API_BASE || '';
  var TOKEN_KEY = 'admin_access_token';

  var errBox = document.getElementById('page-error');
  var infoBox = document.getElementById('page-info');
  var form = document.getElementById('form-rounding');
  var modeEl = document.getElementById('rounding-mode');
  var stepEl = document.getElementById('rounding-step');
  var enabledEl = document.getElementById('rounding-enabled');
  var btnSave = document.getElementById('btn-save');
  var btnReload = document.getElementById('btn-reload');

  function showError(msg) {
    infoBox.style.display = 'none';
    if (!msg) { errBox.style.display = 'none'; return; }
    errBox.textContent = msg;
    errBox.style.display = 'block';
  }
  function showInfo(msg) {
    errBox.style.display = 'none';
    if (!msg) { infoBox.style.display = 'none'; return; }
    infoBox.textContent = msg;
    infoBox.style.display = 'block';
  }

  function setStepValue(step) {
    var s = String(step);
    var opt = Array.prototype.find.call(stepEl.options, function (o) { return o.value === s; });
    if (opt) { stepEl.value = s; return; }
    var custom = document.createElement('option');
    custom.value = s;
    custom.textContent = s + ' минут';
    stepEl.appendChild(custom);
    stepEl.value = s;
  }

  function apiFetchJson(path, opts) {
    var token = localStorage.getItem(TOKEN_KEY);
    var headers = { 'Content-Type': 'application/json' };
    if (token) headers['Authorization'] = 'Bearer ' + token;
    return fetch(API_BASE + path, Object.assign({ headers: headers }, opts || {})).then(function (r) {
      if (r.status === 401) {
        localStorage.removeItem(TOKEN_KEY);
        window.location.href = 'index.html';
        throw new Error('unauthorized');
      }
      return r.text().then(function (text) {
        var data = null;
        try { data = text ? JSON.parse(text) : null; } catch (e) { data = text; }
        if (!r.ok) {
          var detail = (data && data.detail) ? data.detail : (text || ('HTTP ' + r.status));
          throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
        }
        return data;
      });
    });
  }

  function load() {
    showError(''); showInfo('');
    btnSave.disabled = true;
    return apiFetchJson('/api/v1/time-tracking/settings/rounding').then(function (data) {
      if (!data) return;
      modeEl.value = data.roundingMode || data.rounding_mode || 'up';
      setStepValue(data.roundingStepMinutes || data.rounding_step_minutes || 15);
      enabledEl.checked = Boolean(data.roundingEnabled != null ? data.roundingEnabled : data.rounding_enabled);
      btnSave.disabled = false;
    }).catch(function (e) {
      showError('Не удалось загрузить настройки: ' + e.message);
    });
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    showError(''); showInfo('');
    var payload = {
      roundingEnabled: enabledEl.checked,
      roundingMode: modeEl.value,
      roundingStepMinutes: parseInt(stepEl.value, 10)
    };
    btnSave.disabled = true;
    apiFetchJson('/api/v1/time-tracking/settings/rounding', {
      method: 'PUT',
      body: JSON.stringify(payload)
    }).then(function () {
      showInfo('Настройки сохранены. Округлённые часы пересчитаны для всех записей.');
      btnSave.disabled = false;
    }).catch(function (err) {
      showError('Ошибка сохранения: ' + err.message);
      btnSave.disabled = false;
    });
  });

  btnReload.addEventListener('click', function () { load(); });

  load();
})();
