import { useMemo, useState } from 'react'
import { ChevronRight, FlaskConical, Plus, Search } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import type { Session } from '@/lib/types'
import { EmptyState, StatusBadge, formatTime, relativeTime, statusTone, taskSummary } from './primitives'

type Filter = 'all' | 'active' | 'success' | 'danger' | 'other'


export function RunsPage({ runs, onOpen, onCompose }: {
  runs: { data?: Session[]; loading: boolean; error?: string }
  onOpen: (id: string) => void
  onCompose: () => void
}) {
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<Filter>('all')
  const items = useMemo(() => [...(runs.data || [])].sort((a, b) => (b.start_time || 0) - (a.start_time || 0)), [runs.data])
  const bucket = (run: Session): Filter => {
    const tone = statusTone(run.status)
    return tone === 'info' ? 'active' : tone === 'success' || tone === 'danger' ? tone : 'other'
  }
  const counts = useMemo(() => items.reduce<Record<Filter, number>>((acc, run) => { acc[bucket(run)]++; acc.all++; return acc }, { all: 0, active: 0, success: 0, danger: 0, other: 0 }), [items])
  const filtered = items.filter(run => (filter === 'all' || bucket(run) === filter) && `${run.initial_goal} ${run.session_id} ${run.model_info?.id}`.toLowerCase().includes(query.toLowerCase()))

  return <ScrollArea className="h-full">
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 p-4 md:p-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Runs</h1>
        </div>
        <Button onClick={onCompose}><Plus />New run</Button>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <Tabs value={filter} onValueChange={value => setFilter(value as Filter)}>
          <TabsList>
            <TabsTrigger value="all">All <Count n={counts.all} /></TabsTrigger>
            <TabsTrigger value="active">Active <Count n={counts.active} /></TabsTrigger>
            <TabsTrigger value="success">Completed <Count n={counts.success} /></TabsTrigger>
            <TabsTrigger value="danger">Failed <Count n={counts.danger} /></TabsTrigger>
            {!!counts.other && <TabsTrigger value="other">Other <Count n={counts.other} /></TabsTrigger>}
          </TabsList>
        </Tabs>
        <div className="relative w-full sm:w-72">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search tasks, models, run IDs…" className="pl-8" />
        </div>
      </div>

      {runs.error && <p role="alert" className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">{runs.error}</p>}

      <div className="overflow-hidden rounded-lg border">
        <Table>
          <TableHeader className="bg-muted/50">
            <TableRow>
              <TableHead className="w-28">Status</TableHead>
              <TableHead>Test</TableHead>
              <TableHead className="hidden w-56 lg:table-cell">Model</TableHead>
              <TableHead className="hidden w-32 md:table-cell">Device</TableHead>
              <TableHead className="w-32 text-right">Started</TableHead>
              <TableHead className="w-8" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {runs.loading && !runs.data && Array.from({ length: 4 }, (_, i) => <TableRow key={i}>
              <TableCell><Skeleton className="h-5 w-20" /></TableCell>
              <TableCell><Skeleton className="h-4 w-3/4" /><Skeleton className="mt-2 h-3 w-1/2" /></TableCell>
              <TableCell className="hidden lg:table-cell"><Skeleton className="h-4 w-32" /></TableCell>
              <TableCell className="hidden md:table-cell"><Skeleton className="h-4 w-20" /></TableCell>
              <TableCell><Skeleton className="ml-auto h-4 w-16" /></TableCell>
              <TableCell />
            </TableRow>)}
            {filtered.map(run => {
              const task = taskSummary(run.initial_goal)
              return <TableRow key={run.session_id} className="cursor-pointer" tabIndex={0} onClick={() => onOpen(run.session_id)} onKeyDown={e => { if (e.key === 'Enter') onOpen(run.session_id) }}>
                <TableCell className="align-top"><StatusBadge status={run.status} /></TableCell>
                <TableCell className="max-w-0 align-top whitespace-normal">
                  <p className="line-clamp-1 font-medium">{task.title}</p>
                  {task.facts.length ? <p className="mt-1 flex flex-wrap gap-1">{task.facts.slice(0, 4).map(fact => <span key={fact} className="max-w-56 truncate rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">{fact}</span>)}</p>
                    : task.rest && <p className="mt-0.5 line-clamp-1 text-xs text-muted-foreground">{task.rest}</p>}
                  <p className="mt-1 truncate font-mono text-[11px] text-muted-foreground/70">{run.session_id}</p>
                </TableCell>
                <TableCell className="hidden align-top text-xs text-muted-foreground lg:table-cell"><span className="line-clamp-2 break-all">{run.model_info?.id || '—'}</span></TableCell>
                <TableCell className="hidden align-top font-mono text-xs text-muted-foreground md:table-cell">{run.device_serial || '—'}</TableCell>
                <TableCell className="text-right align-top text-xs">
                  <p>{relativeTime(run.start_time)}</p>
                  <p className="text-muted-foreground">{formatTime(run.start_time)}</p>
                </TableCell>
                <TableCell className="align-top"><ChevronRight className="size-4 text-muted-foreground" /></TableCell>
              </TableRow>
            })}
          </TableBody>
        </Table>
        {!runs.loading && !filtered.length && <EmptyState icon={FlaskConical} title={items.length ? 'No runs match' : 'No experiments yet'} className="m-4">
          {items.length ? 'Try another filter or search term.' : <>Describe a test in plain language and Artemis runs it on a device. <Button variant="link" size="sm" className="h-auto p-0" onClick={onCompose}>Create one</Button></>}
        </EmptyState>}
      </div>
    </div>
  </ScrollArea>
}

function Count({ n }: { n: number }) {
  return <span className="ml-1 rounded bg-background/60 px-1 font-mono text-[10px] text-muted-foreground">{n}</span>
}
