import { useMemo, useState } from 'react'
import { Check, Loader2, Play, RefreshCw, X } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useResource } from '@/hooks/use-resource'
import { post } from '@/lib/api'
import type { AndroidDevice, DeviceResponse } from '@/lib/types'
import type { BatchState } from './run-composer'
import { Disclosure, JsonBlock } from './primitives'

type VerifyRow = { pair_id: string; app: string; bucket_id: string; bucket: string; mechanism: string; verifier_id: string; control_true: boolean; fault_false: boolean; artifact_hashes_match: boolean; separates: boolean; live: boolean }
type Verify = {
  source: string; suite_id: string; pairs: VerifyRow[]
  summary: { pair_count: number; control_true_count: number; fault_false_count: number; issues: unknown[]; duplicate_pair_ids: number; duplicate_reference_pairs: number; template_count: number; unique_source_parameter_sets: number }
  detail?: { contract: unknown; reference_control: unknown; reference_fault: unknown; expected_ui_evidence?: string }
}
type Catalog = { suite_id: string; dataset_files_sha256: Record<string, string>; pairs: { pair_id: string; instruction: string; planned_read_tier: string | null; fixture_requirement: string; live_reason: string | null }[] }

const ALL = '__all__'
const yes = (ok: boolean) => ok ? <Check className="size-4 text-success" aria-label="yes" /> : <X className="size-4 text-destructive" aria-label="no" />

/** The frozen eval set and its offline verifier. Reference checks use authored artifacts, never device observations. */
export function EvalPage({ onStarted }: { onStarted: (batch: BatchState) => void }) {
  const verify = useResource<Verify>('/api/research/qa/verify')
  const catalog = useResource<Catalog>('/api/research/qa/pairs')
  const devices = useResource<DeviceResponse | AndroidDevice[]>('/api/devices', 10000)
  const [app, setApp] = useState(ALL)
  const [bucket, setBucket] = useState(ALL)
  const [open, setOpen] = useState<string | null>(null)

  const rows = verify.data?.pairs || []
  const s = verify.data?.summary
  const apps = useMemo(() => [...new Set(rows.map(r => r.app))].sort(), [rows])
  const byBucket = useMemo(() => {
    const groups = new Map<string, { label: string; pairs: number; separated: number; live: number }>()
    for (const r of rows) {
      const g = groups.get(r.bucket_id) || { label: r.bucket, pairs: 0, separated: 0, live: 0 }
      g.pairs++; if (r.separates) g.separated++; if (r.live) g.live++
      groups.set(r.bucket_id, g)
    }
    return [...groups.entries()]
  }, [rows])
  const shown = rows.filter(r => (app === ALL || r.app === app) && (bucket === ALL || r.bucket_id === bucket))
  const deviceList = Array.isArray(devices.data) ? devices.data : devices.data?.devices || []
  const emulator = deviceList.map(d => d.serial || d.device_id || '').find(id => id.startsWith('emulator-'))

  return <ScrollArea className="h-full">
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 p-4 md:p-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Eval set</h1>
          <p className="mt-1 font-mono text-xs text-muted-foreground">{verify.data?.suite_id || '…'}{catalog.data ? ` · pairs.jsonl ${catalog.data.dataset_files_sha256['pairs.jsonl']?.slice(0, 12)}` : ''}</p>
        </div>
        <Button variant="outline" size="sm" onClick={verify.refresh} disabled={verify.loading}>{verify.loading ? <Loader2 className="animate-spin" /> : <RefreshCw />}Re-verify</Button>
      </div>

      {verify.error && <p role="alert" className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">{verify.error}</p>}

      {s && <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <Stat label="Pairs" value={s.pair_count} note={`${s.pair_count * 2} variants`} />
        <Stat label="Controls verified true" value={s.control_true_count} note={`of ${s.pair_count}`} />
        <Stat label="Faults verified false" value={s.fault_false_count} note={`of ${s.pair_count}`} />
        <Stat label="Contract issues" value={s.issues.length + s.duplicate_pair_ids + s.duplicate_reference_pairs} note="hash, duplicate, separation" />
        <Stat label="Runnable on device" value={rows.filter(r => r.live).length} note="pairs with a live adapter" />
      </div>}
      <p className="-mt-3 text-xs text-muted-foreground">Reference check: the verifier is re-run on the authored control and fault artifacts. No device or model is involved. Device truth comes only from live runs.</p>

      <div className="overflow-hidden rounded-lg border">
        <Table>
          <TableHeader className="bg-muted/50"><TableRow><TableHead>Bucket</TableHead><TableHead className="text-right">Pairs</TableHead><TableHead className="text-right">Separated</TableHead><TableHead className="text-right">Runnable on device</TableHead></TableRow></TableHeader>
          <TableBody>
            {byBucket.map(([id, g]) => <TableRow key={id} className="cursor-pointer" onClick={() => setBucket(id)}>
              <TableCell>{g.label}</TableCell><TableCell className="text-right tabular-nums">{g.pairs}</TableCell>
              <TableCell className="text-right tabular-nums">{g.separated}</TableCell>
              <TableCell className="text-right tabular-nums">{g.live ? g.live : <span className="text-muted-foreground">adapter not built</span>}</TableCell>
            </TableRow>)}
          </TableBody>
        </Table>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Select value={app} onValueChange={setApp}><SelectTrigger className="w-48"><SelectValue /></SelectTrigger><SelectContent><SelectItem value={ALL}>All apps</SelectItem>{apps.map(a => <SelectItem key={a} value={a}>{a}</SelectItem>)}</SelectContent></Select>
        <Select value={bucket} onValueChange={setBucket}><SelectTrigger className="w-64"><SelectValue /></SelectTrigger><SelectContent><SelectItem value={ALL}>All buckets</SelectItem>{byBucket.map(([id, g]) => <SelectItem key={id} value={id}>{g.label}</SelectItem>)}</SelectContent></Select>
        <span className="text-xs text-muted-foreground">{shown.length} pairs</span>
      </div>

      <div className="overflow-hidden rounded-lg border">
        <Table>
          <TableHeader className="bg-muted/50"><TableRow>
            <TableHead>Pair</TableHead><TableHead>App</TableHead><TableHead>Bucket · mechanism</TableHead>
            <TableHead className="text-center">Control true</TableHead><TableHead className="text-center">Fault false</TableHead><TableHead className="text-center">Hashes</TableHead><TableHead>Device</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {shown.slice(0, 300).map(r => <TableRow key={r.pair_id} className="cursor-pointer" onClick={() => setOpen(r.pair_id)}>
              <TableCell className="font-mono text-xs">{r.pair_id}</TableCell><TableCell className="text-xs">{r.app}</TableCell>
              <TableCell className="text-xs">{r.bucket}<p className="text-muted-foreground">{r.mechanism}</p></TableCell>
              <TableCell><div className="flex justify-center">{yes(r.control_true)}</div></TableCell>
              <TableCell><div className="flex justify-center">{yes(r.fault_false)}</div></TableCell>
              <TableCell><div className="flex justify-center">{yes(r.artifact_hashes_match)}</div></TableCell>
              <TableCell>{r.live ? <Badge variant="secondary" className="rounded-md">Runnable</Badge> : <span className="text-xs text-muted-foreground">Reference only</span>}</TableCell>
            </TableRow>)}
          </TableBody>
        </Table>
        {shown.length > 300 && <p className="border-t px-3 py-2 text-xs text-muted-foreground">Showing 300 of {shown.length}; filter by app or bucket to see the rest.</p>}
      </div>
    </div>
    {open && <PairDetail pairId={open} catalog={catalog.data} emulator={emulator} onClose={() => setOpen(null)} onStarted={onStarted} />}
  </ScrollArea>
}

function Stat({ label, value, note }: { label: string; value: number; note: string }) {
  return <div className="rounded-lg border p-3"><p className="text-xs text-muted-foreground">{label}</p><p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p><p className="text-[11px] text-muted-foreground">{note}</p></div>
}

function PairDetail({ pairId, catalog, emulator, onClose, onStarted }: { pairId: string; catalog?: Catalog; emulator?: string; onClose: () => void; onStarted: (batch: BatchState) => void }) {
  const result = useResource<Verify>(`/api/research/qa/verify?pair_id=${pairId}`)
  const row = result.data?.pairs[0]
  const meta = catalog?.pairs.find(p => p.pair_id === pairId)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function run() {
    if (!emulator) return
    setBusy(true); setError('')
    try {
      const plans = (['control', 'fault'] as const).map(variant => ({ condition_id: 'baseline', switches: {}, qa_pair_id: pairId, variant, fault_seed: variant === 'fault', repeat: 1 }))
      onStarted(await post<BatchState>('/api/research/batches', { experiment_name: `eval-v0.1/${pairId}`, device_serial: emulator, fixture_kind: 'qa', plans }))
      onClose()
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  return <Dialog open onOpenChange={v => { if (!v) onClose() }}>
    <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-3xl">
      <DialogHeader>
        <DialogTitle className="font-mono text-base">{pairId}</DialogTitle>
        <DialogDescription>{row ? `${row.app} · ${row.bucket} · ${row.mechanism} · ${row.verifier_id}` : 'Loading…'}</DialogDescription>
      </DialogHeader>
      {meta && <div className="flex flex-col gap-1.5">
        <p className="text-xs font-medium text-muted-foreground">Instruction (the only text the agent sees; identical for both variants)</p>
        <p className="rounded-md border bg-muted/40 p-3 text-sm whitespace-pre-wrap break-words">{meta.instruction}</p>
      </div>}
      {row && <div className="flex flex-wrap gap-2 text-xs">
        <Badge variant="outline" className="gap-1 rounded-md">{yes(row.control_true)} control verified true</Badge>
        <Badge variant="outline" className="gap-1 rounded-md">{yes(row.fault_false)} fault verified false</Badge>
        <Badge variant="outline" className="gap-1 rounded-md">{yes(row.artifact_hashes_match)} artifact hashes</Badge>
        <Badge variant="outline" className="rounded-md">read tier {meta?.planned_read_tier || '?'}</Badge>
      </div>}
      {result.data?.detail && <div className="flex flex-col gap-2">
        <Disclosure title="Verifier contract" defaultOpen><JsonBlock value={result.data.detail.contract} /></Disclosure>
        <Disclosure title="Reference control artifact (authored)"><JsonBlock value={result.data.detail.reference_control} /></Disclosure>
        <Disclosure title="Reference fault artifact (authored)"><JsonBlock value={result.data.detail.reference_fault} /></Disclosure>
      </div>}
      <div className="flex flex-wrap items-center justify-between gap-2 border-t pt-3">
        <p className="text-xs text-muted-foreground">{row?.live ? (emulator ? `Runs control then fault on ${emulator}.` : 'Connect an AndroidWorld emulator to run.') : meta?.live_reason}</p>
        <Button onClick={run} disabled={!row?.live || !emulator || busy}>{busy ? <Loader2 className="animate-spin" /> : <Play />}Run pair on device</Button>
      </div>
      {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
    </DialogContent>
  </Dialog>
}
