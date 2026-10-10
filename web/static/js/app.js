/* ============================================================
   JM 轻量版 前端 —— 公共工具 / 搜索 / 下载 / 阅读器 / 书架 / 设置
   ============================================================ */
(function () {
  'use strict';

  var App = window.App = { version: null };

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

  /* ═══════════════════════════════════════════════════════
     搜索页
     ═══════════════════════════════════════════════════════ */
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

  // 搜索页：完整会话（查询/范围/排序/结果）存 sessionStorage，切回原样还原
  var SEARCH_SS_KEY = 'jm_lite_search_state';
  function saveSearchState() {
    var input = $('searchInput');
    try {
      sessionStorage.setItem(SEARCH_SS_KEY, JSON.stringify({
        query: input ? input.value : '',
        scope: searchState.scope,
        sort: searchState.sort,
        tagMode: searchState.tagMode,
        page: searchState.page,
        cards: searchState.cards,
        searched: searchState.searched
      }));
    } catch (e) {}
  }
  function loadSearchState() {
    try {
      var raw = sessionStorage.getItem(SEARCH_SS_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (e) { return null; }
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

  // 各页 init 都带 DOM 守卫（元素不存在直接 return），这里可以安全全调
  function initSubscriptionsPage() {
    var root = $('subPageRoot');
    if (!root) return;                       // 非订阅页，自守卫直接退出

    var blocksEl = $('subAuthorBlocks');
    var emptyEl = $('subEmpty');
    if ($('subManageBtn')) {
      $('subManageBtn').addEventListener('click', function () { pjaxNav('/settings', true); });
    }

    function renderAuthorBlock(author) {
      var block = document.createElement('section');
      block.className = 'sub-author-block';
      block.innerHTML =
        '<div class="sub-author-head">' +
          '<h2 class="sub-author-name">' + esc(author) + '</h2>' +
          '<span class="sub-author-count" data-count></span>' +
        '</div>' +
        '<div class="comic-grid sub-author-grid" data-grid>' +
          '<div class="sub-block-loading">加载中…</div>' +
        '</div>';
      blocksEl.appendChild(block);
      var grid = block.querySelector('[data-grid]');
      var countEl = block.querySelector('[data-count]');
      api('/api/subscription-works?author=' + encodeURIComponent(author))
        .then(function (r) {
          if (!r || !r.success) throw new Error((r && r.message) || '加载失败');
          var works = r.works || [];
          if (r.error) {
            grid.innerHTML = '<div class="sub-block-error">该作者加载失败：' + esc(r.error) + '</div>';
            return;
          }
          if (!works.length) {
            grid.innerHTML = '<div class="sub-block-error">没有找到该作者的作品</div>';
            return;
          }
          var unread = works.filter(function (w) { return !w.read; }).length;
          countEl.textContent = '共 ' + works.length + ' 部 · 未看 ' + unread;
          grid.innerHTML = works.map(function (w) {
            return cardHtml({ id: w.id, title: w.title, author: w.author, cover: w.cover, finished: w.read });
          }).join('');
        })
        .catch(function (e) {
          grid.innerHTML = '<div class="sub-block-error">加载失败：' + esc(e.message) + '</div>';
        });
    }

    api('/api/subscriptions')
      .then(function (r) {
        var subs = (r && r.data) || [];
        var authors = subs.map(function (s) { return s.author; }).filter(Boolean);
        if (!authors.length) { emptyEl.hidden = false; return; }
        emptyEl.hidden = true;
        authors.forEach(renderAuthorBlock);
      })
      .catch(function () {
        emptyEl.hidden = false;
        var t = emptyEl.querySelector('.empty-state__title');
        if (t) t.textContent = '订阅列表加载失败';
      });

    // 卡片点击 → 详情（块内委托，避免影响其它页的卡片监听）
    root.addEventListener('click', function (e) {
      var card = e.target.closest('.comic-card');
      if (card && card.dataset.jmId) openDetail(card.dataset.jmId);
    });
  }

  function routeInit() {
    initSearchPage();
    initDownloadsPage();
    initLibraryPage();
    initSettingsPage();
    initSubscriptionsPage();
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

  var searchState = {
    scope: 'keyword',   // keyword | tag | author
    sort: 'mr',
    tagMode: 'or',
    page: 1,
    loading: false,
    cards: [],
    searched: false,
  };

  function isDigits(s) { return /^\d+$/.test(s || ''); }

  function cardHtml(c) {
    var id = c.id || 0;
    var badges = '';
    if (c.downloaded) badges += '<span class="status-badge status-badge--dl">已下载</span>';
    if (c.finished) badges += '<span class="status-badge status-badge--fin">已读完</span>';
    var tags = c.tags || [];
    var shown = tags.slice(0, 6).map(function (t) {
      return '<span class="tag-chip">' + esc(t) + '</span>';
    }).join('');
    if (tags.length > 6) shown += '<span class="tag-chip tag-chip--more">+' + (tags.length - 6) + '</span>';
    var dlBtn = '<button class="card-dl" type="button" data-dl="' + id + '"' +
      ' data-title="' + esc(c.title || '') + '" title="下载" aria-label="下载">' +
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
      '<path d="M12 3v12"/><path d="M7 10l5 5 5-5"/><path d="M5 21h14"/></svg></button>';
    return '' +
      '<div class="comic-card" data-jm-id="' + id + '">' +
        badges +
        '<div class="comic-card__coverwrap">' +
          (id
            ? '<img class="comic-card__cover" src="/api/cover/proxy/' + id + '" loading="lazy" alt="" onerror="this.classList.add(\'is-broken\');this.style.visibility=\'hidden\'">'
            : (c.cover
                ? '<img class="comic-card__cover" src="' + esc(c.cover) + '" loading="lazy" alt="" onerror="this.classList.add(\'is-broken\');this.style.visibility=\'hidden\'">'
                : '<div class="comic-card__cover is-empty"></div>')) +
          dlBtn +
        '</div>' +
        '<div class="comic-card__body">' +
          '<div class="comic-card__title">' + esc(c.title || '未命名漫画') + '</div>' +
          '<div class="comic-card__meta"><span class="m-author">' + esc(c.author || '未知作者') + '</span>' +
            '<span class="m-jm">JM' + id + '</span></div>' +
          '<div class="comic-card__tags">' + shown + '</div>' +
        '</div>' +
      '</div>';
  }

  function renderCards(list, append) {
    var grid = $('comicGrid');
    if (!grid) return;
    if (!append) {
      grid.innerHTML = '';
      searchState.cards = [];
    }
    if (list.length) grid.insertAdjacentHTML('beforeend', list.map(cardHtml).join(''));
    searchState.cards = searchState.cards.concat(list);
    if (!append) enrichMissing(list);
    saveSearchState();
  }

  function setCount() {
    var el = $('resultCount');
    if (el) el.textContent = searchState.searched ? ('共 ' + searchState.cards.length + ' 条') : '';
  }

  /** 搜索用时（端到端：请求 + 响应），显示在筛选行右侧空白处 */
  function setSearchTime(ms) {
    var el = $('searchTime');
    if (!el) return;
    el.textContent = (ms != null && ms > 0) ? ('用时 ' + (ms / 1000).toFixed(2) + ' s') : '';
  }

  function showLoading(on) {
    var el = $('loading');
    if (el) el.hidden = !on;
  }

  function showEmpty(title, sub) {
    var box = $('emptyState');
    if (!box) return;
    $('emptyTitle').textContent = title || '没有结果';
    $('emptySub').textContent = sub || '换个关键词或 JM 号试试';
    box.hidden = false;
  }

  function hideEmpty() {
    var box = $('emptyState');
    if (box) box.hidden = true;
  }

  function setLoadMore(on) {
    var el = $('loadMore');
    if (el) el.hidden = !on;
  }

  function enrichMissing(list) {
    var need = list.filter(function (c) { return c.id && (!c.tags || !c.tags.length); });
    if (!need.length) return;
    var ids = need.map(function (c) { return c.id; });
    var chunks = [];
    for (var i = 0; i < ids.length; i += 12) chunks.push(ids.slice(i, i + 12));
    setTimeout(function () { chunks.forEach(enrichChunk); }, 300);
  }

  async function enrichChunk(chunk) {
    try {
      var r = await api('/api/search/enrich?ids=' + chunk.join(','));
      if (!r || !r.success || !r.data) return;
      Object.keys(r.data).forEach(function (key) {
        var d = r.data[key];
        var card = document.querySelector('.comic-card[data-jm-id="' + key + '"]');
        if (!card || !d.tags || !d.tags.length) return;
        var box = card.querySelector('.comic-card__tags');
        if (box && !box.children.length) {
          box.innerHTML = d.tags.slice(0, 6).map(function (t) {
            return '<span class="tag-chip">' + esc(t) + '</span>';
          }).join('');
        }
      });
    } catch (e) { /* 静默 */ }
  }

  async function doSearch(reset) {
    if (searchState.loading) return;
    var t0 = Date.now();                      // 端到端耗时（含网络），finally 里统一上报
    var input = $('searchInput');
    var q = (input && input.value || '').trim();
    var scope = searchState.scope;
    var needMsg = { keyword: '请输入关键词', tag: '请输入标签', author: '请输入作者名' }[scope];
    if (!q) { toast(needMsg); return; }

    if (reset) searchState.page = 1;
    searchState.loading = true;
    searchState.searched = true;
    showLoading(true);
    hideEmpty();
    setLoadMore(false);

    try {
      if (scope === 'keyword' && isDigits(q)) {
        var rj = await api('/api/search/jm/' + q);
        if (rj.success && rj.data) {
          renderCards([rj.data], false);
          setCount();
        } else {
          renderCards([], false);
          setCount();
          showEmpty('没有找到这本漫画', rj.message || ('JM 号 ' + q + ' 无结果'));
        }
        return;
      }

      var url;
      if (scope === 'keyword') {
        url = '/api/search/keyword?keyword=' + encodeURIComponent(q) +
              '&order_by=' + encodeURIComponent(searchState.sort) +
              '&page=' + searchState.page;
      } else if (scope === 'tag') {
        url = '/api/search/tags?tags=' + encodeURIComponent(q) +
              '&mode=' + encodeURIComponent(searchState.tagMode);
      } else {
        url = '/api/search/author?author=' + encodeURIComponent(q);
      }

      var r = await api(url);
      if (!r.success) {
        toast(r.message || '搜索失败');
        if (reset) { renderCards([], false); }
        showEmpty('搜索失败', r.message || '');
        setCount();
        return;
      }
      var list = r.data || [];
      renderCards(list, searchState.page > 1);
      setCount();
      if (!list.length && searchState.page === 1) {
        showEmpty('没有结果', scope === 'tag' ? '换个标签或改「或/且」试试' : '换个关键词试试');
      }
      if (scope === 'keyword' && list.length >= 20) setLoadMore(true);
      var tmg = $('tagModeGroup');
      if (tmg) tmg.hidden = scope !== 'tag';
    } catch (e) {
      toast('网络异常：' + e.message);
      showEmpty('网络异常', '请检查网络或代理设置');
    } finally {
      searchState.loading = false;
      showLoading(false);
      setSearchTime(Date.now() - t0);
    }
  }

  /* ── 详情模态 ─────────────────────────────────────────── */
  async function openDetail(jmId) {
    try {
      var r = await api('/api/detail/' + jmId);
      if (!r.success) { toast(r.message || '加载失败'); return; }
      showDetailModal(r.data || {});
    } catch (e) {
      toast('加载详情失败：' + e.message);
    }
  }

  function closeModal() {
    var m = $('detailModal');
    if (m) m.remove();
  }

  function showDetailModal(c) {
    closeModal();
    var tags = (c.tags || []).map(function (t) {
      return '<span class="tag-chip">' + esc(t) + '</span>';
    }).join('');
    var overlay = document.createElement('div');
    overlay.id = 'detailModal';
    overlay.className = 'modal-overlay';
    overlay.innerHTML = '' +
      '<div class="modal" role="dialog" aria-modal="true">' +
        '<button class="modal__close" id="modalClose" title="关闭">×</button>' +
        '<div class="detail">' +
          '<div class="detail__cover">' +
            (c.id
              ? '<img src="/api/cover/proxy/' + c.id + '" alt="" onerror="this.style.visibility=\'hidden\'">'
              : (c.cover
                  ? '<img src="' + esc(c.cover) + '" alt="" onerror="this.style.visibility=\'hidden\'">'
                  : '<div class="detail__cover-empty"></div>')) +
          '</div>' +
          '<div class="detail__info">' +
            '<h2 class="detail__title">' + esc(c.title || '未命名漫画') + '</h2>' +
            '<div class="detail__meta">' +
              '<span>作者：' + esc(c.author || '未知') + '</span>' +
              (c.favorites ? '<span>收藏：' + Number(c.favorites).toLocaleString() + '</span>' : '') +
              (c.pages ? '<span>页数：' + esc(c.pages) + '</span>'
                : (c.chapters ? '<span>章节：' + esc(c.chapters) + '</span>' : '')) +
              '<span class="muted">JM ' + esc(c.id || '') + '</span>' +
            '</div>' +
            '<div class="detail__tags">' + tags + '</div>' +
            (c.description ? '<p class="detail__desc">' + esc(c.description) + '</p>' : '') +
            '<div class="detail__actions">' +
              '<button class="btn btn--primary" id="detailDlBtn">下载</button>' +
            '</div>' +
          '</div>' +
        '</div>' +
      '</div>';
    document.body.appendChild(overlay);
    overlay.addEventListener('click', function (e) {
      if (e.target === overlay) closeModal();
    });
    var btn = $('modalClose');
    if (btn) btn.addEventListener('click', closeModal);
    var dlBtn = $('detailDlBtn');
    if (dlBtn) dlBtn.addEventListener('click', function () { startDownload(c.id, c.title); });
  }

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') closeModal();
  });

  /* ── 搜索页初始化 ─────────────────────────────────────── */
  function initSearchPage() {
    if (!$('searchInput')) return;

    /* 搜索列数（设置 search_columns：0=自动；进页面时同步一次） */
    (function applySearchCols() {
      var g = $('comicGrid');
      if (!g) return;
      api('/api/settings').then(function (r) {
        var n = parseInt(((r.data || {}).search_columns) || '0', 10) || 0;
        if (n > 0) g.style.setProperty('--lib-cols', n);
        else g.style.removeProperty('--lib-cols');
      }).catch(function () { /* 静默，用默认 */ });
    })();

    var input = $('searchInput');
    var btn = $('searchBtn');
    var grid = $('comicGrid');

    if (btn) btn.addEventListener('click', function () { doSearch(true); });
    if (input) input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') doSearch(true);
    });
    if (input) input.addEventListener('input', saveSearchState);

    document.querySelectorAll('#scopeTabs .seg-item').forEach(function (t) {
      t.addEventListener('click', function () {
        document.querySelectorAll('#scopeTabs .seg-item').forEach(function (x) {
          x.classList.remove('is-active');
        });
        t.classList.add('is-active');
        searchState.scope = t.dataset.scope || 'keyword';
        var tmg = $('tagModeGroup');
        if (tmg) tmg.hidden = searchState.scope !== 'tag';
        if (searchState.searched) doSearch(true);
      });
    });

    var sortSel = $('sortBy');
    if (sortSel) sortSel.addEventListener('change', function () {
      searchState.sort = sortSel.value;
      if (searchState.searched) doSearch(true);
    });
    var tagMode = $('tagMode');
    if (tagMode) tagMode.addEventListener('change', function () {
      searchState.tagMode = tagMode.value;
      if (searchState.searched) doSearch(true);
    });

    var more = $('loadMoreBtn');
    if (more) more.addEventListener('click', function () {
      searchState.page += 1;
      doSearch(false);
    });

    if (grid) grid.addEventListener('click', function (e) {
      var dlBtn = e.target.closest('[data-dl]');
      if (dlBtn) { e.preventDefault(); e.stopPropagation(); startDownload(dlBtn.dataset.dl, dlBtn.dataset.title); return; }
      var card = e.target.closest('.comic-card');
      if (card && card.dataset.jmId) openDetail(card.dataset.jmId);
    });

    var qp = new URLSearchParams(location.search);
    var kw = qp.get('kw');
    if (kw) {
      input.value = kw;
      setTimeout(function () { doSearch(true); }, 60);
    } else {
      var saved = loadSearchState();
      if (saved && saved.searched && saved.cards && saved.cards.length) {
        searchState.scope = saved.scope || 'keyword';
        searchState.sort = saved.sort || 'mr';
        searchState.tagMode = saved.tagMode || 'or';
        searchState.page = saved.page || 1;
        searchState.cards = saved.cards;
        searchState.searched = true;
        input.value = saved.query || '';
        document.querySelectorAll('#scopeTabs .seg-item').forEach(function (x) {
          x.classList.toggle('is-active', (x.dataset.scope || 'keyword') === searchState.scope);
        });
        var tmg0 = $('tagModeGroup'); if (tmg0) tmg0.hidden = searchState.scope !== 'tag';
        if (sortSel) sortSel.value = searchState.sort;
        if (tagMode) tagMode.value = searchState.tagMode;
        grid.innerHTML = '';
        grid.insertAdjacentHTML('beforeend', saved.cards.map(cardHtml).join(''));
        // 不再补拉 enrich：卡片自带 tags，再发一次网络请求会拖慢切回
        setCount();
        restoreScroll();
      }
    }
  }

  /* ═══════════════════════════════════════════════════════
     下载链路
     ═══════════════════════════════════════════════════════ */
  async function startDownload(jmId, title) {
    if (!jmId) return;
    try {
      var r = await api('/api/download/' + jmId, { method: 'POST' });
      if (!r.success) { toast(r.message || '下载失败'); return; }
      toast('已开始下载：' + (title || ('JM-' + jmId)));
      var did = r.download_id;
      var start = Date.now();
      while (Date.now() - start < 600000) {
        await sleep(2000);
        var p = await api('/api/download/progress/' + did);
        if (!p.success) break;
        var d = p.data || {};
        if (d.status === 'error') { toast('下载失败：' + (d.message || '')); break; }
        if (d.status === 'completed') { toast('下载完成：' + (title || ('JM-' + jmId))); break; }
      }
    } catch (e) {
      toast('下载异常：' + e.message);
    }
  }

  function initDownloadsPage() {
    var activeList = $('activeList');
    if (!activeList) return;

    var input = $('batchInput');
    function parseIds() {
      return (input.value.match(/\d+/g) || []).map(Number);
    }
    function syncCount() {
      var n = parseIds().length;
      $('batchCount').textContent = n ? (n + ' 个任务') : '';
    }
    input.addEventListener('input', syncCount);
    syncCount();

    $('batchClearBtn').addEventListener('click', function () {
      input.value = '';
      syncCount();
    });

    $('batchDownloadBtn').addEventListener('click', async function () {
      var ids = parseIds();
      if (!ids.length) { toast('请输入至少一个 JM 号'); return; }
      if (ids.length > 20) { toast('一次最多 20 个'); return; }
      try {
        var r = await api('/api/download/batch', { method: 'POST', body: { ids: ids } });
        if (!r.success) { toast(r.message || '批量下载失败'); return; }
        var ok = (r.data || []).filter(function (x) { return x.status === 'downloading'; }).length;
        toast('已启动 ' + ok + ' 个下载任务');
        input.value = '';
        syncCount();
        refreshActive();
      } catch (e) { toast('批量下载异常：' + e.message); }
    });

    function fmtSpeed(bps) {
      if (bps == null) return '测速中…';
      if (bps < 0) bps = 0;
      if (bps >= 1024 * 1024) return (bps / (1024 * 1024)).toFixed(1) + ' MB/s';
      if (bps >= 1024) return (bps / 1024).toFixed(0) + ' KB/s';
      return '0 KB/s';
    }

    // 速度由后端「累计下载字节」增量推导（after_image 逐图累加真实字节）。
    // 早前版本是后端每秒扫 TempCache 目录估算，既吃 CPU 又会在搬运清空后读出 0。
    var speedState = {};   // download_id -> {bytes, t, ema}
    function speedOf(k, bytes) {
      var now = Date.now();
      var st = speedState[k];
      if (!st) { speedState[k] = { bytes: bytes || 0, t: now, ema: 0 }; return null; }
      var dt = (now - st.t) / 1000;
      if (dt < 0.8) return st.ema;          // 采样间隔过短，沿用上次值
      var inst = Math.max(0, ((bytes || 0) - st.bytes) / dt);
      st.ema = st.ema ? (st.ema * 0.6 + inst * 0.4) : inst;
      st.bytes = bytes || 0;
      st.t = now;
      return st.ema;
    }

    async function refreshActive() {
      try {
        var r = await api('/api/download/progress');
        var data = r.data || {};
        var keys = Object.keys(data);
        $('activeCount').textContent = keys.length ? (keys.length + ' 个') : '';
        $('activeEmpty').hidden = keys.length > 0;
        // 清理已结束任务的测速缓存，避免内存堆积
        Object.keys(speedState).forEach(function (id) { if (!data[id]) delete speedState[id]; });
        activeList.innerHTML = keys.map(function (k) {
          var d = data[k];
          var pct = Math.max(0, Math.min(100, d.progress || 0));
          var cls = '';
          if (d.status === 'error') cls = ' dl-item--error';
          else if (d.status === 'cancelled') cls = ' dl-item--done';
          var active = ['starting', 'preparing', 'downloading', 'processing'].indexOf(d.status) >= 0;
          var spd = speedOf(k, d.bytes);
          // 左侧行：大小 · 已下/余章数；右侧：速度在百分比左边（用户指定布局）
          var sub = [];
          if (d.bytes) sub.push(fmtBytes(d.bytes));
          if (d.total) {
            var doneCh = Math.min(d.done || 0, d.total);
            sub.push('已下 ' + doneCh + ' 章 · 余 ' + Math.max(0, d.total - doneCh) + ' 章');
          } else if (d.images) {
            sub.push('已下 ' + d.images + ' 图');
          }
          var subText = sub.length ? sub.join(' · ') : '';
          var msg = d.message || '';
          // 下载中且已精简数据可用时，只显示左侧行；其余阶段保留状态文案
          var line = (d.status === 'downloading' && subText)
            ? subText
            : (msg + (subText ? (msg ? ' · ' : '') + subText : ''));
          var spdText = '';
          if (active || spd) {
            var pre = (d.status === 'starting' || d.status === 'preparing');
            spdText = pre ? '测速中…' : fmtSpeed(spd || 0);
          }
          var rightText = (spdText ? spdText + ' · ' : '') + pct + '%';
          var rightBtn = active
            ? '<button class="dl-item__cancel" data-cancel="' + esc(k) + '">取消</button>'
            : '<button class="dl-item__x" data-del="' + esc(k) + '" title="移除">×</button>';
          return '<div class="dl-item' + cls + '">' +
            '<div class="dl-item__head">' +
              '<span class="dl-item__title">' + esc(d.title || ('JM-' + d.jm_id)) + '</span>' +
              rightBtn +
            '</div>' +
            '<div class="dl-bar"><div class="dl-bar__fill" style="width:' + pct + '%"></div></div>' +
            '<div class="dl-item__msg"><span>' + esc(line) + '</span>' +
              '<span class="dl-item__right muted">' + esc(rightText) + '</span></div>' +
          '</div>';
        }).join('');
      } catch (e) { /* 静默 */ }
    }

    activeList.addEventListener('click', async function (e) {
      var cancelBtn = e.target.closest('[data-cancel]');
      if (cancelBtn) {
        try {
          await api('/api/download/cancel/' + cancelBtn.dataset.cancel, { method: 'POST' });
          refreshActive();
        } catch (err) { /* 静默 */ }
        return;
      }
      var delBtn = e.target.closest('[data-del]');
      if (!delBtn) return;
      try {
        await api('/api/download/progress/' + delBtn.dataset.del, { method: 'DELETE' });
        refreshActive();
      } catch (err) { /* 静默 */ }
    });

    async function refreshHistory() {
      try {
        var r = await api('/api/download/history');
        var list = r.data || [];
        $('historyCount').textContent = list.length ? (list.length + ' 条') : '';
        $('historyEmpty').hidden = list.length > 0;
        $('historyList').innerHTML = list.map(function (h) {
          var badge = h.download_status === 'completed'
            ? '<span class="dl-status dl-status--ok">完成</span>'
            : (h.download_status === 'cancelled'
                ? '<span class="dl-status">已取消</span>'
                : '<span class="dl-status dl-status--err">失败</span>');
          var files = h.files_exist
            ? '<span class="dl-status dl-status--ok">在库</span>'
            : '<span class="dl-status">已删</span>';
          // 续下：未在库 + TempCache 有已下部分（已下的图会被自动跳过）
          var resumeBtn = h.resumable
            ? '<button class="btn btn--sm" data-resume="' + h.jm_id + '" title="从已下部分继续">续下</button>'
            : '';
          return '<div class="dl-item dl-item--flat">' +
            '<div class="dl-item__head">' +
              '<span class="dl-item__title">' + esc(h.title || ('JM-' + h.jm_id)) + '</span>' +
              badge + files +
              '<span class="muted">' + esc(h.complete_time || h.download_time || '') + '</span>' +
              resumeBtn +
              '<button class="dl-item__x" data-hid="' + h.id + '" title="删除记录">×</button>' +
            '</div>' +
            (h.error_message ? '<div class="dl-item__msg"><span>' + esc(h.error_message) + '</span></div>' : '') +
          '</div>';
        }).join('');
      } catch (e) { /* 静默 */ }
    }

    $('historyList').addEventListener('click', async function (e) {
      var rb = e.target.closest('[data-resume]');
      if (rb) {
        var jm = parseInt(rb.dataset.resume, 10);
        rb.disabled = true;
        try {
          var r = await api('/api/download/' + jm, { method: 'POST' });
          if (r.success) {
            toast('已开始续下（自动跳过已下部分）');
            refreshActive();
            refreshHistory();
          } else {
            toast(r.message || '续下失败');
            rb.disabled = false;
          }
        } catch (err) {
          toast('续下失败：' + err.message);
          rb.disabled = false;
        }
        return;
      }
      var btn = e.target.closest('[data-hid]');
      if (!btn) return;
      try {
        await api('/api/download/history/' + btn.dataset.hid, { method: 'DELETE' });
        refreshHistory();
      } catch (err) { /* 静默 */ }
    });

    $('clearHistoryBtn').addEventListener('click', async function () {
      try {
        await api('/api/download/history', { method: 'DELETE' });
        refreshHistory();
        toast('已清空历史');
      } catch (e) { /* 静默 */ }
    });

    Promise.all([refreshActive(), refreshHistory()]).then(restoreScroll);
    // 定时器登记到页面清理表：PJAX 切走时必须停掉，否则每次切回下载页都会叠加
    var _tActive = setInterval(refreshActive, 1500);
    var _tHistory = setInterval(refreshHistory, 8000);
    regCleanup(function () { clearInterval(_tActive); clearInterval(_tHistory); });
  }

  /* ═══════════════════════════════════════════════════════
     阅读器
     ═══════════════════════════════════════════════════════ */
  function initReaderPage() {
    var stage = $('readerStage');
    if (!stage) return;

    var jmId = parseInt(location.pathname.split('/').pop(), 10);
    var titleEl = $('readerTitle');
    var zoomVal = $('zoomVal');
    var chapInfo = $('chapInfo');
    var pageInfo = $('pageInfo');
    var prevChapBtn = $('prevChapBtn');
    var nextChapBtn = $('nextChapBtn');
    var rail = $('readerRail');
    var railFill = rail ? rail.querySelector('i') : null;   // 进度填充条
    var grid = $('readerGrid');
    var overviewBtn = $('overviewBtn');
    var RAIL_DEFAULT_COLOR = '#7B6FE0';
    var railColor = RAIL_DEFAULT_COLOR;
    var pps = 1;             // 览图列数（reader_pages_per_screen，1=自适应）
    var overview = false;    // 缩略图览模式

    var pages = [], current = 0, zoom = 1;
    var currentImg = null;
    var MIN_ZOOM = 0.1, MAX_ZOOM = 6;
    var viewInitialized = false;
    var chapters = [], currentChapter = '1', currentChapterIndex = 0;
    var preloadCache = {};
    var PRELOAD_COUNT = 10, PRELOAD_CONCUR = 4;
    var wheelMode = 'scroll';    // scroll=多页连排（默认）/ page=滑动翻页 / zoom=以光标缩放（读设置）
    var chapterToastEnabled = true;
    // 连排模式状态：整章图片纵向排一列，滚轮原生滚动 = 翻页
    var colEls = [];             // 每页 <img> 引用（与 pages 同序）
    var colChapter = null;       // 连排列当前所属章节 id
    var colAdvancing = false;    // 到底自动接下一章的防重入锁
    var colPendingSeek = -1;     // 建列后待定位的页（-1 = 无）

    (async function () {
      try {
        var results = await Promise.all([api('/api/read/' + jmId), api('/api/settings')]);
        var r = results[0];
        var cfg = (results[1] || {}).data || {};
        wheelMode = (cfg.reader_wheel_mode === 'page' || cfg.reader_wheel_mode === 'zoom')
          ? cfg.reader_wheel_mode : 'scroll';
        chapterToastEnabled = cfg.reader_chapter_toast !== '0';
        railColor = cfg.reader_progress_color || RAIL_DEFAULT_COLOR;
        pps = Math.min(6, Math.max(1, parseInt(cfg.reader_pages_per_screen, 10) || 1));
        if (rail) {
          rail.style.setProperty('--rail-color', railColor);
          rail.hidden = false;
        }
        if (!r.success) {
          stage.innerHTML = '<div class="empty-state"><p class="empty-state__title">无法打开</p><p class="muted">' +
            esc(r.message || '') + '</p></div>';
          return;
        }
        var d = r.data;
        if (titleEl) titleEl.textContent = d.title || ('JM-' + jmId);
        chapters = d.chapters || [];
        currentChapter = d.current_chapter || '1';
        currentChapterIndex = Math.max(0, chapters.findIndex(function (c) { return c.id === currentChapter; }));
        pages = Array.isArray(d.current_chapter_pages) ? d.current_chapter_pages : [];
        updateChapterUI();
        if (!pages.length) {
          stage.innerHTML = '<div class="empty-state"><p class="empty-state__title">该章节没有图片</p>' +
            '<p class="muted">可能是下载未完成或目录异常</p></div>';
          return;
        }
        var start = Math.min(Math.max(0, (d.read_progress || 0)), pages.length - 1);
        // 连排模式：从中间页进入时先预载前几页，拿真实宽高做占位，定位才准
        if (start > 0) {
          await preloadImages(currentChapter, pages.slice(0, Math.min(start + 2, pages.length)))
            .catch(function () {});
        }
        renderPage(start);
      } catch (e) {
        stage.innerHTML = '<div class="empty-state"><p class="empty-state__title">加载失败</p><p class="muted">' +
          esc(e.message) + '</p></div>';
      }
    })();

    function updateChapterUI() {
      var hasMulti = chapters.length > 1;
      if (chapInfo) {
        chapInfo.hidden = !hasMulti;
        if (hasMulti) chapInfo.textContent = (currentChapterIndex + 1) + ' / ' + chapters.length;
      }
      if (prevChapBtn) { prevChapBtn.hidden = !hasMulti; prevChapBtn.disabled = currentChapterIndex <= 0; }
      if (nextChapBtn) { nextChapBtn.hidden = !hasMulti; nextChapBtn.disabled = currentChapterIndex >= chapters.length - 1; }
    }

    /* ── 章节选择浮层 ─────────────────────────────────── */
    var chapPop = null;
    function closeChapPop() {
      if (chapPop) { chapPop.remove(); chapPop = null; }
    }
    function toggleChapPop() {
      if (chapPop) { closeChapPop(); return; }
      if (!chapters.length) return;
      chapPop = document.createElement('div');
      chapPop.className = 'chap-pop';
      chapPop.innerHTML = chapters.map(function (c, i) {
        return '<button class="chap-pop__item' + (i === currentChapterIndex ? ' on' : '') +
          '" data-ci="' + i + '">' + esc(c.name || ('第' + (i + 1) + '章')) + '</button>';
      }).join('');
      var rect = chapInfo.getBoundingClientRect();
      chapPop.style.left = Math.max(8, Math.min(window.innerWidth - 250, rect.left)) + 'px';
      chapPop.style.top = (rect.bottom + 6) + 'px';
      document.body.appendChild(chapPop);
      chapPop.addEventListener('click', function (e) {
        var btn = e.target.closest('[data-ci]');
        if (!btn) return;
        var idx = parseInt(btn.dataset.ci, 10);
        closeChapPop();
        if (idx !== currentChapterIndex) loadChapter(idx).then(function (ok) { if (ok) renderPage(0); });
      });
    }
    if (chapInfo) chapInfo.addEventListener('click', toggleChapPop);
    document.addEventListener('click', function (e) {
      if (chapPop && !chapPop.contains(e.target) && e.target !== chapInfo) closeChapPop();
    });

    /* ── 图片预加载（记录真实宽高：连排建列时用作占位比例，定位不漂移）── */
    function cacheSlot(cid) {
      return preloadCache[cid] || (preloadCache[cid] = { pages: [], images: new Set(), dims: {} });
    }

    async function preloadImages(cid, pageList) {
      var slice = pageList.slice(0, PRELOAD_COUNT);
      var cache = cacheSlot(cid);
      var cursor = 0;
      async function worker() {
        while (cursor < slice.length) {
          var p = slice[cursor++];
          if (cache.images.has(p)) continue;
          await new Promise(function (resolve) {
            var img = new Image();
            img.onload = function () {
              if (img.naturalWidth) cache.dims[p] = { w: img.naturalWidth, h: img.naturalHeight };
              resolve();
            };
            img.onerror = function () { resolve(); };
            img.src = '/api/comic/' + jmId + '/page/' + p + '?chapter=' + encodeURIComponent(cid);
            cache.images.add(p);
          });
        }
      }
      var workers = [];
      for (var w = 0; w < Math.min(PRELOAD_CONCUR, slice.length); w++) workers.push(worker());
      await Promise.all(workers);
    }

    async function fetchChapterPages(index) {
      if (index < 0 || index >= chapters.length) return null;
      var cid = chapters[index].id;
      var c = preloadCache[cid];
      if (c && c.pages.length) return c.pages;
      var r = await api('/api/read/' + jmId + '/chapter/' + encodeURIComponent(cid));
      if (!r.success) return null;
      var cp = Array.isArray(r.data.current_chapter_pages) ? r.data.current_chapter_pages : [];
      cacheSlot(cid).pages = cp;
      return cp;
    }

    async function loadChapter(index) {
      if (index < 0 || index >= chapters.length) return false;
      var targetCid = chapters[index].id;
      var cached = preloadCache[targetCid];
      if (cached && cached.pages.length) {
        currentChapterIndex = index;
        currentChapter = targetCid;
        pages = cached.pages;
      } else {
        var r = await api('/api/read/' + jmId + '/chapter/' + encodeURIComponent(targetCid));
        if (!r.success) { toast('章节加载失败'); return false; }
        pages = Array.isArray(r.data.current_chapter_pages) ? r.data.current_chapter_pages : [];
        var slot = cacheSlot(targetCid);
        slot.pages = pages;
        currentChapterIndex = index;
        currentChapter = targetCid;
      }
      updateChapterUI();
      var nextIdx = index + 1;
      if (nextIdx < chapters.length) fetchChapterPages(nextIdx).catch(function () {});
      return true;
    }

    async function preloadChapter(index) {
      if (index < 0 || index >= chapters.length) return;
      var pagesList = await fetchChapterPages(index);
      if (!pagesList || !pagesList.length) return;
      await preloadImages(chapters[index].id, pagesList);
    }

    function maybePreload() {
      if (!pages.length) return;
      var nextIdx = currentChapterIndex + 1;
      if (nextIdx >= chapters.length) return;
      var remaining = pages.length - current - 1;
      var ratio = ((current + 1) / pages.length) * 100;
      if (remaining <= 5 || ratio >= 25) {
        preloadChapter(nextIdx).catch(function () {});
      }
    }

    function maybePrefetchCurrent() {
      if (!pages.length) return;
      var start = current + 1;
      if (start >= pages.length) return;
      var slice = pages.slice(start, start + PRELOAD_COUNT);
      if (slice.length) preloadImages(currentChapter, slice).catch(function () {});
    }

    /* ── 进度落库（防抖 800ms） ───────────────────────── */
    var _saveTimer = null;
    function saveProgressDebounced() {
      clearTimeout(_saveTimer);
      _saveTimer = setTimeout(function () {
        api('/api/read/' + jmId + '/progress', { method: 'POST', body: { page: current } })
          .catch(function () {});
      }, 800);
    }

    var _finishedMarked = false;
    async function markReadFinishedOnce() {
      if (_finishedMarked) return;
      _finishedMarked = true;
      try {
        var r = await api('/api/status/' + jmId + '/finished', { method: 'POST', body: { finished: true } });
        if (r.success) toast('已标记读完（7 天后自动清理本地，可重新下载）');
      } catch (e) { _finishedMarked = false; }
    }

    /* ── 页面渲染 / 缩放 ─────────────────────────────── */
    function renderPage(i) {
      if (i < 0) {
        if (currentChapterIndex > 0) {
          loadChapter(currentChapterIndex - 1).then(function (ok) { if (ok) renderPage(pages.length - 1); });
        } else if (chapterToastEnabled) {
          toast('已经是第一页了');
        }
        return;
      }
      if (i >= pages.length) {
        if (currentChapterIndex < chapters.length - 1) {
          loadChapter(currentChapterIndex + 1).then(function (ok) { if (ok) renderPage(0); });
        } else {
          if (chapterToastEnabled) toast('已经是最后一页了');
          markReadFinishedOnce();
        }
        return;
      }
      current = i;
      maybePreload();
      maybePrefetchCurrent();
      saveProgressDebounced();
      // 览图模式：只更新高亮/页码，不加载大图（换章后也走这里）
      if (overview) {
        if (pageInfo) pageInfo.textContent = (current + 1) + ' / ' + pages.length;
        updateRail();
        markOverviewCurrent();
        return;
      }
      if (isCol()) { colSeek(i); return; }
      stage.scrollTop = 0;
      stage.innerHTML = '';
      var spinner = document.createElement('div');
      spinner.className = 'reader__loading';
      stage.appendChild(spinner);
      var img = document.createElement('img');
      img.className = 'reader__img';
      img.alt = '第 ' + (current + 1) + ' 页';
      img.style.width = (stage.clientWidth * zoom) + 'px';
      img.onload = function () {
        currentImg = img;
        if (spinner.parentNode) spinner.remove();
        if (!viewInitialized) { fitView(); viewInitialized = true; }
      };
      img.onerror = function () {
        stage.innerHTML = '<div class="empty-state"><p class="empty-state__title">加载失败</p>' +
          '<p class="muted">章节 ' + esc(currentChapter) + ' · 第 ' + (current + 1) + ' 页</p></div>';
      };
      img.src = '/api/comic/' + jmId + '/page/' + pages[i] + '?chapter=' + encodeURIComponent(currentChapter);
      stage.appendChild(img);
      currentImg = img;
      if (pageInfo) pageInfo.textContent = (current + 1) + ' / ' + pages.length;
      updateRail();
      if (overview) markOverviewCurrent();
    }

    /* ── 连排模式（scroll）：整章一列，滚轮原生滚动 = 翻页 ── */
    function isCol() { return wheelMode === 'scroll'; }

    function buildColumn() {
      colChapter = currentChapter;
      colEls = [];
      colAdvancing = false;
      stage.classList.add('is-col');
      stage.innerHTML = '';
      stage.style.setProperty('--pw', Math.round(stage.clientWidth * zoom) + 'px');
      var cache = cacheSlot(currentChapter);
      pages.forEach(function (p, i) {
        var wrap = document.createElement('div');
        wrap.className = 'reader__page';
        var img = document.createElement('img');
        img.className = 'reader__img';
        img.loading = 'lazy';
        img.alt = '第 ' + (i + 1) + ' 页';
        img.dataset.idx = String(i);
        var dim = cache.dims[p];
        // 占位比例：已知真实宽高用它，未知按 1.4 估（加载后自动纠正，防滚动漂移）
        img.style.aspectRatio = dim ? (dim.w + '/' + dim.h) : '1.4';
        img.onload = function () {
          if (img.naturalWidth) {
            cache.dims[p] = { w: img.naturalWidth, h: img.naturalHeight };
            img.style.aspectRatio = '';
          }
        };
        img.onerror = function () { wrap.classList.add('is-err'); };
        img.src = '/api/comic/' + jmId + '/page/' + p + '?chapter=' + encodeURIComponent(currentChapter);
        wrap.appendChild(img);
        stage.appendChild(wrap);
        colEls.push(img);
      });
      if (pageInfo) pageInfo.textContent = (current + 1) + ' / ' + pages.length;
      updateRail();
    }

    function colSeek(i) {
      i = Math.min(Math.max(0, i), Math.max(0, pages.length - 1));
      if (colChapter !== currentChapter || !colEls.length) {
        colPendingSeek = i;
        buildColumn();
        colApplyPendingSeek();
        return;
      }
      var el = colEls[i];
      if (el) {
        stage.scrollTop = Math.max(0, el.offsetTop - 8);
        colSync(i);   // 显式同步（滚动位置若恰好不变，scroll 事件不触发）
      }
    }

    function colApplyPendingSeek() {
      if (colPendingSeek < 0) return;
      var i = colPendingSeek;
      colPendingSeek = -1;
      var el = colEls[i];
      if (el) stage.scrollTop = Math.max(0, el.offsetTop - 8);
      colSync(i);
    }

    function colSync(forceIdx) {
      if (!pages.length) return;
      var idx = (typeof forceIdx === 'number' && forceIdx >= 0)
        ? forceIdx
        : ReaderLogic.columnIndex(
            stage.scrollTop, stage.clientHeight,
            colEls.map(function (el) { return el.offsetTop; }),
            colEls.map(function (el) { return el.offsetHeight || 0; }));
      if (idx < 0) return;
      if (idx !== current) {
        current = idx;
        maybePreload();
        maybePrefetchCurrent();
        saveProgressDebounced();
        if (overview) markOverviewCurrent();
      }
      currentImg = colEls[current] || null;
      if (pageInfo) pageInfo.textContent = (current + 1) + ' / ' + pages.length;
      updateRail();
      // 到底：非末章自动接下一章；末章标记读完
      var atBottom = stage.scrollTop + stage.clientHeight >= stage.scrollHeight - 4;
      if (atBottom && current >= pages.length - 1) {
        if (currentChapterIndex < chapters.length - 1) {
          if (!colAdvancing) {
            colAdvancing = true;
            loadChapter(currentChapterIndex + 1).then(function (ok) {
              colAdvancing = false;
              if (ok) { zoom = 1; renderPage(0); }
            });
          }
        } else {
          markReadFinishedOnce();
        }
      }
    }

    function applyColZoom(newZoom) {
      zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, newZoom));
      stage.style.setProperty('--pw', Math.round(stage.clientWidth * zoom) + 'px');
      if (zoomVal) zoomVal.textContent = Math.round(zoom * 100) + '%';
    }

    /* ── 右侧进度滑轨（手机端 reader_progress_color 复刻）────── */
    function updateRail() {
      if (!railFill || !pages.length) return;
      railFill.style.height = (((current + 1) / pages.length) * 100).toFixed(2) + '%';
    }

    /* ── 缩略图览（手机端 reader_pages_per_screen 复刻）──────── */
    function renderOverview() {
      if (!grid) return;
      grid.hidden = false;
      stage.hidden = true;
      if (pps > 1) {
        grid.classList.add('is-fixed');
        grid.style.setProperty('--cols', pps);
      } else {
        grid.classList.remove('is-fixed');
      }
      grid.innerHTML = ReaderLogic.buildOverviewHtml(jmId, currentChapter, pages, current);
    }

    function markOverviewCurrent() {
      if (!grid) return;
      var cells = grid.querySelectorAll('.reader__grid__cell');
      for (var i = 0; i < cells.length; i++) {
        cells[i].classList.toggle('is-cur', i === current);
      }
      var cur = grid.querySelector('.reader__grid__cell.is-cur');
      if (cur && cur.scrollIntoView) cur.scrollIntoView({ block: 'nearest' });
    }

    function setOverview(on) {
      overview = !!on;
      if (overview) {
        renderOverview();
      } else {
        if (grid) { grid.hidden = true; grid.innerHTML = ''; }
        stage.hidden = false;
      }
      if (overviewBtn) overviewBtn.textContent = overview ? '回到阅读' : '览图';
      if (rail) rail.hidden = overview;   // 览图模式下隐藏滑轨
    }

    function applyZoom(newZoom, focalX, focalY) {
      var img = currentImg;
      if (!img) return;
      newZoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, newZoom));
      var sw = stage.clientWidth, sh = stage.clientHeight;
      if (focalX == null) { focalX = sw / 2; focalY = sh / 2; }
      var oldW = img.clientWidth, oldH = img.clientHeight;
      var fX = 0, fY = 0;
      if (oldW > 0 && oldH > 0) {
        fX = (stage.scrollLeft + focalX) / oldW;
        fY = (stage.scrollTop + focalY) / oldH;
      }
      zoom = newZoom;
      img.style.width = (sw * zoom) + 'px';
      var newW = img.clientWidth, newH = img.clientHeight;
      if (newW > 0 && newH > 0) {
        stage.scrollLeft = fX * newW - focalX;
        stage.scrollTop = fY * newH - focalY;
      }
      if (zoomVal) zoomVal.textContent = Math.round(zoom * 100) + '%';
    }

    function fitView() {
      var img = currentImg;
      if (!img || !img.naturalWidth) return;
      var sw = stage.clientWidth, sh = stage.clientHeight;
      var targetW;
      if (wheelMode === 'scroll') {
        // 半页模式：页高 ≈ 2× 视口高，滚轮纵向翻动
        targetW = img.naturalWidth * ((sh * 2) / img.naturalHeight);
      } else if (wheelMode === 'page') {
        // 滑动翻页：宽度铺满，页高超出视口时滚轮先页内滑、到底/到顶再翻页
        targetW = sw;
      } else {
        targetW = img.naturalWidth * Math.min(sw / img.naturalWidth, sh / img.naturalHeight);
      }
      zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, targetW / sw));
      img.style.width = (sw * zoom) + 'px';
      img.style.left = (sw > img.clientWidth ? (sw - img.clientWidth) / 2 : 0) + 'px';
      stage.scrollTop = 0;
      stage.scrollLeft = 0;
      if (zoomVal) zoomVal.textContent = Math.round(zoom * 100) + '%';
    }

    /* ── 交互绑定 ─────────────────────────────────────── */
    $('prevBtn').addEventListener('click', function () { renderPage(current - 1); });
    $('nextBtn').addEventListener('click', function () { renderPage(current + 1); });
    if (pageInfo) pageInfo.addEventListener('click', function () {
      var p = prompt('跳转到第几页？（1-' + pages.length + '）', String(current + 1));
      if (p === null) return;
      var n = parseInt(p, 10);
      if (isNaN(n) || n < 1 || n > pages.length) { toast('请输入 1-' + pages.length + ' 之间的页码'); return; }
      renderPage(n - 1);
    });
    if (prevChapBtn) prevChapBtn.addEventListener('click', function () {
      if (currentChapterIndex > 0) loadChapter(currentChapterIndex - 1).then(function (ok) { if (ok) renderPage(pages.length - 1); });
    });
    if (nextChapBtn) nextChapBtn.addEventListener('click', function () {
      if (currentChapterIndex < chapters.length - 1) loadChapter(currentChapterIndex + 1).then(function (ok) { if (ok) renderPage(0); });
    });
    // ── 进度滑轨：按下即预览定位，拖动实时预览，松开跳页 ──
    if (rail) {
      var railSeeking = false, railTarget = null;
      function railPreview(clientY) {
        if (!pages.length) return;
        var rect = rail.getBoundingClientRect();
        var idx = ReaderLogic.railIndex(clientY, rect.top, rect.height, pages.length);
        if (idx < 0) return;
        railTarget = idx;
        if (railFill) railFill.style.height = (((idx + 1) / pages.length) * 100).toFixed(2) + '%';
        if (pageInfo) pageInfo.textContent = (idx + 1) + ' / ' + pages.length;
      }
      rail.addEventListener('mousedown', function (e) {
        if (e.button !== 0 || overview) return;   // 右键留给缩放
        e.preventDefault();
        railSeeking = true;
        railPreview(e.clientY);
      });
      document.addEventListener('mousemove', function (e) {
        if (railSeeking) railPreview(e.clientY);
      });
      document.addEventListener('mouseup', function () {
        if (!railSeeking) return;
        railSeeking = false;
        if (railTarget != null && railTarget !== current) renderPage(railTarget);
        railTarget = null;
      });
    }

    // ── 览图：切换 + 点击定位（手机端「缩略图览」复刻）──
    if (overviewBtn) {
      overviewBtn.addEventListener('click', function () { setOverview(!overview); });
    }
    if (grid) {
      grid.addEventListener('click', function (e) {
        var cell = e.target.closest('[data-idx]');
        if (!cell) return;
        var idx = parseInt(cell.dataset.idx, 10);
        setOverview(false);
        renderPage(idx);
      });
    }

    $('zoomIn').addEventListener('click', function () {
      if (isCol()) applyColZoom(zoom * 1.2); else applyZoom(zoom * 1.2);
    });
    $('zoomOut').addEventListener('click', function () {
      if (isCol()) applyColZoom(zoom / 1.2); else applyZoom(zoom / 1.2);
    });
    $('closeReader').addEventListener('click', function () {
      if (history.length > 1) history.back();
      else location.href = '/library';
    });

    // 滚轮：动作判定交给 ReaderLogic.resolveWheelAction（纯函数，可单测），
    // 这里只负责执行——右键+滚轮=缩放（任何模式）／page=滑动翻页／scroll／zoom
    var wheelAcc = 0, wheelLockUntil = 0;
    stage.addEventListener('wheel', function (e) {
      // 连排模式：普通滚轮直接交给原生滚动（滚动即翻页），不拦截
      if (isCol() && !(e.buttons & 2) && !e.ctrlKey) return;
      // 连排 + 缩放（Ctrl+滚轮 / 右键+滚轮）
      if (isCol()) {
        e.preventDefault();
        applyColZoom(zoom * (e.deltaY < 0 ? 1.15 : 1 / 1.15));
        return;
      }
      if (!currentImg) return;
      e.preventDefault();
      var rect = stage.getBoundingClientRect();
      var act = ReaderLogic.resolveWheelAction(
        { deltaY: e.deltaY, buttons: e.buttons },
        {
          mode: wheelMode, acc: wheelAcc, lockUntil: wheelLockUntil, now: Date.now(),
          atTop: stage.scrollTop <= 4,
          atBottom: stage.scrollTop + stage.clientHeight >= stage.scrollHeight - 4
        });
      wheelAcc = act.acc;
      wheelLockUntil = act.lockUntil;
      if (act.action === 'zoom') {
        applyZoom(zoom * (e.deltaY < 0 ? 1.15 : 1 / 1.15), e.clientX - rect.left, e.clientY - rect.top);
      } else if (act.action === 'scroll') {
        stage.scrollTop += e.deltaY;
      } else if (act.action === 'scrollPage') {
        stage.scrollTop += act.dir * stage.clientHeight * 0.85;
      } else if (act.action === 'flip') {
        renderPage(current + act.dir);
      }
    }, { passive: false });
    // 右键仅用于配合滚轮缩放，屏蔽系统右键菜单
    stage.addEventListener('contextmenu', function (e) { e.preventDefault(); });
    // 连排模式：滚动即翻页（当前页跟随视口，进度/滑轨/预读全部联动）
    stage.addEventListener('scroll', function () {
      if (isCol() && !overview && colEls.length) colSync();
    }, { passive: true });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowLeft') renderPage(current - 1);
      else if (e.key === 'ArrowRight') renderPage(current + 1);
      else if (e.key === 'ArrowUp') {
        if (overview && grid) grid.scrollTop -= 120; else stage.scrollTop -= 120;
        e.preventDefault();
      }
      else if (e.key === 'ArrowDown') {
        if (overview && grid) grid.scrollTop += 120; else stage.scrollTop += 120;
        e.preventDefault();
      }
      else if (e.key === 'Escape') {
        if (overview) setOverview(false);      // 先退出览图
        else $('closeReader').click();
      }
    });
  }

  /* ═══════════════════════════════════════════════════════
     书架 + 分类 + 多选 + 回收站
     ═══════════════════════════════════════════════════════ */
  function initLibraryPage() {
    var treeEl = $('catTree');
    if (!treeEl) return;

    var grid = $('comicGrid');
    var emptyBox = $('emptyState');
    var nameEl = $('currentCatName');
    var countEl = $('currentCatCount');
    var shelfView = $('shelfView');
    var recycleView = $('recycleView');
    var recycleGrid = $('recycleGrid');
    var recycleBadge = $('recycleBadge');
    var selToolbar = $('selToolbar');

    var treeData = [];
    var allComics = [];
    var view = { type: 'all', id: null };  // all | fav | uncat | cat
    var selection = { on: false, ids: new Set() };
    // 书架配置（refresh 时从 /api/settings 同步）：排序 / 每行列数 / 读完处理
    var shelfCfg = { sort: 'download_desc', columns: 0, finished: 'divider' };
    var sortSel = $('shelfSort');

    function findNode(nodes, id) {
      for (var i = 0; i < (nodes || []).length; i++) {
        if (nodes[i].id === id) return nodes[i];
        var r = findNode(nodes[i].children, id);
        if (r) return r;
      }
      return null;
    }

    function walkTree(nodes, fn, depth) {
      (nodes || []).forEach(function (n) {
        fn(n, depth || 0);
        walkTree(n.children, fn, (depth || 0) + 1);
      });
    }

    function viewTitle() {
      if (view.type === 'all') return '全部漫画';
      if (view.type === 'fav') return '收藏';
      if (view.type === 'uncat') return '未归类';
      var n = findNode(treeData, view.id);
      return n ? n.name : '分类';
    }

    function isRead(c) {
      return !!((c.read_progress && c.read_progress > 0) || c.last_read_time);
    }

    function filtered() {
      if (view.type === 'fav') return allComics.filter(function (c) { return c.favorite; });
      if (view.type === 'uncat') return allComics.filter(function (c) { return !(c.category_ids || []).length; });
      if (view.type === 'cat') return allComics.filter(function (c) { return (c.category_ids || []).indexOf(view.id) >= 0; });
      return allComics;
    }

    /* ── 分类树 ─────────────────────────────────────── */
    function treeRow(opts) {
      var cls = 'tree-row';
      if (opts.active) cls += ' on';
      if (opts.virtual) cls += ' tree-row--virt';
      var acts = '';
      if (!opts.virtual) {
        acts = '<span class="tree-acts">' +
          '<button data-rename="' + opts.id + '" title="重命名">✎</button>' +
          '<button data-delcat="' + opts.id + '" title="删除分类">🗑</button>' +
          '</span>';
      }
      return '<div class="' + cls + '"' + (opts.virtual ? '' : ' draggable="true"') +
        ' data-cat="' + (opts.virtual ? '' : opts.id) + '"' +
        (opts.virtual ? ' data-virt="' + opts.virt + '"' : '') +
        ' style="padding-left:' + (10 + (opts.depth || 0) * 14) + 'px">' +
        '<span class="tree-name">' + esc(opts.name) + '</span>' +
        '<span class="tree-count">' + (opts.count || 0) + '</span>' + acts +
      '</div>';
    }

    function renderTree() {
      var favCount = allComics.filter(function (c) { return c.favorite; }).length;
      var uncatCount = allComics.filter(function (c) { return !(c.category_ids || []).length; }).length;
      var html = '';
      html += treeRow({ virtual: true, virt: 'all', name: '全部', count: allComics.length, active: view.type === 'all' });
      html += treeRow({ virtual: true, virt: 'fav', name: '收藏', count: favCount, active: view.type === 'fav' });
      html += treeRow({ virtual: true, virt: 'uncat', name: '未归类', count: uncatCount, active: view.type === 'uncat' });
      html += '<div class="tree-sep"></div>';
      if (treeData.length) {
        walkTree(treeData, function (n, depth) {
          html += treeRow({
            id: n.id, name: n.name, count: n.count, depth: depth,
            active: view.type === 'cat' && view.id === n.id,
          });
        });
      } else {
        html += '<div class="tree-empty muted">还没有分类，点上方「＋」新建</div>';
      }
      treeEl.innerHTML = html;
    }

    /* ── 书架卡片 ───────────────────────────────────── */
    function shelfCardHtml(c) {
      var id = c.id;
      var badges = '';
      if (c.favorite) badges += '<span class="status-badge status-badge--fav">★</span>';
      if (c.finished) badges += '<span class="status-badge status-badge--fin">已读完</span>';
      var pct = (c.pages && c.read_progress > 0) ? Math.min(100, Math.round(c.read_progress / c.pages * 100)) : 0;
      var progress = pct ? '<span class="shelf-progress">读至 ' + pct + '%</span>' : '';
      var dlBtn = '<button class="card-dl" type="button" data-dl="' + id + '"' +
        ' data-title="' + esc(c.title || '') + '" title="下载" aria-label="下载">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
        '<path d="M12 3v12"/><path d="M7 10l5 5 5-5"/><path d="M5 21h14"/></svg></button>';
      var pagesTxt = (c.pages ? ' · ' + (c.pages || 0) + ' 页' : '');
      var favSvg = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round">' +
        '<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>';
      var delSvg = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
        '<polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>';
      return '<div class="comic-card" draggable="true" data-jm-id="' + id + '">' +
        badges +
        '<div class="comic-card__coverwrap">' +
          '<img class="comic-card__cover" src="/api/cover/downloaded/' + id + '" loading="lazy" alt="" ' +
            'onerror="this.classList.add(\'is-broken\');this.style.visibility=\'hidden\'">' +
          dlBtn +
        '</div>' +
        '<div class="comic-card__body">' +
          '<div class="comic-card__title">' + esc(c.title || ('JM-' + id)) + '</div>' +
          '<div class="comic-card__meta"><span class="m-author">' + esc(c.author || '未知作者') + '</span>' +
            '<span class="m-jm">JM' + id + '</span>' + pagesTxt + '</div>' +
          '<div class="shelf-actions">' +
            '<button class="shelf-act' + (c.favorite ? ' on' : '') + '" data-act="fav" data-id="' + id +
              '" data-on="' + (c.favorite ? 1 : 0) + '" title="收藏" aria-label="收藏">' + favSvg + '</button>' +
            '<button class="shelf-act shelf-act--del" data-act="del" data-id="' + id +
              '" title="删除本地（移入回收站）" aria-label="删除">' + delSvg + '</button>' +
            progress +
          '</div>' +
        '</div>' +
      '</div>';
    }

    function renderGrid() {
      var list = filtered();
      // 已读完处理（手机端 finished_in_library 对齐）：
      //   divider = 沉底 + 分隔线（默认）；hidden = 不显示
      var doneCount = list.filter(function (c) { return c.finished; }).length;
      if (shelfCfg.finished === 'hidden') {
        list = list.filter(function (c) { return !c.finished; });
      }
      if (nameEl) nameEl.textContent = viewTitle();
      if (countEl) countEl.textContent = list.length ? (list.length + ' 部') : '';
      if (emptyBox) emptyBox.hidden = list.length > 0;
      // 每行列数（0 = 自动随窗口）
      if (shelfCfg.columns > 0) grid.style.setProperty('--lib-cols', shelfCfg.columns);
      else grid.style.removeProperty('--lib-cols');
      var html;
      if (shelfCfg.finished === 'divider' && doneCount > 0) {
        var unread = list.filter(function (c) { return !c.finished; });
        var done = list.filter(function (c) { return c.finished; });
        html = unread.map(shelfCardHtml).join('') +
          '<div class="lib-divider"><span>已读完 · ' + done.length + ' 本</span></div>' +
          done.map(shelfCardHtml).join('');
      } else {
        html = list.map(shelfCardHtml).join('');
      }
      grid.innerHTML = html;
      // 多选态：回填选中样式
      if (selection.on) {
        grid.querySelectorAll('.comic-card').forEach(function (card) {
          if (selection.ids.has(parseInt(card.dataset.jmId, 10))) card.classList.add('is-selected');
        });
      }
    }

    /* ── 多选模式 ───────────────────────────────────── */
    function setSelCount() {
      var el = $('selCount');
      if (el) el.textContent = selection.ids.size;
    }
    function enterSelection() {
      selection.on = true;
      selection.ids = new Set();
      document.body.classList.add('selection-mode');
      if (selToolbar) selToolbar.hidden = false;
      if ($('selectBtn')) $('selectBtn').disabled = true;
      setSelCount();
      renderGrid();
    }
    function exitSelection() {
      selection.on = false;
      selection.ids = new Set();
      document.body.classList.remove('selection-mode');
      if (selToolbar) selToolbar.hidden = true;
      if ($('selectBtn')) $('selectBtn').disabled = false;
      renderGrid();
    }
    function toggleSelect(jmId) {
      if (selection.ids.has(jmId)) selection.ids.delete(jmId);
      else selection.ids.add(jmId);
      var card = grid.querySelector('.comic-card[data-jm-id="' + jmId + '"]');
      if (card) card.classList.toggle('is-selected', selection.ids.has(jmId));
      setSelCount();
    }
    function selectBy(mode) {
      var list = filtered();
      selection.ids = new Set();
      list.forEach(function (c) {
        if (mode === 'all') selection.ids.add(c.id);
        else if (mode === 'read' && isRead(c)) selection.ids.add(c.id);
        else if (mode === 'unread' && !isRead(c)) selection.ids.add(c.id);
      });
      setSelCount();
      renderGrid();
    }
    async function deleteSelected() {
      var ids = Array.from(selection.ids);
      if (!ids.length) { toast('请先选择要删除的漫画'); return; }
      if (!confirm('删除所选 ' + ids.length + ' 本？将移入回收站，7 天内可恢复或重新下载。')) return;
      var ok = 0;
      for (var i = 0; i < ids.length; i++) {
        try {
          var r = await api('/api/delete/' + ids[i], { method: 'DELETE' });
          if (r.success) ok++;
        } catch (e) { /* 单本失败不影响其余 */ }
      }
      toast('已删除 ' + ok + '/' + ids.length + ' 本（移入回收站）');
      exitSelection();
      refresh();
    }

    /* ── 回收站视图 ─────────────────────────────────── */
    function recycleCardHtml(it) {
      var id = it.id;
      var chip = it.local
        ? '<span class="recycle-chip recycle-chip--grace">宽限中 · 剩 ' + it.remain_days + ' 天</span>'
        : '<span class="recycle-chip recycle-chip--gone">可重新下载</span>';
      var cover = '/api/cover/downloaded/' + id;
      var online = '/api/cover/proxy/' + id;   // 已删本的封面兜底也走本地代理（服务端拉取+缓存）
      return '<div class="comic-card" data-rid="' + id + '">' +
        '<img class="comic-card__cover" src="' + cover + '" loading="lazy" alt="" ' +
          'onerror="this.onerror=null;' + (online ? 'this.src=\'' + online + '\';' : 'this.classList.add(\'is-broken\');') + '">' +
        '<div class="comic-card__body">' +
          '<div class="comic-card__title">' + esc(it.title || ('JM-' + id)) + '</div>' +
          '<div class="comic-card__meta">' + esc(it.author || '未知作者') + '</div>' +
          '<div class="recycle-meta">' + chip + '</div>' +
          '<div class="recycle-actions">' +
            '<button class="btn btn--sm" data-ract="restore" data-id="' + id + '">恢复</button>' +
            (it.local ? '' : '<button class="btn btn--sm btn--primary" data-ract="redl" data-id="' + id + '">重新下载</button>') +
            '<button class="btn btn--sm btn--danger" data-ract="purge" data-id="' + id + '">彻底删除</button>' +
          '</div>' +
        '</div>' +
      '</div>';
    }

    async function loadRecycle() {
      try {
        var r = await api('/api/recycle');
        var items = r.data || [];
        if (recycleBadge) { recycleBadge.hidden = items.length === 0; recycleBadge.textContent = items.length; }
        if (!recycleView || recycleView.hidden) return items;
        $('recycleCount').textContent = items.length ? (items.length + ' 项') : '';
        $('recycleEmpty').hidden = items.length > 0;
        recycleGrid.innerHTML = items.map(recycleCardHtml).join('');
        return items;
      } catch (e) { return []; }
    }

    function showRecycle(on) {
      shelfView.hidden = on;
      recycleView.hidden = !on;
      if (on) loadRecycle();
    }

    if ($('recycleBtn')) $('recycleBtn').addEventListener('click', function () { showRecycle(true); });
    if ($('recycleBackBtn')) $('recycleBackBtn').addEventListener('click', function () { showRecycle(false); refresh(); });

    if (recycleGrid) recycleGrid.addEventListener('click', async function (e) {
      var btn = e.target.closest('[data-ract]');
      if (!btn) return;
      var id = parseInt(btn.dataset.id, 10);
      var act = btn.dataset.ract;
      if (act === 'restore') {
        var r = await api('/api/recycle/' + id + '/restore', { method: 'POST' });
        toast(r.success ? '已恢复（本地已删，可重新下载）' : '恢复失败');
        loadRecycle();
      } else if (act === 'redl') {
        var r2 = await api('/api/download/' + id, { method: 'POST' });
        if (r2.success) { toast('已开始重新下载'); loadRecycle(); }
        else toast(r2.message || '下载失败');
      } else if (act === 'purge') {
        if (!confirm('彻底删除？将清除账本、标记与残留文件，不可恢复。')) return;
        var r3 = await api('/api/recycle/' + id, { method: 'DELETE' });
        toast(r3.success ? '已彻底删除' : '删除失败');
        loadRecycle();
      }
    });

    /* ── 数据加载 ───────────────────────────────────── */
    async function refresh() {
      try {
        var results = await Promise.all([
          api('/api/downloaded'),
          api('/api/categories?tree=1'),
          api('/api/settings'),
        ]);
        allComics = (results[0].data) || [];
        treeData = (results[1].data) || [];
        // 同步书架配置（排序/列数/读完处理——设置页改完回来即生效）
        var cfgd = results[2].data || {};
        shelfCfg.sort = cfgd.shelf_sort || 'download_desc';
        shelfCfg.columns = parseInt(cfgd.library_columns || '0', 10) || 0;
        shelfCfg.finished = cfgd.library_finished || 'divider';
        if (sortSel && sortSel.value !== shelfCfg.sort) sortSel.value = shelfCfg.sort;
        if (view.type === 'cat' && view.id && !findNode(treeData, view.id)) {
          view = { type: 'all', id: null };
        }
        renderTree();
        renderGrid();
        loadRecycle();  // 顺带刷新回收站徽标
      } catch (e) {
        toast('书架加载失败：' + e.message);
      }
    }

    /* ── 排序切换（写设置 shelf_sort 并即时刷新）───────── */
    if (sortSel) {
      sortSel.addEventListener('change', async function () {
        shelfCfg.sort = sortSel.value;
        try {
          await api('/api/settings', { method: 'POST', body: { shelf_sort: sortSel.value } });
          await refresh();
        } catch (e) { toast('排序保存失败：' + e.message); }
      });
    }

    /* ── 事件绑定 ───────────────────────────────────── */
    if ($('selectBtn')) $('selectBtn').addEventListener('click', enterSelection);
    if ($('selExitBtn')) $('selExitBtn').addEventListener('click', exitSelection);
    if ($('selDeleteBtn')) $('selDeleteBtn').addEventListener('click', deleteSelected);
    if (selToolbar) selToolbar.addEventListener('click', function (e) {
      var btn = e.target.closest('[data-sel]');
      if (btn) selectBy(btn.dataset.sel);
    });

    grid.addEventListener('click', async function (e) {
      var dlBtn = e.target.closest('[data-dl]');
      if (dlBtn) { e.preventDefault(); e.stopPropagation(); startDownload(dlBtn.dataset.dl, dlBtn.dataset.title); return; }
      var card = e.target.closest('.comic-card');
      if (!card) return;
      var jmId = parseInt(card.dataset.jmId, 10);
      if (selection.on) { toggleSelect(jmId); return; }
      var actBtn = e.target.closest('[data-act]');
      if (actBtn) {
        e.stopPropagation();
        if (actBtn.dataset.act === 'fav') {
          var on = actBtn.dataset.on !== '1';
          api('/api/status/' + jmId + '/favorite', { method: 'POST', body: { favorite: on } })
            .then(function (r) {
              if (!r.success) { toast(r.message || '操作失败'); return; }
              // 原地更新，不整格重渲染（避免全部封面重载闪烁）
              var comic = allComics.find(function (c) { return c.id === jmId; });
              if (comic) comic.favorite = on;
              actBtn.classList.toggle('on', on);
              actBtn.dataset.on = on ? '1' : '0';
              var card = actBtn.closest('.comic-card');
              if (card) {
                var badge = card.querySelector('.status-badge--fav');
                if (on && !badge) {
                  var b = document.createElement('span');
                  b.className = 'status-badge status-badge--fav';
                  b.textContent = '★';
                  card.insertBefore(b, card.firstChild);
                } else if (!on && badge) badge.remove();
              }
              // 收藏视图取消收藏 → 移出该卡片；其余视图只重画左侧树（无封面，不闪）
              if (view.type === 'fav' && !on && card) card.remove();
              renderTree();
            });
        } else if (actBtn.dataset.act === 'del') {
          e.preventDefault();
          var ok = await confirmModal({
            title: '删除这本漫画？',
            html: '「' + esc((allComics.find(function (c) { return c.id === jmId; }) || {}).title || ('JM' + jmId)) + '」的本地文件将移入回收站，<b>7 天内</b>可恢复或重新下载。',
            okText: '删除'
          });
          if (!ok) return;
          api('/api/delete/' + jmId, { method: 'DELETE' })
            .then(function (r) {
              if (r.success) { toast('已移入回收站'); refresh(); }
              else toast(r.message || '删除失败');
            });
        }
        return;
      }
      if (jmId) location.href = '/reader/' + jmId;
    });

    grid.addEventListener('dragstart', function (e) {
      var card = e.target.closest('.comic-card');
      if (!card) return;
      dragCatId = null;   // 本次拖的是漫画，不是分类
      e.dataTransfer.setData('text/plain', card.dataset.jmId);
      e.dataTransfer.effectAllowed = 'move';
    });

    treeEl.addEventListener('click', async function (e) {
      var renameBtn = e.target.closest('[data-rename]');
      if (renameBtn) {
        var rid = parseInt(renameBtn.dataset.rename, 10);
        var node = findNode(treeData, rid);
        var name = prompt('重命名分类', node ? node.name : '');
        if (name && name.trim()) {
          var r = await api('/api/categories/' + rid, { method: 'PUT', body: { name: name.trim() } });
          if (r.success) { toast('已重命名'); refresh(); } else toast(r.message || '重命名失败');
        }
        return;
      }
      var delBtn = e.target.closest('[data-delcat]');
      if (delBtn) {
        deleteCategoryFlow(parseInt(delBtn.dataset.delcat, 10));
        return;
      }
      var row = e.target.closest('.tree-row');
      if (!row) return;
      if (row.dataset.virt) {
        view = { type: row.dataset.virt, id: null };
      } else if (row.dataset.cat) {
        view = { type: 'cat', id: parseInt(row.dataset.cat, 10) };
      }
      renderTree();
      renderGrid();
    });

    // ── 分类拖拽：① 漫画卡片拖到分类行 = 归类；② 分类行拖到另一分类行 = 调层级 ──
    // 两者共用 text/plain：漫画=纯数字，分类='cat:<id>'（parseInt 兼容旧漫画逻辑）
    var dragCatId = null;   // 正在拖动的分类 id（null = 拖的是漫画）

    function isDescendantCat(catId, targetId) {
      var node = findNode(treeData, catId);
      if (!node) return false;
      var found = false;
      walkTree([node], function (n) { if (n.id === targetId) found = true; });
      return found;
    }

    treeEl.addEventListener('dragstart', function (e) {
      var row = e.target.closest('.tree-row');
      if (!row || !row.dataset.cat) return;   // 虚拟视图不可拖
      dragCatId = parseInt(row.dataset.cat, 10);
      e.dataTransfer.setData('text/plain', 'cat:' + dragCatId);
      e.dataTransfer.effectAllowed = 'move';
    });
    treeEl.addEventListener('dragend', function () {
      dragCatId = null;
      treeEl.querySelectorAll('.tree-row.drop-over, .tree-row.drop-invalid')
        .forEach(function (x) { x.classList.remove('drop-over', 'drop-invalid'); });
    });

    treeEl.addEventListener('dragover', function (e) {
      var row = e.target.closest('.tree-row');
      if (!row) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      treeEl.querySelectorAll('.tree-row.drop-over, .tree-row.drop-invalid')
        .forEach(function (x) { x.classList.remove('drop-over', 'drop-invalid'); });
      // 分类拖拽守卫：不能落到自己或自己的子孙上（会成环）
      if (dragCatId != null) {
        var tid = row.dataset.cat ? parseInt(row.dataset.cat, 10) : 0;
        if (tid && (tid === dragCatId || isDescendantCat(dragCatId, tid))) {
          row.classList.add('drop-invalid');
          e.dataTransfer.dropEffect = 'none';
          return;
        }
      }
      row.classList.add('drop-over');
    });
    treeEl.addEventListener('dragleave', function (e) {
      var row = e.target.closest('.tree-row');
      if (row) row.classList.remove('drop-over', 'drop-invalid');
    });
    async function handleDrop(row, raw) {
      row.classList.remove('drop-over', 'drop-invalid');
      raw = raw || '';

      // ── 分类 → 分类/顶层：调整层级 ──
      if (raw.indexOf('cat:') === 0 || dragCatId != null) {
        var cid = dragCatId != null ? dragCatId : parseInt(raw.slice(4), 10);
        dragCatId = null;
        if (!cid) return;
        var pid = row.dataset.cat ? parseInt(row.dataset.cat, 10) : 0;   // 虚拟行/顶层 = 0
        if (pid && (pid === cid || isDescendantCat(cid, pid))) { toast('不能移到自己的子分类里'); return; }
        var node = findNode(treeData, cid);
        if (node && ((node.parent_id || 0) === (pid || 0))) return;      // 层级没变
        var targetName = pid ? ((findNode(treeData, pid) || {}).name || ('#' + pid)) : '顶层';
        var r = await api('/api/categories/' + cid, { method: 'PUT', body: { parent_id: pid } });
        if (r.success) { toast('已移动到「' + targetName + '」'); refresh(); }
        else toast(r.message || '移动失败');
        return;
      }

      // ── 漫画 → 分类：归类 ──
      var jmId = parseInt(raw, 10);
      if (!jmId) return;
      var cidList = row.dataset.virt ? [] : [parseInt(row.dataset.cat, 10)];
      try {
        var r2 = await api('/api/comic/' + jmId + '/categories', { method: 'PUT', body: { category_ids: cidList } });
        if (r2.success) {
          toast(cidList.length ? '已归类' : '已移入未归类');
          refresh();
        } else toast(r2.message || '归类失败');
      } catch (err) { toast('归类失败：' + err.message); }
    }
    treeEl.addEventListener('drop', function (e) {
      var row = e.target.closest('.tree-row');
      if (!row) return;
      e.preventDefault();
      handleDrop(row, e.dataTransfer ? e.dataTransfer.getData('text/plain') : '');
    });

    // ── WebView2 拖拽补丁 v2：WebView2 的 HTML5 DnD 半残——dragstart 会触发但
    //    拖不动，还会留一个僵死的拖拽残影（用户实测）。对策：
    //    ① 原生 DnD 一律 preventDefault 禁用（残影不再出现，真浏览器也不与模拟双路打架）；
    //    ② mousedown/mousemove/mouseup 全程模拟拖拽，决策逻辑走 LibraryDrag 纯模块；
    //    ③ 落点统一走 handleDrop。
    var mdrag = null;          // {src, x, y, started, payload, ghost}
    var mdragConsumed = false; // 拖拽结束后抑制紧随而来的 click（避免误开阅读页/误选中）

    function mdragCleanup(st) {
      if (st.ghost) st.ghost.remove();
      st.src.style.opacity = '';
      treeEl.querySelectorAll('.tree-row.drop-over, .tree-row.drop-invalid')
        .forEach(function (x) { x.classList.remove('drop-over', 'drop-invalid'); });
    }

    function mdragBegin(e) {
      if (e.button !== 0) return;
      var src = e.target.closest('[draggable="true"]');
      if (!src) return;
      mdrag = { src: src, x: e.clientX, y: e.clientY, started: false, payload: null, ghost: null };
    }

    function mdragMove(e) {
      if (!mdrag) return;
      if (!mdrag.started) {
        if (!LibraryDrag.shouldBegin(e.clientX - mdrag.x, e.clientY - mdrag.y)) return;
        // 起拖：识别载荷（漫画卡片 or 分类行）
        var pl = LibraryDrag.resolvePayload({
          isCard: mdrag.src.classList.contains('comic-card'),
          jmId: mdrag.src.dataset.jmId,
          catId: mdrag.src.dataset.cat
        });
        if (!pl) { mdrag = null; return; }
        mdrag.payload = pl.payload;
        dragCatId = pl.dragCatId;
        mdrag.started = true;
        mdragConsumed = true;
        var g = mdrag.src.cloneNode(true);
        g.style.cssText = 'position:fixed;left:0;top:0;margin:0;pointer-events:none;z-index:9999;' +
          'opacity:.85;width:' + mdrag.src.offsetWidth + 'px;box-shadow:0 6px 20px rgba(0,0,0,.25);';
        document.body.appendChild(g);
        mdrag.ghost = g;
        mdrag.src.style.opacity = '.4';
      }
      e.preventDefault();
      mdrag.ghost.style.left = (e.clientX + 12) + 'px';
      mdrag.ghost.style.top = (e.clientY + 8) + 'px';
      // 高亮悬停的目标行
      var hit = document.elementFromPoint(e.clientX, e.clientY);
      var row = hit && hit.closest ? hit.closest('.tree-row') : null;
      treeEl.querySelectorAll('.tree-row.drop-over, .tree-row.drop-invalid')
        .forEach(function (x) { x.classList.remove('drop-over', 'drop-invalid'); });
      if (row) {
        var tid = row.dataset.cat ? parseInt(row.dataset.cat, 10) : 0;
        if (LibraryDrag.targetState(dragCatId, tid, isDescendantCat) === 'invalid') {
          row.classList.add('drop-invalid');
        } else {
          row.classList.add('drop-over');
        }
      }
    }

    async function mdragEnd(e) {
      if (!mdrag) return;
      var st = mdrag;
      mdrag = null;
      mdragCleanup(st);
      if (!LibraryDrag.shouldDrop(st.started)) return;   // 没超过阈值 = 普通点击，放行
      e.preventDefault();
      var hit = document.elementFromPoint(e.clientX, e.clientY);
      var row = hit && hit.closest ? hit.closest('.tree-row') : null;
      if (!row) { dragCatId = null; return; }
      await handleDrop(row, st.payload);
    }

    grid.addEventListener('mousedown', mdragBegin);
    treeEl.addEventListener('mousedown', mdragBegin);
    document.addEventListener('mousemove', mdragMove);
    document.addEventListener('mouseup', mdragEnd);
    // 原生 HTML5 DnD 全禁：WebView2 半残会留僵死残影，真浏览器里与鼠标模拟双路打架
    grid.addEventListener('dragstart', function (e) { e.preventDefault(); }, true);
    treeEl.addEventListener('dragstart', function (e) { e.preventDefault(); }, true);
    // 拖拽中途焦点丢失（切窗/拖出窗口）也要清场
    window.addEventListener('blur', function () {
      if (mdrag) { mdragCleanup(mdrag); mdrag = null; dragCatId = null; }
    });
    // 拖完吃掉 click：书架卡片点击会跳阅读器，这里拦一次
    grid.addEventListener('click', function (e) {
      if (mdragConsumed) { e.stopPropagation(); mdragConsumed = false; }
    }, true);
    treeEl.addEventListener('click', function (e) {
      if (mdragConsumed) { e.stopPropagation(); mdragConsumed = false; }
    }, true);

    var newBtn = $('newCatBtn');
    if (newBtn) newBtn.addEventListener('click', async function () {
      var name = prompt('新分类名称');
      if (!name || !name.trim()) return;
      var r = await api('/api/categories', { method: 'POST', body: { name: name.trim() } });
      if (r.success) { toast('已创建'); refresh(); } else toast(r.message || '创建失败');
    });

    async function deleteCategoryFlow(catId) {
      var node = findNode(treeData, catId);
      var name = node ? node.name : ('#' + catId);
      try {
        var r = await api('/api/categories/' + catId + '?count_only=1');
        var cnt = (r.data && r.data.count) || 0;
        if (!cnt) {
          var okDel = await confirmModal({
            title: '删除分类「' + name + '」？',
            text: '仅删除分类，不会删除分类下的漫画。',
            okText: '删除',
            icon: 'warn'
          });
          if (!okDel) return;
          var r2 = await api('/api/categories/' + catId, { method: 'DELETE', body: {} });
          if (r2.success) { toast('已删除分类'); refresh(); } else toast(r2.message || '删除失败');
          return;
        }
        var opts = '<option value="">未归类</option>';
        walkTree(treeData, function (n) {
          if (n.id !== catId) opts += '<option value="' + n.id + '">' + esc(n.name) + '</option>';
        });
        var overlay = document.createElement('div');
        overlay.className = 'modal-overlay';
        overlay.innerHTML = '<div class="modal" style="max-width:420px">' +
          '<h3 style="margin:0 0 8px">删除分类「' + esc(name) + '」</h3>' +
          '<p class="muted" style="margin:0 0 12px">该分类下有 ' + cnt + ' 部漫画，请选择它们的去向：</p>' +
          '<select id="reassignSel" class="filter-select" style="width:100%">' + opts + '</select>' +
          '<div class="detail__actions"><span class="spacer"></span>' +
            '<button class="btn" data-cancel>取消</button>' +
            '<button class="btn btn--primary" data-ok>确认删除</button></div>' +
        '</div>';
        document.body.appendChild(overlay);
        overlay.addEventListener('click', function (ev) {
          if (ev.target === overlay || ev.target.hasAttribute('data-cancel')) { overlay.remove(); return; }
          if (ev.target.hasAttribute('data-ok')) {
            var sel = overlay.querySelector('#reassignSel').value;
            var payload = { reassign_to: sel === '' ? null : parseInt(sel, 10) };
            api('/api/categories/' + catId, { method: 'DELETE', body: payload }).then(function (r3) {
              overlay.remove();
              if (r3.success) { toast('已删除分类'); refresh(); } else toast(r3.message || '删除失败');
            });
          }
        });
      } catch (e) {
        toast('删除失败：' + e.message);
      }
    }

    refresh().then(restoreScroll);
  }

  /* ═══════════════════════════════════════════════════════
     设置：六入口 + 二级面板（外观/书架/搜索/阅读/下载/关于）
     ═══════════════════════════════════════════════════════ */
  function initSettingsPage() {
    var home = $('setHome');
    if (!home) return;

    var cfg = {};
    var GROUPS = ['appearance', 'library', 'search', 'reader', 'download', 'about'];
    var BL_TYPE_NAMES = { author: '作者', work: '作品', tag: '标签' };
    var THEME_NAMES = { system: '跟随系统', light: '浅色', dark: '深色' };
    var SORT_NAMES = { mr: '最新', mv: '浏览量', mp: '收藏量' };
    var HIDE_NAMES = { hide: '隐藏', gray: '灰显', off: '不处理' };
    var WHEEL_NAMES = { scroll: '上下连排', page: '滑动翻页', zoom: '以光标缩放' };
    var QUALITY_NAMES = { original: '原画', high: '高', medium: '中', low: '低' };

    /* ── hash 路由（一级 / 二级） ─────────────────────── */
    function showGroup(name) {
      home.hidden = true;
      GROUPS.forEach(function (g) {
        var el = $('set-' + g);
        if (el) el.hidden = (g !== name);
      });
    }
    function showHome() {
      GROUPS.forEach(function (g) {
        var el = $('set-' + g);
        if (el) el.hidden = true;
      });
      home.hidden = false;
    }
    function routeFromHash() {
      var h = (location.hash || '').replace('#', '');
      if (h && GROUPS.indexOf(h) >= 0) showGroup(h);
      else showHome();
    }
    home.addEventListener('click', function (e) {
      var card = e.target.closest('[data-group]');
      if (!card) return;
      location.hash = card.dataset.group;
    });
    document.querySelectorAll('[data-back]').forEach(function (b) {
      b.addEventListener('click', function () { location.hash = ''; });
    });
    window.addEventListener('hashchange', routeFromHash);

    /* ── 分段 / 芯片控件 ─────────────────────────────── */
    function markChoice(containerId, value) {
      var box = $(containerId);
      if (!box) return;
      box.querySelectorAll('[data-v]').forEach(function (b) {
        b.classList.toggle('is-active', b.dataset.v === String(value));
      });
    }
    function initChoice(containerId, onChange) {
      var box = $(containerId);
      if (!box) return;
      box.addEventListener('click', function (e) {
        var b = e.target.closest('[data-v]');
        if (!b) return;
        markChoice(containerId, b.dataset.v);
        onChange(b.dataset.v);
      });
    }
    async function saveCfg(key, value) {
      var body = {};
      body[key] = String(value);
      var r = await api('/api/settings', { method: 'POST', body: body });
      if (r.success) cfg = r.data || cfg;
      return r.success;
    }

    /* ── 摘要 ─────────────────────────────────────────── */
    function renderSummaries() {
      var t = $('sum-appearance');
      if (t) t.textContent = '主题：' + (THEME_NAMES[cfg.theme] || '跟随系统');
      var l = $('sum-library');
      if (l) l.textContent = '云同步 ' + (cfg.sync_enabled === '1' ? '已开启' : '未开启') + ' · 订阅巡检';
      var s = $('sum-search');
      if (s) s.textContent = '排序：' + (SORT_NAMES[cfg.default_sort] || '最新') + ' · 黑名单';
      var rd = $('sum-reader');
      if (rd) rd.textContent = '滚轮：' + (WHEEL_NAMES[cfg.reader_wheel_mode] || '滑动翻页');
      var dl = $('sum-download');
      if (dl) dl.textContent = '并发 ' + (cfg.max_concurrent_downloads || '3') +
        ' · 画质 ' + (QUALITY_NAMES[cfg.image_quality] || '原画');
    }

    /* ── 外观 ─────────────────────────────────────────── */
    function applyThemePref(pref) {
      try {
        if (pref === 'light' || pref === 'dark') {
          document.documentElement.setAttribute('data-theme', pref);
          localStorage.setItem('jm_lite_theme', pref);
        } else {
          document.documentElement.removeAttribute('data-theme');
          localStorage.removeItem('jm_lite_theme');
        }
      } catch (e) { /* 忽略 */ }
    }
    initChoice('setThemeSeg', function (v) {
      applyThemePref(v);
      saveCfg('theme', v).then(renderSummaries);
    });

    /* ── 云同步 ───────────────────────────────────────── */
    function renderSync(st) {
      var d = st || {};
      if ($('syncUrlTxt')) $('syncUrlTxt').textContent = d.server_url || '未配置';
      if ($('syncTokenTxt')) $('syncTokenTxt').textContent = d.token_masked || '未配置';
      if ($('syncEnabled')) $('syncEnabled').checked = !!d.enabled;
      var dot = $('syncDot');
      var txt = $('syncStateTxt');
      if (dot && txt) {
        if (d.enabled && d.configured) {
          dot.className = 'sync-dot ok';
          txt.textContent = d.last_at ? ('已开启 · 上次同步 ' + fmtTime(d.last_at)) : '已开启 · 尚未同步';
        } else if (d.enabled) {
          dot.className = 'sync-dot err';
          txt.textContent = '已开启但未配置完整';
        } else {
          dot.className = 'sync-dot';
          txt.textContent = '未开启';
        }
      }
      if ($('syncLastTxt')) {
        $('syncLastTxt').textContent = d.last_at ? ('上次：' + fmtTime(d.last_at)) : '尚未同步';
      }
      var res = $('syncResult');
      if (res) {
        if (d.last_result) { res.hidden = false; res.textContent = d.last_result; }
        else res.hidden = true;
      }
      var l = $('sum-library');
      if (l) l.textContent = '云同步 ' + (d.enabled ? '已开启' : '未开启') + ' · 订阅巡检';
    }
    async function refreshSync() {
      try {
        var r = await api('/api/sync/status');
        if (r.success) renderSync(r.data);
      } catch (e) { /* 静默 */ }
    }

    if ($('syncEnabled')) $('syncEnabled').addEventListener('change', async function () {
      var ok = await saveCfg('sync_enabled', this.checked ? '1' : '0');
      toast(ok ? (this.checked ? '云同步已开启' : '云同步已关闭') : '保存失败');
      refreshSync();
    });
    if ($('syncEditUrl')) $('syncEditUrl').addEventListener('click', async function () {
      var v = prompt('同步服务器地址', cfg.sync_server_url || '');
      if (v === null) return;
      v = v.trim();
      if (!v) return;
      await saveCfg('sync_server_url', v);
      refreshSync();
    });
    if ($('syncEditToken')) $('syncEditToken').addEventListener('click', async function () {
      var v = prompt('同步密钥', '');
      if (v === null || !v.trim()) return;
      await saveCfg('sync_token', v.trim());
      refreshSync();
    });
    if ($('syncNowBtn')) $('syncNowBtn').addEventListener('click', async function () {
      var btn = this;
      btn.disabled = true;
      btn.textContent = '同步中…';
      try {
        var r = await api('/api/sync/now', { method: 'POST' });
        if (r.success) {
          toast('同步完成：拉回 ' + r.pulled + ' · 推上 ' + r.pushed);
        } else {
          toast(r.message || '同步失败');
        }
        if (r.status) renderSync(r.status);
      } catch (e) {
        toast('同步异常：' + e.message);
      } finally {
        btn.disabled = false;
        btn.textContent = '立即同步';
      }
    });

    /* ── 搜索 / 阅读 / 下载 ──────────────────────────── */
    initChoice('setSortSeg', function (v) { saveCfg('default_sort', v).then(renderSummaries); });
    initChoice('setHideDlSeg', function (v) { saveCfg('hide_downloaded_in_search', v); });
    initChoice('setHideFinSeg', function (v) { saveCfg('hide_finished_in_search', v); });
    initChoice('setWheelSeg', function (v) { saveCfg('reader_wheel_mode', v).then(renderSummaries); });
    initChoice('setPpsSeg', function (v) { saveCfg('reader_pages_per_screen', v).then(renderSummaries); });
    // 书架显示（每行列数 / 已读完处理——与手机端 finished_in_library 对齐）
    initChoice('setLibColsSeg', function (v) { saveCfg('library_columns', v); });
    initChoice('setLibFinSeg', function (v) { saveCfg('library_finished', v); });
    initChoice('setSearchColsSeg', function (v) { saveCfg('search_columns', v); });

    /* ── 收藏备份（导出写文件 / 导入读 JSON，兼容手机端格式）── */
    var favExportBtn = $('favExportBtn');
    if (favExportBtn) {
      favExportBtn.addEventListener('click', async function () {
        favExportBtn.disabled = true;
        try {
          var r = await api('/api/favorites/export', { method: 'POST' });
          if (r.success) {
            var info = $('favBackupInfo');
            if (info) info.textContent = '已导出 ' + r.data.count + ' 本收藏 → ' + r.data.path;
            toast('已导出 ' + r.data.count + ' 本收藏（文件在 UserData/exports 里）');
          } else {
            toast(r.message || '导出失败');
          }
        } catch (e) { toast('导出失败：' + e.message); }
        favExportBtn.disabled = false;
      });
    }
    var favImportBtn = $('favImportBtn');
    var favImportFile = $('favImportFile');
    if (favImportBtn && favImportFile) {
      favImportBtn.addEventListener('click', function () { favImportFile.click(); });
      favImportFile.addEventListener('change', function () {
        var f = favImportFile.files && favImportFile.files[0];
        if (!f) return;
        var reader = new FileReader();
        reader.onload = async function () {
          try {
            var data = JSON.parse(reader.result);
            var r = await api('/api/favorites/import', { method: 'POST', body: data });
            if (r.success) {
              toast('导入完成：新增 ' + r.data.added + ' 本（备份共 ' + r.data.total + ' 本）');
            } else {
              toast(r.message || '导入失败');
            }
          } catch (e) { toast('文件解析失败：' + e.message); }
          favImportFile.value = '';
        };
        reader.readAsText(f);
      });
    }

    // 进度滑轨颜色：预设色板 + 自定义取色器
    function markSwatch(color) {
      var box = $('setRailColor');
      if (!box) return;
      box.querySelectorAll('.swatch').forEach(function (b) {
        b.classList.toggle('is-active', (b.dataset.c || '').toLowerCase() === String(color).toLowerCase());
      });
      var custom = $('setRailColorCustom');
      if (custom && /^#[0-9a-fA-F]{6}$/.test(color)) custom.value = color;
    }
    (function initRailColor() {
      var box = $('setRailColor');
      if (!box) return;
      var custom = $('setRailColorCustom');
      box.addEventListener('click', function (e) {
        var b = e.target.closest('.swatch');
        if (!b) return;
        markSwatch(b.dataset.c);
        saveCfg('reader_progress_color', b.dataset.c);
      });
      if (custom) {
        custom.addEventListener('input', function () {
          markSwatch(custom.value);
          saveCfg('reader_progress_color', custom.value);
        });
      }
    })();
    initChoice('setQualitySeg', function (v) { saveCfg('image_quality', v).then(renderSummaries); });
    initChoice('setConcurrencyChips', function (v) { saveCfg('max_concurrent_downloads', v).then(renderSummaries); });
    if ($('setChapToast')) $('setChapToast').addEventListener('change', function () {
      saveCfg('reader_chapter_toast', this.checked ? '1' : '0');
    });

    /* ── 黑名单 ───────────────────────────────────────── */
    async function refreshBlocks() {
      try {
        var r = await api('/api/blocklist');
        var list = r.data || [];
        $('blEmpty').hidden = list.length > 0;
        $('blList').innerHTML = list.map(function (b) {
          return '<div class="bl-item">' +
            '<span class="bl-item__type">' + (BL_TYPE_NAMES[b.block_type] || esc(b.block_type)) + '</span>' +
            '<span class="bl-item__value">' + esc(b.value) + '</span>' +
            '<button class="dl-item__x" data-bldel="' + b.id + '" title="移出黑名单">×</button>' +
          '</div>';
        }).join('');
      } catch (e) { /* 静默 */ }
    }
    if ($('blAddBtn')) $('blAddBtn').addEventListener('click', async function () {
      var value = ($('blValue').value || '').trim();
      var type = $('blType').value;
      if (!value) { toast('请输入要屏蔽的内容'); return; }
      var r = await api('/api/blocklist', { method: 'POST', body: { type: type, value: value } });
      if (r.success) { toast('已加入黑名单'); $('blValue').value = ''; refreshBlocks(); }
      else toast(r.message || '添加失败');
    });
    if ($('blList')) $('blList').addEventListener('click', async function (e) {
      var del = e.target.closest('[data-bldel]');
      if (!del) return;
      await api('/api/blocklist/' + del.dataset.bldel, { method: 'DELETE' });
      toast('已移出黑名单');
      refreshBlocks();
    });

    /* ── 订阅巡检 ─────────────────────────────────────── */
    async function refreshSubs() {
      try {
        var results = await Promise.all([api('/api/subscriptions'), api('/api/sub_updates')]);
        var subs = results[0].data || [];
        var updates = results[1].data || [];

        $('subEmpty').hidden = subs.length > 0;
        $('subList').innerHTML = subs.map(function (s) {
          var badge = s.new_count ? '<span class="dl-status dl-status--ok">' + s.new_count + ' 新</span>' : '';
          var last = s.last_title ? ('最近：' + esc(s.last_title)) : '';
          return '<div class="sub-item">' +
            '<span class="sub-item__author">' + esc(s.author) + '</span>' + badge +
            '<span class="muted sub-item__last">' + last + '</span>' +
            '<button class="dl-item__x" data-subdel="' + s.id + '" title="取消订阅">×</button>' +
          '</div>';
        }).join('');

        $('subUpdatesEmpty').hidden = updates.length > 0;
        $('subUpdatesList').innerHTML = updates.map(function (u) {
          return '<div class="sub-item' + (u.seen ? ' sub-item--seen' : '') + '">' +
            '<span class="sub-item__author">' + esc(u.title || ('作品 ' + u.book_id)) + '</span>' +
            '<span class="muted">' + esc(u.author) + '</span>' +
            '<button class="btn btn--sm" data-goto="' + u.book_id + '">详情</button>' +
          '</div>';
        }).join('');
      } catch (e) { /* 静默 */ }
    }
    if ($('subList')) $('subList').addEventListener('click', async function (e) {
      var del = e.target.closest('[data-subdel]');
      if (!del) return;
      if (!confirm('取消订阅该作者？')) return;
      await api('/api/subscriptions/' + del.dataset.subdel, { method: 'DELETE' });
      toast('已取消订阅');
      refreshSubs();
    });
    if ($('subUpdatesList')) $('subUpdatesList').addEventListener('click', function (e) {
      var go = e.target.closest('[data-goto]');
      if (go) openDetail(go.dataset.goto);
    });
    if ($('subAddBtn')) $('subAddBtn').addEventListener('click', async function () {
      var input = $('subAuthorInput');
      var author = (input.value || '').trim();
      if (!author) { toast('请输入作者名'); return; }
      var r = await api('/api/subscriptions', { method: 'POST', body: { author: author } });
      if (r.success) { toast(r.exists ? '已在订阅中' : '已订阅'); input.value = ''; refreshSubs(); }
      else toast(r.message || '订阅失败');
    });
    if ($('subAuthorInput')) $('subAuthorInput').addEventListener('keydown', function (e) {
      if (e.key === 'Enter') $('subAddBtn').click();
    });
    if ($('subPollBtn')) $('subPollBtn').addEventListener('click', async function () {
      toast('正在巡检…');
      try {
        var r = await api('/api/subscriptions/poll', { method: 'POST' });
        if (r.success) {
          toast('巡检完成：检查 ' + (r.checked || 0) + ' 位作者，新增 ' + (r.added_new || 0) + ' 条新作');
          refreshSubs();
        } else toast(r.message || '巡检失败');
      } catch (e) { toast('巡检异常：' + e.message); }
    });
    if ($('subAllSeenBtn')) $('subAllSeenBtn').addEventListener('click', async function () {
      await api('/api/sub_updates/seen', { method: 'POST', body: { all: true } });
      toast('已全部标记已读');
      refreshSubs();
    });
    if ($('subClearUpdatesBtn')) $('subClearUpdatesBtn').addEventListener('click', async function () {
      if (!confirm('清空全部新作记录？')) return;
      await api('/api/sub_updates', { method: 'DELETE' });
      toast('已清空新作');
      refreshSubs();
    });

    /* ── 关于 ─────────────────────────────────────────── */
    api('/api/about').then(function (r) {
      if (!r.success || !r.data) return;
      var d = r.data;
      if ($('aboutDataDir')) $('aboutDataDir').textContent = d.base_dir || '-';
      var list = $('aboutStorageList');
      if (list && Array.isArray(d.storage_items)) {
        var total = d.total_size || 0;
        if ($('aboutStorageTotal')) {
          $('aboutStorageTotal').textContent = '总计 ' + fmtBytes(total) +
            '（程序本体 ' + fmtBytes(d.app_size || 0) + ' + 用户数据 ' + fmtBytes(d.user_size || 0) + '）';
        }
        list.innerHTML = d.storage_items.map(function (it) {
          var pct = total > 0 ? Math.max(1, Math.round(it.size / total * 100)) : 0;
          return '<div class="storage-row">' +
            '<div class="storage-row__head">' +
              '<span class="storage-row__name">' + esc(it.label) + '</span>' +
              '<span class="storage-row__size">' + fmtBytes(it.size) + ' · ' + pct + '%</span>' +
            '</div>' +
            '<div class="storage-row__bar"><i style="width:' + pct + '%"></i></div>' +
            '<div class="storage-row__path">' + esc(it.rel) + '</div>' +
          '</div>';
        }).join('');
      }
    }).catch(function () {});

    /* ── 初始化 ───────────────────────────────────────── */
    async function loadCfg() {
      try {
        var r = await api('/api/settings');
        cfg = r.data || {};
        markChoice('setThemeSeg', cfg.theme || 'system');
        markChoice('setSortSeg', cfg.default_sort || 'mr');
        markChoice('setHideDlSeg', cfg.hide_downloaded_in_search || 'hide');
        markChoice('setHideFinSeg', cfg.hide_finished_in_search || 'hide');
        markChoice('setWheelSeg', cfg.reader_wheel_mode || 'scroll');
        markChoice('setPpsSeg', cfg.reader_pages_per_screen || '1');
        markChoice('setLibColsSeg', cfg.library_columns || '0');
        markChoice('setLibFinSeg', cfg.library_finished || 'divider');
        markChoice('setSearchColsSeg', cfg.search_columns || '0');
        markSwatch(cfg.reader_progress_color || '#7B6FE0');
        markChoice('setQualitySeg', cfg.image_quality || 'original');
        markChoice('setConcurrencyChips', cfg.max_concurrent_downloads || '3');
        if ($('setChapToast')) $('setChapToast').checked = cfg.reader_chapter_toast !== '0';
        renderSummaries();
      } catch (e) { /* 静默 */ }
    }

    loadCfg();
    refreshSync();
    refreshBlocks();
    refreshSubs();
    routeFromHash();
    restoreScroll();
  }

  /* ── 初始化 ───────────────────────────────────────────── */
  document.addEventListener('DOMContentLoaded', async function () {
    var themeBtn = $('themeToggle');
    if (themeBtn) themeBtn.addEventListener('click', toggleTheme);
    try {
      var r = await api('/api/ping');
      App.version = r.version;
    } catch (e) { /* 忽略 */ }
    initDlBadge();
    initSearchPage();
    initDownloadsPage();
    initReaderPage();
    initLibraryPage();
    initSettingsPage();
    initSubscriptionsPage();
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
})();