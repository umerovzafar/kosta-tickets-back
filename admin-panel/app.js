(function () {
  var API_BASE = window.ADMIN_API_BASE || 'http://localhost:1234';
  var TOKEN_KEY = 'admin_access_token';

  function getToken() {
    return localStorage.getItem(TOKEN_KEY);
  }

  function setToken(token) {
    localStorage.setItem(TOKEN_KEY, token);
  }

  function clearToken() {
    localStorage.removeItem(TOKEN_KEY);
  }

  function apiFetch(path, options) {
    options = options || {};
    var headers = options.headers || {};
    var token = getToken();
    if (token) headers['Authorization'] = 'Bearer ' + token;
    if (options.body && typeof options.body === 'object' && !(options.body instanceof FormData)) {
      headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify(options.body);
    }
    return fetch(API_BASE + path, {
      method: options.method || 'GET',
      headers: headers,
      body: options.body
    });
  }

  var ROLES = ['Сотрудник', 'IT отдел', 'Партнер', 'Администратор', 'Главный администратор', 'Офис менеджер'];

  function showError(el, msg) {
    var box = document.getElementById(el);
    if (!box) return;
    box.textContent = msg;
    box.classList.add('error-msg');
    box.style.display = 'block';
  }

  function hideError(el) {
    var box = document.getElementById(el);
    if (box) box.style.display = 'none';
  }

  window.adminApp = {
    getToken: getToken,
    setToken: setToken,
    clearToken: clearToken,
    API_BASE: API_BASE,
    ROLES: ROLES,

    login: function (username, password) {
      var url = (API_BASE || '').replace(/\/$/, '') + '/api/v1/auth/admin/login';
      return fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: username, password: password })
      }).then(function (r) {
        if (r.status === 401) {
          return r.json().then(function (d) { throw new Error(d.detail || 'Неверный логин или пароль'); });
        }
        if (r.status === 404) {
          throw new Error('Сервис входа не найден. Проверьте, что gateway запущен на ' + (API_BASE || '...') + ' и перезапустите контейнеры (docker-compose up -d --build gateway auth).');
        }
        if (!r.ok) {
          return r.json().catch(function () { return {}; }).then(function (d) {
            throw new Error(d.detail || d.message || 'Ошибка входа');
          });
        }
        return r.json().then(function (data) {
          setToken(data.access_token);
        });
      });
    },

    logoutUrl: function () {
      return API_BASE + '/api/v1/auth/azure/logout';
    },

    loadUsers: function () {
      return apiFetch('/api/v1/users?include_archived=false').then(function (r) {
        if (r.status === 401) {
          clearToken();
          window.location.href = 'index.html';
          return Promise.reject(new Error('Unauthorized'));
        }
        if (r.status === 403) return Promise.reject(new Error('Доступ запрещён. Нужна роль Администратор, Партнер или IT отдел для просмотра списка пользователей.'));
        if (!r.ok) return Promise.reject(new Error('Не удалось загрузить пользователей'));
        return r.json();
      });
    },

    setRole: function (userId, role) {
      return apiFetch('/api/v1/users/' + userId + '/role', {
        method: 'PATCH',
        body: { role: role }
      }).then(function (r) {
        if (r.status === 401) {
          clearToken();
          window.location.href = 'index.html';
          return Promise.reject(new Error('Unauthorized'));
        }
        if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || 'Ошибка'); });
        return r.json();
      });
    },

  };
})();
