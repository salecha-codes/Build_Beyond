#!/usr/bin/env node
/** Behavioral QA of the real advisory artifact and real browser/model flow.
 * These checks do not establish diagnosis accuracy or agronomic validity.
 * Run after npm run build. QA_LEAF/QA_CROP override the real photo and crop.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const { chromium } = require('playwright');
const esbuild = require('esbuild');

const root = path.resolve(__dirname, '../..');
const baseURL = (process.env.QA_BASE_URL || 'http://127.0.0.1:3000').replace(/\/$/, '') + '/';
const out = process.env.QA_ARTIFACTS || path.join(root, 'frontend/test-results/advisory');
fs.mkdirSync(out, { recursive: true });
const fieldLeaf = '/workspace/crop-data/plantdoc-5467f601/raw/train/Corn rust leaf/corn-rust-4.jpg';
const defaultLeaf = fs.existsSync(fieldLeaf) ? fieldLeaf : path.join(root, 'android/app/src/androidTest/assets/leaf_input.jpg');
const photo = process.env.QA_LEAF || defaultLeaf;
const crop = process.env.QA_CROP || (photo === fieldLeaf ? 'maize' : 'tomato');
const mouse = process.env.QA_MOUSE || '/workspace/crop-data/nonleaf/source/n03793489_mouse.JPEG';
const report = { startedAt: new Date().toISOString(), baseURL, checks: [], pageErrors: [], scope: 'software behavior, not agricultural validation' };
function check(name, details = {}) { report.checks.push({ name, status: 'passed', ...details }); console.log(`PASS ${name}`); }

function policyChecks() {
  const built = esbuild.buildSync({ entryPoints: [path.join(root, 'frontend/src/lib/advisory.ts')], bundle: true,
    write: false, platform: 'node', format: 'cjs', define: { 'import.meta.env': '{"BASE_URL":"/"}' } });
  const mod = new Module(path.join(root, 'frontend/tests/__advisory_qa__.cjs'), module);
  mod.paths = module.paths; mod.filename = mod.id; mod._compile(built.outputFiles[0].text, mod.filename);
  const { validateAdvisoryModel, evaluateAdvisory } = mod.exports;
  const model = validateAdvisoryModel(JSON.parse(fs.readFileSync(path.join(root, 'content/advisory_model.json'), 'utf8')));
  const fixtures = JSON.parse(fs.readFileSync(path.join(root, 'contracts/fixtures/advisory_cases.json'), 'utf8'));
  const tested = [];
  for (const item of fixtures.cases) {
    const result = evaluateAdvisory(model, item.conditionId, item.symptoms, item.resultType);
    for (const [key, expected] of Object.entries(item.expected)) {
      const actual = key === 'diseaseCareAllowed' ? !!result.profile : result[key];
      assert.equal(actual, expected, `${item.name}: ${key}`);
    }
    assert.equal(result.requiresConfirmation, true);
    tested.push({ name: item.name, severity: result.severity, urgency: result.urgency, conditionCare: !!result.profile });
  }
  assert.equal(Object.keys(model.profiles).length, 17);
  assert.equal(model.trained, false); assert.equal(model.field_validated, false);
  check('shared hand-authored advisory behavior scenarios', { cases: tested, modelVersion: model.model_version });
}

async function readRecords(page) {
  return page.evaluate(() => new Promise((resolve, reject) => {
    const open = indexedDB.open('debuggers-crop-health', 1);
    open.onerror = () => reject(String(open.error));
    open.onsuccess = () => {
      const db = open.result;
      const request = db.transaction('observations').objectStore('observations').getAll();
      request.onerror = () => { db.close(); reject(String(request.error)); };
      request.onsuccess = () => { const rows = request.result.map(({ photoBlob, ...row }) => ({ ...row, photoBytes: photoBlob?.size || 0 })); db.close(); resolve(rows); };
    };
  }));
}

async function analyze(page, filename, cropId) {
  await page.goto(baseURL, { waitUntil: 'domcontentloaded' });
  await page.getByTestId('home-scan').waitFor();
  await page.getByTestId(`crop-${cropId}`).click();
  await page.getByTestId('home-scan').click();
  await page.getByTestId('upload-input').setInputFiles(filename);
  await page.getByTestId('analyze-photo').click();
  await page.getByTestId('result-status').waitFor({ timeout: 90_000 });
  return page.getByTestId('result-status').getAttribute('data-result-type');
}

async function answer(page, options) {
  await page.getByRole('button', { name: /Check concern|Check severity|Answer 6|Answer six|observations|questions/i }).filter({ hasNot: page.locator('.advisory-panel') }).first().click();
  for (let question = 0; question < options.length; question++) {
    assert.equal(await page.getByTestId('concern-next').isEnabled(), false, `question ${question + 1} needs an explicit answer`);
    if (question === 1 || question >= 3) {
      const audio = await audioPlayback(page, 0);
      assert.match(audio.url, /advisory_question_(coverage|wilting|fruit_stem|wet_weather)\.ogg/);
    }
    await page.getByTestId(`concern-option-${options[question]}`).click();
    await page.getByTestId('concern-next').click();
  }
  await page.getByTestId('concern-summary').waitFor();
}

async function audioPlayback(page, index) {
  const button = page.getByTestId('audio-toggle').nth(index);
  await button.click();
  await page.waitForFunction((i) => {
    const audio = document.querySelectorAll('audio')[i];
    return audio && !audio.paused && audio.readyState >= 2 && audio.currentTime > .05;
  }, index, { timeout: 15_000 });
  const result = await page.locator('audio').nth(index).evaluate(audio => ({ url: audio.currentSrc,
    duration: audio.duration, currentTime: audio.currentTime, paused: audio.paused }));
  assert.match(result.url, /advisory_/); assert.ok(result.duration > 1);
  await button.click();
  return result;
}

async function exclusiveAudio(page) {
  await page.getByTestId('audio-toggle').nth(0).click();
  await page.waitForFunction(() => !document.querySelectorAll('audio')[0]?.paused);
  await page.getByTestId('audio-toggle').nth(1).click();
  await page.waitForFunction(() => {
    const clips = [...document.querySelectorAll('audio')];
    return clips[0]?.paused && clips[1] && !clips[1].paused && clips.filter(clip => !clip.paused).length === 1;
  });
  await page.getByTestId('audio-toggle').nth(1).click();
}

async function browserChecks() {
  const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROMIUM_PATH || '/usr/bin/chromium',
    args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  try {
    const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
    const page = await context.newPage();
    page.on('pageerror', e => report.pageErrors.push(e.message));
    const type = await analyze(page, photo, crop);
    report.artifacts = await page.evaluate(async () => ({
      classifier: await (await fetch('./assets/model/model_metadata.json')).json(),
      advisory: await (await fetch('./assets/content/advisory_receipt.json')).json(),
    }));
    assert.ok(['likely', 'healthy', 'uncertain'].includes(type), `Real leaf must expose a leaf-supported candidate, got ${type}. Use QA_LEAF/QA_CROP for a supported photo.`);
    await page.getByTestId('advisory-summary').waitFor();
    assert.match(await page.getByTestId('advisory-severity').innerText(), /Not enough information/);
    const conditionHeading = await page.locator('.result-heading h2').innerText();
    check('real leaf inference reaches unknown advisory until explicit answers', { photo, crop, type, conditionHeading });

    // Large reported leaf damage plus wilting is severe and urgent regardless of classifier confidence.
    await answer(page, [1, 3, 1, 0, 1, 1]);
    assert.equal(await page.getByTestId('advisory-severity').innerText(), 'Severe signs');
    assert.match(await page.getByTestId('advisory-urgency').innerText(), /Urgent/);
    await page.screenshot({ path: path.join(out, 'severe-urgent-summary.png'), fullPage: true });
    check('six explicit observations produce severe reported damage and urgent action');
    await page.getByRole('button', { name: 'Back to result', exact: true }).click();
    await page.getByTestId('save-scan').click();
    await page.waitForFunction(() => document.querySelector('[data-testid="save-scan"]')?.textContent.includes('Saved on this device'));
    const rows = await readRecords(page);
    assert.equal(rows.length, 1); const saved = rows[0];
    assert.equal(saved.concern.reportedSymptoms.leafCoverage, 'MANY_SPOTS');
    assert.equal(saved.concern.reportedSymptoms.wiltingOrDying, true);
    assert.equal(saved.concern.reportedSymptoms.fruitOrStemAffected, false);
    assert.equal(saved.concern.reportedSymptoms.wetWeather, false);
    assert.ok(saved.photoBytes > 0);
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.getByTestId('nav-history').click();
    await page.getByTestId(`observation-${saved.id}`).getByRole('button').first().click();
    assert.equal(await page.getByTestId('advisory-severity').innerText(), 'Severe signs');
    assert.match(await page.getByTestId('advisory-urgency').innerText(), /Urgent/);
    check('real saved photo and all advisory answers survive reload/history reopen', { saved });

    // Update answers on that existing observation, without replacing its image or duplicating the scan.
    await answer(page, [1, 1, 1, 1, 1, 1]);
    assert.equal(await page.getByTestId('advisory-severity').innerText(), 'Mild');
    await page.getByTestId('save-care-plan').click();
    await page.getByTestId('save-care-plan').getByText('Care answers saved').waitFor();
    const updatedRows = await readRecords(page);
    assert.equal(updatedRows.length, 1);
    assert.equal(updatedRows[0].id, saved.id);
    assert.equal(updatedRows[0].concern.reportedSymptoms.leafCoverage, 'FEW_SPOTS');
    assert.equal(updatedRows[0].concern.reportedSymptoms.wiltingOrDying, false);
    assert.equal(updatedRows[0].photoBytes, saved.photoBytes);
    await page.getByRole('button', { name: 'Back to result', exact: true }).click();
    check('mild reassessment updates the existing saved care answers without duplicate records or photo loss');

    await page.getByRole('button', { name: 'See guidance', exact: true }).click();
    await page.getByTestId('conditional-care').waitFor();
    assert.match(await page.getByTestId('conditional-care').innerText(), /confirmed/i);
    const audio = [];
    for (const language of ['en', 'kn', 'hi']) {
      await page.getByTestId(`language-${language}`).click();
      const text = await page.getByTestId('conditional-care').innerText();
      if (language === 'kn') assert.match(text, /[\u0c80-\u0cff]/);
      if (language === 'hi') assert.match(text, /[\u0900-\u097f]/);
      assert.ok(await page.locator('.advisory-panel .guidance-card').count() >= 5, 'Care must include curability, immediate actions, management, prevention and escalation.');
      const dimensions = await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth }));
      assert.ok(dimensions.scrollWidth <= dimensions.width + 1, `${language} mobile layout overflow`);
      if (language === 'en') {
        await exclusiveAudio(page);
        check('starting care narration pauses urgency narration so voices cannot overlap');
      }
      audio.push({ language, urgency: await audioPlayback(page, 0), care: await audioPlayback(page, 1) });
      await page.screenshot({ path: path.join(out, `care-${language}.png`), fullPage: true });
    }
    check('trilingual conditional care and new urgency/care audio decode and play', { audio, nativePronunciationValidated: false });

    await page.waitForFunction(async () => navigator.serviceWorker.controller &&
      (await Promise.all((await caches.keys()).map(async key => (await (await caches.open(key)).keys()).map(request => request.url)))).flat().some(url => url.endsWith('advisory_hi') || url.endsWith('audio/hi/advisory_urgent.ogg')), undefined, { timeout: 90_000 });
    await context.setOffline(true);
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.getByTestId('nav-history').click();
    await page.getByTestId(`observation-${saved.id}`).getByRole('button').first().click();
    assert.equal(await page.getByTestId('advisory-severity').innerText(), 'हल्का');
    await page.getByRole('button', { name: /ಸಲಹೆ ನೋಡಿ|मार्गदर्शन देखें|See guidance/ }).click();
    await page.getByTestId('conditional-care').waitFor();
    const offlineAudio = await audioPlayback(page, 1);
    assert.equal(await page.evaluate(() => navigator.onLine), false);
    check('offline reload restores advisory answers, conditional care and new audio', { offlineAudio });
    await context.setOffline(false);
    await page.goto(baseURL, { waitUntil: 'domcontentloaded' });
    await page.getByTestId('language-en').click();
    if (!fs.existsSync(mouse)) throw new Error('Provide a real nonleaf fixture with QA_MOUSE; mouse rejection was not tested.');
    const nonleafType = await analyze(page, mouse, 'tomato');
    assert.equal(nonleafType, 'retake');
    assert.equal(await page.getByTestId('conditional-care').count(), 0);
    assert.equal(await page.locator('.prediction').count(), 0);
    check('real mouse photo is rejected with no disease prediction or condition care', { mouse });
    assert.equal(report.pageErrors.length, 0, JSON.stringify(report.pageErrors));
    await context.close();
  } finally { await browser.close(); }
}

(async () => {
  try {
    policyChecks();
    if (!process.argv.includes('--policy-only')) await browserChecks();
    report.status = 'passed';
  } catch (error) { report.status = 'failed'; report.error = String(error.stack || error); process.exitCode = 1; console.error(report.error); }
  finally { report.finishedAt = new Date().toISOString(); fs.writeFileSync(path.join(out, 'report.json'), JSON.stringify(report, null, 2) + '\n'); }
})();
