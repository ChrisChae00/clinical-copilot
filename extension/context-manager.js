// ContextManager
// Stores chat context in memory for the current panel runtime only.
// Nothing is written to extension storage.

(function () {
  'use strict';

  class ContextManager {
    constructor() {
      this.context = '';
    }

    getContext() {
      return this.context;
    }

    setContext(context) {
      this.context = context || '';
    }

    clearContext() {
      this.context = '';
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
