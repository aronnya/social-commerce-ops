import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError } from '../api/client'
import { getAttention, getDemandAnalytics } from '../api/resources'
import type {
  AttentionCounts,
  AttentionItem,
  AttentionQueue,
  AttentionType,
  DemandAnalytics,
  LostDemandReason,
  Money,
} from '../api/types'
import { useReferenceData } from '../api/useReferenceData'
import { EmptyState, ErrorState, LoadingState } from '../ui/PageState'
import { StatusBadge, type StatusTone } from '../ui/StatusBadge'

type LoadState<T> = {
  data: T | null
  loading: boolean
  error: string | null
}

const ATTENTION_CARDS: {
  key: keyof AttentionCounts
  label: string
  hint: string
  surface: string
  to: string
}[] = [
  {
    key: 'preorder_needs_supplier_order',
    label: 'Needs supplier order',
    hint: 'Confirmed, not yet grouped',
    surface: 'sky',
    to: '/preorders?status=CONFIRMED',
  },
  {
    key: 'supplier_order_draft_needs_placement',
    label: 'Drafts to place',
    hint: 'Review then place',
    surface: 'cream',
    to: '/supplier-orders?status=DRAFT',
  },
  {
    key: 'supplier_order_needs_reconciliation',
    label: 'Arrived — reconcile',
    hint: 'Match received vs ordered',
    surface: 'lavender',
    to: '/supplier-orders?status=ARRIVED',
  },
  {
    key: 'preorder_needs_customer_ready',
    label: 'Arrived — mark ready',
    hint: 'Tell the customer it is here',
    surface: 'mist',
    to: '/preorders?status=ARRIVED',
  },
  {
    key: 'preorder_needs_fulfilment',
    label: 'Ready — fulfil',
    hint: 'Collection or post',
    surface: 'sage',
    to: '/preorders?status=READY_FOR_CUSTOMER',
  },
]

const ATTENTION_COPY: Record<
  AttentionType,
  { title: (id: number) => string; badge: string; tone: StatusTone }
> = {
  preorder_needs_supplier_order: {
    title: (id) => `Add preorder #${id} to a supplier order`,
    badge: 'Supplier order',
    tone: 'info',
  },
  supplier_order_draft_needs_placement: {
    title: (id) => `Review and place supplier order #${id}`,
    badge: 'Place draft',
    tone: 'warning',
  },
  supplier_order_needs_reconciliation: {
    title: (id) => `Reconcile arrived supplier order #${id}`,
    badge: 'Reconcile',
    tone: 'warning',
  },
  preorder_needs_customer_ready: {
    title: (id) => `Mark preorder #${id} ready for customer`,
    badge: 'Mark ready',
    tone: 'info',
  },
  preorder_needs_fulfilment: {
    title: (id) => `Complete customer fulfilment for preorder #${id}`,
    badge: 'Fulfil',
    tone: 'success',
  },
  preorder_overpaid: {
    title: (id) => `Review overpayment on preorder #${id}`,
    badge: 'Overpaid',
    tone: 'danger',
  },
}

const LOST_DEMAND_LABELS: Record<LostDemandReason, string> = {
  TOO_EXPENSIVE: 'Too expensive',
  SUPPLIER_UNAVAILABLE: 'Supplier unavailable',
  CUSTOMER_GHOSTED: 'Customer ghosted',
  WRONG_SIZE: 'Wrong size',
  NOT_INTERESTED: 'Not interested',
}

function formatWhen(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
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

export function DashboardPage() {
  const [attentionTick, setAttentionTick] = useState(0)
  const [demandTick, setDemandTick] = useState(0)
  const [attention, setAttention] = useState<LoadState<AttentionQueue>>({
    data: null,
    loading: true,
    error: null,
  })
  const [demand, setDemand] = useState<LoadState<DemandAnalytics>>({
    data: null,
    loading: true,
    error: null,
  })

  const retryAttention = useCallback(() => {
    setAttention({ data: null, loading: true, error: null })
    setAttentionTick((value) => value + 1)
  }, [])

  const retryDemand = useCallback(() => {
    setDemand({ data: null, loading: true, error: null })
    setDemandTick((value) => value + 1)
  }, [])

  useEffect(() => {
    let cancelled = false
    withTimeout(getAttention(), 20000)
      .then((data) => {
        if (!cancelled) {
          setAttention({ data, loading: false, error: null })
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setAttention({ data: null, loading: false, error: errorMessage(caught) })
        }
      })
    return () => {
      cancelled = true
    }
  }, [attentionTick])

  useEffect(() => {
    let cancelled = false
    withTimeout(getDemandAnalytics(), 20000)
      .then((data) => {
        if (!cancelled) {
          setDemand({ data, loading: false, error: null })
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setDemand({ data: null, loading: false, error: errorMessage(caught) })
        }
      })
    return () => {
      cancelled = true
    }
  }, [demandTick])

  return (
    <div className="dashboard">
      <header className="page-header">
        <h1>Dashboard</h1>
        <p>What needs your attention today.</p>
      </header>

      <section className="dash-cards" aria-label="Attention summary">
        {ATTENTION_CARDS.map((card) => {
          const count = attention.data?.counts[card.key]
          return (
            <Link key={card.key} to={card.to} className={`dash-card dash-card--${card.surface}`}>
              <span className="dash-card__count">
                {attention.loading ? '…' : attention.error ? '—' : count}
              </span>
              <span className="dash-card__label">{card.label}</span>
              <span className="dash-card__hint">{card.hint}</span>
            </Link>
          )
        })}
      </section>

      <div className="dash-grid">
        <section className="panel dash-queue" aria-labelledby="attention-queue-heading">
          <header className="panel__header">
            <h2 id="attention-queue-heading">Attention Queue</h2>
            <p>Work that needs action, ordered by priority.</p>
          </header>
          <div className="panel__body panel__body--queue">
            {attention.loading ? (
              <LoadingState message="Loading attention items…" />
            ) : attention.error ? (
              <ErrorState
                title="Attention could not be loaded"
                message={attention.error}
                onRetry={retryAttention}
              />
            ) : attention.data && attention.data.items.length === 0 ? (
              <EmptyState
                title="You're all caught up"
                message="No operational items need attention right now."
              />
            ) : (
              <ul className="queue-list">
                {attention.data?.items.map((item) => (
                  <QueueRow key={`${item.type}-${item.entity_type}-${item.entity_id}`} item={item} />
                ))}
              </ul>
            )}
          </div>
        </section>

        <div className="dash-side">
          <section className="panel panel--demand" aria-labelledby="demand-heading">
            <header className="panel__header">
              <h2 id="demand-heading">Demand at a glance</h2>
              <p>Enquiry conversion from current records.</p>
            </header>
            <div className="panel__body panel__body--demand">
              {demand.loading ? (
                <LoadingState message="Loading demand…" />
              ) : demand.error ? (
                <ErrorState
                  title="Demand could not be loaded"
                  message={demand.error}
                  onRetry={retryDemand}
                />
              ) : demand.data ? (
                <DemandGlance analytics={demand.data} />
              ) : null}
            </div>
          </section>

          <section className="panel panel--actions" aria-labelledby="quick-actions-heading">
            <header className="panel__header">
              <h2 id="quick-actions-heading">Quick actions</h2>
            </header>
            <nav className="quick-actions">
              <Link to="/enquiries" className="quick-action quick-action--sky">
                <span className="quick-action__label">New enquiry</span>
                <span className="quick-action__go" aria-hidden="true">
                  →
                </span>
              </Link>
              <Link to="/preorders" className="quick-action quick-action--cream">
                <span className="quick-action__label">New preorder</span>
                <span className="quick-action__go" aria-hidden="true">
                  →
                </span>
              </Link>
              <Link to="/supplier-orders" className="quick-action quick-action--sage">
                <span className="quick-action__label">Generate supplier orders</span>
                <span className="quick-action__go" aria-hidden="true">
                  →
                </span>
              </Link>
            </nav>
          </section>
        </div>
      </div>
    </div>
  )
}

function QueueRow({ item }: { item: AttentionItem }) {
  const { customerName, productName, supplierName } = useReferenceData()
  const copy = ATTENTION_COPY[item.type]
  const to = item.entity_type === 'supplier_order' ? '/supplier-orders' : '/preorders'
  const context = [
    item.customer_id !== null ? customerName(item.customer_id) : null,
    item.product_id !== null ? productName(item.product_id) : null,
    item.supplier_id !== null ? supplierName(item.supplier_id) : null,
  ].filter((value): value is string => Boolean(value))

  return (
    <li>
      <Link to={to} className={`queue-row queue-row--${copy.tone}`}>
        <span className="queue-row__tone" aria-hidden="true" />
        <div className="queue-row__main">
          <p className="queue-row__title">{copy.title(item.entity_id)}</p>
          <p className="queue-row__meta">
            <StatusBadge label={copy.badge} tone={copy.tone} />
            {context.length > 0 ? <span>{context.join(' · ')}</span> : null}
          </p>
        </div>
        <div className="queue-row__aside">
          <time dateTime={item.occurred_at}>{formatWhen(item.occurred_at)}</time>
          {item.outstanding_balance !== null ? (
            <span>Outstanding {formatAmount(item.outstanding_balance)}</span>
          ) : null}
        </div>
      </Link>
    </li>
  )
}

function DemandGlance({ analytics }: { analytics: DemandAnalytics }) {
  const overview = analytics.overview
  const topProducts = analytics.products.slice(0, 3)
  const lost = analytics.lost_demand

  return (
    <div className="demand">
      <dl className="demand-stats">
        <div className="mini-stat mini-stat--sky">
          <dt>Total enquiries</dt>
          <dd>{overview.total_enquiries}</dd>
        </div>
        <div className="mini-stat mini-stat--cream">
          <dt>Open</dt>
          <dd>{overview.open_enquiries}</dd>
        </div>
        <div className="mini-stat mini-stat--sage">
          <dt>Converted</dt>
          <dd>{overview.converted_enquiries}</dd>
        </div>
        <div className="mini-stat mini-stat--blush">
          <dt>Lost</dt>
          <dd>{overview.lost_enquiries}</dd>
        </div>
        <div className="mini-stat mini-stat--lavender">
          <dt>Conversion rate</dt>
          <dd>{formatRate(overview.conversion_rate)}</dd>
        </div>
      </dl>

      <div className="demand-block">
        <h3>Top requested products</h3>
        {topProducts.length === 0 ? (
          <p className="muted">No product demand yet.</p>
        ) : (
          <ol className="demand-products">
            {topProducts.map((row, index) => (
              <li key={row.product_id}>
                <span className="demand-products__rank">{index + 1}</span>
                <span className="demand-products__name">{row.name}</span>
                <span className="muted">
                  {row.enquiry_count} enquiries · {row.requested_quantity} requested
                </span>
              </li>
            ))}
          </ol>
        )}
      </div>

      <div className="demand-block">
        <h3>Lost demand</h3>
        {lost.length === 0 ? (
          <p className="muted">No lost-demand reasons recorded.</p>
        ) : (
          <ul className="lost-demand">
            {lost.map((bucket) => (
              <li
                key={bucket.reason}
                className={bucket.count === 0 ? 'lost-demand__item is-muted' : 'lost-demand__item'}
              >
                <span>{LOST_DEMAND_LABELS[bucket.reason]}</span>
                <span>{bucket.count}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
