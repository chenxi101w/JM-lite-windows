/* ============================================================
   JM 轻量版 · 前端 reader —— 阅读器（连排 / 翻页 / 缩放 / 览图 / 滑轨）
   ============================================================ */
window.JM = window.JM || {};
(function (JM) {
  'use strict';

  var $ = JM.$,
      api = JM.api,
      esc = JM.esc,
      toast = JM.toast;

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

  JM.initReaderPage = initReaderPage;
  JM.pages.reader = initReaderPage;
})(window.JM);
