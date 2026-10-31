import { useState, type ReactNode } from 'react'
import { Check, ChevronRight, Copy, Eye, FlaskConical, MessageSquareQuote, ShieldCheck, HelpCircle } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

type Tone = 'success' | 'danger' | 'warning' | 'info' | 'neutral'

const TONES: Record<Tone, string> = {
  success: 'border-success/30 bg-success/10 text-success',
  danger: 'border-destructive/30 bg-destructive/10 text-destructive',
  warning: 'border-warning/40 bg-warning/10 text-warning',
  info: 'border-info/30 bg-info/10 text-info',
  neutral: 'border-border bg-muted text-muted-foreground',
}

export function statusTone(status?: string): Tone {
  const value = (status || '').toLowerCase()
  if (['completed', 'passed', 'pass', 'met', 'satisfied', 'success', 'succeeded', 'correct'].includes(value)) return 'success'
  if (['failed', 'fail', 'error', 'unmet', 'not_met', 'faulty', 'tampered'].includes(value)) return 'danger'
  if (['running', 'pending', 'queued', 'paused', 'starting'].includes(value)) return 'info'
  if (['inconclusive', 'warn', 'warning', 'stopped', 'cancelled', 'partial', 'interrupted'].includes(value)) return 'warning'
  return 'neutral'
}

export function StatusBadge({ status, className }: { status?: string; className?: string }) {
  const tone = statusTone(status)
  const live = ['running', 'pending', 'queued'].includes((status || '').toLowerCase())
  return <Badge variant="outline" className={cn('gap-1.5 rounded-md font-medium capitalize', TONES[tone], className)}>
    <span className={cn('size-1.5 rounded-full bg-current', live && 'animate-pulse')} />
    {(status || 'unknown').replaceAll('_', ' ')}
  </Badge>
}

/** Provenance of a piece of evidence. Keeps observations visibly separate from model claims. */
export type Provenance = 'observed' | 'self-report' | 'model-assisted' | 'oracle' | 'unknown'

const PROVENANCE: Record<Provenance, { label: string; hint: string; icon: typeof Eye; className: string }> = {
  observed: { label: 'Observed', hint: 'Recorded by the harness: screenshots, action results, device reads.', icon: Eye, className: 'text-success border-success/30' },
  'self-report': { label: 'Self-report', hint: 'Written by the actor model. Not independent evidence of why it acted.', icon: MessageSquareQuote, className: 'text-warning border-warning/40' },
  'model-assisted': { label: 'Model-assisted', hint: 'Produced by a separate model reading recorded evidence. An interpretation, not ground truth.', icon: FlaskConical, className: 'text-info border-info/30' },
  oracle: { label: 'Oracle', hint: 'Independent state read, kept outside the actor and Checker inputs.', icon: ShieldCheck, className: 'text-foreground border-foreground/30' },
  unknown: { label: 'Unknown', hint: 'Alternatives, evidence, or an independent oracle are missing.', icon: HelpCircle, className: 'text-muted-foreground' },
}

export function ProvenanceTag({ kind, className }: { kind: Provenance; className?: string }) {
  const item = PROVENANCE[kind]
  const Icon = item.icon
  return <Tooltip>
    <TooltipTrigger asChild>
      <Badge variant="outline" className={cn('h-5 cursor-help gap-1 rounded-md px-1.5 text-[10px] font-medium uppercase tracking-wide', item.className, className)}><Icon />{item.label}</Badge>
    </TooltipTrigger>
    <TooltipContent className="max-w-64">{item.hint}</TooltipContent>
  </Tooltip>
}

export function SectionHeader({ title, description, children, className }: { title: ReactNode; description?: ReactNode; children?: ReactNode; className?: string }) {
  return <div className={cn('flex items-start justify-between gap-3', className)}>
    <div className="min-w-0">
      <h3 className="text-sm font-semibold leading-none">{title}</h3>
      {description && <p className="mt-1.5 text-xs text-muted-foreground">{description}</p>}
    </div>
    {children && <div className="flex shrink-0 items-center gap-1.5">{children}</div>}
  </div>
}

export function EmptyState({ icon: Icon, title, children, className }: { icon?: typeof Eye; title: string; children?: ReactNode; className?: string }) {
  return <div className={cn('flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed px-6 py-10 text-center', className)}>
    {Icon && <div className="flex size-9 items-center justify-center rounded-full bg-muted text-muted-foreground"><Icon className="size-4" /></div>}
    <p className="text-sm font-medium">{title}</p>
    {children && <div className="max-w-sm text-xs text-muted-foreground">{children}</div>}
  </div>
}

export function JsonBlock({ value, className }: { value: unknown; className?: string }) {
  const [copied, setCopied] = useState(false)
  const text = typeof value === 'string' ? value : JSON.stringify(value, null, 2)
  return <div className={cn('group relative rounded-md border bg-muted/50', className)}>
    <Button type="button" variant="ghost" size="icon-xs" className="absolute top-1.5 right-1.5 opacity-0 group-hover:opacity-100 focus-visible:opacity-100" aria-label="Copy"
      onClick={() => { void navigator.clipboard?.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1200) }}>
      {copied ? <Check /> : <Copy />}
    </Button>
    <pre className="max-h-96 overflow-auto p-3 font-mono text-[11px] leading-relaxed whitespace-pre-wrap break-words">{text}</pre>
  </div>
}

/** A labelled disclosure row. Used for everything that should be expandable. */
export function Disclosure({ title, meta, defaultOpen = false, children, className }: { title: ReactNode; meta?: ReactNode; defaultOpen?: boolean; children: ReactNode; className?: string }) {
  const [open, setOpen] = useState(defaultOpen)
  return <Collapsible open={open} onOpenChange={setOpen} className={cn('rounded-lg border', className)}>
    <CollapsibleTrigger className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-[13px] font-medium hover:bg-muted/50">
      <ChevronRight className={cn('size-4 shrink-0 text-muted-foreground transition-transform', open && 'rotate-90')} />
      <span className="min-w-0 flex-1 truncate">{title}</span>
      {meta && <span className="flex shrink-0 items-center gap-1.5 text-xs font-normal text-muted-foreground">{meta}</span>}
    </CollapsibleTrigger>
    <CollapsibleContent className="border-t p-3">{children}</CollapsibleContent>
  </Collapsible>
}

export function pad(value: number) { return String(value).padStart(2, '0') }

export function formatTime(seconds?: number) {
  if (!Number.isFinite(seconds)) return '—'
  return new Date(seconds! * 1000).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export function relativeTime(seconds?: number) {
  if (!Number.isFinite(seconds)) return ''
  const diff = Date.now() / 1000 - seconds!
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

/**
 * Readable parts of a natural-language test. The first sentence is the title; a trailing JSON
 * block (fixture prompts append expected fields) becomes short "key: value" facts that tell
 * otherwise identical tests apart.
 */
export function taskSummary(goal?: string) {
  const text = (goal || 'Untitled task').trim()
  const json = text.indexOf('{')
  const prose = (json > 0 ? text.slice(0, json) : text).replace(/\s+/g, ' ').trim()
  const title = prose.match(/^.{20,}?[.!?](\s|$)/)?.[0]?.trim() || prose
  let facts: string[] = []
  if (json > 0) {
    try {
      const data = JSON.parse(text.slice(json))
      const hints = data.display_hints || {}
      const fields = data.expected_fields || data
      facts = Object.entries(fields).filter(([, v]) => v !== null && typeof v !== 'object').map(([k, v]) => `${k.replaceAll('_', ' ')}: ${hints[k] ?? v}`)
    } catch { /* not JSON */ }
  }
  return { title, facts, rest: prose.slice(title.length).trim() }
}

/** Checker records written when the check itself crashed, rather than a judgment of the agent. */
export function isHarnessError(evidence?: string) {
  return /^(check raised an exception|final check error)/i.test((evidence || '').trim())
}
