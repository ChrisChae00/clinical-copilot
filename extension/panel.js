const API_URL = 'http://localhost:8000';
const API_KEY = 'api-key-placeholder';

const form = document.getElementById('prompt-form');
const input = document.getElementById('prompt-input');
const sendBtn = document.getElementById('send-btn');
const voiceBtn = document.getElementById('voice-btn');
const responseArea = document.getElementById('response-area');
const spinner = document.getElementById('spinner');
const closeBtn = document.getElementById('close-btn');
const gatherContextBtn = document.getElementById('gather-context-btn');
const autofillBtn = document.getElementById('autofill-btn');
const viewContextBtn = document.getElementById('view-context-btn');
const clearContextBtn = document.getElementById('clear-context-btn');
const contextView = document.getElementById('context-view');
const drawerToggleBtn = document.getElementById('drawer-toggle-btn');
const newChatBtn = document.getElementById('new-chat-btn');
const threadDrawer = document.getElementById('thread-drawer');
const threadList = document.getElementById('thread-list');
const threadSearchBar = document.getElementById('thread-search-bar');
const threadSearch = document.getElementById('thread-search');

const contextManager = new ContextManager();
const historyManager = new HistoryManager();

// ── Boot ──────────────────────────────────────────────────────

async function initHistory() {
  await historyManager.createThread();
  await renderThreadList();
  await renderActiveThread();
}

async function renderThreadList() {
  const state = await historyManager._load();
  const threads = Object.values(state.threads)
    .sort((a, b) => b.updatedAt - a.updatedAt);
  threadList.replaceChildren();
  threads.forEach(({ id, title }) => {
    const item = document.createElement('div');
    item.className = `thread-item${id === state.activeThreadId ? ' active' : ''}`;
    item.dataset.id = id;
    item.setAttribute('role', 'listitem');

    const titleSpan = document.createElement('span');
    titleSpan.className = 'thread-item-title';
    titleSpan.textContent = title;
    titleSpan.title = title;

    const delBtn = document.createElement('button');
    delBtn.className = 'thread-delete-btn';
    delBtn.textContent = '\xd7';
    delBtn.setAttribute('aria-label', `Delete ${title}`);
    delBtn.addEventListener('click', async (e) => {
      e.stopPropagation();
      await historyManager.deleteThread(id);
      await renderThreadList();
      await renderActiveThread();
    });

    item.appendChild(titleSpan);
    item.appendChild(delBtn);

    item.addEventListener('click', async () => {
      await historyManager.setActive(id);
      await renderThreadList();
      await renderActiveThread();
    });

    titleSpan.addEventListener('dblclick', (e) => {
      e.stopPropagation();
      titleSpan.contentEditable = 'true';
      titleSpan.focus();
      const range = document.createRange();
      range.selectNodeContents(titleSpan);
      window.getSelection().removeAllRanges();
      window.getSelection().addRange(range);
    });

    titleSpan.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); titleSpan.blur(); }
      if (e.key === 'Escape') {
        titleSpan.contentEditable = 'false';
        titleSpan.textContent = title;
      }
    });

    titleSpan.addEventListener('blur', async () => {
      if (titleSpan.contentEditable !== 'true') return;
      titleSpan.contentEditable = 'false';
      const newTitle = titleSpan.textContent.trim();
      if (newTitle && newTitle !== title) {
        await historyManager.renameThread(id, newTitle);
        await renderThreadList();
      }
    });

    threadList.appendChild(item);
  });
}

async function renderActiveThread() {
  const state = await historyManager._load();
  const thread = await historyManager.getThread(state.activeThreadId);
  responseArea.replaceChildren();
  if (!thread) return;
  thread.messages.forEach(({ role, text }, i) => appendMessage(text, role, i));
}

initHistory();

// ── Header controls ───────────────────────────────────────────

drawerToggleBtn.addEventListener('click', () => {
  const isHidden = threadDrawer.classList.toggle('hidden');
  threadSearchBar.classList.toggle('hidden', isHidden);
});

newChatBtn.addEventListener('click', async () => {
  await historyManager.createThread();
  await renderThreadList();
  await renderActiveThread();
});

// ── Context controls ──────────────────────────────────────────

function renderContextView(context) {
  if (!context) {
    contextView.textContent = 'No context stored.';
    return;
  }
  contextView.textContent = JSON.stringify(context, null, 2);
}

function setContextButtonsLoading(loading) {
  gatherContextBtn.disabled = loading;
  autofillBtn.disabled = loading;
  clearContextBtn.disabled = loading;
  gatherContextBtn.textContent = loading ? 'Gathering...' : 'Gather context';
}

function setAutofillLoading(loading) {
  autofillBtn.disabled = loading;
  gatherContextBtn.disabled = loading;
  clearContextBtn.disabled = loading;
  autofillBtn.textContent = loading ? 'Autofilling...' : 'Autofill';
}

closeBtn.addEventListener('click', () => {
  window.parent.postMessage({ type: 'CLINICAL_ALLY_CLOSE' }, '*');
});

let contextVisible = false;

viewContextBtn.addEventListener('click', async () => {
  contextVisible = !contextVisible;
  contextView.classList.toggle('hidden', !contextVisible);
  viewContextBtn.textContent = contextVisible ? 'Hide context' : 'View context';
  if (contextVisible) {
    const storedContext = await contextManager.getStoredContext();
    renderContextView(storedContext);
  }
});

gatherContextBtn.addEventListener('click', async () => {
  setContextButtonsLoading(true);
  try {
    const html = await contextManager.requestPageHtml();
    if (!html) throw new Error('Unable to read page HTML.');
    const currentContext = await contextManager.getStoredContext();
    const resp = await fetch(`${API_URL}/process-context`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-API-Key': API_KEY },
      body: JSON.stringify({ html, context: currentContext }),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(err.detail || `HTTP ${resp.status}`);
    }
    const updatedContext = await resp.json();
    await contextManager.setStoredContext(updatedContext);
    if (contextVisible) renderContextView(updatedContext);
  } catch (err) {
    appendMessage(`Context error: ${err.message}`, 'error');
  } finally {
    setContextButtonsLoading(false);
  }
});

clearContextBtn.addEventListener('click', async () => {
  await contextManager.clearStoredContext();
  if (contextVisible) renderContextView(null);
});

autofillBtn.addEventListener('click', async () => {
  setAutofillLoading(true);
  try {
    const storedContext = await contextManager.getStoredContext();
    if (!storedContext) throw new Error('No stored context found. Gather context first.');
    const result = await contextManager.requestAutofill({
      apiUrl: API_URL,
      apiKey: API_KEY,
      context: storedContext,
      prompt: input.value.trim(),
    });
    appendAutofillMessage(result);
  } catch (err) {
    appendMessage(`Autofill error: ${err.message}`, 'error');
  } finally {
    setAutofillLoading(false);
  }
});

// ── Voice recording ───────────────────────────────────────────

let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;

voiceBtn.addEventListener('click', async () => {
  if (isRecording) { mediaRecorder.stop(); return; }
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch {
    appendMessage('Microphone access denied.', 'error');
    return;
  }
  audioChunks = [];
  const mimeType = MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : '';
  mediaRecorder = new MediaRecorder(stream, mimeType ? { mimeType } : {});
  mediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) audioChunks.push(e.data); };
  mediaRecorder.onstop = async () => {
    stream.getTracks().forEach((t) => t.stop());
    voiceBtn.classList.remove('recording');
    isRecording = false;
    const blob = new Blob(audioChunks, mimeType ? { type: mimeType } : {});
    await sendAudioForTranscription(blob);
  };
  mediaRecorder.start();
  isRecording = true;
  voiceBtn.classList.add('recording');
});

async function sendAudioForTranscription(blob) {
  setLoading(true);
  voiceBtn.disabled = true;
  try {
    const formData = new FormData();
    formData.append('audio', blob, 'recording.webm');
    const resp = await fetch(`${API_URL}/transcribe`, {
      method: 'POST',
      headers: { 'X-API-Key': API_KEY },
      body: formData,
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(err.detail || `HTTP ${resp.status}`);
    }
    const { segments } = await resp.json();
    appendTranscript(segments);
    analyzeTranscript(segments);
  } catch (err) {
    appendMessage(`Transcription error: ${err.message}`, 'error');
  } finally {
    setLoading(false);
    voiceBtn.disabled = false;
  }
}

async function analyzeTranscript(segments) {
  const analyzingDiv = appendMessage('Analyzing conversation for clinical actions…', 'assistant');
  analyzingDiv.classList.add('analyzing');

  try {
    const context = await requestContext();
    const body = { segments };
    if (context && context.page_type !== 'unknown') body.context = context;

    const resp = await fetch(`${API_URL}/analyze-transcript`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-API-Key': API_KEY },
      body: JSON.stringify(body),
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(err.detail || `HTTP ${resp.status}`);
    }

    const { summary, actions } = await resp.json();
    analyzingDiv.remove();
    appendClinicalActions(summary, actions || []);
  } catch (err) {
    analyzingDiv.textContent = `Analysis error: ${err.message}`;
    analyzingDiv.className = 'message error';
  }
}

function appendTranscript(segments) {
  const container = document.createElement('div');
  container.className = 'message transcript';
  segments.forEach(({ speaker, text }) => {
    const line = document.createElement('div');
    line.className = 'transcript-line';
    const label = document.createElement('span');
    label.className = 'speaker-label';
    label.textContent = `${speaker}: `;
    line.appendChild(label);
    line.appendChild(document.createTextNode(text));
    container.appendChild(line);
  });
  // Transcripts are display-only and not persisted to thread history (by design).
  responseArea.appendChild(container);
  container.scrollIntoView({ behavior: 'smooth', block: 'end' });
}

// ── Chat form ─────────────────────────────────────────────────

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const prompt = input.value.trim();
  if (!prompt) return;

  const state = await historyManager._load();
  const activeId = state.activeThreadId;
  if (!activeId) return;

  const threadBeforeSend = await historyManager.getThread(activeId);
  const userMsgIndex = threadBeforeSend ? threadBeforeSend.messages.length : 0;
  appendMessage(prompt, 'user', userMsgIndex);
  await historyManager.appendMessage(activeId, 'user', prompt);
  input.value = '';
  setLoading(true);
  setThreadLock(true);

  try {
    const storedContext = await contextManager.getStoredContext();
    const resp = await fetch(`${API_URL}/generate-str`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': API_KEY,
        'Accept': 'text/event-stream',
      },
      body: JSON.stringify({ prompt, context: storedContext }),
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(err.detail || `HTTP ${resp.status}`);
    }

    const assistantMsgIndex = userMsgIndex + 1;
    const msgDiv = appendMessage('', 'assistant', assistantMsgIndex);
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let streamDone = false;
    let assistantText = '';

    setLoading(false);

    while (!streamDone) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const payload = line.slice(6).trim();
        if (payload === '[DONE]') { streamDone = true; break; }
        try {
          const token = JSON.parse(payload);
          msgDiv.textContent += token;
          assistantText += token;
          msgDiv.scrollIntoView({ behavior: 'smooth', block: 'end' });
        } catch { /* malformed chunk */ }
      }
    }

    if (buffer.startsWith('data: ')) {
      const payload = buffer.slice(6).trim();
      if (payload && payload !== '[DONE]') {
        try {
          const token = JSON.parse(payload);
          msgDiv.textContent += token;
          assistantText += token;
        } catch { /* malformed chunk */ }
      }
    }
    reader.cancel();

    if (assistantText) {
      await historyManager.appendMessage(activeId, 'assistant', assistantText);
      await autoTitleIfNeeded(activeId, prompt, assistantText);
    }
  } catch (err) {
    appendMessage(`Error: ${err.message}`, 'error');
  } finally {
    setLoading(false);
    setThreadLock(false);
  }
});

async function autoTitleIfNeeded(threadId, userPrompt, assistantText) {
  const thread = await historyManager.getThread(threadId);
  if (!thread || thread.title !== 'New chat') return;
  try {
    const summaryPrompt =
      'Summarize this exchange in 6 words or fewer as a chat title. No punctuation.\n' +
      `User: ${userPrompt.slice(0, 200)}\nAssistant: ${assistantText.slice(0, 200)}`;
    const resp = await fetch(`${API_URL}/generate-str`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-API-Key': API_KEY },
      body: JSON.stringify({ prompt: summaryPrompt }),
    });
    if (!resp.ok) return;
    const raw = await resp.json();
    const title = String(raw).trim().replace(/^["']|["']$/g, '').slice(0, 60);
    if (title) {
      await historyManager.renameThread(threadId, title);
      await renderThreadList();
    }
  } catch (e) {
    console.warn('[ClinicalAlly] thread title generation failed:', e.message);
  }
}

// ── Thread search ─────────────────────────────────────────────

threadSearch.addEventListener('input', async () => {
  const query = threadSearch.value.trim();
  responseArea.querySelectorAll('.message').forEach(el => el.classList.remove('search-highlight'));
  if (!query) return;

  const state = await historyManager._load();
  const matchIndices = await historyManager.searchInThread(state.activeThreadId, query);
  if (!matchIndices.length) return;

  matchIndices.forEach(i => {
    const el = responseArea.querySelector(`[data-msg-index="${i}"]`);
    if (el) el.classList.add('search-highlight');
  });
  const firstEl = responseArea.querySelector(`[data-msg-index="${matchIndices[0]}"]`);
  if (firstEl) firstEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
});

// ── DOM helpers ───────────────────────────────────────────────

function appendMessage(text, role, msgIndex) {
  const div = document.createElement('div');
  div.className = `message ${role}`;
  div.textContent = text;
  if (msgIndex !== undefined) div.dataset.msgIndex = msgIndex;
  responseArea.appendChild(div);
  div.scrollIntoView({ behavior: 'smooth', block: 'end' });
  return div;
}

function appendAutofillMessage(result) {
  const applied = Array.isArray(result?.applied) ? result.applied : [];
  const skipped = Array.isArray(result?.skipped) ? result.skipped : [];
  const div = document.createElement('div');
  div.className = 'message assistant autofill-summary';
  const title = document.createElement('div');
  title.className = 'autofill-title';
  title.textContent = result?.message || (
    applied.length ? `Autofilled ${applied.length} fields.` : 'No fields were autofilled.'
  );
  div.appendChild(title);
  if (applied.length) {
    const list = document.createElement('ul');
    applied.forEach((field) => {
      const item = document.createElement('li');
      const label = field.label || field.field_id || 'Unlabeled field';
      const value = field.value == null || field.value === '' ? '' : `: ${field.value}`;
      item.textContent = `${label}${value}`;
      list.appendChild(item);
    });
    div.appendChild(list);
  }
  if (skipped.length) {
    const detail = document.createElement('div');
    detail.className = 'autofill-detail';
    detail.textContent = 'Skipped suggestions';
    div.appendChild(detail);
    const list = document.createElement('ul');
    skipped.forEach((field) => {
      const item = document.createElement('li');
      const label = field.label || field.field_id || 'Unlabeled field';
      const reason = field.reason ? `: ${field.reason}` : '';
      item.textContent = `${label}${reason}`;
      list.appendChild(item);
    });
    div.appendChild(list);
  }
  responseArea.appendChild(div);
  div.scrollIntoView({ behavior: 'smooth', block: 'end' });
  return div;
}

function appendClinicalActions(summary, actions) {
  const ACTION_TYPE_LABELS = {
    referral: 'Referral',
    lab_order: 'Lab Order',
    prescription: 'Prescription',
    follow_up: 'Follow-Up',
    imaging: 'Imaging',
    note: 'Note',
    alert: 'Alert',
  };
  const PRIORITY_LABELS = { high: 'Urgent', medium: 'Important', low: 'Routine' };

  const container = document.createElement('div');
  container.className = 'message clinical-actions';

  const header = document.createElement('div');
  header.className = 'actions-header';
  header.textContent = 'Suggested Clinical Actions';
  container.appendChild(header);

  if (summary) {
    const summaryEl = document.createElement('p');
    summaryEl.className = 'actions-summary';
    summaryEl.textContent = summary;
    container.appendChild(summaryEl);
  }

  if (actions.length === 0) {
    const none = document.createElement('p');
    none.className = 'actions-empty';
    none.textContent = 'No specific actions identified.';
    container.appendChild(none);
  } else {
    actions.forEach((action) => {
      const card = document.createElement('div');
      card.className = `action-card priority-${action.priority || 'low'}`;

      const cardHeader = document.createElement('div');
      cardHeader.className = 'action-card-header';

      const badge = document.createElement('span');
      badge.className = `action-badge priority-${action.priority || 'low'}`;
      badge.textContent = PRIORITY_LABELS[action.priority] || action.priority;

      const type = document.createElement('span');
      type.className = 'action-type';
      type.textContent = ACTION_TYPE_LABELS[action.type] || action.type;

      cardHeader.appendChild(badge);
      cardHeader.appendChild(type);
      card.appendChild(cardHeader);

      const title = document.createElement('div');
      title.className = 'action-title';
      title.textContent = action.title;
      card.appendChild(title);

      if (action.description) {
        const desc = document.createElement('div');
        desc.className = 'action-description';
        desc.textContent = action.description;
        card.appendChild(desc);
      }

      if (action.details && Object.keys(action.details).length > 0) {
        const detailsList = document.createElement('div');
        detailsList.className = 'action-details';
        Object.entries(action.details).forEach(([k, v]) => {
          const item = document.createElement('span');
          item.className = 'action-detail-item';
          const val = Array.isArray(v) ? v.join(', ') : v;
          item.textContent = `${k}: ${val}`;
          detailsList.appendChild(item);
        });
        card.appendChild(detailsList);
      }

      container.appendChild(card);
    });
  }

  responseArea.appendChild(container);
  container.scrollIntoView({ behavior: 'smooth', block: 'end' });
}

function setLoading(loading) {
  sendBtn.disabled = loading;
  input.disabled = loading;
  spinner.classList.toggle('hidden', !loading);
}

function setThreadLock(locked) {
  threadList.style.pointerEvents = locked ? 'none' : '';
}