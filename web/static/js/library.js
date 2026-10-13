/* ============================================================
   JM 轻量版 · 前端 library —— 书架 / 分类树 / 多选 / 回收站 / 拖拽归类
   ============================================================ */
window.JM = window.JM || {};
(function (JM) {
  'use strict';

  var $ = JM.$,
      api = JM.api,
      esc = JM.esc,
      toast = JM.toast,
      confirmModal = JM.confirmModal,
      restoreScroll = JM.restoreScroll,
      startDownload = JM.startDownload;

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
      if (c.favorite) badges += '<span class="status-badge status-badge--fav">♥</span>';
      if (c.finished) badges += '<span class="status-badge status-badge--fin">已读完</span>';
      var pct = (c.pages && c.read_progress > 0) ? Math.min(100, Math.round(c.read_progress / c.pages * 100)) : 0;
      var progress = pct ? '<span class="shelf-progress">读至 ' + pct + '%</span>' : '';
      var dlBtn = '<button class="card-dl" type="button" data-dl="' + id + '"' +
        ' data-title="' + esc(c.title || '') + '" title="下载" aria-label="下载">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
        '<path d="M12 3v12"/><path d="M7 10l5 5 5-5"/><path d="M5 21h14"/></svg></button>';
      var pagesTxt = (c.pages ? ' · ' + (c.pages || 0) + ' 页' : '');
      var favSvg = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
        '<path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>';
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
                  b.textContent = '♥';
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

  JM.initLibraryPage = initLibraryPage;
  JM.pages.library = initLibraryPage;
})(window.JM);
