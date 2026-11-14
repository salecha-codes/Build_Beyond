/** Functional treatment-plan behavior tests; not treatment efficacy validation. */
const { before, test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const esbuild = require('esbuild');
const root = path.resolve(__dirname, '../..');
let protocolsApi, advisoryApi, model, advisory;
before(async () => {
  async function load(name) {
    const built = await esbuild.build({ entryPoints: [path.join(root, `frontend/src/lib/${name}.ts`)], bundle: true, write: false, format: 'cjs', platform: 'node', target: 'es2022', define: { 'import.meta.env': '{"BASE_URL":"/"}' } });
    const filename = path.join(__dirname, `in-memory-${name}.cjs`);
    const compiled = new Module(filename, module);
    compiled._compile(built.outputFiles[0].text, filename);
    return compiled.exports;
  }
  protocolsApi = await load('careProtocols');
  advisoryApi = await load('advisory');
  model = protocolsApi.validateCareProtocols(JSON.parse(fs.readFileSync(path.join(root, 'content/care_protocols.json'))));
  advisory = advisoryApi.validateAdvisoryModel(JSON.parse(fs.readFileSync(path.join(root, 'content/advisory_model.json'))));
});
const symptoms = coverage => ({ leafCoverage: coverage, spreadingQuickly: false, manyPlantsAffected: false, wiltingOrDying: false, uncertainAnswers: false, fruitOrStemAffected: false, wetWeather: false });
test('all 17 categories expose complete treatment and recovery in all 3 languages', () => {
  assert.equal(Object.keys(model.protocols).length, 17);
  for (const [id, profile] of Object.entries(model.protocols)) {
    for (const language of ['en', 'kn', 'hi']) {
      const status = advisoryApi.evaluateAdvisory(advisory, id, null, 'uncertain');
      const plan = protocolsApi.buildCarePlan(model, id, status, language);
      assert.ok(plan, `${id}/${language}`);
      assert.ok(plan.copy.treatment_options.length > 0);
      assert.ok(plan.copy.follow_up.length > 0);
      assert.ok(plan.copy.recovery_signs.length > 0);
      assert.ok(plan.copy.failure_signs.length > 0);
      assert.equal(plan.copy, profile.translations[language]);
      assert.equal(plan.stage, null);
    }
  }
});
test('actual treatment steps change from mild to severe for every category', () => {
  for (const id of Object.keys(model.protocols)) {
    const mild = protocolsApi.buildCarePlan(model,id,advisoryApi.evaluateAdvisory(advisory,id,symptoms('FEW_SPOTS'),'uncertain'),'en');
    const severe = protocolsApi.buildCarePlan(model,id,advisoryApi.evaluateAdvisory(advisory,id,symptoms('MANY_SPOTS'),'uncertain'),'en');
    assert.ok(mild?.stage && severe?.stage,id);
    assert.notDeepEqual(mild.stage.actions,severe.stage.actions,`${id} severity must affect actions`);
  }
});
test('unknown answers never select mild actions', () => {
  const id = 'tomato_early_blight';
  const result = advisoryApi.evaluateAdvisory(advisory,id,null,'uncertain');
  assert.equal(result.severity,'UNKNOWN');
  assert.equal(protocolsApi.buildCarePlan(model,id,result,'en').stage,null);
});
test('healthy no-damage care does not pretend mild disease was reported', () => {
  const id = 'maize_healthy';
  const result = advisoryApi.evaluateAdvisory(advisory,id,symptoms('NO_VISIBLE_DAMAGE'),'healthy');
  const plan = protocolsApi.buildCarePlan(model,id,result,'en');
  assert.equal(plan.severity,'NONE');
  assert.equal(plan.stage,null);
});
test('symptoms conflicting with healthy output retain evaluation and recovery checks', () => {
  const id = 'potato_healthy';
  const result = advisoryApi.evaluateAdvisory(advisory,id,{...symptoms('MANY_SPOTS'),wiltingOrDying:true},'healthy');
  assert.equal(result.profile,null);
  assert.ok(result.reasonCodes.includes('healthy_conflict'));
  const plan = protocolsApi.buildCarePlan(model,id,result,'en');
  assert.ok(plan);
  assert.ok(plan.copy.confirm_checks.length);
  assert.equal(plan.severity,'SEVERE');
});
test('retake, wrong crop and missing model cannot authorize automatic treatment', () => {
  for (const type of ['retake','crop_mismatch','model_unavailable']) {
    const id='tomato_early_blight';
    assert.equal(protocolsApi.buildCarePlan(model,id,advisoryApi.evaluateAdvisory(advisory,id,symptoms('FEW_SPOTS'),type),'en'),null);
  }
});
test('a low-confidence named leaf candidate can show conditional treatment information', () => {
  const id='tomato_septoria_leaf_spot';
  const result=advisoryApi.evaluateAdvisory(advisory,id,symptoms('SOME_SPOTS'),'uncertain');
  const plan=protocolsApi.buildCarePlan(model,id,result,'en');
  assert.ok(plan);
  assert.equal(plan.stage,model.protocols[id].translations.en.stage_plans.MODERATE);
});
test('missing treatment translations and unknown references fail closed', () => {
  const missing=structuredClone(model);
  missing.protocols.tomato_early_blight.translations.hi.recovery_signs=[];
  assert.throws(()=>protocolsApi.validateCareProtocols(missing),/Incomplete treatment/);
  const badSource=structuredClone(model);
  badSource.protocols.tomato_early_blight.source_ids.push('invented-reference');
  assert.throws(()=>protocolsApi.validateCareProtocols(badSource),/Missing treatment/);
});
