'use strict';
// Validate the review artifact only. This does not exercise the product.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const { createRequire } = require('node:module');
const root = path.resolve(__dirname, '..');
const frontendRequire = createRequire(path.join(root, 'frontend', 'package.json'));
const { JSDOM, VirtualConsole } = frontendRequire('jsdom');
const htmlPath = path.join(__dirname, 'experience-architecture-review.html');
const html = fs.readFileSync(htmlPath, 'utf8');
const checks = [];
const errors = [];
const vc = new VirtualConsole();
vc.on('jsdomError', error => errors.push(error.message));
let externalCalls = 0;
const dom = new JSDOM(html, {
  runScripts: 'dangerously',
  url: 'https://artifact.invalid/review',
  virtualConsole: vc,
  beforeParse(window) {
    window.fetch = () => { externalCalls++; throw new Error('External request blocked'); };
    window.XMLHttpRequest = class { constructor() { externalCalls++; throw new Error('XHR blocked'); } };
  },
});
const document = dom.window.document;
const text = () => document.getElementById('proto-content').textContent;
const click = selector => {
  const el = document.querySelector(selector);
  assert.ok(el, `Missing control: ${selector}`);
  el.click();
};
function check(name, test) {
  test();
  checks.push({ name, passed: true });
}
check('Source identity and evidence boundary', () => {
  assert.match(html, /03af5c3/);
  assert.match(html, /未进行用户访谈/);
  assert.match(html, /示例数据/);
  assert.match(html, /未实施/);
});
check('Ten issue records and ten evidence groups', () => {
  assert.equal(document.querySelectorAll('#diagnosis details').length, 10);
  assert.equal(document.querySelectorAll('.source-item').length, 10);
});
check('All cited repository files exist', () => {
  for (const el of document.querySelectorAll('.source-item code')) {
    const relative = el.textContent.split(':')[0];
    assert.ok(fs.existsSync(path.join(root, relative)), `Missing source: ${relative}`);
  }
});
check('Section links and unique initial IDs', () => {
  const ids = [...document.querySelectorAll('[id]')].map(el => el.id);
  assert.equal(new Set(ids).size, ids.length);
  assert.equal(document.querySelectorAll('.toc a').length, 10);
  for (const a of document.querySelectorAll('a[href^="#"]')) {
    assert.ok(document.getElementById(a.hash.slice(1)), `Missing anchor: ${a.hash}`);
  }
});
check('Six journeys support selected and hidden state', () => {
  const tabs = [...document.querySelectorAll('[data-journey]')];
  assert.equal(tabs.length, 6);
  for (const tab of tabs) {
    tab.click();
    assert.equal(tab.getAttribute('aria-selected'), 'true');
    assert.equal(document.getElementById(tab.getAttribute('aria-controls')).hidden, false);
    assert.equal([...document.querySelectorAll('[role="tabpanel"]')].filter(p => !p.hidden).length, 1);
  }
});
check('Journey arrow keys and Home/End move focus', () => {
  const tabs = [...document.querySelectorAll('[data-journey]')];
  tabs[0].click();
  tabs[0].dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
  assert.equal(document.activeElement, tabs[1]);
  assert.equal(tabs[1].getAttribute('aria-selected'), 'true');
  tabs[1].dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'End', bubbles: true }));
  assert.equal(document.activeElement, tabs[5]);
  tabs[5].dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'Home', bubbles: true }));
  assert.equal(document.activeElement, tabs[0]);
});
check('Start -> result -> preview -> original conversation', () => {
  click('[data-screen="home"]');
  click('[data-action="start"]');
  assert.match(text(), /同一个任务现场/);
  click('[data-action="make-result"]');
  assert.match(text(), /行动清单/);
  click('[data-action="results"]');
  click('[data-action="preview"]');
  assert.match(text(), /负责人待填写/);
  click('[data-action="resume"]');
  assert.match(text(), /同一个任务现场/);
  click('[data-action="continue"]');
  assert.equal(document.activeElement.id, 'demo-followup');
});
check('Attachment failure blocks result but not draft editing', () => {
  const draft = document.getElementById('demo-followup');
  draft.value = '保留我的未发送草稿';
  draft.dispatchEvent(new dom.window.Event('input', { bubbles: true }));
  click('[data-action="file-error"]');
  assert.equal(document.getElementById('demo-followup').disabled, false);
  assert.equal(document.getElementById('demo-followup').value, '保留我的未发送草稿');
  click('[data-action="make-result"]');
  assert.match(document.querySelector('#proto-content [role="alert"]').textContent, /先选择/);
  click('[data-action="exclude"]');
  assert.match(text(), /本轮上下文：无附件/);
  click('[data-action="make-result"]');
  assert.match(text(), /行动清单/);
});
check('Starting a new task clears prior result, attachment and draft state', () => {
  click('[data-screen="home"]');
  document.getElementById('demo-goal').value = '测试目标 <不作为 HTML 执行>';
  click('[data-action="start"]');
  assert.match(text(), /测试目标 <不作为 HTML 执行>/);
  assert.equal(document.getElementById('demo-followup').value, '');
  assert.equal(document.querySelector('[data-action="results"]'), null);
  assert.match(text(), /本轮上下文：无附件/);
});
check('Personal capability activation is distinct from starting a task', () => {
  click('[data-screen="capability"]');
  assert.match(text(), /尚未为我启用/);
  click('[data-action="enable-skill"]');
  assert.match(text(), /已模拟为我启用/);
  click('[data-action="start"]');
  assert.match(text(), /同一个任务现场/);
});
check('Admin check -> apply -> user verification remains explicit', () => {
  click('[data-screen="admin"]');
  assert.match(text(), /尚未检查/);
  assert.equal(document.querySelector('[data-action="confirm-enable"]'), null);
  click('[data-action="check"]');
  assert.match(text(), /待确认启用/);
  click('[data-action="confirm-enable"]');
  assert.match(text(), /待用户验收/);
  click('[data-action="verify"]');
  assert.match(text(), /已记录示例验收/);
  click('[data-action="reset-admin"]');
  assert.match(text(), /尚未检查/);
});
check('Every preview navigation renders with a simulation notice', () => {
  for (const b of document.querySelectorAll('[data-screen]')) {
    b.click();
    assert.match(text(), /不连接产品/);
    assert.equal(document.querySelectorAll('.proto-nav [aria-current="page"]').length, 1);
  }
});
check('No external assets, runtime calls or script errors', () => {
  assert.equal(document.querySelectorAll('script[src],link[rel="stylesheet"],iframe').length, 0);
  assert.equal(externalCalls, 0);
  assert.deepEqual(errors, []);
  assert.ok(!html.includes('http://') && !html.includes('https://'));
});
click('[data-screen="home"]');
const report = {
  artifact: path.basename(htmlPath),
  sha256: crypto.createHash('sha256').update(html).digest('hex'),
  bytes: Buffer.byteLength(html),
  validation: 'Static structure and jsdom interaction checks only',
  productRuntimeTested: false,
  browserLayoutTested: false,
  realModelCalled: false,
  checksPassed: checks.length,
  checks,
};
fs.writeFileSync(path.join(__dirname, 'experience-architecture-validation.json'), JSON.stringify(report, null, 2) + '\n', 'utf8');
console.log(JSON.stringify(report, null, 2));
dom.window.close();
