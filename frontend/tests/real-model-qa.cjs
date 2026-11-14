#!/usr/bin/env node
/**
 * Focused actual-model smoke. PREPARED ONLY until parent explicitly authorizes execution.
 * QA_TUNE_MANIFEST must identify three TUNE-only examples selected after policy freeze:
 * {scope:'source_tune_only',protocol_manifest:'/.../tune.jsonl',model_sha256:'...',
 *  samples:[{crop_id:'tomato',local_path:'/...',expected_condition_id:'...'}, ...]}
 * No CAL/final-test image selection or model-policy modification occurs here.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const fsSync = require('node:fs');
const path = require('node:path');
const { createHash } = require('node:crypto');
const { chromium } = require('playwright');
const esbuild = require('esbuild');
const root = path.resolve(__dirname, '../..');
const frontend = path.join(root, 'frontend');
const baseURL = (process.env.QA_BASE_URL || 'http://127.0.0.1:3000').replace(/\/$/, '') + '/';
const basePath = new URL(baseURL).pathname;
const artifacts = process.env.QA_ARTIFACTS || path.join(frontend, 'test-results/real-model');
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const report = { status: 'running', startedAt: new Date().toISOString(), checks: [], observations: [], pageErrors: [] };
function check(name, details = {}) { report.checks.push({ name, ...details }); console.log(`PASS ${name}`); }
async function until(predicate, label, timeout = 90_000) {
  const deadline = Date.now() + timeout;
  do { const value = await predicate(); if (value) return value; await new Promise(resolve => setTimeout(resolve, 100)); } while (Date.now() < deadline);
  throw new Error(`Timed out: ${label}`);
}
async function readTuneExamples() {
  assert.ok(process.env.QA_TUNE_MANIFEST, 'Parent must provide QA_TUNE_MANIFEST after the final bundle and TUNE gates are frozen.');
  const selected = JSON.parse(await fs.readFile(process.env.QA_TUNE_MANIFEST, 'utf8'));
  assert.equal(selected.scope, 'source_tune_only');
  assert.ok(typeof selected.protocol_manifest === 'string' && /(?:^|[/_])tune\.jsonl$/i.test(selected.protocol_manifest));
  const protocolBytes = await fs.readFile(selected.protocol_manifest);
  const protocolRows = protocolBytes.toString('utf8').split(/\r?\n/).filter(Boolean).map(line => JSON.parse(line));
  const protocol = new Map(protocolRows.map(row => [path.resolve(row.local_path), row]));
  assert.equal(selected.samples.length, 3, 'Use one frozen-policy accepted TUNE example per crop.');
  assert.deepEqual([...new Set(selected.samples.map(row => row.crop_id))].sort(), ['maize','potato','tomato']);
  for (const sample of selected.samples) {
    const local = path.resolve(sample.local_path), original = protocol.get(local);
    assert.ok(original, `Input must belong to the explicit TUNE protocol: ${local}`);
    assert.equal(original.crop_id, sample.crop_id);
    const bytes = await fs.readFile(local);
    if (original.sha256) assert.equal(sha(bytes), original.sha256);
    sample.local_path = local; sample.sha256 = sha(bytes); sample.protocol_label_id = original.label_id;
  }
  report.examples = selected.samples;
  report.protocol = { file: selected.protocol_manifest, sha256: sha(protocolBytes), scope: 'TUNE runtime examples; not final-test accuracy evidence' };
  return selected;
}
async function buildRealHarness() {
  const files = await fs.readdir(path.join(frontend, 'dist/assets'));
  const built = await esbuild.build({
    entryPoints: [path.join(frontend, 'src/lib/inference.ts')], bundle: true, write: false,
    format: 'esm', platform: 'browser', target: 'es2022',
    define: { 'import.meta.env': JSON.stringify({ BASE_URL: basePath, PROD: true }) },
    plugins: [{ name: 'qa-built-production-runtime-urls', setup(build) {
      build.onResolve({ filter: /onnxruntime-web\/dist\/.*\?url$/ }, args => ({ path: args.path, namespace: 'qa-url' }));
      build.onLoad({ filter: /.*/, namespace: 'qa-url' }, args => {
        const original = path.basename(args.path.replace(/\?url$/, ''));
        const extension = path.extname(original), stem = original.slice(0, -extension.length);
        const matching = files.filter(file => file === original || (file.startsWith(`${stem}-`) && file.endsWith(extension)));
        assert.equal(matching.length, 1, `Expected one built real runtime asset for ${original}.`);
        return { contents: `export default ${JSON.stringify(new URL(`assets/${matching[0]}`, baseURL).href)};`, loader: 'js' };
      });
    }}],
  });
  return built.outputFiles[0].text;
}
async function realApiChecks(browser, selected, metadata) {
  const context = await browser.newContext({ serviceWorkers: 'block' });
  const page = await context.newPage();
  const source = await buildRealHarness();
  await page.route('**/__qa_real__/index.html', route => route.fulfill({ contentType: 'text/html', body: '<!doctype html><meta charset="utf-8"><link rel="icon" href="data:,"><title>Actual model runtime smoke</title>' }));
  await page.route('**/__qa_real__/engine.mjs', route => route.fulfill({ contentType: 'application/javascript', body: source }));
  await page.goto(new URL('/__qa_real__/index.html', baseURL).href);
  const outputs = [];
  for (const sample of selected.samples) {
    const bytes = Array.from(await fs.readFile(sample.local_path));
    const actual = await page.evaluate(async ({ bytes, crop }) => {
      const engine = await import('/__qa_real__/engine.mjs');
      const output = await engine.analyzeLeaf(new File([new Uint8Array(bytes)], 'real-TUNE-leaf.jpg', { type: 'image/jpeg' }), crop);
      return { status: await engine.getModelStatus(), output };
    }, { bytes, crop: sample.crop_id });
    assert.equal(actual.status.ready, true); assert.equal(actual.status.validated, false);
    assert.equal(actual.status.sourceEvaluated, true); assert.equal(actual.output.validated, false);
    assert.equal(actual.output.sourceEvaluated, true); assert.equal(actual.output.allowConditionSpecificAdvice, false);
    assert.equal(actual.output.modelSha256, metadata.model_sha256); assert.equal(actual.output.executionProvider, 'wasm');
    assert.ok(['likely','healthy'].includes(actual.output.type), `${sample.crop_id}: ${JSON.stringify(actual.output.reasons)}`);
    assert.equal(actual.output.candidates.length, 17);
    assert.ok(actual.output.candidates.every(row => Number.isFinite(row.score) && row.score >= 0 && row.score <= 1));
    assert.ok(Math.abs(actual.output.candidates.reduce((sum,row) => sum+row.score,0)-1)<1e-6);
    assert.deepEqual(actual.output.outputShapes, [[1,17],[1,960]]);
    assert.equal(actual.output.candidates[0].cropId, sample.crop_id);
    if (sample.expected_condition_id) assert.equal(actual.output.candidates[0].id, sample.expected_condition_id);
    assert.ok(Number.isFinite(actual.output.embeddingDistance));
    outputs.push({ sample, ...actual });
  }
  check('actual ORT WASM accepts one qualified TUNE example per crop while field validation/advisory permission remain false', { models: outputs.map(row => ({ crop:row.sample.crop_id, type:row.output.type, condition:row.output.candidates[0].id, score:row.output.candidates[0].score, inferenceMs:row.output.inferenceMs })) });
  const synthetic = [];
  for (const kind of ['noise','checker']) {
    const observed = await page.evaluate(async kind => {
      const engine = await import('/__qa_real__/engine.mjs');
      const canvas = document.createElement('canvas'); canvas.width=256; canvas.height=256;
      const context = canvas.getContext('2d'), image = context.createImageData(256,256);
      const seed = crypto.getRandomValues(new Uint32Array(1))[0]; let state=seed || 1;
      const next = () => {state^=state<<13;state^=state>>>17;state^=state<<5;return state>>>0;};
      for(let y=0;y<256;y++)for(let x=0;x<256;x++){
        const offset=(y*256+x)*4;
        if(kind==='noise')for(let c=0;c<3;c++)image.data[offset+c]=next()&255;
        else {const color=(Math.floor(x/8)+Math.floor(y/8))%2?[24,40,200]:[220,180,30];for(let c=0;c<3;c++)image.data[offset+c]=color[c];}
        image.data[offset+3]=255;
      }
      context.putImageData(image,0,0);
      const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));
      const output=await engine.analyzeLeaf(new File([blob],`fresh-nonleaf-${kind}.png`,{type:'image/png'}),'tomato');
      return {kind,seed,bytes:Array.from(new Uint8Array(await blob.arrayBuffer())),output};
    }, kind);
    const bytes = Buffer.from(observed.bytes); delete observed.bytes;
    observed.file = path.join(artifacts, `fresh-nonleaf-${kind}.png`); observed.sha256 = sha(bytes);
    await fs.writeFile(observed.file, bytes); synthetic.push(observed);
    if (observed.output.type === 'uncertain') break;
  }
  report.syntheticObservations = synthetic;
  const uncertain = synthetic.find(row => row.output.type === 'uncertain');
  assert.ok(uncertain, 'No uncertain synthetic nonleaf was observed; report these outcomes instead of claiming certified OOD rejection.');
  check('a fresh synthetic nonleaf produced an observed uncertain result', { kind:uncertain.kind, reasons:uncertain.output.reasons, limitation:'A small runtime smoke is not an OOD certification.' });
  await fs.writeFile(path.join(artifacts,'real-api-outputs.json'),JSON.stringify(outputs,null,2));
  await context.close();
  return { outputs, uncertain };
}
async function home(page) {
  for(let i=0;i<5;i++){
    const tab=page.getByTestId('nav-home');if(await tab.isVisible()){await tab.click();return;}
    const back=page.locator('.top-bar > button.icon-button, .camera-top > button.icon-button').first();
    if(await back.isVisible())await back.click();else throw new Error('No usable back/Home control.');
  }
  throw new Error('Could not return Home.');
}
async function upload(page, crop, input) {
  await home(page);await page.getByTestId(`crop-${crop}`).click();await page.getByTestId('home-scan').click();
  await page.getByTestId('upload-input').setInputFiles(input);await page.getByTestId('analyze-photo').click();
  await page.getByTestId('result-status').waitFor({state:'visible',timeout:120_000});
}
async function rows(page) {
  return page.evaluate(()=>new Promise((resolve,reject)=>{
    const opening=indexedDB.open('debuggers-crop-health',1);opening.onerror=()=>reject(opening.error);
    opening.onsuccess=()=>{const db=opening.result;const request=db.transaction('observations').objectStore('observations').getAll();
      request.onerror=()=>{db.close();reject(request.error)};request.onsuccess=()=>{const result=request.result.map(row=>({...row,photoBlob:undefined,photoBytes:row.photoBlob?.size||0}));db.close();resolve(result)};};
  }));
}
async function realUiChecks(browser, api, metadata, catalog) {
  const context=await browser.newContext({viewport:{width:390,height:844},deviceScaleFactor:1});
  const page=await context.newPage();page.on('pageerror',error=>report.pageErrors.push(error.message));
  await page.goto(baseURL,{waitUntil:'domcontentloaded'});await page.getByTestId('home-scan').waitFor();
  let saved;
  for(const actual of api.outputs){
    await upload(page,actual.sample.crop_id,actual.sample.local_path);
    assert.equal(await page.getByTestId('result-status').getAttribute('data-result-type'),actual.output.type);
    assert.equal(await page.locator('.result-heading h2').innerText(),actual.output.candidates[0].nameEn);
    const status=await page.getByTestId('result-status').innerText();assert.match(status,/Model match/);
    assert.doesNotMatch(status,/This prototype model has not been validated|Not sure about this one/);
    await page.screenshot({path:path.join(artifacts,`accepted-${actual.sample.crop_id}.png`)});
    if(!saved){await page.getByTestId('save-scan').click();saved=(await until(async()=>{const found=await rows(page);return found.length===1?found:false;},'one committed accepted QA observation'))[0];
      assert.equal(saved.validated,false);assert.ok(['likely','healthy'].includes(saved.resultType));assert.equal(saved.modelVersion,metadata.model_version);assert.ok(saved.photoBytes>0);}
  }
  check('production UI shows actual named accepted conditions for all three crops without the obsolete all-uncertain banner');
  await upload(page,'tomato',api.uncertain.file);
  assert.equal(await page.getByTestId('result-status').getAttribute('data-result-type'),'uncertain');
  await page.screenshot({path:path.join(artifacts,'synthetic-uncertain-ui.png')});
  await home(page);await page.getByTestId('language-hi').click();
  await until(()=>page.evaluate(()=>document.documentElement.lang==='hi'&&localStorage.getItem('crophealth.language')==='hi'),'Hindi language preference');
  await page.reload({waitUntil:'domcontentloaded'});await page.getByTestId('nav-history').click();
  await page.getByTestId(`observation-${saved.id}`).getByRole('button').first().click();
  assert.equal(await page.getByTestId('result-status').getAttribute('data-result-type'),saved.resultType);
  assert.equal(await page.locator('.result-heading h2').innerText(),catalog.conditions[saved.conditionId].translations.hi.name);
  assert.match(await page.getByTestId('result-status').innerText(),/[\u0900-\u097f]/);
  assert.equal((await rows(page))[0].validated,false);
  await page.screenshot({path:path.join(artifacts,'accepted-history-hindi.png')});
  check('accepted observation/photo survives reload and restores its named condition in Hindi with field validation false',{saved});
  await home(page);await page.getByTestId('nav-history').click();await page.getByTestId(`delete-${saved.id}`).click();await page.getByTestId('confirm-delete').click();
  await until(async()=>(await rows(page)).length===0,'owned QA record deletion');
  assert.deepEqual(report.pageErrors,[]);await context.close();
}
(async()=>{
  await fs.mkdir(artifacts,{recursive:true});
  const selected=await readTuneExamples();
  const metadata=await(await fetch(new URL('assets/model/model_metadata.json',baseURL))).json();
  assert.equal(metadata.diagnosis_validated,false);assert.equal(metadata.source_acceptance_qualified,true);
  if(selected.model_sha256)assert.equal(selected.model_sha256,metadata.model_sha256);
  const catalog=await(await fetch(new URL('assets/content/catalog.json',baseURL))).json();
  const manifest=await(await fetch(new URL('offline-manifest.json',baseURL))).json();
  report.artifact={modelSha256:metadata.model_sha256,modelVersion:metadata.model_version,offlineCacheVersion:manifest.version};
  const executablePath=process.env.CHROMIUM_PATH||(fsSync.existsSync('/usr/bin/chromium')?'/usr/bin/chromium':undefined);
  const browser=await chromium.launch({executablePath,headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});
  try{const api=await realApiChecks(browser,selected,metadata);await realUiChecks(browser,api,metadata,catalog);report.status='passed';}
  catch(error){report.status='failed';report.error=error.stack||String(error);console.error(report.error);process.exitCode=1;
    for(const[i,context]of browser.contexts().entries())for(const[j,page]of context.pages().entries())await page.screenshot({path:path.join(artifacts,`failure-${i}-${j}.png`)}).catch(()=>undefined);}
  finally{report.finishedAt=new Date().toISOString();await fs.writeFile(path.join(artifacts,'summary.json'),JSON.stringify(report,null,2));await browser.close();}
})().catch(error=>{console.error(error.stack||String(error));process.exitCode=1;});
