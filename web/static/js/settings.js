/* ============================================================
   JM 轻量版 · 前端 settings —— 设置（六入口二级面板）+ 订阅页
   ============================================================ */
window.JM = window.JM || {};
(function (JM) {
  'use strict';

  var $ = JM.$,
      api = JM.api,
      esc = JM.esc,
      toast = JM.toast,
      fmtBytes = JM.fmtBytes,
      fmtTime = JM.fmtTime,
      pjaxNav = JM.pjaxNav,
      openDetail = JM.openDetail,
      cardHtml = JM.cardHtml,
      restoreScroll = JM.restoreScroll;

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

  JM.initSubscriptionsPage = initSubscriptionsPage;
  JM.initSettingsPage = initSettingsPage;
  JM.pages.subscriptions = initSubscriptionsPage;
  JM.pages.settings = initSettingsPage;
})(window.JM);
