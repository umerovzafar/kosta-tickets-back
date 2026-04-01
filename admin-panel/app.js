(function () {
  var API_BASE = (function () {
    var cfg =
      typeof window.ADMIN_API_BASE !== 'undefined' && window.ADMIN_API_BASE !== null
        ? String(window.ADMIN_API_BASE).trim()
        : '';
    if (cfg) return cfg.replace(/\/$/, '');
    var o = window.location;
    if (
      o &&
      (o.hostname === 'localhost' || o.hostname === '127.0.0.1') &&
      String(o.port) === '8080'
    ) {
      return 'http://localhost:1234';
    }
    return (o && o.origin) ? o.origin.replace(/\/$/, '') : 'http://localhost:1234';
  })();
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

    loadHikvisionUsers: function (filters) {
      filters = filters || {};
      var q = [];
      if (filters.name) q.push('name=' + encodeURIComponent(filters.name));
      if (filters.employee_no) q.push('employee_no=' + encodeURIComponent(filters.employee_no));
      var path = '/api/v1/attendance/hikvision/users' + (q.length ? ('?' + q.join('&')) : '');
      return apiFetch(path).then(function (r) {
        if (r.status === 401) {
          clearToken();
          window.location.href = 'index.html';
          return Promise.reject(new Error('Unauthorized'));
        }
        if (r.status === 403) return Promise.reject(new Error('Доступ запрещён.'));
        if (!r.ok) return r.json().catch(function () { return {}; }).then(function (e) {
          throw new Error(e.detail || 'Не удалось загрузить пользователей с камер');
        });
        return r.json();
      });
    },

    listHikvisionMappings: function () {
      return apiFetch('/api/v1/attendance/hikvision/mappings').then(function (r) {
        if (r.status === 401) {
          clearToken();
          window.location.href = 'index.html';
          return Promise.reject(new Error('Unauthorized'));
        }
        if (!r.ok) return r.json().catch(function () { return {}; }).then(function (e) {
          throw new Error(e.detail || 'Не удалось загрузить привязки');
        });
        return r.json();
      });
    },

    upsertHikvisionMapping: function (payload) {
      return apiFetch('/api/v1/attendance/hikvision/mappings', {
        method: 'PUT',
        body: payload
      }).then(function (r) {
        if (r.status === 401) {
          clearToken();
          window.location.href = 'index.html';
          return Promise.reject(new Error('Unauthorized'));
        }
        if (!r.ok) return r.json().catch(function () { return {}; }).then(function (e) {
          throw new Error(e.detail || 'Не удалось сохранить привязку');
        });
        return r.json();
      });
    },

    deleteHikvisionMapping: function (cameraEmployeeNo) {
      return apiFetch('/api/v1/attendance/hikvision/mappings/' + encodeURIComponent(cameraEmployeeNo), {
        method: 'DELETE'
      }).then(function (r) {
        if (r.status === 401) {
          clearToken();
          window.location.href = 'index.html';
          return Promise.reject(new Error('Unauthorized'));
        }
        if (!r.ok) return r.json().catch(function () { return {}; }).then(function (e) {
          throw new Error(e.detail || 'Не удалось удалить привязку');
        });
        return r.json();
      });
    },

    ensureAuth: function () {
      if (!getToken()) {
        window.location.href = 'index.html';
        return false;
      }
      return true;
    },

    ensureGuest: function () {
      if (getToken()) {
        window.location.href = 'dashboard.html';
        return false;
      }
      return true;
    },

    bindLogout: function (id) {
      var el = document.getElementById(id || 'btn-logout');
      if (!el) return;
      el.href = this.logoutUrl();
      el.onclick = function (e) {
        e.preventDefault();
        clearToken();
        window.location.href = API_BASE + '/api/v1/auth/azure/logout';
      };
    },

    mountSidebar: function (activePage) {
      var nav = document.getElementById('sidebar-nav');
      if (!nav) return;
      var items = [
        { id: 'dashboard', href: 'dashboard.html', label: 'Дашборд' },
        { id: 'users', href: 'users.html', label: 'Пользователи' },
        { id: 'hikvision', href: 'hikvision.html', label: 'Камеры Hikvision' }
      ];
      nav.innerHTML = items.map(function (item) {
        var cls = item.id === activePage ? 'side-link active' : 'side-link';
        return '<a class="' + cls + '" href="' + item.href + '">' + item.label + '</a>';
      }).join('');
    },

    dedupeHikvisionUsers: function (devices) {
      var uniq = {};
      var cameraMap = {};
      var errors = [];
      (devices || []).forEach(function (d) {
        cameraMap[(d.camera_ip || '-')] = true;
        if (d.error) {
          errors.push('Камера ' + (d.camera_ip || '-') + ': ' + d.error);
          return;
        }
        (d.users || []).forEach(function (u) {
          var emp = (u.employee_no || '').trim();
          var nm = (u.name || '').trim();
          var key = emp ? ('emp:' + emp) : ('name:' + nm.toLowerCase());
          if (!key || key === 'name:') key = 'raw:' + JSON.stringify(u);
          if (!uniq[key]) {
            uniq[key] = {
              employee_no: emp || '-',
              name: nm || '-',
              department: (u.department || '').trim() || '-',
              cameras: {}
            };
          }
          if ((u.department || '').trim() && uniq[key].department === '-') {
            uniq[key].department = (u.department || '').trim();
          }
          uniq[key].cameras[(d.camera_ip || '-')] = true;
        });
      });
      var users = Object.keys(uniq).map(function (k) {
        var item = uniq[k];
        return {
          cameras: Object.keys(item.cameras),
          employee_no: item.employee_no,
          name: item.name,
          department: item.department
        };
      });
      return { users: users, camera_count: Object.keys(cameraMap).length, errors: errors };
    },

  };
})();
