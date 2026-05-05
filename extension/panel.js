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
let patientContext = null;

// Request context from the host page (content.js) on load
window.parent.postMessage({ type: 'REQUEST_CONTEXT' }, '*');

window.addEventListener('message', (event) => {
  if (event.data?.type === 'CONTEXT_RESPONSE') {
    patientContext = event.data.context;
  }
});

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
  mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });

  mediaRecorder.ondataavailable = (e) => {
    if (e.data.size > 0) audioChunks.push(e.data);
  };

  mediaRecorder.onstop = async () => {
    stream.getTracks().forEach((t) => t.stop());
    voiceBtn.classList.remove('recording');
    isRecording = false;
    const blob = new Blob(audioChunks, { type: 'audio/webm' });
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
    // Build request body — include extracted patient context if available
    const body = { prompt };
    if (patientContext && Object.keys(patientContext).length > 0) {
      body.context = patientContext;
    }

    // TODO Sprint 2: enable streaming (ReadableStream) for faster perceived response
    // TODO Sprint 3: maintain conversation history (send prior turns to proxy)
    const resp = await fetch(`${API_URL}/generate-str`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': API_KEY
      },
      body: JSON.stringify(body)
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(err.detail || `HTTP ${resp.status}`);
    }

    const data = await resp.json();
    appendMessage(data, 'assistant');
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
}

function setLoading(loading) {
  sendBtn.disabled = loading;
  input.disabled = loading;
  spinner.classList.toggle('hidden', !loading);
}
