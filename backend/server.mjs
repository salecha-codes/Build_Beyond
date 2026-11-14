import http from 'node:http';
import { createReadStream } from 'node:fs';
import { readFile, stat } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const projectRoot = fileURLToPath(new URL('../', import.meta.url));
const mime = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.wasm': 'application/wasm',
  '.onnx': 'application/octet-stream',
  '.ogg': 'audio/ogg',
  '.wav': 'audio/wav',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.webmanifest': 'application/manifest+json',
  '.woff2': 'font/woff2',
  '.ico': 'image/x-icon',
};

export function createPreviewServer({
  directory = path.join(projectRoot, 'frontend/dist'),
  base = '/',
} = {}) {
  const root = path.resolve(directory);
  const prefix = '/' + base.split('/').filter(Boolean).join('/') + (base === '/' ? '' : '/');
  return http.createServer(async (request, response) => {
    response.setHeader('X-Content-Type-Options', 'nosniff');
    response.setHeader('Referrer-Policy', 'strict-origin-when-cross-origin');
    response.setHeader('Permissions-Policy', 'camera=(self), microphone=(), geolocation=()');
    try {
      if (!['GET', 'HEAD'].includes(request.method)) {
        response.writeHead(405, { Allow: 'GET, HEAD' }).end('Method not allowed');
        return;
      }
      const url = new URL(request.url, 'http://localhost');
      const decoded = decodeURIComponent(url.pathname);
      if (decoded.includes('\0')) {
        response.writeHead(400).end('Invalid path');
        return;
      }
      if (prefix !== '/' && decoded === '/') {
        response.writeHead(302, { Location: prefix }).end();
        return;
      }
      if (!decoded.startsWith(prefix)) {
        response.writeHead(404).end('Not found');
        return;
      }
      const localPath = '/' + decoded.slice(prefix.length);
      if (localPath === '/api/health') {
        response.writeHead(200, {
          'Content-Type': 'application/json',
          'Cache-Control': 'no-store',
        });
        response.end(
          JSON.stringify({
            status: 'ok',
            app: 'Offline Crop Health',
            version: '0.2.0-review2',
            inference: 'browser-local',
            photoUploads: false,
            database: 'device-local',
          }),
        );
        return;
      }
      let filename = path.resolve(root, '.' + localPath);
      if (filename !== root && !filename.startsWith(root + path.sep)) {
        response.writeHead(403).end('Forbidden');
        return;
      }
      let info;
      try {
        info = await stat(filename);
      } catch {
        /* SPA navigation can use index.html. */
      }
      if (!info?.isFile()) {
        if (!path.extname(localPath) && request.headers.accept?.includes('text/html')) {
          filename = path.join(root, 'index.html');
          info = await stat(filename);
        } else if (localPath === '/') {
          filename = path.join(root, 'index.html');
          info = await stat(filename);
        } else {
          response.writeHead(404).end('Not found');
          return;
        }
      }
      response.writeHead(200, {
        'Content-Type': mime[path.extname(filename)] || 'application/octet-stream',
        'Content-Length': info.size,
        'Cache-Control': /\/(sw\.js|index\.html)$/.test(filename)
          ? 'no-cache'
          : 'public, max-age=0, must-revalidate',
      });
      if (request.method === 'HEAD') {
        response.end();
        return;
      }
      const stream = createReadStream(filename);
      stream.on('error', () => response.destroy());
      stream.pipe(response);
    } catch (error) {
      if (!response.headersSent) response.writeHead(error instanceof URIError ? 400 : 500);
      response.end('Preview request could not be completed');
    }
  });
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const port = Number(process.env.PORT || 3000);
  const directory = path.resolve(projectRoot, process.env.STATIC_DIR || 'frontend/dist');
  await readFile(path.join(directory, 'index.html'));
  createPreviewServer({ directory, base: process.env.BASE_PATH || '/' }).listen(
    port,
    '0.0.0.0',
    () => {
      console.log(`Crop Health preview listening on http://0.0.0.0:${port}`);
    },
  );
}
