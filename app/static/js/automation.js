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
        <div class="schedule-card">
          <div class="schedule-header"><h3 class="schedule-title">重点公众号采集</h3><div id="account-health-status"></div></div>
          <div class="schedule-meta" id="account-health-meta">加载中...</div>
          <button class="btn btn-secondary btn-sm mt-4" id="btn-collect-priority">立即采集</button>
        </div>
        <div class="schedule-card">
          <div class="schedule-header"><h3 class="schedule-title">飞书数据对账</h3><div id="reconcile-status"></div></div>
          <div class="schedule-meta" id="reconcile-meta">加载中...</div>
          <button class="btn btn-secondary btn-sm mt-4" id="btn-reconcile">检测并修复缺失记录</button>
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
    document.getElementById('btn-collect-priority').onclick = async () => {
      try { const r = await API.collectPriorityAccounts(); toast(`已触发 ${r.triggered.length} 个公众号`, 'success'); await loadAutomation(); }
      catch (e) { toast(`采集触发失败: ${e.message}`, 'error'); }
    };
    document.getElementById('btn-reconcile').onclick = async () => {
      try { const r = await API.repairFeishuReconcile(); toast(`修复 ${r.repaired_event_ids.length} 条缺失记录`, 'success'); await loadAutomation(); }
      catch (e) { toast(`飞书对账失败: ${e.message}`, 'error'); }
    };
  }
});

async function loadAutomation() {
  try {
    const [syncStatus, botStatus, settings, runs, accountsHealth, reconcile] = await Promise.all([
      API.autoSyncStatus().catch(() => null),
      API.botStatus().catch(() => null),
      API.getSettings().catch(() => ({})),
      API.syncRuns({ limit: 10 }).catch(() => []),
      API.automationAccountsHealth().catch(() => []),
      API.feishuReconcile().catch(() => null),
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

    const staleAccounts = accountsHealth.filter(item => item.status === 'stale');
    document.getElementById('account-health-meta').innerHTML =
      `主动采集: ${esc(settings.priority_collection_cron || '未启用')}<br>` +
      `已监测: ${accountsHealth.length} 个 · 超过 SLA: ${staleAccounts.length} 个` +
      (staleAccounts.length ? `<br><span class="text-danger">${staleAccounts.slice(0, 4).map(item => esc(item.mp_name)).join('、')}</span>` : '');
    document.getElementById('account-health-status').innerHTML = statusBadge(staleAccounts.length ? 'degraded' : 'ok');

    if (reconcile) {
      const issueCount = reconcile.missing_record_ids.length + reconcile.field_drift_event_ids.length + reconcile.missing_attachment_event_ids.length;
      document.getElementById('reconcile-meta').innerHTML =
        `本地/飞书/匹配: ${reconcile.local_records}/${reconcile.remote_records}/${reconcile.matched_records ?? '—'}<br>` +
        `缺失 ${reconcile.missing_record_ids.length} · 字段漂移 ${reconcile.field_drift_event_ids.length} · 附件缺失 ${reconcile.missing_attachment_event_ids.length}` +
        (reconcile.skipped_terminal_records ? `<br>已忽略 ${reconcile.skipped_terminal_records} 条隐藏或归档记录` : '');
      document.getElementById('reconcile-status').innerHTML = statusBadge(issueCount ? 'degraded' : 'ok');
      const reconcileButton = document.getElementById('btn-reconcile');
      reconcileButton.disabled = reconcile.safe_to_repair === false;
      reconcileButton.title = reconcile.safe_to_repair === false ? '本地与飞书记录无交集，已禁用自动修复' : '';
    } else {
      document.getElementById('reconcile-meta').textContent = '当前无法读取飞书记录';
      document.getElementById('reconcile-status').innerHTML = statusBadge('error');
    }

    // Recent runs
    const runsContainer = document.getElementById('recent-runs');
    if (runs.length) {
      runsContainer.innerHTML = `<table class="data-table"><thead><tr><th>来源</th><th>状态</th><th>远端扫描</th><th>新增文章</th><th>飞书写入</th><th>时间</th></tr></thead><tbody>
        ${runs.map(r => {
          let metrics = {};
          try { metrics = JSON.parse(r.result_preview || '[]')[0] || {}; } catch {}
          return `<tr><td>${esc(r.source)}</td><td>${esc(r.status)}</td><td>${esc(metrics.remote_scanned ?? '—')}</td><td>${esc(metrics.articles_created ?? r.imported_count)}</td><td>${esc(metrics.events_synced ?? '—')}</td><td>${timeAgo(r.started_at)}</td></tr>`;
        }).join('')}</tbody></table>`;
    } else {
      runsContainer.innerHTML = '<div class="text-muted">暂无任务记录</div>';
    }
  } catch (e) {
    toast(`加载自动化状态失败: ${e.message}`, 'error');
  }
}
