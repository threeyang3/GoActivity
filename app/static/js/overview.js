/* Overview Page — GoActivity */
import API from './api.js';
import { registerPage, toast, esc, timeAgo, statusBadge } from './app.js';

registerPage('overview', {
  init() {},
  render(body) {
    body.innerHTML = `
      <div class="metric-grid mb-4" id="overview-metrics"><div class="text-muted">加载中...</div></div>
      <div class="overview-grid mb-4" id="health-cards"><div class="text-muted">加载中...</div></div>
      <div class="card mb-4">
        <div class="card-header"><h3 class="card-title">快捷操作</h3></div>
        <div class="card-body flex gap-2 flex-wrap">
          <button class="btn btn-primary" id="btn-sync-now">立即同步</button>
          <button class="btn btn-secondary" id="btn-daily-report">发送日报</button>
          <button class="btn btn-secondary" id="btn-weekly-report">发送周报</button>
          <button class="btn btn-secondary" id="btn-feishu-views">同步飞书视图</button>
        </div>
      </div>
      <div class="dashboard-two-col">
        <div class="card">
          <div class="card-header"><h3 class="card-title">今日活动</h3></div>
          <div class="card-body" id="today-events"><div class="text-muted">加载中...</div></div>
        </div>
        <div class="card">
          <div class="card-header"><h3 class="card-title">未来 7 天</h3></div>
          <div class="card-body" id="upcoming-events"><div class="text-muted">加载中...</div></div>
        </div>
      </div>
      <div class="dashboard-two-col mt-4">
        <div class="card">
          <div class="card-header"><h3 class="card-title">关键异常与待处理</h3></div>
          <div class="card-body" id="pending-panel"><div class="text-muted">加载中...</div></div>
        </div>
        <div class="card">
          <div class="card-header"><h3 class="card-title">最近同步</h3></div>
          <div class="card-body" id="recent-sync"><div class="text-muted">加载中...</div></div>
        </div>
      </div>`;

    loadOverview();

    document.getElementById('btn-sync-now').onclick = async () => {
      try { const r = await API.triggerAutoSync(); toast(`同步状态: ${r.status}`, 'info'); }
      catch (e) { toast(`同步失败: ${e.message}`, 'error'); }
    };
    document.getElementById('btn-daily-report').onclick = async () => {
      try { await API.dailyReport(true); toast('日报已发送', 'success'); }
      catch (e) { toast(`发送失败: ${e.message}`, 'error'); }
    };
    document.getElementById('btn-weekly-report').onclick = async () => {
      try { await API.weeklyReport(true); toast('周报已发送', 'success'); }
      catch (e) { toast(`发送失败: ${e.message}`, 'error'); }
    };
    document.getElementById('btn-feishu-views').onclick = async () => {
      try { const r = await API.setupFeishuViews(); toast(`飞书视图已处理: 创建 ${r.created}, 更新 ${r.updated || 0}`, 'success'); }
      catch (e) { toast(`设置失败: ${e.message}`, 'error'); }
    };
  }
});

async function loadOverview() {
  try {
    const [health, stats, today, pending, runs, pipeline] = await Promise.all([
      API.health(),
      API.dashboardStats(),
      API.dashboardToday(),
      API.dashboardPending(),
      API.syncRuns({ limit: 5 }),
      API.dashboardPipelineStatus(),
    ]);
    renderMetrics(stats, pipeline);
    renderHealth(health);
    renderToday(today);
    renderPending(pending, pipeline);
    renderRecentSync(runs, stats.latest_sync);
  } catch (e) {
    toast(`加载总览失败: ${e.message}`, 'error');
  }
}

function renderMetrics(stats, pipeline) {
  const events = stats.events || {};
  const metrics = [
    ['活跃活动', events.active ?? 0, `总计 ${events.total ?? 0}`],
    ['待处理', events.review ?? 0, `待同步 ${pipeline.pending_sync_count ?? 0}`],
    ['同步失败', events.failed ?? 0, pipeline.last_sync?.status ? `最近同步 ${pipeline.last_sync.status}` : '暂无同步'],
    ['最近入库文章', pipeline.total_articles ?? 0, pipeline.latest_article_mp_name || '暂无来源'],
  ];
  document.getElementById('overview-metrics').innerHTML = metrics.map(([label, value, sub]) => `
    <div class="metric-card">
      <div class="metric-label">${esc(label)}</div>
      <div class="metric-value">${esc(value)}</div>
      <div class="metric-sub">${esc(sub)}</div>
    </div>`).join('');
}

function renderHealth(health) {
  const checks = health.checks || {};
  const items = [
    { label: '整体状态', status: health.status, detail: '服务总览' },
    { label: '数据库', status: checks.database?.status, detail: checks.database?.detail || '主存储' },
    { label: 'WeRSS', status: checks.we_mp_rss?.status, detail: checks.we_mp_rss?.latency_ms ? `${checks.we_mp_rss.latency_ms}ms` : '采集链路' },
    { label: '自动同步', status: checks.auto_sync_scheduler?.status, detail: '调度器' },
    { label: '报告任务', status: checks.report_scheduler?.status, detail: '日报 / 周报' },
    { label: '飞书机器人', status: checks.bot_consumer?.status, detail: '会话入口' },
  ];
  document.getElementById('health-cards').innerHTML = items.map(i => `
    <div class="status-card">
      <div class="status-card-icon ${i.status || 'unknown'}"><span class="status-dot status-${i.status || 'unknown'}"></span></div>
      <div>
        <div class="status-card-label">${esc(i.label)}</div>
        <div class="status-card-value">${esc(i.status || '未知')}</div>
        <div class="status-card-detail">${esc(i.detail)}</div>
      </div>
    </div>`).join('');
}

function renderToday(data) {
  const todayContainer = document.getElementById('today-events');
  const upcomingContainer = document.getElementById('upcoming-events');
  const todayItems = data.today || [];
  const upcomingItems = data.upcoming || [];

  todayContainer.innerHTML = renderEventList(
    todayItems,
    upcomingItems.length ? `今天没有活动，接下来 7 天有 ${upcomingItems.length} 场可关注活动` : '今天没有活动记录'
  );
  upcomingContainer.innerHTML = renderEventList(upcomingItems, '未来 7 天暂无活动');

  todayContainer.classList.toggle('compact-empty', todayItems.length === 0);
  upcomingContainer.classList.toggle('compact-empty', upcomingItems.length === 0);
}

function renderEventList(items = [], emptyText) {
  if (!items.length) return `<div class="empty-inline empty-panel">${esc(emptyText)}</div>`;
  return `<div class="mini-list">${items.map(item => `
    <div class="mini-list-item">
      <div class="mini-list-title">${esc(item.title || '(无标题)')}</div>
      <div class="mini-list-meta">${esc(item.start_time || '时间待补充')} · ${esc(item.location || '地点待补充')}</div>
    </div>`).join('')}</div>`;
}

function renderPending(pending, pipeline) {
  const blocks = [
    ['低置信度', pending.low_confidence?.count || 0],
    ['同步失败', pending.failed_sync?.count || 0],
    ['待同步', pending.pending_sync?.count || 0],
    ['图片重试', pending.needs_retry?.count || 0],
  ];
  const warnings = [];
  if (pipeline.article_stale_warning) warnings.push(`最近文章已 ${pipeline.article_stale_days} 天未更新`);
  if (pipeline.last_sync?.status && pipeline.last_sync.status !== 'success') warnings.push(`最近同步状态: ${pipeline.last_sync.status}`);
  document.getElementById('pending-panel').innerHTML = `
    <div class="metric-grid compact mb-3">${blocks.map(([label, value]) => `
      <div class="metric-card compact">
        <div class="metric-label">${esc(label)}</div>
        <div class="metric-value">${esc(value)}</div>
      </div>`).join('')}</div>
    ${warnings.length ? `<div class="notice-list">${warnings.map(item => `<div class="notice warning">${esc(item)}</div>`).join('')}</div>` : '<div class="empty-inline">暂无关键异常</div>'}`;
}

function renderRecentSync(runs = [], latestSync) {
  const container = document.getElementById('recent-sync');
  if (!runs.length) {
    container.innerHTML = '<div class="empty-inline">暂无同步记录</div>';
    return;
  }
  container.innerHTML = `
    ${latestSync ? `<div class="mb-3">最近一次: ${statusBadge(latestSync.status)} <span class="text-muted">${esc(timeAgo(latestSync.started_at))}</span></div>` : ''}
    <table class="data-table"><thead><tr><th>来源</th><th>状态</th><th>导入</th><th>时间</th></tr></thead><tbody>
      ${runs.map(r => `<tr>
        <td>${esc(r.source)}</td>
        <td>${esc(r.status)}</td>
        <td>${esc(r.imported_count)}</td>
        <td>${timeAgo(r.started_at)}</td>
      </tr>`).join('')}</tbody></table>`;
}
