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
import { analyzeLeaf, getModelStatus } from './lib/inference';
import type { AssessmentResult, ModelStatus } from './lib/inference';
import {
  conditionName,
  cropName,
  getGuidance,
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
  const [answers, setAnswers] = useState<(number | null)[]>([null, null, null]);
  const [concern, setConcern] = useState<ConcernResult | null>(null);
  const [concernComplete, setConcernComplete] = useState(false);
  const [expertOpen, setExpertOpen] = useState(false);
  const [expertNumber, setExpertNumber] = useState('');
  const [deleteTarget, setDeleteTarget] = useState<ObservationRecord | null>(null);
  const upload = useRef<HTMLInputElement>(null);
  const analysisRequest = useRef(0);
  const offlineReady = useOfflineReady();
  const t = useCallback((en: string, kn: string) => translateUi(en, kn, language), [language]);
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
    void loadCatalog()
      .then(() => setCatalogReady(true))
      .catch(() => setCatalogFailed(true));
    void getModelStatus()
      .then(setModel)
      .catch(() =>
        setModel({
          ready: false,
          validated: false,
          name: 'MobileNetV4',
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
    setAnswers([null, null, null]);
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
  const top = assessment?.candidates[0];
  const conditionId = opened?.conditionId || top?.id || null;
  const score = opened?.score ?? top?.score ?? null;
  const provisionalPrediction = resultType === 'uncertain' && !!conditionId &&
    (assessment?.sourceEvaluated === true ||
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
  const conditionSpecificAdviceAllowed =
    accepted && validated &&
    (assessment as (AssessmentResult & { allowConditionSpecificAdvice?: boolean }) | null)
      ?.allowConditionSpecificAdvice === true;
  const guidance = conditionSpecificAdviceAllowed && conditionId ? getGuidance(conditionId, language) : null;

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
        note: '',
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
    setAnswers([null, null, null]);
    setScreen('result');
  }
  function beginConcern() {
    setQuestion(0);
    setAnswers([null, null, null]);
    setConcernComplete(false);
    setScreen('concern');
  }
  function nextConcern() {
    if (answers[question] === null) return;
    if (question < 2) {
      setQuestion(question + 1);
      return;
    }
    const coverage: LeafCoverage =
      answers[1] === 0
        ? 'FEW_SPOTS'
        : answers[1] === 1
          ? 'SOME_SPOTS'
          : answers[1] === 2
            ? 'MANY_SPOTS'
            : 'NOT_REPORTED';
    const reported: ReportedSymptoms = {
      ...EMPTY_SYMPTOMS,
      spreadingQuickly: answers[0] === 0,
      manyPlantsAffected: answers[2] === 0,
      leafCoverage: coverage,
      uncertainAnswers: answers[0] === 2 || answers[1] === 3 || answers[2] === 2,
    };
    const summary = summarizeConcern(reported);
    setConcern(summary);
    setConcernComplete(true);
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
      record.modelVersion === model?.version && model?.sourceEvaluated === true;
    const label =
      (acceptedRecord || predictedRecord) && record.conditionId
        ? conditionName(record.conditionId, language)
        : t('Uncertain result', 'ಅನಿಶ್ಚಿತ ಫಲಿತಾಂಶ');
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
              {predictedRecord && `${record.resultType === 'crop_mismatch' ? t('Crop mismatch', 'ಬೆಳೆ ಹೊಂದಿಕೆಯಾಗಿಲ್ಲ') : t('Low confidence prediction', 'ಕಡಿಮೆ ವಿಶ್ವಾಸದ ಅಂದಾಜು')} · `}
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
              'Running MobileNetV4 on this device. The first check may take a little longer.',
              'ಈ ಸಾಧನದಲ್ಲಿ MobileNetV4 ಚಾಲನೆಯಲ್ಲಿದೆ. ಮೊದಲ ಪರಿಶೀಲನೆಗೆ ಸ್ವಲ್ಪ ಹೆಚ್ಚು ಸಮಯ ಬೇಕಾಗಬಹುದು.',
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
                {hasPrediction && conditionId
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
                {accepted
                  ? t('Model match', 'ಮಾದರಿಯ ಹೊಂದಾಣಿಕೆ')
                  : cropMismatchPrediction
                    ? t('Crop mismatch', 'ಬೆಳೆ ಹೊಂದಿಕೆಯಾಗಿಲ್ಲ')
                  : provisionalPrediction
                    ? t('Low confidence prediction', 'ಕಡಿಮೆ ವಿಶ್ವಾಸದ ಅಂದಾಜು')
                  : resultType === 'retake'
                    ? t('A clearer photo will help', 'ಸ್ಪಷ್ಟ ಚಿತ್ರ ಸಹಾಯ ಮಾಡುತ್ತದೆ')
                    : resultType === 'model_unavailable'
                      ? t('Unable to run the model', 'ಮಾದರಿಯನ್ನು ಚಲಾಯಿಸಲಾಗಲಿಲ್ಲ')
                      : t('Not sure about this one', 'ಈ ಬಗ್ಗೆ ಖಚಿತವಿಲ್ಲ')}
              </h2>
            </div>
            {accepted ? (
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
            </p> : <p>{provisionalPrediction
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
              {assessment?.candidates.slice(0, 2).map((item, index) => (
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
          {assessment?.qualityIssues && assessment.qualityIssues.length > 0 && (
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
          {currentConcern && (
            <div className="soft-card" data-testid="concern-summary">
              <h3>
                {currentConcern.level === 'SEEK_LOCAL_EXPERT'
                  ? t('Ask a local expert', 'ಸ್ಥಳೀಯ ತಜ್ಞರನ್ನು ಕೇಳಿ')
                  : t('Observe and recheck', 'ಗಮನಿಸಿ ಮರುಪರಿಶೀಲಿಸಿ')}
              </h3>
              <p>
                {t(
                  'Based on your answers about visible symptoms, not an AI severity estimate.',
                  'ಕಾಣುವ ಲಕ್ಷಣಗಳ ಬಗ್ಗೆ ನಿಮ್ಮ ಉತ್ತರಗಳ ಆಧಾರಿತ. AI ತೀವ್ರತೆ ಅಂದಾಜಲ್ಲ.',
                )}
              </p>
            </div>
          )}
          <div className="button-stack">
            {cropMismatchPrediction && <button className="secondary" onClick={() => navigate('home')}>
              {t('Change selected crop', 'ಆಯ್ಕೆ ಮಾಡಿದ ಬೆಳೆಯನ್ನು ಬದಲಿಸಿ')}
            </button>}
            {!accepted && expertButton}
            <button className="primary" onClick={beginConcern}>
              {t('Check concern (3 questions)', 'ಲಕ್ಷಣ ಪರಿಶೀಲನೆ (3 ಪ್ರಶ್ನೆಗಳು)')}
            </button>
            <button className="secondary" onClick={() => navigate('guidance')}>
              {t('See guidance', 'ಸಲಹೆ ನೋಡಿ')}
            </button>
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
    const generic = getPrompt(hasPrediction ? 'check_expert' : 'uncertain', language);
    page = (
      <>
        {topBar('result', languageToggle)}
        <main className="app-page with-top">
          <div className="heading-copy">
            <h1 data-testid="guidance-heading">{t('Care for your crop', 'ನಿಮ್ಮ ಬೆಳೆ ಆರೈಕೆ')}</h1>
            <p>
              {cropName(activeCrop, language)} ·{' '}
              {guidance?.name || t('General observation guidance', 'ಸಾಮಾನ್ಯ ವೀಕ್ಷಣೆಯ ಸಲಹೆ')}
            </p>
          </div>
          <AudioPlayer
            language={language}
            src={catalogReady ? guidance?.audioAsset || generic.audioAsset : null}
            label={t('Listen to guidance', 'ಸಲಹೆ ಕೇಳಿ')}
          />
          {guidance ? (
            <>
              {[
                ['Do now', 'ಈಗ ಮಾಡಿ', guidance.actions, ''],
                ['What to watch', 'ಗಮನಿಸಬೇಕಾದವು', guidance.symptoms, 'gold'],
                ['Prevention', 'ಮುನ್ನೆಚ್ಚರಿಕೆ', guidance.prevention, 'rose'],
              ].map(([en, kn, lines, color]) => (
                <section className={`guidance-card ${color}`} key={String(en)}>
                  <h3>{t(String(en), String(kn))}</h3>
                  <ul>
                    {(lines as string[]).map((line) => (
                      <li key={line}>{line}</li>
                    ))}
                  </ul>
                </section>
              ))}
              <p className="hint">{guidance.caution}</p>
            </>
          ) : (
            <>
              <section className="guidance-card">
                <h3>{t('Observe your plants', 'ಗಿಡಗಳನ್ನು ಗಮನಿಸಿ')}</h3>
                <ul>
                  <li>
                    {t(
                      'Look at more than one plant. Note whether symptoms are spreading.',
                      'ಒಂದಕ್ಕಿಂತ ಹೆಚ್ಚು ಗಿಡಗಳನ್ನು ನೋಡಿ. ಲಕ್ಷಣಗಳು ಹರಡುತ್ತಿವೆಯೇ ಗಮನಿಸಿ.',
                    )}
                  </li>
                  <li>
                    {t(
                      'Keep a dated photo and recheck the same plant.',
                      'ದಿನಾಂಕದೊಂದಿಗೆ ಚಿತ್ರ ಉಳಿಸಿ. ಅದೇ ಗಿಡವನ್ನು ಮತ್ತೆ ಪರಿಶೀಲಿಸಿ.',
                    )}
                  </li>
                </ul>
              </section>
              <section className="guidance-card gold">
                <h3>{t('Get the cause checked', 'ಕಾರಣ ಪರಿಶೀಲಿಸಿಕೊಳ್ಳಿ')}</h3>
                <ul>
                  <li>{getPrompt('check_expert', language).message}</li>
                </ul>
              </section>
              <section className="guidance-card rose">
                <h3>{t('Take simple precautions', 'ಸರಳ ಮುನ್ನೆಚ್ಚರಿಕೆ ವಹಿಸಿ')}</h3>
                <ul>
                  <li>
                    {t(
                      'Keep tools clean and avoid moving damaged plant material between fields.',
                      'ಉಪಕರಣಗಳನ್ನು ಸ್ವಚ್ಛವಾಗಿಡಿ. ಹಾನಿಗೊಂಡ ಗಿಡದ ಭಾಗಗಳನ್ನು ಹೊಲಗಳ ನಡುವೆ ಸಾಗಿಸಬೇಡಿ.',
                    )}
                  </li>
                  <li>
                    {t(
                      'Do not choose a pesticide or dosage from this prototype result.',
                      'ಈ ಮಾದರಿಯ ಫಲಿತಾಂಶದಿಂದ ಕೀಟನಾಶಕ ಅಥವಾ ಪ್ರಮಾಣ ಆಯ್ಕೆ ಮಾಡಬೇಡಿ.',
                    )}
                  </li>
                </ul>
              </section>
            </>
          )}
          {expertButton}
          <p className="privacy-note">
            {t(
              'Prototype guidance and Kannada translations are pending agronomist and language review.',
              'ಮಾದರಿ ಸಲಹೆ ಮತ್ತು ಕನ್ನಡ ಅನುವಾದಗಳಿಗೆ ಕೃಷಿ ತಜ್ಞರ ಹಾಗೂ ಭಾಷಾ ಪರಿಶೀಲನೆ ಬಾಕಿಯಿದೆ.',
            )}
          </p>
        </main>
      </>
    );
  } else if (screen === 'concern') {
    const keys = ['concern_spreading', 'concern_coverage', 'concern_plants'];
    const questions = [
      t('Are symptoms spreading quickly?', 'ಲಕ್ಷಣಗಳು ವೇಗವಾಗಿ ಹರಡುತ್ತಿವೆಯೇ?'),
      t('How much of the leaf looks affected?', 'ಎಲೆಯ ಎಷ್ಟು ಭಾಗದಲ್ಲಿ ಲಕ್ಷಣಗಳಿವೆ?'),
      t('Do several plants have these symptoms?', 'ಹಲವು ಗಿಡಗಳಲ್ಲಿ ಇದೇ ಲಕ್ಷಣಗಳಿವೆಯೇ?'),
    ];
    const options =
      question === 1
        ? [
            t('A few small spots', 'ಕೆಲವು ಸಣ್ಣ ಚುಕ್ಕೆಗಳು'),
            t('Some of the leaf', 'ಎಲೆಯ ಕೆಲವು ಭಾಗ'),
            t('Most of the leaf', 'ಎಲೆಯ ಹೆಚ್ಚಿನ ಭಾಗ'),
            t('I’m not sure', 'ನನಗೆ ಖಚಿತವಿಲ್ಲ'),
          ]
        : [t('Yes', 'ಹೌದು'), t('No', 'ಇಲ್ಲ'), t('I’m not sure', 'ನನಗೆ ಖಚಿತವಿಲ್ಲ')];
    const summaryPrompt = getPrompt(
      currentConcern?.level === 'SEEK_LOCAL_EXPERT' ? 'concern_expert' : 'concern_observe',
      language,
    );
    page = (
      <>
        {topBar(
          'result',
          !concernComplete ? (
            <span className="hint">
              {t(`Question ${question + 1} of 3`, `ಪ್ರಶ್ನೆ ${question + 1} / 3`)}
            </span>
          ) : null,
        )}
        <main className="app-page with-top">
          {concernComplete ? (
            <>
              <div className="heading-copy" data-testid="concern-summary">
                <h1>
                  {currentConcern?.level === 'SEEK_LOCAL_EXPERT'
                    ? t('Get a closer look', 'ಹೆಚ್ಚಿನ ಪರಿಶೀಲನೆ ಪಡೆಯಿರಿ')
                    : t('Observe and recheck', 'ಗಮನಿಸಿ ಮರುಪರಿಶೀಲಿಸಿ')}
                </h1>
                <p>{summaryPrompt.message}</p>
              </div>
              <AudioPlayer
            language={language}
                src={catalogReady ? summaryPrompt.audioAsset : null}
                label={t('Listen to next steps', 'ಮುಂದಿನ ಕ್ರಮ ಕೇಳಿ')}
              />
              <div className="soft-card">
                <h3>{t('Your observations matter', 'ನಿಮ್ಮ ಗಮನಿಸುವಿಕೆ ಮುಖ್ಯ')}</h3>
                <p>
                  {t(
                    'This follow-up comes from your answers. It does not measure disease severity from the image.',
                    'ಇದು ನಿಮ್ಮ ಉತ್ತರಗಳ ಆಧಾರಿತ ಸಲಹೆ. ಚಿತ್ರದಿಂದ ರೋಗದ ತೀವ್ರತೆಯನ್ನು ಅಳೆಯುವುದಿಲ್ಲ.',
                  )}
                </p>
              </div>
              {currentConcern?.level === 'SEEK_LOCAL_EXPERT' && expertButton}
              <button className="primary" onClick={() => navigate('guidance')}>
                {t('See guidance', 'ಸಲಹೆ ನೋಡಿ')}
              </button>
              <button className="secondary" onClick={() => navigate('result')}>
                {t('Back to result', 'ಫಲಿತಾಂಶಕ್ಕೆ ಹಿಂತಿರುಗಿ')}
              </button>
              {(opened || savedId) && (
                <p className="hint">
                  {t(
                    'These new answers are for this visit. The saved observation is unchanged.',
                    'ಈ ಹೊಸ ಉತ್ತರಗಳು ಈ ಭೇಟಿಗೆ ಮಾತ್ರ. ಉಳಿಸಿದ ದಾಖಲೆ ಬದಲಾಗುವುದಿಲ್ಲ.',
                  )}
                </p>
              )}
            </>
          ) : (
            <>
              <div className="question-progress">
                <i style={{ width: `${((question + 1) / 3) * 100}%` }} />
              </div>
              <p>
                {cropName(activeCrop, language)} · {t('Your observations', 'ನಿಮ್ಮ ಗಮನಿಸುವಿಕೆ')}
              </p>
              <h1 className="question-title">{questions[question]}</h1>
              <AudioPlayer
            language={language}
                compact
                src={catalogReady ? getPrompt(keys[question], language).audioAsset : null}
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
                {question === 2 ? t('See next steps', 'ಮುಂದಿನ ಕ್ರಮ ನೋಡಿ') : t('Next', 'ಮುಂದೆ')}
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
                ? t('MobileNetV4 installed', 'MobileNetV4 ಸಿದ್ಧ')
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
            <h3>MobileNetV4</h3>
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
              <p>{t('Real MobileNetV4 inference. No photo upload.', 'Real MobileNetV4 inference. No photo upload.')}</p>
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
