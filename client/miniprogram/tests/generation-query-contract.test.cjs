const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function fixture() {
  let request;
  const context = { module: { exports: {} }, wx: {
    getStorageSync: () => 'token',
    request(options) { request = options; options.success({ statusCode: 200, data: { code: 0, data: {} } }); },
  } };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../miniprogram/utils/api.js'), 'utf8'), context);
  return { api: context.module.exports, request: () => request };
}

for (const method of ['generateReading', 'generateTranslation', 'generateEssay']) {
  test(`${method}: stage travels in query parameters accepted by backend`, async () => {
    const f = fixture();
    await f.api[method]({ stage: 3, difficulty: '高 级&复习' });
    const request = f.request();
    const url = new URL(request.url);
    assert.equal(request.method, 'POST');
    assert.equal(url.searchParams.get('stage'), '3');
    if (method === 'generateReading') assert.equal(url.searchParams.get('difficulty'), '高 级&复习');
  });
}

for (const method of ['getScenarioList', 'getScenarioVideoList']) {
  test(`${method}: custom page size uses the backend field`, async () => {
    const f = fixture();
    await f.api[method]({ page: 2, pageSize: 7 });
    assert.equal(f.request().method, 'GET');
    assert.equal(f.request().data.page, 2);
    assert.equal(f.request().data.page_size, 7);
    assert.equal(f.request().data.pageSize, undefined);
  });
}
