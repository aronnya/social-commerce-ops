import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { getPreorders } from '../api/resources'
import type {
  Money,
  PaymentSummaryStatus,
  Preorder,
  PreorderStatus,
  Product,
} from '../api/types'
import { useReferenceData } from '../api/useReferenceData'
import { EmptyState, ErrorState, LoadingState } from '../ui/PageState'
import { StatusBadge, type StatusTone } from '../ui/StatusBadge'

const PAGE_SIZE = 10

const WORKFLOW_STATUSES: PreorderStatus[] = [
  'CONFIRMED',
  'ORDERED_FROM_SUPPLIER',
  'ARRIVED',
  'READY_FOR_CUSTOMER',
  'FULFILLED',
  'CANCELLED',
  'SUPPLIER_UNAVAILABLE',
]

const PAYMENT_STATUSES: PaymentSummaryStatus[] = [
  'UNPAID',
  'PARTIALLY_PAID',
  'PAID',
  'OVERPAID',
]

const WORKFLOW_LABEL: Record<PreorderStatus, string> = {
  CONFIRMED: 'Confirmed',
  ORDERED_FROM_SUPPLIER: 'Ordered',
  ARRIVED: 'Arrived',
  READY_FOR_CUSTOMER: 'Ready',
  FULFILLED: 'Fulfilled',
  CANCELLED: 'Cancelled',
  SUPPLIER_UNAVAILABLE: 'Unavailable',
}

const WORKFLOW_TONE: Record<PreorderStatus, StatusTone> = {
  CONFIRMED: 'info',
  ORDERED_FROM_SUPPLIER: 'lavender',
  ARRIVED: 'warm',
  READY_FOR_CUSTOMER: 'mint',
  FULFILLED: 'success',
  CANCELLED: 'neutral',
  SUPPLIER_UNAVAILABLE: 'danger',
}

const PAYMENT_LABEL: Record<PaymentSummaryStatus, string> = {
  UNPAID: 'Unpaid',
  PARTIALLY_PAID: 'Partial',
  PAID: 'Paid',
  OVERPAID: 'Overpaid',
}

const PAYMENT_TONE: Record<PaymentSummaryStatus, StatusTone> = {
  UNPAID: 'warm',
  PARTIALLY_PAID: 'warning',
  PAID: 'success',
  OVERPAID: 'danger',
}

const SUMMARY_CARDS: {
  key: 'total' | PreorderStatus
  label: string
  hint: string
  surface: string
  status: PreorderStatus | 'ALL'
}[] = [
  {
    key: 'total',
    label: 'Total',
    hint: 'All loaded preorders',
    surface: 'sky',
    status: 'ALL',
  },
  {
    key: 'CONFIRMED',
    label: 'Confirmed',
    hint: 'Awaiting supplier grouping',
    surface: 'cream',
    status: 'CONFIRMED',
  },
  {
    key: 'ORDERED_FROM_SUPPLIER',
    label: 'Ordered',
    hint: 'With the supplier',
    surface: 'lavender',
    status: 'ORDERED_FROM_SUPPLIER',
  },
  {
    key: 'ARRIVED',
    label: 'Arrived',
    hint: 'In hand, not yet ready',
    surface: 'mist',
    status: 'ARRIVED',
  },
  {
    key: 'READY_FOR_CUSTOMER',
    label: 'Ready for customer',
    hint: 'Collection or post',
    surface: 'sage',
    status: 'READY_FOR_CUSTOMER',
  },
  {
    key: 'FULFILLED',
    label: 'Fulfilled',
    hint: 'Handed over',
    surface: 'blush',
    status: 'FULFILLED',
  },
]

type WorkflowFilter = PreorderStatus | 'ALL'
type PaymentFilter = PaymentSummaryStatus | 'ALL' | 'PRICE_NOT_SET'

function isPreorderStatus(value: string | null): value is PreorderStatus {
  return value !== null && (WORKFLOW_STATUSES as string[]).includes(value)
}

function formatWhen(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return date.toLocaleString(undefined, { dateStyle: 'medium' })
}

function formatAmount(value: Money): string {
  const amount = Number(value)
  if (!Number.isFinite(amount)) {
    return String(value)
  }
  return amount.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
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

function productMeta(product: Product | undefined): string {
  if (!product) {
    return ''
  }
  return [product.style, product.colour, product.size].filter(Boolean).join(' · ')
}

export function PreordersPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const reference = useReferenceData()
  const [tick, setTick] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [preorders, setPreorders] = useState<Preorder[]>([])
  const [query, setQuery] = useState('')
  const [paymentFilter, setPaymentFilter] = useState<PaymentFilter>('ALL')
  const [supplierFilter, setSupplierFilter] = useState('ALL')
  const [page, setPage] = useState(1)
  const [pageFilterKey, setPageFilterKey] = useState('')

  const statusParam = searchParams.get('status')
  const workflowFilter: WorkflowFilter = isPreorderStatus(statusParam) ? statusParam : 'ALL'

  const retry = useCallback(() => {
    setLoading(true)
    setError(null)
    setTick((value) => value + 1)
  }, [])

  useEffect(() => {
    let cancelled = false
    withTimeout(getPreorders(), 20000)
      .then((data) => {
        if (!cancelled) {
          setPreorders(data)
          setLoading(false)
          setError(null)
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setPreorders([])
          setLoading(false)
          setError(errorMessage(caught))
        }
      })
    return () => {
      cancelled = true
    }
  }, [tick])

  const counts = useMemo(() => {
    const next: Record<PreorderStatus, number> = {
      CONFIRMED: 0,
      ORDERED_FROM_SUPPLIER: 0,
      ARRIVED: 0,
      READY_FOR_CUSTOMER: 0,
      FULFILLED: 0,
      CANCELLED: 0,
      SUPPLIER_UNAVAILABLE: 0,
    }
    for (const row of preorders) {
      next[row.status] += 1
    }
    return next
  }, [preorders])

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return preorders.filter((row) => {
      if (workflowFilter !== 'ALL' && row.status !== workflowFilter) {
        return false
      }
      const payment = row.payment_summary.status
      if (paymentFilter === 'PRICE_NOT_SET' && payment !== null) {
        return false
      }
      if (
        paymentFilter !== 'ALL' &&
        paymentFilter !== 'PRICE_NOT_SET' &&
        payment !== paymentFilter
      ) {
        return false
      }
      const product = reference.productById[row.product_id]
      if (supplierFilter !== 'ALL' && product?.supplier_id !== Number(supplierFilter)) {
        return false
      }
      if (!needle) {
        return true
      }
      const haystack = [
        `#${row.id}`,
        String(row.id),
        reference.customerName(row.customer_id),
        reference.productName(row.product_id),
        product ? reference.supplierName(product.supplier_id) : '',
      ]
        .join(' ')
        .toLowerCase()
      return haystack.includes(needle)
    })
  }, [paymentFilter, preorders, query, reference, supplierFilter, workflowFilter])

  const filterKey = `${workflowFilter}|${paymentFilter}|${supplierFilter}|${query}`
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

  function setWorkflowFilter(next: WorkflowFilter) {
    const params = new URLSearchParams(searchParams)
    if (next === 'ALL') {
      params.delete('status')
    } else {
      params.set('status', next)
    }
    setSearchParams(params, { replace: true })
  }

  return (
    <div className="preorders">
      <header className="page-header">
        <h1>Preorders</h1>
        <p>Manage confirmed customer commitments.</p>
      </header>

      <section className="preorder-cards" aria-label="Preorder summary">
        {SUMMARY_CARDS.map((card) => {
          const count = card.key === 'total' ? preorders.length : counts[card.key]
          const selected = workflowFilter === card.status
          return (
            <button
              key={card.key}
              type="button"
              className={`dash-card dash-card--${card.surface}${selected ? ' is-selected' : ''}`}
              onClick={() => setWorkflowFilter(card.status)}
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
            <span className="visually-hidden">Search preorders</span>
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search preorders..."
            />
          </label>
          <label>
            <span className="visually-hidden">Workflow status</span>
            <select
              value={workflowFilter}
              onChange={(event) => setWorkflowFilter(event.target.value as WorkflowFilter)}
            >
              <option value="ALL">All statuses</option>
              {WORKFLOW_STATUSES.map((status) => (
                <option key={status} value={status}>
                  {WORKFLOW_LABEL[status]}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span className="visually-hidden">Payment status</span>
            <select
              value={paymentFilter}
              onChange={(event) => setPaymentFilter(event.target.value as PaymentFilter)}
            >
              <option value="ALL">All payments</option>
              {PAYMENT_STATUSES.map((status) => (
                <option key={status} value={status}>
                  {PAYMENT_LABEL[status]}
                </option>
              ))}
              <option value="PRICE_NOT_SET">Price not set</option>
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
          <LoadingState message="Loading preorders…" />
        ) : error ? (
          <ErrorState title="Preorders could not be loaded" message={error} onRetry={retry} />
        ) : preorders.length === 0 ? (
          <EmptyState
            title="No preorders yet"
            message="Confirmed customer commitments will appear here."
          />
        ) : filtered.length === 0 ? (
          <EmptyState
            title="No matching preorders"
            message="No preorders match these filters."
          />
        ) : (
          <>
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Preorder</th>
                    <th>Customer</th>
                    <th>Product</th>
                    <th>Qty</th>
                    <th>Price</th>
                    <th>Payment</th>
                    <th>Status</th>
                    <th>Supplier</th>
                    <th>Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {pageRows.map((row) => {
                    const product = reference.productById[row.product_id]
                    const meta = productMeta(product)
                    const payment = row.payment_summary.status
                    return (
                      <tr key={row.id}>
                        <td className="data-table__id">#{row.id}</td>
                        <td>{reference.customerName(row.customer_id)}</td>
                        <td>
                          <span className="cell-primary">{reference.productName(row.product_id)}</span>
                          {meta ? <span className="cell-meta">{meta}</span> : null}
                        </td>
                        <td>{row.quantity}</td>
                        <td>
                          {row.agreed_price === null ? 'Not set' : formatAmount(row.agreed_price)}
                        </td>
                        <td>
                          {payment === null ? (
                            <StatusBadge label="Price not set" tone="neutral" />
                          ) : (
                            <StatusBadge label={PAYMENT_LABEL[payment]} tone={PAYMENT_TONE[payment]} />
                          )}
                        </td>
                        <td>
                          <StatusBadge
                            label={WORKFLOW_LABEL[row.status]}
                            tone={WORKFLOW_TONE[row.status]}
                          />
                        </td>
                        <td>
                          {product ? reference.supplierName(product.supplier_id) : '—'}
                        </td>
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
