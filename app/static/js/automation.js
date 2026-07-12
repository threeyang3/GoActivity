/* Automation Page — GoActivity */
import API from './api.js';
import { registerPage, toast, esc, timeAgo, statusBadge } from './app.js';

registerPage('automation', {
  init() {},
  render(body) {
    body.innerHTML = `
      <div class="grid gap-4" style="grid-template-columns: repeat(auto-fill, minmax(340px, 1fr))">
        <div class="schedule-card" id="auto-sync-card">
          <div class="schedule-header"><h3 class="schedule-title">自动同步</h3><div id="auto-sync-toggle" class="toggle active"></div></div>
          <div class="schedule-meta" id="auto-sync-meta">加载中...</div>
          <button class="btn btn-primary btn-sm mt-4" id="btn-trigger-sync">立即执行</button>
        </div>
        <div class="schedule-card" id="daily-report-card">
          <div class="schedule-header"><h3 class="schedule-title">日报</h3><div id="daily-toggle" class="toggle active"></div></div>
          <div class="schedule-meta" id="daily-meta">加载中...</div>
          <button class="btn btn-secondary btn-sm mt-4" id="btn-send-daily">立即发送</button>
        </div>
        <div class="schedule-card" id="weekly-report-card">
          <div class="schedule-header"><h3 class="schedule-title">周报</h3><div id="weekly-toggle" class="toggle active"></div></div>
          <div class="schedule-meta" id="weekly-meta">加载中...</div>
          <button class="btn btn-secondary btn-sm mt-4" id="btn-send-weekly">立即发送</button>
        </div>
        <div class="schedule-card" id="bot-card">
          <div class="schedule-header"><h3 class="schedule-title">飞书机器人</h3><div id="bot-status"></div></div>
          <div class="schedule-meta" id="bot-meta">加载中...</div>
        </div>
      </div>
      <div class="card mt-4">
        <div class="card-header"><h3 class="card-title">最近任务</h3></div>
        <div class="card-body" id="recent-runs"><div class="text-muted">加载中...</div></div>
      </div>`;

    loadAutomation();
    document.getElementById('btn-trigger-sync').onclick = async () => {
      try { const r = await API.triggerAutoSync(); toast(`同步: ${r.status}`, 'info'); }
      catch (e) { toast(`同步失败: ${e.message}`, 'error'); }
    };
    document.getElementById('btn-send-daily').onclick = async () => {
      try { await API.dailyReport(true); toast('日报已发送', 'success'); }
      catch (e) { toast(`发送失败: ${e.message}`, 'error'); }
    };
    document.getElementById('btn-send-weekly').onclick = async () => {
      try { await API.weeklyReport(true); toast('周报已发送', 'success'); }
      catch (e) { toast(`发送失败: ${e.message}`, 'error'); }
    };
  }
});

async function loadAutomation() {
  try {
    const [syncStatus, botStatus, settings, runs] = await Promise.all([
      API.autoSyncStatus().catch(() => null),
      API.botStatus().catch(() => null),
      API.getSettings().catch(() => ({})),
      API.syncRuns({ limit: 10 }).catch(() => []),
    ]);

    // Auto sync
    const syncMeta = document.getElementById('auto-sync-meta');
    if (syncStatus) {
      syncMeta.innerHTML = `Cron: ${esc(settings.auto_sync_cron || '0 * * * *')}<br>状态: ${esc(syncStatus.status || '未知')}`;
    }

    // Daily report
    const dailyMeta = document.getElementById('daily-meta');
    dailyMeta.innerHTML = `Cron: ${esc(settings.feishu_report_daily_cron || '0 9 * * *')}<br>状态: ${settings.feishu_report_daily_enabled ? '已启用' : '已禁用'}`;
    document.getElementById('daily-toggle').classList.toggle('active', !!settings.feishu_report_daily_enabled);

    // Weekly report
    const weeklyMeta = document.getElementById('weekly-meta');
    weeklyMeta.innerHTML = `Cron: ${esc(settings.feishu_report_weekly_cron || '0 9 * * 1')}<br>状态: ${settings.feishu_report_weekly_enabled ? '已启用' : '已禁用'}`;
    document.getElementById('weekly-toggle').classList.toggle('active', !!settings.feishu_report_weekly_enabled);

    // Bot
    const botMeta = document.getElementById('bot-meta');
    const botStatusEl = document.getElementById('bot-status');
    if (botStatus) {
      botMeta.innerHTML = `状态: ${botStatus.running ? '运行中' : '未运行'}`;
      botStatusEl.innerHTML = statusBadge(botStatus.running ? 'ok' : 'disabled');
    }

    // Recent runs
    const runsContainer = document.getElementById('recent-runs');
    if (runs.length) {
      runsContainer.innerHTML = `<table class="data-table"><thead><tr><th>来源</th><th>状态</th><th>导入</th><th>时间</th></tr></thead><tbody>
        ${runs.map(r => `<tr><td>${esc(r.source)}</td><td>${esc(r.status)}</td><td>${esc(r.imported_count)}</td><td>${timeAgo(r.started_at)}</td></tr>`).join('')}</tbody></table>`;
    } else {
      runsContainer.innerHTML = '<div class="text-muted">暂无任务记录</div>';
    }
  } catch (e) {
    toast(`加载自动化状态失败: ${e.message}`, 'error');
  }
}
