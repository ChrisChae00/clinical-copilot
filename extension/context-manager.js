// ContextManager
// Shares chat context in memory across open Clinical Ally panels.
// Nothing is written to extension storage or persisted after the session.

(function () {
  'use strict';

  const CHANNEL_NAME = 'clinical-ally-context';
  const SYNC_WAIT_MS = 100;

  class ContextManager {
    constructor() {
      this.context = '';
      this.updatedAt = 0;
      this.channel = new BroadcastChannel(CHANNEL_NAME);

      this.ready = new Promise((resolve) => {
        this.resolveReady = resolve;
        setTimeout(resolve, SYNC_WAIT_MS);
      });

      this.channel.addEventListener('message', (event) => {
        this.handleMessage(event.data);
      });

      this.channel.postMessage({ type: 'REQUEST_CONTEXT' });
    }

    async getContext() {
      await this.ready;
      return this.context;
    }

    setContext(context) {
      this.context = context || '';
      this.updatedAt = Date.now();
      this.broadcastContext();
      this.resolveReady();
    }

    clearContext() {
      this.context = '';
      this.updatedAt = Date.now();
      this.broadcastContext();
      this.resolveReady();
    }

    broadcastContext() {
      this.channel.postMessage({
        type: 'CONTEXT_STATE',
        context: this.context,
        updatedAt: this.updatedAt,
      });
    }

    handleMessage(message) {
      if (message?.type === 'REQUEST_CONTEXT') {
        this.broadcastContext();
        return;
      }

      if (message?.type !== 'CONTEXT_STATE') return;
      if (typeof message.updatedAt !== 'number') return;
      if (message.updatedAt < this.updatedAt) return;

      this.context = typeof message.context === 'string' ? message.context : '';
      this.updatedAt = message.updatedAt;

      if (this.updatedAt > 0) this.resolveReady();
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
  }

  window.ContextManager = ContextManager;
})();
