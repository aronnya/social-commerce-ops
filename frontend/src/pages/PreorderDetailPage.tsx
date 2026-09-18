import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { getPreorder, createPayment, fulfilPreorder, transitionPreorder } from '../api/resources'
import type {
  Fulfilment,
  FulfilmentCreate,
  FulfilmentMethod,
  Money,
  PaymentCreate,
  PaymentMethod,
  PaymentSummaryStatus,
  PostageType,
  Preorder,
  PreorderStatus,
  PreorderTransitionStatus,
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

function describeActionError(caught: unknown): string {
  if (caught instanceof ApiError && caught.status === 409) {
    return caught.message
  }
  if (caught instanceof ApiError && caught.status === 0) {
    return caught.message
  }
  if (caught instanceof ApiError && caught.status === 422) {
    return 'The request was not valid.'
  }
  return 'This action could not be completed.'
}

function confirmTerminal(preorderId: number, action: 'cancel' | 'unavailable'): boolean {
  if (action === 'cancel') {
    return window.confirm(`Cancel preorder #${preorderId}?`)
  }
  return window.confirm(`Mark preorder #${preorderId} as supplier unavailable?`)
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
  const [mutating, setMutating] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [panel, setPanel] = useState<'none' | 'fulfil' | 'payment'>('none')
  const actionLock = useRef(false)

  const retry = useCallback(() => {
    setActionError(null)
    setTick((value) => value + 1)
  }, [])

  const runTransition = useCallback(
    async (status: PreorderTransitionStatus, terminal?: 'cancel' | 'unavailable') => {
      if (preorderId === null || actionLock.current) {
        return
      }
      if (terminal && !confirmTerminal(preorderId, terminal)) {
        return
      }
      actionLock.current = true
      setMutating(true)
      setActionError(null)
      try {
        const data = await withTimeout(transitionPreorder(preorderId, status), 20000)
        setResult({
          id: preorderId,
          tick,
          preorder: data,
          errorKind: null,
          message: '',
        })
      } catch (caught: unknown) {
        setActionError(describeActionError(caught))
      } finally {
        actionLock.current = false
        setMutating(false)
      }
    },
    [preorderId, tick],
  )

  const runFulfil = useCallback(
    async (payload: FulfilmentCreate) => {
      if (preorderId === null || actionLock.current) {
        return
      }
      actionLock.current = true
      setMutating(true)
      setActionError(null)
      try {
        const data = await withTimeout(fulfilPreorder(preorderId, payload), 20000)
        setResult({
          id: preorderId,
          tick,
          preorder: data,
          errorKind: null,
          message: '',
        })
        setPanel('none')
      } catch (caught: unknown) {
        setActionError(describeActionError(caught))
      } finally {
        actionLock.current = false
        setMutating(false)
      }
    },
    [preorderId, tick],
  )

  const runPayment = useCallback(
    async (payload: PaymentCreate) => {
      if (preorderId === null || actionLock.current) {
        return
      }
      actionLock.current = true
      setMutating(true)
      setActionError(null)
      try {
        await withTimeout(createPayment(preorderId, payload), 20000)
        const data = await withTimeout(getPreorder(preorderId), 20000)
        setResult({
          id: preorderId,
          tick,
          preorder: data,
          errorKind: null,
          message: '',
        })
        setPanel('none')
      } catch (caught: unknown) {
        setActionError(describeActionError(caught))
      } finally {
        actionLock.current = false
        setMutating(false)
      }
    },
    [preorderId, tick],
  )

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

      <PreorderActions
        preorder={preorder}
        busy={mutating}
        error={panel === 'none' ? actionError : null}
        onTransition={runTransition}
        onOpenFulfil={() => {
          setActionError(null)
          setPanel(panel === 'fulfil' ? 'none' : 'fulfil')
        }}
        onOpenPayment={() => {
          setActionError(null)
          setPanel(panel === 'payment' ? 'none' : 'payment')
        }}
      />

      {panel === 'fulfil' && preorder.status === 'READY_FOR_CUSTOMER' ? (
        <FulfilmentForm
          busy={mutating}
          error={actionError}
          onCancel={() => setPanel('none')}
          onSubmit={runFulfil}
        />
      ) : null}

      {panel === 'payment' ? (
        <PaymentForm
          busy={mutating}
          error={actionError}
          outstanding={preorder.payment_summary.outstanding_balance}
          priceSet={preorder.agreed_price !== null}
          onCancel={() => setPanel('none')}
          onSubmit={runPayment}
        />
      ) : null}

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

function PreorderActions({
  preorder,
  busy,
  error,
  onTransition,
  onOpenFulfil,
  onOpenPayment,
}: {
  preorder: Preorder
  busy: boolean
  error: string | null
  onTransition: (
    status: PreorderTransitionStatus,
    terminal?: 'cancel' | 'unavailable',
  ) => void
  onOpenFulfil: () => void
  onOpenPayment: () => void
}) {
  const status = preorder.status
  const hint =
    status === 'CONFIRMED'
      ? 'Supplier ordering is managed through Supplier Orders.'
      : status === 'ORDERED_FROM_SUPPLIER'
        ? 'Arrival is recorded during supplier reconciliation.'
        : status === 'READY_FOR_CUSTOMER'
          ? 'Fulfilment is recorded with a dedicated fulfilment step.'
          : status === 'FULFILLED'
            ? 'This preorder is complete.'
            : status === 'CANCELLED'
              ? 'This preorder is cancelled.'
              : status === 'SUPPLIER_UNAVAILABLE'
                ? 'This preorder is marked supplier unavailable.'
                : null

  const canReady = status === 'ARRIVED'
  const canFulfil = status === 'READY_FOR_CUSTOMER'
  const canCancel =
    status === 'CONFIRMED' ||
    status === 'ORDERED_FROM_SUPPLIER' ||
    status === 'READY_FOR_CUSTOMER'
  const canUnavailable =
    status === 'CONFIRMED' || status === 'ORDERED_FROM_SUPPLIER' || status === 'ARRIVED'
  const canPay = true
  const hasButtons = canReady || canFulfil || canCancel || canUnavailable || canPay

  return (
    <section className="panel detail-actions" aria-label="Preorder actions">
      {hint ? <p className="detail-muted">{hint}</p> : null}
      {hasButtons ? (
        <div className="detail-actions__row">
          {canFulfil ? (
            <button
              type="button"
              className="action-btn action-btn--primary"
              disabled={busy}
              onClick={onOpenFulfil}
            >
              Fulfil preorder
            </button>
          ) : null}
          {canReady ? (
            <button
              type="button"
              className="action-btn action-btn--primary"
              disabled={busy}
              onClick={() => onTransition('READY_FOR_CUSTOMER')}
            >
              Mark ready for customer
            </button>
          ) : null}
          {canPay ? (
            <button
              type="button"
              className="action-btn"
              disabled={busy}
              onClick={onOpenPayment}
            >
              Record payment
            </button>
          ) : null}
          {canCancel ? (
            <button
              type="button"
              className="action-btn action-btn--danger"
              disabled={busy}
              onClick={() => onTransition('CANCELLED', 'cancel')}
            >
              Cancel preorder
            </button>
          ) : null}
          {canUnavailable ? (
            <button
              type="button"
              className="action-btn action-btn--danger"
              disabled={busy}
              onClick={() => onTransition('SUPPLIER_UNAVAILABLE', 'unavailable')}
            >
              Supplier unavailable
            </button>
          ) : null}
        </div>
      ) : null}
      {error ? <p className="detail-action-error">{error}</p> : null}
    </section>
  )
}

function FulfilmentForm({
  busy,
  error,
  onCancel,
  onSubmit,
}: {
  busy: boolean
  error: string | null
  onCancel: () => void
  onSubmit: (payload: FulfilmentCreate) => void
}) {
  const [method, setMethod] = useState<FulfilmentMethod>('HOME_COLLECTION')
  const [postageType, setPostageType] = useState<PostageType>('REGULAR')
  const [address, setAddress] = useState('')
  const [tracking, setTracking] = useState('')
  const [postageCost, setPostageCost] = useState('')
  const [notes, setNotes] = useState('')

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (busy) {
      return
    }
    if (method === 'HOME_COLLECTION') {
      onSubmit({
        method: 'HOME_COLLECTION',
        notes: notes.trim() ? notes.trim() : null,
      })
      return
    }
    const payload: FulfilmentCreate = {
      method: 'POST',
      postage_type: postageType,
      delivery_address: address.trim(),
      notes: notes.trim() ? notes.trim() : null,
    }
    if (postageCost.trim()) {
      payload.postage_cost = postageCost.trim()
    }
    if (postageType === 'REGISTERED') {
      payload.tracking_reference = tracking.trim()
    }
    onSubmit(payload)
  }

  return (
    <section className="panel">
      <h2>Fulfil preorder</h2>
      <form className="ops-form" onSubmit={handleSubmit}>
        <label>
          Method
          <select
            value={method}
            disabled={busy}
            onChange={(event) => setMethod(event.target.value as FulfilmentMethod)}
          >
            <option value="HOME_COLLECTION">Home collection</option>
            <option value="POST">Post</option>
          </select>
        </label>
        {method === 'POST' ? (
          <>
            <label>
              Postage type
              <select
                value={postageType}
                disabled={busy}
                onChange={(event) => setPostageType(event.target.value as PostageType)}
              >
                <option value="REGULAR">Regular</option>
                <option value="REGISTERED">Registered</option>
              </select>
            </label>
            <label className="ops-form__wide">
              Delivery address
              <textarea
                required
                rows={3}
                value={address}
                disabled={busy}
                onChange={(event) => setAddress(event.target.value)}
              />
            </label>
            {postageType === 'REGISTERED' ? (
              <label className="ops-form__wide">
                Tracking reference
                <input
                  required
                  value={tracking}
                  disabled={busy}
                  onChange={(event) => setTracking(event.target.value)}
                />
              </label>
            ) : null}
            <label>
              Postage cost
              <input
                type="number"
                min="0"
                step="0.01"
                value={postageCost}
                disabled={busy}
                onChange={(event) => setPostageCost(event.target.value)}
              />
            </label>
          </>
        ) : null}
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
        <div className="detail-actions__row">
          <button type="submit" className="action-btn action-btn--primary" disabled={busy}>
            Confirm fulfilment
          </button>
          <button type="button" className="action-btn" disabled={busy} onClick={onCancel}>
            Cancel
          </button>
        </div>
      </form>
    </section>
  )
}

function PaymentForm({
  busy,
  error,
  outstanding,
  priceSet,
  onCancel,
  onSubmit,
}: {
  busy: boolean
  error: string | null
  outstanding: Money | null
  priceSet: boolean
  onCancel: () => void
  onSubmit: (payload: PaymentCreate) => void
}) {
  const [amount, setAmount] = useState('')
  const [method, setMethod] = useState<PaymentMethod>('BANK_TRANSFER')
  const [reference, setReference] = useState('')
  const [paidAt, setPaidAt] = useState('')
  const [notes, setNotes] = useState('')
  const amountNumber = Number(amount)
  const outstandingNumber = outstanding === null ? null : Number(outstanding)
  const overpay =
    priceSet &&
    Number.isFinite(amountNumber) &&
    outstandingNumber !== null &&
    Number.isFinite(outstandingNumber) &&
    amountNumber > outstandingNumber

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (busy) {
      return
    }
    const payload: PaymentCreate = {
      amount: amount.trim(),
      method,
    }
    if (reference.trim()) {
      payload.reference = reference.trim()
    }
    if (notes.trim()) {
      payload.notes = notes.trim()
    }
    if (paidAt.trim()) {
      const parsed = new Date(paidAt)
      if (!Number.isNaN(parsed.getTime())) {
        payload.paid_at = parsed.toISOString()
      }
    }
    onSubmit(payload)
  }

  return (
    <section className="panel">
      <h2>Record payment</h2>
      {!priceSet ? (
        <p className="detail-muted">Set agreed price on the preorder before recording a payment.</p>
      ) : null}
      <form className="ops-form" onSubmit={handleSubmit}>
        <label>
          Amount
          <input
            required
            type="number"
            min="0.01"
            step="0.01"
            value={amount}
            disabled={busy || !priceSet}
            onChange={(event) => setAmount(event.target.value)}
          />
        </label>
        <label>
          Method
          <select
            value={method}
            disabled={busy || !priceSet}
            onChange={(event) => setMethod(event.target.value as PaymentMethod)}
          >
            <option value="BANK_TRANSFER">Bank transfer</option>
            <option value="REVOLUT">Revolut</option>
          </select>
        </label>
        <label>
          Paid at
          <input
            type="datetime-local"
            value={paidAt}
            disabled={busy || !priceSet}
            onChange={(event) => setPaidAt(event.target.value)}
          />
        </label>
        <label>
          Reference
          <input
            value={reference}
            disabled={busy || !priceSet}
            onChange={(event) => setReference(event.target.value)}
          />
        </label>
        <label className="ops-form__wide">
          Notes
          <textarea
            rows={2}
            value={notes}
            disabled={busy || !priceSet}
            onChange={(event) => setNotes(event.target.value)}
          />
        </label>
        {overpay ? (
          <p className="detail-muted">
            This amount is more than the current outstanding balance. Overpayment is allowed.
          </p>
        ) : null}
        {error ? <p className="detail-action-error">{error}</p> : null}
        <div className="detail-actions__row">
          <button
            type="submit"
            className="action-btn action-btn--primary"
            disabled={busy || !priceSet}
          >
            Save payment
          </button>
          <button type="button" className="action-btn" disabled={busy} onClick={onCancel}>
            Cancel
          </button>
        </div>
      </form>
    </section>
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
