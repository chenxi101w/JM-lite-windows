/* ============================================================
   JM 轻量版 · 前端 downloads —— 下载页（进行中 / 历史 / 批量 / 续下）
   ============================================================ */
window.JM = window.JM || {};
(function (JM) {
  'use strict';

  var $ = JM.$,
      api = JM.api,
      esc = JM.esc,
      toast = JM.toast,
      fmtBytes = JM.fmtBytes,
      regCleanup = JM.regCleanup,
      restoreScroll = JM.restoreScroll;

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

  JM.initDownloadsPage = initDownloadsPage;
  JM.pages.downloads = initDownloadsPage;
})(window.JM);
