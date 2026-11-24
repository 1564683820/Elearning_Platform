const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

test('batch favorite removal uses DELETE and preserves Snowflake IDs', async () => {
  let request;
  const context = { module: { exports: {} }, wx: {
    getStorageSync: () => 'test-token',
    request(options) { request = options; options.success({ statusCode: 200, data: { code: 0, data: { deleted_count: 1 } } }); },
  } };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../miniprogram/utils/api.js'), 'utf8'), context);
  await context.module.exports.batchRemoveFavorites(['9007199254740993']);
  assert.equal(request.method, 'DELETE');
  assert.ok(request.url.endsWith('/favorites/batch'));
  assert.equal(request.data.ids[0], '9007199254740993');
  assert.equal(request.header.Authorization, 'Bearer test-token');
});
