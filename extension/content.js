// Clinical Ally — content script
// Injects the sidebar into the host page via shadow DOM (open mode for Sprint 1 testability)
// TODO Sprint 2: switch to closed shadow root

(function () {
  'use strict';

  // Prevent double-injection
  if (document.getElementById('clinical-ally-host')) return;

  const PANEL_WIDTH_EXPANDED = 360;
  const PANEL_WIDTH_COLLAPSED = 48;

  // ── Host element ──────────────────────────────────────────────
  const host = document.createElement('div');
  host.id = 'clinical-ally-host';
  Object.assign(host.style, {
    position: 'fixed',
    right: '0',
    top: '0',
    height: '100vh',
    width: `${PANEL_WIDTH_EXPANDED}px`,
    zIndex: '2147483647',
    transition: 'width 0.3s ease',
    boxShadow: '-2px 0 8px rgba(0,0,0,0.15)',
  });
  document.body.appendChild(host);

  // ── Shadow root ───────────────────────────────────────────────
  const shadow = host.attachShadow({ mode: 'open' });

  // ── Toggle button (visible when collapsed) ────────────────────
  const toggleBtn = document.createElement('button');
  Object.assign(toggleBtn.style, {
    position: 'absolute',
    left: '0',
    top: '50%',
    transform: 'translateY(-50%)',
    width: `${PANEL_WIDTH_COLLAPSED}px`,
    height: '80px',
    background: '#0066cc',
    color: '#fff',
    border: 'none',
    borderRadius: '8px 0 0 8px',
    cursor: 'pointer',
    fontSize: '10px',
    fontFamily: 'sans-serif',
    fontWeight: '600',
    letterSpacing: '0.5px',
    writingMode: 'vertical-rl',
    textOrientation: 'mixed',
    display: 'none',
    zIndex: '1',
  });
  toggleBtn.textContent = 'Clinical Ally';
  toggleBtn.setAttribute('aria-label', 'Open Clinical Ally sidebar');
  toggleBtn.setAttribute('title', 'Open Clinical Ally');
  shadow.appendChild(toggleBtn);

  // ── Iframe to hold the panel ──────────────────────────────────
  const iframe = document.createElement('iframe');
  iframe.src = browser.runtime.getURL('panel.html');
  Object.assign(iframe.style, {
    width: '100%',
    height: '100%',
    border: 'none',
    display: 'block',
  });
  iframe.setAttribute('title', 'Clinical Ally sidebar');
  shadow.appendChild(iframe);

  // ── Collapse / expand ─────────────────────────────────────────
  let expanded = true;

  function collapse() {
    expanded = false;
    host.style.width = `${PANEL_WIDTH_COLLAPSED}px`;
    iframe.style.display = 'none';
    toggleBtn.style.display = 'block';
  }

  function expand() {
    expanded = true;
    host.style.width = `${PANEL_WIDTH_EXPANDED}px`;
    iframe.style.display = 'block';
    toggleBtn.style.display = 'none';
  }

  toggleBtn.addEventListener('click', expand);

  // Listen for close message from panel.js
  window.addEventListener('message', (event) => {
    if (event.data && event.data.type === 'CLINICAL_ALLY_CLOSE') {
      collapse();
    }
  });
})();
