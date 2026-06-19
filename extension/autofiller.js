// Clinical Ally autofill helper.
// Runs in the host page content-script context so it can inspect and update the page DOM.

(function () {
  'use strict';

  const FILLABLE_SELECTOR = 'input, textarea, select, [contenteditable="true"]';
  const SKIPPED_INPUT_TYPES = new Set([
    'button',
    'color',
    'file',
    'hidden',
    'image',
    'password',
    'reset',
    'submit',
  ]);

  class ClinicalAllyAutofiller {
    constructor({
      apiUrl,
      apiKey,
      context,
      prompt = '',
      preserveExisting = false,
      documentRef = document,
    } = {}) {
      if (!apiUrl) throw new Error('Autofill API URL is required.');
      if (!apiKey) throw new Error('Autofill API key is required.');

      this.apiUrl = apiUrl.replace(/\/$/, '');
      this.apiKey = apiKey;
      this.context = context || '';
      this.prompt = prompt || [
        'Fill blank fields on the current page using only the saved context.',
        'Only return fills for fields where the context provides a confident value.',
        'Prefer leaving a field blank over guessing.',
      ].join(' ');
      this.preserveExisting = preserveExisting;
      this.document = documentRef;
      this.fieldMap = new Map();
      this.usedFieldIds = new Set();
    }

    // main entry
    // - parses the page for fillable fields
    // - sends the fields and context to the API for fill suggestions
    // - applies the fills to the page and returns a summary of the results
    async autofill() {
      const fields = this.parseFields();
      if (!fields.length) {
        return {
          fields,
          fills: [],
          applied: [],
          skipped: [],
          message: 'No fillable fields were found on this page.',
        };
      }

      const response = await this.requestFills(fields);
      const fills = Array.isArray(response?.fills) ? response.fills : [];
      const result = this.applyFills(fills);

      return {
        fields,
        fills,
        ...result,
        message: this.buildMessage(result.applied, result.skipped, fields.length),
      };
    }

    parseFields() {
      this.fieldMap.clear();
      this.usedFieldIds.clear();

      const controls = Array.from(this.document.querySelectorAll(FILLABLE_SELECTOR))
        .filter((control) => this.isFillableControl(control));
      const fields = [];
      const radioGroups = new Map();

      controls.forEach((control) => {
        if (this.getControlType(control) === 'radio') {
          const groupKey = control.name || control.id || this.getDomPath(control);
          if (!radioGroups.has(groupKey)) radioGroups.set(groupKey, []);
          radioGroups.get(groupKey).push(control);
          return;
        }

        const field = this.createField(control, fields.length);
        fields.push(field);
        this.fieldMap.set(field.id, { kind: 'control', control, field });
      });

      radioGroups.forEach((groupControls) => {
        const field = this.createRadioField(groupControls, fields.length);
        fields.push(field);
        this.fieldMap.set(field.id, { kind: 'radio', controls: groupControls, field });
      });

      return fields;
    }

    // builds the request body for the /autofill enpoint
    buildRequestBody(fields) {
      return {
        prompt: this.prompt,
        context: this.context,
        fields,
      };
    }

    // sends the autofill request to the API and returns the response
    async requestFills(fields) {
      if (!window.Client) throw new Error('API client is unavailable.');

      const client = new window.Client({
        apiUrl: this.apiUrl,
        apiKey: this.apiKey,
      });

      return client.autofill(this.buildRequestBody(fields));
    }

    // applies the suggested fills to the page, returning a summary of which fills were applied vs skipped
    applyFills(fills) {
      const applied = [];
      const skipped = [];

      fills.forEach((fill) => {
        const fieldId = fill?.field_id || fill?.id;
        const target = this.resolveFieldTarget(fieldId);
        if (!target) {
          skipped.push({ field_id: fieldId || '', reason: 'Field was not found on the page.' });
          return;
        }

        try {
          const result = target.kind === 'radio'
            ? this.applyRadioFill(target, fill)
            : this.applyControlFill(target, fill);

          if (result.applied) {
            applied.push(result.summary);
          } else {
            skipped.push(result.summary);
          }
        } catch (err) {
          skipped.push({
            field_id: fieldId,
            label: target.field.label,
            reason: err.message,
          });
        }
      });

      return { applied, skipped };
    }

    // finds the target controls for a given field id, using exact ID match, name match, or DOM query as needed
    // eg. a fill with field_id "email" would match an input with id="email" or name="email", or a field with label "Email" if no exact matches were found
    resolveFieldTarget(fieldId) {
      if (!fieldId) return null;
      if (this.fieldMap.has(fieldId)) return this.fieldMap.get(fieldId);

      for (const target of this.fieldMap.values()) {
        if (target.field.dom_id === fieldId || target.field.name === fieldId) {
          return target;
        }
      }

      return null;
    }

    // applies a fill to a control, based on its type (text, checkbox, select, radio, contenteditable)
    applyControlFill(target, fill) {
      const { control, field } = target;
      const controlType = this.getControlType(control);

      if (controlType === 'checkbox') return this.applyCheckboxFill(target, fill);
      if (control.tagName === 'SELECT') return this.applySelectFill(target, fill);
      if (control.isContentEditable) return this.applyContentEditableFill(target, fill);
      return this.applyTextFill(target, fill);
    }

    // for text-like controls, we set the value directly and dispatch input events to ensure any listeners are triggered
    applyTextFill(target, fill) {
      const { control, field } = target;
      const action = this.#normalizeAction(fill.action, 'fill');
      const nextValue = this.#stringifyFillValue(fill.value);

      if (this.shouldPreserveControlValue(control, nextValue, action)) {
        return this.skippedSummary(field, 'Skipped because the field already had a value.');
      }

      this.setNativeValue(control, nextValue);
      this.dispatchInputEvents(control);
      return this.appliedSummary(field, nextValue, action);
    }

    // for contenteditable elements
    applyContentEditableFill(target, fill) {
      const { control, field } = target;
      const action = this.#normalizeAction(fill.action, 'fill');
      const nextValue = this.#stringifyFillValue(fill.value);

      if (this.shouldPreserveControlValue(control, nextValue, action)) {
        return this.skippedSummary(field, 'Skipped because the field already had a value.');
      }

      control.textContent = nextValue;
      this.dispatchInputEvents(control);
      return this.appliedSummary(field, nextValue, action);
    }

    // for checkboxes
    applyCheckboxFill(target, fill) {
      const { control, field } = target;
      const action = this.#normalizeAction(fill.action, 'check');
      const shouldCheck = this.getRequestedCheckedState(action, fill.value);

      if (this.shouldPreserveControlValue(control, shouldCheck, action)) {
        return this.skippedSummary(field, 'Skipped because the field already had a value.');
      }

      this.setNativeChecked(control, shouldCheck);
      this.dispatchInputEvents(control);
      return this.appliedSummary(field, shouldCheck ? 'checked' : 'unchecked', shouldCheck ? 'check' : 'uncheck');
    }

    // for select dropdowns
    applySelectFill(target, fill) {
      const { control, field } = target;
      const requestedValues = this.getRequestedSelectValues(fill.value, control.multiple);
      if (!requestedValues.length) {
        throw new Error('No dropdown option value was provided.');
      }

      const optionMatches = this.findSelectOptions(control, requestedValues);

      if (optionMatches.length !== requestedValues.length) {
        throw new Error(`Requested option was not available: ${requestedValues.join(', ')}`);
      }

      if (this.shouldPreserveSelectValue(control, requestedValues)) {
        return this.skippedSummary(field, 'Skipped because the dropdown already had a value.');
      }

      if (control.multiple) {
        Array.from(control.options).forEach((option) => {
          option.selected = optionMatches.includes(option);
        });
      } else {
        this.setNativeValue(control, optionMatches[0].value);
        optionMatches[0].selected = true;
      }

      this.dispatchInputEvents(control);
      return this.appliedSummary(field, this.getSelectedOptionText(control), 'select');
    }

    // radio
    applyRadioFill(target, fill) {
      const { controls, field } = target;
      const action = this.#normalizeAction(fill.action, 'select');
      const requestedValue = fill.value == null ? '' : String(fill.value);
      const selected = this.findRadioControl(controls, requestedValue);

      if (
        this.preserveExisting &&
        !field.is_empty &&
        field.current_value !== requestedValue &&
        action !== 'uncheck'
      ) {
        return {
          applied: false,
          summary: {
            field_id: field.id,
            label: field.label,
            reason: 'Skipped because the radio group already had a value.',
          },
        };
      }

      if (action === 'uncheck') {
        controls.forEach((control) => {
          this.setNativeChecked(control, false);
          this.dispatchInputEvents(control);
        });
        return this.appliedSummary(field, 'unselected', 'uncheck');
      }

      if (!selected) throw new Error('Requested radio option was not available.');

      this.setNativeChecked(selected, true);
      this.dispatchInputEvents(selected);
      return this.appliedSummary(field, this.getLabelForControl(selected), 'select');
    }

    // creates a field object for a given control
    createField(control, index) {
      const baseId = this.getBaseFieldId(control, index);
      const fieldId = this.makeUniqueFieldId(baseId);
      const type = this.getControlType(control);
      const field = {
        id: fieldId,
        label: this.getLabelForControl(control),
        type: this.getFieldType(control),
        control_type: type,
        tag: control.tagName.toLowerCase(),
        required: Boolean(control.required || control.getAttribute('aria-required') === 'true'),
        disabled: Boolean(control.disabled),
        readonly: Boolean(control.readOnly),
        current_value: this.getCurrentValue(control),
        is_empty: this.isEmptyControl(control),
      };

      if (control.id) field.dom_id = control.id;
      if (control.name) field.name = control.name;
      if (control.placeholder) field.placeholder = control.placeholder.trim();
      if (control.tagName === 'SELECT') field.options = this.getSelectOptions(control);

      return field;
    }

    createRadioField(controls, index) {
      const first = controls[0];
      const baseId = first.name || first.id || `radio_${index + 1}`;
      const fieldId = this.makeUniqueFieldId(baseId);
      const checked = controls.find((control) => control.checked);
      return {
        id: fieldId,
        label: this.getRadioGroupLabel(controls),
        type: 'radio',
        tag: 'input',
        required: controls.some((control) => control.required),
        current_value: checked?.value || '',
        is_empty: !checked,
        name: first.name || '',
        options: controls.map((control) => ({
          value: control.value,
          label: this.getLabelForControl(control),
          checked: Boolean(control.checked),
        })),
      };
    }

    isFillableControl(control) {
      const view = control.ownerDocument?.defaultView || window;
      if (!(control instanceof view.HTMLElement)) return false;
      if (control.closest('#clinical-ally-host')) return false;
      if (control.disabled || control.getAttribute('aria-disabled') === 'true') return false;
      if (control.readOnly) return false;
      if (control.tagName === 'INPUT' && SKIPPED_INPUT_TYPES.has(this.getControlType(control))) return false;
      if (control.offsetParent === null && control.getClientRects().length === 0) return false;

      const style = window.getComputedStyle(control);
      return style.visibility !== 'hidden' && style.display !== 'none';
    }

    getBaseFieldId(control, index) {
      return control.id || control.name || control.getAttribute('aria-label') || `field_${index + 1}`;
    }

    makeUniqueFieldId(baseId) {
      const cleanBase = this.#cleanText(baseId).replace(/\s+/g, '_') || 'field';
      let candidate = cleanBase;
      let counter = 2;

      while (this.usedFieldIds.has(candidate)) {
        candidate = `${cleanBase}__${counter}`;
        counter += 1;
      }

      this.usedFieldIds.add(candidate);
      return candidate;
    }

    getControlType(control) {
      if (control.isContentEditable) return 'contenteditable';
      if (control.tagName === 'TEXTAREA') return 'textarea';
      if (control.tagName === 'SELECT') return control.multiple ? 'select-multiple' : 'select';
      return (control.getAttribute('type') || 'text').toLowerCase();
    }

    getFieldType(control) {
      const controlType = this.getControlType(control);
      if (controlType === 'select-multiple' || controlType === 'select') return 'select';
      return controlType;
    }

    getCurrentValue(control) {
      if (this.getControlType(control) === 'checkbox') return Boolean(control.checked);
      if (control.isContentEditable) return this.#cleanText(control.textContent || '');
      if (control.tagName === 'SELECT' && control.multiple) {
        return Array.from(control.selectedOptions).map((option) => option.value);
      }
      if (control.tagName === 'SELECT') return control.value || '';
      return control.value || '';
    }

    isEmptyControl(control) {
      if (this.getControlType(control) === 'checkbox') return !control.checked;
      if (control.isContentEditable) return !this.#cleanText(control.textContent || '');
      if (control.tagName === 'SELECT') return this.isEmptySelect(control);
      return !String(control.value || '').trim();
    }

    isSameControlValue(control, value, action) {
      if (this.getControlType(control) === 'checkbox') {
        return control.checked === this.getRequestedCheckedState(action, value);
      }

      if (control.isContentEditable) return control.textContent === String(value ?? '');
      return String(control.value ?? '') === String(value ?? '');
    }

    shouldPreserveControlValue(control, value, action) {
      return (
        this.preserveExisting &&
        !this.isEmptyControl(control) &&
        !this.isSameControlValue(control, value, action)
      );
    }

    shouldPreserveSelectValue(select, requestedValues) {
      if (!this.preserveExisting || this.isEmptySelect(select)) return false;

      const currentValues = Array.from(select.selectedOptions).map((option) => option.value);
      if (!select.multiple) return currentValues[0] !== requestedValues[0];

      return (
        currentValues.length !== requestedValues.length ||
        currentValues.some((value) => !requestedValues.includes(value))
      );
    }

    getRequestedCheckedState(action, value) {
      if (action === 'check') return true;
      if (action === 'uncheck') return false;
      if (typeof value === 'boolean') return value;

      const normalized = String(value ?? '').trim().toLowerCase();
      if (['true', 'yes', 'y', '1', 'checked', 'on'].includes(normalized)) return true;
      if (['false', 'no', 'n', '0', 'unchecked', 'off', ''].includes(normalized)) return false;

      return Boolean(value);
    }

    isEmptySelect(select) {
      const selected = select.options[select.selectedIndex];
      const value = select.value || '';
      const label = this.#cleanText(selected?.textContent || '');
      return (
        !value ||
        selected?.disabled ||
        select.selectedIndex < 0 ||
        (/^(--)?\s*(select|choose|please select|none)\b/i).test(label)
      );
    }

    getSelectOptions(select) {
      return Array.from(select.options)
        .filter((option) => !option.disabled)
        .map((option) => ({
          value: option.value,
          label: this.#cleanText(option.textContent || option.label || option.value),
          selected: Boolean(option.selected),
        }));
    }

    getRequestedSelectValues(value, multiple) {
      if (Array.isArray(value)) {
        return value.map((item) => String(item)).filter((item) => item !== '');
      }

      if (multiple && typeof value === 'string' && value.includes(',')) {
        return value.split(',').map((item) => item.trim()).filter(Boolean);
      }

      return [String(value ?? '')].filter((item) => item !== '');
    }

    findSelectOptions(select, requestedValues) {
      return requestedValues
        .map((value) => this.findSelectOption(select, value))
        .filter(Boolean);
    }

    findSelectOption(select, requestedValue) {
      const options = Array.from(select.options).filter((option) => !option.disabled);
      const requested = String(requestedValue ?? '');
      const normalizedRequested = this.#normalizeMatchText(requested);

      return (
        options.find((option) => option.value === requested) ||
        options.find((option) => this.#cleanText(option.textContent || option.label) === requested) ||
        options.find((option) => this.#normalizeMatchText(option.value) === normalizedRequested) ||
        options.find((option) => this.#normalizeMatchText(option.textContent || option.label) === normalizedRequested) ||
        options.find((option) => this.optionLabelStartsWithValue(option, requested))
      );
    }

    getSelectedOptionText(select) {
      const selected = Array.from(select.selectedOptions || []);
      if (selected.length) {
        return selected.map((option) => this.#cleanText(option.textContent || option.value)).join(', ');
      }
      return this.#cleanText(select.value || '');
    }

    optionLabelStartsWithValue(option, requestedValue) {
      const requested = String(requestedValue ?? '').trim();
      if (!requested) return false;

      const label = this.#cleanText(option.textContent || option.label || '');
      return new RegExp(`^${this.#escapeRegExp(requested)}\\b`).test(label);
    }

    findRadioControl(controls, requestedValue) {
      const requested = String(requestedValue ?? '');
      const normalizedRequested = this.#normalizeMatchText(requested);

      return (
        controls.find((control) => control.value === requested) ||
        controls.find((control) => this.#normalizeMatchText(control.value) === normalizedRequested) ||
        controls.find((control) => this.#normalizeMatchText(this.getLabelForControl(control)) === normalizedRequested)
      );
    }

    #normalizeAction(action, fallback) {
      const normalized = String(action || fallback || '').toLowerCase();
      if (normalized === 'select' || normalized === 'fill' || normalized === 'check' || normalized === 'uncheck') {
        return normalized;
      }
      return fallback;
    }

    #stringifyFillValue(value) {
      if (value == null) return '';
      if (Array.isArray(value)) return value.join(', ');
      return String(value);
    }

    setNativeValue(control, value) {
      const view = control.ownerDocument?.defaultView || window;
      const prototype = control.tagName === 'TEXTAREA'
        ? view.HTMLTextAreaElement.prototype
        : control.tagName === 'SELECT'
          ? view.HTMLSelectElement.prototype
          : view.HTMLInputElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(prototype, 'value')?.set;

      if (setter) setter.call(control, value);
      else control.value = value;
    }

    setNativeChecked(control, checked) {
      const view = control.ownerDocument?.defaultView || window;
      const setter = Object.getOwnPropertyDescriptor(view.HTMLInputElement.prototype, 'checked')?.set;

      if (setter) setter.call(control, checked);
      else control.checked = checked;
    }

    getLabelForControl(control) {
      const labelledBy = control.getAttribute('aria-labelledby');
      if (labelledBy) {
        const text = labelledBy
          .split(/\s+/)
          .map((id) => this.document.getElementById(id)?.textContent || '')
          .join(' ');
        if (this.#cleanText(text)) return this.#cleanText(text);
      }

      const ariaLabel = this.#cleanText(control.getAttribute('aria-label') || '');
      if (ariaLabel) return ariaLabel;

      if (control.id) {
        const label = this.document.querySelector(`label[for="${this.#cssEscape(control.id)}"]`);
        const labelText = this.#getElementTextWithoutControls(label);
        if (labelText) return labelText;
      }

      const wrappingLabel = control.closest('label');
      if (wrappingLabel) {
        const labelText = this.#getElementTextWithoutControls(wrappingLabel);
        if (labelText) return labelText;
      }

      const tableLabel = this.getNearbyTableLabel(control);
      if (tableLabel) return tableLabel;

      const title = this.#cleanText(control.getAttribute('title') || '');
      if (title) return title;

      const placeholder = this.#cleanText(control.getAttribute('placeholder') || '');
      if (placeholder) return placeholder;

      return this.#cleanText(control.name || control.id || 'Unlabeled field');
    }

    getRadioGroupLabel(controls) {
      const first = controls[0];
      const fieldset = first.closest('fieldset');
      const legend = this.#cleanText(fieldset?.querySelector('legend')?.textContent || '');
      if (legend) return legend;

      const tableLabel = this.getNearbyTableLabel(first);
      if (tableLabel) return tableLabel;

      return this.#cleanText(first.name || first.id || 'Radio group');
    }

    getNearbyTableLabel(control) {
      const cell = control.closest('td, th');
      const row = cell?.parentElement;
      if (!cell || !row) return '';

      const cells = Array.from(row.children).filter((child) => ['TD', 'TH'].includes(child.tagName));
      const index = cells.indexOf(cell);
      for (let i = index - 1; i >= 0; i -= 1) {
        const candidate = this.#getElementTextWithoutControls(cells[i]);
        if (candidate) return candidate;
      }

      const firstCell = this.#getElementTextWithoutControls(cells[0]);
      return firstCell && !firstCell.includes(this.#cleanText(control.value || '')) ? firstCell : '';
    }

    getDomPath(control) {
      const parts = [];
      let node = control;

      while (node && node.nodeType === Node.ELEMENT_NODE && parts.length < 4) {
        const tag = node.tagName.toLowerCase();
        const siblingIndex = Array.from(node.parentElement?.children || [])
          .filter((sibling) => sibling.tagName === node.tagName)
          .indexOf(node) + 1;
        parts.unshift(`${tag}:nth-of-type(${siblingIndex})`);
        node = node.parentElement;
      }

      return parts.join('>');
    }

    dispatchInputEvents(control) {
      control.dispatchEvent(new Event('input', { bubbles: true }));
      control.dispatchEvent(new Event('change', { bubbles: true }));
      control.dispatchEvent(new Event('blur', { bubbles: true }));
    }

    appliedSummary(field, value, action) {
      return {
        applied: true,
        summary: {
          field_id: field.id,
          label: field.label,
          value,
          action,
        },
      };
    }

    unchangedSummary(field, value) {
      return this.appliedSummary(field, value, 'unchanged');
    }

    skippedSummary(field, reason) {
      return {
        applied: false,
        summary: {
          field_id: field.id,
          label: field.label,
          reason,
        },
      };
    }

    buildMessage(applied, skipped, fieldCount) {
      if (applied.length) {
        return `Autofilled ${applied.length} of ${fieldCount} detected fields.`;
      }
      if (skipped.length) {
        return `No fields were changed. ${skipped.length} suggested fills were skipped.`;
      }
      return `No fields were changed. ${fieldCount} fillable fields were detected.`;
    }

    #cleanText(text) {
      return String(text || '').replace(/\s+/g, ' ').trim();
    }

    #getElementTextWithoutControls(element) {
      if (!element) return '';

      const clone = element.cloneNode(true);
      clone.querySelectorAll('input, textarea, select, button, option, script, style').forEach((node) => node.remove());
      return this.#cleanText(clone.textContent || '');
    }

    #normalizeMatchText(text) {
      return this.#cleanText(text).toLowerCase();
    }

    #escapeRegExp(value) {
      return String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }

    #cssEscape(value) {
      if (window.CSS?.escape) return window.CSS.escape(value);
      return String(value).replace(/\\/g, '\\\\').replace(/"/g, '\\"');
    }
  }

  window.ClinicalAllyAutofiller = ClinicalAllyAutofiller;
})();