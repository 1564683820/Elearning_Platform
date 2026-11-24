const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function fixture(api) {
  let page;
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../miniprogram/pages/training/word-quiz/index.js'), 'utf8'), {
    Page: p => { page = p; }, console, Date,
    require: name => name.endsWith('api.js') ? api : {},
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

for (const [key, name] of [['translation', 'Translation'], ['essay', 'Essay']]) {
  test(`${key}: grading is exclusive and answer stays matched to the request`, async () => {
    let resolve, calls = 0, fetches = 0;
    const page = fixture({ [`score${name}`]: () => { calls++; return new Promise(r => { resolve = r; }); },
      fetchFromQuestionBank: async () => { fetches++; return { stem: 'New' }; } });
    Object.assign(page.data[key], { stem: 'Topic', reference: 'Ref', userAnswer: 'My answer', questionBankId: '9007199254740993' });
    const pending = page[`on${name}Submit`]();
    const duplicate = page[`on${name}Submit`]();
    assert.equal(calls, 1);
    page[`on${name}Input`]({ detail: { value: 'Changed during grading' } });
    assert.equal(page.data[key].userAnswer, 'My answer');
    page[`on${name}Retry`]();
    assert.equal(page.data[key].userAnswer, 'My answer');
    await page[`on${name}Next`]();
    await page[`load${name}Question`]();
    assert.equal(fetches, 0);
    resolve({ score: 80, feedback: 'Feedback' });
    await Promise.all([pending, duplicate]);
    assert.equal(page.data[key].submitted, true);
    assert.equal(page.data[key].loading, false);
  });

  test(`${key}: failure preserves the draft for retry`, async () => {
    const page = fixture({ [`score${name}`]: async () => { throw Error('offline'); } });
    Object.assign(page.data[key], { stem: 'Topic', userAnswer: 'Draft' });
    await page[`on${name}Submit`]();
    assert.equal(page.data[key].submitted, false);
    assert.equal(page.data[key].loading, false);
    assert.equal(page.data[key].userAnswer, 'Draft');
  });

  test(`${key}: stale fetch cannot replace the newest question`, async () => {
    const requests = [];
    const page = fixture({ fetchFromQuestionBank: () => new Promise(r => requests.push(r)) });
    const first = page[`load${name}Question`]();
    const second = page[`load${name}Question`]();
    requests[1]({ stem: 'Newest', reference: 'Ref' });
    await second;
    requests[0]({ stem: 'Old', reference: 'Ref' });
    await first;
    assert.equal(page.data[key].stem, 'Newest');
  });

  test(`${key}: unload ignores late score result`, async () => {
    let resolve;
    const page = fixture({ [`score${name}`]: () => new Promise(r => { resolve = r; }) });
    Object.assign(page.data[key], { stem: 'Topic', userAnswer: 'Draft' });
    const pending = page[`on${name}Submit`]();
    page.onUnload();
    resolve({ score: 80 });
    await pending;
    assert.equal(page.data[key].submitted, false);
  });

  test(`${key}: empty fetch exposes retry state and clears previous question`, async () => {
    const page = fixture({ fetchFromQuestionBank: async () => null });
    Object.assign(page.data[key], { stem: 'Old', scoreResult: { score: 80 }, submitted: true });
    await page[`load${name}Question`]();
    assert.equal(page.data[key].stem, '');
    assert.equal(page.data[key].scoreResult, null);
    assert.equal(page.data[key].submitted, false);
    assert.equal(page.data[key].loading, false);
    assert.ok(page.data[key].error);
  });

  test(`${key}: late failed fetch cannot clear newer loading state`, async () => {
    const requests = [];
    const page = fixture({ fetchFromQuestionBank: () => new Promise((resolve, reject) => requests.push({ resolve, reject })) });
    const first = page[`load${name}Question`]();
    const second = page[`load${name}Question`]();
    requests[0].reject(Error('old failure'));
    await first;
    assert.equal(page.data[key].loading, true);
    requests[1].resolve({ stem: 'Current' });
    await second;
    assert.equal(page.data[key].stem, 'Current');
    assert.equal(page.data[key].loading, false);
  });
}
