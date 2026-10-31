import { useState } from 'react'
import { CheckCircle2, CircleAlert, CircleDashed, MonitorSmartphone, RefreshCw, Smartphone } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import { useResource } from '@/hooks/use-resource'
import { post } from '@/lib/api'
import type { AndroidDevice, DeviceResponse, Probe } from '@/lib/types'
import { cn } from '@/lib/utils'
import { Disclosure, EmptyState, JsonBlock, StatusBadge } from './primitives'

export function Environment() {
  const readiness = useResource<{ overall_ready: boolean; probes: Probe[] }>('/api/system/readiness'), devices = useResource<DeviceResponse | AndroidDevice[]>('/api/devices', 10000)
  const deviceRows = Array.isArray(devices.data) ? devices.data : devices.data?.devices || []
  const [busy, setBusy] = useState(false), [error, setError] = useState('')
  async function select(serial: string) {
    setBusy(true); setError('')
    try { await post('/api/system/devices/select', { serial }); readiness.refresh(); devices.refresh() } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  const probes = readiness.data?.probes || []

  return <ScrollArea className="h-full">
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 p-4 md:p-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Environment</h1>
          <p className="mt-1 text-sm text-muted-foreground">Connections used by the execution harness.</p>
        </div>
        <div className="flex items-center gap-2">
          {readiness.data && <StatusBadge status={readiness.data.overall_ready ? 'passed' : 'failed'} className="normal-case" />}
          <Button size="sm" variant="outline" onClick={() => { readiness.refresh(); devices.refresh() }}><RefreshCw className={readiness.loading ? 'animate-spin' : ''} />Refresh</Button>
        </div>
      </div>
      {(readiness.error || devices.error || error) && <p role="alert" className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">{readiness.error || devices.error || error}</p>}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><MonitorSmartphone className="size-4" />Android devices</CardTitle>
          <CardDescription>Select the device the harness should drive.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          {deviceRows.map((device, i) => {
            const serial = device.serial || device.device_id || device.id
            return <div key={serial || i} className="flex items-center gap-3 rounded-lg border p-3">
              <div className="flex size-9 items-center justify-center rounded-md bg-muted"><Smartphone className="size-4 text-muted-foreground" /></div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{device.model || serial}</p>
                <p className="truncate font-mono text-xs text-muted-foreground">{serial} · {device.status || device.state || 'unknown'}</p>
              </div>
              <Button variant="outline" size="sm" disabled={busy || !serial || device.state === 'unauthorized'} onClick={() => select(serial!)}>Select</Button>
            </div>
          })}
          {!deviceRows.length && !devices.loading && <EmptyState icon={Smartphone} title="No devices returned">Start an emulator or connect a phone with USB debugging enabled.</EmptyState>}
          <Disclosure title="Local ADB setup"><JsonBlock value={'env -u ADB_SERVER_SOCKET adb start-server\nadb devices -l'} /></Disclosure>
        </CardContent>
      </Card>

      <div>
        <h2 className="mb-3 text-sm font-semibold">Readiness probes</h2>
        <div className="grid gap-3 md:grid-cols-2">
          {readiness.loading && !readiness.data && Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-24" />)}
          {probes.map(probe => {
            const Icon = probe.status === 'pass' ? CheckCircle2 : probe.status === 'fail' ? CircleAlert : CircleDashed
            return <Card key={probe.id} className="gap-2 py-4">
              <CardHeader className="px-4">
                <CardTitle className="flex items-center gap-2 text-sm">
                  <Icon className={cn('size-4', probe.status === 'pass' ? 'text-success' : probe.status === 'fail' ? 'text-destructive' : 'text-muted-foreground')} />
                  {probe.title}
                  <StatusBadge status={probe.status === 'fail' ? 'failed' : probe.status === 'pass' ? 'passed' : probe.status} className="ml-auto" />
                </CardTitle>
                <CardDescription>{probe.summary}</CardDescription>
              </CardHeader>
              {probe.description && <CardContent className="px-4 text-xs text-muted-foreground">{probe.description}</CardContent>}
            </Card>
          })}
        </div>
      </div>
    </div>
  </ScrollArea>
}
