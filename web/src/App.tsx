import { lazy, Suspense } from 'react'
import { AppHeader } from './components/AppHeader'
import { AppStateProvider, useApp } from './lib/appState'
import DataPage from './pages/Data'
import ExportGuidePage from './pages/ExportGuide'
import ImportPage from './pages/Import'
import LandingPage from './pages/Landing'
import SystemCheck from './pages/SystemCheck'

// The dashboard (and ECharts) is a separate chunk, loaded when first shown.
const DashboardPage = lazy(() => import('./pages/Dashboard'))

function Loading() {
  return <p className="mx-auto max-w-6xl animate-pixel-blink px-6 py-10 font-pixel text-[10px] text-orange-light">LOADING…</p>
}

function Dashboard() {
  return (
    <Suspense fallback={<Loading />}>
      <DashboardPage />
    </Suspense>
  )
}

function Page() {
  const { path, bounds, storeState } = useApp()
  if (path === '/import') return <ImportPage />
  if (path === '/data') return <DataPage />
  if (path === '/system') return <SystemCheck />
  if (path === '/guide') return <ExportGuidePage />
  if (path === '/welcome') return <LandingPage />
  if (path === '/dashboard' || path === '/insights') return <Dashboard />
  // home: the dashboard once this database has data, otherwise the landing screen
  if (storeState.status !== 'ready' || !bounds) return storeState.status === 'error' ? <SystemCheck /> : <Loading />
  return bounds.events > 0 ? <Dashboard /> : <LandingPage />
}

export default function App() {
  return (
    <AppStateProvider>
      <AppHeader />
      <Page />
    </AppStateProvider>
  )
}
