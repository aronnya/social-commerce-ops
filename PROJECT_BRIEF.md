# Project brief

Internal operations platform for a small social-commerce clothing business that mainly sells South Asian / Pakistani clothing through Facebook.

## Problem

Work is currently spread across Facebook Messenger, WhatsApp, payment records, and manual tracking. There is no single system for the order lifecycle or for learning from interest that does not become a sale.

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

## Catalogue vs inventory

A supplier product / catalogue item is **not** inventory.

If a supplier sends a photo of a dress, that dress can exist in the catalogue even though the business does not own it. Inventory is only items the business actually owns or has received.

Most sales are **preorders**: the owner orders from the supplier after a customer commits. Occasionally the owner buys about 20–30 dresses in advance for in-person sales.

## Real-world workflow this app should support

1. Suppliers send photos of available dresses (today via WhatsApp).
2. The owner chooses products and posts selected photos on Facebook.
3. Customers enquire (today via Messenger).
4. Interested customers may preorder. The owner then orders from the supplier.
5. Several customer preorders may be grouped into one supplier order.
6. The supplier ships to the owner.
7. The owner records arrival and fulfils customer orders.
8. Customers usually pay by bank transfer or Revolut.

## Enquiry outcomes (demand data)

Capture interest even when no sale happens. Initial outcomes:

- `PREORDERED`
- `TOO_EXPENSIVE`
- `SUPPLIER_UNAVAILABLE`
- `CUSTOMER_GHOSTED`
- `WRONG_SIZE`
- `NOT_INTERESTED`

Analytics should later answer:

- Which products get the most enquiries?
- Which convert into orders?
- Why are sales lost?
- Which suppliers’ products perform best?
- Which price ranges have demand?
- What might be worth buying as local inventory?

Use SQL aggregation. No machine learning in the initial product.

## State models (MVP)

Preorder lifecycle (happy path):

`INQUIRY` → `CONFIRMED` → `ORDERED_FROM_SUPPLIER` → `ARRIVED` → `READY_FOR_CUSTOMER` → `FULFILLED`

Side outcomes: `CANCELLED`, `SUPPLIER_UNAVAILABLE`

State changes must follow explicit allowed transitions (not arbitrary updates).

Payment states (separate): `UNPAID`, `PARTIALLY_PAID`, `PAID`, `REFUNDED`

Supplier-order states (separate): `DRAFT`, `PLACED`, `CONFIRMED`, `DISPATCHED`, `ARRIVED`, `RECONCILED`

## Out of scope for MVP

- Facebook Messenger integration
- WhatsApp Business integration
- Automated payment reconciliation
- Visual product similarity / search
- Advanced demand forecasting
- Microservices, Kubernetes, Kafka, Redis, GraphQL

## Constraints

- React + TypeScript frontend
- Python FastAPI + SQLAlchemy + Pydantic backend
- PostgreSQL
- UI will come from Figma later; do not invent a generic SaaS dashboard
- No real customer/supplier/payment data in the repository
- Secrets never in source control
