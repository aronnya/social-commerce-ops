import { useMemo, useRef, useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { createProduct, createSupplier, updateProduct } from '../api/resources'
import type { Money, Product, ProductCreate, SupplierCreate } from '../api/types'
import { useReferenceData } from '../api/useReferenceData'
import { EmptyState, ErrorState, LoadingState } from '../ui/PageState'
import { StatusBadge } from '../ui/StatusBadge'

const PAGE_SIZE = 10

type PriceFilter = 'ALL' | 'PRICED' | 'UNPRICED'
type Panel = 'none' | 'product' | 'supplier' | 'edit'

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

function optionalText(value: string): string | undefined {
  const trimmed = value.trim()
  return trimmed ? trimmed : undefined
}

export function CataloguePage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const reference = useReferenceData()
  const [query, setQuery] = useState('')
  const [priceFilter, setPriceFilter] = useState<PriceFilter>('ALL')
  const [page, setPage] = useState(1)
  const [pageFilterKey, setPageFilterKey] = useState('')
  const [panel, setPanel] = useState<Panel>('none')
  const [editing, setEditing] = useState<Product | null>(null)
  const [busy, setBusy] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const lock = useRef(false)

  const supplierParam = searchParams.get('supplier')
  const supplierFilter = supplierParam && /^\d+$/.test(supplierParam) ? supplierParam : 'ALL'

  const products = reference.products

  const counts = useMemo(() => {
    const supplierIds = new Set<number>()
    let priced = 0
    for (const row of products) {
      supplierIds.add(row.supplier_id)
      if (row.selling_price !== null) {
        priced += 1
      }
    }
    return {
      suppliers: supplierIds.size,
      priced,
      unpriced: products.length - priced,
    }
  }, [products])

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return products.filter((row) => {
      if (supplierFilter !== 'ALL' && row.supplier_id !== Number(supplierFilter)) {
        return false
      }
      if (priceFilter === 'PRICED' && row.selling_price === null) {
        return false
      }
      if (priceFilter === 'UNPRICED' && row.selling_price !== null) {
        return false
      }
      if (!needle) {
        return true
      }
      const haystack = [
        `#${row.id}`,
        String(row.id),
        row.name,
        row.style ?? '',
        row.colour ?? '',
        row.size ?? '',
        reference.supplierName(row.supplier_id),
      ]
        .join(' ')
        .toLowerCase()
      return haystack.includes(needle)
    })
  }, [priceFilter, products, query, reference, supplierFilter])

  const filterKey = `${supplierFilter}|${priceFilter}|${query}`
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

  function setSupplierFilter(next: string) {
    const params = new URLSearchParams(searchParams)
    if (next === 'ALL') {
      params.delete('supplier')
    } else {
      params.set('supplier', next)
    }
    setSearchParams(params, { replace: true })
  }

  async function runMutation(work: () => Promise<string>) {
    if (lock.current) {
      return
    }
    lock.current = true
    setBusy(true)
    setFormError(null)
    setNotice(null)
    try {
      const message = await work()
      setNotice(message)
      setPanel('none')
      setEditing(null)
      reference.refresh()
    } catch (caught: unknown) {
      setFormError(mutationError(caught, 'This change could not be saved.'))
    } finally {
      lock.current = false
      setBusy(false)
    }
  }

  return (
    <div className="preorders catalogue">
      <header className="list-header">
        <div className="page-header">
          <h1>Catalogue</h1>
          <p>Products currently offered by suppliers. This is not owned stock.</p>
        </div>
        <div className="detail-actions__row">
          <button
            type="button"
            className="action-btn"
            disabled={busy}
            onClick={() => {
              setFormError(null)
              setPanel(panel === 'supplier' ? 'none' : 'supplier')
              setEditing(null)
            }}
          >
            + New supplier
          </button>
          <button
            type="button"
            className="action-btn action-btn--primary"
            disabled={busy}
            onClick={() => {
              setFormError(null)
              setPanel(panel === 'product' ? 'none' : 'product')
              setEditing(null)
            }}
          >
            + New product
          </button>
        </div>
      </header>

      {panel === 'product' ? (
        <ProductForm
          title="New catalogue product"
          busy={busy}
          error={formError}
          onCancel={() => {
            setPanel('none')
            setFormError(null)
          }}
          onSubmit={(payload) =>
            runMutation(async () => {
              const created = await withTimeout(createProduct(payload), 20000)
              return `Catalogue product #${created.id} was added.`
            })
          }
        />
      ) : null}

      {panel === 'supplier' ? (
        <SupplierForm
          busy={busy}
          error={formError}
          onCancel={() => {
            setPanel('none')
            setFormError(null)
          }}
          onSubmit={(payload) =>
            runMutation(async () => {
              const created = await withTimeout(createSupplier(payload), 20000)
              return `Supplier #${created.id} was added.`
            })
          }
        />
      ) : null}

      {panel === 'edit' && editing ? (
        <ProductForm
          title={`Edit product #${editing.id}`}
          product={editing}
          busy={busy}
          error={formError}
          onCancel={() => {
            setPanel('none')
            setEditing(null)
            setFormError(null)
          }}
          onSubmit={(payload) =>
            runMutation(async () => {
              const updated = await withTimeout(updateProduct(editing.id, payload), 20000)
              return `Catalogue product #${updated.id} was updated.`
            })
          }
        />
      ) : null}

      {notice ? <p className="ops-notice">{notice}</p> : null}

      <section className="preorder-cards enquiry-cards" aria-label="Catalogue summary">
        <button
          type="button"
          className={`dash-card dash-card--sky${supplierFilter === 'ALL' && priceFilter === 'ALL' ? ' is-selected' : ''}`}
          onClick={() => {
            setSupplierFilter('ALL')
            setPriceFilter('ALL')
          }}
        >
          <span className="dash-card__count">
            {reference.loading ? '…' : reference.error ? '—' : products.length}
          </span>
          <span className="dash-card__label">Total</span>
          <span className="dash-card__hint">Supplier-offered products</span>
        </button>
        <div className="dash-card dash-card--cream dash-card--static">
          <span className="dash-card__count">
            {reference.loading ? '…' : reference.error ? '—' : counts.suppliers}
          </span>
          <span className="dash-card__label">Suppliers</span>
          <span className="dash-card__hint">With catalogue products</span>
        </div>
        <button
          type="button"
          className={`dash-card dash-card--sage${priceFilter === 'PRICED' ? ' is-selected' : ''}`}
          onClick={() => setPriceFilter('PRICED')}
        >
          <span className="dash-card__count">
            {reference.loading ? '…' : reference.error ? '—' : counts.priced}
          </span>
          <span className="dash-card__label">Priced</span>
          <span className="dash-card__hint">Selling price set</span>
        </button>
        <button
          type="button"
          className={`dash-card dash-card--blush${priceFilter === 'UNPRICED' ? ' is-selected' : ''}`}
          onClick={() => setPriceFilter('UNPRICED')}
        >
          <span className="dash-card__count">
            {reference.loading ? '…' : reference.error ? '—' : counts.unpriced}
          </span>
          <span className="dash-card__label">Price not set</span>
          <span className="dash-card__hint">Selling price empty</span>
        </button>
      </section>

      <section className="panel preorder-panel">
        <div className="preorder-toolbar">
          <label className="preorder-search">
            <span className="visually-hidden">Search catalogue</span>
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search catalogue..."
            />
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
          <label>
            <span className="visually-hidden">Selling price</span>
            <select
              value={priceFilter}
              onChange={(event) => setPriceFilter(event.target.value as PriceFilter)}
            >
              <option value="ALL">All prices</option>
              <option value="PRICED">Priced</option>
              <option value="UNPRICED">Price not set</option>
            </select>
          </label>
        </div>

        {reference.loading ? (
          <LoadingState message="Loading catalogue…" />
        ) : reference.error ? (
          <ErrorState
            title="Catalogue could not be loaded"
            message={reference.error}
            onRetry={reference.refresh}
          />
        ) : products.length === 0 ? (
          <EmptyState
            title="No catalogue products yet"
            message="Add supplier-offered products here. Owned stock lives on Inventory."
          />
        ) : filtered.length === 0 ? (
          <EmptyState title="No matching products" message="No catalogue products match these filters." />
        ) : (
          <>
            <div className="table-wrap">
              <table className="data-table data-table--catalogue">
                <thead>
                  <tr>
                    <th>Product</th>
                    <th>Supplier</th>
                    <th>Details</th>
                    <th>Selling price</th>
                    <th>Supplier cost</th>
                    <th>Updated</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {pageRows.map((row) => {
                    const meta = [row.style, row.colour, row.size].filter(Boolean).join(' · ')
                    return (
                      <tr key={row.id}>
                        <td>
                          <span className="data-table__id">#{row.id}</span>
                          <span className="cell-primary">{row.name}</span>
                        </td>
                        <td>{reference.supplierName(row.supplier_id)}</td>
                        <td>{meta ? meta : <span className="data-table__muted">—</span>}</td>
                        <td>
                          {row.selling_price === null ? (
                            <StatusBadge label="Not set" tone="neutral" />
                          ) : (
                            formatAmount(row.selling_price)
                          )}
                        </td>
                        <td>
                          {row.supplier_cost === null ? '—' : formatAmount(row.supplier_cost)}
                        </td>
                        <td className="data-table__muted">{formatWhen(row.updated_at)}</td>
                        <td>
                          <button
                            type="button"
                            className="action-btn"
                            disabled={busy}
                            onClick={() => {
                              setFormError(null)
                              setEditing(row)
                              setPanel('edit')
                            }}
                          >
                            Edit
                          </button>
                        </td>
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

function ProductForm({
  title,
  product,
  busy,
  error,
  onCancel,
  onSubmit,
}: {
  title: string
  product?: Product
  busy: boolean
  error: string | null
  onCancel: () => void
  onSubmit: (payload: ProductCreate) => void
}) {
  const reference = useReferenceData()
  const [supplierId, setSupplierId] = useState(product ? String(product.supplier_id) : '')
  const [name, setName] = useState(product?.name ?? '')
  const [style, setStyle] = useState(product?.style ?? '')
  const [colour, setColour] = useState(product?.colour ?? '')
  const [size, setSize] = useState(product?.size ?? '')
  const [sellingPrice, setSellingPrice] = useState(
    product?.selling_price === null || product?.selling_price === undefined
      ? ''
      : String(product.selling_price),
  )
  const [supplierCost, setSupplierCost] = useState(
    product?.supplier_cost === null || product?.supplier_cost === undefined
      ? ''
      : String(product.supplier_cost),
  )
  const [description, setDescription] = useState(product?.description ?? '')
  const [notes, setNotes] = useState(product?.notes ?? '')

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (busy) {
      return
    }
    const payload: ProductCreate = {
      supplier_id: Number(supplierId),
      name: name.trim(),
    }
    const nextStyle = optionalText(style)
    const nextColour = optionalText(colour)
    const nextSize = optionalText(size)
    const nextDescription = optionalText(description)
    const nextNotes = optionalText(notes)
    if (nextStyle) payload.style = nextStyle
    if (nextColour) payload.colour = nextColour
    if (nextSize) payload.size = nextSize
    if (nextDescription) payload.description = nextDescription
    if (nextNotes) payload.notes = nextNotes
    if (sellingPrice.trim()) payload.selling_price = sellingPrice.trim()
    if (supplierCost.trim()) payload.supplier_cost = supplierCost.trim()
    onSubmit(payload)
  }

  return (
    <section className="panel">
      <h2>{title}</h2>
      <p className="detail-muted">Adds a supplier-offered product. It does not create owned inventory.</p>
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
        <label>
          Name
          <input
            required
            maxLength={200}
            value={name}
            disabled={busy}
            onChange={(event) => setName(event.target.value)}
          />
        </label>
        <label>
          Style
          <input value={style} disabled={busy} onChange={(event) => setStyle(event.target.value)} />
        </label>
        <label>
          Colour
          <input value={colour} disabled={busy} onChange={(event) => setColour(event.target.value)} />
        </label>
        <label>
          Size
          <input value={size} disabled={busy} onChange={(event) => setSize(event.target.value)} />
        </label>
        <label>
          Selling price
          <input
            type="number"
            min="0"
            step="0.01"
            value={sellingPrice}
            disabled={busy}
            onChange={(event) => setSellingPrice(event.target.value)}
          />
        </label>
        <label>
          Supplier cost
          <input
            type="number"
            min="0"
            step="0.01"
            value={supplierCost}
            disabled={busy}
            onChange={(event) => setSupplierCost(event.target.value)}
          />
        </label>
        <label className="ops-form__wide">
          Description
          <textarea
            rows={2}
            value={description}
            disabled={busy}
            onChange={(event) => setDescription(event.target.value)}
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
            Save product
          </button>
          <button type="button" className="action-btn" disabled={busy} onClick={onCancel}>
            Cancel
          </button>
        </div>
      </form>
    </section>
  )
}

function SupplierForm({
  busy,
  error,
  onCancel,
  onSubmit,
}: {
  busy: boolean
  error: string | null
  onCancel: () => void
  onSubmit: (payload: SupplierCreate) => void
}) {
  const [name, setName] = useState('')
  const [contactName, setContactName] = useState('')
  const [phone, setPhone] = useState('')
  const [whatsapp, setWhatsapp] = useState('')
  const [email, setEmail] = useState('')
  const [notes, setNotes] = useState('')

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (busy) {
      return
    }
    const payload: SupplierCreate = { name: name.trim() }
    const contact = optionalText(contactName)
    const nextPhone = optionalText(phone)
    const nextWhatsapp = optionalText(whatsapp)
    const nextEmail = optionalText(email)
    const nextNotes = optionalText(notes)
    if (contact) payload.contact_name = contact
    if (nextPhone) payload.phone = nextPhone
    if (nextWhatsapp) payload.whatsapp = nextWhatsapp
    if (nextEmail) payload.email = nextEmail
    if (nextNotes) payload.notes = nextNotes
    onSubmit(payload)
  }

  return (
    <section className="panel">
      <h2>New supplier</h2>
      <p className="detail-muted">Suppliers own catalogue products, not customer records.</p>
      <form className="ops-form" onSubmit={handleSubmit}>
        <label>
          Name
          <input
            required
            maxLength={200}
            value={name}
            disabled={busy}
            onChange={(event) => setName(event.target.value)}
          />
        </label>
        <label>
          Contact name
          <input
            value={contactName}
            disabled={busy}
            onChange={(event) => setContactName(event.target.value)}
          />
        </label>
        <label>
          Phone
          <input value={phone} disabled={busy} onChange={(event) => setPhone(event.target.value)} />
        </label>
        <label>
          WhatsApp
          <input
            value={whatsapp}
            disabled={busy}
            onChange={(event) => setWhatsapp(event.target.value)}
          />
        </label>
        <label className="ops-form__wide">
          Email
          <input
            type="email"
            value={email}
            disabled={busy}
            onChange={(event) => setEmail(event.target.value)}
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
            Save supplier
          </button>
          <button type="button" className="action-btn" disabled={busy} onClick={onCancel}>
            Cancel
          </button>
        </div>
      </form>
    </section>
  )
}
