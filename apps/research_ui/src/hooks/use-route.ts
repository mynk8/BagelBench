import { useCallback, useEffect, useState } from 'react'

export type Route = { page: 'runs' } | { page: 'run'; id: string } | { page: 'environment' } | { page: 'results' } | { page: 'eval' }

function parse(hash: string): Route {
  const parts = hash.replace(/^#\/?/, '').split('/').filter(Boolean)
  if (parts[0] === 'runs' && parts[1]) return { page: 'run', id: decodeURIComponent(parts[1]) }
  if (parts[0] === 'environment') return { page: 'environment' }
  if (parts[0] === 'results') return { page: 'results' }
  if (parts[0] === 'eval') return { page: 'eval' }
  return { page: 'runs' }
}

export function routeHref(route: Route) {
  if (route.page === 'run') return `#/runs/${encodeURIComponent(route.id)}`
  if (route.page === 'results') return '#/results'
  if (route.page === 'eval') return '#/eval'
  return route.page === 'environment' ? '#/environment' : '#/runs'
}

/** Hash routing keeps back/forward and reload working without a router dependency. */
export function useRoute() {
  const [route, setRoute] = useState<Route>(() => parse(window.location.hash))
  useEffect(() => {
    const sync = () => setRoute(parse(window.location.hash))
    window.addEventListener('hashchange', sync)
    return () => window.removeEventListener('hashchange', sync)
  }, [])
  const navigate = useCallback((next: Route) => { window.location.hash = routeHref(next) }, [])
  return [route, navigate] as const
}

export function useMediaQuery(query: string) {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches)
  useEffect(() => {
    const list = window.matchMedia(query)
    const sync = () => setMatches(list.matches)
    sync(); list.addEventListener('change', sync)
    return () => list.removeEventListener('change', sync)
  }, [query])
  return matches
}

export function useTheme() {
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    try { const saved = localStorage.getItem('artemis-theme'); if (saved === 'light' || saved === 'dark') return saved } catch { /* storage unavailable */ }
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  })
  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark')
    try { localStorage.setItem('artemis-theme', theme) } catch { /* storage unavailable */ }
  }, [theme])
  return [theme, setTheme] as const
}
