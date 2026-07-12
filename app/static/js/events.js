/* Events Page — GoActivity */
import API from './api.js';
import { registerPage, toast, esc, timeAgo, eventStatusBadge, categoryBadge, openModal, closeModal } from './app.js';

let currentPage = 1;
let currentStatus = '';
let selectedIds = new Set();

registerPage('events', {
  init() {},
  render(body) {
    body.innerHTML = `
      <div class="events-toolbar">
        <input type="text" class="form-input" id="event-search" placeholder="搜索活动...">
        <select class="form-select" id="event-status-filter">
          <option value="">活跃活动</option>
          <option value="all">全部状态</option>
          <option value="pending">待处理</option>
          <option value="extracted">已抽取</option>
          <option value="synced">已同步</option>
          <option value="archived">已归档</option>
          <option value="filtered_out">已过滤</option>
        </select>
        <button class="btn btn-secondary btn-sm" id="btn-refresh-events">刷新</button>
      </div>
      <div id="batch-bar" class="batch-bar hidden">
        <span id="batch-count">0 项已选</span>
        <button class="btn btn-primary btn-sm" data-action="sync">同步飞书</button>
        <button class="btn btn-secondary btn-sm" data-action="archive">归档</button>
        <button class="btn btn-secondary btn-sm" data-action="keep">置顶</button>
        <button class="btn btn-ghost btn-sm" id="btn-clear-selection">取消选择</button>
      </div>
      <div class="card">
        <div class="card-body" id="events-table"><div class="text-muted">加载中...</div></div>
      </div>
      <div class="flex items-center justify-between mt-4" id="events-pagination"></div>`;

    loadEvents();
    document.getElementById('btn-refresh-events').onclick = () => loadEvents();
    document.getElementById('event-status-filter').onchange = (e) => {
      currentStatus = e.target.value;
      currentPage = 1;
      loadEvents();
    };
    document.getElementById('event-search').oninput = debounce(() => { currentPage = 1; loadEvents(); }, 300);
    document.getElementById('btn-clear-selection').onclick = () => { selectedIds.clear(); updateBatchBar(); loadEvents(); };
    document.querySelectorAll('#batch-bar [data-action]').forEach(btn => {
      btn.onclick = () => batchAction(btn.dataset.action);
    });
  }
});

function debounce(fn, ms) {
  let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

async function loadEvents() {
  const container = document.getElementById('events-table');
  const search = document.getElementById('event-search')?.value || '';
  try {
    const params = { page: currentPage, page_size: 20 };
    if (currentStatus && currentStatus !== 'all') params.status = currentStatus;
    const events = await API.events(params);
    if (!events.length) { container.innerHTML = '<div class="empty-state"><p class="empty-state-title">暂无活动</p></div>'; return; }
    container.innerHTML = `<table class="data-table"><thead><tr>
      <th><input type="checkbox" id="select-all" aria-label="全选"></th>
      <th>活动</th><th>分类</th><th>状态</th><th>时间</th><th>操作</th>
    </tr></thead><tbody>
      ${events.map(e => `<tr class="event-row" data-id="${esc(e.event_id)}">
        <td><input type="checkbox" class="event-checkbox" value="${esc(e.event_id)}" ${selectedIds.has(e.event_id) ? 'checked' : ''}></td>
        <td>
          <div class="event-title">${esc(e.title)}</div>
          <div class="event-meta">${esc(e.location)}${e.speaker ? ' · ' + esc(e.speaker) : ''}</div>
        </td>
        <td>${categoryBadge(e.category_1)}</td>
        <td>${eventStatusBadge(e.status)}</td>
        <td class="text-sm text-muted">${esc(e.start_time) || '—'}</td>
        <td>
          <div class="flex gap-2">
            <button class="btn btn-ghost btn-sm" onclick="window._editEvent('${esc(e.event_id)}')">编辑</button>
            <button class="btn btn-ghost btn-sm" onclick="window._syncEvent('${esc(e.event_id)}')">同步</button>
          </div>
        </td>
      </tr>`).join('')}</tbody></table>`;

    // Event listeners
    document.getElementById('select-all').onchange = (e) => {
      document.querySelectorAll('.event-checkbox').forEach(cb => {
        cb.checked = e.target.checked;
        const id = cb.value;
        if (e.target.checked) selectedIds.add(id); else selectedIds.delete(id);
      });
      updateBatchBar();
    };
    document.querySelectorAll('.event-checkbox').forEach(cb => {
      cb.onchange = () => {
        if (cb.checked) selectedIds.add(cb.value); else selectedIds.delete(cb.value);
        updateBatchBar();
      };
    });
  } catch (e) {
    container.innerHTML = `<div class="text-muted">加载失败: ${esc(e.message)}</div>`;
  }
}

function updateBatchBar() {
  const bar = document.getElementById('batch-bar');
  const count = document.getElementById('batch-count');
  if (selectedIds.size > 0) {
    bar.classList.remove('hidden');
    count.textContent = `${selectedIds.size} 项已选`;
  } else {
    bar.classList.add('hidden');
  }
}

async function batchAction(action) {
  if (!selectedIds.size) return;
  try {
    const r = await API.batchEvents(action, [...selectedIds]);
    toast(`操作完成: 成功 ${r.processed}, 失败 ${r.failed}`, r.failed ? 'warning' : 'success');
    selectedIds.clear();
    updateBatchBar();
    loadEvents();
  } catch (e) { toast(`批量操作失败: ${e.message}`, 'error'); }
}

window._editEvent = async function(id) {
  try {
    const events = await API.events({ status: 'all' });
    const event = events.find(e => e.event_id === id);
    if (!event) { toast('活动未找到', 'error'); return; }
    openModal('编辑活动', `
      <div class="form-group"><label class="form-label">标题</label><input class="form-input" id="edit-title" value="${esc(event.title)}"></div>
      <div class="form-group"><label class="form-label">开始时间</label><input class="form-input" id="edit-start" value="${esc(event.start_time)}"></div>
      <div class="form-group"><label class="form-label">结束时间</label><input class="form-input" id="edit-end" value="${esc(event.end_time)}"></div>
      <div class="form-group"><label class="form-label">地点</label><input class="form-input" id="edit-location" value="${esc(event.location)}"></div>
      <div class="form-group"><label class="form-label">分类</label><input class="form-input" id="edit-cat1" value="${esc(event.category_1)}"></div>
      <div class="form-group"><label class="form-label">主讲人</label><input class="form-input" id="edit-speaker" value="${esc(event.speaker)}"></div>
      <div class="form-group"><label class="form-label">主办方</label><input class="form-input" id="edit-organizer" value="${esc(event.organizer)}"></div>
      <div class="form-group"><label class="form-label">摘要</label><textarea class="form-textarea" id="edit-summary">${esc(event.summary)}</textarea></div>`,
      `<button class="btn btn-secondary" onclick="window._closeModal()">取消</button>
       <button class="btn btn-primary" id="btn-save-event">保存</button>`);
    document.getElementById('btn-save-event').onclick = async () => {
      try {
        await API.editEvent(id, {
          title: document.getElementById('edit-title').value,
          start_time: document.getElementById('edit-start').value,
          end_time: document.getElementById('edit-end').value,
          location: document.getElementById('edit-location').value,
          category_1: document.getElementById('edit-cat1').value,
          speaker: document.getElementById('edit-speaker').value,
          organizer: document.getElementById('edit-organizer').value,
          summary: document.getElementById('edit-summary').value,
        });
        toast('活动已更新', 'success');
        closeModal();
        loadEvents();
      } catch (e) { toast(`保存失败: ${e.message}`, 'error'); }
    };
  } catch (e) { toast(`加载失败: ${e.message}`, 'error'); }
};

window._syncEvent = async function(id) {
  try {
    const r = await API.syncFeishu(id);
    toast(`同步状态: ${r.status}`, r.status === 'synced' ? 'success' : 'warning');
    loadEvents();
  } catch (e) { toast(`同步失败: ${e.message}`, 'error'); }
};

window._closeModal = closeModal;
