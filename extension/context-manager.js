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
};
