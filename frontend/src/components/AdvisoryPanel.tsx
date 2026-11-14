import type { ReactNode } from 'react';
import { AlertCircle, ShieldCheck } from 'lucide-react';
import { AudioPlayer } from './AudioPlayer';
import { assetUrl } from '../lib/content';
import { advisoryReason, advisoryText } from '../lib/advisory';
import type { AdvisoryModel, AdvisoryResult, AdvisoryTextKey } from '../lib/advisory';
import type { Language } from '../lib/types';

export function AdvisoryPanel({ result, language, model, onQuestions, detailed = false, treatmentContent, showPriorityAudio = false }:
  { result: AdvisoryResult; language: Language; model: AdvisoryModel; onQuestions?: () => void; detailed?: boolean; treatmentContent?: ReactNode; showPriorityAudio?: boolean }) {
  const a = (key: AdvisoryTextKey) => advisoryText(key, language);
  const copy = result.profile?.translations[language];
  const color = result.urgency === 'URGENT' ? 'urgent' : result.urgency === 'SAME_DAY' ? 'today' : result.urgency === 'SOON' ? 'soon' : 'monitor';
  const sourceIds = result.profile?.source_ids ?? [];
  return <section className="advisory-panel" data-testid="advisory-panel">
    <div className={`advisory-priority ${color}`} role="status" data-testid="advisory-summary">
      <div className="advisory-heading">{result.urgency === 'MONITOR' ? <ShieldCheck size={23} /> : <AlertCircle size={23} />}<strong>{a('title')}</strong></div>
      <div className="advisory-metrics">
        <div><small>{a('severity')}</small><strong data-testid="advisory-severity">{a(result.severity)}</strong></div>
        <div><small>{a('urgency')}</small><strong data-testid="advisory-urgency">{a(result.urgency)}</strong></div>
      </div>
      <p>{a('basis')}</p>
    </div>
    {!result.observations && <p className="hint">{a('noAnswers')}</p>}
    {onQuestions && <button className="secondary" onClick={onQuestions}>{a('questions')}</button>}
    <details className="advisory-reasons" open={detailed}>
      <summary>{a('why')}</summary>
      <ul>{result.reasonCodes.map(code => <li key={code}>{advisoryReason(code, language)}</li>)}</ul>
    </details>
    {(detailed || showPriorityAudio) && <AudioPlayer language={language} src={assetUrl(`audio/${language}/advisory_${result.urgency.toLowerCase()}.ogg`)} label={a('urgency')} compact />}
    {detailed && <>
      {treatmentContent}
      {copy ? <>
        <section className="guidance-card" data-testid="conditional-care">
          <h3>{a('conditional')}</h3><p>{copy.overview}</p>
          <h3>{a('curability')}</h3><p>{copy.curability}</p>
        </section>
        <AudioPlayer language={language} src={assetUrl(`audio/${language}/advisory_${Object.keys(model.profiles).find(id => model.profiles[id] === result.profile)}.ogg`)} label={a('careAudio')} />
        {(['do_now', 'management', 'prevention', 'escalation'] as const).map((key, i) => <section className={`guidance-card ${i % 2 ? 'gold' : ''}`} key={key}>
          <h3>{a(({ do_now: 'now', management: 'management', prevention: 'prevention', escalation: 'escalation' } as const)[key])}</h3>
          <ul>{copy[key].map(line => <li key={line}>{line}</li>)}</ul>
        </section>)}
        <details className="advisory-reasons"><summary>{language === 'hi' ? 'संदर्भ और समीक्षा स्थिति' : language === 'kn' ? 'ಮೂಲಗಳು ಮತ್ತು ಪರಿಶೀಲನೆಯ ಸ್ಥಿತಿ' : 'References & review status'}</summary>
          <ul>{model.sources.filter(source => sourceIds.includes(source.id)).map(source => <li key={source.id}><a href={source.url} target="_blank" rel="noreferrer">{source.title}</a><small> · {source.verification_status.replaceAll('_', ' ')}</small></li>)}</ul>
        </details>
      </> : <section className="guidance-card gold"><h3>{a('generic')}</h3><ul>
        <li>{language === 'hi' ? 'तारीख के साथ तस्वीर रखें, पास के पौधों को देखें और साफ उपकरण इस्तेमाल करें।' : language === 'kn' ? 'ದಿನಾಂಕದ ಚಿತ್ರ ಉಳಿಸಿ, ಹತ್ತಿರದ ಗಿಡ ನೋಡಿ ಮತ್ತು ಸ್ವಚ್ಛ ಉಪಕರಣ ಬಳಸಿ.' : 'Keep a dated photo, inspect nearby plants and use clean tools.'}</li>
        <li>{language === 'hi' ? 'इस अनुमान के आधार पर पौधे नष्ट न करें या दवा की मात्रा न चुनें।' : language === 'kn' ? 'ಈ ಅಂದಾಜಿನಿಂದ ಗಿಡ ನಾಶ ಮಾಡಬೇಡಿ ಅಥವಾ ಔಷಧ ಪ್ರಮಾಣ ಆಯ್ಕೆ ಮಾಡಬೇಡಿ.' : 'Do not destroy plants or choose a pesticide dose from this prediction.'}</li>
      </ul></section>}
      <p className="privacy-note">{a('model')} · {result.modelVersion}</p>
    </>}
  </section>;
}
