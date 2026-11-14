import { CONDITIONS, CROPS } from './types';
import type {
  ConditionLabel,
  ConcernResult,
  CropId,
  Guidance,
  Language,
  Prompt,
  ReportedSymptoms,
  SourceReference,
} from './types';

interface RawCopy {
  name: string;
  summary: string;
  symptoms: string[];
  actions: string[];
  prevention: string[];
  caution: string;
  audio_asset?: string;
  translation_status: string;
}
interface RawPrompt {
  title: string;
  message: string;
  audio_asset?: string;
}
export interface ContentCatalog {
  schema_version: number;
  content_version: string;
  review_notice: string;
  conditions: Record<
    string,
    {
      review_status: string;
      chemical_treatment_enabled: boolean;
      sources: { id: string; title: string; url: string; verification_status: string }[];
      translations: Record<Language, RawCopy>;
    }
  >;
  prompts: Record<string, Record<Language, RawPrompt>>;
  ui_strings: Record<Language, Record<string, string>>;
}

const env = (import.meta as ImportMeta & { env?: { BASE_URL?: string } }).env;
const defaultBase = env?.BASE_URL ?? '/';
let activeBase = defaultBase;
let catalog: ContentCatalog | null = null;
let pending: Promise<ContentCatalog> | null = null;
let pendingBase: string | null = null;

/** Resolve only packaged assets, respecting Vite's BASE_URL (including subpath deployments). */
export function assetUrl(path: string, baseUrl = activeBase): string {
  const normalized = path.replace(/^\/+/, '');
  if (/^[a-z]+:/i.test(normalized) || normalized.split('/').includes('..')) {
    throw new Error('Expected a packaged asset path.');
  }
  const relative = normalized.startsWith('assets/') ? normalized : `assets/${normalized}`;
  return `${baseUrl.endsWith('/') ? baseUrl : `${baseUrl}/`}${relative}`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
function validateCatalog(value: unknown): ContentCatalog {
  if (
    !isRecord(value) ||
    value.schema_version !== 1 ||
    typeof value.content_version !== 'string' ||
    !isRecord(value.conditions) ||
    !isRecord(value.prompts) ||
    !isRecord(value.ui_strings)
  ) {
    throw new Error('The packaged guidance catalog is incompatible.');
  }
  for (const label of CONDITIONS) {
    const item = value.conditions[label.id];
    if (
      !isRecord(item) ||
      !isRecord(item.translations) ||
      !isRecord(item.translations.en) ||
      !isRecord(item.translations.kn)
    )
      throw new Error(`Missing bilingual guidance: ${label.id}`);
    for (const lang of ['en', 'kn']) {
      const copy = item.translations[lang];
      if (
        !isRecord(copy) ||
        typeof copy.name !== 'string' ||
        typeof copy.summary !== 'string' ||
        !Array.isArray(copy.actions) ||
        !Array.isArray(copy.symptoms) ||
        !Array.isArray(copy.prevention)
      ) {
        throw new Error(`Invalid packaged guidance: ${label.id}/${lang}`);
      }
    }
  }
  return value as unknown as ContentCatalog;
}

/** Call once at startup. The resolved URL is local/static, never an advisory API. */
export async function loadCatalog(baseUrl = defaultBase): Promise<ContentCatalog> {
  if (catalog && activeBase === baseUrl) return catalog;
  if (pending && pendingBase === baseUrl) return pending;
  activeBase = baseUrl;
  pendingBase = baseUrl;
  pending = (async () => {
    const response = await fetch(assetUrl('content/catalog.json', baseUrl), {
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
    });
    if (!response.ok) throw new Error(`Offline guidance could not load (${response.status}).`);
    const result = validateCatalog(await response.json());
    catalog = result;
    return result;
  })();
  try {
    return await pending;
  } finally {
    pending = null;
    pendingBase = null;
  }
}
export const initContent = loadCatalog;
export function isCatalogLoaded(): boolean {
  return catalog !== null;
}
export function getConditionLabel(id: string): ConditionLabel | undefined {
  return CONDITIONS.find((item) => item.id === id);
}
export function conditionName(id: string, language: Language): string {
  const label = getConditionLabel(id);
  return label ? (language === 'kn' ? label.name_kn : label.name_en) : id.replaceAll('_', ' ');
}
export function cropName(id: CropId, language: Language): string {
  const crop = CROPS.find((item) => item.id === id)!;
  return language === 'kn' ? crop.nameKn : crop.nameEn;
}

export function getGuidance(conditionId: string, language: Language): Guidance | null {
  const item = catalog?.conditions[conditionId];
  if (!item || !catalog) return null;
  const copy = item.translations[language] ?? item.translations.en;
  const path = copy.audio_asset || null;
  return {
    conditionId,
    name: copy.name,
    summary: copy.summary,
    symptoms: [...copy.symptoms],
    actions: [...copy.actions],
    prevention: [...copy.prevention],
    caution: copy.caution,
    audioAsset: path ? assetUrl(path) : null,
    audioPath: path,
    contentVersion: catalog.content_version,
    reviewStatus: item.review_status,
    translationStatus: copy.translation_status,
    sources: item.sources.map(
      (source): SourceReference => ({
        id: source.id,
        title: source.title,
        url: source.url,
        verificationStatus: source.verification_status,
      }),
    ),
  };
}

const fallback: Record<Language, RawPrompt> = {
  en: {
    title: 'Guidance is not ready',
    message:
      'Take a clear photo of one leaf in daylight. This prototype cannot confirm a disease. Ask a local agriculture adviser before choosing treatment.',
  },
  kn: {
    title: 'ಮಾರ್ಗದರ್ಶನ ಸಿದ್ಧವಾಗಿಲ್ಲ',
    message:
      'ಹಗಲಿನ ಬೆಳಕಿನಲ್ಲಿ ಒಂದು ಎಲೆಯ ಸ್ಪಷ್ಟ ಚಿತ್ರ ತೆಗೆದುಕೊಳ್ಳಿ. ಈ ಮಾದರಿ ರೋಗವನ್ನು ಖಚಿತಪಡಿಸುವುದಿಲ್ಲ. ಚಿಕಿತ್ಸೆ ಆಯ್ಕೆ ಮಾಡುವ ಮೊದಲು ಸ್ಥಳೀಯ ಕೃಷಿ ಸಲಹೆಗಾರರನ್ನು ಸಂಪರ್ಕಿಸಿ.',
  },
};
export function getPrompt(key: string, language: Language): Prompt {
  const translations = catalog?.prompts[key] ?? catalog?.prompts.uncertain;
  const copy = translations?.[language] ?? translations?.en ?? fallback[language];
  const path = copy.audio_asset || null;
  return {
    key,
    title: copy.title,
    message: copy.message,
    audioAsset: path ? assetUrl(path) : null,
    audioPath: path,
  };
}
export function text(key: string, language: Language): string {
  return catalog?.ui_strings[language]?.[key] ?? catalog?.ui_strings.en[key] ?? key;
}
export const t = text;

/** Same observation-based rule as Android. It is not an image-derived severity grade. */
export function summarizeConcern(input: Partial<ReportedSymptoms>): ConcernResult {
  const reportedSymptoms: ReportedSymptoms = {
    spreadingQuickly: input.spreadingQuickly ?? false,
    manyPlantsAffected: input.manyPlantsAffected ?? false,
    wiltingOrDying: input.wiltingOrDying ?? false,
    leafCoverage: input.leafCoverage ?? 'NOT_REPORTED',
    uncertainAnswers: input.uncertainAnswers ?? false,
  };
  const needsExpert =
    reportedSymptoms.spreadingQuickly ||
    reportedSymptoms.manyPlantsAffected ||
    reportedSymptoms.wiltingOrDying ||
    reportedSymptoms.leafCoverage === 'MANY_SPOTS' ||
    reportedSymptoms.leafCoverage === 'NOT_REPORTED' ||
    reportedSymptoms.uncertainAnswers;
  return {
    level: needsExpert ? 'SEEK_LOCAL_EXPERT' : 'OBSERVE_AND_RECHECK',
    reportedSymptoms,
    ruleVersion: 'prototype-observation-v1',
    agronomistReviewed: false,
  };
}
