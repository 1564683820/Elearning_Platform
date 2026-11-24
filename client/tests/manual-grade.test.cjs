const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const { test } = require('node:test');

function loadApi(fetchImpl) {
  const calls = [];
  const client = new Proxy({}, { get: (_, method) => (...args) => {
    calls.push({ method, args });
    return Promise.resolve({ data: { data: { submission_id: '9007199254740993' } } });
  } });
  const source = fs.readFileSync(path.join(__dirname, '../src/api/teacher.ts'), 'utf8');
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
  const exports = {};
  vm.runInNewContext(compiled, { exports, fetch: fetchImpl, localStorage: { getItem: () => 'test-token' }, require: () => ({ __esModule: true, default: client, getBaseURL: () => '/Elearning/api/v1' }) });
  return { api: exports.teacherApi, calls };
}

test('AI class query passes cancellation signal to actual fetch boundary', async () => {
  const controller = new AbortController();
  let request;
  const { api } = loadApi(async (url, options) => { request = { url, options }; return {}; });
  await api.aiQueryStream({ class_id: '9007199254740993', question: 'summary' }, controller.signal);
  assert.equal(request.options.signal, controller.signal);
  assert.equal(request.url, '/Elearning/api/v1/teacher/ai-query/stream');
  assert.equal(JSON.parse(request.options.body).class_id, '9007199254740993');
  controller.abort();
  assert.equal(request.options.signal.aborted, true);
});

test('grading info preserves a Snowflake ID verbatim', async () => {
  const { api, calls } = loadApi();
  await api.getExamGradingInfo('9007199254740993');
  assert.equal(calls[0].args[0], '/teacher/exam/9007199254740993/grading-info');
});

test('manual grading uses shared client and multipart with exact ID and payload', async () => {
  const { api, calls } = loadApi();
  const form = new FormData();
  form.append('manual_answers_json', '{"21":"B"}');
  const result = await api.manualGrade('9007199254740993', form);
  assert.equal(calls[0].method, 'post');
  assert.equal(calls[0].args[0], '/teacher/exam/9007199254740993/manual-grade');
  assert.equal(calls[0].args[1], form);
  assert.equal(calls[0].args[2].headers['Content-Type'], 'multipart/form-data');
  assert.equal(result.submission_id, '9007199254740993');
});

function keyboardFixture() {
  const file = ts.createSourceFile('page.tsx', fs.readFileSync(path.join(__dirname, '../src/pages/ManualGrade/index.tsx'), 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  let handler;
  function visit(node) {
    if (ts.isVariableDeclaration(node) && node.name.getText(file) === 'handleKey') handler = node.initializer.getText(file);
    ts.forEachChild(node, visit);
  }
  visit(file);
  assert.ok(handler, 'keyboard event handler exists');
  const js = ts.transpileModule(`const handler = ${handler};`, { compilerOptions: { target: ts.ScriptTarget.ES2020 } }).outputText;
  const selected = [];
  class Element {
    constructor(editable = false) { this.editable = editable; }
    closest() { return this.editable ? this : null; }
  }
  const context = {
    HTMLElement: Element, focusQnum: 21, submitting: false, gradeResult: null,
    gradingInfo: { questions: [{ question_number: 21, options: ['A', 'B', 'C', 'D'] }] },
    selectAnswer: (...args) => selected.push(args), setFocusQnum: () => {}, setAnswers: () => {},
  };
  vm.createContext(context);
  vm.runInContext(js, context);
  return {
    selected, context,
    press(key, editable = false, overrides = {}) {
      let prevented = false;
      context.event = { key, target: new Element(editable), preventDefault() { prevented = true; }, ...overrides };
      vm.runInContext('handler(event)', context);
      return prevented;
    },
  };
}

test('keyboard grading leaves input fields and shortcut keys alone', () => {
  const f = keyboardFixture();
  assert.equal(f.press('A', true), false);
  assert.equal(f.press('Backspace', true), false);
  assert.equal(f.press('A', false, { ctrlKey: true }), false);
  assert.equal(f.press('A', false, { isComposing: true }), false);
  assert.equal(f.press('A', false, { repeat: true }), false);
  assert.equal(f.selected.length, 0);
});

test('keyboard grades only valid options and cannot change a submitted result', () => {
  const f = keyboardFixture();
  assert.equal(f.press('G'), false);
  assert.equal(f.press('a'), true);
  assert.equal(f.selected[0][0], 21);
  assert.equal(f.selected[0][1], 'A');
  f.context.gradeResult = { submission_id: '1' };
  assert.equal(f.press('B'), false);
  assert.equal(f.selected.length, 1);
});
