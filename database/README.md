# Local data storage

This prototype has **two local implementations**, not a central database service:

| Runtime | Persistence | Stored information |
|---|---|---|
| Native Android | Room / SQLite (`crop-observations.db`) and app-private image files | Saved observations and their photo paths |
| Browser preview | IndexedDB (`debuggers-crop-health`, version 1) | Saved observation metadata and the actual photo `Blob` in one atomic record |
 | Browser preference | `localStorage` keys `crophealth.language` and `crophealth.onboarded` | `en`, `kn` and `hi` interface preference and first-run onboarding status |

There is no remote observation API, shared cloud database, authentication service, or automatic Android/browser synchronization. The web preview and Android APK keep separate histories. No mock or demonstration rows are inserted. An empty history means no observation has been saved in that installation/origin.

## Android schema

[`android/schema.sql`](android/schema.sql) records the actual generated Room schema for database version 2. It includes Room's identity table/hash. The source of truth is:

- `android/app/src/main/java/com/debuggers/crophealth/data/ObservationStore.kt`
- generated `android/app/build/generated/ksp/debug/kotlin/com/debuggers/crophealth/data/CropDatabase_Impl.kt`

The table stores ID/time/crop, private image path, outcome, condition/model score where available, model version, inference duration, note and validated flag. The image bytes live in app-private storage. Native deletion removes the observation and deletes an owned image only after no remaining observation references it. The schema is documentation of the real local database, not a proposed server schema or a migration to apply to a backend.

Version 2 adds nullable `reportedSymptomsJson`. The non-destructive 1→2 migration
preserves existing scans. Completed advisory-question answers are saved here;
old scans retain null/unknown answers. Revising a care questionnaire updates that
record without replacing its photo or disease-model output. The current advisory
model recomputes care and urgency from those saved observations.

## Browser schema

[`browser/schema.json`](browser/schema.json) records the actual store and indexes created by `frontend/src/lib/storage.ts`. `observations` has primary key `id` and nonunique indexes on `createdAt`, `cropId` and `resultType`.

A saved record contains:

- `id`, `createdAt` (epoch milliseconds), `cropId`;
- `photoBlob` (`Blob` or null), not a temporary object URL;
- `resultType`, optional `conditionId`/`score`;
- `modelVersion`, `inferenceMs`, `note`, `validated`;
- optional user-reported concern answers and rule version.

`saveObservation` uses `add`, so a duplicate ID cannot silently overwrite an existing observation. Metadata and image are stored in one IndexedDB transaction. Deleting a record removes its stored Blob with it. The UI must revoke any temporary `URL.createObjectURL` when its corresponding view is disposed; revoking that URL does not delete the saved Blob.

`listObservations` supports crop/outcome/search/time filters and pagination, and returns newest first. `deleteObservation` deletes one selected ID; `clearObservations` is an explicit clear-all operation. Language preference is stored independently. `HISTORY_CHANGED_EVENT` notifies the current tab after successful mutations.

IndexedDB is scoped to the browser origin. Another device/browser, another preview origin, private mode or cleared site data does not share this history. Storage permission/quota errors are surfaced; there is no in-memory fallback presented as durable storage.

## Content and inference assets

The parent asset preparation script copies the **actual** Android content and speech assets to `frontend/public/assets/`. Content helpers resolve paths relative to Vite `BASE_URL`:

- `assets/content/catalog.json` — 17 English/Kannada/Hindi condition records and prompts;
- `assets/content/advisory_model.json` — the separate trilingual care-and-urgency knowledge model;
- `assets/content/advisory_receipt.json` and `advisory_audio_manifest.json` — knowledge and new narration provenance;
- `assets/content/audio_manifest.json` — 90 speech clip hashes/durations;
- `assets/audio/en/*.ogg`, `assets/audio/kn/*.ogg` — generated local speech.

These are versioned read-only files, not mutable database records or a live advisory service. Content remains general observation guidance; expert review and Kannada pronunciation review are pending. The model's validation status must accompany saved results. A score from an unvalidated model is not a confirmed diagnosis.

In a browser, loading local/static assets can require an initial download from the preview origin. Offline reload/playback depends on the browser cache/service-worker implementation and must be tested; static URLs alone do not establish offline readiness. A camera requires a secure context (HTTPS or localhost) and the user's browser permission.

## Checks

The browser QA workflow should save a real uploaded photo, reload the page, reopen the same record, filter it, and delete exactly that record. It should verify the photo bytes remain available after reload, Kannada guidance/audio loads, missing/not-sure concern answers never become a low-concern diagnosis, and no seed records appear. Android and browser checks must be reported independently; browser/emulator timings are not phone benchmarks.
