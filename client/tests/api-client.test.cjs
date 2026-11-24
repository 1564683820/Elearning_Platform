const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const axios = require('axios');

function loadClient() {
  const source = fs.readFileSync(path.join(__dirname, '../src/api/client.ts'), 'utf8');
  const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
  const exports = {};
  vm.runInNewContext(js, { exports, require: () => axios, localStorage: { getItem: () => 'test-token' } });
  return exports.default;
}

test('HTTP failure keeps status, payload and Axios identity while presenting detail', async () => {
  const client = loadClient();
  let original;
  client.defaults.adapter = config => {
    original = new axios.AxiosError('Request failed', 'ERR_BAD_REQUEST', config, {}, {
      status: 403, statusText: 'Forbidden', headers: {}, config, data: { detail: '无权访问班级' },
    });
    return Promise.reject(original);
  };
  await assert.rejects(client.get('/teacher/classes/1'), error => {
    assert.equal(error, original);
    assert.equal(error.message, '无权访问班级');
    assert.equal(error.response.status, 403);
    assert.ok(axios.isAxiosError(error));
    return true;
  });
});

test('validation detail arrays produce readable messages', async () => {
  const client = loadClient();
  client.defaults.adapter = config => Promise.reject(new axios.AxiosError('Request failed', '', config, {}, {
    status: 422, config, data: { detail: [{ loc: ['body', 'image'], msg: 'Field required' }] },
  }));
  await assert.rejects(client.get('/upload'), error => {
    assert.equal(typeof error.message, 'string');
    assert.match(error.message, /image.*Field required/);
    return true;
  });
});

test('network and cancellation errors retain their codes', async () => {
  for (const original of [new axios.AxiosError('Network Error', 'ERR_NETWORK'), new axios.CanceledError('cancelled')]) {
    const client = loadClient();
    client.defaults.adapter = () => Promise.reject(original);
    await assert.rejects(client.get('/slow'), error => error === original && error.code === original.code);
  }
});

test('requests retain configured prefix and current token', async () => {
  const client = loadClient();
  client.defaults.adapter = async config => {
    assert.equal(config.baseURL, '/Elearning/api/v1');
    assert.equal(config.headers.Authorization, 'Bearer test-token');
    return { data: { code: 0 }, status: 200, headers: {}, config };
  };
  await client.get('/teacher/classes');
});
