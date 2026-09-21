# Social Commerce Operations Platform

An internal operations platform built for the workflow of a real social-commerce clothing business, where supplier catalogue products generate customer enquiries and preorders **before** most stock is physically purchased.

This is not a customer-facing shop. The operator records catalogue items, demand, buying, payments, arrivals, owned stock, and customer handoff in one system.

**The public repository and screenshots use synthetic demo data only.** There are no real customer, supplier, or payment records in git.

## Why I Built It

Social-commerce clothing often sells from a supplier photo before the business owns the garment. Work then spreads across messages, spreadsheets, and payment apps. This project models that workflow as an operations system:

- suppliers provide clothing catalogue items
- products can be advertised without being owned inventory
- customers enquire through social channels (recorded here; not ingested live)
- confirmed demand becomes preorders
- multiple preorders can be consolidated into supplier orders
- payments are tracked independently of shipment status
- supplier deliveries must be reconciled against what was ordered
- excess received units become owned inventory
- customers ultimately collect in person or receive orders by post

## Key Engineering Decisions

1. **Catalogue ≠ inventory.** A product is a sellable description from a supplier. Owned stock lives on inventory lots created from reconciliation remainder.
2. **Enquiry ≠ preorder.** Interest and lost demand are stored even when nobody commits to buy.
3. **Payment state is independent of preorder state.** A garment can be on a boat while the customer is unpaid, partial, paid, or overpaid. Status is derived from payment rows.
4. **Supplier orders preserve preorder allocations.** Draft generation consolidates quantities by product but keeps a link to each customer preorder.
5. **Reconciliation turns physical receipt into consequences.** Ordered quantity stays historical; received quantity is recorded once; customer-bound units move preorders; remainder becomes inventory.
6. **The attention queue is derived.** Actionable work is queried from live state. There is no separate task table to drift out of date.
7. **Analytics conversion uses a linked preorder.** An enquiry whose outcome says `PREORDERED` is not treated as converted unless a `Preorder.enquiry_id` link exists.
8. **Customer fulfilment is a dedicated operation.** `FULFILLED` is not a free-form status edit. Home collection and post (including registered tracking) are recorded on a fulfilment row.

## Core Workflow

```
Supplier Catalogue
    ↓
Customer Enquiry
    ↓
Confirmed Preorder
    ↓
Supplier Order Generation (DRAFT)
    ↓
Supplier Order Placement
    ↓
Delivery Reconciliation
    ├── Customer-bound units → Preorders ARRIVED
    └── Excess units → Inventory lots
    ↓
Ready for Customer
    ↓
Home Collection / Post
```

Payment recording runs in parallel: bank transfer and Revolut rows update a derived payment summary without moving the preorder state machine.

## Features

Implemented in the current portfolio scope:

- supplier catalogue management
- customer and enquiry tracking, including lost-demand outcomes
- explicit preorder workflow
- independent payment ledger and derived payment status
- supplier-order generation from confirmed demand
- preorder-to-supplier-order allocations
- supplier delivery reconciliation
- inventory lots from excess received stock
- derived operational attention queue
- demand / lost-demand analytics
- customer fulfilment via home collection or post
- registered-post tracking reference capture

Not claimed (deliberately out of scope):

- authentication
- live WhatsApp or Facebook ingestion
- An Post or other carrier APIs
- live parcel tracking
- machine learning, forecasting, or recommendations
- production hosting
- automated supplier ordering
- payment-provider integration

## Architecture

| Layer | Choice |
| --- | --- |
| Frontend | React + TypeScript (Vite) |
| Backend | FastAPI + Python |
| Persistence | PostgreSQL + SQLAlchemy 2 |
| Migrations | Alembic (`0001`–`0007`) |
| Validation | Pydantic |
| Testing | pytest against PostgreSQL |

```
React UI → HTTP/JSON API → FastAPI → SQLAlchemy → PostgreSQL
```

Development and automated tests use PostgreSQL. The suite is not swapped onto SQLite.

The API and UI are local processes. A `DATABASE_URL` points at PostgreSQL. This README does not claim a hosted production deployment.

## Data Model

| Entity | Role |
| --- | --- |
| **Supplier** | Source of catalogue products and supplier orders |
| **Product** | Catalogue item (style/colour/size/prices). Not on-hand stock |
| **Customer** | Person who enquires or preorders |
| **Enquiry** | Interest in one product; may stay open, convert, or record a lost reason |
| **Preorder** | Commitment to buy; optional link to an enquiry; walk-ins allowed |
| **Payment** | Individual transfer against a preorder |
| **SupplierOrder** | Batch purchase from one supplier |
| **SupplierOrderLine** | Consolidated product quantity on that batch |
| **SupplierOrderAllocation** | Which preorder (and quantity) sits on a line |
| **InventoryLot** | Owned units not bound to a customer preorder |
| **Fulfilment** | Write-once record of home collection or post for a ready preorder |

The separations exist so demand, buying, cash, and physical stock can disagree in real life without corrupting each other.

## State Machines

### Preorder

Happy path:

`CONFIRMED` → `ORDERED_FROM_SUPPLIER` → `ARRIVED` → `READY_FOR_CUSTOMER` → `FULFILLED`

Side terminal states: `CANCELLED`, `SUPPLIER_UNAVAILABLE`.

`ORDERED_FROM_SUPPLIER` is set when a draft supplier order is **placed**. `ARRIVED` is set by **reconciliation**. `FULFILLED` is set only by **fulfil**. Generic transitions cannot take those shortcuts.

### Supplier order

`DRAFT` → `PLACED` → `CONFIRMED` → `DISPATCHED` → `ARRIVED` → `RECONCILED`

`PLACED` and `RECONCILED` are dedicated operations, not generic status patches.

### Payment (derived, not stored)

`UNPAID` · `PARTIALLY_PAID` · `PAID` · `OVERPAID`

Computed from `quantity × agreed_price` versus the sum of payment rows. `OVERPAID` is an exception state, not a dropdown.

## Reconciliation

On an `ARRIVED` supplier order:

- line **ordered quantity** is historical and is not overwritten
- **received quantity** is recorded per line
- customer-bound allocations are considered first
- default arrival uses deterministic FIFO over allocated preorders
- whole preorders arrive; partial preorder arrival is not modelled
- processing stops at the first unfillable preorder instead of skipping ahead
- leftover received units become **inventory lots**
- shortages leave later preorders waiting (`ORDERED_FROM_SUPPLIER`)
- reconciliation is irreversible in v1

## Demand Analytics

`GET /api/v1/analytics/demand` is a derived read model (optional `from`/`to` on enquiry time):

- total, open, resolved, converted, and lost enquiry counts
- conversion rate (`converted / resolved`, or null when resolved is 0)
- five factual lost-demand reasons
- product and supplier demand aggregates
- integrity signals (preordered without a link; linked preorder with a mismatched outcome)
- all-time supplier reconciliation snapshot (ordered vs received)

**Converted** means an enquiry with an actual linked preorder. The `PREORDERED` outcome enum is not sufficient.

This is operational analytics, not machine learning.

## Operational Attention Queue

`GET /api/v1/attention` highlights live actionable states, including:

- confirmed preorder not yet allocated to a supplier order
- draft supplier order awaiting placement
- arrived supplier order awaiting reconciliation
- arrived preorder awaiting ready-for-customer
- ready preorder awaiting fulfilment
- overpayment

Completing the real operation removes the item. No separate task table.

## Screenshots

Screenshots will be added from the synthetic demo dataset.

### Dashboard

### Preorders

### Supplier Orders & Reconciliation

### Enquiries

### Catalogue & Inventory

### Demand Insights

## Running Locally

Prerequisites: Python 3.11+, Node.js 20+, PostgreSQL, Git.

Copy environment placeholders (never commit `.env`):

```powershell
copy .env.example .env
```

Set `DATABASE_URL` to PostgreSQL. Example shape only:

```
DATABASE_URL=postgresql://USER:PASSWORD@127.0.0.1:5432/YOUR_DATABASE
```

Backend:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend (second terminal):

```powershell
cd frontend
npm install
npm run dev
```

- UI: http://localhost:5173
- API: http://127.0.0.1:8000
- OpenAPI: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/health (`/health` means the API process is reachable, not that the database is healthy)

### Synthetic demo data

Use a **local** database whose name contains `demo` or `test`. Do not point this at MAIN or any hosted production database.

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
$env:ALLOW_DEMO_SEED="1"
$env:DEMO_DATABASE_URL="postgresql://USER:PASSWORD@127.0.0.1:5432/sco_demo"
python -m scripts.seed_demo --reset
```

The seeder refuses to run unless `ALLOW_DEMO_SEED=1` and the target is loopback **and** the database name contains `demo` or `test`. `--reset` wipes application tables on that guarded database only, then inserts fictional records through the same service operations the API uses.

## Testing

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pytest
```

`GET /health` always runs. Database-backed tests require `TEST_DATABASE_URL` on a dedicated PostgreSQL database (they create and drop tables). Coverage includes catalogue CRUD, enquiry/preorder rules, payments, supplier-order generation and placement, reconciliation and inventory remainder, fulfilment, attention, demand analytics, and demo-seed safety guards.

Frontend:

```powershell
cd frontend
npm run build
npm run lint
```

## Privacy / Demo Data

- this repository contains no real customer records
- real supplier or private payment data must not be committed
- screenshots and local demos should use the synthetic seeder (or equivalent fictional records)

## Project Status

Feature-complete for the current portfolio scope.

Deliberately deferred: social-platform ingestion, authentication, carrier APIs, refunds, inventory consumption from local stock, photos, and forecasting.

Further engineering notes live in [ARCHITECTURE.md](ARCHITECTURE.md). Product intent is in [PROJECT_BRIEF.md](PROJECT_BRIEF.md).
