# Architecture

This document is the living explanation of how the system is built. It is written so a beginner can defend the project in an internship interview.

## Product principle

Every major screen should help the user perform or understand an operational task. The platform should not become CRUD for its own sake. Data storage supports workflows, automation, exception handling and decision-making.

REST list/create/update endpoints will exist because the workflow needs records. They are not the product. The valuable behaviour is coordinating preorders, supplier orders, payments, inventory, exceptions, and (later) demand decisions.

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

The API and UI run on the host machine so logs and breakpoints stay simple. PostgreSQL is a hosted instance (for example Supabase), configured with `DATABASE_URL`. Do not put that URL in git.

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
      core/db.py       # SQLAlchemy engine, session, Base
      models.py        # Supplier, Product (catalogue), Customer
      schemas.py       # Pydantic request/response shapes
      services.py      # database operations and rules
      api.py           # /api/v1 HTTP routes
    alembic/           # database migrations
    tests/
    requirements.txt
    alembic.ini
  frontend/            # Vite + React + TypeScript
```

Keep models/schemas/services in a few modules for now. Split into packages later if the files get hard to read.

Business rules belong in `services.py` (or equivalent domain functions), not only in React. The frontend should call operations such as “generate draft supplier order” or “record arrival”; it should not send arbitrary status strings the API blindly saves.

## Important entities and relationships

| Entity | Status | What it is |
| --- | --- | --- |
| `suppliers` | Implemented | People/businesses in Pakistan who provide dresses |
| `products` | Implemented | Catalogue items (photos later, prices, type). **Not** stock. |
| `customers` | Implemented | People who enquire or buy |
| `enquiries` | Implemented | Interest in a product, including lost sales |
| `preorders` | Planned | A customer commitment to buy a catalogue item |
| `payments` | Planned | Individual transfers (bank / Revolut). Separate from preorder status. |
| `supplier_orders` | Planned | A batch sent to a supplier |
| `supplier_order_lines` | Planned | Consolidated rows on that batch, with links back to preorders and/or stock buys |
| `inventory_lots` | Planned | Physical stock the business owns |
| `workflow_events` | Later | Audit trail of important workflow changes |

Relationships in plain English:

- A supplier has many products.
- A product belongs to one supplier.
- A customer has many enquiries and many preorders.
- An enquiry is about one product and one customer. It may later link to a preorder, or it may end with a lost-sale reason.
- A preorder is for one customer and one product. It may come from an enquiry (optional, because walk-in sales exist).
- A preorder may be attached to one **active** supplier order once it is grouped for buying. It must not be included in multiple active supplier orders.
- Payments belong to a preorder. Several payments can add up to the agreed price. Payment status is calculated from those rows.
- A supplier order has many lines. A line consolidates quantity for a product/variant, still pointing at the customer preorders (and optional inventory buys) it covers. Lines should be able to record ordered vs received quantity at reconciliation.
- An inventory lot points at a product and records quantity actually on hand. Receiving a stock purchase increases it. Allocating or selling physical stock decreases it, and must not go below available quantity.
- Workflow events (when added) point at the relevant entity and record what happened and when.

Why enquiry and preorder are separate: analytics must count “people asked about this dress” even when they never ordered. If we only stored preorders, we would throw away lost-demand data.

Why payment status is not a preorder status: the dress can already be ordered from Pakistan while the customer has paid, partly paid, or not paid. Mixing those into one enum would make reports and rules messy.

Why supplier-order status is separate: one supplier shipment can cover many customer preorders. The shipment can be “dispatched” while an individual preorder is still “ordered from supplier”.

## Operational behaviours (how the domain should work)

These behaviours are the point of the architecture. They will be added milestone by milestone, not all in the first database slice.

### Action / attention queue

The API should eventually expose a derived queue (SQL over current state), not a separately maintained to-do table that can drift. Examples:

- confirmed preorders not yet on a supplier order
- supplier orders waiting for the next valid action
- items in `ARRIVED` / `READY_FOR_CUSTOMER` waiting for collection or delivery
- preorders with an outstanding balance
- orders that may be delayed (once we have enough timestamps/events)

The home screen’s job is: “What needs my attention today?”

### Supplier order generation

Confirmed preorders should be groupable **by supplier** into a `DRAFT` supplier order. The service should:

- consolidate quantities for the same product/variant
- keep links from the draft (and its lines) back to each customer preorder
- leave the draft for the owner to review
- only then allow marking the order `PLACED`

This is a workflow operation, not “type a supplier order in a form from scratch” as the main path.

### Payment calculation

Prefer derived payment state from payment records (never stored on Preorder or Payment):

- total order amount = `preorder.quantity * preorder.agreed_price` (null if `agreed_price` is null)
- amount paid (sum of payment rows)
- outstanding balance (`total - paid` when total is known)
- `UNPAID` / `PARTIALLY_PAID` / `PAID`, plus `OVERPAID` when paid exceeds total

Do not treat payment status as an unrelated dropdown. Refunds should later be first-class records that adjust the same calculations.

### Supplier delivery reconciliation

When a supplier order arrives, the owner reconciles ordered quantity vs received quantity per line. The service should:

- flag missing or unavailable items
- attach received units to the relevant customer preorders and/or increase inventory (for stock buys)
- drive the related preorder transitions (`ARRIVED`, or a side outcome such as `SUPPLIER_UNAVAILABLE` when items will not come)

### Inventory consequences

Catalogue `products` and `inventory_lots` stay different tables. Rules:

- receiving a stock purchase increases physical inventory
- selling or allocating physical stock reduces available inventory
- refuse allocations that exceed what is available

Preorder fulfilment from a Pakistan shipment and fulfilment from local stock are both valid paths; only the local-stock path consumes inventory lots.

### Workflow / business-rule enforcement

Invalid operations should fail in the backend (clear HTTP errors), including:

- illegal preorder or supplier-order transitions
- attaching a preorder to a second active supplier order
- over-allocating inventory
- payments that would make totals inconsistent (for example ignoring the agreed amount)

### Event / history tracking

A `workflow_events` (or similarly named) history can be added when those operations exist. Examples of events: enquiry created, preorder confirmed, payment recorded, supplier order placed, supplier order dispatched, item arrived, customer notified, fulfilled. That trail later supports operational metrics (for example average time from confirmed to fulfilled). It is not required before the first CRUD tables exist.

### Demand intelligence

Keep analysing **enquiries** as well as completed sales. SQL aggregations should later cover conversion, lost-sale reasons, high-interest/low-conversion products, demand by style/colour/size/price/supplier/time, supplier performance, and candidates for local inventory. No machine learning in the MVP.

## Planned REST API

Version prefix: `/api/v1`.

Resource endpoints will exist for the entities above. In addition, the API should grow **operations** that encode the workflow:

| Area | Endpoints (planned) |
| --- | --- |
| Health | `GET /health` |
| Suppliers | `GET/POST /api/v1/suppliers`, `GET/PATCH/DELETE /api/v1/suppliers/{id}` |
| Products | `GET/POST /api/v1/products`, `GET/PATCH/DELETE /api/v1/products/{id}` (`?supplier_id=` filter) |
| Customers | `GET/POST /api/v1/customers`, `GET/PATCH/DELETE /api/v1/customers/{id}` |
| Enquiries | `GET/POST /api/v1/enquiries`, `PATCH` for outcome |
| Preorders | `GET/POST /api/v1/preorders`, `POST /api/v1/preorders/{id}/transitions` |
| Payments | `GET/POST /api/v1/preorders/{id}/payments` (status is derived, not PATCHed independently) |
| Supplier orders | generate draft from confirmed preorders; lines; transitions; reconcile received quantities |
| Inventory | list, receive, allocate (with availability checks) |
| Attention | `GET /api/v1/attention` (or similar) — derived queue |
| Analytics | `GET /api/v1/analytics/...` — enquiries, conversions, loss reasons, suppliers, prices |
| Events | later: list history for an entity |

Preorder status is **not** a free-form `PATCH`. A dedicated transition endpoint will check an allow-list of next states. The same idea applies to supplier-order status.

Exact paths can be chosen when those milestones are built. Do not add messaging webhooks or PDF export in the core API.

## Request / data flow (once features exist)

1. Owner records a catalogue product from a supplier photo (catalogue, not inventory).
2. A customer enquiry is stored against that product (outcome may still be unknown).
3. If they commit, a preorder is created (`CONFIRMED`) and the enquiry outcome becomes `PREORDERED`.
4. Payments are recorded as they arrive; paid / outstanding / payment status are derived.
5. The owner generates a draft supplier order from confirmed preorders for that supplier, reviews quantities, then marks it `PLACED`.
6. On arrival, the owner reconciles received vs ordered quantities; received items update preorders and/or inventory.
7. Ready items wait in the attention queue until collection/delivery (`FULFILLED`). Inventory-backed sales decrement available stock.
8. Analytics queries group enquiries and preorders in SQL.

## State models (planned)

### Preorder

Happy path: `INQUIRY` → `CONFIRMED` → `ORDERED_FROM_SUPPLIER` → `ARRIVED` → `READY_FOR_CUSTOMER` → `FULFILLED`

Also allowed as exits (exact edges to be coded later): `CANCELLED`, `SUPPLIER_UNAVAILABLE`

### Payment (derived from payment rows; not a stored column)

`UNPAID` | `PARTIALLY_PAID` | `PAID` | `OVERPAID` (exception when paid > quantity × agreed_price). Refunds later, from refund records.

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
| Operations in services | Rules stay testable and UI-independent | A bit more structure than “update the row” |
| Derived attention queue | Cannot drift from real state | Queries must stay cheap and clear |
| Hosted Postgres (e.g. Supabase) | No local database install or Docker | Needs `DATABASE_URL` in `.env`; tests need a separate `TEST_DATABASE_URL` |
| No Redis | No caching/queue requirement yet | Fine at this scale |
| Minimal UI until Figma | Avoid throwing away a fake dashboard | Early screens will look plain on purpose |

## Known limitations (now)

- No authentication
- No product photos
- Supplier orders, inventory, attention queue, events, and analytics are specified, not built
- Catalogue products are not inventory; there is no stock quantity yet
- Frontend still only checks that the API health endpoint responds

## Milestone 2 notes

Implemented:

- SQLAlchemy 2.0 engine/session (`app/core/db.py`)
- Alembic migration `0001_catalogue_core` (suppliers, products, customers)
- Integer primary keys (simple to explain; good enough at this scale)
- `products.supplier_id` foreign key; cannot delete a supplier that still has products
- Pydantic validation on write; service layer owns those rules
- pytest for health always; CRUD tests when `TEST_DATABASE_URL` is set

Not implemented: preorders, payments, workflow operations.

## Future improvements (explicitly not MVP / not core dependencies)

The domain must work without external messaging APIs.

- Facebook Messenger integration
- Supplier WhatsApp / WhatsApp Business integration
- Automated bank-feed payment matching
- PDF / exportable supplier order summaries
- Visual product similarity / search
- Advanced ML forecasting
- Multi-user permissions

## Milestone 1 notes

Implemented in the first commit: split frontend/backend, `/health`, env-based settings, Vite app, pytest for health. Database work moved to Milestone 2.
