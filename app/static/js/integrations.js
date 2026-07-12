/* Integrations Page — GoActivity */
import API from './api.js';
import { registerPage, toast, esc, statusBadge } from './app.js';

const GROUPS = {
  ocr: ['ocr_provider', 'ocr_api_key', 'ocr_api_base_url', 'ocr_api_model', 'ocr_api_timeout_seconds', 'ocr_max_images'],
  vision: ['vision_api_provider', 'vision_api_key', 'vision_api_base_url', 'vision_api_model', 'vision_api_timeout_seconds', 'vision_max_images', 'vision_max_tokens'],
  text_ai: ['text_ai_provider', 'text_ai_api_key', 'text_ai_api_base_url', 'text_ai_api_model', 'text_ai_api_timeout_seconds', 'text_ai_max_tokens'],
  feishu: ['feishu_provider', 'feishu_cli_path', 'feishu_app_id', 'feishu_app_secret', 'feishu_bitable_app_token', 'feishu_bitable_table_id', 'feishu_dry_run'],
  werss: ['we_mp_rss_base_url', 'we_mp_rss_api_base', 'we_mp_rss_access_key', 'we_mp_rss_secret_key'],
};

registerPage('integrations', {
  init() {},
  render(body) {
    body.innerHTML = `
      <div class="card mb-4">
        <div class="card-header"><h3 class="card-title">推荐管线</h3></div>
        <div class="card-body">
          <div class="preset-grid">
            <button class="preset-card" data-preset="balanced">
              <div class="preset-title">RapidOCR + 多模态 Vision</div>
              <div class="preset-desc">兼顾成本、速度和图片理解能力。</div>
            </button>
            <button class="preset-card" data-preset="api-heavy">
              <div class="preset-title">API OCR + 多模态 Vision</div>
              <div class="preset-desc">适合追求更高识别精度的场景。</div>
            </button>
            <button class="preset-card" data-preset="budget">
              <div class="preset-title">RapidOCR + 文本 AI</div>
              <div class="preset-desc">最低成本，适合大量处理。</div>
            </button>
          </div>
        </div>
      </div>
      <div class="settings-grid" id="integration-panels"><div class="text-muted">加载中...</div></div>`;

    loadPanels();
    body.querySelectorAll('[data-preset]').forEach(btn => {
      btn.onclick = () => applyPreset(btn.dataset.preset);
    });
  }
});

async function loadPanels() {
  try {
    const [schema, settings, health] = await Promise.all([API.settingsSchema(), API.getSettings(), API.health()]);
    const checks = health.checks || {};
    const schemaMap = Object.fromEntries(schema.map(item => [item.key, item]));
    const panels = [
      panel('OCR', 'ocr', checks.ocr?.status, 'btn-test-ocr', 'btn-save-ocr', GROUPS.ocr, settings, schemaMap),
      panel('Vision', 'vision', checks.vision?.status, 'btn-test-vision', 'btn-save-vision', GROUPS.vision, settings, schemaMap),
      panel('文本 AI', 'text_ai', checks.text_ai?.status, 'btn-test-text_ai', 'btn-save-text_ai', GROUPS.text_ai, settings, schemaMap),
      panel('飞书', 'feishu', checks.lark_cli?.status, 'btn-test-feishu', 'btn-save-feishu', GROUPS.feishu, settings, schemaMap),
      panel('WeRSS', 'werss', checks.we_mp_rss?.status, 'btn-test-werss', 'btn-save-werss', GROUPS.werss, settings, schemaMap),
    ];
    document.getElementById('integration-panels').innerHTML = panels.join('');

    [['ocr', API.testOcr], ['vision', API.testVision], ['text_ai', API.testTextAi], ['feishu', API.testFeishu], ['werss', API.testWeMpRss]].forEach(([name, fn]) => {
      document.getElementById(`btn-test-${name}`)?.addEventListener('click', () => testProvider(name, fn));
      document.getElementById(`btn-save-${name}`)?.addEventListener('click', () => saveGroup(name));
    });
  } catch (e) {
    toast(`加载集成配置失败: ${e.message}`, 'error');
  }
}

function panel(title, group, status, testId, saveId, keys, settings, schemaMap) {
  return `
    <div class="settings-section">
      <div class="settings-section-header">
        <div>
          <h3 class="settings-section-title">${esc(title)}</h3>
          <div class="text-sm text-muted">${statusBadge(status || 'unknown')}</div>
        </div>
        <div class="flex gap-2">
          <button class="btn btn-ghost btn-sm" id="${testId}">测试</button>
          <button class="btn btn-primary btn-sm" id="${saveId}">保存</button>
        </div>
      </div>
      <div class="settings-section-body">
        ${keys.map(key => renderField(group, schemaMap[key], settings[key])).join('')}
        <div id="test-result-${group}"></div>
      </div>
    </div>`;
}

function renderField(group, schema, value) {
  if (!schema) return '';
  const displayValue = typeof value === 'object' && value?.configured !== undefined ? '' : (value ?? schema.default ?? '');
  const isSecret = schema.is_secret;
  const fieldId = `${group}-${schema.key}`;
  const maskedHint = isSecret && value?.configured ? `当前: ${esc(value.masked_value)}` : '';
  if (schema.type === 'select') {
    return `<div class="form-group">
      <label class="form-label">${esc(schema.label)}</label>
      <select class="form-select" data-group="${esc(group)}" data-key="${esc(schema.key)}" id="${fieldId}">
        ${(schema.options || []).map(option => `<option value="${esc(option)}" ${displayValue === option ? 'selected' : ''}>${esc(option)}</option>`).join('')}
      </select>
      ${schema.help ? `<div class="form-hint">${esc(schema.help)}</div>` : ''}
    </div>`;
  }
  if (schema.type === 'boolean') {
    return `<div class="form-group">
      <label class="form-label">${esc(schema.label)}</label>
      <select class="form-select" data-group="${esc(group)}" data-key="${esc(schema.key)}" id="${fieldId}">
        <option value="true" ${displayValue === true ? 'selected' : ''}>是</option>
        <option value="false" ${displayValue !== true ? 'selected' : ''}>否</option>
      </select>
      ${schema.help ? `<div class="form-hint">${esc(schema.help)}</div>` : ''}
    </div>`;
  }
  const inputType = isSecret ? 'password' : (schema.type === 'integer' || schema.type === 'number' ? 'number' : 'text');
  return `<div class="form-group">
    <label class="form-label">${esc(schema.label)}</label>
    <div class="secret-row">
      <input class="form-input" data-group="${esc(group)}" data-key="${esc(schema.key)}" type="${inputType}" id="${fieldId}" value="${esc(displayValue)}" placeholder="${isSecret ? '留空表示保持不变' : ''}">
      ${isSecret ? `<button type="button" class="btn btn-ghost btn-sm" data-toggle-secret="${fieldId}">显示</button>` : ''}
    </div>
    ${maskedHint ? `<div class="form-hint">${maskedHint}</div>` : ''}
    ${schema.help ? `<div class="form-hint">${esc(schema.help)}</div>` : ''}
  </div>`;
}

async function saveGroup(group) {
  const updates = {};
  const clearSecrets = [];
  document.querySelectorAll(`[data-group="${group}"][data-key]`).forEach(el => {
    const key = el.dataset.key;
    let value = el.value;
    if (el.tagName === 'SELECT' && (value === 'true' || value === 'false')) value = value === 'true';
    if (el.type === 'number' && value !== '') value = value.includes('.') ? parseFloat(value) : parseInt(value, 10);
    if (el.type === 'password' && value === '') return;
    updates[key] = value;
  });
  try {
    const result = await API.updateSettings({ ...updates, clear_secrets: clearSecrets });
    reportSaveResult(result);
    await loadPanels();
  } catch (e) {
    toast(`保存失败: ${e.message}`, 'error');
  }
}

async function testProvider(group, fn) {
  const resultEl = document.getElementById(`test-result-${group}`);
  resultEl.innerHTML = '<div class="test-result">测试中...</div>';
  try {
    const result = await fn();
    resultEl.innerHTML = `<div class="test-result ${result.ok ? 'ok' : 'error'}">${esc(result.message)}${result.latency_ms ? ` (${result.latency_ms}ms)` : ''}</div>`;
  } catch (e) {
    resultEl.innerHTML = `<div class="test-result error">测试失败: ${esc(e.message)}</div>`;
  }
}

async function applyPreset(preset) {
  const presets = {
    balanced: { ocr_provider: 'rapid', vision_api_provider: 'openai_compatible', text_ai_provider: 'disabled' },
    'api-heavy': { ocr_provider: 'openai_compatible', vision_api_provider: 'openai_compatible', text_ai_provider: 'disabled' },
    budget: { ocr_provider: 'rapid', vision_api_provider: 'textai', text_ai_provider: 'openai_compatible' },
  };
  try {
    const result = await API.updateSettings(presets[preset]);
    reportSaveResult(result);
    await loadPanels();
  } catch (e) {
    toast(`应用预设失败: ${e.message}`, 'error');
  }
}

function reportSaveResult(result) {
  if (result.applied?.length) toast(`已应用 ${result.applied.length} 项配置`, 'success');
  if (result.reloaded?.length) toast(`已热加载: ${result.reloaded.join(', ')}`, 'info');
  if (result.rescheduled?.length) toast(`已重建任务: ${result.rescheduled.join(', ')}`, 'info');
  if (result.restart_required?.length) toast(`需要重启: ${result.restart_required.join(', ')}`, 'warning');
  if (result.errors?.length) result.errors.forEach(item => toast(`${item.key}: ${item.error}`, 'error'));
}

document.addEventListener('click', event => {
  const button = event.target.closest('[data-toggle-secret]');
  if (!button) return;
  const input = document.getElementById(button.dataset.toggleSecret);
  if (!input) return;
  input.type = input.type === 'password' ? 'text' : 'password';
  button.textContent = input.type === 'password' ? '显示' : '隐藏';
});
