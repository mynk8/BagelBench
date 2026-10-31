import { useEffect, useState } from 'react'
import { BarChart3, Database, FlaskConical, List, Moon, MonitorSmartphone, Plus, Sun } from 'lucide-react'
import { Separator } from '@/components/ui/separator'
import { Breadcrumb, BreadcrumbItem, BreadcrumbList, BreadcrumbPage } from '@/components/ui/breadcrumb'
import {
  Sidebar, SidebarContent, SidebarFooter, SidebarGroup, SidebarGroupContent, SidebarGroupLabel, SidebarHeader, SidebarInset,
  SidebarMenu, SidebarMenuButton, SidebarMenuItem, SidebarProvider, SidebarRail, SidebarTrigger,
} from '@/components/ui/sidebar'
import { useResource } from '@/hooks/use-resource'
import { routeHref, useRoute, useTheme } from '@/hooks/use-route'
import { RunComposer } from '@/components/research/run-composer'
import { BatchCard, type TrackedBatch } from '@/components/research/batch-card'
import { RunDetail } from '@/components/research/run-detail'
import { RunsPage } from '@/components/research/runs-page'
import { Environment } from '@/components/research/environment'
import { ResultsPage } from '@/components/research/results-page'
import { EvalPage } from '@/components/research/eval-page'
import type { Session } from '@/lib/types'



export function App() {
  const [route, navigate] = useRoute()
  const [theme, setTheme] = useTheme()
  const [compose, setCompose] = useState(false)
  const [batch, setBatch] = useState<TrackedBatch | null>(null)
  const runs = useResource<Session[]>('/api/sessions', 4000)
  const items = runs.data || []

  useEffect(() => {
    const show = () => navigate({ page: 'environment' })
    window.addEventListener('artemis:environment', show)
    return () => window.removeEventListener('artemis:environment', show)
  }, [navigate])

  return <SidebarProvider className="h-svh overflow-hidden">
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" asChild>
              <a href={routeHref({ page: 'runs' })}>
                <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground"><FlaskConical className="size-4" /></div>
                <div className="grid flex-1 text-left leading-tight">
                  <span className="truncate text-sm font-semibold">Artemis</span>
                  <span className="truncate text-xs text-muted-foreground">Interpretability research</span>
                </div>
              </a>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton tooltip="New run" onClick={() => setCompose(true)} className="bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground active:bg-primary/90 active:text-primary-foreground">
                  <Plus /><span>New run</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
        <SidebarGroup>
          <SidebarGroupLabel>Workspace</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton asChild tooltip="Runs" isActive={route.page === 'runs' || route.page === 'run'}>
                  <a href={routeHref({ page: 'runs' })}><List /><span>Runs</span></a>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton asChild tooltip="Eval set" isActive={route.page === 'eval'}>
                  <a href={routeHref({ page: 'eval' })}><Database /><span>Eval set</span></a>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton asChild tooltip="Results" isActive={route.page === 'results'}>
                  <a href={routeHref({ page: 'results' })}><BarChart3 /><span>Results</span></a>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton asChild tooltip="Environment" isActive={route.page === 'environment'}>
                  <a href={routeHref({ page: 'environment' })}><MonitorSmartphone /><span>Environment</span></a>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton tooltip="Toggle theme" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>
              {theme === 'dark' ? <Sun /> : <Moon />}<span>{theme === 'dark' ? 'Light mode' : 'Dark mode'}</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>

    <SidebarInset className="min-h-0 min-w-0 overflow-hidden">
      {route.page !== 'run' && <header className="flex h-12 shrink-0 items-center gap-2 border-b px-3">
        <SidebarTrigger />
        <Separator orientation="vertical" className="mr-1 data-[orientation=vertical]:h-4" />
        <Breadcrumb className="min-w-0">
          <BreadcrumbList className="flex-nowrap">
            <BreadcrumbItem><BreadcrumbPage>{route.page === 'environment' ? 'Environment' : route.page === 'results' ? 'Results' : route.page === 'eval' ? 'Eval set' : 'Runs'}</BreadcrumbPage></BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
      </header>}
      <div className="min-h-0 flex-1 overflow-hidden">
        {route.page === 'environment' ? <Environment />
          : route.page === 'results' ? <ResultsPage />
          : route.page === 'eval' ? <EvalPage onStarted={started => { setBatch({ ...started, follow: true }); runs.refresh() }} />
          : route.page === 'run' ? <RunDetail key={route.id} id={route.id} session={items.find(x => x.session_id === route.id)} />
          : <RunsPage runs={runs} onOpen={id => navigate({ page: 'run', id })} onCompose={() => setCompose(true)} />}
      </div>
    </SidebarInset>

    <BatchCard batch={batch} onChange={setBatch} onOpenRun={id => navigate({ page: 'run', id })} />

    <RunComposer open={compose} onOpenChange={setCompose} onStarted={started => { setBatch({ ...started, follow: true }); runs.refresh() }} />
  </SidebarProvider>
}
