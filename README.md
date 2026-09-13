# Social Commerce Operations Platform

Private internal web app for running a small social-commerce clothing business that sells mainly through Facebook.

This is **not** a customer-facing shop. It is an operations tool for suppliers, catalogue items, customers, enquiries, preorders, payments, supplier orders, local inventory, fulfilment, and demand analytics.

## Status

Milestone 2 is in place: hosted PostgreSQL (SQLAlchemy + Alembic), plus supplier, catalogue product, and customer APIs. Workflow features (enquiries, preorders, payments, supplier orders) are not built yet.

## Repository layout

- `backend/` — Python FastAPI API
- `frontend/` — React + TypeScript SPA
- `PROJECT_BRIEF.md` — product requirements
- `ARCHITECTURE.md` — how the system is designed (interview notes live here too)

## Prerequisites

- Python 3.11+ (this machine currently has 3.14, which is fine)
- Node.js 20+
- Git

## First-time setup

```powershell
cd C:\Users\khana\Projects\social-commerce-ops
copy .env.example .env
```

Edit `.env` and set `DATABASE_URL` to a hosted PostgreSQL URL (for example Supabase). Use the SQLAlchemy driver prefix `postgresql+psycopg://` and include `sslmode=require` if the host asks for SSL. Never commit `.env`.

For pytest, set `TEST_DATABASE_URL` to a **separate** database. Tests create and drop tables; do not point them at real business data.

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

- API: http://127.0.0.1:8000
- API docs: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/health
- Suppliers: http://127.0.0.1:8000/api/v1/suppliers
- Products (catalogue): http://127.0.0.1:8000/api/v1/products
- Customers: http://127.0.0.1:8000/api/v1/customers
- Frontend: http://localhost:5173

## Tests

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pytest
```

`GET /health` always runs. Supplier/product/customer tests skip unless `TEST_DATABASE_URL` is set.

## Security

- Never commit `.env` or real credentials.
- Never commit real customer, supplier, or payment data.
- Use synthetic demo data only.

## GitHub

Create a private GitHub repository when you are ready, then add it as `origin`. Keep the repo private: this app will hold business operations data locally even if the committed code stays synthetic.
