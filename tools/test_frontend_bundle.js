/* 前端模块化冒烟：在最小 DOM 桩上按 base.html 顺序真实加载全部脚本，
   然后触发 DOMContentLoaded 与各页 init，捕获加载期/初始化期的运行时错误。
   用法：node tools/_smoke_frontend.js
*/
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const JS = path.join(__dirname, '..', 'web', 'static', 'js');
const ORDER = ['reader-logic.js', 'library-drag-logic.js', 'core.js', 'ui.js',
               'search.js', 'downloads.js', 'reader.js', 'library.js', 'settings.js'];

let fail = 0;
const check = (cond, msg) => {
  if (cond) console.log('[OK ] ' + msg);
  else { console.log('[FAIL] ' + msg); fail++; }
};

/* ── 最小 DOM 桩 ─────────────────────────────────────────── */
function el(tag) {
  const node = {
    tagName: (tag || 'div').toUpperCase(), children: [], style: {},
    dataset: {}, hidden: false, disabled: false, value: '', textContent: '',
    innerHTML: '', className: '', files: [],
    classList: {
      _s: new Set(),
      add() { [].forEach.call(arguments, c => this._s.add(c)); },
      remove() { [].forEach.call(arguments, c => this._s.delete(c)); },
      toggle(c, on) { on === undefined ? (this._s.has(c) ? this._s.delete(c) : this._s.add(c))
                                       : (on ? this._s.add(c) : this._s.delete(c)); },
      contains(c) { return this._s.has(c); },
    },
    setAttribute() {}, getAttribute() { return null; }, removeAttribute() {},
    hasAttribute() { return false; }, addEventListener() {}, removeEventListener() {},
    appendChild(c) { this.children.push(c); return c; }, insertBefore(c) { return c; },
    removeChild() {}, remove() {}, insertAdjacentHTML() {}, focus() {}, click() {},
    querySelector() { return null; }, querySelectorAll() { return []; },
    closest() { return null; }, contains() { return false; },
    getBoundingClientRect() { return { top: 0, left: 0, width: 0, height: 0, bottom: 0, right: 0 }; },
    scrollIntoView() {}, cloneNode() { return el(tag); },
    scrollTop: 0, scrollLeft: 0, scrollHeight: 0, clientWidth: 1200, clientHeight: 800,
    offsetTop: 0, offsetHeight: 0, offsetWidth: 200, naturalWidth: 0, naturalHeight: 0,
    parentNode: null, firstChild: null, style_extra: '',
  };
  node.style.setProperty = () => {}; node.style.removeProperty = () => {};
  node.style.cssText = '';
  return node;
}

const store = () => {
  const m = {};
  return { getItem: k => (k in m ? m[k] : null), setItem: (k, v) => { m[k] = String(v); },
           removeItem: k => { delete m[k]; }, clear: () => { for (const k in m) delete m[k]; } };
};

const documentStub = {
  getElementById: () => null,           // 所有 init 自守卫 → 直接 return
  querySelector: () => null,
  querySelectorAll: () => [],
  createElement: t => el(t),
  addEventListener: () => {}, removeEventListener: () => {},
  body: el('body'), documentElement: el('html'),
  head: el('head'),
};

const win = {
  document: documentStub,
  localStorage: store(), sessionStorage: store(),
  matchMedia: () => ({ matches: false, addEventListener() {}, addListener() {} }),
  addEventListener: () => {}, removeEventListener: () => {},
  innerWidth: 1280, innerHeight: 800, location: { href: 'http://x/', pathname: '/', search: '', hash: '' },
  history: { pushState() {}, back() {}, length: 1 },
  setTimeout, clearTimeout, setInterval, clearInterval,
  requestAnimationFrame: cb => setTimeout(cb, 0),
  console, Promise, Math, Date, JSON, Object, Array, String, Number, Boolean, Set, Map,
  Error, parseInt, parseFloat, isNaN, encodeURIComponent, decodeURIComponent,
  URL, URLSearchParams: global.URLSearchParams,
  Image: function () { return el('img'); },
  DOMParser: function () { this.parseFromString = () => documentStub; },
  prompt: () => null, confirm: () => false, alert: () => {},
  getComputedStyle: () => ({ getPropertyValue: () => '' }),
};
win.window = win;

/* fetch 桩：统一返回成功信封 */
let fetchCalls = 0;
win.fetch = async (url) => {
  fetchCalls++;
  return { ok: true, status: 200, json: async () => ({ success: true, data: [] }), text: async () => '' };
};

const ctx = vm.createContext(win);
ctx.globalThis = ctx;

/* ── 按 base.html 顺序加载 ───────────────────────────────── */
for (const f of ORDER) {
  const src = fs.readFileSync(path.join(JS, f), 'utf-8');
  try {
    vm.runInContext(src, ctx, { filename: f });
    check(true, `加载 ${f}`);
  } catch (e) {
    check(false, `加载 ${f} → ${e.message}`);
  }
}

const JM = win.JM || {};
check(!!JM.pages, 'JM 命名空间存在且含 pages 注册表');
check(win.App === win.JM, 'window.App 与 window.JM 为同一对象（兼容别名）');

const need = ['search', 'downloads', 'reader', 'library', 'settings', 'subscriptions'];
for (const p of need) check(typeof JM.pages[p] === 'function', `页面模块已注册：${p}`);

/* ── 基元行为 ───────────────────────────────────────────── */
check(typeof JM.esc === 'function' && JM.esc('<a href="x">') === '&lt;a href=&quot;x&quot;&gt;',
      'JM.esc 转义正确');
check(JM.fmtBytes(2048) === '2.0 KB' && JM.fmtBytes(1024 * 1024) === '1.0 MB', 'JM.fmtBytes 正常');
check(JM.fmtTime(0) === '', 'JM.fmtTime(0) 返回空');
check(typeof JM.api === 'function' && typeof JM.toast === 'function'
      && typeof JM.confirmModal === 'function' && typeof JM.toggleTheme === 'function',
      'api/toast/confirmModal/toggleTheme 已挂载');
check(typeof JM.startDownload === 'function' && typeof JM.openDetail === 'function'
      && typeof JM.cardHtml === 'function', 'startDownload/openDetail/cardHtml 已挂载');

/* cardHtml 真实渲染 */
const html = JM.cardHtml({ id: 12345, title: '测试<书>', author: 'A', tags: ['t1', 't2'] });
check(typeof html === 'string' && html.indexOf('comic-card') >= 0 && html.indexOf('data-jm-id="12345"') >= 0,
      'cardHtml 产出卡片结构');
check(html.indexOf('&lt;书&gt;') >= 0, 'cardHtml 对标题做转义');

/* ── 触发各页初始化（DOM 全空 → 全部自守卫返回） ─────────── */
let threw = null;
try {
  JM.routeInit();
  if (JM.pages.reader) JM.pages.reader();
} catch (e) { threw = e; }
check(!threw, '空 DOM 下 routeInit + 阅读器初始化不抛错' + (threw ? ` → ${threw.message}` : ''));

/* ── 触发 DOMContentLoaded ──────────────────────────────── */
documentStub.addEventListener = (type, fn) => { if (type === 'DOMContentLoaded') documentStub._dom = fn; };
// core 已经用旧桩注册过，这里直接手动取：重新执行 core 的注册路径不可行，
// 改为直接调用等价流程（api ping + routeInit + badge + scroll）
(async () => {
  try {
    await JM.api('/api/ping');
    JM.initDlBadge();
    JM.routeInit();
    if (JM.pages.reader) JM.pages.reader();
    JM.bindScrollKeep();
    check(true, 'DOMContentLoaded 等价流程执行成功');
  } catch (e) {
    check(false, 'DOMContentLoaded 等价流程 → ' + e.message);
  }
  console.log('\n' + (fail === 0 ? '全部通过' : `${fail} 项失败`));
  process.exit(fail === 0 ? 0 : 1);
})();
