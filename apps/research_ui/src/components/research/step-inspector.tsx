import { useState } from 'react'
import { ImageOff } from 'lucide-react'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { actionLabel, executionStatus, imageUrl, type resultScreen } from '@/lib/evidence'
import type { Step } from '@/lib/types'
import { Disclosure, JsonBlock, StatusBadge, pad } from './primitives'

/** One step: what the screen showed before and after, then the agent's own account and the raw record. */
export function StepInspector({ step, after }: { step: Step; after?: ReturnType<typeof resultScreen> }) {
  const [zoom, setZoom] = useState<string | null>(null)
  const recordedAfter = imageUrl(step.post_image_name || step.post_screenshot)
  const shots: { label: string; url: string | null }[] = [
    { label: 'Before', url: imageUrl(step.pre_image_name || step.pre_screenshot) },
    { label: recordedAfter || !after?.inferredFrom ? 'After' : 'After (next step’s screen)', url: recordedAfter || after?.image || null },
  ]
  const reasoning = step.operator_native_thinking || step.operator_raw_thinking

  return <div className="flex flex-col gap-4 p-4">
    <div className="flex items-start justify-between gap-3">
      <div className="min-w-0">
        <p className="font-mono text-[11px] text-muted-foreground">STEP {pad(step.step_number)}</p>
        <h3 className="mt-0.5 text-base font-semibold break-words">{actionLabel(step)}</h3>
      </div>
      <StatusBadge status={executionStatus(step)} />
    </div>

    <div className="grid grid-cols-2 gap-3">
      {shots.map(shot => <figure key={shot.label} className="flex min-w-0 flex-col gap-1.5">
        <figcaption className="text-xs text-muted-foreground">{shot.label}</figcaption>
        <div className="flex h-[min(56vh,560px)] items-center justify-center overflow-hidden rounded-lg border bg-muted/40">
          {shot.url
            ? <button type="button" className="h-full w-full p-1.5" onClick={() => setZoom(shot.url)} aria-label={`Enlarge ${shot.label}`}><img src={shot.url} alt={`${shot.label} step ${step.step_number}`} className="h-full w-full object-contain" /></button>
            : <span className="flex flex-col items-center gap-1 text-xs text-muted-foreground"><ImageOff className="size-4" />Not captured</span>}
        </div>
      </figure>)}
    </div>

    <Disclosure title="Agent’s account of this step" meta="self-report">
      <div className="flex flex-col gap-3 text-sm leading-relaxed whitespace-pre-wrap break-words text-muted-foreground">
        {step.summary && <p>{step.summary}</p>}
        <p>{reasoning || 'No reasoning recorded.'}</p>
      </div>
    </Disclosure>
    {step.last_execution_result && <Disclosure title="Execution result"><JsonBlock value={step.last_execution_result} /></Disclosure>}
    <Disclosure title="Raw step record"><JsonBlock value={step} /></Disclosure>

    <Dialog open={!!zoom} onOpenChange={open => { if (!open) setZoom(null) }}>
      <DialogContent className="sm:max-w-[min(90vw,900px)]">
        <DialogHeader><DialogTitle>Step {pad(step.step_number)} · {actionLabel(step)}</DialogTitle><DialogDescription>Recorded screenshot.</DialogDescription></DialogHeader>
        {zoom && <img src={zoom} alt="Enlarged screenshot" className="max-h-[78vh] w-full object-contain" />}
      </DialogContent>
    </Dialog>
  </div>
}
