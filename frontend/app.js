/**
 * T2S Copilot - Clean Light Web Interface with Chat Session History
 */

const STORAGE_KEY = 't2s_copilot_sessions_v1';

let appConfig = { databases: [], models: [] };
let chatSessions = [];
let activeSessionId = null;

// DOM Elements
const sidebar = document.getElementById('sidebar');
const toggleSidebarBtn = document.getElementById('toggleSidebarBtn');
const newChatBtn = document.getElementById('newChatBtn');
const clearAllHistoryBtn = document.getElementById('clearAllHistoryBtn');
const sessionHistoryList = document.getElementById('sessionHistoryList');
const sessionCountBadge = document.getElementById('sessionCountBadge');
const dbSelect = document.getElementById('dbSelect');
const modelSelect = document.getElementById('modelSelect');

// Split-Screen Dual Pane Elements
const workspacePane = document.getElementById('workspacePane');
const workspaceQuestionTitle = document.getElementById('workspaceQuestionTitle');
const workspaceMetaBadge = document.getElementById('workspaceMetaBadge');
const fullscreenWorkspaceBtn = document.getElementById('fullscreenWorkspaceBtn');
const workspaceBody = document.getElementById('workspaceBody');
const workspaceEmptyState = document.getElementById('workspaceEmptyState');
const workspaceDetailContainer = document.getElementById('workspaceDetailContainer');

const questionPane = document.getElementById('questionPane');
const paneSplitter = document.getElementById('paneSplitter');
const questionCountBadge = document.getElementById('questionCountBadge');
const questionList = document.getElementById('questionList');
const questionListEmpty = document.getElementById('questionListEmpty');
const quickCardsContainer = document.getElementById('quickCardsContainer');

const queryForm = document.getElementById('queryForm');
const queryInput = document.getElementById('queryInput');
const sendBtn = document.getElementById('sendBtn');

let activeQuestionId = null;

const MIN_QUESTION_PANE_WIDTH = 300;
const MIN_WORKSPACE_PANE_WIDTH = 380;

function setQuestionPaneWidth(clientX) {
  const container = paneSplitter?.parentElement;
  if (!container) return;

  const rect = container.getBoundingClientRect();
  const maxWidth = rect.width - MIN_WORKSPACE_PANE_WIDTH - paneSplitter.offsetWidth;
  const width = Math.min(Math.max(clientX - rect.left, MIN_QUESTION_PANE_WIDTH), maxWidth);
  container.style.setProperty('--question-pane-width', `${Math.round(width)}px`);
}

function initPaneSplitter() {
  if (!paneSplitter || !questionPane || !workspacePane) return;

  // Danh sách câu hỏi luôn ở cột bên trái/giữa; câu trả lời ở cột bên phải.
  // Sắp lại DOM để bố cục vẫn chính xác ngay cả khi CSS cũ còn trong browser cache.
  const container = paneSplitter.parentElement;
  if (container) {
    container.insertBefore(questionPane, workspacePane);
    container.insertBefore(paneSplitter, workspacePane);
  }

  if (!window.matchMedia('(min-width: 1024px)').matches) return;

  let dragging = false;
  const stopDragging = () => {
    if (!dragging) return;
    dragging = false;
    paneSplitter.classList.remove('is-dragging');
    document.body.classList.remove('is-resizing');
  };

  paneSplitter.addEventListener('pointerdown', event => {
    dragging = true;
    paneSplitter.setPointerCapture?.(event.pointerId);
    paneSplitter.classList.add('is-dragging');
    document.body.classList.add('is-resizing');
    setQuestionPaneWidth(event.clientX);
  });
  paneSplitter.addEventListener('pointermove', event => {
    if (dragging) setQuestionPaneWidth(event.clientX);
  });
  paneSplitter.addEventListener('pointerup', stopDragging);
  paneSplitter.addEventListener('pointercancel', stopDragging);
  paneSplitter.addEventListener('keydown', event => {
    if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
    const current = questionPane.getBoundingClientRect();
    setQuestionPaneWidth(current.right + (event.key === 'ArrowLeft' ? -24 : 24));
    event.preventDefault();
  });
}

function escapeHtml(str) {
  if (typeof str !== 'string') return str;
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function scrollToBottom() {
  if (workspaceBody) {
    workspaceBody.scrollTop = workspaceBody.scrollHeight;
  }
}

// ---------------------------------------------------------------------------
// 1. Quản lý Session & LocalStorage
// ---------------------------------------------------------------------------
function loadSessions() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    chatSessions = raw ? JSON.parse(raw) : [];
  } catch (e) {
    console.error('Lỗi đọc sessions:', e);
    chatSessions = [];
  }
}

function saveSessions() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(chatSessions));
  } catch (e) {
    console.error('Lỗi lưu sessions:', e);
  }
}

function getActiveSession() {
  return chatSessions.find(s => s.id === activeSessionId);
}

function createNewSession(initialTitle = 'Hội thoại mới') {
  const newSession = {
    id: 'sess_' + Date.now(),
    title: initialTitle,
    dbId: dbSelect ? dbSelect.value : 'financial',
    modelId: modelSelect ? modelSelect.value : 'openai/gpt-oss-120b',
    createdAt: Date.now(),
    messages: [], // array of { role: 'user'|'assistant', data: ... }
  };
  chatSessions.unshift(newSession);
  activeSessionId = newSession.id;
  saveSessions();
  renderSidebarSessions();
  loadSessionIntoUI(newSession);
  return newSession;
}

function switchSession(sessionId) {
  activeSessionId = sessionId;
  const sess = getActiveSession();
  if (sess) {
    if (sess.dbId && dbSelect) dbSelect.value = sess.dbId;
    if (sess.modelId && modelSelect) modelSelect.value = sess.modelId;
    loadSessionIntoUI(sess);
    renderSidebarSessions();
  }
}

function deleteSession(sessionId, event) {
  if (event) event.stopPropagation();
  chatSessions = chatSessions.filter(s => s.id !== sessionId);
  saveSessions();
  if (activeSessionId === sessionId) {
    if (chatSessions.length > 0) {
      switchSession(chatSessions[0].id);
    } else {
      createNewSession();
    }
  } else {
    renderSidebarSessions();
  }
}

function clearAllSessions() {
  if (confirm('Bạn có chắc chắn muốn xóa toàn bộ lịch sử trò chuyện?')) {
    chatSessions = [];
    saveSessions();
    createNewSession();
  }
}

function renderSidebarSessions() {
  sessionHistoryList.innerHTML = '';
  sessionCountBadge.textContent = chatSessions.length;

  if (chatSessions.length === 0) {
    sessionHistoryList.innerHTML = `
      <div class="px-2 py-4 text-center text-xs text-slate-400">
        Chưa có lịch sử hội thoại
      </div>
    `;
    return;
  }

  chatSessions.forEach(sess => {
    const item = document.createElement('div');
    const isActive = sess.id === activeSessionId;
    item.className = `session-item ${isActive ? 'active' : ''}`;
    item.innerHTML = `
      <div class="flex items-center gap-2 overflow-hidden flex-1">
        <i data-lucide="message-square" class="w-3.5 h-3.5 shrink-0 ${isActive ? 'text-indigo-600' : 'text-slate-400'}"></i>
        <span class="session-title">${escapeHtml(sess.title)}</span>
      </div>
      <button class="delete-btn" title="Xóa hội thoại" onclick="deleteSession('${sess.id}', event)">
        <i data-lucide="x" class="w-3.5 h-3.5"></i>
      </button>
    `;
    item.onclick = () => switchSession(sess.id);
    sessionHistoryList.appendChild(item);
  });

  lucide.createIcons();
}

function formatQuestionTime(ts) {
  if (!ts) return '';
  const d = new Date(ts);
  const h = String(d.getHours()).padStart(2, '0');
  const m = String(d.getMinutes()).padStart(2, '0');
  return `${h}:${m}`;
}

function loadSessionIntoUI(sess) {
  const headerSessionTitle = document.getElementById('headerSessionTitle');
  if (headerSessionTitle && sess) {
    headerSessionTitle.textContent = sess.title || 'Hội thoại mới';
  }

  activeQuestionId = null;
  renderQuestionList(sess);
}

function renderQuestionList(sess) {
  if (!questionList) return;
  questionList.innerHTML = '';

  if (!sess || !sess.messages || sess.messages.length === 0) {
    if (questionListEmpty) {
      questionList.appendChild(questionListEmpty);
      questionListEmpty.classList.remove('hidden');
    }
    if (questionCountBadge) questionCountBadge.textContent = '0 câu';
    if (workspaceEmptyState) workspaceEmptyState.classList.remove('hidden');
    if (workspaceDetailContainer) {
      workspaceDetailContainer.classList.add('hidden');
      workspaceDetailContainer.innerHTML = '';
    }
    if (workspaceQuestionTitle) workspaceQuestionTitle.textContent = 'Câu trả lời & quá trình suy luận';
    if (workspaceMetaBadge) workspaceMetaBadge.classList.add('hidden');
    renderSuggestions();
    return;
  }

  if (questionListEmpty) questionListEmpty.classList.add('hidden');

  const userMsgs = sess.messages.filter(m => m.role === 'user');
  if (questionCountBadge) questionCountBadge.textContent = `${userMsgs.length} câu`;

  userMsgs.forEach(uMsg => {
    const asstMsg = sess.messages.find(m => m.role === 'assistant' && (m.qId === uMsg.id || m.msgId === uMsg.msgId || (sess.messages.indexOf(m) === sess.messages.indexOf(uMsg) + 1)));

    let statusBadge = '<span class="text-[10.5px] text-indigo-600 font-semibold flex items-center gap-1"><span class="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-pulse"></span> Đang xử lý...</span>';

    if (asstMsg) {
      if (asstMsg.result) {
        const isBlocked = asstMsg.result.status === 'blocked' || asstMsg.result.is_blocked || (asstMsg.result.sqlgrade && asstMsg.result.sqlgrade.grade === 'F');
        const isExecutionFailed = asstMsg.result.is_execution_failed || asstMsg.result.status === 'execution_failed';
        const latency = asstMsg.result.total_latency_seconds || 1.0;
        const rowCount = asstMsg.result.row_count || (asstMsg.result.rows ? asstMsg.result.rows.length : 0);

        if (isBlocked) {
          statusBadge = `<span class="text-[10.5px] font-semibold text-rose-600 flex items-center gap-1"><i data-lucide="shield-alert" class="w-3 h-3 text-rose-500"></i> Bị chặn (${latency}s)</span>`;
        } else if (isExecutionFailed) {
          statusBadge = `<span class="text-[10.5px] font-semibold text-amber-700 flex items-center gap-1"><i data-lucide="alert-triangle" class="w-3 h-3 text-amber-500"></i> Lỗi CSDL (${latency}s)</span>`;
        } else {
          statusBadge = `<span class="text-[10.5px] font-semibold text-emerald-700 flex items-center gap-1"><i data-lucide="check-circle" class="w-3 h-3 text-emerald-600"></i> Hoàn tất (${latency}s) • ${rowCount} dòng</span>`;
        }
      } else if (asstMsg.error) {
        statusBadge = `<span class="text-[10.5px] font-semibold text-rose-600 flex items-center gap-1"><i data-lucide="alert-circle" class="w-3 h-3 text-rose-500"></i> Thất bại</span>`;
      }
    }

    const card = document.createElement('div');
    const qIdentifier = uMsg.id || uMsg.msgId;
    // Thẻ đang giới hạn ở 2 dòng; chỉ tạo điều khiển khi câu hỏi thực sự dài.
    const needsExpand = uMsg.text.length > 118;
    card.id = `qcard_${qIdentifier}`;
    const cardMsgId = uMsg.msgId || (asstMsg ? asstMsg.msgId : '');
    card.dataset.msgId = cardMsgId;
    card.className = `question-card-item ${qIdentifier === activeQuestionId ? 'active' : ''}`;
    card.innerHTML = `
      <div class="flex items-center justify-between gap-1.5 mb-1.5">
        <span class="text-[10px] font-mono font-bold px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 border border-slate-200">${escapeHtml(uMsg.dbId || sess.dbId || 'DB')}</span>
        <span class="text-[10px] text-slate-400 font-mono">${formatQuestionTime(uMsg.timestamp)}</span>
      </div>
      <div class="q-title mb-2.5">${escapeHtml(uMsg.text)}</div>
      ${needsExpand ? `
        <button type="button" class="question-expand-btn" aria-expanded="false" title="Xem toàn bộ câu hỏi">
          <i data-lucide="chevrons-down" class="w-3.5 h-3.5"></i>
          <span>Xem đầy đủ</span>
        </button>
      ` : ''}
      <div class="flex items-center justify-between pt-1 border-t border-slate-100">
        <div class="q-status-container">${statusBadge}</div>
        <i data-lucide="chevron-right" class="w-3.5 h-3.5 text-slate-400 shrink-0"></i>
      </div>
    `;

    card.onclick = () => selectQuestion(qIdentifier);
    const expandButton = card.querySelector('.question-expand-btn');
    if (expandButton) {
      expandButton.onclick = event => {
        event.stopPropagation();
        const expanded = card.classList.toggle('is-expanded');
        const title = card.querySelector('.q-title');
        if (title) {
          title.style.webkitLineClamp = expanded ? 'unset' : '2';
          title.style.display = expanded ? 'block' : '-webkit-box';
        }
        expandButton.setAttribute('aria-expanded', String(expanded));
        expandButton.title = expanded ? 'Thu gọn câu hỏi' : 'Xem toàn bộ câu hỏi';
        expandButton.innerHTML = expanded
          ? '<i data-lucide="chevrons-up" class="w-3.5 h-3.5"></i><span>Thu gọn</span>'
          : '<i data-lucide="chevrons-down" class="w-3.5 h-3.5"></i><span>Xem đầy đủ</span>';
        lucide.createIcons();
      };
    }
    questionList.appendChild(card);
  });

  lucide.createIcons();

  if (!activeQuestionId && userMsgs.length > 0) {
    const lastMsg = userMsgs[userMsgs.length - 1];
    selectQuestion(lastMsg.id || lastMsg.msgId);
  }
}

function selectQuestion(qId) {
  const sess = getActiveSession();
  if (!sess || !sess.messages) return;

  activeQuestionId = qId;

  document.querySelectorAll('.question-card-item').forEach(el => {
    el.classList.toggle('active', el.id === `qcard_${qId}`);
  });

  const uMsg = sess.messages.find(m => m.role === 'user' && (m.id === qId || m.msgId === qId));
  if (!uMsg) return;

  const asstMsg = sess.messages.find(m => m.role === 'assistant' && (m.qId === qId || m.msgId === uMsg.msgId || (sess.messages.indexOf(m) === sess.messages.indexOf(uMsg) + 1)));

  if (workspaceEmptyState) workspaceEmptyState.classList.add('hidden');
  if (workspaceDetailContainer) {
    workspaceDetailContainer.classList.remove('hidden');
    workspaceDetailContainer.innerHTML = '';
  }

  if (workspaceQuestionTitle) {
    workspaceQuestionTitle.textContent = uMsg.text;
  }

  if (workspaceMetaBadge) {
    workspaceMetaBadge.textContent = `${uMsg.dbId || sess.dbId || 'CSDL'} • ${uMsg.modelId || sess.modelId || 'Model'}`;
    workspaceMetaBadge.classList.remove('hidden');
  }

  if (asstMsg) {
    restoreAssistantMessage(asstMsg, workspaceDetailContainer);
  }

  if (workspaceBody) {
    workspaceBody.scrollTop = 0;
  }
}

function updateQuestionCardStatus(msgId, data, eventType) {
  const card = document.querySelector(`[data-msg-id="${msgId}"]`);
  if (!card) return;
  const statusContainer = card.querySelector('.q-status-container');
  if (!statusContainer) return;

  if (eventType === 'result') {
    const isBlocked = data.status === 'blocked' || data.is_blocked || (data.sqlgrade && data.sqlgrade.grade === 'F');
    const isExecutionFailed = data.is_execution_failed || data.status === 'execution_failed';
    const latency = data.total_latency_seconds || 1.0;
    const rowCount = data.row_count || (data.rows ? data.rows.length : 0);

    if (isBlocked) {
      statusContainer.innerHTML = `<span class="text-[10.5px] font-semibold text-rose-600 flex items-center gap-1"><i data-lucide="shield-alert" class="w-3 h-3 text-rose-500"></i> Bị chặn (${latency}s)</span>`;
    } else if (isExecutionFailed) {
      statusContainer.innerHTML = `<span class="text-[10.5px] font-semibold text-amber-700 flex items-center gap-1"><i data-lucide="alert-triangle" class="w-3 h-3 text-amber-500"></i> Lỗi CSDL (${latency}s)</span>`;
    } else {
      statusContainer.innerHTML = `<span class="text-[10.5px] font-semibold text-emerald-700 flex items-center gap-1"><i data-lucide="check-circle" class="w-3 h-3 text-emerald-600"></i> Hoàn tất (${latency}s) • ${rowCount} dòng</span>`;
    }
  } else if (eventType === 'error') {
    statusContainer.innerHTML = `<span class="text-[10.5px] font-semibold text-rose-600 flex items-center gap-1"><i data-lucide="alert-circle" class="w-3 h-3 text-rose-500"></i> Thất bại</span>`;
  }
  lucide.createIcons();
}

// ---------------------------------------------------------------------------
// 2. Khởi tạo Giao diện & Tải Cấu hình
// ---------------------------------------------------------------------------
async function init() {
  initPaneSplitter();
  loadSessions();

  try {
    const res = await fetch('/api/config');
    appConfig = await res.json();
    renderControls();
  } catch (err) {
    console.error('Lỗi nạp cấu hình:', err);
  }

  // Khởi tạo hoặc nạp session
  if (chatSessions.length > 0) {
    switchSession(chatSessions[0].id);
  } else {
    createNewSession();
  }

  lucide.createIcons();
}

function renderControls() {
  if (appConfig.databases && appConfig.databases.length > 0) {
    dbSelect.innerHTML = appConfig.databases
      .map(db => `<option value="${db.id}">${db.icon} ${db.title} (${db.id})</option>`)
      .join('');
  }

  if (appConfig.models && appConfig.models.length > 0) {
    modelSelect.innerHTML = appConfig.models
      .map(m => `<option value="${m.id}">${m.name} (${m.provider})</option>`)
      .join('');
  }

  const activeSess = getActiveSession();
  if (activeSess) {
    if (activeSess.dbId) dbSelect.value = activeSess.dbId;
    if (activeSess.modelId) modelSelect.value = activeSess.modelId;
  }

  renderSuggestions();
}

// Hiển thị câu hỏi gợi ý ở đầu phiên chat mới (Welcome Hero)
function renderSuggestions() {
  const currentDbId = dbSelect ? dbSelect.value : 'financial';
  const currentDb = (appConfig.databases || []).find(d => d.id === currentDbId);
  if (!currentDb) return;

  quickCardsContainer.innerHTML = '';
  (currentDb.prompts || []).slice(0, 3).forEach(promptText => {
    const card = document.createElement('div');
    card.className =
      'p-3.5 rounded-xl bg-white border border-slate-200 hover:border-indigo-400 hover:shadow-sm cursor-pointer transition-all flex flex-col justify-between';
    card.innerHTML = `
      <div class="text-xs text-slate-700 font-medium leading-relaxed mb-2.5">${escapeHtml(promptText)}</div>
      <div class="text-[11px] text-indigo-600 font-semibold flex items-center gap-1">Hỏi câu này ➔</div>
    `;
    card.onclick = () => submitPrompt(promptText);
    quickCardsContainer.appendChild(card);
  });

  lucide.createIcons();
}

// Lắng nghe sự kiện
dbSelect.addEventListener('change', () => {
  const sess = getActiveSession();
  if (sess) {
    sess.dbId = dbSelect.value;
    saveSessions();
  }
  renderSuggestions();
});

modelSelect.addEventListener('change', () => {
  const sess = getActiveSession();
  if (sess) {
    sess.modelId = modelSelect.value;
    saveSessions();
  }
});

toggleSidebarBtn.addEventListener('click', () => {
  sidebar.classList.toggle('-ml-72');
});

newChatBtn.addEventListener('click', () => {
  createNewSession();
});

clearAllHistoryBtn.addEventListener('click', () => {
  clearAllSessions();
});

// Phóng to / Thu nhỏ Không gian Tư duy & Đồ thị
if (fullscreenWorkspaceBtn && workspacePane) {
  fullscreenWorkspaceBtn.addEventListener('click', () => {
    const isMax = workspacePane.classList.toggle('is-maximized');
    fullscreenWorkspaceBtn.innerHTML = isMax
      ? `<i data-lucide="minimize-2" class="w-3.5 h-3.5"></i>`
      : `<i data-lucide="maximize-2" class="w-3.5 h-3.5"></i>`;
    lucide.createIcons();
  });
}

// Enter để gửi câu hỏi, Shift+Enter để xuống dòng
if (queryInput) {
  queryInput.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      queryForm.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
    }
  });
}

// ---------------------------------------------------------------------------
// 3. Gửi Câu hỏi & Nhận Stream SSE
// ---------------------------------------------------------------------------
window.submitPrompt = function (text) {
  queryInput.value = text;
  queryForm.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
};

queryForm.addEventListener('submit', async e => {
  e.preventDefault();
  const question = queryInput.value.trim();
  if (!question) return;

  let sess = getActiveSession();
  if (!sess) {
    sess = createNewSession();
  }

  // Cập nhật tiêu đề session nếu là câu hỏi đầu tiên
  if (sess.messages.length === 0 || sess.title === 'Hội thoại mới') {
    sess.title = question.length > 28 ? question.substring(0, 28) + '...' : question;
    sess.dbId = dbSelect.value;
    sess.modelId = modelSelect.value;
    saveSessions();
    renderSidebarSessions();
  }

  const qId = 'q_' + Date.now();
  const uMsg = {
    id: qId,
    msgId: qId,
    role: 'user',
    text: question,
    timestamp: new Date().toISOString(),
    dbId: dbSelect.value,
    modelId: modelSelect.value,
  };

  sess.messages.push(uMsg);
  saveSessions();

  // Cập nhật danh sách câu hỏi bên phải
  renderQuestionList(sess);
  activeQuestionId = qId;
  document.querySelectorAll('.question-card-item').forEach(el => {
    el.classList.toggle('active', el.id === `qcard_${qId}`);
  });

  // Khởi tạo không gian làm việc bên trái
  if (workspaceEmptyState) workspaceEmptyState.classList.add('hidden');
  if (workspaceDetailContainer) {
    workspaceDetailContainer.classList.remove('hidden');
    workspaceDetailContainer.innerHTML = '';
  }
  if (workspaceQuestionTitle) {
    workspaceQuestionTitle.textContent = question;
  }
  if (workspaceMetaBadge) {
    workspaceMetaBadge.textContent = `${dbSelect.value} • ${modelSelect.value}`;
    workspaceMetaBadge.classList.remove('hidden');
  }

  queryInput.value = '';
  queryInput.disabled = true;
  sendBtn.disabled = true;

  // Khung Assistant với Stepper 4 bước bên trong Workspace Container
  const msgId = 'msg_' + Date.now();
  const assistantDiv = createAssistantShell(msgId);
  if (workspaceDetailContainer) {
    workspaceDetailContainer.appendChild(assistantDiv);
  } else if (chatMessages) {
    chatMessages.appendChild(assistantDiv);
  }
  if (workspaceBody) workspaceBody.scrollTop = 0;

  const assistantRecord = {
    role: 'assistant',
    qId: qId,
    msgId: msgId,
    steps: {},
    thinking: {},
    result: null,
    error: null,
  };

  const startTime = Date.now();
  const timerInterval = setInterval(() => {
    const timerElem = document.getElementById(`${msgId}_timer`);
    if (timerElem && timerElem.textContent.startsWith('Đang chạy')) {
      const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
      timerElem.textContent = `Đang chạy... (${elapsed}s)`;
    } else {
      clearInterval(timerInterval);
    }
  }, 200);

  try {
    const response = await fetch('/api/query/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question,
        database_id: dbSelect.value,
        model_name: modelSelect.value,
      }),
    });

    if (!response.ok) {
      let errDetail = `Máy chủ phản hồi mã lỗi ${response.status}`;
      try {
        const errJson = await response.json();
        if (errJson && errJson.detail) {
          errDetail = errJson.detail;
        }
      } catch (_) {}
      throw new Error(errDetail);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const chunks = buffer.split('\n\n');
      buffer = chunks.pop();

      for (const chunk of chunks) {
        const lines = chunk.split('\n');
        let eventType = 'message';
        let data = null;

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            eventType = line.replace('event: ', '').trim();
          } else if (line.startsWith('data: ')) {
            try {
              data = JSON.parse(line.replace('data: ', '').trim());
            } catch (pErr) {
              console.error('Lỗi parse data SSE:', pErr);
            }
          }
        }

        if (data) {
          if (eventType === 'step') {
            assistantRecord.steps[data.step] = data;
            if (data.thinking) {
              assistantRecord.thinking['step' + data.step] = data.thinking;
            }
          } else if (eventType === 'result') {
            assistantRecord.result = data;
            if (data.thinking_step1) assistantRecord.thinking.step1 = data.thinking_step1;
            if (data.thinking_graph) assistantRecord.thinking.step2 = data.thinking_graph;
            if (data.thinking_ast) assistantRecord.thinking.step3 = data.thinking_ast;
            if (data.thinking_exec) assistantRecord.thinking.step4 = data.thinking_exec;
            updateQuestionCardStatus(qId, data, 'result');
          } else if (eventType === 'error') {
            assistantRecord.error = data.error_message;
            updateQuestionCardStatus(qId, data, 'error');
          }
          handleStreamEvent(msgId, eventType, data);
        }
      }
    }

    // Lưu phản hồi Assistant vào session
    sess.messages.push(assistantRecord);
    saveSessions();
  } catch (err) {
    assistantRecord.error = err.message;
    sess.messages.push(assistantRecord);
    saveSessions();
    renderError(msgId, err.message);
    updateQuestionCardStatus(qId, { error_message: err.message }, 'error');
  } finally {
    clearInterval(timerInterval);
    queryInput.disabled = false;
    sendBtn.disabled = false;
    queryInput.focus();
    if (workspaceBody) workspaceBody.scrollTop = 0;
  }
});

// ---------------------------------------------------------------------------
// 4. UI Helpers
// ---------------------------------------------------------------------------
function appendUserMessage(text, scroll = true) {
  const wrapper = document.createElement('div');
  wrapper.className = 'flex justify-end';
  wrapper.innerHTML = `
    <div class="user-msg-bubble max-w-xl">
      ${escapeHtml(text)}
    </div>
  `;
  chatMessages.appendChild(wrapper);
  if (scroll) scrollToBottom();
}

function createAssistantShell(msgId) {
  const card = document.createElement('div');
  card.id = msgId;
  card.className = 'assistant-card space-y-3';

  card.innerHTML = `
    <!-- Stepper 4 bước tinh gọn & Nút Mở rộng Tư duy -->
    <div id="${msgId}_stepper" class="stepper-container">
      <div class="text-xs font-semibold text-slate-500 mb-2.5 flex items-center justify-between">
        <span class="flex items-center gap-1.5">
          <span class="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-pulse"></span>
          <span>Tiến trình xử lý:</span>
        </span>
        <div class="flex items-center gap-2">
          <button id="${msgId}_toggle_thinking" type="button" class="thinking-accordion-btn" onclick="toggleThinkingProcess('${msgId}')">
            <i data-lucide="network" class="w-3.5 h-3.5 text-indigo-600"></i>
            <span id="${msgId}_toggle_text">Tổng quan xử lý</span>
            <i id="${msgId}_toggle_arrow" data-lucide="chevron-down" class="w-3.5 h-3.5 transition-transform duration-200"></i>
          </button>
          <span id="${msgId}_timer" class="text-[11px] font-mono text-slate-400 font-medium">Đang chạy...</span>
        </div>
      </div>

      <div class="grid grid-cols-2 sm:grid-cols-4 gap-2" role="tablist" aria-label="Các bước xử lý truy vấn">
        <button id="${msgId}_step_1" type="button" class="step-node cursor-pointer hover:border-indigo-300" onclick="selectStepTab('${msgId}', 1)" role="tab">
          <div id="${msgId}_icon_1" class="step-icon">1</div>
          <span class="truncate">Dò tìm dữ liệu</span>
        </button>
        <button id="${msgId}_step_2" type="button" class="step-node cursor-pointer hover:border-indigo-300" onclick="selectStepTab('${msgId}', 2)" role="tab">
          <div id="${msgId}_icon_2" class="step-icon">2</div>
          <span class="truncate">Tạo SQL</span>
        </button>
        <button id="${msgId}_step_3" type="button" class="step-node cursor-pointer hover:border-indigo-300" onclick="selectStepTab('${msgId}', 3)" role="tab">
          <div id="${msgId}_icon_3" class="step-icon">3</div>
          <span class="truncate">An toàn AST</span>
        </button>
        <button id="${msgId}_step_4" type="button" class="step-node cursor-pointer hover:border-indigo-300" onclick="selectStepTab('${msgId}', 4)" role="tab">
          <div id="${msgId}_icon_4" class="step-icon">4</div>
          <span class="truncate">Kết quả</span>
        </button>
      </div>
      <div id="${msgId}_step_detail" class="text-[11px] text-slate-500 mt-2.5 pt-2 border-t border-slate-200/60 hidden">
      </div>

      <!-- Khung Quá trình Tư duy & Đồ thị quan hệ bảng (Thu gọn / Mở rộng) -->
      <div id="${msgId}_thinking_box" class="thinking-box hidden">
        <div class="px-3.5 py-2 bg-slate-100/80 border-b border-slate-200/80 flex items-center justify-between text-[11px] font-semibold text-slate-700">
          <span class="flex items-center gap-1.5">
            <i data-lucide="git-fork" class="w-3.5 h-3.5 text-indigo-600"></i>
            <span>Chi tiết Tư duy Suy luận & Đồ thị Schema (Dành cho DE & DA)</span>
          </span>
          <span class="text-[10px] text-slate-400 font-normal">Bấm một bước để xem chi tiết riêng</span>
        </div>
        <div id="${msgId}_thinking_steps_container" class="divide-y divide-slate-200/60 text-xs">
          <!-- Step 1 Thinking -->
          <div id="${msgId}_think_row_1" class="thinking-step-row">
            <div class="thinking-step-header" onclick="toggleStepRow('${msgId}', 1)">
              <span class="font-semibold text-slate-800 flex items-center gap-1.5 step-title-text">
                <span class="w-2 h-2 rounded-full bg-slate-300" id="${msgId}_think_dot_1"></span>
                <span>Bước 1: Phân tích Schema & Dò tìm thực thể</span>
              </span>
              <i id="${msgId}_think_arrow_1" data-lucide="chevron-down" class="w-3.5 h-3.5 text-slate-400"></i>
            </div>
            <div id="${msgId}_think_content_1" class="mt-2 text-slate-600 space-y-1.5 text-[11.5px] hidden">
              <div class="text-slate-400 italic">Đang chờ khởi tạo...</div>
            </div>
          </div>

          <!-- Step 2 Thinking (Steiner Join Graph) -->
          <div id="${msgId}_think_row_2" class="thinking-step-row">
            <div class="thinking-step-header" onclick="toggleStepRow('${msgId}', 2)">
              <span class="font-semibold text-slate-800 flex items-center gap-1.5 step-title-text">
                <span class="w-2 h-2 rounded-full bg-slate-300" id="${msgId}_think_dot_2"></span>
                <span>Bước 2: Suy luận Đồ thị JOIN & Steiner Minimal Tree</span>
              </span>
              <i id="${msgId}_think_arrow_2" data-lucide="chevron-down" class="w-3.5 h-3.5 text-slate-400"></i>
            </div>
            <div id="${msgId}_think_content_2" class="mt-2 text-slate-600 space-y-1.5 text-[11.5px] hidden">
              <div class="text-slate-400 italic">Đang chờ khởi tạo...</div>
            </div>
          </div>

          <!-- Step 3 Thinking (AST Security Checklist) -->
          <div id="${msgId}_think_row_3" class="thinking-step-row">
            <div class="thinking-step-header" onclick="toggleStepRow('${msgId}', 3)">
              <span class="font-semibold text-slate-800 flex items-center gap-1.5 step-title-text">
                <span class="w-2 h-2 rounded-full bg-slate-300" id="${msgId}_think_dot_3"></span>
                <span>Bước 3: Kiểm tra an toàn AST & Chính sách Viễn thông</span>
              </span>
              <i id="${msgId}_think_arrow_3" data-lucide="chevron-down" class="w-3.5 h-3.5 text-slate-400"></i>
            </div>
            <div id="${msgId}_think_content_3" class="mt-2 text-slate-600 space-y-1.5 text-[11.5px] hidden">
              <div class="text-slate-400 italic">Đang chờ khởi tạo...</div>
            </div>
          </div>

          <!-- Step 4 Thinking (Execution & Rows) -->
          <div id="${msgId}_think_row_4" class="thinking-step-row">
            <div class="thinking-step-header" onclick="toggleStepRow('${msgId}', 4)">
              <span class="font-semibold text-slate-800 flex items-center gap-1.5 step-title-text">
                <span class="w-2 h-2 rounded-full bg-slate-300" id="${msgId}_think_dot_4"></span>
                <span>Bước 4: Thực thi CSDL & Thống kê Tài nguyên</span>
              </span>
              <i id="${msgId}_think_arrow_4" data-lucide="chevron-down" class="w-3.5 h-3.5 text-slate-400"></i>
            </div>
            <div id="${msgId}_think_content_4" class="mt-2 text-slate-600 space-y-1.5 text-[11.5px] hidden">
              <div class="text-slate-400 italic">Đang chờ khởi tạo...</div>
            </div>
          </div>
        </div>
      </div>

    </div>

    <!-- Output Area (SQL & Table) -->
    <div id="${msgId}_output" class="space-y-3 hidden" role="tabpanel"></div>
  `;

  return card;
}

function handleStreamEvent(msgId, eventType, data) {
  if (eventType === 'step') {
    const stepNum = data.step;
    const node = document.getElementById(`${msgId}_step_${stepNum}`);
    const icon = document.getElementById(`${msgId}_icon_${stepNum}`);
    const detailBox = document.getElementById(`${msgId}_step_detail`);

    if (!node) return;

    node.classList.remove('running', 'done', 'warning', 'failed', 'blocked', 'cancelled', 'skipped');

    if (data.status === 'running') {
      node.classList.add('running');
      if (icon) icon.innerHTML = stepNum;
    } else if (data.status === 'done') {
      node.classList.add('done');
      if (icon) icon.innerHTML = '✓';
    } else if (data.status === 'warning') {
      node.classList.add('warning');
      if (icon) icon.innerHTML = '!';
    } else if (data.status === 'failed' || data.status === 'blocked') {
      node.classList.add('failed');
      if (icon) icon.innerHTML = '✕';
    } else if (data.status === 'cancelled' || data.status === 'skipped') {
      node.classList.add('cancelled');
      if (icon) icon.innerHTML = '–';
    }

    if (data.detail && detailBox) {
      detailBox.classList.remove('hidden');
      if (data.status === 'failed' || data.status === 'blocked') {
        detailBox.className = 'text-[11px] text-rose-600 font-medium mt-2.5 pt-2 border-t border-rose-200/80 flex items-start gap-1.5';
        detailBox.innerHTML = `<i data-lucide="shield-alert" class="w-3.5 h-3.5 shrink-0 mt-0.5 text-rose-500"></i><span>${escapeHtml(data.detail)}</span>`;
      } else if (data.status === 'warning') {
        detailBox.className = 'text-[11px] text-amber-700 font-medium mt-2.5 pt-2 border-t border-amber-200/80 flex items-start gap-1.5';
        detailBox.innerHTML = `<i data-lucide="alert-triangle" class="w-3.5 h-3.5 shrink-0 mt-0.5 text-amber-500"></i><span>${escapeHtml(data.detail)}</span>`;
      } else {
        detailBox.className = 'text-[11px] text-slate-500 mt-2.5 pt-2 border-t border-slate-200/60';
        detailBox.textContent = data.detail;
      }
      lucide.createIcons();
    }

    if (data.thinking) {
      renderStepThinking(msgId, stepNum, data.thinking, data.status);
    }
    if (data.status === 'running') selectStepTab(msgId, stepNum);
  } else if (eventType === 'result') {
    const isBlocked = data.status === 'blocked' || data.is_blocked || (data.sqlgrade && data.sqlgrade.grade === 'F');
    const isExecutionFailed = data.is_execution_failed || data.status === 'execution_failed';
    const timer = document.getElementById(`${msgId}_timer`);
    if (timer) {
      if (isBlocked) {
        timer.textContent = `Bị chặn (${data.total_latency_seconds}s)`;
        timer.className = 'text-[11px] font-mono text-rose-600 font-bold';
      } else if (isExecutionFailed) {
        timer.textContent = `Lỗi CSDL (${data.total_latency_seconds}s)`;
        timer.className = 'text-[11px] font-mono text-amber-600 font-bold';
      } else {
        timer.textContent = `Hoàn tất (${data.total_latency_seconds}s)`;
        timer.className = 'text-[11px] font-mono text-emerald-600 font-medium';
      }
    }
    if (data.thinking_step1) {
      renderStepThinking(msgId, 1, data.thinking_step1, 'done');
    }
    if (data.thinking_graph) {
      renderStepThinking(msgId, 2, data.thinking_graph, isExecutionFailed ? 'warning' : 'done');
    }
    if (data.thinking_ast) {
      renderStepThinking(msgId, 3, data.thinking_ast, isBlocked ? 'failed' : 'done');
    }
    if (data.thinking_exec) {
      renderStepThinking(msgId, 4, data.thinking_exec, isBlocked ? 'blocked' : (isExecutionFailed ? 'failed' : 'done'));
    }
    renderResult(msgId, data);
    selectStepTab(msgId, 4);
  } else if (eventType === 'error') {
    const timer = document.getElementById(`${msgId}_timer`);
    if (timer) {
      timer.textContent = `Thất bại`;
      timer.className = 'text-[11px] font-mono text-rose-600 font-bold';
    }
    renderError(msgId, data.error_message);
    selectStepTab(msgId, 4);
  }

  scrollToBottom();
}

function restoreAssistantMessage(msg, targetContainer) {
  const container = targetContainer || workspaceDetailContainer || document.getElementById('chatMessages');
  if (!container) return;
  const msgId = msg.msgId || 'msg_' + Math.random();
  const card = createAssistantShell(msgId);
  container.appendChild(card);

  const isBlocked = msg.result && (msg.result.status === 'blocked' || msg.result.is_blocked || (msg.result.sqlgrade && msg.result.sqlgrade.grade === 'F'));
  const isExecutionFailed = msg.result && (msg.result.is_execution_failed || msg.result.status === 'execution_failed');

  // Restore steps with accurate logic
  for (let i = 1; i <= 4; i++) {
    const node = document.getElementById(`${msgId}_step_${i}`);
    const icon = document.getElementById(`${msgId}_icon_${i}`);
    if (!node) continue;
    node.classList.remove('running', 'done', 'warning', 'failed', 'blocked', 'cancelled');

    if (isBlocked) {
      if (i <= 2) {
        node.classList.add('done');
        if (icon) icon.innerHTML = '✓';
      } else if (i === 3) {
        node.classList.add('failed');
        if (icon) icon.innerHTML = '✕';
      } else if (i === 4) {
        node.classList.add('cancelled');
        if (icon) icon.innerHTML = '–';
      }
    } else if (isExecutionFailed) {
      if (i === 1) {
        node.classList.add('done');
        if (icon) icon.innerHTML = '✓';
      } else if (i === 2) {
        node.classList.add('warning');
        if (icon) icon.innerHTML = '!';
      } else if (i === 3) {
        node.classList.add('done');
        if (icon) icon.innerHTML = '✓';
      } else if (i === 4) {
        node.classList.add('failed');
        if (icon) icon.innerHTML = '✕';
      }
    } else {
      node.classList.add('done');
      if (icon) icon.innerHTML = '✓';
    }
  }

  // Khôi phục Quá trình Tư duy (Thinking Steps) để triệt tiêu hoàn toàn 'Đang chờ khởi tạo...'
  const t = msg.thinking || (msg.result ? {
    step1: msg.result.thinking_step1,
    step2: msg.result.thinking_graph,
    step3: msg.result.thinking_ast,
    step4: msg.result.thinking_exec,
  } : null);

  if (t) {
    if (t.step1) renderStepThinking(msgId, 1, t.step1, 'done');
    if (t.step2) renderStepThinking(msgId, 2, t.step2, isExecutionFailed ? 'warning' : 'done');
    if (t.step3) renderStepThinking(msgId, 3, t.step3, isBlocked ? 'failed' : 'done');
    if (t.step4) renderStepThinking(msgId, 4, t.step4, isBlocked ? 'blocked' : (isExecutionFailed ? 'failed' : 'done'));
  }

  if (msg.result) {
    const timer = document.getElementById(`${msgId}_timer`);
    if (timer) {
      if (isBlocked) {
        timer.textContent = `Bị chặn (${msg.result.total_latency_seconds || 1.2}s)`;
        timer.className = 'text-[11px] font-mono text-rose-600 font-bold';
      } else if (isExecutionFailed) {
        timer.textContent = `Lỗi CSDL (${msg.result.total_latency_seconds || 1.2}s)`;
        timer.className = 'text-[11px] font-mono text-amber-600 font-bold';
      } else {
        timer.textContent = `Hoàn tất (${msg.result.total_latency_seconds || 1.2}s)`;
        timer.className = 'text-[11px] font-mono text-emerald-600 font-medium';
      }
    }
    renderResult(msgId, msg.result);
    selectStepTab(msgId, 4);
  } else if (msg.error) {
    renderError(msgId, msg.error);
    selectStepTab(msgId, 4);
  } else {
    selectStepTab(msgId, 1);
  }
}

function renderResult(msgId, data) {
  const output = document.getElementById(`${msgId}_output`);
  if (!output) return;

  const isBlocked = data.status === 'blocked' || data.is_blocked || (data.sqlgrade && data.sqlgrade.grade === 'F');
  const isExecutionFailed = data.is_execution_failed || data.status === 'execution_failed';
  let html = '';

  // 1. SQL Box
  if (data.sql) {
    const codeId = `code_${Date.now()}_${Math.floor(Math.random() * 1000)}`;
    const headerTag = isBlocked
      ? `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-100 text-rose-700 border border-rose-200 flex items-center gap-1">
           <i data-lucide="shield-alert" class="w-3 h-3 text-rose-600"></i>
           <span>Câu lệnh bị từ chối thực thi</span>
         </span>`
      : `<span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
           Hợp lệ
         </span>`;

    html += `
      <div class="sql-box ${isBlocked ? 'border-rose-300' : ''}">
        <div class="sql-header ${isBlocked ? 'bg-rose-50/70 border-rose-200' : ''}">
          <div class="flex items-center gap-2">
            <span class="flex items-center gap-1.5 text-slate-700">
              <i data-lucide="terminal" class="w-3.5 h-3.5 ${isBlocked ? 'text-rose-600' : 'text-indigo-600'}"></i>
              <span class="font-semibold">${isBlocked ? 'SQL đề xuất bởi AI (Nguy hại)' : 'Câu lệnh SQL đã tạo'}</span>
            </span>
            ${headerTag}
          </div>
          <button onclick="copyCode('${codeId}', this)" class="px-2.5 py-1 rounded bg-white hover:bg-slate-100 border border-slate-200 text-xs font-medium text-slate-600 hover:text-slate-900 transition-colors flex items-center gap-1 cursor-pointer">
            <i data-lucide="copy" class="w-3 h-3"></i>
            <span>Sao chép</span>
          </button>
        </div>
        <div class="sql-content overflow-x-auto">
          <pre><code id="${codeId}" class="language-sql">${escapeHtml(data.sql)}</code></pre>
        </div>
      </div>
    `;
  }

  // 2. Data Table OR Security Blocked Banner OR Execution Error Banner
  if (isBlocked) {
    const findings = (data.sqlgrade && data.sqlgrade.findings && data.sqlgrade.findings.length > 0)
      ? data.sqlgrade.findings
      : (data.error_message ? [data.error_message] : ['Vi phạm chính sách an toàn dữ liệu.']);
    
    const findingsItems = findings
      .map(f => `<li class="flex items-start gap-1.5"><span class="text-rose-500 font-bold">•</span><span>${escapeHtml(f)}</span></li>`)
      .join('');

    const adviceText = data.advice || "Bổ sung điều kiện truy vấn an toàn để bảo vệ cơ sở dữ liệu.";

    html += `
      <div class="security-blocked-box">
        <div class="flex items-start gap-3">
          <div class="w-9 h-9 rounded-xl bg-rose-100 text-rose-600 flex items-center justify-center shrink-0 mt-0.5">
            <i data-lucide="shield-alert" class="w-5 h-5 text-rose-600"></i>
          </div>
          <div class="space-y-2 flex-1">
            <div class="flex flex-wrap items-center justify-between gap-2">
              <h4 class="text-xs font-bold text-rose-900 uppercase tracking-wide flex items-center gap-1.5">
                <span>Truy vấn bị từ chối thực thi (Guardrail An Toàn)</span>
              </h4>
              <span class="text-[10px] font-bold px-2.5 py-0.5 rounded-full bg-rose-200/80 text-rose-800">
                0 dòng quét • Bảo vệ CSDL
              </span>
            </div>
            <p class="text-xs text-rose-700 leading-relaxed">
              Hệ thống AST Policy Guard đã chủ động ngắt lệnh để bảo vệ cơ sở dữ liệu khỏi rủi ro quá tải hoặc thao tác can thiệp dữ liệu:
            </p>
            <ul class="text-xs text-rose-800 font-medium space-y-1.5 bg-white/90 p-3 rounded-lg border border-rose-200">
              ${findingsItems}
            </ul>
            <div class="p-2.5 rounded-lg bg-rose-100/60 border border-rose-200/80 text-[11px] text-rose-800 flex items-start gap-2 mt-1">
              <i data-lucide="lightbulb" class="w-3.5 h-3.5 shrink-0 text-amber-600 mt-0.5"></i>
              <span><strong>Cách khắc phục:</strong> ${escapeHtml(adviceText)}</span>
            </div>
          </div>
        </div>
      </div>
    `;
  } else if (isExecutionFailed) {
    const errText = data.error_message || "Lỗi thực thi SQLite";
    const adviceText = data.advice || "Kiểm tra lại cấu trúc bảng hoặc thử lại với một mô hình AI khác.";

    html += `
      <div class="p-4 rounded-xl bg-amber-50/90 border border-amber-300/80 text-xs text-amber-900 space-y-2.5 shadow-2xs">
        <div class="flex items-start gap-3">
          <div class="w-8 h-8 rounded-lg bg-amber-100 text-amber-700 flex items-center justify-center shrink-0 mt-0.5">
            <i data-lucide="database" class="w-4 h-4 text-amber-600"></i>
          </div>
          <div class="space-y-1.5 flex-1">
            <div class="flex items-center justify-between">
              <h4 class="font-bold text-amber-900 flex items-center gap-1.5">
                <span>Cơ sở dữ liệu báo lỗi thực thi (Schema Mismatch)</span>
              </h4>
              <span class="text-[10px] font-semibold px-2 py-0.5 rounded bg-amber-200/70 text-amber-800">
                Lỗi CSDL
              </span>
            </div>
            <p class="text-[11.5px] text-amber-800">
              Câu lệnh SQL do AI tạo ra chứa tên cột hoặc cấu trúc không khớp với cơ sở dữ liệu thực tế:
            </p>
            <div class="p-2 rounded bg-white font-mono text-[11px] text-rose-700 border border-amber-200">
              ${escapeHtml(errText)}
            </div>
            <div class="p-2 rounded bg-amber-100/60 border border-amber-200/70 text-[11px] text-amber-800 flex items-start gap-1.5">
              <i data-lucide="lightbulb" class="w-3.5 h-3.5 shrink-0 text-amber-600 mt-0.5"></i>
              <span><strong>Gợi ý:</strong> ${escapeHtml(adviceText)}</span>
            </div>
          </div>
        </div>
      </div>
    `;
  } else {
    // Trường hợp an toàn (Hạng A, Hạng B): Hiển thị bảng dữ liệu
    html += `
      <div class="data-table-wrap">
        <div class="p-3 bg-slate-50/80 border-b border-slate-200 flex items-center justify-between">
          <div class="flex items-center gap-2">
            <i data-lucide="table" class="w-3.5 h-3.5 text-slate-500"></i>
            <span class="text-xs font-bold text-slate-700">Kết quả dữ liệu</span>
            <span class="text-[11px] font-semibold text-slate-500 bg-white border border-slate-200 px-2 py-0.5 rounded-full">
              ${data.row_count} dòng
            </span>
          </div>
          ${
            data.row_count > 0
              ? `
            <button onclick="downloadTable('${msgId}')" class="px-2.5 py-1 rounded bg-white hover:bg-slate-100 border border-slate-200 text-xs font-medium text-slate-600 transition-colors flex items-center gap-1 cursor-pointer">
              <i data-lucide="download" class="w-3 h-3"></i>
              <span>Tải CSV</span>
            </button>
          `
              : ''
          }
        </div>
    `;

    if (data.rows && data.rows.length > 0 && data.columns && data.columns.length > 0) {
      html += `
        <div class="overflow-x-auto">
          <table>
            <thead>
              <tr>
                ${data.columns.map(col => `<th>${escapeHtml(col)}</th>`).join('')}
              </tr>
            </thead>
            <tbody>
              ${data.rows
                .slice(0, 50)
                .map(
                  row => `
                <tr>
                  ${data.columns.map(col => `<td>${escapeHtml(String(row[col] !== null ? row[col] : 'NULL'))}</td>`).join('')}
                </tr>
              `
                )
                .join('')}
            </tbody>
          </table>
        </div>
      `;
    } else {
      html += `
        <div class="p-4 text-xs text-slate-500 text-center">
          Câu lệnh thực thi thành công nhưng trả về 0 dòng dữ liệu trên database hiện tại.
        </div>
      `;
    }

    html += `</div>`;
  }

  // 3. Bottom Metadata (Trạng thái thực thi doanh nghiệp - Không hiển thị điểm thi Benchmark A-F)
  const isBlockedOrDanger = isBlocked || (data.sqlgrade && data.sqlgrade.grade === 'F');
  const isWarn = data.guardrails_status === 'warning' || (data.sqlgrade && data.sqlgrade.grade === 'B');

  let statusBadge = '';
  if (isBlockedOrDanger) {
    statusBadge = `
      <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold border bg-rose-50 text-rose-700 border-rose-200">
        <span class="w-1.5 h-1.5 rounded-full bg-rose-500"></span>
        <span>${escapeHtml(data.status_label || 'Từ chối thực thi (Chặn rủi ro)')}</span>
      </span>
    `;
  } else if (isWarn) {
    statusBadge = `
      <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium border bg-amber-50 text-amber-700 border-amber-200">
        <span class="w-1.5 h-1.5 rounded-full bg-amber-500"></span>
        <span>${escapeHtml(data.status_label || 'Thực thi có cảnh báo (N:M)')}</span>
      </span>
    `;
  } else {
    statusBadge = `
      <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium border bg-emerald-50 text-emerald-700 border-emerald-200">
        <span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
        <span>${escapeHtml(data.status_label || 'Thực thi an toàn (Chỉ đọc)')}</span>
      </span>
    `;
  }

  // Guardrails status badge
  let guardrailText = '';
  if (isBlockedOrDanger) {
    guardrailText = `
      <span class="text-rose-600 font-semibold flex items-center gap-1">
        <i data-lucide="shield-alert" class="w-3.5 h-3.5"></i>
        <span>✗ Kiểm định AST: Đã chặn rủi ro</span>
      </span>
    `;
  } else if (isWarn) {
    guardrailText = `
      <span class="text-amber-600 font-semibold flex items-center gap-1">
        <i data-lucide="alert-triangle" class="w-3.5 h-3.5"></i>
        <span>! Kiểm định AST: Cảnh báo quan hệ N:M</span>
      </span>
    `;
  } else {
    guardrailText = `
      <span class="text-emerald-600 font-semibold flex items-center gap-1">
        <i data-lucide="shield-check" class="w-3.5 h-3.5"></i>
        <span>✓ Kiểm định AST: Hợp lệ 100%</span>
      </span>
    `;
  }

  html += `
    <div class="flex flex-wrap items-center gap-3 text-xs text-slate-400 pt-2 border-t border-slate-100 mt-2">
      ${statusBadge}
      <span class="text-slate-300">|</span>
      <span>⏱️ Thời gian: <strong class="text-slate-600">${data.total_latency_seconds}s</strong></span>
      <span class="text-slate-300">•</span>
      <span>🤖 Mô hình: <strong class="text-slate-600">${data.model_used || 'GPT OSS 120B'}</strong></span>
      <span class="text-slate-300">•</span>
      ${guardrailText}
    </div>
  `;

  output.innerHTML = html;

  // Highlight syntax
  document.querySelectorAll('pre code').forEach(el => {
    hljs.highlightElement(el);
  });
  lucide.createIcons();

  window[`_rows_${msgId}`] = data;
}

function renderError(msgId, errText) {
  const output = document.getElementById(`${msgId}_output`);
  if (!output) return;

  output.innerHTML = `
    <div class="p-4 rounded-xl bg-rose-50 border border-rose-200 text-xs text-rose-700 leading-relaxed flex items-start gap-2.5">
      <i data-lucide="alert-circle" class="w-4 h-4 text-rose-600 shrink-0 mt-0.5"></i>
      <div class="flex-1">
        <strong class="font-bold text-rose-800">Không thể hoàn tất yêu cầu:</strong>
        <p class="mt-1 font-mono text-[11.5px] bg-white/80 p-2 rounded border border-rose-200/80 break-words text-rose-900">${escapeHtml(errText)}</p>
        <div class="mt-2.5 text-[11px] text-slate-500 flex items-center justify-between">
          <span>Gợi ý: Kiểm tra lại lựa chọn CSDL hoặc thử gửi lại câu hỏi.</span>
          <button type="button" onclick="retryLastQuestion()" class="px-2.5 py-1 rounded-md bg-rose-100 hover:bg-rose-200 text-rose-800 font-medium transition-colors inline-flex items-center gap-1 cursor-pointer">
            <i data-lucide="rotate-cw" class="w-3 h-3"></i>
            <span>Thử lại câu hỏi</span>
          </button>
        </div>
      </div>
    </div>
  `;
  lucide.createIcons();
}

window.retryLastQuestion = function () {
  const sess = getCurrentSession();
  if (!sess || !sess.messages || sess.messages.length === 0) return;
  for (let i = sess.messages.length - 1; i >= 0; i--) {
    if (sess.messages[i].role === 'user') {
      queryInput.value = sess.messages[i].text;
      queryForm.dispatchEvent(new Event('submit'));
      break;
    }
  }
};

// ---------------------------------------------------------------------------
// 5. Tiện ích Copy & CSV
// ---------------------------------------------------------------------------
window.copyCode = function (id, btn) {
  const el = document.getElementById(id);
  if (!el) return;
  navigator.clipboard.writeText(el.textContent).then(() => {
    const oldText = btn.innerHTML;
    btn.innerHTML = `<i data-lucide="check" class="w-3 h-3"></i><span>Đã chép</span>`;
    btn.classList.add('btn-copied');
    lucide.createIcons();
    setTimeout(() => {
      btn.innerHTML = oldText;
      btn.classList.remove('btn-copied');
      lucide.createIcons();
    }, 1800);
  });
};

window.downloadTable = function (msgId) {
  const data = window[`_rows_${msgId}`];
  if (!data || !data.rows || !data.rows.length) return;

  const cols = data.columns;
  let csv = cols.map(c => `"${c}"`).join(',') + '\n';
  data.rows.forEach(r => {
    csv += cols.map(c => `"${r[c] !== null ? String(r[c]).replace(/"/g, '""') : ''}"`).join(',') + '\n';
  });

  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `query_data_${Date.now()}.csv`;
  a.click();
  URL.revokeObjectURL(url);
};

// ---------------------------------------------------------------------------
// 6. Quản lý Modal Nhập Cơ sở Dữ liệu Mới (Import Database Modal)
// ---------------------------------------------------------------------------
const importDbModal = document.getElementById('importDbModal');
const openImportModalBtn = document.getElementById('openImportModalBtn');
const closeImportModalBtn = document.getElementById('closeImportModalBtn');
const cancelImportBtn = document.getElementById('cancelImportBtn');
const submitImportBtn = document.getElementById('submitImportBtn');

const importDbTitle = document.getElementById('importDbTitle');
const importDbId = document.getElementById('importDbId');
const importDbDesc = document.getElementById('importDbDesc');
const importDbIcon = document.getElementById('importDbIcon');

const importSqlTextarea = document.getElementById('importSqlTextarea');
const importSqliteFileInput = document.getElementById('importSqliteFileInput');
const importSqliteFileName = document.getElementById('importSqliteFileName');
const importCsvFileInput = document.getElementById('importCsvFileInput');
const importCsvFileName = document.getElementById('importCsvFileName');

const importModalError = document.getElementById('importModalError');
const importModalErrorText = document.getElementById('importModalErrorText');
const importModalProgress = document.getElementById('importModalProgress');
const loadSampleSqlBtn = document.getElementById('loadSampleSqlBtn');

let activeImportTab = 'sql';

function initImportModal() {
  if (!openImportModalBtn || !importDbModal) return;

  // Mở modal
  openImportModalBtn.addEventListener('click', () => {
    importDbModal.classList.remove('hidden');
    importModalError.classList.add('hidden');
    importModalProgress.classList.add('hidden');
    importDbTitle.focus();
  });

  // Đóng modal
  const closeModal = () => {
    importDbModal.classList.add('hidden');
    importModalError.classList.add('hidden');
    importModalProgress.classList.add('hidden');
  };

  if (closeImportModalBtn) closeImportModalBtn.addEventListener('click', closeModal);
  if (cancelImportBtn) cancelImportBtn.addEventListener('click', closeModal);

  // Đóng khi click ngoài hộp thoại
  importDbModal.addEventListener('click', e => {
    if (e.target === importDbModal) closeModal();
  });

  // Chuyển Tabs
  const tabBtns = document.querySelectorAll('.import-tab-btn');
  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      tabBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');

      activeImportTab = btn.dataset.tab;
      document.querySelectorAll('.tab-pane').forEach(p => p.classList.add('hidden'));
      const activePane = document.getElementById(`tabContent_${activeImportTab}`);
      if (activePane) activePane.classList.remove('hidden');

      if (activeImportTab === 'sql' && importDbIcon) importDbIcon.value = '📝';
      else if (activeImportTab === 'sqlite' && importDbIcon) importDbIcon.value = '🗄️';
      else if (activeImportTab === 'csv' && importDbIcon) importDbIcon.value = '📊';
    });
  });

  // Tự động sinh ID từ Tiêu đề nếu chưa nhập ID
  if (importDbTitle) {
    importDbTitle.addEventListener('input', () => {
      if (!importDbId.dataset.userEdited) {
        const slug = importDbTitle.value
          .toLowerCase()
          .normalize('NFD')
          .replace(/[\u0300-\u036f]/g, '')
          .replace(/[^a-z0-9]+/g, '_')
          .replace(/^_+|_+$/g, '');
        importDbId.value = slug;
      }
    });
  }

  if (importDbId) {
    importDbId.addEventListener('input', () => {
      importDbId.dataset.userEdited = 'true';
    });
  }

  // Tải mẫu thử kịch bản SQL
  if (loadSampleSqlBtn) {
    loadSampleSqlBtn.addEventListener('click', () => {
      importDbTitle.value = 'Quản lý Bán lẻ & Đơn hàng';
      importDbId.value = 'retail_store';
      importDbDesc.value = 'Dữ liệu sản phẩm, số lượng tồn kho và các đơn đặt hàng bán lẻ.';
      importDbIcon.value = '🛒';
      importSqlTextarea.value = `CREATE TABLE products (
    product_id INTEGER PRIMARY KEY,
    product_name TEXT NOT NULL,
    category TEXT,
    price REAL,
    stock_qty INTEGER
);

CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY,
    product_id INTEGER,
    order_date TEXT,
    quantity INTEGER,
    status TEXT,
    FOREIGN KEY (product_id) REFERENCES products(product_id)
);

INSERT INTO products VALUES (1, 'Điện thoại 5G Pro', 'Điện tử', 15000000, 45);
INSERT INTO products VALUES (2, 'Tai nghe không dây chống ồn', 'Âm thanh', 2500000, 120);
INSERT INTO products VALUES (3, 'Đồng hồ thông minh thể thao', 'Phụ kiện', 4500000, 30);
INSERT INTO products VALUES (4, 'Bàn phím cơ không dây', 'Phụ kiện', 1800000, 60);

INSERT INTO orders VALUES (101, 1, '2026-09-10', 2, 'COMPLETED');
INSERT INTO orders VALUES (102, 2, '2026-09-12', 1, 'COMPLETED');
INSERT INTO orders VALUES (103, 3, '2026-09-15', 3, 'PENDING');
INSERT INTO orders VALUES (104, 1, '2026-09-18', 1, 'COMPLETED');
INSERT INTO orders VALUES (105, 4, '2026-09-20', 4, 'COMPLETED');`;
    });
  }

  // Cập nhật tên tệp SQLite khi chọn
  if (importSqliteFileInput) {
    importSqliteFileInput.addEventListener('change', () => {
      const file = importSqliteFileInput.files[0];
      if (file) {
        importSqliteFileName.textContent = `Đã chọn: ${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
        if (!importDbTitle.value) {
          const stem = file.name.replace(/\.[^/.]+$/, '');
          importDbTitle.value = stem.charAt(0).toUpperCase() + stem.slice(1);
          importDbId.value = stem.toLowerCase().replace(/[^a-z0-9]+/g, '_');
        }
      }
    });
  }

  // Cập nhật tên tệp CSV khi chọn
  if (importCsvFileInput) {
    importCsvFileInput.addEventListener('change', () => {
      const files = importCsvFileInput.files;
      if (files.length > 0) {
        const names = Array.from(files).map(f => f.name).join(', ');
        importCsvFileName.textContent = `Đã chọn ${files.length} tệp: ${names}`;
        if (!importDbTitle.value) {
          const stem = files[0].name.replace(/\.[^/.]+$/, '');
          importDbTitle.value = stem.charAt(0).toUpperCase() + stem.slice(1);
          importDbId.value = stem.toLowerCase().replace(/[^a-z0-9]+/g, '_');
        }
      }
    });
  }

  // Xử lý gửi Form Nhập CSDL
  if (submitImportBtn) {
    submitImportBtn.addEventListener('click', handleImportSubmit);
  }
}

async function handleImportSubmit() {
  const title = importDbTitle.value.trim();
  const dbId = importDbId.value.trim();
  const desc = importDbDesc.value.trim();
  const icon = importDbIcon.value.trim() || '🗄️';

  if (!title || !dbId) {
    showImportError('Vui lòng nhập đầy đủ Tên hiển thị và Mã CSDL (ID).');
    return;
  }

  importModalError.classList.add('hidden');
  importModalProgress.classList.remove('hidden');
  submitImportBtn.disabled = true;

  try {
    let response;

    if (activeImportTab === 'sql') {
      const sqlScript = importSqlTextarea.value.trim();
      if (!sqlScript) {
        throw new Error('Vui lòng nhập kịch bản SQL.');
      }
      response = await fetch('/api/database/import/sql', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          db_id: dbId,
          title: title,
          description: desc,
          icon: icon,
          sql_script: sqlScript,
        }),
      });
    } else if (activeImportTab === 'sqlite') {
      const file = importSqliteFileInput.files[0];
      if (!file) {
        throw new Error('Vui lòng chọn tệp SQLite.');
      }
      const formData = new FormData();
      formData.append('file', file);
      formData.append('db_id', dbId);
      formData.append('title', title);
      formData.append('description', desc);
      formData.append('icon', icon);

      response = await fetch('/api/database/import/sqlite', {
        method: 'POST',
        body: formData,
      });
    } else if (activeImportTab === 'csv') {
      const files = importCsvFileInput.files;
      if (!files || files.length === 0) {
        throw new Error('Vui lòng chọn ít nhất một tệp CSV.');
      }
      const formData = new FormData();
      Array.from(files).forEach(f => formData.append('files', f));
      formData.append('db_id', dbId);
      formData.append('title', title);
      formData.append('description', desc);
      formData.append('icon', icon);

      response = await fetch('/api/database/import/csv', {
        method: 'POST',
        body: formData,
      });
    }

    if (!response.ok) {
      const errData = await response.json();
      throw new Error(errData.detail || 'Lỗi khi nhập CSDL');
    }

    const resJson = await response.json();
    const newDb = resJson.database;

    // Cập nhật cấu hình và danh sách dropdown CSDL
    if (!appConfig.databases) appConfig.databases = [];
    appConfig.databases = appConfig.databases.filter(d => d.id !== newDb.id);
    appConfig.databases.push(newDb);

    // Render lại bộ chọn database
    dbSelect.innerHTML = appConfig.databases
      .map(db => `<option value="${db.id}">${db.icon} ${db.title} (${db.id})</option>`)
      .join('');

    // Chọn ngay CSDL mới
    dbSelect.value = newDb.id;

    // Đóng Modal
    importDbModal.classList.add('hidden');

    // Tạo phiên hội thoại mới cho CSDL vừa nhập
    createNewSession();

    // Reset Form
    importDbTitle.value = '';
    importDbId.value = '';
    importDbDesc.value = '';
    importSqlTextarea.value = '';
    if (importSqliteFileInput) importSqliteFileInput.value = '';
    if (importCsvFileInput) importCsvFileInput.value = '';
    importSqliteFileName.textContent = 'Bấm để chọn tệp .sqlite hoặc .db';
    importCsvFileName.textContent = 'Bấm để chọn một hoặc nhiều tệp .csv';

  } catch (err) {
    showImportError(err.message);
  } finally {
    importModalProgress.classList.add('hidden');
    submitImportBtn.disabled = false;
  }
}

function showImportError(msg) {
  importModalErrorText.textContent = msg;
  importModalError.classList.remove('hidden');
}

// ---------------------------------------------------------------------------
// 7. Quản lý Quá trình Tư duy & Đồ thị quan hệ bảng (DE / DA Thinking)
// ---------------------------------------------------------------------------
window.toggleThinkingProcess = function (msgId) {
  const box = document.getElementById(`${msgId}_thinking_box`);
  const arrow = document.getElementById(`${msgId}_toggle_arrow`);
  const output = document.getElementById(`${msgId}_output`);
  if (!box) return;

  const isHidden = box.classList.contains('hidden');
  if (isHidden) {
    box.classList.remove('hidden');
    box.classList.add('is-overview');
    if (output) output.classList.add('hidden');
    if (arrow) arrow.style.transform = 'rotate(180deg)';
    // Tổng quan chỉ hiển thị timeline; không lặp chi tiết của từng tab.
    for (let i = 1; i <= 4; i++) {
      const row = document.getElementById(`${msgId}_think_row_${i}`);
      const content = document.getElementById(`${msgId}_think_content_${i}`);
      const rowArrow = document.getElementById(`${msgId}_think_arrow_${i}`);
      if (row) row.classList.remove('hidden');
      if (content) {
        content.classList.add('hidden');
        if (rowArrow) rowArrow.style.transform = 'rotate(0deg)';
      }
    }
  } else {
    // Quay về tab người dùng xem gần nhất, mặc định là Kết quả.
    selectStepTab(msgId, Number(box.dataset.activeStep || 4));
  }
  lucide.createIcons();
};

window.selectStepTab = function (msgId, stepNum) {
  const box = document.getElementById(`${msgId}_thinking_box`);
  const arrow = document.getElementById(`${msgId}_toggle_arrow`);
  const output = document.getElementById(`${msgId}_output`);
  if (!box || !output) return;

  const isResult = stepNum === 4;
  box.dataset.activeStep = String(stepNum);
  output.classList.toggle('hidden', !isResult);
  box.classList.toggle('hidden', isResult);
  box.classList.remove('is-overview');
  if (arrow) arrow.style.transform = isResult ? 'rotate(0deg)' : 'rotate(180deg)';

  for (let i = 1; i <= 4; i++) {
    const node = document.getElementById(`${msgId}_step_${i}`);
    const row = document.getElementById(`${msgId}_think_row_${i}`);
    const content = document.getElementById(`${msgId}_think_content_${i}`);
    const rowArrow = document.getElementById(`${msgId}_think_arrow_${i}`);
    if (node) {
      node.classList.toggle('is-selected', i === stepNum);
      node.setAttribute('aria-selected', String(i === stepNum));
    }
    if (row) row.classList.toggle('hidden', i !== stepNum || isResult);
    if (content) {
      content.classList.toggle('hidden', i !== stepNum || isResult);
      if (rowArrow) rowArrow.style.transform = i === stepNum && !isResult ? 'rotate(180deg)' : 'rotate(0deg)';
    }
  }
  lucide.createIcons();
};

window.toggleStepRow = function (msgId, stepNum) {
  const content = document.getElementById(`${msgId}_think_content_${stepNum}`);
  const arrow = document.getElementById(`${msgId}_think_arrow_${stepNum}`);
  if (!content) return;

  const isHidden = content.classList.contains('hidden');
  if (isHidden) {
    content.classList.remove('hidden');
    if (arrow) arrow.style.transform = 'rotate(180deg)';
  } else {
    content.classList.add('hidden');
    if (arrow) arrow.style.transform = 'rotate(0deg)';
  }
  lucide.createIcons();
};

function renderStepThinking(msgId, stepNum, thinking, status) {
  const dot = document.getElementById(`${msgId}_think_dot_${stepNum}`);
  const content = document.getElementById(`${msgId}_think_content_${stepNum}`);
  if (!content) return;

  if (dot) {
    dot.className = 'w-2 h-2 rounded-full';
    if (status === 'done') dot.classList.add('bg-emerald-500');
    else if (status === 'failed' || status === 'blocked') dot.classList.add('bg-rose-500');
    else if (status === 'warning') dot.classList.add('bg-amber-500');
    else dot.classList.add('bg-blue-500');
  }

  let html = '';

  if (stepNum === 1) {
    // Bước 1: Schema & Evidence
    const tables = thinking.available_tables || [];
    const fks = thinking.catalog_foreign_keys || [];
    const evidence = thinking.evidence_applied || [];
    const sampleCols = thinking.sample_columns || {};
    const grainInfo = thinking.grain_info || {};
    const valueDict = thinking.value_dictionary || {};
    const relDetails = thinking.relationship_details || [];

    html = `
      <div class="space-y-2.5">
        <div class="flex items-center gap-1.5 text-slate-700 font-medium">
          <i data-lucide="database" class="w-3.5 h-3.5 text-indigo-600"></i>
          <span>Danh sách bảng trong Schema:</span>
          <span class="font-mono text-xs bg-slate-100 px-2 py-0.5 rounded text-indigo-700">${tables.join(', ') || 'Không có bảng'}</span>
        </div>
        ${
          evidence.length > 0
            ? `<div class="p-2 rounded bg-amber-50 border border-amber-200/70 text-[11px] text-amber-800">
                <span class="font-semibold">Quy tắc nghiệp vụ (Evidence):</span> ${escapeHtml(evidence.join('; '))}
              </div>`
            : ''
        }
        ${
          Object.keys(grainInfo).length > 0
            ? `<div class="bg-violet-50/80 border border-violet-200/80 rounded-lg p-2.5 space-y-1.5">
                <div class="flex items-center gap-1.5 text-violet-800 font-semibold text-[11px]">
                  <i data-lucide="layers" class="w-3.5 h-3.5 text-violet-600"></i>
                  <span>Độ hạt dữ liệu (Grain Analysis - 1 dòng đại diện cho thực thể gì):</span>
                </div>
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-1.5 text-[10.5px]">
                  ${Object.entries(grainInfo)
                    .map(
                      ([tbl, gDesc]) => `
                    <div class="bg-white/90 rounded px-2 py-1 border border-violet-100 flex items-start gap-1.5 shadow-2xs">
                      <span class="font-mono font-bold text-violet-900 shrink-0">${escapeHtml(tbl)}:</span>
                      <span class="text-slate-600 leading-tight">${escapeHtml(gDesc)}</span>
                    </div>
                  `
                    )
                    .join('')}
                </div>
              </div>`
            : ''
        }
        ${
          Object.keys(valueDict).length > 0
            ? `<div class="bg-sky-50/80 border border-sky-200/80 rounded-lg p-2.5 space-y-1.5">
                <div class="flex items-center gap-1.5 text-sky-800 font-semibold text-[11px]">
                  <i data-lucide="book-open" class="w-3.5 h-3.5 text-sky-600"></i>
                  <span>Từ điển giá trị hợp lệ (Value Dictionary - Tránh bịa literal):</span>
                </div>
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-1.5 text-[10.5px]">
                  ${Object.entries(valueDict)
                    .map(
                      ([col, vals]) => `
                    <div class="bg-white/90 rounded px-2 py-1 border border-sky-100 space-y-1 shadow-2xs">
                      <span class="font-mono font-bold text-sky-900 text-[10.5px]">${escapeHtml(col)}</span>
                      <div class="flex flex-wrap gap-1">
                        ${vals
                          .map(
                            v =>
                              `<span class="bg-sky-100 text-sky-800 px-1.5 py-0.2 rounded font-mono text-[9.5px]">${escapeHtml(
                                String(v)
                              )}</span>`
                          )
                          .join('')}
                      </div>
                    </div>
                  `
                    )
                    .join('')}
                </div>
              </div>`
            : ''
        }
        ${
          relDetails.length > 0
            ? `<div class="bg-indigo-50/70 border border-indigo-200/80 rounded-lg p-2.5 space-y-1.5">
                <div class="flex items-center justify-between text-indigo-800 font-semibold text-[11px]">
                  <div class="flex items-center gap-1.5">
                    <i data-lucide="git-branch" class="w-3.5 h-3.5 text-indigo-600"></i>
                    <span>Bản đồ quan hệ khóa ngoại (Relationship Catalog):</span>
                  </div>
                  <span class="text-[10px] text-indigo-600 bg-indigo-100/70 px-2 py-0.5 rounded font-mono">${relDetails.length} quan hệ</span>
                </div>
                <div class="space-y-1 max-h-36 overflow-y-auto pr-1">
                  ${relDetails
                    .map(
                      r => `
                    <div class="bg-white/90 border border-indigo-100 rounded px-2 py-0.5 text-[10.5px] flex items-center justify-between font-mono shadow-2xs">
                      <span><span class="text-slate-800 font-bold">${escapeHtml(r.from_table || '')}.${escapeHtml(
                        r.from_column || ''
                      )}</span> <span class="text-indigo-500 font-sans">→</span> <span class="text-slate-800 font-bold">${escapeHtml(
                        r.to_table || ''
                      )}.${escapeHtml(r.to_column || '')}</span></span>
                      <span class="text-[9.5px] text-indigo-700 font-sans bg-indigo-50 px-1 rounded">${escapeHtml(
                        r.type || 'N:1'
                      )}</span>
                    </div>
                  `
                    )
                    .join('')}
                </div>
              </div>`
            : ''
        }
        ${
          Object.keys(sampleCols).length > 0
            ? `<div class="bg-white p-2 rounded border border-slate-200">
                <div class="text-[10.5px] font-semibold text-slate-500 uppercase tracking-wide mb-1">Cột thuộc tính nhận diện:</div>
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-1 text-[11px]">
                  ${Object.entries(sampleCols)
                    .map(
                      ([tbl, cols]) =>
                        `<div><span class="font-mono font-semibold text-slate-700">${escapeHtml(tbl)}</span>: <span class="text-slate-500 font-mono text-[10px]">${escapeHtml(cols.join(', '))}</span></div>`
                    )
                    .join('')}
                </div>
              </div>`
            : ''
        }
        <div class="text-[10.5px] text-slate-400">
          Khóa ngoại đã quét trong Catalog: <span class="font-mono text-slate-600">${fks.length} quan hệ FK</span>
        </div>
      </div>
    `;
  } else if (stepNum === 2) {
    // Bước 2: Steiner Join Graph & Whiteboard Visual Canvas
    const refTables = thinking.referenced_tables || [];
    const edges = thinking.steiner_edges || [];
    const bridgeTables = thinking.bridge_tables || [];
    const warnings = thinking.graph_warnings || [];
    const canvasId = `whiteboard_${msgId}`;

    // Tạo danh sách nodes từ thinking.graph_nodes hoặc tự suy luận
    let nodes = thinking.graph_nodes;
    if (!nodes || nodes.length === 0) {
      const allGraphTables = Array.from(
        new Set([
          ...refTables,
          ...edges.map(e => e.left),
          ...edges.map(e => e.right),
          ...bridgeTables,
        ])
      );
      nodes = allGraphTables.map(tbl => {
        const isBridge = bridgeTables.includes(tbl);
        return {
          id: tbl,
          label: tbl,
          role: isBridge ? 'bridge' : (refTables.includes(tbl) ? 'primary' : 'dimension'),
          is_bridge: isBridge,
          key_columns: ['id'],
          total_columns: 5,
          all_columns: ['id', 'name', 'status'],
        };
      });
    }

    // HTML cho Infinite Canvas với Toolbar, Viewport, Surface, SVG Connectors và Nodes
    html = `
      <div class="space-y-3">
        <!-- Interactive Whiteboard Canvas -->
        <div id="${canvasId}" class="whiteboard-canvas">
          <!-- Top Control Header -->
          <div class="flex items-center justify-between px-3 py-2 border-b border-slate-200/80 bg-white/70 backdrop-blur-xs">
            <div class="flex items-center gap-2">
              <span class="whiteboard-badge text-indigo-700 bg-indigo-50 border-indigo-200">
                <i data-lucide="layout-grid" class="w-3.5 h-3.5 text-indigo-600"></i>
                <span>Infinite Whiteboard Canvas</span>
              </span>
              <span class="text-[10.5px] text-slate-500 font-medium hidden sm:inline">Kéo thả thẻ bảng • Thu phóng & Di chuyển vô hạn</span>
            </div>
            <div class="flex items-center gap-1.5">
              <span class="text-[10px] text-emerald-700 font-semibold bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full flex items-center gap-1">
                <i data-lucide="shield-check" class="w-3 h-3 text-emerald-600"></i>
                <span>KMB Steiner Tree</span>
              </span>
              <button type="button" class="px-2 py-1 rounded hover:bg-slate-100 text-slate-600 border border-slate-200 text-xs flex items-center gap-1" title="Toàn màn hình bảng trắng" onclick="toggleCanvasFullscreen('${canvasId}')">
                <i data-lucide="maximize-2" class="w-3.5 h-3.5"></i>
                <span class="text-[10.5px] font-medium hidden sm:inline">Phóng to</span>
              </button>
            </div>
          </div>

          <!-- The Pan & Zoom Viewport -->
          <div id="${canvasId}_viewport" class="whiteboard-viewport">
            <!-- Surface containing nodes and SVG layer -->
            <div id="${canvasId}_surface" class="whiteboard-surface">
              <svg id="${canvasId}_svg" class="whiteboard-svg-layer">
                <defs>
                  <marker id="${canvasId}_arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                    <path d="M 0 1 L 10 5 L 0 9 z" fill="#6366f1" />
                  </marker>
                  <marker id="${canvasId}_arrow_bridge" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                    <path d="M 0 1 L 10 5 L 0 9 z" fill="#10b981" />
                  </marker>
                </defs>
                <g id="${canvasId}_paths"></g>
              </svg>
              <div id="${canvasId}_badges"></div>
              <div id="${canvasId}_nodes"></div>
            </div>

            <!-- Floating Canvas Toolbar -->
            <div class="whiteboard-toolbar">
              <button class="whiteboard-toolbar-btn" title="Thu phóng lớn hơn (+)" onclick="zoomWhiteboard('${canvasId}', 1.2)">
                <i data-lucide="zoom-in" class="w-3.5 h-3.5"></i>
              </button>
              <button class="whiteboard-toolbar-btn" title="Thu nhỏ (-)" onclick="zoomWhiteboard('${canvasId}', 0.83)">
                <i data-lucide="zoom-out" class="w-3.5 h-3.5"></i>
              </button>
              <button class="whiteboard-toolbar-btn" title="Căn giữa & Khôi phục (Reset)" onclick="resetWhiteboard('${canvasId}')">
                <i data-lucide="rotate-ccw" class="w-3.5 h-3.5"></i>
              </button>
            </div>
          </div>

          <!-- Bottom Summary & Join Predicates -->
          <div class="p-3 bg-white border-t border-slate-200/70 text-[11px] space-y-2">
            ${
              bridgeTables.length > 0
                ? `<div class="p-2 bg-emerald-50/90 rounded-lg border border-emerald-200 text-[11px] text-emerald-800 flex items-center gap-2">
                    <i data-lucide="git-merge" class="w-3.5 h-3.5 text-emerald-600 shrink-0"></i>
                    <span><strong>Bảng cầu nối an toàn (Bridge Table):</strong> Tự động bổ sung <em>${escapeHtml(
                      bridgeTables.join(', ')
                    )}</em> vào đường đi tối ưu nhằm tránh rủi ro Fanout Cartesian.</span>
                  </div>`
                : ''
            }
            ${
              edges.length > 0
                ? `<div class="space-y-1">
                    <div class="text-[10px] font-semibold text-slate-400 uppercase tracking-wide">Mệnh đề nối bảng suy luận (Steiner ON Predicates):</div>
                    ${edges
                      .map(
                        e => `
                      <div class="font-mono text-[10.5px] bg-slate-50 border border-slate-200/80 rounded px-2 py-1 text-slate-700 flex items-center justify-between">
                        <span>${escapeHtml(e.left)} <strong class="text-indigo-600">JOIN</strong> ${escapeHtml(e.right)} <strong class="text-indigo-600">ON</strong> ${escapeHtml(e.on_clause)}</span>
                        <span class="text-[9.5px] text-indigo-700 font-semibold bg-indigo-50 border border-indigo-200 px-1.5 py-0.2 rounded">${escapeHtml(e.cardinality || 'N:1')}</span>
                      </div>
                    `
                      )
                      .join('')}
                  </div>`
                : `<div class="text-slate-500 italic">Truy vấn trên bảng đơn (Single-table query). Không phát sinh phép nối.</div>`
            }
          </div>
        </div>
      </div>
    `;

    // Lên lịch render Canvas engine sau khi DOM đã được mount
    setTimeout(() => {
      initInteractiveWhiteboard(canvasId, nodes, edges);
    }, 50);
  } else if (stepNum === 3) {
    // Bước 3: AST Policy & Security Checklist
    const checklist = thinking.checklist || [];
    const findings = thinking.findings || [];

    html = `
      <div class="space-y-2">
        <div class="text-[10.5px] font-semibold text-slate-500 uppercase tracking-wide">
          Bảng kiểm tra An toàn Cú pháp & Ngăn chặn Rủi ro:
        </div>
        <div class="grid grid-cols-1 gap-1.5">
          ${checklist
            .map(item => {
              const isPass = item.status === 'passed';
              const isWarn = item.status === 'warning';
              const badgeClass = isPass
                ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                : isWarn
                ? 'bg-amber-50 text-amber-700 border-amber-200'
                : 'bg-rose-50 text-rose-700 border-rose-200';
              const iconName = isPass ? 'check-circle' : isWarn ? 'alert-triangle' : 'shield-alert';

              return `
                <div class="p-2 rounded-lg border ${badgeClass} flex items-start justify-between gap-2">
                  <div class="flex items-start gap-1.5">
                    <i data-lucide="${iconName}" class="w-3.5 h-3.5 shrink-0 mt-0.5"></i>
                    <div>
                      <div class="font-semibold text-[11px]">${escapeHtml(item.rule)}</div>
                      <div class="text-[10px] opacity-85">${escapeHtml(item.detail)}</div>
                    </div>
                  </div>
                  <span class="px-1.5 py-0.5 rounded text-[9.5px] font-bold uppercase tracking-wider ${
                    isPass ? 'bg-emerald-100/70' : isWarn ? 'bg-amber-100/70' : 'bg-rose-100/70'
                  }">
                    ${isPass ? 'HỢP LỆ' : isWarn ? 'CẢNH BÁO' : 'TỪ CHỐI'}
                  </span>
                </div>
              `;
            })
            .join('')}
        </div>
      </div>
    `;
  } else if (stepNum === 4) {
    // Bước 4: Execution & Stats
    const rows = thinking.rows_returned || 0;
    const lat = thinking.execution_latency_ms || 1;
    const total = thinking.total_elapsed_seconds || 1;

    html = `
      <div class="flex items-center gap-4 flex-wrap text-slate-700 bg-white p-2.5 rounded-lg border border-slate-200 text-[11px]">
        <div>
          <span class="text-slate-400">Số dòng kết quả:</span>
          <span class="font-mono font-bold text-indigo-700 ml-1">${rows}</span>
        </div>
        <div class="border-l border-slate-200 pl-4">
          <span class="text-slate-400">Thời gian thực thi DB:</span>
          <span class="font-mono font-bold text-slate-800 ml-1">${lat}ms</span>
        </div>
        <div class="border-l border-slate-200 pl-4">
          <span class="text-slate-400">Tổng thời gian Pipeline:</span>
          <span class="font-mono font-bold text-emerald-600 ml-1">${total}s</span>
        </div>
      </div>
    `;
  }

  content.innerHTML = html;
  lucide.createIcons();
}

// ---------------------------------------------------------------------------
// 8. Whiteboard Canvas Engine (Infinite Canvas, Drag-and-Drop, Dynamic Connectors)
// ---------------------------------------------------------------------------
const _canvasStates = {};

function initInteractiveWhiteboard(canvasId, nodes, edges) {
  const container = document.getElementById(canvasId);
  const viewport = document.getElementById(`${canvasId}_viewport`);
  const surface = document.getElementById(`${canvasId}_surface`);
  const nodesContainer = document.getElementById(`${canvasId}_nodes`);
  const pathsGroup = document.getElementById(`${canvasId}_paths`);
  const badgesContainer = document.getElementById(`${canvasId}_badges`);

  if (!viewport || !surface || !nodesContainer) return;

  // Khởi tạo state cho canvas này
  const state = {
    canvasId,
    panX: 40,
    panY: 30,
    scale: 1,
    isPanning: false,
    isDraggingNode: false,
    startMouseX: 0,
    startMouseY: 0,
    activeNodeId: null,
    nodeDragOffset: { x: 0, y: 0 },
    nodes: {},
    edges: edges || [],
  };
  _canvasStates[canvasId] = state;

  // Tính toán vị trí ban đầu (Layout) cho các node
  const count = nodes.length;
  const viewportWidth = viewport.clientWidth || 600;
  const startX = 50;
  const spacingX = Math.max(220, Math.min(280, (viewportWidth - 100) / Math.max(1, count - 1)));

  nodes.forEach((n, idx) => {
    // Sắp xếp dạng luồng từ trái sang phải hoặc zigzag nếu nhiều node
    const col = idx % 3;
    const row = Math.floor(idx / 3);
    const x = startX + col * 240;
    const y = 40 + row * 130;
    state.nodes[n.id] = {
      ...n,
      x: x,
      y: y,
      width: 190,
      height: 90,
    };
  });

  // Render HTML thẻ bảng (Node Cards)
  let nodesHtml = '';
  Object.values(state.nodes).forEach(n => {
    const isBridge = n.role === 'bridge' || n.is_bridge;
    const headerClass = isBridge ? 'bridge' : (n.role === 'primary' ? 'primary' : 'dimension');
    const badgeText = isBridge ? 'Cầu nối' : (n.role === 'primary' ? 'Truy vấn' : 'Tham chiếu');

    nodesHtml += `
      <div id="${canvasId}_node_${n.id}" class="canvas-node table-node-card" style="left: ${n.x}px; top: ${n.y}px;" onmousedown="onNodeMouseDown(event, '${canvasId}', '${n.id}')">
        <div class="table-node-header ${headerClass}">
          <span class="flex items-center gap-1.5 truncate">
            <i data-lucide="table" class="w-3.5 h-3.5 shrink-0"></i>
            <span class="truncate">${escapeHtml(n.label || n.id)}</span>
          </span>
          <span class="text-[9px] px-1.5 py-0.2 rounded font-mono font-medium ${isBridge ? 'bg-emerald-100 text-emerald-800' : 'bg-indigo-100 text-indigo-800'}">${badgeText}</span>
        </div>
        <div class="table-node-body space-y-1">
          <div class="key-col">
            <i data-lucide="key" class="w-3 h-3 text-indigo-500 shrink-0"></i>
            <span class="truncate">Khóa: ${escapeHtml((n.key_columns && n.key_columns.length > 0) ? n.key_columns.join(', ') : 'id')}</span>
          </div>
          <div class="text-[9.5px] text-slate-400 flex items-center justify-between border-t border-slate-100 pt-1">
            <span>Tổng cột: ${n.total_columns || 5}</span>
            <span class="text-[9px] text-indigo-500 font-semibold cursor-grab">⠿ Kéo</span>
          </div>
        </div>
      </div>
    `;
  });
  nodesContainer.innerHTML = nodesHtml;
  lucide.createIcons();

  // Đo đạc kích thước thực tế sau khi DOM xuất hiện
  setTimeout(() => {
    Object.keys(state.nodes).forEach(id => {
      const el = document.getElementById(`${canvasId}_node_${id}`);
      if (el) {
        state.nodes[id].width = el.offsetWidth || 190;
        state.nodes[id].height = el.offsetHeight || 90;
      }
    });
    updateCanvasTransform(canvasId);
    redrawConnectors(canvasId);
  }, 30);

  // Sự kiện Viewport Panning (Kéo nền canvas)
  viewport.addEventListener('mousedown', (e) => {
    if (state.isDraggingNode) return;
    state.isPanning = true;
    state.startMouseX = e.clientX - state.panX;
    state.startMouseY = e.clientY - state.panY;
    viewport.style.cursor = 'grabbing';
  });

  window.addEventListener('mousemove', (e) => {
    if (state.isPanning) {
      state.panX = e.clientX - state.startMouseX;
      state.panY = e.clientY - state.startMouseY;
      updateCanvasTransform(canvasId);
    } else if (state.isDraggingNode && state.activeNodeId) {
      const node = state.nodes[state.activeNodeId];
      if (node) {
        // Tọa độ đã chia cho scale
        const mouseXInSurface = (e.clientX - viewport.getBoundingClientRect().left - state.panX) / state.scale;
        const mouseYInSurface = (e.clientY - viewport.getBoundingClientRect().top - state.panY) / state.scale;

        node.x = Math.round(mouseXInSurface - state.nodeDragOffset.x);
        node.y = Math.round(mouseYInSurface - state.nodeDragOffset.y);

        const nodeEl = document.getElementById(`${canvasId}_node_${node.id}`);
        if (nodeEl) {
          nodeEl.style.left = `${node.x}px`;
          nodeEl.style.top = `${node.y}px`;
        }
        redrawConnectors(canvasId);
      }
    }
  });

  window.addEventListener('mouseup', () => {
    if (state.isPanning) {
      state.isPanning = false;
      viewport.style.cursor = 'grab';
    }
    if (state.isDraggingNode) {
      if (state.activeNodeId) {
        const nodeEl = document.getElementById(`${canvasId}_node_${state.activeNodeId}`);
        if (nodeEl) nodeEl.classList.remove('is-dragging');
      }
      state.isDraggingNode = false;
      state.activeNodeId = null;
      viewport.classList.remove('is-dragging-node');
    }
  });

  // Sự kiện Wheel (Thu phóng bằng con lăn chuột)
  viewport.addEventListener('wheel', (e) => {
    e.preventDefault();
    const zoomFactor = e.deltaY < 0 ? 1.1 : 0.9;
    zoomWhiteboard(canvasId, zoomFactor, e.clientX, e.clientY);
  }, { passive: false });

  updateCanvasTransform(canvasId);
  redrawConnectors(canvasId);
}

// Bắt đầu kéo một Node
window.onNodeMouseDown = function (e, canvasId, nodeId) {
  e.stopPropagation(); // Ngăn mousedown nổi bọt lên canvas viewport
  const state = _canvasStates[canvasId];
  if (!state) return;

  const node = state.nodes[nodeId];
  if (!node) return;

  state.isDraggingNode = true;
  state.activeNodeId = nodeId;

  const viewport = document.getElementById(`${canvasId}_viewport`);
  const rect = viewport.getBoundingClientRect();
  const mouseXInSurface = (e.clientX - rect.left - state.panX) / state.scale;
  const mouseYInSurface = (e.clientY - rect.top - state.panY) / state.scale;

  state.nodeDragOffset.x = mouseXInSurface - node.x;
  state.nodeDragOffset.y = mouseYInSurface - node.y;

  viewport.classList.add('is-dragging-node');
  const nodeEl = document.getElementById(`${canvasId}_node_${nodeId}`);
  if (nodeEl) nodeEl.classList.add('is-dragging');
};

// Cập nhật vị trí bề mặt surface (CSS transform pan + zoom)
function updateCanvasTransform(canvasId) {
  const state = _canvasStates[canvasId];
  const surface = document.getElementById(`${canvasId}_surface`);
  if (!state || !surface) return;

  surface.style.transform = `translate(${state.panX}px, ${state.panY}px) scale(${state.scale})`;
}

// Vẽ lại các đường nối SVG Bezier & Cardinality Badges
function redrawConnectors(canvasId) {
  const state = _canvasStates[canvasId];
  const pathsGroup = document.getElementById(`${canvasId}_paths`);
  const badgesContainer = document.getElementById(`${canvasId}_badges`);
  if (!state || !pathsGroup || !badgesContainer) return;

  let pathsHtml = '';
  let badgesHtml = '';

  state.edges.forEach((edge, idx) => {
    const leftNode = state.nodes[edge.left];
    const rightNode = state.nodes[edge.right];
    if (!leftNode || !rightNode) return;

    // Xác định điểm bắt đầu và kết thúc
    let x1, y1, x2, y2;
    if (leftNode.x + leftNode.width < rightNode.x) {
      // Trái sang Phải
      x1 = leftNode.x + leftNode.width;
      y1 = leftNode.y + leftNode.height / 2;
      x2 = rightNode.x;
      y2 = rightNode.y + rightNode.height / 2;
    } else if (rightNode.x + rightNode.width < leftNode.x) {
      // Phải sang Trái
      x1 = leftNode.x;
      y1 = leftNode.y + leftNode.height / 2;
      x2 = rightNode.x + rightNode.width;
      y2 = rightNode.y + rightNode.height / 2;
    } else {
      // Trên dưới
      x1 = leftNode.x + leftNode.width / 2;
      y1 = leftNode.y + (leftNode.y < rightNode.y ? leftNode.height : 0);
      x2 = rightNode.x + rightNode.width / 2;
      y2 = rightNode.y + (leftNode.y < rightNode.y ? 0 : rightNode.height);
    }

    // Tính đường cong Cubic Bezier mượt mà
    const dx = Math.abs(x2 - x1) * 0.5;
    const dy = Math.abs(y2 - y1) * 0.2;
    const cx1 = x1 + (x2 >= x1 ? dx : -dx);
    const cy1 = y1;
    const cx2 = x2 - (x2 >= x1 ? dx : -dx);
    const cy2 = y2;

    const pathD = `M ${x1} ${y1} C ${cx1} ${cy1}, ${cx2} ${cy2}, ${x2} ${y2}`;
    const isBridgeEdge = (leftNode.is_bridge || rightNode.is_bridge);
    const strokeColor = isBridgeEdge ? '#10b981' : '#6366f1';
    const markerId = isBridgeEdge ? `${canvasId}_arrow_bridge` : `${canvasId}_arrow`;

    pathsHtml += `
      <path d="${pathD}" class="connector-line ${isBridgeEdge ? 'bridge' : ''}" marker-end="url(#${markerId})" />
    `;

    // Tọa độ badge ở trung điểm đường cong (t = 0.5 trên Bezier curve)
    const midX = 0.125 * x1 + 0.375 * cx1 + 0.375 * cx2 + 0.125 * x2;
    const midY = 0.125 * y1 + 0.375 * cy1 + 0.375 * cy2 + 0.125 * y2;

    badgesHtml += `
      <div class="edge-badge ${isBridgeEdge ? 'border-emerald-400 text-emerald-700' : ''}" style="left: ${midX}px; top: ${midY}px;">
        ${escapeHtml(edge.cardinality || 'N:1')}
      </div>
    `;
  });

  pathsGroup.innerHTML = pathsHtml;
  badgesContainer.innerHTML = badgesHtml;
}

// Hàm Thu phóng Canvas
window.zoomWhiteboard = function (canvasId, factor, clientX, clientY) {
  const state = _canvasStates[canvasId];
  const viewport = document.getElementById(`${canvasId}_viewport`);
  if (!state || !viewport) return;

  const oldScale = state.scale;
  const newScale = Math.min(2.2, Math.max(0.4, oldScale * factor));
  if (Math.abs(newScale - oldScale) < 0.001) return;

  const rect = viewport.getBoundingClientRect();
  const originX = (clientX !== undefined ? clientX - rect.left : viewport.clientWidth / 2);
  const originY = (clientY !== undefined ? clientY - rect.top : viewport.clientHeight / 2);

  // Điều chỉnh pan để điểm chuột giữ nguyên vị trí
  state.panX = originX - (originX - state.panX) * (newScale / oldScale);
  state.panY = originY - (originY - state.panY) * (newScale / oldScale);
  state.scale = newScale;

  updateCanvasTransform(canvasId);
};

// Căn giữa & Khôi phục mặc định
window.resetWhiteboard = function (canvasId) {
  const state = _canvasStates[canvasId];
  if (!state) return;
  state.panX = 40;
  state.panY = 30;
  state.scale = 1;
  updateCanvasTransform(canvasId);
  redrawConnectors(canvasId);
};

// Bật / tắt chế độ toàn màn hình cho bảng trắng
window.toggleCanvasFullscreen = function (canvasId) {
  const container = document.getElementById(canvasId);
  if (!container) return;
  const isFull = container.classList.toggle('is-fullscreen');

  // Đổi biểu tượng nút fullscreen nếu có
  setTimeout(() => {
    resetWhiteboard(canvasId);
  }, 100);
};

// ---------------------------------------------------------------------------
// 9. Khởi động ứng dụng
// ---------------------------------------------------------------------------
window.addEventListener('DOMContentLoaded', () => {
  init();
  initImportModal();
});
