import { assetUrl } from './content';
import { CONDITIONS } from './types';
import type { Language } from './types';
import type { AdvisoryResult, Severity } from './advisory';

export interface TreatmentOption { id: string; title: string; when: string; steps: string[]; limits: string; source_ids: string[] }
export interface CareStage { title: string; actions: string[] }
export interface CareProtocolCopy {
  goal: string;
  confirm_checks: string[];
  look_alikes: string[];
  treatment_options: TreatmentOption[];
  avoid: string[];
  recovery_signs: string[];
  failure_signs: string[];
  follow_up: { when: string; check: string; action: string }[];
  stage_plans: Record<'MILD' | 'MODERATE' | 'SEVERE', CareStage>;
  expert_questions: string[];
}
export interface CareProtocols {
  schema_version: 1;
  version: string;
  agronomist_reviewed: false;
  field_validated: false;
  sources: { id: string; title: string; url: string; verification_status: string }[];
  protocols: Record<string, { crop_id: string; source_ids: string[]; translations: Record<Language, CareProtocolCopy> }>;
}
export interface CarePlan {
  conditionId: string;
  modelVersion: string;
  copy: CareProtocolCopy;
  stage: CareStage | null;
  severity: Severity;
  sourceIds: string[];
}
function strings(value: unknown): value is string[] {
  return Array.isArray(value) && value.length > 0 && value.every(x => typeof x === 'string' && x.trim());
}
export function validateCareProtocols(value: unknown): CareProtocols {
  const m = value as CareProtocols;
  if (!m || m.schema_version !== 1 || m.agronomist_reviewed !== false || m.field_validated !== false ||
      typeof m.version !== 'string' || !m.version.trim() || !m.protocols || !Array.isArray(m.sources)) throw new Error('The packaged treatment model is incompatible.');
  if (Object.keys(m.protocols).length !== CONDITIONS.length) throw new Error('Treatment categories do not match the disease model.');
  const ids = new Set(m.sources.map(s => s.id));
  if (ids.size !== m.sources.length || !m.sources.every(s => s.id && s.title && /^https:\/\//.test(s.url) && s.verification_status)) throw new Error('Invalid treatment references.');
  for (const label of CONDITIONS) {
    const p = m.protocols[label.id];
    if (!p || p.crop_id !== label.crop_id || !strings(p.source_ids) || !p.source_ids.every(id => ids.has(id))) throw new Error(`Missing treatment protocol: ${label.id}`);
    for (const lang of ['en', 'kn', 'hi'] as const) {
      const c = p.translations?.[lang];
      if (!c || typeof c.goal !== 'string' || !c.goal.trim() ||
          !['confirm_checks', 'look_alikes', 'avoid', 'recovery_signs', 'failure_signs', 'expert_questions'].every(k => strings(c[k as keyof CareProtocolCopy])) ||
          !Array.isArray(c.treatment_options) || !c.treatment_options.length || !c.treatment_options.every(t => t.id && t.title && t.when && strings(t.steps) && t.limits && Array.isArray(t.source_ids) && t.source_ids.every(id => ids.has(id))) ||
          !Array.isArray(c.follow_up) || !c.follow_up.length || !c.follow_up.every(f => f.when && f.check && f.action) ||
          !['MILD', 'MODERATE', 'SEVERE'].every(k => { const s = c.stage_plans?.[k as keyof typeof c.stage_plans]; return s?.title && strings(s.actions); })) throw new Error(`Incomplete treatment protocol: ${label.id}/${lang}`);
    }
  }
  return m;
}
export async function loadCareProtocols(): Promise<CareProtocols> {
  const response = await fetch(assetUrl('content/care_protocols.json'), { credentials: 'same-origin' });
  if (!response.ok) throw new Error(`Offline treatment model could not load (${response.status}).`);
  return validateCareProtocols(await response.json());
}
/** A named, supported condition is required; a score is never a treatment input. */
export function buildCarePlan(model: CareProtocols, conditionId: string | null, advisory: AdvisoryResult, language: Language): CarePlan | null {
  if (!conditionId || (!advisory.profile && !(conditionId.endsWith('_healthy') && advisory.reasonCodes.includes('healthy_conflict')))) return null;
  const profile = model.protocols[conditionId];
  if (!profile) return null;
  const copy = profile.translations[language];
  const stage = advisory.severity === 'UNKNOWN' || advisory.severity === 'NONE' ? null : copy.stage_plans[advisory.severity];
  return { conditionId, modelVersion: model.version, copy, stage, severity: advisory.severity, sourceIds: [...new Set([...profile.source_ids, ...copy.treatment_options.flatMap(option => option.source_ids)])] };
}
const COPY = {
  title: ['Treatment & recovery plan', 'ಚಿಕಿತ್ಸೆ ಮತ್ತು ಚೇತರಿಕೆ ಯೋಜನೆ', 'उपचार और सुधार की योजना'],
  library: ['Care library', 'ಆರೈಕೆ ಮಾಹಿತಿ', 'देखभाल पुस्तकालय'],
  libraryHint: ['Choose a condition, answer six questions, then review its treatment and recovery plan. A library choice is not a diagnosis.', 'ಸ್ಥಿತಿ ಆಯ್ಕೆಮಾಡಿ, ಆರು ಪ್ರಶ್ನೆಗಳಿಗೆ ಉತ್ತರಿಸಿ, ನಂತರ ಚಿಕಿತ್ಸೆಯ ಮತ್ತು ಚೇತರಿಕೆಯ ಯೋಜನೆ ನೋಡಿ. ಗ್ರಂಥಾಲಯದ ಆಯ್ಕೆ ರೋಗನಿರ್ಣಯವಲ್ಲ.', 'स्थिति चुनें, छह सवालों के जवाब दें, फिर उपचार और सुधार योजना देखें। पुस्तकालय में चयन रोग की पुष्टि नहीं है।'],
  selected: ['Selected by you from the care library. This is not a diagnosis.', 'ಆರೈಕೆ ಮಾಹಿತಿಯಿಂದ ನೀವು ಆಯ್ದದ್ದು. ಇದು ರೋಗನಿರ್ಣಯವಲ್ಲ.', 'देखभाल पुस्तकालय से आपने चुना है। यह रोग का निदान नहीं है।'],
  search: ['Search condition or crop', 'ರೋಗ ಅಥವಾ ಬೆಳೆ ಹುಡುಕಿ', 'रोग या फसल खोजें'],
  all: ['All crops', 'ಎಲ್ಲ ಬೆಳೆಗಳು', 'सभी फसलें'],
  goal: ['What treatment can achieve', 'ಚಿಕಿತ್ಸೆಯಿಂದ ಸಾಧ್ಯವಾಗುವುದು', 'उपचार से क्या संभव है'],
  stage: ['Your next steps', 'ನಿಮ್ಮ ಮುಂದಿನ ಕ್ರಮಗಳು', 'आपके अगले कदम'],
  routine: ['No visible leaf damage was reported. Use the routine health and prevention steps below, and reassess if symptoms appear.', 'ಕಾಣುವ ಎಲೆ ಹಾನಿ ತಿಳಿಸಿಲ್ಲ. ಕೆಳಗಿನ ಸಾಮಾನ್ಯ ಆರೋಗ್ಯ ಮತ್ತು ತಡೆ ಕ್ರಮ ಅನುಸರಿಸಿ; ಲಕ್ಷಣ ಕಂಡರೆ ಮತ್ತೆ ಪರಿಶೀಲಿಸಿ.', 'पत्ती पर दिखने वाला नुकसान नहीं बताया गया। नीचे सामान्य देखभाल और बचाव के कदम अपनाएँ; लक्षण आएँ तो फिर जाँचें।'],
  unknown: ['Answer the damage questions to choose the appropriate care intensity. Until then, use these steps as conditional information.', 'ಸೂಕ್ತ ಆರೈಕೆ ಆಯ್ಕೆ ಮಾಡಲು ಹಾನಿಯ ಪ್ರಶ್ನೆಗಳಿಗೆ ಉತ್ತರಿಸಿ. ಅಲ್ಲಿವರೆಗೆ ಈ ಕ್ರಮಗಳನ್ನು ಷರತ್ತುಬದ್ಧ ಮಾಹಿತಿಯಾಗಿ ಬಳಸಿ.', 'देखभाल का स्तर चुनने के लिए नुकसान के प्रश्नों के उत्तर दें। तब तक इन कदमों को शर्त के साथ दी गई जानकारी मानें।'],
  checks: ['Check before treating', 'ಚಿಕಿತ್ಸೆಗೆ ಮೊದಲು ಪರಿಶೀಲಿಸಿ', 'उपचार से पहले जाँचें'],
  similar: ['Other causes to rule out', 'ಹೊರಗಿಡಬೇಕಾದ ಇತರ ಕಾರಣಗಳು', 'मिलते-जुलते दूसरे कारण'],
  options: ['Treatment options & how to use them', 'ಚಿಕಿತ್ಸೆ ಆಯ್ಕೆಗಳು ಮತ್ತು ಬಳಕೆ', 'उपचार के विकल्प और तरीके'],
  when: ['When this option helps', 'ಈ ಆಯ್ಕೆ ನೆರವಾಗುವ ಸಂದರ್ಭ', 'यह विकल्प कब मदद करता है'],
  limits: ['Limits & precautions', 'ಮಿತಿಗಳು ಮತ್ತು ಮುನ್ನೆಚ್ಚರಿಕೆ', 'सीमाएँ और सावधानियाँ'],
  avoid: ['Avoid these mistakes', 'ಈ ತಪ್ಪುಗಳನ್ನು ತಪ್ಪಿಸಿ', 'इन गलतियों से बचें'],
  improvement: ['Signs management is helping', 'ನಿರ್ವಹಣೆ ನೆರವಾಗುವ ಲಕ್ಷಣಗಳು', 'प्रबंधन से लाभ के संकेत'],
  worsening: ['Signs the plan needs review', 'ಯೋಜನೆ ಮರುಪರಿಶೀಲನೆ ಬೇಕಾದ ಲಕ್ಷಣಗಳು', 'योजना की समीक्षा के संकेत'],
  followup: ['Follow-up checkpoints', 'ಮುಂದಿನ ಪರಿಶೀಲನೆಗಳು', 'आगे की जाँच'],
  expert: ['Questions for your crop adviser', 'ಕೃಷಿ ಸಲಹೆಗಾರರಿಗೆ ಕೇಳಬೇಕಾದ ಪ್ರಶ್ನೆಗಳು', 'कृषि सलाहकार से पूछें'],
  refs: ['Sources & verification status', 'ಮೂಲಗಳು ಮತ್ತು ಪರಿಶೀಲನೆ ಸ್ಥಿತಿ', 'स्रोत और सत्यापन स्थिति'],
  notice: ['Conditional care information. Product registration, crop labels and local expert review determine which treatments are appropriate. Observation checkpoints are not pesticide application intervals or promised recovery dates.', 'ಷರತ್ತುಬದ್ಧ ಆರೈಕೆ ಮಾಹಿತಿ. ಉತ್ಪನ್ನ ನೋಂದಣಿ, ಬೆಳೆ ಲೇಬಲ್ ಮತ್ತು ಸ್ಥಳೀಯ ತಜ್ಞರ ಸಲಹೆ ಸೂಕ್ತ ಚಿಕಿತ್ಸೆಯನ್ನು ನಿರ್ಧರಿಸುತ್ತವೆ. ಪರಿಶೀಲನೆ ಸಮಯ ಸಿಂಪಡಣೆ ಅಂತರ ಅಥವಾ ಖಚಿತ ಚೇತರಿಕೆ ದಿನಾಂಕವಲ್ಲ.', 'शर्त के साथ देखभाल की जानकारी। उत्पाद पंजीकरण, फसल का लेबल और स्थानीय विशेषज्ञ की समीक्षा से उचित उपचार तय होता है। जाँच के समय छिड़काव के अंतराल या सुधार की गारंटी नहीं हैं।'],
  retry: ['Retry loading treatment', 'ಚಿಕಿತ್ಸೆ ಮಾಹಿತಿ ಮತ್ತೆ ಲೋಡ್ ಮಾಡಿ', 'उपचार की जानकारी फिर लोड करें'],
  loading: ['Loading detailed treatment information…', 'ವಿವರವಾದ ಚಿಕಿತ್ಸೆ ಮಾಹಿತಿ ಲೋಡ್ ಆಗುತ್ತಿದೆ…', 'विस्तृत उपचार की जानकारी लोड हो रही है…'],
  failure: ['Detailed treatment information could not load. The basic care summary remains available; try reopening the app once its offline assets are ready.', 'ವಿವರವಾದ ಚಿಕಿತ್ಸೆ ಮಾಹಿತಿ ಲೋಡ್ ಆಗಲಿಲ್ಲ. ಮೂಲ ಆರೈಕೆ ಸಾರಾಂಶ ಲಭ್ಯವಿದೆ; ಆಫ್‌ಲೈನ್ ಸಿದ್ಧವಾದ ಬಳಿಕ ಮತ್ತೆ ತೆರೆಯಿರಿ.', 'विस्तृत उपचार की जानकारी लोड नहीं हुई। मूल देखभाल का सार उपलब्ध है; ऑफलाइन सामग्री तैयार होने पर फिर खोलें।'],
  empty: ['No matching conditions. Try another crop or search term.', 'ಹೊಂದುವ ರೋಗ ಇಲ್ಲ. ಬೇರೆ ಬೆಳೆ ಅಥವಾ ಪದ ಪ್ರಯತ್ನಿಸಿ.', 'कोई स्थिति नहीं मिली। दूसरी फसल या खोज शब्द आजमाएँ।'],
  audio: ['Listen to treatment and recovery summary', 'ಚಿಕಿತ್ಸೆ ಮತ್ತು ಚೇತರಿಕೆ ಸಾರಾಂಶ ಕೇಳಿ', 'उपचार और सुधार का सार सुनें'],
} as const;
export type CareTextKey = keyof typeof COPY;
export function careText(key: CareTextKey, language: Language): string { return COPY[key][language === 'kn' ? 1 : language === 'hi' ? 2 : 0]; }
