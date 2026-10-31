import { useState, type ReactNode } from 'react'
import { Download } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useResource } from '@/hooks/use-resource'
import { routeHref } from '@/hooks/use-route'
import { ERROR_TEXT, OutcomeBadge, type TrialObservation } from './trial'
import { EmptyState, formatTime } from './primitives'

type Rate = { numerator: number; denominator: number; rate: number | null; wilson_95: [number, number] | null }
type Summary = {
  runs: number; counted: number; excluded: number; accuracy: Rate; wrong_pass: Rate; wrong_fail: Rate; no_decision: Rate; pair_accuracy: Rate
  outcomes: Record<'correct_pass' | 'correct_fail' | 'false_pass' | 'false_fail' | 'inconclusive', number>
  mean_steps: number | null; mean_seconds: number | null; mean_tokens: number | null
}
type Run = TrialObservation & { app: string | null; bucket: string | null; mechanism: string | null; expected_verdict: string | null; seeded_at: number | null; efficiency: { steps: number | null; seconds: number | null; tokens: number | null } }
type Score = { suite_id: string; overall: Summary; leaderboard: (Summary & { model: string; condition: string })[]; by_bucket: (Summary & { name: string })[]; by_app: (Summary & { name: string })[]; exclusions: Record<string, number>; runs: Run[] }

const SEGMENTS = [
  { key: 'correct', label: 'Correct', color: 'var(--chart-1)' },
  { key: 'false_pass', label: 'Wrong PASS', color: 'var(--chart-2)' },
  { key: 'false_fail', label: 'Wrong FAIL', color: 'var(--chart-3)' },
  { key: 'inconclusive', label: 'No decision', color: 'var(--chart-4)' },
] as const

const pct = (r?: number | null) => r == null ? '—' : `${Math.round(r * 100)}%`
const ci = (rate: Rate) => rate.wilson_95 ? `${pct(rate.wilson_95[0])}–${pct(rate.wilson_95[1])}` : ''
const num = (v: number | null, digits = 0) => v == null ? '—' : v.toFixed(digits)

type Tip = { text: string; x: number; y: number } | null

/** Benchmark readout: every number is recomputed from saved runs; excluded runs are counted, never scored. */
export function ResultsPage() {
  const [suite, setSuite] = useState<'eval' | 'pilot'>('eval')
  const [judge, setJudge] = useState<'agent' | 'checker'>('agent')
  const [tip, setTip] = useState<Tip>(null)
  const url = `/api/research/eval/score?suite=${suite}&judge=${judge}`
  const score = useResource<Score>(url, 10000)
  const data = score.data
  const o = data?.overall
  const show = (text: string) => (e: React.MouseEvent) => setTip({ text, x: e.clientX, y: e.clientY })

  return <ScrollArea className="h-full">
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 p-4 md:p-8" onMouseLeave={() => setTip(null)}>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Results</h1>
          <p className="mt-1 font-mono text-xs text-muted-foreground">{data?.suite_id || '…'}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Tabs value={suite} onValueChange={v => setSuite(v as typeof suite)}><TabsList><TabsTrigger value="eval">Eval set</TabsTrigger><TabsTrigger value="pilot">Pilot</TabsTrigger></TabsList></Tabs>
          <Tabs value={judge} onValueChange={v => setJudge(v as typeof judge)}><TabsList><TabsTrigger value="agent">Agent verdict</TabsTrigger><TabsTrigger value="checker">Checker verdict</TabsTrigger></TabsList></Tabs>
          <Button variant="outline" size="sm" asChild><a href={url} target="_blank" rel="noreferrer"><Download />JSON</a></Button>
        </div>
      </div>

      {score.error && <p role="alert" className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">{score.error}</p>}
      {data && !data.runs.length && <EmptyState title="No runs yet">Run eval cases from New run.</EmptyState>}

      {o && !!data?.runs.length && <>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
          <Stat label="Accuracy" rate={o.accuracy} />
          <Stat label="Wrong PASS" rate={o.wrong_pass} note="of fault runs" />
          <Stat label="Wrong FAIL" rate={o.wrong_fail} note="of control runs" />
          <Stat label="No decision" rate={o.no_decision} />
          <Stat label="Pair accuracy" rate={o.pair_accuracy} note="both variants right" />
          <div className="rounded-lg border p-3"><p className="text-xs text-muted-foreground">Counted</p><p className="mt-1 text-2xl font-semibold tabular-nums">{o.counted}<span className="text-base font-normal text-muted-foreground">/{o.runs}</span></p><p className="text-[11px] text-muted-foreground">{o.excluded} excluded</p></div>
        </div>

        <section className="flex flex-col gap-2">
          <h2 className="text-sm font-semibold">Leaderboard</h2>
          <div className="overflow-x-auto rounded-lg border">
            <Table>
              <TableHeader className="bg-muted/50"><TableRow>
                <TableHead>Model</TableHead><TableHead>Condition</TableHead><TableHead className="text-right">Accuracy</TableHead><TableHead className="text-right">Wrong PASS</TableHead><TableHead className="text-right">Wrong FAIL</TableHead><TableHead className="text-right">No decision</TableHead><TableHead className="text-right">Pairs</TableHead><TableHead className="text-right">Counted</TableHead><TableHead className="text-right">Steps</TableHead><TableHead className="text-right">Min</TableHead><TableHead className="text-right">Tokens (k)</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {data.leaderboard.map(r => <TableRow key={r.model + r.condition}>
                  <TableCell className="max-w-56 truncate text-xs" title={r.model}>{r.model}</TableCell>
                  <TableCell className="max-w-56 truncate text-xs" title={r.condition}>{r.condition}</TableCell>
                  <RateCell rate={r.accuracy} strong /><RateCell rate={r.wrong_pass} /><RateCell rate={r.wrong_fail} /><RateCell rate={r.no_decision} /><RateCell rate={r.pair_accuracy} />
                  <TableCell className="text-right text-xs tabular-nums">{r.counted}/{r.runs}</TableCell>
                  <TableCell className="text-right text-xs tabular-nums">{num(r.mean_steps, 1)}</TableCell>
                  <TableCell className="text-right text-xs tabular-nums">{r.mean_seconds == null ? '—' : (r.mean_seconds / 60).toFixed(1)}</TableCell>
                  <TableCell className="text-right text-xs tabular-nums">{r.mean_tokens == null ? '—' : Math.round(r.mean_tokens / 1000)}</TableCell>
                </TableRow>)}
              </TableBody>
            </Table>
          </div>
          <p className="text-[11px] text-muted-foreground">Rates over counted runs, with 95% Wilson intervals. Steps, minutes and tokens are means per counted run.</p>
        </section>

        <div className="grid gap-6 lg:grid-cols-[minmax(0,420px)_1fr]">
        <ChartCard title="Verdict vs app data" note="Rows: what code read from the app after the run. Columns: what the judge declared.">
          <VerdictMatrix runs={data.runs.filter(r => !r.error)} judge={judge === 'agent' ? 'Agent' : 'Checker'} show={show} hide={() => setTip(null)} />
        </ChartCard>
        <ChartCard title="Outcome mix" note="Share of counted runs per model and condition.">
          <div className="flex flex-wrap gap-4 text-xs">{SEGMENTS.map(s => <span key={s.key} className="flex items-center gap-1.5"><span className="size-2.5 rounded-sm" style={{ background: s.color }} />{s.label}</span>)}</div>
          <div className="flex flex-col gap-3">
            {data.leaderboard.map(r => {
              const counts = { correct: r.outcomes.correct_pass + r.outcomes.correct_fail, false_pass: r.outcomes.false_pass, false_fail: r.outcomes.false_fail, inconclusive: r.outcomes.inconclusive }
              return <div key={r.model + r.condition} className="grid grid-cols-[minmax(0,220px)_1fr] items-center gap-3">
                <p className="truncate text-xs" title={`${r.model} · ${r.condition}`}>{r.condition.split('/').pop()} <span className="text-muted-foreground">· {r.model.split('/').pop()}</span></p>
                <div className="flex h-6 gap-[2px]">
                  {r.counted ? SEGMENTS.filter(s => counts[s.key]).map((s, i, all) => {
                    const share = counts[s.key] / r.counted
                    return <div key={s.key} onMouseMove={show(`${s.label}: ${counts[s.key]} of ${r.counted} (${pct(share)})`)} onMouseLeave={() => setTip(null)}
                      className="flex items-center justify-center text-[11px] font-medium text-white" style={{ width: `${share * 100}%`, background: s.color, borderRadius: `${i === 0 ? 4 : 0}px ${i === all.length - 1 ? 4 : 0}px ${i === all.length - 1 ? 4 : 0}px ${i === 0 ? 4 : 0}px` }}>
                      {share >= 0.12 ? counts[s.key] : ''}
                    </div>
                  }) : <p className="text-xs text-muted-foreground">No counted runs</p>}
                </div>
              </div>
            })}
          </div>
        </ChartCard>
        </div>

        <div className="grid gap-6">
          <ChartCard title="Accuracy by bucket" note="Bars: accuracy. Lines: 95% interval."><RateBars rows={data.by_bucket} show={show} hide={() => setTip(null)} /></ChartCard>
          <ChartCard title="Accuracy by app" note="Bars: accuracy. Lines: 95% interval."><RateBars rows={data.by_app} show={show} hide={() => setTip(null)} /></ChartCard>
        </div>

        {!!Object.keys(data.exclusions).length && <section className="flex flex-col gap-2">
          <h2 className="text-sm font-semibold">Excluded runs</h2>
          <div className="flex flex-wrap gap-2 text-xs">{Object.entries(data.exclusions).map(([k, n]) => <span key={k} className="rounded-md border px-2 py-1">{ERROR_TEXT[k] || k}: <b className="tabular-nums">{n}</b></span>)}</div>
        </section>}

        <section className="flex flex-col gap-2">
          <h2 className="text-sm font-semibold">Runs</h2>
          <div className="overflow-x-auto rounded-lg border">
            <Table>
              <TableHeader className="bg-muted/50"><TableRow>
                <TableHead>Started</TableHead><TableHead>Pair</TableHead><TableHead>App · bucket</TableHead><TableHead>Variant</TableHead><TableHead>Expected</TableHead><TableHead>Agent</TableHead><TableHead>Outcome</TableHead><TableHead className="text-right">Steps</TableHead><TableHead className="text-right">Tokens (k)</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {data.runs.map(r => <TableRow key={r.session_id}>
                  <TableCell className="text-xs whitespace-nowrap"><a className="hover:underline" href={routeHref({ page: 'run', id: r.session_id })}>{formatTime(r.seeded_at || undefined)}</a></TableCell>
                  <TableCell className="font-mono text-[11px]">{r.pair_id}</TableCell>
                  <TableCell className="text-xs">{r.app}<p className="text-muted-foreground">{r.bucket} · {r.mechanism}</p></TableCell>
                  <TableCell className="text-xs capitalize">{r.variant}</TableCell>
                  <TableCell className="text-xs">{r.expected_verdict || (r.variant === 'fault' ? 'FAIL' : 'PASS')}</TableCell>
                  <TableCell className="text-xs">{r.verdict || '—'}</TableCell>
                  <TableCell>{r.error ? <span className="text-xs text-muted-foreground">Excluded: {ERROR_TEXT[r.error] || r.error}</span> : <OutcomeBadge outcome={r.outcome} />}</TableCell>
                  <TableCell className="text-right text-xs tabular-nums">{r.efficiency.steps ?? '—'}</TableCell>
                  <TableCell className="text-right text-xs tabular-nums">{r.efficiency.tokens == null ? '—' : Math.round(r.efficiency.tokens / 1000)}</TableCell>
                </TableRow>)}
              </TableBody>
            </Table>
          </div>
        </section>
      </>}
    </div>
    {tip && <div className="pointer-events-none fixed z-50 rounded-md border bg-popover px-2 py-1 text-xs text-popover-foreground shadow-md" style={{ left: tip.x + 12, top: tip.y + 12 }}>{tip.text}</div>}
  </ScrollArea>
}

function Stat({ label, rate, note }: { label: string; rate: Rate; note?: string }) {
  return <div className="rounded-lg border p-3">
    <p className="text-xs text-muted-foreground">{label}</p>
    <p className="mt-1 text-2xl font-semibold tabular-nums">{pct(rate.rate)}</p>
    <p className="text-[11px] text-muted-foreground tabular-nums">{rate.numerator}/{rate.denominator}{rate.wilson_95 ? ` · ${ci(rate)}` : ''}{note ? ` · ${note}` : ''}</p>
  </div>
}

function RateCell({ rate, strong }: { rate: Rate; strong?: boolean }) {
  return <TableCell className="text-right text-xs tabular-nums whitespace-nowrap"><span className={strong ? 'font-semibold' : ''}>{pct(rate.rate)}</span>{rate.denominator ? <span className="text-muted-foreground"> {rate.numerator}/{rate.denominator}</span> : null}</TableCell>
}

function ChartCard({ title, note, children }: { title: string; note: string; children: ReactNode }) {
  return <section className="flex flex-col gap-3 rounded-lg border p-4">
    <div><h2 className="text-sm font-semibold">{title}</h2><p className="text-[11px] text-muted-foreground">{note}</p></div>
    {children}
  </section>
}

/** Confusion matrix of the judge's verdict against the post-run data read. Diagonal cells are correct. */
function VerdictMatrix({ runs, judge, show, hide }: { runs: Run[]; judge: string; show: (text: string) => (e: React.MouseEvent) => void; hide: () => void }) {
  const rows = [{ key: true, label: 'Data correct', right: 'PASS' }, { key: false, label: 'Data faulty', right: 'FAIL' }]
  const cols = [{ key: 'PASS', label: 'PASS' }, { key: 'FAIL', label: 'FAIL' }, { key: null, label: 'No decision' }]
  const said = (r: Run) => r.verdict === 'PASS' || r.verdict === 'FAIL' ? r.verdict : null
  const cell = (row: boolean, col: string | null) => runs.filter(r => r.post_oracle_correct === row && said(r) === col).length
  const max = Math.max(1, ...rows.flatMap(r => cols.map(c => cell(r.key, c.key))))
  return <div className="grid grid-cols-[96px_repeat(3,minmax(0,1fr))] gap-[2px] text-xs">
    <span />{cols.map(c => <p key={c.label} className="pb-1 text-center text-muted-foreground">{judge}: {c.label}</p>)}
    {rows.map(r => {
      const total = cols.reduce((n, c) => n + cell(r.key, c.key), 0)
      return [<p key={r.label} className="flex items-center text-muted-foreground">{r.label}</p>, ...cols.map(c => {
        const n = cell(r.key, c.key), ok = c.key === r.right
        const tone = ok ? 'var(--chart-1)' : 'var(--chart-2)'
        return <div key={r.label + c.label} onMouseMove={show(`${r.label}, ${judge.toLowerCase()} said ${c.label}: ${n} of ${total} runs${ok ? ' (correct)' : n ? ' (wrong)' : ''}`)} onMouseLeave={hide}
          className="flex h-16 flex-col items-center justify-center rounded-[4px] border"
          style={{ background: n ? `color-mix(in oklab, ${tone} ${12 + 48 * n / max}%, transparent)` : undefined }}>
          <span className="text-lg font-semibold tabular-nums">{n}</span>
          <span className="text-[10px] text-muted-foreground">{ok ? 'correct' : c.key ? 'wrong' : 'no decision'}</span>
        </div>
      })]
    })}
  </div>
}

/** One horizontal bar per group on a fixed 0–100% axis, with the 95% interval drawn as a line. */
function RateBars({ rows, show, hide }: { rows: (Summary & { name: string })[]; show: (text: string) => (e: React.MouseEvent) => void; hide: () => void }) {
  return <div className="flex flex-col gap-2">
    <div className="grid grid-cols-[minmax(0,180px)_1fr_80px] gap-3 text-[10px] text-muted-foreground"><span /><div className="flex justify-between"><span>0%</span><span>50%</span><span>100%</span></div><span /></div>
    {rows.map(r => {
      const a = r.accuracy
      return <div key={r.name} className="grid grid-cols-[minmax(0,180px)_1fr_80px] items-center gap-3"
        onMouseMove={show(`${r.name}: ${pct(a.rate)} (${a.numerator}/${a.denominator})${a.wilson_95 ? `, 95% ${ci(a)}` : ''}`)} onMouseLeave={hide}>
        <p className="truncate text-xs" title={r.name}>{r.name}</p>
        <div className="relative h-5 rounded-sm bg-muted/60">
          {a.rate != null && <div className="absolute inset-y-0 left-0 rounded-r-[4px]" style={{ width: `${a.rate * 100}%`, background: 'var(--chart-1)' }} />}
          {a.wilson_95 && <div className="absolute top-1/2 h-[2px] -translate-y-1/2 bg-foreground/70" style={{ left: `${a.wilson_95[0] * 100}%`, width: `${(a.wilson_95[1] - a.wilson_95[0]) * 100}%` }} />}
        </div>
        <p className="text-right text-xs tabular-nums">{a.denominator ? `${pct(a.rate)} · ${a.numerator}/${a.denominator}` : <span className="text-muted-foreground">no runs</span>}</p>
      </div>
    })}
  </div>
}
