import { useEffect, useRef, useState, type ReactNode } from 'react'
import { ChevronDown, ChevronRight, Download, Square } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { SidebarTrigger } from '@/components/ui/sidebar'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { useResource } from '@/hooks/use-resource'
import { routeHref, useMediaQuery } from '@/hooks/use-route'
import { post } from '@/lib/api'
import { actionLabel, executionStatus, resultScreen } from '@/lib/evidence'
import type { Checks, Session, Step } from '@/lib/types'
import { cn } from '@/lib/utils'
import { StepInspector } from './step-inspector'
import { VerdictTimeline } from './verdict-timeline'
import { AdmissionChecklist, ADMISSION_TEXT, ERROR_TEXT, GroundingDetail, OutcomeBadge, type TrialObservation } from './trial'
import { Disclosure, EmptyState, StatusBadge, pad, statusTone } from './primitives'

type SideTab = 'score' | 'checker' | 'device'

export function RunDetail({ id, session }: { id: string; session?: Session }) {
  const base = `/api/sessions/${encodeURIComponent(id)}`
  const steps = useResource<Step[]>(`${base}/steps`, 3000)
  const checks = useResource<Checks>(`${base}/checks`, 3000)
  const experiment = useResource<any>(`${base}/experiment`)
  const fallback = useResource<Session>(session ? null : base)
  const run = session || fallback.data
  const [selected, setSelected] = useState('')
  const [error, setError] = useState('')
  const [stopping, setStopping] = useState(false)
  const [side, setSide] = useState<SideTab>('score')
  const [mobile, setMobile] = useState<'steps' | 'evidence' | 'side'>('evidence')
  const [taskOpen, setTaskOpen] = useState(false)
  const wide = useMediaQuery('(min-width: 1024px)')
  const pending = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  // Live updates only trigger a refetch; the recorded data is the single source shown.
  useEffect(() => {
    const stream = new EventSource(`/api/stream/${encodeURIComponent(id)}`)
    const refresh = () => {
      if (!pending.current) pending.current = setTimeout(() => { steps.refresh(); checks.refresh(); pending.current = undefined }, 750)
    }
    for (const type of ['step_updated', 'step_recorded', 'checker_event', 'session_ended']) stream.addEventListener(type, refresh)
    return () => { stream.close(); if (pending.current) clearTimeout(pending.current) }
  }, [id])

  const allSteps = steps.data || []
  const step = allSteps.find(item => item.step_id === selected) || allSteps.at(-1)
  const stepIndex = step ? allSteps.indexOf(step) : -1
  const task = (experiment.data?.original_task || run?.initial_goal || 'Loading…') as string
  const active = ['running', 'paused', 'pending', 'queued'].includes(run?.status || '')
  const verdicts = checks.data?.records || []
  const tab = side === 'device' && !active ? 'score' : side

  function selectStep(stepId: string) { setSelected(stepId); setMobile('evidence') }
  function move(delta: number) {
    const next = allSteps[Math.min(allSteps.length - 1, Math.max(0, stepIndex + delta))]
    if (next) setSelected(next.step_id)
  }
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.target as HTMLElement).closest('input, textarea, select, [contenteditable], [role=dialog]')) return
      if (event.key === 'ArrowDown' || event.key === 'j') { event.preventDefault(); move(1) }
      if (event.key === 'ArrowUp' || event.key === 'k') { event.preventDefault(); move(-1) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  async function stop() {
    setStopping(true); setError('')
    try { await post('/api/stop', { session_id: id }) } catch (e) { setError((e as Error).message) } finally { setStopping(false) }
  }
  async function exportRun() {
    setError('')
    try {
      const response = await fetch(`${base}/research-export`)
      if (!response.ok) { const body = await response.json().catch(() => ({})); throw new Error(body.detail || `Export failed (${response.status})`) }
      const url = URL.createObjectURL(await response.blob()); const anchor = document.createElement('a')
      anchor.href = url; anchor.download = `artemis-${id}.zip`; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (e) { setError((e as Error).message) }
  }

  const stepsColumn = <Column title="Steps" meta={String(allSteps.length)}>
    <nav aria-label="Recorded steps" className="flex flex-col gap-0.5 p-2">
      {allSteps.map(item => {
        const on = step?.step_id === item.step_id
        const tone = statusTone(executionStatus(item))
        return <button key={item.step_id} onClick={() => selectStep(item.step_id)} aria-current={on || undefined}
          className={cn('flex w-full items-start gap-2.5 rounded-md px-2 py-1.5 text-left hover:bg-muted', on && 'bg-muted')}>
          <span className={cn('mt-0.5 w-6 shrink-0 font-mono text-[11px] text-muted-foreground', on && 'font-semibold text-foreground')}>{pad(item.step_number)}</span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[13px] font-medium">{actionLabel(item)}</span>
            {item.summary && <span className="block truncate text-xs text-muted-foreground">{item.summary}</span>}
          </span>
          <span className={cn('mt-2 size-1.5 shrink-0 rounded-full', tone === 'danger' ? 'bg-destructive' : tone === 'success' ? 'bg-success' : 'bg-muted-foreground/30')} />
        </button>
      })}
      {!allSteps.length && <p className="p-3 text-xs text-muted-foreground">{steps.loading ? 'Loading…' : 'No steps recorded.'}</p>}
    </nav>
  </Column>

  const evidenceColumn = <Column title="Evidence" meta={<span className="flex items-center gap-1">
    <span className="font-mono">{step ? `${pad(step.step_number)} / ${pad(allSteps.length)}` : '—'}</span>
    <Button size="icon-xs" variant="ghost" aria-label="Previous step" disabled={stepIndex <= 0} onClick={() => move(-1)}><ChevronDown className="rotate-180" /></Button>
    <Button size="icon-xs" variant="ghost" aria-label="Next step" disabled={stepIndex < 0 || stepIndex >= allSteps.length - 1} onClick={() => move(1)}><ChevronDown /></Button>
  </span>}>
    {step && run ? <StepInspector key={step.step_id} step={step} after={resultScreen(allSteps, stepIndex)} />
      : <p className="p-4 text-sm text-muted-foreground">{steps.loading ? 'Loading…' : 'No step selected.'}</p>}
  </Column>

  const sideColumn = <Tabs value={tab} onValueChange={v => setSide(v as SideTab)} className="flex h-full min-h-0 flex-col gap-0">
    <div className="flex h-10 shrink-0 items-center border-b px-2">
      <TabsList className="h-8">
        <TabsTrigger value="score" className="text-xs">Score</TabsTrigger>
        <TabsTrigger value="checker" className="text-xs">Checker{!!verdicts.length && <span className="ml-1 font-mono text-[10px] text-muted-foreground">{verdicts.length}</span>}</TabsTrigger>
        {active && <TabsTrigger value="device" className="text-xs">Live screen</TabsTrigger>}
      </TabsList>
    </div>
    <TabsContent value="score" className="min-h-0 flex-1 overflow-y-auto"><ScorePanel id={id} base={base} active={active} checks={checks} experiment={experiment.data} run={run} onError={setError} /></TabsContent>
    <TabsContent value="checker" className="min-h-0 flex-1 overflow-y-auto"><div className="flex flex-col gap-3 p-3">
      <p className="text-xs text-muted-foreground">The Checker reviews the agent’s individual steps while it works. “Passed” and “Failed” here grade those steps, not the test. The test result is on the Score tab.</p>
      <VerdictTimeline records={verdicts} onStep={selectStep} />
    </div></TabsContent>
    {active && <TabsContent value="device" className="relative min-h-0 flex-1 overflow-hidden bg-neutral-950">
      <img src="/api/stream/device-live" alt="Live device screen" className="h-full w-full object-contain" />
      <p className="absolute top-2 left-2 rounded bg-black/70 px-2 py-1 text-[11px] text-white/85">Live from {run?.device_serial || 'the device'} · not a recording</p>
    </TabsContent>}
  </Tabs>

  return <div className="flex h-full min-h-0 flex-col">
    <header className="flex h-12 shrink-0 items-center gap-2 border-b px-3">
      <SidebarTrigger />
      <Separator orientation="vertical" className="data-[orientation=vertical]:h-4" />
      <a href={routeHref({ page: 'runs' })} className="hidden shrink-0 text-sm text-muted-foreground hover:text-foreground sm:block">Runs</a>
      <ChevronRight className="hidden size-3.5 shrink-0 text-muted-foreground sm:block" />
      <StatusBadge status={run?.status || 'loading'} className="shrink-0" />
      <button className="min-w-0 flex-1 truncate text-left text-sm font-medium hover:underline hover:underline-offset-4" onClick={() => setTaskOpen(true)} title="Show the full test">{task.replace(/\s+/g, ' ')}</button>
      <Button size="sm" variant="outline" onClick={exportRun} disabled={!run || !steps.data}><Download /><span className="hidden md:inline">Export</span></Button>
      {active && <Button size="sm" variant="destructive" onClick={stop} disabled={stopping}><Square />{stopping ? 'Stopping…' : 'Stop'}</Button>}
    </header>

    {(error || steps.error || checks.error || fallback.error) && <p role="alert" className="shrink-0 border-b bg-destructive/10 px-4 py-2 text-sm text-destructive">{error || steps.error || checks.error || fallback.error}</p>}

    {wide ? <div className="grid min-h-0 flex-1 grid-cols-[300px_minmax(0,1fr)_380px] divide-x">
      {stepsColumn}{evidenceColumn}{sideColumn}
    </div>
      : <Tabs value={mobile} onValueChange={v => setMobile(v as typeof mobile)} className="flex min-h-0 flex-1 flex-col gap-0">
        <div className="shrink-0 border-b px-3 py-2"><TabsList className="w-full"><TabsTrigger value="steps">Steps</TabsTrigger><TabsTrigger value="evidence">Evidence</TabsTrigger><TabsTrigger value="side">Score</TabsTrigger></TabsList></div>
        <TabsContent value="steps" className="min-h-0 flex-1">{stepsColumn}</TabsContent>
        <TabsContent value="evidence" className="min-h-0 flex-1">{evidenceColumn}</TabsContent>
        <TabsContent value="side" className="min-h-0 flex-1">{sideColumn}</TabsContent>
      </Tabs>}

    <Dialog open={taskOpen} onOpenChange={setTaskOpen}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader><DialogTitle>Test</DialogTitle><DialogDescription>Exactly as the agent received it.</DialogDescription></DialogHeader>
        <p className="max-h-[60vh] overflow-y-auto text-sm leading-relaxed whitespace-pre-wrap break-words">{task}</p>
      </DialogContent>
    </Dialog>
  </div>
}

function Column({ title, meta, children }: { title: string; meta?: ReactNode; children: ReactNode }) {
  return <section className="flex h-full min-h-0 min-w-0 flex-col">
    <div className="flex h-10 shrink-0 items-center justify-between gap-2 border-b px-3">
      <h2 className="text-sm font-medium">{title}</h2>
      {meta && <div className="text-xs text-muted-foreground">{meta}</div>}
    </div>
    <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
  </section>
}

/** Verdict against the independent state read, whether the run counts, and the reads themselves. */
function ScorePanel({ id, base, active, checks, experiment, run, onError }: { id: string; base: string; active: boolean; checks: { data?: Checks; refresh: () => void }; experiment?: any; run?: Session; onError: (message: string) => void }) {
  const trial = useResource<{ agent: TrialObservation | null; checker: TrialObservation | null }>(`/api/sessions/${encodeURIComponent(id)}/trial`, 5000)
  const [finalizing, setFinalizing] = useState(false)
  const [visibility, setVisibility] = useState('')
  const [evidence, setEvidence] = useState('')
  const [saving, setSaving] = useState(false)
  const truth = checks.data?.ground_truth || []
  const pre = truth.find((r: any) => r.phase === 'pre')
  const postRead = [...truth].reverse().find((r: any) => r.phase === 'post')
  const review = [...truth].reverse().find((r: any) => r.phase === 'visibility_review')
  const agent = trial.data?.agent
  const checker = trial.data?.checker

  async function finalize() {
    setFinalizing(true); onError('')
    try { await post(`${base}/ground-truth/finalize`, {}); checks.refresh(); trial.refresh() } catch (e) { onError((e as Error).message) } finally { setFinalizing(false) }
  }
  async function saveReview() {
    setSaving(true); onError('')
    try { await post(`${base}/ground-truth/visibility-review`, { discoverable: visibility === 'yes', evidence: evidence.trim() }); checks.refresh(); trial.refresh() } catch (e) { onError((e as Error).message) } finally { setSaving(false) }
  }

  if (!pre) return <div className="p-3"><EmptyState title="Not scored">No independent state read is attached to this run, so its outcome is unknown.</EmptyState></div>

  return <div className="flex flex-col gap-4 p-3">
    {agent && <section className="flex flex-col gap-3">
      {active
        ? <p className="rounded-md border bg-muted/40 px-3 py-2 text-sm">Run in progress. It is scored once the run ends and the app data is read again.</p>
        : <div className="flex items-center justify-between gap-2"><p className="text-sm font-semibold">Result</p>
          {agent.error || agent.outcome === 'unscored' ? <span className="text-xs text-muted-foreground">Not counted: {ERROR_TEXT[agent.error || ''] || agent.error || 'not scored'}</span> : <OutcomeBadge outcome={agent.outcome} />}</div>}
      <dl className="grid grid-cols-3 gap-2 text-xs">
        <Fact label="Expected" value={agent.variant === 'fault' ? 'FAIL' : 'PASS'} note={agent.variant === 'fault' ? 'fault planted' : 'data correct'} />
        <Fact label={active ? 'Agent so far' : 'Agent said'} value={agent.agent_verdict || '—'} note={agent.agent_verdict ? 'from its notes' : 'no verdict yet'} />
        <Fact label="App data after" value={agent.post_oracle_correct === null ? '—' : agent.post_oracle_correct ? 'Correct' : 'Faulty'} note={agent.post_oracle_correct === null ? 'not read yet' : 'read from database'} />
      </dl>
      {agent.agent_verdict_source && <p className="rounded-md bg-muted/50 px-2.5 py-1.5 text-[11px] break-words text-muted-foreground" title={`${agent.agent_verdict_source.note}:${agent.agent_verdict_source.line}`}>“{agent.agent_verdict_source.text}” <span className="opacity-70">({agent.agent_verdict_source.note})</span></p>}
      <div className="border-t pt-3">
        <p className="mb-2 text-xs font-medium">{active ? 'Counts toward results when' : ADMISSION_TEXT[agent.admission] || agent.admission}</p>
        <AdmissionChecklist trial={agent} running={active} />
      </div>
      {agent.grounding && <div className="border-t pt-3"><GroundingDetail grounding={agent.grounding} verdict={agent.agent_verdict} running={active} /></div>}
      <p className="border-t pt-3 text-xs"><span className="text-muted-foreground">Checker’s verdict (second opinion): </span>{active ? 'pending' : checker?.error ? (ERROR_TEXT[checker.error] || checker.error) : checker?.checker_verdict || '—'}</p>
    </section>}

    <section className="flex flex-col gap-2 border-t pt-3">
      <p className="text-xs font-medium">App data reads</p>
      <Read label="Before run" value={pre.target_satisfied ? 'correct' : 'faulty (fault planted)'} hash={pre.state_sha256} />
      {postRead ? <Read label="After run" value={`${postRead.target_satisfied ? 'correct' : 'faulty'}${postRead.target_state_changed ? ', changed by the run' : ', unchanged'}`} hash={postRead.state_sha256} />
        : !active && <Button size="sm" variant="outline" className="self-start" onClick={finalize} disabled={finalizing}>{finalizing ? 'Reading device…' : 'Read state after run'}</Button>}
    </section>

    <Disclosure title="Fault visibility review" meta={review ? (review.discoverable ? 'visible' : 'not visible') : 'not reviewed'}>
      <div className="flex flex-col gap-3">
        <p className="text-xs text-muted-foreground">Could the fault be seen in the app’s screens?</p>
        <div className="grid gap-1.5"><Label>Visible</Label>
          <Select value={visibility || undefined} onValueChange={setVisibility}><SelectTrigger className="w-32"><SelectValue placeholder="Select" /></SelectTrigger><SelectContent><SelectItem value="yes">Yes</SelectItem><SelectItem value="no">No</SelectItem></SelectContent></Select>
        </div>
        <div className="grid gap-1.5"><Label htmlFor="visibility-evidence">Evidence</Label><Textarea id="visibility-evidence" value={evidence} onChange={e => setEvidence(e.target.value)} rows={2} placeholder="Step or screenshot" /></div>
        <Button size="sm" variant="outline" className="self-start" disabled={!visibility || evidence.trim().length < 8 || saving} onClick={saveReview}>{saving ? 'Saving…' : 'Save'}</Button>
      </div>
    </Disclosure>

    <p className="text-[11px] text-muted-foreground">{[run?.model_info?.id || experiment?.model?.id, experiment?.condition, agent?.harness_commit && `harness ${agent.harness_commit.slice(0, 8)}${agent.harness_dirty ? '*' : ''}`].filter(Boolean).join(' · ')}</p>
  </div>
}

function Fact({ label, value, note }: { label: string; value: string; note?: string }) {
  return <div className="min-w-0 rounded-md border px-2.5 py-2"><dt className="text-[10px] text-muted-foreground uppercase">{label}</dt><dd className="mt-0.5 truncate text-sm font-semibold">{value}</dd>{note && <dd className="truncate text-[10px] text-muted-foreground">{note}</dd>}</div>
}

function Read({ label, value, hash }: { label: string; value: string; hash?: string }) {
  return <div className="flex items-baseline justify-between gap-2 text-xs"><span><span className="text-muted-foreground">{label}: </span>{value}</span>{hash && <span className="font-mono text-[10px] text-muted-foreground">{hash.slice(0, 10)}</span>}</div>
}
