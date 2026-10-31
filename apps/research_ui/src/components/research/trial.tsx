import { Check, Minus, X } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

export type TrialObservation = {
  session_id: string; trial_id: string; pair_id: string; family: string; variant: 'control' | 'fault'; judge: 'agent' | 'checker'
  condition: string; model: string; repeat_index: number
  verdict: 'PASS' | 'FAIL' | 'INCONCLUSIVE' | null; agent_verdict: string | null
  agent_verdict_source: { note: string; line: number; text: string } | null; agent_verdict_conflicting: boolean
  checker_verdict: string | null; checker_error: string | null; run_status: string; error: string | null
  outcome: 'correct_pass' | 'correct_fail' | 'false_pass' | 'false_fail' | 'inconclusive' | 'unscored'
  pre_oracle_correct: boolean | null; post_oracle_correct: boolean | null; setup_confirmed: boolean; visibility_confirmed: boolean
  protected_state_changed: boolean | null; criterion_matched: boolean; mutation_version: string; oracle_version: string | null
  harness_commit: string | null; harness_dirty: boolean | null; admission: string; superseded?: boolean
  grounding: Grounding | null
}

export type Grounding = {
  screens: number; screens_without_text: number; observed_fields: number; checkable_fields: number
  record_seen: boolean; record_screen_step: number | null; grounded_pass: boolean | null
  fields: Record<string, { display: string | null; status: 'observed' | 'not_observed' | 'uncheckable'; first_step: number | null }>
  fault: { field: string | null; actual: unknown; display: string | null; on_screen?: boolean | null; first_step?: number | null; missing_record?: boolean } | null
}

const OUTCOME: Record<TrialObservation['outcome'], { label: string; className: string }> = {
  correct_pass: { label: 'Correct', className: 'border-success/30 bg-success/10 text-success' },
  correct_fail: { label: 'Correct', className: 'border-success/30 bg-success/10 text-success' },
  false_pass: { label: 'Wrong: passed a fault', className: 'border-destructive/30 bg-destructive/10 text-destructive' },
  false_fail: { label: 'Wrong: failed correct data', className: 'border-destructive/30 bg-destructive/10 text-destructive' },
  inconclusive: { label: 'No decision', className: 'border-warning/40 bg-warning/10 text-warning' },
  unscored: { label: 'Not counted', className: 'border-border bg-muted text-muted-foreground' },
}

export function OutcomeBadge({ outcome, className }: { outcome: TrialObservation['outcome']; className?: string }) {
  const item = OUTCOME[outcome]
  return <Badge variant="outline" className={cn('rounded-md font-medium', item.className, className)}>{item.label}</Badge>
}

export const ERROR_TEXT: Record<string, string> = {
  run_cancelled: 'Run was cancelled', run_failed: 'Run failed', run_unknown: 'Run status unknown', run_running: 'Run still in progress',
  run_queued: 'Run not started yet', run_pending: 'Run not started yet',
  no_post_oracle_read: 'App data not read after the run', no_declared_verdict: 'Agent gave no verdict',
  checker_crashed: 'Checker crashed', no_final_checker_pass: 'Checker gave no final verdict',
}

export const ADMISSION_TEXT: Record<string, string> = {
  admitted: 'Counted', execution_error: 'Not counted', missing_or_invalid_fields: 'Not counted: data missing', setup_failure: 'Not counted: starting data not confirmed',
  visibility_unreviewed: 'Not counted yet: fault visibility not checked', criterion_mismatch: 'Not counted: test text changed', protected_state_changed: 'Not counted: agent changed data', missing_observation: 'Not run',
}

/** What a run needs before it counts toward results. Items that can only be known after the run show as pending while it runs. */
export function AdmissionChecklist({ trial, running = false }: { trial: TrialObservation; running?: boolean }) {
  const later = (value: boolean | null) => running ? null : value
  const items: [string, boolean | null][] = [
    ['Run finished', later(trial.run_status === 'completed')],
    ['Starting data confirmed (read before the run)', trial.setup_confirmed],
    ['App data read again after the run', later(trial.post_oracle_correct !== null)],
    [trial.judge === 'agent' ? 'Agent gave a verdict' : 'Checker gave a final verdict', later(trial.verdict !== null)],
    ['Test text sent unchanged', trial.criterion_matched],
    ['Agent changed no other data', later(trial.protected_state_changed === null ? null : !trial.protected_state_changed)],
    ['Fault visibility checked by a person', trial.visibility_confirmed || (running ? null : false)],
  ]
  return <ul className="grid gap-1.5">
    {items.map(([label, ok]) => <li key={label} className="flex items-center gap-2 text-xs">
      <span className={cn('flex size-4 shrink-0 items-center justify-center rounded-full', ok === true ? 'bg-success/15 text-success' : ok === false ? 'bg-destructive/15 text-destructive' : 'bg-muted text-muted-foreground')}>
        {ok === true ? <Check className="size-3" /> : ok === false ? <X className="size-3" /> : <Minus className="size-3" />}
      </span>
      <span className={ok === false ? 'text-foreground' : 'text-muted-foreground'}>{label}</span>
    </li>)}
  </ul>
}

/** Which expected values were on the agent's screen, from recorded screen text only — never from its own notes. */
export function GroundingDetail({ grounding, verdict, running = false }: { grounding: Grounding; verdict: string | null; running?: boolean }) {
  const fault = grounding.fault
  const fields = Object.keys(grounding.fields).length
  return <div className="flex flex-col gap-2">
    <div className="flex flex-wrap items-center gap-1.5 text-xs">
      <span className="font-medium">Seen on screen{running ? ' so far' : ''}</span>
      {!running && grounding.grounded_pass === true && <Badge variant="outline" className="rounded-md border-success/30 bg-success/10 text-success">PASS backed by screen</Badge>}
      {!running && grounding.grounded_pass === false && <Badge variant="outline" className="rounded-md border-warning/40 bg-warning/10 text-warning">PASS not backed by screen</Badge>}
      <span className="ml-auto text-muted-foreground">{grounding.observed_fields} of {grounding.checkable_fields} checkable fields seen{grounding.checkable_fields < fields ? ` · ${fields - grounding.checkable_fields} can’t be checked from screen text` : ''}</span>
    </div>
    <div className="divide-y rounded-md border">
      {Object.entries(grounding.fields).map(([field, item]) => <div key={field} className="flex items-center gap-2 px-2.5 py-1.5 text-xs">
        <span className={cn('size-1.5 shrink-0 rounded-full', item.status === 'observed' ? 'bg-success' : item.status === 'not_observed' ? 'bg-destructive' : 'bg-muted-foreground/40')} />
        <span className="w-28 shrink-0 truncate text-muted-foreground">{field}</span>
        <span className="min-w-0 flex-1 truncate font-mono text-[11px]" title={item.display || ''}>{item.display ?? '—'}</span>
        <span className="shrink-0 text-muted-foreground">{item.status === 'observed' ? `seen at step ${item.first_step}` : item.status === 'not_observed' ? 'never on screen' : 'can’t check from screen text'}</span>
      </div>)}
    </div>
    {fault && <p className="text-xs">{fault.missing_record ? 'Planted fault: target record deleted.' : <>Planted fault: <span className="text-muted-foreground">{fault.field}</span> is <span className="font-mono">{String(fault.display ?? fault.actual)}</span></>}
      {' '}{fault.on_screen === true ? <span className="text-destructive">· shown to the agent at step {fault.first_step}</span> : fault.on_screen === false ? <span className="text-muted-foreground">· never on screen</span> : <span className="text-muted-foreground">· visibility not text-checkable</span>}</p>}
  </div>
}
