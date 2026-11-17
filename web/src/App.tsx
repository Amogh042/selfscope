import { AppHeader } from './components/AppHeader'
import { AppStateProvider, useApp } from './lib/appState'
import DataPage from './pages/Data'
import ImportPage from './pages/Import'
import SystemCheck from './pages/SystemCheck'

function Page() {
  const { path } = useApp()
  if (path === '/import') return <ImportPage />
  if (path === '/data') return <DataPage />
  return <SystemCheck />
}

export default function App() {
  return (
    <AppStateProvider>
      <AppHeader />
      <Page />
    </AppStateProvider>
  )
}
