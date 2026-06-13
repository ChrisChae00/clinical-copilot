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
const attachBtn = document.getElementById('attach-btn');
const imageInput = document.getElementById('image-input');
const imagePreviews = document.getElementById('image-previews');

const contextManager = new ContextManager();

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
  await contextManager.clearChatContext();
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
let recordingInterval = null;

const recordingIndicator = document.getElementById('recording-visualizer');
const recordingTimer = document.getElementById('recording-timer');

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

    clearInterval(recordingInterval);
    recordingIndicator.classList.add('hidden');
    input.classList.remove('hidden');

    const endNotice = appendMessage('Recording ended. Processing audio transcription…', 'assistant');

    const blob = new Blob(audioChunks, mimeType ? { type: mimeType } : {});
    await sendAudioForTranscription(blob);

    if (endNotice && endNotice.parentNode) {
      endNotice.remove();
    }
  };

  mediaRecorder.start();
  isRecording = true;
  voiceBtn.classList.add('recording');

  input.classList.add('hidden');
  recordingIndicator.classList.remove('hidden');

  let elapsedSeconds = 0;
  recordingTimer.textContent = '00:00';
  recordingInterval = setInterval(() => {
    elapsedSeconds++;
    const mins = String(Math.floor(elapsedSeconds / 60)).padStart(2, '0');
    const secs = String(elapsedSeconds % 60).padStart(2, '0');
    recordingTimer.textContent = `${mins}:${secs}`;
  }, 1000);
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
    const context = await contextManager.getStoredContext();
    const body = { segments };
    if (context) body.context = context;

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
  responseArea.appendChild(container);
  container.scrollIntoView({ behavior: 'smooth', block: 'end' });
  return container;
}

// ── Image attachments ─────────────────────────────────────────
// Captured via file picker or clipboard paste, sent with the next
// chat message as base64 (no data-URI prefix — Ollama expects raw base64).

let pendingImages = [];
let imageIdCounter = 0;

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = reader.result;
      const comma = String(dataUrl).indexOf(',');
      resolve({ dataUrl, b64: String(dataUrl).slice(comma + 1) });
    };
    reader.onerror = () => reject(new Error('Could not read image file.'));
    reader.readAsDataURL(file);
  });
}

async function addImageFile(file) {
  if (!file || !file.type.startsWith('image/')) return;
  try {
    const { dataUrl, b64 } = await fileToBase64(file);
    pendingImages.push({ id: imageIdCounter++, dataUrl, b64 });
    renderImagePreviews();
  } catch (err) {
    appendMessage(`Image error: ${err.message}`, 'error');
  }
}

function removePendingImage(id) {
  pendingImages = pendingImages.filter((img) => img.id !== id);
  renderImagePreviews();
}

function renderImagePreviews() {
  imagePreviews.replaceChildren();
  pendingImages.forEach((img) => {
    const chip = document.createElement('div');
    chip.className = 'image-chip';

    const thumb = document.createElement('img');
    thumb.className = 'image-chip-thumb';
    thumb.src = img.dataUrl;
    thumb.alt = 'Attached image';
    chip.appendChild(thumb);

    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'image-chip-remove';
    remove.setAttribute('aria-label', 'Remove image');
    remove.textContent = '×';
    remove.addEventListener('click', () => removePendingImage(img.id));
    chip.appendChild(remove);

    imagePreviews.appendChild(chip);
  });
}

attachBtn.addEventListener('click', () => imageInput.click());

imageInput.addEventListener('change', async () => {
  for (const file of imageInput.files) await addImageFile(file);
  imageInput.value = ''; // allow re-selecting the same file
});

input.addEventListener('paste', async (e) => {
  const items = e.clipboardData?.items || [];
  for (const item of items) {
    if (item.type.startsWith('image/')) {
      const file = item.getAsFile();
      if (file) await addImageFile(file);
    }
  }
});

// ── Chat form ─────────────────────────────────────────────────

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const prompt = input.value.trim();
  if (!prompt) return;

  appendMessage(prompt, 'user');
  input.value = '';
  setLoading(true);

  try {
    // Build context string — use accumulated chat context if it exists,
    // otherwise seed from current page's patient info.
    let chatContext = await contextManager.getChatContext();
    if (!chatContext) {
      const contextObj = await contextManager.requestContext();
      chatContext = contextManager.serializeContextToPatientInfo(contextObj);
    }

    const raw_html = await contextManager.requestPageHtml();
    const images_b64 = pendingImages.map((img) => img.b64);

    const resp = await fetch(`${API_URL}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-API-Key': API_KEY },
      body: JSON.stringify({
        prompt,
        context: chatContext || undefined,
        raw_html: raw_html || undefined,
        images_b64: images_b64.length ? images_b64 : undefined,
      }),
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(err.detail || `HTTP ${resp.status}`);
    }

    const { response, updated_context, actions } = await resp.json();
    appendMessage(response, 'assistant');

    pendingImages = [];
    renderImagePreviews();

    if (updated_context) await contextManager.setChatContext(updated_context);
    if (actions?.length) renderActionSuggestions(actions);
  } catch (err) {
    appendMessage(`Error: ${err.message}`, 'error');
  } finally {
    setLoading(false);
  }
});

// ── Action suggestions ────────────────────────────────────────

const ACTION_LABELS = {
  autofill: 'Autofill form',
};

function renderActionSuggestions(actions) {
  const container = document.createElement('div');
  container.className = 'message assistant action-suggestions';

  const label = document.createElement('div');
  label.className = 'action-suggestions-label';
  label.textContent = 'Suggested actions:';
  container.appendChild(label);

  actions.forEach((action) => {
    const btn = document.createElement('button');
    btn.className = 'action-suggestion-btn';
    btn.textContent = ACTION_LABELS[action] || action;

    if (action === 'autofill') {
      btn.addEventListener('click', async () => {
        btn.disabled = true;
        setAutofillLoading(true);
        try {
          const storedContext = await contextManager.getStoredContext();
          if (!storedContext) throw new Error('No stored context. Use Gather context first.');
          const result = await contextManager.requestAutofill({
            apiUrl: API_URL,
            apiKey: API_KEY,
            context: storedContext,
            prompt: '',
          });
          appendAutofillMessage(result);
        } catch (err) {
          appendMessage(`Autofill error: ${err.message}`, 'error');
        } finally {
          setAutofillLoading(false);
        }
      });
    } else {
      btn.disabled = true;
      btn.title = 'Not yet supported';
    }

    container.appendChild(btn);
  });

  responseArea.appendChild(container);
  container.scrollIntoView({ behavior: 'smooth', block: 'end' });
}

// ── DOM helpers ───────────────────────────────────────────────

function appendMessage(text, role) {
  const div = document.createElement('div');
  div.className = `message ${role}`;
  div.textContent = text;
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

const DISMISS_REASONS = [
  'Not useful',
  'Irrelevant to this patient',
  'Already done',
  'Duplicate recommendation',
  'Other',
];

const DRAFT_BTN_LABELS = {
  referral: 'Draft Referral',
  lab_order: 'Draft Lab Order',
  prescription: 'Draft Prescription',
  follow_up: 'Draft Follow-Up Note',
  imaging: 'Draft Imaging Order',
  note: 'Draft Note',
  alert: 'Draft Alert',
};

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
    actions.forEach((action, actionIdx) => {
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

      // Draft area (hidden until generated)
      const draftArea = document.createElement('div');
      draftArea.className = 'action-draft hidden';

      const draftText = document.createElement('textarea');
      draftText.className = 'action-draft-text';
      draftText.readOnly = true;
      draftText.rows = 6;
      draftArea.appendChild(draftText);

      const copyBtn = document.createElement('button');
      copyBtn.className = 'action-copy-btn';
      copyBtn.textContent = 'Copy';
      copyBtn.addEventListener('click', () => {
        navigator.clipboard.writeText(draftText.value).then(() => {
          copyBtn.textContent = 'Copied!';
          setTimeout(() => { copyBtn.textContent = 'Copy'; }, 1500);
        });
      });
      draftArea.appendChild(copyBtn);
      card.appendChild(draftArea);

      // Dismiss reason area (hidden until dismiss clicked)
      const dismissArea = document.createElement('div');
      dismissArea.className = 'action-dismiss-area hidden';

      const dismissLabel = document.createElement('span');
      dismissLabel.className = 'action-dismiss-label';
      dismissLabel.textContent = 'Why are you dismissing this?';
      dismissArea.appendChild(dismissLabel);

      const dismissSelect = document.createElement('select');
      dismissSelect.className = 'action-dismiss-select';
      const defaultOpt = document.createElement('option');
      defaultOpt.value = '';
      defaultOpt.textContent = 'Select a reason…';
      dismissSelect.appendChild(defaultOpt);
      DISMISS_REASONS.forEach((reason) => {
        const opt = document.createElement('option');
        opt.value = reason;
        opt.textContent = reason;
        dismissSelect.appendChild(opt);
      });
      dismissArea.appendChild(dismissSelect);

      const dismissBtns = document.createElement('div');
      dismissBtns.className = 'action-dismiss-btns';

      const confirmDismissBtn = document.createElement('button');
      confirmDismissBtn.className = 'action-confirm-dismiss-btn';
      confirmDismissBtn.textContent = 'Confirm';
      confirmDismissBtn.addEventListener('click', () => {
        if (!dismissSelect.value) return;
        const reason = dismissSelect.value;
        card.classList.add('dismissed');
        buttonsRow.remove();
        dismissArea.remove();
        dismissReasonEl.textContent = `Dismissed: ${reason}`;
        dismissReasonEl.classList.remove('hidden');
      });
      dismissBtns.appendChild(confirmDismissBtn);

      const cancelDismissBtn = document.createElement('button');
      cancelDismissBtn.className = 'action-cancel-dismiss-btn';
      cancelDismissBtn.textContent = 'Cancel';
      cancelDismissBtn.addEventListener('click', () => {
        dismissArea.classList.add('hidden');
        buttonsRow.classList.remove('hidden');
      });
      dismissBtns.appendChild(cancelDismissBtn);
      dismissArea.appendChild(dismissBtns);
      card.appendChild(dismissArea);

      const dismissReasonEl = document.createElement('div');
      dismissReasonEl.className = 'action-dismiss-reason hidden';
      card.appendChild(dismissReasonEl);

      // Action buttons row
      const buttonsRow = document.createElement('div');
      buttonsRow.className = 'action-buttons';

      const draftBtn = document.createElement('button');
      draftBtn.className = 'action-draft-btn';
      draftBtn.textContent = DRAFT_BTN_LABELS[action.type] || 'Draft';
      draftBtn.addEventListener('click', async () => {
        draftBtn.disabled = true;
        draftBtn.textContent = 'Generating…';
        draftArea.classList.add('hidden');
        try {
          const storedContext = await contextManager.getStoredContext();
          const resp = await fetch(`${API_URL}/draft-action`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-API-Key': API_KEY },
            body: JSON.stringify({ action, context: storedContext }),
          });
          if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Unknown error' }));
            throw new Error(err.detail || `HTTP ${resp.status}`);
          }
          const { draft } = await resp.json();
          draftText.value = draft;
          draftArea.classList.remove('hidden');
          draftBtn.textContent = 'Regenerate';
        } catch (err) {
          draftText.value = `Error generating draft: ${err.message}`;
          draftArea.classList.remove('hidden');
          draftBtn.textContent = DRAFT_BTN_LABELS[action.type] || 'Draft';
        } finally {
          draftBtn.disabled = false;
        }
      });

      const dismissBtn = document.createElement('button');
      dismissBtn.className = 'action-dismiss-btn';
      dismissBtn.textContent = 'Dismiss';
      dismissBtn.addEventListener('click', () => {
        buttonsRow.classList.add('hidden');
        dismissArea.classList.remove('hidden');
      });

      buttonsRow.appendChild(draftBtn);
      buttonsRow.appendChild(dismissBtn);
      card.appendChild(buttonsRow);

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
