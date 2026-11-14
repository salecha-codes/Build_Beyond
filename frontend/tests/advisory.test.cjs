/** Functional behavior fixtures for the expert model, not disease/severity accuracy validation. */
const { before, test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const esbuild = require('esbuild');
const root = path.resolve(__dirname, '../..');
const fixtures = JSON.parse(fs.readFileSync(path.join(root, 'contracts/fixtures/advisory_cases.json'))).cases;
let api, model;
before(async () => {
  const built = await esbuild.build({entryPoints:[path.join(root,'frontend/src/lib/advisory.ts')],bundle:true,write:false,format:'cjs',platform:'node',target:'es2022',define:{'import.meta.env':JSON.stringify({BASE_URL:'/'})}});
  const filename = path.join(__dirname,'in-memory-advisory.cjs');
  const loaded = new Module(filename, module);
  loaded._compile(built.outputFiles[0].text, filename);
  api = loaded.exports;
  model = api.validateAdvisoryModel(JSON.parse(fs.readFileSync(path.join(root,'content/advisory_model.json'))));
});
for (const fixture of fixtures) test(`advisory contract: ${fixture.name}`, () => {
  const result = api.evaluateAdvisory(model, fixture.conditionId, fixture.symptoms, fixture.resultType);
  assert.equal(result.severity, fixture.expected.severity);
  if (fixture.expected.urgency) assert.equal(result.urgency, fixture.expected.urgency);
  if (fixture.expected.diseaseCareAllowed !== undefined) assert.equal(!!result.profile, fixture.expected.diseaseCareAllowed);
  assert.equal(result.requiresConfirmation, true);
  assert.equal(result.conditionalCare, true);
});
test('healthy-looking prediction cannot suppress visible symptoms', () => {
  const result = api.evaluateAdvisory(model,'tomato_healthy',{leafCoverage:'FEW_SPOTS'},'healthy');
  assert.equal(result.profile,null);
  assert.equal(result.urgency,'SOON');
  assert.ok(result.reasonCodes.includes('healthy_conflict'));
});
test('classifier confidence is not a severity input', () => {
  const observations = {leafCoverage:'FEW_SPOTS',modelScore:.99};
  const low = api.evaluateAdvisory(model,'tomato_early_blight',{...observations,modelScore:.1},'uncertain');
  const high = api.evaluateAdvisory(model,'tomato_early_blight',observations,'likely');
  assert.equal(low.severity,high.severity);
  assert.equal(low.urgency,high.urgency);
  assert.equal(low.severity,'MILD');
});
test('all17 profiles preserve three-language conditional care and explicit model status', () => {
  assert.equal(Object.keys(model.profiles).length,17);
  assert.equal(model.trained,false);
  assert.equal(model.field_validated,false);
  for (const profile of Object.values(model.profiles)) {
    for (const language of ['en','kn','hi']) {
      assert.ok(profile.translations[language].curability.length > 15);
      assert.ok(profile.translations[language].do_now.length >= 2);
    }
  }
});
test('invalid or partially missing care model fails closed', () => {
  const incomplete = structuredClone(model);
  delete incomplete.profiles.tomato_mosaic_virus.translations.kn;
  assert.throws(()=>api.validateAdvisoryModel(incomplete),/Incomplete care profile/);
  assert.throws(()=>api.validateAdvisoryModel({...model,field_validated:true}),/incompatible/);
});
test('no answers never defaults to mild damage or routine reassurance', () => {
  const result = api.evaluateAdvisory(model,'maize_common_rust',null,'uncertain');
  assert.equal(result.severity,'UNKNOWN');
  assert.equal(result.urgency,'SOON');
  assert.ok(result.reasonCodes.includes('awaiting_answers'));
});

test('legacy three-question answers do not imply newer questions were answered no', () => {
  const legacy = {leafCoverage:'FEW_SPOTS',spreadingQuickly:false,manyPlantsAffected:false,wiltingOrDying:false,uncertainAnswers:false};
  const result = api.evaluateAdvisory(model,'tomato_early_blight',legacy,'likely');
  assert.equal(result.severity,'MILD');
  assert.equal(result.urgency,'SOON');
  assert.ok(result.reasonCodes.includes('incomplete_answers'));
  assert.equal(result.observations.fruitOrStemAffected,undefined);
  assert.equal(result.observations.wetWeather,undefined);
});
