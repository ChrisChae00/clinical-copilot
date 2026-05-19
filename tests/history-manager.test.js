// Unit tests for HistoryManager
// Mock browser.storage.local, run with: node tests/history-manager.test.js

'use strict';

// ── Mock browser.storage.local ────────────────────────────────────────────────
let mockStore = {};

global.browser = {
  storage: {
    local: {
      get: async (key) => {
        if (mockStore[key] === undefined) return {};
        return { [key]: mockStore[key] };
      },
      set: async (obj) => {
        Object.assign(mockStore, obj);
      },
      remove: async (key) => {
        delete mockStore[key];
      },
    },
  },
};

// Allow window.HistoryManager = ... assignment to work in Node
global.window = global;

// Load module under test
require('../extension/history-manager.js');
const HistoryManager = global.window.HistoryManager;

// ── Test runner ───────────────────────────────────────────────────────────────
let passed = 0;
let failed = 0;

function resetStore() {
  mockStore = {};
}

async function test(name, fn) {
  resetStore();
  try {
    await fn();
    console.log(`  PASS  ${name}`);
    passed++;
  } catch (err) {
    console.error(`  FAIL  ${name}`);
    console.error(`        ${err.message}`);
    failed++;
  }
}

function assert(condition, message) {
  if (!condition) throw new Error(message || 'Assertion failed');
}

function assertEqual(actual, expected, message) {
  if (actual !== expected) {
    throw new Error(message || `Expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}

// ── Helper: small async delay ─────────────────────────────────────────────────
const delay = (ms) => new Promise((r) => setTimeout(r, ms));

// ── Tests ─────────────────────────────────────────────────────────────────────
(async () => {
  console.log('\nRunning HistoryManager tests...\n');

  // 1. createThread returns id and sets it active
  await test('createThread returns id and sets it active', async () => {
    const hm = new HistoryManager();
    const id = await hm.createThread();
    assert(typeof id === 'string' && id.startsWith('t_'), `id should start with "t_", got: ${id}`);

    const state = (await browser.storage.local.get('clinicalAllyChatHistory'))['clinicalAllyChatHistory'];
    assertEqual(state.activeThreadId, id, 'activeThreadId should match created id');
    assertEqual(state.threads[id].title, 'New chat', 'title should be "New chat"');
    assert(Array.isArray(state.threads[id].messages) && state.threads[id].messages.length === 0,
      'messages should be empty array');
  });

  // 2. appendMessage saves user + assistant messages
  await test('appendMessage saves user + assistant messages', async () => {
    const hm = new HistoryManager();
    const id = await hm.createThread();
    await hm.appendMessage(id, 'user', 'Hello');
    await hm.appendMessage(id, 'assistant', 'Hi there');

    const thread = await hm.getThread(id);
    assertEqual(thread.messages.length, 2, 'should have 2 messages');
    assertEqual(thread.messages[0].role, 'user', 'first message role');
    assertEqual(thread.messages[0].text, 'Hello', 'first message text');
    assertEqual(thread.messages[1].role, 'assistant', 'second message role');
    assertEqual(thread.messages[1].text, 'Hi there', 'second message text');
    assert(typeof thread.messages[0].ts === 'number', 'ts should be numeric');
    assert(typeof thread.messages[1].ts === 'number', 'ts should be numeric');
  });

  // 3. listThreads returns threads sorted by updatedAt desc
  await test('listThreads returns threads sorted by updatedAt desc', async () => {
    const hm = new HistoryManager();
    const id1 = await hm.createThread();
    await delay(5);
    const id2 = await hm.createThread();

    const list = await hm.listThreads();
    assertEqual(list.length, 2, 'should have 2 threads');
    assertEqual(list[0].id, id2, 'newest thread should be first');
    assertEqual(list[1].id, id1, 'older thread should be second');
  });

  // 4. renameThread updates title
  await test('renameThread updates title', async () => {
    const hm = new HistoryManager();
    const id = await hm.createThread();
    await hm.renameThread(id, 'My renamed thread');
    const thread = await hm.getThread(id);
    assertEqual(thread.title, 'My renamed thread', 'title should be updated');
  });

  // 5. deleteThread removes thread and moves active to next newest
  await test('deleteThread removes thread and moves active to next newest', async () => {
    const hm = new HistoryManager();
    const id1 = await hm.createThread();
    await delay(5);
    const id2 = await hm.createThread();

    await hm.deleteThread(id2);

    const state = (await browser.storage.local.get('clinicalAllyChatHistory'))['clinicalAllyChatHistory'];
    assert(!state.threads[id2], 'deleted thread should not exist');
    assertEqual(state.activeThreadId, id1, 'active should move to older thread');
  });

  // 6. deleteThread on last thread creates a new one
  await test('deleteThread on last thread creates a new one', async () => {
    const hm = new HistoryManager();
    const id = await hm.createThread();
    await hm.deleteThread(id);

    const state = (await browser.storage.local.get('clinicalAllyChatHistory'))['clinicalAllyChatHistory'];
    assert(!state.threads[id], 'original thread should be gone');
    assert(state.activeThreadId !== null, 'activeThreadId should not be null');
    const newId = state.activeThreadId;
    assert(newId.startsWith('t_'), 'new thread id should start with t_');
    assert(state.threads[newId], 'new thread should exist in threads');
  });

  // 7. prune keeps only 50 newest threads
  await test('prune keeps only 50 newest threads', async () => {
    const hm = new HistoryManager();
    for (let i = 0; i < 51; i++) {
      const id = await hm.createThread();
      await hm.appendMessage(id, 'user', `msg ${i}`);
      if (i < 50) await delay(2); // ensure distinct updatedAt for first 50
    }
    const list = await hm.listThreads();
    assertEqual(list.length, 50, 'should only have 50 threads after pruning');
  });

  // 8. searchInThread returns indices of matching messages
  await test('searchInThread returns indices of matching messages', async () => {
    const hm = new HistoryManager();
    const id = await hm.createThread();
    await hm.appendMessage(id, 'user', 'Patient on medication A');
    await hm.appendMessage(id, 'assistant', 'Diabetes management plan');
    await hm.appendMessage(id, 'user', 'Follow up next week');

    const medMatches = await hm.searchInThread(id, 'medication');
    assertEqual(medMatches.length, 1, 'medication should match 1 message');
    assertEqual(medMatches[0], 0, 'medication match should be at index 0');

    const diabMatches = await hm.searchInThread(id, 'iabet');
    assertEqual(diabMatches.length, 1, 'iabet should match 1 message');
    assertEqual(diabMatches[0], 1, 'iabet match should be at index 1');
  });

  // 9. searchInThread is case-insensitive
  await test('searchInThread is case-insensitive', async () => {
    const hm = new HistoryManager();
    const id = await hm.createThread();
    await hm.appendMessage(id, 'user', 'Diabetes is a concern');

    const matches = await hm.searchInThread(id, 'diabetes');
    assertEqual(matches.length, 1, 'case-insensitive search should find 1 match');
  });

  // 10. setActive changes activeThreadId
  await test('setActive changes activeThreadId', async () => {
    const hm = new HistoryManager();
    const id1 = await hm.createThread();
    await delay(5);
    const id2 = await hm.createThread();

    // id2 is active now; switch back to id1
    await hm.setActive(id1);
    const state = (await browser.storage.local.get('clinicalAllyChatHistory'))['clinicalAllyChatHistory'];
    assertEqual(state.activeThreadId, id1, 'activeThreadId should be id1');
  });

  // 11. getThread returns null for unknown id
  await test('getThread returns null for unknown id', async () => {
    const hm = new HistoryManager();
    await hm.createThread();
    const result = await hm.getThread('t_nonexistent_0000');
    assertEqual(result, null, 'getThread should return null for unknown id');
  });

  // 12. setActive throws for unknown id
  await test('setActive throws for unknown id', async () => {
    const hm2 = new HistoryManager();
    let threw = false;
    try {
      await hm2.setActive('t_nonexistent');
    } catch (e) {
      threw = true;
    }
    assert(threw, 'setActive should throw for unknown id');
  });

  // ── Summary ───────────────────────────────────────────────────────────────
  console.log(`\n${passed} passed, ${failed} failed\n`);
  if (failed > 0) process.exit(1);
})();
