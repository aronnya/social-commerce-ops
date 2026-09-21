import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { getHealth } from '../api/resources'

const NAV_ITEMS = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/enquiries', label: 'Enquiries', end: false },
  { to: '/preorders', label: 'Preorders', end: false },
  { to: '/supplier-orders', label: 'Supplier Orders', end: false },
  { to: '/catalogue', label: 'Catalogue', end: false },
  { to: '/inventory', label: 'Inventory', end: false },
  { to: '/customers', label: 'Customers', end: false },
  { to: '/insights', label: 'Insights', end: false },
] as const

type HealthState = 'checking' | 'ok' | 'error'

export function AppLayout() {
  const [health, setHealth] = useState<HealthState>('checking')

  useEffect(() => {
    getHealth()
      .then((body) => {
        setHealth(body.status === 'ok' ? 'ok' : 'error')
      })
      .catch(() => {
        setHealth('error')
      })
  }, [])

  const healthLabel =
    health === 'checking'
      ? 'Checking API…'
      : health === 'ok'
        ? 'API connected'
        : 'API unavailable'

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar__brand">
          <span className="sidebar__mark" aria-hidden="true" />
          <div>
            <p className="sidebar__title">Social Commerce Ops</p>
            <p className="sidebar__subtitle">Internal operations</p>
          </div>
        </div>
        <nav className="sidebar__nav" aria-label="Main">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                isActive ? 'sidebar__link sidebar__link--active' : 'sidebar__link'
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className={`sidebar__health sidebar__health--${health}`}>
          <span className="sidebar__health-dot" aria-hidden="true" />
          <span>{healthLabel}</span>
        </div>
      </aside>
      <main className="content">
        <div className="content__inner">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
