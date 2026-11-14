import { useCallback, useEffect, useRef, useState } from 'react';
import type { ChangeEvent, ReactNode } from 'react';
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  Camera,
  Check,
  CheckCircle2,
  ChevronRight,
  Download,
  HelpCircle,
  History,
  Home,
  ImagePlus,
  Leaf,
  LoaderCircle,
  Phone,
  Settings,
  ShieldCheck,
  Smartphone,
  Sprout,
  Trash2,
  Volume2,
  WifiOff,
  X,
  Zap,
  ZapOff,
} from 'lucide-react';
import { AudioPlayer } from './components/AudioPlayer';
import { AdvisoryPanel } from './components/AdvisoryPanel';
import { TreatmentPlan } from './components/TreatmentPlan';
import { buildCarePlan, careText, loadCareProtocols } from './lib/careProtocols';
import type { CareProtocols, CareTextKey } from './lib/careProtocols';
import { advisoryText, evaluateAdvisory, loadAdvisoryModel } from './lib/advisory';
import type { AdvisoryModel, AdvisoryResult, AdvisoryTextKey } from './lib/advisory';
import { analyzeLeaf, getModelStatus } from './lib/inference';
import type { AssessmentResult, ModelStatus } from './lib/inference';
import {
  conditionName,
  assetUrl,
  cropName,
  getPrompt,
  loadCatalog,
  summarizeConcern,
  translateUi,
} from './lib/content';
import {
  deleteObservation,
  getLanguage,
  HISTORY_CHANGED_EVENT,
  listObservations,
  saveObservation,
  updateObservationConcern,
  setLanguage as persistLanguage,
} from './lib/storage';
import { CONDITIONS, CROPS, LANGUAGES, LANGUAGE_LABELS, LANGUAGE_LOCALES } from './lib/types';
import type {
  ConcernResult,
  CropId,
  Language,
  LeafCoverage,
  ObservationRecord,
  ReportedSymptoms,
} from './lib/types';
import { useOfflineReady } from './lib/offline';

type Screen =
  | 'home'
  | 'capture'
  | 'photo'
  | 'processing'
  | 'result'
  | 'guidance'
  | 'care_library'
  | 'care_detail'
  | 'concern'
  | 'history'
  | 'help'
  | 'settings';
const EMPTY_SYMPTOMS: ReportedSymptoms = {
  spreadingQuickly: false,
  manyPlantsAffected: false,
  wiltingOrDying: false,
  leafCoverage: 'NOT_REPORTED',
  uncertainAnswers: false,
};

function usePhotoUrl(blob: Blob | null | undefined) {
  const [url, setUrl] = useState<string | undefined>();
  useEffect(() => {
    if (!blob) {
      setUrl(undefined);
      return;
    }
    const objectUrl = URL.createObjectURL(blob);
    setUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [blob]);
  return url;
}

function Photo({
  blob,
  className = 'scan-thumb',
  alt = 'Selected crop leaf',
}: {
  blob?: Blob | null;
  className?: string;
  alt?: string;
}) {
  const url = usePhotoUrl(blob);
  return url ? (
    <img className={className} src={url} alt={alt} />
  ) : (
    <span className={`${className} empty`}>
      <Leaf size={23} />
    </span>
  );
}

async function historyPhoto(file: Blob): Promise<Blob> {
  // Persist a bounded image rather than a multi-megapixel camera original.
  try {
    const bitmap = await createImageBitmap(file, {
      imageOrientation: 'from-image',
      resizeWidth: 640,
      resizeQuality: 'high',
    });
    const scale = Math.min(1, 640 / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(bitmap.width * scale));
    canvas.height = Math.max(1, Math.round(bitmap.height * scale));
    canvas.getContext('2d')!.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    bitmap.close();
    return await new Promise<Blob>((resolve) =>
      canvas.toBlob((blob) => resolve(blob || file), 'image/jpeg', 0.82),
    );
  } catch {
    return file;
  }
}

export default function App() {
  const [screen, setScreen] = useState<Screen>('home');
  const [language, setLanguage] = useState<Language>(getLanguage);
  const [crop, setCrop] = useState<CropId>('tomato');
  const [photo, setPhoto] = useState<File | null>(null);
  const [assessment, setAssessment] = useState<AssessmentResult | null>(null);
  const [opened, setOpened] = useState<ObservationRecord | null>(null);
  const [history, setHistory] = useState<ObservationRecord[]>([]);
  const [historyFilter, setHistoryFilter] = useState<CropId | 'all'>('all');
  const [historyLoading, setHistoryLoading] = useState(true);
  const [model, setModel] = useState<ModelStatus | null>(null);
  const [catalogReady, setCatalogReady] = useState(false);
  const [catalogFailed, setCatalogFailed] = useState(false);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [savedId, setSavedId] = useState<string | null>(null);
  const [question, setQuestion] = useState(0);
  const [answers, setAnswers] = useState<(number | null)[]>(Array(6).fill(null));
  const [advisoryModel, setAdvisoryModel] = useState<AdvisoryModel | null>(null);
  const [advisoryFailed, setAdvisoryFailed] = useState(false);
  const [concern, setConcern] = useState<ConcernResult | null>(null);
  const [concernComplete, setConcernComplete] = useState(false);
  const [careSaved, setCareSaved] = useState(false);
  const [careProtocols, setCareProtocols] = useState<CareProtocols | null>(null);
  const [protocolsFailed, setProtocolsFailed] = useState(false);
  const [treatmentAudioPaths, setTreatmentAudioPaths] = useState<Set<string>>(new Set());
  const [libraryOrigin, setLibraryOrigin] = useState<'home' | 'result' | 'guidance'>('home');
  const [libraryCrop, setLibraryCrop] = useState<CropId | 'all'>('all');
  const [librarySearch, setLibrarySearch] = useState('');
  const [manualCareId, setManualCareId] = useState<string | null>(null);
  const [manualConcern, setManualConcern] = useState<ConcernResult | null>(null);
  const [libraryQuestioning, setLibraryQuestioning] = useState(false);
  const [expertOpen, setExpertOpen] = useState(false);
  const [expertNumber, setExpertNumber] = useState('');
  const [deleteTarget, setDeleteTarget] = useState<ObservationRecord | null>(null);
  const upload = useRef<HTMLInputElement>(null);
  const analysisRequest = useRef(0);
  const offlineReady = useOfflineReady();
  const t = useCallback((en: string, kn: string) => translateUi(en, kn, language), [language]);
  const a = (key: AdvisoryTextKey) => advisoryText(key, language);
  const c = (key: CareTextKey) => careText(key, language);
  const refreshHistory = useCallback(async () => {
    try {
      setHistory(await listObservations({ limit: 100 }));
    } catch {
      setError('Saved scans could not be opened. Browser storage may be unavailable.');
    } finally {
      setHistoryLoading(false);
    }
  }, []);
  useEffect(() => {
    void loadAdvisoryModel().then(setAdvisoryModel).catch(() => setAdvisoryFailed(true));
    void loadCareProtocols().then(setCareProtocols).catch(() => setProtocolsFailed(true));
    void fetch(assetUrl('content/treatment_audio_manifest.json')).then(r => r.ok ? r.json() : null).then(manifest => {
      if (Array.isArray(manifest?.clips)) setTreatmentAudioPaths(new Set(manifest.clips.map((clip: { path: string }) => clip.path)));
    }).catch(() => undefined);
    void loadCatalog()
      .then(() => setCatalogReady(true))
      .catch(() => setCatalogFailed(true));
    void getModelStatus()
      .then(setModel)
      .catch(() =>
        setModel({
          ready: false,
          validated: false,
          name: 'Crop disease model',
          version: '',
          bytes: 0,
          message: 'Model could not be loaded.',
        }),
      );
    void refreshHistory();
    window.addEventListener(HISTORY_CHANGED_EVENT, refreshHistory);
    return () => window.removeEventListener(HISTORY_CHANGED_EVENT, refreshHistory);
  }, [refreshHistory]);
  useEffect(() => {
    document.documentElement.lang = language;
  }, [language]);

  function changeLanguage(value: Language) {
    setLanguage(value);
    try {
      persistLanguage(value);
    } catch {
      setError('Language changed for this visit; browser preferences could not be saved.');
    }
  }
  function navigate(next: Screen) {
    if (screen === 'processing') analysisRequest.current++;
    setError('');
    setScreen(next);
  }
  function selectPhoto(file: File | null) {
    if (!file) return;
    if (!file.type.startsWith('image/')) {
      setError(t('Choose an image file (JPG, PNG or WebP).', 'ಚಿತ್ರದ ಫೈಲ್ ಆಯ್ಕೆಮಾಡಿ.'));
      return;
    }
    if (file.size > 32 * 1024 * 1024) {
      setError(
        t(
          'This photo is too large. Choose a photo smaller than 32 MB.',
          '32 MB ಗಿಂತ ಚಿಕ್ಕ ಚಿತ್ರ ಆಯ್ಕೆಮಾಡಿ.',
        ),
      );
      return;
    }
    setError('');
    setPhoto(file);
    setAssessment(null);
    setOpened(null);
    setSavedId(null);
    setConcern(null);
    setConcernComplete(false);
    setAnswers(Array(6).fill(null));
    setScreen('photo');
  }
  function onUpload(event: ChangeEvent<HTMLInputElement>) {
    selectPhoto(event.target.files?.[0] || null);
    event.target.value = '';
  }
  async function analyze() {
    if (!photo) return;
    const current = ++analysisRequest.current;
    setScreen('processing');
    setError('');
    try {
      await new Promise<void>((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
      );
      const result = await analyzeLeaf(photo, crop);
      if (current !== analysisRequest.current) return;
      setAssessment(result);
      setScreen('result');
    } catch (reason) {
      if (current !== analysisRequest.current) return;
      setScreen('photo');
      setError(
        reason instanceof Error
          ? reason.message
          : t(
              'Could not analyse this photo. Please try another.',
              'ಮತ್ತೊಂದು ಚಿತ್ರವನ್ನು ಪ್ರಯತ್ನಿಸಿ.',
            ),
      );
    }
  }
  const activePhoto = opened?.photoBlob || photo;
  const activeCrop = opened?.cropId || crop;
  const resultType = opened?.resultType || assessment?.type || 'uncertain';
  const validated = opened?.validated ?? assessment?.validated ?? false;
  // Accepted prototype matches are not the same as independently field-validated results.
  const accepted = resultType === 'likely' || resultType === 'healthy';
  const nonLeaf = assessment?.qualityIssues?.includes('NOT_A_LEAF') === true || opened?.note === 'NOT_A_LEAF';
  const unfamiliarLeaf = (assessment?.leafCheckPassed === true && assessment.reasons?.some(reason => ['UNFAMILIAR_IMAGE', 'CONDITION_DISABLED'].includes(reason)) === true) || opened?.note === 'LEAF_CHECKED_UNCERTAIN';
  const unsupportedImage = (assessment?.leafCheckPassed !== true && assessment?.reasons?.some(reason => ['UNFAMILIAR_IMAGE', 'CONDITION_DISABLED'].includes(reason)) === true) || opened?.note === 'UNSUPPORTED_IMAGE';
  const top = unsupportedImage || nonLeaf ? undefined : assessment?.candidates[0];
  const conditionId = unsupportedImage || nonLeaf ? null : opened?.conditionId || top?.id || null;
  const score = unsupportedImage || nonLeaf ? null : opened?.score ?? top?.score ?? null;
  const provisionalPrediction = resultType === 'uncertain' && !!conditionId &&
    (assessment?.sourceEvaluated === true || opened?.note === 'LEAF_CHECKED_UNCERTAIN' ||
      (opened?.modelVersion === model?.version && model?.sourceEvaluated === true));
  const cropMismatchPrediction = resultType === 'crop_mismatch' && !!conditionId &&
    (assessment?.sourceEvaluated === true ||
      (opened?.modelVersion === model?.version && model?.sourceEvaluated === true));
  const hasPrediction = accepted || provisionalPrediction || cropMismatchPrediction;
  const predictedCrop = top?.cropId || CONDITIONS.find(item => item.id === conditionId)?.crop_id || activeCrop;
  const promptKey =
    resultType === 'retake'
      ? 'retake'
      : resultType === 'crop_mismatch'
        ? 'crop_mismatch'
        : resultType === 'model_unavailable'
          ? 'model_unavailable'
          : accepted && resultType === 'healthy'
            ? 'healthy'
            : hasPrediction
              ? 'model_prototype'
              : 'uncertain';
  const resultPrompt = getPrompt(promptKey, language);
  const currentConcern = concern || opened?.concern || null;
  const advisory = advisoryModel ? evaluateAdvisory(advisoryModel, conditionId, currentConcern?.reportedSymptoms, resultType) : null;
  const manualAdvisory = advisoryModel && manualCareId ? evaluateAdvisory(advisoryModel, manualCareId, manualConcern?.reportedSymptoms, 'uncertain') : null;
  const questionAdvisory = libraryQuestioning ? manualAdvisory : advisory;
  const scanCarePlan = careProtocols && advisory ? buildCarePlan(careProtocols, conditionId, advisory, language) : null;
  const manualCarePlan = careProtocols && manualAdvisory ? buildCarePlan(careProtocols, manualCareId, manualAdvisory, language) : null;
  function openCareLibrary() { setLibraryOrigin(screen === 'result' || screen === 'guidance' ? screen : 'home'); setLibraryQuestioning(false); navigate('care_library'); }
  function selectLibraryCondition(id: string) { setManualCareId(id); setManualConcern(null); setLibraryQuestioning(false); navigate('care_detail'); }
  function retryCareProtocols() {
    setProtocolsFailed(false);
    void loadCareProtocols().then(setCareProtocols).catch(() => setProtocolsFailed(true));
  }
  function treatmentPanel(plan: ReturnType<typeof buildCarePlan>) {
    return plan && careProtocols ? <TreatmentPlan plan={plan} model={careProtocols} language={language} audioPaths={treatmentAudioPaths} /> : protocolsFailed ? <div role="status" data-testid="treatment-load-error"><p className="hint">{c('failure')}</p><button className="secondary" data-testid="care-protocols-retry" onClick={retryCareProtocols}>{c('retry')}</button></div> : !careProtocols ? <p className="hint" role="status" data-testid="treatment-loading">{c('loading')}</p> : null;
  }


  function detailedCare(result: AdvisoryResult, plan: ReturnType<typeof buildCarePlan>, onQuestions?: () => void) {
    if (!advisoryModel) return null;
    // Priority remains above the full protocol. Older generic care is a fallback,
    // rather than a second long plan below the condition-specific instructions.
    return plan ? <>
      <AdvisoryPanel result={result} model={advisoryModel} language={language} onQuestions={onQuestions} showPriorityAudio />
      {treatmentPanel(plan)}
    </> : <AdvisoryPanel result={result} model={advisoryModel} language={language} onQuestions={onQuestions} detailed treatmentContent={treatmentPanel(null)} />;
  }

  async function saveScan() {
    if (saving || savedId || opened || !assessment || !photo) return;
    setSaving(true);
    try {
      const record = await saveObservation({
        cropId: crop,
        photoBlob: await historyPhoto(photo),
        resultType: assessment.type,
        conditionId: top?.id || null,
        score: top?.score ?? null,
        modelVersion: assessment.modelVersion,
        inferenceMs: assessment.inferenceMs,
        validated: assessment.validated,
        concern,
        note: nonLeaf ? 'NOT_A_LEAF' : unsupportedImage ? 'UNSUPPORTED_IMAGE' : unfamiliarLeaf ? 'LEAF_CHECKED_UNCERTAIN' : '',
      });
      setSavedId(record.id);
      await refreshHistory();
    } catch {
      setError(
        t(
          'Could not save. Browser storage may be full or disabled.',
          'ಉಳಿಸಲಾಗಲಿಲ್ಲ. ಬ್ರೌಸರ್ ಸಂಗ್ರಹವನ್ನು ಪರಿಶೀಲಿಸಿ.',
        ),
      );
    } finally {
      setSaving(false);
    }
  }
  function openScan(record: ObservationRecord) {
    setOpened(record);
    setAssessment(null);
    setConcern(record.concern);
    setConcernComplete(false);
    setAnswers(Array(6).fill(null));
    setScreen('result');
  }
  function beginConcern() { setLibraryQuestioning(false); startConcern(currentConcern); }
  function beginLibraryConcern() { setLibraryQuestioning(true); startConcern(manualConcern); }
  function startConcern(previous: ConcernResult | null) {
    setCareSaved(false);
    setQuestion(0);
    const x = previous?.reportedSymptoms;
    const yesNo = (answer: boolean | undefined) => !x || x.uncertainAnswers || typeof answer !== 'boolean' ? null : answer ? 0 : 1;
    setAnswers(x ? [yesNo(x.spreadingQuickly), ['NO_VISIBLE_DAMAGE','FEW_SPOTS','SOME_SPOTS','MANY_SPOTS','NOT_REPORTED'].indexOf(x.leafCoverage), yesNo(x.manyPlantsAffected), yesNo(x.wiltingOrDying), yesNo(x.fruitOrStemAffected), yesNo(x.wetWeather)] : Array(6).fill(null));
    setConcernComplete(false);
    setScreen('concern');
  }
  function nextConcern() {
    if (answers[question] === null) return;
    if (question < 5) {
      setQuestion(question + 1);
      return;
    }
    const coverage: LeafCoverage = ['NO_VISIBLE_DAMAGE', 'FEW_SPOTS', 'SOME_SPOTS', 'MANY_SPOTS', 'NOT_REPORTED'][answers[1] ?? 4] as LeafCoverage;
    const reported: ReportedSymptoms = {
      ...EMPTY_SYMPTOMS,
      spreadingQuickly: answers[0] === 0,
      manyPlantsAffected: answers[2] === 0,
      wiltingOrDying: answers[3] === 0,
      fruitOrStemAffected: answers[4] === 0,
      wetWeather: answers[5] === 0,
      leafCoverage: coverage,
      uncertainAnswers: answers.some((answer, index) => answer === null || answer === (index === 1 ? 4 : 2)),
    };
    const summary = summarizeConcern(reported);
    if (advisoryModel) {
      const next = evaluateAdvisory(advisoryModel, libraryQuestioning ? manualCareId : conditionId, reported, libraryQuestioning ? 'uncertain' : resultType);
      summary.level = next.urgency === 'MONITOR' ? 'OBSERVE_AND_RECHECK' : 'SEEK_LOCAL_EXPERT';
    }
    if (libraryQuestioning) setManualConcern(summary);
    else setConcern(summary);
    setConcernComplete(true);
  }

  async function saveCarePlan() {
    const id = opened?.id || savedId;
    if (!id || !concern || saving) return;
    setSaving(true);
    try {
      const record = await updateObservationConcern(id, concern);
      if (opened) setOpened(record);
      setCareSaved(true);
      await refreshHistory();
    } catch (failure) { setError(failure instanceof Error ? failure.message : String(failure)); }
    finally { setSaving(false); }
  }

  const languageToggle = (
    <div className="language-toggle" aria-label={t('Language', 'Language')}>
      {LANGUAGES.map((value) => (
        <button
          key={value}
          data-testid={`language-${value}`}
          lang={value}
          className={language === value ? 'active' : ''}
          aria-pressed={language === value}
          onClick={() => changeLanguage(value)}
        >
          {LANGUAGE_LABELS[value]}
        </button>
      ))}
    </div>
  );
  const offlineBadge = (
    <span className={`offline-badge ${offlineReady ? '' : 'preparing'}`}>
      {offlineReady
        ? t('Offline ready', 'ಆಫ್‌ಲೈನ್ ಸಿದ್ಧ')
        : t('Preparing offline', 'ಆಫ್‌ಲೈನ್ ಸಿದ್ಧವಾಗುತ್ತಿದೆ')}
    </span>
  );
  function topBar(back: Screen, right?: ReactNode) {
    return (
      <div className="top-bar">
        <button className="icon-button" aria-label={t('Back', 'Back')} onClick={() => navigate(back)}>
          <ArrowLeft size={22} />
        </button>
        {right}
      </div>
    );
  }
  function cropChips(
    value: CropId | 'all',
    select: (value: CropId | 'all') => void,
    includeAll = false,
  ) {
    return (
      <div className="crop-list" aria-label={t('Crop', 'Crop')}>
        {includeAll && (
          <button
            className={`crop-chip ${value === 'all' ? 'active' : ''}`}
            onClick={() => select('all')}
          >
            {t('All', 'ಎಲ್ಲಾ')}
          </button>
        )}
        {CROPS.map((item) => (
          <button
            key={item.id}
            className={`crop-chip ${value === item.id ? 'active' : ''}`}
            data-testid={`crop-${item.id}`}
            aria-pressed={value === item.id}
            onClick={() => select(item.id)}
          >
            {cropName(item.id, language)}
          </button>
        ))}
      </div>
    );
  }
  const expertButton = (
    <button className="expert-button" onClick={() => setExpertOpen(true)}>
      <Phone size={17} />
      {t('Contact a local expert', 'ಸ್ಥಳೀಯ ತಜ್ಞರನ್ನು ಸಂಪರ್ಕಿಸಿ')}
    </button>
  );
  function historyCard(record: ObservationRecord, deletable = false) {
    const acceptedRecord = record.resultType === 'likely' || record.resultType === 'healthy';
    const predictedRecord = (record.resultType === 'uncertain' || record.resultType === 'crop_mismatch') && !!record.conditionId &&
      ((record.modelVersion === model?.version && model?.sourceEvaluated === true) || record.note === 'LEAF_CHECKED_UNCERTAIN');
    const label =
      (acceptedRecord || predictedRecord) && record.conditionId
        ? conditionName(record.conditionId, language)
        : record.note === 'NOT_A_LEAF' ? t('No clear leaf detected', 'ಸ್ಪಷ್ಟ ಎಲೆ ಪತ್ತೆಯಾಗಲಿಲ್ಲ') : t('Uncertain result', 'ಅನಿಶ್ಚಿತ ಫಲಿತಾಂಶ');
    return (
      <div className="history-card" key={record.id} data-testid={`observation-${record.id}`}>
        <button
          className="history-open"
          onClick={() => openScan(record)}
          aria-label={`${cropName(record.cropId, language)} ${label}`}
        >
          <Photo alt={t('Selected crop leaf', 'Selected crop leaf')} blob={record.photoBlob} />
          <span className="history-copy">
            <strong>{label}</strong>
            <small>
              {predictedRecord && `${record.resultType === 'crop_mismatch' ? t('Crop mismatch', 'ಬೆಳೆ ಹೊಂದಿಕೆಯಾಗಿಲ್ಲ') : record.note === 'LEAF_CHECKED_UNCERTAIN' ? t('Uncertain model candidate', 'ಅನಿಶ್ಚಿತ ಮಾದರಿ ಊಹೆ') : t('Low confidence prediction', 'ಕಡಿಮೆ ವಿಶ್ವಾಸದ ಅಂದಾಜು')} · `}
              {cropName(record.cropId, language)} ·{' '}
              {new Date(record.createdAt).toLocaleTimeString(
                LANGUAGE_LOCALES[language],
                { hour: 'numeric', minute: '2-digit' },
              )}
              {record.score !== null
                ? ` · ${Math.round(record.score * 100)}% ${t('model score', 'ಮಾದರಿ ಅಂಕ')}`
                : ''}
            </small>
            <span className="concern-pill">
              {record.concern?.level === 'SEEK_LOCAL_EXPERT'
                ? t('Expert follow-up', 'ತಜ್ಞರ ಸಲಹೆ')
                : record.concern
                  ? t('Observe & recheck', 'ಗಮನಿಸಿ, ಮರುಪರಿಶೀಲಿಸಿ')
                  : acceptedRecord
                    ? t('Model match', 'ಮಾದರಿಯ ಹೊಂದಾಣಿಕೆ')
                    : t('Not confirmed', 'ಖಚಿತವಲ್ಲ')}
            </span>
          </span>
        </button>
        {deletable ? (
          <button
            className="icon-button"
            data-testid={`delete-${record.id}`}
            aria-label={t('Delete scan', 'ದಾಖಲೆ ಅಳಿಸಿ')}
            onClick={() => setDeleteTarget(record)}
          >
            <Trash2 size={16} />
          </button>
        ) : (
          <ChevronRight size={17} />
        )}
      </div>
    );
  }

  let page: ReactNode;
  if (screen === 'home')
    page = (
      <>
        <main className="app-page">
          <div className="home-top">
            {offlineBadge}
            {languageToggle}
          </div>
          <div className="heading-copy">
            <h1>{t('Check your crop', 'ನಿಮ್ಮ ಬೆಳೆ ಪರಿಶೀಲಿಸಿ')}</h1>
            <p>
              {t(
                'Take a photo of one leaf. No internet needed after setup.',
                'ಒಂದು ಎಲೆಯ ಚಿತ್ರ ತೆಗೆಯಿರಿ. ಸಿದ್ಧವಾದ ನಂತರ ಇಂಟರ್ನೆಟ್ ಬೇಡ.',
              )}
            </p>
          </div>
          <button className="scan-hero" data-testid="home-scan" onClick={() => navigate('capture')}>
            <span className="hero-camera">
              <Camera size={27} />
            </span>
            <span className="hero-bottom">
              <span>
                <strong>{t('Scan a leaf', 'ಎಲೆ ಪರಿಶೀಲಿಸಿ')}</strong>
                <small>{t('A little clarity for your crop', 'ನಿಮ್ಮ ಬೆಳೆ ಬಗ್ಗೆ ತಿಳಿಯಿರಿ')}</small>
              </span>
              <ArrowRight size={21} />
            </span>
          </button>
          <button className="secondary care-library-entry" data-testid="open-care-library" onClick={openCareLibrary}><Sprout size={19} />{c('library')}</button>
          <div className="section-heading">
            <h2>{t('Choose your crop', 'ನಿಮ್ಮ ಬೆಳೆ ಆಯ್ಕೆಮಾಡಿ')}</h2>
          </div>
          {cropChips(crop, (value) => value !== 'all' && setCrop(value))}
          <div className="section-heading">
            <h2>{t('Recent scans', 'ಇತ್ತೀಚಿನ ದಾಖಲೆಗಳು')}</h2>
            <button className="text-button" onClick={() => navigate('history')}>
              {t('View all', 'ಎಲ್ಲಾ ನೋಡಿ')}
            </button>
          </div>
          {historyLoading ? (
            <div className="soft-card">
              <p>{t('Opening saved scans…', 'ದಾಖಲೆಗಳನ್ನು ತೆರೆಯಲಾಗುತ್ತಿದೆ…')}</p>
            </div>
          ) : history.length ? (
            history.slice(0, 2).map((item) => historyCard(item))
          ) : (
            <div className="soft-card empty-card">
              <Sprout size={28} />
              <h3>{t('Your first leaf starts here', 'ಮೊದಲ ಎಲೆಯಿಂದ ಆರಂಭಿಸಿ')}</h3>
              <p>
                {t(
                  'Scan a leaf and save your observation. Your photos stay on this device.',
                  'ಎಲೆ ಪರಿಶೀಲಿಸಿ, ದಾಖಲೆಯನ್ನು ಉಳಿಸಿ. ಚಿತ್ರಗಳು ಈ ಸಾಧನದಲ್ಲೇ ಇರುತ್ತವೆ.',
                )}
              </p>
            </div>
          )}
          <p className="privacy-note">
            {t(
              'Review 2 prototype · Model results are not a confirmed diagnosis.',
              'ಪರಿಶೀಲನೆ 2 ಮಾದರಿ · ಫಲಿತಾಂಶ ಖಚಿತ ರೋಗನಿರ್ಣಯವಲ್ಲ.',
            )}
          </p>
        </main>
      </>
    );
  else if (screen === 'capture')
    page = (
      <CameraCapture
        crop={crop}
        language={language}
        onBack={() => navigate('home')}
        onGallery={() => upload.current?.click()}
        onPhoto={selectPhoto}
        onLanguage={() => changeLanguage(LANGUAGES[(LANGUAGES.indexOf(language) + 1) % LANGUAGES.length])}
      />
    );
  else if (screen === 'photo')
    page = (
      <>
        {topBar('capture', languageToggle)}
        <main className="app-page with-top">
          <div className="heading-copy">
            <h1>{t('Ready to check?', 'ಪರಿಶೀಲಿಸಲು ಸಿದ್ಧವೇ?')}</h1>
            <p>
              {cropName(crop, language)} · {t('One clear leaf is best', 'ಒಂದು ಸ್ಪಷ್ಟ ಎಲೆ ಉತ್ತಮ')}
            </p>
          </div>
          <Photo alt={t('Selected crop leaf', 'Selected crop leaf')} blob={photo} className="photo-review" />
          <div className="soft-card">
            <h3>{t('A quick photo check', 'ಚಿತ್ರವನ್ನು ಪರಿಶೀಲಿಸಿ')}</h3>
            <p>
              {t(
                'Is the leaf clear, well lit and filling most of the photo? Avoid hands, several leaves and very dark images.',
                'ಎಲೆ ಸ್ಪಷ್ಟವಾಗಿ ಬೆಳಕಿನಲ್ಲಿ ಕಾಣುತ್ತಿದೆಯೇ? ಕೈಗಳು, ಹಲವು ಎಲೆಗಳು ಮತ್ತು ಕತ್ತಲಾದ ಚಿತ್ರಗಳನ್ನು ತಪ್ಪಿಸಿ.',
              )}
            </p>
          </div>
          <div className="button-stack">
            <button
              className="primary"
              data-testid="analyze-photo"
              disabled={!photo}
              onClick={() => void analyze()}
            >
              <Leaf size={18} />
              {t('Analyse leaf', 'ಎಲೆ ಪರಿಶೀಲಿಸಿ')}
            </button>
            <button className="secondary" onClick={() => navigate('capture')}>
              {t('Retake photo', 'ಮತ್ತೆ ಚಿತ್ರ ತೆಗೆಯಿರಿ')}
            </button>
          </div>
          <p className="privacy-note">
            {t(
              'Analysis runs on your device. Your photo is never uploaded.',
              'ಪರಿಶೀಲನೆ ನಿಮ್ಮ ಸಾಧನದಲ್ಲೇ ನಡೆಯುತ್ತದೆ. ಚಿತ್ರ ಅಪ್‌ಲೋಡ್ ಆಗುವುದಿಲ್ಲ.',
            )}
          </p>
        </main>
      </>
    );
  else if (screen === 'processing')
    page = (
      <>
        {topBar('photo')}
        <main className="app-page processing">
          <div className="spinner" />
          <h2>{t('Looking at your leaf', 'ಎಲೆಯನ್ನು ಪರಿಶೀಲಿಸಲಾಗುತ್ತಿದೆ')}</h2>
          <p>
            {t(
              'Running the crop model on this device. The first check may take a little longer.',
              'ಈ ಸಾಧನದಲ್ಲಿ ಬೆಳೆ ಮಾದರಿ ಚಾಲನೆಯಲ್ಲಿದೆ. ಮೊದಲ ಪರಿಶೀಲನೆಗೆ ಸ್ವಲ್ಪ ಹೆಚ್ಚು ಸಮಯ ಬೇಕಾಗಬಹುದು.',
            )}
          </p>
          <span className="offline-badge">{t('Photo stays here', 'ಚಿತ್ರ ಇಲ್ಲೇ ಇರುತ್ತದೆ')}</span>
        </main>
      </>
    );
  else if (screen === 'result')
    page = (
      <>
        {topBar(
          opened ? 'history' : 'home',
          <span className="offline-badge">
            {t('Analysed on device', 'ಸಾಧನದಲ್ಲೇ ಪರಿಶೀಲಿಸಲಾಗಿದೆ')}
          </span>,
        )}
        <main className="app-page with-top">
          <div className="result-heading">
            <Photo alt={t('Selected crop leaf', 'Selected crop leaf')} blob={activePhoto} />
            <div>
              <small>{cropName(hasPrediction ? predictedCrop : activeCrop, language)}</small>
              <h2>
                {nonLeaf ? t('No clear leaf detected', 'ಸ್ಪಷ್ಟ ಎಲೆ ಪತ್ತೆಯಾಗಲಿಲ್ಲ') : hasPrediction && conditionId
                  ? conditionName(conditionId, language)
                  : resultType === 'retake'
                    ? t('Try another photo', 'ಮತ್ತೊಂದು ಚಿತ್ರ ಪ್ರಯತ್ನಿಸಿ')
                    : resultType === 'model_unavailable'
                      ? t('Model unavailable', 'ಮಾದರಿ ಲಭ್ಯವಿಲ್ಲ')
                      : t('Let’s take a closer look', 'ಇನ್ನಷ್ಟು ಪರಿಶೀಲಿಸೋಣ')}
              </h2>
            </div>
          </div>
          <div className={accepted ? 'soft-card' : 'alert-card'} data-testid="result-status" data-result-type={resultType}>
            <div className="alert-title">
              {accepted ? <CheckCircle2 size={22} /> : <AlertCircle size={22} />}
              <h2>
                {nonLeaf ? t('Please photograph a crop leaf', 'ಬೆಳೆ ಎಲೆಯ ಚಿತ್ರ ತೆಗೆಯಿರಿ') : accepted
                  ? t('Model match', 'ಮಾದರಿಯ ಹೊಂದಾಣಿಕೆ')
                  : cropMismatchPrediction
                    ? t('Crop mismatch', 'ಬೆಳೆ ಹೊಂದಿಕೆಯಾಗಿಲ್ಲ')
                  : provisionalPrediction
                    ? unfamiliarLeaf ? t('Uncertain model candidate', 'ಅನಿಶ್ಚಿತ ಮಾದರಿ ಊಹೆ') : t('Low confidence prediction', 'ಕಡಿಮೆ ವಿಶ್ವಾಸದ ಅಂದಾಜು')
                  : resultType === 'retake'
                    ? t('A clearer photo will help', 'ಸ್ಪಷ್ಟ ಚಿತ್ರ ಸಹಾಯ ಮಾಡುತ್ತದೆ')
                    : resultType === 'model_unavailable'
                      ? t('Unable to run the model', 'ಮಾದರಿಯನ್ನು ಚಲಾಯಿಸಲಾಗಲಿಲ್ಲ')
                      : t('Not sure about this one', 'ಈ ಬಗ್ಗೆ ಖಚಿತವಿಲ್ಲ')}
              </h2>
            </div>
            {nonLeaf ? <p>{t('This does not look like a clear leaf photo. Take a close-up of one tomato, potato or maize leaf.', 'ಸ್ಪಷ್ಟ ಎಲೆಯ ಚಿತ್ರ ಕಾಣಿಸುತ್ತಿಲ್ಲ. ಒಂದು ಟೊಮ್ಯಾಟೊ, ಆಲೂಗಡ್ಡೆ ಅಥವಾ ಮೆಕ್ಕೆಜೋಳದ ಎಲೆಯ ಹತ್ತಿರದ ಚಿತ್ರ ತೆಗೆಯಿರಿ.')}</p> : accepted ? (
              <p>
                {t(
                  'Dataset-tested estimate. Confirm the condition with a local crop expert.',
                  'ಡೇಟಾಸೆಟ್‌ನಲ್ಲಿ ಪರೀಕ್ಷಿಸಿದ ಅಂದಾಜು. ಸ್ಥಳೀಯ ಕೃಷಿ ತಜ್ಞರಿಂದ ಸ್ಥಿತಿಯನ್ನು ಖಚಿತಪಡಿಸಿಕೊಳ್ಳಿ.',
                )}
              </p>
            ) : cropMismatchPrediction ? <p>
              {t('Selected crop', 'ಆಯ್ಕೆ ಮಾಡಿದ ಬೆಳೆ')}: {cropName(activeCrop, language)}.<br />
              {t('Model predicts', 'ಮಾದರಿಯ ಅಂದಾಜು')}: {cropName(predictedCrop, language)}.<br />
              {t('Check the crop selection or retake a clear photo of one leaf.', 'ಬೆಳೆ ಆಯ್ಕೆಯನ್ನು ಪರಿಶೀಲಿಸಿ ಅಥವಾ ಒಂದು ಎಲೆಯ ಸ್ಪಷ್ಟ ಚಿತ್ರವನ್ನು ಮತ್ತೆ ತೆಗೆಯಿರಿ.')}
            </p> : <p>{unfamiliarLeaf
              ? t('A leaf was detected. This is the closest model match, but the photo differs from its training examples. Check the result with a clearer photo or a crop expert.', 'ಎಲೆ ಪತ್ತೆಯಾಗಿದೆ. ಇದು ಮಾದರಿಯ ಹತ್ತಿರದ ಹೊಂದಾಣಿಕೆ, ಆದರೆ ಚಿತ್ರ ತರಬೇತಿ ಉದಾಹರಣೆಗಳಿಂದ ಭಿನ್ನವಾಗಿದೆ. ಸ್ಪಷ್ಟ ಚಿತ್ರ ಅಥವಾ ಕೃಷಿ ತಜ್ಞರಿಂದ ಫಲಿತಾಂಶ ಪರಿಶೀಲಿಸಿ.')
              : provisionalPrediction
              ? t('This is the model’s top prediction for your leaf. Retake a clearer photo to check the result.', 'ಇದು ನಿಮ್ಮ ಎಲೆಗೆ ಮಾದರಿಯ ಪ್ರಮುಖ ಅಂದಾಜು. ಫಲಿತಾಂಶ ಪರಿಶೀಲಿಸಲು ಇನ್ನಷ್ಟು ಸ್ಪಷ್ಟ ಚಿತ್ರ ತೆಗೆಯಿರಿ.')
              : resultPrompt.message}</p>}
            {!accepted && !validated && !model?.sourceEvaluated && (
              <p>
                {t(
                  'This prototype model has not been validated for disease diagnosis. Scores below are model outputs, not diagnostic confidence.',
                  'ಈ ಮಾದರಿಯ ರೋಗನಿರ್ಣಯವನ್ನು ದೃಢೀಕರಿಸಿಲ್ಲ. ಕೆಳಗಿನ ಅಂಕಗಳು ಮಾದರಿಯ ಫಲಿತಾಂಶಗಳು; ರೋಗದ ಖಚಿತತೆ ಅಲ್ಲ.',
                )}
              </p>
            )}
          </div>
          {score !== null && (
            <div className="soft-card">
              <div className="score-heading">
                <span>{accepted ? t('Model match score', 'ಮಾದರಿಯ ಹೊಂದಾಣಿಕೆ ಅಂಕ') : hasPrediction ? t('Prediction score', 'ಅಂದಾಜಿನ ಅಂಕ') : t('Top model score', 'ಅತ್ಯಧಿಕ ಮಾದರಿ ಅಂಕ')}</span>
                <strong>{Math.round(score * 100)}%</strong>
              </div>
              <div className={`score-track ${validated ? 'validated' : ''}`}>
                <i style={{ width: `${Math.max(0, Math.min(100, score * 100))}%` }} />
              </div>
              <span className="score-note">
                {accepted ? t(
                  'Model score for this image, not field accuracy.',
                  'ಈ ಚಿತ್ರದ ಮಾದರಿ ಅಂಕ; ಹೊಲದಲ್ಲಿ ಅಳೆಯಲಾದ ನಿಖರತೆ ಅಲ್ಲ.',
                ) : t(
                  'A high score does not prove that the diagnosis is correct.',
                  'ಹೆಚ್ಚಿನ ಅಂಕ ಬಂದರೂ ರೋಗನಿರ್ಣಯ ಸರಿಯಾಗಿದೆ ಎಂದರ್ಥವಲ್ಲ.',
                )}
              </span>
              {opened && conditionId && (
                <div className="prediction">
                  <strong>{conditionName(conditionId, language)}</strong>
                  <span>{accepted ? t('Saved model match', 'ಉಳಿಸಿದ ಮಾದರಿಯ ಹೊಂದಾಣಿಕೆ') : cropMismatchPrediction ? t('Crop mismatch', 'ಬೆಳೆ ಹೊಂದಿಕೆಯಾಗಿಲ್ಲ') : provisionalPrediction ? t('Saved prediction · low confidence', 'ಉಳಿಸಿದ ಅಂದಾಜು · ಕಡಿಮೆ ವಿಶ್ವಾಸ') : t('Stored candidate · not confirmed', 'ಉಳಿಸಿದ ಸಾಧ್ಯತೆ · ಖಚಿತವಲ್ಲ')}</span>
                </div>
              )}
              {!unsupportedImage && assessment?.candidates.slice(0, 2).map((item, index) => (
                <div className="prediction" key={item.id}>
                  <div>
                    <strong>{conditionName(item.id, language)}</strong>
                    <p>
                      {cropName(item.cropId, language)} · {accepted ? index === 0 ? t('Model match', 'ಮಾದರಿಯ ಹೊಂದಾಣಿಕೆ') : t('Other candidate', 'ಇನ್ನೊಂದು ಸಾಧ್ಯತೆ') : hasPrediction ? index === 0 ? t('Top prediction', 'ಪ್ರಮುಖ ಅಂದಾಜು') : t('Alternative prediction', 'ಪರ್ಯಾಯ ಅಂದಾಜು') : t('not confirmed', 'ಖಚಿತವಲ್ಲ')}
                    </p>
                  </div>
                  <span>{(item.score * 100).toFixed(1)}%</span>
                </div>
              ))}
            </div>
          )}
          {!nonLeaf && assessment?.qualityIssues && assessment.qualityIssues.length > 0 && (
            <p className="hint">
              {t('Photo check: ', 'ಚಿತ್ರ ಪರಿಶೀಲನೆ: ')}
              {assessment.qualityIssues.map(issue => t(issue.replaceAll('_', ' '), issue.replaceAll('_', ' '))).join(', ')}
            </p>
          )}
          <AudioPlayer
            language={language}
            src={catalogReady ? resultPrompt.audioAsset : null}
            label={t('Listen in English', 'ಕನ್ನಡದಲ್ಲಿ ಕೇಳಿ')}
            compact
          />
          {advisory && advisoryModel && !nonLeaf && <AdvisoryPanel result={advisory} language={language} model={advisoryModel} />}
          {advisoryFailed && <p className="hint">{a('failure')}</p>}
          <div className="button-stack">
            <button className="secondary" data-testid="result-care-library" onClick={openCareLibrary}>{c('library')}</button>
            {cropMismatchPrediction && <button className="secondary" onClick={() => navigate('home')}>
              {t('Change selected crop', 'ಆಯ್ಕೆ ಮಾಡಿದ ಬೆಳೆಯನ್ನು ಬದಲಿಸಿ')}
            </button>}
            {!accepted && !nonLeaf && expertButton}
            {!nonLeaf && <>
            <button className="primary" onClick={beginConcern}>
              {a('questions')}
            </button>
            <button className="secondary" onClick={() => navigate('guidance')}>
              {t('See guidance', 'ಸಲಹೆ ನೋಡಿ')}
            </button>
            </>}
            <button className="secondary" onClick={() => navigate('capture')}>
              {t('Retake photo', 'ಮತ್ತೆ ಚಿತ್ರ ತೆಗೆಯಿರಿ')}
            </button>
            <button
              className="secondary"
              data-testid="save-scan"
              disabled={saving || !!savedId || !!opened || !assessment}
              onClick={() => void saveScan()}
            >
              {savedId || opened ? (
                <Check size={17} />
              ) : saving ? (
                <LoaderCircle size={17} />
              ) : (
                <Download size={17} />
              )}
              {savedId || opened
                ? t('Saved on this device', 'ಈ ಸಾಧನದಲ್ಲಿ ಉಳಿಸಲಾಗಿದೆ')
                : saving
                  ? t('Saving…', 'ಉಳಿಸಲಾಗುತ್ತಿದೆ…')
                  : t('Save scan', 'ದಾಖಲೆ ಉಳಿಸಿ')}
            </button>
          </div>
          <p className="privacy-note">
            {t(
              'Avoid selecting a treatment from a model score. Confirm the cause with a qualified local expert.',
              'ಮಾದರಿ ಅಂಕದಿಂದ ಚಿಕಿತ್ಸೆ ಆಯ್ಕೆ ಮಾಡಬೇಡಿ. ಅರ್ಹ ಸ್ಥಳೀಯ ತಜ್ಞರ ಮೂಲಕ ಕಾರಣ ಖಚಿತಪಡಿಸಿಕೊಳ್ಳಿ.',
            )}
          </p>
        </main>
      </>
    );
  else if (screen === 'guidance') {
    page = <>
      {topBar('result', languageToggle)}
      <main className="app-page with-top">
        <div className="heading-copy">
          <h1 data-testid="guidance-heading">{t('Care for your crop', 'ನಿಮ್ಮ ಬೆಳೆ ಆರೈಕೆ')}</h1>
          <p>{cropName(activeCrop, language)} · {conditionId ? conditionName(conditionId, language) : a('generic')}</p>
        </div>
        {advisory && advisoryModel ? detailedCare(advisory, scanCarePlan, beginConcern) : <p>{advisoryFailed ? a('failure') : t('Loading…', 'ಲೋಡ್ ಆಗುತ್ತಿದೆ…')}</p>}
        <button className="secondary" onClick={openCareLibrary}>{c('library')}</button>
        {expertButton}
      </main>
    </>;
  } else if (screen === 'care_library') {
    const query = librarySearch.trim().toLocaleLowerCase();
    const matches = CONDITIONS.filter(item => (libraryCrop === 'all' || item.crop_id === libraryCrop) &&
      (!query || [conditionName(item.id, language), item.name_en, cropName(item.crop_id, language), item.id].some(text => text.toLocaleLowerCase().includes(query))));
    page = <>{topBar(libraryOrigin, languageToggle)}<main className="app-page with-top">
      <div className="heading-copy"><h1>{c('library')}</h1><p>{c('libraryHint')}</p></div>
      <input className="care-search" type="search" aria-label={c('search')} placeholder={c('search')} value={librarySearch} onChange={event => setLibrarySearch(event.target.value)} data-testid="care-library-search" />
      {cropChips(libraryCrop, setLibraryCrop, true)}
      <div className="care-library-list" data-testid="care-library-list">{matches.map(item => <button className="care-library-card" key={item.id} onClick={() => selectLibraryCondition(item.id)} data-testid={`care-condition-${item.id}`}><span className="scan-thumb empty"><Leaf size={23} /></span><span><strong>{conditionName(item.id, language)}</strong><small>{cropName(item.crop_id, language)}</small></span><ChevronRight size={20} /></button>)}</div>
      {!matches.length && <p>{c('empty')}</p>}
      <button className="secondary" data-testid="care-library-back" onClick={() => navigate(libraryOrigin)}>{libraryOrigin === 'home' ? t('Home', 'ಮುಖಪುಟ') : t('Back to result', 'ಫಲಿತಾಂಶಕ್ಕೆ ಹಿಂತಿರುಗಿ')}</button>
    </main></>;
  } else if (screen === 'care_detail') {
    const selectedLabel = CONDITIONS.find(item => item.id === manualCareId);
    page = <>{topBar('care_library', languageToggle)}<main className="app-page with-top">
      <div className="heading-copy"><h1 data-testid="manual-care-heading">{manualCareId ? conditionName(manualCareId, language) : c('library')}</h1><p>{selectedLabel && cropName(selectedLabel.crop_id, language)}</p></div>
      <p className="manual-care-notice" data-testid="manual-care-notice">{c('selected')}</p>
      {manualAdvisory && advisoryModel ? detailedCare(manualAdvisory, manualCarePlan, beginLibraryConcern) : <p>{advisoryFailed ? a('failure') : t('Loading…', 'ಲೋಡ್ ಆಗುತ್ತಿದೆ…')}</p>}
      {expertButton}
    </main></>;
  } else if (screen === 'concern') {
    const keys = ['concern_spreading', 'concern_coverage', 'concern_plants'];
    const questions = Array.from({ length: 6 }, (_, index) => a(`question${index}` as AdvisoryTextKey));
    const options = question === 1
      ? [a('none'), a('few'), a('some'), a('many'), a('unsure')]
      : [a('yes'), a('no'), a('unsure')];
    page = (
      <>
        {topBar(
          libraryQuestioning ? 'care_detail' : 'result',
          !concernComplete ? (
            <span className="hint">
              {language === 'hi' ? `प्रश्न ${question + 1} / 6` : language === 'kn' ? `ಪ್ರಶ್ನೆ ${question + 1} / 6` : `Question ${question + 1} of 6`}
            </span>
          ) : null,
        )}
        <main className="app-page with-top">
          {concernComplete ? (
            <>
              <div className="heading-copy" data-testid="concern-summary"><h1>{a('title')}</h1><p>{(libraryQuestioning ? manualCareId : conditionId) ? conditionName((libraryQuestioning ? manualCareId : conditionId)!, language) : a('generic')}</p></div>
              {questionAdvisory && advisoryModel && detailedCare(questionAdvisory, libraryQuestioning ? manualCarePlan : scanCarePlan)}
              {advisoryFailed && <p>{a('failure')}</p>}
              {questionAdvisory?.urgency !== 'MONITOR' && expertButton}
              <button className="primary" onClick={() => navigate(libraryQuestioning ? 'care_detail' : 'guidance')}>
                {t('See guidance', 'ಸಲಹೆ ನೋಡಿ')}
              </button>
              <button className="secondary" onClick={() => navigate(libraryQuestioning ? 'care_detail' : 'result')}>
                {libraryQuestioning ? c('library') : t('Back to result', 'ಫಲಿತಾಂಶಕ್ಕೆ ಹಿಂತಿರುಗಿ')}
              </button>
              {!libraryQuestioning && (opened || savedId) && <button className="secondary" onClick={saveCarePlan} disabled={saving || careSaved} data-testid="save-care-plan">
                {careSaved ? (language === 'hi' ? 'देखभाल के उत्तर सहेजे गए' : language === 'kn' ? 'ಆರೈಕೆ ಉತ್ತರ ಉಳಿಸಲಾಗಿದೆ' : 'Care answers saved') : (language === 'hi' ? 'देखभाल के उत्तर सहेजें' : language === 'kn' ? 'ಆರೈಕೆ ಉತ್ತರ ಉಳಿಸಿ' : 'Save care answers')}
              </button>}
            </>
          ) : (
            <>
              <div className="question-progress">
                <i style={{ width: `${((question + 1) / 6) * 100}%` }} />
              </div>
              <p>
                {cropName(libraryQuestioning ? CONDITIONS.find(x => x.id === manualCareId)?.crop_id || activeCrop : activeCrop, language)} · {t('Your observations', 'ನಿಮ್ಮ ಗಮನಿಸುವಿಕೆ')}
              </p>
              <h1 className="question-title">{questions[question]}</h1>
              <AudioPlayer
            language={language}
                compact
                src={catalogReady ? question === 1 ? assetUrl(`audio/${language}/advisory_question_coverage.ogg`) : question < 3 ? getPrompt(keys[question], language).audioAsset : assetUrl(`audio/${language}/advisory_question_${['wilting', 'fruit_stem', 'wet_weather'][question - 3]}.ogg`) : null}
                label={t('Read question aloud', 'ಪ್ರಶ್ನೆ ಕೇಳಿ')}
              />
              <div className="button-stack" role="radiogroup" aria-label={questions[question]}>
                {options.map((option, index) => (
                  <button
                    key={`${question}-${index}`}
                    className={`question-option ${answers[question] === index ? 'active' : ''}`}
                    role="radio"
                    aria-checked={answers[question] === index}
                    data-testid={`concern-option-${index}`}
                    onClick={() =>
                      setAnswers((previous) =>
                        previous.map((answer, i) => (i === question ? index : answer)),
                      )
                    }
                  >
                    <span className="radio-dot" />
                    {option}
                  </button>
                ))}
              </div>
              <div style={{ flex: 1 }} />
              <button
                className="primary"
                data-testid="concern-next"
                disabled={answers[question] === null}
                onClick={nextConcern}
              >
                {question === 5 ? t('See next steps', 'ಮುಂದಿನ ಕ್ರಮ ನೋಡಿ') : t('Next', 'ಮುಂದೆ')}
                <ArrowRight size={17} />
              </button>
              <p className="small-center">
                {t(
                  'Your answers help decide when to ask an expert.',
                  'ಯಾವಾಗ ತಜ್ಞರ ಸಲಹೆ ಬೇಕು ಎಂದು ತಿಳಿಯಲು ನಿಮ್ಮ ಉತ್ತರಗಳು ಸಹಾಯ ಮಾಡುತ್ತವೆ.',
                )}
              </p>
            </>
          )}
        </main>
      </>
    );
  } else if (screen === 'history') {
    const filtered = history.filter(
      (row) => historyFilter === 'all' || row.cropId === historyFilter,
    );
    let previousDate = '';
    page = (
      <main className="app-page">
        <div className="heading-copy">
          <h1>{t('History', 'ಇತಿಹಾಸ')}</h1>
          <p className="saved-copy">● {t('Saved on this device', 'ಈ ಸಾಧನದಲ್ಲಿ ಉಳಿಸಲಾಗಿದೆ')}</p>
        </div>
        {cropChips(historyFilter, setHistoryFilter, true)}
        <div data-testid="history-list" style={{ display: 'grid', gap: 11 }}>
          {historyLoading ? (
            <div className="soft-card">
              <p>{t('Opening your scans…', 'ದಾಖಲೆಗಳನ್ನು ತೆರೆಯಲಾಗುತ್ತಿದೆ…')}</p>
            </div>
          ) : filtered.length ? (
            filtered.map((record) => {
              const date = new Date(record.createdAt),
                today = new Date(),
                yesterday = new Date();
              yesterday.setDate(today.getDate() - 1);
              const dateKey = date.toDateString(),
                label =
                  dateKey === today.toDateString()
                    ? t('Today', 'ಇಂದು')
                    : dateKey === yesterday.toDateString()
                      ? t('Yesterday', 'ನಿನ್ನೆ')
                      : date.toLocaleDateString(LANGUAGE_LOCALES[language], {
                          day: 'numeric',
                          month: 'short',
                        });
              const heading = previousDate !== dateKey;
              previousDate = dateKey;
              return (
                <div key={record.id} style={{ display: 'grid', gap: 10 }}>
                  {heading && <h3 className="history-date">{label}</h3>}
                  {historyCard(record, true)}
                </div>
              );
            })
          ) : (
            <div className="soft-card empty-card">
              <History size={29} />
              <h3>{t('No saved scans yet', 'ಇನ್ನೂ ದಾಖಲೆಗಳಿಲ್ಲ')}</h3>
              <p>
                {t(
                  'Save a scan after checking a leaf. It will appear here with your photo and notes.',
                  'ಎಲೆ ಪರಿಶೀಲಿಸಿದ ನಂತರ ದಾಖಲೆಯನ್ನು ಉಳಿಸಿ. ಅದು ಚಿತ್ರದೊಂದಿಗೆ ಇಲ್ಲಿ ಕಾಣುತ್ತದೆ.',
                )}
              </p>
              <button className="text-button" onClick={() => navigate('capture')}>
                {t('Scan your first leaf', 'ಮೊದಲ ಎಲೆ ಪರಿಶೀಲಿಸಿ')} →
              </button>
            </div>
          )}
        </div>
        <p className="privacy-note">
          {t(
            'Photos and results live in this browser on this device. Clearing site data removes them.',
            'ಚಿತ್ರಗಳು ಮತ್ತು ಫಲಿತಾಂಶಗಳು ಈ ಸಾಧನದ ಬ್ರೌಸರ್‌ನಲ್ಲೇ ಇರುತ್ತವೆ. ಸೈಟ್ ಡೇಟಾ ಅಳಿಸಿದರೆ ದಾಖಲೆಗಳು ಅಳಿಯುತ್ತವೆ.',
          )}
        </p>
      </main>
    );
  } else if (screen === 'help')
    page = (
      <main className="app-page">
        <div className="section-heading">
          <div className="heading-copy">
            <h1>{t('A little help', 'ಸ್ವಲ್ಪ ಸಹಾಯ')}</h1>
            <p>{t('Better photos. Clearer next steps.', 'ಉತ್ತಮ ಚಿತ್ರಗಳು. ಸ್ಪಷ್ಟ ಮುಂದಿನ ಕ್ರಮ.')}</p>
          </div>
          <button
            className="icon-button"
            aria-label={t('Settings', 'Settings')}
            onClick={() => navigate('settings')}
          >
            <Settings size={20} />
          </button>
        </div>
        <h3>{t('Take a good leaf photo', 'ಉತ್ತಮ ಎಲೆಯ ಚಿತ್ರ ತೆಗೆಯಿರಿ')}</h3>
        {[
          [
            t('One leaf at a time', 'ಒಂದು ಬಾರಿ ಒಂದು ಎಲೆ'),
            t(
              'Fill the frame with one leaf, including the affected area.',
              'ಲಕ್ಷಣವಿರುವ ಭಾಗದೊಂದಿಗೆ ಒಂದು ಎಲೆಯನ್ನು ಚೌಕಟ್ಟಿನಲ್ಲಿ ಇರಿಸಿ.',
            ),
          ],
          [
            t('Find soft daylight', 'ಉತ್ತಮ ಹಗಲು ಬೆಳಕು'),
            t(
              'Avoid harsh shadows, glare and very dark photos.',
              'ಗಾಢ ನೆರಳು, ಮಿನುಗುವಿಕೆ ಮತ್ತು ಕತ್ತಲಾದ ಚಿತ್ರಗಳನ್ನು ತಪ್ಪಿಸಿ.',
            ),
          ],
          [
            t('Keep it steady', 'ಸ್ಥಿರವಾಗಿ ಹಿಡಿಯಿರಿ'),
            t(
              'Hold still and make sure the leaf is in focus.',
              'ಸ್ಥಿರವಾಗಿ ಹಿಡಿದು ಎಲೆ ಸ್ಪಷ್ಟವಾಗಿ ಕಾಣುವುದನ್ನು ಖಚಿತಪಡಿಸಿ.',
            ),
          ],
        ].map(([title, description], index) => (
          <div className="tip-card" key={index}>
            <span className="tip-number">{index + 1}</span>
            <div>
              <h3>{title}</h3>
              <p>{description}</p>
            </div>
          </div>
        ))}
        <div className="soft-card">
          <h3>{t('What does a score mean?', 'ಅಂಕದ ಅರ್ಥವೇನು?')}</h3>
          <p>
            {t(
              'A model score describes how the image compares with training labels. It is not proof of a disease, a field accuracy measurement or permission to spray.',
              'ಮಾದರಿ ಅಂಕವು ಚಿತ್ರ ತರಬೇತಿಯ ಲೇಬಲ್‌ಗಳಿಗೆ ಎಷ್ಟು ಹೋಲುತ್ತದೆ ಎಂದು ತಿಳಿಸುತ್ತದೆ. ಅದು ರೋಗದ ಪುರಾವೆ ಅಥವಾ ಸಿಂಪಡಣೆಗೆ ಅನುಮತಿ ಅಲ್ಲ.',
            )}
          </p>
        </div>
        <div className="settings-row">
          <div>
            <h3>{t('Language & voice', 'ಭಾಷೆ ಮತ್ತು ಧ್ವನಿ')}</h3>
            <p>{t('Bundled English, Kannada and Hindi audio', 'ಇಂಗ್ಲಿಷ್, ಕನ್ನಡ ಮತ್ತು ಹಿಂದಿ ಧ್ವನಿ')}</p>
          </div>
          {languageToggle}
        </div>
        <div className="soft-card">
          <div className={`model-status ${model?.ready ? '' : 'pending'}`}>
            {model?.ready ? <CheckCircle2 size={18} /> : <LoaderCircle size={18} />}
            <strong>
              {model?.ready
                ? `${model.name} · ${t('Installed', 'ಸಿದ್ಧ')}`
                : model
                  ? t('Model unavailable', 'ಮಾದರಿ ಲಭ್ಯವಿಲ್ಲ')
                  : t('Preparing model', 'ಮಾದರಿ ಸಿದ್ಧವಾಗುತ್ತಿದೆ')}
            </strong>
          </div>
          <p>
            {model?.sourceEvaluated ? t('Dataset-tested model · Field confirmation is still needed.', 'ಡೇಟಾಸೆಟ್‌ನಲ್ಲಿ ಪರೀಕ್ಷಿಸಿದ ಮಾದರಿ · ಹೊಲದಲ್ಲಿ ದೃಢೀಕರಣ ಇನ್ನೂ ಅಗತ್ಯ.') : t(
              'Prototype model · Disease diagnosis is not validated.',
              'ಮಾದರಿ ಆವೃತ್ತಿ · ರೋಗನಿರ್ಣಯವನ್ನು ದೃಢೀಕರಿಸಿಲ್ಲ.',
            )}
          </p>
          <button className="text-button" onClick={() => navigate('settings')}>
            {t('Model & content details', 'ಮಾದರಿ ಮತ್ತು ವಿಷಯದ ವಿವರಗಳು')} →
          </button>
        </div>
        {expertButton}
        <p className="privacy-note">
          {t(
            'For advice, contact a qualified local agriculture professional. Keep their verified number handy.',
            'ಸಲಹೆಗಾಗಿ ಅರ್ಹ ಸ್ಥಳೀಯ ಕೃಷಿ ತಜ್ಞರನ್ನು ಸಂಪರ್ಕಿಸಿ. ಅವರ ಖಚಿತ ಸಂಖ್ಯೆಯನ್ನು ಇಟ್ಟುಕೊಳ್ಳಿ.',
          )}
        </p>
      </main>
    );
  else
    page = (
      <>
        {topBar('help', languageToggle)}
        <main className="app-page with-top">
          <h1>{t('About this prototype', 'ಈ ಮಾದರಿಯ ಬಗ್ಗೆ')}</h1>
          <div className="soft-card">
            <h3>{model?.name || t('Crop disease model', 'ಬೆಳೆ ರೋಗ ಮಾದರಿ')}</h3>
            <p>
              {model?.message ? t(model.message, model.message) : t('Preparing the local model…', 'ಸ್ಥಳೀಯ ಮಾದರಿ ಸಿದ್ಧವಾಗುತ್ತಿದೆ…')}
            </p>
            <p className="model-details">
              {model?.version || t('Version loading', 'Version loading')}
              {model?.bytes ? ` · ${(model.bytes / 1024 / 1024).toFixed(1)} ${t('MB model', 'MB model')}` : ''}
              <br />
              {t(
                '17 image classes · Tomato, Potato and Maize',
                '17 ಚಿತ್ರ ವರ್ಗಗಳು · ಟೊಮ್ಯಾಟೊ, ಆಲೂಗಡ್ಡೆ ಮತ್ತು ಮೆಕ್ಕೆಜೋಳ',
              )}
              <br />
              {model?.sourceEvaluated ? t('Source test passed · Field diagnosis is not validated.', 'ಮೂಲ ಡೇಟಾ ಪರೀಕ್ಷೆಯಲ್ಲಿ ತೇರ್ಗಡೆ · ಹೊಲದ ರೋಗನಿರ್ಣಯವನ್ನು ದೃಢೀಕರಿಸಿಲ್ಲ.') : t(
                'Validation: not validated for disease diagnosis',
                'ದೃಢೀಕರಣ: ರೋಗನಿರ್ಣಯಕ್ಕೆ ದೃಢೀಕರಿಸಿಲ್ಲ',
              )}
            </p>
            {!model?.ready && (
              <button className="model-retry" onClick={() => void getModelStatus().then(setModel)}>
                {t('Retry model', 'ಮಾದರಿ ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ')}
              </button>
            )}
          </div>
          <div className="soft-card">
            <h3>{t('Offline assets', 'ಆಫ್‌ಲೈನ್ ಸಂಪನ್ಮೂಲಗಳು')}</h3>
            <p>
              {offlineReady
                ? t(
                    'App, model and content are available offline in this browser.',
                    'ಅಪ್ಲಿಕೇಶನ್, ಮಾದರಿ ಮತ್ತು ವಿಷಯ ಈ ಬ್ರೌಸರ್‌ನಲ್ಲಿ ಆಫ್‌ಲೈನ್ ಲಭ್ಯ.',
                  )
                : t(
                    'Keep this page open with internet until offline preparation finishes. Storage can be cleared by the browser.',
                    'ಆಫ್‌ಲೈನ್ ಸಿದ್ಧವಾಗುವವರೆಗೆ ಇಂಟರ್ನೆಟ್‌ನೊಂದಿಗೆ ಪುಟ ತೆರೆದಿಡಿ. ಬ್ರೌಸರ್ ಸಂಗ್ರಹವನ್ನು ಅಳಿಸಬಹುದು.',
                  )}
            </p>
            <p className="model-details">
              {catalogReady
                ? t('Content catalogue loaded', 'ವಿಷಯ ಪಟ್ಟಿ ಸಿದ್ಧ')
                : catalogFailed
                  ? t(
                      'Content unavailable — reload while online',
                      'ವಿಷಯ ಲಭ್ಯವಿಲ್ಲ — ಇಂಟರ್ನೆಟ್‌ನಲ್ಲಿ ಮರುಲೋಡ್ ಮಾಡಿ',
                    )
                  : t('Loading content…', 'ವಿಷಯ ಲೋಡ್ ಆಗುತ್ತಿದೆ…')}
            </p>
          </div>
          <div className="soft-card">
            <h3>{t('Guidance & language', 'ಸಲಹೆ ಮತ್ತು ಭಾಷೆ')}</h3>
            <p>
              {t(
                'English, Kannada and Hindi guidance with bundled speech. Text, translations and general observation rules need agronomist and native-language review before field use.',
                'ಇಂಗ್ಲಿಷ್, ಕನ್ನಡ ಮತ್ತು ಹಿಂದಿ ಸಲಹೆ, ಧ್ವನಿಯೊಂದಿಗೆ. ಹೊಲದಲ್ಲಿ ಬಳಸುವ ಮೊದಲು ಕೃಷಿ ತಜ್ಞರ ಮತ್ತು ಭಾಷಾ ಪರಿಶೀಲನೆ ಅಗತ್ಯ.',
              )}
            </p>
          </div>
          <div className="soft-card">
            <h3>{t('Private by design', 'ನಿಮ್ಮ ಮಾಹಿತಿಯ ಗೌಪ್ಯತೆ')}</h3>
            <p>
              {t(
                'Images are processed locally with ONNX Runtime Web. Saved scans use IndexedDB on this device. There is no remote diagnosis or photo upload.',
                'ಚಿತ್ರಗಳನ್ನು ONNX Runtime Web ಮೂಲಕ ಸಾಧನದಲ್ಲೇ ಪರಿಶೀಲಿಸಲಾಗುತ್ತದೆ. ಉಳಿಸಿದ ದಾಖಲೆಗಳು ಈ ಸಾಧನದ IndexedDB ಯಲ್ಲಿರುತ್ತವೆ. ಚಿತ್ರ ಅಪ್‌ಲೋಡ್ ಇಲ್ಲ.',
              )}
            </p>
          </div>
        </main>
      </>
    );

  const primaryTab = screen === 'home' || screen === 'history' || screen === 'help';
  return (
    <div className="preview-shell">
      <aside className="preview-context">
        <div className="preview-brand">
          <span>
            <Leaf size={21} />
          </span>
          CropHealth · Debuggers
        </div>
        <div className="preview-kicker">BUILD BEYOND ’26 / REVIEW 2</div>
        <h1>
          {t('A little clarity.', 'A little clarity.')}
          <br />
          {t('For every leaf.', 'For every leaf.')}
        </h1>
        <p>
          {t('Crop health guidance that stays with the farmer. Try the working browser prototype, with the same local model and content as our Android app.', 'Crop health guidance that stays with the farmer. Try the working browser prototype, with the same local model and content as our Android app.')}
        </p>
        <div className="preview-points">
          <div className="preview-point">
            <span>
              <WifiOff size={20} />
            </span>
            <div>
              <strong>{t('Built for offline use', 'Built for offline use')}</strong>
              <p>{t('Prepare once, then check leaves without a connection.', 'Prepare once, then check leaves without a connection.')}</p>
            </div>
          </div>
          <div className="preview-point">
            <span>
              <ShieldCheck size={20} />
            </span>
            <div>
              <strong>{t('Your photo stays on your device', 'Your photo stays on your device')}</strong>
              <p>{t('On-device disease model. No photo upload.', 'ಸಾಧನದಲ್ಲೇ ರೋಗದ ಮಾದರಿ. ಚಿತ್ರ ಅಪ್‌ಲೋಡ್ ಇಲ್ಲ.')}</p>
            </div>
          </div>
          <div className="preview-point">
            <span>
              <Volume2 size={20} />
            </span>
            <div>
              <strong>{t('English + ಕನ್ನಡ + हिन्दी, with voice', 'English + ಕನ್ನಡ + हिन्दी, with voice')}</strong>
              <p>{t('Bundled speech, available without a cloud service.', 'Bundled speech, available without a cloud service.')}</p>
            </div>
          </div>
        </div>
        <div className="preview-notice">
          <strong>{t('Browser preview', 'Browser preview')}</strong> · {t('This browser preview runs the same model as the Android app. Dataset-tested matches are estimates; uncertain photos ask for a retake or expert review. Model scores are not a field diagnosis.', 'ಈ ಬ್ರೌಸರ್ ಆವೃತ್ತಿ Android ಆಪ್‌ನ ಅದೇ ಮಾದರಿಯನ್ನು ಬಳಸುತ್ತದೆ. ಡೇಟಾಸೆಟ್‌ನಲ್ಲಿ ಪರೀಕ್ಷಿಸಿದ ಹೊಂದಾಣಿಕೆಗಳು ಅಂದಾಜುಗಳು; ಅನಿಶ್ಚಿತ ಚಿತ್ರಗಳಿಗೆ ಮತ್ತೆ ಫೋಟೋ ಅಥವಾ ತಜ್ಞರ ಪರಿಶೀಲನೆ ಕೇಳಲಾಗುತ್ತದೆ. ಮಾದರಿಯ ಅಂಕಗಳು ಹೊಲದಲ್ಲಿನ ರೋಗನಿರ್ಣಯವಲ್ಲ.')}
        </div>
      </aside>
      <div className="device-frame">
        <div className="phone-app">
          <input
            ref={upload}
            className="hidden-input"
            type="file"
            accept="image/*"
            data-testid="upload-input"
            aria-label={t('Choose leaf photo', 'Choose leaf photo')}
            onChange={onUpload}
          />
          {page}
          {primaryTab && (
            <nav className="bottom-nav" aria-label={t('Main navigation', 'Main navigation')}>
              {(
                [
                  { id: 'home', icon: Home, en: 'Home', kn: 'ಮುಖಪುಟ' },
                  { id: 'history', icon: History, en: 'History', kn: 'ಇತಿಹಾಸ' },
                  { id: 'help', icon: HelpCircle, en: 'Help', kn: 'ಸಹಾಯ' },
                ] as const
              ).map((tab) => (
                <button
                  key={tab.id}
                  className={`nav-button ${screen === tab.id ? 'active' : ''}`}
                  data-testid={`nav-${tab.id}`}
                  aria-current={screen === tab.id ? 'page' : undefined}
                  onClick={() => navigate(tab.id)}
                >
                  <span>
                    <tab.icon size={19} />
                  </span>
                  {t(tab.en, tab.kn)}
                </button>
              ))}
            </nav>
          )}
          {error && (
            <div className="error-toast" role="alert">
              <AlertCircle size={17} />
              <span style={{ flex: 1 }}>{t(error, error)}</span>
              <button onClick={() => setError('')} aria-label={t('Dismiss error', 'Dismiss error')}>
                <X size={16} />
              </button>
            </div>
          )}
          {expertOpen && (
            <div className="modal-overlay">
              <section
                className="modal"
                role="dialog"
                aria-modal="true"
                aria-labelledby="expert-title"
              >
                <h2 id="expert-title">{t('Call a local expert', 'ಸ್ಥಳೀಯ ತಜ್ಞರಿಗೆ ಕರೆ ಮಾಡಿ')}</h2>
                <p>
                  {t(
                    'Enter the verified number of your local agriculture officer or crop specialist. Calling needs phone service.',
                    'ನಿಮ್ಮ ಸ್ಥಳೀಯ ಕೃಷಿ ಅಧಿಕಾರಿ ಅಥವಾ ಬೆಳೆ ತಜ್ಞರ ಖಚಿತ ಸಂಖ್ಯೆಯನ್ನು ನಮೂದಿಸಿ. ಕರೆಗೆ ದೂರವಾಣಿ ಸೇವೆ ಅಗತ್ಯ.',
                  )}
                </p>
                <label>
                  {t('Phone number', 'ದೂರವಾಣಿ ಸಂಖ್ಯೆ')}
                  <input
                    type="tel"
                    autoFocus
                    value={expertNumber}
                    placeholder="+91…"
                    onChange={(event) => setExpertNumber(event.target.value)}
                  />
                </label>
                <div className="modal-actions">
                  <button className="secondary" onClick={() => setExpertOpen(false)}>
                    {t('Cancel', 'ರದ್ದು')}
                  </button>
                  <a
                    className="primary"
                    aria-disabled={!/\d{5}/.test(expertNumber.replace(/\D/g, ''))}
                    onClick={(event) => {
                      if (!/\d{5}/.test(expertNumber.replace(/\D/g, ''))) event.preventDefault();
                    }}
                    style={{
                      textDecoration: 'none',
                      pointerEvents: /\d{5}/.test(expertNumber.replace(/\D/g, ''))
                        ? undefined
                        : 'none',
                      opacity: /\d{5}/.test(expertNumber.replace(/\D/g, '')) ? 1 : 0.5,
                    }}
                    href={`tel:${expertNumber.replace(/[^+\d]/g, '')}`}
                  >
                    <Phone size={16} />
                    {t('Call', 'ಕರೆ ಮಾಡಿ')}
                  </a>
                </div>
              </section>
            </div>
          )}
          {deleteTarget && (
            <div className="modal-overlay">
              <section
                className="modal"
                role="dialog"
                aria-modal="true"
                aria-labelledby="delete-title"
              >
                <h2 id="delete-title">{t('Delete this scan?', 'ಈ ದಾಖಲೆ ಅಳಿಸಬೇಕೇ?')}</h2>
                <p>
                  {t(
                    'The saved photo and result will be removed from this device.',
                    'ಉಳಿಸಿದ ಚಿತ್ರ ಮತ್ತು ಫಲಿತಾಂಶ ಈ ಸಾಧನದಿಂದ ಅಳಿಸಲಾಗುತ್ತದೆ.',
                  )}
                </p>
                <div className="modal-actions">
                  <button className="secondary" onClick={() => setDeleteTarget(null)}>
                    {t('Cancel', 'ರದ್ದು')}
                  </button>
                  <button
                    className="primary"
                    data-testid="confirm-delete"
                    onClick={async () => {
                      try {
                        await deleteObservation(deleteTarget.id);
                        setDeleteTarget(null);
                        await refreshHistory();
                      } catch {
                        setError(t('Could not delete the scan.', 'ದಾಖಲೆ ಅಳಿಸಲಾಗಲಿಲ್ಲ.'));
                      }
                    }}
                  >
                    {t('Delete', 'ಅಳಿಸಿ')}
                  </button>
                </div>
              </section>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function CameraCapture({
  crop,
  language,
  onBack,
  onGallery,
  onPhoto,
  onLanguage,
}: {
  crop: CropId;
  language: Language;
  onBack: () => void;
  onGallery: () => void;
  onPhoto: (photo: File) => void;
  onLanguage: () => void;
}) {
  const video = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [ready, setReady] = useState(false);
  const [cameraError, setCameraError] = useState('');
  const [torchSupported, setTorchSupported] = useState(false);
  const [torch, setTorch] = useState(false);
  const t = (en: string, kn: string) => translateUi(en, kn, language);
  useEffect(() => {
    let cancelled = false;
    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraError('Camera requires HTTPS and a supported browser. Choose a photo instead.');
      return;
    }
    void navigator.mediaDevices
      .getUserMedia({
        video: {
          facingMode: { ideal: 'environment' },
          width: { ideal: 1280 },
          height: { ideal: 1280 },
        },
        audio: false,
      })
      .then((stream) => {
        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }
        streamRef.current = stream;
        if (video.current) {
          video.current.srcObject = stream;
          void video.current
            .play()
            .catch(() => setCameraError('Tap the preview to start your camera.'));
        }
        const capabilities = stream
          .getVideoTracks()[0]
          ?.getCapabilities?.() as MediaTrackCapabilities & { torch?: boolean };
        setTorchSupported(!!capabilities?.torch);
      })
      .catch((reason) => {
        if (!cancelled)
          setCameraError(
            reason?.name === 'NotAllowedError'
              ? 'Camera permission was denied. Allow it in browser settings or choose a photo.'
              : 'Camera is unavailable. You can still choose a leaf photo.',
          );
      });
    return () => {
      cancelled = true;
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    };
  }, []);
  async function capture() {
    const element = video.current;
    if (!element || !ready || !element.videoWidth) return;
    const scale = Math.min(1, 1600 / Math.max(element.videoWidth, element.videoHeight));
    const canvas = document.createElement('canvas');
    canvas.width = Math.round(element.videoWidth * scale);
    canvas.height = Math.round(element.videoHeight * scale);
    canvas.getContext('2d')!.drawImage(element, 0, 0, canvas.width, canvas.height);
    canvas.toBlob(
      (blob) => {
        if (blob) onPhoto(new File([blob], `leaf-${Date.now()}.jpg`, { type: 'image/jpeg' }));
        else setCameraError('Could not capture this photo. Please try again.');
      },
      'image/jpeg',
      0.9,
    );
  }
  async function toggleTorch() {
    const track = streamRef.current?.getVideoTracks()[0];
    if (!track || !torchSupported) return;
    try {
      await track.applyConstraints({ advanced: [{ torch: !torch } as MediaTrackConstraintSet] });
      setTorch(!torch);
    } catch {
      setCameraError('Flash is unavailable on this camera.');
    }
  }
  return (
    <section className="camera-page">
      <div className="camera-top">
        <button className="icon-button" onClick={onBack} aria-label={t('Back', 'Back')}>
          <X size={22} />
        </button>
        <span className="crop-label">{cropName(crop, language)}</span>
        <button
          onClick={() => void toggleTorch()}
          disabled={!torchSupported}
          aria-label={torch ? t('Flash on', 'ಫ್ಲ್ಯಾಶ್ ಆನ್') : t('Flash off', 'ಫ್ಲ್ಯಾಶ್ ಆಫ್')}
          style={{ display: 'flex', gap: 5, alignItems: 'center' }}
        >
          {torch ? <Zap size={15} /> : <ZapOff size={15} />}
          {torchSupported
            ? torch
              ? t('Flash on', 'ಫ್ಲ್ಯಾಶ್ ಆನ್')
              : t('Flash off', 'ಫ್ಲ್ಯಾಶ್ ಆಫ್')
            : t('No flash', 'ಫ್ಲ್ಯಾಶ್ ಇಲ್ಲ')}
        </button>
      </div>
      <div className="camera-frame" onClick={() => void video.current?.play()}>
        <video
          ref={video}
          autoPlay
          playsInline
          muted
          onLoadedData={() => setReady(true)}
          style={{ display: ready ? 'block' : 'none' }}
        />
        {!ready && (
          <div className="camera-placeholder">
            <Camera size={37} />
            <p>
              {cameraError
                ? t('Choose a leaf photo to continue', 'ಮುಂದುವರಿಯಲು ಎಲೆಯ ಚಿತ್ರ ಆಯ್ಕೆಮಾಡಿ')
                : t('Opening your camera…', 'ಕ್ಯಾಮೆರಾ ತೆರೆಯಲಾಗುತ್ತಿದೆ…')}
            </p>
          </div>
        )}
      </div>
      <p className="camera-helper">
        {t('Fit one leaf inside the frame', 'ಒಂದು ಎಲೆಯನ್ನು ಚೌಕಟ್ಟಿನೊಳಗೆ ಇರಿಸಿ')}
      </p>
      <div className="camera-tips">
        <span>{t('Good light', 'ಉತ್ತಮ ಬೆಳಕು')}</span>
        <span>{t('Hold steady', 'ಸ್ಥಿರವಾಗಿ ಹಿಡಿ')}</span>
        <span>{t('Close up', 'ಹತ್ತಿರದಿಂದ')}</span>
      </div>
      {cameraError && (
        <p className="capture-error" role="status">
          {t(cameraError, cameraError)}
        </p>
      )}
      <div className="camera-controls">
        <button
          className="camera-gallery"
          aria-label={t('Choose photo from gallery', 'Choose photo from gallery')}
          onClick={onGallery}
        >
          <ImagePlus size={23} />
        </button>
        <button
          className="shutter"
          disabled={!ready}
          onClick={() => void capture()}
          aria-label={t('Take leaf photo', 'Take leaf photo')}
        >
          <i />
        </button>
        <button className="camera-language" onClick={onLanguage} aria-label={t('Change language', 'Change language')}>
          {language === 'en' ? 'ಕ' : language === 'kn' ? 'हिं' : 'En'}
        </button>
      </div>
      <p style={{ color: '#aba1b7', fontSize: 10, textAlign: 'center' }}>
        {t(
          'Or choose an existing leaf photo from your gallery',
          'ಅಥವಾ ಗ್ಯಾಲರಿಯಿಂದ ಎಲೆಯ ಚಿತ್ರ ಆಯ್ಕೆಮಾಡಿ',
        )}
      </p>
    </section>
  );
}
