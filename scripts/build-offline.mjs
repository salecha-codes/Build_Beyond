import { createHash } from 'node:crypto';
import { readdir, readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const directory = fileURLToPath(new URL('../frontend/dist/', import.meta.url));
const entries = [];
async function walk(folder) {
  for (const entry of await readdir(folder, { withFileTypes: true })) {
    const filename = path.join(folder, entry.name);
    if (entry.isDirectory()) await walk(filename);
    else if (
      !['sw.js', 'offline-manifest.json'].includes(entry.name) &&
      !entry.name.endsWith('.map')
    ) {
      entries.push(path.relative(directory, filename).split(path.sep).join('/'));
    }
  }
}
await walk(directory);
entries.sort();
const hash = createHash('sha256');
for (const entry of entries) {
  hash.update(entry);
  hash.update(await readFile(path.join(directory, entry)));
}
const version = hash.digest('hex').slice(0, 16);
const template = await readFile(new URL('./service-worker.template.js', import.meta.url), 'utf8');
await writeFile(
  path.join(directory, 'sw.js'),
  template
    .replace('__CACHE_VERSION__', version)
    .replace('__PRECACHE_LIST__', JSON.stringify(entries)),
);
await writeFile(
  path.join(directory, 'offline-manifest.json'),
  JSON.stringify({ version, files: entries }, null, 2) + '\n',
);
console.log(`Offline cache ${version}: ${entries.length} local files.`);
