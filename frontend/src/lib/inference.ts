/** Real, local CPU inference. No upload, remote diagnosis API, or fixture predictions. */
import * as ort from 'onnxruntime-web/wasm';
// The npm workspace hoists ORT here; its package exports do not expose dist assets.
// Vite emits both files with local URLs, which also remain valid in the QA bundle.
import wasmUrl from '../../../node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.wasm?url';
import wasmModuleUrl from '../../../node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.mjs?url';
import { assetUrl, getConditionLabel } from './content';
import { CONDITIONS } from './types';
import type { AssessmentType, CropId } from './types';
export type { CropId } from './types';

export interface Candidate {
  id: string;
  cropId: CropId;
  nameEn: string;
  nameKn: string;
  score: number;
}
export interface ModelStatus {
  ready: boolean;
  validated: boolean;
  name: string;
  version: string;
  bytes: number;
  message: string;
  modelSha256?: string;
  executionProvider?: 'wasm';
}
export interface AssessmentResult {
  type: AssessmentType;
  candidates: Candidate[];
  inferenceMs: number;
  modelVersion: string;
  validated: boolean;
  qualityIssues?: string[];
  reasons?: string[];
  modelSha256?: string;
  executionProvider?: 'wasm';
  outputShapes?: number[][];
  preprocessingMs?: number;
}
export interface PreprocessSpec {
  width: number;
  height: number;
  padding_rgb: readonly number[];
  pixel_scale: number;
  mean: readonly number[];
  std: readonly number[];
}
interface Metadata {
  schema_version: number;
  model_version: string;
  architecture: string;
  model_file: string;
  model_sha256: string;
  model_size_bytes: number;
  class_count: number;
  embedding_dimension: number;
  diagnosis_validated: boolean;
  training_status: string;
  input: PreprocessSpec & {
    name: string;
    shape: number[];
    dtype: string;
    layout: string;
    color_order: string;
    resize: string;
    resize_rounding: string;
    interpolation: string;
    exif_orientation: boolean;
  };
  outputs: {
    logits: { name: string; shape: number[] };
    embeddings: { name: string; shape: number[] };
  };
}
interface Policy {
  schema_version: number;
  model_version: string;
  validated: boolean;
  temperature: number;
  min_confidence: number;
  min_margin: number;
  thresholds_calibrated: boolean;
  enabled_condition_ids?: string[];
  allow_condition_specific_advice: boolean;
}
interface Bundle {
  metadata: Metadata;
  policy: Policy;
  session: ort.InferenceSession;
  validated: boolean;
}

export const DEFAULT_PREPROCESS: Readonly<PreprocessSpec> = Object.freeze({
  width: 224,
  height: 224,
  padding_rgb: [124, 116, 104],
  pixel_scale: 255,
  mean: [0.485, 0.456, 0.406],
  std: [0.229, 0.224, 0.225],
});

interface Kernel {
  first: number;
  coefficients: Int32Array;
}
function axisKernels(inputSize: number, outputSize: number): Kernel[] {
  const scale = inputSize / outputSize;
  const support = Math.max(1, scale);
  const inverse = 1 / support;
  return Array.from({ length: outputSize }, (_, i) => {
    const center = (i + 0.5) * scale;
    const first = Math.max(0, Math.trunc(center - support + 0.5));
    const end = Math.min(inputSize, Math.trunc(center + support + 0.5));
    const weights = Array.from({ length: end - first }, (_, offset) =>
      Math.max(0, 1 - Math.abs((offset + first - center + 0.5) * inverse)),
    );
    const total = weights.reduce((a, b) => a + b, 0);
    if (!(total > 0)) throw new Error('Empty RGB interpolation kernel.');
    return {
      first,
      coefficients: Int32Array.from(weights, (weight) =>
        Math.trunc((weight / total) * 4194304 + 0.5),
      ),
    };
  });
}

/**
 * Separable antialiased RGB BILINEAR matching Pillow's 22-bit coefficient/8-bit
 * intermediate convention, unchanged axes skipped. Ordinary letterbox resizing
 * runs horizontal then vertical; mixed width-up/height-down uses Pillow13's
 * reducing-axis-first optimization.
 * Algorithm reference: https://github.com/python-pillow/Pillow/blob/13.0.0/src/libImaging/Resample.c
 * Input/output is packed RGB, not RGBA. Browser image decoding is a separate step.
 */
export function pillowBilinearRgb(
  rgb: Uint8Array | Uint8ClampedArray,
  width: number,
  height: number,
  newWidth: number,
  newHeight: number,
): Uint8Array {
  for (const size of [width, height, newWidth, newHeight]) {
    if (!Number.isSafeInteger(size) || size < 1) throw new Error('Invalid RGB image dimensions.');
  }
  if (rgb.length !== width * height * 3)
    throw new Error('RGB buffer size does not match dimensions.');
  if (newWidth * Math.max(height, newHeight) > 16777216)
    throw new Error('RGB resize exceeds the memory bound.');
  // Pillow13 reduces height first only for this mixed up/downsampling case.
  // Letterbox preprocessing never mixes upscaling and downscaling axes.
  if (newWidth > width && newHeight < height) {
    return pillowBilinearRgb(
      pillowBilinearRgb(rgb, width, height, width, newHeight),
      width,
      newHeight,
      newWidth,
      newHeight,
    );
  }
  let horizontal: Uint8Array | Uint8ClampedArray = rgb;
  if (width !== newWidth) {
    const kernels = axisKernels(width, newWidth);
    horizontal = new Uint8Array(newWidth * height * 3);
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < newWidth; x++) {
        const { first, coefficients } = kernels[x];
        for (let channel = 0; channel < 3; channel++) {
          let sum = 2097152;
          for (let k = 0; k < coefficients.length; k++) {
            sum += rgb[(y * width + first + k) * 3 + channel] * coefficients[k];
          }
          horizontal[(y * newWidth + x) * 3 + channel] = Math.max(0, Math.min(255, sum >> 22));
        }
      }
    }
  }
  if (height === newHeight) return Uint8Array.from(horizontal);
  const kernels = axisKernels(height, newHeight);
  const output = new Uint8Array(newWidth * newHeight * 3);
  for (let y = 0; y < newHeight; y++) {
    const { first, coefficients } = kernels[y];
    for (let x = 0; x < newWidth; x++) {
      for (let channel = 0; channel < 3; channel++) {
        let sum = 2097152;
        for (let k = 0; k < coefficients.length; k++) {
          sum += horizontal[((first + k) * newWidth + x) * 3 + channel] * coefficients[k];
        }
        output[(y * newWidth + x) * 3 + channel] = Math.max(0, Math.min(255, sum >> 22));
      }
    }
  }
  return output;
}

/** Half-up letterbox + float32 ImageNet normalization, packed RGB -> NCHW. */
export function preprocessRgb(
  rgb: Uint8Array | Uint8ClampedArray,
  width: number,
  height: number,
  spec: Readonly<PreprocessSpec> = DEFAULT_PREPROCESS,
): Float32Array {
  const scale = Math.min(spec.width / width, spec.height / height);
  const newWidth = Math.max(1, Math.floor(width * scale + 0.5));
  const newHeight = Math.max(1, Math.floor(height * scale + 0.5));
  const resized = pillowBilinearRgb(rgb, width, height, newWidth, newHeight);
  const offsetX = Math.floor((spec.width - newWidth) / 2);
  const offsetY = Math.floor((spec.height - newHeight) / 2);
  const area = spec.width * spec.height;
  const result = new Float32Array(3 * area);
  const mean = Float32Array.from(spec.mean),
    std = Float32Array.from(spec.std);
  const pixelScale = Math.fround(spec.pixel_scale);
  for (let y = 0; y < spec.height; y++) {
    for (let x = 0; x < spec.width; x++) {
      const inside =
        x >= offsetX && x < offsetX + newWidth && y >= offsetY && y < offsetY + newHeight;
      const source = ((y - offsetY) * newWidth + x - offsetX) * 3;
      for (let channel = 0; channel < 3; channel++) {
        const value = inside ? resized[source + channel] : spec.padding_rgb[channel];
        result[channel * area + y * spec.width + x] = Math.fround(
          Math.fround(Math.fround(value / pixelScale) - mean[channel]) / std[channel],
        );
      }
    }
  }
  return result;
}

/**
 * EXIF orientation is applied once by createImageBitmap. Decoded working RGB is
 * capped to 1024px; large-image browser decode/downsampling can differ from Android
 * codecs. Exact Pillow parity applies from these decoded RGB bytes to model tensor.
 */
export async function decodeLeafImage(
  file: Blob,
): Promise<{ rgb: Uint8Array; width: number; height: number }> {
  if (!file.size || file.size > 30 * 1024 * 1024)
    throw new Error('Select a photo smaller than 30 MB.');
  let bitmap = await createImageBitmap(file, {
    imageOrientation: 'from-image',
    premultiplyAlpha: 'none',
  });
  try {
    const scale = Math.min(1, 1024 / Math.max(bitmap.width, bitmap.height));
    if (scale < 1) {
      const capped = await createImageBitmap(bitmap, {
        resizeWidth: Math.max(1, Math.floor(bitmap.width * scale + 0.5)),
        resizeHeight: Math.max(1, Math.floor(bitmap.height * scale + 0.5)),
        resizeQuality: 'high',
      });
      bitmap.close();
      bitmap = capped;
    }
    const { width, height } = bitmap;
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    try {
      const context = canvas.getContext('2d', { willReadFrequently: true });
      if (!context) throw new Error('This browser cannot prepare photos.');
      context.drawImage(bitmap, 0, 0);
      const rgba = context.getImageData(0, 0, width, height).data;
      const rgb = new Uint8Array(width * height * 3);
      for (let i = 0; i < width * height; i++) {
        rgb[i * 3] = rgba[i * 4];
        rgb[i * 3 + 1] = rgba[i * 4 + 1];
        rgb[i * 3 + 2] = rgba[i * 4 + 2];
      }
      return { rgb, width, height };
    } finally {
      canvas.width = 0;
      canvas.height = 0;
    }
  } finally {
    bitmap.close();
  }
}

/** Capture heuristics only; passing these does not prove that a photo contains a leaf. */
export function photoQualityIssues(rgb: Uint8Array, width: number, height: number): string[] {
  const scale = Math.min(1, 256 / Math.max(width, height));
  const w = Math.max(1, Math.floor(width * scale)),
    h = Math.max(1, Math.floor(height * scale));
  const small = pillowBilinearRgb(rgb, width, height, w, h);
  const luma = new Float64Array(w * h);
  let total = 0;
  for (let i = 0; i < luma.length; i++) {
    luma[i] = 0.2126 * small[i * 3] + 0.7152 * small[i * 3 + 1] + 0.0722 * small[i * 3 + 2];
    total += luma[i];
  }
  let sum = 0,
    squared = 0,
    count = 0;
  for (let y = 1; y < h - 1; y++)
    for (let x = 1; x < w - 1; x++) {
      const i = y * w + x;
      const lap = luma[i - 1] + luma[i + 1] + luma[i - w] + luma[i + w] - 4 * luma[i];
      sum += lap;
      squared += lap * lap;
      count++;
    }
  const mean = total / luma.length;
  const variance = count ? Math.max(0, squared / count - (sum / count) ** 2) : 0;
  const issues: string[] = [];
  if (width < 224 || height < 224) issues.push('TOO_SMALL');
  if (mean < 20) issues.push('TOO_DARK');
  if (mean > 240) issues.push('TOO_BRIGHT');
  if (variance < 25) issues.push('BLURRY');
  return issues;
}

let bundlePromise: Promise<Bundle> | null = null;
let lastStatus: ModelStatus = {
  ready: false,
  validated: false,
  name: 'MobileNetV4-Conv-Small',
  version: '',
  bytes: 0,
  message: 'Preparing the local model…',
};
function requireThat(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}
async function jsonAsset(path: string): Promise<unknown> {
  const response = await fetch(assetUrl(`model/${path}`), {
    credentials: 'same-origin',
    cache: 'force-cache',
  });
  if (!response.ok) throw new Error(`Packaged model asset could not load (${response.status}).`);
  return response.json();
}
async function loadBundle(): Promise<Bundle> {
  const [metadataJson, policyJson, labelsJson] = await Promise.all([
    jsonAsset('model_metadata.json'),
    jsonAsset('decision_policy.json'),
    jsonAsset('labels.json'),
  ]);
  const metadata = metadataJson as Metadata,
    policy = policyJson as Policy;
  const labels = labelsJson as {
    schema_version: number;
    labels: Array<{ index: number; id: string; crop_id: string; source_label: string }>;
  };
  requireThat(
    metadata.schema_version === 1 && policy.schema_version === 1 && labels.schema_version === 1,
    'Incompatible model bundle schema.',
  );
  requireThat(
    metadata.architecture === 'MobileNetV4-Conv-Small' &&
      metadata.class_count === 17 &&
      metadata.embedding_dimension === 960,
    'The packaged model architecture does not match this application.',
  );
  requireThat(
    metadata.model_version === policy.model_version && metadata.model_file === 'crop_model.onnx',
    'Model and policy versions disagree.',
  );
  requireThat(
    metadata.input?.dtype === 'float32' &&
      metadata.input.layout === 'NCHW' &&
      metadata.input.color_order === 'RGB' &&
      metadata.input.resize === 'letterbox' &&
      metadata.input.resize_rounding === 'half_up' &&
      metadata.input.interpolation === 'bilinear' &&
      JSON.stringify(metadata.input.shape) === '[1,3,224,224]' &&
      metadata.input.width === 224 &&
      metadata.input.height === 224,
    'Unsupported model preprocessing contract.',
  );
  requireThat(
    metadata.input.mean.length === 3 &&
      metadata.input.std.length === 3 &&
      metadata.input.padding_rgb.length === 3 &&
      metadata.input.mean.every(Number.isFinite) &&
      metadata.input.std.every((value) => Number.isFinite(value) && value > 0) &&
      metadata.input.padding_rgb.every(
        (value) => Number.isInteger(value) && value >= 0 && value <= 255,
      ) &&
      Number.isFinite(metadata.input.pixel_scale) &&
      metadata.input.pixel_scale > 0,
    'Invalid RGB normalization contract.',
  );
  requireThat(
    Array.isArray(labels.labels) &&
      labels.labels.length === CONDITIONS.length &&
      labels.labels.every((label, index) => {
        const expected = CONDITIONS[index];
        return (
          label.index === index &&
          label.id === expected.id &&
          label.crop_id === expected.crop_id &&
          label.source_label === expected.source_label
        );
      }),
    'Model labels disagree with the stable application contract.',
  );
  requireThat(
    Number.isFinite(policy.temperature) &&
      policy.temperature > 0 &&
      Number.isFinite(policy.min_confidence) &&
      policy.min_confidence >= 0 &&
      policy.min_confidence <= 1 &&
      Number.isFinite(policy.min_margin) &&
      policy.min_margin >= 0 &&
      policy.min_margin <= 1,
    'Invalid model acceptance policy.',
  );
  requireThat(/^[a-f0-9]{64}$/.test(metadata.model_sha256), 'Missing model checksum.');
  const response = await fetch(assetUrl(`model/${metadata.model_file}`), {
    credentials: 'same-origin',
    cache: 'force-cache',
  });
  if (!response.ok) throw new Error(`The local model could not load (${response.status}).`);
  const bytes = await response.arrayBuffer();
  requireThat(
    bytes.byteLength === metadata.model_size_bytes,
    'The local model file has an unexpected size.',
  );
  requireThat(!!globalThis.crypto?.subtle, 'A secure context is required to verify the model.');
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  const sha256 = Array.from(new Uint8Array(digest), (value) =>
    value.toString(16).padStart(2, '0'),
  ).join('');
  requireThat(sha256 === metadata.model_sha256, 'The local model checksum does not match.');
  // Single thread runs without SharedArrayBuffer/cross-origin isolation. All runtime
  // code and WASM come from this build; no CDN or arbitrary remote code is loaded.
  ort.env.wasm.numThreads = 1;
  ort.env.wasm.proxy = false;
  ort.env.wasm.wasmPaths = { wasm: wasmUrl, mjs: wasmModuleUrl };
  const session = await ort.InferenceSession.create(bytes, {
    executionProviders: ['wasm'],
    graphOptimizationLevel: 'all',
  });
  requireThat(
    session.inputNames.includes(metadata.input.name) &&
      session.outputNames.includes(metadata.outputs.logits.name) &&
      session.outputNames.includes(metadata.outputs.embeddings.name),
    'The model input/output names do not match metadata.',
  );
  const validated =
    metadata.diagnosis_validated === true &&
    policy.validated === true &&
    policy.thresholds_calibrated === true;
  lastStatus = {
    ready: true,
    validated,
    name: metadata.architecture,
    version: metadata.model_version,
    bytes: bytes.byteLength,
    message: validated
      ? 'Local model is ready.'
      : 'Local scratch-trained prototype is ready. Disease diagnosis is not validated.',
    modelSha256: sha256,
    executionProvider: 'wasm',
  };
  return { metadata, policy, session, validated };
}
function getBundle(): Promise<Bundle> {
  if (!bundlePromise)
    bundlePromise = loadBundle().catch((error) => {
      lastStatus = {
        ...lastStatus,
        ready: false,
        validated: false,
        message: error instanceof Error ? error.message : 'The local model is unavailable.',
      };
      bundlePromise = null;
      throw error;
    });
  return bundlePromise;
}
export async function getModelStatus(): Promise<ModelStatus> {
  try {
    await getBundle();
  } catch {
    /* Visible unavailable status, never fabricated readiness. */
  }
  return { ...lastStatus };
}

let inferenceQueue: Promise<unknown> = Promise.resolve();
/** Runs at most one real model call at a time; all scores retain the global17-label normalization. */
export function analyzeLeaf(file: File, cropId: CropId): Promise<AssessmentResult> {
  const pending = inferenceQueue.then(() => analyzeOnce(file, cropId));
  inferenceQueue = pending.catch(() => undefined);
  return pending;
}
async function analyzeOnce(file: File, cropId: CropId): Promise<AssessmentResult> {
  const base = (): AssessmentResult => ({
    type: 'model_unavailable',
    candidates: [],
    inferenceMs: 0,
    modelVersion: lastStatus.version,
    validated: false,
  });
  let decoded: Awaited<ReturnType<typeof decodeLeafImage>>;
  const preparationStart = performance.now();
  try {
    decoded = await decodeLeafImage(file);
  } catch (error) {
    return {
      ...base(),
      type: 'retake',
      qualityIssues: ['UNREADABLE'],
      reasons: [error instanceof Error ? error.message : 'This photo could not be read.'],
    };
  }
  const qualityIssues = photoQualityIssues(decoded.rgb, decoded.width, decoded.height);
  if (qualityIssues.length)
    return { ...base(), type: 'retake', qualityIssues, reasons: ['PHOTO_QUALITY_HEURISTIC'] };
  let bundle: Bundle;
  try {
    bundle = await getBundle();
  } catch (error) {
    return { ...base(), reasons: [error instanceof Error ? error.message : 'MODEL_UNAVAILABLE'] };
  }
  const { metadata, policy, validated, session } = bundle;
  const input = preprocessRgb(decoded.rgb, decoded.width, decoded.height, metadata.input);
  const preprocessingMs = performance.now() - preparationStart;
  // Give the processing screen a rendering opportunity before a CPU WASM call.
  await new Promise<void>((resolve) => setTimeout(resolve, 0));
  const tensor = new ort.Tensor('float32', input, metadata.input.shape);
  let outputs: ort.InferenceSession.ReturnType | undefined;
  const started = performance.now();
  try {
    outputs = await session.run({ [metadata.input.name]: tensor });
    const inferenceMs = performance.now() - started;
    const logits = outputs[metadata.outputs.logits.name],
      embeddings = outputs[metadata.outputs.embeddings.name];
    requireThat(
      logits.type === 'float32' &&
        logits.data.length === 17 &&
        embeddings.type === 'float32' &&
        embeddings.data.length === 960 &&
        JSON.stringify(logits.dims) === '[1,17]' &&
        JSON.stringify(embeddings.dims) === '[1,960]',
      'The local model returned invalid output dimensions.',
    );
    const values = Array.from(logits.data as Float32Array);
    requireThat(
      values.every(Number.isFinite) &&
        Array.from(embeddings.data as Float32Array).every(Number.isFinite),
      'The model returned invalid scores.',
    );
    const scaled = values.map((value) => value / policy.temperature);
    const maximum = Math.max(...scaled),
      exps = scaled.map((value) => Math.exp(value - maximum));
    const sum = exps.reduce((a, b) => a + b, 0);
    const candidates = CONDITIONS.map(
      (condition, index): Candidate => ({
        id: condition.id,
        cropId: condition.crop_id,
        nameEn: condition.name_en,
        nameKn: getConditionLabel(condition.id)?.name_kn ?? condition.name_en,
        score: exps[index] / sum,
      }),
    ).sort((a, b) => b.score - a.score);
    const result: AssessmentResult = {
      type: 'uncertain',
      candidates,
      inferenceMs,
      modelVersion: metadata.model_version,
      validated,
      reasons: [],
      modelSha256: metadata.model_sha256,
      executionProvider: 'wasm',
      preprocessingMs,
      outputShapes: [Array.from(logits.dims), Array.from(embeddings.dims)],
    };
    // Gate precedes crop mismatch: an unvalidated model cannot assert a wrong crop.
    if (!validated) return { ...result, reasons: ['MODEL_NOT_VALIDATED'] };
    const top = candidates[0];
    if (top.cropId !== cropId)
      return { ...result, type: 'crop_mismatch', reasons: ['CROP_MISMATCH'] };
    if (top.score < policy.min_confidence) result.reasons!.push('LOW_SCORE');
    if (top.score - candidates[1].score < policy.min_margin) result.reasons!.push('AMBIGUOUS');
    if (policy.enabled_condition_ids && !policy.enabled_condition_ids.includes(top.id))
      result.reasons!.push('CONDITION_DISABLED');
    if (result.reasons!.length) return result;
    return { ...result, type: top.id.endsWith('_healthy') ? 'healthy' : 'likely' };
  } catch (error) {
    return {
      ...base(),
      modelVersion: metadata.model_version,
      reasons: [error instanceof Error ? error.message : 'INFERENCE_FAILED'],
    };
  } finally {
    tensor.dispose();
    if (outputs) for (const output of Object.values(outputs)) output.dispose();
  }
}
