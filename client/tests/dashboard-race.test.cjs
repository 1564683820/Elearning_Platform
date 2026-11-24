const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((r, j) => { resolve = r; reject = j; });
  return { promise, resolve, reject };
}

function fixture(pageName, api) {
  const effects = [];
  const state = [];
  let cursor = 0;
  let params = { classId: '1', studentId: '10' };
  const source = fs.readFileSync(path.join(__dirname, `../src/pages/${pageName}/index.tsx`), 'utf8');
  const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
  const exports = {};
  const modules = {
    react: {
      useState(initial) { const id = cursor++; if (!(id in state)) state[id] = initial; return [state[id], value => { state[id] = value; }]; },
      useEffect(fn) { effects.push(fn); }, useRef: () => ({ current: null }),
    },
    'react-router-dom': { useParams: () => params, useNavigate: () => () => {} },
    'react/jsx-runtime': { jsx: () => null, jsxs: () => null },
  };
  vm.runInNewContext(js, { exports, require: name => modules[name] || (name.includes('api/teacher') ? { teacherApi: api } : { colors: {} }), AbortController, Error });
  return {
    state,
    render(next) { params = next; cursor = 0; effects.length = 0; exports.default(); return effects[0](); },
  };
}

test('dashboard ignores a previous class response arriving after the current class', async () => {
  const old = deferred();
  const current = deferred();
  let calls = 0;
  const f = fixture('Dashboard', {
    getClassDashboard: () => (++calls === 1 ? old.promise : current.promise),
    listStudents: async () => [],
  });
  const cleanup = f.render({ classId: '1' });
  cleanup();
  f.render({ classId: '2' });
  current.resolve({ class_id: '2' });
  await new Promise(setImmediate);
  old.resolve({ class_id: '1' });
  await new Promise(setImmediate);
  assert.equal(f.state[0].class_id, '2');
  assert.equal(f.state[2], false);
});

test('student detail clears old data and reports request failure', async () => {
  const pending = deferred();
  const failed = deferred();
  let calls = 0;
  const f = fixture('StudentDetail', { getStudentDetail: () => (++calls === 1 ? pending.promise : failed.promise) });
  f.render({ classId: '1', studentId: '10' });
  pending.resolve({ nickname: 'first' });
  await new Promise(setImmediate);
  assert.equal(f.state[0].nickname, 'first');
  // Replace data while a subsequent request is pending; old student must disappear.
  // This fixture exercises effects, not the loaded page's visual layout.
  f.state[1] = true;
  f.render({ classId: '2', studentId: '20' });
  assert.equal(f.state[0], null);
  assert.equal(f.state[1], true);
  failed.reject(new Error('无权访问该学生'));
  await new Promise(setImmediate);
  assert.equal(f.state[2], '无权访问该学生');
  assert.equal(f.state[1], false);
});
