// Clinical Ally — content script
// Injects the sidebar into the host page via shadow DOM

(function () {
  'use strict';

  // Prevent double-injection
  if (document.getElementById('clinical-ally-host')) return;

  // ── OSCAR context extraction ──────────────────────────────────

  const _val   = (id) => document.getElementById(id)?.value?.trim() || '';
  const _selOpt = (el) => el ? (el.options[el.selectedIndex]?.text || '').trim() : '';

  // Extracts patient header + demographic_no present on most OSCAR pages
  function _extractCommon(ctx) {
    const header = document.querySelector('.TopStatusBar h2');
    if (header) ctx.patient_header = header.textContent.trim();
    const demoNo = _val('demographicNo');
    if (demoNo) ctx.demographic_no = demoNo;
  }

  function _extractConsultationRequest(ctx) {
    ctx.page_type = 'consultation_request';
    _extractCommon(ctx);

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
        const link = valueEl.querySelector('a');
        ctx[key] = (link || valueEl).textContent.trim();
      }
    });

    const textareaFields = [
      ['currentMedications',  'current_medications'],
      ['allergies',           'allergies'],
      ['clinicalInformation', 'clinical_information'],
      ['concurrentProblems',  'concurrent_problems'],
    ];
    textareaFields.forEach(([id, key]) => {
      const v = _val(id);
      if (v) ctx[key] = v;
    });

    const form = document.getElementById('EctConsultationFormRequest2Form');
    const rfc = form.querySelector('textarea[name="reasonForConsultation"]');
    if (rfc?.value?.trim()) ctx.reason_for_consultation = rfc.value.trim();

    ctx.referring_practitioner = _selOpt(form.querySelector('select[name="providerNo"]'));
    ctx.service    = _selOpt(document.getElementById('service'));
    ctx.specialist = _selOpt(document.getElementById('specialist'));
    ctx.urgency    = _selOpt(document.getElementById('urgency'));

    const referalDate = _val('referalDate');
    if (referalDate) ctx.referral_date = referalDate;
  }

  function _extractEncounter(ctx) {
    ctx.page_type = 'encounter';
    _extractCommon(ctx);

    // Encounter note — OSCAR uses a textarea or rich editor
    const noteEl = document.getElementById('note') ||
                   document.querySelector('textarea[name="note"]') ||
                   document.querySelector('.noteEditor textarea') ||
                   document.querySelector('#noteContainer textarea');
    if (noteEl?.value?.trim()) ctx.encounter_note = noteEl.value.trim();

    // SOAP fields (some OSCAR versions split the note)
    const soapFields = [
      ['subjectiveText',  'subjective'],
      ['objectiveText',   'objective'],
      ['assessmentText',  'assessment'],
      ['planText',        'plan'],
    ];
    soapFields.forEach(([id, key]) => {
      const v = _val(id);
      if (v) ctx[key] = v;
    });

    // Problem list — table rows with diagnosis codes/descriptions
    const problems = [];
    document.querySelectorAll('.problem-list tr, #problemList tr, table.problem tr').forEach((row) => {
      const cells = row.querySelectorAll('td');
      if (cells.length >= 2) {
        const desc = cells[0].textContent.trim() || cells[1].textContent.trim();
        if (desc) problems.push(desc);
      }
    });
    if (problems.length) ctx.problem_list = problems;

    // Reason for visit
    const reasonEl = document.querySelector('input[name="reason"], #reason, input[name="appointmentReason"]');
    if (reasonEl?.value?.trim()) ctx.reason_for_visit = reasonEl.value.trim();
  }

  function _extractDemographic(ctx) {
    ctx.page_type = 'demographic';

    const textFields = [
      ['lastName',    'last_name'],
      ['firstName',   'first_name'],
      ['address',     'address'],
      ['city',        'city'],
      ['province',    'province'],
      ['postal',      'postal_code'],
      ['phone',       'phone'],
      ['phone2',      'phone2'],
      ['email',       'email'],
      ['hin',         'health_card_no'],
      ['ver',         'health_card_version'],
    ];
    textFields.forEach(([name, key]) => {
      const el = document.querySelector(`input[name="${name}"], #${name}`);
      if (el?.value?.trim()) ctx[key] = el.value.trim();
    });

    const dob = _val('dobYear') && _val('dobMonth') && _val('dobDay')
      ? `${_val('dobYear')}-${_val('dobMonth').padStart(2,'0')}-${_val('dobDay').padStart(2,'0')}`
      : '';
    if (dob) ctx.date_of_birth = dob;

    const sex = document.querySelector('select[name="sex"], #sex');
    if (sex) ctx.sex = _selOpt(sex);

    const hcType = document.querySelector('select[name="hcType"], #hcType');
    if (hcType) ctx.health_card_province = _selOpt(hcType);
  }

  function _extractLabResults(ctx) {
    ctx.page_type = 'lab_results';
    _extractCommon(ctx);

    const labs = [];
    // Skip the first row of each table to avoid picking up column headers
    document.querySelectorAll('table').forEach((table) => {
      Array.from(table.querySelectorAll('tr')).slice(1).forEach((row) => {
        const cells = row.querySelectorAll('td');
        if (cells.length < 3) return;
        const name  = cells[0].textContent.trim();
        const value = cells[1].textContent.trim();
        const range = cells[2]?.textContent?.trim() || '';
        if (name && value && name.length < 60) {
          labs.push(range ? `${name}: ${value} (ref: ${range})` : `${name}: ${value}`);
        }
      });
    });
    if (labs.length) ctx.lab_results = labs;

    // Collection date shown in header or caption
    const dateEl = document.querySelector('.labDate, td.labDate, caption, .reportDate');
    if (dateEl) ctx.collection_date = dateEl.textContent.trim();
  }

  function _extractPrescriptions(ctx) {
    ctx.page_type = 'prescription';
    _extractCommon(ctx);

    const rxList = [];
    // Skip the first row of each table to avoid picking up column headers
    document.querySelectorAll('table').forEach((table) => {
      Array.from(table.querySelectorAll('tr')).slice(1).forEach((row) => {
        const cells = row.querySelectorAll('td');
        if (cells.length >= 2) {
          const drug = cells[0].textContent.trim();
          const dose = cells[1]?.textContent?.trim() || '';
          if (drug && drug.length < 80) rxList.push(dose ? `${drug} — ${dose}` : drug);
        }
      });
    });
    document.querySelectorAll('.drugList li').forEach((li) => {
      const text = li.textContent.trim();
      if (text && text.length < 80) rxList.push(text);
    });
    if (rxList.length) ctx.prescriptions = rxList;
  }

  function _extractScheduler(ctx) {
    ctx.page_type = 'scheduler';

    // Extract appointments visible in current day view
    const appts = [];
    document.querySelectorAll('td.appt, .appointment, tr[class*="appt"]').forEach((appt) => {
      const time    = appt.querySelector('.apptTime, td:first-child')?.textContent?.trim() || '';
      const patient = appt.querySelector('.patientName, a[href*="demographic"]')?.textContent?.trim() || '';
      const reason  = appt.querySelector('.apptReason, .reason')?.textContent?.trim() || '';
      if (patient) appts.push([time, patient, reason].filter(Boolean).join(' — '));
    });
    if (appts.length) ctx.appointments = appts;

    // Date being viewed
    const url = new URL(window.location.href);
    const y = url.searchParams.get('year');
    const m = url.searchParams.get('month');
    const d = url.searchParams.get('day');
    if (y && m && d) ctx.schedule_date = `${y}-${m.padStart(2,'0')}-${d.padStart(2,'0')}`;
  }

  function _extractPreventiveCare(ctx) {
    ctx.page_type = 'preventive_care';
    _extractCommon(ctx);

    const items = [];
    // Skip the first row of each table to avoid picking up column headers
    document.querySelectorAll('table').forEach((table) => {
      Array.from(table.querySelectorAll('tr')).slice(1).forEach((row) => {
        const cells = row.querySelectorAll('td');
        if (cells.length >= 2) {
          const item = cells[0].textContent.trim();
          const status = cells[1].textContent.trim();
          if (item && status && item.length < 80) items.push(`${item}: ${status}`);
        }
      });
    });
    if (items.length) ctx.preventive_care_items = items;
  }

  function extractOSCARContext() {
    const ctx = {
      page_url: window.location.href,
      page_title: document.title,
      page_type: 'unknown',
    };

    const url = window.location.href;

    try {
      if (document.getElementById('EctConsultationFormRequest2Form')) {
        _extractConsultationRequest(ctx);
      } else if (url.includes('/casemgmt/') || url.includes('caseManagement')) {
        _extractEncounter(ctx);
      } else if (url.includes('/demographic/demographiccontrol') || url.includes('addDemographic')) {
        _extractDemographic(ctx);
      } else if (url.includes('/lab/') || url.includes('labReport') || url.includes('LabReport')) {
        _extractLabResults(ctx);
      } else if (url.includes('/oscarRx/') || url.includes('RxPreview') || new URL(url).pathname.includes('/prescription')) {
        _extractPrescriptions(ctx);
      } else if (url.includes('providercontrol') || url.includes('provider/scheduler')) {
        _extractScheduler(ctx);
      } else if (url.includes('/oscarPrevention/') || url.includes('Prevention')) {
        _extractPreventiveCare(ctx);
      } else {
        // Generic fallback — extract patient header if present on any OSCAR page
        _extractCommon(ctx);
      }
    } catch (err) {
      console.error('[ClinicalAlly] extractOSCARContext failed:', err);
      ctx.extraction_error = err.message;
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
  iframe.setAttribute('allow', 'microphone');
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
    // Only accept messages from our own iframe — rejects any other frame on the page
    if (event.source !== iframe.contentWindow) return;
    if (event.data.type === 'CLINICAL_ALLY_CLOSE') {
      collapse();
    } else if (event.data.type === 'REQUEST_CONTEXT') {
      const context = extractOSCARContext();
      iframe.contentWindow.postMessage(
        { type: 'CONTEXT_RESPONSE', context },
        browser.runtime.getURL('')  // restrict to extension origin, not wildcard
      );
    } else if (event.data.type === 'REQUEST_PAGE_HTML') {
      const html = document.documentElement?.outerHTML || '';
      iframe.contentWindow.postMessage(
        { type: 'PAGE_HTML_RESPONSE', html },
        browser.runtime.getURL('')
      );
    } else if (event.data.type === 'REQUEST_PAGE_SCREENSHOT') {
      const capturePageScreenshot = async () => {
        const previousVisibility = host.style.visibility;
        host.style.visibility = 'hidden';

        try {
          await new Promise((resolve) => {
            requestAnimationFrame(() => requestAnimationFrame(resolve));
          });

          const dataUrl = await browser.runtime.sendMessage({ type: 'CAPTURE_VISIBLE_TAB' });
          const commaIndex = String(dataUrl || '').indexOf(',');
          return commaIndex >= 0 ? dataUrl.slice(commaIndex + 1) : dataUrl;
        } finally {
          host.style.visibility = previousVisibility;
        }
      };

      capturePageScreenshot()
        .then((screenshot_b64) => {
          iframe.contentWindow.postMessage(
            { type: 'PAGE_SCREENSHOT_RESPONSE', ok: true, screenshot_b64 },
            browser.runtime.getURL('')
          );
        })
        .catch((err) => {
          iframe.contentWindow.postMessage(
            { type: 'PAGE_SCREENSHOT_RESPONSE', ok: false, error: err.message },
            browser.runtime.getURL('')
          );
        });
    } else if (event.data.type === 'REQUEST_AUTOFILL') {
      if (!window.AutofillManager) {
        iframe.contentWindow.postMessage(
          { type: 'AUTOFILL_RESPONSE', ok: false, error: 'AutofillManager is unavailable.' },
          browser.runtime.getURL('')
        );
        return;
      }

      const runAutofill = async () => {
        const autofillManager = new window.AutofillManager({
          apiUrl: event.data.apiUrl,
          apiKey: event.data.apiKey,
          context: event.data.context || '',
          prompt: event.data.prompt || '',
          images_b64: Array.isArray(event.data.images_b64) ? event.data.images_b64 : [],
        });
        return autofillManager.autofill();
      };

      runAutofill()
        .then((result) => {
          iframe.contentWindow.postMessage(
            { type: 'AUTOFILL_RESPONSE', ok: true, result },
            browser.runtime.getURL('')
          );
        })
        .catch((err) => {
          iframe.contentWindow.postMessage(
            { type: 'AUTOFILL_RESPONSE', ok: false, error: err.message },
            browser.runtime.getURL('')
          );
        });
    }
  });
})();
