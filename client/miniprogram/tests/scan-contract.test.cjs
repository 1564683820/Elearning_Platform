const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function apiFixture(response) {
  let upload;
  const context = { module: { exports: {} }, wx: {
    getStorageSync: () => 'test-token',
    uploadFile(options) { upload = options; options.success(response); },
  } };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../miniprogram/utils/api.js'), 'utf8'), context);
  return { api: context.module.exports, upload: () => upload };
}

test('scan upload matches backend image/class_id contract and preserves IDs', async () => {
  const f = apiFixture({ statusCode: 200, data: JSON.stringify({ code: 0, data: { submission_id: '9007199254740993' } }) });
  const result = await f.api.scanGrade('9007199254740993', '/photo.jpg', '9007199254740995');
  assert.equal(f.upload().name, 'image');
  assert.equal(f.upload().formData.class_id, '9007199254740995');
  assert.ok(f.upload().url.endsWith('/teacher/exam/9007199254740993/scan-grade'));
  assert.equal(result.submission_id, '9007199254740993');
});

test('scan upload displays FastAPI detail on HTTP failure', async () => {
  const f = apiFixture({ statusCode: 401, data: JSON.stringify({ detail: '扫描会话已过期' }) });
  await assert.rejects(f.api.scanGrade('1', '/photo.jpg'), /扫描会话已过期/);
});

function pageFixture(result) {
  let page;
  let calls = 0;
  const context = { getApp: () => ({}), Page: p => { page = p; },
    require: () => ({ scanGrade: async () => result, callHttpAPI: async () => { calls++; } }),
    wx: { showToast() {}, showLoading() {}, hideLoading() {} }, console,
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../miniprogram/pages/teacher/scan/index.js'), 'utf8'), context);
  page.data = { ...page.data, examId: '1', classId: '2', photoQueue: [{ id: 'photo', tempPath: '/photo.jpg', status: 'processing' }] };
  page._recognizing = {};
  page.setData = updates => Object.assign(page.data, updates);
  page.loadProgress = async () => {};
  return { page, calls: () => calls };
}

test('saved scan uses authoritative totals and is never submitted twice', async () => {
  const f = pageFixture({ submission_id: '9007199254740993', total_score: 7.5, max_score: 100, answers: [{ question_number: 21, student_answer: 'B', is_correct: true, score: 2 }] });
  await f.page.recognizePhoto('photo');
  const item = f.page.data.photoQueue[0];
  assert.equal(item.score, 7.5);
  assert.equal(item.submission_id, '9007199254740993');
  assert.equal(item._submitted, true);
  assert.equal(f.page.data.unsubmittedCount, 0);
  await f.page.submitAllResults();
  assert.equal(f.calls(), 0);
});

test('HTTP error cannot be treated as success even if its body contains code zero', async () => {
  const f = apiFixture({ statusCode: 500, data: JSON.stringify({ code: 0, message: 'server failed' }) });
  await assert.rejects(f.api.scanGrade('1', '/photo.jpg'), /server failed/);
});

test('missing saved record is not shown as a successfully saved grade', async () => {
  const f = pageFixture({ total_score: 99, answers: [] });
  await f.page.recognizePhoto('photo');
  assert.equal(f.page.data.photoQueue[0].status, 'error');
  assert.equal(f.page.data.unsubmittedCount, 0);
  assert.equal(f.calls(), 0);
});
