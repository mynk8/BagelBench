import { useMemo, useState, type ReactNode } from 'react'
import { ArrowUpRight, CircleAlert, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { post } from '@/lib/api'
import { useResource } from '@/hooks/use-resource'
import type { AndroidDevice, DeviceResponse } from '@/lib/types'
import { cn } from '@/lib/utils'

export type BatchState = { batch_id: string; status: 'running' | 'completed' | 'stopped' | 'failed' | 'interrupted'; total: number; index: number; completed: number; message: string; error: string | null; current_session_id: string | null; session_ids: string[]; experiment_name: string; fixture_kind?: string }
export type QaPair = { pair_id: string; app: string; bucket: string; bucket_id: string; mechanism: string; planned_read_tier: string | null; fixture_requirement: string; instruction: string; live: boolean; live_reason: string | null }
type PilotManifest = { suite_id: string; trials: { trial_id: string; variant: 'control' | 'fault' }[] }
type Mode = 'pair' | 'pilot' | 'written'

const CONDITIONS = [
  { id: 'baseline', label: 'Baseline', switches: {} },
  { id: 'thinking', label: 'Model thinking on', switches: { ARTEMIS_THINKING_ENABLED: true } },
]
const BATCH_LIMIT = 600
const ALL = '__all__'

function Field({ label, htmlFor, children, className }: { label: string; htmlFor?: string; children: ReactNode; className?: string }) {
  return <div className={cn('grid content-start gap-1.5', className)}><Label htmlFor={htmlFor} className="text-xs text-muted-foreground">{label}</Label>{children}</div>
}

function Alert({ children }: { children: ReactNode }) {
  return <p role="alert" className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive"><CircleAlert className="mt-px size-3.5 shrink-0" />{children}</p>
}

export function RunComposer({ open, onOpenChange, onStarted }: { open: boolean; onOpenChange: (open: boolean) => void; onStarted: (batch: BatchState) => void }) {
  const [mode, setMode] = useState<Mode>('pair')
  const [serial, setSerial] = useState('')
  const [name, setName] = useState('eval-v0.1')
  const [conditions, setConditions] = useState<string[]>(['baseline'])
  const [repeats, setRepeats] = useState(1)
  const [task, setTask] = useState('')
  const [app, setApp] = useState(ALL)
  const [bucket, setBucket] = useState(ALL)
  const [liveOnly, setLiveOnly] = useState(true)
  const [chosen, setChosen] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const devices = useResource<DeviceResponse | AndroidDevice[]>(open ? '/api/devices' : null, 10000)
  const choices = Array.isArray(devices.data) ? devices.data : devices.data?.devices || []
  const device = serial || choices[0]?.serial || choices[0]?.device_id || ''
  const catalog = useResource<{ suite_id: string; pairs: QaPair[] }>(open && mode === 'pair' ? '/api/research/qa/pairs' : null)
  const manifest = useResource<PilotManifest>(open && mode === 'pilot' ? '/api/research/pilot' : null)

  const pairs = catalog.data?.pairs || []
  const apps = useMemo(() => [...new Set(pairs.map(p => p.app))].sort(), [pairs])
  const buckets = useMemo(() => [...new Map(pairs.map(p => [p.bucket_id, p.bucket])).entries()], [pairs])
  const visible = pairs.filter(p => (app === ALL || p.app === app) && (bucket === ALL || p.bucket_id === bucket) && (!liveOnly || p.live))
  const rows = CONDITIONS.filter(c => conditions.includes(c.id))
  const variantsPerCase = mode === 'written' ? 1 : 2
  const cases = mode === 'pair' ? chosen.length : mode === 'pilot' ? (manifest.data?.trials.length || 0) / 2 : task.trim() ? 1 : 0
  const planCount = cases * variantsPerCase * rows.length * repeats
  const needsEmulator = mode !== 'written' && !device.startsWith('emulator-')

  function onePerApp() {
    const picked = apps.map(a => pairs.find(p => p.app === a && p.live)?.pair_id).filter(Boolean) as string[]
    setChosen(picked)
  }

  async function start(e: React.FormEvent) {
    e.preventDefault()
    if (busy || planCount < 1 || planCount > BATCH_LIMIT || !device || needsEmulator) return
    const repeatsList = Array.from({ length: repeats }, (_, i) => i + 1)
    const plans = mode === 'pair'
      ? rows.flatMap(c => chosen.flatMap(pairId => repeatsList.flatMap(repeat => (['control', 'fault'] as const).map(variant =>
        ({ condition_id: c.id, switches: c.switches, qa_pair_id: pairId, variant, fault_seed: variant === 'fault', repeat })))))
      : mode === 'pilot'
        ? rows.flatMap(c => (manifest.data?.trials || []).flatMap(trial => repeatsList.map(repeat =>
          ({ condition_id: c.id, switches: c.switches, pilot_trial_id: trial.trial_id, fault_seed: trial.variant === 'fault', repeat }))))
        : rows.flatMap(c => repeatsList.map(repeat => ({ condition_id: c.id, switches: c.switches, task: task.trim(), repeat })))
    setBusy(true); setError('')
    try {
      const batch = await post<BatchState>('/api/research/batches', { experiment_name: name, device_serial: device, fixture_kind: mode === 'pair' ? 'qa' : mode === 'pilot' ? 'pilot' : 'none', plans })
      onOpenChange(false); onStarted(batch)
    } catch (err) { setError((err as Error).message) } finally { setBusy(false) }
  }

  return <Dialog open={open} onOpenChange={v => { if (!busy) onOpenChange(v) }}>
    <DialogContent className="flex max-h-[calc(100dvh-2rem)] flex-col gap-0 p-0 sm:max-w-3xl" onInteractOutside={e => { if (busy) e.preventDefault() }}>
      <DialogHeader className="border-b px-6 pt-6 pb-4">
        <DialogTitle>New run</DialogTitle>
        <DialogDescription>Each eval case runs twice with the same instruction: once on correct data, once with the fault.</DialogDescription>
      </DialogHeader>
      <form onSubmit={start} className="flex min-h-0 flex-1 flex-col">
        <div className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto px-6 py-5">
          <Tabs value={mode} onValueChange={v => setMode(v as Mode)}>
            <TabsList className="w-full">
              <TabsTrigger value="pair">Eval cases</TabsTrigger>
              <TabsTrigger value="pilot">Pilot · 60 trials</TabsTrigger>
              <TabsTrigger value="written">Written test</TabsTrigger>
            </TabsList>
          </Tabs>

          {mode === 'pair' && <div className="flex flex-col gap-3">
            <div className="grid gap-3 sm:grid-cols-[1fr_1fr_auto]">
              <Select value={app} onValueChange={setApp}>
                <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value={ALL}>All apps</SelectItem>{apps.map(a => <SelectItem key={a} value={a}>{a}</SelectItem>)}</SelectContent>
              </Select>
              <Select value={bucket} onValueChange={setBucket}>
                <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value={ALL}>All buckets</SelectItem>{buckets.map(([id, label]) => <SelectItem key={id} value={id}>{label}</SelectItem>)}</SelectContent>
              </Select>
              <Button type="button" variant="outline" onClick={onePerApp} disabled={!pairs.length}>One pair per app</Button>
            </div>
            <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
              <label className="flex items-center gap-2"><Checkbox checked={liveOnly} onCheckedChange={v => setLiveOnly(v === true)} />Runnable on device only</label>
              <span>{chosen.length} selected · {visible.length} shown{catalog.data ? ` · ${catalog.data.suite_id}` : ''}</span>
            </div>
            <ScrollArea className="h-64 rounded-md border">
              <div className="divide-y">
                {visible.map(p => {
                  const on = chosen.includes(p.pair_id)
                  return <label key={p.pair_id} title={p.live ? p.instruction : p.live_reason || ''} className={cn('flex cursor-pointer items-start gap-3 px-3 py-2', !p.live && 'cursor-not-allowed opacity-50', on && 'bg-muted')}>
                    <Checkbox className="mt-0.5" disabled={!p.live} checked={on} onCheckedChange={v => setChosen(v === true ? [...chosen, p.pair_id] : chosen.filter(x => x !== p.pair_id))} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm">{p.app} · {p.bucket} · {p.mechanism}</span>
                      <span className="block truncate font-mono text-[11px] text-muted-foreground">{p.pair_id} · tier {p.planned_read_tier || '?'}{p.live ? '' : ' · no live adapter'}</span>
                    </span>
                  </label>
                })}
                {catalog.loading && <p className="p-3 text-xs text-muted-foreground">Loading catalog…</p>}
              </div>
            </ScrollArea>
          </div>}

          {mode === 'pilot' && <p className="rounded-md border bg-muted/40 px-3 py-2 text-sm">{manifest.loading ? 'Loading pilot…' : manifest.error || `${manifest.data?.suite_id} · ${manifest.data?.trials.length || 0} trials (30 control/fault pairs)`}</p>}

          {mode === 'written' && <Field label="Test" htmlFor="run-task"><Textarea id="run-task" value={task} onChange={e => setTask(e.target.value)} rows={5} className="min-h-28 text-sm" placeholder="Describe what to test and what counts as PASS." /></Field>}

          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Device">
              <Select value={device || undefined} onValueChange={setSerial}>
                <SelectTrigger className="w-full"><SelectValue placeholder={devices.loading ? 'Finding devices…' : 'No device'} /></SelectTrigger>
                <SelectContent>{choices.filter(d => d.serial || d.device_id).map(d => <SelectItem key={d.serial || d.device_id} value={(d.serial || d.device_id)!}>{d.model || d.serial || d.device_id}</SelectItem>)}</SelectContent>
              </Select>
            </Field>
            <Field label="Run name" htmlFor="run-name"><Input id="run-name" value={name} onChange={e => setName(e.target.value)} maxLength={80} required /></Field>
            <Field label="Repeats" htmlFor="run-repeats"><Input id="run-repeats" type="number" min={1} max={12} value={repeats} onChange={e => setRepeats(Math.max(1, Math.min(12, Number(e.target.value) || 1)))} /></Field>
          </div>
          <Field label="Conditions">
            <ToggleGroup type="multiple" variant="outline" size="sm" value={conditions} onValueChange={setConditions} className="flex w-full flex-wrap justify-start gap-1.5 shadow-none *:rounded-md! *:border-l!">
              {CONDITIONS.map(c => <ToggleGroupItem key={c.id} value={c.id} className="flex-none px-3 text-xs data-[state=on]:bg-primary data-[state=on]:text-primary-foreground">{c.label}</ToggleGroupItem>)}
            </ToggleGroup>
          </Field>

          {!devices.loading && !choices.length && <Alert>No device connected. Start the emulator first (Environment page).</Alert>}
          {needsEmulator && !!choices.length && <Alert>Eval cases and the pilot need a dedicated AndroidWorld emulator.</Alert>}
          {planCount > BATCH_LIMIT && <Alert>{planCount} runs exceeds the limit of {BATCH_LIMIT}.</Alert>}
          {(catalog.error || manifest.error || devices.error) && <Alert>{catalog.error || manifest.error || devices.error}</Alert>}
          {error && <Alert>{error}</Alert>}
        </div>
        <DialogFooter className="items-center gap-2 border-t px-6 py-4 sm:justify-between">
          <p className="text-sm"><span className="font-semibold">{planCount}</span> run{planCount === 1 ? '' : 's'}</p>
          <div className="flex gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Cancel</Button>
            <Button type="submit" disabled={busy || planCount < 1 || planCount > BATCH_LIMIT || !device || needsEmulator || !conditions.length}>{busy ? <Loader2 className="animate-spin" /> : <ArrowUpRight />}{busy ? 'Starting…' : 'Run'}</Button>
          </div>
        </DialogFooter>
      </form>
    </DialogContent>
  </Dialog>
}
