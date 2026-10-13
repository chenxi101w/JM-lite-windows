/* ============================================================
   JM 轻量版 · 前端 search —— 搜索页（关键词 / 标签 / 作者 / JM 号）
   ============================================================ */
window.JM = window.JM || {};
(function (JM) {
  'use strict';

  var $ = JM.$,
      api = JM.api,
      esc = JM.esc,
      toast = JM.toast,
      restoreScroll = JM.restoreScroll,
      openDetail = JM.openDetail,
      startDownload = JM.startDownload,
      cardHtml = JM.cardHtml;

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

  JM.searchState = searchState;
  JM.saveSearchState = saveSearchState;
  JM.loadSearchState = loadSearchState;
  JM.doSearch = doSearch;
  JM.renderCards = renderCards;
  JM.initSearchPage = initSearchPage;
  JM.pages.search = initSearchPage;
})(window.JM);
