// DomBridge
//
// bridge between the sidebar iframe and the host-page content script
// panel iframe cannot directly access the EMR page DOM, so page-level operations
// such as context extraction, raw HTML retrieval, and autofill must be requested
// through the content script.
//
// Keep this file focused on message passing only. DOM scraping and form mutation
// belong in content-script helpers such as AutofillManager.

(function () {
  'use strict';

  class DomBridge {
    requestContext(timeoutMs = 500) {
      return this.waitForParentResponse({
        requestType: 'REQUEST_CONTEXT',
        responseType: 'CONTEXT_RESPONSE',
        responseKey: 'context',
        timeoutMs,
        timeoutMessage: '[ClinicalAlly] Context response timed out — proceeding without patient context',
      });
    }

    requestPageHtml(timeoutMs = 1000) {
      return this.waitForParentResponse({
        requestType: 'REQUEST_PAGE_HTML',
        responseType: 'PAGE_HTML_RESPONSE',
        responseKey: 'html',
        timeoutMs,
        timeoutMessage: '[ClinicalAlly] Page HTML response timed out',
      });
    }

    requestPageScreenshots(timeoutMs = 60000) {
      return new Promise((resolve, reject) => {
        const timer = setTimeout(() => {
          window.removeEventListener('message', handler);
          reject(new Error('Page screenshots response timed out.'));
        }, timeoutMs);

        function handler(event) {
          if (event.source !== window.parent) return;
          if (event.data?.type !== 'PAGE_SCREENSHOTS_RESPONSE') return;

          clearTimeout(timer);
          window.removeEventListener('message', handler);

          if (event.data.ok) {
            resolve(Array.isArray(event.data.screenshots_b64) ? event.data.screenshots_b64 : []);
          } else {
            reject(new Error(event.data.error || 'Page screenshots capture failed.'));
          }
        }

        window.addEventListener('message', handler);
        window.parent.postMessage({ type: 'REQUEST_PAGE_SCREENSHOTS' }, '*');
      });
    }

    requestAutofill(payload, timeoutMs = 300000) {
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

    waitForParentResponse({ requestType, responseType, responseKey, timeoutMs, timeoutMessage }) {
      return new Promise((resolve) => {
        const timer = setTimeout(() => {
          window.removeEventListener('message', handler);
          console.warn(timeoutMessage);
          resolve(null);
        }, timeoutMs);

        function handler(event) {
          if (event.source !== window.parent) return;
          if (event.data?.type !== responseType) return;

          clearTimeout(timer);
          window.removeEventListener('message', handler);
          resolve(event.data[responseKey] || null);
        }

        window.addEventListener('message', handler);
        window.parent.postMessage({ type: requestType }, '*');
      });
    }
  }

  window.DomBridge = DomBridge;
})();
