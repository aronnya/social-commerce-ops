# Architecture

This document is the living explanation of how the system is built. It is written so a beginner can defend the project in an internship interview.

## Product principle

Every major screen should help the user perform or understand an operational task. The platform should not become CRUD for its own sake. Data storage supports workflows, automation, exception handling and decision-making.

REST list/create/update endpoints exist because the workflow needs records. They are not the product. The valuable behaviour is coordinating preorders, supplier orders, payments, inventory, exceptions, and demand decisions.

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

The API and UI run on the host machine so logs and breakpoints stay simple. PostgreSQL is configured with `DATABASE_URL` (local or hosted). Do not put that URL in git.

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
      models.py        # SQLAlchemy entities (catalogue through fulfilment)
      schemas.py       # Pydantic request/response shapes
      services.py      # database operations and rules
      api.py           # /api/v1 HTTP routes
    alembic/           # database migrations 0001–0007
    scripts/           # synthetic demo seeder (guarded; not an API)
    tests/
    requirements.txt
    alembic.ini
  frontend/            # Vite + React + TypeScript
  docs/screenshots/    # README captures (synthetic demo)
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
| `preorders` | Implemented | A customer commitment to buy a catalogue item |
| `payments` | Implemented | Individual transfers (bank / Revolut). Separate from preorder status. |
| `supplier_orders` | Implemented | A batch sent to a supplier. `RECONCILED` is set only by `POST /supplier-orders/{id}/reconcile`. |
| `supplier_order_lines` | Implemented | Consolidated rows: ordered `quantity` is immutable; `received_quantity` is a separate fact |
| `inventory_lots` | Implemented | Physically owned/unassigned stock. Created by reconciliation remainder; API is read-only in v1. |
| `fulfilments` | Implemented | How a customer received a ready preorder (`HOME_COLLECTION` or `POST`). 1:1 with preorder; write-once. Completing uses `POST /api/v1/preorders/{id}/fulfil`. |
| `workflow_events` | Later | Audit trail of important workflow changes |

Relationships in plain English:

- A supplier has many products.
- A product belongs to one supplier.
- A customer has many enquiries and many preorders.
- An enquiry is about one product and one customer. It may later link to a preorder, or it may end with a lost-sale reason.
- A preorder is for one customer and one product. It may come from an enquiry (optional, because walk-in sales exist).
- A preorder may be attached to one **active** supplier order once it is grouped for buying. It must not be included in multiple active supplier orders.
- Payments belong to a preorder. Several payments can add up to the agreed price. Payment status is calculated from those rows.
- A fulfilled preorder has at most one **fulfilment** record: collection at home, or post (regular or registered). The address written on a packet is snapshotted on that row, not on the customer. Postage cost is optional operational spend and is not part of payment totals. Preorders marked `FULFILLED` before this table existed may have no fulfilment row; those facts are not invented.
- A supplier order has many lines. A line consolidates quantity for a product/variant, still pointing at the customer preorders. Ordered quantity and received quantity are separate facts; discrepancy is derived (`received - ordered`). Customer-bound preorder units do not enter inventory lots.
- An inventory lot points at a product and records quantity actually on hand that the business owns and has not assigned to a customer preorder. Direct stock purchases, later receipts, and consumption are deferred.
- Workflow events (when added) point at the relevant entity and record what happened and when.

Why enquiry and preorder are separate: analytics must count “people asked about this dress” even when they never ordered. If we only stored preorders, we would throw away lost-demand data.

Why payment status is not a preorder status: the dress can already be ordered from Pakistan while the customer has paid, partly paid, or not paid. Mixing those into one enum would make reports and rules messy.

Why supplier-order status is separate: one supplier shipment can cover many customer preorders. The shipment can be “dispatched” while an individual preorder is still “ordered from supplier”.

Why fulfilment is not a preorder column dump: method, postage, address, and tracking are operational facts about the handoff, like payment rows. `READY_FOR_CUSTOMER` → `FULFILLED` is owned by `fulfil_preorder`, the same way placement owns `ORDERED_FROM_SUPPLIER` and reconciliation owns `ARRIVED`. Generic transitions cannot set `FULFILLED`. Payment state does not gate fulfilment. v1 records are immutable (no update/delete). An Post, live tracking, labels, ETAs, and extra shipping statuses are deferred.

## Operational behaviours

These behaviours are implemented in `services.py` and exposed as read/write HTTP operations. The frontend calls those operations; it does not invent parallel state machines.

### Action / attention queue

`GET /api/v1/attention` is a **derived** queue from current tables. There is no `AttentionTask` table and no way to dismiss an item except by completing the underlying operation. The endpoint is read-only.

v1 types, in display order:

1. `preorder_overpaid` — `sum(payments) > quantity × agreed_price`. May persist until refunds exist; payment amounts cannot be reduced.
2. `supplier_order_needs_reconciliation` — supplier order `ARRIVED`
3. `preorder_needs_customer_ready` — preorder `ARRIVED`
4. `preorder_needs_fulfilment` — preorder `READY_FOR_CUSTOMER`. Completing `fulfil_preorder` sets `FULFILLED` and the item disappears; the queue is not redesigned.
5. `supplier_order_draft_needs_placement` — supplier order `DRAFT`
6. `preorder_needs_supplier_order` — `CONFIRMED` with no supplier-order allocation

Within a type: `occurred_at` ASC, then `entity_type`, then `entity_id`. Not a scored urgency.

Deferred: in-flight supplier orders (`PLACED`/`CONFIRMED`/`DISPATCHED`), blanket unpaid/partial payments, open enquiries, SLA/due dates, shortage still allocated after recon.

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

Catalogue `products` and `inventory_lots` stay different tables. In v1:

- unassigned remainder after supplier-order reconciliation creates `InventoryLot` rows
- `GET /api/v1/inventory` is read-only
- consuming lots for local-stock sales, extra receipts, and allocation-from-inventory are deferred

Preorder fulfilment from a Pakistan shipment does not decrement inventory lots. The local-stock consumption path is specified, not built.

### Workflow / business-rule enforcement

Invalid operations should fail in the backend (clear HTTP errors), including:

- illegal preorder or supplier-order transitions
- attaching a preorder to a second active supplier order
- over-allocating inventory
- payments that would make totals inconsistent (for example ignoring the agreed amount)

### Event / history tracking

A `workflow_events` (or similarly named) history can still be added. Examples: enquiry created, preorder confirmed, payment recorded, supplier order placed, item arrived, fulfilled. It is not required for v1 operations.

### Demand intelligence

`list_demand_analytics` is a **derived** read model (no analytics tables). Conversion is an actual `Preorder.enquiry_id` link, never `Enquiry.outcome == PREORDERED`. Open enquiries are excluded from the conversion denominator (`resolved = converted + lost`; rate is `null` when resolved is 0). Lost demand is the five coded enquiry outcomes only, in a fixed order, including zero buckets.

Product and supplier rows are raw aggregates (enquiry count, requested quantity, distinct customers, converted/lost/open, rate) for entities with at least one enquiry in the window. Supplier demand is catalogue attribution via `Product.supplier_id`, not shipment quality. Optional `[from, to)` filters `Enquiry.enquired_at` only. Reconciliation snapshot is all-time `RECONCILED` orders (ordered vs received, shortage/excess) with `date_basis = "all_time"`.

No revenue/cash/margin, no timing/SLA metrics, no scoring, no high-interest flag, no ML. `GET /api/v1/analytics/demand` is read-only. Optional `from`/`to` query params are timezone-aware and filter `Enquiry.enquired_at` as `[from, to)`.

## REST API

Version prefix: `/api/v1`.

Resource endpoints exist for the entities above. Workflow is encoded as **operations**, not free-form status edits:

| Area | Endpoints |
| --- | --- |
| Health | `GET /health` (API process; not database connectivity) |
| Suppliers | `GET/POST /api/v1/suppliers`, `GET/PATCH/DELETE /api/v1/suppliers/{id}` |
| Products | `GET/POST /api/v1/products`, `GET/PATCH/DELETE /api/v1/products/{id}` (`?supplier_id=` filter) |
| Customers | `GET/POST /api/v1/customers`, `GET/PATCH/DELETE /api/v1/customers/{id}` |
| Enquiries | `GET/POST /api/v1/enquiries`, `PATCH` for outcome |
| Preorders | `GET/POST /api/v1/preorders`, `POST /api/v1/preorders/{id}/transitions`, `POST /api/v1/preorders/{id}/fulfil` (`FULFILLED` is not a generic transition) |
| Payments | `GET/POST /api/v1/preorders/{id}/payments` (status is derived, not PATCHed independently) |
| Supplier orders | generate draft; place; transitions; reconcile received quantities |
| Inventory | `GET /api/v1/inventory` (read-only in v1) |
| Attention | `GET /api/v1/attention` — derived queue |
| Analytics | `GET /api/v1/analytics/demand` — derived enquiry conversion, lost demand, product/supplier demand, all-time recon snapshot |
| Events | later: list history for an entity |

Preorder status is **not** a free-form `PATCH`. A dedicated transition endpoint checks an allow-list of next states. The same idea applies to supplier-order status. Messaging webhooks and PDF export are out of the core API.

## Request / data flow

1. Owner records a catalogue product from a supplier photo (catalogue, not inventory).
2. A customer enquiry is stored against that product (outcome may still be unknown).
3. If they commit, a preorder is created (`CONFIRMED`) and the enquiry outcome becomes `PREORDERED`.
4. Payments are recorded as they arrive; paid / outstanding / payment status are derived.
5. The owner generates a draft supplier order from confirmed preorders for that supplier, reviews quantities, then marks it `PLACED`.
6. On arrival, the owner reconciles received vs ordered quantities; received items update preorders and/or inventory.
7. Ready items wait in the attention queue until the owner records fulfilment: home collection, or post (`REGULAR` / `REGISTERED`, address snapshot, optional postage cost, registered tracking required). That operation sets `FULFILLED`.
8. Analytics queries group enquiries and preorders in SQL. Conversion uses the preorder link.

## State models

### Preorder

Happy path: `CONFIRMED` → `ORDERED_FROM_SUPPLIER` → `ARRIVED` → `READY_FOR_CUSTOMER` → `FULFILLED`

`FULFILLED` is set only by `POST /api/v1/preorders/{id}/fulfil` (`fulfil_preorder`). From `READY_FOR_CUSTOMER`, generic transitions allow `CANCELLED` only.

- `HOME_COLLECTION`: no postal fields
- `POST` + `REGULAR`: delivery address required, postage cost optional, tracking reference null
- `POST` + `REGISTERED`: delivery address required, postage cost optional, tracking reference required

Payment remains independent of fulfilment. `CANCELLED` and `SUPPLIER_UNAVAILABLE` remain exits on earlier preorder states.

### Payment (derived from payment rows; not a stored column)

`UNPAID` | `PARTIALLY_PAID` | `PAID` | `OVERPAID` (exception when paid > quantity × agreed_price). Refunds later, from refund records.

### Supplier order

`DRAFT` → `PLACED` → `CONFIRMED` → `DISPATCHED` → `ARRIVED`, then `POST .../reconcile` → `RECONCILED`. Generic transitions cannot set `PLACED` or `RECONCILED`. Ordered line `quantity` is never overwritten; clients may derive `received_quantity - quantity`. Unassigned received units become `InventoryLot` rows. `GET /api/v1/inventory` is read-only.

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
| PostgreSQL (not SQLite) | Same engine in development and tests | Needs `DATABASE_URL` / `TEST_DATABASE_URL` |
| No Redis | No caching/queue requirement yet | Fine at this scale |
| Operations UI over generic admin | Screens match the workflow | Not a public storefront |

## Known limitations (now)

- No authentication
- No product photos
- Events, multiple receipts, stock-buy lines, allocation release, inventory consumption, returns/refunds/damage are specified, not built
- Demand analytics is derived and read-only (`GET /api/v1/analytics/demand`). Enquiry `PREORDERED` can still be set without a preorder; conversion uses the preorder link and exposes mismatch counts. No `enquired_at` index yet.
- Attention queue is derived (no table); `GET /api/v1/attention` is read-only. `OVERPAID` items can stick until refunds exist.
- Catalogue products are not inventory; unassigned owned stock lives on `InventoryLot`, not on `Product`
- No An Post integration, live tracking, labels, postage price list, or extra shipping statuses. Fulfilment rows are immutable in v1 (no PATCH/DELETE).
- Sidebar health copy reflects API reachability (`GET /health`), not database connectivity.

## Catalogue milestone notes

Implemented early:

- SQLAlchemy 2.0 engine/session (`app/core/db.py`)
- Alembic from `0001_catalogue_core` through `0007_preorder_fulfilments`
- Integer primary keys (simple to explain; good enough at this scale)
- `products.supplier_id` foreign key; cannot delete a supplier that still has products
- Pydantic validation on write; service layer owns those rules
- pytest for health always; database tests when `TEST_DATABASE_URL` is set

Later milestones added enquiries, preorders, payments, supplier orders, reconciliation, inventory lots, fulfilment, attention, demand analytics, and the React operations UI. See the root README for the recruiter-facing summary.

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
