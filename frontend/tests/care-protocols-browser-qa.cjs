#!/usr/bin/env node
/** Actual treatment-flow acceptance checks. These are not treatment-efficacy or disease-accuracy measurements. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const esbuild = require('esbuild');
const { chromium } = require('playwright');
const root = path.resolve(__dirname, '../..');
const baseURL = (process.env.QA_BASE_URL || 'http://127.0.0.1:3000').replace(/\/$/, '') + '/';
const skipAudio = process.env.QA_SKIP_AUDIO === '1';
const out = process.env.QA_ARTIFACTS || path.join(root, 'frontend/test-results/care-protocols');
fs.mkdirSync(out, { recursive: true });
const report = { audioChecksSkipped: skipAudio, startedAt: new Date().toISOString(), baseURL, scope: 'Software behavior and artifact coverage, not agronomic validation', checks: [], pageErrors: [] };
const check = (name, details = {}) => { report.checks.push({ name, status: 'passed', ...details }); console.log(`PASS ${name}`); };
const labels = JSON.parse(fs.readFileSync(path.join(root, 'contracts/labels.json'), 'utf8')).labels;
const leaf = process.env.QA_LEAF || '/workspace/crop-data/plantdoc-5467f601/raw/train/Corn rust leaf/corn-rust-4.jpg';
const crop = process.env.QA_CROP || 'maize';
const mouse = process.env.QA_MOUSE || '/workspace/crop-data/nonleaf/source/n03793489_mouse.JPEG';
function loadModule(relative) {
  const built = esbuild.buildSync({ entryPoints: [path.join(root, relative)], bundle: true, write: false, platform: 'node', format: 'cjs', define: { 'import.meta.env': '{"BASE_URL":"/"}' } });
  const mod = new Module(path.join(root, 'frontend/tests/__care_qa__.cjs'), module);
  mod.paths = module.paths; mod.filename = mod.id; mod._compile(built.outputFiles[0].text, mod.filename); return mod.exports;
}
function policyChecks() {
  const api = loadModule('frontend/src/lib/careProtocols.ts');
  const advisory = loadModule('frontend/src/lib/advisory.ts');
  const model = api.validateCareProtocols(JSON.parse(fs.readFileSync(path.join(root, 'content/care_protocols.json'), 'utf8')));
  const first = advisory.validateAdvisoryModel(JSON.parse(fs.readFileSync(path.join(root, 'content/advisory_model.json'), 'utf8')));
  assert.equal(Object.keys(model.protocols).length, 17);
  const inputs = { spreadingQuickly: false, manyPlantsAffected: false, wiltingOrDying: false, fruitOrStemAffected: false, wetWeather: false, uncertainAnswers: false, leafCoverage: 'FEW_SPOTS' };
  let differingPlans = 0;
  for (const label of labels) for (const lang of ['en', 'kn', 'hi']) {
    const unknown = advisory.evaluateAdvisory(first, label.id, null, 'uncertain');
    const plan = api.buildCarePlan(model, label.id, unknown, lang);
    assert.ok(plan, `${label.id}/${lang} must be browsable without a photo or answers`);
    assert.equal(plan.stage, null, 'Unknown answers must not select mild actions');
    const copy = plan.copy;
    for (const field of ['confirm_checks', 'look_alikes', 'avoid', 'recovery_signs', 'failure_signs', 'follow_up', 'expert_questions', 'treatment_options']) assert.ok(copy[field].length, `${label.id}/${lang}/${field}`);
    for (const option of copy.treatment_options) { assert.ok(option.when); assert.ok(option.steps.length); assert.ok(option.limits); }
    if (!label.id.endsWith('_healthy')) {
      const mild = api.buildCarePlan(model, label.id, advisory.evaluateAdvisory(first, label.id, inputs, 'uncertain'), lang);
      const severe = api.buildCarePlan(model, label.id, advisory.evaluateAdvisory(first, label.id, { ...inputs, leafCoverage: 'MANY_SPOTS', wiltingOrDying: true }, 'uncertain'), lang);
      assert.ok(mild?.stage && severe?.stage);
      assert.notDeepEqual(mild.stage.actions, severe.stage.actions, `${label.id}/${lang}: severity must change actions, not just a badge`);
      differingPlans++;
    }
  }
  for (const type of ['retake', 'crop_mismatch', 'model_unavailable']) {
    assert.equal(api.buildCarePlan(model, 'tomato_early_blight', advisory.evaluateAdvisory(first, 'tomato_early_blight', inputs, type), 'en'), null);
  }
  check('actual protocol model covers17×3 and selects different mild/severe actions', { modelVersion: model.version, profileTranslations: 51, differingPlans, automaticBlockedStates: 3 });
  return model;
}
async function records(page) {
  return page.evaluate(() => new Promise((resolve, reject) => {
    const req = indexedDB.open('debuggers-crop-health', 1); req.onerror = () => reject(String(req.error));
    req.onsuccess = () => { const db = req.result; const read = db.transaction('observations').objectStore('observations').getAll();
      read.onerror = () => { db.close(); reject(String(read.error)); };
      read.onsuccess = () => { const rows = read.result.map(({ photoBlob, ...row }) => ({ ...row, photoBytes: photoBlob?.size || 0 })); db.close(); resolve(rows); }; };
  }));
}
async function back(page) { await page.locator('.top-bar').getByRole('button').first().click(); }
async function openManual(page, id) {
  await page.getByTestId(`care-condition-${id}`).click();
  await page.getByTestId('manual-care-notice').waitFor();
  assert.match(await page.getByTestId('manual-care-notice').innerText(), /not a diagnosis/);
  await page.getByTestId('treatment-plan').waitFor();
  assert.equal(await page.getByTestId('treatment-plan').getAttribute('data-condition'), id);
  assert.equal(await page.getByTestId('conditional-care').count(), 0, 'Rich treatment must not repeat the older generic care article');
  assert.equal(await page.getByTestId('advisory-summary').evaluate(node => !!(node.compareDocumentPosition(document.querySelector('[data-testid="treatment-plan"]')) & Node.DOCUMENT_POSITION_FOLLOWING)), true, 'Urgency must precede the long treatment plan');
}
async function answer(page, values, previousAnswers = null) {
  await page.getByRole('button', { name: /Check damage.*6 questions/ }).click();
  for (const [index, value] of values.entries()) {
    if (previousAnswers) assert.equal(await page.getByTestId(`concern-option-${previousAnswers[index]}`).getAttribute('aria-checked'), 'true', `Editing must preserve answer ${index + 1}`);
    await page.getByTestId(`concern-option-${value}`).click(); await page.getByTestId('concern-next').click();
  }
  await page.getByTestId('concern-summary').waitFor();
}
async function analyze(page, filename, cropId) {
  assert.ok(fs.existsSync(filename), `Real photo missing: set QA_LEAF/QA_MOUSE: ${filename}`);
  await page.goto(baseURL, { waitUntil: 'domcontentloaded' });
  await page.getByTestId('home-scan').waitFor(); await page.getByTestId(`crop-${cropId}`).click();
  await page.getByTestId('home-scan').click(); await page.getByTestId('upload-input').setInputFiles(filename);
  await page.getByTestId('analyze-photo').click(); await page.getByTestId('result-status').waitFor({ timeout: 90_000 });
  return page.getByTestId('result-status').getAttribute('data-result-type');
}
async function playback(page, filename) {
  if (skipAudio) return { skipped: true, reason: 'UI-only preparation run; narration assets not yet installed' };
  const clip = page.locator(`audio[src$="/${filename}"]`); await clip.waitFor({ state: 'attached' });
  const button = clip.locator('..').getByTestId('audio-toggle'); await button.click();
  await page.waitForFunction(suffix => { const audio = [...document.querySelectorAll('audio')].find(a => a.currentSrc.endsWith('/' + suffix)); return audio && !audio.paused && audio.currentTime > .03; }, filename, { timeout: 15_000 });
  const data = await clip.evaluate(a => ({ url: a.currentSrc, duration: a.duration })); assert.ok(data.duration > 1); await button.click(); return data;
}
async function browserChecks(model) {
  const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROMIUM_PATH || '/usr/bin/chromium', args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  try {
    const context = await browser.newContext({ viewport: { width: 390, height: 844 } }); const page = await context.newPage();
    page.on('pageerror', e => report.pageErrors.push(e.message));
    await page.goto(baseURL, { waitUntil: 'domcontentloaded' });
    report.artifacts = await page.evaluate(async () => ({ script: document.querySelector('script[type=module]')?.src, offlineCacheVersion: (await (await fetch('./offline-manifest.json')).json()).version, careReceipt: await (await fetch('./assets/content/care_protocols_receipt.json')).json() }));
    await page.getByTestId('open-care-library').click();
    assert.equal(await page.getByTestId('care-library-list').getByRole('button').count(), 17);
    for (const label of labels) {
      await openManual(page, label.id);
      assert.equal(await page.getByTestId('manual-care-heading').innerText(), label.name_en);
      assert.equal(await page.getByTestId('treatment-plan').getAttribute('data-stage'), 'UNKNOWN');
      assert.equal(await page.getByTestId('treatment-option').count(), model.protocols[label.id].translations.en.treatment_options.length);
      assert.ok((await page.getByTestId('recovery-signs').innerText()).includes(model.protocols[label.id].translations.en.recovery_signs[0]));
      assert.ok((await page.getByTestId('follow-up-plan').innerText()).includes(model.protocols[label.id].translations.en.follow_up[0].action));
      await back(page);
    }
    assert.equal((await records(page)).length, 0);
    check('all17 complete care protocols accessible without photo, diagnosis or saved scan');
    await page.getByTestId('care-library-search').fill('potato'); assert.equal(await page.getByTestId('care-library-list').getByRole('button').count(), 3);
    await page.getByTestId('care-library-search').fill(''); await openManual(page, 'tomato_early_blight');
    await answer(page, [1, 1, 1, 1, 1, 1]);
    assert.equal(await page.getByTestId('treatment-plan').getAttribute('data-stage'), 'MILD');
    const mildSteps = await page.getByTestId('stage-plan').innerText();
    await page.getByRole('button', { name: 'See guidance', exact: true }).click();
    await answer(page, [1, 3, 1, 0, 0, 1], [1, 1, 1, 1, 1, 1]);
    assert.equal(await page.getByTestId('treatment-plan').getAttribute('data-stage'), 'SEVERE');
    assert.notEqual(await page.getByTestId('stage-plan').innerText(), mildSteps);
    assert.equal((await records(page)).length, 0, 'Manual answers must not create a diagnosis');
    await page.getByRole('button', { name: 'See guidance', exact: true }).click();
    const audio = [];
    for (const lang of ['en', 'kn', 'hi']) {
      await page.getByTestId(`language-${lang}`).click();
      const plan = page.getByTestId('treatment-plan');
      if (lang === 'kn') assert.match(await plan.innerText(), /[\u0c80-\u0cff]/);
      if (lang === 'hi') assert.match(await plan.innerText(), /[\u0900-\u097f]/);
      assert.ok((await plan.innerText()).includes(model.protocols.tomato_early_blight.translations[lang].treatment_options[0].steps[0]));
      audio.push({ language: lang, treatment: await playback(page, 'treatment_tomato_early_blight.ogg'), stage: await playback(page, 'treatment_stage_severe.ogg') });
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
      await page.locator('.app-page').evaluate(node => node.scrollTo({ top: 0 }));
      await page.screenshot({ path: path.join(out, `care-overview-${lang}.png`), fullPage: true });
      await plan.evaluate(node => node.scrollIntoView({ block: 'start' }));
      await page.screenshot({ path: path.join(out, `treatment-${lang}.png`), fullPage: true });
    }
    check(skipAudio ? 'six manual answers change actual action steps and trilingual treatment text renders' : 'six manual answers change actual action steps and trilingual treatment/stage narration plays', { audio, pronunciationValidated: false });
    await page.waitForFunction(async onlyUI => navigator.serviceWorker.controller && (await Promise.all((await caches.keys()).map(async key => (await (await caches.open(key)).keys()).map(r => r.url)))).flat().some(url => url.endsWith(onlyUI ? '/care_protocols.json' : '/treatment_stage_severe.ogg')), skipAudio, { timeout: 90_000 });
    await context.setOffline(true); await page.reload({ waitUntil: 'domcontentloaded' });
    await page.getByTestId('open-care-library').click(); await page.getByTestId('care-condition-tomato_early_blight').click();
    await page.getByTestId('treatment-plan').waitFor();
    const offlineAudio = await playback(page, 'treatment_tomato_early_blight.ogg'); assert.equal(await page.evaluate(() => navigator.onLine), false);
    check(skipAudio ? 'offline reload retains the complete manual treatment library' : 'offline reload retains the complete manual library and treatment narration', { offlineAudio });
    await context.setOffline(false); await page.goto(baseURL, { waitUntil: 'domcontentloaded' }); await page.getByTestId('language-en').click();
    const type = await analyze(page, leaf, crop); assert.ok(['likely', 'healthy', 'uncertain'].includes(type));
    const originalHeading = await page.locator('.result-heading h2').innerText();
    await page.getByTestId('save-scan').click(); await page.waitForFunction(() => document.querySelector('[data-testid="save-scan"]')?.textContent.includes('Saved on this device'));
    const originalRows = await records(page); assert.equal(originalRows.length, 1); assert.ok(originalRows[0].photoBytes > 0);
    await page.getByTestId('result-care-library').click(); await openManual(page, 'potato_late_blight');
    await answer(page, [1, 3, 1, 0, 1, 0]);
    assert.deepEqual(await records(page), originalRows, 'Manual disease or answers must not relabel the saved scan');
    await page.getByRole('button', { name: 'See guidance', exact: true }).click();
    await back(page); await back(page);
    await page.getByTestId('result-status').waitFor();
    assert.equal(await page.locator('.result-heading h2').innerText(), originalHeading, 'Returning from care must preserve the live diagnosis');
    await page.goto(baseURL, { waitUntil: 'domcontentloaded' }); await page.getByTestId('nav-history').click();
    await page.getByTestId(`observation-${originalRows[0].id}`).getByRole('button').first().click();
    assert.equal(await page.locator('.result-heading h2').innerText(), originalHeading);
    check('real saved leaf diagnosis/photo remain unchanged after manual selection and severe questionnaire', { resultType: type, originalHeading, savedId: originalRows[0].id });
    const nonleaf = await analyze(page, mouse, 'tomato'); assert.equal(nonleaf, 'retake'); assert.equal(await page.getByTestId('treatment-plan').count(), 0);
    check('real mouse still returns retake without automatic disease treatment');
    assert.equal(report.pageErrors.length, 0, JSON.stringify(report.pageErrors)); await context.close();
    const failureContext = await browser.newContext({ serviceWorkers: 'block', viewport: { width: 390, height: 844 } });
    await failureContext.route('**/assets/content/care_protocols.json', route => route.fulfill({ status: 404, contentType: 'application/json', body: '{}' }));
    const failed = await failureContext.newPage(); await failed.goto(baseURL, { waitUntil: 'domcontentloaded' });
    await failed.getByTestId('open-care-library').click(); await failed.getByTestId('care-condition-tomato_early_blight').click();
    await failed.getByTestId('treatment-load-error').waitFor(); assert.equal(await failed.getByTestId('treatment-plan').count(), 0);
    await failureContext.unroute('**/assets/content/care_protocols.json');
    await failed.getByTestId('care-protocols-retry').click(); await failed.getByTestId('treatment-plan').waitFor();
    check('missing detailed care asset shows an explicit error and retry recovers the real plan'); await failureContext.close();
  } finally { await browser.close(); }
}
(async () => { try { const model = policyChecks(); if (!process.argv.includes('--policy-only')) await browserChecks(model); report.status = 'passed'; }
catch (error) { report.status = 'failed'; report.error = String(error.stack || error); process.exitCode = 1; console.error(report.error); }
finally { report.finishedAt = new Date().toISOString(); fs.writeFileSync(path.join(out, 'report.json'), JSON.stringify(report, null, 2) + '\n'); } })();
