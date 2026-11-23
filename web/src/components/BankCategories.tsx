// Bank categories: spend by category, the REVIEW list (low-confidence predictions) and
// a transaction list where the user can correct any category. Corrections are stored in
// the category_overrides table and always win over the model (src/sql/categorise.sql).

import { useState, useSyncExternalStore } from 'react'
import { useStoreQuery } from '../lib/appState'
import { categoriseState } from '../lib/categorise'
import { store } from '../lib/store'

export const BANK_CATEGORIES = [
  'tea_snacks',
  'meals',
  'food_delivery',
  'groceries_qcommerce',
  'transport',
  'shopping',
  'entertainment',
  'bills_recharge',
  'subscriptions',
  'p2p_transfer',
  'cash_atm',
  'other',
  'income',
] as const

const fmt = new Intl.NumberFormat('en-IN')
const inr = (n: number | null | undefined) =>
  n == null ? '—' : `₹${new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 }).format(n)}`
const label = (c: string | null) => (c ? c.replace(/_/g, ' ') : '—')

interface ReviewRow {
  event_key: string
  payee_key: string
  local_date: string
  actor: string | null
  title: string | null
  amount: number
  model_category: string | null
  confidence: number | null
}
interface TxnRow {
  event_key: string
  payee_key: string
  local_date: string
  actor: string | null
  title: string | null
  value: number
  category: string | null
  model_category: string | null
  confidence: number | null
  source: string | null
}

function CategorySelect({
  value,
  eventKey,
  payeeKey,
  applyToPayee,
  onError,
}: {
  value: string | null
  eventKey: string
  payeeKey: string
  applyToPayee: boolean
  onError: (e: string) => void
}) {
  const [busy, setBusy] = useState(false)
  async function change(next: string) {
    setBusy(true)
    try {
      const [scope, target] = applyToPayee ? (['payee', payeeKey] as const) : (['event', eventKey] as const)
      if (next === '__model') await store.clearOverride(scope, target)
      else await store.setOverride(scope, target, next)
    } catch (e) {
      onError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }
  return (
    <select
      value={value ?? ''}
      disabled={busy}
      onChange={(e) => void change(e.target.value)}
      aria-label="Category"
      className="max-w-40 border-2 border-orange-dark bg-bg px-1 py-0.5 font-mono text-xs text-text"
    >
      {value == null && <option value="">—</option>}
      {BANK_CATEGORIES.map((c) => (
        <option key={c} value={c}>
          {label(c)}
        </option>
      ))}
      <option value="__model">↺ undo correction</option>
    </select>
  )
}

function SourceTag({ source, confidence }: { source: string | null; confidence: number | null }) {
  const cls =
    source === 'review'
      ? 'border-orange-light text-orange-light'
      : source?.includes('override')
        ? 'border-xp text-xp'
        : 'border-orange-dark text-muted'
  const text =
    source === 'model' && confidence != null ? `model ${(confidence * 100).toFixed(0)}%` : (source ?? 'pending')
  return <span className={`border px-1 font-mono text-[10px] whitespace-nowrap ${cls}`}>{text}</span>
}

export function BankCategories() {
  const cat = useSyncExternalStore(categoriseState.subscribe, categoriseState.get)
  const info = useStoreQuery<{ version: string | null; test_macro_f1: string | null }>('categoriser_info').data?.[0]
  const byCat =
    useStoreQuery<{ category: string; spent: number; txns: number; share: number | null }>('bank_by_category').data ?? []
  const review = useStoreQuery<ReviewRow>('bank_review').data ?? []
  const reviewCount = useStoreQuery<{ n: number }>('bank_review_count').data?.[0]?.n ?? 0
  const [filter, setFilter] = useState<string | null>(null)
  const [page, setPage] = useState(0)
  const txns =
    useStoreQuery<TxnRow>('bank_txns', { txn_category: filter, txn_offset: String(page * 25) }).data ?? []
  const total = useStoreQuery<{ n: number }>('bank_txn_count', { txn_category: filter }).data?.[0]?.n ?? 0
  const [applyToPayee, setApplyToPayee] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const pages = Math.max(1, Math.ceil(total / 25))

  return (
    <div className="flex flex-col gap-6 border-t-2 border-orange-dark pt-6">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <span className="font-pixel text-[10px] text-orange">SPEND CATEGORIES</span>
        <span className="font-mono text-[11px] text-muted">
          {cat.running
            ? 'categorising in the Python worker…'
            : info?.version
              ? `model v${info.version} · test macro-F1 ${Number(info.test_macro_f1).toFixed(2)} (synthetic demo test set) · runs in this browser`
              : 'not categorised yet'}
          {cat.error && <span className="text-danger"> · {cat.error}</span>}
        </span>
      </div>

      {/* spend by category */}
      <div className="overflow-x-auto border-2 border-orange-dark bg-bg">
        <table className="w-full border-collapse font-mono text-xs">
          <thead>
            <tr>
              {['category', 'spent', 'share', 'txns'].map((h, i) => (
                <th key={h} className={`border-b-2 border-orange-dark px-2 py-1.5 font-normal text-muted uppercase ${i ? 'text-right' : 'text-left'}`}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {byCat.map((r) => (
              <tr key={r.category} className="odd:bg-panel/40">
                <td className="px-2 py-1 text-orange-light">
                  <button className="hover:underline" onClick={() => { setFilter(r.category); setPage(0) }}>
                    {label(r.category)}
                  </button>
                </td>
                <td className="px-2 py-1 text-right tabular-nums text-text">{inr(r.spent)}</td>
                <td className="px-2 py-1 text-right tabular-nums text-text">
                  <span className="mr-2 inline-block h-2 bg-orange align-middle" style={{ width: `${Math.round((r.share ?? 0) * 80)}px` }} />
                  {((r.share ?? 0) * 100).toFixed(1)}%
                </td>
                <td className="px-2 py-1 text-right tabular-nums text-muted">{fmt.format(r.txns)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <label className="flex items-center gap-2 font-mono text-xs text-text">
        <input type="checkbox" checked={applyToPayee} onChange={(e) => setApplyToPayee(e.target.checked)} className="accent-[#ff7a00]" />
        When I change a category, apply it to <strong className="text-orange-light">all payments to this payee</strong>
      </label>
      {error && <p className="font-mono text-xs text-danger">{error}</p>}

      {/* REVIEW */}
      <div className="flex flex-col gap-2">
        <span className="font-pixel text-[9px] text-orange-light">
          REVIEW · {fmt.format(reviewCount)} LOW-CONFIDENCE {reviewCount === 1 ? 'PAYMENT' : 'PAYMENTS'} (SHOWN AS OTHER)
        </span>
        {reviewCount === 0 ? (
          <p className="font-mono text-xs text-muted">Nothing to review.</p>
        ) : (
          <div className="max-h-72 overflow-auto border-2 border-orange-light/60 bg-bg">
            <table className="w-full border-collapse font-mono text-xs">
              <tbody>
                {review.map((r) => (
                  <tr key={r.event_key} className="odd:bg-panel/40">
                    <td className="px-2 py-1 whitespace-nowrap text-muted">{r.local_date}</td>
                    <td className="px-2 py-1 text-text" title={r.title ?? undefined}>
                      {r.actor ?? '—'}
                    </td>
                    <td className="px-2 py-1 text-right tabular-nums text-text">{inr(r.amount)}</td>
                    <td className="px-2 py-1 whitespace-nowrap text-muted">
                      guess: {label(r.model_category)} {r.confidence != null && `(${(r.confidence * 100).toFixed(0)}%)`}
                    </td>
                    <td className="px-2 py-1">
                      <CategorySelect value="other" eventKey={r.event_key} payeeKey={r.payee_key} applyToPayee={applyToPayee} onError={setError} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* all transactions */}
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-3">
          <span className="font-pixel text-[9px] text-orange-light">TRANSACTIONS</span>
          <select
            value={filter ?? ''}
            onChange={(e) => { setFilter(e.target.value || null); setPage(0) }}
            aria-label="Filter by category"
            className="border-2 border-orange-dark bg-bg px-1 py-0.5 font-mono text-xs text-text"
          >
            <option value="">all categories</option>
            {[...BANK_CATEGORIES].map((c) => (
              <option key={c} value={c}>
                {label(c)}
              </option>
            ))}
          </select>
          <span className="font-mono text-[11px] text-muted">
            {fmt.format(total)} rows · page {page + 1}/{pages}
          </span>
          <span className="ml-auto flex gap-2">
            <button className="border-2 border-orange-dark px-2 py-0.5 font-pixel text-[8px] text-orange disabled:text-muted" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
              ◀ PREV
            </button>
            <button className="border-2 border-orange-dark px-2 py-0.5 font-pixel text-[8px] text-orange disabled:text-muted" disabled={page + 1 >= pages} onClick={() => setPage((p) => p + 1)}>
              NEXT ▶
            </button>
          </span>
        </div>
        <div className="overflow-x-auto border-2 border-orange-dark bg-bg">
          <table className="w-full border-collapse font-mono text-xs">
            <tbody>
              {txns.map((r) => (
                <tr key={r.event_key} className="odd:bg-panel/40">
                  <td className="px-2 py-1 whitespace-nowrap text-muted">{r.local_date}</td>
                  <td className="px-2 py-1 text-text" title={r.title ?? undefined}>
                    {r.actor ?? '—'}
                    {r.title && <span className="text-muted"> · {r.title}</span>}
                  </td>
                  <td className={`px-2 py-1 text-right tabular-nums ${r.value < 0 ? 'text-text' : 'text-xp'}`}>
                    {r.value < 0 ? '−' : '+'}
                    {inr(Math.abs(r.value))}
                  </td>
                  <td className="px-2 py-1">
                    <CategorySelect value={r.category} eventKey={r.event_key} payeeKey={r.payee_key} applyToPayee={applyToPayee} onError={setError} />
                  </td>
                  <td className="px-2 py-1">
                    <SourceTag source={r.source} confidence={r.confidence} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
