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

// ── Patient context ───────────────────────────────────────────
const EXTENSION_ORIGIN = new URL(browser.runtime.getURL('')).origin;

// Returns a Promise that resolves to the current EMR context (or null on timeout).
// Sends REQUEST_CONTEXT to the host page and waits up to timeoutMs for a response.
function requestContext(timeoutMs = 500) {
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      window.removeEventListener('message', handler);
      console.warn('[ClinicalAlly] Context response timed out — proceeding without patient context');
      resolve(null);
    }, timeoutMs);

    function handler(event) {
      if (event.origin !== EXTENSION_ORIGIN) return;
      if (event.data?.type !== 'CONTEXT_RESPONSE') return;
      clearTimeout(timer);
      window.removeEventListener('message', handler);
      resolve(event.data.context);
    }

    window.addEventListener('message', handler);
    window.parent.postMessage({ type: 'REQUEST_CONTEXT' }, EXTENSION_ORIGIN);
  });
}

// Close button collapses the sidebar via postMessage to content.js
closeBtn.addEventListener('click', () => {
  window.parent.postMessage({ type: 'CLINICAL_ALLY_CLOSE' }, '*');
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
    // Fetch fresh context on every submission so the AI sees the current form state
    const context = await requestContext();

    const body = { prompt };
    if (context && context.page_type !== 'unknown') {
      body.context = context;
    }

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

function setLoading(loading) {
  sendBtn.disabled = loading;
  input.disabled = loading;
  spinner.classList.toggle('hidden', !loading);
}
