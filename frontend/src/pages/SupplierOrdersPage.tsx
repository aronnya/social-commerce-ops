import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { generateSupplierOrderDraft, getSupplierOrders } from '../api/resources'
import type { SupplierOrder, SupplierOrderStatus } from '../api/types'
import { useReferenceData } from '../api/useReferenceData'
import { EmptyState, ErrorState, LoadingState } from '../ui/PageState'
import { StatusBadge, type StatusTone } from '../ui/StatusBadge'

const PAGE_SIZE = 10

const ORDER_STATUSES: SupplierOrderStatus[] = [
  'DRAFT',
  'PLACED',
  'CONFIRMED',
  'DISPATCHED',
  'ARRIVED',
  'RECONCILED',
]

const STATUS_LABEL: Record<SupplierOrderStatus, string> = {
  DRAFT: 'Draft',
  PLACED: 'Placed',
  CONFIRMED: 'Confirmed',
  DISPATCHED: 'Dispatched',
  ARRIVED: 'Arrived',
  RECONCILED: 'Reconciled',
}

const STATUS_TONE: Record<SupplierOrderStatus, StatusTone> = {
  DRAFT: 'warm',
  PLACED: 'info',
  CONFIRMED: 'lavender',
  DISPATCHED: 'mint',
  ARRIVED: 'warning',
  RECONCILED: 'success',
}

const SUMMARY_CARDS: {
  key: 'total' | 'DRAFT' | 'PLACED' | 'progress' | 'ARRIVED' | 'RECONCILED'
  label: string
  hint: string
  surface: string
  status: SupplierOrderStatus | 'ALL' | null
}[] = [
  {
    key: 'total',
    label: 'Total',
    hint: 'All loaded orders',
    surface: 'sky',
    status: 'ALL',
  },
  {
    key: 'DRAFT',
    label: 'Draft',
    hint: 'Ready to place',
    surface: 'cream',
    status: 'DRAFT',
  },
  {
    key: 'PLACED',
    label: 'Placed',
    hint: 'With the supplier',
    surface: 'lavender',
    status: 'PLACED',
  },
  {
    key: 'progress',
    label: 'In progress',
    hint: 'Confirmed or dispatched',
    surface: 'mist',
    status: null,
  },
  {
    key: 'ARRIVED',
    label: 'Arrived',
    hint: 'Awaiting reconciliation',
    surface: 'sage',
    status: 'ARRIVED',
  },
  {
    key: 'RECONCILED',
    label: 'Reconciled',
    hint: 'Quantities recorded',
    surface: 'blush',
    status: 'RECONCILED',
  },
]

type StatusFilter = SupplierOrderStatus | 'ALL'

function isSupplierOrderStatus(value: string | null): value is SupplierOrderStatus {
  return value !== null && (ORDER_STATUSES as string[]).includes(value)
}

function formatWhen(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return date.toLocaleString(undefined, { dateStyle: 'medium' })
}

function errorMessage(caught: unknown): string {
  if (caught instanceof ApiError) {
    return caught.message
  }
  return 'Something went wrong.'
}

function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => {
      reject(new ApiError('The request timed out.', 0))
    }, ms)
    promise.then(
      (value) => {
        window.clearTimeout(timer)
        resolve(value)
      },
      (caught: unknown) => {
        window.clearTimeout(timer)
        reject(caught)
      },
    )
  })
}

function orderedUnits(order: SupplierOrder): number {
  return order.lines.reduce((sum, line) => sum + line.quantity, 0)
}

function receivedUnits(order: SupplierOrder): number | null {
  if (order.lines.every((line) => line.received_quantity === null)) {
    return null
  }
  return order.lines.reduce((sum, line) => sum + (line.received_quantity ?? 0), 0)
}

export function SupplierOrdersPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const reference = useReferenceData()
  const [tick, setTick] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [orders, setOrders] = useState<SupplierOrder[]>([])
  const [query, setQuery] = useState('')
  const [supplierFilter, setSupplierFilter] = useState('ALL')
  const [page, setPage] = useState(1)
  const [pageFilterKey, setPageFilterKey] = useState('')
  const [generating, setGenerating] = useState(false)
  const [generateBusy, setGenerateBusy] = useState(false)
  const [generateError, setGenerateError] = useState<string | null>(null)
  const [generateNotice, setGenerateNotice] = useState<string | null>(null)
  const generateLock = useRef(false)

  const statusParam = searchParams.get('status')
  const statusFilter: StatusFilter = isSupplierOrderStatus(statusParam) ? statusParam : 'ALL'

  const retry = useCallback(() => {
    setLoading(true)
    setError(null)
    setTick((value) => value + 1)
  }, [])

  useEffect(() => {
    let cancelled = false
    withTimeout(getSupplierOrders(), 20000)
      .then((data) => {
        if (!cancelled) {
          setOrders(data)
          setLoading(false)
          setError(null)
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setOrders([])
          setLoading(false)
          setError(errorMessage(caught))
        }
      })
    return () => {
      cancelled = true
    }
  }, [tick])

  const counts = useMemo(() => {
    const next: Record<SupplierOrderStatus, number> = {
      DRAFT: 0,
      PLACED: 0,
      CONFIRMED: 0,
      DISPATCHED: 0,
      ARRIVED: 0,
      RECONCILED: 0,
    }
    for (const row of orders) {
      next[row.status] += 1
    }
    return next
  }, [orders])

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return orders.filter((row) => {
      if (statusFilter !== 'ALL' && row.status !== statusFilter) {
        return false
      }
      if (supplierFilter !== 'ALL' && row.supplier_id !== Number(supplierFilter)) {
        return false
      }
      if (!needle) {
        return true
      }
      const products = row.lines.map((line) => reference.productName(line.product_id)).join(' ')
      const haystack = [
        `#${row.id}`,
        String(row.id),
        reference.supplierName(row.supplier_id),
        STATUS_LABEL[row.status],
        row.status,
        products,
      ]
        .join(' ')
        .toLowerCase()
      return haystack.includes(needle)
    })
  }, [orders, query, reference, statusFilter, supplierFilter])

  const filterKey = `${statusFilter}|${supplierFilter}|${query}`
  const currentPage = pageFilterKey === filterKey ? page : 1
  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const safePage = Math.min(currentPage, pageCount)
  const pageRows = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE)
  const rangeStart = filtered.length === 0 ? 0 : (safePage - 1) * PAGE_SIZE + 1
  const rangeEnd = Math.min(safePage * PAGE_SIZE, filtered.length)

  function goToPage(next: number) {
    setPageFilterKey(filterKey)
    setPage(next)
  }

  function setStatusFilter(next: StatusFilter) {
    const params = new URLSearchParams(searchParams)
    if (next === 'ALL') {
      params.delete('status')
    } else {
      params.set('status', next)
    }
    setSearchParams(params, { replace: true })
  }

  function cardCount(key: (typeof SUMMARY_CARDS)[number]['key']): number {
    if (key === 'total') {
      return orders.length
    }
    if (key === 'progress') {
      return counts.CONFIRMED + counts.DISPATCHED
    }
    return counts[key]
  }

  return (
    <div className="preorders supplier-orders">
      <header className="list-header">
        <div className="page-header">
          <h1>Supplier Orders</h1>
          <p>Consolidate confirmed demand and coordinate supplier purchases.</p>
        </div>
        <button
          type="button"
          className="action-btn action-btn--primary"
          disabled={generateBusy}
          onClick={() => {
            setGenerateError(null)
            setGenerating((open) => !open)
          }}
        >
          Generate supplier orders
        </button>
      </header>

      {generating ? (
        <GenerateDraftForm
          busy={generateBusy}
          error={generateError}
          onCancel={() => {
            setGenerating(false)
            setGenerateError(null)
          }}
          onSubmit={async (supplierId) => {
            if (generateLock.current) {
              return
            }
            generateLock.current = true
            setGenerateBusy(true)
            setGenerateError(null)
            setGenerateNotice(null)
            try {
              const created = await withTimeout(
                generateSupplierOrderDraft({ supplier_id: supplierId }),
                20000,
              )
              setGenerateNotice(`Draft supplier order #${created.id} was created.`)
              setGenerating(false)
              setTick((value) => value + 1)
            } catch (caught: unknown) {
              setGenerateError(
                caught instanceof ApiError &&
                  (caught.status === 409 || caught.status === 0 || caught.status === 404)
                  ? caught.message
                  : caught instanceof ApiError && caught.status === 422
                    ? 'The request was not valid.'
                    : 'Draft supplier orders could not be generated.',
              )
            } finally {
              generateLock.current = false
              setGenerateBusy(false)
            }
          }}
        />
      ) : null}

      {generateNotice ? <p className="ops-notice">{generateNotice}</p> : null}

      <section className="preorder-cards" aria-label="Supplier order summary">
        {SUMMARY_CARDS.map((card) => {
          const count = cardCount(card.key)
          const selected = card.status !== null && statusFilter === card.status
          if (card.status === null) {
            return (
              <div key={card.key} className={`dash-card dash-card--${card.surface} dash-card--static`}>
                <span className="dash-card__count">{loading ? '…' : error ? '—' : count}</span>
                <span className="dash-card__label">{card.label}</span>
                <span className="dash-card__hint">{card.hint}</span>
              </div>
            )
          }
          return (
            <button
              key={card.key}
              type="button"
              className={`dash-card dash-card--${card.surface}${selected ? ' is-selected' : ''}`}
              onClick={() => setStatusFilter(card.status as StatusFilter)}
            >
              <span className="dash-card__count">{loading ? '…' : error ? '—' : count}</span>
              <span className="dash-card__label">{card.label}</span>
              <span className="dash-card__hint">{card.hint}</span>
            </button>
          )
        })}
      </section>

      <section className="panel preorder-panel">
        <div className="preorder-toolbar">
          <label className="preorder-search">
            <span className="visually-hidden">Search supplier orders</span>
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search supplier orders..."
            />
          </label>
          <label>
            <span className="visually-hidden">Status</span>
            <select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value as StatusFilter)}
            >
              <option value="ALL">All statuses</option>
              {ORDER_STATUSES.map((status) => (
                <option key={status} value={status}>
                  {STATUS_LABEL[status]}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span className="visually-hidden">Supplier</span>
            <select
              value={supplierFilter}
              onChange={(event) => setSupplierFilter(event.target.value)}
            >
              <option value="ALL">All suppliers</option>
              {reference.suppliers.map((supplier) => (
                <option key={supplier.id} value={String(supplier.id)}>
                  {supplier.name}
                </option>
              ))}
            </select>
          </label>
        </div>

        {loading ? (
          <LoadingState message="Loading supplier orders…" />
        ) : error ? (
          <ErrorState title="Supplier orders could not be loaded" message={error} onRetry={retry} />
        ) : orders.length === 0 ? (
          <EmptyState
            title="No supplier orders yet"
            message="Generate drafts from confirmed preorder demand."
          />
        ) : filtered.length === 0 ? (
          <EmptyState
            title="No matching supplier orders"
            message="No supplier orders match these filters."
          />
        ) : (
          <>
            <div className="table-wrap">
              <table className="data-table data-table--supplier">
                <thead>
                  <tr>
                    <th>Order</th>
                    <th>Supplier</th>
                    <th>Status</th>
                    <th>Lines</th>
                    <th>Ordered units</th>
                    <th>Received</th>
                    <th>Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {pageRows.map((row) => {
                    const received = receivedUnits(row)
                    return (
                      <tr key={row.id} className="data-table__clickable">
                        <td className="data-table__id">
                          <Link
                            to={`/supplier-orders/${row.id}`}
                            className="data-table__row-link"
                          >
                            #{row.id}
                          </Link>
                        </td>
                        <td>{reference.supplierName(row.supplier_id)}</td>
                        <td>
                          <StatusBadge
                            label={STATUS_LABEL[row.status]}
                            tone={STATUS_TONE[row.status]}
                          />
                        </td>
                        <td>{row.lines.length}</td>
                        <td>{orderedUnits(row)}</td>
                        <td>{received === null ? '—' : received}</td>
                        <td className="data-table__muted">{formatWhen(row.updated_at)}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            <footer className="table-footer">
              <p>
                Showing {rangeStart}–{rangeEnd} of {filtered.length}
              </p>
              <div className="table-pager">
                <button
                  type="button"
                  disabled={safePage <= 1}
                  onClick={() => goToPage(safePage - 1)}
                >
                  Previous
                </button>
                <span>
                  Page {safePage} of {pageCount}
                </span>
                <button
                  type="button"
                  disabled={safePage >= pageCount}
                  onClick={() => goToPage(safePage + 1)}
                >
                  Next
                </button>
              </div>
            </footer>
          </>
        )}
      </section>
    </div>
  )
}

function GenerateDraftForm({
  busy,
  error,
  onCancel,
  onSubmit,
}: {
  busy: boolean
  error: string | null
  onCancel: () => void
  onSubmit: (supplierId: number) => void
}) {
  const reference = useReferenceData()
  const [supplierId, setSupplierId] = useState('')

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (busy) {
      return
    }
    onSubmit(Number(supplierId))
  }

  return (
    <section className="panel">
      <h2>Generate supplier orders</h2>
      <p className="detail-muted">
        Create draft supplier orders from confirmed preorder demand.
      </p>
      <form className="ops-form" onSubmit={handleSubmit}>
        <label>
          Supplier
          <select
            required
            value={supplierId}
            disabled={busy}
            onChange={(event) => setSupplierId(event.target.value)}
          >
            <option value="">Select supplier</option>
            {reference.suppliers.map((supplier) => (
              <option key={supplier.id} value={String(supplier.id)}>
                {supplier.name}
              </option>
            ))}
          </select>
        </label>
        {error ? <p className="detail-action-error">{error}</p> : null}
        <div className="detail-actions__row ops-form__wide">
          <button type="submit" className="action-btn action-btn--primary" disabled={busy}>
            Generate draft
          </button>
          <button type="button" className="action-btn" disabled={busy} onClick={onCancel}>
            Cancel
          </button>
        </div>
      </form>
    </section>
  )
}
