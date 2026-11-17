import { useEffect, useState } from 'react'
import ImportPage from './pages/Import'
import SystemCheck from './pages/SystemCheck'

// Tiny hash router: "#/" = System Check, "#/import" = Import.
function useHash() {
  const [hash, setHash] = useState(() => window.location.hash)
  useEffect(() => {
    const on = () => {
      setHash(window.location.hash)
      window.scrollTo(0, 0)
    }
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  return hash
}

export default function App() {
  return useHash() === '#/import' ? <ImportPage /> : <SystemCheck />
}
