import { cp, mkdir, readFile, rm } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = fileURLToPath(new URL('../', import.meta.url));
const destination = path.join(root, 'frontend/public/assets');
await mkdir(destination, { recursive: true });
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
