const API_URL = 'http://localhost:8000';
const API_KEY = 'api-key-placeholder';
const client = new Client({ apiUrl: API_URL, apiKey: API_KEY });

const form = document.getElementById('prompt-form');
const input = document.getElementById('prompt-input');
const sendBtn = document.getElementById('send-btn');
const voiceBtn = document.getElementById('voice-btn');
const responseArea = document.getElementById('response-area');
const spinner = document.getElementById('spinner');
const closeBtn = document.getElementById('close-btn');
const viewContextBtn = document.getElementById('view-context-btn');
const clearContextBtn = document.getElementById('clear-context-btn');
const contextView = document.getElementById('context-view');
const includeHtmlToggle = document.getElementById('include-html-toggle');
const attachImageBtn = document.getElementById('attach-image-btn');
const imageInput = document.getElementById('image-input');
const imagePreviewList = document.getElementById('image-preview-list');

const contextManager = new ContextManager();
const domBridge = new DomBridge();
const imageManager = new ImageManager({
  attachButton: attachImageBtn,
  fileInput: imageInput,
  pasteTarget: input,
  previewList: imagePreviewList,
  onError: (err) => appendMessage(`Image attach error: ${err.message}`, 'error'),
});

let lastUserPrompt = '';
let lastUserImagesB64 = [];

// ── Context controls ──────────────────────────────────────────

function renderContextView(context) {
  if (!context) {
    contextView.textContent = 'No context yet — start chatting.';
    return;
  }
  contextView.textContent = context;
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
    renderContextView(contextManager.getContext());
  }
});


clearContextBtn.addEventListener('click', async () => {
  contextManager.clearContext();
  if (contextVisible) renderContextView(null);
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
    const { segments } = await client.transcribe(blob);
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
    const context = await resolveChatContext();
    const { summary, actions } = await client.analyzeTranscript({
      segments,
      context: context || undefined,
    });
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

// ── Chat form ─────────────────────────────────────────────────

async function resolveChatContext() {
  let context = contextManager.getContext();

  if (!context) {
    const contextObj = await domBridge.requestContext();
    context = contextManager.serializeContextToPatientInfo(contextObj);
    contextManager.setContext(context);
  }

  return context || '';
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const prompt = input.value.trim();
  if (!prompt) return;

  const imagesToSend = imageManager.getImages();
  lastUserPrompt = prompt;
  lastUserImagesB64 = imagesToSend.map((image) => image.b64);

  const imageCountLabel = imagesToSend.length
    ? ` (${imagesToSend.length} image${imagesToSend.length === 1 ? '' : 's'} attached)`
    : '';

  appendMessage(`${prompt}${imageCountLabel}`, 'user');
  input.value = '';
  setLoading(true);

  try {
    const chatContext = await resolveChatContext();
    const includeRawHtml = Boolean(includeHtmlToggle?.checked);
    const raw_html = includeRawHtml ? await domBridge.requestPageHtml() : '';

    const { response, updated_context, actions } = await client.chat({
      prompt,
      context: chatContext || undefined,
      raw_html: raw_html || undefined,
      images_b64: imagesToSend.length ? imagesToSend.map((image) => image.b64) : undefined,
    });
    appendMessage(response, 'assistant');
    imageManager.clear();

    if (updated_context) contextManager.setContext(updated_context);
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
  const supportedActions = (actions || []).filter((action) => action === 'autofill');
  if (!supportedActions.length) return;

  const container = document.createElement('div');
  container.className = 'message assistant action-suggestions';

  const label = document.createElement('div');
  label.className = 'action-suggestions-label';
  label.textContent = 'Suggested actions:';
  container.appendChild(label);

  supportedActions.forEach((action) => {
    if (action === 'autofill') {
      container.appendChild(createAutofillActionCard());
    }
  });

  responseArea.appendChild(container);
  container.scrollIntoView({ behavior: 'smooth', block: 'end' });
}

function createAutofillActionCard() {
  const card = document.createElement('div');
  card.className = 'autofill-action-card';

  const title = document.createElement('div');
  title.className = 'autofill-action-title';
  title.textContent = ACTION_LABELS.autofill;
  card.appendChild(title);

  const description = document.createElement('div');
  description.className = 'autofill-action-description';
  description.textContent = 'Run this to scan the current page fields and fill supported values from the current context.';
  card.appendChild(description);

  const extraPrompt = document.createElement('textarea');
  extraPrompt.className = 'autofill-extra-prompt';
  extraPrompt.rows = 3;
  extraPrompt.placeholder = 'Optional: add extra instructions for this autofill run.';
  card.appendChild(extraPrompt);

  const runBtn = document.createElement('button');
  runBtn.className = 'autofill-run-btn';
  runBtn.type = 'button';
  runBtn.textContent = 'Run autofill';
  runBtn.addEventListener('click', async () => {
    runBtn.disabled = true;
    runBtn.textContent = 'Running autofill…';

    try {
      await runAutofillAction(extraPrompt.value.trim());
      runBtn.textContent = 'Autofill complete';
    } catch (err) {
      appendMessage(`Autofill error: ${err.message}`, 'error');
      runBtn.disabled = false;
      runBtn.textContent = 'Run autofill';
    }
  });
  card.appendChild(runBtn);

  return card;
}

async function runAutofillAction(extraPrompt) {
  const context = await resolveChatContext();
  const prompt = [
    lastUserPrompt,
    extraPrompt ? `Additional autofill instructions: ${extraPrompt}` : '',
  ].filter(Boolean).join('\n\n');
  const images_b64 = [
    ...lastUserImagesB64,
    ...imageManager.getImagesBase64(),
  ];

  const result = await domBridge.requestAutofill({
    apiUrl: API_URL,
    apiKey: API_KEY,
    context,
    prompt,
    images_b64,
  });

  appendAutofillMessage(result);
  imageManager.clear();
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
          const currentContext = await resolveChatContext();
          const { draft } = await client.draftAction({
            action,
            context: currentContext || undefined,
          });
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
  imageManager.setDisabled(loading);
  spinner.classList.toggle('hidden', !loading);
}
