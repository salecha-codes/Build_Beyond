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
  sourceEvaluated?: boolean;
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
  sourceEvaluated?: boolean;
  allowConditionSpecificAdvice?: boolean;
  embeddingDistance?: number;
  leafProbability?: number;
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
  source_evaluated?: boolean;
  source_thresholds_calibrated?: boolean;
  source_acceptance_qualified?: boolean;
  source_acceptance_enabled?: boolean;
  training_status: string;
  leaf_gate?: {
    enabled: boolean;
    output_name: string;
    minimum_leaf_probability: number;
    receipt_file: string;
    receipt_sha256: string;
  };
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
    leaf_logit?: { name: string; shape: number[] };
  };
}
interface Policy {
  schema_version: number;
  model_version: string;
  model_sha256?: string;
  validated: boolean;
  temperature: number;
  min_confidence: number;
  min_margin: number;
  thresholds_calibrated: boolean;
  enabled_condition_ids?: string[];
  allow_condition_specific_advice: boolean;
  source_evaluated?: boolean;
  source_thresholds_calibrated?: boolean;
  source_acceptance_qualified?: boolean;
  source_acceptance_enabled?: boolean;
  source_evaluation_file?: string;
  source_evaluation_sha256?: string;
  embedding_centroids_file?: string;
  embedding_centroids_sha256?: string;
  class_thresholds?: Record<string, ClassThreshold>;
  max_embedding_distance?: number | null;
}
interface ClassThreshold {
  enabled: boolean;
  minimum_confidence: number | null;
  minimum_margin: number | null;
  max_embedding_distance?: number | null;
}
interface SourceAcceptance {
  thresholds: Record<string, ClassThreshold>;
  centroids: Record<string, readonly number[]>;
}
interface Bundle {
  metadata: Metadata;
  policy: Policy;
  session: ort.InferenceSession;
  validated: boolean;
  sourceEvaluated: boolean;
  sourceAcceptance?: SourceAcceptance;
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
  name: 'Crop disease model',
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
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
async function sha256Bytes(bytes: ArrayBuffer): Promise<string> {
  requireThat(!!globalThis.crypto?.subtle, 'A secure context is required to verify the model.');
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(digest), value => value.toString(16).padStart(2, '0')).join('');
}
async function verifiedJsonAsset(filename: string, expectedHash: unknown): Promise<unknown> {
  requireThat(typeof expectedHash === 'string' && /^[a-f0-9]{64}$/.test(expectedHash),
    'Missing source-evidence checksum.');
  const response = await fetch(assetUrl(`model/${filename}`), { credentials: 'same-origin', cache: 'force-cache' });
  requireThat(response.ok, `Packaged source evidence could not load (${response.status}).`);
  const bytes = await response.arrayBuffer();
  requireThat(await sha256Bytes(bytes) === expectedHash, 'Source evidence checksum does not match.');
  return JSON.parse(new TextDecoder().decode(bytes));
}

/** Both vectors are normalized here; zero/nonfinite vectors are invalid runtime evidence. */
export function unitEmbeddingDistance(embedding: ArrayLike<number>, centroid: readonly number[]): number {
  requireThat(embedding.length === centroid.length && embedding.length > 0, 'Embedding dimensions disagree.');
  let embeddingSquared = 0, centroidSquared = 0;
  for (let i = 0; i < embedding.length; i++) {
    requireThat(Number.isFinite(embedding[i]) && Number.isFinite(centroid[i]), 'Embedding values must be finite.');
    embeddingSquared += embedding[i] * embedding[i];
    centroidSquared += centroid[i] * centroid[i];
  }
  requireThat(Number.isFinite(embeddingSquared) && Number.isFinite(centroidSquared) &&
    embeddingSquared > 0 && centroidSquared > 0, 'The model returned an invalid embedding.');
  const embeddingNorm = Math.sqrt(embeddingSquared), centroidNorm = Math.sqrt(centroidSquared);
  let squaredDistance = 0;
  for (let i = 0; i < embedding.length; i++) {
    const difference = embedding[i] / embeddingNorm - centroid[i] / centroidNorm;
    squaredDistance += difference * difference;
  }
  return Math.sqrt(squaredDistance);
}

export function validateSourceAcceptance(
  metadata: Pick<Metadata, 'model_version' | 'model_sha256'>,
  policy: Pick<Policy, 'temperature' | 'class_thresholds'>, receipt: unknown, centroidFile: unknown,
): SourceAcceptance {
  requireThat(isRecord(receipt) && receipt.schema_version === 1 &&
    receipt.model_version === metadata.model_version && receipt.model_sha256 === metadata.model_sha256 &&
    receipt.scope === 'source_domain_only' && receipt.source_acceptance_qualified === true,
  'Source evaluation does not qualify this exact model.');
  const frozen = receipt.frozen_policy;
  requireThat(isRecord(frozen) && frozen.temperature === policy.temperature && isRecord(frozen.class_thresholds),
    'Source evaluation and calibrated policy disagree.');
  const thresholds = policy.class_thresholds;
  requireThat(isRecord(thresholds) && Object.keys(thresholds).length === CONDITIONS.length &&
    Object.keys(frozen.class_thresholds).length === CONDITIONS.length,
  'Source class thresholds do not match the label contract.');
  let enabled = 0;
  for (const label of CONDITIONS) {
    const row = thresholds[label.id], reference = frozen.class_thresholds[label.id];
    requireThat(isRecord(row) && typeof row.enabled === 'boolean' && isRecord(reference) &&
      row.enabled === reference.enabled && row.minimum_confidence === reference.minimum_confidence &&
      row.minimum_margin === reference.minimum_margin && row.max_embedding_distance === reference.max_embedding_distance,
    'Frozen source thresholds do not match the packaged policy.');
    const nullableProbability = (value: unknown) => value === null ||
      (typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1);
    requireThat(nullableProbability(row.minimum_confidence) && nullableProbability(row.minimum_margin) &&
      (row.max_embedding_distance == null || (typeof row.max_embedding_distance === 'number' &&
        Number.isFinite(row.max_embedding_distance) && row.max_embedding_distance >= 0 && row.max_embedding_distance <= 2 + 1e-6)),
    'Invalid source class threshold values.');
    if (row.enabled) {
      requireThat(typeof row.minimum_confidence === 'number' && Number.isFinite(row.minimum_confidence) &&
        row.minimum_confidence > 0 && row.minimum_confidence < 1 &&
        typeof row.minimum_margin === 'number' && Number.isFinite(row.minimum_margin) &&
        row.minimum_margin > 0 && row.minimum_margin < 1 &&
        typeof row.max_embedding_distance === 'number' && Number.isFinite(row.max_embedding_distance) &&
        row.max_embedding_distance >= 0 && row.max_embedding_distance <= 2 + 1e-6,
      'Enabled source classes require calibrated confidence, margin and distance thresholds.');
      enabled++;
    }
  }
  requireThat(enabled > 0, 'Source acceptance has no enabled classes.');
  requireThat(isRecord(centroidFile) && centroidFile.schema_version === 1 &&
    centroidFile.model_version === metadata.model_version && centroidFile.model_sha256 === metadata.model_sha256 &&
    centroidFile.embedding_dimension === 960 &&
    centroidFile.normalization === 'l2_per_embedding_mean_then_l2_centroid' &&
    centroidFile.distance === 'l2_unit_embedding_to_predicted_class_centroid' &&
    Array.isArray(centroidFile.label_ids) && centroidFile.label_ids.length === CONDITIONS.length &&
    centroidFile.label_ids.every((id, index) => id === CONDITIONS[index].id) &&
    Array.isArray(centroidFile.centroids) && centroidFile.centroids.length === CONDITIONS.length,
  'Embedding centroids do not match this model and label contract.');
  const centroids: Record<string, readonly number[]> = {};
  for (let index = 0; index < CONDITIONS.length; index++) {
    const vector: unknown = centroidFile.centroids[index];
    requireThat(Array.isArray(vector) && vector.length === 960 && vector.every(value => typeof value === 'number' && Number.isFinite(value)),
      'Invalid embedding centroid dimensions or values.');
    const norm = Math.sqrt(vector.reduce((sum: number, value: number) => sum + value * value, 0));
    requireThat(Number.isFinite(norm) && Math.abs(norm - 1) <= 1e-3, 'Embedding centroids must have unit norm.');
    centroids[CONDITIONS[index].id] = vector;
  }
  return { thresholds, centroids };
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
    ['MobileNetV4-Conv-Small', 'MobileNetV3-Large'].includes(metadata.architecture) &&
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
  requireThat(Number.isFinite(policy.temperature) && policy.temperature > 0, 'Invalid model temperature.');
  const validated = metadata.diagnosis_validated === true && policy.validated === true && policy.thresholds_calibrated === true;
  const sourceClaimed = metadata.source_evaluated === true && policy.source_evaluated === true &&
    metadata.source_thresholds_calibrated === true && metadata.source_acceptance_qualified === true &&
    metadata.source_acceptance_enabled === true && policy.source_thresholds_calibrated === true &&
    policy.source_acceptance_qualified === true && policy.source_acceptance_enabled === true;
  if (validated && !sourceClaimed) {
    requireThat(Number.isFinite(policy.min_confidence) && policy.min_confidence >= 0 && policy.min_confidence <= 1 &&
      Number.isFinite(policy.min_margin) && policy.min_margin >= 0 && policy.min_margin <= 1 &&
      (policy.max_embedding_distance == null || (Number.isFinite(policy.max_embedding_distance) && policy.max_embedding_distance >= 0)),
    'Invalid model acceptance policy.');
  }
  if (policy.model_sha256 !== undefined) requireThat(policy.model_sha256 === metadata.model_sha256, 'Policy and model checksums disagree.');
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
  const sha256 = await sha256Bytes(bytes);
  requireThat(sha256 === metadata.model_sha256, 'The local model checksum does not match.');
  let sourceAcceptance: SourceAcceptance | undefined;
  if (sourceClaimed) {
    requireThat(policy.source_evaluation_file === 'source_evaluation.json' &&
      policy.embedding_centroids_file === 'embedding_centroids.json', 'Unsupported source evidence filenames.');
    const [receipt, centroids] = await Promise.all([
      verifiedJsonAsset(policy.source_evaluation_file, policy.source_evaluation_sha256),
      verifiedJsonAsset(policy.embedding_centroids_file, policy.embedding_centroids_sha256),
    ]);
    sourceAcceptance = validateSourceAcceptance(metadata, policy, receipt, centroids);
  }
  const sourceEvaluated = sourceAcceptance !== undefined;
  if (metadata.leaf_gate?.enabled) {
    const gate = metadata.leaf_gate;
    requireThat(gate.output_name === 'leaf_logit' && metadata.outputs.leaf_logit?.name === gate.output_name &&
      JSON.stringify(metadata.outputs.leaf_logit.shape) === '[1,1]' &&
      Number.isFinite(gate.minimum_leaf_probability) && gate.minimum_leaf_probability > 0 && gate.minimum_leaf_probability < 1 &&
      gate.receipt_file === 'leaf_validation.json', 'Invalid leaf-check contract.');
    const receipt = await verifiedJsonAsset(gate.receipt_file, gate.receipt_sha256);
    requireThat(isRecord(receipt) && receipt.schema_version === 1 &&
      receipt.model_sha256 === metadata.model_sha256 && receipt.model_version === metadata.model_version &&
      receipt.output_name === gate.output_name && receipt.minimum_leaf_probability === gate.minimum_leaf_probability,
    'Leaf-check evidence does not match this model.');
  }
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
  requireThat(!metadata.leaf_gate?.enabled || session.outputNames.includes(metadata.leaf_gate.output_name), 'Leaf-check output is missing.');
  lastStatus = {
    ready: true,
    validated,
    name: metadata.architecture,
    version: metadata.model_version,
    bytes: bytes.byteLength,
    message: validated
      ? 'Local model is ready.'
      : sourceAcceptance
        ? 'Source-tested prototype is ready. Field diagnosis is not validated.'
        : 'Local scratch-trained prototype is ready. Disease diagnosis is not validated.',
    modelSha256: sha256,
    executionProvider: 'wasm',
    sourceEvaluated,
  };
  return { metadata, policy, session, validated, sourceEvaluated, sourceAcceptance };
}
function getBundle(): Promise<Bundle> {
  if (!bundlePromise)
    bundlePromise = loadBundle().catch((error) => {
      lastStatus = {
        ...lastStatus,
        ready: false,
        validated: false,
        sourceEvaluated: false,
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
    sourceEvaluated: false,
    allowConditionSpecificAdvice: false,
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
  const { metadata, policy, validated, session, sourceEvaluated, sourceAcceptance } = bundle;
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
    let leafProbability: number | undefined;
    if (metadata.leaf_gate?.enabled) {
      const leaf = outputs[metadata.leaf_gate.output_name];
      requireThat(leaf?.type === 'float32' && leaf.data.length === 1 && JSON.stringify(leaf.dims) === '[1,1]', 'Invalid leaf-check output.');
      const leafLogit = Number(leaf.data[0]);
      requireThat(Number.isFinite(leafLogit), 'Invalid leaf-check score.');
      leafProbability = leafLogit >= 0 ? 1 / (1 + Math.exp(-leafLogit)) : Math.exp(leafLogit) / (1 + Math.exp(leafLogit));
      if (leafProbability < metadata.leaf_gate.minimum_leaf_probability) return {
        ...base(), type: 'retake', candidates: [], inferenceMs, modelVersion: metadata.model_version,
        modelSha256: metadata.model_sha256, leafProbability,
        qualityIssues: ['NOT_A_LEAF'], reasons: ['NOT_A_LEAF'], executionProvider: 'wasm',
      };
    }
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
      sourceEvaluated,
      allowConditionSpecificAdvice: validated && policy.allow_condition_specific_advice === true,
      reasons: [],
      modelSha256: metadata.model_sha256,
      executionProvider: 'wasm',
      preprocessingMs,
      outputShapes: [Array.from(logits.dims), Array.from(embeddings.dims)],
      leafProbability,
    };
    // Source-qualified prototype acceptance is distinct from field validation.
    // Old or failed-qualification bundles remain ready but explicitly uncertain.
    if (!validated && !sourceAcceptance) return { ...result, reasons: ['MODEL_NOT_VALIDATED'] };
    const top = candidates[0];
    if (sourceAcceptance) {
      const threshold = sourceAcceptance.thresholds[top.id];
      if (!threshold.enabled) result.reasons!.push('CONDITION_DISABLED');
      else {
        if (top.score < threshold.minimum_confidence!) result.reasons!.push('LOW_SCORE');
        if (top.score - candidates[1].score < threshold.minimum_margin!) result.reasons!.push('AMBIGUOUS');
        const distance = unitEmbeddingDistance(embeddings.data as Float32Array, sourceAcceptance.centroids[top.id]);
        result.embeddingDistance = distance;
        if (distance > threshold.max_embedding_distance!) result.reasons!.push('UNFAMILIAR_IMAGE');
      }
    } else {
      if (top.score < policy.min_confidence) result.reasons!.push('LOW_SCORE');
      if (top.score - candidates[1].score < policy.min_margin) result.reasons!.push('AMBIGUOUS');
      if (policy.enabled_condition_ids && !policy.enabled_condition_ids.includes(top.id)) result.reasons!.push('CONDITION_DISABLED');
      if (policy.max_embedding_distance != null) result.reasons!.push('MISSING_EMBEDDING_DISTANCE');
    }
    if (result.reasons!.length) return result;
    // Crop corrections also require all source-confidence and unfamiliar-image gates.
    if (top.cropId !== cropId) return { ...result, type: 'crop_mismatch', reasons: ['CROP_MISMATCH'] };
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
