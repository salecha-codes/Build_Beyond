import type {
  AssessmentType,
  CropId,
  Language,
  NewObservation,
  ObservationFilters,
  ObservationRecord,
} from './types';
import { CONDITIONS, CROPS } from './types';

const DB_NAME = 'debuggers-crop-health';
const DB_VERSION = 1;
const STORE = 'observations';
const LANGUAGE_KEY = 'crophealth.language';
export const HISTORY_CHANGED_EVENT = 'crophealth:observations-changed';
let opening: Promise<IDBDatabase> | null = null;

export class LocalStorageError extends Error {
  constructor(
    message: string,
    readonly original?: unknown,
  ) {
    super(message);
    this.name = 'LocalStorageError';
  }
}
function storageError(error: unknown): LocalStorageError {
  if (error instanceof LocalStorageError) return error;
  const name = error instanceof DOMException ? error.name : '';
  if (name === 'QuotaExceededError')
    return new LocalStorageError(
      'Device storage is full. Delete older observations and try again.',
      error,
    );
  return new LocalStorageError(
    'Local history is unavailable. Check browser storage permissions and try again.',
    error,
  );
}
function changed(): void {
  if (typeof window !== 'undefined') window.dispatchEvent(new Event(HISTORY_CHANGED_EVENT));
}
function database(): Promise<IDBDatabase> {
  if (opening) return opening;
  opening = new Promise((resolve, reject) => {
    if (typeof indexedDB === 'undefined') {
      reject(new LocalStorageError('This browser does not provide persistent local history.'));
      return;
    }
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      const store = db.objectStoreNames.contains(STORE)
        ? request.transaction!.objectStore(STORE)
        : db.createObjectStore(STORE, { keyPath: 'id' });
      for (const index of ['createdAt', 'cropId', 'resultType']) {
        if (!store.indexNames.contains(index)) store.createIndex(index, index, { unique: false });
      }
    };
    request.onerror = () => {
      opening = null;
      reject(storageError(request.error));
    };
    request.onblocked = () => {
      opening = null;
      reject(new LocalStorageError('Close other tabs using this app so local history can update.'));
    };
    request.onsuccess = () => {
      const db = request.result;
      db.onversionchange = () => {
        db.close();
        opening = null;
      };
      resolve(db);
    };
  });
  return opening;
}
function requestValue<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(storageError(request.error));
  });
}
function complete(transaction: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve();
    transaction.onabort = () => reject(storageError(transaction.error));
    transaction.onerror = () => reject(storageError(transaction.error));
  });
}
function freshId(): string {
  return (
    globalThis.crypto?.randomUUID?.() ??
    `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
  );
}
const crops: CropId[] = ['tomato', 'potato', 'maize'];
const results: AssessmentType[] = [
  'uncertain',
  'retake',
  'crop_mismatch',
  'model_unavailable',
  'likely',
  'healthy',
];

/** No seed/mock rows. New observations always originate from an explicit save action. */
export async function saveObservation(input: NewObservation): Promise<ObservationRecord> {
  if (!crops.includes(input.cropId) || !results.includes(input.resultType))
    throw new LocalStorageError('The observation has an unsupported crop or outcome.');
  if (input.score != null && (!Number.isFinite(input.score) || input.score < 0 || input.score > 1))
    throw new LocalStorageError('The observation contains an invalid model score.');
  if (input.photoBlob != null && !(input.photoBlob instanceof Blob))
    throw new LocalStorageError('The observation photo is not a valid local image.');
  if (input.inferenceMs != null && (!Number.isFinite(input.inferenceMs) || input.inferenceMs < 0))
    throw new LocalStorageError('The observation contains an invalid inference duration.');
  if (input.id != null && !input.id.trim())
    throw new LocalStorageError('The observation ID is empty.');
  const createdAt = input.createdAt ?? Date.now();
  if (!Number.isFinite(createdAt) || createdAt < 0)
    throw new LocalStorageError('The observation date is invalid.');
  const record: ObservationRecord = {
    id: input.id ?? freshId(),
    createdAt,
    cropId: input.cropId,
    photoBlob: input.photoBlob ?? null,
    resultType: input.resultType,
    conditionId: input.conditionId ?? null,
    score: input.score ?? null,
    modelVersion: input.modelVersion || 'unavailable',
    inferenceMs: Math.max(0, input.inferenceMs ?? 0),
    note: input.note ?? '',
    validated: input.validated ?? false,
    concern: input.concern ?? null,
  };
  const db = await database();
  try {
    const tx = db.transaction(STORE, 'readwrite');
    const finished = complete(tx);
    // add, not put: accidental duplicate IDs never silently overwrite an existing observation.
    tx.objectStore(STORE).add(record);
    await finished;
    changed();
    return record;
  } catch (error) {
    throw storageError(error);
  }
}

export async function getObservation(id: string): Promise<ObservationRecord | undefined> {
  const db = await database();
  return requestValue(db.transaction(STORE, 'readonly').objectStore(STORE).get(id));
}
export async function listObservations(
  filters: ObservationFilters = {},
): Promise<ObservationRecord[]> {
  const db = await database();
  const all = await requestValue<ObservationRecord[]>(
    db.transaction(STORE, 'readonly').objectStore(STORE).getAll(),
  );
  const query = filters.query?.trim().toLocaleLowerCase();
  const selected = all
    .filter((row) => {
      const label = CONDITIONS.find((item) => item.id === row.conditionId);
      const crop = CROPS.find((item) => item.id === row.cropId);
      const searchable =
        `${row.cropId} ${crop?.nameEn ?? ''} ${crop?.nameKn ?? ''} ${row.conditionId ?? ''} ${label?.name_en ?? ''} ${label?.name_kn ?? ''} ${row.resultType} ${row.note}`
          .replaceAll('_', ' ')
          .toLocaleLowerCase();
      return (
        (!filters.cropId || filters.cropId === 'all' || row.cropId === filters.cropId) &&
        (!filters.resultType ||
          filters.resultType === 'all' ||
          row.resultType === filters.resultType) &&
        (filters.since == null || row.createdAt >= filters.since) &&
        (filters.until == null || row.createdAt <= filters.until) &&
        (!query || searchable.includes(query))
      );
    })
    .sort((a, b) => b.createdAt - a.createdAt || a.id.localeCompare(b.id));
  const offset = Math.max(0, Math.floor(filters.offset ?? 0));
  const limit = filters.limit == null ? selected.length : Math.max(0, Math.floor(filters.limit));
  return selected.slice(offset, offset + limit);
}
export async function deleteObservation(id: string): Promise<void> {
  const db = await database();
  const tx = db.transaction(STORE, 'readwrite');
  const finished = complete(tx);
  tx.objectStore(STORE).delete(id);
  await finished;
  changed();
}
export async function clearObservations(): Promise<void> {
  const db = await database();
  const tx = db.transaction(STORE, 'readwrite');
  const finished = complete(tx);
  tx.objectStore(STORE).clear();
  await finished;
  changed();
}
export function getLanguage(): Language {
  try {
    return globalThis.localStorage?.getItem(LANGUAGE_KEY) === 'kn' ? 'kn' : 'en';
  } catch {
    return 'en';
  }
}
export function setLanguage(language: Language): void {
  if (language !== 'en' && language !== 'kn')
    throw new LocalStorageError('Unsupported interface language.');
  try {
    globalThis.localStorage.setItem(LANGUAGE_KEY, language);
  } catch (error) {
    throw new LocalStorageError('Language preference could not be saved on this browser.', error);
  }
}
/** Useful for controlled tests; it does not delete stored observations. */
export async function closeHistoryDatabase(): Promise<void> {
  if (opening) {
    (await opening).close();
    opening = null;
  }
}
