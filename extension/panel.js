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
const contextStatus = document.getElementById('context-status');
const includeHtmlToggle = document.getElementById('include-html-toggle');
const includeScreenshotToggle = document.getElementById('include-screenshot-toggle');
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

let contextStatusTimer = null;

// Brief confirmation next to the context buttons (e.g. after clearing).
function showContextStatus(message) {
  clearTimeout(contextStatusTimer);
  contextStatus.textContent = message;
  contextStatus.classList.remove('hidden', 'fading');
  contextStatusTimer = setTimeout(() => {
    contextStatus.classList.add('fading');
    contextStatusTimer = setTimeout(() => {
      contextStatus.classList.add('hidden');
    }, 400);
  }, 1600);
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
    renderContextView(await contextManager.getContext());
  }
});


clearContextBtn.addEventListener('click', () => {
  contextManager.clearContext();
  if (contextVisible) renderContextView(null);
  showContextStatus('Context cleared ✓');
});

// ── Referral generation ───────────────────────────────────────

let referralDraftText = null;
let referralDraftCard = null;
let referralPulseTimer = null;

const REFERRAL_DRAFT_ACTION = {
  type: 'referral',
  title: 'Referral letter',
  description: '',
};

// Scrolls the whole draft card into view and flashes it so the user can see
// that a draft was just created or replaced.
function focusReferralCard(card) {
  card.scrollIntoView({ behavior: 'smooth', block: 'center' });

  clearTimeout(referralPulseTimer);
  card.classList.remove('highlight-pulse');
  void card.offsetWidth; // force reflow so repeat clicks restart the animation
  card.classList.add('highlight-pulse');
  referralPulseTimer = setTimeout(() => {
    card.classList.remove('highlight-pulse');
  }, 1500);
}

async function runReferralAction(description = '') {
  const context = await resolveChatContext();
  const { draft } = await client.draftAction({
    action: {
      ...REFERRAL_DRAFT_ACTION,
      description,
    },
    context: context || undefined,
  });

  if (referralDraftText) {
    referralDraftText.value = draft;
  } else {
    const created = appendReferralDraft(draft);
    referralDraftText = created.textarea;
    referralDraftCard = created.card;
  }

  focusReferralCard(referralDraftCard);
  return draft;
}

// Builds the referral draft card and returns { card, textarea } so subsequent
// regenerations can update it in place instead of stacking new cards.
function appendReferralDraft(draft) {
  const container = document.createElement('div');
  container.className = 'message assistant referral-card';

  const header = document.createElement('div');
  header.className = 'actions-header';
  header.textContent = 'Referral Letter';
  container.appendChild(header);

  const draftArea = document.createElement('div');
  draftArea.className = 'action-draft';

  const draftText = document.createElement('textarea');
  draftText.className = 'action-draft-text';
  draftText.rows = 12;
  draftText.value = draft;
  draftArea.appendChild(draftText);

  const buttonsRow = document.createElement('div');
  buttonsRow.className = 'action-buttons';

  const copyBtn = document.createElement('button');
  copyBtn.className = 'action-copy-btn';
  copyBtn.textContent = 'Copy';
  copyBtn.addEventListener('click', () => {
    navigator.clipboard.writeText(draftText.value).then(() => {
      copyBtn.textContent = 'Copied!';
      setTimeout(() => { copyBtn.textContent = 'Copy'; }, 1500);
    });
  });
  buttonsRow.appendChild(copyBtn);
  draftArea.appendChild(buttonsRow);

  container.appendChild(draftArea);
  responseArea.appendChild(container);
  return { card: container, textarea: draftText };
}

// ── Voice recording ───────────────────────────────────────────

let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;
let recordingInterval = null;
let liveTranscriptInterval = null;
let tempAudioContainer = null;

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
    clearInterval(liveTranscriptInterval);
    recordingIndicator.classList.add('hidden');
    input.classList.remove('hidden');

    const endNotice = appendMessage('Recording ended. Processing audio transcription…', 'assistant');

    const blob = new Blob(audioChunks, mimeType ? { type: mimeType } : {});
    await sendAudioForTranscription(blob);

    if (endNotice && endNotice.parentNode) {
      endNotice.remove();
    }
  };

  mediaRecorder.start(1000);
  isRecording = true;
  voiceBtn.classList.add('recording');

  input.classList.add('hidden');
  recordingIndicator.classList.remove('hidden');

  // temp container for live text
  tempAudioContainer = document.createElement('div');
  tempAudioContainer.className = 'message transcript temp';
  tempAudioContainer.style.opacity = '0.6'; // Visually distinguish it as a draft
  responseArea.appendChild(tempAudioContainer);

  let isTranscribingLive = false;
  liveTranscriptInterval = setInterval(async () => {
    // prevent overlapping requests
    if (audioChunks.length > 0 && !isTranscribingLive) {
      isTranscribingLive = true;
      const blob = new Blob(audioChunks, mimeType ? { type: mimeType } : {});
      try {
        const { segments } = await client.transcribe(blob);
        // only update UI if still recording
        if (isRecording) {
          renderInterimTranscript(segments, tempAudioContainer);
        }
      } catch (err) {
        console.warn('Live transcription skipped this tick due to error:', err);
      } finally {
        isTranscribingLive = false;
      }
    }
  }, 3000);

  // timer logic
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

    // remove live transcripting container
    if(tempAudioContainer && tempAudioContainer.parentNode){
      tempAudioContainer.remove();
      tempAudioContainer = null;
    }

    appendTranscript(segments);
    summarizeTranscript(segments);
    syncTranscriptToContext(segments);
  } catch (err) {
    appendMessage(`Transcription error: ${err.message}`, 'error');
  } finally {
    setLoading(false);
    voiceBtn.disabled = false;
  }
}

// Extracts patient/clinical info mentioned during the conversation into the
// accumulated context, then always offers an autofill suggestion so the user
// can enter whatever was picked up (eg. "the patient has diabetes") into the
// form with one click, without needing to ask for it explicitly.
async function syncTranscriptToContext(segments) {
  const transcriptText = segments.map(({ speaker, text }) => `${speaker}: ${text}`).join('\n');
  if (!transcriptText.trim()) return;

  try {
    const chatContext = await resolveChatContext();
    const { updated_context } = await client.chat({
      prompt: 'Extract any new patient or clinical information (diagnoses, symptoms, '
        + 'medications, allergies, vitals, history, etc.) mentioned in this conversation '
        + 'transcript and incorporate it into the accumulated context.\n\n'
        + '### CONVERSATION TRANSCRIPT ###\n' + transcriptText,
      context: chatContext || undefined,
    });
    if (updated_context) contextManager.setContext(updated_context);
  } catch (err) {
    appendMessage(`Could not extract context from transcript: ${err.message}`, 'error');
  }

  const container = document.createElement('div');
  container.className = 'message assistant action-suggestions';

  const label = document.createElement('div');
  label.className = 'action-suggestions-label';
  label.textContent = 'Suggested actions:';
  container.appendChild(label);

  container.appendChild(createAutofillActionCard(
    'Fill in any fields supported by the following conversation transcript. '
      + 'Only use info explicitly mentioned below — do not fill unrelated fields.\n\n'
      + '### CONVERSATION TRANSCRIPT ###\n' + transcriptText,
    'Detected patient/clinical details from this conversation. Run this to enter them into the form.',
  ));

  responseArea.appendChild(container);
  container.scrollIntoView({ behavior: 'smooth', block: 'end' });
}

// Replaces its own placeholder message in place, so the summary lands where the
// "Summarizing…" line was rather than after whatever else finished first.
async function summarizeTranscript(segments) {
  const div = appendMessage('Summarizing conversation…', 'assistant');

  try {
    const context = await resolveChatContext();
    const { summary } = await client.analyzeTranscript({
      segments,
      context: context || undefined,
    });
    if (!summary) {
      div.remove();
      return;
    }
    div.textContent = summary;
  } catch (err) {
    div.textContent = `Summary error: ${err.message}`;
    div.className = 'message error';
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
  let context = await contextManager.getContext();

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
  const includeRawHtml = Boolean(includeHtmlToggle?.checked);
  const includePageScreenshots = Boolean(includeScreenshotToggle?.checked);

  input.value = '';

  try {
    const chatContext = await resolveChatContext();
    const raw_html = includeRawHtml ? await domBridge.requestPageHtml() : '';
    const pageScreenshotsB64 = includePageScreenshots
      ? await domBridge.requestPageScreenshots()
      : [];
    const images_b64 = imagesToSend.map((image) => image.b64);
    const displayImages = imagesToSend.slice();

    pageScreenshotsB64.forEach((screenshotB64, index) => {
      images_b64.push(screenshotB64);
      displayImages.push({
        name: `Captured page segment ${index + 1} of ${pageScreenshotsB64.length}`,
        dataUrl: `data:image/jpeg;base64,${screenshotB64}`,
      });
    });

    lastUserImagesB64 = images_b64.slice();

    appendMessage(prompt, 'user', { images: displayImages });
    setLoading(true);

    const { response, updated_context, actions } = await client.chat({
      prompt,
      context: chatContext || undefined,
      raw_html: raw_html || undefined,
      images_b64: images_b64.length ? images_b64 : undefined,
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
  referral: 'Generate referral',
};

function renderActionSuggestions(actions) {
  const supportedActions = [...new Set(
    (actions || [])
      .map(normalizeActionName)
      .filter((action) => action && ACTION_LABELS[action])
  )];
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
    } else if (action === 'referral') {
      container.appendChild(createReferralActionCard());
    }
  });

  responseArea.appendChild(container);
  container.scrollIntoView({ behavior: 'smooth', block: 'end' });
}

function normalizeActionName(action) {
  const rawName = typeof action === 'string' ? action : action?.type;
  const normalized = String(rawName || '').trim().toLowerCase();
  const aliases = {
    generate_referral: 'referral',
    referral_letter: 'referral',
  };
  return aliases[normalized] || normalized;
}

// basePrompt: explicit instructions to seed the autofill run with (eg. a transcript).
// Pass null (default) to fall back to the last chat message the user typed.
// Pass '' explicitly to force AutofillManager's own "fill from context only" default.
function createAutofillActionCard(basePrompt = null, description = null) {
  const card = document.createElement('div');
  card.className = 'autofill-action-card';

  const title = document.createElement('div');
  title.className = 'autofill-action-title';
  title.textContent = ACTION_LABELS.autofill;
  card.appendChild(title);

  const descriptionEl = document.createElement('div');
  descriptionEl.className = 'autofill-action-description';
  descriptionEl.textContent = description
    || 'Run this to scan the current page fields and fill supported values from the current context.';
  card.appendChild(descriptionEl);

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
      await runAutofillAction(extraPrompt.value.trim(), basePrompt);
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

function createReferralActionCard() {
  const card = document.createElement('div');
  card.className = 'autofill-action-card referral-action-card';

  const title = document.createElement('div');
  title.className = 'autofill-action-title';
  title.textContent = ACTION_LABELS.referral;
  card.appendChild(title);

  const descriptionEl = document.createElement('div');
  descriptionEl.className = 'autofill-action-description';
  descriptionEl.textContent = 'Run this to draft a referral letter from the current patient context.';
  card.appendChild(descriptionEl);

  const extraPrompt = document.createElement('textarea');
  extraPrompt.className = 'autofill-extra-prompt';
  extraPrompt.rows = 3;
  extraPrompt.placeholder = 'Optional: add specialist, reason, urgency, or letter details.';
  card.appendChild(extraPrompt);

  const runBtn = document.createElement('button');
  runBtn.className = 'autofill-run-btn referral-run-btn';
  runBtn.type = 'button';
  runBtn.textContent = referralDraftText ? 'Regenerate referral' : 'Generate referral';
  runBtn.addEventListener('click', async () => {
    runBtn.disabled = true;
    runBtn.textContent = referralDraftText ? 'Regenerating referral...' : 'Generating referral...';

    const description = [
      lastUserPrompt,
      extraPrompt.value.trim()
        ? `Additional referral instructions: ${extraPrompt.value.trim()}`
        : '',
    ].filter(Boolean).join('\n\n');

    try {
      await runReferralAction(description);
      runBtn.textContent = 'Referral drafted';
    } catch (err) {
      appendMessage(`Referral error: ${err.message}`, 'error');
      runBtn.disabled = false;
      runBtn.textContent = referralDraftText ? 'Regenerate referral' : 'Generate referral';
    }
  });
  card.appendChild(runBtn);

  return card;
}

async function runAutofillAction(extraPrompt, basePrompt = null) {
  const context = await resolveChatContext();
  const prompt = [
    basePrompt === null ? lastUserPrompt : basePrompt,
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

function appendMessage(text, role, options = {}) {
  const div = document.createElement('div');
  div.className = `message ${role}`;

  if (role === 'user' && Array.isArray(options.images) && options.images.length > 0) {
    const textEl = document.createElement('div');
    textEl.className = 'message-text';
    textEl.textContent = text;
    div.appendChild(textEl);

    const imagesEl = document.createElement('div');
    imagesEl.className = 'message-images';
    options.images.forEach((image) => {
      const figure = document.createElement('figure');
      figure.className = 'message-image-item';

      const img = document.createElement('img');
      img.src = image.dataUrl;
      img.alt = image.name || 'Attached image';
      figure.appendChild(img);

      const caption = document.createElement('figcaption');
      caption.textContent = image.name || 'Attached image';
      figure.appendChild(caption);

      imagesEl.appendChild(figure);
    });

    div.appendChild(imagesEl);
  } else {
    div.textContent = text;
  }

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

function setLoading(loading) {
  sendBtn.disabled = loading;
  input.disabled = loading;
  imageManager.setDisabled(loading);
  spinner.classList.toggle('hidden', !loading);
}

function renderInterimTranscript(segments, container) {
  container.innerHTML = ''; //clear previous text
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
  container.scrollIntoView({ behavior: 'smooth', block: 'end' });
}
