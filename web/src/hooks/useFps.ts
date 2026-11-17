import { useEffect, useState } from 'react'

/**
 * Main-thread frame rate, sampled once per second via requestAnimationFrame.
 * If heavy work ever lands on the UI thread this number collapses — the
 * SYSTEM CHECK page shows it to prove Pyodide loading happens off-thread.
 */
export function useFps(): number {
  const [fps, setFps] = useState(0)
  useEffect(() => {
    let frames = 0
    let last = performance.now()
    let raf = 0
    const tick = (now: number) => {
      frames++
      if (now - last >= 1000) {
        setFps(Math.round((frames * 1000) / (now - last)))
        frames = 0
        last = now
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [])
  return fps
}
