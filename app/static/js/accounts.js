/* Accounts Operations Desk — GoActivity */
import API from './api.js';
import { registerPage, toast, esc, timeAgo, openModal, closeModal } from './app.js';

let accounts = [];
let healthRows = [];
let authorization = null;
let activeFilter = 'all';

registerPage('accounts', {
  init() {},
  render(body) {
    body.innerHTML = `
      <section class="accounts-briefing" aria-labelledby="accounts-briefing-title">
        <div class="accounts-briefing-copy">
          <div class="eyebrow">SOURCE OPERATIONS · 来源运营台</div>
          <h2 id="accounts-briefing-title">先确认授权，再管理采集</h2>
          <p>微信授权是所有公众号采集的总开关；下方逐项展示每个来源的数据新鲜度与产出。</p>
        </div>
        <div class="accounts-briefing-actions">
          <button class="btn btn-secondary" id="btn-refresh-accounts">刷新状态</button>
          <button class="btn btn-primary" id="btn-open-authorization">管理微信授权</button>
        </div>
      </section>

      <section class="source-status-board" id="source-status-board" aria-live="polite">
        <div class="source-status-loading"><span class="spinner spinner-sm"></span> 正在检查采集链路...</div>
      </section>

      <section class="accounts-workspace">
        <div class="accounts-workspace-heading">
          <div>
            <div class="eyebrow">SUBSCRIPTIONS · 订阅来源</div>
            <h2>公众号清单</h2>
          </div>
          <button class="btn btn-primary" id="btn-add-account">＋ 添加公众号</button>
        </div>
        <div class="accounts-toolbar">
          <label class="account-search-wrap">
            <span class="sr-only">搜索公众号</span>
            <input type="search" class="form-input" id="account-search" placeholder="搜索名称或公众号 ID">
          </label>
          <label class="account-filter-wrap">
            <span>查看</span>
            <select class="form-select" id="account-health-filter">
              <option value="all">全部来源</option>
              <option value="attention">需要处理</option>
              <option value="healthy">状态正常</option>
            </select>
          </label>
          <div class="accounts-result-count" id="accounts-result-count">—</div>
        </div>
        <div id="accounts-list" class="accounts-grid">
          <div class="account-list-loading"><span class="spinner"></span><span>正在汇总公众号状态...</span></div>
        </div>
      </section>`;

    document.getElementById('btn-refresh-accounts').onclick = () => loadWorkspace(true);
    document.getElementById('btn-add-account').onclick = showAddAccountModal;
    document.getElementById('btn-open-authorization').onclick = openAuthorizationCenter;
    document.getElementById('account-search').oninput = debounce(renderAccounts, 180);
    document.getElementById('account-health-filter').onchange = event => {
      activeFilter = event.target.value;
      renderAccounts();
    };
    document.getElementById('accounts-list').onclick = handleAccountAction;
    loadWorkspace();
  }
});

function debounce(fn, ms) {
  let timer;
  return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), ms); };
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

function accountId(account) {
  return account.mp_id || account.id || '';
}

function accountAvatar(account) {
  return account.avatar || account.mp_cover || '';
}

function accountInitial(account) {
  return (account.mp_name || '?').trim().slice(0, 1);
}

function accountDescription(account) {
  return account.mp_intro || '暂无公众号简介';
}

function healthFor(account) {
  const id = accountId(account);
  return healthRows.find(item => (id && item.mp_id === id) || item.mp_name === account.mp_name) || null;
}

function healthPresentation(row) {
  const map = {
    fresh: { label: '数据新鲜', tone: 'ok', note: '最近采集在 SLA 内' },
    quiet_source: { label: '近期停更', tone: 'quiet', note: '来源近期没有新文章' },
    stale_data: { label: '采集滞后', tone: 'warning', note: '来源有新内容但本地未及时采集' },
    never_collected: { label: '从未采集', tone: 'danger', note: '请立即触发一次采集' },
  };
  return map[row?.health_status] || { label: '等待检测', tone: 'unknown', note: '暂无本地采集记录' };
}

function needsAttention(row) {
  return ['stale_data', 'never_collected'].includes(row?.health_status);
}

async function loadWorkspace(showToast = false) {
  const refreshButton = document.getElementById('btn-refresh-accounts');
  if (refreshButton) {
    refreshButton.disabled = true;
    refreshButton.textContent = '检查中…';
  }
  const results = await Promise.allSettled([
    API.accounts({ limit: 100 }),
    API.automationAccountsHealth(),
    API.accountAuthorization(),
  ]);

  healthRows = results[1].status === 'fulfilled' && Array.isArray(results[1].value) ? results[1].value : [];
  accounts = results[0].status === 'fulfilled'
    ? normalizeAccountList(results[0].value)
    : healthRows.filter(item => item.remote_subscribed).map(item => ({
      id: item.mp_id,
      mp_name: item.mp_name,
      status: 1,
      mp_intro: '订阅列表暂不可用，当前显示本地健康记录',
    }));
  authorization = results[2].status === 'fulfilled' ? results[2].value : {
    service_reachable: false,
    authorization_status: 'unknown',
    error: results[2].reason?.message || '状态检查失败',
  };

  renderSourceStatus();
  renderAccounts();
  if (refreshButton) {
    refreshButton.disabled = false;
    refreshButton.textContent = '刷新状态';
  }
  if (showToast) toast('公众号与授权状态已刷新', 'success');
}

function renderSourceStatus() {
  const container = document.getElementById('source-status-board');
  if (!container) return;
  const attentionCount = accounts.filter(account => needsAttention(healthFor(account))).length;
  const authorized = Boolean(authorization?.authorized);
  const reachable = Boolean(authorization?.service_reachable);
  const authTone = !reachable ? 'danger' : (authorized ? 'ok' : 'warning');
  const authTitle = !reachable ? '采集器不可达' : (authorized ? '微信授权有效' : '微信授权已失效');
  const authDetail = !reachable
    ? (authorization?.error || '无法连接 WeRSS 服务')
    : (authorized
      ? `${authorization.account_name || '当前微信公众平台账号'}${authorization.expiry_time ? ` · 到期 ${authorization.expiry_time}` : ''}`
      : '请进入授权中心扫码，恢复公众号搜索与文章采集');
  const healthTone = attentionCount ? 'warning' : 'ok';
  const healthTitle = attentionCount ? `${attentionCount} 个来源需要处理` : '来源数据状态正常';
  const collectedCount = healthRows.filter(item => item.article_count > 0).length;

  container.innerHTML = `
    <article class="source-status-primary tone-${authTone}">
      <div class="source-status-icon">${authorized && reachable ? '✓' : '!'}</div>
      <div class="source-status-copy">
        <div class="source-status-kicker">微信采集授权 · 总开关</div>
        <h3>${esc(authTitle)}</h3>
        <p>${esc(authDetail)}</p>
      </div>
      <button class="source-status-link" id="status-open-authorization">${authorized ? '查看授权' : '立即处理'} →</button>
    </article>
    <article class="source-stat-tile">
      <span class="source-stat-label">已订阅</span>
      <strong>${accounts.length}</strong>
      <span>个公众号来源</span>
    </article>
    <article class="source-stat-tile tone-${healthTone}">
      <span class="source-stat-label">数据体征</span>
      <strong>${attentionCount}</strong>
      <span>${esc(healthTitle)}</span>
    </article>
    <article class="source-stat-tile">
      <span class="source-stat-label">已有数据</span>
      <strong>${collectedCount}</strong>
      <span>个来源已入库</span>
    </article>`;
  document.getElementById('status-open-authorization').onclick = openAuthorizationCenter;
}

function renderAccounts() {
  const container = document.getElementById('accounts-list');
  if (!container) return;
  const query = (document.getElementById('account-search')?.value || '').trim().toLowerCase();
  const visible = accounts.filter(account => {
    const row = healthFor(account);
    const matchesText = !query || `${account.mp_name || ''} ${accountId(account)}`.toLowerCase().includes(query);
    const matchesFilter = activeFilter === 'all'
      || (activeFilter === 'attention' && needsAttention(row))
      || (activeFilter === 'healthy' && !needsAttention(row));
    return matchesText && matchesFilter;
  });

  const count = document.getElementById('accounts-result-count');
  if (count) count.textContent = `显示 ${visible.length} / ${accounts.length}`;
  if (!visible.length) {
    container.innerHTML = `<div class="empty-state accounts-empty">
      <p class="empty-state-title">没有符合条件的公众号</p>
      <p>${accounts.length ? '试试清除搜索词或切换筛选条件。' : '点击“添加公众号”建立第一个采集来源。'}</p>
    </div>`;
    return;
  }

  container.innerHTML = visible.map((account, index) => {
    const row = healthFor(account);
    const health = healthPresentation(row);
    const latestIngested = row?.latest_ingested_at ? timeAgo(row.latest_ingested_at) : '无记录';
    const latestPublish = row?.latest_publish_epoch
      ? timeAgo(new Date(Number(row.latest_publish_epoch) * 1000).toISOString())
      : '无记录';
    const subscribed = account.status === undefined || Number(account.status) === 1;
    return `
      <article class="account-card account-tone-${health.tone}" style="--account-index:${index}">
        <div class="account-card-topline">
          <span class="account-health-mark"></span>
          <span class="account-health-label">${esc(health.label)}</span>
          <span class="account-subscription-state">${subscribed ? '● 已订阅' : '○ 已停用'}</span>
        </div>
        <div class="account-card-identity">
          <div class="account-avatar account-avatar-rich">
            ${accountAvatar(account) ? `<img src="${esc(accountAvatar(account))}" alt="" loading="lazy" referrerpolicy="no-referrer">` : ''}
            <span class="account-avatar-fallback">${esc(accountInitial(account))}</span>
          </div>
          <div class="account-info">
            <h3 class="account-name">${esc(account.mp_name || '未命名公众号')}</h3>
            <div class="account-meta font-mono">${esc(accountId(account))}</div>
          </div>
        </div>
        <p class="account-desc">${esc(accountDescription(account))}</p>
        <div class="account-health-note">${esc(health.note)}</div>
        <dl class="account-metrics">
          <div><dt>文章入库</dt><dd>${row?.article_count ?? 0}</dd></div>
          <div><dt>活动产出</dt><dd>${row?.event_count ?? 0}</dd></div>
          <div><dt>最近入库</dt><dd>${esc(latestIngested)}</dd></div>
          <div><dt>最近发文</dt><dd>${esc(latestPublish)}</dd></div>
        </dl>
        <div class="account-actions">
          <button class="btn btn-primary btn-sm" data-action="update" data-id="${esc(accountId(account))}">立即采集</button>
          <button class="btn btn-ghost btn-sm account-delete" data-action="delete" data-id="${esc(accountId(account))}" data-name="${esc(account.mp_name || '')}">移除订阅</button>
        </div>
      </article>`;
  }).join('');
}

function openAuthorizationCenter() {
  const url = authorization?.admin_url || 'http://127.0.0.1:8001/#/wechat-status';
  window.open(url, '_blank', 'noopener,noreferrer');
}

async function handleAccountAction(event) {
  const button = event.target.closest('button[data-action]');
  if (!button) return;
  const id = button.dataset.id;
  if (button.dataset.action === 'update') await updateAccount(id, button);
  if (button.dataset.action === 'delete') await deleteAccount(id, button.dataset.name);
}

function showAddAccountModal() {
  openModal('添加公众号', `
    <div class="add-account-intro">
      <strong>从微信公众平台搜索并订阅</strong>
      <span>搜索依赖有效的微信授权；若搜索失败，请先关闭弹窗并检查页面顶部授权状态。</span>
    </div>
    <div class="form-group">
      <label class="form-label" for="search-kw">公众号名称</label>
      <input class="form-input" id="search-kw" placeholder="例如：北大团委" autocomplete="off">
    </div>
    <div id="search-results" class="account-search-results"><div class="search-prompt">输入至少两个字开始搜索</div></div>`,
    `<button class="btn btn-secondary" id="btn-close-account-modal">取消</button>`);
  document.getElementById('btn-close-account-modal').onclick = closeModal;
  document.getElementById('search-kw').oninput = debounce(searchAvailableAccounts, 450);
}

async function searchAvailableAccounts() {
  const kw = document.getElementById('search-kw')?.value.trim() || '';
  const container = document.getElementById('search-results');
  if (!container) return;
  if (kw.length < 2) {
    container.innerHTML = '<div class="search-prompt">输入至少两个字开始搜索</div>';
    return;
  }
  container.innerHTML = '<div class="search-prompt"><span class="spinner spinner-sm"></span> 正在搜索微信公众平台...</div>';
  try {
    const results = await API.searchAccounts(kw);
    const list = normalizeAccountList(results);
    if (!list.length) {
      container.innerHTML = '<div class="search-prompt">没有找到匹配公众号，请尝试更完整的名称。</div>';
      return;
    }
    container.innerHTML = list.map(account => `
      <button class="account-search-result" type="button" data-id="${esc(accountId(account))}" data-name="${esc(account.mp_name || '')}" data-avatar="${esc(accountAvatar(account))}">
        <span class="account-avatar account-avatar-rich">
          ${accountAvatar(account) ? `<img src="${esc(accountAvatar(account))}" alt="" loading="lazy" referrerpolicy="no-referrer">` : ''}
          <span class="account-avatar-fallback">${esc(accountInitial(account))}</span>
        </span>
        <span class="account-info">
          <strong class="account-name">${esc(account.mp_name || '未命名公众号')}</strong>
          <span class="account-meta">${esc(accountDescription(account))}</span>
        </span>
        <span class="search-result-action">添加 →</span>
      </button>`).join('');
    container.onclick = event => {
      const target = event.target.closest('.account-search-result');
      if (target) addAccount(target.dataset.id, target.dataset.name, target.dataset.avatar, target);
    };
  } catch (error) {
    container.innerHTML = `<div class="search-error">搜索失败：${esc(error.message)}<br><small>请检查微信授权和 WeRSS 服务状态。</small></div>`;
  }
}

async function addAccount(mpId, mpName, avatar, button) {
  button.disabled = true;
  try {
    await API.addAccount({ mp_id: mpId, mp_name: mpName, avatar });
    toast(`已添加：${mpName}`, 'success');
    closeModal();
    await loadWorkspace();
  } catch (error) {
    button.disabled = false;
    toast(`添加失败：${error.message}`, 'error');
  }
}

async function deleteAccount(mpId, name) {
  if (!confirm(`确认移除公众号“${name}”？已有文章和活动不会被删除。`)) return;
  try {
    await API.deleteAccount(mpId);
    toast(`已移除订阅：${name}`, 'success');
    await loadWorkspace();
  } catch (error) {
    toast(`移除失败：${error.message}`, 'error');
  }
}

async function updateAccount(mpId, button) {
  const original = button.textContent;
  button.disabled = true;
  button.textContent = '已提交…';
  try {
    await API.updateAccount(mpId);
    toast('采集任务已提交，可稍后刷新查看最新入库时间', 'success');
  } catch (error) {
    button.disabled = false;
    button.textContent = original;
    toast(`采集失败：${error.message}`, 'error');
  }
}
