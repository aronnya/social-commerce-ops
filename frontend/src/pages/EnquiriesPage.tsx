import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { createEnquiry, getEnquiries, updateEnquiry } from '../api/resources'
import type {
  Enquiry,
  EnquiryCreate,
  EnquiryOutcome,
  EnquiryUpdate,
  LostDemandReason,
} from '../api/types'
import { useReferenceData } from '../api/useReferenceData'
import { EmptyState, ErrorState, LoadingState } from '../ui/PageState'
import { StatusBadge, type StatusTone } from '../ui/StatusBadge'

const PAGE_SIZE = 10

const LOST_OUTCOMES: LostDemandReason[] = [
  'TOO_EXPENSIVE',
  'SUPPLIER_UNAVAILABLE',
  'CUSTOMER_GHOSTED',
  'WRONG_SIZE',
  'NOT_INTERESTED',
]

const ALL_OUTCOMES: EnquiryOutcome[] = ['PREORDERED', ...LOST_OUTCOMES]

const OUTCOME_LABEL: Record<EnquiryOutcome, string> = {
  PREORDERED: 'Preordered',
  TOO_EXPENSIVE: 'Too expensive',
  SUPPLIER_UNAVAILABLE: 'Supplier unavailable',
  CUSTOMER_GHOSTED: 'Customer ghosted',
  WRONG_SIZE: 'Wrong size',
  NOT_INTERESTED: 'Not interested',
}

const OUTCOME_TONE: Record<EnquiryOutcome, StatusTone> = {
  PREORDERED: 'success',
  TOO_EXPENSIVE: 'warning',
  SUPPLIER_UNAVAILABLE: 'danger',
  CUSTOMER_GHOSTED: 'warm',
  WRONG_SIZE: 'lavender',
  NOT_INTERESTED: 'neutral',
}

const SUMMARY_CARDS: {
  key: 'total' | 'open' | 'PREORDERED' | 'lost'
  label: string
  hint: string
  surface: string
  filter: OutcomeFilter
}[] = [
  {
    key: 'total',
    label: 'Total',
    hint: 'All loaded enquiries',
    surface: 'sky',
    filter: 'ALL',
  },
  {
    key: 'open',
    label: 'Open',
    hint: 'No outcome yet',
    surface: 'cream',
    filter: 'OPEN',
  },
  {
    key: 'PREORDERED',
    label: 'Preordered',
    hint: 'Outcome only, not conversion proof',
    surface: 'sage',
    filter: 'PREORDERED',
  },
  {
    key: 'lost',
    label: 'Lost',
    hint: 'Recorded lost-demand reasons',
    surface: 'blush',
    filter: 'LOST',
  },
]

type OutcomeFilter = EnquiryOutcome | 'ALL' | 'OPEN' | 'LOST'

function isOutcomeFilter(value: string | null): value is OutcomeFilter {
  return (
    value === 'ALL' ||
    value === 'OPEN' ||
    value === 'LOST' ||
    (value !== null && (ALL_OUTCOMES as string[]).includes(value))
  )
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

function mutationError(caught: unknown, fallback: string): string {
  if (
    caught instanceof ApiError &&
    (caught.status === 409 || caught.status === 0 || caught.status === 404)
  ) {
    return caught.message
  }
  if (caught instanceof ApiError && caught.status === 422) {
    return 'The request was not valid.'
  }
  return fallback
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

function isLostOutcome(outcome: EnquiryOutcome | null): outcome is LostDemandReason {
  return outcome !== null && (LOST_OUTCOMES as string[]).includes(outcome)
}

export function EnquiriesPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const reference = useReferenceData()
  const [tick, setTick] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [enquiries, setEnquiries] = useState<Enquiry[]>([])
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(1)
  const [pageFilterKey, setPageFilterKey] = useState('')
  const [creating, setCreating] = useState(false)
  const [createBusy, setCreateBusy] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const [createNotice, setCreateNotice] = useState<string | null>(null)
  const [resolvingId, setResolvingId] = useState<number | null>(null)
  const [resolveBusy, setResolveBusy] = useState(false)
  const [resolveError, setResolveError] = useState<string | null>(null)
  const createLock = useRef(false)
  const resolveLock = useRef(false)

  const outcomeParam = searchParams.get('outcome')
  const outcomeFilter: OutcomeFilter = isOutcomeFilter(outcomeParam) ? outcomeParam : 'ALL'

  const retry = useCallback(() => {
    setLoading(true)
    setError(null)
    setTick((value) => value + 1)
  }, [])

  useEffect(() => {
    let cancelled = false
    withTimeout(getEnquiries(), 20000)
      .then((data) => {
        if (!cancelled) {
          setEnquiries(data)
          setLoading(false)
          setError(null)
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setEnquiries([])
          setLoading(false)
          setError(errorMessage(caught))
        }
      })
    return () => {
      cancelled = true
    }
  }, [tick])

  const counts = useMemo(() => {
    let open = 0
    let preordered = 0
    let lost = 0
    for (const row of enquiries) {
      if (row.outcome === null) {
        open += 1
      } else if (row.outcome === 'PREORDERED') {
        preordered += 1
      } else if (isLostOutcome(row.outcome)) {
        lost += 1
      }
    }
    return { open, preordered, lost }
  }, [enquiries])

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return enquiries.filter((row) => {
      if (outcomeFilter === 'OPEN' && row.outcome !== null) {
        return false
      }
      if (outcomeFilter === 'LOST' && !isLostOutcome(row.outcome)) {
        return false
      }
      if (
        outcomeFilter !== 'ALL' &&
        outcomeFilter !== 'OPEN' &&
        outcomeFilter !== 'LOST' &&
        row.outcome !== outcomeFilter
      ) {
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
        row.notes ?? '',
        row.outcome ? OUTCOME_LABEL[row.outcome] : 'open',
      ]
        .join(' ')
        .toLowerCase()
      return haystack.includes(needle)
    })
  }, [enquiries, outcomeFilter, query, reference])

  const filterKey = `${outcomeFilter}|${query}`
  const currentPage = pageFilterKey === filterKey ? page : 1
  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const safePage = Math.min(currentPage, pageCount)
  const pageRows = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE)
  const rangeStart = filtered.length === 0 ? 0 : (safePage - 1) * PAGE_SIZE + 1
  const rangeEnd = Math.min(safePage * PAGE_SIZE, filtered.length)
  const resolving = enquiries.find((row) => row.id === resolvingId) ?? null

  function goToPage(next: number) {
    setPageFilterKey(filterKey)
    setPage(next)
  }

  function setOutcomeFilter(next: OutcomeFilter) {
    const params = new URLSearchParams(searchParams)
    if (next === 'ALL') {
      params.delete('outcome')
    } else {
      params.set('outcome', next)
    }
    setSearchParams(params, { replace: true })
  }

  function replaceEnquiry(updated: Enquiry) {
    setEnquiries((current) =>
      current.map((row) => (row.id === updated.id ? updated : row)),
    )
  }

  function cardCount(key: (typeof SUMMARY_CARDS)[number]['key']): number {
    if (key === 'total') {
      return enquiries.length
    }
    if (key === 'open') {
      return counts.open
    }
    if (key === 'PREORDERED') {
      return counts.preordered
    }
    return counts.lost
  }

  return (
    <div className="preorders enquiries">
      <header className="list-header">
        <div className="page-header">
          <h1>Enquiries</h1>
          <p>Track customer interest and understand lost demand.</p>
        </div>
        <button
          type="button"
          className="action-btn action-btn--primary"
          disabled={createBusy}
          onClick={() => {
            setCreateError(null)
            setCreating((open) => !open)
          }}
        >
          + New Enquiry
        </button>
      </header>

      {creating ? (
        <NewEnquiryForm
          busy={createBusy}
          error={createError}
          onCancel={() => {
            setCreating(false)
            setCreateError(null)
          }}
          onSubmit={async (payload) => {
            if (createLock.current) {
              return
            }
            createLock.current = true
            setCreateBusy(true)
            setCreateError(null)
            setCreateNotice(null)
            try {
              const created = await withTimeout(createEnquiry(payload), 20000)
              setEnquiries((current) => [...current, created])
              setCreateNotice(`Enquiry #${created.id} was recorded.`)
              setCreating(false)
            } catch (caught: unknown) {
              setCreateError(mutationError(caught, 'This enquiry could not be created.'))
            } finally {
              createLock.current = false
              setCreateBusy(false)
            }
          }}
        />
      ) : null}

      {createNotice ? <p className="ops-notice">{createNotice}</p> : null}

      {resolving && resolving.outcome === null ? (
        <ResolveEnquiryForm
          enquiry={resolving}
          busy={resolveBusy}
          error={resolveError}
          onCancel={() => {
            setResolvingId(null)
            setResolveError(null)
          }}
          onSubmit={async (payload) => {
            if (resolveLock.current) {
              return
            }
            resolveLock.current = true
            setResolveBusy(true)
            setResolveError(null)
            try {
              const updated = await withTimeout(updateEnquiry(resolving.id, payload), 20000)
              replaceEnquiry(updated)
              setResolvingId(null)
            } catch (caught: unknown) {
              setResolveError(mutationError(caught, 'This enquiry could not be updated.'))
            } finally {
              resolveLock.current = false
              setResolveBusy(false)
            }
          }}
        />
      ) : null}

      <section className="preorder-cards enquiry-cards" aria-label="Enquiry summary">
        {SUMMARY_CARDS.map((card) => {
          const count = cardCount(card.key)
          const selected = outcomeFilter === card.filter
          return (
            <button
              key={card.key}
              type="button"
              className={`dash-card dash-card--${card.surface}${selected ? ' is-selected' : ''}`}
              onClick={() => setOutcomeFilter(card.filter)}
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
            <span className="visually-hidden">Search enquiries</span>
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search enquiries..."
            />
          </label>
          <label>
            <span className="visually-hidden">Outcome</span>
            <select
              value={outcomeFilter}
              onChange={(event) => setOutcomeFilter(event.target.value as OutcomeFilter)}
            >
              <option value="ALL">All outcomes</option>
              <option value="OPEN">Open</option>
              <option value="LOST">Lost demand</option>
              {ALL_OUTCOMES.map((outcome) => (
                <option key={outcome} value={outcome}>
                  {OUTCOME_LABEL[outcome]}
                </option>
              ))}
            </select>
          </label>
        </div>

        {loading ? (
          <LoadingState message="Loading enquiries…" />
        ) : error ? (
          <ErrorState title="Enquiries could not be loaded" message={error} onRetry={retry} />
        ) : enquiries.length === 0 ? (
          <EmptyState
            title="No enquiries yet"
            message="Record customer interest before it becomes a preorder."
          />
        ) : filtered.length === 0 ? (
          <EmptyState title="No matching enquiries" message="No enquiries match these filters." />
        ) : (
          <>
            <div className="table-wrap">
              <table className="data-table data-table--enquiries">
                <thead>
                  <tr>
                    <th>Enquiry</th>
                    <th>Customer</th>
                    <th>Product</th>
                    <th>Qty</th>
                    <th>Outcome</th>
                    <th>Notes</th>
                    <th>Created</th>
                    <th>Updated</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {pageRows.map((row) => (
                    <tr key={row.id}>
                      <td className="data-table__id">#{row.id}</td>
                      <td>{reference.customerName(row.customer_id)}</td>
                      <td>{reference.productName(row.product_id)}</td>
                      <td>{row.quantity}</td>
                      <td>
                        {row.outcome === null ? (
                          <StatusBadge label="Open" tone="info" />
                        ) : (
                          <StatusBadge
                            label={OUTCOME_LABEL[row.outcome]}
                            tone={OUTCOME_TONE[row.outcome]}
                          />
                        )}
                      </td>
                      <td>
                        {row.notes ? (
                          <span className="cell-notes">{row.notes}</span>
                        ) : (
                          <span className="data-table__muted">—</span>
                        )}
                      </td>
                      <td className="data-table__muted">{formatWhen(row.created_at)}</td>
                      <td className="data-table__muted">{formatWhen(row.updated_at)}</td>
                      <td>
                        {row.outcome === null ? (
                          <button
                            type="button"
                            className="action-btn"
                            disabled={resolveBusy}
                            onClick={() => {
                              setResolveError(null)
                              setResolvingId(row.id)
                            }}
                          >
                            Record outcome
                          </button>
                        ) : (
                          <span className="data-table__muted">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
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

function NewEnquiryForm({
  busy,
  error,
  onCancel,
  onSubmit,
}: {
  busy: boolean
  error: string | null
  onCancel: () => void
  onSubmit: (payload: EnquiryCreate) => void
}) {
  const reference = useReferenceData()
  const [customerId, setCustomerId] = useState('')
  const [productId, setProductId] = useState('')
  const [quantity, setQuantity] = useState('1')
  const [notes, setNotes] = useState('')

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (busy) {
      return
    }
    const payload: EnquiryCreate = {
      customer_id: Number(customerId),
      product_id: Number(productId),
      quantity: Number(quantity),
    }
    if (notes.trim()) {
      payload.notes = notes.trim()
    }
    onSubmit(payload)
  }

  return (
    <section className="panel">
      <h2>New enquiry</h2>
      <p className="detail-muted">Records customer interest. This is not a preorder.</p>
      <form className="ops-form" onSubmit={handleSubmit}>
        <label>
          Customer
          <select
            required
            value={customerId}
            disabled={busy}
            onChange={(event) => setCustomerId(event.target.value)}
          >
            <option value="">Select customer</option>
            {reference.customers.map((customer) => (
              <option key={customer.id} value={String(customer.id)}>
                {customer.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Product
          <select
            required
            value={productId}
            disabled={busy}
            onChange={(event) => setProductId(event.target.value)}
          >
            <option value="">Select product</option>
            {reference.products.map((product) => (
              <option key={product.id} value={String(product.id)}>
                {product.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Quantity
          <input
            required
            type="number"
            min="1"
            step="1"
            value={quantity}
            disabled={busy}
            onChange={(event) => setQuantity(event.target.value)}
          />
        </label>
        <label className="ops-form__wide">
          Notes
          <textarea
            rows={2}
            value={notes}
            disabled={busy}
            onChange={(event) => setNotes(event.target.value)}
          />
        </label>
        {error ? <p className="detail-action-error">{error}</p> : null}
        <div className="detail-actions__row ops-form__wide">
          <button type="submit" className="action-btn action-btn--primary" disabled={busy}>
            Create enquiry
          </button>
          <button type="button" className="action-btn" disabled={busy} onClick={onCancel}>
            Cancel
          </button>
        </div>
      </form>
    </section>
  )
}

function ResolveEnquiryForm({
  enquiry,
  busy,
  error,
  onCancel,
  onSubmit,
}: {
  enquiry: Enquiry
  busy: boolean
  error: string | null
  onCancel: () => void
  onSubmit: (payload: EnquiryUpdate) => void
}) {
  const reference = useReferenceData()
  const [outcome, setOutcome] = useState<LostDemandReason | ''>('')
  const [notes, setNotes] = useState(enquiry.notes ?? '')

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (busy || outcome === '') {
      return
    }
    const payload: EnquiryUpdate = { outcome }
    if (notes.trim()) {
      payload.notes = notes.trim()
    } else if (enquiry.notes) {
      payload.notes = null
    }
    onSubmit(payload)
  }

  return (
    <section className="panel">
      <h2>Record outcome</h2>
      <p className="detail-muted">
        Enquiry #{enquiry.id} · {reference.customerName(enquiry.customer_id)} ·{' '}
        {reference.productName(enquiry.product_id)}. Lost-demand reasons only. Preorder conversion
        stays with preorder creation.
      </p>
      <form className="ops-form" onSubmit={handleSubmit}>
        <label>
          Outcome
          <select
            required
            value={outcome}
            disabled={busy}
            onChange={(event) => setOutcome(event.target.value as LostDemandReason | '')}
          >
            <option value="">Select reason</option>
            {LOST_OUTCOMES.map((value) => (
              <option key={value} value={value}>
                {OUTCOME_LABEL[value]}
              </option>
            ))}
          </select>
        </label>
        <label className="ops-form__wide">
          Notes
          <textarea
            rows={2}
            value={notes}
            disabled={busy}
            onChange={(event) => setNotes(event.target.value)}
          />
        </label>
        {error ? <p className="detail-action-error">{error}</p> : null}
        <div className="detail-actions__row ops-form__wide">
          <button type="submit" className="action-btn action-btn--primary" disabled={busy}>
            Save outcome
          </button>
          <button type="button" className="action-btn" disabled={busy} onClick={onCancel}>
            Cancel
          </button>
        </div>
      </form>
    </section>
  )
}
