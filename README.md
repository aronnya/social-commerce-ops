# Social Commerce Operations Platform

Private internal web app for running a small social-commerce clothing business that sells mainly through Facebook.

This is **not** a customer-facing shop. It is an operations tool for suppliers, catalogue items, customers, enquiries, preorders, payments, supplier orders, local inventory, fulfilment, and demand analytics.

## Status

Milestone 1 is in place: repository layout, documentation, a FastAPI health endpoint, and a React + TypeScript frontend. Business features and the database connection are not implemented yet.

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

The API does not connect to a database yet. Later we will use hosted PostgreSQL (for example Supabase). Do not put real credentials in git.

Backend:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
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
- Frontend: http://localhost:5173

## Tests

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pytest
```

## Security

- Never commit `.env` or real credentials.
- Never commit real customer, supplier, or payment data.
- Use synthetic demo data only.

## GitHub

Create a private GitHub repository when you are ready, then add it as `origin`. Keep the repo private: this app will hold business operations data locally even if the committed code stays synthetic.
