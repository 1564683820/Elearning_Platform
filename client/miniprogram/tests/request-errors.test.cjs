const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function fixture(response) {
  let cleared = 0;
  let prompted = 0;
  const context = { module: { exports: {} }, wx: {
    getStorageSync: () => 'valid-token',
    removeStorageSync: () => { cleared++; },
    showModal: () => { prompted++; },
    request: options => options.success(response),
  } };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../miniprogram/utils/api.js'), 'utf8'), context);
  return { api: context.module.exports, cleared: () => cleared, prompted: () => prompted };
}

test('403 preserves login and presents the permission error', async () => {
  const f = fixture({ statusCode: 403, data: { detail: '无权操作该班级' } });
  await assert.rejects(f.api.callHttpAPI('/teacher/classes/1', {}, 'GET'), /无权操作该班级/);
  assert.equal(f.cleared(), 0);
  assert.equal(f.prompted(), 0);
});

test('401 still clears expired credentials and prompts login', async () => {
  const f = fixture({ statusCode: 401, data: { detail: 'expired' } });
  await assert.rejects(f.api.callHttpAPI('/private', {}, 'GET'), /登录已过期/);
  assert.equal(f.cleared(), 1);
  assert.equal(f.prompted(), 1);
});

test('HTTP failure is not success even if code zero appears in body', async () => {
  const f = fixture({ statusCode: 500, data: { code: 0, data: 'invalid' } });
  await assert.rejects(f.api.callHttpAPI('/failed', {}, 'GET'), /服务器内部错误/);
});
