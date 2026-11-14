import { conditionName, cropName, assetUrl } from '../lib/content';
import { careText } from '../lib/careProtocols';
import type { CarePlan, CareProtocols, CareTextKey } from '../lib/careProtocols';
import type { CropId, Language } from '../lib/types';
import { AudioPlayer } from './AudioPlayer';

export function TreatmentPlan({ plan, model, language, audioPaths }: { plan: CarePlan; model: CareProtocols; language: Language; audioPaths: ReadonlySet<string> }) {
  const c = (key: CareTextKey) => careText(key, language);
  const copy = plan.copy;
  const list = (items: string[]) => <ul>{items.map(line => <li key={line}>{line}</li>)}</ul>;
  return <section className="treatment-plan" data-testid="treatment-plan" data-condition={plan.conditionId} data-stage={plan.severity}>
    <div className="heading-copy"><h2>{c('title')}</h2><p>{cropName(model.protocols[plan.conditionId].crop_id as CropId, language)} · {conditionName(plan.conditionId, language)}</p></div>
    {audioPaths.has(`audio/${language}/treatment_${plan.conditionId}.ogg`) && <AudioPlayer language={language} src={assetUrl(`audio/${language}/treatment_${plan.conditionId}.ogg`)} label={c('audio')} />}
    <section className="guidance-card" data-testid="treatment-goal"><h3>{c('goal')}</h3><p>{copy.goal}</p></section>
    <section className="guidance-card gold" data-testid="stage-plan"><h3>{c('stage')}</h3>{plan.stage ? <><p>{plan.stage.title}</p>{list(plan.stage.actions)}</> : <p>{c(plan.severity === 'NONE' ? 'routine' : 'unknown')}</p>}</section>
    {plan.severity !== 'NONE' && audioPaths.has(`audio/${language}/treatment_stage_${plan.severity.toLowerCase()}.ogg`) && <AudioPlayer language={language} src={assetUrl(`audio/${language}/treatment_stage_${plan.severity.toLowerCase()}.ogg`)} label={c('stage')} compact />}
    <section className="guidance-card"><h3>{c('checks')}</h3>{list(copy.confirm_checks)}<h3>{c('similar')}</h3>{list(copy.look_alikes)}</section>
    <h3>{c('options')}</h3>
    {copy.treatment_options.map((option, index) => <article className="guidance-card treatment-option" key={option.id} data-testid="treatment-option">
      <h3><span className="treatment-number">{index + 1}</span>{option.title}</h3>
      <p><strong>{c('when')}: </strong>{option.when}</p>
      <ol>{option.steps.map(step => <li key={step}>{step}</li>)}</ol>
      <p className="hint"><strong>{c('limits')}: </strong>{option.limits}</p>
      {option.source_ids.length > 0 && <details className="treatment-option-sources"><summary>{c('refs')}</summary><ul>{model.sources.filter(source => option.source_ids.includes(source.id)).map(source => <li key={source.id}><a href={source.url} target="_blank" rel="noreferrer">{source.title}</a><small> · {source.verification_status.replaceAll('_', ' ')}</small></li>)}</ul></details>}
    </article>)}
    <section className="guidance-card rose"><h3>{c('avoid')}</h3>{list(copy.avoid)}</section>
    <section className="guidance-card" data-testid="recovery-signs"><h3>{c('improvement')}</h3>{list(copy.recovery_signs)}</section>
    <section className="guidance-card gold"><h3>{c('worsening')}</h3>{list(copy.failure_signs)}</section>
    <section className="guidance-card" data-testid="follow-up-plan"><h3>{c('followup')}</h3><ol className="follow-up-list">{copy.follow_up.map((point, index) => <li key={`${point.when}-${index}`}><strong>{point.when}</strong><p>{point.check}</p><p>{point.action}</p></li>)}</ol></section>
    <section className="guidance-card"><h3>{c('expert')}</h3>{list(copy.expert_questions)}</section>
    <details className="advisory-reasons"><summary>{c('refs')}</summary><ul>{model.sources.filter(s => plan.sourceIds.includes(s.id)).map(s => <li key={s.id}><a href={s.url} target="_blank" rel="noreferrer">{s.title}</a><small> · {s.verification_status.replaceAll('_', ' ')}</small></li>)}</ul></details>
    <p className="privacy-note">{c('notice')} · {plan.modelVersion}</p>
  </section>;
}
