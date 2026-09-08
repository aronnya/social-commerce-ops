# Project brief

Internal operations platform for a small social-commerce clothing business that mainly sells South Asian / Pakistani clothing through Facebook.

## Problem

Work is currently spread across Facebook Messenger, WhatsApp, payment records, and manual tracking. There is no single system for the order lifecycle or for learning from interest that does not become a sale.

## Product principle

Every major screen should help the user perform or understand an operational task. The platform should not become CRUD for its own sake. Data storage supports workflows, automation, exception handling and decision-making.

The system must not become a generic admin app that only stores and displays records. Its core value is coordinating and automating the real operational workflow.

## Product

A private web application for the business owner. Customers do not log in.

The system manages:

- suppliers
- supplier product / catalogue items
- customers
- customer enquiries
- preorders and preorder statuses
- payments (separate from preorder status)
- supplier orders (separate from preorder status)
- locally held inventory
- fulfilment
- demand analytics from enquiry outcomes

Storing those records is a means to run the workflow below, not the product itself.

## Catalogue vs inventory

A supplier product / catalogue item is **not** inventory.

If a supplier sends a photo of a dress, that dress can exist in the catalogue even though the business does not own it. Inventory is only items the business actually owns or has received.

Most sales are **preorders**: the owner orders from the supplier after a customer commits. Occasionally the owner buys about 20–30 dresses in advance for in-person sales.

Receiving stock purchases should increase physical inventory. Selling or allocating physical stock should reduce available inventory. The system must not allocate more physical stock than is available.

## Real-world workflow this app should support

1. Suppliers send photos of available dresses (today via WhatsApp).
2. The owner chooses products and posts selected photos on Facebook.
3. Customers enquire (today via Messenger).
4. Interested customers may preorder. The owner then orders from the supplier.
5. Confirmed preorders can be grouped by supplier into a **draft** supplier order. Quantities are consolidated, but each line still links back to the customer preorders. The owner reviews the draft, then marks it placed.
6. The supplier ships to the owner.
7. On arrival, the owner **reconciles** ordered quantities against received quantities, flags missing or unavailable items, and connects received items to the relevant preorders or to inventory.
8. The owner fulfils customer orders (collection or delivery).
9. Customers usually pay by bank transfer or Revolut. Payment state is calculated from payment records, not chosen independently of those records.

## Action / attention queue

The system should derive “what needs attention today?” from current data, rather than relying on the owner to hunt through lists. Examples:

- confirmed preorders not yet included in a supplier order
- supplier orders awaiting the next action
- arrived customer items awaiting collection or delivery
- outstanding customer balances
- supplier orders or preorders that may be delayed

This is an operational queue, not a decorative dashboard of counts.

## Payments

Payment status is **separate** from preorder status and should be **derived** from payment records where possible.

The system should calculate:

- total order amount
- amount paid
- outstanding balance
- `UNPAID` / `PARTIALLY_PAID` / `PAID`

Refunds should be modelled appropriately later, still from records rather than an unrelated manual status.

## Workflow rules (backend-enforced)

The backend must enforce valid operations. The UI must not be the only place rules live. Examples:

- only allowed preorder state transitions
- a preorder must not sit on more than one active supplier order
- inventory allocations cannot exceed available quantity
- payment and order operations must stay consistent with stored records

## History (later in the product, not a blocker for first tables)

Important workflow changes should eventually leave an audit trail, for example: enquiry created, preorder confirmed, payment recorded, supplier order placed or dispatched, item arrived, customer notified, fulfilled. That history can later support metrics such as average fulfilment time.

## Enquiry outcomes (demand data)

Capture interest even when no sale happens. Demand must not be inferred from completed sales alone. Initial outcomes:

- `PREORDERED`
- `TOO_EXPENSIVE`
- `SUPPLIER_UNAVAILABLE`
- `CUSTOMER_GHOSTED`
- `WRONG_SIZE`
- `NOT_INTERESTED`

Analytics should later answer:

- conversion rates (enquiry → preorder / sale)
- why sales are lost
- high-interest, low-conversion products
- demand by style, colour, size, price range, supplier, and time
- which suppliers’ products perform best
- what might be worth buying as local inventory

Use SQL aggregation. No machine learning in the initial product.

## State models (MVP)

Preorder lifecycle (happy path):

`INQUIRY` → `CONFIRMED` → `ORDERED_FROM_SUPPLIER` → `ARRIVED` → `READY_FOR_CUSTOMER` → `FULFILLED`

Side outcomes: `CANCELLED`, `SUPPLIER_UNAVAILABLE`

State changes must follow explicit allowed transitions (not arbitrary updates).

Payment states (separate, derived): `UNPAID`, `PARTIALLY_PAID`, `PAID` (refunds later)

Supplier-order states (separate): `DRAFT`, `PLACED`, `CONFIRMED`, `DISPATCHED`, `ARRIVED`, `RECONCILED`

## Out of scope for MVP

These must not be core dependencies. The domain must work without external messaging APIs.

- Facebook Messenger integration
- Supplier WhatsApp / WhatsApp Business integration
- Automated payment reconciliation against bank feeds
- Visual product similarity / search
- Advanced ML forecasting
- PDF / exportable supplier order summaries
- Microservices, Kubernetes, Kafka, Redis, GraphQL

## Constraints

- React + TypeScript frontend
- Python FastAPI + SQLAlchemy + Pydantic backend
- PostgreSQL
- UI will come from Figma later; do not invent a generic SaaS dashboard
- No real customer/supplier/payment data in the repository
- Secrets never in source control
