import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import {
  getSupplierOrder,
  placeSupplierOrder,
  reconcileSupplierOrder,
  transitionSupplierOrder,
} from '../api/resources'
import type {
  SupplierOrder,
  SupplierOrderLine,
  SupplierOrderReconcile,
  SupplierOrderStatus,
  SupplierOrderTransitionStatus,
} from '../api/types'
import { useReferenceData } from '../api/useReferenceData'
import { EmptyState, ErrorState, LoadingState } from '../ui/PageState'
import { StatusBadge, type StatusTone } from '../ui/StatusBadge'

const HAPPY_PATH: SupplierOrderStatus[] = [
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

type DetailResult =
  | { id: number; tick: number; order: SupplierOrder; errorKind: null; message: '' }
  | {
      id: number
      tick: number
      order: null
      errorKind: 'not-found' | 'error'
      message: string
    }

function parseOrderId(value: string | undefined): number | null {
  if (!value) {
    return null
  }
  const id = Number.parseInt(value, 10)
  if (!Number.isInteger(id) || id < 1 || String(id) !== value) {
    return null
  }
  return id
}

function formatWhen(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
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
  if (caught instanceof ApiError && caught.status === 404) {
    return caught.message
  }
  if (caught instanceof ApiError && caught.status === 422) {
    return 'The request was not valid.'
  }
  return 'This action could not be completed.'
}

function describeLoadError(caught: unknown): {
  kind: 'not-found' | 'error'
  message: string
} {
  if (caught instanceof ApiError && caught.status === 404) {
    return { kind: 'not-found', message: 'This supplier order does not exist.' }
  }
  if (caught instanceof ApiError) {
    return { kind: 'error', message: caught.message }
  }
  return { kind: 'error', message: 'This supplier order could not be loaded.' }
}

export function SupplierOrderDetailPage() {
  const { id } = useParams()
  const orderId = parseOrderId(id)
  const reference = useReferenceData()
  const [tick, setTick] = useState(0)
  const [result, setResult] = useState<DetailResult | null>(null)
  const [mutating, setMutating] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [panel, setPanel] = useState<'none' | 'reconcile'>('none')
  const [successNotice, setSuccessNotice] = useState<string | null>(null)
  const actionLock = useRef(false)

  const retry = useCallback(() => {
    setActionError(null)
    setTick((value) => value + 1)
  }, [])

  const applyOrder = useCallback(
    (data: SupplierOrder) => {
      if (orderId === null) {
        return
      }
      setResult({
        id: orderId,
        tick,
        order: data,
        errorKind: null,
        message: '',
      })
    },
    [orderId, tick],
  )

  const runPlace = useCallback(async () => {
    if (orderId === null || actionLock.current) {
      return
    }
    if (
      !window.confirm(
        'Place this supplier order? Allocated preorders will move to ordered from supplier.',
      )
    ) {
      return
    }
    actionLock.current = true
    setMutating(true)
    setActionError(null)
    setSuccessNotice(null)
    try {
      const data = await withTimeout(placeSupplierOrder(orderId), 20000)
      applyOrder(data)
      setSuccessNotice('Supplier order placed.')
    } catch (caught: unknown) {
      setActionError(describeActionError(caught))
    } finally {
      actionLock.current = false
      setMutating(false)
    }
  }, [applyOrder, orderId])

  const runTransition = useCallback(
    async (status: SupplierOrderTransitionStatus) => {
      if (orderId === null || actionLock.current) {
        return
      }
      actionLock.current = true
      setMutating(true)
      setActionError(null)
      setSuccessNotice(null)
      try {
        const data = await withTimeout(transitionSupplierOrder(orderId, status), 20000)
        applyOrder(data)
      } catch (caught: unknown) {
        setActionError(describeActionError(caught))
      } finally {
        actionLock.current = false
        setMutating(false)
      }
    },
    [applyOrder, orderId],
  )

  const runReconcile = useCallback(
    async (payload: SupplierOrderReconcile) => {
      if (orderId === null || actionLock.current) {
        return
      }
      actionLock.current = true
      setMutating(true)
      setActionError(null)
      setSuccessNotice(null)
      try {
        const data = await withTimeout(reconcileSupplierOrder(orderId, payload), 20000)
        applyOrder(data)
        setPanel('none')
        setSuccessNotice('Delivery reconciled. Resulting stock is recorded by the backend.')
      } catch (caught: unknown) {
        setActionError(describeActionError(caught))
      } finally {
        actionLock.current = false
        setMutating(false)
      }
    },
    [applyOrder, orderId],
  )

  useEffect(() => {
    if (orderId === null) {
      return
    }
    let cancelled = false
    withTimeout(getSupplierOrder(orderId), 20000)
      .then((data) => {
        if (!cancelled) {
          setResult({
            id: orderId,
            tick,
            order: data,
            errorKind: null,
            message: '',
          })
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          const described = describeLoadError(caught)
          setResult({
            id: orderId,
            tick,
            order: null,
            errorKind: described.kind,
            message: described.message,
          })
        }
      })
    return () => {
      cancelled = true
    }
  }, [orderId, tick])

  if (orderId === null) {
    return (
      <div className="preorder-detail supplier-order-detail">
        <Link to="/supplier-orders" className="detail-back">
          Back to Supplier Orders
        </Link>
        <section className="panel detail-state">
          <EmptyState
            title="Supplier order not found"
            message="This supplier order does not exist."
          />
        </section>
      </div>
    )
  }

  const current = result && result.id === orderId && result.tick === tick ? result : null
  const loading = current === null
  const order = current?.order ?? null
  const errorKind = current?.errorKind ?? null
  const errorMessage = current?.message ?? ''

  if (loading) {
    return (
      <div className="preorder-detail supplier-order-detail">
        <Link to="/supplier-orders" className="detail-back">
          Back to Supplier Orders
        </Link>
        <section className="panel detail-state">
          <LoadingState message="Loading supplier order…" />
        </section>
      </div>
    )
  }

  if (errorKind === 'not-found' || !order) {
    return (
      <div className="preorder-detail supplier-order-detail">
        <Link to="/supplier-orders" className="detail-back">
          Back to Supplier Orders
        </Link>
        <section className="panel detail-state">
          {errorKind === 'error' ? (
            <ErrorState
              title="Supplier order could not be loaded"
              message={errorMessage}
              onRetry={retry}
            />
          ) : (
            <EmptyState title="Supplier order not found" message={errorMessage} />
          )}
        </section>
      </div>
    )
  }

  const currentIndex = HAPPY_PATH.indexOf(order.status)
  const orderedUnits = order.lines.reduce((sum, line) => sum + line.quantity, 0)

  return (
    <div className="preorder-detail supplier-order-detail">
      <Link to="/supplier-orders" className="detail-back">
        Back to Supplier Orders
      </Link>

      <header className="detail-header">
        <div>
          <div className="detail-header__title">
            <h1>Supplier Order #{order.id}</h1>
            <StatusBadge label={STATUS_LABEL[order.status]} tone={STATUS_TONE[order.status]} />
          </div>
          <p>{reference.supplierName(order.supplier_id)}</p>
        </div>
      </header>

      <OrderActions
        order={order}
        busy={mutating}
        error={panel === 'none' ? actionError : null}
        onPlace={runPlace}
        onTransition={runTransition}
        onOpenReconcile={() => {
          setActionError(null)
          setPanel(panel === 'reconcile' ? 'none' : 'reconcile')
        }}
      />

      {successNotice && panel === 'none' ? <p className="ops-notice">{successNotice}</p> : null}

      {panel === 'reconcile' && order.status === 'ARRIVED' ? (
        <ReconcileForm
          lines={order.lines}
          busy={mutating}
          error={actionError}
          onCancel={() => setPanel('none')}
          onSubmit={runReconcile}
        />
      ) : null}

      <div className="detail-grid">
        <section className="panel">
          <h2>Order overview</h2>
          <dl className="detail-facts">
            <div>
              <dt>Supplier</dt>
              <dd>{reference.supplierName(order.supplier_id)}</dd>
            </div>
            <div>
              <dt>Status</dt>
              <dd>{STATUS_LABEL[order.status]}</dd>
            </div>
            <div>
              <dt>Lines</dt>
              <dd>{order.lines.length}</dd>
            </div>
            <div>
              <dt>Ordered units</dt>
              <dd>{orderedUnits}</dd>
            </div>
            <div>
              <dt>Created</dt>
              <dd>{formatWhen(order.created_at)}</dd>
            </div>
            <div>
              <dt>Updated</dt>
              <dd>{formatWhen(order.updated_at)}</dd>
            </div>
            {order.placed_at ? (
              <div>
                <dt>Placed</dt>
                <dd>{formatWhen(order.placed_at)}</dd>
              </div>
            ) : null}
            {order.reconciled_at ? (
              <div>
                <dt>Reconciled</dt>
                <dd>{formatWhen(order.reconciled_at)}</dd>
              </div>
            ) : null}
          </dl>
          {order.notes ? <p className="detail-notes">{order.notes}</p> : null}
          {order.reconciliation_notes ? (
            <p className="detail-notes">{order.reconciliation_notes}</p>
          ) : null}
        </section>

        <section className="panel">
          <h2>Supplier order progress</h2>
          <p className="detail-muted">Current workflow state. Transition times are not stored.</p>
          <ol className="progress-steps">
            {HAPPY_PATH.map((step, index) => {
              const state =
                currentIndex === -1
                  ? 'future'
                  : index < currentIndex
                    ? 'done'
                    : index === currentIndex
                      ? 'current'
                      : 'future'
              return (
                <li key={step} className={`progress-step is-${state}`}>
                  <span>{STATUS_LABEL[step]}</span>
                </li>
              )
            })}
          </ol>
        </section>
      </div>

      <section className="panel">
        <h2>Lines</h2>
        <p className="detail-muted">
          Quantities are consolidated by product. Allocations keep the customer commitments.
        </p>
        {order.lines.length === 0 ? (
          <p className="detail-muted">This order has no lines.</p>
        ) : (
          order.lines.map((line) => (
            <article key={line.id} className="line-block">
              <dl className="detail-facts">
                <div className="detail-facts__wide">
                  <dt>Product</dt>
                  <dd>{reference.productName(line.product_id)}</dd>
                </div>
                <div>
                  <dt>Ordered</dt>
                  <dd>{line.quantity}</dd>
                </div>
                <div>
                  <dt>Received</dt>
                  <dd>{line.received_quantity === null ? '—' : line.received_quantity}</dd>
                </div>
                {line.unit_cost !== null ? (
                  <div>
                    <dt>Unit cost</dt>
                    <dd>{String(line.unit_cost)}</dd>
                  </div>
                ) : null}
                {line.notes ? (
                  <div className="detail-facts__wide">
                    <dt>Line notes</dt>
                    <dd>{line.notes}</dd>
                  </div>
                ) : null}
              </dl>
              <h3 className="line-block__heading">Allocations</h3>
              {line.allocations.length === 0 ? (
                <p className="detail-muted">No allocations on this line.</p>
              ) : (
                <div className="table-wrap">
                  <table className="data-table data-table--nested">
                    <thead>
                      <tr>
                        <th>Preorder</th>
                        <th>Allocated qty</th>
                      </tr>
                    </thead>
                    <tbody>
                      {line.allocations.map((allocation) => (
                        <tr key={allocation.id}>
                          <td>
                            <Link to={`/preorders/${allocation.preorder_id}`}>
                              #{allocation.preorder_id}
                            </Link>
                          </td>
                          <td>{allocation.quantity}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </article>
          ))
        )}
      </section>
    </div>
  )
}

function OrderActions({
  order,
  busy,
  error,
  onPlace,
  onTransition,
  onOpenReconcile,
}: {
  order: SupplierOrder
  busy: boolean
  error: string | null
  onPlace: () => void
  onTransition: (status: SupplierOrderTransitionStatus) => void
  onOpenReconcile: () => void
}) {
  const status = order.status
  const hint =
    status === 'DRAFT'
      ? 'Placement is recorded with the dedicated place operation.'
      : status === 'ARRIVED'
        ? 'Reconciliation records what physically arrived.'
        : status === 'RECONCILED'
          ? 'This supplier order is reconciled.'
          : null

  const canPlace = status === 'DRAFT'
  const canConfirm = status === 'PLACED'
  const canDispatch = status === 'CONFIRMED'
  const canArrive = status === 'DISPATCHED'
  const canReconcile = status === 'ARRIVED'
  const hasButtons = canPlace || canConfirm || canDispatch || canArrive || canReconcile

  return (
    <section className="panel detail-actions" aria-label="Supplier order actions">
      {hint ? <p className="detail-muted">{hint}</p> : null}
      {hasButtons ? (
        <div className="detail-actions__row">
          {canPlace ? (
            <button
              type="button"
              className="action-btn action-btn--primary"
              disabled={busy}
              onClick={onPlace}
            >
              Place supplier order
            </button>
          ) : null}
          {canConfirm ? (
            <button
              type="button"
              className="action-btn action-btn--primary"
              disabled={busy}
              onClick={() => onTransition('CONFIRMED')}
            >
              Confirm supplier order
            </button>
          ) : null}
          {canDispatch ? (
            <button
              type="button"
              className="action-btn action-btn--primary"
              disabled={busy}
              onClick={() => onTransition('DISPATCHED')}
            >
              Mark dispatched
            </button>
          ) : null}
          {canArrive ? (
            <button
              type="button"
              className="action-btn action-btn--primary"
              disabled={busy}
              onClick={() => onTransition('ARRIVED')}
            >
              Mark arrived
            </button>
          ) : null}
          {canReconcile ? (
            <button
              type="button"
              className="action-btn action-btn--primary"
              disabled={busy}
              onClick={onOpenReconcile}
            >
              Reconcile delivery
            </button>
          ) : null}
        </div>
      ) : null}
      {error ? <p className="detail-action-error">{error}</p> : null}
    </section>
  )
}

function ReconcileForm({
  lines,
  busy,
  error,
  onCancel,
  onSubmit,
}: {
  lines: SupplierOrderLine[]
  busy: boolean
  error: string | null
  onCancel: () => void
  onSubmit: (payload: SupplierOrderReconcile) => void
}) {
  const reference = useReferenceData()
  const [received, setReceived] = useState<Record<number, string>>(() => {
    const initial: Record<number, string> = {}
    for (const line of lines) {
      initial[line.id] = ''
    }
    return initial
  })
  const [notes, setNotes] = useState('')

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (busy) {
      return
    }
    if (
      !window.confirm(
        'Reconciliation records what physically arrived and cannot be edited in v1.',
      )
    ) {
      return
    }
    const payload: SupplierOrderReconcile = {
      lines: lines.map((line) => ({
        line_id: line.id,
        received_quantity: Number(received[line.id]),
      })),
    }
    if (notes.trim()) {
      payload.reconciliation_notes = notes.trim()
    }
    onSubmit(payload)
  }

  return (
    <section className="panel">
      <h2>Reconcile delivery</h2>
      <p className="detail-muted">
        Enter received quantities for every line. Shortages, filled preorders, and surplus stock
        are decided by the backend.
      </p>
      <form className="ops-form" onSubmit={handleSubmit}>
        {lines.map((line) => (
          <div key={line.id} className="ops-form__wide reconcile-line">
            <div>
              <p className="cell-primary">{reference.productName(line.product_id)}</p>
              <p className="cell-meta">Ordered {line.quantity}</p>
            </div>
            <label>
              Received quantity
              <input
                required
                type="number"
                min="0"
                step="1"
                value={received[line.id] ?? ''}
                disabled={busy}
                onChange={(event) =>
                  setReceived((current) => ({
                    ...current,
                    [line.id]: event.target.value,
                  }))
                }
              />
            </label>
          </div>
        ))}
        <label className="ops-form__wide">
          Reconciliation notes
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
            Confirm reconciliation
          </button>
          <button type="button" className="action-btn" disabled={busy} onClick={onCancel}>
            Cancel
          </button>
        </div>
      </form>
    </section>
  )
}
