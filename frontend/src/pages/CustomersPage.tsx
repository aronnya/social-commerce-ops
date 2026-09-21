import { useMemo, useRef, useState, type FormEvent } from 'react'
import { ApiError } from '../api/client'
import { createCustomer, updateCustomer } from '../api/resources'
import type { Customer, CustomerCreate } from '../api/types'
import { useReferenceData } from '../api/useReferenceData'
import { EmptyState, ErrorState, LoadingState } from '../ui/PageState'
import { StatusBadge } from '../ui/StatusBadge'

const PAGE_SIZE = 10

type ContactFilter = 'ALL' | 'PHONE' | 'FACEBOOK'
type Panel = 'none' | 'create' | 'edit'

function formatWhen(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return date.toLocaleString(undefined, { dateStyle: 'medium' })
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

export function CustomersPage() {
  const reference = useReferenceData()
  const [query, setQuery] = useState('')
  const [contactFilter, setContactFilter] = useState<ContactFilter>('ALL')
  const [page, setPage] = useState(1)
  const [pageFilterKey, setPageFilterKey] = useState('')
  const [panel, setPanel] = useState<Panel>('none')
  const [editing, setEditing] = useState<Customer | null>(null)
  const [busy, setBusy] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const lock = useRef(false)

  const customers = reference.customers

  const counts = useMemo(() => {
    let phone = 0
    let facebook = 0
    let notes = 0
    for (const row of customers) {
      if (row.phone) phone += 1
      if (row.facebook_name) facebook += 1
      if (row.notes) notes += 1
    }
    return { phone, facebook, notes }
  }, [customers])

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return customers.filter((row) => {
      if (contactFilter === 'PHONE' && !row.phone) {
        return false
      }
      if (contactFilter === 'FACEBOOK' && !row.facebook_name) {
        return false
      }
      if (!needle) {
        return true
      }
      const haystack = [`#${row.id}`, String(row.id), row.name, row.phone ?? '', row.facebook_name ?? '', row.notes ?? '']
        .join(' ')
        .toLowerCase()
      return haystack.includes(needle)
    })
  }, [contactFilter, customers, query])

  const filterKey = `${contactFilter}|${query}`
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
      setFormError(mutationError(caught, 'This customer could not be saved.'))
    } finally {
      lock.current = false
      setBusy(false)
    }
  }

  return (
    <div className="preorders customers">
      <header className="list-header">
        <div className="page-header">
          <h1>Customers</h1>
          <p>People who enquire and preorder. This is not a CRM scorecard.</p>
        </div>
        <button
          type="button"
          className="action-btn action-btn--primary"
          disabled={busy}
          onClick={() => {
            setFormError(null)
            setEditing(null)
            setPanel(panel === 'create' ? 'none' : 'create')
          }}
        >
          + New customer
        </button>
      </header>

      {panel === 'create' ? (
        <CustomerForm
          title="New customer"
          busy={busy}
          error={formError}
          onCancel={() => {
            setPanel('none')
            setFormError(null)
          }}
          onSubmit={(payload) =>
            runMutation(async () => {
              const created = await withTimeout(createCustomer(payload), 20000)
              return `Customer #${created.id} was added.`
            })
          }
        />
      ) : null}

      {panel === 'edit' && editing ? (
        <CustomerForm
          title={`Edit customer #${editing.id}`}
          customer={editing}
          busy={busy}
          error={formError}
          onCancel={() => {
            setPanel('none')
            setEditing(null)
            setFormError(null)
          }}
          onSubmit={(payload) =>
            runMutation(async () => {
              const updated = await withTimeout(updateCustomer(editing.id, payload), 20000)
              return `Customer #${updated.id} was updated.`
            })
          }
        />
      ) : null}

      {notice ? <p className="ops-notice">{notice}</p> : null}

      <section className="preorder-cards enquiry-cards" aria-label="Customer summary">
        <button
          type="button"
          className={`dash-card dash-card--sky${contactFilter === 'ALL' ? ' is-selected' : ''}`}
          onClick={() => setContactFilter('ALL')}
        >
          <span className="dash-card__count">
            {reference.loading ? '…' : reference.error ? '—' : customers.length}
          </span>
          <span className="dash-card__label">Total</span>
          <span className="dash-card__hint">Customer records</span>
        </button>
        <button
          type="button"
          className={`dash-card dash-card--cream${contactFilter === 'PHONE' ? ' is-selected' : ''}`}
          onClick={() => setContactFilter('PHONE')}
        >
          <span className="dash-card__count">
            {reference.loading ? '…' : reference.error ? '—' : counts.phone}
          </span>
          <span className="dash-card__label">Phone on file</span>
          <span className="dash-card__hint">Has a phone number</span>
        </button>
        <button
          type="button"
          className={`dash-card dash-card--lavender${contactFilter === 'FACEBOOK' ? ' is-selected' : ''}`}
          onClick={() => setContactFilter('FACEBOOK')}
        >
          <span className="dash-card__count">
            {reference.loading ? '…' : reference.error ? '—' : counts.facebook}
          </span>
          <span className="dash-card__label">Facebook name</span>
          <span className="dash-card__hint">Has a Facebook name</span>
        </button>
        <div className="dash-card dash-card--mist dash-card--static">
          <span className="dash-card__count">
            {reference.loading ? '…' : reference.error ? '—' : counts.notes}
          </span>
          <span className="dash-card__label">Notes on file</span>
          <span className="dash-card__hint">Has operator notes</span>
        </div>
      </section>

      <section className="panel preorder-panel">
        <div className="preorder-toolbar">
          <label className="preorder-search">
            <span className="visually-hidden">Search customers</span>
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search customers..."
            />
          </label>
          <label>
            <span className="visually-hidden">Contact</span>
            <select
              value={contactFilter}
              onChange={(event) => setContactFilter(event.target.value as ContactFilter)}
            >
              <option value="ALL">All customers</option>
              <option value="PHONE">Phone on file</option>
              <option value="FACEBOOK">Facebook name</option>
            </select>
          </label>
        </div>

        {reference.loading ? (
          <LoadingState message="Loading customers…" />
        ) : reference.error ? (
          <ErrorState
            title="Customers could not be loaded"
            message={reference.error}
            onRetry={reference.refresh}
          />
        ) : customers.length === 0 ? (
          <EmptyState title="No customers yet" message="Add a customer record when someone enquires." />
        ) : filtered.length === 0 ? (
          <EmptyState title="No matching customers" message="No customers match these filters." />
        ) : (
          <>
            <div className="table-wrap">
              <table className="data-table data-table--customers">
                <thead>
                  <tr>
                    <th>Customer</th>
                    <th>Phone</th>
                    <th>Facebook</th>
                    <th>Notes</th>
                    <th>Created</th>
                    <th>Updated</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {pageRows.map((row) => (
                    <tr key={row.id}>
                      <td>
                        <span className="data-table__id">#{row.id}</span>
                        <span className="cell-primary">{row.name}</span>
                      </td>
                      <td>{row.phone ?? <span className="data-table__muted">—</span>}</td>
                      <td>
                        {row.facebook_name ? (
                          row.facebook_name
                        ) : (
                          <StatusBadge label="Not set" tone="neutral" />
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
                  ))}
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

function CustomerForm({
  title,
  customer,
  busy,
  error,
  onCancel,
  onSubmit,
}: {
  title: string
  customer?: Customer
  busy: boolean
  error: string | null
  onCancel: () => void
  onSubmit: (payload: CustomerCreate) => void
}) {
  const [name, setName] = useState(customer?.name ?? '')
  const [phone, setPhone] = useState(customer?.phone ?? '')
  const [facebookName, setFacebookName] = useState(customer?.facebook_name ?? '')
  const [notes, setNotes] = useState(customer?.notes ?? '')

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (busy) {
      return
    }
    const payload: CustomerCreate = { name: name.trim() }
    const nextPhone = optionalText(phone)
    const nextFacebook = optionalText(facebookName)
    const nextNotes = optionalText(notes)
    if (nextPhone) payload.phone = nextPhone
    if (nextFacebook) payload.facebook_name = nextFacebook
    if (nextNotes) payload.notes = nextNotes
    onSubmit(payload)
  }

  return (
    <section className="panel">
      <h2>{title}</h2>
      <p className="detail-muted">Stores contact identity only. Do not use this as a sales leaderboard.</p>
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
          Phone
          <input value={phone} disabled={busy} onChange={(event) => setPhone(event.target.value)} />
        </label>
        <label>
          Facebook name
          <input
            value={facebookName}
            disabled={busy}
            onChange={(event) => setFacebookName(event.target.value)}
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
            Save customer
          </button>
          <button type="button" className="action-btn" disabled={busy} onClick={onCancel}>
            Cancel
          </button>
        </div>
      </form>
    </section>
  )
}
