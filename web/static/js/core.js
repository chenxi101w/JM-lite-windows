/* ============================================================
   JM 轻量版 · 前端 core —— 命名空间 / 基元 / 主题 / PJAX / 启动
   ============================================================ */
// 模块约定：
//   · 全部挂在 window.JM 下（window.App 保留为兼容别名）
//   · 页面模块把 init 注册进 JM.pages[<name>]，由 JM.routeInit() 统一驱动
window.JM = window.JM || {};
window.App = window.JM;   // 兼容旧引用
(function (JM) {
  'use strict';

  JM.pages = JM.pages || {};   // 页面模块注册表：name -> init()

  var App = JM;   // 兼容别名：App.xxx 即 JM.xxx（下面都挂在同一对象上）
  App.version = null;

  /* ── DOM 简写 ─────────────────────────────────────────── */
  function $(id) { return document.getElementById(id); }

  /* ── API 封装 ─────────────────────────────────────────── */
  async function api(path, options) {
    var opt = Object.assign({ headers: {} }, options || {});
    if (opt.body && typeof opt.body !== 'string') {
      opt.headers['Content-Type'] = 'application/json';
      opt.body = JSON.stringify(opt.body);
    }
    var resp = await fetch(path, opt);
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    return resp.json();
  }
  App.api = api;

  /* ── HTML 转义 ────────────────────────────────────────── */
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }
  App.esc = esc;

  /* ── 轻提示 ───────────────────────────────────────────── */
  var toastTimer = null;
  function toast(msg) {
    var el = $('toast');
    if (!el) {
      el = document.createElement('div');
      el.id = 'toast';
      el.className = 'toast';
      document.body.appendChild(el);
    }
    el.textContent = msg;
    el.classList.add('is-show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.classList.remove('is-show'); }, 2400);
  }
  App.toast = toast;

  /* ── 美化确认弹窗（替代原生 confirm）────────────────────
     confirmModal({ title, text, okText, icon }) → Promise<boolean>
     icon: 'trash'(默认) | 'warn'                                          */
  function confirmModal(opts) {
    var icons = {
      trash: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
        '<polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>',
      warn: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
        '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>'
    };
    var iconKey = opts.icon && icons[opts.icon] ? opts.icon : 'trash';
    return new Promise(function (resolve) {
      var overlay = document.createElement('div');
      overlay.className = 'modal-overlay confirm-overlay';
      overlay.innerHTML =
        '<div class="modal confirm-modal">' +
          '<div class="confirm-modal__badge">' + icons[iconKey] + '</div>' +
          '<h3 class="confirm-modal__title">' + esc(opts.title || '确认操作') + '</h3>' +
          '<p class="confirm-modal__text">' + (opts.html || esc(opts.text || '')) + '</p>' +
          '<div class="confirm-modal__actions">' +
            '<button class="btn" data-cm-no>取消</button>' +
            '<button class="btn btn--danger" data-cm-yes>' + esc(opts.okText || '确认') + '</button>' +
          '</div>' +
        '</div>';
      document.body.appendChild(overlay);
      var done = false;
      function finish(v) {
        if (done) return;
        done = true;
        document.removeEventListener('keydown', onKey);
        overlay.classList.add('is-leaving');
        setTimeout(function () { overlay.remove(); resolve(v); }, 140);
      }
      function onKey(e) { if (e.key === 'Escape') finish(false); }
      overlay.addEventListener('click', function (ev) {
        if (ev.target === overlay || ev.target.closest('[data-cm-no]')) finish(false);
        else if (ev.target.closest('[data-cm-yes]')) finish(true);
      });
      document.addEventListener('keydown', onKey);
      // 默认焦点给取消（危险操作防手滑回车）
      setTimeout(function () {
        var no = overlay.querySelector('[data-cm-no]');
        if (no) no.focus();
      }, 0);
    });
  }
  App.confirmModal = confirmModal;

  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

  function fmtBytes(n) {
    n = Number(n) || 0;
    if (n < 1024) return n + ' B';
    if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB';
    if (n < 1024 * 1024 * 1024) return (n / 1024 / 1024).toFixed(1) + ' MB';
    return (n / 1024 / 1024 / 1024).toFixed(2) + ' GB';
  }

  function fmtTime(ms) {
    if (!ms) return '';
    var d = new Date(Number(ms));
    if (isNaN(d.getTime())) return '';
    var p = function (x) { return (x < 10 ? '0' : '') + x; };
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) + ' ' +
           p(d.getHours()) + ':' + p(d.getMinutes());
  }

  /* ── 主题 ─────────────────────────────────────────────── */
  function effectiveTheme() {
    var t = document.documentElement.getAttribute('data-theme');
    if (t === 'light' || t === 'dark') return t;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  function toggleTheme() {
    var next = effectiveTheme() === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    try { localStorage.setItem('jm_lite_theme', next); } catch (e) {}
  }
  App.toggleTheme = toggleTheme;

  /* ── 全局：侧栏下载徽标 ───────────────────────────────── */
  function initDlBadge() {
    var badge = $('dlBadge');
    if (!badge) return;
    async function tick() {
      try {
        var r = await api('/api/download/progress');
        var n = Object.keys(r.data || {}).length;
        badge.hidden = n === 0;
        badge.textContent = n;
      } catch (e) { /* 静默 */ }
    }
    tick();
    setInterval(tick, 8000);
  }



  /* ── 页面状态保持（切换页面保留原内容/滚动） ───────────── */
  // 滚动位置：按路由路径存 sessionStorage，切回时还原
  function _saveScrollNow() {
    var m = document.querySelector('.main');
    if (!m) return;
    try { sessionStorage.setItem('jm_lite_scroll_' + location.pathname, String(m.scrollTop)); } catch (e) {}
  }
  var _scrollThrottle = null;
  function bindScrollKeep() {
    var m = document.querySelector('.main');
    if (!m) return;
    m.addEventListener('scroll', function () {
      if (_scrollThrottle) return;
      _scrollThrottle = setTimeout(function () { _scrollThrottle = null; _saveScrollNow(); }, 150);
    }, { passive: true });
  }
  function restoreScroll() {
    var m = document.querySelector('.main');
    if (!m) return;
    try {
      var v = parseInt(sessionStorage.getItem('jm_lite_scroll_' + location.pathname) || '0', 10);
      if (v > 0) m.scrollTop = v;
    } catch (e) {}
  }


  /* ── PJAX：侧栏局部刷新（切换不卡 + 保留原内容） ────────── */
  // 原先侧栏是整页跳转（pywebview 重新拉 HTML+JS+CSS 并重跑全部 init），
  // 加上下载页 setInterval 会叠加，表现为「切换页面卡死」。改为只换 .main。
  var _pageCleanups = [];
  function regCleanup(fn) { if (typeof fn === 'function') _pageCleanups.push(fn); }
  function clearPageCleanups() {
    for (var i = 0; i < _pageCleanups.length; i++) {
      try { _pageCleanups[i](); } catch (e) { /* 忽略 */ }
    }
    _pageCleanups = [];
  }

  function closeAllModals() {
    document.querySelectorAll('.modal-overlay').forEach(function (m) { m.remove(); });
  }

  function markActiveNav(pathname) {
    document.querySelectorAll('.side-nav .side-item').forEach(function (a) {
      a.classList.toggle('is-active', a.getAttribute('href') === pathname);
    });
  }


  /* ── 路由初始化：驱动所有已注册页面模块 ───────────────── */
  // 各页 init 都带 DOM 守卫（元素不存在直接 return），可安全全调。
  // 阅读器走整页跳转、不参与 PJAX，故这里跳过。
  function routeInit() {
    Object.keys(JM.pages).forEach(function (name) {
      if (name !== 'reader') JM.pages[name]();
    });
  }

  var _pjaxBusy = false;
  function pjaxNav(href, push) {
    if (_pjaxBusy) return;
    var url;
    try { url = new URL(href, location.href); } catch (e) { location.href = href; return; }
    if (url.origin !== location.origin) { location.href = href; return; }
    // 阅读器要加载大量整页图片，仍走整页跳转更稳
    if (url.pathname.indexOf('/reader') === 0) { location.href = href; return; }

    _pjaxBusy = true;
    document.body.classList.add('is-pjax');
    var target = url.pathname + url.search;
    fetch(target, { headers: { 'X-PJAX': '1' } })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.text();
      })
      .then(function (html) {
        var doc = new DOMParser().parseFromString(html, 'text/html');
        var newMain = doc.querySelector('.main');
        if (!newMain) throw new Error('页面结构异常');
        clearPageCleanups();          // 停掉上一页的定时器，避免叠加
        closeAllModals();
        var oldMain = document.querySelector('.main');
        oldMain.parentNode.replaceChild(newMain, oldMain);
        if (push !== false) history.pushState({ pjax: 1 }, '', target);
        markActiveNav(url.pathname);
        routeInit();                  // 新 DOM 上的元素级监听天然不重复
        bindScrollKeep();             // 新的 .main 重新绑滚动保持
        restoreScroll();
      })
      .catch(function () { location.href = target; })
      .then(function () {
        _pjaxBusy = false;
        document.body.classList.remove('is-pjax');
      });
  }


  /* ── 启动 ─────────────────────────────────────────────── */
  document.addEventListener('DOMContentLoaded', async function () {
    var themeBtn = $('themeToggle');
    if (themeBtn) themeBtn.addEventListener('click', toggleTheme);
    try {
      var r = await api('/api/ping');
      App.version = r.version;
    } catch (e) { /* 忽略 */ }
    initDlBadge();
    routeInit();                              // 各页 init（阅读器除外）
    if (JM.pages.reader) JM.pages.reader();   // 阅读器启动时单独初始化
    bindScrollKeep();

    // ── PJAX 导航：拦截侧栏链接，局部换 .main，不再整页跳转 ──
    document.addEventListener('click', function (e) {
      var a = e.target.closest('.side-nav .side-item');
      if (!a) return;
      var href = a.getAttribute('href');
      if (!href || href.charAt(0) !== '/') return;
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      if (e.button != null && e.button !== 0) return;
      e.preventDefault();
      if (a.classList.contains('is-active')) return;   // 已在当前页，忽略
      pjaxNav(href, true);
    });
    window.addEventListener('popstate', function () { pjaxNav(location.href, false); });
  });

  /* ── 对外导出（其余经 App.xxx 在基元处直接挂载） ──────── */
  JM.$ = $;
  JM.sleep = sleep;
  JM.fmtBytes = fmtBytes;
  JM.fmtTime = fmtTime;
  JM.effectiveTheme = effectiveTheme;
  JM.regCleanup = regCleanup;
  JM.clearPageCleanups = clearPageCleanups;
  JM.closeAllModals = closeAllModals;
  JM.markActiveNav = markActiveNav;
  JM.bindScrollKeep = bindScrollKeep;
  JM.restoreScroll = restoreScroll;
  JM.routeInit = routeInit;
  JM.pjaxNav = pjaxNav;
  JM.initDlBadge = initDlBadge;
})(window.JM);
