const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

test('word progress posts mastery to the authenticated backend route', async () => {
  let request;
  const context = { module: { exports: {} }, wx: {
    getStorageSync: () => 'test-token',
    request(options) { request = options; options.success({ statusCode: 200, data: {
      code: 0, data: { mastery_level: 1, review_count: 2 },
    } }); },
  } };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../miniprogram/utils/api.js'), 'utf8'), context);
  const result = await context.module.exports.recordWordProgress('12345', 1);
  assert.ok(request.url.endsWith('/words/12345/progress'));
  assert.equal(request.method, 'POST');
  assert.equal(request.data.mastery_level, 1);
  assert.equal(request.header.Authorization, 'Bearer test-token');
  assert.equal(result.review_count, 2);
});

test('browsing a word preserves an existing higher mastery level', async () => {
  let page, saved;
  const context = { Page: p => { page = p; }, console,
    require: () => ({ recordWordProgress: async (...args) => { saved = args; } }),
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../miniprogram/pages/memory/word/index.js'), 'utf8'), context);
  for (const level of [0, 1, 2, 3]) {
    page.data.wordDetail = { id: 12, progress: { mastery_level: level } };
    await page.recordCurrentWordProgress();
    assert.equal(saved[0], 12);
    assert.equal(saved[1], Math.max(1, level));
  }
});
