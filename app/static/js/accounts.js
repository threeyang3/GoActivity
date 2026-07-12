/* Accounts Page — GoActivity */
import API from './api.js';
import { registerPage, toast, esc, timeAgo, openModal, closeModal } from './app.js';

registerPage('accounts', {
  init() {},
  render(body) {
    body.innerHTML = `
      <div class="events-toolbar">
        <input type="text" class="form-input" id="account-search" placeholder="搜索公众号...">
        <button class="btn btn-primary btn-sm" id="btn-add-account">添加公众号</button>
        <button class="btn btn-secondary btn-sm" id="btn-refresh-accounts">刷新</button>
      </div>
      <div id="accounts-list" class="grid gap-4" style="grid-template-columns: repeat(auto-fill, minmax(320px, 1fr))">
        <div class="text-muted">加载中...</div>
      </div>`;

    loadAccounts();
    document.getElementById('btn-refresh-accounts').onclick = () => loadAccounts();
    document.getElementById('btn-add-account').onclick = () => showAddAccountModal();
    document.getElementById('account-search').oninput = debounce(() => loadAccounts(), 300);
  }
});

function debounce(fn, ms) {
  let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

function normalizeAccountList(payload) {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.items)) return payload.items;
  if (Array.isArray(payload?.data)) return payload.data;
  if (Array.isArray(payload?.data?.items)) return payload.data.items;
  if (Array.isArray(payload?.data?.list)) return payload.data.list;
  if (Array.isArray(payload?.list)) return payload.list;
  return [];
}

function accountId(mp) {
  return mp.mp_id || mp.id || '';
}

function accountAvatar(mp) {
  return mp.avatar || mp.mp_cover || '';
}

function accountUpdatedAt(mp) {
  return mp.updated_at || mp.last_update || mp.created_at || '';
}

function accountInitial(mp) {
  return (mp.mp_name || '?').trim().slice(0, 1);
}

function accountDescription(mp) {
  return mp.mp_intro || '暂无简介';
}

async function loadAccounts() {
  const container = document.getElementById('accounts-list');
  const kw = document.getElementById('account-search')?.value || '';
  try {
    const params = { limit: 50 };
    if (kw) params.kw = kw;
    const data = await API.accounts(params);
    const list = normalizeAccountList(data);
    if (!list.length) { container.innerHTML = '<div class="empty-state"><p class="empty-state-title">暂无公众号</p></div>'; return; }
    container.innerHTML = list.map(mp => `
      <div class="account-card">
        <div class="account-avatar account-avatar-rich">
          ${accountAvatar(mp) ? `<img src="${esc(accountAvatar(mp))}" alt="" loading="lazy" referrerpolicy="no-referrer">` : ''}
          <span class="account-avatar-fallback">${esc(accountInitial(mp))}</span>
        </div>
        <div class="account-info">
          <div class="account-header-row">
            <div class="account-name">${esc(mp.mp_name)}</div>
            <div class="account-meta">更新 ${timeAgo(accountUpdatedAt(mp))}</div>
          </div>
          <div class="account-meta font-mono">${esc(accountId(mp))}</div>
          <div class="account-desc">${esc(accountDescription(mp))}</div>
        </div>
        <div class="account-actions">
          <button class="btn btn-ghost btn-sm" onclick="window._updateAccount('${esc(accountId(mp))}')">更新</button>
          <button class="btn btn-ghost btn-sm" style="color:var(--color-red)" onclick="window._deleteAccount('${esc(accountId(mp))}', '${esc(mp.mp_name)}')">删除</button>
        </div>
      </div>`).join('');
  } catch (e) {
    container.innerHTML = `<div class="text-muted">加载失败: ${esc(e.message)}</div>`;
  }
}

function showAddAccountModal() {
  openModal('添加公众号', `
    <div class="form-group"><label class="form-label">搜索公众号</label><input class="form-input" id="search-kw" placeholder="输入公众号名称"></div>
    <div id="search-results"></div>`,
    `<button class="btn btn-secondary" onclick="window._closeModal()">取消</button>`);
  document.getElementById('search-kw').oninput = debounce(async () => {
    const kw = document.getElementById('search-kw').value.trim();
    if (!kw) return;
    const container = document.getElementById('search-results');
    container.innerHTML = '<div class="text-muted">搜索中...</div>';
    try {
      const results = await API.searchAccounts(kw);
      const list = normalizeAccountList(results);
      if (!list.length) { container.innerHTML = '<div class="text-muted">未找到</div>'; return; }
      container.innerHTML = list.map(mp => `
        <div class="account-card mb-2" style="cursor:pointer" onclick="window._addAccount('${esc(accountId(mp))}', '${esc(mp.mp_name)}', '${esc(accountAvatar(mp))}')">
          <div class="account-avatar account-avatar-rich">
            ${accountAvatar(mp) ? `<img src="${esc(accountAvatar(mp))}" alt="" loading="lazy" referrerpolicy="no-referrer">` : ''}
            <span class="account-avatar-fallback">${esc(accountInitial(mp))}</span>
          </div>
          <div class="account-info">
            <div class="account-name">${esc(mp.mp_name)}</div>
            <div class="account-meta">${esc(accountDescription(mp))}</div>
          </div>
        </div>`).join('');
    } catch (e) { container.innerHTML = `<div class="text-muted">搜索失败: ${esc(e.message)}</div>`; }
  }, 500);
}

window._addAccount = async function(mpId, mpName, avatar) {
  try {
    await API.addAccount({ mp_id: mpId, mp_name: mpName, avatar });
    toast(`已添加: ${mpName}`, 'success');
    closeModal();
    loadAccounts();
  } catch (e) { toast(`添加失败: ${e.message}`, 'error'); }
};

window._deleteAccount = async function(mpId, name) {
  if (!confirm(`确认删除公众号 "${name}"？`)) return;
  try {
    await API.deleteAccount(mpId);
    toast(`已删除: ${name}`, 'success');
    loadAccounts();
  } catch (e) { toast(`删除失败: ${e.message}`, 'error'); }
};

window._updateAccount = async function(mpId) {
  try {
    await API.updateAccount(mpId);
    toast('已触发更新', 'success');
  } catch (e) { toast(`更新失败: ${e.message}`, 'error'); }
};

window._closeModal = closeModal;
