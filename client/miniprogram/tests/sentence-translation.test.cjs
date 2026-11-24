const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function fixture(fetchQuestion) {
  let page;
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../miniprogram/pages/training/sentence-translate/index.js'), 'utf8'), {
    Page: p => { page = p; }, console, getApp: () => ({ globalData: { stage: 3 } }),
    require: () => ({ fetchFromQuestionBank: fetchQuestion }), wx: { showToast() {}, navigateBack() {} },
  });
  page.data = { ...page.data };
  page.setData = updates => Object.assign(page.data, updates);
  return page;
}

const sample = { question_bank_id: '9007199254740993', stem: '你好。', reference: 'Hello.', hints: 'Greeting' };

test('translation loads actual bilingual question with stage and displays paired reference', async () => {
  let request;
  const page = fixture(async data => { request = data; return sample; });
  await page.loadQuestions();
  assert.equal(request.qtype, 'translation');
  assert.equal(request.stage, 3);
  assert.equal(page.data.question.id, sample.question_bank_id);
  assert.equal(page.data.question.zh, '你好。');
  page.onInput({ detail: { value: 'Hi.' } });
  await page.onSubmit();
  assert.equal(page.data.referenceText, 'Hello.');
  assert.equal(page.data.showReference, true);
});

test('direction changes clear old answer/reference and reverse source pairing', async () => {
  const page = fixture(async () => sample);
  await page.loadQuestions();
  page.onInput({ detail: { value: 'Hi.' } });
  await page.onSubmit();
  page.onDirectionChange({ currentTarget: { dataset: { dir: 'en2zh' } } });
  assert.equal(page.data.inputText, '');
  assert.equal(page.data.showReference, false);
  page.onInput({ detail: { value: '你好' } });
  await page.onSubmit();
  assert.equal(page.data.referenceText, '你好。');
});

test('fetch failure and incomplete question never silently become sample exercises', async () => {
  for (const fetchQuestion of [async () => { throw Error('offline'); }, async () => ({ stem: 'incomplete' })]) {
    const page = fixture(fetchQuestion);
    await page.loadQuestions();
    assert.equal(page.data.question, null);
    assert.ok(page.data.error);
    assert.equal(page.data.loading, false);
  }
});

test('late fetch after unload cannot overwrite the page', async () => {
  let resolve;
  const page = fixture(() => new Promise(r => { resolve = r; }));
  const pending = page.loadQuestions();
  page.onUnload();
  resolve(sample);
  await pending;
  assert.equal(page.data.question, null);
});

test('next question fetches fresh data and cannot skip unanswered practice', async () => {
  let count = 0;
  const page = fixture(async () => { count++; return sample; });
  await page.loadQuestions();
  await page.onNextQuestion();
  assert.equal(count, 1);
  page.onInput({ detail: { value: 'Hi.' } });
  await page.onSubmit();
  await page.onNextQuestion();
  assert.equal(count, 2);
  assert.equal(page.data.currentIndex, 1);
  assert.equal(page.data.showReference, false);
});

test('translation template binds implemented handlers and the actual reference field', () => {
  const page = fixture(async () => sample);
  const markup = fs.readFileSync(path.join(__dirname, '../miniprogram/pages/training/sentence-translate/index.wxml'), 'utf8');
  for (const match of markup.matchAll(/bindtap="(\w+)"/g)) assert.equal(typeof page[match[1]], 'function', match[1]);
  assert.ok(markup.includes('{{referenceText}}'));
});
