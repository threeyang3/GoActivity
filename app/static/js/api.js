/* API Client — GoActivity */
const API = {
  _token: null,

  setToken(token) {
    this._token = token;
    if (token) localStorage.setItem('admin_token', token);
    else localStorage.removeItem('admin_token');
  },

  getToken() {
    if (!this._token) this._token = localStorage.getItem('admin_token');
    return this._token;
  },

  async request(url, options = {}) {
    const headers = { 'Content-Type': 'application/json', ...options.headers };
    const token = this.getToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const response = await fetch(url, { ...options, headers });

    if (!response.ok) {
      let detail = `HTTP ${response.status}`;
      try {
        const body = await response.json();
        detail = body.detail || body.message || JSON.stringify(body);
      } catch {}
      const err = new Error(detail);
      err.status = response.status;
      throw err;
    }
    return response.json();
  },

  get(url) { return this.request(url); },
  post(url, body) { return this.request(url, { method: 'POST', body: JSON.stringify(body) }); },
  put(url, body) { return this.request(url, { method: 'PUT', body: JSON.stringify(body) }); },
  del(url) { return this.request(url, { method: 'DELETE' }); },

  // Health
  health() { return this.get('/health'); },
  diagnostics() { return this.get('/diagnostics/config'); },

  // Events
  events(params = {}) {
    const qs = new URLSearchParams(params).toString();
    return this.get(`/events${qs ? '?' + qs : ''}`);
  },
  editEvent(id, data) { return this.put(`/events/${id}`, data); },
  batchEvents(action, ids) { return this.post('/events/batch', { action, event_ids: ids }); },
  extractEvent(id) { return this.post(`/events/${id}/extract`); },
  syncFeishu(id) { return this.post(`/events/${id}/sync-feishu`); },
  keepEvent(id, value) { return this.post(`/events/${id}/keep?value=${value}`); },
  participateEvent(id, value) { return this.post(`/events/${id}/participate?value=${value}`); },
  archiveEvent(id) { return this.post(`/events/${id}/archive`); },
  unarchiveEvent(id) { return this.post(`/events/${id}/unarchive`); },

  // Accounts
  accounts(params = {}) {
    const qs = new URLSearchParams(params).toString();
    return this.get(`/accounts${qs ? '?' + qs : ''}`);
  },
  accountAuthorization() { return this.get('/accounts/authorization'); },
  addAccount(body) { return this.post('/accounts', body); },
  deleteAccount(id) { return this.del(`/accounts/${id}`); },
  updateAccount(id) { return this.post(`/accounts/update/${id}`); },
  searchAccounts(kw) { return this.get(`/accounts/search/${encodeURIComponent(kw)}`); },

  // Sync
  syncArticles(limit = 20) { return this.post(`/sync/we-mp-rss/articles?limit=${limit}`); },
  syncLogs() { return this.get('/sync/logs'); },
  syncRuns(params = {}) {
    const qs = new URLSearchParams(params).toString();
    return this.get(`/sync/runs${qs ? '?' + qs : ''}`);
  },

  // Reports
  dailyReport(send = false) { return this.post(`/reports/daily?send_to_feishu=${send}`); },
  weeklyReport(send = false) { return this.post(`/reports/weekly?send_to_feishu=${send}`); },

  // Automation
  autoSyncStatus() { return this.get('/sync/status'); },
  triggerAutoSync() { return this.post('/sync/auto'); },
  botStatus() { return this.get('/bot/status'); },
  automationStatus() { return this.get('/automation/status'); },
  automationAccountsHealth() { return this.get('/automation/accounts-health'); },
  feishuReconcile() { return this.get('/automation/feishu-reconcile'); },
  repairFeishuReconcile() { return this.post('/automation/feishu-reconcile'); },
  collectPriorityAccounts() { return this.post('/automation/collect-priority'); },

  // Settings
  settingsSchema() { return this.get('/settings/schema'); },
  getSettings() { return this.get('/settings'); },
  updateSettings(data) { return this.put('/settings', data); },
  resetSettings(keys) { return this.post('/settings/reset', { keys }); },
  reloadSettings() { return this.post('/settings/reload'); },
  testOcr() { return this.post('/settings/test/ocr'); },
  testVision() { return this.post('/settings/test/vision'); },
  testTextAi() { return this.post('/settings/test/text-ai'); },
  testFeishu() { return this.post('/settings/test/feishu'); },
  testWeMpRss() { return this.post('/settings/test/we-mp-rss'); },

  // Dashboard
  dashboardStats() { return this.get('/dashboard/stats'); },
  dashboardToday() { return this.get('/dashboard/today'); },
  dashboardPending() { return this.get('/dashboard/pending'); },
  dashboardPipelineStatus() { return this.get('/dashboard/pipeline-status'); },
  dashboardAccuracy() { return this.get('/dashboard/accuracy'); },
  dashboardAccountsHealth() { return this.get('/dashboard/accounts-health'); },
  dashboardFeishuLink() { return this.get('/dashboard/feishu-link'); },

  // Setup
  setupFeishuViews() { return this.post('/setup/feishu-views'); },
};

export default API;
