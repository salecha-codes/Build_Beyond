import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { once } from 'node:events';
import { createPreviewServer } from '../server.mjs';

test('host serves WASM and shell, refuses uploads and keeps non-public files private', async () => {
  const temporary = await mkdtemp(path.join(tmpdir(), 'crop-host-'));
  const directory = path.join(temporary, 'public');
  await mkdir(directory);
  await writeFile(path.join(directory, 'index.html'), '<main>Crop Health</main>');
  await writeFile(path.join(directory, 'runtime.wasm'), Buffer.from([0, 97, 115, 109]));
  await writeFile(path.join(temporary, 'private.txt'), 'TEST PRIVATE MARKER');
  const server = createPreviewServer({ directory });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const base = `http://127.0.0.1:${server.address().port}`;
  try {
    const health = await fetch(base + '/api/health');
    assert.equal(health.status, 200);
    assert.equal((await health.json()).photoUploads, false);
    const wasm = await fetch(base + '/runtime.wasm');
    assert.equal(wasm.headers.get('content-type'), 'application/wasm');
    assert.equal((await wasm.arrayBuffer()).byteLength, 4);
    const navigation = await fetch(base + '/history', { headers: { Accept: 'text/html' } });
    assert.match(await navigation.text(), /Crop Health/);
    const upload = await fetch(base + '/api/scan', {
      method: 'POST',
      body: 'synthetic photo bytes',
    });
    assert.equal(upload.status, 405);
    const traversal = await fetch(base + '/%2e%2e%2fprivate.txt');
    assert.equal(traversal.status, 403);
    assert.doesNotMatch(await traversal.text(), /TEST PRIVATE MARKER/);
  } finally {
    server.closeAllConnections();
    await new Promise((resolve) => server.close(resolve));
    await rm(temporary, { recursive: true });
  }
});

test('subdirectory deployment serves its shell and rejects unrelated paths', async () => {
  const directory = await mkdtemp(path.join(tmpdir(), 'crop-base-'));
  await writeFile(path.join(directory, 'index.html'), 'SUBDIRECTORY SHELL');
  const server = createPreviewServer({ directory, base: '/Build_Beyond/' });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const base = `http://127.0.0.1:${server.address().port}`;
  try {
    assert.equal(await (await fetch(base + '/Build_Beyond/')).text(), 'SUBDIRECTORY SHELL');
    assert.equal((await fetch(base + '/unrelated.html')).status, 404);
    const redirect = await fetch(base + '/', { redirect: 'manual' });
    assert.equal(redirect.headers.get('location'), '/Build_Beyond/');
  } finally {
    server.closeAllConnections();
    await new Promise((resolve) => server.close(resolve));
    await rm(directory, { recursive: true });
  }
});
