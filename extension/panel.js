// TODO: make proxy URL configurable (env var or extension settings page)
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

// Shared context manager keeps storage and host-page messaging together.
const contextManager = new ContextManager();

function renderContextView(context) {
  if (!context) {
    contextView.textContent = 'No context stored.';
    return;
  }
  contextView.textContent = JSON.stringify(context, null, 2);
}

// button loading states
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

// Close button collapses the sidebar via postMessage to content.js
closeBtn.addEventListener('click', () => {
  window.parent.postMessage({ type: 'CLINICAL_ALLY_CLOSE' }, '*');
});

// ── Context controls ─────────────────────────────────────
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

// Gather context button: fetch HTML, send to backend, store
gatherContextBtn.addEventListener('click', async () => {
  setContextButtonsLoading(true);
  try {
    const html = await contextManager.requestPageHtml();
    if (!html) throw new Error('Unable to read page HTML.');

    const currentContext = await contextManager.getStoredContext();
    const resp = await fetch(`${API_URL}/process-context`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': API_KEY,
      },
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

// Clear shared context.
clearContextBtn.addEventListener('click', async () => {
  await contextManager.clearStoredContext();
  if (contextVisible) renderContextView(null);
});

autofillBtn.addEventListener('click', async () => {
  setAutofillLoading(true);

  try {
    const storedContext = await contextManager.getStoredContext();
    if (!storedContext) {
      throw new Error('No stored context found. Gather context first.');
    }

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
  if (isRecording) {
    mediaRecorder.stop();
    return;
  }

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

  mediaRecorder.ondataavailable = (e) => {
    if (e.data.size > 0) audioChunks.push(e.data);
  };

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
  } catch (err) {
    appendMessage(`Transcription error: ${err.message}`, 'error');
  } finally {
    setLoading(false);
    voiceBtn.disabled = false;
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

  responseArea.appendChild(container);
  container.scrollIntoView({ behavior: 'smooth', block: 'end' });
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();

  const prompt = input.value.trim();
  if (!prompt) return;

  // Display user message
  appendMessage(prompt, 'user');
  input.value = '';

  // Loading state
  setLoading(true);

  try {
    // get context from storage to include in API request
    const storedContext = await contextManager.getStoredContext();

    const body = {
      prompt,
      context: storedContext,
    };

    // TODO Sprint 3: maintain conversation history (send prior turns to proxy)
    const resp = await fetch(`${API_URL}/generate-str`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': API_KEY,
        'Accept': 'text/event-stream'
      },
      body: JSON.stringify(body)
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(err.detail || `HTTP ${resp.status}`);
    }

    const msgDiv = appendMessage('', 'assistant');
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let streamDone = false;

    setLoading(false);

    while (!streamDone) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop(); // keep incomplete last line

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const payload = line.slice(6).trim();
        if (payload === '[DONE]') {
          streamDone = true;
          break;
        }
        try {
          const token = JSON.parse(payload);
          msgDiv.textContent += token;
          msgDiv.scrollIntoView({ behavior: 'smooth', block: 'end' });
        } catch {
          // malformed chunk — skip
        }
      }
    }

    // flush any token remaining in buffer if stream ended without a trailing newline
    if (buffer.startsWith('data: ')) {
      const payload = buffer.slice(6).trim();
      if (payload && payload !== '[DONE]') {
        try {
          msgDiv.textContent += JSON.parse(payload);
        } catch {
          // malformed chunk — skip
        }
      }
    }
    reader.cancel();
  } catch (err) {
    appendMessage(`Error: ${err.message}`, 'error');
  } finally {
    setLoading(false);
  }
});

function appendMessage(text, role) {
  const div = document.createElement('div');
  div.className = `message ${role}`;
  div.textContent = text;
  responseArea.appendChild(div);
  div.scrollIntoView({ behavior: 'smooth', block: 'end' });
  return div;
}

// autofill messages for demo pursepose 
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

function setLoading(loading) {
  sendBtn.disabled = loading;
  input.disabled = loading;
  spinner.classList.toggle('hidden', !loading);
}
