import { assetUrl } from './content';
import { CONDITIONS } from './types';
import type { AssessmentType, Language, ReportedSymptoms } from './types';

/** This second model is an authored decision system, not a trained image model. */
export interface AdvisoryCopy {
  overview: string;
  curability: string;
  do_now: string[];
  management: string[];
  prevention: string[];
  escalation: string[];
}
export interface AdvisoryProfile {
  crop_id: string;
  kind: 'healthy' | 'fungal' | 'oomycete' | 'bacterial' | 'viral' | 'pest';
  risk: 'routine' | 'rapid_blight' | 'virus' | 'foliar';
  source_ids: string[];
  translations: Record<Language, AdvisoryCopy>;
}
export interface AdvisoryModel {
  schema_version: 1;
  model_version: string;
  model_type: 'expert_decision_model';
  trained: false;
  agronomist_reviewed: false;
  field_validated: false;
  profiles: Record<string, AdvisoryProfile>;
  sources: { id: string; title: string; url: string; verification_status: string }[];
}
export type Severity = 'NONE' | 'UNKNOWN' | 'MILD' | 'MODERATE' | 'SEVERE';
export type Urgency = 'MONITOR' | 'SOON' | 'SAME_DAY' | 'URGENT';
export interface AdvisoryResult {
  severity: Severity;
  urgency: Urgency;
  reviewHours: number;
  reasonCodes: string[];
  modelVersion: string;
  requiresConfirmation: true;
  conditionalCare: true;
  profile: AdvisoryProfile | null;
  observations: Partial<ReportedSymptoms> | null;
}

export function validateAdvisoryModel(value: unknown): AdvisoryModel {
  const m = value as AdvisoryModel;
  if (!m || m.schema_version !== 1 || m.model_type !== 'expert_decision_model' ||
    m.trained !== false || m.field_validated !== false || m.agronomist_reviewed !== false ||
    typeof m.model_version !== 'string' || !m.model_version.trim() || !Array.isArray(m.sources) || !m.profiles) {
    throw new Error('The packaged care model is incompatible.');
  }
  if (!m.sources.every(source => source && typeof source.id === 'string' && typeof source.title === 'string' &&
    typeof source.url === 'string' && /^https?:\/\//.test(source.url) && typeof source.verification_status === 'string'))
    throw new Error('Invalid care references.');
  for (const condition of CONDITIONS) {
    const p = m.profiles[condition.id];
    if (!p || p.crop_id !== condition.crop_id || !['routine', 'rapid_blight', 'virus', 'foliar'].includes(p.risk) ||
      !['healthy', 'fungal', 'oomycete', 'bacterial', 'viral', 'pest'].includes(p.kind) ||
      !Array.isArray(p.source_ids) || !p.source_ids.every(id => m.sources.some(source => source.id === id)))
      throw new Error(`Missing care profile: ${condition.id}`);
    for (const language of ['en', 'kn', 'hi'] as const) {
      const copy = p.translations?.[language];
      if (!copy || typeof copy.overview !== 'string' || !copy.overview.trim() || typeof copy.curability !== 'string' || !copy.curability.trim() ||
        !['do_now', 'management', 'prevention', 'escalation'].every(key => {
          const list = copy[key as keyof AdvisoryCopy];
          return Array.isArray(list) && list.length > 0 && list.every(line => typeof line === 'string' && line.trim());
        })) throw new Error(`Incomplete care profile: ${condition.id}/${language}`);
    }
  }
  return m;
}
export async function loadAdvisoryModel(): Promise<AdvisoryModel> {
  const response = await fetch(assetUrl('content/advisory_model.json'), { credentials: 'same-origin' });
  if (!response.ok) throw new Error(`Offline care model could not load (${response.status}).`);
  return validateAdvisoryModel(await response.json());
}

/** Classifier score is deliberately absent: confidence cannot measure damage. */
export function evaluateAdvisory(
  model: AdvisoryModel,
  conditionId: string | null,
  observations?: Partial<ReportedSymptoms> | null,
  resultType?: AssessmentType,
): AdvisoryResult {
  const blocked = resultType === 'retake' || resultType === 'model_unavailable' || resultType === 'crop_mismatch';
  let profile = !blocked && conditionId ? model.profiles[conditionId] ?? null : null;
  const x = observations;
  // Older saved scans only asked three questions. Missing newer answers are
  // not negative answers and must never silently qualify for routine monitoring.
  const incompleteAnswers = !!x && (
    !['NO_VISIBLE_DAMAGE', 'FEW_SPOTS', 'SOME_SPOTS', 'MANY_SPOTS', 'NOT_REPORTED'].includes(x.leafCoverage ?? '') ||
    ['spreadingQuickly', 'manyPlantsAffected', 'wiltingOrDying', 'fruitOrStemAffected', 'wetWeather', 'uncertainAnswers']
      .some(key => typeof x[key as keyof ReportedSymptoms] !== 'boolean')
  );
  const reasonCodes: string[] = [];
  let severity: Severity = 'UNKNOWN';
  if (x?.wiltingOrDying || x?.fruitOrStemAffected || x?.leafCoverage === 'MANY_SPOTS') severity = 'SEVERE';
  else if (x?.leafCoverage === 'SOME_SPOTS') severity = 'MODERATE';
  else if (x?.leafCoverage === 'FEW_SPOTS') severity = 'MILD';
  else if (x?.leafCoverage === 'NO_VISIBLE_DAMAGE') severity = 'NONE';
  if (!x) reasonCodes.push('awaiting_answers');
  else if (x.leafCoverage === 'NOT_REPORTED' || !x.leafCoverage) reasonCodes.push('coverage_unknown');
  if (x?.uncertainAnswers) reasonCodes.push('uncertain_answers');
  if (incompleteAnswers) reasonCodes.push('incomplete_answers');
  if (x?.wiltingOrDying) reasonCodes.push('wilting');
  if (x?.fruitOrStemAffected) reasonCodes.push('fruit_or_stem');
  if (x?.leafCoverage === 'NO_VISIBLE_DAMAGE') reasonCodes.push('coverage_none');
  if (x?.leafCoverage === 'MANY_SPOTS') reasonCodes.push('coverage_high');
  if (x?.leafCoverage === 'SOME_SPOTS') reasonCodes.push('coverage_moderate');
  if (x?.leafCoverage === 'FEW_SPOTS') reasonCodes.push('coverage_low');
  if (x?.spreadingQuickly) reasonCodes.push('rapid_spread');
  if (x?.manyPlantsAffected) reasonCodes.push('multiple_plants');
  if (profile?.risk === 'rapid_blight') reasonCodes.push('rapid_blight');
  if (profile?.risk === 'virus') reasonCodes.push('virus');
  if (x?.wetWeather && profile?.kind !== 'healthy') reasonCodes.push('wet_weather');
  const healthyConflict = profile?.kind === 'healthy' && !!(x?.spreadingQuickly || x?.manyPlantsAffected ||
    x?.wiltingOrDying || x?.fruitOrStemAffected || ['FEW_SPOTS', 'SOME_SPOTS', 'MANY_SPOTS'].includes(x?.leafCoverage ?? ''));
  if (healthyConflict) { reasonCodes.push('healthy_conflict'); profile = null; }
  let urgency: Urgency;
  if (x?.wiltingOrDying || (x?.spreadingQuickly && x.manyPlantsAffected)) urgency = 'URGENT';
  else if (severity === 'SEVERE' || profile?.risk === 'rapid_blight' || (profile?.risk === 'virus' && x?.spreadingQuickly)) urgency = 'SAME_DAY';
  else if (severity === 'MODERATE' || x?.spreadingQuickly || x?.manyPlantsAffected || x?.uncertainAnswers ||
    severity === 'UNKNOWN' || profile?.risk === 'virus' || healthyConflict || incompleteAnswers) urgency = 'SOON';
  else urgency = 'MONITOR';
  if (!profile) reasonCodes.push(blocked ? 'blocked_prediction' : 'confirm_cause');
  return { severity, urgency, reviewHours: urgency === 'URGENT' ? 0 : urgency === 'SAME_DAY' ? 24 : 48,
    reasonCodes, modelVersion: model.model_version, requiresConfirmation: true, conditionalCare: true,
    profile, observations: observations ?? null };
}

const COPY = {
  title: ['Care & urgency', 'ಆರೈಕೆ ಮತ್ತು ತುರ್ತು ಕ್ರಮ', 'देखभाल और तात्कालिकता'],
  severity: ['Reported damage', 'ತಿಳಿಸಿದ ಹಾನಿ', 'बताया गया नुकसान'],
  urgency: ['When to act', 'ಯಾವಾಗ ಕ್ರಮ ಕೈಗೊಳ್ಳಬೇಕು', 'कब कदम उठाएँ'],
  NONE: ['No visible damage reported', 'ಕಾಣುವ ಹಾನಿ ತಿಳಿಸಿಲ್ಲ', 'दिखने वाला नुकसान नहीं बताया'],
  UNKNOWN: ['Not enough information', 'ಮಾಹಿತಿ ಸಾಕಾಗಿಲ್ಲ', 'जानकारी पर्याप्त नहीं'],
  MILD: ['Mild', 'ಕಡಿಮೆ', 'हल्का'], MODERATE: ['Moderate', 'ಮಧ್ಯಮ', 'मध्यम'], SEVERE: ['Severe signs', 'ತೀವ್ರ ಲಕ್ಷಣಗಳು', 'गंभीर लक्षण'],
  MONITOR: ['Monitor · recheck within 48 hours', 'ಗಮನಿಸಿ · 48 ಗಂಟೆಯೊಳಗೆ ಪರಿಶೀಲಿಸಿ', 'निगरानी करें · 48 घंटे में दोबारा देखें'],
  SOON: ['Ask an expert within 48 hours', '48 ಗಂಟೆಯೊಳಗೆ ತಜ್ಞರನ್ನು ಕೇಳಿ', '48 घंटे में विशेषज्ञ से पूछें'],
  SAME_DAY: ['Get advice today · within 24 hours', 'ಇಂದೇ ಸಲಹೆ ಪಡೆಯಿರಿ · 24 ಗಂಟೆಯೊಳಗೆ', 'आज सलाह लें · 24 घंटे के भीतर'],
  URGENT: ['Urgent · contact an expert now', 'ತುರ್ತು · ಈಗಲೇ ತಜ್ಞರನ್ನು ಸಂಪರ್ಕಿಸಿ', 'तत्काल · अभी विशेषज्ञ से संपर्क करें'],
  basis: ['Based on your observations and the suspected condition. This is not an image-measured severity grade.', 'ನಿಮ್ಮ ಗಮನಿಸುವಿಕೆ ಮತ್ತು ಶಂಕಿತ ರೋಗದ ಆಧಾರಿತ. ಇದು ಚಿತ್ರದಿಂದ ಅಳೆದ ತೀವ್ರತೆ ಅಲ್ಲ.', 'आपकी बताई स्थिति और संभावित रोग पर आधारित। यह तस्वीर से मापी गई गंभीरता नहीं है।'],
  conditional: ['Care if this condition is confirmed', 'ಈ ರೋಗ ದೃಢಪಟ್ಟರೆ ಅನುಸರಿಸಬೇಕಾದ ಆರೈಕೆ', 'इस रोग की पुष्टि होने पर देखभाल'],
  generic: ['Confirm the cause before disease-specific treatment', 'ರೋಗಕ್ಕೆ ನಿರ್ದಿಷ್ಟ ಚಿಕಿತ್ಸೆಗೂ ಮೊದಲು ಕಾರಣ ದೃಢಪಡಿಸಿ', 'रोग-विशेष उपचार से पहले कारण की पुष्टि कराएँ'],
  questions: ['Check damage & urgency · 6 questions', 'ಹಾನಿ ಮತ್ತು ತುರ್ತು ಪರಿಶೀಲನೆ · 6 ಪ್ರಶ್ನೆಗಳು', 'नुकसान और तात्कालिकता जाँचें · 6 प्रश्न'],
  now: ['Do now', 'ಈಗ ಮಾಡಿ', 'अभी क्या करें'], management: ['Management options', 'ನಿರ್ವಹಣೆಯ ಆಯ್ಕೆಗಳು', 'प्रबंधन के विकल्प'],
  prevention: ['Prevent the next infection', 'ಮುಂದಿನ ಸೋಂಕನ್ನು ತಡೆಯಿರಿ', 'अगले संक्रमण से बचाव'], escalation: ['Get help if…', 'ಈ ಸಂದರ್ಭದಲ್ಲಿ ನೆರವು ಪಡೆಯಿರಿ…', 'इन स्थितियों में मदद लें…'],
  curability: ['Can it recover?', 'ಚೇತರಿಸಿಕೊಳ್ಳಬಹುದೇ?', 'क्या सुधार हो सकता है?'],
  why: ['Why this priority?', 'ಈ ಆದ್ಯತೆ ಏಕೆ?', 'यह प्राथमिकता क्यों?'],
  model: ['Offline expert decision model · prototype, not agronomist validated', 'ಆಫ್‌ಲೈನ್ ತಜ್ಞ ನಿರ್ಧಾರ ಮಾದರಿ · ಕೃಷಿ ತಜ್ಞರಿಂದ ದೃಢೀಕರಿಸದ ಮಾದರಿ', 'ऑफलाइन विशेषज्ञ निर्णय मॉडल · प्रारूप, कृषि विशेषज्ञ द्वारा सत्यापित नहीं'],
  noAnswers: ['Answer the damage questions to personalize urgency.', 'ತುರ್ತು ಕ್ರಮ ತಿಳಿಯಲು ಹಾನಿಯ ಪ್ರಶ್ನೆಗಳಿಗೆ ಉತ್ತರಿಸಿ.', 'तात्कालिकता जानने के लिए नुकसान के प्रश्नों का उत्तर दें।'],
  careAudio: ['Listen to care summary', 'ಆರೈಕೆಯ ಸಾರಾಂಶ ಕೇಳಿ', 'देखभाल का सार सुनें'],
  audio: ['Listen to general precautions', 'ಸಾಮಾನ್ಯ ಮುನ್ನೆಚ್ಚರಿಕೆ ಕೇಳಿ', 'सामान्य सावधानियाँ सुनें'],
  question0: ['Are symptoms spreading quickly?', 'ಲಕ್ಷಣಗಳು ವೇಗವಾಗಿ ಹರಡುತ್ತಿವೆಯೇ?', 'क्या लक्षण तेजी से फैल रहे हैं?'],
  question1: ['How much of this leaf looks affected?', 'ಈ ಎಲೆಯ ಎಷ್ಟು ಭಾಗದಲ್ಲಿ ಲಕ್ಷಣಗಳಿವೆ?', 'इस पत्ते का कितना हिस्सा प्रभावित है?'],
  question2: ['Do several plants have these symptoms?', 'ಹಲವು ಗಿಡಗಳಲ್ಲಿ ಇದೇ ಲಕ್ಷಣಗಳಿವೆಯೇ?', 'क्या कई पौधों में ये लक्षण हैं?'],
  question3: ['Are plants wilting or dying?', 'ಗಿಡಗಳು ಬಾಡುತ್ತಿವೆಯೇ ಅಥವಾ ಸಾಯುತ್ತಿವೆಯೇ?', 'क्या पौधे मुरझा रहे हैं या मर रहे हैं?'],
  question4: ['Are fruits, tubers or stems also affected?', 'ಹಣ್ಣು, ಗೆಡ್ಡೆ ಅಥವಾ ಕಾಂಡಕ್ಕೂ ಹಾನಿಯಾಗಿದೆಯೇ?', 'क्या फल, कंद या तने भी प्रभावित हैं?'],
  question5: ['Has the crop had wet or humid conditions?', 'ಬೆಳೆಯ ಸುತ್ತ ತೇವ ಅಥವಾ ಆರ್ದ್ರತೆ ಇದೆಯೇ?', 'क्या फसल के आसपास नमी या आर्द्रता रही है?'],
  none: ['No visible damage', 'ಕಾಣುವ ಹಾನಿ ಇಲ್ಲ', 'कोई नुकसान नहीं दिखता'],
  few: ['A few spots · less than 10%', 'ಕೆಲವು ಚುಕ್ಕೆಗಳು · 10% ಕ್ಕಿಂತ ಕಡಿಮೆ', 'कुछ धब्बे · 10% से कम'],
  some: ['Some damage · about 10–30%', 'ಸ್ವಲ್ಪ ಹಾನಿ · ಸುಮಾರು 10–30%', 'कुछ नुकसान · लगभग 10–30%'],
  many: ['Many spots · more than 30%', 'ಹಲವು ಚುಕ್ಕೆಗಳು · 30% ಕ್ಕಿಂತ ಹೆಚ್ಚು', 'बहुत धब्बे · 30% से अधिक'],
  yes: ['Yes', 'ಹೌದು', 'हाँ'], no: ['No', 'ಇಲ್ಲ', 'नहीं'], unsure: ['I’m not sure', 'ನನಗೆ ಖಚಿತವಿಲ್ಲ', 'मुझे पक्का नहीं'],
  failure: ['The offline care model could not load. Retake a clear photo and contact an agriculture expert if symptoms spread.', 'ಆಫ್‌ಲೈನ್ ಆರೈಕೆ ಮಾದರಿ ಲೋಡ್ ಆಗಲಿಲ್ಲ. ಸ್ಪಷ್ಟ ಚಿತ್ರ ತೆಗೆದು, ಲಕ್ಷಣ ಹರಡಿದರೆ ಕೃಷಿ ತಜ್ಞರನ್ನು ಸಂಪರ್ಕಿಸಿ.', 'ऑफलाइन देखभाल मॉडल लोड नहीं हुआ। साफ तस्वीर लें और लक्षण फैलने पर कृषि विशेषज्ञ से संपर्क करें।'],
} as const;
export type AdvisoryTextKey = keyof typeof COPY;
export function advisoryText(key: AdvisoryTextKey, language: Language): string {
  return COPY[key][language === 'kn' ? 1 : language === 'hi' ? 2 : 0];
}
const REASONS: Record<string, readonly [string, string, string]> = {
  awaiting_answers: ['Answer the damage questions first.', 'ಮೊದಲು ಹಾನಿಯ ಪ್ರಶ್ನೆಗಳಿಗೆ ಉತ್ತರಿಸಿ.', 'पहले नुकसान के प्रश्नों के उत्तर दें।'],
  coverage_none: ['No visible damage was reported on this leaf.', 'ಈ ಎಲೆಯಲ್ಲಿ ಕಾಣುವ ಹಾನಿ ತಿಳಿಸಿಲ್ಲ.', 'इस पत्ते पर कोई दिखने वाला नुकसान नहीं बताया गया।'],
  coverage_unknown: ['Extent of damage is not known.', 'ಹಾನಿಯ ಪ್ರಮಾಣ ತಿಳಿದಿಲ್ಲ.', 'नुकसान का विस्तार पता नहीं है।'],
  incomplete_answers: ['Some questions have not been answered. Complete all six questions before relying on routine monitoring.', 'ಕೆಲವು ಪ್ರಶ್ನೆಗಳಿಗೆ ಉತ್ತರಿಸಿಲ್ಲ. ಸಾಮಾನ್ಯ ವೀಕ್ಷಣೆಯನ್ನು ಅವಲಂಬಿಸುವ ಮೊದಲು ಆರು ಪ್ರಶ್ನೆಗಳಿಗೆ ಉತ್ತರಿಸಿ.', 'कुछ प्रश्नों के उत्तर नहीं दिए गए हैं। केवल निगरानी पर निर्भर होने से पहले सभी छह प्रश्नों के उत्तर दें।'],
  uncertain_answers: ['Some answers are uncertain; get the crop checked.', 'ಕೆಲವು ಉತ್ತರ ಖಚಿತವಿಲ್ಲ; ಬೆಳೆ ಪರಿಶೀಲಿಸಿಕೊಳ್ಳಿ.', 'कुछ उत्तर अनिश्चित हैं; फसल की जाँच कराएँ।'],
  wilting: ['Wilting or dying plants need immediate attention.', 'ಬಾಡುವ ಅಥವಾ ಸಾಯುವ ಗಿಡಗಳಿಗೆ ತಕ್ಷಣ ಗಮನ ಬೇಕು.', 'मुरझाते या मरते पौधों को तुरंत ध्यान चाहिए।'],
  fruit_or_stem: ['Fruit, tuber or stem symptoms can threaten the harvest.', 'ಹಣ್ಣು, ಗೆಡ್ಡೆ ಅಥವಾ ಕಾಂಡದ ಲಕ್ಷಣ ಇಳುವರಿಗೆ ಹಾನಿ ಮಾಡಬಹುದು.', 'फल, कंद या तने के लक्षण उपज को नुकसान पहुँचा सकते हैं।'],
  coverage_high: ['You reported more than 30% of this leaf affected.', 'ಈ ಎಲೆಯ 30% ಕ್ಕಿಂತ ಹೆಚ್ಚು ಭಾಗ ಹಾನಿ ತಿಳಿಸಿದ್ದೀರಿ.', 'आपने इस पत्ते का 30% से अधिक प्रभावित बताया।'],
  coverage_moderate: ['You reported about 10–30% of this leaf affected.', 'ಈ ಎಲೆಯ ಸುಮಾರು 10–30% ಭಾಗ ಹಾನಿ ತಿಳಿಸಿದ್ದೀರಿ.', 'आपने इस पत्ते का लगभग 10–30% प्रभावित बताया।'],
  coverage_low: ['You reported less than 10% of this leaf affected.', 'ಈ ಎಲೆಯ 10% ಕ್ಕಿಂತ ಕಡಿಮೆ ಭಾಗ ಹಾನಿ ತಿಳಿಸಿದ್ದೀರಿ.', 'आपने इस पत्ते का 10% से कम प्रभावित बताया।'],
  rapid_spread: ['Symptoms are spreading quickly.', 'ಲಕ್ಷಣಗಳು ವೇಗವಾಗಿ ಹರಡುತ್ತಿವೆ.', 'लक्षण तेजी से फैल रहे हैं।'],
  multiple_plants: ['Several plants are affected.', 'ಹಲವು ಗಿಡಗಳಿಗೆ ಹಾನಿಯಾಗಿದೆ.', 'कई पौधे प्रभावित हैं।'],
  rapid_blight: ['Suspected late blight can spread rapidly; get same-day advice.', 'ಶಂಕಿತ ತಡವಾದ ಅಂಗಮಾರಿ ವೇಗವಾಗಿ ಹರಡಬಹುದು; ಇಂದೇ ಸಲಹೆ ಪಡೆಯಿರಿ.', 'संभावित पछेती झुलसा तेजी से फैल सकता है; आज ही सलाह लें।'],
  virus: ['Virus symptoms need confirmation and spread prevention; sprays do not cure the virus.', 'ವೈರಸ್ ಲಕ್ಷಣ ದೃಢೀಕರಣ ಮತ್ತು ಹರಡುವಿಕೆ ತಡೆ ಬೇಕು; ಸಿಂಪಡಣೆ ವೈರಸ್ ಗುಣಪಡಿಸುವುದಿಲ್ಲ.', 'विषाणु के लक्षणों की पुष्टि और फैलाव रोकना जरूरी है; छिड़काव विषाणु का इलाज नहीं करता।'],
  wet_weather: ['Wet conditions can favor several leaf diseases; inspect nearby plants.', 'ತೇವ ಹಲವು ಎಲೆ ರೋಗಗಳಿಗೆ ಅನುಕೂಲ; ಹತ್ತಿರದ ಗಿಡಗಳನ್ನು ನೋಡಿ.', 'नमी कई पत्ती रोगों को बढ़ावा दे सकती है; आसपास के पौधे देखें।'],
  healthy_conflict: ['Visible symptoms conflict with the healthy-looking prediction; confirm the cause.', 'ಕಾಣುವ ಲಕ್ಷಣಗಳು ಆರೋಗ್ಯಕರ ಅಂದಾಜಿಗೆ ಹೊಂದುವುದಿಲ್ಲ; ಕಾರಣ ದೃಢಪಡಿಸಿ.', 'दिख रहे लक्षण स्वस्थ दिखने के अनुमान से मेल नहीं खाते; कारण की पुष्टि कराएँ।'],
  blocked_prediction: ['This result cannot identify a condition for specific care.', 'ಈ ಫಲಿತಾಂಶದಿಂದ ನಿರ್ದಿಷ್ಟ ಆರೈಕೆಗೆ ರೋಗ ಗುರುತಿಸಲಾಗದು.', 'इस परिणाम से विशेष देखभाल के लिए रोग पहचान नहीं हो सकती।'],
  confirm_cause: ['Confirm the cause with a local agriculture expert.', 'ಸ್ಥಳೀಯ ಕೃಷಿ ತಜ್ಞರಿಂದ ಕಾರಣ ದೃಢಪಡಿಸಿ.', 'स्थानीय कृषि विशेषज्ञ से कारण की पुष्टि कराएँ।'],
};
export function advisoryReason(code: string, language: Language): string {
  return REASONS[code]?.[language === 'kn' ? 1 : language === 'hi' ? 2 : 0] ?? code;
}
