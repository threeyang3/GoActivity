/* App Core — GoActivity */
import API from './api.js';
import State from './state.js';

/* ── Utilities ── */
export function toast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = message;
  container.appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; setTimeout(() => el.remove(), 200); }, 3200);
}

export function esc(v) {
  if (v == null) return '';
  const d = document.createElement('div');
  d.textContent = String(v);
  return d.innerHTML;
}

export function timeAgo(iso) {
  if (!iso) return '未知';
  const t = new Date(iso).getTime();
  if (isNaN(t)) return iso;
  const m = Math.floor((Date.now() - t) / 60000);
  if (m < 1) return '刚刚';
  if (m < 60) return `${m}分钟前`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}小时前`;
  const d = Math.floor(h / 24);
  if (d < 30) return `${d}天前`;
  return `${Math.floor(d / 30)}个月前`;
}

export function statusBadge(status) {
  const map = {
    ok: ['badge-ok', '正常'], degraded: ['badge-degraded', '降级'],
    error: ['badge-error', '错误'], disabled: ['badge-disabled', '已禁用'],
    configured: ['badge-ok', '已配置'], not_configured: ['badge-muted', '未配置'],
    mock: ['badge-muted', 'Mock'], unreachable: ['badge-error', '不可达'],
    running: ['badge-ok', '运行中'], stopped: ['badge-error', '已停止'],
    no_runs: ['badge-muted', '无记录'],
  };
  const [cls, label] = map[status] || ['badge-muted', status];
  return `<span class="badge ${cls}">${esc(label)}</span>`;
}

export function eventStatusBadge(status) {
  const map = {
    pending: ['badge-muted', '待处理'], pending_ai: ['badge-muted', '待抽取'],
    extracted: ['badge-ok', '已抽取'], synced: ['badge-ok', '已同步'],
    filtered_out: ['badge-disabled', '已过滤'], expired_hidden: ['badge-disabled', '已过期'],
    archived: ['badge-muted', '已归档'], error: ['badge-error', '错误'],
  };
  const [cls, label] = map[status] || ['badge-muted', status];
  return `<span class="badge ${cls}">${esc(label)}</span>`;
}

export function categoryBadge(cat) {
  if (!cat || cat === '其他') return '';
  return `<span class="badge badge-muted">${esc(cat)}</span>`;
}

/* ── Modal ── */
let currentModal = null;
export function openModal(title, bodyHtml, footerHtml = '') {
  closeModal();
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.innerHTML = `
    <div class="modal">
      <div class="modal-header">
        <h3 class="modal-title">${esc(title)}</h3>
        <button class="btn btn-ghost btn-icon btn-sm modal-close" aria-label="关闭">&times;</button>
      </div>
      <div class="modal-body">${bodyHtml}</div>
      ${footerHtml ? `<div class="modal-footer">${footerHtml}</div>` : ''}
    </div>`;
  document.body.appendChild(overlay);
  currentModal = overlay;
  overlay.querySelector('.modal-close').onclick = closeModal;
  overlay.addEventListener('click', e => { if (e.target === overlay) closeModal(); });
  document.addEventListener('keydown', function handler(e) {
    if (e.key === 'Escape') { closeModal(); document.removeEventListener('keydown', handler); }
  });
  const firstInput = overlay.querySelector('input, select, textarea');
  if (firstInput) firstInput.focus();
}
export function closeModal() {
  if (currentModal) { currentModal.remove(); currentModal = null; }
}

/* ── Navigation ── */
const pages = {};
export function registerPage(name, { init, render }) {
  pages[name] = { init, render };
}

function normalizePage(page) {
  return pages[page] ? page : 'overview';
}

function currentHashPage() {
  return normalizePage((window.location.hash || '').replace(/^#/, '').trim());
}

export function navigate(page, { updateHash = true } = {}) {
  page = normalizePage(page);
  State.set('currentPage', page);
  // Update nav
  document.querySelectorAll('.nav-item').forEach(el => {
    el.classList.toggle('active', el.dataset.page === page);
  });
  // Render page
  const body = document.getElementById('page-body');
  if (body) {
    body.innerHTML = '';
    pages[page].render(body);
  }
  // Update header
  const titles = {
    overview: '管理总览', events: '活动管理', accounts: '公众号管理',
    automation: '自动化', integrations: '集成与模型', system: '系统设置',
  };
  const titleEl = document.getElementById('page-title');
  if (titleEl) titleEl.textContent = titles[page] || page;

  if (updateHash && window.location.hash !== `#${page}`) {
    window.location.hash = page;
  }
}

/* ── Init ── */
export async function initApp() {
  // Setup navigation
  document.querySelectorAll('.nav-item[data-page]').forEach(el => {
    el.addEventListener('click', () => navigate(el.dataset.page));
  });

  window.addEventListener('hashchange', () => {
    const page = currentHashPage();
    if (State.get('currentPage') !== page) {
      navigate(page, { updateHash: false });
    }
  });

  // Init pages
  for (const [name, page] of Object.entries(pages)) {
    if (page.init) await page.init();
  }

  navigate(currentHashPage(), { updateHash: false });
}
