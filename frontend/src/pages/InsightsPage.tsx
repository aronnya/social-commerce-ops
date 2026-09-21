import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { getDemandAnalytics } from '../api/resources'
import type { DemandAnalytics, LostDemandReason, Money } from '../api/types'
import { useReferenceData } from '../api/useReferenceData'
import { EmptyState, ErrorState, LoadingState } from '../ui/PageState'

const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/

const LOST_DEMAND_LABELS: Record<LostDemandReason, string> = {
  TOO_EXPENSIVE: 'Too expensive',
  SUPPLIER_UNAVAILABLE: 'Supplier unavailable',
  CUSTOMER_GHOSTED: 'Customer ghosted',
  WRONG_SIZE: 'Wrong size',
  NOT_INTERESTED: 'Not interested',
}

const LOST_ORDER: LostDemandReason[] = [
  'TOO_EXPENSIVE',
  'SUPPLIER_UNAVAILABLE',
  'CUSTOMER_GHOSTED',
  'WRONG_SIZE',
  'NOT_INTERESTED',
]

function isDateOnly(value: string | null): value is string {
  return value !== null && DATE_PATTERN.test(value)
}

function startUtc(dateOnly: string): string {
  return `${dateOnly}T00:00:00.000Z`
}

function exclusiveEndUtc(dateOnly: string): string {
  const [year, month, day] = dateOnly.split('-').map(Number)
  return new Date(Date.UTC(year, month - 1, day + 1)).toISOString()
}

function formatRate(value: Money | null): string {
  if (value === null) {
    return '—'
  }
  const rate = Number(value)
  if (!Number.isFinite(rate)) {
    return '—'
  }
  return `${(rate * 100).toLocaleString(undefined, { maximumFractionDigits: 1 })}%`
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

export function InsightsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const reference = useReferenceData()
  const fromRaw = searchParams.get('from')
  const toRaw = searchParams.get('to')
  const appliedFrom = isDateOnly(fromRaw) ? fromRaw : ''
  const appliedTo = isDateOnly(toRaw) ? toRaw : ''
  const invalidAppliedRange = Boolean(appliedFrom && appliedTo && appliedFrom > appliedTo)
  const [fromDraft, setFromDraft] = useState(appliedFrom)
  const [toDraft, setToDraft] = useState(appliedTo)
  const [formError, setFormError] = useState<string | null>(null)
  const [tick, setTick] = useState(0)
  const requestKey = `${appliedFrom}|${appliedTo}|${tick}`
  const [result, setResult] = useState<{
    key: string
    analytics: DemandAnalytics | null
    error: string | null
  } | null>(null)

  const retry = useCallback(() => {
    setTick((value) => value + 1)
  }, [])

  useEffect(() => {
    if (invalidAppliedRange) {
      return
    }
    let cancelled = false
    const params: { from?: string; to?: string } = {}
    if (appliedFrom) {
      params.from = startUtc(appliedFrom)
    }
    if (appliedTo) {
      params.to = exclusiveEndUtc(appliedTo)
    }
    withTimeout(getDemandAnalytics(params), 20000)
      .then((data) => {
        if (!cancelled) {
          setResult({ key: requestKey, analytics: data, error: null })
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setResult({ key: requestKey, analytics: null, error: errorMessage(caught) })
        }
      })
    return () => {
      cancelled = true
    }
  }, [appliedFrom, appliedTo, invalidAppliedRange, requestKey])

  const loading = !invalidAppliedRange && result?.key !== requestKey
  const error = result?.key === requestKey ? result.error : null
  const analytics = result?.key === requestKey ? result.analytics : null
  const rangeError =
    formError ?? (invalidAppliedRange ? 'From must be on or before To.' : null)

  function applyRange(event: FormEvent) {
    event.preventDefault()
    if (fromDraft && !isDateOnly(fromDraft)) {
      setFormError('From is not a valid date.')
      return
    }
    if (toDraft && !isDateOnly(toDraft)) {
      setFormError('To is not a valid date.')
      return
    }
    if (fromDraft && toDraft && fromDraft > toDraft) {
      setFormError('From must be on or before To.')
      return
    }
    setFormError(null)
    const params = new URLSearchParams()
    if (fromDraft) {
      params.set('from', fromDraft)
    }
    if (toDraft) {
      params.set('to', toDraft)
    }
    setSearchParams(params, { replace: true })
  }

  function clearRange() {
    setFromDraft('')
    setToDraft('')
    setFormError(null)
    setSearchParams(new URLSearchParams(), { replace: true })
  }

  const overview = analytics?.overview
  const lostMax = useMemo(() => {
    const buckets = analytics?.lost_demand ?? []
    return Math.max(0, ...buckets.map((bucket) => bucket.count))
  }, [analytics])

  return (
    <div className="preorders insights">
      <header className="page-header">
        <h1>Insights</h1>
        <p>Understand customer demand, conversion, and lost-sale reasons.</p>
      </header>

      <section className="panel">
        <h2>Enquiry window</h2>
        <p className="detail-muted">
          Filters enquiries by enquiry date. The selected To date is included. Conversion uses
          linked preorders, not the Preordered outcome label.
        </p>
        <form className="ops-form insight-range" onSubmit={applyRange}>
          <label>
            From
            <input
              type="date"
              value={fromDraft}
              onChange={(event) => setFromDraft(event.target.value)}
            />
          </label>
          <label>
            To
            <input type="date" value={toDraft} onChange={(event) => setToDraft(event.target.value)} />
          </label>
          <div className="detail-actions__row insight-range__actions">
            <button type="submit" className="action-btn action-btn--primary">
              Apply
            </button>
            <button type="button" className="action-btn" onClick={clearRange}>
              Clear
            </button>
          </div>
        </form>
        {rangeError ? <p className="detail-action-error">{rangeError}</p> : null}
      </section>

      {loading ? (
        <section className="panel">
          <LoadingState message="Loading demand insights…" />
        </section>
      ) : error ? (
        <section className="panel">
          <ErrorState title="Insights could not be loaded" message={error} onRetry={retry} />
        </section>
      ) : analytics && overview ? (
        <>
          <section className="preorder-cards enquiry-cards" aria-label="Demand overview">
            <div className="dash-card dash-card--sky dash-card--static">
              <span className="dash-card__count">{overview.total_enquiries}</span>
              <span className="dash-card__label">Total enquiries</span>
              <span className="dash-card__hint">{overview.requested_quantity} units requested</span>
            </div>
            <div className="dash-card dash-card--cream dash-card--static">
              <span className="dash-card__count">{overview.open_enquiries}</span>
              <span className="dash-card__label">Open</span>
              <span className="dash-card__hint">No linked preorder, no outcome</span>
            </div>
            <div className="dash-card dash-card--sage dash-card--static">
              <span className="dash-card__count">{overview.converted_enquiries}</span>
              <span className="dash-card__label">Converted</span>
              <span className="dash-card__hint">Linked preorder exists</span>
            </div>
            <div className="dash-card dash-card--blush dash-card--static">
              <span className="dash-card__count">{overview.lost_enquiries}</span>
              <span className="dash-card__label">Lost</span>
              <span className="dash-card__hint">Factual lost-demand outcome</span>
            </div>
            <div className="dash-card dash-card--lavender dash-card--static insight-rate-card">
              <span className="dash-card__count">{formatRate(overview.conversion_rate)}</span>
              <span className="dash-card__label">Conversion rate</span>
              <span className="dash-card__hint">
                {overview.conversion_rate === null
                  ? 'Not enough resolved data'
                  : `${overview.converted_enquiries} of ${overview.resolved_enquiries} resolved`}
              </span>
            </div>
          </section>
          {overview.total_enquiries === 0 ? (
            <p className="detail-muted">No enquiries in this window.</p>
          ) : null}

          <section className="panel">
            <h2>Lost demand</h2>
            <p className="detail-muted">Counts use the five recorded lost-sale reasons only.</p>
            {lostMax === 0 ? (
              <p className="detail-muted">No lost-demand outcomes in this window.</p>
            ) : null}
            <ul className="insight-bars">
              {LOST_ORDER.map((reason) => {
                const bucket = analytics.lost_demand.find((item) => item.reason === reason)
                const count = bucket?.count ?? 0
                const width = lostMax === 0 ? 0 : Math.round((count / lostMax) * 100)
                return (
                  <li key={reason} className={count === 0 ? 'insight-bar is-muted' : 'insight-bar'}>
                    <span className="insight-bar__label">{LOST_DEMAND_LABELS[reason]}</span>
                    <span className="insight-bar__track" aria-hidden="true">
                      <span className="insight-bar__fill" style={{ width: `${width}%` }} />
                    </span>
                    <span className="insight-bar__count">{count}</span>
                  </li>
                )
              })}
            </ul>
          </section>

          <section className="panel">
            <h2>Product demand</h2>
            <p className="detail-muted">
              Enquiry demand by catalogue product. Conversion is linked-preorder conversion.
            </p>
            {analytics.products.length === 0 ? (
              <EmptyState
                title="No product demand"
                message="No enquiries fall in this window."
              />
            ) : (
              <div className="table-wrap">
                <table className="data-table data-table--insights">
                  <thead>
                    <tr>
                      <th>Product</th>
                      <th>Enquiries</th>
                      <th>Converted</th>
                      <th>Lost</th>
                      <th>Open</th>
                      <th>Conversion</th>
                    </tr>
                  </thead>
                  <tbody>
                    {analytics.products.map((row) => {
                      const meta = [row.style, row.colour, row.size].filter(Boolean).join(' · ')
                      const productLabel = row.name || reference.productName(row.product_id)
                      return (
                        <tr key={row.product_id}>
                          <td>
                            <span className="cell-primary">{productLabel}</span>
                            <span className="cell-meta">
                              {row.supplier_name || reference.supplierName(row.supplier_id)}
                              {meta ? ` · ${meta}` : ''}
                            </span>
                          </td>
                          <td>{row.enquiry_count}</td>
                          <td>{row.converted_enquiries}</td>
                          <td>{row.lost_enquiries}</td>
                          <td>{row.open_enquiries}</td>
                          <td>{formatRate(row.conversion_rate)}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="panel">
            <h2>Supplier demand</h2>
            <p className="detail-muted">
              Enquiry demand for each supplier’s catalogue products. This is not a supplier score.
            </p>
            {analytics.suppliers.length === 0 ? (
              <EmptyState
                title="No supplier demand"
                message="No enquiries fall in this window."
              />
            ) : (
              <div className="table-wrap">
                <table className="data-table data-table--insights">
                  <thead>
                    <tr>
                      <th>Supplier</th>
                      <th>Enquiries</th>
                      <th>Customers</th>
                      <th>Converted</th>
                      <th>Lost</th>
                      <th>Open</th>
                      <th>Conversion</th>
                    </tr>
                  </thead>
                  <tbody>
                    {analytics.suppliers.map((row) => (
                      <tr key={row.supplier_id}>
                        <td className="cell-primary">
                          {row.name || reference.supplierName(row.supplier_id)}
                        </td>
                        <td>{row.enquiry_count}</td>
                        <td>{row.distinct_customers}</td>
                        <td>{row.converted_enquiries}</td>
                        <td>{row.lost_enquiries}</td>
                        <td>{row.open_enquiries}</td>
                        <td>{formatRate(row.conversion_rate)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="panel">
            <h2>Data quality</h2>
            <p className="detail-muted">Integrity signals, not demand performance.</p>
            {overview.unlinked_preordered_outcomes === 0 &&
            overview.linked_preorder_outcome_mismatch === 0 ? (
              <p className="detail-muted">No integrity issues in this window.</p>
            ) : (
              <dl className="detail-facts">
                <div>
                  <dt>Marked preordered without a linked preorder</dt>
                  <dd>{overview.unlinked_preordered_outcomes}</dd>
                </div>
                <div>
                  <dt>Linked preorder with a mismatched enquiry outcome</dt>
                  <dd>{overview.linked_preorder_outcome_mismatch}</dd>
                </div>
              </dl>
            )}
          </section>

          <section className="panel">
            <h2>Supplier reconciliation</h2>
            <p className="detail-muted">
              All-time reconciled supplier orders. This is not customer collection or postage, and
              it is not limited to the enquiry date range.
            </p>
            <dl className="detail-facts">
              <div>
                <dt>Reconciled orders</dt>
                <dd>{analytics.fulfilment.reconciled_order_count}</dd>
              </div>
              <div>
                <dt>Ordered units</dt>
                <dd>{analytics.fulfilment.ordered_quantity}</dd>
              </div>
              <div>
                <dt>Received units</dt>
                <dd>{analytics.fulfilment.received_quantity}</dd>
              </div>
              <div>
                <dt>Shortage units</dt>
                <dd>{analytics.fulfilment.shortage_units}</dd>
              </div>
              <div>
                <dt>Excess units</dt>
                <dd>{analytics.fulfilment.excess_units}</dd>
              </div>
            </dl>
          </section>
        </>
      ) : null}
    </div>
  )
}
