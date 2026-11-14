# Preview backend

`server.mjs` serves the compiled React preview and exposes `GET /api/health`. It uses Node.js built-ins, accepts GET/HEAD only, and has no photo-upload, inference, account, or cloud-storage endpoint.

The crop model runs on the user's device. Browser observations are stored in IndexedDB; Android observations use Room/SQLite. A server database is unnecessary for these offline flows.

From the repository root:

```sh
npm ci
npm run build
npm start
```

The server listens on `0.0.0.0:3000`. `PORT` changes the listening port. `STATIC_DIR` changes the public build directory; its default is `frontend/dist`. `BASE_PATH` supports a deployed subdirectory and must match the frontend's build-time `VITE_BASE_PATH`. Only the compiled public directory is served; repository/training files are outside that directory.

Static hosting can serve `frontend/dist` directly without this Node backend. The browser app does not depend on `/api/health`, so offline use also works on a static host.
