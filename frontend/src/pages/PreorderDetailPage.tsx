import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { getPreorder } from '../api/resources'
import type {
  Fulfilment,
  Money,
  PaymentSummaryStatus,
  Preorder,
  PreorderStatus,
  Product,
  Supplier,
} from '../api/types'
import { useReferenceData } from '../api/useReferenceData'
import { EmptyState, ErrorState, LoadingState } from '../ui/PageState'
import { StatusBadge, type StatusTone } from '../ui/StatusBadge'

const HAPPY_PATH: PreorderStatus[] = [
  'CONFIRMED',
  'ORDERED_FROM_SUPPLIER',
  'ARRIVED',
  'READY_FOR_CUSTOMER',
  'FULFILLED',
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

function parsePreorderId(value: string | undefined): number | null {
  if (!value) {
    return null
  }
  const id = Number.parseInt(value, 10)
  if (!Number.isInteger(id) || id < 1 || String(id) !== value) {
    return null
  }
  return id
}

function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => {
      reject(new ApiError('The request timed out.', 0))
    }, ms)
    promise.then(
      (next) => {
        window.clearTimeout(timer)
        resolve(next)
      },
      (caught: unknown) => {
        window.clearTimeout(timer)
        reject(caught)
      },
    )
  })
}

function describeError(caught: unknown): { kind: 'not-found' | 'error'; message: string } {
  if (caught instanceof ApiError && caught.status === 404) {
    return { kind: 'not-found', message: 'This preorder does not exist.' }
  }
  if (caught instanceof ApiError && caught.status === 0) {
    return { kind: 'error', message: caught.message }
  }
  return { kind: 'error', message: 'This preorder could not be loaded.' }
}

function orderTotal(quantity: number, agreedPrice: Money | null): string {
  if (agreedPrice === null) {
    return 'Not set'
  }
  const unit = Number(agreedPrice)
  if (!Number.isFinite(unit)) {
    return '—'
  }
  return formatAmount(unit * quantity)
}

function productFacts(product: Product | undefined): { label: string; value: string }[] {
  if (!product) {
    return []
  }
  const facts: { label: string; value: string }[] = []
  if (product.style) {
    facts.push({ label: 'Style', value: product.style })
  }
  if (product.colour) {
    facts.push({ label: 'Colour', value: product.colour })
  }
  if (product.size) {
    facts.push({ label: 'Size', value: product.size })
  }
  return facts
}

type DetailResult =
  | { id: number; tick: number; preorder: Preorder; errorKind: null; message: '' }
  | {
      id: number
      tick: number
      preorder: null
      errorKind: 'not-found' | 'error'
      message: string
    }

export function PreorderDetailPage() {
  const { id } = useParams()
  const preorderId = parsePreorderId(id)
  const reference = useReferenceData()
  const [tick, setTick] = useState(0)
  const [result, setResult] = useState<DetailResult | null>(null)

  const retry = useCallback(() => {
    setTick((value) => value + 1)
  }, [])

  useEffect(() => {
    if (preorderId === null) {
      return
    }
    let cancelled = false
    withTimeout(getPreorder(preorderId), 20000)
      .then((data) => {
        if (!cancelled) {
          setResult({
            id: preorderId,
            tick,
            preorder: data,
            errorKind: null,
            message: '',
          })
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          const described = describeError(caught)
          setResult({
            id: preorderId,
            tick,
            preorder: null,
            errorKind: described.kind,
            message: described.message,
          })
        }
      })
    return () => {
      cancelled = true
    }
  }, [preorderId, tick])

  if (preorderId === null) {
    return (
      <div className="preorder-detail">
        <Link to="/preorders" className="detail-back">
          Back to Preorders
        </Link>
        <section className="panel detail-state">
          <EmptyState
            title="Preorder not found"
            message="This preorder does not exist."
          />
        </section>
      </div>
    )
  }

  const current =
    result && result.id === preorderId && result.tick === tick ? result : null
  const loading = current === null
  const preorder = current?.preorder ?? null
  const errorKind = current?.errorKind ?? null
  const errorMessage = current?.message ?? ''

  if (loading) {
    return (
      <div className="preorder-detail">
        <Link to="/preorders" className="detail-back">
          Back to Preorders
        </Link>
        <section className="panel detail-state">
          <LoadingState message="Loading preorder…" />
        </section>
      </div>
    )
  }

  if (errorKind === 'not-found' || !preorder) {
    return (
      <div className="preorder-detail">
        <Link to="/preorders" className="detail-back">
          Back to Preorders
        </Link>
        <section className="panel detail-state">
          {errorKind === 'error' ? (
            <ErrorState
              title="Preorder could not be loaded"
              message={errorMessage}
              onRetry={retry}
            />
          ) : (
            <EmptyState title="Preorder not found" message={errorMessage} />
          )}
        </section>
      </div>
    )
  }

  const product = reference.productById[preorder.product_id]
  const customer = reference.customerById[preorder.customer_id]
  const supplier: Supplier | undefined = product
    ? reference.supplierById[product.supplier_id]
    : undefined
  const payment = preorder.payment_summary
  const facts = productFacts(product)
  const currentIndex = HAPPY_PATH.indexOf(preorder.status)
  const isTerminalSide =
    preorder.status === 'CANCELLED' || preorder.status === 'SUPPLIER_UNAVAILABLE'

  return (
    <div className="preorder-detail">
      <Link to="/preorders" className="detail-back">
        Back to Preorders
      </Link>

      <header className="detail-header">
        <div>
          <div className="detail-header__title">
            <h1>Preorder #{preorder.id}</h1>
            <StatusBadge
              label={WORKFLOW_LABEL[preorder.status]}
              tone={WORKFLOW_TONE[preorder.status]}
            />
          </div>
          <p>
            {reference.customerName(preorder.customer_id)} ·{' '}
            {reference.productName(preorder.product_id)}
          </p>
        </div>
      </header>

      <div className="detail-grid">
        <section className="panel">
          <h2>Product and order</h2>
          <p className="detail-lead">{reference.productName(preorder.product_id)}</p>
          <dl className="detail-facts">
            <div>
              <dt>Quantity</dt>
              <dd>{preorder.quantity}</dd>
            </div>
            <div>
              <dt>Unit price</dt>
              <dd>
                {preorder.agreed_price === null ? 'Not set' : formatAmount(preorder.agreed_price)}
              </dd>
            </div>
            <div>
              <dt>Order total</dt>
              <dd>{orderTotal(preorder.quantity, preorder.agreed_price)}</dd>
            </div>
            <div>
              <dt>Supplier</dt>
              <dd>
                {product ? reference.supplierName(product.supplier_id) : '—'}
              </dd>
            </div>
            {facts.map((fact) => (
              <div key={fact.label}>
                <dt>{fact.label}</dt>
                <dd>{fact.value}</dd>
              </div>
            ))}
            <div>
              <dt>Updated</dt>
              <dd>{formatWhen(preorder.updated_at)}</dd>
            </div>
          </dl>
        </section>

        <div className="detail-side">
          <section className="panel">
            <h2>Customer</h2>
            <p className="detail-lead">{reference.customerName(preorder.customer_id)}</p>
            <dl className="detail-facts detail-facts--stack">
              <div>
                <dt>Phone</dt>
                <dd>{customer?.phone ?? '—'}</dd>
              </div>
              <div>
                <dt>Facebook name</dt>
                <dd>{customer?.facebook_name ?? '—'}</dd>
              </div>
              {customer?.notes ? (
                <div>
                  <dt>Notes</dt>
                  <dd>{customer.notes}</dd>
                </div>
              ) : null}
            </dl>
          </section>

          <section className="panel">
            <h2>Payment</h2>
            <div className="detail-payment-status">
              {payment.status === null ? (
                <StatusBadge label="Price not set" tone="neutral" />
              ) : (
                <StatusBadge
                  label={PAYMENT_LABEL[payment.status]}
                  tone={PAYMENT_TONE[payment.status]}
                />
              )}
            </div>
            <dl className="detail-facts detail-facts--stack">
              <div>
                <dt>Total due</dt>
                <dd>{payment.total_amount === null ? '—' : formatAmount(payment.total_amount)}</dd>
              </div>
              <div>
                <dt>Amount paid</dt>
                <dd>{formatAmount(payment.amount_paid)}</dd>
              </div>
              <div>
                <dt>Outstanding</dt>
                <dd>
                  {payment.outstanding_balance === null
                    ? '—'
                    : formatAmount(payment.outstanding_balance)}
                </dd>
              </div>
            </dl>
          </section>

          <section className="panel">
            <h2>Supplier</h2>
            <p className="detail-lead">
              {product ? reference.supplierName(product.supplier_id) : '—'}
            </p>
            <dl className="detail-facts detail-facts--stack">
              <div>
                <dt>Contact</dt>
                <dd>{supplier?.contact_name ?? '—'}</dd>
              </div>
              <div>
                <dt>Phone</dt>
                <dd>{supplier?.phone ?? '—'}</dd>
              </div>
              <div>
                <dt>WhatsApp</dt>
                <dd>{supplier?.whatsapp ?? '—'}</dd>
              </div>
              <div>
                <dt>Email</dt>
                <dd>{supplier?.email ?? '—'}</dd>
              </div>
            </dl>
          </section>
        </div>
      </div>

      <section className="panel">
        <h2>Preorder progress</h2>
        <p className="detail-muted">Current workflow state. Transition times are not stored.</p>
        <ol className="progress-steps">
          {HAPPY_PATH.map((step, index) => {
            const state =
              isTerminalSide || currentIndex === -1
                ? 'future'
                : index < currentIndex
                  ? 'done'
                  : index === currentIndex
                    ? 'current'
                    : 'future'
            return (
              <li key={step} className={`progress-step is-${state}`}>
                <span>{WORKFLOW_LABEL[step]}</span>
              </li>
            )
          })}
        </ol>
        {isTerminalSide ? (
          <p className="progress-outcome">
            Ended as {WORKFLOW_LABEL[preorder.status]}. The happy path did not continue.
          </p>
        ) : null}
      </section>

      {preorder.fulfilment ? <FulfilmentCard fulfilment={preorder.fulfilment} /> : null}

      {preorder.notes ? (
        <section className="panel">
          <h2>Notes</h2>
          <p className="detail-notes">{preorder.notes}</p>
        </section>
      ) : null}
    </div>
  )
}

function FulfilmentCard({ fulfilment }: { fulfilment: Fulfilment }) {
  const isPost = fulfilment.method === 'POST'
  return (
    <section className="panel">
      <h2>Fulfilment</h2>
      <dl className="detail-facts">
        <div>
          <dt>Method</dt>
          <dd>{fulfilment.method === 'HOME_COLLECTION' ? 'Home collection' : 'Post'}</dd>
        </div>
        {isPost ? (
          <div>
            <dt>Postage</dt>
            <dd>{fulfilment.postage_type === 'REGISTERED' ? 'Registered' : 'Regular'}</dd>
          </div>
        ) : null}
        {isPost && fulfilment.delivery_address ? (
          <div className="detail-facts__wide">
            <dt>Delivery address</dt>
            <dd>{fulfilment.delivery_address}</dd>
          </div>
        ) : null}
        {isPost && fulfilment.postage_cost !== null ? (
          <div>
            <dt>Postage cost</dt>
            <dd>{formatAmount(fulfilment.postage_cost)}</dd>
          </div>
        ) : null}
        {isPost && fulfilment.postage_type === 'REGISTERED' && fulfilment.tracking_reference ? (
          <div className="detail-facts__wide">
            <dt>Tracking reference</dt>
            <dd>{fulfilment.tracking_reference}</dd>
          </div>
        ) : null}
        <div>
          <dt>Fulfilled</dt>
          <dd>{formatWhen(fulfilment.fulfilled_at)}</dd>
        </div>
        {fulfilment.notes ? (
          <div className="detail-facts__wide">
            <dt>Notes</dt>
            <dd>{fulfilment.notes}</dd>
          </div>
        ) : null}
      </dl>
    </section>
  )
}
