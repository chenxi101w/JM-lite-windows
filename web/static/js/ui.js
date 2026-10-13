/* ============================================================
   JM 轻量版 · 前端 ui —— 卡片渲染 / 详情模态 / 下载触发
   ============================================================ */
window.JM = window.JM || {};
(function (JM) {
  'use strict';

  var $ = JM.$,
      api = JM.api,
      esc = JM.esc,
      toast = JM.toast,
      sleep = JM.sleep;

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

  JM.cardHtml = cardHtml;
  JM.openDetail = openDetail;
  JM.closeModal = closeModal;
  JM.showDetailModal = showDetailModal;
  JM.startDownload = startDownload;
})(window.JM);
