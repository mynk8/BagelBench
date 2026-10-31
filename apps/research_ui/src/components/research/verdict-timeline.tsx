import { useState } from 'react'
import { ArrowRight, ExternalLink, Gavel } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { verdictTransitions } from '@/lib/evidence'
import type { Verdict } from '@/lib/types'
import { Disclosure, EmptyState, JsonBlock, StatusBadge, isHarnessError } from './primitives'

export function VerdictTimeline({ records, onStep, latestOnly = false }: { records: Verdict[]; onStep: (id: string) => void; latestOnly?: boolean }) {
  if (!records.length) return <EmptyState icon={Gavel} title="No Checker verdicts yet">Verdicts appear as the Checker evaluates acceptance criteria.</EmptyState>
  const transitions = verdictTransitions(records).reverse()
  return <div className="flex flex-col gap-2">
    {(latestOnly ? transitions.slice(0, 1) : transitions).map(item => <VerdictCard key={`${item.record.attempt_id}-${item.index}`} {...item} onStep={onStep} />)}
  </div>
}

function VerdictCard({ record, from, changed, index, onStep }: ReturnType<typeof verdictTransitions>[number] & { onStep: (id: string) => void }) {
  const [expanded, setExpanded] = useState(false)
  const evidence = record.evidence || 'No evidence cited.'
  const long = evidence.length > 280
  const crashed = isHarnessError(record.evidence)
  return <article id={`verdict-${index}`} className="scroll-mt-4 rounded-lg border p-3">
    <div className="flex flex-wrap items-center gap-1.5">
      {changed && <><StatusBadge status={from} /><ArrowRight className="size-3 text-muted-foreground" /></>}
      <StatusBadge status={record.status} />
      {crashed && <Badge variant="outline" className="rounded-md border-destructive/40 text-[10px] text-destructive">Checker error · not a judgment</Badge>}
      <Badge variant="outline" className="rounded-md font-mono text-[10px] font-normal text-muted-foreground">{record.kind}</Badge>
      <span className="ml-auto font-mono text-[10px] text-muted-foreground">v{index + 1}</span>
    </div>
    <p className="mt-2 text-[13px] leading-snug font-medium break-words">{record.item_text}</p>
    <p className={`mt-1.5 text-xs leading-relaxed whitespace-pre-wrap break-words text-muted-foreground ${long && !expanded ? 'line-clamp-3' : ''}`}>{evidence}</p>
    {long && <Button variant="link" size="sm" className="h-auto p-0 text-xs" onClick={() => setExpanded(!expanded)}>{expanded ? 'Show less' : 'Show full evidence'}</Button>}
    <div className="mt-2 flex flex-wrap items-center gap-2">
      <span className="truncate font-mono text-[10px] text-muted-foreground">{record.checkpoint_id}</span>
      {record.anchor_step_id && <Button size="xs" variant="outline" onClick={() => onStep(record.anchor_step_id!)}><ExternalLink />Source step</Button>}
    </div>
    <Disclosure title="Ledger record" className="mt-2 border-dashed"><JsonBlock value={record} /></Disclosure>
  </article>
}
