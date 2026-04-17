(function () {
  if (!window.adminApp.ensureAuth()) return;
  window.adminApp.mountSidebar('time-tracking-reset');
  window.adminApp.bindLogout('btn-logout');

  var err = document.getElementById('page-error');
  var info = document.getElementById('page-info');
  var btn = document.getElementById('btn-reset-tt');

  function show(el, msg) {
    if (!el) return;
    el.textContent = msg;
    el.style.display = 'block';
  }
  function hide(el) {
    if (!el) return;
    el.style.display = 'none';
  }

  window.adminApp.getMe().then(function (me) {
    var role = (me && me.role) || '';
    if (role === 'Главный администратор') {
      btn.disabled = false;
      show(info, 'Вы вошли как главный администратор. Перед сбросом включите TIME_TRACKING_ALLOW_BUSINESS_DATA_RESET=true для сервиса time_tracking.');
    } else {
      show(err, 'Сброс доступен только главному администратору.');
    }
  }).catch(function (e) {
    show(err, (e && e.message) || 'Не удалось загрузить профиль');
  });

  btn.onclick = function () {
    hide(err);
    hide(info);
    if (
      !window.confirm(
        'Удалить ВСЕ бизнес-данные учёта времени (кроме списка пользователей TT)? Это необратимо.'
      )
    ) {
      return;
    }
    var phrase = window.prompt('Введите подтверждение:', '');
    if (phrase !== 'RESET_TIME_TRACKING_BUSINESS_DATA') {
      show(err, 'Фраза не совпала — сброс отменён.');
      return;
    }
    btn.disabled = true;
    window.adminApp
      .resetTimeTrackingBusinessData()
      .then(function (res) {
        show(info, (res && res.message) || 'Готово.');
      })
      .catch(function (e) {
        show(err, (e && e.message) || 'Ошибка');
      })
      .then(function () {
        window.adminApp.getMe().then(function (me) {
          if ((me && me.role) === 'Главный администратор') btn.disabled = false;
        });
      });
  };
})();
