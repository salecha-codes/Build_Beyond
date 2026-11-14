/**
 * Lightweight loader/decision fixtures. ORT and image decoding are explicitly
 * mocked here: these checks do not execute or measure a trained crop model.
 */
const { test, before, afterEach } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const { createHash, webcrypto } = require('node:crypto');
const esbuild = require('esbuild');
const root = path.resolve(__dirname, '../..');
const labels = JSON.parse(fs.readFileSync(path.join(root, 'contracts/labels.json'), 'utf8'));
const ids = labels.labels.map(label => label.id);
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const copy = value => JSON.parse(JSON.stringify(value));
const original = { fetch: global.fetch, document: global.document, createImageBitmap: global.createImageBitmap };
if (!global.crypto) global.crypto = webcrypto;
afterEach(() => Object.assign(global, original));

let bundle;
before(async () => {
  const built = await esbuild.build({
    stdin: { resolveDir: root, contents: `export * from './frontend/src/lib/inference.ts'; export { configureFixture } from 'qa:ort-control';`, loader: 'ts' },
    bundle: true, write: false, format: 'cjs', platform: 'node', target: 'es2022',
    define: { 'import.meta.env': JSON.stringify({ BASE_URL: '/', PROD: true }) },
    plugins: [{
      name: 'explicit-unit-only-ort-stub', setup(build) {
        build.onResolve({ filter: /^(onnxruntime-web\/wasm|qa:ort-control)$/ }, () => ({ path: 'ort-fixture', namespace: 'unit-ort' }));
        build.onLoad({ filter: /.*/, namespace: 'unit-ort' }, () => ({ contents: `
          let fixture; export const env={wasm:{}};
          export function configureFixture(value){fixture=value;}
          export class Tensor{constructor(type,data,dims){this.type=type;this.data=data;this.dims=dims;}dispose(){}}
          export const InferenceSession={async create(){fixture.creates++;return{
            inputNames:['image'],outputNames:['logits','embeddings'],
            async run(){if(fixture.runError)throw new Error(fixture.runError);return{
              logits:new Tensor('float32',Float32Array.from(fixture.logits),[1,17]),
              embeddings:new Tensor('float32',Float32Array.from(fixture.embedding),[1,960])};},async release(){}
          };}};`, loader: 'js' }));
        build.onResolve({ filter: /\?url$/ }, args => ({ path: args.path, namespace: 'unit-url' }));
        build.onLoad({ filter: /.*/, namespace: 'unit-url' }, () => ({ contents: `export default '/unused-unit-only-runtime';`, loader: 'js' }));
      },
    }],
  });
  bundle = built.outputFiles[0].text;
});
function freshEngine() {
  const filename = path.join(__dirname, 'in-memory-unit-engine.cjs');
  const loaded = new Module(filename, module);
  loaded.filename = filename; loaded.paths = module.paths; loaded._compile(bundle, filename);
  return loaded.exports;
}
function fixture() {
  const model = Buffer.from('unit fixture, not an ONNX model');
  const modelHash = hash(model), version = 'qa-fixture-not-a-trained-model';
  const thresholds = Object.fromEntries(ids.map(id => [id, { enabled: false, minimum_confidence: null, minimum_margin: null, max_embedding_distance: null }]));
  thresholds.potato_early_blight = { enabled: true, minimum_confidence: .8, minimum_margin: .2, max_embedding_distance: .3 };
  const metadata = {
    schema_version: 1, model_version: version, architecture: 'MobileNetV4-Conv-Small',
    model_file: 'crop_model.onnx', model_sha256: modelHash, model_size_bytes: model.length,
    class_count: 17, embedding_dimension: 960, diagnosis_validated: false, training_status: 'unit_fixture',
    source_evaluated: true, source_thresholds_calibrated: true, source_acceptance_qualified: true, source_acceptance_enabled: true,
    input: { name: 'image', dtype: 'float32', shape: [1,3,224,224], layout: 'NCHW', color_order: 'RGB',
      width: 224, height: 224, resize: 'letterbox', resize_rounding: 'half_up', interpolation: 'bilinear',
      padding_rgb: [124,116,104], pixel_scale: 255, mean: [.485,.456,.406], std: [.229,.224,.225], exif_orientation: true },
    outputs: { logits: { name: 'logits', shape: [1,17] }, embeddings: { name: 'embeddings', shape: [1,960] } },
  };
  // No legacy globals: qualified source acceptance must use the frozen class gates.
  const policy = {
    schema_version: 1, model_version: version, model_sha256: modelHash, validated: false,
    thresholds_calibrated: false, temperature: 1, allow_condition_specific_advice: false,
    source_evaluated: true, source_thresholds_calibrated: true, source_acceptance_qualified: true, source_acceptance_enabled: true,
    source_evaluation_file: 'source_evaluation.json', embedding_centroids_file: 'embedding_centroids.json', class_thresholds: thresholds,
  };
  const centroids = { schema_version: 1, model_version: version, model_sha256: modelHash,
    embedding_dimension: 960, label_ids: ids, normalization: 'l2_per_embedding_mean_then_l2_centroid',
    distance: 'l2_unit_embedding_to_predicted_class_centroid', centroids: ids.map(() => [1,...Array(959).fill(0)]) };
  const receipt = { schema_version: 1, model_version: version, model_sha256: modelHash,
    scope: 'source_domain_only', source_acceptance_qualified: true,
    frozen_policy: { temperature: policy.temperature, class_thresholds: copy(thresholds) } };
  return { model, metadata, policy, centroids, receipt,
    ort: { creates: 0, logits: ids.map(id => id === 'potato_early_blight' ? 10 : -6), embedding: [1,...Array(959).fill(0)] } };
}
function seal(value) {
  const source = Buffer.from(JSON.stringify(value.receipt)), centroids = Buffer.from(JSON.stringify(value.centroids));
  value.policy.source_evaluation_sha256 = hash(source);
  value.policy.embedding_centroids_sha256 = hash(centroids);
  return new Map([
    ['model_metadata.json', Buffer.from(JSON.stringify(value.metadata))],
    ['decision_policy.json', Buffer.from(JSON.stringify(value.policy))],
    ['labels.json', Buffer.from(JSON.stringify(labels))],
    ['crop_model.onnx', value.model], ['source_evaluation.json', source], ['embedding_centroids.json', centroids],
  ]);
}
function install(value, assets = seal(value)) {
  const requests = [];
  global.fetch = async input => {
    const filename = new URL(String(input), 'https://unit.invalid').pathname.split('/').pop();
    requests.push(filename); const body = assets.get(filename);
    return new Response(body || 'Missing unit fixture', { status: body ? 200 : 404 });
  };
  // Decoder stub supplies a textured, correctly sized RGB image so these tests
  // exercise acceptance rather than codec behavior (covered by separate goldens).
  const rgba = new Uint8ClampedArray(256*256*4);
  for (let y=0;y<256;y++) for (let x=0;x<256;x++) {
    const offset=(y*256+x)*4, level=(x+y)%2 ? 96 : 160;
    rgba[offset]=rgba[offset+1]=rgba[offset+2]=level; rgba[offset+3]=255;
  }
  global.createImageBitmap = async () => ({ width: 256, height: 256, close() {} });
  global.document = { createElement: () => ({ width: 0, height: 0, getContext: () => ({ drawImage() {}, getImageData: () => ({ data: rgba }) }) }) };
  const engine = freshEngine(); engine.configureFixture(value.ort);
  return { engine, requests };
}
const image = () => new File([new Uint8Array([1])], 'explicit-unit-decoder-fixture.png', { type: 'image/png' });

// These fixtures assert policy/runtime wiring, never model recognition quality.
test('qualified source prediction accepts while field validation/advisory permission remain false', async () => {
  const value=fixture(); value.policy.allow_condition_specific_advice=true;
  const {engine}=install(value); const status=await engine.getModelStatus();
  assert.equal(status.ready,true); assert.equal(status.validated,false); assert.equal(status.sourceEvaluated,true);
  const output=await engine.analyzeLeaf(image(),'potato');
  assert.equal(output.type,'likely'); assert.equal(output.validated,false); assert.equal(output.sourceEvaluated,true);
  assert.equal(output.allowConditionSpecificAdvice,false); assert.equal(output.embeddingDistance,0);
  assert.equal(output.candidates.length,17); assert.ok(Math.abs(output.candidates.reduce((sum,item)=>sum+item.score,0)-1)<1e-12);
});
test('qualified healthy-looking class is separate from field validation', async () => {
  const value=fixture(); value.policy.class_thresholds.tomato_healthy=copy(value.policy.class_thresholds.potato_early_blight);
  value.receipt.frozen_policy.class_thresholds=copy(value.policy.class_thresholds);
  value.ort.logits=ids.map(id=>id==='tomato_healthy'?10:-6);
  const {engine}=install(value); const output=await engine.analyzeLeaf(image(),'tomato');
  assert.equal(output.type,'healthy'); assert.equal(output.validated,false);
});
test('absent source flags keep legacy executable model uncertain', async () => {
  const value=fixture(); for(const key of ['source_evaluated','source_thresholds_calibrated','source_acceptance_qualified','source_acceptance_enabled']){delete value.metadata[key];delete value.policy[key];}
  const {engine,requests}=install(value); assert.equal((await engine.getModelStatus()).ready,true);
  const output=await engine.analyzeLeaf(image(),'potato'); assert.equal(output.type,'uncertain');
  assert.deepEqual(output.reasons,['MODEL_NOT_VALIDATED']); assert.equal(output.sourceEvaluated,false);
  assert.ok(!requests.includes('source_evaluation.json'));
});
for(const key of ['source_evaluated','source_thresholds_calibrated','source_acceptance_qualified','source_acceptance_enabled']) test(`false metadata ${key} cannot qualify source acceptance`,async()=>{
  const value=fixture(); value.metadata[key]=false;
  const {engine}=install(value); assert.equal((await engine.getModelStatus()).ready,true);
  const output=await engine.analyzeLeaf(image(),'potato');assert.equal(output.type,'uncertain');assert.equal(output.sourceEvaluated,false);
});
test('failed qualification remains ready and uncertain even without source sidecars',async()=>{
  const value=fixture();value.policy.source_acceptance_qualified=false;const assets=seal(value);assets.delete('source_evaluation.json');assets.delete('embedding_centroids.json');
  const {engine}=install(value,assets);assert.equal((await engine.getModelStatus()).ready,true);
  const output=await engine.analyzeLeaf(image(),'potato');assert.equal(output.type,'uncertain');assert.equal(output.sourceEvaluated,false);
});
test('disabled class null thresholds remain uncertain rather than malformed or accepted',async()=>{
  const value=fixture();value.policy.class_thresholds.tomato_healthy=copy(value.policy.class_thresholds.potato_early_blight);
  value.policy.class_thresholds.potato_early_blight={enabled:false,minimum_confidence:null,minimum_margin:null,max_embedding_distance:null};
  value.receipt.frozen_policy.class_thresholds=copy(value.policy.class_thresholds);
  const {engine}=install(value);assert.equal((await engine.getModelStatus()).ready,true);
  assert.deepEqual((await engine.analyzeLeaf(image(),'potato')).reasons,['CONDITION_DISABLED']);
});
test('low global score/margin are uncertain before a different-crop correction',async()=>{
  const value=fixture();for(const id of ids)value.policy.class_thresholds[id]=copy(value.policy.class_thresholds.potato_early_blight);
  value.receipt.frozen_policy.class_thresholds=copy(value.policy.class_thresholds);value.ort.logits=Array(17).fill(0);
  const {engine}=install(value);const output=await engine.analyzeLeaf(image(),'tomato');
  assert.equal(output.candidates[0].cropId,'maize');assert.equal(output.type,'uncertain');assert.ok(output.reasons.includes('LOW_SCORE'));assert.ok(output.reasons.includes('AMBIGUOUS'));
});
test('unfamiliar embedding is uncertain before a different-crop correction',async()=>{
  const value=fixture();value.ort.embedding=[0,1,...Array(958).fill(0)];const {engine}=install(value);
  const output=await engine.analyzeLeaf(image(),'tomato');assert.equal(output.type,'uncertain');assert.deepEqual(output.reasons,['UNFAMILIAR_IMAGE']);
  assert.ok(Math.abs(output.embeddingDistance-Math.sqrt(2))<1e-12);
});
test('crop mismatch is emitted only after the qualified class passes every gate',async()=>{
  const {engine}=install(fixture());const output=await engine.analyzeLeaf(image(),'tomato');
  assert.equal(output.type,'crop_mismatch');assert.deepEqual(output.reasons,['CROP_MISMATCH']);assert.equal(output.candidates.length,17);
});
for(const filename of ['source_evaluation.json','embedding_centroids.json'])test(`${filename} byte tampering fails its bound SHA before session creation`,async()=>{
  const value=fixture(),assets=seal(value);assets.set(filename,Buffer.concat([assets.get(filename),Buffer.from(' ')]));
  const {engine}=install(value,assets);const status=await engine.getModelStatus();assert.equal(status.ready,false);assert.match(status.message,/checksum/);assert.equal(value.ort.creates,0);
});
for(const field of ['minimum_confidence','minimum_margin','max_embedding_distance','enabled'])test(`frozen policy ${field} corruption is rejected even when receipt bytes have a valid SHA`,async()=>{
  const value=fixture();value.policy.class_thresholds.potato_early_blight[field]=field==='enabled'?false:.1;
  const {engine}=install(value);const status=await engine.getModelStatus();assert.equal(status.ready,false);assert.match(status.message,/Frozen source thresholds/);assert.equal(value.ort.creates,0);
});
test('frozen temperature mismatch is rejected',async()=>{
  const value=fixture();value.policy.temperature=1.2;const {engine}=install(value);assert.match((await engine.getModelStatus()).message,/calibrated policy disagree/);assert.equal(value.ort.creates,0);
});
for(const damage of ['model-sha','label-order','shape','zero-norm'])test(`bound centroid ${damage} corruption is rejected after valid file hashing`,async()=>{
  const value=fixture();if(damage==='model-sha')value.centroids.model_sha256='f'.repeat(64);
  if(damage==='label-order')value.centroids.label_ids=[ids[1],ids[0],...ids.slice(2)];
  if(damage==='shape')value.centroids.centroids[0]=[1];if(damage==='zero-norm')value.centroids.centroids[0]=Array(960).fill(0);
  const {engine}=install(value);assert.equal((await engine.getModelStatus()).ready,false);assert.equal(value.ort.creates,0);
});
test('runtime failure is model_unavailable with no fake candidate fallback',async()=>{
  const value=fixture();value.ort.runError='Explicit mocked runtime failure';const {engine}=install(value);const output=await engine.analyzeLeaf(image(),'potato');
  assert.equal(output.type,'model_unavailable');assert.deepEqual(output.candidates,[]);assert.match(output.reasons[0],/runtime failure/);
});
test('unit embedding distance normalizes vectors and rejects zero/nonfinite evidence',()=>{
  const engine=freshEngine();assert.equal(engine.unitEmbeddingDistance([2,0],[1,0]),0);
  assert.ok(Math.abs(engine.unitEmbeddingDistance([0,4],[1,0])-Math.sqrt(2))<1e-12);
  assert.throws(()=>engine.unitEmbeddingDistance([0,0],[1,0]),/invalid embedding/);
  assert.throws(()=>engine.unitEmbeddingDistance([NaN,0],[1,0]),/finite/);
});
