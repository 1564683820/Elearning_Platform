const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function fixture(api) {
  let page;
  const root = path.resolve(__dirname, '../miniprogram');
  const helperContext = { module: { exports: {} } };
  vm.runInNewContext(fs.readFileSync(path.join(root, 'utils/material-training.js'), 'utf8'), helperContext);
  vm.runInNewContext(fs.readFileSync(path.join(root, 'pages/training/word-quiz/index.js'), 'utf8'), {
    Page: p => { page = p; }, console, Date,
    require: name => name.endsWith('api.js') ? api : helperContext.module.exports,
    getApp: () => ({ globalData: { stage: 3 } }), wx: { showToast() {} },
  });
  page.data = JSON.parse(JSON.stringify(page.data));
  page.setData = updates => {
    for (const [key, value] of Object.entries(updates)) {
      const fields = key.split('.'); let target = page.data;
      for (const field of fields.slice(0, -1)) target = target[field];
      target[fields.at(-1)] = value;
    }
  };
  page.refreshFavStatus = () => {};
  return page;
}

const questions = [
  { id: '9007199254740993', content: { stem: 'First', options: ['a', 'b'], correct: 1 } },
  { id: '9007199254740995', content: { stem: 'Second', options: ['c', 'd'], correct: 0 } },
];

for (const [key, load, select] of [
  ['wordQuiz', 'loadWordQuestions', 'onWordQuizSelect'],
  ['phrase', 'loadPhraseQuestions', 'onPhraseSelect'],
]) {
  test(`${key}: loads nested content and waits for authoritative save`, async () => {
    let resolve, request, calls = 0;
    const page = fixture({ generateTrainingQuestions: async () => questions,
      submitAnswer: data => { calls++; request = data; return new Promise(r => { resolve = r; }); } });
    await page[load]();
    assert.equal(page.data[key].question.stem, 'First');
    assert.equal(page.data[key].question.options.length, 2);
    const pending = page[select](0);
    await page[select](0);
    assert.equal(calls, 1);
    assert.equal(request.questionId, questions[0].id);
    assert.equal(page.data[key].answered, false);
    resolve({ is_correct: true, correct_answer: 0, analysis: { explanation: 'Server' } });
    await pending;
    assert.equal(page.data[key].correctCount, 1);
    assert.equal(page.data[key].question.correctIndex, 0);
  });

  test(`${key}: failed save stays retryable and does not count as answered`, async () => {
    const page = fixture({ generateTrainingQuestions: async () => questions,
      submitAnswer: async () => { throw Error('offline'); } });
    await page[load]();
    await page[select](0);
    assert.equal(page.data[key].answered, false);
    assert.equal(page.data[key].correctCount, 0);
    assert.equal(page.data[key].submitting, false);
  });

  test(`${key}: reload makes old answer response obsolete`, async () => {
    let resolve;
    const page = fixture({ generateTrainingQuestions: async () => questions,
      submitAnswer: () => new Promise(r => { resolve = r; }) });
    await page[load]();
    const pending = page[select](0);
    await page[load]();
    resolve({ is_correct: true, correct_answer: 0 });
    await pending;
    assert.equal(page.data[key].answered, false);
    assert.equal(page.data[key].correctCount, 0);
  });
}

test('returning to a saved word restores the answer without submitting or counting twice', async () => {
  let calls = 0;
  const page = fixture({ generateTrainingQuestions: async () => questions,
    submitAnswer: async () => { calls++; return { is_correct: true, correct_answer: 0 }; } });
  await page.loadWordQuestions();
  await page.onWordQuizSelect(0);
  page.onWordQuizNext();
  page.onWordQuizPrev();
  assert.equal(page.data.wordQuiz.answered, true);
  assert.equal(page.data.wordQuiz.selectedIndex, 0);
  await page.onWordQuizSelect(0);
  assert.equal(calls, 1);
  assert.equal(page.data.wordQuiz.correctCount, 1);
});

test('pending save blocks navigation and unload rejects late updates', async () => {
  let resolve;
  const page = fixture({ generateTrainingQuestions: async () => questions,
    submitAnswer: () => new Promise(r => { resolve = r; }) });
  await page.loadWordQuestions();
  const pending = page.onWordQuizSelect(0);
  page.onWordQuizNext();
  assert.equal(page.data.wordQuiz.currentIndex, 0);
  page.onUnload();
  resolve({ is_correct: true, correct_answer: 0 });
  await pending;
  assert.equal(page.data.wordQuiz.correctCount, 0);
});

test('newer question load wins even if the first load finishes last', async () => {
  const resolvers = [];
  const page = fixture({ generateTrainingQuestions: () => new Promise(r => resolvers.push(r)) });
  const first = page.loadWordQuestions();
  const second = page.loadWordQuestions();
  resolvers[1]([questions[1]]);
  await second;
  resolvers[0]([questions[0]]);
  await first;
  assert.equal(page.data.wordQuiz.question.id, questions[1].id);
});

test('empty or failed question fetch has no stale question and stays retryable', async () => {
  let fail = false;
  const page = fixture({ generateTrainingQuestions: async () => { if (fail) throw Error('offline'); return []; } });
  await page.loadWordQuestions();
  assert.equal(page.data.wordQuiz.question, null);
  assert.equal(page.data.wordQuiz.loading, false);
  fail = true;
  await page.loadWordQuestions();
  assert.ok(page.data.wordQuiz.error);
  assert.equal(page.data.wordQuiz.question, null);
});
