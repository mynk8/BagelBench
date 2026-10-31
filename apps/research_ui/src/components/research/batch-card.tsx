import { useEffect, useRef, useState } from 'react'
import { Loader2, Square, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { api, post } from '@/lib/api'
import type { BatchState } from './run-composer'
import { StatusBadge } from './primitives'

/** `follow` opens the first run of a batch this tab just started. */
export type TrackedBatch = BatchState & { follow?: boolean }

/** Progress of the server-side batch. Reattaches to a running batch after a reload. */
export function BatchCard({ batch, onChange, onOpenRun }: { batch: TrackedBatch | null; onChange: (batch: TrackedBatch | null) => void; onOpenRun: (id: string) => void }) {
  const [stopping, setStopping] = useState(false)
  const [error, setError] = useState('')
  const followed = useRef<string | null>(null)
  const batchId = batch?.batch_id
  const running = batch?.status === 'running'

  useEffect(() => {
    if (batch) return
    api<{ batches: BatchState[] }>('/api/research/batches?limit=5')
      .then(result => { const live = result.batches.find(item => item.status === 'running'); if (live) onChange(live) })
      .catch(() => { /* Older servers have no batch endpoint. */ })
  }, [])

  useEffect(() => {
    if (!batchId || !running) return
    const timer = setInterval(() => {
      api<BatchState>(`/api/research/batches/${batchId}`)
        .then(next => onChange({ ...next, follow: batch?.follow }))
        .catch(e => setError((e as Error).message))
    }, 2000)
    return () => clearInterval(timer)
  }, [batchId, running])

  useEffect(() => {
    const first = batch?.session_ids[0]
    if (batch?.follow && first && followed.current !== batch.batch_id) { followed.current = batch.batch_id; onOpenRun(first) }
  }, [batch?.session_ids[0]])

  useEffect(() => {
    if (batch?.status !== 'completed') return
    const timer = setTimeout(() => onChange(null), 10000)
    return () => clearTimeout(timer)
  }, [batch?.status])

  if (!batch) return null
  async function stop() {
    setStopping(true); setError('')
    try { onChange({ ...(await post<BatchState>(`/api/research/batches/${batch!.batch_id}/stop`, {})), follow: batch!.follow }) }
    catch (e) { setError((e as Error).message) }
    finally { setStopping(false) }
  }
  const progress = running ? Math.max(batch.completed, batch.index - 1) + 0.5 : batch.completed

  return <div role="status" className="fixed right-4 bottom-4 z-50 grid w-[min(380px,calc(100vw-2rem))] gap-2 rounded-lg border bg-popover p-4 text-popover-foreground shadow-lg">
    <div className="flex items-center gap-2">
      {running && <Loader2 className="size-3.5 animate-spin text-muted-foreground" />}
      <p className="min-w-0 flex-1 truncate text-sm font-semibold">{batch.experiment_name} · {batch.completed}/{batch.total} recorded</p>
      <StatusBadge status={batch.status} />
      {!running && <Button variant="ghost" size="icon-xs" aria-label="Dismiss" onClick={() => onChange(null)}><X /></Button>}
    </div>
    <div className="h-1.5 overflow-hidden rounded-full bg-muted"><div className="h-full rounded-full bg-primary transition-all" style={{ width: `${Math.min(100, (progress / Math.max(1, batch.total)) * 100)}%` }} /></div>
    <p className="text-xs text-muted-foreground">{batch.error || batch.message}</p>
    {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
    <div className="flex items-center gap-2">
      {batch.current_session_id && <Button variant="link" size="sm" className="h-auto p-0" onClick={() => onOpenRun(batch.current_session_id!)}>View current run</Button>}
      {running && <Button variant="outline" size="xs" className="ml-auto" disabled={stopping} onClick={stop}><Square />{stopping ? 'Stopping…' : 'Stop batch'}</Button>}
      {!running && <Button variant="outline" size="xs" className="ml-auto" asChild><a href={`/api/research/batches/${batch.batch_id}/report`} target="_blank" rel="noreferrer">Report</a></Button>}
    </div>
  </div>
}
