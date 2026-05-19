// History Manager
// Manages chat thread history stored in browser.storage.local
// Storage key: 'clinicalAllyChatHistory'
//
// Schema:
// {
//   activeThreadId: "t_<timestamp>_<rand4>" | null,
//   threads: {
//     "t_<id>": {
//       id: "t_<id>",
//       title: "New chat",
//       createdAt: <ms>,
//       updatedAt: <ms>,
//       messages: [ { role, text, ts }, ... ]
//     }
//   }
// }

window.HistoryManager = class HistoryManager {
  constructor(storageKey = 'clinicalAllyChatHistory') {
    this.storageKey = storageKey;
    this.storage = browser.storage.local;
  }

  async _load() {
    const result = await this.storage.get(this.storageKey);
    return result?.[this.storageKey] ?? { activeThreadId: null, threads: {} };
  }

  async _save(state) {
    await this.storage.set({ [this.storageKey]: state });
  }

  _newId() {
    const rand4 = Math.random().toString(36).slice(2, 6).padEnd(4, '0');
    return `t_${Date.now()}_${rand4}`;
  }

  _pruneIfNeeded(state) {
    const ids = Object.keys(state.threads);
    if (ids.length <= 50) return;

    // Sort by updatedAt ascending — oldest first
    ids.sort((a, b) => state.threads[a].updatedAt - state.threads[b].updatedAt);

    // Remove oldest until we're at 50
    const toRemove = ids.slice(0, ids.length - 50);
    for (const id of toRemove) {
      delete state.threads[id];
    }

    // If active thread was pruned, set to newest remaining
    if (state.activeThreadId && !state.threads[state.activeThreadId]) {
      const remaining = Object.values(state.threads)
        .sort((a, b) => b.updatedAt - a.updatedAt);
      state.activeThreadId = remaining.length > 0 ? remaining[0].id : null;
    }
  }

  async createThread() {
    const state = await this._load();
    const id = this._newId();
    const now = Date.now();
    state.threads[id] = {
      id,
      title: 'New chat',
      createdAt: now,
      updatedAt: now,
      messages: [],
    };
    state.activeThreadId = id;
    await this._save(state);
    return id;
  }

  async setActive(id) {
    const state = await this._load();
    state.activeThreadId = id;
    await this._save(state);
  }

  async getThread(id) {
    const state = await this._load();
    return state.threads[id] ?? null;
  }

  async listThreads() {
    const state = await this._load();
    return Object.values(state.threads)
      .map(({ id, title, updatedAt }) => ({ id, title, updatedAt }))
      .sort((a, b) => b.updatedAt - a.updatedAt);
  }

  async appendMessage(threadId, role, text) {
    const state = await this._load();
    const thread = state.threads[threadId];
    if (!thread) throw new Error(`Thread not found: ${threadId}`);

    const now = Date.now();
    thread.messages.push({ role, text, ts: now });
    thread.updatedAt = now;

    this._pruneIfNeeded(state);
    await this._save(state);
  }

  async renameThread(id, title) {
    const state = await this._load();
    const thread = state.threads[id];
    if (!thread) throw new Error(`Thread not found: ${id}`);
    thread.title = title;
    await this._save(state);
  }

  async deleteThread(id) {
    const state = await this._load();
    delete state.threads[id];

    const remaining = Object.values(state.threads)
      .sort((a, b) => b.updatedAt - a.updatedAt);

    if (remaining.length > 0) {
      state.activeThreadId = remaining[0].id;
      await this._save(state);
    } else {
      // No threads left — create a fresh one
      await this._save(state);
      // createThread will load current state and save again
      const newId = this._newId();
      const now = Date.now();
      state.threads[newId] = {
        id: newId,
        title: 'New chat',
        createdAt: now,
        updatedAt: now,
        messages: [],
      };
      state.activeThreadId = newId;
      await this._save(state);
    }
  }

  async searchInThread(id, query) {
    const thread = await this.getThread(id);
    if (!thread) return [];
    const q = query.toLowerCase();
    return thread.messages
      .map((msg, idx) => (msg.text.toLowerCase().includes(q) ? idx : -1))
      .filter((idx) => idx !== -1);
  }
};
