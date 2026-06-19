// Client
// Handles all API communication for the extension.

(function () {
  'use strict';

  class Client {
    constructor({ apiUrl = 'http://localhost:8000', apiKey = 'api-key-placeholder' } = {}) {
      this.apiUrl = apiUrl.replace(/\/$/, '');
      this.apiKey = apiKey;
    }

    async health() {
      return this._request('/health');
    }

    async chat({ prompt, context, raw_html, system_prompt, images_b64 } = {}) {
      return this._postJson('/chat', {
        prompt,
        context,
        raw_html,
        system_prompt,
        images_b64,
      });
    }

    async autofill({ prompt, context, images_b64, fields } = {}) {
      return this._postJson('/autofill', {
        prompt,
        context,
        images_b64,
        fields,
      });
    }

    async transcribe(audioBlob, filename = 'recording.webm') {
      const formData = new FormData();
      formData.append('audio', audioBlob, filename);

      return this._request('/transcribe', {
        method: 'POST',
        body: formData,
      });
    }

    async analyzeTranscript({ segments, context } = {}) {
      return this._postJson('/analyze-transcript', {
        segments,
        context,
      });
    }

    async draftAction({ action, context } = {}) {
      return this._postJson('/draft-action', {
        action,
        context,
      });
    }

    async _postJson(path, payload) {
      return this._request(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(this._withoutUndefined(payload)),
      });
    }

    async _request(path, options = {}) {
      const response = await fetch(`${this.apiUrl}${path}`, {
        ...options,
        headers: {
          'X-API-Key': this.apiKey,
          ...(options.headers || {}),
        },
      });

      if (!response.ok) {
        const errorBody = await response.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(errorBody.detail || `HTTP ${response.status}`);
      }

      return response.json();
    }

    _withoutUndefined(obj) {
      return Object.fromEntries(
        Object.entries(obj || {}).filter(([, value]) => value !== undefined)
      );
    }
  }

  window.Client = Client;
})();