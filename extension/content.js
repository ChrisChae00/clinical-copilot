// Clinical Ally — content script
// Injects the sidebar into the host page via shadow DOM

(function () {
  'use strict';

  // Prevent double-injection
  if (document.getElementById('clinical-ally-host')) return;

  // ── OSCAR context extraction ──────────────────────────────────
  function extractOSCARContext() {
    const ctx = {
      page_url: window.location.href,
      page_title: document.title,
      page_type: 'unknown',
    };

    // ── Consultation Request page ────────────────────────────────
    if (document.getElementById('EctConsultationFormRequest2Form')) {
      ctx.page_type = 'consultation_request';

      // Patient header (e.g. "Smith, John M 45")
      const header = document.querySelector('.TopStatusBar h2');
      if (header) ctx.patient_header = header.textContent.trim();

      // Demographics from label→value table rows
      const labelMap = {
        'Patient':         'patient_name',
        'Birthdate':       'patient_dob',
        'Sex':             'patient_sex',
        'Health Card No.': 'patient_hcn',
        'Tel.No.':         'patient_phone',
        'Cell No.':        'patient_cell',
      };
      document.querySelectorAll('tr').forEach((row) => {
        const labelEl = row.querySelector('td.tite4');
        const valueEl = row.querySelector('td.tite1');
        if (!labelEl || !valueEl) return;
        const key = labelMap[labelEl.textContent.trim()];
        if (key) {
          // prefer link text for patient name
          const link = valueEl.querySelector('a');
          ctx[key] = (link || valueEl).textContent.trim();
        }
      });

      // Clinical textareas (only include if non-empty)
      const textareaFields = [
        ['currentMedications',    'current_medications'],
        ['allergies',             'allergies'],
        ['clinicalInformation',   'clinical_information'],
        ['concurrentProblems',    'concurrent_problems'],
      ];
      textareaFields.forEach(([id, key]) => {
        const el = document.getElementById(id);
        if (el && el.value.trim()) ctx[key] = el.value.trim();
      });

      const form = document.getElementById('EctConsultationFormRequest2Form');
      const rfcEl = form.querySelector('textarea[name="reasonForConsultation"]');
      if (rfcEl && rfcEl.value.trim()) ctx.reason_for_consultation = rfcEl.value.trim();

      // Consultation dropdowns
      const getSelected = (el) => el ? (el.options[el.selectedIndex]?.text || '').trim() : '';
      ctx.referring_practitioner = getSelected(form.querySelector('select[name="providerNo"]'));
      ctx.service  = getSelected(document.getElementById('service'));
      ctx.specialist = getSelected(document.getElementById('specialist'));
      ctx.urgency  = getSelected(document.getElementById('urgency'));

      const referalDate = document.getElementById('referalDate');
      if (referalDate && referalDate.value) ctx.referral_date = referalDate.value;

      const demoNo = document.getElementById('demographicNo');
      if (demoNo) ctx.demographic_no = demoNo.value;
    }

    return ctx;
  }

  const PANEL_WIDTH_EXPANDED = 360;
  const PANEL_WIDTH_COLLAPSED = 48;
  const PANEL_WIDTH_MIN = 200;
  const PANEL_WIDTH_MAX = 800;

  // ── Host element ──────────────────────────────────────────────
  const host = document.createElement('div');
  host.id = 'clinical-ally-host';
  Object.assign(host.style, {
    position: 'fixed',
    right: '0',
    top: '0',
    height: '100vh',
    width: `${PANEL_WIDTH_COLLAPSED}px`,
    zIndex: '2147483647',
    transition: 'width 0.3s ease',
    boxShadow: 'none',
    pointerEvents: 'none',
  });
  document.body.appendChild(host);

  // ── Shadow root ───────────────────────────────────────────────
  const shadow = host.attachShadow({ mode: 'open' });

  // ── Resize handle ────────────────────────────────────────────
  const resizeHandle = document.createElement('div');
  Object.assign(resizeHandle.style, {
    position: 'absolute',
    left: '0',
    top: '0',
    width: '6px',
    height: '100%',
    cursor: 'col-resize',
    zIndex: '2',
    pointerEvents: 'auto',
    display: 'none',
  });
  shadow.appendChild(resizeHandle);

  let isResizing = false;

  resizeHandle.addEventListener('mousedown', (e) => {
    isResizing = true;
    iframe.style.pointerEvents = 'none';
    document.body.style.userSelect = 'none';
    e.preventDefault();
  });

  document.addEventListener('mousemove', (e) => {
    if (!isResizing) return;
    const newWidth = Math.min(PANEL_WIDTH_MAX, Math.max(PANEL_WIDTH_MIN, window.innerWidth - e.clientX));
    host.style.width = `${newWidth}px`;
  });

  document.addEventListener('mouseup', () => {
    if (!isResizing) return;
    isResizing = false;
    iframe.style.pointerEvents = '';
    document.body.style.userSelect = '';
  });

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
    display: 'block',
    zIndex: '1',
    pointerEvents: 'auto',
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
    display: 'none',
  });
  iframe.setAttribute('title', 'Clinical Ally sidebar');
  shadow.appendChild(iframe);

  // ── Collapse / expand ─────────────────────────────────────────
  let expanded = false;

  function collapse() {
    expanded = false;
    host.style.width = `${PANEL_WIDTH_COLLAPSED}px`;
    host.style.boxShadow = 'none';
    host.style.pointerEvents = 'none';
    iframe.style.display = 'none';
    toggleBtn.style.display = 'block';
    resizeHandle.style.display = 'none';
  }

  function expand() {
    expanded = true;
    host.style.width = `${PANEL_WIDTH_EXPANDED}px`;
    host.style.boxShadow = '-2px 0 8px rgba(0,0,0,0.15)';
    host.style.pointerEvents = 'auto';
    iframe.style.display = 'block';
    toggleBtn.style.display = 'none';
    resizeHandle.style.display = 'block';
  }

  toggleBtn.addEventListener('click', expand);

  // Listen for messages from panel.js (inside iframe)
  window.addEventListener('message', (event) => {
    if (!event.data) return;
    if (event.data.type === 'CLINICAL_ALLY_CLOSE') {
      collapse();
    } else if (event.data.type === 'REQUEST_CONTEXT') {
      const context = extractOSCARContext();
      iframe.contentWindow.postMessage({ type: 'CONTEXT_RESPONSE', context }, '*');
    }
  });
})();
