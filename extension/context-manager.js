// ContextManager
// Shares clinical context and Ollama chat history across open panels.
// browser.storage.session is used when available, so state can survive a gap
// with no open panel without being persisted beyond the browser session.

(function () {
  'use strict';

  const CHANNEL_NAME = 'clinical-ally-context';
  const STORAGE_KEY = 'clinical-ally-session-state-v2';
  const STORAGE_SCHEMA_VERSION = 2;
  const SYNC_WAIT_MS = 100;
  const INITIAL_EPOCH = '0';
  const MAX_HISTORY_TURNS = 24;
  const MAX_HISTORY_CHARS = 60000;
  const MAX_HISTORY_IMAGE_CHARS = 6 * 1024 * 1024;

  class ContextManager {
    constructor() {
      this.context = '';
      this.messages = [];
      this.turns = [];
      this.originId = globalThis.crypto?.randomUUID?.()
        || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
      this.sequence = 0;
      this.epoch = INITIAL_EPOCH;
      this.stateVersion = '0';
      this.contextVersion = '0';
      this.listeners = new Set();
      this.initialized = false;
      this.persistQueue = Promise.resolve();

      this.channel = typeof globalThis.BroadcastChannel === 'function'
        ? new BroadcastChannel(CHANNEL_NAME)
        : null;
      this.storageApi = globalThis.browser?.storage || globalThis.chrome?.storage || null;
      this.storageArea = this.storageApi?.session || null;

      this.channel?.addEventListener('message', (event) => {
        this.handleMessage(event.data);
      });

      this.storageChangeListener = (changes, areaName) => {
        if (areaName !== 'session') return;
        const remoteState = changes?.[STORAGE_KEY]?.newValue;
        if (!remoteState || !this.#mergeState(remoteState)) return;

        // A storage update may have raced with an in-memory turn. Re-persist
        // and broadcast the merged union so every panel converges.
        this.#schedulePersist();
        this.broadcastContext();
        this.#notify();
      };
      this.storageApi?.onChanged?.addListener?.(this.storageChangeListener);

      this.ready = this.#initialize();
    }

    async getContext() {
      await this.ready;
      return this.context;
    }

    async getMessages() {
      await this.ready;
      return this.#copyMessages(this.messages);
    }

    async getCombinedContext() {
      await this.ready;

      const sections = [];
      if (this.context) sections.push(this.context);

      if (this.messages.length) {
        const history = this.messages
          .filter((message) => message.role === 'user' || message.role === 'assistant')
          .map((message) => `${message.role}: ${message.content || ''}`)
          .join('\n\n');
        if (history) sections.push(`### CHAT HISTORY ###\n${history}`);
      }

      return sections.join('\n\n');
    }

    async getState() {
      await this.ready;
      return this.#stateSnapshot();
    }

    subscribe(listener) {
      if (typeof listener !== 'function') {
        throw new TypeError('ContextManager subscriber must be a function.');
      }

      this.listeners.add(listener);
      if (this.initialized) {
        queueMicrotask(() => {
          if (this.listeners.has(listener)) this.#notifyListener(listener);
        });
      }

      return () => {
        this.listeners.delete(listener);
      };
    }

    setContext(context, expectedEpoch = this.epoch) {
      if (expectedEpoch !== this.epoch) return false;
      this.context = context && typeof context !== 'string' ? JSON.stringify(context) : (context || '');
      this.contextVersion = this.#nextVersion();
      this.#commit();
      return true;
    }

    commitChatResult(snapshot, messages, updatedContext) {
      if (!snapshot || snapshot.epoch !== this.epoch) return false;

      const normalized = this.#normalizeMessages(messages);
      const baseLength = Array.isArray(snapshot.messages) ? snapshot.messages.length : 0;
      if (normalized.length <= baseLength) return false;

      // The API returns the caller's prior history plus the new user/assistant
      // turn. Store only that suffix so concurrent panels can merge their turns.
      const suffix = normalized.slice(baseLength);
      return this.commitTurn(snapshot, suffix, updatedContext);
    }

    commitTurn(snapshot, messages, updatedContext) {
      if (!snapshot || snapshot.epoch !== this.epoch) return false;

      const suffix = this.#normalizeMessages(messages);
      if (!suffix.length) return false;

      this.turns.push({
        id: this.#nextVersion(),
        messages: suffix,
      });

      if (
        typeof updatedContext === 'string'
        && updatedContext !== snapshot.context
        && this.context === snapshot.context
      ) {
        this.context = updatedContext;
        this.contextVersion = this.#nextVersion();
      }

      this.#commit();
      return true;
    }

    clearContext() {
      this.context = '';
      this.messages = [];
      this.turns = [];
      this.epoch = this.#nextVersion();
      this.contextVersion = this.#nextVersion();
      this.#commit();
    }

    broadcastContext() {
      if (!this.channel) return;
      try {
        this.channel.postMessage({
          type: 'CONTEXT_STATE',
          ...this.#statePayload(),
        });
      } catch (err) {
        console.warn('[ClinicalAlly] Could not broadcast session context:', err);
      }
    }

    handleMessage(message) {
      if (message?.type === 'REQUEST_CONTEXT') {
        this.broadcastContext();
        return;
      }

      if (message?.type !== 'CONTEXT_STATE') return;
      if (!this.#mergeState(message)) return;

      this.#schedulePersist();
      this.#notify();
    }

    async #initialize() {
      await this.#loadStoredState();

      // Publish any restored state and ask already-open panels for turns that
      // may not have reached storage yet.
      this.broadcastContext();
      this.channel?.postMessage({ type: 'REQUEST_CONTEXT' });
      await new Promise((resolve) => setTimeout(resolve, SYNC_WAIT_MS));

      this.initialized = true;
      this.#notify();
    }

    async #loadStoredState() {
      if (!this.storageArea) return;

      try {
        const stored = await this.storageArea.get(STORAGE_KEY);
        const state = stored?.[STORAGE_KEY];
        if (state) this.#mergeState(state);
      } catch (err) {
        // The API may be missing, unsupported, or unavailable until the
        // extension has the storage permission. BroadcastChannel still works.
        console.warn('[ClinicalAlly] Session storage unavailable; using live in-memory sync:', err);
        this.storageArea = null;
      }
    }

    #commit() {
      this.stateVersion = this.#nextVersion();
      this.#refreshMessages();
      this.broadcastContext();
      this.#schedulePersist();
      this.#notify();
    }

    #schedulePersist() {
      if (!this.storageArea) return;
      const payload = this.#statePayload();

      this.persistQueue = this.persistQueue
        .catch(() => undefined)
        .then(async () => {
          if (!this.storageArea) return;
          try {
            await this.storageArea.set({ [STORAGE_KEY]: payload });
          } catch (err) {
            console.warn('[ClinicalAlly] Could not save session context:', err);
            this.storageArea = null;
          }
        });
    }

    #mergeState(remoteState) {
      if (!remoteState || typeof remoteState !== 'object') return false;
      if (
        remoteState.schemaVersion != null
        && remoteState.schemaVersion !== STORAGE_SCHEMA_VERSION
      ) return false;

      const before = this.#stateSummary();
      const remoteEpoch = typeof remoteState.epoch === 'string'
        ? remoteState.epoch
        : INITIAL_EPOCH;
      const remoteVersion = typeof remoteState.stateVersion === 'string'
        ? remoteState.stateVersion
        : '0';
      const remoteContextVersion = typeof remoteState.contextVersion === 'string'
        ? remoteState.contextVersion
        : remoteVersion;

      if (remoteEpoch < this.epoch) return false;

      if (remoteEpoch > this.epoch) {
        this.epoch = remoteEpoch;
        this.context = typeof remoteState.context === 'string' ? remoteState.context : '';
        this.turns = this.#normalizeTurns(
          remoteState.turns,
          remoteState.messages,
          remoteVersion,
        );
        this.stateVersion = remoteVersion;
        this.contextVersion = remoteContextVersion;
      } else {
        const remoteTurns = this.#normalizeTurns(
          remoteState.turns,
          remoteState.messages,
          remoteVersion,
        );
        const turnsById = new Map(this.turns.map((turn) => [turn.id, turn]));

        remoteTurns.forEach((remoteTurn) => {
          const localTurn = turnsById.get(remoteTurn.id);
          if (!localTurn || this.#imageSize(remoteTurn) > this.#imageSize(localTurn)) {
            turnsById.set(remoteTurn.id, remoteTurn);
          }
        });
        this.turns = [...turnsById.values()];

        if (remoteContextVersion > this.contextVersion) {
          this.context = typeof remoteState.context === 'string'
            ? remoteState.context
            : this.context;
          this.contextVersion = remoteContextVersion;
        }
        if (remoteVersion > this.stateVersion) this.stateVersion = remoteVersion;
      }

      this.#refreshMessages();
      return before !== this.#stateSummary();
    }

    #nextVersion() {
      this.sequence += 1;
      return `${String(Date.now()).padStart(13, '0')}:${this.originId}:${String(this.sequence).padStart(8, '0')}`;
    }

    #refreshMessages() {
      this.turns.sort((left, right) => left.id.localeCompare(right.id));
      if (this.turns.length > MAX_HISTORY_TURNS) {
        this.turns = this.turns.slice(-MAX_HISTORY_TURNS);
      }

      const turnTextSize = (turn) => turn.messages.reduce(
        (total, message) => total + message.content.length,
        0,
      );
      let historyChars = this.turns.reduce(
        (total, turn) => total + turnTextSize(turn),
        0,
      );
      while (this.turns.length > 1 && historyChars > MAX_HISTORY_CHARS) {
        historyChars -= turnTextSize(this.turns.shift());
      }

      // Prefer recent visual context while keeping multiple report turns when
      // they fit. Drop individual oldest images only when the shared base64
      // budget is exceeded; text from the turn remains available.
      let imageChars = this.turns.reduce(
        (total, turn) => total + this.#imageSize(turn),
        0,
      );
      for (const turn of this.turns) {
        if (imageChars <= MAX_HISTORY_IMAGE_CHARS) break;
        for (const message of turn.messages) {
          if (!Array.isArray(message.images)) continue;
          while (message.images.length && imageChars > MAX_HISTORY_IMAGE_CHARS) {
            imageChars -= message.images[0].length;
            message.images.shift();
          }
          if (!message.images.length) delete message.images;
          if (imageChars <= MAX_HISTORY_IMAGE_CHARS) break;
        }
      }

      this.messages = this.turns.flatMap((turn) => this.#copyMessages(turn.messages));
    }

    #normalizeMessages(messages) {
      if (!Array.isArray(messages)) return [];

      return messages
        .filter((message) => message && typeof message === 'object')
        .filter((message) => message.role === 'user' || message.role === 'assistant')
        .filter((message) => typeof message.content === 'string')
        .map((message) => {
          const normalized = {
            role: message.role,
            content: message.content,
          };

          if (message.role === 'user' && Array.isArray(message.images)) {
            const images = message.images.filter((image) => typeof image === 'string');
            if (images.length) normalized.images = images;
          }

          return normalized;
        });
    }

    #copyMessages(messages) {
      return messages.map((message) => ({
        ...message,
        ...(Array.isArray(message.images) ? { images: [...message.images] } : {}),
      }));
    }

    #normalizeTurns(turns, legacyMessages, fallbackId) {
      if (Array.isArray(turns)) {
        return turns
          .filter((turn) => turn && typeof turn.id === 'string')
          .map((turn) => ({
            id: turn.id,
            messages: this.#normalizeMessages(turn.messages),
          }))
          .filter((turn) => turn.messages.length);
      }

      const normalized = this.#normalizeMessages(legacyMessages);
      return normalized.length
        ? [{ id: `0000000000000:legacy:${fallbackId}`, messages: normalized }]
        : [];
    }

    #copyTurns(turns) {
      return turns.map((turn) => ({
        id: turn.id,
        messages: this.#copyMessages(turn.messages),
      }));
    }

    #imageSize(turn) {
      return turn.messages.reduce(
        (turnTotal, message) => turnTotal + (Array.isArray(message.images)
          ? message.images.reduce((imageTotal, image) => imageTotal + image.length, 0)
          : 0),
        0,
      );
    }

    #stateSnapshot() {
      return {
        context: this.context,
        messages: this.#copyMessages(this.messages),
        turns: this.#copyTurns(this.turns),
        epoch: this.epoch,
      };
    }

    #statePayload() {
      return {
        schemaVersion: STORAGE_SCHEMA_VERSION,
        context: this.context,
        turns: this.#copyTurns(this.turns),
        epoch: this.epoch,
        stateVersion: this.stateVersion,
        contextVersion: this.contextVersion,
      };
    }

    #stateSummary() {
      return JSON.stringify({
        context: this.context,
        epoch: this.epoch,
        stateVersion: this.stateVersion,
        contextVersion: this.contextVersion,
        turns: this.turns.map((turn) => ({
          id: turn.id,
          messages: turn.messages.map((message) => ({
            role: message.role,
            content: message.content,
            imageLengths: Array.isArray(message.images)
              ? message.images.map((image) => image.length)
              : [],
          })),
        })),
      });
    }

    #notify() {
      if (!this.initialized) return;
      this.listeners.forEach((listener) => this.#notifyListener(listener));
    }

    #notifyListener(listener) {
      try {
        listener(this.#stateSnapshot());
      } catch (err) {
        console.warn('[ClinicalAlly] Context subscriber failed:', err);
      }
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
