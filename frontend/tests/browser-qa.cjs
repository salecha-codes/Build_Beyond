#!/usr/bin/env node
/** Real browser/model QA. Run against the production build; never inject production outcomes. */
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const fsSync = require('node:fs');
const path = require('node:path');
const { createHash } = require('node:crypto');
const { chromium } = require('playwright');

const frontend = path.resolve(__dirname, '..');
const repository = path.resolve(frontend, '..');
const baseURL = (process.env.QA_BASE_URL || 'http://127.0.0.1:3000').replace(/\/$/, '') + '/';
const basePath = new URL(baseURL).pathname;
const artifacts = process.env.QA_ARTIFACTS || path.join(frontend, 'test-results');
const fixture = path.join(repository, 'android/app/src/androidTest/assets/leaf_input.jpg');
const result = { baseURL, startedAt: new Date().toISOString(), checks: [], console: [], pageErrors: [], networkFailures: [] };
async function until(predicate, description, timeout = 30_000) {
  const deadline = Date.now() + timeout;
  do { const value = await predicate(); if (value) return value; await new Promise(resolve => setTimeout(resolve, 100)); } while (Date.now() < deadline);
  throw new Error(`Timed out: ${description}`);
}
function check(name, details = {}) { result.checks.push({ name, status: 'passed', ...details }); console.log(`PASS ${name}`); }
async function screenshot(page, name) { await page.screenshot({ path: path.join(artifacts, `${name}.png`), fullPage: true }); }
async function noOverflow(page) {
  const dimensions = await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth }));
  assert.ok(dimensions.scrollWidth <= dimensions.width + 1, JSON.stringify(dimensions));
}
async function home(page) {
  for (let attempt = 0; attempt < 5; attempt++) {
    const navigation = page.getByTestId('nav-home');
    if (await navigation.isVisible()) { await navigation.click(); return; }
    const back = page.getByRole('button', { name: 'Back', exact: true });
    if (await back.isVisible()) await back.click();
    else throw new Error('Neither Home navigation nor an accessible Back button is available.');
  }
  throw new Error('Home navigation did not become available.');
}
async function uploadAndAnalyze(page) {
  await home(page);
  await page.getByTestId('home-scan').click();
  await page.getByTestId('upload-input').setInputFiles(fixture);
  await page.getByTestId('analyze-photo').click();
  const status = page.getByTestId('result-status');
  await status.waitFor({ state: 'visible', timeout: 120_000 });
  const resultType = await status.getAttribute('data-result-type');
  assert.ok(['healthy', 'likely', 'uncertain'].includes(resultType), `Unexpected result type: ${resultType}`);
  if (resultType === 'uncertain') {
    assert.match(await status.innerText(), /not sure|uncertain|ಖಚಿತವಿಲ್ಲ|ಅನಿಶ್ಚಿತ/i);
  } else {
    assert.match(await status.innerText(), /Model match|ಮಾದರಿಯ ಹೊಂದಾಣಿಕೆ|ಹೊಂದಾಣಿಕೆ/i);
  }
  const text = await page.locator('body').innerText();
  assert.doesNotMatch(text, /Model confidence/);
  return text;
}
async function observations(page) {
  // Wait for the app to create its schema; a read-only QA probe must not create an empty database first.
  await until(() => page.evaluate(async () => (await indexedDB.databases()).some(database => database.name === 'debuggers-crop-health')), 'app-created history schema');
  return page.evaluate(() => new Promise((resolve, reject) => {
    const request = indexedDB.open('debuggers-crop-health', 1);
    request.onerror = () => reject(new Error(String(request.error)));
    request.onsuccess = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains('observations')) { db.close(); reject(new Error('History store is missing.')); return; }
      const read = db.transaction('observations').objectStore('observations').getAll();
      read.onerror = () => { db.close(); reject(new Error(String(read.error))); };
      read.onsuccess = () => {
        const rows = read.result.map(row => ({ ...row, photoBlob: undefined, photoBytes: row.photoBlob?.size || 0, photoType: row.photoBlob?.type }));
        db.close(); resolve(rows);
      };
    };
  }));
}
async function waitForOfflineCache(page) {
  await page.waitForFunction(async () => {
    if (!('serviceWorker' in navigator) || !navigator.serviceWorker.controller) return false;
    const names = await caches.keys();
    const urls = (await Promise.all(names.map(async name => (await (await caches.open(name)).keys()).map(request => request.url)))).flat();
    return urls.some(url => /\.onnx(?:\?|$)/.test(url)) && urls.some(url => /\.wasm(?:\?|$)/.test(url)) && urls.some(url => /\.ogg(?:\?|$)/.test(url));
  }, undefined, { timeout: 120_000 });
  return page.evaluate(async () => {
    const cachesByName = {};
    for (const name of await caches.keys()) cachesByName[name] = (await (await caches.open(name)).keys()).map(request => request.url);
    return { controller: navigator.serviceWorker.controller?.scriptURL, caches: cachesByName };
  });
}
async function assertAudioDecode(page) {
  await page.waitForFunction(() => document.querySelector('audio')?.src.includes('/kn/'));
  const button = page.getByTestId('audio-toggle').first();
  await button.click();
  await page.waitForFunction(() => {
    const audio = document.querySelector('audio');
    return audio && !audio.paused && audio.readyState >= 2 && Number.isFinite(audio.duration) && audio.duration > 0 && audio.currentTime > .05;
  });
  const audio = await page.locator('audio').first().evaluate(element => ({
    url: element.currentSrc, duration: element.duration, readyState: element.readyState,
    currentTime: element.currentTime, paused: element.paused,
  }));
  assert.equal(new URL(audio.url).origin, new URL(baseURL).origin);
  await button.click();
  return audio;
}

async function productionFlow(browser) {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1 });
  const page = await context.newPage();
  page.on('pageerror', error => result.pageErrors.push(error.message));
  page.on('console', message => { if (['warning', 'error'].includes(message.type())) result.console.push({ type: message.type(), text: message.text() }); });
  page.on('requestfailed', request => result.networkFailures.push({ url: request.url(), error: request.failure()?.errorText }));
  await page.goto(baseURL, { waitUntil: 'domcontentloaded' });
  const welcomeGetStarted = page.getByTestId('welcome-get-started');
  if (await welcomeGetStarted.isVisible({ timeout: 2000 }).catch(() => false)) {
    await page.getByTestId('language-kn').click();
    assert.match(await page.locator('body').innerText(), /[\u0C80-\u0CFF]/);
    await page.getByTestId('language-en').click();
    await welcomeGetStarted.click();
    check('onboarding and language selection');
  }
  await page.getByTestId('home-scan').waitFor();
  await noOverflow(page); await screenshot(page, 'mobile-home');
  await page.getByTestId('nav-history').click();
  assert.equal((await observations(page)).length, 0, 'Fresh browser history must be truly empty.');
  await screenshot(page, 'mobile-empty-history');
  check('mobile home and genuine empty local history');

  const visibleResult = await uploadAndAnalyze(page);
  await noOverflow(page); await screenshot(page, 'mobile-real-result');
  check('production UI file input executes real local assessment', { visibleResult });

  await page.getByRole('button', { name: /Observe symptoms|Check concern/i }).click();
  for (const [question, answer] of [[0, 1], [1, 0], [2, 1]]) {
    assert.equal(await page.getByTestId('concern-next').isEnabled(), false, `Question ${question + 1} needs an explicit answer.`);
    await page.getByTestId(`concern-option-${answer}`).click();
    await page.getByTestId('concern-next').click();
  }
  await page.getByTestId('concern-summary').waitFor();
  await screenshot(page, 'mobile-symptom-summary');
  await page.getByRole('button', { name: 'See guidance', exact: true }).click();
  await page.getByTestId('language-kn').click();
  await page.waitForFunction(() => localStorage.getItem('crophealth.language') === 'kn');
  assert.match(await page.locator('body').innerText(), /[\u0C80-\u0CFF]/);
  await noOverflow(page); await screenshot(page, 'mobile-kannada-guidance');
  const audio = await assertAudioDecode(page);
  check('explicit symptom answers, Kannada guidance and bundled audio decode', { audio, audibleSpeakerOutputVerified: false });

  await page.getByRole('button', { name: 'Back', exact: true }).click();
  const shareButton = page.getByTestId('share-observation');
  assert.ok(await shareButton.isVisible(), 'Share observation button must be visible on result screen.');
  check('deliberate observation sharing control is available');
  await page.getByTestId('save-scan').click();
  const savedRows = await until(async () => { const rows = await observations(page); return rows.length === 1 ? rows : false; }, 'one committed saved observation');
  const saved = savedRows[0];
  assert.equal(saved.validated, false); assert.ok(['healthy', 'likely', 'uncertain'].includes(saved.resultType));
  assert.equal(saved.concern?.level, 'OBSERVE_AND_RECHECK');
  assert.equal(saved.concern?.reportedSymptoms.leafCoverage, 'FEW_SPOTS');
  assert.equal(saved.concern?.reportedSymptoms.uncertainAnswers, false);
  const metadata = JSON.parse(await fs.readFile(path.join(repository, 'models/assets/model/model_metadata.json'), 'utf8'));
  assert.ok(saved.photoBytes > 0 && Number.isFinite(saved.score) && saved.modelVersion === metadata.model_version);
  await home(page); await page.getByTestId('nav-history').click();
  await page.getByTestId(`observation-${saved.id}`).getByRole('button').first().click();
  assert.match(await page.getByTestId('result-status').innerText(), /not sure|uncertain|ಖಚಿತವಿಲ್ಲ|ಅನಿಶ್ಚಿತ|Model match|ಮಾದರಿಯ ಹೊಂದಾಣಿಕೆ|ಹೊಂದಾಣಿಕೆ/i);
  await page.waitForFunction(() => { const image = document.querySelector('img[alt="Selected crop leaf"]'); return image?.complete && image.naturalWidth > 0; });
  assert.ok((await page.locator('body').innerText()).includes(`${Math.round(saved.score * 100)}%`));
  await screenshot(page, 'mobile-reopened-local-observation');
  check('actual photo and model result persist and reopen from IndexedDB', { saved });

  await home(page);
  await navigatorReady(page);
  const cache = await waitForOfflineCache(page);
  await fs.writeFile(path.join(artifacts, 'offline-cache.json'), JSON.stringify(cache, null, 2));
  await screenshot(page, 'mobile-home-ready');
  await context.setOffline(true);
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.getByTestId('home-scan').waitFor();
  assert.equal(await page.evaluate(() => navigator.onLine), false);
  await page.getByTestId('nav-history').click();
  await page.getByTestId(`observation-${saved.id}`).waitFor();
  await uploadAndAnalyze(page);
  const offlineAudio = await assertAudioDecode(page);
  await screenshot(page, 'mobile-offline-real-inference');
  check('service worker reload, local history, real ONNX inference and Kannada audio work with network disabled', { cachedAssets: Object.values(cache.caches).flat().length, offlineAudio });

  await home(page); await page.getByTestId('nav-history').click();
  await page.getByTestId(`delete-${saved.id}`).click();
  await page.getByTestId('confirm-delete').click();
  await until(async () => (await observations(page)).length === 0, 'owned QA observation deletion');
  assert.equal((await observations(page)).length, 0);
  check('only the owned QA observation is deleted');
  await context.close();

  const desktop = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const desktopPage = await desktop.newPage();
  await desktopPage.goto(baseURL, { waitUntil: 'domcontentloaded' });
  const desktopGetStarted = desktopPage.getByTestId('welcome-get-started');
  if (await desktopGetStarted.isVisible({ timeout: 2000 }).catch(() => false)) {
    await desktopGetStarted.click();
  }
  await desktopPage.getByTestId('home-scan').waitFor();
  await navigatorReady(desktopPage); await waitForOfflineCache(desktopPage);
  await desktopPage.getByText('Offline ready', { exact: true }).waitFor();
  await noOverflow(desktopPage); await screenshot(desktopPage, 'desktop-home');
  check('desktop layout has no horizontal overflow');
  await desktop.close();
}
async function navigatorReady(page) {
  await page.evaluate(async () => { const registration = await navigator.serviceWorker.ready; if (!registration.active) throw new Error('No active production service worker.'); });
  // Installation may complete after first navigation; reload once to get a controller.
  if (!await page.evaluate(() => Boolean(navigator.serviceWorker.controller))) await page.reload({ waitUntil: 'domcontentloaded' });
}

async function modelHarness(browser) {
  const esbuild = require(require.resolve('esbuild', { paths: [frontend] }));
  // Reproduce Vite's ?url transformation using the already-built production assets.
  // This plugin lives only in the isolated QA bundle; it does not alter application code.
  const assetFiles = await fs.readdir(path.join(frontend, 'dist/assets'));
  const urlPlugin = {
    name: 'qa-production-url-assets',
    setup(build) {
      build.onResolve({ filter: /onnxruntime-web\/dist\/.*\?url$/ }, args => ({ path: args.path, namespace: 'qa-vite-url' }));
      build.onLoad({ filter: /.*/, namespace: 'qa-vite-url' }, args => {
        const original = path.basename(args.path.replace(/\?url$/, ''));
        const extension = path.extname(original), stem = original.slice(0, -extension.length);
        const matches = assetFiles.filter(name => name === original || (name.startsWith(`${stem}-`) && name.endsWith(extension)));
        assert.equal(matches.length, 1, `Expected exactly one built production asset for ${original}: ${matches}`);
        const url = new URL(`assets/${matches[0]}`, `${baseURL.replace(/\/$/, '')}/`).href;
        return { contents: `export default ${JSON.stringify(url)};`, loader: 'js' };
      });
    },
  };
  const built = await esbuild.build({ entryPoints: [path.join(frontend, 'src/lib/inference.ts')], bundle: true, write: false, format: 'esm', platform: 'browser', target: 'es2022', define: { 'import.meta.env': JSON.stringify({ BASE_URL: basePath, PROD: true }) }, plugins: [urlPlugin] });
  const source = built.outputFiles[0].text;
  await fs.writeFile(path.join(artifacts, 'test-only-inference.mjs'), source);
  const context = await browser.newContext({ serviceWorkers: 'block' });
  const page = await context.newPage();
  await page.route('**/__qa__/index.html', route => route.fulfill({ contentType: 'text/html', body: '<!doctype html><meta charset="utf-8"><title>Isolated real-model QA</title>' }));
  await page.route('**/__qa__/inference.mjs', route => route.fulfill({ contentType: 'application/javascript', body: source }));
  const goldenDirectory = path.join(repository, 'contracts/fixtures');
  const goldenNames = new Set(['solid_letterbox.png', 'solid_letterbox.f32', 'leaf_letterbox.png', 'leaf_letterbox.f32']);
  await page.route('**/__qa__/golden/*', async route => {
    const name = new URL(route.request().url()).pathname.split('/').pop();
    if (!goldenNames.has(name)) { await route.fulfill({ status: 404, body: 'Unknown QA fixture' }); return; }
    await route.fulfill({ contentType: name.endsWith('.png') ? 'image/png' : 'application/octet-stream', body: await fs.readFile(path.join(goldenDirectory, name)) });
  });
  await page.goto(new URL('/__qa__/index.html', baseURL).href);
  const bytes = Array.from(await fs.readFile(fixture));
  const inference = await page.evaluate(async bytes => {
    const module = await import('/__qa__/inference.mjs');
    const file = new File([new Uint8Array(bytes)], 'QA-real-leaf.jpg', { type: 'image/jpeg' });
    const output = await module.analyzeLeaf(file, 'tomato');
    const status = await module.getModelStatus();
    return { output, status };
  }, bytes);
  assert.equal(inference.status.ready, true); assert.equal(inference.output.executionProvider, 'wasm');
  assert.equal(inference.output.candidates.length, 17); assert.equal(inference.output.validated, false);
  assert.ok(['healthy', 'likely', 'uncertain'].includes(inference.output.type));
  assert.ok(inference.output.candidates.every(item => Number.isFinite(item.score) && item.score >= 0 && item.score <= 1));
  assert.ok(Math.abs(inference.output.candidates.reduce((sum, item) => sum + item.score, 0) - 1) < 1e-4);
  const metadata = JSON.parse(await fs.readFile(path.join(repository, 'models/assets/model/model_metadata.json'), 'utf8'));
  assert.equal(inference.output.modelSha256, metadata.model_sha256);
  const shapes = Object.values(inference.output.outputShapes);
  assert.ok(shapes.some(shape => Array.isArray(shape) && shape.join(',') === '1,17'));
  assert.ok(shapes.some(shape => Array.isArray(shape) && shape.join(',') === '1,960'));
  await fs.writeFile(path.join(artifacts, 'real-wasm-inference.json'), JSON.stringify(inference, null, 2));
  check('isolated browser harness executes actual WASM model with 17 finite normalized scores and expected hash/shapes', { inferenceMs: inference.output.inferenceMs, modelSha256: inference.output.modelSha256 });
  const preprocessing = await page.evaluate(async () => {
    const module = await import('/__qa__/inference.mjs');
    const result = {};
    for (const name of ['solid_letterbox', 'leaf_letterbox']) {
      const image = await (await fetch(`/__qa__/golden/${name}.png`)).blob();
      const decoded = await module.decodeLeafImage(new File([image], `${name}.png`, { type: 'image/png' }));
      const actual = module.preprocessRgb(decoded.rgb, decoded.width, decoded.height);
      const expected = new Float32Array(await (await fetch(`/__qa__/golden/${name}.f32`)).arrayBuffer());
      if (actual.length !== expected.length) throw new Error(`${name}: tensor shape differs.`);
      const difference = Float32Array.from(actual, (value, index) => Math.abs(value - expected[index]));
      if (!actual.every(Number.isFinite) || !expected.every(Number.isFinite)) throw new Error(`${name}: non-finite preprocessing value.`);
      const mean = difference.reduce((sum, value) => sum + value, 0) / difference.length;
      difference.sort();
      result[name] = { values: difference.length, maxAbsError: difference.at(-1), meanAbsError: mean, p99AbsError: difference[Math.floor(difference.length * .99)] };
    }
    return result;
  });
  for (const [name, diagnostic] of Object.entries(preprocessing)) assert.ok(diagnostic.maxAbsError <= 1e-5, `${name}: ${JSON.stringify(diagnostic)}`);
  await fs.writeFile(path.join(artifacts, 'browser-preprocessing.json'), JSON.stringify(preprocessing, null, 2));
  check('browser decoding and tensor preprocessing match both independent Python fixtures within 1e-5', { preprocessing });
  await context.close();
}

(async () => {
  await fs.mkdir(artifacts, { recursive: true });
  const manifestResponse = await fetch(new URL('offline-manifest.json', baseURL));
  assert.ok(manifestResponse.ok, 'Production offline manifest must be available.');
  const manifest = await manifestResponse.json();
  result.build = { offlineCacheVersion: manifest.version, productionAssets: manifest.files.length };
  const fixtureBytes = await fs.readFile(fixture);
  result.fixture = { path: fixture, sha256: createHash('sha256').update(fixtureBytes).digest('hex') };
  const executablePath = process.env.CHROMIUM_PATH || process.env.QA_CHROMIUM ||
    (fsSync.existsSync('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome') ? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' : undefined) ||
    (fsSync.existsSync('/usr/bin/chromium') ? '/usr/bin/chromium' : undefined);
  const browser = await chromium.launch({ executablePath, headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  try {
    await productionFlow(browser);
    await modelHarness(browser);
    assert.deepEqual(result.pageErrors, [], 'Unexpected production browser exceptions.');
    assert.deepEqual(result.console.filter(item => /Failed to load resource/.test(item.text)), [], 'Production resources must load online and offline.');
    result.status = 'passed';
  } catch (error) {
    result.status = 'failed'; result.error = error.stack || String(error); console.error(result.error); process.exitCode = 1;
    for (const [i, context] of browser.contexts().entries()) for (const [j, page] of context.pages().entries()) {
      await page.screenshot({ path: path.join(artifacts, `failure-${i}-${j}.png`), fullPage: true, timeout: 5_000 }).catch(() => undefined);
      await fs.writeFile(path.join(artifacts, `failure-${i}-${j}.html`), await page.content()).catch(() => undefined);
    }
  }
  finally { result.finishedAt = new Date().toISOString(); await fs.writeFile(path.join(artifacts, 'summary.json'), JSON.stringify(result, null, 2)); await browser.close(); }
})();
