// Context manager
// handles the context
// - requests context from content script
// - stores context in extension storage for access 
// - get, set, delete/clear stored context

window.ContextManager = class ContextManager {
  constructor(storageKey = 'clinicalAllyContext') {
    this.storageKey = storageKey;
    this.storage = browser.storage?.local;

    if (!this.storage) {
      throw new Error('Extension storage is unavailable. Context cannot be shared across windows.');
    }
  }

  _waitForMessage(messageType, responseKey, timeoutMs, requestType, timeoutLog) {
    return new Promise((resolve) => {
      const timer = setTimeout(() => {
        window.removeEventListener('message', handler);
        console.warn(timeoutLog);
        resolve(null);
      }, timeoutMs);

      function handler(event) {
        if (event.source !== window.parent) return;
        if (event.data?.type !== messageType) return;
        clearTimeout(timer);
        window.removeEventListener('message', handler);
        resolve(event.data[responseKey] || null);
      }

      window.addEventListener('message', handler);
      window.parent.postMessage({ type: requestType }, '*');
    });
  }

  requestContext(timeoutMs = 500) {
    return this._waitForMessage(
      'CONTEXT_RESPONSE',
      'context',
      timeoutMs,
      'REQUEST_CONTEXT',
      '[ClinicalAlly] Context response timed out — proceeding without patient context'
    );
  }

  requestPageHtml(timeoutMs = 1000) {
    return this._waitForMessage(
      'PAGE_HTML_RESPONSE',
      'html',
      timeoutMs,
      'REQUEST_PAGE_HTML',
      '[ClinicalAlly] Page HTML response timed out'
    );
  }

  requestAutofill(payload, timeoutMs = 120000) {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        window.removeEventListener('message', handler);
        reject(new Error('Autofill response timed out.'));
      }, timeoutMs);

      function handler(event) {
        if (event.source !== window.parent) return;
        if (event.data?.type !== 'AUTOFILL_RESPONSE') return;

        clearTimeout(timer);
        window.removeEventListener('message', handler);

        if (event.data.ok) {
          resolve(event.data.result);
        } else {
          reject(new Error(event.data.error || 'Autofill failed.'));
        }
      }

      window.addEventListener('message', handler);
      window.parent.postMessage({ type: 'REQUEST_AUTOFILL', ...payload }, '*');
    });
  }

  async getStoredContext() {
    const result = await this.storage.get(this.storageKey);
    return result?.[this.storageKey] ?? null;
  }

  async setStoredContext(context) {
    await this.storage.set({ [this.storageKey]: context });
  }

  async clearStoredContext() {
    await this.storage.remove(this.storageKey);
  }

  // ── Chat context (accumulated string for /chat endpoint) ──────

  get _chatContextKey() { return `${this.storageKey}_chat`; }

  async getChatContext() {
    const result = await this.storage.get(this._chatContextKey);
    return result?.[this._chatContextKey] ?? null;
  }

  async setChatContext(str) {
    await this.storage.set({ [this._chatContextKey]: str });
  }

  async clearChatContext() {
    await this.storage.remove(this._chatContextKey);
  }

  // Converts the JS object from extractOSCARContext() into the
  // ##patient info## string block the /chat endpoint expects.
  serializeContextToPatientInfo(contextObj) {
    if (!contextObj || typeof contextObj !== 'object') return '';

    const SKIP_KEYS = new Set(['page_url', 'page_title', 'extraction_error']);
    const lines = [];

    for (const [key, val] of Object.entries(contextObj)) {
      if (SKIP_KEYS.has(key) || val == null || val === '') continue;
      if (Array.isArray(val)) {
        lines.push(`${key}:`);
        val.forEach((item) => lines.push(`  - ${item}`));
      } else {
        lines.push(`${key}: ${val}`);
      }
    }

    if (!lines.length) return '';
    return '##patient info##\n' + lines.join('\n');
  }
};
