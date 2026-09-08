# Architecture

This document is the living explanation of how the system is built. It is written so a beginner can defend the project in an internship interview.

## High-level architecture

One web app, two processes, one database:

```
Browser (React + TypeScript)
        |
        |  HTTP JSON (REST)
        v
FastAPI backend (Python)
        |
        |  SQLAlchemy
        v
PostgreSQL
```

Reasons:

- The business is one team (the owner). One backend is enough.
- REST + JSON is easy to test and easy to explain.
- PostgreSQL fits related business records (customers, products, orders, payments).
- Frontend and backend stay in separate folders so each can be run, tested, and deployed independently.

We are **not** using microservices, Kubernetes, Kafka, Redis, GraphQL, or Docker. Those would add moving parts without solving a current problem.

The API and UI run on the host machine so logs and breakpoints stay simple. PostgreSQL is the planned database. We will connect to a hosted instance (for example Supabase) in the database milestone, not in Milestone 1.

## Folder structure

```
social-commerce-ops/
  README.md
  PROJECT_BRIEF.md
  ARCHITECTURE.md
  .gitignore
  .env.example
  backend/
    app/
      main.py          # FastAPI application
      core/config.py   # settings from environment variables
    tests/
    requirements.txt
  frontend/            # Vite + React + TypeScript
```

Later backend folders (not created until needed):

- `app/models/` — SQLAlchemy tables
- `app/schemas/` — Pydantic request/response shapes
- `app/api/` — HTTP routes
- `app/services/` — business rules (state transitions, payment totals)
- `alembic/` — database migrations

## Important entities and relationships (planned)

These tables are **not implemented yet**. They are the intended relational model.

| Entity | What it is |
| --- | --- |
| `suppliers` | People/businesses in Pakistan who provide dresses |
| `products` | Catalogue items (photos, prices, type). **Not** stock. |
| `customers` | People who enquire or buy |
| `enquiries` | Interest in a product, including lost sales |
| `preorders` | A customer commitment to buy a catalogue item |
| `payments` | Individual transfers (bank / Revolut). Separate from preorder status. |
| `supplier_orders` | A batch sent to a supplier |
| `supplier_order_lines` | Rows on that batch (for preorders and/or stock buys) |
| `inventory_lots` | Physical stock the business owns |

Relationships in plain English:

- A supplier has many products.
- A product belongs to one supplier.
- A customer has many enquiries and many preorders.
- An enquiry is about one product and one customer. It may later link to a preorder, or it may end with a lost-sale reason.
- A preorder is for one customer and one product. It may come from an enquiry (optional, because walk-in sales exist).
- A preorder may be attached to one supplier order once it is grouped for buying.
- Payments belong to a preorder. Several payments can add up to the agreed price.
- A supplier order has many lines. A line points at a product and optionally at a preorder.
- An inventory lot points at a product and records quantity actually on hand. It may come from a supplier-order line.

Why enquiry and preorder are separate: analytics must count “people asked about this dress” even when they never ordered. If we only stored preorders, we would throw away lost-demand data.

Why payment status is not a preorder status: the dress can already be ordered from Pakistan while the customer has paid, partly paid, or not paid. Mixing those into one enum would make reports and rules messy.

Why supplier-order status is separate: one supplier shipment can cover many customer preorders. The shipment can be “dispatched” while an individual preorder is still “ordered from supplier”.

## Planned REST API

Version prefix: `/api/v1`.

| Area | Endpoints (planned) |
| --- | --- |
| Health | `GET /health` (already exists) |
| Suppliers | `GET/POST /api/v1/suppliers`, `GET/PATCH /api/v1/suppliers/{id}` |
| Products | `GET/POST /api/v1/products`, `GET/PATCH /api/v1/products/{id}` |
| Customers | `GET/POST /api/v1/customers`, `GET/PATCH /api/v1/customers/{id}` |
| Enquiries | `GET/POST /api/v1/enquiries`, `PATCH` for outcome |
| Preorders | `GET/POST /api/v1/preorders`, `POST /api/v1/preorders/{id}/transitions` |
| Payments | `GET/POST /api/v1/preorders/{id}/payments` |
| Supplier orders | `GET/POST /api/v1/supplier-orders`, lines, transitions |
| Inventory | `GET /api/v1/inventory`, receive / adjust |
| Analytics | `GET /api/v1/analytics/enquiries`, conversions, loss reasons, suppliers, prices |

Preorder status is **not** a free-form `PATCH`. A dedicated transition endpoint will check an allow-list of next states.

## Request / data flow (once features exist)

1. Owner records a catalogue product from a supplier photo.
2. A customer enquiry is stored against that product (outcome may still be unknown).
3. If they commit, a preorder is created (`CONFIRMED`) and the enquiry outcome becomes `PREORDERED`.
4. Payments are recorded as they arrive; payment status is derived from paid total vs agreed price.
5. Several preorders are grouped onto a supplier order (`DRAFT` → `PLACED` …).
6. When goods arrive, inventory (if kept) and preorder statuses update (`ARRIVED` → `READY_FOR_CUSTOMER` → `FULFILLED`).
7. Analytics queries group enquiries and preorders in SQL.

## State models (planned)

### Preorder

Happy path: `INQUIRY` → `CONFIRMED` → `ORDERED_FROM_SUPPLIER` → `ARRIVED` → `READY_FOR_CUSTOMER` → `FULFILLED`

Also allowed as exits (exact edges to be coded later): `CANCELLED`, `SUPPLIER_UNAVAILABLE`

### Payment (derived from payment rows)

`UNPAID` | `PARTIALLY_PAID` | `PAID` | `REFUNDED`

### Supplier order

`DRAFT` → `PLACED` → `CONFIRMED` → `DISPATCHED` → `ARRIVED` → `RECONCILED`

## Auth (later, not Milestone 1)

This is a private internal app. We will add a simple login before real use. We will not build Facebook login in the MVP.

## Photos (later)

Store uploaded images on local disk (`uploads/`, gitignored) and save the file path on the product. Cloud object storage is unnecessary until there is more than one machine.

## Money

Store amounts as decimals, not floats. Likely two currencies in real life (supplier cost in PKR, selling price in EUR). MVP: store both as fields, no live FX conversion.

## Tradeoffs

| Choice | Why | Cost |
| --- | --- | --- |
| Monolith API + SPA | Simple to run and explain | Not independently scalable (not needed) |
| Enquiries ≠ preorders | Honest demand analytics | Extra table and a bit more API work |
| Derived payment status | Totals cannot disagree with payment rows | Must recompute when payments change |
| Hosted Postgres later (e.g. Supabase) | No local database install or Docker | Needs a connection string in `.env` when we start Milestone 2 |
| No Redis | No caching/queue requirement yet | Fine at this scale |
| Minimal UI until Figma | Avoid throwing away a fake dashboard | Early screens will look plain on purpose |

## Known limitations (now)

- No business tables or APIs yet
- No authentication
- No product photos
- Database is not used by the API yet
- Frontend only checks that the API health endpoint responds

## Future improvements (not now)

Messenger / WhatsApp import, payment feed matching, image similarity search, forecasting, multi-user permissions.

## Milestone 1 notes

Implemented:

- Split `frontend/` and `backend/`
- FastAPI `GET /health`
- Settings from environment (`.env` is gitignored)
- Vite React + TypeScript app that calls `/health`
- pytest for the health endpoint
- PostgreSQL planned, but no database connection yet

Not implemented: SQLAlchemy models, Alembic, CRUD APIs.
