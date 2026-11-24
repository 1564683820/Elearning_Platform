const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

test('project config points to the client source and the server cloud functions', () => {
  const root = path.resolve(__dirname, '..');
  const config = require('../project.config.json');
  assert.ok(fs.statSync(path.resolve(root, config.miniprogramRoot, 'app.json')).isFile());
  const cloudRoot = path.resolve(root, config.cloudfunctionRoot);
  assert.equal(cloudRoot, path.resolve(root, '../../server/cloudfunctions/miniprogram'));
  for (const name of ['ai', 'login', 'quiz', 'user']) {
    assert.ok(fs.statSync(path.join(cloudRoot, name, 'index.js')).isFile());
  }
});

test('shared API declares each named function only once', () => {
  const file = path.resolve(__dirname, '../miniprogram/utils/api.js');
  const source = ts.createSourceFile(file, fs.readFileSync(file, 'utf8'), ts.ScriptTarget.Latest, true);
  const seen = new Set();
  for (const node of source.statements) {
    if (!ts.isFunctionDeclaration(node) || !node.name) continue;
    assert.ok(!seen.has(node.name.text), `duplicate function: ${node.name.text}`);
    seen.add(node.name.text);
  }
});

test('page calls to imported shared API resolve to exported functions', () => {
  const root = path.resolve(__dirname, '../miniprogram');
  const context = { module: { exports: {} }, wx: { getStorageSync: () => null } };
  vm.runInNewContext(fs.readFileSync(path.join(root, 'utils/api.js'), 'utf8'), context);
  const api = context.module.exports;
  const failures = [];
  let calls = 0;

  function visitFiles(directory) {
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      const file = path.join(directory, entry.name);
      if (entry.isDirectory()) { visitFiles(file); continue; }
      if (!entry.name.endsWith('.js')) continue;
      const source = ts.createSourceFile(file, fs.readFileSync(file, 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.JS);
      const imports = new Set();
      function collect(node) {
        if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name)
            && node.initializer && ts.isCallExpression(node.initializer)
            && node.initializer.expression.getText(source) === 'require') {
          const argument = node.initializer.arguments[0];
          if (argument && ts.isStringLiteral(argument) && /\/utils\/api(?:\.js)?$/.test(argument.text)) imports.add(node.name.text);
        }
        ts.forEachChild(node, collect);
      }
      collect(source);
      function inspect(node) {
        if (ts.isCallExpression(node) && ts.isPropertyAccessExpression(node.expression)
            && ts.isIdentifier(node.expression.expression) && imports.has(node.expression.expression.text)) {
          calls++;
          const method = node.expression.name.text;
          if (typeof api[method] !== 'function') failures.push(`${path.relative(root, file)}: ${method}`);
        }
        ts.forEachChild(node, inspect);
      }
      inspect(source);
    }
  }
  visitFiles(path.join(root, 'pages'));
  assert.ok(calls > 0, 'no imported API calls were inspected');
  assert.deepEqual(failures, []);
});
