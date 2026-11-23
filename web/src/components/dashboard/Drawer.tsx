// Side panel (right edge; full width on phones) for the day drill-down and insight details.
import { useEffect, type ReactNode } from 'react'

export function Drawer({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    const on = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', on)
    return () => window.removeEventListener('keydown', on)
  }, [onClose])
  return (
    <div className="fixed inset-0 z-40 flex justify-end" role="dialog" aria-modal="true" aria-label={title}>
      <button className="absolute inset-0 bg-bg/70" aria-label="Close panel" onClick={onClose} />
      <aside className="relative flex h-full w-full max-w-[560px] flex-col border-l-2 border-orange bg-panel shadow-[-6px_0_0_0_var(--color-orange-dark)]">
        <header className="flex items-center justify-between gap-3 border-b-2 border-orange bg-bg px-4 py-3">
          <h2 className="text-[11px] leading-relaxed text-orange">{title}</h2>
          <button className="pixel-btn !px-2 !py-1" onClick={onClose} aria-label="Close">
            ✖
          </button>
        </header>
        <div className="flex flex-1 flex-col gap-5 overflow-y-auto p-4">{children}</div>
      </aside>
    </div>
  )
}
