const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function fixture(kind, submitAnswer, wxOverrides = {}, apiOverrides = {}) {
  let page;
  const root = path.resolve(__dirname, '../miniprogram');
  const api = { submitAnswer, ...apiOverrides };
  let helper;
  const context = { Page: p => { page = p; }, console, getApp: () => ({ globalData: { stage: 3 } }),
    wx: { showToast() {}, ...wxOverrides }, Date,
    require: name => name.endsWith('api.js') ? api : helper,
  };
  const helperContext = { module: { exports: {} }, wx: context.wx, Date };
  vm.runInNewContext(fs.readFileSync(path.join(root, 'utils/material-training.js'), 'utf8'), helperContext);
  helper = helperContext.module.exports;
  vm.runInNewContext(fs.readFileSync(path.join(root, `pages/training/${kind}/index.js`), 'utf8'), context);
  page.data = { ...page.data, mode: 'question', submitting: false,
    questionStartedAt: Date.now(),
    questions: [{ id: '9007199254740993', content: { stem: 'Choose', options: ['a', 'b'], correct: 1 } }],
  };
  page.setData = updates => Object.assign(page.data, updates);
  return page;
}

test('listening: controls drive audio, update progress and release on exit', () => {
  const handlers = {};
  let plays = 0, pauses = 0, destroyed = 0;
  const audio = { currentTime: 12.7, duration: 30,
    play() { plays++; handlers.Play(); }, pause() { pauses++; handlers.Pause(); }, destroy() { destroyed++; },
  };
  for (const event of ['Play', 'Pause', 'Ended', 'Error', 'TimeUpdate']) audio[`on${event}`] = cb => { handlers[event] = cb; };
  const page = fixture('listening', async () => {}, { createInnerAudioContext: () => audio });
  page.data.currentMaterial = { audio_url: 'https://test.invalid/audio.mp3' };
  page.onPlayToggle();
  assert.equal(plays, 1);
  assert.equal(page.data.isPlaying, true);
  assert.equal(audio.src, page.data.currentMaterial.audio_url);
  handlers.TimeUpdate();
  assert.equal(page.data.currentTime, '0:12');
  page.onSpeedChange({ currentTarget: { dataset: { index: 2 } } });
  assert.equal(audio.playbackRate, 1.2);
  page.onHide();
  assert.equal(pauses, 1);
  page.onBack();
  assert.equal(destroyed, 1);
  handlers.Play();
  assert.equal(page.data.isPlaying, false);
});

for (const kind of ['reading', 'listening', 'phrase-grammar']) {
  test(`${kind}: all template tap bindings have handlers`, () => {
    const page = fixture(kind, async () => {});
    const markup = fs.readFileSync(path.resolve(__dirname, `../miniprogram/pages/training/${kind}/index.wxml`), 'utf8');
    for (const match of markup.matchAll(/bindtap="(\w+)"/g)) assert.equal(typeof page[match[1]], 'function', match[1]);
  });
}

for (const kind of ['reading', 'listening', 'phrase-grammar']) {
  test(`${kind}: submits real ID once and uses server result`, async () => {
    let resolve, calls = 0, request;
    const page = fixture(kind, payload => { calls++; request = payload; return new Promise(r => { resolve = r; }); });
    const pending = page.onSelectOption({ currentTarget: { dataset: { index: 0 } } });
    await page.onSelectOption({ currentTarget: { dataset: { index: 0 } } });
    assert.equal(calls, 1);
    assert.equal(request.questionId, '9007199254740993');
    assert.equal(request.answer, 0);
    assert.equal(page.data.answered, false);
    resolve({ is_correct: true, correct_answer: 0, analysis: { explanation: 'Server explanation' } });
    await pending;
    assert.equal(page.data.correctCount, 1);
    assert.equal(page.data.answered, true);
    assert.equal(page.data.question.correctIndex, 0);
  });

  test(`${kind}: failed save remains retryable without local credit`, async () => {
    const page = fixture(kind, async () => { throw Error('offline'); });
    await page.onSelectOption({ currentTarget: { dataset: { index: 0 } } });
    assert.equal(page.data.answered, false);
    assert.equal(page.data.correctCount, 0);
    assert.equal(page.data.submitting, false);
  });

  test(`${kind}: late response after leaving does not change result`, async () => {
    let resolve;
    const page = fixture(kind, () => new Promise(r => { resolve = r; }));
    const pending = page.onSelectOption({ currentTarget: { dataset: { index: 0 } } });
    page.onUnload();
    resolve({ is_correct: true, correct_answer: 0 });
    await pending;
    assert.equal(page.data.correctCount, 0);
  });
}

test('grammar: loads actual type 4 questions with stage and hides answers until saved', async () => {
  let request;
  const page = fixture('phrase-grammar', async () => {}, {}, {
    generateTrainingQuestions: async payload => {
      request = payload;
      return [{ id: '9007199254740993', content: { stem: 'Grammar stem', options: ['a', 'b'], correct: 0 } }];
    },
  });
  await page.loadQuestion();
  assert.equal(request.stage, 3);
  assert.equal(request.questionTypes[0], 4);
  assert.equal(page.data.question.stem, 'Grammar stem');
  assert.equal(page.data.questions[0].id, '9007199254740993');
  assert.equal(page.data.question.correctIndex, -1);
});

test('grammar: empty question bank and fetch failures remain visible and retryable', async () => {
  let fail = false;
  const page = fixture('phrase-grammar', async () => {}, {}, {
    generateTrainingQuestions: async () => { if (fail) throw Error('offline'); return []; },
  });
  await page.loadQuestion();
  assert.equal(page.data.question, null);
  assert.equal(page.data.loading, false);
  fail = true;
  await page.loadQuestion();
  assert.equal(page.data.question, null);
  assert.ok(page.data.error);
});
