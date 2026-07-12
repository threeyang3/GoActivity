/* System Settings Page — GoActivity */
import API from './api.js';
import { registerPage, toast, esc, statusBadge, timeAgo } from './app.js';

const CORE_SETTING_KEYS = ['app_host', 'app_port', 'allow_lan_access', 'admin_token'];
const TAB_OVERVIEW = 'overview';
const TAB_SETTINGS = 'settings';

let systemState = {
  activeTab: TAB_OVERVIEW,
  settings: null,
  schema: null,
};

registerPage('system', {
  init() {},
  render(body) {
    body.innerHTML = `
      <div class="page-tabs mb-4">
        <button class="page-tab active" data-system-tab="${TAB_OVERVIEW}">运行概览</button>
        <button class="page-tab" data-system-tab="${TAB_SETTINGS}">详细设置</button>
      </div>

      <section data-system-panel="${TAB_OVERVIEW}">
        <div class="metric-grid mb-4" id="system-metrics"><div class="text-muted">加载中...</div></div>
        <div class="dashboard-two-col">
          <div class="card">
            <div class="card-header"><h3 class="card-title">运行状态</h3></div>
            <div class="card-body" id="system-runtime"><div class="text-muted">加载中...</div></div>
          </div>
          <div class="card">
            <div class="card-header"><h3 class="card-title">链路体征</h3></div>
            <div class="card-body" id="pipeline-health"><div class="text-muted">加载中...</div></div>
          </div>
        </div>
        <div class="dashboard-two-col mt-4">
          <div class="card">
            <div class="card-header">
              <h3 class="card-title">核心配置</h3>
              <button class="btn btn-primary btn-sm" id="btn-save-core">保存核心配置</button>
            </div>
            <div class="card-body" id="core-settings"><div class="text-muted">加载中...</div></div>
          </div>
          <div class="card">
            <div class="card-header"><h3 class="card-title">运行操作</h3></div>
            <div class="card-body" id="system-actions"></div>
          </div>
        </div>
        <div class="dashboard-two-col mt-4">
          <div class="card">
            <div class="card-header"><h3 class="card-title">配置诊断</h3></div>
            <div class="card-body" id="config-diagnostics"><div class="text-muted">加载中...</div></div>
          </div>
          <div class="card">
            <div class="card-header"><h3 class="card-title">公众号健康雷达</h3></div>
            <div class="card-body" id="accounts-health"><div class="text-muted">加载中...</div></div>
          </div>
        </div>
      </section>

      <section class="hidden" data-system-panel="${TAB_SETTINGS}">
        <div class="card">
          <div class="card-header">
            <h3 class="card-title">全部设置</h3>
            <button class="btn btn-primary btn-sm" id="btn-save-all">保存全部</button>
          </div>
          <div class="card-body" id="all-settings"><div class="text-muted">切换到此标签后加载</div></div>
        </div>
      </section>`;

    bindTabEvents(body);
    bindActions();
    loadOverviewData();
  }
});

function bindTabEvents(root) {
  root.querySelectorAll('[data-system-tab]').forEach(button => {
    button.onclick = async () => {
      systemState.activeTab = button.dataset.systemTab;
      updateTabUi(root);
      if (systemState.activeTab === TAB_SETTINGS && (!systemState.settings || !systemState.schema)) {
        await loadSettingsData();
      }
    };
  });
}

function updateTabUi(root) {
  root.querySelectorAll('[data-system-tab]').forEach(button => {
    button.classList.toggle('active', button.dataset.systemTab === systemState.activeTab);
  });
  root.querySelectorAll('[data-system-panel]').forEach(panel => {
    panel.classList.toggle('hidden', panel.dataset.systemPanel !== systemState.activeTab);
  });
}

function bindActions() {
  document.getElementById('btn-save-core').onclick = () => saveCoreSettings();
  document.getElementById('btn-save-all').onclick = () => saveAllSettings();
}

async function loadOverviewData() {
  try {
    const settingsPromise = API.getSettings().then(settings => {
      systemState.settings = settings;
      renderCoreSettings(settings);
      renderActions();
      return settings;
    });

    const [health, diagnostics, pipeline, accuracy, accountsHealth, feishuLink, settings] = await Promise.all([
      API.health(),
      API.diagnostics(),
      API.dashboardPipelineStatus(),
      API.dashboardAccuracy(),
      API.dashboardAccountsHealth(),
      API.dashboardFeishuLink(),
      settingsPromise,
    ]);

    renderMetrics(health, pipeline, accuracy);
    renderRuntime(health, settings);
    renderPipeline(pipeline, feishuLink);
    renderDiagnostics(diagnostics, health);
    renderAccountsHealth(accountsHealth);
  } catch (e) {
    toast(`加载系统概览失败: ${e.message}`, 'error');
  }
}

async function loadSettingsData() {
  const container = document.getElementById('all-settings');
  container.innerHTML = '<div class="text-muted">正在加载设置…</div>';
  try {
    const [schema, settings] = await Promise.all([
      API.settingsSchema(),
      systemState.settings ? Promise.resolve(systemState.settings) : API.getSettings(),
    ]);
    systemState.schema = schema;
    systemState.settings = settings;
    renderAllSettings(schema, settings);
  } catch (e) {
    container.innerHTML = `<div class="text-muted">设置加载失败: ${esc(e.message)}</div>`;
  }
}

function renderMetrics(health, pipeline, accuracy) {
  const metrics = [
    ['总体状态', health.status || 'unknown', health.status === 'ok' ? '全部核心模块正常' : '请优先处理异常模块'],
    ['待同步活动', pipeline.pending_sync_count ?? 0, pipeline.last_sync?.status ? `最近同步 ${pipeline.last_sync.status}` : '尚无同步记录'],
    ['低置信度', accuracy.low_confidence_count ?? 0, `已统计 ${accuracy.total_with_confidence ?? 0} 条带置信度活动`],
    ['文章新鲜度', pipeline.article_stale_days ?? 0, pipeline.article_stale_warning ? '采集可能停滞' : '采集最近有更新'],
  ];
  document.getElementById('system-metrics').innerHTML = metrics.map(([label, value, sub]) => `
    <div class="metric-card">
      <div class="metric-label">${esc(label)}</div>
      <div class="metric-value">${typeof value === 'string' ? statusBadge(value) : esc(value)}</div>
      <div class="metric-sub">${esc(sub)}</div>
    </div>`).join('');
}

function renderRuntime(health, settings) {
  const checks = health.checks || {};
  const items = [
    ['数据库', checks.database?.status, checks.database?.detail || '本地 SQLite 主库'],
    ['存储目录', checks.storage?.status, checks.storage?.path || settings.storage_dir || 'storage'],
    ['WeRSS 服务', checks.we_mp_rss?.status, checks.we_mp_rss?.latency_ms ? `${checks.we_mp_rss.latency_ms} ms` : (checks.we_mp_rss?.detail || settings.we_mp_rss_base_url)],
    ['飞书接入', checks.lark_cli?.status, checks.lark_cli?.path || settings.feishu_provider || '未配置'],
    ['自动同步', checks.auto_sync_scheduler?.status, '定时拉取与同步'],
    ['报告任务', checks.report_scheduler?.status, '日报 / 周报'],
    ['飞书机器人', checks.bot_consumer?.status, settings.feishu_bot_enabled ? '已启用会话入口' : '当前未启用'],
  ];
  document.getElementById('system-runtime').innerHTML = `
    <div class="mini-list">
      ${items.map(([label, status, detail]) => `
        <div class="mini-list-item">
          <div class="mini-list-title">${esc(label)} ${statusBadge(status || 'unknown')}</div>
          <div class="mini-list-meta">${esc(detail || '暂无说明')}</div>
        </div>`).join('')}
    </div>`;
}

function renderPipeline(pipeline, feishuLink) {
  const notices = [];
  if (!pipeline.rss_online) notices.push('we-mp-rss 当前不可达，无法继续拉取新文章。');
  if (pipeline.article_stale_warning) notices.push(`最近文章已 ${pipeline.article_stale_days} 天未更新，请检查采集任务。`);
  if (!pipeline.feishu_configured) notices.push('飞书 Base 尚未配置完整，同步无法落库。');
  if (pipeline.last_sync?.status && pipeline.last_sync.status !== 'success') notices.push(`最近一次同步状态为 ${pipeline.last_sync.status}。`);

  document.getElementById('pipeline-health').innerHTML = `
    <div class="kv-table mb-3">
      ${renderKvRows([
        ['采集服务地址', pipeline.rss_url || '未配置'],
        ['最新入库文章', pipeline.latest_article_mp_name || '暂无'],
        ['最近入库时间', pipeline.latest_article_ingested_at ? timeAgo(pipeline.latest_article_ingested_at) : '暂无'],
        ['自动同步 Cron', pipeline.auto_sync_cron || '未配置'],
        ['自动归档阈值', `${pipeline.auto_archive_expired_days ?? 0} 天`],
        ['飞书 Base', feishuLink.configured ? '已配置' : '未配置'],
      ])}
    </div>
    ${feishuLink.url ? `<div class="mb-3"><a href="${esc(feishuLink.url)}" target="_blank" rel="noreferrer">打开飞书多维表格</a></div>` : ''}
    ${notices.length ? `<div class="notice-list">${notices.map(item => `<div class="notice warning">${esc(item)}</div>`).join('')}</div>` : '<div class="empty-inline">当前链路没有明显告警</div>'}`;
}

function renderCoreSettings(settings) {
  document.getElementById('core-settings').innerHTML = `
    <div class="form-group">
      <label class="form-label">监听地址</label>
      <input class="form-input" id="cfg-app-host" value="${esc(settings.app_host || '127.0.0.1')}">
      <div class="form-hint">本机使用建议保持 127.0.0.1，仅在需要局域网共享时调整。</div>
    </div>
    <div class="form-group">
      <label class="form-label">监听端口</label>
      <input class="form-input" id="cfg-app-port" type="number" value="${esc(settings.app_port || 8000)}">
    </div>
    <div class="form-group">
      <label class="form-label">允许局域网访问</label>
      <select class="form-select" id="cfg-allow-lan">
        <option value="false" ${!settings.allow_lan_access ? 'selected' : ''}>否</option>
        <option value="true" ${settings.allow_lan_access ? 'selected' : ''}>是</option>
      </select>
      <div class="form-hint">启用后请务必配置管理令牌。</div>
    </div>
    <div class="form-group">
      <label class="form-label">管理令牌</label>
      <div class="secret-row">
        <input class="form-input" id="cfg-admin-token" type="password" placeholder="留空表示保持不变" value="">
        <button type="button" class="btn btn-ghost btn-sm" data-toggle-secret="cfg-admin-token">显示</button>
      </div>
    </div>`;
}

function renderActions() {
  document.getElementById('system-actions').innerHTML = `
    <div class="action-stack">
      <button class="btn btn-secondary" id="btn-reload-settings">重新加载运行时配置</button>
      <button class="btn btn-secondary" id="btn-reset-core">重置核心配置到默认值</button>
      <div class="form-hint">重新加载适用于可热更新模块；端口、监听地址等仍可能需要手动重启服务。</div>
      <div id="system-action-result"></div>
    </div>`;

  document.getElementById('btn-reload-settings').onclick = async () => {
    try {
      const result = await API.reloadSettings();
      reportSaveResult({ ...result, applied: [] });
      document.getElementById('system-action-result').innerHTML = '<div class="test-result ok">运行时配置已重载</div>';
      await refreshAllData();
    } catch (e) {
      document.getElementById('system-action-result').innerHTML = `<div class="test-result error">重载失败: ${esc(e.message)}</div>`;
      toast(`重载失败: ${e.message}`, 'error');
    }
  };

  document.getElementById('btn-reset-core').onclick = async () => {
    try {
      const result = await API.resetSettings(CORE_SETTING_KEYS);
      if (result.reset?.length) toast(`已重置 ${result.reset.length} 项核心配置`, 'warning');
      if (result.reloaded?.length) toast(`已热加载: ${result.reloaded.join(', ')}`, 'info');
      if (result.rescheduled?.length) toast(`已重建任务: ${result.rescheduled.join(', ')}`, 'info');
      await refreshAllData();
    } catch (e) {
      toast(`重置失败: ${e.message}`, 'error');
    }
  };
}

function renderDiagnostics(diagnostics, health) {
  const diagChecks = diagnostics.checks || [];
  const configWarnings = health.checks?.config?.warnings || [];
  const rows = diagChecks.map(item => `
    <div class="mini-list-item">
      <div class="mini-list-title">${esc(item.key)} ${statusBadge(item.configured ? 'ok' : 'disabled')}</div>
      <div class="mini-list-meta">${esc(item.detail || item.source || '')}</div>
    </div>`).join('');

  document.getElementById('config-diagnostics').innerHTML = `
    ${configWarnings.length ? `<div class="notice-list mb-3">${configWarnings.map(item => `<div class="notice warning">${esc(item)}</div>`).join('')}</div>` : ''}
    <div class="mini-list">${rows || '<div class="empty-inline">暂无诊断信息</div>'}</div>`;
}

function renderAccountsHealth(items = []) {
  const sorted = [...items].sort((a, b) => (b.stale_days || 0) - (a.stale_days || 0)).slice(0, 8);
  if (!sorted.length) {
    document.getElementById('accounts-health').innerHTML = '<div class="empty-inline">暂无公众号数据</div>';
    return;
  }
  document.getElementById('accounts-health').innerHTML = `
    <div class="mini-list">
      ${sorted.map(item => `
        <div class="mini-list-item">
          <div class="mini-list-title">${esc(item.mp_name)}</div>
          <div class="mini-list-meta">
            文章 ${esc(item.article_count)} · 活动 ${esc(item.event_count)} · 最近入库 ${item.latest_ingested_at ? timeAgo(item.latest_ingested_at) : '暂无'}
            ${item.stale_days >= 3 ? ' · 需关注' : ''}
          </div>
        </div>`).join('')}
    </div>`;
}

function renderAllSettings(schema, settings) {
  const container = document.getElementById('all-settings');
  const categories = {};
  schema.forEach(item => {
    const category = item.category || 'other';
    if (!categories[category]) categories[category] = [];
    categories[category].push(item);
  });

  const labels = {
    service: '服务',
    database: '数据库',
    automation: '自动化',
    reports: '报告',
    feishu: '飞书',
    feishu_bot: '飞书机器人',
    werss: 'we-mp-rss',
    ocr: 'OCR',
    vision: 'Vision',
    text_ai: '文本 AI',
  };

  container.innerHTML = Object.entries(categories).map(([category, items]) => `
    <div class="settings-section mb-4">
      <div class="settings-section-header">
        <h3 class="settings-section-title">${esc(labels[category] || category)}</h3>
      </div>
      <div class="settings-section-body">
        ${items.map(item => renderSchemaField(item, settings[item.key])).join('')}
      </div>
    </div>`).join('');
}

function renderSchemaField(item, value) {
  const displayValue = typeof value === 'object' && value?.configured !== undefined ? '' : (value ?? item.default ?? '');
  const configuredHint = item.is_secret && value?.configured ? `当前: ${value.masked_value}` : '';
  if (item.type === 'select') {
    return `
      <div class="form-group">
        <label class="form-label">${esc(item.label)}</label>
        <select class="form-select" data-key="${esc(item.key)}">
          ${(item.options || []).map(option => `<option value="${esc(option)}" ${displayValue === option ? 'selected' : ''}>${esc(option)}</option>`).join('')}
        </select>
        ${item.help ? `<div class="form-hint">${esc(item.help)}</div>` : ''}
      </div>`;
  }
  if (item.type === 'boolean') {
    return `
      <div class="form-group">
        <label class="form-label">${esc(item.label)}</label>
        <select class="form-select" data-key="${esc(item.key)}">
          <option value="true" ${displayValue === true ? 'selected' : ''}>是</option>
          <option value="false" ${displayValue !== true ? 'selected' : ''}>否</option>
        </select>
        ${item.help ? `<div class="form-hint">${esc(item.help)}</div>` : ''}
      </div>`;
  }
  const inputType = item.is_secret ? 'password' : (item.type === 'integer' || item.type === 'number' ? 'number' : 'text');
  const fieldId = `all-${item.key}`;
  return `
    <div class="form-group">
      <label class="form-label">${esc(item.label)}</label>
      <div class="secret-row">
        <input class="form-input" id="${fieldId}" data-key="${esc(item.key)}" type="${inputType}" value="${esc(displayValue)}" placeholder="${item.is_secret ? '留空表示保持不变' : ''}">
        ${item.is_secret ? `<button type="button" class="btn btn-ghost btn-sm" data-toggle-secret="${fieldId}">显示</button>` : ''}
      </div>
      ${configuredHint ? `<div class="form-hint">${esc(configuredHint)}</div>` : ''}
      ${item.help ? `<div class="form-hint">${esc(item.help)}</div>` : ''}
    </div>`;
}

async function refreshAllData() {
  systemState.settings = null;
  systemState.schema = null;
  await loadOverviewData();
  if (systemState.activeTab === TAB_SETTINGS) {
    await loadSettingsData();
  }
}

async function saveCoreSettings() {
  const updates = {};
  const host = document.getElementById('cfg-app-host')?.value.trim();
  const port = document.getElementById('cfg-app-port')?.value.trim();
  const allowLan = document.getElementById('cfg-allow-lan')?.value;
  const token = document.getElementById('cfg-admin-token')?.value;

  if (host) updates.app_host = host;
  if (port) updates.app_port = parseInt(port, 10);
  if (allowLan) updates.allow_lan_access = allowLan === 'true';
  if (token) updates.admin_token = token;

  try {
    const result = await API.updateSettings(updates);
    reportSaveResult(result);
    await refreshAllData();
  } catch (e) {
    toast(`保存核心配置失败: ${e.message}`, 'error');
  }
}

async function saveAllSettings() {
  const updates = {};
  document.querySelectorAll('#all-settings [data-key]').forEach(el => {
    const key = el.dataset.key;
    let value = el.value;
    if (el.tagName === 'SELECT' && (value === 'true' || value === 'false')) value = value === 'true';
    if (el.type === 'number' && value !== '') value = value.includes('.') ? parseFloat(value) : parseInt(value, 10);
    if (el.type === 'password' && value === '') return;
    updates[key] = value;
  });

  try {
    const result = await API.updateSettings(updates);
    reportSaveResult(result);
    await refreshAllData();
  } catch (e) {
    toast(`保存全部设置失败: ${e.message}`, 'error');
  }
}

function reportSaveResult(result) {
  if (result.applied?.length) toast(`已应用 ${result.applied.length} 项配置`, 'success');
  if (result.reloaded?.length) toast(`已热加载: ${result.reloaded.join(', ')}`, 'info');
  if (result.rescheduled?.length) toast(`已重建任务: ${result.rescheduled.join(', ')}`, 'info');
  if (result.restart_required?.length) toast(`需要重启: ${result.restart_required.join(', ')}`, 'warning');
  if (result.errors?.length) result.errors.forEach(item => toast(`${item.key}: ${item.error}`, 'error'));
}

function renderKvRows(rows) {
  return rows.map(([label, value]) => `
    <div class="kv-row">
      <div class="kv-key">${esc(label)}</div>
      <div class="kv-value">${esc(value)}</div>
    </div>`).join('');
}

document.addEventListener('click', event => {
  const button = event.target.closest('[data-toggle-secret]');
  if (!button) return;
  const input = document.getElementById(button.dataset.toggleSecret);
  if (!input) return;
  input.type = input.type === 'password' ? 'text' : 'password';
  button.textContent = input.type === 'password' ? '显示' : '隐藏';
});
