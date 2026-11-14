/** Shared local-prototype contracts. No remote database or seeded history. */
export type Language = 'en' | 'kn';
export type CropId = 'tomato' | 'potato' | 'maize';
export type AssessmentType =
  | 'uncertain'
  | 'retake'
  | 'crop_mismatch'
  | 'model_unavailable'
  | 'likely'
  | 'healthy';

export interface ConditionLabel {
  index: number;
  id: string;
  crop_id: CropId;
  source_label: string;
  name_en: string;
  name_kn: string;
}

export interface SourceReference {
  id: string;
  title: string;
  url: string;
  verificationStatus: string;
}
export interface Guidance {
  conditionId: string;
  name: string;
  summary: string;
  symptoms: string[];
  actions: string[];
  prevention: string[];
  caution: string;
  audioAsset: string | null;
  audioPath: string | null;
  contentVersion: string;
  reviewStatus: string;
  translationStatus: string;
  sources: SourceReference[];
}
export interface Prompt {
  key: string;
  title: string;
  message: string;
  audioAsset: string | null;
  audioPath: string | null;
}
export interface ModelStatus {
  ready: boolean;
  validated: boolean;
  name: string;
  version: string;
  bytes: number;
  message: string;
}

export type LeafCoverage = 'NOT_REPORTED' | 'FEW_SPOTS' | 'SOME_SPOTS' | 'MANY_SPOTS';
export interface ReportedSymptoms {
  spreadingQuickly: boolean;
  manyPlantsAffected: boolean;
  wiltingOrDying: boolean;
  leafCoverage: LeafCoverage;
  uncertainAnswers: boolean;
}
export interface ConcernResult {
  level: 'OBSERVE_AND_RECHECK' | 'SEEK_LOCAL_EXPERT';
  reportedSymptoms: ReportedSymptoms;
  ruleVersion: 'prototype-observation-v1';
  agronomistReviewed: false;
}

/** The photo Blob and metadata are stored atomically in one IndexedDB record. */
export interface ObservationRecord {
  id: string;
  createdAt: number;
  cropId: CropId;
  photoBlob: Blob | null;
  resultType: AssessmentType;
  conditionId: string | null;
  score: number | null;
  modelVersion: string;
  inferenceMs: number;
  note: string;
  validated: boolean;
  concern: ConcernResult | null;
}
export interface NewObservation {
  id?: string;
  createdAt?: number;
  cropId: CropId;
  photoBlob?: Blob | null;
  resultType: AssessmentType;
  conditionId?: string | null;
  score?: number | null;
  modelVersion?: string;
  inferenceMs?: number;
  note?: string;
  validated?: boolean;
  concern?: ConcernResult | null;
}
export interface ObservationFilters {
  cropId?: CropId | 'all';
  resultType?: AssessmentType | 'all';
  query?: string;
  since?: number;
  until?: number;
  offset?: number;
  limit?: number;
}

export const CROPS: readonly { id: CropId; nameEn: string; nameKn: string }[] = [
  { id: 'tomato', nameEn: 'Tomato', nameKn: 'ಟೊಮ್ಯಾಟೊ' },
  { id: 'potato', nameEn: 'Potato', nameKn: 'ಆಲೂಗಡ್ಡೆ' },
  { id: 'maize', nameEn: 'Maize', nameKn: 'ಮೆಕ್ಕೆಜೋಳ' },
];

/** Copied from contracts/labels.json and the actual packaged Kannada content. */
export const CONDITIONS: readonly ConditionLabel[] = [
  {
    index: 0,
    id: 'maize_gray_leaf_spot',
    crop_id: 'maize',
    source_label: 'Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot',
    name_en: 'Gray leaf spot',
    name_kn: 'ಬೂದು ಎಲೆ ಚುಕ್ಕೆ',
  },
  {
    index: 1,
    id: 'maize_common_rust',
    crop_id: 'maize',
    source_label: 'Corn_(maize)___Common_rust_',
    name_en: 'Common rust',
    name_kn: 'ಸಾಮಾನ್ಯ ತುಕ್ಕು ರೋಗ',
  },
  {
    index: 2,
    id: 'maize_northern_leaf_blight',
    crop_id: 'maize',
    source_label: 'Corn_(maize)___Northern_Leaf_Blight',
    name_en: 'Northern leaf blight',
    name_kn: 'ಉತ್ತರ ಎಲೆ ಅಂಗಮಾರಿ',
  },
  {
    index: 3,
    id: 'maize_healthy',
    crop_id: 'maize',
    source_label: 'Corn_(maize)___healthy',
    name_en: 'Healthy-looking',
    name_kn: 'ಆರೋಗ್ಯಕರವಾಗಿ ಕಾಣುವ ಎಲೆ',
  },
  {
    index: 4,
    id: 'potato_early_blight',
    crop_id: 'potato',
    source_label: 'Potato___Early_blight',
    name_en: 'Early blight',
    name_kn: 'ಆರಂಭಿಕ ಅಂಗಮಾರಿ',
  },
  {
    index: 5,
    id: 'potato_late_blight',
    crop_id: 'potato',
    source_label: 'Potato___Late_blight',
    name_en: 'Late blight',
    name_kn: 'ತಡವಾದ ಅಂಗಮಾರಿ',
  },
  {
    index: 6,
    id: 'potato_healthy',
    crop_id: 'potato',
    source_label: 'Potato___healthy',
    name_en: 'Healthy-looking',
    name_kn: 'ಆರೋಗ್ಯಕರವಾಗಿ ಕಾಣುವ ಎಲೆ',
  },
  {
    index: 7,
    id: 'tomato_bacterial_spot',
    crop_id: 'tomato',
    source_label: 'Tomato___Bacterial_spot',
    name_en: 'Bacterial spot',
    name_kn: 'ಬ್ಯಾಕ್ಟೀರಿಯಾ ಎಲೆ ಚುಕ್ಕೆ',
  },
  {
    index: 8,
    id: 'tomato_early_blight',
    crop_id: 'tomato',
    source_label: 'Tomato___Early_blight',
    name_en: 'Early blight',
    name_kn: 'ಆರಂಭಿಕ ಅಂಗಮಾರಿ',
  },
  {
    index: 9,
    id: 'tomato_late_blight',
    crop_id: 'tomato',
    source_label: 'Tomato___Late_blight',
    name_en: 'Late blight',
    name_kn: 'ತಡವಾದ ಅಂಗಮಾರಿ',
  },
  {
    index: 10,
    id: 'tomato_leaf_mold',
    crop_id: 'tomato',
    source_label: 'Tomato___Leaf_Mold',
    name_en: 'Leaf mold',
    name_kn: 'ಎಲೆಯ ಶಿಲೀಂಧ್ರ ಕಲೆ',
  },
  {
    index: 11,
    id: 'tomato_septoria_leaf_spot',
    crop_id: 'tomato',
    source_label: 'Tomato___Septoria_leaf_spot',
    name_en: 'Septoria leaf spot',
    name_kn: 'ಸೆಪ್ಟೋರಿಯಾ ಎಲೆ ಚುಕ್ಕೆ',
  },
  {
    index: 12,
    id: 'tomato_spider_mites',
    crop_id: 'tomato',
    source_label: 'Tomato___Spider_mites Two-spotted_spider_mite',
    name_en: 'Spider-mite symptoms',
    name_kn: 'ಎರಡು ಚುಕ್ಕೆ ಜೇಡನುಸಿ',
  },
  {
    index: 13,
    id: 'tomato_target_spot',
    crop_id: 'tomato',
    source_label: 'Tomato___Target_Spot',
    name_en: 'Target spot',
    name_kn: 'ಗುರಿ ಆಕಾರದ ಎಲೆ ಚುಕ್ಕೆ',
  },
  {
    index: 14,
    id: 'tomato_yellow_leaf_curl_virus',
    crop_id: 'tomato',
    source_label: 'Tomato___Tomato_Yellow_Leaf_Curl_Virus',
    name_en: 'Yellow leaf curl virus',
    name_kn: 'ಹಳದಿ ಎಲೆ ಸುರುಳಿ ವೈರಸ್',
  },
  {
    index: 15,
    id: 'tomato_mosaic_virus',
    crop_id: 'tomato',
    source_label: 'Tomato___Tomato_mosaic_virus',
    name_en: 'Mosaic virus',
    name_kn: 'ಮೊಸಾಯಿಕ್ ವೈರಸ್',
  },
  {
    index: 16,
    id: 'tomato_healthy',
    crop_id: 'tomato',
    source_label: 'Tomato___healthy',
    name_en: 'Healthy-looking',
    name_kn: 'ಆರೋಗ್ಯಕರವಾಗಿ ಕಾಣುವ ಎಲೆ',
  },
];
