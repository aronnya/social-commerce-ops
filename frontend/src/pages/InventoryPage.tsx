import { useCallback, useEffect, useMemo, useState } from 'react'
import { ApiError } from '../api/client'
import { getInventory } from '../api/resources'
import type { InventoryLot } from '../api/types'
import { useReferenceData } from '../api/useReferenceData'
import { EmptyState, ErrorState, LoadingState } from '../ui/PageState'
import { StatusBadge } from '../ui/StatusBadge'

const PAGE_SIZE = 10

type OriginFilter = 'ALL' | 'RECONCILED' | 'UNLINKED'

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

export function InventoryPage() {
  const reference = useReferenceData()
  const [tick, setTick] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lots, setLots] = useState<InventoryLot[]>([])
  const [query, setQuery] = useState('')
  const [originFilter, setOriginFilter] = useState<OriginFilter>('ALL')
  const [supplierFilter, setSupplierFilter] = useState('ALL')
  const [page, setPage] = useState(1)
  const [pageFilterKey, setPageFilterKey] = useState('')

  const retry = useCallback(() => {
    setLoading(true)
    setError(null)
    setTick((value) => value + 1)
  }, [])

  useEffect(() => {
    let cancelled = false
    withTimeout(getInventory(), 20000)
      .then((data) => {
        if (!cancelled) {
          setLots(data)
          setLoading(false)
          setError(null)
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setLots([])
          setLoading(false)
          setError(errorMessage(caught))
        }
      })
    return () => {
      cancelled = true
    }
  }, [tick])

  const counts = useMemo(() => {
    let units = 0
    let reconciled = 0
    let unlinked = 0
    for (const lot of lots) {
      units += lot.quantity_on_hand
      if (lot.supplier_order_line_id === null) {
        unlinked += 1
      } else {
        reconciled += 1
      }
    }
    return { units, reconciled, unlinked }
  }, [lots])

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return lots.filter((lot) => {
      if (originFilter === 'RECONCILED' && lot.supplier_order_line_id === null) {
        return false
      }
      if (originFilter === 'UNLINKED' && lot.supplier_order_line_id !== null) {
        return false
      }
      const product = reference.productById[lot.product_id]
      if (supplierFilter !== 'ALL' && product?.supplier_id !== Number(supplierFilter)) {
        return false
      }
      if (!needle) {
        return true
      }
      const haystack = [
        `#${lot.id}`,
        String(lot.id),
        reference.productName(lot.product_id),
        product ? reference.supplierName(product.supplier_id) : '',
        lot.supplier_order_line_id === null ? 'unlinked' : `line ${lot.supplier_order_line_id}`,
      ]
        .join(' ')
        .toLowerCase()
      return haystack.includes(needle)
    })
  }, [lots, originFilter, query, reference, supplierFilter])

  const filterKey = `${originFilter}|${supplierFilter}|${query}`
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

  return (
    <div className="preorders inventory">
      <header className="list-header">
        <div className="page-header">
          <h1>Inventory</h1>
          <p>
            Stock physically owned by the business. Catalogue products are not owned stock, and
            surplus lots appear here after supplier-order reconciliation.
          </p>
        </div>
      </header>

      <section className="preorder-cards enquiry-cards" aria-label="Inventory summary">
        <button
          type="button"
          className={`dash-card dash-card--sky${originFilter === 'ALL' ? ' is-selected' : ''}`}
          onClick={() => setOriginFilter('ALL')}
        >
          <span className="dash-card__count">{loading ? '…' : error ? '—' : lots.length}</span>
          <span className="dash-card__label">Lots</span>
          <span className="dash-card__hint">Owned inventory lots</span>
        </button>
        <div className="dash-card dash-card--cream dash-card--static">
          <span className="dash-card__count">{loading ? '…' : error ? '—' : counts.units}</span>
          <span className="dash-card__label">Units on hand</span>
          <span className="dash-card__hint">Sum of lot quantities</span>
        </div>
        <button
          type="button"
          className={`dash-card dash-card--sage${originFilter === 'RECONCILED' ? ' is-selected' : ''}`}
          onClick={() => setOriginFilter('RECONCILED')}
        >
          <span className="dash-card__count">{loading ? '…' : error ? '—' : counts.reconciled}</span>
          <span className="dash-card__label">From supplier orders</span>
          <span className="dash-card__hint">Linked to a reconciled line</span>
        </button>
        <button
          type="button"
          className={`dash-card dash-card--lavender${originFilter === 'UNLINKED' ? ' is-selected' : ''}`}
          onClick={() => setOriginFilter('UNLINKED')}
        >
          <span className="dash-card__count">{loading ? '…' : error ? '—' : counts.unlinked}</span>
          <span className="dash-card__label">Unlinked lots</span>
          <span className="dash-card__hint">No supplier-order line</span>
        </button>
      </section>

      <section className="panel preorder-panel">
        <div className="preorder-toolbar">
          <label className="preorder-search">
            <span className="visually-hidden">Search inventory</span>
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search owned stock..."
            />
          </label>
          <label>
            <span className="visually-hidden">Origin</span>
            <select
              value={originFilter}
              onChange={(event) => setOriginFilter(event.target.value as OriginFilter)}
            >
              <option value="ALL">All lots</option>
              <option value="RECONCILED">From supplier orders</option>
              <option value="UNLINKED">Unlinked lots</option>
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
          <LoadingState message="Loading inventory…" />
        ) : error ? (
          <ErrorState title="Inventory could not be loaded" message={error} onRetry={retry} />
        ) : lots.length === 0 ? (
          <EmptyState
            title="No owned stock yet"
            message="Inventory lots are created when reconciliation records surplus units. There is no generic add-stock action in v1."
          />
        ) : filtered.length === 0 ? (
          <EmptyState title="No matching lots" message="No inventory lots match these filters." />
        ) : (
          <>
            <div className="table-wrap">
              <table className="data-table data-table--inventory">
                <thead>
                  <tr>
                    <th>Lot</th>
                    <th>Product</th>
                    <th>Supplier</th>
                    <th>On hand</th>
                    <th>Origin</th>
                    <th>Created</th>
                    <th>Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {pageRows.map((lot) => {
                    const product = reference.productById[lot.product_id]
                    return (
                      <tr key={lot.id}>
                        <td className="data-table__id">#{lot.id}</td>
                        <td>{reference.productName(lot.product_id)}</td>
                        <td>
                          {product ? reference.supplierName(product.supplier_id) : '—'}
                        </td>
                        <td>{lot.quantity_on_hand}</td>
                        <td>
                          {lot.supplier_order_line_id === null ? (
                            <StatusBadge label="Unlinked" tone="neutral" />
                          ) : (
                            <StatusBadge
                              label={`Line #${lot.supplier_order_line_id}`}
                              tone="mint"
                            />
                          )}
                        </td>
                        <td className="data-table__muted">{formatWhen(lot.created_at)}</td>
                        <td className="data-table__muted">{formatWhen(lot.updated_at)}</td>
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
                <button type="button" disabled={safePage <= 1} onClick={() => goToPage(safePage - 1)}>
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
