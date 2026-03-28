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

// Close button collapses the sidebar via postMessage to content.js
closeBtn.addEventListener('click', () => {
  window.parent.postMessage({ type: 'CLINICAL_ALLY_CLOSE' }, '*');
});

// TODO: Implement voice input functionality
// 1. Check for browser support (e.g., window.SpeechRecognition || window.webkitSpeechRecognition).
// 2. Request microphone permissions from the user.
// 3. Initialize the Web Speech API and start listening for audio input.
// 4. Provide visual feedback (e.g., pulsating mic icon, color change) while recording.
// 5. Handle the 'result' event: extract the transcript and append it to `input.value`.
// 6. Handle errors (e.g., 'not-allowed', 'no-speech') gracefully.
// 7. Stop recognition when the user stops speaking or clicks the button again.
voiceBtn.addEventListener('click', () => {
  console.log('Voice input requested. Functionality is pending implementation.');
});

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
    // TODO Sprint 2: attach patient context extracted from current EMR page
    // TODO Sprint 2: enable streaming (ReadableStream) for faster perceived response
    // TODO Sprint 2: maintain conversation history (send prior turns to proxy)
    const resp = await fetch(`${API_URL}/generate-str`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': API_KEY
      },
      body: JSON.stringify({ prompt })
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
