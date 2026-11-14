import { cp, mkdir, readFile, rm } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = fileURLToPath(new URL('../', import.meta.url));
// Keep authored knowledge changes from silently shipping an older care bundle.
const advisorySource = await readFile(path.join(root, 'content/advisory_model.json'));
const advisoryPackaged = await readFile(path.join(root, 'android/app/src/main/assets/content/advisory_model.json'));
const advisoryReceipt = JSON.parse(await readFile(path.join(root, 'android/app/src/main/assets/content/advisory_receipt.json'), 'utf8'));
if (!advisorySource.equals(advisoryPackaged) || createHash('sha256').update(advisorySource).digest('hex') !== advisoryReceipt.profile_sha256)
  throw new Error('Care model assets are stale. Run python3 tools/build_advisory_bundle.py.');
const treatmentSource = await readFile(path.join(root, 'content/care_protocols.json'));
const treatmentPackaged = await readFile(path.join(root, 'android/app/src/main/assets/content/care_protocols.json'));
const treatmentReceipt = JSON.parse(await readFile(path.join(root, 'android/app/src/main/assets/content/care_protocols_receipt.json'), 'utf8'));
if (!treatmentSource.equals(treatmentPackaged) || createHash('sha256').update(treatmentSource).digest('hex') !== treatmentReceipt.protocol_sha256)
  throw new Error('Treatment protocols are stale. Run python3 tools/build_care_protocols.py.');
const destination = path.join(root, 'frontend/public/assets');
await mkdir(destination, { recursive: true });
await cp(path.join(root, 'frontend/public/app-logo.png'), path.join(destination, 'app-logo.png'));
await cp(path.join(root, 'content/samples'), path.join(destination, 'samples'), { recursive: true });
for (const [source, name] of [
  ['models/assets/model', 'model'],
  ['android/app/src/main/assets/content', 'content'],
  ['android/app/src/main/assets/audio', 'audio'],
]) {
  await rm(path.join(destination, name), { recursive: true, force: true });
  await cp(path.join(root, source), path.join(destination, name), { recursive: true });
}
const metadata = JSON.parse(
  await readFile(path.join(destination, 'model/model_metadata.json'), 'utf8'),
);
const actual = createHash('sha256')
  .update(await readFile(path.join(destination, 'model/crop_model.onnx')))
  .digest('hex');
if (actual !== metadata.model_sha256)
  throw new Error('Web model checksum does not match its metadata.');
console.log(`Synchronized real model ${metadata.model_version}, content and offline audio.`);
